#!/usr/bin/env python3
"""
YTD V2 Profile Backtest Runner — 3-Way Comparison

Tests the old profile system (A/B split, dynamic sizing, risk caps) against
the current simplified system using cached tick data for deterministic results.

Config 1: Current system (already run — results imported from state file)
Config 2: Profile Validated — A/B split, dynamic risk, L2 for B, no bail timer
Config 3: Profile Full — Config 2 + bail timer, giveback, consecutive loser stop, warmup sizing

Usage:
    python run_ytd_v2_profile_backtest.py              # Run both configs
    python run_ytd_v2_profile_backtest.py --config 2   # Config 2 only
    python run_ytd_v2_profile_backtest.py --config 3   # Config 3 only
    python run_ytd_v2_profile_backtest.py --report      # Generate report from saved state
"""

import subprocess
import re
import os
import json
import sys
import math
import time
import argparse
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────
STARTING_EQUITY = 30_000
RISK_PCT = 0.025  # 2.5% of equity per trade
RISK_FLOOR = 250
RISK_CEILING = 1500
PROFILE_B_RISK_CAP = 250  # Profile B max risk
MAX_TRADES_PER_DAY = 5
DAILY_LOSS_LIMIT = -1500
MAX_NOTIONAL = 50_000
TOP_N = 5

# Scanner filters (same as current system)
MIN_PM_VOLUME = 0
MIN_GAP_PCT = 5
MAX_GAP_PCT = 500
MAX_FLOAT_MILLIONS = 10

# ENV_BASE shared across all configs (same as current system)
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

# Profile env overrides (from profiles/*.json)
PROFILE_A_ENV = {
    "WB_ENABLE_L2": "0",
    "WB_EXIT_MODE": "signal",
    "WB_CLASSIFIER_ENABLED": "1",
    "WB_CLASSIFIER_SUPPRESS_ENABLED": "0",
    "WB_FAST_MODE": "0",
}

PROFILE_B_ENV = {
    "WB_ENABLE_L2": "0",  # L2 OFF — tick cache doesn't have L2 data
    "WB_L2_HARD_GATE_WARMUP_BARS": "30",
    "WB_L2_STOP_TIGHTEN_MIN_IMBALANCE": "0.65",
    "WB_EXIT_MODE": "signal",
    "WB_CLASSIFIER_ENABLED": "1",
    "WB_CLASSIFIER_SUPPRESS_ENABLED": "0",
    "WB_FAST_MODE": "0",
    "WB_MAX_ENTRIES_PER_SYMBOL": "3",
}

# Config 3 extras (bail timer, giveback, warmup)
CONFIG_3_EXTRAS = {
    "WB_BAIL_TIMER_ENABLED": "1",
    "WB_BAIL_TIMER_MINUTES": "5",
    "WB_GIVEBACK_HARD_PCT": "50",
    "WB_GIVEBACK_WARN_PCT": "20",
    "WB_MAX_CONSECUTIVE_LOSSES": "3",
    "WB_WARMUP_SIZE_PCT": "25",
    "WB_WARMUP_SIZE_THRESHOLD": "500",
}

DATES = [
    "2026-01-02", "2026-01-03", "2026-01-05", "2026-01-06", "2026-01-07",
    "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13", "2026-01-14",
    "2026-01-15", "2026-01-16", "2026-01-20", "2026-01-21", "2026-01-22",
    "2026-01-23", "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29",
    "2026-01-30",
    "2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06",
    "2026-02-09", "2026-02-10", "2026-02-11", "2026-02-12", "2026-02-13",
    "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-23",
    "2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27",
    "2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06",
    "2026-03-09", "2026-03-10", "2026-03-11", "2026-03-12",
]

STATE_FILE = "profile_backtest_state.json"
SCANNER_DIR = "scanner_results"
WORKDIR = "/Users/mannyluke/warrior_bot"
TICK_CACHE_DIR = os.path.join(WORKDIR, "tick_cache")


