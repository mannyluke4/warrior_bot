#!/usr/bin/env python3
"""
January 2025 vs January 2026 — V2 (Ross Exit Enabled)
======================================================
Re-runs BOTH months with WB_ROSS_EXIT_ENABLED=1 to measure the impact of
1m signal-based exits. This is the A/B counterpart to V1 (which ran without
Ross exit).

V1 baselines:
  Jan 2025: 21 days, 32 trades, +$3,423
  Jan 2026: 21 days, 15 trades, +$17,728

Usage:
    source venv/bin/activate
    python run_jan_v2_comparison.py 2>&1 | tee jan_comparison_v2_output.txt

Fresh start: uses jan_comparison_v2_state.json (NOT V1 state).
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


# V1 baselines for comparison report
V1_JAN2025_PNL = 3_423
V1_JAN2025_TRADES = 32
V1_JAN2025_WIN_RATE = 43.8  # 14/32
V1_JAN2026_PNL = 17_728
V1_JAN2026_TRADES = 15
V1_JAN2026_WIN_RATE = 46.7  # 7/15
V1_VERO_PNL = 18_583
V1_ROLR_PNL = 6_444

WORKDIR = os.getenv("WB_WORKDIR", os.path.dirname(os.path.abspath(__file__)))
SCANNER_DIR = "scanner_results"
TICK_CACHE_DIR = os.path.join(WORKDIR, "tick_cache")
STATE_FILE = os.path.join(WORKDIR, "jan_comparison_v2_state.json")
REPORT_FILE = os.path.join(WORKDIR, "cowork_reports", "2026-03-23_jan_comparison_v2.md")

# ── Full ENV_BASE: all V1 fixes + Ross exit ──────────────────────────────
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
    # --- Squeeze exit fixes ---
    "WB_SQ_PARTIAL_EXIT_ENABLED": "1",
    "WB_SQ_WIDE_TRAIL_ENABLED": "1",
    "WB_SQ_RUNNER_DETECT_ENABLED": "1",
    "WB_HALT_THROUGH_ENABLED": "1",
    # --- NEW in V2: Ross Cameron 1m signal exits ---
    "WB_ROSS_EXIT_ENABLED": "1",           # Master switch — replaces 10s BE/TW exits
    "WB_ROSS_MIN_BARS": "2",               # Min 1m bars before any signal fires
    "WB_ROSS_CUC_ENABLED": "1",            # Candle Under Candle → 100% exit
    "WB_ROSS_DOJI_ENABLED": "1",           # Doji → 50% partial
    "WB_ROSS_GRAVESTONE_ENABLED": "1",     # Gravestone doji → 100% exit
    "WB_ROSS_SHOOTING_STAR_ENABLED": "1",  # Shooting star → 100% exit
    "WB_ROSS_TOPPING_TAIL_ENABLED": "1",   # Topping tail (green w/ big wick) → 50% partial
    "WB_ROSS_MACD_ENABLED": "1",           # MACD histogram negative → 100% backstop
    "WB_ROSS_EMA20_ENABLED": "1",          # Close below 20 EMA → 100% backstop
    "WB_ROSS_VWAP_ENABLED": "1",           # Close below VWAP → 100% backstop
    "WB_ROSS_STRUCTURAL_TRAIL": "1",       # Trail = low of last green 1m candle
    "WB_ROSS_CUC_FLOOR_R": "0.0",          # CUC fires at any R
    "WB_ROSS_CUC_MIN_TRADE_BARS": "0",     # No CUC suppression window
    "WB_ROSS_BACKSTOP_MIN_R": "0.0",       # Backstops always full strength
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

        if float_m is not None and float_m > 0 and float_m > MAX_FLOAT_MILLIONS:
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
        env["WB_SCANNER_GAP_PCT"] = str(candidate.get("gap_pct", 0) or 0)
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
        notional_cap = MAX_NOTIONAL

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


# ── Stats ─────────────────────────────────────────────────────────────────
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


def _exit_reason_breakdown(trades):
    """Group trades by exit reason prefix for Ross exit analysis."""
    ROSS_REASONS = [
        "ross_cuc", "ross_doji_partial", "ross_gravestone",
        "ross_shooting_star", "ross_topping_tail",
        "ross_macd_backstop", "ross_ema20_backstop", "ross_vwap_backstop",
        "ross_structural_trail",
    ]
    buckets = {r: [] for r in ROSS_REASONS}
    buckets["non_ross"] = []

    for t in trades:
        reason = t.get("reason", "")
        matched = False
        for r in ROSS_REASONS:
            if reason.startswith(r):
                buckets[r].append(t)
                matched = True
                break
        if not matched:
            buckets["non_ross"].append(t)

    return buckets


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
    print("║        JANUARY COMPARISON V2 (Ross Exit ON): 2025 vs 2026            ║")
    print("╠═══════════════════════════════╦═══════════════╦═══════════════════════╣")
    print(f"║ {'Metric':<29} ║ {'Jan 2025':^13} ║ {'Jan 2026':^21} ║")
    print("╠═══════════════════════════════╬═══════════════╬═══════════════════════╣")

    rows = [
        ("Trading Days", len(d25), len(d26)),
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

    # Exit reason breakdown
    all_trades = state["jan2025"]["trades"] + state["jan2026"]["trades"]
    if all_trades:
        print(f"\n{'─'*60}")
        print("  Exit Reason Breakdown (V2 — Ross exit ON)")
        print(f"{'─'*60}")
        buckets = _exit_reason_breakdown(all_trades)
        for reason, ts in buckets.items():
            if ts:
                avg_pnl = sum(t["pnl"] for t in ts) / len(ts)
                wins = len([t for t in ts if t["pnl"] > 0])
                print(f"  {reason:<30} n={len(ts):>3}  wins={wins:>3}  avg_pnl={avg_pnl:>+8.0f}")

    print()


def _save_report(state, v2_vero_pnl=None, v2_rolr_pnl=None):
    """Save markdown report to cowork_reports/ with V1 vs V2 comparison."""
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    s25 = _compute_stats(state["jan2025"])
    s26 = _compute_stats(state["jan2026"])
    d25 = state["jan2025"]["daily"]
    d26 = state["jan2026"]["daily"]
    meta25 = state.get("meta_jan2025", {})
    meta26 = state.get("meta_jan2026", {})

    all_trades = state["jan2025"]["trades"] + state["jan2026"]["trades"]
    buckets = _exit_reason_breakdown(all_trades)

    def fmt(v):
        if isinstance(v, float) and math.isinf(v):
            return "∞"
        return f"${v:+,.0f}" if isinstance(v, (int, float)) else str(v)

    def delta(v2, v1):
        d = v2 - v1
        sign = "+" if d >= 0 else ""
        return f"{sign}${d:,.0f}"

    def delta_pct(v2, v1):
        d = v2 - v1
        sign = "+" if d >= 0 else ""
        return f"{sign}{d:.1f}%"

    v2_combined = s25["total_pnl"] + s26["total_pnl"]
    v1_combined = V1_JAN2025_PNL + V1_JAN2026_PNL
    v2_vero_str = f"${v2_vero_pnl:+,}" if v2_vero_pnl is not None else "N/A"
    v2_rolr_str = f"${v2_rolr_pnl:+,}" if v2_rolr_pnl is not None else "N/A"

    lines = [
        "# January 2025 vs January 2026 — V2 (Ross Cameron Exit Enabled)",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "**Config:** Full V1 ENV_BASE + WB_ROSS_EXIT_ENABLED=1 (all Ross exit signals ON)",
        "**Baseline:** V1 ran same config without Ross exit",
        "",
        "---",
        "",
        "## Section 1: Ross Exit A/B — V1 vs V2 Summary",
        "",
        "```",
        "╔════════════════════════════════════════════════════════════════════════════════════╗",
        "║            ROSS EXIT A/B: V1 (no Ross) vs V2 (Ross ON)                           ║",
        "╠═══════════════════════════════╦═══════════════╦═══════════════╦════════════════════╣",
        "║ Metric                        ║  V1 (no Ross) ║  V2 (Ross ON) ║  Delta            ║",
        "╠═══════════════════════════════╬═══════════════╬═══════════════╬════════════════════╣",
        f"║ Jan 2025 Total P&L            ║  {fmt(V1_JAN2025_PNL):>14}  ║  {fmt(s25['total_pnl']):>14}  ║  {delta(s25['total_pnl'], V1_JAN2025_PNL):>16}   ║",
        f"║ Jan 2025 Win Rate             ║  {V1_JAN2025_WIN_RATE:.1f}%            ║  {s25['win_rate']:.1f}%              ║  {delta_pct(s25['win_rate'], V1_JAN2025_WIN_RATE):>16}   ║",
        f"║ Jan 2025 Trades               ║  {V1_JAN2025_TRADES:>14}  ║  {s25['n_trades']:>14}  ║  {s25['n_trades'] - V1_JAN2025_TRADES:>+16}   ║",
        f"║ Jan 2026 Total P&L            ║  {fmt(V1_JAN2026_PNL):>14}  ║  {fmt(s26['total_pnl']):>14}  ║  {delta(s26['total_pnl'], V1_JAN2026_PNL):>16}   ║",
        f"║ Jan 2026 Win Rate             ║  {V1_JAN2026_WIN_RATE:.1f}%            ║  {s26['win_rate']:.1f}%              ║  {delta_pct(s26['win_rate'], V1_JAN2026_WIN_RATE):>16}   ║",
        f"║ Jan 2026 Trades               ║  {V1_JAN2026_TRADES:>14}  ║  {s26['n_trades']:>14}  ║  {s26['n_trades'] - V1_JAN2026_TRADES:>+16}   ║",
        f"║ Combined P&L (both months)    ║  {fmt(v1_combined):>14}  ║  {fmt(v2_combined):>14}  ║  {delta(v2_combined, v1_combined):>16}   ║",
        f"║ VERO standalone               ║  {fmt(V1_VERO_PNL):>14}  ║  {v2_vero_str:>14}  ║  {'N/A' if v2_vero_pnl is None else delta(v2_vero_pnl, V1_VERO_PNL):>16}   ║",
        f"║ ROLR standalone               ║  {fmt(V1_ROLR_PNL):>14}  ║  {v2_rolr_str:>14}  ║  {'N/A' if v2_rolr_pnl is None else delta(v2_rolr_pnl, V1_ROLR_PNL):>16}   ║",
        "╚═══════════════════════════════╩═══════════════╩═══════════════╩════════════════════╝",
        "```",
        "",
        "---",
        "",
        "## Section 2: Per-Month Detail",
        "",
    ]

    # Per-day tables
    for label, daily, trades in [("Jan 2025", d25, state["jan2025"]["trades"]),
                                  ("Jan 2026", d26, state["jan2026"]["trades"])]:
        lines += [f"### {label} — Per-Day Detail", ""]
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

    # Section 3: Exit reason analysis
    lines += [
        "## Section 3: Exit Reason Analysis (V2)",
        "",
        "Ross exit replaces 10s BE/TW patterns. Signal breakdown across both months:",
        "",
        "| Exit Reason | Count | Wins | Win% | Total P&L | Avg P&L |",
        "|-------------|-------|------|------|-----------|---------|",
    ]
    for reason, ts in sorted(buckets.items()):
        if not ts:
            continue
        wins = len([t for t in ts if t["pnl"] > 0])
        total_pnl = sum(t["pnl"] for t in ts)
        avg_pnl = total_pnl / len(ts)
        wr = wins / len(ts) * 100
        lines.append(
            f"| {reason} | {len(ts)} | {wins} | {wr:.0f}% | {total_pnl:+,d} | {avg_pnl:+.0f} |"
        )
    lines += ["", "---", ""]

    # Section 4: Trade-by-trade V1 vs V2 comparison
    lines += [
        "## Section 4: Trade-by-Trade V1 vs V2 Comparison",
        "",
        "For stocks appearing in both runs (same symbol+date):",
        "",
        "| Symbol | Date | V1 Exit Reason | V1 P&L | V2 Exit Reason | V2 P&L | Delta |",
        "|--------|------|---------------|--------|---------------|--------|-------|",
    ]

    # Load V1 state for comparison
    v1_state_path = os.path.join(WORKDIR, "jan_comparison_v1_state.json")
    v1_by_key = {}
    if os.path.exists(v1_state_path):
        with open(v1_state_path) as f:
            v1_state = json.load(f)
        for t in v1_state.get("jan2025", {}).get("trades", []) + v1_state.get("jan2026", {}).get("trades", []):
            key = (t["symbol"], t["date"])
            v1_by_key.setdefault(key, []).append(t)

    v2_by_key = {}
    for t in all_trades:
        key = (t["symbol"], t["date"])
        v2_by_key.setdefault(key, []).append(t)

    all_keys = sorted(set(list(v1_by_key.keys()) + list(v2_by_key.keys())))
    for key in all_keys:
        sym, date = key
        v1_ts = v1_by_key.get(key, [])
        v2_ts = v2_by_key.get(key, [])
        max_len = max(len(v1_ts), len(v2_ts))
        for i in range(max_len):
            v1t = v1_ts[i] if i < len(v1_ts) else None
            v2t = v2_ts[i] if i < len(v2_ts) else None
            v1_reason = v1t["reason"] if v1t else "—"
            v1_pnl = f"{v1t['pnl']:+,d}" if v1t else "—"
            v2_reason = v2t["reason"] if v2t else "—"
            v2_pnl = f"{v2t['pnl']:+,d}" if v2t else "—"
            if v1t and v2t:
                delta_pnl = f"{v2t['pnl'] - v1t['pnl']:+,d}"
            else:
                delta_pnl = "N/A"
            lines.append(
                f"| {sym} | {date} | {v1_reason} | {v1_pnl} | {v2_reason} | {v2_pnl} | {delta_pnl} |"
            )
    lines += ["", "---", ""]

    # Section 5: Strategy breakdown
    lines += ["## Section 5: Strategy Breakdown (SQ vs MP)", ""]
    for label, s, s_v1_trades, s_v1_pnl in [
        ("Jan 2025", s25, V1_JAN2025_TRADES, V1_JAN2025_PNL),
        ("Jan 2026", s26, V1_JAN2026_TRADES, V1_JAN2026_PNL),
    ]:
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

    # Section 6: Verdict
    pnl_delta = v2_combined - v1_combined
    pnl_direction = "improved" if pnl_delta >= 0 else "hurt"
    lines += [
        "## Section 6: Verdict",
        "",
        f"### Net P&L Impact",
        f"- V1 combined: ${v1_combined:+,}",
        f"- V2 combined: ${v2_combined:+,}",
        f"- Delta: {delta(v2_combined, v1_combined)} — Ross exit **{pnl_direction}** total P&L",
        "",
        f"### Win Rate Impact",
        f"- Jan 2025: {V1_JAN2025_WIN_RATE:.1f}% → {s25['win_rate']:.1f}% ({delta_pct(s25['win_rate'], V1_JAN2025_WIN_RATE)})",
        f"- Jan 2026: {V1_JAN2026_WIN_RATE:.1f}% → {s26['win_rate']:.1f}% ({delta_pct(s26['win_rate'], V1_JAN2026_WIN_RATE)})",
        "",
        f"### Strategy Impact",
        f"- SQ Jan2025: {s25['sq_pnl']:+,d} | SQ Jan2026: {s26['sq_pnl']:+,d}",
        f"- MP Jan2025: {s25['mp_pnl']:+,d} | MP Jan2026: {s26['mp_pnl']:+,d}",
        "",
        f"### Top Exit Signals Fired",
    ]
    # Sort by count
    top_signals = sorted([(r, ts) for r, ts in buckets.items() if ts], key=lambda x: -len(x[1]))
    for reason, ts in top_signals[:5]:
        avg = sum(t["pnl"] for t in ts) / len(ts)
        lines.append(f"- `{reason}`: {len(ts)} fires, avg P&L {avg:+.0f}")
    lines += [
        "",
        "### Recommendation",
        "",
        "*(Based on the data above — fill in after reviewing results)*",
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
            rs_tag = " [RS]" if c.get("discovery_method") == "rescan" else ""
            print(f"    {c['symbol']}: vol={c.get('pm_volume', 0) or 0:,.0f} "
                  f"gap={c.get('gap_pct', 0) or 0:.0f}% float={c.get('float_millions', 0) or 0:.1f}M"
                  f"{rs_tag}", flush=True)

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
            rs_tag = " [RS]" if c.get("discovery_method") == "rescan" else ""
            print(f"    {c['symbol']}: vol={c.get('pm_volume', 0) or 0:,.0f} "
                  f"gap={c.get('gap_pct', 0) or 0:.0f}% float={c.get('float_millions', 0) or 0:.1f}M"
                  f"{rs_tag}", flush=True)

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
