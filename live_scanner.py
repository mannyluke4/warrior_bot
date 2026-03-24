#!/usr/bin/env python3
"""
live_scanner.py — Real-time pre-market gap-up scanner using Databento EQUS.MINI.

Streams all US equity pre-market quotes from 4:00 AM ET, identifies stocks that
are gapping 10%+ with price $2-$20, RVOL >= 2x, and PM volume >= 50K.
Ranks by composite score and writes to watchlist.txt every minute from 7:00 AM.
New symbol additions cut off at 9:30 AM ET (post-09:30 = negative EV).
Scanner continues tracking existing symbols until 11:00 AM ET.

Usage:
    python live_scanner.py             # Normal run
    python live_scanner.py --dry-run   # Print candidates, don't write watchlist
"""

from __future__ import annotations

import argparse
import json
import logging
import math
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

# Filter thresholds — read from .env (shared with stock_filter.py / scanner_sim.py)
MIN_GAP_PCT = float(os.getenv("WB_MIN_GAP_PCT", "10"))
MAX_GAP_PCT_A = 999.0       # No gap ceiling (Ross traded 500%+ gaps)
MAX_GAP_PCT_B = 999.0       # Same — no gap ceiling
MIN_PRICE = float(os.getenv("WB_MIN_PRICE", "2.00"))
MAX_PRICE = float(os.getenv("WB_MAX_PRICE", "20.00"))
WINDOW_START_HOUR = 7
WINDOW_START_MINUTE = 0
WINDOW_END_HOUR = 9              # Scanner stops adding new symbols at 9:30 (negative EV after)
WINDOW_END_MINUTE = 30
MIN_FLOAT = int(float(os.getenv("WB_MIN_FLOAT", "0.5")) * 1_000_000)
MAX_FLOAT = int(float(os.getenv("WB_MAX_FLOAT", "15")) * 1_000_000)
MIN_PM_VOLUME = int(os.getenv("WB_MIN_PM_VOLUME", "50000"))
MIN_RVOL = float(os.getenv("WB_MIN_REL_VOLUME", "2.0"))
MAX_SCANNER_SYMBOLS = int(os.getenv("WB_MAX_SCANNER_SYMBOLS", "8"))

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
            raw = json.load(f)
        # Clear stale None entries — forces re-lookup through full chain
        # (FMP → yfinance → EDGAR → AlphaVantage). With new fallbacks,
        # most previously-None tickers will now resolve successfully.
        cleaned = {k: v for k, v in raw.items() if v is not None}
        dropped = len(raw) - len(cleaned)
        if dropped > 0:
            print(f"  [float_cache] Cleared {dropped} stale None entries — will re-attempt lookups")
            save_float_cache(cleaned)
        return cleaned
    return {}


def save_float_cache(cache: dict):
    with open(FLOAT_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


# --- SEC EDGAR ticker→CIK map (load once at startup) ---
_EDGAR_CIK_MAP = {}


def _load_edgar_cik_map():
    global _EDGAR_CIK_MAP
    if _EDGAR_CIK_MAP:
        return _EDGAR_CIK_MAP
    try:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": "WarriorBot luke@delightedpath.net"},
            timeout=10,
        )
        data = resp.json()
        _EDGAR_CIK_MAP = {
            v["ticker"].upper(): str(v["cik_str"]).zfill(10)
            for v in data.values()
        }
    except Exception as e:
        print(f"  [EDGAR] Failed to load CIK map: {e}")
    return _EDGAR_CIK_MAP


