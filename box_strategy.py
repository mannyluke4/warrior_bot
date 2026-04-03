"""
box_strategy.py — Mean-reversion box trading strategy.

Buys near bottom of proven 5-day range, sells near top.
Box levels come from scanner output (range_high_5d / range_low_5d).

Usage:
    from box_strategy import BoxStrategyEngine
    engine = BoxStrategyEngine(candidate_dict)
    for bar in bars_1m:
        engine.on_bar(bar)
    trades = engine.trades
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import List, Optional

import pytz

ET = pytz.timezone("US/Eastern")

# ── Env Vars ────────────────────────────────────────────────────────

# Entry
BOX_BUY_ZONE_PCT = float(os.getenv("WB_BOX_BUY_ZONE_PCT", "25"))
BOX_SELL_ZONE_PCT = float(os.getenv("WB_BOX_SELL_ZONE_PCT", "25"))
BOX_RSI_OVERSOLD = float(os.getenv("WB_BOX_RSI_OVERSOLD", "35"))
BOX_RSI_PERIOD = int(os.getenv("WB_BOX_RSI_PERIOD", "14"))
BOX_REVERSAL_CONFIRM = int(os.getenv("WB_BOX_REVERSAL_CONFIRM", "1"))
BOX_MIN_BAR_VOL_RATIO = float(os.getenv("WB_BOX_MIN_BAR_VOL_RATIO", "1.0"))

# Exit
BOX_STOP_PAD_PCT = float(os.getenv("WB_BOX_STOP_PAD_PCT", "0.5"))
BOX_TRAIL_PCT = float(os.getenv("WB_BOX_TRAIL_PCT", "30"))
BOX_TRAIL_ACTIVATION_PCT = float(os.getenv("WB_BOX_TRAIL_ACTIVATION_PCT", "50"))
BOX_BREAKOUT_INVALIDATE_PCT = float(os.getenv("WB_BOX_BREAKOUT_INVALIDATE_PCT", "0.5"))
BOX_VWAP_EXIT_ENABLED = int(os.getenv("WB_BOX_VWAP_EXIT_ENABLED", "0"))
BOX_MAX_RISK_PER_TRADE = float(os.getenv("WB_BOX_MAX_RISK_PER_TRADE", "200"))

# Session
BOX_START_ET = os.getenv("WB_BOX_START_ET", "10:00")
BOX_LAST_ENTRY_ET = os.getenv("WB_BOX_LAST_ENTRY_ET", "14:30")
BOX_HARD_CLOSE_ET = os.getenv("WB_BOX_HARD_CLOSE_ET", "15:45")
BOX_MAX_NOTIONAL = float(os.getenv("WB_BOX_MAX_NOTIONAL", "50000"))
BOX_MAX_LOSS_SESSION = float(os.getenv("WB_BOX_MAX_LOSS_SESSION", "500"))
BOX_MAX_ENTRIES_PER_STOCK = int(os.getenv("WB_BOX_MAX_ENTRIES_PER_STOCK", "2"))


def _parse_time(t_str: str) -> time:
    parts = t_str.split(":")
    return time(int(parts[0]), int(parts[1]))


START_TIME = _parse_time(BOX_START_ET)
LAST_ENTRY_TIME = _parse_time(BOX_LAST_ENTRY_ET)
HARD_CLOSE_TIME = _parse_time(BOX_HARD_CLOSE_ET)


# ── RSI ─────────────────────────────────────────────────────────────

def compute_rsi(closes: list, period: int = 14) -> float:
    """Standard Wilder RSI on a list of close prices."""
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ── Trade State ─────────────────────────────────────────────────────

@dataclass
class BoxTradeState:
    """Tracks one box trade from entry to exit."""
    symbol: str
    entry_price: float
    entry_time: datetime
    shares: int
    box_top: float
    box_bottom: float
    box_range: float
    hard_stop: float
    peak_price: float
    rsi_at_entry: float = 0.0
    bar_volume_at_entry: int = 0
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    hold_minutes: Optional[float] = None


# ── Strategy Engine ─────────────────────────────────────────────────

class BoxStrategyEngine:
    """Runs the box strategy on 1-minute bars for a single candidate."""

    def __init__(self, candidate: dict):
        self.symbol = candidate["symbol"]
        self.box_top = candidate["range_high_5d"]
        self.box_bottom = candidate["range_low_5d"]
        self.box_range = self.box_top - self.box_bottom
        self.box_mid = (self.box_top + self.box_bottom) / 2
        self.scanner_vwap = candidate.get("vwap", 0)

        # Zones
        self.buy_zone_ceiling = self.box_bottom + self.box_range * (BOX_BUY_ZONE_PCT / 100)
        self.sell_zone_floor = self.box_top - self.box_range * (BOX_SELL_ZONE_PCT / 100)
        self.hard_stop_price = self.box_bottom - (self.box_bottom * BOX_STOP_PAD_PCT / 100)

        # State
        self.trades: List[BoxTradeState] = []
        self.active_trade: Optional[BoxTradeState] = None
        self.session_pnl = 0.0
        self.entry_count = 0
        self.stopped_out = False  # hard stop / invalidation / session cap → no re-entry

        # Bar history for RSI + volume avg
        self.closes: List[float] = []
        self.volumes: List[int] = []
        self.prev_bar = None

        # VWAP tracking (computed from intraday bars)
        self._cum_tpv = 0.0
        self._cum_vol = 0
        self.vwap = 0.0

        # Intraday range tracking
        self.today_hod = 0.0
        self.today_lod = float("inf")

    def on_bar(self, bar) -> Optional[str]:
        """Process one 1-minute bar. Returns exit_reason if a trade closed, else None.

        bar must have: .date (datetime), .open, .high, .low, .close, .volume
        """
        bar_time = self._get_bar_time(bar)

        # Update intraday tracking
        self.today_hod = max(self.today_hod, bar.high)
        self.today_lod = min(self.today_lod, bar.low)

        # Update VWAP
        tp = (bar.high + bar.low + bar.close) / 3
        self._cum_tpv += tp * bar.volume
        self._cum_vol += bar.volume
        self.vwap = self._cum_tpv / self._cum_vol if self._cum_vol > 0 else bar.close

        # Update bar history
        self.closes.append(bar.close)
        self.volumes.append(bar.volume)

        # Skip bars before box window
        if bar_time < START_TIME:
            self.prev_bar = bar
            return None

        # Check exits first (if in a position)
        exit_reason = None
        if self.active_trade:
            exit_reason = self._check_exits(bar, bar_time)
            if exit_reason:
                self._close_trade(bar.close, bar.date, exit_reason)
                self.prev_bar = bar
                return exit_reason

        # Check entries (if no position)
        if not self.active_trade and not self.stopped_out:
            self._check_entry(bar, bar_time)

        self.prev_bar = bar
        return None

    def _check_exits(self, bar, bar_time: time) -> Optional[str]:
        """Check all exit rules in priority order. Returns exit reason or None."""
        t = self.active_trade
        price = bar.close

        # Update peak
        t.peak_price = max(t.peak_price, bar.high)

        # 1. Box invalidation
        invalidation_threshold = self.box_range * (BOX_BREAKOUT_INVALIDATE_PCT / 100)
        if bar.high > self.box_top + invalidation_threshold:
            return "box_invalidation_high"
        if bar.low < self.box_bottom - invalidation_threshold:
            return "box_invalidation_low"

        # 2. Hard stop
        if bar.low <= t.hard_stop:
            return "hard_stop"

        # 3. Time stop
        if bar_time >= HARD_CLOSE_TIME:
            return "time_stop"

        # 4. Session loss cap
        unrealized = (price - t.entry_price) * t.shares
        if self.session_pnl + unrealized <= -BOX_MAX_LOSS_SESSION:
            return "session_loss_cap"

        # 5. Target exit (sell zone)
        if price >= self.sell_zone_floor:
            return "target_sell_zone"

        # 6. VWAP exit (optional)
        if BOX_VWAP_EXIT_ENABLED and self.vwap > 0:
            if price >= self.vwap and t.entry_price < self.vwap:
                return "vwap_target"

        # 7. Trailing stop
        trail_activation = self.box_range * (BOX_TRAIL_ACTIVATION_PCT / 100)
        if t.peak_price - t.entry_price >= trail_activation:
            trail_distance = self.box_range * (BOX_TRAIL_PCT / 100)
            trail_stop = t.peak_price - trail_distance
            if price <= trail_stop:
                return "trailing_stop"

        return None

    def _check_entry(self, bar, bar_time: time):
        """Check all entry criteria. Opens a trade if all pass."""
        # Time gate
        if bar_time >= LAST_ENTRY_TIME:
            return

        # Re-entry limit
        if self.entry_count >= BOX_MAX_ENTRIES_PER_STOCK:
            return

        # Session loss cap already hit
        if self.session_pnl <= -BOX_MAX_LOSS_SESSION:
            self.stopped_out = True
            return

        price = bar.close

        # 1. Price in buy zone
        if price > self.buy_zone_ceiling:
            return

        # 2. Box still valid (today's range hasn't broken the box)
        if self.today_hod > self.box_top * 1.005:
            return
        if self.today_lod < self.box_bottom * 0.995:
            return

        # 3. RSI oversold
        rsi = compute_rsi(self.closes, BOX_RSI_PERIOD)
        if rsi >= BOX_RSI_OVERSOLD:
            return

        # 4. Reversal confirmation: green bar after red bar
        if BOX_REVERSAL_CONFIRM:
            if self.prev_bar is None:
                return
            if not (bar.close > bar.open and self.prev_bar.close < self.prev_bar.open):
                return

        # 5. Volume confirmation
        if len(self.volumes) >= 20:
            avg_vol_20 = sum(self.volumes[-20:]) / 20
            if avg_vol_20 > 0 and bar.volume < avg_vol_20 * BOX_MIN_BAR_VOL_RATIO:
                return

        # All criteria met — enter
        self._open_trade(bar, price, rsi)

    def _open_trade(self, bar, price: float, rsi: float):
        """Open a new box trade."""
        # Position sizing
        risk_per_share = price - self.hard_stop_price
        shares = int(BOX_MAX_NOTIONAL / price)

        if risk_per_share > 0:
            risk_shares = int(BOX_MAX_RISK_PER_TRADE / risk_per_share)
            shares = min(shares, risk_shares)

        if shares <= 0:
            return

        self.active_trade = BoxTradeState(
            symbol=self.symbol,
            entry_price=price,
            entry_time=bar.date,
            shares=shares,
            box_top=self.box_top,
            box_bottom=self.box_bottom,
            box_range=self.box_range,
            hard_stop=self.hard_stop_price,
            peak_price=price,
            rsi_at_entry=rsi,
            bar_volume_at_entry=bar.volume,
        )
        self.entry_count += 1

    def _close_trade(self, exit_price: float, exit_time: datetime, reason: str):
        """Close the active trade and record results."""
        t = self.active_trade
        t.exit_price = exit_price
        t.exit_time = exit_time
        t.exit_reason = reason
        t.pnl = (exit_price - t.entry_price) * t.shares
        t.pnl_pct = ((exit_price - t.entry_price) / t.entry_price) * 100 if t.entry_price > 0 else 0
        t.hold_minutes = (exit_time - t.entry_time).total_seconds() / 60

        self.session_pnl += t.pnl
        self.trades.append(t)
        self.active_trade = None

        # Stops that prevent re-entry
        if reason in ("hard_stop", "box_invalidation_high", "box_invalidation_low", "session_loss_cap"):
            self.stopped_out = True

    @staticmethod
    def _get_bar_time(bar) -> time:
        """Extract time in ET from bar.date, handling UTC and aware datetimes."""
        dt = bar.date
        if not hasattr(dt, 'time') or not callable(dt.time):
            return time(0, 0)
        # If timezone-aware, convert to ET
        if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
            dt_et = dt.astimezone(ET)
            return dt_et.time()
        # If naive, assume it's already ET
        return dt.time()
