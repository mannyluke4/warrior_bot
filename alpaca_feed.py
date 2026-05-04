"""alpaca_feed.py — drop-in replacement for ib_insync.IB market-data layer.

Mirrors the subset of ib_insync's IB API that bot_v3_hybrid.py uses for tick
subscription, historical fetch, and connection lifecycle. Backed by:
  - alpaca.data.live.StockDataStream — live trade websocket
  - alpaca.data.historical.StockHistoricalDataClient — historical ticks/bars

Design constraint: every method/attribute the bot reaches for on `state.ib`
exists here with the same name and roughly the same shape. The bot reads
`ticker.last`, `ticker.lastSize`, `tick.price`, `tick.size`, `tick.time`, and
calls `state.ib.sleep(N)` to yield — all preserved.

Threading model:
  - Stream thread (daemon, named "alpaca-stream") owns the asyncio loop,
    receives Trade messages from Alpaca, enqueues to `_tick_queue`.
  - Main thread calls `sleep(N)` which drains the queue, updates ticker
    objects in place, and fires `pendingTickersEvent` with the updated set —
    same shape ib_insync delivers (a set of Ticker objects).
  - All ticker mutations and event dispatch happen on the main thread.

Order execution (AlpacaBroker via TradingClient) is NOT in this module —
broker.py already handles that. This module is data-feed only.
"""

from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Optional

# ─────────────────────────────────────────────────────────────────────
# IB-shape stubs the bot expects to receive
# ─────────────────────────────────────────────────────────────────────

class StockContract:
    """Drop-in for ib_insync.Stock. Bot only reads .symbol; the other fields
    exist for signature parity (`Stock(symbol, 'SMART', 'USD')`)."""
    __slots__ = ("symbol", "exchange", "currency", "conId")

    def __init__(self, symbol: str, exchange: str = "SMART", currency: str = "USD"):
        self.symbol = symbol.upper()
        self.exchange = exchange
        self.currency = currency
        self.conId = 0  # ib_insync attribute; some bot code reads it

    def __repr__(self) -> str:
        return f"StockContract({self.symbol!r})"


# Alias so `from alpaca_feed import Stock` works as `from ib_insync import Stock`
Stock = StockContract


class HistoricalTickStub:
    """Drop-in for ib_insync.HistoricalTickLast — bot reads .time, .price, .size."""
    __slots__ = ("time", "price", "size")

    def __init__(self, time: datetime, price: float, size: int):
        self.time = time
        self.price = price
        self.size = size


class HistoricalBarStub:
    """Drop-in for ib_insync.BarData — bot reads .date, .open, .high, .low,
    .close, .volume. Used by reqHistoricalData fallback path."""
    __slots__ = ("date", "open", "high", "low", "close", "volume", "average", "barCount")

    def __init__(self, date, open_, high, low, close, volume):
        self.date = date
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.average = 0.0
        self.barCount = 0


class AlpacaTicker:
    """Drop-in for ib_insync.Ticker. Bot reads .last, .lastSize, .contract,
    .marketPrice(); all are mutated in place by the feed's drain pass."""
    __slots__ = ("contract", "last", "lastSize", "time")

    def __init__(self, contract: StockContract):
        self.contract = contract
        self.last = float("nan")
        self.lastSize = 0
        self.time: Optional[datetime] = None

    def marketPrice(self) -> float:
        return self.last

    def __repr__(self) -> str:
        sym = self.contract.symbol if self.contract else "?"
        last = "nan" if self.last != self.last else f"{self.last:.4f}"
        return f"AlpacaTicker({sym}, last={last}, size={self.lastSize})"


