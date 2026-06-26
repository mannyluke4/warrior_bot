"""All-time-high lookup via Databento daily OHLCV — feeds the manual bot's
blue-sky alert.

"All-time high" here means the maximum daily HIGH over the symbol's full
Databento DBEQ.BASIC coverage (history begins ~2018-05-07). For the typical
squeeze name (a recent IPO) that equals the true ATH; for a pre-2018 ticker it
is the coverage-window high. This tradeoff was chosen deliberately on
2026-06-25 (cheap, no new vendor, correct for recent IPOs).

Design mirrors float_cache.py exactly: get_ath() returns a cached value (even
if a day stale) or None INSTANTLY and schedules a single background Databento
lookup. It NEVER blocks the tick / publish path — a daily-bars request over
years is a tiny payload but still an external HTTP call, so it runs on a
daemon worker. The cache is atomic-write + self-healing on corruption. A
symbol is refreshed at most once per ET trading day.

The caller gates Databento spend: only invoke get_ath() when
WB_ENGINE_ATH_ENABLED=1. This module makes a Databento call only on a
cache-miss / stale entry.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

_ET = ZoneInfo("America/New_York")

SCANNER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_results")
ATH_CACHE_PATH = os.path.join(SCANNER_DIR, "ath_cache.json")

# DBEQ.BASIC ohlcv-1d coverage currently begins 2023-03-28, so "all-time high"
# is really "max daily high since Databento coverage start" (~3 years). For the
# typical recent-IPO squeeze name that equals the true ATH; for older tickers
# it's the coverage-window high. The exact start is resolved from the dataset's
# metadata at runtime (a query before coverage returns HTTP 422), with the env
# value as a fallback only.
DATASET = os.getenv("WB_ATH_DATASET", "DBEQ.BASIC")
_START_FALLBACK = os.getenv("WB_ATH_START_DATE", "2023-03-28")
_resolved_start: str | None = None
_start_lock = threading.Lock()


def _dataset_start() -> str:
    """Resolve the dataset's ohlcv-1d coverage start (YYYY-MM-DD), cached for
    the process. Falls back to the env start on any metadata error."""
    global _resolved_start
    with _start_lock:
        if _resolved_start is not None:
            return _resolved_start
    start = _START_FALLBACK
    try:
        key = os.getenv("DATABENTO_API_KEY") or os.getenv("DB_API_KEY")
        if key:
            import databento as db
            r = db.Historical(key).metadata.get_dataset_range(dataset=DATASET)
            raw = None
            if isinstance(r, dict):
                schema = r.get("schema", {}).get("ohlcv-1d", {})
                raw = schema.get("start") or r.get("start")
            if raw:
                start = str(raw)[:10]
    except Exception as e:
        print(f"  [ath_cache] dataset-range lookup failed ({str(e)[:80]}); using {start}", flush=True)
    with _start_lock:
        _resolved_start = start
    return start


def _today_et() -> str:
    """ET trading date as YYYY-MM-DD. Uses zoneinfo (not a hardcoded UTC
    offset) so the asof boundary is correct across the EST/EDT switch — a
    hardcoded -4 would silently shift the refresh boundary by an hour in
    winter (the class of DST bug we've been bitten by before)."""
    return datetime.now(_ET).strftime("%Y-%m-%d")


# ── Cache persistence (atomic + self-healing, same contract as float_cache) ──

def load_ath_cache() -> dict:
    """Load the ATH cache. Shape: {SYMBOL: {"ath": float|null, "asof": "YYYY-MM-DD"}}.
    A regenerable cache must NEVER take the bot down, so corruption is salvaged
    or backed-up-and-reset rather than raised."""
    if not os.path.exists(ATH_CACHE_PATH):
        return {}
    try:
        with open(ATH_CACHE_PATH) as f:
            text = f.read()
    except OSError:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        try:
            raw, _ = json.JSONDecoder().raw_decode(text)
            print(f"  [ath_cache] WARN: recovered from corruption ({e}); kept {len(raw)} entries")
            save_ath_cache(raw)
            return raw
        except Exception:
            backup = ATH_CACHE_PATH + ".corrupt"
            try:
                os.replace(ATH_CACHE_PATH, backup)
            except OSError:
                pass
            print(f"  [ath_cache] WARN: unrecoverable corruption ({e}); backed up to {backup}, starting empty")
            return {}


def save_ath_cache(cache: dict) -> None:
    os.makedirs(SCANNER_DIR, exist_ok=True)
    # Atomic write: temp file in the same dir + os.replace() (atomic rename on
    # POSIX) so a concurrent reader can never see a half-written file.
    tmp = f"{ATH_CACHE_PATH}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(cache, f, indent=2)
    os.replace(tmp, ATH_CACHE_PATH)


# ── Background lookup (single daemon worker; never blocks the caller) ─────────

_LOOKUP_QUEUE: "queue.Queue[str]" = queue.Queue()
_LOOKUP_THREAD: "threading.Thread | None" = None
_LOOKUP_LOCK = threading.Lock()
_LOOKUP_INFLIGHT: set = set()
_CACHE_REF: dict = {}


def _lookup_ath(symbol: str) -> float | None:
    """Blocking Databento call — max daily high over full coverage. Runs on the
    worker thread only. Returns None on any error/empty (self-heal)."""
    key = os.getenv("DATABENTO_API_KEY") or os.getenv("DB_API_KEY")
    if not key:
        return None
    try:
        import warnings
        import databento as db
        client = db.Historical(key)
        # end is exclusive → through yesterday's daily bar. Pre-market today is
        # measured against the prior coverage high, which is what "blue sky"
        # means (breaking into territory with no historical supply above).
        start = _dataset_start()
        with warnings.catch_warnings():
            # Databento emits a BentoWarning listing reduced-quality days; it's
            # informational and would spam the bot log on every lookup.
            warnings.simplefilter("ignore")
            df = client.timeseries.get_range(
                dataset=DATASET,
                schema="ohlcv-1d",
                symbols=[symbol],
                stype_in="raw_symbol",
                start=start,
                end=_today_et(),
            ).to_df()
        if df is None or len(df) == 0:
            return None
        hi = float(df["high"].max())
        if hi > 0:
            print(f"  [ath_cache] {symbol}: ATH ${hi:.4f} (max daily high since {start})", flush=True)
            return hi
    except Exception as e:
        print(f"  [ath_cache] {symbol}: {str(e)[:100]}", flush=True)
    return None


def _lookup_worker() -> None:
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
            value = _lookup_ath(symbol)
            with _LOOKUP_LOCK:
                # asof=today even on None so we don't re-query a no-data symbol
                # repeatedly within the same trading day.
                cache[symbol] = {"ath": value, "asof": _today_et()}
                _LOOKUP_INFLIGHT.discard(symbol)
            if time.time() - saved_at > 5:
                try:
                    save_ath_cache(cache)
                    saved_at = time.time()
                except Exception:
                    pass
        except Exception as e:
            with _LOOKUP_LOCK:
                cache[symbol] = {"ath": None, "asof": _today_et()}
                _LOOKUP_INFLIGHT.discard(symbol)
            print(f"  [ath_cache] {symbol} lookup failed: {str(e)[:80]}", flush=True)


def _ensure_worker(cache: dict) -> None:
    global _LOOKUP_THREAD, _CACHE_REF
    with _LOOKUP_LOCK:
        if _CACHE_REF is not cache:
            _CACHE_REF = cache  # last writer wins; single-process so fine
        if _LOOKUP_THREAD is None or not _LOOKUP_THREAD.is_alive():
            _LOOKUP_THREAD = threading.Thread(
                target=_lookup_worker, daemon=True, name="ath-lookup"
            )
            _LOOKUP_THREAD.start()


def get_ath(symbol: str, cache: dict) -> float | None:
    """Non-blocking all-time-high lookup. Returns the cached ATH instantly
    (even if a day stale — coverage high barely moves day to day) and schedules
    a background refresh when the entry is missing or older than today. Returns
    None only when nothing is cached yet; the next scan loop will have it."""
    entry = cache.get(symbol)
    today = _today_et()
    if entry is not None:
        fresh = entry.get("asof") == today
        if fresh:
            return entry.get("ath")  # may be None (looked up today, no data)
        # Stale: schedule a refresh but serve the stale value meanwhile.
        with _LOOKUP_LOCK:
            if symbol not in _LOOKUP_INFLIGHT:
                _LOOKUP_INFLIGHT.add(symbol)
                _LOOKUP_QUEUE.put(symbol)
        _ensure_worker(cache)
        return entry.get("ath")
    # No entry: schedule lookup, return None for now.
    with _LOOKUP_LOCK:
        if symbol in _LOOKUP_INFLIGHT:
            return None
        _LOOKUP_INFLIGHT.add(symbol)
    _LOOKUP_QUEUE.put(symbol)
    _ensure_worker(cache)
    return None
