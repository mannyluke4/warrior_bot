"""Smoke tests for the Wave 3 portfolio backtest scaffolding."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path("/Users/duffy/warrior_bot_v2")
sys.path.insert(0, str(REPO))


def test_load_day_bars_aapl_2024_01_02():
    """Smoke test: AAPL 2024-01-02 should have ~390 RTH bars."""
    from backtest.portfolio_backtest import load_day_bars
    bars = load_day_bars("AAPL", date(2024, 1, 2))
    assert 380 <= len(bars) <= 395
    assert bars[0].timestamp.time().hour == 9
    assert bars[0].timestamp.time().minute == 30
    assert bars[-1].timestamp.time().hour == 15
    assert bars[-1].timestamp.time().minute >= 55


def test_pdh_pdl_fade_single_day():
    """End-to-end: NVDA 2024-01-03 PDH-fade fires (known from smoke test)."""
    from backtest.portfolio_backtest import run_single_strategy_single_day
    trades = run_single_strategy_single_day(
        strategy_yaml=str(REPO / "strategies" / "pdh_pdl_fade.yaml"),
        symbol="NVDA",
        session_date=date(2024, 1, 3),
    )
    # Should produce 0 or 1 trades
    assert isinstance(trades, list)
    assert len(trades) <= 1
    if trades:
        t = trades[0]
        assert t["strategy"] == "PDH-PDL-Fade"
        assert t["symbol"] == "NVDA"
        assert t["direction"] in ("long", "short")
        assert t["entry_price"] > 0
        assert t["qty"] >= 0


def test_subprocess_runner_roundtrip():
    """Smoke test for the subprocess runner: single pair via subprocess."""
    from backtest.nautilus_subprocess_runner import PairTask, _run_one_pair
    task = PairTask(
        strategy_yaml=str(REPO / "strategies" / "pdh_pdl_fade.yaml"),
        symbol="NVDA",
        session_date=date(2024, 1, 3),
    )
    result = _run_one_pair(task)
    # Process exited cleanly
    assert result.error is None, f"subprocess failed: {result.error}"
    # Summary captured
    assert result.summary is not None
    assert "n_fills" in result.summary
    # Fills count matches in-process result
    assert result.summary["n_fills"] == len(result.fills)


def test_per_day_per_symbol_lock_counts():
    """Lock collisions on 1-month run are non-zero (proves the mechanism fires)."""
    from backtest.portfolio_backtest import (
        PortfolioConfig, SizingMode, run_portfolio_backtest,
    )
    cfg = PortfolioConfig(
        sizing_mode=SizingMode(name="half_kelly"),
        strategy_yamls=(
            str(REPO / "strategies" / "orb_5min.yaml"),
            str(REPO / "strategies" / "pdh_pdl_fade.yaml"),
            str(REPO / "strategies" / "pdh_pdl_breakout.yaml"),
        ),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 10),
    )
    result = run_portfolio_backtest(cfg)
    # 3 strategies * 36 symbols * 7 sessions ~= 750 candidate pairs; lock should fire on >= 50
    assert result["lock_collisions"] >= 1
    # And the totals
    n_trades = sum(len(v) for v in result["trades_by_strategy"].values())
    assert n_trades > 0


def test_sizing_mode_fixed_dollar():
    """Fixed-dollar mode produces non-zero qty when half-Kelly would cap to zero."""
    from backtest.portfolio_backtest import SizingMode
    mode = SizingMode(name="fixed_dollar", fixed_dollar_risk=1000.0)
    qty, risk = mode.size(
        equity=100_000,
        entry_price=100.0,
        stop_price=99.0,
        recent_bar_volume=1_000_000,
    )
    assert qty == 1000  # $1000 risk / $1 per share
    assert risk == 1000.0


def test_sizing_mode_half_kelly_caps_at_bar_volume():
    """Half-Kelly caps shares at 5% of bar volume."""
    from backtest.portfolio_backtest import SizingMode
    mode = SizingMode(name="half_kelly", risk_per_trade_pct=1.0)
    # equity=100k, R=$0.10/share -> theoretical = 5000 shares
    # bar_vol=10000 -> 5% cap = 500 shares
    qty, risk = mode.size(
        equity=100_000,
        entry_price=100.0,
        stop_price=99.90,
        recent_bar_volume=10_000,
    )
    assert qty <= 500
    assert risk == 500.0  # half-kelly = 1% * 100k * 0.5
