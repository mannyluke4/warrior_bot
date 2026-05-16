"""PDH-Fade-with-L2 synthetic backtest — Wave 5 Agent N.

Re-runs the Wave-3 PDH-Fade strategy on the same 36-symbol shortlist and
date range, but filters each candidate entry through the synthetic-L2
``depth_imbalance`` confirmation gate.

Honest framing
==============

L2 historical data is NOT in our Databento Standard subscription.  This
script feeds the L2 plugin with SYNTHETIC depth derived from candle
wick asymmetry + bar volume (see ``backtest/synthetic_l2.py``).  Results
are directional intuition only — not validated edge.  Real validation
is queued for Wave 6 once live L2 capture is in place.

Approach
========

1. Load the already-archived Wave-3 PDH-Fade trade log
   (``backtest_archive/wave3_portfolio/trades_PDH-PDL-Fade_fixed_dollar.parquet``).
2. For each trade, reconstruct the 1m bar that triggered the entry
   (the bar BEFORE ``entry_ts`` — entry fills at next bar's open per
   the Wave-3 fill model).
3. Synthesize the L2 state from that bar (+ prior bar for vacuum) via
   ``synth_l2_state``.
4. Run the trade through ``L2Confirm(mode='depth_imbalance',
   min_imbalance=1.5)`` with direction inferred from the level kind.
5. Keep only trades where L2 confirmed.

Sharpe is computed identically to Wave-3 (per-trade return = pnl /
risk_dollars; annualized scaling factor 252 ** 0.5 over per-trade
sequence).  This isn't the same as session-level Sharpe used in the
production validation gates, but it's the same convention used in
``2026-05-16_wave3_portfolio_backtest.md``, so the deltas are
comparable.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from backtest.synthetic_l2 import SyntheticL2Config, synth_l2_state
from framework.confirmations.l2_confirm import L2Confirm
from framework.level_sources.base import Bar, Level


REPO = Path("/Users/duffy/warrior_bot_v2")
TRADES_PARQUET = REPO / "backtest_archive/wave3_portfolio/trades_PDH-PDL-Fade_fixed_dollar.parquet"
CACHE_ROOT = REPO / "tick_cache_databento"
OUTPUT_DIR = REPO / "backtest_archive" / "wave5_l2_synth"


# ---------------------------------------------------------------------------
# Bar loading (shared shape with portfolio_backtest.py)
# ---------------------------------------------------------------------------


def load_day_bars(symbol: str, session_date: date) -> list[Bar]:
    fp = CACHE_ROOT / symbol / f"1m_{session_date.isoformat()}.parquet"
    if not fp.exists():
        return []
    try:
        df = pd.read_parquet(fp)
    except Exception:
        return []
    if df.empty:
        return []
    bars: list[Bar] = []
    for row in df.itertuples(index=False):
        ts = pd.Timestamp(row.ts_event).to_pydatetime()
        try:
            bars.append(
                Bar(
                    timestamp=ts,
                    open=float(row.open),
                    high=float(row.high),
                    low=float(row.low),
                    close=float(row.close),
                    volume=float(row.volume),
                    symbol=symbol,
                )
            )
        except (ValueError, TypeError):
            continue
    return bars


# ---------------------------------------------------------------------------
# L2 filter
# ---------------------------------------------------------------------------


def trigger_bar_for_trade(
    bars: list[Bar], entry_ts: datetime
) -> tuple[Optional[Bar], Optional[Bar]]:
    """Find the bar that fired the rejection (bar BEFORE entry_ts) and its prior."""
    if not bars:
        return None, None
    target_ts = entry_ts
    # entry fills at next-bar open per Wave-3 fill model.  The trigger bar
    # is therefore the one whose timestamp is the bar before entry_ts.
    for i, b in enumerate(bars):
        if b.timestamp >= target_ts:
            if i == 0:
                return None, None
            trigger = bars[i - 1]
            prior = bars[i - 2] if i >= 2 else None
            return trigger, prior
    return None, None


def apply_l2_filter(
    trades: pd.DataFrame,
    l2c: L2Confirm,
    *,
    config: Optional[SyntheticL2Config] = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """Return trades that pass synthetic-L2 confirmation."""
    keep_idx: list[int] = []
    confirmed_count = 0
    rejected_count = 0
    no_data_count = 0
    cache_by_key: dict[tuple[str, date], list[Bar]] = {}

    for idx, row in trades.iterrows():
        sym = row["symbol"]
        sess_d = pd.Timestamp(row["session_date"]).date()
        cache_key = (sym, sess_d)
        bars = cache_by_key.get(cache_key)
        if bars is None:
            bars = load_day_bars(sym, sess_d)
            cache_by_key[cache_key] = bars
        if not bars:
            no_data_count += 1
            continue

        entry_ts = pd.Timestamp(row["entry_ts"]).to_pydatetime()
        if entry_ts.tzinfo is None and bars[0].timestamp.tzinfo is not None:
            # Some parquets have tz, some don't.  Strip tz so comparison works.
            entry_ts = entry_ts.replace(tzinfo=bars[0].timestamp.tzinfo)
        elif entry_ts.tzinfo is not None and bars[0].timestamp.tzinfo is None:
            entry_ts = entry_ts.replace(tzinfo=None)

        trigger, prior = trigger_bar_for_trade(bars, entry_ts)
        if trigger is None:
            no_data_count += 1
            continue

        # Direction matches the trade.  Build a level proxy of the right kind.
        direction = str(row["direction"])
        # PDH/PDL is the level the trade fades.  For a fade long (PDL fade),
        # the trade entry direction is "long" and the level is PDL.
        # For a fade short (PDH fade), entry is "short" and level is PDH.
        lvl_kind = "PDL" if direction == "long" else "PDH"
        lvl_price = float(row["entry_price"])  # approx — exact level not in record
        level = Level(
            price=lvl_price, kind=lvl_kind, session_date=sess_d
        )

        synth_state = synth_l2_state(trigger, prior_bar=prior, config=config)
        res = l2c.check_confirmation(level=level, bars=[trigger], l2_state=synth_state)
        if res.confirmed:
            keep_idx.append(idx)
            confirmed_count += 1
            if verbose and confirmed_count <= 3:
                print(f"  KEEP {sym} {sess_d} {direction}: {res.reason}")
        else:
            rejected_count += 1
            if verbose and rejected_count <= 3:
                print(f"  DROP {sym} {sess_d} {direction}: {res.reason}")

    print(
        f"L2 filter results: confirmed={confirmed_count}, "
        f"rejected={rejected_count}, no_data={no_data_count}, "
        f"total_input={len(trades)}"
    )
    return trades.loc[keep_idx].copy()


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def annualized_sharpe(returns: pd.Series) -> float:
    """Sharpe with the Wave-3 convention: per-trade R-multiple, sqrt(252) scaling."""
    if len(returns) < 2:
        return float("nan")
    mu = returns.mean()
    sd = returns.std(ddof=1)
    if sd <= 0 or not math.isfinite(sd):
        return float("nan")
    return float(mu / sd * math.sqrt(252))


def max_drawdown(equity: pd.Series) -> float:
    if len(equity) == 0:
        return 0.0
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return float(dd.min())


def compute_metrics(trades: pd.DataFrame, starting_equity: float = 100_000.0) -> dict[str, Any]:
    if trades.empty:
        return {
            "n_trades": 0,
            "sharpe": float("nan"),
            "total_pnl": 0.0,
            "win_rate": float("nan"),
            "avg_r": float("nan"),
            "profit_factor": float("nan"),
            "max_drawdown_pct": float("nan"),
        }
    t = trades.copy()
    t = t.sort_values("entry_ts")
    r = t["r_multiple"].astype(float)
    pnl = t["pnl"].astype(float)
    wins = (pnl > 0).sum()
    losses = (pnl <= 0).sum()
    gross_win = pnl[pnl > 0].sum()
    gross_loss = -pnl[pnl <= 0].sum()
    pf = float(gross_win / gross_loss) if gross_loss > 0 else float("inf")

    equity = starting_equity + pnl.cumsum()
    mdd = max_drawdown(equity)

    return {
        "n_trades": int(len(t)),
        "sharpe": annualized_sharpe(r),
        "total_pnl": float(pnl.sum()),
        "win_rate": float(wins / max(1, wins + losses)),
        "avg_r": float(r.mean()),
        "profit_factor": pf,
        "max_drawdown_pct": float(mdd * 100.0),
    }


# ---------------------------------------------------------------------------
# CLI driver
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="PDH-Fade with synthetic L2 — Wave 5 N")
    ap.add_argument("--min-imbalance", type=float, default=1.5)
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--max-spread-pct", type=float, default=1.0)
    ap.add_argument("--mode", default="depth_imbalance",
                    choices=["depth_imbalance", "stacked_bids", "stacked_asks", "momentum_vacuum"])
    ap.add_argument("--vacuum-drop-pct", type=float, default=0.50)
    ap.add_argument("--stack-size-threshold", type=float, default=1000.0)
    ap.add_argument("--stack-levels-required", type=int, default=3)
    ap.add_argument("--year-filter", type=int, default=None,
                    help="If set, only run trades from this year")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=OUTPUT_DIR)
    args = ap.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[wave5/N] Loading PDH-Fade trades from {TRADES_PARQUET}")
    if not TRADES_PARQUET.exists():
        print(f"ERROR: trades parquet not found at {TRADES_PARQUET}", file=sys.stderr)
        return 2

    df = pd.read_parquet(TRADES_PARQUET)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"])
    df["session_date"] = pd.to_datetime(df["session_date"]).dt.date

    if args.year_filter:
        df = df[pd.to_datetime(df["entry_ts"]).dt.year == args.year_filter].copy()
        print(f"[wave5/N] Filtered to year {args.year_filter}: {len(df)} trades")

    print(f"[wave5/N] Baseline (no L2): {len(df)} trades")
    baseline = compute_metrics(df)
    print(f"  baseline metrics: {json.dumps(baseline, indent=2, default=str)}")

    l2c = L2Confirm(
        mode=args.mode,
        min_imbalance=args.min_imbalance,
        top_n=args.top_n,
        stack_size_threshold=args.stack_size_threshold,
        stack_levels_required=args.stack_levels_required,
        vacuum_drop_pct=args.vacuum_drop_pct,
        max_spread_pct=args.max_spread_pct,
        pass_through_on_missing=False,
    )

    print(f"[wave5/N] Applying synthetic L2 filter "
          f"(mode={args.mode}, min_imbalance={args.min_imbalance})...")
    df_l2 = apply_l2_filter(df, l2c, verbose=args.verbose)
    print(f"[wave5/N] With synthetic L2: {len(df_l2)} trades "
          f"(reduction: {100 * (1 - len(df_l2) / max(1, len(df))):.1f}%)")
    l2_metrics = compute_metrics(df_l2)
    print(f"  L2 metrics: {json.dumps(l2_metrics, indent=2, default=str)}")

    # Save outputs
    out_tag = (f"{args.mode}_imb{args.min_imbalance}"
               + (f"_y{args.year_filter}" if args.year_filter else "_all"))
    df_l2.to_parquet(args.out_dir / f"pdh_fade_l2_{out_tag}.parquet")
    summary = {
        "config": {
            "mode": args.mode,
            "min_imbalance": args.min_imbalance,
            "top_n": args.top_n,
            "max_spread_pct": args.max_spread_pct,
            "year_filter": args.year_filter,
        },
        "baseline": baseline,
        "with_l2": l2_metrics,
        "trade_count_reduction_pct": (
            100 * (1 - len(df_l2) / max(1, len(df)))
        ),
        "sharpe_delta": (l2_metrics["sharpe"] - baseline["sharpe"])
            if math.isfinite(l2_metrics["sharpe"])
            and math.isfinite(baseline["sharpe"])
            else None,
    }
    summary_path = args.out_dir / f"summary_{out_tag}.json"
    with summary_path.open("w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"[wave5/N] Wrote {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
