# market_scanner.py

import os
from typing import Set, List, Optional
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass, AssetStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame

from logger import log_event


class MarketScanner:
    """
    Dynamically scans the market for actively traded stocks.

    Option 3 Hybrid Approach:
    - Fetch ~500-1000 actively traded symbols from Alpaca
    - Pre-filter by price range ($1-$20) to reduce API calls
    - Apply existing stock_filter.py logic to reduced universe
    - Return top candidates automatically
    """

    def __init__(self, api_key: str, api_secret: str):
        self.trading_client = TradingClient(api_key, api_secret, paper=True)
        self.hist_client = StockHistoricalDataClient(api_key, api_secret)

        # Configuration
        self.min_price = float(os.getenv("WB_MIN_PRICE", "1.00"))
        self.max_price = float(os.getenv("WB_MAX_PRICE", "20.00"))
        self.max_symbols_to_scan = int(os.getenv("WB_SCANNER_MAX_SYMBOLS", "500"))
        self.max_workers = int(os.getenv("WB_SCANNER_WORKERS", "10"))  # Parallel API calls

    def get_active_symbols(self) -> Set[str]:
        """
        Get list of actively traded symbols from Alpaca.
        Filters for:
        - US equity stocks
        - Active status
        - Tradable
        - No ETFs, crypto, or other asset classes
        """
        try:
            print(f"\n🔍 Scanning market for active symbols...", flush=True)

            # Get all active, tradable US equity stocks
            search_params = GetAssetsRequest(
                asset_class=AssetClass.US_EQUITY,
                status=AssetStatus.ACTIVE
            )

            assets = self.trading_client.get_all_assets(search_params)

            # Filter for tradable stocks (exclude ETFs, fractional-only, etc.)
            symbols = set()
            for asset in assets:
                # Skip if not tradable
                if not asset.tradable:
                    continue

                # Skip if fractionable only (usually ETFs or special securities)
                if asset.fractionable and not asset.shortable:
                    continue

                # Skip if symbol is not standard (1-5 letters)
                symbol = asset.symbol
                if not symbol.isalpha() or not (1 <= len(symbol) <= 5):
                    continue

                symbols.add(symbol)

            print(f"   Found {len(symbols)} tradable US equity symbols", flush=True)
            log_event("market_scan_symbols_found", None, count=len(symbols))

            return symbols

        except Exception as e:
            print(f"⚠️ Failed to fetch active symbols: {e}", flush=True)
            log_event("exception", None, where="get_active_symbols", error=str(e))
            return set()

    def prefilter_by_price(self, symbols: Set[str]) -> Set[str]:
        """
        Fast pre-filter: check current price and volume.
        Only keep symbols in target price range with decent volume.
        This reduces the number of symbols we need to deeply analyze.
        """
        if not symbols:
            return set()

        print(f"\n🎯 Pre-filtering {len(symbols)} symbols by price range (${self.min_price:.2f}-${self.max_price:.2f})...", flush=True)

        passing_symbols = set()
        batch_size = 100  # Alpaca allows multi-symbol snapshots
        symbol_list = list(symbols)

        # Process in batches
        for i in range(0, len(symbol_list), batch_size):
            batch = symbol_list[i:i + batch_size]

            try:
                # Get snapshots for entire batch (efficient)
                snapshot_req = StockSnapshotRequest(symbol_or_symbols=batch)
                snapshots = self.hist_client.get_stock_snapshot(snapshot_req)

                for symbol, snap in snapshots.items():
                    if not snap or not snap.latest_trade:
                        continue

                    price = float(snap.latest_trade.price)
                    volume = int(snap.latest_trade.size) if snap.latest_trade else 0

                    # Quick filters
                    if self.min_price <= price <= self.max_price:
                        # Basic volume check (must have some activity)
                        if volume > 0:
                            passing_symbols.add(symbol)

            except Exception as e:
                # Log but continue with other batches
                log_event("exception", None, where="prefilter_batch", error=str(e), batch_size=len(batch))
                continue

        print(f"   ✅ {len(passing_symbols)} symbols passed price pre-filter", flush=True)
        log_event("market_scan_prefiltered", None, count=len(passing_symbols))

        # Limit to max symbols to scan (prioritize by volume or random sampling)
        if len(passing_symbols) > self.max_symbols_to_scan:
            print(f"   📊 Limiting to top {self.max_symbols_to_scan} symbols", flush=True)
            # For now, just take first N (could be enhanced with volume sorting)
            passing_symbols = set(list(passing_symbols)[:self.max_symbols_to_scan])

        return passing_symbols

    def scan_market(self) -> Set[str]:
        """
        Main entry point: scan market and return symbols to watch.

        Flow:
        1. Get all active symbols from Alpaca (~8000)
        2. Pre-filter by price range (~500-1000)
        3. Return pre-filtered list for detailed filtering

        The detailed filtering (gap %, relative volume, EMAs, etc.)
        is still done by stock_filter.py to avoid duplication.
        """
        # Step 1: Get all active symbols
        all_symbols = self.get_active_symbols()

        if not all_symbols:
            print("⚠️ No active symbols found. Check API connection.", flush=True)
            return set()

        # Step 2: Pre-filter by price range (fast)
        prefiltered = self.prefilter_by_price(all_symbols)

        if not prefiltered:
            print("⚠️ No symbols passed price pre-filter. Adjust WB_MIN_PRICE/WB_MAX_PRICE.", flush=True)
            return set()

        print(f"\n📋 Market scan complete: {len(prefiltered)} symbols ready for filtering", flush=True)

        return prefiltered
