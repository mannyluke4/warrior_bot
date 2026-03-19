#!/usr/bin/env python3
"""
2-Week Continuous Backtest Runner
Runs simulate.py on all known stocks for each trading day in two windows,
tracks equity, and generates TWO_WEEK_BACKTEST_RESULTS.md.
"""

import subprocess
import re
import os
import json
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
    "WB_MIN_ENTRY_SCORE": "8.0",
    "WB_MAX_NOTIONAL": "50000",
}

# ── Stock lists per date ────────────────────────────────────────────────
# Built from study_data files + known 15-date set stocks

WINDOW1 = {
    # Jan 13-29, 2026 (~12 trading days)
    "2026-01-13": [],  # No known scanner hits
    "2026-01-14": ["BNAI", "BOLT", "ROLR"],
    "2026-01-15": ["SPHL"],
    "2026-01-16": ["ACCL", "ALMS", "AZI", "BCTX", "FEED", "GWAV", "HIND",
                    "LCFY", "PAVM", "ROLR", "SHPH", "STKH", "STSS", "TNMG", "VERO"],
    # Jan 17-19: weekend + MLK Monday (Jan 19)
    "2026-01-20": ["TWG"],
    "2026-01-21": ["PAVM"],
    "2026-01-22": [],  # No known scanner hits
    "2026-01-23": ["MOVE", "SLE"],
    # Jan 24-25: weekend
    "2026-01-26": [],  # No known scanner hits (weekday)
    "2026-01-27": ["ACON", "BCTX", "FLYX", "GRI", "HIND", "MOVE", "RVSN",
                    "SLE", "SXTP"],
    "2026-01-28": ["BNAI", "GRI", "MLEC", "SNSE", "SXTP"],
    "2026-01-29": [],  # No known scanner hits
}

WINDOW2 = {
    # Feb 3-20, 2026 (~14 trading days)
    "2026-02-03": ["CRMX"],
    "2026-02-04": [],
    "2026-02-05": ["APVO", "HIMZ", "INBS", "GWAV", "HIND", "PAVM", "RVSN",
                    "SNSE", "VERO"],
    "2026-02-06": ["MNTS"],
    # Feb 7-8: weekend
    "2026-02-09": [],
    "2026-02-10": [],
    "2026-02-11": [],
    "2026-02-12": ["CGTL", "UONE"],
    "2026-02-13": ["ACON", "ALMS", "ANPA", "FLYX", "GWAV", "MLEC", "ROLR"],
    # Feb 14-15: weekend
    "2026-02-16": [],  # Presidents' Day
    "2026-02-17": [],
    "2026-02-18": ["AAOI", "BATL", "SNSE"],
    "2026-02-19": ["ENVB", "RELY"],
    "2026-02-20": ["NCI"],
}


