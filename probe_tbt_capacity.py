#!/usr/bin/env python3
"""probe_tbt_capacity.py — re-measure the account's reqTickByTickData capacity.

TBT_MAX (WB_TBT_MAX) is currently 5, from a single 2026-05-05 probe. That cap is
the hard ceiling on how many movers the engine can watch at full resolution at
once — the whole tier-promotion bottleneck. If IBKR grants more tick-by-tick
lines now (they scale with account equity / commissions / market-data package),
raising TBT_MAX directly widens coverage. This re-runs the probe.

How it works: connect on a DISTINCT clientId, then subscribe to a list of liquid
symbols via reqTickByTickData('AllLast') ONE AT A TIME, watching errorEvent for
the tick-by-tick limit error (IBKR 10197 / "max number of tick-by-tick" / 322).
The first symbol that errors is the ceiling. Cancels everything and disconnects.

IMPORTANT — capacity is per ACCOUNT, shared across all clientIds. If the live
engine (clientId 1) is holding N tick-by-tick subs, this probe measures the
REMAINING capacity, so TOTAL = N + probe_result. For a clean TOTAL, run it while
the engine's tier1 is empty (after-hours, or stop the engine briefly). The script
prints the engine's current tier1 count hint from the log if it can.

Subscription ACCEPTANCE is capacity-gated, not data-gated, so this is valid
after-hours (you don't need live prints — you need to see which subs error).

Run:  ./venv/bin/python probe_tbt_capacity.py [MAX_TO_TRY] [SYM,SYM,...]
"""
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from ib_insync import IB, Stock  # noqa: E402

PORT = int(os.getenv("IBKR_PORT", "4002"))
CLIENT_ID = int(os.getenv("TBT_PROBE_CLIENT_ID", "88"))
MAX_TRY = int(sys.argv[1]) if len(sys.argv) > 1 else 25
# Always-liquid large/mid caps so a qualify never fails; tick-by-tick ACCEPTANCE
# is what we measure, not whether these are moving.
DEFAULT_SYMS = ("AAPL MSFT NVDA TSLA AMD AMZN META GOOGL SPY QQQ INTC F BAC "
                "SOFI PLTR NIO T AAL CCL SNAP RIVN LCID MARA RIOT COIN").split()
SYMS = sys.argv[2].split(",") if len(sys.argv) > 2 else DEFAULT_SYMS
SYMS = SYMS[:MAX_TRY]

# Tick-by-tick capacity / competing-data errors we treat as "ceiling hit".
LIMIT_ERRORS = {10197, 322, 420, 10089, 10090}

ib = IB()
errors: dict = {}  # reqId-ish → (code, msg) ; we key by symbol via contract


def on_error(reqId, code, msg, contract):
    sym = getattr(contract, "symbol", "?") if contract else "?"
    if code in LIMIT_ERRORS or "tick-by-tick" in msg.lower() or "max number" in msg.lower():
        errors.setdefault(sym, (code, msg))
        print(f"  ⛔ {sym}: IBKR {code} — {msg}", flush=True)
    elif code not in (2104, 2106, 2158, 2107, 2119, 162):
        print(f"  (info) {sym}: IBKR {code} — {msg}", flush=True)


def main():
    print(f"=== TBT capacity probe — port {PORT}, clientId {CLIENT_ID} ===", flush=True)
    print(f"Current WB_TBT_MAX = {os.getenv('WB_TBT_MAX', '5')} (the value to re-validate)\n", flush=True)
    ib.errorEvent += on_error
    try:
        ib.connect("127.0.0.1", PORT, clientId=CLIENT_ID, timeout=15)
    except Exception as e:
        print(f"CONNECT FAILED: {e!r}\n(Is the gateway up on {PORT}? Is clientId {CLIENT_ID} free?)", flush=True)
        return
    print("connected. subscribing tick-by-tick one at a time...\n", flush=True)

    ok = []
    for sym in SYMS:
        c = Stock(sym, "SMART", "USD")
        try:
            ib.qualifyContracts(c)
        except Exception as e:
            print(f"  (skip) {sym}: qualify failed: {e}", flush=True)
            continue
        before = len(errors)
        try:
            ib.reqTickByTickData(c, "AllLast", 0, False)
        except Exception as e:
            print(f"  ⛔ {sym}: reqTickByTickData raised: {e}", flush=True)
            errors.setdefault(sym, (-1, str(e)))
            break
        ib.sleep(1.2)  # let an error event arrive if the line was refused
        if sym in errors and len(errors) > before:
            print(f"  >>> CEILING at {len(ok)} concurrent tick-by-tick subs "
                  f"(the {len(ok)+1}th was refused)\n", flush=True)
            break
        ok.append(sym)
        print(f"  ✓ {sym} accepted ({len(ok)} concurrent)", flush=True)

    print(f"\n=== RESULT: {len(ok)} concurrent tick-by-tick subscriptions accepted "
          f"({'no ceiling hit within %d tries' % len(SYMS) if not errors else 'ceiling hit'}) ===", flush=True)
    print(f"  accepted: {ok}", flush=True)
    if len(ok) > int(os.getenv("WB_TBT_MAX", "5")):
        print(f"  → IBKR now allows MORE than WB_TBT_MAX={os.getenv('WB_TBT_MAX','5')}. "
              f"Consider raising WB_TBT_MAX toward {len(ok)} (leave headroom for the account's own usage).", flush=True)
    print("  NOTE: capacity is per-account & shared with the engine (clientId 1). "
          "If the engine held tick-by-tick subs during this probe, TOTAL = engine_count + this result.", flush=True)

    # Clean up: cancel everything we subscribed.
    for sym in ok:
        try:
            c = Stock(sym, "SMART", "USD"); ib.qualifyContracts(c)
            ib.cancelTickByTickData(c, "AllLast")
        except Exception:
            pass
    ib.disconnect()
    print("disconnected, all probe subscriptions cancelled.", flush=True)


if __name__ == "__main__":
    main()
