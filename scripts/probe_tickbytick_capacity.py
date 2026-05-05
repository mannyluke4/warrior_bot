"""probe_tickbytick_capacity.py — Probe IBKR account's reqTickByTickData
simultaneous-subscription cap.

Per DIRECTIVE_TICKBYTICK_MIGRATION.md (Stage 1). The number of active
tick-by-tick subscriptions IBKR allows depends on account equity and
commissions; retail baseline is 5, larger accounts get more. We don't
know the exact figure for this account until we test.

Approach:
  1. Connect to IB Gateway with a fresh clientId (default 98) so we
     don't collide with running bots (1=main, 2=sub-bot, 99=fetcher).
  2. Walk a list of safe liquid symbols NOT in the bot's current
     watchlist (AAPL, MSFT, SPY, QQQ, NVDA, TSLA, …).
  3. For each symbol: call reqTickByTickData('AllLast'); wait 5s; check
     whether IBKR returned an error (10089 / 10186 / similar) or
     whether the subscription is producing events.
  4. Report the count where it stops working = Tier 1 capacity.

The script is read-only — never places orders, never modifies state of
the running bots. Cancels all subscriptions on exit.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

# Repo root for shared imports
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from ib_insync import IB, Stock, util  # noqa: E402


# Probe universe — liquid, large-cap names that are guaranteed to have
# real-time data and that the bot doesn't trade. Picked to span exchanges
# (NYSE + NASDAQ) so we don't hit a per-exchange cap if one exists.
PROBE_SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META",   # NASDAQ mega-caps
    "TSLA", "NVDA", "AMD", "INTC", "ORCL",     # NASDAQ tech
    "JPM", "BAC", "WFC", "C", "GS",            # NYSE financials
    "JNJ", "PFE", "MRK", "BMY", "GILD",        # pharma
    "XOM", "CVX", "COP", "OXY", "MPC",         # energy
    "SPY", "QQQ", "IWM", "DIA", "VTI",         # ETFs
    "F", "GM", "T", "VZ", "DIS",               # miscellaneous large caps
    "NFLX", "CRM", "ADBE", "PYPL", "SQ",       # mid-tier NASDAQ
    "BABA", "NIO", "PDD", "JD", "TME",         # ADRs
    "PLTR", "SOFI", "RBLX", "U", "NET",        # mid-cap growth
]  # 50 candidates — overkill, but we'll stop on first failure


# IBKR error codes we care about
ERROR_TBT_LIMIT = 10186          # "Max number of tick-by-tick requests reached"
ERROR_TBT_NEED_SUB = 10089       # "Requested market data requires additional subscription"
ERROR_DATA_FARM = (2103, 2105)   # data farm disconnects (informational)
ERROR_HIST_FARM = (2107, 2108)   # historical farm (informational)


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe IBKR reqTickByTickData capacity")
    ap.add_argument("--client-id", type=int, default=98,
                    help="IBKR clientId (default 98, isolated from bots).")
    ap.add_argument("--port", type=int, default=4002, help="IB Gateway port.")
    ap.add_argument("--max-symbols", type=int, default=50,
                    help="Stop after testing this many symbols regardless.")
    ap.add_argument("--wait-seconds", type=float, default=5.0,
                    help="Seconds to wait after each subscription for events/errors.")
    args = ap.parse_args()

    print(f"=== reqTickByTickData CAPACITY PROBE ===")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Connection: 127.0.0.1:{args.port}  clientId={args.client_id}")
    print(f"Probe universe: up to {min(args.max_symbols, len(PROBE_SYMBOLS))} symbols")
    print()

    ib = IB()
    try:
        ib.connect("127.0.0.1", args.port, clientId=args.client_id, timeout=15)
    except Exception as e:
        print(f"FATAL: gateway connect failed: {e}", file=sys.stderr)
        return 2
    print(f"Connected. Account: {ib.managedAccounts()}")
    print()

    # Capture errors per request
    errors: List[Dict] = []
    ticks_per_req: Dict[int, int] = defaultdict(int)
    sub_to_sym: Dict[int, str] = {}

    def _on_error(reqId, errorCode, errorString, contract):
        errors.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "reqId": reqId,
            "code": errorCode,
            "msg": errorString,
            "symbol": getattr(contract, "symbol", None) if contract else None,
        })
        is_warning = errorCode in (200, *ERROR_DATA_FARM, *ERROR_HIST_FARM, 2158, 2104, 2106)
        prefix = "  ℹ️ " if is_warning else "  ⚠️ "
        print(f"{prefix}IBKR error {errorCode} reqId={reqId} — {errorString}")

    ib.errorEvent += _on_error

    successful: List[str] = []
    failed_at: str = ""
    failure_reason: str = ""

    symbols_to_test = PROBE_SYMBOLS[:args.max_symbols]
    print(f"Subscribing one-at-a-time to reqTickByTickData('AllLast'); "
          f"{args.wait_seconds:.0f}s wait between each.\n")

    for i, sym in enumerate(symbols_to_test, 1):
        contract = Stock(sym, "SMART", "USD")
        try:
            ib.qualifyContracts(contract)
        except Exception as e:
            print(f"  [{i}/{len(symbols_to_test)}] {sym:<6} qualify failed: {e}")
            continue

        # Snapshot error count before subscribing — we'll diff after the wait.
        err_count_before = len(errors)
        sub = ib.reqTickByTickData(contract, tickType="AllLast", numberOfTicks=0,
                                    ignoreSize=False)

        # Wait for events / errors. ib_insync's `sleep` pumps the event loop.
        ib.sleep(args.wait_seconds)

        # Check for tick-by-tick events on the ticker
        ticks_received = len(sub.tickByTicks) if hasattr(sub, "tickByTicks") else 0
        new_errors = errors[err_count_before:]
        critical_errors = [
            e for e in new_errors
            if e["code"] in (ERROR_TBT_LIMIT, ERROR_TBT_NEED_SUB)
        ]

        if critical_errors:
            err = critical_errors[0]
            failed_at = sym
            failure_reason = f"code {err['code']}: {err['msg']}"
            print(f"  [{i}/{len(symbols_to_test)}] {sym:<6} ❌ FAIL — {failure_reason}")
            ib.cancelTickByTickData(contract, tickType="AllLast")
            break

        successful.append(sym)
        print(f"  [{i}/{len(symbols_to_test)}] {sym:<6} ✓ subscribed; "
              f"{ticks_received} ticks in {args.wait_seconds:.0f}s")

    print()
    print(f"=== RESULT ===")
    print(f"Successful subscriptions: {len(successful)}")
    print(f"Symbols subscribed:       {', '.join(successful)}")
    if failed_at:
        print(f"Failed at:                {failed_at} ({failure_reason})")
    else:
        print(f"No failure — capacity is at least {len(successful)} (probe didn't exhaust)")

    print()
    print(f"=== Cleanup — cancelling all probe subscriptions ===")
    for sym in successful:
        contract = Stock(sym, "SMART", "USD")
        try:
            ib.cancelTickByTickData(contract, tickType="AllLast")
        except Exception:
            pass
    ib.sleep(2)

    ib.disconnect()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
