from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


def ema_next(prev: Optional[float], price: float, length: int) -> float:
    alpha = 2.0 / (length + 1.0)
    return price if prev is None else (price * alpha) + (prev * (1.0 - alpha))


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

        return self

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