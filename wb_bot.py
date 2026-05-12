"""wb_bot.py — thin Setup B strategy bot for Wave Breakout entries.

Same shape as squeeze_bot.py but wired to WaveBreakoutDetector. Consumes
ticks + bars from data_engine.py over the Unix socket, runs the WB
detector per symbol, and submits orders to Alpaca on the THIRD paper
account.

Per directive: fail-CLOSED on stream_paused / socket disconnect. No
IBKR connection, no subscription management, no tick cache.
"""

from __future__ import annotations

import math
import os
import signal
import socket
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from engine_bot_common import (
    DailyRisk,
    EngineState,
    bar_from_message,
    connect_to_engine,
    engine_reader_thread,
    get_priced_limit,
    make_alpaca_broker,
    now_et,
    now_iso_et,
    place_with_retry,
    starting_equity_from_broker,
    wait_for_fill,
    ET,
    UTC,
)
from engine_ipc import (
    BarMessage,
    SubscriptionsMessage,
    TickMessage,
)
from wave_breakout_detector import WaveBreakoutDetector


# ══════════════════════════════════════════════════════════════════════
# Config (WB-specific knobs — reads from .env via shared loader)
# ══════════════════════════════════════════════════════════════════════

WB_ENABLED = os.getenv("WB_WAVE_BREAKOUT_ENABLED", "1") == "1"

WB_RISK_PCT = float(os.getenv("WB_WB_RISK_PCT", "0.025"))
WB_RISK_FLOOR = float(os.getenv("WB_WB_RISK_FLOOR_DOLLARS", "500"))
WB_RISK_CEIL = float(os.getenv("WB_WB_RISK_CEILING_DOLLARS", "5000"))
WB_MIN_R_PER_SHARE = float(os.getenv("WB_WB_MIN_RISK_PER_SHARE", "0.01"))
WB_MIN_RISK_PCT = float(os.getenv("WB_WB_MIN_RISK_PCT", "0.001"))
WB_MAX_NOTIONAL = float(os.getenv("WB_WB_MAX_NOTIONAL", "50000"))
WB_NOTIONAL_PER_POS_PCT = float(os.getenv("WB_WB_NOTIONAL_PER_POSITION_PCT", "1.0"))
WB_NOTIONAL_FLOOR = float(os.getenv("WB_WB_NOTIONAL_FLOOR", "10000"))
WB_MAX_CONCURRENT = int(os.getenv("WB_WB_MAX_CONCURRENT", "3"))

ENTRY_SLIPPAGE_MIN = float(os.getenv("WB_ENTRY_SLIPPAGE_MIN", "0.05"))
ENTRY_SLIPPAGE_PCT = float(os.getenv("WB_ENTRY_SLIPPAGE_PCT", "0.005"))
ENTRY_RETRY_TIMEOUT_SEC = int(os.getenv("WB_ENTRY_RETRY_TIMEOUT_SEC", "10"))

# Trailing-stop knobs (mirror WaveBreakoutDetector's defaults; the detector
# reads them itself but the bot wants visibility for log lines + persistence).
WB_TRAILING_ACTIVATE_R = float(os.getenv("WB_WB_TRAILING_ACTIVATE_R", "1.0"))
WB_TRAILING_DISTANCE_R = float(os.getenv("WB_WB_TRAILING_DISTANCE_R", "0.5"))
WB_HARD_STOP_R = float(os.getenv("WB_WB_HARD_STOP_R", "1.0"))
# Pyramid trigger leg2 is SILENT in Setup A per 2026-05-08 breakdown — the
# detector emits WB_PYRAMID but Setup A's subbot doesn't wire it to an
# Alpaca BUY. We mirror that exactly: log the signal, don't place leg2.
WB_PYRAMID_ENABLED = os.getenv("WB_WB_PYRAMID_ENABLED", "0") == "1"


# ══════════════════════════════════════════════════════════════════════
# Per-symbol position
# ══════════════════════════════════════════════════════════════════════


