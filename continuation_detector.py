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
        self._cooldown_bars = int(os.getenv("WB_CT_COOLDOWN_BARS", "2"))
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

        # Cascade lockout (Item 1)
        self._cascade_lockout_min = float(os.getenv("WB_CT_CASCADE_LOCKOUT_MIN", "10"))
        self._lockout_until_minutes: Optional[int] = None  # minutes since midnight
        self._sq_trade_count: int = 0  # Number of SQ trades on this symbol this session
        self._max_sq_for_ct = int(os.getenv("WB_CT_MAX_SQ_TRADES", "2"))  # CT only fires after single-SQ stocks

        # Wider CT target (Item 4 — gated OFF by default)
        self._ct_wider_target = os.getenv("WB_CT_WIDER_TARGET", "0") == "1"
        self._ct_target_r = float(os.getenv("WB_CT_TARGET_R", "3.0"))

        # EMA length (matches squeeze/MP)
        self._ema_len = 9

        # --- Internal state ---
        self._state: str = "IDLE"
        self._cooldown_remaining: int = 0
        self._reentry_count: int = 0

        # Deferred activation (queued until SQ is confirmed idle)
        self._pending_activation: Optional[dict] = None

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
                              hod: float = 0, avg_squeeze_vol: float = 0,
                              bar_time: str = ""):
        """Called when a squeeze trade closes. ALWAYS resets lockout timer.
        Only stages CT activation on winning SQ trades.

        On cascading stocks (VERO, ROLR), SQ fires multiple trades in rapid
        succession. Each close re-calls this method and pushes the lockout
        forward. CT only actually starts processing bars after the lockout
        expires AND the SQ-IDLE gate passes. This ensures CT never interferes
        with SQ cascades.
        """
        if not self.enabled:
            return

        # Count SQ trades on this symbol
        self._sq_trade_count += 1

        # ALWAYS reset the lockout timer — even losing SQ trades mean SQ is
        # still active on this stock. Cascade stocks keep pushing it forward.
        if bar_time and ":" in bar_time:
            h, m = int(bar_time.split(":")[0]), int(bar_time.split(":")[1])
            lockout_min = h * 60 + m + int(self._cascade_lockout_min)
            self._lockout_until_minutes = lockout_min

        # Block CT on cascade stocks (2+ SQ trades = cascade, CT stays locked all session)
        if self._sq_trade_count > self._max_sq_for_ct:
            return  # This is a cascade stock — CT not appropriate

        if pnl <= 0:
            return  # Only stage activation on winning squeezes
        if self._reentry_count >= self._max_reentries:
            return  # Already used all re-entries this session

        # DON'T activate immediately — queue it. On cascading stocks (VERO,
        # ROLR), SQ fires multiple trades in quick succession. Each close
        # re-queues here. The actual activation only happens when the caller
        # (simulate.py / bot_ibkr.py) calls check_pending_activation() during
        # a confirmed SQ IDLE period AND lockout has expired. This ensures
        # zero CT processing during SQ cascades — no butterfly effects.
        self._pending_activation = {
            "entry": entry,
            "exit_price": exit_price,
            "hod": hod,
            "avg_squeeze_vol": avg_squeeze_vol,
        }

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

    def check_pending_activation(self, bar_time: str = "") -> Optional[str]:
        """Called ONLY when SQ is confirmed IDLE and lockout expired.
        Activates CT from queued data. Returns status message or None."""
        if not self._pending_activation:
            return None

        # Block on cascade stocks — if SQ fired 2+ trades, CT is not appropriate
        if self._sq_trade_count > self._max_sq_for_ct:
            self._pending_activation = None
            return f"CT BLOCKED: cascade stock ({self._sq_trade_count} SQ trades > max {self._max_sq_for_ct})"

        # Don't activate during lockout
        if self._lockout_until_minutes is not None and bar_time and ":" in bar_time:
            h, m = int(bar_time.split(":")[0]), int(bar_time.split(":")[1])
            current_min = h * 60 + m
            if current_min < self._lockout_until_minutes:
                return None  # Still locked out

        data = self._pending_activation
        self._pending_activation = None
        
        self._state = "SQ_CONFIRMED"
        self._squeeze_entry = data["entry"]
        self._squeeze_exit = data["exit_price"]
        self._squeeze_high = data["hod"]
        self._squeeze_vol = data["avg_squeeze_vol"]
        self._cooldown_remaining = self._cooldown_bars
        self._pullback_bars = []
        self._pullback_low = None
        self._pullback_high = None
        self.armed = None
        return "CT_ACTIVATED — SQ confirmed idle, starting cooldown"

    def on_bar_close_1m(self, bar, vwap: Optional[float] = None,
                        bar_time: str = "") -> Optional[str]:
        """Process each 1-minute bar close. Returns status message or None."""
        if not self.enabled:
            return None

        # Check lockout — ZERO processing during lockout period
        if self._lockout_until_minutes is not None and bar_time and ":" in bar_time:
            h, m = int(bar_time.split(":")[0]), int(bar_time.split(":")[1])
            current_min = h * 60 + m
            if current_min < self._lockout_until_minutes:
                return None  # LOCKED — zero processing

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
            # SOFT GATES — pause and re-check next bar, keep pullback context
            # On soft gate fail: go back to WATCHING but do NOT clear
            # pullback_bars/pullback_low/pullback_high. On next green bar,
            # CT re-enters CT_PRIMED and re-checks with full context preserved.

            # Gate 1: Volume decay (SOFT — can recover)
            if self._squeeze_vol and self._squeeze_vol > 0 and self._pullback_bars:
                pb_avg_vol = sum(b["v"] for b in self._pullback_bars) / len(self._pullback_bars)
                vol_ratio = pb_avg_vol / self._squeeze_vol
                if vol_ratio > self._min_vol_decay:
                    self._state = "WATCHING"  # Keep pullback bars
                    return f"CT_PAUSE: volume high ({vol_ratio:.1f}x), re-checking"

            # Gate 2: Price above VWAP (SOFT — stock can reclaim on next bar)
            if self._require_vwap and vwap and bar.close < vwap:
                self._state = "WATCHING"  # Keep pullback bars
                return f"CT_PAUSE: below VWAP (${bar.close:.2f} < ${vwap:.2f}), re-checking"

            # Gate 3: Price above 9 EMA (SOFT — same logic)
            if self._require_ema and self.ema and bar.close < self.ema:
                self._state = "WATCHING"  # Keep pullback bars
                return f"CT_PAUSE: below EMA (${bar.close:.2f} < ${self.ema:.2f}), re-checking"

            # HARD GATES — these truly disqualify the setup

            # Gate 4: MACD negative (HARD — dump signal)
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
        self._pending_activation = None
        self._lockout_until_minutes = None
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
