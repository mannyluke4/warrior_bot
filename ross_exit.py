"""
Ross Cameron Exit Signal Manager  (WB_ROSS_EXIT_ENABLED=1)

Implements pure signal-based 1m exits modeled on Ross Cameron's actual methodology.
All logic is gated OFF by default; existing behavior is 100% unchanged when disabled.

Signal hierarchy (Ross's actual order — candle patterns FIRST, backstops LAST):

  TIER 1 — WARNING CANDLES (50% partial exit, fires once per trade):
       • Regular Doji     (body ≤15% range, wicks ≥20% each side)
       • Topping Tail     (green/flat, upper wick ≥50% range, wick ≥2× body)

  TIER 2 — CONFIRMED CANDLE REVERSALS (100% exit of remaining):
       • Gravestone Doji  (body ≤10% range, upper wick ≥70%, lower wick ≤15%)
       • Shooting Star    (red close + long upper wick — confirmed reversal)
       • Candle Under Candle (CUC) — current low < prior low in bullish context
         (requires ≥2 consecutive higher-highs before firing)

  TIER 3 — TECHNICAL BACKSTOPS (100% exit — last resort, only if no candle signal):
       • 1m close below VWAP
       • 1m close below 20 EMA
       • MACD(12,26,9) histogram goes negative on 1m
       NOTE: Above 5R, backstops fire as partial_50 to protect runners.

Structural trailing stop:
  • stop = low of last completed green 1m candle, never below entry + $0.01

Key gates (all default ON when WB_ROSS_EXIT_ENABLED=1):
  WB_ROSS_CUC_ENABLED=1
  WB_ROSS_DOJI_ENABLED=1
  WB_ROSS_GRAVESTONE_ENABLED=1
  WB_ROSS_SHOOTING_STAR_ENABLED=1
  WB_ROSS_TOPPING_TAIL_ENABLED=1
  WB_ROSS_MACD_ENABLED=1
  WB_ROSS_EMA20_ENABLED=1
  WB_ROSS_VWAP_ENABLED=1
  WB_ROSS_STRUCTURAL_TRAIL=1
  WB_ROSS_MIN_BARS=2     # minimum 1m bars in trade before any signal fires
  WB_ROSS_CUC_MIN_R=5.0  # suppress CUC when unrealized gain >= this R (deep runner gate)
  WB_ROSS_CUC_FLOOR_R=0.0  # CUC only fires when unrealized >= this R (0=disabled)
  WB_ROSS_CUC_MIN_TRADE_BARS=0  # CUC suppressed for first N 1m bars of trade (0=disabled)
  WB_ROSS_BACKSTOP_MIN_R=0.0  # backstops soften to 50% above this AND ≥5R
"""

import os
from typing import Optional, Tuple


class _EMATracker:
    """Incremental Exponential Moving Average — feed one close at a time."""

    def __init__(self, period: int):
        self.period = period
        self._k = 2.0 / (period + 1)
        self._ema: Optional[float] = None
        self._count = 0
        self._seed_sum = 0.0

    def update(self, value: float) -> Optional[float]:
        """Return current EMA after consuming value, or None if not yet seeded."""
        self._count += 1
        if self._count < self.period:
            self._seed_sum += value
            return None
        elif self._count == self.period:
            self._seed_sum += value
            self._ema = self._seed_sum / self.period
        else:
            self._ema = value * self._k + self._ema * (1 - self._k)
        return self._ema


