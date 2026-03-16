#!/usr/bin/env python3
"""
Scanner Simulator — Replays pre-market data for a given date to find
gap-up small-cap candidates, classifies them by float, and outputs
a candidate list for backtesting with simulate.py.

Usage:
    python scanner_sim.py --date 2026-01-13
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta

import requests
import pytz
import yfinance as yf
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass, AssetStatus

load_dotenv()

ET = pytz.timezone("US/Eastern")

FMP_API_KEY = os.getenv("FMP_API_KEY")

KNOWN_FLOATS = {
    "SPRC": 400_000,
    "TNMG": 1_150_000,
    "MNTS": 1_300_000,
    "ELAB": 2_100_000,
    "GWAV": 800_000,
    "VERO": 1_600_000,
    "APVO": 900_000,
    "BNAI": 3_300_000,
    "MOVE": 600_000,
    "ANPA": 700_000,
    "PAVM": 700_000,
    "ROLR": 3_600_000,
    "ACON": 700_000,
    "BDSX": 3_700_000,
    "HIND": 1_500_000,
    "MLEC": 700_000,
    "SNSE": 700_000,
    "ENVB": 500_000,
    "SHPH": 1_600_000,
    "LCFY": 1_400_000,
    "SXTP": 900_000,
    "BCTX": 1_700_000,
    "JZXN": 1_320_000,
}

LEVERAGED_ETF_BLACKLIST = {
    "MSTU", "MSTX", "MSTZ",
    "CONL", "WEBL", "SOXL", "SOXS", "TQQQ", "SQQQ",
    "UVXY", "SVXY", "NUGT", "DUST", "JNUG", "JDST",
    "LABU", "LABD", "FNGU", "FNGD", "TECL", "TECS",
    "SPXL", "SPXS", "TNA", "TZA", "UPRO", "SPXU",
    "FAS", "FAZ", "ERX", "ERY", "BOIL", "KOLD",
    "NAIL", "DRV", "CURE", "DRIP", "GUSH",
    "BITX", "BITU", "SBIT",
}


def is_junk_security(symbol: str, name: str = "") -> bool:
    """Filter out preferred stock, warrants, units, rights, and leveraged ETFs."""
    sym = symbol.upper()
    name_upper = name.upper() if name else ""
    if sym in LEVERAGED_ETF_BLACKLIST:
        return True
    junk_keywords = ["PREFERRED", "WARRANT", " UNIT", "RIGHTS",
                     "DEPOSITARY", "DEBENTURE", "CONVERTIBLE NOTE"]
    if any(kw in name_upper for kw in junk_keywords):
        return True
    if len(sym) >= 5:
        if sym[-1] == "P" and not sym[-2:] in ("LP", "EP", "AP", "IP", "OP", "UP"):
            return True
        if sym[-1] == "W":
            return True
        if sym[-1] == "U" and len(sym) >= 5:
            return True
    return False


API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

hist_client = StockHistoricalDataClient(API_KEY, API_SECRET)
trading_client = TradingClient(API_KEY, API_SECRET)

SCANNER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_results")
FLOAT_CACHE_PATH = os.path.join(SCANNER_DIR, "float_cache.json")


def load_float_cache() -> dict:
    if os.path.exists(FLOAT_CACHE_PATH):
        with open(FLOAT_CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_float_cache(cache: dict):
    with open(FLOAT_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def get_float(symbol: str, cache: dict) -> float | None:
    """Look up float shares. Priority: KNOWN_FLOATS → cache → FMP API → yfinance fallback."""
    # 1. Hardcoded known floats (most reliable for our universe)
    if symbol in KNOWN_FLOATS:
        return KNOWN_FLOATS[symbol]

    # 2. Cache (includes previously looked-up values and cached failures)
    if symbol in cache:
        return cache[symbol]

    # 3. FMP API (primary lookup)
    float_shares = None
    if FMP_API_KEY:
        try:
            url = f"https://financialmodelingprep.com/stable/shares-float?symbol={symbol}&apikey={FMP_API_KEY}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 0:
                float_shares = data[0].get("floatShares") or data[0].get("outstandingShares")
                if float_shares:
                    print(f"  [FMP] {symbol}: {float_shares/1e6:.2f}M")
        except Exception as e:
            print(f"  [FMP] {symbol}: {e}")

    # 4. yfinance fallback
    if float_shares is None:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            float_shares = info.get("floatShares")
            if float_shares:
                print(f"  [yfinance] {symbol}: {float_shares/1e6:.2f}M")
        except Exception as e:
            print(f"  [yfinance] {symbol}: {e}")

    # Cache result (even None to avoid re-lookups)
    cache[symbol] = float_shares
    save_float_cache(cache)
    time.sleep(0.5)
    return float_shares


def classify_profile(float_shares: float | None) -> str:
    """Classify stock by float: A (<5M), B (5-10M), X (>10M or unknown)."""
    if float_shares is None:
        return "X"
    millions = float_shares / 1_000_000
    if millions < 5:
        return "A"
    elif millions <= 10:
        return "B"
    else:
        return "skip"


def get_all_active_symbols() -> list[str]:
    """Get all active US equity symbols from Alpaca."""
    request = GetAssetsRequest(
        asset_class=AssetClass.US_EQUITY,
        status=AssetStatus.ACTIVE,
    )
    assets = trading_client.get_all_assets(request)
    symbols = []
    filtered_count = 0
    for a in assets:
        # Note: tradable=False includes OTC stocks (e.g. VERO) that still have
        # market data on Alpaca. For backtesting we want these candidates.
        # The fractionable filter is also removed — it was blocking micro-caps.
        if any(c in a.symbol for c in ['.', '/']):
            continue
        asset_name = getattr(a, 'name', '') or ''
        if is_junk_security(a.symbol, asset_name):
            filtered_count += 1
            continue
        symbols.append(a.symbol)
    print(f"  Filtered {filtered_count} junk securities (preferred/warrants/leveraged ETFs)")
    return symbols


def fetch_prev_close(symbols: list[str], date_str: str) -> dict[str, float]:
    """Fetch previous trading day close for all symbols via 1-day bars."""
    date = datetime.strptime(date_str, "%Y-%m-%d")
    # Look back up to 7 calendar days to find prev trading day
    start = date - timedelta(days=7)

    prev_close = {}
    chunk_size = 1000
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i + chunk_size]
        try:
            request = StockBarsRequest(
                symbol_or_symbols=chunk,
                timeframe=TimeFrame.Day,
                start=ET.localize(datetime.combine(start.date(), datetime.min.time())),
                end=ET.localize(datetime.combine(date.date(), datetime.min.time())),
            )
            bars = hist_client.get_stock_bars(request)
            for sym, bar_list in bars.data.items():
                if bar_list:
                    # Filter to bars strictly before the target date
                    target_date = date.date()
                    prev_bars = [b for b in bar_list
                                 if b.timestamp.astimezone(ET).date() < target_date]
                    if prev_bars:
                        prev_close[sym] = prev_bars[-1].close
        except Exception as e:
            print(f"  [prev_close chunk {i}] Error: {e}")

    return prev_close


def fetch_premarket_bars(symbols: list[str], date_str: str) -> dict[str, list]:
    """Fetch pre-market 1-min bars (4:00-7:15 AM ET) for all symbols."""
    date = datetime.strptime(date_str, "%Y-%m-%d")
    pm_start = ET.localize(datetime.combine(date.date(), datetime.min.time().replace(hour=4, minute=0)))
    pm_end = ET.localize(datetime.combine(date.date(), datetime.min.time().replace(hour=7, minute=15)))

    pm_bars = {}
    chunk_size = 1000
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i + chunk_size]
        try:
            request = StockBarsRequest(
                symbol_or_symbols=chunk,
                timeframe=TimeFrame.Minute,
                start=pm_start,
                end=pm_end,
            )
            bars = hist_client.get_stock_bars(request)
            for sym, bar_list in bars.data.items():
                if bar_list:
                    pm_bars[sym] = bar_list
        except Exception as e:
            print(f"  [pm_bars chunk {i}] Error: {e}")

    return pm_bars


def compute_gap_candidates(prev_close: dict, pm_bars: dict) -> list[dict]:
    """Find stocks gapping up >= 5% with price $2-$20."""
    candidates = []
    for sym, bars in pm_bars.items():
        if sym not in prev_close:
            continue
        pc = prev_close[sym]
        if pc <= 0:
            continue

        # Use the latest pre-market price
        pm_price = bars[-1].close
        gap_pct = (pm_price - pc) / pc * 100

        if gap_pct < 5:
            continue
        if pm_price < 2.0 or pm_price > 20.0:
            continue

        # Determine first activity time (first bar with volume)
        first_time = None
        for bar in bars:
            if bar.volume and bar.volume > 0:
                bar_time = bar.timestamp.astimezone(ET)
                first_time = bar_time
                break

        # Determine sim_start based on first activity time
        if first_time is None:
            sim_start = "07:00"
        elif first_time.hour < 7:
            sim_start = "07:00"
        elif first_time.hour == 7 and first_time.minute <= 30:
            sim_start = f"{first_time.hour:02d}:{first_time.minute:02d}"
        else:
            continue  # First seen after 7:30 AM — skip

        # Pre-market volume (total volume across all PM bars)
        pm_volume = sum(b.volume for b in bars if b.volume)

        candidates.append({
            "symbol": sym,
            "prev_close": round(pc, 4),
            "pm_price": round(pm_price, 4),
            "gap_pct": round(gap_pct, 2),
            "pm_volume": pm_volume,
            "first_seen_et": first_time.strftime("%H:%M") if first_time else "N/A",
            "sim_start": sim_start,
        })

    # Sort by gap% descending
    candidates.sort(key=lambda x: x["gap_pct"], reverse=True)
    return candidates


def find_late_movers(prev_close: dict, existing_symbols: set, date_str: str) -> list[dict]:
    """Legacy: Find stocks that gap at open but had zero pre-market bars.
    Kept for backward compatibility. Use find_emerging_movers() instead.
    """
    check_symbols = list(set(prev_close.keys()) - existing_symbols)
    if not check_symbols:
        return []

    date = datetime.strptime(date_str, "%Y-%m-%d")
    rth_start = ET.localize(datetime.combine(date.date(), datetime.min.time().replace(hour=9, minute=30)))
    rth_end = ET.localize(datetime.combine(date.date(), datetime.min.time().replace(hour=9, minute=35)))

    late_movers = []
    chunk_size = 1000
    for i in range(0, len(check_symbols), chunk_size):
        chunk = check_symbols[i:i + chunk_size]
        try:
            request = StockBarsRequest(
                symbol_or_symbols=chunk,
                timeframe=TimeFrame.Minute,
                start=rth_start,
                end=rth_end,
            )
            bars = hist_client.get_stock_bars(request)
            for sym, bar_list in bars.data.items():
                if not bar_list:
                    continue
                pc = prev_close.get(sym)
                if not pc or pc <= 0:
                    continue
                open_price = bar_list[0].open
                gap_pct = (open_price - pc) / pc * 100
                if gap_pct < 5 or open_price < 2.0 or open_price > 20.0:
                    continue
                late_movers.append({
                    "symbol": sym,
                    "prev_close": round(pc, 4),
                    "pm_price": round(open_price, 4),
                    "gap_pct": round(gap_pct, 2),
                    "pm_volume": sum(b.volume for b in bar_list if b.volume),
                    "first_seen_et": "09:30",
                    "sim_start": "09:30",
                })
        except Exception as e:
            print(f"  [late_movers chunk {i}] Error: {e}")

    late_movers.sort(key=lambda x: x["gap_pct"], reverse=True)
    return late_movers


# Continuous scanning checkpoints (all times ET)
SCAN_CHECKPOINTS = [
    ("08:00", 8, 0),
    ("08:30", 8, 30),
    ("09:00", 9, 0),
    ("09:30", 9, 30),
    ("10:00", 10, 0),
    ("10:30", 10, 30),
]

# Previous checkpoint for each (to define the fetch window)
_CHECKPOINT_WINDOWS = [
    # (label, start_hour, start_min, end_hour, end_min)
    ("08:00", 7, 15, 8, 0),
    ("08:30", 8, 0, 8, 30),
    ("09:00", 8, 30, 9, 0),
    ("09:30", 9, 0, 9, 30),
    ("10:00", 9, 30, 10, 0),
    ("10:30", 10, 0, 10, 30),
]


def find_emerging_movers(prev_close: dict, existing_candidates: list[dict],
                         date_str: str) -> list[dict]:
    """Continuous re-scan: check for new gap candidates at multiple checkpoints.

    Scans at 8:00, 8:30, 9:00, 9:30, 10:00, 10:30 AM ET for stocks that
    have gapped >= 5% vs prev_close but weren't caught by the original
    7:15 AM premarket scan. This catches mid-morning catalysts like ROLR
    on Jan 14 (news at 8:18 AM, +340% gap).

    Args:
        prev_close: {symbol: prev_close_price} for all active symbols
        existing_candidates: list of candidate dicts already found by premarket scan
        date_str: date string YYYY-MM-DD

    Returns:
        list of new candidate dicts with discovery_time and discovery_method fields
    """
    date = datetime.strptime(date_str, "%Y-%m-%d")
    found_symbols = {c["symbol"] for c in existing_candidates}
    all_new = []

    for label, win_start_h, win_start_m, win_end_h, win_end_m in _CHECKPOINT_WINDOWS:
        # Skip symbols already found
        check_symbols = list(set(prev_close.keys()) - found_symbols)
        if not check_symbols:
            break

        win_start = ET.localize(datetime.combine(
            date.date(), datetime.min.time().replace(hour=win_start_h, minute=win_start_m)))
        win_end = ET.localize(datetime.combine(
            date.date(), datetime.min.time().replace(hour=win_end_h, minute=win_end_m)))

        checkpoint_new = []
        chunk_size = 1000
        for i in range(0, len(check_symbols), chunk_size):
            chunk = check_symbols[i:i + chunk_size]
            try:
                request = StockBarsRequest(
                    symbol_or_symbols=chunk,
                    timeframe=TimeFrame.Minute,
                    start=win_start,
                    end=win_end,
                )
                bars = hist_client.get_stock_bars(request)
                for sym, bar_list in bars.data.items():
                    if not bar_list or sym in found_symbols:
                        continue
                    pc = prev_close.get(sym)
                    if not pc or pc <= 0:
                        continue

                    # Use the latest bar's close as current price
                    latest_price = bar_list[-1].close
                    gap_pct = (latest_price - pc) / pc * 100

                    if gap_pct < 5:
                        continue
                    if latest_price < 2.0 or latest_price > 20.0:
                        continue

                    vol = sum(b.volume for b in bar_list if b.volume)

                    checkpoint_new.append({
                        "symbol": sym,
                        "prev_close": round(pc, 4),
                        "pm_price": round(latest_price, 4),
                        "gap_pct": round(gap_pct, 2),
                        "pm_volume": vol,
                        "first_seen_et": label,
                        "sim_start": label,
                        "discovery_time": label,
                        "discovery_method": "rescan",
                    })
                    found_symbols.add(sym)
            except Exception as e:
                print(f"  [rescan {label} chunk {i}] Error: {e}")

        if checkpoint_new:
            checkpoint_new.sort(key=lambda x: x["gap_pct"], reverse=True)
            for c in checkpoint_new:
                print(f"         RESCAN [{label}]: {c['symbol']} gap={c['gap_pct']:+.1f}% ${c['pm_price']:.2f}")
            all_new.extend(checkpoint_new)

    return all_new


def run_scanner(date_str: str):
    print(f"\n{'=' * 60}")
    print(f"  SCANNER SIMULATOR — {date_str}")
    print(f"{'=' * 60}")

    # Step 1: Get all active symbols
    print("\n  [1/5] Fetching active US equity symbols...")
    all_symbols = get_all_active_symbols()
    print(f"         {len(all_symbols)} symbols found")

    # Step 2: Fetch previous day close
    print("  [2/5] Fetching previous-day close...")
    prev_close = fetch_prev_close(all_symbols, date_str)
    print(f"         {len(prev_close)} symbols with prev close")

    # Step 3: Fetch pre-market bars
    print("  [3/5] Fetching pre-market bars (4:00-7:15 AM ET)...")
    pm_bars = fetch_premarket_bars(all_symbols, date_str)
    print(f"         {len(pm_bars)} symbols with PM activity")

    # Step 4: Compute gap candidates
    print("  [4/5] Computing gap candidates (>=5%, $2-$20)...")
    candidates = compute_gap_candidates(prev_close, pm_bars)
    print(f"         {len(candidates)} raw candidates")

    # Tag premarket candidates with discovery metadata
    for c in candidates:
        c["discovery_time"] = c.get("first_seen_et", "premarket")
        c["discovery_method"] = "premarket"

    # Step 4b: Continuous re-scan (8:00, 8:30, 9:00, 9:30, 10:00, 10:30 AM ET)
    print(f"  [4b/5] Running continuous re-scan (8:00 AM - 10:30 AM ET)...")
    emerging = find_emerging_movers(prev_close, candidates, date_str)
    print(f"         {len(emerging)} emerging movers found across all checkpoints")
    candidates.extend(emerging)
    # Re-sort all candidates by gap% descending
    candidates.sort(key=lambda x: x["gap_pct"], reverse=True)

    # Step 5: Look up float and classify
    print("  [5/5] Looking up float (known → cache → FMP → yfinance)...")
    float_cache = load_float_cache()
    final_candidates = []

    for c in candidates:
        sym = c["symbol"]
        float_shares = get_float(sym, float_cache)
        profile = classify_profile(float_shares)

        if profile == "skip":
            print(f"         {sym}: float {float_shares/1e6:.1f}M → skip (>10M)")
            continue

        float_m = round(float_shares / 1e6, 2) if float_shares else None
        c["float_shares"] = float_shares
        c["float_millions"] = float_m
        c["profile"] = profile
        final_candidates.append(c)
        label = f"{float_m}M" if float_m else "unknown"
        print(f"         {sym}: gap {c['gap_pct']:+.1f}%, ${c['pm_price']:.2f}, float {label} → {profile}")

    # Output JSON
    json_path = os.path.join(SCANNER_DIR, f"{date_str}.json")
    with open(json_path, "w") as f:
        json.dump(final_candidates, f, indent=2)

    # Output text summary
    txt_path = os.path.join(SCANNER_DIR, f"{date_str}.txt")
    with open(txt_path, "w") as f:
        f.write(f"Scanner Results — {date_str}\n")
        f.write(f"{'=' * 80}\n")
        f.write(f"{'Symbol':<8} {'Gap%':>7} {'Price':>7} {'Float':>8} {'Profile':>7} {'SimStart':>8} {'PM Vol':>10} {'Discovery':>10} {'Method':>10}\n")
        f.write(f"{'─'*8} {'─'*7} {'─'*7} {'─'*8} {'─'*7} {'─'*8} {'─'*10} {'─'*10} {'─'*10}\n")
        for c in final_candidates:
            float_str = f"{c['float_millions']}M" if c['float_millions'] else "N/A"
            disc_time = c.get("discovery_time", "premarket")
            disc_method = c.get("discovery_method", "premarket")
            f.write(
                f"{c['symbol']:<8} {c['gap_pct']:>+7.1f}% {c['pm_price']:>7.2f} {float_str:>8} "
                f"{c['profile']:>7} {c['sim_start']:>8} {c['pm_volume']:>10,} {disc_time:>10} {disc_method:>10}\n"
            )
        f.write(f"\nTotal candidates: {len(final_candidates)}\n")
        # Summary by discovery method
        premarket_count = sum(1 for c in final_candidates if c.get("discovery_method") == "premarket")
        rescan_count = sum(1 for c in final_candidates if c.get("discovery_method") == "rescan")
        f.write(f"  Premarket (7:15 AM): {premarket_count}\n")
        f.write(f"  Continuous rescan:   {rescan_count}\n")

    print(f"\n  Results saved:")
    print(f"    {json_path}")
    print(f"    {txt_path}")
    print(f"  Total candidates: {len(final_candidates)}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Scanner Simulator — find gap-up candidates for a given date")
    parser.add_argument("--date", required=True, help="Date to scan (YYYY-MM-DD)")
    args = parser.parse_args()
    run_scanner(args.date)


if __name__ == "__main__":
    main()