# ── Candidate ranking (same formula as current system) ────────────────

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
    """Load, filter, rank scanner candidates. Returns (top_n, total, passed_filter)."""
    path = os.path.join(WORKDIR, SCANNER_DIR, f"{date_str}.json")
    if not os.path.exists(path):
        return [], 0, 0

    with open(path) as f:
        all_candidates = json.load(f)

    total = len(all_candidates)
    filtered = []
    for c in all_candidates:
        pm_vol = c.get("pm_volume", 0) or 0
        gap = c.get("gap_pct", 0) or 0
        float_m = c.get("float_millions", None)
        profile = c.get("profile", "")

        if pm_vol < MIN_PM_VOLUME:
            continue
        if gap < MIN_GAP_PCT or gap > MAX_GAP_PCT:
            continue
        if float_m is None or float_m == 0 or float_m > MAX_FLOAT_MILLIONS:
            continue
        if profile == "X":
            continue
        filtered.append(c)

    filtered.sort(key=rank_score, reverse=True)
    return filtered[:TOP_N], total, len(filtered)


# ── Risk calculation ──────────────────────────────────────────────────

def calculate_risk(equity: float, profile_code: str) -> int:
    """Dynamic risk per profile. A = 2.5% (floor $250, ceiling $1500). B = A/3 capped at $250."""
    base = max(RISK_FLOOR, min(RISK_CEILING, round(equity * RISK_PCT)))
    if profile_code == "B":
        return min(max(RISK_FLOOR, round(base / 3)), PROFILE_B_RISK_CAP)
    return base  # Profile A (and any other)


# ── Simulation runner ──────────────────────────────────────────────────

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
            candidate: dict = None, profile_env: dict = None,
            config_extras: dict = None) -> list:
    """Run simulate.py with profile-specific env vars."""
    env = {**os.environ, **ENV_BASE}
    if profile_env:
        env.update(profile_env)
    if config_extras:
        env.update(config_extras)
    env["WB_MIN_ENTRY_SCORE"] = str(min_score)

    if candidate:
        env["WB_SCANNER_GAP_PCT"] = str(candidate.get("gap_pct", 0))
        env["WB_SCANNER_RVOL"] = str(candidate.get("relative_volume", 0) or 0)
        env["WB_SCANNER_FLOAT_M"] = str(candidate.get("float_millions", 20) or 20)

    cmd = [
        sys.executable, "simulate.py", symbol, date, sim_start, "12:00",
        "--ticks",
        "--risk", str(risk), "--no-fundamentals",
    ]
    if os.path.isdir(TICK_CACHE_DIR):
        cmd.extend(["--tick-cache", TICK_CACHE_DIR])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, env=env,
            cwd=WORKDIR,
        )
        if result.returncode != 0:
            print(f"    SIM FAILED: {symbol} {date} (exit code {result.returncode})", flush=True)
            print(f"    stderr: {result.stderr[-500:]}", flush=True)
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
        if r_val > 0:
            shares = risk / r_val
        else:
            shares = risk
        notional = shares * entry_price

        trades.append({
            "num": int(m.group(1)),
            "time": m.group(2),
            "entry": entry_price,
            "stop": float(m.group(4)),
            "r": r_val,
            "score": float(m.group(6)),
            "exit_price": float(m.group(7)),
            "reason": m.group(8),
            "pnl": int(float(m.group(9))),
            "r_mult": m.group(10),
            "symbol": symbol,
            "date": date,
            "notional": notional,
            "profile": candidate.get("profile", "A") if candidate else "A",
        })

    trade_pnl = sum(t["pnl"] for t in trades)
    profile = candidate.get("profile", "?") if candidate else "?"
    print(f"    {symbol}[{profile}]: ticks={tick_count:,} armed={armed_count} signals={signal_count} trades={len(trades)} risk=${risk} pnl={trade_pnl:+d}", flush=True)

    return trades


# ── State management ──────────────────────────────────────────────────

def load_state():
    p = os.path.join(WORKDIR, STATE_FILE)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


def save_state(state):
    with open(os.path.join(WORKDIR, STATE_FILE), "w") as f:
        json.dump(state, f, indent=2)


# ── Main backtest loop ────────────────────────────────────────────────

