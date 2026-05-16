"""End-to-end ORB backtest runner with sensitivity + tier attribution.

Reads pre-fetched 1m bars from `tick_cache_databento/<sym>/1m_<date>.parquet`,
runs the ORB strategy across the universe + date range, and dumps:

* `backtest_archive/orb_<run>_trades.parquet`  — every trade
* `backtest_archive/orb_<run>_summary.json`    — metrics + breakdowns
* Prints a console summary

Sensitivity: pass `--minutes 5 15 30` to run multiple OR widths.
Walk-forward: trades are timestamped — quarterly distribution is in the summary.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from backtest.orb_backtest import (
    ORBBacktestResult,
    ORBConfig,
    Trade,
    price_tier,
    run_orb_backtest,
)
from backtest.orb_data_fetcher import ORB_UNIVERSE
from framework.level_sources.base import Bar


_TICK_CACHE = Path("/Users/duffy/warrior_bot_v2/tick_cache_databento")
_OUT_DIR = Path("/Users/duffy/warrior_bot_v2/backtest_archive")
_OUT_DIR.mkdir(exist_ok=True)


log = logging.getLogger("orb_run")


# ---------------------------------------------------------------------------
# Loading bars from cache
# ---------------------------------------------------------------------------


def load_bars_from_cache(
    symbols: list[str],
    start: date,
    end: date,
    rth_only: bool = True,
) -> dict[tuple[str, date], list[Bar]]:
    """Load already-cached 1m bars from disk. No network."""
    result: dict[tuple[str, date], list[Bar]] = {}
    rth_start = (9, 30)
    rth_end = (16, 0)

    for sym in symbols:
        sym_dir = _TICK_CACHE / sym.upper()
        if not sym_dir.exists():
            continue
        for cp in sorted(sym_dir.glob("1m_*.parquet")):
            d_str = cp.stem.replace("1m_", "")
            try:
                d = date.fromisoformat(d_str)
            except ValueError:
                continue
            if d < start or d > end:
                continue
            try:
                df = pd.read_parquet(cp)
            except Exception:
                continue
            if df.empty:
                continue
            bars = []
            for row in df.itertuples(index=False):
                ts = pd.Timestamp(row.ts_event)
                # Strip tz if present
                if ts.tz is not None:
                    ts = ts.tz_localize(None)
                t = ts.time()
                # RTH 09:30–16:00 (the cache may include extended hours)
                if rth_only:
                    minute_of_day = t.hour * 60 + t.minute
                    if minute_of_day < rth_start[0] * 60 + rth_start[1]:
                        continue
                    if minute_of_day >= rth_end[0] * 60 + rth_end[1]:
                        continue
                bars.append(Bar(
                    timestamp=ts.to_pydatetime(),
                    open=float(row.open),
                    high=float(row.high),
                    low=float(row.low),
                    close=float(row.close),
                    volume=float(row.volume),
                    symbol=sym,
                ))
            if bars:
                bars.sort(key=lambda b: b.timestamp)
                result[(sym, d)] = bars
    return result


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def compute_metrics(result: ORBBacktestResult, starting_balance: float) -> dict:
    if not result.trades:
        return {
            "n_trades": 0,
            "net_pnl": 0.0,
            "win_rate": float("nan"),
            "profit_factor": float("nan"),
            "avg_r_multiple": float("nan"),
            "sharpe": float("nan"),
            "max_drawdown_pct": 0.0,
            "max_drawdown_dollars": 0.0,
        }
    df = result.trades_df
    n_trades = len(df)
    wins = (df["pnl"] > 0).sum()
    losses = (df["pnl"] < 0).sum()
    win_rate = wins / n_trades
    gross_wins = df.loc[df["pnl"] > 0, "pnl"].sum()
    gross_losses = abs(df.loc[df["pnl"] < 0, "pnl"].sum())
    pf = gross_wins / gross_losses if gross_losses > 0 else float("inf")
    net_pnl = df["pnl"].sum()
    avg_r = df["r_multiple"].mean()

    # Build daily equity curve
    df = df.sort_values("exit_ts").copy()
    df["cum_pnl"] = df["pnl"].cumsum()
    df["equity"] = starting_balance + df["cum_pnl"]
    df["session_date"] = pd.to_datetime(df["session_date"])

    # Daily P&L by session_date
    daily = df.groupby("session_date")["pnl"].sum().sort_index()
    daily_eq = daily.cumsum() + starting_balance

    # Daily returns
    daily_ret = daily_eq.pct_change().dropna()
    if len(daily_ret) > 1 and daily_ret.std() > 0:
        sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252))
    else:
        sharpe = float("nan")

    # Max drawdown on daily equity
    if len(daily_eq) >= 2:
        peak = daily_eq.cummax()
        dd = (daily_eq - peak) / peak
        max_dd_pct = float(dd.min())
        max_dd_dollars = float((daily_eq - peak).min())
    else:
        max_dd_pct = 0.0
        max_dd_dollars = 0.0

    return {
        "n_trades": int(n_trades),
        "n_wins": int(wins),
        "n_losses": int(losses),
        "net_pnl": float(net_pnl),
        "gross_wins": float(gross_wins),
        "gross_losses": float(gross_losses),
        "win_rate": float(win_rate),
        "profit_factor": float(pf),
        "avg_r_multiple": float(avg_r),
        "sharpe": float(sharpe),
        "max_drawdown_pct": float(max_dd_pct),
        "max_drawdown_dollars": float(max_dd_dollars),
        "ending_equity": float(starting_balance + net_pnl),
        "n_sessions": int(daily.shape[0]),
    }


def per_tier_attribution(df: pd.DataFrame) -> dict:
    """P&L breakdown by price tier."""
    if df.empty:
        return {}
    out = {}
    for tier, group in df.groupby("price_tier"):
        gw = group.loc[group["pnl"] > 0, "pnl"].sum()
        gl = abs(group.loc[group["pnl"] < 0, "pnl"].sum())
        out[tier] = {
            "n_trades": int(len(group)),
            "net_pnl": float(group["pnl"].sum()),
            "win_rate": float((group["pnl"] > 0).mean()),
            "avg_r_multiple": float(group["r_multiple"].mean()),
            "profit_factor": float(gw / gl) if gl > 0 else float("inf"),
        }
    return out


def per_quarter_distribution(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    df = df.copy()
    df["session_date"] = pd.to_datetime(df["session_date"])
    df["quarter"] = df["session_date"].dt.to_period("Q").astype(str)
    out = {}
    total = df["pnl"].sum()
    for q, g in df.groupby("quarter"):
        out[q] = {
            "n_trades": int(len(g)),
            "net_pnl": float(g["pnl"].sum()),
            "pct_of_total": float(g["pnl"].sum() / total) if total != 0 else 0.0,
            "win_rate": float((g["pnl"] > 0).mean()),
        }
    return out


def per_year_distribution(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    df = df.copy()
    df["session_date"] = pd.to_datetime(df["session_date"])
    df["year"] = df["session_date"].dt.year
    out = {}
    total = df["pnl"].sum()
    for y, g in df.groupby("year"):
        out[int(y)] = {
            "n_trades": int(len(g)),
            "net_pnl": float(g["pnl"].sum()),
            "pct_of_total": float(g["pnl"].sum() / total) if total != 0 else 0.0,
            "win_rate": float((g["pnl"] > 0).mean()),
        }
    return out


def per_symbol_attribution(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    out = {}
    for sym, g in df.groupby("symbol"):
        out[sym] = {
            "n_trades": int(len(g)),
            "net_pnl": float(g["pnl"].sum()),
            "win_rate": float((g["pnl"] > 0).mean()),
            "avg_r_multiple": float(g["r_multiple"].mean()),
        }
    return out


# ---------------------------------------------------------------------------
# Run + save
# ---------------------------------------------------------------------------


def run_one(
    bars_by_symbol_day: dict[tuple[str, date], list[Bar]],
    cfg: ORBConfig,
    label: str,
) -> tuple[dict, pd.DataFrame]:
    t0 = time.time()
    result = run_orb_backtest(bars_by_symbol_day, cfg)
    elapsed = time.time() - t0
    metrics = compute_metrics(result, cfg.starting_balance)
    df = result.trades_df
    metrics["run_seconds"] = round(elapsed, 2)
    metrics["label"] = label
    metrics["minutes"] = cfg.minutes

    if not df.empty:
        metrics["per_tier"] = per_tier_attribution(df)
        metrics["per_quarter"] = per_quarter_distribution(df)
        metrics["per_year"] = per_year_distribution(df)
        metrics["per_symbol"] = per_symbol_attribution(df)
        metrics["max_quarter_pct"] = max(q["pct_of_total"] for q in metrics["per_quarter"].values())
    else:
        metrics["per_tier"] = {}
        metrics["per_quarter"] = {}
        metrics["per_year"] = {}
        metrics["per_symbol"] = {}
        metrics["max_quarter_pct"] = 0.0

    return metrics, df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument(
        "--minutes", type=int, nargs="+", default=[5, 15, 30],
        help="OR window widths to sweep (default: 5 15 30).",
    )
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--label", default="orb_oos_2020_2024")
    parser.add_argument(
        "--no-direction-bias", action="store_true",
        help="Disable the 5min opening-bar direction bias gate (allow both directions).",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    symbols = args.symbols or ORB_UNIVERSE
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    log.info("Loading bars from cache: %d symbols, %s..%s", len(symbols), start, end)

    bars = load_bars_from_cache(symbols, start, end)
    n_sym_days = len(bars)
    log.info("Loaded %d (symbol, day) entries", n_sym_days)
    if n_sym_days == 0:
        log.error("No bars loaded — did you run `python -m backtest.orb_fetch_all` first?")
        sys.exit(1)

    all_results: dict[str, dict] = {}
    for m in args.minutes:
        cfg = ORBConfig(
            minutes=m,
            use_direction_bias=not args.no_direction_bias,
        )
        label_m = f"{args.label}_or{m}m"
        log.info("Running ORB sweep: minutes=%d", m)
        metrics, df = run_one(bars, cfg, label_m)
        all_results[f"or{m}min"] = metrics
        # Save trades
        if not df.empty:
            out_trades = _OUT_DIR / f"{label_m}_trades.parquet"
            df.to_parquet(out_trades, index=False)
            log.info("Saved trades: %s (n=%d)", out_trades, len(df))

        log.info(
            "minutes=%d  N=%-4d  PnL=$%-+10.0f  Sharpe=%5.2f  WinRate=%5.1f%%  MaxDD=%6.1f%%  PF=%.2f  MaxQ=%5.1f%%",
            m,
            metrics["n_trades"],
            metrics["net_pnl"],
            metrics["sharpe"],
            metrics["win_rate"] * 100 if not np.isnan(metrics["win_rate"]) else float('nan'),
            metrics["max_drawdown_pct"] * 100,
            metrics["profit_factor"] if not np.isinf(metrics["profit_factor"]) else 99.99,
            metrics["max_quarter_pct"] * 100,
        )

    out_summary = _OUT_DIR / f"{args.label}_summary.json"
    with open(out_summary, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    log.info("Saved summary: %s", out_summary)


if __name__ == "__main__":
    main()
