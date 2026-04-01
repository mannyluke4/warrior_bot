#!/usr/bin/env python3
"""
run_backtest_v2.py — IBKR-era backtest runner with live progress reporting.

Usage:
    python run_backtest_v2.py --start 2026-01-02 --end 2026-03-25
    python run_backtest_v2.py --start 2026-03-01 --end 2026-03-25 --label "March 2026"
    python run_backtest_v2.py --start 2026-01-02 --end 2026-03-25 --windows "07:00-12:00,16:00-20:00" --label "Morning+Evening"
    python run_backtest_v2.py --start 2026-01-02 --end 2026-03-25 --windows "04:00-20:00" --label "Full Day"

--windows: comma-separated time windows (start-end in ET). Each candidate is simulated
           in EACH window. Default is scanner sim_start to 12:00.
--status-file: custom status filename (default: current_run.md). Allows parallel runs.

Progress is written to backtest_status/<status-file> after every date.
Any Claude Code session can check progress by reading that file.
"""

import subprocess
import sys
import os
import json
import re
import time
import math
import glob
import argparse
from datetime import datetime
from collections import Counter

# ── Config ────────────────────────────────────────────────────────────
STARTING_EQUITY = 30_000
RISK_PCT = 0.025
MAX_TRADES_PER_DAY = 5
DAILY_LOSS_LIMIT = -3000
MAX_NOTIONAL = 100_000

ENV_BASE = {
    "WB_SQUEEZE_ENABLED": "1", "WB_MP_ENABLED": "0",
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
}

TRADE_PAT = re.compile(
    r'^\s*(\d+)\s+(\d{2}:\d{2})\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+'
    r'([\d.]+)\s+([\d.]+)\s+(\S+)\s+([+-]?\d+)\s+([+-]?[\d.]+R)',
    re.MULTILINE
)

WORKDIR = os.path.dirname(os.path.abspath(__file__))
STATUS_DIR = os.path.join(WORKDIR, "backtest_status")
# These are defaults; overridden by --status-file arg
STATUS_FILE = os.path.join(STATUS_DIR, "current_run.md")
STATE_FILE = os.path.join(STATUS_DIR, "current_run_state.json")


def write_status(label, dates, current_idx, equity, all_trades, daily_results, start_time,
                  status_file=None, state_file=None):
    """Write progress to a markdown file that any session can read."""
    os.makedirs(STATUS_DIR, exist_ok=True)
    sf = status_file or STATUS_FILE
    stf = state_file or STATE_FILE

    elapsed = time.time() - start_time
    elapsed_str = f"{int(elapsed//3600)}h {int((elapsed%3600)//60)}m {int(elapsed%60)}s"

    total_dates = len(dates)
    pct = (current_idx / total_dates * 100) if total_dates > 0 else 0
    total_pnl = equity - STARTING_EQUITY
    wins = sum(1 for t in all_trades if t["pnl"] > 0)
    losses = sum(1 for t in all_trades if t["pnl"] < 0)
    wr = f"{wins*100//(wins+losses)}%" if wins + losses > 0 else "N/A"

    # Estimate time remaining
    if current_idx > 0:
        per_date = elapsed / current_idx
        remaining = per_date * (total_dates - current_idx)
        eta_str = f"{int(remaining//3600)}h {int((remaining%3600)//60)}m"
    else:
        eta_str = "calculating..."

    lines = [
        f"# Backtest Progress: {label}",
        f"**Last updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"## Status: {'RUNNING' if current_idx < total_dates else 'COMPLETE'}",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Progress | **{current_idx}/{total_dates} dates ({pct:.0f}%)** |",
        f"| Elapsed | {elapsed_str} |",
        f"| ETA | {eta_str} |",
        f"| Current equity | **${equity:,.0f}** |",
        f"| Total P&L | **${total_pnl:+,.0f} ({total_pnl/STARTING_EQUITY*100:+.1f}%)** |",
        f"| Trades | {len(all_trades)} ({wr}, {wins}W/{losses}L) |",
        f"| Avg winner | ${sum(t['pnl'] for t in all_trades if t['pnl']>0)/max(wins,1):+,.0f} |",
        f"| Avg loser | ${sum(t['pnl'] for t in all_trades if t['pnl']<0)/max(losses,1):+,.0f} |",
        "",
        "## Recent Activity",
        "",
    ]

    # Last 10 daily results
    recent = [d for d in daily_results if d["trades"] > 0][-10:]
    if recent:
        lines.append("| Date | Trades | Day P&L | Equity | Stocks |")
        lines.append("|------|--------|---------|--------|--------|")
        for d in recent:
            lines.append(f"| {d['date']} | {d['trades']} | ${d['pnl']:+,} | ${d['equity']:,.0f} | {d.get('symbols','')} |")
    else:
        lines.append("*No trades yet.*")

    # Exit reason breakdown
    if all_trades:
        lines.append("")
        lines.append("## Exit Reasons")
        lines.append("")
        reasons = Counter(t["reason"] for t in all_trades)
        lines.append("| Reason | Count | Wins | P&L |")
        lines.append("|--------|-------|------|-----|")
        for r, n in reasons.most_common(10):
            p = sum(t["pnl"] for t in all_trades if t["reason"] == r)
            w = sum(1 for t in all_trades if t["reason"] == r and t["pnl"] > 0)
            lines.append(f"| {r} | {n} | {w} | ${p:+,} |")

    with open(sf, "w") as f:
        f.write("\n".join(lines) + "\n")

    # Also save state JSON for resumability
    state = {
        "label": label,
        "last_date": dates[current_idx - 1] if current_idx > 0 else None,
        "equity": equity,
        "trades": all_trades,
        "daily": daily_results,
    }
    with open(stf, "w") as f:
        json.dump(state, f, indent=2)


