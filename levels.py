"""
LevelMap — Resistance/support level tracking with entry gate.

Tracks key price levels (whole/half dollars, PM high, VWAP, rejection zones)
and counts how many times price has tested and failed at each level.
An entry gate blocks new entries near levels with 2+ failures.

Toggle: WB_LEVEL_MAP_ENABLED=1 in .env
"""

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PriceLevel:
    price: float
    level_type: str  # "whole_dollar", "half_dollar", "pm_high", "vwap", "rejection"
    zone_width: float  # absolute width (0.5% of price)
    touch_count: int = 0
    fail_count: int = 0  # price entered zone then closed below
    break_count: int = 0  # consecutive closes above
    is_broken: bool = False  # reclassified as support after confirmed break
    last_touch_bar: int = 0

    @property
    def zone_top(self) -> float:
        return self.price + self.zone_width

    @property
    def zone_bottom(self) -> float:
        return self.price - self.zone_width


class LevelMap:
    """Tracks resistance/support levels and gates entries near failed resistance."""

    def __init__(
        self,
        enabled: bool = True,
        min_fail_count: int = 2,
        zone_width_pct: float = 0.5,
        break_confirm_bars: int = 2,
        break_min_volume_ratio: float = 1.5,
    ):
        self.enabled = enabled
        self.min_fail_count = min_fail_count
        self.zone_width_pct = zone_width_pct
        self.break_confirm_bars = break_confirm_bars
        self.break_min_volume_ratio = break_min_volume_ratio

        self.levels: list[PriceLevel] = []
        self._bar_count = 0
        self._recent_volumes: deque = deque(maxlen=20)

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def seed_levels(
        self,
        pm_high: Optional[float],
        current_price: float,
    ) -> None:
        """Generate levels at session start: whole/half dollars + PM high."""
        self.levels.clear()

        if current_price <= 0:
            return

        # Range: ±30% of current price
        lo = current_price * 0.70
        hi = current_price * 1.30

        # Whole dollar levels
        start = max(1, math.floor(lo))
        end = math.ceil(hi)
        for d in range(start, end + 1):
            p = float(d)
            if lo <= p <= hi:
                self._add_level(p, "whole_dollar")

        # Half dollar levels
        start_half = max(0.5, math.floor(lo * 2) / 2)
        p = start_half
        while p <= hi:
            # Only add if it's a true half (not a whole)
            if abs(p - round(p)) > 0.01:
                if lo <= p <= hi:
                    self._add_level(p, "half_dollar")
            p += 0.5

        # Premarket high
        if pm_high and pm_high > 0 and lo <= pm_high <= hi:
            self._add_level(pm_high, "pm_high")

    def _add_level(self, price: float, level_type: str) -> None:
        """Add a level, avoiding duplicates within zone overlap."""
        zone_w = max(0.03, price * (self.zone_width_pct / 100))
        # Skip if too close to an existing level
        for existing in self.levels:
            if abs(existing.price - price) < zone_w:
                return
        self.levels.append(PriceLevel(
            price=round(price, 4),
            level_type=level_type,
            zone_width=round(zone_w, 4),
        ))

    # ------------------------------------------------------------------
    # Dynamic updates
    # ------------------------------------------------------------------

    def update_vwap(self, vwap: Optional[float]) -> None:
        """Update or add the VWAP level."""
        if vwap is None or vwap <= 0:
            return
        for lv in self.levels:
            if lv.level_type == "vwap":
                lv.price = round(vwap, 4)
                lv.zone_width = max(0.03, vwap * (self.zone_width_pct / 100))
                return
        # First VWAP — add it
        self._add_level(vwap, "vwap")

    def on_bar_close(self, o: float, h: float, l: float, c: float, v: float) -> None:
        """Update level tracking on every 1-min bar close."""
        if not self.enabled:
            return

        self._bar_count += 1
        self._recent_volumes.append(v)
        avg_vol = sum(self._recent_volumes) / max(len(self._recent_volumes), 1)

        for lv in self.levels:
            if lv.is_broken:
                continue

            zone_top = lv.zone_top
            zone_bot = lv.zone_bottom

            # Touch: high reached into the zone from below
            touched = h >= zone_bot and l < zone_top
            if touched:
                lv.touch_count += 1
                lv.last_touch_bar = self._bar_count

                # Failure: entered zone but closed below it
                if c < zone_bot:
                    lv.fail_count += 1
                    lv.break_count = 0  # reset break streak

            # Break tracking: close above the zone
            if c > zone_top:
                # Only count break bars with enough volume
                if avg_vol > 0 and v >= avg_vol * self.break_min_volume_ratio:
                    lv.break_count += 1
                else:
                    lv.break_count += 1  # still count, volume just adds confidence

                if lv.break_count >= self.break_confirm_bars:
                    lv.is_broken = True
            elif c <= zone_top:
                # Close fell back into or below zone — reset break streak
                lv.break_count = 0

        # --- Dynamic rejection zone creation ---
        # If bar made a high into "no man's land" (not near any existing level)
        # and closed red with a meaningful rejection, create a new level there.
        # This captures intraday resistance at non-round-number prices.
        if c < o and h > 0:  # Red bar
            near_existing = any(
                abs(lv.price - h) < lv.zone_width * 2
                for lv in self.levels if not lv.is_broken
            )
            # Meaningful rejection: high at least 0.5% above close
            if not near_existing and h > c * 1.005:
                self._add_level(h, "rejection")

    # ------------------------------------------------------------------
    # Entry gate
    # ------------------------------------------------------------------

    def blocks_entry(self, entry_price: float, session_hod: float = 0.0) -> tuple[bool, str]:
        """Check if entry_price is near a failed resistance level.

        Args:
            entry_price: the proposed entry price
            session_hod: current session high of day. If entry is near HOD (within 1%),
                         the gate is bypassed — the stock is in price discovery, not resistance.

        Returns (blocked: bool, reason: str).
        """
        if not self.enabled:
            return False, ""

        # At or near session HOD = price discovery, not resistance. Don't block.
        if session_hod > 0 and entry_price >= session_hod * 0.99:
            return False, ""

        for lv in self.levels:
            if lv.is_broken:
                continue

            # Per-level-type fail thresholds:
            # Structural levels (whole/half dollar, PM high, VWAP) gate at min_fail_count (1)
            # Dynamic rejection zones need more evidence — gate at minimum 2 fails
            if lv.level_type == "rejection":
                required_fails = max(self.min_fail_count, 2)  # minimum 2 for rejections
            else:
                required_fails = self.min_fail_count  # 1 for structural levels

            if lv.fail_count < required_fails:
                continue
            # Check if entry price is within the level's zone
            if lv.zone_bottom <= entry_price <= lv.zone_top:
                reason = (
                    f"resistance_{lv.level_type}_{lv.price:.2f}"
                    f"_failed_{lv.fail_count}x"
                )
                return True, reason

        return False, ""

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_nearest_resistance(self, price: float) -> Optional[PriceLevel]:
        """Return the nearest unbroken level above current price."""
        best = None
        best_dist = float("inf")
        for lv in self.levels:
            if lv.is_broken:
                continue
            if lv.price > price:
                dist = lv.price - price
                if dist < best_dist:
                    best_dist = dist
                    best = lv
        return best

    def summary(self) -> str:
        """Debug summary for backtest output."""
        lines = [f"LevelMap ({len(self.levels)} levels, {self._bar_count} bars):"]
        for lv in sorted(self.levels, key=lambda x: x.price):
            status = "BROKEN" if lv.is_broken else "active"
            lines.append(
                f"  ${lv.price:.2f} ({lv.level_type}) "
                f"touches={lv.touch_count} fails={lv.fail_count} "
                f"breaks={lv.break_count} [{status}]"
            )
        return "\n".join(lines)
