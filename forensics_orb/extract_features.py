"""
ORB-5min forensic feature extraction.

For each of the 9,790 ORB trades, attach per-bar context features computed from
the corresponding 1m parquet files. Output: enriched parquet keyed by trade
row index.

Features computed per trade (entry_ts):
  - pm_gap_pct: (RTH-open price - prior session close) / prior close * 100
  - or5_volume: total volume of the 5-min opening range (09:30-09:35 ET, 5 bars)
  - or5_dir: 'green' / 'red' / 'doji' of the cumulative 09:30-09:34 bars
  - rvol_today_open: today's first-10-min volume / 20-day avg first-10-min volume
  - vwap_at_entry: cumulative VWAP from RTH open to entry bar
  - dist_vwap_pct: (entry_price - vwap_at_entry) / vwap_at_entry * 100
  - mins_from_open: minutes between entry_ts and 09:30
  - day_of_week: Mon..Fri (0..4)
  - vix_proxy: rolling 5-day stddev of universe high-low% (computed once per date)
  - tier: bucket on entry_price ($<10, $10-20, $20-50, $50-100, $100-200, $200-300, $300+)
  - bar_count_rth: number of populated 1m bars (data-quality flag)

Aggregates 20-day baselines per (symbol, calendar-date) from the same parquet
files. Caches per-symbol per-date aggregates to disk.
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from datetime import datetime, date, timedelta

import numpy as np
import pandas as pd

ROOT = Path("/Users/duffy/warrior_bot_v2")
CACHE_DIR = ROOT / "tick_cache_databento"
TRADES_PATH = ROOT / "backtest_archive" / "wave3_portfolio" / "trades_ORB-5min_fixed_dollar.parquet"
OUT_PATH = ROOT / "forensics_orb" / "trades_with_features.parquet"

RTH_OPEN = pd.Timestamp("09:30:00").time()
RTH_CLOSE = pd.Timestamp("16:00:00").time()


def _load_day_bars(symbol: str, d: date) -> pd.DataFrame | None:
    p = CACHE_DIR / symbol / f"1m_{d.isoformat()}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if df.empty:
        return None
    return df


def _classify_bar_color(o: float, c: float, eps_pct: float = 0.05) -> str:
    if o <= 0:
        return "doji"
    pct = (c - o) / o * 100
    if pct > eps_pct:
        return "green"
    if pct < -eps_pct:
        return "red"
    return "doji"


def _trading_dates_for_symbol(symbol: str) -> list[date]:
    syms = sorted(os.listdir(CACHE_DIR / symbol))
    out = []
    for n in syms:
        if not n.startswith("1m_") or not n.endswith(".parquet"):
            continue
        try:
            d = datetime.strptime(n[3:-8], "%Y-%m-%d").date()
        except ValueError:
            continue
        out.append(d)
    return sorted(out)


def _prior_close(symbol: str, today: date, dates_sorted: list[date]) -> float | None:
    """RTH close from prior trading day (16:00 ET nominal). Use last RTH bar close."""
    idx = pd.Series(dates_sorted).searchsorted(today)
    if idx == 0:
        return None
    prior = dates_sorted[idx - 1]
    bars = _load_day_bars(symbol, prior)
    if bars is None:
        return None
    rth = bars[(bars["ts_event"].dt.time >= RTH_OPEN) & (bars["ts_event"].dt.time < RTH_CLOSE)]
    if rth.empty:
        return None
    return float(rth.iloc[-1]["close"])


def _premarket_gap_pct(symbol: str, today: date, dates_sorted: list[date]) -> float | None:
    """Today's RTH-open price vs prior RTH close."""
    prior_close = _prior_close(symbol, today, dates_sorted)
    if prior_close is None or prior_close <= 0:
        return None
    bars = _load_day_bars(symbol, today)
    if bars is None:
        return None
    rth = bars[(bars["ts_event"].dt.time >= RTH_OPEN) & (bars["ts_event"].dt.time < RTH_CLOSE)]
    if rth.empty:
        return None
    open_price = float(rth.iloc[0]["open"])
    return (open_price - prior_close) / prior_close * 100


