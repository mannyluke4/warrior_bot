#!/usr/bin/env python3
"""
ibkr_tick_fetcher.py — Fetch historical tick data from IBKR and save to tick_cache.

Populates the same tick_cache format that simulate.py --ticks reads,
so backtests use the exact same data source as the live bot.

Usage:
    python ibkr_tick_fetcher.py EEIQ 2026-03-26
    python ibkr_tick_fetcher.py EEIQ 2026-03-26 --start 07:00 --end 20:00
    python ibkr_tick_fetcher.py --date 2026-03-26 --all-scanner  # fetch all scanner candidates
"""

import os
import sys
import json
import gzip
import argparse
import time as time_mod
from datetime import datetime, timedelta

from ib_insync import IB, Stock

TICK_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tick_cache")
SCANNER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_results")


def fetch_ticks(ib: IB, symbol: str, date: str, start_et: str = "04:00", end_et: str = "20:00"):
    """
    Fetch all trade ticks for a symbol on a given date from IBKR.
    Paginates through reqHistoricalTicks (1000 ticks per call).
    Returns list of dicts: [{"p": price, "s": size, "t": iso_timestamp}, ...]
    """
    contract = Stock(symbol, "SMART", "USD")
    try:
        ib.qualifyContracts(contract)
    except Exception as e:
        print(f"  Could not qualify {symbol}: {e}")
        return []

    import pytz
    ET = pytz.timezone("US/Eastern")

    all_ticks = []
    # Start from the beginning of the requested window
    # IBKR format: "yyyymmdd hh:mm:ss US/Eastern"
    date_compact = date.replace("-", "")
    current_start = f"{date_compact} {start_et}:00 US/Eastern"

    # Build end datetime in ET for comparison
    end_dt_et = ET.localize(datetime.strptime(f"{date} {end_et}", "%Y-%m-%d %H:%M"))
    max_iterations = 2000  # Safety limit (dense stocks can have many pages)
    pages = 0

    for i in range(max_iterations):
        try:
            ticks = ib.reqHistoricalTicks(
                contract,
                startDateTime=current_start,
                endDateTime="",
                numberOfTicks=1000,
                whatToShow="TRADES",
                useRth=False,
            )
        except Exception as e:
            print(f"  Error fetching ticks at {current_start}: {e}")
            break

        if not ticks:
            break

        pages += 1
        past_end = False
        for t in ticks:
            ts_utc = t.time
            tick_et = ts_utc.astimezone(ET)
            if tick_et >= end_dt_et:
                past_end = True
                break

            all_ticks.append({
                "p": float(t.price),
                "s": int(t.size),
                "t": ts_utc.isoformat(),
            })

        if past_end:
            break

        # Advance past the last tick's timestamp for next page
        last_time = ticks[-1].time
        # Use the exact last timestamp + tiny offset to avoid duplicates
        next_start = last_time.strftime("%Y%m%d %H:%M:%S") + " UTC"
        if current_start == next_start:
            # Same second — all ticks in this second, advance by 1s
            next_start = (last_time + timedelta(seconds=1)).strftime("%Y%m%d %H:%M:%S") + " UTC"
        current_start = next_start

        # Progress every 10 pages
        if pages % 10 == 0:
            tick_et = last_time.astimezone(ET)
            print(f"    {len(all_ticks):,} ticks, up to {tick_et.strftime('%H:%M:%S')} ET...", flush=True)

        # Rate limit (IBKR pacing)
        time_mod.sleep(0.3)

        if len(ticks) < 1000:
            break

    return all_ticks


def save_ticks(ticks: list, symbol: str, date: str):
    """Save ticks to tick_cache in the format simulate.py expects."""
    date_dir = os.path.join(TICK_CACHE_DIR, date)
    os.makedirs(date_dir, exist_ok=True)
    out_path = os.path.join(date_dir, f"{symbol}.json.gz")

    with gzip.open(out_path, "wt") as f:
        json.dump(ticks, f)

    print(f"  Saved {len(ticks)} ticks → {out_path}")
    return out_path


