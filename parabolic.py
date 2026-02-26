"""
ParabolicRegimeDetector — Multi-signal parabolic regime detection for exit logic.

Replaces the simple _in_parabolic_grace() heuristic with a richer detector that:
1. Detects parabolic regimes via 4 signals (new highs, volume expansion, ATR expansion, ROC acceleration)
2. Requires 3+ signals to classify as parabolic (reduces false positives)
3. Suppresses BE and TW exits during parabolic
4. Provides a wider Chandelier trailing stop for classic mode (disabled in signal mode)
5. Classifies flash spikes (<60s of new highs) separately — does NOT suppress exits
6. Detects exhaustion for proactive trim signals
7. Enforces minimum hold times after entry

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
    is_flash_spike: bool = False  # fast burst (<60s) — exits NOT suppressed
    consecutive_new_highs: int = 0
    volume_expansion_ratio: float = 1.0
    atr_expansion_ratio: float = 1.0
    roc_acceleration: float = 0.0  # bar-over-bar rate of change
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
        min_roc_acceleration: float = 1.2,  # ROC must be accelerating 1.2x
        chandelier_mult: float = 2.5,
        min_hold_bars_normal: int = 3,      # 3 x 10s = 30s
        min_hold_bars_parabolic: int = 6,   # 6 x 10s = 60s (reduced from 12)
        flash_spike_threshold: int = 6,     # <6 bars of new highs = flash spike (60s)
        exhaustion_vol_divergence: float = 0.5,
    ):
        self.enabled = enabled
        self.min_new_highs = min_new_highs
        self.min_vol_expansion = min_vol_expansion
        self.min_atr_expansion = min_atr_expansion
        self.min_roc_acceleration = min_roc_acceleration
        self.chandelier_mult = chandelier_mult
        self.min_hold_bars_normal = min_hold_bars_normal
        self.min_hold_bars_parabolic = min_hold_bars_parabolic
        self.flash_spike_threshold = flash_spike_threshold
        self.exhaustion_vol_divergence = exhaustion_vol_divergence

        # Internal tracking
        self._highs: deque = deque(maxlen=50)
        self._closes: deque = deque(maxlen=50)  # for ROC calculation
        self._volumes: deque = deque(maxlen=50)
        self._atrs: deque = deque(maxlen=50)  # bar range as ATR proxy
        self._bar_count: int = 0
        self._peak_vol: float = 0.0
        self._peak_high: float = 0.0
        self._first_new_high_bar: int = 0  # when the new-high streak started

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
        self._closes.append(c)
        atr_proxy = h - l
        self._atrs.append(atr_proxy)
        has_volume = v > 0
        if has_volume:
            self._volumes.append(v)
            self._peak_vol = max(self._peak_vol, v)
        self._peak_high = max(self._peak_high, h)

        # --- Signal 1: Consecutive new highs ---
        if len(self._highs) >= 2:
            lookback = list(self._highs)[-min(len(self._highs), self.min_new_highs + 1):-1]
            if lookback and h > max(lookback):
                if self.state.consecutive_new_highs == 0:
                    self._first_new_high_bar = self._bar_count  # mark streak start
                self.state.consecutive_new_highs += 1
            else:
                # Decay — allow 1 bar of pause without resetting
                self.state.consecutive_new_highs = max(0, self.state.consecutive_new_highs - 1)
                if self.state.consecutive_new_highs == 0:
                    self._first_new_high_bar = 0
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

        # --- Signal 4: ROC acceleration (rate of change increasing bar-over-bar) ---
        sig_roc = False
        if len(self._closes) >= 6:
            closes = list(self._closes)
            # ROC of last 3 bars vs ROC of prior 3 bars
            recent_roc = (closes[-1] - closes[-3]) / max(abs(closes[-3]), 0.0001)
            prior_roc = (closes[-3] - closes[-6]) / max(abs(closes[-6]), 0.0001) if len(closes) >= 6 else 0
            if prior_roc > 0:
                self.state.roc_acceleration = recent_roc / prior_roc
                sig_roc = self.state.roc_acceleration >= self.min_roc_acceleration
            else:
                self.state.roc_acceleration = recent_roc * 10 if recent_roc > 0 else 0
                sig_roc = recent_roc > 0.005  # modest upward ROC when prior was flat/negative

        # --- Flash spike detection ---
        is_flash_spike = False
        if sig_highs and self._first_new_high_bar > 0:
            bars_since_start = self._bar_count - self._first_new_high_bar
            is_flash_spike = bars_since_start < self.flash_spike_threshold

        # --- Parabolic detection ---
        # Need 3+ of 4 signals AND in profit AND NOT a flash spike
        signals_active = sum([sig_highs, sig_volume, sig_atr, sig_roc])
        in_profit = c > entry_price + (1.0 * r_value) if r_value > 0 else c > entry_price

        was_parabolic = self.state.is_parabolic
        self.state.is_parabolic = (signals_active >= 3 and in_profit and not is_flash_spike)
        self.state.is_flash_spike = is_flash_spike

        # --- Chandelier stop (wider trailing stop during parabolic, classic mode only) ---
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
        Flash spikes do NOT suppress exits.
        Hard stop is NEVER suppressed — only pattern exits.
        """
        if not self.enabled:
            return False
        if self.state.is_flash_spike:
            return False
        if self.state.is_parabolic:
            return True
        if self._bar_count < self.state.hold_until_bar:
            return True
        return False

    def get_chandelier_stop(self) -> float:
        """Get the Chandelier trailing stop during parabolic regime.

        Returns the stop price, or 0.0 if not in parabolic mode.
        NOTE: Caller should only use this in classic exit mode, NOT signal mode.
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
        self._closes.clear()
        self._volumes.clear()
        self._atrs.clear()
        self._bar_count = 0
        self._peak_vol = 0.0
        self._peak_high = 0.0
        self._first_new_high_bar = 0
        self.state = ParabolicState()
