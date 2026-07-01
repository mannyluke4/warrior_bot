#!/usr/bin/env python3
"""alpaca_scanner.py — IBKR-free / Databento-free premarket gapper scanner.

Built 2026-07-01 for the IBKR outage: the IBKR scanner (ibkr_scanner) is the
real source normally, but it's down, and the Databento live scanner
(EQUS.MINI) has been delivering ~0 volume for weeks. This scans via Alpaca
market data and writes the same watchlist.txt the engine/publisher consume
(SYMBOL:gap_pct:rvol:float_m:pm_volume).

Data reality: the Alpaca account is IEX-only (SIP 403), so VOLUME undercounts
badly. We therefore filter on GAP% + PRICE (both reliable on IEX — last trade
vs clean prevClose), NOT absolute volume. RVOL is computed IEX-relative
(today's IEX vol / 20d avg IEX vol) so the ratio is self-consistent. Float is
backfilled from float_cache (Databento historical, still available).

Universe: Alpaca movers (gainers) ∪ most-actives, then gap% is RECOMPUTED
from snapshots (the movers %chg is corrupted by stale pre-reverse-split
references — recomputing against the clean prevDailyBar self-corrects it).

Run: ./venv/bin/python alpaca_scanner.py   (loops until the cutoff)
"""
from __future__ import annotations

import os
import time
import logging
from datetime import datetime

import pytz
import requests
from dotenv import load_dotenv

load_dotenv("/Users/duffy/warrior_bot_v2/.env")

ET = pytz.timezone("America/New_York")
DATA = "https://data.alpaca.markets"
KEY = os.getenv("APCA_API_KEY_ID") or os.getenv("MAIN_APCA_API_KEY_ID")
SEC = os.getenv("APCA_API_SECRET_KEY") or os.getenv("MAIN_APCA_API_SECRET_KEY")
H = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SEC}

MIN_PRICE = float(os.getenv("WB_MIN_PRICE", "2.0"))
MAX_PRICE = float(os.getenv("WB_MAX_PRICE", "20.0"))
MIN_GAP = float(os.getenv("WB_MIN_GAP_PCT", "10.0"))
MIN_IEX_VOL = int(os.getenv("WB_ALPACA_MIN_IEX_VOL", "300"))   # liquidity floor (IEX undercounts)
MAX_FLOAT_M = float(os.getenv("WB_MAX_FLOAT", "20"))           # keep it small-cap (float millions)
FEED = os.getenv("WB_ALPACA_FEED", "iex").lower()             # 'sip' once real-time data is subscribed
POLL_SEC = int(os.getenv("WB_ALPACA_SCAN_SEC", "45"))
CUTOFF = os.getenv("WB_SCANNER_CUTOFF_ET", "20:00")
WATCHLIST = os.getenv("WB_WATCHLIST_FILE", "watchlist.txt")

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("alpaca_scanner")


def _get(url):
    r = requests.get(url, headers=H, timeout=15)
    r.raise_for_status()
    return r.json()


def universe() -> list[str]:
    syms = set()
    try:
        j = _get(f"{DATA}/v1beta1/screener/stocks/movers?top=50")
        for g in (j.get("gainers") or []):
            if g.get("symbol"):
                syms.add(g["symbol"].upper())
    except Exception as e:
        log.warning(f"movers fetch failed: {e}")
    try:
        j = _get(f"{DATA}/v1beta1/screener/stocks/most-actives?top=50")
        for a in (j.get("most_actives") or []):
            if a.get("symbol"):
                syms.add(a["symbol"].upper())
    except Exception as e:
        log.warning(f"most-actives fetch failed: {e}")
    # plain equity tickers only; drop 5-char warrants/units (…W / …U)
    return [s for s in syms
            if s.isalpha() and 1 <= len(s) <= 5
            and not (len(s) == 5 and s[-1] in ("W", "U"))]


