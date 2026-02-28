#!/usr/bin/env python3
"""
Classifier Validation — Phase 2

Runs the StockClassifier against every stock in study_data/ and produces:
  - study_results/classifier_validation.md  (human-readable report)
  - study_results/classifier_validation.csv (per-stock data)
"""

import csv
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path

from classifier import EXIT_PROFILES, StockClassifier

STUDY_DIR = Path("study_data")
OUT_DIR = Path("study_results")


# ── Determine actual best type in hindsight ─────────────────────────

def actual_best_type(data: dict) -> str:
    trades = data.get("trades", [])
    metrics = data.get("stock_metrics", {})
    summary = data.get("summary", {})

    if not trades:
        return "no_trade"

    net_pnl = summary.get("net_pnl", 0)

    # Cascading: multiple winning trades entering higher
    if len(trades) >= 3:
        entries = [t["entry_price"] for t in trades]
        if entries == sorted(entries):
            winning = sum(1 for t in trades if t["pnl"] > 0)
            if winning >= 2:
                return "cascading"

    # One big move: 1-2 trades, big win
    if len(trades) <= 2 and net_pnl > 500:
        max_r = max(t.get("peak_unrealized_r", 0) for t in trades)
        if max_r >= 2.0:
            return "one_big_move"

    # Smooth trend clipped: lots of highs but lost money
    if metrics.get("new_high_count_30m", 0) >= 5 and net_pnl < 0:
        lot = summary.get("total_left_on_table_pct_avg", 0)
        if lot > 70:
            return "smooth_trend_clipped"

    # Choppy
    if metrics.get("pullback_depth_avg_pct", 0) > 8:
        return "choppy"

    # Should have avoided: all losing trades
    if net_pnl < -200 and all(t["pnl"] <= 0 for t in trades):
        return "should_have_avoided"

    return "mixed"


# ── Load all study JSONs ────────────────────────────────────────────

def load_all() -> list[dict]:
    results = []
    for fp in sorted(STUDY_DIR.glob("*.json")):
        with open(fp) as f:
            data = json.load(f)
        data["_path"] = str(fp)
        results.append(data)
    return results


# ── Run validation ──────────────────────────────────────────────────

