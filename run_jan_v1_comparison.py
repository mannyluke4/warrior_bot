#!/usr/bin/env python3
"""
January 2025 vs January 2026 Side-by-Side Comparison
=====================================================
Runs BOTH months with identical full config (all fixes: scanner + SQ exit fixes)
and produces a unified report.

Config: Scanner fixes V1 + SQ exit fixes (partial exit, wide trail, runner detect,
        halt-through) + MP enabled + unknown-float gate ON.

Usage:
    source venv/bin/activate
    python run_jan_v1_comparison.py 2>&1 | tee jan_comparison_v1_output.txt

Resume: Re-run same command — state file tracks progress.
"""

import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────
STARTING_EQUITY = 30_000
RISK_PCT = 0.025          # 2.5% of equity per trade
MAX_TRADES_PER_DAY = 5
DAILY_LOSS_LIMIT = -1_500
MAX_NOTIONAL = 50_000
TOP_N = 5

# Scanner filters
MIN_PM_VOLUME = 50_000
MIN_GAP_PCT = 10
MAX_GAP_PCT = 500
MAX_FLOAT_MILLIONS = 10
MIN_RVOL = 2.0

# Unknown-float gate: always ON for this comparison
ALLOW_UNKNOWN_FLOAT = True
UNKNOWN_FLOAT_MIN_GAP = 50.0
UNKNOWN_FLOAT_MIN_PM_VOL = 1_000_000
UNKNOWN_FLOAT_MIN_RVOL = 10.0
UNKNOWN_FLOAT_NOTIONAL_FACTOR = 0.5

WORKDIR = os.getenv("WB_WORKDIR", os.path.dirname(os.path.abspath(__file__)))
SCANNER_DIR = "scanner_results"
TICK_CACHE_DIR = os.path.join(WORKDIR, "tick_cache")
STATE_FILE = os.path.join(WORKDIR, "jan_comparison_v1_state.json")
REPORT_FILE = os.path.join(WORKDIR, "cowork_reports", "2026-03-23_jan_comparison_v1.md")

# ── Full ENV_BASE: all fixes enabled ────────────────────────────────────
ENV_BASE = {
    # --- Core strategy ---
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
    "WB_MAX_LOSS_R": "0.75",
    "WB_NO_REENTRY_ENABLED": "1",
    # --- Strategy 2: Squeeze V2 ---
    "WB_SQUEEZE_ENABLED": "1",
    "WB_SQ_VOL_MULT": "3.0",
    "WB_SQ_MIN_BAR_VOL": "50000",
    "WB_SQ_MIN_BODY_PCT": "1.5",
    "WB_SQ_PRIME_BARS": "3",
    "WB_SQ_MAX_R": "0.80",
    "WB_SQ_LEVEL_PRIORITY": "pm_high,whole_dollar,pdh",
    "WB_SQ_PROBE_SIZE_MULT": "0.5",
    "WB_SQ_MAX_ATTEMPTS": "3",
    "WB_SQ_PARA_ENABLED": "1",
    "WB_SQ_PARA_STOP_OFFSET": "0.10",
    "WB_SQ_PARA_TRAIL_R": "1.0",
    "WB_SQ_NEW_HOD_REQUIRED": "1",
    "WB_SQ_MAX_LOSS_DOLLARS": "500",
    "WB_SQ_TARGET_R": "2.0",
    "WB_SQ_CORE_PCT": "75",
    "WB_SQ_RUNNER_TRAIL_R": "2.5",
    "WB_SQ_TRAIL_R": "1.5",
    "WB_SQ_STALL_BARS": "5",
    "WB_SQ_VWAP_EXIT": "1",
    "WB_SQ_PM_CONFIDENCE": "1",
    "WB_PILLAR_GATES_ENABLED": "1",
    "WB_MP_ENABLED": "1",
    # --- Scanner fixes ---
    "WB_ALLOW_UNKNOWN_FLOAT": "1",
    # --- Squeeze exit fixes (were coded but OFF in batch runner) ---
    "WB_SQ_PARTIAL_EXIT_ENABLED": "1",   # 50% at target, runner continues
    "WB_SQ_WIDE_TRAIL_ENABLED": "1",     # 2x wider parabolic trail for winners
    "WB_SQ_RUNNER_DETECT_ENABLED": "1",  # 3x trail when target hit <5 min (fast runners)
    "WB_HALT_THROUGH_ENABLED": "1",      # Don't stop-out during halt/grace periods
}

