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
import math
import os
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
from l2_signals import L2SignalDetector
from l2_entry import L2EntryDetector

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
    runner_stop: float = 0.0
    closed: bool = False

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
        self.stock_info = stock_info
        self.quality_min_float = quality_min_float

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

        self.open_trade: Optional[SimTrade] = None
        self.closed_trades: list[SimTrade] = []
        self.signals_received: int = 0

        # Per-symbol re-entry cooldown tracking
        self._symbol_entry_count: dict[str, int] = {}
        self._symbol_cooldown_until: dict[str, int] = {}  # symbol -> minute offset when cooldown expires

    def _time_to_minutes(self, time_str: str) -> int:
        """Convert 'HH:MM' to minutes since midnight for cooldown tracking."""
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    def on_signal(self, symbol: str, entry: float, stop: float, r: float,
                  score: float, detail: str, time_str: str) -> Optional[SimTrade]:
        self.signals_received += 1

        if self.open_trade is not None:
            return None

        if r <= 0 or r < self.min_r:
            return None

        # Per-symbol re-entry cooldown
        now_min = self._time_to_minutes(time_str)
        cooldown_until = self._symbol_cooldown_until.get(symbol)
        if cooldown_until is not None:
            if now_min < cooldown_until:
                return None  # still in cooldown
            else:
                # Cooldown expired, reset
                self._symbol_entry_count[symbol] = 0
                self._symbol_cooldown_until.pop(symbol, None)

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
        if qty <= 0:
            return None

        if self.three_tranche_enabled:
            # 3-tranche split: T1 (core) + T2 + T3 (runner)
            qty_core = max(1, int(math.floor(qty * self.scale_t1)))
            qty_t2 = max(0, int(math.floor(qty * self.scale_t2)))
            qty_runner = max(0, qty - qty_core - qty_t2)
            # Guard: if qty is too small for T3, fold remainder into T2
            if qty_runner <= 0 and qty_t2 > 0:
                qty_runner = 0
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
            entry_time=time_str,
            peak=fill_price,
            runner_stop=stop,
        )
        self.open_trade = t

        # Track re-entry count and start cooldown when cap is reached
        entry_count = self._symbol_entry_count.get(symbol, 0) + 1
        self._symbol_entry_count[symbol] = entry_count
        if entry_count >= self.max_entries_per_symbol:
            self._symbol_cooldown_until[symbol] = now_min + self.symbol_cooldown_min

        return t

    def on_tick(self, price: float, time_str: str):
        t = self.open_trade
        if t is None or t.closed:
            return

        t.peak = max(t.peak, price)

        # --- MAX LOSS CAP (hard safety net) ---
        if self.max_loss_r > 0 and t.r > 0:
            loss_per_share = t.entry - price
            if loss_per_share >= self.max_loss_r * t.r:
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
            if t.tp_hit:
                trail_stop = t.peak * (1.0 - self.signal_trail_pct)
                t.stop = max(t.stop, trail_stop)

            # Check stop (hard or trailed)
            if price <= t.stop:
                reason = "trail_stop" if t.tp_hit else "stop_hit"
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

    def _close(self, t: SimTrade):
        t.closed = True
        self.closed_trades.append(t)
        self.open_trade = None


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
    req = StockTradesRequest(
        symbol_or_symbols=[symbol],
        start=start_utc,
        end=end_utc,
        feed="sip",
    )
    trade_set = hist_client.get_stock_trades(req)
    return trade_set.data.get(symbol, [])


