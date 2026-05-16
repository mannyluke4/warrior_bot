"""Lightweight YAML-spec validator for the healthy-fluctuation framework.

This is intentionally NOT a full jsonschema implementation — it's a focused
validator that enforces the shape we expect from strategy YAML files and
emits clear error messages with the failing path.

Used by `registry.StrategyRegistry.load_yaml()` to fail fast on malformed
specs before plugin instantiation, where errors would be cryptic.

Schema (informal):

    name: str (required)
    enabled: bool (default true)
    level_source:
        type: str (required)
        params: dict (optional)
    arrival_detector:
        type: 'proximity' (required)
        params: { proximity_pct: float? , proximity_dollar: float|dict? }
            at least one of the two required
    confirmation_rule:
        type: str (required)
        params: dict (optional)
    stop_rule:
        type: str (required, must be in STOP_RULES or 'composite')
        params: dict (optional)
    target_rule:
        type: str (required, must be in TARGET_RULES or 'composite')
        params: dict (optional)
    risk_per_trade_pct: float (required, > 0)
    max_concurrent_positions: int (required, > 0)
    trade_windows: list[[str, str]] (required, each pair HH:MM)
    vix_size_multiplier: dict (optional)

Errors raise `SchemaError` with a `.path` attribute pointing at the
offending key.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from framework.stops import STOP_RULES
from framework.targets import TARGET_RULES


class SchemaError(ValueError):
    """Validation failure with a path attribute."""

    def __init__(self, message: str, path: str = "") -> None:
        super().__init__(f"[{path}] {message}" if path else message)
        self.path = path
        self.message = message


_HHMM_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _require(cond: bool, msg: str, path: str) -> None:
    if not cond:
        raise SchemaError(msg, path)


def _require_keys(d: Any, keys: Iterable[str], path: str) -> None:
    _require(isinstance(d, dict), f"expected mapping, got {type(d).__name__}", path)
    for k in keys:
        if k not in d:
            raise SchemaError(f"missing required key '{k}'", path)


def _require_type(value: Any, expected: type | tuple[type, ...], path: str) -> None:
    if not isinstance(value, expected):
        names = (
            expected.__name__
            if isinstance(expected, type)
            else "/".join(t.__name__ for t in expected)
        )
        raise SchemaError(
            f"expected {names}, got {type(value).__name__}", path
        )


def _validate_arrival(block: Any, path: str) -> None:
    _require_keys(block, ("type",), path)
    _require(
        block["type"] == "proximity",
        f"arrival_detector.type must be 'proximity', got '{block['type']}'",
        f"{path}.type",
    )
    params = block.get("params") or {}
    _require_type(params, dict, f"{path}.params")
    pct = params.get("proximity_pct")
    dol = params.get("proximity_dollar")
    _require(
        pct is not None or dol is not None,
        "arrival_detector requires proximity_pct OR proximity_dollar",
        f"{path}.params",
    )
    if pct is not None:
        _require_type(pct, (int, float), f"{path}.params.proximity_pct")
        _require(pct >= 0, "proximity_pct must be >= 0", f"{path}.params.proximity_pct")
    if dol is not None:
        # May be float (single value) or dict (price-tier keyed)
        if isinstance(dol, dict):
            for k, v in dol.items():
                _require_type(v, (int, float), f"{path}.params.proximity_dollar.{k}")
        else:
            _require_type(dol, (int, float), f"{path}.params.proximity_dollar")
            _require(
                dol >= 0,
                "proximity_dollar must be >= 0",
                f"{path}.params.proximity_dollar",
            )


def _validate_trade_windows(value: Any, path: str) -> None:
    _require_type(value, list, path)
    _require(len(value) > 0, "trade_windows must be non-empty", path)
    for i, win in enumerate(value):
        p = f"{path}[{i}]"
        _require_type(win, (list, tuple), p)
        _require(len(win) == 2, "each trade window must be [start, end]", p)
        for j, t in enumerate(win):
            tp = f"{p}[{j}]"
            _require_type(t, str, tp)
            _require(
                bool(_HHMM_RE.match(t)),
                f"trade-window time '{t}' is not HH:MM",
                tp,
            )


def _validate_plugin_block(
    block: Any, path: str, known_types: Iterable[str] | None = None
) -> None:
    _require_keys(block, ("type",), path)
    _require_type(block["type"], str, f"{path}.type")
    if "params" in block:
        _require_type(block["params"], dict, f"{path}.params")
    if known_types is not None and block["type"] != "composite":
        known = set(known_types)
        if block["type"] not in known:
            raise SchemaError(
                f"unknown plugin '{block['type']}'. Known: {sorted(known)}",
                f"{path}.type",
            )


def validate_strategy_spec(spec: Any) -> None:
    """Validate a parsed YAML dict against the StrategySpec schema.

    Raises SchemaError on the first violation.
    """
    _require_type(spec, dict, "$")

    _require_keys(
        spec,
        (
            "name",
            "level_source",
            "arrival_detector",
            "confirmation_rule",
            "stop_rule",
            "target_rule",
            "risk_per_trade_pct",
            "max_concurrent_positions",
            "trade_windows",
        ),
        "$",
    )

    _require_type(spec["name"], str, "$.name")
    _require(len(spec["name"]) > 0, "name must be non-empty", "$.name")

    if "enabled" in spec:
        _require_type(spec["enabled"], bool, "$.enabled")

    _validate_plugin_block(spec["level_source"], "$.level_source")
    _validate_arrival(spec["arrival_detector"], "$.arrival_detector")
    _validate_plugin_block(spec["confirmation_rule"], "$.confirmation_rule")
    _validate_plugin_block(
        spec["stop_rule"], "$.stop_rule", known_types=STOP_RULES.keys()
    )
    _validate_plugin_block(
        spec["target_rule"], "$.target_rule", known_types=TARGET_RULES.keys()
    )

    _require_type(spec["risk_per_trade_pct"], (int, float), "$.risk_per_trade_pct")
    _require(
        spec["risk_per_trade_pct"] > 0,
        "risk_per_trade_pct must be > 0",
        "$.risk_per_trade_pct",
    )

    _require_type(spec["max_concurrent_positions"], int, "$.max_concurrent_positions")
    _require(
        spec["max_concurrent_positions"] > 0,
        "max_concurrent_positions must be > 0",
        "$.max_concurrent_positions",
    )

    _validate_trade_windows(spec["trade_windows"], "$.trade_windows")

    if "vix_size_multiplier" in spec:
        _require_type(spec["vix_size_multiplier"], dict, "$.vix_size_multiplier")
