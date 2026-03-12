#!/usr/bin/env python3
"""
Diagnose why Ross's stocks did/didn't appear on scanner.
Checks Alpaca data availability, prev close, premarket price, gap%, price range, float.
"""

import json
import os
import time
from datetime import datetime, timedelta

import pytz
import requests
import yfinance as yf
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

load_dotenv()

ET = pytz.timezone("US/Eastern")
FMP_API_KEY = os.getenv("FMP_API_KEY")
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
hist_client = StockHistoricalDataClient(API_KEY, API_SECRET)

FLOAT_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_results", "float_cache.json")

def load_float_cache():
    if os.path.exists(FLOAT_CACHE_PATH):
        with open(FLOAT_CACHE_PATH) as f:
            return json.load(f)
    return {}

def get_float_info(symbol, cache):
    """Get float from cache, FMP, or yfinance."""
    if symbol in cache and cache[symbol] is not None:
        return cache[symbol], "cache"

    # FMP
    if FMP_API_KEY:
        try:
            url = f"https://financialmodelingprep.com/stable/shares-float?symbol={symbol}&apikey={FMP_API_KEY}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 0:
                fs = data[0].get("floatShares") or data[0].get("outstandingShares")
                if fs:
                    return fs, "FMP"
        except Exception as e:
            print(f"  [FMP error for {symbol}]: {e}")

    # yfinance
    try:
        info = yf.Ticker(symbol).info
        fs = info.get("floatShares")
        if fs:
            return fs, "yfinance"
    except Exception as e:
        print(f"  [yfinance error for {symbol}]: {e}")

    return None, "not_found"


