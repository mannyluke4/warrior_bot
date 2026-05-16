"""Unit tests for backtest.vectorbt_runner."""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from backtest.vectorbt_runner import run_signal_backtest, sweep


def test_buy_and_hold_matches_theoretical_pnl():
    """Buy at bar 0, hold to bar N-1.

    Theoretical: starting at $100, ending at $110, with default vectorbt
    sizing (100% of cash on first signal) the % return should be ~10%.
    """
    np.random.seed(0)
    close = pd.Series(
        np.linspace(100, 110, 252),
        index=pd.date_range("2024-01-02", periods=252, freq="1D"),
    )
    entries = pd.Series(False, index=close.index)
    entries.iloc[0] = True
    exits = pd.Series(False, index=close.index)
    exits.iloc[-1] = True

    m = run_signal_backtest(close, entries, exits, init_cash=100_000, freq="1D")
    # The vectorbt P&L should be ~10% of init_cash with full-cash sizing.
    # Allow ±1% wiggle for partial-share rounding.
    pct = m.net_pnl / 100_000.0
    assert 0.09 < pct < 0.11, f"buy-and-hold pct return {pct:.4f} not ~10%"


def test_sweep_returns_dataframe():
    np.random.seed(1)
    close = pd.Series(
        np.linspace(100, 110, 100),
        index=pd.date_range("2024-01-02", periods=100, freq="1D"),
    )

    def simple_ma_signal(c: pd.Series, window: int = 5):
        ma = c.rolling(window).mean()
        entries = (c > ma) & (c.shift(1) <= ma.shift(1))
        exits = (c < ma) & (c.shift(1) >= ma.shift(1))
        return entries.fillna(False), exits.fillna(False)

    df = sweep(close, simple_ma_signal, param_grid={"window": [3, 5, 10]}, freq="1D")
    assert len(df) == 3
    assert set(["window", "n_trades", "net_pnl", "sharpe"]).issubset(df.columns)
