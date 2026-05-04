"""wave_analysis.py — Read the census/waves/trades CSVs and emit the
quantitative facts that go into Section A-D of the analysis report.

Pure analysis — no detector or simulator changes. Outputs a dict-of-dicts
to stdout (and writes a JSON file `wave_research/ytd_summary.json`).
"""

from __future__ import annotations

import csv
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WR = os.path.join(REPO, "wave_research")


def read_csv(path: str) -> List[dict]:
    with open(path) as f:
        return list(csv.DictReader(f))


def num(v, default=0.0, *, t=float):
    try:
        if v == "" or v is None:
            return default
        return t(v)
    except Exception:
        return default


def section_a_frequency(census: List[dict], waves: List[dict]) -> dict:
    """Wave frequency, magnitude distribution, time-of-day buckets."""
    if not census:
        return {}

    # Per (sym, date) waves count
    waves_per_cell = [int(c.get("total_waves") or 0) for c in census]
    nz = [n for n in waves_per_cell if n > 0]
    cells_with_waves = len(nz)

    # Magnitude distribution (over ALL waves, both directions)
    mags = [num(w.get("magnitude_pct")) for w in waves if w.get("magnitude_pct")]
    mag_buckets = Counter()
    for m in mags:
        if m < 1.0:
            mag_buckets["<1%"] += 1
        elif m < 2.0:
            mag_buckets["1-2%"] += 1
        elif m < 3.0:
            mag_buckets["2-3%"] += 1
        elif m < 5.0:
            mag_buckets["3-5%"] += 1
        elif m < 10.0:
            mag_buckets["5-10%"] += 1
        else:
            mag_buckets[">10%"] += 1

    # Time-of-day distribution from census aggregates
    tod = {
        "premarket (4-9:30)": sum(int(c.get("waves_premarket") or 0) for c in census),
        "morning (9:30-12)":  sum(int(c.get("waves_morning") or 0) for c in census),
        "midday (12-15)":     sum(int(c.get("waves_midday") or 0) for c in census),
        "close (15-16)":      sum(int(c.get("waves_close") or 0) for c in census),
        "afterhours (16-20)": sum(int(c.get("waves_afterhours") or 0) for c in census),
    }

    # Cells with score-≥7 setups
    cells_with_setups = sum(1 for c in census if int(c.get("setups_score_ge_7") or 0) > 0)

    # Watchlist coverage: % of (sym, date) cells that produced ≥1 wave
    pct_with_waves = cells_with_waves / len(census) * 100.0

    return {
        "n_cells": len(census),
        "cells_with_any_wave": cells_with_waves,
        "pct_cells_with_waves": round(pct_with_waves, 1),
        "cells_with_setup_ge_7": cells_with_setups,
        "pct_cells_with_setup": round(cells_with_setups / len(census) * 100.0, 1),
        "total_waves": len(waves),
        "avg_waves_per_active_cell": round(statistics.mean(nz), 2) if nz else 0,
        "median_waves_per_active_cell": int(statistics.median(nz)) if nz else 0,
        "max_waves_in_one_cell": max(nz) if nz else 0,
        "magnitude_distribution_pct": dict(mag_buckets),
        "time_of_day_buckets": tod,
        "median_wave_magnitude_pct": round(statistics.median(mags), 3) if mags else 0,
        "p25_wave_magnitude_pct": round(statistics.quantiles(mags, n=4)[0], 3) if len(mags) >= 4 else 0,
        "p75_wave_magnitude_pct": round(statistics.quantiles(mags, n=4)[2], 3) if len(mags) >= 4 else 0,
    }


def section_b_pattern_match(waves: List[dict]) -> dict:
    """Pattern match rate, criteria-level predictive value."""
    # Only score down-waves get a numeric score (longs are taken on bounce
    # bars after down waves).
    down = [w for w in waves if w.get("direction") == "down" and w.get("score") not in ("", None)]
    n_down = len(down)
    if n_down == 0:
        return {}

    scores = [int(num(w.get("score"), t=float)) for w in down]
    score_dist = Counter(scores)

    score_ge_7 = sum(1 for s in scores if s >= 7)
    score_ge_8 = sum(1 for s in scores if s >= 8)
    score_ge_9 = sum(1 for s in scores if s >= 9)
    score_ge_10 = sum(1 for s in scores if s >= 10)

    # Criterion hit rate at score ≥ 7 vs all
    criteria_keys = [
        "score_has_prior_waves", "score_near_recent_low", "score_macd_rising",
        "score_higher_low", "score_volume_confirm", "score_green_bounce",
        "score_minimal_upper_wick",
    ]
    crit_all = {k: 0 for k in criteria_keys}
    crit_top = {k: 0 for k in criteria_keys}
    n_top = 0
    for w in down:
        s = int(num(w.get("score"), t=float))
        for k in criteria_keys:
            v = num(w.get(k), t=float)
            if v == 1:
                crit_all[k] += 1
                if s >= 7:
                    crit_top[k] += 1
        if s >= 7:
            n_top += 1

    return {
        "n_down_waves_scored": n_down,
        "score_ge_7": score_ge_7,
        "pct_score_ge_7": round(score_ge_7 / n_down * 100.0, 2),
        "score_ge_8": score_ge_8,
        "score_ge_9": score_ge_9,
        "score_ge_10": score_ge_10,
        "score_distribution": {str(k): v for k, v in sorted(score_dist.items())},
        "criterion_hit_rate_all_pct": {
            k: round(crit_all[k] / n_down * 100.0, 1) for k in criteria_keys
        },
        "criterion_hit_rate_top_pct": {
            k: round(crit_top[k] / max(n_top, 1) * 100.0, 1) for k in criteria_keys
        },
    }


