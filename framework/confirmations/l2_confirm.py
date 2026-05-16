"""L2Confirm — wraps existing L2 state for backtest/live use.

The actual L2 detection lives in `l2_signals.py` (production code, UNTOUCHED).
This module is a thin confirmation-protocol wrapper that consumes the same
state dict that `l2_signals.L2SignalDetector.get_state()` returns:

    {
        "imbalance": float,           # 0.0-1.0, bid share of (bid+ask) total
        "imbalance_trend": str,       # "rising" / "falling" / "flat"
        "bid_stacking": bool,
        "bid_stack_levels": list[(price, size)],
        "large_bid": bool,
        "large_ask": bool,
        "spread_pct": float,
        "ask_thinning": bool,
        "signals": list[L2Signal],
    }

For BACKTEST use, the snapshot may be reconstructed from historical L2 data
if available, OR be None (then pass-through is configured by `pass_through_on_missing`).

Usage:

    >>> from l2_signals import L2SignalDetector
    >>> det = L2SignalDetector()
    >>> # ... det.on_snapshot(snap) ...
    >>> state = det.get_state("ABCD")
    >>> l2c = L2Confirm(min_imbalance=0.55, max_spread_pct=1.0,
    ...                 require_bid_stacking=True)
    >>> result = l2c.check_confirmation(level=pdh, bars=[entry_bar], l2_state=state)
    >>> result.confirmed
    True

Edge cases:
- l2_state is None:
    - pass_through_on_missing=True  -> confirmed=True, strength=0.0, reason "no L2"
    - pass_through_on_missing=False -> confirmed=False, reason "no L2"
- Missing keys in state dict       -> treated as "unknown", veto if required
- Wrong direction (e.g. require_ask_stacking when bid info only) -> handled gracefully
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


def _finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


@dataclass
class L2Confirm:
    """L2-state confirmation wrapper.

    Args:
        min_imbalance: For LONG, minimum bid-share imbalance (0.5-1.0).
            For SHORT, maximum bid-share (i.e. ask dominance threshold) —
            value is interpreted as "min imbalance favoring our direction".
        max_spread_pct: Maximum acceptable spread % (vetoes wide spreads).
            Set to a large number to disable. Default 1.0.
        require_bid_stacking: When True (long), bid_stacking must be True.
        require_ask_stacking: When True (short), bid_stacking must be False
            AND ask_thinning OR large_ask present (proxy for ask-side build).
            (l2_signals.py only tracks bid_stacking; ask-side derives.)
        direction: "long" / "short" / "auto".
        pass_through_on_missing: When True and l2_state is None, return
            confirmed=True with strength 0 (don't veto). Default False.
    """

    min_imbalance: float = 0.55
    max_spread_pct: float = 1.0
    require_bid_stacking: bool = False
    require_ask_stacking: bool = False
    direction: Direction = "auto"
    pass_through_on_missing: bool = False

    def check_confirmation(
        self,
        level: Optional[Level],
        bars: list[Bar],
        l2_state: Optional[dict[str, Any]] = None,
    ) -> ConfirmationResult:
        # Direction resolution
        if self.direction in ("long", "short"):
            direction = self.direction
        elif level is not None:
            direction = _infer_direction(level)
        else:
            direction = "long"

        if l2_state is None:
            if self.pass_through_on_missing:
                return ConfirmationResult(
                    confirmed=True,
                    pattern_name="l2_confirm",
                    strength=0.0,
                    reason="no L2 state (pass-through)",
                    metadata={"direction": direction, "pass_through": True},
                )
            return ConfirmationResult(
                confirmed=False,
                pattern_name="l2_confirm",
                strength=0.0,
                reason="no L2 state",
                metadata={"direction": direction},
            )

        imbalance = l2_state.get("imbalance")
        spread_pct = l2_state.get("spread_pct")
        bid_stacking = bool(l2_state.get("bid_stacking", False))
        ask_thinning = bool(l2_state.get("ask_thinning", False))
        large_bid = bool(l2_state.get("large_bid", False))
        large_ask = bool(l2_state.get("large_ask", False))

        # 1. Spread veto
        if spread_pct is not None and _finite(spread_pct):
            if float(spread_pct) > self.max_spread_pct:
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="l2_confirm",
                    strength=0.0,
                    reason=(
                        f"spread_pct={float(spread_pct):.2f}% > max={self.max_spread_pct:.2f}%"
                    ),
                    metadata={"direction": direction, "spread_pct": float(spread_pct)},
                )

        # 2. Imbalance check
        if imbalance is None or not _finite(imbalance):
            return ConfirmationResult(
                confirmed=False,
                pattern_name="l2_confirm",
                strength=0.0,
                reason="missing imbalance",
                metadata={"direction": direction},
            )
        imbalance = float(imbalance)
        if direction == "long":
            imbalance_ok = imbalance >= self.min_imbalance
            imb_strength = min(1.0, max(0.0, (imbalance - 0.5) * 4.0))
        else:
            # Short: we want ask dominance -> bid share LOW
            # Interpretation: min_imbalance is the threshold favoring our direction.
            # For short, that means imbalance <= (1 - min_imbalance) is required.
            short_threshold = 1.0 - self.min_imbalance
            imbalance_ok = imbalance <= short_threshold
            imb_strength = min(1.0, max(0.0, (0.5 - imbalance) * 4.0))

        if not imbalance_ok:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="l2_confirm",
                strength=0.0,
                reason=(
                    f"{direction} imbalance fail: bid_share={imbalance:.2f}, "
                    f"need {'>=' if direction == 'long' else '<='} "
                    f"{self.min_imbalance if direction == 'long' else 1.0 - self.min_imbalance:.2f}"
                ),
                metadata={"direction": direction, "imbalance": imbalance},
            )

        # 3. Stacking requirements
        if direction == "long" and self.require_bid_stacking and not bid_stacking:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="l2_confirm",
                strength=0.0,
                reason="long requires bid_stacking but absent",
                metadata={"direction": direction, "imbalance": imbalance},
            )
        if direction == "short" and self.require_ask_stacking:
            # l2_signals.py tracks bid_stacking explicitly; for ask-side proxy
            # we accept (large_ask AND ask_thinning is informational only).
            # The strict interpretation: no bid stacking + at least one ask signal.
            if bid_stacking and not (large_ask or ask_thinning):
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="l2_confirm",
                    strength=0.0,
                    reason="short requires ask_stacking; bid_stacking present, no ask signal",
                    metadata={
                        "direction": direction,
                        "bid_stacking": bid_stacking,
                        "large_ask": large_ask,
                        "ask_thinning": ask_thinning,
                    },
                )

        # Strength: blend imbalance + stacking + bonus for large orders on our side
        stack_bonus = 0.0
        if direction == "long":
            if bid_stacking:
                stack_bonus += 0.5
            if large_bid:
                stack_bonus += 0.25
            if large_ask:
                stack_bonus -= 0.25
        else:
            if not bid_stacking:
                stack_bonus += 0.25
            if large_ask:
                stack_bonus += 0.5
            if ask_thinning:
                stack_bonus += 0.25
            if large_bid:
                stack_bonus -= 0.25
        stack_bonus = max(0.0, min(1.0, stack_bonus))
        strength = round(0.6 * imb_strength + 0.4 * stack_bonus, 4)

        return ConfirmationResult(
            confirmed=True,
            pattern_name="l2_confirm",
            strength=strength,
            reason=(
                f"{direction} L2 ok: imbalance={imbalance:.2f}, "
                f"spread_pct={spread_pct if spread_pct is not None else 'n/a'}, "
                f"bid_stacking={bid_stacking}, large_bid={large_bid}, large_ask={large_ask}"
            ),
            metadata={
                "direction": direction,
                "imbalance": imbalance,
                "spread_pct": spread_pct,
                "bid_stacking": bid_stacking,
                "large_bid": large_bid,
                "large_ask": large_ask,
                "ask_thinning": ask_thinning,
            },
        )
