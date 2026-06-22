"""move_strike_subbot.py — Setup B paper sub-bot (2026-05-20).

Runs alongside warrior_bot_v2/bot_v3_hybrid.py to A/B-test the MOVE_STRIKE
entry + HWM exit strategy on the SAME tick stream the main bot processes.

Data flow:
    main bot (IBKR) → engine_publisher Unix socket → THIS BOT → Alpaca exec
                                                     ↓
                                             squeeze_detector → movement_strike
                                                     ↓
                                                position open
                                                     ↓
                                              hwm_exit checks per tick

No IBKR session (no 10197 competing-session risk). No second data feed.
Different Alpaca paper account (sub-bot keys) so the A/B is clean.

Scope deliberately narrow:
  - No resume from disk; fresh start each session.
  - One concurrent position (no portfolio cap juggling).
  - Watchlist inferred from incoming tick symbols (no separate poller).
  - No partials / runners — full position closes on first exit signal.

Strategy logic ports cleanly:
  - Arm: SqueezeDetectorV2 (same as main bot)
  - Strike: MovementStrike (2× avg-body anomaly with arm-reset)
  - Exit: HWM trail (25→50% adaptive HH) + stop-prox bail + hard stop

Env contract:
  ENGINE_IPC_SOCKET             — defaults to /tmp/warrior_engine.sock
  WB_BT_MOVE_STRIKE             — must be 1 to enable arm→strike flow
  WB_BT_MOVE_HWM_EXIT           — must be 1 to enable HWM exit
  WB_BT_MOVE_*                  — full HWM/strike config (see hwm_exit.py
                                  and movement_strike.py)
  WB_SUBBOT_APCA_API_KEY_ID     — sub-bot Alpaca paper account
  WB_SUBBOT_APCA_API_SECRET_KEY
  WB_SUBBOT_RISK_DOLLARS        — default $1000 per trade
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

# Load .env BEFORE we read any APCA_API_* env vars. daily_run_v3.sh only
# injects credentials inline for the main bot launch — the sub-bot has
# to source its own (2026-05-21 fix).
from dotenv import load_dotenv
load_dotenv()

# ── Imports of project modules ────────────────────────────────────────
from engine_ipc import (
    DEFAULT_SOCKET_PATH,
    TickMessage,
    decode,
)
from squeeze_detector_v2 import SqueezeDetectorV2 as SqueezeDetector
from movement_strike import MovementStrike
from hwm_exit import HWMExitConfig, evaluate as hwm_evaluate
from bars import TradeBarBuilder

# Alpaca SDK (already in project venv per existing sub-bot)
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce


ET = timezone(timedelta(hours=-4))  # EDT; for May 2026


# ══════════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════════
SOCKET_PATH = os.getenv("ENGINE_IPC_SOCKET", DEFAULT_SOCKET_PATH)
RISK_DOLLARS = float(os.getenv("WB_SUBBOT_RISK_DOLLARS", "1000"))
PROBE_SIZE_MULT = float(os.getenv("WB_SQ_PROBE_SIZE_MULT", "0.5"))
MAX_NOTIONAL = float(os.getenv("WB_MAX_NOTIONAL", "50000"))
MAX_SHARES = int(os.getenv("WB_MAX_SHARES", "100000"))

# ── Strategy filters + sizing (2026-06-17, sub-bot live-validation plan) ──
# All OFF by default; enabled per-variant via daily_run_v3.sh launch env.
#   EQUITY_PCT_SIZING:  0 = off (use RISK_DOLLARS). e.g. 0.70 → each position is
#                       70% of current equity (starting equity + realized daily P&L).
#   ENTRY_BLOCK_WINDOWS_ET: comma list of HH:MM-HH:MM ET windows to BLOCK new
#                       entries (e.g. "09:30-11:00,13:00-14:00" — the open chop +
#                       1pm dead hour where losses cluster). "" = off.
#   SYMBOL_LOSS_LOCKOUT: 1 = once a symbol takes a LOSS today, block all further
#                       entries on it for the rest of the day (kills revenge
#                       re-entries; keeps win-continuations). Full-day; stronger
#                       than the 30-min reentry-loss gate.
EQUITY_PCT_SIZING = float(os.getenv("WB_SUBBOT_EQUITY_PCT", "0"))
ENTRY_BLOCK_WINDOWS_ET = os.getenv("WB_ENTRY_BLOCK_WINDOWS_ET", "").strip()
SYMBOL_LOSS_LOCKOUT = os.getenv("WB_SYMBOL_LOSS_LOCKOUT", "0") == "1"
_SUBBOT_LOG_SUFFIX = os.getenv("WB_SUBBOT_LOG_SUFFIX", "").strip()
LOG_TAG = f"[MOVE_SUB_{_SUBBOT_LOG_SUFFIX}]" if _SUBBOT_LOG_SUFFIX else "[MOVE_SUB]"


def now_iso_et() -> str:
    return datetime.now(ET).strftime("%H:%M:%S")


def now_minute_et() -> int:
    et = datetime.now(ET)
    return et.hour * 60 + et.minute


# ══════════════════════════════════════════════════════════════════════
# REGIME-SHIFT detector (Stage 2 — 2026-05-23)
# ══════════════════════════════════════════════════════════════════════
class RegimeShiftDetector:
    """Per-symbol bar-close anomaly detector. Mirror of
    simulate.SimRegimeShiftDetector — keep parity with that class.

    Per cowork_reports/2026-05-22_regime_shift_stage2_directive.md.
    On each 1-min bar close, computes body / median(last_N closed bar
    bodies). Fires when ratio exceeds threshold AND bar is green
    (close > open). body = bar.high - bar.low (range)."""

    def __init__(
        self,
        ratio_threshold: float = 4.0,
        baseline_bars: int = 5,
        baseline_min: float = 0.02,
        body_min: float = 0.05,
        require_green: bool = True,
    ) -> None:
        from collections import deque
        self.ratio_threshold = ratio_threshold
        self.baseline_bars = baseline_bars
        self.baseline_min = baseline_min
        self.body_min = body_min
        self.require_green = require_green
        self._bar_bodies: deque = deque(maxlen=baseline_bars)

    def check_on_bar_close(self, bar) -> dict:
        try:
            body = float(bar.high) - float(bar.low)
            close_open_signed = float(bar.close) - float(bar.open)
        except Exception:
            return {"fired": False, "body": 0.0, "baseline": 0.0,
                    "ratio": 0.0, "reason": "bar_parse_error"}
        abs_body = abs(body)
        if len(self._bar_bodies) < max(2, self.baseline_bars // 2):
            self._bar_bodies.append(abs_body)
            return {"fired": False, "body": body, "baseline": 0.0,
                    "ratio": 0.0, "reason": "baseline_warmup"}
        bodies_sorted = sorted(self._bar_bodies)
        n = len(bodies_sorted)
        baseline = bodies_sorted[n // 2] if n % 2 == 1 else (
            (bodies_sorted[n // 2 - 1] + bodies_sorted[n // 2]) / 2.0
        )
        self._bar_bodies.append(abs_body)
        if baseline < self.baseline_min:
            return {"fired": False, "body": body, "baseline": baseline,
                    "ratio": 0.0, "reason": "baseline_below_min"}
        if abs_body < self.body_min:
            return {"fired": False, "body": body, "baseline": baseline,
                    "ratio": 0.0, "reason": "body_below_min"}
        ratio = abs_body / baseline
        if ratio < self.ratio_threshold:
            return {"fired": False, "body": body, "baseline": baseline,
                    "ratio": ratio, "reason": "ratio_below_threshold"}
        if self.require_green and close_open_signed <= 0:
            return {"fired": False, "body": body, "baseline": baseline,
                    "ratio": ratio, "reason": "not_green_bar"}
        return {"fired": True, "body": body, "baseline": baseline,
                "ratio": ratio, "reason": None}


# ══════════════════════════════════════════════════════════════════════
# Position state
# ══════════════════════════════════════════════════════════════════════
class SubPosition:
    """Single-position-at-a-time state holder for the sub-bot."""

    __slots__ = (
        "symbol", "entry", "stop", "r", "qty", "score",
        "peak", "peak_time", "cum_low", "entry_time_et",
        "entry_time_min", "hh_count", "prev_bar_high",
        "order_id_buy", "order_id_sell", "is_reentry", "reentry_tag",
        "fill_entry_price", "fill_entry_qty",
        "setup_type", "move_partial_fired", "partial_pnl",
        # Lever 1 (2026-05-26): track exit-in-flight to gate against
        # double-submission when a SELL is still parked at the broker
        # awaiting fill. Set True before submit; cleared on full fill
        # (position itself goes away) or partial/no-fill (retry next tick).
        "exit_pending",
        # Track A (Phase 4): historical entry minute, set only in sim
        # via SubBotSim.replay_ticks. None in live — live uses the
        # wall-clock entry_time_min for age computations. Track A's
        # dispatcher prefers entry_minute_sim when present.
        "entry_minute_sim",
    )

    def __init__(self, symbol: str, entry: float, stop: float, r: float,
                 qty: int, score: float, time_et: str,
                 is_reentry: bool = False, reentry_tag: str = "",
                 setup_type: str = "move_strike"):
        self.symbol = symbol
        self.entry = entry
        self.stop = stop
        self.r = r
        self.qty = qty
        self.score = score
        self.peak = entry
        self.peak_time = time_et
        self.cum_low = entry
        self.entry_time_et = time_et
        et = datetime.now(ET)
        self.entry_time_min = et.hour * 60 + et.minute
        self.entry_minute_sim = None  # only set by SubBotSim in sim
        self.hh_count = 0
        self.prev_bar_high = 0.0
        self.order_id_buy: Optional[str] = None
        self.order_id_sell: Optional[str] = None
        self.is_reentry = is_reentry
        self.reentry_tag = reentry_tag
        # Actual fills (populated by _wait_for_fill after order submit).
        self.fill_entry_price: Optional[float] = None
        self.fill_entry_qty: Optional[int] = None
        # Stage 2 regime-shift fields (2026-05-23). setup_type routes
        # the exit handler; move_partial_fired tracks the 1.5R partial
        # mechanism for regime-shift trades.
        self.setup_type = setup_type
        self.move_partial_fired = False
        self.partial_pnl = 0.0
        self.exit_pending = False


# ══════════════════════════════════════════════════════════════════════
# Sub-bot core
# ══════════════════════════════════════════════════════════════════════
class MoveStrikeSubBot:
    def __init__(self):
        # Per-symbol state
        self.detectors: dict[str, SqueezeDetector] = {}
        self.move_strikes: dict[str, MovementStrike] = {}
        self.prev_arm_state: dict[str, object] = {}
        # Single bar builder driven by all symbols' ticks. Callback wired
        # explicitly per TradeBarBuilder's API.
        self.bar_builder = TradeBarBuilder(
            on_bar_close=self._on_bar_close_internal,
            et_tz=ET,
            interval_seconds=60,
        )
        # Position
        self.position: Optional[SubPosition] = None
        # HWM config (read env once)
        self.hwm_cfg = HWMExitConfig()
        # Movement-strike config
        self.move_lookback = int(os.getenv("WB_BT_MOVE_LOOKBACK", "5"))
        self.move_mult = float(os.getenv("WB_BT_MOVE_MULT", "2.0"))
        self.move_stop_lookback = int(os.getenv("WB_BT_MOVE_STOP_LOOKBACK", "10"))
        self.move_chase_cap_pct = float(os.getenv("WB_BT_MOVE_CHASE_PCT", "2.0"))
        # Alpaca broker
        self.alpaca: Optional[TradingClient] = None
        self._init_alpaca()
        # Daily P&L tracking
        self.daily_pnl = 0.0
        self.daily_trades_closed = 0
        # Strategy filters (2026-06-17 plan). Process restarts daily via cron,
        # so this in-memory state is naturally per-trading-day.
        self._starting_equity = 0.0          # set at Alpaca connect; equity = this + daily_pnl
        self._lossout_symbols: set = set()   # symbols that took a loss today (loss-lockout)
        self._entry_block_windows = []       # [(start_min_et, end_min_et), ...]
        for _w in ENTRY_BLOCK_WINDOWS_ET.split(","):
            _w = _w.strip()
            if not _w or "-" not in _w:
                continue
            try:
                _a, _b = _w.split("-")
                _ah, _am = (int(x) for x in _a.split(":"))
                _bh, _bm = (int(x) for x in _b.split(":"))
                self._entry_block_windows.append((_ah * 60 + _am, _bh * 60 + _bm))
            except Exception:
                print(f"{LOG_TAG} bad WB_ENTRY_BLOCK_WINDOWS_ET segment: {_w!r}", flush=True)
        if self._entry_block_windows or SYMBOL_LOSS_LOCKOUT or EQUITY_PCT_SIZING > 0:
            print(f"{LOG_TAG} filters: equity_pct={EQUITY_PCT_SIZING} "
                  f"block_windows={self._entry_block_windows} "
                  f"loss_lockout={SYMBOL_LOSS_LOCKOUT}", flush=True)
        # Stats
        self.ticks_received = 0
        self.symbols_seen: set[str] = set()
        # Per-symbol HH-count state (only matters once a position is open)
        # We pre-track on each bar so HH is correct at any moment.
        self._sym_prev_bar_high: dict[str, float] = {}
        self._sym_hh_count: dict[str, int] = defaultdict(int)
        # Re-entry config (2026-05-20 deploy) — GREEN mode chosen as winner.
        # BREAK kept gated for future flexibility. Cycle-reset semantics:
        # each fresh MOVE_STRIKE cycle gets its own re-entry budget;
        # re-entries don't.
        self.reentry_green = os.getenv("WB_BT_MOVE_REENTRY_GREEN", "0") == "1"
        self.reentry_break = os.getenv("WB_BT_MOVE_REENTRY_BREAK", "0") == "1"
        self.reentry_lookback = int(os.getenv("WB_BT_MOVE_REENTRY_LOOKBACK", "10"))
        self.reentry_window_min = float(os.getenv("WB_BT_MOVE_REENTRY_WINDOW_MIN", "30"))
        self.reentry_max_per_sym = int(os.getenv("WB_BT_MOVE_REENTRY_MAX_PER_SYM", "1"))
        # Same-bar block (2026-05-21): refuse to re-enter on the bar we
        # just exited. Sim-validated, mirrors Manny's day-trading principle.
        self.reentry_block_same_bar = os.getenv("WB_BT_MOVE_REENTRY_BLOCK_SAME_BAR", "1") == "1"
        # Stay-armed (2026-05-21): after a successful MOVE_STRIKE entry,
        # keep movement_strike monitoring continuously even when the
        # squeeze detector hasn't re-armed. With cool-down + continuation
        # gates to filter chop.
        self.move_stay_armed = os.getenv("WB_BT_MOVE_STAY_ARMED", "0") == "1"
        self.move_stay_armed_cooldown_min = float(os.getenv("WB_BT_MOVE_STAY_ARMED_COOLDOWN_MIN", "15"))
        self.move_stay_armed_min_gap_pct = float(os.getenv("WB_BT_MOVE_STAY_ARMED_MIN_GAP_PCT", "2.0"))
        self._move_stay_armed_symbols: set[str] = set()
        self._move_stay_armed_last_exit_min: dict[str, int] = {}
        self._move_stay_armed_last_exit_price: dict[str, float] = {}
        # Max-below-arm filter (2026-05-21): skip MOVE_STRIKE if price
        # has decayed too far below the real arm (PIII 2026-05-21 was
        # -5.6% below arm). Default 0 = off; set to 3.0 to enable.
        self.move_max_below_arm_pct = float(os.getenv("WB_BT_MOVE_MAX_BELOW_ARM_PCT", "0"))
        # Per-symbol watch state: {symbol → {"high","stop","expires_min"}}
        self._reentry_watches: dict[str, dict] = {}
        # Persistent per-symbol counter — survives watch pop so the cap
        # is enforced across multiple close→watch cycles within one
        # MOVE_STRIKE cycle.
        self._reentry_count_per_symbol: dict[str, int] = {}
        # Per-symbol bar history for re-entry watch snapshot. Deque so
        # we can take the last N efficiently. Bar dicts mirror sim format.
        from collections import deque
        self._bar_history_per_sym: dict[str, deque] = {}
        self._bar_history_maxlen = max(20, self.reentry_lookback * 2)
        # Shutdown
        self._stop = False
        # Diagnostic — how many bars built per symbol
        self._bars_per_sym: dict[str, int] = defaultdict(int)
        # Alpaca-aware limit pricing (2026-05-22). Mirrors main bot's
        # compute_alpaca_aware_limit() helper. Gated by WB_ALPACA_AWARE_LIMITS.
        self.alpaca_aware_limits = os.getenv("WB_ALPACA_AWARE_LIMITS", "0") == "1"
        # engine_seq gap audit (2026-05-22 per engine_seq_audit_directive).
        # Per-symbol last-seen engine_seq → detect dropped ticks from the
        # publisher's overflow path. Cumulative drops surfaced in STATS.
        self.seq_audit_enabled = os.getenv("WB_SUBBOT_SEQ_AUDIT", "1") == "1"
        self._last_engine_seq: dict[str, int] = {}
        self._dropped_tick_count: int = 0
        # Lever 3 (2026-05-26): periodic broker reconciliation.
        self.reconcile_interval_sec = int(os.getenv("WB_RECONCILE_INTERVAL_SEC", "60"))
        self._last_reconcile_at: Optional[float] = None
        # REENTRY-loss-gate (2026-05-27 evening, Variant C live test).
        # Broadened from the earlier HWM-only scope after today's AMSS
        # 15:16 REENTRY GREEN disaster (-$577 in 1 second). The disaster's
        # prior exit was regime_shift_hard_stop, which the HWM-narrow gate
        # missed by one reason-string. The actual failure pattern is
        # "REENTRY GREEN immediately after ANY loss-class exit on the
        # same symbol within WINDOW_MIN" — see
        # cowork_reports/2026-05-27_reentry_loss_gate_broaden_directive.md.
        self.reentry_loss_gate_enabled = (
            os.getenv("WB_MOVE_REENTRY_LOSS_GATE_ENABLED", "0") == "1"
        )
        self.reentry_loss_gate_window_min = float(
            os.getenv("WB_MOVE_REENTRY_LOSS_GATE_WINDOW_MIN", "30")
        )
        # symbol → (exit_reason, exit_minute_et). Populated in _close_position.
        self._last_exit_reason_by_symbol: dict[str, tuple[str, int]] = {}

        # FIRESTORM gate (2026-05-28, Variant A live test). Block entries
        # when the prior completed 1m bar's tick count is below threshold.
        # Hypothesis (validated on live-week 5/26-5/28): the strategy's
        # edge concentrates on high-tick-rate setups; entries on quiet
        # bars are largely random losses. YTD-sim confirms 50% WR at
        # ≥100 ticks/sec vs 19% at <5 ticks/sec — see
        # cowork_reports/2026-05-28_ytd_tick_rate_audit.md (TBD).
        self.firestorm_gate_enabled = (
            os.getenv("WB_MOVE_FIRESTORM_GATE_ENABLED", "0") == "1"
        )
        self.firestorm_gate_min_ticks_per_min = int(
            os.getenv("WB_MOVE_FIRESTORM_GATE_MIN_TICKS_PER_MIN", "6000")
        )
        # Lever 2 (2026-05-26): active cancel + replace on slow exits.
        self.exit_retry_enabled = os.getenv("WB_EXIT_RETRY_ENABLED", "1") == "1"
        self.exit_max_retries = int(os.getenv("WB_EXIT_MAX_RETRIES", "3"))
        self.exit_aggressive_discount_pct = float(os.getenv("WB_EXIT_AGGRESSIVE_DISCOUNT_PCT", "0.005"))
        self.exit_retry_timeout_sec = int(os.getenv("WB_EXIT_RETRY_TIMEOUT_SEC", "10"))
        self.exit_safety_floor_pct = float(os.getenv("WB_EXIT_SAFETY_FLOOR_PCT", "0.50"))

        # --- REGIME-SHIFT Stage 2 (2026-05-23) ---
        # Mirror of simulate.py's regime-shift config. Per
        # cowork_reports/2026-05-22_regime_shift_stage2_directive.md.
        self.regime_shift_enabled = (
            os.getenv("WB_REGIME_SHIFT_ENABLED", "0") == "1"
        )
        self.regime_shift_ratio_threshold = float(
            os.getenv("WB_REGIME_SHIFT_RATIO_THRESHOLD", "4.0")
        )
        self.regime_shift_baseline_bars = int(
            os.getenv("WB_REGIME_SHIFT_BASELINE_BARS", "5")
        )
        self.regime_shift_target_r = float(
            os.getenv("WB_REGIME_SHIFT_TARGET_R", "1.5")
        )
        self.regime_shift_partial_pct = float(
            os.getenv("WB_REGIME_SHIFT_PARTIAL_PCT", "0.9")
        )
        self.regime_shift_require_armed = (
            os.getenv("WB_REGIME_SHIFT_REQUIRE_ARMED", "1") == "1"
        )
        self.regime_shift_require_green_bar = (
            os.getenv("WB_REGIME_SHIFT_REQUIRE_GREEN_BAR", "1") == "1"
        )
        self.regime_shift_runner_stop_to_be = (
            os.getenv("WB_REGIME_SHIFT_RUNNER_STOP_TO_BE", "1") == "1"
        )
        self.regime_shift_max_per_symbol = int(
            os.getenv("WB_REGIME_SHIFT_MAX_PER_SYMBOL", "1")
        )
        # Per-symbol detector + state
        self.regime_shift_detectors: dict[str, RegimeShiftDetector] = {}
        # Symbols that have ARMED (via squeeze detector) earlier today
        self._regime_shift_armed_today: set = set()
        # Per-symbol ET minute when the CURRENT arm fired. Used by the
        # time-window block so a setup that armed in a VALID window can still
        # trigger inside a blocked window (the block targets new in-window
        # setups, not entries from earlier valid arms). Re-arms overwrite it.
        self._arm_minute_et: dict[str, int] = {}
        # Per-symbol entry counter
        self._regime_shift_entries_per_symbol: dict[str, int] = {}

        # --- MOVE_STRIKE Fade-Environment Gate (2026-05-23) ---
        # Mirror of simulate.py's fade-gate logic. Each enabled signal
        # blocks new MOVE_STRIKE entries on that symbol for the rest of
        # the session once triggered. Regime-shift entries are NOT gated.
        # Per cowork_reports/2026-05-23_movestrike_fade_gate_directive.md.
        self.move_fade_vwap_enabled = (
            os.getenv("WB_MOVE_FADE_VWAP_ENABLED", "0") == "1"
        )
        self.move_fade_open_drawdown_pct = float(
            os.getenv("WB_MOVE_FADE_OPEN_DRAWDOWN_PCT", "0")
        )
        self.move_fade_downtrend_bars = int(
            os.getenv("WB_MOVE_FADE_DOWNTREND_BARS", "0")
        )
        self.move_fade_body_cv_threshold = float(
            os.getenv("WB_MOVE_FADE_BODY_CV_THRESHOLD", "0")
        )
        self.move_fade_combine_mode = (
            os.getenv("WB_MOVE_FADE_COMBINE_MODE", "any").lower()
        )
        from collections import deque as _deque_fade
        self._move_fade_session_open: dict[str, float] = {}
        self._move_fade_recent_bars: dict[str, _deque_fade] = {}
        self._move_fade_blocked_symbols: set = set()

    def _wait_for_fill(self, order_id: str, timeout: int = 15):
        """Poll Alpaca for the order's fill. Returns (filled_avg_price, filled_qty)
        or (None, 0) on timeout/cancel/reject. Mirrors bot_v3_hybrid.py:1195
        wait_for_fill pattern."""
        if not order_id:
            return None, 0
        try:
            from alpaca.trading.enums import OrderStatus
        except Exception:
            OrderStatus = None
        for _ in range(timeout * 2):
            try:
                o = self.alpaca.get_order_by_id(order_id)
            except Exception:
                o = None
            if o is not None:
                status = getattr(o, "status", None)
                status_val = status.value if hasattr(status, "value") else str(status)
                if status_val == "filled":
                    return float(o.filled_avg_price or 0), int(o.filled_qty or 0)
                if status_val in ("canceled", "cancelled", "expired", "rejected"):
                    return None, 0
            time.sleep(0.5)
        # Timeout — cancel and final check.
        try:
            self.alpaca.cancel_order_by_id(order_id)
        except Exception:
            pass
        try:
            o = self.alpaca.get_order_by_id(order_id)
        except Exception:
            o = None
        if o is not None:
            status = getattr(o, "status", None)
            status_val = status.value if hasattr(status, "value") else str(status)
            if status_val == "filled":
                return float(o.filled_avg_price or 0), int(o.filled_qty or 0)
        return None, 0

    def _cancel_open_sells(self, symbol: str) -> int:
        """Cancel any open/parked SELL orders for `symbol`, releasing the
        shares they hold (held_for_orders) before we resubmit an exit.

        Fix for the 2026-06-04 FOXX partial oversell loop: a parked partial
        SELL that never filled (and whose timeout-cancel silently failed) kept
        holding shares, so every re-fired partial stacked a 2nd sell that
        Alpaca rejected. Cancel-first makes the resubmit idempotent and
        self-healing. Returns number of orders cancelled.
        """
        if self.alpaca is None:
            return 0
        n = 0
        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            orders = self.alpaca.get_orders(
                filter=GetOrdersRequest(
                    status=QueryOrderStatus.OPEN, symbols=[symbol]
                )
            )
            for o in orders:
                side = getattr(o, "side", None)
                side_val = side.value if hasattr(side, "value") else str(side)
                if side_val.lower() == "sell":
                    try:
                        self.alpaca.cancel_order_by_id(str(o.id))
                        n += 1
                    except Exception:
                        pass
        except Exception as e:
            print(f"{LOG_TAG} PARTIAL CANCEL-OPEN FAIL {symbol}: {e!r}",
                  flush=True)
        if n:
            time.sleep(0.4)  # let the broker release held shares
        return n

    def _broker_available_qty(self, symbol: str) -> Optional[int]:
        """Shares actually sellable right now for `symbol` (broker truth =
        total qty minus held_for_orders). Returns 0 if the broker holds no
        position, or None on a transient read error (caller should not
        over-react to None)."""
        if self.alpaca is None:
            return None
        try:
            pos = self.alpaca.get_open_position(symbol)
        except Exception:
            return 0  # 404 / no position → flat
        try:
            qa = getattr(pos, "qty_available", None)
            if qa is not None:
                return int(float(qa))
            return int(float(pos.qty))
        except (ValueError, TypeError, AttributeError):
            return None

    def _compute_alpaca_aware_limit(self, symbol: str, signal_price: float,
                                     side: str, buffer_pct: float = 0.005) -> float:
        """Sub-bot copy of compute_alpaca_aware_limit (see bot_v3_hybrid.py:2775).
        For BUY: max(signal × (1+buffer), alpaca_ask × (1+buffer)).
        For SELL: min(signal × (1-buffer), alpaca_bid × (1-buffer)).
        Falls back to base on >5% divergence or quote failure."""
        side_u = side.upper()
        base_limit = round(signal_price * (1 + buffer_pct), 2) if side_u == "BUY" \
            else round(signal_price * (1 - buffer_pct), 2)
        if not self.alpaca_aware_limits or self.alpaca_data is None:
            return base_limit
        try:
            from alpaca.data.requests import StockLatestQuoteRequest
            q_resp = self.alpaca_data.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=symbol)
            )
            q = q_resp.get(symbol) if isinstance(q_resp, dict) else None
            if q is None:
                return base_limit
            if side_u == "BUY":
                alpaca_ref = float(q.ask_price) if getattr(q, "ask_price", None) else None
            else:
                alpaca_ref = float(q.bid_price) if getattr(q, "bid_price", None) else None
            if alpaca_ref is None or signal_price <= 0:
                return base_limit
            if abs(alpaca_ref - signal_price) / signal_price > 0.05:
                print(f"{LOG_TAG} ALPACA_QUOTE_DIVERGENT {symbol}: "
                      f"alpaca_ref={alpaca_ref:.4f} signal={signal_price:.4f} "
                      f">5% gap, using base", flush=True)
                return base_limit
            if side_u == "BUY":
                return round(max(base_limit, alpaca_ref * (1 + buffer_pct)), 2)
            return round(min(base_limit, alpaca_ref * (1 - buffer_pct)), 2)
        except Exception as e:
            print(f"{LOG_TAG} ALPACA_AWARE_FAIL {symbol}: {e!r} — using base", flush=True)
            return base_limit

    def _get_current_bid(self, symbol: str) -> Optional[float]:
        """Fetch current bid from Alpaca data API for Lever 2 retry pricing.
        Returns None on quote failure (caller falls back to keep-alive)."""
        if self.alpaca_data is None:
            return None
        try:
            from alpaca.data.requests import StockLatestQuoteRequest
            q_resp = self.alpaca_data.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=symbol)
            )
            q = q_resp.get(symbol) if isinstance(q_resp, dict) else None
            if q is None:
                return None
            bid = float(q.bid_price) if getattr(q, "bid_price", None) else 0.0
            return bid if bid > 0 else None
        except Exception as e:
            print(f"{LOG_TAG} BID FETCH FAIL {symbol}: {e!r}", flush=True)
            return None

    def _init_alpaca(self) -> None:
        key = os.getenv("WB_SUBBOT_APCA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID")
        secret = (
            os.getenv("WB_SUBBOT_APCA_API_SECRET_KEY")
            or os.getenv("APCA_API_SECRET_KEY")
        )
        if not key or not secret:
            print(f"{LOG_TAG} FATAL: no Alpaca credentials in env", flush=True)
            sys.exit(1)
        self.alpaca = TradingClient(key, secret, paper=True)
        # Separate data client for latest-quote lookups (Alpaca-aware
        # limit pricing). Falls back to None if init fails — helper
        # gracefully returns base limit when data_client is None.
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            self.alpaca_data = StockHistoricalDataClient(key, secret)
        except Exception as e:
            print(f"{LOG_TAG} WARN: Alpaca data client init failed: {e!r}", flush=True)
            self.alpaca_data = None
        try:
            acct = self.alpaca.get_account()
            self._starting_equity = float(acct.equity)
            print(
                f"{LOG_TAG} Alpaca PAPER connected — "
                f"account={acct.account_number} equity=${float(acct.equity):,.0f}",
                flush=True,
            )
        except Exception as e:
            print(f"{LOG_TAG} FATAL: Alpaca auth failed: {e!r}", flush=True)
            sys.exit(1)

    # ──────────────────────────────────────────────────────────────────
    # Setup wiring per symbol (lazy on first tick)
    # ──────────────────────────────────────────────────────────────────
    def _ensure_symbol(self, symbol: str) -> None:
        if symbol in self.detectors:
            return
        det = SqueezeDetector()
        det.symbol = symbol
        self.detectors[symbol] = det
        self.move_strikes[symbol] = MovementStrike(
            lookback_bars=self.move_lookback,
            multiplier=self.move_mult,
            stop_lookback_bars=self.move_stop_lookback,
        )
        # Regime-shift detector (Stage 2 — 2026-05-23). Independent of
        # MovementStrike; consumes 1m bar closes via on_bar_close_1m.
        if self.regime_shift_enabled:
            self.regime_shift_detectors[symbol] = RegimeShiftDetector(
                ratio_threshold=self.regime_shift_ratio_threshold,
                baseline_bars=self.regime_shift_baseline_bars,
                require_green=self.regime_shift_require_green_bar,
            )
        self.prev_arm_state[symbol] = None
        self.symbols_seen.add(symbol)
        print(
            f"{LOG_TAG} [{now_iso_et()}] new symbol {symbol} — detector + "
            f"movement_strike instantiated",
            flush=True,
        )
        # Seed from tick cache (2026-05-22 per p0_go_live_stack item 3).
        # If main bot has been running and writing tick_cache for this
        # symbol, replay those ticks through our detector + bar builder
        # so a sub-bot restart mid-session doesn't start blind. Gated by
        # WB_SUBBOT_SEED_FROM_CACHE (default 1).
        if os.getenv("WB_SUBBOT_SEED_FROM_CACHE", "1") == "1":
            self._seed_symbol_from_cache(symbol)

    def _seed_symbol_from_cache(self, symbol: str) -> None:
        """Replay today's tick_cache for `symbol` through the detector +
        bar builder + movement_strike. Mirrors main bot's
        seed_symbol_from_cache (bot_v3_hybrid.py:1823). Idempotent — call
        on first encounter of a symbol after a restart."""
        import gzip
        from datetime import datetime as _dt
        today = _dt.now(ET).strftime("%Y-%m-%d")
        cache_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "tick_cache", today, f"{symbol}.json.gz",
        )
        if not os.path.exists(cache_path):
            return
        try:
            with gzip.open(cache_path, "rt") as f:
                raw_ticks = json.load(f)
        except Exception as e:
            print(f"{LOG_TAG} SEED {symbol} cache read failed: {e!r}", flush=True)
            return
        if not raw_ticks:
            return
        # Cutoff: replay only ticks earlier than NOW (live ticks will
        # cover the rest as they arrive on the engine socket).
        # Overridable for sim use (simulate_subbot.py sets self._seed_cutoff_utc
        # to the replay window's start, so seed loads cache up to window start
        # and the replay loop feeds the rest. Prevents double-counting when
        # cache + live stream overlap).
        now_utc = getattr(self, "_seed_cutoff_utc", None) or _dt.now(timezone.utc)
        replayed = 0
        try:
            det = self.detectors.get(symbol)
            if det is None:
                return
            # Suppress signals during seed if the detector supports it
            # (SqueezeDetector v1 doesn't; v2 has begin_seed/end_seed).
            seed_aware = hasattr(det, "begin_seed") and hasattr(det, "end_seed")
            if seed_aware:
                det.begin_seed()
            for tk in raw_ticks:
                try:
                    price = float(tk["p"])
                    size = int(tk.get("s") or 0)
                    ts_utc = _dt.fromisoformat(tk["t"])
                except (KeyError, ValueError, TypeError):
                    continue
                if ts_utc >= now_utc:
                    break  # don't seed into the future
                try:
                    # TradeBarBuilder.on_trade(symbol, price, size, ts) —
                    # the single shared bar_builder routes by symbol.
                    self.bar_builder.on_trade(symbol, price, size, ts_utc)
                except Exception:
                    pass
                replayed += 1
            if seed_aware:
                det.end_seed()
            print(
                f"{LOG_TAG} SEED {symbol} replayed {replayed:,} ticks from cache",
                flush=True,
            )
        except Exception as e:
            print(f"{LOG_TAG} SEED {symbol} failed: {e!r}", flush=True)

    # ──────────────────────────────────────────────────────────────────
    # Fade-environment gate (Stage parallel — 2026-05-23)
    # Mirror of simulate.py logic. Maintains per-symbol session_open and
    # last-10 (open, close) bars; helper returns block/reason.
    # ──────────────────────────────────────────────────────────────────
    def update_fade_environment_state(self, symbol: str, bar) -> None:
        if symbol not in self._move_fade_session_open:
            self._move_fade_session_open[symbol] = float(bar.open)
        from collections import deque as _deque
        dq = self._move_fade_recent_bars.get(symbol)
        if dq is None:
            dq = _deque(maxlen=10)
            self._move_fade_recent_bars[symbol] = dq
        dq.append((float(bar.open), float(bar.close)))

    def is_in_fade_environment(self, symbol: str, price: float,
                                vwap: Optional[float]):
        """Returns (blocked, reason). Sticky once triggered."""
        if symbol in self._move_fade_blocked_symbols:
            return (True, "session-blocked")
        vwap_on = self.move_fade_vwap_enabled
        dd_on = self.move_fade_open_drawdown_pct > 0
        dt_on = self.move_fade_downtrend_bars > 0
        cv_on = self.move_fade_body_cv_threshold > 0
        enabled_count = int(vwap_on) + int(dd_on) + int(dt_on) + int(cv_on)
        if enabled_count == 0:
            return (False, "")
        signals = []
        if vwap_on and vwap is not None and vwap > 0:
            if price < vwap:
                signals.append("vwap")
        if dd_on:
            open_px = self._move_fade_session_open.get(symbol, 0.0)
            if open_px > 0:
                dd_pct = (open_px - price) / open_px * 100.0
                if dd_pct >= self.move_fade_open_drawdown_pct:
                    signals.append("drawdown")
        if dt_on:
            bars = self._move_fade_recent_bars.get(symbol)
            n = self.move_fade_downtrend_bars
            if bars is not None and len(bars) >= n:
                last_n = list(bars)[-n:]
                all_red = all(c < o for (o, c) in last_n)
                closes = [c for (_o, c) in last_n]
                desc = all(closes[i] < closes[i - 1] for i in range(1, n))
                if all_red and desc:
                    signals.append("downtrend")
        if cv_on:
            bars = self._move_fade_recent_bars.get(symbol)
            if bars is not None and len(bars) >= 10:
                bodies = [abs(c - o) for (o, c) in bars]
                try:
                    import statistics as _stats
                    m = _stats.mean(bodies)
                    if m > 0:
                        s = _stats.stdev(bodies)
                        if s / m > self.move_fade_body_cv_threshold:
                            signals.append("cv")
                except Exception:
                    pass
        if not signals:
            return (False, "")
        if self.move_fade_combine_mode == "all":
            if len(signals) == enabled_count:
                self._move_fade_blocked_symbols.add(symbol)
                return (True, "+".join(signals))
            return (False, "")
        self._move_fade_blocked_symbols.add(symbol)
        return (True, "+".join(signals))

    # ──────────────────────────────────────────────────────────────────
    # Bar-close hook (called by TradeBarBuilder when a 1m bar closes)
    # ──────────────────────────────────────────────────────────────────
    def _on_bar_close_internal(self, bar) -> None:
        """TradeBarBuilder calls this with a Bar dataclass.
        We dispatch to the per-symbol handler."""
        try:
            self.on_bar_close_1m(bar.symbol, bar)
        except Exception as e:
            print(
                f"{LOG_TAG} on_bar_close_1m error {bar.symbol}: {e!r}", flush=True
            )

    def on_bar_close_1m(self, symbol: str, bar) -> None:
        """``bar`` is a Bar dataclass with .open/.high/.low/.close/.volume."""
        self._bars_per_sym[symbol] += 1
        self._ensure_symbol(symbol)
        # Fade-gate per-bar state update (2026-05-23). Tracks first-bar
        # open + rolling (open, close) deque for the entry-time fade check.
        self.update_fade_environment_state(symbol, bar)
        det = self.detectors[symbol]
        try:
            vwap = self.bar_builder.get_vwap(symbol)
        except Exception:
            vwap = None
        # Feed the detector — this can set det.armed if conditions met.
        # Detector reads bar.open/high/low/close/volume directly.
        try:
            det.on_bar_close_1m(bar, vwap=vwap)
        except Exception as e:
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} det.on_bar_close error: {e!r}",
                flush=True,
            )
        # Detect arm transition (None → armed) to reset movement_strike
        prev = self.prev_arm_state.get(symbol)
        if det.armed is not None and prev is None:
            self.move_strikes[symbol].reset_history()
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} ARMED "
                f"entry={det.armed.trigger_high:.4f} stop={det.armed.stop_low:.4f} "
                f"R={det.armed.r:.4f} score={det.armed.score:.1f} — "
                f"movement_strike history reset",
                flush=True,
            )
            # Track for regime-shift require_armed gate.
            if self.regime_shift_enabled:
                self._regime_shift_armed_today.add(symbol)
            # Stamp the arm time for the time-window block (gate on arm, not
            # entry). Use the BAR's ET time, not wall-clock, so a seed/replay
            # restart re-stamps the true historical arm minute (not "now").
            try:
                _bar_et = bar.start_utc.astimezone(ET)
                self._arm_minute_et[symbol] = _bar_et.hour * 60 + _bar_et.minute
            except Exception:
                self._arm_minute_et[symbol] = now_minute_et()
        self.prev_arm_state[symbol] = det.armed

        # HH tracking — global per-symbol (for an active position's exit)
        if self._sym_prev_bar_high.get(symbol, 0) > 0:
            if bar.high > self._sym_prev_bar_high[symbol]:
                self._sym_hh_count[symbol] += 1
            else:
                self._sym_hh_count[symbol] = 0
        self._sym_prev_bar_high[symbol] = bar.high

        # Update active position's HH counter if this is the held symbol
        if self.position is not None and self.position.symbol == symbol:
            self.position.hh_count = self._sym_hh_count[symbol]

        # Per-symbol bar history for re-entry watch snapshot.
        from collections import deque
        if symbol not in self._bar_history_per_sym:
            self._bar_history_per_sym[symbol] = deque(maxlen=self._bar_history_maxlen)
        self._bar_history_per_sym[symbol].append({
            "o": bar.open, "h": bar.high, "l": bar.low,
            "c": bar.close, "v": bar.volume,
        })

        # GREEN re-entry trigger: at bar close, if no position AND watch
        # exists for this symbol AND bar is green (close > open) → fire.
        if (self.position is None and self.reentry_green
                and symbol in self._reentry_watches
                and bar.close > bar.open):
            self._try_fire_green_reentry(symbol, bar)

        # REGIME-SHIFT detection (Stage 2 — 2026-05-23). Second-order
        # body anomaly on bar close. Skips if any position is open.
        # Skips if symbol has not armed today (require_armed gate).
        # Per-symbol max-1 by default.
        if self.regime_shift_enabled and self.position is None:
            rs_det = self.regime_shift_detectors.get(symbol)
            if rs_det is not None:
                # Past entry-time cutoff?
                _cutoff = os.getenv("WB_ENTRY_TIME_CUTOFF_ET", "19:30")
                try:
                    _ch, _cm = (int(x) for x in _cutoff.split(":")[:2])
                    _past_cutoff = now_minute_et() >= _ch * 60 + _cm
                except Exception:
                    _past_cutoff = False
                if not _past_cutoff:
                    self._maybe_fire_regime_shift(symbol, bar, rs_det)

    # ──────────────────────────────────────────────────────────────────
    # Per-tick processing
    # ──────────────────────────────────────────────────────────────────
    def _current_min_for_age(self) -> int:
        """Return the minute-of-day used by Track A's position-age
        calculations. Default: now_minute_et() (live wall clock).
        SubBotSim overrides this to return the historical sim minute
        so age computations work correctly during backtest replay."""
        return now_minute_et()

    def on_tick(self, symbol: str, price: float, ts_iso: str, size: int) -> None:
        self.ticks_received += 1
        self._ensure_symbol(symbol)
        # Bar builder needs a datetime, not the ISO string
        try:
            ts = datetime.fromisoformat(ts_iso)
        except Exception:
            ts = datetime.now(timezone.utc)
        # Feed the bar builder (triggers our on_bar_close_1m via callback)
        try:
            self.bar_builder.on_trade(symbol, price, size, ts)
        except Exception as e:
            print(
                f"{LOG_TAG} bar_builder error on {symbol}: {e!r}", flush=True
            )

        # If we have an open position, run HWM exit checks
        if self.position is not None and self.position.symbol == symbol:
            self._maintain_position(price)
            # If we just closed in _maintain_position, return — don't
            # also evaluate a new entry on the same tick.
            if self.position is None:
                return

        # If no position, check for new entry
        if self.position is None:
            self._maybe_enter(symbol, price)

    # ──────────────────────────────────────────────────────────────────
    # Re-entry helpers (GREEN mode + cycle reset, 2026-05-20)
    # ──────────────────────────────────────────────────────────────────
    def _register_reentry_watch(self, t: SubPosition) -> None:
        """Called after a position closes. Sets up a re-entry watch if
        the cap allows. Cycle semantics: a fresh MOVE_STRIKE exit resets
        the per-symbol count to 0 (new cycle); a re-entry exit does not."""
        if not (self.reentry_green or self.reentry_break):
            return
        # Cycle reset on fresh MOVE_STRIKE (non-reentry) exit
        if not t.is_reentry:
            self._reentry_count_per_symbol[t.symbol] = 0
        # Cap check
        if self._reentry_count_per_symbol.get(t.symbol, 0) >= self.reentry_max_per_sym:
            return
        bars = self._bar_history_per_sym.get(t.symbol)
        if not bars:
            return
        last_n = list(bars)[-self.reentry_lookback:]
        if len(last_n) < 3:
            return
        high = max(b["h"] for b in last_n)
        low = min(b["l"] for b in last_n)
        self._reentry_watches[t.symbol] = {
            "high": high,
            "stop": low,
            "expires_min": now_minute_et() + self.reentry_window_min,
            # Same-bar guard: this minute is the exit bar. Block any
            # re-entry attempt that fires before bar_minute advances.
            "exit_bar_minute": now_minute_et(),
        }
        print(
            f"{LOG_TAG} [{now_iso_et()}] {t.symbol} REENTRY WATCH set: "
            f"high={high:.3f} stop={low:.3f} "
            f"expires_in={int(self.reentry_window_min)}min",
            flush=True,
        )

    def _try_fire_green_reentry(self, symbol: str, bar) -> None:
        """At bar close, if watch exists and bar is green, fire re-entry."""
        watch = self._reentry_watches.get(symbol)
        if watch is None:
            return
        cur_min = now_minute_et()
        if cur_min > watch["expires_min"]:
            self._reentry_watches.pop(symbol, None)
            return
        # Same-bar guard — don't re-enter on the bar we just exited.
        if (self.reentry_block_same_bar
                and cur_min <= watch.get("exit_bar_minute", -1)):
            return
        # Guard: bar.close must clear the snapshotted stop (otherwise
        # we'd immediately stop out).
        if bar.close <= watch["stop"]:
            return
        # REENTRY-loss-gate (2026-05-27 evening, Variant C live test):
        # block REENTRY GREEN when the most-recent exit on this symbol
        # was a LOSS-CLASS exit within WINDOW_MIN. Broadened from the
        # earlier HWM-only scope after today's AMSS 15:16 disaster
        # (-$577 in 1 second after a regime_shift_hard_stop). False
        # negatives (gate doesn't fire when it should) recover on
        # the next cycle; false positives silently kill winners,
        # so the list is explicit prefixes only.
        if self.reentry_loss_gate_enabled:
            prev = self._last_exit_reason_by_symbol.get(symbol)
            if prev is not None:
                prev_reason, prev_min = prev
                window_age = cur_min - prev_min
                if (window_age <= self.reentry_loss_gate_window_min
                        and (prev_reason.startswith("move_hwm_exit")
                             or prev_reason.startswith("move_stop_prox_bail")
                             or prev_reason.startswith("move_hard_stop")
                             or prev_reason.startswith("regime_shift_hard_stop"))):
                    print(
                        f"{LOG_TAG} [{now_iso_et()}] REENTRY_LOSS_GATE_BLOCK "
                        f"{symbol} reason={prev_reason} "
                        f"window_age_min={window_age}",
                        flush=True,
                    )
                    # Pop the watch — gate is decisive for this cycle.
                    self._reentry_watches.pop(symbol, None)
                    return
        entry_price = bar.close
        stop = watch["stop"]
        r = entry_price - stop
        if r <= 0:
            return
        qty = self._compute_qty(entry_price, r, 99.0)
        if qty <= 0:
            return
        # Open re-entry position. Same code path as primary open but
        # tagged so the close handler knows not to reset the count.
        self._open_position_with_tag(
            symbol, entry_price, stop, r, qty, 99.0,
            is_reentry=True, reentry_tag="GREEN",
        )
        self._reentry_count_per_symbol[symbol] = (
            self._reentry_count_per_symbol.get(symbol, 0) + 1
        )
        self._reentry_watches.pop(symbol, None)

    def _maybe_eod_flatten(self) -> None:
        """Wall-clock EOD force-flatten — fires independently of whether the
        held symbol is still ticking.

        Fix for the 2026-06-04 STI overnight hold: the tick-driven flatten in
        _maintain_position never ran because STI's last tick was 16:44 ET, ~3h
        before the 19:30 cutoff, so the position carried overnight on A and C.
        This is called from the consume() loop's periodic path (and on socket
        timeouts), so a quiet symbol no longer slips past the cutoff. Uses a
        live broker bid for the exit ref (engine ticks may be silent), falling
        back to last peak/entry. Gated by WB_EOD_FORCE_FLATTEN_ENABLED like the
        tick-driven path; _close_position is oversell-safe.
        """
        p = self.position
        if p is None:
            return
        if os.getenv("WB_EOD_FORCE_FLATTEN_ENABLED", "0") != "1":
            return
        try:
            _ffh, _ffm = (int(x) for x in os.getenv(
                "WB_EOD_FORCE_FLATTEN_TIME_ET", "19:30").split(":")[:2])
        except Exception:
            return
        if now_minute_et() < _ffh * 60 + _ffm:
            return
        ref = self._get_current_bid(p.symbol)
        if ref is None or ref <= 0:
            ref = p.peak or p.fill_entry_price or p.entry
        print(
            f"{LOG_TAG} [{now_iso_et()}] EOD HEARTBEAT FLATTEN {p.symbol} "
            f"(wall-clock trigger — symbol may be quiet) ref=${ref:.4f}",
            flush=True,
        )
        self._close_position("eod_force_flatten", ref)

    def _maintain_position(self, price: float) -> None:
        p = self.position
        # Universal EOD force-flatten (2026-06-02): independent of Track A AND
        # setup_type, so NOTHING is carried overnight. The old force-flatten was
        # Track-A-only + regime/firestorm-only, so orphan_adopted residuals (e.g.
        # PRFX, held for days through its $4.75 stop down to $1.92) survived.
        # Fires on the first tick at/after the cutoff. Default OFF (preserves
        # sim/backtest reproducibility); daily_run_v3.sh sets =1 for live. Time
        # defaults to the 19:30 ET entry cutoff.
        if os.getenv("WB_EOD_FORCE_FLATTEN_ENABLED", "0") == "1":
            try:
                _ffh, _ffm = (int(x) for x in os.getenv(
                    "WB_EOD_FORCE_FLATTEN_TIME_ET", "19:30").split(":")[:2])
                if now_minute_et() >= _ffh * 60 + _ffm:
                    self._close_position("eod_force_flatten", price)
                    return
            except Exception:
                pass
        if price > p.peak:
            p.peak = price
            p.peak_time = now_iso_et()
        if price < p.cum_low:
            p.cum_low = price
        # Sync HH count from per-symbol tracker (updated on bar closes)
        p.hh_count = self._sym_hh_count.get(p.symbol, 0)

        # Regime-shift positions: pre-partial uses hard-stop + 1.5R target
        # only. HWM trail is suppressed until partial fires (sim parity —
        # PCLA-class trades need runway). After partial fires, runner is
        # managed by hwm_evaluate at BE stop.
        # FIRESTORM_TRIGGER (Phase 3 Stage 1, sim-only) reuses the same
        # exit framework — dispatcher broadened to accept either setup_type.
        # Bit-identical to pre-FT live behavior because live never produces
        # firestorm_trigger positions.
        if (p.setup_type in ("regime_shift", "firestorm_trigger")
                and not p.move_partial_fired):
            # Track A (Phase 4, env-gated, applies to BOTH regime_shift
            # AND firestorm_trigger): phased drawdown floor replaces the
            # hard stop. Three-phase schedule by position age (default
            # 50%/30%/20% with 15/45 min boundaries). Plus force-flatten
            # at WB_EXIT_FORCE_FLATTEN_TIME (default 15:30 ET).
            #
            # Stage 1.5 fallback (sim-only): if Track A is OFF and the
            # FT-specific drawdown var is set, use that single static
            # threshold. Preserves Stage 1.5 sweep reproducibility.
            #
            # Default (both Track A and Stage 1.5 vars off): original
            # hard stop. Bit-identical to pre-Track-A live behavior.
            from exit_track_a import (
                track_a_enabled, phased_drawdown_threshold,
                should_force_flatten,
            )
            if track_a_enabled():
                # Force-flatten check first (overrides drawdown floor).
                # _current_min_for_age() is polymorphic — wall clock in
                # live, historical minute in sim. See SubBotSim override.
                cur_min = self._current_min_for_age()
                if should_force_flatten(cur_min):
                    self._close_position(
                        f"{p.setup_type}_force_flatten", price)
                    return
                # Phased drawdown floor based on position age.
                # Sim sets entry_minute_sim to the historical minute via
                # the SubBotSim.replay_ticks transition logic; live
                # leaves it None and uses the wall-clock entry_time_min.
                entry_min = (p.entry_minute_sim
                             if p.entry_minute_sim is not None
                             else p.entry_time_min)
                age_min = max(0, cur_min - entry_min)
                dd_threshold = phased_drawdown_threshold(age_min)
                drawdown = (
                    (p.entry - price) / p.entry if p.entry > 0 else 0
                )
                if dd_threshold > 0 and drawdown >= dd_threshold:
                    self._close_position(
                        f"{p.setup_type}_drawdown_floor", price)
                    return
            else:
                # Stage 1.5 fallback or default hard-stop path.
                ft_dd_floor_pct = float(
                    os.getenv("WB_FT_DRAWDOWN_FLOOR_PCT", "0")
                ) if p.setup_type == "firestorm_trigger" else 0.0
                if ft_dd_floor_pct > 0:
                    drawdown = (
                        (p.entry - price) / p.entry if p.entry > 0 else 0
                    )
                    if drawdown >= ft_dd_floor_pct:
                        self._close_position(
                            "firestorm_trigger_drawdown_floor", price)
                        return
                else:
                    # Hard stop (default behavior — bit-identical to
                    # pre-Stage-1.5 live behavior).
                    if price <= p.stop:
                        self._close_position(
                            f"{p.setup_type}_hard_stop", price)
                        return
            # Target = entry + target_R * R. Fire partial when crossed.
            target_price = p.entry + self.regime_shift_target_r * p.r
            if price >= target_price:
                self._fire_regime_shift_partial(p, price)
            return  # no trail pre-partial

        # Hard-stop safety net for setups WITHOUT their own pre-partial stop
        # management (notably orphan_adopted). regime_shift/firestorm handle their
        # stop in the branch above; everything else used to fall straight to
        # hwm_evaluate, which only trails AFTER +min_gain profit — so a losing
        # orphan (PRFX 2026-06-02: held through its $4.75 stop to $1.92) never
        # exited. Enforce the hard stop here. Default OFF (preserves sim/backtest
        # reproducibility); daily_run_v3.sh sets =1 for live.
        if (os.getenv("WB_ORPHAN_HARD_STOP_ENABLED", "0") == "1"
                and p.setup_type not in ("regime_shift", "firestorm_trigger")
                and price <= p.stop):
            self._close_position(f"{p.setup_type}_hard_stop", price)
            return

        decision = hwm_evaluate(p, price, now_minute_et(), self.hwm_cfg)
        if decision is None:
            return
        reason, exit_price = decision
        self._close_position(reason, exit_price)

    # ──────────────────────────────────────────────────────────────────
    # REGIME-SHIFT entry + partial mechanism (Stage 2 — 2026-05-23)
    # ──────────────────────────────────────────────────────────────────
    def _strategy_filters_block(self, symbol: str, setup_label: str) -> bool:
        """Plan filters (2026-06-17). Return True to block this entry.

        (1) Time-window block: skip entries inside configured ET windows (the
            cash open + 1pm dead hour, where losses cluster).
        (2) Per-symbol same-day loss-lockout: once a symbol takes a loss today,
            block further entries on it (revenge re-entries lose 64-83%).
        Both gated; no-op unless enabled via env. Called at every order path."""
        if self._entry_block_windows:
            # Gate on ARM time, not entry time: a setup that armed in a valid
            # window may still trigger inside a blocked window (per Manny
            # 2026-06-22 — NXTS armed 08:48 valid, triggered in the 09:30-11:00
            # block, and should have been allowed). Only setups that ARMED
            # inside a window are new in-window setups → blocked. Fall back to
            # current time if no arm stamp (e.g. non-MOVE_STRIKE paths).
            arm_m = self._arm_minute_et.get(symbol)
            check_m = arm_m if arm_m is not None else now_minute_et()
            for s, e in self._entry_block_windows:
                if s <= check_m < e:
                    src = "armed_at" if arm_m is not None else "now"
                    print(f"{LOG_TAG} [{now_iso_et()}] {symbol} TIME_WINDOW_BLOCK "
                          f"{setup_label} ({src}={check_m} in {s}-{e})", flush=True)
                    return True
        if SYMBOL_LOSS_LOCKOUT and symbol in self._lossout_symbols:
            print(f"{LOG_TAG} [{now_iso_et()}] {symbol} LOSS_LOCKOUT_BLOCK "
                  f"{setup_label} (symbol already lost today)", flush=True)
            return True
        return False

    def _firestorm_gate_blocks(self, symbol: str, setup: str) -> bool:
        """Return True if the FIRESTORM gate should block this entry.

        Reads the last completed 1m bar's tick count from the bar
        builder. If below threshold (default 6000 = 100/sec × 60), block.
        Logs FIRESTORM_GATE_BLOCK on block. No-op if gate disabled.
        """
        if not self.firestorm_gate_enabled:
            return False
        tc = self.bar_builder.get_last_completed_bar_tick_count(symbol)
        if tc >= self.firestorm_gate_min_ticks_per_min:
            return False
        print(
            f"{LOG_TAG} [{now_iso_et()}] FIRESTORM_GATE_BLOCK {symbol} "
            f"setup={setup} prior_bar_ticks={tc} "
            f"threshold={self.firestorm_gate_min_ticks_per_min}",
            flush=True,
        )
        return True

    def _maybe_fire_regime_shift(self, symbol: str, bar,
                                  rs_det: RegimeShiftDetector) -> None:
        """Run the regime-shift detector on this 1m bar close. If it
        fires AND all gates pass, open a regime-shift position."""
        rs_result = rs_det.check_on_bar_close(bar)
        if not rs_result.get("fired"):
            return
        # require_armed gate — only fire on symbols that have armed for
        # MOVE_STRIKE earlier today.
        if (self.regime_shift_require_armed
                and symbol not in self._regime_shift_armed_today):
            return
        # Per-symbol entry cap
        cur = self._regime_shift_entries_per_symbol.get(symbol, 0)
        if cur >= self.regime_shift_max_per_symbol:
            return
        # FIRESTORM gate — block entries on quiet bars (Variant A test).
        if self._firestorm_gate_blocks(symbol, "regime_shift"):
            return
        # Plan filters (time-window block + per-symbol loss-lockout).
        if self._strategy_filters_block(symbol, "regime_shift"):
            return
        # Trigger event log
        print(
            f"{LOG_TAG} [{now_iso_et()}] REGIME_SHIFT_TRIGGER {symbol} "
            f"bar_body=${rs_result['body']:.4f} "
            f"baseline=${rs_result['baseline']:.4f} "
            f"ratio={rs_result['ratio']:.2f}",
            flush=True,
        )
        self._open_regime_shift_position(symbol, bar, rs_result)

    def _open_regime_shift_position(self, symbol: str, bar, rs_result) -> None:
        """Open a regime-shift position. Entry = bar.close, stop = bar.low.
        R = entry - stop. Probe-sized qty. Alpaca-aware limit. Sets
        setup_type='regime_shift' so _maintain_position routes through
        the partial mechanism.

        Track A (Phase 4, env-gated): R floor on the stop placement.
        When WB_EXIT_TRACK_A_ENABLED=1, the raw stop = bar.low is widened
        if R is below the configured floor (default max($0.10, 5% of
        entry)). Default OFF — bit-identical to pre-Track-A behavior."""
        entry = float(bar.close)
        raw_stop = float(bar.low)
        from exit_track_a import compute_stop_with_r_floor
        stop, r = compute_stop_with_r_floor(entry, raw_stop)
        if r <= 0.01:
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} regime_shift skip — "
                f"r={r:.4f} too small",
                flush=True,
            )
            return
        qty = self._compute_qty(entry, r, 99.0)
        if qty <= 0:
            return
        # Alpaca-aware buy limit, mirroring _open_position_with_tag.
        slip = max(0.07, entry * 0.01)
        base_limit = round(entry + slip, 2)
        aware_limit = self._compute_alpaca_aware_limit(symbol, entry, "BUY")
        limit = max(aware_limit, base_limit)
        print(
            f"{LOG_TAG} [{now_iso_et()}] 🚀 ENTRY REGIME_SHIFT {symbol} "
            f"qty={qty} limit=${limit:.2f} (anomaly@${entry:.2f}) "
            f"stop=${stop:.2f} R=${r:.4f} "
            f"body=${rs_result['body']:.4f} ratio={rs_result['ratio']:.2f}",
            flush=True,
        )
        try:
            req = LimitOrderRequest(
                symbol=symbol, qty=qty, side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY, limit_price=limit,
                extended_hours=True,
            )
            order = self.alpaca.submit_order(order_data=req)
        except Exception as e:
            print(f"{LOG_TAG} REGIME_SHIFT ENTRY REJECT {symbol}: {e!r}",
                  flush=True)
            return
        self.position = SubPosition(
            symbol=symbol, entry=entry, stop=stop, r=r, qty=qty,
            score=99.0, time_et=now_iso_et(),
            is_reentry=False, reentry_tag="",
            setup_type="regime_shift",
        )
        self.position.order_id_buy = str(order.id) if hasattr(order, "id") else None
        fill_px, fill_qty = self._wait_for_fill(self.position.order_id_buy, timeout=15)
        if fill_px is not None and fill_qty > 0:
            self.position.fill_entry_price = fill_px
            self.position.fill_entry_qty = fill_qty
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} regime_shift entry "
                f"FILLED @ ${fill_px:.4f} qty={fill_qty} (limit was ${limit:.2f})",
                flush=True,
            )
            if fill_qty < qty:
                self.position.qty = fill_qty
            # Bump the per-symbol counter on a real fill so partial fills
            # don't burn the cap.
            self._regime_shift_entries_per_symbol[symbol] = (
                self._regime_shift_entries_per_symbol.get(symbol, 0) + 1
            )
        else:
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} regime_shift entry "
                f"NOT FILLED (timeout/cancel/reject) — abandoning trade",
                flush=True,
            )
            self.position = None
            return
        self.position.hh_count = self._sym_hh_count.get(symbol, 0)

    def _fire_regime_shift_partial(self, p: "SubPosition", price: float) -> None:
        """Sell partial_pct of the position at entry + target_R*R - slip.
        After fill: raise stop to BE, mark move_partial_fired=True,
        runner continues with HWM trail."""
        partial_qty = max(1, int(round(p.qty * self.regime_shift_partial_pct)))
        if p.qty > 1:
            # Always leave at least 1 share as runner.
            partial_qty = min(partial_qty, p.qty - 1)
        runner_qty = p.qty - partial_qty

        # ── SAFE RESUBMIT (fix: 2026-06-04 FOXX partial oversell loop) ──────
        # This partial re-fires on every target-cross tick until move_partial_
        # fired flips True (only on a real fill). If a prior partial SELL is
        # parked-unfilled at the broker it still holds shares (held_for_orders),
        # so a fresh full-size partial stacks on top and Alpaca rejects it with
        # "insufficient qty available" — and, after a manual flatten, with
        # "cannot be sold short" — looping forever (21,945× on FOXX). Cancel any
        # open SELL for this symbol to release the shares, then size to the
        # broker's ACTUAL available qty so we can never over-sell. Gate defaults
        # ON; set WB_MOVE_PARTIAL_SAFE_RESUBMIT=0 to revert to legacy behavior.
        if os.getenv("WB_MOVE_PARTIAL_SAFE_RESUBMIT", "1") == "1":
            self._cancel_open_sells(p.symbol)
            avail = self._broker_available_qty(p.symbol)
            if avail is not None:
                if avail <= 0:
                    # Broker flat / position closing elsewhere — nothing to
                    # sell. Don't spam; reconcile clears local state.
                    print(
                        f"{LOG_TAG} [{now_iso_et()}] PARTIAL SKIP {p.symbol}: "
                        f"broker available qty={avail} (flat/closing) — "
                        f"deferring to reconcile",
                        flush=True,
                    )
                    return
                capped = min(partial_qty, avail - 1) if avail > 1 else avail
                capped = max(1, capped)
                if capped != partial_qty:
                    print(
                        f"{LOG_TAG} [{now_iso_et()}] PARTIAL QTY CAP {p.symbol}: "
                        f"{partial_qty}→{capped} (broker available={avail})",
                        flush=True,
                    )
                partial_qty = capped
                runner_qty = max(0, avail - partial_qty)
        # Sell limit: floor at entry + 1.5R - slip (don't price above
        # current price — that would never fill).
        slip = max(0.05, price * 0.005)
        target_limit = round(p.entry + self.regime_shift_target_r * p.r - slip, 2)
        # Tighten toward alpaca_bid via aware-limit helper.
        aware_limit = self._compute_alpaca_aware_limit(p.symbol, price, "SELL")
        limit = min(aware_limit, target_limit, round(price - slip, 2))
        print(
            f"{LOG_TAG} [{now_iso_et()}] 🎯 PARTIAL REGIME_SHIFT {p.symbol} "
            f"qty={partial_qty} limit=${limit:.2f} "
            f"(target={self.regime_shift_target_r}R={p.entry + self.regime_shift_target_r*p.r:.2f}, "
            f"runner={runner_qty})",
            flush=True,
        )
        try:
            req = LimitOrderRequest(
                symbol=p.symbol, qty=partial_qty, side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY, limit_price=limit,
                extended_hours=True,
            )
            order = self.alpaca.submit_order(order_data=req)
        except Exception as e:
            print(f"{LOG_TAG} PARTIAL REJECT {p.symbol}: {e!r}", flush=True)
            return
        order_id = str(order.id) if hasattr(order, "id") else None
        fill_px, fill_qty = self._wait_for_fill(order_id, timeout=15)
        if fill_px is None or fill_qty <= 0:
            # Partial order didn't fill — keep position intact, will
            # re-try on next tick that exceeds target.
            print(
                f"{LOG_TAG} [{now_iso_et()}] {p.symbol} regime_shift partial "
                f"NOT FILLED — will retry on next target-cross tick",
                flush=True,
            )
            return
        # Real-fill P&L for the partial leg.
        cost_basis = float(p.fill_entry_price or p.entry)
        partial_pnl = (fill_px - cost_basis) * fill_qty
        p.partial_pnl = partial_pnl
        self.daily_pnl += partial_pnl
        print(
            f"{LOG_TAG} [{now_iso_et()}] {p.symbol} partial FILLED @ ${fill_px:.4f} "
            f"qty={fill_qty} pnl=${partial_pnl:+,.2f}",
            flush=True,
        )
        # Shrink position to runner, raise stop to BE.
        p.qty = p.qty - fill_qty
        if self.regime_shift_runner_stop_to_be:
            p.stop = float(p.fill_entry_price or p.entry)
        p.move_partial_fired = True
        # Reset peak so HWM trail starts from current price (post-partial
        # — the runner's HWM should track from here, not from pre-partial
        # peak which is already booked).
        p.peak = price
        p.cum_low = price

    def _maybe_enter(self, symbol: str, price: float) -> None:
        det = self.detectors.get(symbol)
        if det is None:
            return
        # Entry-time cutoff (2026-05-22 Manny directive: no new entries
        # after 19:30 ET). Mirrors main bot's WB_ENTRY_TIME_CUTOFF_ET
        # at bot_v3_hybrid.py:223. PCLA 2026-05-22 19:55 entry triggered
        # this rule — 25 min past cutoff, forced flatten.
        _cutoff = os.getenv("WB_ENTRY_TIME_CUTOFF_ET", "19:30")
        try:
            _ch, _cm = (int(x) for x in _cutoff.split(":")[:2])
            _now_min = now_minute_et()
            if _now_min >= _ch * 60 + _cm:
                return  # past entry cutoff
        except Exception:
            pass  # bad cutoff value — allow entry
        # Real arm OR stay-armed mode (no detector arm, but symbol
        # previously fired MOVE_STRIKE today).
        has_real_arm = det.armed is not None
        stay_armed_active = (
            not has_real_arm
            and self.move_stay_armed
            and symbol in self._move_stay_armed_symbols
        )
        if not (has_real_arm or stay_armed_active):
            return
        ms = self.move_strikes[symbol]
        bar_minute = now_minute_et()
        if not ms.update_and_check(price, bar_minute):
            return
        cons_stop = ms.get_consolidation_stop()
        if cons_stop is None or price <= cons_stop:
            return
        # Fade-environment gate (2026-05-23). Blocks new MOVE_STRIKE
        # entries on faded symbols. Sticky once triggered; regime-shift
        # entries are NOT gated.
        try:
            _fade_vwap = self.bar_builder.get_vwap(symbol)
        except Exception:
            _fade_vwap = None
        _fade_blocked, _fade_reason = self.is_in_fade_environment(
            symbol, price, _fade_vwap,
        )
        if _fade_blocked and _fade_reason != "session-blocked":
            print(
                f"{LOG_TAG} [{now_iso_et()}] MOVE_FADE_GATE_BLOCK {symbol} "
                f"reason={_fade_reason} (price=${price:.4f} "
                f"vwap={'$%.4f' % _fade_vwap if _fade_vwap else 'n/a'} "
                f"open=${self._move_fade_session_open.get(symbol, 0):.4f})",
                flush=True,
            )
            return
        if _fade_blocked:
            return  # session-blocked, silent
        # Real arm: apply chase cap + below-arm filter
        if has_real_arm:
            arm_price = det.armed.entry_price or 0.0
            if arm_price > 0:
                gap_above_arm = (price - arm_price) / arm_price * 100.0
                if gap_above_arm > self.move_chase_cap_pct:
                    print(
                        f"{LOG_TAG} [{now_iso_et()}] {symbol} CHASE-SKIP (arm preserved) "
                        f"trigger={price:.3f} arm={arm_price:.3f} "
                        f"gap={gap_above_arm:.2f}%",
                        flush=True,
                    )
                    # Arm survives — wait for price to come back in range
                    # (matches sim's behavior at simulate.py:3745-3771).
                    # 2026-05-22 fix per chase_skip_arm_preservation_directive
                    # — MTVA 6-hour silence root cause.
                    return
                # Below-arm filter (PIII 2026-05-21 saved $670 on
                # backtest reconstruction).
                if self.move_max_below_arm_pct > 0:
                    below_arm_pct = (arm_price - price) / arm_price * 100.0
                    if below_arm_pct > self.move_max_below_arm_pct:
                        print(
                            f"{LOG_TAG} [{now_iso_et()}] {symbol} BELOW-ARM-SKIP (arm preserved) "
                            f"trigger={price:.3f} arm={arm_price:.3f} "
                            f"below={below_arm_pct:.2f}% (cap={self.move_max_below_arm_pct}%)",
                            flush=True,
                        )
                        # Arm survives — same fix as chase-skip path.
                        return
        # Stay-armed gates: cool-down + continuation %
        if stay_armed_active:
            last_min = self._move_stay_armed_last_exit_min.get(symbol, -10000)
            last_px = self._move_stay_armed_last_exit_price.get(symbol, 0.0)
            if (bar_minute - last_min) < self.move_stay_armed_cooldown_min:
                return  # within cooldown
            if last_px > 0 and price < last_px * (1.0 + self.move_stay_armed_min_gap_pct / 100.0):
                return  # not a continuation
        r = price - cons_stop
        if r <= 0:
            return
        if stay_armed_active:
            score = 50.0  # synthetic
        else:
            score = det.armed.score
        qty = self._compute_qty(price, r, score)
        if qty <= 0:
            return
        self._open_position(symbol, price, cons_stop, r, qty, score)
        # Mark stay-armed (any MOVE_STRIKE entry flags the symbol)
        if self.move_stay_armed:
            self._move_stay_armed_symbols.add(symbol)
        # Consume the arm (if real)
        if has_real_arm:
            det.armed = None
            self.prev_arm_state[symbol] = None

    def _compute_qty(self, price: float, r: float, score: float) -> int:
        # Equity-% sizing (2026-06-17 plan): each position = EQUITY_PCT of current
        # equity (starting equity + realized daily P&L → compounds intraday). No
        # leverage. Overrides the fixed-RISK_DOLLARS path when enabled.
        if EQUITY_PCT_SIZING > 0:
            equity = self._starting_equity + self.daily_pnl
            if equity > 0 and price > 0:
                qty = int((EQUITY_PCT_SIZING * equity) / price)
                return min(max(qty, 0), MAX_SHARES)
            # Equity unavailable (auth/connect failure) → skip rather than mis-size.
            print(f"{LOG_TAG} SIZING: equity unavailable (start={self._starting_equity} "
                  f"daily={self.daily_pnl}) — skipping entry", flush=True)
            return 0
        qty_risk = int(RISK_DOLLARS / max(r, 0.01))
        qty_notional = int(MAX_NOTIONAL / max(price, 0.01))
        qty = min(qty_risk, qty_notional, MAX_SHARES)
        # Probe sizing per main bot convention
        qty = max(1, int(qty * PROBE_SIZE_MULT))
        return qty

    # ──────────────────────────────────────────────────────────────────
    # Order submission
    # ──────────────────────────────────────────────────────────────────
    def _open_position(self, symbol: str, entry: float, stop: float,
                       r: float, qty: int, score: float) -> None:
        """Primary entry from MOVE_STRIKE arm + anomaly fire."""
        self._open_position_with_tag(
            symbol, entry, stop, r, qty, score,
            is_reentry=False, reentry_tag="",
        )

    def _open_position_with_tag(
        self, symbol: str, entry: float, stop: float,
        r: float, qty: int, score: float,
        is_reentry: bool, reentry_tag: str,
    ) -> None:
        # FIRESTORM gate — block entries on quiet bars (Variant A test).
        setup_label = f"reentry_{reentry_tag}" if is_reentry else "move_strike"
        if self._firestorm_gate_blocks(symbol, setup_label):
            return
        # Plan filters (time-window block + per-symbol loss-lockout).
        if self._strategy_filters_block(symbol, setup_label):
            return
        slip = max(0.07, entry * 0.01)
        base_limit = round(entry + slip, 2)
        # Alpaca-aware limit (2026-05-22): widen to alpaca_ask + buffer
        # when our IBKR-derived limit is below Alpaca's actual ask.
        aware_limit = self._compute_alpaca_aware_limit(symbol, entry, "BUY")
        limit = max(aware_limit, base_limit)
        tag_str = f" REENTRY({reentry_tag})" if is_reentry else ""
        print(
            f"{LOG_TAG} [{now_iso_et()}] 🟩 ENTRY{tag_str} {symbol} qty={qty} "
            f"limit=${limit:.2f} (anomaly@${entry:.2f}) stop=${stop:.2f} "
            f"R=${r:.4f} score={score:.1f}",
            flush=True,
        )
        try:
            req = LimitOrderRequest(
                symbol=symbol, qty=qty, side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY, limit_price=limit,
                extended_hours=True,
            )
            order = self.alpaca.submit_order(order_data=req)
        except Exception as e:
            print(f"{LOG_TAG} ENTRY REJECT {symbol}: {e!r}", flush=True)
            return
        self.position = SubPosition(
            symbol=symbol, entry=entry, stop=stop, r=r, qty=qty,
            score=score, time_et=now_iso_et(),
            is_reentry=is_reentry, reentry_tag=reentry_tag,
        )
        self.position.order_id_buy = str(order.id) if hasattr(order, "id") else None
        # Wait for fill so we can book real entry price (2026-05-22).
        fill_px, fill_qty = self._wait_for_fill(self.position.order_id_buy, timeout=15)
        if fill_px is not None and fill_qty > 0:
            self.position.fill_entry_price = fill_px
            self.position.fill_entry_qty = fill_qty
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} entry FILLED "
                f"@ ${fill_px:.4f} qty={fill_qty} (limit was ${limit:.2f})",
                flush=True,
            )
            # If partial fill, shrink the position's qty so the exit
            # doesn't try to sell shares we don't own.
            if fill_qty < qty:
                self.position.qty = fill_qty
        else:
            # Order didn't fill (timeout/cancel/reject). Clear position
            # so we don't track ghost shares — and don't manage exits.
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} entry order NOT FILLED "
                f"(timeout/cancel/reject) — abandoning trade",
                flush=True,
            )
            self.position = None
            return
        # Sync HH count from current per-symbol tracker
        self.position.hh_count = self._sym_hh_count.get(symbol, 0)

    def _close_position(self, reason: str, ref_price: float) -> None:
        """Submit an exit SELL LIMIT and reconcile the bot's position state
        against the actual fill outcome.

        Lever 1 (2026-05-26): three-case handling so we never clear
        self.position while the broker holds shares.
        Lever 2 (2026-05-26): on zero-fill, cancel + chase the bid up to
        WB_EXIT_MAX_RETRIES times before falling through to keep-alive.

        Per cowork_reports/2026-05-26_sub_bot_orphan_fix_directive.md.

        Gate: if a previous SELL is still pending (p.exit_pending), bail
        without re-submitting. Avoids stacking SELLs on the same residual.
        """
        p = self.position
        if p is None:
            return
        if p.exit_pending:
            # A previous SELL is still parked at the broker. Don't stack a
            # second one — wait for that one to fill or be cancelled.
            return
        # Initial limit: SELL slightly below ref_price for likely fill.
        slip = max(0.05, ref_price * 0.005)
        base_limit = round(ref_price - slip, 2)
        aware_limit = self._compute_alpaca_aware_limit(p.symbol, ref_price, "SELL")
        limit = min(aware_limit, base_limit)
        ordered_qty = p.qty
        # ── SAFE EXIT QTY (fix: 2026-05-29 PRFX / 2026-05-28 SPRC oversell loops) ──
        # The full-exit path requested p.qty even when the broker held far less
        # (PRFX: tracked 2,631 vs broker 4, held_for_orders=0 → 120,887 EXIT
        # REJECTs, position NEVER exited and carried). Cancel any parked SELL to
        # release held shares, then cap the order to the broker's ACTUAL
        # available qty so we can never request more than we hold. If the broker
        # is already flat, clear local state and let reconcile finish. Gate
        # defaults ON; set WB_MOVE_EXIT_AVAIL_CAP=0 to revert to legacy.
        if os.getenv("WB_MOVE_EXIT_AVAIL_CAP", "1") == "1":
            self._cancel_open_sells(p.symbol)
            avail = self._broker_available_qty(p.symbol)
            if avail is not None:
                if avail <= 0:
                    print(
                        f"{LOG_TAG} [{now_iso_et()}] EXIT SKIP {p.symbol}: broker "
                        f"available qty={avail} (already flat) — clearing local "
                        f"state, deferring to reconcile",
                        flush=True,
                    )
                    self.position = None
                    return
                if avail < ordered_qty:
                    print(
                        f"{LOG_TAG} [{now_iso_et()}] EXIT QTY CAP {p.symbol}: "
                        f"{ordered_qty}→{avail} (broker available)",
                        flush=True,
                    )
                    ordered_qty = avail
                    p.qty = avail
        _tag = "REGIME_SHIFT" if p.setup_type == "regime_shift" else "MOVE_STRIKE"
        print(
            f"{LOG_TAG} [{now_iso_et()}] 🟥 EXIT {_tag} {p.symbol} qty={ordered_qty} "
            f"limit=${limit:.2f} (ref=${ref_price:.2f}) reason={reason}",
            flush=True,
        )
        entry_basis = p.fill_entry_price if p.fill_entry_price is not None else p.entry
        safety_floor = round(entry_basis * self.exit_safety_floor_pct, 4)

        max_attempts = 1 + (self.exit_max_retries if self.exit_retry_enabled else 0)
        attempt = 0
        sell_fill_px: Optional[float] = None
        sell_fill_qty = 0
        timeout = 15  # initial timeout per directive
        prev_order_id: Optional[str] = None

        while attempt < max_attempts:
            attempt += 1
            try:
                req = LimitOrderRequest(
                    symbol=p.symbol, qty=ordered_qty, side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY, limit_price=limit,
                    extended_hours=True,
                )
                p.exit_pending = True
                order = self.alpaca.submit_order(order_data=req)
                p.order_id_sell = str(order.id) if hasattr(order, "id") else None
                prev_order_id = p.order_id_sell
                sell_fill_px, sell_fill_qty = self._wait_for_fill(p.order_id_sell, timeout=timeout)
            except Exception as e:
                p.exit_pending = False
                p.order_id_sell = None
                print(f"{LOG_TAG} EXIT REJECT {p.symbol}: {e!r}", flush=True)
                return

            # Outcome dispatch — break out of retry loop on terminal results.
            if sell_fill_px is not None and sell_fill_qty > 0:
                # Full or partial — exit retry loop, handle below.
                break

            # Zero fill. Either retry or fall through to keep-alive.
            if attempt >= max_attempts:
                break

            # Lever 2 retry path: cancel the stuck order, fetch new bid,
            # re-price aggressively.
            try:
                if prev_order_id:
                    self.alpaca.cancel_order_by_id(prev_order_id)
                    time.sleep(0.5)
            except Exception as e:
                # Cancel failure is non-fatal — the order may have already
                # been filled or cancelled between our wait and now. Log + continue.
                print(f"{LOG_TAG} EXIT CANCEL FAIL {p.symbol}: {e!r}", flush=True)

            new_bid = self._get_current_bid(p.symbol)
            if new_bid is None:
                # No bid available → can't chase. Break to keep-alive.
                print(
                    f"{LOG_TAG} EXIT RETRY {p.symbol} attempt={attempt}: "
                    f"no bid available, falling through to keep-alive",
                    flush=True,
                )
                break

            new_limit = round(new_bid * (1 - self.exit_aggressive_discount_pct), 2)
            new_limit = max(new_limit, safety_floor)
            print(
                f"{LOG_TAG} EXIT RETRY {p.symbol} attempt={attempt}/{max_attempts - 1} "
                f"bid=${new_bid:.4f} new_limit=${new_limit:.4f} (floor=${safety_floor:.4f})",
                flush=True,
            )
            limit = new_limit
            timeout = self.exit_retry_timeout_sec  # shorter on retries — bid moves fast
            # Loop continues; new SELL submitted at the head of next iteration.

        # ── CASE 1: Full fill — flatten position. ─────────────────────────
        if sell_fill_px is not None and sell_fill_qty >= ordered_qty:
            real_pnl = (sell_fill_px - entry_basis) * sell_fill_qty
            self.daily_pnl += real_pnl
            self.daily_trades_closed += 1
            print(
                f"{LOG_TAG} real P&L={real_pnl:+,.0f} daily={self.daily_pnl:+,.0f} "
                f"(trade #{self.daily_trades_closed}) "
                f"entry=${entry_basis:.4f} exit=${sell_fill_px:.4f} qty={sell_fill_qty}",
                flush=True,
            )
            # Per-symbol loss-lockout: if the POSITION (final leg + any scaled-out
            # partial) netted a loss, block further entries on this symbol today.
            # Uses position net (not just the runner leg) so a 90%-at-target
            # scale-out winner with a red 10% runner is NOT wrongly locked.
            if SYMBOL_LOSS_LOCKOUT:
                position_net = real_pnl + (getattr(p, "partial_pnl", 0.0) or 0.0)
                if position_net < 0:
                    self._lossout_symbols.add(p.symbol)
                    print(f"{LOG_TAG} [{now_iso_et()}] {p.symbol} → LOSS_LOCKOUT armed "
                          f"(position net ${position_net:+,.0f}; no re-entry today)",
                          flush=True)
            self._register_reentry_watch(p)
            if self.move_stay_armed:
                self._move_stay_armed_last_exit_min[p.symbol] = now_minute_et()
                self._move_stay_armed_last_exit_price[p.symbol] = float(ref_price)
            # REENTRY-HWM-gate tracking: capture exit reason + minute for
            # the gate's decision on subsequent REENTRY GREEN attempts.
            self._last_exit_reason_by_symbol[p.symbol] = (reason, now_minute_et())
            self.position = None
            return

        # ── CASE 2: Partial fill — record realized, keep residual alive. ──
        if sell_fill_px is not None and sell_fill_qty > 0:
            realized_pnl = (sell_fill_px - entry_basis) * sell_fill_qty
            self.daily_pnl += realized_pnl
            residual = ordered_qty - sell_fill_qty
            p.qty = residual
            p.order_id_sell = None
            p.exit_pending = False
            print(
                f"{LOG_TAG} EXIT PARTIAL {p.symbol}: filled {sell_fill_qty} "
                f"@ ${sell_fill_px:.4f} (entry=${entry_basis:.4f}) realized "
                f"P&L=${realized_pnl:+,.2f}; residual {residual} kept alive, "
                f"will retry exit on next tick",
                flush=True,
            )
            return

        # ── CASE 3: Zero fill (after all retries) — keep-alive + CRITICAL. ─
        p.order_id_sell = None
        p.exit_pending = False
        print(
            f"{LOG_TAG} 🔥 EXIT NO-FILL {p.symbol} qty={ordered_qty} "
            f"ref=${ref_price:.2f} reason={reason} after {attempt} attempt(s) — "
            f"position alive, will retry exit on next tick",
            flush=True,
        )
        return

    # ──────────────────────────────────────────────────────────────────
    # Lever 3 (2026-05-26): periodic broker reconciliation.
    # ──────────────────────────────────────────────────────────────────
    def _reconcile_with_broker(self) -> None:
        """Compare bot's view of position state against the broker's truth.

        Two divergence cases handled:
          - Broker has a position the bot doesn't track → adopt with
            conservative ±5% stop/target defaults, mark setup_type as
            'orphan_adopted'. Only adopts when self.position is None
            (sub-bot is single-position; can't manage two).
          - Bot tracks a position the broker doesn't have → flatten the
            bot's internal state (no broker exposure to manage).

        Idempotent: prints only on state change. Read-only call to Alpaca
        wrapped in try/except so a transient network error doesn't crash
        the loop.

        Per cowork_reports/2026-05-26_sub_bot_orphan_fix_directive.md
        §Lever 3 sub-bot.
        """
        if self.alpaca is None:
            return
        try:
            broker_positions = self.alpaca.get_all_positions()
        except Exception as e:
            print(f"{LOG_TAG} RECONCILE FAIL: {e!r}", flush=True)
            return

        broker_syms = {p.symbol: p for p in broker_positions}
        bot_sym = self.position.symbol if self.position else None

        # Case A: bot tracks something broker doesn't have → flatten locally.
        if bot_sym is not None and bot_sym not in broker_syms:
            print(
                f"{LOG_TAG} RECONCILE FLATTEN {bot_sym}: bot tracked but "
                f"broker has no shares — clearing local state",
                flush=True,
            )
            self.position = None
            bot_sym = None

        # Case B: broker has positions the bot doesn't track.
        for sym, bpos in broker_syms.items():
            if sym == bot_sym:
                continue  # bot already manages this one
            try:
                adopted_qty = int(float(bpos.qty))
                avg_entry = float(bpos.avg_entry_price)
            except (ValueError, TypeError, AttributeError):
                continue
            if adopted_qty <= 0:
                # Short position — out of scope; sub-bot is long-only.
                continue
            if self.position is not None:
                # Already managing a different symbol; can't adopt a second.
                # Log once per cycle so operator sees the unhandled orphan.
                print(
                    f"{LOG_TAG} RECONCILE ORPHAN-UNHANDLED {sym} qty={adopted_qty} "
                    f"avg=${avg_entry:.4f} (bot busy with {self.position.symbol}) — "
                    f"manual intervention required",
                    flush=True,
                )
                continue
            # Adopt with conservative ±5% defaults. Mark setup_type so
            # exit handlers (if they branch on setup_type) treat it as a
            # special case rather than MOVE_STRIKE / regime_shift logic.
            adopted_stop = round(avg_entry * 0.95, 4)
            adopted = SubPosition(
                symbol=sym, entry=avg_entry, stop=adopted_stop,
                r=avg_entry - adopted_stop, qty=adopted_qty, score=0.0,
                time_et=now_iso_et(), setup_type="orphan_adopted",
            )
            # Treat broker's avg as the canonical entry-fill price.
            adopted.fill_entry_price = avg_entry
            adopted.fill_entry_qty = adopted_qty
            self.position = adopted
            print(
                f"{LOG_TAG} RECONCILE ADOPT {sym} qty={adopted_qty} "
                f"avg=${avg_entry:.4f} stop=${adopted_stop:.4f} "
                f"setup=orphan_adopted — managing residual until exit",
                flush=True,
            )

    # ──────────────────────────────────────────────────────────────────
    # Socket consumer loop
    # ──────────────────────────────────────────────────────────────────
    def consume(self) -> None:
        sock = self._connect_with_retry()
        if sock is None:
            print(f"{LOG_TAG} could not connect to engine — exiting", flush=True)
            return
        buf = b""
        last_stats = time.time()
        last_heartbeat = 0.0
        while not self._stop:
            timed_out = False
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                # No data within the recv timeout — NOT a disconnect. Fall
                # through to the periodic/heartbeat path so the wall-clock EOD
                # flatten still runs when the tape is silent.
                timed_out = True
                chunk = b""
            except (ConnectionResetError, OSError) as e:
                print(f"{LOG_TAG} socket recv error: {e!r} — reconnecting", flush=True)
                try:
                    sock.close()
                except Exception:
                    pass
                sock = self._connect_with_retry()
                if sock is None:
                    return
                buf = b""
                continue
            if not timed_out and not chunk:
                print(f"{LOG_TAG} socket closed by peer — reconnecting", flush=True)
                try:
                    sock.close()
                except Exception:
                    pass
                sock = self._connect_with_retry()
                if sock is None:
                    return
                buf = b""
                continue
            if chunk:
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = decode(line)
                    except Exception as e:
                        print(f"{LOG_TAG} decode error: {e!r} on {line[:120]!r}", flush=True)
                        continue
                    self._dispatch(msg)
            now = time.time()
            # Wall-clock EOD force-flatten heartbeat (fix 2026-06-04 STI
            # overnight hold). Runs every iteration incl. socket timeouts, so a
            # held position whose symbol has gone quiet is still flattened at
            # the cutoff rather than carried overnight.
            if now - last_heartbeat >= 10:
                self._maybe_eod_flatten()
                last_heartbeat = now
            # Periodic stats + broker reconciliation (Lever 3, 2026-05-26).
            if now - last_stats > 60:
                print(
                    f"{LOG_TAG} [{now_iso_et()}] STATS ticks={self.ticks_received} "
                    f"symbols={len(self.symbols_seen)} pos={'YES' if self.position else 'no'} "
                    f"daily_pnl={self.daily_pnl:+,.0f} drops={self._dropped_tick_count}",
                    flush=True,
                )
                last_stats = now
                # Lever 3: periodic broker reconcile to catch any orphans
                # the exit code path left behind. Idempotent — logs only
                # on state change.
                if (
                    self._last_reconcile_at is None
                    or (time.time() - self._last_reconcile_at) >= self.reconcile_interval_sec
                ):
                    self._reconcile_with_broker()
                    self._last_reconcile_at = now

    def _connect_with_retry(self) -> Optional[socket.socket]:
        attempt = 0
        while not self._stop:
            attempt += 1
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(SOCKET_PATH)
                # 5s recv timeout so the consume loop's wall-clock heartbeat
                # (EOD flatten) runs even when no engine ticks arrive at all.
                s.settimeout(5.0)
                # On (re)connect, the publisher may have restarted with
                # a fresh seq counter. Clear last-seen state so we don't
                # log a spurious gap on the first tick of the new stream.
                if self.seq_audit_enabled:
                    self._last_engine_seq.clear()
                print(
                    f"{LOG_TAG} [{now_iso_et()}] connected to engine "
                    f"({SOCKET_PATH}) attempt={attempt}",
                    flush=True,
                )
                return s
            except (FileNotFoundError, ConnectionRefusedError, OSError) as e:
                if attempt == 1:
                    print(
                        f"{LOG_TAG} engine socket not ready yet ({e!r}) — "
                        f"retrying every 2s",
                        flush=True,
                    )
                time.sleep(2)
        return None

    def _dispatch(self, msg) -> None:
        # Hello frames from the publisher come as a plain dict
        if isinstance(msg, dict) and msg.get("type") == "hello":
            print(f"{LOG_TAG} engine hello: {msg}", flush=True)
            return
        if isinstance(msg, TickMessage):
            # engine_seq gap detection (2026-05-22). Publisher drops the
            # oldest tick when its 10K queue overflows. With this check
            # we can see drops in the log immediately and reason about
            # whether silent arm-state divergences correlate with drops.
            if self.seq_audit_enabled and hasattr(msg, "engine_seq"):
                seq = getattr(msg, "engine_seq", None)
                if seq is not None:
                    last = self._last_engine_seq.get(msg.symbol)
                    if last is not None and seq > last + 1:
                        gap = seq - last - 1
                        self._dropped_tick_count += gap
                        print(
                            f"{LOG_TAG} [{now_iso_et()}] ENGINE_SEQ_GAP {msg.symbol} "
                            f"expected={last + 1} got={seq} dropped={gap}",
                            flush=True,
                        )
                    self._last_engine_seq[msg.symbol] = seq
            self.on_tick(msg.symbol, msg.price, msg.ts, msg.size)


def main():
    # Strict gate checks — abort if MOVE_STRIKE/HWM aren't enabled.
    if os.getenv("WB_BT_MOVE_STRIKE", "0") != "1":
        print(f"{LOG_TAG} FATAL: WB_BT_MOVE_STRIKE != 1; refusing to start", flush=True)
        sys.exit(1)
    if os.getenv("WB_BT_MOVE_HWM_EXIT", "0") != "1":
        print(f"{LOG_TAG} FATAL: WB_BT_MOVE_HWM_EXIT != 1; refusing to start", flush=True)
        sys.exit(1)
    bot = MoveStrikeSubBot()

    def _shutdown(signum, frame):
        print(f"{LOG_TAG} signal {signum} received — stopping", flush=True)
        bot._stop = True

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    print(f"{LOG_TAG} starting consume loop", flush=True)
    bot.consume()
    # Shutdown backstop (fix 2026-06-04): on exit, flatten any open position
    # IF we're at/after the EOD cutoff. _maybe_eod_flatten is no-op before the
    # cutoff, so a mid-session watchdog restart (e.g. the 14:59 ET tick-drought
    # restart) does NOT flatten — it still rehydrates per the session-
    # persistence rule. Only an end-of-session shutdown closes the position.
    try:
        bot._maybe_eod_flatten()
    except Exception as e:
        print(f"{LOG_TAG} SHUTDOWN FLATTEN FAIL: {e!r}", flush=True)
    print(f"{LOG_TAG} consume loop exited", flush=True)


if __name__ == "__main__":
    main()
