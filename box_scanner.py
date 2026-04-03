"""
box_scanner.py — Multi-day range scanner for mean-reversion (Box Strategy V2).

Finds stocks trading in established 5-day ranges with tested support/resistance.
Uses multi-day S/R levels (not single-morning HOD/LOD) confirmed by multiple tests.

Two modes:
  - Live: scan_box_candidates(ib) — IBKR HOT_BY_VOLUME + multi-day filters
  - Historical: scan_box_historical(ib, date_str) — pre-built universe + daily bars

Phase 1: Scanner only. Outputs candidates to scanner_results_box/. No strategy.
"""

from __future__ import annotations

import json
import math
import os
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytz
from ib_insync import IB, Stock

ET = pytz.timezone("US/Eastern")

# ── Env vars ─────────────────────────────────────────────────────────

BOX_MIN_PRICE = float(os.getenv("WB_BOX_MIN_PRICE", "5.00"))
BOX_MAX_PRICE = float(os.getenv("WB_BOX_MAX_PRICE", "100.00"))
BOX_MIN_RANGE_PCT = float(os.getenv("WB_BOX_MIN_RANGE_PCT", "2.0"))
BOX_MAX_RANGE_PCT = float(os.getenv("WB_BOX_MAX_RANGE_PCT", "15.0"))
BOX_MIN_RANGE_DOLLARS = float(os.getenv("WB_BOX_MIN_RANGE_DOLLARS", "0.75"))
BOX_MAX_VWAP_DIST_PCT = float(os.getenv("WB_BOX_MAX_VWAP_DIST_PCT", "2.0"))
BOX_MIN_SESSION_VOL = int(os.getenv("WB_BOX_MIN_SESSION_VOL", "100000"))
BOX_SCAN_TIME_ET = os.getenv("WB_BOX_SCAN_TIME_ET", "10:00")

# Multi-day range
BOX_RANGE_LOOKBACK_DAYS = int(os.getenv("WB_BOX_RANGE_LOOKBACK_DAYS", "5"))
BOX_MIN_HIGH_TESTS = int(os.getenv("WB_BOX_MIN_HIGH_TESTS", "2"))
BOX_MIN_LOW_TESTS = int(os.getenv("WB_BOX_MIN_LOW_TESTS", "2"))
BOX_LEVEL_TOLERANCE_PCT = float(os.getenv("WB_BOX_LEVEL_TOLERANCE_PCT", "1.0"))
BOX_MAX_TODAY_ADR_UTIL = float(os.getenv("WB_BOX_MAX_TODAY_ADR_UTIL", "0.80"))
BOX_MAX_SMA_SLOPE_PCT = float(os.getenv("WB_BOX_MAX_SMA_SLOPE_PCT", "5.0"))
BOX_MAX_GAP_PCT = float(os.getenv("WB_BOX_MAX_GAP_PCT", "5.0"))
BOX_MIN_AVG_VOL_5D = int(os.getenv("WB_BOX_MIN_AVG_VOL_5D", "500000"))

# ── Output ───────────────────────────────────────────────────────────

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_results_box")

# ── ADR Cache ────────────────────────────────────────────────────────

_adr_cache: Dict[Tuple[str, str], float] = {}
_ADR_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "box_adr_cache.json")


def _load_adr_cache():
    global _adr_cache
    if os.path.exists(_ADR_CACHE_FILE):
        try:
            with open(_ADR_CACHE_FILE) as f:
                raw = json.load(f)
            _adr_cache = {tuple(k.split("|")): v for k, v in raw.items()}
        except Exception:
            _adr_cache = {}


def _save_adr_cache():
    try:
        raw = {f"{k[0]}|{k[1]}": v for k, v in _adr_cache.items()}
        os.makedirs(os.path.dirname(_ADR_CACHE_FILE), exist_ok=True)
        with open(_ADR_CACHE_FILE, "w") as f:
            json.dump(raw, f)
    except Exception as e:
        print(f"  [BOX] ADR cache save error: {e}", flush=True)


# ── Daily Bars Cache (avoid re-fetching) ─────────────────────────────

_daily_bars_cache: Dict[Tuple[str, str], list] = {}


# ── IBKR Data Fetching ──────────────────────────────────────────────

