#!/usr/bin/env python3
"""
Analyze indicator state at 2R target exits.

This script reads tick cache files and builds 1-minute bars with:
- MACD / signal line / histogram
- Volume analysis
- VWAP
- Candle patterns

For the specified stocks and dates, it extracts the exact moment when
a 2R target was hit and shows what the indicators looked like.
"""

import json
import gzip
import os
import sys
from datetime import datetime, timedelta, time
from collections import defaultdict
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple


# ─────────────────────────────────────────────
# MACD Implementation (from macd.py)
# ─────────────────────────────────────────────

def ema_next(prev: Optional[float], price: float, length: int) -> float:
    alpha = 2.0 / (length + 1.0)
    return price if prev is None else (price * alpha) + (prev * (1.0 - alpha))


@dataclass
class MACDState:
    ema12: Optional[float] = None
    ema26: Optional[float] = None
    macd: Optional[float] = None
    signal: Optional[float] = None
    hist: Optional[float] = None

    prev_macd: Optional[float] = None
    prev_signal: Optional[float] = None
    prev_hist: Optional[float] = None

    def update(self, close: float) -> "MACDState":
        self.ema12 = ema_next(self.ema12, close, 12)
        self.ema26 = ema_next(self.ema26, close, 26)

        if self.ema12 is None or self.ema26 is None:
            return self

        self.prev_macd = self.macd
        self.prev_signal = self.signal
        self.prev_hist = self.hist

        self.macd = self.ema12 - self.ema26
        self.signal = ema_next(self.signal, self.macd, 9)

        if self.signal is not None:
            self.hist = self.macd - self.signal

        return self

    def bullish(self) -> bool:
        return (
            self.macd is not None
            and self.signal is not None
            and self.macd > self.signal
        )

    def bearish_cross(self) -> bool:
        if (
            self.prev_macd is None
            or self.prev_signal is None
            or self.macd is None
            or self.signal is None
        ):
            return False
        return self.prev_macd >= self.prev_signal and self.macd < self.signal


# ─────────────────────────────────────────────
# Candle Patterns
# ─────────────────────────────────────────────

def is_doji(o: float, h: float, l: float, c: float, pct: float = 0.3) -> bool:
    """Doji: open and close are very close."""
    body = abs(c - o)
    if o == 0:
        return False
    return body <= (h - l) * pct


def is_shooting_star(o: float, h: float, l: float, c: float) -> bool:
    """Shooting star: open at bottom, closes near bottom, long upper wick."""
    body = abs(c - o)
    lower = min(o, c)
    upper_wick = h - lower
    lower_wick = lower - l
    return upper_wick > 2 * body and lower_wick < body


def is_bearish_engulfing(o: float, h: float, l: float, c: float,
                         prev_o: float, prev_h: float, prev_l: float, prev_c: float) -> bool:
    """Bearish engulfing: prev bar bullish, current bar bearish and engulfs."""
    prev_body = prev_c - prev_o
    curr_body = o - c
    if prev_body <= 0 or curr_body <= 0:
        return False
    return o >= prev_c and c <= prev_o


# ─────────────────────────────────────────────
# 1-Minute Bar Builder
# ─────────────────────────────────────────────

@dataclass
class Bar1M:
    timestamp: int  # Unix timestamp (start of bar)
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float
    macd: Optional[MACDState] = None

    def time_str(self) -> str:
        dt = datetime.utcfromtimestamp(self.timestamp)
        return dt.strftime("%H:%M")

    def describe(self) -> str:
        lines = [
            f"  Time: {self.time_str()} UTC",
            f"  OHLC: {self.open:.4f} / {self.high:.4f} / {self.low:.4f} / {self.close:.4f}",
            f"  Volume: {self.volume:,}",
            f"  VWAP: {self.vwap:.4f}",
        ]
        if self.macd and self.macd.macd is not None:
            lines.append(f"  MACD: {self.macd.macd:.6f} (signal: {self.macd.signal:.6f}, hist: {self.macd.hist:.6f})")
            if self.macd.bullish():
                lines.append(f"    -> Bullish (MACD > signal)")
            else:
                lines.append(f"    -> Bearish (MACD < signal)")
            if self.macd.bearish_cross():
                lines.append(f"    -> BEARISH CROSS (downside momentum shift)")

        # Candle pattern
        patterns = []
        if is_doji(self.open, self.high, self.low, self.close):
            patterns.append("DOJI")
        if is_shooting_star(self.open, self.high, self.low, self.close):
            patterns.append("SHOOTING STAR")

        if patterns:
            lines.append(f"  Patterns: {', '.join(patterns)}")

        return "\n".join(lines)


