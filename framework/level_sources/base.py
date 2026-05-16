"""LevelSourceProtocol — the abstract interface every level source plugin implements.

A level source consumes a symbol's bar history (and optionally tick data) and
produces a LevelSet — the set of prices where the bot expects a reaction.

This module also defines the value objects shared across the framework:
- Bar: a single OHLCV bar
- BarHistory: a thin container over a list of Bars
- Level: one price point with a kind tag
- LevelSet: all of today's levels for a single symbol

Wave 1 ships only the protocol + value objects. Concrete plugins
(OpeningRange, VWAP, PDH_PDL, RoundNumber, VolumeProfile, AnchoredVWAP)
land in Wave 2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import (
    Any,
    Iterable,
    Iterator,
    Literal,
    Protocol,
    runtime_checkable,
)

# ---------------------------------------------------------------------------
# Bar / BarHistory — minimal value objects used across plugins.
# ---------------------------------------------------------------------------

LevelKind = Literal[
    "POC",
    "VAH",
    "VAL",
    "HVN",
    "LVN",
    "PDH",
    "PDL",
    "ORH",
    "ORL",
    "VWAP",
    "ROUND",
    "PM_HIGH",
    "PM_LOW",
    "ANCHORED_VWAP",
    "SWING_HIGH",
    "SWING_LOW",
    "BOX_TOP",
    "BOX_BOTTOM",
]

_VALID_LEVEL_KINDS: frozenset[str] = frozenset(LevelKind.__args__)  # type: ignore[attr-defined]


@dataclass(frozen=True)
class Bar:
    """A single OHLCV bar.

    Timestamps are ET-naive ISO strings or datetime objects; the framework
    does not enforce a specific tz convention at this layer. Plugins that
    care about tz wrap upstream.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = ""

    @property
    def range_size(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low


@dataclass
class BarHistory:
    """A thin container over a chronologically-ordered list of Bars.

    Mutable on purpose — `update_intraday(bar)` appends as new bars close.
    """

    symbol: str
    bars: list[Bar] = field(default_factory=list)

    def append(self, bar: Bar) -> None:
        self.bars.append(bar)

    def __iter__(self) -> Iterator[Bar]:
        return iter(self.bars)

    def __len__(self) -> int:
        return len(self.bars)

    def __getitem__(self, idx: int) -> Bar:
        return self.bars[idx]

    @property
    def last(self) -> Bar | None:
        return self.bars[-1] if self.bars else None

    def slice_between(self, start: datetime, end: datetime) -> list[Bar]:
        """Return bars with timestamp in [start, end) (half-open)."""
        return [b for b in self.bars if start <= b.timestamp < end]


# ---------------------------------------------------------------------------
# Level / LevelSet — what level sources produce.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Level:
    """A single price level the bot watches for a reaction.

    `price` is the level price.
    `kind` is one of the LevelKind tags (POC / VAH / VAL / etc.).
    `metadata` is plugin-specific (e.g. volume-at-price for POC, slope for VWAP).
    """

    price: float
    kind: str
    session_date: date
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in _VALID_LEVEL_KINDS:
            # Allow unknown kinds but warn-friendly: keep as-is for plugin
            # extensibility. Future tightening can raise here if needed.
            object.__setattr__(self, "kind", self.kind)


@dataclass(frozen=True)
class LevelSet:
    """All of one symbol's levels for one session.

    `levels` is the canonical list; helpers `all_levels`, `by_kind`, and
    `closest_to` provide common access patterns.
    """

    symbol: str
    session_date: date
    levels: tuple[Level, ...] = field(default_factory=tuple)

    @classmethod
    def from_iterable(
        cls, symbol: str, session_date: date, levels: Iterable[Level]
    ) -> "LevelSet":
        return cls(symbol=symbol, session_date=session_date, levels=tuple(levels))

    @property
    def all_levels(self) -> tuple[Level, ...]:
        return self.levels

    def by_kind(self, kind: str) -> tuple[Level, ...]:
        return tuple(lvl for lvl in self.levels if lvl.kind == kind)

    def closest_to(self, price: float) -> Level | None:
        if not self.levels:
            return None
        return min(self.levels, key=lambda lvl: abs(lvl.price - price))


# ---------------------------------------------------------------------------
# LevelSourceProtocol — what every level source plugin implements.
# ---------------------------------------------------------------------------


@runtime_checkable
class LevelSourceProtocol(Protocol):
    """Plugin contract for level sources.

    A level source has two phases:

    1. `compute_levels(symbol, history)` — called at session boot
       (or on demand). Reads bar history (and possibly other state)
       and returns the LevelSet the strategy will watch.

    2. `update_intraday(bar)` — called as new bars close during the session.
       Plugins that maintain developing levels (developing POC, intraday
       VWAP, rolling swing extremes) mutate internal state here. Plugins
       that emit only fixed levels (PDH/PDL, opening range after the
       opening minutes) may no-op.
    """

    def compute_levels(
        self, symbol: str, history: BarHistory
    ) -> LevelSet: ...

    def update_intraday(self, bar: Bar) -> None: ...
