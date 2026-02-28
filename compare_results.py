#!/usr/bin/env python3
"""
Compare study results: baseline vs classifier (gate only) vs classifier+suppress.
Reads from:
  - study_data/                (baseline / gate-only — identical P&L)
  - study_data_suppress/       (classifier ON, suppression ON)
Produces study_results_suppress/comparison_report.md
"""

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

BASELINE_DIR = Path("study_data_classifier")  # Phase 2.1 data (gate only, no suppression)
SUPPRESS_DIR = Path("study_data_suppress")    # Phase 2.2 data (gate + suppression)
OUT_DIR = Path("study_results_suppress")


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
    suppress = load_dir(SUPPRESS_DIR)

    if not baseline:
        print("No baseline data in study_data/")
        return
    if not suppress:
        print("No suppress data in study_data_suppress/")
        print("Run: WB_CLASSIFIER_SUPPRESS_ENABLED=1 STUDY_OUTPUT_DIR=study_data_suppress bash run_study_classifier.sh")
        return

    OUT_DIR.mkdir(exist_ok=True)

    all_keys = sorted(set(baseline.keys()) | set(suppress.keys()))
    rows = []

    for key in all_keys:
        b = baseline.get(key)
        s = suppress.get(key)

        if not b:
            continue

        b_pnl = get_pnl(b)
        b_trades = get_trades(b)
        b_type = get_classifier_type(b)

        if s:
            s_pnl = get_pnl(s)
            s_trades = get_trades(s)
            s_type = get_classifier_type(s)
            diff = s_pnl - b_pnl
        else:
            s_pnl = None
            s_trades = None
            s_type = "not_run"
            diff = None

        symbol = b.get("symbol", key.split("_")[0])
        date = b.get("date", key.split("_")[-1])
        month = date[:7] if date else "unknown"

        avoided = b_type == "avoid" or s_type == "avoid"

        rows.append({
            "key": key,
            "symbol": symbol,
            "date": date,
            "month": month,
            "baseline_pnl": b_pnl,
            "baseline_trades": b_trades,
            "baseline_type": b_type,
            "suppress_pnl": s_pnl,
            "suppress_trades": s_trades,
            "suppress_type": s_type,
            "diff": diff,
            "avoided": avoided,
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
    lines = ["# Phase 2.2 Comparison: Baseline vs Classifier+Suppression\n"]

    matched = [r for r in rows if r["suppress_pnl"] is not None]
    unmatched = [r for r in rows if r["suppress_pnl"] is None]

    avoided = [r for r in matched if r["avoided"]]
    traded = [r for r in matched if not r["avoided"]]

    b_total = sum(r["baseline_pnl"] for r in matched)
    s_total = sum(r["suppress_pnl"] for r in matched)
    improvement = s_total - b_total

    b_traded_total = sum(r["baseline_pnl"] for r in traded)
    s_traded_total = sum(r["suppress_pnl"] for r in traded)

    # Summary table
    lines.append("## Summary\n")
    lines.append("| Config | Stocks Traded | Total P&L | Avg P&L/Stock |")
    lines.append("|--------|--------------|-----------|---------------|")
    lines.append(f"| Baseline (OFF) | {len(matched)} | ${b_total:+,.0f} | "
                 f"${b_total / len(matched):+,.0f} |")
    lines.append(f"| Classifier (gate only) | {len(traded)} | ${b_traded_total:+,.0f} | "
                 f"${b_traded_total / len(traded):+,.0f} |" if traded else "| Classifier (gate only) | 0 | $0 | $0 |")
    lines.append(f"| **Classifier+Suppress** | **{len(traded)}** | **${s_traded_total:+,.0f}** | "
                 f"**${s_traded_total / len(traded):+,.0f}** |" if traded else "| Classifier+Suppress | 0 | $0 | $0 |")
    lines.append(f"\n- Gate avoided: {len(avoided)} stocks")
    lines.append(f"- Suppression impact: **${s_traded_total - b_traded_total:+,.0f}** on traded stocks")
    if unmatched:
        lines.append(f"- Stocks in baseline but not in suppress run: {len(unmatched)}")
    lines.append("")

    # Avoided stocks (same as before)
    lines.append("## Stocks the Classifier AVOIDED (Gate)\n")
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

    # Exit suppression impact — stocks where P&L changed
    lines.append("## Exit Suppression Impact\n")
    changed = [r for r in traded if r["diff"] and abs(r["diff"]) > 1]
    if changed:
        lines.append("| Symbol | Date | Type | Baseline P&L | Suppress P&L | Delta |")
        lines.append("|--------|------|------|-------------|-------------|-------|")
        for r in sorted(changed, key=lambda x: x["diff"], reverse=True):
            lines.append(
                f"| {r['symbol']} | {r['date']} | {r['suppress_type']} | "
                f"${r['baseline_pnl']:+,.0f} | ${r['suppress_pnl']:+,.0f} | "
                f"${r['diff']:+,.0f} |"
            )
        total_delta = sum(r["diff"] for r in changed)
        winners = [r for r in changed if r["diff"] > 0]
        losers = [r for r in changed if r["diff"] < 0]
        lines.append(f"\n- Stocks improved: **{len(winners)}** (${sum(r['diff'] for r in winners):+,.0f})")
        lines.append(f"- Stocks regressed: **{len(losers)}** (${sum(r['diff'] for r in losers):+,.0f})")
        lines.append(f"- Net suppression value: **${total_delta:+,.0f}**")
    else:
        lines.append("No stocks changed — suppression had no effect on P&L.")
    lines.append("")

    # Regression check
    lines.append("## Regression Check\n")
    regressions = [r for r in traded if r["diff"] and r["diff"] < -10]
    if regressions:
        lines.append("Stocks where classifier+suppress P&L DECREASED vs baseline:\n")
        lines.append("| Symbol | Date | Type | Baseline | Suppress | Regression |")
        lines.append("|--------|------|------|----------|----------|------------|")
        for r in sorted(regressions, key=lambda x: x["diff"]):
            lines.append(
                f"| {r['symbol']} | {r['date']} | {r['suppress_type']} | "
                f"${r['baseline_pnl']:+,.0f} | ${r['suppress_pnl']:+,.0f} | "
                f"${r['diff']:+,.0f} |"
            )
    else:
        lines.append("None — no regressions!")
    lines.append("")

    # Per-type summary
    lines.append("## Per-Type Impact\n")
    by_type = defaultdict(list)
    for r in matched:
        by_type[r["suppress_type"]].append(r)

    lines.append("| Type | Stocks | Baseline Avg | Suppress Avg | Delta |")
    lines.append("|------|--------|-------------|-------------|-------|")
    for btype in ["cascading", "one_big_move", "smooth_trend", "early_bird",
                  "choppy", "uncertain", "avoid"]:
        group = by_type.get(btype, [])
        if not group:
            continue
        avg_b = statistics.mean([r["baseline_pnl"] for r in group])
        avg_s_vals = [r["suppress_pnl"] for r in group if r["suppress_pnl"] is not None]
        avg_s = statistics.mean(avg_s_vals) if avg_s_vals else 0
        change = avg_s - avg_b
        lines.append(
            f"| {btype} | {len(group)} | ${avg_b:+,.0f} | "
            f"${avg_s:+,.0f} | ${change:+,.0f} |"
        )
    lines.append("")

    # Hot vs cold market
    lines.append("## Hot vs Cold Market\n")
    by_month = defaultdict(list)
    for r in matched:
        by_month[r["month"]].append(r)

    lines.append("| Month | Stocks | Baseline | Gate Only | Gate+Suppress |")
    lines.append("|-------|--------|----------|----------|---------------|")
    for month in sorted(by_month.keys()):
        group = by_month[month]
        b_sum = sum(r["baseline_pnl"] for r in group)
        # Gate-only = baseline for traded + $0 for avoided
        gate_sum = sum(r["baseline_pnl"] for r in group if not r["avoided"])
        s_sum = sum(r["suppress_pnl"] for r in group if r["suppress_pnl"] is not None)
        lines.append(
            f"| {month} | {len(group)} | ${b_sum:+,.0f} | "
            f"${gate_sum:+,.0f} | ${s_sum:+,.0f} |"
        )
    lines.append("")

    # Today's session (Feb 27)
    feb27 = [r for r in matched if r["date"] == "2026-02-27"]
    if feb27:
        lines.append("## Today's Session (2026-02-27)\n")
        lines.append("| Symbol | Type | Baseline P&L | Suppress P&L | Delta |")
        lines.append("|--------|------|-------------|-------------|-------|")
        for r in sorted(feb27, key=lambda x: x["baseline_pnl"], reverse=True):
            delta = r["diff"] if r["diff"] else 0
            lines.append(
                f"| {r['symbol']} | {r['suppress_type']} | "
                f"${r['baseline_pnl']:+,.0f} | "
                f"${r['suppress_pnl']:+,.0f} | "
                f"${delta:+,.0f} |"
            )
        b27_total = sum(r["baseline_pnl"] for r in feb27)
        s27_total = sum(r["suppress_pnl"] for r in feb27 if r["suppress_pnl"] is not None)
        traded27 = [r for r in feb27 if not r["avoided"]]
        avoided27 = [r for r in feb27 if r["avoided"]]
        lines.append(f"\n- Stocks traded: {len(traded27)}, avoided: {len(avoided27)}")
        lines.append(f"- Baseline total: ${b27_total:+,.0f}")
        lines.append(f"- Suppress total: ${s27_total:+,.0f}")
        lines.append(f"- Delta: ${s27_total - b27_total:+,.0f}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    run()
