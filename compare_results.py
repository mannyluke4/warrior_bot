#!/usr/bin/env python3
"""
Compare study results: baseline (classifier OFF) vs tuned (classifier ON).
Reads from study_data/ (baseline) and study_data_classifier/ (classifier ON).
Produces study_results_classifier/comparison_report.md
"""

import csv
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path

BASELINE_DIR = Path("study_data")
CLASSIFIER_DIR = Path("study_data_classifier")
OUT_DIR = Path("study_results_classifier")


def load_dir(d: Path) -> dict[str, dict]:
    """Load all JSONs from a directory, keyed by 'SYMBOL_DATE'."""
    result = {}
    for fp in sorted(d.glob("*.json")):
        with open(fp) as f:
            data = json.load(f)
        key = f"{data['symbol']}_{data['date']}"
        result[key] = data
    return result


def get_pnl(data: dict) -> float:
    return data.get("summary", {}).get("net_pnl", 0)


def get_trades(data: dict) -> int:
    return data.get("summary", {}).get("total_trades", 0)


def get_classifier_type(data: dict) -> str:
    clf = data.get("config", {}).get("classifier", {})
    return clf.get("behavior_type", "none")


def run():
    baseline = load_dir(BASELINE_DIR)
    classifier = load_dir(CLASSIFIER_DIR)

    if not baseline:
        print("No baseline data in study_data/")
        return
    if not classifier:
        print("No classifier data in study_data_classifier/")
        print("Run: bash run_study_classifier.sh")
        return

    OUT_DIR.mkdir(exist_ok=True)

    # Match stocks present in both
    all_keys = sorted(set(baseline.keys()) | set(classifier.keys()))
    rows = []

    for key in all_keys:
        b = baseline.get(key)
        c = classifier.get(key)

        if not b:
            continue  # Skip if no baseline

        b_pnl = get_pnl(b)
        b_trades = get_trades(b)

        if c:
            c_pnl = get_pnl(c)
            c_trades = get_trades(c)
            c_type = get_classifier_type(c)
            diff = c_pnl - b_pnl
        else:
            c_pnl = None
            c_trades = None
            c_type = "not_run"
            diff = None

        symbol = b.get("symbol", key.split("_")[0])
        date = b.get("date", key.split("_")[-1])

        # Determine month for hot/cold market split
        month = date[:7] if date else "unknown"

        rows.append({
            "key": key,
            "symbol": symbol,
            "date": date,
            "month": month,
            "baseline_pnl": b_pnl,
            "baseline_trades": b_trades,
            "classifier_pnl": c_pnl,
            "classifier_trades": c_trades,
            "classifier_type": c_type,
            "diff": diff,
            "avoided": c_type == "avoid" if c else False,
        })

    # Write CSV
    csv_path = OUT_DIR / "comparison.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  CSV: {csv_path}  ({len(rows)} stocks)")

    # Generate report
    report = generate_report(rows)
    md_path = OUT_DIR / "comparison_report.md"
    with open(md_path, "w") as f:
        f.write(report)
    print(f"  Report: {md_path}")


