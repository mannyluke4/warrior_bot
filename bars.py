from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, time
from typing import Callable, Dict, Optional


@dataclass
class Bar:
    symbol: str
    start_utc: datetime  # bucket start in UTC
    open: float
    high: float
    low: float
    close: float
    volume: int  # sum of trade sizes in the bucket

    @property
    def date(self) -> datetime:
        """Alias for start_utc — compatibility with ib_insync BarData and BarProxy."""
        return self.start_utc


class TradeBarBuilder:
    """
    Builds N-second bars from trades (default: 60s).
    Calls on_bar_close(bar) when a bucket completes.

    Also maintains:
      - session VWAP (from trades) per symbol, reset on ET date change
      - HOD per symbol (high of day from trades)
    """

    def __init__(
        self,
        on_bar_close: Callable[[Bar], None],
        et_tz,
        interval_seconds: int = 60,
    ):
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        self.on_bar_close = on_bar_close
        self.et_tz = et_tz
        self.interval_seconds = int(interval_seconds)

        self._cur: Dict[str, Optional[Bar]] = {}
        self._last_bucket_start: Dict[str, Optional[datetime]] = {}

        # VWAP accumulators per symbol for the current ET session day
        self._vwap_pv: Dict[str, float] = {}
        self._vwap_vol: Dict[str, int] = {}
        self._session_et_date: Dict[str, Optional[datetime.date]] = {}

        # High of day per symbol (ET session day)
        self._hod: Dict[str, float] = {}

        # Premarket tracking per symbol (resets on new ET date)
        self._premarket_high: Dict[str, float] = {}
        self._premarket_complete: Dict[str, bool] = {}
        self._premarket_bull_flag_high: Dict[str, Optional[float]] = {}

        # Track if we've crossed into market hours for the day
        self._market_opened_today: Dict[str, bool] = {}

        # Premarket bar tracking for bull flag detection
        self._premarket_bars: Dict[str, list] = {}  # list of highs during premarket

    def get_vwap(self, symbol: str) -> Optional[float]:
        vol = self._vwap_vol.get(symbol, 0)
        if vol <= 0:
            return None
        return self._vwap_pv.get(symbol, 0.0) / vol

    def get_hod(self, symbol: str) -> Optional[float]:
        return self._hod.get(symbol)

    def get_premarket_high(self, symbol: str) -> Optional[float]:
        """Get the premarket high for this symbol (4 AM - 9:30 AM ET)"""
        return self._premarket_high.get(symbol)

    def get_premarket_bull_flag_high(self, symbol: str) -> Optional[float]:
        """Get the premarket bull flag high if detected"""
        return self._premarket_bull_flag_high.get(symbol)

    def is_premarket(self, ts_utc: datetime) -> bool:
        """Check if timestamp is during premarket (4:00 AM - 9:30 AM ET)"""
        ts_et = ts_utc.astimezone(self.et_tz)
        t = ts_et.time()
        return time(4, 0) <= t < time(9, 30)

    def is_market_hours(self, ts_utc: datetime) -> bool:
        """Check if timestamp is during regular market hours (9:30 AM - 4:00 PM ET)"""
        ts_et = ts_utc.astimezone(self.et_tz)
        t = ts_et.time()
        return time(9, 30) <= t < time(16, 0)

    def is_golden_hour(self, ts_utc: datetime) -> bool:
        """Check if we're in the golden hour (9:30 AM - 10:00 AM ET)"""
        ts_et = ts_utc.astimezone(self.et_tz)
        t = ts_et.time()
        return time(9, 30) <= t < time(10, 0)

    def _detect_premarket_bull_flag(self, symbol: str):
        """
        Detect premarket bull flag pattern.
        A bull flag in premarket is characterized by:
        - Multiple touches/tests of a resistance level
        - That level becomes the breakout trigger

        Simple heuristic: if we have 3+ bars that came within 0.5% of the premarket high,
        it's likely a flat-top/bull flag pattern, and that level is significant.
        """
        pm_bars = self._premarket_bars.get(symbol, [])
        pm_high = self._premarket_high.get(symbol)

        if not pm_bars or pm_high is None or pm_high <= 0 or len(pm_bars) < 10:
            return

        # Check how many bars touched near the premarket high
        tolerance = pm_high * 0.005  # 0.5% tolerance
        touches = sum(1 for bar_high in pm_bars if abs(bar_high - pm_high) <= tolerance)

        # If 3+ touches, consider it a bull flag pattern
        if touches >= 3:
            self._premarket_bull_flag_high[symbol] = pm_high

    def _bucket_start_utc(self, ts_utc: datetime) -> datetime:
        epoch = int(ts_utc.timestamp())
        bucket_epoch = (epoch // self.interval_seconds) * self.interval_seconds
        return datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)

    def _reset_session_if_needed(self, symbol: str, ts_utc: datetime):
        ts_et = ts_utc.astimezone(self.et_tz)
        d = ts_et.date()
        if self._session_et_date.get(symbol) != d:
            self._session_et_date[symbol] = d
            self._vwap_pv[symbol] = 0.0
            self._vwap_vol[symbol] = 0
            self._hod[symbol] = float("-inf")

            # Reset premarket tracking on new day
            self._premarket_high[symbol] = float("-inf")
            self._premarket_complete[symbol] = False
            self._premarket_bull_flag_high[symbol] = None
            self._market_opened_today[symbol] = False
            self._premarket_bars[symbol] = []

    def seed_bar_close(self, symbol: str, o: float, h: float, l: float, c: float, v: float, ts_utc):
        """
        Seed-only: update VWAP/HOD/session state without calling on_bar_close callback.
        This MUST seed the same fields used by get_vwap/get_hod.
        """
        if isinstance(ts_utc, datetime):
            if ts_utc.tzinfo is None:
                ts_utc = ts_utc.replace(tzinfo=timezone.utc)
            else:
                ts_utc = ts_utc.astimezone(timezone.utc)
        else:
            ts_utc = datetime.now(timezone.utc)

        self._reset_session_if_needed(symbol, ts_utc)

        vv = int(v)
        if vv < 0:
            vv = 0

        # ✅ Seed the real VWAP accumulators used by get_vwap()
        self._vwap_pv[symbol] = self._vwap_pv.get(symbol, 0.0) + (float(c) * vv)
        self._vwap_vol[symbol] = self._vwap_vol.get(symbol, 0) + vv

        # ✅ Seed the real HOD used by get_hod()
        self._hod[symbol] = max(self._hod.get(symbol, float("-inf")), float(h))

        # ✅ Seed premarket high if in premarket
        if self.is_premarket(ts_utc):
            pm_high = self._premarket_high.get(symbol, float("-inf"))
            self._premarket_high[symbol] = max(pm_high, float(h))

    def on_trade(self, symbol: str, price: float, size: int, ts: datetime):
        if ts.tzinfo is None:
            ts_utc = ts.replace(tzinfo=timezone.utc)
        else:
            ts_utc = ts.astimezone(timezone.utc)

        self._reset_session_if_needed(symbol, ts_utc)

        self._vwap_pv[symbol] = self._vwap_pv.get(symbol, 0.0) + (price * size)
        self._vwap_vol[symbol] = self._vwap_vol.get(symbol, 0) + int(size)

        self._hod[symbol] = max(self._hod.get(symbol, float("-inf")), price)

        # Track premarket high (4 AM - 9:30 AM ET)
        if self.is_premarket(ts_utc):
            pm_high = self._premarket_high.get(symbol, float("-inf"))
            self._premarket_high[symbol] = max(pm_high, price)

        # Mark premarket as complete when we enter market hours
        if self.is_market_hours(ts_utc) and not self._market_opened_today.get(symbol, False):
            self._premarket_complete[symbol] = True
            self._market_opened_today[symbol] = True

            # Detect premarket bull flag before market open
            self._detect_premarket_bull_flag(symbol)

        b0 = self._bucket_start_utc(ts_utc)
        last_b0 = self._last_bucket_start.get(symbol)

        if last_b0 is None:
            self._last_bucket_start[symbol] = b0
            self._cur[symbol] = Bar(symbol, b0, price, price, price, price, int(size))
            return

        if b0 == last_b0:
            b = self._cur.get(symbol)
            if b is None:
                self._cur[symbol] = Bar(symbol, b0, price, price, price, price, int(size))
            else:
                b.high = max(b.high, price)
                b.low = min(b.low, price)
                b.close = price
                b.volume += int(size)
            return

        prev_bar = self._cur.get(symbol)
        if prev_bar is not None:
            self.on_bar_close(prev_bar)

            # Track premarket bars for bull flag detection
            if self.is_premarket(ts_utc):
                if symbol not in self._premarket_bars:
                    self._premarket_bars[symbol] = []
                self._premarket_bars[symbol].append(prev_bar.high)

        self._last_bucket_start[symbol] = b0
        self._cur[symbol] = Bar(symbol, b0, price, price, price, price, int(size))
