#!/usr/bin/env python3
"""
Weekend Megatest Runner — Full Strategy Matrix
Runs strategy combos across all available scanner dates.
Usage: python run_megatest.py <combo_id>
  combo_id: mp_only | sq_only | mp_sq | all_three
"""

import subprocess
import re
import os
import json
import sys
import glob
import math
import time
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────
STARTING_EQUITY = 30_000
RISK_PCT = 0.025  # 2.5% of equity per trade
MAX_TRADES_PER_DAY = 5
DAILY_LOSS_LIMIT = -3000  # Stop trading if daily P&L hits this (aligned with live .env WB_MAX_DAILY_LOSS=3000)
MAX_NOTIONAL = 50_000
TOP_N = 5  # Watchlist size

# Scanner filters
MIN_PM_VOLUME = 50_000
MIN_GAP_PCT = 10
MAX_GAP_PCT = 500
MAX_FLOAT_MILLIONS = 10  # Ross uses 10M — stocks above this aren't low-float movers
MIN_RVOL = 2.0


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
    "WB_MAX_LOSS_R": "0.75",
    "WB_NO_REENTRY_ENABLED": "1",
    # Strategy 2: Squeeze V2
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
}

# ── Dynamic date discovery ────────────────────────────────────────────
DATES = sorted([
    os.path.basename(f).replace('.json', '')
    for f in glob.glob(os.path.join(
        os.getenv("WB_WORKDIR", os.path.dirname(os.path.abspath(__file__))),
        'scanner_results', '20??-??-??.json'
    ))
])

# ── Combo configurations ──────────────────────────────────────────────
COMBO_OVERRIDES = {
    "mp_only": {
        "WB_SQUEEZE_ENABLED": "0",
        "WB_VR_ENABLED": "0",
    },
    "sq_only": {
        "WB_SQUEEZE_ENABLED": "1",
        "WB_VR_ENABLED": "0",
        "WB_MP_SUPPRESS_ENTRIES": "1",
    },
    "mp_sq": {
        "WB_SQUEEZE_ENABLED": "1",
        "WB_VR_ENABLED": "0",
    },
    "all_three": {
        "WB_SQUEEZE_ENABLED": "1",
        "WB_VR_ENABLED": "1",
        "WB_VR_MAX_R": "1.00",
        "WB_VR_MAX_R_PCT": "5.0",
        "WB_VR_RECLAIM_WINDOW": "5",
        "WB_VR_MAX_BELOW_BARS": "20",
        "WB_VR_MAX_ATTEMPTS": "3",
        "WB_VR_SEVERE_VWAP_LOSS_PCT": "20.0",
    },
}

# Combo ID from CLI arg
COMBO_ID = sys.argv[1] if len(sys.argv) > 1 else "mp_sq"
if COMBO_ID not in COMBO_OVERRIDES:
    print(f"Unknown combo: {COMBO_ID}. Options: {list(COMBO_OVERRIDES.keys())}")
    sys.exit(1)

# Apply combo overrides to ENV_BASE
ENV_BASE.update(COMBO_OVERRIDES[COMBO_ID])

MEGATEST_DIR = "megatest_results"
os.makedirs(os.path.join(os.getenv("WB_WORKDIR", os.path.dirname(os.path.abspath(__file__))), MEGATEST_DIR), exist_ok=True)

STATE_FILE = os.path.join(MEGATEST_DIR, f"megatest_state_{COMBO_ID}_v2.json")
SCANNER_DIR = "scanner_results"
WORKDIR = os.getenv("WB_WORKDIR", os.path.dirname(os.path.abspath(__file__)))


# ── Candidate ranking ─────────────────────────────────────────────────

def rank_score(candidate):
    """Composite score: 40% RVOL + 30% abs volume + 20% gap + 10% float bonus."""
    pm_vol = candidate.get("pm_volume", 0) or 0
    rvol = candidate.get("relative_volume", 0) or 0
    gap_pct = candidate.get("gap_pct", 0) or 0
    float_m = candidate.get("float_millions", 10) or 10

    # Relative volume (log scale, capped) — stocks with unusual interest rank higher
    rvol_score = math.log10(max(rvol, 0.1) + 1) / math.log10(51)  # 0-1 range, 50x = 1.0
    # Absolute volume (keep as tiebreaker)
    vol_score = math.log10(max(pm_vol, 1)) / 8  # normalize
    gap_score = min(gap_pct, 100) / 100
    float_penalty = min(float_m, 10) / 10  # tightened to 10M

    return (0.4 * rvol_score) + (0.3 * vol_score) + (0.2 * gap_score) + (0.1 * (1 - float_penalty))