def run_config(config_num: int, resume_state: dict = None):
    """Run one config (2 or 3) across all 49 dates."""
    config_name = f"config_{config_num}"
    config_extras = CONFIG_3_EXTRAS if config_num == 3 else {}

    if resume_state and config_name in resume_state:
        cs = resume_state[config_name]
        equity = cs["equity"]
        trades = cs["trades"]
        daily = cs["daily"]
        max_eq = cs.get("max_equity", equity)
        max_dd = cs.get("max_drawdown", 0)
        selection_log = cs.get("selection_log", [])
        last_done = cs.get("last_completed_date", "")
        start_idx = DATES.index(last_done) + 1 if last_done in DATES else 0
        print(f"Resuming Config {config_num} from {last_done} (eq=${equity:,.0f})", flush=True)
    else:
        equity = STARTING_EQUITY
        trades = []
        daily = []
        max_eq = equity
        max_dd = 0
        selection_log = []
        start_idx = 0

    total_dates = len(DATES)

    for i in range(start_idx, total_dates):
        date = DATES[i]
        top5, total_cands, passed_filter = load_and_rank(date)

        sel_entry = {
            "date": date,
            "total_candidates": total_cands,
            "passed_filter": passed_filter,
            "selected": [{"symbol": c["symbol"], "profile": c.get("profile", "?"),
                          "pm_volume": c.get("pm_volume", 0),
                          "gap_pct": c.get("gap_pct", 0),
                          "float_millions": c.get("float_millions", 0),
                          "rank_score": round(rank_score(c), 3)} for c in top5],
        }
        selection_log.append(sel_entry)

        if not top5:
            daily.append({"date": date, "trades": 0, "wins": 0, "losses": 0,
                         "day_pnl": 0, "equity": equity,
                         "note": f"no candidates (total={total_cands}, passed={passed_filter})"})
            print(f"[{i+1}/{total_dates}] {date}: 0 candidates", flush=True)
            _save_config_state(resume_state or {}, config_name, date, equity, trades, daily,
                               max_eq, max_dd, selection_log)
            continue

        # Profile breakdown for this day
        a_stocks = [c for c in top5 if c.get("profile") == "A"]
        b_stocks = [c for c in top5 if c.get("profile") == "B"]
        print(f"[{i+1}/{total_dates}] {date}: {total_cands} scanned → {len(top5)} selected "
              f"({len(a_stocks)}A + {len(b_stocks)}B) eq=${equity:,.0f}", flush=True)

        day_trades = []
        day_pnl = 0
        day_notional = 0

        for c in top5:
            if len(day_trades) >= MAX_TRADES_PER_DAY:
                break
            if day_pnl <= DAILY_LOSS_LIMIT:
                break

            sym = c["symbol"]
            profile = c.get("profile", "A")

            # Profile-specific risk
            risk = calculate_risk(equity, profile)

            # Profile-specific env
            if profile == "B":
                profile_env = PROFILE_B_ENV
            else:
                profile_env = PROFILE_A_ENV

            all_trades = run_sim(sym, date, "07:00", risk, min_score=0,
                                candidate=c, profile_env=profile_env,
                                config_extras=config_extras)
            time.sleep(0.5)  # Light rate limit (cached data)

            for t in all_trades:
                if len(day_trades) >= MAX_TRADES_PER_DAY:
                    break
                if day_pnl <= DAILY_LOSS_LIMIT:
                    break
                if day_notional + t["notional"] > MAX_NOTIONAL:
                    continue

                day_trades.append(t)
                day_pnl += t["pnl"]
                day_notional += t["notional"]

        equity += day_pnl
        if equity > max_eq:
            max_eq = equity
        dd = max_eq - equity
        if dd > max_dd:
            max_dd = dd

        wins = sum(1 for t in day_trades if t["pnl"] > 0)
        losses = sum(1 for t in day_trades if t["pnl"] < 0)

        daily.append({"date": date, "trades": len(day_trades), "wins": wins,
                      "losses": losses, "day_pnl": day_pnl, "equity": equity})
        trades.extend(day_trades)

        # Profile breakdown in daily summary
        a_pnl = sum(t["pnl"] for t in day_trades if t.get("profile") == "A")
        b_pnl = sum(t["pnl"] for t in day_trades if t.get("profile") == "B")
        a_count = sum(1 for t in day_trades if t.get("profile") == "A")
        b_count = sum(1 for t in day_trades if t.get("profile") == "B")
        print(f"  Config {config_num}: {len(day_trades)} trades "
              f"({a_count}A ${a_pnl:+,} + {b_count}B ${b_pnl:+,}) "
              f"day=${day_pnl:+,} eq=${equity:,.0f}", flush=True)

        _save_config_state(resume_state or {}, config_name, date, equity, trades, daily,
                           max_eq, max_dd, selection_log)

    return {
        "equity": equity, "trades": trades, "daily": daily,
        "max_equity": max_eq, "max_drawdown": max_dd,
        "selection_log": selection_log,
    }


