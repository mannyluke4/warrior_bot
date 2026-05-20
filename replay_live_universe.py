#!/usr/bin/env python3
"""replay_live_universe.py — 1:1 backtest against live's actual watchlist.

For each day's daily log, extract per-symbol visibility windows (when the
symbol was actively producing ticks in the bot's ACTIVE heartbeats) and
run simulate.py for that exact window. This avoids the "phantom trade"
problem where the standard backtester runs candidates the live bot never
actually had on its dynamic watchlist.

Usage:
    ./venv/bin/python replay_live_universe.py --start 2026-05-15 --end 2026-05-20
    WB_BT_MOVE_STRIKE=1 ./venv/bin/python replay_live_universe.py --start 2026-05-15 --end 2026-05-20 --label "MoveStrike"

Env vars propagate through to simulate.py (so WB_BT_MOVE_STRIKE,
WB_TICK_LEVEL_ARM, etc. work via shell prefix).
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

WORKDIR = Path(__file__).parent.resolve()
ACTIVE_LINE_RE = re.compile(
    r"^\[(\d{2}):(\d{2}):\d{2} ET\] ACTIVE \|"
)
# Capture each "SYM:Nt/STATE" token in the ACTIVE line tail.
SYM_TOKEN_RE = re.compile(r"\b([A-Z][A-Z0-9]{0,5}):\d+t/[A-Z_]+")


def parse_log_windows(log_path: Path) -> dict[str, tuple[str, str]]:
    """Return {symbol: ("HH:MM", "HH:MM")} = first/last seen on ACTIVE lines."""
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    with open(log_path, "r", errors="replace") as f:
        for line in f:
            m = ACTIVE_LINE_RE.match(line)
            if not m:
                continue
            hh, mm = m.group(1), m.group(2)
            timestr = f"{hh}:{mm}"
            for tok in SYM_TOKEN_RE.finditer(line):
                sym = tok.group(1)
                if sym not in first:
                    first[sym] = timestr
                last[sym] = timestr
    return {sym: (first[sym], last[sym]) for sym in first}


TRADE_LINE_RE = re.compile(
    r"^\s+\d+\s+(\d{2}:\d{2})\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+"
    r"([\d.]+)\s+([\d.]+)\s+(\S+)\s+([-+]?\d+)"
)


def run_one_sim(symbol: str, date: str, start: str, end: str,
                slippage: float = 0.07, extra_env: dict | None = None) -> list[dict]:
    """Run simulate.py for one (symbol, date, window). Return list of trades."""
    cmd = [
        sys.executable, str(WORKDIR / "simulate.py"),
        symbol, date, start, end,
        "--ticks", "--tick-cache", "tick_cache/",
        "--slippage", str(slippage), "--no-fundamentals",
    ]
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
            cwd=str(WORKDIR), env=env,
        )
    except subprocess.TimeoutExpired:
        return []
    trades = []
    for line in (result.stdout + result.stderr).splitlines():
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
    return trades


def daterange(start: str, end: str):
    d0 = datetime.strptime(start, "%Y-%m-%d").date()
    d1 = datetime.strptime(end, "%Y-%m-%d").date()
    while d0 <= d1:
        yield d0.strftime("%Y-%m-%d")
        d0 += timedelta(days=1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--label", default="replay", help="Label for report")
    p.add_argument("--slippage", type=float, default=0.07)
    p.add_argument("--end-cap", default="12:00",
                   help="Cap window end at this ET time (default 12:00 — Ross hours)")
    args = p.parse_args()

    overall_trades: list[dict] = []
    per_day: list[dict] = []

    for date in daterange(args.start, args.end):
        log_path = WORKDIR / "logs" / f"{date}_daily.log"
        if not log_path.exists():
            print(f"[{date}] no daily log — skip", flush=True)
            continue
        windows = parse_log_windows(log_path)
        if not windows:
            print(f"[{date}] no ACTIVE heartbeats — skip", flush=True)
            continue
        day_pnl = 0
        day_trades_count = 0
        day_syms = []
        for sym, (t0, t1) in sorted(windows.items()):
            # The detector needs pre-arm context (~30 min of bars for the
            # prime sequence). So sim_start is FIXED at 04:00 to give the
            # detector full visibility; we post-filter trades to drop any
            # that happened before live actually had the symbol on its
            # watchlist (first ACTIVE timestamp).
            end_capped = min(t1, args.end_cap)
            if t0 >= end_capped:
                continue  # symbol only appeared after cap
            tick_cache_path = WORKDIR / "tick_cache" / date / f"{sym}.json.gz"
            if not tick_cache_path.exists():
                continue
            trades = run_one_sim(sym, date, "04:00", end_capped, slippage=args.slippage)
            for t in trades:
                # 1:1 filter: drop trades that fired before live's first
                # ACTIVE for this symbol (= before live actually had it
                # on the watchlist). Avoids "phantom arms" pre-discovery.
                if t["time"] < t0:
                    continue
                t["symbol"] = sym
                t["date"] = date
                day_pnl += t["pnl"]
                day_trades_count += 1
                overall_trades.append(t)
                day_syms.append(sym)
        per_day.append({"date": date, "trades": day_trades_count, "pnl": day_pnl})
        print(f"[{date}] {day_trades_count} trades, P&L=${day_pnl:+,} "
              f"({len(windows)} symbols watched, {len(set(day_syms))} traded)",
              flush=True)

    total_pnl = sum(t["pnl"] for t in overall_trades)
    wins = [t for t in overall_trades if t["pnl"] > 0]
    losses = [t for t in overall_trades if t["pnl"] <= 0]

    print("")
    print(f"=== {args.label} | {args.start} → {args.end} ===")
    print(f"Total: {len(overall_trades)} trades, "
          f"{len(wins)}W / {len(losses)}L "
          f"({100*len(wins)/max(1,len(overall_trades)):.0f}% WR)")
    print(f"Gross P&L: ${total_pnl:+,}")
    if wins:
        print(f"Avg winner: ${sum(t['pnl'] for t in wins)//len(wins):+,}")
    if losses:
        print(f"Avg loser:  ${sum(t['pnl'] for t in losses)//len(losses):+,}")
    print("")
    print("Per-day:")
    for d in per_day:
        print(f"  {d['date']}: {d['trades']} trades, ${d['pnl']:+,}")

    out_path = WORKDIR / "backtest_status" / f"replay_{args.label}_{args.start}_{args.end}.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"label": args.label, "start": args.start, "end": args.end,
                   "trades": overall_trades, "per_day": per_day,
                   "total_pnl": total_pnl}, f, indent=2)
    print(f"\nDetail: {out_path}")


if __name__ == "__main__":
    main()
