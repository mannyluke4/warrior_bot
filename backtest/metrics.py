"""
backtest.metrics
================

Shared performance-metrics calculation for the Healthy Fluctuation Framework
backtest harness.

All numbers are computed from a list of ``Trade`` dictionaries (defined below
for documentation purposes — any dict-like with the same keys works) plus an
optional equity curve (a pandas ``Series`` of mark-to-market equity).

Trade record schema
-------------------
Each trade record is expected to be a dict with at least::

    {
        "symbol":       "AAPL",
        "side":         "long" | "short",
        "entry_ts":     pd.Timestamp,
        "exit_ts":      pd.Timestamp,
        "entry_price":  float,
        "exit_price":   float,
        "qty":          int,
        "pnl":          float,           # signed dollar P&L (net of commissions if applicable)
        "r_multiple":   float | None,    # signed R-multiple if known
    }

Functions
---------
* ``sharpe_ratio(returns, periods_per_year=252)``
* ``max_drawdown(equity_curve)``
* ``profit_factor(trades)``
* ``win_rate(trades)``
* ``avg_r_multiple(trades)``
* ``hold_time_distribution(trades)``
* ``summarize(trades, equity_curve)`` -> dict with all of the above

These functions are deliberately decoupled from NautilusTrader / vectorbt so
they can be re-used regardless of the engine that produced the trade log.

Author: Agent A (Wave 1 — Healthy Fluctuation Framework)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


__all__ = [
    "sharpe_ratio",
    "max_drawdown",
    "profit_factor",
    "win_rate",
    "avg_r_multiple",
    "hold_time_distribution",
    "summarize",
    "MetricsResult",
]


# ---------------------------------------------------------------------------
# Core primitives
# ---------------------------------------------------------------------------


def sharpe_ratio(
    returns: Sequence[float] | pd.Series,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
) -> float:
    """Annualized Sharpe ratio.

    Parameters
    ----------
    returns : sequence of per-period returns (NOT prices). Period is whatever
        the caller's resampling step is; ``periods_per_year`` converts.
    periods_per_year : 252 for daily, 252*6.5*60 for 1-minute equity, etc.
    risk_free_rate : annualized risk-free rate. Default 0 — strategies are
        evaluated on raw alpha.

    Returns
    -------
    float : NaN if std=0 or no data.
    """
    r = pd.Series(returns).dropna()
    if len(r) < 2:
        return float("nan")
    excess = r - (risk_free_rate / periods_per_year)
    std = excess.std(ddof=1)
    # Floating-point std of constant series can be ~1e-19 instead of exactly 0,
    # which yields an infinite Sharpe. Treat anything below 1e-12 as zero.
    if std < 1e-12 or math.isnan(std):
        return float("nan")
    return float(excess.mean() / std * math.sqrt(periods_per_year))


def max_drawdown(equity_curve: Sequence[float] | pd.Series) -> dict:
    """Peak-to-trough maximum drawdown.

    Returns a dict::

        {
            "max_drawdown_pct": float,          # negative number, e.g. -0.12 = -12%
            "max_drawdown_dollars": float,      # absolute dollars
            "peak_idx": int,                     # index of peak before trough
            "trough_idx": int,                   # index of trough
        }
    """
    eq = pd.Series(equity_curve).dropna()
    if len(eq) < 2:
        return {
            "max_drawdown_pct": 0.0,
            "max_drawdown_dollars": 0.0,
            "peak_idx": 0,
            "trough_idx": 0,
        }
    # Reindex to a clean positional integer index so idxmin/idxmax return ints
    # regardless of the caller's original index type.
    eq = eq.reset_index(drop=True)
    running_max = eq.cummax()
    drawdown = (eq - running_max) / running_max
    trough_idx = int(drawdown.idxmin()) if drawdown.size else 0
    # Find peak before trough
    peak_idx = int(running_max.loc[:trough_idx].idxmax()) if trough_idx >= 0 else 0
    return {
        "max_drawdown_pct": float(drawdown.min()),
        "max_drawdown_dollars": float(eq.iloc[trough_idx] - running_max.iloc[trough_idx]),
        "peak_idx": peak_idx,
        "trough_idx": trough_idx,
    }


def profit_factor(trades: Iterable[Mapping]) -> float:
    """Gross wins / |gross losses|. Returns inf if no losses, NaN if no trades."""
    gross_wins = 0.0
    gross_losses = 0.0
    n = 0
    for t in trades:
        pnl = float(t.get("pnl", 0.0))
        if pnl > 0:
            gross_wins += pnl
        elif pnl < 0:
            gross_losses += pnl
        n += 1
    if n == 0:
        return float("nan")
    if gross_losses == 0:
        return float("inf") if gross_wins > 0 else float("nan")
    return float(gross_wins / abs(gross_losses))


def win_rate(trades: Iterable[Mapping]) -> float:
    """Fraction of trades with strictly positive P&L. NaN if no trades."""
    trades = list(trades)
    if not trades:
        return float("nan")
    wins = sum(1 for t in trades if float(t.get("pnl", 0.0)) > 0)
    return wins / len(trades)


def avg_r_multiple(trades: Iterable[Mapping]) -> float:
    """Average R-multiple across trades that report one. NaN if none."""
    rs = [float(t["r_multiple"]) for t in trades if t.get("r_multiple") is not None]
    return float(np.mean(rs)) if rs else float("nan")


def hold_time_distribution(trades: Iterable[Mapping]) -> dict:
    """Return p25/p50/p75 of hold time in seconds plus the raw distribution."""
    holds = []
    for t in trades:
        entry = t.get("entry_ts")
        exitt = t.get("exit_ts")
        if entry is None or exitt is None:
            continue
        delta = pd.Timestamp(exitt) - pd.Timestamp(entry)
        holds.append(delta.total_seconds())
    if not holds:
        return {"p25": float("nan"), "p50": float("nan"), "p75": float("nan"),
                "min": float("nan"), "max": float("nan"), "samples": holds}
    arr = np.array(holds)
    return {
        "p25": float(np.percentile(arr, 25)),
        "p50": float(np.percentile(arr, 50)),
        "p75": float(np.percentile(arr, 75)),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "samples": holds,
    }


# ---------------------------------------------------------------------------
# Summary object
# ---------------------------------------------------------------------------


@dataclass
class MetricsResult:
    """Standardized result object returned by both NautilusRunner and VectorbtRunner."""

    n_trades: int
    gross_pnl: float
    net_pnl: float
    win_rate: float
    profit_factor: float
    avg_r_multiple: float
    sharpe: float
    max_drawdown_pct: float
    max_drawdown_dollars: float
    hold_time_p50_sec: float

    # Raw artifacts (optional, omitted from JSON serialization)
    trades: list | None = None
    equity_curve: pd.Series | None = None

    def to_dict(self) -> dict:
        return {
            "n_trades": self.n_trades,
            "gross_pnl": self.gross_pnl,
            "net_pnl": self.net_pnl,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "avg_r_multiple": self.avg_r_multiple,
            "sharpe": self.sharpe,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_dollars": self.max_drawdown_dollars,
            "hold_time_p50_sec": self.hold_time_p50_sec,
        }

    def __str__(self) -> str:
        d = self.to_dict()
        lines = [f"  {k:>22s}: {v}" for k, v in d.items()]
        return "MetricsResult(\n" + "\n".join(lines) + "\n)"


def summarize(
    trades: Sequence[Mapping],
    equity_curve: pd.Series | None = None,
    daily_returns: pd.Series | None = None,
    periods_per_year: int = 252,
) -> MetricsResult:
    """Compute the full metrics suite. ``daily_returns`` overrides Sharpe input
    if both equity_curve and daily_returns are supplied; otherwise daily returns
    are derived from equity_curve.

    Both ``equity_curve`` and ``daily_returns`` are optional — if neither is
    supplied, Sharpe / drawdown will be NaN / 0 respectively.
    """
    trades_list = list(trades)
    gross_pnl = sum(float(t.get("pnl", 0.0)) for t in trades_list)
    # For now, gross == net; commissions are baked into pnl by NautilusTrader
    # at the engine level when fee_model is configured.
    net_pnl = gross_pnl

    if daily_returns is None and equity_curve is not None:
        daily_returns = pd.Series(equity_curve).pct_change().dropna()
    sharpe = sharpe_ratio(daily_returns, periods_per_year) if daily_returns is not None else float("nan")
    dd = max_drawdown(equity_curve) if equity_curve is not None else {
        "max_drawdown_pct": 0.0, "max_drawdown_dollars": 0.0,
    }
    hold = hold_time_distribution(trades_list)
    return MetricsResult(
        n_trades=len(trades_list),
        gross_pnl=float(gross_pnl),
        net_pnl=float(net_pnl),
        win_rate=win_rate(trades_list),
        profit_factor=profit_factor(trades_list),
        avg_r_multiple=avg_r_multiple(trades_list),
        sharpe=sharpe,
        max_drawdown_pct=dd["max_drawdown_pct"],
        max_drawdown_dollars=dd["max_drawdown_dollars"],
        hold_time_p50_sec=hold["p50"],
        trades=trades_list,
        equity_curve=equity_curve,
    )
