#!/usr/bin/env python3
"""
box_optimize.py — Phase 2B: Exit variant comparison + filter tightening.

Runs all exit variants and filter sets using cached bars (no IBKR needed),
generates comparison reports.

Usage:
    python box_optimize.py                    # Run everything
    python box_optimize.py --variants-only    # Just exit variants
    python box_optimize.py --filters-only     # Just filter sets (uses winning variant)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from box_backtest import (
    BarProxy, _load_cached_bars, load_all_candidates,
    run_candidate_with_trades, trade_to_row, RESULTS_DIR, _bar_time_et,
)

# ── Filter Sets ─────────────────────────────────────────────────────

FILTER_SETS = {
    "proven": {
        "label": "Proven Box",
        "min_range_pct": 2.0,
        "max_range_pct": 6.0,
        "min_total_tests": 5,
        "min_price": 15.0,
        "max_adr_util": 0.80,
        "skip_friday": False,
    },
    "highconv": {
        "label": "High Conviction",
        "min_range_pct": 2.0,
        "max_range_pct": 4.0,
        "min_high_tests": 3,
        "min_low_tests": 3,
        "min_price": 15.0,
        "max_adr_util": 0.50,
        "skip_friday": False,
    },
    "volsweet": {
        "label": "Vol Sweet Spot",
        "min_range_pct": 2.0,
        "max_range_pct": 6.0,
        "min_total_tests": 5,
        "min_price": 15.0,
        "max_adr_util": 0.80,
        "skip_friday": True,
    },
}


def passes_filter(candidate: dict, filter_set: dict) -> bool:
    """Check if a candidate passes a filter set."""
    fs = filter_set
    c = candidate

    if c.get("price", 0) < fs.get("min_price", 0):
        return False
    if c.get("range_pct", 0) < fs.get("min_range_pct", 0):
        return False
    if c.get("range_pct", 0) > fs.get("max_range_pct", 100):
        return False

    total_tests = c.get("high_tests", 0) + c.get("low_tests", 0)
    if total_tests < fs.get("min_total_tests", 0):
        return False
    if c.get("high_tests", 0) < fs.get("min_high_tests", 0):
        return False
    if c.get("low_tests", 0) < fs.get("min_low_tests", 0):
        return False
    if c.get("adr_util_today", 0) > fs.get("max_adr_util", 1.0):
        return False

    if fs.get("skip_friday"):
        try:
            dt = datetime.strptime(c.get("_date", ""), "%Y-%m-%d")
            if dt.weekday() == 4:  # Friday
                return False
        except ValueError:
            pass

    return True


# ── Run One Config ──────────────────────────────────────────────────

def run_config(candidates: list, exit_variant: str, output_dir: Path,
               filter_set: dict = None, label: str = "") -> dict:
    """Run backtest for a specific exit variant + optional filter. Returns summary dict."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Apply filter
    if filter_set:
        filtered = [c for c in candidates if passes_filter(c, filter_set)]
    else:
        filtered = candidates

    print(f"\n{'='*50}", flush=True)
    print(f"  Running: {label or exit_variant}", flush=True)
    print(f"  Candidates: {len(filtered)} (of {len(candidates)})", flush=True)
    print(f"  Exit variant: {exit_variant}", flush=True)
    print(f"{'='*50}", flush=True)

    results = []
    all_trade_rows = []

    # Group by date
    by_date = defaultdict(list)
    for c in filtered:
        by_date[c["_date"]].append(c)

    for date_str in sorted(by_date.keys()):
        for candidate in by_date[date_str]:
            symbol = candidate["symbol"]
            cached = _load_cached_bars(date_str, symbol)
            if cached is not None:
                bars_1m = [BarProxy(b) for b in cached]
            else:
                bars_1m = []

            result, trades = run_candidate_with_trades(candidate, bars_1m, exit_variant)
            results.append(result)
            for t in trades:
                all_trade_rows.append(trade_to_row(t, date_str))

    # Write CSVs
    _write_csvs(results, all_trade_rows, output_dir)

    # Compute summary
    summary = _compute_summary(results, all_trade_rows, len(filtered))
    summary["label"] = label or exit_variant
    summary["exit_variant"] = exit_variant
    summary["candidates_total"] = len(filtered)

    print(f"  Trades: {summary['total_trades']}, P&L: ${summary['total_pnl']:,.2f}, "
          f"WR: {summary['win_rate']:.1f}%, Avg: ${summary['avg_pnl']:,.2f}", flush=True)

    return summary


