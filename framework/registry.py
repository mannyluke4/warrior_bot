"""StrategySpec + StrategyRegistry — YAML-driven strategy composition.

A StrategySpec captures the full configuration of one strategy: which
level source, arrival detector, confirmation rule, stop rule, target
rule, and risk knobs to use. Strategies are defined as YAML files and
loaded via `StrategyRegistry.load_yaml()`.

Wave 1 ships:
- The dataclass schema.
- A YAML loader that validates structure and instantiates built-in
  stop/target/arrival plugins.
- Stubs for level_source / confirmation_rule that store the requested
  type + params for Wave 2 to wire up actual implementations.

This module imports yaml lazily so the rest of the framework doesn't
require PyYAML installed unless YAML loading is exercised.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Optional

from framework.arrival import ArrivalDetector
from framework.composite import build_composite_target
from framework.stops import STOP_RULES, StopRuleProtocol
from framework.targets import TARGET_RULES, TargetRuleProtocol
from framework.yaml_schema import SchemaError, validate_strategy_spec


# ---------------------------------------------------------------------------
# Placeholder objects for plugin types Wave 2 will implement.
# We capture the requested type/params so registry round-trips cleanly.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LevelSourceStub:
    """Wave-1 placeholder for level_source plugins.

    Stores the requested type + params. Wave 2 replaces this with
    concrete classes (OpeningRange, VWAP, PDH_PDL, RoundNumber, ...).
    """

    type: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfirmationStub:
    """Wave-1 placeholder for confirmation_rule plugins."""

    type: str
    params: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# StrategySpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategySpec:
    """The complete config for one strategy.

    Created via `StrategyRegistry.load_yaml()`. Once loaded, the spec is
    immutable. Wave-2 components consume this object to run the strategy.

    Wave-4 filter knobs (all optional, default to None / empty):
      - entry_time_window:  dict {start, end, tz} — second-precision entry
        window (e.g. PDH-Fade F1: 09:30:00 - 09:44:59 ET)
      - abandon_rule:       dict {enabled, minutes_after_entry,
        exit_if_not_profit, exit_cap_dollars, exit_method}
      - tier_filter:        dict {enabled, min_price, max_price?}
      - opening_bar_alignment: dict {required, allow_doji}
      - skip_mondays:       bool
      - symbol_blacklist:   tuple[str, ...]
      - require_vwap_alignment: bool
      - pre_entry_consolidation_max_pct: float | None
      - volume_min_multiple: float | None
    """

    name: str
    enabled: bool
    level_source: Any  # LevelSourceProtocol once wired in Wave 2; LevelSourceStub in Wave 1
    arrival_detector: ArrivalDetector
    confirmation_rule: Any  # ConfirmationProtocol once wired in Wave 2; ConfirmationStub in Wave 1
    stop_rule: StopRuleProtocol
    target_rule: TargetRuleProtocol
    risk_per_trade_pct: float
    max_concurrent_positions: int
    trade_windows: tuple[tuple[str, str], ...]
    vix_size_multiplier: dict[str, Any] = field(default_factory=dict)
    # Wave-4 optional filter knobs (see class docstring).
    entry_time_window: Optional[dict[str, Any]] = None
    abandon_rule: Optional[dict[str, Any]] = None
    tier_filter: Optional[dict[str, Any]] = None
    opening_bar_alignment: Optional[dict[str, Any]] = None
    skip_mondays: bool = False
    symbol_blacklist: tuple[str, ...] = ()
    require_vwap_alignment: bool = False
    pre_entry_consolidation_max_pct: Optional[float] = None
    volume_min_multiple: Optional[float] = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


# ---------------------------------------------------------------------------
# Plugin instantiation helpers
# ---------------------------------------------------------------------------


def _instantiate_arrival(block: dict[str, Any]) -> ArrivalDetector:
    params = block.get("params") or {}
    dol = params.get("proximity_dollar")
    # If proximity_dollar is a price-tier-keyed dict, we can't resolve it
    # here — the strategy needs to know the symbol's price first. For
    # Wave 1 we accept the dict and pass through the smallest threshold so
    # the detector is instantiable; Wave 2 will plumb in tier-aware
    # resolution at the strategy level.
    if isinstance(dol, dict):
        dol_value: Optional[float] = min((float(v) for v in dol.values()), default=None)
    elif dol is None:
        dol_value = None
    else:
        dol_value = float(dol)
    pct = params.get("proximity_pct")
    pct_value = float(pct) if pct is not None else None
    return ArrivalDetector(proximity_pct=pct_value, proximity_dollar=dol_value)


def _filter_kwargs(cls: type, params: dict[str, Any]) -> dict[str, Any]:
    fields = getattr(cls, "__dataclass_fields__", {})
    return {k: v for k, v in params.items() if k in fields}


def _instantiate_stop(block: dict[str, Any]) -> StopRuleProtocol:
    t = block["type"]
    params = block.get("params") or {}
    if t == "composite":
        # Wave 1 doesn't support composite stops; the schema validator
        # already accepts 'composite' — surface the limitation here.
        from framework.composite import build_composite_stop

        return build_composite_stop(params)
    if t not in STOP_RULES:
        raise SchemaError(
            f"unknown stop rule '{t}'. Known: {sorted(STOP_RULES.keys())}",
            "$.stop_rule.type",
        )
    cls = STOP_RULES[t]
    kwargs = _filter_kwargs(cls, params)
    # Required-arg classes (OppositeRange, InLVN) may need values that
    # aren't in YAML; surface a clear error in that case.
    try:
        return cls(**kwargs)
    except TypeError as e:
        raise SchemaError(
            f"failed to instantiate stop rule '{t}': {e}", "$.stop_rule.params"
        ) from e


def _instantiate_target(block: dict[str, Any]) -> TargetRuleProtocol:
    t = block["type"]
    params = block.get("params") or {}
    if t == "composite":
        return build_composite_target(params)
    if t not in TARGET_RULES:
        raise SchemaError(
            f"unknown target rule '{t}'. Known: {sorted(TARGET_RULES.keys())}",
            "$.target_rule.type",
        )
    cls = TARGET_RULES[t]
    # Map yaml-friendly aliases to dataclass field names.
    aliased = dict(params)
    if "r_multiple" in aliased and "r" not in aliased:
        aliased["r"] = aliased["r_multiple"]
    kwargs = _filter_kwargs(cls, aliased)
    try:
        return cls(**kwargs)
    except TypeError as e:
        raise SchemaError(
            f"failed to instantiate target rule '{t}': {e}",
            "$.target_rule.params",
        ) from e


# ---------------------------------------------------------------------------
# StrategyRegistry — singleton-style container with explicit instantiation.
# ---------------------------------------------------------------------------


class StrategyRegistry:
    """Container of loaded StrategySpecs, accessed by name.

    Not a hard singleton — multiple instances are allowed for tests, but
    the canonical one is exposed as `StrategyRegistry.default()` for app
    code that wants a single registry.
    """

    _default: ClassVar[Optional["StrategyRegistry"]] = None

    def __init__(self) -> None:
        self._strategies: dict[str, StrategySpec] = {}

    @classmethod
    def default(cls) -> "StrategyRegistry":
        if cls._default is None:
            cls._default = cls()
        return cls._default

    @classmethod
    def reset_default(cls) -> None:
        cls._default = None

    # ----- public API -----

    def register(self, spec: StrategySpec) -> None:
        self._strategies[spec.name] = spec

    def get(self, name: str) -> StrategySpec:
        if name not in self._strategies:
            raise KeyError(
                f"strategy '{name}' not registered. "
                f"Available: {sorted(self._strategies.keys())}"
            )
        return self._strategies[name]

    def list_enabled(self) -> list[StrategySpec]:
        return [s for s in self._strategies.values() if s.enabled]

    def list_all(self) -> list[StrategySpec]:
        return list(self._strategies.values())

    def __contains__(self, name: str) -> bool:
        return name in self._strategies

    def __len__(self) -> int:
        return len(self._strategies)

    # ----- YAML loader -----

    def load_yaml(self, path: str | Path) -> StrategySpec:
        """Parse + validate + instantiate a strategy YAML, register it, return it."""
        try:
            import yaml  # local import: PyYAML only needed when loading
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "PyYAML required to load strategy specs. Install via "
                "`pip install pyyaml`."
            ) from e

        p = Path(path)
        with p.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        return self.load_dict(raw)

    def load_dict(self, raw: dict[str, Any]) -> StrategySpec:
        """Same as load_yaml but takes a pre-parsed dict (handy for tests)."""
        validate_strategy_spec(raw)

        level_source_block = raw["level_source"]
        level_source = LevelSourceStub(
            type=level_source_block["type"],
            params=dict(level_source_block.get("params") or {}),
        )

        arrival_detector = _instantiate_arrival(raw["arrival_detector"])

        conf_block = raw["confirmation_rule"]
        confirmation_rule = ConfirmationStub(
            type=conf_block["type"],
            params=dict(conf_block.get("params") or {}),
        )

        stop_rule = _instantiate_stop(raw["stop_rule"])
        target_rule = _instantiate_target(raw["target_rule"])

        # Wave-4 optional filter knobs (Phase B1).
        etw = raw.get("entry_time_window")
        ar = raw.get("abandon_rule")
        tf = raw.get("tier_filter")
        oba = raw.get("opening_bar_alignment")
        bl = raw.get("symbol_blacklist") or ()
        cons_max = raw.get("pre_entry_consolidation_max_pct")
        vol_min = raw.get("volume_min_multiple")

        spec = StrategySpec(
            name=raw["name"],
            enabled=bool(raw.get("enabled", True)),
            level_source=level_source,
            arrival_detector=arrival_detector,
            confirmation_rule=confirmation_rule,
            stop_rule=stop_rule,
            target_rule=target_rule,
            risk_per_trade_pct=float(raw["risk_per_trade_pct"]),
            max_concurrent_positions=int(raw["max_concurrent_positions"]),
            trade_windows=tuple(tuple(w) for w in raw["trade_windows"]),
            vix_size_multiplier=dict(raw.get("vix_size_multiplier") or {}),
            entry_time_window=dict(etw) if isinstance(etw, dict) else None,
            abandon_rule=dict(ar) if isinstance(ar, dict) else None,
            tier_filter=dict(tf) if isinstance(tf, dict) else None,
            opening_bar_alignment=dict(oba) if isinstance(oba, dict) else None,
            skip_mondays=bool(raw.get("skip_mondays", False)),
            symbol_blacklist=tuple(str(s) for s in bl),
            require_vwap_alignment=bool(raw.get("require_vwap_alignment", False)),
            pre_entry_consolidation_max_pct=float(cons_max)
            if cons_max is not None
            else None,
            volume_min_multiple=float(vol_min) if vol_min is not None else None,
            raw=raw,
        )
        self.register(spec)
        return spec