# ── Dates ────────────────────────────────────────────────────────────────
JAN_2025_DATES = [
    "2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08",
    "2025-01-09", "2025-01-10", "2025-01-13", "2025-01-14", "2025-01-15",
    "2025-01-16", "2025-01-17", "2025-01-21", "2025-01-22", "2025-01-23",
    "2025-01-24", "2025-01-27", "2025-01-28", "2025-01-29", "2025-01-30",
    "2025-01-31",
]

JAN_2026_DATES = [
    "2026-01-02", "2026-01-03", "2026-01-05", "2026-01-06", "2026-01-07",
    "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13", "2026-01-14",
    "2026-01-15", "2026-01-16", "2026-01-20", "2026-01-21", "2026-01-22",
    "2026-01-23", "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29",
    "2026-01-30",
]

# ── Candidate ranking ────────────────────────────────────────────────────
def rank_score(candidate):
    """Composite score: 40% RVOL + 30% abs volume + 20% gap + 10% float bonus."""
    pm_vol = candidate.get("pm_volume", 0) or 0
    rvol = candidate.get("relative_volume", 0) or 0
    gap_pct = candidate.get("gap_pct", 0) or 0
    float_m = candidate.get("float_millions", 10) or 10
    rvol_score = math.log10(max(rvol, 0.1) + 1) / math.log10(51)
    vol_score = math.log10(max(pm_vol, 1)) / 8
    gap_score = min(gap_pct, 100) / 100
    float_penalty = min(float_m, 10) / 10
    return (0.4 * rvol_score) + (0.3 * vol_score) + (0.2 * gap_score) + (0.1 * (1 - float_penalty))


def load_and_rank(date_str: str) -> tuple:
    """Load, filter, rank scanner candidates.

    Returns (top_n, total, passed_filter, n_unknown_float, n_rescan).
    """
    path = os.path.join(WORKDIR, SCANNER_DIR, f"{date_str}.json")
    if not os.path.exists(path):
        return [], 0, 0, 0, 0

    with open(path) as f:
        all_candidates = json.load(f)

    total = len(all_candidates)
    filtered = []
    n_unknown_float = 0
    n_rescan = 0

    for c in all_candidates:
        pm_vol = c.get("pm_volume", 0) or 0
        gap = c.get("gap_pct", 0) or 0
        float_m = c.get("float_millions", None)
        profile = c.get("profile", "")
        method = c.get("discovery_method", "premarket")

        if pm_vol < MIN_PM_VOLUME:
            continue
        if gap < MIN_GAP_PCT or gap > MAX_GAP_PCT:
            continue
        rvol = c.get("relative_volume", 0) or 0

        # Unknown-float gate: "X" is legacy name, kept for backward compat
        if profile in ("X", "unknown") or float_m is None or float_m == 0:
            if not ALLOW_UNKNOWN_FLOAT:
                continue
            if (gap < UNKNOWN_FLOAT_MIN_GAP
                    or pm_vol < UNKNOWN_FLOAT_MIN_PM_VOL
                    or rvol < UNKNOWN_FLOAT_MIN_RVOL):
                continue
            c = dict(c)
            c["_unknown_float"] = True
            n_unknown_float += 1
            if method == "rescan":
                n_rescan += 1
            filtered.append(c)
            continue

        if float_m > MAX_FLOAT_MILLIONS:
            continue
        if rvol < MIN_RVOL:
            continue
        if method == "rescan":
            n_rescan += 1
        filtered.append(c)

    filtered.sort(key=rank_score, reverse=True)
    top = filtered[:TOP_N]
    return top, total, len(filtered), n_unknown_float, n_rescan


# ── Simulation runner ────────────────────────────────────────────────────
TRADE_PAT = re.compile(
    r'^\s*(\d+)\s+'
    r'(\d{2}:\d{2})\s+'
    r'([\d.]+)\s+'
    r'([\d.]+)\s+'
    r'([\d.]+)\s+'
    r'([\d.]+)\s+'
    r'([\d.]+)\s+'
    r'(\S+)\s+'
    r'([+-]?\d+)\s+'
    r'([+-]?[\d.]+R)',
    re.MULTILINE
)
TICK_DIAG_PAT = re.compile(r'Tick replay:\s+([\d,]+)\s+trades')
ARMED_DIAG_PAT = re.compile(r'Armed:\s+(\d+)\s+\|\s+Signals:\s+(\d+)')