def _write_csvs(results, trade_rows, output_dir):
    candidate_fields = [
        "date", "symbol", "box_score", "range_high_5d", "range_low_5d",
        "range_pct", "range_position_pct", "high_tests", "low_tests",
        "adr_util_today", "vwap_dist_pct", "sma_slope_pct", "avg_daily_vol_5d",
        "price", "num_trades", "total_pnl", "best_trade_pnl", "worst_trade_pnl",
        "win_rate", "avg_hold_minutes", "exit_reasons", "skip_reason",
    ]
    trade_fields = [
        "date", "symbol", "entry_time", "entry_price", "exit_time", "exit_price",
        "shares", "pnl", "pnl_pct", "exit_reason", "hold_minutes",
        "box_top", "box_bottom", "box_range", "rsi_at_entry", "bar_volume_at_entry",
    ]
    with open(output_dir / "per_candidate.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=candidate_fields)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in candidate_fields})
    with open(output_dir / "all_trades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=trade_fields)
        w.writeheader()
        for r in trade_rows:
            w.writerow(r)


def _compute_summary(results, trade_rows, n_candidates) -> dict:
    traded = [r for r in results if r["num_trades"] > 0]
    total_trades = sum(r["num_trades"] for r in results)
    total_pnl = sum(r["total_pnl"] for r in traded)
    wins = sum(1 for t in trade_rows if t.get("pnl") and float(t["pnl"]) > 0)
    losses = total_trades - wins
    win_rate = wins / total_trades * 100 if total_trades else 0
    avg_pnl = total_pnl / total_trades if total_trades else 0

    # Profit factor
    gross_wins = sum(float(t["pnl"]) for t in trade_rows if float(t.get("pnl", 0)) > 0)
    gross_losses = abs(sum(float(t["pnl"]) for t in trade_rows if float(t.get("pnl", 0)) < 0))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    # Avg winner/loser
    winner_pnls = [float(t["pnl"]) for t in trade_rows if float(t.get("pnl", 0)) > 0]
    loser_pnls = [float(t["pnl"]) for t in trade_rows if float(t.get("pnl", 0)) < 0]
    avg_winner = statistics.mean(winner_pnls) if winner_pnls else 0
    avg_loser = statistics.mean(loser_pnls) if loser_pnls else 0

    # Max drawdown (cumulative P&L curve)
    cum_pnl = 0
    peak_pnl = 0
    max_dd = 0
    for t in trade_rows:
        cum_pnl += float(t.get("pnl", 0))
        peak_pnl = max(peak_pnl, cum_pnl)
        dd = peak_pnl - cum_pnl
        max_dd = max(max_dd, dd)

    # Avg hold time
    hold_times = [float(t["hold_minutes"]) for t in trade_rows if float(t.get("hold_minutes", 0)) > 0]
    avg_hold = statistics.mean(hold_times) if hold_times else 0

    # Exit reason distribution
    exit_reasons = defaultdict(int)
    for t in trade_rows:
        exit_reasons[t.get("exit_reason", "unknown")] += 1

    # Re-entry count (trades > 1 per symbol-date)
    sym_date_counts = defaultdict(int)
    for t in trade_rows:
        sym_date_counts[(t["date"], t["symbol"])] += 1
    reentries = sum(v - 1 for v in sym_date_counts.values() if v > 1)

    # Daily P&L for consistency
    daily_pnl = defaultdict(float)
    for r in traded:
        daily_pnl[r["date"]] += r["total_pnl"]
    positive_days = sum(1 for v in daily_pnl.values() if v > 0)
    total_days = len(daily_pnl)
    consistency = positive_days / total_days * 100 if total_days else 0

    # Worst trade
    worst_pnl = min((float(t["pnl"]) for t in trade_rows), default=0)
    best_pnl = max((float(t["pnl"]) for t in trade_rows), default=0)

    # Max daily loss
    max_daily_loss = min(daily_pnl.values(), default=0)

    return {
        "candidates_traded": len(traded),
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_pnl": avg_pnl,
        "avg_hold": avg_hold,
        "profit_factor": profit_factor,
        "max_drawdown": max_dd,
        "avg_winner": avg_winner,
        "avg_loser": avg_loser,
        "best_trade": best_pnl,
        "worst_trade": worst_pnl,
        "exit_reasons": dict(exit_reasons),
        "reentries": reentries,
        "consistency": consistency,
        "positive_days": positive_days,
        "total_days": total_days,
        "max_daily_loss": max_daily_loss,
        "daily_pnl": dict(daily_pnl),
    }


# ── Reports ─────────────────────────────────────────────────────────

def generate_exit_comparison(summaries: list):
    """Generate EXIT_VARIANT_COMPARISON.md."""
    lines = ["# Exit Variant Comparison Report",
             f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             "", "---", ""]

    # Main comparison table
    lines.append("## Side-by-Side Comparison")
    lines.append("")
    headers = ["Metric"] + [s["label"] for s in summaries]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "-------|" * len(headers))

    rows = [
        ("Total trades", lambda s: f"{s['total_trades']}"),
        ("Wins", lambda s: f"{s['wins']}"),
        ("Win rate", lambda s: f"{s['win_rate']:.1f}%"),
        ("Total P&L", lambda s: f"${s['total_pnl']:,.2f}"),
        ("Avg P&L/trade", lambda s: f"${s['avg_pnl']:,.2f}"),
        ("Avg hold (min)", lambda s: f"{s['avg_hold']:.0f}"),
        ("Profit factor", lambda s: f"{s['profit_factor']:.2f}" if s['profit_factor'] != float('inf') else "inf"),
        ("Max drawdown", lambda s: f"${s['max_drawdown']:,.2f}"),
        ("Avg winner", lambda s: f"${s['avg_winner']:,.2f}"),
        ("Avg loser", lambda s: f"${s['avg_loser']:,.2f}"),
        ("Best trade", lambda s: f"${s['best_trade']:,.2f}"),
        ("Worst trade", lambda s: f"${s['worst_trade']:,.2f}"),
        ("Re-entries", lambda s: f"{s['reentries']}"),
        ("Consistency", lambda s: f"{s['consistency']:.0f}% ({s['positive_days']}/{s['total_days']} days)"),
        ("Max daily loss", lambda s: f"${s['max_daily_loss']:,.2f}"),
    ]
    for label, fn in rows:
        line = f"| {label} | " + " | ".join(fn(s) for s in summaries) + " |"
        lines.append(line)

    lines.append("")
    lines.append("---")
    lines.append("")

    # Exit reason breakdown per variant
    lines.append("## Exit Reason Breakdown")
    lines.append("")
    all_reasons = set()
    for s in summaries:
        all_reasons.update(s["exit_reasons"].keys())

    headers = ["Exit Reason"] + [s["label"] for s in summaries]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "-------|" * len(headers))
    for reason in sorted(all_reasons):
        vals = [str(s["exit_reasons"].get(reason, 0)) for s in summaries]
        lines.append(f"| {reason} | " + " | ".join(vals) + " |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Generated by box_optimize.py — STOP for review.*")

    report_path = RESULTS_DIR / "EXIT_VARIANT_COMPARISON.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport saved: {report_path}", flush=True)


