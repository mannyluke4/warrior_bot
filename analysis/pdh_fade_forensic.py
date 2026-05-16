"""PDH-Fade Forensic — pre-bar feature enrichment + hypothesis tests.

Inputs:  backtest_archive/wave3_portfolio/trades_PDH-PDL-Fade_fixed_dollar.csv
         tick_cache_databento/<SYM>/1m_<YYYY-MM-DD>.parquet

Outputs: analysis/pdh_fade_enriched.parquet  (one row per trade, +features)
"""
from __future__ import annotations
import os
import sys
import pandas as pd
import numpy as np
from datetime import time as dtime
from pathlib import Path

ROOT = Path('/Users/duffy/warrior_bot_v2')
TRADES_CSV = ROOT / 'backtest_archive/wave3_portfolio/trades_PDH-PDL-Fade_fixed_dollar.csv'
TICK_DIR = ROOT / 'tick_cache_databento'
OUT_PARQUET = ROOT / 'analysis/pdh_fade_enriched.parquet'

RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)


def session_bars(symbol: str, session_date: pd.Timestamp) -> pd.DataFrame | None:
    """Load 1-min bars for a symbol on a session date.  Restrict to RTH + PM."""
    fname = TICK_DIR / symbol / f"1m_{session_date.strftime('%Y-%m-%d')}.parquet"
    if not fname.exists():
        return None
    try:
        df = pd.read_parquet(fname)
        df['ts_event'] = pd.to_datetime(df['ts_event'])
        return df.sort_values('ts_event').reset_index(drop=True)
    except Exception:
        return None


def prior_day_bars(symbol: str, session_date: pd.Timestamp, max_back: int = 7) -> pd.DataFrame | None:
    """Find the most recent prior session's RTH bars."""
    for d in range(1, max_back + 1):
        prior = session_date - pd.Timedelta(days=d)
        df = session_bars(symbol, prior)
        if df is None or len(df) == 0:
            continue
        # Restrict to RTH for prior-day range
        rth = df[(df.ts_event.dt.time >= RTH_OPEN) & (df.ts_event.dt.time < RTH_CLOSE)]
        if len(rth) >= 30:
            return rth
    return None


