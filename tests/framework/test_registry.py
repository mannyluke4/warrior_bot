"""Tests for framework.registry — YAML loader and StrategySpec instantiation."""
from __future__ import annotations

from pathlib import Path

import pytest

from framework.arrival import ArrivalDetector
from framework.registry import (
    ConfirmationStub,
    LevelSourceStub,
    StrategyRegistry,
    StrategySpec,
)
from framework.targets import CompositeTarget


SAMPLE_YAML = (
    Path(__file__).resolve().parents[2] / "framework" / "sample_strategy.yaml"
)


def _fresh_registry() -> StrategyRegistry:
    StrategyRegistry.reset_default()
    return StrategyRegistry()


def test_sample_yaml_loads_end_to_end() -> None:
    """The full sample YAML should parse, validate, and instantiate plugins."""
    reg = _fresh_registry()
    spec = reg.load_yaml(SAMPLE_YAML)

    assert isinstance(spec, StrategySpec)
    assert spec.name == "Sample-Round-Number-Demo"
    assert spec.enabled is True
    assert spec.risk_per_trade_pct == 1.0
    assert spec.max_concurrent_positions == 3
    assert spec.trade_windows == (("09:35", "11:30"), ("13:30", "15:55"))


def test_loader_instantiates_correct_plugin_types() -> None:
    reg = _fresh_registry()
    spec = reg.load_yaml(SAMPLE_YAML)

    # Level source + confirmation are stubs in Wave 1
    assert isinstance(spec.level_source, LevelSourceStub)
    assert spec.level_source.type == "round_number"
    assert "increments" in spec.level_source.params

    assert isinstance(spec.confirmation_rule, ConfirmationStub)
    assert spec.confirmation_rule.type == "signal_candle"

    # Arrival is concrete
    assert isinstance(spec.arrival_detector, ArrivalDetector)
    assert spec.arrival_detector.proximity_pct == 0.001
    assert spec.arrival_detector.proximity_dollar == 0.10

    # Stop is concrete
    from framework.stops import JustPastLevel

    assert isinstance(spec.stop_rule, JustPastLevel)
    assert spec.stop_rule.pad_dollar == 0.05

    # Target is composite
    assert isinstance(spec.target_rule, CompositeTarget)
    assert spec.target_rule.primary is not None
    assert spec.target_rule.fallback is not None
    assert spec.target_rule.trailing is not None


def test_registry_get_and_list_enabled() -> None:
    reg = _fresh_registry()
    spec = reg.load_yaml(SAMPLE_YAML)
    assert reg.get(spec.name) is spec
    assert spec in reg.list_enabled()
    assert spec in reg.list_all()
    assert len(reg) == 1
    assert spec.name in reg


def test_registry_get_missing_raises() -> None:
    reg = _fresh_registry()
    with pytest.raises(KeyError):
        reg.get("does-not-exist")


def test_disabled_strategy_excluded_from_list_enabled() -> None:
    reg = _fresh_registry()
    spec_dict = {
        "name": "DisabledOne",
        "enabled": False,
        "level_source": {"type": "round_number"},
        "arrival_detector": {
            "type": "proximity",
            "params": {"proximity_pct": 0.001},
        },
        "confirmation_rule": {"type": "signal_candle"},
        "stop_rule": {"type": "just_past_level", "params": {"pad_dollar": 0.05}},
        "target_rule": {"type": "r_multiple", "params": {"r_multiple": 2.0}},
        "risk_per_trade_pct": 1.0,
        "max_concurrent_positions": 1,
        "trade_windows": [["09:30", "15:55"]],
    }
    spec = reg.load_dict(spec_dict)
    assert spec.enabled is False
    assert spec not in reg.list_enabled()
    assert spec in reg.list_all()


def test_registry_default_singleton() -> None:
    StrategyRegistry.reset_default()
    a = StrategyRegistry.default()
    b = StrategyRegistry.default()
    assert a is b
    StrategyRegistry.reset_default()
    c = StrategyRegistry.default()
    assert c is not a


def test_register_directly_round_trip() -> None:
    """`registry.register(spec)` lets callers add hand-built specs."""
    reg = _fresh_registry()
    spec_dict = {
        "name": "HandBuilt",
        "level_source": {"type": "vwap"},
        "arrival_detector": {
            "type": "proximity",
            "params": {"proximity_pct": 0.002},
        },
        "confirmation_rule": {"type": "breakout_candle"},
        "stop_rule": {"type": "bar_low", "params": {"lookback": 3}},
        "target_rule": {"type": "r_multiple", "params": {"r_multiple": 2.0}},
        "risk_per_trade_pct": 0.5,
        "max_concurrent_positions": 2,
        "trade_windows": [["09:30", "15:55"]],
    }
    spec = reg.load_dict(spec_dict)
    assert reg.get("HandBuilt") is spec
