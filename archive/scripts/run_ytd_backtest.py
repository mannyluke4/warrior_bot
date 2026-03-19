#!/usr/bin/env python3
"""
YTD A/B Backtest Runner — Score Gate Test
Runs simulate.py on all scanner candidates for Jan 2 – Mar 12, 2026
in two parallel configurations (A: score gate ON, B: score gate OFF).
Tracks equity, saves state for resume, generates YTD_BACKTEST_RESULTS.md.
"""

import subprocess
import re
import os
import json
import sys
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────
STARTING_EQUITY = 30_000
RISK_PCT = 0.025  # 2.5% of equity per trade

ENV_BASE = {
    "WB_CLASSIFIER_ENABLED": "1",
    "WB_CLASSIFIER_RECLASS_ENABLED": "1",
    "WB_EXHAUSTION_ENABLED": "1",
    "WB_WARMUP_BARS": "5",
    "WB_CONTINUATION_HOLD_ENABLED": "1",
    "WB_CONT_HOLD_5M_TREND_GUARD": "1",
    "WB_CONT_HOLD_5M_VOL_EXIT_MULT": "2.0",
    "WB_CONT_HOLD_5M_MIN_BARS": "2",
    "WB_CONT_HOLD_MIN_VOL_DOM": "2.0",
    "WB_CONT_HOLD_MIN_SCORE": "8.0",
    "WB_CONT_HOLD_MAX_LOSS_R": "0.5",
    "WB_CONT_HOLD_CUTOFF_HOUR": "10",
    "WB_CONT_HOLD_CUTOFF_MIN": "30",
    "WB_MAX_NOTIONAL": "50000",
}

DATES = [
    # January
    "2026-01-02", "2026-01-03", "2026-01-05", "2026-01-06", "2026-01-07",
    "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13", "2026-01-14",
    "2026-01-15", "2026-01-16", "2026-01-20", "2026-01-21", "2026-01-22",
    "2026-01-23", "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29",
    "2026-01-30",
    # February
    "2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06",
    "2026-02-09", "2026-02-10", "2026-02-11", "2026-02-12", "2026-02-13",
    "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-23",
    "2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27",
    # March
    "2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06",
    "2026-03-09", "2026-03-10", "2026-03-11", "2026-03-12",
]

STATE_FILE = "ytd_backtest_state.json"
SCANNER_DIR = "scanner_results"
WORKDIR = "/Users/mannyluke/warrior_bot"

# ── Scanner candidate loading ──────────────────────────────────────────

