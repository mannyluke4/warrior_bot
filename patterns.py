# patterns.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Deque, Optional, List, Dict
from collections import deque
import math


@dataclass
class PatternSignal:
    name: str
    detail: str


def _slope(vals: List[float]) -> float:
    if len(vals) < 2:
        return 0.0
    return vals[-1] - vals[0]


def _near(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def _avg(vals: List[float]) -> float:
    return sum(vals) / max(1, len(vals))


def _stdev(vals: List[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _avg(vals)
    var = _avg([(x - m) ** 2 for x in vals])
    return math.sqrt(var)


class PatternDetector:
    """
    OHLCV-only pattern tagger. Emits PatternSignal(name, detail) when patterns appear.
    Designed for 10s bars or 1m bars.

    NOTE: This file does NOT know VWAP/HOD/premarket. Those belong elsewhere.
    """

    def __init__(self, maxlen: int = 200):
        self.bars: Deque[dict] = deque(maxlen=maxlen)

        # Simple anti-spam cooldowns: tag -> remaining bars until it can fire again
        self._cooldown: Dict[str, int] = {}
        self._cooldown_default = 8  # tune per timeframe (10s bars: 8 = ~80s)

    def _tick_cooldowns(self):
        dead = []
        for k, v in self._cooldown.items():
            nv = v - 1
            if nv <= 0:
                dead.append(k)
            else:
                self._cooldown[k] = nv
        for k in dead:
            self._cooldown.pop(k, None)

    def _can_emit(self, name: str) -> bool:
        return self._cooldown.get(name, 0) <= 0

    def _emit(self, sigs: List[PatternSignal], name: str, detail: str, cooldown: Optional[int] = None):
        if not self._can_emit(name):
            return
        sigs.append(PatternSignal(name, detail))
        self._cooldown[name] = int(cooldown if cooldown is not None else self._cooldown_default)

    def update(self, o: float, h: float, l: float, c: float, v: float) -> List[PatternSignal]:
        self.bars.append({"o": o, "h": h, "l": l, "c": c, "v": v})
        self._tick_cooldowns()

        sigs: List[PatternSignal] = []
        if len(self.bars) < 15:
            return sigs

        # --- Big picture / risk first ---
        danger = self._trend_failure()
        if danger:
            self._emit(sigs, danger.name, danger.detail, cooldown=6)

        lowliq = self._low_liquidity()
        if lowliq:
            self._emit(sigs, lowliq.name, lowliq.detail, cooldown=10)

        wick = self._topping_wicky()
        if wick:
            self._emit(sigs, wick.name, wick.detail, cooldown=8)

        # --- Bullish structures ---
        bf = self._bull_flag()
        if bf:
            self._emit(sigs, bf.name, bf.detail, cooldown=10)

        ft = self._flat_top_breakout()
        if ft:
            self._emit(sigs, ft.name, ft.detail, cooldown=10)

        at = self._ascending_triangle()
        if at:
            self._emit(sigs, at.name, at.detail, cooldown=10)

        abcd = self._abcd_pullback()
        if abcd:
            self._emit(sigs, abcd.name, abcd.detail, cooldown=10)

        r2g = self._red_to_green()
        if r2g:
            self._emit(sigs, r2g.name, r2g.detail, cooldown=8)

        vol = self._volume_surge()
        if vol:
            self._emit(sigs, vol.name, vol.detail, cooldown=6)

        whole = self._whole_dollar_nearby()
        if whole:
            self._emit(sigs, whole.name, whole.detail, cooldown=6)

        return sigs

    # ----------------------------
    # Bull Flag (existing)
    # ----------------------------
    def _bull_flag(self) -> Optional[PatternSignal]:
        if len(self.bars) < 25:
            return None

        recent = list(self.bars)[-25:]
        closes = [b["c"] for b in recent]
        vols   = [b["v"] for b in recent]

        imp = closes[-25:-13]  # 12 bars
        flag = closes[-13:]    # 13 bars

        imp_move = max(imp) - min(imp)
        if imp_move <= 0:
            return None

        if imp_move < 0.03 * max(imp):  # ~3%
            return None

        flag_slope = _slope(flag)
        if flag_slope > 0:
            return None

        imp_low = min(imp)
        imp_high = max(imp)
        allowed_retrace = imp_high - (0.55 * (imp_high - imp_low))  # ~45% max retrace
        if min(flag) < allowed_retrace:
            return None

        avg_imp_v = _avg(vols[-25:-13])
        avg_flag_v = _avg(vols[-13:])
        if avg_imp_v > 0 and avg_flag_v > avg_imp_v * 1.15:
            return None

        return PatternSignal("BULL_FLAG", f"impulse={imp_move:.4f} flag_slope={flag_slope:.4f}")

    # ----------------------------
    # Flat-Top Breakout (existing)
    # ----------------------------
    def _flat_top_breakout(self) -> Optional[PatternSignal]:
        recent = list(self.bars)[-20:]
        highs = [b["h"] for b in recent]
        lows  = [b["l"] for b in recent]

        top = max(highs)
        tol = max(0.01, top * 0.002)  # ~0.2% or 1 cent

        touches = sum(1 for x in highs if _near(x, top, tol))
        if touches < 3:
            return None

        low_slope = _slope(lows)
        if low_slope <= 0:
            return None

        return PatternSignal("FLAT_TOP", f"top={top:.4f} touches={touches} low_slope={low_slope:.4f}")

    # ----------------------------
    # Ascending Triangle (existing)
    # ----------------------------
    def _ascending_triangle(self) -> Optional[PatternSignal]:
        recent = list(self.bars)[-25:]
        highs = [b["h"] for b in recent]
        lows  = [b["l"] for b in recent]

        top = max(highs)
        tol = max(0.01, top * 0.002)
        touches = sum(1 for x in highs if _near(x, top, tol))
        if touches < 3:
            return None

        first_half_min = min(lows[:12])
        second_half_min = min(lows[12:])
        if second_half_min <= first_half_min:
            return None

        return PatternSignal("ASC_TRIANGLE", f"top={top:.4f} touches={touches} lows_rising=1")

    # ----------------------------
    # ABCD pullback (existing)
    # ----------------------------
    def _abcd_pullback(self) -> Optional[PatternSignal]:
        if len(self.bars) < 30:
            return None

        recent = list(self.bars)[-30:]
        closes = [b["c"] for b in recent]

        a = min(closes[:10])
        b = max(closes[:10])
        if b <= a:
            return None

        c = min(closes[10:20])
        if c >= b:
            return None

        if c <= a:
            return None

        if closes[-1] <= closes[-3]:
            return None

        return PatternSignal("ABCD", f"A={a:.4f} B={b:.4f} C={c:.4f}")

    # ----------------------------
    # Trend failure / danger (existing)
    # ----------------------------
    def _trend_failure(self) -> Optional[PatternSignal]:
        """
        Two levels:
        - DANGER_TREND_DOWN_STRONG: sustained lower highs/lows + meaningful drop
        - DANGER_TREND_DOWN: mild LH/LL chop (score penalty only)
        """
        if len(self.bars) < 12:
            return None

        recent = list(self.bars)[-12:]
        highs = [b["h"] for b in recent]
        lows  = [b["l"] for b in recent]
        closes = [b["c"] for b in recent]

        hs = _slope(highs)
        ls = _slope(lows)

        if hs < 0 and ls < 0:
            # how meaningful is the drop?
            start = closes[0]
            end = closes[-1]
            drop_pct = (start - end) / max(0.01, start)

            # STRONG danger if drop is meaningful (tune)
            if drop_pct >= 0.006:  # 0.6% over last 12 bars
                return PatternSignal("DANGER_TREND_DOWN_STRONG", f"drop_pct={drop_pct:.3%}")
            return PatternSignal("DANGER_TREND_DOWN", "mild_lower_highs_lows")

        return None

    # ----------------------------
    # NEW: Red-to-Green proxy
    # ----------------------------
    def _red_to_green(self) -> Optional[PatternSignal]:
        """
        Proxy:
        - recent dip: last 10 bars include a close below earlier close
        - now: last 2-3 closes pushing up strongly (reclaim)
        """
        if len(self.bars) < 18:
            return None

        recent = list(self.bars)[-18:]
        closes = [b["c"] for b in recent]

        base = closes[0]
        dipped = min(closes[2:12]) < base * 0.997  # ~0.3% dip (tune)
        if not dipped:
            return None

        reclaim = closes[-1] > closes[-3] and closes[-1] > base
        if not reclaim:
            return None

        return PatternSignal("RED_TO_GREEN", f"base={base:.4f} low={min(closes[2:12]):.4f} reclaim={closes[-1]:.4f}")

    # ----------------------------
    # NEW: Whole dollar / key level nearby
    # ----------------------------
    def _whole_dollar_nearby(self) -> Optional[PatternSignal]:
        """
        Emits when price is within X cents of a whole dollar.
        Very useful for scoring (psych level).
        """
        c = self.bars[-1]["c"]
        whole = round(c)
        dist = abs(c - whole)
        if dist <= 0.06:  # within 6 cents
            return PatternSignal("WHOLE_DOLLAR_NEARBY", f"whole={whole:.2f} dist={dist:.4f}")
        return None

    # ----------------------------
    # NEW: Volume surge
    # ----------------------------
    def _volume_surge(self) -> Optional[PatternSignal]:
        if len(self.bars) < 25:
            return None
        recent = list(self.bars)[-25:]
        vols = [b["v"] for b in recent]
        v_now = vols[-1]
        v_avg = _avg(vols[-20:-1])
        if v_avg <= 0:
            return None
        if v_now >= v_avg * 2.2:
            return PatternSignal("VOLUME_SURGE", f"v_now={v_now} v_avg={v_avg:.1f} x={(v_now / v_avg):.2f}")
        return None

    # ----------------------------
    # NEW: Low liquidity risk
    # ----------------------------
    def _low_liquidity(self) -> Optional[PatternSignal]:
        """
        Repeated tiny volume bars can mean unreliable fills/slippage risk.
        """
        recent = list(self.bars)[-20:]
        vols = [b["v"] for b in recent]
        v_avg = _avg(vols)
        if v_avg < 50:  # tune per universe
            return PatternSignal("LOW_LIQUIDITY", f"avg_vol={v_avg:.1f}")
        return None

    # ----------------------------
    # NEW: Topping / wicky exhaustion
    # ----------------------------
    def _topping_wicky(self) -> Optional[PatternSignal]:
        """
        Upper-wick heavy bars near recent highs can be a caution tag.
        """
        if len(self.bars) < 12:
            return None
        recent = list(self.bars)[-12:]
        highs = [b["h"] for b in recent]
        top = max(highs)
        last = recent[-1]

        rng = max(1e-9, last["h"] - last["l"])
        upper_wick = last["h"] - max(last["o"], last["c"])
        body = abs(last["c"] - last["o"])

        # near top + big upper wick + smallish body
        if _near(last["h"], top, max(0.01, top * 0.002)) and (upper_wick / rng) >= 0.45 and (body / rng) <= 0.35:
            return PatternSignal("TOPPING_WICKY", f"top={top:.4f} uw_ratio={(upper_wick/rng):.2f}")
        return None