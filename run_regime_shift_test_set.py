#!/usr/bin/env python3
"""Run REGIME-SHIFT Stage 1 backtest across the historical vertical test set.

Per cowork_reports/2026-05-22_regime_shift_strategy_directive.md.

Usage:
    WB_REGIME_SHIFT_RATIO_THRESHOLD=4.0 python run_regime_shift_test_set.py
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime

# Top 30 days by intraday range from the file-size scan (per directive)
TEST_SET = [
    ("SPHL", "2026-01-15"), ("GLTO", "2025-10-07"), ("BIRD", "2026-04-15"),
    ("CYN", "2025-06-26"), ("BGLC", "2025-07-01"), ("MBIO", "2025-07-07"),
    ("VERO", "2026-01-16"), ("XBIO", "2025-10-08"), ("FGI", "2025-09-16"),
    ("CYCN", "2026-04-01"), ("CETX", "2025-12-08"), ("HOTH", "2025-01-07"),
    ("SXTP", "2026-01-22"), ("HWH", "2025-09-02"), ("TNON", "2025-03-25"),
    ("AGMH", "2025-09-19"), ("AVX", "2025-09-22"), ("STI", "2025-10-13"),
    ("AIHS", "2025-09-03"), ("QTTB", "2025-12-01"), ("APM", "2025-08-21"),
    ("XPON", "2025-08-14"), ("AIXC", "2025-09-22"), ("OLOX", "2025-10-10"),
    ("PLRZ", "2025-12-02"), ("KTTA", "2025-05-06"), ("NDRA", "2025-07-08"),
    ("HOUR", "2025-09-05"), ("IVF", "2026-01-20"), ("COOT", "2025-10-15"),
    ("PCLA", "2026-05-21"),  # canonical case
]


def run_one(symbol, date):
    cmd = [
        sys.executable, "simulate.py",
        symbol, date, "04:00", "20:00",
        "--ticks", "--tick-cache", "tick_cache/",
        "--slippage", "0.07", "--no-fundamentals",
    ]
    env = dict(os.environ)
    env.setdefault("WB_BT_MOVE_STRIKE", "1")
    env.setdefault("WB_BT_MOVE_HWM_EXIT", "1")
    env.setdefault("WB_BT_MOVE_REENTRY_GREEN", "1")
    env.setdefault("WB_BT_MOVE_REENTRY_BLOCK_SAME_BAR", "1")
    env.setdefault("WB_BT_MOVE_STAY_ARMED", "1")
    env.setdefault("WB_BT_MOVE_MAX_BELOW_ARM_PCT", "3.0")
    env.setdefault("WB_REGIME_SHIFT_ENABLED", "1")
    env.setdefault("WB_REGIME_SHIFT_REQUIRE_ARMED", "1")
    env.setdefault("WB_REGIME_SHIFT_MAX_PER_SYMBOL", "1")
    env.setdefault("WB_SQUEEZE_VERSION", "2")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
    except subprocess.TimeoutExpired:
        return {"symbol": symbol, "date": date, "error": "timeout"}
    out = p.stdout
    # Parse total P&L
    m = re.search(r"Gross P&L:\s+\$([+-]?[\d,]+)", out)
    pnl = int(m.group(1).replace(",", "")) if m else 0
    # Parse trade count
    m = re.search(r"Trades:\s+(\d+)\s+\|", out)
    trades = int(m.group(1)) if m else 0
    # Parse intraday range from tick cache size proxy
    # Better: parse High and Low from sim output bar summary
    m_high = re.search(r"Max price:\s+\$?([\d.]+)", out)
    m_low = re.search(r"Min price:\s+\$?([\d.]+)", out)
    # Look at regime-shift trade specifically — any line with regime_partial
    rs_trades = []
    rs_entries = []
    for line in out.split("\n"):
        if "regime_partial" in line:
            rs_trades.append(line.strip())
        if "REGIME_SHIFT entry" in line:
            rs_entries.append(line.strip())
    return {
        "symbol": symbol,
        "date": date,
        "total_trades": trades,
        "total_pnl": pnl,
        "regime_partial_count": len(rs_trades),
        "regime_partial_lines": rs_trades[:3],  # truncate
    }


def main():
    threshold = os.environ.get("WB_REGIME_SHIFT_RATIO_THRESHOLD", "3.0")
    max_per_sym = os.environ.get("WB_REGIME_SHIFT_MAX_PER_SYMBOL", "1")
    print(f"=== REGIME-SHIFT Stage 1 — Set A ===")
    print(f"Threshold: {threshold}, max_per_symbol: {max_per_sym}")
    print(f"Test set: {len(TEST_SET)} symbol/date pairs")
    print()
    results = []
    for i, (sym, date) in enumerate(TEST_SET):
        # Skip if tick cache missing
        if not os.path.exists(f"tick_cache/{date}/{sym}.json.gz"):
            print(f"[{i + 1}/{len(TEST_SET)}] {sym} {date}: NO CACHE — skip")
            continue
        r = run_one(sym, date)
        results.append(r)
        if r.get("error"):
            print(f"[{i + 1}/{len(TEST_SET)}] {sym} {date}: {r['error']}")
        else:
            print(f"[{i + 1}/{len(TEST_SET)}] {sym} {date}: "
                  f"trades={r['total_trades']} pnl=${r['total_pnl']:+,d} "
                  f"regime_partials={r['regime_partial_count']}")
    print()
    print("=== Summary ===")
    valid = [r for r in results if not r.get("error")]
    total_pnl = sum(r["total_pnl"] for r in valid)
    total_trades = sum(r["total_trades"] for r in valid)
    rs_partial_count = sum(r["regime_partial_count"] for r in valid)
    winning_days = sum(1 for r in valid if r["total_pnl"] > 0)
    print(f"Days tested: {len(valid)} / {len(TEST_SET)}")
    print(f"Total trades: {total_trades}")
    print(f"Total P&L: ${total_pnl:+,d}")
    print(f"Winning days: {winning_days} / {len(valid)} ({winning_days/len(valid)*100:.0f}%)")
    print(f"Regime-shift partial fires: {rs_partial_count}")
    # Per-day breakdown
    print()
    print("=== Per-day ===")
    for r in valid:
        marker = "🎯" if r["regime_partial_count"] > 0 else "  "
        print(f"  {marker} {r['date']} {r['symbol']:>5}: "
              f"trades={r['total_trades']:>3} pnl=${r['total_pnl']:+6,d}")

    # Persist as JSON for the report
    out_path = f"backtest_status/regime_shift_set_a_thr{threshold}_max{max_per_sym}.json"
    with open(out_path, "w") as f:
        json.dump({
            "threshold": threshold,
            "max_per_symbol": max_per_sym,
            "results": valid,
            "summary": {
                "days_tested": len(valid),
                "total_pnl": total_pnl,
                "total_trades": total_trades,
                "winning_days": winning_days,
                "regime_partial_count": rs_partial_count,
            },
        }, f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
