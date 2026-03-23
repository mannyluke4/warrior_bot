#!/usr/bin/env python3
"""
January 2026 A/B Comparison: Baseline vs New Features ON
Runs all January trading days, same top-5 ranked selection,
comparing baseline ENV_BASE vs ENV_BASE + new feature flags.
"""

import subprocess
import re
import os
import json
import sys
import math
import time
from datetime import datetime

# ── Config (matches run_ytd_v2_backtest.py) ──────────────────────────────────
STARTING_EQUITY = 30_000
RISK_PCT = 0.025
MAX_TRADES_PER_DAY = 5
DAILY_LOSS_LIMIT = -1500
MAX_NOTIONAL = 50_000
TOP_N = 5

MIN_PM_VOLUME = 50_000
MIN_GAP_PCT = 10
MAX_GAP_PCT = 500
MAX_FLOAT_MILLIONS = 10
MIN_RVOL = 2.0

WORKDIR = os.getenv("WB_WORKDIR", os.path.dirname(os.path.abspath(__file__)))
TICK_CACHE_DIR = os.path.join(WORKDIR, "tick_cache")
SCANNER_DIR = "scanner_results"

JAN_DATES = [
    "2026-01-02", "2026-01-03", "2026-01-05", "2026-01-06", "2026-01-07",
    "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13", "2026-01-14",
    "2026-01-15", "2026-01-16", "2026-01-20", "2026-01-21", "2026-01-22",
    "2026-01-23", "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29",
    "2026-01-30",
]

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

NEW_FEATURES = {
    "WB_MP_ENABLED": "0",              # Keep MP OFF (it's the fix)
    "WB_ALLOW_UNKNOWN_FLOAT": "1",      # Item 2: allow unknown-float stocks
    "WB_SQ_PARTIAL_EXIT_ENABLED": "1", # Item 3: SQ partial exit
    "WB_SQ_WIDE_TRAIL_ENABLED": "1",   # Item 3: SQ wide trail
    "WB_SQ_RUNNER_DETECT_ENABLED": "1",# Item 3: SQ runner detect
    "WB_RANK_GRACE_ENABLED": "1",      # Item 4: rank grace
    "WB_CONVICTION_SIZING_ENABLED": "1",# Item 5: conviction sizing
    "WB_HALT_THROUGH_ENABLED": "1",    # Item 6: halt-through logic
}


# ── Candidate ranking (matches run_ytd_v2_backtest.py) ──────────────────────

def rank_score(candidate):
    pm_vol = candidate.get("pm_volume", 0) or 0
    rvol = candidate.get("relative_volume", 0) or 0
    gap_pct = candidate.get("gap_pct", 0) or 0
    float_m = candidate.get("float_millions", 10) or 10
    rvol_score = math.log10(max(rvol, 0.1) + 1) / math.log10(51)
    vol_score = math.log10(max(pm_vol, 1)) / 8
    gap_score = min(gap_pct, 100) / 100
    float_penalty = min(float_m, 10) / 10
    return (0.4 * rvol_score) + (0.3 * vol_score) + (0.2 * gap_score) + (0.1 * (1 - float_penalty))


def load_and_rank(date_str):
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
        if pm_vol < MIN_PM_VOLUME: continue
        if gap < MIN_GAP_PCT or gap > MAX_GAP_PCT: continue
        if float_m is None or float_m == 0 or float_m > MAX_FLOAT_MILLIONS: continue
        # "X" is legacy name for unknown-float, kept for backward compat with old scanner JSONs
        if profile in ("X", "unknown"): continue
        rvol = c.get("relative_volume", 0) or 0
        if rvol < MIN_RVOL: continue
        filtered.append(c)
    filtered.sort(key=rank_score, reverse=True)
    return filtered[:TOP_N], total, len(filtered)


# ── Simulation runner ────────────────────────────────────────────────────────

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


def run_sim(symbol, date, sim_start, risk, min_score, candidate, extra_env=None):
    env = {**os.environ, **ENV_BASE}
    if extra_env:
        env.update(extra_env)
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
            cmd, capture_output=True, text=True, timeout=300, env=env, cwd=WORKDIR
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
        r_val = float(m.group(5))
        entry_price = float(m.group(3))
        shares = risk / r_val if r_val > 0 else risk
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
            "notional": shares * entry_price,
        })
    return trades


