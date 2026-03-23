"""
Ross Cameron Exit Signal Manager  (WB_ROSS_EXIT_ENABLED=1)

Implements pure signal-based 1m exits modeled on Ross Cameron's actual methodology.
All logic is gated OFF by default; existing behavior is 100% unchanged when disabled.

Signal hierarchy (fastest → most confirmed):
  1. Hard backstops — immediate 100% exit:
       • 1m close below VWAP
       • 1m close below 20 EMA
       • MACD(12,26,9) histogram goes negative on 1m
  2. Strong candle reversals — 100% exit:
       • Gravestone Doji  (body ≤10% range, upper wick ≥70%, lower wick ≤15%)
       • Shooting Star    (red, upper wick ≥ 2× body, upper wick ≥50% range)
       • Candle Under Candle (CUC) — current low < prior low in bullish context
  3. Warning candle — 50% partial exit:
       • Regular Doji     (body ≤15% range, wicks ≥20% each side)

Structural trailing stop:
  • stop = low of last completed green 1m candle, never below entry + $0.01

Key gates (all default ON when WB_ROSS_EXIT_ENABLED=1):
  WB_ROSS_CUC_ENABLED=1
  WB_ROSS_DOJI_ENABLED=1
  WB_ROSS_GRAVESTONE_ENABLED=1
  WB_ROSS_SHOOTING_STAR_ENABLED=1
  WB_ROSS_MACD_ENABLED=1
  WB_ROSS_EMA20_ENABLED=1
  WB_ROSS_VWAP_ENABLED=1
  WB_ROSS_STRUCTURAL_TRAIL=1
  WB_ROSS_MIN_BARS=2     # minimum 1m bars in trade before any signal fires
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
    ) -> Tuple[Optional[str], Optional[str], Optional[float]]:
        """
        Process one completed 1m bar.

        Args:
            o/h/l/c      : bar OHLC values
            vwap         : current VWAP (None or 0 = not available)
            in_trade     : True if a position is currently open
            entry_price  : entry price of open trade (for BE floor on structural stop)

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
        # TIER 1 — HARD BACKSTOPS (any one = 100% exit, no waiting for candle shape)
        # ═══════════════════════════════════════════════════════════════════════════

        # VWAP break
        if self._vwap_enabled and vwap and vwap > 0 and c < vwap:
            return "full_100", "ross_vwap_break", new_structural_stop

        # 20 EMA break
        if self._ema20_enabled and e20 is not None and c < e20:
            return "full_100", "ross_ema20_break", new_structural_stop

        # MACD histogram negative
        if self._macd_enabled and macd_histogram is not None and macd_histogram < 0:
            return "full_100", "ross_macd_negative", new_structural_stop

        # ═══════════════════════════════════════════════════════════════════════════
        # TIER 2 — STRONG CANDLE REVERSALS (100% exit)
        # ═══════════════════════════════════════════════════════════════════════════

        # Gravestone Doji: tiny body, all upper wick, minimal lower wick
        if self._gravestone_enabled:
            if (body / rng <= 0.10
                    and upper_wick / rng >= 0.70
                    and lower_wick / rng <= 0.15):
                return "full_100", "ross_gravestone_doji", new_structural_stop

        # Shooting Star: red candle, long upper wick >= 2× body, wick >= 50% range
        if self._shooting_star_enabled and is_red:
            if (upper_wick >= 2.0 * max(body, 1e-9)
                    and upper_wick / rng >= 0.50):
                return "full_100", "ross_shooting_star", new_structural_stop

        # Candle Under Candle: current low breaks prior low in bullish context
        if self._cuc_enabled and curr["l"] < prev["l"]:
            # Require prior bullish context so we don't exit on the very first red tick
            prior_green = prev["c"] > prev["o"]
            if not prior_green and len(self._bars) >= 3:
                prior_green = self._bars[-3]["c"] > self._bars[-3]["o"]
            if prior_green:
                return "full_100", "ross_cuc_exit", new_structural_stop

        # ═══════════════════════════════════════════════════════════════════════════
        # TIER 3 — WARNING (50% partial exit — only fires once per trade)
        # ═══════════════════════════════════════════════════════════════════════════

        # Regular Doji: tiny body, wicks on BOTH sides — after ≥2 large green candles.
        # Ross's definition: "after a big green run" so the prior bar MUST be green.
        # This prevents doji noise at entry-level consolidations.
        if self._doji_enabled and not self.partial_taken:
            prior_was_green = prev["c"] > prev["o"]
            if (prior_was_green
                    and body / rng <= 0.15
                    and upper_wick / rng >= 0.20
                    and lower_wick / rng >= 0.20):
                return "partial_50", "ross_doji_partial", new_structural_stop

        return None, None, new_structural_stop

    def get_structural_stop(self, entry_price: float) -> Optional[float]:
        """Return the current structural trailing stop level, or None."""
        if not self._structural_trail or self._last_green_bar_low is None:
            return None
        be_floor = entry_price + 0.01
        return max(self._last_green_bar_low, be_floor)
