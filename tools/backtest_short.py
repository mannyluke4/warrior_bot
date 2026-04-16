#!/usr/bin/env python3
"""Backtest the Strategy B short detector on a (symbol, date) from tick cache.

Replays ticks through bar_builder + short_detector, simulates the hypothetical
short trade, reports entry/stop/exit + P&L.

Usage:
    python tools/backtest_short.py VERO 2026-01-16
    python tools/backtest_short.py --universe  # VERO, ROLR, GWAV, BIRD, PAVM, ...

Exit logic mirrors the strategy's design targets:
  - Hard stop at HOD × (1 + WB_SHORT_STOP_BUFFER_PCT/100)
  - Target 1: VWAP at the time of arm (cover half)
  - Target 2: 50% retrace of the morning move (cover remainder)
  - Time-stop: exit at sim_end regardless
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bars import TradeBarBuilder, Bar  # noqa: E402
from short_detector import ShortDetector  # noqa: E402

ET = ZoneInfo("America/New_York")

# Universe — stocks the bot actually subscribes to (≤$20 entry). From
# Phase 1 fade analysis, these are the "in-universe" set that the live
# short detector would see in a real session.
IN_UNIVERSE = [
    ("VERO", "2026-01-16"),
    ("ROLR", "2026-01-14"),
    ("GWAV", "2026-01-16"),
    ("HIND", "2026-01-27"),
    ("ACCL", "2026-01-16"),
    ("MLEC", "2026-02-13"),
    ("BIRD", "2026-04-15"),
    ("PAVM", "2026-01-21"),
]


@dataclass
class Trade:
    symbol: str
    date: str
    entry_price: float
    entry_time: str
    stop: float
    hod: float
    target1_vwap: float
    target2_retrace: float
    exit_price: float
    exit_time: str
    exit_reason: str
    pnl_per_share: float
    r_multiple: float
    qty: int
    dollar_pnl: float
    notional: float


# Sizing — mirrors live squeeze config at commit HEAD
EQUITY = float(os.environ.get("WB_EQUITY", "30000"))
RISK_PCT = float(os.environ.get("WB_RISK_PCT", "0.035"))
MAX_NOTIONAL = float(os.environ.get("WB_MAX_NOTIONAL", "50000"))
MAX_SHARES = int(os.environ.get("WB_MAX_SHARES", "100000"))


def compute_qty(entry_price: float, stop: float) -> int:
    """Position sizing: 3.5% of equity / R (dollar risk per share).
    Capped at MAX_NOTIONAL / entry_price, floored at 1."""
    r = abs(stop - entry_price)
    if r <= 0:
        return 0
    risk_dollars = max(50, EQUITY * RISK_PCT)
    qty_risk = int(risk_dollars / r)
    qty_notional = int(MAX_NOTIONAL / max(entry_price, 0.01))
    return max(1, min(qty_risk, qty_notional, MAX_SHARES))


def load_ticks(symbol: str, date: str):
    path = os.path.join(ROOT, "tick_cache", date, f"{symbol}.json.gz")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with gzip.open(path, "rt") as f:
        raw = json.load(f)
    ticks = []
    for t in raw:
        try:
            ts = datetime.fromisoformat(t["t"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ticks.append((ts, float(t["p"]), int(t["s"])))
        except (KeyError, ValueError, TypeError):
            continue
    ticks.sort(key=lambda x: x[0])
    return ticks


def run_symbol(symbol: str, date: str, verbose: bool = False) -> list[Trade]:
    ticks = load_ticks(symbol, date)
    if not ticks:
        return []

    # Session-low tracking for 50% retrace target
    pre_peak_min_price = float("inf")

    # Build bars + VWAP from ticks.
    # We also capture VWAP at each bar close for the detector + targets.
    bars_collected: list[Bar] = []
    bar_vwaps: list[float] = []
    cum_pv = 0.0
    cum_v = 0

    detector = ShortDetector()
    detector.symbol = symbol

    entered = False
    entry_price = 0.0
    entry_time = None
    armed_hod = 0.0
    armed_vwap = 0.0

    exit_price = 0.0
    exit_time = None
    exit_reason = ""

    # Bar builder feeds the detector on close — we use a callback.
    def on_bar(bar):
        nonlocal pre_peak_min_price
        bars_collected.append(bar)
        bar_vwaps.append(cum_pv / cum_v if cum_v > 0 else 0.0)
        # Pre-peak session low for 50% retrace (only track until HOD detected)
        if not entered and detector._state == "IDLE":
            if bar.low < pre_peak_min_price:
                pre_peak_min_price = bar.low
        msg = detector.on_bar_close_1m(bar, vwap=bar_vwaps[-1])
        if verbose and msg:
            print(f"  [{bar.start.astimezone(ET).strftime('%H:%M')}] {msg}")

    bb = TradeBarBuilder(on_bar_close=on_bar, et_tz=ET, interval_seconds=60)

    trade: Trade | None = None

    for ts, price, size in ticks:
        cum_pv += price * size
        cum_v += size
        bb.on_trade(symbol, price, size, ts)

        if entered:
            # Manage the short position — stop + tiered targets.
            # Key design: only consider targets that are BELOW entry. If
            # entry already undercut VWAP (happens when LH break fires
            # late in the fade), VWAP is useless as a forward target — fall
            # back to 50% retrace, then gap fill (entry × 0.85), then time.
            curr_vwap = bar_vwaps[-1] if bar_vwaps else 0.0
            retrace_50 = (armed_hod + pre_peak_min_price) / 2.0 if pre_peak_min_price < float("inf") else entry_price * 0.90

            # Stop hit (price rose back above stop)
            if detector.armed and price >= detector.armed.stop:
                exit_price = detector.armed.stop
                exit_time = ts
                exit_reason = "stop_hit"
                break
            # Target 1 (VWAP) — only if armed_vwap was meaningfully below entry
            if armed_vwap > 0 and armed_vwap < entry_price * 0.99 and price <= armed_vwap:
                exit_price = price
                exit_time = ts
                exit_reason = "target_vwap"
                break
            # Target 2 (50% retrace) — only if below entry
            if retrace_50 < entry_price * 0.99 and price <= retrace_50:
                exit_price = price
                exit_time = ts
                exit_reason = "target_retrace50"
                break
            # Time-stop: exit if held > 60 minutes (configurable). Prevents
            # carrying a short into afternoon chop where the trade can revert.
            if entry_time and (ts - entry_time).total_seconds() > 3600:
                exit_price = price
                exit_time = ts
                exit_reason = "time_60min"
                break
            continue

        # Not yet entered — check for trigger
        msg = detector.on_trade_price(price)
        if msg and "SHORT ENTRY SIGNAL" in msg:
            if verbose:
                print(f"  [{ts.astimezone(ET).strftime('%H:%M:%S')}] {msg}")
            entered = True
            entry_price = price
            entry_time = ts
            armed_hod = detector.armed.hod_price
            armed_vwap = bar_vwaps[-1] if bar_vwaps else 0.0
            detector.notify_trade_opened()

    if entered:
        if not exit_time:
            # Time-out at end of tick stream
            exit_price = ticks[-1][1]
            exit_time = ticks[-1][0]
            exit_reason = "time_stop"
        r = detector.armed.stop - entry_price if detector.armed else 0.01
        pnl_per_share = entry_price - exit_price  # short: profit when price falls
        r_multiple = pnl_per_share / r if r > 0 else 0
        qty = compute_qty(entry_price, detector.armed.stop) if detector.armed else 0
        trade = Trade(
            symbol=symbol,
            date=date,
            entry_price=round(entry_price, 4),
            entry_time=entry_time.astimezone(ET).strftime("%H:%M:%S"),
            stop=round(detector.armed.stop, 4) if detector.armed else 0,
            hod=round(armed_hod, 4),
            target1_vwap=round(armed_vwap, 4),
            target2_retrace=round((armed_hod + pre_peak_min_price) / 2.0, 4)
            if pre_peak_min_price < float("inf") else 0,
            exit_price=round(exit_price, 4),
            exit_time=exit_time.astimezone(ET).strftime("%H:%M:%S"),
            exit_reason=exit_reason,
            pnl_per_share=round(pnl_per_share, 4),
            r_multiple=round(r_multiple, 2),
            qty=qty,
            dollar_pnl=round(pnl_per_share * qty, 2),
            notional=round(entry_price * qty, 2),
        )
        return [trade]
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", nargs="?")
    parser.add_argument("date", nargs="?")
    parser.add_argument("--universe", action="store_true", help="Run all in-universe targets")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    targets = IN_UNIVERSE if args.universe else [(args.symbol, args.date)]
    if not args.universe and (not args.symbol or not args.date):
        parser.print_help()
        return

    all_trades = []
    print(f"Sizing: equity=${EQUITY:,.0f} risk={RISK_PCT*100:.1f}% max_notional=${MAX_NOTIONAL:,.0f}")
    print()
    print(f"{'Symbol':6} {'Date':10} {'Entry':>8} {'Stop':>8} {'Exit':>8}  {'Reason':17} "
          f"{'Qty':>5} {'Notional':>9}  {'PnL/sh':>7} {'$PnL':>8} {'R':>6}")
    print("-" * 115)
    for sym, date in targets:
        try:
            trades = run_symbol(sym, date, verbose=args.verbose)
        except FileNotFoundError:
            print(f"{sym:6} {date:10}  (no tick cache — skipped)")
            continue
        if not trades:
            print(f"{sym:6} {date:10}  NO TRADE (no arm/trigger detected)")
            continue
        for t in trades:
            all_trades.append(t)
            print(f"{t.symbol:6} {t.date:10} ${t.entry_price:>7.2f} ${t.stop:>7.2f} "
                  f"${t.exit_price:>7.2f}  "
                  f"{t.exit_reason:17} {t.qty:>5} ${t.notional:>8,.0f}  "
                  f"${t.pnl_per_share:>+6.2f} ${t.dollar_pnl:>+7,.0f} {t.r_multiple:>+5.1f}R")

    if all_trades:
        total_pnl = sum(t.pnl_per_share for t in all_trades)
        total_dollar = sum(t.dollar_pnl for t in all_trades)
        wins = [t for t in all_trades if t.dollar_pnl > 0]
        avg_r = sum(t.r_multiple for t in all_trades) / len(all_trades)
        avg_notional = sum(t.notional for t in all_trades) / len(all_trades)
        print()
        print(f"Total: {len(all_trades)} trades, {len(wins)} wins ({len(wins) / len(all_trades) * 100:.0f}% WR), "
              f"avg R={avg_r:+.2f}")
        print(f"  PnL/sh sum: ${total_pnl:+,.2f}  |  Dollar PnL: ${total_dollar:+,.2f}  |  Avg notional: ${avg_notional:,.0f}")


if __name__ == "__main__":
    main()
