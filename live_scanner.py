#!/usr/bin/env python3
"""
live_scanner.py — Real-time pre-market gap-up scanner using Databento EQUS.MINI.

Streams all US equity pre-market quotes from 4:00 AM ET, identifies stocks that
are gapping 10-40% with price $3-$10, classifies by float (Profile A/B), and
writes qualifying candidates to watchlist.txt at 7:14 AM ET.

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

# Filter thresholds (directive spec)
MIN_GAP_PCT = 10.0
MAX_GAP_PCT_A = 40.0   # Profile A: gap 10-40%
MAX_GAP_PCT_B = 25.0   # Profile B: gap 10-25%
MIN_PRICE = 3.0
MAX_PRICE = 10.0
WINDOW_START_HOUR = 7
WINDOW_START_MINUTE = 0
WINDOW_END_HOUR = 7
WINDOW_END_MINUTE = 14
MIN_FLOAT_A = 500_000       # 0.5M
MAX_FLOAT_A = 5_000_000     # 5M
MAX_FLOAT_B = 50_000_000    # 50M
MAX_PROFILE_B_CANDIDATES = 2

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


def classify_profile(float_shares: Optional[float]) -> str:
    """A (<5M, >=0.5M) | B (5-50M) | X (>50M or unknown)."""
    if float_shares is None:
        return "X"
    if float_shares < MIN_FLOAT_A:
        return "X"           # < 0.5M — too thin
    if float_shares <= MAX_FLOAT_A:
        return "A"
    if float_shares <= MAX_FLOAT_B:
        return "B"
    return "X"              # > 50M — skip


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
        if gap_pct > MAX_GAP_PCT_A:   # skip even Profile B above 40%
            return

        # Timing filter: only accept 4:00 AM – 7:14 AM ET
        ts_et = pd.Timestamp(event.ts_recv, unit="ns", tz="UTC").tz_convert(ET)
        hour, minute = ts_et.hour, ts_et.minute
        if hour < 4:
            return
        if hour > WINDOW_END_HOUR or (hour == WINDOW_END_HOUR and minute > WINDOW_END_MINUTE):
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
        """Look up float, classify, and add to candidates if profile A or B."""
        float_shares = get_float(symbol, self.float_cache)
        profile = classify_profile(float_shares)

        if profile == "X":
            self._rejected.add(symbol)
            return

        # Profile B gap cap is tighter (10-25%)
        if profile == "B" and gap_pct > MAX_GAP_PCT_B:
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
            "profile": profile,
            "first_seen_et": first_seen,
        }

        with self.lock:
            self.candidates[symbol] = candidate

        float_str = f"{float_m}M" if float_m else "N/A"
        self.log.info(
            f"CANDIDATE [{first_seen}] {symbol}: "
            f"gap={gap_pct:+.1f}% ${price:.2f} float={float_str} → {profile}"
        )

    # -----------------------------------------------------------------------
    # Watchlist output
    # -----------------------------------------------------------------------

    def write_watchlist(self, label: str = "final"):
        """Write qualified candidates to watchlist.txt (and save JSON snapshot)."""
        with self.lock:
            candidates_copy = dict(self.candidates)

        if not candidates_copy:
            self.log.info(f"[{label.upper()}] No candidates to write.")
            return

        # Separate A and B; sort each by gap% descending
        a_list = sorted(
            [c for c in candidates_copy.values() if c["profile"] == "A"],
            key=lambda x: x["gap_pct"], reverse=True
        )
        b_list = sorted(
            [c for c in candidates_copy.values() if c["profile"] == "B"],
            key=lambda x: x["gap_pct"], reverse=True
        )[:MAX_PROFILE_B_CANDIDATES]   # Only top 1-2 Profile B

        all_final = a_list + b_list

        # Print summary
        self.log.info(f"\n{'='*60}")
        self.log.info(f"  [{label.upper()} WATCHLIST] {datetime.now(ET).strftime('%H:%M')} ET")
        self.log.info(f"  Profile A: {len(a_list)} | Profile B: {len(b_list)}")
        self.log.info(f"{'='*60}")
        for c in all_final:
            float_str = f"{c['float_millions']}M" if c['float_millions'] else "N/A"
            self.log.info(
                f"  {c['symbol']:<6} :{c['profile']}  "
                f"gap={c['gap_pct']:+.1f}%  ${c['price']:.2f}  float={float_str}  "
                f"first={c['first_seen_et']}"
            )
        self.log.info(f"{'='*60}\n")

        if self.dry_run:
            self.log.info("[DRY RUN] Watchlist NOT written.")
            return

        # Write watchlist.txt
        with open(WATCHLIST_FILE, "w") as f:
            f.write(f"# Live scanner output — {self.today} {label}\n")
            f.write(f"# Generated at {datetime.now(ET).strftime('%H:%M:%S')} ET\n")
            for c in all_final:
                f.write(f"{c['symbol']}:{c['profile']}\n")

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
            # Step 3: Time-managed loop
            while True:
                now_et = datetime.now(ET)
                h, m = now_et.hour, now_et.minute

                # Initial watchlist at 7:00 AM
                if h == WINDOW_START_HOUR and m >= WINDOW_START_MINUTE and not self._initial_watchlist_written:
                    self._initial_watchlist_written = True
                    self.write_watchlist("initial")

                # Final watchlist at 7:14 AM — lock and stop
                if (h > WINDOW_END_HOUR or (h == WINDOW_END_HOUR and m >= WINDOW_END_MINUTE)) \
                        and not self._final_watchlist_written:
                    self._final_watchlist_written = True
                    self.write_watchlist("final")
                    self.log.info("Scanner window closed (7:14 AM ET). Stopping stream.")
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
