#!/usr/bin/env python3
"""One-off orphan flatten for FEBO (main bot, IBKR paper). Idempotent.

The main bot detected FEBO as an orphan (broker holds it, no bot state) and
entered ORPHAN HALT — it will NOT auto-flatten and blocks all new entries until
reconciled (bot_v3_hybrid.py:996). This clears that block so the v2 move-stack
(R5 paper validation) can trade. Connects on a DEDICATED clientId so it never
collides with the running bot. Submits a SELL LIMIT (outside-RTH for pre-market),
reprices down a few times to ensure a fill on a thin micro-cap, then logs to
logs/manual_interventions.log. If FEBO is already flat, it's a no-op.

Run from ~/warrior_bot_v2:  ./venv/bin/python flatten_febo.py
"""
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.expanduser("~/warrior_bot_v2"))
os.chdir(os.path.expanduser("~/warrior_bot_v2"))
from dotenv import load_dotenv
load_dotenv()
from ib_insync import IB, Stock, LimitOrder

ET = ZoneInfo("America/New_York")
SYMBOL = "FEBO"
HOST = os.getenv("IBKR_HOST", "127.0.0.1")
PORT = int(os.getenv("IBKR_PORT", "4002"))
CLIENT_ID = int(os.getenv("FLATTEN_CLIENT_ID", "77"))   # dedicated — not the bot's
MAX_REPRICES = int(os.getenv("FLATTEN_MAX_REPRICES", "4"))
WAIT_SEC = int(os.getenv("FLATTEN_WAIT_SEC", "20"))


def log_intervention(msg: str):
    line = f"{datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S')} ET  cc-session  manual-flatten  {SYMBOL}  {msg}\n"
    with open("logs/manual_interventions.log", "a") as f:
        f.write(line)
    print("LOGGED:", line.strip(), flush=True)


def main():
    ib = IB()
    try:
        ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=15)
    except Exception as e:
        print(f"FATAL: could not connect to IBKR {HOST}:{PORT} clientId={CLIENT_ID}: {e!r}", flush=True)
        return 2
    try:
        pos = next((p for p in ib.positions() if p.contract.symbol == SYMBOL and p.position != 0), None)
        if pos is None:
            print(f"{SYMBOL} already flat at broker — nothing to do (no-op).", flush=True)
            return 0
        qty = int(abs(pos.position))
        side = "SELL" if pos.position > 0 else "BUY"  # long orphan → SELL
        contract = Stock(SYMBOL, "SMART", "USD")
        ib.qualifyContracts(contract)
        print(f"{SYMBOL}: broker holds {pos.position} (avg ${pos.avgCost:.4f}) — flattening {qty} via {side} LIMIT", flush=True)

        for attempt in range(1, MAX_REPRICES + 1):
            tkr = ib.reqMktData(contract, "", True, False)
            ib.sleep(2.0)
            bid, ask, last = tkr.bid, tkr.ask, tkr.last
            ref = next((x for x in (bid, last, ask) if x and x > 0), None)
            if ref is None:
                ref = pos.avgCost
            # SELL: price at/below bid, getting more aggressive each attempt.
            aggression = 0.005 * attempt   # 0.5%, 1.0%, ...
            limit = round(max(0.01, ref * (1 - aggression)), 2)
            order = LimitOrder(side, qty, limit, outsideRth=True, tif="DAY")
            trade = ib.placeOrder(contract, order)
            print(f"  attempt {attempt}: {side} {qty} @ ${limit:.2f} (bid={bid} ask={ask} last={last})", flush=True)
            deadline = time.time() + WAIT_SEC
            while time.time() < deadline:
                ib.sleep(1.0)
                if trade.orderStatus.status == "Filled":
                    fpx = trade.orderStatus.avgFillPrice
                    print(f"  ✅ FILLED {qty} @ ${fpx:.4f}", flush=True)
                    log_intervention(f"flattened orphan {qty}sh @ ${fpx:.4f} (clientId {CLIENT_ID}) "
                                     f"to clear ORPHAN HALT for v2 move-stack R5. Per Manny.")
                    return 0
            ib.cancelOrder(order)
            ib.sleep(1.0)
            print(f"  attempt {attempt} unfilled — repricing", flush=True)
        print(f"⚠️ {SYMBOL} NOT filled after {MAX_REPRICES} attempts — left working/cancelled. "
              f"Re-run when liquidity improves (e.g. 9:30 ET open).", flush=True)
        log_intervention(f"flatten ATTEMPTED but unfilled after {MAX_REPRICES} reprices "
                         f"(thin liquidity); halt NOT cleared — retry at open.")
        return 1
    finally:
        ib.disconnect()


if __name__ == "__main__":
    sys.exit(main())
