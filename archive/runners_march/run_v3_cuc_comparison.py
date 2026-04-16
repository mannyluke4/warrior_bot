#!/usr/bin/env python3
"""
V3 CUC Comparison Runner — 3-config YTD comparison for CUC gate tuning.

Reuses scanner/ranking/sim logic from run_ytd_v2_backtest.py.
Runs 3 configs per day (C, D, E) with different CUC gate settings.
Config A (baseline) and B (V2) data already exists in ytd_v2_backtest_state.json.

Config C: Ross Exit ON + CUC_MIN_TRADE_BARS=5
Config D: Ross Exit ON + CUC_FLOOR_R=2.0
Config E: Ross Exit ON + CUC_MIN_TRADE_BARS=5 + CUC_FLOOR_R=2.0
"""

import os
import sys
import json
import time
from datetime import datetime

# Import shared logic from the V2 runner
from run_ytd_v2_backtest import (
    STARTING_EQUITY, RISK_PCT, MAX_TRADES_PER_DAY, DAILY_LOSS_LIMIT,
    MAX_NOTIONAL, DATES, load_and_rank, run_sim, rank_score,
    WORKDIR,
)

STATE_FILE = "ytd_v3_cuc_state.json"

CONFIGS = {
    "config_c": {
        "label": "V2 + MinBars=5",
        "env": {"WB_ROSS_EXIT_ENABLED": "1", "WB_ROSS_CUC_MIN_TRADE_BARS": "5", "WB_ROSS_CUC_FLOOR_R": "0"},
    },
    "config_d": {
        "label": "V2 + FloorR=2.0",
        "env": {"WB_ROSS_EXIT_ENABLED": "1", "WB_ROSS_CUC_MIN_TRADE_BARS": "0", "WB_ROSS_CUC_FLOOR_R": "2.0"},
    },
    "config_e": {
        "label": "V2 + MinBars=5 + FloorR=2.0",
        "env": {"WB_ROSS_EXIT_ENABLED": "1", "WB_ROSS_CUC_MIN_TRADE_BARS": "5", "WB_ROSS_CUC_FLOOR_R": "2.0"},
    },
}


def _run_config_day(top5, date, risk, min_score, max_consec_losses=2):
    """Run one config for one day (same logic as V2 runner)."""
    day_trades = []
    day_pnl = 0
    day_notional = 0
    consec_losses = 0

    for c in top5:
        if len(day_trades) >= MAX_TRADES_PER_DAY:
            break
        if day_pnl <= DAILY_LOSS_LIMIT:
            break
        if max_consec_losses > 0 and consec_losses >= max_consec_losses:
            break

        sym = c["symbol"]
        float_m = c.get("float_millions", 0) or 0
        stock_risk = min(risk, 250) if float_m > 5.0 else risk
        sim_start = c.get("sim_start", "07:00")
        all_trades = run_sim(sym, date, sim_start, stock_risk, min_score, candidate=c)
        time.sleep(0.5)

        for t in all_trades:
            if len(day_trades) >= MAX_TRADES_PER_DAY:
                break
            if day_pnl <= DAILY_LOSS_LIMIT:
                break
            if max_consec_losses > 0 and consec_losses >= max_consec_losses:
                break
            if day_notional + t["notional"] > MAX_NOTIONAL:
                continue

            day_trades.append(t)
            day_pnl += t["pnl"]
            day_notional += t["notional"]

            if t["pnl"] < 0:
                consec_losses += 1
            else:
                consec_losses = 0

    return day_trades, day_pnl


def load_state():
    p = os.path.join(WORKDIR, STATE_FILE)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


def save_state(state):
    with open(os.path.join(WORKDIR, STATE_FILE), "w") as f:
        json.dump(state, f, indent=2)


