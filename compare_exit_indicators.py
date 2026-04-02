#!/usr/bin/env python3
"""
Compare indicator state at 2R exits: DONE stocks vs RUNNER stocks.

For each stock, finds the 1m bar closest to the known exit time and prints
MACD, volume, VWAP, candle patterns. Then compares "done" vs "runner" groups.
"""

import json, gzip, os, sys
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional, List, Dict

# ── MACD ──
def ema_next(prev, price, length):
    alpha = 2.0 / (length + 1.0)
    return price if prev is None else (price * alpha) + (prev * (1.0 - alpha))

class MACDState:
    def __init__(self):
        self.ema12 = self.ema26 = self.macd = self.signal = self.hist = None
        self.prev_macd = self.prev_signal = self.prev_hist = None
    def update(self, close):
        self.ema12 = ema_next(self.ema12, close, 12)
        self.ema26 = ema_next(self.ema26, close, 26)
        if self.ema12 is None or self.ema26 is None: return
        self.prev_macd, self.prev_signal, self.prev_hist = self.macd, self.signal, self.hist
        self.macd = self.ema12 - self.ema26
        self.signal = ema_next(self.signal, self.macd, 9)
        if self.signal is not None:
            self.hist = self.macd - self.signal
    def copy(self):
        m = MACDState()
        m.ema12, m.ema26, m.macd, m.signal, m.hist = self.ema12, self.ema26, self.macd, self.signal, self.hist
        m.prev_macd, m.prev_signal, m.prev_hist = self.prev_macd, self.prev_signal, self.prev_hist
        return m

# ── Bar builder ──
@dataclass
class Bar1M:
    time_str: str
    ts_utc: int
    o: float; h: float; l: float; c: float
    volume: int
    vwap_cum: float  # cumulative VWAP
    macd_val: Optional[float] = None
    macd_sig: Optional[float] = None
    macd_hist: Optional[float] = None
    bearish_cross: bool = False

def build_bars(ticks):
    bars = []
    macd = MACDState()
    cum_pv = 0.0; cum_vol = 0
    cur_min = None; cur_ticks = []

    for t in ticks:
        dt = datetime.fromisoformat(t["t"].replace("Z","+00:00"))
        p, s = float(t["p"]), int(t["s"])
        min_key = dt.strftime("%H:%M")
        min_ts = int(dt.replace(second=0, microsecond=0).timestamp())

        if cur_min is not None and min_key != cur_min:
            bar = _make_bar(cur_ticks, cur_min, cur_min_ts, macd, cum_pv, cum_vol)
            bars.append(bar)
            macd.update(bar.c)
            cur_ticks = []

        cur_min = min_key
        cur_min_ts = min_ts
        cur_ticks.append((p, s))
        cum_pv += p * s
        cum_vol += s

    if cur_ticks:
        bar = _make_bar(cur_ticks, cur_min, cur_min_ts, macd, cum_pv, cum_vol)
        bars.append(bar)
    return bars

def _make_bar(ticks, time_str, ts, macd, cum_pv, cum_vol):
    prices = [t[0] for t in ticks]
    sizes = [t[1] for t in ticks]
    o, h, l, c = prices[0], max(prices), min(prices), prices[-1]
    v = sum(sizes)
    vwap = cum_pv / cum_vol if cum_vol > 0 else c

    macd.update(c)
    bcross = (macd.prev_macd is not None and macd.prev_signal is not None and
              macd.macd is not None and macd.signal is not None and
              macd.prev_macd >= macd.prev_signal and macd.macd < macd.signal)

    return Bar1M(time_str=time_str, ts_utc=ts, o=o, h=h, l=l, c=c, volume=v,
                 vwap_cum=vwap,
                 macd_val=macd.macd, macd_sig=macd.signal, macd_hist=macd.hist,
                 bearish_cross=bcross)

