"""Tests for framework.targets — every built-in target rule on synthetic inputs."""
from __future__ import annotations

from datetime import date

import pytest

from framework.level_sources.base import BarHistory, Level, LevelSet
from framework.targets import (
    CompositeTarget,
    EdgeToEdge,
    OppositeLevel,
    RMultiple,
    SessionClose,
    TrailingATR,
)


SESSION = date(2026, 5, 15)


def _level(price: float, kind: str = "ROUND") -> Level:
    return Level(price=price, kind=kind, session_date=SESSION)


def _level_set(prices: list[float], symbol: str = "TEST") -> LevelSet:
    return LevelSet.from_iterable(
        symbol=symbol,
        session_date=SESSION,
        levels=[_level(p) for p in prices],
    )


def _empty_history(symbol: str = "TEST") -> BarHistory:
    return BarHistory(symbol=symbol)


# ---- OppositeLevel ---------------------------------------------------------


def test_opposite_level_long_picks_lowest_above_entry() -> None:
    rule = OppositeLevel()
    ls = _level_set([10.00, 10.50, 11.00, 12.00])
    out = rule.compute_target(
        entry_price=10.25,
        level=_level(10.00),
        level_set=ls,
        history=_empty_history(),
        direction="long",
    )
    assert out.primary_price == 10.50


def test_opposite_level_short_picks_highest_below_entry() -> None:
    rule = OppositeLevel()
    ls = _level_set([10.00, 10.50, 11.00, 12.00])
    out = rule.compute_target(
        entry_price=10.75,
        level=_level(11.00),
        level_set=ls,
        history=_empty_history(),
        direction="short",
    )
    assert out.primary_price == 10.50


def test_opposite_level_no_higher_level_returns_none() -> None:
    rule = OppositeLevel()
    ls = _level_set([10.00, 10.50])
    out = rule.compute_target(11.0, _level(10.50), ls, _empty_history(), "long")
    assert out.primary_price is None
    assert out.metadata.get("reason") == "no_higher_level"


# ---- RMultiple -------------------------------------------------------------


def test_r_multiple_long() -> None:
    rule = RMultiple(r=2.0)
    out = rule.compute_target(
        entry_price=10.00,
        level=_level(10.00),
        level_set=_level_set([]),
        history=_empty_history(),
        direction="long",
        stop_price=9.80,
    )
    # 1R = 0.20 -> 2R target = 10.40
    assert out.primary_price == pytest.approx(10.40)


def test_r_multiple_short() -> None:
    rule = RMultiple(r=2.0)
    out = rule.compute_target(
        entry_price=10.00,
        level=_level(10.00),
        level_set=_level_set([]),
        history=_empty_history(),
        direction="short",
        stop_price=10.20,
    )
    assert out.primary_price == pytest.approx(9.60)


def test_r_multiple_requires_stop() -> None:
    rule = RMultiple(r=2.0)
    out = rule.compute_target(10.0, _level(10.0), _level_set([]), _empty_history(), "long")
    assert out.primary_price is None


# ---- SessionClose ----------------------------------------------------------


def test_session_close_flags_close_exit() -> None:
    rule = SessionClose()
    out = rule.compute_target(10.0, _level(10.0), _level_set([]), _empty_history(), "long")
    assert out.primary_price is None
    assert out.session_close_exit is True


# ---- EdgeToEdge ------------------------------------------------------------


def test_edge_to_edge_long_picks_max() -> None:
    rule = EdgeToEdge()
    ls = _level_set([9.50, 10.00, 10.50, 11.00, 12.00])
    out = rule.compute_target(10.00, _level(10.00), ls, _empty_history(), "long")
    assert out.primary_price == 12.00


def test_edge_to_edge_short_picks_min() -> None:
    rule = EdgeToEdge()
    ls = _level_set([9.50, 10.00, 10.50, 11.00, 12.00])
    out = rule.compute_target(10.50, _level(10.50), ls, _empty_history(), "short")
    assert out.primary_price == 9.50


def test_edge_to_edge_empty_set_returns_none() -> None:
    rule = EdgeToEdge()
    out = rule.compute_target(10.0, _level(10.0), _level_set([]), _empty_history(), "long")
    assert out.primary_price is None


# ---- TrailingATR -----------------------------------------------------------


def test_trailing_atr_emits_trailing_policy() -> None:
    rule = TrailingATR(atr_mult=1.5, activate_at_r=1.5)
    out = rule.compute_target(10.0, _level(10.0), _level_set([]), _empty_history(), "long")
    assert out.primary_price is None
    assert out.trailing == {"activate_at_r": 1.5, "atr_mult": 1.5}


# ---- CompositeTarget -------------------------------------------------------


def test_composite_primary_used_when_resolves() -> None:
    composite = CompositeTarget(
        primary=OppositeLevel(),
        fallback=RMultiple(r=2.0),
        trailing=TrailingATR(atr_mult=1.5, activate_at_r=1.5),
    )
    ls = _level_set([10.00, 10.50, 11.00])
    out = composite.compute_target(10.25, _level(10.00), ls, _empty_history(), "long", stop_price=9.90)
    assert out.primary_price == 10.50
    assert out.trailing == {"activate_at_r": 1.5, "atr_mult": 1.5}


def test_composite_fallback_used_when_primary_yields_none() -> None:
    composite = CompositeTarget(
        primary=OppositeLevel(),
        fallback=RMultiple(r=2.0),
    )
    # No higher levels -> OppositeLevel returns None -> fallback engages
    ls = _level_set([9.00, 9.50])
    out = composite.compute_target(10.0, _level(10.0), ls, _empty_history(), "long", stop_price=9.80)
    assert out.primary_price == pytest.approx(10.40)


def test_composite_without_fallback_returns_none_when_primary_none() -> None:
    composite = CompositeTarget(primary=OppositeLevel())
    ls = _level_set([9.00])
    out = composite.compute_target(10.0, _level(10.0), ls, _empty_history(), "long", stop_price=9.80)
    assert out.primary_price is None
