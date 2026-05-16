"""Unit tests for framework.level_sources.opening_range.

Synthetic-bar tests that cover:

* Canonical 5-min OR construction from naïve ET timestamps.
* Configurable `minutes` (15, 30) — sensitivity-analysis path.
* Direction bias from the opening 1-min bar (long / short / neutral).
* `update_intraday` is a no-op (OR is fixed once computed).
* Edge cases: empty history, partial window, missing 09:30 anchor,
  UTC timestamps (session_open_local=False), `require_full_window=False`.

Synthetic data convention: timestamps are naïve `datetime(YYYY, M, D, h, m)`
treated as ET. Volumes/prices are integers for clarity. The session date
threaded into Levels comes from the first bar's date.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from framework.level_sources.base import Bar, BarHistory, Level, LevelSet
from framework.level_sources.opening_range import OpeningRangeSource


# ----- helpers ------------------------------------------------------------


def _bar(
    h: int,
    m: int,
    o: float,
    high: float,
    low: float,
    c: float,
    v: float = 1000,
    d: date = date(2024, 1, 16),
) -> Bar:
    """Build a Bar with naïve ET timestamp (h, m) on `d`."""
    return Bar(
        timestamp=datetime(d.year, d.month, d.day, h, m),
        open=o,
        high=high,
        low=low,
        close=c,
        volume=v,
        symbol="TEST",
    )


def _history(*bars: Bar, symbol: str = "TEST") -> BarHistory:
    h = BarHistory(symbol=symbol)
    for b in bars:
        h.append(b)
    return h


# ----- canonical 5-min ORB ------------------------------------------------


def test_5min_orb_basic() -> None:
    src = OpeningRangeSource(minutes=5)
    h = _history(
        _bar(9, 30, 100.00, 101.00, 99.50, 100.80),   # opening bar — green
        _bar(9, 31, 100.80, 101.50, 100.50, 101.20),
        _bar(9, 32, 101.20, 101.80, 100.90, 101.50),
        _bar(9, 33, 101.50, 102.20, 101.30, 102.00),  # OR high here
        _bar(9, 34, 102.00, 102.10, 100.80, 101.00),
        _bar(9, 35, 101.00, 101.20, 100.70, 100.90),  # OUT of window
    )
    ls = src.compute_levels("TEST", h)
    assert ls.symbol == "TEST"
    assert ls.session_date == date(2024, 1, 16)
    kinds = {lvl.kind for lvl in ls.levels}
    assert kinds == {"ORH", "ORL"}
    orh = next(l for l in ls.levels if l.kind == "ORH").price
    orl = next(l for l in ls.levels if l.kind == "ORL").price
    assert orh == pytest.approx(102.20)
    assert orl == pytest.approx(99.50)


def test_5min_orb_excludes_bars_after_window() -> None:
    """The 09:35 bar must NOT be included in the 5-min OR."""
    src = OpeningRangeSource(minutes=5)
    h = _history(
        _bar(9, 30, 100, 100.5, 99, 100),
        _bar(9, 31, 100, 100, 100, 100),
        _bar(9, 32, 100, 100, 100, 100),
        _bar(9, 33, 100, 100, 100, 100),
        _bar(9, 34, 100, 100, 100, 100),
        _bar(9, 35, 100, 999, 50, 100),  # huge bar AFTER window — must be ignored
    )
    ls = src.compute_levels("TEST", h)
    orh = next(l for l in ls.levels if l.kind == "ORH").price
    orl = next(l for l in ls.levels if l.kind == "ORL").price
    assert orh == pytest.approx(100.5)
    assert orl == pytest.approx(99.0)


def test_15min_orb_sensitivity_variant() -> None:
    src = OpeningRangeSource(minutes=15)
    bars = [_bar(9, 30 + i, 100 + i * 0.1, 100 + i * 0.1 + 0.5, 100 + i * 0.1 - 0.5, 100 + i * 0.1)
            for i in range(20)]
    h = _history(*bars)
    ls = src.compute_levels("TEST", h)
    orh = next(l for l in ls.levels if l.kind == "ORH").price
    orl = next(l for l in ls.levels if l.kind == "ORL").price
    # OR window is bars at minutes 30..44 (15 bars). Last opening bar starts
    # at minute 44 with open = 100 + 14*0.1 = 101.4, high = 101.9.
    assert orh == pytest.approx(101.9)
    assert orl == pytest.approx(99.5)


def test_30min_orb_sensitivity_variant() -> None:
    src = OpeningRangeSource(minutes=30)
    # 35 bars: 30 inside window, 5 outside.
    bars = []
    for i in range(35):
        bars.append(_bar(9, 30 + i if 9 * 60 + 30 + i < 10 * 60 else 0,  # noqa: invalid for h>9
                         100, 100, 100, 100))
    # Build correctly with explicit minutes/hours that increment past 09:59
    bars = []
    base = datetime(2024, 1, 16, 9, 30)
    for i in range(35):
        ts = base + timedelta(minutes=i)
        bars.append(Bar(timestamp=ts, open=100.0 + i * 0.01, high=100.0 + i * 0.01 + 0.5,
                        low=100.0 + i * 0.01 - 0.5, close=100.0 + i * 0.01, volume=1000))
    h = _history(*bars)
    ls = src.compute_levels("TEST", h)
    orh = next(l for l in ls.levels if l.kind == "ORH").price
    orl = next(l for l in ls.levels if l.kind == "ORL").price
    # OR window is bars at minutes 30..59 (30 bars). Last opening bar's
    # open = 100 + 29*0.01 = 100.29, high = 100.79
    assert orh == pytest.approx(100.79)
    assert orl == pytest.approx(99.5)


# ----- direction bias -----------------------------------------------------


def test_direction_bias_long() -> None:
    src = OpeningRangeSource(minutes=5)
    h = _history(
        _bar(9, 30, 100.0, 101.0, 99.5, 100.8),  # green: close > open
        _bar(9, 31, 100.8, 101.0, 100.5, 100.9),
        _bar(9, 32, 100.9, 101.1, 100.6, 101.0),
        _bar(9, 33, 101.0, 101.2, 100.7, 101.1),
        _bar(9, 34, 101.1, 101.3, 100.8, 101.2),
    )
    ls = src.compute_levels("TEST", h)
    orh_level = next(l for l in ls.levels if l.kind == "ORH")
    assert orh_level.metadata["direction_bias"] == "long"


def test_direction_bias_short() -> None:
    src = OpeningRangeSource(minutes=5)
    h = _history(
        _bar(9, 30, 100.0, 100.5, 99.0, 99.2),   # red: close < open
        _bar(9, 31, 99.2, 99.5, 99.0, 99.4),
        _bar(9, 32, 99.4, 99.6, 99.1, 99.5),
        _bar(9, 33, 99.5, 99.7, 99.2, 99.6),
        _bar(9, 34, 99.6, 99.8, 99.3, 99.7),
    )
    ls = src.compute_levels("TEST", h)
    orh_level = next(l for l in ls.levels if l.kind == "ORH")
    assert orh_level.metadata["direction_bias"] == "short"


def test_direction_bias_neutral_on_doji() -> None:
    src = OpeningRangeSource(minutes=5)
    h = _history(
        _bar(9, 30, 100.0, 100.5, 99.5, 100.0),  # doji: close == open
        _bar(9, 31, 100.0, 100.2, 99.8, 100.0),
        _bar(9, 32, 100.0, 100.2, 99.8, 100.0),
        _bar(9, 33, 100.0, 100.2, 99.8, 100.0),
        _bar(9, 34, 100.0, 100.2, 99.8, 100.0),
    )
    ls = src.compute_levels("TEST", h)
    orh_level = next(l for l in ls.levels if l.kind == "ORH")
    assert orh_level.metadata["direction_bias"] == "neutral"


def test_direction_bias_disabled() -> None:
    src = OpeningRangeSource(minutes=5, use_5min_direction_bias=False)
    h = _history(
        _bar(9, 30, 100.0, 101.0, 99.5, 100.8),  # would be "long"
        _bar(9, 31, 100.8, 101.0, 100.5, 100.9),
        _bar(9, 32, 100.9, 101.1, 100.6, 101.0),
        _bar(9, 33, 101.0, 101.2, 100.7, 101.1),
        _bar(9, 34, 101.1, 101.3, 100.8, 101.2),
    )
    ls = src.compute_levels("TEST", h)
    orh_level = next(l for l in ls.levels if l.kind == "ORH")
    assert orh_level.metadata["direction_bias"] == "neutral"


# ----- update_intraday no-op ---------------------------------------------


def test_update_intraday_is_noop() -> None:
    src = OpeningRangeSource(minutes=5)
    # update_intraday should never raise and never change emitted levels.
    src.update_intraday(_bar(10, 15, 105, 106, 104, 105))
    # Idempotence: calling compute_levels before and after produces the same
    # LevelSet content.
    h = _history(
        _bar(9, 30, 100.0, 101.0, 99.5, 100.8),
        _bar(9, 31, 100.8, 101.0, 100.5, 100.9),
        _bar(9, 32, 100.9, 101.1, 100.6, 101.0),
        _bar(9, 33, 101.0, 101.2, 100.7, 101.1),
        _bar(9, 34, 101.1, 101.3, 100.8, 101.2),
    )
    ls1 = src.compute_levels("TEST", h)
    src.update_intraday(_bar(10, 30, 110, 111, 109, 110.5))
    ls2 = src.compute_levels("TEST", h)
    assert {(l.kind, l.price) for l in ls1.levels} == {(l.kind, l.price) for l in ls2.levels}


# ----- edge cases ---------------------------------------------------------


def test_empty_history_returns_empty_levelset() -> None:
    src = OpeningRangeSource(minutes=5)
    ls = src.compute_levels("EMPTY", BarHistory(symbol="EMPTY"))
    assert ls.symbol == "EMPTY"
    assert ls.levels == ()


def test_no_opening_anchor_returns_empty() -> None:
    """If there's no 09:30 bar, no OR can be computed."""
    src = OpeningRangeSource(minutes=5)
    h = _history(
        _bar(10, 0, 100, 101, 99, 100.5),
        _bar(10, 1, 100.5, 101.5, 100, 101),
    )
    ls = src.compute_levels("TEST", h)
    assert ls.levels == ()


