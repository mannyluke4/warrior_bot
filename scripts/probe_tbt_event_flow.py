"""probe_tbt_event_flow.py — Diagnose why Tier 1 symbols went data-blind 2026-05-06.

Hypothesis: in ib_insync, reqMktData() and reqTickByTickData() return DIFFERENT
Ticker objects for the same contract. The bot's `on_ticker_update` dispatch
routes whichever ticker fires `pendingTickersEvent` to `_drain_tick_by_tick_ticker()`,
which reads `ticker.tickByTicks`. If the snapshot ticker fires, its tickByTicks
is empty, and the drain silently exits — losing all snapshot updates AND
producing no work even when the symbol is "subscribed" to TBT.

This script tests that hypothesis directly: subscribe ERNA via BOTH paths,
hook pendingTickersEvent, watch for 30s, and print which Ticker objects fire
and which contain tickByTicks data.

Read-only — never places orders. Disconnects cleanly on exit.
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from datetime import datetime
from ib_insync import IB, Stock


SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "ERNA"
CLIENT_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 97
WATCH_SECONDS = int(sys.argv[3]) if len(sys.argv) > 3 else 30

print(f"=== TBT EVENT FLOW PROBE ===")
print(f"Symbol: {SYMBOL}")
print(f"clientId: {CLIENT_ID}")
print(f"Watch window: {WATCH_SECONDS}s")
print(f"Start: {datetime.now().isoformat(timespec='seconds')}")
print()

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=CLIENT_ID, timeout=10)
print(f"Connected. Account: {ib.managedAccounts()}")

contract = Stock(SYMBOL, "SMART", "USD")
ib.qualifyContracts(contract)

snapshot_ticker = ib.reqMktData(contract, "233", False, False)
tbt_ticker = ib.reqTickByTickData(contract, "AllLast", 0, False)

print(f"snapshot_ticker id: {id(snapshot_ticker)}")
print(f"tbt_ticker id     : {id(tbt_ticker)}")
print(f"SAME OBJECT?      : {snapshot_ticker is tbt_ticker}")
print()
print("Watching pendingTickersEvent for", WATCH_SECONDS, "s...")
print("(Each event prints: which ticker(s) fired + tickByTicks length)")
print()

events_by_id: dict[int, int] = defaultdict(int)
sample_logs: list[str] = []

def on_pending_tickers(tickers):
    for t in tickers:
        events_by_id[id(t)] += 1
        if len(sample_logs) < 25:  # cap log noise
            sym = t.contract.symbol if t.contract else "?"
            tbt_len = len(getattr(t, "tickByTicks", []) or [])
            last = getattr(t, "last", None)
            last_size = getattr(t, "lastSize", None)
            sample_logs.append(
                f"  [evt #{sum(events_by_id.values()):3}] sym={sym} "
                f"id={id(t)} tickByTicks_len={tbt_len} "
                f"last={last} lastSize={last_size}"
            )

ib.pendingTickersEvent += on_pending_tickers

start = time.time()
while time.time() - start < WATCH_SECONDS:
    ib.sleep(0.5)

print()
print("=== EVENTS LOG (first 25) ===")
for line in sample_logs:
    print(line)

print()
print("=== EVENTS-BY-TICKER-ID ===")
for tid, count in events_by_id.items():
    role = []
    if tid == id(snapshot_ticker): role.append("snapshot_ticker")
    if tid == id(tbt_ticker): role.append("tbt_ticker")
    print(f"  id={tid}  count={count}  role={'+'.join(role) or '?'}")

print()
print("=== FINAL TICKER STATE ===")
print(f"snapshot_ticker.last={snapshot_ticker.last} lastSize={snapshot_ticker.lastSize}")
print(f"snapshot_ticker.tickByTicks length: {len(getattr(snapshot_ticker, 'tickByTicks', []) or [])}")
print(f"tbt_ticker.last={tbt_ticker.last} lastSize={tbt_ticker.lastSize}")
print(f"tbt_ticker.tickByTicks length     : {len(getattr(tbt_ticker, 'tickByTicks', []) or [])}")

print()
print("=== CONCLUSION ===")
if snapshot_ticker is tbt_ticker:
    print("Same Ticker object — both APIs share state. Dispatch bug is NOT object-identity.")
    print("Hypothesis falsified. Investigate elsewhere (subscription longevity, idle timeout, etc.)")
else:
    snap_tbt_len = len(getattr(snapshot_ticker, 'tickByTicks', []) or [])
    tbt_tbt_len = len(getattr(tbt_ticker, 'tickByTicks', []) or [])
    if snap_tbt_len == 0 and tbt_tbt_len > 0:
        print(f"DIFFERENT objects. snapshot.tickByTicks=0, tbt.tickByTicks={tbt_tbt_len}")
        print("HYPOTHESIS CONFIRMED: drain reads from wrong ticker if snapshot fires the event.")
        print("Fix: dispatch by sym → look up state.tbt_tickers[sym], drain THAT ticker only.")
    else:
        print(f"DIFFERENT objects but BOTH have tickByTicks (snap={snap_tbt_len} tbt={tbt_tbt_len})")
        print("Surprising — investigate ib_insync version behavior.")

print()
print("Cleaning up...")
ib.cancelMktData(contract)
ib.cancelTickByTickData(contract, "AllLast")
ib.disconnect()
print("Done.")
