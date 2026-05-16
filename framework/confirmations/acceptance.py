"""Acceptance — N consecutive bars closing inside a zone (80% rule).

Phase 2 strategy: Volume Profile 80% Rule. After price re-enters the prior
session's Value Area from outside, if the last N bars all close inside the
[VAL, VAH] zone, the strategy accepts the re-entry and trades toward the
opposite VA edge.

Configuration accepts zone bounds either as fixed values or as callables
that derive bounds from the level/bars (useful when bounds shift with
developing profile or with anchored values).

Usage with fixed bounds:

    >>> a = Acceptance(zone_low=10.50, zone_high=11.00, min_bars=2)
    >>> bars = [...history..., bar_close_10_60, bar_close_10_85]
    >>> result = a.check_confirmation(level=None, bars=bars)
    >>> result.confirmed
    True

Usage with callable bounds (e.g. derived from level metadata):

    >>> a = Acceptance(
    ...     zone_low=lambda level, bars: level.metadata["val"],
    ...     zone_high=lambda level, bars: level.metadata["vah"],
    ...     min_bars=2,
    ... )

Edge cases:
- Fewer than min_bars in history -> confirmed=False, reason includes deficit
- NaN closes                     -> confirmed=False, reason="nan close"
- zone_low >= zone_high           -> confirmed=False, reason="invalid zone"
- Empty bars                     -> confirmed=False
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from framework.confirmations.base import ConfirmationResult
from framework.level_sources.base import Bar, Level


ZoneBound = Union[float, Callable[[Optional[Level], list[Bar]], float]]


def _resolve_bound(
    bound: ZoneBound, level: Optional[Level], bars: list[Bar]
) -> float:
    if callable(bound):
        return float(bound(level, bars))
    return float(bound)


@dataclass
class Acceptance:
    """Zone-acceptance confirmation plugin.

    Args:
        zone_low: Lower bound of the acceptance zone. Either a float or
            a callable (level, bars) -> float.
        zone_high: Upper bound, same shape.
        min_bars: Minimum consecutive bars whose close must be in zone.
            Default 2.
    """

    zone_low: ZoneBound
    zone_high: ZoneBound
    min_bars: int = 2

    def check_confirmation(
        self,
        level: Optional[Level],
        bars: list[Bar],
        l2_state: Optional[dict[str, Any]] = None,
    ) -> ConfirmationResult:
        if self.min_bars < 1:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="acceptance",
                strength=0.0,
                reason=f"min_bars must be >= 1 (got {self.min_bars})",
            )
        if not bars:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="acceptance",
                strength=0.0,
                reason="no bars",
            )
        if len(bars) < self.min_bars:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="acceptance",
                strength=0.0,
                reason=f"need {self.min_bars} bars, have {len(bars)}",
            )

        try:
            low = _resolve_bound(self.zone_low, level, bars)
            high = _resolve_bound(self.zone_high, level, bars)
        except Exception as e:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="acceptance",
                strength=0.0,
                reason=f"zone resolver failed: {e}",
            )

        if not (math.isfinite(low) and math.isfinite(high)):
            return ConfirmationResult(
                confirmed=False,
                pattern_name="acceptance",
                strength=0.0,
                reason=f"invalid zone bounds: low={low}, high={high}",
            )
        if low >= high:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="acceptance",
                strength=0.0,
                reason=f"invalid zone: low={low} >= high={high}",
            )

        recent = bars[-self.min_bars:]
        closes_in_zone = []
        for b in recent:
            if not math.isfinite(b.close):
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="acceptance",
                    strength=0.0,
                    reason="nan close",
                )
            closes_in_zone.append(low <= b.close <= high)

        all_in = all(closes_in_zone)
        if not all_in:
            n_in = sum(closes_in_zone)
            return ConfirmationResult(
                confirmed=False,
                pattern_name="acceptance",
                strength=n_in / self.min_bars,
                reason=(
                    f"only {n_in}/{self.min_bars} bars in zone [{low:.4f}, {high:.4f}]"
                ),
                metadata={
                    "zone_low": low,
                    "zone_high": high,
                    "bars_in_zone": n_in,
                    "bars_required": self.min_bars,
                },
            )

        # Strength: tighter clustering toward zone midpoint = stronger.
        # Compute mean normalized distance from midpoint (0 = at mid, 1 = at edge).
        mid = (low + high) / 2.0
        half_width = (high - low) / 2.0
        if half_width <= 0:
            tightness = 1.0
        else:
            distances = [abs(b.close - mid) / half_width for b in recent]
            avg_dist = sum(distances) / len(distances)
            tightness = max(0.0, min(1.0, 1.0 - avg_dist))
        # Plus a bonus for having more than min_bars in zone (look further back)
        bonus_window = bars[-(self.min_bars + 3):] if len(bars) >= self.min_bars + 3 else bars
        extra_in = sum(1 for b in bonus_window if math.isfinite(b.close) and low <= b.close <= high)
        bonus = min(1.0, extra_in / max(1, len(bonus_window)))
        strength = round(0.6 * tightness + 0.4 * bonus, 4)

        return ConfirmationResult(
            confirmed=True,
            pattern_name="acceptance",
            strength=strength,
            reason=(
                f"{self.min_bars} consecutive closes in zone [{low:.4f}, {high:.4f}]"
            ),
            metadata={
                "zone_low": low,
                "zone_high": high,
                "bars_in_zone": self.min_bars,
                "tightness": tightness,
            },
        )
