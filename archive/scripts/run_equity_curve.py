#!/usr/bin/env python3
"""
Equity Curve Backtest Runner — Sequential multi-day backtest with realistic sizing.

Runs simulate.py for each day sequentially, carrying equity forward.
Parses scanner .txt files for candidate lists and simulator output for trade results.

Usage:
    python run_equity_curve.py
"""

import os
import re
import subprocess
import sys

# ─── Configuration ───
STARTING_EQUITY = 30000.0
RISK_DOLLARS = 750
MAX_NOTIONAL = 10000
MAX_SHARES = 3000
MAX_SYMBOLS_PER_DAY = 8
SIM_WINDOW = ("07:00", "12:00")

DATES = [
    "2026-01-05",
    "2026-01-06",
    "2026-01-07",
    "2026-01-08",
    "2026-01-09",
    "2026-01-12",
    "2026-01-13",
    # "2026-01-14",  # no scanner results
    # "2026-01-15",  # no scanner results
    "2026-01-16",
]

SCANNER_DIR = os.path.join(os.path.dirname(__file__), "scanner_results")
REPORT_PATH = os.path.join(SCANNER_DIR, "EQUITY_CURVE_JAN2026.md")

# Unified scanner filters (post-simplification)
MIN_GAP_PCT = 5.0
MIN_PRICE = 2.0
MAX_PRICE = 20.0
# Float filter: 100K to 50M (in millions as shown in scanner: 0.1M to 50M)
MIN_FLOAT_M = 0.01  # effectively allow unknown floats through if they pass other filters
MAX_FLOAT_M = 50.0


def parse_scanner(date_str: str) -> list[dict]:
    """Parse scanner .txt file, apply unified filters, return top N symbols."""
    path = os.path.join(SCANNER_DIR, f"{date_str}.txt")
    if not os.path.exists(path):
        print(f"  WARNING: No scanner file for {date_str}")
        return []

    candidates = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("Scanner") or line.startswith("=") or line.startswith("─"):
                continue
            if line.startswith("Symbol") or line.startswith("Total"):
                continue

            parts = line.split()
            if len(parts) < 4:
                continue

            symbol = parts[0]
            gap_str = parts[1].replace("+", "").replace("%", "")
            try:
                gap_pct = float(gap_str)
            except ValueError:
                continue

            try:
                price = float(parts[2])
            except ValueError:
                continue

            # Parse float — "N/A" means unknown (profile X), skip those
            float_str = parts[3]
            if float_str == "N/A":
                continue  # skip ETFs/unknown float
            try:
                float_m = float(float_str.replace("M", ""))
            except ValueError:
                continue

            # Apply unified filters
            if gap_pct < MIN_GAP_PCT:
                continue
            if price < MIN_PRICE or price > MAX_PRICE:
                continue
            if float_m < 0.1 or float_m > MAX_FLOAT_M:
                continue

            # Parse PM volume
            pm_vol = 0.0
            try:
                pm_vol_str = parts[-1].replace(",", "")
                pm_vol = float(pm_vol_str)
            except (ValueError, IndexError):
                pass

            candidates.append({
                "symbol": symbol,
                "gap_pct": gap_pct,
                "price": price,
                "float_m": float_m,
                "pm_vol": pm_vol,
            })

    # Sort by gap% descending, take top N
    candidates.sort(key=lambda c: c["gap_pct"], reverse=True)
    return candidates[:MAX_SYMBOLS_PER_DAY]


