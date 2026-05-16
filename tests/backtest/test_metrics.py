"""Unit tests for backtest.metrics."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

import sys, os
sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from backtest.metrics import (
    sharpe_ratio,
    max_drawdown,
    profit_factor,
    win_rate,
    avg_r_multiple,
    hold_time_distribution,
    summarize,
)


def test_sharpe_basic_positive():
    # Linear up-trending returns => positive Sharpe
    rs = pd.Series([0.001] * 252)
    s = sharpe_ratio(rs, periods_per_year=252)
    # All identical positive returns => std == 0 => NaN
    assert math.isnan(s)


def test_sharpe_with_volatility():
    np.random.seed(42)
    # mean 0.0005, std 0.01 => annualized Sharpe ~ 0.0005/0.01 * sqrt(252) ~ 0.79
    rs = np.random.normal(loc=0.0005, scale=0.01, size=252)
    s = sharpe_ratio(rs, periods_per_year=252)
    assert 0.3 < s < 1.5, f"expected ~0.79, got {s}"


def test_sharpe_empty_returns_nan():
    assert math.isnan(sharpe_ratio([]))
    assert math.isnan(sharpe_ratio([1.0]))


def test_max_drawdown_basic():
    eq = pd.Series([100, 110, 105, 90, 95, 100])
    dd = max_drawdown(eq)
    # peak at 110 (idx 1) -> trough at 90 (idx 3): drawdown = (90-110)/110 = -0.1818
    assert dd["max_drawdown_pct"] == pytest.approx(-0.1818, rel=1e-3)
    assert dd["max_drawdown_dollars"] == pytest.approx(-20, rel=1e-3)


def test_max_drawdown_monotone_increasing_is_zero():
    eq = pd.Series([100, 110, 120, 130])
    dd = max_drawdown(eq)
    assert dd["max_drawdown_pct"] == pytest.approx(0.0)


def test_profit_factor():
    trades = [
        {"pnl": 100},
        {"pnl": -50},
        {"pnl": 200},
        {"pnl": -100},
    ]
    # gross_wins = 300, gross_losses = 150
    assert profit_factor(trades) == pytest.approx(2.0)


def test_profit_factor_no_losses():
    trades = [{"pnl": 100}, {"pnl": 50}]
    assert profit_factor(trades) == float("inf")


def test_profit_factor_empty():
    assert math.isnan(profit_factor([]))


def test_win_rate():
    trades = [
        {"pnl": 100}, {"pnl": -50}, {"pnl": 200}, {"pnl": -100},
    ]
    assert win_rate(trades) == 0.5


def test_avg_r_multiple():
    trades = [
        {"pnl": 100, "r_multiple": 2.0},
        {"pnl": -50, "r_multiple": -1.0},
        {"pnl": 200, "r_multiple": 3.0},
    ]
    assert avg_r_multiple(trades) == pytest.approx((2.0 + -1.0 + 3.0) / 3.0)


def test_avg_r_multiple_no_r_returns_nan():
    trades = [{"pnl": 100, "r_multiple": None}]
    assert math.isnan(avg_r_multiple(trades))


def test_hold_time_distribution():
    t0 = pd.Timestamp("2024-01-02 09:30:00")
    trades = [
        {"entry_ts": t0, "exit_ts": t0 + pd.Timedelta(minutes=10)},
        {"entry_ts": t0, "exit_ts": t0 + pd.Timedelta(minutes=20)},
        {"entry_ts": t0, "exit_ts": t0 + pd.Timedelta(minutes=30)},
    ]
    h = hold_time_distribution(trades)
    assert h["p50"] == pytest.approx(20 * 60)  # 20 minutes in seconds


def test_summarize_round_trip():
    t0 = pd.Timestamp("2024-01-02 09:30:00")
    trades = [
        {"pnl": 100, "r_multiple": 2.0, "entry_ts": t0, "exit_ts": t0 + pd.Timedelta(minutes=10)},
        {"pnl": -50, "r_multiple": -1.0, "entry_ts": t0, "exit_ts": t0 + pd.Timedelta(minutes=15)},
    ]
    eq = pd.Series([100_000, 100_100, 100_050, 100_150])
    m = summarize(trades, equity_curve=eq, periods_per_year=252)
    assert m.n_trades == 2
    assert m.gross_pnl == 50.0
    assert m.win_rate == 0.5
    assert m.profit_factor == 2.0
    assert m.avg_r_multiple == pytest.approx(0.5)
    assert m.max_drawdown_pct < 0
    d = m.to_dict()
    assert set(d.keys()) >= {"n_trades", "gross_pnl", "win_rate", "sharpe"}
