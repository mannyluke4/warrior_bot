"""Unit tests for framework/level_sources/vwap.py — Wave 2, Agent G.

Coverage:
- VWAP math correctness (single bar, multi-bar, weighting by volume)
- Sigma (volume-weighted std) correctness vs. closed-form reference
- Band level generation (1σ, 2σ, mixed multipliers)
- update_intraday parity with compute_levels (incremental == batch)
- vwap_slope_classifier:
    * flat market -> 'flat'
    * strong uptrend -> 'trending_up'
    * strong downtrend -> 'trending_down'
    * edge cases: 0/1 bars, all-zero volume bars
- Robustness: NaN/zero/negative volume bars are skipped
- Level metadata: sigma + slope_per_bar exposed for diagnostics
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import pytest

from framework.level_sources.base import Bar, BarHistory, Level, LevelSet
from framework.level_sources.vwap import (
    SlopeRegime,
    VWAPSource,
    _format_band_label,
    _linreg_slope,
)


# ---------------------------------------------------------------------------
# helpers — synthetic bar generators
# ---------------------------------------------------------------------------

BASE_TS = datetime(2024, 6, 14, 13, 30, tzinfo=timezone.utc)


def mk_bar(
    *, open: float, high: float, low: float, close: float,
    volume: float = 1_000.0, offset_min: int = 0, symbol: str = "TEST",
) -> Bar:
    return Bar(
        timestamp=BASE_TS + timedelta(minutes=offset_min),
        open=open, high=high, low=low, close=close,
        volume=volume, symbol=symbol,
    )


def mk_history(bars: list[Bar], symbol: str = "TEST") -> BarHistory:
    return BarHistory(symbol=symbol, bars=list(bars))


def flat_bars(n: int, price: float = 100.0, volume: float = 1_000.0) -> list[Bar]:
    """N identical bars — VWAP should equal `price`, sigma should be 0."""
    return [
        mk_bar(
            open=price, high=price, low=price, close=price,
            volume=volume, offset_min=i,
        )
        for i in range(n)
    ]


def trending_bars(
    n: int, start: float = 100.0, step: float = 0.10, volume: float = 1_000.0,
) -> list[Bar]:
    """Monotonic up-trend. Each bar opens at prev close + step."""
    out: list[Bar] = []
    p = start
    for i in range(n):
        out.append(mk_bar(
            open=p, high=p + step / 2, low=p - step / 2, close=p + step,
            volume=volume, offset_min=i,
        ))
        p += step
    return out


# ---------------------------------------------------------------------------
# VWAP math — single & multi-bar
# ---------------------------------------------------------------------------


def test_vwap_single_bar_equals_typical_price():
    bar = mk_bar(open=10, high=12, low=8, close=11, volume=1000)
    src = VWAPSource()
    ls = src.compute_levels("TEST", mk_history([bar]))
    vwap = src.vwap
    assert vwap is not None
    # typical = (12 + 8 + 11) / 3 = 10.333...
    assert math.isclose(vwap, 31.0 / 3.0, rel_tol=1e-12)
    # Single bar has zero variance about its own mean.
    assert math.isclose(src.sigma, 0.0, abs_tol=1e-12)
    # LevelSet contains VWAP + 2 bands per default config (1σ, 2σ).
    vwap_levels = ls.by_kind("VWAP")
    assert len(vwap_levels) == 1
    assert math.isclose(vwap_levels[0].price, 31.0 / 3.0, rel_tol=1e-12)


def test_vwap_multi_bar_equal_volume_equal_typical():
    """Three identical bars: VWAP == typical, sigma == 0."""
    bars = flat_bars(3, price=50.0, volume=200.0)
    src = VWAPSource()
    src.compute_levels("X", mk_history(bars))
    assert math.isclose(src.vwap, 50.0, rel_tol=1e-12)
    assert math.isclose(src.sigma, 0.0, abs_tol=1e-12)


def test_vwap_weights_by_volume():
    """High-volume bar should pull VWAP toward its typical price."""
    # Bar A: typical=10, vol=100   ->  contributes 1000 to PV
    # Bar B: typical=20, vol=900   ->  contributes 18000 to PV
    # total PV = 19000, total vol = 1000, vwap = 19.0
    a = mk_bar(open=10, high=10, low=10, close=10, volume=100, offset_min=0)
    b = mk_bar(open=20, high=20, low=20, close=20, volume=900, offset_min=1)
    src = VWAPSource()
    src.compute_levels("X", mk_history([a, b]))
    assert math.isclose(src.vwap, 19.0, rel_tol=1e-12)


def test_vwap_sigma_closed_form_two_bar():
    """Closed-form sigma check for a 2-bar case.

    Bars: (typical, volume) = (10, 100), (20, 100)
    Running VWAPs:
        after 1 bar: 10
        after 2 bars: 15
    Running PVV (squared dev about running vwap, vol-weighted):
        bar1: (10-10)^2 * 100 = 0
        bar2: (20-15)^2 * 100 = 2500
    Total PVV = 2500, total vol = 200 -> var = 12.5, sigma = sqrt(12.5) ≈ 3.5355
    """
    a = mk_bar(open=10, high=10, low=10, close=10, volume=100, offset_min=0)
    b = mk_bar(open=20, high=20, low=20, close=20, volume=100, offset_min=1)
    src = VWAPSource()
    src.compute_levels("X", mk_history([a, b]))
    assert math.isclose(src.vwap, 15.0, rel_tol=1e-12)
    assert math.isclose(src.sigma, math.sqrt(12.5), rel_tol=1e-10)


def test_vwap_skips_zero_volume_bars():
    """Bars with zero volume don't contribute to VWAP."""
    a = mk_bar(open=10, high=10, low=10, close=10, volume=1000, offset_min=0)
    b = mk_bar(open=99, high=99, low=99, close=99, volume=0, offset_min=1)
    c = mk_bar(open=20, high=20, low=20, close=20, volume=1000, offset_min=2)
    src = VWAPSource()
    src.compute_levels("X", mk_history([a, b, c]))
    # Bar b skipped — VWAP is mean of (10, 20) at equal volume = 15.
    assert math.isclose(src.vwap, 15.0, rel_tol=1e-12)