def test_partial_window_with_require_full_window_returns_empty() -> None:
    """If only 3 of 5 bars are present in the OR window, default rejects it."""
    src = OpeningRangeSource(minutes=5, require_full_window=True)
    h = _history(
        _bar(9, 30, 100, 101, 99.5, 100.5),
        _bar(9, 31, 100.5, 101.2, 100, 101),
        _bar(9, 32, 101, 101.5, 100.5, 101.2),
        # Missing 9:33, 9:34
    )
    ls = src.compute_levels("TEST", h)
    assert ls.levels == ()


def test_partial_window_without_require_full_window_builds_from_available() -> None:
    """With require_full_window=False, OR is built from whatever's available."""
    src = OpeningRangeSource(minutes=5, require_full_window=False)
    h = _history(
        _bar(9, 30, 100, 101.50, 99.50, 100.5),
        _bar(9, 31, 100.5, 101.20, 100.00, 101),
        _bar(9, 32, 101, 101.80, 100.50, 101.2),
    )
    ls = src.compute_levels("TEST", h)
    orh = next(l for l in ls.levels if l.kind == "ORH").price
    orl = next(l for l in ls.levels if l.kind == "ORL").price
    assert orh == pytest.approx(101.80)
    assert orl == pytest.approx(99.50)


def test_invalid_minutes_raises() -> None:
    src = OpeningRangeSource(minutes=0)
    h = _history(_bar(9, 30, 100, 101, 99, 100))
    with pytest.raises(ValueError, match="minutes must be > 0"):
        src.compute_levels("TEST", h)


