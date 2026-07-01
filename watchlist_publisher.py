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
POLL_SEC = int(os.getenv("WB_WL_PUBLISH_SEC", "15"))
ATH_ENABLED = os.getenv("WB_ENGINE_ATH_ENABLED", "0") == "1"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def build_meta(watchlist: list[str]) -> list[dict]:
    """Mirror bot_v3_hybrid._publish_subscriptions' meta assembly, minus the
    IBKR/tick-derived fields (hod/lod). All inputs are Databento."""
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

    meta = []
    for sym in watchlist:
        gap, rvol, fm = wl_meta.get(sym, (None, None, None))
        if fm is None:
            fs = fcache.get(sym)
            if fs:
                fm = round(fs / 1e6, 2)
        item = {"symbol": sym, "gap_pct": gap, "rvol": rvol, "float_m": fm}
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
    print(f"[WL_PUB] publishing {WATCHLIST_FILE} every {POLL_SEC}s "
          f"(ATH={'on' if ATH_ENABLED else 'off'}). IBKR-free degraded mode.",
          flush=True)
    last_sig = None
    while True:
        wl = read_watchlist()
        meta = build_meta(wl)
        # publish_subscriptions de-dupes internally; the call is cheap. It
        # also re-sends the latest frame to each newly-connected manual bot.
        pub.publish_subscriptions(wl, meta=meta)
        sig = (tuple(wl), len(meta))
        if sig != last_sig:
            print(f"[WL_PUB] published {len(wl)} symbols: {wl}", flush=True)
            last_sig = sig
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