def generate_report(rows: list[dict]) -> str:
    lines = ["# Baseline vs Classifier Comparison\n"]

    # Only rows where classifier was run
    matched = [r for r in rows if r["classifier_pnl"] is not None]
    unmatched = [r for r in rows if r["classifier_pnl"] is None]

    b_total = sum(r["baseline_pnl"] for r in matched)
    c_total = sum(r["classifier_pnl"] for r in matched)
    improvement = c_total - b_total
    pct = (improvement / abs(b_total) * 100) if b_total != 0 else 0

    avoided = [r for r in matched if r["avoided"]]
    traded = [r for r in matched if not r["avoided"]]

    lines.append("## Summary\n")
    lines.append(f"- **Baseline total P&L**: ${b_total:+,.0f} ({len(matched)} stocks)")
    lines.append(f"- **Classifier total P&L**: ${c_total:+,.0f} "
                 f"({len(traded)} traded, {len(avoided)} avoided)")
    lines.append(f"- **Improvement**: ${improvement:+,.0f} ({pct:+.1f}%)")
    if unmatched:
        lines.append(f"- Stocks in baseline but not in classifier run: {len(unmatched)}")
    lines.append("")

    # Avoided stocks
    lines.append("## Stocks the Classifier AVOIDED\n")
    if avoided:
        lines.append("| Symbol | Date | Baseline P&L | Saved? |")
        lines.append("|--------|------|-------------|--------|")
        for r in sorted(avoided, key=lambda x: x["baseline_pnl"]):
            saved = "YES" if r["baseline_pnl"] <= 0 else "NO (false positive)"
            lines.append(f"| {r['symbol']} | {r['date']} | "
                         f"${r['baseline_pnl']:+,.0f} | {saved} |")
        total_saved = sum(r["baseline_pnl"] for r in avoided if r["baseline_pnl"] < 0)
        total_missed = sum(r["baseline_pnl"] for r in avoided if r["baseline_pnl"] > 0)
        lines.append(f"\n- Losses avoided: **${abs(total_saved):,.0f}**")
        lines.append(f"- Profits missed: **${total_missed:+,.0f}**")
        lines.append(f"- Net gate value: **${abs(total_saved) - total_missed:+,.0f}**")
    else:
        lines.append("None — classifier traded all stocks.")
    lines.append("")

    # Improved stocks
    improved = [r for r in traded if r["diff"] and r["diff"] > 10]
    lines.append("## Stocks Where Classifier IMPROVED P&L\n")
    if improved:
        lines.append("| Symbol | Date | Baseline | Classifier | Improvement | Type |")
        lines.append("|--------|------|----------|-----------|-------------|------|")
        for r in sorted(improved, key=lambda x: x["diff"], reverse=True):
            lines.append(
                f"| {r['symbol']} | {r['date']} | ${r['baseline_pnl']:+,.0f} | "
                f"${r['classifier_pnl']:+,.0f} | ${r['diff']:+,.0f} | {r['classifier_type']} |"
            )
    else:
        lines.append("None.")
    lines.append("")

    # Hurt stocks
    hurt = [r for r in traded if r["diff"] and r["diff"] < -10]
    lines.append("## Stocks Where Classifier HURT P&L\n")
    if hurt:
        lines.append("| Symbol | Date | Baseline | Classifier | Regression | Type |")
        lines.append("|--------|------|----------|-----------|------------|------|")
        for r in sorted(hurt, key=lambda x: x["diff"]):
            lines.append(
                f"| {r['symbol']} | {r['date']} | ${r['baseline_pnl']:+,.0f} | "
                f"${r['classifier_pnl']:+,.0f} | ${r['diff']:+,.0f} | {r['classifier_type']} |"
            )
    else:
        lines.append("None — no regressions!")
    lines.append("")

    # Per-type summary
    lines.append("## Per-Type Summary\n")
    by_type = defaultdict(list)
    for r in matched:
        by_type[r["classifier_type"]].append(r)

    lines.append("| Type | Count | Avg Baseline P&L | Avg Classifier P&L | Change |")
    lines.append("|------|-------|-----------------|-------------------|--------|")
    for btype in ["cascading", "one_big_move", "smooth_trend", "early_bird",
                  "choppy", "uncertain", "avoid"]:
        group = by_type.get(btype, [])
        if not group:
            continue
        avg_b = statistics.mean([r["baseline_pnl"] for r in group])
        avg_c_vals = [r["classifier_pnl"] for r in group if r["classifier_pnl"] is not None]
        avg_c = statistics.mean(avg_c_vals) if avg_c_vals else 0
        change = avg_c - avg_b
        lines.append(
            f"| {btype} | {len(group)} | ${avg_b:+,.0f} | "
            f"${avg_c:+,.0f} | ${change:+,.0f} |"
        )
    lines.append("")

    # Hot vs cold market
    lines.append("## Hot vs Cold Market\n")
    by_month = defaultdict(list)
    for r in matched:
        by_month[r["month"]].append(r)

    lines.append("| Month | Stocks | Baseline Total | Classifier Total | Change |")
    lines.append("|-------|--------|---------------|-----------------|--------|")
    for month in sorted(by_month.keys()):
        group = by_month[month]
        b_sum = sum(r["baseline_pnl"] for r in group)
        c_sum = sum(r["classifier_pnl"] for r in group if r["classifier_pnl"] is not None)
        lines.append(
            f"| {month} | {len(group)} | ${b_sum:+,.0f} | "
            f"${c_sum:+,.0f} | ${c_sum - b_sum:+,.0f} |"
        )
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    run()