def load_and_rank(date_str: str) -> tuple:
    """Load, filter, rank scanner candidates. Returns (top_n, total, passed_filter)."""
    path = os.path.join(WORKDIR, SCANNER_DIR, f"{date_str}.json")
    if not os.path.exists(path):
        return [], 0, 0

    with open(path) as f:
        all_candidates = json.load(f)

    total = len(all_candidates)

    # Filter
    filtered = []
    for c in all_candidates:
        pm_vol = c.get("pm_volume", 0) or 0
        gap = c.get("gap_pct", 0) or 0
        float_m = c.get("float_millions", None)
        profile = c.get("profile", "")
        rvol = c.get("relative_volume", 0) or 0

        if pm_vol < MIN_PM_VOLUME:
            continue
        if gap < MIN_GAP_PCT or gap > MAX_GAP_PCT:
            continue
        if float_m is not None and float_m > 0 and float_m > MAX_FLOAT_MILLIONS:
            continue
        if rvol < MIN_RVOL:
            continue
        filtered.append(c)

    # Rank and take top N
    filtered.sort(key=rank_score, reverse=True)
    top = filtered[:TOP_N]

    return top, total, len(filtered)


# ── Simulation runner ──────────────────────────────────────────────────

TRADE_PAT = re.compile(
    r'^\s*(\d+)\s+'           # trade number
    r'(\d{2}:\d{2})\s+'      # entry time
    r'([\d.]+)\s+'           # entry price
    r'([\d.]+)\s+'           # stop price
    r'([\d.]+)\s+'           # R
    r'([\d.]+)\s+'           # score
    r'([\d.]+)\s+'           # exit price
    r'(\S+)\s+'              # reason
    r'([+-]?\d+)\s+'         # P&L
    r'([+-]?[\d.]+R)'        # R-mult
    r'(?:\s+(\d{2}:\d{2}))?',  # XTIME (exit time) — optional, added in simulate.py
    re.MULTILINE
)


TICK_DIAG_PAT = re.compile(r'Tick replay:\s+([\d,]+)\s+trades')
ARMED_DIAG_PAT = re.compile(r'Armed:\s+(\d+)\s+\|\s+Signals:\s+(\d+)')

TICK_CACHE_DIR = os.path.join(WORKDIR, "tick_cache")


def run_sim(symbol: str, date: str, sim_start: str, risk: int, min_score: float,
            candidate: dict = None, use_tick_cache: bool = True,
            max_notional_override: int = None,
            env_overrides: dict = None) -> list:
    """Run simulate.py and parse trade results."""
    env = {**os.environ, **ENV_BASE}
    env["WB_MIN_ENTRY_SCORE"] = str(min_score)
    if max_notional_override is not None:
        env["WB_MAX_NOTIONAL"] = str(max_notional_override)
    # Pass Ross Pillar data via env vars for entry-time checks
    if candidate:
        env["WB_SCANNER_GAP_PCT"] = str(candidate.get("gap_pct", 0))
        env["WB_SCANNER_RVOL"] = str(candidate.get("relative_volume", 0) or 0)
        env["WB_SCANNER_FLOAT_M"] = str(candidate.get("float_millions", 20) or 20)
    # Per-call env overrides (e.g., conviction-scaled MAX_NOTIONAL)
    if env_overrides:
        env.update(env_overrides)

    cmd = [
        sys.executable, "simulate.py", symbol, date, sim_start, "12:00",
        "--ticks",
        "--risk", str(risk), "--no-fundamentals",
    ]
    # Use tick cache if directory exists
    if use_tick_cache and os.path.isdir(TICK_CACHE_DIR):
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

    # Diagnostic logging: extract tick count, armed count, signal count
    tick_match = TICK_DIAG_PAT.search(output)
    armed_match = ARMED_DIAG_PAT.search(output)
    tick_count = int(tick_match.group(1).replace(",", "")) if tick_match else -1
    armed_count = int(armed_match.group(1)) if armed_match else -1
    signal_count = int(armed_match.group(2)) if armed_match else -1

    trades = []
    for m in TRADE_PAT.finditer(output):
        entry_price = float(m.group(3))
        stop_price = float(m.group(4))
        r_val = float(m.group(5))
        # Notional: shares * entry_price, where shares = risk / R
        # Use r_val (actual R from detector), NOT entry-stop distance
        if r_val > 0:
            shares = risk / r_val
        else:
            shares = risk  # fallback
        notional = shares * entry_price

        trades.append({
            "num": int(m.group(1)),
            "time": m.group(2),            # entry time (HH:MM)
            "exit_time": m.group(11) or "", # final exit time (HH:MM) from XTIME column
            "entry": entry_price,
            "stop": stop_price,
            "r": r_val,
            "score": float(m.group(6)),
            "exit_price": float(m.group(7)),
            "reason": m.group(8),
            "pnl": int(float(m.group(9))),
            "r_mult": m.group(10),
            "symbol": symbol,
            "date": date,
            "notional": notional,
            "setup_type": "squeeze" if m.group(8).startswith("sq_") else "micro_pullback",
        })

    trade_pnl = sum(t["pnl"] for t in trades)
    print(f"    {symbol}: ticks={tick_count:,} armed={armed_count} signals={signal_count} trades={len(trades)} pnl={trade_pnl:+d}", flush=True)

    return trades


