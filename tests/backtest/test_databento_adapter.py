"""Unit tests for framework.data_adapters.databento_adapter.

These tests use SYNTHETIC data — they do NOT hit the live Databento API.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from framework.data_adapters.databento_adapter import DatabentoAdapter


@pytest.fixture
def tmp_cache(tmp_path: Path) -> Path:
    d = tmp_path / "cache"
    d.mkdir()
    return d


@pytest.fixture
def adapter(tmp_cache: Path) -> DatabentoAdapter:
    # Pass an explicit api_key=None and a tmp cache — _ensure_client will only
    # be called if we miss cache, and these tests preseed the cache.
    return DatabentoAdapter(cache_dir=tmp_cache, api_key="dummy-key-for-tests")


def _synthetic_trades_df(n: int = 100, symbol: str = "AAPL") -> pd.DataFrame:
    """Generate a normalized trades-schema DataFrame."""
    start = pd.Timestamp("2024-01-02 14:30:00", tz="UTC")
    ts = pd.date_range(start, periods=n, freq="100ms")
    prices = 185.0 + np.cumsum(np.random.normal(0, 0.01, n))
    return pd.DataFrame({
        "ts_event": ts,
        "price": prices,
        "size": np.random.randint(1, 100, n),
        "side": np.random.choice(["A", "B", "N"], n),
        "symbol": symbol,
    })


def _synthetic_bbo_df(n: int = 100, symbol: str = "AAPL") -> pd.DataFrame:
    """Generate a normalized bbo-1s DataFrame."""
    start = pd.Timestamp("2024-01-02 14:30:00", tz="UTC")
    ts = pd.date_range(start, periods=n, freq="1s")
    mid = 185.0 + np.cumsum(np.random.normal(0, 0.02, n))
    spread = 0.01
    return pd.DataFrame({
        "ts_event": ts,
        "bid_px": mid - spread / 2,
        "ask_px": mid + spread / 2,
        "bid_sz": np.random.randint(100, 5000, n),
        "ask_sz": np.random.randint(100, 5000, n),
        "symbol": symbol,
    })


def test_cache_path_creates_directory(adapter: DatabentoAdapter):
    p = adapter._cache_path("AAPL", "trades", "2024-01-02")
    assert p.parent.exists()
    assert p.suffix == ".parquet"
    assert "AAPL" in str(p)


def test_dates_in_range(adapter: DatabentoAdapter):
    dates = adapter._dates_in_range("2024-01-02", "2024-01-05")
    assert dates == ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]


def test_dates_in_range_reversed_returns_empty(adapter: DatabentoAdapter):
    assert adapter._dates_in_range("2024-01-05", "2024-01-02") == []


def test_normalize_trades_df_synthetic():
    # Simulate what Databento's raw .to_df() looks like for trades schema:
    # DatetimeIndex + price/size/side columns.
    n = 50
    start = pd.Timestamp("2024-01-02 14:30:00", tz="UTC")
    idx = pd.date_range(start, periods=n, freq="100ms")
    raw = pd.DataFrame({
        "price": np.random.uniform(184, 186, n),
        "size": np.random.randint(1, 100, n),
        "side": np.random.choice(["A", "B", "N"], n),
        "action": ["T"] * n,
    }, index=idx)
    norm = DatabentoAdapter._normalize_df(raw, "AAPL", "trades")
    assert set(["ts_event", "price", "size", "side", "symbol"]).issubset(norm.columns)
    assert len(norm) == n
    assert (norm["symbol"] == "AAPL").all()


def test_normalize_bbo_df_synthetic():
    n = 20
    start = pd.Timestamp("2024-01-02 14:30:00", tz="UTC")
    idx = pd.date_range(start, periods=n, freq="1s")
    raw = pd.DataFrame({
        "bid_px_00": np.random.uniform(184.99, 185.01, n),
        "ask_px_00": np.random.uniform(185.01, 185.03, n),
        "bid_sz_00": np.random.randint(100, 5000, n),
        "ask_sz_00": np.random.randint(100, 5000, n),
    }, index=idx)
    norm = DatabentoAdapter._normalize_df(raw, "AAPL", "bbo-1s")
    assert set(["ts_event", "bid_px", "ask_px", "bid_sz", "ask_sz", "symbol"]).issubset(norm.columns)
    assert len(norm) == n


def test_fetch_trades_loads_from_cache(adapter: DatabentoAdapter, tmp_cache: Path):
    # Pre-seed the cache with synthetic data
    df = _synthetic_trades_df(n=200)
    cache_path = adapter._cache_path("AAPL", "trades", "2024-01-02")
    df.to_parquet(cache_path, index=False)

    out = adapter.fetch_trades("AAPL", "2024-01-02", "2024-01-02", use_cache=True)
    assert not out.empty
    assert len(out) == 200
    assert set(["ts_event", "price", "size", "symbol"]).issubset(out.columns)


def test_to_trade_ticks_conversion(adapter: DatabentoAdapter):
    df = _synthetic_trades_df(n=50)
    ticks = adapter.to_trade_ticks(df, instrument_id_str="AAPL.XNAS", price_precision=2)
    assert len(ticks) == 50
    first = ticks[0]
    # Sanity-check the first tick
    assert str(first.instrument_id) == "AAPL.XNAS"
    assert float(first.price) > 0
    assert int(first.size) > 0


def test_to_quote_ticks_conversion(adapter: DatabentoAdapter):
    df = _synthetic_bbo_df(n=50)
    quotes = adapter.to_quote_ticks(df, instrument_id_str="AAPL.XNAS", price_precision=2)
    assert len(quotes) == 50
    first = quotes[0]
    assert str(first.instrument_id) == "AAPL.XNAS"
    assert float(first.bid_price) > 0
    assert float(first.ask_price) >= float(first.bid_price)


def test_to_quote_ticks_drops_zero_bid_or_ask(adapter: DatabentoAdapter):
    df = _synthetic_bbo_df(n=10)
    df.loc[0, "bid_px"] = 0
    df.loc[1, "ask_px"] = 0
    quotes = adapter.to_quote_ticks(df, instrument_id_str="AAPL.XNAS")
    # We dropped two rows
    assert len(quotes) == 8


def test_resample_to_bars(adapter: DatabentoAdapter):
    df = _synthetic_trades_df(n=600)  # 600 * 100ms = 60s
    bars = DatabentoAdapter.resample_to_bars(df, freq="10s")
    # 60s / 10s = 6 bars
    assert len(bars) >= 5
    assert set(["open", "high", "low", "close", "volume"]).issubset(bars.columns)
    assert (bars["high"] >= bars["low"]).all()


def test_resample_empty_returns_empty():
    out = DatabentoAdapter.resample_to_bars(pd.DataFrame(), freq="1min")
    assert out.empty
    assert set(out.columns) >= {"open", "high", "low", "close", "volume"}
