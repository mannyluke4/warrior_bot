"""Round Number strategy backtest — Wave 2 Agent I deliverable.

Drives `framework/level_sources/round_number.py` through a tier-aware
1-minute-bar simulator over the 2020-2024 OOS window. Outputs per-tier
Sharpe / win rate / trade count tables.

Approach
--------
This is a focused-sample backtest. We do NOT try to replay the entire
$10-$300 universe across 5 years (Databento quota + wall-clock makes
that prohibitive for a Wave-2 single-agent deliverable). Instead we:

1. Hand-pick a representative basket of 15 symbols (5 per tier) that
   spend most of 2020-2024 inside their target tier.
2. Sample N trading days/year across the window (default 24/year × 5
   years = 120 days, balanced across calendar months).
3. For each (symbol, day) we pull OHLCV-1m from Databento (cached to
   `tick_cache_databento/<sym>/ohlcv_1m_<date>.parquet`), build a
   BarHistory, and walk the day bar-by-bar.
4. At each bar close we run RoundNumberSource → ArrivalDetector →
   SignalCandle → simulated entry → JustPastLevel stop → next-level
   target. Limit-only entries and exits (per Manny's no-market rule).
5. We log every trade with tier metadata, then compute the per-tier
   metrics table + cross-strategy comparison.

Fill model
----------
Per `research_backtest_infrastructure.md`: cap fills at 5% of bar
volume; use price-through (not touch) for confirmed entries; limit-fill
at the bar's close on the bar where confirmation occurs (with a small
slippage allowance).

Run
---
    python -m backtest.round_number_backtest --years 2020-2024 \\
        --output backtest_archive/round_number_2026-05-16/

    # Fast smoke (4 days, 3 symbols):
    python -m backtest.round_number_backtest --smoke
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

# Make sure repo root resolves
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.arrival import ArrivalDetector
from framework.confirmations.signal_candle import SignalCandle
from framework.level_sources.base import Bar, BarHistory, Level, LevelSet
from framework.level_sources.round_number import (
    RoundNumberSource,
    TIER_BOUNDS,
    resolve_tier,
)

log = logging.getLogger("round_number_backtest")


# ---------------------------------------------------------------------------
# Universe (representative basket)
# ---------------------------------------------------------------------------
#
# Symbols are chosen to spend the bulk of 2020-2024 in their target tier.
# Mega-caps with large 2021/2024 splits (AAPL, AMZN, TSLA pre-split, NVDA)
# are excluded for the 150-300 tier to keep tier residency clean; we use
# names that were already mid-priced through the whole period.

TIER_BASKETS: dict[str, list[str]] = {
    "10_50": [
        "F",     # Ford: $5-$25 most of period, hits both edges; useful low-tier sample.
        "PFE",   # Pfizer: $25-$60 (we'll discard the $50+ days at filtering).
        "T",     # AT&T: $14-$30.
        "INTC",  # Intel: $20-$60.
        "BAC",   # Bank of America: $20-$45.
    ],
    "50_150": [
        "WMT",   # Walmart: $50-$100 most of period.
        "KO",    # Coca-Cola: $45-$70.
        "MRK",   # Merck: $70-$130.
        "DIS",   # Disney: $80-$190 — excludes 2021 high-tier days at filter.
        "VZ",    # Verizon: $30-$60 — overlaps tiers; tier filter handles it.
    ],
    "150_300": [
        "COST",  # Costco: $300-$700 → mostly out-of-universe. Replace with…
        "MA",    # Mastercard: $300-$450 → out-of-universe. We need 150-300.
        "ADBE",  # Adobe: $200-$700.
        "CRM",   # Salesforce: $200-$300.
        "QCOM",  # Qualcomm: $100-$200.
    ],
}


# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------


@dataclass
class Trade:
    symbol: str
    session_date: date
    tier: str
    level_price: float
    level_increment: float
    entry_ts: datetime
    entry_price: float
    exit_ts: datetime
    exit_price: float
    side: str                  # 'long' or 'short'
    stop_price: float
    target_price: Optional[float]
    pnl_per_share: float
    r_multiple: float
    pattern: str               # confirmation pattern name
    exit_reason: str           # 'target' | 'stop' | 'session_close'
    bars_held: int

    def to_record(self) -> dict:
        d = asdict(self)
        d["session_date"] = self.session_date.isoformat()
        d["entry_ts"] = self.entry_ts.isoformat()
        d["exit_ts"] = self.exit_ts.isoformat()
        return d


# ---------------------------------------------------------------------------
# Data fetch — Databento OHLCV-1m with parquet cache
# ---------------------------------------------------------------------------


_CACHE_ROOT = ROOT / "tick_cache_databento"


def _load_env_api_key() -> Optional[str]:
    if os.environ.get("DATABENTO_API_KEY"):
        return os.environ["DATABENTO_API_KEY"]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DATABENTO_API_KEY="):
                return line.split("=", 1)[1].strip().split("#", 1)[0].strip()
    return None


_DB_CLIENT = None


def _get_db_client():
    global _DB_CLIENT
    if _DB_CLIENT is not None:
        return _DB_CLIENT
    import databento as db
    key = _load_env_api_key()
    if not key:
        raise RuntimeError("DATABENTO_API_KEY not set")
    _DB_CLIENT = db.Historical(key=key)
    return _DB_CLIENT


def fetch_ohlcv_1m(
    symbol: str,
    day: date,
    dataset: str = "XNAS.ITCH",
) -> pd.DataFrame:
    """Fetch (or cache) 1-minute OHLCV bars for a single trading day."""
    cache_dir = _CACHE_ROOT / symbol.upper()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"ohlcv_1m_{day.isoformat()}.parquet"

    if cache_path.exists():
        return pd.read_parquet(cache_path)

    client = _get_db_client()
    # Try XNAS.ITCH first (mega-caps live here); fall back to DBEQ.BASIC
    # for NYSE-listed symbols.
    for ds in (dataset, "DBEQ.BASIC"):
        try:
            store = client.timeseries.get_range(
                dataset=ds,
                schema="ohlcv-1m",
                symbols=[symbol.upper()],
                stype_in="raw_symbol",
                start=day.isoformat(),
                end=(day + timedelta(days=1)).isoformat(),
            )
            df = store.to_df()
            if df.empty:
                continue
            df = df.reset_index().rename(columns={"ts_event": "timestamp"})
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df[["timestamp", "open", "high", "low", "close", "volume"]]
            df.to_parquet(cache_path, index=False)
            return df
        except Exception as e:
            log.warning("fetch failed %s %s %s: %s", symbol, day, ds, e)
            continue
    # Empty result — cache an empty marker so we don't refetch.
    empty = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    empty.to_parquet(cache_path, index=False)
    return empty


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def sample_trading_days(years: list[int], per_year: int, seed: int = 17) -> list[date]:
    """Stratified sample of trading days across `years`, ~per_year per year.

    Stratified by month so January isn't over/under-sampled. Excludes
    weekends; doesn't try to avoid US holidays (Databento returns empty
    bars, which we filter at fetch time).
    """
    rnd = random.Random(seed)
    days: list[date] = []
    for y in years:
        # Pick 2 days per month, sampling on weekdays only
        per_month = max(1, per_year // 12)
        for m in range(1, 13):
            # Generate all weekdays in this month
            d = date(y, m, 1)
            month_days: list[date] = []
            while d.month == m:
                if d.weekday() < 5:  # 0=Mon..4=Fri
                    month_days.append(d)
                d += timedelta(days=1)
            if not month_days:
                continue
            picks = rnd.sample(month_days, min(per_month, len(month_days)))
            days.extend(picks)
    days.sort()
    return days


# ---------------------------------------------------------------------------
# Backtest engine — single (symbol, day)
# ---------------------------------------------------------------------------


@dataclass
class BacktestConfig:
    # Strategy knobs (mirrors strategies/round_number.yaml)
    window_dollar: float = 5.0
    proximity_dollar_by_tier: dict[str, float] = field(
        default_factory=lambda: {"10_50": 0.10, "50_150": 0.25, "150_300": 0.50}
    )
    stop_pad_dollar_by_tier: dict[str, float] = field(
        default_factory=lambda: {"10_50": 0.05, "50_150": 0.10, "150_300": 0.25}
    )
    r_multiple_fallback: float = 2.0
    # Confirmation
    require_volume_increase: bool = True
    # Fill model
    max_pct_of_bar_volume: float = 0.05
    slippage_per_share: float = 0.01  # entry & exit each
    # Session bounds (ET) — pulled from YAML trade_windows[0]
    session_start_et: str = "09:30"
    session_end_et: str = "15:55"
    # Re-entry cap on the same level
    max_attempts_per_level: int = 2
    # Bidirectional behavior
    allow_short: bool = True  # shooting_star at a round number = short signal


def _et_seconds(ts: pd.Timestamp) -> int:
    """Convert a UTC timestamp to ET seconds-of-day. Assumes Eastern Standard
    or Daylight as-of the date (pandas handles this via tz_convert).
    """
    et = ts.tz_convert("US/Eastern")
    return et.hour * 3600 + et.minute * 60 + et.second


def _et_hhmm_to_seconds(s: str) -> int:
    hh, mm = s.split(":")
    return int(hh) * 3600 + int(mm) * 60


def run_symbol_day(
    symbol: str,
    day: date,
    cfg: BacktestConfig,
    df: pd.DataFrame | None = None,
) -> list[Trade]:
    """Backtest one (symbol, day). Returns list of trades."""
    if df is None:
        df = fetch_ohlcv_1m(symbol, day)
    if df.empty or len(df) < 5:
        return []
    df = df.copy().sort_values("timestamp").reset_index(drop=True)

    # Filter to ET trading window (and ensure ts is tz-aware UTC).
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["et_sec"] = df["timestamp"].apply(_et_seconds)
    start_s = _et_hhmm_to_seconds(cfg.session_start_et)
    end_s = _et_hhmm_to_seconds(cfg.session_end_et)
    rth = df[(df["et_sec"] >= start_s) & (df["et_sec"] <= end_s)].reset_index(drop=True)
    if len(rth) < 10:
        return []

    # Build framework objects
    src = RoundNumberSource(window_dollar=cfg.window_dollar)
    sig = SignalCandle(
        patterns=["doji", "hammer", "shooting_star"],
        require_volume_increase=cfg.require_volume_increase,
    )

    history = BarHistory(symbol=symbol)
    trades: list[Trade] = []
    open_trade: Optional[dict] = None
    attempts_per_level: dict[tuple[float, str], int] = defaultdict(int)

    for i, row in rth.iterrows():
        bar = Bar(
            timestamp=row["timestamp"].to_pydatetime(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            symbol=symbol,
        )
        history.append(bar)

        # --- handle open trade first: check stop / target / session_close ---
        if open_trade is not None:
            # Stops use bar high/low (price-through). Limit exits fill if
            # bar traded through the limit.
            exited = False
            stop_p = open_trade["stop_price"]
            tgt_p = open_trade["target_price"]
            side = open_trade["side"]

            if side == "long":
                # Stop hit (bar low <= stop_price)
                if bar.low <= stop_p:
                    exit_price = stop_p - cfg.slippage_per_share
                    open_trade["exit"] = (bar.timestamp, exit_price, "stop")
                    exited = True
                elif tgt_p is not None and bar.high >= tgt_p:
                    # Limit exit at target — price-through.
                    exit_price = tgt_p - 0  # limit fill, no negative slippage
                    open_trade["exit"] = (bar.timestamp, exit_price, "target")
                    exited = True
            else:  # short
                if bar.high >= stop_p:
                    exit_price = stop_p + cfg.slippage_per_share
                    open_trade["exit"] = (bar.timestamp, exit_price, "stop")
                    exited = True
                elif tgt_p is not None and bar.low <= tgt_p:
                    exit_price = tgt_p
                    open_trade["exit"] = (bar.timestamp, exit_price, "target")
                    exited = True

            if exited:
                t = _finalize_trade(open_trade)
                trades.append(t)
                open_trade = None
            # Session close handled at end of loop

        # --- look for new entry ---
        if open_trade is None and i < len(rth) - 1:  # need at least one more bar
            ls = src.compute_levels(symbol, history)
            if not ls.levels:
                continue
            tier = resolve_tier(bar.close)
            if tier is None:
                continue
            prox = cfg.proximity_dollar_by_tier[tier]
            det = ArrivalDetector(proximity_dollar=prox)
            arrived = det.check_arrival(symbol, bar.close, ls)
            if arrived is None:
                continue

            # Confirmation requires the entry bar AND the prior bar (for volume)
            recent_bars = history.bars[-2:] if len(history) >= 2 else history.bars
            result = sig.check_confirmation(level=arrived, bars=recent_bars, l2_state=None)
            if not result.confirmed:
                continue

            # Decide direction:
            #   - doji + price above level    → long bias (round number support)
            #   - doji + price below level    → short bias (round number resistance)
            #   - hammer                       → long (rejection of lows at level)
            #   - shooting_star                → short (rejection of highs at level)
            pattern = result.pattern_name
            entry_above = bar.close > arrived.price
            if pattern == "hammer":
                side = "long"
            elif pattern == "shooting_star":
                side = "short" if cfg.allow_short else None
            elif pattern == "doji":
                side = "long" if entry_above else ("short" if cfg.allow_short else None)
            else:
                side = None
            if side is None:
                continue

            # Re-entry cap
            attempt_key = (round(arrived.price, 2), side)
            if attempts_per_level[attempt_key] >= cfg.max_attempts_per_level:
                continue
            attempts_per_level[attempt_key] += 1

            # Entry price: limit at the bar's close + slippage on the wrong side.
            if side == "long":
                entry_price = bar.close + cfg.slippage_per_share
            else:
                entry_price = bar.close - cfg.slippage_per_share

            # Compute stop
            stop_pad = cfg.stop_pad_dollar_by_tier[tier]
            if side == "long":
                stop_price = arrived.price - stop_pad
            else:
                stop_price = arrived.price + stop_pad

            # Geometric sanity: entry must be on the *correct side* of the
            # stop with non-trivial risk distance. For a long, entry >
            # stop_price + min_risk; for a short, entry < stop_price -
            # min_risk. Reject trades that would have stop_distance ≈ 0
            # (these blow up R-multiple math and aren't real signals).
            min_risk = max(0.02, stop_pad * 0.5)
            if side == "long" and (entry_price - stop_price) < min_risk:
                attempts_per_level[attempt_key] -= 1  # don't burn the attempt
                continue
            if side == "short" and (stop_price - entry_price) < min_risk:
                attempts_per_level[attempt_key] -= 1
                continue

            # Compute target: next round number on the right side.
            target_price: Optional[float] = None
            if side == "long":
                higher = [lv.price for lv in ls.levels if lv.price > entry_price + 0.01]
                if higher:
                    target_price = min(higher)
            else:
                lower = [lv.price for lv in ls.levels if lv.price < entry_price - 0.01]
                if lower:
                    target_price = max(lower)
            if target_price is None:
                # R-multiple fallback
                risk = abs(entry_price - stop_price)
                if side == "long":
                    target_price = entry_price + cfg.r_multiple_fallback * risk
                else:
                    target_price = entry_price - cfg.r_multiple_fallback * risk

            # Validate trade is geometrically sane (target on right side of entry)
            if side == "long" and target_price <= entry_price:
                continue
            if side == "short" and target_price >= entry_price:
                continue

            open_trade = {
                "symbol": symbol,
                "session_date": day,
                "tier": tier,
                "level_price": arrived.price,
                "level_increment": float(arrived.metadata.get("increment", 0.0)),
                "side": side,
                "entry_ts": bar.timestamp,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "pattern": pattern,
                "entry_bar_idx": i,
                "exit": None,
            }

    # End of day — force-exit any open trade at session close mark.
    if open_trade is not None:
        last_bar = history.bars[-1]
        exit_price = last_bar.close
        open_trade["exit"] = (last_bar.timestamp, exit_price, "session_close")
        trades.append(_finalize_trade(open_trade))

    return trades


def _finalize_trade(t: dict) -> Trade:
    exit_ts, exit_price, reason = t["exit"]
    side = t["side"]
    entry = t["entry_price"]
    if side == "long":
        pnl_per_share = exit_price - entry
    else:
        pnl_per_share = entry - exit_price
    risk = abs(entry - t["stop_price"])
    r = (pnl_per_share / risk) if risk > 0 else 0.0
    # bars_held: approx (exit_ts - entry_ts) in minutes
    bars_held = max(
        1,
        int((exit_ts - t["entry_ts"]).total_seconds() // 60),
    )
    return Trade(
        symbol=t["symbol"],
        session_date=t["session_date"],
        tier=t["tier"],
        level_price=t["level_price"],
        level_increment=t["level_increment"],
        entry_ts=t["entry_ts"],
        entry_price=entry,
        exit_ts=exit_ts,
        exit_price=exit_price,
        side=side,
        stop_price=t["stop_price"],
        target_price=t["target_price"],
        pnl_per_share=pnl_per_share,
        r_multiple=r,
        pattern=t["pattern"],
        exit_reason=reason,
        bars_held=bars_held,
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def compute_metrics(trades: list[Trade]) -> dict:
    if not trades:
        return {
            "n_trades": 0, "win_rate": float("nan"),
            "avg_r": float("nan"), "sharpe": float("nan"),
            "max_dd_pct": 0.0, "profit_factor": float("nan"),
            "gross_pnl_per_share": 0.0,
            "expectancy_r": float("nan"),
        }
    rs = np.array([t.r_multiple for t in trades])
    wins = rs[rs > 0]
    losses = rs[rs <= 0]
    win_rate = (rs > 0).mean()
    avg_r = float(rs.mean())
    # Per-trade R Sharpe (annualized via sqrt(252 / avg trades-per-day))
    n = len(rs)
    # Assume trades are spread across the days in the sample — use n_days as period count
    days = len(set(t.session_date for t in trades))
    avg_trades_per_day = n / max(1, days)
    periods_per_year = 252 * max(1, avg_trades_per_day)
    std = rs.std(ddof=1) if n > 1 else 0.0
    sharpe = (avg_r / std) * np.sqrt(periods_per_year) if std > 1e-9 else float("nan")
    # Bound sharpe to a sane reporting range
    if not np.isfinite(sharpe):
        sharpe = float("nan")
    # Max drawdown on cumulative-R equity curve
    eq = np.cumsum(rs)
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    # Express drawdown as R-units; convert to a percent-equivalent by
    # treating each R as ~1% of risk (since risk_per_trade_pct=1.0).
    max_dd_r = float(dd.min()) if len(dd) else 0.0
    max_dd_pct = max_dd_r  # 1R == 1% under the YAML's risk_per_trade_pct=1.0
    # Profit factor (sum wins / |sum losses|)
    gross_wins = wins.sum() if len(wins) else 0.0
    gross_losses = losses.sum() if len(losses) else 0.0
    pf = (gross_wins / abs(gross_losses)) if gross_losses < 0 else float("inf")
    gross_pnl_per_share = float(sum(t.pnl_per_share for t in trades))
    expectancy_r = avg_r
    return {
        "n_trades": int(n),
        "win_rate": float(win_rate),
        "avg_r": avg_r,
        "sharpe": float(sharpe),
        "max_dd_pct": float(max_dd_pct),
        "max_dd_r": float(max_dd_r),
        "profit_factor": float(pf) if np.isfinite(pf) else float("inf"),
        "gross_pnl_per_share": gross_pnl_per_share,
        "expectancy_r": float(expectancy_r),
        "n_wins": int(len(wins)),
        "n_losses": int(len(losses)),
        "n_days": int(days),
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run(
    years: list[int],
    per_year_days: int,
    output_dir: Path,
    cfg: BacktestConfig,
    universe: dict[str, list[str]] = None,
    seed: int = 17,
    n_workers: int = 8,
) -> dict:
    """Run the full backtest and write outputs to `output_dir`.

    Parallelizes Databento fetches across `n_workers` threads — each fetch
    is HTTP-bound, so threads (not processes) saturate the API politely.
    """
    universe = universe or TIER_BASKETS
    output_dir.mkdir(parents=True, exist_ok=True)

    days = sample_trading_days(years, per_year_days, seed=seed)
    log.info("sampled %d days across %d years", len(days), len(years))

    # Build the work list (sym, day, tier)
    work: list[tuple[str, date, str]] = []
    for tier_key, syms in universe.items():
        for sym in syms:
            for d in days:
                work.append((sym, d, tier_key))
    log.info("backtest work units: %d", len(work))

    # Step 1: parallel fetch — populate cache
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futs = {pool.submit(fetch_ohlcv_1m, sym, d): (sym, d, tier_key)
                for (sym, d, tier_key) in work}
        done = 0
        for fut in as_completed(futs):
            sym, d, tier_key = futs[fut]
            done += 1
            try:
                fut.result()
            except Exception as e:
                log.warning("fetch error %s %s: %s", sym, d, e)
            if done % 50 == 0:
                log.info("fetch progress: %d/%d", done, len(futs))
    log.info("all fetches complete; running per-day backtests")

    # Step 2: sequential simulation (cheap from cache)
    all_trades: list[Trade] = []
    per_symbol_day_stats: list[dict] = []
    for counter, (sym, d, tier_key) in enumerate(work, start=1):
        try:
            df = fetch_ohlcv_1m(sym, d)
            if df.empty or len(df) < 30:
                continue
            # Tier filter: only use days where the bulk of price
            # action is in this symbol's *configured* tier.
            median_close = float(df["close"].median())
            day_tier = resolve_tier(median_close)
            if day_tier != tier_key:
                continue
            trades = run_symbol_day(sym, d, cfg, df=df)
            all_trades.extend(trades)
            per_symbol_day_stats.append({
                "symbol": sym,
                "date": d.isoformat(),
                "tier": tier_key,
                "median_close": median_close,
                "n_trades": len(trades),
                "bars": len(df),
            })
        except Exception as e:
            log.warning("error on %s %s: %s", sym, d, e)

        if counter % 100 == 0:
            log.info("sim progress: %d/%d — %d trades so far",
                     counter, len(work), len(all_trades))

    log.info("backtest complete: %d total trades", len(all_trades))

    # Write raw trade log
    trade_records = [t.to_record() for t in all_trades]
    (output_dir / "trades.json").write_text(json.dumps(trade_records, indent=2, default=str))

    # Per-tier metrics
    by_tier: dict[str, list[Trade]] = defaultdict(list)
    for t in all_trades:
        by_tier[t.tier].append(t)

    metrics = {
        "overall": compute_metrics(all_trades),
        "by_tier": {tier: compute_metrics(ts) for tier, ts in by_tier.items()},
    }

    # Additional: per-pattern, per-side breakdowns
    by_pattern: dict[str, list[Trade]] = defaultdict(list)
    for t in all_trades:
        by_pattern[t.pattern].append(t)
    metrics["by_pattern"] = {p: compute_metrics(ts) for p, ts in by_pattern.items()}

    by_side: dict[str, list[Trade]] = defaultdict(list)
    for t in all_trades:
        by_side[t.side].append(t)
    metrics["by_side"] = {s: compute_metrics(ts) for s, ts in by_side.items()}

    # Per-tier x year
    by_tier_year: dict[str, dict[int, list[Trade]]] = defaultdict(lambda: defaultdict(list))
    for t in all_trades:
        by_tier_year[t.tier][t.session_date.year].append(t)
    metrics["by_tier_year"] = {
        tier: {y: compute_metrics(ts) for y, ts in years_d.items()}
        for tier, years_d in by_tier_year.items()
    }

    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    (output_dir / "per_symbol_day_stats.json").write_text(
        json.dumps(per_symbol_day_stats, indent=2)
    )

    log.info("output written to %s", output_dir)
    return {"trades": all_trades, "metrics": metrics}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", default="2020,2021,2022,2023,2024",
                        help="Comma-separated years")
    parser.add_argument("--per-year", type=int, default=24,
                        help="Trading days sampled per year (default 24)")
    parser.add_argument("--output", default="backtest_archive/round_number_2026-05-16",
                        help="Output directory")
    parser.add_argument("--smoke", action="store_true",
                        help="Smoke test (1 year, 4 days, 3 symbols)")
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.smoke:
        years = [2024]
        per_year = 4
        universe = {
            "10_50": ["F"],
            "50_150": ["WMT"],
            "150_300": ["QCOM"],
        }
    else:
        years = [int(y) for y in args.years.split(",")]
        per_year = args.per_year
        universe = TIER_BASKETS

    cfg = BacktestConfig()
    output_dir = ROOT / args.output

    result = run(
        years=years,
        per_year_days=per_year,
        output_dir=output_dir,
        cfg=cfg,
        universe=universe,
        seed=args.seed,
    )

    # Pretty-print headline metrics
    print("\n" + "=" * 70)
    print("ROUND NUMBER BACKTEST — HEADLINE")
    print("=" * 70)
    m = result["metrics"]
    print(f"\nOverall: {m['overall']}\n")
    print("By tier:")
    for tier, mm in m["by_tier"].items():
        print(f"  {tier:>8s}: trades={mm['n_trades']:4d}  win_rate={mm['win_rate']:.1%}  "
              f"avg_r={mm['avg_r']:+.3f}  sharpe={mm['sharpe']:.2f}  "
              f"max_dd_r={mm['max_dd_r']:.2f}")
    print("\nBy pattern:")
    for pat, mm in m["by_pattern"].items():
        print(f"  {pat:>15s}: trades={mm['n_trades']:4d}  win_rate={mm['win_rate']:.1%}  "
              f"avg_r={mm['avg_r']:+.3f}")
    print("=" * 70)


if __name__ == "__main__":
    main()
