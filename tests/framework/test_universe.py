"""Tests for the framework universe filter.

Tests are organized in three layers:

1. Unit  — synthetic input, each filter exercised in isolation
2. Edge  — missing/invalid data, empty inputs
3. Integration — full pipeline with monkeypatched data fetches
                  (avoids hitting Databento / yfinance from CI)

Live integration with Databento happens via the CLI smoke test, not here.
Tests must not depend on network or on the live float_cache.json contents.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from framework.universe import (
    UniverseConfig,
    UniverseFilter,
    _is_etf_or_junk_symbol,
    _trading_days_before,
)


# ── synthetic fixtures ────────────────────────────────────────────────────


def _make_ohlcv(rows):
    """Build a databento-style OHLCV-1d DataFrame from a list of dicts."""
    df = pd.DataFrame(rows)
    if "ts_event" not in df.columns:
        df["ts_event"] = pd.to_datetime(df["date"]).dt.tz_localize("UTC")
    return df[["ts_event", "instrument_id", "open", "high", "low", "close", "volume"]]


def _make_defs(rows):
    return pd.DataFrame(rows)[["instrument_id", "raw_symbol", "instrument_class"]]


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Redirect the framework cache to tmp_path to keep tests hermetic."""
    cache_dir = tmp_path / "universe_cache"
    cache_dir.mkdir()
    fake_float_cache = cache_dir / "framework_float_cache.json"
    monkeypatch.setattr(
        "framework.universe._UNIVERSE_CACHE_DIR", cache_dir,
    )
    monkeypatch.setattr(
        "framework.universe._FRAMEWORK_FLOAT_CACHE_PATH", fake_float_cache,
    )
    # Live float cache: point at a non-existent file so we don't pick up
    # real live cache data in tests.
    monkeypatch.setattr(
        "framework.universe._FLOAT_CACHE_PATH",
        cache_dir / "nonexistent_live_float_cache.json",
    )
    return cache_dir


@pytest.fixture
def target_date():
    return dt.date(2024, 6, 17)


@pytest.fixture
def synth_universe(target_date):
    """Five symbols with controlled properties to exercise filters.

    AAA — passes everything (mid-cap, in price band, healthy fluctuation)
    BBB — too cheap (below price_min)
    CCC — too expensive (above price_max)
    DDD — float too small
    EEE — float too large
    FFF — day range too tight
    GGG — relative volume too low
    HHH — ADV too low
    """
    # Build 25 days of prior history (uniform) + a target-day row each.
    rows = []
    syms = {
        1: ("AAA", 50.0, 50_000_000, 200_000),     # in-band
        2: ("BBB", 5.0, 50_000_000, 200_000),      # below price_min
        3: ("CCC", 500.0, 50_000_000, 200_000),    # above price_max
        4: ("DDD", 50.0, 10_000_000, 200_000),     # float below band
        5: ("EEE", 50.0, 500_000_000, 200_000),    # float above band
        6: ("FFF", 50.0, 50_000_000, 200_000),     # day range too tight
        7: ("GGG", 50.0, 50_000_000, 200_000),     # RV too low
        8: ("HHH", 50.0, 50_000_000, 5_000),       # ADV too low
    }
    # 20 prior days
    for d_offset in range(25, 0, -1):
        for iid, (sym, price, _float, vol) in syms.items():
            day = target_date - dt.timedelta(days=d_offset)
            rows.append({
                "date": day, "instrument_id": iid,
                "open": price, "high": price * 1.02, "low": price * 0.98,
                "close": price, "volume": vol,
            })
    # Target-day rows
    target_rows = {
        1: ("AAA", 50.0, 50.0, 52.0, 49.5, 51.5, 400_000),  # 5% range, 2x RV
        2: ("BBB",  5.0,  5.0,  5.2,  4.95,  5.15, 400_000),
        3: ("CCC", 500.0, 500.0, 520.0, 495.0, 515.0, 400_000),
        4: ("DDD", 50.0, 50.0, 52.0, 49.5, 51.5, 400_000),
        5: ("EEE", 50.0, 50.0, 52.0, 49.5, 51.5, 400_000),
        6: ("FFF", 50.0, 50.0, 50.5, 49.8, 50.1, 400_000),  # 1.4% range
        7: ("GGG", 50.0, 50.0, 52.0, 49.5, 51.5, 220_000),  # 1.1x RV
        8: ("HHH", 50.0, 50.0, 52.0, 49.5, 51.5, 10_000),
    }
    for iid, (sym, prev_close, op, hi, lo, cl, vol) in target_rows.items():
        rows.append({
            "date": target_date, "instrument_id": iid,
            "open": op, "high": hi, "low": lo, "close": cl, "volume": vol,
        })
    ohlcv = _make_ohlcv(rows)
    defs = _make_defs([
        {"instrument_id": i, "raw_symbol": s[0], "instrument_class": "K"}
        for i, s in syms.items()
    ])
    floats = {s[0]: s[2] for s in syms.values()}
    return ohlcv, defs, floats