def test_vwap_skips_negative_and_nan_volume():
    """Defensive: negative or NaN volume bars are silently skipped."""
    a = mk_bar(open=10, high=10, low=10, close=10, volume=1000, offset_min=0)
    b = mk_bar(open=99, high=99, low=99, close=99, volume=-500, offset_min=1)
    c = mk_bar(open=99, high=99, low=99, close=99, volume=float("nan"), offset_min=2)
    src = VWAPSource()
    src.compute_levels("X", mk_history([a, b, c]))
    # Only bar a counts.
    assert math.isclose(src.vwap, 10.0, rel_tol=1e-12)


def test_vwap_empty_history_returns_none_and_empty_levelset():
    src = VWAPSource()
    ls = src.compute_levels("X", mk_history([]))
    assert src.vwap is None
    assert src.sigma is None
    assert ls.levels == tuple()


# ---------------------------------------------------------------------------
# Band level generation
# ---------------------------------------------------------------------------


def test_default_bands_produce_vwap_upper_lower_1_and_2():
    bars = flat_bars(5, price=100.0, volume=1000.0)
    # Inject one outlier to get a non-zero sigma.
    outlier = mk_bar(open=110, high=110, low=110, close=110,
                     volume=1000, offset_min=5)
    src = VWAPSource()  # default bands [1.0, 2.0]
    ls = src.compute_levels("X", mk_history(bars + [outlier]))
    kinds = {lvl.kind for lvl in ls.levels}
    assert {"VWAP", "VWAP_UPPER_1", "VWAP_LOWER_1",
            "VWAP_UPPER_2", "VWAP_LOWER_2"} <= kinds


def test_band_levels_are_symmetric_about_vwap():
    bars = flat_bars(3, price=50.0, volume=100.0) + [
        mk_bar(open=60, high=60, low=60, close=60, volume=100, offset_min=3),
        mk_bar(open=40, high=40, low=40, close=40, volume=100, offset_min=4),
    ]
    src = VWAPSource(band_sigmas=[1.0, 2.0])
    ls = src.compute_levels("X", mk_history(bars))
    vwap = ls.by_kind("VWAP")[0].price
    up1 = ls.by_kind("VWAP_UPPER_1")[0].price
    lo1 = ls.by_kind("VWAP_LOWER_1")[0].price
    up2 = ls.by_kind("VWAP_UPPER_2")[0].price
    lo2 = ls.by_kind("VWAP_LOWER_2")[0].price
    # Symmetry: up1 - vwap == vwap - lo1
    assert math.isclose(up1 - vwap, vwap - lo1, rel_tol=1e-12)
    assert math.isclose(up2 - vwap, vwap - lo2, rel_tol=1e-12)
    # 2σ band is exactly twice 1σ band distance.
    assert math.isclose(up2 - vwap, 2.0 * (up1 - vwap), rel_tol=1e-12)


