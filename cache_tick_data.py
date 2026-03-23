#!/usr/bin/env python3
"""
Cache Tick Data — Download and store Alpaca tick data locally for deterministic backtests.

Downloads tick-level trade data for every stock/date pair selected by the scanner,
saves to tick_cache/{date}/{symbol}.json.gz. One stock at a time, with rate limiting
and retries, to avoid Alpaca API non-determinism from concurrent requests.

Usage:
    python cache_tick_data.py                    # cache all dates
    python cache_tick_data.py --dates 2026-01-16 # cache specific date(s)
    python cache_tick_data.py --force             # re-download even if cached
    python cache_tick_data.py --verify            # verify existing cache integrity
"""

import argparse
import gzip
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytz
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockTradesRequest

# Load .env manually (avoid python-dotenv dependency)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

ET = pytz.timezone("US/Eastern")
WORKDIR = os.path.dirname(os.path.abspath(__file__))
SCANNER_DIR = os.path.join(WORKDIR, "scanner_results")
CACHE_DIR = os.path.join(WORKDIR, "tick_cache")
MANIFEST_FILE = os.path.join(CACHE_DIR, "manifest.json")

# Scanner filters (must match run_ytd_v2_backtest.py)
MIN_GAP_PCT = 5
MAX_GAP_PCT = 500
MAX_FLOAT_MILLIONS = 10
TOP_N = 5

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
hist_client = StockHistoricalDataClient(API_KEY, API_SECRET)

# All backtest dates
DATES = [
    "2026-01-02", "2026-01-03", "2026-01-05", "2026-01-06", "2026-01-07",
    "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13", "2026-01-14",
    "2026-01-15", "2026-01-16", "2026-01-20", "2026-01-21", "2026-01-22",
    "2026-01-23", "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29",
    "2026-01-30",
    "2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06",
    "2026-02-09", "2026-02-10", "2026-02-11", "2026-02-12", "2026-02-13",
    "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-23",
    "2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27",
    "2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06",
    "2026-03-09", "2026-03-10", "2026-03-11", "2026-03-12",
]

import math

def rank_score(candidate):
    """Composite score: 40% RVOL + 30% abs volume + 20% gap + 10% float bonus.
    Must match run_ytd_v2_backtest.py exactly."""
    pm_vol = candidate.get("pm_volume", 0) or 0
    rvol = candidate.get("relative_volume", 0) or 0
    gap_pct = candidate.get("gap_pct", 0) or 0
    float_m = candidate.get("float_millions", 10) or 10
    rvol_score = math.log10(max(rvol, 0.1) + 1) / math.log10(51)
    vol_score = math.log10(max(pm_vol, 1)) / 8
    gap_score = min(gap_pct, 100) / 100
    float_penalty = min(float_m, 10) / 10
    return (0.4 * rvol_score) + (0.3 * vol_score) + (0.2 * gap_score) + (0.1 * (1 - float_penalty))


def load_top_stocks(date_str):
    """Load scanner results for a date and return top N stocks (matching batch runner logic)."""
    path = os.path.join(SCANNER_DIR, f"{date_str}.json")
    if not os.path.exists(path):
        return []

    with open(path) as f:
        candidates = json.load(f)

    # Apply same filters as run_ytd_v2_backtest.py
    filtered = []
    for c in candidates:
        gap = c.get("gap_pct", 0) or 0
        float_m = c.get("float_millions") or 999
        profile = c.get("profile", "unknown")
        if gap < MIN_GAP_PCT or gap > MAX_GAP_PCT:
            continue
        if float_m > MAX_FLOAT_MILLIONS:
            continue
        # "X" is legacy name for unknown-float, kept for backward compat with old scanner JSONs
        if profile in ("X", "unknown"):
            continue
        filtered.append(c)

    # Rank and take top N
    filtered.sort(key=rank_score, reverse=True)
    return filtered[:TOP_N]


