#!/usr/bin/env python3
"""
tw_exit_analysis.py — Compare TW-enabled vs TW-disabled exits for every TW trade.

Runs simulate.py twice for each stock: once with TW on, once with TW off.
Captures the exit difference and post-exit price action.

Usage:
    python tw_exit_analysis.py ALL
    python tw_exit_analysis.py GITS 2026-03-10
"""

import os
import sys
import re
import subprocess
from datetime import datetime, timedelta
from typing import Optional

import pytz
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

load_dotenv()

ET = pytz.timezone("US/Eastern")
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
hist_client = StockHistoricalDataClient(API_KEY, API_SECRET)

# All stocks that had TW exits (or might have TW exits)
# We run both TW=on and TW=off for each, then compare
TW_STOCKS = [
    # 49-day backtest winners with TW exits
    {"symbol": "VERO", "date": "2026-01-16", "float_m": 1.6, "gap_pct": 40.0},
    {"symbol": "ROLR", "date": "2026-01-14", "float_m": 3.78, "gap_pct": 340.0},
    {"symbol": "AGPU", "date": "2026-01-15", "float_m": 2.0, "gap_pct": 20.0},
    {"symbol": "WHLR", "date": "2026-02-06", "float_m": 1.5, "gap_pct": 15.0},
    {"symbol": "PMN",  "date": "2026-01-30", "float_m": 2.0, "gap_pct": 10.0},
    # 49-day losers with TW exits
    {"symbol": "AUST", "date": "2026-01-23", "float_m": 2.0, "gap_pct": 15.0},
    {"symbol": "RUBI", "date": "2026-02-19", "float_m": 3.0, "gap_pct": 12.0},
    # Weekly TW exits
    {"symbol": "TLYS", "date": "2026-03-12", "float_m": 9.29, "gap_pct": 62.6},
    {"symbol": "BIAF", "date": "2026-03-17", "float_m": 4.35, "gap_pct": 19.9},
    {"symbol": "LUNL", "date": "2026-03-17", "float_m": 0.17, "gap_pct": 10.3},
    {"symbol": "BMNZ", "date": "2026-03-18", "float_m": 2.0, "gap_pct": 13.6},
    # Also run OKLL which was BE but check if TW would have fired
    {"symbol": "OKLL", "date": "2026-03-17", "float_m": 1.36, "gap_pct": 19.9},
]


def run_simulation(symbol, date, tw_enabled, float_m=0):
    """Run simulate.py and parse the output."""
    env = os.environ.copy()
    env["WB_EXIT_ON_TOPPING_WICKY"] = "1" if tw_enabled else "0"
    # Simulator doesn't read WB_EXIT_ON_TOPPING_WICKY directly.
    # To disable TW in sim: set grace period to 9999 minutes (effectively infinite).
    if not tw_enabled:
        env["WB_TOPPING_WICKY_GRACE_MIN"] = "9999"
    if float_m > 0:
        env["WB_SCANNER_FLOAT_M"] = str(float_m)

    cmd = [
        sys.executable, "simulate.py",
        symbol, date, "07:00", "12:00",
        "--ticks",
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            env=env,
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}

    return parse_sim_output(output)


def parse_sim_output(output):
    """Parse simulate.py output for trade results."""
    trades = []

    # Parse trade lines: "    1   08:45  16.9900  16.8000  0.1900   10.1  17.0300  topping_wicky_exit_full      +141    +0.2R"
    trade_pattern = re.compile(
        r'\s+(\d+)\s+'           # trade number
        r'(\d+:\d+)\s+'         # time
        r'([\d.]+)\s+'          # entry
        r'([\d.]+)\s+'          # stop
        r'([\d.]+)\s+'          # R
        r'([\d.]+)\s+'          # score
        r'([\d.]+)\s+'          # exit price
        r'(\S+)\s+'             # reason
        r'([+-]?\d[\d,]*)\s+'   # P&L
        r'([+-]?\d+\.?\d*)R'    # R-mult
    )

    for line in output.split("\n"):
        m = trade_pattern.search(line)
        if m:
            pnl_str = m.group(9).replace(",", "")
            trades.append({
                "num": int(m.group(1)),
                "time": m.group(2),
                "entry": float(m.group(3)),
                "stop": float(m.group(4)),
                "r": float(m.group(5)),
                "score": float(m.group(6)),
                "exit": float(m.group(7)),
                "reason": m.group(8),
                "pnl": int(float(pnl_str)),
                "r_mult": float(m.group(10)),
            })

    # Parse summary line
    no_trades = "No trades taken" in output
    armed = 0
    signals = 0
    arm_match = re.search(r'Armed:\s+(\d+)', output)
    sig_match = re.search(r'Signals:\s+(\d+)', output)
    if arm_match:
        armed = int(arm_match.group(1))
    if sig_match:
        signals = int(sig_match.group(1))

    return {
        "trades": trades,
        "no_trades": no_trades,
        "armed": armed,
        "signals": signals,
    }


