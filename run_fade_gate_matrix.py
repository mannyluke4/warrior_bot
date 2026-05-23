#!/usr/bin/env python3
"""Run the MOVE_STRIKE fade-gate variant matrix per directive
cowork_reports/2026-05-23_movestrike_fade_gate_directive.md.

For each variant V1..V8, runs:
  - Set A: 31 historical vertical-class days (via simulate.py)
  - Set B: 10-day live-universe replay (2026-05-07..2026-05-20)

Outputs per-variant JSON + summary table.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

WORKDIR = Path(__file__).parent.resolve()

# Set A: 31 historical pairs (mirrors run_regime_shift_test_set.py)
SET_A = [
    ("SPHL", "2026-01-15"), ("GLTO", "2025-10-07"), ("BIRD", "2026-04-15"),
    ("CYN", "2025-06-26"), ("BGLC", "2025-07-01"), ("MBIO", "2025-07-07"),
    ("VERO", "2026-01-16"), ("XBIO", "2025-10-08"), ("FGI", "2025-09-16"),
    ("CYCN", "2026-04-01"), ("CETX", "2025-12-08"), ("HOTH", "2025-01-07"),
    ("SXTP", "2026-01-22"), ("HWH", "2025-09-02"), ("TNON", "2025-03-25"),
    ("AGMH", "2025-09-19"), ("AVX", "2025-09-22"), ("STI", "2025-10-13"),
    ("AIHS", "2025-09-03"), ("QTTB", "2025-12-01"), ("APM", "2025-08-21"),
    ("XPON", "2025-08-14"), ("AIXC", "2025-09-22"), ("OLOX", "2025-10-10"),
    ("PLRZ", "2025-12-02"), ("KTTA", "2025-05-06"), ("NDRA", "2025-07-08"),
    ("HOUR", "2025-09-05"), ("IVF", "2026-01-20"), ("COOT", "2025-10-15"),
    ("PCLA", "2026-05-21"),
]

SET_B_START = "2026-05-07"
SET_B_END = "2026-05-20"

# Base env (all variants share this — Stage 1 +$3,411 config)
BASE_ENV = {
    "WB_BT_MOVE_STRIKE": "1",
    "WB_BT_MOVE_HWM_EXIT": "1",
    "WB_BT_MOVE_REENTRY_GREEN": "1",
    "WB_BT_MOVE_REENTRY_BLOCK_SAME_BAR": "1",
    "WB_BT_MOVE_STAY_ARMED": "1",
    "WB_BT_MOVE_MAX_BELOW_ARM_PCT": "3.0",
    "WB_REGIME_SHIFT_ENABLED": "1",
    "WB_REGIME_SHIFT_RATIO_THRESHOLD": "4.0",
    "WB_REGIME_SHIFT_REQUIRE_ARMED": "1",
    "WB_REGIME_SHIFT_MAX_PER_SYMBOL": "1",
    "WB_SQUEEZE_VERSION": "2",
}

# Per-variant fade-gate env overrides
VARIANTS = {
    "V0_baseline": {},  # control — no fade gate
    "V1_vwap": {
        "WB_MOVE_FADE_VWAP_ENABLED": "1",
    },
    "V2_drawdown": {
        "WB_MOVE_FADE_OPEN_DRAWDOWN_PCT": "5.0",
    },
    "V3_downtrend": {
        "WB_MOVE_FADE_DOWNTREND_BARS": "3",
    },
    "V4_bodycv": {
        "WB_MOVE_FADE_BODY_CV_THRESHOLD": "2.0",
    },
    "V5_vwap_drawdown_OR": {
        "WB_MOVE_FADE_VWAP_ENABLED": "1",
        "WB_MOVE_FADE_OPEN_DRAWDOWN_PCT": "5.0",
        "WB_MOVE_FADE_COMBINE_MODE": "any",
    },
    "V6_vwap_downtrend_OR": {
        "WB_MOVE_FADE_VWAP_ENABLED": "1",
        "WB_MOVE_FADE_DOWNTREND_BARS": "3",
        "WB_MOVE_FADE_COMBINE_MODE": "any",
    },
    "V7_all_OR": {
        "WB_MOVE_FADE_VWAP_ENABLED": "1",
        "WB_MOVE_FADE_OPEN_DRAWDOWN_PCT": "5.0",
        "WB_MOVE_FADE_DOWNTREND_BARS": "3",
        "WB_MOVE_FADE_BODY_CV_THRESHOLD": "2.0",
        "WB_MOVE_FADE_COMBINE_MODE": "any",
    },
    "V8_vwap_drawdown_AND": {
        "WB_MOVE_FADE_VWAP_ENABLED": "1",
        "WB_MOVE_FADE_OPEN_DRAWDOWN_PCT": "5.0",
        "WB_MOVE_FADE_COMBINE_MODE": "all",
    },
}


def merge_env(overrides):
    env = dict(os.environ)
    env.update(BASE_ENV)
    env.update(overrides)
    return env


def run_set_a_one(symbol, date, env):
    cmd = [
        sys.executable, "simulate.py",
        symbol, date, "04:00", "20:00",
        "--ticks", "--tick-cache", "tick_cache/",
        "--slippage", "0.07", "--no-fundamentals",
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=240, env=env, cwd=WORKDIR)
    except subprocess.TimeoutExpired:
        return {"symbol": symbol, "date": date, "error": "timeout",
                "pnl": 0, "trades": 0, "fade_blocks": 0}
    out = p.stdout
    m_pnl = re.search(r"Gross P&L:\s+\$([+-]?[\d,]+)", out)
    pnl = int(m_pnl.group(1).replace(",", "")) if m_pnl else 0
    m_tr = re.search(r"Trades:\s+(\d+)\s+\|", out)
    trades = int(m_tr.group(1)) if m_tr else 0
    fade_blocks = out.count("MOVE_FADE_GATE_BLOCK")
    return {
        "symbol": symbol, "date": date,
        "pnl": pnl, "trades": trades, "fade_blocks": fade_blocks,
    }


def run_set_a(variant, env):
    from concurrent.futures import ProcessPoolExecutor, as_completed
    pending = []
    for sym, date in SET_A:
        cache_path = WORKDIR / "tick_cache" / date / f"{sym}.json.gz"
        if not cache_path.exists():
            continue
        pending.append((sym, date))
    results = []
    # 6 workers — Set A sims are mostly CPU + tick replay.
    with ProcessPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(run_set_a_one, s, d, env): (s, d) for s, d in pending}
        for f in as_completed(futs):
            results.append(f.result())
    total = sum(r["pnl"] for r in results)
    total_trades = sum(r["trades"] for r in results)
    total_blocks = sum(r["fade_blocks"] for r in results)
    avx = [r for r in results if r["symbol"] == "AVX" and r["date"] == "2025-09-22"]
    avx_pnl = avx[0]["pnl"] if avx else None
    avx_trades = avx[0]["trades"] if avx else None
    return {
        "variant": variant,
        "set_a_total_pnl": total,
        "set_a_total_trades": total_trades,
        "set_a_total_fade_blocks": total_blocks,
        "set_a_avx_pnl": avx_pnl,
        "set_a_avx_trades": avx_trades,
        "set_a_per_day": results,
    }


def run_set_b(variant, env):
    """Use replay_live_universe.py to replay 2026-05-07..2026-05-20."""
    label = f"fade_{variant}"
    cmd = [
        sys.executable, "replay_live_universe.py",
        "--start", SET_B_START, "--end", SET_B_END,
        "--label", label,
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=1800, env=env, cwd=WORKDIR)
    except subprocess.TimeoutExpired:
        return {"variant": variant, "set_b_error": "timeout"}
    json_path = WORKDIR / "backtest_status" / f"replay_{label}_{SET_B_START}_{SET_B_END}.json"
    if not json_path.exists():
        return {"variant": variant, "set_b_error": "no_output",
                "stdout_tail": p.stdout[-500:]}
    with open(json_path) as f:
        data = json.load(f)
    return {
        "set_b_total_pnl": data.get("total_pnl"),
        "set_b_trades": len(data.get("trades", [])),
        "set_b_per_day": data.get("per_day", []),
        "set_b_json_path": str(json_path),
    }


def main():
    variants_to_run = sys.argv[1:] if len(sys.argv) > 1 else list(VARIANTS.keys())
    all_results = {}
    t0 = time.time()
    for v_name in variants_to_run:
        if v_name not in VARIANTS:
            print(f"Unknown variant: {v_name}", flush=True)
            continue
        env = merge_env(VARIANTS[v_name])
        print(f"\n=== {v_name} ===", flush=True)
        print(f"  fade_env: {VARIANTS[v_name]}", flush=True)
        ta = time.time()
        a = run_set_a(v_name, env)
        print(f"  Set A: ${a['set_a_total_pnl']:+,} ({a['set_a_total_trades']} trades, "
              f"AVX=${a['set_a_avx_pnl']:+,}, {a['set_a_total_fade_blocks']} blocks) "
              f"[{time.time()-ta:.0f}s]", flush=True)
        tb = time.time()
        b = run_set_b(v_name, env)
        print(f"  Set B: ${b.get('set_b_total_pnl',0):+,} "
              f"({b.get('set_b_trades',0)} trades) "
              f"[{time.time()-tb:.0f}s]", flush=True)
        all_results[v_name] = {**a, **b}
        out = WORKDIR / "backtest_status" / f"fade_gate_{v_name}.json"
        with open(out, "w") as f:
            json.dump(all_results[v_name], f, indent=2)
    # Summary table
    print("\n=== SUMMARY ===", flush=True)
    print(f"{'Variant':<28} {'Set A P&L':>10} {'AVX':>10} {'Set B P&L':>10}", flush=True)
    for v, r in all_results.items():
        print(f"{v:<28} ${r.get('set_a_total_pnl',0):>+9,} "
              f"${r.get('set_a_avx_pnl',0) or 0:>+9,} "
              f"${r.get('set_b_total_pnl',0) or 0:>+9,}", flush=True)
    out = WORKDIR / "backtest_status" / "fade_gate_matrix_summary.json"
    with open(out, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nElapsed: {(time.time()-t0)/60:.1f} min", flush=True)
    print(f"Saved: {out}", flush=True)


if __name__ == "__main__":
    main()
