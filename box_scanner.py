"""
box_scanner.py — Range-bound stock scanner for mean-reversion (Box Strategy).

Finds stocks that have used 60%+ of their ADR by mid-morning and are settling
into a tradeable range. Completely separate from the momentum/squeeze scanner.

Two modes:
  - Live: scan_box_candidates(ib, scan_time_et) — uses IBKR HOT_BY_VOLUME + custom filters
  - Historical: scan_box_historical(ib, date_str, scan_time_et) — uses cached/fetched 1m bars

Phase 1: Scanner only. Outputs candidates to scanner_results_box/. No strategy, no trades.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytz

ET = pytz.timezone("US/Eastern")

# ── Env vars ─────────────────────────────────────────────────────────

BOX_MIN_PRICE = float(os.getenv("WB_BOX_MIN_PRICE", "5.00"))
BOX_MAX_PRICE = float(os.getenv("WB_BOX_MAX_PRICE", "100.00"))
BOX_MIN_RANGE_PCT = float(os.getenv("WB_BOX_MIN_RANGE_PCT", "2.0"))
BOX_MAX_RANGE_PCT = float(os.getenv("WB_BOX_MAX_RANGE_PCT", "15.0"))
BOX_MIN_ADR_UTIL = float(os.getenv("WB_BOX_MIN_ADR_UTIL", "0.60"))
BOX_MAX_VWAP_DIST_PCT = float(os.getenv("WB_BOX_MAX_VWAP_DIST_PCT", "3.0"))
BOX_MIN_SESSION_VOL = int(os.getenv("WB_BOX_MIN_SESSION_VOL", "200000"))
BOX_MIN_HOD_AGE_MIN = int(os.getenv("WB_BOX_MIN_HOD_AGE_MIN", "15"))
BOX_MIN_LOD_AGE_MIN = int(os.getenv("WB_BOX_MIN_LOD_AGE_MIN", "15"))
BOX_VOL_DECLINE_MAX = float(os.getenv("WB_BOX_VOL_DECLINE_MAX", "0.60"))
BOX_MIN_STABILITY = float(os.getenv("WB_BOX_MIN_STABILITY", "0.50"))
BOX_SCAN_TIME_ET = os.getenv("WB_BOX_SCAN_TIME_ET", "10:00")

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


def compute_20d_adr(ib, symbol: str, end_date: str = "") -> float:
    """Compute 20-day Average Daily Range from IBKR historical daily bars."""
    from ib_insync import Stock
    contract = Stock(symbol, "SMART", "USD")
    try:
        # IBKR wants yyyymmdd HH:mm:ss format
        ibkr_end = f"{end_date.replace('-', '')} 23:59:59" if end_date else ""
        ib.qualifyContracts(contract)
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=ibkr_end,
            durationStr="30 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
        ib.sleep(0.5)  # Rate limit pacing
        if not bars or len(bars) < 5:
            return 0.0
        ranges = [b.high - b.low for b in bars[-20:] if b.high > b.low]
        return sum(ranges) / len(ranges) if ranges else 0.0
    except Exception as e:
        print(f"  [BOX] ADR fetch error {symbol}: {e}", flush=True)
        return 0.0


def compute_adr_cached(ib, symbol: str, date_str: str = "") -> float:
    """Compute 20-day ADR with per-date caching."""
    if not date_str:
        date_str = datetime.now(ET).strftime("%Y-%m-%d")
    cache_key = (symbol, date_str)
    if cache_key in _adr_cache:
        return _adr_cache[cache_key]
    adr = compute_20d_adr(ib, symbol, end_date=date_str)
    _adr_cache[cache_key] = adr
    return adr


# ── Intraday Data ────────────────────────────────────────────────────

def get_intraday_bars(ib, symbol: str, date_str: str, end_time_et: str = "12:00") -> list:
    """Fetch 1m intraday bars from IBKR for a specific date up to end_time."""
    from ib_insync import Stock
    contract = Stock(symbol, "SMART", "USD")
    # Build end datetime string for IBKR (yyyymmdd HH:mm:ss tz)
    end_dt = f"{date_str.replace('-', '')} {end_time_et}:00 US/Eastern"
    try:
        ib.qualifyContracts(contract)
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_dt,
            durationStr="1 D",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=2,  # UTC datetime objects
        )
        ib.sleep(1)  # Pacing: 1s between requests
        return bars or []
    except Exception as e:
        print(f"  [BOX] Intraday fetch error {symbol}: {e}", flush=True)
        ib.sleep(1)
        return []


def analyze_intraday(bars, scan_time_et: str = "10:00") -> Optional[dict]:
    """Analyze intraday bars and compute all box metrics.

    Args:
        bars: list of IBKR bars (must be 1-min, regular hours)
        scan_time_et: "HH:MM" ET — only consider bars up to this time

    Returns:
        dict with all metrics, or None if insufficient data
    """
    if not bars or len(bars) < 10:
        return None

    # Parse scan time
    scan_h, scan_m = int(scan_time_et.split(":")[0]), int(scan_time_et.split(":")[1])

    # Filter bars up to scan time
    filtered = []
    for b in bars:
        bar_et = b.date.astimezone(ET) if hasattr(b.date, 'astimezone') else b.date
        if hasattr(bar_et, 'hour'):
            if bar_et.hour < scan_h or (bar_et.hour == scan_h and bar_et.minute <= scan_m):
                filtered.append(b)

    if len(filtered) < 5:
        return None

    # Basic metrics
    hod = max(b.high for b in filtered)
    lod = min(b.low for b in filtered)
    last_price = filtered[-1].close
    session_vol = sum(b.volume for b in filtered)
    intraday_range = hod - lod

    if intraday_range <= 0 or lod <= 0:
        return None

    range_pct = (intraday_range / lod) * 100

    # VWAP
    cum_tpv = 0.0
    cum_vol = 0
    for b in filtered:
        tp = (b.high + b.low + b.close) / 3
        cum_tpv += tp * b.volume
        cum_vol += b.volume
    vwap = cum_tpv / cum_vol if cum_vol > 0 else last_price
    vwap_dist_pct = abs(last_price - vwap) / vwap * 100 if vwap > 0 else 99

    # HOD/LOD age (minutes since last new high/low)
    last_hod_idx = 0
    last_lod_idx = 0
    running_high = 0
    running_low = float('inf')
    for i, b in enumerate(filtered):
        if b.high >= running_high:
            running_high = b.high
            last_hod_idx = i
        if b.low <= running_low:
            running_low = b.low
            last_lod_idx = i
    hod_age_min = len(filtered) - 1 - last_hod_idx
    lod_age_min = len(filtered) - 1 - last_lod_idx

    # Volume decline: first 15 min vs last 15 min before scan
    # Regular hours start at bar index 0 (RTH=True bars)
    early_bars = filtered[:15]
    recent_bars = filtered[-15:]
    early_vol = sum(b.volume for b in early_bars) if early_bars else 1
    recent_vol = sum(b.volume for b in recent_bars) if recent_bars else 1
    vol_decline = recent_vol / early_vol if early_vol > 0 else 1.0

    # Stability: 1 - (stdev of last 30 closes / range)
    recent_closes = [b.close for b in filtered[-30:]]
    if len(recent_closes) > 1 and intraday_range > 0:
        stdev = statistics.stdev(recent_closes)
        stability = 1 - (stdev / intraday_range)
    else:
        stability = 0.0

    return {
        "price": last_price,
        "hod": hod,
        "lod": lod,
        "range_pct": round(range_pct, 2),
        "intraday_range": round(intraday_range, 4),
        "vwap": round(vwap, 4),
        "vwap_dist_pct": round(vwap_dist_pct, 2),
        "session_volume": session_vol,
        "hod_age_min": hod_age_min,
        "lod_age_min": lod_age_min,
        "vol_decline_ratio": round(vol_decline, 3),
        "stability": round(stability, 3),
        "bar_count": len(filtered),
    }


# ── Scoring ──────────────────────────────────────────────────────────

def compute_box_score(adr_util: float, vwap_dist_pct: float,
                      vol_decline: float, stability: float,
                      hod_age_min: int, lod_age_min: int) -> float:
    """Higher = better box candidate. Max ~10."""
    score = 0.0

    # ADR utilization (0-3) — most important
    score += min(adr_util, 1.0) * 3.0

    # VWAP proximity (0-2) — closer = better
    score += max(0, 2.0 - (vwap_dist_pct * 0.67))

    # Volume decline (0-1.5) — lower = better
    score += max(0, 1.5 - (vol_decline * 2.5))

    # Stability (0-2)
    score += max(0, stability) * 2.0

    # Level age bonus (0-1.5) — older HOD/LOD = more established
    age_min = min(hod_age_min, lod_age_min)
    score += min(age_min / 60, 1.0) * 1.5

    return round(score, 2)


# ── Filter Pipeline ──────────────────────────────────────────────────

def apply_box_filters(symbol: str, metrics: dict, adr: float) -> Optional[dict]:
    """Apply all Tier 1 + Tier 2 filters. Returns enriched dict or None if filtered."""

    price = metrics["price"]
    range_pct = metrics["range_pct"]
    intraday_range = metrics["intraday_range"]
    vwap_dist_pct = metrics["vwap_dist_pct"]
    session_vol = metrics["session_volume"]
    hod_age_min = metrics["hod_age_min"]
    lod_age_min = metrics["lod_age_min"]
    vol_decline = metrics["vol_decline_ratio"]
    stability = metrics["stability"]

    # Tier 1: Must-have
    if not (BOX_MIN_PRICE <= price <= BOX_MAX_PRICE):
        return None
    if adr <= 0:
        return None
    adr_util = intraday_range / adr
    if adr_util < BOX_MIN_ADR_UTIL:
        return None
    if not (BOX_MIN_RANGE_PCT <= range_pct <= BOX_MAX_RANGE_PCT):
        return None
    if session_vol < BOX_MIN_SESSION_VOL:
        return None

    # Tier 2: Quality
    if hod_age_min < BOX_MIN_HOD_AGE_MIN:
        return None
    if lod_age_min < BOX_MIN_LOD_AGE_MIN:
        return None
    if vwap_dist_pct > BOX_MAX_VWAP_DIST_PCT:
        return None
    if vol_decline > BOX_VOL_DECLINE_MAX:
        return None
    if stability < BOX_MIN_STABILITY:
        return None

    # Score
    box_score = compute_box_score(adr_util, vwap_dist_pct, vol_decline,
                                  stability, hod_age_min, lod_age_min)

    return {
        "symbol": symbol,
        "price": price,
        "hod": metrics["hod"],
        "lod": metrics["lod"],
        "range_pct": range_pct,
        "adr_20d": round(adr, 4),
        "adr_util": round(adr_util, 3),
        "vwap": metrics["vwap"],
        "vwap_dist_pct": vwap_dist_pct,
        "session_volume": session_vol,
        "vol_decline_ratio": vol_decline,
        "stability": stability,
        "hod_age_min": hod_age_min,
        "lod_age_min": lod_age_min,
        "box_score": box_score,
    }


# ── Live Scanner ─────────────────────────────────────────────────────

def scan_box_candidates(ib, scan_time_et: str = BOX_SCAN_TIME_ET) -> List[dict]:
    """Live scan using IBKR HOT_BY_VOLUME + custom box filters."""
    from ib_insync import ScannerSubscription

    print(f"[BOX] Scanning for box candidates at {scan_time_et} ET...", flush=True)

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

    print(f"[BOX] HOT_BY_VOLUME returned {len(results)} stocks", flush=True)

    candidates = []
    date_str = datetime.now(ET).strftime("%Y-%m-%d")

    for i, r in enumerate(results):
        symbol = r.contractDetails.contract.symbol
        try:
            adr = compute_adr_cached(ib, symbol, date_str)
            bars = get_intraday_bars(ib, symbol, date_str, end_time_et=scan_time_et)
            metrics = analyze_intraday(bars, scan_time_et)
            if metrics is None:
                continue
            result = apply_box_filters(symbol, metrics, adr)
            if result:
                candidates.append(result)
                print(f"  [BOX] ✅ {symbol}: score={result['box_score']:.1f} "
                      f"adr_util={result['adr_util']:.0%} range={result['range_pct']:.1f}% "
                      f"vwap_dist={result['vwap_dist_pct']:.1f}%", flush=True)
        except Exception as e:
            print(f"  [BOX] Error processing {symbol}: {e}", flush=True)

    candidates.sort(key=lambda c: c["box_score"], reverse=True)
    print(f"[BOX] Found {len(candidates)} box candidates", flush=True)

    # Save results
    _save_results(date_str, scan_time_et, candidates)
    _save_adr_cache()

    return candidates[:10]


# ── Historical Scanner ───────────────────────────────────────────────

def scan_box_historical(ib, date_str: str, scan_time_et: str = "10:00",
                        universe: Optional[List[str]] = None) -> List[dict]:
    """Historical scan — pull 1m bars for universe stocks, apply box filters.

    Args:
        ib: connected IB instance
        date_str: "YYYY-MM-DD"
        scan_time_et: "HH:MM" to evaluate at
        universe: list of symbols to scan (if None, uses built-in liquid universe)
    """
    if universe is None:
        universe = _get_default_universe()

    print(f"[BOX] Historical scan {date_str} @ {scan_time_et} ET "
          f"({len(universe)} symbols)...", flush=True)

    candidates = []

    for i, symbol in enumerate(universe):
        if (i + 1) % 20 == 0:
            print(f"  [BOX] Progress: {i+1}/{len(universe)}...", flush=True)

        try:
            adr = compute_adr_cached(ib, symbol, date_str)
            if adr <= 0:
                continue

            bars = get_intraday_bars(ib, symbol, date_str, end_time_et=scan_time_et)
            if not bars:
                continue

            metrics = analyze_intraday(bars, scan_time_et)
            if metrics is None:
                continue

            result = apply_box_filters(symbol, metrics, adr)
            if result:
                candidates.append(result)

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
    """Load universe from box_universe.txt, or return a built-in default."""
    if os.path.exists(_UNIVERSE_FILE):
        with open(_UNIVERSE_FILE) as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]

    # Built-in default: ~100 liquid mid-cap stocks ($5-$100, avg vol > 500K)
    # This is a starting point — should be replaced with a dynamically-built list
    return [
        "AAPL", "AMD", "AMZN", "BAC", "C", "CCL", "CMCSA", "CSCO",
        "DAL", "DIS", "F", "FCX", "GE", "GILD", "GM", "GOLD",
        "HOOD", "HPE", "INTC", "JD", "KEY", "KMI", "KO", "KVUE",
        "LUV", "LYFT", "MRO", "MRVL", "MU", "NEM", "NIO", "NOK",
        "NYCB", "OXY", "PARA", "PBR", "PCG", "PFE", "PLTR", "PLUG",
        "PYPL", "QCOM", "RIVN", "ROKU", "SCHW", "SHOP", "SNAP", "SOFI",
        "SQ", "SWN", "T", "TEVA", "TGT", "TFC", "UBER", "USB",
        "VZ", "WBA", "WBD", "WFC", "XOM", "ZION",
        # Mid-cap movers
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

    # Append to existing file if rescanning same day
    existing = []
    if os.path.exists(outfile):
        try:
            with open(outfile) as f:
                existing = json.load(f)
            if not isinstance(existing, list):
                existing = [existing]
        except Exception:
            existing = []

    snapshot = {
        "scan_time_et": scan_time_et,
        "date": date_str,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    existing.append(snapshot)

    with open(outfile, "w") as f:
        json.dump(existing, f, indent=2)


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from ib_insync import IB

    parser = argparse.ArgumentParser(description="Box Scanner — find range-bound stocks")
    parser.add_argument("--date", default="", help="Historical date (YYYY-MM-DD). Empty = live.")
    parser.add_argument("--time", default=BOX_SCAN_TIME_ET, help="Scan time ET (HH:MM)")
    parser.add_argument("--port", type=int, default=4002, help="IBKR Gateway port")
    parser.add_argument("--universe", default="", help="Path to universe file")
    args = parser.parse_args()

    _load_adr_cache()
    print(f"ADR cache: {len(_adr_cache)} entries loaded", flush=True)

    ib = IB()
    ib.connect("127.0.0.1", args.port, clientId=10)  # clientId=10 to avoid conflicts

    try:
        if args.date:
            universe = None
            if args.universe:
                with open(args.universe) as f:
                    universe = [l.strip() for l in f if l.strip()]
            results = scan_box_historical(ib, args.date, args.time, universe)
        else:
            results = scan_box_candidates(ib, args.time)

        print(f"\n{'='*60}")
        print(f"  BOX SCANNER RESULTS: {args.date or 'LIVE'} @ {args.time} ET")
        print(f"  Candidates: {len(results)}")
        print(f"{'='*60}")
        for i, c in enumerate(results[:10], 1):
            print(f"  {i:2d}. {c['symbol']:6s} score={c['box_score']:5.1f} "
                  f"price=${c['price']:.2f} range={c['range_pct']:.1f}% "
                  f"adr_util={c['adr_util']:.0%} vwap_dist={c['vwap_dist_pct']:.1f}% "
                  f"vol_decline={c['vol_decline_ratio']:.2f} stab={c['stability']:.2f}")
    finally:
        ib.disconnect()
        _save_adr_cache()