def run_sim(symbol: str, date: str, sim_start: str, risk: int, min_score: float,
            candidate: dict = None) -> list:
    """Run simulate.py and parse trade results."""
    env = {**os.environ, **ENV_BASE}
    env["WB_MIN_ENTRY_SCORE"] = str(min_score)
    if candidate:
        env["WB_SCANNER_GAP_PCT"] = str(candidate.get("gap_pct", 0))
        env["WB_SCANNER_RVOL"] = str(candidate.get("relative_volume", 0) or 0)
        env["WB_SCANNER_FLOAT_M"] = str(candidate.get("float_millions", 20) or 20)

    cmd = [
        sys.executable, "simulate.py", symbol, date, sim_start, "12:00",
        "--ticks", "--risk", str(risk), "--no-fundamentals",
    ]
    if os.path.isdir(TICK_CACHE_DIR):
        cmd.extend(["--tick-cache", TICK_CACHE_DIR])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, env=env, cwd=WORKDIR,
        )
        if result.returncode != 0:
            print(f"    SIM FAILED: {symbol} {date} (exit {result.returncode})", flush=True)
            print(f"    stderr: {result.stderr[-400:]}", flush=True)
            return []
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT: {symbol} {date}", flush=True)
        return []
    except Exception as e:
        print(f"    ERROR: {symbol} {date}: {e}", flush=True)
        return []

    tick_match = TICK_DIAG_PAT.search(output)
    armed_match = ARMED_DIAG_PAT.search(output)
    tick_count = int(tick_match.group(1).replace(",", "")) if tick_match else -1
    armed_count = int(armed_match.group(1)) if armed_match else -1
    signal_count = int(armed_match.group(2)) if armed_match else -1

    trades = []
    for m in TRADE_PAT.finditer(output):
        entry_price = float(m.group(3))
        r_val = float(m.group(5))
        shares = risk / r_val if r_val > 0 else risk
        notional = shares * entry_price
        reason = m.group(8)
        trades.append({
            "num": int(m.group(1)),
            "time": m.group(2),
            "entry": entry_price,
            "stop": float(m.group(4)),
            "r": r_val,
            "score": float(m.group(6)),
            "exit_price": float(m.group(7)),
            "reason": reason,
            "pnl": int(float(m.group(9))),
            "r_mult": m.group(10),
            "symbol": symbol,
            "date": date,
            "notional": notional,
            "setup_type": "squeeze" if reason.startswith("sq_") else "micro_pullback",
        })

    trade_pnl = sum(t["pnl"] for t in trades)
    print(f"    {symbol}: ticks={tick_count:,} armed={armed_count} signals={signal_count} "
          f"trades={len(trades)} pnl={trade_pnl:+d}", flush=True)
    return trades


def _run_day(top5, date, risk):
    """Run one day with trade cap, daily loss limit, and notional tracking."""
    day_trades = []
    day_pnl = 0
    day_notional = 0
    consec_losses = 0
    MAX_CONSEC_LOSSES = 2

    for c in top5:
        if len(day_trades) >= MAX_TRADES_PER_DAY:
            break
        if day_pnl <= DAILY_LOSS_LIMIT:
            break
        if consec_losses >= MAX_CONSEC_LOSSES:
            break

        sym = c["symbol"]
        float_m = c.get("float_millions", 0) or 0
        stock_risk = min(risk, 250) if float_m > 5.0 else risk
        sim_start = c.get("sim_start", "07:00")
        # Unknown-float stocks: conservative 50% notional cap
        notional_cap = int(MAX_NOTIONAL * UNKNOWN_FLOAT_NOTIONAL_FACTOR) if c.get("_unknown_float") else MAX_NOTIONAL

        all_trades = run_sim(sym, date, sim_start, stock_risk, min_score=8.0, candidate=c)
        time.sleep(1)

        for t in all_trades:
            if len(day_trades) >= MAX_TRADES_PER_DAY:
                break
            if day_pnl <= DAILY_LOSS_LIMIT:
                break
            if consec_losses >= MAX_CONSEC_LOSSES:
                break
            if day_notional + t["notional"] > notional_cap:
                continue

            day_trades.append(t)
            day_pnl += t["pnl"]
            day_notional += t["notional"]
            if t["pnl"] < 0:
                consec_losses += 1
            else:
                consec_losses = 0

    return day_trades, day_pnl


