"""wave_breakout_detector.py — Wave Breakout strategy module.

Strategy validated by Stage 1 + Stage 2 research (DIRECTIVE_WAVE_*) and
approved for Stage 3 build (DIRECTIVE_WAVE_BREAKOUT_STAGE3_BUILD.md).
Configuration corresponds to V8b: V2 trailing-only + V5 pyramid + V7
concurrent (the latter enforced by the bot, not this module).

State machine
-------------
    IDLE → WAVE_OBSERVING → SETUP_SCORED → ARMED → IN_TRADE → IDLE

  IDLE             — fresh start, no waves yet
  WAVE_OBSERVING   — wave_detector has emitted ≥1 wave; we're tracking
                     enough history to score future setups
  SETUP_SCORED     — just scored a down-wave, score < MIN_SCORE; reverts
                     immediately to WAVE_OBSERVING (transient)
  ARMED            — score ≥ MIN_SCORE; waiting for the next tick to enter
                     (entry = next bar's open ≈ first tick after wave bar
                     closes)
  IN_TRADE         — filled long position; managing trailing stop and
                     pyramid logic until exit

Bot integration
---------------
The bot owns:
  - position sizing (compute_wb_position_size, equity-percent + caps)
  - order placement (place_wave_breakout_entry / _exit)
  - portfolio concurrency cap (≤ MAX_CONCURRENT positions across symbols)

The detector returns string messages the bot acts on:
  "WB_RESET: reason"            — state cleared, no action
  "WB_OBSERVE: wave_id=N ..."   — informational, accumulating context
  "WB_DOWNWAVE: score=X ..."    — scored a down-wave; if score >= MIN_SCORE,
                                  detector flips to ARMED and the message
                                  starts with "WB_ARMED" instead
  "WB_ARMED: score=X entry_at=PRICE stop=PRICE"   — ready to enter
  "WB_DISARMED: reason"         — armed but invalidated before entry
  "WB_ENTER: entry=PRICE stop=PRICE score=X"     — fire entry now (tick path)
  "WB_TRAIL_ARMED: peak=P trail=P"               — trailing stop activated
  "WB_PYRAMID: leg2_entry=P risk=$X"             — V5 second leg fired
  "WB_EXIT: reason=R exit=P r_mult=+X.X"         — close position now

bot.py inspects the prefix to decide whether to place orders. All state
transitions are also written to the strategy log with [WB] prefix.

This module is read-only with respect to existing strategy code:
no imports from squeeze_detector, no modifications anywhere else.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from bars import Bar
from macd import MACDState
from wave_detector import WaveDetector


# ─────────────────────────────────────────────────────────────────────
# Config (env-driven; read once at construction)
# ─────────────────────────────────────────────────────────────────────

@dataclass
class WaveBreakoutConfig:
    """Snapshot of all WB_WB_* env vars at detector construction time."""
    # Wave detection (proven in research; do NOT change without re-running census)
    min_wave_pct: float = 0.0075
    wave_min_duration_min: int = 3
    wave_max_duration_min: int = 15
    reversal_confirm_pct: float = 0.005

    # Setup scoring threshold
    min_score: int = 7

    # Exit logic (V2 trailing-only)
    trailing_activate_r: float = 1.0
    trailing_distance_r: float = 0.5
    hard_stop_r: float = 1.0          # initial stop = -1R below entry
    no_time_stop: bool = True
    session_end_force_exit: bool = True
    stop_buffer_pct: float = 0.25     # below bounce-bar low (matches research)

    # Pyramid (V5)
    pyramid_enabled: bool = True
    pyramid_trigger_r: float = 1.0    # add second leg at +1R

    @classmethod
    def from_env(cls) -> "WaveBreakoutConfig":
        def f(name, default):
            return float(os.getenv(name, str(default)))
        def i(name, default):
            return int(float(os.getenv(name, str(default))))
        def b(name, default):
            return os.getenv(name, "1" if default else "0") == "1"
        return cls(
            min_wave_pct=f("WB_WB_MIN_WAVE_PCT", 0.0075),
            wave_min_duration_min=i("WB_WB_WAVE_MIN_DURATION_MIN", 3),
            wave_max_duration_min=i("WB_WB_WAVE_MAX_DURATION_MIN", 15),
            reversal_confirm_pct=f("WB_WB_REVERSAL_CONFIRM_PCT", 0.005),
            min_score=i("WB_WB_MIN_SCORE", 7),
            trailing_activate_r=f("WB_WB_TRAILING_ACTIVATE_R", 1.0),
            trailing_distance_r=f("WB_WB_TRAILING_DISTANCE_R", 0.5),
            hard_stop_r=f("WB_WB_HARD_STOP_R", 1.0),
            no_time_stop=b("WB_WB_NO_TIME_STOP", True),
            session_end_force_exit=b("WB_WB_SESSION_END_FORCE_EXIT", True),
            stop_buffer_pct=f("WB_WB_STOP_BUFFER_PCT", 0.25),
            pyramid_enabled=b("WB_WB_PYRAMID_ENABLED", True),
            pyramid_trigger_r=f("WB_WB_PYRAMID_TRIGGER_R", 1.0),
        )


# ─────────────────────────────────────────────────────────────────────
# Position bookkeeping (per-symbol; the bot owns the order side)
# ─────────────────────────────────────────────────────────────────────

@dataclass
class _Position:
    entry_price: float
    stop: float                     # initial hard stop (-1R)
    score: int
    entry_time_utc: datetime
    R: float                        # 1R = entry - stop (positive)

    # Running state
    peak: float = 0.0
    trail_armed: bool = False
    trail_stop: float = 0.0
    pyramid_filled: bool = False
    pyramid_entry_price: float = 0.0


# ─────────────────────────────────────────────────────────────────────
# WaveBreakoutDetector
# ─────────────────────────────────────────────────────────────────────

class WaveBreakoutDetector:
    """Per-symbol Wave Breakout strategy detector.

    Lifecycle:
        det = WaveBreakoutDetector("BIRD")
        for bar in bar_stream:
            msg = det.on_bar_close_1m(bar, vwap=...)
            if msg: log(msg)
        for tick in ticks:
            msg = det.on_trade_price(tick.price, tick.ts)
            if msg and msg.startswith("WB_ENTER"):
                bot.place_entry(...)
            elif msg and msg.startswith("WB_EXIT"):
                bot.place_exit(...)

    The detector tracks state internally; the bot is informed via return
    values. Position fills are reported back via mark_filled() so we don't
    enter twice.
    """

    def __init__(self, symbol: str, config: Optional[WaveBreakoutConfig] = None):
        self.symbol = symbol
        self.cfg = config or WaveBreakoutConfig.from_env()

        # Wave detection (composed)
        self._wave_det = WaveDetector(
            symbol,
            min_magnitude_pct=self.cfg.min_wave_pct * 100.0,
            min_reversal_pct=self.cfg.reversal_confirm_pct * 100.0,
            min_duration_min=self.cfg.wave_min_duration_min,
            max_duration_min=self.cfg.wave_max_duration_min,
        )
        self._macd = MACDState()

        # Bar history (for scoring, mirrors what wave_census builds)
        self._bars: List[dict] = []
        self._waves: List[dict] = []
        self._vol_prefix: List[int] = [0]

        # State
        self.state: str = "IDLE"
        self._armed_setup: Optional[dict] = None     # populated when ARMED
        self._position: Optional[_Position] = None   # populated when IN_TRADE
        self._pending_entry: bool = False             # bot has order out, not yet filled

    # ── Public API ──────────────────────────────────────────────────────
    def on_bar_close_1m(self, bar: Bar, vwap: Optional[float] = None) -> Optional[str]:
        """Process a closed 1-min bar. Updates wave detection + MACD; may
        emit "WB_ARMED" message (or trail/pyramid status if IN_TRADE)."""
        self._bars.append({
            "start_utc": bar.start_utc,
            "open": float(bar.open), "high": float(bar.high),
            "low": float(bar.low), "close": float(bar.close),
            "volume": int(bar.volume),
        })
        self._vol_prefix.append(self._vol_prefix[-1] + int(bar.volume))
        self._macd.update(float(bar.close))

        wave = self._wave_det.on_bar_close(bar)
        if wave is None:
            return None

        # A wave just confirmed.
        self._waves.append(wave)

        if self.state in ("IN_TRADE",) or self._pending_entry:
            # We're already in a trade or awaiting entry; new waves are
            # informational only. Don't re-arm mid-position.
            return f"WB_OBSERVE: wave_id={wave['wave_id']} dir={wave['direction']} (in-trade)"

        if wave["direction"] != "down":
            # Up-waves contribute to context (used in scoring of future
            # down-waves) but don't themselves trigger arm.
            self.state = "WAVE_OBSERVING"
            return f"WB_OBSERVE: wave_id={wave['wave_id']} dir=up mag={wave['magnitude_pct']:.2f}%"

        # Down-wave: score it as a long-entry setup.
        bounce_bar = self._bars[-1]  # the bar that confirmed the reversal
        prior_waves = self._waves[:-1]
        avg_5 = self._avg_volume_last_n(5, end_index=len(self._bars) - 2)
        score = self._score_down_wave(wave, prior_waves, bounce_bar, avg_5)
        self.state = "SETUP_SCORED"

        if score < self.cfg.min_score:
            self.state = "WAVE_OBSERVING"
            return (f"WB_DOWNWAVE: wave_id={wave['wave_id']} score={score} "
                    f"(< {self.cfg.min_score}, no arm)")

        # Score clears threshold — ARM.
        # Entry candidate = open of NEXT bar (we don't know it yet); arm
        # at "next tick" semantics. We compute the stop and 1R now.
        wave_low = float(bounce_bar["low"])
        stop = wave_low * (1.0 - self.cfg.stop_buffer_pct / 100.0)
        # Provisional entry is bounce_bar's close (will be replaced by
        # actual first-tick price in on_trade_price).
        prov_entry = float(bounce_bar["close"])
        if stop >= prov_entry:
            self.state = "WAVE_OBSERVING"
            return f"WB_NO_ARM: wave_id={wave['wave_id']} stop({stop:.4f})>=entry({prov_entry:.4f})"

        self._armed_setup = {
            "wave_id": int(wave["wave_id"]),
            "score": int(score),
            "wave_low": wave_low,
            "provisional_stop": stop,
            "armed_at_utc": bar.start_utc,
        }
        self.state = "ARMED"
        return (f"WB_ARMED: score={score} wave_id={wave['wave_id']} "
                f"prov_entry={prov_entry:.4f} stop={stop:.4f}")

    def on_trade_price(self, price: float, ts: Optional[datetime] = None) -> Optional[str]:
        """Process a tick. Fires entry on first tick after ARMED, manages
        trailing/pyramid/exits when IN_TRADE."""
        # ── ARMED: first tick after arm = entry trigger ────────────
        if self.state == "ARMED" and self._armed_setup is not None and not self._pending_entry:
            setup = self._armed_setup
            entry_price = float(price)
            stop = setup["provisional_stop"]
            # Recompute stop relative to live entry: use the wave_low's
            # buffer (NOT entry-relative) because that's the structural level.
            R = entry_price - stop
            if R <= 0:
                # Live price already at/below the wave low — disarm.
                self._armed_setup = None
                self.state = "WAVE_OBSERVING"
                return f"WB_DISARMED: live_entry({entry_price:.4f}) <= stop({stop:.4f})"

            self._pending_entry = True
            return (f"WB_ENTER: entry={entry_price:.4f} stop={stop:.4f} "
                    f"score={setup['score']} wave_id={setup['wave_id']}")

        # ── IN_TRADE: manage trail / pyramid / exit ─────────────────
        if self.state == "IN_TRADE" and self._position is not None:
            return self._update_position(float(price))

        return None

    def check_exit(self, price: float, bar: Optional[Bar] = None) -> Optional[str]:
        """Standalone exit check — used by the bot when it wants to assess
        the current position outside of a normal tick callback (e.g., during
        connection-recovery). Same logic as on_trade_price's IN_TRADE path."""
        if self.state != "IN_TRADE" or self._position is None:
            return None
        return self._update_position(float(price))

    # ── Position lifecycle hooks (the bot reports back to us) ──────────
    def mark_filled(self, fill_price: float, fill_time_utc: datetime,
                    score: Optional[int] = None) -> None:
        """Bot calls this once the entry order fills. Detector transitions
        ARMED → IN_TRADE and starts managing exits."""
        if self._armed_setup is None:
            # Defensive: shouldn't happen, but don't crash.
            return
        setup = self._armed_setup
        stop = setup["provisional_stop"]
        R = fill_price - stop
        if R <= 0:
            # Edge case — fill landed at/below stop. Clear and report.
            self._armed_setup = None
            self._pending_entry = False
            self.state = "WAVE_OBSERVING"
            return

        self._position = _Position(
            entry_price=fill_price,
            stop=stop,
            score=int(score if score is not None else setup["score"]),
            entry_time_utc=fill_time_utc,
            R=R,
            peak=fill_price,
            trail_armed=False,
            trail_stop=stop,
        )
        self._armed_setup = None
        self._pending_entry = False
        self.state = "IN_TRADE"

    def mark_entry_failed(self, reason: str = "") -> None:
        """Bot calls if the entry order was rejected / cancelled / timed out
        without fill. Detector clears ARMED state and goes back to OBSERVING."""
        self._armed_setup = None
        self._pending_entry = False
        self.state = "WAVE_OBSERVING"

    def mark_exited(self, exit_price: float = 0.0, reason: str = "") -> None:
        """Bot calls once the exit order fills (or position is force-closed)."""
        self._position = None
        self.state = "WAVE_OBSERVING"

    def reset_session(self) -> None:
        """Clear all state at session boundaries (between morning/evening
        windows or at session end)."""
        self._wave_det.reset()
        self._macd = MACDState()
        self._bars.clear()
        self._waves.clear()
        self._vol_prefix = [0]
        self.state = "IDLE"
        self._armed_setup = None
        self._position = None
        self._pending_entry = False

    # ── Read-only accessors ────────────────────────────────────────────
    @property
    def has_position(self) -> bool:
        return self._position is not None

    @property
    def is_armed(self) -> bool:
        return self.state == "ARMED" and not self._pending_entry

    @property
    def position(self) -> Optional[_Position]:
        return self._position

    # ── Internals ───────────────────────────────────────────────────────
    def _update_position(self, price: float) -> Optional[str]:
        """Per-tick position management — trailing stop activation, trail
        update, pyramid trigger, exit check. Returns a "WB_EXIT: ..." or
        "WB_PYRAMID: ..." or "WB_TRAIL_ARMED: ..." message when state
        changes; otherwise None.

        Stop check ordering (per directive Stage 2): if both stop and
        trailing-stop fire in the same tick, the more conservative one
        (effective_stop = max(initial, trail)) is used."""
        pos = self._position
        if pos is None:
            return None

        # Update peak.
        if price > pos.peak:
            pos.peak = price

        # Trailing-stop activation.
        msg_to_return: Optional[str] = None
        if not pos.trail_armed and (pos.peak - pos.entry_price) >= self.cfg.trailing_activate_r * pos.R:
            pos.trail_armed = True
            new_trail = max(pos.stop, pos.peak - self.cfg.trailing_distance_r * pos.R)
            pos.trail_stop = new_trail
            msg_to_return = f"WB_TRAIL_ARMED: peak={pos.peak:.4f} trail={new_trail:.4f}"

        if pos.trail_armed:
            # Update trail upward as peak rises.
            new_trail = max(pos.stop, pos.peak - self.cfg.trailing_distance_r * pos.R)
            if new_trail > pos.trail_stop:
                pos.trail_stop = new_trail

        # Pyramid (V5). Add second leg when price has reached pyramid_trigger_r·R
        # above entry. Bot computes leg-2 size; we just emit the signal.
        if (self.cfg.pyramid_enabled and not pos.pyramid_filled
                and (pos.peak - pos.entry_price) >= self.cfg.pyramid_trigger_r * pos.R):
            pos.pyramid_filled = True
            pos.pyramid_entry_price = price
            # Note: pyramid signal stacks with trail_armed signal; we
            # prefer the most recent state event.
            return f"WB_PYRAMID: leg2_entry={price:.4f} R={pos.R:.4f}"

        # Exit check.
        effective_stop = pos.trail_stop if pos.trail_armed else pos.stop
        if price <= effective_stop:
            r_mult = (price - pos.entry_price) / pos.R if pos.R > 0 else 0.0
            reason = "trailing_stop" if (pos.trail_armed and effective_stop > pos.stop) else "stop_hit"
            return (f"WB_EXIT: reason={reason} exit={price:.4f} "
                    f"r_mult={r_mult:+.2f}")

        return msg_to_return

    def _score_down_wave(self, wave: dict, prior_waves: List[dict],
                         bounce_bar: dict, avg_5_bar_volume: float) -> int:
        """Score a freshly-emitted down-wave on the 7 directive criteria.

        Mirrors scripts/wave_census.score_wave_setup byte-for-byte; the
        research used this exact formula and any drift would change the
        backtest baseline."""
        score = 0

        # (1) prior waves observed (≥2)
        if len(prior_waves) >= 2:
            score += 1

        # Reference points from recent down-waves (whose end is a low)
        recent_down = [w["end_price"] for w in prior_waves[-3:] if w["direction"] == "down"]
        prev_down = [w["end_price"] for w in prior_waves[-2:] if w["direction"] == "down"]

        # (2) bounce bar low within 1% of recent down-wave low cluster
        if recent_down:
            recent_low = min(recent_down)
            if recent_low > 0 and abs(bounce_bar["low"] - recent_low) / recent_low <= 0.01:
                score += 2

        # (3) MACD histogram rising (positive or just-turning, AND > prev)
        if (self._macd.hist is not None and self._macd.prev_hist is not None
                and self._macd.hist > self._macd.prev_hist
                and self._macd.hist >= -1e-9):
            score += 2

        # (4) higher low (current bounce low > previous down-wave's low)
        if prev_down:
            prev_low = min(prev_down)
            if bounce_bar["low"] > prev_low:
                score += 2

        # (5) volume confirmation
        if avg_5_bar_volume > 0 and bounce_bar["volume"] > avg_5_bar_volume:
            score += 1

        # (6) green candle
        if bounce_bar["close"] > bounce_bar["open"]:
            score += 1

        # (7) minimal upper wick
        body = abs(bounce_bar["close"] - bounce_bar["open"])
        upper_wick = bounce_bar["high"] - max(bounce_bar["open"], bounce_bar["close"])
        if body > 0 and (upper_wick / body) < 0.5:
            score += 1

        return score

    def _avg_volume_last_n(self, n: int, end_index: Optional[int] = None) -> float:
        """Mean volume of the last `n` bars ending at `end_index` (inclusive).
        Returns 0 when fewer than n bars are available. Uses prefix-sum array
        for O(1) lookup."""
        if end_index is None:
            end_index = len(self._bars) - 1
        if end_index < 0 or n <= 0:
            return 0.0
        start = end_index - n + 1
        if start < 0:
            return 0.0
        total = self._vol_prefix[end_index + 1] - self._vol_prefix[start]
        return total / n
