"""Databento EQUS.MINI live-feed health probe (2026-06-23).

The decisive test for the 6/19-6/22 scanner outage: subscribe to the SAME live
feed the scanner uses (EQUS.MINI tbbo) for a handful of always-liquid names and
count trade prints + shares over a short window. MUST be run during market hours
(or active pre-market ~08:00 ET) — after-hours there are legitimately ~0 trades,
so a zero reading off-hours proves nothing.

  alive  → many trade prints + real share volume  → feed is fine, look elsewhere
  DEAD   → ~0 prints during active trading         → live delivery is broken;
                                                      escalate to Databento support

Run: ./venv/bin/python scanner_feed_probe.py [SECONDS] [SYM,SYM,...]
"""
import os, sys, signal, datetime
from dotenv import load_dotenv
load_dotenv("/Users/duffy/warrior_bot_v2/.env")
import databento as db

SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 15
SYMS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["AAPL", "TSLA", "NVDA", "SPY", "AMD"]
key = os.getenv("DATABENTO_API_KEY") or os.getenv("DB_API_KEY")

et = datetime.datetime.now()  # local; informational
print(f"Probe: EQUS.MINI tbbo {SYMS} for {SECS}s  (local {et:%H:%M})")


class _TO(Exception):
    pass


signal.signal(signal.SIGALRM, lambda *a: (_ for _ in ()).throw(_TO()))
n = 0
vol = 0
per = {s: 0 for s in SYMS}
live = None
idmap = {}
try:
    live = db.Live(key)
    live.subscribe(dataset="EQUS.MINI", schema="tbbo", stype_in="raw_symbol", symbols=SYMS)
    signal.alarm(SECS + 2)
    for rec in live:
        if isinstance(rec, db.SymbolMappingMsg):
            idmap[rec.instrument_id] = rec.stype_out_symbol
            continue
        if isinstance(rec, db.TBBOMsg):
            n += 1
            try:
                sz = int(rec.size)
            except Exception:
                sz = 0
            vol += sz
            s = idmap.get(rec.instrument_id)
            if s in per:
                per[s] += sz
    signal.alarm(0)
except _TO:
    pass
except Exception as e:
    print("ERR:", repr(e)[:160])
finally:
    try:
        if live:
            live.stop()
    except Exception:
        pass

print(f"\nRESULT: {n} trade prints, {vol:,} shares in ~{SECS}s")
for s, v in per.items():
    print(f"  {s}: {v:,}")
if n == 0 or vol == 0:
    print("\n>>> VERDICT: DEAD — zero trade flow. If market is active, the EQUS.MINI"
          "\n    live delivery is broken; escalate to Databento (subscription is active,"
          "\n    historical has the data, so it's a live-gateway problem on their side).")
else:
    print("\n>>> VERDICT: ALIVE — feed is delivering. If the scanner is still empty,"
          "\n    the problem is downstream (accumulation/filters), not the feed.")
