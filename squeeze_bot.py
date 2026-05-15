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
    presubmit_bp_check,
    entry_time_allowed,
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

# Session-resume gate. Mirrors Setup A's WB_SESSION_RESUME_ENABLED. When 0
# (default), bot writes durable state but cold-starts on every boot so a
# later "flip to 1" can resume cleanly without retroactive bugs.
SESSION_RESUME_ENABLED = os.getenv("WB_SESSION_RESUME_ENABLED", "0") == "1"


# ══════════════════════════════════════════════════════════════════════
# Per-symbol state
# ══════════════════════════════════════════════════════════════════════


@dataclass
class _Position:
    """Squeeze position state — augmented to carry every field Setup A's
    `_squeeze_exit` ladder reads. Field names match Setup A's open_position
    dict so the persistence layer's schema can map 1:1 between the two
    setups when we eventually want to compare.

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
    # Trade-management state — mutated by the exit ladder, persisted on every
    # change so a crash-restart resumes from the right rung of the ladder.
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
    def __init__(self, *, boot_mode: str = "cold", boot_reason: str = "no_marker"):
        if not SQ_ENABLED:
            raise SystemExit("WB_SQUEEZE_ENABLED=0 — refusing to start.")
        self.bot_id = "squeeze_bot"
        self.boot_mode = boot_mode
        self.boot_reason = boot_reason
        self.broker = make_alpaca_broker()
        self.starting_equity = starting_equity_from_broker(self.broker)
        self.risk = DailyRisk(self.starting_equity)
        print(f"[SQUEEZE] {now_iso_et()} starting equity ${self.starting_equity:,.0f} "
              f"(third Alpaca paper account)", flush=True)
        self.state = EngineState()
        self.detectors: dict[str, SqueezeDetector] = {}
        self.positions: dict[str, _Position] = {}
        # Per-symbol seed state. The engine seeds the bar-builder from
        # tick_cache at boot + on intraday adds, then broadcasts those
        # replayed bars to clients. Without this state the detector
        # can't tell "seed bar" from "live bar" and its stale-arm
        # safeguard (validate_arm_after_seed) never fires — see
        # ATRA 2026-05-13 phantom-arm incident.
        #
        # Bar-age heuristic: a bar whose ts_close is >30s older than
        # wall-clock is a replayed seed bar. Live bars arrive within
        # ~5s of their bucket close. State machine per symbol:
        #   cold → seeding (first seed bar) → live (first live bar,
        #   at which point we call end_seed + validate_arm_after_seed)
        self.seeding: dict[str, bool] = {}
        self.seed_last_price: dict[str, float] = {}
        # RLock because `_persist_open_trades` re-enters the lock from
        # inside `_tick_manage_exit` (which is already holding it). A
        # plain Lock would deadlock the bot the first time the ladder
        # tries to persist mid-exit.
        self._positions_lock = threading.RLock()
        self._shutdown = threading.Event()
        # Per-bot persistence helper — writes go to session_state_engine/<date>/squeeze_bot/.
        self.session = EngineSession(self.bot_id)
        # If we're cold-starting, stamp the marker so a subsequent crash
        # within the same day can be detected as a resume candidate.
        if self.boot_mode == "cold":
            try:
                self.session.write_marker()
            except Exception as e:
                print(f"[SQUEEZE] {now_iso_et()} write_marker error: {e!r}", flush=True)
        # Resume rehydration runs early so positions are available before
        # the engine reader thread starts firing ticks.
        if self.boot_mode == "resume":
            self._resume_rehydrate()

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
        # During seed replay, ticks accompany bars; the detector's seed
        # path handles warmup via seed_bar_close. Routing seed-time ticks
        # through on_trade_price would let a stale armed setup fire an
        # entry mid-replay (the ATRA 2026-05-13 phantom-arm bug). Skip.
        if self.seeding.get(sym, False):
            return
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

        # ── Seed vs live routing ──────────────────────────────────────
        # The engine seeds bar-builder from tick_cache at boot and on
        # intraday adds, then broadcasts those replayed bars to clients.
        # The detector has separate code paths for seed vs live (seed
        # warms indicators silently; live can fire signals). Bar age
        # tells us which: live bars arrive within ~5s of their ts_close;
        # seed bars are minutes-to-hours old. Threshold 30s.
        #
        # State machine: cold → seeding (first seed bar) → live (first
        # live bar). The seeding→live transition is the critical
        # boundary where we call end_seed + validate_arm_after_seed to
        # drop arms whose trigger is already far below current price.
        now_utc = datetime.now(UTC)
        try:
            ts_close_dt = datetime.fromisoformat(msg.ts_close)
            bar_age_s = (now_utc - ts_close_dt.astimezone(UTC)).total_seconds()
        except Exception:
            # Unparseable ts_close — assume live to preserve current behavior.
            bar_age_s = 0.0
        is_seed_bar = bar_age_s > 30

        was_seeding = self.seeding.get(sym, False)

        if is_seed_bar:
            # Seed bar — route through detector's seed path (no signals).
            if not was_seeding:
                # Entering seed phase for this symbol — explicit begin_seed
                # to keep the detector's internal flags consistent with
                # Setup A's bot_v3_hybrid pattern.
                try:
                    det.begin_seed()
                except Exception as e:
                    print(f"[SQUEEZE] {now_iso_et()} {sym} begin_seed error: "
                          f"{e!r}", flush=True)
                self.seeding[sym] = True
            try:
                det.seed_bar_close(bar.open, bar.high, bar.low, bar.close,
                                    bar.volume)
            except Exception as e:
                print(f"[SQUEEZE] {now_iso_et()} {sym} seed_bar_close error: "
                      f"{e!r}", flush=True)
            self.seed_last_price[sym] = bar.close
            return  # No signal evaluation during seed

        # Live bar — handle seed→live transition first.
        if was_seeding:
            try:
                det.end_seed()
            except Exception as e:
                print(f"[SQUEEZE] {now_iso_et()} {sym} end_seed error: {e!r}",
                      flush=True)
            last_price = self.seed_last_price.get(sym, bar.close)
            try:
                validation = det.validate_arm_after_seed(last_price)
                if validation:
                    print(f"[BOT-SEED-VALIDATE] {now_iso_et()} {sym} "
                          f"{validation}", flush=True)
            except Exception as e:
                print(f"[SQUEEZE] {now_iso_et()} {sym} validate_arm_after_seed "
                      f"error: {e!r}", flush=True)
            self.seeding[sym] = False
            print(f"[SQUEEZE] {now_iso_et()} {sym} seed→live transition "
                  f"(seed_last_price=${last_price:.4f})", flush=True)

        # Now process the live bar normally.
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
        # Persist the watchlist so a resumed engine + bot pair can see
        # what symbols this session has been tracking. Best-effort.
        try:
            self.session.write_watchlist(list(msg.watchlist))
        except Exception as e:
            print(f"[SQUEEZE] {now_iso_et()} write_watchlist error: {e!r}",
                  flush=True)

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

        # Entry-time cutoff (user directive 2026-05-14).
        _et_ok, _et_reason = entry_time_allowed()
        if not _et_ok:
            print(f"[SQUEEZE] {now_iso_et()} {symbol} ENTRY BLOCKED: {_et_reason}",
                  flush=True)
            return

        # Pre-submit BP check (Cowork directive 2026-05-14 §3).
        _bp_ok, _bp_reason = presubmit_bp_check(self.broker, symbol, qty, entry,
                                                 log_prefix="[SQUEEZE] ")
        if not _bp_ok:
            print(f"[SQUEEZE] {now_iso_et()} {symbol} ENTRY BLOCKED: {_bp_reason}",
                  flush=True)
            return

        # L2 Layer 1 observe-only gate (Cowork DIRECTIVE_2026-05-15_L2_LAYER1_TODAY).
        if os.environ.get("WB_SQ_L2_FILTER_ENABLED", "0") == "1":
            try:
                import l2_helper
                _l2_state = l2_helper.request_l2_snapshot(symbol, None, timeout_sec=2.0)
                _l2_verdict = l2_helper.evaluate_l2_filter(_l2_state)
                print(f"[L2] SQ_ARM {symbol} state={l2_helper.summarize_l2(_l2_state)} "
                      f"verdict={_l2_verdict.action} reason={_l2_verdict.reason}",
                      flush=True)
                if os.environ.get("WB_SQ_L2_FILTER_OBSERVE_ONLY", "1") != "1":
                    if _l2_verdict.action == "VETO":
                        print(f"[SQUEEZE] {now_iso_et()} {symbol} ENTRY BLOCKED by L2: "
                              f"{_l2_verdict.reason}", flush=True)
                        return
            except Exception as _e:
                print(f"[L2] SQ_ARM {symbol} eval failed: {_e!r} — proceeding",
                      flush=True)

        # Parabolic flag — Setup A reads this from `armed.score_detail`,
        # which we get via the ENTRY SIGNAL's `why=` suffix. The detector
        # appends "[PARABOLIC]" to score_detail when parabolic mode armed.
        # Parsing the full text rather than `parts["why"]` because the why
        # token can contain semicolons that the naive split corrupts.
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
                # Persist immediately on fill confirmation — same as Setup A's
                # persist_open_trades() write point.
                self._persist_open_trades()
                retry_tag = f" (after {res.attempts} retries)" if res.attempts > 0 else ""
                para_tag = " [PARABOLIC]" if is_parabolic else ""
                print(f"[SQUEEZE] {now_iso_et()} {symbol} FILL @ "
                      f"${res.fill_price:.4f} qty={res.filled_qty}{retry_tag}{para_tag}",
                      flush=True)
            else:
                # place_with_retry already logged the specific failure
                # reason (timeout / rejected / chase-cap exceeded). Nothing
                # else to do — detector state was not advanced past `armed`
                # clearance, so the next legitimate trigger can fire normally.
                pass

        threading.Thread(target=_await_fill, daemon=True,
                         name=f"squeeze-fill-{symbol}").start()

    # ── Exit management ──────────────────────────────────────────────

    def _tick_manage_exit(self, symbol: str, price: float):
        """Full Setup A squeeze exit ladder, byte-for-byte port of
        `_squeeze_exit` in bot_v3_hybrid.py (line 3005-3083 at HEAD).

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
        prevents the retry loop from being entered twice in parallel; once
        an exit is dispatched, subsequent ticks bail at the top of this
        method until the loop completes or aborts.
        """
        with self._positions_lock:
            pos = self.positions.get(symbol)
            if pos is None:
                return
            # Don't manage exits until entry fill is confirmed (Setup A
            # gates this on fill_confirmed; we set fill_confirmed=True the
            # moment _await_fill records a fill, so this is mostly a no-op
            # but matches Setup A's defensive ordering).
            if not pos.fill_confirmed:
                return

            # Update peak — persist on advance like Setup A.
            if price > pos.peak:
                pos.peak = price
                self._persist_open_trades()

            # Skip if an exit cycle is already mid-retry; the in-flight
            # loop owns the position until it completes or aborts.
            if pos.exit_in_flight:
                return

            entry = pos.entry
            stop = pos.stop
            r = pos.r
            qty = pos.qty

            # ── Bail timer (pre-ladder gate) ──────────────────────────
            # Setup A's manage_exit dispatches to _squeeze_exit AFTER the
            # bail-timer check. We inline that here so dispatch order is
            # byte-identical: bail first, then dollar-cap, then ladder.
            if BAIL_TIMER_ENABLED:
                minutes_in = (now_et() - pos.entry_time).total_seconds() / 60.0
                if minutes_in >= BAIL_TIMER_MINUTES and price <= entry:
                    pos.exit_in_flight = True
                    self._persist_open_trades()
                    self._submit_exit(pos, price, reason="bail_timer")
                    return

            # ── 0) Dollar loss cap ────────────────────────────────────
            if SQ_MAX_LOSS_DOLLARS > 0:
                unrealized_loss = (entry - price) * qty
                if unrealized_loss >= SQ_MAX_LOSS_DOLLARS:
                    pos.exit_in_flight = True
                    self._persist_open_trades()
                    self._submit_exit(
                        pos, price,
                        reason=f"sq_dollar_loss_cap (${unrealized_loss:,.0f})",
                    )
                    return

            # ── 1) Hard stop ──────────────────────────────────────────
            if price <= stop:
                pos.exit_in_flight = True
                self._persist_open_trades()
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
                        self._persist_open_trades()
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
                # strategy that the engine doesn't run). Document this so
                # a later sweep doesn't quietly add it.
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
                        #
                        # Critical: _submit_exit must use the qty value
                        # captured BEFORE this shrink, so we pass qty_core
                        # explicitly rather than re-reading pos.qty.
                        pos.qty = qty_runner
                        pos.exit_in_flight = True  # runner remains, in_flight is for the core sale
                        self._persist_open_trades()
                        self._submit_exit_partial(
                            pos, price, qty_core, reason="sq_target_hit",
                        )
                    else:
                        # qty_core == qty (SQ_CORE_PCT=100, or qty was 1
                        # to start). Full exit at target — no runner.
                        pos.exit_in_flight = True
                        self._persist_open_trades()
                        self._submit_exit(pos, price, reason="sq_target_hit")
                    return

            # ── Post-target (runner) phase ────────────────────────────
            # The bail-timer above already fired for the pre-runner window;
            # post-target trail is the only remaining exit rung.
            if pos.tp_hit and pos.qty > 0:
                if r > 0:
                    runner_trail = pos.peak - (SQ_RUNNER_TRAIL_R * r)
                    runner_stop = max(pos.runner_stop, runner_trail)
                    if runner_stop > pos.runner_stop:
                        pos.runner_stop = runner_stop
                        self._persist_open_trades()
                    if price <= runner_stop:
                        pos.exit_in_flight = True
                        self._persist_open_trades()
                        self._submit_exit(pos, price, reason="sq_runner_trail")
                        return

    def _submit_exit(self, pos: _Position, price: float, reason: str):
        """SELL LIMIT exit for the FULL current pos.qty.

        Cross-feed-aware: uses cached Alpaca bid when fresh so we sell at
        Alpaca's actual bid rather than IBKR's possibly-stale price. On
        timeout the order is cancelled and re-priced against the freshest
        Alpaca quote — this fixes the CLNN trail-limit no-fill scenario
        from 2026-05-11 where the SELL limit sat above Alpaca's bid until
        the position bled out.

        Stop-hit / max-loss / dollar-cap exits use a wider buffer (urgency
        to clear). Project rule: no market orders, ever.

        Persistence: closes (filled) flush risk.json + clear open_trades.json
        synchronously inside the fill thread. Timeouts re-flush
        open_trades.json so the persisted state knows the exit is no longer
        in flight.
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
                # Persist: position cleared, risk advanced.
                self._persist_open_trades()
                self._persist_risk()
                retry_tag = f" (after {res.attempts} retries)" if res.attempts > 0 else ""
                partial_tag = (f" [PARTIAL {res.filled_qty}/{exit_qty}]"
                               if res.filled_qty < exit_qty else "")
                print(f"[SQUEEZE] {now_iso_et()} {symbol} CLOSED @ "
                      f"${res.fill_price:.4f} pnl=${pnl:+,.2f} reason={reason} "
                      f"daily_pnl=${self.risk.daily_pnl:+,.2f}{retry_tag}{partial_tag}",
                      flush=True)
            else:
                # Exit didn't fill — clear the in-flight flag so the next
                # adverse tick triggers another full retry cycle. Project
                # rule: no market fallback.
                with self._positions_lock:
                    live = self.positions.get(symbol)
                    if live is not None:
                        live.exit_in_flight = False
                self._persist_open_trades()
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

        Persistence: target-hit partials are a state transition (tp_hit
        flipped, partial_filled_qty / runner_stop set). The caller already
        wrote open_trades.json before calling this; we write again on the
        actual fill to record the partial_filled_at timestamp accurately
        and on close-of-thread to clear exit_in_flight.

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
                # Update partial_filled_qty in case Alpaca filled less than
                # requested (rare — most likely full core fill).
                with self._positions_lock:
                    live = self.positions.get(symbol)
                    if live is not None:
                        live.partial_filled_qty = int(res.filled_qty)
                        live.exit_in_flight = False  # runner is free to manage now
                self._persist_open_trades()
                self._persist_risk()
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
                self._persist_open_trades()
                print(f"[SQUEEZE] {now_iso_et()} {symbol} CORE EXIT FAILED "
                      f"— rolled back tp_hit, will retry target on next tick",
                      flush=True)

        threading.Thread(target=_await_partial_fill, daemon=True,
                         name=f"squeeze-core-{symbol}").start()

    # ── Persistence ──────────────────────────────────────────────────

    def _position_to_record(self, pos: _Position) -> dict:
        """Map _Position → open_trades.json schema. Field set matches the
        EngineSession.OPEN_TRADE_REQUIRED_FIELDS_ENGINE validation set."""
        return {
            "symbol": pos.symbol,
            "setup_type": pos.setup_type,
            "entry_price": float(pos.entry),
            "entry_time": pos.entry_time.isoformat(),
            "qty": int(pos.qty),
            "r": float(pos.r),
            "stop": float(pos.stop),
            "score": float(pos.score),
            "peak": float(pos.peak),
            "tp_hit": bool(pos.tp_hit),
            "partial_filled_qty": int(pos.partial_filled_qty),
            "partial_filled_at": pos.partial_filled_at,
            "runner_stop": float(pos.runner_stop),
            "is_parabolic": bool(pos.is_parabolic),
            "fill_confirmed": bool(pos.fill_confirmed),
            "order_id": pos.order_id,
            # Audit-only — handy in post-mortem JSON inspection.
            "score_detail": pos.score_detail,
        }

    def _record_to_position(self, rec: dict) -> _Position:
        """Inverse — rebuild a _Position from a persisted record."""
        entry_time_str = rec.get("entry_time", "")
        try:
            et = datetime.fromisoformat(entry_time_str)
            if et.tzinfo is None:
                et = et.replace(tzinfo=UTC)
            et = et.astimezone(ET)
        except (ValueError, TypeError):
            et = now_et()
        return _Position(
            symbol=rec["symbol"],
            qty=int(rec["qty"]),
            entry=float(rec["entry_price"]),
            stop=float(rec["stop"]),
            r=float(rec["r"]),
            score=float(rec.get("score", 0.0)),
            entry_time=et,
            order_id=rec.get("order_id", ""),
            peak=float(rec.get("peak", rec["entry_price"])),
            setup_type=rec.get("setup_type", "squeeze"),
            score_detail=rec.get("score_detail", ""),
            is_parabolic=bool(rec.get("is_parabolic", False)),
            tp_hit=bool(rec.get("tp_hit", False)),
            partial_filled_qty=int(rec.get("partial_filled_qty", 0)),
            partial_filled_at=rec.get("partial_filled_at"),
            runner_stop=float(rec.get("runner_stop", 0.0)),
            fill_confirmed=bool(rec.get("fill_confirmed", True)),
            exit_in_flight=False,  # never persist in-flight state
        )

    def _persist_open_trades(self) -> None:
        """Flush every currently-confirmed position to open_trades.json.
        Best-effort: on IO error log and continue — the periodic flush
        thread will retry."""
        try:
            with self._positions_lock:
                trades = [self._position_to_record(p)
                          for p in self.positions.values()
                          if p.fill_confirmed]
            self.session.write_open_trades(trades)
        except Exception as e:
            print(f"[SQUEEZE] {now_iso_et()} persist_open_trades error: {e!r}",
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
            print(f"[SQUEEZE] {now_iso_et()} persist_risk error: {e!r}", flush=True)

    def _periodic_flush_loop(self):
        """Belt-and-suspenders background flush — every WB_SESSION_FLUSH_SEC
        seconds, rewrite open_trades.json + risk.json so a kill -9 mid-
        update loses at most one cycle worth of trail-stop drift."""
        while not self._shutdown.is_set():
            self._shutdown.wait(self.session.flush_sec)
            if self._shutdown.is_set():
                return
            self._persist_open_trades()
            self._persist_risk()

    # ── Resume ────────────────────────────────────────────────────────

    def _resume_rehydrate(self):
        """Resume-mode startup: rehydrate positions + risk counters from
        disk, cancel any pending Alpaca orders (entry retry state is lost
        on crash; standing exits are an invariant violation), then
        reconcile against Alpaca's actual position list.

        Critical adoption policy (per project rule
        feedback_session_persistence_required.md): if Alpaca reports an
        open position the bot's state doesn't know about, we ADOPT it
        with conservative defaults (stop = entry × 0.97, R = entry × 0.03),
        flagged setup_type="orphan_adopted". We NEVER auto-flatten — the
        2026-05-05 CLNN incident showed how dangerous that is.

        If WB_SESSION_RESUME_ENABLED=0 (default), this method is still
        callable but `main()` won't enter the resume branch (boot_mode
        forced to "cold"); the call is gated externally.
        """
        print(f"[SQUEEZE] {now_iso_et()} RESUME: reconciling state", flush=True)

        # Step 1: cancel any open orders left over from the crash. Standing
        # SELLs are an invariant violation (we never leave protective stops
        # at the broker per project rules); a leftover BUY might be a stale
        # retry attempt that we no longer track.
        cancelled_buy = cancelled_sell = 0
        try:
            open_orders = self.broker.get_open_orders() or []
        except Exception as e:
            print(f"[SQUEEZE] {now_iso_et()} RESUME: get_open_orders failed: {e!r}",
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
                print(f"[SQUEEZE] {now_iso_et()} RESUME: cancel {o.order_id} "
                      f"failed: {e!r}", flush=True)
        if cancelled_buy or cancelled_sell:
            print(f"[SQUEEZE] {now_iso_et()} RESUME: cancelled "
                  f"{cancelled_buy} BUYs + {cancelled_sell} SELLs",
                  flush=True)

        # Step 2: load persisted open trades, index by symbol.
        persisted = self.session.read_open_trades()
        by_symbol = {r["symbol"]: r for r in persisted}

        # Step 3: reconcile against broker.
        try:
            broker_positions = self.broker.get_positions() or []
        except Exception as e:
            print(f"[SQUEEZE] {now_iso_et()} RESUME: get_positions failed: {e!r}",
                  flush=True)
            broker_positions = []

        rehydrated_symbols: set[str] = set()
        for bp in broker_positions:
            sym = bp.symbol
            broker_qty = bp.qty
            broker_entry = bp.avg_entry_price
            qty_avail = bp.qty_available

            if qty_avail == 0:
                print(f"[SQUEEZE] {now_iso_et()} RESUME: {sym} qty={broker_qty} "
                      f"all held_for_orders — skip (pending exit will resolve)",
                      flush=True)
                continue

            rec = by_symbol.get(sym)
            if rec is None:
                # No persisted record → orphan. Adopt with conservative
                # defaults rather than flatten. Setup type marks the
                # provenance so post-mortem can audit.
                print(f"[SQUEEZE] {now_iso_et()} [ORPHAN_DETECTED] {sym} "
                      f"qty={qty_avail} entry=${broker_entry:.4f} "
                      f"— adopting with conservative defaults "
                      f"(stop=entry*0.99, R=entry*0.01)", flush=True)
                # Tighter than Setup A's 3%-stop default because the engine
                # has no idea what setup produced this position; a 1% stop
                # bounds downside while the operator decides what to do.
                pos = _Position(
                    symbol=sym, qty=qty_avail,
                    entry=float(broker_entry),
                    stop=float(broker_entry) * 0.99,
                    r=float(broker_entry) * 0.01,
                    score=0.0,
                    entry_time=now_et(),
                    order_id="adopted",
                    peak=float(broker_entry),
                    setup_type="orphan_adopted",
                    fill_confirmed=True,
                )
                self.positions[sym] = pos
                rehydrated_symbols.add(sym)
                continue

            # Persisted match — rehydrate, but trust broker on qty drift.
            pos = self._record_to_position(rec)
            if pos.qty != broker_qty:
                print(f"[SQUEEZE] {now_iso_et()} RESUME: {sym} qty drift "
                      f"persisted={pos.qty} broker={broker_qty} — trusting broker",
                      flush=True)
                pos.qty = broker_qty
            self.positions[sym] = pos
            rehydrated_symbols.add(sym)
            print(f"[SQUEEZE] {now_iso_et()} RESUME: rehydrated {sym} "
                  f"qty={pos.qty} entry=${pos.entry:.4f} stop=${pos.stop:.4f} "
                  f"peak=${pos.peak:.4f} tp_hit={pos.tp_hit}", flush=True)

        # Step 4: drop persisted records that no longer exist at broker
        # (closed during crash window).
        dropped = set(by_symbol.keys()) - rehydrated_symbols
        for sym in dropped:
            print(f"[SQUEEZE] {now_iso_et()} RESUME: dropping persisted "
                  f"{sym} (no live broker position — closed during crash window)",
                  flush=True)

        # Step 5: restore risk counters.
        risk_data = self.session.read_risk()
        self.risk.daily_pnl = float(risk_data.get("daily_pnl", 0.0))
        self.risk.daily_entries = int(risk_data.get("daily_entries", 0))
        self.risk.consecutive_losses = int(risk_data.get("consecutive_losses", 0))
        self.risk.closed_trades = list(risk_data.get("closed_trades", []))
        print(f"[SQUEEZE] {now_iso_et()} RESUME: risk restored "
              f"daily_pnl=${self.risk.daily_pnl:+,.2f} "
              f"entries={self.risk.daily_entries} "
              f"consec_losses={self.risk.consecutive_losses}", flush=True)

        # Step 6: persist the reconciled state so on-disk matches in-memory.
        self._persist_open_trades()
        self._persist_risk()
        print(f"[SQUEEZE] {now_iso_et()} RESUME: complete", flush=True)

    # ── Main loop ─────────────────────────────────────────────────────

    def run(self):
        sock = connect_to_engine(self.bot_id, timeout=30.0)
        self.state.connected = True
        self.state.stream_paused = True  # cleared on first heartbeat with ibkr_connected=True
        print(f"[SQUEEZE] {now_iso_et()} connected to engine — fail-CLOSED until "
              f"first healthy heartbeat", flush=True)

        # Periodic flush thread — every WB_SESSION_FLUSH_SEC seconds,
        # rewrite open_trades.json + risk.json so a kill -9 mid-update
        # loses at most one cycle worth of trail-stop drift.
        threading.Thread(target=self._periodic_flush_loop, daemon=True,
                         name="periodic-flush").start()

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
    """CLI:
      --resume  Force resume from today's marker (cold-starts if no marker).
      --fresh   Force cold start, scrubbing today's session_state_engine/<date>/<bot_id>/.
      (no flag) Auto-decide via marker presence (Setup A's pattern).

    The resume gate WB_SESSION_RESUME_ENABLED must ALSO be 1 for resume to
    actually take effect — when 0 (default), the bot writes durable state
    but cold-starts on every boot. This matches Setup A's two-gate setup
    so a config flip on either side has the same effect.
    """
    import argparse
    parser = argparse.ArgumentParser(description="Setup B squeeze bot")
    parser.add_argument("--resume", action="store_true",
                        help="Force resume from today's marker")
    parser.add_argument("--fresh", action="store_true",
                        help="Force cold start, wiping today's session_state_engine/squeeze_bot/")
    args, _ = parser.parse_known_args()

    # We need a session to call decide_boot_mode; build a transient one
    # using the same bot_id the SqueezeBot constructor will use. The
    # SqueezeBot instance later constructs its own EngineSession — both
    # point at the same on-disk directory, so they observe the same
    # marker state.
    session = EngineSession("squeeze_bot")
    if args.fresh:
        # Wipe BEFORE deciding mode so empty-state logic fires cleanly.
        session.scrub_today()
    boot_mode, boot_reason = decide_boot_mode(
        session, fresh=args.fresh, resume=args.resume,
    )
    # Hard gate: WB_SESSION_RESUME_ENABLED=0 forces cold even if a marker
    # is present. Mirrors Setup A's two-gate design.
    if boot_mode == "resume" and not SESSION_RESUME_ENABLED:
        print(f"[SQUEEZE] BOOT: would RESUME (reason={boot_reason}) but "
              f"WB_SESSION_RESUME_ENABLED=0 — forcing COLD", flush=True)
        boot_mode = "cold"
        boot_reason = "resume_gate_off"
    age = session.marker_age_seconds()
    age_str = f"{age:.0f}s" if age is not None else "n/a"
    print(f"[SQUEEZE] BOOT: {boot_mode.upper()} (reason={boot_reason}, "
          f"marker_age={age_str})", flush=True)

    bot = SqueezeBot(boot_mode=boot_mode, boot_reason=boot_reason)
    def _sig(*_):
        print(f"[SQUEEZE] {now_iso_et()} signal received — shutting down",
              flush=True)
        bot.request_shutdown()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    bot.run()


if __name__ == "__main__":
    main()
