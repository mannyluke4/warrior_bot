"""VIX regime classifier with size-multiplier hooks.

Wave 1, Agent E, deliverable 4 (DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md §3).

Per Manny review (5/17): hooks built, DEFAULT OFF. Validate from backtest.
When disabled, `size_multiplier` returns `base_size` unmodified — no side
effects, no network calls, truly inert.

Regimes (boundary convention: lower-inclusive, upper-exclusive except 'extreme'):
  low      : VIX < 16
  optimal  : 16 <= VIX < 28
  high     : 28 <= VIX < 40
  extreme  : VIX >= 40

Size multipliers (when enabled):
  optimal  : 1.0×
  low      : 0.5×
  high     : 0.75×
  extreme  : 0.0× (no trades)

Environment toggle:
  WB_USE_VIX_REGIME=0 (default) → disabled
  WB_USE_VIX_REGIME=1            → enabled
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Optional


REGIME_LOW = "low"
REGIME_OPTIMAL = "optimal"
REGIME_HIGH = "high"
REGIME_EXTREME = "extreme"

_SIZE_MULTIPLIERS: dict[str, float] = {
    REGIME_OPTIMAL: 1.0,
    REGIME_LOW: 0.5,
    REGIME_HIGH: 0.75,
    REGIME_EXTREME: 0.0,
}


def _env_default_enabled() -> bool:
    return os.environ.get("WB_USE_VIX_REGIME", "0") == "1"


@dataclass
class VIXRegime:
    """VIX classifier + sizing-multiplier hook.

    Parameters
    ----------
    enabled : bool | None
        If None (default), reads `WB_USE_VIX_REGIME` env var (default "0").
        If explicitly True/False, overrides the env var.
    optimal_range : tuple[float, float]
        (low_bound, high_bound) for the 'optimal' regime. Default (16, 28).
    """

    enabled: Optional[bool] = None
    optimal_range: tuple[float, float] = (16.0, 28.0)
    extreme_threshold: float = 40.0

    def __post_init__(self) -> None:
        if self.enabled is None:
            object.__setattr__(self, "enabled", _env_default_enabled())

    # ------------------------------------------------------------------ #
    # Classification
    # ------------------------------------------------------------------ #
    def current_regime(self, vix_value: float) -> str:
        """Return regime label for a VIX value.

        Returns 'optimal' as a safe default if vix_value is not finite.
        """
        try:
            v = float(vix_value)
        except (TypeError, ValueError):
            return REGIME_OPTIMAL
        if not math.isfinite(v):
            return REGIME_OPTIMAL
        lo, hi = self.optimal_range
        if v < lo:
            return REGIME_LOW
        if v < hi:
            return REGIME_OPTIMAL
        if v < self.extreme_threshold:
            return REGIME_HIGH
        return REGIME_EXTREME

    # ------------------------------------------------------------------ #
    # Sizing hook
    # ------------------------------------------------------------------ #
    def size_multiplier(self, vix_value: float, base_size: int) -> int:
        """Return adjusted share count given a VIX value.

        DEFAULT BEHAVIOR (enabled=False): returns base_size unchanged.
        ENABLED BEHAVIOR: multiplies by regime factor and floors to int.

        Never raises. Never performs IO.
        """
        try:
            bs = int(base_size)
        except (TypeError, ValueError):
            return 0
        if bs <= 0:
            return 0
        if not self.enabled:
            return bs

        regime = self.current_regime(vix_value)
        mult = _SIZE_MULTIPLIERS.get(regime, 1.0)
        out = int(math.floor(bs * mult))
        return max(out, 0)

    # ------------------------------------------------------------------ #
    # Best-effort VIX fetch — only invoked when caller asks.
    # When disabled or on any error, returns None.
    # ------------------------------------------------------------------ #
    def get_vix_value(self) -> Optional[float]:
        """Best-effort VIX fetch via Databento. When disabled OR if the
        client/credentials are not available, returns None. Never raises.
        """
        if not self.enabled:
            return None
        try:
            import databento  # noqa: F401  (presence check)
        except ImportError:
            return None
        # Real Databento fetch is not wired in this scaffold — Manny's
        # directive is "build hooks". Returning None is the safe default
        # until Wave 4 wires a live source. Callers should fall through
        # to a cached / config-supplied value.
        return None


__all__ = [
    "VIXRegime",
    "REGIME_LOW",
    "REGIME_OPTIMAL",
    "REGIME_HIGH",
    "REGIME_EXTREME",
]
