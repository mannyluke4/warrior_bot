"""Compare release_on_stop vs first_in_time backtest results.

Reads per-strategy CSV trade logs from both runs, computes Sharpe / P&L /
MaxDD per strategy + portfolio, attributes secondary-fill P&L, and prints
markdown-ready blocks for the validation report.

Usage::

    python scripts/release_on_stop_analysis.py \\
        --baseline backtest_archive/wave3_portfolio \\
        --treatment backtest_archive/wave4_release_on_stop \\
        --mode fixed_dollar
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def _trades(dir_: Path, mode: str) -> dict[str, pd.DataFrame]:
    out = {}
    for fp in sorted(dir_.glob(f"trades_*_{mode}.csv")):
        strat = fp.stem.replace("trades_", "").replace(f"_{mode}", "")
        df = pd.read_csv(fp)
        if df.empty:
            out[strat] = df
            continue
        df["entry_ts"] = pd.to_datetime(df["entry_ts"])
        df["exit_ts"] = pd.to_datetime(df["exit_ts"])
        df["session_date"] = pd.to_datetime(df["session_date"]).dt.date
        out[strat] = df
    return out


def _metrics(df: pd.DataFrame, starting_equity: float = 100_000.0) -> dict[str, float]:
    if df.empty:
        return {
            "n_trades": 0, "net_pnl": 0.0, "win_rate": float("nan"),
            "profit_factor": float("nan"), "avg_r": float("nan"),
            "sharpe": float("nan"), "max_dd_pct": 0.0,
        }
    daily = df.groupby("session_date")["pnl"].sum().sort_index()
    eq = daily.cumsum() + starting_equity
    running_max = eq.cummax()
    dd_pct = (eq - running_max) / running_max
    max_dd_pct = float(dd_pct.min()) if len(dd_pct) else 0.0
    daily_pct = daily / starting_equity
    if daily_pct.std() > 0 and len(daily_pct) > 1:
        sharpe = float(daily_pct.mean() / daily_pct.std() * np.sqrt(252))
    else:
        sharpe = float("nan")
    wins = df[df.pnl > 0].pnl.sum()
    losses = -df[df.pnl < 0].pnl.sum()
    pf = (wins / losses) if losses > 0 else float("nan")
    return {
        "n_trades": int(len(df)),
        "net_pnl": float(df.pnl.sum()),
        "win_rate": float((df.pnl > 0).mean()),
        "profit_factor": pf,
        "avg_r": float(df.r_multiple.mean()) if "r_multiple" in df.columns else float("nan"),
        "sharpe": sharpe,
        "max_dd_pct": max_dd_pct,
    }


def _portfolio_metrics(by_strat: dict[str, pd.DataFrame], starting_equity: float = 100_000.0) -> dict[str, float]:
    frames = [df for df in by_strat.values() if not df.empty]
    if not frames:
        return _metrics(pd.DataFrame(columns=["pnl", "session_date"]))
    combined = pd.concat(frames, ignore_index=True)
    return _metrics(combined, starting_equity=starting_equity)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True,
                    help="dir with first_in_time trades (Wave 3 baseline)")
    ap.add_argument("--treatment", required=True,
                    help="dir with release_on_stop trades")
    ap.add_argument("--mode", default="fixed_dollar")
    args = ap.parse_args()

    base_dir = Path(args.baseline)
    treat_dir = Path(args.treatment)

    base = _trades(base_dir, args.mode)
    treat = _trades(treat_dir, args.mode)

    # Read summaries for collision counts
    try:
        base_summary = json.loads((base_dir / f"summary_{args.mode}.json").read_text())
    except FileNotFoundError:
        base_summary = {}
    try:
        treat_summary = json.loads((treat_dir / f"summary_{args.mode}.json").read_text())
    except FileNotFoundError:
        treat_summary = {}

    strategies = sorted(set(base) | set(treat))

    print("# Per-strategy comparison (release_on_stop vs first_in_time)\n")
    print("| Strategy | Mode | N trades | Net P&L | Sharpe | MaxDD% | WR | PF |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    for s in strategies:
        b = _metrics(base.get(s, pd.DataFrame(columns=["pnl", "session_date"])))
        t = _metrics(treat.get(s, pd.DataFrame(columns=["pnl", "session_date"])))
        print(
            f"| {s} | baseline | {b['n_trades']:,} | ${b['net_pnl']:+,.0f} "
            f"| {b['sharpe']:.2f} | {b['max_dd_pct']*100:.1f}% "
            f"| {b['win_rate']:.1%} | {b['profit_factor']:.2f} |"
        )
        print(
            f"| {s} | release | {t['n_trades']:,} | ${t['net_pnl']:+,.0f} "
            f"| {t['sharpe']:.2f} | {t['max_dd_pct']*100:.1f}% "
            f"| {t['win_rate']:.1%} | {t['profit_factor']:.2f} |"
        )
        delta_pnl = t["net_pnl"] - b["net_pnl"]
        delta_sharpe = (t["sharpe"] - b["sharpe"]) if not (np.isnan(t["sharpe"]) or np.isnan(b["sharpe"])) else float("nan")
        print(
            f"| {s} | Δ | {t['n_trades'] - b['n_trades']:+,} | ${delta_pnl:+,.0f} "
            f"| {delta_sharpe:+.2f} | {(t['max_dd_pct'] - b['max_dd_pct'])*100:+.1f}pp |  |  |"
        )

    print("\n# Portfolio aggregate\n")
    pb = _portfolio_metrics(base)
    pt = _portfolio_metrics(treat)
    print(f"- Baseline (first_in_time)    : net ${pb['net_pnl']:+,.0f}, "
          f"Sharpe {pb['sharpe']:.2f}, MaxDD {pb['max_dd_pct']*100:.1f}%, N {pb['n_trades']:,}")
    print(f"- Treatment (release_on_stop) : net ${pt['net_pnl']:+,.0f}, "
          f"Sharpe {pt['sharpe']:.2f}, MaxDD {pt['max_dd_pct']*100:.1f}%, N {pt['n_trades']:,}")
    print(f"- Realized lift               : ${pt['net_pnl'] - pb['net_pnl']:+,.0f} "
          f"({(pt['net_pnl'] - pb['net_pnl']) / max(abs(pb['net_pnl']), 1) * 100:+.1f}%)")
    print(f"- $427K target recovery       : {(pt['net_pnl'] - pb['net_pnl']) / 427_000 * 100:.0f}% of estimate")

    print("\n# Lock collisions\n")
    print(f"- Baseline collisions  : {base_summary.get('lock_collisions', 'n/a')}")
    print(f"- Treatment collisions : {treat_summary.get('lock_collisions', 'n/a')}")

    print("\n# Secondary-fill attribution (release_on_stop only)\n")
    print("| Strategy | Total trades | Secondary fills | Secondary P&L | Sec-fill share of net |")
    print("|---|---:|---:|---:|---:|")
    secondary_pnl_total = 0.0
    secondary_count_total = 0
    for s in strategies:
        df = treat.get(s)
        if df is None or df.empty or "secondary_fill" not in df.columns:
            continue
        sec = df[df["secondary_fill"]]
        if len(sec) == 0:
            print(f"| {s} | {len(df):,} | 0 | $0 | 0% |")
            continue
        sec_pnl = float(sec.pnl.sum())
        net = float(df.pnl.sum())
        share = sec_pnl / net if net != 0 else float("nan")
        secondary_pnl_total += sec_pnl
        secondary_count_total += len(sec)
        print(f"| {s} | {len(df):,} | {len(sec):,} | ${sec_pnl:+,.0f} | {share:+.1%} |")
    print(f"\n**Total secondary fills:** {secondary_count_total:,}")
    print(f"**Total secondary P&L:** ${secondary_pnl_total:+,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