def build_1m_bars(ticks: List[Dict]) -> List[Bar1M]:
    """Build 1-minute bars from tick data."""
    if not ticks:
        return []

    bars = []
    current_minute_ts = None
    bar_ticks = []
    macd_state = MACDState()
    vwap_pv = 0.0  # price * volume
    vwap_vol = 0

    for tick in ticks:
        # Parse ISO timestamp
        t_str = tick["t"]
        tick_dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
        t = int(tick_dt.timestamp())

        p = float(tick["p"])
        s = int(tick["s"])  # size

        # Determine minute bucket
        minute_start = tick_dt.replace(second=0, microsecond=0)
        minute_ts = int(minute_start.timestamp())

        if current_minute_ts is None:
            current_minute_ts = minute_ts

        if minute_ts != current_minute_ts:
            # Build bar for previous minute
            if bar_ticks:
                bar = _build_bar_from_ticks(bar_ticks, current_minute_ts, macd_state, vwap_pv, vwap_vol)
                bars.append(bar)
                macd_state.update(bar.close)

            # Start new minute
            current_minute_ts = minute_ts
            bar_ticks = []
            vwap_pv = 0.0
            vwap_vol = 0

        bar_ticks.append(tick)
        vwap_pv += p * s
        vwap_vol += s

    # Final bar
    if bar_ticks:
        bar = _build_bar_from_ticks(bar_ticks, current_minute_ts, macd_state, vwap_pv, vwap_vol)
        bars.append(bar)

    return bars


def _build_bar_from_ticks(ticks: List[Dict], minute_ts: int, macd_state: MACDState,
                          vwap_pv: float, vwap_vol: int) -> Bar1M:
    """Build a single 1M bar from tick list."""
    prices = [float(t["p"]) for t in ticks]
    sizes = [int(t["s"]) for t in ticks]

    o = prices[0]
    h = max(prices)
    l = min(prices)
    c = prices[-1]
    v = sum(sizes)

    vwap = vwap_pv / vwap_vol if vwap_vol > 0 else c

    # Update MACD
    macd_state.update(c)

    return Bar1M(
        timestamp=minute_ts,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
        vwap=vwap,
        macd=MACDState(ema12=macd_state.ema12, ema26=macd_state.ema26,
                       macd=macd_state.macd, signal=macd_state.signal, hist=macd_state.hist,
                       prev_macd=macd_state.prev_macd, prev_signal=macd_state.prev_signal,
                       prev_hist=macd_state.prev_hist),
    )


# ─────────────────────────────────────────────
# Tick Cache Reader
# ─────────────────────────────────────────────

def load_tick_cache(symbol: str, date_str: str, cache_dir: str = "tick_cache") -> Optional[List[Dict]]:
    """Load tick data from cache file (YYYY-MM-DD/SYMBOL.json.gz)."""
    cache_path = Path(cache_dir) / date_str / f"{symbol}.json.gz"

    if not cache_path.exists():
        print(f"  [SKIP] No tick cache: {cache_path}", file=sys.stderr)
        return None

    try:
        with gzip.open(cache_path, 'rt') as f:
            data = json.load(f)
        print(f"  [LOAD] {len(data)} ticks from {cache_path}")
        return data
    except Exception as e:
        print(f"  [ERROR] Failed to load {cache_path}: {e}", file=sys.stderr)
        return None


# ─────────────────────────────────────────────
# Target Hit Detector (simplified)
# ─────────────────────────────────────────────

def analyze_exits(symbol: str, date_str: str, bars: List[Bar1M]) -> None:
    """
    Analyze the bars to find potential 2R target hits.

    For now, we'll print all bars so you can identify the target hits manually.
    A full implementation would need:
    - Entry price/time
    - R value (stop loss distance)
    - 2R target level
    """
    print(f"\n{'='*80}")
    print(f"EXIT ANALYSIS: {symbol} on {date_str}")
    print(f"{'='*80}")

    if not bars:
        print("  No bars to analyze")
        return

    print(f"\nTotal bars: {len(bars)}")
    print("\nBar-by-bar indicator state:")
    print(f"{'Time':<8} {'O':<8} {'H':<8} {'L':<8} {'C':<8} {'Vol':<10} {'VWAP':<8} {'MACD':<12} {'Signal':<12}")
    print("-" * 100)

    for bar in bars:
        macd_str = f"{bar.macd.macd:.6f}" if bar.macd and bar.macd.macd else "---"
        signal_str = f"{bar.macd.signal:.6f}" if bar.macd and bar.macd.signal else "---"

        print(
            f"{bar.time_str():<8} "
            f"{bar.open:<8.4f} "
            f"{bar.high:<8.4f} "
            f"{bar.low:<8.4f} "
            f"{bar.close:<8.4f} "
            f"{bar.volume:<10,} "
            f"{bar.vwap:<8.4f} "
            f"{macd_str:<12} "
            f"{signal_str:<12}"
        )

    # Print detailed view of key bars
    print("\n" + "="*80)
    print("DETAILED BAR ANALYSIS")
    print("="*80)
    for i, bar in enumerate(bars):
        print(f"\nBar {i+1}/{len(bars)}:")
        print(bar.describe())