# ── State management ───────────────────────────────────────────────────

def load_state():
    p = os.path.join(WORKDIR, STATE_FILE)
    if os.path.exists(p):
        with open(p) as f:
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
        missed_opps = state.get("missed_opportunities", [])
        selection_log = state.get("selection_log", [])
        start_idx = DATES.index(last_done) + 1 if last_done in DATES else 0
        print(f"Resuming from {last_done} (A: ${eq_a:,.0f}, B: ${eq_b:,.0f})", flush=True)
    else:
        eq_a = STARTING_EQUITY
        eq_b = STARTING_EQUITY
        trades_a, trades_b = [], []
        daily_a, daily_b = [], []
        max_eq_a, max_eq_b = eq_a, eq_b
        max_dd_a, max_dd_b = 0, 0
        missed_opps = []
        selection_log = []
        start_idx = 0

    total_dates = len(DATES)

    for i in range(start_idx, total_dates):
        date = DATES[i]
        top5, total_cands, passed_filter = load_and_rank(date)

        # Log selection
        sel_entry = {
            "date": date,
            "total_candidates": total_cands,
            "passed_filter": passed_filter,
            "selected": [{"symbol": c["symbol"], "pm_volume": c.get("pm_volume", 0),
                          "gap_pct": c.get("gap_pct", 0), "float_millions": c.get("float_millions", 0),
                          "rank_score": round(rank_score(c), 3)} for c in top5],
        }
        selection_log.append(sel_entry)

        if not top5:
            daily_a.append({"date": date, "trades": 0, "wins": 0, "losses": 0,
                           "day_pnl": 0, "equity": eq_a,
                           "note": f"no candidates (total={total_cands}, passed={passed_filter})"})
            daily_b.append({"date": date, "trades": 0, "wins": 0, "losses": 0,
                           "day_pnl": 0, "equity": eq_b,
                           "note": f"no candidates (total={total_cands}, passed={passed_filter})"})
            print(f"[{i+1}/{total_dates}] {date}: {total_cands} scanned, {passed_filter} passed filter, 0 selected", flush=True)
            save_state(_build_state(date, eq_a, eq_b, trades_a, trades_b, daily_a, daily_b,
                                    max_eq_a, max_eq_b, max_dd_a, max_dd_b, missed_opps, selection_log))
            continue

        risk_a = max(int(eq_a * RISK_PCT), 50)  # Floor at $50 to avoid 0-risk trades
        risk_b = max(int(eq_b * RISK_PCT), 50)

        print(f"[{i+1}/{total_dates}] {date}: {total_cands} scanned → {passed_filter} passed → top {len(top5)} selected (risk A=${risk_a}, B=${risk_b})", flush=True)
        for c in top5:
            print(f"    #{top5.index(c)+1} {c['symbol']}: vol={c.get('pm_volume',0):,.0f}, gap={c.get('gap_pct',0):.0f}%, float={c.get('float_millions',0):.1f}M", flush=True)

        # Run Config A
        day_trades_a, day_pnl_a = _run_config_day(top5, date, risk_a, min_score=8.0, max_consec_losses=2)
        # Run Config B
        day_trades_b, day_pnl_b = _run_config_day(top5, date, risk_b, min_score=0, max_consec_losses=2)

        eq_a += day_pnl_a
        eq_b += day_pnl_b

        # Drawdown tracking
        if eq_a > max_eq_a: max_eq_a = eq_a
        dd_a = max_eq_a - eq_a
        if dd_a > max_dd_a: max_dd_a = dd_a

        if eq_b > max_eq_b: max_eq_b = eq_b
        dd_b = max_eq_b - eq_b
        if dd_b > max_dd_b: max_dd_b = dd_b

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

        save_state(_build_state(date, eq_a, eq_b, trades_a, trades_b, daily_a, daily_b,
                                max_eq_a, max_eq_b, max_dd_a, max_dd_b, missed_opps, selection_log))

    return {
        "config_a": {"equity": eq_a, "trades": trades_a, "daily": daily_a,
                      "max_drawdown": max_dd_a, "max_equity": max_eq_a},
        "config_b": {"equity": eq_b, "trades": trades_b, "daily": daily_b,
                      "max_drawdown": max_dd_b, "max_equity": max_eq_b},
        "missed_opportunities": missed_opps,
        "selection_log": selection_log,
    }


