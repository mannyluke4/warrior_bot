#!/usr/bin/env python3
"""
Detailed YTD backtest with MP V2 enabled — captures all signals, entries, exits.
Runs each scanner candidate through simulate.py --verbose and parses full output.
"""

import subprocess, sys, os, json, re, time, glob, gzip
from datetime import datetime
from collections import Counter, defaultdict

WORKDIR = os.path.dirname(os.path.abspath(__file__))
STARTING_EQUITY = 30_000
RISK_PCT = 0.025
MAX_TRADES_PER_DAY = 5
DAILY_LOSS_LIMIT = -3000
MAX_NOTIONAL = 100_000

ENV_BASE = {
    "WB_SQUEEZE_ENABLED": "1", "WB_MP_ENABLED": "0", "WB_MP_V2_ENABLED": "1",
    "WB_SQ_VOL_MULT": "3.0", "WB_SQ_MIN_BAR_VOL": "50000",
    "WB_SQ_MIN_BODY_PCT": "1.5", "WB_SQ_PRIME_BARS": "3",
    "WB_SQ_MAX_R": "0.80", "WB_SQ_LEVEL_PRIORITY": "pm_high,whole_dollar,pdh",
    "WB_SQ_PROBE_SIZE_MULT": "0.5", "WB_SQ_MAX_ATTEMPTS": "3",
    "WB_SQ_PARA_ENABLED": "1", "WB_SQ_PARA_STOP_OFFSET": "0.10",
    "WB_SQ_PARA_TRAIL_R": "1.0", "WB_SQ_NEW_HOD_REQUIRED": "1",
    "WB_SQ_MAX_LOSS_DOLLARS": "500", "WB_SQ_TARGET_R": "2.0",
    "WB_SQ_CORE_PCT": "75", "WB_SQ_RUNNER_TRAIL_R": "2.5",
    "WB_SQ_TRAIL_R": "1.5", "WB_SQ_STALL_BARS": "5",
    "WB_SQ_VWAP_EXIT": "1", "WB_SQ_PM_CONFIDENCE": "1",
    "WB_BAIL_TIMER_ENABLED": "1", "WB_BAIL_TIMER_MINUTES": "5",
    "WB_MAX_NOTIONAL": str(MAX_NOTIONAL), "WB_MAX_LOSS_R": "0.75",
    "WB_EXHAUSTION_ENABLED": "1", "WB_WARMUP_BARS": "5",
    "WB_PILLAR_GATES_ENABLED": "1",
    # MP V2 settings
    "WB_MP_V2_SQ_PRIORITY": "1",
    "WB_MP_REENTRY_COOLDOWN_BARS": "3",
    "WB_MP_MAX_REENTRIES": "3",
    "WB_MP_REENTRY_MIN_R": "0.06",
    "WB_MP_REENTRY_MACD_GATE": "0",
    "WB_MP_REENTRY_USE_SQ_EXITS": "1",
    "WB_MP_REENTRY_PROBE_SIZE": "0.5",
}

WINDOWS = [("07:00", "12:00"), ("16:00", "20:00")]

TRADE_PAT = re.compile(
    r'^\s*(\d+)\s+(\d{2}:\d{2})\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+'
    r'([\d.]+)\s+([\d.]+)\s+(\S+)\s+([+-]?\d+)\s+([+-]?[\d.]+R)',
    re.MULTILINE
)

# Capture verbose signals
SQ_PRIMED_PAT = re.compile(r'\[(\d{2}:\d{2})\] SQ_PRIMED: (.+)')
SQ_ARMED_PAT = re.compile(r'\[(\d{2}:\d{2})\] ARMED (.+)')
SQ_ENTRY_PAT = re.compile(r'\[(\d{2}:\d{2})\] (SQ_ENTRY|MP_V2_ENTRY): (.+)')
SQ_REJECT_PAT = re.compile(r'\[(\d{2}:\d{2})\] SQ_REJECT: (.+)')
SQ_RESET_PAT = re.compile(r'\[(\d{2}:\d{2})\] (SQ_RESET|1M RESET|SQ_NO_ARM): (.+)')
MP_V2_PAT = re.compile(r'\[(\d{2}:\d{2})\] (MP_V2[_ ]\w+|MP_V2_DEFERRED): (.+)')
DEFERRED_PAT = re.compile(r'\[(\d{2}:\d{2})\] MP_V2_DEFERRED: (.+)')
EXIT_PAT = re.compile(r'\[(\d{2}:\d{2})\] (TOPPING_WICKY|BEARISH_ENGULF|TW_SUPPRESS|BE_SUPPRESS)')


