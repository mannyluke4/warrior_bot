#!/usr/bin/env python3
"""
Warrior Bot — Historical Backtesting / Simulation Engine

Replays historical 1-minute bars through the exact same detection and exit
logic the live bot uses, then prints a trade report.

Usage:
    python simulate.py RELY 2026-02-19                     # full day
    python simulate.py RELY 2026-02-19 09:30 12:00         # time window
    python simulate.py RELY NAMM 2026-02-19                # multiple tickers
    python simulate.py RELY 2026-02-19 --risk 500          # override risk $
    python simulate.py RELY 2026-02-19 --min-score 5       # override min score
    python simulate.py RELY 2026-02-19 --slippage 0.03     # entry slippage $
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, time
from typing import Optional

import pytz
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockTradesRequest
from alpaca.data.timeframe import TimeFrame

from bars import TradeBarBuilder, Bar
from candles import is_bearish_engulfing
from micro_pullback import MicroPullbackDetector
from trade_manager import check_toxic_filters
from ross_exit import RossExitManager

load_dotenv()

ET = pytz.timezone("US/Eastern")

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
hist_client = StockHistoricalDataClient(API_KEY, API_SECRET)


# ─────────────────────────────────────────────
# Simulated trade tracking
# ─────────────────────────────────────────────

@dataclass
class SimTrade:
    symbol: str
    entry: float
    stop: float
    r: float
    qty_total: int
    qty_core: int       # T1 in 3-tranche mode
    qty_runner: int     # T3 in 3-tranche mode
    score: float = 0.0
    score_detail: str = ""
    setup_type: str = "micro_pullback"
    entry_time: str = ""
    # Core/T1 exit
    core_exit_price: float = 0.0
    core_exit_time: str = ""
    core_exit_reason: str = ""
    # T2 exit (3-tranche only; qty_t2=0 when disabled)
    qty_t2: int = 0
    t2_exit_price: float = 0.0
    t2_exit_time: str = ""
    t2_exit_reason: str = ""
    t2_hit: bool = False
    # Runner/T3 exit
    runner_exit_price: float = 0.0
    runner_exit_time: str = ""
    runner_exit_reason: str = ""
    # State
    tp_hit: bool = False    # T1 hit
    peak: float = 0.0
    peak_time: str = ""
    runner_stop: float = 0.0
    highest_r: float = 0.0   # Peak R-multiple seen (for WB_TRAILING_STOP)
    closed: bool = False
    # Halt-through state (WB_HALT_THROUGH_ENABLED)
    halt_detected: bool = False
    halt_detected_at_ts: Optional[datetime] = None
    halt_resume_grace_until_ts: Optional[datetime] = None
    # Ross exit state (WB_ROSS_EXIT_ENABLED)
    _ross_partial_taken: bool = False

    def pnl(self) -> float:
        pnl = 0.0
        if self.core_exit_price > 0 and self.qty_core > 0:
            pnl += (self.core_exit_price - self.entry) * self.qty_core
        if self.t2_exit_price > 0 and self.qty_t2 > 0:
            pnl += (self.t2_exit_price - self.entry) * self.qty_t2
        if self.runner_exit_price > 0 and self.qty_runner > 0:
            pnl += (self.runner_exit_price - self.entry) * self.qty_runner
        return pnl

    def r_multiple(self) -> float:
        if self.r <= 0:
            return 0.0
        return self.pnl() / (self.r * self.qty_total)


class SimTradeManager:
    """Lightweight trade manager that mirrors the live exit logic without Alpaca API."""

    def __init__(
        self,
        risk_dollars: float = 1000.0,
        scale_core: float = 0.65,
        min_r: float = 0.06,
        max_notional: float = 50000.0,
        max_shares: int = 100000,
        core_tp_r: float = 1.0,
        tp_fuzz: float = 0.03,
        be_offset: float = 0.01,
        runner_trail_r: float = 1.0,
        slippage: float = 0.02,
        exit_mode: str = "signal",
        be_trigger_r: float = 1.0,
        signal_trail_pct: float = 0.05,
        max_entries_per_symbol: int = 2,
        symbol_cooldown_min: int = 10,
        max_loss_r: float = 2.0,
        reentry_cooldown_bars: int = 0,
        stock_info=None,
        quality_min_float: float = 0.5,
        # 3-tranche exit scaling
        three_tranche_enabled: bool = False,
        scale_t1: float = 0.40,
        scale_t2: float = 0.35,
        t1_tp_r: float = 1.0,
        t2_tp_r: float = 2.0,
        t2_stop_lock_r: float = 0.5,
    ):
        self.risk_dollars = risk_dollars
        self.scale_core = scale_core
        self.min_r = min_r
        self.max_notional = max_notional
        self.max_shares = max_shares
        self.core_tp_r = core_tp_r
        self.tp_fuzz = tp_fuzz
        self.be_offset = be_offset
        self.runner_trail_r = runner_trail_r
        self.slippage = slippage
        self.exit_mode = exit_mode
        self.be_trigger_r = be_trigger_r
        self.signal_trail_pct = signal_trail_pct
        self.max_entries_per_symbol = max_entries_per_symbol
        self.symbol_cooldown_min = symbol_cooldown_min
        self.max_loss_r = max_loss_r
        self.reentry_cooldown_bars = reentry_cooldown_bars
        self.stock_info = stock_info
        self.quality_min_float = quality_min_float
        # Float-tiered max loss cap
        self._max_loss_r_tiered = os.getenv("WB_MAX_LOSS_R_TIERED", "0") == "1"
        self._max_loss_r_ultra_low = float(os.getenv("WB_MAX_LOSS_R_ULTRA_LOW_FLOAT", "0"))
        self._max_loss_r_low = float(os.getenv("WB_MAX_LOSS_R_LOW_FLOAT", "0.85"))
        self._max_loss_r_thresh_low = float(os.getenv("WB_MAX_LOSS_R_FLOAT_THRESHOLD_LOW", "1.0"))
        self._max_loss_r_thresh_high = float(os.getenv("WB_MAX_LOSS_R_FLOAT_THRESHOLD_HIGH", "5.0"))
        self._max_loss_triggers_cooldown = os.getenv("WB_MAX_LOSS_TRIGGERS_COOLDOWN", "0") == "1"
        # Fallback float from scanner env var (batch runner passes WB_SCANNER_FLOAT_M)
        self._scanner_float_m = float(os.getenv("WB_SCANNER_FLOAT_M", "0"))

        # 3-tranche exit scaling
        self.three_tranche_enabled = three_tranche_enabled
        self.scale_t1 = scale_t1
        self.scale_t2 = scale_t2
        self.t1_tp_r = t1_tp_r
        self.t2_tp_r = t2_tp_r
        self.t2_stop_lock_r = t2_stop_lock_r
        # When 3-tranche is enabled, force classic exit mode
        if self.three_tranche_enabled and self.exit_mode == "signal":
            self.exit_mode = "classic"

        # --- Squeeze exit parameters ---
        self.sq_trail_r = float(os.getenv("WB_SQ_TRAIL_R", "1.5"))
        self.sq_stall_bars = int(os.getenv("WB_SQ_STALL_BARS", "5"))
        self.sq_target_r = float(os.getenv("WB_SQ_TARGET_R", "2.0"))
        self.sq_core_pct = int(os.getenv("WB_SQ_CORE_PCT", "75"))
        self.sq_runner_trail_r = float(os.getenv("WB_SQ_RUNNER_TRAIL_R", "2.5"))
        self.sq_vwap_exit = os.getenv("WB_SQ_VWAP_EXIT", "1") == "1"
        self.sq_para_trail_r = float(os.getenv("WB_SQ_PARA_TRAIL_R", "1.0"))
        self.sq_max_loss_dollars = float(os.getenv("WB_SQ_MAX_LOSS_DOLLARS", "500"))
        self._sq_bars_no_new_high = 0  # stall counter for squeeze time stop
        self._sq_last_vwap: Optional[float] = None  # updated on 1m bar close

        # --- Bail timer (matches live bot) ---
        self.bail_timer_enabled = os.getenv("WB_BAIL_TIMER_ENABLED", "1") == "1"
        self.bail_timer_minutes = float(os.getenv("WB_BAIL_TIMER_MINUTES", "5"))

        # Fix 1: partial exit on sq_target_hit — take only N% at target, let rest run
        self.sq_partial_exit_enabled = os.getenv("WB_SQ_PARTIAL_EXIT_ENABLED", "0") == "1"
        self.sq_partial_pct = int(os.getenv("WB_SQ_PARTIAL_PCT", "50"))

        # Fix 2: wider parabolic trail — multiply trail width to give winners more room
        self.sq_wide_trail_enabled = os.getenv("WB_SQ_WIDE_TRAIL_ENABLED", "0") == "1"
        self.sq_trail_multiplier = float(os.getenv("WB_SQ_TRAIL_MULTIPLIER", "2.0"))

        # Fix 3: runner detection — stocks hitting target in <5m get even wider trail (3x)
        self.sq_runner_detect_enabled = os.getenv("WB_SQ_RUNNER_DETECT_ENABLED", "0") == "1"
        self._sq_target_hit_min: Optional[int] = None  # minutes since midnight when target was hit

        # --- VWAP Reclaim exit parameters (Strategy 4) ---
        self.vr_stall_bars = int(os.getenv("WB_VR_STALL_BARS", "5"))
        self.vr_target_r = float(os.getenv("WB_VR_TARGET_R", "1.5"))
        self.vr_core_pct = int(os.getenv("WB_VR_CORE_PCT", "75"))
        self.vr_runner_trail_r = float(os.getenv("WB_VR_RUNNER_TRAIL_R", "2.0"))
        self.vr_vwap_exit = os.getenv("WB_VR_VWAP_EXIT", "1") == "1"
        self.vr_trail_r = float(os.getenv("WB_VR_TRAIL_R", "1.5"))
        self.vr_max_loss_dollars = float(os.getenv("WB_VR_MAX_LOSS_DOLLARS", "300"))
        self._vr_bars_no_new_high = 0  # stall counter for VR time stop
        self._vr_last_vwap: Optional[float] = None  # updated on 1m bar close

        # --- Ross exit mode (WB_ROSS_EXIT_ENABLED=0 by default) ---
        self.ross_exit_enabled = os.getenv("WB_ROSS_EXIT_ENABLED", "0") == "1"
        # SQ + Ross coexistence: let SQ mechanical exits (target hit, trail) work alongside Ross 1m signals
        self.sq_ross_coexist = os.getenv("WB_SQ_ROSS_COEXIST", "0") == "1"

        # --- Halt-through (WB_HALT_THROUGH_ENABLED=0 by default) ---
        self._halt_through_enabled = os.getenv("WB_HALT_THROUGH_ENABLED", "0") == "1"
        self._halt_detect_sec = float(os.getenv("WB_HALT_DETECT_SEC", "30"))
        self._halt_min_profit_r = float(os.getenv("WB_HALT_MIN_PROFIT_R", "1.0"))
        self._halt_resume_grace_sec = float(os.getenv("WB_HALT_RESUME_GRACE_SEC", "10"))
        self._halt_max_duration_sec = float(os.getenv("WB_HALT_MAX_DURATION_SEC", "600"))

        # Account tracking for realistic backtesting
        self.account_equity = float(os.getenv("WB_SIM_ACCOUNT_EQUITY", "0"))  # 0 = disabled
        self.current_equity = self.account_equity  # tracks running balance
        self.open_notional = 0.0  # notional value of open positions

        self.open_trade: Optional[SimTrade] = None
        self.closed_trades: list[SimTrade] = []
        self.signals_received: int = 0
        self.on_trade_close = None  # callback(SimTrade) — set by caller for quality gate integration

        # Per-symbol re-entry cooldown tracking
        self._symbol_entry_count: dict[str, int] = {}
        self._symbol_cooldown_until: dict[str, int] = {}  # symbol -> minute offset when cooldown expires
        # Stop-hit cooldown: bars remaining before re-entry allowed
        self._stop_hit_cooldown: dict[str, int] = {}  # symbol -> bars remaining

    def _time_to_minutes(self, time_str: str) -> int:
        """Convert 'HH:MM' to minutes since midnight for cooldown tracking."""
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    # ------------------------------------------------------------------
    # Halt-through helpers (simulate tick-gap halts)
    # ------------------------------------------------------------------
    def _is_sim_halt_active(self, t: "SimTrade") -> bool:
        """True if halt-through is suspending trail/pattern exits for this trade."""
        if t.halt_detected:
            return True
        if t.halt_resume_grace_until_ts is not None:
            return True  # cleared by handle_tick_halt on next tick
        return False

    def handle_tick_halt(self, ts: datetime, prev_ts: Optional[datetime]):
        """Detect/manage halt state based on gap between consecutive tick timestamps.

        Call before on_tick() for each tick in the replay loop when --ticks mode is active.
        """
        if not self._halt_through_enabled:
            return
        t = self.open_trade
        if t is None or t.closed:
            return

        # Clear expired grace period
        if t.halt_resume_grace_until_ts is not None and ts >= t.halt_resume_grace_until_ts:
            t.halt_resume_grace_until_ts = None

        # Handle resumption: got a tick while halt was detected
        if t.halt_detected:
            t.halt_detected = False
            t.halt_detected_at_ts = None
            grace_td = timedelta(seconds=self._halt_resume_grace_sec)
            t.halt_resume_grace_until_ts = ts + grace_td
            ts_et = ts.astimezone(ET).strftime("%H:%M:%S")
            print(
                f"  HALT_THROUGH [{ts_et}] {t.symbol}: halt resumed,"
                f" grace={self._halt_resume_grace_sec:.0f}s",
                flush=True,
            )
            return

        # Detect new halt: large time gap while position is profitable
        if prev_ts is None:
            return
        gap_sec = (ts - prev_ts).total_seconds()
        if gap_sec < self._halt_detect_sec:
            return

        # Only halt-through on profitable positions
        unrealized_r = (t.peak - t.entry) / t.r if t.r > 0 else 0
        if unrealized_r < self._halt_min_profit_r:
            return

        # Enforce max duration: if gap > max_duration, don't treat as halt-through
        if self._halt_max_duration_sec > 0 and gap_sec > self._halt_max_duration_sec:
            return

        # Halt detected!
        t.halt_detected = True
        t.halt_detected_at_ts = prev_ts
        ts_et = ts.astimezone(ET).strftime("%H:%M:%S")
        print(
            f"  HALT_THROUGH [{ts_et}] {t.symbol}: halt detected"
            f" (gap={gap_sec:.0f}s, profit={unrealized_r:.1f}R) — suspending trail exits",
            flush=True,
        )
        # Immediately process resumption: this tick IS the resumption
        t.halt_detected = False
        t.halt_detected_at_ts = None
        grace_td = timedelta(seconds=self._halt_resume_grace_sec)
        t.halt_resume_grace_until_ts = ts + grace_td
        print(
            f"  HALT_THROUGH [{ts_et}] {t.symbol}: halt resumed (same tick),"
            f" grace={self._halt_resume_grace_sec:.0f}s",
            flush=True,
        )

    def on_signal(self, symbol: str, entry: float, stop: float, r: float,
                  score: float, detail: str, time_str: str,
                  setup_type: str = "micro_pullback", size_mult: float = 1.0) -> Optional[SimTrade]:
        self.signals_received += 1

        if self.open_trade is not None:
            return None

        if r <= 0 or r < self.min_r:
            return None

        # Per-symbol re-entry cooldown (entry-count based)
        now_min = self._time_to_minutes(time_str)
        cooldown_until = self._symbol_cooldown_until.get(symbol)
        if cooldown_until is not None:
            if now_min < cooldown_until:
                return None  # still in cooldown
            else:
                # Cooldown expired, reset
                self._symbol_entry_count[symbol] = 0
                self._symbol_cooldown_until.pop(symbol, None)

        # Stop-hit cooldown: block re-entry for N bars after stop_hit
        if symbol in self._stop_hit_cooldown:
            return None

        # Quality gate: check cached fundamentals
        if self.stock_info is not None:
            if (self.stock_info.float_shares is not None
                    and self.stock_info.float_shares < self.quality_min_float):
                return None

        fill_price = entry + self.slippage
        actual_r = fill_price - stop
        if actual_r <= 0:
            return None

        qty_risk = int(math.floor(self.risk_dollars / actual_r))
        qty_notional = int(math.floor(self.max_notional / max(fill_price, 0.01)))
        qty = min(qty_risk, qty_notional, self.max_shares)

        # Apply size_mult (e.g. squeeze probe = 0.5x)
        if size_mult < 1.0:
            qty = max(1, int(math.floor(qty * size_mult)))

        # Buying power constraint (4x margin for PDT accounts)
        if self.account_equity > 0:
            available_bp = (self.current_equity * 4) - self.open_notional
            if available_bp <= 0:
                return None  # no buying power left
            qty_bp = int(math.floor(available_bp / max(fill_price, 0.01)))
            qty = min(qty, qty_bp)

        if qty <= 0:
            return None

        if setup_type in ("squeeze", "mp_reentry", "continuation"):
            # Squeeze / MP V2 re-entry / CT: core + runner split for partial exits
            # Fix 1: when partial exit enabled, use sq_partial_pct instead of sq_core_pct
            _sq_split_pct = self.sq_partial_pct if self.sq_partial_exit_enabled else self.sq_core_pct
            qty_core = max(1, int(math.floor(qty * _sq_split_pct / 100)))
            qty_t2 = 0
            qty_runner = max(0, qty - qty_core)
        elif setup_type == "vwap_reclaim":
            # VWAP Reclaim: core + runner split (similar to squeeze)
            qty_core = max(1, int(math.floor(qty * self.vr_core_pct / 100)))
            qty_t2 = 0
            qty_runner = max(0, qty - qty_core)
        elif self.three_tranche_enabled:
            # 3-tranche split: T1 (core) + T2 + T3 (runner)
            qty_core = max(1, int(math.floor(qty * self.scale_t1)))
            qty_t2 = max(0, int(math.floor(qty * self.scale_t2)))
            qty_runner = max(0, qty - qty_core - qty_t2)
            # Guard: if qty is too small for T3, fold remainder into T2
            if qty_runner <= 0 and qty_t2 > 0:
                qty_runner = 0
        elif self.ross_exit_enabled:
            # Ross exit: 50/50 split — core exits on warning (doji), runner on confirmed signal
            # Applies to ALL trade types (MP, SQ, VR) when WB_ROSS_EXIT_ENABLED=1
            qty_core = max(1, qty // 2)
            qty_t2 = 0
            qty_runner = max(0, qty - qty_core)
        elif self.exit_mode == "signal":
            qty_core = qty      # full position, no split
            qty_t2 = 0
            qty_runner = 0
        else:
            qty_core = max(1, int(math.floor(qty * self.scale_core)))
            qty_t2 = 0
            qty_runner = max(0, qty - qty_core)

        t = SimTrade(
            symbol=symbol,
            entry=fill_price,
            stop=stop,
            r=actual_r,
            qty_total=qty,
            qty_core=qty_core,
            qty_t2=qty_t2,
            qty_runner=qty_runner,
            score=score,
            score_detail=detail,
            setup_type=setup_type,
            entry_time=time_str,
            peak=fill_price,
            runner_stop=stop,
        )
        self.open_trade = t
        if setup_type in ("squeeze", "mp_reentry", "continuation"):
            self._sq_target_hit_min = None  # reset runner detection state

        # Track open notional for buying power
        if self.account_equity > 0:
            self.open_notional += qty * fill_price

        # Track re-entry count and start cooldown when cap is reached
        # Squeeze trades use their own counter (detector._attempts), don't count against MP
        # MP V2 re-entry trades use mp_det._reentry_count, don't count against standard MP cooldown
        if setup_type not in ("squeeze", "mp_reentry", "continuation"):
            entry_count = self._symbol_entry_count.get(symbol, 0) + 1
            self._symbol_entry_count[symbol] = entry_count
            if entry_count >= self.max_entries_per_symbol:
                self._symbol_cooldown_until[symbol] = now_min + self.symbol_cooldown_min

        return t

    def on_tick(self, price: float, time_str: str):
        t = self.open_trade
        if t is None or t.closed:
            return

        if price > t.peak:
            t.peak = price
            t.peak_time = time_str
            # Reset stall counter for squeeze / mp_reentry / vwap_reclaim
            if t.setup_type in ("squeeze", "mp_reentry", "continuation"):
                self._sq_bars_no_new_high = 0
            elif t.setup_type == "vwap_reclaim":
                self._vr_bars_no_new_high = 0

        # --- Bail timer: exit if unprofitable after N minutes ---
        if self.bail_timer_enabled and t.entry_time:
            entry_min = int(t.entry_time.split(":")[0]) * 60 + int(t.entry_time.split(":")[1])
            now_min = int(time_str.split(":")[0]) * 60 + int(time_str.split(":")[1])
            if (now_min - entry_min) >= self.bail_timer_minutes:
                if price <= t.entry:
                    t.core_exit_price = price
                    t.core_exit_time = time_str
                    t.core_exit_reason = "bail_timer"
                    if t.qty_runner > 0:
                        t.runner_exit_price = price
                        t.runner_exit_time = time_str
                        t.runner_exit_reason = "bail_timer"
                    self._close(t)
                    return

        # --- Route squeeze exits ---
        if t.setup_type == "squeeze":
            self._squeeze_tick_exits(t, price, time_str)
            return

        # --- Route MP V2 re-entry exits through squeeze exit system ---
        if t.setup_type == "mp_reentry":
            self._squeeze_tick_exits(t, price, time_str)
            return

        # --- Route continuation exits through squeeze exit system ---
        if t.setup_type == "continuation":
            self._squeeze_tick_exits(t, price, time_str)
            return

        # --- Route VWAP Reclaim exits ---
        if t.setup_type == "vwap_reclaim":
            self._vr_tick_exits(t, price, time_str)
            return

        # --- MAX LOSS CAP (hard safety net) ---
        # Determine effective cap: flat or float-tiered
        _eff_mlr = self.max_loss_r
        if self._max_loss_r_tiered:
            # Try stock_info first, then fall back to scanner env var
            _fm = None
            if self.stock_info and hasattr(self.stock_info, 'float_shares') and self.stock_info.float_shares:
                _fm = self.stock_info.float_shares
            elif self._scanner_float_m > 0:
                _fm = self._scanner_float_m
            if _fm is not None:
                if _fm < self._max_loss_r_thresh_low:
                    _eff_mlr = self._max_loss_r_ultra_low  # 0 = OFF for ultra-low float
                elif _fm <= self._max_loss_r_thresh_high:
                    _eff_mlr = self._max_loss_r_low  # e.g. 0.85 for 1-5M float
                # else: use self.max_loss_r (5M+ default)

        if _eff_mlr > 0 and t.r > 0:
            loss_per_share = t.entry - price
            if loss_per_share >= _eff_mlr * t.r:
                t.core_exit_price = price
                t.core_exit_time = time_str
                t.core_exit_reason = "max_loss_hit"
                self._close(t)
                return

        # --- Signal exit mode: no fixed TP, trailing stop on full position ---
        if self.exit_mode == "signal":
            # Activate trailing once price reaches TP level
            if price >= t.entry + (self.be_trigger_r * t.r):
                t.tp_hit = True
                t.stop = max(t.stop, t.entry + self.be_offset)

            # Trail only after TP level reached (before that, hard stop provides safety)
            # Halt-through: skip trail update during halt/grace (hard stop still runs below)
            if t.tp_hit and not (self._halt_through_enabled and self._is_sim_halt_active(t)):
                trail_stop = t.peak * (1.0 - self.signal_trail_pct)
                t.stop = max(t.stop, trail_stop)

            # NOTE: R-multiple trailing stop is updated on 10s bar closes, not per tick.
            # See on_10s_close() below. The stop level (t.stop) is checked here every tick.

            # Check stop (hard or trailed) — always active even during halt
            if price <= t.stop:
                reason = "trail_stop" if t.tp_hit else "stop_hit"
                if t._ross_partial_taken:
                    # Core (50%) was already exited by a Ross warning signal;
                    # stop hit now closes the remaining runner portion only.
                    t.runner_exit_price = price
                    t.runner_exit_time = time_str
                    t.runner_exit_reason = reason
                else:
                    t.core_exit_price = price
                    t.core_exit_time = time_str
                    t.core_exit_reason = reason
                self._close(t)
            return

        # --- Classic exit mode: core TP + runner trail ---

        # 1) Hard stop (before T1/TP hit) — exit all tranches
        if not t.tp_hit and price <= t.stop:
            t.core_exit_price = price
            t.core_exit_time = time_str
            t.core_exit_reason = "stop_hit"
            if t.qty_t2 > 0:
                t.t2_exit_price = price
                t.t2_exit_time = time_str
                t.t2_exit_reason = "stop_hit"
            t.runner_exit_price = price
            t.runner_exit_time = time_str
            t.runner_exit_reason = "stop_hit"
            self._close(t)
            return

        # 2) T1/Core take profit (with fuzz)
        if not t.tp_hit and t.qty_core > 0:
            tp_r = self.t1_tp_r if self.three_tranche_enabled else self.core_tp_r
            tp_core = t.entry + (tp_r * t.r)
            if price >= (tp_core - self.tp_fuzz):
                t.tp_hit = True
                t.core_exit_price = price
                t.core_exit_time = time_str
                t.core_exit_reason = "take_profit_t1" if self.three_tranche_enabled else "take_profit_core"
                # Move stop to breakeven
                t.runner_stop = max(t.stop, t.entry + self.be_offset)

        # 3) Post-T1 stop (T1 hit, T2 not yet, price falls to stop) — exit T2 + T3
        if self.three_tranche_enabled and t.tp_hit and not t.t2_hit:
            if price <= t.runner_stop:
                if t.qty_t2 > 0:
                    t.t2_exit_price = price
                    t.t2_exit_time = time_str
                    t.t2_exit_reason = "post_t1_stop"
                if t.qty_runner > 0:
                    t.runner_exit_price = price
                    t.runner_exit_time = time_str
                    t.runner_exit_reason = "post_t1_stop"
                self._close(t)
                return

        # 4) T2 take profit at 2R (3-tranche only)
        if self.three_tranche_enabled and t.tp_hit and not t.t2_hit and t.qty_t2 > 0:
            tp_t2 = t.entry + (self.t2_tp_r * t.r)
            if price >= (tp_t2 - self.tp_fuzz):
                t.t2_hit = True
                t.t2_exit_price = price
                t.t2_exit_time = time_str
                t.t2_exit_reason = "take_profit_t2"
                # Lock stop at entry + 0.5R
                lock_stop = t.entry + (self.t2_stop_lock_r * t.r)
                t.runner_stop = max(t.runner_stop, lock_stop)

        # 5) Runner/T3 trailing stop
        if t.tp_hit:
            trail_stop = t.peak - (self.runner_trail_r * t.r)
            t.runner_stop = max(t.runner_stop, trail_stop, t.entry + self.be_offset)

            if price <= t.runner_stop and t.qty_runner > 0:
                t.runner_exit_price = price
                t.runner_exit_time = time_str
                t.runner_exit_reason = "runner_stop_hit"
                # In 3-tranche: also close T2 if still open
                if self.three_tranche_enabled and not t.t2_hit and t.qty_t2 > 0:
                    t.t2_exit_price = price
                    t.t2_exit_time = time_str
                    t.t2_exit_reason = "runner_stop_hit"
                self._close(t)

    # ------------------------------------------------------------------
    # Squeeze exit logic
    # ------------------------------------------------------------------
    def _squeeze_tick_exits(self, t: SimTrade, price: float, time_str: str):
        """Tick-level exits for squeeze trades."""
        # 0) Absolute dollar loss cap (catches gap-throughs)
        if self.sq_max_loss_dollars > 0:
            unrealized_loss = (t.entry - price) * t.qty_total
            if unrealized_loss >= self.sq_max_loss_dollars:
                reason = f"sq_dollar_loss_cap (${unrealized_loss:,.0f} >= ${self.sq_max_loss_dollars:,.0f})"
                t.core_exit_price = price
                t.core_exit_time = time_str
                t.core_exit_reason = reason
                if t.qty_runner > 0:
                    t.runner_exit_price = price
                    t.runner_exit_time = time_str
                    t.runner_exit_reason = reason
                self._close(t)
                return

        # 1) Hard stop (always)
        if price <= t.stop:
            reason = "sq_stop_hit"
            t.core_exit_price = price
            t.core_exit_time = time_str
            t.core_exit_reason = reason
            if t.qty_runner > 0:
                t.runner_exit_price = price
                t.runner_exit_time = time_str
                t.runner_exit_reason = reason
            self._close(t)
            return

        # 2) Max loss cap (same as MP)
        _eff_mlr = self.max_loss_r
        if self._max_loss_r_tiered:
            _fm = None
            if self.stock_info and hasattr(self.stock_info, 'float_shares') and self.stock_info.float_shares:
                _fm = self.stock_info.float_shares
            elif self._scanner_float_m > 0:
                _fm = self._scanner_float_m
            if _fm is not None:
                if _fm < self._max_loss_r_thresh_low:
                    _eff_mlr = self._max_loss_r_ultra_low
                elif _fm <= self._max_loss_r_thresh_high:
                    _eff_mlr = self._max_loss_r_low
        if _eff_mlr > 0 and t.r > 0:
            loss_per_share = t.entry - price
            if loss_per_share >= _eff_mlr * t.r:
                t.core_exit_price = price
                t.core_exit_time = time_str
                t.core_exit_reason = "sq_max_loss_hit"
                if t.qty_runner > 0:
                    t.runner_exit_price = price
                    t.runner_exit_time = time_str
                    t.runner_exit_reason = "sq_max_loss_hit"
                self._close(t)
                return

        # --- Pre-target phase (full position) ---
        # When Ross exit is ON and coexist is OFF, skip mechanical trail and target exits entirely —
        # Ross 1m signals handle all exits. When coexist is ON, SQ/VR mechanical exits
        # run alongside Ross signals: SQ handles core exit at target, Ross handles runner.
        if not t.tp_hit and (not self.ross_exit_enabled or self.sq_ross_coexist):
            # 3) Trailing stop (pre-target) — tighter for parabolic entries
            # Halt-through: skip trail during halt/grace (hard stop above still active)
            if t.r > 0 and not (self._halt_through_enabled and self._is_sim_halt_active(t)):
                is_parabolic = "[PARABOLIC]" in (t.score_detail or "")
                trail_r = self.sq_para_trail_r if is_parabolic else self.sq_trail_r
                # Fix 2: widen trail to give winners more room
                if self.sq_wide_trail_enabled:
                    trail_r *= self.sq_trail_multiplier
                trail_price = t.peak - (trail_r * t.r)
                if price <= trail_price:
                    reason = "sq_para_trail_exit" if is_parabolic else "sq_trail_exit"
                    t.core_exit_price = price
                    t.core_exit_time = time_str
                    t.core_exit_reason = reason
                    if t.qty_runner > 0:
                        t.runner_exit_price = price
                        t.runner_exit_time = time_str
                        t.runner_exit_reason = reason
                    self._close(t)
                    return

            # 4) Target hit — exit core (partial or full), keep runner
            if t.r > 0 and price >= t.entry + (self.sq_target_r * t.r):
                t.tp_hit = True
                t.core_exit_price = price
                t.core_exit_time = time_str
                t.core_exit_reason = "sq_target_hit"
                # Move runner stop to breakeven
                t.runner_stop = max(t.stop, t.entry + 0.01)
                # Fix 3: record when target was hit for runner detection
                if self.sq_runner_detect_enabled:
                    self._sq_target_hit_min = self._time_to_minutes(time_str)
                return

        # --- Post-target phase (runner only) ---
        # Skipped when Ross exit is ON (unless coexist allows SQ runner management)
        if t.tp_hit and t.qty_runner > 0 and t.runner_exit_price == 0 and (not self.ross_exit_enabled or self.sq_ross_coexist):
            # Runner trailing stop
            # Halt-through: skip trail update/check during halt/grace
            if t.r > 0 and not (self._halt_through_enabled and self._is_sim_halt_active(t)):
                eff_runner_trail_r = self.sq_runner_trail_r
                # Fix 2: apply multiplier to runner trail too
                if self.sq_wide_trail_enabled:
                    eff_runner_trail_r *= self.sq_trail_multiplier
                # Fix 3: runner detection — target hit within 5 minutes → 3x trail
                if (self.sq_runner_detect_enabled and self._sq_target_hit_min is not None):
                    now_min = self._time_to_minutes(time_str)
                    minutes_since_target = now_min - self._sq_target_hit_min
                    if minutes_since_target <= 5 and price >= t.entry + (self.sq_target_r * t.r):
                        eff_runner_trail_r = self.sq_runner_trail_r * 3.0
                runner_trail = t.peak - (eff_runner_trail_r * t.r)
                t.runner_stop = max(t.runner_stop, runner_trail)

            if price <= t.runner_stop and not (self._halt_through_enabled and self._is_sim_halt_active(t)):
                t.runner_exit_price = price
                t.runner_exit_time = time_str
                t.runner_exit_reason = "sq_runner_trail"
                self._close(t)
                return

    def on_1m_bar_close_squeeze(self, t: SimTrade, o: float, h: float, l: float,
                                c: float, v: float, vwap: Optional[float],
                                time_str: str):
        """1m bar-level exits for squeeze trades and mp_reentry (stall + VWAP loss)."""
        if t is None or t.closed or t.setup_type not in ("squeeze", "mp_reentry", "continuation"):
            return

        self._sq_last_vwap = vwap

        # Stall counter: increment if no new high on this bar
        if h <= t.peak:
            self._sq_bars_no_new_high += 1
        else:
            self._sq_bars_no_new_high = 0

        # Time stop: no new high in N bars
        if self._sq_bars_no_new_high >= self.sq_stall_bars:
            if not t.tp_hit:
                # Exit full position
                t.core_exit_price = c
                t.core_exit_time = time_str
                t.core_exit_reason = f"sq_time_exit({self._sq_bars_no_new_high}bars)"
                if t.qty_runner > 0:
                    t.runner_exit_price = c
                    t.runner_exit_time = time_str
                    t.runner_exit_reason = f"sq_time_exit({self._sq_bars_no_new_high}bars)"
                self._close(t)
                return
            elif t.qty_runner > 0 and t.runner_exit_price == 0:
                # Exit runner only
                t.runner_exit_price = c
                t.runner_exit_time = time_str
                t.runner_exit_reason = f"sq_runner_time_exit({self._sq_bars_no_new_high}bars)"
                self._close(t)
                return

        # VWAP loss exit
        if self.sq_vwap_exit and vwap is not None and c < vwap:
            if not t.tp_hit:
                t.core_exit_price = c
                t.core_exit_time = time_str
                t.core_exit_reason = "sq_vwap_exit"
                if t.qty_runner > 0:
                    t.runner_exit_price = c
                    t.runner_exit_time = time_str
                    t.runner_exit_reason = "sq_vwap_exit"
                self._close(t)
                return
            elif t.qty_runner > 0 and t.runner_exit_price == 0:
                t.runner_exit_price = c
                t.runner_exit_time = time_str
                t.runner_exit_reason = "sq_runner_vwap_exit"
                self._close(t)
                return

    # ------------------------------------------------------------------
    # VWAP Reclaim tick-level exit logic (Strategy 4)
    # ------------------------------------------------------------------
    def _vr_tick_exits(self, t: SimTrade, price: float, time_str: str):
        """Tick-level exits for VWAP reclaim trades."""
        # 0) Absolute dollar loss cap
        if self.vr_max_loss_dollars > 0:
            unrealized_loss = (t.entry - price) * t.qty_total
            if unrealized_loss >= self.vr_max_loss_dollars:
                reason = f"vr_dollar_loss_cap (${unrealized_loss:,.0f} >= ${self.vr_max_loss_dollars:,.0f})"
                t.core_exit_price = price
                t.core_exit_time = time_str
                t.core_exit_reason = reason
                if t.qty_runner > 0:
                    t.runner_exit_price = price
                    t.runner_exit_time = time_str
                    t.runner_exit_reason = reason
                self._close(t)
                return

        # 1) Hard stop
        if price <= t.stop:
            t.core_exit_price = price
            t.core_exit_time = time_str
            t.core_exit_reason = "vr_stop_hit"
            if t.qty_runner > 0:
                t.runner_exit_price = price
                t.runner_exit_time = time_str
                t.runner_exit_reason = "vr_stop_hit"
            self._close(t)
            return

        # 2) Max loss R cap (same logic as squeeze)
        _eff_mlr = self.max_loss_r
        if _eff_mlr > 0 and t.r > 0:
            loss_per_share = t.entry - price
            if loss_per_share >= _eff_mlr * t.r:
                t.core_exit_price = price
                t.core_exit_time = time_str
                t.core_exit_reason = "vr_max_loss_hit"
                if t.qty_runner > 0:
                    t.runner_exit_price = price
                    t.runner_exit_time = time_str
                    t.runner_exit_reason = "vr_max_loss_hit"
                self._close(t)
                return

        # --- Pre-target phase ---
        # When Ross exit is ON and coexist is OFF, skip mechanical exits.
        # When coexist is ON, VR mechanical exits run alongside Ross signals.
        if not t.tp_hit and (not self.ross_exit_enabled or self.sq_ross_coexist):
            # Trailing stop (pre-target)
            if t.r > 0:
                trail_price = t.peak - (self.vr_trail_r * t.r)
                if price <= trail_price:
                    t.core_exit_price = price
                    t.core_exit_time = time_str
                    t.core_exit_reason = "vr_trail_exit"
                    if t.qty_runner > 0:
                        t.runner_exit_price = price
                        t.runner_exit_time = time_str
                        t.runner_exit_reason = "vr_trail_exit"
                    self._close(t)
                    return

            # Core TP: hit target R → close core, keep runner
            if t.r > 0 and price >= t.entry + (self.vr_target_r * t.r):
                t.tp_hit = True
                t.core_exit_price = price
                t.core_exit_time = time_str
                t.core_exit_reason = f"vr_core_tp_{self.vr_target_r}R"
                if t.qty_runner > 0:
                    t.runner_stop = max(t.runner_stop, t.entry + 0.01)
                else:
                    self._close(t)
                return
        elif not self.ross_exit_enabled or self.sq_ross_coexist:
            # --- Post-target: runner management ---
            if t.qty_runner > 0 and t.runner_exit_price == 0:
                runner_trail = t.peak - (self.vr_runner_trail_r * t.r)
                if price <= runner_trail:
                    t.runner_exit_price = price
                    t.runner_exit_time = time_str
                    t.runner_exit_reason = "vr_runner_trail"
                    self._close(t)
                    return

    def on_1m_bar_close_vr(self, t: SimTrade, o: float, h: float, l: float,
                           c: float, v: float, vwap: Optional[float],
                           time_str: str):
        """1m bar-level exits for VWAP reclaim trades (stall + VWAP loss)."""
        if t is None or t.closed or t.setup_type != "vwap_reclaim":
            return

        self._vr_last_vwap = vwap

        # Stall counter
        if h <= t.peak:
            self._vr_bars_no_new_high += 1
        else:
            self._vr_bars_no_new_high = 0

        # Time stop: no new high in N bars
        if self._vr_bars_no_new_high >= self.vr_stall_bars:
            if not t.tp_hit:
                t.core_exit_price = c
                t.core_exit_time = time_str
                t.core_exit_reason = f"vr_time_exit({self._vr_bars_no_new_high}bars)"
                if t.qty_runner > 0:
                    t.runner_exit_price = c
                    t.runner_exit_time = time_str
                    t.runner_exit_reason = f"vr_time_exit({self._vr_bars_no_new_high}bars)"
                self._close(t)
                return
            elif t.qty_runner > 0 and t.runner_exit_price == 0:
                t.runner_exit_price = c
                t.runner_exit_time = time_str
                t.runner_exit_reason = f"vr_runner_time_exit({self._vr_bars_no_new_high}bars)"
                self._close(t)
                return

        # VWAP loss exit (CRITICAL for VWAP reclaim — thesis is dead if VWAP lost again)
        if self.vr_vwap_exit and vwap is not None and c < vwap:
            if not t.tp_hit:
                t.core_exit_price = c
                t.core_exit_time = time_str
                t.core_exit_reason = "vr_vwap_exit"
                if t.qty_runner > 0:
                    t.runner_exit_price = c
                    t.runner_exit_time = time_str
                    t.runner_exit_reason = "vr_vwap_exit"
                self._close(t)
                return
            elif t.qty_runner > 0 and t.runner_exit_price == 0:
                t.runner_exit_price = c
                t.runner_exit_time = time_str
                t.runner_exit_reason = "vr_runner_vwap_exit"
                self._close(t)
                return

    def force_close(self, price: float, time_str: str):
        t = self.open_trade
        if t is None or t.closed:
            return
        if not t.tp_hit:
            t.core_exit_price = price
            t.core_exit_time = time_str
            t.core_exit_reason = "sim_end"
        if t.qty_t2 > 0 and not t.t2_hit:
            t.t2_exit_price = price
            t.t2_exit_time = time_str
            t.t2_exit_reason = "sim_end"
        if t.qty_runner > 0:
            t.runner_exit_price = price
            t.runner_exit_time = time_str
            t.runner_exit_reason = "sim_end"
        self._close(t)

    def on_exit_signal(self, signal_name: str, price: float, time_str: str):
        """Handle pattern-based exit signals (topping_wicky, l2_bearish, etc.)."""
        t = self.open_trade
        # Halt-through: suppress pattern exits during halt/grace (hard stops handled in on_tick)
        _halt_pattern_exits = ("topping_wicky", "bearish_engulfing", "chandelier_stop",
                               "parabolic_exhaustion", "5m_trend_guard_exit")
        if (self._halt_through_enabled and t is not None and not t.closed
                and signal_name in _halt_pattern_exits
                and self._is_sim_halt_active(t)):
            return
        if t is None or t.closed:
            return

        # Signal mode: exit signals always close the full position
        if self.exit_mode == "signal":
            t.core_exit_price = price
            t.core_exit_time = time_str
            t.core_exit_reason = f"{signal_name}_exit_full"
            self._close(t)
            return

        # Classic mode: pre-TP exits full, post-TP exits remaining tranches
        if not t.tp_hit:
            t.core_exit_price = price
            t.core_exit_time = time_str
            t.core_exit_reason = f"{signal_name}_exit_full"
            if t.qty_t2 > 0:
                t.t2_exit_price = price
                t.t2_exit_time = time_str
                t.t2_exit_reason = f"{signal_name}_exit_full"
            t.runner_exit_price = price
            t.runner_exit_time = time_str
            t.runner_exit_reason = f"{signal_name}_exit_full"
            self._close(t)
        else:
            # Post-T1: exit remaining T2 + T3
            if t.qty_t2 > 0 and not t.t2_hit:
                t.t2_exit_price = price
                t.t2_exit_time = time_str
                t.t2_exit_reason = f"{signal_name}_exit_remaining"
            if t.qty_runner > 0:
                t.runner_exit_price = price
                t.runner_exit_time = time_str
                t.runner_exit_reason = f"{signal_name}_exit_runner"
            if t.qty_t2 > 0 or t.qty_runner > 0:
                self._close(t)

    def on_ross_exit_signal(
        self,
        action: str,
        signal_name: str,
        price: float,
        time_str: str,
        verbose: bool = False,
    ):
        """
        Handle a Ross exit signal emitted by RossExitManager.

        action="partial_50"  → exit core tranche (50%), keep runner open.
        action="full_100"    → exit remaining position entirely.
        """
        t = self.open_trade
        if t is None or t.closed:
            return

        if action == "partial_50":
            if t.tp_hit:
                return  # partial already taken — ignore subsequent doji warnings
            # Exit the core (50%) portion
            t.core_exit_price = price
            t.core_exit_time = time_str
            t.core_exit_reason = signal_name
            t.tp_hit = True
            t._ross_partial_taken = True
            # Keep the original pattern stop — DO NOT tighten to BE here.
            # The runner holds with the structural stop (original pattern low).
            # CUC, MACD, EMA20, or VWAP will exit the runner on the next 1m bar.
            # Tightening to BE immediately would stop the runner out on the next tick.
            if verbose:
                print(
                    f"  [{time_str}] ROSS_PARTIAL_50 ({signal_name}) "
                    f"@ {price:.4f} — {t.qty_core} shares exited, "
                    f"{t.qty_runner} runner shares remain (stop stays @ {t.stop:.4f})",
                    flush=True,
                )
            # DO NOT call _close() — runner portion is still live

        elif action == "full_100":
            if t._ross_partial_taken:
                # Core already sold on warning; now exit runner only
                t.runner_exit_price = price
                t.runner_exit_time = time_str
                t.runner_exit_reason = signal_name
            else:
                # No prior partial — close entire position at once
                t.core_exit_price = price
                t.core_exit_time = time_str
                t.core_exit_reason = signal_name
                if t.qty_runner > 0:
                    t.runner_exit_price = price
                    t.runner_exit_time = time_str
                    t.runner_exit_reason = signal_name
            if verbose:
                print(
                    f"  [{time_str}] ROSS_FULL_100 ({signal_name}) @ {price:.4f}",
                    flush=True,
                )
            self._close(t)

    def on_bar_close_1m_cooldown(self):
        """Decrement stop-hit cooldowns on each 1m bar close."""
        for sym in list(self._stop_hit_cooldown):
            self._stop_hit_cooldown[sym] -= 1
            if self._stop_hit_cooldown[sym] <= 0:
                del self._stop_hit_cooldown[sym]

    def _close(self, t: SimTrade):
        t.closed = True
        self.closed_trades.append(t)
        # Release notional and update equity for buying power tracking
        if self.account_equity > 0:
            self.open_notional -= t.qty_total * t.entry  # release original notional
            self.open_notional = max(0.0, self.open_notional)  # safety clamp
            self.current_equity += t.pnl()  # adjust equity by P&L
        # If closed by stop_hit or max_loss_hit, start re-entry cooldown
        _loss_reasons = ("stop_hit", "max_loss_hit") if self._max_loss_triggers_cooldown else ("stop_hit",)
        if self.reentry_cooldown_bars > 0 and t.core_exit_reason in _loss_reasons:
            self._stop_hit_cooldown[t.symbol] = self.reentry_cooldown_bars
        self.open_trade = None
        # Notify quality gate of trade result
        if self.on_trade_close is not None:
            self.on_trade_close(t)


# ─────────────────────────────────────────────
# Data fetching
# ─────────────────────────────────────────────

def fetch_bars(symbol: str, start_utc: datetime, end_utc: datetime) -> list:
    req = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute,
        start=start_utc,
        end=end_utc,
        feed="sip",
    )
    return hist_client.get_stock_bars(req).data.get(symbol, [])


def fetch_trades(symbol: str, start_utc: datetime, end_utc: datetime) -> list:
    """Fetch tick-level trade data from Alpaca for high-fidelity backtesting."""
    import time as _time
    req = StockTradesRequest(
        symbol_or_symbols=[symbol],
        start=start_utc,
        end=end_utc,
        feed="sip",
    )
    for attempt in range(3):
        try:
            trade_set = hist_client.get_stock_trades(req)
            return trade_set.data.get(symbol, [])
        except Exception as e:
            if attempt < 2:
                wait = 2 ** attempt  # 1s, 2s
                print(f"  [RETRY] fetch_trades {symbol}: {e} — retrying in {wait}s", flush=True)
                _time.sleep(wait)
            else:
                print(f"  [FAILED] fetch_trades {symbol}: {e} — all retries exhausted", flush=True)
                raise


def synthetic_ticks(o, h, l, c):
    """O→H→L→C for green bars, O→L→H→C for red bars."""
    if c >= o:
        return [o, h, l, c]
    else:
        return [o, l, h, c]


# ─────────────────────────────────────────────
# Behavior Study Metrics (--export-json)
# ─────────────────────────────────────────────

class BehaviorMetrics:
    """Accumulates behavioral metrics over 1-minute bars for the study export."""

    def __init__(self, sim_start_time: str):
        self.sim_start_time = sim_start_time
        self.sim_start_min = self._to_min(sim_start_time)
        self._bars: list[dict] = []  # all 1m bars: {o, h, l, c, v, time_str, vwap}
        self._running_high = 0.0
        self._last_high_time: str = ""
        self._new_high_times: list[int] = []  # minutes-since-midnight of each new high
        self._pullbacks: list[dict] = []  # {depth_pct, start_min, end_min}
        self._in_pullback = False
        self._pullback_start_high = 0.0
        self._pullback_start_min = 0
        self._pullback_low = 0.0

    @staticmethod
    def _to_min(t: str) -> int:
        parts = t.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    def on_1m_bar(self, o: float, h: float, l: float, c: float, v: float,
                  time_str: str, vwap: float = 0.0):
        bar = {"o": o, "h": h, "l": l, "c": c, "v": v, "time": time_str, "vwap": vwap}
        self._bars.append(bar)
        bar_min = self._to_min(time_str)

        # New high tracking (close > all prior closes)
        prior_closes = [b["c"] for b in self._bars[:-1]]
        if not prior_closes or c > max(prior_closes):
            self._new_high_times.append(bar_min)

        # Running high for pullback tracking
        if h > self._running_high:
            self._running_high = h
            self._last_high_time = time_str

        # Pullback detection
        if self._running_high > 0:
            drop_pct = (self._running_high - l) / self._running_high * 100
            if not self._in_pullback and drop_pct > 0.3:
                self._in_pullback = True
                self._pullback_start_high = self._running_high
                self._pullback_start_min = bar_min
                self._pullback_low = l
            elif self._in_pullback:
                self._pullback_low = min(self._pullback_low, l)
                if c > self._pullback_start_high:
                    depth = (self._pullback_start_high - self._pullback_low) / self._pullback_start_high * 100
                    self._pullbacks.append({
                        "depth_pct": depth,
                        "start_min": self._pullback_start_min,
                        "end_min": bar_min,
                    })
                    self._in_pullback = False

    def _first_n_bars(self, n: int) -> list[dict]:
        return self._bars[:n]

    def snapshot_at(self, minutes: int) -> dict:
        """Return classifier-ready metrics from the first N minutes of bars.

        Recomputes everything on the truncated subset so the classifier
        sees ONLY what it would see in real-time.
        """
        bars = self._bars[:minutes]
        if not bars:
            return {
                "new_high_count": 0, "pullback_count": 0,
                "pullback_depth_avg_pct": 0, "green_bar_ratio": 0,
                "max_vwap_distance_pct": 0, "price_range_pct": 0,
                "vol_total": 0,
            }

        # New-high count (close > all prior closes)
        nh_count = 0
        for i, b in enumerate(bars):
            prior = [bb["c"] for bb in bars[:i]]
            if not prior or b["c"] > max(prior):
                nh_count += 1

        # Pullback detection on the subset
        running_high = 0.0
        in_pb = False
        pb_start_high = 0.0
        pb_low = 0.0
        pullbacks: list[float] = []
        for b in bars:
            if b["h"] > running_high:
                running_high = b["h"]
            if running_high > 0:
                drop = (running_high - b["l"]) / running_high * 100
                if not in_pb and drop > 0.3:
                    in_pb = True
                    pb_start_high = running_high
                    pb_low = b["l"]
                elif in_pb:
                    pb_low = min(pb_low, b["l"])
                    if b["c"] > pb_start_high:
                        depth = (pb_start_high - pb_low) / pb_start_high * 100
                        pullbacks.append(depth)
                        in_pb = False

        pb_count = len(pullbacks)
        pb_depth_avg = statistics.mean(pullbacks) if pullbacks else 0

        # Green bar ratio
        greens = sum(1 for b in bars if b["c"] >= b["o"])
        green_ratio = greens / len(bars)

        # Price range
        hi = max(b["h"] for b in bars)
        lo = min(b["l"] for b in bars)
        range_pct = (hi - lo) / lo * 100 if lo > 0 else 0

        # VWAP distance
        max_vwap_dist = 0
        for b in bars:
            if b.get("vwap", 0) > 0:
                dist = abs(b["c"] - b["vwap"]) / b["vwap"] * 100
                max_vwap_dist = max(max_vwap_dist, dist)

        # Volume
        vol_total = sum(b["v"] for b in bars)

        return {
            "new_high_count": nh_count,
            "pullback_count": pb_count,
            "pullback_depth_avg_pct": round(pb_depth_avg, 2),
            "green_bar_ratio": round(green_ratio, 2),
            "max_vwap_distance_pct": round(max_vwap_dist, 2),
            "price_range_pct": round(range_pct, 2),
            "vol_total": int(vol_total),
        }

    def to_dict(self) -> dict:
        bars_30m = self._first_n_bars(30)
        if not bars_30m:
            return {}

        # --- NEW HIGH BEHAVIOR ---
        cutoff_min = self.sim_start_min + 30
        nh_30 = [t for t in self._new_high_times if t < cutoff_min]
        nh_count = len(nh_30)
        if len(nh_30) >= 2:
            cadences = [(nh_30[i+1] - nh_30[i]) * 60 for i in range(len(nh_30)-1)]
            nh_cadence_avg = statistics.mean(cadences)
            nh_cadence_std = statistics.stdev(cadences) if len(cadences) > 1 else 0
        else:
            nh_cadence_avg = 0
            nh_cadence_std = 0

        # --- PULLBACK BEHAVIOR ---
        pb_30 = [p for p in self._pullbacks if p["start_min"] < cutoff_min]
        pb_count = len(pb_30)
        pb_depth_avg = statistics.mean([p["depth_pct"] for p in pb_30]) if pb_30 else 0
        pb_depth_max = max([p["depth_pct"] for p in pb_30]) if pb_30 else 0
        pb_recovery_avg = statistics.mean([(p["end_min"] - p["start_min"]) * 60 for p in pb_30]) if pb_30 else 0

        # --- VOLUME SHAPE ---
        vols = [b["v"] for b in bars_30m]
        vol_total = sum(vols)
        vol_first_5m = sum(vols[:5])
        last_5_start = max(0, len(bars_30m) - 5)
        vol_last_5m = sum(vols[last_5_start:])
        vol_decay = vol_last_5m / vol_first_5m if vol_first_5m > 0 else 0
        spike_count = 0
        for i, v in enumerate(vols):
            start_idx = max(0, i - 5)
            window = vols[start_idx:i] if i > 0 else [v]
            avg_w = statistics.mean(window) if window else v
            if avg_w > 0 and v > 2 * avg_w:
                spike_count += 1

        # --- TREND STRENGTH ---
        greens = sum(1 for b in bars_30m if b["c"] >= b["o"])
        green_ratio = greens / len(bars_30m) if bars_30m else 0
        max_consec_green = max_consec_red = cur_green = cur_red = 0
        for b in bars_30m:
            if b["c"] >= b["o"]:
                cur_green += 1
                cur_red = 0
            else:
                cur_red += 1
                cur_green = 0
            max_consec_green = max(max_consec_green, cur_green)
            max_consec_red = max(max_consec_red, cur_red)
        first_c = bars_30m[0]["o"]
        last_c = bars_30m[-1]["c"]
        hi_30 = max(b["h"] for b in bars_30m)
        lo_30 = min(b["l"] for b in bars_30m)
        range_pct = (hi_30 - lo_30) / lo_30 * 100 if lo_30 > 0 else 0

        # --- BAR CHARACTER ---
        uw_ratios = []
        body_ratios = []
        for b in bars_30m:
            rng = b["h"] - b["l"]
            if rng > 0:
                upper_wick = b["h"] - max(b["o"], b["c"])
                body = abs(b["c"] - b["o"])
                uw_ratios.append(upper_wick / rng)
                body_ratios.append(body / rng)
        uw_avg = statistics.mean(uw_ratios) if uw_ratios else 0
        body_avg = statistics.mean(body_ratios) if body_ratios else 0
        bars_last_10 = bars_30m[max(0, len(bars_30m)-10):]
        uw_last10 = []
        body_last10 = []
        for b in bars_last_10:
            rng = b["h"] - b["l"]
            if rng > 0:
                uw_last10.append((b["h"] - max(b["o"], b["c"])) / rng)
                body_last10.append(abs(b["c"] - b["o"]) / rng)
        uw_avg_last10 = statistics.mean(uw_last10) if uw_last10 else 0
        body_avg_last10 = statistics.mean(body_last10) if body_last10 else 0

        # --- VWAP RELATIONSHIP ---
        bars_with_vwap = [b for b in bars_30m if b["vwap"] > 0]
        above_vwap = sum(1 for b in bars_with_vwap if b["c"] > b["vwap"])
        pct_above_vwap = above_vwap / len(bars_with_vwap) if bars_with_vwap else 0
        vwap_crosses = 0
        for i in range(1, len(bars_with_vwap)):
            prev_above = bars_with_vwap[i-1]["c"] > bars_with_vwap[i-1]["vwap"]
            curr_above = bars_with_vwap[i]["c"] > bars_with_vwap[i]["vwap"]
            if prev_above != curr_above:
                vwap_crosses += 1
        max_vwap_dist = 0
        for b in bars_with_vwap:
            if b["vwap"] > 0:
                dist = abs(b["c"] - b["vwap"]) / b["vwap"] * 100
                max_vwap_dist = max(max_vwap_dist, dist)

        # --- PRICE AT KEY TIMESTAMPS ---
        def _price_at_offset(offset_min: int) -> float | None:
            target = self.sim_start_min + offset_min
            for b in self._bars:
                if self._to_min(b["time"]) >= target:
                    return b["c"]
            return None

        def _high_by_offset(offset_min: int) -> float | None:
            target = self.sim_start_min + offset_min
            matching = [b for b in self._bars if self._to_min(b["time"]) < target]
            return max(b["h"] for b in matching) if matching else None

        def _low_by_offset(offset_min: int) -> float | None:
            target = self.sim_start_min + offset_min
            matching = [b for b in self._bars if self._to_min(b["time"]) < target]
            return min(b["l"] for b in matching) if matching else None

        return {
            "new_high_count_30m": nh_count,
            "new_high_cadence_avg_sec": round(nh_cadence_avg, 1),
            "new_high_cadence_stdev_sec": round(nh_cadence_std, 1),
            "pullback_count_30m": pb_count,
            "pullback_depth_avg_pct": round(pb_depth_avg, 2),
            "pullback_depth_max_pct": round(pb_depth_max, 2),
            "pullback_recovery_avg_sec": round(pb_recovery_avg, 0),
            "vol_spike_count_30m": spike_count,
            "vol_total_30m": int(vol_total),
            "vol_first_5m": int(vol_first_5m),
            "vol_last_5m_of_30": int(vol_last_5m),
            "vol_decay_ratio": round(vol_decay, 3),
            "green_bar_ratio_30m": round(green_ratio, 2),
            "max_consecutive_green": max_consec_green,
            "max_consecutive_red": max_consec_red,
            "price_range_30m_pct": round(range_pct, 2),
            "upper_wick_ratio_avg": round(uw_avg, 3),
            "upper_wick_ratio_last_10m": round(uw_avg_last10, 3),
            "body_ratio_avg": round(body_avg, 3),
            "body_ratio_last_10m": round(body_avg_last10, 3),
            "pct_bars_above_vwap_30m": round(pct_above_vwap, 2),
            "vwap_cross_count_30m": vwap_crosses,
            "max_vwap_distance_pct": round(max_vwap_dist, 2),
            "price_at_5m": _price_at_offset(5),
            "price_at_10m": _price_at_offset(10),
            "price_at_15m": _price_at_offset(15),
            "price_at_30m": _price_at_offset(30),
            "price_at_60m": _price_at_offset(60),
            "high_at_30m": _high_by_offset(30),
            "high_at_60m": _high_by_offset(60),
            "low_at_30m": _low_by_offset(30),
            "low_at_60m": _low_by_offset(60),
        }

    def get_post_exit_data(self, exit_time: str, entry_price: float, exit_price: float) -> dict:
        """Get price data at intervals after a trade exit."""
        exit_min = self._to_min(exit_time)

        def _price_after(offset_min: int) -> float | None:
            target = exit_min + offset_min
            for b in self._bars:
                if self._to_min(b["time"]) >= target:
                    return b["c"]
            return None

        # High/low in 30 minutes after exit
        bars_after = [b for b in self._bars
                      if exit_min < self._to_min(b["time"]) <= exit_min + 30]
        high_after = max((b["h"] for b in bars_after), default=None)
        low_after = min((b["l"] for b in bars_after), default=None)

        # Left on table calculation
        left_on_table = None
        if high_after is not None and entry_price > 0:
            denom = high_after - entry_price
            if denom > 0:
                left_on_table = round((high_after - exit_price) / denom * 100, 1)
                left_on_table = max(0, min(100, left_on_table))
            else:
                left_on_table = 0

        return {
            "price_1m_after_exit": _price_after(1),
            "price_5m_after_exit": _price_after(5),
            "price_10m_after_exit": _price_after(10),
            "price_30m_after_exit": _price_after(30),
            "high_after_exit_30m": high_after,
            "low_after_exit_30m": low_after,
            "left_on_table_pct": left_on_table,
        }


def export_study_json(symbol: str, date_str: str, start_et: str, end_et: str,
                      trades: list, metrics: BehaviorMetrics,
                      stock_info, config: dict):
    """Write the study JSON file after simulation completes."""
    os.makedirs("study_data", exist_ok=True)
    outpath = f"study_data/{symbol}_{date_str}.json"

    # Fundamentals
    fundamentals = {}
    if stock_info:
        fundamentals["gap_pct"] = getattr(stock_info, "gap_pct", None)
        fundamentals["float_shares"] = getattr(stock_info, "float_shares", None)
    if metrics._bars:
        fundamentals["price_at_sim_start"] = metrics._bars[0]["o"]

    # Per-trade data
    trade_list = []
    for i, t in enumerate(trades):
        exit_price = t.core_exit_price if t.core_exit_price > 0 else t.entry
        exit_time = t.core_exit_time or t.entry_time
        exit_reason = t.core_exit_reason or "unknown"
        hold_sec = 0
        if t.entry_time and exit_time:
            e_min = BehaviorMetrics._to_min(t.entry_time)
            x_min = BehaviorMetrics._to_min(exit_time)
            hold_sec = (x_min - e_min) * 60

        peak_r = (t.peak - t.entry) / t.r if t.r > 0 else 0
        time_to_peak = 0
        if t.entry_time and t.peak_time:
            time_to_peak = (BehaviorMetrics._to_min(t.peak_time) - BehaviorMetrics._to_min(t.entry_time)) * 60
        dd_from_peak = 0
        if t.peak > 0:
            dd_from_peak = (t.peak - exit_price) / t.peak * 100

        # Extract tags from score_detail (format: "macd=7.5*0.6;bull_struct=+3;vol_surge=+2")
        tag_names = []
        _skip_tags = {"macd"}
        for part in (t.score_detail or "").split(";"):
            name = part.split("=")[0].strip()
            # Skip macd, R-threshold entries, and empty/numeric names
            if not name or name.startswith("R>") or name in _skip_tags:
                continue
            tag_names.append(name)

        td = {
            "trade_num": i + 1,
            "entry_price": round(t.entry, 4),
            "entry_time": t.entry_time,
            "stop": round(t.stop, 4),
            "r": round(t.r, 4),
            "score": t.score,
            "score_detail": t.score_detail,
            "tags": tag_names,
            "exit_price": round(exit_price, 4),
            "exit_time": exit_time,
            "exit_reason": exit_reason,
            "pnl": round(t.pnl(), 2),
            "r_multiple": round(t.r_multiple(), 2),
            "qty": t.qty_total,
            "hold_time_sec": hold_sec,
            "peak_price": round(t.peak, 4),
            "peak_time": t.peak_time,
            "peak_unrealized_r": round(peak_r, 2),
            "time_to_peak_sec": time_to_peak,
            "drawdown_from_peak_at_exit_pct": round(dd_from_peak, 2),
        }

        # Post-exit tracking
        if exit_time:
            post = metrics.get_post_exit_data(exit_time, t.entry, exit_price)
            td.update(post)

        trade_list.append(td)

    # Summary
    wins = sum(1 for t in trades if t.pnl() >= 0)
    losses = sum(1 for t in trades if t.pnl() < 0)
    total = wins + losses
    net_pnl = sum(t.pnl() for t in trades)
    avg_r = statistics.mean([t.r_multiple() for t in trades]) if trades else 0
    avg_hold = statistics.mean([td["hold_time_sec"] for td in trade_list]) if trade_list else 0
    lot_vals = [td.get("left_on_table_pct") for td in trade_list if td.get("left_on_table_pct") is not None]
    avg_lot = statistics.mean(lot_vals) if lot_vals else 0

    result = {
        "symbol": symbol,
        "date": date_str,
        "sim_start": start_et,
        "sim_end": end_et,
        "config": config,
        "fundamentals": fundamentals,
        "stock_metrics": metrics.to_dict(),
        "trades": trade_list,
        "summary": {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "net_pnl": round(net_pnl, 2),
            "avg_r": round(avg_r, 2),
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            "avg_hold_time_sec": round(avg_hold, 0),
            "total_left_on_table_pct_avg": round(avg_lot, 1),
        },
    }

    with open(outpath, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  Study JSON exported: {outpath}", flush=True)


# ─────────────────────────────────────────────
# Simulation engine
# ─────────────────────────────────────────────

def run_simulation(
    symbol: str,
    date_str: str,
    start_et_str: str = "09:30",
    end_et_str: str = "16:00",
    risk_dollars: float = None,
    min_score: float = None,
    slippage: float = 0.02,
    verbose: bool = False,
    use_l2: bool = False,
    use_l2_entry: bool = False,
    no_fundamentals: bool = False,
    use_ticks: bool = False,
    feed: str = "alpaca",
    export_json: bool = False,
    profile: str = "A",
    candidates_count: int = 0,
    gap_pct: float = 0.0,
    pm_volume: float = 0.0,
    tick_cache: str = None,
):
    # Parse times
    date = datetime.strptime(date_str, "%Y-%m-%d")

    sh, sm = map(int, start_et_str.split(":"))
    eh, em = map(int, end_et_str.split(":"))

    sim_start_et = ET.localize(date.replace(hour=sh, minute=sm, second=0, microsecond=0))
    sim_end_et = ET.localize(date.replace(hour=eh, minute=em, second=0, microsecond=0))

    # Seed from 4 AM ET to capture full premarket
    seed_start_et = ET.localize(date.replace(hour=4, minute=0, second=0, microsecond=0))

    seed_start_utc = seed_start_et.astimezone(timezone.utc)
    sim_start_utc = sim_start_et.astimezone(timezone.utc)
    sim_end_utc = sim_end_et.astimezone(timezone.utc)

    # Override env vars for this simulation run
    if min_score is not None:
        os.environ["WB_MIN_SCORE"] = str(min_score)
    if risk_dollars is not None:
        os.environ["WB_RISK_DOLLARS"] = str(risk_dollars)

    # Read settings (after possible overrides)
    _risk = float(os.getenv("WB_RISK_DOLLARS", "1000"))
    _min_score = float(os.getenv("WB_MIN_SCORE", "3"))
    _scale_core = float(os.getenv("WB_SCALE_CORE", "0.65"))
    _min_r = float(os.getenv("WB_MIN_R", "0.06"))
    _max_notional = float(os.getenv("WB_MAX_NOTIONAL", "50000"))
    _max_shares = int(os.getenv("WB_MAX_SHARES", "100000"))
    _core_tp_r = float(os.getenv("WB_CORE_TP_R", "1.0"))
    _tp_fuzz = float(os.getenv("WB_TP_FUZZ", "0.03"))
    _be_offset = float(os.getenv("WB_BE_OFFSET", "0.01"))
    _runner_trail_r = float(os.getenv("WB_RUNNER_TRAIL_R", "1.0"))
    _macd_gate = os.getenv("WB_MACD_HARD_GATE", "1") == "1"
    _exit_mode = os.getenv("WB_EXIT_MODE", "signal")
    _be_trigger_r = float(os.getenv("WB_BE_TRIGGER_R", "1.0"))
    _signal_trail_pct = float(os.getenv("WB_SIGNAL_TRAIL_PCT", "0.05"))
    _max_entries = int(os.getenv("WB_MAX_ENTRIES_PER_SYMBOL", "2"))
    _cooldown_min = int(os.getenv("WB_SYMBOL_COOLDOWN_MIN", "10"))
    _max_loss_r = float(os.getenv("WB_MAX_LOSS_R", "2.0"))
    _max_loss_r_tiered = os.getenv("WB_MAX_LOSS_R_TIERED", "0") == "1"
    _max_loss_r_ultra_low = float(os.getenv("WB_MAX_LOSS_R_ULTRA_LOW_FLOAT", "0"))
    _max_loss_r_low = float(os.getenv("WB_MAX_LOSS_R_LOW_FLOAT", "0.85"))
    _max_loss_r_thresh_low = float(os.getenv("WB_MAX_LOSS_R_FLOAT_THRESHOLD_LOW", "1.0"))
    _max_loss_r_thresh_high = float(os.getenv("WB_MAX_LOSS_R_FLOAT_THRESHOLD_HIGH", "5.0"))
    _tw_grace_min = int(os.getenv("WB_TOPPING_WICKY_GRACE_MIN", "3"))
    _tw_min_profit_r = float(os.getenv("WB_TW_MIN_PROFIT_R", "1.0"))
    _be_min_profit_r = float(os.getenv("WB_BE_MIN_PROFIT_R", "0.5"))
    _reentry_cooldown_bars = int(os.getenv("WB_REENTRY_COOLDOWN_BARS", "5"))

    # 3-tranche exit scaling
    _3tranche_enabled = os.getenv("WB_3TRANCHE_ENABLED", "0") == "1"
    _scale_t1 = float(os.getenv("WB_SCALE_T1", "0.40"))
    _scale_t2 = float(os.getenv("WB_SCALE_T2", "0.35"))
    _t1_tp_r = float(os.getenv("WB_T1_TP_R", "1.0"))
    _t2_tp_r = float(os.getenv("WB_T2_TP_R", "2.0"))
    _t2_stop_lock_r = float(os.getenv("WB_T2_STOP_LOCK_R", "0.5"))

    # Continuation hold — suppress TW/BE exits on high-conviction setups
    _continuation_hold_enabled = os.getenv("WB_CONTINUATION_HOLD_ENABLED", "0") == "1"
    _cont_hold_min_vol_dom = float(os.getenv("WB_CONT_HOLD_MIN_VOL_DOM", "2.0"))
    _cont_hold_min_score = float(os.getenv("WB_CONT_HOLD_MIN_SCORE", "8.0"))
    _cont_hold_max_loss_r = float(os.getenv("WB_CONT_HOLD_MAX_LOSS_R", "0.5"))
    _cont_hold_cutoff_hour = int(os.getenv("WB_CONT_HOLD_CUTOFF_HOUR", "10"))
    _cont_hold_cutoff_min = int(os.getenv("WB_CONT_HOLD_CUTOFF_MIN", "30"))
    _cont_hold_max_holds = int(os.getenv("WB_CONT_HOLD_MAX_HOLDS", "2"))
    _cont_hold_use_1m_exits = os.getenv("WB_CONT_HOLD_USE_1M_EXITS", "0") == "1"
    _cont_hold_5m_guard = os.getenv("WB_CONT_HOLD_5M_TREND_GUARD", "0") == "1"
    _cont_hold_5m_vol_mult = float(os.getenv("WB_CONT_HOLD_5M_VOL_EXIT_MULT", "2.0"))
    _cont_hold_5m_min_bars = int(os.getenv("WB_CONT_HOLD_5M_MIN_BARS", "2"))
    _cont_hold_direction_check = os.getenv("WB_CONT_HOLD_DIRECTION_CHECK", "0") == "1"
    _max_loss_triggers_cooldown = os.getenv("WB_MAX_LOSS_TRIGGERS_COOLDOWN", "0") == "1"
    _min_entry_score = float(os.getenv("WB_MIN_ENTRY_SCORE", "0"))

    # Ross Pillar Gates (entry-time checks)
    _pillar_min_gap = float(os.getenv("WB_PILLAR_MIN_GAP_PCT", "10"))   # Pillar 1: up 10%+
    _pillar_min_rvol = float(os.getenv("WB_PILLAR_MIN_RVOL", "2.0"))    # Pillar 2: RVOL >= 2x
    _pillar_min_price = float(os.getenv("WB_PILLAR_MIN_PRICE", "2.0"))  # Pillar 4: price floor
    _pillar_max_price = float(os.getenv("WB_PILLAR_MAX_PRICE", "20.0")) # Pillar 4: price ceiling
    _scanner_gap_pct = float(os.getenv("WB_SCANNER_GAP_PCT", "0"))
    _scanner_rvol = float(os.getenv("WB_SCANNER_RVOL", "0"))

    if risk_dollars is not None:
        _risk = risk_dollars

    # Fetch all bars for the day
    print(f"\nFetching {symbol} bars for {date_str}...", flush=True)
    all_bars = fetch_bars(symbol, seed_start_utc, sim_end_utc)

    if not all_bars:
        print(f"  No bars returned for {symbol} on {date_str}. Skipping.", flush=True)
        return []

    # Split into seed and sim bars
    seed_bars = []
    sim_bars = []
    for b in all_bars:
        ts = getattr(b, "timestamp", None) or getattr(b, "t", None)
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)

        if ts < sim_start_utc:
            seed_bars.append((b, ts))
        else:
            sim_bars.append((b, ts))

    print(f"  Total bars: {len(all_bars)}  |  Seed: {len(seed_bars)}  |  Sim: {len(sim_bars)}", flush=True)

    if not sim_bars:
        print(f"  No sim bars in window {start_et_str}-{end_et_str}. Skipping.", flush=True)
        return []

    # Fetch fundamentals for quality gate
    _sim_stock_info = None
    _quality_min_float = float(os.getenv("WB_QUALITY_MIN_FLOAT", "0.5"))
    if not no_fundamentals and os.getenv("WB_SIM_FETCH_FUNDAMENTALS", "1") == "1":
        try:
            from stock_filter import StockFilter
            _sf = StockFilter(API_KEY, API_SECRET)
            _sim_stock_info = _sf.get_stock_info(symbol)
            if _sim_stock_info:
                fl = f"{_sim_stock_info.float_shares:.1f}M" if _sim_stock_info.float_shares else "N/A"
                print(f"  Fundamentals: float={fl} gap={_sim_stock_info.gap_pct:+.1f}%", flush=True)
        except Exception as e:
            print(f"  Fundamentals: skipped ({e})", flush=True)

    # Create components
    det = MicroPullbackDetector()
    det.symbol = symbol

    # Micro Pullback gate (Strategy 1 — OFF by default, 0% win rate Jan 2025)
    mp_enabled = os.getenv("WB_MP_ENABLED", "0") == "1"

    # MP V2 SQ-priority gate (default ON — SQ always has priority over MP V2 re-entries)
    _mp_v2_sq_priority = os.getenv("WB_MP_V2_SQ_PRIORITY", "1") == "1"

    # Squeeze detector (Strategy 2)
    from squeeze_detector import SqueezeDetector
    sq_det = SqueezeDetector()
    sq_det.symbol = symbol
    sq_enabled = os.getenv("WB_SQUEEZE_ENABLED", "0") == "1"

    # VWAP Reclaim detector (Strategy 4)
    from vwap_reclaim_detector import VwapReclaimDetector
    vr_det = VwapReclaimDetector()
    vr_det.symbol = symbol
    vr_enabled = os.getenv("WB_VR_ENABLED", "0") == "1"

    # Continuation detector (Strategy 1c — post-squeeze continuation)
    from continuation_detector import ContinuationDetector
    ct_det = ContinuationDetector()
    ct_enabled = ct_det.enabled

    # Pass gap_pct for conviction floor gate
    if _sim_stock_info is not None and hasattr(_sim_stock_info, 'gap_pct'):
        det.gap_pct = _sim_stock_info.gap_pct
        if sq_enabled:
            sq_det.gap_pct = _sim_stock_info.gap_pct
        if vr_enabled:
            vr_det.gap_pct = _sim_stock_info.gap_pct

    # LevelMap resistance tracking (entry gate)
    _level_map_enabled = os.getenv("WB_LEVEL_MAP_ENABLED", "0") == "1"
    if _level_map_enabled:
        from levels import LevelMap
        _level_map = LevelMap(
            enabled=True,
            min_fail_count=int(os.getenv("WB_LEVEL_MIN_FAILS", "2")),
            zone_width_pct=float(os.getenv("WB_LEVEL_ZONE_WIDTH_PCT", "0.5")),
            break_confirm_bars=int(os.getenv("WB_LEVEL_BREAK_CONFIRM_BARS", "2")),
        )
        det.level_map = _level_map
        if verbose:
            print("  LevelMap: ENABLED", flush=True)

    # Bar builder for VWAP/HOD/PM_HIGH tracking (no callback needed — we call det directly)
    bar_builder = TradeBarBuilder(on_bar_close=lambda b: None, et_tz=ET, interval_seconds=60)

    sim_mgr = SimTradeManager(
        risk_dollars=_risk,
        scale_core=_scale_core,
        min_r=_min_r,
        max_notional=_max_notional,
        max_shares=_max_shares,
        core_tp_r=_core_tp_r,
        tp_fuzz=_tp_fuzz,
        be_offset=_be_offset,
        runner_trail_r=_runner_trail_r,
        slippage=slippage,
        exit_mode=_exit_mode,
        be_trigger_r=_be_trigger_r,
        signal_trail_pct=_signal_trail_pct,
        max_entries_per_symbol=_max_entries,
        symbol_cooldown_min=_cooldown_min,
        max_loss_r=_max_loss_r,
        stock_info=_sim_stock_info,
        quality_min_float=_quality_min_float,
        three_tranche_enabled=_3tranche_enabled,
        scale_t1=_scale_t1,
        scale_t2=_scale_t2,
        t1_tp_r=_t1_tp_r,
        t2_tp_r=_t2_tp_r,
        t2_stop_lock_r=_t2_stop_lock_r,
        reentry_cooldown_bars=_reentry_cooldown_bars,
    )

    # Wire up quality gate trade-close callback
    def _on_sim_trade_close(t):
        # Only count standalone MP trades against MP quality gate (squeeze/VR/mp_reentry have own tracking)
        if t.setup_type not in ("squeeze", "vwap_reclaim", "mp_reentry", "continuation"):
            det.record_trade_result(t.pnl())
        if sq_enabled and t.setup_type == "squeeze":
            sq_det.notify_trade_closed(symbol, t.pnl())
            # MP V2: unlock re-entry detection when squeeze trade closes
            det.notify_squeeze_closed(symbol, t.pnl())
            # CT: unlock continuation detection when squeeze trade closes
            if ct_enabled:
                _sq_hod = bar_builder.get_hod(symbol) or 0
                _sq_avg_vol = 0
                if hasattr(sq_det, 'bars_1m') and sq_det.bars_1m:
                    _sq_avg_vol = sum(b.get("v", 0) if isinstance(b, dict) else getattr(b, "volume", 0)
                                      for b in sq_det.bars_1m) / len(sq_det.bars_1m)
                ct_det.notify_squeeze_closed(
                    symbol, t.pnl(),
                    entry=t.entry, exit_price=t.core_exit_price or t.entry,
                    hod=_sq_hod, avg_squeeze_vol=_sq_avg_vol,
                )
        if vr_enabled and t.setup_type == "vwap_reclaim":
            vr_det.notify_trade_closed(symbol, t.pnl())
        # MP V2: track re-entry count when mp_reentry trade closes
        if t.setup_type == "mp_reentry":
            det.notify_reentry_closed()
        # CT: track re-entry count when continuation trade closes
        if t.setup_type == "continuation" and ct_enabled:
            ct_det.notify_continuation_closed(t.pnl())
    sim_mgr.on_trade_close = _on_sim_trade_close

    # Ross exit manager — only active when WB_ROSS_EXIT_ENABLED=1
    _ross_exit_enabled = sim_mgr.ross_exit_enabled
    _ross_exit_mgr = RossExitManager() if _ross_exit_enabled else None
    if _ross_exit_enabled and verbose:
        print("  ROSS_EXIT: ENABLED (WB_ROSS_EXIT_ENABLED=1) — 1m signal-based exits active", flush=True)

    # ── Behavior metrics (for --export-json study) ──
    _bm = BehaviorMetrics(start_et_str) if export_json else None

    # ── Seed phase ──
    for b, ts in seed_bars:
        o = float(b.open)
        h = float(b.high)
        l = float(b.low)
        c = float(b.close)
        v = float(b.volume)
        det.seed_bar_close(o, h, l, c, v)
        if sq_enabled:
            sq_det.seed_bar_close(o, h, l, c, v)
        if vr_enabled:
            vr_det.seed_bar_close(o, h, l, c, v)
        if ct_enabled:
            ct_det.seed_bar_close(o, h, l, c, v)
        bar_builder.seed_bar_close(symbol, o, h, l, c, v, ts)

    ema_after_seed = det.ema
    print(f"  Seed complete: EMA9={ema_after_seed:.4f}" if ema_after_seed else "  Seed complete: EMA9=None", flush=True)

    # Seed LevelMap with PM high and current price
    if _level_map_enabled and det.level_map:
        pm_high = bar_builder.get_premarket_high(symbol)
        first_price = float(seed_bars[-1][0].close) if seed_bars else 5.0
        det.level_map.seed_levels(pm_high=pm_high, current_price=first_price)
        if verbose:
            print(f"  LevelMap seeded: PM_HIGH={pm_high}, ref_price={first_price:.2f}", flush=True)

    # ── Sim phase ──
    armed_count = 0
    setups_seen = 0

    if use_ticks:
        # ── TICK MODE: replay actual trades through bar builders (matches live bot) ──

        # Create two bar builders like the live bot: 10s for exits, 1m for setups
        # Shared state for bar close callbacks
        tick_sim_state = {
            "armed_count": 0,
            "last_1m_msg": None,
            "last_1m_time": None,
            "prev_10s_bar": None,  # for bearish engulfing detection
            "recent_10s_highs": [],  # for BE parabolic grace
            "prev_1m_bar": None,  # for 1m BE detection in continuation hold
        }
        _exit_on_bear_engulf = os.getenv("WB_EXIT_ON_BEAR_ENGULF", "1") == "1"
        _be_parabolic_grace = os.getenv("WB_BE_PARABOLIC_GRACE", "1") == "1"

        # Parabolic regime detector (replaces simple grace when enabled)
        _parabolic_regime_enabled = os.getenv("WB_PARABOLIC_REGIME_ENABLED", "0") == "1"
        _parabolic_det = None
        if _parabolic_regime_enabled:
            from parabolic import ParabolicRegimeDetector
            _parabolic_det = ParabolicRegimeDetector(
                enabled=True,
                min_new_highs=int(os.getenv("WB_PARABOLIC_MIN_NEW_HIGHS", "3")),
                chandelier_mult=float(os.getenv("WB_PARABOLIC_CHANDELIER_MULT", "2.5")),
                min_hold_bars_normal=int(os.getenv("WB_PARABOLIC_MIN_HOLD_BARS_NORMAL", "3")),
                min_hold_bars_parabolic=int(os.getenv("WB_PARABOLIC_MIN_HOLD_BARS", "12")),
            )
            if verbose:
                print("  Parabolic regime detector: ENABLED", flush=True)
        _be_grace_min_r = float(os.getenv("WB_BE_GRACE_MIN_R", "1.0"))
        _be_grace_min_new_highs = int(os.getenv("WB_BE_GRACE_MIN_NEW_HIGHS", "3"))
        _be_grace_lookback = int(os.getenv("WB_BE_GRACE_LOOKBACK_BARS", "6"))
        _be_grace_min = int(os.getenv("WB_BE_GRACE_MIN", "0"))

        def _in_tw_grace(time_str: str) -> bool:
            """True if the open trade is within the topping wicky grace period."""
            t = sim_mgr.open_trade
            if t is None or t.closed or _tw_grace_min <= 0:
                return False
            entry_min = int(t.entry_time.split(":")[0]) * 60 + int(t.entry_time.split(":")[1])
            now_min = int(time_str.split(":")[0]) * 60 + int(time_str.split(":")[1])
            return (now_min - entry_min) < _tw_grace_min

        def _in_be_grace(time_str: str) -> bool:
            """True if the open trade is within the BE time-based grace period."""
            t = sim_mgr.open_trade
            if t is None or t.closed or _be_grace_min <= 0:
                return False
            entry_min = int(t.entry_time.split(":")[0]) * 60 + int(t.entry_time.split(":")[1])
            now_min = int(time_str.split(":")[0]) * 60 + int(time_str.split(":")[1])
            return (now_min - entry_min) < _be_grace_min

        def _in_parabolic_grace_sim(bar_close: float) -> bool:
            """Suppress BE exits during genuine parabolic ramps (not flash spikes)."""
            if not _be_parabolic_grace:
                return False
            t = sim_mgr.open_trade
            if t is None or t.closed:
                return False
            if bar_close < t.entry + (_be_grace_min_r * t.r):
                return False
            highs = tick_sim_state["recent_10s_highs"]
            if len(highs) < 2:
                return False
            window = highs[-_be_grace_lookback:]
            new_high_count = 0
            running = window[0]
            for bh in window[1:]:
                if bh > running:
                    new_high_count += 1
                    running = bh
            return new_high_count >= _be_grace_min_new_highs

        def _check_continuation_hold(bar, time_str: str) -> tuple[bool, str]:
            """Check if continuation hold conditions are met (stateless check)."""
            t = sim_mgr.open_trade
            if t is None or t.closed:
                return False, ""

            # Legacy counter mode (when 1m/5m exits not enabled)
            if not _cont_hold_use_1m_exits and not _cont_hold_5m_guard:
                hold_count = getattr(t, '_cont_hold_count', 0)
                if hold_count >= _cont_hold_max_holds:
                    return False, ""

            # Check 1: Volume dominance at current moment (live from detector bars)
            if len(det.bars_1m) >= 5:
                recent_5_vol = sum(b["v"] for b in list(det.bars_1m)[-5:])
                avg_5_vol = (sum(b["v"] for b in det.bars_1m) / len(det.bars_1m)) * 5
                vol_dom = recent_5_vol / avg_5_vol if avg_5_vol > 0 else 0.0
            else:
                vol_dom = 0.0

            if vol_dom < _cont_hold_min_vol_dom:
                return False, ""

            # Check 2: Original setup score
            if t.score < _cont_hold_min_score:
                return False, ""

            # Check 3: Unrealized P&L not too deep
            unrealized_r = (bar.close - t.entry) / t.r if t.r > 0 else 0
            if unrealized_r < -_cont_hold_max_loss_r:
                return False, ""

            # Check 3b: Direction check — don't suppress exits when underwater + sellers dominate
            if _cont_hold_direction_check and len(det.bars_1m) >= 5:
                if unrealized_r < 0:
                    last_5 = list(det.bars_1m)[-5:]
                    red_count = sum(1 for b in last_5 if b["c"] < b["o"])
                    if red_count >= 3:
                        return False, f"direction_check(underwater={unrealized_r:.1f}R,red={red_count}/5)"

            # Check 4: Time of day cutoff
            try:
                hh, mm = int(time_str.split(":")[0]), int(time_str.split(":")[1])
                cutoff_total = _cont_hold_cutoff_hour * 60 + _cont_hold_cutoff_min
                now_total = hh * 60 + mm
                if now_total > cutoff_total:
                    return False, ""
            except Exception:
                return False, ""

            # All checks passed
            if not _cont_hold_use_1m_exits and not _cont_hold_5m_guard:
                # Legacy counter mode — increment hold count
                hold_count = getattr(t, '_cont_hold_count', 0)
                t._cont_hold_count = hold_count + 1
                return True, f"continuation_hold(vol_dom={vol_dom:.1f}x,score={t.score:.1f},unreal_r={unrealized_r:.1f},hold#{hold_count+1})"
            else:
                return True, f"continuation_hold(vol_dom={vol_dom:.1f}x,score={t.score:.1f},unreal_r={unrealized_r:.1f})"

        def on_10s_close(bar):
            """10s bar close: exit pattern detection (like live bot's on_bar_close_10s)."""
            ts_et = bar.start_utc.astimezone(ET)
            time_str = ts_et.strftime("%H:%M")

            prev = tick_sim_state["prev_10s_bar"]
            tick_sim_state["prev_10s_bar"] = {"o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close}

            # Track 10s bar highs for legacy parabolic grace
            tick_sim_state["recent_10s_highs"].append(bar.high)
            if len(tick_sim_state["recent_10s_highs"]) > _be_grace_lookback + 5:
                tick_sim_state["recent_10s_highs"] = tick_sim_state["recent_10s_highs"][-(_be_grace_lookback + 5):]

            if sim_mgr.open_trade is None or sim_mgr.open_trade.closed:
                return

            # R-multiple trailing stop: update on 10s bar close (not per-tick, to avoid spike noise).
            # Only fires after signal mode's own tp_hit (be_trigger_r) — avoids premature exits
            # on cascading stocks that pull back before making their run.
            # Also skips if R < WB_TRAILING_STOP_MIN_R_PCT% of entry (e.g., halt-spike trades with
            # tiny absolute R on high-priced stocks — trailing stop disrupts their cascade).
            if os.getenv("WB_TRAILING_STOP_ENABLED", "0") == "1":
                t = sim_mgr.open_trade
                _min_r_pct = float(os.getenv("WB_TRAILING_STOP_MIN_R_PCT", "1.0"))
                _r_pct = (t.r / t.entry * 100.0) if t.entry > 0 else 0.0
                if t.tp_hit and t.r > 0 and _r_pct >= _min_r_pct:
                    bar_r = (bar.close - t.entry) / t.r
                    t.highest_r = max(t.highest_r, bar_r)
                    _be_thr = float(os.getenv("WB_TRAILING_STOP_BE_THRESHOLD_R", "2"))
                    _lk_thr = float(os.getenv("WB_TRAILING_STOP_LOCK_THRESHOLD_R", "4"))
                    _tr_thr = float(os.getenv("WB_TRAILING_STOP_TRAIL_THRESHOLD_R", "6"))
                    _tr_off = float(os.getenv("WB_TRAILING_STOP_TRAIL_OFFSET", "0.15"))
                    new_stop = t.stop
                    if t.highest_r >= _be_thr:
                        new_stop = max(new_stop, t.entry)           # breakeven
                    if t.highest_r >= _lk_thr:
                        new_stop = max(new_stop, t.entry + t.r)     # lock +1R
                    if t.highest_r >= _tr_thr:
                        new_stop = max(new_stop, t.peak - _tr_off)  # trail below peak
                    t.stop = new_stop

            # Feed parabolic regime detector
            if _parabolic_det is not None:
                t = sim_mgr.open_trade
                _parabolic_det.on_10s_bar(
                    bar.open, bar.high, bar.low, bar.close, bar.volume,
                    t.entry, t.r,
                )

            def _should_suppress_pattern_exit() -> tuple[bool, str]:
                # Continuation hold runs BEFORE signal mode check — it applies to
                # all exit modes because its purpose is suppressing premature TW/BE
                # exits on high-conviction setups regardless of mode
                if _continuation_hold_enabled:
                    suppress, reason = _check_continuation_hold(bar, time_str)
                    if suppress:
                        return True, reason

                if _exit_mode == "signal":
                    # Signal mode: no other exit suppression (VERO's edge comes from exit + re-enter)
                    return False, ""
                if _parabolic_det is not None:
                    if _parabolic_det.should_suppress_exit():
                        return True, "parabolic_regime"
                elif _in_parabolic_grace_sim(bar.close):
                    return True, "parabolic_grace"

                return False, ""

            # Skip ALL pattern exit detection on 10s bars for squeeze/VR trades
            # (squeeze/VR have their own exit logic — TW/BE are too sensitive)
            # Also skip for MP trades when Ross exit is ON (1m signals take over)
            if sim_mgr.open_trade is not None and not sim_mgr.open_trade.closed:
                if sim_mgr.open_trade.setup_type in ("squeeze", "vwap_reclaim", "mp_reentry", "continuation"):
                    return
                if _ross_exit_enabled:
                    return  # Ross handles all trade types via 1m signals

            # If in 5m guard or 1m exit mode, skip ALL pattern exit detection on 10s bars
            # Hard stops (stop_hit, max_loss_hit) are handled separately and always fire
            if _continuation_hold_enabled:
                t = sim_mgr.open_trade
                if t is not None and not t.closed:
                    if _cont_hold_5m_guard and getattr(t, '_cont_hold_5m_mode', False):
                        return  # exit detection handled in on_5m_close
                    if _cont_hold_use_1m_exits and getattr(t, '_cont_hold_1m_mode', False):
                        return  # exit detection handled in on_1m_close

            # Topping wicky exit on 10s bars (with grace period after entry)
            if ("TOPPING_WICKY" in (det.last_patterns or [])
                and not _in_tw_grace(time_str)):
                # Profit gate: suppress TW on confirmed runners (profit >= min R)
                _tw_profit_ok = True
                if _tw_min_profit_r > 0 and sim_mgr.open_trade and not sim_mgr.open_trade.closed:
                    _tw_unreal = bar.close - sim_mgr.open_trade.entry
                    _tw_r_thresh = _tw_min_profit_r * sim_mgr.open_trade.r
                    if sim_mgr.open_trade.r > 0 and _tw_unreal >= _tw_r_thresh:
                        _tw_profit_ok = False
                        if verbose:
                            print(f"  [{time_str}] TW_SUPPRESSED (profit_gate: ${_tw_unreal:.2f} >= {_tw_min_profit_r}R=${_tw_r_thresh:.2f}) @ {bar.close:.4f}", flush=True)
                if _tw_profit_ok:
                    suppress, suppress_reason = _should_suppress_pattern_exit()
                    if suppress:
                        if verbose:
                            print(f"  [{time_str}] TW_SUPPRESSED ({suppress_reason}) @ {bar.close:.4f}", flush=True)
                    else:
                        sim_mgr.on_exit_signal("topping_wicky", bar.close, time_str)
                        if verbose:
                            print(f"  [{time_str}] TOPPING_WICKY_EXIT @ {bar.close:.4f}", flush=True)
                        return

            # Bearish engulfing exit on 10s bars (with time + parabolic grace)
            if _exit_on_bear_engulf and prev is not None:
                if is_bearish_engulfing(bar.open, bar.high, bar.low, bar.close,
                                        prev["o"], prev["h"], prev["l"], prev["c"]):
                    if _in_be_grace(time_str):
                        if verbose:
                            print(f"  [{time_str}] BE_SUPPRESSED (time grace) @ {bar.close:.4f}", flush=True)
                    else:
                        # Profit gate: suppress BE only in small positive profit (< min R)
                        # Skip in signal mode — BE exits are part of the cascading strategy
                        _be_profit_ok = True
                        if _exit_mode != "signal" and _be_min_profit_r > 0 and sim_mgr.open_trade and not sim_mgr.open_trade.closed:
                            _be_unreal = bar.close - sim_mgr.open_trade.entry
                            if 0 < _be_unreal < _be_min_profit_r * sim_mgr.open_trade.r:
                                _be_profit_ok = False
                                if verbose:
                                    print(f"  [{time_str}] BE_SUPPRESSED (profit_gate: ${_be_unreal:.2f} < {_be_min_profit_r}R=${_be_min_profit_r * sim_mgr.open_trade.r:.2f}) @ {bar.close:.4f}", flush=True)
                        if _be_profit_ok:
                            suppress, suppress_reason = _should_suppress_pattern_exit()
                            if suppress:
                                if verbose:
                                    print(f"  [{time_str}] BE_SUPPRESSED ({suppress_reason}) @ {bar.close:.4f}", flush=True)
                            else:
                                sim_mgr.on_exit_signal("bearish_engulfing", bar.close, time_str)
                                if verbose:
                                    print(f"  [{time_str}] BEARISH_ENGULFING_EXIT @ {bar.close:.4f}", flush=True)

            # Parabolic exhaustion trim signal
            if _parabolic_det is not None and _parabolic_det.should_trim():
                if sim_mgr.open_trade and not sim_mgr.open_trade.closed:
                    sim_mgr.on_exit_signal("parabolic_exhaustion", bar.close, time_str)
                    if verbose:
                        print(f"  [{time_str}] PARABOLIC_EXHAUSTION_TRIM @ {bar.close:.4f}", flush=True)

        def on_1m_close(bar):
            """1m bar close: PRIMARY setup detection (like live bot's on_bar_close_1m)."""
            ts_et = bar.start_utc.astimezone(ET)
            time_str = ts_et.strftime("%H:%M")

            # Update premarket levels
            pm_high = bb_1m.get_premarket_high(symbol)
            pm_bf_high = bb_1m.get_premarket_bull_flag_high(symbol)
            det.update_premarket_levels(pm_high, pm_bf_high)

            vwap = bb_1m.get_vwap(symbol)

            msg = det.on_bar_close_1m(bar, vwap=vwap)

            # --- Squeeze detection (only if not already in a trade) ---
            sq_msg = None
            if sq_enabled and sim_mgr.open_trade is None:
                sq_det.update_premarket_levels(pm_high, pm_bf_high)
                sq_msg = sq_det.on_bar_close_1m(bar, vwap=vwap)
                if sq_msg and verbose:
                    print(f"  [{time_str}] {sq_msg}", flush=True)
                if sq_msg and "ARMED" in sq_msg:
                    tick_sim_state["armed_count"] += 1

            # --- Continuation detection (only if not in a trade AND SQ is fully idle) ---
            ct_msg = None
            _ct_sq_idle = (not sq_enabled) or (sq_det._state == "IDLE" and not sq_det._in_trade)
            if ct_enabled and sim_mgr.open_trade is None and _ct_sq_idle:
                ct_msg = ct_det.on_bar_close_1m(bar, vwap=vwap)
                if ct_msg and verbose:
                    print(f"  [{time_str}] {ct_msg}", flush=True)
                if ct_msg and "CT_ARMED" in ct_msg:
                    tick_sim_state["armed_count"] += 1

            # --- Squeeze / MP V2 / CT re-entry 1m bar exits ---
            # Skip when Ross exit is ON — Ross 1m signals handle exits instead
            if not _ross_exit_enabled and sim_mgr.open_trade is not None and not sim_mgr.open_trade.closed:
                if sim_mgr.open_trade.setup_type in ("squeeze", "mp_reentry", "continuation"):
                    sim_mgr.on_1m_bar_close_squeeze(
                        sim_mgr.open_trade,
                        bar.open, bar.high, bar.low, bar.close, bar.volume,
                        vwap, time_str,
                    )
                    if sim_mgr.open_trade is None or sim_mgr.open_trade.closed:
                        closed_t = sim_mgr.closed_trades[-1] if sim_mgr.closed_trades else None
                        if closed_t:
                            if closed_t.setup_type == "squeeze":
                                sq_det.notify_trade_closed(symbol, closed_t.pnl())
                                # MP V2: unlock re-entry detection
                                det.notify_squeeze_closed(symbol, closed_t.pnl())
                                # CT: unlock continuation detection
                                if ct_enabled:
                                    _sq_hod = bb_1m.get_hod(symbol) or 0
                                    _sq_avg_vol = 0
                                    if hasattr(sq_det, 'bars_1m') and sq_det.bars_1m:
                                        _sq_avg_vol = sum(b.get("v", 0) if isinstance(b, dict) else getattr(b, "volume", 0)
                                                          for b in sq_det.bars_1m) / len(sq_det.bars_1m)
                                    ct_det.notify_squeeze_closed(
                                        symbol, closed_t.pnl(),
                                        entry=closed_t.entry, exit_price=closed_t.core_exit_price or closed_t.entry,
                                        hod=_sq_hod, avg_squeeze_vol=_sq_avg_vol,
                                    )
                            elif closed_t.setup_type == "mp_reentry":
                                det.notify_reentry_closed()
                            elif closed_t.setup_type == "continuation" and ct_enabled:
                                ct_det.notify_continuation_closed(closed_t.pnl())
                            if verbose:
                                _exit_label = {
                                    "squeeze": "SQ_EXIT",
                                    "mp_reentry": "MP_V2_EXIT",
                                    "continuation": "CT_EXIT",
                                }.get(closed_t.setup_type, "EXIT")
                                print(
                                    f"  [{time_str}] {_exit_label}: {closed_t.core_exit_reason} "
                                    f"P&L=${closed_t.pnl():+,.0f}",
                                    flush=True,
                                )

            # --- VWAP Reclaim detection (only if not already in a trade) ---
            vr_msg = None
            if vr_enabled and sim_mgr.open_trade is None:
                vr_msg = vr_det.on_bar_close_1m(bar, vwap=vwap)
                if vr_msg and verbose:
                    print(f"  [{time_str}] {vr_msg}", flush=True)
                if vr_msg and "VR_ARMED" in vr_msg:
                    tick_sim_state["armed_count"] += 1

            # --- VWAP Reclaim 1m bar exits ---
            # Skip when Ross exit is ON — Ross 1m signals handle exits instead
            if vr_enabled and not _ross_exit_enabled and sim_mgr.open_trade is not None and not sim_mgr.open_trade.closed:
                if sim_mgr.open_trade.setup_type == "vwap_reclaim":
                    sim_mgr.on_1m_bar_close_vr(
                        sim_mgr.open_trade,
                        bar.open, bar.high, bar.low, bar.close, bar.volume,
                        vwap, time_str,
                    )
                    if sim_mgr.open_trade is None or sim_mgr.open_trade.closed:
                        closed_t = sim_mgr.closed_trades[-1] if sim_mgr.closed_trades else None
                        if closed_t:
                            vr_det.notify_trade_closed(symbol, closed_t.pnl())
                            if verbose:
                                print(
                                    f"  [{time_str}] VR_EXIT: {closed_t.core_exit_reason} "
                                    f"P&L=${closed_t.pnl():+,.0f}",
                                    flush=True,
                                )

            # Feed behavior metrics
            if _bm is not None:
                _bm.on_1m_bar(bar.open, bar.high, bar.low, bar.close, bar.volume, time_str, vwap)

            # --- Continuation Hold: 1m bar exit detection ---
            # Skip when in 5m guard mode (5m guard supersedes 1m exits)
            if _cont_hold_use_1m_exits and _continuation_hold_enabled and not (
                _cont_hold_5m_guard and sim_mgr.open_trade and not sim_mgr.open_trade.closed
                and getattr(sim_mgr.open_trade, '_cont_hold_5m_mode', False)):
                t = sim_mgr.open_trade
                if t is not None and not t.closed:
                    still_valid, hold_reason = _check_continuation_hold(bar, time_str)

                    if still_valid:
                        # Mark/keep trade in 1m exit mode
                        t._cont_hold_1m_mode = True

                        # Check Topping Wicky on THIS 1m bar directly
                        if len(det.bars_1m) >= 12:
                            recent_12 = list(det.bars_1m)[-12:]
                            top = max(b["h"] for b in recent_12)
                            last_1m = recent_12[-1]
                            rng = max(1e-9, last_1m["h"] - last_1m["l"])
                            upper_wick = last_1m["h"] - max(last_1m["o"], last_1m["c"])
                            body = abs(last_1m["c"] - last_1m["o"])
                            near_top = abs(last_1m["h"] - top) <= max(0.01, top * 0.002)
                            if near_top and (upper_wick / rng) >= 0.45 and (body / rng) <= 0.35:
                                if verbose:
                                    print(f"  [{time_str}] TOPPING_WICKY_EXIT (1m bar, cont_hold) @ {bar.close:.4f}", flush=True)
                                sim_mgr.on_exit_signal("topping_wicky", bar.close, time_str)

                        # Check BE on 1m bar using previous 1m bar
                        prev_1m = tick_sim_state.get("prev_1m_bar")
                        if (prev_1m is not None and _exit_on_bear_engulf
                            and sim_mgr.open_trade is not None and not sim_mgr.open_trade.closed):
                            if is_bearish_engulfing(bar.open, bar.high, bar.low, bar.close,
                                                     prev_1m["o"], prev_1m["h"], prev_1m["l"], prev_1m["c"]):
                                if verbose:
                                    print(f"  [{time_str}] BEARISH_ENGULFING_EXIT (1m bar, cont_hold) @ {bar.close:.4f}", flush=True)
                                sim_mgr.on_exit_signal("bearish_engulfing", bar.close, time_str)

                        if verbose and sim_mgr.open_trade and not sim_mgr.open_trade.closed:
                            print(f"  [{time_str}] CONT_HOLD_1M_CHECK: no exit signal ({hold_reason})", flush=True)
                    else:
                        # Conditions no longer met — exit 1m mode
                        t._cont_hold_1m_mode = False
                        if verbose:
                            print(f"  [{time_str}] CONT_HOLD_1M_MODE_OFF: conditions no longer met", flush=True)

            # Topping wicky exit after 1m bar close (with grace period after entry)
            # Skip when in 1m exit mode (handled by cont hold block above)
            # Skip for squeeze trades (squeeze has its own exit logic)
            # Skip when Ross exit mode is ON (Ross 1m signals handle all trade types)
            if (sim_mgr.open_trade is not None
                and not sim_mgr.open_trade.closed
                and sim_mgr.open_trade.setup_type not in ("squeeze", "mp_reentry", "continuation")
                and not _ross_exit_enabled
                and not getattr(sim_mgr.open_trade, '_cont_hold_1m_mode', False)
                and not getattr(sim_mgr.open_trade, '_cont_hold_5m_mode', False)
                and "TOPPING_WICKY" in (det.last_patterns or [])
                and not _in_tw_grace(time_str)):
                # Profit gate: suppress TW on confirmed runners (profit >= min R)
                _tw_profit_ok = True
                if _tw_min_profit_r > 0 and sim_mgr.open_trade.r > 0:
                    _tw_unreal = bar.close - sim_mgr.open_trade.entry
                    _tw_r_thresh = _tw_min_profit_r * sim_mgr.open_trade.r
                    if _tw_unreal >= _tw_r_thresh:
                        _tw_profit_ok = False
                        if verbose:
                            print(f"  [{time_str}] TW_SUPPRESSED (profit_gate: ${_tw_unreal:.2f} >= {_tw_min_profit_r}R=${_tw_r_thresh:.2f}) @ {bar.close:.4f}", flush=True)
                if _tw_profit_ok:
                    sim_mgr.on_exit_signal("topping_wicky", bar.close, time_str)
                    if verbose:
                        print(f"  [{time_str}] TOPPING_WICKY_EXIT @ {bar.close:.4f}", flush=True)

            # --- Ross exit: 1m signal-based exits for ALL trade types ---
            # Runs when WB_ROSS_EXIT_ENABLED=1 and any trade is open (MP, SQ, VR).
            # Replaces: TW/BE on 10s bars, fixed trails, stall timer, R targets, sq_target_hit.
            # Keeps: bail timer, max_loss_hit, hard stop, dollar loss cap (all in on_tick).
            if (_ross_exit_enabled
                    and _ross_exit_mgr is not None
                    and sim_mgr.open_trade is not None
                    and not sim_mgr.open_trade.closed):
                _rt = sim_mgr.open_trade
                _unrealized_r = (bar.close - _rt.entry) / _rt.r if _rt.r > 0 else 0.0
                _r_action, _r_signal, _r_new_stop = _ross_exit_mgr.on_1m_bar_close(
                    o=bar.open, h=bar.high, l=bar.low, c=bar.close,
                    vwap=vwap,
                    in_trade=True,
                    entry_price=_rt.entry,
                    unrealized_r=_unrealized_r,
                )
                # Note: structural stop (_r_new_stop) is NOT applied to t.stop.
                # The CUC signal already handles the case when a 1m bar closes below
                # the prior bar's low — which IS the structural trail.  Applying it as
                # a tick-by-tick mechanical stop would cause premature exits on intra-bar
                # noise that Ross explicitly ignores (he exits on bar CLOSE, not on tick).
                # Act on exit signal (if any)
                if _r_action is not None and (sim_mgr.open_trade is None or not sim_mgr.open_trade.closed):
                    if _r_action == "partial_50":
                        _ross_exit_mgr.partial_taken = True
                    sim_mgr.on_ross_exit_signal(
                        action=_r_action,
                        signal_name=_r_signal,
                        price=bar.close,
                        time_str=time_str,
                        verbose=verbose,
                    )
            elif _ross_exit_enabled and _ross_exit_mgr is not None:
                # Not in a trade — still feed bars so EMAs warm up
                _ross_exit_mgr.on_1m_bar_close(
                    o=bar.open, h=bar.high, l=bar.low, c=bar.close,
                    vwap=vwap, in_trade=False,
                )

            # Decrement stop-hit re-entry cooldown
            sim_mgr.on_bar_close_1m_cooldown()

            if verbose and msg:
                print(f"  [{time_str}] {msg}", flush=True)

            if msg and "ARMED" in msg:
                tick_sim_state["armed_count"] += 1

            tick_sim_state["last_1m_msg"] = msg
            tick_sim_state["last_1m_time"] = time_str
            tick_sim_state["prev_1m_bar"] = {"o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close}

        _completed_5m_bars = {}  # {symbol: [bar_dict, ...]} — tracks all completed 5m bars for seeding

        def on_5m_close(bar):
            """5m bar close: track completed bars + active-phase exit detection."""
            ts_et = bar.start_utc.astimezone(ET)
            time_str = ts_et.strftime("%H:%M")

            # Always track completed bars for seeding (regardless of guard mode)
            sym = bar.symbol
            if sym not in _completed_5m_bars:
                _completed_5m_bars[sym] = []
            _completed_5m_bars[sym].append({
                "o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close,
                "v": bar.volume, "time": time_str,
            })

            if not _cont_hold_5m_guard or not _continuation_hold_enabled:
                return

            t = sim_mgr.open_trade
            if t is None or t.closed:
                return
            if not getattr(t, '_cont_hold_5m_mode', False):
                return

            # ─── ACTIVE PHASE ───
            # Track 5m bars for this trade
            bars_5m = getattr(t, '_5m_bars', [])
            bars_5m.append({
                "o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close,
                "v": bar.volume, "time": time_str,
            })
            t._5m_bars = bars_5m

            # Re-evaluate continuation hold base conditions
            still_valid, hold_reason = _check_continuation_hold(bar, time_str)

            if not still_valid:
                t._cont_hold_5m_mode = False
                if verbose:
                    print(f"  [{time_str}] 5M_GUARD_OFF: conditions no longer met", flush=True)
                return

            # Need at least 2 bars for average calculation (seeded + new)
            if len(bars_5m) < 2:
                return

            # Check: Is this a RED bar with HIGH VOLUME?
            is_red = bar.close < bar.open
            avg_vol = sum(b["v"] for b in bars_5m[:-1]) / len(bars_5m[:-1])
            vol_ratio = bar.volume / avg_vol if avg_vol > 0 else 0

            if is_red and vol_ratio >= _cont_hold_5m_vol_mult:
                if verbose:
                    print(f"  [{time_str}] 5M_TREND_GUARD_EXIT: red bar vol={bar.volume:,} ({vol_ratio:.1f}x avg={avg_vol:,.0f}) @ {bar.close:.4f}", flush=True)
                sim_mgr.on_exit_signal("5m_trend_guard_exit", bar.close, time_str)
                t._cont_hold_5m_mode = False
                return

            if verbose:
                bar_type = "RED" if is_red else "green"
                print(f"  [{time_str}] 5M_GUARD_HOLD: {bar_type} vol={bar.volume:,} ({vol_ratio:.1f}x avg) @ {bar.close:.4f}", flush=True)

        # Create bar builders with callbacks
        bb_10s = TradeBarBuilder(on_bar_close=on_10s_close, et_tz=ET, interval_seconds=10)
        bb_1m = TradeBarBuilder(on_bar_close=on_1m_close, et_tz=ET, interval_seconds=60)
        bb_5m = TradeBarBuilder(on_bar_close=on_5m_close, et_tz=ET, interval_seconds=300)

        # Seed builders with premarket bars (for VWAP/HOD/PM tracking)
        for b, ts in seed_bars:
            o = float(b.open)
            h = float(b.high)
            l = float(b.low)
            c = float(b.close)
            v = float(b.volume)
            bb_10s.seed_bar_close(symbol, o, h, l, c, v, ts)
            bb_1m.seed_bar_close(symbol, o, h, l, c, v, ts)
            bb_5m.seed_bar_close(symbol, o, h, l, c, v, ts)

        # Fetch actual trades for the sim window
        _cache_file = None
        if tick_cache:
            import gzip as _gzip
            _cache_file = os.path.join(tick_cache, date_str, f"{symbol}.json.gz")
            if os.path.exists(_cache_file):
                print(f"  Loading ticks from cache: {_cache_file}", flush=True)
                from collections import namedtuple
                _CachedTick = namedtuple("_CachedTick", ["price", "size", "timestamp"])
                with _gzip.open(_cache_file, "rt") as _cf:
                    _cached = json.load(_cf)
                tick_trades = [
                    _CachedTick(
                        t["p"], t["s"],
                        datetime.fromisoformat(t["t"])
                    )
                    for t in _cached
                ]
            else:
                print(f"  WARNING: No cache file {_cache_file} — falling back to API", flush=True)
                tick_trades = fetch_trades(symbol, sim_start_utc, sim_end_utc)

                # ── Write fetched ticks to cache so future runs don't re-fetch ──
                if tick_trades:
                    _cache_dir = os.path.join(tick_cache, date_str)
                    os.makedirs(_cache_dir, exist_ok=True)
                    _cache_payload = [
                        {"p": float(t.price), "s": int(t.size),
                         "t": t.timestamp.isoformat() if hasattr(t.timestamp, "isoformat") else str(t.timestamp)}
                        for t in tick_trades
                    ]
                    with _gzip.open(_cache_file, "wt") as _cf:
                        json.dump(_cache_payload, _cf)
                    print(f"  Cached {len(_cache_payload)} ticks → {_cache_file}", flush=True)
        elif feed == "databento":
            print(f"  Fetching tick data from Databento...", flush=True)
            from databento_feed import fetch_trades_historical
            _db_trades_raw = fetch_trades_historical(
                symbol, date_str,
                start_et=start_et_str, end_et=end_et_str,
            )
            # Convert dicts to simple objects with .price, .size, .timestamp
            from collections import namedtuple
            _DbnTick = namedtuple("_DbnTick", ["price", "size", "timestamp"])
            tick_trades = [_DbnTick(t["price"], t["size"], t["timestamp"]) for t in _db_trades_raw]

            # ── Write to tick cache if tick_cache dir was specified ──
            if tick_cache and _db_trades_raw:
                import gzip as _gzip
                _cache_dir = os.path.join(tick_cache, date_str)
                os.makedirs(_cache_dir, exist_ok=True)
                _cache_out = os.path.join(_cache_dir, f"{symbol}.json.gz")
                _cache_payload = [
                    {"p": t["price"], "s": t["size"], "t": t["timestamp"].isoformat()
                     if hasattr(t["timestamp"], "isoformat") else str(t["timestamp"])}
                    for t in _db_trades_raw
                ]
                with _gzip.open(_cache_out, "wt") as _cf:
                    json.dump(_cache_payload, _cf)
                print(f"  Cached {len(_cache_payload)} ticks → {_cache_out}", flush=True)
        else:
            print(f"  Fetching tick data from Alpaca...", flush=True)
            tick_trades = fetch_trades(symbol, sim_start_utc, sim_end_utc)

            # ── Write to tick cache if tick_cache dir was specified ──
            if tick_cache and tick_trades:
                import gzip as _gzip
                _cache_dir = os.path.join(tick_cache, date_str)
                os.makedirs(_cache_dir, exist_ok=True)
                _cache_out = os.path.join(_cache_dir, f"{symbol}.json.gz")
                _cache_payload = [
                    {"p": float(t.price), "s": int(t.size),
                     "t": t.timestamp.isoformat() if hasattr(t.timestamp, "isoformat") else str(t.timestamp)}
                    for t in tick_trades
                ]
                with _gzip.open(_cache_out, "wt") as _cf:
                    json.dump(_cache_payload, _cf)
                print(f"  Cached {len(_cache_payload)} ticks → {_cache_out}", flush=True)
        print(f"  Tick replay: {len(tick_trades)} trades for sim window", flush=True)

        if not tick_trades:
            print(f"  No tick data in window {start_et_str}-{end_et_str}. Skipping.", flush=True)
        else:
            last_price = None
            last_time_str = None
            last_ts_utc = None  # for halt-through gap detection

            for t in tick_trades:
                price = float(t.price)
                size = int(t.size)
                ts = t.timestamp
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)

                ts_et = ts.astimezone(ET)
                time_str = ts_et.strftime("%H:%M")

                # Feed to both bar builders (fires callbacks on bar close)
                bb_10s.on_trade(symbol, price, size, ts)
                bb_1m.on_trade(symbol, price, size, ts)
                bb_5m.on_trade(symbol, price, size, ts)

                # Trigger check on every tick (like live bot's on_trade)
                is_premarket = bb_1m.is_premarket(ts)

                # --- Squeeze trigger (priority over MP) ---
                _sq_armed_before = sq_det.armed if sq_enabled else None
                if sq_enabled and _sq_armed_before is not None and sim_mgr.open_trade is None:
                    sq_trigger = sq_det.on_trade_price(price, is_premarket=is_premarket)
                    if sq_trigger and "ENTRY SIGNAL" in sq_trigger:
                        trade = sim_mgr.on_signal(
                            symbol=symbol,
                            entry=_sq_armed_before.trigger_high,
                            stop=_sq_armed_before.stop_low,
                            r=_sq_armed_before.r,
                            score=_sq_armed_before.score,
                            detail=_sq_armed_before.score_detail,
                            time_str=time_str,
                            setup_type="squeeze",
                            size_mult=_sq_armed_before.size_mult,
                        )
                        if trade:
                            sq_det.notify_trade_opened()
                            if verbose:
                                print(
                                    f"  [{time_str}] SQ_ENTRY: {trade.entry:.4f} stop={trade.stop:.4f} "
                                    f"R={trade.r:.4f} qty={trade.qty_total} score={trade.score:.1f} "
                                    f"setup_type=squeeze",
                                    flush=True,
                                )
                            # Ross exit: reset per-trade state on new squeeze entry
                            if _ross_exit_mgr is not None:
                                _ross_exit_mgr.reset()

                # --- Continuation trigger (after SQ, before VR/MP) ---
                _ct_armed_before = ct_det.armed if ct_enabled else None
                if ct_enabled and _ct_armed_before is not None and sim_mgr.open_trade is None:
                    # SQ priority gate: defer CT if SQ is actively hunting
                    _ct_sq_deferred = False
                    if sq_enabled and (sq_det._state != "IDLE" or sq_det._in_trade):
                        _ct_sq_deferred = True
                        if verbose:
                            print(f"  [{time_str}] CT DEFERRED: SQ has priority (state={sq_det._state})", flush=True)
                    if not _ct_sq_deferred:
                        ct_trigger = ct_det.on_trade_price(price, is_premarket=is_premarket)
                        if ct_trigger and "ENTRY SIGNAL" in ct_trigger:
                            trade = sim_mgr.on_signal(
                                symbol=symbol,
                                entry=_ct_armed_before.trigger_high,
                                stop=_ct_armed_before.stop_low,
                                r=_ct_armed_before.r,
                                score=_ct_armed_before.score,
                                detail=_ct_armed_before.score_detail,
                                time_str=time_str,
                                setup_type="continuation",
                                size_mult=_ct_armed_before.size_mult,
                            )
                            if trade:
                                if verbose:
                                    print(
                                        f"  [{time_str}] CT_ENTRY: {trade.entry:.4f} stop={trade.stop:.4f} "
                                        f"R={trade.r:.4f} qty={trade.qty_total} score={trade.score:.1f} "
                                        f"setup_type=continuation",
                                        flush=True,
                                    )

                # --- VWAP Reclaim trigger (priority between squeeze and MP) ---
                _vr_armed_before = vr_det.armed if vr_enabled else None
                if vr_enabled and _vr_armed_before is not None and sim_mgr.open_trade is None:
                    vr_trigger = vr_det.on_trade_price(price, is_premarket=is_premarket)
                    if vr_trigger and "ENTRY SIGNAL" in vr_trigger:
                        trade = sim_mgr.on_signal(
                            symbol=symbol,
                            entry=_vr_armed_before.trigger_high,
                            stop=_vr_armed_before.stop_low,
                            r=_vr_armed_before.r,
                            score=_vr_armed_before.score,
                            detail=_vr_armed_before.score_detail,
                            time_str=time_str,
                            setup_type="vwap_reclaim",
                            size_mult=_vr_armed_before.size_mult,
                        )
                        if trade:
                            vr_det.notify_trade_opened()
                            if verbose:
                                print(
                                    f"  [{time_str}] VR_ENTRY: {trade.entry:.4f} stop={trade.stop:.4f} "
                                    f"R={trade.r:.4f} qty={trade.qty_total} score={trade.score:.1f} "
                                    f"setup_type=vwap_reclaim",
                                    flush=True,
                                )
                            # Ross exit: reset per-trade state on new VR entry
                            if _ross_exit_mgr is not None:
                                _ross_exit_mgr.reset()

                armed_before = det.armed
                trigger_msg = det.on_trade_price(price, is_premarket=is_premarket)
                if trigger_msg and "ENTRY SIGNAL" in trigger_msg and armed_before:
                    _armed_setup_type = getattr(armed_before, 'setup_type', 'micro_pullback')
                    # V6.1: Toxic entry filters
                    _toxic = check_toxic_filters(
                        entry_price=armed_before.trigger_high,
                        stop_price=armed_before.stop_low,
                        gap_pct=gap_pct,
                        pm_volume=pm_volume,
                        candidates_count=candidates_count,
                        month=date.month,
                    )
                    if _toxic['action'] == 'BLOCK':
                        if verbose:
                            print(f"  [{time_str}] TOXIC_BLOCK {symbol}: {_toxic['reason']}", flush=True)
                    elif _scanner_gap_pct > 0 and _scanner_gap_pct < _pillar_min_gap:
                        if verbose:
                            print(f"  [{time_str}] PILLAR_BLOCK: gap {_scanner_gap_pct:.1f}% < {_pillar_min_gap}%", flush=True)
                    elif _scanner_rvol > 0 and _scanner_rvol < _pillar_min_rvol:
                        if verbose:
                            print(f"  [{time_str}] PILLAR_BLOCK: RVOL {_scanner_rvol:.1f}x < {_pillar_min_rvol}x", flush=True)
                    elif armed_before.trigger_high < _pillar_min_price or armed_before.trigger_high > _pillar_max_price:
                        if verbose:
                            print(f"  [{time_str}] PILLAR_BLOCK: price ${armed_before.trigger_high:.2f} outside ${_pillar_min_price}-${_pillar_max_price}", flush=True)
                    elif _min_entry_score > 0 and armed_before.score < _min_entry_score:
                        if verbose:
                            print(f"  [{time_str}] ENTRY_BLOCKED: score {armed_before.score:.1f} < min {_min_entry_score}", flush=True)
                    elif not mp_enabled and _armed_setup_type != "mp_reentry":
                        if verbose:
                            print(f"  [{time_str}] MP_DISABLED: would-be entry @ {armed_before.trigger_high:.4f} score={armed_before.score:.1f} (WB_MP_ENABLED=0)", flush=True)
                    elif _armed_setup_type == "mp_reentry" and _mp_v2_sq_priority and sq_enabled and (sq_det._state != "IDLE" or sq_det._in_trade):
                        if verbose:
                            print(f"  [{time_str}] MP_V2_DEFERRED: SQ has priority (state={sq_det._state}, in_trade={sq_det._in_trade})", flush=True)
                    else:
                        _saved_risk = None
                        _qg_size_mult = getattr(armed_before, 'size_mult', 1.0)
                        _effective_mult = _toxic.get('multiplier', 1.0) if _toxic['action'] == 'HALF_RISK' else 1.0
                        _effective_mult *= _qg_size_mult
                        if _effective_mult < 1.0:
                            _saved_risk = sim_mgr.risk_dollars
                            sim_mgr.risk_dollars = _saved_risk * _effective_mult
                            if verbose:
                                parts = []
                                if _toxic['action'] == 'HALF_RISK':
                                    parts.append(f"toxic={_toxic['multiplier']:.0%}")
                                if _qg_size_mult < 1.0:
                                    parts.append(f"qg_price={_qg_size_mult:.0%}")
                                print(f"  [{time_str}] SIZE_REDUCE {symbol}: {'+'.join(parts)} (risk ${sim_mgr.risk_dollars:.0f})", flush=True)
                        trade = sim_mgr.on_signal(
                            symbol=symbol,
                            entry=armed_before.trigger_high,
                            stop=armed_before.stop_low,
                            r=armed_before.r,
                            score=armed_before.score,
                            detail=armed_before.score_detail,
                            time_str=time_str,
                            setup_type=_armed_setup_type,
                            size_mult=_qg_size_mult,
                        )
                        if _saved_risk is not None:
                            sim_mgr.risk_dollars = _saved_risk
                        if trade and verbose:
                            _entry_label = "MP_V2_ENTRY" if _armed_setup_type == "mp_reentry" else "ENTRY"
                            print(
                                f"  [{time_str}] {_entry_label}: {trade.entry:.4f} stop={trade.stop:.4f} "
                                f"R={trade.r:.4f} qty={trade.qty_total} score={trade.score:.1f} "
                                f"setup_type={_armed_setup_type}",
                                flush=True,
                            )
                        # Ross exit: reset per-trade state on new entry
                        if trade and _ross_exit_mgr is not None:
                            _ross_exit_mgr.reset()
                        # Initialize continuation hold 1m mode on new trade
                        if trade and _cont_hold_use_1m_exits and _continuation_hold_enabled:
                            trade._cont_hold_1m_mode = False
                            # Check if trade qualifies for 1m mode at entry
                            # Create a minimal bar-like object for the check
                            class _BarSnap:
                                def __init__(self, c): self.close = c
                            qualifies, _ = _check_continuation_hold(_BarSnap(price), time_str)
                            if qualifies:
                                trade._cont_hold_1m_mode = True
                                if verbose:
                                    print(f"  [{time_str}] CONT_HOLD_1M_MODE_ON at entry (score={trade.score:.1f})", flush=True)
                        # Initialize continuation hold 5m trend guard on new trade
                        if trade and _cont_hold_5m_guard and _continuation_hold_enabled:
                            trade._cont_hold_5m_mode = False
                            trade._5m_bars = []
                            class _BarSnap5:
                                def __init__(self, c): self.close = c
                            qualifies, _ = _check_continuation_hold(_BarSnap5(price), time_str)
                            if qualifies:
                                # SEEDED CHECK: look at already-completed 5m bars (session only)
                                completed = _completed_5m_bars.get(symbol, [])
                                session_bars = [b for b in completed if b["time"] >= "09:30"]
                                if len(session_bars) >= _cont_hold_5m_min_bars:
                                    recent = session_bars[-_cont_hold_5m_min_bars:]
                                    green_count = sum(1 for b in recent if b["c"] > b["o"])
                                    if green_count >= _cont_hold_5m_min_bars:
                                        trade._cont_hold_5m_mode = True
                                        trade._5m_bars = list(recent)  # seed with historical bars
                                        if verbose:
                                            print(f"  [{time_str}] 5M_GUARD_SEEDED: {green_count}/{_cont_hold_5m_min_bars} green session bars — IMMEDIATE activation (score={trade.score:.1f})", flush=True)
                                    elif verbose:
                                        print(f"  [{time_str}] 5M_GUARD_SKIP: only {green_count}/{_cont_hold_5m_min_bars} green session bars — staying in 10s hold", flush=True)
                                elif verbose:
                                    print(f"  [{time_str}] 5M_GUARD_SKIP: only {len(session_bars)} session bars (need {_cont_hold_5m_min_bars}) — staying in 10s hold", flush=True)

                # Halt-through: detect/manage halt state via tick timestamp gap
                sim_mgr.handle_tick_halt(ts, last_ts_utc)

                # Stop/TP/trail check on every tick
                sim_mgr.on_tick(price, time_str)

                # Parabolic Chandelier stop check — ONLY in classic mode
                # In signal mode, the existing signal trail handles exits;
                # Chandelier is wider and causes worse exits on flash spikes / cascading re-entry stocks
                if (_parabolic_det is not None
                    and _exit_mode == "classic"
                    and sim_mgr.open_trade is not None
                    and not sim_mgr.open_trade.closed):
                    chandelier = _parabolic_det.get_chandelier_stop()
                    if chandelier > 0 and price <= chandelier:
                        sim_mgr.on_exit_signal("chandelier_stop", price, time_str)
                        if verbose:
                            print(f"  [{time_str}] CHANDELIER_STOP @ {price:.4f} (stop={chandelier:.4f})", flush=True)

                # Reset parabolic detector when trade closes
                if (_parabolic_det is not None
                    and (sim_mgr.open_trade is None or sim_mgr.open_trade.closed)):
                    _parabolic_det.reset()

                last_price = price
                last_time_str = time_str
                last_ts_utc = ts

            # Force-close any open position at sim end
            if last_price is not None:
                sim_mgr.force_close(last_price, last_time_str)
                if _parabolic_det is not None:
                    _parabolic_det.reset()

        armed_count = tick_sim_state["armed_count"]

    else:
        # ── BAR MODE: original 1-min bar simulation ──

        def _in_tw_grace_bar(time_str: str) -> bool:
            """True if the open trade is within the topping wicky grace period."""
            t = sim_mgr.open_trade
            if t is None or t.closed or _tw_grace_min <= 0:
                return False
            entry_min = int(t.entry_time.split(":")[0]) * 60 + int(t.entry_time.split(":")[1])
            now_min = int(time_str.split(":")[0]) * 60 + int(time_str.split(":")[1])
            return (now_min - entry_min) < _tw_grace_min

        for b, ts in sim_bars:
            o = float(b.open)
            h = float(b.high)
            l = float(b.low)
            c = float(b.close)
            v = float(b.volume)
            ts_et = ts.astimezone(ET)
            time_str = ts_et.strftime("%H:%M")

            # 1) Update VWAP/HOD/PM_HIGH via bar_builder seed (no callback)
            bar_builder.seed_bar_close(symbol, o, h, l, c, v, ts)

            # Update premarket levels on detector
            pm_high = bar_builder.get_premarket_high(symbol)
            pm_bf_high = bar_builder.get_premarket_bull_flag_high(symbol)
            det.update_premarket_levels(pm_high, pm_bf_high)

            # 2) Construct Bar object and feed to detectors
            bar_obj = Bar(symbol=symbol, start_utc=ts, open=o, high=h, low=l, close=c, volume=int(v))
            vwap = bar_builder.get_vwap(symbol)

            msg = det.on_bar_close_1m(bar_obj, vwap=vwap)

            # Feed squeeze detector (bar mode was missing this entirely)
            if sq_enabled:
                pm_high = bar_builder.get_premarket_high(symbol)
                pm_bf = bar_builder.get_premarket_bull_flag_high(symbol)
                sq_det.update_premarket_levels(pm_high, pm_bf)
                sq_msg = sq_det.on_bar_close_1m(bar_obj, vwap=vwap)
                if verbose and sq_msg:
                    print(f"  [{time_str}] {sq_msg}", flush=True)

            # Feed continuation detector (bar mode — only when SQ is fully idle)
            _ct_sq_idle_bar = (not sq_enabled) or (sq_det._state == "IDLE" and not sq_det._in_trade)
            if ct_enabled and sim_mgr.open_trade is None and _ct_sq_idle_bar:
                ct_msg_bar = ct_det.on_bar_close_1m(bar_obj, vwap=vwap)
                if verbose and ct_msg_bar:
                    print(f"  [{time_str}] {ct_msg_bar}", flush=True)

            # Feed behavior metrics
            if _bm is not None:
                _bm.on_1m_bar(o, h, l, c, v, time_str, vwap)

            # Decrement stop-hit re-entry cooldown
            sim_mgr.on_bar_close_1m_cooldown()

            # Topping wicky exit (with grace period after entry)
            if (sim_mgr.open_trade is not None
                and not sim_mgr.open_trade.closed
                and "TOPPING_WICKY" in (det.last_patterns or [])
                and not _in_tw_grace_bar(time_str)):
                # Profit gate: suppress TW on confirmed runners (profit >= min R)
                _tw_profit_ok = True
                if _tw_min_profit_r > 0 and sim_mgr.open_trade.r > 0:
                    _tw_unreal = c - sim_mgr.open_trade.entry
                    _tw_r_thresh = _tw_min_profit_r * sim_mgr.open_trade.r
                    if _tw_unreal >= _tw_r_thresh:
                        _tw_profit_ok = False
                        if verbose:
                            print(f"  [{time_str}] TW_SUPPRESSED (profit_gate: ${_tw_unreal:.2f} >= {_tw_min_profit_r}R=${_tw_r_thresh:.2f}) @ {c:.4f}", flush=True)
                if _tw_profit_ok:
                    sim_mgr.on_exit_signal("topping_wicky", c, time_str)
                    if verbose:
                        print(f"  [{time_str}] TOPPING_WICKY_EXIT @ {c:.4f}", flush=True)

            if verbose:
                if msg:
                    print(f"  [{time_str}] {msg}", flush=True)

            # Track armed count
            if msg and "ARMED" in msg:
                armed_count += 1
            if det.armed is not None or (msg and "ARMED" in msg):
                setups_seen += 1

            # 3) Walk synthetic ticks for trigger/exit execution
            is_premarket = bar_builder.is_premarket(ts)
            ticks = synthetic_ticks(o, h, l, c)
            for tick in ticks:
                # --- Squeeze trigger (priority over MP) ---
                _sq_armed_before = sq_det.armed if sq_enabled else None
                if sq_enabled and _sq_armed_before is not None and sim_mgr.open_trade is None:
                    sq_trigger = sq_det.on_trade_price(tick, is_premarket=is_premarket)
                    if sq_trigger and "ENTRY SIGNAL" in sq_trigger:
                        _sq_toxic = check_toxic_filters(
                            entry_price=_sq_armed_before.trigger_high,
                            stop_price=_sq_armed_before.stop_low,
                            gap_pct=gap_pct,
                            pm_volume=pm_volume,
                            candidates_count=candidates_count,
                            month=date.month,
                        )
                        _sq_blocked = False
                        if _sq_toxic['action'] == 'BLOCK':
                            if verbose:
                                print(f"  [{time_str}] TOXIC_BLOCK {symbol}: {_sq_toxic['reason']}", flush=True)
                            _sq_blocked = True
                        elif _scanner_gap_pct > 0 and _scanner_gap_pct < _pillar_min_gap:
                            if verbose:
                                print(f"  [{time_str}] PILLAR_BLOCK: gap {_scanner_gap_pct:.1f}% < {_pillar_min_gap}%", flush=True)
                            _sq_blocked = True
                        elif _scanner_rvol > 0 and _scanner_rvol < _pillar_min_rvol:
                            if verbose:
                                print(f"  [{time_str}] PILLAR_BLOCK: RVOL {_scanner_rvol:.1f}x < {_pillar_min_rvol}x", flush=True)
                            _sq_blocked = True
                        elif _sq_armed_before.trigger_high < _pillar_min_price or _sq_armed_before.trigger_high > _pillar_max_price:
                            if verbose:
                                print(f"  [{time_str}] PILLAR_BLOCK: price ${_sq_armed_before.trigger_high:.2f} outside ${_pillar_min_price}-${_pillar_max_price}", flush=True)
                            _sq_blocked = True

                        if not _sq_blocked:
                            _sq_size_mult = getattr(_sq_armed_before, 'size_mult', 1.0)
                            _sq_eff_mult = _sq_toxic.get('multiplier', 1.0) if _sq_toxic['action'] == 'HALF_RISK' else 1.0
                            _sq_eff_mult *= _sq_size_mult
                            _sq_saved_risk = None
                            if _sq_eff_mult < 1.0:
                                _sq_saved_risk = sim_mgr.risk_dollars
                                sim_mgr.risk_dollars = _sq_saved_risk * _sq_eff_mult
                            trade = sim_mgr.on_signal(
                                symbol=symbol,
                                entry=_sq_armed_before.trigger_high,
                                stop=_sq_armed_before.stop_low,
                                r=_sq_armed_before.r,
                                score=_sq_armed_before.score,
                                detail=_sq_armed_before.score_detail,
                                time_str=time_str,
                                setup_type="squeeze",
                                size_mult=_sq_size_mult,
                            )
                            if _sq_saved_risk is not None:
                                sim_mgr.risk_dollars = _sq_saved_risk
                            if trade:
                                sq_det.notify_trade_opened()
                                if verbose:
                                    print(
                                        f"  [{time_str}] SQ_ENTRY: {trade.entry:.4f} stop={trade.stop:.4f} "
                                        f"R={trade.r:.4f} qty={trade.qty_total} score={trade.score:.1f} "
                                        f"setup_type=squeeze",
                                        flush=True,
                                    )

                # --- Continuation trigger (bar mode, after SQ, before MP) ---
                _ct_armed_before_bar = ct_det.armed if ct_enabled else None
                if ct_enabled and _ct_armed_before_bar is not None and sim_mgr.open_trade is None:
                    _ct_sq_deferred_bar = False
                    if sq_enabled and (sq_det._state != "IDLE" or sq_det._in_trade):
                        _ct_sq_deferred_bar = True
                    if not _ct_sq_deferred_bar:
                        ct_trigger_bar = ct_det.on_trade_price(tick, is_premarket=is_premarket)
                        if ct_trigger_bar and "ENTRY SIGNAL" in ct_trigger_bar:
                            trade = sim_mgr.on_signal(
                                symbol=symbol,
                                entry=_ct_armed_before_bar.trigger_high,
                                stop=_ct_armed_before_bar.stop_low,
                                r=_ct_armed_before_bar.r,
                                score=_ct_armed_before_bar.score,
                                detail=_ct_armed_before_bar.score_detail,
                                time_str=time_str,
                                setup_type="continuation",
                                size_mult=_ct_armed_before_bar.size_mult,
                            )
                            if trade and verbose:
                                print(
                                    f"  [{time_str}] CT_ENTRY: {trade.entry:.4f} stop={trade.stop:.4f} "
                                    f"R={trade.r:.4f} qty={trade.qty_total} score={trade.score:.1f} "
                                    f"setup_type=continuation",
                                    flush=True,
                                )

                # Standard micro pullback / MP V2 re-entry trigger
                armed_before = det.armed
                trigger_msg = det.on_trade_price(tick, is_premarket=is_premarket)
                if trigger_msg and "ENTRY SIGNAL" in trigger_msg and armed_before:
                    _armed_setup_type = getattr(armed_before, 'setup_type', 'micro_pullback')
                    # V6.1: Toxic entry filters
                    _toxic = check_toxic_filters(
                        entry_price=armed_before.trigger_high,
                        stop_price=armed_before.stop_low,
                        gap_pct=gap_pct,
                        pm_volume=pm_volume,
                        candidates_count=candidates_count,
                        month=date.month,
                    )
                    if _toxic['action'] == 'BLOCK':
                        if verbose:
                            print(f"  [{time_str}] TOXIC_BLOCK {symbol}: {_toxic['reason']}", flush=True)
                    elif _scanner_gap_pct > 0 and _scanner_gap_pct < _pillar_min_gap:
                        if verbose:
                            print(f"  [{time_str}] PILLAR_BLOCK: gap {_scanner_gap_pct:.1f}% < {_pillar_min_gap}%", flush=True)
                    elif _scanner_rvol > 0 and _scanner_rvol < _pillar_min_rvol:
                        if verbose:
                            print(f"  [{time_str}] PILLAR_BLOCK: RVOL {_scanner_rvol:.1f}x < {_pillar_min_rvol}x", flush=True)
                    elif armed_before.trigger_high < _pillar_min_price or armed_before.trigger_high > _pillar_max_price:
                        if verbose:
                            print(f"  [{time_str}] PILLAR_BLOCK: price ${armed_before.trigger_high:.2f} outside ${_pillar_min_price}-${_pillar_max_price}", flush=True)
                    elif _min_entry_score > 0 and armed_before.score < _min_entry_score:
                        if verbose:
                            print(f"  [{time_str}] ENTRY_BLOCKED: score {armed_before.score:.1f} < min {_min_entry_score}", flush=True)
                    elif not mp_enabled and _armed_setup_type != "mp_reentry":
                        if verbose:
                            print(f"  [{time_str}] MP_DISABLED: would-be entry @ {armed_before.trigger_high:.4f} score={armed_before.score:.1f} (WB_MP_ENABLED=0)", flush=True)
                    elif _armed_setup_type == "mp_reentry" and _mp_v2_sq_priority and sq_enabled and (sq_det._state != "IDLE" or sq_det._in_trade):
                        if verbose:
                            print(f"  [{time_str}] MP_V2_DEFERRED: SQ has priority (state={sq_det._state}, in_trade={sq_det._in_trade})", flush=True)
                    else:
                        _saved_risk = None
                        _qg_size_mult = getattr(armed_before, 'size_mult', 1.0)
                        _effective_mult = _toxic.get('multiplier', 1.0) if _toxic['action'] == 'HALF_RISK' else 1.0
                        _effective_mult *= _qg_size_mult
                        if _effective_mult < 1.0:
                            _saved_risk = sim_mgr.risk_dollars
                            sim_mgr.risk_dollars = _saved_risk * _effective_mult
                            if verbose:
                                parts = []
                                if _toxic['action'] == 'HALF_RISK':
                                    parts.append(f"toxic={_toxic['multiplier']:.0%}")
                                if _qg_size_mult < 1.0:
                                    parts.append(f"qg_price={_qg_size_mult:.0%}")
                                print(f"  [{time_str}] SIZE_REDUCE {symbol}: {'+'.join(parts)} (risk ${sim_mgr.risk_dollars:.0f})", flush=True)
                        trade = sim_mgr.on_signal(
                            symbol=symbol,
                            entry=armed_before.trigger_high,
                            stop=armed_before.stop_low,
                            r=armed_before.r,
                            score=armed_before.score,
                            detail=armed_before.score_detail,
                            time_str=time_str,
                            setup_type=_armed_setup_type,
                            size_mult=_qg_size_mult,
                        )
                        if _saved_risk is not None:
                            sim_mgr.risk_dollars = _saved_risk
                        if trade and verbose:
                            _entry_label = "MP_V2_ENTRY" if _armed_setup_type == "mp_reentry" else "ENTRY"
                            print(
                                f"  [{time_str}] {_entry_label}: {trade.entry:.4f} stop={trade.stop:.4f} "
                                f"R={trade.r:.4f} qty={trade.qty_total} score={trade.score:.1f} "
                                f"setup_type={_armed_setup_type}",
                                flush=True,
                            )

                # Check stops/TP/runner
                sim_mgr.on_tick(tick, time_str)

        # Force-close any open position at sim end
        if sim_bars:
            last_bar, last_ts = sim_bars[-1]
            last_close = float(last_bar.close)
            last_time = last_ts.astimezone(ET).strftime("%H:%M")
            sim_mgr.force_close(last_close, last_time)

    # ── Report ──
    trades = sim_mgr.closed_trades
    l2_info = "L2=OFF"
    if use_ticks:
        l2_info += " [TICK mode]"
        report_vwap = bb_1m.get_vwap(symbol)
        report_sim_count = len(tick_trades)
    else:
        report_vwap = bar_builder.get_vwap(symbol)
        report_sim_count = len(sim_bars)
    print_report(
        symbol=symbol,
        date_str=date_str,
        start_et=start_et_str,
        end_et=end_et_str,
        risk=_risk,
        min_score=_min_score,
        macd_gate=_macd_gate,
        slippage=slippage,
        seed_count=len(seed_bars),
        sim_count=report_sim_count,
        ema=det.ema,
        vwap=report_vwap,
        trades=trades,
        armed_count=armed_count,
        signals_received=sim_mgr.signals_received,
        l2_info=l2_info,
        exit_mode=_exit_mode,
        max_entries=_max_entries,
        cooldown_min=_cooldown_min,
    )

    # Equity tracking report (machine-parseable for wrapper scripts)
    if sim_mgr.account_equity > 0:
        day_pnl = sum(t.pnl() for t in trades)
        print(f"  EQUITY: ${sim_mgr.current_equity:,.2f} (day P&L: ${day_pnl:+,.0f}, open notional: ${sim_mgr.open_notional:,.0f})")

    # Export study JSON if requested
    if export_json and _bm is not None:
        config = {
            "exit_mode": _exit_mode,
            "risk": _risk,
            "tw_min_profit_r": _tw_min_profit_r,
            "be_min_profit_r": _be_min_profit_r,
            "reentry_cooldown_bars": _reentry_cooldown_bars,
            "min_tags": int(os.getenv("WB_MIN_TAGS", "1")),
        }
        export_study_json(
            symbol=symbol,
            date_str=date_str,
            start_et=start_et_str,
            end_et=end_et_str,
            trades=trades,
            metrics=_bm,
            stock_info=_sim_stock_info,
            config=config,
        )

    return trades


# ─────────────────────────────────────────────
# Report printer
# ─────────────────────────────────────────────

def print_report(
    symbol, date_str, start_et, end_et, risk, min_score, macd_gate,
    slippage, seed_count, sim_count, ema, vwap, trades, armed_count,
    signals_received, l2_info="L2=OFF", exit_mode="signal",
    max_entries=2, cooldown_min=10,
):
    bar = "=" * 70

    print(f"\n{bar}")
    print(f"  BACKTEST REPORT: {symbol} -- {date_str} ({start_et} -> {end_et} ET)")
    print(bar)
    print(
        f"  Settings: risk=${risk:.0f}  min_score={min_score}  "
        f"MACD_gate={'ON' if macd_gate else 'OFF'}  slippage=${slippage:.2f}  exit={exit_mode}  "
        f"cooldown={max_entries}/{cooldown_min}m  {l2_info}"
    )
    ema_str = f"{ema:.4f}" if ema else "N/A"
    vwap_str = f"{vwap:.4f}" if vwap else "N/A"
    print(f"  Bars: {sim_count} sim + {seed_count} seed  |  EMA9={ema_str}  VWAP={vwap_str}")
    print(bar)

    if not trades:
        print("\n  No trades taken.\n")
        print(f"  Armed: {armed_count}  |  Signals: {signals_received}")
        print(bar)
        return

    # Header
    print()
    print(f"  {'#':>3}  {'TIME':>6}  {'ENTRY':>7}  {'STOP':>7}  {'R':>6}  {'SCORE':>5}  {'EXIT':>7}  {'REASON':<20}  {'P&L':>8}  {'R-MULT':>6}  {'XTIME':>5}")
    print(f"  {'─'*3}  {'─'*6}  {'─'*7}  {'─'*7}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*20}  {'─'*8}  {'─'*6}  {'─'*5}")

    total_pnl = 0.0
    wins = 0
    losses = 0
    largest_win = 0.0
    largest_loss = 0.0

    for i, t in enumerate(trades, 1):
        # Multi-tranche display: show each tranche exit on its own line
        has_t1_tp = t.tp_hit and t.core_exit_reason in ("take_profit_core", "take_profit_t1")
        if has_t1_tp:
            # T1/Core took profit — show T1 line
            core_pnl = (t.core_exit_price - t.entry) * t.qty_core
            core_r = core_pnl / (t.r * t.qty_total) if t.r > 0 else 0
            t1_label = "t1_tp" if t.qty_t2 > 0 else "core_tp"
            _xtime = t.runner_exit_time or t.t2_exit_time or t.core_exit_time or ""
            print(
                f"  {i:>3}  {t.entry_time:>6}  {t.entry:>7.4f}  {t.stop:>7.4f}  {t.r:>6.4f}  {t.score:>5.1f}  "
                f"{t.core_exit_price:>7.4f}  {t1_label:<20}  {core_pnl:>+8.0f}  {core_r:>+6.1f}R  {_xtime:>5}"
            )
            # T2 line (3-tranche only)
            if t.qty_t2 > 0 and t.t2_exit_price > 0:
                t2_pnl = (t.t2_exit_price - t.entry) * t.qty_t2
                t2_r = t2_pnl / (t.r * t.qty_total) if t.r > 0 else 0
                print(
                    f"  {'':>3}  {'':>6}  {'':>7}  {'':>7}  {'':>6}  {'':>5}  "
                    f"{t.t2_exit_price:>7.4f}  {t.t2_exit_reason:<20}  {t2_pnl:>+8.0f}  {t2_r:>+6.1f}R"
                )
            # Runner/T3 line
            if t.qty_runner > 0 and t.runner_exit_price > 0:
                runner_pnl = (t.runner_exit_price - t.entry) * t.qty_runner
                runner_r = runner_pnl / (t.r * t.qty_total) if t.r > 0 else 0
                print(
                    f"  {'':>3}  {'':>6}  {'':>7}  {'':>7}  {'':>6}  {'':>5}  "
                    f"{t.runner_exit_price:>7.4f}  {t.runner_exit_reason:<20}  {runner_pnl:>+8.0f}  {runner_r:>+6.1f}R"
                )
        else:
            # Full stop or sim_end — all tranches exit at same price
            exit_price = t.core_exit_price if t.core_exit_price > 0 else t.runner_exit_price
            reason = t.core_exit_reason if t.core_exit_reason else t.runner_exit_reason
            trade_pnl = t.pnl()
            trade_r = t.r_multiple()
            _xtime = t.runner_exit_time or t.t2_exit_time or t.core_exit_time or ""
            print(
                f"  {i:>3}  {t.entry_time:>6}  {t.entry:>7.4f}  {t.stop:>7.4f}  {t.r:>6.4f}  {t.score:>5.1f}  "
                f"{exit_price:>7.4f}  {reason:<20}  {trade_pnl:>+8.0f}  {trade_r:>+6.1f}R  {_xtime:>5}"
            )

        trade_pnl = t.pnl()
        total_pnl += trade_pnl
        if trade_pnl >= 0:
            wins += 1
            largest_win = max(largest_win, trade_pnl)
        else:
            losses += 1
            largest_loss = min(largest_loss, trade_pnl)

    # Summary
    print()
    print(f"  {'─' * 66}")
    print(f"  SUMMARY")
    print(f"  {'─' * 66}")
    total = wins + losses
    wr = (wins / total * 100) if total > 0 else 0
    avg_r = (total_pnl / (risk * total)) if total > 0 and risk > 0 else 0
    print(f"  Trades: {total}  |  Wins: {wins}  |  Losses: {losses}  |  Win Rate: {wr:.1f}%")
    print(f"  Gross P&L: ${total_pnl:+,.0f}  |  Avg R-Multiple: {avg_r:+.1f}R")
    print(f"  Largest Win: ${largest_win:+,.0f}  |  Largest Loss: ${largest_loss:+,.0f}")
    print(f"  Armed: {armed_count}  |  Signals: {signals_received}  |  Entered: {total}")
    print(bar)
    print()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Warrior Bot Backtester — replay historical bars through the live detection engine"
    )
    parser.add_argument("args", nargs="+", help="SYMBOL [SYMBOL2 ...] DATE [START_ET] [END_ET]")
    parser.add_argument("--risk", type=float, default=None, help="Override WB_RISK_DOLLARS")
    parser.add_argument("--min-score", type=float, default=None, help="Override WB_MIN_SCORE")
    parser.add_argument("--slippage", type=float, default=0.02, help="Entry slippage in dollars (default 0.02)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print all detector signals")
    parser.add_argument("--no-fundamentals", action="store_true", help="Skip fetching fundamental data (faster batch runs)")
    parser.add_argument("--ticks", action="store_true", help="Use tick-level data for bar construction (matches live bot behavior)")
    parser.add_argument("--feed", choices=["alpaca", "databento"], default="alpaca",
                        help="Data source for tick data (default: alpaca). Use 'databento' for high-fidelity trade data.")
    parser.add_argument("--tick-cache", type=str, default=None,
                        help="Path to tick cache directory. Loads ticks from local files instead of API.")
    parser.add_argument("--export-json", action="store_true", help="Export behavioral study JSON to study_data/")
    parser.add_argument("--candidates", type=int, default=0, help="Total scanner candidates for this day (toxic filter 1)")
    parser.add_argument("--gap", type=float, default=0.0, help="Pre-market gap %% (toxic filter 2)")
    parser.add_argument("--pmvol", type=float, default=0.0, help="Pre-market volume in shares (toxic filter 2)")
    parser.add_argument("--equity", type=float, default=0,
                        help="Starting account equity for buying power tracking (0=disabled)")
    args = parser.parse_args()

    # Parse positional args: symbols, date, optional start/end times
    positional = args.args
    symbols = []
    date_str = None
    start_et = "09:30"
    end_et = "16:00"
    start_set = False

    for a in positional:
        # Date looks like YYYY-MM-DD
        if len(a) == 10 and a[4] == "-" and a[7] == "-":
            date_str = a
        # Time looks like HH:MM
        elif ":" in a and len(a) <= 5:
            if date_str is not None and not start_set:
                start_et = a
                start_set = True
            elif date_str is not None:
                end_et = a
        else:
            symbols.append(a.upper())

    if not date_str:
        print("Error: no date provided (YYYY-MM-DD)")
        sys.exit(1)
    if not symbols:
        print("Error: no symbols provided")
        sys.exit(1)

    # Pass equity to env for buying power tracking
    if args.equity > 0:
        os.environ["WB_SIM_ACCOUNT_EQUITY"] = str(args.equity)

    # When --feed databento is used, force tick mode on
    if args.feed == "databento":
        args.ticks = True

    feed_str = f" | Feed: {args.feed.upper()}" if args.feed != "alpaca" else ""
    mode_str = "TICK MODE" if args.ticks else "BAR MODE"
    print(f"\n{'=' * 70}")
    print(f"  WARRIOR BOT BACKTESTER ({mode_str}{feed_str})")
    print(f"  Symbols: {', '.join(symbols)}  |  Date: {date_str}  |  Window: {start_et} -> {end_et} ET")
    print(f"{'=' * 70}")

    all_trades = []
    for sym in symbols:
        trades = run_simulation(
            symbol=sym,
            date_str=date_str,
            start_et_str=start_et,
            end_et_str=end_et,
            risk_dollars=args.risk,
            min_score=args.min_score,
            slippage=args.slippage,
            verbose=args.verbose,
            no_fundamentals=args.no_fundamentals,
            use_ticks=args.ticks,
            feed=args.feed,
            export_json=args.export_json,
            candidates_count=args.candidates,
            gap_pct=args.gap,
            pm_volume=args.pmvol,
            tick_cache=args.tick_cache,
        )
        all_trades.extend(trades)

    # Multi-symbol summary
    if len(symbols) > 1 and all_trades:
        total_pnl = sum(t.pnl() for t in all_trades)
        wins = sum(1 for t in all_trades if t.pnl() >= 0)
        losses = sum(1 for t in all_trades if t.pnl() < 0)
        total = wins + losses
        wr = (wins / total * 100) if total > 0 else 0
        print(f"\n{'=' * 70}")
        print(f"  COMBINED SUMMARY ({len(symbols)} symbols)")
        print(f"  Trades: {total}  |  Wins: {wins}  |  Losses: {losses}  |  Win Rate: {wr:.1f}%")
        print(f"  Gross P&L: ${total_pnl:+,.0f}")
        print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
