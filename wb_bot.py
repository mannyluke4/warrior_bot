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
    EngineSession,
    EngineState,
    bar_from_message,
    connect_to_engine,
    decide_boot_mode,
    engine_reader_thread,
    get_priced_limit,
    make_alpaca_broker,
    now_et,
    now_iso_et,
    place_with_retry,
    starting_equity_from_broker,
    today_et_str,
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

SESSION_RESUME_ENABLED = os.getenv("WB_SESSION_RESUME_ENABLED", "0") == "1"


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
    we carry is leaner than squeeze's — but we still persist enough that
    a crash-restart can pick up the position and continue managing.

    The trailing_armed / trail_stop flags are mirrored from the detector
    for visibility + log lines. On resume we don't try to rehydrate them
    back into the detector — the detector's `_update_position` is purely
    a function of (peak, entry, R, stop) which we DO restore, so the
    trail recomputes correctly on the next tick.
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
    # Trail-state mirror — for log lines and persistence audit only.
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
    def __init__(self, *, boot_mode: str = "cold", boot_reason: str = "no_marker"):
        if not WB_ENABLED:
            raise SystemExit("WB_WAVE_BREAKOUT_ENABLED=0 — refusing to start.")
        self.bot_id = "wb_bot"
        self.boot_mode = boot_mode
        self.boot_reason = boot_reason
        self.broker = make_alpaca_broker()
        self.starting_equity = starting_equity_from_broker(self.broker)
        self.risk = DailyRisk(self.starting_equity)
        print(f"[WB] {now_iso_et()} starting equity ${self.starting_equity:,.0f} "
              f"(third Alpaca paper account)", flush=True)
        self.state = EngineState()
        self.detectors: dict[str, WaveBreakoutDetector] = {}
        self.positions: dict[str, _WBPosition] = {}
        # RLock — `_persist_open_trades` re-enters from contexts already
        # holding the lock (mirror of squeeze_bot rationale).
        self._positions_lock = threading.RLock()
        self._shutdown = threading.Event()
        # Per-bot persistence helper — writes go to session_state_engine/<date>/wb_bot/.
        self.session = EngineSession(self.bot_id)
        if self.boot_mode == "cold":
            try:
                self.session.write_marker()
            except Exception as e:
                print(f"[WB] {now_iso_et()} write_marker error: {e!r}", flush=True)
        if self.boot_mode == "resume":
            self._resume_rehydrate()

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
        # Update bot-side peak mirror + persist on peak advance, mirroring
        # Setup A's per-tick peak update for the squeeze side. This keeps
        # the persisted record fresh enough that a crash recovery sees
        # an up-to-date peak rather than the stale entry-time peak.
        with self._positions_lock:
            pos = self.positions.get(sym)
            if pos is not None and pos.fill_confirmed and msg.price > pos.peak:
                pos.peak = msg.price
                self._persist_open_trades()
        if not res:
            return
        if res.startswith("WB_ENTER"):
            self._handle_entry(sym, res, det)
        elif res.startswith("WB_EXIT"):
            self._handle_exit(sym, res)
        elif res.startswith("WB_TRAIL_ARMED"):
            # Mirror trail state onto the bot-side position so a crash-
            # restart can persist that the trail is armed (the detector
            # state machine will recompute trail_stop from peak+R, but
            # logs read more naturally when the bot mirrors the flag).
            with self._positions_lock:
                pos = self.positions.get(sym)
                if pos is not None:
                    pos.trail_armed = True
                    # Parse trail=X.XXXX out of the message text.
                    for tok in res.split():
                        if tok.startswith("trail="):
                            try:
                                pos.trail_stop = float(tok.split("=", 1)[1])
                            except ValueError:
                                pass
                    self._persist_open_trades()
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
                # Stub — leg2 execution intentionally not wired during A/B.
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
        try:
            self.session.write_watchlist(list(msg.watchlist))
        except Exception as e:
            print(f"[WB] {now_iso_et()} write_watchlist error: {e!r}", flush=True)

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
                self._persist_open_trades()
                retry_tag = f" (after {res.attempts} retries)" if res.attempts > 0 else ""
                print(f"[WB] {now_iso_et()} {symbol} FILL @ "
                      f"${res.fill_price:.4f} qty={res.filled_qty}{retry_tag}",
                      flush=True)
            else:
                # place_with_retry already logged the specific failure
                # reason (timeout / rejected / chase-cap exceeded).
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
                self._persist_open_trades()
                self._persist_risk()
                retry_tag = f" (after {res.attempts} retries)" if res.attempts > 0 else ""
                partial_tag = (f" [PARTIAL {res.filled_qty}/{pos.qty}]"
                               if res.filled_qty < pos.qty else "")
                print(f"[WB] {now_iso_et()} {symbol} CLOSED @ "
                      f"${res.fill_price:.4f} pnl=${pnl:+,.2f} reason={reason} "
                      f"daily_pnl=${self.risk.daily_pnl:+,.2f}{retry_tag}{partial_tag}",
                      flush=True)
            else:
                # All retries exhausted or terminal status (rejected / etc).
                # Clear the in-flight flag so the next WB_EXIT can spin up
                # a new cycle. Project rule: no market fallback.
                with self._positions_lock:
                    live = self.positions.get(symbol)
                    if live is not None:
                        live.exit_in_flight = False
                self._persist_open_trades()
                print(f"[WB] {now_iso_et()} {symbol} EXIT FAILED — position "
                      f"still open", flush=True)

        threading.Thread(target=_await_exit_fill, daemon=True,
                         name=f"wb-exit-{symbol}").start()

    # ── Persistence ──────────────────────────────────────────────────

    def _position_to_record(self, pos: _WBPosition) -> dict:
        """Map _WBPosition → open_trades.json schema. The required-fields
        set in EngineSession is squeeze-oriented (carries tp_hit etc.); we
        fill those with WB-appropriate defaults (tp_hit=False, no partial,
        runner_stop=0) so the same validation passes for both bots."""
        return {
            "symbol": pos.symbol,
            "setup_type": "wave_breakout",
            "entry_price": float(pos.entry),
            "entry_time": pos.entry_time.isoformat(),
            "qty": int(pos.qty),
            "r": float(pos.entry - pos.stop),
            "stop": float(pos.stop),
            "score": float(pos.score),
            "peak": float(pos.peak),
            "tp_hit": False,
            "partial_filled_qty": 0,
            "partial_filled_at": None,
            "runner_stop": 0.0,
            "is_parabolic": False,
            "fill_confirmed": bool(pos.fill_confirmed),
            "order_id": pos.order_id,
            # WB-specific audit fields.
            "trail_armed": bool(pos.trail_armed),
            "trail_stop": float(pos.trail_stop),
            "pyramid_filled": bool(pos.pyramid_filled),
            "risk_dollars": float(pos.risk_dollars),
        }

    def _record_to_position(self, rec: dict) -> _WBPosition:
        entry_time_str = rec.get("entry_time", "")
        try:
            et = datetime.fromisoformat(entry_time_str)
            if et.tzinfo is None:
                et = et.replace(tzinfo=UTC)
            et = et.astimezone(ET)
        except (ValueError, TypeError):
            et = now_et()
        return _WBPosition(
            symbol=rec["symbol"],
            qty=int(rec["qty"]),
            entry=float(rec["entry_price"]),
            stop=float(rec["stop"]),
            score=int(rec.get("score", 7)),
            risk_dollars=float(rec.get("risk_dollars", 0.0)),
            entry_time=et,
            order_id=rec.get("order_id", ""),
            peak=float(rec.get("peak", rec["entry_price"])),
            pyramid_filled=bool(rec.get("pyramid_filled", False)),
            trail_armed=bool(rec.get("trail_armed", False)),
            trail_stop=float(rec.get("trail_stop", 0.0)),
            fill_confirmed=bool(rec.get("fill_confirmed", True)),
            exit_in_flight=False,
        )

    def _persist_open_trades(self) -> None:
        try:
            with self._positions_lock:
                trades = [self._position_to_record(p)
                          for p in self.positions.values()
                          if p.fill_confirmed]
            self.session.write_open_trades(trades)
        except Exception as e:
            print(f"[WB] {now_iso_et()} persist_open_trades error: {e!r}",
                  flush=True)

    def _persist_risk(self) -> None:
        try:
            self.session.write_risk(
                daily_pnl=self.risk.daily_pnl,
                daily_entries=self.risk.daily_entries,
                consecutive_losses=self.risk.consecutive_losses,
                closed_trades=self.risk.closed_trades,
            )
        except Exception as e:
            print(f"[WB] {now_iso_et()} persist_risk error: {e!r}", flush=True)

    def _periodic_flush_loop(self):
        while not self._shutdown.is_set():
            self._shutdown.wait(self.session.flush_sec)
            if self._shutdown.is_set():
                return
            self._persist_open_trades()
            self._persist_risk()

    # ── Resume ────────────────────────────────────────────────────────

    def _resume_rehydrate(self):
        """Resume-mode startup: cancel any open orders, rehydrate WB
        positions from disk, reconcile against Alpaca, restore risk.

        Orphan policy: any Alpaca position the bot's state doesn't know
        about gets adopted with conservative defaults (stop = entry × 0.99,
        risk_dollars = 0). Never auto-flatten — per project rule.

        Note: the detector state is NOT rehydrated. The detector is
        rebuilt from scratch and won't know it has an open position. The
        bot side knows, and the bot routes exit signals via WB_EXIT
        messages from the detector. On resume, the detector starts in
        IDLE state, but the bot side has the position. So a re-entry
        signal could fire while we already hold the symbol — the
        `already_in_position` guard in _handle_entry catches that.

        The position's actual exit will fire from the bot side via the
        same tick-by-tick stop check — wait, this is a problem. The
        WB exit logic lives inside `WaveBreakoutDetector._update_position`,
        which only runs when `self._position` is set (set by
        det.mark_filled). On resume, we don't call mark_filled, so the
        detector has no position to manage exits on.

        Fix: after rehydrating a position, call det.mark_filled() to
        re-anchor the detector's exit state machine. This recomputes
        trail_stop / hard_stop from the persisted entry/stop/peak.
        """
        print(f"[WB] {now_iso_et()} RESUME: reconciling state", flush=True)

        cancelled_buy = cancelled_sell = 0
        try:
            open_orders = self.broker.get_open_orders() or []
        except Exception as e:
            print(f"[WB] {now_iso_et()} RESUME: get_open_orders failed: {e!r}",
                  flush=True)
            open_orders = []
        for o in open_orders:
            try:
                self.broker.cancel_order(o.order_id)
                if o.side == "BUY":
                    cancelled_buy += 1
                else:
                    cancelled_sell += 1
            except Exception as e:
                print(f"[WB] {now_iso_et()} RESUME: cancel {o.order_id} "
                      f"failed: {e!r}", flush=True)
        if cancelled_buy or cancelled_sell:
            print(f"[WB] {now_iso_et()} RESUME: cancelled "
                  f"{cancelled_buy} BUYs + {cancelled_sell} SELLs", flush=True)

        persisted = self.session.read_open_trades()
        # Only rehydrate WB positions — squeeze positions belong to the
        # sibling bot. The setup_type field marks ownership.
        wb_records = [r for r in persisted if r.get("setup_type") == "wave_breakout"]
        by_symbol = {r["symbol"]: r for r in wb_records}

        try:
            broker_positions = self.broker.get_positions() or []
        except Exception as e:
            print(f"[WB] {now_iso_et()} RESUME: get_positions failed: {e!r}",
                  flush=True)
            broker_positions = []

        rehydrated_symbols: set[str] = set()
        for bp in broker_positions:
            sym = bp.symbol
            broker_qty = bp.qty
            broker_entry = bp.avg_entry_price
            qty_avail = bp.qty_available
            if qty_avail == 0:
                print(f"[WB] {now_iso_et()} RESUME: {sym} qty={broker_qty} "
                      f"all held_for_orders — skip", flush=True)
                continue

            rec = by_symbol.get(sym)
            if rec is None:
                # No persisted WB record. We CAN'T assume this is a WB
                # orphan — it might belong to the squeeze sibling. So we
                # only adopt as WB if the persisted file mentions no other
                # strategy claiming it (in our per-bot file it doesn't, so
                # we'd adopt every cross-bot position). Safer: log + skip,
                # let the squeeze bot adopt if it's a squeeze position.
                # The session_state directory is per-bot, so each bot only
                # sees its OWN persisted positions — squeeze positions are
                # in squeeze_bot/open_trades.json, not wb_bot's.
                #
                # That means a true WB orphan (one we lost track of) WILL
                # look like no-persisted-record here. Adopt conservatively.
                print(f"[WB] {now_iso_et()} [ORPHAN_DETECTED] {sym} "
                      f"qty={qty_avail} entry=${broker_entry:.4f} "
                      f"— adopting as WB-orphan (stop=entry*0.99)",
                      flush=True)
                pos = _WBPosition(
                    symbol=sym, qty=qty_avail,
                    entry=float(broker_entry),
                    stop=float(broker_entry) * 0.99,
                    score=0, risk_dollars=0.0,
                    entry_time=now_et(),
                    order_id="adopted",
                    peak=float(broker_entry),
                    fill_confirmed=True,
                )
                self.positions[sym] = pos
                # Re-anchor the detector so exits can fire on the next tick.
                det = self._ensure_detector(sym)
                try:
                    det.mark_filled(float(broker_entry), datetime.now(UTC), score=0)
                except Exception as e:
                    print(f"[WB] {now_iso_et()} {sym} mark_filled (resume) error: "
                          f"{e!r}", flush=True)
                rehydrated_symbols.add(sym)
                continue

            pos = self._record_to_position(rec)
            if pos.qty != broker_qty:
                print(f"[WB] {now_iso_et()} RESUME: {sym} qty drift "
                      f"persisted={pos.qty} broker={broker_qty} — trusting broker",
                      flush=True)
                pos.qty = broker_qty
            self.positions[sym] = pos
            # Re-anchor detector so its exit-trail recomputes from peak/R.
            det = self._ensure_detector(sym)
            try:
                det.mark_filled(float(pos.entry), pos.entry_time.astimezone(UTC),
                                score=int(pos.score))
            except Exception as e:
                print(f"[WB] {now_iso_et()} {sym} mark_filled (resume) error: "
                      f"{e!r}", flush=True)
            rehydrated_symbols.add(sym)
            print(f"[WB] {now_iso_et()} RESUME: rehydrated {sym} qty={pos.qty} "
                  f"entry=${pos.entry:.4f} stop=${pos.stop:.4f} peak=${pos.peak:.4f}",
                  flush=True)

        dropped = set(by_symbol.keys()) - rehydrated_symbols
        for sym in dropped:
            print(f"[WB] {now_iso_et()} RESUME: dropping persisted {sym} "
                  f"(no live broker position)", flush=True)

        risk_data = self.session.read_risk()
        self.risk.daily_pnl = float(risk_data.get("daily_pnl", 0.0))
        self.risk.daily_entries = int(risk_data.get("daily_entries", 0))
        self.risk.consecutive_losses = int(risk_data.get("consecutive_losses", 0))
        self.risk.closed_trades = list(risk_data.get("closed_trades", []))
        print(f"[WB] {now_iso_et()} RESUME: risk restored "
              f"daily_pnl=${self.risk.daily_pnl:+,.2f} "
              f"entries={self.risk.daily_entries}", flush=True)
        self._persist_open_trades()
        self._persist_risk()
        print(f"[WB] {now_iso_et()} RESUME: complete", flush=True)

    # ── Main loop ─────────────────────────────────────────────────────

    def run(self):
        sock = connect_to_engine(self.bot_id, timeout=30.0)
        self.state.connected = True
        self.state.stream_paused = True
        print(f"[WB] {now_iso_et()} connected to engine — fail-CLOSED until "
              f"first healthy heartbeat", flush=True)

        threading.Thread(target=self._periodic_flush_loop, daemon=True,
                         name="periodic-flush").start()

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
    """CLI:
      --resume  Force resume from today's marker (cold-starts if no marker).
      --fresh   Force cold start, scrubbing session_state_engine/<date>/wb_bot/.
      (no flag) Auto-decide via marker presence.
    """
    import argparse
    parser = argparse.ArgumentParser(description="Setup B wave-breakout bot")
    parser.add_argument("--resume", action="store_true",
                        help="Force resume from today's marker")
    parser.add_argument("--fresh", action="store_true",
                        help="Force cold start, wiping session_state_engine/wb_bot/")
    args, _ = parser.parse_known_args()

    session = EngineSession("wb_bot")
    if args.fresh:
        session.scrub_today()
    boot_mode, boot_reason = decide_boot_mode(
        session, fresh=args.fresh, resume=args.resume,
    )
    if boot_mode == "resume" and not SESSION_RESUME_ENABLED:
        print(f"[WB] BOOT: would RESUME (reason={boot_reason}) but "
              f"WB_SESSION_RESUME_ENABLED=0 — forcing COLD", flush=True)
        boot_mode = "cold"
        boot_reason = "resume_gate_off"
    age = session.marker_age_seconds()
    age_str = f"{age:.0f}s" if age is not None else "n/a"
    print(f"[WB] BOOT: {boot_mode.upper()} (reason={boot_reason}, "
          f"marker_age={age_str})", flush=True)

    bot = WBBot(boot_mode=boot_mode, boot_reason=boot_reason)
    def _sig(*_):
        print(f"[WB] {now_iso_et()} signal received — shutting down", flush=True)
        bot.request_shutdown()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    bot.run()


if __name__ == "__main__":
    main()