class RossExitManager:
    """
    Tracks 1m bar state and emits exit signals per Ross Cameron's methodology.

    Instantiate once per symbol simulation run (or live session).
    Call reset() each time a new trade opens.
    Call on_1m_bar_close() on every completed 1m candle.

    Returns: (action, signal_name, new_structural_stop)
      action           : None | "partial_50" | "full_100"
      signal_name      : str  (for logging)
      new_structural_stop : float | None  (update trade stop to this value if not None)
    """

    def __init__(self):
        # MACD(12, 26, 9) incremental state
        self._ema12 = _EMATracker(12)
        self._ema26 = _EMATracker(26)
        self._ema9_macd = _EMATracker(9)   # tracks MACD-line values

        # 20 EMA for 1m bars
        self._ema20 = _EMATracker(20)

        # 1m bar history ring (for CUC: need prev bar)
        self._bars: list = []              # list of {"o","h","l","c"} dicts

        # Structural trail state (survives across trades — reflects cumulative 1m data)
        self._last_green_bar_low: Optional[float] = None

        # Per-trade state — reset via reset()
        self.partial_taken: bool = False   # True after a 50% doji partial has fired
        self._bars_since_entry: int = 0

        # Config knobs (read once at construction)
        self._min_bars = int(os.getenv("WB_ROSS_MIN_BARS", "2"))
        self._cuc_enabled = os.getenv("WB_ROSS_CUC_ENABLED", "1") == "1"
        self._doji_enabled = os.getenv("WB_ROSS_DOJI_ENABLED", "1") == "1"
        self._gravestone_enabled = os.getenv("WB_ROSS_GRAVESTONE_ENABLED", "1") == "1"
        self._shooting_star_enabled = os.getenv("WB_ROSS_SHOOTING_STAR_ENABLED", "1") == "1"
        self._macd_enabled = os.getenv("WB_ROSS_MACD_ENABLED", "1") == "1"
        self._ema20_enabled = os.getenv("WB_ROSS_EMA20_ENABLED", "1") == "1"
        self._vwap_enabled = os.getenv("WB_ROSS_VWAP_ENABLED", "1") == "1"
        self._structural_trail = os.getenv("WB_ROSS_STRUCTURAL_TRAIL", "1") == "1"
        self._topping_tail_enabled = os.getenv("WB_ROSS_TOPPING_TAIL_ENABLED", "1") == "1"
        self._cuc_min_r = float(os.getenv("WB_ROSS_CUC_MIN_R", "5.0"))
        self._cuc_floor_r = float(os.getenv("WB_ROSS_CUC_FLOOR_R", "0.0"))
        self._cuc_min_trade_bars = int(os.getenv("WB_ROSS_CUC_MIN_TRADE_BARS", "0"))
        self._backstop_min_r = float(os.getenv("WB_ROSS_BACKSTOP_MIN_R", "0.0"))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self):
        """Call when entering a new trade to clear per-trade counters."""
        self.partial_taken = False
        self._bars_since_entry = 0
        # _last_green_bar_low intentionally NOT reset — the structural trail carries
        # over from bars completed before entry (still valid price structure).

    def on_1m_bar_close(
        self,
        o: float,
        h: float,
        l: float,
        c: float,
        vwap: Optional[float],
        in_trade: bool,
        entry_price: float = 0.0,
        unrealized_r: float = 0.0,
    ) -> Tuple[Optional[str], Optional[str], Optional[float]]:
        """
        Process one completed 1m bar.

        Args:
            o/h/l/c      : bar OHLC values
            vwap         : current VWAP (None or 0 = not available)
            in_trade     : True if a position is currently open
            entry_price  : entry price of open trade (for BE floor on structural stop)
            unrealized_r : current unrealized gain in R-multiples (for CUC suppression)

        Returns:
            (action, signal_name, new_structural_stop)
              action              None | "partial_50" | "full_100"
              signal_name         human-readable label for logging
              new_structural_stop float to ratchet stop to, or None
        """
        # ── Always update indicators (even when flat, so they're warm when we enter) ──
        e12 = self._ema12.update(c)
        e26 = self._ema26.update(c)
        e20 = self._ema20.update(c)

        macd_histogram: Optional[float] = None
        if e12 is not None and e26 is not None:
            macd_line = e12 - e26
            sig_line = self._ema9_macd.update(macd_line)
            if sig_line is not None:
                macd_histogram = macd_line - sig_line

        # ── Track bar history ──────────────────────────────────────────────────────
        self._bars.append({"o": o, "h": h, "l": l, "c": c})
        if len(self._bars) > 60:
            self._bars = self._bars[-60:]

        # ── Structural trailing stop: update on green bars ─────────────────────────
        new_structural_stop: Optional[float] = None
        if self._structural_trail and c > o:          # green bar
            self._last_green_bar_low = l
            if in_trade and entry_price > 0:
                be_floor = entry_price + 0.01
                new_structural_stop = max(l, be_floor)

        # ── Skip signal evaluation when not in a trade ─────────────────────────────
        if not in_trade:
            return None, None, new_structural_stop

        self._bars_since_entry += 1

        # Don't fire exits on the very first bars — too close to entry
        if self._bars_since_entry < self._min_bars:
            return None, None, new_structural_stop

        # Need at least 2 bars for CUC comparison
        if len(self._bars) < 2:
            return None, None, new_structural_stop

        prev = self._bars[-2]
        curr = self._bars[-1]

        # Candle geometry
        rng = max(1e-9, curr["h"] - curr["l"])
        body = abs(curr["c"] - curr["o"])
        upper_wick = curr["h"] - max(curr["o"], curr["c"])
        lower_wick = min(curr["o"], curr["c"]) - curr["l"]
        is_red = curr["c"] < curr["o"]

        # ═══════════════════════════════════════════════════════════════════════════
        # TIER 1 — WARNING CANDLES (50% partial exit — only fires once per trade)
        # Ross's hierarchy: candle patterns are the PRIMARY exit trigger.
        # ═══════════════════════════════════════════════════════════════════════════

        # Regular Doji: tiny body, wicks on BOTH sides — after a big green run.
        # Ross's definition: "after a big green run" so the prior bar MUST be green.
        if self._doji_enabled and not self.partial_taken:
            prior_was_green = prev["c"] > prev["o"]
            if (prior_was_green
                    and body / rng <= 0.15
                    and upper_wick / rng >= 0.20
                    and lower_wick / rng >= 0.20):
                return "partial_50", "ross_doji_partial", new_structural_stop

        # Topping Tail: large upper wick after green run, NOT a red close.
        # (If it closes red, it's a shooting star — handled in Tier 2)
        if self._topping_tail_enabled and not self.partial_taken:
            if (not is_red                             # green or flat close
                    and upper_wick / rng >= 0.50       # wick ≥50% of bar range
                    and upper_wick >= 2.0 * max(body, 1e-9)):   # wick ≥2× body
                prior_was_green = prev["c"] > prev["o"]
                if prior_was_green:
                    return "partial_50", "ross_topping_tail_warning", new_structural_stop

        # ═══════════════════════════════════════════════════════════════════════════
        # TIER 2 — CONFIRMED CANDLE REVERSALS (100% exit of remaining)
        # ═══════════════════════════════════════════════════════════════════════════

        # Gravestone Doji: tiny body, all upper wick, minimal lower wick
        if self._gravestone_enabled:
            if (body / rng <= 0.10
                    and upper_wick / rng >= 0.70
                    and lower_wick / rng <= 0.15):
                return "full_100", "ross_gravestone_doji", new_structural_stop

        # Shooting Star: red candle, long upper wick >= 2× body, wick >= 50% range
        # This is a CONFIRMED reversal (red close = sellers won) → 100% exit
        if self._shooting_star_enabled and is_red:
            if (upper_wick >= 2.0 * max(body, 1e-9)
                    and upper_wick / rng >= 0.50):
                return "full_100", "ross_shooting_star", new_structural_stop

        # Candle Under Candle: current low breaks prior low in bullish context
        # Requires ≥2 consecutive higher-highs before (establishes uptrend to reverse from)
        if self._cuc_enabled and curr["l"] < prev["l"]:
            bullish_context = False
            if len(self._bars) >= 3:
                b_minus2 = self._bars[-3]
                b_minus1 = self._bars[-2]  # == prev
                # Two prior bars made consecutive higher highs
                if b_minus1["h"] > b_minus2["h"]:
                    if len(self._bars) >= 4:
                        b_minus3 = self._bars[-4]
                        bullish_context = b_minus2["h"] > b_minus3["h"]
                    else:
                        # Only 3 bars available — require the 2 we have to be green
                        bullish_context = (b_minus2["c"] > b_minus2["o"]
                                           and b_minus1["c"] > b_minus1["o"])

            if bullish_context:
                # Deep runner gate: suppress CUC when deep in profit (pullback, not reversal)
                if in_trade and unrealized_r >= self._cuc_min_r:
                    print(
                        f"  ROSS_CUC_SUPPRESSED: unrealized={unrealized_r:.1f}R >= threshold={self._cuc_min_r:.1f}R"
                        f" — letting other signals handle exit",
                        flush=True,
                    )
                # Floor gate: suppress CUC when not yet profitable enough
                elif self._cuc_floor_r > 0 and in_trade and unrealized_r < self._cuc_floor_r:
                    print(
                        f"  ROSS_CUC_FLOOR: unrealized={unrealized_r:.1f}R < floor={self._cuc_floor_r:.1f}R"
                        f" — suppressing CUC",
                        flush=True,
                    )
                # Min trade bars gate: suppress CUC in early bars of trade
                elif self._cuc_min_trade_bars > 0 and self._bars_since_entry < self._cuc_min_trade_bars:
                    print(
                        f"  ROSS_CUC_MIN_BARS: bars_in_trade={self._bars_since_entry}"
                        f" < min={self._cuc_min_trade_bars} — suppressing CUC",
                        flush=True,
                    )
                else:
                    return "full_100", "ross_cuc_exit", new_structural_stop

        # ═══════════════════════════════════════════════════════════════════════════
        # TIER 3 — TECHNICAL BACKSTOPS (last resort — only fire if no candle signal)
        # Ross uses these as the "you must not still be holding" fallback.
        # Above 5R, backstops soften to partial_50 to protect runners from MACD flicker.
        # ═══════════════════════════════════════════════════════════════════════════

        # VWAP break
        if self._vwap_enabled and vwap and vwap > 0 and c < vwap:
            if in_trade and unrealized_r >= 5.0 and not self.partial_taken:
                return "partial_50", "ross_vwap_break_warning", new_structural_stop
            return "full_100", "ross_vwap_break", new_structural_stop

        # 20 EMA break
        if self._ema20_enabled and e20 is not None and c < e20:
            if in_trade and unrealized_r >= 5.0 and not self.partial_taken:
                return "partial_50", "ross_ema20_break_warning", new_structural_stop
            return "full_100", "ross_ema20_break", new_structural_stop

        # MACD histogram negative
        if self._macd_enabled and macd_histogram is not None and macd_histogram < 0:
            if in_trade and unrealized_r >= 5.0 and not self.partial_taken:
                return "partial_50", "ross_macd_negative_warning", new_structural_stop
            return "full_100", "ross_macd_negative", new_structural_stop

        return None, None, new_structural_stop

    def get_structural_stop(self, entry_price: float) -> Optional[float]:
        """Return the current structural trailing stop level, or None."""
        if not self._structural_trail or self._last_green_bar_low is None:
            return None
        be_floor = entry_price + 0.01
        return max(self._last_green_bar_low, be_floor)