def test_single_band_yaml_use_case():
    """The trend-continuation strategy YAML configures bands: [1.0]."""
    bars = flat_bars(2, price=10) + [
        mk_bar(open=12, high=12, low=12, close=12, volume=1000, offset_min=2)
    ]
    src = VWAPSource(band_sigmas=[1.0])
    ls = src.compute_levels("X", mk_history(bars))
    kinds = {lvl.kind for lvl in ls.levels}
    assert kinds == {"VWAP", "VWAP_UPPER_1", "VWAP_LOWER_1"}


def test_band_label_formatter():
    assert _format_band_label(1.0) == "1"
    assert _format_band_label(2.0) == "2"
    assert _format_band_label(1.5) == "1_5"
    assert _format_band_label(2.5) == "2_5"


# ---------------------------------------------------------------------------
# update_intraday parity with compute_levels
# ---------------------------------------------------------------------------


def test_update_intraday_matches_compute_levels_for_same_bar_stream():
    """Incremental ingest must equal batch ingest."""
    bars = trending_bars(20, start=100.0, step=0.05, volume=500.0)
    batch = VWAPSource()
    batch.compute_levels("X", mk_history(bars))

    incr = VWAPSource()
    # Bootstrap with empty history then feed bars one at a time.
    incr.compute_levels("X", mk_history([]))
    incr._session_date = bars[0].timestamp.date()  # type: ignore[attr-defined]
    incr._symbol = "X"  # type: ignore[attr-defined]
    for b in bars:
        incr.update_intraday(b)

    assert math.isclose(batch.vwap, incr.vwap, rel_tol=1e-12)
    assert math.isclose(batch.sigma, incr.sigma, rel_tol=1e-12)