def _run_config_day(top5, date, risk, min_score, max_consec_losses=0):
    """Run one config for one day with trade cap + daily loss limit + single-position enforcement.

    Bug fixes (v2):
      #1 — Single-position enforcement: live bot holds only ONE position at a time.
           All stocks' trades are sorted by entry time; trades that start before the
           current position's exit time are blocked.
      #2 — Per-position notional: MAX_NOTIONAL is a per-trade cap, not cumulative.
           Each trade is checked independently (the previous trade has closed before
           the next one can open, so there's no additive notional exposure).
      #8 — DAILY_LOSS_LIMIT aligned with live: -$3,000 (was -$1,500).

    max_consec_losses: stop trading after N consecutive losses (0 = disabled).
    """
    # Rank-grace config (OFF by default — matches WB_RANK_GRACE_ENABLED=0 in live bot).
    rank_grace_enabled = os.getenv("WB_RANK_GRACE_ENABLED", "0") == "1"
    rank_grace_minutes = int(os.getenv("WB_RANK_GRACE_MINUTES", "10"))
    rank_grace_top_n = int(os.getenv("WB_RANK_GRACE_TOP_N", "2"))

    # Build rank map: {symbol: rank_position} where 1 = highest-ranked.
    # top5 is already sorted best-first by load_and_rank().
    symbol_rank = {c["symbol"]: idx + 1 for idx, c in enumerate(top5)}

    # Earliest sim_start across candidates is the "session open" for grace timing.
    all_sim_starts = [c.get("sim_start", "07:00") for c in top5]
    session_start_str = min(all_sim_starts)  # lexicographic min works for HH:MM

    # Step 1: Run all stocks and collect trades per symbol.
    _conviction_enabled = os.getenv("WB_CONVICTION_SIZING_ENABLED", "0") == "1"
    _conviction_base = float(os.getenv("WB_CONVICTION_BASE_SCORE", "0.6"))
    _conviction_min = float(os.getenv("WB_CONVICTION_MIN_MULT", "0.5"))
    _conviction_max = float(os.getenv("WB_CONVICTION_MAX_MULT", "2.5"))
    _conviction_scale_notional = os.getenv("WB_CONVICTION_SCALE_NOTIONAL", "1") == "1"

    all_stock_trades = []
    for c in top5:
        sym = c["symbol"]
        float_m = c.get("float_millions", 0) or 0
        stock_risk = min(risk, 250) if float_m > 5.0 else risk
        sim_start = c.get("sim_start", "07:00")
        notional_override = None

        # Conviction sizing: scale risk and MAX_NOTIONAL by scanner rank score
        env_overrides = {}
        if _conviction_enabled:
            score = rank_score(c)
            conv_mult = max(_conviction_min, min(_conviction_max, score / _conviction_base if _conviction_base > 0 else 1.0))
            stock_risk = int(stock_risk * conv_mult)
            if _conviction_scale_notional:
                env_overrides["WB_MAX_NOTIONAL"] = str(int(MAX_NOTIONAL * conv_mult))

        trades = run_sim(sym, date, sim_start, stock_risk, min_score, candidate=c,
                         max_notional_override=notional_override,
                         env_overrides=env_overrides if env_overrides else None)
        time.sleep(1)
        if trades:
            all_stock_trades.append((sym, trades))

    # Step 2: Annotate each trade with estimated exit_time and rank position.
    # simulate.py now outputs an XTIME (final exit time) column. When present, use it.
    # Fallback: use the entry time of the NEXT trade from the SAME stock (conservative
    # upper bound — works because simulate.py trades are already sequential per stock).
    all_trades_flat = []
    for sym, trades in all_stock_trades:
        sym_rank = symbol_rank.get(sym, len(top5) + 1)
        for i, t in enumerate(trades):
            t = dict(t)  # copy — don't mutate the parsed dict
            if not t.get("exit_time"):
                # XTIME not captured (shouldn't happen with updated simulate.py, but safe)
                if i + 1 < len(trades):
                    t["exit_time"] = trades[i + 1]["time"]
                else:
                    t["exit_time"] = "12:00"
            t["rank"] = sym_rank  # annotate with rank position for grace-period check
            all_trades_flat.append(t)

    # Step 3: Sort all trades across all stocks chronologically.
    all_trades_flat.sort(key=lambda t: t["time"])

    # Step 4: Enforce single-position + per-day limits.
    day_trades = []
    day_pnl = 0
    consec_losses = 0
    position_end = "00:00"  # no open position at start of day

    # Compute the grace-period cutoff time string (HH:MM) for comparison.
    if rank_grace_enabled:
        sess_h, sess_m = map(int, session_start_str.split(":"))
        grace_total_min = sess_h * 60 + sess_m + rank_grace_minutes
        grace_cutoff_str = f"{grace_total_min // 60:02d}:{grace_total_min % 60:02d}"
    else:
        grace_cutoff_str = "00:00"  # unused when disabled

    for t in all_trades_flat:
        if len(day_trades) >= MAX_TRADES_PER_DAY:
            break
        if day_pnl <= DAILY_LOSS_LIMIT:
            break
        if max_consec_losses > 0 and consec_losses >= max_consec_losses:
            break

        # Bug #1 fix: single-position gate — skip if previous position still open
        if t["time"] < position_end:
            continue

        # Rank-grace gate: during grace window only top-N ranked stocks can enter.
        if rank_grace_enabled and t["time"] < grace_cutoff_str:
            if t.get("rank", 1) > rank_grace_top_n:
                continue

        # Bug #2 fix: per-position notional cap — each trade checked independently
        # (previous trade has closed by the time we enter this one)
        if t["notional"] > MAX_NOTIONAL:
            continue

        day_trades.append(t)
        day_pnl += t["pnl"]
        position_end = t["exit_time"]  # block new entries until this trade closes

        if t["pnl"] < 0:
            consec_losses += 1
        else:
            consec_losses = 0

    return day_trades, day_pnl