@dataclass
class _WBPosition:
    """WB position state.

    The WB exit logic lives almost entirely INSIDE the WaveBreakoutDetector:
    activation, trail update, hard stop, pyramid trigger all live in
    `WaveBreakoutDetector._update_position`. The bot just routes the
    detector's WB_EXIT message to an Alpaca SELL. So the bot-side state
    we carry is leaner than squeeze's — but we still mirror the trail
    flags for log audits.
    """
    symbol: str
    qty: int
    entry: float
    stop: float
    score: int
    risk_dollars: float
    entry_time: datetime
    order_id: str
    peak: float
    pyramid_filled: bool = False
    # Trail-state mirror — for log lines + audit.
    trail_armed: bool = False
    trail_stop: float = 0.0
    fill_confirmed: bool = False
    # In-flight guard for exit retry loop (see squeeze_bot for rationale).
    exit_in_flight: bool = False


# ══════════════════════════════════════════════════════════════════════
# Helpers (size + notional cap — port of Setup A's compute_wb_position_size)
# ══════════════════════════════════════════════════════════════════════


def _wb_effective_notional_cap(equity: float) -> tuple[float, float, float, float]:
    """Returns (effective_cap, hard_ceiling, equity_cap, floor) — same as
    Setup A's _wb_effective_notional_cap. The equity-tied cap is the
    correctness fix from 2026-05-08."""
    hard_ceiling = WB_MAX_NOTIONAL
    equity_cap = equity * WB_NOTIONAL_PER_POS_PCT
    floor = WB_NOTIONAL_FLOOR
    effective = min(hard_ceiling, max(floor, equity_cap))
    return effective, hard_ceiling, equity_cap, floor


def _compute_wb_position_size(entry: float, stop: float,
                              equity: float) -> tuple[int, float]:
    """Mirror Setup A's compute_wb_position_size for parity. Returns
    (shares, risk_dollars)."""
    risk_per_share = entry - stop
    floor_risk_per_share = max(WB_MIN_R_PER_SHARE, entry * WB_MIN_RISK_PCT)
    if risk_per_share < floor_risk_per_share:
        return 0, 0.0
    risk_dollars = max(WB_RISK_FLOOR, min(WB_RISK_CEIL, equity * WB_RISK_PCT))
    shares_by_risk = int(math.floor(risk_dollars / risk_per_share))
    eff_cap, _, _, _ = _wb_effective_notional_cap(equity)
    shares_by_notional = int(math.floor(eff_cap / max(entry, 0.01)))
    qty = min(shares_by_risk, shares_by_notional)
    return max(0, qty), risk_dollars


# ══════════════════════════════════════════════════════════════════════
# Bot
# ══════════════════════════════════════════════════════════════════════