def generate_filter_comparison(summaries: list, baseline_summary: dict):
    """Generate FILTER_COMPARISON.md."""
    all_summaries = [baseline_summary] + summaries

    lines = ["# Filter Set Comparison Report",
             f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             "", "---", ""]

    headers = ["Metric"] + [s["label"] for s in all_summaries]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "-------|" * len(headers))

    rows = [
        ("Candidates passing", lambda s: f"{s['candidates_total']}"),
        ("Candidates traded", lambda s: f"{s['candidates_traded']}"),
        ("Total trades", lambda s: f"{s['total_trades']}"),
        ("Win rate", lambda s: f"{s['win_rate']:.1f}%"),
        ("Total P&L", lambda s: f"${s['total_pnl']:,.2f}"),
        ("Avg P&L/trade", lambda s: f"${s['avg_pnl']:,.2f}"),
        ("Profit factor", lambda s: f"{s['profit_factor']:.2f}" if s['profit_factor'] != float('inf') else "inf"),
        ("Worst trade", lambda s: f"${s['worst_trade']:,.2f}"),
        ("Max daily loss", lambda s: f"${s['max_daily_loss']:,.2f}"),
        ("Consistency", lambda s: f"{s['consistency']:.0f}% ({s['positive_days']}/{s['total_days']} days)"),
    ]
    for label, fn in rows:
        line = f"| {label} | " + " | ".join(fn(s) for s in all_summaries) + " |"
        lines.append(line)

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Generated by box_optimize.py — STOP for review.*")

    report_path = RESULTS_DIR / "FILTER_COMPARISON.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Report saved: {report_path}", flush=True)


