"""
epl_mp_reentry.py — EPL Strategy: Micro-Pullback Re-Entry.

Detects pullback → confirmation → re-entry after SQ 2R graduation.
Plugs into epl_framework.py's EPLStrategy ABC.

State machine per symbol: IDLE → WATCHING → PULLBACK → ARMED → (entry or reset)
Own exits: hard stop, 1.5R trail, VWAP loss, 5-bar time stop.

Gated: WB_EPL_MP_ENABLED=0 by default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Optional

from epl_framework import (
    EPLStrategy, GraduationContext, EntrySignal, ExitSignal,
)


# ── Env vars ─────────────────────────────────────────────────────────

EPL_MP_ENABLED = os.getenv("WB_EPL_MP_ENABLED", "0") == "1"
EPL_MP_COOLDOWN_BARS = int(os.getenv("WB_EPL_MP_COOLDOWN_BARS", "3"))
EPL_MP_MAX_PULLBACK_BARS = int(os.getenv("WB_EPL_MP_MAX_PULLBACK_BARS", "3"))
EPL_MP_MIN_R = float(os.getenv("WB_EPL_MP_MIN_R", "0.06"))
EPL_MP_STOP_PAD = float(os.getenv("WB_EPL_MP_STOP_PAD", "0.01"))
EPL_MP_VWAP_FLOOR = os.getenv("WB_EPL_MP_VWAP_FLOOR", "1") == "1"


# ── Per-symbol state ─────────────────────────────────────────────────

@dataclass
class MPReentryState:
    phase: str = "IDLE"
    graduation_ctx: Optional[GraduationContext] = None
    cooldown_bars: int = 0
    pullback_count: int = 0
    pullback_low: float = float('inf')
    trigger_high: float = 0.0
    entry_price: float = 0.0
    stop_price: float = 0.0
    r_value: float = 0.0
    bars_since_graduation: int = 0
    last_bar: Optional[dict] = None
    prev_bar: Optional[dict] = None
    # Trade management (set when in trade)
    _in_trade: bool = False
    _trail_stop: float = 0.0
    _bars_in_trade: int = 0
    _trade_peak: float = 0.0
    _bars_no_new_high: int = 0


# ── Strategy ─────────────────────────────────────────────────────────

class EPLMPReentry(EPLStrategy):
    """MP Re-Entry: detects micro-pullback re-entry after SQ 2R graduation."""

    def __init__(self):
        self._states: Dict[str, MPReentryState] = {}

    @property
    def name(self) -> str:
        return "epl_mp_reentry"

    @property
    def priority(self) -> int:
        return 50

    def _get_or_create_state(self, symbol: str) -> MPReentryState:
        if symbol not in self._states:
            self._states[symbol] = MPReentryState()
        return self._states[symbol]

    # ── Lifecycle ────────────────────────────────────────────────────

    def on_graduation(self, ctx: GraduationContext) -> None:
        if not EPL_MP_ENABLED:
            return
        state = self._get_or_create_state(ctx.symbol)
        state.graduation_ctx = ctx
        state.phase = "WATCHING"
        state.cooldown_bars = EPL_MP_COOLDOWN_BARS
        state.bars_since_graduation = 0
        state.pullback_count = 0
        state.pullback_low = float('inf')
        state._in_trade = False

    def on_expiry(self, symbol: str) -> None:
        state = self._states.get(symbol)
        if state:
            state.phase = "IDLE"

    def reset(self, symbol: str) -> None:
        state = self._states.get(symbol)
        if state:
            state.phase = "WATCHING" if state.graduation_ctx else "IDLE"
            state.pullback_count = 0
            state.pullback_low = float('inf')
            state.cooldown_bars = EPL_MP_COOLDOWN_BARS
            state._in_trade = False
            state._trail_stop = 0.0
            state._bars_in_trade = 0
            state._trade_peak = 0.0
            state._bars_no_new_high = 0

    # ── Detection: on_bar ────────────────────────────────────────────

    def on_bar(self, symbol: str, bar: dict) -> Optional[EntrySignal]:
        if not EPL_MP_ENABLED:
            return None
        state = self._states.get(symbol)
        if not state or state.phase == "IDLE":
            return None

        state.bars_since_graduation += 1
        state.prev_bar = state.last_bar
        state.last_bar = bar

        # Cooldown
        if state.cooldown_bars > 0:
            state.cooldown_bars -= 1
            return None

        # ── WATCHING: Look for pullback bars ──
        if state.phase == "WATCHING":
            if self._is_pullback_bar(bar, state.prev_bar):
                state.phase = "PULLBACK"
                state.pullback_count = 1
                state.pullback_low = bar["l"]
            return None

        # ── PULLBACK: Count pullback bars, wait for confirmation ──
        if state.phase == "PULLBACK":
            if self._is_pullback_bar(bar, state.prev_bar):
                state.pullback_count += 1
                state.pullback_low = min(state.pullback_low, bar["l"])
                # VWAP floor: pullback breaching VWAP = breakdown, not pullback
                if EPL_MP_VWAP_FLOOR and bar.get("vwap") and state.pullback_low < bar["vwap"]:
                    state.phase = "WATCHING"
                    state.pullback_count = 0
                    state.pullback_low = float('inf')
                    return None
                if state.pullback_count > EPL_MP_MAX_PULLBACK_BARS:
                    state.phase = "WATCHING"
                    state.pullback_count = 0
                    state.pullback_low = float('inf')
                return None

            # Green bar after pullback — check if valid trigger
            is_green = bar.get("green", bar["c"] >= bar["o"])
            if is_green and state.pullback_count >= 1:
                if self._is_valid_trigger(bar, state.prev_bar):
                    entry = bar["h"]
                    stop = state.pullback_low - EPL_MP_STOP_PAD
                    r = entry - stop
                    if r < EPL_MP_MIN_R:
                        state.phase = "WATCHING"
                        state.pullback_count = 0
                        state.pullback_low = float('inf')
                        return None
                    # VWAP floor: block ARM if pullback low is below VWAP
                    if EPL_MP_VWAP_FLOOR and bar.get("vwap") and state.pullback_low < bar["vwap"]:
                        state.phase = "WATCHING"
                        state.pullback_count = 0
                        state.pullback_low = float('inf')
                        return None

                    state.phase = "ARMED"
                    state.trigger_high = entry
                    state.entry_price = entry
                    state.stop_price = stop
                    state.r_value = r
                    return None  # Wait for tick to break trigger_high

            # Neither pullback nor valid trigger — reset
            state.phase = "WATCHING"
            state.pullback_count = 0
            state.pullback_low = float('inf')
            return None

        return None

    # ── Detection: on_tick ───────────────────────────────────────────

    def on_tick(self, symbol: str, price: float, size: int) -> Optional[EntrySignal]:
        if not EPL_MP_ENABLED:
            return None
        state = self._states.get(symbol)
        if not state or state.phase != "ARMED":
            return None

        if price >= state.trigger_high:
            signal = EntrySignal(
                symbol=symbol,
                strategy=self.name,
                entry_price=state.entry_price,
                stop_price=state.stop_price,
                target_price=None,
                position_size_pct=1.0,
                reason=f"pullback_break trigger={state.trigger_high:.2f} pb_low={state.pullback_low:.2f}",
                confidence=self._compute_confidence(state),
            )
            # Reset to WATCHING for potential next pullback
            state.phase = "WATCHING"
            state.pullback_count = 0
            state.pullback_low = float('inf')
            return signal

        return None

    # ── Exit management ──────────────────────────────────────────────

    def manage_exit(self, symbol: str, price: float, bar: Optional[dict]) -> Optional[ExitSignal]:
        state = self._states.get(symbol)
        if not state or not state._in_trade:
            return None

        # 1. Hard stop
        if price <= state.stop_price:
            return ExitSignal(
                symbol=symbol, strategy=self.name,
                exit_price=price, exit_reason="epl_mp_stop_hit",
            )

        # Update peak
        if price > state._trade_peak:
            state._trade_peak = price

        # 2. Trail at 1.5R once profitable
        if state.r_value > 0:
            pnl_r = (price - state.entry_price) / state.r_value
            if pnl_r >= 1.5:
                trail_stop = state._trade_peak - (1.5 * state.r_value)
                if trail_stop > state._trail_stop:
                    state._trail_stop = trail_stop
                if state._trail_stop > 0 and price <= state._trail_stop:
                    return ExitSignal(
                        symbol=symbol, strategy=self.name,
                        exit_price=price,
                        exit_reason=f"epl_mp_trail_exit(R={pnl_r:.1f})",
                    )

        # 3. VWAP loss (on bar close)
        if bar and bar.get("vwap") and price < bar["vwap"]:
            return ExitSignal(
                symbol=symbol, strategy=self.name,
                exit_price=price, exit_reason="epl_mp_vwap_loss",
            )

        # 4. Time stop: 5 bars without new high (on bar close)
        if bar:
            state._bars_in_trade += 1
            if bar["h"] > state._trade_peak:
                state._bars_no_new_high = 0
            else:
                state._bars_no_new_high += 1
            if state._bars_no_new_high >= 5:
                return ExitSignal(
                    symbol=symbol, strategy=self.name,
                    exit_price=price,
                    exit_reason=f"epl_mp_time_exit({state._bars_no_new_high}bars)",
                )

        return None

    def mark_in_trade(self, symbol: str) -> None:
        """Called by sim/bot after executing entry."""
        state = self._states.get(symbol)
        if state:
            state._in_trade = True
            state._trail_stop = 0.0
            state._bars_in_trade = 0
            state._trade_peak = state.entry_price
            state._bars_no_new_high = 0

    # ── Helpers ──────────────────────────────────────────────────────

    def _is_pullback_bar(self, bar: dict, prev_bar: Optional[dict]) -> bool:
        is_green = bar.get("green", bar["c"] >= bar["o"])
        if not is_green:
            return True  # Red candle
        if prev_bar and bar["c"] <= prev_bar["c"]:
            return True  # Green but lower close
        # Wick pullback
        rng = bar["h"] - bar["l"]
        if rng > 0:
            lower_wick = min(bar["o"], bar["c"]) - bar["l"]
            body = abs(bar["c"] - bar["o"])
            if (lower_wick / rng) >= 0.45 and (body / rng) <= 0.35:
                return True
        return False

    def _is_valid_trigger(self, bar: dict, prev_bar: Optional[dict]) -> bool:
        rng = bar["h"] - bar["l"]
        if rng <= 0:
            return False
        upper_wick = bar["h"] - max(bar["o"], bar["c"])
        body = abs(bar["c"] - bar["o"])
        # Reject shooting star
        if (upper_wick / rng) >= 0.6 and (body / rng) <= 0.25:
            return False
        # Valid: hammer, bullish engulfing, or strong close
        lower_wick = min(bar["o"], bar["c"]) - bar["l"]
        is_hammer = (lower_wick / rng) >= 0.5 and (body / rng) <= 0.4
        bull_engulf = (prev_bar and bar["c"] > prev_bar["o"]
                       and bar["o"] < prev_bar["c"])
        strong_close = bar["c"] >= (bar["l"] + 0.75 * rng)
        return is_hammer or bull_engulf or strong_close

    def _compute_confidence(self, state: MPReentryState) -> float:
        score = 0.5
        if state.pullback_count <= 2:
            score += 0.2
        if state.r_value <= 0.10:
            score += 0.1
        if state.bars_since_graduation <= 10:
            score += 0.1
        return min(score, 1.0)
