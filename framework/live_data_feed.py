"""framework.live_data_feed — IBKR real-time bar feed for the framework runner.

Wave 4 paper deployment. Subscribes to 1-minute bars for the 36-symbol
Databento universe via ib_insync (same IB Gateway used by Setup A's
`bot_alpaca_subbot.py`, but on a separate `clientId` — defaulted to 51 via
`WB_FRAMEWORK_IB_CLIENT_ID`).

Patterns are copied from (READ-ONLY references — neither file modified):
    bot_alpaca_subbot.py — connect(), reqHistoricalData seeding loop
    ibkr_feed.py         — connect/disconnect/subscribe lifecycle

Design choices:
    - Pull 1-minute bars via reqRealTimeBars(5s, TRADES) and aggregate into
      1-minute closes in-process. This matches what `bot_alpaca_subbot.py`
      effectively does via TradeBarBuilder, but we do the rollup explicitly
      here so the framework runner can subscribe per-strategy callbacks per
      symbol without touching the legacy TradeBarBuilder.
    - Maintain a per-symbol bar history deque (default 240 bars = 4 hours).
      Strategies (PDH-Fade, ORB, PDH-Breakout) need at most 25 bars of
      lookback (5-bar pre-entry consolidation + 20-bar volume baseline),
      so 240 is comfortably oversized.
    - Provide a `seed_history(symbol)` call that fetches the prior session's
      1-minute RTH bars via reqHistoricalData. PDH/PDL strategies need
      prior-day OHLC; the seeding is done once per symbol at startup.
    - All public methods are safe to call from the main asyncio/ib_insync
      event loop (no internal threads).

Public API:
    LiveDataFeed(host, port, client_id)
    feed.connect() -> bool
    feed.subscribe(symbol, on_bar_close=callable)
    feed.unsubscribe(symbol)
    feed.disconnect()
    feed.get_history(symbol) -> list[Bar]
    feed.get_prior_day_bars(symbol) -> list[Bar]
    feed.seed_history(symbol)     # fetch prior-day + today-so-far

The `Bar` type is the framework's standard `framework.level_sources.base.Bar`
so signal evaluators consume it natively.
"""
from __future__ import annotations

import os
from collections import deque
from datetime import datetime, timedelta
from typing import Callable, Optional

import pytz

from framework.level_sources.base import Bar

ET = pytz.timezone("US/Eastern")
UTC = pytz.UTC


# ---------------------------------------------------------------------------
# 5s -> 1m bar aggregator
# ---------------------------------------------------------------------------


class _MinuteAggregator:
    """Roll 5-second real-time bars into 1-minute closes.

    On every 5s tick the aggregator either extends the current 1m bar or, if
    the minute has rolled over, finalizes the prior 1m and starts a new one.
    Calls `on_close(bar)` exactly once per closed minute.
    """

    def __init__(self, symbol: str, on_close: Callable[[Bar], None]) -> None:
        self.symbol = symbol
        self.on_close = on_close
        self._current_minute: Optional[datetime] = None
        self._open = 0.0
        self._high = 0.0
        self._low = 0.0
        self._close = 0.0
        self._volume = 0.0

    def feed(self, ts_et: datetime, o: float, h: float, l: float, c: float, v: float) -> None:
        # Truncate to minute (ET-naive)
        minute = ts_et.replace(second=0, microsecond=0)
        if self._current_minute is None:
            self._current_minute = minute
            self._open = float(o)
            self._high = float(h)
            self._low = float(l)
            self._close = float(c)
            self._volume = float(v)
            return
        if minute == self._current_minute:
            self._high = max(self._high, float(h))
            self._low = min(self._low, float(l))
            self._close = float(c)
            self._volume += float(v)
            return
        # Minute rolled over — emit the prior minute's bar
        bar = Bar(
            timestamp=self._current_minute,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._volume,
            symbol=self.symbol,
        )
        try:
            self.on_close(bar)
        except Exception as e:  # never let a callback exception kill the feed
            print(f"[FRAMEWORK_FEED] {self.symbol} on_close raised: {e!r}", flush=True)
        # Start the new minute
        self._current_minute = minute
        self._open = float(o)
        self._high = float(h)
        self._low = float(l)
        self._close = float(c)
        self._volume = float(v)

    def force_finalize(self) -> Optional[Bar]:
        """Emit and return the in-progress 1m bar (used at force-exit time)."""
        if self._current_minute is None:
            return None
        bar = Bar(
            timestamp=self._current_minute,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._volume,
            symbol=self.symbol,
        )
        self._current_minute = None
        return bar


