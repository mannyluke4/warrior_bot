#!/usr/bin/env python3
"""
January backtest comparison: baseline (all items OFF) vs features ON (items 1-6).
Runs simulate.py in tick mode for each January stock the bot actually traded.
"""
import subprocess, sys, os, re

TICK_CACHE = "tick_cache/"
RISK = 1000

# January stocks actually traded, with sim_start from scanner results
JAN_STOCKS = [
    ("2026-01-02", "FUTG",  "10:00"),
    ("2026-01-07", "NVVE",  "10:00"),
    ("2026-01-08", "ACON",  "07:00"),
    ("2026-01-12", "BDSX",  "07:00"),
    ("2026-01-13", "AHMA",  "08:00"),
    ("2026-01-13", "SPRC",  "07:00"),
    ("2026-01-14", "ROLR",  "08:30"),
    ("2026-01-15", "CJMB",  "09:00"),
    ("2026-01-15", "SPHL",  "07:00"),
    ("2026-01-16", "VERO",  "07:00"),
    ("2026-01-20", "POLA",  "07:00"),
    ("2026-01-21", "GITS",  "10:30"),
    ("2026-01-21", "SLGB",  "07:00"),
    ("2026-01-22", "IOTR",  "07:00"),
    ("2026-01-23", "AUST",  "10:00"),
    ("2026-01-23", "MOVE",  "07:00"),
    ("2026-01-26", "BATL",  "07:00"),
    ("2026-01-27", "CYN",   "07:00"),
    ("2026-01-27", "XHLD",  "10:00"),
    ("2026-01-30", "PMN",   "08:30"),
]

# Baseline: all new items gated OFF (default state)
# Item 1 (MP gate): WB_MP_ENABLED=0 is default — SQ only
BASELINE_ENV = {
    "WB_MP_ENABLED": "0",
    "WB_ALLOW_UNKNOWN_FLOAT": "0",
    "WB_SQ_PARTIAL_EXIT_ENABLED": "0",
    "WB_SQ_WIDE_TRAIL_ENABLED": "0",
    "WB_SQ_RUNNER_DETECT_ENABLED": "0",
    "WB_RANK_GRACE_ENABLED": "0",
    "WB_CONVICTION_SIZING_ENABLED": "0",
    "WB_HALT_THROUGH_ENABLED": "0",
}

# Features ON: all items enabled
FEATURES_ON_ENV = {
    "WB_MP_ENABLED": "0",          # Item 1: keep MP off (that's the point)
    "WB_ALLOW_UNKNOWN_FLOAT": "1",  # Item 2
    "WB_SQ_PARTIAL_EXIT_ENABLED": "1",  # Item 3 Fix 1
    "WB_SQ_WIDE_TRAIL_ENABLED": "1",    # Item 3 Fix 2
    "WB_SQ_RUNNER_DETECT_ENABLED": "1", # Item 3 Fix 3
    "WB_RANK_GRACE_ENABLED": "1",       # Item 4
    "WB_CONVICTION_SIZING_ENABLED": "1",# Item 5
    "WB_HALT_THROUGH_ENABLED": "1",     # Item 6
}

TRADE_PAT = re.compile(
    r"^\s*\d+\s+[\d:]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+\S+"
    r"\s+([+-]\$[\d,]+)\s+([+-][\d.]+R)", re.MULTILINE
)
PNL_PAT = re.compile(r"Gross P&L:\s*\$([+-][\d,]+)")
TRADES_PAT = re.compile(r"Trades:\s*(\d+)")


def run_sim(date, symbol, sim_start, extra_env):
    env = {**os.environ, **extra_env}
    cmd = [sys.executable, "simulate.py", symbol, date, sim_start, "12:00",
           "--ticks", "--tick-cache", TICK_CACHE,
           "--risk", str(RISK), "--no-fundamentals"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
        out = r.stdout + r.stderr
        pnl_m = PNL_PAT.search(out)
        trades_m = TRADES_PAT.search(out)
        pnl = int(pnl_m.group(1).replace(",", "").replace("+", "")) if pnl_m else 0
        n_trades = int(trades_m.group(1)) if trades_m else 0
        return pnl, n_trades
    except Exception as e:
        print(f"  ERROR {symbol} {date}: {e}")
        return 0, 0


def main():
    print(f"\n{'='*70}")
    print(f"  JANUARY BACKTEST COMPARISON — Baseline vs Features ON")
    print(f"  20 stocks the bot actually traded in January 2026")
    print(f"  Strategy: SQ-only (MP disabled), --ticks mode, 07:00-12:00 ET")
    print(f"{'='*70}\n")

    print(f"{'Stock':<8} {'Date':<12} {'SimStart':<10} {'Baseline P&L':>14} {'Features ON P&L':>16} {'Delta':>10} {'#Trades Base':>13} {'#Trades ON':>11}")
    print("-" * 100)

    total_base = 0
    total_on = 0
    results = []

    for date, symbol, sim_start in JAN_STOCKS:
        print(f"  Running {symbol} {date}...", end=" ", flush=True)
        base_pnl, base_n = run_sim(date, symbol, sim_start, BASELINE_ENV)
        on_pnl, on_n = run_sim(date, symbol, sim_start, FEATURES_ON_ENV)
        delta = on_pnl - base_pnl
        total_base += base_pnl
        total_on += on_pnl
        results.append((date, symbol, sim_start, base_pnl, on_pnl, delta, base_n, on_n))
        print(f"done  base=${base_pnl:+,}  on=${on_pnl:+,}  delta={delta:+,}")

    print(f"\n{'='*70}")
    print(f"\n{'Stock':<8} {'Date':<12} {'SimStart':<10} {'Baseline P&L':>14} {'Features ON P&L':>16} {'Delta':>10} {'Trades(B)':>10} {'Trades(ON)':>11}")
    print("-" * 100)
    for date, symbol, sim_start, base_pnl, on_pnl, delta, base_n, on_n in results:
        flag = " ✅" if delta > 0 else (" ❌" if delta < 0 else "")
        print(f"{symbol:<8} {date:<12} {sim_start:<10} ${base_pnl:>+12,}  ${on_pnl:>+14,}  {delta:>+9,}{flag}  {base_n:>8}   {on_n:>8}")

    print("-" * 100)
    total_delta = total_on - total_base
    print(f"{'TOTAL':<32} ${total_base:>+12,}  ${total_on:>+14,}  {total_delta:>+9,}")
    print(f"\n  Net change from features ON: ${total_delta:+,}")


if __name__ == "__main__":
    main()