def diagnose_ticker(symbol, date_str):
    """Check a single ticker on a single date."""
    print(f"\n{'='*60}")
    print(f"  DIAGNOSING: {symbol} on {date_str}")
    print(f"{'='*60}")

    date = datetime.strptime(date_str, "%Y-%m-%d")
    result = {
        "symbol": symbol,
        "date": date_str,
        "has_alpaca_data": False,
        "prev_close": None,
        "pm_price": None,
        "gap_pct": None,
        "price_filter": None,
        "gap_filter": None,
        "float_shares": None,
        "float_source": None,
        "float_filter": None,
        "first_pm_bar": None,
        "pm_volume": None,
        "pm_high": None,
        "notes": [],
    }

    # Step 1: Fetch prev close (look back 7 days)
    start = date - timedelta(days=7)
    try:
        request = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame.Day,
            start=ET.localize(datetime.combine(start.date(), datetime.min.time())),
            end=ET.localize(datetime.combine(date.date(), datetime.min.time())),
        )
        bars = hist_client.get_stock_bars(request)
        if symbol in bars.data and bars.data[symbol]:
            prev_bar = bars.data[symbol][-1]
            result["prev_close"] = prev_bar.close
            print(f"  Prev close: ${prev_bar.close:.4f} (from {prev_bar.timestamp.date()})")
        else:
            result["notes"].append("No prev close data in Alpaca")
            print(f"  NO prev close data found")
    except Exception as e:
        result["notes"].append(f"Prev close error: {e}")
        print(f"  Prev close error: {e}")

    # Step 2: Fetch premarket bars (4:00 AM - 9:30 AM to see full picture)
    pm_start = ET.localize(datetime.combine(date.date(), datetime.min.time().replace(hour=4, minute=0)))
    pm_end = ET.localize(datetime.combine(date.date(), datetime.min.time().replace(hour=9, minute=30)))

    try:
        request = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame.Minute,
            start=pm_start,
            end=pm_end,
        )
        bars = hist_client.get_stock_bars(request)
        if symbol in bars.data and bars.data[symbol]:
            bar_list = bars.data[symbol]
            result["has_alpaca_data"] = True

            # Find first bar with volume
            first_vol_bar = None
            for b in bar_list:
                if b.volume and b.volume > 0:
                    first_vol_bar = b
                    break

            if first_vol_bar:
                ft = first_vol_bar.timestamp.astimezone(ET)
                result["first_pm_bar"] = ft.strftime("%H:%M")
                print(f"  First PM bar with volume: {ft.strftime('%H:%M')} ET")

            # Use latest PM bar close as PM price (up to 7:15 for scanner comparison)
            pm_bars_715 = [b for b in bar_list if b.timestamp.astimezone(ET).hour < 7 or
                          (b.timestamp.astimezone(ET).hour == 7 and b.timestamp.astimezone(ET).minute <= 15)]

            if pm_bars_715:
                latest = pm_bars_715[-1]
                result["pm_price"] = latest.close
                result["pm_high"] = max(b.high for b in pm_bars_715)
                result["pm_volume"] = sum(b.volume for b in pm_bars_715 if b.volume)
                print(f"  PM price (by 7:15): ${latest.close:.4f}")
                print(f"  PM high (by 7:15):  ${result['pm_high']:.4f}")
                print(f"  PM volume (by 7:15): {result['pm_volume']:,.0f}")
            else:
                # Check if there are bars after 7:15
                if bar_list:
                    latest = bar_list[-1]
                    lt = latest.timestamp.astimezone(ET)
                    result["pm_price"] = latest.close
                    result["pm_high"] = max(b.high for b in bar_list)
                    result["pm_volume"] = sum(b.volume for b in bar_list if b.volume)
                    result["notes"].append(f"No PM bars before 7:15 — first bar at {lt.strftime('%H:%M')}")
                    print(f"  No PM bars before 7:15 — first at {lt.strftime('%H:%M')}")
                    print(f"  Price at first bar: ${latest.close:.4f}")

            # Show all PM bars for context
            print(f"  Total PM bars (4:00-9:30): {len(bar_list)}")
            for b in bar_list[:5]:
                bt = b.timestamp.astimezone(ET)
                print(f"    {bt.strftime('%H:%M')} O=${b.open:.2f} H=${b.high:.2f} L=${b.low:.2f} C=${b.close:.2f} V={b.volume}")
            if len(bar_list) > 5:
                print(f"    ... ({len(bar_list)-5} more bars)")
                # Show last few bars too
                for b in bar_list[-3:]:
                    bt = b.timestamp.astimezone(ET)
                    print(f"    {bt.strftime('%H:%M')} O=${b.open:.2f} H=${b.high:.2f} L=${b.low:.2f} C=${b.close:.2f} V={b.volume}")
        else:
            result["notes"].append("NO Alpaca premarket data — likely data gap")
            print(f"  NO premarket data in Alpaca")
    except Exception as e:
        result["notes"].append(f"PM bars error: {e}")
        print(f"  PM bars error: {e}")

    # Step 3: Also fetch regular hours bars to see what happened during the day
    reg_start = ET.localize(datetime.combine(date.date(), datetime.min.time().replace(hour=9, minute=30)))
    reg_end = ET.localize(datetime.combine(date.date(), datetime.min.time().replace(hour=12, minute=0)))

    try:
        request = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame.Minute,
            start=reg_start,
            end=reg_end,
        )
        bars = hist_client.get_stock_bars(request)
        if symbol in bars.data and bars.data[symbol]:
            bar_list = bars.data[symbol]
            print(f"  Regular hours bars (9:30-12:00): {len(bar_list)}")
            if bar_list:
                open_price = bar_list[0].open
                high_price = max(b.high for b in bar_list)
                low_price = min(b.low for b in bar_list)
                close_price = bar_list[-1].close
                total_vol = sum(b.volume for b in bar_list if b.volume)
                print(f"    Open=${open_price:.2f} High=${high_price:.2f} Low=${low_price:.2f} Close=${close_price:.2f}")
                print(f"    Total volume: {total_vol:,.0f}")
                result["reg_open"] = open_price
                result["reg_high"] = high_price
        else:
            result["notes"].append("No regular hours data either")
            print(f"  No regular hours data in Alpaca")
    except Exception as e:
        print(f"  Regular hours error: {e}")

    # Step 4: Compute gap % and check filters
    if result["prev_close"] and result["pm_price"]:
        gap = (result["pm_price"] - result["prev_close"]) / result["prev_close"] * 100
        result["gap_pct"] = round(gap, 2)
        print(f"\n  Gap %: {gap:+.2f}%")

        # Scanner sim uses >=10% gap, live_scanner uses >=5%
        result["gap_filter_5pct"] = "PASS" if gap >= 5 else f"FAIL (need >=5%, got {gap:.1f}%)"
        result["gap_filter_10pct"] = "PASS" if gap >= 10 else f"FAIL (need >=10%, got {gap:.1f}%)"
        print(f"  Gap filter (>=5%):  {result['gap_filter_5pct']}")
        print(f"  Gap filter (>=10%): {result['gap_filter_10pct']}")

        # Price filter
        price = result["pm_price"]
        result["price_filter"] = "PASS" if 2.0 <= price <= 20.0 else f"FAIL (${price:.2f} outside $2-$20)"
        print(f"  Price filter ($2-$20): {result['price_filter']}")

    # Step 5: Float check
    cache = load_float_cache()
    float_shares, source = get_float_info(symbol, cache)
    result["float_shares"] = float_shares
    result["float_source"] = source

    if float_shares:
        float_m = float_shares / 1_000_000
        result["float_millions"] = round(float_m, 2)
        # Live scanner filter: 100K-50M
        if 100_000 <= float_shares <= 50_000_000:
            result["float_filter"] = "PASS"
        else:
            result["float_filter"] = f"FAIL ({float_m:.2f}M outside 100K-50M)"
        # Scanner sim profile
        if float_m < 5:
            result["profile"] = "A"
        elif float_m <= 10:
            result["profile"] = "B"
        else:
            result["profile"] = "skip (>10M)"
        print(f"  Float: {float_m:.2f}M (source: {source}) → {result['float_filter']}, profile: {result.get('profile', 'N/A')}")
    else:
        result["float_filter"] = "FAIL (unknown float → rejected)"
        result["profile"] = "X (unknown)"
        print(f"  Float: UNKNOWN (source: {source}) → rejected by scanner")

    return result


# Ross's tickers to diagnose
TICKERS = [
    ("FTEEL", "2025-11-06"),   # +$3,224
    ("OPTX",  "2026-01-06"),   # +$3,600
    ("ELAB",  "2026-01-06"),   # +$3,500
    ("SPCB",  "2025-01-02"),   # +$2,400
    ("CERO",  "2026-01-06"),   # untested
    ("AEI",   "2025-01-02"),   # +$852
    ("ALM",   "2026-01-06"),   # +$500
    ("LNAI",  "2025-11-05"),   # -$3,926
    ("CCTG",  "2025-11-05"),   # -$900
    ("NUAAI", "2025-11-06"),   # -$400
]


if __name__ == "__main__":
    results = []
    for sym, dt in TICKERS:
        r = diagnose_ticker(sym, dt)
        results.append(r)
        time.sleep(0.3)  # rate limit

    # Save results
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_diagnosis_raw.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n\nResults saved to {out_path}")
