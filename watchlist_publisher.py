#!/usr/bin/env python3
"""watchlist_publisher.py — IBKR-free watchlist publisher (2026-06-30).

Purpose: keep a watchlist flowing to the manual bot when IBKR MARKET DATA is
unavailable (e.g. the ~2026-07-01→07 outage) but the Databento scanner is
still running. Run this INSTEAD of bot_v3_hybrid.py during the outage.

It binds the SAME engine socket the manual bot already consumes
(WB_ENGINE_TCP_BIND:WB_ENGINE_TCP_PORT + the Unix socket), so the manual bot
needs NO changes — it just sees a watchlist with per-symbol metadata.

Everything published is Databento-sourced, so nothing here touches IBKR:
  - symbols + gap% + RVOL + float  ← the scanner's watchlist.txt
  - float                          ← float_cache (Databento), backfill
  - ATH                            ← ath_cache (Databento), if WB_ENGINE_ATH_ENABLED=1
There are NO live ticks, so the manual bot shows no live price / HOD / LOD
(those need a tick feed). That's the expected degraded state.

Usage (on the mac mini, with .env providing the socket/port config):
    WB_ENGINE_PUBLISH_ENABLED=1 ./venv/bin/python watchlist_publisher.py
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# The publisher only binds when enabled; default it on for this tool so a
# bare launch works, but respect an explicit override.
os.environ.setdefault("WB_ENGINE_PUBLISH_ENABLED", "1")

from engine_publisher import get_publisher  # noqa: E402

WATCHLIST_FILE = os.getenv("WB_WATCHLIST_FILE", "watchlist.txt")
POLL_SEC = int(os.getenv("WB_WL_PUBLISH_SEC", "15"))       # subscription refresh cadence
PRICE_SEC = int(os.getenv("WB_WL_PRICE_SEC", "3"))         # price-tick cadence
ATH_ENABLED = os.getenv("WB_ENGINE_ATH_ENABLED", "0") == "1"

# Alpaca IEX price feed (2026-07-01): during the IBKR outage the manual bot
# has no ticks, so it can't price/size an order. Poll Alpaca snapshots for the
# watchlist symbols and publish last-trade + NBBO as ticks so the manual bot
# shows live-ish prices and can trade. IEX-only (small-cap prints are sparse,
# ~seconds latency) but far better than nothing.
import requests  # noqa: E402
_APCA_KEY = os.getenv("APCA_API_KEY_ID") or os.getenv("MAIN_APCA_API_KEY_ID")
_APCA_SEC = os.getenv("APCA_API_SECRET_KEY") or os.getenv("MAIN_APCA_API_SECRET_KEY")
_APCA_H = {"APCA-API-KEY-ID": _APCA_KEY, "APCA-API-SECRET-KEY": _APCA_SEC}
_APCA_DATA = "https://data.alpaca.markets"
_APCA_FEED = os.getenv("WB_ALPACA_FEED", "iex").lower()   # 'sip' once real-time is subscribed


def alpaca_snapshots(symbols: list[str]) -> dict:
    out = {}
    for i in range(0, len(symbols), 40):
        chunk = ",".join(symbols[i:i + 40])
        for _ in range(3):   # ride SIP-propagation 403 flakiness
            try:
                r = requests.get(
                    f"{_APCA_DATA}/v2/stocks/snapshots?symbols={chunk}&feed={_APCA_FEED}",
                    headers=_APCA_H, timeout=8)
                if r.status_code == 200:
                    out.update(r.json())
                    break
            except Exception:
                pass
            time.sleep(0.4)
    return out


_MAX_AGE_SEC = int(os.getenv("WB_WL_PRICE_MAX_AGE_SEC", "600"))  # never publish stale prints


def _age_sec(ts_iso):
    """Seconds since an ISO8601 UTC timestamp, or None if unparseable."""
    if not ts_iso:
        return None
    try:
        from datetime import datetime, timezone
        t = ts_iso.replace("Z", "+00:00")
        # trim sub-second precision Alpaca sends beyond microseconds
        if "." in t:
            head, tail = t.split(".", 1)
            frac = "".join(c for c in tail if c.isdigit())[:6]
            off = tail[len(frac):] if not tail[len(frac):].isdigit() else "+00:00"
            t = f"{head}.{frac}{'+00:00' if '+' not in off and '-' not in off else off}"
        dt = datetime.fromisoformat(t)
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        return None


def publish_prices(pub, symbols: list[str]) -> int:
    """Publish last-trade + NBBO as ticks — ONLY when the print is fresh.
    The free Alpaca IEX feed has no premarket data (frozen at yesterday's
    close until RTH), so a staleness guard prevents publishing yesterday's
    price as if it were live — which would be worse than no price."""
    if not symbols or not (_APCA_KEY and _APCA_SEC):
        return 0
    snaps = alpaca_snapshots(symbols)
    n = 0
    for sym, s in snaps.items():
        lt = s.get("latestTrade") or {}
        q = s.get("latestQuote") or {}
        age = _age_sec(lt.get("t"))
        if age is None or age > _MAX_AGE_SEC:
            continue  # stale (e.g. premarket with no IEX data) — don't publish
        px = lt.get("p")
        if px and px > 0:
            pub.publish_tick(sym, px, ts_iso=lt.get("t"), size=int(lt.get("s") or 0),
                             bid=q.get("bp"), ask=q.get("ap"))
            n += 1
    return n


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def session_hi_lo(symbols: list[str]) -> dict:
    """Today's session HIGH/LOW per symbol from Alpaca 1-min bars (04:00 ET on).
    Shipped as hod/lod so the manual bot seeds real session extremes instead of
    its since-connect calc. (Alpaca's dailyBar is stale in premarket — shows
    yesterday — so minute bars are the reliable source.)"""
    if not symbols or not (_APCA_KEY and _APCA_SEC):
        return {}
    from datetime import datetime, timezone, timedelta
    et = timezone(timedelta(hours=-4))   # EDT (this outage window is all July)
    start = (datetime.now(et).replace(hour=4, minute=0, second=0, microsecond=0)
             .astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    out = {}
    for i in range(0, len(symbols), 40):
        chunk = ",".join(symbols[i:i + 40])
        for _ in range(3):
            try:
                r = requests.get(
                    f"{_APCA_DATA}/v2/stocks/bars?symbols={chunk}&timeframe=1Min"
                    f"&start={start}&limit=10000&feed={_APCA_FEED}",
                    headers=_APCA_H, timeout=12)
                if r.status_code == 200:
                    for sym, bars in (r.json().get("bars") or {}).items():
                        if bars:
                            out[sym] = (round(max(b["h"] for b in bars), 4),
                                        round(min(b["l"] for b in bars), 4))
                    break
            except Exception:
                pass
            time.sleep(0.4)
    return out


def build_meta(watchlist: list[str]) -> list[dict]:
    """Mirror bot_v3_hybrid._publish_subscriptions' meta assembly. gap/rvol/
    float/ath from scanner+caches; hod/lod from today's Alpaca minute bars."""
    # gap/rvol/float from the scanner's watchlist.txt line
    # (SYMBOL:gap:rvol:float:pm_volume).
    wl_meta: dict[str, tuple] = {}
    try:
        with open(WATCHLIST_FILE) as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                p = ln.split(":")
                if len(p) >= 3:
                    wl_meta[p[0].strip().upper()] = (
                        _f(p[1]), _f(p[2]), _f(p[3]) if len(p) >= 4 else None
                    )
    except Exception:
        pass

    try:
        from float_cache import load_float_cache
        fcache = load_float_cache()
    except Exception:
        fcache = {}

    acache = {}
    if ATH_ENABLED:
        try:
            from ath_cache import load_ath_cache
            acache = load_ath_cache()
        except Exception:
            acache = {}

    hilo = session_hi_lo(watchlist)

    meta = []
    for sym in watchlist:
        gap, rvol, fm = wl_meta.get(sym, (None, None, None))
        if fm is None:
            fs = fcache.get(sym)
            if fs:
                fm = round(fs / 1e6, 2)
        item = {"symbol": sym, "gap_pct": gap, "rvol": rvol, "float_m": fm}
        hl = hilo.get(sym)
        if hl:
            item["hod"], item["lod"] = hl[0], hl[1]
        if ATH_ENABLED:
            try:
                from ath_cache import get_ath
                a = get_ath(sym, acache)
                if a is not None:
                    item["ath"] = round(a, 4)
            except Exception:
                pass
        meta.append(item)
    return meta


