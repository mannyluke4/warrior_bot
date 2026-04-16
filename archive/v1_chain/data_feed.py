"""
DataFeed abstraction layer.

Decouples market data ingestion from trade execution.
Allows switching between Alpaca, IBKR, or Databento via WB_DATA_FEED env var.

Trade callback signature: callback(symbol: str, price: float, size: int, timestamp: datetime)
Quote callback signature: callback(symbol: str, bid: float|None, ask: float|None, timestamp: datetime)
All timestamps are timezone-aware UTC datetimes.
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Callable, Optional


class DataFeed(ABC):
    """Abstract interface for live market data feeds."""

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the data source. Returns True on success."""
        ...

    @abstractmethod
    def subscribe_trades(self, symbol: str, callback: Callable) -> None:
        """Subscribe to trade updates for a symbol."""
        ...

    @abstractmethod
    def subscribe_quotes(self, symbol: str, callback: Callable) -> None:
        """Subscribe to quote updates for a symbol."""
        ...

    @abstractmethod
    def unsubscribe_trades(self, symbol: str) -> None:
        """Unsubscribe from trade updates for a symbol."""
        ...

    @abstractmethod
    def unsubscribe_quotes(self, symbol: str) -> None:
        """Unsubscribe from quote updates for a symbol."""
        ...

    @abstractmethod
    def run(self) -> None:
        """Start the data feed event loop (blocking)."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop the data feed."""
        ...


# ---------------------------------------------------------------------------
# Alpaca implementation (wraps existing StockDataStream)
# ---------------------------------------------------------------------------

class AlpacaFeed(DataFeed):
    """Live market data via Alpaca websocket.

    This is the existing behavior, wrapped in the DataFeed interface.
    Normalizes Alpaca trade/quote objects into clean callback args.
    """

    def __init__(self, api_key: str, api_secret: str):
        from alpaca.data.live import StockDataStream
        from alpaca.data.enums import DataFeed as AlpacaDataFeed
        self._stream = StockDataStream(api_key, api_secret, feed=AlpacaDataFeed.SIP)

    def connect(self) -> bool:
        return True  # Alpaca connects lazily on run()

    def subscribe_trades(self, symbol: str, callback: Callable) -> None:
        async def _handler(trade):
            sym = getattr(trade, "symbol", None)
            if not sym:
                return
            px = float(getattr(trade, "price", 0) or 0)
            sz = int(getattr(trade, "size", 0) or 0)
            ts = getattr(trade, "timestamp", None) or getattr(trade, "t", None)
            if ts is None:
                ts = datetime.now(timezone.utc)
            elif isinstance(ts, datetime) and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            callback(sym, px, sz, ts)

        self._stream.subscribe_trades(_handler, symbol)

    def subscribe_quotes(self, symbol: str, callback: Callable) -> None:
        async def _handler(q):
            sym = getattr(q, "symbol", None)
            if not sym:
                return
            bid = float(getattr(q, "bid_price", 0) or 0) or None
            ask = float(getattr(q, "ask_price", 0) or 0) or None
            ts = getattr(q, "timestamp", None) or getattr(q, "t", None)
            if ts is None:
                ts = datetime.now(timezone.utc)
            elif isinstance(ts, datetime) and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            callback(sym, bid, ask, ts)

        self._stream.subscribe_quotes(_handler, symbol)

    def unsubscribe_trades(self, symbol: str) -> None:
        self._stream.unsubscribe_trades(symbol)

    def unsubscribe_quotes(self, symbol: str) -> None:
        self._stream.unsubscribe_quotes(symbol)

    def run(self) -> None:
        self._stream.run()

    def stop(self) -> None:
        self._stream.stop()


# ---------------------------------------------------------------------------
# IBKR implementation (skeleton — activate when account is approved)
# ---------------------------------------------------------------------------

class IBKRDataFeed(DataFeed):
    """Live L1 trades + quotes via IB Gateway / ib_insync.

    Requires IB Gateway or TWS running locally.
    Uses reqTickByTickData for trade prints and bid/ask updates.
    """

    def __init__(self, host: str = None, port: int = None, client_id: int = None):
        self._host = host or os.getenv("WB_IBKR_HOST", "127.0.0.1")
        self._port = int(port or os.getenv("WB_IBKR_PORT", "7497"))
        self._client_id = int(client_id or os.getenv("WB_IBKR_CLIENT_ID_DATA", "2"))
        self._ib = None
        self._contracts = {}
        self._trade_callbacks = {}
        self._quote_callbacks = {}

    def connect(self) -> bool:
        try:
            from ib_insync import IB
            self._ib = IB()
            self._ib.connect(self._host, self._port, clientId=self._client_id)
            return self._ib.isConnected()
        except Exception as e:
            print(f"IBKR DataFeed connect failed: {e}", flush=True)
            return False

    def subscribe_trades(self, symbol: str, callback: Callable) -> None:
        from ib_insync import Stock
        if symbol not in self._contracts:
            contract = Stock(symbol, 'SMART', 'USD')
            self._ib.qualifyContracts(contract)
            self._contracts[symbol] = contract

        self._trade_callbacks[symbol] = callback
        ticker = self._ib.reqTickByTickData(self._contracts[symbol], 'AllLast')
        ticker.updateEvent += lambda t, sym=symbol: self._on_trade_tick(sym, t)

    def subscribe_quotes(self, symbol: str, callback: Callable) -> None:
        from ib_insync import Stock
        if symbol not in self._contracts:
            contract = Stock(symbol, 'SMART', 'USD')
            self._ib.qualifyContracts(contract)
            self._contracts[symbol] = contract

        self._quote_callbacks[symbol] = callback
        ticker = self._ib.reqTickByTickData(self._contracts[symbol], 'BidAsk')
        ticker.updateEvent += lambda t, sym=symbol: self._on_quote_tick(sym, t)

    def _on_trade_tick(self, symbol: str, ticker):
        cb = self._trade_callbacks.get(symbol)
        if not cb:
            return
        for tick in ticker.tickByTickAllLast:
            ts = tick.time
            if isinstance(ts, datetime) and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            cb(symbol, float(tick.price), int(tick.size), ts)

    def _on_quote_tick(self, symbol: str, ticker):
        cb = self._quote_callbacks.get(symbol)
        if not cb:
            return
        for tick in ticker.tickByTickBidAsk:
            ts = tick.time
            if isinstance(ts, datetime) and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            bid = float(tick.bidPrice) if tick.bidPrice > 0 else None
            ask = float(tick.askPrice) if tick.askPrice > 0 else None
            cb(symbol, bid, ask, ts)

    def unsubscribe_trades(self, symbol: str) -> None:
        if symbol in self._contracts and self._ib:
            self._ib.cancelTickByTickData(self._contracts[symbol], 'AllLast')
        self._trade_callbacks.pop(symbol, None)

    def unsubscribe_quotes(self, symbol: str) -> None:
        if symbol in self._contracts and self._ib:
            self._ib.cancelTickByTickData(self._contracts[symbol], 'BidAsk')
        self._quote_callbacks.pop(symbol, None)

    def run(self) -> None:
        if self._ib:
            self._ib.run()

    def stop(self) -> None:
        if self._ib:
            self._ib.disconnect()