def run_day(date_str: str, equity: float, candidates: list[dict]) -> dict:
    """Run simulate.py for all candidates on a single day. Returns day results."""
    symbols = [c["symbol"] for c in candidates]
    if not symbols:
        return {
            "date": date_str,
            "starting_equity": equity,
            "symbols": 0,
            "trades": [],
            "day_pnl": 0.0,
            "ending_equity": equity,
        }

    # Set env vars for realistic sizing
    env = os.environ.copy()
    env["WB_ENTRY_MODE"] = "pullback"
    env["WB_QUALITY_GATE_ENABLED"] = "1"
    env["WB_NO_REENTRY_ENABLED"] = "1"
    env["WB_MAX_SYMBOL_LOSSES"] = "1"
    env["WB_MAX_SYMBOL_TRADES"] = "10"
    env["WB_RISK_DOLLARS"] = str(RISK_DOLLARS)
    env["WB_MAX_NOTIONAL"] = str(MAX_NOTIONAL)
    env["WB_MAX_SHARES"] = str(MAX_SHARES)
    env["WB_SIM_ACCOUNT_EQUITY"] = str(equity)
    # Gate thresholds (defaults)
    env["WB_MAX_PULLBACK_RETRACE_PCT"] = "65"
    env["WB_MAX_PB_VOL_RATIO"] = "70"
    env["WB_MAX_PB_CANDLES"] = "4"
    env["WB_MIN_IMPULSE_PCT"] = "2.0"
    env["WB_MIN_IMPULSE_VOL_MULT"] = "1.5"
    env["WB_PRICE_SWEET_LOW"] = "3.0"
    env["WB_PRICE_SWEET_HIGH"] = "15.0"

    cmd = [
        sys.executable, "simulate.py",
        *symbols, date_str, SIM_WINDOW[0], SIM_WINDOW[1],
        "--equity", str(equity),
        "--no-fundamentals",
    ]

    print(f"\n{'='*70}")
    print(f"  DAY: {date_str} | Equity: ${equity:,.2f} | Symbols: {', '.join(symbols)}")
    print(f"{'='*70}")

    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env,
        cwd=os.path.dirname(__file__),
        timeout=600,
    )

    output = result.stdout
    if result.returncode != 0:
        print(f"  ERROR: simulate.py returned {result.returncode}")
        print(result.stderr[-500:] if result.stderr else "")
        return {
            "date": date_str,
            "starting_equity": equity,
            "symbols": len(symbols),
            "trades": [],
            "day_pnl": 0.0,
            "ending_equity": equity,
            "output": output,
            "error": True,
        }

    # Parse trades from output
    trades = parse_trades(output, date_str)
    day_pnl = sum(t["pnl"] for t in trades)

    # Parse gate activity
    gate_lines = parse_gate_activity(output)

    print(output)  # show full output

    return {
        "date": date_str,
        "starting_equity": equity,
        "symbols": len(symbols),
        "candidates": candidates,
        "trades": trades,
        "day_pnl": day_pnl,
        "ending_equity": equity + day_pnl,
        "gate_lines": gate_lines,
        "output": output,
    }


def parse_trades(output: str, date_str: str) -> list[dict]:
    """Parse trade lines from simulator output, tracking which symbol each belongs to."""
    trades = []
    current_symbol = "?"

    # Match report header to track current symbol
    header_re = re.compile(r'BACKTEST REPORT:\s+(\S+)')
    # Trade lines look like:
    #   1  09:35  14.2200   13.7800   0.4400    6.0  14.6600  take_profit_core          +310     +1.0R
    trade_re = re.compile(
        r'^\s+(\d+)\s+'           # trade number
        r'(\d{2}:\d{2})\s+'      # entry time
        r'([\d.]+)\s+'           # entry price
        r'([\d.]+)\s+'           # stop price
        r'([\d.]+)\s+'           # R value
        r'([\d.]+)\s+'           # score
        r'([\d.]+)\s+'           # exit price
        r'(\S+)\s+'              # reason
        r'([+-][\d,]+)\s+'       # P&L
        r'([+-][\d.]+)R'         # R-multiple
    )

    for line in output.split("\n"):
        # Track which symbol we're in
        hm = header_re.search(line)
        if hm:
            current_symbol = hm.group(1)

        m = trade_re.match(line)
        if m:
            pnl_str = m.group(9).replace(",", "")
            trades.append({
                "num": int(m.group(1)),
                "date": date_str,
                "symbol": current_symbol,
                "entry_time": m.group(2),
                "entry": float(m.group(3)),
                "stop": float(m.group(4)),
                "r": float(m.group(5)),
                "score": float(m.group(6)),
                "exit": float(m.group(7)),
                "reason": m.group(8),
                "pnl": float(pnl_str),
                "r_mult": float(m.group(10)),
            })

    return trades


