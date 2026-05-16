"""Tests for framework.level_sources.volume_profile.

Covers:
- Bin construction (typical-price binning, bin width by pct vs dollar)
- POC identification (highest-volume bin wins)
- HVN classification (bin volume >= mean × hvn_multiplier)
- LVN classification (bin volume <= mean × lvn_multiplier)
- Intraday update semantics (developing profile)
- Edge cases: empty history, zero-volume bars, single-bin profiles,
  non-finite OHLC, pathological configs.
- YAML round-trip via `from_config`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from framework.level_sources.base import Bar, BarHistory, Level, LevelSet
from framework.level_sources.volume_profile import (
    VolumeProfileSource,
    from_config,
)


SESSION = date(2024, 1, 15)


def _bar(
    ts: datetime,
    o: float,
    h: float,
    l: float,
    c: float,
    v: float,
    symbol: str = "AAPL",
) -> Bar:
    return Bar(timestamp=ts, open=o, high=h, low=l, close=c, volume=v, symbol=symbol)


def _make_history(
    bars_by_day: dict[date, list[tuple[float, float, float, float, float]]],
    symbol: str = "AAPL",
    start_minute: int = 30,
) -> BarHistory:
    """Build a BarHistory from {day: [(o,h,l,c,v), ...]} pairs.

    Bars are stamped at 09:30, 09:31, ... per day.
    """
    bars: list[Bar] = []
    for d, day_bars in sorted(bars_by_day.items()):
        for i, (o, h, l, c, v) in enumerate(day_bars):
            ts = datetime(d.year, d.month, d.day, 9, start_minute + i, 0)
            bars.append(_bar(ts, o, h, l, c, v, symbol))
    return BarHistory(symbol=symbol, bars=bars)


# ---------------------------------------------------------------------------
# Construction & validation
# ---------------------------------------------------------------------------


def test_default_construction() -> None:
    src = VolumeProfileSource()
    assert src.lookback_sessions == 5
    assert src.bin_pct == 0.001
    assert src.hvn_multiplier == 1.5
    assert src.lvn_multiplier == 0.5
    assert src.emit_poc and src.emit_hvn and src.emit_lvn


def test_validation_lookback_sessions_positive() -> None:
    with pytest.raises(ValueError, match="lookback_sessions"):
        VolumeProfileSource(lookback_sessions=0)


def test_validation_bin_requires_positive() -> None:
    with pytest.raises(ValueError, match="bin_pct or bin_dollar"):
        VolumeProfileSource(bin_pct=0.0, bin_dollar=None)


def test_validation_bin_dollar_positive_only() -> None:
    with pytest.raises(ValueError, match="bin_dollar"):
        VolumeProfileSource(bin_pct=0.0, bin_dollar=0.0)


def test_validation_hvn_multiplier() -> None:
    with pytest.raises(ValueError, match="hvn_multiplier"):
        VolumeProfileSource(hvn_multiplier=1.0)


def test_validation_lvn_multiplier_in_range() -> None:
    with pytest.raises(ValueError, match="lvn_multiplier"):
        VolumeProfileSource(lvn_multiplier=1.0)
    with pytest.raises(ValueError, match="lvn_multiplier"):
        VolumeProfileSource(lvn_multiplier=0.0)


# ---------------------------------------------------------------------------
# Empty / degenerate inputs
# ---------------------------------------------------------------------------


def test_empty_history_returns_empty_levelset() -> None:
    src = VolumeProfileSource()
    hist = BarHistory(symbol="AAPL", bars=[])
    ls = src.compute_levels("AAPL", hist)
    assert ls.symbol == "AAPL"
    assert ls.levels == ()


def test_zero_volume_bars_skipped() -> None:
    """Bars with volume <= 0 must not poison the bin distribution."""
    src = VolumeProfileSource(target_date=SESSION, bin_dollar=0.10)
    bars = [
        _bar(datetime(2024, 1, 10, 9, 30), 100.0, 100.1, 99.9, 100.0, 0),  # skipped
        _bar(datetime(2024, 1, 10, 9, 31), 100.0, 100.1, 99.9, 100.0, 1_000_000),
        _bar(datetime(2024, 1, 10, 9, 32), 100.0, 100.1, 99.9, 100.0, 1_000_000),
    ]
    hist = BarHistory(symbol="AAPL", bars=bars)
    ls = src.compute_levels("AAPL", hist)
    poc = [l for l in ls.levels if l.kind == "POC"]
    assert len(poc) == 1
    # POC bin volume should equal the sum of the two non-zero-volume bars
    assert poc[0].metadata["bin_volume"] == 2_000_000.0


def test_non_finite_ohlc_skipped() -> None:
    src = VolumeProfileSource(target_date=SESSION, bin_dollar=0.10)
    bars = [
        _bar(datetime(2024, 1, 10, 9, 30), float("nan"), 100.1, 99.9, 100.0, 1000),
        _bar(datetime(2024, 1, 10, 9, 31), 100.0, 100.1, 99.9, 100.0, 1_000_000),
    ]
    hist = BarHistory(symbol="AAPL", bars=bars)
    ls = src.compute_levels("AAPL", hist)
    # The NaN bar is skipped; we still get a POC from the second bar.
    poc = [l for l in ls.levels if l.kind == "POC"]
    assert len(poc) == 1


def test_single_bin_profile_emits_poc_only() -> None:
    """When all volume lands in one bin, POC is emitted but no HVN/LVN."""
    src = VolumeProfileSource(target_date=SESSION, bin_dollar=10.0)  # huge bin
    bars = [
        _bar(datetime(2024, 1, 10, 9, 30), 100.0, 100.1, 99.9, 100.0, 1_000_000),
        _bar(datetime(2024, 1, 10, 9, 31), 100.0, 100.1, 99.9, 100.0, 2_000_000),
    ]
    hist = BarHistory(symbol="AAPL", bars=bars)
    ls = src.compute_levels("AAPL", hist)
    kinds = [l.kind for l in ls.levels]
    assert kinds.count("POC") == 1
    assert "HVN" not in kinds
    assert "LVN" not in kinds


# ---------------------------------------------------------------------------
# POC identification
# ---------------------------------------------------------------------------


def test_poc_is_highest_volume_bin() -> None:
    """The bin with the largest cumulative volume must be the POC."""
    src = VolumeProfileSource(target_date=SESSION, bin_dollar=0.10, lookback_sessions=1)
    # All bars on one date so the lookback fallback uses today's bars.
    d = date(2024, 1, 10)
    bars_data = [
        # (o, h, l, c, v)
        # Cluster around $100.00 (one big volume)
        (100.0, 100.05, 99.95, 100.0, 5_000_000),
        # Cluster around $101.00
        (101.0, 101.05, 100.95, 101.0, 1_000_000),
        # Cluster around $99.00
        (99.0, 99.05, 98.95, 99.0, 1_000_000),
    ]
    hist = _make_history({d: bars_data}, symbol="AAPL")
    src.target_date = d  # force same-day window via fallback
    # Override: VolumeProfileSource's target_date defaults to the latest bar.
    # Setting it to d ensures consistency.
    ls = src.compute_levels("AAPL", hist)
    poc = [l for l in ls.levels if l.kind == "POC"]
    assert len(poc) == 1
    # POC bin should be the one at ~$100.00
    assert abs(poc[0].price - 100.0) < 0.10
    assert poc[0].metadata["bin_volume"] == 5_000_000.0


# ---------------------------------------------------------------------------
# HVN / LVN classification
# ---------------------------------------------------------------------------


def test_hvn_classification_threshold() -> None:
    """Bins with volume >= mean * hvn_multiplier become HVN levels.

    Build a profile with: 4 small bins of 100k vol + 1 fat bin of 1M vol.
    Mean = (4*100k + 1M)/5 = 280k. hvn threshold (1.5x) = 420k.
    The fat bin (1M) is the POC; we need a SECOND fat bin to actually
    emit HVN since POC is excluded. Use 2 fat bins of equal size — one
    wins POC arbitrarily, the other registers as HVN.
    """
    src = VolumeProfileSource(
        target_date=SESSION,
        bin_dollar=0.10,
        hvn_multiplier=1.5,
        lvn_multiplier=0.5,
        lookback_sessions=1,
    )
    d = date(2024, 1, 10)
    bars_data = [
        # 3 "background" bins
        (100.0, 100.05, 99.95, 100.0, 100_000),    # bin 1000
        (101.0, 101.05, 100.95, 101.0, 100_000),   # bin 1010
        (102.0, 102.05, 101.95, 102.0, 100_000),   # bin 1020
        # 2 "cluster" bins — both clearly HVN-eligible
        (105.0, 105.05, 104.95, 105.0, 1_500_000), # bin 1050
        (106.0, 106.05, 105.95, 106.0, 1_500_000), # bin 1060
    ]
    hist = _make_history({d: bars_data}, symbol="AAPL")
    src.target_date = d
    ls = src.compute_levels("AAPL", hist)
    kinds = [l.kind for l in ls.levels]
    # Exactly one POC + at least one HVN
    assert kinds.count("POC") == 1
    assert kinds.count("HVN") >= 1


def test_lvn_classification_threshold() -> None:
    """Bins with volume <= mean * lvn_multiplier become LVN levels."""
    src = VolumeProfileSource(
        target_date=SESSION,
        bin_dollar=0.10,
        hvn_multiplier=2.0,
        lvn_multiplier=0.5,
        lookback_sessions=1,
        merge_adjacent=False,  # disable cluster merging to verify per-bin classification
    )
    d = date(2024, 1, 10)
    # 2 big bins (1M each) + 2 small bins (100k each).
    # Mean = (2M + 200k)/4 = 550k. LVN threshold (0.5x) = 275k.
    # The two small bins fall below 275k → both LVN.
    bars_data = [
        (100.0, 100.05, 99.95, 100.0, 1_000_000),  # POC candidate
        (101.0, 101.05, 100.95, 101.0, 1_000_000),  # HVN candidate
        (103.0, 103.05, 102.95, 103.0, 100_000),    # LVN candidate
        (104.0, 104.05, 103.95, 104.0, 100_000),    # LVN candidate
    ]
    hist = _make_history({d: bars_data}, symbol="AAPL")
    src.target_date = d
    ls = src.compute_levels("AAPL", hist)
    lvn_levels = [l for l in ls.levels if l.kind == "LVN"]
    assert len(lvn_levels) == 2
    # LVN prices should be near $103 and $104
    lvn_prices = sorted(l.price for l in lvn_levels)
    assert any(abs(p - 103.0) < 0.10 for p in lvn_prices)
    assert any(abs(p - 104.0) < 0.10 for p in lvn_prices)


def test_merge_adjacent_collapses_clusters() -> None:
    """Adjacent same-class bins should collapse to one cluster Level.

    Profile: 5 low-vol bins + 3 adjacent high-vol HVN bins + 1 winning
    POC bin. The 3 adjacent HVN bins must collapse to a single cluster.
    """
    src = VolumeProfileSource(
        target_date=SESSION,
        bin_dollar=0.10,
        hvn_multiplier=1.5,
        lvn_multiplier=0.5,
        lookback_sessions=1,
        merge_adjacent=True,
    )
    d = date(2024, 1, 10)
    # 5 low-vol baseline bins; 3 adjacent HVN bins; 1 POC bin.
    # Mean = (5*100k + 3*1.5M + 5M) / 9 ≈ 1.16M. hvn_threshold = 1.74M.
    # The 3 adjacent HVN bins are at 1.5M each (below threshold individually
    # but the 5M POC is excluded). Adjust HVN sizes to ensure they clearly
    # exceed threshold.
    bars_data = [
        (100.0, 100.05, 99.95, 100.0, 100_000),
        (101.0, 101.05, 100.95, 101.0, 100_000),
        (102.0, 102.05, 101.95, 102.0, 100_000),
        (103.0, 103.05, 102.95, 103.0, 100_000),
        (104.0, 104.05, 103.95, 104.0, 100_000),
        # 3 adjacent high-vol bins (cluster)
        (105.05, 105.10, 105.00, 105.05, 2_000_000),
        (105.15, 105.20, 105.10, 105.15, 2_000_000),
        (105.25, 105.30, 105.20, 105.25, 2_000_000),
        # POC bin (highest vol)
        (110.0, 110.05, 109.95, 110.0, 5_000_000),
    ]
    hist = _make_history({d: bars_data}, symbol="AAPL")
    src.target_date = d
    ls = src.compute_levels("AAPL", hist)
    hvn = [l for l in ls.levels if l.kind == "HVN"]
    # The $105 cluster should be ONE Level (not 3 separate HVN bins).
    assert len(hvn) == 1
    assert hvn[0].metadata.get("n_bins_in_cluster") == 3
    # Cluster centroid should be ~$105.15-105.20 area (middle of the 3 bins)
    assert 105.0 < hvn[0].price < 105.3


def test_emit_flags_respected() -> None:
    """emit_poc/hvn/lvn=False suppresses the corresponding level kinds."""
    src = VolumeProfileSource(
        target_date=SESSION,
        bin_dollar=0.10,
        emit_poc=False,
        emit_hvn=True,
        emit_lvn=False,
        lookback_sessions=1,
    )
    d = date(2024, 1, 10)
    bars_data = [
        (100.0, 100.05, 99.95, 100.0, 1_500_000),
        (101.0, 101.05, 100.95, 101.0, 1_500_000),
        (102.0, 102.05, 101.95, 102.0, 100_000),
    ]
    hist = _make_history({d: bars_data}, symbol="AAPL")
    src.target_date = d
    ls = src.compute_levels("AAPL", hist)
    kinds = [l.kind for l in ls.levels]
    assert "POC" not in kinds
    assert "LVN" not in kinds
    # HVN may or may not fire depending on thresholds; test only that the
    # suppressed kinds are absent.


# ---------------------------------------------------------------------------
# Lookback semantics
# ---------------------------------------------------------------------------


def test_lookback_sessions_limits_window() -> None:
    """Only the most recent N prior sessions feed the profile."""
    src = VolumeProfileSource(
        target_date=SESSION,
        bin_dollar=0.10,
        lookback_sessions=2,
    )
    # 4 prior sessions in history, all before SESSION
    days = [SESSION - timedelta(days=i) for i in range(5, 1, -1)]  # 4 oldest
    bars_by_day = {}
    for i, d in enumerate(days):
        # Each session puts its volume in a different bin.
        # i=0 -> $100, i=1 -> $101, ..., i=3 -> $103
        price = 100.0 + i
        bars_by_day[d] = [(price, price + 0.05, price - 0.05, price, 1_000_000)]
    hist = _make_history(bars_by_day, symbol="AAPL")
    ls = src.compute_levels("AAPL", hist)
    # Only the 2 most recent prior sessions (i=2, i=3 → $102 and $103) feed.
    # POC should be one of those two.
    poc = [l for l in ls.levels if l.kind == "POC"][0]
    assert 102.0 - 0.10 < poc.price < 103.0 + 0.10


# ---------------------------------------------------------------------------
# Intraday update semantics
# ---------------------------------------------------------------------------


def test_intraday_update_basic_accumulation() -> None:
    src = VolumeProfileSource()
    bar1 = _bar(datetime(2024, 1, 15, 9, 30), 100.0, 100.1, 99.9, 100.0, 1_000_000)
    bar2 = _bar(datetime(2024, 1, 15, 9, 31), 100.0, 100.1, 99.9, 100.0, 2_000_000)
    src.update_intraday(bar1)
    src.update_intraday(bar2)
    snapshot = src.intraday_snapshot("AAPL", session_date=SESSION)
    poc = [l for l in snapshot.levels if l.kind == "POC"]
    assert len(poc) == 1
    # POC bin should hold ~3M shares
    assert poc[0].metadata["bin_volume"] == 3_000_000.0


def test_intraday_update_ignores_zero_volume() -> None:
    src = VolumeProfileSource()
    src.update_intraday(
        _bar(datetime(2024, 1, 15, 9, 30), 100.0, 100.1, 99.9, 100.0, 0)
    )
    snapshot = src.intraday_snapshot("AAPL", session_date=SESSION)
    assert snapshot.levels == ()


def test_intraday_update_ignores_nan() -> None:
    src = VolumeProfileSource()
    src.update_intraday(
        _bar(
            datetime(2024, 1, 15, 9, 30),
            100.0, float("nan"), 99.9, 100.0, 1000,
        )
    )
    snapshot = src.intraday_snapshot("AAPL", session_date=SESSION)
    # NaN bar must not register
    assert snapshot.levels == ()


def test_reset_intraday_clears_state() -> None:
    src = VolumeProfileSource()
    src.update_intraday(
        _bar(datetime(2024, 1, 15, 9, 30), 100.0, 100.1, 99.9, 100.0, 1_000_000)
    )
    src.reset_intraday()
    snapshot = src.intraday_snapshot("AAPL", session_date=SESSION)
    assert snapshot.levels == ()


# ---------------------------------------------------------------------------
# Bin-width semantics
# ---------------------------------------------------------------------------


def test_bin_dollar_overrides_bin_pct() -> None:
    src = VolumeProfileSource(bin_pct=0.001, bin_dollar=0.50, lookback_sessions=1)
    # At $100, bin_pct would give 10 cents; bin_dollar should win at 50 cents.
    d = date(2024, 1, 10)
    bars_data = [
        (100.0, 100.05, 99.95, 100.0, 1_000_000),
        (100.30, 100.35, 100.25, 100.30, 1_000_000),  # within 50c -> same bin
        (100.80, 100.85, 100.75, 100.80, 1_000_000),  # next 50c bin
    ]
    hist = _make_history({d: bars_data}, symbol="AAPL")
    src.target_date = d
    ls = src.compute_levels("AAPL", hist)
    # With 50c bins, the first 2 bars fall in one bin, the third in another.
    # The "stacked" bin holds 2M; the lone bin holds 1M. Stacked wins POC.
    poc = [l for l in ls.levels if l.kind == "POC"][0]
    assert poc.metadata["bin_volume"] == 2_000_000.0


def test_bin_width_floor_one_cent() -> None:
    """Very low prices with small bin_pct don't produce sub-penny bins."""
    src = VolumeProfileSource(bin_pct=0.00001, lookback_sessions=1)
    d = date(2024, 1, 10)
    bars_data = [
        # ref price ~$2 -> bin_pct 0.00001 -> 2e-5, below 1c floor
        (2.0, 2.001, 1.999, 2.0, 1_000_000),
    ]
    hist = _make_history({d: bars_data}, symbol="AAPL")
    src.target_date = d
    ls = src.compute_levels("AAPL", hist)
    poc = [l for l in ls.levels if l.kind == "POC"][0]
    assert poc.metadata["bin_width"] == pytest.approx(0.01)


