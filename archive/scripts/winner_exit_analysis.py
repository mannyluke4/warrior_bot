#!/usr/bin/env python3
"""
winner_exit_analysis.py — Analyze post-exit price action on winning trades.

For each winner, fetches 1-minute bars after the exit and computes:
- Post-exit HOD (how much further did it run?)
- Time to HOD
- Post-exit LOD (how fast did it reverse?)
- Money left on the table
- Re-entry opportunities

Usage:
    python winner_exit_analysis.py ALL           # Run all winners
    python winner_exit_analysis.py GITS 2026-03-10  # Single stock
"""

import os
import sys
from datetime import datetime, timedelta, timezone
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

# All winners from 49-day + weekly backtests (all fixes ON, new config)
WINNERS = [
    # 49-day winners
    {"symbol": "VERO", "date": "2026-01-16", "entry": 3.58, "exit": 4.68, "exit_time": "07:14", "r": 0.12, "r_mult": 9.2, "pnl": 9166, "exit_reason": "topping_wicky", "score": 11.1},
    {"symbol": "ROLR", "date": "2026-01-14", "entry": 9.33, "exit": 12.90, "exit_time": "08:26", "r": 1.10, "r_mult": 3.2, "pnl": 3242, "exit_reason": "topping_wicky", "score": 11.0},
    {"symbol": "SNSE", "date": "2026-01-02", "entry": 3.20, "exit": 3.37, "exit_time": "09:45", "r": 0.08, "r_mult": 2.1, "pnl": 1680, "exit_reason": "bearish_engulfing", "score": 10.0},
    {"symbol": "SXTC", "date": "2026-01-08", "entry": 2.75, "exit": 3.01, "exit_time": "08:12", "r": 0.10, "r_mult": 2.6, "pnl": 1058, "exit_reason": "bearish_engulfing", "score": 12.0},
    {"symbol": "SXTC", "date": "2026-01-08", "entry": 3.14, "exit": 3.27, "exit_time": "08:31", "r": 0.13, "r_mult": 1.0, "pnl": 628, "exit_reason": "bearish_engulfing", "score": 12.0},
    {"symbol": "BDSX", "date": "2026-01-12", "entry": 3.52, "exit": 3.70, "exit_time": "09:35", "r": 0.08, "r_mult": 2.2, "pnl": 1760, "exit_reason": "bearish_engulfing", "score": 10.0},
    {"symbol": "AGPU", "date": "2026-01-15", "entry": 5.10, "exit": 5.30, "exit_time": "09:50", "r": 0.12, "r_mult": 1.7, "pnl": 1360, "exit_reason": "bearish_engulfing", "score": 10.0},
    {"symbol": "PMN",  "date": "2026-01-30", "entry": 4.82, "exit": 4.88, "exit_time": "10:05", "r": 0.14, "r_mult": 0.4, "pnl": 320, "exit_reason": "topping_wicky", "score": 8.0},
    {"symbol": "WHLR", "date": "2026-02-06", "entry": 3.10, "exit": 3.15, "exit_time": "09:40", "r": 0.10, "r_mult": 0.5, "pnl": 400, "exit_reason": "topping_wicky", "score": 9.0},
    # Weekly winners (all fixes ON)
    {"symbol": "GITS", "date": "2026-03-10", "entry": 2.54, "exit": 2.76, "exit_time": "10:33", "r": 0.08, "r_mult": 2.7, "pnl": 2748, "exit_reason": "bearish_engulfing", "score": 10.0},
    {"symbol": "TLYS", "date": "2026-03-12", "entry": 2.72, "exit": 2.73, "exit_time": "07:06", "r": 0.13, "r_mult": 0.1, "pnl": 77, "exit_reason": "topping_wicky", "score": 12.0},
    {"symbol": "OKLL", "date": "2026-03-17", "entry": 10.05, "exit": 10.24, "exit_time": "08:13", "r": 0.16, "r_mult": 1.2, "pnl": 945, "exit_reason": "bearish_engulfing", "score": 11.0},
    {"symbol": "LUNL", "date": "2026-03-17", "entry": 13.00, "exit": 13.13, "exit_time": "09:59", "r": 0.28, "r_mult": 0.5, "pnl": 464, "exit_reason": "topping_wicky", "score": 12.5},
    {"symbol": "BMNZ", "date": "2026-03-18", "entry": 16.99, "exit": 17.03, "exit_time": "08:48", "r": 0.19, "r_mult": 0.2, "pnl": 118, "exit_reason": "topping_wicky", "score": 10.1},
]