# ─────────────────────────────────────────────
# Volume Spike & Price Run Detection
# ─────────────────────────────────────────────

def find_key_moments(bars: List[Bar1M]) -> List[Tuple[int, str]]:
    """Find bars with notable volume spikes, breakouts, or runs."""
    moments = []
    avg_vol = sum(b.volume for b in bars) / len(bars) if bars else 0

    for i, bar in enumerate(bars):
        reasons = []

        # High volume bars (3x average)
        if bar.volume > avg_vol * 3:
            reasons.append(f"HIGH_VOL({bar.volume:,})")

        # Large intrabar moves (> 2% range)
        if bar.open > 0:
            pct_range = ((bar.high - bar.low) / bar.open) * 100
            if pct_range > 2.0:
                reasons.append(f"LARGE_MOVE({pct_range:.1f}%)")

        # Parabolic acceleration (close much higher than open)
        if bar.close > bar.open and bar.volume > avg_vol:
            pct_move = ((bar.close - bar.open) / bar.open) * 100
            if pct_move > 1.5:
                reasons.append(f"PARABOLIC({pct_move:.1f}%)")

        # MACD bullish cross
        if bar.macd and bar.macd.prev_macd is not None:
            if bar.macd.prev_macd <= bar.macd.prev_signal and bar.macd.macd > bar.macd.signal:
                reasons.append("MACD_BULLISH_CROSS")

        if reasons:
            moments.append((i, ", ".join(reasons)))

    return moments


def print_key_moments(symbol: str, bars: List[Bar1M]) -> None:
    """Print bars around key moments (likely trade entries/exits)."""
    moments = find_key_moments(bars)

    if not moments:
        print("  No key moments detected")
        return

    print(f"\nKey moments in {symbol}:")
    print(f"{'Time':<8} {'Event':<50}")
    print("-" * 60)

    for idx, reason in moments[:15]:  # Show first 15 key moments
        bar = bars[idx]
        print(f"{bar.time_str():<8} {reason:<50}")

    print("\n" + "="*80)
    print("DETAILED VIEW OF KEY MOMENTS (showing ±3 bars)")
    print("="*80)

    for idx, reason in moments[:5]:  # Deep dive into first 5
        start = max(0, idx - 3)
        end = min(len(bars), idx + 4)

        print(f"\n>>> Key Moment at {bars[idx].time_str()}: {reason}")
        print(f"    Close: ${bars[idx].close:.4f}, Volume: {bars[idx].volume:,}")
        print()

        for i in range(start, end):
            marker = ">>>" if i == idx else "   "
            b = bars[i]
            macd_str = f"M:{b.macd.macd:.6f}|S:{b.macd.signal:.6f}" if b.macd and b.macd.macd else "MACD:---"
            pattern_str = ""
            if is_doji(b.open, b.high, b.low, b.close):
                pattern_str += " [DOJI]"
            if is_shooting_star(b.open, b.high, b.low, b.close):
                pattern_str += " [STAR]"

            print(
                f"{marker} {b.time_str()} | O:{b.open:7.4f} H:{b.high:7.4f} L:{b.low:7.4f} C:{b.close:7.4f} | "
                f"V:{b.volume:8,} VWAP:{b.vwap:.4f} | {macd_str}{pattern_str}"
            )


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    test_cases = [
        ("ATON", "2025-03-28"),
        ("BOSC", "2025-05-29"),
    ]

    for symbol, date_str in test_cases:
        print(f"\n{'='*80}")
        print(f"Loading: {symbol} {date_str}")
        print(f"{'='*80}")

        ticks = load_tick_cache(symbol, date_str)
        if not ticks:
            continue

        bars = build_1m_bars(ticks)
        print_key_moments(symbol, bars)
        print("\n")
        print(f"\nFull bar-by-bar analysis available above. {len(bars)} total bars.")
        print(f"Price range: ${min(b.close for b in bars):.4f} - ${max(b.close for b in bars):.4f}")


if __name__ == "__main__":
    main()
