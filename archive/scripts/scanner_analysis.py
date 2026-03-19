#!/usr/bin/env python3
"""
Scanner Analysis — Aggregates simulate.py results from scanner backtest
into a markdown report with per-profile and per-day breakdowns.

Usage:
    python scanner_analysis.py
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict

SCANNER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_results")
DATES = ["2026-01-13", "2026-01-15", "2026-02-10", "2026-02-12", "2026-03-04"]


def parse_sim_output(filepath: str) -> dict:
    """Parse a simulate.py output file to extract trade metrics."""
    result = {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "pnl": 0.0,
        "win_rate": 0.0,
    }

    if not os.path.exists(filepath):
        return result

    with open(filepath) as f:
        content = f.read()

    # Parse summary section: "Trades: N  |  Wins: N  |  Losses: N  |  Win Rate: N%"
    trades_match = re.search(r"Trades:\s+(\d+)\s+\|\s+Wins:\s+(\d+)\s+\|\s+Losses:\s+(\d+)\s+\|\s+Win Rate:\s+([\d.]+)%", content)
    if trades_match:
        result["trades"] = int(trades_match.group(1))
        result["wins"] = int(trades_match.group(2))
        result["losses"] = int(trades_match.group(3))
        result["win_rate"] = float(trades_match.group(4))

    # Parse "Gross P&L: $+N,NNN" or "Gross P&L: $-N,NNN"
    pnl_match = re.search(r"Gross P&L:\s+\$([\+\-]?[\d,]+)", content)
    if pnl_match:
        pnl_str = pnl_match.group(1).replace(",", "")
        result["pnl"] = float(pnl_str)

    return result


def generate_report():
    print(f"\n{'=' * 60}")
    print(f"  SCANNER BACKTEST ANALYSIS")
    print(f"{'=' * 60}")

    # Collect all results
    all_results = []  # list of dicts with date, symbol, profile, sim metrics

    for date in DATES:
        json_path = os.path.join(SCANNER_DIR, f"{date}.json")
        if not os.path.exists(json_path):
            print(f"  WARNING: {json_path} not found, skipping")
            continue

        with open(json_path) as f:
            candidates = json.load(f)

        for c in candidates:
            sym = c["symbol"]
            profile = c["profile"]
            sim_file = os.path.join(SCANNER_DIR, f"{date}_{sym}.txt")
            metrics = parse_sim_output(sim_file)

            all_results.append({
                "date": date,
                "symbol": sym,
                "profile": profile,
                "gap_pct": c.get("gap_pct", 0),
                "pm_price": c.get("pm_price", 0),
                "float_millions": c.get("float_millions"),
                "sim_start": c.get("sim_start", "07:00"),
                **metrics,
            })

    if not all_results:
        print("  No results found!")
        return

    # Aggregate by profile
    profile_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "stocks": 0})
    for r in all_results:
        p = r["profile"]
        profile_stats[p]["stocks"] += 1
        profile_stats[p]["trades"] += r["trades"]
        profile_stats[p]["wins"] += r["wins"]
        profile_stats[p]["losses"] += r["losses"]
        profile_stats[p]["pnl"] += r["pnl"]

    # Aggregate by date
    date_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "stocks": 0})
    for r in all_results:
        d = r["date"]
        date_stats[d]["stocks"] += 1
        date_stats[d]["trades"] += r["trades"]
        date_stats[d]["wins"] += r["wins"]
        date_stats[d]["losses"] += r["losses"]
        date_stats[d]["pnl"] += r["pnl"]

    # Grand totals
    total_stocks = len(all_results)
    total_trades = sum(r["trades"] for r in all_results)
    total_wins = sum(r["wins"] for r in all_results)
    total_losses = sum(r["losses"] for r in all_results)
    total_pnl = sum(r["pnl"] for r in all_results)
    total_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0

    # Build report
    lines = []
    lines.append("# Scanner Backtest Report")
    lines.append("")
    lines.append(f"**Dates tested:** {', '.join(DATES)}")
    lines.append(f"**Total candidates scanned:** {total_stocks}")
    lines.append(f"**Total trades:** {total_trades}")
    lines.append(f"**Overall P&L:** ${total_pnl:+,.0f}")
    lines.append(f"**Win Rate:** {total_wr:.1f}% ({total_wins}W / {total_losses}L)")
    lines.append("")

    # Profile breakdown
    lines.append("## P&L by Profile")
    lines.append("")
    lines.append("| Profile | Stocks | Trades | Wins | Losses | Win Rate | P&L |")
    lines.append("|---------|--------|--------|------|--------|----------|-----|")
    for p in sorted(profile_stats.keys()):
        s = profile_stats[p]
        wr = (s["wins"] / s["trades"] * 100) if s["trades"] > 0 else 0
        lines.append(
            f"| {p} | {s['stocks']} | {s['trades']} | {s['wins']} | {s['losses']} "
            f"| {wr:.1f}% | ${s['pnl']:+,.0f} |"
        )
    lines.append("")

    # Per-day breakdown
    lines.append("## P&L by Date")
    lines.append("")
    lines.append("| Date | Stocks | Trades | Wins | Losses | Win Rate | P&L |")
    lines.append("|------|--------|--------|------|--------|----------|-----|")
    for d in DATES:
        if d in date_stats:
            s = date_stats[d]
            wr = (s["wins"] / s["trades"] * 100) if s["trades"] > 0 else 0
            lines.append(
                f"| {d} | {s['stocks']} | {s['trades']} | {s['wins']} | {s['losses']} "
                f"| {wr:.1f}% | ${s['pnl']:+,.0f} |"
            )
    lines.append("")

    # Per-stock detail table
    lines.append("## Per-Stock Detail")
    lines.append("")
    lines.append("| Date | Symbol | Profile | Gap% | Price | Float | Trades | P&L |")
    lines.append("|------|--------|---------|------|-------|-------|--------|-----|")
    for r in sorted(all_results, key=lambda x: (x["date"], x["symbol"])):
        float_str = f"{r['float_millions']}M" if r['float_millions'] else "N/A"
        lines.append(
            f"| {r['date']} | {r['symbol']} | {r['profile']} | {r['gap_pct']:+.1f}% "
            f"| ${r['pm_price']:.2f} | {float_str} | {r['trades']} | ${r['pnl']:+,.0f} |"
        )
    lines.append("")

    report = "\n".join(lines)

    report_path = os.path.join(SCANNER_DIR, "SCANNER_BACKTEST_REPORT.md")
    with open(report_path, "w") as f:
        f.write(report)

    print(f"\n  Report saved: {report_path}")
    print(f"  {total_stocks} stocks, {total_trades} trades, ${total_pnl:+,.0f} total P&L")
    print()


if __name__ == "__main__":
    generate_report()
