"""Read-only probe: dump every accountValues() tag IBKR populates right now.

Used to design broker.get_buying_power()'s tag-fallback hierarchy with real
field names rather than assumed ones. Does NOT subscribe to market data and
does NOT place any orders. Connects with a distinct clientId (99) so it
cannot collide with the live bot (clientId=1) or the L2 reader (clientId=42).
"""
from __future__ import annotations

import os
import sys
import time
from collections import defaultdict

from ib_insync import IB

HOST = os.getenv("IBKR_HOST", "127.0.0.1")
PORT = int(os.getenv("IBKR_PORT", "4002"))
CLIENT_ID = 99
SETTLE_S = 4.0

CASH_OF_INTEREST = {
    "BuyingPower",
    "AvailableFunds",
    "EquityWithLoanValue",
    "ExcessLiquidity",
    "NetLiquidation",
    "TotalCashValue",
    "CashBalance",
    "GrossPositionValue",
    "DayTradesRemaining",
    "AccountType",
    "Currency",
    "AccruedCash",
    "FullAvailableFunds",
    "FullExcessLiquidity",
    "FullInitMarginReq",
    "FullMaintMarginReq",
    "InitMarginReq",
    "MaintMarginReq",
    "Leverage",
    "RegTEquity",
    "RegTMargin",
    "SMA",
}


def main() -> int:
    ib = IB()
    print(f"[probe] connecting to {HOST}:{PORT} clientId={CLIENT_ID}", flush=True)
    ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=15)
    print(f"[probe] connected. waiting {SETTLE_S}s for accountValues to populate...", flush=True)
    ib.sleep(SETTLE_S)

    values = list(ib.accountValues())
    print(f"[probe] received {len(values)} account-value records", flush=True)

    by_account: dict[str, dict[tuple[str, str], str]] = defaultdict(dict)
    for v in values:
        by_account[v.account][(v.tag, v.currency)] = v.value

    for account in sorted(by_account):
        print()
        print(f"=== account {account} ===")
        rows = by_account[account]

        print("-- cash / margin / buying-power tags --")
        for tag in sorted(CASH_OF_INTEREST):
            usd = rows.get((tag, "USD"))
            bcy = rows.get((tag, "BASE"))
            blank = rows.get((tag, ""))
            cell = usd if usd is not None else (bcy if bcy is not None else blank)
            if cell is not None:
                src = "USD" if usd is not None else ("BASE" if bcy is not None else "''")
                print(f"  {tag:30s} = {cell:>20s}   [{src}]")
            else:
                print(f"  {tag:30s} = <not populated>")

        print("-- every tag/currency pair returned --")
        for (tag, currency), value in sorted(rows.items()):
            cur = currency or "(blank)"
            print(f"  {tag:30s} [{cur:6s}] = {value}")

    ib.disconnect()
    print("\n[probe] disconnected. done.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
