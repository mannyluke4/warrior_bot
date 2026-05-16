"""Stop rules for the healthy-fluctuation framework.

A stop rule is a plugin that, given an entry price, the level being traded,
and recent bar history, returns the stop price. Stops are bot-internal
price comparisons per Manny's hard rule ("no broker stops"); they fire as
SELL LIMIT exits when the comparison trips. Nothing in this module
submits orders.

Built-ins:
- JustPastLevel: stop a fixed dollar pad past the level
- OppositeRange: stop at the opposite side of an opening range
- InLVN: stop inside a designated Low-Volume Node
- BarLow: stop below the lowest low of the last N bars

All take direction='long' or 'short' so the math flips correctly.

Wave-1 contract: pure computation, no order placement. Stop rules
that need extra context (an LVN list, an opening range) accept it as
constructor args.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from framework.level_sources.base import Bar, BarHistory, Level

Direction = Literal["long", "short"]


@runtime_checkable
class StopRuleProtocol(Protocol):
    """Plugin contract: (entry_price, level, history, direction) -> stop_price."""

    def compute_stop(
        self,
        entry_price: float,
        level: Level,
        history: BarHistory,
        direction: Direction = "long",
    ) -> float: ...


# ---------------------------------------------------------------------------
# Built-ins
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JustPastLevel:
    """Stop just past the level on the wrong side.

    For a long: stop = level.price - pad_dollar.
    For a short: stop = level.price + pad_dollar.

    `pad_dollar` may be 0 (stop exactly at level) but typically a few cents
    to clear noise wicks.
    """

    pad_dollar: float = 0.05

    def compute_stop(
        self,
        entry_price: float,
        level: Level,
        history: BarHistory,
        direction: Direction = "long",
    ) -> float:
        if direction == "long":
            return level.price - self.pad_dollar
        return level.price + self.pad_dollar


@dataclass(frozen=True)
class OppositeRange:
    """Stop at the opposite side of an opening range.

    The OR levels are looked up on the level set by kind: long trades
    breaking ORH stop at ORL; short trades breaking ORL stop at ORH.

    `opening_range_high` and `opening_range_low` are passed in at
    construction time (a strategy resolves these from its LevelSet).
    """

    opening_range_high: float
    opening_range_low: float

    def compute_stop(
        self,
        entry_price: float,
        level: Level,
        history: BarHistory,
        direction: Direction = "long",
    ) -> float:
        return self.opening_range_low if direction == "long" else self.opening_range_high


@dataclass(frozen=True)
class InLVN:
    """Stop inside the nearest Low-Volume Node on the wrong side of entry.

    Per VP methodology, LVNs are "thin" zones where price transits
    quickly — putting the stop inside an LVN means a stop hit reflects
    real direction change, not noise.

    `lvn_levels` is a tuple of LVN prices (typically from the level set).
    """

    lvn_levels: tuple[float, ...]
    pad_dollar: float = 0.02

    def compute_stop(
        self,
        entry_price: float,
        level: Level,
        history: BarHistory,
        direction: Direction = "long",
    ) -> float:
        if not self.lvn_levels:
            # Fallback: just-past-level behavior with default pad
            return JustPastLevel(self.pad_dollar).compute_stop(
                entry_price, level, history, direction
            )
        if direction == "long":
            candidates = [p for p in self.lvn_levels if p < entry_price]
            if not candidates:
                return JustPastLevel(self.pad_dollar).compute_stop(
                    entry_price, level, history, direction
                )
            return max(candidates) - self.pad_dollar
        candidates = [p for p in self.lvn_levels if p > entry_price]
        if not candidates:
            return JustPastLevel(self.pad_dollar).compute_stop(
                entry_price, level, history, direction
            )
        return min(candidates) + self.pad_dollar


@dataclass(frozen=True)
class BarLow:
    """Stop below the lowest low (long) or above the highest high (short)
    of the last `lookback` bars.

    A small `pad_dollar` keeps the stop just past the extreme so wicks
    don't trigger it.
    """

    lookback: int = 3
    pad_dollar: float = 0.02

    def compute_stop(
        self,
        entry_price: float,
        level: Level,
        history: BarHistory,
        direction: Direction = "long",
    ) -> float:
        if len(history) == 0:
            # No history; fall back to level
            return JustPastLevel(self.pad_dollar).compute_stop(
                entry_price, level, history, direction
            )
        n = min(self.lookback, len(history))
        recent = history.bars[-n:]
        if direction == "long":
            extreme = min(b.low for b in recent)
            return extreme - self.pad_dollar
        extreme = max(b.high for b in recent)
        return extreme + self.pad_dollar


# Registry of stop-rule names for YAML loading. New plugins register here.
STOP_RULES: dict[str, type] = {
    "just_past_level": JustPastLevel,
    "opposite_range": OppositeRange,
    "in_lvn": InLVN,
    "bar_low": BarLow,
}
