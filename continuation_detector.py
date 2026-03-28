"""Post-squeeze continuation detector (CT).

Implements the CT state machine from DIRECTIVE_POST_SQUEEZE_CONTINUATION.md.
Only activates after a profitable squeeze trade closes on a given symbol.
Watches for Ross-style pullback -> consolidation -> breakout continuation.

State machine:
    IDLE -> SQ_CONFIRMED -> WATCHING -> CT_PRIMED -> CT_ARMED -> CT_TRIGGERED
"""
from __future__ import annotations

import os
from typing import Optional
from collections import deque

from macd import MACDState
from micro_pullback import ArmedTrade, ema_next


class ContinuationDetector:
    """Post-squeeze continuation entry detector."""

    def __init__(self):
        self.enabled = os.getenv("WB_CT_ENABLED", "0") == "1"

        # Timing
        self._cooldown_bars = int(os.getenv("WB_CT_COOLDOWN_BARS", "3"))
        self._max_reentries = int(os.getenv("WB_CT_MAX_REENTRIES", "2"))
        self._min_pullback_bars = int(os.getenv("WB_CT_MIN_PULLBACK_BARS", "1"))
        self._max_pullback_bars = int(os.getenv("WB_CT_MAX_PULLBACK_BARS", "5"))

        # Quality filters
        self._max_retrace_pct = float(os.getenv("WB_CT_MAX_RETRACE_PCT", "50"))
        self._min_vol_decay = float(os.getenv("WB_CT_MIN_VOL_DECAY", "1.50"))  # Pullback avg vol < 1.5x squeeze avg vol
        self._require_vwap = os.getenv("WB_CT_REQUIRE_VWAP", "1") == "1"
        self._require_ema = os.getenv("WB_CT_REQUIRE_EMA", "1") == "1"
        self._require_macd = os.getenv("WB_CT_REQUIRE_MACD", "1") == "1"
        self._min_r = float(os.getenv("WB_MIN_R", "0.06"))

        # Sizing
        self._probe_size = float(os.getenv("WB_CT_PROBE_SIZE", "0.5"))
        self._full_size = float(os.getenv("WB_CT_FULL_SIZE", "1.0"))

        # EMA length (matches squeeze/MP)
        self._ema_len = 9

        # --- Internal state ---
        self._state: str = "IDLE"
        self._cooldown_remaining: int = 0
        self._reentry_count: int = 0

        # Squeeze trade context
        self._squeeze_entry: Optional[float] = None
        self._squeeze_exit: Optional[float] = None
        self._squeeze_high: Optional[float] = None
        self._squeeze_vol: Optional[float] = None  # avg volume during squeeze bars

        # Pullback tracking
        self._pullback_bars: list = []
        self._pullback_low: Optional[float] = None
        self._pullback_high: Optional[float] = None

        # EMA + MACD (fed from bar closes)
        self.ema: Optional[float] = None
        self.macd_state: MACDState = MACDState()

        # Armed trade
        self.armed: Optional[ArmedTrade] = None
        self._last_msg: str = ""

    # ──────────────────────────────────────────────────────────────
    # Seeding (premarket / warmup bars)
    # ──────────────────────────────────────────────────────────────

    def seed_bar_close(self, o: float, h: float, l: float, c: float, v: float):
        """Seed EMA + MACD from historical bars. No state machine logic."""
        self.ema = ema_next(self.ema, c, self._ema_len)
        self.macd_state.update(c)

    # ──────────────────────────────────────────────────────────────
    # Squeeze lifecycle notifications
    # ──────────────────────────────────────────────────────────────

    def notify_squeeze_closed(self, symbol: str, pnl: float,
                              entry: float = 0, exit_price: float = 0,
                              hod: float = 0, avg_squeeze_vol: float = 0):
        """Called when a squeeze trade closes. Activates CT if profitable."""
        if not self.enabled:
            return
        if pnl <= 0:
            return  # Only activate on winning squeezes
        if self._reentry_count >= self._max_reentries:
            return  # Already used all re-entries this session

        self._state = "SQ_CONFIRMED"
        self._squeeze_entry = entry
        self._squeeze_exit = exit_price
        self._squeeze_high = hod
        self._squeeze_vol = avg_squeeze_vol
        self._cooldown_remaining = self._cooldown_bars
        self._pullback_bars = []
        self._pullback_low = None
        self._pullback_high = None
        self.armed = None

    def notify_continuation_closed(self, pnl: float):
        """Called when a continuation trade closes."""
        self._reentry_count += 1
        if self._reentry_count >= self._max_reentries:
            self._state = "IDLE"
            self.armed = None
            return

        # Go back to cooldown -> watching for next pullback
        self._state = "SQ_CONFIRMED"
        self._cooldown_remaining = 2 if pnl > 0 else self._cooldown_bars
        self._pullback_bars = []
        self._pullback_low = None
        self._pullback_high = None
        self.armed = None

    # ──────────────────────────────────────────────────────────────
    # 1-minute bar processing
    # ──────────────────────────────────────────────────────────────

    def on_bar_close_1m(self, bar, vwap: Optional[float] = None) -> Optional[str]:
        """Process each 1-minute bar close. Returns status message or None."""
        if not self.enabled:
            return None

        # Always update EMA + MACD
        c = bar.close
        self.ema = ema_next(self.ema, c, self._ema_len)
        self.macd_state.update(c)

        if self._state == "IDLE":
            return None

        if self._reentry_count >= self._max_reentries:
            self._state = "IDLE"
            self.armed = None
            return "CT_MAX_REENTRIES — done for this symbol"

        # --- SQ_CONFIRMED: cooldown ---
        if self._state == "SQ_CONFIRMED":
            self._cooldown_remaining -= 1
            if self._cooldown_remaining <= 0:
                self._state = "WATCHING"
                return "CT_WATCHING — cooldown expired, hunting pullbacks"
            return f"CT_COOLDOWN ({self._cooldown_remaining} bars remaining)"

        # --- WATCHING: look for pullback formation ---
        if self._state == "WATCHING":
            is_red = bar.close < bar.open
            is_lower_close = (
                len(self._pullback_bars) > 0
                and bar.close <= self._pullback_bars[-1]["c"]
            )
            is_pullback_bar = is_red or (is_lower_close and len(self._pullback_bars) > 0)

            if is_pullback_bar:
                self._pullback_bars.append({
                    "o": bar.open, "h": bar.high, "l": bar.low,
                    "c": bar.close, "v": bar.volume,
                })
                self._pullback_low = min(b["l"] for b in self._pullback_bars)
                self._pullback_high = max(b["h"] for b in self._pullback_bars)

                # Check: pullback too deep?
                if self._squeeze_high and self._squeeze_entry:
                    squeeze_range = self._squeeze_high - self._squeeze_entry
                    if squeeze_range > 0:
                        retrace = self._squeeze_high - self._pullback_low
                        retrace_pct = (retrace / squeeze_range) * 100
                        if retrace_pct > self._max_retrace_pct:
                            return self._reset(
                                f"CT_RESET: pullback too deep ({retrace_pct:.0f}% retrace)"
                            )

                # Check: pullback too long?
                if len(self._pullback_bars) > self._max_pullback_bars:
                    return self._reset(
                        f"CT_RESET: pullback too long ({len(self._pullback_bars)} bars)"
                    )

                return (
                    f"CT_PULLBACK: {len(self._pullback_bars)} bars, "
                    f"low=${self._pullback_low:.2f}"
                )

            # Green bar after sufficient pullback -> check for PRIMED
            if len(self._pullback_bars) >= self._min_pullback_bars and bar.close > bar.open:
                self._state = "CT_PRIMED"
                # Fall through to CT_PRIMED check below
            else:
                # No pullback yet, or green bar without enough pullback bars
                return None

        # --- CT_PRIMED: validate pullback quality ---
        if self._state == "CT_PRIMED":
            # Gate 1: Volume decay
            if self._squeeze_vol and self._squeeze_vol > 0 and self._pullback_bars:
                pb_avg_vol = sum(b["v"] for b in self._pullback_bars) / len(self._pullback_bars)
                vol_ratio = pb_avg_vol / self._squeeze_vol
                if vol_ratio > self._min_vol_decay:
                    return self._reset(
                        f"CT_REJECT: pullback volume too high "
                        f"({vol_ratio:.1f}x squeeze avg)"
                    )

            # Gate 2: Price above VWAP
            if self._require_vwap and vwap and bar.close < vwap:
                return self._reset("CT_REJECT: price below VWAP on confirmation")

            # Gate 3: Price above 9 EMA
            if self._require_ema and self.ema and bar.close < self.ema:
                return self._reset("CT_REJECT: price below 9 EMA on confirmation")

            # Gate 4: MACD positive (Ross's #1 dip-vs-dump filter)
            if self._require_macd and not self.macd_state.bullish():
                return self._reset("CT_REJECT: MACD negative — likely dump, not dip")

            # All gates passed — ARM the trade
            if self._pullback_high is None or self._pullback_low is None:
                return self._reset("CT_REJECT: no pullback range defined")

            entry = self._pullback_high + 0.01  # Break of consolidation ceiling
            stop = self._pullback_low - 0.01    # Below pullback low
            r = entry - stop

            if r <= 0 or r < self._min_r:
                return self._reset(f"CT_REJECT: R too small ({r:.4f})")

            # Sizing: probe on first re-entry, full on second
            size_mult = self._probe_size if self._reentry_count == 0 else self._full_size

            self._state = "CT_ARMED"
            self.armed = ArmedTrade(
                trigger_high=entry,
                stop_low=stop,
                entry_price=entry,
                r=r,
                score=5.0,  # Base score for continuation
                score_detail=f"continuation: reentry#{self._reentry_count + 1}",
                setup_type="continuation",
                size_mult=size_mult,
            )
            return f"CT_ARMED: entry=${entry:.2f} stop=${stop:.2f} R=${r:.4f}"

        # --- CT_ARMED: waiting for price trigger (handled in on_trade_price) ---
        if self._state == "CT_ARMED":
            return None

        return None

    # ──────────────────────────────────────────────────────────────
    # Tick-level trigger check
    # ──────────────────────────────────────────────────────────────

    def on_trade_price(self, price: float, is_premarket: bool = False) -> Optional[str]:
        """Check if armed trade triggers on this price."""
        if self._state != "CT_ARMED" or not self.armed:
            return None

        if price >= self.armed.trigger_high:
            self._state = "IDLE"  # Reset after trigger (will re-enter via notify)
            return f"CT ENTRY SIGNAL @ ${price:.2f}"

        return None

    # ──────────────────────────────────────────────────────────────
    # Reset + daily reset
    # ──────────────────────────────────────────────────────────────

    def _reset(self, msg: str) -> str:
        """Reset to WATCHING state (keep watching for next pullback)."""
        self._state = "WATCHING"
        self._pullback_bars = []
        self._pullback_low = None
        self._pullback_high = None
        self.armed = None
        self._last_msg = msg
        return msg

    def reset(self):
        """Daily reset: clear all state for a new session."""
        self._state = "IDLE"
        self._cooldown_remaining = 0
        self._reentry_count = 0
        self._squeeze_entry = None
        self._squeeze_exit = None
        self._squeeze_high = None
        self._squeeze_vol = None
        self._pullback_bars = []
        self._pullback_low = None
        self._pullback_high = None
        self.ema = None
        self.macd_state = MACDState()
        self.armed = None
