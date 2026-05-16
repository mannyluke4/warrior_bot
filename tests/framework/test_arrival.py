"""Tests for framework.arrival — proximity-based level arrival edge cases."""
from __future__ import annotations

from datetime import date

import pytest

from framework.arrival import ArrivalDetector
from framework.level_sources.base import Level, LevelSet


SESSION = date(2026, 5, 15)


def _level_set(prices: list[float], symbol: str = "TEST") -> LevelSet:
    return LevelSet.from_iterable(
        symbol=symbol,
        session_date=SESSION,
        levels=[Level(price=p, kind="ROUND", session_date=SESSION) for p in prices],
    )


def test_requires_at_least_one_proximity() -> None:
    with pytest.raises(ValueError):
        ArrivalDetector()


def test_negative_proximity_rejected() -> None:
    with pytest.raises(ValueError):
        ArrivalDetector(proximity_pct=-0.001)
    with pytest.raises(ValueError):
        ArrivalDetector(proximity_dollar=-0.01)


def test_arrival_exact_level_match() -> None:
    det = ArrivalDetector(proximity_dollar=0.10)
    ls = _level_set([10.00, 11.00, 12.00])
    assert det.check_arrival("TEST", 11.00, ls).price == 11.00


def test_arrival_within_proximity_dollar() -> None:
    det = ArrivalDetector(proximity_dollar=0.10)
    ls = _level_set([10.00, 11.00, 12.00])
    assert det.check_arrival("TEST", 10.95, ls).price == 11.00
    assert det.check_arrival("TEST", 11.10, ls).price == 11.00


def test_arrival_just_outside_proximity() -> None:
    det = ArrivalDetector(proximity_dollar=0.10)
    ls = _level_set([10.00, 11.00, 12.00])
    # 10.85 is 0.15 below 11.00 -> outside 0.10 threshold; closest is 10.00
    # 10.85 - 10.00 = 0.85 also outside -> None
    assert det.check_arrival("TEST", 10.85, ls) is None


def test_arrival_just_inside_proximity_pct() -> None:
    det = ArrivalDetector(proximity_pct=0.01)  # 1%
    ls = _level_set([100.00, 110.00])
    # 1% of 100 = 1.00, so 99.50 is within proximity of 100
    assert det.check_arrival("TEST", 99.50, ls).price == 100.00
    # 98.99 is 1.01 below 100, outside threshold (1% of 98.99 = 0.99)
    assert det.check_arrival("TEST", 98.99, ls) is None


def test_arrival_picks_first_in_level_set_order() -> None:
    """If two levels are within proximity, the FIRST in level-set order wins."""
    det = ArrivalDetector(proximity_dollar=1.0)
    ls = _level_set([10.00, 10.50])
    # Both within 1.0 of 10.25; first-in-set is 10.00
    assert det.check_arrival("TEST", 10.25, ls).price == 10.00


def test_arrival_no_levels_returns_none() -> None:
    det = ArrivalDetector(proximity_dollar=0.10)
    assert det.check_arrival("TEST", 10.00, _level_set([])) is None


def test_arrival_threshold_uses_larger_of_pct_and_dollar() -> None:
    """When both are set, the LARGER of the two thresholds applies."""
    # At $100: pct gives 0.10, dollar gives 0.50 -> larger wins (0.50)
    det = ArrivalDetector(proximity_pct=0.001, proximity_dollar=0.50)
    ls = _level_set([100.00, 200.00])
    assert det.check_arrival("TEST", 99.60, ls).price == 100.00  # 0.40 dist < 0.50

    # At $200: pct gives 0.20, dollar gives 0.50 -> larger wins (0.50)
    assert det.check_arrival("TEST", 200.45, ls).price == 200.00


def test_arrival_symbol_mismatch_returns_none() -> None:
    det = ArrivalDetector(proximity_dollar=0.10)
    ls = _level_set([10.00, 11.00], symbol="ABC")
    assert det.check_arrival("XYZ", 10.00, ls) is None