def _save_config_state(state, config_name, date, equity, trades, daily,
                       max_eq, max_dd, selection_log):
    state[config_name] = {
        "last_completed_date": date,
        "equity": equity,
        "trades": trades,
        "daily": daily,
        "max_equity": max_eq,
        "max_drawdown": max_dd,
        "selection_log": selection_log,
    }
    save_state(state)


# ── Statistics ────────────────────────────────────────────────────────

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
    max_dd_pct = (max_dd / max_eq * 100) if max_eq > 0 else 0
    largest_win = max((t["pnl"] for t in trades), default=0)
    largest_loss = min((t["pnl"] for t in trades), default=0)
    return {
        "total_pnl": total_pnl, "total_return": total_pnl / STARTING_EQUITY * 100,
        "total_trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate_str": f"{len(wins)}/{len(active)} ({len(wins)/len(active)*100:.0f}%)" if active else "0/0",
        "avg_win": avg_win, "avg_loss": avg_loss, "profit_factor": pf,
        "max_dd": max_dd, "max_dd_pct": max_dd_pct,
        "largest_win": largest_win, "largest_loss": largest_loss,
        "avg_trades_per_day": len(trades) / len(DATES) if DATES else 0,
    }


# ── Report generation ─────────────────────────────────────────────────

