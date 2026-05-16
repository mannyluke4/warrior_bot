"""
framework.data_adapters.databento_adapter
=========================================

Databento Standard plan adapter for the Healthy Fluctuation Framework.

This module:

1. Pulls historical equities ``trades`` (trade ticks) and ``bbo-1s`` /
   ``mbp-1`` quote data from the Databento HTTP API.
2. Caches every (symbol, date) range locally as parquet under
   ``tick_cache_databento/<symbol>/<date>.parquet`` so subsequent backtests
   replay from disk without re-hitting the API.
3. Converts cached DataFrames into NautilusTrader ``TradeTick`` and
   ``QuoteTick`` objects so the wider backtest harness can consume them
   directly.

Sample usage
------------
::

    from framework.data_adapters.databento_adapter import DatabentoAdapter

    a = DatabentoAdapter()                                # reads API key from env
    df_trades = a.fetch_trades("AAPL", "2024-01-02", "2024-01-03")
    df_bbo    = a.fetch_bbo   ("AAPL", "2024-01-02", "2024-01-03")
    ticks     = a.to_trade_ticks(df_trades, instrument_id_str="AAPL.XNAS")
    quotes    = a.to_quote_ticks(df_bbo,    instrument_id_str="AAPL.XNAS")

Databento API call patterns (Standard plan)
-------------------------------------------
The Standard plan includes the ``XNAS.ITCH`` (Nasdaq) and ``DBEQ.BASIC``
(US Equities consolidated) datasets, which is where AAPL et al. live for
trades + top-of-book quotes. We default to ``XNAS.ITCH`` because:

* It's the canonical Nasdaq feed (no consolidation latency artefacts).
* Schemas ``trades`` and ``bbo-1s`` are both included on Standard.

For non-Nasdaq symbols, swap ``dataset="DBEQ.BASIC"`` or pass another via
``DatabentoAdapter(default_dataset=...)``.

Costs
-----
Each ``timeseries.get_range`` call burns Databento API quota. The adapter
*always* checks the parquet cache first, only hitting the API when a
(symbol, date) is missing. For Q1 2024 AAPL trades the on-disk footprint
is ~150-300 MB per symbol (raw trade ticks at full resolution).

API key
-------
Read from ``os.environ["DATABENTO_API_KEY"]``. Falls back to ``.env``
parsing if the variable isn't already in the process environment.

Author: Agent A (Wave 1 — Healthy Fluctuation Framework)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

# Databento and Nautilus imports are wrapped so unit tests can mock them
# without forcing the heavy deps to be installed in the test env.
try:
    import databento as db  # type: ignore
    _HAS_DATABENTO = True
except ImportError:  # pragma: no cover
    _HAS_DATABENTO = False

try:
    from nautilus_trader.model.data import TradeTick, QuoteTick
    from nautilus_trader.model.enums import AggressorSide
    from nautilus_trader.model.identifiers import InstrumentId, TradeId
    from nautilus_trader.model.objects import Price, Quantity
    _HAS_NAUTILUS = True
except ImportError:  # pragma: no cover
    _HAS_NAUTILUS = False


__all__ = ["DatabentoAdapter", "DEFAULT_CACHE_DIR"]


log = logging.getLogger(__name__)


DEFAULT_CACHE_DIR = Path("/Users/duffy/warrior_bot_v2/tick_cache_databento")
DEFAULT_DATASET = "XNAS.ITCH"
DEFAULT_TRADES_SCHEMA = "trades"
DEFAULT_BBO_SCHEMA = "bbo-1s"   # 1-second top-of-book (Standard plan)


def _load_env_api_key() -> str | None:
    """Read DATABENTO_API_KEY from process env, falling back to ../.env file."""
    key = os.environ.get("DATABENTO_API_KEY")
    if key:
        return key
    env_file = Path("/Users/duffy/warrior_bot_v2/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DATABENTO_API_KEY="):
                return line.split("=", 1)[1].strip().split("#", 1)[0].strip()
    return None


@dataclass
class DatabentoAdapter:
    """Lazily-instantiated wrapper around ``databento.Historical``.

    Attributes
    ----------
    cache_dir : Path
        Root directory for parquet caches.
    default_dataset : str
        Databento dataset code (default ``"XNAS.ITCH"``).
    api_key : str | None
        Override; otherwise read from ``DATABENTO_API_KEY``.
    """

    cache_dir: Path = DEFAULT_CACHE_DIR
    default_dataset: str = DEFAULT_DATASET
    api_key: str | None = None

    def __post_init__(self) -> None:
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = None  # lazy

    # ---- client ---------------------------------------------------------

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not _HAS_DATABENTO:
            raise RuntimeError(
                "databento package not installed. "
                "Install with: pip install databento"
            )
        key = self.api_key or _load_env_api_key()
        if not key:
            raise RuntimeError(
                "DATABENTO_API_KEY not set. Set it in the environment or in "
                "/Users/duffy/warrior_bot_v2/.env"
            )
        self._client = db.Historical(key=key)
        return self._client

    # ---- cache helpers --------------------------------------------------

    def _cache_path(self, symbol: str, schema: str, date_str: str) -> Path:
        """Return cache parquet path: tick_cache_databento/<symbol>/<schema>_<date>.parquet"""
        symdir = self.cache_dir / symbol.upper()
        symdir.mkdir(parents=True, exist_ok=True)
        return symdir / f"{schema}_{date_str}.parquet"

    def _dates_in_range(self, start: str, end: str) -> list[str]:
        """Inclusive list of YYYY-MM-DD dates between start and end (calendar, not trading)."""
        s = pd.Timestamp(start).normalize()
        e = pd.Timestamp(end).normalize()
        if e < s:
            return []
        return [d.strftime("%Y-%m-%d") for d in pd.date_range(s, e, freq="D")]

    # ---- public fetchers ------------------------------------------------

    def fetch_trades(
        self,
        symbol: str,
        start: str,
        end: str,
        dataset: str | None = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Fetch trade ticks for ``symbol`` between [start, end) (UTC dates).

        ``start`` and ``end`` are ISO date strings (``"YYYY-MM-DD"``) or anything
        ``pd.Timestamp`` parses.

        The adapter caches one parquet per calendar day. Days that already
        exist on disk are loaded from cache.

        Returns
        -------
        pd.DataFrame with columns: ``ts_event`` (UTC datetime64),
        ``price``, ``size``, ``side`` (``"B"``/``"S"`` aggressor, may be ``"N"``
        if unknown), ``symbol``.
        """
        return self._fetch_schema(
            symbol, start, end, schema=DEFAULT_TRADES_SCHEMA,
            dataset=dataset, use_cache=use_cache,
        )

    def fetch_bbo(
        self,
        symbol: str,
        start: str,
        end: str,
        dataset: str | None = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Fetch top-of-book BBO (1-second cadence) for ``symbol``.

        Returns DataFrame with: ``ts_event``, ``bid_px``, ``ask_px``,
        ``bid_sz``, ``ask_sz``, ``symbol``.
        """
        return self._fetch_schema(
            symbol, start, end, schema=DEFAULT_BBO_SCHEMA,
            dataset=dataset, use_cache=use_cache,
        )

    # ---- core fetch -----------------------------------------------------

    def _fetch_schema(
        self,
        symbol: str,
        start: str,
        end: str,
        schema: str,
        dataset: str | None = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        dataset = dataset or self.default_dataset
        dates = self._dates_in_range(start, end)
        if not dates:
            return pd.DataFrame()
        frames: list[pd.DataFrame] = []
        to_fetch: list[str] = []
        for d in dates:
            cp = self._cache_path(symbol, schema, d)
            if use_cache and cp.exists():
                frames.append(pd.read_parquet(cp))
            else:
                to_fetch.append(d)

        if to_fetch:
            log.info("[databento] fetching %s %s for %s (%d days uncached)",
                     symbol, schema, dataset, len(to_fetch))
            client = self._ensure_client()
            # Databento API: pull the contiguous uncached span in one call to
            # minimize HTTP overhead; we then slice per day before caching.
            span_start = to_fetch[0]
            span_end = (pd.Timestamp(to_fetch[-1]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            store = client.timeseries.get_range(
                dataset=dataset,
                schema=schema,
                symbols=[symbol.upper()],
                stype_in="raw_symbol",
                start=span_start,
                end=span_end,
            )
            raw_df = store.to_df()
            if raw_df.empty:
                log.warning("[databento] empty response for %s %s %s..%s",
                            symbol, schema, span_start, span_end)
            else:
                normalized = self._normalize_df(raw_df, symbol, schema)
                # Cache per day
                normalized = normalized.copy()
                normalized["_date"] = normalized["ts_event"].dt.tz_convert("UTC").dt.date
                for date_obj, day_df in normalized.groupby("_date"):
                    date_str = date_obj.strftime("%Y-%m-%d")
                    cp = self._cache_path(symbol, schema, date_str)
                    day_df.drop(columns=["_date"]).to_parquet(cp, index=False)
                    frames.append(day_df.drop(columns=["_date"]))

        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True)
        out = out.sort_values("ts_event").reset_index(drop=True)
        return out

    # ---- normalization --------------------------------------------------

    @staticmethod
    def _normalize_df(df: pd.DataFrame, symbol: str, schema: str) -> pd.DataFrame:
        """Normalize Databento raw DataFrame to our canonical column set."""
        out = pd.DataFrame()
        # Databento puts the event time in the DataFrame index by default
        if isinstance(df.index, pd.DatetimeIndex):
            ts = df.index
        elif "ts_event" in df.columns:
            ts = pd.to_datetime(df["ts_event"], utc=True)
        else:
            raise ValueError("Could not locate ts_event column in Databento DataFrame")
        out["ts_event"] = pd.to_datetime(ts, utc=True)

        if schema == DEFAULT_TRADES_SCHEMA:
            # Databento `trades` schema columns: price, size, side, action, flags ...
            out["price"] = df["price"].astype(float).values
            out["size"]  = df["size"].astype(int).values
            # side: 'A' = ask-side aggressor (buyer hit ask),
            #       'B' = bid-side aggressor (seller hit bid),
            #       'N' = none/unknown
            out["side"]  = df["side"].astype(str).values if "side" in df.columns else "N"
            out["symbol"] = symbol.upper()
        elif schema in (DEFAULT_BBO_SCHEMA, "bbo", "mbp-1"):
            # bbo-1s columns: bid_px_00, ask_px_00, bid_sz_00, ask_sz_00
            bid_col = "bid_px_00" if "bid_px_00" in df.columns else "bid_px"
            ask_col = "ask_px_00" if "ask_px_00" in df.columns else "ask_px"
            bsz_col = "bid_sz_00" if "bid_sz_00" in df.columns else "bid_sz"
            asz_col = "ask_sz_00" if "ask_sz_00" in df.columns else "ask_sz"
            out["bid_px"] = df[bid_col].astype(float).values
            out["ask_px"] = df[ask_col].astype(float).values
            out["bid_sz"] = df[bsz_col].astype(int).values
            out["ask_sz"] = df[asz_col].astype(int).values
            out["symbol"] = symbol.upper()
        else:
            raise ValueError(f"Unsupported schema {schema!r} for normalization")
        return out

    # ---- nautilus conversion -------------------------------------------

    def to_trade_ticks(
        self,
        df: pd.DataFrame,
        instrument_id_str: str,
        price_precision: int = 2,
        size_precision: int = 0,
    ) -> list:
        """Convert normalized trades DataFrame -> list[TradeTick].

        ``instrument_id_str`` like ``"AAPL.XNAS"``. Each row produces one
        ``TradeTick`` suitable for ``BacktestEngine.add_data``.
        """
        if not _HAS_NAUTILUS:
            raise RuntimeError("nautilus-trader not installed")
        if df.empty:
            return []
        instrument_id = InstrumentId.from_str(instrument_id_str)
        ticks: list = []
        # Cache the side -> AggressorSide mapping once
        _aggr = {
            "A": AggressorSide.BUYER,    # ask-side aggressor = buyer hit ask
            "B": AggressorSide.SELLER,   # bid-side aggressor = seller hit bid
            "N": AggressorSide.NO_AGGRESSOR,
        }
        for i, row in enumerate(df.itertuples(index=False)):
            ts_ns = int(pd.Timestamp(row.ts_event).value)
            side = _aggr.get(getattr(row, "side", "N"), AggressorSide.NO_AGGRESSOR)
            ticks.append(TradeTick(
                instrument_id=instrument_id,
                price=Price(float(row.price), price_precision),
                size=Quantity(int(row.size), size_precision),
                aggressor_side=side,
                trade_id=TradeId(f"DB-{i}"),
                ts_event=ts_ns,
                ts_init=ts_ns,
            ))
        return ticks

    def to_quote_ticks(
        self,
        df: pd.DataFrame,
        instrument_id_str: str,
        price_precision: int = 2,
        size_precision: int = 0,
    ) -> list:
        """Convert normalized bbo DataFrame -> list[QuoteTick]."""
        if not _HAS_NAUTILUS:
            raise RuntimeError("nautilus-trader not installed")
        if df.empty:
            return []
        instrument_id = InstrumentId.from_str(instrument_id_str)
        quotes: list = []
        for row in df.itertuples(index=False):
            ts_ns = int(pd.Timestamp(row.ts_event).value)
            # Defensive: discard rows where bid/ask is zero or NaN (Databento
            # emits these for halts / pre-open).
            bid = float(row.bid_px)
            ask = float(row.ask_px)
            if not (np.isfinite(bid) and np.isfinite(ask)) or bid <= 0 or ask <= 0:
                continue
            quotes.append(QuoteTick(
                instrument_id=instrument_id,
                bid_price=Price(bid, price_precision),
                ask_price=Price(ask, price_precision),
                bid_size=Quantity(int(row.bid_sz), size_precision),
                ask_size=Quantity(int(row.ask_sz), size_precision),
                ts_event=ts_ns,
                ts_init=ts_ns,
            ))
        return quotes

    # ---- bar resampling (utility for vectorbt) -------------------------

    @staticmethod
    def resample_to_bars(trades_df: pd.DataFrame, freq: str = "1min") -> pd.DataFrame:
        """Aggregate normalized trades into OHLCV bars."""
        if trades_df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = trades_df.set_index("ts_event")
        ohlc = df["price"].resample(freq).ohlc()
        vol = df["size"].resample(freq).sum().rename("volume")
        out = ohlc.join(vol).dropna(subset=["open"]).copy()
        return out
