"""
ibkr_scanner.py — Unified pre-market gap-up scanner using IBKR API.
Used by BOTH the live bot AND the backtest runner.

Live mode:  reqScannerSubscription + reqMktData for real-time candidates
Backtest mode: reqHistoricalData for historical candidates on a given date

Replaces: scanner_sim.py, live_scanner.py, market_scanner.py, stock_filter.py
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timedelta
from typing import Optional

import pytz
from ib_insync import IB, Stock, ScannerSubscription

# Reuse existing float lookup chain (FMP → yfinance → EDGAR → AlphaVantage)
from scanner_sim import (
    get_float,
    load_float_cache,
    save_float_cache,
    classify_profile,
    KNOWN_FLOATS,
)

ET = pytz.timezone("US/Eastern")

# Filter thresholds — read from .env with sensible defaults
MIN_GAP_PCT = float(os.getenv("WB_MIN_GAP_PCT", "10"))
MAX_GAP_PCT = float(os.getenv("WB_MAX_GAP_PCT", "500"))
MIN_PRICE = float(os.getenv("WB_MIN_PRICE", "2.00"))
MAX_PRICE = float(os.getenv("WB_MAX_PRICE", "20.00"))
MAX_FLOAT_M = float(os.getenv("WB_MAX_FLOAT", "15"))
MIN_RVOL = float(os.getenv("WB_MIN_REL_VOLUME", "2.0"))
MIN_PM_VOLUME = int(os.getenv("WB_MIN_PM_VOLUME", "50000"))
MAX_MARKET_CAP = 500_000_000  # $500M — small-cap filter proxy
SCANNER_RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_results")
FLOAT_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_results", "float_cache.json")


# ── Ranking ──────────────────────────────────────────────────────────

def rank_score(c: dict) -> float:
    """Unified composite ranking: RVOL 40%, PM volume 30%, gap% 20%, float 10%."""
    rvol = c.get("relative_volume", 0) or 0
    pm_vol = c.get("pm_volume", 0) or 0
    gap = c.get("gap_pct", 0) or 0
    float_m = c.get("float_millions", 10) or 10
    rvol_score = math.log10(min(rvol, 50) + 1) / math.log10(51)
    vol_score = math.log10(max(pm_vol, 1)) / 8
    gap_score = min(gap, 100) / 100
    float_score = 1 - (min(float_m, 10) / 10)
    return (0.40 * rvol_score) + (0.30 * vol_score) + (0.20 * gap_score) + (0.10 * float_score)


# ── RVOL Computation (unified for live + backtest) ───────────────────

def compute_adv(ib: IB, symbol: str, date_str: Optional[str] = None) -> float:
    """Compute 20-day average daily volume using IBKR historical data.
    Same source for both live and backtest → parity guaranteed."""
    contract = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(contract)

    if date_str:
        end_dt = f"{date_str.replace('-', '')} 16:00:00 US/Eastern"
    else:
        end_dt = ''  # Now

    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_dt,
            durationStr='30 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1,
            timeout=15,  # 15 second timeout
        )
        ib.sleep(0.5)
        if bars and len(bars) >= 5:
            vols = [b.volume for b in bars[-20:]]
            return sum(vols) / len(vols)
    except Exception as e:
        print(f"  [ADV] {symbol}: error — {e}")

    return 0.0


def compute_rvol(current_volume: float, adv: float) -> float:
    """Relative volume = current volume / average daily volume."""
    if adv <= 0:
        return 0.0
    return current_volume / adv


# ── Live Scanner ─────────────────────────────────────────────────────

def scan_premarket_live(ib: IB, top_n: int = 20) -> list[dict]:
    """Live mode: scan for pre-market gap-up candidates RIGHT NOW.
    Returns list of candidate dicts in standard format."""

    sub = ScannerSubscription(
        instrument='STK',
        locationCode='STK.US.MAJOR',  # TODO: STK.US for OTC once permissions active
        scanCode='TOP_PERC_GAIN',
        abovePrice=MIN_PRICE,
        belowPrice=MAX_PRICE,
        aboveVolume=MIN_PM_VOLUME,
        marketCapBelow=MAX_MARKET_CAP,
        numberOfRows=top_n,
    )

    results = ib.reqScannerData(sub)
    if not results:
        return []

    candidates = []
    float_cache = load_float_cache()

    for r in results:
        contract = r.contractDetails.contract
        symbol = contract.symbol

        # Get live market data for gap, volume, price
        ib.qualifyContracts(contract)
        ticker = ib.reqMktData(contract, '', False, False)
        ib.sleep(1)

        price = ticker.last or ticker.close or 0
        prev_close = ticker.close or 0
        volume = ticker.volume or 0

        if price <= 0 or prev_close <= 0:
            ib.cancelMktData(contract)
            continue

        gap_pct = (price - prev_close) / prev_close * 100

        # Get ADV for RVOL
        adv = compute_adv(ib, symbol)
        rvol = compute_rvol(volume, adv) if adv > 0 else 0

        # Float lookup
        float_shares = get_float(symbol, float_cache)
        float_m = round(float_shares / 1e6, 2) if float_shares else None
        profile = classify_profile(float_shares)

        ib.cancelMktData(contract)

        # Apply filters
        if gap_pct < MIN_GAP_PCT or gap_pct > MAX_GAP_PCT:
            continue
        if price < MIN_PRICE or price > MAX_PRICE:
            continue
        if rvol < MIN_RVOL and rvol > 0:
            continue
        if volume < MIN_PM_VOLUME:
            continue
        if profile == "skip":
            continue

        now_et = datetime.now(ET)
        discovery_time = f"{now_et.hour:02d}:{now_et.minute:02d}"

        candidates.append({
            "symbol": symbol,
            "prev_close": round(prev_close, 4),
            "pm_price": round(price, 4),
            "gap_pct": round(gap_pct, 2),
            "pm_volume": volume,
            "first_seen_et": discovery_time,
            "sim_start": discovery_time,
            "discovery_time": discovery_time,
            "discovery_method": "ibkr_live",
            "avg_daily_volume": round(adv, 0),
            "relative_volume": round(rvol, 2),
            "float_shares": float_shares,
            "float_millions": float_m,
            "profile": profile,
        })

    # Rank and return
    candidates.sort(key=rank_score, reverse=True)

    # Save to scanner_results — append mode with timestamped snapshots
    today_str = datetime.now(ET).strftime("%Y-%m-%d")
    now_et = datetime.now(ET)
    os.makedirs(SCANNER_RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(SCANNER_RESULTS_DIR, f"{today_str}.json")

    # Load existing snapshots (or start fresh)
    existing = []
    if os.path.exists(out_path):
        try:
            with open(out_path, "r") as f:
                data = json.load(f)
            # Handle both old format (flat list) and new format (list of snapshots)
            if data and isinstance(data, list) and isinstance(data[0], dict) and "timestamp" in data[0]:
                existing = data
            elif data and isinstance(data, list):
                # Old format — wrap as a legacy snapshot
                existing = [{"timestamp": "legacy", "scan_time_et": "unknown", "candidates": data}]
        except Exception:
            existing = []

    # Track symbols that dropped since last scan
    if existing:
        prev_symbols = {c["symbol"] for c in existing[-1].get("candidates", [])}
        curr_symbols = {c["symbol"] for c in candidates}
        dropped = prev_symbols - curr_symbols
        added = curr_symbols - prev_symbols
        for sym in sorted(dropped):
            print(f"  Scanner: {sym} DROPPED (was present in previous scan)", flush=True)
        for sym in sorted(added):
            print(f"  Scanner: {sym} NEW (not in previous scan)", flush=True)

    snapshot = {
        "timestamp": now_et.astimezone(pytz.utc).isoformat(),
        "scan_time_et": now_et.strftime("%H:%M:%S"),
        "candidates": candidates,
    }
    existing.append(snapshot)
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)
    print(f"  Saved: {out_path} ({len(existing)} snapshots)")

    return candidates


# ── Historical Scanner (Backtest Mode) ───────────────────────────────

def scan_historical(ib: IB, date_str: str, top_n: int = 20) -> list[dict]:
    """Backtest mode: reconstruct what the scanner would have seen on date_str.
    Uses IBKR historical data to compute gap, volume, and RVOL.
    Returns same format as scan_premarket_live()."""

    print(f"\n{'='*60}")
    print(f"  IBKR SCANNER — {date_str}")
    print(f"{'='*60}")

    # Step 1: Get scanner results for that date
    # IBKR doesn't support historical scanner requests, so we need to
    # fetch bars for a broad universe and filter ourselves.
    # Strategy: get the day's biggest gainers by fetching daily bars
    # for the date and comparing to previous close.

    # For now, use the approach of fetching PM bars for known symbols
    # from existing scanner_results (if available) as seed candidates,
    # then validate with IBKR data.

    # Check if we have existing scanner_results to use as seed
    seed_file = os.path.join(SCANNER_RESULTS_DIR, f"{date_str}.json")
    seed_symbols = set()
    if os.path.exists(seed_file):
        with open(seed_file) as f:
            seed_data = json.load(f)
        seed_symbols = {c["symbol"] for c in seed_data}
        print(f"  Seed: {len(seed_symbols)} symbols from existing scanner_results")

    # If no seed data, we can't reconstruct without a full universe scan
    # (IBKR historical scanner is not available via API)
    if not seed_symbols:
        print("  WARNING: No seed data — historical scanner requires existing scanner_results")
        print("  Use scan_premarket_live() for live mode instead")
        return []

    float_cache = load_float_cache()
    candidates = []

    for symbol in seed_symbols:
        contract = Stock(symbol, 'SMART', 'USD')
        try:
            ib.qualifyContracts(contract)
        except Exception:
            continue

        # Get the day's bars (including pre-market)
        try:
            bars = ib.reqHistoricalData(
                contract,
                endDateTime=f"{date_str.replace('-', '')} 16:00:00 US/Eastern",
                durationStr='1 D',
                barSizeSetting='1 min',
                whatToShow='TRADES',
                useRTH=False,
                formatDate=1,
            timeout=15,  # 15 second timeout
            )
            ib.sleep(0.5)
        except Exception as e:
            print(f"  {symbol}: bar fetch error — {e}")
            continue

        if not bars:
            continue

        # Get previous close from daily bar
        try:
            daily_bars = ib.reqHistoricalData(
                contract,
                endDateTime=f"{date_str.replace('-', '')} 09:30:00 US/Eastern",
                durationStr='2 D',
                barSizeSetting='1 day',
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1,
            timeout=15,  # 15 second timeout
            )
            ib.sleep(0.5)
            prev_close = daily_bars[-2].close if daily_bars and len(daily_bars) >= 2 else 0
        except Exception:
            prev_close = 0

        if prev_close <= 0:
            continue

        # Compute PM metrics from intraday bars
        pm_bars = [b for b in bars if b.date.hour < 9 or (b.date.hour == 9 and b.date.minute < 30)]
        rth_bars = [b for b in bars if not (b.date.hour < 9 or (b.date.hour == 9 and b.date.minute < 30))]

        if pm_bars:
            pm_price = pm_bars[-1].close
            pm_volume = sum(b.volume for b in pm_bars)
            first_bar_time = pm_bars[0].date.astimezone(ET)
            discovery_time = f"{first_bar_time.hour:02d}:{first_bar_time.minute:02d}"
        elif rth_bars:
            pm_price = rth_bars[0].open
            pm_volume = sum(b.volume for b in bars)
            discovery_time = "09:30"
        else:
            continue

        gap_pct = (pm_price - prev_close) / prev_close * 100

        # ADV and RVOL
        adv = compute_adv(ib, symbol, date_str)
        rvol = compute_rvol(pm_volume, adv) if adv > 0 else 0

        # Float
        float_shares = get_float(symbol, float_cache)
        float_m = round(float_shares / 1e6, 2) if float_shares else None
        profile = classify_profile(float_shares)

        # Apply filters
        if gap_pct < MIN_GAP_PCT or gap_pct > MAX_GAP_PCT:
            continue
        if pm_price < MIN_PRICE or pm_price > MAX_PRICE:
            continue
        if profile == "skip":
            continue
        # RVOL filter (but don't block unknown RVOL)
        if rvol > 0 and rvol < MIN_RVOL:
            print(f"  {symbol}: FILTERED (RVOL {rvol:.2f}x < {MIN_RVOL}x, ADV={adv:,.0f})")
            continue
        if pm_volume < MIN_PM_VOLUME:
            continue

        candidates.append({
            "symbol": symbol,
            "prev_close": round(prev_close, 4),
            "pm_price": round(pm_price, 4),
            "gap_pct": round(gap_pct, 2),
            "pm_volume": pm_volume,
            "first_seen_et": discovery_time,
            "sim_start": discovery_time,
            "discovery_time": discovery_time,
            "discovery_method": "ibkr_historical",
            "avg_daily_volume": round(adv, 0),
            "relative_volume": round(rvol, 2),
            "float_shares": float_shares,
            "float_millions": float_m,
            "profile": profile,
        })

        print(f"  ✅ {symbol}: gap={gap_pct:+.1f}% rvol={rvol:.1f}x vol={pm_volume:,} "
              f"float={float_m or 'N/A'}M price=${pm_price:.2f}")

    # Rank
    candidates.sort(key=rank_score, reverse=True)
    print(f"\n  Total candidates: {len(candidates)}")

    # Save to scanner_results
    os.makedirs(SCANNER_RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(SCANNER_RESULTS_DIR, f"{date_str}.json")
    with open(out_path, "w") as f:
        json.dump(candidates, f, indent=2)
    print(f"  Saved: {out_path}")

    return candidates


# ── CLI ──────────────────────────────────────────────────────────────

def backfill(ib: IB, start_date: str, end_date: str):
    """Regenerate scanner_results for all trading days in range using IBKR data."""
    import glob
    # Find all dates that have existing scanner_results (seed data)
    existing = sorted([
        os.path.basename(f).replace('.json', '')
        for f in glob.glob(os.path.join(SCANNER_RESULTS_DIR, '20??-??-??.json'))
    ])
    # Filter to requested range
    dates = [d for d in existing if start_date <= d <= end_date]
    print(f"Backfill: {len(dates)} dates from {start_date} to {end_date}")

    total_candidates = 0
    for i, date_str in enumerate(dates):
        print(f"\n[{i+1}/{len(dates)}] {date_str}")
        try:
            candidates = scan_historical(ib, date_str)
            total_candidates += len(candidates)
            time.sleep(1)  # Rate limit between dates
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    print(f"\n{'='*60}")
    print(f"  BACKFILL COMPLETE: {len(dates)} dates, {total_candidates} total candidates")
    print(f"{'='*60}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="IBKR Unified Scanner")
    parser.add_argument("--mode", choices=["live", "historical", "backfill"], default="live")
    parser.add_argument("--date", help="Date for historical mode (YYYY-MM-DD)")
    parser.add_argument("--start", help="Start date for backfill (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date for backfill (YYYY-MM-DD)")
    parser.add_argument("--port", type=int, default=7497, help="TWS/Gateway port")
    parser.add_argument("--client-id", type=int, default=50)
    args = parser.parse_args()

    ib = IB()
    ib.connect('127.0.0.1', args.port, clientId=args.client_id)
    print(f"Connected: {ib.isConnected()}, Account: {ib.managedAccounts()}")

    if args.mode == "live":
        candidates = scan_premarket_live(ib)
        print(f"\n{'='*60}")
        print(f"  LIVE SCANNER — {len(candidates)} candidates")
        print(f"{'='*60}")
        for c in candidates:
            print(f"  {c['symbol']}: gap={c['gap_pct']:+.1f}% rvol={c['relative_volume']:.1f}x "
                  f"vol={c['pm_volume']:,} float={c.get('float_millions', 'N/A')}M")
    elif args.mode == "historical":
        if not args.date:
            print("ERROR: --date required for historical mode")
            ib.disconnect()
            return
        candidates = scan_historical(ib, args.date)
    elif args.mode == "backfill":
        if not args.start or not args.end:
            print("ERROR: --start and --end required for backfill mode")
            ib.disconnect()
            return
        backfill(ib, args.start, args.end)

    ib.disconnect()


if __name__ == "__main__":
    main()