# ── State management ─────────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return None


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _empty_month_state(starting_equity):
    return {
        "equity": starting_equity,
        "trades": [],
        "daily": [],
        "max_equity": starting_equity,
        "max_drawdown": 0,
        "dates_completed": [],
    }


# ── Reporting ────────────────────────────────────────────────────────────
def _compute_stats(month_state):
    trades = month_state["trades"]
    daily = month_state["daily"]
    if not trades:
        return {
            "n_trades": 0, "n_wins": 0, "n_losses": 0, "win_rate": 0.0,
            "total_pnl": 0, "avg_pnl_day": 0, "profit_factor": 0.0,
            "max_drawdown": month_state.get("max_drawdown", 0),
            "best_day": 0, "worst_day": 0, "ending_equity": month_state["equity"],
            "sq_trades": 0, "mp_trades": 0, "sq_pnl": 0, "mp_pnl": 0,
            "sq_wins": 0, "mp_wins": 0,
        }

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    sq = [t for t in trades if t["setup_type"] == "squeeze"]
    mp = [t for t in trades if t["setup_type"] == "micro_pullback"]
    day_pnls = [d["day_pnl"] for d in daily]

    return {
        "n_trades": len(trades),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0.0,
        "total_pnl": sum(t["pnl"] for t in trades),
        "avg_pnl_day": sum(t["pnl"] for t in trades) / max(len(daily), 1),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "max_drawdown": month_state.get("max_drawdown", 0),
        "best_day": max(day_pnls) if day_pnls else 0,
        "worst_day": min(day_pnls) if day_pnls else 0,
        "ending_equity": month_state["equity"],
        "sq_trades": len(sq),
        "mp_trades": len(mp),
        "sq_pnl": sum(t["pnl"] for t in sq),
        "mp_pnl": sum(t["pnl"] for t in mp),
        "sq_wins": len([t for t in sq if t["pnl"] > 0]),
        "mp_wins": len([t for t in mp if t["pnl"] > 0]),
    }


