"""Short strategy detectors — Strategies B, A, C from
DIRECTIVE_SHORT_STRATEGY_RESEARCH.md.

Three parallel detector classes sharing the same public contract:
  detector.on_bar_close_1m(bar, vwap=...)  → Optional[log_msg]
  detector.on_trade_price(price)           → Optional[entry_signal]
  detector.armed                           → ShortArm | None (when LH_ARMED)
  detector.reset()
  detector.notify_trade_opened() / notify_trade_closed(pnl)

Strategy B — "Lower High Short" (this file's original implementation).
Strategy A — "Exhaustion Short" — shorts on the first exhaustion-pattern bar
  after HOD (shooting star / bearish engulfing / candle-under-candle).
  Stop at HOD × 1.03.
Strategy C — "VWAP Rejection Short" — waits for price to drop below VWAP,
  bounce back toward VWAP, then get rejected (bar closes below VWAP).
  Stop at VWAP × 1.01.

Strategy B original notes:
State machine fed by 1m bars. Designed to match the morning-through-fade
profile observed in the Phase 1 fade analysis
(cowork_reports/short_analysis/PHASE1_SUMMARY.md).

Flow:
  IDLE → TOPPED      when HOD stops advancing for `dwell_bars` consecutive bars
  TOPPED → LH_ARMED  first bar after the top whose high makes a local peak
                     (higher than immediately-prior bar) but still < HOD
  LH_ARMED → TRIGGERED when any tick trades at or below the LH bar's low
  ARMED/TOPPED → IDLE if any bar makes a new HOD (invalidates the top call)
  LH_ARMED → IDLE    if armed for > max_arm_bars without trigger (stale)

Each triggered signal emits the short entry with:
  trigger_low  — price to short at (break below LH bar's low)
  stop         — HOD × (1 + stop_buffer_pct/100), default HOD * 1.01
  hod_price    — for target computation downstream (target = VWAP by default)

One short per symbol per session. Caller should call `reset()` on new sessions.

No external deps — just the Bar dataclass. Backtest and live paths both
feed `on_bar_close_1m(bar)` and `on_trade_price(price)`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ShortArm:
    """State carried when the detector is LH_ARMED, waiting for a tick-level
    break of the lower-high bar's low."""
    trigger_low: float  # price at/below this triggers the short
    stop: float         # stop-loss price (above HOD + buffer)
    hod_price: float    # HOD at the time of arm
    lh_bar_high: float  # the lower-high bar's high (for diagnostics)
    armed_bar_idx: int  # bar index when armed (for staleness check)


