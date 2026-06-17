"""Regression test for the 2026-06-16 CRVO orphan bug: the entry-retry loop
ignored partial fills and resubmitted the full qty each retry, accumulating
unrecorded shares at the broker that were later re-adopted as orphans.

Validates WB_ENTRY_RECONCILE_FILLS=1 behavior:
  1. each retry sizes to the REMAINDER (qty - broker_held) → no over-accumulation
  2. on terminal (timeout/cancel), the position is reconciled to broker truth
     (partial fills are KEPT + managed, never left as an orphan)
  3. a clean full fill still records correctly (no regression)

Run: ./venv/bin/python tests/test_entry_partial_fill_reconcile.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot_v3_hybrid as b
from broker import BrokerOrder, BrokerPosition, STATUS_FILLED, STATUS_PARTIALLY


class FakeBroker:
    """Simulates a fast mover: every BUY order partially fills `fill_frac` of
    its requested qty immediately, then sits 'partially filled' forever (never
    completes) so the retry loop times out — exactly the CRVO failure mode.
    Tracks cumulative broker position across all orders."""
    def __init__(self, fill_frac=0.40, full_fill=False):
        self.fill_frac = fill_frac
        self.full_fill = full_fill
        self.orders = {}          # order_id -> dict(symbol, req, filled, limit)
        self.position = 0         # cumulative shares actually filled
        self.cost = 0.0           # sum(filled_i * price_i) for avg
        self._next = 1
        self.submitted_qtys = []  # every requested qty, for assertions

    def submit_limit(self, symbol, qty, side, limit_price, extended_hours=True):
        self.submitted_qtys.append(int(qty))
        oid = str(self._next); self._next += 1
        fill = int(qty) if self.full_fill else int(qty * self.fill_frac)
        self.orders[oid] = {"symbol": symbol, "req": int(qty), "filled": fill,
                            "limit": float(limit_price)}
        self.position += fill
        self.cost += fill * float(limit_price)
        return BrokerOrder(order_id=oid, symbol=symbol, qty=int(qty), side="BUY",
                           limit_price=float(limit_price),
                           status=(STATUS_FILLED if fill == int(qty) else STATUS_PARTIALLY),
                           filled_qty=fill, filled_avg_price=float(limit_price))

    def get_order_status(self, order_id):
        o = self.orders.get(str(order_id))
        if o is None:
            return None
        status = STATUS_FILLED if o["filled"] == o["req"] else STATUS_PARTIALLY
        return BrokerOrder(order_id=str(order_id), symbol=o["symbol"], qty=o["req"],
                           side="BUY", limit_price=o["limit"], status=status,
                           filled_qty=o["filled"], filled_avg_price=o["limit"])

    def cancel_order(self, order_id):
        pass  # broker keeps the partial fill; remainder is cancelled (no-op here)

    def get_positions(self):
        if self.position <= 0:
            return []
        avg = self.cost / self.position
        return [BrokerPosition(symbol="CRVO", qty=self.position,
                               qty_available=self.position, avg_entry_price=avg)]

    def get_buying_power(self):
        return 1_000_000.0


def _setup(fill_frac=0.40, full_fill=False):
    b.ENTRY_RECONCILE_FILLS = True
    b.ENTRY_RETRY_ENABLED = True
    b.ENTRY_MAX_RETRIES = 3
    b.ENTRY_RETRY_TIMEOUT_SEC = 0.4          # keep the loop fast
    b.ENTRY_MAX_CHASE_PCT_LOW = 1e9          # never chase-cap-abort in the test
    b.ENTRY_MAX_CHASE_PCT_HIGH = 1e9
    fake = FakeBroker(fill_frac=fill_frac, full_fill=full_fill)
    b.state.broker = fake
    b.state.last_tick_price = {"CRVO": 4.00}
    b.state.pending_order = None
    return fake


def test_partial_fills_reconciled_not_orphaned():
    fake = _setup(fill_frac=0.40)
    Q = 1000
    # Initial order, as enter_trade would have placed it (full qty).
    init = fake.submit_limit("CRVO", Q, "BUY", 4.00)
    b.state.open_position = {"symbol": "CRVO", "qty": Q, "entry": 4.00, "stop": 3.20,
                             "r": 0.80, "score": 11.0, "setup_type": "move_strike",
                             "peak": 4.00, "order_id": init.order_id, "fill_confirmed": False}
    b._verify_fill_with_retry("CRVO", Q, 0.80, init.order_id, 4.00, 4.00, "open_position")

    pos = b.state.open_position
    assert pos is not None, "BUG: position lost — partial fills orphaned (regression!)"
    assert pos["qty"] == fake.position, \
        f"recorded qty {pos['qty']} != broker held {fake.position} (orphan gap)"
    assert fake.position <= Q, \
        f"OVER-ACCUMULATED {fake.position} > intended {Q} (remainder-sizing failed)"
    assert pos["fill_confirmed"] is True, "kept partial must be fill_confirmed"
    # Kept shares MUST carry a real stop (= avg_fill - r) so manage_exit protects
    # them — regression guard for the seed-recovery fix.
    assert pos["stop"] is not None and abs(pos["stop"] - (pos["entry"] - 0.80)) < 1e-6, \
        f"kept position has no/wrong stop: stop={pos['stop']} entry={pos['entry']}"
    # retries must shrink (remainder sizing): each requested qty <= the prior
    later = fake.submitted_qtys[1:]
    assert all(later[i] <= later[i-1] for i in range(1, len(later))) and later[0] < Q, \
        f"retries not sized to remainder: {fake.submitted_qtys}"
    print(f"  PASS partial-fill reconcile: intended={Q} broker_held={fake.position} "
          f"recorded={pos['qty']} submits={fake.submitted_qtys} (no orphan, no over-fill)")


def test_clean_full_fill_no_regression():
    fake = _setup(full_fill=True)
    Q = 800
    init = fake.submit_limit("CRVO", Q, "BUY", 4.00)
    b.state.open_position = {"symbol": "CRVO", "qty": Q, "entry": 4.00, "stop": 3.20,
                             "r": 0.80, "score": 11.0, "setup_type": "move_strike",
                             "peak": 4.00, "order_id": init.order_id, "fill_confirmed": False}
    b._verify_fill_with_retry("CRVO", Q, 0.80, init.order_id, 4.00, 4.00, "open_position")
    pos = b.state.open_position
    assert pos is not None and pos["qty"] == Q, f"clean full fill broke: {pos}"
    assert fake.position == Q and len(fake.submitted_qtys) == 1, \
        f"full fill should not retry: submits={fake.submitted_qtys}"
    print(f"  PASS clean full fill: qty={pos['qty']} (single order, no retry)")


def test_gate_off_preserves_legacy():
    fake = _setup(fill_frac=0.40)
    b.ENTRY_RECONCILE_FILLS = False  # legacy behavior: orphan on terminal
    Q = 1000
    init = fake.submit_limit("CRVO", Q, "BUY", 4.00)
    b.state.open_position = {"symbol": "CRVO", "qty": Q, "entry": 4.00, "stop": 3.20,
                             "r": 0.80, "score": 11.0, "setup_type": "move_strike",
                             "peak": 4.00, "order_id": init.order_id, "fill_confirmed": False}
    b._verify_fill_with_retry("CRVO", Q, 0.80, init.order_id, 4.00, 4.00, "open_position")
    # Legacy: position cleared to None on final timeout (the original bug) and
    # the broker accumulated > intended (full-qty resubmits). This documents WHY
    # the gate exists.
    assert b.state.open_position is None, "gate-off should reproduce legacy orphan (None)"
    print(f"  PASS gate-off legacy: position=None, broker over-accumulated to "
          f"{fake.position} (the bug — fixed when gate ON)")


if __name__ == "__main__":
    test_partial_fills_reconciled_not_orphaned()
    test_clean_full_fill_no_regression()
    test_gate_off_preserves_legacy()
    print("ALL TESTS PASSED")