def fetch_and_cache(symbol, date_str, sim_start="07:00", sim_end="12:00",
                    force=False, manifest=None):
    """Fetch tick data from Alpaca and save to cache. Returns (tick_count, checksum, status)."""
    date_dir = os.path.join(CACHE_DIR, date_str)
    os.makedirs(date_dir, exist_ok=True)
    cache_file = os.path.join(date_dir, f"{symbol}.json.gz")

    # Skip if already cached (unless --force)
    if os.path.exists(cache_file) and not force:
        # Verify file is readable
        try:
            with gzip.open(cache_file, "rt") as f:
                data = json.load(f)
            count = len(data)
            checksum = manifest.get(f"{date_str}/{symbol}", {}).get("checksum", "cached") if manifest else "cached"
            return count, checksum, "skipped"
        except Exception:
            print(f"    Corrupt cache file, re-downloading...", flush=True)

    # Build UTC time window
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    start_parts = sim_start.split(":")
    end_parts = sim_end.split(":")
    start_et = ET.localize(dt.replace(hour=int(start_parts[0]), minute=int(start_parts[1])))
    end_et = ET.localize(dt.replace(hour=int(end_parts[0]), minute=int(end_parts[1])))
    start_utc = start_et.astimezone(timezone.utc)
    end_utc = end_et.astimezone(timezone.utc)

    # Fetch with retries
    req = StockTradesRequest(
        symbol_or_symbols=[symbol],
        start=start_utc,
        end=end_utc,
        feed="sip",
    )

    tick_data = None
    for attempt in range(3):
        try:
            trade_set = hist_client.get_stock_trades(req)
            raw_trades = trade_set.data.get(symbol, [])
            # Serialize to list of dicts
            tick_data = []
            for t in raw_trades:
                tick_data.append({
                    "p": float(t.price),
                    "s": int(t.size),
                    "t": t.timestamp.isoformat(),
                })
            break
        except Exception as e:
            if attempt < 2:
                wait = 2 ** (attempt + 1)
                print(f"    [RETRY {attempt+1}] {symbol} {date_str}: {e} — waiting {wait}s", flush=True)
                time.sleep(wait)
            else:
                print(f"    [FAILED] {symbol} {date_str}: {e} — all retries exhausted", flush=True)
                return 0, None, "failed"

    if tick_data is None:
        return 0, None, "failed"

    # Compute checksum
    raw_json = json.dumps(tick_data, separators=(",", ":"))
    checksum = hashlib.md5(raw_json.encode()).hexdigest()[:12]

    # Write compressed
    with gzip.open(cache_file, "wt") as f:
        f.write(raw_json)

    return len(tick_data), checksum, "downloaded"


def load_manifest():
    """Load existing manifest or create empty one."""
    if os.path.exists(MANIFEST_FILE):
        with open(MANIFEST_FILE) as f:
            return json.load(f)
    return {}


def save_manifest(manifest):
    """Save manifest to disk."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


def verify_cache(dates):
    """Verify all cached files are readable and match manifest checksums."""
    manifest = load_manifest()
    ok = 0
    bad = 0
    missing = 0

    for date_str in dates:
        stocks = load_top_stocks(date_str)
        for c in stocks:
            sym = c["symbol"]
            key = f"{date_str}/{sym}"
            cache_file = os.path.join(CACHE_DIR, date_str, f"{sym}.json.gz")

            if not os.path.exists(cache_file):
                print(f"  MISSING: {key}", flush=True)
                missing += 1
                continue

            try:
                with gzip.open(cache_file, "rt") as f:
                    data = json.load(f)
                count = len(data)
                raw_json = json.dumps(data, separators=(",", ":"))
                checksum = hashlib.md5(raw_json.encode()).hexdigest()[:12]

                expected = manifest.get(key, {})
                if expected.get("checksum") and expected["checksum"] != checksum:
                    print(f"  CHECKSUM MISMATCH: {key} (expected {expected['checksum']}, got {checksum})", flush=True)
                    bad += 1
                else:
                    ok += 1
            except Exception as e:
                print(f"  CORRUPT: {key}: {e}", flush=True)
                bad += 1

    print(f"\nVerification: {ok} OK, {bad} bad, {missing} missing", flush=True)
    return bad == 0 and missing == 0


def validate_cache(dates):
    """Compare cached tick counts to fresh API calls. Re-download any mismatches.
    This catches Alpaca's rate-limiting-induced data loss during initial caching."""
    manifest = load_manifest()
    fixed = 0
    ok_count = 0

    for date_str in dates:
        stocks = load_top_stocks(date_str)
        for c in stocks:
            sym = c["symbol"]
            key = f"{date_str}/{sym}"
            cached_ticks = manifest.get(key, {}).get("ticks", 0)

            # Quick API call to get tick count
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            sim_start = c.get("sim_start", "07:00")
            start_parts = sim_start.split(":")
            start_et = ET.localize(dt.replace(hour=int(start_parts[0]), minute=int(start_parts[1])))
            end_et = ET.localize(dt.replace(hour=12, minute=0))
            start_utc = start_et.astimezone(timezone.utc)
            end_utc = end_et.astimezone(timezone.utc)

            try:
                req = StockTradesRequest(
                    symbol_or_symbols=[sym], start=start_utc, end=end_utc, feed="sip"
                )
                trade_set = hist_client.get_stock_trades(req)
                api_ticks = len(trade_set.data.get(sym, []))
            except Exception as e:
                print(f"  {key}: API error during validation: {e}", flush=True)
                time.sleep(5)
                continue

            if api_ticks != cached_ticks:
                pct_diff = abs(api_ticks - cached_ticks) / max(cached_ticks, 1) * 100
                print(f"  MISMATCH {key}: cached={cached_ticks:,} api={api_ticks:,} ({pct_diff:.1f}% diff) — re-caching...", flush=True)
                count, checksum, status = fetch_and_cache(sym, date_str, sim_start=sim_start, force=True)
                if status == "downloaded":
                    manifest[key] = {
                        "ticks": count,
                        "checksum": checksum,
                        "cached_at": datetime.now().isoformat(),
                        "validated": True,
                    }
                    save_manifest(manifest)
                    print(f"    Re-cached: {count:,} ticks (md5: {checksum})", flush=True)
                    fixed += 1
                time.sleep(5)
            else:
                ok_count += 1
                time.sleep(2)

    print(f"\nValidation: {ok_count} OK, {fixed} fixed", flush=True)
    return fixed