class ShortDetector:
    """Strategy B: short on the break below the first lower high after HOD."""

    def __init__(self):
        # Params — env-driven so Cowork / Manny can tune without code changes
        self.dwell_bars = int(os.getenv("WB_SHORT_DWELL_BARS", "3"))
        self.max_arm_bars = int(os.getenv("WB_SHORT_MAX_ARM_BARS", "8"))
        self.stop_buffer_pct = float(os.getenv("WB_SHORT_STOP_BUFFER_PCT", "1.0"))
        self.min_hod_fade_pct = float(os.getenv("WB_SHORT_MIN_HOD_FADE_PCT", "0.5"))
        self.min_hod_vwap_ratio = float(os.getenv("WB_SHORT_MIN_HOD_VWAP_RATIO", "1.10"))

        # State
        self.symbol: str = ""
        self._state = "IDLE"           # IDLE | TOPPED | LH_ARMED
        self._hod = 0.0                # running high-of-day
        self._hod_bar_idx = -1         # bar index when HOD was set (for dwell)
        self._bar_idx = 0              # monotonic 1m bar counter
        self._prev_bar_high = 0.0      # needed to detect local peaks
        self.armed: Optional[ShortArm] = None

        # Session guards
        self._shorted = False          # once triggered, stay done (one short per session)
        self._in_trade = False         # set by caller when short is open

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    def reset(self):
        self._state = "IDLE"
        self._hod = 0.0
        self._hod_bar_idx = -1
        self._bar_idx = 0
        self._prev_bar_high = 0.0
        self.armed = None
        self._shorted = False
        self._in_trade = False

    def notify_trade_opened(self):
        self._in_trade = True
        self._shorted = True
        self._state = "IDLE"  # disarm; caller manages the position

    def notify_trade_closed(self, pnl: float):
        self._in_trade = False
        # stays _shorted=True; one short per symbol per session

    # ------------------------------------------------------------------
    # Bar-close feed (main state machine driver)
    # ------------------------------------------------------------------
    def on_bar_close_1m(self, bar, vwap: Optional[float] = None) -> Optional[str]:
        """Called on every 1m bar close. Returns a log message or None.

        bar must expose .open, .high, .low, .close (standard Bar dataclass).
        vwap is the session VWAP at the bar's close — used for the HOD/VWAP
        ratio filter (avoid shorting when HOD isn't meaningfully above VWAP;
        R/R collapses).
        """
        self._bar_idx += 1
        prev_high = self._prev_bar_high
        self._prev_bar_high = bar.high

        # Already shorted / in trade — no new signals this session.
        if self._shorted or self._in_trade:
            return None

        # Track running HOD regardless of state.
        if bar.high > self._hod:
            # New HOD: reset the state machine back to IDLE.
            # If we were ARMED on a stale LH, it's invalidated.
            self._hod = bar.high
            self._hod_bar_idx = self._bar_idx
            if self._state != "IDLE":
                old = self._state
                self._state = "IDLE"
                self.armed = None
                return f"SHORT_RESET: new HOD ${bar.high:.4f} (was in {old})"
            return None

        # From here: bar did NOT make a new high.

        if self._state == "IDLE":
            # Need dwell_bars consecutive bars without a new HOD before
            # declaring the top in. The bar that set the HOD counts as bar 0.
            bars_since_hod = self._bar_idx - self._hod_bar_idx
            if bars_since_hod < self.dwell_bars:
                return None

            # Fade-depth filter: require price has actually pulled back at
            # least min_hod_fade_pct from HOD before we consider the top in.
            if self._hod > 0:
                pullback_pct = (self._hod - bar.low) / self._hod * 100
                if pullback_pct < self.min_hod_fade_pct:
                    return None

            # HOD/VWAP ratio filter — skip stocks where the peak isn't
            # meaningfully above VWAP (R/R target = VWAP, so a peak near
            # VWAP has tiny reward).
            if vwap and vwap > 0:
                ratio = self._hod / vwap
                if ratio < self.min_hod_vwap_ratio:
                    return f"SHORT_SKIP: HOD/VWAP={ratio:.2f}x < {self.min_hod_vwap_ratio}x (insufficient R/R)"

            self._state = "TOPPED"
            return f"SHORT_TOPPED: HOD=${self._hod:.4f} dwell={bars_since_hod} bars"

        if self._state == "TOPPED":
            # Looking for a local-peak bar that is < HOD (first lower high).
            # Minimum requirement: bar.high > prev_bar.high (went up relative
            # to the prior bar) AND bar.high < HOD. Once we see it, arm.
            if bar.high > prev_high and bar.high < self._hod:
                trigger_low = bar.low
                stop = self._hod * (1 + self.stop_buffer_pct / 100)
                self.armed = ShortArm(
                    trigger_low=trigger_low,
                    stop=stop,
                    hod_price=self._hod,
                    lh_bar_high=bar.high,
                    armed_bar_idx=self._bar_idx,
                )
                self._state = "LH_ARMED"
                return (f"SHORT_ARMED: LH=${bar.high:.4f} trigger<=${trigger_low:.4f} "
                        f"stop=${stop:.4f} HOD=${self._hod:.4f}")
            return None

        if self._state == "LH_ARMED":
            # Staleness check — if we've been armed too long without a tick
            # cross, abort the arm and wait for a fresh lower-high formation.
            age = self._bar_idx - self.armed.armed_bar_idx if self.armed else 0
            if age > self.max_arm_bars:
                self._state = "TOPPED"
                self.armed = None
                return f"SHORT_UNARM: stale (age={age} bars > {self.max_arm_bars})"
            # Otherwise wait for on_trade_price to fire the trigger.
            return None

        return None

    # ------------------------------------------------------------------
    # Tick-price feed (trigger confirmation)
    # ------------------------------------------------------------------
    def on_trade_price(self, price: float) -> Optional[str]:
        """Called on every live tick. If armed and price crosses below
        trigger_low, emit the entry signal."""
        if self._state != "LH_ARMED" or self.armed is None:
            return None
        if self._shorted or self._in_trade:
            return None
        if price <= self.armed.trigger_low:
            self._shorted = True
            msg = (f"SHORT ENTRY SIGNAL @ {price:.4f} "
                   f"(break <= {self.armed.trigger_low:.4f}) "
                   f"stop={self.armed.stop:.4f} HOD={self.armed.hod_price:.4f}")
            return msg
        return None


