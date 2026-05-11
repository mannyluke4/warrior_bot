"""squeeze_bot.py — thin Setup B strategy bot for squeeze entries.

Consumes ticks + bars from data_engine.py over the Unix socket and
runs the SqueezeDetector per symbol. On entry signals it places orders
through Alpaca against the THIRD paper account (PA-NEW credentials in
.env.engine).

Does NOT:
  - Connect to IBKR (engine owns the connection)
  - Manage subscriptions / watchlist (engine drives that via IPC)
  - Write to tick_cache_*/  (engine writes tick_cache_engine/)
  - Run a watchdog
  - Implement TBT promotion / demotion

Per directive section "Failure Modes": fail-CLOSED on stream_paused or
socket disconnect — refuse new entries, continue managing existing
positions only.
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

# Make the worktree root importable (so `from squeeze_detector import ...`
# works regardless of cwd).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from engine_bot_common import (
    DailyRisk,
    EngineState,
    bar_from_message,
    connect_to_engine,
    engine_reader_thread,
    make_alpaca_broker,
    now_et,
    now_iso_et,
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
from squeeze_detector import SqueezeDetector


# ══════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════

SQ_ENABLED = os.getenv("WB_SQUEEZE_ENABLED", "1") == "1"
MIN_R = float(os.getenv("WB_MIN_R", "0.06"))
RISK_PCT = float(os.getenv("WB_RISK_PCT", "0.035"))
MAX_NOTIONAL = float(os.getenv("WB_MAX_NOTIONAL", "50000"))
MAX_SHARES = int(os.getenv("WB_MAX_SHARES", "100000"))
ENTRY_SLIPPAGE_MIN = float(os.getenv("WB_ENTRY_SLIPPAGE_MIN", "0.05"))
ENTRY_SLIPPAGE_PCT = float(os.getenv("WB_ENTRY_SLIPPAGE_PCT", "0.005"))
ENTRY_RETRY_TIMEOUT_SEC = int(os.getenv("WB_ENTRY_RETRY_TIMEOUT_SEC", "10"))


# ══════════════════════════════════════════════════════════════════════
# Per-symbol state
# ══════════════════════════════════════════════════════════════════════


@dataclass
class _Position:
    symbol: str
    qty: int
    entry: float
    stop: float
    r: float
    score: float
    entry_time: datetime
    order_id: str
    peak: float
    setup_type: str = "squeeze"


# ══════════════════════════════════════════════════════════════════════
# Bot
# ══════════════════════════════════════════════════════════════════════


class SqueezeBot:
    def __init__(self):
        if not SQ_ENABLED:
            raise SystemExit("WB_SQUEEZE_ENABLED=0 — refusing to start.")
        self.bot_id = "squeeze_bot"
        self.broker = make_alpaca_broker()
        self.starting_equity = starting_equity_from_broker(self.broker)
        self.risk = DailyRisk(self.starting_equity)
        print(f"[SQUEEZE] {now_iso_et()} starting equity ${self.starting_equity:,.0f} "
              f"(third Alpaca paper account)", flush=True)
        self.state = EngineState()
        self.detectors: dict[str, SqueezeDetector] = {}
        self.positions: dict[str, _Position] = {}
        self._positions_lock = threading.Lock()
        self._shutdown = threading.Event()

    def _ensure_detector(self, symbol: str) -> SqueezeDetector:
        d = self.detectors.get(symbol)
        if d is None:
            d = SqueezeDetector()
            d.symbol = symbol
            self.detectors[symbol] = d
        return d

    # ── Event handlers ────────────────────────────────────────────────

    def on_tick(self, msg: TickMessage):
        sym = msg.symbol
        det = self._ensure_detector(sym)
        # Tick path — detector returns "ENTRY SIGNAL ..." when an armed
        # squeeze trigger fires.
        try:
            sig = det.on_trade_price(msg.price)
        except Exception as e:
            print(f"[SQUEEZE] {now_iso_et()} {sym} detector tick error: {e!r}",
                  flush=True)
            return
        # Manage open position exits on every tick (price comparison).
        self._tick_manage_exit(sym, msg.price)
        if not sig:
            return
        if "SQ_SEED_GATE" in sig:
            # Detector internally suppressed — log + move on.
            print(f"[SQUEEZE] {now_iso_et()} {sym} {sig}", flush=True)
            return
        if "ENTRY SIGNAL" in sig:
            # det.on_trade_price already cleared `armed`; the signal
            # message text carries stop/R/score, and entry == this tick.
            self._handle_entry_signal(sym, sig, msg.price, det)

    def on_bar(self, msg: BarMessage):
        sym = msg.symbol
        det = self._ensure_detector(sym)
        bar = bar_from_message(msg)
        try:
            res = det.on_bar_close_1m(bar, vwap=msg.vwap)
        except Exception as e:
            print(f"[SQUEEZE] {now_iso_et()} {sym} detector bar error: {e!r}",
                  flush=True)
            return
        if res:
            print(f"[SQUEEZE] {now_iso_et()} {sym} {res}", flush=True)

    def on_subscriptions(self, msg: SubscriptionsMessage):
        # Pre-warm detectors for new symbols (instantiates state). The
        # detector itself is cheap to construct; ensures the first tick
        # has a detector ready.
        for sym in msg.watchlist:
            self._ensure_detector(sym)

    def on_disconnect(self):
        print(f"[SQUEEZE] {now_iso_et()} engine socket closed — fail-CLOSED, "
              f"no new entries. Open positions: {len(self.positions)} "
              f"(continuing to manage via cached last-tick prices when they arrive — "
              f"none will arrive until engine reconnects). "
              f"Manual intervention required to flatten if engine stays down.",
              flush=True)
        # Don't kill the bot — keep positions tracked. Manual operator
        # decides whether to relaunch after engine comes back.

    # ── Entry placement ──────────────────────────────────────────────

    def _handle_entry_signal(self, symbol: str, sig: str, price: float,
                              det: SqueezeDetector):
        """Parse the ENTRY SIGNAL message + place the Alpaca order. We
        rebuild the entry/stop/R/score from the detector's last armed
        state stamped into the message text — same parse Setup A's
        check_triggers does."""
        # Fail-CLOSED guard.
        if not self.state.can_enter:
            print(f"[SQUEEZE] {now_iso_et()} {symbol} REFUSE entry: stream paused / "
                  f"engine disconnected / fail-CLOSED active", flush=True)
            return
        if self.risk.kill_switch_active:
            print(f"[SQUEEZE] {now_iso_et()} {symbol} REFUSE entry: daily risk kill "
                  f"(daily_pnl=${self.risk.daily_pnl:+,.2f} "
                  f"consec_losses={self.risk.consecutive_losses})", flush=True)
            return
        if symbol in self.positions:
            print(f"[SQUEEZE] {now_iso_et()} {symbol} REFUSE entry: already in position",
                  flush=True)
            return

        # Parse the detector signal message. Setup A's signal text is:
        #   "ENTRY SIGNAL @ {entry:.4f} (break {trigger:.4f}) "
        #   "stop={stop:.4f} R={r:.4f} score={score:.1f} setup_type=squeeze why=..."
        parts: dict[str, str] = {}
        for tok in sig.split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                parts[k] = v
        try:
            stop = float(parts["stop"])
            r = float(parts["R"])
            score = float(parts.get("score", "0"))
        except (KeyError, ValueError) as e:
            print(f"[SQUEEZE] {now_iso_et()} {symbol} ENTRY parse error: {e!r} "
                  f"sig={sig!r}", flush=True)
            return
        # Use the trigger tick price as the entry reference (Setup A's
        # enter_trade uses armed.trigger_high; on the bot side we only
        # see the message text — the trigger tick price is equivalent
        # since the detector cleared `armed` on this exact tick).
        entry = float(price)

        if r <= 0 or r < MIN_R:
            print(f"[SQUEEZE] {now_iso_et()} {symbol} SKIP: R={r:.4f} < min {MIN_R}",
                  flush=True)
            return

        # Dynamic risk sizing (mirrors Setup A's enter_trade).
        current_equity = self.starting_equity + self.risk.daily_pnl
        risk_dollars = max(50.0, current_equity * RISK_PCT)
        qty = int(math.floor(risk_dollars / r))
        qty_notional = int(math.floor(MAX_NOTIONAL / max(entry, 0.01)))
        qty = min(qty, qty_notional, MAX_SHARES)
        if qty <= 0:
            print(f"[SQUEEZE] {now_iso_et()} {symbol} SKIP: qty<=0 (equity "
                  f"${current_equity:,.0f}, risk ${risk_dollars:.0f})", flush=True)
            return

        slippage = max(ENTRY_SLIPPAGE_MIN, entry * ENTRY_SLIPPAGE_PCT)
        limit_price = round(entry + slippage, 2)
        notional = qty * entry
        print(f"[SQUEEZE] {now_iso_et()} {symbol} ENTRY qty={qty} limit=${limit_price:.2f} "
              f"stop=${stop:.4f} R=${r:.4f} risk=${risk_dollars:.0f} "
              f"notional=${notional:,.0f} score={score:.1f}", flush=True)

        try:
            order = self.broker.submit_limit(
                symbol, qty, "BUY", limit_price, extended_hours=True,
            )
        except Exception as e:
            print(f"[SQUEEZE] {now_iso_et()} {symbol} BROKER REJECT: {e!r}",
                  flush=True)
            return

        # Off-loop wait for fill so the tick handler keeps draining.
        def _await_fill():
            fill_price, filled_qty = wait_for_fill(
                self.broker, order.order_id, timeout=ENTRY_RETRY_TIMEOUT_SEC,
            )
            if filled_qty > 0 and fill_price is not None:
                pos = _Position(
                    symbol=symbol, qty=filled_qty, entry=float(fill_price),
                    stop=stop, r=r, score=score,
                    entry_time=now_et(), order_id=order.order_id,
                    peak=float(fill_price),
                )
                with self._positions_lock:
                    self.positions[symbol] = pos
                self.risk.daily_entries += 1
                det.notify_trade_opened()
                print(f"[SQUEEZE] {now_iso_et()} {symbol} FILL @ ${fill_price:.4f} "
                      f"qty={filled_qty}", flush=True)
            else:
                print(f"[SQUEEZE] {now_iso_et()} {symbol} ENTRY TIMEOUT — "
                      f"no fill in {ENTRY_RETRY_TIMEOUT_SEC}s, cancelled",
                      flush=True)

        threading.Thread(target=_await_fill, daemon=True,
                         name=f"squeeze-fill-{symbol}").start()

    # ── Exit management ──────────────────────────────────────────────

    def _tick_manage_exit(self, symbol: str, price: float):
        """Mirror Setup A's manage_exit at a high level: stop loss + 2R
        target. Simpler than the full Setup A ladder because the engine
        bot is intentionally minimal during A/B — once we win the A/B
        we'll expand. For now, hit stop = exit-at-limit at stop, hit
        target = exit-at-limit at target. Both via SELL LIMIT (no market
        orders per project rule).
        """
        with self._positions_lock:
            pos = self.positions.get(symbol)
            if pos is None:
                return
            if price > pos.peak:
                pos.peak = price
            # Stop hit?
            if price <= pos.stop:
                self._submit_exit(pos, price, reason="sq_stop_hit")
                return
            # Target (1.5R per X01 config)
            target_r = float(os.getenv("WB_SQ_TARGET_R", "1.5"))
            target_px = pos.entry + target_r * pos.r
            if price >= target_px and pos.qty > 0:
                self._submit_exit(pos, price, reason="sq_target_hit")
                return

    def _submit_exit(self, pos: _Position, price: float, reason: str):
        """SELL LIMIT exit. Limit set slightly below ref price so the
        order takes the bid in a falling tape but doesn't sit forever."""
        # Use a small wiggle: $0.03 below ref for normal targets, 3%
        # below ref for stop-hit urgency. Same convention as Setup A.
        if reason in ("sq_stop_hit", "sq_max_loss_hit"):
            limit_price = round(price * 0.97, 2)
        else:
            limit_price = round(price - 0.03, 2)
        try:
            order = self.broker.submit_limit(
                pos.symbol, pos.qty, "SELL", limit_price, extended_hours=True,
            )
        except Exception as e:
            print(f"[SQUEEZE] {now_iso_et()} {pos.symbol} EXIT REJECT: {e!r}",
                  flush=True)
            return
        print(f"[SQUEEZE] {now_iso_et()} {pos.symbol} EXIT submitted "
              f"reason={reason} qty={pos.qty} limit=${limit_price:.2f}",
              flush=True)

        # Off-loop fill wait + book the P&L.
        symbol = pos.symbol

        def _await_exit_fill():
            fill_price, filled_qty = wait_for_fill(
                self.broker, order.order_id, timeout=15,
            )
            if filled_qty > 0 and fill_price is not None:
                pnl = (fill_price - pos.entry) * filled_qty
                self.risk.record_close(pnl)
                with self._positions_lock:
                    self.positions.pop(symbol, None)
                det = self.detectors.get(symbol)
                if det is not None:
                    try:
                        det.notify_trade_closed(symbol, pnl,
                                                r_mult=(pnl / (pos.qty * pos.r))
                                                if pos.r > 0 and pos.qty > 0 else 0.0)
                    except Exception:
                        pass
                print(f"[SQUEEZE] {now_iso_et()} {symbol} CLOSED @ "
                      f"${fill_price:.4f} pnl=${pnl:+,.2f} reason={reason} "
                      f"daily_pnl=${self.risk.daily_pnl:+,.2f}", flush=True)
            else:
                # Exit didn't fill — leave the position in books and try
                # again on the next adverse tick. No fallback to market
                # (project rule).
                print(f"[SQUEEZE] {now_iso_et()} {symbol} EXIT TIMEOUT — "
                      f"position still open, will retry on next adverse tick",
                      flush=True)

        threading.Thread(target=_await_exit_fill, daemon=True,
                         name=f"squeeze-exit-{symbol}").start()

    # ── Main loop ─────────────────────────────────────────────────────

    def run(self):
        sock = connect_to_engine(self.bot_id, timeout=30.0)
        self.state.connected = True
        self.state.stream_paused = True  # cleared on first heartbeat with ibkr_connected=True
        print(f"[SQUEEZE] {now_iso_et()} connected to engine — fail-CLOSED until "
              f"first healthy heartbeat", flush=True)

        # Reader thread.
        t = threading.Thread(
            target=engine_reader_thread,
            args=(sock, self.state, self.on_tick, self.on_bar,
                  self.on_subscriptions, self.on_disconnect),
            name="engine-reader", daemon=True,
        )
        t.start()

        # Promote out of stream_paused once we see a healthy heartbeat.
        def _hb_watcher():
            while not self._shutdown.is_set():
                if (self.state.connected and self.state.ibkr_connected
                        and self.state.last_heartbeat_ts is not None):
                    if self.state.stream_paused:
                        self.state.stream_paused = False
                        print(f"[SQUEEZE] {now_iso_et()} stream healthy — "
                              f"entries unlocked", flush=True)
                time.sleep(0.5)
        threading.Thread(target=_hb_watcher, daemon=True,
                         name="hb-watcher").start()

        # Block on shutdown signal.
        self._shutdown.wait()
        try:
            sock.close()
        except Exception:
            pass
        print(f"[SQUEEZE] {now_iso_et()} shutdown complete "
              f"(daily_pnl=${self.risk.daily_pnl:+,.2f}, "
              f"open_positions={len(self.positions)})", flush=True)

    def request_shutdown(self):
        self._shutdown.set()


def main():
    bot = SqueezeBot()
    def _sig(*_):
        print(f"[SQUEEZE] {now_iso_et()} signal received — shutting down",
              flush=True)
        bot.request_shutdown()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    bot.run()


if __name__ == "__main__":
    main()
