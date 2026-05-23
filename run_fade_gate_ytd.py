#!/usr/bin/env python3
"""Run V0/V1/V4 fade-gate variants across the full YTD tick_cache universe.

For each variant, walks tick_cache/2026-*/ for every (symbol, date) pair,
runs simulate.py 04:00-20:00 (full day — detector needs pre-7am context,
some stocks run post-12pm), then post-filters out trades that fired before
07:00 ET (mirrors live scanner's first checkpoint).

Defaults:
  variants:   V0_baseline, V1_vwap, V4_bodycv
  workers:    8 per variant (ProcessPoolExecutor)
  window:     04:00-20:00 sim, results filtered to time >= 07:00
"""
import json
import os
import re
import subprocess
import sys
import time as _time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

WORKDIR = Path(__file__).parent.resolve()

# Trade line regex (from replay_live_universe.py:55).
TRADE_LINE_RE = re.compile(
    r"^\s+\d+\s+(\d{2}:\d{2})\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+"
    r"([\d.]+)\s+([\d.]+)\s+(\S+)\s+([-+]?\d+)"
)

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

VARIANTS = {
    "V0_baseline": {},
    "V1_vwap": {"WB_MOVE_FADE_VWAP_ENABLED": "1"},
    "V4_bodycv": {"WB_MOVE_FADE_BODY_CV_THRESHOLD": "2.0"},
}

START_FILTER_ET = "07:00"  # drop trades that fire before this


def discover_pairs():
    """Walk tick_cache/2026-*/*.json.gz; return list of (sym, date)."""
    pairs = []
    for d in sorted(WORKDIR.glob("tick_cache/2026-*")):
        if not d.is_dir():
            continue
        date = d.name
        for f in sorted(d.glob("*.json.gz")):
            sym = f.stem.replace(".json", "")
            pairs.append((sym, date))
    return pairs


def run_one(sym, date, env_overrides):
    cmd = [
        sys.executable, str(WORKDIR / "simulate.py"),
        sym, date, "04:00", "20:00",
        "--ticks", "--tick-cache", "tick_cache/",
        "--slippage", "0.07", "--no-fundamentals",
    ]
    env = dict(os.environ)
    env.update(BASE_ENV)
    env.update(env_overrides)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=240, env=env, cwd=str(WORKDIR))
    except subprocess.TimeoutExpired:
        return {"sym": sym, "date": date, "error": "timeout",
                "trades_all": 0, "trades_filtered": 0,
                "pnl_filtered": 0, "pnl_unfiltered": 0,
                "filtered_trades": []}
    trades = []
    for line in (p.stdout + p.stderr).splitlines():
        m = TRADE_LINE_RE.match(line)
        if m:
            trades.append({
                "time": m.group(1),
                "entry": float(m.group(2)),
                "stop": float(m.group(3)),
                "r": float(m.group(4)),
                "score": float(m.group(5)),
                "exit": float(m.group(6)),
                "reason": m.group(7),
                "pnl": int(m.group(8)),
            })
    filtered = [t for t in trades if t["time"] >= START_FILTER_ET]
    return {
        "sym": sym, "date": date,
        "trades_all": len(trades),
        "trades_filtered": len(filtered),
        "pnl_unfiltered": sum(t["pnl"] for t in trades),
        "pnl_filtered": sum(t["pnl"] for t in filtered),
        "filtered_trades": filtered,
    }


def run_variant(variant_name, env_overrides, pairs, workers=8):
    t0 = _time.time()
    results = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(run_one, s, d, env_overrides): (s, d) for s, d in pairs}
        done = 0
        for f in as_completed(futs):
            r = f.result()
            results.append(r)
            done += 1
            if done % 200 == 0:
                elapsed = _time.time() - t0
                rate = done / elapsed
                eta = (len(pairs) - done) / rate if rate > 0 else 0
                print(f"  [{variant_name}] {done}/{len(pairs)} "
                      f"({elapsed/60:.1f}m elapsed, ETA {eta/60:.1f}m)",
                      flush=True)
    total_filtered = sum(r["pnl_filtered"] for r in results)
    total_unfiltered = sum(r["pnl_unfiltered"] for r in results)
    total_trades = sum(r["trades_filtered"] for r in results)
    # Per-day aggregation
    by_day = {}
    for r in results:
        by_day.setdefault(r["date"], {"trades": 0, "pnl": 0})
        by_day[r["date"]]["trades"] += r["trades_filtered"]
        by_day[r["date"]]["pnl"] += r["pnl_filtered"]
    per_day = [{"date": d, "trades": v["trades"], "pnl": v["pnl"]}
               for d, v in sorted(by_day.items())]
    elapsed = _time.time() - t0
    out = {
        "variant": variant_name,
        "env": env_overrides,
        "total_pnl_filtered": total_filtered,
        "total_pnl_unfiltered": total_unfiltered,
        "total_trades_filtered": total_trades,
        "pair_count": len(results),
        "elapsed_sec": int(elapsed),
        "per_day": per_day,
        "per_pair": [{"sym": r["sym"], "date": r["date"],
                       "trades": r["trades_filtered"],
                       "pnl": r["pnl_filtered"]}
                      for r in results],
    }
    json_path = WORKDIR / "backtest_status" / f"fade_gate_ytd_{variant_name}.json"
    with open(json_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  [{variant_name}] DONE in {elapsed/60:.1f}m — "
          f"filtered P&L ${total_filtered:+,} "
          f"({total_trades} trades, {len(results)} pairs)", flush=True)
    return out


def main():
    pairs = discover_pairs()
    print(f"=== YTD Fade-Gate (V0/V1/V4) ===", flush=True)
    print(f"Pairs: {len(pairs)} | Window: 04:00-20:00 | "
          f"Trade filter: time >= {START_FILTER_ET}", flush=True)
    variants_to_run = sys.argv[1:] if len(sys.argv) > 1 else list(VARIANTS.keys())
    summary = {}
    t0 = _time.time()
    for v in variants_to_run:
        if v not in VARIANTS:
            print(f"Unknown variant: {v}", flush=True)
            continue
        print(f"\n--- {v} ---", flush=True)
        summary[v] = run_variant(v, VARIANTS[v], pairs, workers=8)
    print(f"\n=== SUMMARY ===", flush=True)
    print(f"{'Variant':<14} {'Filtered $':>14} {'Trades':>8} {'Elapsed':>10}",
          flush=True)
    for v, r in summary.items():
        print(f"{v:<14} ${r['total_pnl_filtered']:>+13,} "
              f"{r['total_trades_filtered']:>8} "
              f"{r['elapsed_sec']/60:>8.1f}m", flush=True)
    out = WORKDIR / "backtest_status" / "fade_gate_ytd_summary.json"
    with open(out, "w") as f:
        json.dump({v: {k: rv[k] for k in
                       ["variant", "env", "total_pnl_filtered",
                        "total_pnl_unfiltered", "total_trades_filtered",
                        "pair_count", "elapsed_sec", "per_day"]}
                   for v, rv in summary.items()}, f, indent=2)
    print(f"\nTotal elapsed: {(_time.time()-t0)/60:.1f}m", flush=True)
    print(f"Saved: {out}", flush=True)


if __name__ == "__main__":
    main()
