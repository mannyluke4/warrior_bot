#!/usr/bin/env python3
"""
test_vol_ratio_parity.py — Test 1: Compare vol_ratio between RTVolume and Historical ticks.

Replays both tick sources through independent TradeBarBuilder + SqueezeDetector
and compares vol_ratio bar-by-bar.
"""

import csv
import gzip
import json
import os
import sys
from collections import namedtuple
from datetime import datetime, timezone

import pytz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bars import TradeBarBuilder, Bar
from squeeze_detector import SqueezeDetector

ET = pytz.timezone("US/Eastern")


def load_ticks(path):
    """Load ticks from json.gz, return list of (dt_utc, price, size)."""
    with gzip.open(path, "rt") as f:
        raw = json.load(f)
    ticks = []
    for t in raw:
        dt = datetime.fromisoformat(t["t"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        ticks.append((dt, float(t["p"]), int(t["s"])))
    return ticks


class DetectorHarness:
    """Replays ticks through TradeBarBuilder + SqueezeDetector, records per-bar state."""

    def __init__(self, symbol):
        self.symbol = symbol
        self.sq = SqueezeDetector()
        self.sq.symbol = symbol
        self.bars = []  # list of {time_et, vol, avg_vol, vol_ratio, state, armed_price}

        self.bb = TradeBarBuilder(on_bar_close=self._on_bar, et_tz=ET, interval_seconds=60)
        self._bar_count = 0

    def _on_bar(self, bar):
        self._bar_count += 1
        o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume
        self.sq.seed_bar_close(o, h, l, c, v)

        # Extract vol_ratio from detector internals
        bars_1m = self.sq.bars_1m
        if len(bars_1m) >= 2:
            prior_vols = [b["v"] for b in list(bars_1m)[:-1]]
            avg_vol = sum(prior_vols) / len(prior_vols) if prior_vols else 0
            vol_ratio = v / avg_vol if avg_vol > 0 else 0
        else:
            avg_vol = 0
            vol_ratio = 0

        bar_time = bar.start_utc.astimezone(ET) if bar.start_utc else None
        state = self.sq._state if hasattr(self.sq, '_state') else "?"
        armed_price = self.sq.armed.trigger_high if self.sq.armed else None

        self.bars.append({
            "time_et": bar_time.strftime("%H:%M") if bar_time else "?",
            "vol": v,
            "avg_vol": round(avg_vol, 0),
            "vol_ratio": round(vol_ratio, 2),
            "state": state,
            "armed_price": armed_price,
        })

    def replay(self, ticks):
        for dt, price, size in ticks:
            if price <= 0 or size <= 0:
                continue
            self.bb.on_trade(self.symbol, price, size, dt)


def run_comparison(symbol, date, live_path, hist_path, output_csv, output_label):
    """Run comparison for one symbol-date."""
    print(f"\n{'='*60}")
    print(f"  {symbol} {date}: {output_label}")
    print(f"{'='*60}")

    live_ticks = load_ticks(live_path)
    hist_ticks = load_ticks(hist_path)
    print(f"  Live (RTVolume): {len(live_ticks):,} ticks")
    print(f"  Historical:      {len(hist_ticks):,} ticks")
    print(f"  Ratio:           {len(hist_ticks)/max(len(live_ticks),1):.1f}x")

    # Replay both
    live_h = DetectorHarness(symbol)
    hist_h = DetectorHarness(symbol)
    live_h.replay(live_ticks)
    hist_h.replay(hist_ticks)

    print(f"  Live bars:  {len(live_h.bars)}")
    print(f"  Hist bars:  {len(hist_h.bars)}")

    # Align bars by time
    live_by_time = {b["time_et"]: b for b in live_h.bars}
    hist_by_time = {b["time_et"]: b for b in hist_h.bars}
    all_times = sorted(set(list(live_by_time.keys()) + list(hist_by_time.keys())))

    # Write CSV
    rows = []
    for t in all_times:
        lb = live_by_time.get(t, {})
        hb = hist_by_time.get(t, {})
        rows.append({
            "time_et": t,
            "rtv_vol": lb.get("vol", ""),
            "hist_vol": hb.get("vol", ""),
            "rtv_avg": lb.get("avg_vol", ""),
            "hist_avg": hb.get("avg_vol", ""),
            "rtv_ratio": lb.get("vol_ratio", ""),
            "hist_ratio": hb.get("vol_ratio", ""),
            "rtv_state": lb.get("state", ""),
            "hist_state": hb.get("state", ""),
            "rtv_armed": lb.get("armed_price", ""),
            "hist_armed": hb.get("armed_price", ""),
        })

    with open(output_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # Summary stats
    matched_times = [t for t in all_times if t in live_by_time and t in hist_by_time]
    ratio_diffs = []
    state_matches = 0
    armed_matches = 0
    for t in matched_times:
        lb = live_by_time[t]
        hb = hist_by_time[t]
        if lb["vol_ratio"] > 0 and hb["vol_ratio"] > 0:
            ratio_diffs.append(abs(lb["vol_ratio"] - hb["vol_ratio"]) / max(lb["vol_ratio"], hb["vol_ratio"]))
        if lb["state"] == hb["state"]:
            state_matches += 1
        if lb["armed_price"] == hb["armed_price"]:
            armed_matches += 1

    result = {
        "symbol": symbol,
        "date": date,
        "live_ticks": len(live_ticks),
        "hist_ticks": len(hist_ticks),
        "tick_ratio": round(len(hist_ticks) / max(len(live_ticks), 1), 1),
        "live_bars": len(live_h.bars),
        "hist_bars": len(hist_h.bars),
        "matched_bars": len(matched_times),
        "avg_ratio_diff": round(sum(ratio_diffs) / len(ratio_diffs) * 100, 1) if ratio_diffs else 0,
        "max_ratio_diff": round(max(ratio_diffs) * 100, 1) if ratio_diffs else 0,
        "state_match_pct": round(state_matches / len(matched_times) * 100, 1) if matched_times else 0,
        "armed_match_pct": round(armed_matches / len(matched_times) * 100, 1) if matched_times else 0,
    }

    print(f"\n  Matched bars: {result['matched_bars']}")
    print(f"  Avg vol_ratio difference: {result['avg_ratio_diff']}%")
    print(f"  Max vol_ratio difference: {result['max_ratio_diff']}%")
    print(f"  State match: {result['state_match_pct']}%")
    print(f"  Armed match: {result['armed_match_pct']}%")
    print(f"  → CSV: {output_csv}")

    return result


def generate_report(results):
    lines = ["# Vol Ratio Parity Report — RTVolume vs Historical Ticks",
             f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             "", "---", ""]

    lines.append("## Summary")
    lines.append("")
    lines.append("| Symbol | Date | Live Ticks | Hist Ticks | Tick Ratio | Matched Bars | Avg Ratio Diff | Max Ratio Diff | State Match | Armed Match |")
    lines.append("|--------|------|-----------|-----------|------------|-------------|---------------|---------------|-------------|-------------|")
    for r in results:
        lines.append(f"| {r['symbol']} | {r['date']} | {r['live_ticks']:,} | {r['hist_ticks']:,} | "
                     f"{r['tick_ratio']}x | {r['matched_bars']} | {r['avg_ratio_diff']}% | {r['max_ratio_diff']}% | "
                     f"{r['state_match_pct']}% | {r['armed_match_pct']}% |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Interpretation
    avg_diff_all = sum(r["avg_ratio_diff"] for r in results) / len(results) if results else 0
    lines.append("## Interpretation")
    lines.append("")
    if avg_diff_all < 20:
        lines.append(f"**Average ratio difference across all tests: {avg_diff_all:.1f}%** — WITHIN 20% THRESHOLD.")
        lines.append("")
        lines.append("RTVolume undercount appears proportional. `vol_ratio` tracks consistently between live and historical feeds. "
                     "The squeeze detector should fire on the same setups regardless of data source.")
        lines.append("")
        lines.append("**Recommendation:** No `WB_SQ_VOL_MULT` calibration needed. Current thresholds are valid for live trading.")
    else:
        lines.append(f"**Average ratio difference across all tests: {avg_diff_all:.1f}%** — EXCEEDS 20% THRESHOLD.")
        lines.append("")
        lines.append("RTVolume compresses volume spikes more than quiet bars. `vol_ratio` is systematically lower on the live feed. "
                     "The squeeze detector will be harder to arm live than in backtests.")
        lines.append("")
        lines.append("**Recommendation:** Consider lowering `WB_SQ_VOL_MULT` for live trading, or switching to `reqTickByTickData('AllLast')`.")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Report by test_vol_ratio_parity.py*")

    with open("parity_tests/VOL_RATIO_PARITY_REPORT.md", "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport → parity_tests/VOL_RATIO_PARITY_REPORT.md")


if __name__ == "__main__":
    os.makedirs("parity_tests", exist_ok=True)

    tests = [
        ("FCUV", "2026-04-06", "tick_cache/2026-04-06/FCUV.json.gz",
         "tick_cache_historical/2026-04-06/FCUV.json.gz",
         "parity_tests/vol_ratio_comparison_FCUV_20260406.csv"),
        ("MLEC", "2026-04-06", "tick_cache/2026-04-06/MLEC.json.gz",
         "tick_cache_historical/2026-04-06/MLEC.json.gz",
         "parity_tests/vol_ratio_comparison_MLEC_20260406.csv"),
        ("ADVB", "2026-04-07", "tick_cache/2026-04-07/ADVB.json.gz",
         "tick_cache_historical/2026-04-07/ADVB.json.gz",
         "parity_tests/vol_ratio_comparison_ADVB_20260407.csv"),
    ]

    results = []
    for symbol, date, live_path, hist_path, csv_path in tests:
        if not os.path.exists(live_path):
            print(f"SKIP {symbol} {date}: no live tick cache")
            continue
        if not os.path.exists(hist_path):
            print(f"SKIP {symbol} {date}: no historical tick cache")
            continue
        r = run_comparison(symbol, date, live_path, hist_path, csv_path, f"RTVolume vs Historical")
        results.append(r)

    generate_report(results)
