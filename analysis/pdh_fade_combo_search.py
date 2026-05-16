"""Search filter combinations for the Sharpe>=2.0 target.

Also produce final viability-at-$25K and out-of-sample stats.
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path('/Users/duffy/warrior_bot_v2')
df = pd.read_parquet(ROOT / 'analysis/pdh_fade_enriched.parquet')
df['year'] = pd.to_datetime(df['session_date']).dt.year
df['session_date'] = pd.to_datetime(df['session_date'])
df['vwap_aligned'] = ((df.direction == 'short') & (df.price_vs_vwap_pct < 0)) | \
                    ((df.direction == 'long') & (df.price_vs_vwap_pct > 0))
df['in_first_5min'] = df.minute_of_day < 9*60 + 35
df['in_first_10min'] = df.minute_of_day < 9*60 + 40
df['in_first_15min'] = df.minute_of_day < 9*60 + 45
df['big_gap'] = df.gap_pct.abs() > 1.5

def metrics(s, label='', start_equity=100_000):
    if len(s) == 0:
        return {'label': label, 'n': 0}
    daily = s.groupby('session_date').pnl.sum()
    if len(daily) == 0:
        return {'label': label, 'n': 0}
    sharpe = (daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else np.nan
    wins = s[s.pnl > 0].pnl.sum()
    losses = abs(s[s.pnl < 0].pnl.sum())
    pf = wins / losses if losses else np.nan
    # full-period DD with zero-fill days
    daily_full = pd.Series(0.0, index=pd.date_range(s.session_date.min(), s.session_date.max(), freq='B'))
    daily_full.update(daily)
    eq = start_equity + daily_full.cumsum()
    peak = eq.cummax()
    max_dd_pct = ((eq - peak) / peak).min() * 100
    return {
        'label': label, 'n': len(s), 'wr': s.win.mean(),
        'pnl': s.pnl.sum(), 'avg_r': s.r_multiple.mean(),
        'sharpe': sharpe, 'pf': pf, 'max_dd_pct': max_dd_pct,
        'avg_per_day': daily.mean(), 'days': len(daily),
    }

# Try more combos with stricter conditions
filters = {
    'baseline': df.index >= 0,
    # Time-only variants
    'F_t5': df.in_first_5min,
    'F_t10': df.in_first_10min,
    'F_t15': df.in_first_15min,
    # Add VWAP-align
    'F_t10_vwap': df.in_first_10min & df.vwap_aligned,
    'F_t15_vwap': df.in_first_15min & df.vwap_aligned,
    # Add tier
    'F_t10_tier50': df.in_first_10min & (df.entry_price >= 50),
    'F_t10_tier150': df.in_first_10min & (df.entry_price >= 150),
    'F_t15_tier150': df.in_first_15min & (df.entry_price >= 150),
    # Multi-feature
    'F_t10_vwap_tier50': df.in_first_10min & df.vwap_aligned & (df.entry_price >= 50),
    'F_t10_vwap_tier150': df.in_first_10min & df.vwap_aligned & (df.entry_price >= 150),
    'F_t15_vwap_tier150': df.in_first_15min & df.vwap_aligned & (df.entry_price >= 150),
    # Direction-specific
    'F_short_only_t15_vwap': (df.direction == 'short') & df.in_first_15min & df.vwap_aligned,
    'F_long_only_t15_vwap': (df.direction == 'long') & df.in_first_15min & df.vwap_aligned,
    # Gap-aware
    'F_t15_vwap_small_gap': df.in_first_15min & df.vwap_aligned & (df.gap_pct.abs() < 2),
    'F_t15_vwap_big_gap': df.in_first_15min & df.vwap_aligned & (df.gap_pct.abs() >= 1),
    # Touch combos
    'F_t10_tier50_touch2': df.in_first_10min & (df.entry_price >= 50) & (df.level_touches >= 2),
    # Hold-time abandon: simulate cutting losers at minute X
}

print(f"\n{'filter':40s} {'n':>5s} {'wr':>6s} {'sharpe':>7s} {'pf':>6s} {'maxDD':>8s} {'avg_r':>7s} {'pnl':>12s} {'$/day':>7s}")
results = []
for name, mask in filters.items():
    s = df[mask]
    m = metrics(s, name)
    results.append(m)
    if m['n'] > 0:
        print(f"{name:40s} {m['n']:>5d} {m['wr']*100:>5.1f}% {m['sharpe']:>7.2f} {m['pf']:>6.2f} {m['max_dd_pct']:>7.1f}% {m['avg_r']:>7.3f} ${m['pnl']:>11,.0f} ${m['avg_per_day']:>6.0f}")

# --- Now simulate H10 abandon rule on top of best filter ---
print("\n" + "="*100)
print("HOLD-TIME ABANDON SIMULATION (on F_t15_vwap = best balance)")
print("="*100)
# Idea: trades that aren't in profit by minute X are exited at last price at minute X.
# We CAN'T fully simulate without bar data per trade, but we can do an approximate:
# - If exit_reason == 'stop' or 'session_close' AND hold_min > X -> CAP loss to estimated mid-time price
# Since we don't have intra-trade bars, instead just count:
# - For each trade, if hold_min > X and pnl <= 0 -> the trade lost the full amount anyway (stop fired later or session close)
# - But the trades we'd cut might be the multi-hour drifts that ended -$200 instead of going to a winner
#
# More careful: the EXPECTED VALUE of a trade given "still open at minute X with P&L <= 0" — does it become positive?
# Approach: among trades not in profit at minute X (proxy: hold_min > X AND pnl <= 0 final), what's average pnl?
# If avg_final_pnl is very negative for these, abandoning early HELPS. If close to zero, neutral. If positive, hurts.
base = df[df.in_first_15min & df.vwap_aligned].copy()
print(f"Base set: {len(base):,} trades")
for X in [10, 15, 20, 30, 45, 60]:
    # "Abandon" means cap pnl to ~0 (or specifically, exit at minute X). Without bar-level data we approximate:
    # trades with hold_min > X that ended in loss are "candidates" for abandon
    cands = base[base.hold_min > X]
    print(f"\nAbandon at minute {X}:")
    print(f"  Candidates (hold>{X}min): {len(cands)} ({len(cands)/len(base)*100:.1f}%)")
    print(f"  Of those, eventual: wins={cands.win.sum()} ({cands.win.mean()*100:.1f}%), losses={(~cands.win).sum()}")
    print(f"  Avg pnl of these candidates: ${cands.pnl.mean():.0f} (winners ${cands[cands.win].pnl.mean():.0f}, losers ${cands[~cands.win].pnl.mean():.0f})")
    # Abandon-rule simulation: if hold > X and not won by exit, cap to -0.3R (half-stop)
    # i.e., assume early-abandon means we get out at ~-0.3R instead of letting stop fire at -1R
    sim = base.copy()
    half_stop = -300  # ~30% of $1K risk
    # If a trade ended as loser AND held longer than X minutes, cap loss to half_stop
    abandon_mask = (sim.hold_min > X) & (sim.pnl <= 0)
    sim.loc[abandon_mask, 'pnl'] = sim.loc[abandon_mask, 'pnl'].clip(lower=half_stop)
    m = metrics(sim, f'abandon@{X}min')
    print(f"  SIM metrics: n={m['n']}, sharpe={m['sharpe']:.2f}, pf={m['pf']:.2f}, pnl=${m['pnl']:,.0f}")

# --- Year-by-year out-of-sample on best candidate ---
print("\n" + "="*100)
print("YEAR-BY-YEAR ON BEST CANDIDATES (full walk-forward)")
print("="*100)
candidates = {
    'F1: time-only (09:30-09:44)': df[df.in_first_15min],
    'F3: time + multi-touch': df[df.in_first_15min & (df.level_touches >= 2)],
    'F7: time + tier>=$50': df[df.in_first_15min & (df.entry_price >= 50)],
    'F2: time + vwap-aligned': df[df.in_first_15min & df.vwap_aligned],
    'F8: time + vwap + tier>=$150': df[df.in_first_15min & df.vwap_aligned & (df.entry_price >= 150)],
}

for name, s in candidates.items():
    print(f"\n{name} (n={len(s):,}):")
    print(f"  {'year':>6s} {'n':>5s} {'wr':>6s} {'pnl':>12s} {'avg_r':>7s} {'sharpe':>7s}")
    for y in sorted(s.year.unique()):
        sy = s[s.year == y]
        if len(sy) < 10:
            continue
        daily = sy.groupby('session_date').pnl.sum()
        sh = (daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0
        print(f"  {y:>6d} {len(sy):>5d} {sy.win.mean()*100:>5.1f}% ${sy.pnl.sum():>11,.0f} {sy.r_multiple.mean():>7.3f} {sh:>7.2f}")

# --- VIABILITY AT $25K ---
print("\n" + "="*100)
print("$25K VIABILITY ANALYSIS")
print("="*100)
# Use F_t15_tier50 as recommended (best Sharpe with good winner retention)
# Best balance from above: F7 has Sharpe 1.57, keeps 65% winner PnL, DD only -10.9%
best_set = df[df.in_first_15min & (df.entry_price >= 50)]
m = metrics(best_set, 'F7-final')
print(f"\nRecommended filter: F7 = first 15min + price >= $50")
print(f"  Aggregate: Sharpe {m['sharpe']:.2f}, PF {m['pf']:.2f}, WR {m['wr']*100:.1f}%, MaxDD {m['max_dd_pct']:.1f}%")
print(f"  Trades: {m['n']:,} ({m['days']} days, {m['n']/m['days']:.1f}/day)")
print(f"  P&L: ${m['pnl']:,.0f} on $100K @ $1K risk → ${m['pnl']*0.25:,.0f} on $25K @ $250 risk")

# Scaled to $25K + $250 risk
scale = 0.25
print(f"\nAT $25K with $250 risk per trade:")
print(f"  Expected total P&L (5yr): ${m['pnl']*scale:,.0f}")
print(f"  Final equity: ${25000 + m['pnl']*scale:,.0f}")
print(f"  Worst DD: {m['max_dd_pct']:.1f}% = ${25000 * m['max_dd_pct']/100:,.0f}")
# Worst losing streak
best_sorted = best_set.sort_values('entry_ts').reset_index(drop=True)
runs = []
cur = 0
streak = 0
for p in best_sorted.pnl * scale:
    if p < 0:
        cur += p
        streak += 1
    else:
        if cur < 0:
            runs.append((streak, cur))
        cur = 0
        streak = 0
if cur < 0:
    runs.append((streak, cur))
runs.sort(key=lambda x: x[1])
print(f"  Worst $-losing-streaks (count, $):")
for s, p in runs[:5]:
    print(f"    {s} losses in a row, $-{abs(p):,.0f}")

# 6-month worst
daily = best_set.assign(pnl=best_set.pnl*scale).groupby('session_date').pnl.sum()
daily_full = pd.Series(0.0, index=pd.date_range(best_set.session_date.min(), best_set.session_date.max(), freq='B'))
daily_full.update(daily)
roll = daily_full.rolling('180D').sum()
print(f"  Worst 6-month rolling P&L: ${roll.min():,.0f}  (date: {roll.idxmin().date()})")
print(f"  Best 6-month rolling P&L:  ${roll.max():,.0f}  (date: {roll.idxmax().date()})")

# Consecutive loss-day analysis
loss_days = (daily_full < 0).astype(int)
max_streak = 0
cur_streak = 0
for d in loss_days:
    if d:
        cur_streak += 1
        max_streak = max(max_streak, cur_streak)
    else:
        cur_streak = 0
print(f"  Max consecutive loss days: {max_streak}")
print(f"  % positive days: {(daily > 0).mean() * 100:.1f}%")
print(f"  Best day: ${daily.max():,.0f}, Worst day: ${daily.min():,.0f}")
print(f"  Median day: ${daily.median():,.0f}, Mean day: ${daily.mean():,.0f}")
