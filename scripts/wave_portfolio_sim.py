"""wave_portfolio_sim.py — Variant 7 (and V8 combined): cross-symbol
concurrent-position simulator.

Uses the existing single-position simulate_trade + wave detection
machinery, but post-processes the resulting trade timeline to enforce
a portfolio-level concurrency cap (≤3 open positions, no duplicate
symbol).

Design — "filter, don't re-simulate":

  Each candidate trade's exit is independent of other trades (different
  symbols, no shared state). So we don't need to re-simulate when applying
  the concurrency cap — we can simulate every candidate independently
  (which we already do via wave_census.simulate_trade), then walk the
  resulting (entry_time → exit_time) intervals in time order and keep
  only the ones that fit in 3 slots.

This is correct, fast, and reuses everything we built. The only thing it
gives up is potential interaction effects (e.g., maybe holding A would
have affected your decision to enter B) — but the directive's V7 spec is
purely a slot/symbol cap, no inter-trade interaction.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import pytz

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from scripts.wave_census import (  # noqa: E402
    PRESETS, VariantConfig, HypotheticalTrade, process_symbol_date,
    discover_2026_files, OUT_DIR, ET,
)


@dataclass
class PortfolioTrade:
    """A trade that survived the concurrency filter, plus its slot index."""
    symbol: str
    date: str
    wave_id: int
    score: int
    entry_time_et: str
    entry_price: float
    target: float
    stop: float
    exit_time_et: str
    exit_price: float
    exit_reason: str
    pnl_per_share: float
    shares: int
    pnl: float
    risk_per_share: float
    duration_minutes: float
    slot: int  # 0, 1, or 2 — which of the 3 slots this trade used


def _parse_et_dt(date_str: str, et_hms: str) -> datetime:
    """Combine a YYYY-MM-DD date with an HH:MM:SS ET time string into a
    timezone-aware datetime in UTC for ordering."""
    dt = datetime.strptime(f"{date_str} {et_hms}", "%Y-%m-%d %H:%M:%S")
    return ET.localize(dt).astimezone(timezone.utc)


def apply_concurrency(
    candidates: List[HypotheticalTrade],
    max_concurrent: int = 3,
    one_per_symbol: bool = True,
) -> List[PortfolioTrade]:
    """Walk candidate trades in entry-time order; keep only those that fit
    within `max_concurrent` simultaneous slots (and obey one-per-symbol).

    Open positions are released when their exit_time precedes the new
    candidate's entry_time. A trade whose exit_time == another's entry_time
    is treated as freed before the new one opens (i.e., closes first).
    """
    by_date_then_time: Dict[str, List[HypotheticalTrade]] = defaultdict(list)
    for t in candidates:
        by_date_then_time[t.date].append(t)

    portfolio: List[PortfolioTrade] = []
    for date_str, day_trades in by_date_then_time.items():
        # Sort by (entry_time, exit_time) so deterministic ordering on ties.
        day_trades.sort(key=lambda t: (t.entry_time_et, t.exit_time_et))

        open_until: List[Tuple[datetime, str, int]] = []  # (exit_dt, symbol, slot_idx)

        for t in day_trades:
            entry_dt = _parse_et_dt(t.date, t.entry_time_et)
            exit_dt = _parse_et_dt(t.date, t.exit_time_et)

            # Free any slots whose exit time is ≤ this candidate's entry.
            open_until = [(d, s, i) for (d, s, i) in open_until if d > entry_dt]

            # One per symbol gate
            if one_per_symbol and any(s == t.symbol for (_, s, _) in open_until):
                continue
            # Concurrency cap
            if len(open_until) >= max_concurrent:
                continue

            # Pick the first available slot index (0..max_concurrent-1).
            used_slots = {i for (_, _, i) in open_until}
            slot = next((i for i in range(max_concurrent) if i not in used_slots), 0)

            open_until.append((exit_dt, t.symbol, slot))
            portfolio.append(PortfolioTrade(**{**asdict(t), "slot": slot}))

    return portfolio


def run_portfolio_variant(
    variant_name: str,
    config: VariantConfig,
    max_concurrent: int = 3,
    one_per_symbol: bool = True,
    files: Optional[list] = None,
) -> Tuple[List[HypotheticalTrade], List[PortfolioTrade]]:
    """Run the per-(sym, date) census with `config`, then apply the
    portfolio concurrency filter. Returns (raw_candidates, portfolio_trades)."""
    if files is None:
        files = discover_2026_files()

    candidates: List[HypotheticalTrade] = []
    t0 = time.time()
    for i, (sym, date_str, path) in enumerate(files, 1):
        try:
            _, _, trades = process_symbol_date(sym, date_str, path, config=config)
        except Exception as e:
            print(f"  [{i}/{len(files)}] {sym} {date_str}: ERROR {e}", flush=True)
            continue
        candidates.extend(trades)
        if i % 200 == 0 or i == len(files):
            elapsed = time.time() - t0
            rate = i / max(elapsed, 0.001)
            print(f"  [{i}/{len(files)}]  {len(candidates)} candidates  "
                  f"[{rate:.1f}/s, eta {(len(files)-i)/max(rate,0.001):.0f}s]", flush=True)

    portfolio = apply_concurrency(candidates, max_concurrent, one_per_symbol)
    return candidates, portfolio


def write_trades_csv(path: str, trades: list) -> None:
    if not trades:
        with open(path, "w") as f:
            f.write("")
        return
    fields = list(asdict(trades[0]).keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in trades:
            w.writerow(asdict(t))


def summarize(trades: list, label: str) -> dict:
    if not trades:
        return {"label": label, "n_trades": 0}
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total = sum(pnls)
    gross_w = sum(wins)
    gross_l = abs(sum(losses)) or 1.0
    return {
        "label": label,
        "n_trades": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 2),
        "profit_factor": round(gross_w / gross_l, 2),
        "total_pnl": round(total, 2),
        "avg_win": round(sum(wins) / max(len(wins), 1), 2),
        "avg_loss": round(sum(losses) / max(len(losses), 1), 2),
        "max_trade": round(max(pnls), 2),
        "min_trade": round(min(pnls), 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Wave portfolio simulator (V7/V8)")
    ap.add_argument("--base-variant", default="v0_baseline",
                    help="Base config preset (default: v0_baseline). V7 = v0_baseline. "
                         "V8 should be a custom combined variant.")
    ap.add_argument("--out-name", default="",
                    help="Output dir name override (default = base_variant + '_concurrent').")
    ap.add_argument("--max-concurrent", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--symbols", default="")
    args = ap.parse_args()

    if args.base_variant not in PRESETS:
        print(f"Unknown variant: {args.base_variant}", file=sys.stderr)
        return 2
    config = PRESETS[args.base_variant]()
    print(f"Base variant: {config.name}, max_concurrent={args.max_concurrent}", flush=True)

    files = discover_2026_files()
    if args.symbols:
        wanted = {s.strip().upper() for s in args.symbols.split(",") if s.strip()}
        files = [f for f in files if f[0].upper() in wanted]
    if args.limit:
        files = files[: args.limit]

    out_name = args.out_name or f"{config.name}_concurrent"
    out_dir = os.path.join(OUT_DIR, out_name)
    os.makedirs(out_dir, exist_ok=True)

    candidates, portfolio = run_portfolio_variant(
        out_name, config, max_concurrent=args.max_concurrent, files=files,
    )

    write_trades_csv(os.path.join(out_dir, f"{out_name}_candidates.csv"), candidates)
    write_trades_csv(os.path.join(out_dir, f"{out_name}_portfolio.csv"), portfolio)

    cand_sum = summarize(candidates, "candidates (no cap)")
    port_sum = summarize(portfolio, f"portfolio (≤{args.max_concurrent} concurrent, 1/symbol)")
    summary = {"candidates": cand_sum, "portfolio": port_sum,
               "filtered_out": cand_sum["n_trades"] - port_sum["n_trades"]}
    with open(os.path.join(out_dir, f"{out_name}_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
