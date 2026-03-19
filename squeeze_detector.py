"""Strategy 2: Squeeze / Breakout Detector.

Detects volume-explosion breakouts through key levels (PM high, whole dollar, PDH).
Separate module from micro_pullback — same interface so simulator/bot can consume both.

All gated by WB_SQUEEZE_ENABLED=0 (OFF by default).
"""

from __future__ import annotations

import math
import os
from collections import deque
from typing import Deque, Optional

from micro_pullback import ArmedTrade, ema_next


class SqueezeDetector:
    """IDLE → PRIMED → ARMED → TRIGGERED state machine for squeeze/breakout entries."""

    def __init__(self):
        # --- Master gate ---
        self.enabled = os.getenv("WB_SQUEEZE_ENABLED", "0") == "1"

        # --- Detection thresholds ---
        self.vol_mult = float(os.getenv("WB_SQ_VOL_MULT", "3.0"))
        self.min_bar_vol = int(os.getenv("WB_SQ_MIN_BAR_VOL", "50000"))
        self.min_body_pct = float(os.getenv("WB_SQ_MIN_BODY_PCT", "1.5"))
        self.prime_bars = int(os.getenv("WB_SQ_PRIME_BARS", "3"))
        self.max_r = float(os.getenv("WB_SQ_MAX_R", "0.80"))
        self.level_priority = os.getenv("WB_SQ_LEVEL_PRIORITY", "pm_high,whole_dollar,pdh").split(",")
        self.pm_confidence = os.getenv("WB_SQ_PM_CONFIDENCE", "1") == "1"
        self.max_attempts = int(os.getenv("WB_SQ_MAX_ATTEMPTS", "3"))
        self.probe_size_mult = float(os.getenv("WB_SQ_PROBE_SIZE_MULT", "0.5"))

        # --- Parabolic mode ---
        self.para_enabled = os.getenv("WB_SQ_PARA_ENABLED", "1") == "1"
        self.para_stop_offset = float(os.getenv("WB_SQ_PARA_STOP_OFFSET", "0.10"))
        self.para_trail_r = float(os.getenv("WB_SQ_PARA_TRAIL_R", "1.0"))

        # --- State ---
        self.symbol: str = ""
        self.armed: Optional[ArmedTrade] = None
        self.ema: Optional[float] = None
        self._ema_len = 9

        self._state = "IDLE"  # IDLE, PRIMED, ARMED
        self._primed_bars_left = 0
        self._primed_bar: Optional[dict] = None  # the bar that caused PRIMED

        # --- Bar history ---
        self.bars_1m: Deque[dict] = deque(maxlen=50)

        # --- Premarket levels ---
        self.premarket_high: Optional[float] = None
        self.premarket_bull_flag_high: Optional[float] = None
        self.prior_day_high: Optional[float] = None  # set by caller if available

        # --- Per-stock session tracking ---
        self._attempts = 0
        self._has_winner = False  # True after first winning squeeze on this symbol
        self._in_trade = False  # set by caller when squeeze trade is active

        # --- Gap data (set by caller) ---
        self.gap_pct: Optional[float] = None

    # ------------------------------------------------------------------
    # Seed (warm up indicators — no signals)
    # ------------------------------------------------------------------
    def seed_bar_close(self, o: float, h: float, l: float, c: float, v: float):
        self.ema = ema_next(self.ema, c, self._ema_len)
        info = {"o": o, "h": h, "l": l, "c": c, "v": v, "green": c >= o}
        self.bars_1m.append(info)

    # ------------------------------------------------------------------
    # Primary detection on 1m bar closes
    # ------------------------------------------------------------------
    def on_bar_close_1m(self, bar, vwap: Optional[float] = None) -> Optional[str]:
        if not self.enabled:
            return None

        o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume

        # Update EMA
        self.ema = ema_next(self.ema, c, self._ema_len)

        info = {"o": o, "h": h, "l": l, "c": c, "v": v, "green": c >= o}
        self.bars_1m.append(info)

        # Don't detect while in a trade
        if self._in_trade:
            return None

        # If already ARMED, just wait for tick trigger
        if self._state == "ARMED":
            return None

        # --- PRIMED state: waiting for level break ---
        if self._state == "PRIMED":
            self._primed_bars_left -= 1

            # Check for reset conditions
            if vwap is not None and c < vwap:
                self._reset("vwap_lost")
                return f"SQ_RESET: vwap_lost (close={c:.4f} < vwap={vwap:.4f})"

            if self._primed_bars_left <= 0:
                self._reset("prime_expired")
                return f"SQ_RESET: prime_expired ({self.prime_bars} bars elapsed)"

            # Check for level break
            level_name, level_price = self._find_broken_level(h)
            if level_name is not None:
                return self._try_arm(level_name, level_price, info, vwap)

            return None

        # --- IDLE state: look for volume explosion ---
        if len(self.bars_1m) < 3:
            return None

        if vwap is None:
            return None

        # Volume check
        avg_vol = self._avg_prior_vol()
        if avg_vol <= 0:
            return None

        vol_ratio = v / avg_vol
        if vol_ratio < self.vol_mult:
            return None
        if v < self.min_bar_vol:
            return None

        # Price above VWAP
        if c < vwap:
            return None

        # Green bar with significant body
        if not info["green"]:
            return None
        body = abs(c - o)
        if o > 0 and (body / o) * 100 < self.min_body_pct:
            return None

        # Max attempts check
        if self._attempts >= self.max_attempts:
            return f"SQ_NO_ARM: max_attempts ({self._attempts}/{self.max_attempts})"

        # --- Transition to PRIMED ---
        self._state = "PRIMED"
        self._primed_bars_left = self.prime_bars
        self._primed_bar = dict(info)

        prime_msg = (
            f"SQ_PRIMED: vol={vol_ratio:.1f}x avg, bar_vol={v:,.0f}, "
            f"price=${c:.4f} above VWAP (${vwap:.4f})"
        )

        # Check if level already broken on this bar
        level_name, level_price = self._find_broken_level(h)
        if level_name is not None:
            arm_msg = self._try_arm(level_name, level_price, info, vwap)
            if arm_msg:
                return f"{prime_msg}\n  {arm_msg}"
            return prime_msg

        return prime_msg

    # ------------------------------------------------------------------
    # Tick trigger check
    # ------------------------------------------------------------------
    def on_trade_price(self, price: float, is_premarket: bool = False) -> Optional[str]:
        if not self.enabled or self.armed is None:
            return None

        if price >= self.armed.trigger_high:
            msg = (
                f"ENTRY SIGNAL @ {self.armed.entry_price:.4f} "
                f"(break {self.armed.trigger_high:.4f}) "
                f"stop={self.armed.stop_low:.4f} R={self.armed.r:.4f} "
                f"score={self.armed.score:.1f} "
                f"setup_type=squeeze why={self.armed.score_detail}"
            )
            self.armed = None
            self._state = "IDLE"
            self._attempts += 1
            return msg

        return None

    # ------------------------------------------------------------------
    # Premarket levels
    # ------------------------------------------------------------------
    def update_premarket_levels(self, pm_high: Optional[float], pm_bf_high: Optional[float] = None):
        self.premarket_high = pm_high
        self.premarket_bull_flag_high = pm_bf_high

    # ------------------------------------------------------------------
    # Trade lifecycle callbacks
    # ------------------------------------------------------------------
    def notify_trade_closed(self, symbol: str, pnl: float):
        if pnl > 0:
            self._has_winner = True
        self._in_trade = False

    def notify_trade_opened(self):
        self._in_trade = True

    # ------------------------------------------------------------------
    # Reset for new day/stock
    # ------------------------------------------------------------------
    def reset(self):
        self._state = "IDLE"
        self._primed_bars_left = 0
        self._primed_bar = None
        self.armed = None
        self._attempts = 0
        self._has_winner = False
        self._in_trade = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _reset(self, reason: str = ""):
        self._state = "IDLE"
        self._primed_bars_left = 0
        self._primed_bar = None
        self.armed = None

    def _avg_prior_vol(self) -> float:
        """Average volume of all 1m bars except the most recent."""
        if len(self.bars_1m) < 2:
            return 0.0
        bars = list(self.bars_1m)[:-1]
        total = sum(b["v"] for b in bars)
        return total / len(bars) if bars else 0.0

    def _find_broken_level(self, bar_high: float) -> tuple[Optional[str], Optional[float]]:
        """Check if bar_high has broken any key level, in priority order."""
        for level_type in self.level_priority:
            level_type = level_type.strip()
            price = self._get_level_price(level_type, bar_high)
            if price is not None and bar_high > price:
                return level_type, price
        return None, None

    def _get_level_price(self, level_type: str, reference_price: float) -> Optional[float]:
        if level_type == "pm_high":
            return self.premarket_high
        elif level_type == "whole_dollar":
            # Nearest whole dollar above the open of the last bar
            if len(self.bars_1m) < 1:
                return None
            last_open = self.bars_1m[-1]["o"]
            return float(math.ceil(last_open))
        elif level_type == "pdh":
            return self.prior_day_high
        return None

    def _stop_from_consolidation(self) -> float:
        """Stop = lowest low of last 3 bars before the current bar."""
        # Use bars before the most recent one (the breakout bar)
        bars = list(self.bars_1m)
        if len(bars) < 2:
            return bars[-1]["l"] if bars else 0.0
        lookback = bars[max(0, len(bars) - 4):len(bars) - 1]  # 3 bars before current
        if not lookback:
            return bars[-1]["l"]
        return min(b["l"] for b in lookback)

    def _try_arm(self, level_name: str, level_price: float, bar: dict,
                 vwap: Optional[float]) -> Optional[str]:
        """Attempt to ARM on a level break. Returns message or None."""
        entry_price = level_price + 0.02  # small buffer above breakout level
        stop_low = self._stop_from_consolidation()
        r = entry_price - stop_low

        if r <= 0:
            self._reset("invalid_r")
            return f"SQ_NO_ARM: invalid_r (entry={entry_price:.4f} stop={stop_low:.4f})"

        # R cap: max absolute R or 5% of price
        max_r_pct = entry_price * 0.05
        effective_max_r = min(self.max_r, max_r_pct)
        if r > effective_max_r:
            if not self.para_enabled:
                self._reset("max_r_exceeded")
                return (
                    f"SQ_NO_ARM: max_r_exceeded R={r:.4f} > max={effective_max_r:.4f} "
                    f"(entry={entry_price:.4f} stop={stop_low:.4f})"
                )

            # --- Parabolic mode: level-based stop ---
            para_stop = level_price - self.para_stop_offset
            breakout_bar_low = bar["l"]
            para_stop = max(para_stop, breakout_bar_low)  # use tighter of the two
            para_r = entry_price - para_stop

            if para_r <= 0:
                self._reset("para_invalid_r")
                return f"SQ_NO_ARM: para_invalid_r (entry={entry_price:.4f} stop={para_stop:.4f})"

            # Even parabolic mode has a sanity cap
            if para_r > self.max_r:
                self._reset("para_max_r_exceeded")
                return (
                    f"SQ_NO_ARM: para_max_r_exceeded R={para_r:.4f} > max={self.max_r:.4f} "
                    f"(entry={entry_price:.4f} stop={para_stop:.4f})"
                )

            # Score with parabolic tag
            score, detail = self._score_setup(bar, vwap, level_name)
            detail += ";[PARABOLIC]"

            # Parabolic ALWAYS uses probe sizing
            size_mult = self.probe_size_mult

            self.armed = ArmedTrade(
                trigger_high=entry_price,
                stop_low=para_stop,
                entry_price=entry_price,
                r=para_r,
                score=score,
                score_detail=detail,
                setup_type="squeeze",
                size_mult=size_mult,
            )
            self._state = "ARMED"

            return (
                f"ARMED entry={entry_price:.4f} stop={para_stop:.4f} R={para_r:.4f} "
                f"score={score:.1f} level={level_name} setup_type=squeeze "
                f"[PARABOLIC] [PROBE={size_mult:.0%}] why={detail}"
            )

        # Score
        score, detail = self._score_setup(bar, vwap, level_name)

        # Probe sizing: half size on first attempt unless we already have a winner
        size_mult = 1.0 if self._has_winner else self.probe_size_mult

        self.armed = ArmedTrade(
            trigger_high=entry_price,
            stop_low=stop_low,
            entry_price=entry_price,
            r=r,
            score=score,
            score_detail=detail,
            setup_type="squeeze",
            size_mult=size_mult,
        )
        self._state = "ARMED"

        size_tag = f" [PROBE={size_mult:.0%}]" if size_mult < 1.0 else ""
        return (
            f"ARMED entry={entry_price:.4f} stop={stop_low:.4f} R={r:.4f} "
            f"score={score:.1f} level={level_name} setup_type=squeeze{size_tag} "
            f"why={detail}"
        )

    def _score_setup(self, bar: dict, vwap: Optional[float],
                     level_name: str) -> tuple[float, str]:
        """Simple V1 scoring for squeeze setups."""
        score = 5.0
        parts = ["base=5.0"]

        # Volume multiple above threshold
        avg_vol = self._avg_prior_vol()
        if avg_vol > 0:
            vol_ratio = bar["v"] / avg_vol
            extra_mults = vol_ratio - self.vol_mult
            if extra_mults > 0:
                bonus = min(extra_mults, 5.0)  # cap at +5
                score += bonus
                parts.append(f"vol_extra=+{bonus:.1f}")

        # PM bull flag detected
        if self.pm_confidence and self.premarket_bull_flag_high is not None:
            score += 2.0
            parts.append("pm_bull_flag=+2.0")

        # Gap strength
        if self.gap_pct is not None and self.gap_pct >= 20:
            score += 1.0
            parts.append("gap_20pct=+1.0")

        # VWAP distance (healthy = 2-15% above)
        if vwap is not None and vwap > 0:
            vwap_dist_pct = (bar["c"] - vwap) / vwap * 100
            if 2.0 <= vwap_dist_pct <= 15.0:
                score += 1.0
                parts.append(f"vwap_dist=+1.0({vwap_dist_pct:.0f}%)")

        # Price above PM high (strongest level)
        if level_name == "pm_high":
            score += 1.0
            parts.append("pm_high_break=+1.0")

        score = min(score, 15.0)
        return score, "squeeze: " + ";".join(parts)
