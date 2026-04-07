#!/usr/bin/env python3
"""
test_seed_parity.py — Test 3: Validate that tick-level seeding (Option C)
produces the same detector state as organic replay.

Compares two paths for FCUV Apr 6:
  Path A (organic): Replay ALL ticks from start through TradeBarBuilder + SqueezeDetector
  Path B (seeded):  Replay ticks before discovery time, then continue organically
                    — simulating what the live bot does post-Option-C fix
"""

import gzip
import json
import os
import sys
from datetime import datetime, timezone

import pytz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bars import TradeBarBuilder
from squeeze_detector import SqueezeDetector

ET = pytz.timezone("US/Eastern")


def load_ticks(path):
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


class TrackedDetector:
    """Wraps SqueezeDetector + TradeBarBuilder with per-bar state recording."""

    def __init__(self, symbol):
        self.symbol = symbol
        self.sq = SqueezeDetector()
        self.sq.symbol = symbol
        self.bb = TradeBarBuilder(on_bar_close=self._on_bar, et_tz=ET, interval_seconds=60)
        self.bar_states = []

    def _on_bar(self, bar):
        o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume
        self.sq.seed_bar_close(o, h, l, c, v)

        bars_1m = self.sq.bars_1m
        if len(bars_1m) >= 2:
            prior_vols = [b["v"] for b in list(bars_1m)[:-1]]
            avg_vol = sum(prior_vols) / len(prior_vols)
            vol_ratio = v / avg_vol if avg_vol > 0 else 0
        else:
            avg_vol = 0
            vol_ratio = 0

        bar_time = bar.start_utc.astimezone(ET) if bar.start_utc else None
        self.bar_states.append({
            "time_et": bar_time.strftime("%H:%M:%S") if bar_time else "?",
            "vol": v,
            "avg_vol": round(avg_vol),
            "vol_ratio": round(vol_ratio, 3),
            "ema": round(self.sq.ema, 4) if self.sq.ema else None,
            "hod": round(self.sq._session_hod, 4),
            "state": self.sq._state,
            "armed": self.sq.armed.trigger_high if self.sq.armed else None,
        })

    def feed(self, ticks):
        for dt, price, size in ticks:
            if price <= 0 or size <= 0:
                continue
            self.bb.on_trade(self.symbol, price, size, dt)


