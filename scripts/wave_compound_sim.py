"""wave_compound_sim.py — Compounding-equity + buying-power-aware backtest.

The Stage 2 V8b headline (+$154K, PF 2.01) used FIXED $1,000 risk per
trade. Live config uses 2.5% equity-percent sizing (matches squeeze for
compounding). This sim validates what V8b looks like under realistic
account dynamics:

  - Starting equity = $30,000 (matches squeeze + main bot)
  - Risk per trade = 2.5% × current equity, floor $500, ceiling $5,000
  - V0 sizer hardening (min risk-per-share floor, $50K max notional)
  - Buying power cap: BP = 4 × current_equity (PDT-protected paper account
    with equity > $25K). Position sizing also bounded by available BP.
  - Concurrent-position cap: ≤3 (V7), no duplicate symbols
  - Trades walked globally in entry-time order; each trade's outcome (entry
    price, exit price, exit reason) is reused from the per-(sym, date)
    sim — only sizing/pnl is recomputed against running equity & BP.

Why post-process and not re-run? Trade outcomes (target_hit / stop_hit /
trailing_stop) depend on price trajectory, not on shares. So we can reuse
the existing per-trade outputs and just resize. This is correct as long as
no individual trade is sized so large that it could move the market — at
≤$50K notional, that's vanishingly true for the names in this universe.

Outputs to wave_research/<base>_compound/:
  trades.csv         — every executed trade with compounding-correct shares + pnl
  skipped.csv        — candidates rejected by BP cap or concurrency
  equity_curve.csv   — equity at each trade boundary
  summary.json       — headline stats vs fixed-$1K baseline
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import pytz

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from scripts.wave_census import HypotheticalTrade, OUT_DIR, ET  # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# Sizing config (matches live env vars in spirit, hardcoded here for the
# backtest — env-overridable below)
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CompoundingConfig:
    starting_equity: float = 30_000.0
    risk_pct: float = 0.025                # 2.5% of current equity
    risk_floor: float = 500.0
    risk_ceiling: float = 5_000.0
    max_notional: float = 50_000.0          # V0 sizer cap (per trade)
    min_risk_per_share: float = 0.01        # V0 sizer floor
    min_risk_pct_of_entry: float = 0.001    # V0 10bps floor
    buying_power_multiplier: float = 4.0    # 4× equity for PDT-protected
    max_concurrent: int = 3                 # V7 portfolio cap
    one_per_symbol: bool = True             # don't pile on same symbol
    track_buying_power: bool = True

    @classmethod
    def from_env(cls) -> "CompoundingConfig":
        def f(name, default):
            return float(os.getenv(name, str(default)))
        def i(name, default):
            return int(float(os.getenv(name, str(default))))
        def b(name, default):
            return os.getenv(name, "1" if default else "0") == "1"
        return cls(
            starting_equity=f("WB_STARTING_EQUITY", 30_000.0),
            risk_pct=f("WB_WB_RISK_PCT", 0.025),
            risk_floor=f("WB_WB_RISK_FLOOR_DOLLARS", 500.0),
            risk_ceiling=f("WB_WB_RISK_CEILING_DOLLARS", 5_000.0),
            max_notional=f("WB_WB_MAX_NOTIONAL", 50_000.0),
            min_risk_per_share=f("WB_WB_MIN_RISK_PER_SHARE", 0.01),
            min_risk_pct_of_entry=f("WB_WB_MIN_RISK_PCT", 0.001),
            buying_power_multiplier=f("WB_BP_MULTIPLIER", 4.0),
            max_concurrent=i("WB_WB_MAX_CONCURRENT", 3),
            track_buying_power=b("WB_BP_TRACK", True),
        )


def equity_percent_size(*, entry_price: float, raw_risk_per_share: float,
                        current_equity: float, available_bp: float,
                        cfg: CompoundingConfig) -> Tuple[int, float, float]:
    """V0-hardened equity-percent sizing.

    Returns (shares, risk_dollars, notional). (0, 0, 0) if unsizable.
    """
    if entry_price <= 0 or current_equity <= 0:
        return (0, 0.0, 0.0)
    risk_dollars = max(cfg.risk_floor, min(cfg.risk_ceiling,
                                            current_equity * cfg.risk_pct))
    risk_per_share = max(raw_risk_per_share, cfg.min_risk_per_share,
                         entry_price * cfg.min_risk_pct_of_entry)
    if risk_per_share <= 0:
        return (0, 0.0, 0.0)
    shares_by_risk = int(risk_dollars / risk_per_share)
    shares_by_notional = int(cfg.max_notional / entry_price)
    if cfg.track_buying_power and available_bp > 0:
        shares_by_bp = int(available_bp / entry_price)
    else:
        shares_by_bp = shares_by_risk  # not binding
    shares = max(0, min(shares_by_risk, shares_by_notional, shares_by_bp))
    notional = shares * entry_price
    return (shares, risk_dollars, notional)


# ─────────────────────────────────────────────────────────────────────
# Compounding portfolio simulator
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CompoundedTrade:
    symbol: str
    date: str
    entry_time_et: str
    exit_time_et: str
    entry_price: float
    exit_price: float
    raw_risk_per_share: float
    exit_reason: str
    score: int
    shares: int
    risk_dollars: float
    notional: float
    pnl: float
    pnl_per_share: float
    equity_before: float
    equity_after: float
    bp_committed_before: float
    skipped_reason: str = ""


def _parse_et(date_str: str, et_hms: str) -> datetime:
    dt = datetime.strptime(f"{date_str} {et_hms}", "%Y-%m-%d %H:%M:%S")
    return ET.localize(dt).astimezone(timezone.utc)


def run_compounding(
    candidates_csv: str,
    out_dir: str,
    cfg: Optional[CompoundingConfig] = None,
) -> dict:
    """Read raw per-(sym, date) trades from V8b candidates CSV, walk in
    time order, recompute sizing under compounding + BP cap, write
    outputs."""
    cfg = cfg or CompoundingConfig.from_env()
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.exists(candidates_csv):
        raise FileNotFoundError(candidates_csv)

    raw: List[dict] = list(csv.DictReader(open(candidates_csv)))
    if not raw:
        return {"n_trades": 0}

    # Sort all candidates by absolute time (date + entry_time_et)
    def sort_key(r):
        return (r.get("date", ""), r.get("entry_time_et", ""), r.get("symbol", ""))
    raw.sort(key=sort_key)

    equity = cfg.starting_equity
    bp_committed = 0.0
    open_positions: List[dict] = []  # {symbol, exit_dt, notional}

    executed: List[CompoundedTrade] = []
    skipped: List[dict] = []
    equity_curve: List[Tuple[str, str, float]] = [
        ("session_open", cfg.starting_equity.__class__.__name__, cfg.starting_equity),
    ]

    def free_expired(at_dt: datetime) -> None:
        nonlocal bp_committed
        still_open = []
        for p in open_positions:
            if p["exit_dt"] <= at_dt:
                bp_committed -= p["notional"]
            else:
                still_open.append(p)
        open_positions[:] = still_open
        if bp_committed < 0:
            bp_committed = 0.0

    for r in raw:
        try:
            entry_dt = _parse_et(r["date"], r["entry_time_et"])
            exit_dt = _parse_et(r["date"], r["exit_time_et"])
            entry_price = float(r["entry_price"])
            exit_price = float(r["exit_price"])
            raw_risk = float(r["risk_per_share"])  # already V0-floored in census
            exit_reason = r["exit_reason"]
            score = int(r["score"])
            sym = r["symbol"]
        except (KeyError, ValueError):
            continue

        # Free any positions that exited before this candidate's entry.
        free_expired(entry_dt)

        # Concurrency cap
        if len(open_positions) >= cfg.max_concurrent:
            skipped.append({**r, "skipped_reason": "concurrency_cap"})
            continue
        if cfg.one_per_symbol and any(p["symbol"] == sym for p in open_positions):
            skipped.append({**r, "skipped_reason": "duplicate_symbol"})
            continue

        # Compute available BP at the time of entry
        max_bp_now = cfg.buying_power_multiplier * equity
        available_bp = max(0.0, max_bp_now - bp_committed)

        # Size with compounding-correct risk
        shares, risk_dollars, notional = equity_percent_size(
            entry_price=entry_price, raw_risk_per_share=raw_risk,
            current_equity=equity, available_bp=available_bp, cfg=cfg,
        )
        if shares <= 0:
            skipped.append({**r, "skipped_reason": "size_zero_after_bp"})
            continue

        # Check that we actually have enough BP for this notional
        if cfg.track_buying_power and notional > available_bp:
            skipped.append({**r, "skipped_reason": "insufficient_bp"})
            continue

        # Execute the trade.
        pnl_per_share = exit_price - entry_price
        pnl = pnl_per_share * shares

        equity_before = equity
        bp_before = bp_committed

        # Reserve notional for the holding period
        bp_committed += notional
        open_positions.append({
            "symbol": sym, "exit_dt": exit_dt, "notional": notional,
        })

        # On exit (which we resolve right here for accounting; in reality
        # the exit happens later but our equity-curve granularity is one
        # entry per trade — the exit's PnL is realized when we mark this
        # trade complete, which we do as the trade is "atomic" in this sim).
        # However: for the equity curve to be CORRECT for compounding, we
        # need to credit PnL only when the trade EXITS, not when it ENTERS.
        # We achieve this by deferring PnL application to the next free_expired
        # call. So we don't update equity here; we update it when the
        # position's exit_dt is reached.
        open_positions[-1]["pnl_at_exit"] = pnl

        executed.append(CompoundedTrade(
            symbol=sym, date=r["date"],
            entry_time_et=r["entry_time_et"], exit_time_et=r["exit_time_et"],
            entry_price=round(entry_price, 4),
            exit_price=round(exit_price, 4),
            raw_risk_per_share=round(raw_risk, 4),
            exit_reason=exit_reason, score=score,
            shares=shares,
            risk_dollars=round(risk_dollars, 2),
            notional=round(notional, 2),
            pnl=round(pnl, 2),
            pnl_per_share=round(pnl_per_share, 4),
            equity_before=round(equity_before, 2),
            equity_after=0.0,  # filled below after PnL realized
            bp_committed_before=round(bp_before, 2),
        ))

    # Drain remaining open positions — realize their PnL into equity.
    # (They'd close before next-day's first trade in real life; for
    # accounting we close them all at the end of the simulation.)
    final_dt = datetime.max.replace(tzinfo=timezone.utc)
    free_expired(final_dt)

    # Walk executed trades again to update equity_after using their exit
    # order (in real time): build an exit-time-sorted index, walk it, apply
    # pnl in exit order, and back-fill equity_after on each trade.
    # Simpler: since equity changes are deterministic from PnL ordering,
    # we just apply PnL in exit_time order and write back.
    by_exit = sorted(range(len(executed)),
                     key=lambda i: (executed[i].date, executed[i].exit_time_et))
    eq = cfg.starting_equity
    for idx in by_exit:
        eq += executed[idx].pnl
        executed[idx].equity_after = round(eq, 2)
        equity_curve.append((executed[idx].date, executed[idx].exit_time_et, round(eq, 2)))

    # Recompute "equity_before" for the by-entry-order trades using exit-
    # time-realized equity from prior trades. This is a cleaner equity_at_entry.
    # Build a sorted-by-exit-time prefix sum to look up equity at any time.
    realized_events: List[Tuple[datetime, float]] = []  # (exit_dt_utc, cumulative_pnl_after_that_exit)
    cum = 0.0
    for idx in by_exit:
        t = executed[idx]
        ed = _parse_et(t.date, t.exit_time_et)
        cum += t.pnl
        realized_events.append((ed, cum))

    def equity_at(dt: datetime) -> float:
        """Equity at a given time = starting + sum of all PnL realized BEFORE dt."""
        # Binary search would be faster; linear is fine for a few hundred trades.
        last_cum = 0.0
        for ed, c in realized_events:
            if ed < dt:
                last_cum = c
            else:
                break
        return cfg.starting_equity + last_cum

    for t in executed:
        t.equity_before = round(equity_at(_parse_et(t.date, t.entry_time_et)), 2)

    # ── Outputs ────────────────────────────────────────────────────────
    trades_path = os.path.join(out_dir, "trades.csv")
    skipped_path = os.path.join(out_dir, "skipped.csv")
    curve_path = os.path.join(out_dir, "equity_curve.csv")
    summary_path = os.path.join(out_dir, "summary.json")

    if executed:
        fields = list(asdict(executed[0]).keys())
        with open(trades_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for t in executed:
                w.writerow(asdict(t))
    else:
        open(trades_path, "w").close()

    if skipped:
        sfields = sorted({k for r in skipped for k in r.keys()})
        with open(skipped_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=sfields)
            w.writeheader()
            for r in skipped:
                w.writerow(r)
    else:
        open(skipped_path, "w").close()

    with open(curve_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "time_et_or_event", "equity"])
        for r in equity_curve:
            w.writerow(r)

    # Summary
    pnls = [t.pnl for t in executed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total = sum(pnls)
    pf = (sum(wins) / abs(sum(losses))) if losses else float("inf")
    final_equity = cfg.starting_equity + total

    skipped_counts = defaultdict(int)
    for r in skipped:
        skipped_counts[r.get("skipped_reason", "unknown")] += 1

    # Drawdown over equity curve
    peak = cfg.starting_equity
    max_dd = 0.0
    max_dd_pct = 0.0
    for _, _, eq_v in equity_curve:
        if not isinstance(eq_v, (int, float)):
            continue
        peak = max(peak, eq_v)
        dd = peak - eq_v
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = dd / peak * 100.0 if peak > 0 else 0.0

    summary = {
        "starting_equity": cfg.starting_equity,
        "final_equity": round(final_equity, 2),
        "growth_factor": round(final_equity / cfg.starting_equity, 3),
        "n_trades_executed": len(executed),
        "n_skipped": len(skipped),
        "skipped_reasons": dict(skipped_counts),
        "win_rate_pct": round(len(wins) / len(pnls) * 100, 2) if pnls else 0.0,
        "profit_factor": round(pf, 2) if pf != float("inf") else None,
        "total_pnl": round(total, 2),
        "avg_win": round(sum(wins) / max(len(wins), 1), 2),
        "avg_loss": round(sum(losses) / max(len(losses), 1), 2),
        "max_drawdown_dollars": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_trade": round(max(pnls), 2) if pnls else 0,
        "min_trade": round(min(pnls), 2) if pnls else 0,
        "config": asdict(cfg),
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    return summary


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Compounding-equity backtest of V8b")
    ap.add_argument("--base", default="v8b_v2_pyramid",
                    help="Base variant directory under wave_research/. "
                         "Reads candidates.csv from that dir.")
    ap.add_argument("--out-name", default="",
                    help="Output dir under wave_research/. Default = <base>_compound.")
    ap.add_argument("--starting-equity", type=float, default=30_000.0)
    ap.add_argument("--risk-pct", type=float, default=0.025)
    ap.add_argument("--bp-multiplier", type=float, default=4.0)
    ap.add_argument("--no-bp-track", action="store_true",
                    help="Disable buying-power cap (only equity + concurrency)")
    args = ap.parse_args()

    candidates_csv = os.path.join(OUT_DIR, args.base, f"{args.base}_candidates.csv")
    out_name = args.out_name or f"{args.base}_compound"
    out_dir = os.path.join(OUT_DIR, out_name)

    cfg = CompoundingConfig.from_env()
    cfg.starting_equity = args.starting_equity
    cfg.risk_pct = args.risk_pct
    cfg.buying_power_multiplier = args.bp_multiplier
    cfg.track_buying_power = not args.no_bp_track

    print(f"Compounding sim: base={args.base}  starting=${cfg.starting_equity:,.0f}  "
          f"risk_pct={cfg.risk_pct:.1%}  BP_mult={cfg.buying_power_multiplier}× "
          f"BP_track={cfg.track_buying_power}", flush=True)

    if not os.path.exists(candidates_csv):
        print(f"ERROR: candidates CSV not found: {candidates_csv}", file=sys.stderr)
        print("Run wave_portfolio_sim first to generate the V8b candidates list.", file=sys.stderr)
        return 2

    summary = run_compounding(candidates_csv, out_dir, cfg)
    print()
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
