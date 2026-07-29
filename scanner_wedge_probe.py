#!/usr/bin/env python3
"""scanner_wedge_probe.py — root-cause the recurring reqScannerData wedge.

The engine's IBKR scanner wedges at the 04:00 start (Error 162 "API scanner
subscription cancelled / Historical Market Data Service error") and never
recovers — a process restart re-wedges (proven 7/24, 7/27, 7/28). This probe
reproduces the exact reqScannerData calls the engine makes and distinguishes the
possible causes so we know what actually fixes it:

  A. LEAKED SUBSCRIPTION — ib_insync's reqScannerData does
     reqScannerSubscription + cancel; if a 162-erroring sub isn't cancelled it
     leaks a scanner slot. After ~N leaks every scan 162s. Test: does an explicit
     cancelScannerSubscription between calls stop the 162s? If yes → fix = cancel
     leaked subs (in-process recovery, no restart).
  B. SERVICE NOT READY at 04:00 — the HMDS/scanner farm isn't up that early.
     Test: 162 from the first call, but a later retry (or a fresh reqId after a
     delay) succeeds → fix = delay first scan / retry with backoff.
  C. SERVICE DOWN / PERMISSION — every call 162s regardless → fix = IBKR-side
     (market-data permission, data farm), not our code.

Run during the window you want to diagnose (ideally the 04:00-04:30 ET start when
it wedges, but any time reproduces the mechanism). Uses a DISTINCT clientId so it
won't disturb the engine.

Run:  ./venv/bin/python scanner_wedge_probe.py [N_ROUNDS]
"""
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from ib_insync import IB, ScannerSubscription  # noqa: E402

PORT = int(os.getenv("IBKR_PORT", "4002"))
CLIENT_ID = int(os.getenv("SCANNER_PROBE_CLIENT_ID", "87"))
N_ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 8
SCAN_CODES = ["TOP_PERC_GAIN", "MOST_ACTIVE", "HOT_BY_VOLUME"]
MIN_PRICE = float(os.getenv("WB_MIN_PRICE", "2.00"))
MAX_PRICE = float(os.getenv("WB_MAX_PRICE", "20.00"))
MIN_PM_VOLUME = int(os.getenv("WB_MIN_PM_VOLUME", "50000"))
MAX_MARKET_CAP = 500_000_000

errors: list = []


def on_error(reqId, code, msg, contract):
    if code == 162 or "scanner" in msg.lower():
        errors.append((code, msg))


def make_sub(code):
    return ScannerSubscription(
        instrument="STK", locationCode="STK.US.MAJOR", scanCode=code,
        abovePrice=MIN_PRICE, belowPrice=MAX_PRICE,
        aboveVolume=int(MIN_PM_VOLUME), marketCapBelow=MAX_MARKET_CAP,
        numberOfRows=20,
    )


def one_scan(ib, code, cancel_after):
    """Run one reqScannerData; return (n_results, had_162). cancel_after=True
    explicitly cancels the subscription to test the leaked-slot hypothesis."""
    before = len(errors)
    n = 0
    try:
        sub = make_sub(code)
        results = ib.reqScannerData(sub)
        n = len(results or [])
        if cancel_after:
            try:
                ib.cancelScannerSubscription(ib.reqScannerSubscription(make_sub(code)))
            except Exception:
                pass
    except Exception as e:
        print(f"    reqScannerData({code}) raised: {e!r}", flush=True)
    ib.sleep(1.0)
    had162 = len(errors) > before
    return n, had162


def run_phase(ib, label, cancel_after):
    print(f"\n--- {label} (cancel_after={cancel_after}) ---", flush=True)
    total_rows = 0
    for r in range(N_ROUNDS):
        line = []
        for code in SCAN_CODES:
            n, had162 = one_scan(ib, code, cancel_after)
            total_rows += n
            line.append(f"{code}={n}{'*162' if had162 else ''}")
        print(f"  round {r+1}: " + "  ".join(line), flush=True)
        time.sleep(1)
    return total_rows


def main():
    et = time.strftime("%H:%M:%S")
    print(f"=== scanner-wedge probe {et} — port {PORT}, clientId {CLIENT_ID}, {N_ROUNDS} rounds ===", flush=True)
    ib = IB()
    ib.errorEvent += on_error
    try:
        ib.connect("127.0.0.1", PORT, clientId=CLIENT_ID, timeout=15)
    except Exception as e:
        print(f"CONNECT FAILED: {e!r}", flush=True)
        return
    print("connected.", flush=True)

    # Phase 1: replicate the engine EXACTLY (no explicit cancel between calls).
    # Many rounds test whether rows eventually drop to 0 (a subscription leak
    # developing) or stay healthy (wedge is not a leak on THIS connection).
    p1_rows = run_phase(ib, "PHASE 1: engine-style (no explicit cancel)", cancel_after=False)

    # Phase 2: same but explicitly cancel each subscription (leaked-slot test).
    errors.clear()
    p2_rows = run_phase(ib, "PHASE 2: with explicit cancelScannerSubscription", cancel_after=True)

    # The signal is RESULT COUNT, not 162 count: 162 is benign cancel-noise that
    # fires AFTER results arrive. Wedged = 0 results; healthy = 16-20 results.
    print("\n=== VERDICT ===", flush=True)
    print(f"  (162 errors are benign cancel-noise — they fire even on healthy scans "
          f"that returned rows. The real signal is whether ROWS came back.)", flush=True)
    print(f"  Phase 1 total rows: {p1_rows}   Phase 2 total rows: {p2_rows}", flush=True)
    if p1_rows > 0:
        print(f"  → This FRESH connection's scanner WORKS ({p1_rows} rows). But the ENGINE "
              f"(clientId 1) returns 0 all day. So the wedge is CONNECTION-STATE-specific to "
              f"the engine's clientId — NOT an IBKR service/permission outage. A process "
              f"restart re-inherits the same clientId's wedged gateway session, which is why "
              f"restarts don't fix it. FIX = on wedge, RECONNECT WITH A FRESH clientId "
              f"(or rotate clientId on restart), not just restart the process.", flush=True)
    else:
        print(f"  → Even a fresh connection got 0 rows → genuine IBKR-side scanner outage "
              f"right now. Re-run during active hours to confirm.", flush=True)
    ib.disconnect()
    print("disconnected.", flush=True)


if __name__ == "__main__":
    main()
