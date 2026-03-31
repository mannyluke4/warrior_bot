#!/usr/bin/env python3
"""
unified_scanner.py — Unified Scanner V3: One scanner logic, two modes.

Replaces live_scanner.py (live mode) and scanner_sim.py (backtest mode) as the
single source of truth for "which stocks to trade and when."

Core principle: The ScanEngine processes 1-minute bars chronologically and records
the EXACT minute each stock first passes ALL filters simultaneously. This discovery
time is used as sim_start for backtesting (no look-ahead bias) and as the watchlist
write time for live trading.

Usage:
    python unified_scanner.py --live
    python unified_scanner.py --backtest --date 2026-01-16
    python unified_scanner.py --backtest --start 2026-01-02 --end 2026-03-31
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, date as date_type
from threading import Lock
from typing import Optional

import pytz
from dotenv import load_dotenv

load_dotenv()

# Databento import — may not be installed in all environments
try:
    import databento as db
    HAS_DATABENTO = True
except ImportError:
    HAS_DATABENTO = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

ET = pytz.timezone("US/Eastern")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHLIST_FILE = os.path.join(BOT_DIR, "watchlist.txt")
SCANNER_DIR = os.path.join(BOT_DIR, "scanner_results")
FLOAT_CACHE_PATH = os.path.join(SCANNER_DIR, "float_cache.json")
os.makedirs(SCANNER_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Filter thresholds — read from .env (shared with all scanners)
# ---------------------------------------------------------------------------
MIN_GAP_PCT = float(os.getenv("WB_MIN_GAP_PCT", "10"))
MIN_PRICE = float(os.getenv("WB_MIN_PRICE", "2.00"))
MAX_PRICE = float(os.getenv("WB_MAX_PRICE", "20.00"))
MIN_FLOAT = int(float(os.getenv("WB_MIN_FLOAT", "0.5")) * 1_000_000)
MAX_FLOAT = int(float(os.getenv("WB_MAX_FLOAT", "15")) * 1_000_000)
MIN_PM_VOLUME = int(os.getenv("WB_MIN_PM_VOLUME", "50000"))
MIN_RVOL = float(os.getenv("WB_MIN_REL_VOLUME", "2.0"))
MAX_SCANNER_SYMBOLS = int(os.getenv("WB_MAX_SCANNER_SYMBOLS", "8"))

# ---------------------------------------------------------------------------
# Reuse float lookup chain from scanner_sim.py
# ---------------------------------------------------------------------------
# Import from scanner_sim.py: get_float, load_float_cache, save_float_cache,
# classify_profile, KNOWN_FLOATS
# These are proven and shared across all existing scanners.
try:
    from scanner_sim import (
        get_float,
        load_float_cache,
        save_float_cache,
        classify_profile,
        KNOWN_FLOATS,
    )
except ImportError:
    # Fallback: import from live_scanner.py which has the same functions
    try:
        from live_scanner import (
            get_float,
            load_float_cache,
            save_float_cache,
            KNOWN_FLOATS,
        )
        # live_scanner doesn't export classify_profile, define it here
        def classify_profile(float_shares: Optional[float]) -> str:
            if float_shares is None:
                return "unknown"
            millions = float_shares / 1_000_000
            if millions < 5:
                return "A"
            elif millions <= 15:
                return "B"
            else:
                return "skip"
    except ImportError:
        print("ERROR: Cannot import float lookup functions from scanner_sim.py or live_scanner.py")
        print("       Ensure at least one of these files exists in the same directory.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Rank scoring — unified composite (same as scanner_sim.py)
# ---------------------------------------------------------------------------
def rank_score(candidate: dict) -> float:
    """Composite ranking: RVOL 40%, PM volume 30%, gap% 20%, float 10%."""
    rvol = candidate.get("relative_volume", 0) or 0
    pm_vol = candidate.get("pm_volume", 0) or 0
    gap = candidate.get("gap_pct", 0) or 0
    float_m = candidate.get("float_millions", 10) or 10
    rvol_score = math.log10(min(rvol, 50) + 1) / math.log10(51)
    vol_score = math.log10(max(pm_vol, 1)) / 8
    gap_score = min(gap, 100) / 100
    float_score = 1 - (min(float_m, 10) / 10)
    return (0.40 * rvol_score) + (0.30 * vol_score) + (0.20 * gap_score) + (0.10 * float_score)


# ═══════════════════════════════════════════════════════════════════════════
# ScanEngine — Core streaming scanner
# ═══════════════════════════════════════════════════════════════════════════

class ScanEngine:
    """
    Streaming scanner that processes 1-minute bars chronologically.
    Same code path for live (Databento stream) and backtest (Databento historical replay).

    For each 1-min bar:
      1. Update cumulative volume for that symbol
      2. Compute gap% from prev_close
      3. Check all filters (price, gap, volume, RVOL, float)
      4. If ALL filters pass for the first time -> record discovery_time

    Discovery time = the timestamp of the 1-min bar where the stock FIRST
    passes all filters simultaneously. This is the exact moment the live
    scanner would have added it to the watchlist.
    """

    def __init__(
        self,
        prev_close: dict[str, float],
        adv: dict[str, float],
        float_cache: dict,
    ):
        self.prev_close = prev_close        # symbol -> previous close price
        self.adv = adv                       # symbol -> 20-day avg daily volume
        self.float_cache = float_cache       # shared float cache dict

        # Per-symbol cumulative state
        self.cum_volume: dict[str, int] = {}
        self.last_close: dict[str, float] = {}
        self.high_price: dict[str, float] = {}

        # Discovery tracking
        self.discovered: dict[str, dict] = {}   # symbol -> candidate dict
        self.float_checked: dict[str, Optional[float]] = {}  # symbol -> float_shares
        self.rejected: set[str] = set()         # symbols that failed float filter

        # Callback for live mode (called when a new stock is discovered)
        self.on_discovery: Optional[callable] = None

    def process_bar(
        self,
        symbol: str,
        timestamp,
        close: float,
        high: float,
        volume: int,
    ):
        """
        Process a single 1-minute bar. Updates cumulative state and checks
        all filters. If all pass for the first time, records discovery.

        Args:
            symbol: Ticker symbol
            timestamp: Bar timestamp (datetime or pd.Timestamp, timezone-aware)
            close: Bar close price
            high: Bar high price
            volume: Bar volume
        """
        # Skip if already discovered or permanently rejected
        if symbol in self.discovered or symbol in self.rejected:
            return

        # Update cumulative state
        if symbol not in self.cum_volume:
            self.cum_volume[symbol] = 0
        self.cum_volume[symbol] += volume
        self.last_close[symbol] = close
        self.high_price[symbol] = max(self.high_price.get(symbol, 0), high)

        # Get prev_close — skip if not available
        pc = self.prev_close.get(symbol)
        if not pc or pc <= 0:
            return

        # ---------------------------------------------------------------
        # Apply ALL filters simultaneously
        # ---------------------------------------------------------------

        # Filter 1: Price ($2-$20)
        if close < MIN_PRICE or close > MAX_PRICE:
            return

        # Filter 2: Gap% (10%+)
        gap_pct = (close - pc) / pc * 100.0
        if gap_pct < MIN_GAP_PCT:
            return

        # Filter 3: PM Volume (50K+ cumulative)
        cum_vol = self.cum_volume[symbol]
        if cum_vol < MIN_PM_VOLUME:
            return

        # Filter 4: RVOL (2x+ cumulative vs avg daily volume)
        avg_vol = self.adv.get(symbol, 0)
        rvol = (cum_vol / avg_vol) if avg_vol > 0 else 0.0
        if avg_vol > 0 and rvol < MIN_RVOL:
            return

        # Filter 5: Float (0.5M-15M) — cached, one lookup per symbol
        if symbol not in self.float_checked:
            self.float_checked[symbol] = get_float(symbol, self.float_cache)
        float_shares = self.float_checked[symbol]

        if float_shares is not None:
            if float_shares < MIN_FLOAT or float_shares > MAX_FLOAT:
                self.rejected.add(symbol)
                return
        # None float → allow through (unknown float, let strategy gates decide)

        # ---------------------------------------------------------------
        # ALL FILTERS PASSED — this is the discovery moment
        # ---------------------------------------------------------------
        try:
            ts_et = timestamp.astimezone(ET)
        except (AttributeError, TypeError):
            # If timestamp doesn't have astimezone, try wrapping it
            if HAS_PANDAS:
                ts_et = pd.Timestamp(timestamp).tz_convert(ET)
            else:
                ts_et = timestamp  # fallback
        discovery = f"{ts_et.hour:02d}:{ts_et.minute:02d}"

        profile = classify_profile(float_shares)
        float_m = round(float_shares / 1e6, 2) if float_shares else None

        candidate = {
            "symbol": symbol,
            "prev_close": round(pc, 4),
            "pm_price": round(close, 4),
            "gap_pct": round(gap_pct, 2),
            "pm_volume": cum_vol,
            "cumulative_volume_at_discovery": cum_vol,
            "avg_daily_volume": round(avg_vol, 0) if avg_vol > 0 else None,
            "relative_volume": round(rvol, 2) if avg_vol > 0 else None,
            "float_shares": float_shares,
            "float_millions": float_m,
            "profile": profile,
            "discovery_time": discovery,
            "sim_start": discovery,
            "discovery_method": "unified_v3",
            "first_seen_et": discovery,
        }
        candidate["rank_score"] = round(rank_score(candidate), 4)

        self.discovered[symbol] = candidate

        # Fire callback for live mode
        if self.on_discovery:
            self.on_discovery(candidate)

    def get_discoveries(self) -> list[dict]:
        """Return all discovered candidates, sorted by rank_score descending."""
        candidates = list(self.discovered.values())
        candidates.sort(key=lambda x: x.get("rank_score", 0), reverse=True)
        return candidates


# ═══════════════════════════════════════════════════════════════════════════
# Backtest Mode
# ═══════════════════════════════════════════════════════════════════════════

def _require_databento():
    """Abort if databento is not installed."""
    if not HAS_DATABENTO:
        print("ERROR: 'databento' package is not installed.")
        print("       Install with: pip install databento")
        sys.exit(1)
    if not HAS_PANDAS:
        print("ERROR: 'pandas' package is not installed.")
        print("       Install with: pip install pandas")
        sys.exit(1)


def fetch_prev_close_and_adv(client, date_str: str) -> tuple[dict, dict]:
    """
    Fetch previous close + 20-day average daily volume from Databento EQUS.SUMMARY.

    Returns:
        (prev_close, adv) — both dicts of {symbol: float}
    """
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    # 30 calendar days back to ensure ~21 trading days
    start_date = target_date - timedelta(days=30)

    print(f"  [1/3] Fetching OHLCV-1d from {start_date} to {target_date} (EQUS.SUMMARY)...")
    data = client.timeseries.get_range(
        dataset="EQUS.SUMMARY",
        schema="ohlcv-1d",
        symbols="ALL_SYMBOLS",
        start=str(start_date),
        end=str(target_date),
    )

    # Insert symbology so to_df() maps instrument IDs to ticker symbols
    symbology_json = data.request_symbology(client)
    data.insert_symbology_json(symbology_json)
    df = data.to_df(price_type="float")

    if "symbol" not in df.columns:
        print("  WARNING: 'symbol' column missing — check Databento symbology")
        return {}, {}

    # Compute average daily volume from the full window
    adv = {}
    if "volume" in df.columns:
        avg_vol = df.groupby("symbol")["volume"].mean().to_dict()
        adv = {k: float(v) for k, v in avg_vol.items()}
    print(f"         {len(adv):,} symbols with avg daily volume")

    # Previous close: most recent row per symbol
    prev_close = {}
    if "ts_event" in df.columns:
        df_latest = df.sort_values("ts_event").drop_duplicates("symbol", keep="last")
    else:
        df_latest = df.drop_duplicates("symbol", keep="last")
    prev_close = df_latest.set_index("symbol")["close"].to_dict()
    print(f"         {len(prev_close):,} symbols with prev close")

    return prev_close, adv


def run_backtest_single(date_str: str, client=None):
    """
    Replay Databento historical data for a single date to determine exact
    discovery times for all candidates.

    Args:
        date_str: Date string YYYY-MM-DD
        client: Optional db.Historical() client (reused for multi-date runs)
    """
    _require_databento()

    print(f"\n{'='*60}")
    print(f"  UNIFIED SCANNER V3 — BACKTEST — {date_str}")
    print(f"{'='*60}")

    if client is None:
        client = db.Historical()

    # Step 1: Fetch prev_close + ADV
    prev_close, adv = fetch_prev_close_and_adv(client, date_str)
    if not prev_close:
        print(f"  ERROR: No prev_close data for {date_str}. Skipping.")
        return

    # Step 2: Fetch ALL 1-min bars for the date (4AM-10AM ET)
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    # Determine ET offset for this date (EST=-05:00 or EDT=-04:00)
    dt_local = ET.localize(datetime(target_date.year, target_date.month, target_date.day, 4, 0, 0))
    offset = dt_local.strftime("%z")  # e.g. "-0500" or "-0400"
    offset_fmt = f"{offset[:3]}:{offset[3:]}"  # e.g. "-05:00"

    start_ts = f"{date_str}T04:00:00{offset_fmt}"
    end_ts = f"{date_str}T10:00:00{offset_fmt}"

    print(f"  [2/3] Fetching 1-min bars {start_ts} to {end_ts} (EQUS.MINI ohlcv-1m)...")
    try:
        bars_data = client.timeseries.get_range(
            dataset="EQUS.MINI",
            schema="ohlcv-1m",
            symbols="ALL_SYMBOLS",
            start=start_ts,
            end=end_ts,
        )
    except Exception as e:
        print(f"  ERROR fetching 1-min bars: {e}")
        return

    # Insert symbology
    try:
        symbology_json = bars_data.request_symbology(client)
        bars_data.insert_symbology_json(symbology_json)
    except Exception as e:
        print(f"  WARNING: Symbology insertion failed: {e}")

    df = bars_data.to_df(price_type="float")

    if df.empty:
        print(f"  No bars returned for {date_str}. Market holiday?")
        return

    if "symbol" not in df.columns:
        print(f"  WARNING: 'symbol' column missing from bars DataFrame")
        return

    # Sort all bars chronologically
    if "ts_event" in df.columns:
        df = df.sort_values("ts_event")
    bar_count = len(df)
    symbol_count = df["symbol"].nunique()
    print(f"         {bar_count:,} bars across {symbol_count:,} symbols")

    # Step 3: Feed bars to ScanEngine
    print(f"  [3/3] Processing bars through ScanEngine...")
    float_cache = load_float_cache()
    engine = ScanEngine(prev_close=prev_close, adv=adv, float_cache=float_cache)

    for _, bar in df.iterrows():
        engine.process_bar(
            symbol=bar["symbol"],
            timestamp=bar.get("ts_event", bar.name) if "ts_event" in bar.index else bar.name,
            close=bar["close"],
            high=bar["high"],
            volume=int(bar["volume"]),
        )

    # Get discoveries
    candidates = engine.get_discoveries()

    # Update total pm_volume to full-day cumulative (not just at discovery)
    for c in candidates:
        sym = c["symbol"]
        if sym in engine.cum_volume:
            c["pm_volume"] = engine.cum_volume[sym]

    # Save results
    save_scanner_results(date_str, candidates)

    # Summary
    print(f"\n  {'='*60}")
    print(f"  RESULTS: {len(candidates)} candidates")
    print(f"  {'='*60}")
    for c in candidates:
        float_str = f"{c['float_millions']}M" if c['float_millions'] else "N/A"
        rvol_str = f"{c['relative_volume']:.1f}x" if c.get('relative_volume') else "N/A"
        print(
            f"  {c['symbol']:<6} gap={c['gap_pct']:+.1f}% ${c['pm_price']:.2f} "
            f"float={float_str} rvol={rvol_str} "
            f"disc={c['discovery_time']} score={c.get('rank_score', 0):.3f}"
        )
    print()


def run_backtest_range(start_str: str, end_str: str):
    """Run backtest for a range of dates."""
    _require_databento()

    start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

    # Build list of business days in range
    dates = []
    current = start_date
    while current <= end_date:
        # Skip weekends
        if current.weekday() < 5:  # Mon=0, Fri=4
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    print(f"\n  Unified Scanner V3 — Backtest Range")
    print(f"  {start_str} to {end_str} ({len(dates)} business days)")
    print(f"{'='*60}")

    # Reuse a single Historical client for all dates
    client = db.Historical()

    for i, date_str in enumerate(dates):
        print(f"\n  [{i+1}/{len(dates)}] {date_str}")
        try:
            run_backtest_single(date_str, client=client)
        except Exception as e:
            print(f"  ERROR on {date_str}: {e}")
            import traceback
            traceback.print_exc()
            continue

    print(f"\n{'='*60}")
    print(f"  Backtest range complete: {len(dates)} dates processed")
    print(f"{'='*60}")


def save_scanner_results(date_str: str, candidates: list[dict]):
    """Save scanner results as JSON (same format as existing scanner_results)."""
    json_path = os.path.join(SCANNER_DIR, f"{date_str}.json")
    with open(json_path, "w") as f:
        json.dump(candidates, f, indent=2, default=str)

    # Also write human-readable text summary
    txt_path = os.path.join(SCANNER_DIR, f"{date_str}.txt")
    with open(txt_path, "w") as f:
        f.write(f"Scanner Results — {date_str} (Unified V3)\n")
        f.write(f"{'='*90}\n")
        f.write(
            f"{'Symbol':<8} {'Gap%':>7} {'Price':>7} {'Float':>8} {'Profile':>7} "
            f"{'SimStart':>8} {'PM Vol':>10} {'RVOL':>6} {'Discovery':>10} {'Score':>6}\n"
        )
        f.write(
            f"{'─'*8} {'─'*7} {'─'*7} {'─'*8} {'─'*7} "
            f"{'─'*8} {'─'*10} {'─'*6} {'─'*10} {'─'*6}\n"
        )
        for c in candidates:
            float_str = f"{c['float_millions']}M" if c.get('float_millions') else "N/A"
            rvol_str = f"{c.get('relative_volume', 0):.1f}x" if c.get('relative_volume') else "N/A"
            f.write(
                f"{c['symbol']:<8} {c['gap_pct']:>+7.1f}% {c['pm_price']:>7.2f} {float_str:>8} "
                f"{c.get('profile', '?'):>7} {c['sim_start']:>8} {c['pm_volume']:>10,} "
                f"{rvol_str:>6} {c['discovery_time']:>10} {c.get('rank_score', 0):>6.3f}\n"
            )
        f.write(f"\nTotal candidates: {len(candidates)}\n")
        f.write(f"Discovery method: unified_v3\n")

    print(f"  Saved: {json_path}")
    print(f"  Saved: {txt_path}")


# ═══════════════════════════════════════════════════════════════════════════
# Live Mode
# ═══════════════════════════════════════════════════════════════════════════

class LiveScannerV3:
    """
    Live scanner using Databento EQUS.MINI stream.
    Builds 1-min bars from mbp-1 events, feeds to ScanEngine.
    Writes discoveries to watchlist.txt immediately.
    Runs 4:00 AM - 10:00 AM ET, then self-terminates.
    """

    def __init__(self, dry_run: bool = False):
        _require_databento()

        self.dry_run = dry_run
        self.today = datetime.now(ET).date()
        self.lock = Lock()

        # Bar builder state: instrument_id -> {symbol, open, high, low, close, volume, bar_minute}
        self.bar_builders: dict[int, dict] = {}
        self.symbol_dir: dict[int, str] = {}  # instrument_id -> ticker

        # ScanEngine will be initialized after loading prev_close + ADV
        self.engine: Optional[ScanEngine] = None

        # Track written watchlist symbols (append-only)
        self._written_symbols: set[str] = set()

        print(f"  Live Scanner V3 starting — {self.today} {'[DRY RUN]' if dry_run else ''}")

    def load_reference_data(self):
        """Fetch prev_close + ADV from Databento EQUS.SUMMARY (21 business days)."""
        print("[1/2] Fetching prev_close + ADV from Databento EQUS.SUMMARY...")
        client = db.Historical()
        today_ts = pd.Timestamp.now(tz="US/Eastern").normalize()
        start_day = (today_ts - pd.offsets.BusinessDay(21)).date()
        end_day = today_ts.date()

        print(f"       Requesting OHLCV-1d from {start_day} to {end_day}...")
        data = client.timeseries.get_range(
            dataset="EQUS.SUMMARY",
            schema="ohlcv-1d",
            symbols="ALL_SYMBOLS",
            start=start_day,
            end=end_day,
        )

        symbology_json = data.request_symbology(client)
        data.insert_symbology_json(symbology_json)
        df = data.to_df(price_type="float")

        if "symbol" not in df.columns:
            raise RuntimeError("'symbol' column missing — check Databento symbology")

        # ADV
        adv = {}
        if "volume" in df.columns:
            avg_vol = df.groupby("symbol")["volume"].mean().to_dict()
            adv = {k: float(v) for k, v in avg_vol.items()}
        print(f"       {len(adv):,} symbols with avg daily volume")

        # Prev close
        if "ts_event" in df.columns:
            df_latest = df.sort_values("ts_event").drop_duplicates("symbol", keep="last")
        else:
            df_latest = df.drop_duplicates("symbol", keep="last")
        prev_close = df_latest.set_index("symbol")["close"].to_dict()
        print(f"       {len(prev_close):,} symbols with prev close")

        # Initialize ScanEngine
        float_cache = load_float_cache()
        self.engine = ScanEngine(prev_close=prev_close, adv=adv, float_cache=float_cache)
        self.engine.on_discovery = self._on_discovery

    def _on_discovery(self, candidate: dict):
        """Called by ScanEngine when a new stock passes all filters."""
        sym = candidate["symbol"]
        float_str = f"{candidate['float_millions']}M" if candidate.get('float_millions') else "N/A"
        rvol_str = f"{candidate['relative_volume']:.1f}x" if candidate.get('relative_volume') else "N/A"
        print(
            f"  DISCOVERED [{candidate['discovery_time']}] {sym}: "
            f"gap={candidate['gap_pct']:+.1f}% ${candidate['pm_price']:.2f} "
            f"float={float_str} rvol={rvol_str}",
            flush=True,
        )

        # Write to watchlist immediately
        if not self.dry_run:
            self._append_to_watchlist(candidate)

    def _append_to_watchlist(self, candidate: dict):
        """Append a newly discovered symbol to watchlist.txt (thread-safe)."""
        sym = candidate["symbol"]
        with self.lock:
            if sym in self._written_symbols:
                return
            if len(self._written_symbols) >= MAX_SCANNER_SYMBOLS:
                print(f"  WATCHLIST FULL ({MAX_SCANNER_SYMBOLS} symbols) — skipping {sym}")
                return
            self._written_symbols.add(sym)

        # Read existing watchlist
        existing_lines = []
        if os.path.exists(WATCHLIST_FILE):
            try:
                with open(WATCHLIST_FILE, "r") as f:
                    existing_lines = [l.rstrip("\n") for l in f if l.strip() and not l.strip().startswith("#")]
            except Exception:
                pass

        float_m = candidate.get("float_millions", 0) or 0
        rvol = candidate.get("relative_volume", 0) or 0
        pm_vol = candidate.get("pm_volume", 0) or 0
        new_line = f"{sym}:{candidate['gap_pct']}:{rvol}:{float_m}:{pm_vol}"

        with open(WATCHLIST_FILE, "w") as f:
            f.write(f"# Unified Scanner V3 — {self.today}\n")
            f.write(f"# Format: SYMBOL:gap_pct:rvol:float_m:pm_volume\n")
            f.write(f"# Updated at {datetime.now(ET).strftime('%H:%M:%S')} ET\n")
            for line in existing_lines:
                existing_sym = line.split(":")[0].upper()
                if existing_sym != sym:
                    f.write(f"{line}\n")
            f.write(f"{new_line}\n")

        print(f"  -> Wrote {sym} to watchlist.txt")

    def on_event(self, event):
        """
        Called for every event from the Databento live stream.
        Builds 1-min bars and feeds completed bars to ScanEngine.
        """
        # Symbol mapping
        if isinstance(event, db.SymbolMappingMsg):
            with self.lock:
                self.symbol_dir[event.instrument_id] = event.stype_out_symbol
            return

        if not isinstance(event, db.MBP1Msg):
            return

        # Resolve symbol
        with self.lock:
            symbol = self.symbol_dir.get(event.instrument_id)
        if not symbol:
            return

        # Extract price from top-of-book
        try:
            bid = event.levels[0].pretty_bid_px
            ask = event.levels[0].pretty_ask_px
        except (IndexError, AttributeError):
            return
        if bid <= 0 or ask <= 0:
            return
        mid = (bid + ask) / 2.0

        # Approximate volume from event size
        size = getattr(event, "size", 0) or 0

        # Get timestamp
        ts = pd.Timestamp(event.ts_event, unit="ns", tz="UTC")
        ts_et = ts.tz_convert(ET)
        bar_minute = ts_et.floor("min")

        # Build 1-minute bars
        iid = event.instrument_id
        if iid not in self.bar_builders:
            self.bar_builders[iid] = {
                "symbol": symbol,
                "open": mid,
                "high": mid,
                "low": mid,
                "close": mid,
                "volume": size,
                "bar_minute": bar_minute,
            }
        else:
            bb = self.bar_builders[iid]
            if bar_minute != bb["bar_minute"]:
                # New minute — flush previous bar to ScanEngine
                if self.engine and bb["volume"] > 0:
                    self.engine.process_bar(
                        symbol=bb["symbol"],
                        timestamp=bb["bar_minute"],
                        close=bb["close"],
                        high=bb["high"],
                        volume=bb["volume"],
                    )
                # Start new bar
                self.bar_builders[iid] = {
                    "symbol": symbol,
                    "open": mid,
                    "high": mid,
                    "low": mid,
                    "close": mid,
                    "volume": size,
                    "bar_minute": bar_minute,
                }
            else:
                bb["high"] = max(bb["high"], mid)
                bb["low"] = min(bb["low"], mid)
                bb["close"] = mid
                bb["volume"] += size

    def run(self):
        """Main live scanner loop. Runs 4AM-10AM ET."""
        # Step 1: Load reference data
        self.load_reference_data()

        # Step 2: Start Databento live stream
        print("[2/2] Connecting to Databento live stream (EQUS.MINI mbp-1)...")
        today_et = datetime.now(ET).date()
        premarket_start = ET.localize(
            datetime(today_et.year, today_et.month, today_et.day, 4, 0, 0)
        )

        live = db.Live()
        live.subscribe(
            dataset="EQUS.MINI",
            schema="mbp-1",
            symbols="ALL_SYMBOLS",
            start=premarket_start,
        )
        live.add_callback(self.on_event)
        live.start()
        print(f"       Stream started, replaying from {premarket_start.strftime('%H:%M')} ET...")

        try:
            while True:
                now_et = datetime.now(ET)
                h, m = now_et.hour, now_et.minute

                # Stop at 10:00 AM ET
                if h >= 10:
                    print(f"\n  Scanner cutoff reached (10:00 AM ET). Stopping stream.")
                    break

                time.sleep(5)

        finally:
            # Flush all pending bars
            if self.engine:
                for iid, bb in self.bar_builders.items():
                    if bb["volume"] > 0:
                        self.engine.process_bar(
                            symbol=bb["symbol"],
                            timestamp=bb["bar_minute"],
                            close=bb["close"],
                            high=bb["high"],
                            volume=bb["volume"],
                        )

            try:
                live.stop()
            except Exception:
                pass

            # Save JSON snapshot of all discoveries
            if self.engine:
                candidates = self.engine.get_discoveries()
                save_scanner_results(str(self.today), candidates)

        # Final summary
        if self.engine:
            candidates = self.engine.get_discoveries()
            print(f"\n  Final: {len(candidates)} discoveries")
            for c in candidates:
                print(f"    {c['symbol']}: disc={c['discovery_time']} gap={c['gap_pct']:+.1f}%")

        print("  Done.")


# ═══════════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Unified Scanner V3 — One scanner logic, two modes (live + backtest)"
    )
    subparsers = parser.add_subparsers(dest="mode")

    # Live mode
    live_parser = subparsers.add_parser("live", help="Run live scanner (4AM-10AM ET)")
    live_parser.add_argument("--dry-run", action="store_true", help="Print only, don't write watchlist")

    # Backtest mode
    bt_parser = subparsers.add_parser("backtest", help="Replay historical data for exact discovery times")
    bt_parser.add_argument("--date", help="Single date (YYYY-MM-DD)")
    bt_parser.add_argument("--start", help="Start date for range (YYYY-MM-DD)")
    bt_parser.add_argument("--end", help="End date for range (YYYY-MM-DD)")

    # Also support --live / --backtest flags directly (as specified in directive)
    parser.add_argument("--live", action="store_true", help="Run live scanner")
    parser.add_argument("--backtest", action="store_true", help="Run backtest scanner")
    parser.add_argument("--date", help="Single date for backtest (YYYY-MM-DD)")
    parser.add_argument("--start", help="Start date for backtest range (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date for backtest range (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Print only, don't write watchlist")

    args = parser.parse_args()

    # Determine mode from either subparser or flags
    if args.mode == "live" or getattr(args, "live", False):
        scanner = LiveScannerV3(dry_run=getattr(args, "dry_run", False))
        scanner.run()

    elif args.mode == "backtest" or getattr(args, "backtest", False):
        date_arg = getattr(args, "date", None)
        start_arg = getattr(args, "start", None)
        end_arg = getattr(args, "end", None)

        if date_arg:
            run_backtest_single(date_arg)
        elif start_arg and end_arg:
            run_backtest_range(start_arg, end_arg)
        else:
            print("ERROR: Backtest mode requires --date or --start/--end")
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