def load_ticks(cache_dir, date_str, symbol):
    path = os.path.join(cache_dir, date_str, f"{symbol}.json.gz")
    if not os.path.exists(path):
        return None
    with gzip.open(path, 'rt') as f:
        return json.load(f)

def candle_patterns(bar):
    patterns = []
    rng = bar.h - bar.l
    if rng <= 0: return patterns
    body = abs(bar.c - bar.o)
    upper_wick = bar.h - max(bar.o, bar.c)
    lower_wick = min(bar.o, bar.c) - bar.l

    if body <= 0.12 * rng: patterns.append("doji")
    if upper_wick >= 2 * body and body > 0 and lower_wick < body:
        patterns.append("shooting_star")
    if bar.c < bar.o and rng > 0 and (bar.c - bar.l) <= 0.25 * rng:
        patterns.append("bearish_close_low")  # close in bottom 25%
    if rng / bar.o > 0.05 and bar.c < bar.o:
        patterns.append("wide_range_red")
    return patterns

def analyze_stock(cache_dir, date_str, symbol, exit_time_utc, entry_price, r_value,
                  category, post_r):
    """Analyze a single stock around its exit time."""
    ticks = load_ticks(cache_dir, date_str, symbol)
    if ticks is None:
        return None

    bars = build_bars(ticks)
    if not bars:
        return None

    # Find the exit bar (closest to exit_time_utc)
    exit_bar_idx = None
    target_price = entry_price + 2 * r_value  # 2R target

    # Find bar where price first reaches 2R target
    for i, bar in enumerate(bars):
        if bar.h >= target_price and exit_bar_idx is None:
            exit_bar_idx = i
            break

    # If we didn't find target hit by price, find by time
    if exit_bar_idx is None:
        for i, bar in enumerate(bars):
            if bar.time_str >= exit_time_utc:
                exit_bar_idx = i
                break

    if exit_bar_idx is None:
        return None

    # Get context: 5 bars before, exit bar, 5 bars after
    start = max(0, exit_bar_idx - 5)
    end = min(len(bars), exit_bar_idx + 6)
    context_bars = bars[start:end]
    exit_bar = bars[exit_bar_idx]

    # Volume analysis: avg of 5 bars before exit
    vol_before = [bars[i].volume for i in range(max(0, exit_bar_idx-5), exit_bar_idx)]
    avg_vol_before = sum(vol_before) / len(vol_before) if vol_before else 0
    vol_ratio = exit_bar.volume / avg_vol_before if avg_vol_before > 0 else 0

    # Peak volume in session up to exit
    peak_vol = max(b.volume for b in bars[:exit_bar_idx+1]) if exit_bar_idx > 0 else exit_bar.volume
    is_climax = exit_bar.volume >= peak_vol * 0.9

    # MACD histogram trend (last 3 bars before exit)
    hist_trend = []
    for i in range(max(0, exit_bar_idx-3), exit_bar_idx+1):
        if bars[i].macd_hist is not None:
            hist_trend.append(bars[i].macd_hist)
    hist_declining = len(hist_trend) >= 2 and all(hist_trend[i] <= hist_trend[i-1] for i in range(1, len(hist_trend)))

    # VWAP distance at exit
    vwap_dist_pct = ((exit_bar.c - exit_bar.vwap_cum) / exit_bar.vwap_cum * 100) if exit_bar.vwap_cum > 0 else 0

    # How far from HOD at exit
    session_high = max(b.h for b in bars[:exit_bar_idx+1])
    dist_from_hod = (session_high - exit_bar.c) / session_high * 100 if session_high > 0 else 0

    # Candle patterns at exit
    exit_patterns = candle_patterns(exit_bar)

    # Check prior bar for patterns too
    prior_patterns = []
    if exit_bar_idx > 0:
        prior_patterns = candle_patterns(bars[exit_bar_idx - 1])

    # Check for bearish engulfing
    if exit_bar_idx > 0:
        prev = bars[exit_bar_idx - 1]
        if (prev.c > prev.o and  # prev green
            exit_bar.c < exit_bar.o and  # current red
            exit_bar.o >= prev.c and exit_bar.c <= prev.o):
            exit_patterns.append("bearish_engulfing")

    # R multiple at exit
    r_at_exit = (exit_bar.c - entry_price) / r_value if r_value > 0 else 0

    # Bars since session open (proxy for "how extended")
    bars_into_session = exit_bar_idx

    # Volume trend: declining or expanding?
    if len(vol_before) >= 3:
        recent_3_vol = vol_before[-3:]
        vol_declining = all(recent_3_vol[i] <= recent_3_vol[i-1] for i in range(1, len(recent_3_vol)))
        vol_expanding = all(recent_3_vol[i] >= recent_3_vol[i-1] for i in range(1, len(recent_3_vol)))
    else:
        vol_declining = vol_expanding = False

    return {
        "symbol": symbol,
        "date": date_str,
        "category": category,
        "post_r": post_r,
        "exit_time": exit_bar.time_str,
        "exit_price": exit_bar.c,
        "entry_price": entry_price,
        "r_value": r_value,
        "r_at_exit": r_at_exit,
        "target_2r": target_price,
        # MACD
        "macd": exit_bar.macd_val,
        "macd_signal": exit_bar.macd_sig,
        "macd_hist": exit_bar.macd_hist,
        "macd_bullish": exit_bar.macd_val > exit_bar.macd_sig if exit_bar.macd_val and exit_bar.macd_sig else None,
        "macd_bearish_cross": exit_bar.bearish_cross,
        "hist_declining": hist_declining,
        "hist_trend": hist_trend,
        # Volume
        "exit_volume": exit_bar.volume,
        "avg_vol_5bar": avg_vol_before,
        "vol_ratio": vol_ratio,
        "is_climax_vol": is_climax,
        "vol_declining_3bar": vol_declining,
        "vol_expanding_3bar": vol_expanding,
        # VWAP
        "vwap": exit_bar.vwap_cum,
        "vwap_dist_pct": vwap_dist_pct,
        # Candle
        "exit_patterns": exit_patterns,
        "prior_patterns": prior_patterns,
        # Context
        "dist_from_hod_pct": dist_from_hod,
        "bars_into_session": bars_into_session,
        # Context bars for detailed view
        "context_bars": [(b.time_str, b.o, b.h, b.l, b.c, b.volume,
                          b.macd_hist, candle_patterns(b)) for b in context_bars],
        "exit_bar_offset": exit_bar_idx - start,
    }


