"""
ibkr_feed.py — Live Level 2 data feed via Interactive Brokers

Connects to IB Gateway/TWS via ib_insync and streams real-time
market depth (L2) data, converting to L2Snapshot objects that
feed into L2SignalDetector.

Requirements:
  - IB Gateway or TWS running locally
  - IBKR account with L2 market data subscriptions:
    * US Securities Snapshot and Futures Value Bundle
    * NASDAQ TotalView + EDS
    * NYSE Open Book
  - pip install ib_insync

NOTE: This module is built now but can only be tested once the
IBKR account is set up and IB Gateway is running.
"""

from __future__ import annotations

import os
import asyncio
import threading
from datetime import datetime
from typing import Callable, Optional

import pytz
from dotenv import load_dotenv

from l2_signals import L2Snapshot

load_dotenv()

ET = pytz.timezone("US/Eastern")


class IBKRFeed:
    """
    Live L2 data feed from Interactive Brokers.

    Connects to IB Gateway, subscribes to market depth for symbols,
    and dispatches L2Snapshot objects via callbacks.
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        client_id: int = None,
    ):
        self.host = host or os.getenv("WB_IBKR_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("WB_IBKR_PORT", "7497"))
        self.client_id = client_id or int(os.getenv("WB_IBKR_CLIENT_ID", "1"))

        self.ib = None  # IB connection (lazy init)
        self._subscriptions: dict[str, object] = {}  # symbol → ticker
        self._callbacks: dict[str, Callable] = {}     # symbol → callback
        self._connected = False

    def connect(self) -> bool:
        """Connect to IB Gateway/TWS. Returns True on success."""
        try:
            from ib_insync import IB
            self.ib = IB()
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            self._connected = True
            print(f"IBKR connected: {self.host}:{self.port} (client {self.client_id})", flush=True)
            return True
        except Exception as e:
            print(f"IBKR connection failed: {e}", flush=True)
            self._connected = False
            return False

    def disconnect(self):
        """Disconnect from IB Gateway."""
        if self.ib and self._connected:
            # Unsubscribe all market depth first
            for symbol in list(self._subscriptions.keys()):
                self.unsubscribe_l2(symbol)
            self.ib.disconnect()
            self._connected = False
            print("IBKR disconnected", flush=True)

    def subscribe_l2(
        self,
        symbol: str,
        callback: Callable[[str, L2Snapshot], None],
        num_rows: int = 10,
    ):
        """
        Subscribe to Level 2 market depth for a symbol.

        callback signature: callback(symbol: str, snapshot: L2Snapshot)
        """
        if not self._connected or not self.ib:
            print(f"IBKR not connected — cannot subscribe L2 for {symbol}", flush=True)
            return

        if symbol in self._subscriptions:
            print(f"IBKR: already subscribed to L2 for {symbol}", flush=True)
            return

        try:
            from ib_insync import Stock

            contract = Stock(symbol, "SMART", "USD")
            self.ib.qualifyContracts(contract)

            ticker = self.ib.reqMktDepth(contract, numRows=num_rows)
            ticker.updateEvent += lambda t: self._on_depth_update(symbol, t)

            self._subscriptions[symbol] = ticker
            self._callbacks[symbol] = callback
            print(f"IBKR: subscribed L2 for {symbol} ({num_rows} levels)", flush=True)

        except Exception as e:
            print(f"IBKR: failed to subscribe L2 for {symbol}: {e}", flush=True)

    def unsubscribe_l2(self, symbol: str):
        """Unsubscribe from Level 2 data for a symbol."""
        ticker = self._subscriptions.pop(symbol, None)
        self._callbacks.pop(symbol, None)

        if ticker and self.ib and self._connected:
            try:
                self.ib.cancelMktDepth(ticker.contract)
                print(f"IBKR: unsubscribed L2 for {symbol}", flush=True)
            except Exception as e:
                print(f"IBKR: error unsubscribing {symbol}: {e}", flush=True)

    def _on_depth_update(self, symbol: str, ticker):
        """
        Called by ib_insync when market depth updates.
        Converts to L2Snapshot and dispatches to callback.
        """
        callback = self._callbacks.get(symbol)
        if not callback:
            return

        try:
            # Extract bid levels
            bids = []
            if hasattr(ticker, 'domBids') and ticker.domBids:
                for d in ticker.domBids:
                    if d.price > 0 and d.size > 0:
                        bids.append((float(d.price), int(d.size)))

            # Extract ask levels
            asks = []
            if hasattr(ticker, 'domAsks') and ticker.domAsks:
                for d in ticker.domAsks:
                    if d.price > 0 and d.size > 0:
                        asks.append((float(d.price), int(d.size)))

            if not bids or not asks:
                return

            snapshot = L2Snapshot(
                timestamp=datetime.now(ET),
                symbol=symbol,
                bids=bids,
                asks=asks,
            )

            callback(symbol, snapshot)

        except Exception as e:
            print(f"IBKR L2 callback error for {symbol}: {e}", flush=True)

    @property
    def is_connected(self) -> bool:
        return self._connected and self.ib is not None


# ─────────────────────────────────────────────
# CLI: smoke test (requires IB Gateway running)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import time

    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    print(f"\n{'=' * 60}")
    print(f"  IBKR L2 SMOKE TEST: {symbol}")
    print(f"  Duration: {duration}s")
    print(f"{'=' * 60}")

    feed = IBKRFeed()
    if not feed.connect():
        print("Cannot connect to IBKR. Is IB Gateway running?")
        sys.exit(1)

    snap_count = 0

    def on_l2(sym, snap):
        global snap_count
        snap_count += 1
        if snap_count <= 5 or snap_count % 10 == 0:
            print(f"  [{snap.timestamp.strftime('%H:%M:%S')}] {sym}: "
                  f"best_bid={snap.bids[0] if snap.bids else 'N/A'} "
                  f"best_ask={snap.asks[0] if snap.asks else 'N/A'} "
                  f"levels={len(snap.bids)}b/{len(snap.asks)}a", flush=True)

    feed.subscribe_l2(symbol, on_l2)

    print(f"\n  Listening for {duration}s...\n")
    time.sleep(duration)

    feed.disconnect()
    print(f"\n  Received {snap_count} L2 snapshots in {duration}s")