class _Event:
    """Minimal stand-in for ib_insync's Event class.

    Supports `event += handler` / `event -= handler` / `event(*args)` and the
    `event.clear()` housekeeping the bot uses on reconnect. Handlers are
    called synchronously on the main thread."""

    def __init__(self, name: str = ""):
        self._name = name
        self._handlers: list[Callable] = []

    def __iadd__(self, fn: Callable):
        if fn not in self._handlers:
            self._handlers.append(fn)
        return self

    def __isub__(self, fn: Callable):
        try:
            self._handlers.remove(fn)
        except ValueError:
            pass
        return self

    def clear(self) -> None:
        self._handlers.clear()

    def __call__(self, *args, **kwargs) -> None:
        for h in list(self._handlers):
            try:
                h(*args, **kwargs)
            except Exception as e:
                print(f"⚠️ AlpacaFeed event[{self._name}] handler "
                      f"{getattr(h, '__name__', repr(h))} raised: {e}", flush=True)
                traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────
# Datetime parsing — IBKR's reqHistoricalTicks signature uses string dates
# ─────────────────────────────────────────────────────────────────────

import pytz
_ET = pytz.timezone("US/Eastern")


def _parse_ib_dtstr(s: str) -> Optional[datetime]:
    """Parse the date strings the bot passes to reqHistoricalTicks.
    Formats observed:
      "20260504 04:00:00 US/Eastern"
      "20260504 11:23:45 UTC"
      "" (empty → None, signals "now")
    """
    if not s:
        return None
    s = s.strip()
    parts = s.split()
    if len(parts) < 2:
        return None
    date_str, time_str = parts[0], parts[1]
    tz_str = parts[2] if len(parts) > 2 else "UTC"
    fmt = "%Y%m%d %H:%M:%S"
    naive = datetime.strptime(f"{date_str} {time_str}", fmt)
    if tz_str.upper() == "UTC":
        return naive.replace(tzinfo=timezone.utc)
    if tz_str == "US/Eastern":
        return _ET.localize(naive).astimezone(timezone.utc)
    return naive.replace(tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────────────
# AlpacaFeed — the IB() drop-in
# ─────────────────────────────────────────────────────────────────────

class AlpacaFeed:
    """Drop-in replacement for ib_insync.IB, backed by Alpaca data APIs.

    Lifecycle:
      feed = AlpacaFeed()
      feed.connect()               # initializes clients, kicks off stream thread
      ticker = feed.reqMktData(Stock("AAPL"), "233", False, False)
      feed.sleep(0.5)              # drains queue, fires pendingTickersEvent
      feed.cancelMktData(Stock("AAPL"))
      feed.disconnect()
    """

    # The IEX free feed covers most low-float small-caps Manny trades; SIP
    # ($99/mo) gets full consolidated tape. Default IEX; flip via env.
    @staticmethod
    def _resolve_feed():
        from alpaca.data.enums import DataFeed
        name = os.getenv("WB_ALPACA_DATA_FEED", "iex").lower()
        try:
            return DataFeed(name)
        except ValueError:
            return DataFeed.IEX

    def __init__(self):
        self._connected = False
        self._historical = None
        self._stream = None
        self._stream_thread: Optional[threading.Thread] = None
        self._stream_loop: Optional[asyncio.AbstractEventLoop] = None
        self._stream_started = threading.Event()
        # Tick events from the stream thread → drained by main thread in sleep()
        self._tick_queue: queue.Queue = queue.Queue(maxsize=200_000)
        self._tickers: dict[str, AlpacaTicker] = {}  # symbol → live AlpacaTicker
        self._subscribed: set[str] = set()
        # Lock guards _subscribed mutations across main + stream threads
        self._sub_lock = threading.Lock()
        # Stream warmup state — set when the stream's _running flag flips True
        self._stream_running = threading.Event()

        # Events the bot registers handlers on
        self.pendingTickersEvent = _Event("pendingTickers")
        self.errorEvent = _Event("error")

    # ── Connection lifecycle ────────────────────────────────────────────
    def connect(self, host: str = None, port: int = None, clientId: int = None) -> None:
        """Initialize Alpaca clients and start the stream thread.
        host/port/clientId are accepted for signature parity with IB.connect
        but ignored — Alpaca uses API keys."""
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.live import StockDataStream

        api_key = os.getenv("APCA_API_KEY_ID")
        api_secret = os.getenv("APCA_API_SECRET_KEY")
        if not api_key or not api_secret:
            raise RuntimeError(
                "AlpacaFeed.connect: APCA_API_KEY_ID / APCA_API_SECRET_KEY "
                "missing from environment. Check .env."
            )

        self._data_feed = self._resolve_feed()
        self._historical = StockHistoricalDataClient(api_key, api_secret)
        self._stream = StockDataStream(api_key, api_secret, feed=self._data_feed)
        self._connected = True

        # Stream thread runs the asyncio loop. We don't start the websocket
        # yet — alpaca-py's _run_forever spins waiting for at least one
        # subscription. The first reqMktData triggers it.
        self._start_stream_thread()
        print(f"  AlpacaFeed: connected (feed={self._data_feed.value}, stream thread armed)",
              flush=True)

    def disconnect(self) -> None:
        self._connected = False
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass

    def isConnected(self) -> bool:
        # Alpaca clients have no persistent connection in the REST sense;
        # we report True as long as connect() was called and not torn down.
        # Stream-level health is monitored by the bot's tick-audit loop.
        return self._connected

    def managedAccounts(self) -> list[str]:
        """Mirror IB.managedAccounts (used for startup logging only)."""
        try:
            return ["ALPACA_PAPER"]
        except Exception:
            return []

    # ── Contract qualification (no-op for Alpaca) ───────────────────────
    def qualifyContracts(self, *contracts):
        """ib_insync requires contracts be qualified to a conId before use.
        Alpaca takes plain symbol strings; nothing to do."""
        return list(contracts)

    # ── Live tick subscription ──────────────────────────────────────────
    def reqMktData(self, contract, generic_ticks: str = "",
                   snapshot: bool = False, regulatory: bool = False) -> AlpacaTicker:
        """Subscribe to live trades for the contract's symbol. Returns an
        AlpacaTicker that the feed mutates in place on each trade event.

        generic_ticks/snapshot/regulatory are accepted for signature parity
        and ignored — Alpaca's free tier doesn't have IB's tick-type matrix."""
        symbol = self._symbol_of(contract)
        ticker = self._tickers.get(symbol)
        if ticker is None:
            ticker = AlpacaTicker(contract)
            self._tickers[symbol] = ticker

        with self._sub_lock:
            if symbol not in self._subscribed:
                # subscribe_trades is idempotent and safe mid-run; alpaca-py
                # internally calls _send_subscribe_msg when self._running.
                self._stream.subscribe_trades(self._on_trade, symbol)
                self._subscribed.add(symbol)
        return ticker

    def cancelMktData(self, contract) -> None:
        """Unsubscribe from live trades. Symbol's ticker stays around in case
        the bot retains the reference (cleanup on disconnect)."""
        symbol = self._symbol_of(contract)
        with self._sub_lock:
            if symbol in self._subscribed:
                try:
                    self._stream.unsubscribe_trades(symbol)
                except Exception as e:
                    print(f"⚠️ AlpacaFeed: unsubscribe {symbol} failed: {e}", flush=True)
                self._subscribed.discard(symbol)

    # ── Historical fetch — replaces IBKR's reqHistoricalTicks ──────────
    def reqHistoricalTicks(self, contract, startDateTime: str, endDateTime: str,
                           numberOfTicks: int, whatToShow: str = "TRADES",
                           useRth: bool = False, ignoreSize: bool = False) -> list:
        """Fetch historical trades from Alpaca. Returns a list of HistoricalTickStub.

        Pagination behavior differs slightly from IBKR:
          - IBKR: numberOfTicks ≤ 1000 per call, paginate by walking the time cursor.
          - Alpaca: paginates internally via next_page_token; returns all ticks
            in [start, end] up to numberOfTicks.

        The bot's seed_symbol uses up to 100 IBKR pages × 1000 ticks =
        100K-tick budget. We honor that here by capping `limit` at the
        bot's per-call value (it'll keep advancing the start cursor for
        very dense days, just as it does for IBKR)."""
        from alpaca.data.requests import StockTradesRequest

        symbol = self._symbol_of(contract)
        start_utc = _parse_ib_dtstr(startDateTime)
        end_utc = _parse_ib_dtstr(endDateTime) or datetime.now(timezone.utc)
        if start_utc is None:
            return []
        if end_utc <= start_utc:
            return []

        # Alpaca's limit param caps per-page response size. Cap at the bot's
        # request size (default 1000) to mirror IBKR pagination granularity.
        limit = max(1, min(int(numberOfTicks or 1000), 10_000))

        try:
            req = StockTradesRequest(
                symbol_or_symbols=symbol,
                start=start_utc, end=end_utc, limit=limit,
                feed=self._data_feed,
            )
            response = self._historical.get_stock_trades(req)
            # Response is a TradeSet — .data is dict[symbol, list[Trade]]
            trades = response.data.get(symbol, []) if hasattr(response, "data") else []
            out = []
            for t in trades:
                price = float(getattr(t, "price", 0) or 0)
                size = int(getattr(t, "size", 0) or 0)
                ts = getattr(t, "timestamp", None)
                if price <= 0 or size <= 0 or ts is None:
                    continue
                # Alpaca timestamps are tz-aware UTC datetimes
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                out.append(HistoricalTickStub(ts, price, size))
            return out
        except Exception as e:
            print(f"⚠️ AlpacaFeed.reqHistoricalTicks {symbol} failed: {e}", flush=True)
            return []

    def reqHistoricalData(self, contract, endDateTime: str = "",
                          durationStr: str = "1 D",
                          barSizeSetting: str = "1 min",
                          whatToShow: str = "TRADES",
                          useRTH: bool = False,
                          formatDate: int = 2) -> list:
        """Fetch historical bars from Alpaca (fallback path when ticks fail).
        Returns list of HistoricalBarStub. Maps IBKR durationStr → Alpaca
        StockBarsRequest start/end.

        Bar size mapping:
          "1 min"  → TimeFrame.Minute
          "5 mins" → TimeFrame(5, TimeFrameUnit.Minute)
          "1 day"  → TimeFrame.Day
        Anything more exotic isn't used by the bot."""
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        symbol = self._symbol_of(contract)
        end_utc = _parse_ib_dtstr(endDateTime) or datetime.now(timezone.utc)

        # Parse durationStr — formats observed in the bot: "1 D", "2 D", etc.
        from datetime import timedelta as _td
        dur_n, dur_unit = (durationStr.split() + ["D"])[:2]
        try:
            n = int(dur_n)
        except (ValueError, TypeError):
            n = 1
        unit = (dur_unit or "D").upper()[0]
        if unit == "S":
            start_utc = end_utc - _td(seconds=n)
        elif unit == "D":
            start_utc = end_utc - _td(days=n)
        elif unit == "W":
            start_utc = end_utc - _td(weeks=n)
        else:
            start_utc = end_utc - _td(days=n)

        # Bar size
        size = barSizeSetting.lower()
        if "min" in size:
            try:
                amount = int(size.split()[0])
            except (ValueError, IndexError):
                amount = 1
            tf = TimeFrame(amount, TimeFrameUnit.Minute) if amount != 1 else TimeFrame.Minute
        elif "hour" in size:
            tf = TimeFrame.Hour
        elif "day" in size:
            tf = TimeFrame.Day
        else:
            tf = TimeFrame.Minute

        try:
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                start=start_utc, end=end_utc, timeframe=tf,
                feed=self._data_feed,
            )
            response = self._historical.get_stock_bars(req)
            bars = response.data.get(symbol, []) if hasattr(response, "data") else []
            out = []
            for b in bars:
                ts = getattr(b, "timestamp", None)
                if ts is None:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                out.append(HistoricalBarStub(
                    date=ts,
                    open_=float(getattr(b, "open", 0) or 0),
                    high=float(getattr(b, "high", 0) or 0),
                    low=float(getattr(b, "low", 0) or 0),
                    close=float(getattr(b, "close", 0) or 0),
                    volume=int(getattr(b, "volume", 0) or 0),
                ))
            return out
        except Exception as e:
            print(f"⚠️ AlpacaFeed.reqHistoricalData {symbol} failed: {e}", flush=True)
            return []

    # ── Sleep / yield — drains queue + fires pendingTickersEvent ────────
    def sleep(self, seconds: float) -> None:
        """Yield for `seconds`. While yielding, drain queued live trades and
        dispatch them via pendingTickersEvent. Mirrors ib_insync.IB.sleep,
        which under the hood pumps the asyncio loop."""
        deadline = time.time() + max(0.0, float(seconds))
        # Always drain at least once even if seconds == 0 (for state.ib.sleep(0)
        # patterns the bot uses to yield to events).
        self._drain_once()
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 0.05))
            self._drain_once()

    def _drain_once(self) -> None:
        """Drain queued ticks, update tickers in place, fire pendingTickersEvent
        with the set of updated tickers."""
        updated: set[AlpacaTicker] = set()
        # Cap the per-drain work to keep the loop responsive even under heavy
        # tick rates (e.g. premarket runner with 10K trades/min).
        max_per_drain = 5000
        for _ in range(max_per_drain):
            try:
                ev = self._tick_queue.get_nowait()
            except queue.Empty:
                break
            symbol, price, size, ts_utc = ev
            ticker = self._tickers.get(symbol)
            if ticker is None:
                continue
            ticker.last = price
            ticker.lastSize = size
            ticker.time = ts_utc
            updated.add(ticker)
        if updated:
            self.pendingTickersEvent(updated)

    # ── Stream thread plumbing ──────────────────────────────────────────
    def _start_stream_thread(self) -> None:
        if self._stream_thread is not None and self._stream_thread.is_alive():
            return

        def _runner():
            try:
                # alpaca-py's run() calls asyncio.run(_run_forever()) — owns its
                # own loop. _run_forever spins until at least one subscription
                # is registered, then opens the WS.
                self._stream.run()
            except Exception as e:
                print(f"⚠️ AlpacaFeed stream thread crashed: {e}", flush=True)
                traceback.print_exc()
                # Surface to the bot via errorEvent so its watchdog notices.
                try:
                    self.errorEvent(0, 0, str(e), None)
                except Exception:
                    pass

        self._stream_thread = threading.Thread(
            target=_runner, daemon=True, name="alpaca-stream",
        )
        self._stream_thread.start()
        # Mark started — the thread is up and run() is being invoked. Actual
        # WS connection happens when the first subscribe lands.
        self._stream_started.set()

    async def _on_trade(self, trade) -> None:
        """Coroutine handler registered with subscribe_trades. Runs on the
        stream's asyncio loop. Enqueues for main-thread consumption."""
        try:
            symbol = getattr(trade, "symbol", "")
            price = float(getattr(trade, "price", 0) or 0)
            size = int(getattr(trade, "size", 0) or 0)
            ts = getattr(trade, "timestamp", None)
            if not symbol or price <= 0 or size <= 0:
                return
            if ts is None:
                ts = datetime.now(timezone.utc)
            elif ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            try:
                self._tick_queue.put_nowait((symbol, price, size, ts))
            except queue.Full:
                # Drop on the floor; the audit loop will catch sustained drops.
                pass
        except Exception as e:
            print(f"⚠️ AlpacaFeed _on_trade error: {e}", flush=True)

    # ── Helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _symbol_of(contract) -> str:
        if hasattr(contract, "symbol"):
            return contract.symbol.upper()
        return str(contract).upper()

    # ── IB-only methods the bot may incidentally call. We provide stubs
    #     that don't crash; squeeze path doesn't actually exercise these. ─
    def trades(self) -> list:
        """ib_insync.IB.trades — returns list of Trade objects from the IB
        side. Order flow goes through state.broker (AlpacaBroker), not here,
        so this is a stub returning empty."""
        return []

    def positions(self) -> list:
        return []

    def portfolio(self) -> list:
        return []

    def accountValues(self) -> list:
        return []

    def reqGlobalCancel(self) -> None:
        pass