def run():
    stocks = load_all()
    if not stocks:
        print("No study data found in study_data/")
        return

    classifier = StockClassifier()
    rows: list[dict] = []

    for data in stocks:
        sm = data.get("stock_metrics", {})
        summary = data.get("summary", {})
        trades = data.get("trades", [])
        symbol = data.get("symbol", "???")
        date = data.get("date", "???")

        # Map 30m metric names → classifier names
        metrics = {
            "new_high_count": sm.get("new_high_count_30m", 0),
            "pullback_count": sm.get("pullback_count_30m", 0),
            "pullback_depth_avg_pct": sm.get("pullback_depth_avg_pct", 0),
            "green_bar_ratio": sm.get("green_bar_ratio_30m", 0),
            "max_vwap_distance_pct": sm.get("max_vwap_distance_pct", 0),
            "price_range_pct": sm.get("price_range_30m_pct", 0),
            "vol_total": sm.get("vol_total_30m", 0),
        }

        result = classifier.classify(metrics, minutes=30)
        abt = actual_best_type(data)

        # Count BE/TW exits with R-based suppression analysis
        exit_profile = result.exit_profile
        be_sup_r = exit_profile.get("suppress_be_under_r") or 0
        tw_sup_r = exit_profile.get("suppress_tw_under_r") or 0

        be_exits = [t for t in trades if "bearish_engulfing" in (t.get("exit_reason") or "")]
        tw_exits = [t for t in trades if "topping_wicky" in (t.get("exit_reason") or "")]

        be_count = len(be_exits)
        tw_count = len(tw_exits)
        be_would_suppress = 0
        tw_would_suppress = 0
        be_went_higher = 0
        be_suppress_gain = 0.0
        be_suppress_loss = 0.0
        tw_suppress_gain = 0.0
        tw_suppress_loss = 0.0

        for t in be_exits:
            exit_r = t.get("r_multiple", 0)
            peak_r = t.get("peak_unrealized_r", 0)
            qty = t.get("qty", 0)
            r_val = t.get("r", 0)
            high_after = t.get("high_after_exit_30m")

            if be_sup_r > 0 and exit_r < be_sup_r:
                be_would_suppress += 1
                if high_after and high_after > t["exit_price"]:
                    be_went_higher += 1
                    extra = (high_after - t["exit_price"]) * qty
                    be_suppress_gain += extra
                else:
                    # Would have held into further loss
                    low_after = t.get("low_after_exit_30m")
                    if low_after and low_after < t["exit_price"]:
                        loss = (t["exit_price"] - low_after) * qty
                        be_suppress_loss += loss
            else:
                if high_after and high_after > t["exit_price"]:
                    be_went_higher += 1

        for t in tw_exits:
            exit_r = t.get("r_multiple", 0)
            high_after = t.get("high_after_exit_30m")
            qty = t.get("qty", 0)

            if tw_sup_r > 0 and exit_r < tw_sup_r:
                tw_would_suppress += 1
                if high_after and high_after > t["exit_price"]:
                    tw_suppress_gain += (high_after - t["exit_price"]) * qty
                else:
                    low_after = t.get("low_after_exit_30m")
                    if low_after and low_after < t["exit_price"]:
                        tw_suppress_loss += (t["exit_price"] - low_after) * qty

        row = {
            "symbol": symbol,
            "date": date,
            "actual_pnl": summary.get("net_pnl", 0),
            "total_trades": summary.get("total_trades", 0),
            "win_rate": summary.get("win_rate", 0),
            "classifier_type": result.behavior_type,
            "classifier_confidence": result.confidence,
            "classifier_reasoning": result.reasoning,
            "actual_best_type": abt,
            "match": result.behavior_type == abt
                     or (result.behavior_type == "avoid" and abt == "should_have_avoided")
                     or (result.behavior_type == "avoid" and abt == "no_trade"),
            "be_exits": be_count,
            "be_would_suppress": be_would_suppress,
            "be_went_higher": be_went_higher,
            "be_suppress_gain": round(be_suppress_gain, 2),
            "be_suppress_loss": round(be_suppress_loss, 2),
            "tw_exits": tw_count,
            "tw_would_suppress": tw_would_suppress,
            "tw_suppress_gain": round(tw_suppress_gain, 2),
            "tw_suppress_loss": round(tw_suppress_loss, 2),
            "nh": sm.get("new_high_count_30m", 0),
            "pb": sm.get("pullback_count_30m", 0),
            "vwap_dist": sm.get("max_vwap_distance_pct", 0),
            "range_pct": sm.get("price_range_30m_pct", 0),
            "vol": sm.get("vol_total_30m", 0),
        }
        rows.append(row)

    # ── Write CSV ────────────────────────────────────────────────────
    OUT_DIR.mkdir(exist_ok=True)
    csv_path = OUT_DIR / "classifier_validation.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  CSV: {csv_path}  ({len(rows)} stocks)")

    # ── Generate report ──────────────────────────────────────────────
    report = generate_report(rows)
    md_path = OUT_DIR / "classifier_validation.md"
    with open(md_path, "w") as f:
        f.write(report)
    print(f"  Report: {md_path}")


# ── Report generation ───────────────────────────────────────────────

