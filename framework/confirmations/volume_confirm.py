"""VolumeConfirm — threshold-based volume confirmation.

Compares the entry bar's volume against a configurable baseline:
- "prior_bar": volume of bar immediately before entry bar
- "20_bar_avg": average volume over the prior 20 bars
- "session_avg": average volume over all bars in the session so far

Usage:

    >>> vc = VolumeConfirm(min_relative_volume=1.5, comparison="prior_bar")
    >>> bars = [Bar(...), Bar(...)]  # last is entry bar
    >>> result = vc.check_confirmation(level=None, bars=bars, l2_state=None)
    >>> result.confirmed
    True

Edge cases:
- Empty bars list  -> ConfirmationResult(confirmed=False, reason="no bars")
- Baseline <= 0    -> ConfirmationResult(confirmed=False, reason="zero baseline")
- NaN volume       -> ConfirmationResult(confirmed=False, reason="nan volume")
- Insufficient prior bars (e.g. 20-bar avg with only 5 bars):
                       falls back to whatever is available; returns reason noting it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Optional

from framework.confirmations.base import ConfirmationResult
from framework.level_sources.base import Bar, Level


Comparison = Literal["prior_bar", "20_bar_avg", "session_avg"]


def _is_finite(x: float) -> bool:
    """Return True if x is a real finite number (not NaN/Inf)."""
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


@dataclass
class VolumeConfirm:
    """Volume-threshold confirmation plugin.

    Args:
        min_relative_volume: Minimum (entry_volume / baseline) ratio.
            E.g. 2.0 means entry bar volume must be >= 2x the baseline.
        comparison: Which baseline to compare against.
            One of "prior_bar", "20_bar_avg", "session_avg".

    Example:
        >>> vc = VolumeConfirm(min_relative_volume=2.0, comparison="20_bar_avg")
    """

    min_relative_volume: float = 1.5
    comparison: Comparison = "prior_bar"

    def _baseline(self, bars: list[Bar]) -> tuple[float, str]:
        """Compute the baseline volume + a label for the reason string.

        Returns (baseline_value, baseline_label). baseline_value <= 0 means
        baseline could not be computed.
        """
        if self.comparison == "prior_bar":
            if len(bars) < 2:
                return 0.0, "prior_bar (missing)"
            v = bars[-2].volume
            return (v if _is_finite(v) else 0.0), "prior_bar"

        if self.comparison == "20_bar_avg":
            # bars[-1] is entry; baseline = mean of bars[-21:-1] (20 prior)
            window = bars[-21:-1]
            if not window:
                return 0.0, "20_bar_avg (missing)"
            vols = [b.volume for b in window if _is_finite(b.volume)]
            if not vols:
                return 0.0, "20_bar_avg (no valid)"
            return sum(vols) / len(vols), f"{len(vols)}_bar_avg"

        # session_avg
        if len(bars) < 2:
            return 0.0, "session_avg (missing)"
        prior = bars[:-1]
        vols = [b.volume for b in prior if _is_finite(b.volume)]
        if not vols:
            return 0.0, "session_avg (no valid)"
        return sum(vols) / len(vols), f"session_avg({len(vols)})"

    def check_confirmation(
        self,
        level: Optional[Level],
        bars: list[Bar],
        l2_state: Optional[dict[str, Any]] = None,
    ) -> ConfirmationResult:
        if not bars:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="volume_confirm",
                strength=0.0,
                reason="no bars",
            )

        entry_vol = bars[-1].volume
        if not _is_finite(entry_vol):
            return ConfirmationResult(
                confirmed=False,
                pattern_name="volume_confirm",
                strength=0.0,
                reason="nan entry volume",
            )

        baseline, label = self._baseline(bars)
        if baseline <= 0:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="volume_confirm",
                strength=0.0,
                reason=f"zero baseline ({label})",
            )

        ratio = entry_vol / baseline
        confirmed = ratio >= self.min_relative_volume

        # Strength: 0 below threshold, asymptotic toward 1 as ratio grows.
        # ratio == threshold  -> 0.5; ratio == 2*threshold -> ~0.67
        denom = max(self.min_relative_volume, 1e-9)
        strength = min(1.0, max(0.0, ratio / (denom + ratio))) if ratio > 0 else 0.0

        return ConfirmationResult(
            confirmed=confirmed,
            pattern_name="volume_confirm",
            strength=strength,
            reason=(
                f"entry_vol={entry_vol:.0f} / {label}={baseline:.0f} "
                f"= {ratio:.2f}x (min={self.min_relative_volume:.2f})"
            ),
            metadata={
                "entry_volume": entry_vol,
                "baseline": baseline,
                "baseline_label": label,
                "ratio": ratio,
            },
        )
