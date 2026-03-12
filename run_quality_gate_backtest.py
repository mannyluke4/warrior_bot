#!/usr/bin/env python3
"""
Quality Gate Backtest — Run 5 dates with gates OFF (baseline) and gates ON.
Forces WB_ENTRY_MODE=pullback for both to ensure gates 1-4 are active.
Captures QUALITY_GATE log lines and trade results for comparison report.
"""

import json
import os
import re
import subprocess
import sys

DATES = ["2025-01-02", "2025-11-05", "2025-11-06", "2026-01-06", "2026-02-03"]

# Base env: direct mode (matches shell env and directive baseline)
BASE_ENV = {
    "WB_QUALITY_GATE_ENABLED": "0",
    "WB_NO_REENTRY_ENABLED": "0",
}

# Gates ON env
GATE_ENV = {
    "WB_QUALITY_GATE_ENABLED": "1",
    "WB_MAX_PULLBACK_RETRACE_PCT": "65",
    "WB_MAX_PB_VOL_RATIO": "70",
    "WB_MAX_PB_CANDLES": "4",
    "WB_MIN_IMPULSE_PCT": "2.0",
    "WB_MIN_IMPULSE_VOL_MULT": "1.5",
    "WB_PRICE_SWEET_LOW": "3.0",
    "WB_PRICE_SWEET_HIGH": "15.0",
    "WB_NO_REENTRY_ENABLED": "1",
    "WB_MAX_SYMBOL_LOSSES": "1",
    "WB_MAX_SYMBOL_TRADES": "10",
}


def parse_output(output: str) -> dict:
    """Parse simulate.py output for P&L, trades, and gate logs."""
    result = {
        "pnl": 0.0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "gate_logs": [],
        "trade_lines": [],
        "raw": output,
    }

    # P&L
    m = re.search(r'Gross P&L:\s*\$([+-]?[\d,]+(?:\.\d+)?)', output)
    if m:
        result["pnl"] = float(m.group(1).replace(',', ''))

    # Trades / Wins / Losses
    m = re.search(r'Trades:\s*(\d+)', output)
    if m:
        result["trades"] = int(m.group(1))
    m = re.search(r'Wins:\s*(\d+)', output)
    if m:
        result["wins"] = int(m.group(1))
    m = re.search(r'Losses:\s*(\d+)', output)
    if m:
        result["losses"] = int(m.group(1))

    # Gate logs
    for line in output.split('\n'):
        if 'QUALITY_GATE' in line:
            result["gate_logs"].append(line.strip())
        if 'quality_gate_failed' in line:
            result["gate_logs"].append(line.strip())

    # Trade table lines (match the formatted trade table)
    for line in output.split('\n'):
        if re.match(r'\s+\d+\s+\d{2}:\d{2}', line):
            result["trade_lines"].append(line.strip())

    return result