def run_comparison():
    state = load_state()
    if state:
        last_done = state["last_completed_date"]
        start_idx = DATES.index(last_done) + 1 if last_done in DATES else 0
        print(f"Resuming from {last_done}", flush=True)
    else:
        state = {"last_completed_date": None}
        for key in CONFIGS:
            state[key] = {"equity": STARTING_EQUITY, "trades": [], "daily": [],
                          "max_equity": STARTING_EQUITY, "max_drawdown": 0}
        start_idx = 0

    total_dates = len(DATES)

    for i in range(start_idx, total_dates):
        date = DATES[i]
        top5, total_cands, passed_filter = load_and_rank(date)

        if not top5:
            for key in CONFIGS:
                state[key]["daily"].append({
                    "date": date, "trades": 0, "wins": 0, "losses": 0,
                    "day_pnl": 0, "equity": state[key]["equity"],
                    "note": f"no candidates (total={total_cands}, passed={passed_filter})"
                })
            print(f"[{i+1}/{total_dates}] {date}: 0 candidates", flush=True)
            state["last_completed_date"] = date
            save_state(state)
            continue

        print(f"[{i+1}/{total_dates}] {date}: {total_cands} scanned → {passed_filter} passed → top {len(top5)}", flush=True)

        for key, cfg in CONFIGS.items():
            eq = state[key]["equity"]
            risk = max(int(eq * RISK_PCT), 50)

            # Set env vars for this config
            for env_key, env_val in cfg["env"].items():
                os.environ[env_key] = env_val

            day_trades, day_pnl = _run_config_day(top5, date, risk, min_score=8.0, max_consec_losses=2)

            eq += day_pnl
            state[key]["equity"] = eq
            state[key]["trades"].extend(day_trades)

            # Drawdown tracking
            if eq > state[key]["max_equity"]:
                state[key]["max_equity"] = eq
            dd = state[key]["max_equity"] - eq
            if dd > state[key]["max_drawdown"]:
                state[key]["max_drawdown"] = dd

            wins = sum(1 for t in day_trades if t["pnl"] > 0)
            losses = sum(1 for t in day_trades if t["pnl"] < 0)
            state[key]["daily"].append({
                "date": date, "trades": len(day_trades), "wins": wins,
                "losses": losses, "day_pnl": day_pnl, "equity": eq
            })

            print(f"  {cfg['label']}: {len(day_trades)} trades, ${day_pnl:+,}, eq=${eq:,.0f}", flush=True)

        state["last_completed_date"] = date
        save_state(state)

    return state


def calc_stats(trades, equity, max_dd, max_eq):
    active = [t for t in trades if t["pnl"] != 0]
    wins = [t for t in active if t["pnl"] > 0]
    losses = [t for t in active if t["pnl"] < 0]
    total_pnl = equity - STARTING_EQUITY
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    gross_wins = sum(t["pnl"] for t in wins)
    gross_losses = abs(sum(t["pnl"] for t in losses))
    pf = gross_wins / gross_losses if gross_losses > 0 else float("inf")
    largest_win = max((t["pnl"] for t in trades), default=0)
    largest_loss = min((t["pnl"] for t in trades), default=0)
    return {
        "total_pnl": total_pnl, "total_trades": len(trades),
        "win_rate": f"{len(wins)}/{len(active)} ({len(wins)/len(active)*100:.0f}%)" if active else "0/0",
        "avg_win": avg_win, "avg_loss": avg_loss, "profit_factor": pf,
        "max_dd": max_dd, "largest_win": largest_win, "largest_loss": largest_loss,
    }