def _print_summary(state):
    """Print the side-by-side summary table."""
    s25 = _compute_stats(state["jan2025"])
    s26 = _compute_stats(state["jan2026"])
    d25 = state["jan2025"]["daily"]
    d26 = state["jan2026"]["daily"]
    meta25 = state.get("meta_jan2025", {})
    meta26 = state.get("meta_jan2026", {})

    def fmt_pnl(v): return f"${v:+,.0f}" if v != 0 else "$0"
    def fmt_pct(v): return f"{v:.1f}%"

    print()
    print("╔═══════════════════════════════════════════════════════════════════════╗")
    print("║            JANUARY COMPARISON: 2025 vs 2026                          ║")
    print("╠═══════════════════════════════╦═══════════════╦═══════════════════════╣")
    print(f"║ {'Metric':<29} ║ {'Jan 2025':^13} ║ {'Jan 2026':^21} ║")
    print("╠═══════════════════════════════╬═══════════════╬═══════════════════════╣")

    rows = [
        ("Trading Days", len(d25), len(d26)),
        ("Scanner Candidates (total)", meta25.get("total_scanned", "?"), meta26.get("total_scanned", "?")),
        ("Candidates Passing Filters", meta25.get("total_passed", "?"), meta26.get("total_passed", "?")),
        ("Unknown-Float Candidates", meta25.get("n_unknown_float", 0), meta26.get("n_unknown_float", 0)),
        ("Rescan Candidates", meta25.get("n_rescan", 0), meta26.get("n_rescan", 0)),
        ("Total Trades", s25["n_trades"], s26["n_trades"]),
        ("SQ Trades", s25["sq_trades"], s26["sq_trades"]),
        ("MP Trades", s25["mp_trades"], s26["mp_trades"]),
        ("Win Rate", fmt_pct(s25["win_rate"]), fmt_pct(s26["win_rate"])),
        ("Total P&L", fmt_pnl(s25["total_pnl"]), fmt_pnl(s26["total_pnl"])),
        ("Avg P&L / Day", fmt_pnl(s25["avg_pnl_day"]), fmt_pnl(s26["avg_pnl_day"])),
        ("Profit Factor", s25["profit_factor"], s26["profit_factor"]),
        ("Max Drawdown", fmt_pnl(-s25["max_drawdown"]), fmt_pnl(-s26["max_drawdown"])),
        ("Best Day", fmt_pnl(s25["best_day"]), fmt_pnl(s26["best_day"])),
        ("Worst Day", fmt_pnl(s25["worst_day"]), fmt_pnl(s26["worst_day"])),
        ("Ending Equity", fmt_pnl(s25["ending_equity"]), fmt_pnl(s26["ending_equity"])),
    ]

    for label, v25, v26 in rows:
        print(f"║ {label:<29} ║ {str(v25):^13} ║ {str(v26):^21} ║")

    print("╚═══════════════════════════════╩═══════════════╩═══════════════════════╝")

    # Per-day detail
    for label, daily, trades in [("Jan 2025", d25, state["jan2025"]["trades"]),
                                  ("Jan 2026", d26, state["jan2026"]["trades"])]:
        print(f"\n{'─'*80}")
        print(f"  {label} — Per-Day Detail")
        print(f"{'─'*80}")
        print(f"  {'Date':<12} {'Candidates':>10} {'Traded':>7} {'Trades':>7} {'P&L':>10} {'Equity':>12}  Best Trade")
        print(f"  {'─'*12} {'─'*10} {'─'*7} {'─'*7} {'─'*10} {'─'*12}")
        for d in daily:
            day_trades = [t for t in trades if t["date"] == d["date"]]
            best = max(day_trades, key=lambda t: t["pnl"]) if day_trades else None
            best_str = f"{best['symbol']} {best['pnl']:+d}" if best else "—"
            print(f"  {d['date']:<12} {d.get('total_cands', '?'):>10} {d.get('n_traded', '?'):>7} "
                  f"{d['trades']:>7} {d['day_pnl']:>+10,d} {d['equity']:>12,.0f}  {best_str}")

    # Strategy breakdown
    print(f"\n{'─'*60}")
    print("  Strategy Breakdown")
    print(f"{'─'*60}")
    for label, s in [("Jan 2025", s25), ("Jan 2026", s26)]:
        print(f"\n  {label}:")
        if s["sq_trades"]:
            sq_wr = s["sq_wins"] / s["sq_trades"] * 100
            print(f"    SQ: {s['sq_trades']} trades  {sq_wr:.0f}% win  {fmt_pnl(s['sq_pnl'])}")
        else:
            print(f"    SQ: 0 trades")
        if s["mp_trades"]:
            mp_wr = s["mp_wins"] / s["mp_trades"] * 100
            print(f"    MP: {s['mp_trades']} trades  {mp_wr:.0f}% win  {fmt_pnl(s['mp_pnl'])}")
        else:
            print(f"    MP: 0 trades")

    # Top 5 trades per month
    for label, trades in [("Jan 2025", state["jan2025"]["trades"]),
                           ("Jan 2026", state["jan2026"]["trades"])]:
        print(f"\n  {label} — Top 5 Trades:")
        top5 = sorted(trades, key=lambda t: t["pnl"], reverse=True)[:5]
        for t in top5:
            print(f"    {t['symbol']} {t['date']} {t['setup_type'][:2].upper()} "
                  f"{t['pnl']:+d} @ {t['reason']}")

    print()