def run_backtest(dates, label, windows=None, status_file=None, state_file=None, max_stocks=5,
                 salary_cap=None, pdt_mode=False):
    """
    Run backtest across dates.
    windows: list of (start_time, end_time) tuples, e.g. [("07:00","12:00"), ("16:00","20:00")]
             If None, uses scanner sim_start to 12:00 (original behavior).
    salary_cap: if set, withdraw profits above this amount at end of each day.
    pdt_mode: if True, enforce 3 day trades per 5 business days until equity >= $25K.
    """
    equity = STARTING_EQUITY
    all_trades = []
    daily_results = []
    total_withdrawn = 0
    withdrawal_log = []
    start_time = time.time()
    sf = status_file or STATUS_FILE
    stf = state_file or STATE_FILE

    # PDT tracking: rolling 5-day window of day trade counts
    PDT_THRESHOLD = 25_000
    PDT_MAX_DAY_TRADES = 3  # per 5 business days
    pdt_trade_history = []  # list of (date_index, num_trades) for rolling window
    pdt_crossed = False  # True once equity >= $25K

    window_desc = ""
    if windows:
        window_desc = " | Windows: " + ", ".join(f"{w[0]}-{w[1]}" for w in windows)
    if salary_cap:
        window_desc += f" | Salary mode: cap ${salary_cap:,}"
    if pdt_mode:
        window_desc += f" | PDT mode: 3 trades/5 days until ${PDT_THRESHOLD:,}"

    print(f"{'='*60}")
    print(f"  {label}{window_desc}")
    print(f"  {len(dates)} trading days, starting ${STARTING_EQUITY:,}")
    print(f"  Progress → {sf}")
    print(f"{'='*60}")

    for i, date in enumerate(dates):
        # Load candidates from V3 scanner (primary — Databento, correct discovery times)
        scanner_file = os.path.join(WORKDIR, "scanner_results", f"{date}.json")
        cands = []
        if os.path.exists(scanner_file):
            with open(scanner_file) as f:
                data = json.load(f)
            # Handle both V3 format (flat list) and old snapshot format
            if data and isinstance(data, list):
                if isinstance(data[0], dict) and "timestamp" in data[0]:
                    # Old snapshot format — extract unique candidates across all snapshots
                    seen = set()
                    for snap in data:
                        for c in snap.get("candidates", []):
                            if c["symbol"] not in seen:
                                seen.add(c["symbol"])
                                cands.append(c)
                else:
                    cands = data

        # Also load IBKR scanner results if available (secondary source)
        ibkr_file = os.path.join(WORKDIR, "scanner_results_ibkr", f"{date}.json")
        if os.path.exists(ibkr_file):
            with open(ibkr_file) as f:
                ibkr_data = json.load(f)
            ibkr_cands = []
            if ibkr_data and isinstance(ibkr_data, list):
                if isinstance(ibkr_data[0], dict) and "timestamp" in ibkr_data[0]:
                    seen_ibkr = set()
                    for snap in ibkr_data:
                        for c in snap.get("candidates", []):
                            if c["symbol"] not in seen_ibkr:
                                seen_ibkr.add(c["symbol"])
                                ibkr_cands.append(c)
                else:
                    ibkr_cands = ibkr_data

            # Merge: for stocks in both, use EARLIER sim_start. Add IBKR-only stocks.
            v3_by_sym = {c["symbol"]: c for c in cands}
            for c in ibkr_cands:
                sym = c["symbol"]
                if sym in v3_by_sym:
                    # Both have it — use the EARLIER discovery/sim_start
                    v3_start = v3_by_sym[sym].get("sim_start", "12:00")
                    ibkr_start = c.get("sim_start", "12:00")
                    if ibkr_start < v3_start:
                        # IBKR found it earlier — replace V3 entry
                        v3_by_sym[sym]["sim_start"] = ibkr_start
                        v3_by_sym[sym]["discovery_time"] = ibkr_start
                else:
                    cands.append(c)

        if not cands:
            daily_results.append({"date": date, "trades": 0, "pnl": 0, "equity": equity})
            write_status(label, dates, i + 1, equity, all_trades, daily_results, start_time, sf, stf)
            continue

        # PDT mode: use full buying power (4x margin) for each trade
        if pdt_mode and not pdt_crossed:
            buying_power = equity * 4  # 4x margin
            risk = max(int(buying_power * RISK_PCT), 50)
        else:
            risk = max(int(equity * RISK_PCT), 50)

        day_pnl = 0
        day_trades = 0
        day_symbols = []

        # PDT: calculate how many trades we're allowed today
        if pdt_mode and not pdt_crossed:
            # Rolling 5-day window: count trades in last 5 business days
            recent_trades = sum(nt for di, nt in pdt_trade_history if di > i - 5)
            pdt_remaining = max(0, PDT_MAX_DAY_TRADES - recent_trades)
            max_trades_today = min(pdt_remaining, 1)  # Take at most 1 per day to spread trades
            if pdt_remaining == 0:
                max_trades_today = 0
        else:
            max_trades_today = MAX_TRADES_PER_DAY

        # Determine which time windows to simulate
        if windows:
            sim_windows = windows
        else:
            sim_windows = None  # use per-candidate sim_start

        traded_syms_today = set()  # Track which symbols already traded (prevent evening dupes)

        for c in cands:  # No cap — run all candidates from both scanners
            if day_trades >= max_trades_today or day_pnl <= DAILY_LOSS_LIMIT:
                break
            sym = c["symbol"]
            env = dict(os.environ)
            env.update(ENV_BASE)
            # PDT mode: override MAX_NOTIONAL to full buying power
            if pdt_mode and not pdt_crossed:
                env["WB_MAX_NOTIONAL"] = str(int(equity * 4))
            env["WB_SCANNER_GAP_PCT"] = str(c.get("gap_pct", 0))
            env["WB_SCANNER_RVOL"] = str(c.get("relative_volume", 0))
            env["WB_SCANNER_FLOAT_M"] = str(c.get("float_millions", 20) or 20)

            # Run each window for this candidate
            if sim_windows:
                window_list = sim_windows
            else:
                ss = c.get("sim_start", "07:00")
                window_list = [(ss, "12:00")]

            for win_start, win_end in window_list:
                if day_trades >= max_trades_today or day_pnl <= DAILY_LOSS_LIMIT:
                    break
                # Skip if this stock already traded in an earlier window today
                if sym in traded_syms_today and win_start != window_list[0][0]:
                    continue
                cmd = [sys.executable, "simulate.py", sym, date, win_start, win_end,
                       "--ticks", "--risk", str(risk), "--no-fundamentals",
                       "--tick-cache", "tick_cache/"]
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env,
                                           cwd=WORKDIR)
                    output = result.stdout + result.stderr
                except:
                    continue
                for m in TRADE_PAT.finditer(output):
                    if day_trades >= max_trades_today:
                        break
                    pnl = int(float(m.group(9)))
                    day_pnl += pnl
                    day_trades += 1
                    all_trades.append({"date": date, "symbol": sym, "pnl": pnl,
                                       "reason": m.group(8), "window": f"{win_start}-{win_end}"})
                    if sym not in day_symbols:
                        day_symbols.append(sym)
                    traded_syms_today.add(sym)
                time.sleep(0.3)

        equity += day_pnl

        # PDT: record today's trades and check for $25K crossover
        if pdt_mode:
            if day_trades > 0:
                pdt_trade_history.append((i, day_trades))
            # Clean old entries outside 5-day window
            pdt_trade_history = [(di, nt) for di, nt in pdt_trade_history if di > i - 5]
            if not pdt_crossed and equity >= PDT_THRESHOLD:
                pdt_crossed = True
                print(f"  🎉 PDT CLEARED! Equity ${equity:,.0f} >= ${PDT_THRESHOLD:,} — normal trading unlocked", flush=True)

        # Salary mode: withdraw profits above cap at end of day
        day_withdrawal = 0
        if salary_cap and equity > salary_cap:
            day_withdrawal = equity - salary_cap
            total_withdrawn += day_withdrawal
            equity = salary_cap
            withdrawal_log.append({"date": date, "amount": day_withdrawal, "total": total_withdrawn})

        daily_results.append({
            "date": date, "trades": day_trades, "pnl": day_pnl,
            "equity": equity, "symbols": " ".join(day_symbols),
            "withdrawal": day_withdrawal, "total_withdrawn": total_withdrawn,
        })

        if day_trades > 0:
            wd_str = f" | withdrew ${day_withdrawal:,.0f} (total ${total_withdrawn:,.0f})" if day_withdrawal > 0 else ""
            pdt_str = ""
            if pdt_mode and not pdt_crossed:
                recent = sum(nt for di, nt in pdt_trade_history if di > i - 5)
                pdt_str = f" [PDT: {recent}/{PDT_MAX_DAY_TRADES} used]"
            print(f"[{i+1}/{len(dates)}] {date}: {day_trades} trades, ${day_pnl:+,}, eq=${equity:,.0f}{wd_str}{pdt_str}")
        else:
            pdt_str = ""
            if pdt_mode and not pdt_crossed:
                recent = sum(nt for di, nt in pdt_trade_history if di > i - 5)
                pdt_str = f" [PDT: {recent}/{PDT_MAX_DAY_TRADES} used]"
            print(f"[{i+1}/{len(dates)}] {date}: —{pdt_str}")

        write_status(label, dates, i + 1, equity, all_trades, daily_results, start_time, sf, stf)

    # Final summary
    total_pnl = equity - STARTING_EQUITY + total_withdrawn
    wins = sum(1 for t in all_trades if t["pnl"] > 0)
    losses = sum(1 for t in all_trades if t["pnl"] < 0)
    wr = "%d%%" % (wins * 100 // (wins + losses)) if wins + losses else "N/A"

    print(f"\n{'='*60}")
    print(f"  FINAL: {label}")
    print(f"  Trades: {len(all_trades)}, WR: {wr} ({wins}W/{losses}L)")
    if salary_cap:
        print(f"  Total Earned: ${total_pnl:+,}")
        print(f"  Withdrawn: ${total_withdrawn:,} ({len(withdrawal_log)} withdrawals)")
        print(f"  Account: ${equity:,}")
    else:
        print(f"  P&L: ${total_pnl:+,} ({total_pnl/STARTING_EQUITY*100:+.1f}%)")
        print(f"  Equity: ${equity:,}")
    print(f"{'='*60}")

    write_status(label, dates, len(dates), equity, all_trades, daily_results, start_time, sf, stf)


def main():
    global STARTING_EQUITY
    parser = argparse.ArgumentParser(description="V2 Backtest Runner with Progress Reporting")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--label", default=None, help="Label for this run")
    parser.add_argument("--windows", default=None,
                        help='Comma-separated time windows in ET, e.g. "07:00-12:00,16:00-20:00"')
    parser.add_argument("--status-file", default=None,
                        help="Custom status filename (default: current_run.md). Allows parallel runs.")
    parser.add_argument("--max-stocks", type=int, default=5,
                        help="Max scanner candidates per day (0 = unlimited, default 5)")
    parser.add_argument("--ab-mp-v2", action="store_true",
                        help="Run A/B comparison: Config A (SQ-only) vs Config B (SQ + MP V2)")
    parser.add_argument("--salary", type=int, default=None,
                        help="Salary mode: withdraw profits above this amount daily (e.g., --salary 100000)")
    parser.add_argument("--pdt", action="store_true",
                        help="PDT mode: 3 day trades per 5 business days until equity >= $25K")
    parser.add_argument("--equity", type=int, default=None,
                        help="Override starting equity (e.g., --equity 5000)")
    args = parser.parse_args()

    if args.equity:
        STARTING_EQUITY = args.equity

    # Find all dates with scanner data in range
    all_files = sorted(glob.glob(os.path.join(WORKDIR, "scanner_results", "20??-??-??.json")))
    dates = [os.path.basename(f).replace(".json", "") for f in all_files
             if args.start <= os.path.basename(f).replace(".json", "") <= args.end]

    # Parse windows
    windows = None
    if args.windows:
        windows = []
        for w in args.windows.split(","):
            parts = w.strip().split("-")
            if len(parts) == 2:
                windows.append((parts[0], parts[1]))

    # Status files
    status_file = None
    state_file = None
    if args.status_file:
        status_file = os.path.join(STATUS_DIR, args.status_file)
        state_file = os.path.join(STATUS_DIR, args.status_file.replace(".md", "_state.json"))

    max_stocks = args.max_stocks if args.max_stocks > 0 else None

    if args.ab_mp_v2:
        # A/B comparison: SQ-only vs SQ + MP V2
        mp_v2_vars = {
            "WB_MP_V2_ENABLED": "1",
            "WB_MP_V2_SQ_PRIORITY": "1",
            "WB_MP_REENTRY_COOLDOWN_BARS": "3",
            "WB_MP_MAX_REENTRIES": "3",
            "WB_MP_REENTRY_MIN_R": "0.06",
            "WB_MP_REENTRY_MACD_GATE": "0",
            "WB_MP_REENTRY_USE_SQ_EXITS": "1",
            "WB_MP_REENTRY_PROBE_SIZE": "0.5",
        }

        # Config A: SQ-only
        os.environ["WB_MP_V2_ENABLED"] = "0"
        label_a = f"Config A (SQ-Only) {args.start} to {args.end}"
        sf_a = os.path.join(STATUS_DIR, "ab_config_a.md") if not status_file else status_file.replace(".md", "_a.md")
        stf_a = sf_a.replace(".md", "_state.json")
        print(f"\n>>> Running Config A: SQ-Only <<<\n")
        run_backtest(dates, label_a, windows=windows, status_file=sf_a, state_file=stf_a,
                     max_stocks=max_stocks)

        # Config B: SQ + MP V2
        for k, v in mp_v2_vars.items():
            os.environ[k] = v
        label_b = f"Config B (SQ + MP V2) {args.start} to {args.end}"
        sf_b = os.path.join(STATUS_DIR, "ab_config_b.md") if not status_file else status_file.replace(".md", "_b.md")
        stf_b = sf_b.replace(".md", "_state.json")
        print(f"\n>>> Running Config B: SQ + MP V2 <<<\n")
        run_backtest(dates, label_b, windows=windows, status_file=sf_b, state_file=stf_b,
                     max_stocks=max_stocks)

        # Read results and compare
        with open(stf_a) as f:
            res_a = json.load(f)
        with open(stf_b) as f:
            res_b = json.load(f)
        eq_a = res_a["equity"]
        eq_b = res_b["equity"]
        pnl_a = eq_a - STARTING_EQUITY
        pnl_b = eq_b - STARTING_EQUITY
        trades_a = res_a["trades"]
        trades_b = res_b["trades"]
        wins_a = sum(1 for t in trades_a if t["pnl"] > 0)
        wins_b = sum(1 for t in trades_b if t["pnl"] > 0)
        losses_a = sum(1 for t in trades_a if t["pnl"] < 0)
        losses_b = sum(1 for t in trades_b if t["pnl"] < 0)

        print(f"\n{'='*60}")
        print(f"  A/B COMPARISON: SQ-Only vs SQ + MP V2")
        print(f"  Period: {args.start} to {args.end} ({len(dates)} days)")
        print(f"{'='*60}")
        print(f"  Config A (SQ-Only):   ${pnl_a:+,.0f} ({pnl_a/STARTING_EQUITY*100:+.1f}%) | {len(trades_a)} trades, {wins_a}W/{losses_a}L")
        print(f"  Config B (SQ+MP V2):  ${pnl_b:+,.0f} ({pnl_b/STARTING_EQUITY*100:+.1f}%) | {len(trades_b)} trades, {wins_b}W/{losses_b}L")
        print(f"  MP V2 impact:         ${pnl_b - pnl_a:+,.0f}")
        print(f"{'='*60}")
    else:
        label = args.label or f"Backtest {args.start} to {args.end}"
        run_backtest(dates, label, windows=windows, status_file=status_file, state_file=state_file,
                     max_stocks=max_stocks, salary_cap=args.salary, pdt_mode=args.pdt)


if __name__ == "__main__":
    main()