def test_compute_levels_resets_state():
    """Calling compute_levels a second time starts fresh."""
    bars1 = flat_bars(5, price=10, volume=100)
    bars2 = flat_bars(3, price=50, volume=200)
    src = VWAPSource()
    src.compute_levels("X", mk_history(bars1))
    assert math.isclose(src.vwap, 10.0, rel_tol=1e-12)
    src.compute_levels("X", mk_history(bars2))
    assert math.isclose(src.vwap, 50.0, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Slope classifier
# ---------------------------------------------------------------------------


def test_classifier_flat_when_vwap_constant():
    src = VWAPSource()
    src.compute_levels("X", mk_history(flat_bars(20, price=100, volume=100)))
    assert src.vwap_slope_classifier(last_n_bars=10) == "flat"


def test_classifier_trending_up_for_monotonic_uptrend():
    src = VWAPSource()
    # 20 bars, +0.05/bar typical -> roughly +0.5% per bar after compounding
    bars = trending_bars(30, start=100.0, step=0.10, volume=100.0)
    src.compute_levels("X", mk_history(bars))
    assert src.vwap_slope_classifier(last_n_bars=10) == "trending_up"


def test_classifier_trending_down_for_monotonic_downtrend():
    src = VWAPSource()
    bars = trending_bars(30, start=100.0, step=-0.10, volume=100.0)
    src.compute_levels("X", mk_history(bars))
    assert src.vwap_slope_classifier(last_n_bars=10) == "trending_down"


def test_classifier_returns_flat_on_short_history():
    src = VWAPSource()
    src.compute_levels("X", mk_history([]))
    assert src.vwap_slope_classifier() == "flat"
    # One bar -> still flat.
    src.compute_levels("X", mk_history(flat_bars(1, price=50)))
    assert src.vwap_slope_classifier() == "flat"


def test_classifier_window_uses_only_last_n_bars():
    """Confirm last_n_bars slices the VWAP series — slope is computed only
    over the tail. We can't simply 'flatten' VWAP by adding flat-price bars
    because cumulative VWAP keeps converging toward the new price, but we
    CAN demonstrate the window mechanic by comparing slope-classifier with
    different window sizes on the same series.

    Construction: a series that gently up-trends for the first 100 bars,
    then ramps HARD up for the last 10. The full-series classifier should
    say trending_up; a window of just the last 5 (the ramp section) should
    say trending_up MORE strongly (slope_per_bar magnitude is larger when
    measured over the ramp alone).
    """
    base = trending_bars(100, start=10.0, step=0.001, volume=100.0)
    ramp_start = base[-1].close
    ramp = trending_bars(10, start=ramp_start, step=0.20, volume=100.0)
    for i in range(len(ramp)):
        b = ramp[i]
        ramp[i] = mk_bar(
            open=b.open, high=b.high, low=b.low, close=b.close,
            volume=b.volume, offset_min=100 + i,
        )
    src = VWAPSource()
    src.compute_levels("X", mk_history(base + ramp))
    # Both windows should classify as trending_up
    assert src.vwap_slope_classifier(last_n_bars=5) == "trending_up"
    # Slope magnitude over the tail should exceed slope over everything:
    short = abs(_linreg_slope(src.state.vwap_series[-5:]))
    long = abs(_linreg_slope(src.state.vwap_series))
    assert short > long


def test_classifier_threshold_is_price_invariant():
    """Two trends with the same percent slope should classify identically."""
    src_lo = VWAPSource()
    src_lo.compute_levels(
        "X",
        mk_history(trending_bars(30, start=10.0, step=0.005, volume=100.0)),
    )
    src_hi = VWAPSource()
    src_hi.compute_levels(
        "X",
        mk_history(trending_bars(30, start=1000.0, step=0.5, volume=100.0)),
    )
    assert src_lo.vwap_slope_classifier(last_n_bars=10) == src_hi.vwap_slope_classifier(last_n_bars=10)


def test_classifier_custom_flat_threshold():
    """A larger flat_pct_per_bar should reclassify a mild trend as flat."""
    src = VWAPSource()
    # +0.10/bar at start=100 -> well above default threshold
    bars = trending_bars(30, start=100.0, step=0.10, volume=100.0)
    src.compute_levels("X", mk_history(bars))
    # Default threshold -> trends.
    assert src.vwap_slope_classifier(last_n_bars=10) == "trending_up"
    # Aggressive threshold (1% / bar = 100bp/bar) -> reclassifies as flat.
    assert src.vwap_slope_classifier(last_n_bars=10, flat_pct_per_bar=0.01) == "flat"


# ---------------------------------------------------------------------------
# Diagnostics & metadata
# ---------------------------------------------------------------------------


def test_level_metadata_contains_sigma_and_slope():
    bars = trending_bars(20, start=100, step=0.05, volume=100)
    src = VWAPSource()
    ls = src.compute_levels("X", mk_history(bars))
    vwap_level = ls.by_kind("VWAP")[0]
    assert "sigma" in vwap_level.metadata
    assert "slope_per_bar" in vwap_level.metadata
    assert "n_bars" in vwap_level.metadata
    assert vwap_level.metadata["slope_per_bar"] > 0  # upward
    assert vwap_level.metadata["n_bars"] == 20
    band_level = ls.by_kind("VWAP_UPPER_1")[0]
    assert "n_sigma" in band_level.metadata
    assert math.isclose(band_level.metadata["n_sigma"], 1.0, rel_tol=1e-12)


def test_current_levelset_returns_consistent_set():
    """current_levelset() should match a fresh compute_levels() given the same data."""
    bars = trending_bars(15, start=100, step=0.10, volume=100)
    src = VWAPSource()
    ls = src.compute_levels("ABC", mk_history(bars))
    ls2 = src.current_levelset()
    # Same number + kinds of levels, same prices.
    kinds1 = sorted(lvl.kind for lvl in ls.levels)
    kinds2 = sorted(lvl.kind for lvl in ls2.levels)
    assert kinds1 == kinds2
    for kind in kinds1:
        a = ls.by_kind(kind)[0]
        b = ls2.by_kind(kind)[0]
        assert math.isclose(a.price, b.price, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Linear regression slope helper
# ---------------------------------------------------------------------------


def test_linreg_slope_simple_cases():
    # Constant -> 0
    assert _linreg_slope([5.0, 5.0, 5.0]) == 0.0
    # Pure ramp +1/step
    assert math.isclose(_linreg_slope([0.0, 1.0, 2.0, 3.0]), 1.0, rel_tol=1e-12)
    # Pure ramp -2/step
    assert math.isclose(_linreg_slope([10.0, 8.0, 6.0, 4.0]), -2.0, rel_tol=1e-12)


def test_linreg_slope_degenerate():
    # Empty, 1-element -> 0
    assert _linreg_slope([]) == 0.0
    assert _linreg_slope([42.0]) == 0.0


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_vwap_source_conforms_to_level_source_protocol():
    from framework.level_sources.base import LevelSourceProtocol
    src = VWAPSource()
    # Runtime-checkable protocol via duck-typing on the methods.
    assert isinstance(src, LevelSourceProtocol)


def test_levelset_session_date_from_first_bar():
    bars = flat_bars(2, price=10, volume=100)
    src = VWAPSource()
    ls = src.compute_levels("X", mk_history(bars))
    assert ls.session_date == bars[0].timestamp.date()