# ---------------------------------------------------------------------------
# LiveDataFeed
# ---------------------------------------------------------------------------


class LiveDataFeed:
    """IBKR live data feed: 5s real-time bars → 1m closes per symbol.

    Use:
        feed = LiveDataFeed(host="127.0.0.1", port=7497, client_id=51)
        feed.connect()
        feed.subscribe("AAPL", on_bar_close=on_bar_close_callback)
        # ... main loop runs feed.ib.run() / sleep loop ...
        feed.disconnect()
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        client_id: Optional[int] = None,
        history_depth: int = 240,
    ) -> None:
        self.host = host or os.environ.get("WB_IBKR_HOST", "127.0.0.1")
        self.port = port or int(os.environ.get("WB_IBKR_PORT", "7497"))
        # Framework runs on its own clientId (default 51 per directive).
        self.client_id = (
            client_id
            if client_id is not None
            else int(os.environ.get("WB_FRAMEWORK_IB_CLIENT_ID", "51"))
        )
        self.history_depth = history_depth
        self.ib = None  # ib_insync.IB() — lazy-initialized in connect()
        self._connected = False
        self._contracts: dict[str, object] = {}
        self._aggregators: dict[str, _MinuteAggregator] = {}
        self._history: dict[str, deque] = {}
        self._prior_day_bars: dict[str, list[Bar]] = {}
        self._user_callbacks: dict[str, Callable[[Bar], None]] = {}
        self._real_time_bars: dict[str, object] = {}  # ib_insync RealTimeBarList per symbol

    # ----- lifecycle -----

    def connect(self) -> bool:
        """Open an IB Gateway connection. Returns True on success."""
        try:
            from ib_insync import IB
        except ImportError as e:
            print(f"[FRAMEWORK_FEED] ib_insync not installed: {e}", flush=True)
            return False
        self.ib = IB()
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            self._connected = bool(self.ib.isConnected())
            if self._connected:
                print(
                    f"[FRAMEWORK_FEED] connected: {self.host}:{self.port} "
                    f"clientId={self.client_id}",
                    flush=True,
                )
            return self._connected
        except Exception as e:
            print(f"[FRAMEWORK_FEED] connect failed: {e!r}", flush=True)
            self._connected = False
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected and self.ib is not None and self.ib.isConnected()

    def disconnect(self) -> None:
        if not self.ib:
            return
        for sym in list(self._real_time_bars.keys()):
            self.unsubscribe(sym)
        try:
            self.ib.disconnect()
        except Exception:
            pass
        self._connected = False
        print("[FRAMEWORK_FEED] disconnected", flush=True)

    # ----- subscription -----

    def _qualify(self, symbol: str):
        """Qualify and cache a Stock contract for `symbol`."""
        if symbol in self._contracts:
            return self._contracts[symbol]
        from ib_insync import Stock
        c = Stock(symbol, "SMART", "USD")
        self.ib.qualifyContracts(c)
        self._contracts[symbol] = c
        return c

    def subscribe(self, symbol: str, on_bar_close: Callable[[Bar], None]) -> bool:
        """Subscribe to 5s real-time bars for `symbol`; emit 1m closes via callback.

        Returns True on success.
        """
        if not self.is_connected:
            print(
                f"[FRAMEWORK_FEED] subscribe({symbol}): not connected",
                flush=True,
            )
            return False
        if symbol in self._real_time_bars:
            # idempotent: replace callback only
            self._user_callbacks[symbol] = on_bar_close
            return True
        try:
            c = self._qualify(symbol)
            # whatToShow=TRADES, useRTH=False so we cover ext-hours too
            rtb = self.ib.reqRealTimeBars(c, 5, "TRADES", False)
        except Exception as e:
            print(
                f"[FRAMEWORK_FEED] subscribe({symbol}) raised: {e!r}",
                flush=True,
            )
            return False
        self._real_time_bars[symbol] = rtb
        self._user_callbacks[symbol] = on_bar_close
        self._history.setdefault(symbol, deque(maxlen=self.history_depth))

        def _on_minute_close(bar: Bar, _sym=symbol) -> None:
            self._history[_sym].append(bar)
            cb = self._user_callbacks.get(_sym)
            if cb:
                cb(bar)

        agg = _MinuteAggregator(symbol, _on_minute_close)
        self._aggregators[symbol] = agg

        def _on_5s_update(bars, hasNewBar, _sym=symbol, _agg=agg) -> None:
            if not bars:
                return
            b = bars[-1]
            # ib_insync RealTimeBar.time is tz-aware (UTC). Convert to ET-naive.
            ts_utc = b.time
            if ts_utc.tzinfo is None:
                ts_utc = ts_utc.replace(tzinfo=UTC)
            ts_et = ts_utc.astimezone(ET).replace(tzinfo=None)
            _agg.feed(ts_et, b.open_, b.high, b.low, b.close, b.volume)

        rtb.updateEvent += _on_5s_update
        print(f"[FRAMEWORK_FEED] subscribed: {symbol}", flush=True)
        return True

    def unsubscribe(self, symbol: str) -> None:
        rtb = self._real_time_bars.pop(symbol, None)
        self._user_callbacks.pop(symbol, None)
        if rtb is not None and self.ib is not None:
            try:
                self.ib.cancelRealTimeBars(rtb)
            except Exception:
                pass
        print(f"[FRAMEWORK_FEED] unsubscribed: {symbol}", flush=True)

    # ----- history -----

    def get_history(self, symbol: str) -> list[Bar]:
        """Return all in-memory closed 1m bars for `symbol`, oldest first."""
        return list(self._history.get(symbol, ()))

    def get_prior_day_bars(self, symbol: str) -> list[Bar]:
        return list(self._prior_day_bars.get(symbol, ()))

    def seed_history(self, symbol: str, lookback_days: int = 5) -> int:
        """Fetch the prior trading session's RTH 1m bars + today-so-far.

        Fills `_prior_day_bars[symbol]` and the running `_history[symbol]`.
        Returns the count of bars seeded. Best-effort: errors return 0.
        """
        if not self.is_connected:
            return 0
        try:
            c = self._qualify(symbol)
        except Exception:
            return 0

        # Prior day(s): 2 trading days back covers Monday's prior-Friday
        try:
            prior = self.ib.reqHistoricalData(
                c,
                endDateTime="",
                durationStr="2 D",
                barSizeSetting="1 min",
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            )
        except Exception as e:
            print(
                f"[FRAMEWORK_FEED] seed_history({symbol}) raised: {e!r}",
                flush=True,
            )
            return 0
        if not prior:
            return 0

        # Group by session date. ib_insync returns BarData with .date
        # (timezone-naive ET).
        from collections import defaultdict

        by_day: dict[str, list[Bar]] = defaultdict(list)
        for b in prior:
            ts = b.date
            if not isinstance(ts, datetime):
                # `b.date` is a python datetime for 1-min bars
                try:
                    ts = datetime.fromisoformat(str(b.date))
                except Exception:
                    continue
            day = ts.date().isoformat()
            try:
                bar = Bar(
                    timestamp=ts,
                    open=float(b.open),
                    high=float(b.high),
                    low=float(b.low),
                    close=float(b.close),
                    volume=float(b.volume),
                    symbol=symbol,
                )
            except (ValueError, TypeError):
                continue
            by_day[day].append(bar)

        if not by_day:
            return 0

        days_sorted = sorted(by_day.keys())
        today = datetime.now(ET).date().isoformat()
        prior_day = None
        for d in reversed(days_sorted):
            if d != today:
                prior_day = d
                break
        if prior_day is not None:
            self._prior_day_bars[symbol] = by_day[prior_day]

        # Seed today's history deque
        hist = self._history.setdefault(symbol, deque(maxlen=self.history_depth))
        if today in by_day:
            for bar in by_day[today]:
                hist.append(bar)

        total = sum(len(v) for v in by_day.values())
        print(
            f"[FRAMEWORK_FEED] seeded {symbol}: {total} bars "
            f"(prior_day={prior_day}, today={len(by_day.get(today, []))})",
            flush=True,
        )
        return total

    # ----- utility (used at force-exit / shutdown) -----

    def force_finalize_open_minutes(self) -> list[Bar]:
        """Emit any in-progress 1m bars early. Used at force-exit time so
        the runner can act on the most-recent data point even mid-minute.
        """
        out: list[Bar] = []
        for sym, agg in self._aggregators.items():
            b = agg.force_finalize()
            if b is not None:
                self._history[sym].append(b)
                out.append(b)
        return out
