"""Tests for framework.stops — every built-in stop rule on synthetic inputs."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from framework.level_sources.base import Bar, BarHistory, Level
from framework.stops import (
    BarLow,
    InLVN,
    JustPastLevel,
    OppositeRange,
)


def _level(price: float, kind: str = "ROUND") -> Level:
    return Level(price=price, kind=kind, session_date=date(2026, 5, 15))


def _bar(ts_min: int, o: float, h: float, l: float, c: float, v: float = 1000) -> Bar:
    return Bar(
        timestamp=datetime(2026, 5, 15, 9, 30 + ts_min),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
    )


def _history(*bars: Bar, symbol: str = "TEST") -> BarHistory:
    h = BarHistory(symbol=symbol)
    for b in bars:
        h.append(b)
    return h


# ---- JustPastLevel ---------------------------------------------------------


def test_just_past_level_long() -> None:
    rule = JustPastLevel(pad_dollar=0.05)
    out = rule.compute_stop(entry_price=10.10, level=_level(10.00), history=_history(), direction="long")
    assert out == pytest.approx(9.95)


def test_just_past_level_short() -> None:
    rule = JustPastLevel(pad_dollar=0.05)
    out = rule.compute_stop(entry_price=9.90, level=_level(10.00), history=_history(), direction="short")
    assert out == pytest.approx(10.05)


def test_just_past_level_zero_pad() -> None:
    rule = JustPastLevel(pad_dollar=0.0)
    assert rule.compute_stop(10.10, _level(10.00), _history(), "long") == 10.00


# ---- OppositeRange ---------------------------------------------------------


def test_opposite_range_long() -> None:
    rule = OppositeRange(opening_range_high=11.00, opening_range_low=10.50)
    out = rule.compute_stop(11.05, _level(11.00, "ORH"), _history(), "long")
    assert out == 10.50


def test_opposite_range_short() -> None:
    rule = OppositeRange(opening_range_high=11.00, opening_range_low=10.50)
    out = rule.compute_stop(10.45, _level(10.50, "ORL"), _history(), "short")
    assert out == 11.00


# ---- InLVN -----------------------------------------------------------------


def test_in_lvn_long_picks_highest_lvn_below_entry() -> None:
    rule = InLVN(lvn_levels=(9.50, 9.80, 10.30), pad_dollar=0.02)
    out = rule.compute_stop(10.10, _level(10.00), _history(), "long")
    # Highest LVN below 10.10 is 9.80; subtract pad
    assert out == pytest.approx(9.78)


def test_in_lvn_short_picks_lowest_lvn_above_entry() -> None:
    rule = InLVN(lvn_levels=(9.50, 10.20, 10.50), pad_dollar=0.02)
    out = rule.compute_stop(10.10, _level(10.00), _history(), "short")
    assert out == pytest.approx(10.22)


def test_in_lvn_no_candidates_falls_back_to_just_past_level() -> None:
    rule = InLVN(lvn_levels=(10.50, 11.00), pad_dollar=0.05)
    # All LVNs are ABOVE entry; long direction has no candidate -> fallback
    out = rule.compute_stop(10.10, _level(10.00), _history(), "long")
    assert out == pytest.approx(9.95)


def test_in_lvn_empty_falls_back() -> None:
    rule = InLVN(lvn_levels=(), pad_dollar=0.05)
    out = rule.compute_stop(10.10, _level(10.00), _history(), "long")
    assert out == pytest.approx(9.95)


# ---- BarLow ----------------------------------------------------------------


def test_bar_low_long_uses_min_of_lookback() -> None:
    rule = BarLow(lookback=3, pad_dollar=0.02)
    h = _history(
        _bar(0, 10.0, 10.5, 9.80, 10.30),
        _bar(1, 10.3, 10.7, 10.10, 10.50),
        _bar(2, 10.5, 10.8, 10.20, 10.60),
    )
    # Min low across last 3 bars = 9.80
    assert rule.compute_stop(10.60, _level(10.00), h, "long") == pytest.approx(9.78)


def test_bar_low_short_uses_max_of_lookback() -> None:
    rule = BarLow(lookback=3, pad_dollar=0.02)
    h = _history(
        _bar(0, 10.0, 10.50, 9.80, 10.30),
        _bar(1, 10.3, 10.70, 10.10, 10.50),
        _bar(2, 10.5, 10.85, 10.20, 10.60),
    )
    # Max high across last 3 bars = 10.85
    assert rule.compute_stop(9.90, _level(10.00), h, "short") == pytest.approx(10.87)


def test_bar_low_lookback_truncates_to_available() -> None:
    rule = BarLow(lookback=10, pad_dollar=0.02)
    h = _history(_bar(0, 10.0, 10.5, 9.90, 10.30))
    assert rule.compute_stop(10.10, _level(10.00), h, "long") == pytest.approx(9.88)


def test_bar_low_empty_history_falls_back() -> None:
    rule = BarLow(lookback=3, pad_dollar=0.05)
    out = rule.compute_stop(10.10, _level(10.00), _history(), "long")
    # Falls back to JustPastLevel with same pad
    assert out == pytest.approx(9.95)
