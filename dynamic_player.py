#!/usr/bin/env python3
"""
Dynamic Player V1 — Post-squeeze dip-buying system.

State machine: IDLE → WATCHING → PLAYING → DONE

Reads 1m bars after a squeeze exit, tracks up/down waves, scores each dip
on a 6-signal scorecard, and generates BUY/SELL signals for the simulator.

All thresholds configurable via WB_DP_* env vars.
Gated by WB_DYNAMIC_PLAYER_ENABLED=0 (OFF by default).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────
# Wave data structure
# ─────────────────────────────────────────────

@dataclass
class Wave:
    type: str                  # "UP" or "DOWN"
    start_price: float = 0.0
    end_price: float = 0.0
    start_time: str = ""
    end_time: str = ""
    duration: int = 0          # minutes
    volume: int = 0
    move_pct: float = 0.0
    made_new_hod: bool = False
    vwap_position: str = ""    # "above" or "below"
    ema_position: str = ""     # "above" or "below"
    # For down-waves: lowest price touched during the wave
    low_price: float = 0.0
    # For tracking VWAP/EMA touch-and-recover
    touched_vwap_and_recovered: bool = False
    broke_ema_and_recovered: bool = False


# ─────────────────────────────────────────────
# Wave Tracker
# ─────────────────────────────────────────────

class WaveTracker:
    """Tracks up-waves and down-waves on 1m bars in real time."""

    def __init__(self, reversal_threshold: float = 0.02):
        self.reversal_threshold = reversal_threshold
        self.waves: list[Wave] = []
        self.current_wave: Optional[Wave] = None
        self.swing_high: float = 0.0
        self.swing_low: float = float("inf")
        self.hod: float = 0.0
        self._bar_count: int = 0
        self._cum_volume: int = 0
        self._start_price: float = 0.0
        self._start_time: str = ""
        self._wave_low: float = float("inf")  # tracks lowest price in current wave
        self._wave_bars_below_vwap: int = 0
        self._wave_bars_below_ema: int = 0
        self._wave_first_bar_below_vwap: bool = False
        self._wave_recovered_vwap: bool = False
        self._wave_first_bar_below_ema: bool = False
        self._wave_recovered_ema: bool = False
        self._last_bar_close: float = 0.0
        self._last_bar_time: str = ""
        self._last_vwap: float = 0.0
        self._last_ema: float = 0.0

    def start_tracking(self, price: float, time_str: str):
        """Initialize tracking from a known starting point (SQ exit)."""
        self._start_price = price
        self._start_time = time_str
        self.swing_high = price
        self.swing_low = price
        self.hod = price
        self._last_bar_close = price
        self._wave_low = price
        # Start with an UP wave assumption (most common post-squeeze)
        self.current_wave = Wave(
            type="UP",
            start_price=price,
            start_time=time_str,
        )
        self._cum_volume = 0
        self._bar_count = 0
        self._wave_bars_below_vwap = 0
        self._wave_bars_below_ema = 0
        self._wave_first_bar_below_vwap = False
        self._wave_recovered_vwap = False
        self._wave_first_bar_below_ema = False
        self._wave_recovered_ema = False

    def on_bar(self, bar_close: float, bar_high: float, bar_low: float,
               bar_volume: int, bar_time: str, vwap: float, ema: float,
               hod: float) -> Optional[Wave]:
        """
        Process a 1m bar. Returns a completed wave if a reversal was detected,
        otherwise None.
        """
        if self.current_wave is None:
            return None

        self._bar_count += 1
        self._cum_volume += bar_volume
        self._last_bar_close = bar_close
        self._last_bar_time = bar_time
        self._last_vwap = vwap
        self._last_ema = ema

        # Update HOD
        if bar_high > self.hod:
            self.hod = bar_high
        if hod > self.hod:
            self.hod = hod

        # Track wave low
        if bar_low < self._wave_low:
            self._wave_low = bar_low

        # Track VWAP/EMA touch-and-recover
        if bar_low < vwap:
            self._wave_first_bar_below_vwap = True
        if self._wave_first_bar_below_vwap and bar_close > vwap:
            self._wave_recovered_vwap = True

        if bar_low < ema:
            self._wave_first_bar_below_ema = True
        if self._wave_first_bar_below_ema and bar_close > ema:
            self._wave_recovered_ema = True

        completed = None

        if self.current_wave.type == "UP":
            # Update swing high
            if bar_high > self.swing_high:
                self.swing_high = bar_high

            # Check for reversal: close drops enough below swing high
            if self.swing_high > 0:
                drop_pct = (self.swing_high - bar_close) / self.swing_high
                if drop_pct >= self.reversal_threshold and self._bar_count >= 1:
                    # Complete the UP wave
                    completed = self._complete_wave(self.swing_high, bar_time, vwap, ema)
                    # Start a new DOWN wave
                    self._start_new_wave("DOWN", self.swing_high, bar_time)
                    self.swing_low = bar_low
                    self._wave_low = bar_low

        elif self.current_wave.type == "DOWN":
            # Update swing low
            if bar_low < self.swing_low:
                self.swing_low = bar_low

            # Check for reversal: close rises enough above swing low
            if self.swing_low > 0:
                rise_pct = (bar_close - self.swing_low) / self.swing_low
                if rise_pct >= self.reversal_threshold and self._bar_count >= 1:
                    # Complete the DOWN wave
                    completed = self._complete_wave(self.swing_low, bar_time, vwap, ema)
                    # Start a new UP wave
                    self._start_new_wave("UP", self.swing_low, bar_time)
                    self.swing_high = bar_high
                    self._wave_low = bar_low

        return completed

    def _complete_wave(self, end_price: float, end_time: str,
                       vwap: float, ema: float) -> Wave:
        """Finalize the current wave and return it."""
        w = self.current_wave
        w.end_price = end_price
        w.end_time = end_time
        w.volume = self._cum_volume
        w.duration = max(1, self._bar_count)
        w.low_price = self._wave_low

        # Move %
        if w.start_price > 0:
            w.move_pct = ((end_price - w.start_price) / w.start_price) * 100
        else:
            w.move_pct = 0.0

        # HOD check (for UP waves)
        if w.type == "UP" and end_price >= self.hod * 0.999:
            w.made_new_hod = True

        # Positions
        w.vwap_position = "above" if end_price > vwap else "below"
        w.ema_position = "above" if end_price > ema else "below"

        # Touch-and-recover flags
        w.touched_vwap_and_recovered = self._wave_recovered_vwap
        w.broke_ema_and_recovered = self._wave_recovered_ema

        self.waves.append(w)
        return w

    def _start_new_wave(self, wave_type: str, start_price: float, start_time: str):
        """Initialize a new wave."""
        self.current_wave = Wave(
            type=wave_type,
            start_price=start_price,
            start_time=start_time,
        )
        self._cum_volume = 0
        self._bar_count = 0
        self._wave_low = float("inf")
        self._wave_bars_below_vwap = 0
        self._wave_bars_below_ema = 0
        self._wave_first_bar_below_vwap = False
        self._wave_recovered_vwap = False
        self._wave_first_bar_below_ema = False
        self._wave_recovered_ema = False

    def get_last_completed_wave(self) -> Optional[Wave]:
        """Return the most recently completed wave."""
        return self.waves[-1] if self.waves else None

    def get_prior_up_wave(self) -> Optional[Wave]:
        """Return the most recent completed UP wave."""
        for w in reversed(self.waves):
            if w.type == "UP":
                return w
        return None

    def get_prior_down_wave(self) -> Optional[Wave]:
        """Return the most recent completed DOWN wave."""
        for w in reversed(self.waves):
            if w.type == "DOWN":
                return w
        return None


# ─────────────────────────────────────────────
# Dip Scorecard
# ─────────────────────────────────────────────

class DipScorecard:
    """Scores a completed down-wave on 6 signals."""

    def __init__(self):
        self.max_retrace_green = float(os.getenv("WB_DP_MAX_RETRACE_GREEN", "50"))
        self.max_retrace_red = float(os.getenv("WB_DP_MAX_RETRACE_RED", "80"))
        self.max_dip_dur_green = float(os.getenv("WB_DP_MAX_DIP_DURATION_GREEN", "2"))
        self.max_dip_dur_red = float(os.getenv("WB_DP_MAX_DIP_DURATION_RED", "4"))
        self.max_vol_ratio_green = float(os.getenv("WB_DP_MAX_VOL_RATIO_GREEN", "1.0"))
        self.max_vol_ratio_red = float(os.getenv("WB_DP_MAX_VOL_RATIO_RED", "1.5"))

    def score(self, dip_wave: Wave, prior_up_wave: Wave,
              current_vwap: float, current_ema: float,
              hod: float) -> tuple[int, int, int, list[str]]:
        """
        Score a dip wave. Returns (green, yellow, red, details).
        """
        green = yellow = red = 0
        details = []

        # 1. Retrace %
        if prior_up_wave and abs(prior_up_wave.move_pct) > 0:
            retrace_pct = abs(dip_wave.move_pct) / abs(prior_up_wave.move_pct) * 100
        else:
            retrace_pct = 100.0  # assume worst if no prior up wave

        if retrace_pct < self.max_retrace_green:
            green += 1
            details.append(f"retrace={retrace_pct:.0f}%:GREEN")
        elif retrace_pct < self.max_retrace_red:
            yellow += 1
            details.append(f"retrace={retrace_pct:.0f}%:YELLOW")
        else:
            red += 1
            details.append(f"retrace={retrace_pct:.0f}%:RED")

        # 2. VWAP position
        if dip_wave.end_price > current_vwap:
            if not dip_wave.touched_vwap_and_recovered:
                green += 1
                details.append("vwap=above:GREEN")
            else:
                # Touched VWAP but recovered — still above at end
                green += 1
                details.append("vwap=touched_recovered:GREEN")
        elif dip_wave.touched_vwap_and_recovered:
            yellow += 1
            details.append("vwap=touched_recovered:YELLOW")
        else:
            red += 1
            details.append("vwap=below:RED")

        # 3. EMA9 position
        if dip_wave.end_price > current_ema:
            if not dip_wave.broke_ema_and_recovered:
                green += 1
                details.append("ema=above:GREEN")
            else:
                green += 1
                details.append("ema=broke_recovered:GREEN")
        elif dip_wave.broke_ema_and_recovered:
            yellow += 1
            details.append("ema=broke_recovered:YELLOW")
        else:
            red += 1
            details.append("ema=below:RED")

        # 4. Dip duration
        if dip_wave.duration <= self.max_dip_dur_green:
            green += 1
            details.append(f"dur={dip_wave.duration}m:GREEN")
        elif dip_wave.duration <= self.max_dip_dur_red:
            yellow += 1
            details.append(f"dur={dip_wave.duration}m:YELLOW")
        else:
            red += 1
            details.append(f"dur={dip_wave.duration}m:RED")

        # 5. Volume ratio (dip vol/min vs prior up vol/min)
        dip_vol_per_min = dip_wave.volume / max(dip_wave.duration, 1)
        up_vol_per_min = prior_up_wave.volume / max(prior_up_wave.duration, 1) if prior_up_wave else 1
        vol_ratio = dip_vol_per_min / max(up_vol_per_min, 1)

        if vol_ratio < self.max_vol_ratio_green:
            green += 1
            details.append(f"vol_ratio={vol_ratio:.2f}:GREEN")
        elif vol_ratio < self.max_vol_ratio_red:
            yellow += 1
            details.append(f"vol_ratio={vol_ratio:.2f}:YELLOW")
        else:
            red += 1
            details.append(f"vol_ratio={vol_ratio:.2f}:RED")

        # 6. Prior up-wave made new HOD?
        # For first 3 waves after SQ exit, use SQ exit price as reference
        # (cold-start: actual HOD was set during squeeze, not yet reclaimed)
        _hod_ref = hod
        _hod_label = "hod"
        if hasattr(self, '_waves_since_exit') and self._waves_since_exit <= 3 and self.sq_exit_price > 0:
            _hod_ref = self.sq_exit_price
            _hod_label = "sq_exit"

        if prior_up_wave:
            if prior_up_wave.made_new_hod:
                green += 1
                details.append("prior_hod=yes:GREEN")
            elif _hod_ref > 0 and prior_up_wave.end_price > _hod_ref * 0.97:
                green += 1  # Close to SQ exit price counts as GREEN for early waves
                details.append(f"prior_hod=near_{_hod_label}:GREEN")
            elif _hod_ref > 0 and prior_up_wave.end_price > _hod_ref * 0.90:
                yellow += 1
                details.append(f"prior_hod=approaching_{_hod_label}:YELLOW")
            else:
                red += 1
                details.append("prior_hod=no:RED")
        else:
            yellow += 1
            details.append("prior_hod=unknown:YELLOW")

        return green, yellow, red, details


# ─────────────────────────────────────────────
# Dynamic Player — state machine
# ─────────────────────────────────────────────

class DynamicPlayer:
    """
    Post-squeeze dynamic trading system.

    States: IDLE → WATCHING → PLAYING → DONE

    Generates BUY/SELL signals for the simulator to act on.
    """

    def __init__(self):
        # Configuration from env
        self.enabled = os.getenv("WB_DYNAMIC_PLAYER_ENABLED", "0") == "1"
        self.min_green_signals = int(os.getenv("WB_DP_MIN_GREEN_SIGNALS", "3"))
        self.max_red_signals = int(os.getenv("WB_DP_MAX_RED_SIGNALS", "0"))
        self.hard_stop_pct = float(os.getenv("WB_DP_HARD_STOP_PCT", "2.0"))
        self.time_stop_min = int(os.getenv("WB_DP_TIME_STOP_MIN", "3"))
        self.max_trades = int(os.getenv("WB_DP_MAX_TRADES_PER_STOCK", "10"))
        self.max_loss = float(os.getenv("WB_DP_MAX_LOSS_PER_STOCK", "2000"))
        self.halt_recovery_waves = int(os.getenv("WB_DP_HALT_RECOVERY_WAVES", "3"))
        reversal_threshold = float(os.getenv("WB_DP_WAVE_REVERSAL_THRESHOLD", "0.02"))

        # State
        self.state: str = "IDLE"
        self.done_reason: str = ""
        self.trade_count: int = 0
        self.cumulative_pnl: float = 0.0
        self.consecutive_lower_highs: int = 0
        self.last_bounce_high: float = 0.0

        # Wave tracking
        self.wave_tracker = WaveTracker(reversal_threshold=reversal_threshold)
        self.scorecard = DipScorecard()

        # Active position state
        self.in_position: bool = False
        self.entry_price: float = 0.0
        self.entry_time: str = ""
        self.stop_price: float = 0.0
        self.dip_low: float = 0.0
        self.position_size_mult: float = 1.0  # 1.0 = full, 0.5 = half

        # Halt state
        self.halt_paused: bool = False
        self.halt_above_vwap_waves: int = 0

        # SQ exit reference
        self.sq_exit_price: float = 0.0
        self.sq_exit_time: str = ""

        # Tracking for verbose output
        self.log: list[str] = []

    def reset(self):
        """Reset to IDLE for a new stock."""
        self.state = "IDLE"
        self.done_reason = ""
        self.trade_count = 0
        self.cumulative_pnl = 0.0
        self.consecutive_lower_highs = 0
        self.last_bounce_high = 0.0
        self.in_position = False
        self.entry_price = 0.0
        self.entry_time = ""
        self.stop_price = 0.0
        self.dip_low = 0.0
        self.position_size_mult = 1.0
        self.halt_paused = False
        self.halt_above_vwap_waves = 0
        self.sq_exit_price = 0.0
        self.sq_exit_time = ""
        self.wave_tracker = WaveTracker(
            reversal_threshold=self.wave_tracker.reversal_threshold
        )
        self.log = []

    # ── Public API ──

    def on_sq_exit(self, exit_price: float, exit_time: str,
                   vwap: float, ema: float, hod: float):
        """
        Called when a squeeze trade closes. Transitions IDLE → WATCHING.
        """
        if not self.enabled:
            return
        if self.state != "IDLE":
            return

        self.sq_exit_price = exit_price
        self.sq_exit_time = exit_time
        self._waves_since_exit = 0  # Track waves for cold-start HOD reference
        self.state = "WATCHING"
        self.wave_tracker.start_tracking(exit_price, exit_time)
        self.wave_tracker.hod = hod
        self.log.append(
            f"[{exit_time}] DP: IDLE→WATCHING (SQ exit ${exit_price:.2f}, "
            f"VWAP=${vwap:.2f}, HOD=${hod:.2f})"
        )

    def on_bar(self, bar_close: float, bar_high: float, bar_low: float,
               bar_volume: int, bar_time: str, vwap: float, ema: float,
               hod: float, last_bar_close: float = 0.0) -> Optional[str]:
        """
        Process a 1m bar. Returns signal: "BUY", "SELL", or None.

        Called from simulate.py on each 1m bar close when DP state != IDLE.
        """
        if not self.enabled:
            return None
        if self.state in ("IDLE", "DONE"):
            return None

        # ── Halt detection: 10%+ gap between bars ──
        if last_bar_close > 0 and bar_close > 0:
            gap_pct = abs(bar_close - last_bar_close) / last_bar_close
            if gap_pct >= 0.25:  # 25% — real circuit breaker, not normal volatility
                return self._handle_halt(bar_time, vwap)

        # ── If in halt pause, check for recovery ──
        if self.halt_paused:
            return self._check_halt_recovery(bar_close, bar_time, vwap, ema, hod)

        # ── If in position, check exits ──
        if self.in_position:
            return self._check_exits(
                bar_close, bar_high, bar_low, bar_volume,
                bar_time, vwap, ema, hod
            )

        # ── Feed bar to wave tracker ──
        completed_wave = self.wave_tracker.on_bar(
            bar_close, bar_high, bar_low, bar_volume,
            bar_time, vwap, ema, hod
        )

        if completed_wave is None:
            return None

        # ── Process completed wave ──
        if completed_wave.type == "DOWN":
            return self._on_dip_complete(completed_wave, bar_close, bar_time, vwap, ema, hod)
        elif completed_wave.type == "UP":
            return self._on_bounce_complete(completed_wave, bar_close, bar_time, vwap, ema, hod)

        return None

    def on_trade_closed(self, pnl: float, exit_reason: str):
        """Called when the simulator closes a DP trade. Updates internal state."""
        self.in_position = False
        self.trade_count += 1
        self.cumulative_pnl += pnl
        self.log.append(
            f"DP: trade closed, reason={exit_reason}, pnl=${pnl:+,.0f}, "
            f"total_trades={self.trade_count}, cum_pnl=${self.cumulative_pnl:+,.0f}"
        )

        # Check max trades
        if self.trade_count >= self.max_trades:
            self._go_done("dp_max_trades")
            return

        # Check max loss
        if self.cumulative_pnl <= -self.max_loss:
            self._go_done("dp_max_loss")
            return

    def force_done(self, reason: str):
        """Force DP to DONE state (e.g., when SQ re-arms)."""
        if self.state == "DONE":
            return
        self._go_done(reason)

    def notify_dp_exit(self, price: float, time_str: str, exit_reason: str) -> float:
        """
        Generate exit details for a DP position. Returns the stop price.
        Called by the simulator when it needs to close a DP position.
        """
        pnl_per_share = price - self.entry_price
        return pnl_per_share

    # ── Internal methods ──

    def _on_dip_complete(self, dip_wave: Wave, bar_close: float,
                         bar_time: str, vwap: float, ema: float,
                         hod: float) -> Optional[str]:
        """Handle a completed down-wave (dip). Score it and maybe BUY."""
        prior_up = self.wave_tracker.get_prior_up_wave()

        # Track waves since SQ exit for cold-start HOD reference
        if hasattr(self, '_waves_since_exit'):
            self._waves_since_exit += 1

        # Score the dip
        green, yellow, red, details = self.scorecard.score(
            dip_wave, prior_up, vwap, ema, hod
        )

        detail_str = ", ".join(details)
        self.log.append(
            f"[{bar_time}] DP_DIP: {green}G/{yellow}Y/{red}R ({detail_str})"
        )

        if self.state == "WATCHING":
            # Dip evaluation — stay WATCHING on failure, only DONE after 3 consecutive fails
            if not hasattr(self, '_consecutive_dip_fails'):
                self._consecutive_dip_fails = 0

            if dip_wave.duration > 5:
                self._consecutive_dip_fails += 1
                if self._consecutive_dip_fails >= 5:
                    self._go_done("5_consecutive_dip_fails")
                    return None
                self.log.append(f"[{bar_time}] DP_SKIP: dip too slow ({dip_wave.duration}m), waiting for next")
                return None
            if bar_close < vwap:
                self._consecutive_dip_fails += 1
                if self._consecutive_dip_fails >= 5:
                    self._go_done("5_consecutive_below_vwap")
                    return None
                self.log.append(f"[{bar_time}] DP_SKIP: below VWAP, waiting for next")
                return None
            if red > self.max_red_signals:
                self._consecutive_dip_fails += 1
                if self._consecutive_dip_fails >= 5:
                    self._go_done(f"5_consecutive_red_signals")
                    return None
                self.log.append(f"[{bar_time}] DP_SKIP: {red}R signals, waiting for next dip")
                return None
            if green >= self.min_green_signals:
                self._consecutive_dip_fails = 0  # Reset on success
                self.state = "PLAYING"
                self.log.append(
                    f"[{bar_time}] DP: WATCHING→PLAYING ({green}G/{yellow}Y/{red}R)"
                )
                return self._generate_buy(dip_wave, bar_close, bar_time, green, vwap, ema)
            else:
                self._consecutive_dip_fails += 1
                if self._consecutive_dip_fails >= 5:
                    self._go_done(f"5_consecutive_insufficient_greens")
                    return None
                self.log.append(f"[{bar_time}] DP_SKIP: {green}G not enough, waiting for next")
                return None

        elif self.state == "PLAYING":
            if not hasattr(self, '_playing_skip_count'):
                self._playing_skip_count = 0

            _max_red_playing = int(os.getenv("WB_DP_MAX_RED_SIGNALS_PLAYING", "1"))
            _playing_patience = int(os.getenv("WB_DP_PLAYING_PATIENCE", "5"))

            # STRUCTURAL DONE triggers (run is genuinely over)

            # 1m bar below VWAP = breakdown
            if bar_close < vwap:
                self._go_done("playing_below_vwap")
                return None

            # Dip retrace >100% = exhaustion
            if prior_up and abs(prior_up.move_pct) > 0:
                retrace_pct = abs(dip_wave.move_pct) / abs(prior_up.move_pct) * 100
                if retrace_pct > 100:
                    self._go_done(f"playing_deep_retrace ({retrace_pct:.0f}%)")
                    return None

            # Too many reds on a single dip = trouble (but allow up to max_red_playing)
            if red > _max_red_playing:
                self._playing_skip_count += 1
                if self._playing_skip_count >= _playing_patience:
                    self._go_done(f"playing_{_playing_patience}_consecutive_skips")
                    return None
                self.log.append(
                    f"[{bar_time}] DP_PLAYING_SKIP: {green}G/{yellow}Y/{red}R "
                    f"({red}R > {_max_red_playing} max, skip {self._playing_skip_count}/{_playing_patience})"
                )
                return None

            # Scorecard passes — enter if enough greens
            if green >= self.min_green_signals:
                self._playing_skip_count = 0  # Reset on successful entry
                return self._generate_buy(dip_wave, bar_close, bar_time, green, vwap, ema)
            else:
                # Not enough greens but within red tolerance — skip, don't die
                self._playing_skip_count += 1
                if self._playing_skip_count >= _playing_patience:
                    self._go_done(f"playing_{_playing_patience}_consecutive_skips")
                    return None
                self.log.append(
                    f"[{bar_time}] DP_PLAYING_SKIP: {green}G/{yellow}Y/{red}R "
                    f"(need {self.min_green_signals}G, skip {self._playing_skip_count}/{_playing_patience})"
                )
                return None

        return None

    def _on_bounce_complete(self, bounce_wave: Wave, bar_close: float,
                            bar_time: str, vwap: float, ema: float,
                            hod: float) -> Optional[str]:
        """Handle a completed up-wave (bounce). Check for lower highs."""
        if self.state != "PLAYING":
            return None

        # Track lower highs
        if self.last_bounce_high > 0:
            if bounce_wave.end_price < self.last_bounce_high:
                self.consecutive_lower_highs += 1
                self.log.append(
                    f"[{bar_time}] DP: lower high #{self.consecutive_lower_highs} "
                    f"(${bounce_wave.end_price:.2f} < ${self.last_bounce_high:.2f})"
                )
                if self.consecutive_lower_highs >= 2:
                    self._go_done("two_consecutive_lower_highs")
                    if self.in_position:
                        return "SELL"
                    return None
            else:
                self.consecutive_lower_highs = 0

        self.last_bounce_high = bounce_wave.end_price

        # If in position and the up-wave has completed (reversal detected),
        # that means price is already pulling back — exit the bounce
        if self.in_position:
            return "SELL"

        return None

    def _generate_buy(self, dip_wave: Wave, bar_close: float,
                      bar_time: str, green_count: int,
                      vwap: float, ema: float) -> Optional[str]:
        """Generate a BUY signal with entry/stop details."""
        if self.in_position:
            return None  # already in a trade

        # Entry at the reversal bar close (current bar)
        self.entry_price = bar_close
        self.entry_time = bar_time

        # Stop: lower of entry - hard_stop_pct and dip low
        hard_stop = bar_close * (1 - self.hard_stop_pct / 100)
        dip_low = dip_wave.low_price if dip_wave.low_price < float("inf") else dip_wave.end_price
        self.stop_price = min(hard_stop, dip_low)
        self.dip_low = dip_low

        # Position size: full if 5-6 green, half if 3-4
        if green_count >= 5:
            self.position_size_mult = 1.0
        else:
            self.position_size_mult = 0.5

        self.in_position = True

        self.log.append(
            f"[{bar_time}] DP_BUY: entry=${bar_close:.2f}, stop=${self.stop_price:.2f}, "
            f"dip_low=${dip_low:.2f}, size_mult={self.position_size_mult:.1f}, "
            f"greens={green_count}"
        )

        return "BUY"

    def _check_exits(self, bar_close: float, bar_high: float, bar_low: float,
                     bar_volume: int, bar_time: str, vwap: float, ema: float,
                     hod: float) -> Optional[str]:
        """Check exit conditions while in a DP position."""
        if not self.in_position:
            return None

        # 1. Hard stop
        if bar_low <= self.stop_price:
            self.log.append(
                f"[{bar_time}] DP_HARD_STOP: bar_low=${bar_low:.2f} <= stop=${self.stop_price:.2f}"
            )
            return "SELL"

        # 2. VWAP stop: 1m bar closes below VWAP
        if bar_close < vwap:
            self.log.append(
                f"[{bar_time}] DP_VWAP_STOP: close=${bar_close:.2f} < VWAP=${vwap:.2f}"
            )
            return "SELL"

        # 3. Time stop: unprofitable after N minutes
        if self.entry_time:
            entry_min = _time_to_min(self.entry_time)
            now_min = _time_to_min(bar_time)
            elapsed = now_min - entry_min
            if elapsed >= self.time_stop_min and bar_close <= self.entry_price:
                self.log.append(
                    f"[{bar_time}] DP_TIME_STOP: {elapsed}m elapsed, "
                    f"close=${bar_close:.2f} <= entry=${self.entry_price:.2f}"
                )
                return "SELL"

        # 4. Wave reversal exit: feed bar to wave tracker, check for completed up-wave
        completed_wave = self.wave_tracker.on_bar(
            bar_close, bar_high, bar_low, bar_volume,
            bar_time, vwap, ema, hod
        )

        if completed_wave and completed_wave.type == "UP":
            # Up-wave completed (price reversed down from peak) — take profit
            self.log.append(
                f"[{bar_time}] DP_WAVE_EXIT: up-wave peak=${completed_wave.end_price:.2f}, "
                f"close=${bar_close:.2f}"
            )
            # Also track lower highs
            if self.last_bounce_high > 0 and completed_wave.end_price < self.last_bounce_high:
                self.consecutive_lower_highs += 1
            else:
                self.consecutive_lower_highs = 0
            self.last_bounce_high = completed_wave.end_price
            return "SELL"

        return None

    def _handle_halt(self, bar_time: str, vwap: float) -> Optional[str]:
        """Handle a detected halt (10%+ gap between bars)."""
        self.log.append(f"[{bar_time}] DP: HALT DETECTED")

        if self.in_position:
            # Tighten stop to 1% below current price
            # (The sim will check stop on next bar)
            new_stop = self._last_bar_close() * 0.99
            self.stop_price = max(self.stop_price, new_stop)
            self.log.append(
                f"[{bar_time}] DP: in position during halt — tightened stop to ${self.stop_price:.2f}"
            )
            return None
        else:
            self.halt_paused = True
            self.halt_above_vwap_waves = 0
            self.log.append(
                f"[{bar_time}] DP: HALT_PAUSE activated, "
                f"need {self.halt_recovery_waves} above-VWAP waves"
            )
            return None

    def _last_bar_close(self) -> float:
        """Get last bar close from wave tracker."""
        return self.wave_tracker._last_bar_close

    def _check_halt_recovery(self, bar_close: float, bar_time: str,
                              vwap: float, ema: float, hod: float) -> Optional[str]:
        """Check if halt recovery conditions are met."""
        # Feed bar to wave tracker
        completed_wave = self.wave_tracker.on_bar(
            bar_close, bar_close, bar_close, 0,
            bar_time, vwap, ema, hod
        )

        if completed_wave:
            if completed_wave.end_price > vwap:
                self.halt_above_vwap_waves += 1
                self.log.append(
                    f"[{bar_time}] DP: halt recovery wave {self.halt_above_vwap_waves}"
                    f"/{self.halt_recovery_waves} above VWAP"
                )
            else:
                self.halt_above_vwap_waves = 0

            if self.halt_above_vwap_waves >= self.halt_recovery_waves:
                self.halt_paused = False
                self.log.append(
                    f"[{bar_time}] DP: halt recovery complete, resuming"
                )

        return None

    def _go_done(self, reason: str):
        """Transition to DONE state."""
        self.state = "DONE"
        self.done_reason = reason
        self.log.append(f"DP: → DONE ({reason})")

    def get_exit_reason(self, bar_close: float, bar_low: float,
                        vwap: float) -> str:
        """Determine the specific exit reason for logging."""
        if bar_low <= self.stop_price:
            return "dp_hard_stop"
        if bar_close < vwap:
            return "dp_vwap_stop"
        if self.entry_time:
            entry_min = _time_to_min(self.entry_time)
            now_min = _time_to_min(self.wave_tracker._last_bar_time)
            if now_min - entry_min >= self.time_stop_min and bar_close <= self.entry_price:
                return "dp_time_stop"
        if self.state == "DONE":
            if "lower_high" in self.done_reason:
                return "dp_wave_exit"
            return f"dp_{self.done_reason}"
        return "dp_wave_exit"


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _time_to_min(time_str: str) -> int:
    """Convert HH:MM to minutes since midnight."""
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])
