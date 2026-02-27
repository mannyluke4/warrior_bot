#!/usr/bin/env python3
"""
Analyze behavioral study JSON files and produce consolidated reports.

Reads from study_data/*.json
Writes to study_results/:
  - consolidated.csv       One row per stock, all metrics + summary
  - trades_detail.csv      One row per trade across all stocks
  - correlation_matrix.png Heatmap of metric correlations with P&L
  - analysis_report.md     Full markdown report
"""

import json
import os
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

try:
    import seaborn as sns
    HAS_SNS = True
except ImportError:
    HAS_SNS = False

INPUT_DIR = "study_data"
OUTPUT_DIR = "study_results"


def load_all_json() -> list[dict]:
    """Load all study JSON files."""
    files = sorted(glob.glob(os.path.join(INPUT_DIR, "*.json")))
    data = []
    for f in files:
        with open(f) as fh:
            d = json.load(fh)
            d["_file"] = os.path.basename(f)
            data.append(d)
    return data


def build_stock_df(data: list[dict]) -> pd.DataFrame:
    """Build one-row-per-stock DataFrame with all metrics + summary."""
    rows = []
    for d in data:
        row = {
            "symbol": d["symbol"],
            "date": d["date"],
            "sim_start": d["sim_start"],
            "sim_end": d["sim_end"],
        }
        # Fundamentals
        for k, v in d.get("fundamentals", {}).items():
            row[f"fund_{k}"] = v
        # Stock metrics
        for k, v in d.get("stock_metrics", {}).items():
            row[k] = v
        # Summary
        for k, v in d.get("summary", {}).items():
            row[k] = v
        # Config
        row["exit_mode"] = d.get("config", {}).get("exit_mode", "")
        rows.append(row)
    return pd.DataFrame(rows)


def build_trades_df(data: list[dict]) -> pd.DataFrame:
    """Build one-row-per-trade DataFrame across all stocks."""
    rows = []
    for d in data:
        base = {
            "symbol": d["symbol"],
            "date": d["date"],
        }
        for k, v in d.get("fundamentals", {}).items():
            base[f"fund_{k}"] = v
        for k, v in d.get("stock_metrics", {}).items():
            base[f"sm_{k}"] = v
        for trade in d.get("trades", []):
            row = {**base}
            for k, v in trade.items():
                row[k] = v
            rows.append(row)
    return pd.DataFrame(rows)


def make_correlation_matrix(df: pd.DataFrame, output_path: str):
    """Generate a correlation heatmap between behavioral metrics and P&L."""
    if not HAS_MPL:
        print("  matplotlib not available, skipping correlation matrix")
        return

    # Select numeric columns that are meaningful for correlation
    metric_cols = [c for c in df.columns if df[c].dtype in ("float64", "int64", "float32", "int32")]
    # Remove identifiers
    skip = {"trade_num", "qty"}
    metric_cols = [c for c in metric_cols if c not in skip]

    if len(metric_cols) < 3:
        print("  Not enough numeric columns for correlation matrix")
        return

    corr = df[metric_cols].corr()

    fig_size = max(10, len(metric_cols) * 0.4)
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))

    if HAS_SNS:
        sns.heatmap(corr, annot=False, cmap="RdBu_r", center=0, ax=ax,
                    xticklabels=True, yticklabels=True)
    else:
        im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(range(len(metric_cols)))
        ax.set_yticks(range(len(metric_cols)))
        ax.set_xticklabels(metric_cols, rotation=90, fontsize=6)
        ax.set_yticklabels(metric_cols, fontsize=6)
        plt.colorbar(im, ax=ax)

    ax.set_title("Behavioral Metrics Correlation Matrix", fontsize=12)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"  Saved: {output_path}")


