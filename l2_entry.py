"""
l2_entry.py — L2-driven entry strategy (Ross Cameron "early entry")

Enters when the order book shows strong buying pressure building BEFORE
the breakout candle prints. This is a fundamentally different strategy
from micro pullback:

  Micro pullback:  breakout → pullback → confirmation → ARM
  L2 entry:        L2 shows buyers stacking → ARM → enter the breakout

This module is COMPLETELY SEPARATE from micro_pullback.py.
It can be backtested independently with: python simulate.py SYMBOL DATE --l2-entry

Key signals that trigger an L2 entry:
  1. Order book imbalance bullish (> 0.60) for 2+ consecutive bars
  2. Bid stacking near current price (buyers lining up)
  3. Ask side thinning (resistance fading)
  4. No large ask wall blocking
  5. Basic conditions: above VWAP, above EMA, green bar, spread reasonable

Stop placement: below the bid stacking level or recent swing low.
"""

from __future__ import annotations

import os
import math
from collections import deque
from dataclasses import dataclass
from typing import Optional

from macd import MACDState


def _ema_next(prev_ema: Optional[float], price: float, length: int) -> float:
    alpha = 2.0 / (length + 1.0)
    if prev_ema is None:
        return price
    return (price * alpha) + (prev_ema * (1.0 - alpha))


@dataclass
class L2ArmedTrade:
    trigger_high: float
    stop_low: float
    entry_price: float
    r: float
    score: float = 0.0
    score_detail: str = ""
    setup_type: str = "l2_entry"