# ══════════════════════════════════════════════════════════════════════
# Strategy A — "Exhaustion Short" (Aggressive)
# ══════════════════════════════════════════════════════════════════════

class ShortDetectorA:
    """Strategy A: short on the first exhaustion-pattern bar after HOD.

    Exhaustion patterns (any triggers an arm):
      - Shooting star: upper_wick > 2 × body, lower_wick < body, bar within
        1% of HOD (top-of-run rejection)
      - Bearish engulfing: prev bar green, current bar red, current open
        ≥ prev close, current close ≤ prev open
      - Candle-under-candle (CUC): current bar's high < previous bar's
        high AND current bar closes below prev bar's low (clean break)

    Trigger is IMMEDIATE on the exhaustion bar's close — no separate
    lower-high wait like Strategy B. Trade-off: earlier entry → higher
    R/R potential, but lower-quality setup → more stop-outs.

    Stop: HOD × 1.03 (per directive Strategy A spec).
    """

    def __init__(self):
        self.hod_proximity_pct = float(os.getenv("WB_SHORT_A_HOD_PROX_PCT", "1.0"))
        self.stop_buffer_pct = float(os.getenv("WB_SHORT_A_STOP_BUFFER_PCT", "3.0"))
        self.min_hod_vwap_ratio = float(os.getenv("WB_SHORT_A_MIN_HOD_VWAP_RATIO", "1.10"))

        self.symbol: str = ""
        self._hod = 0.0
        self._hod_bar_idx = -1
        self._bar_idx = 0
        self._prev_bar = None  # for engulfing + CUC checks
        self.armed: Optional[ShortArm] = None
        self._shorted = False
        self._in_trade = False

    def reset(self):
        self._hod = 0.0
        self._hod_bar_idx = -1
        self._bar_idx = 0
        self._prev_bar = None
        self.armed = None
        self._shorted = False
        self._in_trade = False

    def notify_trade_opened(self):
        self._in_trade = True
        self._shorted = True

    def notify_trade_closed(self, pnl: float):
        self._in_trade = False

    def on_bar_close_1m(self, bar, vwap: Optional[float] = None) -> Optional[str]:
        self._bar_idx += 1
        prev = self._prev_bar
        self._prev_bar = bar

        if self._shorted or self._in_trade:
            return None

        # Track HOD
        if bar.high > self._hod:
            self._hod = bar.high
            self._hod_bar_idx = self._bar_idx
            return None

        # HOD/VWAP filter — skip when R/R to VWAP target is too thin
        if vwap and vwap > 0 and self._hod / vwap < self.min_hod_vwap_ratio:
            return None

        # Bar must be within hod_proximity_pct% of HOD to count as a
        # top-of-run exhaustion (otherwise it's mid-fade, not the top).
        if self._hod > 0:
            prox = (self._hod - bar.high) / self._hod * 100
            if prox > self.hod_proximity_pct:
                return None

        # --- Pattern detection ---
        body = abs(bar.close - bar.open)
        upper_wick = bar.high - max(bar.close, bar.open)
        lower_wick = min(bar.close, bar.open) - bar.low
        pattern = None

        # Shooting star
        if body > 0 and upper_wick > 2 * body and lower_wick < body:
            pattern = "shooting_star"

        # Bearish engulfing (needs prev bar)
        if not pattern and prev is not None:
            if (prev.close > prev.open  # prev green
                    and bar.close < bar.open  # cur red
                    and bar.open >= prev.close
                    and bar.close <= prev.open):
                pattern = "bearish_engulfing"

        # Candle-under-candle (needs prev bar)
        if not pattern and prev is not None:
            if bar.high < prev.high and bar.close < prev.low:
                pattern = "cuc"

        if not pattern:
            return None

        # Arm immediately — trigger fires on bar close (price = bar.close)
        trigger_low = bar.close  # short at the close of the pattern bar
        stop = self._hod * (1 + self.stop_buffer_pct / 100)
        self.armed = ShortArm(
            trigger_low=trigger_low,
            stop=stop,
            hod_price=self._hod,
            lh_bar_high=bar.high,
            armed_bar_idx=self._bar_idx,
        )
        self._shorted = True  # Strategy A triggers immediately on bar close
        return (f"SHORT_A ENTRY ({pattern}): close=${bar.close:.4f} "
                f"HOD=${self._hod:.4f} stop=${stop:.4f}")

    def on_trade_price(self, price: float) -> Optional[str]:
        # Strategy A triggers at bar close, not on tick. This method exists
        # for API parity with B/C but is a no-op.
        return None