def generate_report(stock_df: pd.DataFrame, trades_df: pd.DataFrame, data: list[dict]) -> str:
    """Generate the markdown analysis report."""
    lines = []
    lines.append("# Phase 1 Behavior Study — Analysis Report")
    lines.append(f"**Generated**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Stocks analyzed**: {len(stock_df)}")
    lines.append(f"**Total trades**: {len(trades_df)}")
    lines.append("")

    # Dataset summary
    lines.append("---")
    lines.append("## 1. Dataset Summary")
    lines.append("")
    dates = stock_df["date"].unique()
    lines.append(f"- **Date range**: {min(dates)} to {max(dates)}")
    lines.append(f"- **Unique dates**: {len(dates)}")
    total_pnl = stock_df["net_pnl"].sum()
    lines.append(f"- **Total P&L across all stocks**: ${total_pnl:+,.0f}")
    avg_pnl = stock_df["net_pnl"].mean()
    lines.append(f"- **Average P&L per stock**: ${avg_pnl:+,.0f}")
    winners = (stock_df["net_pnl"] > 0).sum()
    losers = (stock_df["net_pnl"] < 0).sum()
    flat = (stock_df["net_pnl"] == 0).sum()
    lines.append(f"- **Winning stocks**: {winners} | **Losing stocks**: {losers} | **Flat**: {flat}")
    lines.append("")

    # Per-stock P&L table
    lines.append("### Per-Stock Results")
    lines.append("")
    lines.append("| Symbol | Date | Trades | Wins | Losses | Net P&L | Win Rate | Avg R |")
    lines.append("|--------|------|--------|------|--------|---------|----------|-------|")
    for _, r in stock_df.sort_values("net_pnl", ascending=False).iterrows():
        lines.append(
            f"| {r['symbol']} | {r['date']} | {r.get('total_trades', 0):.0f} | "
            f"{r.get('wins', 0):.0f} | {r.get('losses', 0):.0f} | "
            f"${r['net_pnl']:+,.0f} | {r.get('win_rate', 0):.0f}% | "
            f"{r.get('avg_r', 0):+.1f}R |"
        )
    lines.append("")

    # Feature distributions
    lines.append("---")
    lines.append("## 2. Key Metric Distributions")
    lines.append("")
    key_metrics = [
        ("new_high_count_30m", "New Highs (30m)"),
        ("pullback_count_30m", "Pullbacks (30m)"),
        ("pullback_depth_avg_pct", "Avg Pullback Depth %"),
        ("vol_total_30m", "Total Volume (30m)"),
        ("vol_decay_ratio", "Volume Decay Ratio"),
        ("green_bar_ratio_30m", "Green Bar Ratio"),
        ("max_consecutive_green", "Max Consecutive Green"),
        ("price_range_30m_pct", "Price Range % (30m)"),
        ("upper_wick_ratio_avg", "Avg Upper Wick Ratio"),
        ("pct_bars_above_vwap_30m", "% Bars Above VWAP"),
    ]
    lines.append("| Metric | Mean | Median | Std | Min | Max |")
    lines.append("|--------|------|--------|-----|-----|-----|")
    for col, label in key_metrics:
        if col in stock_df.columns:
            s = stock_df[col].dropna()
            if len(s) > 0:
                lines.append(
                    f"| {label} | {s.mean():.2f} | {s.median():.2f} | "
                    f"{s.std():.2f} | {s.min():.2f} | {s.max():.2f} |"
                )
    lines.append("")

    # Correlations with P&L
    lines.append("---")
    lines.append("## 3. Top Features Correlated with P&L")
    lines.append("")
    numeric_cols = [c for c in stock_df.columns
                    if stock_df[c].dtype in ("float64", "int64") and c != "net_pnl"]
    if "net_pnl" in stock_df.columns and len(numeric_cols) > 0:
        correlations = {}
        for c in numeric_cols:
            s = stock_df[[c, "net_pnl"]].dropna()
            if len(s) > 3:
                correlations[c] = s[c].corr(s["net_pnl"])
        sorted_corr = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)

        lines.append("### Top 10 Positive Correlations (higher metric → higher P&L)")
        lines.append("")
        lines.append("| Metric | Correlation |")
        lines.append("|--------|-------------|")
        positive = [(k, v) for k, v in sorted_corr if v > 0][:10]
        for k, v in positive:
            lines.append(f"| {k} | {v:+.3f} |")
        lines.append("")

        lines.append("### Top 10 Negative Correlations (higher metric → lower P&L)")
        lines.append("")
        lines.append("| Metric | Correlation |")
        lines.append("|--------|-------------|")
        negative = [(k, v) for k, v in sorted_corr if v < 0][:10]
        for k, v in negative:
            lines.append(f"| {k} | {v:+.3f} |")
        lines.append("")

    # Trade-level analysis
    lines.append("---")
    lines.append("## 4. Trade-Level Analysis")
    lines.append("")
    if len(trades_df) > 0:
        lines.append(f"- **Total trades**: {len(trades_df)}")
        winning_trades = trades_df[trades_df["pnl"] > 0]
        losing_trades = trades_df[trades_df["pnl"] < 0]
        lines.append(f"- **Winning trades**: {len(winning_trades)} ({len(winning_trades)/len(trades_df)*100:.0f}%)")
        lines.append(f"- **Losing trades**: {len(losing_trades)} ({len(losing_trades)/len(trades_df)*100:.0f}%)")
        lines.append(f"- **Average P&L per trade**: ${trades_df['pnl'].mean():+,.0f}")
        lines.append(f"- **Median P&L per trade**: ${trades_df['pnl'].median():+,.0f}")
        if "hold_time_sec" in trades_df.columns:
            lines.append(f"- **Average hold time**: {trades_df['hold_time_sec'].mean():.0f} seconds")
        if "peak_unrealized_r" in trades_df.columns:
            lines.append(f"- **Average peak unrealized R**: {trades_df['peak_unrealized_r'].mean():.1f}R")
        lines.append("")

        # Exit reason breakdown
        if "exit_reason" in trades_df.columns:
            lines.append("### Exit Reason Breakdown")
            lines.append("")
            lines.append("| Exit Reason | Count | Avg P&L | Win Rate |")
            lines.append("|-------------|-------|---------|----------|")
            for reason, grp in trades_df.groupby("exit_reason"):
                wr = (grp["pnl"] > 0).mean() * 100
                lines.append(
                    f"| {reason} | {len(grp)} | ${grp['pnl'].mean():+,.0f} | {wr:.0f}% |"
                )
            lines.append("")

        # Tag frequency analysis
        if "tags" in trades_df.columns:
            all_tags = {}
            for _, row in trades_df.iterrows():
                tags = row.get("tags", [])
                if isinstance(tags, list):
                    for tag in tags:
                        if tag not in all_tags:
                            all_tags[tag] = {"count": 0, "pnl_sum": 0, "wins": 0}
                        all_tags[tag]["count"] += 1
                        all_tags[tag]["pnl_sum"] += row.get("pnl", 0)
                        if row.get("pnl", 0) > 0:
                            all_tags[tag]["wins"] += 1
            if all_tags:
                lines.append("### Tag Performance")
                lines.append("")
                lines.append("| Tag | Appearances | Avg P&L | Win Rate |")
                lines.append("|-----|-------------|---------|----------|")
                for tag in sorted(all_tags.keys(), key=lambda t: all_tags[t]["pnl_sum"], reverse=True):
                    info = all_tags[tag]
                    avg = info["pnl_sum"] / info["count"]
                    wr = info["wins"] / info["count"] * 100
                    lines.append(f"| {tag} | {info['count']} | ${avg:+,.0f} | {wr:.0f}% |")
                lines.append("")

    # Left on table analysis
    lines.append("---")
    lines.append("## 5. 'Left on Table' Analysis")
    lines.append("")
    if "left_on_table_pct" in trades_df.columns:
        lot = trades_df["left_on_table_pct"].dropna()
        if len(lot) > 0:
            lines.append(f"- **Average left on table**: {lot.mean():.1f}%")
            lines.append(f"- **Median left on table**: {lot.median():.1f}%")
            lines.append("")

            # Worst offenders
            lines.append("### Trades with Most Profit Left on Table")
            lines.append("")
            lines.append("| Symbol | Trade # | Entry | Exit | Exit Reason | Left on Table % | High After 30m |")
            lines.append("|--------|---------|-------|------|-------------|-----------------|----------------|")
            top_lot = trades_df.nlargest(10, "left_on_table_pct")
            for _, t in top_lot.iterrows():
                lines.append(
                    f"| {t['symbol']} | {t.get('trade_num', '?')} | "
                    f"${t.get('entry_price', 0):.2f} | ${t.get('exit_price', 0):.2f} | "
                    f"{t.get('exit_reason', '?')} | {t.get('left_on_table_pct', 0):.1f}% | "
                    f"${t.get('high_after_exit_30m', 0) or 0:.2f} |"
                )
            lines.append("")

    # Stock type clustering (preliminary)
    lines.append("---")
    lines.append("## 6. Preliminary Stock Clustering")
    lines.append("")
    if len(stock_df) >= 5:
        # Classify by behavioral patterns
        lines.append("### By Price Action Type (first 30 minutes)")
        lines.append("")

        # Runners: many new highs, low pullback, strong green
        runners = stock_df[
            (stock_df.get("new_high_count_30m", pd.Series(dtype=float)) >= 10) &
            (stock_df.get("green_bar_ratio_30m", pd.Series(dtype=float)) >= 0.6)
        ] if "new_high_count_30m" in stock_df.columns else pd.DataFrame()

        # Choppy: many pullbacks, low green ratio
        choppy = stock_df[
            (stock_df.get("pullback_count_30m", pd.Series(dtype=float)) >= 5) &
            (stock_df.get("green_bar_ratio_30m", pd.Series(dtype=float)) < 0.55)
        ] if "pullback_count_30m" in stock_df.columns else pd.DataFrame()

        # Faders: low new highs, high upper wick
        faders = stock_df[
            (stock_df.get("new_high_count_30m", pd.Series(dtype=float)) <= 5) &
            (stock_df.get("upper_wick_ratio_avg", pd.Series(dtype=float)) >= 0.3)
        ] if "new_high_count_30m" in stock_df.columns else pd.DataFrame()

        lines.append(f"- **Runners** (10+ new highs, 60%+ green bars): {len(runners)} stocks")
        if len(runners) > 0:
            lines.append(f"  - Stocks: {', '.join(runners['symbol'].tolist())}")
            lines.append(f"  - Avg P&L: ${runners['net_pnl'].mean():+,.0f}")
        lines.append(f"- **Choppy** (5+ pullbacks, <55% green bars): {len(choppy)} stocks")
        if len(choppy) > 0:
            lines.append(f"  - Stocks: {', '.join(choppy['symbol'].tolist())}")
            lines.append(f"  - Avg P&L: ${choppy['net_pnl'].mean():+,.0f}")
        lines.append(f"- **Faders** (5 or fewer new highs, high upper wicks): {len(faders)} stocks")
        if len(faders) > 0:
            lines.append(f"  - Stocks: {', '.join(faders['symbol'].tolist())}")
            lines.append(f"  - Avg P&L: ${faders['net_pnl'].mean():+,.0f}")
        lines.append("")

    # Volume profile
    lines.append("---")
    lines.append("## 7. Volume Profile Analysis")
    lines.append("")
    if "vol_decay_ratio" in stock_df.columns:
        lines.append("### Volume Decay vs P&L")
        lines.append("")
        lines.append("| Volume Decay Bucket | Stocks | Avg P&L | Avg New Highs |")
        lines.append("|---------------------|--------|---------|---------------|")
        stock_df["_vd_bucket"] = pd.cut(stock_df["vol_decay_ratio"],
                                         bins=[0, 0.3, 0.6, 1.0, 10],
                                         labels=["Heavy decay (<0.3)", "Moderate (0.3-0.6)",
                                                  "Steady (0.6-1.0)", "Increasing (>1.0)"])
        for bucket, grp in stock_df.groupby("_vd_bucket", observed=True):
            nh = grp["new_high_count_30m"].mean() if "new_high_count_30m" in grp.columns else 0
            lines.append(f"| {bucket} | {len(grp)} | ${grp['net_pnl'].mean():+,.0f} | {nh:.1f} |")
        stock_df.drop(columns=["_vd_bucket"], inplace=True)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Report generated by analyze_study.py — Phase 1 Behavior Study*")
    lines.append("")

    return "\n".join(lines)


def main():
    data = load_all_json()
    if not data:
        print(f"No JSON files found in {INPUT_DIR}/")
        sys.exit(1)

    print(f"Loaded {len(data)} study files from {INPUT_DIR}/")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Build DataFrames
    stock_df = build_stock_df(data)
    trades_df = build_trades_df(data)
    print(f"  {len(stock_df)} stocks, {len(trades_df)} trades")

    # 1. Consolidated CSV
    csv_path = os.path.join(OUTPUT_DIR, "consolidated.csv")
    stock_df.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path}")

    # 2. Trades detail CSV
    trades_path = os.path.join(OUTPUT_DIR, "trades_detail.csv")
    trades_df.to_csv(trades_path, index=False)
    print(f"  Saved: {trades_path}")

    # 3. Correlation matrix
    corr_path = os.path.join(OUTPUT_DIR, "correlation_matrix.png")
    make_correlation_matrix(trades_df, corr_path)

    # 4. Analysis report
    report = generate_report(stock_df, trades_df, data)
    report_path = os.path.join(OUTPUT_DIR, "analysis_report.md")
    with open(report_path, "w") as f:
        f.write(report)
    print(f"  Saved: {report_path}")

    print(f"\nDone! Results in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