class WBBot:
    def __init__(self):
        if not WB_ENABLED:
            raise SystemExit("WB_WAVE_BREAKOUT_ENABLED=0 — refusing to start.")
        self.bot_id = "wb_bot"
        self.broker = make_alpaca_broker()
        self.starting_equity = starting_equity_from_broker(self.broker)
        self.risk = DailyRisk(self.starting_equity)
        print(f"[WB] {now_iso_et()} starting equity ${self.starting_equity:,.0f} "
              f"(third Alpaca paper account)", flush=True)
        self.state = EngineState()
        self.detectors: dict[str, WaveBreakoutDetector] = {}
        self.positions: dict[str, _WBPosition] = {}
        # RLock for consistency with squeeze_bot; persistence helpers
        # (added in a later commit) re-enter the lock from contexts
        # already holding it. Plain Lock would deadlock.
        self._positions_lock = threading.RLock()
        self._shutdown = threading.Event()

    def _ensure_detector(self, symbol: str) -> WaveBreakoutDetector:
        d = self.detectors.get(symbol)
        if d is None:
            d = WaveBreakoutDetector(symbol)
            self.detectors[symbol] = d
        return d

    def _active_count(self) -> int:
        return sum(1 for _ in self.positions.values())

    # ── Event handlers ────────────────────────────────────────────────

    def on_tick(self, msg: TickMessage):
        sym = msg.symbol
        det = self._ensure_detector(sym)
        try:
            res = det.on_trade_price(msg.price)
        except Exception as e:
            print(f"[WB] {now_iso_et()} {sym} detector tick error: {e!r}",
                  flush=True)
            return
        # Update bot-side peak mirror. The detector tracks its own peak
        # for the trail math, but the bot mirroring keeps the audit log
        # consistent and gives a later persistence layer a current peak
        # to flush. Peak-only update — no other state changes here.
        with self._positions_lock:
            pos = self.positions.get(sym)
            if pos is not None and pos.fill_confirmed and msg.price > pos.peak:
                pos.peak = msg.price
        if not res:
            return
        if res.startswith("WB_ENTER"):
            self._handle_entry(sym, res, det)
        elif res.startswith("WB_EXIT"):
            self._handle_exit(sym, res)
        elif res.startswith("WB_TRAIL_ARMED"):
            # Mirror trail state onto the bot-side position so a later
            # persistence layer can capture "trail is armed" + the
            # current trail_stop. The detector remains the source of
            # truth for trail math — the bot just shadows the flag.
            with self._positions_lock:
                pos = self.positions.get(sym)
                if pos is not None:
                    pos.trail_armed = True
                    for tok in res.split():
                        if tok.startswith("trail="):
                            try:
                                pos.trail_stop = float(tok.split("=", 1)[1])
                            except ValueError:
                                pass
            print(f"[WB] {now_iso_et()} {sym} {res}", flush=True)
        elif res.startswith("WB_PYRAMID"):
            # Pyramid leg2 is SILENT per Setup A (2026-05-08 breakdown
            # documented "pyramid leg2 may not be wired to Alpaca
            # execution"). We log the trigger but DO NOT place a second
            # BUY. WB_WB_PYRAMID_ENABLED is also OFF by default in env.
            #
            # If we ever decide to wire leg2, the place would be here —
            # parse the leg2 entry from the message and call
            # place_with_retry with the additional shares. Until then,
            # this is intentionally a no-op beyond logging.
            if WB_PYRAMID_ENABLED:
                print(f"[WB] {now_iso_et()} {sym} {res} (PYRAMID_ENABLED=1 but "
                      f"leg2 execution intentionally unwired during A/B parity "
                      f"period — matches Setup A behavior; see 2026-05-08 note)",
                      flush=True)
            else:
                print(f"[WB] {now_iso_et()} {sym} {res} (silent — leg2 not "
                      f"wired, matches Setup A)", flush=True)
        elif res.startswith("WB_DISARMED"):
            print(f"[WB] {now_iso_et()} {sym} {res}", flush=True)

    def on_bar(self, msg: BarMessage):
        sym = msg.symbol
        det = self._ensure_detector(sym)
        bar = bar_from_message(msg)
        try:
            res = det.on_bar_close_1m(bar, vwap=msg.vwap)
        except Exception as e:
            print(f"[WB] {now_iso_et()} {sym} detector bar error: {e!r}",
                  flush=True)
            return
        if res:
            print(f"[WB] {now_iso_et()} {sym} {res}", flush=True)

    def on_subscriptions(self, msg: SubscriptionsMessage):
        for sym in msg.watchlist:
            self._ensure_detector(sym)

    def on_disconnect(self):
        print(f"[WB] {now_iso_et()} engine socket closed — fail-CLOSED, no new "
              f"entries. Open positions: {len(self.positions)}", flush=True)

    # ── Entry placement ──────────────────────────────────────────────

    def _handle_entry(self, symbol: str, msg: str, det: WaveBreakoutDetector):
        """Parse `WB_ENTER: entry=X stop=Y score=Z wave_id=W` and place
        Alpaca order."""
        if not self.state.can_enter:
            print(f"[WB] {now_iso_et()} {symbol} REFUSE entry: stream paused / "
                  f"engine disconnected / fail-CLOSED", flush=True)
            det.mark_entry_failed("stream_paused")
            return
        if self.risk.kill_switch_active:
            print(f"[WB] {now_iso_et()} {symbol} REFUSE entry: daily risk kill "
                  f"(daily_pnl=${self.risk.daily_pnl:+,.2f})", flush=True)
            det.mark_entry_failed("daily_risk_kill")
            return
        if symbol in self.positions:
            print(f"[WB] {now_iso_et()} {symbol} REFUSE entry: already in position",
                  flush=True)
            det.mark_entry_failed("already_in_position")
            return
        if self._active_count() >= WB_MAX_CONCURRENT:
            print(f"[WB] {now_iso_et()} {symbol} REFUSE entry: portfolio cap "
                  f"({self._active_count()}/{WB_MAX_CONCURRENT})", flush=True)
            det.mark_entry_failed("portfolio_cap")
            return

        parts: dict[str, str] = {}
        for tok in msg.replace("WB_ENTER:", "").strip().split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                parts[k] = v
        try:
            entry = float(parts["entry"])
            stop = float(parts["stop"])
            score = int(parts.get("score", "7"))
        except (KeyError, ValueError) as e:
            print(f"[WB] {now_iso_et()} {symbol} ENTRY parse error: {e!r} "
                  f"msg={msg!r}", flush=True)
            det.mark_entry_failed(f"parse_error:{e}")
            return

        current_equity = self.starting_equity + self.risk.daily_pnl
        qty, risk_dollars = _compute_wb_position_size(entry, stop, current_equity)
        if qty <= 0:
            print(f"[WB] {now_iso_et()} {symbol} SKIP: qty<=0 (entry={entry:.4f} "
                  f"stop={stop:.4f} equity=${current_equity:,.0f})", flush=True)
            det.mark_entry_failed("size_zero")
            return

        notional = qty * entry
        print(f"[WB] {now_iso_et()} {symbol} ENTRY qty={qty} "
              f"ibkr_signal=${entry:.4f} stop=${stop:.4f} R=${entry-stop:.4f} "
              f"risk=${risk_dollars:.0f} notional=${notional:,.0f} "
              f"score={score}", flush=True)

        # Off-loop retry-with-reprice loop (see engine_bot_common.place_with_retry).
        def _await_fill():
            res = place_with_retry(
                self.broker, self.state, symbol, "BUY", qty,
                ibkr_signal_price=entry,
                log_prefix="WB",
                log_label="QUOTE_AWARE",
            )
            if res.fill_price is not None and res.filled_qty > 0:
                pos = _WBPosition(
                    symbol=symbol, qty=res.filled_qty,
                    entry=float(res.fill_price),
                    stop=stop, score=score, risk_dollars=risk_dollars,
                    entry_time=now_et(), order_id=res.last_order_id or "",
                    peak=float(res.fill_price),
                    fill_confirmed=True,
                )
                with self._positions_lock:
                    self.positions[symbol] = pos
                self.risk.daily_entries += 1
                # The WB detector needs to know the real fill so its
                # trailing-stop math anchors correctly.
                try:
                    det.mark_filled(float(res.fill_price),
                                    datetime.now(UTC), score=score)
                except Exception as e:
                    print(f"[WB] {now_iso_et()} {symbol} mark_filled error: {e!r}",
                          flush=True)
                retry_tag = f" (after {res.attempts} retries)" if res.attempts > 0 else ""
                print(f"[WB] {now_iso_et()} {symbol} FILL @ "
                      f"${res.fill_price:.4f} qty={res.filled_qty}{retry_tag}",
                      flush=True)
            else:
                # place_with_retry already logged the specific timeout
                # reason (max retries vs chase-cap exceeded).
                det.mark_entry_failed("fill_timeout")

        threading.Thread(target=_await_fill, daemon=True,
                         name=f"wb-fill-{symbol}").start()

    # ── Exit handling ────────────────────────────────────────────────

    def _handle_exit(self, symbol: str, msg: str):
        """Detector emitted WB_EXIT. Place SELL LIMIT with retry-and-reprice,
        book P&L when filled. Mirrors squeeze_bot's exit retry pattern."""
        with self._positions_lock:
            pos = self.positions.get(symbol)
            if pos is None:
                return
            if pos.exit_in_flight:
                # Already trying to exit — let the in-flight loop finish.
                return
            pos.exit_in_flight = True
        parts = {}
        for tok in msg.replace("WB_EXIT:", "").strip().split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                parts[k] = v
        reason = parts.get("reason", "unknown")
        try:
            exit_signal_price = float(parts.get("exit", "0"))
        except ValueError:
            exit_signal_price = 0.0
        ref = exit_signal_price if exit_signal_price > 0 else pos.peak
        print(f"[WB] {now_iso_et()} {symbol} EXIT submitting reason={reason} "
              f"qty={pos.qty} ref=${ref:.4f}", flush=True)

        det = self.detectors.get(symbol)

        def _await_exit_fill():
            res = place_with_retry(
                self.broker, self.state, symbol, "SELL", pos.qty,
                ibkr_signal_price=ref,
                log_prefix="WB",
                log_label="QUOTE_AWARE",
            )
            if res.fill_price is not None and res.filled_qty > 0:
                pnl = (res.fill_price - pos.entry) * res.filled_qty
                self.risk.record_close(pnl)
                with self._positions_lock:
                    self.positions.pop(symbol, None)
                if det is not None:
                    try:
                        det.mark_exited(float(res.fill_price), reason=reason)
                    except Exception:
                        pass
                retry_tag = f" (after {res.attempts} retries)" if res.attempts > 0 else ""
                print(f"[WB] {now_iso_et()} {symbol} CLOSED @ "
                      f"${res.fill_price:.4f} pnl=${pnl:+,.2f} reason={reason} "
                      f"daily_pnl=${self.risk.daily_pnl:+,.2f}{retry_tag}",
                      flush=True)
            else:
                # All retries exhausted or chase cap hit — clear the
                # in-flight flag so the next WB_EXIT can spin up a new
                # cycle. No market fallback (project rule).
                with self._positions_lock:
                    live = self.positions.get(symbol)
                    if live is not None:
                        live.exit_in_flight = False
                print(f"[WB] {now_iso_et()} {symbol} EXIT TIMEOUT — position "
                      f"still open", flush=True)

        threading.Thread(target=_await_exit_fill, daemon=True,
                         name=f"wb-exit-{symbol}").start()

    # ── Main loop ─────────────────────────────────────────────────────

    def run(self):
        sock = connect_to_engine(self.bot_id, timeout=30.0)
        self.state.connected = True
        self.state.stream_paused = True
        print(f"[WB] {now_iso_et()} connected to engine — fail-CLOSED until "
              f"first healthy heartbeat", flush=True)

        t = threading.Thread(
            target=engine_reader_thread,
            args=(sock, self.state, self.on_tick, self.on_bar,
                  self.on_subscriptions, self.on_disconnect),
            name="engine-reader", daemon=True,
        )
        t.start()

        def _hb_watcher():
            while not self._shutdown.is_set():
                if (self.state.connected and self.state.ibkr_connected
                        and self.state.last_heartbeat_ts is not None):
                    if self.state.stream_paused:
                        self.state.stream_paused = False
                        print(f"[WB] {now_iso_et()} stream healthy — "
                              f"entries unlocked", flush=True)
                time.sleep(0.5)
        threading.Thread(target=_hb_watcher, daemon=True,
                         name="hb-watcher").start()

        self._shutdown.wait()
        try:
            sock.close()
        except Exception:
            pass
        print(f"[WB] {now_iso_et()} shutdown complete "
              f"(daily_pnl=${self.risk.daily_pnl:+,.2f}, "
              f"open_positions={len(self.positions)})", flush=True)

    def request_shutdown(self):
        self._shutdown.set()


def main():
    bot = WBBot()
    def _sig(*_):
        print(f"[WB] {now_iso_et()} signal received — shutting down", flush=True)
        bot.request_shutdown()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    bot.run()


if __name__ == "__main__":
    main()
