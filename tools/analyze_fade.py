#!/usr/bin/env python3
"""Tick-level fade analyzer for the Short Strategy Research directive.

Produces a structured markdown fade profile per stock/date combination.
Reads from tick_cache/<date>/<symbol>.json.gz (IBKR-sourced) and
study_data/<symbol>_<date>.json for squeeze trade context.

Usage:
    python tools/analyze_fade.py ROLR 2026-01-14
    python tools/analyze_fade.py --all  # iterate the 10-target list

Output: cowork_reports/short_analysis/<SYMBOL>_<DATE>_fade.md
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The 10 Phase-1 targets from DIRECTIVE_SHORT_STRATEGY_RESEARCH.md.
TARGETS = [
    ("ROLR", "2026-01-14"), ("ACCL", "2026-01-16"), ("HIND", "2026-01-27"),
    ("GWAV", "2026-01-16"), ("ANPA", "2026-01-09"), ("BNAI", "2026-01-28"),
    ("PAVM", "2026-01-21"), ("VERO", "2026-01-16"), ("SNSE", "2026-02-18"),
    ("MLEC", "2026-02-13"),
]


@dataclass
class Tick:
    ts: datetime  # ET-localized
    price: float
    size: int


@dataclass
class Bar:
    start: datetime  # ET-localized, minute-truncated
    open: float
    high: float
    low: float
    close: float
    volume: int


def load_ticks(symbol: str, date: str) -> list[Tick]:
    path = os.path.join(ROOT, "tick_cache", date, f"{symbol}.json.gz")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Tick cache missing: {path}")
    with gzip.open(path, "rt") as f:
        raw = json.load(f)
    ticks: list[Tick] = []
    for t in raw:
        try:
            ts = datetime.fromisoformat(t["t"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ts_et = ts.astimezone(ET)
            ticks.append(Tick(ts_et, float(t["p"]), int(t["s"])))
        except (KeyError, ValueError, TypeError):
            continue
    ticks.sort(key=lambda x: x.ts)
    return ticks


def load_study(symbol: str, date: str) -> Optional[dict]:
    path = os.path.join(ROOT, "study_data", f"{symbol}_{date}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def build_bars(ticks: list[Tick], interval_sec: int = 60) -> list[Bar]:
    if not ticks:
        return []
    bars: list[Bar] = []
    bucket_start = ticks[0].ts.replace(second=0, microsecond=0)
    cur = Bar(bucket_start, ticks[0].price, ticks[0].price, ticks[0].price, ticks[0].price, 0)
    for t in ticks:
        # New bucket?
        bucket = t.ts.replace(second=0, microsecond=0)
        if bucket != cur.start:
            bars.append(cur)
            cur = Bar(bucket, t.price, t.price, t.price, t.price, 0)
        cur.high = max(cur.high, t.price)
        cur.low = min(cur.low, t.price)
        cur.close = t.price
        cur.volume += t.size
    bars.append(cur)
    return bars


def compute_vwap(ticks: list[Tick]) -> list[tuple[datetime, float]]:
    """Running VWAP: list of (ts, vwap) at every minute boundary."""
    cum_pv = 0.0
    cum_v = 0
    samples: list[tuple[datetime, float]] = []
    last_minute = None
    for t in ticks:
        cum_pv += t.price * t.size
        cum_v += t.size
        cur_min = t.ts.replace(second=0, microsecond=0)
        if cur_min != last_minute:
            vwap = cum_pv / cum_v if cum_v > 0 else 0.0
            samples.append((cur_min, vwap))
            last_minute = cur_min
    return samples


def vwap_at(samples: list[tuple[datetime, float]], ts: datetime) -> float:
    best = 0.0
    for s_ts, s_v in samples:
        if s_ts <= ts:
            best = s_v
        else:
            break
    return best


def find_hod(ticks: list[Tick]) -> Tick:
    return max(ticks, key=lambda t: t.price)


def pm_high(bars: list[Bar]) -> tuple[Optional[float], Optional[datetime]]:
    """Premarket high: highest bar high between 04:00 ET and 09:30 ET."""
    pm_bars = [b for b in bars if b.start.time() < datetime.strptime("09:30", "%H:%M").time()
               and b.start.time() >= datetime.strptime("04:00", "%H:%M").time()]
    if not pm_bars:
        return None, None
    peak = max(pm_bars, key=lambda b: b.high)
    return peak.high, peak.start


def session_low_after(ticks: list[Tick], start: datetime) -> float:
    after = [t for t in ticks if t.ts >= start]
    if not after:
        return 0.0
    return min(t.price for t in after)


def first_lower_high(bars: list[Bar], peak_idx: int) -> Optional[Bar]:
    """First bar after the peak that makes a *lower* high than the HOD bar."""
    if peak_idx >= len(bars) - 1:
        return None
    peak_high = bars[peak_idx].high
    # Walk forward; first bar whose high < peak_high AND represents a local-max
    for i in range(peak_idx + 1, min(peak_idx + 60, len(bars))):
        if bars[i].high < peak_high:
            # Confirm this is a peak (higher than neighbors at least left)
            if i > peak_idx + 2 and bars[i].high > bars[i - 1].high:
                return bars[i]
    return None


def deepest_pullback_before_first_bounce(bars: list[Bar], peak_idx: int) -> tuple[float, Bar, Bar]:
    """Deepest drop from HOD to a bar-low before a bar that makes a higher high than the prior bar.
    Returns (pct_drop, hod_bar, trough_bar)."""
    hod_bar = bars[peak_idx]
    trough = hod_bar
    for i in range(peak_idx + 1, min(peak_idx + 120, len(bars))):
        if bars[i].low < trough.low:
            trough = bars[i]
        # First bounce: a bar whose high > previous bar's high
        if i > peak_idx + 1 and bars[i].high > bars[i - 1].high and bars[i].low > trough.low:
            break
    pct = (hod_bar.high - trough.low) / hod_bar.high * 100 if hod_bar.high > 0 else 0.0
    return pct, hod_bar, trough


def avg_candle_size(bars: list[Bar], peak_idx: int, window: int = 30) -> tuple[float, float]:
    """Average abs body of red vs green bars in `window` bars after peak."""
    slice_ = bars[peak_idx + 1:peak_idx + 1 + window]
    reds = [abs(b.close - b.open) for b in slice_ if b.close < b.open]
    greens = [abs(b.close - b.open) for b in slice_ if b.close >= b.open]
    return (statistics.mean(reds) if reds else 0.0,
            statistics.mean(greens) if greens else 0.0)


def reclaimed_hod(ticks: list[Tick], hod: Tick, fade_threshold_pct: float = 2.0) -> tuple[bool, Optional[datetime]]:
    """True only if price drops at least fade_threshold_pct% below HOD, then
    later reaches or exceeds HOD. Avoids false positives from ticks at the
    exact HOD price in the immediate aftermath of the high."""
    threshold = hod.price * (1 - fade_threshold_pct / 100)
    faded = False
    for t in ticks:
        if t.ts <= hod.ts:
            continue
        if not faded and t.price <= threshold:
            faded = True
        if faded and t.price >= hod.price:
            return True, t.ts
    return False, None


def volume_during_fade(bars: list[Bar], peak_idx: int, window: int = 30) -> tuple[int, int, float]:
    """Peak volume (1m) vs avg volume in window bars after peak."""
    peak_vol = bars[peak_idx].volume
    fade_slice = bars[peak_idx + 1:peak_idx + 1 + window]
    avg_fade_vol = statistics.mean([b.volume for b in fade_slice]) if fade_slice else 0
    return peak_vol, int(avg_fade_vol), (avg_fade_vol / peak_vol if peak_vol > 0 else 0)


def topping_signals(bars: list[Bar], peak_idx: int) -> list[str]:
    """Heuristic detection of topping signals at/around the peak.
    Returns list of human-readable signal descriptions.
    """
    signals: list[str] = []
    if peak_idx < 2:
        return signals

    peak = bars[peak_idx]
    prior = bars[peak_idx - 1]

    # Shooting star on the peak bar: long upper wick, small body, close near low
    body = abs(peak.close - peak.open)
    upper_wick = peak.high - max(peak.close, peak.open)
    lower_wick = min(peak.close, peak.open) - peak.low
    if body > 0 and upper_wick > 2 * body and lower_wick < body:
        signals.append(f"Shooting star at {peak.start.strftime('%H:%M')} ET "
                       f"(body=${body:.3f} wick_up=${upper_wick:.3f})")
    elif body < (peak.high - peak.low) * 0.2 and (peak.high - peak.low) > 0:
        signals.append(f"Doji at {peak.start.strftime('%H:%M')} ET "
                       f"(body=${body:.3f} range=${peak.high - peak.low:.3f})")

    # Bearish engulfing in the 3 bars after peak
    for i in range(peak_idx + 1, min(peak_idx + 4, len(bars))):
        b = bars[i]
        p = bars[i - 1]
        if (p.close > p.open and b.close < b.open and
                b.open >= p.close and b.close <= p.open):
            signals.append(f"Bearish engulfing at {b.start.strftime('%H:%M')} ET "
                           f"(prev close=${p.close:.3f} → this close=${b.close:.3f})")
            break

    # Lower-high confirmation within 10 bars
    lh = first_lower_high(bars, peak_idx)
    if lh:
        minutes_after = int((lh.start - peak.start).total_seconds() / 60)
        signals.append(f"First lower high at {lh.start.strftime('%H:%M')} ET "
                       f"(${lh.high:.2f}, {minutes_after}m after HOD)")

    # VWAP cross-below — detected in fade_to_vwap
    return signals


def volume_trend_pre_peak(bars: list[Bar], peak_idx: int, window: int = 5) -> str:
    """Was volume increasing or decreasing into the peak?"""
    start = max(0, peak_idx - window)
    pre = [b.volume for b in bars[start:peak_idx + 1]]
    if len(pre) < 2:
        return "insufficient data"
    # Simple trend: compare first half vs second half mean
    half = len(pre) // 2
    early = statistics.mean(pre[:half]) if pre[:half] else 0
    late = statistics.mean(pre[half:]) if pre[half:] else 0
    if late > early * 1.2:
        return f"increasing ({int(early):,} → {int(late):,})"
    elif late < early * 0.8:
        return f"decreasing ({int(early):,} → {int(late):,})"
    else:
        return f"flat ({int(early):,} → {int(late):,})"


def generate_report(symbol: str, date: str) -> str:
    ticks = load_ticks(symbol, date)
    if not ticks:
        return f"# FADE ANALYSIS: {symbol} {date}\n\nNO TICK DATA.\n"

    study = load_study(symbol, date)
    bars = build_bars(ticks)
    vwap_series = compute_vwap(ticks)

    hod = find_hod(ticks)
    peak_bar_idx = next((i for i, b in enumerate(bars)
                         if b.start <= hod.ts < b.start + timedelta(minutes=1)), 0)

    # Peak details
    vwap_at_peak = vwap_at(vwap_series, hod.ts)
    pm_h, pm_h_ts = pm_high(bars)

    # Last squeeze exit from study data
    last_exit_price = None
    last_exit_time = None
    if study and study.get("trades"):
        # Squeeze trades usually have exit_reason starting with sq_
        squeeze_trades = [t for t in study["trades"] if t.get("exit_reason", "").startswith(("sq_", "ross_cuc"))]
        if not squeeze_trades:
            squeeze_trades = study["trades"]
        last_trade = squeeze_trades[-1]
        last_exit_price = last_trade.get("exit_price")
        last_exit_time = last_trade.get("exit_time")

    # Topping signals
    signals = topping_signals(bars, peak_bar_idx)
    vol_trend = volume_trend_pre_peak(bars, peak_bar_idx)

    # Fade structure
    lh = first_lower_high(bars, peak_bar_idx)
    pullback_pct, _, trough = deepest_pullback_before_first_bounce(bars, peak_bar_idx)
    red_avg, green_avg = avg_candle_size(bars, peak_bar_idx)
    did_reclaim, reclaim_ts = reclaimed_hod(ticks, hod)

    # Price 30m after peak
    target_ts = hod.ts + timedelta(minutes=30)
    close_30m_after = next((t.price for t in ticks if t.ts >= target_ts), ticks[-1].price)
    fade_pct = (hod.price - close_30m_after) / hod.price * 100
    fade_dollars = hod.price - close_30m_after

    # Volume profile
    peak_vol, avg_fade_vol, vol_ratio = volume_during_fade(bars, peak_bar_idx)

    # Key levels
    retrace_50 = (hod.price + (hod.price - min(t.price for t in ticks if t.ts <= hod.ts))) / 2
    # Approx "session low so far" = before peak
    pre_peak_low = min(t.price for t in ticks if t.ts <= hod.ts)
    morning_range = hod.price - pre_peak_low
    retrace_50 = hod.price - morning_range * 0.5

    # Did VWAP hold or break during fade?
    post_peak_ticks = [t for t in ticks if t.ts > hod.ts]
    vwap_breakthrough = None
    for t in post_peak_ticks:
        vw_here = vwap_at(vwap_series, t.ts)
        if vw_here > 0 and t.price < vw_here:
            vwap_breakthrough = t
            break
    vwap_status = "broke through" if vwap_breakthrough else "held"
    vwap_time_str = vwap_breakthrough.ts.strftime("%H:%M:%S") if vwap_breakthrough else "n/a"

    # First short entry heuristic: first bearish engulfing or first lower-high break
    short_entry = None
    short_entry_reason = None
    for i in range(peak_bar_idx + 1, min(peak_bar_idx + 15, len(bars))):
        b = bars[i]
        p = bars[i - 1]
        if (p.close > p.open and b.close < b.open and b.open >= p.close and b.close <= p.open):
            short_entry = b.close
            short_entry_reason = f"bearish engulfing at {b.start.strftime('%H:%M')}"
            break
    if not short_entry and lh:
        short_entry = lh.low
        short_entry_reason = f"break below first LH low at {lh.start.strftime('%H:%M')}"

    # RTH vs pre-RTH
    peak_time_et = hod.ts.strftime("%H:%M:%S")
    rth_status = "pre-RTH" if hod.ts.time() < datetime.strptime("09:30", "%H:%M").time() else "RTH"

    # Last squeeze exit → peak distance
    exit_to_peak_min = None
    if last_exit_time:
        try:
            exit_hm = datetime.strptime(last_exit_time, "%H:%M").time()
            exit_dt = hod.ts.replace(hour=exit_hm.hour, minute=exit_hm.minute, second=0)
            exit_to_peak_min = int((hod.ts - exit_dt).total_seconds() / 60)
        except ValueError:
            pass

    # ──────────────────────── Write report ────────────────────────
    lines = []
    lines.append(f"# FADE ANALYSIS: {symbol} {date}")
    lines.append("")
    lines.append(f"_Generated by tools/analyze_fade.py. Source: tick_cache/{date}/{symbol}.json.gz "
                 f"({len(ticks):,} ticks), study_data/{symbol}_{date}.json._")
    lines.append("")
    lines.append("## Peak Details")
    lines.append(f"- HOD: ${hod.price:.2f} at {peak_time_et} ET ({rth_status})")
    lines.append(f"- Last squeeze exit: ${last_exit_price:.2f} at {last_exit_time} ET" if last_exit_price
                 else "- Last squeeze exit: (no squeeze trades in study_data)")
    lines.append(f"- Time from last exit to HOD: {exit_to_peak_min}m" if exit_to_peak_min is not None
                 else "- Time from last exit to HOD: n/a")
    lines.append(f"- VWAP at peak: ${vwap_at_peak:.2f}")
    lines.append(f"- PM high: ${pm_h:.2f} at {pm_h_ts.strftime('%H:%M') if pm_h_ts else 'n/a'} ET" if pm_h
                 else "- PM high: (none)")
    lines.append("")
    lines.append("## Topping Signals")
    lines.append(f"- Volume trend into peak (5m): {vol_trend}")
    for s in signals:
        lines.append(f"- {s}")
    if not signals:
        lines.append("- (no clean topping-pattern signals detected within 3 bars of peak)")
    lines.append(f"- Earliest reliable short entry: ${short_entry:.2f} ({short_entry_reason})"
                 if short_entry else "- Earliest reliable short entry: no signal detected in 15 bars")
    lines.append("")
    lines.append("## Fade Profile")
    lines.append(f"- First lower high: ${lh.high:.2f} at {lh.start.strftime('%H:%M')} ET "
                 f"({int((lh.start - hod.ts).total_seconds() / 60)}m after HOD)"
                 if lh else "- First lower high: (not detected in 60 bars)")
    lines.append(f"- Deepest pullback before first bounce: -{pullback_pct:.1f}% "
                 f"(${hod.price:.2f} → ${trough.low:.2f} at {trough.start.strftime('%H:%M')})")
    lines.append(f"- Avg candle size (red vs green) in 30 bars post-peak: "
                 f"red ${red_avg:.3f} / green ${green_avg:.3f} "
                 f"(ratio {red_avg / green_avg:.1f}x)" if green_avg > 0
                 else f"- Avg candle size: red ${red_avg:.3f}, no green bars")
    lines.append(f"- 30m-after-peak price: ${close_30m_after:.2f} (fade of -{fade_pct:.1f}% = -${fade_dollars:.2f})")
    lines.append(f"- Reclaimed HOD after starting to fade: "
                 f"{'Yes at ' + reclaim_ts.strftime('%H:%M:%S') if did_reclaim else 'No'}")
    lines.append("")
    lines.append("## Key Levels")
    lines.append(f"- VWAP: ${vwap_at_peak:.2f} (at peak) — {vwap_status} during fade"
                 + (f" (first cross below at {vwap_time_str})" if vwap_breakthrough else ""))
    lines.append(f"- PM high: ${pm_h:.2f}" if pm_h else "- PM high: n/a")
    lines.append(f"- 50% retrace of morning move: ${retrace_50:.2f} "
                 f"({'reached' if trough.low <= retrace_50 else 'not reached'}; "
                 f"trough was ${trough.low:.2f})")
    lines.append("")
    lines.append("## Volume Profile")
    lines.append(f"- Peak 1m bar volume: {peak_vol:,}")
    lines.append(f"- Avg volume per 1m bar during 30-bar fade: {avg_fade_vol:,}")
    lines.append(f"- Fade/peak volume ratio: {vol_ratio:.2f}x")
    lines.append("")
    lines.append("## Hypothetical Short Trade")
    if short_entry:
        stop = hod.price * 1.03
        target1 = vwap_at_peak
        target2 = retrace_50
        risk = stop - short_entry
        reward1 = short_entry - target1
        rr1 = reward1 / risk if risk > 0 else 0
        lines.append(f"- Entry: ${short_entry:.2f} ({short_entry_reason})")
        lines.append(f"- Stop: ${stop:.2f} (HOD + 3%)")
        lines.append(f"- Target 1 (VWAP): ${target1:.2f}")
        lines.append(f"- Target 2 (50% retrace): ${target2:.2f}")
        lines.append(f"- Risk: ${risk:.2f}/sh | Reward to T1: ${reward1:.2f} | R/R: {rr1:.1f}")
    else:
        lines.append("- No clean short entry signal detected in 15 bars post-peak.")
    lines.append("")
    return "\n".join(lines)


def write_report(symbol: str, date: str):
    out_dir = os.path.join(ROOT, "cowork_reports", "short_analysis")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{symbol}_{date}_fade.md")
    try:
        report = generate_report(symbol, date)
    except FileNotFoundError as e:
        report = f"# FADE ANALYSIS: {symbol} {date}\n\nSKIPPED — {e}\n"
    with open(out_path, "w") as f:
        f.write(report)
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", nargs="?")
    parser.add_argument("date", nargs="?")
    parser.add_argument("--all", action="store_true", help="Run all 10 targets")
    args = parser.parse_args()

    if args.all:
        for sym, d in TARGETS:
            try:
                path = write_report(sym, d)
                print(f"✓ {sym} {d} → {path}")
            except Exception as e:
                print(f"✗ {sym} {d}: {e}")
    elif args.symbol and args.date:
        path = write_report(args.symbol, args.date)
        print(f"✓ {args.symbol} {args.date} → {path}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
