"""
databento_feed.py — Historical data client (Databento)

Fetches MBP-10 (Level 2) and trade tick data from Databento's
historical API, caches locally, and converts to usable objects
for backtesting.

Usage (standalone test):
    python databento_feed.py ENVB 2026-02-19
    python databento_feed.py ENVB 2026-02-19 08:00 12:00
    python databento_feed.py --trades VERO 2026-01-16 07:00 12:00
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import pytz
from dotenv import load_dotenv

from l2_signals import L2Snapshot

load_dotenv()

ET = pytz.timezone("US/Eastern")

# Cache directory for raw Databento files
CACHE_DIR = Path(os.getenv("WB_L2_CACHE_DIR", "l2_cache"))


def _ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(symbol: str, date_str: str, dataset: str) -> Path:
    """
    Cache file naming: ENVB_2026-02-19_XNAS.dbn.zst
    """
    return CACHE_DIR / f"{symbol}_{date_str}_{dataset.split('.')[0]}.dbn.zst"


# Known NYSE-listed exchanges — expand as needed
NYSE_EXCHANGES = {"XNYS", "ARCX", "XASE"}  # NYSE, Arca, AMEX


def _resolve_dataset(symbol: str) -> str:
    """
    Resolve the correct Databento dataset for a symbol.
    Uses Alpaca metadata if available, otherwise defaults to XNAS.ITCH
    with fallback to XNYS.PILLAR on fetch failure (existing behavior).
    """
    # Try Alpaca asset lookup first
    try:
        from alpaca.trading.client import TradingClient
        client = TradingClient(os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY"))
        asset = client.get_asset(symbol)
        if asset.exchange in NYSE_EXCHANGES:
            print(f"  [{symbol}] Alpaca exchange={asset.exchange} → XNYS.PILLAR", flush=True)
            return "XNYS.PILLAR"
    except Exception:
        pass
    return "XNAS.ITCH"  # Default with existing fallback to XNYS.PILLAR on fetch failure


def fetch_l2_historical(
    symbol: str,
    date_str: str,
    start_et: str = "04:00",
    end_et: str = "16:00",
    dataset: str = None,
    force_refetch: bool = False,
) -> list[L2Snapshot]:
    """
    Fetch historical MBP-10 data for a symbol on a given date.
    Returns a list of L2Snapshot objects sorted by timestamp.

    Checks local cache first; fetches from Databento API if not cached.
    """
    try:
        import databento as db
    except ImportError:
        print("ERROR: databento package not installed. Run: pip install databento", flush=True)
        return []

    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        print("WARNING: DATABENTO_API_KEY not set in .env — cannot fetch L2 data", flush=True)
        return []

    if dataset is None:
        dataset = _resolve_dataset(symbol)

    _ensure_cache_dir()
    cache_file = _cache_path(symbol, date_str, dataset)

    # Check cache
    if not force_refetch and cache_file.exists():
        print(f"  L2 cache hit: {cache_file.name}", flush=True)
        return _parse_dbn_file(cache_file, symbol)

    # Parse time range
    date = datetime.strptime(date_str, "%Y-%m-%d")
    sh, sm = map(int, start_et.split(":"))
    eh, em = map(int, end_et.split(":"))

    start_dt = ET.localize(date.replace(hour=sh, minute=sm, second=0))
    end_dt = ET.localize(date.replace(hour=eh, minute=em, second=0))

    start_utc = start_dt.astimezone(timezone.utc)
    end_utc = end_dt.astimezone(timezone.utc)

    # Fetch from Databento
    print(f"  Fetching L2 from Databento: {symbol} {date_str} {start_et}-{end_et} ({dataset})...", flush=True)

    try:
        client = db.Historical(key=api_key)

        data = client.timeseries.get_range(
            dataset=dataset,
            schema="mbp-10",
            symbols=[symbol],
            start=start_utc.strftime("%Y-%m-%dT%H:%M"),
            end=end_utc.strftime("%Y-%m-%dT%H:%M"),
            stype_in="raw_symbol",
        )

        # Save raw data to cache
        # databento returns a DBNStore; write it to file
        if hasattr(data, 'to_file'):
            data.to_file(str(cache_file))
            print(f"  L2 cached: {cache_file.name}", flush=True)
        elif hasattr(data, 'replay'):
            # Older API: data is already a file path or iterable
            # We'll parse directly and cache the snapshots
            pass

        return _parse_dbn_data(data, symbol)

    except Exception as e:
        print(f"  ERROR fetching L2 data: {e}", flush=True)

        # If NASDAQ fails, try NYSE
        if dataset == "XNAS.ITCH":
            print(f"  Trying NYSE (XNYS.PILLAR)...", flush=True)
            return fetch_l2_historical(
                symbol, date_str, start_et, end_et,
                dataset="XNYS.PILLAR",
                force_refetch=force_refetch,
            )

        return []


def _parse_dbn_file(cache_file: Path, symbol: str) -> list[L2Snapshot]:
    """Parse a cached .dbn.zst file into L2Snapshot objects."""
    try:
        import databento as db
        data = db.DBNStore.from_file(str(cache_file))
        return _parse_dbn_data(data, symbol)
    except Exception as e:
        print(f"  ERROR parsing cached L2: {e}", flush=True)
        return []


def _parse_dbn_data(data, symbol: str) -> list[L2Snapshot]:
    """
    Parse Databento MBP-10 data into L2Snapshot objects.

    MBP-10 records contain 10 bid and 10 ask levels per update.
    We sample at reasonable intervals (not every tick) to keep memory manageable.
    """
    snapshots = []

    try:
        # Convert to DataFrame for easier processing
        df = data.to_df()

        if df.empty:
            print(f"  L2 data: 0 records for {symbol}", flush=True)
            return []

        print(f"  L2 data: {len(df)} records for {symbol}", flush=True)

        # MBP-10 has columns like:
        # ts_event, bid_px_00..bid_px_09, bid_sz_00..bid_sz_09,
        # ask_px_00..ask_px_09, ask_sz_00..ask_sz_09

        # Determine column naming convention
        bid_px_cols = [c for c in df.columns if c.startswith("bid_px_")]
        ask_px_cols = [c for c in df.columns if c.startswith("ask_px_")]
        bid_sz_cols = [c for c in df.columns if c.startswith("bid_sz_")]
        ask_sz_cols = [c for c in df.columns if c.startswith("ask_sz_")]

        if not bid_px_cols:
            # Try alternate column names
            bid_px_cols = [c for c in df.columns if "bid" in c.lower() and "price" in c.lower()]
            ask_px_cols = [c for c in df.columns if "ask" in c.lower() and "price" in c.lower()]
            bid_sz_cols = [c for c in df.columns if "bid" in c.lower() and "size" in c.lower()]
            ask_sz_cols = [c for c in df.columns if "ask" in c.lower() and "size" in c.lower()]

        if not bid_px_cols:
            print(f"  WARNING: Could not find bid/ask columns in L2 data. Columns: {list(df.columns)[:20]}", flush=True)
            return []

        # Sort columns to ensure level ordering
        bid_px_cols.sort()
        ask_px_cols.sort()
        bid_sz_cols.sort()
        ask_sz_cols.sort()

        n_levels = min(len(bid_px_cols), len(ask_px_cols), 10)

        # Sample: take one snapshot per second to reduce volume
        # (raw L2 can be millions of updates per day)
        last_sec = None

        for idx, row in df.iterrows():
            # Get timestamp
            ts = idx if isinstance(idx, datetime) else row.get("ts_event", idx)
            if isinstance(ts, (int, float)):
                ts = datetime.fromtimestamp(ts / 1e9, tz=timezone.utc)
            elif hasattr(ts, 'tzinfo') and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            # Sample at 1-second intervals
            ts_sec = int(ts.timestamp())
            if ts_sec == last_sec:
                continue
            last_sec = ts_sec

            # Build bid/ask level lists
            bids = []
            for i in range(n_levels):
                px = float(row[bid_px_cols[i]])
                sz = int(row[bid_sz_cols[i]])
                if px > 0 and sz > 0:
                    # Databento prices are in fixed-point (divide by 1e9 for some schemas)
                    if px > 1e6:
                        px = px / 1e9
                    bids.append((px, sz))

            asks = []
            for i in range(n_levels):
                px = float(row[ask_px_cols[i]])
                sz = int(row[ask_sz_cols[i]])
                if px > 0 and sz > 0:
                    if px > 1e6:
                        px = px / 1e9
                    asks.append((px, sz))

            if bids and asks:
                snapshots.append(L2Snapshot(
                    timestamp=ts,
                    symbol=symbol,
                    bids=bids,
                    asks=asks,
                ))

        print(f"  L2 snapshots: {len(snapshots)} (1-second sampled)", flush=True)

    except Exception as e:
        print(f"  ERROR parsing L2 data: {e}", flush=True)
        import traceback
        traceback.print_exc()

    return snapshots


def _trades_cache_path(symbol: str, date_str: str, dataset: str) -> Path:
    """Cache file naming for trade ticks: VERO_2026-01-16_trades_XNAS.dbn.zst"""
    return CACHE_DIR / f"{symbol}_{date_str}_trades_{dataset.split('.')[0]}.dbn.zst"


def fetch_trades_historical(
    symbol: str,
    date_str: str,
    start_et: str = "04:00",
    end_et: str = "12:00",
    dataset: str = None,
    force_refetch: bool = False,
) -> list[dict]:
    """
    Fetch historical trade ticks from Databento.

    Returns list of dicts sorted by timestamp:
        [{"price": float, "size": int, "timestamp": datetime}, ...]

    Compatible with simulate.py's tick replay loop (same fields as Alpaca trades).
    """
    try:
        import databento as db
    except ImportError:
        print("ERROR: databento package not installed. Run: pip install databento", flush=True)
        return []

    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        print("WARNING: DATABENTO_API_KEY not set in .env — cannot fetch trade data", flush=True)
        return []

    if dataset is None:
        dataset = _resolve_dataset(symbol)

    _ensure_cache_dir()
    cache_file = _trades_cache_path(symbol, date_str, dataset)

    # Check cache
    if not force_refetch and cache_file.exists():
        print(f"  Trades cache hit: {cache_file.name}", flush=True)
        return _parse_trades_dbn_file(cache_file, symbol)

    # Parse time range
    date = datetime.strptime(date_str, "%Y-%m-%d")
    sh, sm = map(int, start_et.split(":"))
    eh, em = map(int, end_et.split(":"))

    start_dt = ET.localize(date.replace(hour=sh, minute=sm, second=0))
    end_dt = ET.localize(date.replace(hour=eh, minute=em, second=0))

    start_utc = start_dt.astimezone(timezone.utc)
    end_utc = end_dt.astimezone(timezone.utc)

    print(f"  Fetching trades from Databento: {symbol} {date_str} {start_et}-{end_et} ({dataset})...", flush=True)

    try:
        client = db.Historical(key=api_key)

        data = client.timeseries.get_range(
            dataset=dataset,
            schema="trades",
            symbols=[symbol],
            start=start_utc.strftime("%Y-%m-%dT%H:%M"),
            end=end_utc.strftime("%Y-%m-%dT%H:%M"),
            stype_in="raw_symbol",
        )

        # Save raw data to cache
        if hasattr(data, 'to_file'):
            data.to_file(str(cache_file))
            print(f"  Trades cached: {cache_file.name}", flush=True)

        return _parse_trades_dbn_data(data, symbol)

    except Exception as e:
        print(f"  ERROR fetching trade data: {e}", flush=True)

        # If NASDAQ fails, try NYSE
        if dataset == "XNAS.ITCH":
            print(f"  Trying NYSE (XNYS.PILLAR)...", flush=True)
            return fetch_trades_historical(
                symbol, date_str, start_et, end_et,
                dataset="XNYS.PILLAR",
                force_refetch=force_refetch,
            )

        return []


def _parse_trades_dbn_file(cache_file: Path, symbol: str) -> list[dict]:
    """Parse a cached .dbn.zst trades file into trade dicts."""
    try:
        import databento as db
        data = db.DBNStore.from_file(str(cache_file))
        return _parse_trades_dbn_data(data, symbol)
    except Exception as e:
        print(f"  ERROR parsing cached trades: {e}", flush=True)
        return []


def _parse_trades_dbn_data(data, symbol: str) -> list[dict]:
    """
    Parse Databento trade data into simple dicts.

    Returns list of {"price": float, "size": int, "timestamp": datetime}
    sorted by timestamp.
    """
    trades = []

    try:
        df = data.to_df()

        if df.empty:
            print(f"  Trade data: 0 records for {symbol}", flush=True)
            return []

        print(f"  Trade data: {len(df)} records for {symbol}", flush=True)

        # Databento trades schema columns: price, size (+ ts_event as index)
        if "price" not in df.columns:
            print(f"  WARNING: 'price' column not found. Columns: {list(df.columns)[:20]}", flush=True)
            return []

        for idx, row in df.iterrows():
            # Timestamp
            ts = idx if isinstance(idx, datetime) else row.get("ts_event", idx)
            if isinstance(ts, (int, float)):
                ts = datetime.fromtimestamp(ts / 1e9, tz=timezone.utc)
            elif hasattr(ts, 'tzinfo') and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            # Price — Databento may encode as fixed-point integer
            px = float(row["price"])
            if px > 1e6:
                px = px / 1e9

            sz = int(row["size"])

            if px > 0 and sz > 0:
                trades.append({
                    "price": px,
                    "size": sz,
                    "timestamp": ts,
                })

        # Already sorted by timestamp from Databento, but ensure
        trades.sort(key=lambda t: t["timestamp"])

        if trades:
            first_et = trades[0]["timestamp"].astimezone(ET)
            last_et = trades[-1]["timestamp"].astimezone(ET)
            print(f"  Trades: {len(trades)} | ${trades[0]['price']:.2f}-${max(t['price'] for t in trades):.2f} "
                  f"| {first_et.strftime('%H:%M:%S')}-{last_et.strftime('%H:%M:%S')} ET", flush=True)

    except Exception as e:
        print(f"  ERROR parsing trade data: {e}", flush=True)
        import traceback
        traceback.print_exc()

    return trades


def get_l2_for_bar_window(
    snapshots: list[L2Snapshot],
    bar_start: datetime,
    bar_end: datetime,
) -> list[L2Snapshot]:
    """
    Filter L2 snapshots to those within a bar's time window.
    Used by simulate.py to replay L2 data alongside OHLCV bars.
    """
    return [s for s in snapshots if bar_start <= s.timestamp < bar_end]


# ─────────────────────────────────────────────
# CLI: fetch and display data for a symbol
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # Check for --trades flag
    fetch_trades_mode = "--trades" in sys.argv
    argv_clean = [a for a in sys.argv[1:] if a != "--trades"]

    if len(argv_clean) < 2:
        print("Usage: python databento_feed.py [--trades] SYMBOL DATE [START_ET] [END_ET]")
        print("  e.g. python databento_feed.py ENVB 2026-02-19 08:00 12:00")
        print("       python databento_feed.py --trades VERO 2026-01-16 07:00 12:00")
        sys.exit(1)

    symbol = argv_clean[0].upper()
    date_str = argv_clean[1]
    start_et = argv_clean[2] if len(argv_clean) > 2 else "08:00"
    end_et = argv_clean[3] if len(argv_clean) > 3 else "12:00"

    if fetch_trades_mode:
        # Trade tick mode
        print(f"\n{'=' * 60}")
        print(f"  DATABENTO TRADES FETCH: {symbol} on {date_str}")
        print(f"  Window: {start_et} - {end_et} ET")
        print(f"{'=' * 60}")

        tick_trades = fetch_trades_historical(symbol, date_str, start_et, end_et)

        if not tick_trades:
            print("\n  No trade data retrieved.")
            sys.exit(0)

        print(f"\n  Total trades: {len(tick_trades)}")
        print(f"  Price range: ${min(t['price'] for t in tick_trades):.2f} - ${max(t['price'] for t in tick_trades):.2f}")
        first_et_ts = tick_trades[0]["timestamp"].astimezone(ET)
        last_et_ts = tick_trades[-1]["timestamp"].astimezone(ET)
        print(f"  Time range: {first_et_ts.strftime('%H:%M:%S')} - {last_et_ts.strftime('%H:%M:%S')} ET")

        # Volume summary
        total_vol = sum(t["size"] for t in tick_trades)
        print(f"  Total volume: {total_vol:,}")

    else:
        # L2 mode (original)
        print(f"\n{'=' * 60}")
        print(f"  DATABENTO L2 FETCH: {symbol} on {date_str}")
        print(f"  Window: {start_et} - {end_et} ET")
        print(f"{'=' * 60}")

        snaps = fetch_l2_historical(symbol, date_str, start_et, end_et)

        if not snaps:
            print("\n  No L2 data retrieved.")
            sys.exit(0)

        print(f"\n  First snapshot: {snaps[0].timestamp}")
        print(f"  Last snapshot:  {snaps[-1].timestamp}")
        print(f"  Total: {len(snaps)} snapshots")

        sample = snaps[len(snaps) // 2]
        print(f"\n  Sample snapshot @ {sample.timestamp}:")
        print(f"    Bids: {sample.bids[:5]}")
        print(f"    Asks: {sample.asks[:5]}")

        from l2_signals import L2SignalDetector

        det = L2SignalDetector()
        signal_counts: dict[str, int] = {}

        for snap in snaps:
            det.on_snapshot(snap)
            state = det.get_state(symbol)
            if state:
                for sig in state["signals"]:
                    signal_counts[sig.name] = signal_counts.get(sig.name, 0) + 1

        print(f"\n  Signal summary across {len(snaps)} snapshots:")
        for name, count in sorted(signal_counts.items(), key=lambda x: -x[1]):
            pct = count / len(snaps) * 100
            print(f"    {name}: {count} ({pct:.1f}%)")

        final_state = det.get_state(symbol)
        if final_state:
            print(f"\n  Final state:")
            print(f"    Imbalance: {final_state['imbalance']:.2f} ({final_state['imbalance_trend']})")
            print(f"    Spread: {final_state['spread_pct']:.2f}%")
