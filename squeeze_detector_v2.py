"""Squeeze Detector V2 — Candle-intelligent breakout detection.

V2 adds candle intelligence to V1's proven mechanical squeeze detector:
  - Candle-over-candle hard gate at PRIMED transition
  - Doji/exhaustion gate before ARM
  - Intra-bar level break while PRIMED (Option A)
  - Self-contained exit logic via check_exit()

V1 (squeeze_detector.py) is FROZEN. V2 is a separate drop-in replacement.
Switch via WB_SQUEEZE_VERSION=2.

All V2-specific features gated by WB_SQV2_* env vars.
"""

from __future__ import annotations

import math
import os
from collections import deque
from typing import Deque, Optional

from micro_pullback import ArmedTrade, ema_next
from candles import is_doji, is_shooting_star, is_bearish_engulfing
from patterns import PatternDetector


class SqueezeDetectorV2:
    """IDLE → PRIMED → ARMED → TRIGGERED state machine with candle intelligence."""

    def __init__(self):
        # --- Master gate ---
        self.enabled = os.getenv("WB_SQUEEZE_ENABLED", "0") == "1"

        # --- V1 detection thresholds (inherited) ---
        self.vol_mult = float(os.getenv("WB_SQ_VOL_MULT", "3.0"))
        self.min_bar_vol = int(os.getenv("WB_SQ_MIN_BAR_VOL", "50000"))
        self.min_body_pct = float(os.getenv("WB_SQ_MIN_BODY_PCT", "1.5"))
        self.prime_bars = int(os.getenv("WB_SQ_PRIME_BARS", "3"))
        self.max_r = float(os.getenv("WB_SQ_MAX_R", "0.80"))
        self.level_priority = os.getenv("WB_SQ_LEVEL_PRIORITY", "pm_high,whole_dollar,pdh").split(",")
        self.pm_confidence = os.getenv("WB_SQ_PM_CONFIDENCE", "1") == "1"
        self.max_attempts = int(os.getenv("WB_SQ_MAX_ATTEMPTS", "3"))
        self.probe_size_mult = float(os.getenv("WB_SQ_PROBE_SIZE_MULT", "0.5"))

        # --- Parabolic mode (V1) ---
        self.para_enabled = os.getenv("WB_SQ_PARA_ENABLED", "1") == "1"
        self.para_stop_offset = float(os.getenv("WB_SQ_PARA_STOP_OFFSET", "0.10"))
        self.para_trail_r = float(os.getenv("WB_SQ_PARA_TRAIL_R", "1.0"))

        # --- HOD gate (V1) ---
        self.new_hod_required = os.getenv("WB_SQ_NEW_HOD_REQUIRED", "1") == "1"
        self.pm_hod_gate = os.getenv("WB_SQ_PM_HOD_GATE", "0") == "1"

        # --- V2 Entry features ---
        self.coc_required = os.getenv("WB_SQV2_COC_REQUIRED", "1") == "1"
        self.exhaustion_gate = os.getenv("WB_SQV2_EXHAUSTION_GATE", "1") == "1"
        self.intrabar_arm = os.getenv("WB_SQV2_INTRABAR_ARM", "1") == "1"
        self.trend_required = os.getenv("WB_SQV2_TREND_REQUIRED", "0") == "1"
        self.rolling_hod = os.getenv("WB_SQV2_ROLLING_HOD", "1") == "1"

        # --- V2 Exit features ---
        self.candle_exits = os.getenv("WB_SQV2_CANDLE_EXITS", "1") == "1"
        self.cuc_exit = os.getenv("WB_SQV2_CUC_EXIT", "0") == "1"
        self.intrabar_shape = os.getenv("WB_SQV2_INTRABAR_SHAPE", "0") == "1"

        # --- Candle Exit V2: tiered 1m exits with volume confirmation ---
        self._candle_exit_v2 = os.getenv("WB_SQV2_CANDLE_EXIT_V2", "0") == "1"
        self._target_is_exit = os.getenv("WB_SQV2_TARGET_IS_EXIT", "0") == "1"
        self._t1_min_bars = int(os.getenv("WB_SQV2_T1_MIN_BARS", "2"))
        self._t1_threshold = float(os.getenv("WB_SQV2_T1_THRESHOLD_R", "1.0"))
        self._t3_threshold = float(os.getenv("WB_SQV2_T2_THRESHOLD_R", "3.0"))
        self._t2_vol_mult = float(os.getenv("WB_SQV2_T2_VOL_MULT", "1.5"))

        # --- V2 Exit params (from .env, same as V1 candle exits) ---
        self._tw_grace_min = int(os.getenv("WB_TOPPING_WICKY_GRACE_MIN", "3"))
        self._tw_min_profit_r = float(os.getenv("WB_TW_MIN_PROFIT_R", "1.5"))
        self._be_grace_min = int(os.getenv("WB_BE_GRACE_MIN", "0"))
        self._be_parabolic_grace = os.getenv("WB_BE_PARABOLIC_GRACE", "1") == "1"
        self._be_grace_min_r = float(os.getenv("WB_BE_GRACE_MIN_R", "1.0"))
        self._be_grace_min_new_highs = int(os.getenv("WB_BE_GRACE_MIN_NEW_HIGHS", "3"))
        self._be_grace_lookback = int(os.getenv("WB_BE_GRACE_LOOKBACK_BARS", "6"))

        # --- V2 Mechanical exit params (V1 parity) ---
        self._sq_target_r = float(os.getenv("WB_SQ_TARGET_R", "2.0"))
        self._sq_trail_r = float(os.getenv("WB_SQ_TRAIL_R", "1.5"))
        self._sq_para_trail_r = float(os.getenv("WB_SQ_PARA_TRAIL_R", "1.0"))
        self._sq_runner_trail_r = float(os.getenv("WB_SQ_RUNNER_TRAIL_R", "2.5"))
        self._sq_max_loss_dollars = float(os.getenv("WB_SQ_MAX_LOSS_DOLLARS", "500"))
        self._sq_core_pct = int(os.getenv("WB_SQ_CORE_PCT", "75"))

        # --- L2 placeholders — DEFERRED to Phase 2 ---
        # WB_SQV2_L2_EXIT=0
        # WB_SQV2_L2_CONFIRM=0
        # WB_SQV2_L2_MIN_FLOAT_M=5

        # --- State ---
        self.symbol: str = ""
        self.armed: Optional[ArmedTrade] = None
        self.ema: Optional[float] = None
        self._ema_len = 9

        self._state = "IDLE"  # IDLE, PRIMED, ARMED
        self._primed_bars_left = 0
        self._primed_bar: Optional[dict] = None
        self._session_hod: float = 0.0
        self._exhaustion_delay: bool = False  # True = doji/star blocked ARM, need fresh bar

        # --- Bar history ---
        self.bars_1m: Deque[dict] = deque(maxlen=50)

        # --- Premarket levels ---
        self.premarket_high: Optional[float] = None
        self.premarket_bull_flag_high: Optional[float] = None
        self.prior_day_high: Optional[float] = None

        # --- Per-stock session tracking ---
        self._attempts = 0
        self._has_winner = False
        self._in_trade = False

        # --- Gap data (set by caller) ---
        self.gap_pct: Optional[float] = None

        # --- V2 Exit state (managed internally) ---
        self._trade_entry: Optional[float] = None
        self._trade_stop: Optional[float] = None
        self._trade_r: Optional[float] = None
        self._trade_qty: Optional[int] = None
        self._trade_peak: float = 0.0
        self._trade_tp_hit: bool = False
        self._trade_runner_stop: float = 0.0
        self._trade_entry_time: Optional[str] = None  # "HH:MM" ET
        self._trade_is_parabolic: bool = False
        self._pattern_det_10s = PatternDetector()
        self._prev_10s_bar: Optional[dict] = None
        self._recent_10s_highs: list = []
        self._prev_1m_bar: Optional[dict] = None

        # --- Candle Exit V2 state ---
        self._exit_vol_history: list = []
        self._session_max_vol: float = 0
        self._tight_trail_price: Optional[float] = None
        self._bars_in_trade: int = 0
        self._prior_1m_exit_bar: Optional[dict] = None  # {o, h, l, c, v}

        # --- MACD state (V1 compat — V1 uses it for gating in sim) ---
        self.macd_state = type('obj', (object,), {'histogram': None})()

    # ------------------------------------------------------------------
    # Seed (warm up indicators — no signals)
    # ------------------------------------------------------------------
    def seed_bar_close(self, o: float, h: float, l: float, c: float, v: float):
        self.ema = ema_next(self.ema, c, self._ema_len)
        if h > self._session_hod:
            self._session_hod = h
        info = {"o": o, "h": h, "l": l, "c": c, "v": v, "green": c >= o}
        self.bars_1m.append(info)

    # ------------------------------------------------------------------
    # Primary detection on 1m bar closes
    # ------------------------------------------------------------------
    def on_bar_close_1m(self, bar, vwap: Optional[float] = None) -> Optional[str]:
        if not self.enabled:
            return None

        o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume

        # Update EMA and HOD
        self.ema = ema_next(self.ema, c, self._ema_len)
        if h > self._session_hod:
            self._session_hod = h

        info = {"o": o, "h": h, "l": l, "c": c, "v": v, "green": c >= o}
        self.bars_1m.append(info)

        # Track prev 1m bar for CUC exit
        prev_1m = self._prev_1m_bar
        self._prev_1m_bar = dict(info)

        # Don't detect while in a trade
        if self._in_trade:
            return None

        # If already ARMED, just wait for tick trigger
        if self._state == "ARMED":
            return None

        # --- PRIMED state: waiting for level break ---
        if self._state == "PRIMED":
            self._primed_bars_left -= 1

            # Exhaustion delay: if previous bar was doji/star, need fresh momentum
            if self._exhaustion_delay:
                if not info["green"]:
                    # Next bar bearish — reset
                    self._reset("exhaustion_confirmed")
                    return f"SQ_RESET: exhaustion_confirmed (doji/star followed by red bar)"
                else:
                    # Fresh green bar — clear delay, continue
                    self._exhaustion_delay = False

            # Check for reset conditions
            if vwap is not None and c < vwap:
                self._reset("vwap_lost")
                return f"SQ_RESET: vwap_lost (close={c:.4f} < vwap={vwap:.4f})"

            if self._primed_bars_left <= 0:
                self._reset("prime_expired")
                return f"SQ_RESET: prime_expired ({self.prime_bars} bars elapsed)"

            # 1B: Doji/exhaustion gate — if this bar is doji/star, delay ARM
            if self.exhaustion_gate and (is_doji(o, h, l, c) or is_shooting_star(o, h, l, c)):
                self._exhaustion_delay = True
                return f"SQ_EXHAUST_DELAY: doji/star detected, need fresh bar (o={o:.4f} h={h:.4f} l={l:.4f} c={c:.4f})"

            # Check for level break
            level_name, level_price = self._find_broken_level(h)
            if level_name is not None:
                return self._try_arm(level_name, level_price, info, vwap)

            return None

        # --- IDLE state: look for volume explosion ---
        if len(self.bars_1m) < 3:
            return None

        if vwap is None:
            return None

        # Volume check
        avg_vol = self._avg_prior_vol()
        if avg_vol <= 0:
            return None

        vol_ratio = v / avg_vol
        if vol_ratio < self.vol_mult:
            return None
        if v < self.min_bar_vol:
            return None

        # Price above VWAP
        if c < vwap:
            return None

        # Green bar with significant body
        if not info["green"]:
            return None
        body = abs(c - o)
        if o > 0 and (body / o) * 100 < self.min_body_pct:
            return None

        # Max attempts check
        if self._attempts >= self.max_attempts:
            return f"SQ_NO_ARM: max_attempts ({self._attempts}/{self.max_attempts})"

        # 1A: Candle-over-candle hard gate
        if self.coc_required and len(self.bars_1m) >= 2:
            prior_bar = self.bars_1m[-2]
            if h <= prior_bar["h"]:
                return (
                    f"SQ_REJECT: no_candle_over_candle "
                    f"(bar_high=${h:.4f} <= prior_high=${prior_bar['h']:.4f})"
                )

        # HOD gate: bar must be at or making new highs
        if self.new_hod_required:
            if self.pm_hod_gate and self.premarket_high is not None and self.premarket_high > 0:
                if h < self.premarket_high:
                    return (
                        f"SQ_REJECT: not_above_pm_high (bar_high=${h:.4f} < PM_HIGH=${self.premarket_high:.4f})"
                    )
            elif self._session_hod > 0:
                if self.rolling_hod:
                    # V2 rolling HOD: only consider bars still in deque (avoids stale seed-bar spikes)
                    hod_threshold = max(b["h"] for b in list(self.bars_1m)[:-1]) if len(self.bars_1m) > 1 else 0.0
                else:
                    # V1 cumulative HOD: session_hod includes all bars ever seen
                    hod_threshold = self._session_hod
                if h < hod_threshold:
                    return (
                        f"SQ_REJECT: not_new_hod (bar_high=${h:.4f} < HOD=${hod_threshold:.4f})"
                    )

        # --- Transition to PRIMED ---
        self._state = "PRIMED"
        self._primed_bars_left = self.prime_bars
        self._primed_bar = dict(info)
        self._exhaustion_delay = False

        prime_msg = (
            f"SQ_PRIMED: vol={vol_ratio:.1f}x avg, bar_vol={v:,.0f}, "
            f"price=${c:.4f} above VWAP (${vwap:.4f})"
        )

        # Check if level already broken on this bar (same-bar PRIMED+ARMED)
        # This handles fast movers where the volume explosion IS the level break,
        # AND stocks that gapped above PM high before the volume bar fired.
        level_name, level_price = self._find_broken_level(h)
        if level_name is not None:
            arm_msg = self._try_arm(level_name, level_price, info, vwap)
            if arm_msg:
                return f"{prime_msg}\n  {arm_msg}"
            # _try_arm failed (likely R too large) — log it but stay PRIMED
            return prime_msg

        return prime_msg

    # ------------------------------------------------------------------
    # Tick trigger check (V2: also does intra-bar ARM while PRIMED)
    # ------------------------------------------------------------------
    def on_trade_price(self, price: float, is_premarket: bool = False) -> Optional[str]:
        if not self.enabled:
            return None

        # 1C: Intra-bar level break while PRIMED (Option A)
        if self.intrabar_arm and self._state == "PRIMED" and not self._exhaustion_delay:
            level_name, level_price = self._find_broken_level(price)
            if level_name is not None:
                # Use the primed bar for stop calc and scoring
                bar_for_arm = self._primed_bar or (self.bars_1m[-1] if self.bars_1m else None)
                if bar_for_arm:
                    return self._try_arm(level_name, level_price, bar_for_arm, vwap=None)

        # ARMED: check trigger
        if self.armed is not None:
            if price >= self.armed.trigger_high:
                msg = (
                    f"ENTRY SIGNAL @ {self.armed.entry_price:.4f} "
                    f"(break {self.armed.trigger_high:.4f}) "
                    f"stop={self.armed.stop_low:.4f} R={self.armed.r:.4f} "
                    f"score={self.armed.score:.1f} "
                    f"setup_type=squeeze why={self.armed.score_detail}"
                )
                self.armed = None
                self._state = "IDLE"
                self._attempts += 1
                return msg

        return None

    # ------------------------------------------------------------------
    # V2 Exit: check_exit() — called on every tick and on bar close
    # ------------------------------------------------------------------
    def check_exit(self, price: float, qty: int,
                   bar_10s=None, bar_1m=None,
                   time_str: Optional[str] = None) -> Optional[str]:
        """Self-contained exit logic. Returns exit reason or None.

        Called by bot/sim on every tick (price only) and on bar close (with bar).
        The caller handles the actual order placement.
        """
        if not self._in_trade or self._trade_entry is None:
            return None

        entry = self._trade_entry
        stop = self._trade_stop
        r = self._trade_r
        if r is None or r <= 0:
            r = 0.01  # safety

        # Update peak
        if price > self._trade_peak:
            self._trade_peak = price
            # New high clears any tight trail warning
            if self._tight_trail_price is not None:
                self._tight_trail_price = None

        # ── Tight trail check (Candle Exit V2 warning trail) ──
        if self._candle_exit_v2 and self._tight_trail_price is not None:
            if price < self._tight_trail_price:
                self._tight_trail_price = None
                return "candle_warning_trail"

        # ── 0) Dollar loss cap ──
        if self._sq_max_loss_dollars > 0:
            unrealized_loss = (entry - price) * qty
            if unrealized_loss >= self._sq_max_loss_dollars:
                return f"sq_dollar_loss_cap (${unrealized_loss:,.0f})"

        # ── 1) Hard stop ──
        if price <= stop:
            return "sq_stop_hit"

        # ── Pre-target phase ──
        if not self._trade_tp_hit:
            # 2) Trailing stop
            trail_r = self._sq_para_trail_r if self._trade_is_parabolic else self._sq_trail_r
            trail_price = self._trade_peak - (trail_r * r)
            if price <= trail_price:
                return "sq_para_trail_exit" if self._trade_is_parabolic else "sq_trail_exit"

            # 3) Target hit
            if price >= entry + (self._sq_target_r * r):
                self._trade_tp_hit = True
                self._trade_runner_stop = max(stop, entry + 0.01)
                # Candle Exit V2: target is a tier promotion, not an exit
                if self._candle_exit_v2 and not self._target_is_exit:
                    pass  # Stay in trade, Tier 3 candle exits manage the exit
                else:
                    return "sq_target_hit"

        # ── Post-target (runner) ──
        if self._trade_tp_hit:
            runner_trail = self._trade_peak - (self._sq_runner_trail_r * r)
            runner_stop = max(self._trade_runner_stop, runner_trail)
            if price <= runner_stop:
                return "sq_runner_trail"

        # ── Candle Exit V2: tiered 1m exits (replaces 10s exits when active) ──
        if self._candle_exit_v2 and bar_1m is not None:
            unrealized_r = (price - entry) / r if r > 0 else 0
            reason = self._check_candle_exit_v2(bar_1m, unrealized_r)
            if reason:
                return reason
        elif not self._candle_exit_v2:
            # Legacy: 10s candle exits
            if self.candle_exits and bar_10s is not None:
                reason = self._check_candle_exit_10s(bar_10s, time_str)
                if reason:
                    return reason
            # Legacy: CUC exit on 1m bar close
            if self.cuc_exit and bar_1m is not None and self._trade_tp_hit:
                if self._prev_1m_bar is not None and bar_1m.low < self._prev_1m_bar["l"]:
                    return "sq_candle_under_candle_exit"

        return None

    def _check_candle_exit_10s(self, bar, time_str: Optional[str]) -> Optional[str]:
        """Check 10s bar for topping wicky and bearish engulfing exits."""
        o, h, l, c = bar.open, bar.high, bar.low, bar.close
        v = bar.volume if hasattr(bar, 'volume') else 0

        # Feed pattern detector
        signals = self._pattern_det_10s.update(o, h, l, c, v)
        signal_names = [s.name for s in signals]

        prev = self._prev_10s_bar
        self._prev_10s_bar = {"o": o, "h": h, "l": l, "c": c}

        # Track highs for parabolic grace
        self._recent_10s_highs.append(h)
        if len(self._recent_10s_highs) > self._be_grace_lookback + 5:
            self._recent_10s_highs = self._recent_10s_highs[-(self._be_grace_lookback + 5):]

        entry = self._trade_entry
        r = self._trade_r or 0.01

        # ── Topping Wicky ──
        if "TOPPING_WICKY" in signal_names:
            if not self._in_tw_grace(time_str):
                # Profit gate: suppress on confirmed runners
                tw_ok = True
                if self._tw_min_profit_r > 0 and r > 0:
                    unrealized = c - entry
                    if unrealized >= self._tw_min_profit_r * r:
                        tw_ok = False
                if tw_ok:
                    return "topping_wicky_exit"

        # ── Bearish Engulfing ──
        if prev is not None:
            if is_bearish_engulfing(o, h, l, c, prev["o"], prev["h"], prev["l"], prev["c"]):
                if not self._in_be_grace(time_str) and not self._in_parabolic_grace(c):
                    return "bearish_engulfing_exit"

        return None

    def _in_tw_grace(self, time_str: Optional[str]) -> bool:
        if self._tw_grace_min <= 0 or time_str is None or self._trade_entry_time is None:
            return False
        try:
            entry_parts = self._trade_entry_time.split(":")
            now_parts = time_str.split(":")
            entry_min = int(entry_parts[0]) * 60 + int(entry_parts[1])
            now_min = int(now_parts[0]) * 60 + int(now_parts[1])
            return (now_min - entry_min) < self._tw_grace_min
        except (ValueError, IndexError):
            return False

    def _in_be_grace(self, time_str: Optional[str]) -> bool:
        if self._be_grace_min <= 0 or time_str is None or self._trade_entry_time is None:
            return False
        try:
            entry_parts = self._trade_entry_time.split(":")
            now_parts = time_str.split(":")
            entry_min = int(entry_parts[0]) * 60 + int(entry_parts[1])
            now_min = int(now_parts[0]) * 60 + int(now_parts[1])
            return (now_min - entry_min) < self._be_grace_min
        except (ValueError, IndexError):
            return False

    def _in_parabolic_grace(self, bar_close: float) -> bool:
        if not self._be_parabolic_grace:
            return False
        if self._trade_entry is None or self._trade_r is None or self._trade_r <= 0:
            return False
        if bar_close < self._trade_entry + (self._be_grace_min_r * self._trade_r):
            return False
        highs = self._recent_10s_highs
        if len(highs) < 2:
            return False
        window = highs[-self._be_grace_lookback:]
        new_high_count = 0
        running = window[0]
        for bh in window[1:]:
            if bh > running:
                new_high_count += 1
                running = bh
        return new_high_count >= self._be_grace_min_new_highs

    # ------------------------------------------------------------------
    # Trade lifecycle — V2 manages its own exit state
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Candle Exit V2: tiered 1m exits with volume confirmation
    # ------------------------------------------------------------------
    def on_1m_bar_close_exit(self, bar_1m):
        """Called on every 1m bar close while in trade. Updates exit state."""
        if not self._in_trade or bar_1m is None:
            return
        o = bar_1m.open if hasattr(bar_1m, 'open') else bar_1m.get("o", 0)
        h = bar_1m.high if hasattr(bar_1m, 'high') else bar_1m.get("h", 0)
        l = bar_1m.low if hasattr(bar_1m, 'low') else bar_1m.get("l", 0)
        c = bar_1m.close if hasattr(bar_1m, 'close') else bar_1m.get("c", 0)
        v = bar_1m.volume if hasattr(bar_1m, 'volume') else bar_1m.get("v", 0)
        self._bars_in_trade += 1
        self._exit_vol_history.append(v)
        if len(self._exit_vol_history) > 10:
            self._exit_vol_history.pop(0)
        self._session_max_vol = max(self._session_max_vol, v)
        self._prior_1m_exit_bar = {"o": o, "h": h, "l": l, "c": c, "v": v}

    def _avg_recent_volume(self, n: int = 5) -> float:
        if len(self._exit_vol_history) < n:
            return 0
        return sum(self._exit_vol_history[-n:]) / n

    def _is_volume_confirmed(self, bar_volume: float, mult: float = 1.5) -> bool:
        avg = self._avg_recent_volume()
        if avg <= 0:
            return False
        return bar_volume >= mult * avg

    def _is_climax_volume(self, bar_volume: float) -> bool:
        return bar_volume >= self._session_max_vol and self._session_max_vol > 0

    def _check_candle_exit_v2(self, bar_1m, unrealized_r: float) -> Optional[str]:
        """Volume-confirmed 1m candle exit signals, tiered by profit level."""
        if self._bars_in_trade < self._t1_min_bars:
            return None

        o = bar_1m.open if hasattr(bar_1m, 'open') else bar_1m.get("o", 0)
        h = bar_1m.high if hasattr(bar_1m, 'high') else bar_1m.get("h", 0)
        l = bar_1m.low if hasattr(bar_1m, 'low') else bar_1m.get("l", 0)
        c = bar_1m.close if hasattr(bar_1m, 'close') else bar_1m.get("c", 0)
        v = bar_1m.volume if hasattr(bar_1m, 'volume') else bar_1m.get("v", 0)
        rng = h - l
        if rng <= 0:
            return None

        body = abs(c - o)
        upper_wick = h - max(o, c)

        prev = self._prior_1m_exit_bar
        if prev is None:
            return None

        prev_o, prev_h, prev_l, prev_c = prev["o"], prev["h"], prev["l"], prev["c"]
        vol_confirmed = self._is_volume_confirmed(v, self._t2_vol_mult)

        # ── Detect patterns ──
        _is_shooting_star = (body > 0 and upper_wick >= 2 * body
                             and (min(o, c) - l) <= 0.3 * rng)
        _is_gravestone = (body <= 0.12 * rng and rng > 0.001
                          and body > 0 and upper_wick >= 3 * body)
        _is_bearish_engulf = (c < o  # red
                              and prev_c > prev_o  # prev green
                              and c < prev_o and o > prev_c)
        _is_doji = body <= 0.12 * rng and rng > 0.001
        _is_cuc = (l < prev_l and c < prev_c)
        _is_climax_reversal = (h >= self._trade_peak
                               and (c - l) <= 0.25 * rng
                               and self._is_climax_volume(v))

        # ── TIER 1: Capital Protection (< 1.0R) ──
        if unrealized_r < self._t1_threshold:
            if _is_bearish_engulf:
                return "t1_bearish_engulfing_exit"
            if _is_shooting_star:
                return "t1_shooting_star_exit"
            if _is_gravestone:
                return "t1_gravestone_exit"
            return None

        # ── TIER 2: Momentum Protection (1.0R - 3.0R) ──
        if unrealized_r < self._t3_threshold:
            if _is_gravestone and vol_confirmed:
                return "t2_gravestone_vol_exit"
            if _is_shooting_star and vol_confirmed:
                return "t2_shooting_star_vol_exit"
            # Warnings (trail tighten)
            if _is_bearish_engulf:
                self._tight_trail_price = l
            if _is_doji:
                self._tight_trail_price = l
            return None

        # ── TIER 3: Runner Protection (≥ 3.0R) ──
        if _is_cuc:
            return "t3_candle_under_candle_exit"
        if _is_climax_reversal:
            return "t3_climax_reversal_exit"
        # Warnings
        if _is_shooting_star or _is_gravestone:
            self._tight_trail_price = l
        return None

    # ------------------------------------------------------------------
    # Trade lifecycle — V2 manages its own exit state
    # ------------------------------------------------------------------
    def notify_trade_opened(self, entry: float = 0, stop: float = 0,
                            r: float = 0, qty: int = 0,
                            time_str: str = "", is_parabolic: bool = False):
        self._in_trade = True
        self._trade_entry = entry
        self._trade_stop = stop
        self._trade_r = r
        self._trade_qty = qty
        self._trade_peak = entry
        self._trade_tp_hit = False
        self._trade_runner_stop = 0.0
        self._trade_entry_time = time_str
        self._trade_is_parabolic = is_parabolic
        # Reset 10s pattern state for fresh trade
        self._pattern_det_10s = PatternDetector()
        self._prev_10s_bar = None
        self._recent_10s_highs = []
        # Reset Candle Exit V2 state
        self._exit_vol_history = []
        self._session_max_vol = 0
        self._tight_trail_price = None
        self._bars_in_trade = 0
        self._prior_1m_exit_bar = None

    def notify_trade_closed(self, symbol: str, pnl: float):
        if pnl > 0:
            self._has_winner = True
        self._in_trade = False
        self._trade_entry = None
        self._trade_stop = None
        self._trade_r = None
        self._trade_qty = None

    def notify_partial_exit(self, remaining_qty: int):
        """Called after target hit partial exit to update runner qty."""
        self._trade_qty = remaining_qty

    # ------------------------------------------------------------------
    # Premarket levels
    # ------------------------------------------------------------------
    def update_premarket_levels(self, pm_high: Optional[float], pm_bf_high: Optional[float] = None):
        self.premarket_high = pm_high
        self.premarket_bull_flag_high = pm_bf_high

    # ------------------------------------------------------------------
    # Reset for new day/stock
    # ------------------------------------------------------------------
    def reset(self):
        self._state = "IDLE"
        self._primed_bars_left = 0
        self._primed_bar = None
        self._exhaustion_delay = False
        self.armed = None
        self._attempts = 0
        self._has_winner = False
        self._in_trade = False
        self._session_hod = 0.0
        self._trade_entry = None
        self._trade_stop = None
        self._trade_r = None
        self._trade_qty = None
        self._trade_peak = 0.0
        self._trade_tp_hit = False
        self._prev_10s_bar = None
        self._recent_10s_highs = []
        self._prev_1m_bar = None
        self._pattern_det_10s = PatternDetector()
        self._exit_vol_history = []
        self._session_max_vol = 0
        self._tight_trail_price = None
        self._bars_in_trade = 0
        self._prior_1m_exit_bar = None

    # ------------------------------------------------------------------
    # Internal helpers (V1 logic preserved)
    # ------------------------------------------------------------------
    def _reset(self, reason: str = ""):
        self._state = "IDLE"
        self._primed_bars_left = 0
        self._primed_bar = None
        self._exhaustion_delay = False
        self.armed = None

    def _avg_prior_vol(self) -> float:
        """Average volume of all 1m bars except the most recent."""
        if len(self.bars_1m) < 2:
            return 0.0
        bars = list(self.bars_1m)[:-1]
        total = sum(b["v"] for b in bars)
        return total / len(bars) if bars else 0.0

    def _find_broken_level(self, bar_high: float) -> tuple[Optional[str], Optional[float]]:
        """Check if bar_high has broken any key level, in priority order."""
        for level_type in self.level_priority:
            level_type = level_type.strip()
            price = self._get_level_price(level_type, bar_high)
            if price is not None and bar_high > price:
                return level_type, price
        return None, None

    def _get_level_price(self, level_type: str, reference_price: float) -> Optional[float]:
        if level_type == "pm_high":
            return self.premarket_high
        elif level_type == "whole_dollar":
            if len(self.bars_1m) < 1:
                return None
            last_open = self.bars_1m[-1]["o"]
            return float(math.ceil(last_open))
        elif level_type == "pdh":
            return self.prior_day_high
        return None

    def _stop_from_consolidation(self) -> float:
        """Stop = lowest low of last 3 bars before the current bar."""
        bars = list(self.bars_1m)
        if len(bars) < 2:
            return bars[-1]["l"] if bars else 0.0
        lookback = bars[max(0, len(bars) - 4):len(bars) - 1]
        if not lookback:
            return bars[-1]["l"]
        return min(b["l"] for b in lookback)

    def _try_arm(self, level_name: str, level_price: float, bar: dict,
                 vwap: Optional[float]) -> Optional[str]:
        """Attempt to ARM on a level break. Returns message or None."""
        entry_price = level_price + 0.02
        stop_low = self._stop_from_consolidation()
        r = entry_price - stop_low

        if r <= 0:
            self._reset("invalid_r")
            return f"SQ_NO_ARM: invalid_r (entry={entry_price:.4f} stop={stop_low:.4f})"

        # R cap
        max_r_pct = entry_price * 0.05
        effective_max_r = min(self.max_r, max_r_pct)
        if r > effective_max_r:
            if not self.para_enabled:
                self._reset("max_r_exceeded")
                return (
                    f"SQ_NO_ARM: max_r_exceeded R={r:.4f} > max={effective_max_r:.4f} "
                    f"(entry={entry_price:.4f} stop={stop_low:.4f})"
                )

            # Parabolic mode
            para_stop = level_price - self.para_stop_offset
            breakout_bar_low = bar["l"]
            para_stop = max(para_stop, breakout_bar_low)
            para_r = entry_price - para_stop

            if para_r <= 0:
                self._reset("para_invalid_r")
                return f"SQ_NO_ARM: para_invalid_r (entry={entry_price:.4f} stop={para_stop:.4f})"

            if para_r > self.max_r:
                self._reset("para_max_r_exceeded")
                return (
                    f"SQ_NO_ARM: para_max_r_exceeded R={para_r:.4f} > max={self.max_r:.4f} "
                    f"(entry={entry_price:.4f} stop={para_stop:.4f})"
                )

            score, detail = self._score_setup(bar, vwap, level_name)
            detail += ";[PARABOLIC]"
            size_mult = self.probe_size_mult

            self.armed = ArmedTrade(
                trigger_high=entry_price,
                stop_low=para_stop,
                entry_price=entry_price,
                r=para_r,
                score=score,
                score_detail=detail,
                setup_type="squeeze",
                size_mult=size_mult,
            )
            self._state = "ARMED"

            return (
                f"ARMED entry={entry_price:.4f} stop={para_stop:.4f} R={para_r:.4f} "
                f"score={score:.1f} level={level_name} setup_type=squeeze "
                f"[PARABOLIC] [PROBE={size_mult:.0%}] why={detail}"
            )

        # Normal ARM
        score, detail = self._score_setup(bar, vwap, level_name)
        size_mult = 1.0 if self._has_winner else self.probe_size_mult

        self.armed = ArmedTrade(
            trigger_high=entry_price,
            stop_low=stop_low,
            entry_price=entry_price,
            r=r,
            score=score,
            score_detail=detail,
            setup_type="squeeze",
            size_mult=size_mult,
        )
        self._state = "ARMED"

        size_tag = f" [PROBE={size_mult:.0%}]" if size_mult < 1.0 else ""
        return (
            f"ARMED entry={entry_price:.4f} stop={stop_low:.4f} R={r:.4f} "
            f"score={score:.1f} level={level_name} setup_type=squeeze{size_tag} "
            f"why={detail}"
        )

    def _score_setup(self, bar: dict, vwap: Optional[float],
                     level_name: str) -> tuple[float, str]:
        """V1 scoring + V2 COC bonus."""
        score = 5.0
        parts = ["base=5.0"]

        # Volume multiple above threshold
        avg_vol = self._avg_prior_vol()
        if avg_vol > 0:
            vol_ratio = bar["v"] / avg_vol
            extra_mults = vol_ratio - self.vol_mult
            if extra_mults > 0:
                bonus = min(extra_mults, 5.0)
                score += bonus
                parts.append(f"vol_extra=+{bonus:.1f}")

        # PM bull flag detected
        if self.pm_confidence and self.premarket_bull_flag_high is not None:
            score += 2.0
            parts.append("pm_bull_flag=+2.0")

        # Gap strength
        if self.gap_pct is not None and self.gap_pct >= 20:
            score += 1.0
            parts.append("gap_20pct=+1.0")

        # VWAP distance
        if vwap is not None and vwap > 0:
            vwap_dist_pct = (bar["c"] - vwap) / vwap * 100
            if 2.0 <= vwap_dist_pct <= 15.0:
                score += 1.0
                parts.append(f"vwap_dist=+1.0({vwap_dist_pct:.0f}%)")

        # PM high break
        if level_name == "pm_high":
            score += 1.0
            parts.append("pm_high_break=+1.0")

        score = min(score, 15.0)
        return score, "squeeze: " + ";".join(parts)
