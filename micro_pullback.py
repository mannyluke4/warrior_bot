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
    setup_type: str = "micro_pullback"  # "micro_pullback" or "gap_and_go"


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

        # Scoring knobs (env-driven, defaults safe)
        self.use_scoring = os.getenv("WB_USE_SCORING", "1") == "1"
        self.min_score = float(os.getenv("WB_MIN_SCORE", "6"))
        self.max_score = float(os.getenv("WB_MAX_SCORE", "99"))
        self.macd_hard_gate = os.getenv("WB_MACD_HARD_GATE", "1") == "1"

        # Gap and Go settings
        self.enable_gap_and_go = os.getenv("WB_ENABLE_GAP_AND_GO", "1") == "1"
        self.gap_and_go_min_score = float(os.getenv("WB_GAP_AND_GO_MIN_SCORE", "4"))

        # Exhaustion filter settings (prevents late entries on extended stocks)
        self.exhaustion_vwap_pct = float(os.getenv("WB_EXHAUSTION_VWAP_PCT", "10"))
        self.exhaustion_move_pct = float(os.getenv("WB_EXHAUSTION_MOVE_PCT", "50"))
        self.exhaustion_vol_ratio = float(os.getenv("WB_EXHAUSTION_VOL_RATIO", "0.4"))

        # Dynamic filter scaling (scales thresholds to session range for big runners)
        self.trend_strong_range_pct = float(os.getenv("WB_TREND_STRONG_RANGE_PCT", "5"))
        self.exhaustion_vwap_range_mult = float(os.getenv("WB_EXHAUSTION_VWAP_RANGE_MULT", "0.5"))
        self.exhaustion_move_range_mult = float(os.getenv("WB_EXHAUSTION_MOVE_RANGE_MULT", "1.5"))

        # L2 acceleration (active only when l2_state is provided)
        self.l2_accel_impulse = os.getenv("WB_L2_ACCEL_IMPULSE", "1") == "1"
        self.l2_accel_confirm = os.getenv("WB_L2_ACCEL_CONFIRM", "1") == "1"
        self.l2_hard_gate = os.getenv("WB_L2_HARD_GATE", "1") == "1"
        self.l2_min_bullish_for_accel = int(os.getenv("WB_L2_MIN_BULLISH_ACCEL", "3"))

        # Entry mode: "direct" = 1-bar entry, "pullback" = classic 3-bar cycle
        self.entry_mode = os.getenv("WB_ENTRY_MODE", "direct")

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

        # Gap and Go tracking
        self.premarket_high: Optional[float] = None
        self.premarket_bull_flag_high: Optional[float] = None
        # One-shot flag: Gap and Go fires once per session per symbol.
        # After the first signal is sent, this stays True for the rest of the day
        # to prevent the rapid-fire re-entry loop that occurs when TP fires immediately.
        self._gap_and_go_entered: bool = False

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

        # --- Conviction floor (trap stock filter) ---
        self.conviction_floor_enabled = os.getenv("WB_CONVICTION_FLOOR", "0") == "1"
        self.conviction_floor_min_score = float(os.getenv("WB_CONVICTION_FLOOR_MIN_SCORE", "6.0"))
        self.conviction_floor_min_gap_pct = float(os.getenv("WB_CONVICTION_FLOOR_MIN_GAP_PCT", "1.0"))
        self.conviction_floor_min_bars = int(os.getenv("WB_CONVICTION_FLOOR_MIN_BARS", "15"))
        self.gap_pct: float | None = None  # set by caller (simulate.py or bot.py)

        # --- Post-halt sizing override ---
        self.halt_sizing_enabled = os.getenv("WB_HALT_SIZING_OVERRIDE", "0") == "1"
        self.halt_range_multiplier = float(os.getenv("WB_HALT_RANGE_MULT", "5.0"))
        self.halt_stop_atr_mult = float(os.getenv("WB_HALT_STOP_ATR_MULT", "2.5"))
        self.halt_persist_bars = int(os.getenv("WB_HALT_PERSIST_BARS", "5"))
        self._bar_ranges_1m: deque = deque(maxlen=14)
        self._halt_active_bars: int = 0

        # --- Fast Mode (anticipation entry for fast movers) ---
        self.fast_mode_enabled = os.getenv("WB_FAST_MODE", "0") == "1"
        self.fast_mode_max_bar = int(os.getenv("WB_FAST_MODE_MAX_BAR", "30"))
        self.fast_mode_min_gap_pct = float(os.getenv("WB_FAST_MODE_MIN_GAP_PCT", "10.0"))
        self.fast_mode_min_green_bars = int(os.getenv("WB_FAST_MODE_MIN_GREEN_BARS", "3"))
        self.fast_mode_min_bars = int(os.getenv("WB_FAST_MODE_MIN_BARS", "10"))
        self.fast_mode_min_rel_vol = float(os.getenv("WB_FAST_MODE_MIN_REL_VOL", "2.0"))
        self.fast_mode_min_range_pct = float(os.getenv("WB_FAST_MODE_MIN_RANGE_PCT", "5.0"))
        self.fast_mode_entry_buffer_pct = float(os.getenv("WB_FAST_MODE_ENTRY_BUFFER_PCT", "0.3"))
        self.fast_mode_stop_mult = float(os.getenv("WB_FAST_MODE_STOP_MULT", "1.5"))
        self._fast_mode_fired = False  # one-shot per session

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
        self.armed = None

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

    def _fails_conviction_floor(self, score: float) -> tuple[bool, str]:
        """Block entries when ALL THREE: low score + no tags + tiny gap.
        Only active after enough bars for patterns to develop (timing gate).
        Returns (blocked, reason)."""
        if not self.conviction_floor_enabled:
            return False, ""
        if self.gap_pct is None:
            return False, ""  # no gap data = allow (conservative)
        # Timing gate: don't apply in first N bars — Profile A stocks enter
        # early when scores/tags are still building
        if len(self.bars_1m) < self.conviction_floor_min_bars:
            return False, ""
        if score >= self.conviction_floor_min_score:
            return False, ""
        if self.last_patterns:  # has pattern tags
            return False, ""
        if abs(self.gap_pct) >= self.conviction_floor_min_gap_pct:
            return False, ""
        return True, (
            f"conviction_floor: score={score:.1f}<{self.conviction_floor_min_score} "
            f"tags=[] gap={self.gap_pct:+.1f}%<±{self.conviction_floor_min_gap_pct}% "
            f"bars={len(self.bars_1m)}≥{self.conviction_floor_min_bars}"
        )

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

    def _check_fast_mode(self, c: float, vwap: float, macd_score: float) -> Optional[str]:
        """Anticipation entry for fast movers — fires before normal ARM.
        Targets stocks with large premarket gaps that are ramping with volume.
        One-shot per session. Returns ARM string if conditions met, None otherwise."""
        if not self.fast_mode_enabled or self._fast_mode_fired:
            return None
        if self.armed:
            return None  # normal ARM takes priority

        # Timing gate: only in first N bars of session
        bar_count = len(self.bars_1m)
        if bar_count > self.fast_mode_max_bar:
            return None

        _fm_debug = os.getenv("WB_FAST_MODE_DEBUG", "0") == "1"

        # Gap threshold
        if self.gap_pct is None or abs(self.gap_pct) < self.fast_mode_min_gap_pct:
            if _fm_debug: print(f"  FM_DBG bar={bar_count}: gap={self.gap_pct} < {self.fast_mode_min_gap_pct}", flush=True)
            return None

        # Session range threshold
        sr = self._session_range_pct()
        if sr < self.fast_mode_min_range_pct:
            if _fm_debug: print(f"  FM_DBG bar={bar_count}: range={sr:.1f}% < {self.fast_mode_min_range_pct}%", flush=True)
            return None

        # Need enough bars for volume comparison + green bar check
        if bar_count < max(self.fast_mode_min_bars, self.fast_mode_min_green_bars):
            if _fm_debug: print(f"  FM_DBG bar={bar_count}: need {max(self.fast_mode_min_bars, self.fast_mode_min_green_bars)} bars", flush=True)
            return None

        # Consecutive green bars check
        recent = list(self.bars_1m)[-self.fast_mode_min_green_bars:]
        if not all(b["c"] > b["o"] for b in recent):
            if _fm_debug:
                greens = ["G" if b["c"] > b["o"] else "R" for b in recent]
                print(f"  FM_DBG bar={bar_count}: green check FAIL {greens}", flush=True)
            return None

        # Relative volume surge: adaptive window (half recent vs half earlier)
        half = max(2, bar_count // 2)
        recent_vol = sum(b["v"] for b in list(self.bars_1m)[-half:])
        earlier_vol = sum(b["v"] for b in list(self.bars_1m)[:-half])
        if earlier_vol == 0:
            earlier_vol = recent_vol  # avoid div/zero, pass the check
        if recent_vol / earlier_vol < self.fast_mode_min_rel_vol:
            if _fm_debug: print(f"  FM_DBG bar={bar_count}: vol ratio={recent_vol/earlier_vol:.2f} < {self.fast_mode_min_rel_vol}", flush=True)
            return None

        # Must be above VWAP
        if vwap is None or c <= vwap:
            if _fm_debug: print(f"  FM_DBG bar={bar_count}: c={c:.2f} <= vwap={vwap}", flush=True)
            return None

        # Must be near or above premarket high (if available)
        if self.premarket_high and c < self.premarket_high * 0.99:
            return None

        # ---- All conditions met — fire anticipation entry ----
        self._fast_mode_fired = True  # one-shot

        entry = round(c * (1 + self.fast_mode_entry_buffer_pct / 100), 4)
        avg_range = sum(b["h"] - b["l"] for b in recent) / len(recent)
        stop = round(entry - (self.fast_mode_stop_mult * avg_range), 4)
        r = round(entry - stop, 4)
        if r <= 0:
            return None

        score = max(macd_score * 0.6, 4.0)
        detail = (
            f"fast_mode: gap={self.gap_pct:+.1f}% "
            f"range={self._session_range_pct():.1f}% "
            f"green={self.fast_mode_min_green_bars}"
        )

        self.armed = ArmedTrade(
            trigger_high=entry,
            stop_low=stop,
            entry_price=entry,
            r=r,
            score=score,
            score_detail=detail,
            setup_type="fast_mode",
        )

        return (
            f"ARMED entry={entry:.4f} stop={stop:.4f} R={r:.4f} "
            f"score={score:.1f} macd_score={macd_score:.1f} "
            f"tags={self._tags_str()} why={detail}"
        )

    def _tags_str(self) -> str:
        if not self.last_patterns:
            return "[]"
        return "[" + ", ".join(sorted(self.last_patterns)) + "]"

    def _session_range_pct(self) -> float:
        """Session range (high - low) / low * 100, from bars_1m."""
        if len(self.bars_1m) < 2:
            return 0.0
        hi = max(b["h"] for b in self.bars_1m)
        lo = min(b["l"] for b in self.bars_1m)
        if lo <= 0:
            return 0.0
        return (hi - lo) / lo * 100.0

    # -----------------------------
    # L2 helpers (backward compatible: no-ops when l2_state is None)
    # -----------------------------
    def _l2_bullish_strength(self, l2_state: Optional[dict]) -> int:
        """Count bullish L2 signals. Returns 0 when no L2 data."""
        if l2_state is None:
            return 0
        count = 0
        if l2_state.get("imbalance", 0.5) > 0.58:
            count += 1
        if l2_state.get("bid_stacking", False):
            count += 1
        if l2_state.get("ask_thinning", False):
            count += 1
        if l2_state.get("large_bid", False):
            count += 1
        if l2_state.get("imbalance_trend") == "rising":
            count += 1
        return count

    def _l2_is_bearish(self, l2_state: Optional[dict]) -> bool:
        """True when L2 shows strong selling pressure. False when no data.
        Conservative: only flags truly bearish conditions, not normal pullback noise."""
        if l2_state is None:
            return False
        imb = l2_state.get("imbalance", 0.5)
        # Strong bearish imbalance (sellers dominating)
        if imb < 0.30:
            return True
        # Large ask wall + weak imbalance (wall + no buyers)
        if l2_state.get("large_ask", False) and imb < 0.45:
            return True
        return False

    def check_l2_exit(self, l2_state: Optional[dict]) -> Optional[str]:
        """Check if L2 warrants an exit signal. Called by bot.py/simulate.py."""
        if l2_state is None:
            return None
        if l2_state.get("imbalance", 0.5) < 0.30:
            return "l2_bearish"
        if l2_state.get("large_ask", False) and l2_state.get("imbalance", 0.5) < 0.45:
            return "l2_ask_wall"
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

        # --- L2 signals (if available) ---
        l2 = getattr(self, "_last_l2_state", None)
        if l2 is not None:
            # Bullish L2 signals
            if l2["imbalance"] > 0.65:
                score += 2.0
                parts.append(f"l2_imbalance=+2({l2['imbalance']:.2f})")

            if l2["bid_stacking"]:
                score += 1.5
                parts.append("l2_bid_stack=+1.5")

            if l2["ask_thinning"]:
                score += 1.0
                parts.append("l2_thin_ask=+1")

            # Bearish L2 signals (penalties)
            if l2["imbalance"] < 0.35:
                score -= 3.0
                parts.append(f"l2_imbalance_bear=-3({l2['imbalance']:.2f})")

            if l2["large_ask"]:
                score -= 2.0
                parts.append("l2_ask_wall=-2")

            if l2["spread_pct"] > 1.0:
                score -= 2.0
                parts.append(f"l2_wide_spread=-2({l2['spread_pct']:.1f}%)")

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

            r = entry - stop_low
            if r <= 0:
                self._full_reset()
                return "RESET (invalid R)"

            if r < self.MIN_R:
                self._full_reset()
                return f"RESET (R too small: {r:.4f})"

            # ✅ REMOVE the old “30-bar bullish pattern hard gate”
            # ✅ Replace with scoring threshold (only influences arming)

            score, detail = self._score_setup(entry=entry, stop_low=stop_low, macd_score=macd_score)

            if self.use_scoring and (score < self.min_score or score > self.max_score):
                # Not a full reset — we just decline arming this trigger attempt.
                # But structure continues, so next bar can trigger again.
                tag = f"<{self.min_score:.1f}" if score < self.min_score else f">{self.max_score:.1f}"
                return f"NO_ARM score={score:.1f}{tag} macd={macd_score:.1f} tags={self._tags_str()} why={detail}"

            self.armed = ArmedTrade(
                trigger_high=trigger_high,
                stop_low=stop_low,
                entry_price=entry,
                r=r,
                score=score,
                score_detail=detail,
            )
            return (
                f"ARMED entry={entry:.4f} stop={stop_low:.4f} R={r:.4f} "
                f"score={score:.1f} macd_score={macd_score:.1f} tags={self._tags_str()} why={detail}"
            )

        return None

    # -----------------------------
    # DIRECT ENTRY (1-bar mode)
    # -----------------------------
    def _direct_entry_check(self, vwap: float, l2_state: Optional[dict], macd_score: float) -> Optional[str]:
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

        # Rising close (momentum) — waived by L2 acceleration
        rising = b1["c"] > b2["c"]
        if not rising:
            l2_strength = self._l2_bullish_strength(l2_state)
            if not (self.l2_accel_impulse and l2_strength >= self.l2_min_bullish_for_accel):
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

        # L2-enhanced stop (bid stacking)
        if l2_state is not None and l2_state.get("bid_stack_levels"):
            stack_prices = [p for p, _ in l2_state["bid_stack_levels"]]
            if stack_prices:
                highest_stack = max(stack_prices)
                if highest_stack > raw_stop and highest_stack < entry:
                    raw_stop = highest_stack

        stop_low = raw_stop - self.STOP_PAD

        # Post-halt sizing override: tighten stop for meaningful position sizing
        stop_low, halt_adjusted = self._halt_adjusted_stop(entry, stop_low)

        r = entry - stop_low
        if r <= 0:
            return "1M SKIP (invalid R)"
        if r < self.MIN_R:
            return f"1M SKIP (R too small: {r:.4f})"

        # --- Stale stock filter ---
        stale, stale_reason = self._is_stale_stock()
        if stale:
            return f"1M NO_ARM stale_stock: {stale_reason}"

        # --- LevelMap resistance gate ---
        if self.level_map is not None:
            blocked, block_reason = self.level_map.blocks_entry(entry, session_hod=self.session_hod_1m)
            if blocked:
                return f"1M NO_ARM level_gate: {block_reason}"

        # --- Scoring ---
        score, detail = self._score_setup(entry=entry, stop_low=stop_low, macd_score=macd_score)

        # Conviction floor (trap stock filter) — SKIP, don't reset state machine
        blocked, block_reason = self._fails_conviction_floor(score)
        if blocked:
            return f"1M SKIP {block_reason}"

        # --- Exhaustion filters (dynamic: scale thresholds to session range) ---
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

        # L2 hard gate
        if self.l2_hard_gate and self._l2_is_bearish(l2_state):
            imb = l2_state.get("imbalance", 0) if l2_state else 0
            return f"1M NO_ARM L2_bearish imbalance={imb:.2f}"

        # Score gate
        if self.use_scoring and (score < self.min_score or score > self.max_score):
            tag = f"<{self.min_score:.1f}" if score < self.min_score else f">{self.max_score:.1f}"
            return (
                f"1M NO_ARM score={score:.1f}{tag} "
                f"macd={macd_score:.1f} tags={self._tags_str()} why={detail}"
            )

        # --- ARM ---
        self.armed = ArmedTrade(
            trigger_high=entry,
            stop_low=stop_low,
            entry_price=entry,
            r=r,
            score=score,
            score_detail=detail,
        )
        return (
            f"ARMED entry={entry:.4f} stop={stop_low:.4f} R={r:.4f} "
            f"score={score:.1f} macd_score={macd_score:.1f} tags={self._tags_str()} why={detail}"
        )

    # -----------------------------
    # PULLBACK ENTRY (classic 3-bar cycle)
    # -----------------------------
    def _pullback_entry_check(self, vwap: float, l2_state: Optional[dict], macd_score: float) -> Optional[str]:
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
            l2_strength = self._l2_bullish_strength(l2_state)

            is_impulse = (
                b1["green"]
                and above_ema
                and above_vwap
                and b1["c"] > b2["c"]
                and not is_shooting_star(b1["o"], b1["h"], b1["l"], b1["c"])
            )

            l2_accel = False
            if (not is_impulse
                and self.l2_accel_impulse
                and l2_strength >= self.l2_min_bullish_for_accel):
                if (b1["green"] and above_ema and above_vwap
                    and not is_shooting_star(b1["o"], b1["h"], b1["l"], b1["c"])):
                    is_impulse = True
                    l2_accel = True

            if is_impulse:
                self.in_impulse_1m = True
                self.pullback_count_1m = 0
                self.pullback_low_1m = None
                accel_tag = " (L2-accelerated)" if l2_accel else ""
                return f"1M IMPULSE detected{accel_tag}"
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

            if self.pullback_count_1m > self.max_pullback_bars:
                self._full_reset_1m()
                return "1M RESET (pullback too long)"

            if self.l2_hard_gate and self._l2_is_bearish(l2_state):
                self._full_reset_1m()
                return "1M RESET (L2 bearish during pullback)"

            return f"1M PULLBACK {self.pullback_count_1m}/{self.max_pullback_bars}"

        # CONFIRMATION: green bar after at least 1 pullback bar → ARM
        if self.pullback_count_1m >= 1 and b1["green"]:

            if self.macd_hard_gate and (not self.macd_state.bullish()):
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

            if self.l2_accel_confirm and not trigger_ok and not bad_trigger:
                if self._l2_bullish_strength(l2_state) >= self.l2_min_bullish_for_accel:
                    trigger_ok = True

            if (not trigger_ok) or bad_trigger:
                self._full_reset_1m()
                return "1M RESET (weak trigger candle)"

            trigger_high = b1["h"]
            entry = trigger_high

            raw_stop = self.pullback_low_1m if self.pullback_low_1m is not None else b1["l"]

            if l2_state is not None and l2_state.get("bid_stack_levels"):
                stack_prices = [p for p, _ in l2_state["bid_stack_levels"]]
                if stack_prices:
                    highest_stack = max(stack_prices)
                    if highest_stack > raw_stop and highest_stack < b1["h"]:
                        raw_stop = highest_stack

            stop_low = raw_stop - self.STOP_PAD

            # Post-halt sizing override: tighten stop for meaningful position sizing
            stop_low, halt_adjusted = self._halt_adjusted_stop(entry, stop_low)

            r = entry - stop_low
            if r <= 0:
                self._full_reset_1m()
                return "1M RESET (invalid R)"

            if r < self.MIN_R:
                self._full_reset_1m()
                return f"1M RESET (R too small: {r:.4f})"

            # Stale stock filter
            stale, stale_reason = self._is_stale_stock()
            if stale:
                self._full_reset_1m()
                return f"1M NO_ARM stale_stock: {stale_reason}"

            # LevelMap resistance gate
            if self.level_map is not None:
                blocked, block_reason = self.level_map.blocks_entry(entry, session_hod=self.session_hod_1m)
                if blocked:
                    self._full_reset_1m()
                    return f"1M NO_ARM level_gate: {block_reason}"

            score, detail = self._score_setup(entry=entry, stop_low=stop_low, macd_score=macd_score)

            # Conviction floor (trap stock filter) — SKIP, don't reset state machine
            blocked, block_reason = self._fails_conviction_floor(score)
            if blocked:
                return f"1M SKIP {block_reason}"

            # Exhaustion filters (dynamic: scale thresholds to session range)
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

            if self.l2_hard_gate and self._l2_is_bearish(l2_state):
                self._full_reset_1m()
                imb = l2_state.get("imbalance", 0) if l2_state else 0
                return f"1M NO_ARM L2_bearish imbalance={imb:.2f}"

            if self.use_scoring and (score < self.min_score or score > self.max_score):
                tag = f"<{self.min_score:.1f}" if score < self.min_score else f">{self.max_score:.1f}"
                return f"1M NO_ARM score={score:.1f}{tag} macd={macd_score:.1f} tags={self._tags_str()} why={detail}"

            self.armed = ArmedTrade(
                trigger_high=trigger_high,
                stop_low=stop_low,
                entry_price=entry,
                r=r,
                score=score,
                score_detail=detail,
            )
            return (
                f"ARMED entry={entry:.4f} stop={stop_low:.4f} R={r:.4f} "
                f"score={score:.1f} macd_score={macd_score:.1f} tags={self._tags_str()} why={detail}"
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

        l2_state: optional Level 2 order book state from L2SignalDetector.get_state()
        """
        o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume

        # Store L2 state for use in scoring
        self._last_l2_state = l2_state

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

        above_vwap = c >= vwap
        above_ema = c >= self.ema

        # --- Guard checks ---

        # VWAP loss clears structure
        if not above_vwap:
            if self._has_active_structure_1m():
                self._full_reset_1m()
                return "1M RESET (lost VWAP)"
            return None

        # MACD bearish cross resets structure
        if self.macd_state.bearish_cross():
            if self._has_active_structure_1m():
                self._full_reset_1m()
                return "1M RESET (MACD bearish cross)"
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

        # --- Fast Mode: anticipation entry for fast movers ---
        if self.fast_mode_enabled and not self._fast_mode_fired and not self.armed:
            fast_msg = self._check_fast_mode(c, vwap, macd_score)
            if fast_msg:
                return fast_msg

        # If already armed, keep waiting for trigger on live ticks
        if self.armed:
            return None

        # --- Entry mode branch ---
        if self.entry_mode == "direct":
            return self._direct_entry_check(vwap, l2_state, macd_score)
        else:
            return self._pullback_entry_check(vwap, l2_state, macd_score)

    def update_premarket_levels(self, premarket_high: Optional[float], premarket_bull_flag_high: Optional[float]):
        """Update premarket high and bull flag high from bar builder"""
        self.premarket_high = premarket_high
        self.premarket_bull_flag_high = premarket_bull_flag_high

    def on_trade_price(self, price: float, is_premarket: bool = False) -> Optional[str]:
        # 1) Check Gap and Go entry (premarket high break) - only during market hours
        # During premarket, pm_high updates continuously so this would fire on every new high (false signals)
        # _gap_and_go_entered is a one-shot flag: once the signal fires, it never fires again this session.
        # Without this, _full_reset() clears .armed and the signal re-fires on every subsequent tick.
        if not is_premarket and self.enable_gap_and_go and self.premarket_high is not None and price > 0 and not self._gap_and_go_entered:
            # Use premarket bull flag high if available, otherwise premarket high
            pm_trigger = self.premarket_bull_flag_high if self.premarket_bull_flag_high else self.premarket_high

            # Check if price is breaking above premarket level
            if price >= pm_trigger and not self.armed:
                # Block if stock is in a downtrend — same rule as on_bar_close
                current_patterns = set(self.last_patterns or [])
                if "DANGER_TREND_DOWN" in current_patterns:
                    return None
                if "DANGER_TREND_DOWN_STRONG" in current_patterns:
                    sr = self._session_range_pct()
                    if sr < self.trend_strong_range_pct:
                        return None

                # Quick validation: need EMA and basic momentum
                if self.ema is not None and price >= self.ema:
                    # Calculate stop and R
                    # For Gap and Go, stop is typically below premarket consolidation
                    # Use a conservative stop: 2% below premarket high or $0.10, whichever is larger
                    stop_offset = max(0.10, pm_trigger * 0.02)
                    stop_low = pm_trigger - stop_offset
                    r = pm_trigger - stop_low

                    if r >= self.MIN_R:
                        macd_score = self.macd_state.strength_score(price)
                        score, detail = self._score_gap_and_go(pm_trigger, stop_low, macd_score)

                        # Lower threshold for Gap and Go (it's a simpler, cleaner setup)
                        if not self.use_scoring or score >= self.gap_and_go_min_score:
                            # Arm Gap and Go setup
                            self.armed = ArmedTrade(
                                trigger_high=pm_trigger,
                                stop_low=stop_low,
                                entry_price=pm_trigger,
                                r=r,
                                score=score,
                                score_detail=detail,
                                setup_type="gap_and_go"
                            )

                            pm_type = "PM_BULL_FLAG" if self.premarket_bull_flag_high else "PM_HIGH"
                            msg = (
                                f"GAP_AND_GO ENTRY @ {pm_trigger:.4f} "
                                f"(break {pm_type}) "
                                f"stop={stop_low:.4f} R={r:.4f} "
                                f"score={score:.1f} macd_score={macd_score:.1f} "
                                f"tags={self._tags_str()} why={detail}"
                            )
                            # Set one-shot flag BEFORE reset so it survives _full_reset()
                            self._gap_and_go_entered = True
                            self._full_reset()
                            return msg

        # 2) Check existing armed trade (micro pullback or gap and go)
        if self.armed and price >= self.armed.trigger_high:
            ms = self.macd_state.strength_score(price)
            setup_label = "GAP_AND_GO" if self.armed.setup_type == "gap_and_go" else "ENTRY SIGNAL"
            msg = (
                f"{setup_label} @ {self.armed.entry_price:.4f} "
                f"(break {self.armed.trigger_high:.4f}) "
                f"stop={self.armed.stop_low:.4f} R={self.armed.r:.4f} "
                f"score={self.armed.score:.1f} macd_score={ms:.1f} "
                f"tags={self._tags_str()} why={self.armed.score_detail}"
            )
            self._full_reset()
            return msg

        return None

    def _score_gap_and_go(self, entry: float, stop_low: float, macd_score: float) -> tuple[float, str]:
        """
        Score Gap and Go setup. Generally more permissive than micro pullback.
        Returns (score, detail_str).
        """
        score = 0.0
        parts: list[str] = []

        # MACD strength (lighter weight for Gap and Go)
        score += 0.4 * macd_score
        parts.append(f"macd={macd_score:.1f}*0.4")

        # Pattern tags
        tags = set(self.last_patterns or [])

        if "BULL_FLAG" in tags or "FLAT_TOP" in tags:
            score += 4.0
            parts.append("bull_struct=+4")

        if "VOLUME_SURGE" in tags:
            score += 2.5
            parts.append("vol_surge=+2.5")

        if "RED_TO_GREEN" in tags:
            score += 2.0
            parts.append("r2g=+2")

        if "WHOLE_DOLLAR_NEARBY" in tags:
            score += 1.0
            parts.append("whole=+1")

        # Penalties
        if "LOW_LIQUIDITY" in tags:
            score -= 2.5
            parts.append("lowliq=-2.5")

        # R quality
        r = entry - stop_low
        if r >= 0.10:
            score += 1.5
            parts.append("R>=0.10=+1.5")
        elif r >= 0.05:
            score += 0.8
            parts.append("R>=0.05=+0.8")

        detail = ";".join(parts)
        return score, detail