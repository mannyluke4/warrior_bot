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

# ── Squeeze exit-ladder config (mirrors Setup A's bot_v3_hybrid.py knobs)
# These are read with the SAME defaults as Setup A's .env so that on a
# squeeze-only A/B against identical fills, the engine bot makes byte-
# identical exit decisions. Every default below matches Setup A's .env.
SQ_TARGET_R = float(os.getenv("WB_SQ_TARGET_R", "1.5"))
SQ_TRAIL_R = float(os.getenv("WB_SQ_TRAIL_R", "1.5"))
SQ_PARA_TRAIL_R = float(os.getenv("WB_SQ_PARA_TRAIL_R", "1.0"))
SQ_RUNNER_TRAIL_R = float(os.getenv("WB_SQ_RUNNER_TRAIL_R", "2.5"))
SQ_MAX_LOSS_DOLLARS = float(os.getenv("WB_SQ_MAX_LOSS_DOLLARS", "500"))
SQ_CORE_PCT = int(os.getenv("WB_SQ_CORE_PCT", "90"))

BAIL_TIMER_ENABLED = os.getenv("WB_BAIL_TIMER_ENABLED", "1") == "1"
BAIL_TIMER_MINUTES = float(os.getenv("WB_BAIL_TIMER_MINUTES", "5"))


# ══════════════════════════════════════════════════════════════════════
# Per-symbol state
# ══════════════════════════════════════════════════════════════════════


