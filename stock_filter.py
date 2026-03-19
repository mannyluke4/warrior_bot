# stock_filter.py

import os
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockSnapshotRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from logger import log_event


@dataclass
class StockInfo:
    """Fundamental and technical info for filtering"""
    symbol: str
    price: float
    prev_close: float
    gap_pct: float
    volume: int
    avg_volume: float  # 20-day average
    rel_volume: float  # volume / avg_volume
    float_shares: Optional[float] = None  # shares outstanding (millions)
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None


class StockFilter:
    """
    Filters stocks based on Ross Cameron's Warrior Trading criteria:
    - Float < 50M (prefer < 10M)
    - Gap % >= 5% (prefer >= 20%)
    - Price above daily EMAs (20, 50, 200)
    - Relative volume > 1.5x average
    """

    def __init__(self, api_key: str, api_secret: str):
        self.hist_client = StockHistoricalDataClient(api_key, api_secret)

        # Filter thresholds (from Ross's PDF)
        # Defaults tightened to match backtest pillar gates (2026-03-17)
        self.min_gap_pct = float(os.getenv("WB_MIN_GAP_PCT", "10"))  # 10% minimum (Ross Pillar 1)
        self.preferred_gap_pct = float(os.getenv("WB_PREFERRED_GAP_PCT", "20"))  # 20% preferred
        self.min_float = float(os.getenv("WB_MIN_FLOAT", "0.5"))  # 0.5M min (blocks micro-float)
        self.max_float = float(os.getenv("WB_MAX_FLOAT", "10"))  # 10M shares max (Ross Pillar 5)
        self.preferred_max_float = float(os.getenv("WB_PREFERRED_MAX_FLOAT", "10"))  # 10M preferred
        self.min_rel_volume = float(os.getenv("WB_MIN_REL_VOLUME", "2.0"))  # 2x average (Ross Pillar 2)
        self.require_ema_alignment = os.getenv("WB_REQUIRE_EMA_ALIGNMENT", "0") == "1"
        self.min_price = float(os.getenv("WB_MIN_PRICE", "2.00"))  # $2 minimum (Ross Pillar 4)
        self.max_price = float(os.getenv("WB_MAX_PRICE", "20.00"))  # $20 maximum (Ross Pillar 4)

        # Float cache (avoid repeated yfinance calls for same symbol)
        self._float_cache: Dict[str, Optional[float]] = {}

    def get_stock_info(self, symbol: str) -> Optional[StockInfo]:
        """
        Fetch fundamental and technical data for a stock.
        Returns None if data unavailable.
        """
        try:
            # 1) Get snapshot (current price, prev close, volume)
            snapshot_req = StockSnapshotRequest(symbol_or_symbols=[symbol])
            snapshots = self.hist_client.get_stock_snapshot(snapshot_req)
            snap = snapshots.get(symbol)

            if not snap:
                return None

            # Extract data
            latest_trade = snap.latest_trade
            if not latest_trade:
                return None

            price = float(latest_trade.price)
            prev_close = float(snap.previous_daily_bar.close) if snap.previous_daily_bar else price
            # Use today's cumulative daily bar volume, not a single trade's lot size
            if snap.daily_bar and snap.daily_bar.volume:
                volume = int(snap.daily_bar.volume)
            elif snap.minute_bar and snap.minute_bar.volume:
                volume = int(snap.minute_bar.volume)
            else:
                volume = int(snap.latest_trade.size) if snap.latest_trade else 0

            # Calculate gap %
            gap_pct = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0

            # 2) Get 20-day bars for average volume and EMAs
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=60)  # 60 days to ensure we get 20+ trading days

            bars_req = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
                feed="sip",
            )

            bars_resp = self.hist_client.get_stock_bars(bars_req)
            bars = bars_resp.data.get(symbol, [])

            if not bars or len(bars) < 20:
                # Not enough history - can't calculate avg volume or EMAs
                return StockInfo(
                    symbol=symbol,
                    price=price,
                    prev_close=prev_close,
                    gap_pct=gap_pct,
                    volume=volume,
                    avg_volume=volume,  # fallback
                    rel_volume=1.0,  # unknown
                )

            # Calculate average volume (last 20 days)
            recent_volumes = [float(b.volume) for b in bars[-20:]]
            avg_volume = sum(recent_volumes) / len(recent_volumes)
            rel_volume = volume / avg_volume if avg_volume > 0 else 1.0

            # Calculate EMAs (20, 50, 200)
            closes = [float(b.close) for b in bars]
            ema20 = self._calculate_ema(closes, 20) if len(closes) >= 20 else None
            ema50 = self._calculate_ema(closes, 50) if len(closes) >= 50 else None
            ema200 = self._calculate_ema(closes, 200) if len(closes) >= 200 else None

            # Get float data (from yfinance)
            float_shares = self.get_float_estimate(symbol)

            return StockInfo(
                symbol=symbol,
                price=price,
                prev_close=prev_close,
                gap_pct=gap_pct,
                volume=volume,
                avg_volume=avg_volume,
                rel_volume=rel_volume,
                float_shares=float_shares,
                ema20=ema20,
                ema50=ema50,
                ema200=ema200,
            )

        except Exception as e:
            log_event("exception", symbol, where="get_stock_info", error=str(e))
            return None

    def _calculate_ema(self, prices: List[float], length: int) -> Optional[float]:
        """Calculate EMA using standard formula"""
        if len(prices) < length:
            return None

        alpha = 2.0 / (length + 1.0)
        ema = prices[0]  # Start with first price

        for price in prices[1:]:
            ema = (price * alpha) + (ema * (1.0 - alpha))

        return ema

    def get_float_estimate(self, symbol: str) -> Optional[float]:
        """
        Estimate float (shares outstanding) using yfinance.

        Returns float in millions of shares, or None if unavailable.
        Uses cache to avoid repeated API calls for same symbol.
        """
        # Check cache first
        if symbol in self._float_cache:
            return self._float_cache[symbol]

        try:
            import yfinance as yf

            # Fetch ticker info with timeout
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Try multiple fields (Yahoo Finance naming can vary)
            float_shares = (
                info.get('floatShares') or
                info.get('sharesOutstanding') or
                info.get('impliedSharesOutstanding')
            )

            if float_shares and float_shares > 0:
                # Convert to millions
                result = float_shares / 1_000_000
            else:
                result = None

            # Cache result (even if None, to avoid re-querying)
            self._float_cache[symbol] = result
            return result

        except ImportError:
            # yfinance not installed - log once and continue
            if not hasattr(self, '_yfinance_warning_logged'):
                print("⚠️ yfinance not installed. Float filtering disabled.", flush=True)
                print("   Install with: pip install yfinance", flush=True)
                self._yfinance_warning_logged = True
                log_event("warning", None, msg="yfinance_not_installed")
            # Cache None to avoid repeated import errors
            self._float_cache[symbol] = None
            return None

        except Exception as e:
            # API error, timeout, or invalid symbol - cache None and continue silently
            self._float_cache[symbol] = None
            return None

    def passes_filters(self, info: StockInfo) -> tuple[bool, List[str]]:
        """
        Check if stock passes all filters.
        Returns (passes, reasons) where reasons explains failures.
        """
        reasons = []

        # 1) Price range
        if info.price < self.min_price:
            reasons.append(f"price ${info.price:.2f} < ${self.min_price:.2f}")
        if info.price > self.max_price:
            reasons.append(f"price ${info.price:.2f} > ${self.max_price:.2f}")

        # 2) Gap %
        if info.gap_pct < self.min_gap_pct:
            reasons.append(f"gap {info.gap_pct:.1f}% < {self.min_gap_pct:.1f}%")

        # 3) Relative volume
        if info.rel_volume < self.min_rel_volume:
            reasons.append(f"rel_vol {info.rel_volume:.2f}x < {self.min_rel_volume:.2f}x")

        # 4) Float (if available)
        if info.float_shares is not None and info.float_shares < self.min_float:
            reasons.append(f"float {info.float_shares:.2f}M < {self.min_float:.1f}M (micro-float)")
        if info.float_shares is not None and info.float_shares > self.max_float:
            reasons.append(f"float {info.float_shares:.1f}M > {self.max_float:.1f}M")

        # 5) EMA alignment (optional strict filter)
        if self.require_ema_alignment:
            if info.ema20 and info.price < info.ema20:
                reasons.append(f"price ${info.price:.2f} < EMA20 ${info.ema20:.2f}")
            if info.ema50 and info.price < info.ema50:
                reasons.append(f"price ${info.price:.2f} < EMA50 ${info.ema50:.2f}")
            if info.ema200 and info.price < info.ema200:
                reasons.append(f"price ${info.price:.2f} < EMA200 ${info.ema200:.2f}")

        passes = len(reasons) == 0
        return passes, reasons

    def rank_stock(self, info: StockInfo) -> float:
        """
        Composite ranking: 40% RVOL + 30% abs volume + 20% gap + 10% float bonus.
        Must match run_ytd_v2_backtest.py rank_score() exactly.
        """
        import math
        rvol = info.rel_volume if info.rel_volume else 0
        vol = info.volume if info.volume else 0
        gap = info.gap_pct if info.gap_pct else 0
        float_m = info.float_shares if info.float_shares else 10

        rvol_score = math.log10(max(rvol, 0.1) + 1) / math.log10(51)
        vol_score = math.log10(max(vol, 1)) / 8
        gap_score = min(gap, 100) / 100
        float_penalty = min(float_m, 10) / 10

        # Scale to 0-100 for readability (backtest uses 0-1 range)
        return 100 * ((0.4 * rvol_score) + (0.3 * vol_score) + (0.2 * gap_score) + (0.1 * (1 - float_penalty)))

    def filter_watchlist(self, symbols: Set[str]) -> Dict[str, StockInfo]:
        """
        Filter watchlist and return passing stocks with their info.
        Returns dict of {symbol: StockInfo} for stocks that pass filters.
        """
        results = {}
        filtered_out = []

        print(f"\n🔍 Filtering {len(symbols)} symbols...", flush=True)

        for symbol in sorted(symbols):
            info = self.get_stock_info(symbol)
            if not info:
                filtered_out.append((symbol, ["no_data"]))
                continue

            passes, reasons = self.passes_filters(info)

            if passes:
                rank = self.rank_stock(info)
                results[symbol] = info

                log_event(
                    "stock_passed_filter",
                    symbol,
                    price=info.price,
                    gap_pct=info.gap_pct,
                    rel_volume=info.rel_volume,
                    rank=rank,
                    ema20=info.ema20,
                    ema50=info.ema50,
                    ema200=info.ema200,
                )

                float_str = f"float={info.float_shares:.1f}M" if info.float_shares is not None else "float=N/A"
                print(
                    f"✅ {symbol}: ${info.price:.2f} gap={info.gap_pct:+.1f}% "
                    f"vol={info.rel_volume:.1f}x {float_str} rank={rank:.1f}",
                    flush=True,
                )
            else:
                filtered_out.append((symbol, reasons))
                log_event("stock_filtered_out", symbol, reasons=reasons)

        # Print summary
        print(f"\n📊 Filter Results:", flush=True)
        print(f"   ✅ Passed: {len(results)} stocks", flush=True)
        print(f"   ❌ Filtered: {len(filtered_out)} stocks", flush=True)

        if filtered_out and len(filtered_out) <= 10:
            print(f"\n❌ Filtered out:", flush=True)
            for sym, reasons in filtered_out[:10]:
                print(f"   {sym}: {', '.join(reasons)}", flush=True)

        return results
