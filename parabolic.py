"""
ParabolicRegimeDetector — Multi-signal parabolic regime detection for exit logic.

Replaces the simple _in_parabolic_grace() heuristic with a richer detector that:
1. Detects parabolic regimes via 3 signals (consecutive new highs, volume expansion, ATR expansion)
2. Suppresses BE and TW exits during parabolic
3. Provides a wider Chandelier trailing stop as alternative to fixed trail
4. Detects exhaustion for proactive trim signals
5. Enforces minimum hold times after entry

Toggle: WB_PARABOLIC_REGIME_ENABLED=1 in .env
"""

from collections import deque
from dataclasses import dataclass, field


def _is_shooting_star(o: float, h: float, l: float, c: float) -> bool:
    """Standalone shooting star check (avoids circular import from candles.py)."""
    body = abs(c - o)
    full_range = h - l
    if full_range <= 0:
        return False
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    return (upper_wick >= 2 * body) and (lower_wick < body * 0.5) and (full_range > 0)


@dataclass
class ParabolicState:
    is_parabolic: bool = False
    consecutive_new_highs: int = 0
    volume_expansion_ratio: float = 1.0
    atr_expansion_ratio: float = 1.0
    chandelier_stop: float = 0.0
    hold_until_bar: int = 0  # minimum hold bar count
    exhaustion_signals: int = 0


class ParabolicRegimeDetector:
    """Detects parabolic momentum regimes and provides exit guidance."""

    def __init__(
        self,
        enabled: bool = True,
        min_new_highs: int = 3,
        min_vol_expansion: float = 1.5,
        min_atr_expansion: float = 1.3,
        chandelier_mult: float = 2.5,
        min_hold_bars_normal: int = 3,      # 3 x 10s = 30s
        min_hold_bars_parabolic: int = 12,   # 12 x 10s = 120s
        exhaustion_vol_divergence: float = 0.5,
    ):
        self.enabled = enabled
        self.min_new_highs = min_new_highs
        self.min_vol_expansion = min_vol_expansion
        self.min_atr_expansion = min_atr_expansion
        self.chandelier_mult = chandelier_mult
        self.min_hold_bars_normal = min_hold_bars_normal
        self.min_hold_bars_parabolic = min_hold_bars_parabolic
        self.exhaustion_vol_divergence = exhaustion_vol_divergence

        # Internal tracking
        self._highs: deque = deque(maxlen=50)
        self._volumes: deque = deque(maxlen=50)
        self._atrs: deque = deque(maxlen=50)  # bar range as ATR proxy
        self._bar_count: int = 0
        self._peak_vol: float = 0.0
        self._peak_high: float = 0.0

        self.state = ParabolicState()

    def on_10s_bar(
        self,
        o: float, h: float, l: float, c: float,
        v: float,
        entry_price: float,
        r_value: float,
    ) -> ParabolicState:
        """Feed a 10-second bar. Returns updated parabolic state.

        Args:
            o, h, l, c: bar OHLC
            v: bar volume (0 if unavailable — detector works without it)
            entry_price: current trade entry price
            r_value: current trade R value (entry - stop)
        """
        if not self.enabled:
            return self.state

        self._bar_count += 1
        self._highs.append(h)
        atr_proxy = h - l
        self._atrs.append(atr_proxy)
        has_volume = v > 0
        if has_volume:
            self._volumes.append(v)
            self._peak_vol = max(self._peak_vol, v)
        self._peak_high = max(self._peak_high, h)

        # --- Signal 1: Consecutive new highs ---
        if len(self._highs) >= 2:
            # Is this bar a new high vs the peak of the last N bars?
            lookback = list(self._highs)[-min(len(self._highs), self.min_new_highs + 1):-1]
            if lookback and h > max(lookback):
                self.state.consecutive_new_highs += 1
            else:
                # Decay — allow 1 bar of pause without resetting
                self.state.consecutive_new_highs = max(0, self.state.consecutive_new_highs - 1)
        sig_highs = self.state.consecutive_new_highs >= self.min_new_highs

        # --- Signal 2: Volume expansion ---
        sig_volume = False
        if has_volume and len(self._volumes) >= 10:
            avg_vol = sum(list(self._volumes)[-10:]) / 10
            recent_vol = sum(list(self._volumes)[-3:]) / 3
            self.state.volume_expansion_ratio = recent_vol / max(avg_vol, 1)
            sig_volume = self.state.volume_expansion_ratio >= self.min_vol_expansion

        # --- Signal 3: ATR expansion ---
        sig_atr = False
        if len(self._atrs) >= 10:
            avg_atr = sum(list(self._atrs)[-10:]) / 10
            recent_atr = sum(list(self._atrs)[-3:]) / 3
            self.state.atr_expansion_ratio = recent_atr / max(avg_atr, 0.0001)
            sig_atr = self.state.atr_expansion_ratio >= self.min_atr_expansion

        # --- Parabolic detection ---
        # Need 2+ signals AND must be in meaningful profit
        signals_active = sum([sig_highs, sig_volume, sig_atr])
        in_profit = c > entry_price + (1.0 * r_value) if r_value > 0 else c > entry_price

        was_parabolic = self.state.is_parabolic
        self.state.is_parabolic = (signals_active >= 2 and in_profit)

        # --- Chandelier stop (wider trailing stop during parabolic) ---
        if self.state.is_parabolic:
            recent_atrs = list(self._atrs)[-5:]
            current_atr = sum(recent_atrs) / max(len(recent_atrs), 1)
            self.state.chandelier_stop = self._peak_high - (self.chandelier_mult * current_atr)

        # --- Minimum hold enforcement ---
        if self.state.is_parabolic and not was_parabolic:
            # Just entered parabolic — set extended hold
            self.state.hold_until_bar = self._bar_count + self.min_hold_bars_parabolic
        elif self._bar_count == 1:
            # First bar after trade opens — set normal hold
            self.state.hold_until_bar = self._bar_count + self.min_hold_bars_normal

        # --- Exhaustion detection ---
        self.state.exhaustion_signals = 0
        # Volume divergence: price at/near highs but volume declining
        if (has_volume
            and self.state.consecutive_new_highs >= 2
            and self._peak_vol > 0
            and v < self._peak_vol * self.exhaustion_vol_divergence):
            self.state.exhaustion_signals += 1
        # Shooting star pattern
        if _is_shooting_star(o, h, l, c):
            self.state.exhaustion_signals += 1

        return self.state

    def should_suppress_exit(self) -> bool:
        """Should pattern-based exits (BE, TW) be suppressed?

        Returns True during parabolic regime OR within minimum hold period.
        Hard stop is NEVER suppressed — only pattern exits.
        """
        if not self.enabled:
            return False
        if self.state.is_parabolic:
            return True
        if self._bar_count < self.state.hold_until_bar:
            return True
        return False

    def get_chandelier_stop(self) -> float:
        """Get the Chandelier trailing stop during parabolic regime.

        Returns the stop price, or 0.0 if not in parabolic mode.
        """
        if self.state.is_parabolic and self.state.chandelier_stop > 0:
            return self.state.chandelier_stop
        return 0.0

    def should_trim(self) -> bool:
        """Should we trim the position due to exhaustion signals?

        Returns True when 2+ exhaustion signals fire (volume divergence + shooting star).
        """
        return self.state.exhaustion_signals >= 2

    def reset(self):
        """Reset all state. Call when a trade closes."""
        self._highs.clear()
        self._volumes.clear()
        self._atrs.clear()
        self._bar_count = 0
        self._peak_vol = 0.0
        self._peak_high = 0.0
        self.state = ParabolicState()
