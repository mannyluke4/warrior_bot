#!/usr/bin/env python3
"""
run_box_scanner_ytd.py — Run box scanner across all YTD dates.

Usage:
    python run_box_scanner_ytd.py --start 2026-01-02 --end 2026-04-02
    python run_box_scanner_ytd.py --start 2026-01-02 --end 2026-04-02 --time 10:00
    python run_box_scanner_ytd.py --start 2026-03-01 --end 2026-04-02 --universe box_universe.txt

Connects to IBKR Gateway, scans each date in sequence, saves results
to scanner_results_box/. Respects IBKR rate limits with pacing.

NOTE: This is I/O heavy — each date requires ~30-100 IBKR API calls
depending on universe size. Expect ~30 seconds per date.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

import pytz
from ib_insync import IB

ET = pytz.timezone("US/Eastern")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from box_scanner import (
    scan_box_historical, _load_adr_cache, _save_adr_cache,
    RESULTS_DIR,
)


def get_trading_dates(start_str: str, end_str: str) -> list:
    """Generate weekday dates between start and end (inclusive)."""
    start = datetime.strptime(start_str, "%Y-%m-%d")
    end = datetime.strptime(end_str, "%Y-%m-%d")
    dates = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def main():
    parser = argparse.ArgumentParser(description="Box Scanner YTD Runner")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--time", default="10:00", help="Scan time ET (default: 10:00)")
    parser.add_argument("--port", type=int, default=4002, help="IBKR Gateway port")
    parser.add_argument("--universe", default="", help="Path to universe file")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip dates that already have results")
    args = parser.parse_args()

    dates = get_trading_dates(args.start, args.end)
    print(f"Box Scanner YTD: {len(dates)} trading dates from {args.start} to {args.end}")
    print(f"Scan time: {args.time} ET")

    # Load universe
    universe = None
    if args.universe:
        with open(args.universe) as f:
            universe = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        print(f"Universe: {len(universe)} symbols from {args.universe}")

    # Load ADR cache
    _load_adr_cache()
    print(f"ADR cache: {len(_load_adr_cache.__code__.co_consts)} entries", flush=True)

    # Connect to IBKR
    ib = IB()
    print(f"Connecting to IBKR Gateway on port {args.port}...", flush=True)
    ib.connect("127.0.0.1", args.port, clientId=10)
    print("Connected.", flush=True)

    total_candidates = 0
    start_time = time.time()

    try:
        for i, date_str in enumerate(dates):
            # Skip if results already exist
            if args.skip_existing:
                result_file = os.path.join(RESULTS_DIR, f"{date_str}.json")
                if os.path.exists(result_file):
                    print(f"[{i+1}/{len(dates)}] {date_str}: SKIPPED (exists)", flush=True)
                    continue

            elapsed = time.time() - start_time
            rate = (i / elapsed * 60) if elapsed > 0 and i > 0 else 0
            eta = ((len(dates) - i) / rate) if rate > 0 else 0
            print(f"\n[{i+1}/{len(dates)}] {date_str} "
                  f"(elapsed: {elapsed/60:.1f}m, rate: {rate:.1f}/min, "
                  f"ETA: {eta:.0f}m)...", flush=True)

            try:
                candidates = scan_box_historical(ib, date_str, args.time, universe)
                total_candidates += len(candidates)

                # Print top 3 for each date
                for j, c in enumerate(candidates[:3], 1):
                    print(f"  {j}. {c['symbol']:6s} score={c['box_score']:.1f} "
                          f"adr_util={c['adr_util']:.0%} range={c['range_pct']:.1f}%",
                          flush=True)

            except Exception as e:
                print(f"  ERROR: {e}", flush=True)

            # Save ADR cache periodically
            if (i + 1) % 5 == 0:
                _save_adr_cache()

    except KeyboardInterrupt:
        print("\nInterrupted by user.", flush=True)
    finally:
        ib.disconnect()
        _save_adr_cache()

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"  Box Scanner YTD Complete")
    print(f"  Dates scanned: {len(dates)}")
    print(f"  Total candidates: {total_candidates}")
    print(f"  Avg per day: {total_candidates/max(len(dates),1):.1f}")
    print(f"  Elapsed: {elapsed/60:.1f} minutes")
    print(f"  Results saved to: {RESULTS_DIR}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
