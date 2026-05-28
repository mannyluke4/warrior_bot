"""firestorm_trigger.py — Phase 3 Stage 1 prototype detector.

Per cowork_reports/2026-05-28_arming_research_phase3_prototype_directive.md.

A complementary arming path to MovementStrike. Fires when a 1-minute bar's
running tick count crosses a "firestorm" threshold AND the current price
is a configurable % above a reference baseline (default 5% above prior
close — the classic gap-and-run filter). This catches the pre-market /
early-morning gap-and-run pattern that SqueezeDetector is structurally
blind to because no consolidation-below-a-level phase precedes it.

Backtest-only. NOT wired into live sub-bot in this iteration.

Wire protocol (caller's responsibility):
    ft = FirestormTrigger(min_ticks=6000, min_gap_pct=5.0)
    for tick in stream:
        result = ft.update_and_check(
            price=tick.price,
            bar_minute=minute_index_for(tick.ts),
            prior_close=yesterdays_close,  # or None to skip gap filter
        )
        if result is not None:
            # detector fired — caller wires the entry
            open_firestorm_trigger_position(symbol, result)

The detector has NO position-state or exit logic. Its job is exclusively
"is now the moment to arm" — same single-responsibility shape as
MovementStrike's anomaly check.

State per instance: current bar's minute index, tick count, open, low,
and a "fired-this-minute" idempotency flag. One detector per (bot, symbol)
following the same pattern as MovementStrike.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class FirestormFire:
    """Return shape on detector fire — what the caller needs to open
    a position. Mirrors regime_shift's fire payload."""
    trigger_price: float
    bar_open: float
    bar_low: float
    bar_minute: int
    tick_count: int
    gap_pct_vs_prior_close: Optional[float]


class FirestormTrigger:
    """Per-symbol per-bot detector. Fires at most once per bar."""

    def __init__(self, min_ticks: int = 6000, min_gap_pct: float = 5.0):
        if min_ticks < 1:
            raise ValueError("min_ticks must be >= 1")
        self.min_ticks = int(min_ticks)
        self.min_gap_pct = float(min_gap_pct)
        # Current in-progress bar state
        self._cur_minute: Optional[int] = None
        self._cur_tick_count = 0
        self._cur_open: Optional[float] = None
        self._cur_low: Optional[float] = None
        self._fired_this_minute = False

    def update_and_check(
        self,
        price: float,
        bar_minute: int,
        prior_close: Optional[float],
    ) -> Optional[FirestormFire]:
        """Per-tick update. Returns a FirestormFire on the tick that
        triggers; otherwise None.

        `prior_close` is the static reference baseline (e.g., yesterday's
        close) used by the gap filter. Pass None to skip the gap check
        entirely — useful for ablation studies. Note that with None, the
        detector becomes a pure tick-count threshold and will fire on
        any 6000-tick bar regardless of price level vs yesterday.
        """
        if bar_minute != self._cur_minute:
            # Bar rollover: reset state for new bar.
            self._cur_minute = bar_minute
            self._cur_tick_count = 1
            self._cur_open = price
            self._cur_low = price
            self._fired_this_minute = False
            return None

        # Same bar — accumulate.
        self._cur_tick_count += 1
        if self._cur_low is None or price < self._cur_low:
            self._cur_low = price

        if self._fired_this_minute:
            return None
        if self._cur_tick_count < self.min_ticks:
            return None

        # Threshold crossed THIS tick — check gap filter.
        gap_pct: Optional[float] = None
        if prior_close is not None and prior_close > 0:
            gap_pct = (price - prior_close) / prior_close * 100.0
            if gap_pct < self.min_gap_pct:
                return None  # below gap floor — not a gap-and-run

        self._fired_this_minute = True
        return FirestormFire(
            trigger_price=price,
            bar_open=self._cur_open if self._cur_open is not None else price,
            bar_low=self._cur_low if self._cur_low is not None else price,
            bar_minute=bar_minute,
            tick_count=self._cur_tick_count,
            gap_pct_vs_prior_close=gap_pct,
        )

    def reset(self) -> None:
        """Force reset between trading sessions. Tests call this; live
        callers can re-instantiate instead."""
        self._cur_minute = None
        self._cur_tick_count = 0
        self._cur_open = None
        self._cur_low = None
        self._fired_this_minute = False
