"""Bulk 1-minute OHLCV fetcher for the ORB backtest.

Pulls Databento `ohlcv-1m` for a population of (symbol, date) pairs and
hands back a `{(symbol, date): list[Bar]}` dict the ORB harness can
consume directly.

Caches per (symbol, date) under `tick_cache_databento/<symbol>/1m_<date>.parquet`
so subsequent runs replay from disk.

Universe handling
-----------------
For the Wave 2 ORB backtest we deliberately bypass the full
`framework.universe.UniverseFilter` cold-start (which would do an
ALL_SYMBOLS OHLCV-1d scan over 1250 trading days and burn hours of
Databento quota). Instead we use a hand-picked top-N most-liquid universe
spanning all five Manny price tiers ($10-20, $20-50, $50-100, $100-200,
$200-300). This is the "expand to top-200 most liquid" escape hatch the
directive explicitly authorizes when the per-day universe filter would
otherwise produce too few trades.

The static list is built from S&P 500 + NASDAQ-100 + IBD-style high-RVOL
small-caps that traded actively for the entire 2020-2024 period. Symbols
that delisted, merged, or had insufficient history are excluded.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from framework.level_sources.base import Bar


log = logging.getLogger("orb_data_fetcher")


_CACHE_ROOT = Path("/Users/duffy/warrior_bot_v2/tick_cache_databento")


# Curated liquid universe spanning $10-300 price band, balanced across
# tiers. All names survived 2020-2024 and trade >$50M avg daily $-volume
# in 2024. ~30 symbols; full 5-year fetch ≈ 75-90 minutes of Databento
# wall-clock, ~150K symbol-days.
ORB_UNIVERSE = [
    # Mega-caps ($150-300) — 5
    "AAPL", "MSFT", "NVDA", "META", "AVGO",
    # Large-caps ($50-150) — 8
    "AMD", "QCOM", "ADBE", "CRM", "ORCL", "INTC", "MU", "CSCO",
    # Large mixed ($20-100) — 7
    "TSLA", "NFLX", "NKE", "DIS", "BAC", "F", "WFC",
    # Mid-momentum ($20-50) — 6
    "AAL", "DAL", "PLTR", "SOFI", "SNAP", "ROKU",
    # Volatile momentum names that spent meaningful time in $10-20 — 4
    "AMC", "GME", "PLUG", "RIOT",
]
# De-dupe while preserving order
_seen = set()
ORB_UNIVERSE = [s for s in ORB_UNIVERSE if not (s in _seen or _seen.add(s))]


def _cache_path(symbol: str, d: date) -> Path:
    sym_dir = _CACHE_ROOT / symbol.upper()
    sym_dir.mkdir(parents=True, exist_ok=True)
    return sym_dir / f"1m_{d.isoformat()}.parquet"


def _databento_client():
    try:
        import databento as db
    except ImportError as e:
        raise RuntimeError("databento package required") from e
    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        env_file = Path("/Users/duffy/warrior_bot_v2/.env")
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("DATABENTO_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().split("#", 1)[0].strip()
                    break
    if not api_key:
        raise RuntimeError("DATABENTO_API_KEY not set")
    return db.Historical(api_key)


def fetch_1m_bars_range(
    symbols: list[str],
    start_date: date,
    end_date: date,
    dataset: str = "XNAS.ITCH",
    rth_only: bool = True,
    use_cache: bool = True,
) -> dict[tuple[str, date], list[Bar]]:
    """Fetch 1m OHLCV bars for `symbols` across [start_date, end_date].

    Returns a dict keyed by (symbol, date) → list of Bars (RTH only by
    default, sorted ascending by timestamp, timestamps in market-local ET).

    Cache strategy: each (symbol, date) is one parquet file. The function
    walks contiguous uncached spans per symbol and bulk-fetches.

    Conversion: ts_event from Databento is UTC; we convert to America/New_York
    and strip tz so downstream Bar code sees naïve ET timestamps (matching
    the convention OpeningRangeSource expects with session_open_local=True).
    """
    result: dict[tuple[str, date], list[Bar]] = {}
    client = None
    for sym in symbols:
        df_all = _fetch_symbol_range(sym, start_date, end_date, dataset, use_cache, client)
        if df_all is None or df_all.empty:
            continue
        # Group by date
        df_all = df_all.copy()
        df_all["_date"] = df_all["ts_event"].dt.date
        for d, day_df in df_all.groupby("_date"):
            bars = []
            for row in day_df.itertuples(index=False):
                # Filter to RTH (09:30–16:00)
                t = row.ts_event.time()
                if rth_only and (t < datetime(2000, 1, 1, 9, 30).time() or t >= datetime(2000, 1, 1, 16, 0).time()):
                    continue
                bars.append(Bar(
                    timestamp=row.ts_event.replace(tzinfo=None),
                    open=float(row.open),
                    high=float(row.high),
                    low=float(row.low),
                    close=float(row.close),
                    volume=float(row.volume),
                    symbol=sym,
                ))
            if bars:
                result[(sym, d)] = bars
    return result


def _fetch_symbol_range(
    symbol: str,
    start_date: date,
    end_date: date,
    dataset: str,
    use_cache: bool,
    client_holder: object,
) -> pd.DataFrame | None:
    """Fetch (and cache) 1m bars for one symbol over [start_date, end_date].

    Skips weekends entirely (no point fetching Sat/Sun). Uses the cached
    parquet for any prior fetch of a given date — present-non-empty rows go
    into frames; present-empty markers are treated as cached (we know there's
    no data there). Missing dates get fetched as one big span.
    """
    # Weekday-only date list. pandas freq='B' = business days (Mon-Fri).
    all_dates = pd.date_range(start_date, end_date, freq="B").date.tolist()

    frames: list[pd.DataFrame] = []
    to_fetch: list[date] = []
    for d in all_dates:
        cp = _cache_path(symbol, d)
        if use_cache and cp.exists():
            try:
                df = pd.read_parquet(cp)
                if not df.empty:
                    frames.append(df)
                # Empty-marker file means "we already checked; no data here"
            except Exception as e:
                log.warning("Failed cache read %s: %s — refetching", cp, e)
                to_fetch.append(d)
        else:
            to_fetch.append(d)

    if to_fetch:
        # Build ONE big span [first_missing, last_missing] and fetch it.
        # Databento charges by data returned, not by request, so a single
        # big fetch is much faster than hundreds of small ones (which is
        # what consecutive-date coalescing would produce when cached
        # weekdays are interleaved with holiday gaps).
        spans = [(min(to_fetch), max(to_fetch))]
        # Track the set of dates we *expected* in this span so empty-day
        # markers can be written for any date inside [start, end] that
        # Databento doesn't return.
        expected_set = set(to_fetch)
        client = _databento_client()
        for span_start, span_end in spans:
            log.info(
                "[orb_data_fetcher] fetching %s %s ohlcv-1m %s..%s",
                symbol, dataset, span_start, span_end,
            )
            try:
                store = client.timeseries.get_range(
                    dataset=dataset,
                    schema="ohlcv-1m",
                    symbols=[symbol.upper()],
                    stype_in="raw_symbol",
                    start=span_start.isoformat() + "T00:00:00",
                    end=(span_end + timedelta(days=1)).isoformat() + "T00:00:00",
                )
                raw = store.to_df()
            except Exception as e:
                log.warning("[orb_data_fetcher] fetch failed %s %s..%s: %s",
                            symbol, span_start, span_end, e)
                continue
            if raw.empty:
                # Cache empty days so we don't retry every run
                for d in pd.date_range(span_start, span_end, freq="D").date:
                    cp = _cache_path(symbol, d)
                    # Write an empty marker (zero-row parquet)
                    pd.DataFrame(columns=["ts_event", "open", "high", "low", "close", "volume"]).to_parquet(cp, index=False)
                continue
            # Databento returns ts_event in the index, tz-aware UTC
            raw = raw.reset_index()
            if "ts_event" not in raw.columns:
                log.warning("[orb_data_fetcher] missing ts_event column for %s", symbol)
                continue
            # Convert ts_event UTC → America/New_York → naive
            raw["ts_event"] = pd.to_datetime(raw["ts_event"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
            keep = raw[["ts_event", "open", "high", "low", "close", "volume"]].copy()
            keep["_date"] = keep["ts_event"].dt.date
            returned_dates: set[date] = set()
            for d, day_df in keep.groupby("_date"):
                cp = _cache_path(symbol, d)
                day_df.drop(columns=["_date"]).to_parquet(cp, index=False)
                frames.append(day_df.drop(columns=["_date"]))
                returned_dates.add(d)
            # Write empty markers for expected weekdays Databento didn't return
            # (holidays, halt days, pre-IPO).
            for d in expected_set:
                if d < span_start or d > span_end:
                    continue
                if d in returned_dates:
                    continue
                cp = _cache_path(symbol, d)
                if cp.exists():
                    continue
                pd.DataFrame(
                    columns=["ts_event", "open", "high", "low", "close", "volume"]
                ).to_parquet(cp, index=False)

    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True)
    if out.empty:
        return out
    out["ts_event"] = pd.to_datetime(out["ts_event"])
    out = out.sort_values("ts_event").drop_duplicates(subset=["ts_event"]).reset_index(drop=True)
    return out


def _coalesce_spans(dates: list[date]) -> list[tuple[date, date]]:
    """Coalesce consecutive dates into (start, end) spans (calendar)."""
    if not dates:
        return []
    dates = sorted(dates)
    spans: list[tuple[date, date]] = []
    cur_start = dates[0]
    cur_end = dates[0]
    for d in dates[1:]:
        if d - cur_end <= timedelta(days=1):
            cur_end = d
        else:
            spans.append((cur_start, cur_end))
            cur_start = d
            cur_end = d
    spans.append((cur_start, cur_end))
    return spans