def test_utc_timestamps_via_session_open_local_false() -> None:
    """When timestamps are UTC, the source should match the 14:30 UTC anchor (EST)."""
    src = OpeningRangeSource(minutes=5, session_open_local=False)
    # Use 14:30 UTC = 09:30 EST as anchor
    bars = []
    base = datetime(2024, 1, 16, 14, 30)  # 14:30 UTC = 09:30 EST in Jan
    for i in range(5):
        ts = base + timedelta(minutes=i)
        bars.append(Bar(timestamp=ts, open=100 + i, high=100 + i + 0.5,
                        low=100 + i - 0.5, close=100 + i + 0.3, volume=1000))
    h = _history(*bars)
    ls = src.compute_levels("TEST", h)
    assert len(ls.levels) == 2
    orh = next(l for l in ls.levels if l.kind == "ORH").price
    assert orh == pytest.approx(104.5)  # last bar high: 100+4+0.5


def test_metadata_includes_or_high_low_and_volume() -> None:
    src = OpeningRangeSource(minutes=5)
    h = _history(
        _bar(9, 30, 100, 101.5, 99.5, 100.8, v=500),
        _bar(9, 31, 100.8, 101.2, 100.5, 101, v=600),
        _bar(9, 32, 101, 101.5, 100.7, 101.2, v=700),
        _bar(9, 33, 101.2, 101.8, 100.9, 101.4, v=800),
        _bar(9, 34, 101.4, 101.6, 100.8, 101.2, v=900),
    )
    ls = src.compute_levels("TEST", h)
    orh_meta = next(l for l in ls.levels if l.kind == "ORH").metadata
    assert orh_meta["opening_range_minutes"] == 5
    assert orh_meta["opening_range_volume"] == 3500
    assert orh_meta["opening_range_high"] == pytest.approx(101.8)
    assert orh_meta["opening_range_low"] == pytest.approx(99.5)


def test_session_date_taken_from_opening_bar() -> None:
    src = OpeningRangeSource(minutes=5)
    h = _history(
        _bar(9, 30, 100, 101, 99.5, 100.5, d=date(2024, 3, 15)),
        _bar(9, 31, 100.5, 101, 100, 100.8, d=date(2024, 3, 15)),
        _bar(9, 32, 100.8, 101.2, 100.5, 101, d=date(2024, 3, 15)),
        _bar(9, 33, 101, 101.3, 100.8, 101.1, d=date(2024, 3, 15)),
        _bar(9, 34, 101.1, 101.2, 100.9, 101, d=date(2024, 3, 15)),
    )
    ls = src.compute_levels("TEST", h)
    assert ls.session_date == date(2024, 3, 15)
    for lvl in ls.levels:
        assert lvl.session_date == date(2024, 3, 15)


def test_protocol_compliance() -> None:
    """OpeningRangeSource conforms to LevelSourceProtocol."""
    from framework.level_sources.base import LevelSourceProtocol

    src = OpeningRangeSource(minutes=5)
    assert isinstance(src, LevelSourceProtocol)
