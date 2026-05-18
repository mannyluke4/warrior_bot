"""databento_live_feed.py — drop-in replacement for ib_insync.IB market-data
layer, backed by Databento's Live SDK.

Mirrors the subset of ib_insync's IB API that bot_alpaca_subbot.py uses for
tick subscription, historical fetch, and connection lifecycle. The shape is
intentionally identical to alpaca_feed.AlpacaFeed so the subbot can swap
backends via WB_SUBBOT_DATA_FEED env without touching any call site.

Design constraint: every method/attribute the bot reaches for on `state.ib`
exists here with the same name and roughly the same shape. The bot reads
`ticker.last`, `ticker.lastSize`, `ticker.time`, calls `state.ib.sleep(N)`,
and registers handlers on `pendingTickersEvent` / `errorEvent` — all
preserved.

Threading model:
  - Stream thread (daemon, named "databento-stream") owns the db.Live()
    session. Databento's add_callback is a synchronous callback fired on
    its internal reader thread; we DON'T do work there. We push (symbol,
    price, size, ts) tuples to `_tick_queue`.
  - Main thread calls `sleep(N)` which drains the queue, updates ticker
    objects in place, and fires `pendingTickersEvent` with the updated
    set — same shape ib_insync delivers.
  - All ticker mutations and event dispatch happen on the main thread.

Architectural notes (per Step 0 GREEN reconnaissance,
cowork_reports/2026-05-18_databento_subscription_limits.md):
  - One db.Live() session for the entire watchlist. No Tier 1/Tier 2.
  - Databento has no IBKR-style per-session symbol cap. Flat subscription.
  - reconnect_policy="reconnect" + add_reconnect_callback give us auto-
    recovery and gap-replay timestamps for client-side bridging.
  - ts_out=True so we have gateway send-time timestamps for latency diag.
  - No unsubscribe() API. When symbols drop, we mark them ignored client-
    side; the stream keeps flowing for them but trades are dropped.
  - Mid-session symbol add: extra subscribe(...) call after .start() is
    safe (Q4 of the reconnaissance). The SDK appends to the existing
    subscription_requests list.

Order execution (AlpacaBroker via TradingClient) is NOT in this module —
broker.py already handles that. This module is data-feed only.
"""

from __future__ import annotations

import os
import queue
import threading
import time
import traceback
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

# ─────────────────────────────────────────────────────────────────────
# IB-shape stubs the bot expects to receive
# (kept name-compatible with alpaca_feed.py for interchangeable use)
# ─────────────────────────────────────────────────────────────────────


class StockContract:
    """Drop-in for ib_insync.Stock. Bot only reads .symbol; the other fields
    exist for signature parity (`Stock(symbol, 'SMART', 'USD')`)."""
    __slots__ = ("symbol", "exchange", "currency", "conId")

    def __init__(self, symbol: str, exchange: str = "SMART", currency: str = "USD"):
        self.symbol = symbol.upper()
        self.exchange = exchange
        self.currency = currency
        self.conId = 0

    def __repr__(self) -> str:
        return f"StockContract({self.symbol!r})"


