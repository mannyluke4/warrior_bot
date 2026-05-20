"""Movement-anomaly strike trigger (2026-05-20).

Replaces the squeeze detector's price-level trigger with an intra-bar
movement-anomaly trigger. The arm logic (level + 0.02) still picks the
setup; this module decides WHEN within the post-arm window to actually
fire, by watching for the first bar whose upward movement exceeds the
rolling average of recent bar bodies.

Intent (Manny, 2026-05-20): the arm price isn't the goal — entering
near the start of the breakout move is. The bot was filling at the top
of multi-minute recoveries because the level-cross by definition happens
at a local high. Movement-anomaly catches the acceleration earlier.

Mechanics:
  - Track |close - open| (body) for the last N closed bars
  - On each tick, update the in-progress bar's running body
    = (current_price - bar_open)
  - Fire when running body > avg(body history) × multiplier AND running
    body is positive (upward bias — don't strike on downward expansion)

Self-contained — no project imports. Sub-bot can drop this in directly.
"""

from collections import deque
from typing import Optional


class MovementStrike:
    """Per-symbol intra-bar movement-anomaly trigger.

    Caller responsibilities:
      - Call ``update_and_check(price, bar_minute)`` on every tick.
      - Only act on the True return when the detector is also ARMED.
      - The tracker keeps running across arms — no per-arm reset needed.

    Args:
      lookback_bars: how many closed bars to average over.
      multiplier:    intra_body must exceed avg × multiplier to fire.
    """

    def __init__(self, lookback_bars: int = 5, multiplier: float = 1.0,
                 stop_lookback_bars: int = 10):
        self.lookback_bars = lookback_bars
        self.multiplier = multiplier
        self.stop_lookback_bars = stop_lookback_bars
        self._body_history: deque = deque(maxlen=lookback_bars)
        # Bar-low history for consolidation-based stop: low of the last N
        # CLOSED bars (excluding the in-progress anomaly bar itself).
        self._low_history: deque = deque(maxlen=stop_lookback_bars)
        self._cur_minute: Optional[int] = None
        self._cur_open: Optional[float] = None
        self._cur_last: Optional[float] = None
        self._cur_low: Optional[float] = None

    def update_and_check(self, price: float, bar_minute: int) -> bool:
        """Per-tick update. Returns True iff upward anomaly fires this tick.

        ``bar_minute`` is an integer minute key (e.g., hour*60 + minute in
        ET). Any change triggers a new-bar transition: the previous bar's
        |body| is rolled into history and the new bar's open is set.
        """
        if bar_minute != self._cur_minute:
            if (self._cur_open is not None and self._cur_last is not None
                    and self._cur_low is not None):
                self._body_history.append(abs(self._cur_last - self._cur_open))
                self._low_history.append(self._cur_low)
            self._cur_minute = bar_minute
            self._cur_open = price
            self._cur_last = price
            self._cur_low = price
            return False  # fresh bar — no anomaly possible yet

        self._cur_last = price
        if self._cur_low is None or price < self._cur_low:
            self._cur_low = price

        intra_body = price - self._cur_open  # signed; > 0 means upward
        if intra_body <= 0:
            return False  # downward bias filter
        if len(self._body_history) < self.lookback_bars:
            return False  # warming up

        avg_body = sum(self._body_history) / len(self._body_history)
        return intra_body > avg_body * self.multiplier

    def get_consolidation_stop(self) -> Optional[float]:
        """Low of the last N CLOSED bars before the anomaly bar — i.e.,
        the floor of the pre-uptick consolidation. Returns None until
        there's any closed-bar history.
        """
        if not self._low_history:
            return None
        return min(self._low_history)

    def reset_history(self) -> None:
        """Clear all bar history. Call on detector arm so the rolling
        averages and consolidation low only reflect bars seen AFTER the
        setup was identified — pre-arm noise (irrelevant context) is
        dropped.
        """
        self._body_history.clear()
        self._low_history.clear()
        # Keep the in-progress bar tracking intact; it'll roll into
        # history on the next bar transition just like normal.

    # ------------------------------------------------------------------
    # Diagnostics — not load-bearing
    # ------------------------------------------------------------------
    @property
    def avg_body(self) -> float:
        if not self._body_history:
            return 0.0
        return sum(self._body_history) / len(self._body_history)

    @property
    def history_full(self) -> bool:
        return len(self._body_history) >= self.lookback_bars
