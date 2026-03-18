#!/usr/bin/env python3
"""
volume_pressure_analysis.py — Analyze buy/sell volume pressure around ARM signals.

Standalone diagnostic script. Does NOT modify any strategy code.
Runs simulate.py logic to replay ticks, hooks into the detector to capture
1-minute bar history at each ARM event, then computes buy/sell volume ratios.

Usage:
    python volume_pressure_analysis.py HIMZ 2026-03-09 07:00 12:00 --ticks
    python volume_pressure_analysis.py ALL   # runs all 10 stock/date pairs
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytz
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockTradesRequest
from alpaca.data.timeframe import TimeFrame

load_dotenv()

ET = pytz.timezone("US/Eastern")
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
hist_client = StockHistoricalDataClient(API_KEY, API_SECRET)

# All stock/date pairs from the weekly report
ALL_PAIRS = [
    ("HIMZ", "2026-03-09"),
    ("INKT", "2026-03-10"),
    ("GITS", "2026-03-10"),
    ("TLYS", "2026-03-12"),
    ("FLYT", "2026-03-12"),
    ("OKLL", "2026-03-17"),
    ("LUNL", "2026-03-17"),
    ("BIAF", "2026-03-17"),
    ("TRT",  "2026-03-17"),
    ("BMNZ", "2026-03-18"),
]

# Known ARM times and trade results from the weekly report (new config)
KNOWN_TRADES = [
    {"symbol": "HIMZ", "date": "2026-03-09", "arm_time": "08:30", "entry_time": "08:31", "result": "LOSS", "pnl": -675, "entry": 2.36, "stop": 2.21, "r": 0.15, "score": 12.0, "exit_reason": "bearish_engulfing"},
    {"symbol": "HIMZ", "date": "2026-03-09", "arm_time": "08:36", "entry_time": "08:37", "result": "LOSS", "pnl": -399, "entry": 2.37, "stop": 2.27, "r": 0.10, "score": 12.0, "exit_reason": "bearish_engulfing"},
    {"symbol": "INKT", "date": "2026-03-10", "arm_time": "07:05", "entry_time": "07:06", "result": "LOSS", "pnl": -666, "entry": 20.02, "stop": 18.19, "r": 1.83, "score": 12.5, "exit_reason": "bearish_engulfing"},
    {"symbol": "GITS", "date": "2026-03-10", "arm_time": "10:13", "entry_time": "10:17", "result": "WIN", "pnl": 2748, "entry": 2.54, "stop": 2.46, "r": 0.08, "score": 10.0, "exit_reason": "bearish_engulfing"},
    {"symbol": "TLYS", "date": "2026-03-12", "arm_time": "07:02", "entry_time": "07:03", "result": "WIN", "pnl": 77, "entry": 2.72, "stop": 2.59, "r": 0.13, "score": 12.0, "exit_reason": "topping_wicky"},
    {"symbol": "FLYT", "date": "2026-03-12", "arm_time": "08:27", "entry_time": "08:28", "result": "LOSS", "pnl": -696, "entry": 11.49, "stop": 11.29, "r": 0.20, "score": 12.5, "exit_reason": "max_loss_hit"},
    {"symbol": "OKLL", "date": "2026-03-17", "arm_time": "08:10", "entry_time": "08:11", "result": "WIN", "pnl": 945, "entry": 10.05, "stop": 9.89, "r": 0.16, "score": 11.0, "exit_reason": "bearish_engulfing"},
    {"symbol": "LUNL", "date": "2026-03-17", "arm_time": "09:56", "entry_time": "09:59", "result": "LOSS", "pnl": -821, "entry": 13.00, "stop": 12.72, "r": 0.28, "score": 12.5, "exit_reason": "max_loss_hit"},
    {"symbol": "BIAF", "date": "2026-03-17", "arm_time": "09:49", "entry_time": "09:50", "result": "LOSS", "pnl": -85, "entry": 2.85, "stop": 2.61, "r": 0.24, "score": 12.0, "exit_reason": "topping_wicky"},
    {"symbol": "TRT",  "date": "2026-03-17", "arm_time": "09:37", "entry_time": "09:43", "result": "LOSS", "pnl": -784, "entry": 6.26, "stop": 6.15, "r": 0.11, "score": 5.5, "exit_reason": "max_loss_hit"},
    {"symbol": "TRT",  "date": "2026-03-17", "arm_time": "09:48", "entry_time": "09:49", "result": "LOSS", "pnl": -916, "entry": 6.28, "stop": 6.15, "r": 0.13, "score": 5.5, "exit_reason": "max_loss_hit"},
    {"symbol": "BMNZ", "date": "2026-03-18", "arm_time": "08:44", "entry_time": "08:45", "result": "WIN", "pnl": 118, "entry": 16.99, "stop": 16.80, "r": 0.19, "score": 10.1, "exit_reason": "topping_wicky"},
    {"symbol": "BMNZ", "date": "2026-03-18", "arm_time": "10:48", "entry_time": "10:49", "result": "LOSS", "pnl": -257, "entry": 17.51, "stop": 17.41, "r": 0.10, "score": 8.8, "exit_reason": "max_loss_hit"},
]


def fetch_1m_bars(symbol: str, date_str: str, start_et: str = "04:00", end_et: str = "12:00"):
    """Fetch 1-minute bars for a symbol on a given date."""
    date = datetime.strptime(date_str, "%Y-%m-%d")
    sh, sm = int(start_et.split(":")[0]), int(start_et.split(":")[1])
    eh, em = int(end_et.split(":")[0]), int(end_et.split(":")[1])

    start = ET.localize(datetime(date.year, date.month, date.day, sh, sm, 0))
    end = ET.localize(datetime(date.year, date.month, date.day, eh, em, 0))

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
            "green": float(b.close) >= float(b.open),
        })
    return result


def compute_ratios(bars, lookback):
    """Compute buy/sell volume ratios for the last N bars."""
    if len(bars) < lookback:
        lookback = len(bars)
    if lookback == 0:
        return {"buy_vol": 0, "sell_vol": 0, "buy_ratio": 0, "green_pct": 0, "price_trend": 0, "weighted_buy_ratio": 0}

    window = bars[-lookback:]
    buy_vol = sum(b["volume"] for b in window if b["green"])
    sell_vol = sum(b["volume"] for b in window if not b["green"])
    total_vol = buy_vol + sell_vol

    green_count = sum(1 for b in window if b["green"])

    # Weighted buy ratio (more recent bars weighted higher)
    weighted_buy = 0
    weighted_total = 0
    for i, b in enumerate(window):
        weight = (i + 1) / lookback
        weighted_total += b["volume"] * weight
        if b["green"]:
            weighted_buy += b["volume"] * weight

    # Price trend
    price_trend = 0
    if window[0]["close"] > 0:
        price_trend = (window[-1]["close"] - window[0]["close"]) / window[0]["close"] * 100

    return {
        "buy_vol": buy_vol,
        "sell_vol": sell_vol,
        "buy_ratio": round(buy_vol / total_vol * 100, 1) if total_vol > 0 else 0,
        "green_pct": round(green_count / lookback * 100, 1),
        "price_trend": round(price_trend, 2),
        "weighted_buy_ratio": round(weighted_buy / weighted_total * 100, 1) if weighted_total > 0 else 0,
    }


def analyze_trade(trade: dict, all_bars: list) -> dict:
    """Analyze volume pressure around an ARM signal."""
    arm_time = trade["arm_time"]
    entry_time = trade["entry_time"]

    # Find the bar index closest to ARM time
    arm_idx = None
    for i, b in enumerate(all_bars):
        if b["time"] == arm_time:
            arm_idx = i
            break
        if b["time"] > arm_time:
            arm_idx = max(0, i - 1)
            break
    if arm_idx is None:
        arm_idx = len(all_bars) - 1

    # Find entry bar index
    entry_idx = None
    for i, b in enumerate(all_bars):
        if b["time"] == entry_time:
            entry_idx = i
            break
        if b["time"] > entry_time:
            entry_idx = i
            break
    if entry_idx is None:
        entry_idx = min(arm_idx + 1, len(all_bars) - 1)

    # Pre-ARM bars (last 10)
    pre_start = max(0, arm_idx - 9)
    pre_bars = all_bars[pre_start:arm_idx + 1]

    # Post-entry bars (first 5)
    post_end = min(len(all_bars), entry_idx + 6)
    post_bars = all_bars[entry_idx:post_end]

    # Compute ratios at ARM
    ratios_3 = compute_ratios(all_bars[:arm_idx + 1], 3)
    ratios_5 = compute_ratios(all_bars[:arm_idx + 1], 5)
    ratios_10 = compute_ratios(all_bars[:arm_idx + 1], 10)

    # Post-entry ratios
    post_ratios = compute_ratios(post_bars, 5)

    return {
        "trade": trade,
        "pre_bars": pre_bars,
        "post_bars": post_bars,
        "ratios_3": ratios_3,
        "ratios_5": ratios_5,
        "ratios_10": ratios_10,
        "post_ratios": post_ratios,
    }


def format_bar_table(bars, label_start=None):
    """Format bars as a markdown table."""
    lines = []
    lines.append("| Bar # | Time | O | H | L | C | Vol | Green? |")
    lines.append("|-------|------|---|---|---|---|-----|--------|")
    for i, b in enumerate(bars):
        if label_start is not None:
            bar_num = label_start + i
            label = f"+{bar_num}" if bar_num > 0 else str(bar_num)
        else:
            bar_num = i - len(bars)
            label = str(bar_num + 1)
        g = "YES" if b["green"] else "no"
        lines.append(f"| {label:>5} | {b['time']} | {b['open']:.4f} | {b['high']:.4f} | {b['low']:.4f} | {b['close']:.4f} | {b['volume']:>7,} | {g} |")
    return "\n".join(lines)


def format_ratios_table(r3, r5, r10):
    """Format buy/sell ratio table."""
    lines = []
    lines.append("| Window | Buy Vol | Sell Vol | Buy Ratio | Wtd Buy Ratio | Green Bar % | Price Trend |")
    lines.append("|--------|---------|----------|-----------|---------------|-------------|-------------|")
    for label, r in [("3-bar", r3), ("5-bar", r5), ("10-bar", r10)]:
        lines.append(f"| {label} | {r['buy_vol']:>9,} | {r['sell_vol']:>10,} | {r['buy_ratio']:>8.1f}% | {r['weighted_buy_ratio']:>12.1f}% | {r['green_pct']:>10.1f}% | {r['price_trend']:>+10.2f}% |")
    return "\n".join(lines)


def generate_report(results: list) -> str:
    """Generate the full markdown report."""
    lines = []
    lines.append("# Volume Pressure Analysis Report")
    lines.append(f"## Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("Analysis of buy/sell volume pressure in the 1-minute bars leading into each ARM signal.")
    lines.append("**Green bar** = close >= open (buying pressure). **Red bar** = close < open (selling pressure).")
    lines.append("")
    lines.append("---")
    lines.append("")

    for r in results:
        t = r["trade"]
        result_emoji = "WIN" if t["result"] == "WIN" else "LOSS"
        pnl_str = f"+${t['pnl']:,}" if t["pnl"] > 0 else f"-${abs(t['pnl']):,}"

        lines.append(f"### {t['symbol']} — {t['date']} — ARM at {t['arm_time']} — {result_emoji} ({pnl_str})")
        lines.append("")
        lines.append(f"**Setup:** Entry=${t['entry']:.2f} Stop=${t['stop']:.2f} R=${t['r']:.2f} Score={t['score']} Exit={t['exit_reason']}")
        lines.append("")
        lines.append("**Last 10 bars before ARM:**")
        lines.append(format_bar_table(r["pre_bars"]))
        lines.append("")
        lines.append("**Buy/Sell Ratios at ARM:**")
        lines.append(format_ratios_table(r["ratios_3"], r["ratios_5"], r["ratios_10"]))
        lines.append("")
        if r["post_bars"]:
            lines.append("**First 5 bars AFTER entry:**")
            lines.append(format_bar_table(r["post_bars"], label_start=1))
            lines.append("")
            pr = r["post_ratios"]
            lines.append(f"**Post-entry buy ratio (5-bar):** {pr['buy_ratio']:.1f}% (weighted: {pr['weighted_buy_ratio']:.1f}%)")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Summary table
    lines.append("## Summary: Buy Ratio vs Trade Outcome")
    lines.append("")
    lines.append("| Symbol | Date | ARM Time | Result | P&L | 3-bar Buy% | 5-bar Buy% | 10-bar Buy% | Post-Entry 5-bar Buy% |")
    lines.append("|--------|------|----------|--------|-----|------------|------------|-------------|----------------------|")
    for r in results:
        t = r["trade"]
        pnl_str = f"+${t['pnl']:,}" if t["pnl"] > 0 else f"-${abs(t['pnl']):,}"
        lines.append(
            f"| {t['symbol']:<6} | {t['date'][5:]} | {t['arm_time']} | {t['result']:<4} | {pnl_str:>8} "
            f"| {r['ratios_3']['buy_ratio']:>9.1f}% | {r['ratios_5']['buy_ratio']:>9.1f}% "
            f"| {r['ratios_10']['buy_ratio']:>10.1f}% | {r['post_ratios']['buy_ratio']:>20.1f}% |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")

    # Analysis
    winners = [r for r in results if r["trade"]["result"] == "WIN"]
    losers = [r for r in results if r["trade"]["result"] == "LOSS"]

    if winners:
        avg_win_3 = sum(r["ratios_3"]["buy_ratio"] for r in winners) / len(winners)
        avg_win_5 = sum(r["ratios_5"]["buy_ratio"] for r in winners) / len(winners)
        avg_win_10 = sum(r["ratios_10"]["buy_ratio"] for r in winners) / len(winners)
    else:
        avg_win_3 = avg_win_5 = avg_win_10 = 0

    if losers:
        avg_lose_3 = sum(r["ratios_3"]["buy_ratio"] for r in losers) / len(losers)
        avg_lose_5 = sum(r["ratios_5"]["buy_ratio"] for r in losers) / len(losers)
        avg_lose_10 = sum(r["ratios_10"]["buy_ratio"] for r in losers) / len(losers)
    else:
        avg_lose_3 = avg_lose_5 = avg_lose_10 = 0

    lines.append("## Statistical Summary")
    lines.append("")
    lines.append("| Metric | Winners | Losers | Delta |")
    lines.append("|--------|---------|--------|-------|")
    lines.append(f"| Avg 3-bar Buy% | {avg_win_3:.1f}% | {avg_lose_3:.1f}% | {avg_win_3 - avg_lose_3:+.1f}% |")
    lines.append(f"| Avg 5-bar Buy% | {avg_win_5:.1f}% | {avg_lose_5:.1f}% | {avg_win_5 - avg_lose_5:+.1f}% |")
    lines.append(f"| Avg 10-bar Buy% | {avg_win_10:.1f}% | {avg_lose_10:.1f}% | {avg_win_10 - avg_lose_10:+.1f}% |")
    lines.append(f"| Count | {len(winners)} | {len(losers)} | |")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Volume pressure analysis around ARM signals")
    parser.add_argument("args", nargs="*", help="SYMBOL DATE or 'ALL'")
    args = parser.parse_args()

    if args.args and args.args[0].upper() == "ALL":
        pairs = ALL_PAIRS
    elif len(args.args) >= 2:
        pairs = [(args.args[0].upper(), args.args[1])]
    else:
        pairs = ALL_PAIRS

    # Deduplicate pairs (some symbols appear on same date)
    unique_pairs = list(dict.fromkeys(pairs))

    # Fetch bars for each unique symbol/date
    bar_cache = {}
    for symbol, date_str in unique_pairs:
        key = f"{symbol}_{date_str}"
        if key not in bar_cache:
            print(f"Fetching 1m bars for {symbol} on {date_str}...", flush=True)
            bar_cache[key] = fetch_1m_bars(symbol, date_str)
            print(f"  Got {len(bar_cache[key])} bars", flush=True)

    # Analyze each trade
    results = []
    for trade in KNOWN_TRADES:
        key = f"{trade['symbol']}_{trade['date']}"
        # Filter to only requested pairs
        if (trade["symbol"], trade["date"]) not in pairs:
            continue
        bars = bar_cache.get(key, [])
        if not bars:
            print(f"  WARNING: No bars for {trade['symbol']} on {trade['date']}", flush=True)
            continue
        print(f"Analyzing {trade['symbol']} ARM at {trade['arm_time']} ({trade['result']})...", flush=True)
        result = analyze_trade(trade, bars)
        results.append(result)

    # Generate report
    report = generate_report(results)

    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VOLUME_PRESSURE_REPORT.md")
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport written to {report_path}", flush=True)


if __name__ == "__main__":
    main()
