"""
backtest.vectorbt_runner
========================

Lightweight vectorbt-based backtest runner for parameter sweeps.

Where NautilusTrader gives event-accurate tick-by-tick simulation,
vectorbt gives vectorized "try N parameter combos against the same OHLCV
in seconds." That trades off fill-modeling fidelity for raw throughput.

Use this runner for:

* Initial parameter screening (sweep 20-100 combos, take top-K to nautilus)
* Quick sanity checks ("does this signal even make money on AAPL?")
* Long-horizon Sharpe estimation on bar data

Do NOT use this runner for the final acceptance gate — those backtests must
go through ``nautilus_runner`` so fill modeling matches live behavior.

Public surface
--------------
``run_signal_backtest(close, entries, exits, ...)`` runs a single config.
``sweep(close, entries_fn, exits_fn, param_grid, ...)`` runs the same
strategy across a parameter grid and returns a DataFrame of metrics.

Author: Agent A (Wave 1 — Healthy Fluctuation Framework)
"""

from __future__ import annotations

import logging
from itertools import product
from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd
import vectorbt as vbt

from backtest.metrics import MetricsResult, summarize


__all__ = ["run_signal_backtest", "sweep", "vbt_to_metrics"]


log = logging.getLogger(__name__)


def vbt_to_metrics(pf: vbt.Portfolio, periods_per_year: int = 252) -> MetricsResult:
    """Convert a vectorbt ``Portfolio`` into our standardized ``MetricsResult``."""
    trades = []
    try:
        trades_df = pf.trades.records_readable
        if not trades_df.empty:
            for _, t in trades_df.iterrows():
                trades.append({
                    "symbol": str(t.get("Column", "")),
                    "side": "long" if str(t.get("Direction", "Long")).lower() == "long" else "short",
                    "entry_ts": pd.Timestamp(t.get("Entry Index") or t.get("Entry Timestamp") or pd.NaT),
                    "exit_ts":  pd.Timestamp(t.get("Exit Index")  or t.get("Exit Timestamp")  or pd.NaT),
                    "entry_price": float(t.get("Avg Entry Price", 0.0) or 0.0),
                    "exit_price":  float(t.get("Avg Exit Price",  0.0) or 0.0),
                    "qty": int(float(t.get("Size", 0) or 0)),
                    "pnl": float(t.get("PnL", 0.0) or 0.0),
                    "r_multiple": None,
                })
    except Exception as exc:
        log.warning("[vectorbt_runner] could not extract trades: %s", exc)

    equity_curve = None
    try:
        equity_curve = pf.value()
    except Exception:
        pass

    return summarize(trades=trades, equity_curve=equity_curve, periods_per_year=periods_per_year)


def run_signal_backtest(
    close: pd.Series | pd.DataFrame,
    entries: pd.Series | pd.DataFrame,
    exits: pd.Series | pd.DataFrame,
    init_cash: float = 100_000.0,
    fees: float = 0.0,
    slippage: float = 0.0,
    size: float | None = None,
    freq: str = "1D",
    periods_per_year: int = 252,
) -> MetricsResult:
    """Run a single backtest from boolean entry/exit signals.

    Parameters
    ----------
    close : OHLCV close series (or DataFrame for multi-asset)
    entries, exits : boolean signals aligned to ``close``
    init_cash : starting capital
    fees : per-trade fee rate (e.g. 0.0001 = 1bp)
    slippage : per-trade slippage rate
    size : number of shares per entry; if None, vectorbt uses full cash
    freq : pandas-style freq string for Sharpe annualization
    periods_per_year : 252 for daily, 252*6.5*60 for 1-minute equity, etc.
    """
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        init_cash=init_cash,
        fees=fees,
        slippage=slippage,
        size=size,
        freq=freq,
    )
    return vbt_to_metrics(pf, periods_per_year=periods_per_year)


def sweep(
    close: pd.Series,
    signal_fn: Callable[..., tuple[pd.Series, pd.Series]],
    param_grid: Mapping[str, Sequence],
    init_cash: float = 100_000.0,
    fees: float = 0.0,
    slippage: float = 0.0,
    freq: str = "1D",
    periods_per_year: int = 252,
) -> pd.DataFrame:
    """Parameter sweep over ``signal_fn(close, **params) -> (entries, exits)``.

    Returns a DataFrame indexed by parameter combo with columns mirroring
    ``MetricsResult.to_dict()``.
    """
    keys = list(param_grid.keys())
    rows = []
    for combo in product(*[param_grid[k] for k in keys]):
        params = dict(zip(keys, combo))
        entries, exits = signal_fn(close, **params)
        m = run_signal_backtest(
            close, entries, exits,
            init_cash=init_cash, fees=fees, slippage=slippage,
            freq=freq, periods_per_year=periods_per_year,
        )
        rows.append({**params, **m.to_dict()})
    return pd.DataFrame(rows)