# ---------------------------------------------------------------------------
# from_config (YAML round-trip)
# ---------------------------------------------------------------------------


def test_from_config_defaults() -> None:
    src = from_config({})
    assert src.lookback_sessions == 5
    assert src.bin_pct == 0.001
    assert src.hvn_multiplier == 1.5
    assert src.lvn_multiplier == 0.5


def test_from_config_overrides() -> None:
    src = from_config({
        "lookback_sessions": 10,
        "bin_pct": 0.002,
        "bin_dollar": 0.25,
        "hvn_multiplier": 2.0,
        "lvn_multiplier": 0.3,
        "emit_poc": False,
        "emit_hvn": True,
        "emit_lvn": False,
        "min_bars_for_signal": 5,
    })
    assert src.lookback_sessions == 10
    assert src.bin_pct == 0.002
    assert src.bin_dollar == 0.25
    assert src.hvn_multiplier == 2.0
    assert src.lvn_multiplier == 0.3
    assert src.emit_poc is False
    assert src.emit_hvn is True
    assert src.emit_lvn is False
    assert src.min_bars_for_signal == 5


def test_from_config_unknown_keys_ignored() -> None:
    """Unknown YAML keys should be ignored (forward-compat)."""
    src = from_config({"made_up_key": 42, "lookback_sessions": 3})
    assert src.lookback_sessions == 3


