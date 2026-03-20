"""Strategy 4: VWAP Reclaim Detector.

Detects Ross Cameron's "first 1-minute candle to make a new high after price
crosses back above VWAP" pattern.  Fundamentally different from micro-pullback
(trend continuation) and squeeze (volume explosion breakout).

State machine: IDLE → BELOW_VWAP → RECLAIMED → ARMED → TRIGGERED

All gated by WB_VR_ENABLED=0 (OFF by default).
"""

from __future__ import annotations

import os
from collections import deque
from typing import Deque, Optional

from micro_pullback import ArmedTrade, ema_next


class VwapReclaimDetector:
    """IDLE → BELOW_VWAP → RECLAIMED → ARMED → TRIGGERED state machine."""

    def __init__(self):
        # --- Master gate ---
        self.enabled = os.getenv("WB_VR_ENABLED", "0") == "1"

        # --- Detection thresholds ---
        self.vol_mult = float(os.getenv("WB_VR_VOL_MULT", "1.5"))
        self.min_body_pct = float(os.getenv("WB_VR_MIN_BODY_PCT", "0.5"))
        self.max_below_bars = int(os.getenv("WB_VR_MAX_BELOW_BARS", "10"))
        self.max_r = float(os.getenv("WB_VR_MAX_R", "0.50"))
        self.max_r_pct = float(os.getenv("WB_VR_MAX_R_PCT", "3.0"))
        self.macd_gate = os.getenv("WB_VR_MACD_GATE", "0") == "1"
        self.reclaim_window = int(os.getenv("WB_VR_RECLAIM_WINDOW", "3"))
        self.max_attempts = int(os.getenv("WB_VR_MAX_ATTEMPTS", "2"))
        self.severe_vwap_loss_pct = float(os.getenv("WB_VR_SEVERE_VWAP_LOSS_PCT", "20.0"))

        # --- Sizing ---
        self.probe_size_mult = float(os.getenv("WB_VR_PROBE_SIZE_MULT", "0.5"))
        self.full_after_win = os.getenv("WB_VR_FULL_AFTER_WIN", "1") == "1"

        # --- State ---
        self.symbol: str = ""
        self.armed: Optional[ArmedTrade] = None
        self.ema: Optional[float] = None
        self._ema_len = 9

        self._state = "IDLE"  # IDLE, BELOW_VWAP, RECLAIMED, ARMED
        self._below_vwap_bars = 0
        self._ever_above_vwap = False  # Must have been above VWAP before we track dips
        self._reclaim_bar: Optional[dict] = None  # The bar that crossed back above VWAP
        self._reclaim_bars_left = 0  # Countdown for new-high confirmation

        # --- Bar history ---
        self.bars_1m: Deque[dict] = deque(maxlen=50)

        # --- MACD (reuse same approach as MP detector) ---
        self._ema12: Optional[float] = None
        self._ema26: Optional[float] = None
        self._macd_signal: Optional[float] = None

        # --- Per-stock session tracking ---
        self._attempts = 0
        self._has_winner = False
        self._in_trade = False

        # --- Gap data (set by caller) ---
        self.gap_pct: Optional[float] = None

    # ------------------------------------------------------------------
    # Seed (warm up indicators — no signals)
    # ------------------------------------------------------------------
    def seed_bar_close(self, o: float, h: float, l: float, c: float, v: float):
        self.ema = ema_next(self.ema, c, self._ema_len)
        self._update_macd(c)
        info = {"o": o, "h": h, "l": l, "c": c, "v": v, "green": c >= o}
        self.bars_1m.append(info)

    # ------------------------------------------------------------------
    # Primary detection on 1m bar closes
    # ------------------------------------------------------------------
    def on_bar_close_1m(self, bar, vwap: Optional[float] = None) -> Optional[str]:
        if not self.enabled:
            return None

        o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume

        # Update indicators
        self.ema = ema_next(self.ema, c, self._ema_len)
        self._update_macd(c)

        info = {"o": o, "h": h, "l": l, "c": c, "v": v, "green": c >= o}
        self.bars_1m.append(info)

        # Don't detect while in a trade
        if self._in_trade:
            return None

        # Need VWAP to function
        if vwap is None or vwap <= 0:
            return None

        # Price range filter ($2-$20)
        if c < 2.0 or c > 20.0:
            return None

        # If already ARMED, just wait for tick trigger
        if self._state == "ARMED":
            return None

        # Track whether price has ever been above VWAP this session
        if c > vwap:
            self._ever_above_vwap = True

        # --- RECLAIMED state: waiting for new-high confirmation bar ---
        if self._state == "RECLAIMED":
            self._reclaim_bars_left -= 1

            # Reset if price drops back below VWAP
            if c < vwap:
                self._reset("vwap_lost_after_reclaim")
                return (
                    f"VR_RESET: vwap_lost_after_reclaim "
                    f"(close={c:.4f} < vwap={vwap:.4f})"
                )

            # Window expired without new-high confirmation
            if self._reclaim_bars_left <= 0:
                self._reset("reclaim_window_expired")
                return (
                    f"VR_RESET: reclaim_window_expired "
                    f"({self.reclaim_window} bars without new high)"
                )

            # Check for new-high confirmation: bar high > reclaim bar high
            if self._reclaim_bar is not None and h > self._reclaim_bar["h"]:
                # Body confirmation
                body = abs(c - o)
                if o > 0 and (body / o) * 100 < self.min_body_pct:
                    return (
                        f"VR_REJECT: weak_body "
                        f"({(body / o) * 100:.2f}% < {self.min_body_pct}%)"
                    )

                # Bar must be green
                if not info["green"]:
                    return "VR_REJECT: new_high_bar_not_green"

                return self._try_arm(info, vwap)

            return None

        # --- BELOW_VWAP state: waiting for reclaim ---
        if self._state == "BELOW_VWAP":
            if c < vwap:
                self._below_vwap_bars += 1

                # Give up if too many bars below
                if self._below_vwap_bars >= self.max_below_bars:
                    self._reset("too_long_below_vwap")
                    return (
                        f"VR_RESET: too_long_below_vwap "
                        f"({self._below_vwap_bars} bars)"
                    )

                # Give up if price drops severely below VWAP
                vwap_dist_pct = (vwap - c) / vwap * 100
                if vwap_dist_pct > self.severe_vwap_loss_pct:
                    self._reset("severe_vwap_loss")
                    return (
                        f"VR_RESET: severe_vwap_loss "
                        f"({vwap_dist_pct:.1f}% below VWAP)"
                    )

                return None

            # Price closed above VWAP — potential reclaim!
            # Volume confirmation: reclaim bar volume >= vol_mult * avg prior bars
            avg_vol = self._avg_prior_vol(5)
            if avg_vol > 0:
                vol_ratio = v / avg_vol
                if vol_ratio < self.vol_mult:
                    # Weak reclaim — stay in BELOW_VWAP, wait for stronger bar
                    return (
                        f"VR_WEAK_RECLAIM: vol_ratio={vol_ratio:.2f}x "
                        f"< {self.vol_mult}x (staying BELOW_VWAP)"
                    )

            # Bar must be green
            if not info["green"]:
                return "VR_WEAK_RECLAIM: not_green (staying BELOW_VWAP)"

            # MACD gate (optional)
            if self.macd_gate and not self._macd_bullish():
                return "VR_WEAK_RECLAIM: macd_bearish (staying BELOW_VWAP)"

            # Max attempts check
            if self._attempts >= self.max_attempts:
                return (
                    f"VR_NO_RECLAIM: max_attempts "
                    f"({self._attempts}/{self.max_attempts})"
                )

            # --- Transition to RECLAIMED ---
            self._state = "RECLAIMED"
            self._reclaim_bar = dict(info)
            self._reclaim_bars_left = self.reclaim_window

            vol_ratio = v / avg_vol if avg_vol > 0 else 0
            return (
                f"VR_RECLAIMED: close={c:.4f} above VWAP={vwap:.4f}, "
                f"vol={vol_ratio:.1f}x avg, "
                f"waiting {self.reclaim_window} bars for new-high confirmation"
            )

        # --- IDLE state: watch for price dipping below VWAP ---
        if self._state == "IDLE":
            # Must have been above VWAP at some point first
            if not self._ever_above_vwap:
                return None

            # Need enough bar history
            if len(self.bars_1m) < 5:
                return None

            # Detect price closing below VWAP
            if c < vwap:
                self._state = "BELOW_VWAP"
                self._below_vwap_bars = 1
                return (
                    f"VR_BELOW_VWAP: close={c:.4f} < VWAP={vwap:.4f}, "
                    f"watching for reclaim"
                )

        return None

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
                f"setup_type=vwap_reclaim why={self.armed.score_detail}"
            )
            self.armed = None
            self._state = "IDLE"
            self._attempts += 1
            return msg

        return None

    # ------------------------------------------------------------------
    # Trade lifecycle callbacks
    # ------------------------------------------------------------------
    def notify_trade_opened(self):
        self._in_trade = True

    def notify_trade_closed(self, symbol: str, pnl: float):
        if pnl > 0:
            self._has_winner = True
        self._in_trade = False

    # ------------------------------------------------------------------
    # Reset for new day/stock
    # ------------------------------------------------------------------
    def reset(self):
        self._state = "IDLE"
        self._below_vwap_bars = 0
        self._ever_above_vwap = False
        self._reclaim_bar = None
        self._reclaim_bars_left = 0
        self.armed = None
        self._attempts = 0
        self._has_winner = False
        self._in_trade = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _reset(self, reason: str = ""):
        """Soft reset back to IDLE (keeps session counters)."""
        self._state = "IDLE"
        self._below_vwap_bars = 0
        self._reclaim_bar = None
        self._reclaim_bars_left = 0
        self.armed = None

    def _avg_prior_vol(self, lookback: int = 5) -> float:
        """Average volume of prior N bars (excluding the most recent)."""
        if len(self.bars_1m) < 2:
            return 0.0
        bars = list(self.bars_1m)[:-1]  # exclude current bar
        bars = bars[-lookback:]  # last N bars before current
        if not bars:
            return 0.0
        return sum(b["v"] for b in bars) / len(bars)

    def _try_arm(self, confirmation_bar: dict, vwap: Optional[float]) -> Optional[str]:
        """Attempt to ARM on new-high confirmation after reclaim."""
        if self._reclaim_bar is None:
            self._reset("no_reclaim_bar")
            return None

        # Entry = confirmation bar high + small buffer
        entry_price = confirmation_bar["h"] + 0.02

        # Stop = lower of reclaim bar low and confirmation bar low
        stop_low = min(self._reclaim_bar["l"], confirmation_bar["l"])

        r = entry_price - stop_low
        if r <= 0.03:  # MIN_R
            self._reset("invalid_r")
            return (
                f"VR_NO_ARM: invalid_r "
                f"(entry={entry_price:.4f} stop={stop_low:.4f} R={r:.4f})"
            )

        # R cap: absolute and percentage
        if r > self.max_r:
            self._reset("max_r_exceeded")
            return (
                f"VR_NO_ARM: max_r_exceeded "
                f"R={r:.4f} > max={self.max_r:.4f}"
            )
        if entry_price > 0 and (r / entry_price) * 100 > self.max_r_pct:
            self._reset("max_r_pct_exceeded")
            return (
                f"VR_NO_ARM: max_r_pct_exceeded "
                f"R%={((r / entry_price) * 100):.1f}% > {self.max_r_pct}%"
            )

        # Score the setup
        score, detail = self._score_setup(confirmation_bar, vwap)

        # Probe sizing: half size on first attempt unless we have a winner
        if self.full_after_win and self._has_winner:
            size_mult = 1.0
        else:
            size_mult = self.probe_size_mult

        self.armed = ArmedTrade(
            trigger_high=entry_price,
            stop_low=stop_low,
            entry_price=entry_price,
            r=r,
            score=score,
            score_detail=detail,
            setup_type="vwap_reclaim",
            size_mult=size_mult,
        )
        self._state = "ARMED"

        size_tag = f" [PROBE={size_mult:.0%}]" if size_mult < 1.0 else ""
        return (
            f"VR_ARMED: entry={entry_price:.4f} stop={stop_low:.4f} "
            f"R={r:.4f} score={score:.1f}{size_tag} "
            f"setup_type=vwap_reclaim why={detail}"
        )

    def _score_setup(self, bar: dict, vwap: Optional[float]) -> tuple[float, str]:
        """Score a VWAP reclaim setup for quality ranking."""
        score = 5.0
        parts = ["base=5.0"]

        # Volume strength on confirmation bar
        avg_vol = self._avg_prior_vol(5)
        if avg_vol > 0:
            vol_ratio = bar["v"] / avg_vol
            if vol_ratio >= 2.0:
                bonus = min(vol_ratio - 1.0, 3.0)
                score += bonus
                parts.append(f"vol_confirm=+{bonus:.1f}")

        # How quickly the reclaim happened (fewer bars below = stronger)
        if self._below_vwap_bars <= 3:
            score += 2.0
            parts.append("fast_reclaim=+2.0")
        elif self._below_vwap_bars <= 5:
            score += 1.0
            parts.append("mod_reclaim=+1.0")

        # MACD bullish
        if self._macd_bullish():
            score += 1.0
            parts.append("macd_bull=+1.0")

        # EMA alignment (price above EMA9)
        if self.ema is not None and bar["c"] > self.ema:
            score += 1.0
            parts.append("above_ema=+1.0")

        # Tight R (good risk/reward)
        r = bar["h"] + 0.02 - min(
            self._reclaim_bar["l"] if self._reclaim_bar else bar["l"],
            bar["l"],
        )
        if 0 < r <= 0.20:
            score += 1.0
            parts.append("tight_r=+1.0")

        # Gap strength
        if self.gap_pct is not None and self.gap_pct >= 20:
            score += 1.0
            parts.append("gap_20pct=+1.0")

        score = min(score, 15.0)
        return score, "vwap_reclaim: " + ";".join(parts)

    def _update_macd(self, close: float):
        """Update MACD indicators (12/26/9)."""
        self._ema12 = ema_next(self._ema12, close, 12)
        self._ema26 = ema_next(self._ema26, close, 26)
        if self._ema12 is not None and self._ema26 is not None:
            macd_line = self._ema12 - self._ema26
            self._macd_signal = ema_next(self._macd_signal, macd_line, 9)

    def _macd_bullish(self) -> bool:
        """Return True if MACD histogram is positive (bullish momentum)."""
        if self._ema12 is None or self._ema26 is None or self._macd_signal is None:
            return False
        macd_line = self._ema12 - self._ema26
        return macd_line > self._macd_signal