def _build_state(date, eq_a, eq_b, trades_a, trades_b, daily_a, daily_b,
                 max_eq_a, max_eq_b, max_dd_a, max_dd_b, missed_opps, selection_log):
    return {
        "last_completed_date": date,
        "config_a": {"equity": eq_a, "trades": trades_a, "daily": daily_a,
                     "max_equity": max_eq_a, "max_drawdown": max_dd_a},
        "config_b": {"equity": eq_b, "trades": trades_b, "daily": daily_b,
                     "max_equity": max_eq_b, "max_drawdown": max_dd_b},
        "missed_opportunities": missed_opps,
        "selection_log": selection_log,
    }


# ── Report generation ──────────────────────────────────────────────────

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
        "total_trades": len(trades),
        "win_rate_str": f"{len(wins)}/{len(active)} ({len(wins)/len(active)*100:.0f}%)" if active else "0/0",
        "avg_win": avg_win, "avg_loss": avg_loss, "profit_factor": pf,
        "max_dd": max_dd, "max_dd_pct": max_dd_pct,
        "largest_win": largest_win, "largest_loss": largest_loss,
        "avg_trades_per_day": len(trades) / len(DATES) if DATES else 0,
    }


def generate_report(results):
    ca = results["config_a"]
    cb = results["config_b"]
    sa = calc_stats(ca["trades"], ca["equity"], ca["max_drawdown"], ca["max_equity"])
    sb = calc_stats(cb["trades"], cb["equity"], cb["max_drawdown"], cb["max_equity"])
    sel_log = results.get("selection_log", [])

    L = []
    L.append("# YTD V2 Backtest Results: Top-5 Ranked + Trade Cap")
    L.append(f"## Generated {datetime.now().strftime('%Y-%m-%d')}")
    L.append(f"\nPeriod: January 2 - March 12, 2026 ({len(DATES)} trading days)")
    L.append(f"Starting Equity: ${STARTING_EQUITY:,}")
    L.append(f"Risk: {RISK_PCT*100:.1f}% of equity (dynamic)")
    L.append(f"Max trades/day: {MAX_TRADES_PER_DAY} | Daily loss limit: ${DAILY_LOSS_LIMIT:,} | Max notional: ${MAX_NOTIONAL:,}")
    L.append(f"Scanner filter: PM vol >= {MIN_PM_VOLUME:,} (no hard floor), gap {MIN_GAP_PCT}-{MAX_GAP_PCT}%, float < {MAX_FLOAT_MILLIONS}M")
    L.append(f"Top {TOP_N} candidates per day by composite rank (70% volume + 20% gap + 10% float)")

    # Section 1: V1 vs V2
    L.append("\n---\n")
    L.append("## Section 1: V1 vs V2 Comparison\n")
    L.append("| Metric | V1 Config A | V2 Config A | V2 Config B |")
    L.append("|--------|-------------|-------------|-------------|")
    L.append(f"| Total Trades | 184 (11 days) | {sa['total_trades']} ({len(DATES)} days) | {sb['total_trades']} ({len(DATES)} days) |")
    L.append(f"| Avg Trades/Day | 16.7 | {sa['avg_trades_per_day']:.1f} | {sb['avg_trades_per_day']:.1f} |")
    L.append(f"| Final Equity | $7,755 | ${ca['equity']:,.0f} | ${cb['equity']:,.0f} |")
    L.append(f"| Total P&L | -$22,245 | ${sa['total_pnl']:+,.0f} | ${sb['total_pnl']:+,.0f} |")
    L.append(f"| Total Return | -74.2% | {sa['total_return']:+.1f}% | {sb['total_return']:+.1f}% |")

    # Section 2: Summary
    L.append("\n---\n")
    L.append("## Section 2: Summary - Config A vs Config B\n")
    L.append("| Metric | Config A (Gate=8) | Config B (No Gate) |")
    L.append("|--------|--------------------|--------------------|")
    L.append(f"| Final Equity | ${ca['equity']:,.0f} | ${cb['equity']:,.0f} |")
    L.append(f"| Total P&L | ${sa['total_pnl']:+,.0f} | ${sb['total_pnl']:+,.0f} |")
    L.append(f"| Total Return | {sa['total_return']:+.1f}% | {sb['total_return']:+.1f}% |")
    L.append(f"| Total Trades | {sa['total_trades']} | {sb['total_trades']} |")
    L.append(f"| Avg Trades/Day | {sa['avg_trades_per_day']:.1f} | {sb['avg_trades_per_day']:.1f} |")
    L.append(f"| Win Rate | {sa['win_rate_str']} | {sb['win_rate_str']} |")
    L.append(f"| Average Win | ${sa['avg_win']:+,.0f} | ${sb['avg_win']:+,.0f} |")
    L.append(f"| Average Loss | ${sa['avg_loss']:+,.0f} | ${sb['avg_loss']:+,.0f} |")
    L.append(f"| Profit Factor | {sa['profit_factor']:.2f} | {sb['profit_factor']:.2f} |")
    L.append(f"| Max Drawdown $ | ${sa['max_dd']:,.0f} | ${sb['max_dd']:,.0f} |")
    L.append(f"| Max Drawdown % | {sa['max_dd_pct']:.1f}% | {sb['max_dd_pct']:.1f}% |")
    L.append(f"| Largest Win | ${sa['largest_win']:+,} | ${sb['largest_win']:+,} |")
    L.append(f"| Largest Loss | ${sa['largest_loss']:+,} | ${sb['largest_loss']:+,} |")

    # Section 3: Monthly
    L.append("\n---\n")
    L.append("## Section 3: Monthly Breakdown\n")
    L.append("| Month | A P&L | A Trades | B P&L | B Trades |")
    L.append("|-------|-------|----------|-------|----------|")
    for pfx, name in [("2026-01", "Jan"), ("2026-02", "Feb"), ("2026-03", "Mar")]:
        a_pnl = sum(d["day_pnl"] for d in ca["daily"] if d["date"].startswith(pfx))
        a_tr = sum(d["trades"] for d in ca["daily"] if d["date"].startswith(pfx))
        b_pnl = sum(d["day_pnl"] for d in cb["daily"] if d["date"].startswith(pfx))
        b_tr = sum(d["trades"] for d in cb["daily"] if d["date"].startswith(pfx))
        L.append(f"| {name} | ${a_pnl:+,} | {a_tr} | ${b_pnl:+,} | {b_tr} |")

    # Section 4: Daily Detail
    L.append("\n---\n")
    L.append("## Section 4: Daily Detail\n")
    L.append("| Date | Scanned | Passed | Top N | A Trades | A P&L | A Equity | B Trades | B P&L | B Equity |")
    L.append("|------|---------|--------|-------|----------|-------|----------|----------|-------|----------|")
    for da, db, sl in zip(ca["daily"], cb["daily"], sel_log):
        note = f" {da.get('note','')}" if da.get("note") else ""
        L.append(
            f"| {da['date']} | {sl['total_candidates']} | {sl['passed_filter']} | {len(sl['selected'])} | "
            f"{da['trades']} | ${da['day_pnl']:+,} | ${da['equity']:,.0f}{note} | "
            f"{db['trades']} | ${db['day_pnl']:+,} | ${db['equity']:,.0f} |"
        )

    # Section 5: Trade Detail
    L.append("\n---\n")
    L.append("## Section 5: Trade-Level Detail\n")
    L.append("### Config A (Gate=8)\n")
    L.append("| Date | Symbol | Score | Entry | Exit | Reason | P&L |")
    L.append("|------|--------|-------|-------|------|--------|-----|")
    for t in ca["trades"]:
        L.append(f"| {t['date']} | {t['symbol']} | {t['score']:.1f} | ${t['entry']:.2f} | ${t['exit_price']:.2f} | {t['reason']} | ${t['pnl']:+,} |")

    L.append("\n### Config B (No Gate)\n")
    L.append("| Date | Symbol | Score | Entry | Exit | Reason | P&L |")
    L.append("|------|--------|-------|-------|------|--------|-----|")
    for t in cb["trades"]:
        L.append(f"| {t['date']} | {t['symbol']} | {t['score']:.1f} | ${t['entry']:.2f} | ${t['exit_price']:.2f} | {t['reason']} | ${t['pnl']:+,} |")

    # Section 6: Score Gate Diff
    L.append("\n---\n")
    L.append("## Section 6: Score Gate Difference (Trades in B but not A)\n")
    a_set = set((t["date"], t["symbol"], t["num"]) for t in ca["trades"])
    diff = [t for t in cb["trades"] if (t["date"], t["symbol"], t["num"]) not in a_set]
    if diff:
        L.append("| Date | Symbol | Score | Entry | Exit | Reason | P&L (in B) |")
        L.append("|------|--------|-------|-------|------|--------|------------|")
        diff_pnl = 0
        for t in diff:
            L.append(f"| {t['date']} | {t['symbol']} | {t['score']:.1f} | ${t['entry']:.2f} | ${t['exit_price']:.2f} | {t['reason']} | ${t['pnl']:+,} |")
            diff_pnl += t["pnl"]
        L.append(f"\n**Total P&L of blocked trades**: ${diff_pnl:+,}")
        L.append(f"**Score gate net impact**: ${-diff_pnl:+,} (positive = gate helped)")
    else:
        L.append("No trades differ between A and B in the top-5 selected candidates.")

    # Section 7: Missed Opportunities (known winners)
    L.append("\n---\n")
    L.append("## Section 7: Missed Opportunities (Hindsight)\n")
    L.append("### Known Winners - Did They Make the Top 5?\n")
    known_winners = [
        ("BNAI", "2026-01-14", "PM vol 5,686 — below 50K filter", "+$4,907"),
        ("ROLR", "2026-01-14", "PM vol 10.6M — should be #1", "+$2,431"),
        ("GWAV", "2026-01-16", "PM vol 1.5M — should make top 5", "+$6,735 (blocked by gate)"),
        ("VERO", "2026-01-16", "NOT IN SCANNER", "+$8,360"),
    ]
    L.append("| Stock | Date | Scanner Status | Known P&L | In Top 5? |")
    L.append("|-------|------|----------------|-----------|-----------|")
    for sym, dt, note, pnl in known_winners:
        # Check if in selection log
        in_top5 = "N/A"
        for sl in sel_log:
            if sl["date"] == dt:
                selected_syms = [s["symbol"] for s in sl["selected"]]
                if sym in selected_syms:
                    rank = selected_syms.index(sym) + 1
                    in_top5 = f"YES (#{rank})"
                else:
                    in_top5 = "NO"
                break
        L.append(f"| {sym} | {dt} | {note} | {pnl} | {in_top5} |")

    # Section 8: Daily Selection Log
    L.append("\n---\n")
    L.append("## Section 8: Daily Selection Log\n")
    for sl in sel_log:
        if sl["selected"]:
            syms = ", ".join(f"{s['symbol']}(vol={s['pm_volume']:,.0f})" for s in sl["selected"])
            L.append(f"**{sl['date']}**: {sl['total_candidates']} scanned → {sl['passed_filter']} passed → {syms}")
        else:
            L.append(f"**{sl['date']}**: {sl['total_candidates']} scanned → {sl['passed_filter']} passed filter → none selected")

    # Section 9: Robustness
    L.append("\n---\n")
    L.append("## Section 9: Robustness Checks\n")
    for label, trades, daily in [("Config A", ca["trades"], ca["daily"]), ("Config B", cb["trades"], cb["daily"])]:
        active = [t for t in trades if t["pnl"] != 0]
        sorted_wins = sorted([t["pnl"] for t in active if t["pnl"] > 0], reverse=True)
        top3 = sum(sorted_wins[:3]) if len(sorted_wins) >= 3 else sum(sorted_wins)
        total = sum(t["pnl"] for t in active)
        wins = [t for t in active if t["pnl"] > 0]
        losses_list = [t for t in active if t["pnl"] < 0]

        max_streak = streak = 0
        for d in daily:
            if d["day_pnl"] < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            elif d["day_pnl"] > 0:
                streak = 0

        L.append(f"### {label}")
        L.append(f"- P&L without top 3 winners: ${total - top3:+,}")
        L.append(f"- Top 3 winners: ${top3:+,}")
        L.append(f"- Longest consecutive losing streak (days): {max_streak}")
        L.append(f"- Win/loss count (excl breakeven): {len(wins)}W / {len(losses_list)}L")
        L.append("")

    # Section 10: Strategy Breakdown (MP vs Squeeze)
    L.append("\n---\n")
    L.append("## Section 10: Strategy Breakdown (MP vs Squeeze)\n")
    for label, trades in [("Config A", ca["trades"]), ("Config B", cb["trades"])]:
        mp_trades = [t for t in trades if t.get("setup_type", "micro_pullback") == "micro_pullback"]
        sq_trades = [t for t in trades if t.get("setup_type") == "squeeze"]
        mp_wins = [t for t in mp_trades if t["pnl"] > 0]
        mp_losses = [t for t in mp_trades if t["pnl"] < 0]
        sq_wins = [t for t in sq_trades if t["pnl"] > 0]
        sq_losses = [t for t in sq_trades if t["pnl"] < 0]
        mp_pnl = sum(t["pnl"] for t in mp_trades)
        sq_pnl = sum(t["pnl"] for t in sq_trades)
        L.append(f"### {label}")
        L.append(f"| Strategy | Trades | Wins | Losses | Win Rate | Total P&L | Avg P&L |")
        L.append(f"|----------|--------|------|--------|----------|-----------|---------|")
        mp_wr = f"{len(mp_wins)/len(mp_trades)*100:.0f}%" if mp_trades else "N/A"
        sq_wr = f"{len(sq_wins)/len(sq_trades)*100:.0f}%" if sq_trades else "N/A"
        mp_avg = f"${mp_pnl/len(mp_trades):+,.0f}" if mp_trades else "N/A"
        sq_avg = f"${sq_pnl/len(sq_trades):+,.0f}" if sq_trades else "N/A"
        L.append(f"| Micro Pullback | {len(mp_trades)} | {len(mp_wins)} | {len(mp_losses)} | {mp_wr} | ${mp_pnl:+,} | {mp_avg} |")
        L.append(f"| Squeeze | {len(sq_trades)} | {len(sq_wins)} | {len(sq_losses)} | {sq_wr} | ${sq_pnl:+,} | {sq_avg} |")
        L.append("")

    L.append("---\n")
    L.append("*Generated from YTD V2 backtest | Top-5 ranked, 5 trade cap, daily loss limit | Tick mode, Alpaca feed, dynamic sizing | Branch: v6-dynamic-sizing*")

    report_path = os.path.join(WORKDIR, MEGATEST_DIR, f"MEGATEST_RESULTS_{COMBO_ID}.md")
    with open(report_path, "w") as f:
        f.write("\n".join(L))
    print(f"\nReport saved: {report_path}")


# ── Entry point ────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"MEGATEST: {COMBO_ID} — {len(DATES)} trading days")
    print(f"Date range: {DATES[0]} to {DATES[-1]}" if DATES else "No dates found!")
    print(f"Starting equity: ${STARTING_EQUITY:,}")
    print(f"Max {MAX_TRADES_PER_DAY} trades/day, daily loss limit ${DAILY_LOSS_LIMIT:,}")
    print(f"Strategy overrides: {COMBO_OVERRIDES[COMBO_ID]}")
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
