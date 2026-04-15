"""Float lookup + profile classification — Alpaca-free.

Extracted from scanner_sim.py so Alpaca-free callers (warrior_manual,
ibkr_scanner) can use these helpers without loading the Alpaca SDK.

scanner_sim.py re-exports these names for back-compat.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time

import requests
from dotenv import load_dotenv

load_dotenv()

# yfinance import is OPTIONAL — kept only for explicit get_float_blocking()
# fallback. The async path (default get_float()) does NOT use yfinance because
# its 30s connection timeout was the recurring cause of bot watchdog kills
# (2026-04-15: 4× watchdog kills traced to yfinance + FMP rate-limit cascade).
try:
    import yfinance as yf
    _YFINANCE_AVAILABLE = True
except ImportError:
    _YFINANCE_AVAILABLE = False

FMP_API_KEY = os.getenv("FMP_API_KEY")
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")

SCANNER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_results")
FLOAT_CACHE_PATH = os.path.join(SCANNER_DIR, "float_cache.json")


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


def load_float_cache() -> dict:
    if os.path.exists(FLOAT_CACHE_PATH):
        with open(FLOAT_CACHE_PATH) as f:
            raw = json.load(f)
        cleaned = {k: v for k, v in raw.items() if v is not None}
        dropped = len(raw) - len(cleaned)
        if dropped > 0:
            print(f"  [float_cache] Cleared {dropped} stale None entries — will re-attempt lookups")
            save_float_cache(cleaned)
        return cleaned
    return {}


def save_float_cache(cache: dict):
    os.makedirs(SCANNER_DIR, exist_ok=True)
    with open(FLOAT_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


_EDGAR_CIK_MAP: dict = {}


def _load_edgar_cik_map():
    global _EDGAR_CIK_MAP
    if _EDGAR_CIK_MAP:
        return _EDGAR_CIK_MAP
    try:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": "WarriorBot luke@delightedpath.net"},
            timeout=10,
        )
        data = resp.json()
        _EDGAR_CIK_MAP = {
            v["ticker"].upper(): str(v["cik_str"]).zfill(10)
            for v in data.values()
        }
    except Exception as e:
        print(f"  [EDGAR] Failed to load CIK map: {e}")
    return _EDGAR_CIK_MAP


def get_edgar_shares_outstanding(symbol: str) -> float | None:
    """Tier 5: SEC EDGAR shares outstanding as float proxy. Free, 10 req/s."""
    cik_map = _load_edgar_cik_map()
    cik = cik_map.get(symbol.upper())
    if not cik:
        return None
    try:
        url = (f"https://data.sec.gov/api/xbrl/companyconcept/"
               f"CIK{cik}/dei/EntityCommonStockSharesOutstanding.json")
        resp = requests.get(url, headers={
            "User-Agent": "WarriorBot luke@delightedpath.net"
        }, timeout=_LOOKUP_TIMEOUT_SEC)
        if resp.status_code != 200:
            return None
        data = resp.json()
        shares_list = data.get("units", {}).get("shares", [])
        if not shares_list:
            return None
        latest = sorted(shares_list, key=lambda x: x.get("end", ""), reverse=True)[0]
        shares = latest.get("val", 0)
        if shares > 0:
            print(f"  [EDGAR] {symbol}: {shares/1e6:.2f}M shares outstanding")
            return shares
    except Exception as e:
        print(f"  [EDGAR] {symbol}: {e}")
    return None


def get_alpha_vantage_float(symbol: str) -> float | None:
    """Tier 6: Alpha Vantage OVERVIEW — true float. Free tier: 25 calls/day."""
    if not ALPHA_VANTAGE_KEY:
        return None
    try:
        url = (f"https://www.alphavantage.co/query?function=OVERVIEW"
               f"&symbol={symbol}&apikey={ALPHA_VANTAGE_KEY}")
        resp = requests.get(url, timeout=_LOOKUP_TIMEOUT_SEC)
        data = resp.json()
        shares_float = data.get("SharesFloat")
        if shares_float and shares_float != "None" and shares_float != "0":
            val = float(shares_float)
            if val > 0:
                print(f"  [AlphaVantage] {symbol}: {val/1e6:.2f}M float")
                return val
    except Exception as e:
        print(f"  [AlphaVantage] {symbol}: {e}")
    return None


# ── Background float lookup (added 2026-04-15) ──────────────────────────
# History: synchronous get_float() blocked the catchup loop on slow external
# APIs (FMP rate limits → yfinance fallback → 30s timeout cascades). 4×
# watchdog kills today traced to this path. Fix: queue lookups to a single
# background thread, return cached value or None instantly. yfinance dropped
# entirely; FMP + EDGAR + AlphaVantage chain only, each with strict 5s timeout.

_LOOKUP_TIMEOUT_SEC = 5.0
_LOOKUP_QUEUE: "queue.Queue[str]" = queue.Queue()
_LOOKUP_THREAD: "threading.Thread | None" = None
_LOOKUP_LOCK = threading.Lock()
_LOOKUP_INFLIGHT: set = set()  # symbols currently being looked up
_CACHE_REF: dict = {}           # bound on first call so worker has access


def _lookup_fmp(symbol: str) -> float | None:
    if not FMP_API_KEY:
        return None
    try:
        url = f"https://financialmodelingprep.com/stable/shares-float?symbol={symbol}&apikey={FMP_API_KEY}"
        resp = requests.get(url, timeout=_LOOKUP_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list) and len(data) > 0:
            v = data[0].get("floatShares") or data[0].get("outstandingShares")
            if v:
                print(f"  [FMP] {symbol}: {v/1e6:.2f}M", flush=True)
                return v
    except Exception as e:
        print(f"  [FMP] {symbol}: {str(e)[:80]}", flush=True)
    return None


def _lookup_worker():
    """Background thread. Drains queue; populates cache; persists."""
    global _LOOKUP_THREAD
    cache = _CACHE_REF
    saved_at = time.time()
    while True:
        try:
            symbol = _LOOKUP_QUEUE.get(timeout=30)
        except queue.Empty:
            with _LOOKUP_LOCK:
                _LOOKUP_THREAD = None
            return
        try:
            value = _lookup_fmp(symbol)
            if value is None:
                value = get_edgar_shares_outstanding(symbol)
            if value is None:
                value = get_alpha_vantage_float(symbol)
            with _LOOKUP_LOCK:
                cache[symbol] = value
                _LOOKUP_INFLIGHT.discard(symbol)
            # Persist every 5s of activity to avoid losing work on crash.
            if time.time() - saved_at > 5:
                try:
                    save_float_cache(cache)
                    saved_at = time.time()
                except Exception:
                    pass
        except Exception as e:
            with _LOOKUP_LOCK:
                cache[symbol] = None
                _LOOKUP_INFLIGHT.discard(symbol)
            print(f"  [float_lookup] {symbol} chain failed: {str(e)[:80]}", flush=True)


def _ensure_worker(cache: dict):
    """Bind cache reference and spin up worker if not running."""
    global _LOOKUP_THREAD, _CACHE_REF
    with _LOOKUP_LOCK:
        if _CACHE_REF is not cache:
            _CACHE_REF = cache  # last writer wins; fine in single-process
        if _LOOKUP_THREAD is None or not _LOOKUP_THREAD.is_alive():
            _LOOKUP_THREAD = threading.Thread(
                target=_lookup_worker, daemon=True, name="float-lookup"
            )
            _LOOKUP_THREAD.start()


def get_float(symbol: str, cache: dict) -> float | None:
    """Non-blocking float lookup. Returns cached value or None instantly.
    Schedules background lookup for unknowns; cache populates over time."""
    if symbol in KNOWN_FLOATS:
        return KNOWN_FLOATS[symbol]
    if symbol in cache:
        return cache[symbol]
    with _LOOKUP_LOCK:
        if symbol in _LOOKUP_INFLIGHT:
            return None  # already scheduled
        _LOOKUP_INFLIGHT.add(symbol)
    _LOOKUP_QUEUE.put(symbol)
    _ensure_worker(cache)
    return None  # caller treats as unknown for now; next scan will have it


def get_float_blocking(symbol: str, cache: dict) -> float | None:
    """SYNCHRONOUS legacy lookup. Use only when you can afford to block.
    Includes yfinance if available (NOT used by the async path)."""
    if symbol in KNOWN_FLOATS:
        return KNOWN_FLOATS[symbol]
    if symbol in cache:
        return cache[symbol]
    v = _lookup_fmp(symbol)
    if v is None and _YFINANCE_AVAILABLE:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            v = info.get("floatShares")
            if v:
                print(f"  [yfinance] {symbol}: {v/1e6:.2f}M", flush=True)
        except Exception as e:
            print(f"  [yfinance] {symbol}: {str(e)[:80]}", flush=True)
    if v is None:
        v = get_edgar_shares_outstanding(symbol)
    if v is None:
        v = get_alpha_vantage_float(symbol)
    cache[symbol] = v
    save_float_cache(cache)
    return v


def classify_profile(float_shares: float | None) -> str:
    """Classify stock by float: A (<5M), B (5-15M), unknown, skip (>15M)."""
    if float_shares is None:
        return "unknown"
    millions = float_shares / 1_000_000
    if millions < 5:
        return "A"
    elif millions <= 15:
        return "B"
    else:
        return "skip"