def print_result(r):
    tag = "DONE" if r["category"] in ("GOOD_EXIT","PERFECT_EXIT","MODEST") else "RUNNER"
    print(f"\n{'='*70}")
    print(f"  {r['symbol']} ({r['date']})  [{tag}]  post-exit: +{r['post_r']:.1f}R")
    print(f"{'='*70}")
    print(f"  Entry: ${r['entry_price']:.2f}  |  R: ${r['r_value']:.3f}  |  2R target: ${r['target_2r']:.2f}")
    print(f"  Exit bar: {r['exit_time']} UTC  |  Exit price: ${r['exit_price']:.2f}  |  R at exit: {r['r_at_exit']:.1f}R")
    print()
    print(f"  MACD:     {r['macd']:.4f}" if r['macd'] else "  MACD:     N/A")
    print(f"  Signal:   {r['macd_signal']:.4f}" if r['macd_signal'] else "  Signal:   N/A")
    print(f"  Hist:     {r['macd_hist']:.4f}" if r['macd_hist'] else "  Hist:     N/A")
    print(f"  Bullish:  {r['macd_bullish']}")
    print(f"  B.Cross:  {r['macd_bearish_cross']}")
    print(f"  Hist declining (3-bar): {r['hist_declining']}")
    print(f"  Hist trend: {['%.4f'%h for h in r['hist_trend']]}")
    print()
    print(f"  Volume:   {r['exit_volume']:,}")
    print(f"  Avg 5bar: {r['avg_vol_5bar']:,.0f}")
    print(f"  Vol ratio: {r['vol_ratio']:.1f}x")
    print(f"  Climax vol: {r['is_climax_vol']}")
    print(f"  Vol declining (3-bar): {r['vol_declining_3bar']}")
    print(f"  Vol expanding (3-bar): {r['vol_expanding_3bar']}")
    print()
    print(f"  VWAP:     ${r['vwap']:.2f}")
    print(f"  VWAP dist: {r['vwap_dist_pct']:+.1f}%")
    print(f"  Dist from HOD: {r['dist_from_hod_pct']:.1f}%")
    print()
    print(f"  Exit candle: {r['exit_patterns'] or 'none'}")
    print(f"  Prior candle: {r['prior_patterns'] or 'none'}")
    print(f"  Bars into session: {r['bars_into_session']}")
    print()
    print(f"  Context (5 bars before → exit → 5 after):")
    for i, (t, o, h, l, c, v, hist, pats) in enumerate(r['context_bars']):
        marker = " <<<EXIT" if i == r['exit_bar_offset'] else ""
        pat_str = f" [{','.join(pats)}]" if pats else ""
        hist_str = f"h:{hist:+.4f}" if hist is not None else "h:N/A"
        print(f"    {t}  O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f}  V:{v:>8,}  {hist_str}{pat_str}{marker}")


