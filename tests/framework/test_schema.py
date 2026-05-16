"""Tests for framework.yaml_schema — invalid specs rejected with clear errors."""
from __future__ import annotations

import copy

import pytest

from framework.yaml_schema import SchemaError, validate_strategy_spec


VALID_SPEC = {
    "name": "Test-Strategy",
    "enabled": True,
    "level_source": {"type": "round_number", "params": {}},
    "arrival_detector": {
        "type": "proximity",
        "params": {"proximity_pct": 0.001},
    },
    "confirmation_rule": {"type": "signal_candle", "params": {}},
    "stop_rule": {"type": "just_past_level", "params": {"pad_dollar": 0.05}},
    "target_rule": {"type": "r_multiple", "params": {"r_multiple": 2.0}},
    "risk_per_trade_pct": 1.0,
    "max_concurrent_positions": 3,
    "trade_windows": [["09:30", "15:55"]],
}


def test_valid_spec_passes() -> None:
    validate_strategy_spec(VALID_SPEC)


@pytest.mark.parametrize(
    "key",
    [
        "name",
        "level_source",
        "arrival_detector",
        "confirmation_rule",
        "stop_rule",
        "target_rule",
        "risk_per_trade_pct",
        "max_concurrent_positions",
        "trade_windows",
    ],
)
def test_missing_required_key_rejected(key: str) -> None:
    spec = copy.deepcopy(VALID_SPEC)
    del spec[key]
    with pytest.raises(SchemaError) as exc:
        validate_strategy_spec(spec)
    assert key in str(exc.value)


def test_arrival_requires_some_proximity() -> None:
    spec = copy.deepcopy(VALID_SPEC)
    spec["arrival_detector"] = {"type": "proximity", "params": {}}
    with pytest.raises(SchemaError) as exc:
        validate_strategy_spec(spec)
    assert "proximity" in str(exc.value)
    assert "arrival_detector" in exc.value.path


def test_arrival_type_must_be_proximity() -> None:
    spec = copy.deepcopy(VALID_SPEC)
    spec["arrival_detector"]["type"] = "spike"
    with pytest.raises(SchemaError) as exc:
        validate_strategy_spec(spec)
    assert "proximity" in str(exc.value)


def test_unknown_stop_rule_rejected() -> None:
    spec = copy.deepcopy(VALID_SPEC)
    spec["stop_rule"]["type"] = "magic_stop"
    with pytest.raises(SchemaError) as exc:
        validate_strategy_spec(spec)
    assert "magic_stop" in str(exc.value)


def test_unknown_target_rule_rejected() -> None:
    spec = copy.deepcopy(VALID_SPEC)
    spec["target_rule"]["type"] = "tarot_card"
    with pytest.raises(SchemaError) as exc:
        validate_strategy_spec(spec)
    assert "tarot_card" in str(exc.value)


def test_composite_target_accepted() -> None:
    spec = copy.deepcopy(VALID_SPEC)
    spec["target_rule"] = {
        "type": "composite",
        "params": {"primary": "opposite_level", "fallback": "r_multiple", "r_multiple": 2.0},
    }
    validate_strategy_spec(spec)


def test_negative_risk_rejected() -> None:
    spec = copy.deepcopy(VALID_SPEC)
    spec["risk_per_trade_pct"] = -0.5
    with pytest.raises(SchemaError):
        validate_strategy_spec(spec)


def test_zero_max_positions_rejected() -> None:
    spec = copy.deepcopy(VALID_SPEC)
    spec["max_concurrent_positions"] = 0
    with pytest.raises(SchemaError):
        validate_strategy_spec(spec)


def test_max_positions_must_be_int() -> None:
    spec = copy.deepcopy(VALID_SPEC)
    spec["max_concurrent_positions"] = 3.5
    with pytest.raises(SchemaError):
        validate_strategy_spec(spec)


def test_trade_window_bad_time_rejected() -> None:
    spec = copy.deepcopy(VALID_SPEC)
    spec["trade_windows"] = [["09:30", "25:99"]]
    with pytest.raises(SchemaError) as exc:
        validate_strategy_spec(spec)
    assert "HH:MM" in str(exc.value)


def test_trade_window_wrong_arity_rejected() -> None:
    spec = copy.deepcopy(VALID_SPEC)
    spec["trade_windows"] = [["09:30"]]
    with pytest.raises(SchemaError):
        validate_strategy_spec(spec)


def test_empty_trade_windows_rejected() -> None:
    spec = copy.deepcopy(VALID_SPEC)
    spec["trade_windows"] = []
    with pytest.raises(SchemaError):
        validate_strategy_spec(spec)


def test_name_must_be_non_empty() -> None:
    spec = copy.deepcopy(VALID_SPEC)
    spec["name"] = ""
    with pytest.raises(SchemaError):
        validate_strategy_spec(spec)


def test_top_level_must_be_dict() -> None:
    with pytest.raises(SchemaError):
        validate_strategy_spec(["not", "a", "dict"])


def test_schema_error_carries_path() -> None:
    spec = copy.deepcopy(VALID_SPEC)
    spec["arrival_detector"]["type"] = "spike"
    with pytest.raises(SchemaError) as exc:
        validate_strategy_spec(spec)
    assert "arrival_detector" in exc.value.path


def test_arrival_proximity_dollar_as_dict_accepted() -> None:
    """YAML spec for tiered price proximity uses dict; should validate."""
    spec = copy.deepcopy(VALID_SPEC)
    spec["arrival_detector"] = {
        "type": "proximity",
        "params": {"proximity_dollar": {"10_50": 0.10, "50_150": 0.25}},
    }
    validate_strategy_spec(spec)
