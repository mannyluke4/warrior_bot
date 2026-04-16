#!/usr/bin/env python3
"""Isolated IBKRBroker test harness.

Connects to the live IBKR Gateway on a DIFFERENT clientId than the bot
(so the two can coexist), constructs an IBKRBroker, and exercises each
BrokerClient method end-to-end. Designed to be run while the bot is
live — it never places a fillable order.

Safety:
  - Limit BUY @ $1.00 on AAPL (which trades ~$250). Far-out-of-market.
    Will sit in "Submitted" state until we cancel it ~5s later. No fill.
  - No market orders. No short entries.
  - Test contract is AAPL (liquid, well-formed, always shortable on live).

Usage:
    python tools/test_ibkr_broker.py
    # prints per-method PASS / FAIL. Exit 0 = all passed.

Env knobs (optional):
    WB_TEST_IBKR_CLIENT_ID=99     # different from the bot (default 99)
    WB_TEST_IBKR_PORT=4002        # paper gateway (default 4002)
    WB_TEST_SYMBOL=AAPL           # which name to test with
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ib_insync import IB  # noqa: E402
from broker import (  # noqa: E402
    IBKRBroker, BrokerOrder, BrokerPosition,
    STATUS_SUBMITTED, STATUS_FILLED, STATUS_CANCELLED,
    STATUS_PARTIALLY, STATUS_REJECTED, STATUS_EXPIRED, STATUS_UNKNOWN,
    TERMINAL_STATUSES,
)


CLIENT_ID = int(os.getenv("WB_TEST_IBKR_CLIENT_ID", "99"))
PORT = int(os.getenv("WB_TEST_IBKR_PORT", "4002"))
HOST = os.getenv("IBKR_HOST", "127.0.0.1")
TEST_SYMBOL = os.getenv("WB_TEST_SYMBOL", "AAPL")
FAR_OUT_BUY_LIMIT = float(os.getenv("WB_TEST_FAR_LIMIT", "1.00"))  # won't fill


def green(msg): print(f"✓ {msg}", flush=True)
def red(msg): print(f"✗ {msg}", flush=True)
def info(msg): print(f"  {msg}", flush=True)


def test_connect() -> IB:
    ib = IB()
    ib.connect(HOST, PORT, clientId=CLIENT_ID)
    assert ib.isConnected(), "IB connection failed"
    green(f"connected to IBKR on {HOST}:{PORT} clientId={CLIENT_ID}")
    return ib


def test_account_equity(broker: IBKRBroker):
    eq = broker.get_account_equity()
    assert eq > 0, f"expected equity > 0, got {eq}"
    green(f"get_account_equity: ${eq:,.2f}")


def test_positions(broker: IBKRBroker):
    positions = broker.get_positions()
    green(f"get_positions: {len(positions)} open")
    for p in positions:
        info(f"  {p.symbol} qty={p.qty} avail={p.qty_available} "
             f"avg=${p.avg_entry_price:.2f} uPnL=${p.unrealized_pnl:+.2f}")
    # Assert shape: each returned BrokerPosition has the expected fields
    for p in positions:
        assert isinstance(p, BrokerPosition), f"wrong type: {type(p)}"
        assert p.symbol, "position.symbol should be non-empty"


def test_is_shortable(broker: IBKRBroker):
    # Phase 2 MVP always returns True. Exercise path + cache.
    s1 = broker.is_shortable(TEST_SYMBOL)
    s2 = broker.is_shortable(TEST_SYMBOL)  # second call: cached
    assert s1 is True, f"is_shortable MVP should be True, got {s1}"
    assert s2 is True, f"cached is_shortable should be True, got {s2}"
    green(f"is_shortable({TEST_SYMBOL}): {s1} (optimistic MVP)")


def test_submit_limit_then_cancel(broker: IBKRBroker):
    """Submit a far-out-of-market limit BUY, verify status is Submitted,
    then cancel, verify status is Cancelled. Exercise submit_limit,
    get_order_status, cancel_order, get_open_orders in one flow."""
    order = broker.submit_limit(
        symbol=TEST_SYMBOL, qty=1, side="BUY",
        limit_price=FAR_OUT_BUY_LIMIT, extended_hours=True,
    )
    assert isinstance(order, BrokerOrder)
    assert order.order_id, f"expected non-empty order_id, got {order.order_id!r}"
    assert order.symbol == TEST_SYMBOL
    assert order.qty == 1
    assert order.side == "BUY"
    green(f"submit_limit: id={order.order_id} status={order.status}")

    # Poll status for up to 3s — IBKR usually acks in ~0.5s. Use ib.sleep
    # (not time.sleep) so the event loop keeps pumping orderStatus events
    # during the wait. In the live bot this doesn't matter — daemon-thread
    # pollers run while the main loop pumps — but in this single-threaded
    # harness we must pump explicitly.
    ib = broker._ib
    deadline = time.time() + 3
    last = order
    while time.time() < deadline:
        s = broker.get_order_status(order.order_id)
        assert s is not None
        last = s
        if s.status in (STATUS_SUBMITTED, STATUS_PARTIALLY):
            break
        ib.sleep(0.2)
    assert last.status in (STATUS_SUBMITTED, STATUS_PARTIALLY), \
        f"expected Submitted/Partial, got {last.status} reason={last.reject_reason}"
    green(f"get_order_status post-submit: {last.status}")

    # Open-orders list should include our order
    open_orders = broker.get_open_orders()
    matching = [o for o in open_orders if o.order_id == order.order_id]
    assert matching, f"open_orders didn't include {order.order_id}"
    green(f"get_open_orders: found submitted order in list ({len(open_orders)} total open)")

    # Cancel + wait for cancelled status (event-pumped via ib.sleep)
    broker.cancel_order(order.order_id)
    deadline = time.time() + 5
    while time.time() < deadline:
        s = broker.get_order_status(order.order_id)
        if s and s.status == STATUS_CANCELLED:
            break
        ib.sleep(0.2)
    final = broker.get_order_status(order.order_id)
    assert final is not None
    assert final.status == STATUS_CANCELLED, \
        f"expected Cancelled, got {final.status}"
    green(f"cancel_order → status: {final.status}")


def test_cancel_unknown_order_is_noop(broker: IBKRBroker):
    """Canceling an order_id we never submitted should not raise."""
    broker.cancel_order("not-a-real-order-id-12345")
    green("cancel_order(unknown) is a no-op (no exception raised)")


def test_get_order_status_unknown(broker: IBKRBroker):
    """Unknown order_id returns None."""
    s = broker.get_order_status("not-a-real-order-id-99999")
    assert s is None, f"expected None, got {s}"
    green("get_order_status(unknown) returns None")


def main() -> int:
    ib = None
    failures = []
    try:
        ib = test_connect()
        broker = IBKRBroker(ib)
        info(f"IBKRBroker instantiated (test symbol: {TEST_SYMBOL})")
        print()

        for name, fn in [
            ("get_account_equity", test_account_equity),
            ("get_positions", test_positions),
            ("is_shortable", test_is_shortable),
            ("submit + cancel", test_submit_limit_then_cancel),
            ("cancel unknown", test_cancel_unknown_order_is_noop),
            ("get_order_status unknown", test_get_order_status_unknown),
        ]:
            try:
                fn(broker)
            except AssertionError as e:
                red(f"{name}: FAIL — {e}")
                failures.append(name)
            except Exception as e:
                red(f"{name}: ERROR — {type(e).__name__}: {e}")
                failures.append(name)

    finally:
        if ib and ib.isConnected():
            ib.disconnect()
            info("disconnected")

    print()
    if failures:
        red(f"FAILED: {len(failures)} test(s) — {', '.join(failures)}")
        return 1
    green("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