def fetch_post_exit_bars(symbol, date_str, exit_time, minutes=30):
    """Fetch bars after exit for price action analysis."""
    date = datetime.strptime(date_str, "%Y-%m-%d")
    eh, em = int(exit_time.split(":")[0]), int(exit_time.split(":")[1])
    start = ET.localize(datetime(date.year, date.month, date.day, eh, em, 0))
    end = start + timedelta(minutes=minutes)
    market_close = ET.localize(datetime(date.year, date.month, date.day, 16, 0, 0))
    if end > market_close:
        end = market_close

    req = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
    )
    bars = hist_client.get_stock_bars(req).data.get(symbol, [])
    return [{
        "time": b.timestamp.astimezone(ET).strftime("%H:%M") if b.timestamp.tzinfo else str(b.timestamp),
        "high": float(b.high),
        "low": float(b.low),
        "close": float(b.close),
    } for b in bars]


def analyze_stock(stock):
    """Run TW=on and TW=off, compare results."""
    sym = stock["symbol"]
    date = stock["date"]
    float_m = stock.get("float_m", 0)

    print(f"\n{'='*60}", flush=True)
    print(f"  {sym} — {date} (float={float_m}M)", flush=True)
    print(f"{'='*60}", flush=True)

    # Run with TW enabled
    print(f"  Running with TW=ON...", flush=True)
    tw_on = run_simulation(sym, date, tw_enabled=True, float_m=float_m)

    # Run with TW disabled
    print(f"  Running with TW=OFF...", flush=True)
    tw_off = run_simulation(sym, date, tw_enabled=False, float_m=float_m)

    # Compare each trade
    comparisons = []

    # Match trades by number
    on_trades = {t["num"]: t for t in tw_on.get("trades", [])}
    off_trades = {t["num"]: t for t in tw_off.get("trades", [])}

    # Get all trade numbers
    all_nums = sorted(set(list(on_trades.keys()) + list(off_trades.keys())))

    for num in all_nums:
        on_t = on_trades.get(num)
        off_t = off_trades.get(num)

        comp = {
            "symbol": sym,
            "date": date,
            "float_m": float_m,
            "gap_pct": stock.get("gap_pct", 0),
            "trade_num": num,
        }

        if on_t:
            comp["tw_entry"] = on_t["entry"]
            comp["tw_exit"] = on_t["exit"]
            comp["tw_time"] = on_t["time"]
            comp["tw_reason"] = on_t["reason"]
            comp["tw_pnl"] = on_t["pnl"]
            comp["tw_r_mult"] = on_t["r_mult"]
            comp["tw_score"] = on_t["score"]
            comp["tw_r"] = on_t["r"]
            comp["is_tw_exit"] = "topping_wicky" in on_t["reason"]

            # Fetch post-exit bars
            if "topping_wicky" in on_t["reason"]:
                post_bars = fetch_post_exit_bars(sym, date, on_t["time"], 30)
                if post_bars:
                    comp["post_tw_hod"] = max(b["high"] for b in post_bars)
                    comp["post_tw_lod"] = min(b["low"] for b in post_bars)
                    hod_bar = next(b for b in post_bars if b["high"] == comp["post_tw_hod"])
                    lod_bar = next(b for b in post_bars if b["low"] == comp["post_tw_lod"])
                    comp["post_tw_hod_time"] = hod_bar["time"]
                    comp["post_tw_lod_time"] = lod_bar["time"]

                    def tdiff(t1, t2):
                        h1, m1 = int(t1.split(":")[0]), int(t1.split(":")[1])
                        h2, m2 = int(t2.split(":")[0]), int(t2.split(":")[1])
                        return (h2 * 60 + m2) - (h1 * 60 + m1)

                    comp["time_to_hod"] = tdiff(on_t["time"], hod_bar["time"])
                    comp["time_to_lod"] = tdiff(on_t["time"], lod_bar["time"])
        else:
            comp["tw_pnl"] = None
            comp["is_tw_exit"] = False

        if off_t:
            comp["no_tw_entry"] = off_t["entry"]
            comp["no_tw_exit"] = off_t["exit"]
            comp["no_tw_time"] = off_t["time"]
            comp["no_tw_reason"] = off_t["reason"]
            comp["no_tw_pnl"] = off_t["pnl"]
            comp["no_tw_r_mult"] = off_t["r_mult"]
        else:
            comp["no_tw_pnl"] = None
            comp["no_tw_reason"] = "no_trade"

        # Delta
        if comp.get("tw_pnl") is not None and comp.get("no_tw_pnl") is not None:
            comp["delta"] = comp["tw_pnl"] - comp["no_tw_pnl"]
            comp["tw_helped"] = comp["delta"] >= 0
        elif comp.get("tw_pnl") is not None and comp.get("no_tw_pnl") is None:
            comp["delta"] = comp["tw_pnl"]  # TW caused a trade that wouldn't exist
            comp["tw_helped"] = comp["tw_pnl"] >= 0
        elif comp.get("tw_pnl") is None and comp.get("no_tw_pnl") is not None:
            comp["delta"] = -comp["no_tw_pnl"]  # TW prevented a trade
            comp["tw_helped"] = comp["no_tw_pnl"] <= 0
        else:
            comp["delta"] = 0
            comp["tw_helped"] = True

        comparisons.append(comp)

        # Print summary
        tw_str = f"${comp.get('tw_pnl', 'N/A'):>+7}" if comp.get("tw_pnl") is not None else "  N/A  "
        no_tw_str = f"${comp.get('no_tw_pnl', 'N/A'):>+7}" if comp.get("no_tw_pnl") is not None else "  N/A  "
        reason_on = comp.get("tw_reason", "N/A")
        reason_off = comp.get("no_tw_reason", "N/A")
        print(f"  Trade {num}: TW_ON={tw_str} ({reason_on})  TW_OFF={no_tw_str} ({reason_off})  delta={comp.get('delta', 0):+}", flush=True)

    # Handle case where TW=off produces more trades
    if len(off_trades) > len(on_trades):
        for num in sorted(off_trades.keys()):
            if num not in on_trades:
                off_t = off_trades[num]
                comp = {
                    "symbol": sym, "date": date, "float_m": float_m,
                    "gap_pct": stock.get("gap_pct", 0), "trade_num": num,
                    "tw_pnl": None, "is_tw_exit": False,
                    "no_tw_entry": off_t["entry"], "no_tw_exit": off_t["exit"],
                    "no_tw_time": off_t["time"], "no_tw_reason": off_t["reason"],
                    "no_tw_pnl": off_t["pnl"], "no_tw_r_mult": off_t["r_mult"],
                    "delta": 0, "tw_helped": True,
                }
                # Only add if not already in comparisons
                if not any(c["trade_num"] == num for c in comparisons):
                    comparisons.append(comp)

    return comparisons