def _opening_range_features(symbol: str, today: date) -> dict | None:
    """Returns dict with or5_high, or5_low, or5_volume, or5_dir, or5_open, or5_close."""
    bars = _load_day_bars(symbol, today)
    if bars is None:
        return None
    # 09:30 - 09:34 inclusive (5 bars)
    rth = bars[bars["ts_event"].dt.time >= RTH_OPEN]
    rth = rth.sort_values("ts_event")
    if rth.empty:
        return None
    # Use first 5 RTH minute-bars
    or_bars = rth.head(5)
    if len(or_bars) < 1:
        return None
    o5 = float(or_bars.iloc[0]["open"])
    c5 = float(or_bars.iloc[-1]["close"])
    return {
        "or5_high": float(or_bars["high"].max()),
        "or5_low": float(or_bars["low"].min()),
        "or5_volume": int(or_bars["volume"].sum()),
        "or5_dir": _classify_bar_color(o5, c5),
        "or5_open": o5,
        "or5_close": c5,
    }


def _rolling_20d_or5_volume(symbol: str, today: date, dates_sorted: list[date]) -> float | None:
    """20 trading-day mean of OR5 volume strictly before today."""
    idx = pd.Series(dates_sorted).searchsorted(today)
    prior = dates_sorted[max(0, idx - 20):idx]
    if not prior:
        return None
    vols = []
    for d in prior:
        f = _opening_range_features(symbol, d)
        if f is not None:
            vols.append(f["or5_volume"])
    if not vols:
        return None
    return float(np.mean(vols))


