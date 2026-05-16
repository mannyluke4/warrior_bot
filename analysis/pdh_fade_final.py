"""Final filter validation + abandon-rule on the most-robust filter set."""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path('/Users/duffy/warrior_bot_v2')
df = pd.read_parquet(ROOT / 'analysis/pdh_fade_enriched.parquet')
df['year'] = pd.to_datetime(df['session_date']).dt.year
df['session_date'] = pd.to_datetime(df['session_date'])
df['vwap_aligned'] = ((df.direction == 'short') & (df.price_vs_vwap_pct < 0)) | \
                    ((df.direction == 'long') & (df.price_vs_vwap_pct > 0))
df['in_first_10min'] = df.minute_of_day < 9*60 + 40
df['in_first_15min'] = df.minute_of_day < 9*60 + 45

def metrics(s, label='', start_eq=100_000):
    if len(s) == 0:
        return None
    daily = s.groupby('session_date').pnl.sum()
    sh = (daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else np.nan
    wins = s[s.pnl > 0].pnl.sum()
    losses = abs(s[s.pnl < 0].pnl.sum())
    pf = wins / losses if losses else np.nan
    daily_full = pd.Series(0.0, index=pd.date_range(s.session_date.min(), s.session_date.max(), freq='B'))
    daily_full.update(daily)
    eq = start_eq + daily_full.cumsum()
    peak = eq.cummax()
    dd = ((eq - peak) / peak).min() * 100
    return {'label': label, 'n': len(s), 'wr': s.win.mean(), 'pnl': s.pnl.sum(),
            'avg_r': s.r_multiple.mean(), 'sharpe': sh, 'pf': pf, 'max_dd_pct': dd,
            'avg_per_day': daily.mean(), 'days': len(daily)}

def apply_abandon(s, minutes_X, abandon_pnl=-300):
    """Approximate: if a trade ended in loss AND hold > X min, cap loss to abandon_pnl."""
    sim = s.copy()
    mask = (sim.hold_min > minutes_X) & (sim.pnl <= 0)
    sim.loc[mask, 'pnl'] = sim.loc[mask, 'pnl'].clip(lower=abandon_pnl)
    return sim

print("="*100)
print("BEST FILTER CANDIDATES + ABANDON-RULE STACK")
print("="*100)

# Stack abandon@10 on each base
bases = {
    'F1 (t15)': df[df.in_first_15min],
    'F1+vwap (t15+vwap)': df[df.in_first_15min & df.vwap_aligned],
    'F7 (t15+tier50)': df[df.in_first_15min & (df.entry_price >= 50)],
    'F7+vwap (t15+vwap+tier50)': df[df.in_first_15min & df.vwap_aligned & (df.entry_price >= 50)],
    'F7+vwap+touch2': df[df.in_first_15min & df.vwap_aligned & (df.entry_price >= 50) & (df.level_touches >= 2)],
}

print(f"\n{'base':36s} {'abandon':>8s} {'n':>5s} {'wr':>6s} {'sharpe':>7s} {'pf':>6s} {'maxDD':>8s} {'pnl':>12s}")
for base_name, base_set in bases.items():
    for X in [None, 5, 10, 15, 20]:
        if X is None:
            sim = base_set
            tag = 'none'
        else:
            sim = apply_abandon(base_set, X)
            tag = f'@{X}min'
        m = metrics(sim, base_name)
        if m:
            print(f"{base_name:36s} {tag:>8s} {m['n']:>5d} {m['wr']*100:>5.1f}% {m['sharpe']:>7.2f} {m['pf']:>6.2f} {m['max_dd_pct']:>7.1f}% ${m['pnl']:>11,.0f}")
    print()

# --- Walk-forward on best-candidate with abandon ---
print("="*100)
print("WALK-FORWARD WITH ABANDON@10 — calibrate 2020-2022, test 2023-2024")
print("="*100)
candidates = {
    'F1+abandon@10': lambda d: apply_abandon(d[d.in_first_15min], 10),
    'F7+abandon@10': lambda d: apply_abandon(d[d.in_first_15min & (d.entry_price >= 50)], 10),
    'F1+vwap+abandon@10': lambda d: apply_abandon(d[d.in_first_15min & d.vwap_aligned], 10),
    'F7+vwap+abandon@10': lambda d: apply_abandon(d[d.in_first_15min & d.vwap_aligned & (d.entry_price >= 50)], 10),
}

cal = df[df.year <= 2022]
test = df[df.year >= 2023]

print(f"\n{'period':12s} {'filter':35s} {'n':>5s} {'wr':>6s} {'sharpe':>7s} {'pf':>6s} {'maxDD':>8s} {'pnl':>12s}")
for name, fn in candidates.items():
    for period_name, period_df in [('CAL 20-22', cal), ('TEST 23-24', test), ('ALL', df)]:
        sim = fn(period_df)
        m = metrics(sim, name)
        if m:
            print(f"{period_name:12s} {name:35s} {m['n']:>5d} {m['wr']*100:>5.1f}% {m['sharpe']:>7.2f} {m['pf']:>6.2f} {m['max_dd_pct']:>7.1f}% ${m['pnl']:>11,.0f}")
    print()

# Year-by-year for top candidates
print("="*100)
print("YEAR-BY-YEAR — best candidates with abandon@10")
print("="*100)
for name, fn in candidates.items():
    sim = fn(df)
    print(f"\n{name} (n={len(sim):,}):")
    print(f"  {'year':>6s} {'n':>5s} {'wr':>6s} {'pnl':>12s} {'avg_r':>7s} {'sharpe':>7s}")
    for y in sorted(df.year.unique()):
        sy = sim[sim.year == y]
        if len(sy) < 10:
            continue
        daily = sy.groupby('session_date').pnl.sum()
        sh = (daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0
        print(f"  {y:>6d} {len(sy):>5d} {sy.win.mean()*100:>5.1f}% ${sy.pnl.sum():>11,.0f} {sy.r_multiple.mean():>7.3f} {sh:>7.2f}")

# --- Top-of-line viability ---
print("="*100)
print("FINAL RECOMMENDED FILTER — F1+abandon@10 + winner-preservation check")
print("="*100)
# F1+abandon@10 - the simplest robust filter
final = apply_abandon(df[df.in_first_15min], 10)
m = metrics(final)
total_winner_pnl = df[df.win].pnl.sum()
final_winner_pnl = final[final.win].pnl.sum()
top1pct_baseline = df.nlargest(int(len(df)*0.01), 'pnl')
top1_kept = top1pct_baseline[top1pct_baseline.index.isin(final.index)]
print(f"Filter: 09:30-09:44 ET entries only, abandon @ 10min if no profit (cap loss at -$300)")
print(f"  n: {m['n']:,} ({m['n']/len(df)*100:.1f}% of baseline)")
print(f"  Sharpe: {m['sharpe']:.2f} (baseline {1.40:.2f})")
print(f"  PF: {m['pf']:.2f} (baseline 1.27)")
print(f"  WR: {m['wr']*100:.1f}% (baseline 18.8%)")
print(f"  MaxDD: {m['max_dd_pct']:.1f}% (baseline -24.0%)")
print(f"  P&L: ${m['pnl']:,.0f} (baseline $581,896)")
print(f"  Winner P&L kept: ${final_winner_pnl:,.0f} / ${total_winner_pnl:,.0f} = {final_winner_pnl/total_winner_pnl*100:.1f}%")
print(f"  Top 1% P&L kept: ${top1_kept.pnl.sum():,.0f} / ${top1pct_baseline.pnl.sum():,.0f} = {top1_kept.pnl.sum()/top1pct_baseline.pnl.sum()*100:.1f}% (n={len(top1_kept)}/{len(top1pct_baseline)})")

# $25K viability with this filter
scale = 0.25
final25 = final.copy()
final25['pnl'] = final25['pnl'] * scale
daily = final25.groupby('session_date').pnl.sum()
daily_full = pd.Series(0.0, index=pd.date_range(final.session_date.min(), final.session_date.max(), freq='B'))
daily_full.update(daily)
eq = 25_000 + daily_full.cumsum()
peak = eq.cummax()
dd = (eq - peak) / peak
print(f"\nAT $25K with $250 risk per trade:")
print(f"  Total P&L (5yr): ${final25.pnl.sum():,.0f}")
print(f"  Final equity: ${eq.iloc[-1]:,.0f}")
print(f"  Worst DD: {dd.min()*100:.1f}% = ${(eq - peak).min():,.0f}")
print(f"  Median day: ${daily.median():,.0f}, Mean day: ${daily.mean():,.0f}")
print(f"  % positive days: {(daily > 0).mean() * 100:.1f}%")
print(f"  Best day: ${daily.max():,.0f}, Worst day: ${daily.min():,.0f}")
print(f"  Days traded: {len(daily):,} (avg trades/day: {len(final)/len(daily):.1f})")

# Worst losing streak ($)
sorted_trades = final.sort_values('entry_ts').reset_index(drop=True)
cur = 0
streak = 0
runs = []
for p in sorted_trades.pnl * scale:
    if p < 0:
        cur += p
        streak += 1
    else:
        if streak > 0:
            runs.append((streak, cur))
        cur = 0
        streak = 0
runs.sort(key=lambda x: x[1])
print(f"\nLosing streaks:")
print(f"  Max consecutive losers: {max(r[0] for r in runs)}")
print(f"  Median streak: {np.median([r[0] for r in runs]):.0f}")
print(f"  Worst 5 by $-amount:")
for s, p in runs[:5]:
    print(f"    {s} losses in a row, $-{abs(p):,.0f}")

# 6-month rolling
roll = daily_full.rolling('180D').sum()
print(f"\nRolling 6-month P&L:")
print(f"  Worst: ${roll.min():,.0f}  (date: {roll.idxmin().date()})")
print(f"  Best:  ${roll.max():,.0f}  (date: {roll.idxmax().date()})")
print(f"  Median 6-mo: ${roll.median():,.0f}")
print(f"  % of 6-mo windows positive: {(roll > 0).mean()*100:.1f}%")
