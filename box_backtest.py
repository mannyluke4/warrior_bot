#!/usr/bin/env python3
"""
box_backtest.py — Per-candidate YTD backtest for box strategy.

Reads scanner_results_box/*.json, pulls 1m bars from IBKR (cached to disk),
runs box_strategy on each candidate, outputs CSV + markdown report.

Usage:
    python box_backtest.py
    python box_backtest.py --port 4002 --skip-existing
    python box_backtest.py --report-only  # regenerate report from cached results
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time as time_mod
from collections import defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path

import pytz
from ib_insync import IB, Stock

ET = pytz.timezone("US/Eastern")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from box_strategy import BoxStrategyEngine, BoxTradeState


def _bar_time_et(bar) -> time:
    """Get bar time in ET, handling UTC-aware datetimes."""
    dt = bar.date
    if not hasattr(dt, 'time') or not callable(dt.time):
        return time(0, 0)
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        dt_et = dt.astimezone(ET)
        return dt_et.time()
    return dt.time()

# ── Paths ───────────────────────────────────────────────────────────

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
SCANNER_DIR = BASE_DIR / "scanner_results_box"
CACHE_DIR = BASE_DIR / "box_backtest_cache"
RESULTS_DIR = BASE_DIR / "box_backtest_results"


# ── Bar Cache ───────────────────────────────────────────────────────

def _cache_path(date_str: str, symbol: str) -> Path:
    return CACHE_DIR / date_str / f"{symbol}.json"


def _load_cached_bars(date_str: str, symbol: str):
    """Load cached 1m bars from disk. Returns list of dicts or None."""
    p = _cache_path(date_str, symbol)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def _save_cached_bars(date_str: str, symbol: str, bars: list):
    """Save 1m bars to disk cache."""
    p = _cache_path(date_str, symbol)
    p.parent.mkdir(parents=True, exist_ok=True)
    serialized = []
    for b in bars:
        serialized.append({
            "date": str(b.date),
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        })
    with open(p, "w") as f:
        json.dump(serialized, f)


# ── Bar Wrapper (for cached bars) ──────────────────────────────────

class BarProxy:
    """Lightweight bar object from cached dict."""
    __slots__ = ("date", "open", "high", "low", "close", "volume")

    def __init__(self, d: dict):
        self.date = datetime.fromisoformat(d["date"]) if isinstance(d["date"], str) else d["date"]
        self.open = d["open"]
        self.high = d["high"]
        self.low = d["low"]
        self.close = d["close"]
        self.volume = d["volume"]


# ── IBKR Data ──────────────────────────────────────────────────────

def fetch_1m_bars(ib, symbol: str, date_str: str) -> list:
    """Fetch 1m RTH bars from IBKR for a symbol on a date."""
    contract = Stock(symbol, "SMART", "USD")
    end_dt = f"{date_str.replace('-', '')} 16:00:00 US/Eastern"
    try:
        ib.qualifyContracts(contract)
        bars = ib.reqHistoricalData(
            contract, endDateTime=end_dt,
            durationStr="1 D", barSizeSetting="1 min",
            whatToShow="TRADES", useRTH=True, formatDate=2,
        )
        ib.sleep(0.5)
        return bars or []
    except Exception as e:
        print(f"    IBKR error {symbol} {date_str}: {e}", flush=True)
        return []


# ── Run Strategy on One Candidate ──────────────────────────────────

def run_candidate(candidate: dict, bars_1m: list, exit_variant: str = "baseline") -> dict:
    """Run box strategy on a candidate. Returns result dict."""
    symbol = candidate["symbol"]
    date_str = candidate.get("_date", "")

    # Filter bars to box window (10:00 - 15:45 ET)
    box_bars = []
    for b in bars_1m:
        bt = _bar_time_et(b)
        if time(10, 0) <= bt <= time(15, 45):
            box_bars.append(b)

    result = {
        "date": date_str,
        "symbol": symbol,
        "box_score": candidate.get("box_score", 0),
        "range_high_5d": candidate.get("range_high_5d", 0),
        "range_low_5d": candidate.get("range_low_5d", 0),
        "range_pct": candidate.get("range_pct", 0),
        "range_position_pct": candidate.get("range_position_pct", 0),
        "high_tests": candidate.get("high_tests", 0),
        "low_tests": candidate.get("low_tests", 0),
        "adr_util_today": candidate.get("adr_util_today", 0),
        "vwap_dist_pct": candidate.get("vwap_dist_pct", 0),
        "sma_slope_pct": candidate.get("sma_slope_pct"),
        "avg_daily_vol_5d": candidate.get("avg_daily_vol_5d", 0),
        "price": candidate.get("price", 0),
        "num_trades": 0,
        "total_pnl": 0.0,
        "best_trade_pnl": 0.0,
        "worst_trade_pnl": 0.0,
        "win_rate": 0.0,
        "avg_hold_minutes": 0.0,
        "exit_reasons": "",
        "skip_reason": "",
    }

    if len(box_bars) < 60:
        result["skip_reason"] = "insufficient_bars"
        return result

    # Run strategy
    engine = BoxStrategyEngine(candidate)

    # Feed all bars (including pre-10AM for RSI warmup)
    for b in bars_1m:
        engine.on_bar(b)

    # Force close if still open at end
    if engine.active_trade:
        last_bar = bars_1m[-1]
        engine._close_trade(last_bar.close, last_bar.date, "end_of_data")

    trades = engine.trades
    result["num_trades"] = len(trades)

    if trades:
        pnls = [t.pnl for t in trades]
        result["total_pnl"] = round(sum(pnls), 2)
        result["best_trade_pnl"] = round(max(pnls), 2)
        result["worst_trade_pnl"] = round(min(pnls), 2)
        wins = sum(1 for p in pnls if p > 0)
        result["win_rate"] = round(wins / len(trades), 4)
        result["avg_hold_minutes"] = round(
            statistics.mean(t.hold_minutes for t in trades), 1
        )
        result["exit_reasons"] = "|".join(t.exit_reason for t in trades)

    return result


def run_candidate_with_trades(candidate: dict, bars_1m: list, exit_variant: str = "baseline") -> tuple:
    """Run box strategy, return (result_dict, list[BoxTradeState])."""
    symbol = candidate["symbol"]
    date_str = candidate.get("_date", "")

    # Filter bars to box window (10:00 - 15:45 ET)
    box_bars = []
    for b in bars_1m:
        bt = _bar_time_et(b)
        if time(10, 0) <= bt <= time(15, 45):
            box_bars.append(b)

    result = {
        "date": date_str,
        "symbol": symbol,
        "box_score": candidate.get("box_score", 0),
        "range_high_5d": candidate.get("range_high_5d", 0),
        "range_low_5d": candidate.get("range_low_5d", 0),
        "range_pct": candidate.get("range_pct", 0),
        "range_position_pct": candidate.get("range_position_pct", 0),
        "high_tests": candidate.get("high_tests", 0),
        "low_tests": candidate.get("low_tests", 0),
        "adr_util_today": candidate.get("adr_util_today", 0),
        "vwap_dist_pct": candidate.get("vwap_dist_pct", 0),
        "sma_slope_pct": candidate.get("sma_slope_pct"),
        "avg_daily_vol_5d": candidate.get("avg_daily_vol_5d", 0),
        "price": candidate.get("price", 0),
        "num_trades": 0,
        "total_pnl": 0.0,
        "best_trade_pnl": 0.0,
        "worst_trade_pnl": 0.0,
        "win_rate": 0.0,
        "avg_hold_minutes": 0.0,
        "exit_reasons": "",
        "skip_reason": "",
    }

    if len(box_bars) < 60:
        result["skip_reason"] = "insufficient_bars"
        return result, []

    # Run strategy
    engine = BoxStrategyEngine(candidate, exit_variant=exit_variant)
    for b in bars_1m:
        engine.on_bar(b)

    # Force close if still open at end
    if engine.active_trade:
        last_bar = bars_1m[-1]
        engine._close_trade(last_bar.close, last_bar.date, "end_of_data")

    trades = engine.trades
    result["num_trades"] = len(trades)

    if trades:
        pnls = [t.pnl for t in trades]
        result["total_pnl"] = round(sum(pnls), 2)
        result["best_trade_pnl"] = round(max(pnls), 2)
        result["worst_trade_pnl"] = round(min(pnls), 2)
        wins = sum(1 for p in pnls if p > 0)
        result["win_rate"] = round(wins / len(trades), 4)
        result["avg_hold_minutes"] = round(
            statistics.mean(t.hold_minutes for t in trades), 1
        )
        result["exit_reasons"] = "|".join(t.exit_reason for t in trades)

    return result, trades


# ── Load Scanner Results ───────────────────────────────────────────

def load_all_candidates() -> list:
    """Load all candidates from scanner_results_box/*.json."""
    all_candidates = []
    for f in sorted(SCANNER_DIR.glob("*.json")):
        if f.name.startswith("YTD"):
            continue
        date_str = f.stem
        with open(f) as fh:
            data = json.load(fh)
        # Handle both dict and list-of-dicts formats
        if isinstance(data, list):
            entries = []
            for item in data:
                if isinstance(item, dict):
                    entries.extend(item.get("candidates", []))
            candidates_list = entries
        else:
            candidates_list = data.get("candidates", [])
        for c in candidates_list:
            # Skip V1 scanner results (missing V2 fields)
            if "range_high_5d" not in c:
                continue
            c["_date"] = date_str
            all_candidates.append(c)
    return all_candidates


# ── Trade Detail Row ───────────────────────────────────────────────

def trade_to_row(t: BoxTradeState, date_str: str) -> dict:
    return {
        "date": date_str,
        "symbol": t.symbol,
        "entry_time": str(t.entry_time),
        "entry_price": round(t.entry_price, 4),
        "exit_time": str(t.exit_time),
        "exit_price": round(t.exit_price, 4) if t.exit_price else "",
        "shares": t.shares,
        "pnl": round(t.pnl, 2) if t.pnl else 0,
        "pnl_pct": round(t.pnl_pct, 4) if t.pnl_pct else 0,
        "exit_reason": t.exit_reason or "",
        "hold_minutes": round(t.hold_minutes, 1) if t.hold_minutes else 0,
        "box_top": round(t.box_top, 4),
        "box_bottom": round(t.box_bottom, 4),
        "box_range": round(t.box_range, 4),
        "rsi_at_entry": round(t.rsi_at_entry, 1),
        "bar_volume_at_entry": t.bar_volume_at_entry,
    }


# ── Report Generation ──────────────────────────────────────────────

def generate_report(results: list, all_trades: list, output_dir: Path = None):
    """Generate YTD_BOX_STRATEGY_REPORT.md from results."""
    if output_dir is None:
        output_dir = RESULTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Filter to candidates that traded
    traded = [r for r in results if r["num_trades"] > 0]
    skipped = [r for r in results if r["skip_reason"]]
    no_entry = [r for r in results if r["num_trades"] == 0 and not r["skip_reason"]]

    total_pnl = sum(r["total_pnl"] for r in traded)
    total_trades = sum(r["num_trades"] for r in traded)
    wins = sum(1 for t in all_trades if t["pnl"] > 0)
    losses = sum(1 for t in all_trades if t["pnl"] <= 0)
    win_rate = wins / total_trades * 100 if total_trades else 0

    lines = []
    lines.append("# YTD Box Strategy Backtest Report")
    lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Data Range**: 2026-01-02 to 2026-04-02")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1. Overall Stats
    lines.append("## 1. Overall Stats")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total candidates tested | {len(results)} |")
    lines.append(f"| Candidates with trades | {len(traded)} |")
    lines.append(f"| Candidates skipped (no data) | {len(skipped)} |")
    lines.append(f"| Candidates with no entry signal | {len(no_entry)} |")
    lines.append(f"| Total trades | {total_trades} |")
    lines.append(f"| Wins | {wins} |")
    lines.append(f"| Losses | {losses} |")
    lines.append(f"| Win rate | {win_rate:.1f}% |")
    lines.append(f"| Total P&L | ${total_pnl:,.2f} |")
    if total_trades:
        avg_pnl = total_pnl / total_trades
        best = max(all_trades, key=lambda t: t["pnl"])
        worst = min(all_trades, key=lambda t: t["pnl"])
        lines.append(f"| Avg P&L per trade | ${avg_pnl:,.2f} |")
        lines.append(f"| Best trade | ${best['pnl']:,.2f} ({best['symbol']} {best['date']}) |")
        lines.append(f"| Worst trade | ${worst['pnl']:,.2f} ({worst['symbol']} {worst['date']}) |")

        hold_times = [t["hold_minutes"] for t in all_trades if t["hold_minutes"] > 0]
        if hold_times:
            lines.append(f"| Avg hold time | {statistics.mean(hold_times):.0f} min |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # 2. Exit Reason Breakdown
    lines.append("## 2. Exit Reason Breakdown")
    lines.append("")
    reason_stats = defaultdict(lambda: {"count": 0, "pnl": 0.0, "wins": 0})
    for t in all_trades:
        r = t["exit_reason"]
        reason_stats[r]["count"] += 1
        reason_stats[r]["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            reason_stats[r]["wins"] += 1

    lines.append("| Exit Reason | Count | Total P&L | Avg P&L | Win Rate |")
    lines.append("|------------|-------|-----------|---------|----------|")
    for reason, stats in sorted(reason_stats.items(), key=lambda x: -x[1]["count"]):
        avg = stats["pnl"] / stats["count"] if stats["count"] else 0
        wr = stats["wins"] / stats["count"] * 100 if stats["count"] else 0
        lines.append(f"| {reason} | {stats['count']} | ${stats['pnl']:,.2f} | ${avg:,.2f} | {wr:.0f}% |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 3. Performance by Scanner Score
    lines.append("## 3. Performance by Scanner Score")
    lines.append("")
    _bucket_analysis(lines, results, "box_score",
                     [(5, 6), (6, 7), (7, 8), (8, 10)],
                     lambda r, lo, hi: lo <= r.get("box_score", 0) < hi)

    # 4. Performance by Range Characteristics
    lines.append("## 4. Performance by Range Characteristics")
    lines.append("")
    lines.append("### By Range %")
    lines.append("")
    _bucket_analysis(lines, results, "range_pct",
                     [(2, 4), (4, 6), (6, 8), (8, 10), (10, 20)],
                     lambda r, lo, hi: lo <= r.get("range_pct", 0) < hi)

    lines.append("### By Range Position % at Scan")
    lines.append("")
    _bucket_analysis(lines, results, "range_position_pct",
                     [(0, 15), (15, 25), (25, 35), (35, 50), (50, 100)],
                     lambda r, lo, hi: lo <= r.get("range_position_pct", 0) < hi)

    lines.append("### By Total Level Tests (High + Low)")
    lines.append("")
    _bucket_analysis(lines, results, "total_tests",
                     [(4, 5), (5, 6), (6, 7), (7, 20)],
                     lambda r, lo, hi: lo <= (r.get("high_tests", 0) + r.get("low_tests", 0)) < hi)

    # 5. Performance by Stock Characteristics
    lines.append("## 5. Performance by Stock Characteristics")
    lines.append("")
    lines.append("### By Price Bucket")
    lines.append("")
    _bucket_analysis(lines, results, "price",
                     [(5, 15), (15, 30), (30, 50), (50, 100)],
                     lambda r, lo, hi: lo <= r.get("price", 0) < hi)

    lines.append("### By ADR Utilization Today")
    lines.append("")
    _bucket_analysis(lines, results, "adr_util_today",
                     [(0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 1.0)],
                     lambda r, lo, hi: lo <= r.get("adr_util_today", 0) < hi)

    # 6. Performance by Symbol
    lines.append("## 6. Performance by Symbol (Top 20)")
    lines.append("")
    sym_stats = defaultdict(lambda: {"count": 0, "trades": 0, "pnl": 0.0, "wins": 0})
    for r in results:
        s = r["symbol"]
        sym_stats[s]["count"] += 1
        sym_stats[s]["trades"] += r["num_trades"]
        sym_stats[s]["pnl"] += r["total_pnl"]
        if r["total_pnl"] > 0 and r["num_trades"] > 0:
            sym_stats[s]["wins"] += 1

    sym_sorted = sorted(sym_stats.items(), key=lambda x: -x[1]["pnl"])
    lines.append("| Symbol | Appearances | Trades | Total P&L | Avg P&L/Trade | Win Rate |")
    lines.append("|--------|-------------|--------|-----------|---------------|----------|")
    for sym, st in sym_sorted[:20]:
        avg = st["pnl"] / st["trades"] if st["trades"] else 0
        wr = st["wins"] / st["count"] * 100 if st["count"] else 0
        lines.append(f"| {sym} | {st['count']} | {st['trades']} | ${st['pnl']:,.2f} | ${avg:,.2f} | {wr:.0f}% |")

    lines.append("")
    lines.append("### Worst Symbols")
    lines.append("")
    lines.append("| Symbol | Appearances | Trades | Total P&L | Avg P&L/Trade |")
    lines.append("|--------|-------------|--------|-----------|---------------|")
    for sym, st in sym_sorted[-10:]:
        avg = st["pnl"] / st["trades"] if st["trades"] else 0
        lines.append(f"| {sym} | {st['count']} | {st['trades']} | ${st['pnl']:,.2f} | ${avg:,.2f} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 7. Performance by Day of Week / Month
    lines.append("## 7. Performance by Day of Week / Month")
    lines.append("")
    dow_stats = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "wins": 0})
    month_stats = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "wins": 0})
    for r in traded:
        try:
            dt = datetime.strptime(r["date"], "%Y-%m-%d")
            dow = dt.strftime("%A")
            month = dt.strftime("%B")
            dow_stats[dow]["trades"] += r["num_trades"]
            dow_stats[dow]["pnl"] += r["total_pnl"]
            if r["total_pnl"] > 0:
                dow_stats[dow]["wins"] += 1
            month_stats[month]["trades"] += r["num_trades"]
            month_stats[month]["pnl"] += r["total_pnl"]
            if r["total_pnl"] > 0:
                month_stats[month]["wins"] += 1
        except ValueError:
            pass

    lines.append("### By Day of Week")
    lines.append("")
    lines.append("| Day | Trades | Total P&L | Avg P&L |")
    lines.append("|-----|--------|-----------|---------|")
    for dow in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
        if dow in dow_stats:
            st = dow_stats[dow]
            avg = st["pnl"] / st["trades"] if st["trades"] else 0
            lines.append(f"| {dow} | {st['trades']} | ${st['pnl']:,.2f} | ${avg:,.2f} |")
    lines.append("")

    lines.append("### By Month")
    lines.append("")
    lines.append("| Month | Trades | Total P&L | Avg P&L |")
    lines.append("|-------|--------|-----------|---------|")
    for month in ["January", "February", "March", "April"]:
        if month in month_stats:
            st = month_stats[month]
            avg = st["pnl"] / st["trades"] if st["trades"] else 0
            lines.append(f"| {month} | {st['trades']} | ${st['pnl']:,.2f} | ${avg:,.2f} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 8. Correlation Analysis
    lines.append("## 8. Correlation Analysis")
    lines.append("")
    lines.append("Spearman rank correlation between scanner fields and total P&L")
    lines.append("(only candidates with trades)")
    lines.append("")

    numeric_fields = ["box_score", "range_pct", "range_position_pct",
                      "high_tests", "low_tests", "adr_util_today",
                      "vwap_dist_pct", "price", "avg_daily_vol_5d"]
    correlations = []
    for field_name in numeric_fields:
        vals = [(r.get(field_name, 0) or 0, r["total_pnl"]) for r in traded
                if r.get(field_name) is not None]
        if len(vals) >= 10:
            corr = _spearman(vals)
            correlations.append((field_name, corr))

    correlations.sort(key=lambda x: -abs(x[1]))
    lines.append("| Field | Spearman ρ | Direction |")
    lines.append("|-------|-----------|-----------|")
    for fname, corr in correlations:
        direction = "↑ higher = better P&L" if corr > 0.05 else ("↓ lower = better P&L" if corr < -0.05 else "~ no clear relationship")
        lines.append(f"| {fname} | {corr:+.3f} | {direction} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 9. "If We Only Traded These" Analysis
    lines.append("## 9. \"If We Only Traded These\" Analysis")
    lines.append("")
    filters = [
        ("box_score >= 7", lambda r: r.get("box_score", 0) >= 7),
        ("box_score >= 8", lambda r: r.get("box_score", 0) >= 8),
        ("range_pct >= 4%", lambda r: r.get("range_pct", 0) >= 4),
        ("range_pct >= 6%", lambda r: r.get("range_pct", 0) >= 6),
        ("total_tests >= 5", lambda r: (r.get("high_tests", 0) + r.get("low_tests", 0)) >= 5),
        ("total_tests >= 6", lambda r: (r.get("high_tests", 0) + r.get("low_tests", 0)) >= 6),
        ("score >= 7 AND range >= 4%", lambda r: r.get("box_score", 0) >= 7 and r.get("range_pct", 0) >= 4),
        ("score >= 7 AND tests >= 5", lambda r: r.get("box_score", 0) >= 7 and (r.get("high_tests", 0) + r.get("low_tests", 0)) >= 5),
        ("score >= 7 AND range >= 4% AND tests >= 5", lambda r: r.get("box_score", 0) >= 7 and r.get("range_pct", 0) >= 4 and (r.get("high_tests", 0) + r.get("low_tests", 0)) >= 5),
    ]

    # Also build "appeared 10+ times" filter
    sym_counts = defaultdict(int)
    for r in results:
        sym_counts[r["symbol"]] += 1
    frequent_syms = {s for s, c in sym_counts.items() if c >= 10}
    filters.append(("stock appeared 10+ times in YTD", lambda r: r["symbol"] in frequent_syms))

    lines.append("| Filter | Candidates | Trades | Total P&L | Win Rate | Avg P&L/Trade |")
    lines.append("|--------|------------|--------|-----------|----------|---------------|")
    for label, fn in filters:
        subset = [r for r in results if fn(r) and r["num_trades"] > 0]
        n_cand = len([r for r in results if fn(r)])
        n_trades = sum(r["num_trades"] for r in subset)
        pnl = sum(r["total_pnl"] for r in subset)
        w = sum(1 for r in subset if r["total_pnl"] > 0)
        wr = w / len(subset) * 100 if subset else 0
        avg = pnl / n_trades if n_trades else 0
        lines.append(f"| {label} | {n_cand} | {n_trades} | ${pnl:,.2f} | {wr:.0f}% | ${avg:,.2f} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Report generated by box_backtest.py — STOP here for Cowork + Manny review.*")

    report_path = output_dir / "YTD_BOX_STRATEGY_REPORT.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Report saved: {report_path}", flush=True)


def _bucket_analysis(lines, results, label, buckets, match_fn):
    """Generate a bucket analysis table."""
    lines.append(f"| {label} | Candidates | Traded | Trades | Total P&L | Win Rate | Avg P&L/Trade |")
    lines.append("|" + "-------|" * 7)
    for lo, hi in buckets:
        subset = [r for r in results if match_fn(r, lo, hi)]
        traded_sub = [r for r in subset if r["num_trades"] > 0]
        n_trades = sum(r["num_trades"] for r in traded_sub)
        pnl = sum(r["total_pnl"] for r in traded_sub)
        w = sum(1 for r in traded_sub if r["total_pnl"] > 0)
        wr = w / len(traded_sub) * 100 if traded_sub else 0
        avg = pnl / n_trades if n_trades else 0
        lines.append(f"| {lo}-{hi} | {len(subset)} | {len(traded_sub)} | {n_trades} | ${pnl:,.2f} | {wr:.0f}% | ${avg:,.2f} |")
    lines.append("")
    lines.append("---")
    lines.append("")


def _spearman(pairs):
    """Simple Spearman rank correlation for a list of (x, y) tuples."""
    n = len(pairs)
    if n < 3:
        return 0.0

    def _rank(vals):
        indexed = sorted(enumerate(vals), key=lambda x: x[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and indexed[j + 1][1] == indexed[j][1]:
                j += 1
            avg_rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    xs, ys = zip(*pairs)
    rx = _rank(list(xs))
    ry = _rank(list(ys))

    d_sq = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - (6 * d_sq) / (n * (n ** 2 - 1))


# ── Main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Box Strategy YTD Backtest")
    parser.add_argument("--port", type=int, default=4002, help="IBKR Gateway port")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip candidates with cached bars")
    parser.add_argument("--report-only", action="store_true",
                        help="Regenerate report from cached results (no IBKR needed)")
    parser.add_argument("--exit-variant", default="baseline",
                        choices=["baseline", "vwap", "midbox", "tiered"],
                        help="Exit variant to test")
    args = parser.parse_args()

    # Output to variant-specific subdirectory if not baseline
    variant_labels = {"baseline": "", "vwap": "variant_B_vwap",
                      "midbox": "variant_C_midbox", "tiered": "variant_D_tiered"}
    results_dir = RESULTS_DIR
    if args.exit_variant != "baseline":
        results_dir = RESULTS_DIR / variant_labels[args.exit_variant]
    results_dir.mkdir(parents=True, exist_ok=True)

    candidates = load_all_candidates()
    print(f"Loaded {len(candidates)} candidates from scanner results", flush=True)

    # Group by date for efficient processing
    by_date = defaultdict(list)
    for c in candidates:
        by_date[c["_date"]].append(c)

    per_candidate_csv = results_dir / "per_candidate.csv"
    all_trades_csv = results_dir / "all_trades.csv"

    if args.report_only:
        # Load existing results
        results = []
        all_trade_rows = []
        if per_candidate_csv.exists():
            with open(per_candidate_csv) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    for k in ["box_score", "range_pct", "range_position_pct",
                              "adr_util_today", "vwap_dist_pct", "price",
                              "total_pnl", "best_trade_pnl", "worst_trade_pnl",
                              "win_rate", "avg_hold_minutes"]:
                        row[k] = float(row[k]) if row[k] else 0
                    for k in ["high_tests", "low_tests", "num_trades", "avg_daily_vol_5d"]:
                        row[k] = int(float(row[k])) if row[k] else 0
                    results.append(row)
        if all_trades_csv.exists():
            with open(all_trades_csv) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row["pnl"] = float(row["pnl"]) if row["pnl"] else 0
                    row["hold_minutes"] = float(row["hold_minutes"]) if row["hold_minutes"] else 0
                    all_trade_rows.append(row)
        generate_report(results, all_trade_rows, results_dir)
        return

    # Connect to IBKR (skip if all bars are cached)
    ib = None
    try:
        ib = IB()
        print(f"Connecting to IBKR on port {args.port}...", flush=True)
        ib.connect("127.0.0.1", args.port, clientId=11)
        print("Connected.", flush=True)
    except Exception:
        print("IBKR not available — using cached bars only.", flush=True)
        ib = None

    results = []
    all_trade_rows = []
    start_time = time_mod.time()

    # CSV writers
    candidate_fields = [
        "date", "symbol", "box_score", "range_high_5d", "range_low_5d",
        "range_pct", "range_position_pct", "high_tests", "low_tests",
        "adr_util_today", "vwap_dist_pct", "sma_slope_pct", "avg_daily_vol_5d",
        "price", "num_trades", "total_pnl", "best_trade_pnl", "worst_trade_pnl",
        "win_rate", "avg_hold_minutes", "exit_reasons", "skip_reason",
    ]
    trade_fields = [
        "date", "symbol", "entry_time", "entry_price", "exit_time", "exit_price",
        "shares", "pnl", "pnl_pct", "exit_reason", "hold_minutes",
        "box_top", "box_bottom", "box_range", "rsi_at_entry", "bar_volume_at_entry",
    ]

    cand_f = open(per_candidate_csv, "w", newline="")
    trade_f = open(all_trades_csv, "w", newline="")
    cand_writer = csv.DictWriter(cand_f, fieldnames=candidate_fields)
    trade_writer = csv.DictWriter(trade_f, fieldnames=trade_fields)
    cand_writer.writeheader()
    trade_writer.writeheader()

    dates_sorted = sorted(by_date.keys())
    total_dates = len(dates_sorted)

    try:
        for di, date_str in enumerate(dates_sorted):
            date_candidates = by_date[date_str]
            elapsed = time_mod.time() - start_time
            rate = (di / elapsed * 60) if elapsed > 0 and di > 0 else 0

            print(f"\n[{di+1}/{total_dates}] {date_str} — "
                  f"{len(date_candidates)} candidates "
                  f"(elapsed: {elapsed/60:.1f}m)", flush=True)

            for ci, candidate in enumerate(date_candidates):
                symbol = candidate["symbol"]

                # Check cache
                cached = _load_cached_bars(date_str, symbol)
                if cached is not None:
                    bars_1m = [BarProxy(b) for b in cached]
                elif ib is not None:
                    # Fetch from IBKR
                    raw_bars = fetch_1m_bars(ib, symbol, date_str)
                    if raw_bars:
                        _save_cached_bars(date_str, symbol, raw_bars)
                        bars_1m = raw_bars
                    else:
                        bars_1m = []
                    time_mod.sleep(2)  # IBKR rate limit
                else:
                    bars_1m = []

                # Run strategy
                result, trades = run_candidate_with_trades(candidate, bars_1m, exit_variant=args.exit_variant)
                results.append(result)
                cand_writer.writerow({k: result.get(k, "") for k in candidate_fields})
                cand_f.flush()

                # Write trade details
                for t in trades:
                    row = trade_to_row(t, date_str)
                    all_trade_rows.append(row)
                    trade_writer.writerow(row)
                    trade_f.flush()

                if result["num_trades"] > 0:
                    print(f"  {symbol}: {result['num_trades']} trades, "
                          f"P&L=${result['total_pnl']:+.2f} "
                          f"[{result['exit_reasons']}]", flush=True)

    except KeyboardInterrupt:
        print("\nInterrupted by user.", flush=True)
    finally:
        cand_f.close()
        trade_f.close()
        if ib is not None:
            ib.disconnect()

    # Generate report
    generate_report(results, all_trade_rows, results_dir)

    elapsed = time_mod.time() - start_time
    total_trades = sum(r["num_trades"] for r in results)
    total_pnl = sum(r["total_pnl"] for r in results)
    print(f"\n{'='*60}")
    print(f"  Box Backtest Complete ({args.exit_variant})")
    print(f"  Candidates: {len(results)}")
    print(f"  Trades: {total_trades}")
    print(f"  Total P&L: ${total_pnl:,.2f}")
    print(f"  Elapsed: {elapsed/60:.1f} minutes")
    print(f"  Results: {results_dir}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