def synthetic_ticks(o, h, l, c):
    """O→H→L→C for green bars, O→L→H→C for red bars."""
    if c >= o:
        return [o, h, l, c]
    else:
        return [o, l, h, c]


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
):
    # l2-entry implies l2 data
    if use_l2_entry:
        use_l2 = True

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
    _tw_grace_min = int(os.getenv("WB_TOPPING_WICKY_GRACE_MIN", "3"))

    # 3-tranche exit scaling
    _3tranche_enabled = os.getenv("WB_3TRANCHE_ENABLED", "0") == "1"
    _scale_t1 = float(os.getenv("WB_SCALE_T1", "0.40"))
    _scale_t2 = float(os.getenv("WB_SCALE_T2", "0.35"))
    _t1_tp_r = float(os.getenv("WB_T1_TP_R", "1.0"))
    _t2_tp_r = float(os.getenv("WB_T2_TP_R", "2.0"))
    _t2_stop_lock_r = float(os.getenv("WB_T2_STOP_LOCK_R", "0.5"))

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

    # Pass gap_pct for conviction floor gate
    if _sim_stock_info is not None and hasattr(_sim_stock_info, 'gap_pct'):
        det.gap_pct = _sim_stock_info.gap_pct

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

    # L2 entry detector (separate strategy, only used with --l2-entry)
    l2_entry_det = L2EntryDetector() if use_l2_entry else None

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
    )

    # ── L2 data (optional) ──
    l2_snapshots = []
    l2_det = None
    if use_l2:
        try:
            from databento_feed import fetch_l2_historical
            l2_snapshots = fetch_l2_historical(
                symbol, date_str,
                start_et=start_et_str,
                end_et=end_et_str,
            )
            if l2_snapshots:
                l2_det = L2SignalDetector()
                print(f"  L2 data loaded: {len(l2_snapshots)} snapshots", flush=True)
            else:
                print(f"  L2: no data available (running without L2)", flush=True)
        except Exception as e:
            print(f"  L2: failed to load ({e}) — running without L2", flush=True)

    # ── Seed phase ──
    for b, ts in seed_bars:
        o = float(b.open)
        h = float(b.high)
        l = float(b.low)
        c = float(b.close)
        v = float(b.volume)
        det.seed_bar_close(o, h, l, c, v)
        if l2_entry_det:
            l2_entry_det.seed_bar_close(o, h, l, c, v)
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

            # Feed parabolic regime detector
            if _parabolic_det is not None:
                t = sim_mgr.open_trade
                _parabolic_det.on_10s_bar(
                    bar.open, bar.high, bar.low, bar.close, bar.volume,
                    t.entry, t.r,
                )

            # Check parabolic suppression (new detector or legacy)
            # In signal mode, do NOT suppress exits — cascading re-entry IS the strategy
            def _should_suppress_pattern_exit() -> tuple[bool, str]:
                if _exit_mode == "signal":
                    # Signal mode: no exit suppression (VERO's edge comes from exit + re-enter)
                    return False, ""
                if _parabolic_det is not None:
                    if _parabolic_det.should_suppress_exit():
                        return True, "parabolic_regime"
                    return False, ""
                # Legacy fallback
                if _in_parabolic_grace_sim(bar.close):
                    return True, "parabolic_grace"
                return False, ""

            # Topping wicky exit on 10s bars (with grace period after entry)
            if ("TOPPING_WICKY" in (det.last_patterns or [])
                and not _in_tw_grace(time_str)):
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

            # Process L2 snapshots for this bar's time window (if available)
            l2_state_bar = None
            if l2_det and l2_snapshots:
                bar_end = bar.start_utc + timedelta(minutes=1)
                bar_l2 = [s for s in l2_snapshots if bar.start_utc <= s.timestamp < bar_end]
                for snap in bar_l2:
                    l2_det.on_snapshot(snap)
                l2_state_bar = l2_det.get_state(symbol)

            msg = det.on_bar_close_1m(bar, vwap=vwap, l2_state=l2_state_bar)

            # Topping wicky exit after 1m bar close (with grace period after entry)
            if (sim_mgr.open_trade is not None
                and not sim_mgr.open_trade.closed
                and "TOPPING_WICKY" in (det.last_patterns or [])
                and not _in_tw_grace(time_str)):
                sim_mgr.on_exit_signal("topping_wicky", bar.close, time_str)
                if verbose:
                    print(f"  [{time_str}] TOPPING_WICKY_EXIT @ {bar.close:.4f}", flush=True)

            # L2 exit signal
            if (sim_mgr.open_trade is not None
                and not sim_mgr.open_trade.closed
                and l2_state_bar is not None):
                l2_exit = det.check_l2_exit(l2_state_bar)
                if l2_exit:
                    sim_mgr.on_exit_signal(l2_exit, bar.close, time_str)
                    if verbose:
                        print(f"  [{time_str}] {l2_exit.upper()}_EXIT @ {bar.close:.4f}", flush=True)

            if verbose and msg:
                print(f"  [{time_str}] {msg}", flush=True)

            if msg and "ARMED" in msg:
                tick_sim_state["armed_count"] += 1

            tick_sim_state["last_1m_msg"] = msg
            tick_sim_state["last_1m_time"] = time_str

        # Create bar builders with callbacks
        bb_10s = TradeBarBuilder(on_bar_close=on_10s_close, et_tz=ET, interval_seconds=10)
        bb_1m = TradeBarBuilder(on_bar_close=on_1m_close, et_tz=ET, interval_seconds=60)

        # Seed BOTH builders with premarket bars (for VWAP/HOD/PM tracking)
        for b, ts in seed_bars:
            o = float(b.open)
            h = float(b.high)
            l = float(b.low)
            c = float(b.close)
            v = float(b.volume)
            bb_10s.seed_bar_close(symbol, o, h, l, c, v, ts)
            bb_1m.seed_bar_close(symbol, o, h, l, c, v, ts)

        # Fetch actual trades for the sim window
        if feed == "databento":
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
        else:
            print(f"  Fetching tick data from Alpaca...", flush=True)
            tick_trades = fetch_trades(symbol, sim_start_utc, sim_end_utc)
        print(f"  Tick replay: {len(tick_trades)} trades for sim window", flush=True)

        if not tick_trades:
            print(f"  No tick data in window {start_et_str}-{end_et_str}. Skipping.", flush=True)
        else:
            last_price = None
            last_time_str = None

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

                # Trigger check on every tick (like live bot's on_trade)
                is_premarket = bb_1m.is_premarket(ts)
                armed_before = det.armed
                trigger_msg = det.on_trade_price(price, is_premarket=is_premarket)
                if trigger_msg and "ENTRY SIGNAL" in trigger_msg and armed_before:
                    trade = sim_mgr.on_signal(
                        symbol=symbol,
                        entry=armed_before.trigger_high,
                        stop=armed_before.stop_low,
                        r=armed_before.r,
                        score=armed_before.score,
                        detail=armed_before.score_detail,
                        time_str=time_str,
                    )
                    if trade and verbose:
                        print(
                            f"  [{time_str}] ENTRY: {trade.entry:.4f} stop={trade.stop:.4f} "
                            f"R={trade.r:.4f} qty={trade.qty_total} score={trade.score:.1f}",
                            flush=True,
                        )

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

            # 2) Construct Bar object and feed to detector
            bar_obj = Bar(symbol=symbol, start_utc=ts, open=o, high=h, low=l, close=c, volume=int(v))
            vwap = bar_builder.get_vwap(symbol)

            # Process L2 snapshots for this bar's time window (if available)
            l2_state = None
            if l2_det and l2_snapshots:
                bar_end = ts + timedelta(minutes=1)
                bar_l2 = [s for s in l2_snapshots if ts <= s.timestamp < bar_end]
                for snap in bar_l2:
                    l2_det.on_snapshot(snap)
                l2_state = l2_det.get_state(symbol)

            msg = det.on_bar_close_1m(bar_obj, vwap=vwap, l2_state=l2_state)

            # Topping wicky exit (with grace period after entry)
            if (sim_mgr.open_trade is not None
                and not sim_mgr.open_trade.closed
                and "TOPPING_WICKY" in (det.last_patterns or [])
                and not _in_tw_grace_bar(time_str)):
                sim_mgr.on_exit_signal("topping_wicky", c, time_str)
                if verbose:
                    print(f"  [{time_str}] TOPPING_WICKY_EXIT @ {c:.4f}", flush=True)

            # L2 exit signal
            if (sim_mgr.open_trade is not None
                and not sim_mgr.open_trade.closed
                and l2_state is not None):
                l2_exit = det.check_l2_exit(l2_state)
                if l2_exit:
                    sim_mgr.on_exit_signal(l2_exit, c, time_str)
                    if verbose:
                        print(f"  [{time_str}] {l2_exit.upper()}_EXIT @ {c:.4f}", flush=True)

            # L2 entry detector (separate strategy)
            l2e_msg = None
            if l2_entry_det:
                l2e_msg = l2_entry_det.on_bar_close(bar_obj, vwap=vwap, l2_state=l2_state)

            if verbose:
                if msg:
                    print(f"  [{time_str}] {msg}", flush=True)
                if l2e_msg:
                    print(f"  [{time_str}] {l2e_msg}", flush=True)

            # Track armed count from whichever strategy is active
            if l2_entry_det:
                if l2e_msg and "L2E_ARMED" in l2e_msg:
                    armed_count += 1
                if l2_entry_det.armed is not None:
                    setups_seen += 1
            else:
                if msg and "ARMED" in msg:
                    armed_count += 1
                if det.armed is not None or (msg and "ARMED" in msg):
                    setups_seen += 1

            # 3) Walk synthetic ticks for trigger/exit execution
            is_premarket = bar_builder.is_premarket(ts)
            ticks = synthetic_ticks(o, h, l, c)
            for tick in ticks:
                # Check L2 entry trigger (separate strategy)
                if l2_entry_det:
                    l2e_armed_before = l2_entry_det.armed
                    l2e_trigger = l2_entry_det.on_trade_price(tick)
                    if l2e_trigger and l2e_armed_before:
                        trade = sim_mgr.on_signal(
                            symbol=symbol,
                            entry=l2e_armed_before.trigger_high,
                            stop=l2e_armed_before.stop_low,
                            r=l2e_armed_before.r,
                            score=l2e_armed_before.score,
                            detail=l2e_armed_before.score_detail,
                            time_str=time_str,
                        )
                        if trade and verbose:
                            print(
                                f"  [{time_str}] L2E_FILL: {trade.entry:.4f} stop={trade.stop:.4f} "
                                f"R={trade.r:.4f} qty={trade.qty_total} score={trade.score:.1f}",
                                flush=True,
                            )
                else:
                    # Standard micro pullback trigger
                    armed_before = det.armed
                    trigger_msg = det.on_trade_price(tick, is_premarket=is_premarket)
                    if trigger_msg and "ENTRY SIGNAL" in trigger_msg and armed_before:
                        trade = sim_mgr.on_signal(
                            symbol=symbol,
                            entry=armed_before.trigger_high,
                            stop=armed_before.stop_low,
                            r=armed_before.r,
                            score=armed_before.score,
                            detail=armed_before.score_detail,
                            time_str=time_str,
                        )
                        if trade and verbose:
                            print(
                                f"  [{time_str}] ENTRY: {trade.entry:.4f} stop={trade.stop:.4f} "
                                f"R={trade.r:.4f} qty={trade.qty_total} score={trade.score:.1f}",
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
    l2_info = f"L2={len(l2_snapshots)} snaps" if l2_snapshots else "L2=OFF"
    if use_l2_entry:
        l2_info += " [L2-ENTRY mode]"
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
    print(f"  {'#':>3}  {'TIME':>6}  {'ENTRY':>7}  {'STOP':>7}  {'R':>6}  {'SCORE':>5}  {'EXIT':>7}  {'REASON':<20}  {'P&L':>8}  {'R-MULT':>6}")
    print(f"  {'─'*3}  {'─'*6}  {'─'*7}  {'─'*7}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*20}  {'─'*8}  {'─'*6}")

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
            print(
                f"  {i:>3}  {t.entry_time:>6}  {t.entry:>7.4f}  {t.stop:>7.4f}  {t.r:>6.4f}  {t.score:>5.1f}  "
                f"{t.core_exit_price:>7.4f}  {t1_label:<20}  {core_pnl:>+8.0f}  {core_r:>+6.1f}R"
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
            print(
                f"  {i:>3}  {t.entry_time:>6}  {t.entry:>7.4f}  {t.stop:>7.4f}  {t.r:>6.4f}  {t.score:>5.1f}  "
                f"{exit_price:>7.4f}  {reason:<20}  {trade_pnl:>+8.0f}  {trade_r:>+6.1f}R"
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
    parser.add_argument("--l2", action="store_true", help="Enable Level 2 order book data (requires Databento)")
    parser.add_argument("--l2-entry", action="store_true", help="Use L2-driven entry strategy instead of micro pullback")
    parser.add_argument("--no-fundamentals", action="store_true", help="Skip fetching fundamental data (faster batch runs)")
    parser.add_argument("--ticks", action="store_true", help="Use tick-level data for bar construction (matches live bot behavior)")
    parser.add_argument("--feed", choices=["alpaca", "databento"], default="alpaca",
                        help="Data source for tick data (default: alpaca). Use 'databento' for high-fidelity trade data.")
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
            use_l2=args.l2,
            use_l2_entry=args.l2_entry,
            no_fundamentals=args.no_fundamentals,
            use_ticks=args.ticks,
            feed=args.feed,
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