def generate_report(rows: list[dict]) -> str:
    lines = ["# Classifier Validation Report\n"]
    lines.append(f"**Stocks analyzed**: {len(rows)}\n")

    # ── Classification distribution ──────────────────────────────────
    lines.append("## Classification Distribution\n")
    by_type = defaultdict(list)
    for r in rows:
        by_type[r["classifier_type"]].append(r)

    lines.append("| Type | Count | Avg P&L | Win Rate | Traded? |")
    lines.append("|------|-------|---------|----------|---------|")
    for btype in ["cascading", "one_big_move", "smooth_trend", "early_bird",
                  "choppy", "uncertain", "avoid"]:
        group = by_type.get(btype, [])
        if not group:
            continue
        avg_pnl = statistics.mean([r["actual_pnl"] for r in group])
        traded = [r for r in group if r["total_trades"] > 0]
        avg_wr = statistics.mean([r["win_rate"] for r in traded]) if traded else 0
        would_trade = "YES" if btype != "avoid" else "NO"
        lines.append(
            f"| {btype} | {len(group)} | ${avg_pnl:+,.0f} | "
            f"{avg_wr:.0f}% | {would_trade} |"
        )
    lines.append("")

    # ── Gate effectiveness ───────────────────────────────────────────
    lines.append("## Gate Effectiveness\n")
    avoided = by_type.get("avoid", [])
    passed = [r for r in rows if r["classifier_type"] != "avoid"]
    lines.append(f"- Stocks classified **AVOID**: {len(avoided)}")
    if avoided:
        avg_avoid = statistics.mean([r["actual_pnl"] for r in avoided])
        lines.append(f"- Their actual avg P&L: **${avg_avoid:+,.0f}** "
                      f"({'confirms gate works' if avg_avoid < 0 else 'gate may be too aggressive'})")
    lines.append(f"- Stocks that **PASSED** the gate: {len(passed)}")
    if passed:
        avg_pass = statistics.mean([r["actual_pnl"] for r in passed])
        lines.append(f"- Their actual avg P&L: **${avg_pass:+,.0f}**")
    lines.append("")

    # ── P&L saved by gate ────────────────────────────────────────────
    lines.append("## P&L Saved by Gate\n")
    avoided_with_trades = [r for r in avoided if r["total_trades"] > 0]
    if avoided_with_trades:
        total_saved = sum(r["actual_pnl"] for r in avoided_with_trades
                          if r["actual_pnl"] < 0)
        lines.append(f"- Stocks the gate would skip that had trades: "
                      f"{len(avoided_with_trades)}")
        lines.append(f"- Losses that would be avoided: **${abs(total_saved):,.0f}**")
        losers = [r for r in avoided_with_trades if r["actual_pnl"] < 0]
        winners = [r for r in avoided_with_trades if r["actual_pnl"] > 0]
        lines.append(f"- Losers in avoided group: {len(losers)}")
        lines.append(f"- Winners in avoided group: {len(winners)} "
                      f"(would be false positives)")
        if winners:
            missed = sum(r["actual_pnl"] for r in winners)
            lines.append(f"- Profits that would be missed: **${missed:+,.0f}**")
            lines.append(f"- Net savings: **${abs(total_saved) - missed:+,.0f}**")
    else:
        lines.append("- No avoided stocks had trades (all were skipped anyway)\n")
    lines.append("")

    # ── Exit suppression hypothetical (BE + TW) ─────────────────────
    lines.append("## Exit Suppression Hypothetical\n")
    lines.append("For each type, what if BE/TW exits below the profile's R threshold had been suppressed?\n")

    for btype in ["one_big_move", "smooth_trend", "early_bird", "cascading"]:
        group = by_type.get(btype, [])
        if not group:
            continue
        profile = EXIT_PROFILES[btype]
        be_sup = profile.get("suppress_be_under_r", 0)
        tw_sup = profile.get("suppress_tw_under_r", 0)

        total_be = sum(r["be_exits"] for r in group)
        total_tw = sum(r["tw_exits"] for r in group)
        be_would = sum(r["be_would_suppress"] for r in group)
        tw_would = sum(r["tw_would_suppress"] for r in group)
        be_higher = sum(r["be_went_higher"] for r in group)
        be_gain = sum(r["be_suppress_gain"] for r in group)
        be_loss = sum(r["be_suppress_loss"] for r in group)
        tw_gain = sum(r["tw_suppress_gain"] for r in group)
        tw_loss = sum(r["tw_suppress_loss"] for r in group)
        net = (be_gain - be_loss) + (tw_gain - tw_loss)

        lines.append(f"### {btype} (BE < {be_sup}R, TW < {tw_sup}R)")
        lines.append(f"- Stocks: {len(group)}")
        lines.append(f"- **BE exits**: {total_be} total, **{be_would} would be suppressed**")
        if be_would > 0:
            lines.append(f"  - Of suppressed: {be_higher} stock went higher afterward")
            lines.append(f"  - Hypothetical gain: **${be_gain:+,.0f}** / loss: **${-be_loss:,.0f}**")
        lines.append(f"- **TW exits**: {total_tw} total, **{tw_would} would be suppressed**")
        if tw_would > 0:
            lines.append(f"  - Hypothetical gain: **${tw_gain:+,.0f}** / loss: **${-tw_loss:,.0f}**")
        lines.append(f"- **Net impact**: **${net:+,.0f}**")
        lines.append("")

    # ── Actual best type distribution ────────────────────────────────
    lines.append("## Actual Best Type (Hindsight)\n")
    by_actual = defaultdict(list)
    for r in rows:
        by_actual[r["actual_best_type"]].append(r)

    lines.append("| Actual Type | Count | Avg P&L |")
    lines.append("|-------------|-------|---------|")
    for atype in sorted(by_actual.keys()):
        group = by_actual[atype]
        avg = statistics.mean([r["actual_pnl"] for r in group])
        lines.append(f"| {atype} | {len(group)} | ${avg:+,.0f} |")
    lines.append("")

    # ── Confusion matrix ─────────────────────────────────────────────
    lines.append("## Confusion Matrix: Classified vs Actual\n")
    class_types = sorted(set(r["classifier_type"] for r in rows))
    actual_types = sorted(set(r["actual_best_type"] for r in rows))

    header = "| Classified \\ Actual | " + " | ".join(actual_types) + " |"
    sep = "|" + "---|" * (len(actual_types) + 1)
    lines.append(header)
    lines.append(sep)
    for ct in class_types:
        cells = []
        for at in actual_types:
            n = sum(1 for r in rows
                    if r["classifier_type"] == ct and r["actual_best_type"] == at)
            cells.append(str(n) if n > 0 else "-")
        lines.append(f"| {ct} | " + " | ".join(cells) + " |")
    lines.append("")

    # ── Misclassifications ───────────────────────────────────────────
    lines.append("## Notable Misclassifications\n")
    lines.append("Stocks where classifier would have made things WORSE:\n")

    for r in sorted(rows, key=lambda x: x["actual_pnl"], reverse=True):
        # Winners classified as avoid = false positive
        if r["classifier_type"] == "avoid" and r["actual_pnl"] > 200:
            lines.append(
                f"- **{r['symbol']} {r['date']}**: P&L ${r['actual_pnl']:+,.0f} "
                f"but classified AVOID "
                f"(VWAP={r['vwap_dist']:.1f}%, NH={r['nh']}, "
                f"range={r['range_pct']:.1f}%)"
            )
    lines.append("")

    # ── Top performers per type ──────────────────────────────────────
    lines.append("## Top Performers by Classified Type\n")
    for btype in ["cascading", "one_big_move", "smooth_trend", "early_bird"]:
        group = sorted(by_type.get(btype, []),
                       key=lambda x: x["actual_pnl"], reverse=True)
        if not group:
            continue
        lines.append(f"### {btype}")
        for r in group[:5]:
            lines.append(
                f"- {r['symbol']} {r['date']}: ${r['actual_pnl']:+,.0f} "
                f"(NH={r['nh']}, VWAP={r['vwap_dist']:.1f}%, "
                f"range={r['range_pct']:.1f}%)"
            )
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    run()