def run_sim(symbol: str, date: str, risk: int, env_extra: dict) -> list:
    """Run simulate.py and parse trade results. Returns list of trade dicts."""
    env = {**os.environ, **ENV_BASE, **env_extra}

    cmd = [
        "python", "simulate.py", symbol, date, "07:00", "12:00", "--ticks",
        "--risk", str(risk),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180, env=env,
            cwd="/Users/mannyluke/warrior_bot"
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT: {symbol} {date}")
        return []

    trades = []
    # Parse trade lines from the report table
    # Format:  1  09:41  4.5100  4.4700  0.0400  12.5  5.6200  TW ...  +$6,543  +38.5R
    trade_pat = re.compile(
        r'^\s*(\d+)\s+'           # trade number
        r'(\d{2}:\d{2})\s+'      # time
        r'([\d.]+)\s+'           # entry
        r'([\d.]+)\s+'           # stop
        r'([\d.]+)\s+'           # R
        r'([\d.]+)\s+'           # score
        r'([\d.]+)\s+'           # exit
        r'(\S+)\s+'              # reason
        r'([+-]?\d+)\s+'         # P&L (e.g. +4907 or -608)
        r'([+-]?[\d.]+R)',       # R-mult
        re.MULTILINE
    )
    for m in trade_pat.finditer(output):
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

    # Also check for ENTRY_BLOCKED
    blocked = re.findall(r'ENTRY_BLOCKED.*?score\s+([\d.]+)', output)
    for score in blocked:
        trades.append({
            "symbol": symbol, "date": date, "score": float(score),
            "blocked": True, "pnl": 0,
        })

    # Check for "No trades taken"
    if "No trades taken" in output and not trades:
        pass  # No trades is fine

    return trades


def run_window(name: str, dates: dict, starting_eq: float):
    """Run a full window and return results."""
    equity = starting_eq
    all_trades = []
    daily_summary = []
    blocked_trades = []
    max_equity = equity
    max_drawdown = 0
    max_drawdown_pct = 0

    for date in sorted(dates.keys()):
        symbols = dates[date]
        if not symbols:
            daily_summary.append({
                "date": date, "trades": 0, "wins": 0, "losses": 0,
                "day_pnl": 0, "equity": equity, "note": "no scanner hits"
            })
            continue

        risk = int(equity * RISK_PCT)
        day_trades = []
        day_pnl = 0

        for sym in sorted(symbols):
            print(f"  Running {sym} {date} (risk=${risk})...", flush=True)
            trades = run_sim(sym, date, risk, {})
            for t in trades:
                if t.get("blocked"):
                    blocked_trades.append(t)
                    continue
                t["equity_before"] = equity
                day_trades.append(t)
                day_pnl += t["pnl"]

        # Update equity at end of day
        equity += day_pnl
        if equity > max_equity:
            max_equity = equity
        dd = max_equity - equity
        dd_pct = (dd / max_equity * 100) if max_equity > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd
            max_drawdown_pct = dd_pct

        wins = sum(1 for t in day_trades if t["pnl"] > 0)
        losses = sum(1 for t in day_trades if t["pnl"] < 0)
        flat = sum(1 for t in day_trades if t["pnl"] == 0)

        daily_summary.append({
            "date": date, "trades": len(day_trades), "wins": wins,
            "losses": losses, "flat": flat, "day_pnl": day_pnl,
            "equity": equity
        })
        all_trades.extend(day_trades)

        if day_trades:
            print(f"  {date}: {len(day_trades)} trades, "
                  f"P&L: ${day_pnl:+,}, equity: ${equity:,.0f}", flush=True)

    return {
        "name": name,
        "starting_eq": starting_eq,
        "final_eq": equity,
        "trades": all_trades,
        "daily": daily_summary,
        "blocked": blocked_trades,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,
    }


def format_window(res: dict) -> str:
    """Format a window's results as markdown."""
    lines = []
    lines.append(f"## {res['name']}")
    lines.append(f"Starting equity: ${res['starting_eq']:,.0f}\n")

    # Trade table
    lines.append("### Trade Detail")
    lines.append("| Date | Symbol | Score | Entry | Exit | Reason | P&L | Equity |")
    lines.append("|------|--------|-------|-------|------|--------|-----|--------|")
    for t in res["trades"]:
        eq_after = t.get("equity_before", 0) + t["pnl"]
        lines.append(
            f"| {t['date']} | {t['symbol']} | {t['score']:.1f} | "
            f"${t['entry']:.2f} | ${t['exit_price']:.2f} | {t['reason']} | "
            f"${t['pnl']:+,} | ${eq_after:,.0f} |"
        )

    lines.append("")

    # Daily summary
    lines.append("### Daily Summary")
    lines.append("| Date | Trades | Wins | Losses | Day P&L | Running Equity |")
    lines.append("|------|--------|------|--------|---------|----------------|")
    for d in res["daily"]:
        note = f" ({d['note']})" if d.get("note") else ""
        lines.append(
            f"| {d['date']} | {d['trades']} | {d.get('wins', 0)} | "
            f"{d.get('losses', 0)} | ${d['day_pnl']:+,} | "
            f"${d['equity']:,.0f}{note} |"
        )

    lines.append("")

    # Stats
    total_pnl = res["final_eq"] - res["starting_eq"]
    total_return = (total_pnl / res["starting_eq"]) * 100
    trades = [t for t in res["trades"] if t["pnl"] != 0]
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    gross_wins = sum(t["pnl"] for t in wins)
    gross_losses = abs(sum(t["pnl"] for t in losses))
    pf = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    lines.append("### Summary Statistics")
    lines.append(f"- **Final Equity**: ${res['final_eq']:,.0f}")
    lines.append(f"- **Total P&L**: ${total_pnl:+,.0f}")
    lines.append(f"- **Total Return**: {total_return:+.1f}%")
    lines.append(f"- **Max Drawdown**: ${res['max_drawdown']:,.0f} ({res['max_drawdown_pct']:.1f}%)")
    lines.append(f"- **Total Trades**: {len(res['trades'])}")
    lines.append(f"- **Win Rate**: {len(wins)}/{len(trades)} ({len(wins)/len(trades)*100:.0f}%)" if trades else "- **Win Rate**: 0/0")
    lines.append(f"- **Average Win**: ${avg_win:+,.0f}")
    lines.append(f"- **Average Loss**: ${avg_loss:+,.0f}")
    lines.append(f"- **Profit Factor**: {pf:.2f}")

    # Blocked trades
    if res["blocked"]:
        lines.append("\n### Trades Blocked by Score Gate")
        lines.append("| Date | Symbol | Score | Blocked Reason |")
        lines.append("|------|--------|-------|----------------|")
        for b in res["blocked"]:
            lines.append(f"| {b['date']} | {b['symbol']} | {b['score']:.1f} | score < 8.0 |")

    lines.append("")
    return "\n".join(lines)


def main():
    print("=" * 60)
    print("2-WEEK CONTINUOUS BACKTEST")
    print("=" * 60)

    # Window 1
    print("\n--- WINDOW 1: January 13-29, 2026 ---")
    w1 = run_window("WINDOW 1: January 13-29, 2026", WINDOW1, STARTING_EQUITY)

    # Window 2
    print("\n--- WINDOW 2: February 3-20, 2026 ---")
    w2 = run_window("WINDOW 2: February 3-20, 2026", WINDOW2, STARTING_EQUITY)

    # Generate report
    report = []
    report.append("# Two-Week Continuous Backtest Results")
    report.append(f"## Generated {datetime.now().strftime('%Y-%m-%d')}\n")
    report.append("### Configuration")
    report.append("```")
    for k, v in sorted(ENV_BASE.items()):
        report.append(f"{k}={v}")
    report.append(f"Starting Equity: ${STARTING_EQUITY:,}")
    report.append(f"Risk Per Trade: {RISK_PCT*100:.1f}% of equity (dynamic)")
    report.append("```\n")
    report.append("---\n")
    report.append(format_window(w1))
    report.append("---\n")
    report.append(format_window(w2))
    report.append("---\n")

    # Combined summary
    report.append("## Combined Summary\n")
    w1_pnl = w1["final_eq"] - w1["starting_eq"]
    w2_pnl = w2["final_eq"] - w2["starting_eq"]
    report.append(f"| Window | Start | Final | P&L | Return | Trades | Win Rate |")
    report.append(f"|--------|-------|-------|-----|--------|--------|----------|")

    w1_trades = [t for t in w1["trades"] if t["pnl"] != 0]
    w1_wins = [t for t in w1_trades if t["pnl"] > 0]
    w2_trades = [t for t in w2["trades"] if t["pnl"] != 0]
    w2_wins = [t for t in w2_trades if t["pnl"] > 0]

    w1_wr = f"{len(w1_wins)}/{len(w1_trades)} ({len(w1_wins)/len(w1_trades)*100:.0f}%)" if w1_trades else "0/0"
    w2_wr = f"{len(w2_wins)}/{len(w2_trades)} ({len(w2_wins)/len(w2_trades)*100:.0f}%)" if w2_trades else "0/0"

    report.append(f"| Window 1 (Jan) | ${w1['starting_eq']:,} | ${w1['final_eq']:,.0f} | ${w1_pnl:+,.0f} | {w1_pnl/w1['starting_eq']*100:+.1f}% | {len(w1['trades'])} | {w1_wr} |")
    report.append(f"| Window 2 (Feb) | ${w2['starting_eq']:,} | ${w2['final_eq']:,.0f} | ${w2_pnl:+,.0f} | {w2_pnl/w2['starting_eq']*100:+.1f}% | {len(w2['trades'])} | {w2_wr} |")

    combined_pnl = w1_pnl + w2_pnl
    report.append(f"\n**Combined P&L**: ${combined_pnl:+,.0f}")
    report.append(f"\n---\n")
    report.append(f"*Generated from 2-week continuous backtest | Tick mode, Alpaca feed, dynamic sizing | Branch: v6-dynamic-sizing*")

    report_text = "\n".join(report)
    with open("/Users/mannyluke/warrior_bot/TWO_WEEK_BACKTEST_RESULTS.md", "w") as f:
        f.write(report_text)

    print(f"\n{'=' * 60}")
    print(f"RESULTS SAVED: TWO_WEEK_BACKTEST_RESULTS.md")
    print(f"Window 1: ${w1_pnl:+,.0f} ({w1_pnl/w1['starting_eq']*100:+.1f}%)")
    print(f"Window 2: ${w2_pnl:+,.0f} ({w2_pnl/w2['starting_eq']*100:+.1f}%)")
    print(f"Combined: ${combined_pnl:+,.0f}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