def compute_features_for_trade(row, today_df, prior_df) -> dict:
    """Compute pre-entry features for a single trade.  Uses bars STRICTLY before entry_ts."""
    feats = {}
    entry_ts = pd.to_datetime(row['entry_ts'])

    # Today's bars BEFORE entry (cumulative state at entry)
    pre = today_df[today_df.ts_event < entry_ts].copy()
    rth_pre = pre[pre.ts_event.dt.time >= RTH_OPEN]

    # --- Day range expansion at entry ---
    if len(rth_pre) > 0:
        day_high_so_far = rth_pre.high.max()
        day_low_so_far = rth_pre.low.min()
        feats['day_range_pct'] = (day_high_so_far - day_low_so_far) / row['entry_price'] * 100
        feats['day_range_dollars'] = day_high_so_far - day_low_so_far
    else:
        feats['day_range_pct'] = np.nan
        feats['day_range_dollars'] = np.nan

    # --- Prior day range (ADR-ish) ---
    if prior_df is not None and len(prior_df) > 0:
        pdh = prior_df.high.max()
        pdl = prior_df.low.min()
        prior_range = pdh - pdl
        prior_close = prior_df.iloc[-1].close if len(prior_df) > 0 else np.nan
        feats['pdh'] = pdh
        feats['pdl'] = pdl
        feats['prior_range_dollars'] = prior_range
        feats['prior_range_pct'] = prior_range / prior_close * 100 if prior_close else np.nan
        # Day-range / prior-range ratio (compressed vs expanded)
        feats['range_ratio'] = (feats['day_range_dollars'] / prior_range) if prior_range > 0 else np.nan
        # Gap context
        if len(rth_pre) > 0:
            open_today = rth_pre.iloc[0].open
            feats['open_today'] = open_today
            feats['gap_pct'] = (open_today - prior_close) / prior_close * 100 if prior_close else np.nan
        else:
            feats['gap_pct'] = np.nan
            feats['open_today'] = np.nan
    else:
        for k in ['pdh','pdl','prior_range_dollars','prior_range_pct','range_ratio','open_today','gap_pct']:
            feats[k] = np.nan

    # --- VWAP relationship at entry ---
    if len(rth_pre) > 0:
        # Cumulative typical-price weighted VWAP from RTH open through pre-entry
        tp = (rth_pre.high + rth_pre.low + rth_pre.close) / 3
        v = rth_pre.volume.values
        if v.sum() > 0:
            vwap = float((tp.values * v).sum() / v.sum())
            feats['vwap_at_entry'] = vwap
            feats['price_vs_vwap_pct'] = (row['entry_price'] - vwap) / vwap * 100
        else:
            feats['vwap_at_entry'] = np.nan
            feats['price_vs_vwap_pct'] = np.nan
    else:
        feats['vwap_at_entry'] = np.nan
        feats['price_vs_vwap_pct'] = np.nan

    # --- Distance from level (using stop placement) ---
    # Stop is $0.10 past level. For short: stop > entry, level = stop - 0.10
    # For long:  stop < entry, level = stop + 0.10
    if row['direction'] == 'short':
        level = row['stop_price'] - 0.10
        dist_from_level = level - row['entry_price']  # positive: entry below level
    else:
        level = row['stop_price'] + 0.10
        dist_from_level = row['entry_price'] - level  # positive: entry above level
    feats['level_price'] = level
    feats['dist_from_level_pct'] = abs(dist_from_level) / row['entry_price'] * 100

    # --- Recent volatility: last 5 bars range vs prior 5-bar average ---
    if len(pre) >= 10:
        last5 = pre.iloc[-5:]
        prev5 = pre.iloc[-10:-5]
        last5_range = (last5.high - last5.low).mean()
        prev5_range = (prev5.high - prev5.low).mean()
        feats['last5_range'] = last5_range
        feats['volatility_ratio'] = (last5_range / prev5_range) if prev5_range > 0 else np.nan
        # The rejection bar (last bar before entry): how big was it?
        last_bar = pre.iloc[-1]
        feats['last_bar_range'] = last_bar.high - last_bar.low
        feats['last_bar_volume'] = float(last_bar.volume)
        # 5-bar avg vol
        feats['last5_vol_mean'] = last5.volume.mean()
        feats['volume_spike_ratio'] = (last_bar.volume / last5.volume.mean()) if last5.volume.mean() > 0 else np.nan
    else:
        for k in ['last5_range','volatility_ratio','last_bar_range','last_bar_volume','last5_vol_mean','volume_spike_ratio']:
            feats[k] = np.nan

    # --- Multi-touch: how many times did price approach level today before entry? ---
    if len(rth_pre) > 0 and not pd.isna(feats.get('pdh', np.nan)):
        pdh = feats['pdh']
        pdl = feats['pdl']
        # For PDH-fade (short): count bars where high touched within 0.1% of PDH
        if row['direction'] == 'short':
            tol = pdh * 0.001
            touches = (rth_pre.high >= (pdh - tol)).sum()
        else:
            tol = pdl * 0.001
            touches = (rth_pre.low <= (pdl + tol)).sum()
        feats['level_touches'] = int(touches)
    else:
        feats['level_touches'] = np.nan

    # --- Time bucket / day of week ---
    feats['minute_of_day'] = entry_ts.hour * 60 + entry_ts.minute
    feats['day_of_week'] = entry_ts.day_name()

    return feats


def main(limit: int | None = None):
    print(f"Loading trades from {TRADES_CSV}")
    trades = pd.read_csv(TRADES_CSV, parse_dates=['entry_ts', 'exit_ts', 'session_date'])
    if limit:
        trades = trades.head(limit)
    print(f"  {len(trades):,} trades to enrich")

    # Group by (symbol, session_date) for efficient bar-loading
    rows = []
    cache_today = {}
    cache_prior = {}
    n = len(trades)
    for i, (_, row) in enumerate(trades.iterrows()):
        if i % 500 == 0:
            print(f"  progress: {i}/{n}")
        key = (row['symbol'], row['session_date'])
        if key not in cache_today:
            cache_today[key] = session_bars(row['symbol'], row['session_date'])
            cache_prior[key] = prior_day_bars(row['symbol'], row['session_date'])
        today_df = cache_today[key]
        prior_df = cache_prior[key]
        if today_df is None:
            feats = {}
        else:
            feats = compute_features_for_trade(row, today_df, prior_df)
        # Merge with original row
        merged = row.to_dict()
        merged.update(feats)
        rows.append(merged)

    out = pd.DataFrame(rows)
    out['win'] = out['pnl'] > 0
    out['hold_min'] = (pd.to_datetime(out['exit_ts']) - pd.to_datetime(out['entry_ts'])).dt.total_seconds() / 60
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_PARQUET)
    print(f"Wrote {len(out):,} rows -> {OUT_PARQUET}")
    print("Columns:", out.columns.tolist())


if __name__ == '__main__':
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(limit)