def fetch_bars_after(symbol: str, date_str: str, exit_time_str: str, minutes_after: int = 60):
    """Fetch 1-minute bars from exit_time to exit_time + minutes_after."""
    date = datetime.strptime(date_str, "%Y-%m-%d")
    eh, em = int(exit_time_str.split(":")[0]), int(exit_time_str.split(":")[1])

    start = ET.localize(datetime(date.year, date.month, date.day, eh, em, 0))
    end = start + timedelta(minutes=minutes_after)
    # Cap at 16:00 ET (market close)
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

    result = []
    for b in bars:
        ts = b.timestamp
        if isinstance(ts, datetime) and ts.tzinfo:
            ts_et = ts.astimezone(ET)
        else:
            ts_et = ts
        result.append({
            "time": ts_et.strftime("%H:%M"),
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": int(b.volume),
        })
    return result


def analyze_winner(w: dict) -> dict:
    """Analyze post-exit price action for a winning trade."""
    print(f"  Analyzing {w['symbol']} {w['date']} (exit {w['exit_time']} @ ${w['exit']:.2f})...", flush=True)

    bars = fetch_bars_after(w["symbol"], w["date"], w["exit_time"], minutes_after=60)
    if not bars:
        print(f"    WARNING: No post-exit bars for {w['symbol']}", flush=True)
        return {**w, "post_bars": [], "error": "no_data"}

    exit_price = w["exit"]
    entry_price = w["entry"]
    r = w["r"]

    # Post-exit HOD / LOD
    post_hod = exit_price
    post_hod_time = w["exit_time"]
    post_lod = exit_price
    post_lod_time = w["exit_time"]

    for b in bars:
        if b["high"] > post_hod:
            post_hod = b["high"]
            post_hod_time = b["time"]
        if b["low"] < post_lod:
            post_lod = b["low"]
            post_lod_time = b["time"]

    # Time calculations
    def time_diff_min(t1: str, t2: str) -> float:
        h1, m1 = int(t1.split(":")[0]), int(t1.split(":")[1])
        h2, m2 = int(t2.split(":")[0]), int(t2.split(":")[1])
        return (h2 * 60 + m2) - (h1 * 60 + m1)

    time_to_hod = time_diff_min(w["exit_time"], post_hod_time)
    time_to_lod = time_diff_min(w["exit_time"], post_lod_time)

    # Max capturable P&L (if exited at post-exit HOD)
    shares = abs(w["pnl"] / (exit_price - entry_price)) if exit_price != entry_price else 0
    max_pnl = shares * (post_hod - entry_price) if shares > 0 else 0
    money_left = max_pnl - w["pnl"]
    money_left_pct = (money_left / w["pnl"] * 100) if w["pnl"] > 0 else 0

    # Post-exit HOD in R multiples above exit
    post_hod_r = (post_hod - exit_price) / r if r > 0 else 0

    # Prices at intervals
    price_5m = bars[min(4, len(bars) - 1)]["close"] if len(bars) > 0 else exit_price
    price_10m = bars[min(9, len(bars) - 1)]["close"] if len(bars) > 0 else exit_price
    price_30m = bars[min(29, len(bars) - 1)]["close"] if len(bars) > 0 else exit_price
    session_close = bars[-1]["close"] if bars else exit_price

    # Re-entry opportunity: did stock pull back then rally above exit?
    pullback_low = exit_price
    post_pullback_high = exit_price
    found_pullback = False
    for b in bars:
        if b["low"] < pullback_low:
            pullback_low = b["low"]
            found_pullback = True
        if found_pullback and b["high"] > post_pullback_high:
            post_pullback_high = b["high"]
    reentry_viable = found_pullback and post_pullback_high > exit_price * 1.005  # >0.5% above exit

    return {
        **w,
        "post_bars": bars[:30],  # First 30 bars for the report
        "post_hod": post_hod,
        "post_hod_time": post_hod_time,
        "post_hod_pct": round((post_hod - exit_price) / exit_price * 100, 2),
        "post_hod_r": round(post_hod_r, 2),
        "time_to_hod_min": time_to_hod,
        "post_lod": post_lod,
        "post_lod_time": post_lod_time,
        "post_lod_pct": round((post_lod - exit_price) / exit_price * 100, 2),
        "time_to_lod_min": time_to_lod,
        "price_5m": price_5m,
        "price_10m": price_10m,
        "price_30m": price_30m,
        "session_close": session_close,
        "max_pnl": round(max_pnl, 0),
        "money_left": round(money_left, 0),
        "money_left_pct": round(money_left_pct, 1),
        "max_capturable_r": round((post_hod - entry_price) / r, 1) if r > 0 else 0,
        "pullback_low": pullback_low,
        "post_pullback_high": post_pullback_high,
        "reentry_viable": reentry_viable,
    }