if __name__ == "__main__":
    cache_dir = "tick_cache"

    # ── DONE stocks (correct exits) ──
    done_stocks = [
        # (date, symbol, exit_time_utc, entry_price, r_value, category, post_r)
        ("2025-03-28", "ATON", "11:07", 12.04, 0.47, "MODEST", 1.1),
        ("2025-05-29", "BOSC", "12:52", 6.04, 0.14, "MODEST", 0.6),
        # GV, SNES, DRMA - no tick cache
    ]

    # ── RUNNER stocks (should have kept holding) ──
    runner_stocks = [
        ("2026-01-14", "ROLR", "12:19", 4.04, 0.14, "RUNNER", 121.4),
        ("2025-06-26", "CYN",  "11:06", 6.04, 0.14, "RUNNER", 242.0),
        ("2025-06-16", "STAK", "11:10", 3.04, 0.14, "RUNNER", 37.1),
        ("2025-01-24", "ALUR", "11:04", 8.04, 0.14, "RUNNER", 84.7),
        ("2025-02-04", "QNTM", "11:05", 5.04, 0.14, "RUNNER", 10.4),
        ("2026-03-18", "ARTL", "11:42", 5.04, 0.14, "RUNNER", 9.8),
        ("2025-07-17", "BSLK", "11:04", 3.04, 0.14, "RUNNER", 8.6),
        ("2025-06-02", "INM",  "11:01", 4.04, 0.14, "RUNNER", 32.3),
    ]

    print("=" * 70)
    print("  DONE vs RUNNER: Indicator State at 2R Target Hit")
    print("=" * 70)

    done_results = []
    runner_results = []

    print("\n\n### DONE STOCKS (exit was correct) ###")
    for date, sym, exit_t, entry, r, cat, post_r in done_stocks:
        result = analyze_stock(cache_dir, date, sym, exit_t, entry, r, cat, post_r)
        if result:
            done_results.append(result)
            print_result(result)
        else:
            print(f"\n  {sym} ({date}): NO DATA")

    print("\n\n### RUNNER STOCKS (exit was wrong — stock kept going) ###")
    for date, sym, exit_t, entry, r, cat, post_r in runner_stocks:
        result = analyze_stock(cache_dir, date, sym, exit_t, entry, r, cat, post_r)
        if result:
            runner_results.append(result)
            print_result(result)
        else:
            print(f"\n  {sym} ({date}): NO DATA")

    # ── Summary comparison ──
    print("\n\n" + "=" * 70)
    print("  SUMMARY COMPARISON")
    print("=" * 70)

    def avg(vals):
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    def pct_true(vals):
        vals = [v for v in vals if v is not None]
        return sum(1 for v in vals if v) / len(vals) * 100 if vals else 0

    print(f"\n{'Metric':<30} {'DONE (n={len(done_results)})':<25} {'RUNNER (n={len(runner_results)})':<25}")
    print("-" * 80)

    metrics = [
        ("MACD (avg)",
         avg([r["macd"] for r in done_results]),
         avg([r["macd"] for r in runner_results])),
        ("MACD Hist (avg)",
         avg([r["macd_hist"] for r in done_results]),
         avg([r["macd_hist"] for r in runner_results])),
        ("Hist declining %",
         pct_true([r["hist_declining"] for r in done_results]),
         pct_true([r["hist_declining"] for r in runner_results])),
        ("MACD Bullish %",
         pct_true([r["macd_bullish"] for r in done_results]),
         pct_true([r["macd_bullish"] for r in runner_results])),
        ("Bearish Cross %",
         pct_true([r["macd_bearish_cross"] for r in done_results]),
         pct_true([r["macd_bearish_cross"] for r in runner_results])),
        ("Vol ratio (avg)",
         avg([r["vol_ratio"] for r in done_results]),
         avg([r["vol_ratio"] for r in runner_results])),
        ("Climax vol %",
         pct_true([r["is_climax_vol"] for r in done_results]),
         pct_true([r["is_climax_vol"] for r in runner_results])),
        ("Vol declining 3bar %",
         pct_true([r["vol_declining_3bar"] for r in done_results]),
         pct_true([r["vol_declining_3bar"] for r in runner_results])),
        ("Vol expanding 3bar %",
         pct_true([r["vol_expanding_3bar"] for r in done_results]),
         pct_true([r["vol_expanding_3bar"] for r in runner_results])),
        ("VWAP dist % (avg)",
         avg([r["vwap_dist_pct"] for r in done_results]),
         avg([r["vwap_dist_pct"] for r in runner_results])),
        ("Dist from HOD % (avg)",
         avg([r["dist_from_hod_pct"] for r in done_results]),
         avg([r["dist_from_hod_pct"] for r in runner_results])),
        ("Bars into session (avg)",
         avg([r["bars_into_session"] for r in done_results]),
         avg([r["bars_into_session"] for r in runner_results])),
    ]

    for name, done_val, runner_val in metrics:
        d = f"{done_val:.4f}" if isinstance(done_val, float) else str(done_val)
        r = f"{runner_val:.4f}" if isinstance(runner_val, float) else str(runner_val)
        print(f"{name:<30} {d:<25} {r:<25}")

    # Pattern frequency
    print(f"\n{'Exit candle patterns:':<30}")
    from collections import Counter
    done_pats = Counter()
    runner_pats = Counter()
    for r in done_results:
        for p in r["exit_patterns"]: done_pats[p] += 1
        if not r["exit_patterns"]: done_pats["none"] += 1
    for r in runner_results:
        for p in r["exit_patterns"]: runner_pats[p] += 1
        if not r["exit_patterns"]: runner_pats["none"] += 1

    all_pats = set(list(done_pats.keys()) + list(runner_pats.keys()))
    for p in sorted(all_pats):
        d = done_pats.get(p, 0)
        r = runner_pats.get(p, 0)
        d_pct = d / len(done_results) * 100 if done_results else 0
        r_pct = r / len(runner_results) * 100 if runner_results else 0
        print(f"  {p:<26} {d} ({d_pct:.0f}%){'':<15} {r} ({r_pct:.0f}%)")

    print("\n\nDone.")