def parse_gate_activity(output: str) -> list[str]:
    """Extract quality gate lines from output."""
    gate_lines = []
    for line in output.split("\n"):
        stripped = line.strip()
        if stripped.startswith("QUALITY_GATE") or stripped.startswith("GATE_BLOCKED"):
            gate_lines.append(stripped)
    return gate_lines


def estimate_shares(entry, stop, risk, max_notional, max_shares, equity):
    """Estimate share count using same logic as simulator for verification."""
    r = entry - stop
    if r <= 0:
        return 0, 0.0
    qty_risk = int(risk / r)
    qty_notional = int(max_notional / entry)
    qty_bp = int((equity * 4) / entry) if equity > 0 else 999999
    qty = min(qty_risk, qty_notional, max_shares, qty_bp)
    return qty, qty * entry


def generate_report(days: list[dict]):
    """Generate the equity curve report markdown."""
    lines = []
    lines.append("# Realistic Equity Curve Backtest — January 2026")
    lines.append("")
    lines.append("## Configuration")
    lines.append(f"- Starting equity: ${STARTING_EQUITY:,.0f}")
    lines.append(f"- Risk per trade: ${RISK_DOLLARS}")
    lines.append(f"- Max notional: ${MAX_NOTIONAL:,}")
    lines.append(f"- Max shares: {MAX_SHARES:,}")
    lines.append(f"- Entry mode: pullback")
    lines.append(f"- Quality gates: ON")
    lines.append(f"- Window: {SIM_WINDOW[0]} - {SIM_WINDOW[1]} ET")
    lines.append(f"- Buying power: 4x equity (PDT margin)")
    lines.append("")

    # A. Daily Equity Table
    lines.append("## A. Daily Equity Table")
    lines.append("")
    lines.append("| Day | Date | Starting Equity | Symbols | Trades | Wins | Losses | Day P&L | Ending Equity |")
    lines.append("|-----|------|----------------|---------|--------|------|--------|---------|---------------|")

    all_trades = []
    for i, d in enumerate(days, 1):
        trades = d["trades"]
        wins = sum(1 for t in trades if t["pnl"] >= 0)
        losses = sum(1 for t in trades if t["pnl"] < 0)
        total = len(trades)
        lines.append(
            f"| {i} | {d['date']} | ${d['starting_equity']:,.0f} | {d['symbols']} | "
            f"{total} | {wins} | {losses} | ${d['day_pnl']:+,.0f} | ${d['ending_equity']:,.0f} |"
        )
        all_trades.extend(trades)

    lines.append("")

    # B. Trade Log
    lines.append("## B. Trade Log")
    lines.append("")
    lines.append("| # | Date | Symbol | Entry | Stop | R | Exit | Reason | P&L | R-Mult |")
    lines.append("|---|------|--------|-------|------|---|------|--------|-----|--------|")

    for i, t in enumerate(all_trades, 1):
        # Try to find the symbol from the output context
        symbol = t.get("symbol", "?")
        lines.append(
            f"| {i} | {t['date']} | {symbol} | ${t['entry']:.2f} | ${t['stop']:.2f} | "
            f"${t['r']:.2f} | ${t['exit']:.2f} | {t['reason']} | ${t['pnl']:+,.0f} | {t['r_mult']:+.1f}R |"
        )

    lines.append("")

    # C. Gate Activity
    lines.append("## C. Gate Activity")
    lines.append("")
    for d in days:
        gate_lines = d.get("gate_lines", [])
        if gate_lines:
            lines.append(f"### {d['date']}")
            lines.append("```")
            for gl in gate_lines:
                lines.append(gl)
            lines.append("```")
            lines.append("")

    # D. Equity Curve Summary
    lines.append("## D. Equity Curve Summary")
    lines.append("")
    ending = days[-1]["ending_equity"] if days else STARTING_EQUITY
    total_pnl = ending - STARTING_EQUITY
    total_trades = len(all_trades)
    wins = sum(1 for t in all_trades if t["pnl"] >= 0)
    losses = sum(1 for t in all_trades if t["pnl"] < 0)
    wr = (wins / total_trades * 100) if total_trades > 0 else 0
    days_with_trades = sum(1 for d in days if d["trades"])
    daily_pnls = [d["day_pnl"] for d in days]
    best_day = max(daily_pnls) if daily_pnls else 0
    best_date = days[daily_pnls.index(best_day)]["date"] if daily_pnls else "N/A"
    worst_day = min(daily_pnls) if daily_pnls else 0
    worst_date = days[daily_pnls.index(worst_day)]["date"] if daily_pnls else "N/A"
    avg_daily = total_pnl / len(days) if days else 0

    # Max drawdown from peak
    peak = STARTING_EQUITY
    max_dd = 0.0
    running = STARTING_EQUITY
    for d in days:
        running = d["ending_equity"]
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd

    lines.append("```")
    lines.append(f"Starting equity:  ${STARTING_EQUITY:,.0f}")
    lines.append(f"Ending equity:    ${ending:,.0f}")
    lines.append(f"Total P&L:        ${total_pnl:+,.0f}")
    lines.append(f"Total trades:     {total_trades}")
    lines.append(f"Win rate:         {wr:.0f}%")
    lines.append(f"Avg daily P&L:    ${avg_daily:+,.0f}")
    lines.append(f"Best day:         ${best_day:+,.0f} ({best_date})")
    lines.append(f"Worst day:        ${worst_day:+,.0f} ({worst_date})")
    lines.append(f"Days with trades: {days_with_trades}/{len(days)}")
    lines.append(f"Max drawdown:     -${max_dd:,.0f} (from peak)")
    lines.append("```")
    lines.append("")

    # E. Position Sizing Verification
    lines.append("## E. Position Sizing Verification")
    lines.append("")
    lines.append("See individual trade reports above. Position sizes constrained by:")
    lines.append(f"- Risk: ${RISK_DOLLARS}/R → qty_risk = {RISK_DOLLARS}/R")
    lines.append(f"- Notional cap: ${MAX_NOTIONAL:,} → qty_notional = {MAX_NOTIONAL}/price")
    lines.append(f"- Max shares: {MAX_SHARES:,}")
    lines.append(f"- Buying power: 4x equity (starts at ${STARTING_EQUITY*4:,.0f})")
    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by run_equity_curve.py | {len(days)} trading days*")

    return "\n".join(lines)


def main():
    equity = STARTING_EQUITY
    days = []

    for date_str in DATES:
        candidates = parse_scanner(date_str)
        print(f"\n--- {date_str}: {len(candidates)} candidates after filters ---")
        for c in candidates:
            print(f"  {c['symbol']:>6}  gap={c['gap_pct']:+.1f}%  price=${c['price']:.2f}  float={c['float_m']:.2f}M")

        day_result = run_day(date_str, equity, candidates)
        days.append(day_result)

        # Carry equity forward
        equity = day_result["ending_equity"]
        print(f"\n  >>> Day P&L: ${day_result['day_pnl']:+,.0f} | Equity: ${equity:,.2f}")

    # Generate report
    report = generate_report(days)
    with open(REPORT_PATH, "w") as f:
        f.write(report)

    print(f"\n{'='*70}")
    print(f"  EQUITY CURVE REPORT saved to: {REPORT_PATH}")
    print(f"  Starting: ${STARTING_EQUITY:,.0f} → Ending: ${equity:,.0f} ({equity - STARTING_EQUITY:+,.0f})")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