# Alias so `from databento_live_feed import Stock` works as `from ib_insync import Stock`
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
    .close, .volume."""
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


class DatabentoTicker:
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
        return f"DatabentoTicker({sym}, last={last}, size={self.lastSize})"


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
                print(f"⚠️ DatabentoLiveFeed event[{self._name}] handler "
                      f"{getattr(h, '__name__', repr(h))} raised: {e}", flush=True)
                traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────
# Datetime parsing — IBKR's reqHistoricalTicks signature uses string dates
# (re-implemented here so this module is self-contained, identical to
# alpaca_feed._parse_ib_dtstr)
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
# DatabentoLiveFeed — the IB() drop-in
# ─────────────────────────────────────────────────────────────────────


class DatabentoLiveFeed:
    """Drop-in replacement for ib_insync.IB, backed by Databento Live SDK.

    Lifecycle:
      feed = DatabentoLiveFeed()
      feed.connect()                                           # opens db.Live, starts stream thread
      ticker = feed.reqMktData(Stock("AAPL"), "233", False, False)
      feed.sleep(0.5)                                          # drains queue, fires pendingTickersEvent
      feed.cancelMktData(Stock("AAPL"))                        # mark ignored (no real unsubscribe)
      feed.disconnect()

    Env vars:
      DATABENTO_API_KEY                — required; passed to db.Live(key=...)
      WB_DATABENTO_DATASET             — default "XNAS.ITCH" (Step 0 §5: 2-5x denser than EQUS.MINI/DBEQ.BASIC for microcaps)
      WB_DATABENTO_SCHEMA              — default "trades"
      WB_DATABENTO_HEARTBEAT_S         — optional override of SDK default (~30s)
    """

    DEFAULT_DATASET = "XNAS.ITCH"
    DEFAULT_SCHEMA = "trades"

    def __init__(self):
        self._connected = False
        self._live = None           # databento.Live instance
        self._historical = None     # databento.Historical instance (lazy)
        self._stream_thread: Optional[threading.Thread] = None
        self._stream_started = threading.Event()
        self._started_live_session = False  # tracks whether .start() has been called
        # Tick events from the SDK callback thread → drained by main thread in sleep()
        self._tick_queue: queue.Queue = queue.Queue(maxsize=200_000)
        self._tickers: dict[str, DatabentoTicker] = {}        # symbol → live DatabentoTicker
        # Active symbols we currently care about — events for symbols NOT in
        # this set are silently dropped (no Databento unsubscribe API).
        self._active_symbols: set[str] = set()
        # All symbols that have ever been subscribed since process start.
        # On reconnect, we re-subscribe everything in `_active_symbols` (a
        # subset of this) so dropped/cancelled symbols don't come back.
        self._subscribed_symbols: set[str] = set()
        # Lock guards mutations across main + stream threads
        self._sub_lock = threading.Lock()
        # instrument_id → symbol mapping populated from SymbolMappingMsg.
        # Some Databento schemas only carry instrument_id on TradeMsg, not
        # the raw symbol; we map back via this dict.
        self._inst_to_symbol: dict[int, str] = {}
        # Last ts_event we saw (any record) — used in the reconnect callback
        # to compute the gap window for the consumer's bridging logic.
        self._last_record_ts: Optional[datetime] = None
        # Dataset + schema (read at connect() time so env can drive it)
        self._dataset = os.getenv("WB_DATABENTO_DATASET", self.DEFAULT_DATASET)
        self._schema = os.getenv("WB_DATABENTO_SCHEMA", self.DEFAULT_SCHEMA)

        # Events the bot registers handlers on
        self.pendingTickersEvent = _Event("pendingTickers")
        self.errorEvent = _Event("error")

    # ── Connection lifecycle ────────────────────────────────────────────
    def connect(self, host: str = None, port: int = None, clientId: int = None) -> None:
        """Initialize the db.Live() session and start the stream thread.
        host/port/clientId are accepted for signature parity with IB.connect
        but ignored — Databento uses API keys."""
        try:
            import databento as db
        except ImportError as e:
            raise RuntimeError(
                "DatabentoLiveFeed.connect: 'databento' package not installed. "
                "Run: pip install databento"
            ) from e

        api_key = os.getenv("DATABENTO_API_KEY")
        if not api_key:
            raise RuntimeError(
                "DatabentoLiveFeed.connect: DATABENTO_API_KEY missing from "
                "environment. Check .env or pass via daily_run_v3.sh."
            )

        # Heartbeat override (rare; SDK default is ~30s).
        hb_raw = os.getenv("WB_DATABENTO_HEARTBEAT_S", "").strip()
        hb_kwargs = {}
        if hb_raw:
            try:
                hb = int(hb_raw)
                if hb >= 5:
                    hb_kwargs["heartbeat_interval_s"] = hb
            except ValueError:
                pass

        # ts_out=True: gateway send-time on every record, sub-second precision
        # for latency diagnostics vs Setup A.
        # reconnect_policy="reconnect": auto-recover from drops; our callback
        # will be fired with the pre/post-disconnect timestamps so the
        # consumer can bridge the gap via historical (mirrors Setup A's
        # session_resume_deployed pattern).
        # slow_reader_behavior="warn": default; surface SLOW_READER_WARNING
        # SystemMsg in the bot log instead of silently dropping.
        self._live = db.Live(
            key=api_key,
            ts_out=True,
            reconnect_policy="reconnect",
            slow_reader_behavior="warn",
            **hb_kwargs,
        )

        # Register callbacks BEFORE start() so we don't miss the first records.
        self._live.add_callback(self._on_record, exception_callback=self._on_callback_exc)
        try:
            self._live.add_reconnect_callback(
                self._on_reconnect, exception_callback=self._on_callback_exc
            )
        except Exception as e:
            # Older SDKs may not expose add_reconnect_callback; non-fatal.
            print(f"⚠️ DatabentoLiveFeed: add_reconnect_callback unavailable ({e}); "
                  f"reconnect events will not be surfaced.", flush=True)

        # Lazy historical client (only built when reqHistoricalTicks is called).
        self._historical = None
        self._connected = True

        # Stream thread will call .start() AFTER the first subscribe lands —
        # mirrors the alpaca_feed.py "stream armed; activates on first
        # subscription" semantics. We start the thread here but it won't
        # actually run anything until subscribe + start fire.
        self._start_stream_thread()
        print(
            f"  DatabentoLiveFeed: connected "
            f"(dataset={self._dataset}, schema={self._schema}, ts_out=on, "
            f"reconnect=on, slow_reader=warn, stream thread armed)",
            flush=True,
        )

    def disconnect(self) -> None:
        """Tear down the db.Live() session. Ticker objects remain in memory
        in case the consumer retains references; future ticks are dropped."""
        self._connected = False
        live = self._live
        if live is not None:
            try:
                # stop() is the graceful shutdown — it closes the TCP session
                # and unblocks the reader. wait_for_close is optional; the
                # daemon thread will exit on its own as the iterator drains.
                live.stop()
            except Exception:
                pass

    def isConnected(self) -> bool:
        """Reflect Databento's view of session health. is_connected() is the
        SDK's authoritative method; we fall back to our own _connected
        flag if the session hasn't been started yet."""
        if not self._connected:
            return False
        live = self._live
        if live is None:
            return False
        # Pre-start: stream thread hasn't called .start() yet because no
        # subscribe has happened. We report True because we're "ready",
        # mirroring IB.isConnected() which returns True after IB.connect()
        # succeeds even before any market-data subscription.
        if not self._started_live_session:
            return True
        try:
            return bool(live.is_connected())
        except Exception:
            return False

    def managedAccounts(self) -> list[str]:
        """Mirror IB.managedAccounts (used for startup logging only). Databento
        is a data feed, not a broker; return a single dummy account id so the
        subbot's startup-print line doesn't crash."""
        return ["DATABENTO"]

    # ── Contract qualification (no-op for Databento) ────────────────────
    def qualifyContracts(self, *contracts):
        """ib_insync requires contracts be qualified to a conId before use.
        Databento takes plain symbol strings; nothing to do here."""
        return list(contracts)

    # ── Live tick subscription ──────────────────────────────────────────
    def reqMktData(self, contract, generic_ticks: str = "",
                   snapshot: bool = False, regulatory: bool = False,
                   mktDataOptions=None) -> DatabentoTicker:
        """Subscribe to live trades for the contract's symbol. Returns a
        DatabentoTicker that the feed mutates in place on each trade event.

        generic_ticks / snapshot / regulatory / mktDataOptions are accepted
        for signature parity and ignored — Databento exposes one stream
        type (the dataset+schema pair) per Live session."""
        symbol = self._symbol_of(contract)
        ticker = self._tickers.get(symbol)
        if ticker is None:
            ticker = DatabentoTicker(contract)
            self._tickers[symbol] = ticker

        self._subscribe(symbol)
        return ticker

    def reqTickByTickData(self, contract, tickType: str = "AllLast",
                          numberOfTicks: int = 0, ignoreSize: bool = False
                          ) -> DatabentoTicker:
        """IBKR's tick-by-tick variant. Databento's `trades` schema IS per-
        print tick-by-tick data — equivalent to IBKR's 'AllLast'. We collapse
        reqTickByTickData onto the same subscription as reqMktData (one
        DatabentoTicker per symbol, updated in place).

        Matches alpaca_feed.py's behavior — both report the same ticker
        object regardless of which API the bot called."""
        symbol = self._symbol_of(contract)
        ticker = self._tickers.get(symbol)
        if ticker is None:
            ticker = DatabentoTicker(contract)
            self._tickers[symbol] = ticker

        self._subscribe(symbol)
        return ticker

    def cancelMktData(self, contract) -> None:
        """Mark symbol as ignored. Databento has no unsubscribe API; trades
        for the symbol will still arrive from the gateway, but the callback
        drops them. The ticker object stays in self._tickers in case the
        bot retains a reference (cleanup happens in disconnect())."""
        symbol = self._symbol_of(contract)
        with self._sub_lock:
            self._active_symbols.discard(symbol)

    def cancelTickByTickData(self, contract, tickType: str = "AllLast") -> None:
        """Same semantics as cancelMktData — single subscription per symbol."""
        self.cancelMktData(contract)

    # ── Historical fetch — proxies to Databento historical ──────────────
    def reqHistoricalTicks(self, contract, startDateTime: str, endDateTime: str,
                           numberOfTicks: int, whatToShow: str = "TRADES",
                           useRth: bool = False, ignoreSize: bool = False) -> list:
        """Fetch historical trades from Databento. Returns a list of
        HistoricalTickStub objects sorted by time, IBKR-shape.

        The subbot uses this for seed (4 AM ET → now) and gap-bridge
        (disconnect window). We honor numberOfTicks as a soft cap but
        otherwise return everything in [start, end] — Databento doesn't
        page like IBKR does.

        Falls through to XNYS.PILLAR on initial fetch failure for the
        NASDAQ default — mirrors databento_feed.py's existing pattern."""
        api_key = os.getenv("DATABENTO_API_KEY")
        if not api_key:
            print("⚠️ DatabentoLiveFeed.reqHistoricalTicks: DATABENTO_API_KEY "
                  "missing — cannot fetch", flush=True)
            return []
        try:
            import databento as db
        except ImportError:
            print("⚠️ DatabentoLiveFeed.reqHistoricalTicks: databento not installed",
                  flush=True)
            return []

        if self._historical is None:
            self._historical = db.Historical(key=api_key)

        symbol = self._symbol_of(contract)
        start_utc = _parse_ib_dtstr(startDateTime)
        end_utc = _parse_ib_dtstr(endDateTime) or datetime.now(timezone.utc)
        if start_utc is None:
            return []
        if end_utc <= start_utc:
            return []

        # Databento historical only accepts ISO/datetime — use the same
        # format databento_feed.py uses.
        start_str = start_utc.strftime("%Y-%m-%dT%H:%M")
        end_str = end_utc.strftime("%Y-%m-%dT%H:%M")

        dataset = self._dataset
        out: list[HistoricalTickStub] = []
        try:
            data = self._historical.timeseries.get_range(
                dataset=dataset,
                schema="trades",
                symbols=[symbol],
                start=start_str,
                end=end_str,
                stype_in="raw_symbol",
            )
            df = data.to_df() if hasattr(data, "to_df") else None
            if df is None or df.empty:
                return []
            cap = max(1, int(numberOfTicks or 1000))
            count = 0
            for idx, row in df.iterrows():
                ts = idx if isinstance(idx, datetime) else row.get("ts_event", idx)
                if isinstance(ts, (int, float)):
                    ts = datetime.fromtimestamp(ts / 1e9, tz=timezone.utc)
                elif hasattr(ts, "tzinfo") and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                price = float(row.get("price", 0) or 0)
                if price > 1e6:
                    price = price / 1e9
                size = int(row.get("size", 0) or 0)
                if price <= 0 or size <= 0:
                    continue
                out.append(HistoricalTickStub(ts, price, size))
                count += 1
                if count >= cap:
                    break
            return out
        except Exception as e:
            print(f"⚠️ DatabentoLiveFeed.reqHistoricalTicks {symbol} failed: {e}",
                  flush=True)
            return []

    def reqHistoricalData(self, contract, endDateTime: str = "",
                          durationStr: str = "1 D",
                          barSizeSetting: str = "1 min",
                          whatToShow: str = "TRADES",
                          useRTH: bool = False,
                          formatDate: int = 2) -> list:
        """Fallback path — most subbot seed code uses reqHistoricalTicks.
        Builds a synthetic bar list from the historical trades response.
        Used only when the tick path fails. Returns HistoricalBarStub."""
        api_key = os.getenv("DATABENTO_API_KEY")
        if not api_key:
            return []
        try:
            import databento as db
        except ImportError:
            return []

        if self._historical is None:
            self._historical = db.Historical(key=api_key)

        symbol = self._symbol_of(contract)
        end_utc = _parse_ib_dtstr(endDateTime) or datetime.now(timezone.utc)

        # Parse durationStr — "1 D", "2 D", etc.
        dur_n, dur_unit = (durationStr.split() + ["D"])[:2]
        try:
            n = int(dur_n)
        except (ValueError, TypeError):
            n = 1
        unit = (dur_unit or "D").upper()[0]
        if unit == "S":
            start_utc = end_utc - timedelta(seconds=n)
        elif unit == "D":
            start_utc = end_utc - timedelta(days=n)
        elif unit == "W":
            start_utc = end_utc - timedelta(weeks=n)
        else:
            start_utc = end_utc - timedelta(days=n)

        # Determine bar duration in seconds.
        size = barSizeSetting.lower()
        if "min" in size:
            try:
                amount = int(size.split()[0])
            except (ValueError, IndexError):
                amount = 1
            bar_secs = amount * 60
        elif "hour" in size:
            bar_secs = 3600
        elif "day" in size:
            bar_secs = 86400
        else:
            bar_secs = 60

        try:
            data = self._historical.timeseries.get_range(
                dataset=self._dataset,
                schema="trades",
                symbols=[symbol],
                start=start_utc.strftime("%Y-%m-%dT%H:%M"),
                end=end_utc.strftime("%Y-%m-%dT%H:%M"),
                stype_in="raw_symbol",
            )
            df = data.to_df() if hasattr(data, "to_df") else None
            if df is None or df.empty:
                return []
            # Aggregate trades into bars by bar_secs window.
            bars: dict[int, dict] = {}
            for idx, row in df.iterrows():
                ts = idx if isinstance(idx, datetime) else row.get("ts_event", idx)
                if isinstance(ts, (int, float)):
                    ts = datetime.fromtimestamp(ts / 1e9, tz=timezone.utc)
                elif hasattr(ts, "tzinfo") and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                price = float(row.get("price", 0) or 0)
                if price > 1e6:
                    price = price / 1e9
                sz = int(row.get("size", 0) or 0)
                if price <= 0 or sz <= 0:
                    continue
                bucket = int(ts.timestamp() // bar_secs) * bar_secs
                b = bars.get(bucket)
                if b is None:
                    bars[bucket] = {"o": price, "h": price, "l": price,
                                    "c": price, "v": sz, "t": ts}
                else:
                    b["h"] = max(b["h"], price)
                    b["l"] = min(b["l"], price)
                    b["c"] = price
                    b["v"] += sz
            out = []
            for bucket in sorted(bars.keys()):
                b = bars[bucket]
                out.append(HistoricalBarStub(
                    date=b["t"], open_=b["o"], high=b["h"],
                    low=b["l"], close=b["c"], volume=b["v"],
                ))
            return out
        except Exception as e:
            print(f"⚠️ DatabentoLiveFeed.reqHistoricalData {symbol} failed: {e}",
                  flush=True)
            return []

    # ── Sleep / yield — drains queue + fires pendingTickersEvent ────────
    def sleep(self, seconds: float) -> None:
        """Yield for `seconds`. While yielding, drain queued live trades and
        dispatch them via pendingTickersEvent. Mirrors ib_insync.IB.sleep,
        which under the hood pumps the asyncio loop."""
        deadline = time.time() + max(0.0, float(seconds))
        # Always drain at least once even if seconds == 0.
        self._drain_once()
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 0.05))
            self._drain_once()

    def _drain_once(self) -> None:
        """Drain queued ticks, update tickers in place, fire pendingTickersEvent."""
        updated: set[DatabentoTicker] = set()
        # Cap per-drain work to keep the loop responsive even under heavy
        # tick rates (premarket runner with thousands of trades/min).
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

    # ── Subscription plumbing ───────────────────────────────────────────
    def _subscribe(self, symbol: str) -> None:
        """Add `symbol` to the live subscription. Idempotent — repeated calls
        are silent. First call kicks off the stream's .start()."""
        first_subscribe = False
        with self._sub_lock:
            self._active_symbols.add(symbol)
            if symbol not in self._subscribed_symbols:
                self._subscribed_symbols.add(symbol)
                first_subscribe = True

        if not first_subscribe:
            # Already on the wire — nothing to do.
            return

        if self._live is None:
            print(f"⚠️ DatabentoLiveFeed._subscribe({symbol}): live session "
                  f"not initialized (call connect() first)", flush=True)
            return

        try:
            # Step 0 §4: mid-session subscribe() calls are safe. The SDK
            # appends a new SubscriptionRequest to the existing TCP session.
            self._live.subscribe(
                dataset=self._dataset,
                schema=self._schema,
                symbols=[symbol],
                stype_in="raw_symbol",
            )
        except Exception as e:
            print(f"⚠️ DatabentoLiveFeed: subscribe({symbol}) failed: {e}", flush=True)
            return

        # Lazy-start the stream once the first subscribe lands. After this
        # point, .subscribe() calls continue to add to the same session.
        if not self._started_live_session:
            try:
                self._live.start()
                self._started_live_session = True
                self._stream_started.set()
                print(
                    f"  DatabentoLiveFeed: live session started "
                    f"(first subscribe: {symbol})",
                    flush=True,
                )
            except Exception as e:
                print(f"⚠️ DatabentoLiveFeed.start failed: {e}", flush=True)

    # ── Stream thread plumbing ──────────────────────────────────────────
    def _start_stream_thread(self) -> None:
        """Watchdog thread — currently a no-op placeholder. The Databento
        SDK runs its own reader thread internally; this thread just exists
        for symmetry with alpaca_feed.py and as a future hook for stream-
        level health monitoring."""
        if self._stream_thread is not None and self._stream_thread.is_alive():
            return

        def _runner():
            # Idle loop — the SDK handles reads. We're here mostly so the
            # bot has something to grep for ("databento-stream" in ps -ef).
            while self._connected:
                time.sleep(1.0)

        self._stream_thread = threading.Thread(
            target=_runner, daemon=True, name="databento-stream",
        )
        self._stream_thread.start()
        self._stream_started.set()

    # ── SDK callback (runs on Databento's internal reader thread) ───────
    def _on_record(self, record) -> None:
        """Synchronous callback invoked by db.Live for every incoming record.
        Filter to trades, resolve symbol, enqueue for main-thread consumption.

        We DO NOT mutate the ticker or fire pendingTickersEvent here — that
        would race the main thread. See class docstring for the threading
        model."""
        try:
            rtype = type(record).__name__

            # SymbolMappingMsg: caches instrument_id → raw symbol. Always
            # populate, even for instruments we've discarded — cheap.
            if rtype == "SymbolMappingMsg":
                inst_id = getattr(record, "instrument_id", None)
                in_sym = getattr(record, "stype_in_symbol", None)
                if inst_id is not None and in_sym:
                    self._inst_to_symbol[int(inst_id)] = str(in_sym).upper()
                return

            # SystemMsg: heartbeats + SLOW_READER_WARNING + REPLAY_COMPLETED.
            # Surface slow-reader warnings to the bot log so backpressure
            # incidents are visible.
            if rtype == "SystemMsg":
                code = getattr(record, "code", None)
                # SystemCode.SLOW_READER_WARNING (numeric value varies by
                # databento-dbn version). Use the textual msg field, which
                # is human-readable and stable.
                msg = getattr(record, "msg", "") or ""
                if "slow" in msg.lower() or "slow_reader" in str(code).lower():
                    print(f"⚠️ DatabentoLiveFeed: SLOW_READER_WARNING from "
                          f"gateway: {msg!r}", flush=True)
                return

            # ErrorMsg: surface to the bot via errorEvent (matches IB's
            # errorEvent(reqId, errorCode, errorString, contract) shape).
            if rtype == "ErrorMsg":
                code = getattr(record, "code", 0)
                err = getattr(record, "err", "") or ""
                print(f"⚠️ DatabentoLiveFeed: ErrorMsg code={code} err={err!r}",
                      flush=True)
                try:
                    self.errorEvent(0, int(code) if code is not None else 0,
                                    str(err), None)
                except Exception:
                    pass
                return

            # TradeMsg (or Mbp0Msg — equivalent shape for the trades schema).
            # `price` is fixed-point i64 (×1e9); `size` is u32; `ts_event`
            # is nanoseconds since epoch.
            if rtype in ("TradeMsg", "Mbp0Msg"):
                inst_id = getattr(record, "instrument_id", None)
                symbol = self._inst_to_symbol.get(int(inst_id)) if inst_id is not None else None
                if symbol is None:
                    # Haven't seen the SymbolMappingMsg yet (race on first
                    # subscribe); skip — next trade will catch it.
                    return
                # Filter: drop ticks for symbols the consumer has cancelled.
                # We can't unsubscribe at the gateway (no Databento API),
                # but we can drop client-side.
                with self._sub_lock:
                    if symbol not in self._active_symbols:
                        return
                price_raw = getattr(record, "price", 0)
                # databento_dbn returns price as fixed-point int (×1e9).
                # Handle either fixed-point or already-float.
                price = float(price_raw) / 1e9 if abs(price_raw) > 1e6 else float(price_raw)
                size = int(getattr(record, "size", 0) or 0)
                ts_ns = getattr(record, "ts_event", None)
                if ts_ns is None:
                    ts_utc = datetime.now(timezone.utc)
                else:
                    ts_utc = datetime.fromtimestamp(int(ts_ns) / 1e9, tz=timezone.utc)
                self._last_record_ts = ts_utc
                if price <= 0 or size <= 0:
                    return
                try:
                    self._tick_queue.put_nowait((symbol, price, size, ts_utc))
                except queue.Full:
                    # Backpressure-drop. The next sleep() drain will catch up.
                    pass
                return

            # Anything else (unknown record types from a newer SDK): record
            # the timestamp for gap calculations but otherwise ignore.
            ts_ns = getattr(record, "ts_event", None)
            if ts_ns is not None:
                try:
                    self._last_record_ts = datetime.fromtimestamp(
                        int(ts_ns) / 1e9, tz=timezone.utc
                    )
                except Exception:
                    pass
        except Exception as e:
            # Never let the SDK reader thread die — it owns the TCP session.
            print(f"⚠️ DatabentoLiveFeed._on_record error: {e}", flush=True)
            traceback.print_exc()

    def _on_callback_exc(self, exc: Exception) -> None:
        """Exception callback registered with add_callback / add_reconnect_callback.
        Mirrors IB.errorEvent semantics."""
        print(f"⚠️ DatabentoLiveFeed callback exception: {exc!r}", flush=True)
        try:
            self.errorEvent(0, 0, str(exc), None)
        except Exception:
            pass

    def _on_reconnect(self, last_ts, new_ts) -> None:
        """Fired by db.Live when the auto-reconnect policy kicks in.

        `last_ts` is the last ts_event from the disconnected session;
        `new_ts` is the Metadata.start of the new session. Both are
        pandas.Timestamp. We log the gap window so the consumer's session-
        resume / gap-bridge logic can back-fill via historical (mirrors
        Setup A's session_resume_deployed pattern).

        Note: per Step 0 §8, the SDK's `subscription_requests` list is
        retained across reconnects and the gateway-side re-subscription
        is handled by the SDK itself. We don't need to re-call subscribe()
        here — but if a future SDK version changes that, this is the place
        to do it."""
        try:
            last_str = str(last_ts) if last_ts is not None else "?"
            new_str = str(new_ts) if new_ts is not None else "?"
            print(
                f"  ⚠️ DatabentoLiveFeed: RECONNECTED gap={last_str} → {new_str} "
                f"(symbols={len(self._active_symbols)})",
                flush=True,
            )
        except Exception as e:
            print(f"⚠️ DatabentoLiveFeed._on_reconnect log error: {e}", flush=True)

    # ── Helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _symbol_of(contract) -> str:
        if hasattr(contract, "symbol"):
            return contract.symbol.upper()
        return str(contract).upper()

    # ── IB-only methods the bot may incidentally call. Provided as stubs
    #     that don't crash; squeeze path doesn't actually exercise these
    #     for the data-feed side. Order flow goes through state.broker. ─
    def trades(self) -> list:
        return []

    def positions(self) -> list:
        return []

    def portfolio(self) -> list:
        return []

    def accountValues(self) -> list:
        return []

    def reqGlobalCancel(self) -> None:
        pass