def _qualify_and_fetch_daily(ib, symbol: str, end_date: str = "") -> list:
    """Fetch 30D of daily bars from IBKR. Cached per symbol+date."""
    cache_key = (symbol, end_date)
    if cache_key in _daily_bars_cache:
        return _daily_bars_cache[cache_key]

    contract = Stock(symbol, "SMART", "USD")
    try:
        ib.qualifyContracts(contract)
        ibkr_end = f"{end_date.replace('-', '')} 23:59:59" if end_date else ""
        bars = ib.reqHistoricalData(
            contract, endDateTime=ibkr_end,
            durationStr="30 D", barSizeSetting="1 day",
            whatToShow="TRADES", useRTH=True, formatDate=1,
        )
        ib.sleep(0.5)
        result = bars or []
        _daily_bars_cache[cache_key] = result
        return result
    except Exception as e:
        print(f"  [BOX] Daily bar fetch error {symbol}: {e}", flush=True)
        return []


def _fetch_intraday_bars(ib, symbol: str, date_str: str, end_time_et: str = "10:00") -> list:
    """Fetch 1m intraday bars for today (up to scan time)."""
    contract = Stock(symbol, "SMART", "USD")
    end_dt = f"{date_str.replace('-', '')} {end_time_et}:00 US/Eastern"
    try:
        ib.qualifyContracts(contract)
        bars = ib.reqHistoricalData(
            contract, endDateTime=end_dt,
            durationStr="1 D", barSizeSetting="1 min",
            whatToShow="TRADES", useRTH=True, formatDate=2,
        )
        ib.sleep(0.5)
        return bars or []
    except Exception as e:
        print(f"  [BOX] Intraday fetch error {symbol}: {e}", flush=True)
        return []


# ── Level Test Counting ──────────────────────────────────────────────

def count_resistance_tests(daily_bars, level: float, tolerance_pct: float = 1.0) -> int:
    """Count days where bar HIGH approached the resistance level."""
    tolerance = level * (tolerance_pct / 100)
    return sum(1 for b in daily_bars if abs(b.high - level) <= tolerance)


def count_support_tests(daily_bars, level: float, tolerance_pct: float = 1.0) -> int:
    """Count days where bar LOW approached the support level."""
    tolerance = level * (tolerance_pct / 100)
    return sum(1 for b in daily_bars if abs(b.low - level) <= tolerance)


# ── Analysis ─────────────────────────────────────────────────────────

