"""Driver: run PDH/PDL fade + breakout + portfolio backtests + emit metrics.

Output JSON:
    backtest/pdh_pdl_results.json — full results bundle for the report.

Usage:
    python backtest/run_pdh_pdl_backtest.py
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from backtest.metrics import (
    avg_r_multiple,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    win_rate,
)
from backtest.pdh_pdl_backtest import (
    BacktestResult,
    PDHBreakoutConfig,
    PDHFadeConfig,
    Trade,
    run_portfolio,
    run_strategy,
)
from backtest.synthetic_universe import UniverseConfig, generate_universe


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pdh_pdl_runner")


def _daily_pnl_returns(
    trades: list, starting_balance: float
) -> pd.Series:
    """Aggregate trades to daily P&L, normalize by starting balance.

    With fixed-risk sizing, this gives a stable daily return distribution
    (no compounding inflation). Sharpe computed on this series is the
    headline metric — it reflects strategy edge per unit of dispersion,
    not exponential blow-up.
    """
    if not trades:
        return pd.Series([], dtype=float)
    df = pd.DataFrame(trades)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"])
    df["exit_date"] = df["exit_ts"].dt.date
    daily_pnl = df.groupby("exit_date")["pnl"].sum()
    return daily_pnl / starting_balance


def summarize(result: BacktestResult, starting_balance: float) -> dict:
    trades = [t.to_dict() for t in result.trades]
    daily_returns = _daily_pnl_returns(trades, starting_balance)
    sharpe = (
        sharpe_ratio(daily_returns, periods_per_year=252)
        if not daily_returns.empty else float("nan")
    )

    # Drawdown — compute on the fixed-risk equity curve (starting + cum daily P&L).
    if trades:
        eq_with_start = pd.Series(
            [starting_balance + v for v in daily_returns.cumsum() * starting_balance]
        )
        eq_with_start = pd.concat([pd.Series([starting_balance]), eq_with_start]).reset_index(drop=True)
    else:
        eq_with_start = pd.Series([starting_balance])
    dd = max_drawdown(eq_with_start)
    return {
        "n_trades": len(trades),
        "gross_pnl": float(sum(t["pnl"] for t in trades)),
        "win_rate": win_rate(trades),
        "profit_factor": profit_factor(trades),
        "avg_r_multiple": avg_r_multiple(trades),
        "sharpe": sharpe,
        "max_drawdown_pct": dd["max_drawdown_pct"],
        "max_drawdown_dollars": dd["max_drawdown_dollars"],
        "starting_balance": starting_balance,
        "final_equity": float(starting_balance + sum(t["pnl"] for t in trades)),
        "n_daily_returns": int(len(daily_returns)),
        "daily_returns_mean": (
            float(daily_returns.mean()) if not daily_returns.empty else float("nan")
        ),
        "daily_returns_std": (
            float(daily_returns.std()) if not daily_returns.empty else float("nan")
        ),
    }


def attribute_by_price_tier(trades: list[Trade]) -> dict:
    tiers: dict[str, dict] = {}
    df = pd.DataFrame([t.to_dict() for t in trades])
    if df.empty:
        return tiers
    for tier, sub in df.groupby("price_tier"):
        tiers[str(tier)] = {
            "n": int(len(sub)),
            "pnl": float(sub["pnl"].sum()),
            "win_rate": float((sub["pnl"] > 0).mean()),
            "avg_r": float(sub["r_multiple"].mean()),
        }
    return tiers


def attribute_by_level(trades: list[Trade]) -> dict:
    """PDH-fade vs PDL-fade vs PDH-break vs PDL-break."""
    by_key: dict[str, dict] = {}
    df = pd.DataFrame([t.to_dict() for t in trades])
    if df.empty:
        return by_key
    df["key"] = df["strategy"] + "/" + df["level_kind"]
    for k, sub in df.groupby("key"):
        by_key[str(k)] = {
            "n": int(len(sub)),
            "pnl": float(sub["pnl"].sum()),
            "win_rate": float((sub["pnl"] > 0).mean()),
            "avg_r": float(sub["r_multiple"].mean()),
        }
    return by_key


def main() -> None:
    cfg = UniverseConfig(
        n_symbols=50,
        start_date=date(2020, 1, 2),
        end_date=date(2024, 12, 31),
        min_price=10.0,
        max_price=300.0,
        base_seed=42,
    )
    log.info(
        "Generating synthetic universe: %d symbols × ~%d trading days",
        cfg.n_symbols,
        252 * (cfg.end_date.year - cfg.start_date.year + 1),
    )
    universe = generate_universe(cfg)
    log.info("Universe generated: %d (symbol, day) cells", len(universe))

    fade_cfg = PDHFadeConfig()
    break_cfg = PDHBreakoutConfig()

    # --- Standalone fade ---
    log.info("Running PDH-PDL-Fade …")
    fade_result = run_strategy("fade", universe, fade_cfg)
    fade_summary = summarize(fade_result, fade_cfg.starting_balance)
    log.info(
        "Fade: %d trades, Sharpe %.2f, PF %.2f, win %.0f%%, MDD %.1f%%",
        fade_summary["n_trades"],
        fade_summary["sharpe"],
        fade_summary["profit_factor"],
        fade_summary["win_rate"] * 100,
        fade_summary["max_drawdown_pct"] * 100,
    )

    # --- Standalone breakout ---
    log.info("Running PDH-PDL-Breakout …")
    break_result = run_strategy("breakout", universe, break_cfg)
    break_summary = summarize(break_result, break_cfg.starting_balance)
    log.info(
        "Breakout: %d trades, Sharpe %.2f, PF %.2f, win %.0f%%, MDD %.1f%%",
        break_summary["n_trades"],
        break_summary["sharpe"],
        break_summary["profit_factor"],
        break_summary["win_rate"] * 100,
        break_summary["max_drawdown_pct"] * 100,
    )

    # --- Portfolio (conflict-resolved combo) ---
    log.info("Running combined portfolio (conflict-resolved) …")
    portfolio_result = run_portfolio(universe, fade_cfg, break_cfg)
    # Portfolio runs on shared capital (avg of the two starting balances)
    port_starting_balance = (fade_cfg.starting_balance + break_cfg.starting_balance) / 2
    port_summary = summarize(portfolio_result, port_starting_balance)
    log.info(
        "Portfolio: %d trades, Sharpe %.2f, PF %.2f, win %.0f%%, MDD %.1f%%",
        port_summary["n_trades"],
        port_summary["sharpe"],
        port_summary["profit_factor"],
        port_summary["win_rate"] * 100,
        port_summary["max_drawdown_pct"] * 100,
    )

    # --- Conflict counts (informational) ---
    # How often would both have signalled if we didn't lock?
    fade_keys = {(t.symbol, t.session_date) for t in fade_result.trades}
    break_keys = {(t.symbol, t.session_date) for t in break_result.trades}
    overlap_keys = fade_keys & break_keys
    conflict_summary = {
        "fade_total_sessions_traded": len(fade_keys),
        "breakout_total_sessions_traded": len(break_keys),
        "overlap_sessions": len(overlap_keys),
        "overlap_fraction_of_fade": (
            len(overlap_keys) / max(1, len(fade_keys))
        ),
        "overlap_fraction_of_breakout": (
            len(overlap_keys) / max(1, len(break_keys))
        ),
        # In the portfolio with first-in-time wins, how many came from each?
        "portfolio_fade_count": sum(1 for t in portfolio_result.trades if t.strategy == "fade"),
        "portfolio_breakout_count": sum(1 for t in portfolio_result.trades if t.strategy == "breakout"),
    }

    out = {
        "config": {
            "universe": {
                "n_symbols": cfg.n_symbols,
                "start_date": cfg.start_date.isoformat(),
                "end_date": cfg.end_date.isoformat(),
                "min_price": cfg.min_price,
                "max_price": cfg.max_price,
                "level_reaction_prob": cfg.level_reaction_prob,
                "level_breakout_prob": cfg.level_breakout_prob,
                "base_seed": cfg.base_seed,
            },
            "fade_cfg": {
                "proximity_pct": fade_cfg.proximity_pct,
                "rejection_lookback": fade_cfg.rejection_lookback,
                "stop_pad_dollar": fade_cfg.stop_pad_dollar,
                "fallback_r_multiple": fade_cfg.fallback_r_multiple,
                "risk_per_trade_pct": fade_cfg.risk_per_trade_pct,
                "starting_balance": fade_cfg.starting_balance,
            },
            "breakout_cfg": {
                "proximity_pct": break_cfg.proximity_pct,
                "min_vol_mult": break_cfg.min_vol_mult,
                "min_breakout_pct": break_cfg.min_breakout_pct,
                "bar_low_lookback": break_cfg.bar_low_lookback,
                "stop_pad_dollar": break_cfg.stop_pad_dollar,
                "target_r": break_cfg.target_r,
                "trailing_activate_at_r": break_cfg.trailing_activate_at_r,
                "trailing_atr_mult": break_cfg.trailing_atr_mult,
                "risk_per_trade_pct": break_cfg.risk_per_trade_pct,
                "starting_balance": break_cfg.starting_balance,
            },
        },
        "fade": fade_summary,
        "breakout": break_summary,
        "portfolio": port_summary,
        "conflict_summary": conflict_summary,
        "tier_attribution": {
            "fade": attribute_by_price_tier(fade_result.trades),
            "breakout": attribute_by_price_tier(break_result.trades),
            "portfolio": attribute_by_price_tier(portfolio_result.trades),
        },
        "level_attribution": {
            "fade": attribute_by_level(fade_result.trades),
            "breakout": attribute_by_level(break_result.trades),
            "portfolio": attribute_by_level(portfolio_result.trades),
        },
    }

    out_path = Path("/Users/duffy/warrior_bot_v2/backtest/pdh_pdl_results.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("Wrote %s", out_path)

    # Also write trade-level CSVs for downstream analysis
    for label, res in [("fade", fade_result), ("breakout", break_result),
                       ("portfolio", portfolio_result)]:
        if res.trades:
            df = pd.DataFrame([t.to_dict() for t in res.trades])
            csv_path = out_path.parent / f"pdh_pdl_{label}_trades.csv"
            df.to_csv(csv_path, index=False)
            log.info("Wrote %s (%d trades)", csv_path, len(df))


if __name__ == "__main__":
    main()