def generate_report(state):
    # Load A/B data from V2 state
    v2_state_path = os.path.join(WORKDIR, "ytd_v2_backtest_state.json")
    with open(v2_state_path) as f:
        v2_state = json.load(f)

    all_configs = {
        "A (Baseline OFF)": calc_stats(v2_state["config_a"]["trades"], v2_state["config_a"]["equity"],
                                        v2_state["config_a"]["max_drawdown"], v2_state["config_a"]["max_equity"]),
        "B (V2 Current)": calc_stats(v2_state["config_b"]["trades"], v2_state["config_b"]["equity"],
                                      v2_state["config_b"]["max_drawdown"], v2_state["config_b"]["max_equity"]),
    }
    for key, cfg in CONFIGS.items():
        s = state[key]
        all_configs[f"{key[-1].upper()} ({cfg['label']})"] = calc_stats(
            s["trades"], s["equity"], s["max_drawdown"], s["max_equity"])

    L = []
    L.append("# V3 CUC Gate Comparison — YTD 2026")
    L.append(f"## Generated {datetime.now().strftime('%Y-%m-%d')}")
    L.append(f"\nPeriod: Jan 2 - Mar 20, 2026 ({len(DATES)} trading days)")
    L.append(f"Starting Equity: ${STARTING_EQUITY:,}")

    # Summary table
    L.append("\n## All Configs Comparison\n")
    L.append("| Metric | A (Baseline) | B (V2) | C (MinBars=5) | D (FloorR=2) | E (Both) |")
    L.append("|--------|-------------|--------|---------------|--------------|----------|")
    keys = list(all_configs.keys())
    for metric in ["total_pnl", "total_trades", "win_rate", "avg_win", "avg_loss",
                    "profit_factor", "max_dd", "largest_win", "largest_loss"]:
        row = f"| {metric} |"
        for k in keys:
            v = all_configs[k][metric]
            if isinstance(v, float):
                if metric == "profit_factor":
                    row += f" {v:.2f} |"
                else:
                    row += f" ${v:+,.0f} |"
            elif isinstance(v, int):
                if metric in ("total_pnl", "max_dd", "largest_win", "largest_loss", "avg_win", "avg_loss"):
                    row += f" ${v:+,} |"
                else:
                    row += f" {v} |"
            else:
                row += f" {v} |"
        L.append(row)

    # CUC exit analysis
    L.append("\n## CUC Exit Analysis\n")
    for key, cfg in CONFIGS.items():
        trades = state[key]["trades"]
        cuc_trades = [t for t in trades if t["reason"] == "ross_cuc_exit"]
        non_cuc = [t for t in trades if t["reason"] != "ross_cuc_exit"]
        L.append(f"### {cfg['label']}")
        L.append(f"- CUC exits: {len(cuc_trades)}")
        L.append(f"- CUC P&L: ${sum(t['pnl'] for t in cuc_trades):+,}")
        L.append(f"- Non-CUC exits: {len(non_cuc)}")
        L.append(f"- Non-CUC P&L: ${sum(t['pnl'] for t in non_cuc):+,}")
        if cuc_trades:
            L.append("| Date | Symbol | Entry | Exit | Reason | P&L |")
            L.append("|------|--------|-------|------|--------|-----|")
            for t in cuc_trades:
                L.append(f"| {t['date']} | {t['symbol']} | ${t['entry']:.2f} | ${t['exit_price']:.2f} | {t['reason']} | ${t['pnl']:+,} |")
        L.append("")

    # Exit reason distribution for each config
    L.append("\n## Exit Reason Distribution\n")
    for key, cfg in CONFIGS.items():
        trades = state[key]["trades"]
        reasons = {}
        for t in trades:
            r = t["reason"]
            if r not in reasons:
                reasons[r] = {"count": 0, "pnl": 0}
            reasons[r]["count"] += 1
            reasons[r]["pnl"] += t["pnl"]
        L.append(f"### {cfg['label']}")
        L.append("| Exit Reason | Count | Total P&L | Avg P&L |")
        L.append("|-------------|-------|-----------|---------|")
        for r in sorted(reasons, key=lambda x: reasons[x]["count"], reverse=True):
            cnt = reasons[r]["count"]
            pnl = reasons[r]["pnl"]
            L.append(f"| {r} | {cnt} | ${pnl:+,} | ${pnl//cnt:+,} |")
        L.append("")

    # Trade detail
    L.append("\n## Trade Detail (All Configs)\n")
    for key, cfg in CONFIGS.items():
        trades = state[key]["trades"]
        L.append(f"### {cfg['label']}")
        L.append("| Date | Symbol | Entry | Exit | Reason | P&L |")
        L.append("|------|--------|-------|------|--------|-----|")
        for t in trades:
            L.append(f"| {t['date']} | {t['symbol']} | ${t['entry']:.2f} | ${t['exit_price']:.2f} | {t['reason']} | ${t['pnl']:+,} |")
        L.append("")

    report_path = os.path.join(WORKDIR, "cowork_reports", "2026-03-23_v3_cuc_comparison.md")
    with open(report_path, "w") as f:
        f.write("\n".join(L))
    print(f"\nReport saved: {report_path}")


def main():
    print("=" * 60)
    print("V3 CUC GATE COMPARISON: 3-Config YTD")
    print(f"Period: Jan 2 - Mar 20, 2026 ({len(DATES)} trading days)")
    print("Config C: Ross ON + CUC_MIN_TRADE_BARS=5")
    print("Config D: Ross ON + CUC_FLOOR_R=2.0")
    print("Config E: Ross ON + CUC_MIN_TRADE_BARS=5 + CUC_FLOOR_R=2.0")
    print("=" * 60)

    state = run_comparison()
    generate_report(state)

    for key, cfg in CONFIGS.items():
        pnl = state[key]["equity"] - STARTING_EQUITY
        print(f"{cfg['label']}: ${pnl:+,.0f} ({pnl/STARTING_EQUITY*100:+.1f}%)")
    print("=" * 60)


if __name__ == "__main__":
    main()
