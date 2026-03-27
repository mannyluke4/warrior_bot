from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Deque, Optional
from collections import deque

from macd import MACDState
from candles import (
    candle_parts,
    is_hammer,
    is_shooting_star,
    is_bullish_engulfing,
    is_bearish_engulfing,
)
from patterns import PatternDetector


def ema_next(prev_ema: Optional[float], price: float, length: int) -> float:
    alpha = 2.0 / (length + 1.0)
    if prev_ema is None:
        return price
    return (price * alpha) + (prev_ema * (1.0 - alpha))


@dataclass
class ArmedTrade:
    trigger_high: float
    stop_low: float
    entry_price: float
    r: float
    score: float = 0.0
    score_detail: str = ""
    setup_type: str = "micro_pullback"
    size_mult: float = 1.0


class MicroPullbackDetector:
    MIN_R = 0.03
    STOP_PAD = 0.01

    def seed_bar_close(self, o: float, h: float, l: float, c: float, v: float):
        """
        Seed-only: updates EMA/MACD/pattern memory/bars deques.
        Does NOT run impulse/pullback/arming logic.
        Historical data is 1-minute bars, so this seeds both 10s and 1m deques.
        """
        # Update EMA + MACD on closes
        self.ema = ema_next(self.ema, c, self.ema_len)
        self.macd_state.update(c)

        info = {"o": o, "h": h, "l": l, "c": c, "v": v, "green": c >= o}
        self.bars.append(info)
        self.bars_1m.append(info)

        # NOTE: Stale stock tracking intentionally NOT updated during seed phase.
        # Seed bars are for warming EMA/MACD only. Quiet premarket bars would
        # falsely trigger "stale" at sim start. Tracking begins in on_bar_close_1m().

        # Pattern signals memory (same as live, but no decisions)
        pattern_sigs = self.patterns.update(o, h, l, c, v)
        for s in pattern_sigs:
            self.pattern_tags.append(s.name)
        self.last_patterns = list(set(self.pattern_tags))

    def __init__(self, ema_len: int = 9, max_pullback_bars: int = 3):
        self.ema_len = ema_len
        self.max_pullback_bars = max_pullback_bars

        # MACD hard gate (kept — MACD bullish at confirmation is a reasonable filter)
        self.macd_hard_gate = os.getenv("WB_MACD_HARD_GATE", "1") == "1"


        # Exhaustion filter settings (prevents late entries on extended stocks)
        self.exhaustion_vwap_pct = float(os.getenv("WB_EXHAUSTION_VWAP_PCT", "10"))
        self.exhaustion_move_pct = float(os.getenv("WB_EXHAUSTION_MOVE_PCT", "50"))
        self.exhaustion_vol_ratio = float(os.getenv("WB_EXHAUSTION_VOL_RATIO", "0.4"))

        # Dynamic filter scaling (scales thresholds to session range for big runners)
        self.trend_strong_range_pct = float(os.getenv("WB_TREND_STRONG_RANGE_PCT", "5"))
        self.exhaustion_vwap_range_mult = float(os.getenv("WB_EXHAUSTION_VWAP_RANGE_MULT", "0.5"))
        self.exhaustion_move_range_mult = float(os.getenv("WB_EXHAUSTION_MOVE_RANGE_MULT", "1.5"))
        self.exhaustion_enabled = os.getenv("WB_EXHAUSTION_ENABLED", "1") == "1"

        # Entry mode: "direct" = 1-bar entry, "pullback" = classic 3-bar cycle
        self.entry_mode = os.getenv("WB_ENTRY_MODE", "pullback")

        self.ema: Optional[float] = None
        self.macd_state = MACDState()

        self.bars: Deque[dict] = deque(maxlen=200)

        self.in_impulse = False
        self.pullback_count = 0
        self.pullback_low: Optional[float] = None
        self.armed: Optional[ArmedTrade] = None

        self.patterns = PatternDetector()
        self.pattern_tags: Deque[str] = deque(maxlen=6)  # remember recent signals
        self.last_patterns: list[str] = []

        # Premarket level tracking (used by bar builder for PM_HIGH display)
        self.premarket_high: Optional[float] = None
        self.premarket_bull_flag_high: Optional[float] = None

        # --- 1-minute setup state machine ---
        self.in_impulse_1m = False
        self.pullback_count_1m = 0
        self.pullback_low_1m: Optional[float] = None
        self.consecutive_green_1m = 0
        self.max_green_1m = int(os.getenv("WB_MAX_GREEN_1M", "5"))
        self.bars_1m: Deque[dict] = deque(maxlen=50)

        # --- LevelMap (resistance tracking) ---
        self.level_map = None  # injected by caller when WB_LEVEL_MAP_ENABLED=1

        # --- Stale stock filter ---
        self.stale_stock_filter = os.getenv("WB_STALE_STOCK_FILTER", "1") == "1"
        self.stale_max_bars_no_hod = int(os.getenv("WB_STALE_MAX_BARS_NO_HOD", "30"))
        self.stale_vol_decay_pct = float(os.getenv("WB_STALE_VOL_DECAY_PCT", "0"))
        self.stale_session_hod_bars = int(os.getenv("WB_STALE_SESSION_HOD_BARS", "120"))
        self.peak_5bar_vol_1m: float = 0.0
        self.bars_since_new_hod_1m: int = 0
        self.session_hod_1m: float = float("-inf")

        self.gap_pct: float | None = None  # set by caller (simulate.py or bot.py)

        # --- MP V2: Post-Squeeze Re-Entry ---
        self._mp_v2_enabled = os.getenv("WB_MP_V2_ENABLED", "0") == "1"
        self._sq_confirmed: bool = False       # Unlocked by squeeze trade close
        self._cooldown_bars_remaining: int = 0  # Bars to wait before active detection
        self._reentry_count: int = 0           # Re-entries taken this session
        self._reentry_cooldown = int(os.getenv("WB_MP_REENTRY_COOLDOWN_BARS", "3"))
        self._max_reentries = int(os.getenv("WB_MP_MAX_REENTRIES", "3"))
        self._reentry_macd_gate = os.getenv("WB_MP_REENTRY_MACD_GATE", "0") == "1"
        self._reentry_use_sq_exits = os.getenv("WB_MP_REENTRY_USE_SQ_EXITS", "1") == "1"
        self._reentry_min_r = float(os.getenv("WB_MP_REENTRY_MIN_R", "0.06"))
        self._reentry_probe_size = float(os.getenv("WB_MP_REENTRY_PROBE_SIZE", "0.5"))

        # --- Post-halt sizing override ---
        self.halt_sizing_enabled = os.getenv("WB_HALT_SIZING_OVERRIDE", "0") == "1"
        self.halt_range_multiplier = float(os.getenv("WB_HALT_RANGE_MULT", "5.0"))
        self.halt_stop_atr_mult = float(os.getenv("WB_HALT_STOP_ATR_MULT", "2.5"))
        self.halt_persist_bars = int(os.getenv("WB_HALT_PERSIST_BARS", "5"))
        self._bar_ranges_1m: deque = deque(maxlen=14)
        self._halt_active_bars: int = 0

        # --- Minimum session volume gate (block ARM on illiquid stocks) ---
        self.min_session_volume = int(os.getenv("WB_MIN_SESSION_VOLUME", "0"))  # 0 = off

        # --- Warmup gate (block ARMs until N bars of history accumulated) ---
        self.warmup_bars = int(os.getenv("WB_WARMUP_BARS", "5"))

        # --- Quality Gate (Ross-aligned setup filtering) ---
        self.quality_gate_enabled = os.getenv("WB_QUALITY_GATE_ENABLED", "0") == "1"
        self.max_pullback_retrace_pct = float(os.getenv("WB_MAX_PULLBACK_RETRACE_PCT", "65"))
        self.max_pb_vol_ratio = float(os.getenv("WB_MAX_PB_VOL_RATIO", "70"))
        self.max_pb_candles = int(os.getenv("WB_MAX_PB_CANDLES", "4"))
        self.min_impulse_pct = float(os.getenv("WB_MIN_IMPULSE_PCT", "2.0"))
        self.min_impulse_vol_mult = float(os.getenv("WB_MIN_IMPULSE_VOL_MULT", "1.5"))
        self.max_symbol_losses = int(os.getenv("WB_MAX_SYMBOL_LOSSES", "1"))
        self.max_symbol_trades = int(os.getenv("WB_MAX_SYMBOL_TRADES", "2"))
        self.price_sweet_low = float(os.getenv("WB_PRICE_SWEET_LOW", "3.0"))
        self.price_sweet_high = float(os.getenv("WB_PRICE_SWEET_HIGH", "15.0"))
        self.no_reentry_enabled = os.getenv("WB_NO_REENTRY_ENABLED", "0") == "1"

        # Quality gate tracking state
        self._impulse_bar_1m: Optional[dict] = None
        self._pullback_vols_1m: list[float] = []
        self._session_losses: int = 0
        self._session_trades: int = 0
        self.symbol: str = ""
        self.stock_float: Optional[float] = None  # millions, set by caller

        # --- Volatility floor (wider stops on volatile stocks) ---
        self.vol_floor_enabled = os.getenv("WB_VOL_FLOOR_ENABLED", "0") == "1"
        self.vol_floor_atr_mult = float(os.getenv("WB_VOL_FLOOR_ATR_MULT", "1.5"))
        self.vol_floor_pct = float(os.getenv("WB_VOL_FLOOR_PCT", "0"))  # min stop as % of entry price (e.g., 5 = 5%)
        self.vol_floor_min_gap_pct = float(os.getenv("WB_VOL_FLOOR_MIN_GAP_PCT", "20"))
        self.vol_floor_max_r_pct = float(os.getenv("WB_VOL_FLOOR_MAX_R_PCT", "3"))  # only activate when R/entry < this %


    def _has_active_structure(self) -> bool:
        return self.in_impulse or self.pullback_count > 0 or (self.armed is not None)

    def _has_active_structure_1m(self) -> bool:
        return self.in_impulse_1m or self.pullback_count_1m > 0 or (self.armed is not None)

    def _full_reset(self):
        self.in_impulse = False
        self.pullback_count = 0
        self.pullback_low = None
        self.in_impulse_1m = False
        self.pullback_count_1m = 0
        self.pullback_low_1m = None
        self.armed = None

    def _full_reset_1m(self):
        self.in_impulse_1m = False
        self.pullback_count_1m = 0
        self.pullback_low_1m = None
        self._impulse_bar_1m = None
        self._pullback_vols_1m = []
        self.armed = None
        # V2: after reset, re-set impulse so we keep looking for pullbacks
        # (squeeze confirmation persists across resets)
        if self._mp_v2_enabled and self._sq_confirmed:
            self.in_impulse_1m = True

    def notify_squeeze_closed(self, symbol: str, pnl: float):
        """Called when a squeeze trade closes. Unlocks MP V2 re-entry detection."""
        if not self._mp_v2_enabled:
            return
        self._sq_confirmed = True
        self._cooldown_bars_remaining = self._reentry_cooldown
        # Reset the 1m state machine so it starts fresh for re-entry detection
        self._full_reset_1m()
        # Pre-set impulse as confirmed (the squeeze was the impulse)
        self.in_impulse_1m = True

    def _is_stale_stock(self) -> tuple[bool, str]:
        """Check if the stock's move is over. Two independent checks:
        1. Rolling window: no new high in last N bars (handles halt spikes aging out)
        2. Session HOD: no new session high in 2+ hours (catches dead oscillating stocks)
        Either check alone triggers stale."""
        if not self.stale_stock_filter:
            return False, ""
        # Check 1: Rolling window — no new high in last N bars
        n = self.stale_max_bars_no_hod
        if len(self.bars_1m) >= n:
            window = list(self.bars_1m)[-n:]
            running_high = window[0]["h"]
            last_new_high_idx = 0
            for i, b in enumerate(window[1:], 1):
                if b["h"] >= running_high:
                    running_high = b["h"]
                    last_new_high_idx = i
            bars_since = (n - 1) - last_new_high_idx
            if bars_since >= n - 1:
                return True, f"no_new_high_{bars_since}_bars"
        # Check 2: Session HOD — no new session high in a long time
        if self.bars_since_new_hod_1m >= self.stale_session_hod_bars:
            return True, f"no_new_session_hod_{self.bars_since_new_hod_1m}_bars"
        # Check 3: Volume decay (optional, off by default)
        if self.stale_vol_decay_pct > 0 and len(self.bars_1m) >= 5 and self.peak_5bar_vol_1m > 0:
            recent_5 = sum(b["v"] for b in list(self.bars_1m)[-5:])
            pct = (recent_5 / self.peak_5bar_vol_1m) * 100
            if pct < self.stale_vol_decay_pct:
                return True, f"vol_decay_{pct:.0f}pct_of_peak"
        return False, ""

    def _halt_adjusted_stop(self, entry: float, raw_stop: float) -> tuple[float, bool]:
        """If in a post-halt period, tighten the stop using average bar range.
        Returns (adjusted_stop, was_adjusted).
        Uses max() to pick the TIGHTER stop (closer to entry = smaller R = bigger qty)."""
        if not self.halt_sizing_enabled or self._halt_active_bars <= 0:
            return raw_stop, False
        if len(self._bar_ranges_1m) < 3:
            return raw_stop, False
        avg_range = sum(self._bar_ranges_1m) / len(self._bar_ranges_1m)
        override_stop = entry - (self.halt_stop_atr_mult * avg_range)
        adjusted = max(raw_stop, override_stop)  # pick TIGHTER stop
        return adjusted, (adjusted != raw_stop)

    def _vol_floor_stop(self, entry: float, raw_stop: float) -> tuple[float, bool]:
        """If R is too small for the stock's volatility, widen the stop.
        Returns (adjusted_stop, was_adjusted).
        Two mechanisms (takes the wider):
          1. ATR-based: min R = vol_floor_atr_mult * avg_bar_range
          2. Price-based: min R = vol_floor_pct% of entry price
        Targeted activation: only when gap% > min AND R/entry < max%
        """
        if not self.vol_floor_enabled:
            return raw_stop, False

        # Targeted activation criteria
        raw_r = entry - raw_stop
        if self.vol_floor_min_gap_pct > 0 and self.gap_pct is not None:
            if abs(self.gap_pct) < self.vol_floor_min_gap_pct:
                return raw_stop, False  # gap too small, stock isn't volatile enough
        if self.vol_floor_max_r_pct > 0 and entry > 0 and raw_r > 0:
            r_pct = (raw_r / entry) * 100
            if r_pct >= self.vol_floor_max_r_pct:
                return raw_stop, False  # R is already wide enough relative to price

        candidates = []

        # ATR-based floor (needs bar history)
        if len(self._bar_ranges_1m) >= 3:
            avg_range = sum(self._bar_ranges_1m) / len(self._bar_ranges_1m)
            atr_stop = entry - (self.vol_floor_atr_mult * avg_range)
            candidates.append(atr_stop)

        # Price-percentage floor (always available)
        if self.vol_floor_pct > 0:
            pct_stop = entry * (1 - self.vol_floor_pct / 100)
            candidates.append(pct_stop)

        if not candidates:
            return raw_stop, False

        vol_stop = min(candidates)  # widest stop (farthest from entry)
        if vol_stop >= raw_stop:
            return raw_stop, False  # raw stop is already wider
        if vol_stop <= 0:
            return raw_stop, False  # safety: don't go negative
        return vol_stop, True

    def _tags_str(self) -> str:
        if not self.last_patterns:
            return "[]"
        return "[" + ", ".join(sorted(self.last_patterns)) + "]"

    def _session_volume(self) -> int:
        """Total volume across all 1m bars seen so far."""
        return sum(b["v"] for b in self.bars_1m)

    def _session_range_pct(self) -> float:
        """Session range (high - low) / low * 100, from bars_1m."""
        if len(self.bars_1m) < 2:
            return 0.0
        hi = max(b["h"] for b in self.bars_1m)
        lo = min(b["l"] for b in self.bars_1m)
        if lo <= 0:
            return 0.0
        return (hi - lo) / lo * 100.0

    def check_l2_exit(self, l2_state: Optional[dict]) -> Optional[str]:
        """No-op stub — L2 removed from unified strategy."""
        return None

    # -----------------------------
    # Scoring (only influences ARMED)
    # -----------------------------
    def _score_setup(self, entry: float, stop_low: float, macd_score: float) -> tuple[float, str]:
        """
        Returns (score, detail_str).
        Keep this simple so tuning is easy.
        """
        score = 0.0
        parts: list[str] = []

        # --- MACD strength (already bounded [-10,+10]) ---
        # Use as a direct contributor, but lightly (so it doesn't dominate)
        score += 0.6 * macd_score
        parts.append(f"macd={macd_score:.1f}*0.6")

        # --- Pattern tags (context) ---
        tags = set(self.last_patterns or [])

        # Bullish structures (bigger points)
        bullish_struct = {"BULL_FLAG", "ASC_TRIANGLE", "FLAT_TOP", "ABCD"}
        if any(t in tags for t in bullish_struct):
            score += 3.0
            parts.append("bull_struct=+3")

        # Helpful context (small points)
        if "VOLUME_SURGE" in tags:
            score += 2.0
            parts.append("vol_surge=+2")

        if "RED_TO_GREEN" in tags:
            score += 1.5
            parts.append("r2g=+1.5")

        if "WHOLE_DOLLAR_NEARBY" in tags:
            score += 0.5
            parts.append("whole=+0.5")

        # Risk tags (penalties)
        if "LOW_LIQUIDITY" in tags:
            score -= 2.5
            parts.append("lowliq=-2.5")

        # --- R quality (optional small preference) ---
        r = entry - stop_low
        if r >= 0.08:
            score += 1.0
            parts.append("R>=0.08=+1")
        elif r >= 0.05:
            score += 0.5
            parts.append("R>=0.05=+0.5")

        # --- Ross Pillar scoring boosts ---
        _rvol = float(os.getenv("WB_SCANNER_RVOL", "0"))
        _float_m = float(os.getenv("WB_SCANNER_FLOAT_M", "20"))
        _gap = float(os.getenv("WB_SCANNER_GAP_PCT", "0"))

        # Relative Volume boost (Pillar 2)
        if _rvol > 0:
            if _rvol >= 10:
                score += 3.0
                parts.append("rvol_10x=+3")
            elif _rvol >= 5:
                score += 2.0
                parts.append("rvol_5x=+2")
            elif _rvol >= 2:
                score += 1.0
                parts.append("rvol_2x=+1")

        # Float tightness boost (Pillar 5)
        if _float_m > 0:
            if _float_m < 2:
                score += 1.5
                parts.append("float_tight=+1.5")
            elif _float_m < 5:
                score += 0.5
                parts.append("float_ok=+0.5")

        # Gap strength boost (Pillar 1 — beyond the 10% hard gate)
        if _gap > 0:
            if _gap >= 50:
                score += 1.5
                parts.append("gap_50=+1.5")
            elif _gap >= 25:
                score += 0.5
                parts.append("gap_25=+0.5")

        detail = ";".join(parts)
        return score, detail

    def on_bar_close(self, bar, vwap: Optional[float]) -> Optional[str]:
        o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume

        # Update EMA + MACD on closes
        self.ema = ema_next(self.ema, c, self.ema_len)
        self.macd_state.update(c)
        macd_score = self.macd_state.strength_score(c)

        info = {"o": o, "h": h, "l": l, "c": c, "v": v, "green": c >= o}
        self.bars.append(info)

        # Pattern signals (keep a short memory so patterns don't "blink" off)
        pattern_sigs = self.patterns.update(o, h, l, c, v)
        for s in pattern_sigs:
            self.pattern_tags.append(s.name)
        self.last_patterns = list(set(self.pattern_tags))

        if vwap is None or self.ema is None:
            return None

        above_vwap = c >= vwap
        above_ema = c >= self.ema

        # VWAP loss clears structure
        if not above_vwap:
            if self._has_active_structure():
                self._full_reset()
                return "RESET (lost VWAP)"
            return None

        # If MACD flips bearish, walk away/reset structure
        if self.macd_state.bearish_cross():
            if self._has_active_structure():
                self._full_reset()
                return "RESET (MACD bearish cross)"
            return None

        # Trend failure: block setups (dynamic for big runners)
        if "DANGER_TREND_DOWN_STRONG" in self.last_patterns:
            sr = self._session_range_pct()
            if sr < self.trend_strong_range_pct:
                self._full_reset()
                return "RESET (trend failure strong)"
            else:
                if self._has_active_structure():
                    self._full_reset()
                    return f"RESET (trend down, range={sr:.1f}%)"

        # Ross never fades the trend — DANGER_TREND_DOWN is a hard block, not just a penalty
        if "DANGER_TREND_DOWN" in self.last_patterns:
            if self._has_active_structure():
                self._full_reset()
                return "RESET (trend down - no fade)"
            return None

        # If already armed, keep it armed until triggered
        if self.armed:
            return None

        # Need enough bars to judge impulse
        if len(self.bars) < 4:
            return None

        b1 = self.bars[-1]
        b2 = self.bars[-2]
        b3 = self.bars[-3]
        b4 = self.bars[-4]

        bull_engulf = is_bullish_engulfing(
            b1["o"], b1["h"], b1["l"], b1["c"],
            b2["o"], b2["h"], b2["l"], b2["c"],
        )

        bear_engulf = is_bearish_engulfing(
            b1["o"], b1["h"], b1["l"], b1["c"],
            b2["o"], b2["h"], b2["l"], b2["c"],
        )

        impulse_now = (
            b1["green"] and b2["green"] and b3["green"]
            and (b1["c"] > b2["c"] > b3["c"] > b4["c"])
            and above_ema
        )

        if bear_engulf:
            self._full_reset()
            return "RESET (bearish engulfing)"

        # Topping wicky gate — only hard-reset when ALSO below EMA
        if "TOPPING_WICKY" in self.last_patterns:
            if self.ema is not None and c >= self.ema:
                pass  # above EMA → tolerate the wick
            else:
                self._full_reset()
                return "RESET (topping wicky)"

        if not self.in_impulse:
            if impulse_now:
                self.in_impulse = True
                self.pullback_count = 0
                self.pullback_low = None
                return "IMPULSE detected"
            return None

        # Pullback bars (including wick-only pullbacks)
        p = candle_parts(b1["o"], b1["h"], b1["l"], b1["c"])
        wick_pullback = (p.lower_wick / p.rng) >= 0.45 and (p.body / p.rng) <= 0.35
        is_pullback_bar = (not b1["green"]) or (b1["c"] <= b2["c"]) or wick_pullback

        if is_pullback_bar:
            self.pullback_count += 1
            self.pullback_low = l if self.pullback_low is None else min(self.pullback_low, l)

            if self.pullback_count > self.max_pullback_bars:
                self._full_reset()
                return "RESET (pullback too long)"

            return f"PULLBACK {self.pullback_count}/{self.max_pullback_bars}"

        # Trigger candle: green bar after at least 1 pullback bar
        if self.pullback_count >= 1 and b1["green"]:

            # Optional: keep this hard gate for now, or allow via score later
            if self.macd_hard_gate and (not self.macd_state.bullish()):
                self._full_reset()
                return "RESET (MACD not bullish)"

            trigger_ok = (
                is_hammer(b1["o"], b1["h"], b1["l"], b1["c"])
                or bull_engulf
                or (b1["c"] >= (b1["l"] + 0.75 * (b1["h"] - b1["l"])))
            )
            bad_trigger = is_shooting_star(b1["o"], b1["h"], b1["l"], b1["c"])
            if (not trigger_ok) or bad_trigger:
                self._full_reset()
                return "RESET (weak trigger candle)"

            trigger_high = h
            entry = trigger_high

            raw_stop = self.pullback_low if self.pullback_low is not None else l
            stop_low = raw_stop - self.STOP_PAD

            # Volatility floor: widen stop if R is too small for stock's volatility
            stop_low, vol_adjusted = self._vol_floor_stop(entry, stop_low)

            r = entry - stop_low
            if r <= 0:
                self._full_reset()
                return "RESET (invalid R)"

            if r < self.MIN_R:
                self._full_reset()
                return f"RESET (R too small: {r:.4f})"

            # Minimum session volume gate
            if self.min_session_volume > 0:
                sv = self._session_volume()
                if sv < self.min_session_volume:
                    self._full_reset()
                    return f"NO_ARM low_session_volume: {sv} < {self.min_session_volume}"

            # Score for logging only (no gate — score has never been validated as predictive)
            score, detail = self._score_setup(entry=entry, stop_low=stop_low, macd_score=macd_score)

            self.armed = ArmedTrade(
                trigger_high=trigger_high,
                stop_low=stop_low,
                entry_price=entry,
                r=r,
                score=score,
                score_detail=detail,
            )
            vf_tag = " [VOL_FLOOR]" if vol_adjusted else ""
            return (
                f"ARMED entry={entry:.4f} stop={stop_low:.4f} R={r:.4f} "
                f"score={score:.1f} macd_score={macd_score:.1f} tags={self._tags_str()} why={detail}{vf_tag}"
            )

        return None

    # -----------------------------
    # DIRECT ENTRY (1-bar mode)
    # -----------------------------
    def _direct_entry_check(self, vwap: float, macd_score: float) -> Optional[str]:
        """Single-bar entry: qualify this bar → ARM immediately.
        Scanner already confirmed the stock is in play. We just need
        a strong green bar above key levels to get in."""
        if len(self.bars_1m) < 2:
            return None

        b1 = self.bars_1m[-1]
        b2 = self.bars_1m[-2]

        # --- Bar qualification ---
        if not b1["green"]:
            return None

        if not (b1["c"] >= self.ema and b1["c"] >= vwap):
            return None

        if is_shooting_star(b1["o"], b1["h"], b1["l"], b1["c"]):
            return None

        # Rising close (momentum)
        if b1["c"] <= b2["c"]:
            return None

        # MACD must be bullish
        if self.macd_hard_gate and not self.macd_state.bullish():
            return f"1M SKIP (MACD not bullish) macd_score={macd_score:.1f}"

        # Candle quality: close should be in upper portion of range
        rng = b1["h"] - b1["l"]
        if rng > 0 and b1["c"] < (b1["l"] + 0.40 * rng):
            return "1M SKIP (weak candle — close in lower 40%)"

        # --- Stop / R ---
        entry = b1["h"]
        raw_stop = b1["l"]
        stop_low = raw_stop - self.STOP_PAD

        # Volatility floor: widen stop if R is too small for stock's volatility
        stop_low, vol_adjusted = self._vol_floor_stop(entry, stop_low)

        # Post-halt sizing override: tighten stop for meaningful position sizing
        # Skip if vol floor already widened (they have opposite goals)
        if not vol_adjusted:
            stop_low, halt_adjusted = self._halt_adjusted_stop(entry, stop_low)
        else:
            halt_adjusted = False

        r = entry - stop_low
        if r <= 0:
            return "1M SKIP (invalid R)"
        if r < self.MIN_R:
            return f"1M SKIP (R too small: {r:.4f})"

        # --- Stale stock filter ---
        stale, stale_reason = self._is_stale_stock()
        if stale:
            return f"1M NO_ARM stale_stock: {stale_reason}"

        # --- Minimum session volume gate ---
        if self.min_session_volume > 0:
            sv = self._session_volume()
            if sv < self.min_session_volume:
                return f"1M NO_ARM low_session_volume: {sv} < {self.min_session_volume}"

        # --- LevelMap resistance gate ---
        if self.level_map is not None:
            blocked, block_reason = self.level_map.blocks_entry(entry, session_hod=self.session_hod_1m)
            if blocked:
                return f"1M NO_ARM level_gate: {block_reason}"

        # --- Scoring ---
        score, detail = self._score_setup(entry=entry, stop_low=stop_low, macd_score=macd_score)

        # --- Exhaustion filters (dynamic: scale thresholds to session range) ---
        if self.exhaustion_enabled:
            sr = self._session_range_pct()
            eff_vwap_pct = max(self.exhaustion_vwap_pct, sr * self.exhaustion_vwap_range_mult)
            eff_move_pct = max(self.exhaustion_move_pct, sr * self.exhaustion_move_range_mult)

            if vwap is not None and vwap > 0:
                pct_above_vwap = (b1["c"] - vwap) / vwap * 100
                if pct_above_vwap > eff_vwap_pct:
                    return (
                        f"1M NO_ARM exhaustion: {pct_above_vwap:.1f}% above VWAP "
                        f"(max {eff_vwap_pct:.1f}%, range={sr:.1f}%) close={b1['c']:.4f} vwap={vwap:.4f}"
                    )

            if len(self.bars_1m) >= 5:
                session_low = min(b["l"] for b in self.bars_1m)
                if session_low > 0:
                    pct_from_low = (b1["c"] - session_low) / session_low * 100
                    if pct_from_low > eff_move_pct:
                        return (
                            f"1M NO_ARM exhaustion: {pct_from_low:.1f}% from session low "
                            f"(max {eff_move_pct:.1f}%, range={sr:.1f}%) close={b1['c']:.4f} low={session_low:.4f}"
                        )

            if len(self.bars_1m) >= 10:
                recent_vol = sum(b["v"] for b in list(self.bars_1m)[-5:])
                earlier_vol = sum(b["v"] for b in list(self.bars_1m)[-10:-5])
                if earlier_vol > 0:
                    vol_ratio = recent_vol / earlier_vol
                    if vol_ratio < self.exhaustion_vol_ratio:
                        return (
                            f"1M NO_ARM exhaustion: vol_ratio={vol_ratio:.2f} "
                            f"(min {self.exhaustion_vol_ratio}) recent={recent_vol} earlier={earlier_vol}"
                        )

        # Warmup gate: require minimum bar history before arming
        if len(self.bars_1m) < self.warmup_bars:
            return f"1M NO_ARM warmup: {len(self.bars_1m)}/{self.warmup_bars} bars"

        # --- Quality Gate (runs between qualification and ARM) ---
        qg_passed, qg_size_mult, qg_logs = self._check_quality_gate(entry)
        for qg_msg in qg_logs:
            print(f"  {qg_msg}", flush=True)
        if not qg_passed:
            return f"1M NO_ARM quality_gate_failed"

        # --- ARM ---
        self.armed = ArmedTrade(
            trigger_high=entry,
            stop_low=stop_low,
            entry_price=entry,
            r=r,
            score=score,
            score_detail=detail,
        )
        vf_tag = " [VOL_FLOOR]" if vol_adjusted else ""
        return (
            f"ARMED entry={entry:.4f} stop={stop_low:.4f} R={r:.4f} "
            f"score={score:.1f} macd_score={macd_score:.1f} tags={self._tags_str()} why={detail}{vf_tag}"
        )

    # -----------------------------
    # Quality Gate (Ross-aligned setup filtering)
    # -----------------------------
    def record_trade_result(self, pnl: float):
        """Called by the engine after a trade closes. Updates session counters for Gate 5."""
        self._session_trades += 1
        if pnl < 0:
            self._session_losses += 1

    def _avg_bar_vol(self) -> float:
        """Average volume across all 1-min bars in the session."""
        if len(self.bars_1m) < 2:
            return 0.0
        return sum(b["v"] for b in self.bars_1m) / len(self.bars_1m)

    def _gate1_clean_pullback(self) -> tuple[bool, str]:
        """Gate 1: Clean pullback — retrace depth, volume ratio, candle count."""
        sym = self.symbol or "?"
        imp = self._impulse_bar_1m
        if imp is None:
            return True, f"QUALITY_GATE symbol={sym} gate=clean_pullback result=SKIP reason=no_impulse_data"

        impulse_range = imp["h"] - imp["l"]
        if impulse_range <= 0:
            return True, f"QUALITY_GATE symbol={sym} gate=clean_pullback result=SKIP reason=zero_impulse_range"

        # Retrace depth
        pb_low = self.pullback_low_1m if self.pullback_low_1m is not None else imp["l"]
        retrace_depth = imp["h"] - pb_low
        retrace_pct = (retrace_depth / impulse_range) * 100

        if retrace_pct > self.max_pullback_retrace_pct:
            return False, (
                f"QUALITY_GATE symbol={sym} gate=clean_pullback result=FAIL "
                f"reason=retrace_{retrace_pct:.0f}pct_>_max_{self.max_pullback_retrace_pct:.0f}pct"
            )

        # Volume ratio: avg pullback vol vs impulse vol
        if self._pullback_vols_1m and imp["v"] > 0:
            avg_pb_vol = sum(self._pullback_vols_1m) / len(self._pullback_vols_1m)
            vol_ratio_pct = (avg_pb_vol / imp["v"]) * 100
            if vol_ratio_pct > self.max_pb_vol_ratio:
                return False, (
                    f"QUALITY_GATE symbol={sym} gate=clean_pullback result=FAIL "
                    f"reason=pb_vol_{vol_ratio_pct:.0f}pct_>_max_{self.max_pb_vol_ratio:.0f}pct"
                )
        else:
            vol_ratio_pct = 0.0

        # Candle count
        if self.pullback_count_1m > self.max_pb_candles:
            return False, (
                f"QUALITY_GATE symbol={sym} gate=clean_pullback result=FAIL "
                f"reason=pb_candles_{self.pullback_count_1m}_>_max_{self.max_pb_candles}"
            )

        return True, (
            f"QUALITY_GATE symbol={sym} gate=clean_pullback result=PASS "
            f"retrace={retrace_pct:.0f}pct vol_ratio={vol_ratio_pct:.0f}pct candles={self.pullback_count_1m}"
        )

    def _gate2_impulse_strength(self) -> tuple[bool, str]:
        """Gate 2: Impulse strength — price move % and volume vs average."""
        sym = self.symbol or "?"
        imp = self._impulse_bar_1m
        if imp is None:
            return True, f"QUALITY_GATE symbol={sym} gate=impulse_strength result=SKIP reason=no_impulse_data"

        # Impulse move as % of price
        impulse_move = imp["h"] - imp["l"]
        if imp["l"] > 0:
            impulse_pct = (impulse_move / imp["l"]) * 100
        else:
            impulse_pct = 0.0

        if impulse_pct < self.min_impulse_pct:
            return False, (
                f"QUALITY_GATE symbol={sym} gate=impulse_strength result=FAIL "
                f"reason=impulse_{impulse_pct:.1f}pct_<_min_{self.min_impulse_pct:.1f}pct"
            )

        # Volume: impulse bar vs avg bar volume
        avg_vol = self._avg_bar_vol()
        if avg_vol > 0:
            vol_mult = imp["v"] / avg_vol
            if vol_mult < self.min_impulse_vol_mult:
                return False, (
                    f"QUALITY_GATE symbol={sym} gate=impulse_strength result=FAIL "
                    f"reason=impulse_vol_{vol_mult:.1f}x_<_min_{self.min_impulse_vol_mult:.1f}x"
                )
        else:
            vol_mult = 0.0

        return True, (
            f"QUALITY_GATE symbol={sym} gate=impulse_strength result=PASS "
            f"impulse={impulse_pct:.1f}pct vol={vol_mult:.1f}x_avg"
        )

    def _gate3_volume_dominance(self) -> tuple[bool, str]:
        """Gate 3: Volume dominance — warn/log only, never blocks."""
        sym = self.symbol or "?"
        if len(self.bars_1m) < 5:
            return True, f"QUALITY_GATE symbol={sym} gate=volume_dominance result=SKIP reason=insufficient_bars"

        # Check if recent volume is strong relative to session average
        recent_5_vol = sum(b["v"] for b in list(self.bars_1m)[-5:])
        avg_5_vol = (sum(b["v"] for b in self.bars_1m) / len(self.bars_1m)) * 5
        if avg_5_vol > 0:
            vol_ratio = recent_5_vol / avg_5_vol
        else:
            vol_ratio = 0.0

        if vol_ratio < 0.5:
            return True, (
                f"QUALITY_GATE symbol={sym} gate=volume_dominance result=WARN "
                f"reason=fading_volume_{vol_ratio:.1f}x_recent_vs_avg"
            )

        return True, (
            f"QUALITY_GATE symbol={sym} gate=volume_dominance result=PASS "
            f"vol_ratio={vol_ratio:.1f}x_recent_vs_avg"
        )

    def _gate4_price_float(self, entry: float) -> tuple[bool, float, str]:
        """Gate 4: Price/float sweet spot. Returns (pass, size_mult, log_msg)."""
        sym = self.symbol or "?"
        size_mult = 1.0

        # Price check
        if entry < 2.0 or entry > 20.0:
            return False, 0.0, (
                f"QUALITY_GATE symbol={sym} gate=price_float result=FAIL "
                f"reason=price_{entry:.2f}_outside_2-20_range"
            )

        if entry < self.price_sweet_low or entry > self.price_sweet_high:
            size_mult = 0.5
            float_str = f" float={self.stock_float:.1f}M" if self.stock_float is not None else ""
            return True, size_mult, (
                f"QUALITY_GATE symbol={sym} gate=price_float result=REDUCE "
                f"reason=price_{entry:.2f}_outside_{self.price_sweet_low}-{self.price_sweet_high}_sweet_spot "
                f"size_mult=0.5{float_str}"
            )

        float_str = f" float={self.stock_float:.1f}M" if self.stock_float is not None else ""
        return True, 1.0, (
            f"QUALITY_GATE symbol={sym} gate=price_float result=PASS "
            f"price={entry:.2f}{float_str}"
        )

    def _gate5_no_reentry(self) -> tuple[bool, str]:
        """Gate 5: No re-entry after loss on this symbol. Runs independently of quality_gate_enabled."""
        sym = self.symbol or "?"

        if self._session_losses >= self.max_symbol_losses:
            return False, (
                f"QUALITY_GATE symbol={sym} gate=no_reentry result=FAIL "
                f"reason=losses_{self._session_losses}_>=_max_{self.max_symbol_losses}"
            )

        if self._session_trades >= self.max_symbol_trades:
            return False, (
                f"QUALITY_GATE symbol={sym} gate=no_reentry result=FAIL "
                f"reason=trades_{self._session_trades}_>=_max_{self.max_symbol_trades}"
            )

        return True, (
            f"QUALITY_GATE symbol={sym} gate=no_reentry result=PASS "
            f"losses={self._session_losses}/{self.max_symbol_losses} trades={self._session_trades}/{self.max_symbol_trades}"
        )

    def _check_quality_gate(self, entry: float) -> tuple[bool, float, list[str]]:
        """
        Run all quality gates on the current setup.
        Returns (passed, size_mult, log_messages).
        Called after confirmation candle, before ARM gates.
        """
        logs: list[str] = []
        size_mult = 1.0
        passed = True

        # Gate 5 (no re-entry) always runs, regardless of quality_gate_enabled
        if self.no_reentry_enabled:
            g5_pass, g5_msg = self._gate5_no_reentry()
            logs.append(g5_msg)
            if not g5_pass:
                return False, size_mult, logs

        if not self.quality_gate_enabled:
            return True, size_mult, logs

        # Gate 1: Clean Pullback
        g1_pass, g1_msg = self._gate1_clean_pullback()
        logs.append(g1_msg)
        if not g1_pass:
            passed = False

        # Gate 2: Impulse Strength
        g2_pass, g2_msg = self._gate2_impulse_strength()
        logs.append(g2_msg)
        if not g2_pass:
            passed = False

        # Gate 3: Volume Dominance (warn only — never blocks)
        _g3_pass, g3_msg = self._gate3_volume_dominance()
        logs.append(g3_msg)

        # Gate 4: Price/Float Sweet Spot
        g4_pass, g4_mult, g4_msg = self._gate4_price_float(entry)
        logs.append(g4_msg)
        if not g4_pass:
            passed = False
        else:
            size_mult = min(size_mult, g4_mult)

        return passed, size_mult, logs

    # -----------------------------
    # PULLBACK ENTRY (classic 3-bar cycle)
    # -----------------------------
    def _pullback_entry_check(self, vwap: float, macd_score: float) -> Optional[str]:
        """Classic IMPULSE → PULLBACK → CONFIRMATION → ARM cycle."""
        # Need at least 2 bars for comparison
        if len(self.bars_1m) < 2:
            return None

        b1 = self.bars_1m[-1]
        b2 = self.bars_1m[-2]

        above_vwap = b1["c"] >= vwap
        above_ema = b1["c"] >= self.ema

        # --- 1-MINUTE STATE MACHINE ---

        # IMPULSE: 1 green candle with momentum
        if not self.in_impulse_1m:
            is_impulse = (
                b1["green"]
                and above_ema
                and above_vwap
                and b1["c"] > b2["c"]
                and not is_shooting_star(b1["o"], b1["h"], b1["l"], b1["c"])
            )

            if is_impulse:
                self.in_impulse_1m = True
                self.pullback_count_1m = 0
                self.pullback_low_1m = None
                self._impulse_bar_1m = dict(b1)
                self._pullback_vols_1m = []
                return "1M IMPULSE detected"
            return None

        # PULLBACK: red bar, lower close, or wick pullback
        p = candle_parts(b1["o"], b1["h"], b1["l"], b1["c"])
        wick_pullback = False
        if p.rng > 0:
            wick_pullback = (p.lower_wick / p.rng) >= 0.45 and (p.body / p.rng) <= 0.35
        is_pullback_bar = (not b1["green"]) or (b1["c"] <= b2["c"]) or wick_pullback

        if is_pullback_bar:
            self.pullback_count_1m += 1
            self.pullback_low_1m = b1["l"] if self.pullback_low_1m is None else min(self.pullback_low_1m, b1["l"])
            self._pullback_vols_1m.append(b1["v"])

            if self.pullback_count_1m > self.max_pullback_bars:
                self._full_reset_1m()
                return "1M RESET (pullback too long)"

            return f"1M PULLBACK {self.pullback_count_1m}/{self.max_pullback_bars}"

        # CONFIRMATION: green bar after at least 1 pullback bar → ARM
        if self.pullback_count_1m >= 1 and b1["green"]:

            # V2: skip MACD gate when post-squeeze and MACD gate is OFF
            _skip_macd = (self._mp_v2_enabled and self._sq_confirmed and not self._reentry_macd_gate)
            if not _skip_macd and self.macd_hard_gate and (not self.macd_state.bullish()):
                self._full_reset_1m()
                return "1M RESET (MACD not bullish)"

            bull_engulf = is_bullish_engulfing(
                b1["o"], b1["h"], b1["l"], b1["c"],
                b2["o"], b2["h"], b2["l"], b2["c"],
            )
            trigger_ok = (
                is_hammer(b1["o"], b1["h"], b1["l"], b1["c"])
                or bull_engulf
                or (b1["c"] >= (b1["l"] + 0.75 * (b1["h"] - b1["l"])))
            )
            bad_trigger = is_shooting_star(b1["o"], b1["h"], b1["l"], b1["c"])

            if (not trigger_ok) or bad_trigger:
                self._full_reset_1m()
                return "1M RESET (weak trigger candle)"

            trigger_high = b1["h"]
            entry = trigger_high

            raw_stop = self.pullback_low_1m if self.pullback_low_1m is not None else b1["l"]
            stop_low = raw_stop - self.STOP_PAD

            # Volatility floor: widen stop if R is too small for stock's volatility
            stop_low, vol_adjusted = self._vol_floor_stop(entry, stop_low)

            # Post-halt sizing override: tighten stop for meaningful position sizing
            # Skip if vol floor already widened (they have opposite goals)
            if not vol_adjusted:
                stop_low, halt_adjusted = self._halt_adjusted_stop(entry, stop_low)
            else:
                halt_adjusted = False

            r = entry - stop_low
            if r <= 0:
                self._full_reset_1m()
                return "1M RESET (invalid R)"

            # V2: use wider min R for post-squeeze re-entries
            _eff_min_r = self._reentry_min_r if (self._mp_v2_enabled and self._sq_confirmed) else self.MIN_R
            if r < _eff_min_r:
                self._full_reset_1m()
                return f"1M RESET (R too small: {r:.4f})"

            # --- Quality Gate (runs between confirmation and ARM gates) ---
            qg_passed, qg_size_mult, qg_logs = self._check_quality_gate(entry)
            for qg_msg in qg_logs:
                print(f"  {qg_msg}", flush=True)
            if not qg_passed:
                self._full_reset_1m()
                return f"1M NO_ARM quality_gate_failed"

            # Stale stock filter
            stale, stale_reason = self._is_stale_stock()
            if stale:
                self._full_reset_1m()
                return f"1M NO_ARM stale_stock: {stale_reason}"

            # Minimum session volume gate
            if self.min_session_volume > 0:
                sv = self._session_volume()
                if sv < self.min_session_volume:
                    self._full_reset_1m()
                    return f"1M NO_ARM low_session_volume: {sv} < {self.min_session_volume}"

            # LevelMap resistance gate
            if self.level_map is not None:
                blocked, block_reason = self.level_map.blocks_entry(entry, session_hod=self.session_hod_1m)
                if blocked:
                    self._full_reset_1m()
                    return f"1M NO_ARM level_gate: {block_reason}"

            score, detail = self._score_setup(entry=entry, stop_low=stop_low, macd_score=macd_score)

            # Exhaustion filters (dynamic: scale thresholds to session range)
            if self.exhaustion_enabled:
                sr = self._session_range_pct()
                eff_vwap_pct = max(self.exhaustion_vwap_pct, sr * self.exhaustion_vwap_range_mult)
                eff_move_pct = max(self.exhaustion_move_pct, sr * self.exhaustion_move_range_mult)

                if vwap is not None and vwap > 0:
                    pct_above_vwap = (b1["c"] - vwap) / vwap * 100
                    if pct_above_vwap > eff_vwap_pct:
                        self._full_reset_1m()
                        return (
                            f"1M NO_ARM exhaustion: {pct_above_vwap:.1f}% above VWAP "
                            f"(max {eff_vwap_pct:.1f}%, range={sr:.1f}%) close={b1['c']:.4f} vwap={vwap:.4f}"
                        )

                if len(self.bars_1m) >= 5:
                    session_low = min(b["l"] for b in self.bars_1m)
                    if session_low > 0:
                        pct_from_low = (b1["c"] - session_low) / session_low * 100
                        if pct_from_low > eff_move_pct:
                            self._full_reset_1m()
                            return (
                                f"1M NO_ARM exhaustion: {pct_from_low:.1f}% from session low "
                                f"(max {eff_move_pct:.1f}%, range={sr:.1f}%) close={b1['c']:.4f} low={session_low:.4f}"
                            )

                if len(self.bars_1m) >= 10:
                    recent_vol = sum(b["v"] for b in list(self.bars_1m)[-5:])
                    earlier_vol = sum(b["v"] for b in list(self.bars_1m)[-10:-5])
                    if earlier_vol > 0:
                        vol_ratio = recent_vol / earlier_vol
                        if vol_ratio < self.exhaustion_vol_ratio:
                            self._full_reset_1m()
                            return (
                                f"1M NO_ARM exhaustion: vol_ratio={vol_ratio:.2f} "
                                f"(min {self.exhaustion_vol_ratio}) recent={recent_vol} earlier={earlier_vol}"
                            )

            # Warmup gate: require minimum bar history before arming
            if len(self.bars_1m) < self.warmup_bars:
                return f"1M NO_ARM warmup: {len(self.bars_1m)}/{self.warmup_bars} bars"

            # V2: tag re-entry trades and use probe size for first entry
            if self._mp_v2_enabled and self._sq_confirmed:
                _v2_size = self._reentry_probe_size if self._reentry_count == 0 else 1.0
                self.armed = ArmedTrade(
                    trigger_high=trigger_high,
                    stop_low=stop_low,
                    entry_price=entry,
                    r=r,
                    score=score,
                    score_detail=detail,
                    setup_type="mp_reentry",
                    size_mult=_v2_size,
                )
            else:
                self.armed = ArmedTrade(
                    trigger_high=trigger_high,
                    stop_low=stop_low,
                    entry_price=entry,
                    r=r,
                    score=score,
                    score_detail=detail,
                    size_mult=qg_size_mult,
                )
            vf_tag = " [VOL_FLOOR]" if vol_adjusted else ""
            qg_tag = f" [QG_SIZE={qg_size_mult:.0%}]" if qg_size_mult < 1.0 else ""
            return (
                f"ARMED entry={entry:.4f} stop={stop_low:.4f} R={r:.4f} "
                f"score={score:.1f} macd_score={macd_score:.1f} tags={self._tags_str()} why={detail}{vf_tag}{qg_tag}"
            )

        return None

    # -----------------------------
    # 1-MINUTE PRIMARY DETECTION
    # -----------------------------
    def on_bar_close_1m(self, bar, vwap: Optional[float], l2_state: Optional[dict] = None) -> Optional[str]:
        """
        Primary setup detection on 1-minute bars.
        Impulse = 1 green candle with momentum (not 3).
        Pullback = 1-3 bars pulling back.
        Confirmation = 1 green bar → ARM.
        """
        o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume

        # Update shared indicators on 1-minute closes
        self.ema = ema_next(self.ema, c, self.ema_len)
        self.macd_state.update(c)
        macd_score = self.macd_state.strength_score(c)

        info = {"o": o, "h": h, "l": l, "c": c, "v": v, "green": c >= o}
        self.bars_1m.append(info)

        # Feed LevelMap on every 1-min bar close
        if self.level_map is not None:
            self.level_map.on_bar_close(o, h, l, c, v)
            if vwap is not None:
                self.level_map.update_vwap(vwap)

        # Stale stock tracking
        if h > self.session_hod_1m:
            self.session_hod_1m = h
            self.bars_since_new_hod_1m = 0
        else:
            self.bars_since_new_hod_1m += 1
        if len(self.bars_1m) >= 5:
            recent_5 = sum(b["v"] for b in list(self.bars_1m)[-5:])
            self.peak_5bar_vol_1m = max(self.peak_5bar_vol_1m, recent_5)

        # Post-halt range tracking
        if self.halt_sizing_enabled:
            bar_range = h - l
            if len(self._bar_ranges_1m) >= 3:
                avg_range = sum(self._bar_ranges_1m) / len(self._bar_ranges_1m)
                if avg_range > 0 and bar_range > self.halt_range_multiplier * avg_range:
                    self._halt_active_bars = self.halt_persist_bars
                elif self._halt_active_bars > 0:
                    self._halt_active_bars -= 1
            self._bar_ranges_1m.append(bar_range)

        # Pattern signals (keep a short memory so patterns don't "blink" off)
        pattern_sigs = self.patterns.update(o, h, l, c, v)
        for s in pattern_sigs:
            self.pattern_tags.append(s.name)
        self.last_patterns = list(set(self.pattern_tags))

        if vwap is None or self.ema is None:
            return None

        # --- MP V2 gate: post-squeeze re-entry mode ---
        # When V2 is enabled, standalone MP logic is bypassed entirely.
        # V2 only runs when squeeze has confirmed the stock.
        if self._mp_v2_enabled:
            if not self._sq_confirmed:
                return None  # Stay dormant — no squeeze confirmation yet
            if self._cooldown_bars_remaining > 0:
                self._cooldown_bars_remaining -= 1
                return f"MP_V2 COOLDOWN ({self._cooldown_bars_remaining} bars remaining)"
            if self._reentry_count >= self._max_reentries:
                return f"MP_V2 MAX_REENTRIES ({self._reentry_count}/{self._max_reentries})"
            # Ensure impulse is set (squeeze was the impulse)
            if not self.in_impulse_1m:
                self.in_impulse_1m = True
            # Fall through to detection logic with V2-specific behavior...

        above_vwap = c >= vwap
        above_ema = c >= self.ema

        # --- Guard checks ---

        # VWAP loss clears structure
        if not above_vwap:
            if self._has_active_structure_1m():
                blocked_arm = self.armed  # capture before reset clears it
                self._full_reset_1m()
                if blocked_arm is not None:
                    return (
                        f"1M RESET (lost VWAP) VWAP_BLOCKED_ARM "
                        f"score={blocked_arm.score:.1f} "
                        f"entry={blocked_arm.entry_price:.4f} "
                        f"stop={blocked_arm.stop_low:.4f} "
                        f"R={blocked_arm.r:.4f} "
                        f"detail={blocked_arm.score_detail} "
                        f"close={c:.4f} vwap={vwap:.4f}"
                    )
                return "1M RESET (lost VWAP)"
            return None

        # MACD bearish cross resets structure
        # V2: suppress MACD resets when post-squeeze and MACD gate is OFF (default)
        # After a squeeze, MACD going bearish IS the pullback we want to buy.
        if self.macd_state.bearish_cross():
            if self._mp_v2_enabled and self._sq_confirmed and not self._reentry_macd_gate:
                pass  # V2: MACD bearish cross is expected during pullback — don't reset
            elif self._has_active_structure_1m():
                self._full_reset_1m()
                return "1M RESET (MACD bearish cross)"
            else:
                return None

        # Trend failure: hard block (dynamic for big runners)
        if "DANGER_TREND_DOWN_STRONG" in self.last_patterns:
            sr = self._session_range_pct()
            if sr < self.trend_strong_range_pct:
                self._full_reset_1m()
                return "1M RESET (trend failure strong)"
            else:
                if self._has_active_structure_1m():
                    self._full_reset_1m()
                    return f"1M RESET (trend down, range={sr:.1f}%)"
                return None

        if "DANGER_TREND_DOWN" in self.last_patterns:
            if self._has_active_structure_1m():
                self._full_reset_1m()
                return "1M RESET (trend down)"
            return None

        # Bearish engulfing on 1-min bars
        if len(self.bars_1m) >= 2:
            b_cur = self.bars_1m[-1]
            b_prev = self.bars_1m[-2]
            if is_bearish_engulfing(
                b_cur["o"], b_cur["h"], b_cur["l"], b_cur["c"],
                b_prev["o"], b_prev["h"], b_prev["l"], b_prev["c"],
            ):
                self._full_reset_1m()
                return "1M RESET (bearish engulfing)"

        # Topping wicky gate — only hard-reset when ALSO below EMA
        # (above EMA = normal runner volatility, don't block re-entry)
        if "TOPPING_WICKY" in self.last_patterns:
            if self.ema is not None and c >= self.ema:
                pass  # above EMA → tolerate the wick, let structure build
            else:
                self._full_reset_1m()
                return "1M RESET (topping wicky)"

        # --- Consecutive green tracking (extended move detection) ---
        if info["green"]:
            self.consecutive_green_1m += 1
        else:
            self.consecutive_green_1m = 0

        if self.consecutive_green_1m > self.max_green_1m:
            if self._has_active_structure_1m():
                self._full_reset_1m()
            return f"1M RESET (extended: {self.consecutive_green_1m} green candles)"

        # If already armed, keep waiting for trigger on live ticks
        if self.armed:
            return None

        # --- Entry mode branch ---
        if self.entry_mode == "direct":
            return self._direct_entry_check(vwap, macd_score)
        else:
            return self._pullback_entry_check(vwap, macd_score)

    def update_premarket_levels(self, premarket_high: Optional[float], premarket_bull_flag_high: Optional[float]):
        """Update premarket high and bull flag high from bar builder"""
        self.premarket_high = premarket_high
        self.premarket_bull_flag_high = premarket_bull_flag_high

    def on_trade_price(self, price: float, is_premarket: bool = False) -> Optional[str]:
        # MP suppress gate: detector still runs (EMA/state) but entries are blocked
        if os.getenv("WB_MP_SUPPRESS_ENTRIES", "0") == "1":
            return None
        # Check armed trade trigger (micro pullback only — gap-and-go removed)
        if self.armed and price >= self.armed.trigger_high:
            ms = self.macd_state.strength_score(price)
            msg = (
                f"ENTRY SIGNAL @ {self.armed.entry_price:.4f} "
                f"(break {self.armed.trigger_high:.4f}) "
                f"stop={self.armed.stop_low:.4f} R={self.armed.r:.4f} "
                f"score={self.armed.score:.1f} macd_score={ms:.1f} "
                f"tags={self._tags_str()} why={self.armed.score_detail}"
            )
            self._full_reset()
            return msg

        return None