def read_watchlist() -> list[str]:
    syms = []
    try:
        with open(WATCHLIST_FILE) as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                s = ln.split(":")[0].strip().upper()
                if s and s.isalpha() and 1 <= len(s) <= 5:
                    syms.append(s)
    except Exception:
        pass
    return sorted(set(syms))


def main() -> None:
    pub = get_publisher()
    if not pub.enabled:
        print("[WL_PUB] WB_ENGINE_PUBLISH_ENABLED=0 — nothing to do. Set it to 1.",
              flush=True)
        return
    pub.start()
    have_prices = bool(_APCA_KEY and _APCA_SEC)
    print(f"[WL_PUB] subs every {POLL_SEC}s, Alpaca prices every {PRICE_SEC}s "
          f"(ATH={'on' if ATH_ENABLED else 'off'}, prices={'on' if have_prices else 'OFF'}). "
          f"IBKR-free degraded mode.", flush=True)
    last_sig = None
    last_subs = 0.0
    wl: list[str] = []
    while True:
        now = time.time()
        # Refresh the watchlist + metadata periodically (cheap, de-duped).
        if now - last_subs >= POLL_SEC or not wl:
            wl = read_watchlist()
            meta = build_meta(wl)
            pub.publish_subscriptions(wl, meta=meta)
            last_subs = now
            sig = (tuple(wl), len(meta))
            if sig != last_sig:
                print(f"[WL_PUB] published {len(wl)} symbols: {wl}", flush=True)
                last_sig = sig
        # Publish live-ish prices as ticks so the manual bot can quote/size/trade.
        if have_prices:
            try:
                publish_prices(pub, wl)
            except Exception as e:
                print(f"[WL_PUB] price feed error: {e!r}", flush=True)
        time.sleep(PRICE_SEC)


if __name__ == "__main__":
    main()