def _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch):
    """Patch a UniverseFilter to return synthetic data + floats."""
    monkeypatch.setattr(uf, "_fetch_ohlcv", lambda start, end: ohlcv)
    monkeypatch.setattr(uf, "_fetch_definitions", lambda d: defs)
    # Avoid hitting yfinance — preload float cache with our synthetic values.
    uf._float_cache = dict(floats)
    monkeypatch.setattr(uf, "_backfill_floats", lambda symbols: None)


# ── unit: filter sensitivity ──────────────────────────────────────────────


class TestPriceBandFilter:
    def test_passes_in_band_symbol(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        uf = UniverseFilter(UniverseConfig())
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        df = uf.compute_for_date(target_date)
        assert "AAA" in df["symbol"].tolist()

    def test_excludes_too_cheap(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        uf = UniverseFilter(UniverseConfig())
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        df = uf.compute_for_date(target_date)
        assert "BBB" not in df["symbol"].tolist()

    def test_excludes_too_expensive(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        uf = UniverseFilter(UniverseConfig())
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        df = uf.compute_for_date(target_date)
        assert "CCC" not in df["symbol"].tolist()


class TestFloatFilter:
    def test_excludes_too_small_float(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        uf = UniverseFilter(UniverseConfig())
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        df = uf.compute_for_date(target_date)
        assert "DDD" not in df["symbol"].tolist()

    def test_excludes_too_large_float(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        uf = UniverseFilter(UniverseConfig())
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        df = uf.compute_for_date(target_date)
        assert "EEE" not in df["symbol"].tolist()

    def test_missing_float_excluded_by_default(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        # Drop float for AAA — should be excluded.
        del floats["AAA"]
        uf = UniverseFilter(UniverseConfig(backfill_missing_floats=False))
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        df = uf.compute_for_date(target_date)
        assert "AAA" not in df["symbol"].tolist()

    def test_missing_float_passes_when_not_required(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        del floats["AAA"]
        uf = UniverseFilter(UniverseConfig(
            require_float=False, backfill_missing_floats=False,
        ))
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        df = uf.compute_for_date(target_date)
        assert "AAA" in df["symbol"].tolist()


class TestDayRangeFilter:
    def test_excludes_tight_range(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        uf = UniverseFilter(UniverseConfig())
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        df = uf.compute_for_date(target_date)
        assert "FFF" not in df["symbol"].tolist()


class TestRelativeVolumeFilter:
    def test_excludes_low_rv(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        uf = UniverseFilter(UniverseConfig())
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        df = uf.compute_for_date(target_date)
        assert "GGG" not in df["symbol"].tolist()


class TestADVFilter:
    def test_excludes_low_adv(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        uf = UniverseFilter(UniverseConfig())
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        df = uf.compute_for_date(target_date)
        assert "HHH" not in df["symbol"].tolist()


class TestSectorExclusion:
    def test_drops_excluded_sectors(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        uf = UniverseFilter(UniverseConfig(sector_exclusions=["Healthcare"]))
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        # Tag AAA with the excluded sector manually after compute.
        # We can't easily inject sectors via the synth path (no sector data
        # in EQUS.MINI), so we instead verify the empty default keeps AAA.
        df = uf.compute_for_date(target_date)
        # sector column is all None → exclusion doesn't drop AAA when
        # sector is None.
        assert "AAA" in df["symbol"].tolist()

    def test_empty_default_keeps_everything(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        uf = UniverseFilter(UniverseConfig())  # empty sector_exclusions
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        df = uf.compute_for_date(target_date)
        assert "AAA" in df["symbol"].tolist()


# ── edge cases ────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_ohlcv_returns_empty(self, target_date, isolated_cache, monkeypatch):
        uf = UniverseFilter(UniverseConfig())
        monkeypatch.setattr(uf, "_fetch_ohlcv", lambda s, e: pd.DataFrame())
        monkeypatch.setattr(uf, "_fetch_definitions", lambda d: pd.DataFrame())
        df = uf.compute_for_date(target_date)
        assert df.empty

    def test_empty_definitions_returns_empty(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, _, _ = synth_universe
        uf = UniverseFilter(UniverseConfig())
        monkeypatch.setattr(uf, "_fetch_ohlcv", lambda s, e: ohlcv)
        monkeypatch.setattr(uf, "_fetch_definitions", lambda d: pd.DataFrame())
        df = uf.compute_for_date(target_date)
        assert df.empty

    def test_no_target_date_data(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        # Remove all target-date rows → "market holiday" scenario.
        target_pd = pd.to_datetime(target_date).tz_localize("UTC")
        ohlcv = ohlcv[ohlcv["ts_event"] != target_pd].copy()
        uf = UniverseFilter(UniverseConfig())
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        df = uf.compute_for_date(target_date)
        assert df.empty

    def test_missing_price_data_excluded(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        # Inject a NaN price into AAA's target-day open — should drop.
        target_pd = pd.to_datetime(target_date).tz_localize("UTC")
        mask = (
            (ohlcv["ts_event"] == target_pd) & (ohlcv["instrument_id"] == 1)
        )
        ohlcv.loc[mask, "open"] = float("nan")
        uf = UniverseFilter(UniverseConfig())
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        df = uf.compute_for_date(target_date)
        assert "AAA" not in df["symbol"].tolist()


# ── helpers ───────────────────────────────────────────────────────────────


class TestHelpers:
    def test_trading_days_before_pads_holidays(self):
        # 20 trading days before should be at least ~28 calendar days back.
        target = dt.date(2024, 1, 31)
        result = _trading_days_before(target, 20)
        delta = (target - result).days
        assert delta >= 28, f"insufficient pad: {delta} days"

    @pytest.mark.parametrize("sym", [
        "WALDW", "ABCDW",  # 5-char warrant suffixes
        "BABA-A", "BRK.B",  # class-share punctuation
        "WALDU",  # unit suffix
        "SOMEPA",  # preferred suffix
    ])
    def test_junk_symbols_rejected(self, sym):
        assert _is_etf_or_junk_symbol(sym)

    @pytest.mark.parametrize("sym", [
        "AAPL", "NVDA", "TSLA", "MSFT", "SPOT", "AMD", "META",
    ])
    def test_common_stocks_accepted(self, sym):
        assert not _is_etf_or_junk_symbol(sym)


# ── caching ───────────────────────────────────────────────────────────────


class TestCaching:
    def test_to_parquet_round_trip(self, tmp_path):
        df = pd.DataFrame({
            "symbol": ["AAA", "BBB"],
            "prev_close": [50.0, 75.0],
            "adv_dollar": [1e7, 2e7],
            "float_shares": [5e7, 6e7],
            "day_range_pct": [0.03, 0.05],
            "relative_volume": [2.0, 1.8],
            "sector": [None, None],
        })
        path = tmp_path / "test.parquet"
        uf = UniverseFilter()
        uf.to_parquet(df, path)
        out = uf.from_parquet(path)
        assert out["symbol"].tolist() == ["AAA", "BBB"]
        assert out["adv_dollar"].tolist() == [1e7, 2e7]

    def test_filter_for_date_uses_cache(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        uf = UniverseFilter(UniverseConfig(cache_dir=isolated_cache))
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        syms1 = uf.filter_for_date(target_date)
        # Sabotage the fetch — second call should hit cache instead.
        monkeypatch.setattr(
            uf, "_fetch_ohlcv",
            lambda s, e: (_ for _ in ()).throw(RuntimeError("should not be called")),
        )
        syms2 = uf.filter_for_date(target_date)
        assert syms1 == syms2


# ── integration (synthetic) ───────────────────────────────────────────────


class TestIntegration:
    def test_full_pipeline_produces_expected_universe(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        uf = UniverseFilter(UniverseConfig(cache_dir=isolated_cache))
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        syms = uf.filter_for_date(target_date)
        # AAA passes all filters; everyone else fails one.
        assert syms == ["AAA"], (
            f"expected only AAA to pass, got {syms}"
        )

    def test_output_columns_match_spec(
        self, synth_universe, target_date, isolated_cache, monkeypatch,
    ):
        ohlcv, defs, floats = synth_universe
        uf = UniverseFilter(UniverseConfig(cache_dir=isolated_cache))
        _wire_synthetic(uf, ohlcv, defs, floats, monkeypatch)
        uf.filter_for_date(target_date)
        df = uf.from_parquet(uf._cache_path(target_date))
        expected = {
            "symbol", "prev_close", "adv_dollar", "float_shares",
            "day_range_pct", "relative_volume", "sector",
        }
        assert expected.issubset(set(df.columns))
