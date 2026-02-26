"""
databento_feed.py — Historical Level 2 data client (Databento)

Fetches MBP-10 (Market by Price, top 10 levels) data from Databento's
historical API, caches it locally, and converts to L2Snapshot objects
for backtesting.

Usage (standalone test):
    python databento_feed.py ENVB 2026-02-19
    python databento_feed.py ENVB 2026-02-19 08:00 12:00
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


def _resolve_dataset(symbol: str) -> str:
    """
    Determine the Databento dataset based on the exchange.
    Most small-cap momentum stocks trade on NASDAQ.
    For now, default to XNAS.ITCH (NASDAQ TotalView).
    NYSE-listed stocks would use XNYS.PILLAR.
    """
    # TODO: Auto-detect exchange from Alpaca or Databento metadata
    # For now, try NASDAQ first (most warrior stocks are NASDAQ-listed)
    return "XNAS.ITCH"


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
# CLI: fetch and display L2 data for a symbol
# ─────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python databento_feed.py SYMBOL DATE [START_ET] [END_ET]")
        print("  e.g. python databento_feed.py ENVB 2026-02-19 08:00 12:00")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    date_str = sys.argv[2]
    start_et = sys.argv[3] if len(sys.argv) > 3 else "08:00"
    end_et = sys.argv[4] if len(sys.argv) > 4 else "12:00"

    print(f"\n{'=' * 60}")
    print(f"  DATABENTO L2 FETCH: {symbol} on {date_str}")
    print(f"  Window: {start_et} - {end_et} ET")
    print(f"{'=' * 60}")

    snaps = fetch_l2_historical(symbol, date_str, start_et, end_et)

    if not snaps:
        print("\n  No L2 data retrieved.")
        sys.exit(0)

    # Show first/last snapshots and summary stats
    print(f"\n  First snapshot: {snaps[0].timestamp}")
    print(f"  Last snapshot:  {snaps[-1].timestamp}")
    print(f"  Total: {len(snaps)} snapshots")

    # Show a sample snapshot
    sample = snaps[len(snaps) // 2]
    print(f"\n  Sample snapshot @ {sample.timestamp}:")
    print(f"    Bids: {sample.bids[:5]}")
    print(f"    Asks: {sample.asks[:5]}")

    # Run through signal detector to show what signals fire
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