def run_verbose(symbol, date, win_start, win_end, risk, env):
    """Run simulate.py --verbose and capture full output."""
    cmd = [
        sys.executable, "simulate.py", symbol, date, win_start, win_end,
        "--ticks", "--risk", str(risk), "--no-fundamentals",
        "--tick-cache", "tick_cache/", "--verbose",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env, cwd=WORKDIR)
        return result.stdout + result.stderr
    except:
        return ""


def parse_signals(output, symbol, date, window):
    """Parse all signals from verbose output."""
    signals = {
        "primes": [],
        "arms": [],
        "entries": [],
        "rejects": [],
        "resets": [],
        "mp_v2_events": [],
        "deferred": [],
        "exit_signals": [],
    }

    for m in SQ_PRIMED_PAT.finditer(output):
        signals["primes"].append({"time": m.group(1), "detail": m.group(2)})
    for m in SQ_ARMED_PAT.finditer(output):
        signals["arms"].append({"time": m.group(1), "detail": m.group(2)})
    for m in SQ_ENTRY_PAT.finditer(output):
        signals["entries"].append({"time": m.group(1), "type": m.group(2), "detail": m.group(3)})
    for m in SQ_REJECT_PAT.finditer(output):
        signals["rejects"].append({"time": m.group(1), "detail": m.group(2)})
    for m in SQ_RESET_PAT.finditer(output):
        signals["resets"].append({"time": m.group(1), "type": m.group(2), "detail": m.group(3)})
    for m in MP_V2_PAT.finditer(output):
        signals["mp_v2_events"].append({"time": m.group(1), "type": m.group(2), "detail": m.group(3)})
    for m in DEFERRED_PAT.finditer(output):
        signals["deferred"].append({"time": m.group(1), "detail": m.group(2)})

    return signals