def generate_report(state):
    """Generate 3-way comparison report."""
    L = []

    # Load Config 1 results from existing state file
    c1_state_path = os.path.join(WORKDIR, "ytd_v2_backtest_state.json")
    if os.path.exists(c1_state_path):
        with open(c1_state_path) as f:
            c1_raw = json.load(f)
        # Config B (no gate) is the comparison target
        c1 = c1_raw["config_b"]
        s1 = calc_stats(c1["trades"], c1["equity"], c1.get("max_drawdown", 0), c1.get("max_equity", c1["equity"]))
    else:
        c1 = None
        s1 = None

    c2 = state.get("config_2")
    c3 = state.get("config_3")
    s2 = calc_stats(c2["trades"], c2["equity"], c2.get("max_drawdown", 0), c2.get("max_equity", c2["equity"])) if c2 else None
    s3 = calc_stats(c3["trades"], c3["equity"], c3.get("max_drawdown", 0), c3.get("max_equity", c3["equity"])) if c3 else None

    L.append("# Profile System Retest Report")
    L.append(f"## Generated {datetime.now().strftime('%Y-%m-%d')}")
    L.append(f"\nPeriod: January 2 - March 12, 2026 ({len(DATES)} trading days)")
    L.append(f"Starting Equity: ${STARTING_EQUITY:,}")
    L.append(f"Tick Cache: Deterministic replay (240 pairs, 33.7M ticks)")
    L.append(f"\n**Purpose**: Test whether the old profile system was wrongly scrapped due to faulty backtest data.")

    # Section 1: Side-by-side comparison
    L.append("\n---\n")
    L.append("## Section 1: 3-Way Comparison\n")
    L.append("| Metric | Config 1 (Current) | Config 2 (Profiles) | Config 3 (Full) |")
    L.append("|--------|-------------------|--------------------|--------------------|")

    configs = []
    for label, s in [("Config 1", s1), ("Config 2", s2), ("Config 3", s3)]:
        if s:
            configs.append(s)
        else:
            configs.append(None)

    def fmt(s, key, prefix="", suffix=""):
        if s is None:
            return "N/A"
        v = s[key]
        if isinstance(v, str):
            return f"{prefix}{v}{suffix}"
        if isinstance(v, float):
            return f"{prefix}{v:+,.0f}{suffix}" if abs(v) > 1 else f"{prefix}{v:.2f}{suffix}"
        return f"{prefix}{v}{suffix}"

    metrics = [
        ("Final Equity", lambda s: f"${s['total_pnl'] + STARTING_EQUITY:,.0f}" if s else "N/A"),
        ("Total P&L", lambda s: f"${s['total_pnl']:+,.0f}" if s else "N/A"),
        ("Total Return", lambda s: f"{s['total_return']:+.1f}%" if s else "N/A"),
        ("Total Trades", lambda s: f"{s['total_trades']}" if s else "N/A"),
        ("Win Rate", lambda s: s["win_rate_str"] if s else "N/A"),
        ("Avg Win", lambda s: f"${s['avg_win']:+,.0f}" if s else "N/A"),
        ("Avg Loss", lambda s: f"${s['avg_loss']:+,.0f}" if s else "N/A"),
        ("Profit Factor", lambda s: f"{s['profit_factor']:.2f}" if s else "N/A"),
        ("Max Drawdown $", lambda s: f"${s['max_dd']:,.0f}" if s else "N/A"),
        ("Max Drawdown %", lambda s: f"{s['max_dd_pct']:.1f}%" if s else "N/A"),
        ("Largest Win", lambda s: f"${s['largest_win']:+,}" if s else "N/A"),
        ("Largest Loss", lambda s: f"${s['largest_loss']:+,}" if s else "N/A"),
        ("Avg Trades/Day", lambda s: f"{s['avg_trades_per_day']:.1f}" if s else "N/A"),
    ]
    for name, fn in metrics:
        vals = [fn(s) for s in configs]
        L.append(f"| {name} | {vals[0]} | {vals[1]} | {vals[2]} |")

    # Risk descriptions
    L.append(f"\n**Config 1**: Flat dynamic risk (2.5% of equity, ${RISK_FLOOR}-${RISK_CEILING}), no profiles, score gate OFF")
    L.append(f"**Config 2**: Profile A = 2.5% ($250-$1500), Profile B = A/3 capped at $250. No bail timer.")
    L.append(f"**Config 3**: Config 2 + bail timer (5m), giveback (20%/50%), warmup sizing (25% until $500)")
    L.append(f"**L2 note**: Profile B runs WITHOUT L2 (tick cache has trade data only, no book data)")

    # Section 2: Profile A vs B breakdown (for configs 2 & 3)
    L.append("\n---\n")
    L.append("## Section 2: Profile A vs B Breakdown\n")

    for cfg_num, cfg in [(2, c2), (3, c3)]:
        if not cfg:
            continue
        a_trades = [t for t in cfg["trades"] if t.get("profile") == "A"]
        b_trades = [t for t in cfg["trades"] if t.get("profile") == "B"]
        a_pnl = sum(t["pnl"] for t in a_trades)
        b_pnl = sum(t["pnl"] for t in b_trades)
        a_wins = sum(1 for t in a_trades if t["pnl"] > 0)
        b_wins = sum(1 for t in b_trades if t["pnl"] > 0)
        a_active = [t for t in a_trades if t["pnl"] != 0]
        b_active = [t for t in b_trades if t["pnl"] != 0]

        L.append(f"### Config {cfg_num}\n")
        L.append("| Metric | Profile A (Micro-Float) | Profile B (Mid-Float) |")
        L.append("|--------|------------------------|-----------------------|")
        L.append(f"| Trades | {len(a_trades)} | {len(b_trades)} |")
        L.append(f"| P&L | ${a_pnl:+,} | ${b_pnl:+,} |")
        wr_a = f"{a_wins}/{len(a_active)} ({a_wins/len(a_active)*100:.0f}%)" if a_active else "0/0"
        wr_b = f"{b_wins}/{len(b_active)} ({b_wins/len(b_active)*100:.0f}%)" if b_active else "0/0"
        L.append(f"| Win Rate | {wr_a} | {wr_b} |")
        a_avg_r = sum(t.get("pnl", 0) for t in a_trades) / len(a_trades) if a_trades else 0
        b_avg_r = sum(t.get("pnl", 0) for t in b_trades) / len(b_trades) if b_trades else 0
        L.append(f"| Avg P&L/Trade | ${a_avg_r:+,.0f} | ${b_avg_r:+,.0f} |")

        # Risk used for each profile
        a_risks = set()
        b_risks = set()
        for t in a_trades:
            if t.get("r", 0) > 0:
                a_risks.add(int(round(t["notional"] * t["r"] / t["entry"])) if t["entry"] > 0 else 0)
        for t in b_trades:
            if t.get("r", 0) > 0:
                b_risks.add(int(round(t["notional"] * t["r"] / t["entry"])) if t["entry"] > 0 else 0)

        L.append("")

    # Section 3: Day-by-day equity curve
    L.append("\n---\n")
    L.append("## Section 3: Daily Equity Curve\n")
    L.append("| Date | C1 Equity | C1 P&L | C2 Equity | C2 P&L | C3 Equity | C3 P&L |")
    L.append("|------|-----------|--------|-----------|--------|-----------|--------|")

    c1_daily = {d["date"]: d for d in c1["daily"]} if c1 else {}
    c2_daily = {d["date"]: d for d in c2["daily"]} if c2 else {}
    c3_daily = {d["date"]: d for d in c3["daily"]} if c3 else {}

    for date in DATES:
        d1 = c1_daily.get(date, {})
        d2 = c2_daily.get(date, {})
        d3 = c3_daily.get(date, {})
        L.append(
            f"| {date} | "
            f"${d1.get('equity', 0):,.0f} | ${d1.get('day_pnl', 0):+,} | "
            f"${d2.get('equity', 0):,.0f} | ${d2.get('day_pnl', 0):+,} | "
            f"${d3.get('equity', 0):,.0f} | ${d3.get('day_pnl', 0):+,} |"
        )

    # Section 4: Per-trade log with profile tags
    L.append("\n---\n")
    L.append("## Section 4: Trade-Level Detail\n")

    for cfg_num, cfg in [(2, c2), (3, c3)]:
        if not cfg:
            continue
        L.append(f"### Config {cfg_num}\n")
        L.append("| Date | Symbol | Profile | Risk | Entry | Exit | Reason | P&L | R-Mult |")
        L.append("|------|--------|---------|------|-------|------|--------|-----|--------|")
        for t in cfg["trades"]:
            risk_est = int(t["notional"] * t["r"] / t["entry"]) if t["entry"] > 0 and t["r"] > 0 else 0
            L.append(
                f"| {t['date']} | {t['symbol']} | {t.get('profile', '?')} | ${risk_est} | "
                f"${t['entry']:.2f} | ${t['exit_price']:.2f} | {t['reason']} | "
                f"${t['pnl']:+,} | {t['r_mult']} |"
            )
        L.append("")

    # Section 5: Key divergences
    L.append("\n---\n")
    L.append("## Section 5: Key Divergences\n")
    L.append("### Stocks treated differently by profile system\n")

    if c1 and c2:
        c1_syms = set((t["date"], t["symbol"]) for t in c1["trades"])
        c2_syms = set((t["date"], t["symbol"]) for t in c2["trades"])

        only_c1 = c1_syms - c2_syms
        only_c2 = c2_syms - c1_syms

        if only_c1:
            L.append("**Trades in Current System but NOT Profile System:**")
            for date, sym in sorted(only_c1):
                t = next((t for t in c1["trades"] if t["date"] == date and t["symbol"] == sym), None)
                if t:
                    L.append(f"- {date} {sym}: ${t['pnl']:+,}")
            L.append("")

        if only_c2:
            L.append("**Trades in Profile System but NOT Current System:**")
            for date, sym in sorted(only_c2):
                t = next((t for t in c2["trades"] if t["date"] == date and t["symbol"] == sym), None)
                if t:
                    L.append(f"- {date} {sym} [{t.get('profile', '?')}]: ${t['pnl']:+,}")
            L.append("")

        # B-stock impact
        b_trades = [t for t in c2["trades"] if t.get("profile") == "B"]
        if b_trades:
            L.append("**Profile B stocks (mid-float, reduced risk):**")
            for t in b_trades:
                L.append(f"- {t['date']} {t['symbol']}: risk capped, P&L ${t['pnl']:+,}")
            b_total = sum(t["pnl"] for t in b_trades)
            L.append(f"- **Total B-stock P&L**: ${b_total:+,}")

    # Section 6: The big answer
    L.append("\n---\n")
    L.append("## Section 6: The Verdict\n")

    if s1 and s2 and s3:
        L.append(f"| System | P&L | Return | Win Rate | Max DD |")
        L.append(f"|--------|-----|--------|----------|--------|")
        L.append(f"| Current (no profiles) | ${s1['total_pnl']:+,.0f} | {s1['total_return']:+.1f}% | {s1['win_rate_str']} | ${s1['max_dd']:,.0f} |")
        L.append(f"| Profiles Validated | ${s2['total_pnl']:+,.0f} | {s2['total_return']:+.1f}% | {s2['win_rate_str']} | ${s2['max_dd']:,.0f} |")
        L.append(f"| Profiles Full | ${s3['total_pnl']:+,.0f} | {s3['total_return']:+.1f}% | {s3['win_rate_str']} | ${s3['max_dd']:,.0f} |")

        diff_2_1 = (s2["total_pnl"] - s1["total_pnl"])
        diff_3_1 = (s3["total_pnl"] - s1["total_pnl"])
        L.append(f"\n**Profile system vs Current**: ${diff_2_1:+,.0f} (Config 2), ${diff_3_1:+,.0f} (Config 3)")

        if diff_2_1 > 500:
            L.append("\n**OUTCOME 1**: Profile system is significantly better. Consider re-integration.")
        elif diff_2_1 < -500:
            L.append("\n**OUTCOME 3**: Profile system is worse. The simplification was correct.")
        else:
            L.append("\n**OUTCOME 2**: Profile system is roughly equivalent. Extra complexity not worth it.")

    L.append("\n---\n")
    L.append("*Generated from profile retest backtest | Cached tick data (deterministic) | Branch: v6-dynamic-sizing*")

    report_path = os.path.join(WORKDIR, "PROFILE_RETEST_REPORT.md")
    with open(report_path, "w") as f:
        f.write("\n".join(L))
    print(f"\nReport saved: {report_path}", flush=True)
    return report_path