def load_candidates(date_str: str) -> list:
    """Load scanner candidates from cached JSON."""
    path = os.path.join(WORKDIR, SCANNER_DIR, f"{date_str}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    return data


# ── Simulation runner ──────────────────────────────────────────────────

TRADE_PAT = re.compile(
    r'^\s*(\d+)\s+'           # trade number
    r'(\d{2}:\d{2})\s+'      # time
    r'([\d.]+)\s+'           # entry
    r'([\d.]+)\s+'           # stop
    r'([\d.]+)\s+'           # R
    r'([\d.]+)\s+'           # score
    r'([\d.]+)\s+'           # exit
    r'(\S+)\s+'              # reason
    r'([+-]?\d+)\s+'         # P&L
    r'([+-]?[\d.]+R)',       # R-mult
    re.MULTILINE
)


def run_sim(symbol: str, date: str, sim_start: str, risk: int, min_score: float) -> list:
    """Run simulate.py and parse trade results. Returns list of trade dicts."""
    env = {**os.environ, **ENV_BASE}
    env["WB_MIN_ENTRY_SCORE"] = str(min_score)

    cmd = [
        "python", "simulate.py", symbol, date, sim_start, "12:00",
        "--ticks", "--risk", str(risk), "--no-fundamentals",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, env=env,
            cwd=WORKDIR,
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT: {symbol} {date}", flush=True)
        return []
    except Exception as e:
        print(f"    ERROR: {symbol} {date}: {e}", flush=True)
        return []

    trades = []
    for m in TRADE_PAT.finditer(output):
        pnl_str = m.group(9)
        trades.append({
            "num": int(m.group(1)),
            "time": m.group(2),
            "entry": float(m.group(3)),
            "stop": float(m.group(4)),
            "r": float(m.group(5)),
            "score": float(m.group(6)),
            "exit_price": float(m.group(7)),
            "reason": m.group(8),
            "pnl": int(float(pnl_str)),
            "r_mult": m.group(10),
            "symbol": symbol,
            "date": date,
        })

    return trades


# ── State management ───────────────────────────────────────────────────

def load_state():
    if os.path.exists(os.path.join(WORKDIR, STATE_FILE)):
        with open(os.path.join(WORKDIR, STATE_FILE)) as f:
            return json.load(f)
    return None


def save_state(state):
    with open(os.path.join(WORKDIR, STATE_FILE), "w") as f:
        json.dump(state, f, indent=2)


# ── Main backtest loop ─────────────────────────────────────────────────

def run_backtest():
    state = load_state()
    if state:
        last_done = state["last_completed_date"]
        eq_a = state["config_a"]["equity"]
        eq_b = state["config_b"]["equity"]
        trades_a = state["config_a"]["trades"]
        trades_b = state["config_b"]["trades"]
        daily_a = state["config_a"]["daily"]
        daily_b = state["config_b"]["daily"]
        max_eq_a = state["config_a"].get("max_equity", eq_a)
        max_eq_b = state["config_b"].get("max_equity", eq_b)
        max_dd_a = state["config_a"].get("max_drawdown", 0)
        max_dd_b = state["config_b"].get("max_drawdown", 0)
        max_dd_pct_a = state["config_a"].get("max_drawdown_pct", 0)
        max_dd_pct_b = state["config_b"].get("max_drawdown_pct", 0)
        start_idx = DATES.index(last_done) + 1 if last_done in DATES else 0
        print(f"Resuming from {last_done} (A: ${eq_a:,.0f}, B: ${eq_b:,.0f})", flush=True)
    else:
        eq_a = STARTING_EQUITY
        eq_b = STARTING_EQUITY
        trades_a = []
        trades_b = []
        daily_a = []
        daily_b = []
        max_eq_a = eq_a
        max_eq_b = eq_b
        max_dd_a = 0
        max_dd_b = 0
        max_dd_pct_a = 0
        max_dd_pct_b = 0
        start_idx = 0

    total_dates = len(DATES)
    for i in range(start_idx, total_dates):
        date = DATES[i]
        candidates = load_candidates(date)

        if not candidates:
            daily_a.append({"date": date, "trades": 0, "wins": 0, "losses": 0,
                           "day_pnl": 0, "equity": eq_a, "note": "no scanner hits"})
            daily_b.append({"date": date, "trades": 0, "wins": 0, "losses": 0,
                           "day_pnl": 0, "equity": eq_b, "note": "no scanner hits"})
            print(f"[{i+1}/{total_dates}] {date}: no scanner results", flush=True)
            # Save state
            save_state({
                "last_completed_date": date,
                "config_a": {"equity": eq_a, "trades": trades_a, "daily": daily_a,
                             "max_equity": max_eq_a, "max_drawdown": max_dd_a, "max_drawdown_pct": max_dd_pct_a},
                "config_b": {"equity": eq_b, "trades": trades_b, "daily": daily_b,
                             "max_equity": max_eq_b, "max_drawdown": max_dd_b, "max_drawdown_pct": max_dd_pct_b},
            })
            continue

        risk_a = int(eq_a * RISK_PCT)
        risk_b = int(eq_b * RISK_PCT)
        day_pnl_a = 0
        day_pnl_b = 0
        day_trades_a = []
        day_trades_b = []

        print(f"[{i+1}/{total_dates}] {date}: {len(candidates)} candidates (risk A=${risk_a}, B=${risk_b})", flush=True)

        for c in candidates:
            sym = c["symbol"]
            sim_start = c.get("sim_start", "07:00")

            # Config A: score gate = 8.0
            t_a = run_sim(sym, date, sim_start, risk_a, min_score=8.0)
            for t in t_a:
                t["equity_before"] = eq_a
                day_trades_a.append(t)
                day_pnl_a += t["pnl"]

            # Config B: no score gate
            t_b = run_sim(sym, date, sim_start, risk_b, min_score=0)
            for t in t_b:
                t["equity_before"] = eq_b
                day_trades_b.append(t)
                day_pnl_b += t["pnl"]

        # Update equity
        eq_a += day_pnl_a
        eq_b += day_pnl_b

        # Track drawdown
        if eq_a > max_eq_a:
            max_eq_a = eq_a
        dd_a = max_eq_a - eq_a
        dd_pct_a = (dd_a / max_eq_a * 100) if max_eq_a > 0 else 0
        if dd_a > max_dd_a:
            max_dd_a = dd_a
            max_dd_pct_a = dd_pct_a

        if eq_b > max_eq_b:
            max_eq_b = eq_b
        dd_b = max_eq_b - eq_b
        dd_pct_b = (dd_b / max_eq_b * 100) if max_eq_b > 0 else 0
        if dd_b > max_dd_b:
            max_dd_b = dd_b
            max_dd_pct_b = dd_pct_b

        wins_a = sum(1 for t in day_trades_a if t["pnl"] > 0)
        losses_a = sum(1 for t in day_trades_a if t["pnl"] < 0)
        wins_b = sum(1 for t in day_trades_b if t["pnl"] > 0)
        losses_b = sum(1 for t in day_trades_b if t["pnl"] < 0)

        daily_a.append({"date": date, "trades": len(day_trades_a), "wins": wins_a,
                        "losses": losses_a, "day_pnl": day_pnl_a, "equity": eq_a})
        daily_b.append({"date": date, "trades": len(day_trades_b), "wins": wins_b,
                        "losses": losses_b, "day_pnl": day_pnl_b, "equity": eq_b})
        trades_a.extend(day_trades_a)
        trades_b.extend(day_trades_b)

        print(f"  A: {len(day_trades_a)} trades, ${day_pnl_a:+,}, eq=${eq_a:,.0f} | "
              f"B: {len(day_trades_b)} trades, ${day_pnl_b:+,}, eq=${eq_b:,.0f}", flush=True)

        # Save state after each date
        save_state({
            "last_completed_date": date,
            "config_a": {"equity": eq_a, "trades": trades_a, "daily": daily_a,
                         "max_equity": max_eq_a, "max_drawdown": max_dd_a, "max_drawdown_pct": max_dd_pct_a},
            "config_b": {"equity": eq_b, "trades": trades_b, "daily": daily_b,
                         "max_equity": max_eq_b, "max_drawdown": max_dd_b, "max_drawdown_pct": max_dd_pct_b},
        })

    return {
        "config_a": {
            "equity": eq_a, "trades": trades_a, "daily": daily_a,
            "max_drawdown": max_dd_a, "max_drawdown_pct": max_dd_pct_a,
        },
        "config_b": {
            "equity": eq_b, "trades": trades_b, "daily": daily_b,
            "max_drawdown": max_dd_b, "max_drawdown_pct": max_dd_pct_b,
        },
    }


# ── Report generation ──────────────────────────────────────────────────

def calc_stats(trades, equity, max_dd, max_dd_pct):
    """Calculate summary statistics for a config."""
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
        "total_pnl": total_pnl,
        "total_return": total_pnl / STARTING_EQUITY * 100,
        "total_trades": len(trades),
        "win_rate_str": f"{len(wins)}/{len(active)} ({len(wins)/len(active)*100:.0f}%)" if active else "0/0",
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": pf,
        "max_dd": max_dd,
        "max_dd_pct": max_dd_pct,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
    }


def find_diff_trades(trades_a, trades_b):
    """Find trades in B that were blocked by A (score < 8.0)."""
    # Build set of (date, symbol, trade_num) in A
    a_set = set((t["date"], t["symbol"], t["num"]) for t in trades_a)
    # Trades in B not in A
    diff = []
    for t in trades_b:
        key = (t["date"], t["symbol"], t["num"])
        if key not in a_set:
            diff.append(t)
    return diff


def generate_report(results):
    """Generate YTD_BACKTEST_RESULTS.md."""
    ca = results["config_a"]
    cb = results["config_b"]
    sa = calc_stats(ca["trades"], ca["equity"], ca["max_drawdown"], ca["max_drawdown_pct"])
    sb = calc_stats(cb["trades"], cb["equity"], cb["max_drawdown"], cb["max_drawdown_pct"])

    lines = []
    lines.append("# YTD Backtest Results: A/B Score Gate Test")
    lines.append(f"## Generated {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"\nPeriod: January 2 – March 12, 2026 ({len(DATES)} trading days)")
    lines.append(f"Starting Equity: ${STARTING_EQUITY:,}")
    lines.append(f"Risk: {RISK_PCT*100:.1f}% of equity (dynamic)\n")

    # Section 1: Summary
    lines.append("---\n")
    lines.append("## Section 1: Summary Comparison\n")
    lines.append("| Metric | Config A (Gate=8) | Config B (No Gate) |")
    lines.append("|--------|--------------------|--------------------|")
    lines.append(f"| Final Equity | ${ca['equity']:,.0f} | ${cb['equity']:,.0f} |")
    lines.append(f"| Total P&L | ${sa['total_pnl']:+,.0f} | ${sb['total_pnl']:+,.0f} |")
    lines.append(f"| Total Return | {sa['total_return']:+.1f}% | {sb['total_return']:+.1f}% |")
    lines.append(f"| Total Trades | {sa['total_trades']} | {sb['total_trades']} |")
    lines.append(f"| Win Rate | {sa['win_rate_str']} | {sb['win_rate_str']} |")
    lines.append(f"| Average Win | ${sa['avg_win']:+,.0f} | ${sb['avg_win']:+,.0f} |")
    lines.append(f"| Average Loss | ${sa['avg_loss']:+,.0f} | ${sb['avg_loss']:+,.0f} |")
    lines.append(f"| Profit Factor | {sa['profit_factor']:.2f} | {sb['profit_factor']:.2f} |")
    lines.append(f"| Max Drawdown $ | ${sa['max_dd']:,.0f} | ${sb['max_dd']:,.0f} |")
    lines.append(f"| Max Drawdown % | {sa['max_dd_pct']:.1f}% | {sb['max_dd_pct']:.1f}% |")
    lines.append(f"| Largest Single Win | ${sa['largest_win']:+,} | ${sb['largest_win']:+,} |")
    lines.append(f"| Largest Single Loss | ${sa['largest_loss']:+,} | ${sb['largest_loss']:+,} |")

    # Section 2: Monthly Breakdown
    lines.append("\n---\n")
    lines.append("## Section 2: Monthly Breakdown\n")
    lines.append("| Month | A P&L | A Trades | B P&L | B Trades |")
    lines.append("|-------|-------|----------|-------|----------|")
    for month_prefix, month_name in [("2026-01", "Jan"), ("2026-02", "Feb"), ("2026-03", "Mar")]:
        a_pnl = sum(d["day_pnl"] for d in ca["daily"] if d["date"].startswith(month_prefix))
        a_trades = sum(d["trades"] for d in ca["daily"] if d["date"].startswith(month_prefix))
        b_pnl = sum(d["day_pnl"] for d in cb["daily"] if d["date"].startswith(month_prefix))
        b_trades = sum(d["trades"] for d in cb["daily"] if d["date"].startswith(month_prefix))
        lines.append(f"| {month_name} | ${a_pnl:+,} | {a_trades} | ${b_pnl:+,} | {b_trades} |")

    # Section 3: Daily Detail
    lines.append("\n---\n")
    lines.append("## Section 3: Daily Detail\n")
    lines.append("| Date | A Trades | A Day P&L | A Equity | B Trades | B Day P&L | B Equity |")
    lines.append("|------|----------|-----------|----------|----------|-----------|----------|")
    for da, db in zip(ca["daily"], cb["daily"]):
        note_a = f" ({da['note']})" if da.get("note") else ""
        lines.append(
            f"| {da['date']} | {da['trades']} | ${da['day_pnl']:+,} | "
            f"${da['equity']:,.0f}{note_a} | {db['trades']} | ${db['day_pnl']:+,} | "
            f"${db['equity']:,.0f} |"
        )

    # Section 4: Trade-Level Detail
    lines.append("\n---\n")
    lines.append("## Section 4: Trade-Level Detail\n")
    lines.append("### Config A (Gate=8)\n")
    lines.append("| Date | Symbol | Score | Entry | Exit | Reason | P&L |")
    lines.append("|------|--------|-------|-------|------|--------|-----|")
    for t in ca["trades"]:
        lines.append(
            f"| {t['date']} | {t['symbol']} | {t['score']:.1f} | "
            f"${t['entry']:.2f} | ${t['exit_price']:.2f} | {t['reason']} | ${t['pnl']:+,} |"
        )

    lines.append("\n### Config B (No Gate)\n")
    lines.append("| Date | Symbol | Score | Entry | Exit | Reason | P&L |")
    lines.append("|------|--------|-------|-------|------|--------|-----|")
    for t in cb["trades"]:
        lines.append(
            f"| {t['date']} | {t['symbol']} | {t['score']:.1f} | "
            f"${t['entry']:.2f} | ${t['exit_price']:.2f} | {t['reason']} | ${t['pnl']:+,} |"
        )

    # Section 5: Diff Trades
    lines.append("\n---\n")
    lines.append("## Section 5: Trades That Differ (Blocked by A, Taken by B)\n")
    diff = find_diff_trades(ca["trades"], cb["trades"])
    if diff:
        lines.append("| Date | Symbol | Score | Entry | Exit | Reason | P&L (in B) |")
        lines.append("|------|--------|-------|-------|------|--------|------------|")
        total_diff_pnl = 0
        for t in diff:
            lines.append(
                f"| {t['date']} | {t['symbol']} | {t['score']:.1f} | "
                f"${t['entry']:.2f} | ${t['exit_price']:.2f} | {t['reason']} | ${t['pnl']:+,} |"
            )
            total_diff_pnl += t["pnl"]
        lines.append(f"\n**Total P&L of blocked trades**: ${total_diff_pnl:+,}")
        lines.append(f"**Score gate net impact**: ${-total_diff_pnl:+,} (positive = gate helped)")
    else:
        lines.append("No trades differ between A and B.")

    # Section 6: Robustness
    lines.append("\n---\n")
    lines.append("## Section 6: Robustness Checks\n")

    for label, trades in [("Config A", ca["trades"]), ("Config B", cb["trades"])]:
        active = [t for t in trades if t["pnl"] != 0]
        sorted_wins = sorted([t["pnl"] for t in active if t["pnl"] > 0], reverse=True)
        top3 = sum(sorted_wins[:3]) if len(sorted_wins) >= 3 else sum(sorted_wins)
        total = sum(t["pnl"] for t in active)
        excl_be = [t for t in active]  # already excluded 0s

        # Longest losing streak (by day)
        daily = ca["daily"] if "A" in label else cb["daily"]
        max_streak = 0
        streak = 0
        for d in daily:
            if d["day_pnl"] < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            elif d["day_pnl"] > 0:
                streak = 0
            # $0 days don't break streak

        wins = [t for t in active if t["pnl"] > 0]
        losses_list = [t for t in active if t["pnl"] < 0]

        lines.append(f"### {label}")
        lines.append(f"- P&L without top 3 winners: ${total - top3:+,}")
        lines.append(f"- Top 3 winners: ${top3:+,}")
        lines.append(f"- Longest consecutive losing streak (days): {max_streak}")
        lines.append(f"- Win/loss count (excl breakeven): {len(wins)}W / {len(losses_list)}L")
        lines.append("")

    lines.append("---\n")
    lines.append("*Generated from YTD A/B backtest | Tick mode, Alpaca feed, dynamic sizing | Branch: v6-dynamic-sizing*")

    report_path = os.path.join(WORKDIR, "YTD_BACKTEST_RESULTS.md")
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport saved: {report_path}")


# ── Entry point ────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("YTD A/B BACKTEST: Score Gate Test")
    print(f"Period: Jan 2 – Mar 12, 2026 ({len(DATES)} trading days)")
    print(f"Starting equity: ${STARTING_EQUITY:,}")
    print("=" * 60)

    results = run_backtest()
    generate_report(results)

    pnl_a = results["config_a"]["equity"] - STARTING_EQUITY
    pnl_b = results["config_b"]["equity"] - STARTING_EQUITY
    print(f"\n{'=' * 60}")
    print(f"Config A (Gate=8): ${pnl_a:+,.0f} ({pnl_a/STARTING_EQUITY*100:+.1f}%)")
    print(f"Config B (No Gate): ${pnl_b:+,.0f} ({pnl_b/STARTING_EQUITY*100:+.1f}%)")
    print(f"Gate impact: ${pnl_a - pnl_b:+,.0f}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
