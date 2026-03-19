#!/usr/bin/env python3
"""
Key Dates Backtest — Aligned Scanner Only
Runs the YTD V2 backtest engine against ONLY the dates that have
newly aligned (Ross Pillar) scanner results. This avoids mixing
old unaligned scanner data with the new.

Usage:
    source venv/bin/activate
    python run_key_dates_backtest.py
"""

# Monkey-patch the DATES list before importing the runner
import run_ytd_v2_backtest as runner

# Only dates with new aligned scanner results (scanned 2026-03-19)
ALIGNED_DATES = [
    "2026-01-02",
    "2026-01-03",
    "2026-01-05",
    "2026-01-06",
    "2026-01-08",
    "2026-01-14",
    "2026-01-16",
    "2026-03-10",
    "2026-03-18",
]

# Override
runner.DATES = ALIGNED_DATES
runner.STATE_FILE = "key_dates_backtest_state.json"

if __name__ == "__main__":
    print("=" * 60)
    print("KEY DATES BACKTEST — Aligned Scanner Results Only")
    print(f"Dates: {len(ALIGNED_DATES)} ({ALIGNED_DATES[0]} to {ALIGNED_DATES[-1]})")
    print(f"Starting equity: ${runner.STARTING_EQUITY:,}")
    print("=" * 60)
    results = runner.run_backtest()
    runner.generate_report(results)
