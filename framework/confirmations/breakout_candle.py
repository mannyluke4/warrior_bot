"""BreakoutCandle — close beyond level + volume confirmation.

Used by ORB and (post-6/15) squeeze migration. Detection:

- Long direction:  bar.close > level.price * (1 + min_breakout_pct)
- Short direction: bar.close < level.price * (1 - min_breakout_pct)

The direction is inferred from the level kind unless explicitly forced:
- PDH, ORH, HVN-resistance, ROUND, PM_HIGH, BOX_TOP -> long breakout
- PDL, ORL, BOX_BOTTOM, PM_LOW                       -> short breakout
- All others default to long (configurable via `direction` arg).

Volume confirmation:
- entry bar volume >= min_vol_mult * baseline (20-bar average prior)

Usage:

    >>> bc = BreakoutCandle(min_vol_mult=2.0, min_breakout_pct=0.0002)
    >>> bars = [...20 prior bars..., entry_bar]
    >>> result = bc.check_confirmation(level=orh_level, bars=bars)
    >>> result.confirmed
    True

Edge cases:
- Empty bars / no level         -> confirmed=False
- range_size <= 0               -> still evaluable (close-vs-level check works)
- NaN OHLCV                     -> confirmed=False
- Insufficient prior bars for baseline:
                                    fall back to whatever's available; vol-check
                                    can still pass on small windows. If no prior
                                    bars at all, vol-check fails open with reason.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Optional

from framework.confirmations.base import ConfirmationResult
from framework.level_sources.base import Bar, Level


Direction = Literal["long", "short", "auto"]


_LONG_KINDS = frozenset(
    {"PDH", "ORH", "ROUND", "PM_HIGH", "BOX_TOP", "VAH", "POC", "ANCHORED_VWAP", "VWAP", "SWING_HIGH"}
)
_SHORT_KINDS = frozenset({"PDL", "ORL", "PM_LOW", "BOX_BOTTOM", "VAL", "SWING_LOW"})


def _infer_direction(level: Level) -> Literal["long", "short"]:
    if level.kind in _SHORT_KINDS:
        return "short"
    return "long"


def _finite(x: float) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


@dataclass
class BreakoutCandle:
    """Breakout confirmation: close beyond level + volume mult.

    Args:
        min_vol_mult: Minimum entry-bar-volume / 20-bar-avg ratio.
            Default 2.0.
        min_breakout_pct: Minimum fractional breakout (close vs level).
            Default 0.0002 (2 bps).
        require_close_beyond: When True, bar.close must satisfy the
            breakout inequality. When False, bar.high (long) or bar.low
            (short) is sufficient (less common — wick breakouts).
        direction: "long" / "short" / "auto" (infer from level.kind).
    """

    min_vol_mult: float = 2.0
    min_breakout_pct: float = 0.0002
    require_close_beyond: bool = True
    direction: Direction = "auto"

    def _volume_baseline(self, bars: list[Bar]) -> tuple[float, int]:
        """Return (avg_volume, n_bars_used) over prior bars (excluding entry).

        Uses up to 20 prior bars; if fewer are available, uses what exists.
        Skips NaN/inf volumes.
        """
        window = bars[-21:-1] if len(bars) > 1 else []
        vols = [b.volume for b in window if _finite(b.volume)]
        if not vols:
            return 0.0, 0
        return sum(vols) / len(vols), len(vols)

    def check_confirmation(
        self,
        level: Optional[Level],
        bars: list[Bar],
        l2_state: Optional[dict[str, Any]] = None,
    ) -> ConfirmationResult:
        if level is None:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="breakout_candle",
                strength=0.0,
                reason="no level",
            )
        if not bars:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="breakout_candle",
                strength=0.0,
                reason="no bars",
            )

        entry = bars[-1]
        if not all(_finite(x) for x in (entry.open, entry.high, entry.low, entry.close, entry.volume)):
            return ConfirmationResult(
                confirmed=False,
                pattern_name="breakout_candle",
                strength=0.0,
                reason="nan ohlcv",
            )

        if not _finite(level.price) or level.price <= 0:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="breakout_candle",
                strength=0.0,
                reason="invalid level price",
            )

        direction = (
            self.direction if self.direction in ("long", "short") else _infer_direction(level)
        )

        # 1. Price breakout test
        if direction == "long":
            threshold = level.price * (1.0 + self.min_breakout_pct)
            test_price = entry.close if self.require_close_beyond else entry.high
            price_ok = test_price > threshold
            price_reason = (
                f"{('close' if self.require_close_beyond else 'high')}={test_price:.4f} "
                f"vs threshold={threshold:.4f} (level={level.price:.4f} +{self.min_breakout_pct*100:.3f}%)"
            )
        else:
            threshold = level.price * (1.0 - self.min_breakout_pct)
            test_price = entry.close if self.require_close_beyond else entry.low
            price_ok = test_price < threshold
            price_reason = (
                f"{('close' if self.require_close_beyond else 'low')}={test_price:.4f} "
                f"vs threshold={threshold:.4f} (level={level.price:.4f} -{self.min_breakout_pct*100:.3f}%)"
            )

        if not price_ok:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="breakout_candle",
                strength=0.0,
                reason=f"no breakout: {price_reason}",
                metadata={"direction": direction, "level_price": level.price},
            )

        # 2. Volume baseline test
        baseline, n = self._volume_baseline(bars)
        if baseline <= 0:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="breakout_candle",
                strength=0.0,
                reason=f"no volume baseline ({n} bars usable)",
                metadata={"direction": direction},
            )
        vol_mult = entry.volume / baseline
        vol_ok = vol_mult >= self.min_vol_mult

        if not vol_ok:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="breakout_candle",
                strength=0.0,
                reason=(
                    f"vol_mult={vol_mult:.2f}x < min={self.min_vol_mult:.2f}x "
                    f"(baseline={baseline:.0f} over {n} bars)"
                ),
                metadata={
                    "direction": direction,
                    "vol_mult": vol_mult,
                    "baseline": baseline,
                },
            )

        # Strength: blend breakout magnitude and volume mult
        if direction == "long":
            breakout_pct = (entry.close - level.price) / level.price
        else:
            breakout_pct = (level.price - entry.close) / level.price
        # Cap breakout component at 1% (anything beyond is full credit)
        breakout_component = max(0.0, min(1.0, breakout_pct / 0.01))
        # Vol component: 2x -> 0.5, 4x -> 0.75, plateaus
        vol_component = max(0.0, min(1.0, (vol_mult - 1.0) / 4.0))
        strength = round(0.5 * breakout_component + 0.5 * vol_component, 4)

        return ConfirmationResult(
            confirmed=True,
            pattern_name="breakout_candle",
            strength=strength,
            reason=(
                f"{direction} breakout: {price_reason}, "
                f"vol_mult={vol_mult:.2f}x baseline={baseline:.0f} ({n} bars)"
            ),
            metadata={
                "direction": direction,
                "level_price": level.price,
                "level_kind": level.kind,
                "breakout_pct": breakout_pct,
                "vol_mult": vol_mult,
                "baseline": baseline,
                "baseline_bars": n,
            },
        )