# ══════════════════════════════════════════════════════════════════════
# Strategy C — "VWAP Rejection Short" (Moderate)
# ══════════════════════════════════════════════════════════════════════

class ShortDetectorC:
    """Strategy C: wait for price to cross below VWAP, bounce back toward
    VWAP, then get rejected (bar fails to close above VWAP). Short on the
    rejection bar.

    State machine:
      IDLE → BELOW_VWAP (first bar whose close < VWAP, after HOD set)
      BELOW_VWAP → BOUNCED (bar.high >= VWAP × 0.995)
      BOUNCED → ARMED (bar.close < VWAP and bar.high <= VWAP × 1.005)
              ← the rejection: touched VWAP but couldn't close above
      ARMED → TRIGGERED (tick breaks below the rejection bar's low)

    Stop: VWAP × 1.01 (per directive — tight stop above VWAP).
    Target: below — VWAP is already lost, so targets are deeper
    (50% retrace, gap fill).
    """

    def __init__(self):
        self.stop_buffer_pct = float(os.getenv("WB_SHORT_C_STOP_BUFFER_PCT", "1.0"))
        self.vwap_proximity_pct = float(os.getenv("WB_SHORT_C_VWAP_PROX_PCT", "0.5"))
        self.min_hod_vwap_ratio = float(os.getenv("WB_SHORT_C_MIN_HOD_VWAP_RATIO", "1.05"))

        self.symbol: str = ""
        self._state = "IDLE"  # IDLE | BELOW_VWAP | BOUNCED | ARMED
        self._hod = 0.0
        self._bar_idx = 0
        self._vwap_at_break = 0.0  # VWAP when we first went below
        self._rejection_vwap = 0.0  # VWAP at the rejection bar (for stop)
        self.armed: Optional[ShortArm] = None
        self._shorted = False
        self._in_trade = False

    def reset(self):
        self._state = "IDLE"
        self._hod = 0.0
        self._bar_idx = 0
        self._vwap_at_break = 0.0
        self._rejection_vwap = 0.0
        self.armed = None
        self._shorted = False
        self._in_trade = False

    def notify_trade_opened(self):
        self._in_trade = True
        self._shorted = True
        self._state = "IDLE"

    def notify_trade_closed(self, pnl: float):
        self._in_trade = False

    def on_bar_close_1m(self, bar, vwap: Optional[float] = None) -> Optional[str]:
        self._bar_idx += 1

        if self._shorted or self._in_trade:
            return None

        # Track HOD
        if bar.high > self._hod:
            self._hod = bar.high

        # VWAP required
        if not vwap or vwap <= 0:
            return None

        # R/R filter — skip if HOD isn't meaningfully above VWAP
        if self._hod / vwap < self.min_hod_vwap_ratio:
            return None

        if self._state == "IDLE":
            # Transition: first bar that closes below VWAP after HOD is set
            if bar.close < vwap and self._hod > vwap:
                self._state = "BELOW_VWAP"
                self._vwap_at_break = vwap
                return f"SHORT_C BELOW_VWAP: close=${bar.close:.4f} < VWAP=${vwap:.4f} HOD=${self._hod:.4f}"
            return None

        if self._state == "BELOW_VWAP":
            # If price breaks back above VWAP AND closes above, the "below"
            # state invalidates (price reclaimed — could be a failed short).
            if bar.close > vwap * (1 + self.vwap_proximity_pct / 100):
                self._state = "IDLE"
                return f"SHORT_C RESET: price reclaimed VWAP (close=${bar.close:.4f})"
            # Has the bounce come yet? We consider a "bounce" as any bar whose
            # HIGH touches VWAP (from below).
            if bar.high >= vwap * (1 - self.vwap_proximity_pct / 100):
                self._state = "BOUNCED"
                return f"SHORT_C BOUNCED: high=${bar.high:.4f} touched VWAP=${vwap:.4f}"
            return None

        if self._state == "BOUNCED":
            # Rejection: bar touched VWAP but closed back below
            if (bar.high >= vwap * (1 - self.vwap_proximity_pct / 100)
                    and bar.close < vwap):
                # Armed: trigger on next tick break below this bar's low
                trigger_low = bar.low
                stop = vwap * (1 + self.stop_buffer_pct / 100)
                self._rejection_vwap = vwap
                self.armed = ShortArm(
                    trigger_low=trigger_low,
                    stop=stop,
                    hod_price=self._hod,
                    lh_bar_high=bar.high,
                    armed_bar_idx=self._bar_idx,
                )
                self._state = "ARMED"
                return (f"SHORT_C ARMED: rejection at VWAP=${vwap:.4f} "
                        f"trigger<=${trigger_low:.4f} stop=${stop:.4f}")
            # If bar closed above VWAP, bounce was successful — reset
            if bar.close > vwap:
                self._state = "IDLE"
                return f"SHORT_C RESET: bounce closed above VWAP (close=${bar.close:.4f})"
            return None

        if self._state == "ARMED":
            # Invalidate if new HOD — can't short into strength
            if bar.high > self._hod * 1.002:
                self._state = "IDLE"
                self.armed = None
                return f"SHORT_C UNARM: new HOD broke (bar.high=${bar.high:.4f})"
            return None

        return None

    def on_trade_price(self, price: float) -> Optional[str]:
        if self._state != "ARMED" or self.armed is None:
            return None
        if self._shorted or self._in_trade:
            return None
        if price <= self.armed.trigger_low:
            self._shorted = True
            return (f"SHORT_C ENTRY SIGNAL @ {price:.4f} "
                    f"(break <= {self.armed.trigger_low:.4f}) "
                    f"stop={self.armed.stop:.4f} HOD={self.armed.hod_price:.4f}")
        return None


# ══════════════════════════════════════════════════════════════════════
# Factory
# ══════════════════════════════════════════════════════════════════════

def make_short_detector(strategy: str = "B"):
    """Return a detector for the named strategy. Strategies: A, B, C."""
    s = strategy.upper()
    if s == "A":
        return ShortDetectorA()
    if s == "C":
        return ShortDetectorC()
    return ShortDetector()  # default B
