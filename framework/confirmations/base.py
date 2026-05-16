"""ConfirmationProtocol — abstract interface for level-reaction confirmations.

A confirmation plugin observes price action at a level and verifies whether
the reaction is "real" by the strategy's definition. Examples include:

- signal_candle: doji / hammer / shooting star with volume confirmation
- breakout_candle: close beyond level with volume mult
- acceptance: N consecutive bars inside a zone (80% rule)
- rejection: failed test of level
- volume_confirm: relative-volume threshold checks
- l2_confirm: bid/ask imbalance + book stacking

Wave 1 ships only the protocol + ConfirmationResult value object.
Concrete plugins land in Wave 2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from framework.level_sources.base import Bar, Level


@dataclass(frozen=True)
class ConfirmationResult:
    """The verdict from a confirmation plugin.

    `confirmed` is the binary signal.
    `pattern_name` identifies which sub-pattern triggered (e.g. "doji",
    "hammer", "shooting_star" for signal_candle).
    `strength` is a normalized 0-1 score — useful for downstream conviction
    weighting when multiple confirmation rules compose.
    `reason` is a human-readable explanation for logging.
    """

    confirmed: bool
    pattern_name: str
    strength: float = 0.0
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Clamp strength to [0, 1] to keep downstream scoring sane.
        if self.strength < 0.0 or self.strength > 1.0:
            object.__setattr__(self, "strength", max(0.0, min(1.0, self.strength)))


@runtime_checkable
class ConfirmationProtocol(Protocol):
    """Plugin contract for confirmation rules.

    Args:
        level: The level the strategy is watching (price + kind).
        bars: Recent bars in chronological order (oldest first). Plugin
            chooses how many it inspects; typically the most-recent 1-5.
        l2_state: Optional L2 snapshot dict. Shape is plugin-specific;
            None when the strategy doesn't use L2 (or when L2 unavailable
            during backtest).

    Returns:
        ConfirmationResult.
    """

    def check_confirmation(
        self,
        level: Level,
        bars: list[Bar],
        l2_state: dict[str, Any] | None,
    ) -> ConfirmationResult: ...
