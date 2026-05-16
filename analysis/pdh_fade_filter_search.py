"""PDH-Fade filter combination search + walk-forward validation."""
import pandas as pd
import numpy as np
from itertools import product
from pathlib import Path

ROOT = Path('/Users/duffy/warrior_bot_v2')
df = pd.read_parquet(ROOT / 'analysis/pdh_fade_enriched.parquet')
df['year'] = pd.to_datetime(df['session_date']).dt.year
df['session_date'] = pd.to_datetime(df['session_date'])

# Direction-aware VWAP edge: with-trend continuation
# PDH-fade SHORT works when price already below VWAP (trend already down)
# PDL-fade LONG works when price already above VWAP (trend already up)
df['vwap_aligned'] = ((df.direction == 'short') & (df.price_vs_vwap_pct < 0)) | \
                    ((df.direction == 'long') & (df.price_vs_vwap_pct > 0))

# Time gate
df['in_first_15min'] = df.minute_of_day < 9*60 + 45  # 09:30-09:44

# Big-winner attribution: top 1% are dominated by:
# - $150-300 and $300+ tier (huge $-per-share)
# - 09:30-09:34 minute window
# - VWAP-aligned direction
# - 2+ touches typically

def metrics(s, label='', annualization=252):
    """Compute key metrics for a trade subset."""
    if len(s) == 0:
        return {'label': label, 'n': 0}
    daily = s.groupby('session_date').pnl.sum()
    daily_full = pd.Series(0.0, index=pd.date_range(s.session_date.min(), s.session_date.max(), freq='B'))
    daily_full.update(daily)
    eq = 100_000 + daily_full.cumsum()
    peak = eq.cummax()
    dd = (eq - peak) / peak
    max_dd = dd.min()
    wins = s[s.pnl > 0].pnl.sum()
    losses = abs(s[s.pnl < 0].pnl.sum())
    pf = wins / losses if losses else np.nan
    sharpe = (daily.mean() / daily.std() * np.sqrt(annualization)) if daily.std() > 0 else np.nan
    return {
        'label': label,
        'n': len(s),
        'wr': s.win.mean(),
        'pnl': s.pnl.sum(),
        'pnl_per_trade': s.pnl.mean(),
        'avg_r': s.r_multiple.mean(),
        'sharpe': sharpe,
        'pf': pf,
        'max_dd_pct': max_dd*100,
        'days_traded': len(daily),
        'avg_per_day': daily.mean(),
        'worst_day': daily.min(),
        'best_day': daily.max(),
        'p_winners': s[s.win].pnl.sum(),
    }

# --- Test progressive filter stack ---
print("="*100)
print("PROGRESSIVE FILTER STACK")
print("="*100)
configs = [
    ('Baseline (all 9,874)', df),
    ('F1: first 15min (09:30-09:44)', df[df.in_first_15min]),
    ('F2: F1 + VWAP-aligned', df[df.in_first_15min & df.vwap_aligned]),
    ('F3: F1 + multi-touch (>=2)', df[df.in_first_15min & (df.level_touches >= 2)]),
    ('F4: F2 + multi-touch', df[df.in_first_15min & df.vwap_aligned & (df.level_touches >= 2)]),
    ('F5: F2 + tier >= $50', df[df.in_first_15min & df.vwap_aligned & (df.entry_price >= 50)]),
    ('F6: F4 + tier >= $50', df[df.in_first_15min & df.vwap_aligned & (df.level_touches >= 2) & (df.entry_price >= 50)]),
    ('F7: F1 + tier >= $50', df[df.in_first_15min & (df.entry_price >= 50)]),
    ('F8: F2 + tier >= $150', df[df.in_first_15min & df.vwap_aligned & (df.entry_price >= 150)]),
    ('F9: F1 + dist<=0.5%', df[df.in_first_15min & (df.dist_from_level_pct <= 0.5)]),
]
print(f"\n{'label':45s} {'n':>5s} {'wr':>6s} {'pnl':>12s} {'avg_r':>7s} {'sharpe':>7s} {'pf':>6s} {'maxDD':>8s} {'$/day':>8s}")
rows = []
for label, s in configs:
    m = metrics(s, label)
    rows.append(m)
    print(f"{m['label']:45s} {m['n']:>5d} {m['wr']*100:>5.1f}% ${m['pnl']:>11,.0f} {m['avg_r']:>7.3f} {m['sharpe']:>7.2f} {m['pf']:>6.2f} {m['max_dd_pct']:>7.1f}% ${m['avg_per_day']:>7.0f}")

# --- Big-winner P&L preservation ---
print("\n" + "="*100)
print("BIG-WINNER P&L PRESERVATION")
print("="*100)
top1pct_baseline = df.nlargest(int(len(df)*0.01), 'pnl')
total_winner_pnl = df[df.win].pnl.sum()
print(f"Baseline total winner P&L: ${total_winner_pnl:,.0f}")
print(f"Baseline top 1% (n=98) P&L: ${top1pct_baseline.pnl.sum():,.0f}")

for label, s in configs[1:]:
    s_winners = s[s.win]
    pct_kept = s_winners.pnl.sum() / total_winner_pnl * 100
    top1_kept = top1pct_baseline[top1pct_baseline.index.isin(s.index)]
    top1_pnl_kept = top1_kept.pnl.sum() / top1pct_baseline.pnl.sum() * 100
    print(f"  {label:45s}  winner_pnl_kept={pct_kept:5.1f}%  top1%_pnl_kept={top1_pnl_kept:5.1f}%  (n_top1_kept={len(top1_kept)})")