def get_edgar_shares_outstanding(symbol: str) -> Optional[float]:
    """Tier 5: SEC EDGAR shares outstanding as float proxy. Free, 10 req/s."""
    cik_map = _load_edgar_cik_map()
    cik = cik_map.get(symbol.upper())
    if not cik:
        return None
    try:
        url = (f"https://data.sec.gov/api/xbrl/companyconcept/"
               f"CIK{cik}/dei/EntityCommonStockSharesOutstanding.json")
        resp = requests.get(url, headers={
            "User-Agent": "WarriorBot luke@delightedpath.net"
        }, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        shares_list = data.get("units", {}).get("shares", [])
        if not shares_list:
            return None
        latest = sorted(shares_list, key=lambda x: x.get("end", ""), reverse=True)[0]
        shares = latest.get("val", 0)
        if shares > 0:
            print(f"  [EDGAR] {symbol}: {shares/1e6:.2f}M shares outstanding")
            return shares
    except Exception as e:
        print(f"  [EDGAR] {symbol}: {e}")
    return None


# --- Alpha Vantage free tier (25 calls/day, true float) ---
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")


def get_alpha_vantage_float(symbol: str) -> Optional[float]:
    """Tier 6: Alpha Vantage OVERVIEW — true float. Free tier: 25 calls/day."""
    if not ALPHA_VANTAGE_KEY:
        return None
    try:
        url = (f"https://www.alphavantage.co/query?function=OVERVIEW"
               f"&symbol={symbol}&apikey={ALPHA_VANTAGE_KEY}")
        resp = requests.get(url, timeout=10)
        data = resp.json()
        shares_float = data.get("SharesFloat")
        if shares_float and shares_float != "None" and shares_float != "0":
            val = float(shares_float)
            if val > 0:
                print(f"  [AlphaVantage] {symbol}: {val/1e6:.2f}M float")
                return val
    except Exception as e:
        print(f"  [AlphaVantage] {symbol}: {e}")
    return None


def get_float(symbol: str, cache: dict) -> Optional[float]:
    """Priority: KNOWN_FLOATS → cache → FMP → yfinance → EDGAR → AlphaVantage."""
    if symbol in KNOWN_FLOATS:
        return KNOWN_FLOATS[symbol]
    if symbol in cache:
        return cache[symbol]

    float_shares = None

    # 3. FMP API
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

    # 4. yfinance fallback
    if float_shares is None:
        try:
            info = yf.Ticker(symbol).info
            float_shares = info.get("floatShares")
        except Exception:
            pass

    # 5. SEC EDGAR fallback (free, 10 req/s)
    if float_shares is None:
        float_shares = get_edgar_shares_outstanding(symbol)

    # 6. Alpha Vantage free tier (25 calls/day, true float)
    if float_shares is None:
        float_shares = get_alpha_vantage_float(symbol)

    cache[symbol] = float_shares
    save_float_cache(cache)
    return float_shares


def passes_float_filter(float_shares: Optional[float]) -> bool:
    """True if float is between MIN_FLOAT and MAX_FLOAT, or unknown (allowed through)."""
    if float_shares is None:
        return True  # Unknown float → allow through, let strategy gates decide
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
        self.avg_daily_volume: dict[str, float] = {}  # symbol -> 20-day avg daily volume
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
        """Fetch 21 business days of OHLCV for prev close + avg daily volume."""
        self.log.info("[1/2] Fetching 21-day OHLCV (Databento EQUS.SUMMARY ohlcv-1d)...")
        try:
            client = db.Historical()
            today_ts = pd.Timestamp.now(tz="US/Eastern").normalize()
            start_day = (today_ts - pd.offsets.BusinessDay(21)).date()
            end_day = today_ts.date()

            self.log.info(f"      Requesting OHLCV from {start_day} to {end_day}...")
            data = client.timeseries.get_range(
                dataset="EQUS.SUMMARY",
                schema="ohlcv-1d",
                symbols="ALL_SYMBOLS",
                start=start_day,
                end=end_day,
            )

            # Insert symbology so to_df() maps instrument IDs to ticker symbols
            symbology_json = data.request_symbology(client)
            data.insert_symbology_json(symbology_json)
            df = data.to_df(pretty_px=True)

            if "symbol" not in df.columns:
                self.log.warning("      'symbol' column missing from df — check symbology insertion")
                return

            # Compute average daily volume from the full 20-day window
            if "volume" in df.columns:
                avg_vol = df.groupby("symbol")["volume"].mean().to_dict()
                self.avg_daily_volume = {k: float(v) for k, v in avg_vol.items()}
                self.log.info(f"      {len(self.avg_daily_volume):,} symbols with avg daily volume")

            # For prev_close: keep only the most recent row per symbol
            if "ts_event" in df.columns:
                df_latest = df.sort_values("ts_event").drop_duplicates("symbol", keep="last")
            else:
                df_latest = df.drop_duplicates("symbol", keep="last")

            self.prev_close = df_latest.set_index("symbol")["close"].to_dict()
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
    # Volume + RVOL helpers
    # -----------------------------------------------------------------------

    def _get_candidate_volumes(self) -> dict[str, int]:
        """Fetch current session volume for all candidates via Alpaca snapshot."""
        symbols = list(self.candidates.keys())
        if not symbols:
            return {}
        key = os.getenv("APCA_API_KEY_ID", "")
        secret = os.getenv("APCA_API_SECRET_KEY", "")
        if not key:
            self.log.warning("  [scanner] APCA_API_KEY_ID not set — skipping volume snapshot")
            return {}
        url = "https://data.alpaca.markets/v2/stocks/snapshots"
        params = {"symbols": ",".join(symbols), "feed": "sip"}
        headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return {sym: data[sym]["dailyBar"]["v"] for sym in data if sym in data}
        except Exception as e:
            self.log.warning(f"  [scanner] Volume snapshot failed: {e}")
            return {}

    def _rank_score(self, candidate: dict, volume: int, rvol: float) -> float:
        """Composite ranking score: RVOL 40%, volume 30%, gap 20%, float 10%."""
        gap_pct = candidate.get("gap_pct", 0)
        float_m = candidate.get("float_millions", 10) or 10
        rvol_score = math.log10(min(rvol, 50) + 1) / math.log10(51)
        vol_score = math.log10(max(volume, 1)) / 8
        gap_score = min(gap_pct, 100) / 100
        float_score = 1 - (min(float_m, 10) / 10)
        return (0.40 * rvol_score) + (0.30 * vol_score) + (0.20 * gap_score) + (0.10 * float_score)

    # -----------------------------------------------------------------------
    # Watchlist output
    # -----------------------------------------------------------------------

    def _get_current_symbols(self) -> set:
        """Return current candidate symbols."""
        with self.lock:
            return set(self.candidates.keys())

    def write_watchlist(self, label: str = "final"):
        """Write qualified candidates to watchlist.txt (and save JSON snapshot).
        Filters by RVOL/volume, ranks by composite score, append-only."""
        with self.lock:
            candidates_copy = dict(self.candidates)

        if not candidates_copy:
            self.log.info(f"[{label.upper()}] No candidates to write.")
            return

        # Fetch current session volumes for all candidates via Alpaca
        vol_snapshot = self._get_candidate_volumes()

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

        # Filter candidates by RVOL and pre-market volume, compute scores
        scored_candidates = []
        for c in candidates_copy.values():
            sym = c["symbol"]
            pm_volume = vol_snapshot.get(sym, 0)
            avg_vol = self.avg_daily_volume.get(sym, 0)
            rvol = (pm_volume / avg_vol) if avg_vol > 0 else 0.0

            # Attach volume metadata to candidate
            c["pm_volume"] = pm_volume
            c["rvol"] = round(rvol, 2)

            # Existing watchlist symbols bypass volume filter (already approved)
            if sym not in existing_symbols:
                if pm_volume < MIN_PM_VOLUME:
                    self.log.info(
                        f"  SKIP {sym}: pm_volume={pm_volume:,} < {MIN_PM_VOLUME:,}"
                    )
                    continue
                if rvol < MIN_RVOL:
                    self.log.info(
                        f"  SKIP {sym}: rvol={rvol:.2f} < {MIN_RVOL}"
                    )
                    continue

            score = self._rank_score(c, pm_volume, rvol)
            c["rank_score"] = round(score, 4)
            scored_candidates.append(c)

        # Sort by composite rank score descending
        scored_candidates.sort(key=lambda x: x["rank_score"], reverse=True)

        # 9:30 ET cutoff: no NEW symbols after 9:30 (existing watchlist preserved)
        # Data shows post-09:30 discoveries are negative EV (-$2,430, 25% WR)
        now_et = datetime.now(ET)
        past_cutoff = (now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 30))

        # Apply MAX_SCANNER_SYMBOLS cap (existing symbols count toward the cap)
        all_final = []
        total_count = len(existing_symbols)
        for c in scored_candidates:
            if c["symbol"] in existing_symbols:
                all_final.append(c)  # already in watchlist, always include
                continue
            if past_cutoff:
                continue  # Block new symbols after 9:30 ET
            if total_count < MAX_SCANNER_SYMBOLS:
                all_final.append(c)
                total_count += 1

        if past_cutoff and scored_candidates:
            new_blocked = [c["symbol"] for c in scored_candidates if c["symbol"] not in existing_symbols]
            if new_blocked:
                self.log.info(f"  [9:30 CUTOFF] Blocked {len(new_blocked)} new symbols: {new_blocked}")

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
                f"rvol={c.get('rvol', 0):.1f}x  vol={c.get('pm_volume', 0):,}  "
                f"score={c.get('rank_score', 0):.3f}  first={c['first_seen_et']}"
            )
        self.log.info(f"{'='*60}\n")

        if self.dry_run:
            self.log.info("[DRY RUN] Watchlist NOT written.")
            return

        # Write watchlist.txt (append-only: preserve existing entries)
        # Format: SYMBOL:gap_pct:rvol:float_m:pm_volume
        new_symbols = {c["symbol"] for c in all_final}
        with open(WATCHLIST_FILE, "w") as f:
            f.write(f"# Live scanner output — {self.today} {label}\n")
            f.write(f"# Format: SYMBOL:gap_pct:rvol:float_m:pm_volume\n")
            f.write(f"# Generated at {datetime.now(ET).strftime('%H:%M:%S')} ET\n")
            # Preserve existing entries not in current candidates
            for line in existing_lines:
                sym = line.split(":")[0].upper()
                if sym not in new_symbols:
                    f.write(f"{line}\n")
            # Write current candidates with metadata
            for c in all_final:
                float_m = c.get("float_millions", 0) or 0
                rvol = c.get("rvol", 0)
                pm_vol = c.get("pm_volume", 0)
                f.write(f"{c['symbol']}:{c['gap_pct']}:{rvol}:{float_m}:{pm_vol}\n")

        self.log.info(f"  Wrote {len(all_final)} symbols to {WATCHLIST_FILE}")

        # Save JSON snapshot
        json_path = os.path.join(SCANNER_DIR, f"live_{self.today}_{label}.json")
        with open(json_path, "w") as f:
            json.dump(all_final, f, indent=2, default=str)
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
            # Step 3: Time-managed loop (continuous until 9:30 AM ET cutoff)
            last_update_minute = -1  # track last 1-min update write
            _new_symbol_cutoff_h, _new_symbol_cutoff_m = 9, 30
            _seen_symbols: set = set()  # track symbols for post-cutoff filtering
            while True:
                now_et = datetime.now(ET)
                h, m = now_et.hour, now_et.minute

                # Initial watchlist at 7:00 AM
                if h == WINDOW_START_HOUR and m >= WINDOW_START_MINUTE and not self._initial_watchlist_written:
                    self._initial_watchlist_written = True
                    self.write_watchlist("initial")
                    last_update_minute = m
                    # Snapshot current symbols
                    _seen_symbols.update(self._get_current_symbols())

                # Scheduled write at 7:14 AM
                if not self._final_watchlist_written and (
                    h > 7 or (h == 7 and m >= 14)
                ):
                    self._final_watchlist_written = True
                    self.write_watchlist("7_14")
                    last_update_minute = m
                    _seen_symbols.update(self._get_current_symbols())

                # After 7:14, write every 1 minute until 9:30 cutoff
                if self._final_watchlist_written and m != last_update_minute:
                    past_cutoff = (h > _new_symbol_cutoff_h or
                                   (h == _new_symbol_cutoff_h and m >= _new_symbol_cutoff_m))
                    if not past_cutoff:
                        self.write_watchlist(f"update_{h:02d}{m:02d}")
                        last_update_minute = m
                        _seen_symbols.update(self._get_current_symbols())

                # Stop at 9:30 AM ET — write final and exit
                if h > _new_symbol_cutoff_h or (h == _new_symbol_cutoff_h and m >= _new_symbol_cutoff_m):
                    self.write_watchlist("final")
                    self.log.info(f"Scanner cutoff reached (9:30 AM ET). Stopping stream.")
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