# ---------------------------------------------------------------------------
# LevelSet structure
# ---------------------------------------------------------------------------


def test_levels_ordered_by_price_ascending() -> None:
    src = VolumeProfileSource(
        target_date=SESSION,
        bin_dollar=0.10,
        lookback_sessions=1,
    )
    d = date(2024, 1, 10)
    bars_data = [
        (105.0, 105.05, 104.95, 105.0, 1_500_000),
        (100.0, 100.05, 99.95, 100.0, 1_500_000),
        (102.0, 102.05, 101.95, 102.0, 100_000),
    ]
    hist = _make_history({d: bars_data}, symbol="AAPL")
    src.target_date = d
    ls = src.compute_levels("AAPL", hist)
    prices = [l.price for l in ls.levels]
    assert prices == sorted(prices)


def test_metadata_includes_required_fields() -> None:
    src = VolumeProfileSource(target_date=SESSION, bin_dollar=0.10, lookback_sessions=1)
    d = date(2024, 1, 10)
    bars_data = [
        (100.0, 100.05, 99.95, 100.0, 1_000_000),
        (101.0, 101.05, 100.95, 101.0, 1_000_000),
        (102.0, 102.05, 101.95, 102.0, 100_000),
    ]
    hist = _make_history({d: bars_data}, symbol="AAPL")
    src.target_date = d
    ls = src.compute_levels("AAPL", hist)
    for lvl in ls.levels:
        assert "bin_idx" in lvl.metadata
        assert "bin_width" in lvl.metadata
        assert "bin_volume" in lvl.metadata
        assert "ref_price" in lvl.metadata


def test_session_date_propagates_to_levels() -> None:
    src = VolumeProfileSource(target_date=SESSION, bin_dollar=0.10, lookback_sessions=1)
    d = date(2024, 1, 10)
    bars_data = [
        (100.0, 100.05, 99.95, 100.0, 1_000_000),
        (101.0, 101.05, 100.95, 101.0, 1_000_000),
    ]
    hist = _make_history({d: bars_data}, symbol="AAPL")
    src.target_date = d
    ls = src.compute_levels("AAPL", hist)
    for lvl in ls.levels:
        assert lvl.session_date == d