def snapshots(syms: list[str]) -> dict:
    out = {}
    for i in range(0, len(syms), 100):
        chunk = ",".join(syms[i:i + 100])
        try:
            out.update(_get(f"{DATA}/v2/stocks/snapshots?symbols={chunk}&feed={FEED}"))
        except Exception as e:
            log.warning(f"snapshot chunk failed: {e}")
    return out


def avg_daily_vol(syms: list[str]) -> dict:
    """20-session avg IEX daily volume for RVOL (self-consistent ratio)."""
    if not syms:
        return {}
    out = {}
    try:
        chunk = ",".join(syms)
        url = (f"{DATA}/v2/stocks/bars?symbols={chunk}&timeframe=1Day&limit=20"
               f"&feed={FEED}&adjustment=split")
        j = _get(url)
        for sym, bars in (j.get("bars") or {}).items():
            vols = [b.get("v", 0) for b in bars[:-1]]  # exclude today
            if vols:
                out[sym] = sum(vols) / len(vols)
    except Exception as e:
        log.warning(f"avg-vol fetch failed: {e}")
    return out


def load_floats() -> dict:
    try:
        from float_cache import load_float_cache
        return load_float_cache()
    except Exception:
        return {}


def scan_once(fcache: dict) -> list[tuple]:
    uni = universe()
    snaps = snapshots(uni)
    rows = []
    for sym, s in snaps.items():
        lt = (s.get("latestTrade") or {}).get("p")
        pdc = (s.get("prevDailyBar") or {}).get("c")
        db = (s.get("dailyBar") or {})
        dv = db.get("v", 0)
        if not lt or not pdc or pdc <= 0:
            continue
        if not (MIN_PRICE <= lt <= MAX_PRICE):
            continue
        gap = (lt - pdc) / pdc * 100.0
        if gap < MIN_GAP:
            continue
        if dv < MIN_IEX_VOL:
            continue
        rows.append([sym, round(gap, 2), dv, lt])
    # RVOL for the survivors (IEX-relative)
    avg = avg_daily_vol([r[0] for r in rows])
    out = []
    for sym, gap, dv, lt in rows:
        a = avg.get(sym, 0)
        rvol = round(dv / a, 2) if a > 0 else 0.0
        fs = fcache.get(sym)
        fm_val = round(fs / 1e6, 2) if fs else None
        # Drop large-caps (known float over the cap); keep unknown-float names.
        if fm_val is not None and fm_val > MAX_FLOAT_M:
            continue
        fm = fm_val if fm_val is not None else "?"
        out.append((sym, gap, rvol, fm, dv))
    out.sort(key=lambda r: -r[1])   # by gap desc
    return out


def write_watchlist(rows: list[tuple]) -> None:
    now = datetime.now(ET).strftime("%H:%M:%S")
    lines = [f"# Alpaca scanner output — {datetime.now(ET).date()} {now}",
             "# Format: SYMBOL:gap_pct:rvol:float_m:pm_volume"]
    for sym, gap, rvol, fm, dv in rows:
        lines.append(f"{sym}:{gap}:{rvol}:{fm}:{dv}")
    tmp = WATCHLIST + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, WATCHLIST)


def main() -> None:
    if not (KEY and SEC):
        log.error("No Alpaca creds (APCA_API_KEY_ID / SECRET). Aborting.")
        return
    ch, cm = (int(x) for x in CUTOFF.split(":")[:2])
    log.info(f"Alpaca gapper scanner: price ${MIN_PRICE}-${MAX_PRICE}, "
             f"gap>={MIN_GAP}%, every {POLL_SEC}s until {CUTOFF} ET (IEX feed).")
    fcache = load_floats()
    while True:
        now = datetime.now(ET)
        if now.hour * 60 + now.minute >= ch * 60 + cm:
            log.info("Cutoff reached — stopping.")
            break
        try:
            rows = scan_once(fcache)
            write_watchlist(rows)
            log.info(f"Wrote {len(rows)} gappers: {[r[0] for r in rows][:15]}")
        except Exception as e:
            log.warning(f"scan cycle error: {e!r}")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
