"""SignalCandle — doji / hammer / shooting-star detection with volume confirmation.

Per DIRECTIVE_2026-05-17_HEALTHY_FLUCTUATION_FRAMEWORK.md (Signal Candle section)
and research_vp_market_profile.md §7.

EXACT detection criteria:
- Doji:          body / range < 0.10
- Hammer:        lower_wick > 2 * body
                 AND body_ratio < 0.30
                 AND body in upper 30% of range
- Shooting star: upper_wick > 2 * body
                 AND body_ratio < 0.30
                 AND body in lower 30% of range

Volume confirmation (when require_volume_increase=True):
- entry bar volume > prior bar volume

Pattern selection: a single entry bar may satisfy multiple criteria
(e.g. very small body could be both doji and hammer). The detector
returns the FIRST pattern (in config order) that matches, so callers
can prioritize via the `patterns` config.

Usage:

    >>> sc = SignalCandle(patterns=["doji", "hammer", "shooting_star"])
    >>> bars = [prior_bar, entry_bar]
    >>> result = sc.check_confirmation(level=some_level, bars=bars)
    >>> result.confirmed, result.pattern_name
    (True, "hammer")

Edge cases:
- Empty bars list           -> confirmed=False, reason="no bars"
- range_size <= 0           -> confirmed=False, reason="zero range"
- NaN OHLC                  -> confirmed=False, reason="nan ohlc"
- Missing prior bar with require_volume_increase=True
                            -> confirmed=False, reason="no prior bar for volume check"
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from framework.confirmations.base import ConfirmationResult
from framework.level_sources.base import Bar, Level


VALID_PATTERNS = ("doji", "hammer", "shooting_star")


def _all_finite(*xs: float) -> bool:
    for x in xs:
        try:
            if not math.isfinite(float(x)):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _is_doji(bar: Bar) -> tuple[bool, float]:
    """Return (matches, body_ratio)."""
    rng = bar.range_size
    if rng <= 0:
        return False, 0.0
    body_ratio = bar.body / rng
    return body_ratio < 0.10, body_ratio


def _is_hammer(bar: Bar) -> tuple[bool, dict[str, float]]:
    """Hammer: long lower wick, small body in upper 30% of range.

    Returns (matches, debug_dict).
    """
    rng = bar.range_size
    if rng <= 0:
        return False, {}
    body = bar.body
    body_ratio = body / rng
    lower_wick = bar.lower_wick

    # "Body in upper 30% of range" — body's lower edge must be >= low + 0.7*range
    body_low = min(bar.open, bar.close)
    body_low_position = (body_low - bar.low) / rng if rng > 0 else 0.0  # 0 = at low, 1 = at high

    matches = (
        lower_wick > 2.0 * body
        and body_ratio < 0.30
        and body_low_position >= 0.70
    )
    return matches, {
        "body_ratio": body_ratio,
        "lower_wick_to_body": (lower_wick / body) if body > 0 else float("inf"),
        "body_low_position": body_low_position,
    }


def _is_shooting_star(bar: Bar) -> tuple[bool, dict[str, float]]:
    """Shooting star: long upper wick, small body in lower 30% of range."""
    rng = bar.range_size
    if rng <= 0:
        return False, {}
    body = bar.body
    body_ratio = body / rng
    upper_wick = bar.upper_wick

    body_high = max(bar.open, bar.close)
    # body_high_position: 0 = at low, 1 = at high. Body in lower 30% means body_high <= low + 0.3*range
    body_high_position = (body_high - bar.low) / rng if rng > 0 else 0.0

    matches = (
        upper_wick > 2.0 * body
        and body_ratio < 0.30
        and body_high_position <= 0.30
    )
    return matches, {
        "body_ratio": body_ratio,
        "upper_wick_to_body": (upper_wick / body) if body > 0 else float("inf"),
        "body_high_position": body_high_position,
    }


@dataclass
class SignalCandle:
    """Signal-candle confirmation plugin.

    Args:
        patterns: Which sub-patterns to recognize, in priority order.
            Default ["doji", "hammer", "shooting_star"].
        require_volume_increase: When True, entry bar volume must exceed
            prior bar volume. Default True.
    """

    patterns: list[str] = field(
        default_factory=lambda: ["doji", "hammer", "shooting_star"]
    )
    require_volume_increase: bool = True

    def __post_init__(self) -> None:
        # Validate config — unknown pattern names are dropped with a clear error.
        bad = [p for p in self.patterns if p not in VALID_PATTERNS]
        if bad:
            raise ValueError(
                f"Unknown pattern(s): {bad}. Valid: {VALID_PATTERNS}"
            )

    def _strength(self, body_ratio: float, vol_ratio: float | None) -> float:
        """Normalize signal strength to [0, 1].

        Heuristic: lower body_ratio -> stronger pattern (cleaner candle),
        higher vol_ratio -> stronger confirmation. Each contributes 0.5.
        """
        # body component: 0 -> 1.0, 0.30 -> 0.0 (linear)
        body_component = max(0.0, min(1.0, 1.0 - (body_ratio / 0.30)))
        if vol_ratio is None:
            return round(body_component * 0.5, 4)
        # vol component: 1.0 -> 0.0, 3.0 -> 1.0 (saturates)
        vol_component = max(0.0, min(1.0, (vol_ratio - 1.0) / 2.0))
        return round(body_component * 0.5 + vol_component * 0.5, 4)

    def check_confirmation(
        self,
        level: Optional[Level],
        bars: list[Bar],
        l2_state: Optional[dict[str, Any]] = None,
    ) -> ConfirmationResult:
        if not bars:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="signal_candle",
                strength=0.0,
                reason="no bars",
            )

        entry = bars[-1]
        if not _all_finite(entry.open, entry.high, entry.low, entry.close):
            return ConfirmationResult(
                confirmed=False,
                pattern_name="signal_candle",
                strength=0.0,
                reason="nan ohlc",
            )

        if entry.range_size <= 0:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="signal_candle",
                strength=0.0,
                reason="zero range",
            )

        # Volume confirmation (if required)
        vol_ratio: float | None = None
        if self.require_volume_increase:
            if len(bars) < 2:
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="signal_candle",
                    strength=0.0,
                    reason="no prior bar for volume check",
                )
            prior = bars[-2]
            if not math.isfinite(prior.volume) or not math.isfinite(entry.volume):
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="signal_candle",
                    strength=0.0,
                    reason="nan volume",
                )
            if prior.volume <= 0:
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="signal_candle",
                    strength=0.0,
                    reason="zero prior volume",
                )
            if entry.volume <= prior.volume:
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="signal_candle",
                    strength=0.0,
                    reason=(
                        f"volume not increasing: entry={entry.volume:.0f} "
                        f"vs prior={prior.volume:.0f}"
                    ),
                )
            vol_ratio = entry.volume / prior.volume

        # Try each pattern in configured priority order
        for name in self.patterns:
            if name == "doji":
                matches, body_ratio = _is_doji(entry)
                if matches:
                    return ConfirmationResult(
                        confirmed=True,
                        pattern_name="doji",
                        strength=self._strength(body_ratio, vol_ratio),
                        reason=(
                            f"doji body_ratio={body_ratio:.3f} < 0.10"
                            + (f", vol_ratio={vol_ratio:.2f}x" if vol_ratio else "")
                        ),
                        metadata={"body_ratio": body_ratio, "vol_ratio": vol_ratio},
                    )
            elif name == "hammer":
                matches, dbg = _is_hammer(entry)
                if matches:
                    return ConfirmationResult(
                        confirmed=True,
                        pattern_name="hammer",
                        strength=self._strength(dbg["body_ratio"], vol_ratio),
                        reason=(
                            f"hammer lw/body={dbg['lower_wick_to_body']:.2f}, "
                            f"body_ratio={dbg['body_ratio']:.3f}, "
                            f"body_pos={dbg['body_low_position']:.2f}"
                        ),
                        metadata={**dbg, "vol_ratio": vol_ratio},
                    )
            elif name == "shooting_star":
                matches, dbg = _is_shooting_star(entry)
                if matches:
                    return ConfirmationResult(
                        confirmed=True,
                        pattern_name="shooting_star",
                        strength=self._strength(dbg["body_ratio"], vol_ratio),
                        reason=(
                            f"shooting_star uw/body={dbg['upper_wick_to_body']:.2f}, "
                            f"body_ratio={dbg['body_ratio']:.3f}, "
                            f"body_pos={dbg['body_high_position']:.2f}"
                        ),
                        metadata={**dbg, "vol_ratio": vol_ratio},
                    )

        return ConfirmationResult(
            confirmed=False,
            pattern_name="signal_candle",
            strength=0.0,
            reason="no pattern matched",
            metadata={"vol_ratio": vol_ratio},
        )
