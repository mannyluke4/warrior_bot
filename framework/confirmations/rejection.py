"""Rejection — failed-test pattern (PDH/PDL fade).

Used by PDH/PDL fade strategy: price probes the level (poke beyond) but
closes back on the original side, signaling that the breakout failed and
mean-reversion is likely.

Detection logic (resistance level / long-side fade rejected):
- One of the last `lookback_bars` bars (including the entry bar) had
  bar.high > level.price (touched/poked above the level)
- The current (entry) bar closed back BELOW level.price

For a support level (short-side fade rejected — long entry):
- One of the last `lookback_bars` bars had bar.low < level.price
- The current bar closed back ABOVE level.price

The direction (which side counts as "original") is inferred from level.kind:
- Resistance levels (PDH/ORH/VAH/HVN top/etc.) -> short-bias fade (rejection
  means we expect a move DOWN — short entry; pattern_name="rejection_down")
- Support levels (PDL/ORL/VAL/etc.) -> long-bias fade (pattern_name="rejection_up")

Usage:

    >>> r = Rejection(lookback_bars=2)
    >>> result = r.check_confirmation(level=pdh_level, bars=recent_bars)
    >>> result.confirmed, result.pattern_name
    (True, "rejection_down")

Edge cases:
- Empty bars / no level         -> confirmed=False
- lookback_bars > len(bars)     -> uses what's available, still evaluates
- NaN OHLC                      -> confirmed=False
- Touch never occurred          -> confirmed=False (no rejection if no test)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Optional

from framework.confirmations.base import ConfirmationResult
from framework.level_sources.base import Bar, Level


Side = Literal["resistance", "support", "auto"]


_RESISTANCE_KINDS = frozenset(
    {"PDH", "ORH", "VAH", "PM_HIGH", "BOX_TOP", "SWING_HIGH"}
)
_SUPPORT_KINDS = frozenset({"PDL", "ORL", "VAL", "PM_LOW", "BOX_BOTTOM", "SWING_LOW"})


def _infer_side(level: Level) -> Literal["resistance", "support"]:
    if level.kind in _SUPPORT_KINDS:
        return "support"
    # Default to resistance — covers PDH, ORH, VAH, ROUND, POC, etc.
    return "resistance"


def _finite(*xs: float) -> bool:
    for x in xs:
        try:
            if not math.isfinite(float(x)):
                return False
        except (TypeError, ValueError):
            return False
    return True


@dataclass
class Rejection:
    """Failed-test (fade) confirmation plugin.

    Args:
        lookback_bars: How many recent bars (including entry) to scan for
            the level-test event. Default 2.
        side: "resistance" / "support" / "auto" (infer from level.kind).
    """

    lookback_bars: int = 2
    side: Side = "auto"

    def check_confirmation(
        self,
        level: Optional[Level],
        bars: list[Bar],
        l2_state: Optional[dict[str, Any]] = None,
    ) -> ConfirmationResult:
        if level is None:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="rejection",
                strength=0.0,
                reason="no level",
            )
        if not bars:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="rejection",
                strength=0.0,
                reason="no bars",
            )
        if self.lookback_bars < 1:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="rejection",
                strength=0.0,
                reason=f"lookback_bars must be >= 1 (got {self.lookback_bars})",
            )
        if not _finite(level.price) or level.price <= 0:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="rejection",
                strength=0.0,
                reason="invalid level price",
            )

        entry = bars[-1]
        if not _finite(entry.open, entry.high, entry.low, entry.close):
            return ConfirmationResult(
                confirmed=False,
                pattern_name="rejection",
                strength=0.0,
                reason="nan ohlc",
            )

        side = (
            self.side if self.side in ("resistance", "support") else _infer_side(level)
        )
        window = bars[-self.lookback_bars:]
        lp = level.price

        if side == "resistance":
            # Must have poked above the level somewhere in the window
            test_bars = [b for b in window if _finite(b.high) and b.high > lp]
            if not test_bars:
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="rejection",
                    strength=0.0,
                    reason=f"no test of resistance {lp:.4f} in last {len(window)} bars",
                    metadata={"side": side, "level_price": lp},
                )
            # And the entry must have closed back below
            if entry.close >= lp:
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="rejection",
                    strength=0.0,
                    reason=(
                        f"tested resistance {lp:.4f} but entry close={entry.close:.4f} "
                        f"did not return below"
                    ),
                    metadata={"side": side, "level_price": lp},
                )

            # Strength: deeper poke + cleaner reclaim = stronger
            max_high = max(b.high for b in test_bars)
            poke = (max_high - lp) / lp  # fractional poke
            reclaim_dist = (lp - entry.close) / lp
            strength = round(min(1.0, poke * 50.0) * 0.5 + min(1.0, reclaim_dist * 50.0) * 0.5, 4)
            return ConfirmationResult(
                confirmed=True,
                pattern_name="rejection_down",
                strength=strength,
                reason=(
                    f"resistance rejection: max_high={max_high:.4f} > {lp:.4f}, "
                    f"close={entry.close:.4f} < {lp:.4f}"
                ),
                metadata={
                    "side": side,
                    "level_price": lp,
                    "max_test_high": max_high,
                    "poke_pct": poke,
                    "reclaim_pct": reclaim_dist,
                },
            )
        else:
            # support side
            test_bars = [b for b in window if _finite(b.low) and b.low < lp]
            if not test_bars:
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="rejection",
                    strength=0.0,
                    reason=f"no test of support {lp:.4f} in last {len(window)} bars",
                    metadata={"side": side, "level_price": lp},
                )
            if entry.close <= lp:
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="rejection",
                    strength=0.0,
                    reason=(
                        f"tested support {lp:.4f} but entry close={entry.close:.4f} "
                        f"did not return above"
                    ),
                    metadata={"side": side, "level_price": lp},
                )

            min_low = min(b.low for b in test_bars)
            poke = (lp - min_low) / lp
            reclaim_dist = (entry.close - lp) / lp
            strength = round(min(1.0, poke * 50.0) * 0.5 + min(1.0, reclaim_dist * 50.0) * 0.5, 4)
            return ConfirmationResult(
                confirmed=True,
                pattern_name="rejection_up",
                strength=strength,
                reason=(
                    f"support rejection: min_low={min_low:.4f} < {lp:.4f}, "
                    f"close={entry.close:.4f} > {lp:.4f}"
                ),
                metadata={
                    "side": side,
                    "level_price": lp,
                    "min_test_low": min_low,
                    "poke_pct": poke,
                    "reclaim_pct": reclaim_dist,
                },
            )