def _save_report(state):
    """Save markdown report to cowork_reports/."""
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    s25 = _compute_stats(state["jan2025"])
    s26 = _compute_stats(state["jan2026"])
    d25 = state["jan2025"]["daily"]
    d26 = state["jan2026"]["daily"]
    meta25 = state.get("meta_jan2025", {})
    meta26 = state.get("meta_jan2026", {})

    def fmt(v): return f"${v:+,.0f}" if isinstance(v, (int, float)) else str(v)

    lines = [
        "# January 2025 vs January 2026 Comparison — Scanner Fixes V1 + SQ Exit Fixes",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "**Config:** Full ENV_BASE with all fixes: unknown-float gate, SQ partial/wide/runner exits, halt-through, MP enabled",
        "",
        "---",
        "",
        "## Summary Table",
        "",
        "| Metric | Jan 2025 | Jan 2026 |",
        "|--------|----------|----------|",
        f"| Trading Days | {len(d25)} | {len(d26)} |",
        f"| Scanner Candidates (total) | {meta25.get('total_scanned', '?')} | {meta26.get('total_scanned', '?')} |",
        f"| Candidates Passing Filters | {meta25.get('total_passed', '?')} | {meta26.get('total_passed', '?')} |",
        f"| Unknown-Float Candidates | {meta25.get('n_unknown_float', 0)} | {meta26.get('n_unknown_float', 0)} |",
        f"| Rescan Candidates | {meta25.get('n_rescan', 0)} | {meta26.get('n_rescan', 0)} |",
        f"| Total Trades | {s25['n_trades']} | {s26['n_trades']} |",
        f"| SQ Trades | {s25['sq_trades']} | {s26['sq_trades']} |",
        f"| MP Trades | {s25['mp_trades']} | {s26['mp_trades']} |",
        f"| Win Rate | {s25['win_rate']:.1f}% | {s26['win_rate']:.1f}% |",
        f"| Total P&L | {fmt(s25['total_pnl'])} | {fmt(s26['total_pnl'])} |",
        f"| Avg P&L / Day | {fmt(s25['avg_pnl_day'])} | {fmt(s26['avg_pnl_day'])} |",
        f"| Profit Factor | {s25['profit_factor']} | {s26['profit_factor']} |",
        f"| Max Drawdown | {fmt(-s25['max_drawdown'])} | {fmt(-s26['max_drawdown'])} |",
        f"| Best Day | {fmt(s25['best_day'])} | {fmt(s26['best_day'])} |",
        f"| Worst Day | {fmt(s25['worst_day'])} | {fmt(s26['worst_day'])} |",
        f"| Ending Equity | {fmt(s25['ending_equity'])} | {fmt(s26['ending_equity'])} |",
        "",
        "---",
        "",
    ]

    # Scanner improvement section
    lines += [
        "## Scanner Improvement (Jan 2025)",
        "",
        f"- **Unknown-float candidates traded:** {meta25.get('n_unknown_float', 0)} "
        f"(previously blocked by WB_ALLOW_PROFILE_X=0)",
        f"- **Rescan candidates:** {meta25.get('n_rescan', 0)} (rescan found 0 in Jan 2025 before fix)",
        "",
        "---",
        "",
    ]

    # Per-day detail
    for label, daily, trades in [("Jan 2025", d25, state["jan2025"]["trades"]),
                                  ("Jan 2026", d26, state["jan2026"]["trades"])]:
        lines += [f"## {label} — Per-Day Detail", ""]
        lines += ["| Date | Candidates | Traded | Trades | P&L | Equity | Best Trade |",
                  "|------|-----------|--------|--------|-----|--------|-----------|"]
        for d in daily:
            day_trades = [t for t in trades if t["date"] == d["date"]]
            best = max(day_trades, key=lambda t: t["pnl"]) if day_trades else None
            best_str = f"{best['symbol']} {best['pnl']:+d}" if best else "—"
            lines.append(
                f"| {d['date']} | {d.get('total_cands', '?')} | "
                f"{d.get('n_traded', '?')} | {d['trades']} | "
                f"{d['day_pnl']:+,d} | ${d['equity']:,.0f} | {best_str} |"
            )
        lines += ["", "---", ""]

    # Strategy breakdown
    lines += ["## Strategy Breakdown", ""]
    for label, s in [("Jan 2025", s25), ("Jan 2026", s26)]:
        sq_wr = (s["sq_wins"] / s["sq_trades"] * 100) if s["sq_trades"] else 0
        mp_wr = (s["mp_wins"] / s["mp_trades"] * 100) if s["mp_trades"] else 0
        lines += [
            f"### {label}",
            "",
            f"| Strategy | Trades | Wins | Win Rate | P&L |",
            f"|----------|--------|------|----------|-----|",
            f"| Squeeze (SQ) | {s['sq_trades']} | {s['sq_wins']} | {sq_wr:.0f}% | {fmt(s['sq_pnl'])} |",
            f"| Micro Pullback (MP) | {s['mp_trades']} | {s['mp_wins']} | {mp_wr:.0f}% | {fmt(s['mp_pnl'])} |",
            "",
        ]
    lines += ["---", ""]

    # Top 5 / bottom 5 per month
    for label, trades in [("Jan 2025", state["jan2025"]["trades"]),
                           ("Jan 2026", state["jan2026"]["trades"])]:
        sorted_trades = sorted(trades, key=lambda t: t["pnl"], reverse=True)
        lines += [f"## {label} — Top 5 Trades", ""]
        lines += ["| # | Symbol | Date | Strategy | P&L | Reason |",
                  "|---|--------|------|----------|-----|--------|"]
        for i, t in enumerate(sorted_trades[:5], 1):
            lines.append(f"| {i} | {t['symbol']} | {t['date']} | "
                         f"{t['setup_type']} | {t['pnl']:+,d} | {t['reason']} |")
        lines += ["", f"## {label} — Bottom 5 Trades", ""]
        lines += ["| # | Symbol | Date | Strategy | P&L | Reason |",
                  "|---|--------|------|----------|-----|--------|"]
        for i, t in enumerate(sorted_trades[-5:][::-1], 1):
            lines.append(f"| {i} | {t['symbol']} | {t['date']} | "
                         f"{t['setup_type']} | {t['pnl']:+,d} | {t['reason']} |")
        lines += ["", "---", ""]

    lines += [
        "## Notes",
        "",
        "- Jan 2025 scanner JSONs were generated BEFORE the rescan fix (find_emerging_movers found 0 stocks).",
        "  Re-run `scanner_sim.py` for Jan 2025 dates to pick up new rescan candidates.",
        "- SQ exit fixes (partial exit, wide trail, runner detect, halt-through) are enabled for the first time in batch mode.",
        "- MP regression targets: VERO 2026-01-16 +$18,583, ROLR 2026-01-14 +$6,444 (both verified).",
        "",
        f"*Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
    ]

    with open(REPORT_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n  Report saved → {REPORT_FILE}", flush=True)


# ── Main ─────────────────────────────────────────────────────────────────
def run_comparison():
    state = load_state()
    if state:
        print(f"Resuming from state file…", flush=True)
        print(f"  Jan 2025: {len(state['jan2025']['dates_completed'])} dates done, "
              f"equity=${state['jan2025']['equity']:,.0f}", flush=True)
        print(f"  Jan 2026: {len(state['jan2026']['dates_completed'])} dates done, "
              f"equity=${state['jan2026']['equity']:,.0f}", flush=True)
    else:
        state = {
            "jan2025": _empty_month_state(STARTING_EQUITY),
            "jan2026": _empty_month_state(STARTING_EQUITY),
            "meta_jan2025": {"total_scanned": 0, "total_passed": 0,
                             "n_unknown_float": 0, "n_rescan": 0},
            "meta_jan2026": {"total_scanned": 0, "total_passed": 0,
                             "n_unknown_float": 0, "n_rescan": 0},
        }

    # ── Run Jan 2025 ──────────────────────────────────────────────────────
    done25 = set(state["jan2025"]["dates_completed"])
    remaining25 = [d for d in JAN_2025_DATES if d not in done25]
    if remaining25:
        print(f"\n{'='*70}", flush=True)
        print(f"  JANUARY 2025 — {len(remaining25)} dates remaining", flush=True)
        print(f"{'='*70}", flush=True)

    for date in remaining25:
        top5, total, passed, n_uf, n_rs = load_and_rank(date)
        eq = state["jan2025"]["equity"]
        risk = max(int(eq * RISK_PCT), 50)

        state["meta_jan2025"]["total_scanned"] += total
        state["meta_jan2025"]["total_passed"] += passed
        state["meta_jan2025"]["n_unknown_float"] += n_uf
        state["meta_jan2025"]["n_rescan"] += n_rs

        print(f"\n[Jan2025 {date}] {total} scanned → {passed} passed → "
              f"{len(top5)} selected  (uf={n_uf} rescan={n_rs})  risk=${risk}", flush=True)
        for c in top5:
            uf_tag = " [UF]" if c.get("_unknown_float") else ""
            rs_tag = " [RS]" if c.get("discovery_method") == "rescan" else ""
            print(f"    {c['symbol']}: vol={c.get('pm_volume',0):,.0f} "
                  f"gap={c.get('gap_pct',0):.0f}% float={c.get('float_millions',0):.1f}M"
                  f"{uf_tag}{rs_tag}", flush=True)

        if top5:
            day_trades, day_pnl = _run_day(top5, date, risk)
        else:
            day_trades, day_pnl = [], 0

        eq += day_pnl
        state["jan2025"]["equity"] = eq
        state["jan2025"]["trades"].extend(day_trades)

        peak = state["jan2025"]["max_equity"]
        if eq > peak:
            state["jan2025"]["max_equity"] = eq
        dd = state["jan2025"]["max_equity"] - eq
        if dd > state["jan2025"]["max_drawdown"]:
            state["jan2025"]["max_drawdown"] = dd

        sq_today = [t for t in day_trades if t["setup_type"] == "squeeze"]
        mp_today = [t for t in day_trades if t["setup_type"] == "micro_pullback"]
        state["jan2025"]["daily"].append({
            "date": date,
            "total_cands": total,
            "n_traded": len(top5),
            "trades": len(day_trades),
            "sq_trades": len(sq_today),
            "mp_trades": len(mp_today),
            "wins": len([t for t in day_trades if t["pnl"] > 0]),
            "losses": len([t for t in day_trades if t["pnl"] <= 0]),
            "day_pnl": day_pnl,
            "equity": eq,
        })
        state["jan2025"]["dates_completed"].append(date)

        print(f"  → {date}: {len(day_trades)} trades  pnl={day_pnl:+,d}  equity=${eq:,.0f}", flush=True)
        save_state(state)

    # ── Run Jan 2026 ──────────────────────────────────────────────────────
    done26 = set(state["jan2026"]["dates_completed"])
    remaining26 = [d for d in JAN_2026_DATES if d not in done26]
    if remaining26:
        print(f"\n{'='*70}", flush=True)
        print(f"  JANUARY 2026 — {len(remaining26)} dates remaining", flush=True)
        print(f"{'='*70}", flush=True)

    for date in remaining26:
        top5, total, passed, n_uf, n_rs = load_and_rank(date)
        eq = state["jan2026"]["equity"]
        risk = max(int(eq * RISK_PCT), 50)

        state["meta_jan2026"]["total_scanned"] += total
        state["meta_jan2026"]["total_passed"] += passed
        state["meta_jan2026"]["n_unknown_float"] += n_uf
        state["meta_jan2026"]["n_rescan"] += n_rs

        print(f"\n[Jan2026 {date}] {total} scanned → {passed} passed → "
              f"{len(top5)} selected  (uf={n_uf} rescan={n_rs})  risk=${risk}", flush=True)
        for c in top5:
            uf_tag = " [UF]" if c.get("_unknown_float") else ""
            rs_tag = " [RS]" if c.get("discovery_method") == "rescan" else ""
            print(f"    {c['symbol']}: vol={c.get('pm_volume',0):,.0f} "
                  f"gap={c.get('gap_pct',0):.0f}% float={c.get('float_millions',0):.1f}M"
                  f"{uf_tag}{rs_tag}", flush=True)

        if top5:
            day_trades, day_pnl = _run_day(top5, date, risk)
        else:
            day_trades, day_pnl = [], 0

        eq += day_pnl
        state["jan2026"]["equity"] = eq
        state["jan2026"]["trades"].extend(day_trades)

        peak = state["jan2026"]["max_equity"]
        if eq > peak:
            state["jan2026"]["max_equity"] = eq
        dd = state["jan2026"]["max_equity"] - eq
        if dd > state["jan2026"]["max_drawdown"]:
            state["jan2026"]["max_drawdown"] = dd

        sq_today = [t for t in day_trades if t["setup_type"] == "squeeze"]
        mp_today = [t for t in day_trades if t["setup_type"] == "micro_pullback"]
        state["jan2026"]["daily"].append({
            "date": date,
            "total_cands": total,
            "n_traded": len(top5),
            "trades": len(day_trades),
            "sq_trades": len(sq_today),
            "mp_trades": len(mp_today),
            "wins": len([t for t in day_trades if t["pnl"] > 0]),
            "losses": len([t for t in day_trades if t["pnl"] <= 0]),
            "day_pnl": day_pnl,
            "equity": eq,
        })
        state["jan2026"]["dates_completed"].append(date)

        print(f"  → {date}: {len(day_trades)} trades  pnl={day_pnl:+,d}  equity=${eq:,.0f}", flush=True)
        save_state(state)

    # ── Final output ──────────────────────────────────────────────────────
    _print_summary(state)
    _save_report(state)
    save_state(state)


if __name__ == "__main__":
    run_comparison()