def analyze_box_candidate(symbol: str, daily_bars: list, intraday_bars: list,
                          scan_time_et: str = "10:00") -> Optional[dict]:
    """Analyze a stock for multi-day box pattern. Returns metrics dict or None."""

    if len(daily_bars) < 10:
        return None

    # Step 1: 5-day range
    lookback = BOX_RANGE_LOOKBACK_DAYS
    bars_5d = daily_bars[-lookback:]
    if len(bars_5d) < lookback:
        return None

    range_high = max(b.high for b in bars_5d)
    range_low = min(b.low for b in bars_5d)
    range_size = range_high - range_low
    if range_size <= 0 or range_low <= 0:
        return None
    range_pct = (range_size / range_low) * 100

    # Current price (last daily close or latest intraday)
    if intraday_bars:
        current_price = intraday_bars[-1].close
        today_hod = max(b.high for b in intraday_bars)
        today_lod = min(b.low for b in intraday_bars)
        session_vol = sum(b.volume for b in intraday_bars)
    else:
        current_price = daily_bars[-1].close
        today_hod = daily_bars[-1].high
        today_lod = daily_bars[-1].low
        session_vol = daily_bars[-1].volume

    # Step 2: Level tests
    high_tests = count_resistance_tests(bars_5d, range_high, BOX_LEVEL_TOLERANCE_PCT)
    low_tests = count_support_tests(bars_5d, range_low, BOX_LEVEL_TOLERANCE_PCT)

    # Step 3: Price inside range?
    inside_range = range_low <= current_price <= range_high
    range_intact = (today_hod <= range_high * 1.005) and (today_lod >= range_low * 0.995)

    # Step 4: Range position (0% = bottom, 100% = top)
    range_position_pct = ((current_price - range_low) / range_size) * 100

    # Step 5: ADR (from daily bars, cached)
    adr_bars = daily_bars[-20:] if len(daily_bars) >= 20 else daily_bars
    ranges = [b.high - b.low for b in adr_bars if b.high > b.low]
    adr_20d = sum(ranges) / len(ranges) if ranges else 0
    today_range = today_hod - today_lod
    adr_util_today = today_range / adr_20d if adr_20d > 0 else 1.0

    # Step 6: VWAP (from intraday bars)
    vwap = 0
    if intraday_bars:
        cum_tpv, cum_vol = 0.0, 0
        for b in intraday_bars:
            tp = (b.high + b.low + b.close) / 3
            cum_tpv += tp * b.volume
            cum_vol += b.volume
        vwap = cum_tpv / cum_vol if cum_vol > 0 else current_price
    vwap_dist_pct = abs(current_price - vwap) / vwap * 100 if vwap > 0 else 99

    # Step 7: 5-day avg volume
    avg_vol_5d = sum(b.volume for b in bars_5d) / len(bars_5d)

    # Step 8: SMA slope
    sma_slope_pct = None
    if len(daily_bars) >= 25:
        sma_now = sum(b.close for b in daily_bars[-20:]) / 20
        sma_5d_ago = sum(b.close for b in daily_bars[-25:-5]) / 20
        sma_slope_pct = ((sma_now - sma_5d_ago) / sma_5d_ago) * 100 if sma_5d_ago > 0 else 0

    # Step 9: Gap check
    max_gap_pct = 0
    for i in range(1, len(bars_5d)):
        if bars_5d[i - 1].close > 0:
            gap = abs(bars_5d[i].open - bars_5d[i - 1].close) / bars_5d[i - 1].close * 100
            max_gap_pct = max(max_gap_pct, gap)

    return {
        "symbol": symbol,
        "price": round(current_price, 4),
        "range_high_5d": round(range_high, 4),
        "range_low_5d": round(range_low, 4),
        "range_size": round(range_size, 4),
        "range_pct": round(range_pct, 2),
        "high_tests": high_tests,
        "low_tests": low_tests,
        "inside_range": inside_range,
        "range_intact": range_intact,
        "range_position_pct": round(range_position_pct, 1),
        "today_hod": round(today_hod, 4),
        "today_lod": round(today_lod, 4),
        "adr_20d": round(adr_20d, 4),
        "adr_util_today": round(adr_util_today, 3),
        "vwap": round(vwap, 4),
        "vwap_dist_pct": round(vwap_dist_pct, 2),
        "avg_daily_vol_5d": int(avg_vol_5d),
        "session_volume": session_vol,
        "sma_slope_pct": round(sma_slope_pct, 2) if sma_slope_pct is not None else None,
        "max_gap_pct": round(max_gap_pct, 2),
    }


# ── Filter Pipeline ──────────────────────────────────────────────────

def apply_box_filters(metrics: dict) -> Optional[dict]:
    """Apply all filters. Returns enriched dict with score, or None if filtered."""
    m = metrics

    # Price
    if not (BOX_MIN_PRICE <= m["price"] <= BOX_MAX_PRICE):
        return None

    # Range size (pct + dollar floor)
    if not (BOX_MIN_RANGE_PCT <= m["range_pct"] <= BOX_MAX_RANGE_PCT):
        return None
    min_range_dollars = max(BOX_MIN_RANGE_DOLLARS, m["price"] * (BOX_MIN_RANGE_PCT / 100))
    if m["range_size"] < min_range_dollars:
        return None

    # Level tests
    if m["high_tests"] < BOX_MIN_HIGH_TESTS:
        return None
    if m["low_tests"] < BOX_MIN_LOW_TESTS:
        return None

    # Inside range + range intact
    if not m["inside_range"] or not m["range_intact"]:
        return None

    # Today ADR utilization (want LOW — stock is quiet)
    if m["adr_util_today"] > BOX_MAX_TODAY_ADR_UTIL:
        return None

    # VWAP proximity
    if m["vwap_dist_pct"] > BOX_MAX_VWAP_DIST_PCT:
        return None

    # 5-day avg volume
    if m["avg_daily_vol_5d"] < BOX_MIN_AVG_VOL_5D:
        return None

    # Session volume
    if m["session_volume"] < BOX_MIN_SESSION_VOL:
        return None

    # SMA slope (skip if not enough data)
    if m["sma_slope_pct"] is not None and abs(m["sma_slope_pct"]) > BOX_MAX_SMA_SLOPE_PCT:
        return None

    # Gap filter
    if m["max_gap_pct"] > BOX_MAX_GAP_PCT:
        return None

    # Score
    score = compute_box_score_v2(
        m["high_tests"], m["low_tests"], m["range_position_pct"],
        m["range_pct"], m["vwap_dist_pct"], m["adr_util_today"],
    )
    m["box_score"] = score
    return m