def main():
    parser = argparse.ArgumentParser(description="Cache Alpaca tick data for deterministic backtests")
    parser.add_argument("--dates", nargs="+", help="Specific dates to cache (default: all)")
    parser.add_argument("--force", action="store_true", help="Re-download even if cached")
    parser.add_argument("--verify", action="store_true", help="Verify existing cache integrity")
    parser.add_argument("--validate", action="store_true",
                        help="Compare cached tick counts to fresh API calls and fix mismatches")
    args = parser.parse_args()

    dates = args.dates if args.dates else DATES

    if args.verify:
        ok = verify_cache(dates)
        sys.exit(0 if ok else 1)

    if args.validate:
        fixed = validate_cache(dates)
        sys.exit(0)

    manifest = load_manifest()

    total_pairs = 0
    downloaded = 0
    skipped = 0
    failed = 0
    failed_list = []

    for date_str in dates:
        stocks = load_top_stocks(date_str)
        if not stocks:
            print(f"[{date_str}] No scanner results — skipping", flush=True)
            continue

        syms = [c["symbol"] for c in stocks]
        print(f"[{date_str}] Caching {len(stocks)} stocks: {', '.join(syms)}", flush=True)

        for c in stocks:
            sym = c["symbol"]
            sim_start = c.get("sim_start", "07:00")
            total_pairs += 1

            count, checksum, status = fetch_and_cache(
                sym, date_str, sim_start=sim_start, force=args.force, manifest=manifest
            )

            if status == "downloaded":
                downloaded += 1
                manifest[f"{date_str}/{sym}"] = {
                    "ticks": count,
                    "checksum": checksum,
                    "cached_at": datetime.now().isoformat(),
                }
                save_manifest(manifest)
                print(f"  {sym}: {count:,} ticks cached (md5: {checksum})", flush=True)
                # Rate limit between downloads
                time.sleep(2)
            elif status == "skipped":
                skipped += 1
                print(f"  {sym}: {count:,} ticks (already cached)", flush=True)
            else:
                failed += 1
                failed_list.append(f"{date_str}/{sym}")
                print(f"  {sym}: FAILED", flush=True)
                time.sleep(3)  # Extra backoff after failure

    print(f"\n{'='*60}", flush=True)
    print(f"Cache complete: {total_pairs} pairs | {downloaded} downloaded | {skipped} skipped | {failed} failed", flush=True)

    if failed_list:
        print(f"\nFailed stocks (re-run with --dates to retry):", flush=True)
        for f_item in failed_list:
            print(f"  {f_item}", flush=True)

    # Final stats
    total_ticks = sum(v.get("ticks", 0) for v in manifest.values())
    cache_size = 0
    for root, dirs, files in os.walk(CACHE_DIR):
        for fname in files:
            if fname.endswith(".json.gz"):
                cache_size += os.path.getsize(os.path.join(root, fname))

    print(f"\nTotal cached: {len(manifest)} pairs, {total_ticks:,} ticks, {cache_size/1024/1024:.1f} MB on disk", flush=True)


if __name__ == "__main__":
    main()
