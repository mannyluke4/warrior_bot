"""Unit tests for epl_framework.py."""

import os
import sys
import unittest
from datetime import datetime, timedelta

# Ensure EPL is enabled for tests
os.environ["WB_EPL_ENABLED"] = "1"

from epl_framework import (
    GraduationContext, EntrySignal, ExitSignal,
    EPLStrategy, EPLWatchlist, StrategyRegistry, PositionArbitrator,
)


def _make_ctx(symbol: str = "TEST", minutes_ago: int = 0,
              price: float = 10.0) -> GraduationContext:
    return GraduationContext(
        symbol=symbol,
        graduation_time=datetime.now() - timedelta(minutes=minutes_ago),
        graduation_price=price,
        sq_entry_price=price - 0.28,
        sq_stop_price=price - 0.42,
        hod_at_graduation=price + 0.10,
        vwap_at_graduation=price - 1.0,
        pm_high=price - 0.50,
        avg_volume_at_graduation=50000,
        sq_trade_count=1,
        r_value=0.14,
    )


class DummyStrategy(EPLStrategy):
    """Minimal strategy for testing."""
    def __init__(self, name_str="dummy", prio=1, signal=None):
        self._name = name_str
        self._prio = prio
        self._signal = signal
        self.graduations = []
        self.expiries = []
        self.resets = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._prio

    def on_graduation(self, ctx):
        self.graduations.append(ctx.symbol)

    def on_expiry(self, symbol):
        self.expiries.append(symbol)

    def on_bar(self, symbol, bar):
        return self._signal

    def on_tick(self, symbol, price, size):
        return None

    def manage_exit(self, symbol, price, bar):
        return None

    def reset(self, symbol):
        self.resets.append(symbol)


class TestEPLWatchlist(unittest.TestCase):
    def test_add_and_check(self):
        wl = EPLWatchlist(max_stocks=5, expiry_minutes=60)
        ctx = _make_ctx("VERO")
        wl.add(ctx)
        self.assertTrue(wl.is_graduated("VERO"))
        self.assertFalse(wl.is_graduated("NOPE"))
        self.assertEqual(wl.symbols, ["VERO"])

    def test_remove(self):
        wl = EPLWatchlist()
        wl.add(_make_ctx("A"))
        wl.remove("A")
        self.assertFalse(wl.is_graduated("A"))

    def test_max_capacity_eviction(self):
        wl = EPLWatchlist(max_stocks=2, expiry_minutes=60)
        wl.add(_make_ctx("A", minutes_ago=10))
        wl.add(_make_ctx("B", minutes_ago=5))
        # At capacity — adding C should evict oldest (A)
        wl.add(_make_ctx("C", minutes_ago=0))
        self.assertFalse(wl.is_graduated("A"))
        self.assertTrue(wl.is_graduated("B"))
        self.assertTrue(wl.is_graduated("C"))

    def test_re_graduation_updates(self):
        wl = EPLWatchlist()
        wl.add(_make_ctx("VERO", price=8.0))
        wl.add(_make_ctx("VERO", price=12.0))
        ctx = wl.get_context("VERO")
        self.assertEqual(ctx.graduation_price, 12.0)
        self.assertEqual(len(wl.symbols), 1)

    def test_expiry(self):
        wl = EPLWatchlist(expiry_minutes=30)
        wl.add(_make_ctx("OLD", minutes_ago=31))
        wl.add(_make_ctx("NEW", minutes_ago=5))
        expired = wl.check_expiry(datetime.now())
        self.assertEqual(expired, ["OLD"])

    def test_clear(self):
        wl = EPLWatchlist()
        wl.add(_make_ctx("A"))
        wl.add(_make_ctx("B"))
        wl.clear()
        self.assertEqual(wl.symbols, [])