def run_day(top5, date, risk, config_name, extra_env=None):
    day_trades, day_pnl, day_notional = [], 0, 0
    for c in top5:
        if len(day_trades) >= MAX_TRADES_PER_DAY: break
        if day_pnl <= DAILY_LOSS_LIMIT: break
        sym = c["symbol"]
        float_m = c.get("float_millions", 0) or 0
        stock_risk = min(risk, 250) if float_m > 5.0 else risk
        sim_start = c.get("sim_start", "07:00")
        trades = run_sim(sym, date, sim_start, stock_risk, 8.0, c, extra_env)
        time.sleep(0.5)
        for t in trades:
            if len(day_trades) >= MAX_TRADES_PER_DAY: break
            if day_pnl <= DAILY_LOSS_LIMIT: break
            if day_notional + t["notional"] > MAX_NOTIONAL: continue
            day_trades.append(t)
            day_pnl += t["pnl"]
            day_notional += t["notional"]
    return day_trades, day_pnl


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*70}", flush=True)
    print(f"January 2026 A/B Comparison: Baseline vs New Features", flush=True)
    print(f"Dates: {JAN_DATES[0]} — {JAN_DATES[-1]} ({len(JAN_DATES)} days)", flush=True)
    print(f"{'='*70}\n", flush=True)

    eq_base = STARTING_EQUITY
    eq_feat = STARTING_EQUITY
    all_base, all_feat = [], []
    daily_rows = []

    for i, date in enumerate(JAN_DATES):
        top5, total, passed = load_and_rank(date)
        print(f"[{i+1}/{len(JAN_DATES)}] {date}: {total} scanned → {passed} passed → {len(top5)} selected", flush=True)
        if top5:
            for c in top5:
                print(f"    {c['symbol']}: gap={c.get('gap_pct',0):.0f}% rvol={c.get('relative_volume',0):.1f}x float={c.get('float_millions',0):.1f}M", flush=True)

        if not top5:
            daily_rows.append({"date": date, "base_pnl": 0, "feat_pnl": 0,
                                "base_trades": 0, "feat_trades": 0, "note": "no candidates"})
            continue

        risk_base = max(int(eq_base * RISK_PCT), 50)
        risk_feat = max(int(eq_feat * RISK_PCT), 50)

        print(f"  --- BASELINE (risk=${risk_base}) ---", flush=True)
        trades_b, pnl_b = run_day(top5, date, risk_base, "BASELINE")

        print(f"  --- FEATURES ON (risk=${risk_feat}) ---", flush=True)
        trades_f, pnl_f = run_day(top5, date, risk_feat, "FEATURES", extra_env=NEW_FEATURES)

        eq_base += pnl_b
        eq_feat += pnl_f
        all_base.extend(trades_b)
        all_feat.extend(trades_f)

        delta = pnl_f - pnl_b
        daily_rows.append({
            "date": date,
            "base_pnl": pnl_b, "feat_pnl": pnl_f,
            "base_trades": len(trades_b), "feat_trades": len(trades_f),
            "delta": delta,
        })

        print(f"  BASELINE: {len(trades_b)} trades, ${pnl_b:+,}  |  "
              f"FEATURES: {len(trades_f)} trades, ${pnl_f:+,}  |  "
              f"DELTA: ${delta:+,}", flush=True)

    # ── Report ───────────────────────────────────────────────────────────────
    def stats(trades, equity):
        active = [t for t in trades if t["pnl"] != 0]
        wins = [t for t in active if t["pnl"] > 0]
        losses = [t for t in active if t["pnl"] < 0]
        total_pnl = equity - STARTING_EQUITY
        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
        gross_w = sum(t["pnl"] for t in wins)
        gross_l = abs(sum(t["pnl"] for t in losses))
        pf = gross_w / gross_l if gross_l > 0 else float("inf")
        wr = f"{len(wins)}/{len(active)} ({len(wins)/len(active)*100:.0f}%)" if active else "0/0"
        return total_pnl, len(trades), wr, avg_win, avg_loss, pf

    pnl_b, cnt_b, wr_b, aw_b, al_b, pf_b = stats(all_base, eq_base)
    pnl_f, cnt_f, wr_f, aw_f, al_f, pf_f = stats(all_feat, eq_feat)

    print(f"\n{'='*70}", flush=True)
    print(f"JANUARY 2026 RESULTS", flush=True)
    print(f"{'='*70}", flush=True)
    print(f"{'Metric':<28} {'BASELINE':>14} {'FEATURES ON':>14} {'DELTA':>12}", flush=True)
    print(f"{'-'*70}", flush=True)
    print(f"{'Total P&L':<28} ${pnl_b:>+13,} ${pnl_f:>+13,} ${pnl_f-pnl_b:>+11,}", flush=True)
    print(f"{'Final Equity':<28} ${eq_base:>13,.0f} ${eq_feat:>13,.0f}", flush=True)
    print(f"{'Total Trades':<28} {cnt_b:>14} {cnt_f:>14} {cnt_f-cnt_b:>+12}", flush=True)
    print(f"{'Win Rate':<28} {wr_b:>14} {wr_f:>14}", flush=True)
    print(f"{'Avg Win':<28} ${aw_b:>+13,.0f} ${aw_f:>+13,.0f}", flush=True)
    print(f"{'Avg Loss':<28} ${al_b:>+13,.0f} ${al_f:>+13,.0f}", flush=True)
    print(f"{'Profit Factor':<28} {pf_b:>14.2f} {pf_f:>14.2f}", flush=True)

    print(f"\n{'─'*70}", flush=True)
    print(f"{'Date':<14} {'Base P&L':>10} {'Feat P&L':>10} {'Delta':>10} {'B-Tr':>5} {'F-Tr':>5}", flush=True)
    print(f"{'─'*70}", flush=True)
    for r in daily_rows:
        if r.get("note"):
            print(f"{r['date']:<14} {'—':>10} {'—':>10} {'—':>10}  [{r['note']}]", flush=True)
        else:
            delta_str = f"${r['delta']:+,}"
            print(f"{r['date']:<14} ${r['base_pnl']:>+9,} ${r['feat_pnl']:>+9,} {delta_str:>10} {r['base_trades']:>5} {r['feat_trades']:>5}", flush=True)

    # Save JSON for later analysis
    out = {
        "generated": datetime.now().isoformat(),
        "dates": JAN_DATES,
        "baseline": {"total_pnl": pnl_b, "equity": eq_base, "trades": cnt_b, "win_rate": wr_b},
        "features_on": {"total_pnl": pnl_f, "equity": eq_feat, "trades": cnt_f, "win_rate": wr_f},
        "daily": daily_rows,
    }
    out_path = os.path.join(WORKDIR, "jan_compare_results.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults saved to jan_compare_results.json", flush=True)


if __name__ == "__main__":
    main()
