"""Driver: run Volume Profile rejection + breakout + portfolio backtests.

Output JSON: backtest/volume_profile_results.json
            backtest/volume_profile_results_vix_off.json (no VIX filter)

Usage:
    python backtest/run_volume_profile_backtest.py
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
from backtest.volume_profile_backtest import (
    BacktestResult,
    CombinedResults,
    Trade,
    UNIVERSE,
    VPBreakoutConfig,
    VPRejectionConfig,
    _compute_session_vix_proxy,
    _enumerate_sessions,
    run_all_variants,
    run_portfolio,
    run_strategy,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("vp_runner")


def _daily_pnl_returns(trades: list[dict], starting_balance: float) -> pd.Series:
    if not trades:
        return pd.Series([], dtype=float)
    df = pd.DataFrame(trades)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"])
    df["exit_date"] = df["exit_ts"].dt.date
    daily_pnl = df.groupby("exit_date")["pnl"].sum()
    return daily_pnl / starting_balance


def summarize(result: BacktestResult) -> dict:
    trades = [t.to_dict() for t in result.trades]
    daily_returns = _daily_pnl_returns(trades, result.starting_balance)
    sharpe = (
        sharpe_ratio(daily_returns, periods_per_year=252)
        if not daily_returns.empty else float("nan")
    )
    if trades:
        cum_pnl = np.cumsum([t["pnl"] for t in sorted(trades, key=lambda x: x["exit_ts"])])
        eq_curve = pd.Series(result.starting_balance + cum_pnl)
        eq_curve = pd.concat([pd.Series([result.starting_balance]), eq_curve]).reset_index(drop=True)
    else:
        eq_curve = pd.Series([result.starting_balance])
    dd = max_drawdown(eq_curve)
    return {
        "n_trades": len(trades),
        "gross_pnl": float(sum(t["pnl"] for t in trades)),
        "win_rate": win_rate(trades),
        "profit_factor": profit_factor(trades),
        "avg_r_multiple": avg_r_multiple(trades),
        "sharpe": sharpe,
        "max_drawdown_pct": dd["max_drawdown_pct"],
        "max_drawdown_dollars": dd["max_drawdown_dollars"],
        "starting_balance": result.starting_balance,
        "final_equity": float(result.starting_balance + sum(t["pnl"] for t in trades)),
        "n_daily_returns": int(len(daily_returns)),
        "daily_returns_mean": (
            float(daily_returns.mean()) if not daily_returns.empty else float("nan")
        ),
        "daily_returns_std": (
            float(daily_returns.std()) if not daily_returns.empty else float("nan")
        ),
        "skipped_vix_pairs": result.skipped_vix,
        "n_session_symbol_pairs": result.n_session_symbol_pairs,
    }


def attribute_by_price_tier(trades: list[Trade]) -> dict:
    if not trades:
        return {}
    df = pd.DataFrame([t.to_dict() for t in trades])
    out: dict[str, dict] = {}
    for tier, sub in df.groupby("price_tier"):
        out[str(tier)] = {
            "n": int(len(sub)),
            "pnl": float(sub["pnl"].sum()),
            "win_rate": float((sub["pnl"] > 0).mean()),
            "avg_r": float(sub["r_multiple"].mean()),
        }
    return out


def attribute_by_year(trades: list[Trade]) -> dict:
    if not trades:
        return {}
    df = pd.DataFrame([t.to_dict() for t in trades])
    df["year"] = pd.to_datetime(df["session_date"]).dt.year
    out: dict[str, dict] = {}
    for y, sub in df.groupby("year"):
        out[str(int(y))] = {
            "n": int(len(sub)),
            "pnl": float(sub["pnl"].sum()),
            "win_rate": float((sub["pnl"] > 0).mean()),
            "avg_r": float(sub["r_multiple"].mean()),
        }
    return out


def attribute_by_level_kind(trades: list[Trade]) -> dict:
    if not trades:
        return {}
    df = pd.DataFrame([t.to_dict() for t in trades])
    out: dict[str, dict] = {}
    for k, sub in df.groupby("level_kind"):
        out[str(k)] = {
            "n": int(len(sub)),
            "pnl": float(sub["pnl"].sum()),
            "win_rate": float((sub["pnl"] > 0).mean()),
            "avg_r": float(sub["r_multiple"].mean()),
        }
    return out


def main(
    start_date: date = date(2020, 1, 2),
    end_date: date = date(2024, 12, 31),
    vix_threshold: float = 45.0,   # calibrated to ~25% of sessions on our
                                    # synthetic VIX proxy (median is ~34,
                                    # p75 is ~45). Wave 3 K-paper used real
                                    # VIX 25; our proxy is structurally
                                    # higher because it's realized vol of
                                    # a 5-stock high-beta basket.
) -> None:
    rej_cfg = VPRejectionConfig()
    bo_cfg = VPBreakoutConfig()

    sessions = _enumerate_sessions(start_date, end_date)
    log.info("Enumerating %d sessions in %s..%s", len(sessions), start_date, end_date)
    log.info("Computing VIX proxy (one-time)…")
    vix_series = _compute_session_vix_proxy(sessions)
    n_high = sum(1 for v in vix_series.values() if v >= vix_threshold)
    log.info("VIX proxy: %d / %d sessions exceed threshold %.1f", n_high, len(sessions), vix_threshold)

    out: dict = {
        "config": {
            "universe": list(UNIVERSE),
            "n_symbols": len(UNIVERSE),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "vix_threshold": vix_threshold,
            "rejection_cfg": {
                "lookback_sessions": rej_cfg.lookback_sessions,
                "bin_pct": rej_cfg.bin_pct,
                "hvn_multiplier": rej_cfg.hvn_multiplier,
                "proximity_pct": rej_cfg.proximity_pct,
                "stop_pad_dollar": rej_cfg.stop_pad_dollar,
                "risk_dollars": rej_cfg.risk_dollars,
                "starting_balance": rej_cfg.starting_balance,
            },
            "breakout_cfg": {
                "lookback_sessions": bo_cfg.lookback_sessions,
                "bin_pct": bo_cfg.bin_pct,
                "lvn_multiplier": bo_cfg.lvn_multiplier,
                "proximity_pct": bo_cfg.proximity_pct,
                "min_vol_mult": bo_cfg.min_vol_mult,
                "stop_pad_dollar": bo_cfg.stop_pad_dollar,
                "target_r": bo_cfg.target_r,
                "risk_dollars": bo_cfg.risk_dollars,
                "starting_balance": bo_cfg.starting_balance,
            },
        },
    }

    log.info("Running combined sweep (all 6 variants in one pass) …")
    combined = run_all_variants(
        rej_cfg, bo_cfg,
        start_date=start_date, end_date=end_date,
        vix_suppress_threshold=vix_threshold,
        vix_series=vix_series,
    )
    rej_off = combined.rej_off
    bo_off = combined.bo_off
    port_off = combined.port_off
    rej_on = combined.rej_on
    bo_on = combined.bo_on
    port_on = combined.port_on
    log.info(
        "Done. VIX-OFF: rej=%d bo=%d port=%d | VIX-ON: rej=%d bo=%d port=%d",
        len(rej_off.trades), len(bo_off.trades), len(port_off.trades),
        len(rej_on.trades), len(bo_on.trades), len(port_on.trades),
    )

    # Summaries
    for label, result in [
        ("rejection_vix_on", rej_on),
        ("breakout_vix_on", bo_on),
        ("portfolio_vix_on", port_on),
        ("rejection_vix_off", rej_off),
        ("breakout_vix_off", bo_off),
        ("portfolio_vix_off", port_off),
    ]:
        s = summarize(result)
        s["tier_attribution"] = attribute_by_price_tier(result.trades)
        s["year_attribution"] = attribute_by_year(result.trades)
        s["level_kind_attribution"] = attribute_by_level_kind(result.trades)
        out[label] = s

    out_path = Path("/Users/duffy/warrior_bot_v2/backtest/volume_profile_results.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("Wrote %s", out_path)

    # Also dump trade-level CSVs for each leg
    for label, result in [
        ("rejection_vix_on", rej_on),
        ("breakout_vix_on", bo_on),
        ("portfolio_vix_on", port_on),
        ("rejection_vix_off", rej_off),
        ("breakout_vix_off", bo_off),
        ("portfolio_vix_off", port_off),
    ]:
        if result.trades:
            df = pd.DataFrame([t.to_dict() for t in result.trades])
            csv_path = out_path.parent / f"volume_profile_{label}_trades.csv"
            df.to_csv(csv_path, index=False)
            log.info("Wrote %s (%d trades)", csv_path, len(df))


if __name__ == "__main__":
    main()