def needs_extend(cache_path: str, full_day_end_utc_hour: int = 19) -> bool:
    """Check if an existing tick_cache file needs extending to full-day.
    Returns True if the file doesn't exist, is empty, or its last tick
    is before full_day_end_utc_hour (default 19 = 15:00 ET in EDT,
    14:00 ET in EST — conservative cutoff for 'covers the afternoon').
    """
    if not os.path.exists(cache_path):
        return True
    try:
        with gzip.open(cache_path, "rt") as f:
            data = json.load(f)
        if not data:
            return True
        last_t = data[-1].get("t", "")
        # Parse hour from timestamp (format: 2026-01-16T16:59:59+00:00 or similar)
        # Extract the hour portion — works for both T-separated and space-separated
        hour_str = last_t[11:13] if len(last_t) > 13 else ""
        if not hour_str.isdigit():
            return True
        last_hour_utc = int(hour_str)
        return last_hour_utc < full_day_end_utc_hour
    except Exception:
        return True


def safe_save_ticks(new_ticks: list, symbol: str, date: str) -> bool:
    """Save ticks only if the new data is a superset of existing data.
    Returns True if saved, False if skipped (existing had more ticks)."""
    cache_path = os.path.join(TICK_CACHE_DIR, date, f"{symbol}.json.gz")
    existing_count = 0
    if os.path.exists(cache_path):
        try:
            with gzip.open(cache_path, "rt") as f:
                existing = json.load(f)
            existing_count = len(existing)
        except Exception:
            pass
    if len(new_ticks) < existing_count:
        print(f"  SKIP SAVE: {symbol} new={len(new_ticks)} < existing={existing_count} — keeping existing",
              flush=True)
        return False
    save_ticks(new_ticks, symbol, date)
    if existing_count > 0:
        print(f"    (extended: {existing_count:,} → {len(new_ticks):,} ticks)", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description="Fetch IBKR historical ticks for backtesting")
    parser.add_argument("symbol", nargs="?", help="Stock symbol (e.g., EEIQ)")
    parser.add_argument("date", nargs="?", help="Date (YYYY-MM-DD)")
    parser.add_argument("--start", default="04:00", help="Start time ET (default: 04:00)")
    parser.add_argument("--end", default="20:00", help="End time ET (default: 20:00)")
    parser.add_argument("--all-scanner", action="store_true",
                        help="Fetch all symbols from scanner_results for the given date")
    parser.add_argument("--date-range", nargs=2, metavar=("START", "END"),
                        help="Fetch all scanner candidates for a date range")
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch even if cache file exists (overwrite)")
    parser.add_argument("--extend", action="store_true",
                        help="Only refetch files that don't cover full day. "
                             "Checks last tick timestamp — if past 19:00 UTC (15:00 ET), "
                             "considers it complete. Safe on restart: never deletes data, "
                             "only replaces with a superset (more ticks = wider coverage).")
    parser.add_argument("--client-id", type=int, default=int(os.getenv("IBKR_FETCHER_CLIENT_ID", "99")),
                        help="IBKR clientId (default 99). Use distinct values if prior fetcher conn is stuck.")
    args = parser.parse_args()

    # Connect to IBKR
    ib = IB()
    try:
        port = int(os.getenv("IBKR_PORT", "4002"))
        ib.connect("127.0.0.1", port, clientId=args.client_id, timeout=15)
    except Exception as e:
        print(f"FATAL: Cannot connect to IBKR: {e}")
        sys.exit(1)

    try:
        if args.date_range:
            # Fetch all scanner candidates across a date range
            start_date, end_date = args.date_range
            import glob
            scanner_files = sorted(glob.glob(os.path.join(SCANNER_DIR, "20??-??-??.json")))
            dates = [os.path.basename(f).replace(".json", "") for f in scanner_files
                     if start_date <= os.path.basename(f).replace(".json", "") <= end_date]

            total_symbols = 0
            for date in dates:
                sf = os.path.join(SCANNER_DIR, f"{date}.json")
                with open(sf) as f:
                    raw = json.load(f)
                # Handle both formats: flat list of {symbol:...} dicts
                # OR live-scanner's [{timestamp:..., candidates:[...]}] nesting
                if isinstance(raw, list) and raw and "candidates" in raw[0]:
                    candidates = []
                    for entry in raw:
                        candidates.extend(entry.get("candidates", []))
                else:
                    candidates = raw if isinstance(raw, list) else []
                if not candidates:
                    continue

                symbols = [c["symbol"] for c in candidates if "symbol" in c]
                if args.force:
                    to_fetch = symbols
                    cached = []
                    skipped_full = []
                elif args.extend:
                    # Only refetch files that don't cover the full day
                    to_fetch = []
                    cached = []
                    skipped_full = []
                    for s in symbols:
                        cp = os.path.join(TICK_CACHE_DIR, date, f"{s}.json.gz")
                        if not os.path.exists(cp):
                            to_fetch.append(s)
                        elif needs_extend(cp):
                            to_fetch.append(s)
                        else:
                            skipped_full.append(s)
                else:
                    cached = [s for s in symbols if os.path.exists(
                        os.path.join(TICK_CACHE_DIR, date, f"{s}.json.gz"))]
                    to_fetch = [s for s in symbols if s not in cached]
                    skipped_full = []

                if not to_fetch:
                    skip_reason = f"{len(skipped_full)} full-day" if args.extend else f"{len(symbols)} cached"
                    print(f"[{date}] All {len(symbols)} symbols complete ({skip_reason}), skipping")
                    continue

                extend_note = f", {len(skipped_full)} already full-day" if skipped_full else ""
                print(f"\n[{date}] Fetching {len(to_fetch)} symbols{extend_note}...")
                for sym in to_fetch:
                    print(f"  [{date}] {sym}...", flush=True)
                    ticks = fetch_ticks(ib, sym, date, args.start, args.end)
                    if ticks:
                        if args.extend:
                            if safe_save_ticks(ticks, sym, date):
                                total_symbols += 1
                        else:
                            save_ticks(ticks, sym, date)
                            total_symbols += 1
                    else:
                        print(f"  {sym}: no ticks")
                    time_mod.sleep(1)  # IBKR pacing between symbols

            print(f"\nDone. Fetched ticks for {total_symbols} symbol-dates.")

        elif args.all_scanner:
            if not args.date:
                print("ERROR: --all-scanner requires a date argument")
                sys.exit(1)
            sf = os.path.join(SCANNER_DIR, f"{args.date}.json")
            if not os.path.exists(sf):
                print(f"No scanner results for {args.date}")
                sys.exit(1)
            with open(sf) as f:
                candidates = json.load(f)
            print(f"Fetching ticks for {len(candidates)} candidates on {args.date}...")
            for c in candidates:
                sym = c["symbol"]
                # Skip if already cached
                cache_path = os.path.join(TICK_CACHE_DIR, args.date, f"{sym}.json.gz")
                if os.path.exists(cache_path) and not args.force:
                    print(f"  {sym}: already cached, skipping")
                    continue
                print(f"  {sym}...", end=" ", flush=True)
                ticks = fetch_ticks(ib, sym, args.date, args.start, args.end)
                if ticks:
                    save_ticks(ticks, sym, args.date)
                else:
                    print(f"  no ticks")
                time_mod.sleep(1)

        elif args.symbol and args.date:
            print(f"Fetching {args.symbol} ticks for {args.date} ({args.start}-{args.end} ET)...")
            ticks = fetch_ticks(ib, args.symbol, args.date, args.start, args.end)
            if ticks:
                save_ticks(ticks, args.symbol, args.date)
            else:
                print("No ticks returned")
        else:
            parser.print_help()

    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
