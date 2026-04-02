"""
epl_vwap_reclaim.py — EPL Strategy: VWAP Reclaim (Post-2R Deep Pullback).

Detects stocks that dip below VWAP after 2R graduation then reclaim with volume.
Complements MP Re-Entry (shallow pullbacks above VWAP).

State machine: IDLE → WATCHING → BELOW_VWAP → RECLAIMED → ARMED → (entry or reset)

Gated: WB_EPL_VR_ENABLED=0 by default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Optional

from epl_framework import (
    EPLStrategy, GraduationContext, EntrySignal, ExitSignal,
)


# ── Env vars ─────────────────────────────────────────────────────────

EPL_VR_ENABLED = os.getenv("WB_EPL_VR_ENABLED", "0") == "1"
EPL_VR_COOLDOWN_BARS = int(os.getenv("WB_EPL_VR_COOLDOWN_BARS", "3"))
EPL_VR_VOL_MULT = float(os.getenv("WB_EPL_VR_VOL_MULT", "1.5"))
EPL_VR_RECLAIM_WINDOW = int(os.getenv("WB_EPL_VR_RECLAIM_WINDOW", "3"))
EPL_VR_MAX_BELOW_BARS = int(os.getenv("WB_EPL_VR_MAX_BELOW_BARS", "15"))
EPL_VR_MIN_R = float(os.getenv("WB_EPL_VR_MIN_R", "0.06"))
EPL_VR_STOP_PAD = float(os.getenv("WB_EPL_VR_STOP_PAD", "0.01"))
EPL_VR_SEVERE_LOSS_PCT = float(os.getenv("WB_EPL_VR_SEVERE_LOSS_PCT", "20.0"))


# ── Per-symbol state ─────────────────────────────────────────────────

@dataclass
class VRState:
    phase: str = "IDLE"
    graduation_ctx: Optional[GraduationContext] = None
    cooldown_bars: int = 0
    bars_since_graduation: int = 0
    ever_above_vwap_post_grad: bool = False
    below_vwap_bars: int = 0
    below_vwap_low: float = float('inf')
    reclaim_bar: Optional[dict] = None
    reclaim_bars_left: int = 0
    trigger_high: float = 0.0
    entry_price: float = 0.0
    stop_price: float = 0.0
    r_value: float = 0.0
    last_bar: Optional[dict] = None
    avg_volume: float = 0.0
    # Trade management
    _in_trade: bool = False
    _trail_stop: float = 0.0
    _bars_in_trade: int = 0
    _trade_peak: float = 0.0
    _bars_no_new_high: int = 0


# ── Strategy ─────────────────────────────────────────────────────────

class EPLVwapReclaim(EPLStrategy):
    """VWAP Reclaim: deep pullback re-entry after SQ 2R graduation."""

    def __init__(self):
        self._states: Dict[str, VRState] = {}

    @property
    def name(self) -> str:
        return "epl_vwap_reclaim"

    @property
    def priority(self) -> int:
        return 40

    def _get_or_create_state(self, symbol: str) -> VRState:
        if symbol not in self._states:
            self._states[symbol] = VRState()
        return self._states[symbol]

    def _reset_to_watching(self, state: VRState) -> None:
        state.phase = "WATCHING"
        state.below_vwap_bars = 0
        state.below_vwap_low = float('inf')
        state.reclaim_bar = None
        state.reclaim_bars_left = 0

    # ── Lifecycle ────────────────────────────────────────────────────

    def on_graduation(self, ctx: GraduationContext) -> None:
        if not EPL_VR_ENABLED:
            return
        state = self._get_or_create_state(ctx.symbol)
        state.graduation_ctx = ctx
        state.phase = "WATCHING"
        state.cooldown_bars = EPL_VR_COOLDOWN_BARS
        state.bars_since_graduation = 0
        state.ever_above_vwap_post_grad = False
        state.below_vwap_bars = 0
        state.below_vwap_low = float('inf')
        state._in_trade = False

    def on_expiry(self, symbol: str) -> None:
        state = self._states.get(symbol)
        if state:
            state.phase = "IDLE"

    def reset(self, symbol: str) -> None:
        state = self._states.get(symbol)
        if state:
            state.phase = "WATCHING" if state.graduation_ctx else "IDLE"
            state.cooldown_bars = EPL_VR_COOLDOWN_BARS
            state.below_vwap_bars = 0
            state.below_vwap_low = float('inf')
            state.reclaim_bar = None
            state._in_trade = False
            state._trail_stop = 0.0
            state._bars_in_trade = 0
            state._trade_peak = 0.0
            state._bars_no_new_high = 0

    # ── Detection: on_bar ────────────────────────────────────────────

    def on_bar(self, symbol: str, bar: dict) -> Optional[EntrySignal]:
        if not EPL_VR_ENABLED:
            return None
        state = self._states.get(symbol)
        if not state or state.phase == "IDLE":
            return None

        state.bars_since_graduation += 1
        state.last_bar = bar
        vwap = bar.get("vwap")
        if not vwap:
            return None

        # Update running avg volume
        if state.avg_volume == 0:
            state.avg_volume = bar.get("v", 0)
        else:
            state.avg_volume = state.avg_volume * 0.8 + bar.get("v", 0) * 0.2

        # Cooldown
        if state.cooldown_bars > 0:
            state.cooldown_bars -= 1
            return None

        # ── WATCHING: Wait for above VWAP then dip below ──
        if state.phase == "WATCHING":
            if bar["c"] > vwap:
                state.ever_above_vwap_post_grad = True
            elif state.ever_above_vwap_post_grad and bar["c"] < vwap:
                state.phase = "BELOW_VWAP"
                state.below_vwap_bars = 1
                state.below_vwap_low = bar["l"]
            return None

        # ── BELOW_VWAP: Track depth, wait for reclaim ──
        if state.phase == "BELOW_VWAP":
            state.below_vwap_low = min(state.below_vwap_low, bar["l"])

            # Severe loss check
            if vwap > 0:
                vwap_dist_pct = ((vwap - bar["l"]) / vwap) * 100
                if vwap_dist_pct > EPL_VR_SEVERE_LOSS_PCT:
                    self._reset_to_watching(state)
                    return None

            if bar["c"] > vwap:
                # Reclaim — check volume
                is_green = bar.get("green", bar["c"] >= bar["o"])
                vol_ok = state.avg_volume > 0 and bar.get("v", 0) >= (state.avg_volume * EPL_VR_VOL_MULT)
                if vol_ok and is_green:
                    state.phase = "RECLAIMED"
                    state.reclaim_bar = dict(bar)
                    state.reclaim_bars_left = EPL_VR_RECLAIM_WINDOW
                else:
                    self._reset_to_watching(state)
            else:
                state.below_vwap_bars += 1
                if state.below_vwap_bars > EPL_VR_MAX_BELOW_BARS:
                    self._reset_to_watching(state)
            return None

        # ── RECLAIMED: Wait for new-high confirmation ──
        if state.phase == "RECLAIMED":
            if bar["c"] < vwap:
                self._reset_to_watching(state)
                return None

            is_green = bar.get("green", bar["c"] >= bar["o"])
            if bar["h"] > state.reclaim_bar["h"] and is_green:
                # ARM
                entry = bar["h"]
                stop = state.below_vwap_low - EPL_VR_STOP_PAD
                r = entry - stop
                if r < EPL_VR_MIN_R:
                    self._reset_to_watching(state)
                    return None

                state.phase = "ARMED"
                state.trigger_high = entry
                state.entry_price = entry
                state.stop_price = stop
                state.r_value = r
                return None

            state.reclaim_bars_left -= 1
            if state.reclaim_bars_left <= 0:
                self._reset_to_watching(state)
            return None

        return None

    # ── Detection: on_tick ───────────────────────────────────────────

    def on_tick(self, symbol: str, price: float, size: int) -> Optional[EntrySignal]:
        if not EPL_VR_ENABLED:
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
                reason=f"vwap_reclaim trigger={state.trigger_high:.2f} below_low={state.below_vwap_low:.2f}",
                confidence=self._compute_confidence(state),
            )
            self._reset_to_watching(state)
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
                exit_price=price, exit_reason="epl_vr_stop_hit",
            )

        # Update peak
        if price > state._trade_peak:
            state._trade_peak = price

        # 2. Trail at 1.5R
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
                        exit_reason=f"epl_vr_trail_exit(R={pnl_r:.1f})",
                    )

        # 3. VWAP loss (on bar close)
        if bar and bar.get("vwap") and bar["c"] < bar["vwap"]:
            return ExitSignal(
                symbol=symbol, strategy=self.name,
                exit_price=price, exit_reason="epl_vr_vwap_loss",
            )

        # 4. Prior HOD target
        if state.graduation_ctx and price >= state.graduation_ctx.hod_at_graduation:
            return ExitSignal(
                symbol=symbol, strategy=self.name,
                exit_price=price, exit_reason="epl_vr_hod_target",
            )

        # 5. Time stop (on bar close)
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
                    exit_reason=f"epl_vr_time_exit({state._bars_no_new_high}bars)",
                )

        return None

    def mark_in_trade(self, symbol: str) -> None:
        state = self._states.get(symbol)
        if state:
            state._in_trade = True
            state._trail_stop = 0.0
            state._bars_in_trade = 0
            state._trade_peak = state.entry_price
            state._bars_no_new_high = 0

    # ── Helpers ──────────────────────────────────────────────────────

    def _compute_confidence(self, state: VRState) -> float:
        score = 0.5
        if state.below_vwap_bars <= 5:
            score += 0.2
        if (state.graduation_ctx and state.below_vwap_low >
                (state.graduation_ctx.vwap_at_graduation * 0.95)):
            score += 0.1
        if state.bars_since_graduation <= 15:
            score += 0.1
        return min(score, 1.0)