@dataclass
class _Position:
    """Squeeze position state — augmented to carry every field Setup A's
    `_squeeze_exit` ladder reads. Field names match Setup A's open_position
    dict so a future persistence layer can map 1:1 between the two setups.

    Field map (Setup A pos[...] → engine self.X):
      pos["entry"]              → entry           (filled avg)
      pos["stop"]               → stop            (hard stop)
      pos["r"]                  → r               (entry - stop_low for longs)
      pos["qty"]                → qty             (CURRENT qty; drops to runner
                                                    on partial-target exit)
      pos["peak"]               → peak            (max price since entry)
      pos["tp_hit"]             → tp_hit          (target-R partial taken)
      pos["partial_filled_qty"] → partial_filled_qty  (the core size sold at TP)
      pos["partial_filled_at"]  → partial_filled_at   (iso UTC stamp of TP exit)
      pos["runner_stop"]        → runner_stop     (post-TP minimum stop)
      pos["is_parabolic"]       → is_parabolic    (parsed from ENTRY SIGNAL why=)
      pos["entry_time"]         → entry_time      (datetime in ET)
      pos["setup_type"]         → setup_type      ("squeeze" today)
      pos["score"] / pos["score_detail"]
                                 → score / score_detail
      pos["fill_confirmed"]     → fill_confirmed  (True after wait_for_fill)
      pos["order_id"]           → order_id        (ENTRY order id, audit only)

    Engine-only fields (no Setup A equivalent):
      exit_in_flight            — retry-loop ownership guard (see comment
                                   block on `_submit_exit`).
    """
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
    score_detail: str = ""
    is_parabolic: bool = False
    # Trade-management state — mutated by the exit ladder.
    tp_hit: bool = False
    partial_filled_qty: int = 0
    partial_filled_at: Optional[str] = None  # iso UTC string for JSON-trivial
    runner_stop: float = 0.0
    fill_confirmed: bool = False
    # In-flight guard: prevents duplicate exit submissions while a
    # retry-and-reprice loop is mid-flight (without this, every adverse
    # tick during a 4-attempt × 10s retry window would spawn a new exit
    # thread and double-sell).
    exit_in_flight: bool = False


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
        # RLock — the exit ladder's persistence-flush hook (added in the
        # session-persistence commit) re-enters the lock from a context
        # already holding it; using a plain Lock would deadlock. We use
        # RLock from the start so the ladder code can call any helper
        # without lock-discipline footguns.
        self._positions_lock = threading.RLock()
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

        notional = qty * entry
        print(f"[SQUEEZE] {now_iso_et()} {symbol} ENTRY qty={qty} "
              f"ibkr_signal=${entry:.4f} stop=${stop:.4f} R=${r:.4f} "
              f"risk=${risk_dollars:.0f} notional=${notional:,.0f} "
              f"score={score:.1f}", flush=True)

        # Parabolic flag — Setup A reads this from `armed.score_detail`,
        # which we get via the ENTRY SIGNAL's `why=` suffix. The detector
        # appends "[PARABOLIC]" to score_detail when parabolic mode armed;
        # downstream the trail rung reads `is_parabolic` to pick the
        # tighter SQ_PARA_TRAIL_R over SQ_TRAIL_R.
        is_parabolic = "[PARABOLIC]" in sig
        score_detail = sig.split("why=", 1)[1] if "why=" in sig else ""

        # Off-loop retry-with-reprice loop. Each retry repulls
        # get_priced_limit() which reads the freshest cached Alpaca
        # quote — so retries chase real Alpaca liquidity rather than
        # the stale IBKR-derived limit that caused the TRAW 4-retry
        # timeout on 2026-05-11.
        def _await_fill():
            res = place_with_retry(
                self.broker, self.state, symbol, "BUY", qty,
                ibkr_signal_price=entry,
                log_prefix="SQUEEZE",
                log_label="QUOTE_AWARE",
            )
            if res.fill_price is not None and res.filled_qty > 0:
                pos = _Position(
                    symbol=symbol, qty=res.filled_qty,
                    entry=float(res.fill_price),
                    stop=stop, r=r, score=score,
                    entry_time=now_et(), order_id=res.last_order_id or "",
                    peak=float(res.fill_price),
                    score_detail=score_detail,
                    is_parabolic=is_parabolic,
                    fill_confirmed=True,
                )
                with self._positions_lock:
                    self.positions[symbol] = pos
                self.risk.daily_entries += 1
                det.notify_trade_opened()
                retry_tag = f" (after {res.attempts} retries)" if res.attempts > 0 else ""
                para_tag = " [PARABOLIC]" if is_parabolic else ""
                print(f"[SQUEEZE] {now_iso_et()} {symbol} FILL @ "
                      f"${res.fill_price:.4f} qty={res.filled_qty}{retry_tag}{para_tag}",
                      flush=True)
            else:
                # place_with_retry already logged the timeout reason
                # (max retries vs chase-cap exceeded). Nothing else to do —
                # detector state was not advanced past `armed` clearance,
                # so the next legitimate trigger can fire normally.
                pass

        threading.Thread(target=_await_fill, daemon=True,
                         name=f"squeeze-fill-{symbol}").start()

    # ── Exit management ──────────────────────────────────────────────

    def _tick_manage_exit(self, symbol: str, price: float):
        """Full Setup A squeeze exit ladder, byte-for-byte port of
        `_squeeze_exit` in bot_v3_hybrid.py.

        Ladder order (must match Setup A exactly for A/B isolation):
          [Bail timer]    pre-ladder gate — minutes_in_trade >= MIN and
                          price <= entry → bail. Honors WB_BAIL_TIMER_ENABLED.
          [0] Dollar loss cap (SQ_MAX_LOSS_DOLLARS) — exit at any unrealized
                          loss >= cap. Fired first so a violent reversal
                          can't fall through to the slower trail.
          [1] Hard stop — price <= stop (long stop is below entry).
          [Pre-target]    — until tp_hit:
            [2] Trail     — price <= peak - (trail_r * r). trail_r is
                          SQ_PARA_TRAIL_R for parabolic positions, else
                          SQ_TRAIL_R. Same trail used pre-target only.
            [3] Target    — price >= entry + (SQ_TARGET_R * r). Take SQ_CORE_PCT%
                          off as the "core" exit, runner stays open with
                          runner_stop = max(stop, entry + 0.01). Sets tp_hit.
          [Post-target]   — once tp_hit (runner phase):
            [4] Runner trail — price <= max(runner_stop, peak - SQ_RUNNER_TRAIL_R*r).

        Every exit is a SELL LIMIT via `_submit_exit` (which uses
        place_with_retry → cross-feed-aware pricing + retry). Project
        rules: no market orders, no broker stops. The exit_in_flight guard
        prevents the retry loop from being entered twice in parallel.
        """
        with self._positions_lock:
            pos = self.positions.get(symbol)
            if pos is None:
                return
            # Don't manage exits until entry fill is confirmed.
            if not pos.fill_confirmed:
                return

            # Update peak.
            if price > pos.peak:
                pos.peak = price

            # Skip if an exit cycle is already mid-retry; the in-flight
            # loop owns the position until it completes or aborts.
            if pos.exit_in_flight:
                return

            entry = pos.entry
            stop = pos.stop
            r = pos.r
            qty = pos.qty

            # ── Bail timer (pre-ladder gate) ──────────────────────────
            if BAIL_TIMER_ENABLED:
                minutes_in = (now_et() - pos.entry_time).total_seconds() / 60.0
                if minutes_in >= BAIL_TIMER_MINUTES and price <= entry:
                    pos.exit_in_flight = True
                    self._submit_exit(pos, price, reason="bail_timer")
                    return

            # ── 0) Dollar loss cap ────────────────────────────────────
            if SQ_MAX_LOSS_DOLLARS > 0:
                unrealized_loss = (entry - price) * qty
                if unrealized_loss >= SQ_MAX_LOSS_DOLLARS:
                    pos.exit_in_flight = True
                    self._submit_exit(
                        pos, price,
                        reason=f"sq_dollar_loss_cap (${unrealized_loss:,.0f})",
                    )
                    return

            # ── 1) Hard stop ──────────────────────────────────────────
            if price <= stop:
                pos.exit_in_flight = True
                self._submit_exit(pos, price, reason="sq_stop_hit")
                return

            # ── Pre-target phase ──────────────────────────────────────
            if not pos.tp_hit:
                # [2] Trailing stop. For parabolic positions Setup A uses
                # the tighter SQ_PARA_TRAIL_R to lock gains aggressively.
                if r > 0:
                    trail_r = SQ_PARA_TRAIL_R if pos.is_parabolic else SQ_TRAIL_R
                    trail_price = pos.peak - (trail_r * r)
                    if price <= trail_price:
                        reason = ("sq_para_trail_exit" if pos.is_parabolic
                                  else "sq_trail_exit")
                        pos.exit_in_flight = True
                        self._submit_exit(pos, price, reason=reason)
                        return

                # [3] Target hit — exit core, keep runner. SQ_CORE_PCT % off
                # at target; the remaining qty becomes the runner managed
                # by the post-target branch on subsequent ticks.
                #
                # NB: Setup A's EPL graduation hook (bot_v3_hybrid.py
                # line 3041-3058) is NOT ported — EPL is a Setup-A-only
                # framework that doesn't run on the engine side. Omitting
                # it does NOT change exit-fill behavior (no SELL is gated
                # on EPL graduation; it's just bookkeeping for a different
                # strategy that the engine doesn't run).
                if r > 0 and price >= entry + (SQ_TARGET_R * r):
                    pos.tp_hit = True
                    pos.partial_filled_at = datetime.now(UTC).isoformat()
                    qty_core = max(1, int(qty * SQ_CORE_PCT / 100))
                    qty_runner = qty - qty_core
                    pos.partial_filled_qty = qty_core
                    if qty_runner > 0:
                        pos.runner_stop = max(stop, entry + 0.01)
                        # Shrink the bot-tracked qty to the runner size
                        # BEFORE the exit is submitted, so a parallel tick
                        # observing the runner-stop branch sees the right
                        # qty. Setup A sets pos["qty"] = qty_runner AFTER
                        # exit_trade(); we do it before because our exit
                        # path is async (place_with_retry on a worker
                        # thread) and we can't rely on synchronous order
                        # like Setup A's exit_trade does.
                        pos.qty = qty_runner
                        pos.exit_in_flight = True  # runner remains, in_flight is for core sale
                        self._submit_exit_partial(
                            pos, price, qty_core, reason="sq_target_hit",
                        )
                    else:
                        # qty_core == qty (SQ_CORE_PCT=100, or qty was 1
                        # to start). Full exit at target — no runner.
                        pos.exit_in_flight = True
                        self._submit_exit(pos, price, reason="sq_target_hit")
                    return

            # ── Post-target (runner) phase ────────────────────────────
            if pos.tp_hit and pos.qty > 0:
                if r > 0:
                    runner_trail = pos.peak - (SQ_RUNNER_TRAIL_R * r)
                    runner_stop = max(pos.runner_stop, runner_trail)
                    if runner_stop > pos.runner_stop:
                        pos.runner_stop = runner_stop
                    if price <= runner_stop:
                        pos.exit_in_flight = True
                        self._submit_exit(pos, price, reason="sq_runner_trail")
                        return

    def _submit_exit(self, pos: _Position, price: float, reason: str):
        """SELL LIMIT exit for the FULL current pos.qty.

        Cross-feed-aware: uses cached Alpaca bid when fresh so we sell at
        Alpaca's actual bid rather than IBKR's possibly-stale price. On
        timeout the order is cancelled and re-priced against the freshest
        Alpaca quote.

        Stop-hit / max-loss / dollar-cap exits use a wider buffer (urgency
        to clear). Project rule: no market orders, ever.
        """
        symbol = pos.symbol
        urgent_reasons = ("sq_stop_hit", "sq_max_loss_hit", "sq_dollar_loss_cap")
        # Match Setup A's urgent-vs-normal limit buffer asymmetry. Setup A
        # uses `price * 0.97` for urgent (a 3% below-market chase-cap that
        # rapidly walks down to the bid) and `price - 0.03` for non-urgent.
        # We map that to the engine's get_priced_limit knobs: a 3.0% base+
        # cross buffer for urgent, defaults (0.5%) for normal — same
        # economic effect within rounding.
        if reason.startswith("sq_dollar_loss_cap") or reason in urgent_reasons:
            base_buf = 3.0
            cross_buf = 3.0
            label = "QUOTE_AWARE_STOP"
        else:
            base_buf = None
            cross_buf = None
            label = "QUOTE_AWARE"
        print(f"[SQUEEZE] {now_iso_et()} {symbol} EXIT submitting "
              f"reason={reason} qty={pos.qty} ref=${price:.4f}", flush=True)

        # Capture qty BEFORE handing to the worker — pos.qty can mutate
        # under us if the main loop transitions to runner phase.
        exit_qty = pos.qty

        def _await_exit_fill():
            res = place_with_retry(
                self.broker, self.state, symbol, "SELL", exit_qty,
                ibkr_signal_price=price,
                base_buffer_pct=base_buf,
                cross_feed_buffer_pct=cross_buf,
                log_prefix="SQUEEZE",
                log_label=label,
            )
            if res.fill_price is not None and res.filled_qty > 0:
                pnl = (res.fill_price - pos.entry) * res.filled_qty
                self.risk.record_close(pnl)
                with self._positions_lock:
                    self.positions.pop(symbol, None)
                det = self.detectors.get(symbol)
                if det is not None:
                    try:
                        det.notify_trade_closed(
                            symbol, pnl,
                            r_mult=(pnl / (exit_qty * pos.r))
                            if pos.r > 0 and exit_qty > 0 else 0.0)
                    except Exception:
                        pass
                retry_tag = f" (after {res.attempts} retries)" if res.attempts > 0 else ""
                partial_tag = (f" [PARTIAL {res.filled_qty}/{exit_qty}]"
                               if res.filled_qty < exit_qty else "")
                print(f"[SQUEEZE] {now_iso_et()} {symbol} CLOSED @ "
                      f"${res.fill_price:.4f} pnl=${pnl:+,.2f} reason={reason} "
                      f"daily_pnl=${self.risk.daily_pnl:+,.2f}{retry_tag}{partial_tag}",
                      flush=True)
            else:
                # Exit didn't fill — clear the in-flight flag so the next
                # adverse tick triggers another full retry cycle.
                with self._positions_lock:
                    live = self.positions.get(symbol)
                    if live is not None:
                        live.exit_in_flight = False
                print(f"[SQUEEZE] {now_iso_et()} {symbol} EXIT FAILED — "
                      f"position still open, will retry on next adverse tick",
                      flush=True)

        threading.Thread(target=_await_exit_fill, daemon=True,
                         name=f"squeeze-exit-{symbol}").start()

    def _submit_exit_partial(self, pos: _Position, price: float,
                              core_qty: int, reason: str):
        """SELL LIMIT exit for the CORE portion at target-hit. The runner
        (pos.qty after the shrink in the caller) stays open and is managed
        by the post-target branch of `_tick_manage_exit` on subsequent
        ticks.

        P&L is booked for the CORE shares only — the runner books its own
        P&L when it eventually exits via `_submit_exit`. This matches
        Setup A's exit_trade(symbol, price, qty_core, "sq_target_hit")
        semantics (exit_trade computes pnl on the qty argument, not the
        full pos["qty"]).
        """
        symbol = pos.symbol
        print(f"[SQUEEZE] {now_iso_et()} {symbol} TARGET HIT — selling core "
              f"qty={core_qty} (keeping runner qty={pos.qty}) ref=${price:.4f}",
              flush=True)

        def _await_partial_fill():
            res = place_with_retry(
                self.broker, self.state, symbol, "SELL", core_qty,
                ibkr_signal_price=price,
                log_prefix="SQUEEZE",
                log_label="QUOTE_AWARE",
            )
            if res.fill_price is not None and res.filled_qty > 0:
                pnl = (res.fill_price - pos.entry) * res.filled_qty
                self.risk.record_close(pnl)
                with self._positions_lock:
                    live = self.positions.get(symbol)
                    if live is not None:
                        live.partial_filled_qty = int(res.filled_qty)
                        live.exit_in_flight = False  # runner is free to manage now
                retry_tag = f" (after {res.attempts} retries)" if res.attempts > 0 else ""
                print(f"[SQUEEZE] {now_iso_et()} {symbol} CORE EXIT @ "
                      f"${res.fill_price:.4f} qty={res.filled_qty} "
                      f"pnl=${pnl:+,.2f} reason={reason} "
                      f"daily_pnl=${self.risk.daily_pnl:+,.2f}{retry_tag} "
                      f"— runner ({pos.qty}sh) active",
                      flush=True)
            else:
                # Core didn't fill — back out the tp_hit flip so the
                # pre-target ladder takes the next tick instead of the
                # runner phase (otherwise we'd be in runner mode with no
                # core sale, which is a bug). Setup A doesn't hit this
                # case because exit_trade is synchronous; we do, hence the
                # rollback.
                with self._positions_lock:
                    live = self.positions.get(symbol)
                    if live is not None:
                        # Restore the qty we shrunk in _tick_manage_exit.
                        live.qty = live.qty + core_qty
                        live.tp_hit = False
                        live.partial_filled_at = None
                        live.partial_filled_qty = 0
                        live.runner_stop = 0.0
                        live.exit_in_flight = False
                print(f"[SQUEEZE] {now_iso_et()} {symbol} CORE EXIT FAILED "
                      f"— rolled back tp_hit, will retry target on next tick",
                      flush=True)

        threading.Thread(target=_await_partial_fill, daemon=True,
                         name=f"squeeze-core-{symbol}").start()

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