class L2EntryDetector:
    """
    Detects entry setups driven by Level 2 order book signals.

    Unlike MicroPullbackDetector which waits for a price-based
    impulse → pullback → confirmation cycle, this detector fires
    when L2 shows buyers accumulating before the move happens.
    """

    MIN_R = 0.03
    STOP_PAD = 0.01

    def __init__(self):
        # How many consecutive bars L2 must be bullish before arming
        self.min_bullish_bars = int(os.getenv("WB_L2E_MIN_BULLISH_BARS", "2"))

        # Minimum L2 signals required per bar to count as "bullish"
        self.min_bullish_signals = int(os.getenv("WB_L2E_MIN_SIGNALS", "2"))

        # Imbalance threshold (slightly lower than the scoring threshold
        # since we're using it as a convergence signal, not a standalone)
        self.imbalance_threshold = float(os.getenv("WB_L2E_IMBALANCE_MIN", "0.58"))

        # Maximum spread % to allow entry (thin books = slippage risk)
        self.max_spread_pct = float(os.getenv("WB_L2E_MAX_SPREAD", "3.0"))

        # Exhaustion limits (same concept as micro pullback)
        self.max_vwap_pct = float(os.getenv("WB_L2E_MAX_VWAP_PCT", "15"))
        self.max_move_pct = float(os.getenv("WB_L2E_MAX_MOVE_PCT", "60"))

        # Minimum score to arm
        self.min_score = float(os.getenv("WB_L2E_MIN_SCORE", "4.0"))

        # Internal state
        self.ema: Optional[float] = None
        self.ema_len = 9
        self.macd_state = MACDState()
        self.consecutive_bullish = 0
        self.armed: Optional[L2ArmedTrade] = None
        self.bars: deque[dict] = deque(maxlen=50)
        self._cooldown_bars = 0  # bars to wait after a trade fires

    def seed_bar_close(self, o: float, h: float, l: float, c: float, v: float):
        """Seed EMA/MACD from historical bars (no arming)."""
        self.ema = _ema_next(self.ema, c, self.ema_len)
        self.macd_state.update(c)
        self.bars.append({"o": o, "h": h, "l": l, "c": c, "v": v, "green": c >= o})

    def on_bar_close(
        self,
        bar,
        vwap: Optional[float],
        l2_state: Optional[dict],
    ) -> Optional[str]:
        """
        Evaluate at each 1-minute bar close.
        Returns a message string (for logging) or None.
        """
        o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume

        # Update indicators
        self.ema = _ema_next(self.ema, c, self.ema_len)
        self.macd_state.update(c)
        info = {"o": o, "h": h, "l": l, "c": c, "v": v, "green": c >= o}
        self.bars.append(info)

        # Cooldown after a trade
        if self._cooldown_bars > 0:
            self._cooldown_bars -= 1
            return None

        # Already armed — wait for tick trigger
        if self.armed:
            return None

        # No L2 data — can't do anything
        if l2_state is None:
            self.consecutive_bullish = 0
            return None

        # --- Count bullish L2 signals this bar ---
        bullish_count = 0
        signal_parts = []

        if l2_state["imbalance"] > self.imbalance_threshold:
            bullish_count += 1
            signal_parts.append(f"imb={l2_state['imbalance']:.2f}")

        if l2_state["bid_stacking"]:
            bullish_count += 1
            signal_parts.append("bid_stack")

        if l2_state["ask_thinning"]:
            bullish_count += 1
            signal_parts.append("thin_ask")

        if l2_state.get("large_bid"):
            bullish_count += 1
            signal_parts.append("large_bid")

        # Bearish signals cancel out
        bearish = False
        if l2_state["imbalance"] < 0.40:
            bearish = True
        if l2_state.get("large_ask"):
            bearish = True

        if bearish:
            self.consecutive_bullish = 0
            return f"L2E_BEARISH (imb={l2_state['imbalance']:.2f})"

        # Need minimum number of bullish signals
        if bullish_count >= self.min_bullish_signals:
            self.consecutive_bullish += 1
        else:
            self.consecutive_bullish = 0
            return None

        # Need sustained bullish L2 across multiple bars
        if self.consecutive_bullish < self.min_bullish_bars:
            return (
                f"L2E_BUILDING {self.consecutive_bullish}/{self.min_bullish_bars} "
                f"[{', '.join(signal_parts)}]"
            )

        # --- L2 is bullish. Check basic conditions. ---

        # Need VWAP
        if vwap is None or self.ema is None:
            return "L2E_WAIT (no VWAP/EMA)"

        # Must be above VWAP
        if c < vwap:
            self.consecutive_bullish = 0
            return "L2E_RESET (below VWAP)"

        # Must be above EMA
        if c < self.ema:
            self.consecutive_bullish = 0
            return "L2E_RESET (below EMA)"

        # Must be a green bar (momentum)
        if not info["green"]:
            return "L2E_WAIT (red bar)"

        # MACD must not be bearish
        if self.macd_state.bearish_cross():
            self.consecutive_bullish = 0
            return "L2E_RESET (MACD bearish)"

        # Spread check — don't enter thin/illiquid books
        if l2_state["spread_pct"] > self.max_spread_pct:
            return f"L2E_BLOCKED spread={l2_state['spread_pct']:.1f}% (max {self.max_spread_pct}%)"

        # Exhaustion: % above VWAP
        if vwap > 0:
            pct_above_vwap = (c - vwap) / vwap * 100
            if pct_above_vwap > self.max_vwap_pct:
                return f"L2E_BLOCKED exhaustion: {pct_above_vwap:.1f}% above VWAP (max {self.max_vwap_pct}%)"

        # Exhaustion: % from session low
        if len(self.bars) >= 5:
            session_low = min(b["l"] for b in self.bars)
            if session_low > 0:
                pct_from_low = (c - session_low) / session_low * 100
                if pct_from_low > self.max_move_pct:
                    return f"L2E_BLOCKED exhaustion: {pct_from_low:.1f}% from low (max {self.max_move_pct}%)"

        # --- Score the setup ---
        score, detail = self._score_l2_entry(l2_state, c, vwap)

        if score < self.min_score:
            return (
                f"L2E_NO_ARM score={score:.1f}<{self.min_score:.1f} "
                f"[{', '.join(signal_parts)}] why={detail}"
            )

        # --- ARM ---
        entry = h  # break of this bar's high
        # Stop: use the bid stacking level if available, else recent swing low
        stop = self._find_stop(l2_state, info)
        r = entry - stop

        if r <= 0 or r < self.MIN_R:
            return f"L2E_BLOCKED R={r:.4f} too small"

        self.armed = L2ArmedTrade(
            trigger_high=entry,
            stop_low=stop,
            entry_price=entry,
            r=r,
            score=score,
            score_detail=detail,
        )

        return (
            f"L2E_ARMED entry={entry:.4f} stop={stop:.4f} R={r:.4f} "
            f"score={score:.1f} [{', '.join(signal_parts)}] "
            f"consec_bull={self.consecutive_bullish} why={detail}"
        )

    def on_trade_price(self, price: float) -> Optional[str]:
        """Check if armed trade triggers on a price tick."""
        if self.armed and price >= self.armed.trigger_high:
            msg = (
                f"L2E_ENTRY @ {self.armed.entry_price:.4f} "
                f"(break {self.armed.trigger_high:.4f}) "
                f"stop={self.armed.stop_low:.4f} R={self.armed.r:.4f} "
                f"score={self.armed.score:.1f} why={self.armed.score_detail}"
            )
            self._reset_after_trade()
            return msg
        return None

    def _score_l2_entry(self, l2_state: dict, price: float, vwap: float) -> tuple[float, str]:
        """Score the L2 entry setup."""
        score = 0.0
        parts = []

        # L2 imbalance (the core signal)
        imb = l2_state["imbalance"]
        if imb > 0.75:
            score += 3.0
            parts.append(f"imb_strong=+3({imb:.2f})")
        elif imb > 0.65:
            score += 2.0
            parts.append(f"imb=+2({imb:.2f})")
        elif imb > self.imbalance_threshold:
            score += 1.0
            parts.append(f"imb_mild=+1({imb:.2f})")

        # Bid stacking
        if l2_state["bid_stacking"]:
            score += 2.0
            parts.append("bid_stack=+2")

        # Ask thinning (resistance fading)
        if l2_state["ask_thinning"]:
            score += 1.5
            parts.append("thin_ask=+1.5")

        # Large bid (institutional interest)
        if l2_state.get("large_bid"):
            score += 1.5
            parts.append("large_bid=+1.5")

        # Rising imbalance trend (momentum building)
        if l2_state.get("imbalance_trend") == "rising":
            score += 1.0
            parts.append("imb_rising=+1")

        # MACD confirmation
        macd_score = self.macd_state.strength_score(price)
        if macd_score > 3:
            score += 1.0
            parts.append(f"macd=+1({macd_score:.1f})")

        # Penalties
        if l2_state["spread_pct"] > 1.0:
            penalty = min(2.0, l2_state["spread_pct"] / 2)
            score -= penalty
            parts.append(f"spread=-{penalty:.1f}({l2_state['spread_pct']:.1f}%)")

        # Consecutive bullish bars bonus (sustained pressure)
        if self.consecutive_bullish >= 4:
            score += 1.0
            parts.append(f"sustained=+1({self.consecutive_bullish}bars)")

        detail = ";".join(parts)
        return score, detail

    def _find_stop(self, l2_state: dict, current_bar: dict) -> float:
        """
        Find stop level: prefer bid stacking level, else swing low.
        """
        # If we have bid stacking levels, use the highest one as support
        stack_levels = l2_state.get("bid_stack_levels", [])
        if stack_levels:
            # Use the highest stacking level as the stop reference
            highest_stack = max(p for p, _ in stack_levels)
            stop = highest_stack - self.STOP_PAD
            # But don't set stop above bar low (that would be absurd)
            stop = min(stop, current_bar["l"] - self.STOP_PAD)
            return stop

        # Fallback: recent swing low (lowest low of last 3 bars)
        if len(self.bars) >= 3:
            recent_low = min(b["l"] for b in list(self.bars)[-3:])
            return recent_low - self.STOP_PAD

        return current_bar["l"] - self.STOP_PAD

    def _reset_after_trade(self):
        """Reset state after a trade fires."""
        self.armed = None
        self.consecutive_bullish = 0
        self._cooldown_bars = 3  # wait 3 bars before looking again

    def full_reset(self):
        """Hard reset all state."""
        self.armed = None
        self.consecutive_bullish = 0
        self._cooldown_bars = 0
