#!/usr/bin/env python3
"""
live_scanner.py — Real-time pre-market gap-up scanner using Databento EQUS.MINI.

Streams all US equity pre-market quotes from 4:00 AM ET, identifies stocks that
are gapping 5%+ with price $2-$20 and float under 50M, and writes qualifying
candidates to watchlist.txt continuously from 7:00 AM to 11:00 AM ET.

Usage:
    python live_scanner.py             # Normal run
    python live_scanner.py --dry-run   # Print candidates, don't write watchlist
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, date
from threading import Lock
from typing import Optional

import databento as db
import pandas as pd
import pytz
import requests
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

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
# Config
# ---------------------------------------------------------------------------
FMP_API_KEY = os.getenv("FMP_API_KEY")

# Filter thresholds (Phase 1 simplification: widened to match Ross Cameron criteria)
MIN_GAP_PCT = 5.0           # Ross trades 5%+ gaps
MAX_GAP_PCT_A = 999.0       # No gap ceiling (Ross traded 500%+ gaps)
MAX_GAP_PCT_B = 999.0       # Same — no gap ceiling
MIN_PRICE = 2.0             # Ross trades $2+
MAX_PRICE = 20.0            # Ross's stated range for small account
WINDOW_START_HOUR = 7
WINDOW_START_MINUTE = 0
WINDOW_END_HOUR = 11         # Extended to 11:00 AM ET
WINDOW_END_MINUTE = 0
MIN_FLOAT = 100_000          # 100K (sane floor)
MAX_FLOAT = 50_000_000       # 50M (single unified ceiling)
MAX_SCANNER_SYMBOLS = 8      # Cap total symbols across all writes

# Known floats (highest reliability — no API needed)
KNOWN_FLOATS = {
    "SPRC": 400_000,
    "TNMG": 1_150_000,
    "MNTS": 1_300_000,
    "ELAB": 2_100_000,
    "GWAV": 800_000,
    "VERO": 1_600_000,
    "APVO": 900_000,
    "BNAI": 3_300_000,
    "MOVE": 600_000,
    "ANPA": 700_000,
    "PAVM": 700_000,
    "ROLR": 3_600_000,
    "ACON": 700_000,
    "BDSX": 3_700_000,
    "HIND": 1_500_000,
    "MLEC": 700_000,
    "SNSE": 700_000,
    "ENVB": 500_000,
    "SHPH": 1_600_000,
    "LCFY": 1_400_000,
    "SXTP": 900_000,
    "BCTX": 1_700_000,
    "JZXN": 1_320_000,
    "EDSA": 900_000,
    "BATL": 1_800_000,
}


# ---------------------------------------------------------------------------
# Float lookup (shared with scanner_sim.py logic)
# ---------------------------------------------------------------------------

def load_float_cache() -> dict:
    if os.path.exists(FLOAT_CACHE_PATH):
        with open(FLOAT_CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_float_cache(cache: dict):
    with open(FLOAT_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def get_float(symbol: str, cache: dict) -> Optional[float]:
    """Priority: KNOWN_FLOATS → cache → FMP API → yfinance fallback."""
    if symbol in KNOWN_FLOATS:
        return KNOWN_FLOATS[symbol]
    if symbol in cache:
        return cache[symbol]

    float_shares = None

    # FMP API
    if FMP_API_KEY:
        try:
            url = (f"https://financialmodelingprep.com/stable/shares-float"
                   f"?symbol={symbol}&apikey={FMP_API_KEY}")
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data and isinstance(data, list):
                float_shares = data[0].get("floatShares") or data[0].get("outstandingShares")
        except Exception:
            pass

    # yfinance fallback
    if float_shares is None:
        try:
            info = yf.Ticker(symbol).info
            float_shares = info.get("floatShares")
        except Exception:
            pass

    cache[symbol] = float_shares
    save_float_cache(cache)
    return float_shares


def passes_float_filter(float_shares: Optional[float]) -> bool:
    """True if float is between MIN_FLOAT and MAX_FLOAT (or unknown → reject)."""
    if float_shares is None:
        return False
    return MIN_FLOAT <= float_shares <= MAX_FLOAT


# ---------------------------------------------------------------------------
# Live Scanner
# ---------------------------------------------------------------------------

class LiveScanner:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.today = datetime.now(ET).date()

        # Setup logging
        log_path = os.path.join(SCANNER_DIR, f"live_{self.today}.log")
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s  %(message)s",
            datefmt="%H:%M:%S",
            handlers=[
                logging.FileHandler(log_path),
                logging.StreamHandler(sys.stdout),
            ],
        )
        self.log = logging.getLogger("live_scanner")
        self.log.info(f"Live Scanner starting — {self.today} {'[DRY RUN]' if dry_run else ''}")

        # State
        self.prev_close: dict[str, float] = {}       # symbol -> prev close price
        self.symbol_dir: dict[int, str] = {}          # instrument_id -> ticker
        self.candidates: dict[str, dict] = {}         # symbol -> candidate info
        self._processing: set[str] = set()            # symbols with in-flight float lookup
        self._rejected: set[str] = set()              # symbols already filtered out (X profile)
        self.float_cache = load_float_cache()
        self.lock = Lock()

        # Timing flags
        self._initial_watchlist_written = False
        self._final_watchlist_written = False

    # -----------------------------------------------------------------------
    # Step 1: Previous day close via Databento Historical
    # -----------------------------------------------------------------------

    def load_prev_close(self):
        """Fetch previous trading day OHLCV for all symbols via Databento Historical."""
        self.log.info("[1/2] Fetching previous-day close (Databento EQUS.SUMMARY ohlcv-1d)...")
        try:
            client = db.Historical()
            today_ts = pd.Timestamp.now(tz="US/Eastern").normalize()
            prev_day = (today_ts - pd.offsets.BusinessDay(1)).date()
            end_day = today_ts.date()

            self.log.info(f"      Requesting prev close for {prev_day}...")
            data = client.timeseries.get_range(
                dataset="EQUS.SUMMARY",
                schema="ohlcv-1d",
                symbols="ALL_SYMBOLS",
                start=prev_day,
                end=end_day,
            )

            # Insert symbology so to_df() maps instrument IDs to ticker symbols
            symbology_json = data.request_symbology(client)
            data.insert_symbology_json(symbology_json)
            df = data.to_df(pretty_px=True)

            if "symbol" not in df.columns:
                self.log.warning("      'symbol' column missing from df — check symbology insertion")
                return

            # De-duplicate: keep the most recent row per symbol
            if "ts_event" in df.columns:
                df = df.sort_values("ts_event").drop_duplicates("symbol", keep="last")

            self.prev_close = df.set_index("symbol")["close"].to_dict()
            self.log.info(f"      {len(self.prev_close):,} symbols with prev close loaded")

        except Exception as e:
            self.log.error(f"      FAILED to load prev close: {e}")
            self.log.error("      If EQUS.SUMMARY is not in your plan, confirm dataset access")
            self.log.error("      at https://databento.com/platform/datasets")
            self.log.error("      Scanner cannot run without prev close data — aborting")
            raise

    # -----------------------------------------------------------------------
    # Step 2: Databento event callback
    # -----------------------------------------------------------------------

    def on_event(self, event):
        """Called for every event from the Databento live stream."""

        # Build instrument_id → ticker mapping
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

        # Skip already-rejected symbols (no lock needed — set is only added to, never removed)
        if symbol in self._rejected:
            return

        # Get prev close
        pc = self.prev_close.get(symbol)
        if not pc or pc <= 0:
            return

        # Extract mid price
        try:
            bid = event.levels[0].pretty_bid_px
            ask = event.levels[0].pretty_ask_px
        except (IndexError, AttributeError):
            return
        if bid <= 0 or ask <= 0:
            return
        mid = (bid + ask) / 2.0

        # Quick price + gap pre-filter (no lock needed)
        if mid < MIN_PRICE or mid > MAX_PRICE:
            return
        gap_pct = (mid - pc) / pc * 100.0
        if gap_pct < MIN_GAP_PCT:
            return

        # Timing filter: only accept 4:00 AM – 11:00 AM ET
        ts_et = pd.Timestamp(event.ts_recv, unit="ns", tz="UTC").tz_convert(ET)
        hour, minute = ts_et.hour, ts_et.minute
        if hour < 4:
            return
        if hour >= WINDOW_END_HOUR:
            return

        # Check if already a candidate (just update price)
        with self.lock:
            if symbol in self.candidates:
                self.candidates[symbol]["price"] = round(mid, 4)
                self.candidates[symbol]["gap_pct"] = round(gap_pct, 2)
                return
            if symbol in self._processing:
                return
            # Mark as in-flight to prevent duplicate lookups
            self._processing.add(symbol)

        # Float lookup + classification (outside lock — may involve I/O)
        self._add_candidate(symbol, mid, gap_pct, ts_et, pc)

        with self.lock:
            self._processing.discard(symbol)

    def _add_candidate(self, symbol: str, price: float, gap_pct: float,
                       ts_et: pd.Timestamp, prev_close: float):
        """Look up float and add to candidates if it passes the unified filter."""
        float_shares = get_float(symbol, self.float_cache)

        if not passes_float_filter(float_shares):
            self._rejected.add(symbol)
            return

        float_m = round(float_shares / 1_000_000, 2) if float_shares else None
        first_seen = ts_et.strftime("%H:%M")

        candidate = {
            "symbol": symbol,
            "price": round(price, 4),
            "prev_close": round(prev_close, 4),
            "gap_pct": round(gap_pct, 2),
            "float_shares": float_shares,
            "float_millions": float_m,
            "first_seen_et": first_seen,
        }

        with self.lock:
            self.candidates[symbol] = candidate

        float_str = f"{float_m}M" if float_m else "N/A"
        self.log.info(
            f"CANDIDATE [{first_seen}] {symbol}: "
            f"gap={gap_pct:+.1f}% ${price:.2f} float={float_str}"
        )

    # -----------------------------------------------------------------------
    # Watchlist output
    # -----------------------------------------------------------------------

    def write_watchlist(self, label: str = "final"):
        """Write qualified candidates to watchlist.txt (and save JSON snapshot).
        Append-only: existing symbols in watchlist are preserved."""
        with self.lock:
            candidates_copy = dict(self.candidates)

        if not candidates_copy:
            self.log.info(f"[{label.upper()}] No candidates to write.")
            return

        # Read existing watchlist symbols to preserve (append-only)
        existing_symbols = set()
        existing_lines = []
        if os.path.exists(WATCHLIST_FILE):
            try:
                with open(WATCHLIST_FILE, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            existing_lines.append(line)
                            sym = line.split(":")[0].upper()
                            existing_symbols.add(sym)
            except Exception:
                pass

        # Sort all candidates by gap% descending
        all_candidates = sorted(
            candidates_copy.values(),
            key=lambda x: x["gap_pct"], reverse=True
        )

        # Apply MAX_SCANNER_SYMBOLS cap (existing symbols count toward the cap)
        all_final = []
        total_count = len(existing_symbols)
        for c in all_candidates:
            if c["symbol"] in existing_symbols:
                all_final.append(c)  # already in watchlist, always include
                continue
            if total_count < MAX_SCANNER_SYMBOLS:
                all_final.append(c)
                total_count += 1

        # Print summary
        self.log.info(f"\n{'='*60}")
        self.log.info(f"  [{label.upper()} WATCHLIST] {datetime.now(ET).strftime('%H:%M')} ET")
        self.log.info(f"  Candidates: {len(all_final)}")
        self.log.info(f"{'='*60}")
        for c in all_final:
            float_str = f"{c['float_millions']}M" if c['float_millions'] else "N/A"
            self.log.info(
                f"  {c['symbol']:<6}  "
                f"gap={c['gap_pct']:+.1f}%  ${c['price']:.2f}  float={float_str}  "
                f"first={c['first_seen_et']}"
            )
        self.log.info(f"{'='*60}\n")

        if self.dry_run:
            self.log.info("[DRY RUN] Watchlist NOT written.")
            return

        # Write watchlist.txt (append-only: preserve existing entries)
        new_symbols = {c["symbol"] for c in all_final}
        with open(WATCHLIST_FILE, "w") as f:
            f.write(f"# Live scanner output — {self.today} {label}\n")
            f.write(f"# Generated at {datetime.now(ET).strftime('%H:%M:%S')} ET\n")
            # Preserve existing entries not in current candidates
            for line in existing_lines:
                sym = line.split(":")[0].upper()
                if sym not in new_symbols:
                    f.write(f"{line}\n")
            # Write current candidates
            for c in all_final:
                f.write(f"{c['symbol']}\n")

        self.log.info(f"  Wrote {len(all_final)} symbols to {WATCHLIST_FILE}")

        # Save JSON snapshot
        json_path = os.path.join(SCANNER_DIR, f"live_{self.today}_{label}.json")
        with open(json_path, "w") as f:
            json.dump(all_final, f, indent=2)
        self.log.info(f"  Snapshot: {json_path}")

    # -----------------------------------------------------------------------
    # Main run loop
    # -----------------------------------------------------------------------

    def run(self):
        # Step 1: Load previous close
        self.load_prev_close()

        # Step 2: Start Databento live stream
        self.log.info("[2/2] Connecting to Databento live stream (EQUS.MINI mbp-1)...")
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
        self.log.info(f"      Stream started, replaying from {premarket_start.strftime('%H:%M')} ET...")

        try:
            # Step 3: Time-managed loop (continuous until 11:00 AM ET)
            last_update_minute = -1  # track last 5-min update write
            while True:
                now_et = datetime.now(ET)
                h, m = now_et.hour, now_et.minute

                # Initial watchlist at 7:00 AM
                if h == WINDOW_START_HOUR and m >= WINDOW_START_MINUTE and not self._initial_watchlist_written:
                    self._initial_watchlist_written = True
                    self.write_watchlist("initial")
                    last_update_minute = m

                # Scheduled write at 7:14 AM
                if not self._final_watchlist_written and (
                    h > 7 or (h == 7 and m >= 14)
                ):
                    self._final_watchlist_written = True
                    self.write_watchlist("7_14")
                    last_update_minute = m

                # After 7:14, continue writing every 5 minutes until 11:00 AM
                if self._final_watchlist_written and h < WINDOW_END_HOUR:
                    current_5min = (h * 60 + m) // 5
                    last_5min = (h * 60 + last_update_minute) // 5 if last_update_minute >= 0 else -1
                    if current_5min > last_5min:
                        self.write_watchlist(f"update_{h:02d}{m:02d}")
                        last_update_minute = m

                # Stop at 11:00 AM ET
                if h >= WINDOW_END_HOUR:
                    self.write_watchlist("final")
                    self.log.info(f"Scanner window closed ({WINDOW_END_HOUR}:00 AM ET). Stopping stream.")
                    break

                time.sleep(5)

        finally:
            try:
                live.stop()
            except Exception:
                pass

        self.log.info("Done.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Live pre-market gap-up scanner (Databento EQUS.MINI)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print candidates but do not write watchlist.txt",
    )
    args = parser.parse_args()

    scanner = LiveScanner(dry_run=args.dry_run)
    scanner.run()


if __name__ == "__main__":
    main()
