"""Short strategy — Strategy B "Lower High Short".

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