# --- Walk-forward: calibrate 2020-2022, test 2023-2024 ---
print("\n" + "="*100)
print("WALK-FORWARD: calibrate 2020-2022, test 2023-2024")
print("="*100)
cal = df[df.year <= 2022]
test = df[df.year >= 2023]
print(f"Calibration period: {len(cal):,} trades (2020-2022)")
print(f"Test period:        {len(test):,} trades (2023-2024)")

def apply_filter(d, name, fn):
    s = d[fn(d)]
    m = metrics(s, name)
    return m

# Test top candidate filter on both
filter_specs = [
    ('F1: time-only', lambda d: d.in_first_15min),
    ('F2: time + vwap-aligned', lambda d: d.in_first_15min & d.vwap_aligned),
    ('F4: time + vwap + multi-touch', lambda d: d.in_first_15min & d.vwap_aligned & (d.level_touches >= 2)),
    ('F6: time + vwap + multi-touch + tier>=$50', lambda d: d.in_first_15min & d.vwap_aligned & (d.level_touches >= 2) & (d.entry_price >= 50)),
    ('F8: time + vwap + tier>=$150', lambda d: d.in_first_15min & d.vwap_aligned & (d.entry_price >= 150)),
]
print(f"\n{'period':12s} {'filter':45s} {'n':>5s} {'wr':>6s} {'sharpe':>7s} {'pf':>6s} {'maxDD':>8s} {'pnl':>12s}")
for period_name, period_df in [('CAL 20-22', cal), ('TEST 23-24', test), ('ALL', df)]:
    for name, fn in filter_specs:
        m = apply_filter(period_df, name, fn)
        print(f"{period_name:12s} {m['label']:45s} {m['n']:>5d} {m['wr']*100:>5.1f}% {m['sharpe']:>7.2f} {m['pf']:>6.2f} {m['max_dd_pct']:>7.1f}% ${m['pnl']:>11,.0f}")
    print()

# --- Drawdown / streak analysis on best filter ---
print("="*100)
print("BEST FILTER — DETAILED OPERATING METRICS")
print("="*100)

best = df[df.in_first_15min & df.vwap_aligned & (df.entry_price >= 50)]
m = metrics(best, 'BEST = F1 + VWAP-aligned + price>=50')
print(f"\nFilter: {m['label']}")
for k, v in m.items():
    if isinstance(v, float):
        print(f"  {k}: {v:.3f}")
    else:
        print(f"  {k}: {v}")

# Sized at $1,000 risk per trade. Worst losing streak
best_sorted = best.sort_values('entry_ts').reset_index(drop=True)
best_sorted['streak'] = (best_sorted.win != best_sorted.win.shift()).cumsum()
streak_lengths = best_sorted[~best_sorted.win].groupby('streak').size()
print(f"\nLosing streak distribution (consecutive losers):")
print(f"  Max:    {streak_lengths.max()}")
print(f"  Median: {streak_lengths.median():.0f}")
print(f"  Mean:   {streak_lengths.mean():.1f}")
print(f"  Top 5:  {streak_lengths.nlargest(5).tolist()}")

# Drawdown analysis
daily_full = best.groupby('session_date').pnl.sum()
# At $25K starting equity, fixed-dollar $1K = 4% risk per trade -> aggressive
# More realistic: rescale to $250 risk per trade (1% of $25K). Trades scale linearly so P&L * 0.25
print("\nAT $25K STARTING EQUITY (rescale risk_dollars from $1,000 -> $250, i.e., 1% per trade):")
scaled = best.pnl * 0.25
daily_scaled = best.assign(pnl=scaled).groupby('session_date').pnl.sum()
daily_full2 = pd.Series(0.0, index=pd.date_range(best.session_date.min(), best.session_date.max(), freq='B'))
daily_full2.update(daily_scaled)
eq = 25_000 + daily_full2.cumsum()
peak = eq.cummax()
dd = (eq - peak) / peak
worst_dd = dd.min()
worst_dd_dollar = (eq - peak).min()
print(f"  Total P&L: ${scaled.sum():,.0f}")
print(f"  Final equity: ${eq.iloc[-1]:,.0f}")
print(f"  Max DD: {worst_dd*100:.1f}% (= ${worst_dd_dollar:,.0f})")
# Worst 6-month
roll6m_pnl = daily_full2.rolling('180D').sum()
print(f"  Worst 6-month P&L: ${roll6m_pnl.min():,.0f}")
print(f"  Best 6-month P&L:  ${roll6m_pnl.max():,.0f}")

# Worst losing streak in $ terms
losing_runs = []
cur = 0
for p in scaled:
    if p < 0:
        cur += p
    else:
        if cur < 0:
            losing_runs.append(cur)
        cur = 0
if cur < 0:
    losing_runs.append(cur)
losing_runs.sort()
print(f"  Worst 5 $-streaks: {[f'${x:,.0f}' for x in losing_runs[:5]]}")

# Trade counts
print(f"\nTrade frequency:")
print(f"  Total trades: {len(best):,}")
print(f"  Days traded: {best.session_date.nunique():,}")
print(f"  Trades per day: {len(best) / best.session_date.nunique():.1f}")
print(f"  Annualized trades: {len(best) / 5:.0f}")
