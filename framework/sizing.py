"""Position sizing — half-Kelly with bar-volume participation cap.

Wave 1, Agent E, deliverable 1 (DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md §3).

Half-Kelly formula:
    shares = (equity * risk_per_trade_pct / 2) / abs(entry_price - stop_price)

Then capped at:
    max_bar_volume_pct * recent_bar_volume / entry_price

The cap implements the "5% of bar volume" participation rule from
research_backtest_infrastructure.md §3 (realistic fill modeling — queue
position uncertainty discount 20-40%). 5% is the default; configurable.

Defensive contract: any invalid input (zero/negative equity, zero R, zero
or negative entry, non-finite values) returns 0 shares. Never raises —
sizing must not crash the bot.

Public API:
    HalfKellySizer(risk_per_trade_pct=1.0, max_bar_volume_pct=0.05)
    sizer.size_position(equity, entry_price, stop_price, recent_bar_volume)
        -> int  # share count, always >= 0
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class HalfKellySizer:
    """Half-Kelly position sizer with bar-volume participation cap.

    Attributes
    ----------
    risk_per_trade_pct: float
        Percent of equity to risk per trade, e.g. 1.0 = 1%.
    max_bar_volume_pct: float
        Cap on shares as fraction of recent_bar_volume. Default 0.05 (5%).
    """

    risk_per_trade_pct: float = 1.0
    max_bar_volume_pct: float = 0.05

    @staticmethod
    def _is_finite_positive(x: float) -> bool:
        try:
            return math.isfinite(x) and x > 0
        except (TypeError, ValueError):
            return False

    def size_position(
        self,
        equity: float,
        entry_price: float,
        stop_price: float,
        recent_bar_volume: float,
    ) -> int:
        """Compute share count for a trade.

        Returns 0 for any invalid input. Never raises.
        """
        # Validate scalars
        if not self._is_finite_positive(equity):
            return 0
        if not self._is_finite_positive(entry_price):
            return 0
        try:
            if not math.isfinite(stop_price):
                return 0
        except (TypeError, ValueError):
            return 0
        if recent_bar_volume is None:
            return 0
        try:
            if not math.isfinite(float(recent_bar_volume)):
                return 0
        except (TypeError, ValueError):
            return 0
        if recent_bar_volume < 0:
            return 0

        # Validate config
        if self.risk_per_trade_pct <= 0:
            return 0
        if self.max_bar_volume_pct < 0:
            return 0

        # Per-share risk (R)
        r_per_share = abs(entry_price - stop_price)
        if r_per_share <= 0:
            return 0

        # Half-Kelly notional risk
        risk_dollars = equity * (self.risk_per_trade_pct / 100.0) * 0.5
        raw_shares = risk_dollars / r_per_share
        if not math.isfinite(raw_shares) or raw_shares <= 0:
            return 0

        # Bar-volume participation cap.
        # Per directive: shares cap = max_bar_volume_pct * recent_bar_volume
        #                              / entry_price
        # (This treats `recent_bar_volume` as bar dollar-volume when the user
        # supplies dollar volume; or as share volume when shares are supplied.
        # The formula is taken verbatim from the directive — callers pass the
        # measure consistent with how max_bar_volume_pct is calibrated.)
        if recent_bar_volume == 0 or self.max_bar_volume_pct == 0:
            volume_cap_shares = 0.0
        else:
            volume_cap_shares = (
                self.max_bar_volume_pct * recent_bar_volume / entry_price
            )

        shares = min(raw_shares, volume_cap_shares)
        shares_int = int(math.floor(shares))
        return max(shares_int, 0)


__all__ = ["HalfKellySizer"]
