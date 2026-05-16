"""Target rules for the healthy-fluctuation framework.

A target rule, given an entry price, the level being traded, the LevelSet,
and recent bar history, returns one or more target prices. Targets exit at
LIMIT per the no-market-orders rule.

Built-ins:
- OppositeLevel: edge-to-edge — exit at the opposite side of the level structure
- RMultiple: exit at entry +/- N * stop_distance
- SessionClose: exit at session close (default 15:55 ET)
- EdgeToEdge: exit at the opposite extreme of the level set
- TrailingATR: trailing stop activated at activate_at_r, trailing by atr_mult * ATR
- CompositeTarget: primary + fallback + optional trailing (composition for YAML)

All rules return TargetSpec — a frozen dataclass capturing primary target
price, optional trailing config, and metadata for logging. Composite
rules can combine these.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol, runtime_checkable

from framework.level_sources.base import Bar, BarHistory, Level, LevelSet

Direction = Literal["long", "short"]


@dataclass(frozen=True)
class TargetSpec:
    """The result of a target-rule computation.

    `primary_price` is the immediate take-profit price (LIMIT exit).
    `session_close_exit` flags whether the strategy should also force
    exit at session close.
    `trailing` is an optional dict describing the trailing-stop policy
    once price reaches `activate_at_r`. Shape:
        {"activate_at_r": 1.5, "atr_mult": 1.5}
    `metadata` is plugin-specific (e.g. fallback chain, level used).
    """

    primary_price: float | None
    session_close_exit: bool = False
    trailing: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TargetRuleProtocol(Protocol):
    """Plugin contract: (entry, level, level_set, history, direction, stop_price) -> TargetSpec."""

    def compute_target(
        self,
        entry_price: float,
        level: Level,
        level_set: LevelSet,
        history: BarHistory,
        direction: Direction = "long",
        stop_price: Optional[float] = None,
    ) -> TargetSpec: ...


# ---------------------------------------------------------------------------
# Built-ins
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OppositeLevel:
    """Exit at the next level on the opposite side of entry.

    Given a long entry, picks the lowest level above entry as target.
    For a short, picks the highest level below entry.
    """

    def compute_target(
        self,
        entry_price: float,
        level: Level,
        level_set: LevelSet,
        history: BarHistory,
        direction: Direction = "long",
        stop_price: Optional[float] = None,
    ) -> TargetSpec:
        if direction == "long":
            candidates = [lvl.price for lvl in level_set.levels if lvl.price > entry_price]
            if not candidates:
                return TargetSpec(primary_price=None, metadata={"reason": "no_higher_level"})
            return TargetSpec(primary_price=min(candidates))
        candidates = [lvl.price for lvl in level_set.levels if lvl.price < entry_price]
        if not candidates:
            return TargetSpec(primary_price=None, metadata={"reason": "no_lower_level"})
        return TargetSpec(primary_price=max(candidates))


@dataclass(frozen=True)
class RMultiple:
    """Exit at entry +/- r * (entry - stop).

    `r` is the multiple of risk (1R = full stop distance).
    """

    r: float = 2.0

    def compute_target(
        self,
        entry_price: float,
        level: Level,
        level_set: LevelSet,
        history: BarHistory,
        direction: Direction = "long",
        stop_price: Optional[float] = None,
    ) -> TargetSpec:
        if stop_price is None:
            return TargetSpec(primary_price=None, metadata={"reason": "no_stop"})
        risk = abs(entry_price - stop_price)
        if direction == "long":
            return TargetSpec(primary_price=entry_price + self.r * risk)
        return TargetSpec(primary_price=entry_price - self.r * risk)


@dataclass(frozen=True)
class SessionClose:
    """Exit at session close (force-exit timestamp).

    The actual close time is enforced by the trade manager; this rule
    simply signals 'no price target, ride to close.' Sets session_close_exit=True.
    """

    def compute_target(
        self,
        entry_price: float,
        level: Level,
        level_set: LevelSet,
        history: BarHistory,
        direction: Direction = "long",
        stop_price: Optional[float] = None,
    ) -> TargetSpec:
        return TargetSpec(primary_price=None, session_close_exit=True)


@dataclass(frozen=True)
class EdgeToEdge:
    """Exit at the opposite extreme of the level set.

    For a long: the maximum-priced level in the set.
    For a short: the minimum-priced level in the set.

    Useful for VP edge-to-edge plays (VAL -> VAH or POC -> opposite tail).
    """

    def compute_target(
        self,
        entry_price: float,
        level: Level,
        level_set: LevelSet,
        history: BarHistory,
        direction: Direction = "long",
        stop_price: Optional[float] = None,
    ) -> TargetSpec:
        if not level_set.levels:
            return TargetSpec(primary_price=None, metadata={"reason": "empty_level_set"})
        if direction == "long":
            return TargetSpec(primary_price=max(lvl.price for lvl in level_set.levels))
        return TargetSpec(primary_price=min(lvl.price for lvl in level_set.levels))


@dataclass(frozen=True)
class TrailingATR:
    """Trailing-stop target.

    There is no fixed take-profit price. Once price reaches
    `activate_at_r` R-multiples, a trailing stop activates at
    `atr_mult * ATR` away from price. Closing logic lives in the trade
    manager; this plugin just emits the policy.
    """

    atr_mult: float = 1.5
    activate_at_r: float = 1.5

    def compute_target(
        self,
        entry_price: float,
        level: Level,
        level_set: LevelSet,
        history: BarHistory,
        direction: Direction = "long",
        stop_price: Optional[float] = None,
    ) -> TargetSpec:
        return TargetSpec(
            primary_price=None,
            trailing={
                "activate_at_r": self.activate_at_r,
                "atr_mult": self.atr_mult,
            },
        )


@dataclass(frozen=True)
class CompositeTarget:
    """Compose a primary target rule with a fallback and optional trailing.

    Behavior:
    1. Compute `primary`. If it yields a non-None primary_price, use it.
    2. Otherwise compute `fallback`. Use that primary_price.
    3. If `trailing` is provided, merge its trailing policy into the result.

    This is what YAML specs like:
        target_rule:
          type: composite
          params:
            primary: opposite_level
            fallback: r_multiple
            r_multiple: 2.0
            trailing: trailing_atr
            atr_mult: 1.5
            activate_at_r: 1.5
    resolve to.
    """

    primary: TargetRuleProtocol
    fallback: TargetRuleProtocol | None = None
    trailing: TargetRuleProtocol | None = None

    def compute_target(
        self,
        entry_price: float,
        level: Level,
        level_set: LevelSet,
        history: BarHistory,
        direction: Direction = "long",
        stop_price: Optional[float] = None,
    ) -> TargetSpec:
        result = self.primary.compute_target(
            entry_price, level, level_set, history, direction, stop_price
        )
        if result.primary_price is None and self.fallback is not None:
            result = self.fallback.compute_target(
                entry_price, level, level_set, history, direction, stop_price
            )
        trailing_policy = result.trailing
        if self.trailing is not None:
            t = self.trailing.compute_target(
                entry_price, level, level_set, history, direction, stop_price
            )
            if t.trailing:
                trailing_policy = t.trailing
        return TargetSpec(
            primary_price=result.primary_price,
            session_close_exit=result.session_close_exit,
            trailing=trailing_policy,
            metadata={**result.metadata, "composite": True},
        )


# Registry of target-rule names for YAML loading. New plugins register here.
TARGET_RULES: dict[str, type] = {
    "opposite_level": OppositeLevel,
    "r_multiple": RMultiple,
    "session_close": SessionClose,
    "edge_to_edge": EdgeToEdge,
    "trailing_atr": TrailingATR,
    "composite": CompositeTarget,
}