def _entry_context(symbol: str, today: date, entry_ts: pd.Timestamp, entry_price: float) -> dict:
    """VWAP from RTH open through entry bar inclusive, plus minutes-from-open."""
    bars = _load_day_bars(symbol, today)
    if bars is None:
        return {}
    rth = bars[bars["ts_event"].dt.time >= RTH_OPEN].sort_values("ts_event")
    if rth.empty:
        return {}
    upto = rth[rth["ts_event"] <= entry_ts]
    if upto.empty:
        return {}
    typical = (upto["high"] + upto["low"] + upto["close"]) / 3.0
    vol = upto["volume"].astype(float)
    vwap = float((typical * vol).sum() / max(vol.sum(), 1.0))
    open_dt = pd.Timestamp.combine(today, RTH_OPEN)
    mins = int((entry_ts - open_dt).total_seconds() // 60)
    return {
        "vwap_at_entry": vwap,
        "dist_vwap_pct": (entry_price - vwap) / vwap * 100 if vwap > 0 else 0.0,
        "mins_from_open": mins,
        "bar_count_rth_to_entry": int(len(upto)),
    }


def _price_tier(p: float) -> str:
    if p < 10:
        return "<$10"
    if p < 20:
        return "$10-20"
    if p < 50:
        return "$20-50"
    if p < 100:
        return "$50-100"
    if p < 200:
        return "$100-200"
    if p < 300:
        return "$200-300"
    return "$300+"


def main() -> None:
    trades = pd.read_parquet(TRADES_PATH)
    trades["entry_ts"] = pd.to_datetime(trades["entry_ts"])
    trades["exit_ts"] = pd.to_datetime(trades["exit_ts"])
    trades["session_date"] = pd.to_datetime(trades["session_date"]).dt.date

    # Pre-load per-symbol trading-date sequences and a per-symbol OR5 cache
    per_symbol_dates: dict[str, list[date]] = {}
    or5_cache: dict[tuple[str, date], dict | None] = {}
    prior_close_cache: dict[tuple[str, date], float | None] = {}

    syms = sorted(trades["symbol"].unique())
    for s in syms:
        per_symbol_dates[s] = _trading_dates_for_symbol(s)

    # Pre-warm OR5 + prior_close caches by iterating per-symbol all dates that
    # appear in trades + the 20 prior dates.
    print("Pre-warming OR5 cache...", flush=True)
    for s in syms:
        all_dates = per_symbol_dates[s]
        sym_trades = trades[trades["symbol"] == s]
        needed_dates: set[date] = set()
        for d in sym_trades["session_date"].unique():
            idx = pd.Series(all_dates).searchsorted(d)
            needed_dates.add(d)
            for back in range(1, 21):
                if idx - back >= 0:
                    needed_dates.add(all_dates[idx - back])
        for d in sorted(needed_dates):
            or5_cache[(s, d)] = _opening_range_features(s, d)
        # prior close cache for trade dates only
        for d in sym_trades["session_date"].unique():
            prior_close_cache[(s, d)] = _prior_close(s, d, all_dates)
        print(f"  {s}: {len(needed_dates)} dates cached", flush=True)

    # Now compute features per trade
    rows = []
    for i, row in trades.iterrows():
        s = row["symbol"]
        d = row["session_date"]
        entry_ts = row["entry_ts"]
        entry_price = row["entry_price"]

        # premarket gap
        pc = prior_close_cache.get((s, d))
        if pc is not None and pc > 0:
            # Need today's RTH-open price; OR5 features include or5_open which is open of 09:30
            or5 = or5_cache.get((s, d))
            if or5 is not None:
                rth_open = or5["or5_open"]
                gap_pct = (rth_open - pc) / pc * 100
            else:
                gap_pct = np.nan
        else:
            gap_pct = np.nan

        # OR5 metrics
        or5 = or5_cache.get((s, d)) or {}
        or5_vol = or5.get("or5_volume", np.nan)
        or5_dir = or5.get("or5_dir", "unknown")
        or5_open = or5.get("or5_open", np.nan)
        or5_high = or5.get("or5_high", np.nan)
        or5_low = or5.get("or5_low", np.nan)

        # 20-day baseline OR5 volume
        all_dates = per_symbol_dates[s]
        idx = pd.Series(all_dates).searchsorted(d)
        prior = all_dates[max(0, idx - 20):idx]
        baseline_vols = [or5_cache.get((s, dd)) for dd in prior]
        baseline_vols = [b["or5_volume"] for b in baseline_vols if b is not None]
        if baseline_vols:
            baseline_mean = float(np.mean(baseline_vols))
            rvol_or5 = or5_vol / baseline_mean if baseline_mean > 0 and not pd.isna(or5_vol) else np.nan
        else:
            baseline_mean = np.nan
            rvol_or5 = np.nan

        # Entry context (VWAP, mins from open)
        ec = _entry_context(s, d, entry_ts, entry_price)

        rows.append({
            **row.to_dict(),
            "pm_gap_pct": gap_pct,
            "or5_volume": or5_vol,
            "or5_dir": or5_dir,
            "or5_open": or5_open,
            "or5_high": or5_high,
            "or5_low": or5_low,
            "or5_vol_baseline_20d": baseline_mean,
            "or5_rvol": rvol_or5,
            "vwap_at_entry": ec.get("vwap_at_entry", np.nan),
            "dist_vwap_pct": ec.get("dist_vwap_pct", np.nan),
            "mins_from_open": ec.get("mins_from_open", np.nan),
            "day_of_week": entry_ts.dayofweek,
            "tier": _price_tier(entry_price),
            "year": entry_ts.year,
            "quarter": f"{entry_ts.year}Q{(entry_ts.month-1)//3+1}",
        })
        if (i + 1) % 1000 == 0:
            print(f"  {i+1}/{len(trades)} trades processed", flush=True)

    out = pd.DataFrame(rows)
    out.to_parquet(OUT_PATH, index=False)
    print(f"Wrote {len(out)} rows to {OUT_PATH}")
    print()
    print("Quick sanity check:")
    print(out[["symbol","session_date","r_multiple","pm_gap_pct","or5_rvol","dist_vwap_pct","mins_from_open","or5_dir","tier","day_of_week"]].head())


if __name__ == "__main__":
    main()
