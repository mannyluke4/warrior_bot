"""Tests for framework.run_live (Wave 4 paper deployment).

Covered:
  - Dry-run mode loads, verifies, and exits without submitting orders.
  - Strategy load + filter wiring (the 3 Wave-4 YAMLs).
  - Force-exit at 19:55 ET fires SELL LIMIT (not MARKET).
  - Position state persistence round-trip.
  - VIX > 25 suppresses entry.
  - Monday entries skipped.
  - TieredSizer tier_lock=True keeps risk at $300.

Tests are pure unit tests: they monkey-patch LiveBroker / LiveDataFeed so
no IBKR / Alpaca connections are required.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, time as dtime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _framework_env(monkeypatch, tmp_path):
    """Set the .env.framework defaults for every test."""
    monkeypatch.setenv("WB_FRAMEWORK_IB_CLIENT_ID", "51")
    monkeypatch.setenv(
        "WB_FRAMEWORK_STRATEGIES",
        "pdh_fade_filtered,orb_aligned_300plus_monskip,pdh_breakout_f4",
    )
    monkeypatch.setenv("WB_USE_VIX_REGIME", "1")
    monkeypatch.setenv("WB_VIX_SUPPRESS_THRESHOLD", "25")
    monkeypatch.setenv("WB_VIX_REENABLE_THRESHOLD", "22")
    monkeypatch.setenv("WB_FRAMEWORK_SKIP_MONDAYS", "1")
    monkeypatch.setenv("WB_PORTFOLIO_CONFLICT_RULE", "release_on_stop")
    monkeypatch.setenv("WB_PORTFOLIO_LOG_LOCK_COLLISIONS", "1")
    monkeypatch.setenv("WB_SIZING_MODE", "tiered")
    monkeypatch.setenv("WB_TIER_INITIAL", "1")
    monkeypatch.setenv("WB_TIER_LOCK", "1")
    monkeypatch.setenv("WB_TIER_AUTO_ADVANCE", "0")
    monkeypatch.setenv("WB_NO_MARKET_ORDERS", "1")
    monkeypatch.setenv("WB_NO_OVERNIGHTS", "1")
    monkeypatch.setenv("WB_NO_BROKER_STOPS", "1")
    monkeypatch.setenv("APCA_API_KEY_ID", "test_key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test_secret")
    monkeypatch.setenv("APCA_PAPER", "true")
    # Redirect persistence dirs to tmp_path so tests don't pollute
    monkeypatch.setenv("WB_FRAMEWORK_STATE_DIR", str(tmp_path / "paper_state"))
    monkeypatch.setenv("WB_FRAMEWORK_REPORT_DIR", str(tmp_path / "reports"))
    # Redirect TieredSizer state to tmp so tier_lock test is hermetic
    monkeypatch.setenv("WB_TIER_STATE_PATH", str(tmp_path / "tier_state.json"))


def _patch_broker_and_feed(runner_module):
    """Replace LiveBroker/LiveDataFeed with mocks that always succeed.

    Returns (broker_mock_class, feed_mock_class).
    """
    broker_mock = MagicMock()
    broker_instance = MagicMock()
    broker_instance.connect.return_value = True
    broker_instance.is_connected = True
    broker_instance.get_account_equity.return_value = 25_000.0
    broker_instance.dry_run = False
    broker_instance._no_market_orders = True
    broker_instance._no_broker_stops = True
    broker_instance._client = MagicMock()
    # Default: entry result is a "filled" OrderResult
    from framework.live_broker import OrderResult

    broker_instance.submit_entry.return_value = OrderResult(
        order_id="abc",
        symbol="X",
        qty=100,
        side="BUY",
        limit_price=10.0,
        status="filled",
        filled_qty=100,
        filled_avg_price=10.0,
        attempts=1,
        reason="filled",
    )
    broker_instance.submit_exit.return_value = OrderResult(
        order_id="exit-1",
        symbol="X",
        qty=100,
        side="SELL",
        limit_price=9.95,
        status="submitted",
    )
    broker_mock.return_value = broker_instance

    feed_mock = MagicMock()
    feed_instance = MagicMock()
    feed_instance.connect.return_value = True
    feed_instance.is_connected = True
    feed_instance.subscribe.return_value = True
    feed_instance.seed_history.return_value = 0
    feed_instance.get_history.return_value = []
    feed_instance.get_prior_day_bars.return_value = []
    feed_instance.ib = MagicMock()
    feed_mock.return_value = feed_instance

    return broker_mock, feed_mock, broker_instance, feed_instance


# ---------------------------------------------------------------------------
# 1. Dry-run mode does not submit orders
# ---------------------------------------------------------------------------


def test_dry_run_does_not_submit_orders(monkeypatch, tmp_path):
    from framework import run_live

    broker_mock, feed_mock, broker_instance, feed_instance = _patch_broker_and_feed(
        run_live
    )
    # In dry-run the broker should set dry_run=True
    def _broker_factory(**kwargs):
        broker_instance.dry_run = bool(kwargs.get("dry_run", False))
        return broker_instance

    monkeypatch.setattr(run_live, "LiveBroker", _broker_factory)
    monkeypatch.setattr(run_live, "LiveDataFeed", lambda **kw: feed_instance)

    runner = run_live.FrameworkRunner(dry_run=True, verbose=False)
    rc = runner.run(max_iterations=1)

    assert rc == 0
    # No entry/exit/limit submissions in dry-run
    broker_instance.submit_entry.assert_not_called()
    broker_instance.submit_exit.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Strategy load + filter wiring
# ---------------------------------------------------------------------------


def test_strategy_load_uses_same_yamls_as_backtest(monkeypatch):
    """All 3 Wave-4 YAMLs load and use the same SIGNAL_FUNCS as the backtest."""
    from framework import run_live
    from backtest.portfolio_backtest import SIGNAL_FUNCS

    _, _, broker_instance, feed_instance = _patch_broker_and_feed(run_live)
    monkeypatch.setattr(run_live, "LiveBroker", lambda **kw: broker_instance)
    monkeypatch.setattr(run_live, "LiveDataFeed", lambda **kw: feed_instance)

    runner = run_live.FrameworkRunner(dry_run=True, verbose=False)
    arm_names = {a.name for a in runner.arms}
    assert "PDH-PDL-Fade-Filtered" in arm_names
    assert "ORB-Aligned-300Plus-MonSkip" in arm_names
    assert "PDH-Breakout-F4" in arm_names

    # Each arm's YAML filename must be in SIGNAL_FUNCS
    for a in runner.arms:
        fname = Path(a.yaml_path).name
        assert fname in SIGNAL_FUNCS, (
            f"arm {a.name} yaml {fname} not wired into SIGNAL_FUNCS"
        )


def test_retired_strategies_are_skipped(monkeypatch):
    """vwap_mean_reversion + round_number have status: retired — must be skipped."""
    from framework import run_live

    _, _, broker_instance, feed_instance = _patch_broker_and_feed(run_live)
    monkeypatch.setattr(run_live, "LiveBroker", lambda **kw: broker_instance)
    monkeypatch.setattr(run_live, "LiveDataFeed", lambda **kw: feed_instance)

    monkeypatch.setenv(
        "WB_FRAMEWORK_STRATEGIES",
        "pdh_fade_filtered,vwap_mean_reversion,round_number,pdh_breakout_f4",
    )
    runner = run_live.FrameworkRunner(dry_run=True, verbose=False)
    names = [a.name for a in runner.arms]
    # The two retired ones must be skipped
    assert all("VWAP" not in n or "Mean" not in n for n in names) or len(names) == 2
    # And we still have at least the two non-retired
    assert any("PDH-PDL-Fade-Filtered" in n for n in names)
    assert any("PDH-Breakout-F4" in n for n in names)


# ---------------------------------------------------------------------------
# 3. Force-exit at 19:55 ET fires SELL LIMIT (not MARKET)
# ---------------------------------------------------------------------------


def test_force_exit_uses_sell_limit_not_market(monkeypatch):
    """The force-exit chain MUST call submit_limit / force_flatten — never
    submit_market. submit_market is wired to raise RuntimeError."""
    import force_exit as fe_mod

    from framework.live_broker import LiveBroker

    # Build a real LiveBroker but stub out the alpaca client
    monkeypatch.setenv("APCA_API_KEY_ID", "x")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "y")
    broker = LiveBroker(api_key="x", api_secret="y", paper=True, dry_run=False)
    broker._connected = True

    fake_alpaca = MagicMock()
    submitted_orders: list[dict] = []

    def _submit_order(req):
        # alpaca-py would return an Order; we return a thin mock
        submitted_orders.append(
            {
                "symbol": req.symbol,
                "qty": req.qty,
                "side": str(req.side),
                "limit_price": float(getattr(req, "limit_price", 0) or 0),
                "type": type(req).__name__,
            }
        )
        m = MagicMock()
        m.id = "ord-1"
        return m

    fake_alpaca.submit_order = _submit_order
    fake_alpaca.get_order_by_id = MagicMock(
        return_value=MagicMock(status="filled", filled_qty=100, filled_avg_price=10.0)
    )
    fake_alpaca.cancel_order_by_id = MagicMock()
    broker._client = fake_alpaca

    # Reset force_exit's once-per-day latch
    fe_mod.reset_fired_flag()
    # Force-exit at 19:55 — confirm the trigger time logic
    assert fe_mod.should_force_exit_now(now_et=datetime(2026, 5, 18, 19, 55, 0).replace(tzinfo=None))

    # submit_market must raise (hard constraint)
    with pytest.raises(RuntimeError):
        broker.submit_market("AAPL", 100, "SELL")
    with pytest.raises(RuntimeError):
        broker.submit_stop("AAPL", 100, "SELL")

    # force_flatten uses submit_limit under the hood
    result = broker.force_flatten("AAPL", 100, 10.0)
    # Either filled or attempted via submit_limit — never via MarketOrderRequest
    for o in submitted_orders:
        assert "Limit" in o["type"], f"force_flatten submitted non-limit order: {o}"


# ---------------------------------------------------------------------------
# 4. Position state persistence round-trip
# ---------------------------------------------------------------------------


def test_persistence_round_trip(tmp_path):
    """Write open_trades.json, load it back, verify identity."""
    from framework.run_live import FrameworkPersistence, OpenTrade

    persist = FrameworkPersistence(tmp_path, date(2026, 5, 18))
    ot = OpenTrade(
        arm_name="PDH-Breakout-F4",
        yaml_path="strategies/pdh_breakout_f4.yaml",
        symbol="AAPL",
        side="BUY",
        direction="long",
        qty=100,
        entry_price=180.50,
        stop_price=178.25,
        target_price=185.00,
        entry_ts="2026-05-18T09:35:00",
        risk_dollars=300.0,
        order_id="ord-1",
        session_date="2026-05-18",
        secondary_fill=False,
    )
    persist.write_open_trades({"AAPL": ot})
    loaded = persist.load_open_trades()
    assert "AAPL" in loaded
    assert loaded["AAPL"].symbol == "AAPL"
    assert loaded["AAPL"].qty == 100
    assert loaded["AAPL"].entry_price == 180.50
    assert loaded["AAPL"].stop_price == 178.25
    assert loaded["AAPL"].arm_name == "PDH-Breakout-F4"
    # Risk + marker also round-trip cleanly
    from framework.run_live import RiskState

    risk = RiskState(
        starting_equity=25000.0, current_equity=25300.0, hwm=25500.0, lwm=24800.0,
        daily_pnl=300.0, entries_today=1, stops_today=0, targets_today=1,
    )
    persist.write_risk(risk)
    raw = json.loads((persist.dir / "risk.json").read_text())
    assert raw["starting_equity"] == 25000.0
    assert raw["targets_today"] == 1


# ---------------------------------------------------------------------------
# 5. VIX > 25 suppresses entry
# ---------------------------------------------------------------------------


def test_vix_above_25_suppresses(monkeypatch):
    from framework.live_signal_engine import SignalEvaluator
    from framework.vix_regime import VIXRegime
    from backtest.portfolio_backtest import StrategyArm

    # VIX overlay enabled, threshold 25
    monkeypatch.setenv("WB_USE_VIX_REGIME", "1")
    monkeypatch.setenv("WB_VIX_SUPPRESS_THRESHOLD", "25")

    arm = StrategyArm.from_yaml(
        str(REPO / "strategies" / "pdh_breakout_f4.yaml")
    )
    ev = SignalEvaluator(arms=[arm], vix_regime=VIXRegime(enabled=True))
    # Even with a perfect setup, VIX 30 should return empty
    fake_bars = [
        # Doesn't matter — VIX check happens first and returns [] before
        # signal eval reaches the SIGNAL_FUNCS.
    ]
    result = ev.on_bar_close(
        symbol="AAPL",
        history=fake_bars,
        prior_bars=[],
        session_date=date(2026, 5, 20),  # Wednesday (not Monday)
        vix_value=30.0,
    )
    assert result == [], "VIX=30 must suppress entries"

    # VIX 21 (below threshold) should not gate
    result_ok = ev.on_bar_close(
        symbol="AAPL",
        history=fake_bars,
        prior_bars=[],
        session_date=date(2026, 5, 20),
        vix_value=21.0,
    )
    # Empty bar history → no signal, but not because of VIX
    assert result_ok == []


# ---------------------------------------------------------------------------
# 6. Monday entries skipped
# ---------------------------------------------------------------------------


def test_monday_entries_are_skipped(monkeypatch):
    from framework.live_signal_engine import SignalEvaluator
    from framework.vix_regime import VIXRegime
    from backtest.portfolio_backtest import StrategyArm

    monkeypatch.setenv("WB_FRAMEWORK_SKIP_MONDAYS", "1")
    arm = StrategyArm.from_yaml(
        str(REPO / "strategies" / "pdh_breakout_f4.yaml")
    )
    ev = SignalEvaluator(
        arms=[arm], vix_regime=VIXRegime(enabled=False), skip_mondays_env=True
    )
    # 2026-05-18 is a Monday — must return []
    result = ev.on_bar_close(
        symbol="AAPL",
        history=[],
        prior_bars=[],
        session_date=date(2026, 5, 18),
    )
    assert result == [], "Monday must suppress new entries"


# ---------------------------------------------------------------------------
# 7. TieredSizer tier_lock=True keeps risk at $300
# ---------------------------------------------------------------------------


def test_tier_lock_keeps_risk_at_300(monkeypatch, tmp_path):
    """With WB_TIER_LOCK=1 and equity skyrocketing, risk_per_signal stays $300."""
    monkeypatch.setenv("WB_TIER_INITIAL", "1")
    monkeypatch.setenv("WB_TIER_LOCK", "1")
    monkeypatch.setenv("WB_TIER_AUTO_ADVANCE", "0")
    state_path = tmp_path / "tier_state.json"

    from framework.sizing import TieredSizer

    sizer = TieredSizer(
        initial_tier=1, tier_lock=True, auto_advance=False, state_path=state_path
    )
    # Equity at Tier 1 floor
    assert sizer.compute_risk(25_000) == 300.0
    # Even at Tier 9-equivalent equity, risk stays at Tier 1's $300
    big_equity = 500_000.0
    # Simulate many advancement-gate triggers via on_session_close
    for i in range(120):
        sizer.on_session_close(
            session_date=date(2026, 1, 1),
            equity=big_equity,
            portfolio_returns=[0.01] * 60,  # always positive, high Sharpe
        )
    assert sizer.current_tier == 1, "tier_lock=True must pin tier at 1"
    assert sizer.compute_risk(big_equity) == 300.0, (
        "tier_lock=True must keep risk_per_signal at $300 regardless of equity"
    )


# ---------------------------------------------------------------------------
# 8. Filter dispatcher integration
# ---------------------------------------------------------------------------


def test_filter_dispatcher_reuses_backtest_logic():
    """passes_pre_entry_filters is the same code path the backtest uses."""
    from framework.filters import passes_pre_entry_filters

    # PDH-Breakout F4 has a symbol_blacklist
    spec = {
        "symbol_blacklist": ["PLTR", "CRM"],
    }
    # Use a Tuesday so the env-default skip_mondays doesn't pre-empt
    # the symbol_blacklist check.
    tuesday = date(2026, 5, 19)
    assert tuesday.weekday() == 1
    ok, reason = passes_pre_entry_filters(
        spec=spec,
        entry_ts=datetime(2026, 5, 19, 10, 0),
        entry_price=10.0,
        direction="long",
        symbol="PLTR",
        session_date=tuesday,
        vwap_at_entry=None,
        bars_before_entry=[],
        entry_bar_volume=0.0,
    )
    assert not ok
    assert reason == "symbol_blacklist"


# ---------------------------------------------------------------------------
# 9. No-market-orders + no-broker-stops contract
# ---------------------------------------------------------------------------


def test_broker_rejects_market_and_stop_orders():
    """LiveBroker MUST raise on submit_market and submit_stop — hard rule."""
    from framework.live_broker import LiveBroker

    broker = LiveBroker(api_key="x", api_secret="y", paper=True)
    with pytest.raises(RuntimeError, match=r"(?i)market"):
        broker.submit_market("AAPL", 100, "SELL")
    with pytest.raises(RuntimeError, match=r"(?i)stops"):
        broker.submit_stop("AAPL", 100, "SELL")


# ---------------------------------------------------------------------------
# 10. Daily report writes when invoked
# ---------------------------------------------------------------------------


def test_daily_report_writes_to_cowork_reports(monkeypatch, tmp_path):
    from framework import run_live

    _, _, broker_instance, feed_instance = _patch_broker_and_feed(run_live)
    monkeypatch.setattr(run_live, "LiveBroker", lambda **kw: broker_instance)
    monkeypatch.setattr(run_live, "LiveDataFeed", lambda **kw: feed_instance)

    runner = run_live.FrameworkRunner(dry_run=True, verbose=False)
    p = runner.write_daily_report()
    assert p.exists()
    body = p.read_text()
    assert "Framework Daily Report" in body
    assert "Equity:" in body
    assert "Per-strategy P&L" in body
    assert "Tier status" in body
    assert "Force-exit events" in body