def generate_report(results: list) -> str:
    lines = []
    lines.append("# Winner Exit Analysis Report")
    lines.append(f"## Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("For every winning trade: how much further did the stock run after our exit?")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Per-trade detail
    for r in results:
        if "error" in r:
            lines.append(f"### {r['symbol']} — {r['date']} — NO DATA")
            lines.append("")
            continue

        pnl_str = f"+${r['pnl']:,}"
        lines.append(f"### {r['symbol']} — {r['date']} — Exit at {r['exit_time']} — {pnl_str} (+{r['r_mult']}R)")
        lines.append("")
        lines.append(f"**Entry:** ${r['entry']:.2f} | **Exit:** ${r['exit']:.2f} ({r['exit_reason']}) | **R:** ${r['r']:.2f} | **Score:** {r['score']}")
        lines.append("")

        lines.append("**Post-exit price action (1-min bars):**")
        lines.append("| Min | Time | O | H | L | C | Vol |")
        lines.append("|-----|------|---|---|---|---|-----|")
        for i, b in enumerate(r.get("post_bars", [])[:15]):
            lines.append(f"| +{i+1} | {b['time']} | {b['open']:.4f} | {b['high']:.4f} | {b['low']:.4f} | {b['close']:.4f} | {b['volume']:>7,} |")
        if len(r.get("post_bars", [])) > 15:
            lines.append(f"| ... | ({len(r['post_bars'])} total bars) | | | | | |")
        lines.append("")

        lines.append("**Post-exit metrics:**")
        lines.append(f"- Post-exit HOD: **${r['post_hod']:.4f}** at {r['post_hod_time']} ({r['post_hod_pct']:+.2f}%, +{r['post_hod_r']}R above exit) — {r['time_to_hod_min']:.0f} min after exit")
        lines.append(f"- Post-exit LOD: ${r['post_lod']:.4f} at {r['post_lod_time']} ({r['post_lod_pct']:+.2f}%) — {r['time_to_lod_min']:.0f} min after exit")
        lines.append(f"- Price 5m after: ${r['price_5m']:.4f} | 10m: ${r['price_10m']:.4f} | 30m: ${r['price_30m']:.4f}")
        lines.append(f"- Session close: ${r['session_close']:.4f}")
        lines.append(f"- **Max capturable P&L:** ${r['max_pnl']:,.0f} ({r['max_capturable_r']}R) vs actual ${r['pnl']:,} ({r['r_mult']}R)")
        lines.append(f"- **Money left on table:** ${r['money_left']:,.0f} ({r['money_left_pct']:.1f}% of actual P&L)")
        lines.append(f"- Re-entry opportunity: {'YES' if r['reentry_viable'] else 'no'} (pullback to ${r['pullback_low']:.4f}, rally to ${r['post_pullback_high']:.4f})")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Summary tables
    lines.append("## Table 1: Money Left on the Table")
    lines.append("")
    lines.append("| Symbol | Date | Exit R | Exit P&L | Post-Exit HOD R | Max P&L | Left on Table | Left % |")
    lines.append("|--------|------|--------|----------|----------------|---------|---------------|--------|")
    for r in results:
        if "error" in r:
            continue
        lines.append(
            f"| {r['symbol']} | {r['date'][5:]} | +{r['r_mult']}R | +${r['pnl']:,} "
            f"| +{r['max_capturable_r']}R | +${r['max_pnl']:,.0f} "
            f"| ${r['money_left']:,.0f} | {r['money_left_pct']:.1f}% |"
        )
    lines.append("")

    # Total money left
    total_actual = sum(r["pnl"] for r in results if "error" not in r)
    total_max = sum(r["max_pnl"] for r in results if "error" not in r)
    total_left = sum(r["money_left"] for r in results if "error" not in r)
    lines.append(f"**Total actual P&L: +${total_actual:,}** | **Total max capturable: +${total_max:,.0f}** | **Total left on table: ${total_left:,.0f}**")
    lines.append("")

    # Table 2: Exit type comparison
    be_results = [r for r in results if "error" not in r and "bearish_engulfing" in r["exit_reason"]]
    tw_results = [r for r in results if "error" not in r and "topping_wicky" in r["exit_reason"]]

    lines.append("## Table 2: Exit Type Comparison")
    lines.append("")
    lines.append("| Exit Type | Count | Avg R Captured | Avg Post-Exit HOD R | Avg % Left on Table |")
    lines.append("|-----------|-------|---------------|---------------------|---------------------|")
    if be_results:
        avg_r = sum(r["r_mult"] for r in be_results) / len(be_results)
        avg_hod_r = sum(r["post_hod_r"] for r in be_results) / len(be_results)
        avg_left = sum(r["money_left_pct"] for r in be_results) / len(be_results)
        lines.append(f"| Bearish Engulfing | {len(be_results)} | +{avg_r:.1f}R | +{avg_hod_r:.1f}R | {avg_left:.1f}% |")
    if tw_results:
        avg_r = sum(r["r_mult"] for r in tw_results) / len(tw_results)
        avg_hod_r = sum(r["post_hod_r"] for r in tw_results) / len(tw_results)
        avg_left = sum(r["money_left_pct"] for r in tw_results) / len(tw_results)
        lines.append(f"| Topping Wicky | {len(tw_results)} | +{avg_r:.1f}R | +{avg_hod_r:.1f}R | {avg_left:.1f}% |")
    lines.append("")

    # Table 3: Tiny winners
    tiny = [r for r in results if "error" not in r and r["r_mult"] <= 0.5]
    if tiny:
        lines.append("## Table 3: Tiny Winners Deep Dive (<= 0.5R)")
        lines.append("")
        lines.append("| Symbol | Date | Exit R | Post-Exit HOD | Time to HOD | Price 30m After | Did Stock Move? |")
        lines.append("|--------|------|--------|---------------|-------------|-----------------|-----------------|")
        for r in tiny:
            moved = "YES" if r["post_hod_pct"] > 2.0 else "marginally" if r["post_hod_pct"] > 0.5 else "no"
            lines.append(
                f"| {r['symbol']} | {r['date'][5:]} | +{r['r_mult']}R "
                f"| ${r['post_hod']:.2f} (+{r['post_hod_pct']:.1f}%) "
                f"| {r['time_to_hod_min']:.0f} min | ${r['price_30m']:.2f} | {moved} |"
            )
        lines.append("")

    # Table 4: Re-entry opportunities
    lines.append("## Table 4: Re-Entry Opportunities")
    lines.append("")
    lines.append("| Symbol | Date | Exit Time | Exit Price | Pullback Low | Rally High | Re-Entry Viable? |")
    lines.append("|--------|------|-----------|-----------|-------------|-----------|-----------------|")
    for r in results:
        if "error" in r:
            continue
        lines.append(
            f"| {r['symbol']} | {r['date'][5:]} | {r['exit_time']} | ${r['exit']:.2f} "
            f"| ${r['pullback_low']:.2f} | ${r['post_pullback_high']:.2f} "
            f"| {'**YES**' if r['reentry_viable'] else 'no'} |"
        )
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
        winners = [w for w in WINNERS if w["symbol"] == sym and w["date"] == date]
    else:
        winners = WINNERS

    print(f"Analyzing {len(winners)} winning trades...", flush=True)

    results = []
    for w in winners:
        r = analyze_winner(w)
        results.append(r)

    report = generate_report(results)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "WINNER_EXIT_ANALYSIS_REPORT.md")
    with open(path, "w") as f:
        f.write(report)
    print(f"\nReport written to {path}", flush=True)


if __name__ == "__main__":
    main()