def run_sim(symbol: str, date: str, env_overrides: dict) -> dict:
    """Run simulate.py with given env overrides."""
    env = os.environ.copy()
    env.update(env_overrides)

    cmd = [
        sys.executable, "simulate.py",
        symbol, date, "07:00", "12:00",
        "--ticks", "--feed", "alpaca", "--no-fundamentals"
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
        output = proc.stdout + proc.stderr
        return parse_output(output)
    except subprocess.TimeoutExpired:
        return {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0,
                "gate_logs": ["TIMEOUT"], "trade_lines": [], "raw": "TIMEOUT"}
    except Exception as e:
        return {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0,
                "gate_logs": [f"ERROR: {e}"], "trade_lines": [], "raw": str(e)}


def main():
    # Only run symbols that had activity in the baseline or might have activity with gates
    # Get all candidates from scanner JSONs
    all_symbols_by_date = {}
    for date in DATES:
        json_path = f"scanner_results/{date}.json"
        if os.path.exists(json_path):
            with open(json_path) as f:
                candidates = json.load(f)
            all_symbols_by_date[date] = [c["symbol"] for c in candidates]

    # Phase 1: Run baseline (gates OFF, pullback mode)
    print("=" * 60)
    print("  PHASE 1: BASELINE (gates OFF, pullback mode)")
    print("=" * 60)

    baseline = {}
    for date in DATES:
        symbols = all_symbols_by_date.get(date, [])
        print(f"\n  {date} — {len(symbols)} candidates")
        date_results = {}
        for sym in symbols:
            result = run_sim(sym, date, BASE_ENV)
            date_results[sym] = result
            if result["trades"] > 0:
                print(f"    {sym}: {result['trades']}T {result['wins']}W/{result['losses']}L ${result['pnl']:+,.0f}")
        baseline[date] = date_results

        total_t = sum(r["trades"] for r in date_results.values())
        total_p = sum(r["pnl"] for r in date_results.values())
        print(f"  DATE: {total_t} trades, ${total_p:+,.0f}")

    # Phase 2: Run with gates ON
    print("\n" + "=" * 60)
    print("  PHASE 2: GATES ON (all 5 gates, pullback mode)")
    print("=" * 60)

    gated = {}
    for date in DATES:
        symbols = all_symbols_by_date.get(date, [])
        print(f"\n  {date} — {len(symbols)} candidates")
        date_results = {}
        for sym in symbols:
            result = run_sim(sym, date, GATE_ENV)
            date_results[sym] = result
            if result["trades"] > 0:
                print(f"    {sym}: {result['trades']}T {result['wins']}W/{result['losses']}L ${result['pnl']:+,.0f}")
            elif any("FAIL" in l for l in result["gate_logs"]):
                fail_gates = set()
                for l in result["gate_logs"]:
                    if "FAIL" in l:
                        m = re.search(r'gate=(\w+)', l)
                        if m:
                            fail_gates.add(m.group(1))
                print(f"    {sym}: BLOCKED by {', '.join(fail_gates)}")
        gated[date] = date_results

        total_t = sum(r["trades"] for r in date_results.values())
        total_p = sum(r["pnl"] for r in date_results.values())
        print(f"  DATE: {total_t} trades, ${total_p:+,.0f}")

    # Save raw data
    save_data = {"baseline": {}, "gated": {}}
    for date in DATES:
        save_data["baseline"][date] = {}
        save_data["gated"][date] = {}
        for src, dest_key in [(baseline, "baseline"), (gated, "gated")]:
            for sym, r in src.get(date, {}).items():
                save_data[dest_key][date][sym] = {
                    "pnl": r["pnl"],
                    "trades": r["trades"],
                    "wins": r["wins"],
                    "losses": r["losses"],
                    "gate_logs": r["gate_logs"],
                    "trade_lines": r.get("trade_lines", []),
                }

    with open("scanner_results/quality_gate_backtest_raw.json", "w") as f:
        json.dump(save_data, f, indent=2)

    # Summary
    print("\n" + "=" * 60)
    print("  COMPARISON SUMMARY")
    print("=" * 60)

    print(f"\n  {'Date':<12} {'Base T':>7} {'Gate T':>7} {'Filt':>5} {'Base P&L':>10} {'Gate P&L':>10} {'Delta':>8}")
    print(f"  {'-'*12} {'-'*7} {'-'*7} {'-'*5} {'-'*10} {'-'*10} {'-'*8}")

    grand_base_t = grand_gate_t = 0
    grand_base_p = grand_gate_p = 0.0
    grand_base_w = grand_gate_w = 0
    grand_base_l = grand_gate_l = 0

    for date in DATES:
        bt = sum(r["trades"] for r in baseline.get(date, {}).values())
        bp = sum(r["pnl"] for r in baseline.get(date, {}).values())
        bw = sum(r["wins"] for r in baseline.get(date, {}).values())
        bl = sum(r["losses"] for r in baseline.get(date, {}).values())
        gt = sum(r["trades"] for r in gated.get(date, {}).values())
        gp = sum(r["pnl"] for r in gated.get(date, {}).values())
        gw = sum(r["wins"] for r in gated.get(date, {}).values())
        gl = sum(r["losses"] for r in gated.get(date, {}).values())
        filt = bt - gt
        delta = gp - bp
        print(f"  {date:<12} {bt:>7} {gt:>7} {filt:>5} ${bp:>+9,.0f} ${gp:>+9,.0f} ${delta:>+7,.0f}")

        grand_base_t += bt
        grand_gate_t += gt
        grand_base_p += bp
        grand_gate_p += gp
        grand_base_w += bw
        grand_gate_w += gw
        grand_base_l += bl
        grand_gate_l += gl

    filt = grand_base_t - grand_gate_t
    delta = grand_gate_p - grand_base_p
    print(f"  {'TOTAL':<12} {grand_base_t:>7} {grand_gate_t:>7} {filt:>5} ${grand_base_p:>+9,.0f} ${grand_gate_p:>+9,.0f} ${delta:>+7,.0f}")

    base_wr = (grand_base_w / (grand_base_w + grand_base_l) * 100) if (grand_base_w + grand_base_l) > 0 else 0
    gate_wr = (grand_gate_w / (grand_gate_w + grand_gate_l) * 100) if (grand_gate_w + grand_gate_l) > 0 else 0
    print(f"\n  Baseline: {grand_base_t}T {grand_base_w}W/{grand_base_l}L {base_wr:.1f}% WR ${grand_base_p:+,.0f}")
    print(f"  Gates ON: {grand_gate_t}T {grand_gate_w}W/{grand_gate_l}L {gate_wr:.1f}% WR ${grand_gate_p:+,.0f}")
    print(f"\n  Raw data: scanner_results/quality_gate_backtest_raw.json")


if __name__ == "__main__":
    main()
