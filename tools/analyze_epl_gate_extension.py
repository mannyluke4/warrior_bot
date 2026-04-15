#!/usr/bin/env python3
"""Post-hoc analysis for the BIRD autopsy Q3.

Parses per-day sim trade tables from /tmp/autopsy/, isolates EPL MP re-entry
trades (exit reason starts with "epl_mp_"), and simulates what an extended
Gate 5 at max_losses=1 and max_losses=2 would have blocked.

For each EPL trade on a given (symbol, date):
  - Count the losses on that symbol prior to the EPL entry time.
  - If prior_losses >= max_losses, the trade would be blocked.
  - Tally P&L of blocked trades (wins + losses separately).

Output: two tables (one per threshold) with columns per the directive.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

LOG_DIR = Path("/tmp/autopsy")

# Trade row in the sim report.
# Example:
#    10   10:20  11.5000  10.8100  0.6700    5.0  10.8100  epl_mp_stop_hit          -3005    -1.0R  10:20
TRADE_RE = re.compile(
    r"^\s*(\d+)\s+(\d{2}:\d{2})\s+"         # num, time
    r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+"    # entry stop r
    r"([\d.]+)\s+([\d.]+)\s+"               # score exit
    r"(\S+)\s+"                             # reason
    r"([+-]?\d+)\s+"                        # pnl
    r"([+-][\d.]+R)"                        # r_mult
)


def parse_trades(log_path: Path) -> list[dict]:
    trades: list[dict] = []
    with log_path.open() as f:
        for line in f:
            m = TRADE_RE.match(line)
            if not m:
                continue
            trades.append({
                "num": int(m.group(1)),
                "time": m.group(2),
                "entry": float(m.group(3)),
                "reason": m.group(8),
                "pnl": int(m.group(9)),
                "r_mult": m.group(10),
            })
    return trades


def simulate_extended_gate(trades: list[dict], max_losses: int) -> dict:
    """Walk trades chronologically, count prior losses, decide blocks."""
    # Note: this analysis uses per-symbol per-day losses. Since each
    # autopsy file is already one (symbol, date), that's the correct scope.
    prior_losses = 0
    blocked = []
    for t in trades:
        is_epl = t["reason"].startswith("epl_mp_")
        pnl = t["pnl"]
        if is_epl and prior_losses >= max_losses:
            blocked.append({**t, "prior_losses": prior_losses})
        # Running-count update happens AFTER the gate check for this trade:
        # a loss counts against the NEXT trade's gate decision.
        if pnl < 0:
            prior_losses += 1
    blocked_wins = sum(b["pnl"] for b in blocked if b["pnl"] > 0)
    blocked_losses = sum(b["pnl"] for b in blocked if b["pnl"] < 0)
    return {
        "blocked_trades": blocked,
        "blocked_count": len(blocked),
        "delta_pnl": -(blocked_wins + blocked_losses),  # delta = removing these trades
        "blocked_winners": [b for b in blocked if b["pnl"] > 0],
        "blocked_losers": [b for b in blocked if b["pnl"] < 0],
    }


def analyze_day(symbol: str, date: str, log_path: Path):
    if not log_path.exists():
        print(f"\n{symbol} {date}: no log at {log_path}")
        return None

    trades = parse_trades(log_path)
    epl_trades = [t for t in trades if t["reason"].startswith("epl_mp_")]
    total_pnl = sum(t["pnl"] for t in trades)

    result1 = simulate_extended_gate(trades, max_losses=1)
    result2 = simulate_extended_gate(trades, max_losses=2)

    print(f"\n══ {symbol} {date} ══")
    print(f"  Total trades: {len(trades)}  |  EPL: {len(epl_trades)}  |  Day P&L: ${total_pnl:+,}")
    if epl_trades:
        print(f"  EPL detail:")
        for t in epl_trades:
            print(f"    T{t['num']} @ {t['time']} ${t['entry']:.2f} → {t['reason']}  ${t['pnl']:+,} ({t['r_mult']})")

    for label, r in [("max_losses=1", result1), ("max_losses=2", result2)]:
        if r["blocked_count"] == 0:
            print(f"  {label}: 0 EPL trades blocked")
        else:
            print(f"  {label}: {r['blocked_count']} blocked, Δ P&L = ${r['delta_pnl']:+,}"
                  f"  ({len(r['blocked_winners'])}W ${sum(x['pnl'] for x in r['blocked_winners']):+,}"
                  f" / {len(r['blocked_losers'])}L ${sum(x['pnl'] for x in r['blocked_losers']):+,})")
            for t in r["blocked_trades"]:
                w = "WIN" if t["pnl"] > 0 else "LOSS"
                print(f"    BLOCKED T{t['num']} @ {t['time']} {w} ${t['pnl']:+,}"
                      f"  (prior_losses_on_sym={t['prior_losses']}, reason={t['reason']})")

    return {
        "symbol": symbol, "date": date,
        "total_trades": len(trades), "epl_trades": len(epl_trades),
        "day_pnl": total_pnl,
        "blocked_at_1": result1, "blocked_at_2": result2,
    }


def main():
    days = [
        ("VERO", "2026-01-16"),
        ("ROLR", "2026-01-14"),
        ("BATL", "2026-01-26"),
        ("MOVE", "2026-01-23"),
        ("BIRD", "2026-04-15"),
    ]
    results = []
    for sym, date in days:
        path = LOG_DIR / f"{sym}_{date}.log"
        r = analyze_day(sym, date, path)
        if r:
            results.append(r)

    # Summary table
    print("\n\n══ SUMMARY TABLE ══")
    print(f"{'Symbol':6} {'Date':10} {'EPL':>4} {'Blk=1':>5} {'Δ@1':>8} {'Blk=2':>5} {'Δ@2':>8}  Winner blocked?")
    print("-" * 78)
    any_winner_blocked = {1: [], 2: []}
    for r in results:
        b1 = r["blocked_at_1"]; b2 = r["blocked_at_2"]
        winner_blocked_1 = bool(b1["blocked_winners"])
        winner_blocked_2 = bool(b2["blocked_winners"])
        if winner_blocked_1:
            any_winner_blocked[1].append(r["symbol"])
        if winner_blocked_2:
            any_winner_blocked[2].append(r["symbol"])
        verdict = []
        if winner_blocked_1: verdict.append("@1: YES")
        if winner_blocked_2: verdict.append("@2: YES")
        if not verdict: verdict = ["no"]
        print(f"{r['symbol']:6} {r['date']:10} {r['epl_trades']:>4} "
              f"{b1['blocked_count']:>5} ${b1['delta_pnl']:>+6,} "
              f"{b2['blocked_count']:>5} ${b2['delta_pnl']:>+6,}  {', '.join(verdict)}")

    print("\nRegression canary verdict:")
    print(f"  max_losses=1: winners blocked on {any_winner_blocked[1] or 'NONE'}")
    print(f"  max_losses=2: winners blocked on {any_winner_blocked[2] or 'NONE'}")


if __name__ == "__main__":
    main()