def main():
    os.makedirs("parity_tests", exist_ok=True)

    # Use FCUV Apr 6 live ticks (RTVolume)
    symbol = "FCUV"
    date = "2026-04-06"
    tick_path = "tick_cache/2026-04-06/FCUV.json.gz"

    if not os.path.exists(tick_path):
        print(f"ERROR: {tick_path} not found")
        return

    all_ticks = load_ticks(tick_path)
    print(f"Loaded {len(all_ticks):,} ticks for {symbol} {date}")

    # Discovery time from scanner: sim_start=07:58 ET
    discovery_et = ET.localize(datetime.strptime("2026-04-06 07:58:00", "%Y-%m-%d %H:%M:%S"))
    discovery_utc = discovery_et.astimezone(timezone.utc)

    seed_ticks = [(dt, p, s) for dt, p, s in all_ticks if dt < discovery_utc]
    live_ticks = [(dt, p, s) for dt, p, s in all_ticks if dt >= discovery_utc]
    print(f"  Seed ticks (before {discovery_et.strftime('%H:%M ET')}): {len(seed_ticks):,}")
    print(f"  Live ticks (after): {len(live_ticks):,}")

    # Path A: Organic — replay ALL ticks through one detector
    print("\nPath A: Organic replay (all ticks)...")
    organic = TrackedDetector(symbol)
    organic.feed(all_ticks)
    print(f"  Bars: {len(organic.bar_states)}")

    # Path B: Seeded — replay seed ticks, then live ticks (same detector, continuous)
    # This simulates Option C: tick-level seeding through TradeBarBuilder
    print("Path B: Seeded replay (seed ticks, then live ticks)...")
    seeded = TrackedDetector(symbol)
    seeded.feed(seed_ticks)  # seed phase
    seed_bar_count = len(seeded.bar_states)
    seeded.feed(live_ticks)  # live phase
    print(f"  Bars: {len(seeded.bar_states)} ({seed_bar_count} from seed, {len(seeded.bar_states) - seed_bar_count} live)")

    # Compare: only bars AFTER discovery time
    org_post = [b for b in organic.bar_states if b["time_et"] >= "07:58"]
    sed_post = [b for b in seeded.bar_states if b["time_et"] >= "07:58"]

    print(f"\nPost-discovery bars: organic={len(org_post)}, seeded={len(sed_post)}")

    # Match by time
    org_by_time = {b["time_et"]: b for b in org_post}
    sed_by_time = {b["time_et"]: b for b in sed_post}
    all_times = sorted(set(list(org_by_time.keys()) + list(sed_by_time.keys())))
    matched = [(t, org_by_time.get(t), sed_by_time.get(t)) for t in all_times
               if t in org_by_time and t in sed_by_time]

    # Report
    lines = ["# Seed Parity Report — Option C Validation",
             f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"**Stock**: {symbol} {date}",
             f"**Discovery time**: 07:58 ET",
             "", "---", ""]

    lines.append("## Tick Split")
    lines.append(f"- Total ticks: {len(all_ticks):,}")
    lines.append(f"- Seed ticks (before 07:58): {len(seed_ticks):,}")
    lines.append(f"- Live ticks (after 07:58): {len(live_ticks):,}")
    lines.append("")

    lines.append("## Bar Count")
    lines.append(f"- Organic (Path A): {len(organic.bar_states)} total, {len(org_post)} post-discovery")
    lines.append(f"- Seeded (Path B): {len(seeded.bar_states)} total ({seed_bar_count} seed + {len(seeded.bar_states)-seed_bar_count} live), {len(sed_post)} post-discovery")
    lines.append(f"- Matched bars: {len(matched)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Divergence analysis
    vol_diffs = []
    ema_diffs = []
    state_mismatches = 0
    armed_mismatches = 0

    lines.append("## Bar-by-Bar Comparison (post-discovery)")
    lines.append("")
    lines.append("| Time ET | Org Vol | Sed Vol | Match? | Org EMA | Sed EMA | Org State | Sed State | Org Armed | Sed Armed |")
    lines.append("|---------|---------|---------|--------|---------|---------|-----------|-----------|-----------|-----------|")

    for t, ob, sb in matched[:50]:  # first 50 bars
        vol_match = "✓" if ob["vol"] == sb["vol"] else "✗"
        if ob["vol"] != sb["vol"]:
            vol_diffs.append(abs(ob["vol"] - sb["vol"]))
        if ob["ema"] and sb["ema"]:
            ema_diffs.append(abs(ob["ema"] - sb["ema"]))
        if ob["state"] != sb["state"]:
            state_mismatches += 1
        if ob["armed"] != sb["armed"]:
            armed_mismatches += 1

        lines.append(f"| {t} | {ob['vol']:,} | {sb['vol']:,} | {vol_match} | "
                     f"{ob['ema']} | {sb['ema']} | {ob['state']} | {sb['state']} | "
                     f"{ob['armed'] or '-'} | {sb['armed'] or '-'} |")

    if len(matched) > 50:
        # Process remaining without printing
        for t, ob, sb in matched[50:]:
            if ob["vol"] != sb["vol"]:
                vol_diffs.append(abs(ob["vol"] - sb["vol"]))
            if ob["ema"] and sb["ema"]:
                ema_diffs.append(abs(ob["ema"] - sb["ema"]))
            if ob["state"] != sb["state"]:
                state_mismatches += 1
            if ob["armed"] != sb["armed"]:
                armed_mismatches += 1
        lines.append(f"| ... | ({len(matched)-50} more bars) | | | | | | | | |")

    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Volume mismatches**: {len(vol_diffs)} of {len(matched)} bars ({len(vol_diffs)/len(matched)*100:.1f}%)")
    lines.append(f"- **State mismatches**: {state_mismatches} of {len(matched)} bars")
    lines.append(f"- **Armed mismatches**: {armed_mismatches} of {len(matched)} bars")
    if ema_diffs:
        lines.append(f"- **Max EMA difference**: {max(ema_diffs):.6f}")
        lines.append(f"- **Avg EMA difference**: {sum(ema_diffs)/len(ema_diffs):.6f}")
    lines.append("")

    if state_mismatches == 0 and armed_mismatches == 0:
        lines.append("**RESULT: PARITY CONFIRMED.** Option C tick-level seeding produces identical detector state to organic replay. "
                     "The seed path and organic path arrive at the same IDLE/PRIMED/ARMED decisions on every bar.")
    else:
        lines.append(f"**RESULT: DIVERGENCE DETECTED.** {state_mismatches} state mismatches, {armed_mismatches} armed mismatches. "
                     "The seed path diverges from organic replay — investigate root cause.")

    lines.append("")
    lines.append("---")
    lines.append("*Report by test_seed_parity.py*")

    with open("parity_tests/SEED_PARITY_REPORT.md", "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport → parity_tests/SEED_PARITY_REPORT.md")


if __name__ == "__main__":
    main()