def generate_best_config_report(best_summary: dict, best_exit: str,
                                best_filter: str, filter_set: dict):
    """Generate BEST_CONFIG_REPORT.md."""
    lines = ["# Best Configuration Report",
             f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"**Best Exit**: {best_exit}",
             f"**Best Filter**: {best_filter}",
             "", "---", ""]

    # 1. Recommended config
    lines.append("## 1. Recommended Configuration")
    lines.append("")
    lines.append("```bash")
    lines.append(f"# Exit variant: {best_exit}")
    if best_exit == "vwap":
        lines.append("WB_BOX_VWAP_EXIT_ENABLED=1")
    elif best_exit == "midbox":
        lines.append("WB_BOX_MID_EXIT_ENABLED=1")
    elif best_exit == "tiered":
        lines.append("WB_BOX_TIERED_EXIT_ENABLED=1")
    lines.append("")
    if filter_set:
        lines.append(f"# Filter set: {best_filter}")
        for k, v in filter_set.items():
            if k != "label":
                lines.append(f"# {k} = {v}")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 2. Performance summary
    lines.append("## 2. Performance Summary")
    lines.append("")
    s = best_summary
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total trades | {s['total_trades']} |")
    lines.append(f"| Win rate | {s['win_rate']:.1f}% |")
    lines.append(f"| Total P&L | ${s['total_pnl']:,.2f} |")
    lines.append(f"| Avg P&L/trade | ${s['avg_pnl']:,.2f} |")
    lines.append(f"| Profit factor | {s['profit_factor']:.2f} |")
    lines.append(f"| Max drawdown | ${s['max_drawdown']:,.2f} |")
    lines.append(f"| Avg winner | ${s['avg_winner']:,.2f} |")
    lines.append(f"| Avg loser | ${s['avg_loser']:,.2f} |")
    lines.append(f"| Consistency | {s['consistency']:.0f}% ({s['positive_days']}/{s['total_days']} days) |")
    lines.append(f"| Max daily loss | ${s['max_daily_loss']:,.2f} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 3. Cumulative P&L day by day
    lines.append("## 3. Cumulative P&L Curve")
    lines.append("")
    lines.append("| Date | Daily P&L | Cumulative P&L |")
    lines.append("|------|-----------|----------------|")
    cum = 0
    for date_str in sorted(s["daily_pnl"].keys()):
        daily = s["daily_pnl"][date_str]
        cum += daily
        marker = " <<<" if daily < -200 else ""
        lines.append(f"| {date_str} | ${daily:+,.2f} | ${cum:+,.2f} |{marker}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 4. Scaling projection
    lines.append("## 4. Scaling Projection")
    lines.append("")
    base_notional = 50000
    lines.append("| Notional | Projected P&L | Projected Avg/Trade | Projected Max DD |")
    lines.append("|----------|---------------|---------------------|------------------|")
    for notional in [50000, 75000, 100000]:
        scale = notional / base_notional
        lines.append(f"| ${notional:,} | ${s['total_pnl'] * scale:,.2f} | "
                     f"${s['avg_pnl'] * scale:,.2f} | ${s['max_drawdown'] * scale:,.2f} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 5. Worst-case analysis
    lines.append("## 5. Worst-Case Analysis")
    lines.append("")
    lines.append(f"- **Max drawdown**: ${s['max_drawdown']:,.2f}")
    lines.append(f"- **Worst single trade**: ${s['worst_trade']:,.2f}")
    lines.append(f"- **Max daily loss**: ${s['max_daily_loss']:,.2f}")

    # Longest losing streak
    daily_sorted = sorted(s["daily_pnl"].items())
    max_streak = 0
    cur_streak = 0
    for _, pnl in daily_sorted:
        if pnl < 0:
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
        else:
            cur_streak = 0
    lines.append(f"- **Longest losing streak**: {max_streak} consecutive days")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Generated by box_optimize.py — STOP here for Cowork + Manny review.*")

    report_path = RESULTS_DIR / "BEST_CONFIG_REPORT.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Report saved: {report_path}", flush=True)


# ── Main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Box Phase 2B Optimization")
    parser.add_argument("--variants-only", action="store_true")
    parser.add_argument("--filters-only", action="store_true")
    args = parser.parse_args()

    candidates = load_all_candidates()
    print(f"Loaded {len(candidates)} candidates", flush=True)

    # ── Part 1: Exit Variants ───────────────────────────────────────

    variant_summaries = []

    if not args.filters_only:
        print("\n" + "=" * 60)
        print("  PART 1: EXIT VARIANT COMPARISON")
        print("=" * 60)

        variants = [
            ("baseline", "A: Baseline"),
            ("vwap", "B: VWAP"),
            ("midbox", "C: Mid-Box"),
            ("tiered", "D: Tiered"),
        ]

        for variant, label in variants:
            out_dir = RESULTS_DIR if variant == "baseline" else RESULTS_DIR / f"variant_{label[0]}_{variant}"
            summary = run_config(candidates, variant, out_dir, label=label)
            variant_summaries.append(summary)

        generate_exit_comparison(variant_summaries)

    # Pick winner: highest avg P&L with WR > 60%
    if variant_summaries:
        viable = [s for s in variant_summaries if s["win_rate"] > 60]
        if not viable:
            viable = variant_summaries
        winner = max(viable, key=lambda s: s["avg_pnl"])
        winning_exit = winner["exit_variant"]
        print(f"\n>>> Winning exit variant: {winner['label']} "
              f"(${winner['avg_pnl']:.2f}/trade, {winner['win_rate']:.1f}% WR)")
    else:
        # Default for filters-only mode
        winning_exit = "midbox"
        print(f"\n>>> Using default exit variant: {winning_exit}")

    # ── Part 2: Filter Sets ─────────────────────────────────────────

    if not args.variants_only:
        print("\n" + "=" * 60)
        print("  PART 2: FILTER SET COMPARISON")
        print(f"  Using exit variant: {winning_exit}")
        print("=" * 60)

        # Run baseline with winning exit (if not already computed)
        baseline_summary = None
        for s in variant_summaries:
            if s["exit_variant"] == winning_exit:
                baseline_summary = s
                baseline_summary["label"] = f"Baseline ({winning_exit})"
                break
        if baseline_summary is None:
            baseline_summary = run_config(
                candidates, winning_exit, RESULTS_DIR,
                label=f"Baseline ({winning_exit})")

        filter_summaries = []
        for fs_name, fs_config in FILTER_SETS.items():
            out_dir = RESULTS_DIR / f"filter_{fs_name}"
            summary = run_config(
                candidates, winning_exit, out_dir,
                filter_set=fs_config,
                label=fs_config["label"])
            filter_summaries.append((fs_name, fs_config, summary))

        generate_filter_comparison(
            [s for _, _, s in filter_summaries],
            baseline_summary)

        # Pick best filter: highest avg P&L with consistency > 55%
        all_configs = [("none", {}, baseline_summary)] + filter_summaries
        viable_filters = [(n, fc, s) for n, fc, s in all_configs
                          if s["total_trades"] >= 10 and s["consistency"] > 50]
        if not viable_filters:
            viable_filters = all_configs

        best_name, best_fc, best_summary = max(
            viable_filters, key=lambda x: x[2]["avg_pnl"])

        print(f"\n>>> Best filter: {best_name} "
              f"(${best_summary['avg_pnl']:.2f}/trade, "
              f"{best_summary['win_rate']:.1f}% WR, "
              f"{best_summary['consistency']:.0f}% consistency)")

        # Part 3: Best config report
        generate_best_config_report(best_summary, winning_exit, best_name, best_fc)

    print("\n" + "=" * 60)
    print("  ALL DONE — STOP for review")
    print("=" * 60)


if __name__ == "__main__":
    main()
