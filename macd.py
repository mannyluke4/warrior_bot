from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, Tuple


def ema_next(prev: Optional[float], price: float, length: int) -> float:
    alpha = 2.0 / (length + 1.0)
    return price if prev is None else (price * alpha) + (prev * (1.0 - alpha))


# Length of the rolling (macd, signal, hist) history buffer maintained on
# every MACDState. 4 bars is enough for chop_gate_v3.macd_rolling_over,
# which needs (now, 1ago, 2ago). Keep small so memory stays bounded.
_MACD_HISTORY_LEN = 4


@dataclass
class MACDState:
    ema12: Optional[float] = None
    ema26: Optional[float] = None
    macd: Optional[float] = None
    signal: Optional[float] = None
    hist: Optional[float] = None

    prev_macd: Optional[float] = None
    prev_signal: Optional[float] = None
    prev_hist: Optional[float] = None

    # Rolling history of the last N closed-bar (macd, signal, hist)
    # tuples in newest-LAST order. Updated additively at the end of
    # update(); does not alter any existing field semantics, so the
    # extension is safe for the WB detector + any other consumer of
    # the legacy fields (bullish/bearish_cross/etc).
    #
    # chop_gate_v3.macd_rolling_over() reads this via the line_at /
    # signal_at / histogram_at accessors below (index 0 = newest).
    _history: Deque[Tuple[float, float, float]] = field(
        default_factory=lambda: deque(maxlen=_MACD_HISTORY_LEN),
        repr=False,
        compare=False,
    )

    def update(self, close: float) -> "MACDState":
        # --- Update EMAs ---
        self.ema12 = ema_next(self.ema12, close, 12)
        self.ema26 = ema_next(self.ema26, close, 26)

        if self.ema12 is None or self.ema26 is None:
            return self

        # --- Store previous values ---
        self.prev_macd = self.macd
        self.prev_signal = self.signal
        self.prev_hist = self.hist

        # --- Compute MACD ---
        self.macd = self.ema12 - self.ema26
        self.signal = ema_next(self.signal, self.macd, 9)

        if self.signal is not None:
            self.hist = self.macd - self.signal

        # --- Append to rolling history (purely additive) ---
        # Only push when all three are populated. Once signal is non-None,
        # hist is also non-None on the same bar.
        if (self.macd is not None and self.signal is not None
                and self.hist is not None):
            self._history.append(
                (float(self.macd), float(self.signal), float(self.hist))
            )

        return self

    # -------------------------
    # History accessors (additive — for chop_gate_v3 + diagnostics)
    # -------------------------

    def has_history(self, bars: int = 3) -> bool:
        """True iff at least `bars` closed-bar (macd, signal, hist) tuples
        are present in the rolling buffer."""
        return len(self._history) >= int(bars)

    def line_at(self, i: int) -> Optional[float]:
        """Return MACD line `i` bars ago (i=0 → most recent closed bar).
        Returns None when history doesn't extend that far back."""
        h = self._history
        n = len(h)
        idx = n - 1 - int(i)
        if idx < 0 or idx >= n:
            return None
        return h[idx][0]

    def signal_at(self, i: int) -> Optional[float]:
        """Return signal-line value `i` bars ago (i=0 → most recent)."""
        h = self._history
        n = len(h)
        idx = n - 1 - int(i)
        if idx < 0 or idx >= n:
            return None
        return h[idx][1]

    def histogram_at(self, i: int) -> Optional[float]:
        """Return histogram value `i` bars ago (i=0 → most recent)."""
        h = self._history
        n = len(h)
        idx = n - 1 - int(i)
        if idx < 0 or idx >= n:
            return None
        return h[idx][2]

    # -------------------------
    # Signal helpers (existing)
    # -------------------------

    def bullish(self) -> bool:
        return (
            self.macd is not None
            and self.signal is not None
            and self.macd > self.signal
        )

    def bearish_cross(self) -> bool:
        """
        MACD crossed DOWN through signal line.
        Used to detect backside / walk-away conditions.
        """
        if (
            self.prev_macd is None
            or self.prev_signal is None
            or self.macd is None
            or self.signal is None
        ):
            return False

        return self.prev_macd >= self.prev_signal and self.macd < self.signal

    # -------------------------
    # NEW: Strength / scoring helpers
    # -------------------------

    def macd_diff(self) -> Optional[float]:
        """MACD - signal (same as histogram). Positive means bullish."""
        if self.macd is None or self.signal is None:
            return None
        return float(self.macd - self.signal)

    def hist_slope(self) -> Optional[float]:
        """Is momentum expanding (hist rising) or fading (hist falling)?"""
        if self.hist is None or self.prev_hist is None:
            return None
        return float(self.hist - self.prev_hist)

    def strength_score(self, price: float) -> float:
        """
        Returns a bounded score in roughly [-10, +10].
        Uses relative normalization so it works across $1 and $30 tickers.

        - Positive = supportive MACD
        - Negative = MACD is weak/negative relative to price
        """
        if self.macd is None or self.signal is None or self.hist is None:
            return 0.0

        # Normalize by price to avoid "big dollar" bias
        px = max(0.01, float(price))
        diff = float(self.macd - self.signal)  # hist
        rel = diff / px  # e.g., 0.001 = 0.10% of price

        # Base points from bullish/bearish separation
        # Tune these thresholds later with real logs.
        score = 0.0
        if rel >= 0.0008:       # >= 0.08% of price
            score += 6.0
        elif rel >= 0.0004:     # >= 0.04%
            score += 4.0
        elif rel > 0.0:
            score += 2.0
        elif rel <= -0.0008:
            score -= 6.0
        elif rel <= -0.0004:
            score -= 4.0
        else:
            score -= 2.0

        # Momentum expansion bonus / fading penalty
        slope = self.hist_slope()
        if slope is not None:
            if slope > 0:
                score += 1.5
            elif slope < 0:
                score -= 1.0

        # Clamp to keep score sane
        if score > 10.0:
            score = 10.0
        if score < -10.0:
            score = -10.0
        return score