def section_c_performance(trades: List[dict]) -> dict:
    """Hypothetical performance: WR, profit factor, drawdown, distribution."""
    if not trades:
        return {}

    pnls = [num(t.get("pnl")) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    n = len(pnls)
    n_wins = len(wins)
    n_losses = len(losses)

    total = sum(pnls)
    gross_w = sum(wins)
    gross_l = abs(sum(losses))
    pf = gross_w / gross_l if gross_l > 0 else float("inf")

    avg_win = statistics.mean(wins) if wins else 0
    avg_loss = statistics.mean(losses) if losses else 0
    median_win = statistics.median(wins) if wins else 0
    median_loss = statistics.median(losses) if losses else 0

    # Max drawdown — running cumulative PnL through the trade timeline.
    # Sort trades by (date, entry_time_et).
    def trade_key(t):
        return (t.get("date", ""), t.get("entry_time_et", ""))
    sorted_trades = sorted(trades, key=trade_key)
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted_trades:
        cum += num(t.get("pnl"))
        peak = max(peak, cum)
        dd = peak - cum
        max_dd = max(max_dd, dd)

    # Trades-per-day distribution
    by_date = Counter(t.get("date") for t in trades)
    trades_per_day = list(by_date.values())

    # Outlier domination — top-5 trades' contribution to total
    top5_contribution = sum(sorted(pnls, reverse=True)[:5])
    pct_pnl_in_top5 = (top5_contribution / total * 100.0) if total != 0 else 0
    pct_pnl_in_top1 = (sorted(pnls, reverse=True)[0] / total * 100.0) if total != 0 else 0

    # Days that contributed most
    pnl_by_date = defaultdict(float)
    for t in trades:
        pnl_by_date[t.get("date")] += num(t.get("pnl"))
    by_date_sorted = sorted(pnl_by_date.items(), key=lambda x: -x[1])
    top5_days_pnl = sum(p for _, p in by_date_sorted[:5])
    pct_pnl_in_top5_days = (top5_days_pnl / total * 100.0) if total != 0 else 0

    # Symbol contribution
    pnl_by_sym = defaultdict(float)
    sym_trades = defaultdict(int)
    for t in trades:
        pnl_by_sym[t.get("symbol")] += num(t.get("pnl"))
        sym_trades[t.get("symbol")] += 1
    n_unique_syms = len(pnl_by_sym)

    # Exit reason breakdown
    exit_reason = Counter(t.get("exit_reason") for t in trades)

    return {
        "n_trades": n,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate_pct": round(n_wins / n * 100.0, 2),
        "total_pnl": round(total, 2),
        "gross_winners": round(gross_w, 2),
        "gross_losers": round(gross_l, 2),
        "profit_factor": round(pf, 2) if pf != float("inf") else None,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "median_win": round(median_win, 2),
        "median_loss": round(median_loss, 2),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct_of_pnl": round(max_dd / total * 100.0, 1) if total > 0 else 0,
        "trades_per_day_avg": round(statistics.mean(trades_per_day), 2),
        "trades_per_day_max": max(trades_per_day),
        "trade_days": len(by_date),
        "top1_trade_pnl": round(max(pnls), 2),
        "pct_pnl_from_top5_trades": round(pct_pnl_in_top5, 1),
        "pct_pnl_from_top1_trade": round(pct_pnl_in_top1, 1),
        "pct_pnl_from_top5_days": round(pct_pnl_in_top5_days, 1),
        "n_unique_symbols": n_unique_syms,
        "top_5_symbols_by_pnl": [(s, round(p, 2), sym_trades[s]) for s, p in
                                  sorted(pnl_by_sym.items(), key=lambda x: -x[1])[:5]],
        "bottom_5_symbols_by_pnl": [(s, round(p, 2), sym_trades[s]) for s, p in
                                     sorted(pnl_by_sym.items(), key=lambda x: x[1])[:5]],
        "exit_reason_breakdown": dict(exit_reason),
        "top_5_days_by_pnl": [(d, round(p, 2)) for d, p in by_date_sorted[:5]],
        "bottom_5_days_by_pnl": [(d, round(p, 2)) for d, p in by_date_sorted[-5:]],
    }


def section_d_acceptance(c_perf: dict, a_freq: dict) -> dict:
    """Acceptance criteria checklist per the directive's Stage 2 gate."""
    checks = {}
    checks["100+ trades"] = c_perf.get("n_trades", 0) >= 100
    checks["WR >= 50%"] = c_perf.get("win_rate_pct", 0) >= 50.0
    checks["PF >= 1.4"] = (c_perf.get("profit_factor") or 0) >= 1.4
    checks["not outlier-dominated"] = c_perf.get("pct_pnl_from_top5_days", 0) < 50.0
    checks["pattern in >= 30% of cells"] = a_freq.get("pct_cells_with_waves", 0) >= 30.0
    return checks


def main() -> int:
    census = read_csv(os.path.join(WR, "ytd_wave_census.csv"))
    waves = read_csv(os.path.join(WR, "ytd_waves_detail.csv"))
    trades = read_csv(os.path.join(WR, "ytd_hypothetical_trades.csv"))

    a = section_a_frequency(census, waves)
    b = section_b_pattern_match(waves)
    c = section_c_performance(trades)
    d = section_d_acceptance(c, a)

    summary = {
        "section_a_frequency": a,
        "section_b_pattern_match": b,
        "section_c_performance": c,
        "section_d_acceptance": d,
    }

    out = os.path.join(WR, "ytd_summary.json")
    with open(out, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Wrote {out}")
    print()
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
