#!/usr/bin/env python3
"""
15-Date Continuous Scan Backtest Runner

Re-runs scanner with continuous re-scan for all dates, then simulates
all candidates in two modes (gates OFF, gates ON) with realistic sizing.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

DATES = [
    "2025-01-02", "2025-01-08", "2025-01-27",
    "2025-11-05", "2025-11-06", "2025-11-13",
    "2025-12-08", "2025-12-15",
    "2026-01-06", "2026-01-14", "2026-01-15",
    "2026-01-29", "2026-02-03", "2026-02-05",
    "2026-02-12", "2026-02-20",
]

SCANNER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_results")
VENV_PYTHON = "/tmp/wbot_mac_venv/bin/python"

# Realistic sizing
RISK = "750"
MAX_NOTIONAL = "10000"
MAX_SHARES = "3000"


def needs_rescan(date_str: str) -> bool:
    """Check if date already has new-format scanner results."""
    json_path = os.path.join(SCANNER_DIR, f"{date_str}.json")
    if not os.path.exists(json_path):
        return True
    try:
        with open(json_path) as f:
            data = json.load(f)
        if data and "discovery_method" in data[0]:
            return False
    except Exception:
        pass
    return True


def run_scanner(date_str: str):
    """Run scanner_sim.py for a date."""
    print(f"\n{'='*60}")
    print(f"  SCANNING: {date_str}")
    print(f"{'='*60}")
    result = subprocess.run(
        [VENV_PYTHON, "scanner_sim.py", "--date", date_str],
        capture_output=False, text=True, timeout=600
    )
    return result.returncode == 0


def load_candidates(date_str: str) -> list[dict]:
    """Load scanner candidates from JSON."""
    json_path = os.path.join(SCANNER_DIR, f"{date_str}.json")
    with open(json_path) as f:
        return json.load(f)


def run_simulation(symbol: str, date_str: str, sim_start: str, gates_on: bool) -> dict:
    """Run a single simulation and parse results."""
    env = os.environ.copy()
    env["WB_ENTRY_MODE"] = "pullback"
    env["WB_QUALITY_GATE_ENABLED"] = "1" if gates_on else "0"
    env["WB_NO_REENTRY_ENABLED"] = "1" if gates_on else "0"
    env["WB_MAX_SYMBOL_TRADES"] = "10"
    env["WB_RISK_DOLLARS"] = RISK
    env["WB_MAX_NOTIONAL"] = MAX_NOTIONAL
    env["WB_MAX_SHARES"] = MAX_SHARES

    try:
        result = subprocess.run(
            [VENV_PYTHON, "simulate.py", symbol, date_str,
             sim_start, "12:00", "--ticks", "--feed", "alpaca", "--no-fundamentals"],
            capture_output=True, text=True, timeout=300, env=env
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return {"symbol": symbol, "trades": 0, "pnl": 0.0, "armed": 0,
                "trade_details": [], "gate_activity": [], "error": "timeout"}

    # Parse results
    trades = []
    trade_re = re.compile(
        r'\s+(\d+)\s+(\d{2}:\d{2})\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\S+)\s+\$?([+-]?\d[\d,]*)\s+([+-]?\d+\.\d+)R'
    )
    for m in trade_re.finditer(output):
        trades.append({
            "num": int(m.group(1)),
            "time": m.group(2),
            "entry": float(m.group(3)),
            "stop": float(m.group(4)),
            "r": float(m.group(5)),
            "score": float(m.group(6)),
            "exit": float(m.group(7)),
            "reason": m.group(8),
            "pnl": int(m.group(9).replace(",", "")),
            "r_mult": m.group(10),
        })

    # Parse armed count
    armed = 0
    armed_m = re.search(r'Armed:\s*(\d+)', output)
    if armed_m:
        armed = int(armed_m.group(1))

    # Parse gate activity
    gate_lines = [l.strip() for l in output.split('\n') if 'QUALITY_GATE' in l]

    total_pnl = sum(t["pnl"] for t in trades)

    return {
        "symbol": symbol,
        "trades": len(trades),
        "pnl": total_pnl,
        "armed": armed,
        "trade_details": trades,
        "gate_activity": gate_lines,
        "error": None,
    }


def main():
    # Phase 1: Re-scan all dates
    print("=" * 60)
    print("  PHASE 1: RE-SCANNING ALL DATES")
    print("=" * 60)

    for date_str in DATES:
        if needs_rescan(date_str):
            print(f"\n  >>> Rescanning {date_str}...")
            run_scanner(date_str)
        else:
            print(f"\n  >>> {date_str} already has new-format results, skipping.")

    # Phase 2: Run simulations
    print("\n" + "=" * 60)
    print("  PHASE 2: RUNNING SIMULATIONS")
    print("=" * 60)

    all_results = {}

    for date_str in DATES:
        candidates = load_candidates(date_str)

        # Filter: All Profile A, Profile B with gap > 10%, skip X
        sim_candidates = []
        for c in candidates:
            profile = c.get("profile", "X")
            gap = c.get("gap_pct", 0)
            if profile == "A":
                sim_candidates.append(c)
            elif profile == "B" and gap > 10:
                sim_candidates.append(c)
            # Skip X and B with gap <= 10%

        print(f"\n{'='*60}")
        print(f"  {date_str}: {len(candidates)} total candidates, simulating {len(sim_candidates)}")
        print(f"{'='*60}")

        date_results = {
            "date": date_str,
            "total_candidates": len(candidates),
            "sim_candidates": len(sim_candidates),
            "old_candidates": None,  # Will fill from old data
            "gates_off": {"trades": 0, "pnl": 0, "armed": 0, "trade_details": [], "gate_activity": []},
            "gates_on": {"trades": 0, "pnl": 0, "armed": 0, "trade_details": [], "gate_activity": []},
        }

        for i, c in enumerate(sim_candidates):
            sym = c["symbol"]
            sim_start = c.get("sim_start", "07:00")
            disc_method = c.get("discovery_method", "premarket")
            print(f"  [{i+1}/{len(sim_candidates)}] {sym} (start={sim_start}, {disc_method})")

            # Gates OFF
            r_off = run_simulation(sym, date_str, sim_start, gates_on=False)
            r_off["discovery_method"] = disc_method
            r_off["discovery_time"] = c.get("discovery_time", "premarket")
            date_results["gates_off"]["trades"] += r_off["trades"]
            date_results["gates_off"]["pnl"] += r_off["pnl"]
            date_results["gates_off"]["armed"] += r_off["armed"]
            for t in r_off["trade_details"]:
                t["symbol"] = sym
                t["date"] = date_str
                t["discovery_method"] = disc_method
            date_results["gates_off"]["trade_details"].extend(r_off["trade_details"])
            date_results["gates_off"]["gate_activity"].extend(r_off["gate_activity"])

            # Gates ON
            r_on = run_simulation(sym, date_str, sim_start, gates_on=True)
            r_on["discovery_method"] = disc_method
            r_on["discovery_time"] = c.get("discovery_time", "premarket")
            date_results["gates_on"]["trades"] += r_on["trades"]
            date_results["gates_on"]["pnl"] += r_on["pnl"]
            date_results["gates_on"]["armed"] += r_on["armed"]
            for t in r_on["trade_details"]:
                t["symbol"] = sym
                t["date"] = date_str
                t["discovery_method"] = disc_method
            date_results["gates_on"]["trade_details"].extend(r_on["trade_details"])
            date_results["gates_on"]["gate_activity"].extend(r_on["gate_activity"])

            if r_off["error"]:
                print(f"    [OFF] ERROR: {r_off['error']}")
            elif r_off["trades"] > 0:
                print(f"    [OFF] {r_off['trades']} trades, P&L=${r_off['pnl']:+,}")
            if r_on["error"]:
                print(f"    [ON]  ERROR: {r_on['error']}")
            elif r_on["trades"] > 0:
                print(f"    [ON]  {r_on['trades']} trades, P&L=${r_on['pnl']:+,}")

        all_results[date_str] = date_results

    # Save raw results
    raw_path = os.path.join(SCANNER_DIR, "continuous_scan_15date_raw.json")
    with open(raw_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Raw results saved to {raw_path}")

    # Generate report
    generate_report(all_results)


def generate_report(all_results: dict):
    """Generate the markdown report."""
    report_path = os.path.join(SCANNER_DIR, "CONTINUOUS_SCAN_15DATE_REPORT.md")

    lines = []
    lines.append("# Continuous Scan — 15-Date Expanded Backtest Results")
    lines.append(f"## Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # A. Scanner Comparison
    lines.append("## A. Scanner Comparison")
    lines.append("")
    lines.append("| Date | New Scanner (candidates) | Simulated | Profile A | Rescan Added |")
    lines.append("|------|------------------------|-----------|-----------|-------------|")

    total_candidates = 0
    total_simmed = 0
    for date_str in DATES:
        r = all_results[date_str]
        total_candidates += r["total_candidates"]
        total_simmed += r["sim_candidates"]
        # Count rescan candidates
        json_path = os.path.join(SCANNER_DIR, f"{date_str}.json")
        rescan_count = 0
        profile_a = 0
        try:
            with open(json_path) as f:
                data = json.load(f)
            rescan_count = sum(1 for c in data if c.get("discovery_method") == "rescan")
            profile_a = sum(1 for c in data if c.get("profile") == "A")
        except Exception:
            pass
        lines.append(f"| {date_str} | {r['total_candidates']} | {r['sim_candidates']} | {profile_a} | {rescan_count} |")

    lines.append(f"| **TOTAL** | **{total_candidates}** | **{total_simmed}** | | |")
    lines.append("")

    # B. Results Summary
    lines.append("## B. Results Summary")
    lines.append("")
    lines.append("| Date | Symbols Simmed | Armed (OFF) | Trades (OFF) | P&L (OFF) | Armed (ON) | Trades (ON) | P&L (ON) |")
    lines.append("|------|---------------|------------|-------------|-----------|------------|-------------|----------|")

    total_off_trades = 0
    total_off_pnl = 0
    total_on_trades = 0
    total_on_pnl = 0
    total_off_armed = 0
    total_on_armed = 0

    for date_str in DATES:
        r = all_results[date_str]
        off = r["gates_off"]
        on = r["gates_on"]
        total_off_trades += off["trades"]
        total_off_pnl += off["pnl"]
        total_on_trades += on["trades"]
        total_on_pnl += on["pnl"]
        total_off_armed += off["armed"]
        total_on_armed += on["armed"]

        off_pnl_str = f"${off['pnl']:+,}" if off['trades'] > 0 else "$0"
        on_pnl_str = f"${on['pnl']:+,}" if on['trades'] > 0 else "$0"
        lines.append(
            f"| {date_str} | {r['sim_candidates']} | {off['armed']} | {off['trades']} | {off_pnl_str} "
            f"| {on['armed']} | {on['trades']} | {on_pnl_str} |"
        )

    lines.append(
        f"| **TOTAL** | **{total_simmed}** | **{total_off_armed}** | **{total_off_trades}** | **${total_off_pnl:+,}** "
        f"| **{total_on_armed}** | **{total_on_trades}** | **${total_on_pnl:+,}** |"
    )
    lines.append("")

    # C. Comparison to Previous Results
    lines.append("## C. Comparison to Previous Results")
    lines.append("")
    lines.append("| Metric | OLD Scanner | NEW Scanner | Delta |")
    lines.append("|--------|-----------|-----------|-------|")
    lines.append(f"| Total candidates | ~120 (8 cap/date) | {total_candidates} | +{total_candidates - 120} |")
    lines.append(f"| Trades (OFF) | 7 | {total_off_trades} | {total_off_trades - 7:+d} |")
    lines.append(f"| P&L (OFF) | -$352 | ${total_off_pnl:+,} | ${total_off_pnl + 352:+,} |")
    lines.append(f"| Trades (ON) | 2 | {total_on_trades} | {total_on_trades - 2:+d} |")
    lines.append(f"| P&L (ON) | +$1,154 | ${total_on_pnl:+,} | ${total_on_pnl - 1154:+,} |")
    wr_on = f"{sum(1 for d in DATES for t in all_results[d]['gates_on']['trade_details'] if t['pnl'] > 0) / max(total_on_trades, 1) * 100:.0f}%" if total_on_trades > 0 else "N/A"
    lines.append(f"| Win Rate (ON) | 100% | {wr_on} | |")
    lines.append("")

    # D. All Trades Detail
    lines.append("## D. All Trades")
    lines.append("")

    for mode_label, mode_key in [("Gates OFF", "gates_off"), ("Gates ON", "gates_on")]:
        lines.append(f"### {mode_label}")
        lines.append("")
        all_trades = []
        for date_str in DATES:
            all_trades.extend(all_results[date_str][mode_key]["trade_details"])

        if not all_trades:
            lines.append("No trades taken.")
        else:
            lines.append("| Symbol | Date | Time | Discovery | Entry | Exit | Reason | P&L | R-Mult |")
            lines.append("|--------|------|------|-----------|-------|------|--------|-----|--------|")
            for t in all_trades:
                lines.append(
                    f"| {t.get('symbol', '?')} | {t.get('date', '?')} | {t['time']} | "
                    f"{t.get('discovery_method', '?')} | ${t['entry']:.2f} | ${t['exit']:.2f} | "
                    f"{t['reason']} | ${t['pnl']:+,} | {t['r_mult']} |"
                )
        lines.append("")

    # E. Gate Activity on Rescan Candidates
    lines.append("## E. Gate Activity on Rescan Candidates")
    lines.append("")
    lines.append("Gate checks on candidates found by continuous rescan (not premarket):")
    lines.append("")
    lines.append("```")
    gate_count = 0
    for date_str in DATES:
        for mode_key in ["gates_on"]:
            for gl in all_results[date_str][mode_key]["gate_activity"]:
                if gate_count < 100:  # Cap output
                    lines.append(f"  [{date_str}] {gl}")
                    gate_count += 1
    if gate_count == 0:
        lines.append("  No gate activity recorded on rescan candidates.")
    elif gate_count >= 100:
        lines.append(f"  ... ({gate_count}+ total gate checks, showing first 100)")
    lines.append("```")
    lines.append("")

    # F. Key Findings
    lines.append("## F. Key Findings")
    lines.append("")
    lines.append(f"1. **Candidate pool:** {total_candidates} total across 16 dates (was ~120 with old scanner + 8-cap)")
    lines.append(f"2. **Trade count (OFF):** {total_off_trades} trades, P&L ${total_off_pnl:+,}")
    lines.append(f"3. **Trade count (ON):** {total_on_trades} trades, P&L ${total_on_pnl:+,}")

    # Count rescan vs premarket trades
    rescan_trades_off = sum(1 for d in DATES for t in all_results[d]["gates_off"]["trade_details"]
                           if t.get("discovery_method") == "rescan")
    premarket_trades_off = sum(1 for d in DATES for t in all_results[d]["gates_off"]["trade_details"]
                              if t.get("discovery_method") == "premarket")
    lines.append(f"4. **Trade source (OFF):** {premarket_trades_off} from premarket, {rescan_trades_off} from rescan")

    rescan_pnl_off = sum(t["pnl"] for d in DATES for t in all_results[d]["gates_off"]["trade_details"]
                        if t.get("discovery_method") == "rescan")
    premarket_pnl_off = sum(t["pnl"] for d in DATES for t in all_results[d]["gates_off"]["trade_details"]
                           if t.get("discovery_method") == "premarket")
    lines.append(f"5. **P&L by source (OFF):** premarket ${premarket_pnl_off:+,}, rescan ${rescan_pnl_off:+,}")

    avg_trades = total_off_trades / len(DATES) if DATES else 0
    lines.append(f"6. **Trade frequency:** {avg_trades:.1f} trades/day (OFF), {total_on_trades/len(DATES):.1f} trades/day (ON)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Generated by run_15date_continuous.py | Tick mode, Alpaca feed, realistic sizing ($750 risk, $10K max notional)*")

    with open(report_path, "w") as f:
        f.write("\n".join(lines))

    print(f"\n  Report saved to {report_path}")


if __name__ == "__main__":
    main()