# ── Scoring ──────────────────────────────────────────────────────────

def compute_box_score_v2(high_tests: int, low_tests: int, range_position_pct: float,
                         range_pct: float, vwap_dist_pct: float,
                         adr_util_today: float) -> float:
    """Higher = better box BUY candidate. Max ~10."""
    score = 0.0

    # Level strength (0-3) — more tests = more reliable
    level_score = min((high_tests + low_tests) / 4, 1.0) * 3.0
    score += level_score

    # Range position (0-2) — closer to bottom = better buy
    if range_position_pct <= 35:
        score += (35 - range_position_pct) / 35 * 2.0

    # Range quality (0-2) — wider = more profit potential
    score += min(range_pct / 5.0, 1.0) * 2.0

    # VWAP proximity (0-1.5)
    score += max(0, 1.5 - (vwap_dist_pct * 0.75))

    # Quiet today (0-1.5) — low today-ADR = calm
    score += max(0, 1.5 - (adr_util_today * 2.0))

    return round(score, 2)


# ── Live Scanner ─────────────────────────────────────────────────────

def scan_box_candidates(ib, scan_time_et: str = BOX_SCAN_TIME_ET) -> List[dict]:
    """Live scan: IBKR HOT_BY_VOLUME + multi-day box filters."""
    from ib_insync import ScannerSubscription

    print(f"[BOX] Scanning for multi-day box candidates at {scan_time_et} ET...", flush=True)

    sub = ScannerSubscription()
    sub.instrument = "STK"
    sub.locationCode = "STK.US.MAJOR"
    sub.scanCode = "HOT_BY_VOLUME"
    sub.numberOfRows = 100
    sub.abovePrice = BOX_MIN_PRICE
    sub.belowPrice = BOX_MAX_PRICE
    sub.aboveVolume = BOX_MIN_SESSION_VOL

    try:
        results = ib.reqScannerData(sub)
        ib.sleep(1)
    except Exception as e:
        print(f"[BOX] Scanner error: {e}", flush=True)
        return []

    print(f"[BOX] HOT_BY_VOLUME: {len(results)} stocks", flush=True)
    date_str = datetime.now(ET).strftime("%Y-%m-%d")

    return _process_universe(ib, [r.contractDetails.contract.symbol for r in results],
                             date_str, scan_time_et)


# ── Historical Scanner ───────────────────────────────────────────────

def scan_box_historical(ib, date_str: str, scan_time_et: str = "10:00",
                        universe: Optional[List[str]] = None) -> List[dict]:
    """Historical scan: universe + daily bars + intraday bars."""
    if universe is None:
        universe = _get_default_universe()

    print(f"[BOX] Historical scan {date_str} @ {scan_time_et} ET "
          f"({len(universe)} symbols)...", flush=True)

    return _process_universe(ib, universe, date_str, scan_time_et)


# ── Shared Processing ───────────────────────────────────────────────

def _process_universe(ib, symbols: List[str], date_str: str,
                      scan_time_et: str) -> List[dict]:
    """Process a list of symbols through the box filter pipeline."""
    candidates = []

    for i, symbol in enumerate(symbols):
        if (i + 1) % 20 == 0:
            print(f"  [BOX] Progress: {i+1}/{len(symbols)}...", flush=True)

        try:
            # Fetch 30D daily bars
            daily_bars = _qualify_and_fetch_daily(ib, symbol, date_str)
            if len(daily_bars) < 10:
                continue

            # Quick price check before fetching intraday
            last_close = daily_bars[-1].close
            if not (BOX_MIN_PRICE <= last_close <= BOX_MAX_PRICE):
                continue

            # Fetch intraday bars
            intraday_bars = _fetch_intraday_bars(ib, symbol, date_str, scan_time_et)

            # Analyze
            metrics = analyze_box_candidate(symbol, daily_bars, intraday_bars, scan_time_et)
            if metrics is None:
                continue

            # Filter
            result = apply_box_filters(metrics)
            if result:
                candidates.append(result)
                print(f"  [BOX] ✅ {symbol}: score={result['box_score']:.1f} "
                      f"range={result['range_pct']:.1f}% pos={result['range_position_pct']:.0f}% "
                      f"tests={result['high_tests']}H/{result['low_tests']}L "
                      f"adr_today={result['adr_util_today']:.0%}", flush=True)

        except Exception as e:
            print(f"  [BOX] Error {symbol}: {e}", flush=True)

    candidates.sort(key=lambda c: c["box_score"], reverse=True)
    print(f"[BOX] {date_str}: {len(candidates)} box candidates found", flush=True)

    _save_results(date_str, scan_time_et, candidates)
    _save_adr_cache()

    return candidates