def generate_report(all_comparisons):
    lines = []
    lines.append("# Topping Wicky Exit — Complete Impact Analysis")
    lines.append(f"## Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("Every trade run twice: TW enabled vs TW disabled. Shows what TW saved or cost.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Per-stock detail
    by_stock = {}
    for c in all_comparisons:
        key = f"{c['symbol']}_{c['date']}"
        by_stock.setdefault(key, []).append(c)

    for key, comps in by_stock.items():
        sym = comps[0]["symbol"]
        date = comps[0]["date"]
        lines.append(f"### {sym} — {date}")
        lines.append("")
        lines.append("| Trade | TW Exit | TW P&L | No-TW Exit | No-TW P&L | Delta | TW Helped? |")
        lines.append("|-------|---------|--------|------------|-----------|-------|------------|")
        for c in comps:
            tw_pnl = f"${c['tw_pnl']:+,}" if c.get("tw_pnl") is not None else "N/A"
            no_pnl = f"${c['no_tw_pnl']:+,}" if c.get("no_tw_pnl") is not None else "N/A"
            tw_r = c.get("tw_reason", "N/A")
            no_r = c.get("no_tw_reason", "N/A")
            helped = "YES" if c.get("tw_helped") else "**NO**"
            delta = f"${c.get('delta', 0):+,}"
            lines.append(f"| #{c['trade_num']} | {tw_r} {tw_pnl} | {tw_pnl} | {no_r} {no_pnl} | {no_pnl} | {delta} | {helped} |")

        # Post-exit data for TW exits
        for c in comps:
            if c.get("is_tw_exit") and c.get("post_tw_hod"):
                lines.append(f"\nPost-TW exit: HOD=${c['post_tw_hod']:.2f} (+{c.get('time_to_hod', 0)}min), LOD=${c['post_tw_lod']:.2f} (+{c.get('time_to_lod', 0)}min)")

        lines.append("")
        lines.append("---")
        lines.append("")

    # Summary Table 1: Every TW exit
    tw_exits = [c for c in all_comparisons if c.get("is_tw_exit")]
    lines.append("## Summary Table 1: TW Impact — Every TW Exit")
    lines.append("")
    lines.append("| Symbol | Date | TW P&L | No-TW P&L | No-TW Exit | Delta | TW Helped? |")
    lines.append("|--------|------|--------|-----------|------------|-------|------------|")
    for c in tw_exits:
        tw_pnl = f"${c['tw_pnl']:+,}" if c.get("tw_pnl") is not None else "N/A"
        no_pnl = f"${c['no_tw_pnl']:+,}" if c.get("no_tw_pnl") is not None else "N/A"
        no_r = c.get("no_tw_reason", "N/A")
        helped = "YES" if c.get("tw_helped") else "**NO**"
        delta = f"${c.get('delta', 0):+,}"
        lines.append(f"| {c['symbol']} | {c['date'][5:]} | {tw_pnl} | {no_pnl} | {no_r} | {delta} | {helped} |")
    lines.append("")

    # Summary Table 3: Scorecard
    helped = [c for c in tw_exits if c.get("tw_helped")]
    hurt = [c for c in tw_exits if not c.get("tw_helped")]
    total_saved = sum(c.get("delta", 0) for c in helped)
    total_cost = sum(c.get("delta", 0) for c in hurt)

    lines.append("## Summary Table 3: TW Scorecard")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total TW exits | {len(tw_exits)} |")
    lines.append(f"| TW helped (saved money) | {len(helped)} |")
    lines.append(f"| TW hurt (left money on table) | {len(hurt)} |")
    lines.append(f"| Total $ saved by TW | ${total_saved:+,} |")
    lines.append(f"| Total $ cost by TW | ${total_cost:+,} |")
    lines.append(f"| **Net TW impact** | **${total_saved + total_cost:+,}** |")
    lines.append("")

    # Also show all non-TW trades that changed between runs
    non_tw_changes = [c for c in all_comparisons if not c.get("is_tw_exit") and c.get("delta", 0) != 0]
    if non_tw_changes:
        lines.append("## Non-TW Trades That Changed Between Runs")
        lines.append("")
        lines.append("| Symbol | Date | Trade | TW-On P&L | TW-Off P&L | Delta | Note |")
        lines.append("|--------|------|-------|-----------|-----------|-------|------|")
        for c in non_tw_changes:
            tw_pnl = f"${c['tw_pnl']:+,}" if c.get("tw_pnl") is not None else "N/A"
            no_pnl = f"${c['no_tw_pnl']:+,}" if c.get("no_tw_pnl") is not None else "N/A"
            lines.append(f"| {c['symbol']} | {c['date'][5:]} | #{c['trade_num']} | {tw_pnl} | {no_pnl} | ${c.get('delta', 0):+,} | TW affected prior trade timing |")
        lines.append("")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("args", nargs="*")
    args = parser.parse_args()

    if args.args and args.args[0].upper() != "ALL" and len(args.args) >= 2:
        sym = args.args[0].upper()
        date = args.args[1]
        stocks = [s for s in TW_STOCKS if s["symbol"] == sym and s["date"] == date]
        if not stocks:
            stocks = [{"symbol": sym, "date": date, "float_m": 0, "gap_pct": 0}]
    else:
        stocks = TW_STOCKS

    print(f"Analyzing {len(stocks)} stocks (TW on vs TW off)...", flush=True)

    all_comparisons = []
    for stock in stocks:
        comps = analyze_stock(stock)
        all_comparisons.extend(comps)

    report = generate_report(all_comparisons)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "TW_EXIT_ANALYSIS_REPORT.md")
    with open(path, "w") as f:
        f.write(report)
    print(f"\nReport written to {path}", flush=True)


if __name__ == "__main__":
    main()