# ── Entry point ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Profile system retest backtest")
    parser.add_argument("--config", type=int, choices=[2, 3], help="Run specific config only")
    parser.add_argument("--report", action="store_true", help="Generate report from saved state")
    parser.add_argument("--fresh", action="store_true", help="Start fresh (delete saved state)")
    args = parser.parse_args()

    if args.fresh:
        p = os.path.join(WORKDIR, STATE_FILE)
        if os.path.exists(p):
            os.remove(p)
            print("Deleted saved state — starting fresh.", flush=True)

    state = load_state() or {}

    if args.report:
        generate_report(state)
        return

    print("=" * 60)
    print("PROFILE SYSTEM RETEST: 3-Way Comparison")
    print(f"Period: Jan 2 - Mar 12, 2026 ({len(DATES)} trading days)")
    print(f"Starting equity: ${STARTING_EQUITY:,}")
    print(f"Profile A risk: 2.5% ($250-$1500)")
    print(f"Profile B risk: A/3 capped at $250")
    print(f"L2: OFF (tick cache has trade data only)")
    print("=" * 60)

    if args.config is None or args.config == 2:
        print(f"\n{'='*60}")
        print("CONFIG 2: Profile Validated (A/B split, dynamic risk)")
        print(f"{'='*60}")
        c2 = run_config(2, state)
        state["config_2"] = c2
        save_state(state)
        pnl2 = c2["equity"] - STARTING_EQUITY
        print(f"\nConfig 2 done: ${pnl2:+,.0f} ({pnl2/STARTING_EQUITY*100:+.1f}%)")

    if args.config is None or args.config == 3:
        print(f"\n{'='*60}")
        print("CONFIG 3: Profile Full (+ bail timer, giveback, warmup)")
        print(f"{'='*60}")
        c3 = run_config(3, state)
        state["config_3"] = c3
        save_state(state)
        pnl3 = c3["equity"] - STARTING_EQUITY
        print(f"\nConfig 3 done: ${pnl3:+,.0f} ({pnl3/STARTING_EQUITY*100:+.1f}%)")

    # Generate report
    generate_report(state)

    # Final summary
    print(f"\n{'='*60}")
    print("FINAL RESULTS")
    print(f"{'='*60}")

    c1_path = os.path.join(WORKDIR, "ytd_v2_backtest_state.json")
    if os.path.exists(c1_path):
        with open(c1_path) as f:
            c1 = json.load(f)
        pnl1 = c1["config_b"]["equity"] - STARTING_EQUITY
        print(f"Config 1 (Current, no profiles): ${pnl1:+,.0f} ({pnl1/STARTING_EQUITY*100:+.1f}%)")

    if "config_2" in state:
        pnl2 = state["config_2"]["equity"] - STARTING_EQUITY
        print(f"Config 2 (Profiles Validated):    ${pnl2:+,.0f} ({pnl2/STARTING_EQUITY*100:+.1f}%)")

    if "config_3" in state:
        pnl3 = state["config_3"]["equity"] - STARTING_EQUITY
        print(f"Config 3 (Profiles Full):         ${pnl3:+,.0f} ({pnl3/STARTING_EQUITY*100:+.1f}%)")

    print(f"{'='*60}")


if __name__ == "__main__":
    main()
