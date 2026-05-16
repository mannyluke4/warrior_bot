"""Composite plugin helpers used by the YAML loader.

Currently exposes `build_composite_target` and `build_composite_stop` —
helpers the registry calls when it encounters a `type: composite` block
inside a target_rule or stop_rule spec. Centralizing here keeps the
registry code clean.

A composite target spec looks like:

    target_rule:
      type: composite
      params:
        primary: opposite_level
        fallback: r_multiple
        r_multiple: 2.0
        trailing: trailing_atr
        atr_mult: 1.5
        activate_at_r: 1.5

The helpers below pull the named plugin classes from the appropriate
registry, instantiate them with the right kwargs, then wrap them in a
CompositeTarget (or CompositeStop, if/when that exists).
"""
from __future__ import annotations

from typing import Any

from framework.stops import STOP_RULES, StopRuleProtocol
from framework.targets import (
    TARGET_RULES,
    CompositeTarget,
    RMultiple,
    TargetRuleProtocol,
    TrailingATR,
)


def _instantiate_named(
    name: str,
    params: dict[str, Any],
    registry: dict[str, type],
    component_type: str,
) -> Any:
    """Look up `name` in `registry` and instantiate with kwargs from `params`."""
    if name not in registry:
        raise ValueError(
            f"Unknown {component_type} plugin '{name}'. "
            f"Available: {sorted(registry.keys())}"
        )
    cls = registry[name]
    # Filter kwargs to only those accepted by the dataclass fields.
    valid_fields = getattr(cls, "__dataclass_fields__", {})
    if not valid_fields:
        return cls()
    kwargs = {k: v for k, v in params.items() if k in valid_fields}
    return cls(**kwargs)


def build_composite_target(params: dict[str, Any]) -> TargetRuleProtocol:
    """Build a CompositeTarget from a YAML params dict.

    Resolves `primary`, `fallback`, and `trailing` by name, plus inline
    knobs (r_multiple, atr_mult, activate_at_r) that the YAML spec exposes.
    """
    primary_name = params.get("primary")
    if not primary_name:
        raise ValueError("composite target requires 'primary'")

    # Flatten knobs the composite spec exposes inline so primary/fallback/
    # trailing can pick them up.
    flat: dict[str, Any] = {}
    if "r_multiple" in params:
        flat["r"] = params["r_multiple"]
    if "atr_mult" in params:
        flat["atr_mult"] = params["atr_mult"]
    if "activate_at_r" in params:
        flat["activate_at_r"] = params["activate_at_r"]
    if "trailing_atr_mult" in params:
        flat["atr_mult"] = params["trailing_atr_mult"]
    if "activate_trailing_at_r" in params:
        flat["activate_at_r"] = params["activate_trailing_at_r"]

    primary = _instantiate_named(primary_name, flat, TARGET_RULES, "target")

    fallback: TargetRuleProtocol | None = None
    if params.get("fallback"):
        fallback = _instantiate_named(params["fallback"], flat, TARGET_RULES, "target")

    trailing: TargetRuleProtocol | None = None
    trailing_name = params.get("trailing")
    if trailing_name:
        trailing = _instantiate_named(trailing_name, flat, TARGET_RULES, "target")
    elif "activate_at_r" in flat or "activate_trailing_at_r" in params:
        # YAML can imply trailing via `activate_trailing_at_r` without naming it.
        trailing = TrailingATR(
            atr_mult=flat.get("atr_mult", 1.5),
            activate_at_r=flat.get("activate_at_r", 1.5),
        )

    return CompositeTarget(primary=primary, fallback=fallback, trailing=trailing)


def build_composite_stop(params: dict[str, Any]) -> StopRuleProtocol:
    """Build a composite stop (placeholder).

    Wave 1 ships a single composite for targets only. If/when Wave 2
    needs a composite stop (primary + tighten-as-price-moves), this is
    the wiring point. For now, raise so callers know it isn't built yet.
    """
    raise NotImplementedError(
        "composite stop rules are not implemented in Wave 1; "
        "use a single stop rule for now"
    )
