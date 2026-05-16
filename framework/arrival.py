"""Arrival detection — has price arrived at a level?

The ArrivalDetector watches a symbol's current price against its LevelSet
and emits the first level inside the configured proximity window, or None.

Proximity can be specified two ways (at least one required):
- proximity_pct: fractional, e.g. 0.001 = 0.1% of current price
- proximity_dollar: absolute dollars (e.g. 0.10 = ten cents)

Both can be specified; the detector treats them as alternatives — a level
is "arrived at" if it's within EITHER threshold. This matches the YAML
schema where strategies may use price-tier-keyed dictionaries; resolving
those into a single float is done upstream of this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from framework.level_sources.base import Level, LevelSet


@dataclass(frozen=True)
class ArrivalDetector:
    """Proximity-based level arrival detection.

    At least one of `proximity_pct` and `proximity_dollar` must be set.
    Raises ValueError at construction if both are None.

    Returns the first (in level-set order) level within the proximity
    window, or None if the price isn't at any level.
    """

    proximity_pct: Optional[float] = None
    proximity_dollar: Optional[float] = None

    def __post_init__(self) -> None:
        if self.proximity_pct is None and self.proximity_dollar is None:
            raise ValueError(
                "ArrivalDetector requires at least one of "
                "proximity_pct or proximity_dollar"
            )
        if self.proximity_pct is not None and self.proximity_pct < 0:
            raise ValueError("proximity_pct must be >= 0")
        if self.proximity_dollar is not None and self.proximity_dollar < 0:
            raise ValueError("proximity_dollar must be >= 0")

    def _threshold(self, current_price: float) -> float:
        """The effective proximity threshold at `current_price` in dollars.

        Uses the LARGER of the pct- and dollar-derived thresholds (so a
        strategy with both can use pct for high-priced stocks and dollar
        as a minimum floor).
        """
        candidates: list[float] = []
        if self.proximity_pct is not None:
            candidates.append(abs(current_price) * self.proximity_pct)
        if self.proximity_dollar is not None:
            candidates.append(self.proximity_dollar)
        return max(candidates) if candidates else 0.0

    def check_arrival(
        self,
        symbol: str,
        current_price: float,
        level_set: LevelSet,
    ) -> Optional[Level]:
        """Return the first level within proximity, or None.

        Symbol param kept for parity with multi-symbol orchestrators that
        may share a single detector across symbols.
        """
        if level_set.symbol and symbol and level_set.symbol != symbol:
            # Caller passed mismatched LevelSet; play defensively.
            return None
        threshold = self._threshold(current_price)
        for lvl in level_set.levels:
            if abs(current_price - lvl.price) <= threshold:
                return lvl
        return None