class TestStrategyRegistry(unittest.TestCase):
    def test_register_sorted_by_priority(self):
        reg = StrategyRegistry()
        low = DummyStrategy("low", prio=1)
        high = DummyStrategy("high", prio=10)
        reg.register(low)
        reg.register(high)
        self.assertEqual(reg._strategies[0].name, "high")

    def test_notify_graduation(self):
        reg = StrategyRegistry()
        s = DummyStrategy()
        reg.register(s)
        ctx = _make_ctx("VERO")
        reg.notify_graduation(ctx)
        self.assertEqual(s.graduations, ["VERO"])

    def test_notify_expiry(self):
        reg = StrategyRegistry()
        s = DummyStrategy()
        reg.register(s)
        reg.notify_expiry("VERO")
        self.assertEqual(s.expiries, ["VERO"])

    def test_collect_signals_sorted_by_confidence(self):
        reg = StrategyRegistry()
        sig_low = EntrySignal("V", "s1", 10.0, 9.0, None, 1.0, "r1", 0.3)
        sig_high = EntrySignal("V", "s2", 10.0, 9.0, None, 1.0, "r2", 0.9)
        reg.register(DummyStrategy("s1", prio=1, signal=sig_low))
        reg.register(DummyStrategy("s2", prio=2, signal=sig_high))
        signals = reg.collect_entry_signals("V", bar={"o": 10})
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0].confidence, 0.9)

    def test_get_strategy(self):
        reg = StrategyRegistry()
        s = DummyStrategy("myname")
        reg.register(s)
        self.assertEqual(reg.get_strategy("myname").name, "myname")
        self.assertIsNone(reg.get_strategy("nope"))

    def test_reset_all(self):
        reg = StrategyRegistry()
        s = DummyStrategy()
        reg.register(s)
        reg.reset_all("VERO")
        self.assertEqual(s.resets, ["VERO"])


class TestPositionArbitrator(unittest.TestCase):
    def setUp(self):
        self.wl = EPLWatchlist()
        self.reg = StrategyRegistry()
        self.arb = PositionArbitrator(self.reg, self.wl)
        self.wl.add(_make_ctx("VERO"))

    def test_can_enter_basic(self):
        self.assertTrue(self.arb.can_epl_enter("VERO", "IDLE", False, datetime.now()))

    def test_blocked_not_graduated(self):
        self.assertFalse(self.arb.can_epl_enter("NOPE", "IDLE", False, datetime.now()))

    def test_blocked_has_position(self):
        self.assertFalse(self.arb.can_epl_enter("VERO", "IDLE", True, datetime.now()))

    def test_blocked_sq_priority(self):
        self.assertFalse(self.arb.can_epl_enter("VERO", "PRIMED", False, datetime.now()))
        self.assertFalse(self.arb.can_epl_enter("VERO", "ARMED", False, datetime.now()))

    def test_blocked_cooldown(self):
        self.arb.set_cooldown("VERO", datetime.now(), cooldown_seconds=300)
        self.assertFalse(self.arb.can_epl_enter("VERO", "IDLE", False, datetime.now()))
        # After cooldown
        future = datetime.now() + timedelta(seconds=301)
        self.assertTrue(self.arb.can_epl_enter("VERO", "IDLE", False, future))

    def test_blocked_session_loss_cap(self):
        self.arb.record_epl_trade_result("VERO", -1001)
        self.assertTrue(self.arb.session_loss_cap_hit)
        self.assertFalse(self.arb.can_epl_enter("VERO", "IDLE", False, datetime.now()))

    def test_blocked_max_trades(self):
        for _ in range(3):
            self.arb.record_epl_trade_result("VERO", 50)
        self.assertFalse(self.arb.can_epl_enter("VERO", "IDLE", False, datetime.now()))

    def test_get_best_signal(self):
        sig = EntrySignal("V", "s1", 10.0, 9.0, None, 1.0, "test", 0.8)
        self.assertEqual(self.arb.get_best_signal([sig]), sig)
        self.assertIsNone(self.arb.get_best_signal([]))

    def test_reset_session(self):
        self.arb.record_epl_trade_result("VERO", -500)
        self.arb.reset_session()
        self.assertEqual(self.arb.session_pnl, 0.0)


if __name__ == "__main__":
    unittest.main()