def main():
    scanner_dir = os.path.join(WORKDIR, "scanner_results")
    all_files = sorted(glob.glob(os.path.join(scanner_dir, "2026-*.json")))
    dates = [os.path.basename(f).replace(".json", "") for f in all_files
             if "2026-01-02" <= os.path.basename(f).replace(".json", "") <= "2026-03-27"]

    equity = STARTING_EQUITY
    all_trades = []
    all_signals = []
    daily_results = []

    print(f"{'='*70}")
    print(f"  DETAILED YTD: SQ + MP V2 (IBKR Ticks)")
    print(f"  {len(dates)} dates, ${STARTING_EQUITY:,} start, morning + evening")
    print(f"{'='*70}")

    for i, date in enumerate(dates):
        sf = os.path.join(scanner_dir, f"{date}.json")
        with open(sf) as f:
            cands = json.load(f)
        if not cands:
            daily_results.append({"date": date, "trades": 0, "pnl": 0, "equity": equity})
            continue

        risk = max(int(equity * RISK_PCT), 50)
        day_pnl = 0
        day_trades = 0
        day_symbols = []
        day_signal_log = []

        for c in cands[:5]:
            if day_trades >= MAX_TRADES_PER_DAY or day_pnl <= DAILY_LOSS_LIMIT:
                break
            sym = c["symbol"]
            env = dict(os.environ)
            env.update(ENV_BASE)
            env["WB_SCANNER_GAP_PCT"] = str(c.get("gap_pct", 0))
            env["WB_SCANNER_RVOL"] = str(c.get("relative_volume", 0))
            env["WB_SCANNER_FLOAT_M"] = str(c.get("float_millions", 20) or 20)

            for win_start, win_end in WINDOWS:
                if day_trades >= MAX_TRADES_PER_DAY or day_pnl <= DAILY_LOSS_LIMIT:
                    break

                output = run_verbose(sym, date, win_start, win_end, risk, env)
                if not output:
                    continue

                # Parse signals
                signals = parse_signals(output, sym, date, f"{win_start}-{win_end}")
                if any(signals[k] for k in signals):
                    day_signal_log.append({
                        "symbol": sym, "window": f"{win_start}-{win_end}",
                        "signals": signals,
                    })

                # Parse trades
                for m in TRADE_PAT.finditer(output):
                    pnl = int(float(m.group(9)))
                    trade_entry = {
                        "date": date, "symbol": sym,
                        "num": int(m.group(1)),
                        "time": m.group(2),
                        "entry": float(m.group(3)),
                        "stop": float(m.group(4)),
                        "r": float(m.group(5)),
                        "score": float(m.group(6)),
                        "exit_price": float(m.group(7)),
                        "reason": m.group(8),
                        "pnl": pnl,
                        "r_mult": m.group(10),
                        "window": f"{win_start}-{win_end}",
                        "setup_type": "mp_reentry" if "MP_V2_ENTRY" in output and m.group(2) in output else "squeeze",
                        "signals_at_entry": {
                            "primes": len(signals["primes"]),
                            "arms": len(signals["arms"]),
                            "rejects": len(signals["rejects"]),
                            "resets": len(signals["resets"]),
                            "mp_v2_deferred": len(signals["deferred"]),
                        },
                    }
                    day_pnl += pnl
                    day_trades += 1
                    all_trades.append(trade_entry)
                    if sym not in day_symbols:
                        day_symbols.append(sym)

                time.sleep(0.3)

        equity += day_pnl
        daily_results.append({
            "date": date, "trades": day_trades, "pnl": day_pnl,
            "equity": equity, "symbols": " ".join(day_symbols),
        })

        if day_signal_log:
            all_signals.append({"date": date, "symbols": day_signal_log})

        status = f"{day_trades} trades, ${day_pnl:+,}, eq=${equity:,.0f}" if day_trades > 0 else "—"
        print(f"[{i+1}/{len(dates)}] {date}: {status}", flush=True)

    # Generate report
    total_pnl = equity - STARTING_EQUITY
    wins = [t for t in all_trades if t["pnl"] > 0]
    losses = [t for t in all_trades if t["pnl"] < 0]
    sq_trades = [t for t in all_trades if t["reason"].startswith("sq_")]
    mp_trades = [t for t in all_trades if not t["reason"].startswith("sq_") or t.get("setup_type") == "mp_reentry"]

    # Reason breakdown
    reasons = Counter(t["reason"] for t in all_trades)
    reason_pnl = defaultdict(int)
    reason_wins = Counter()
    for t in all_trades:
        reason_pnl[t["reason"]] += t["pnl"]
        if t["pnl"] > 0:
            reason_wins[t["reason"]] += 1

    report = []
    report.append("# DETAILED YTD Backtest: SQ + MP V2 on IBKR Tick Data")
    report.append(f"## Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report.append(f"## Data Source: 100% IBKR historical ticks")
    report.append("")
    report.append("---")
    report.append("")
    report.append(f"## Results: $30,000 → ${equity:,.0f} ({total_pnl/STARTING_EQUITY*100:+.1f}%)")
    report.append("")
    report.append("| Metric | Value |")
    report.append("|--------|-------|")
    report.append(f"| Total P&L | ${total_pnl:+,.0f} |")
    report.append(f"| Trades | {len(all_trades)} |")
    report.append(f"| Win Rate | {len(wins)*100//(len(wins)+len(losses)) if wins or losses else 0}% ({len(wins)}W/{len(losses)}L) |")
    report.append(f"| Avg Winner | ${sum(t['pnl'] for t in wins)/len(wins):+,.0f} |" if wins else "| Avg Winner | N/A |")
    report.append(f"| Avg Loser | ${sum(t['pnl'] for t in losses)/len(losses):+,.0f} |" if losses else "| Avg Loser | N/A |")
    report.append("")

    # Exit reason breakdown
    report.append("## Exit Reasons")
    report.append("")
    report.append("| Reason | Count | Wins | Total P&L | Avg P&L |")
    report.append("|--------|-------|------|-----------|---------|")
    for r, cnt in reasons.most_common():
        w = reason_wins[r]
        p = reason_pnl[r]
        report.append(f"| {r} | {cnt} | {w} | ${p:+,.0f} | ${p//cnt:+,.0f} |")

    # Daily breakdown
    report.append("")
    report.append("## Daily Breakdown")
    report.append("")
    report.append("| Date | Trades | Day P&L | Equity | Stocks |")
    report.append("|------|--------|---------|--------|--------|")
    for d in daily_results:
        if d["trades"] > 0:
            report.append(f"| {d['date']} | {d['trades']} | ${d['pnl']:+,} | ${d['equity']:,.0f} | {d.get('symbols', '')} |")

    # Full trade log with signals
    report.append("")
    report.append("## Complete Trade Log")
    report.append("")
    report.append("| # | Date | Symbol | Time | Entry | Stop | R | Score | Exit | Reason | P&L | R-Mult | Window |")
    report.append("|---|------|--------|------|-------|------|---|-------|------|--------|-----|--------|--------|")
    for i, t in enumerate(all_trades, 1):
        report.append(f"| {i} | {t['date']} | {t['symbol']} | {t['time']} | ${t['entry']:.2f} | ${t['stop']:.2f} | ${t['r']:.4f} | {t['score']:.1f} | ${t['exit_price']:.2f} | {t['reason']} | ${t['pnl']:+,} | {t['r_mult']} | {t['window']} |")

    # Signal activity log
    report.append("")
    report.append("## Signal Activity Log")
    report.append("")
    report.append("Detector signals observed per stock per day:")
    report.append("")
    for day_entry in all_signals:
        report.append(f"### {day_entry['date']}")
        for sym_entry in day_entry["symbols"]:
            sym = sym_entry["symbol"]
            window = sym_entry["window"]
            sigs = sym_entry["signals"]
            report.append(f"**{sym}** ({window}):")

            if sigs["primes"]:
                for s in sigs["primes"]:
                    report.append(f"- [{s['time']}] PRIMED: {s['detail']}")
            if sigs["arms"]:
                for s in sigs["arms"]:
                    report.append(f"- [{s['time']}] ARMED: {s['detail']}")
            if sigs["entries"]:
                for s in sigs["entries"]:
                    report.append(f"- [{s['time']}] {s['type']}: {s['detail']}")
            if sigs["rejects"]:
                for s in sigs["rejects"][:5]:  # Cap at 5 to avoid spam
                    report.append(f"- [{s['time']}] REJECT: {s['detail']}")
                if len(sigs["rejects"]) > 5:
                    report.append(f"- ... and {len(sigs['rejects'])-5} more rejects")
            if sigs["deferred"]:
                for s in sigs["deferred"]:
                    report.append(f"- [{s['time']}] MP_V2_DEFERRED: {s['detail']}")
            if sigs["mp_v2_events"]:
                for s in sigs["mp_v2_events"]:
                    report.append(f"- [{s['time']}] {s['type']}: {s['detail']}")

            total_sigs = sum(len(sigs[k]) for k in sigs)
            if total_sigs == 0:
                report.append("- (no signals)")
            report.append("")

    # Comparison with SQ-only
    report.append("---")
    report.append("")
    report.append("## Comparison: SQ-Only ($296,258) vs SQ+MP_V2 (this run)")
    report.append("")
    report.append(f"| Metric | SQ-Only (Definitive) | SQ + MP V2 (This Run) | Delta |")
    report.append(f"|--------|---------------------|----------------------|-------|")
    report.append(f"| Final Equity | $296,258 | ${equity:,.0f} | ${equity - 296258:+,.0f} |")
    report.append(f"| P&L | +$266,258 | ${total_pnl:+,.0f} | ${total_pnl - 266258:+,.0f} |")
    report.append(f"| Trades | 60 | {len(all_trades)} | {len(all_trades) - 60:+d} |")
    report.append(f"| Win Rate | 82% | {len(wins)*100//(len(wins)+len(losses)) if wins or losses else 0}% | |")

    # Save report
    report_path = os.path.join(WORKDIR, "cowork_reports", "2026-03-28_detailed_ytd_sq_mp_v2.md")
    with open(report_path, "w") as f:
        f.write("\n".join(report))
    print(f"\nReport saved: {report_path}")

    # Save raw data
    data_path = os.path.join(WORKDIR, "backtest_status", "detailed_mp_v2_state.json")
    with open(data_path, "w") as f:
        json.dump({
            "equity": equity,
            "trades": all_trades,
            "daily": daily_results,
            "signals": all_signals,
        }, f, indent=2)

    print(f"\n{'='*70}")
    print(f"  FINAL: SQ + MP V2 (IBKR Ticks)")
    print(f"  Trades: {len(all_trades)}, WR: {len(wins)*100//(len(wins)+len(losses)) if wins or losses else 0}% ({len(wins)}W/{len(losses)}L)")
    print(f"  P&L: ${total_pnl:+,.0f} ({total_pnl/STARTING_EQUITY*100:+.1f}%)")
    print(f"  Equity: ${equity:,.0f}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