# ── Universe ─────────────────────────────────────────────────────────

_UNIVERSE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "box_universe.txt")


def _get_default_universe() -> List[str]:
    """Load universe from box_universe.txt, or return built-in default."""
    if os.path.exists(_UNIVERSE_FILE):
        with open(_UNIVERSE_FILE) as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]

    return [
        "AAPL", "AMD", "AMZN", "BAC", "C", "CCL", "CMCSA", "CSCO",
        "DAL", "DIS", "F", "FCX", "GE", "GILD", "GM", "GOLD",
        "HOOD", "HPE", "INTC", "JD", "KEY", "KMI", "KO", "KVUE",
        "LUV", "LYFT", "MRO", "MRVL", "MU", "NEM", "NIO", "NOK",
        "NYCB", "OXY", "PARA", "PBR", "PCG", "PFE", "PLTR", "PLUG",
        "PYPL", "QCOM", "RIVN", "ROKU", "SCHW", "SHOP", "SNAP", "SOFI",
        "SQ", "SWN", "T", "TEVA", "TGT", "TFC", "UBER", "USB",
        "VZ", "WBA", "WBD", "WFC", "XOM", "ZION",
        "AAL", "ABNB", "AFRM", "AI", "ALB", "ANET", "BABA", "BILL",
        "COIN", "CRWD", "DASH", "DKNG", "DOCU", "ENPH", "ETSY",
        "FSLR", "FUBO", "GME", "GRAB", "LCID", "LI", "MARA",
        "NET", "NU", "OKTA", "OPEN", "OWL", "PANW", "PATH",
        "PINS", "RBLX", "RIOT", "SE", "SNOW", "SPOT", "TTWO",
        "U", "UAL", "UPST", "W", "WDAY", "XP", "ZM", "ZS",
    ]


# ── Output ───────────────────────────────────────────────────────────

def _save_results(date_str: str, scan_time_et: str, candidates: List[dict]):
    """Save scanner results to JSON."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    outfile = os.path.join(RESULTS_DIR, f"{date_str}.json")

    snapshot = {
        "scan_time_et": scan_time_et,
        "date": date_str,
        "scanner_version": "v2_multiday",
        "candidate_count": len(candidates),
        "candidates": candidates,
    }

    with open(outfile, "w") as f:
        json.dump(snapshot, f, indent=2)


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Box Scanner V2 — multi-day range detection")
    parser.add_argument("--date", default="", help="Historical date (YYYY-MM-DD). Empty = live.")
    parser.add_argument("--time", default=BOX_SCAN_TIME_ET, help="Scan time ET (HH:MM)")
    parser.add_argument("--port", type=int, default=4002, help="IBKR Gateway port")
    parser.add_argument("--universe", default="", help="Path to universe file")
    args = parser.parse_args()

    _load_adr_cache()
    print(f"ADR cache: {len(_adr_cache)} entries loaded", flush=True)

    ib = IB()
    ib.connect("127.0.0.1", args.port, clientId=10)

    try:
        if args.date:
            universe = None
            if args.universe:
                with open(args.universe) as f:
                    universe = [l.strip() for l in f if l.strip()]
            results = scan_box_historical(ib, args.date, args.time, universe)
        else:
            results = scan_box_candidates(ib, args.time)

        print(f"\n{'='*70}")
        print(f"  BOX SCANNER V2 RESULTS: {args.date or 'LIVE'} @ {args.time} ET")
        print(f"  Candidates: {len(results)}")
        print(f"{'='*70}")
        for i, c in enumerate(results[:10], 1):
            print(f"  {i:2d}. {c['symbol']:6s} score={c['box_score']:5.1f} "
                  f"${c['range_low_5d']:.2f}-${c['range_high_5d']:.2f} "
                  f"({c['range_pct']:.1f}%) pos={c['range_position_pct']:.0f}% "
                  f"tests={c['high_tests']}H/{c['low_tests']}L "
                  f"adr={c['adr_util_today']:.0%} vwap={c['vwap_dist_pct']:.1f}%")
    finally:
        ib.disconnect()
        _save_adr_cache()