# ---------------------------------------------------------------------------
# Databento implementation (skeleton — activate with subscription)
# ---------------------------------------------------------------------------

class DatabentoDataFeed(DataFeed):
    """Live L1 trades + quotes via Databento Live API.

    Uses EQUS.MINI dataset for license-free BBO + trades.
    Requires DATABENTO_API_KEY env var.
    """

    def __init__(self, api_key: str = None):
        self._key = api_key or os.getenv("DATABENTO_API_KEY", "")
        self._client = None
        self._trade_callbacks = {}
        self._quote_callbacks = {}
        self._running = False

    def connect(self) -> bool:
        try:
            import databento as db
            self._client = db.Live(key=self._key)
            return True
        except Exception as e:
            print(f"Databento DataFeed connect failed: {e}", flush=True)
            return False

    def subscribe_trades(self, symbol: str, callback: Callable) -> None:
        self._trade_callbacks[symbol] = callback

    def subscribe_quotes(self, symbol: str, callback: Callable) -> None:
        self._quote_callbacks[symbol] = callback

    def unsubscribe_trades(self, symbol: str) -> None:
        self._trade_callbacks.pop(symbol, None)

    def unsubscribe_quotes(self, symbol: str) -> None:
        self._quote_callbacks.pop(symbol, None)

    def run(self) -> None:
        import databento as db

        symbols = list(set(
            list(self._trade_callbacks.keys()) +
            list(self._quote_callbacks.keys())
        ))
        if not symbols:
            return

        # Subscribe to trades
        if self._trade_callbacks:
            self._client.subscribe(
                dataset="EQUS.MINI",
                schema="trades",
                symbols=symbols,
            )

        # Subscribe to quotes (BBO)
        if self._quote_callbacks:
            self._client.subscribe(
                dataset="EQUS.MINI",
                schema="bbo-1s",
                symbols=symbols,
            )

        self._running = True
        for record in self._client:
            if not self._running:
                break

            symbol = record.symbol if hasattr(record, 'symbol') else None
            if not symbol:
                continue

            ts_ns = getattr(record, 'ts_event', None)
            if ts_ns is not None:
                ts = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc)
            else:
                ts = datetime.now(timezone.utc)

            # Trade records
            if hasattr(record, 'price') and hasattr(record, 'size'):
                cb = self._trade_callbacks.get(symbol)
                if cb:
                    price = float(record.price) / 1e9  # Databento fixed-point
                    size = int(record.size)
                    cb(symbol, price, size, ts)

            # Quote records (BBO)
            if hasattr(record, 'bid_px') and hasattr(record, 'ask_px'):
                cb = self._quote_callbacks.get(symbol)
                if cb:
                    bid = float(record.bid_px) / 1e9 if record.bid_px > 0 else None
                    ask = float(record.ask_px) / 1e9 if record.ask_px > 0 else None
                    cb(symbol, bid, ask, ts)

    def stop(self) -> None:
        self._running = False
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_feed(api_key: str = "", api_secret: str = "") -> DataFeed:
    """Create the appropriate DataFeed based on WB_DATA_FEED env var."""
    feed_type = os.getenv("WB_DATA_FEED", "alpaca").lower()

    if feed_type == "ibkr":
        feed = IBKRDataFeed()
        if feed.connect():
            print("✅ IBKR data feed connected", flush=True)
            return feed
        print("⚠️ IBKR connection failed — falling back to Alpaca", flush=True)
        return AlpacaFeed(api_key, api_secret)

    if feed_type == "databento":
        feed = DatabentoDataFeed()
        if feed.connect():
            print("✅ Databento data feed connected", flush=True)
            return feed
        print("⚠️ Databento connection failed — falling back to Alpaca", flush=True)
        return AlpacaFeed(api_key, api_secret)

    return AlpacaFeed(api_key, api_secret)
