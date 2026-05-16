"""Run all 11 hypotheses on the enriched PDH-Fade dataset."""
import pandas as pd
import numpy as np
from scipy import stats
from pathlib import Path

ROOT = Path('/Users/duffy/warrior_bot_v2')
P = ROOT / 'analysis/pdh_fade_enriched.parquet'

df = pd.read_parquet(P)
df['year'] = pd.to_datetime(df['session_date']).dt.year
df['price_tier'] = pd.cut(df['entry_price'], [0, 10, 50, 150, 300, 10000],
                          labels=['<$10','$10-50','$50-150','$150-300','$300+'])
df['above_vwap'] = (df['price_vs_vwap_pct'] > 0).astype(int)

print("=" * 80)
print("PDH-FADE FORENSIC — Hypothesis Tests (n =", len(df), "trades)")
print("=" * 80)

def chi_sq(df, feat, win_col='win'):
    """Chi-square test for independence between feature and win/loss."""
    ct = pd.crosstab(df[feat], df[win_col])
    if ct.shape[0] < 2 or ct.shape[1] < 2:
        return None
    chi2, p, dof, _ = stats.chi2_contingency(ct)
    return {'chi2': chi2, 'p': p, 'dof': dof}

def t_test(df, feat, win_col='win'):
    """T-test of feature value: winners vs losers."""
    w = df[df[win_col]][feat].dropna()
    l = df[~df[win_col]][feat].dropna()
    if len(w) < 5 or len(l) < 5:
        return None
    t, p = stats.ttest_ind(w, l, equal_var=False)
    return {'t': t, 'p': p, 'win_mean': w.mean(), 'lose_mean': l.mean(), 'win_n': len(w), 'lose_n': len(l)}

def summary(name, mask):
    sub = df[mask]
    if len(sub) == 0:
        return None
    return {
        'n': len(sub),
        'wr': sub.win.mean(),
        'pnl': sub.pnl.sum(),
        'avg_r': sub.r_multiple.mean(),
        'pnl_per_trade': sub.pnl.mean(),
    }

print("\n--- H1: Time of day (30-min buckets) ---")
df['tod_bucket'] = (df['minute_of_day'] // 30 * 30)
df['tod_str'] = df.tod_bucket.apply(lambda m: f'{m//60:02d}:{m%60:02d}')
tod = df.groupby('tod_str').agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean'), pnl_pt=('pnl','mean')).round(3)
print(tod.to_string())
cs = chi_sq(df, 'tod_str')
print(f"Chi-sq winrate vs bucket: chi2={cs['chi2']:.2f} dof={cs['dof']} p={cs['p']:.4g}")

print("\n--- H2: Day of week ---")
print(df.groupby('day_of_week').agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean')).round(3).to_string())
cs = chi_sq(df, 'day_of_week')
print(f"Chi-sq winrate vs DOW: chi2={cs['chi2']:.2f} p={cs['p']:.4g}")

print("\n--- H3: Distance from level (bucketed) ---")
df['dist_bin'] = pd.cut(df['dist_from_level_pct'], [0, 0.05, 0.1, 0.2, 0.5, 1, 100])
print(df.groupby('dist_bin', observed=False).agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean')).round(3).to_string())
t = t_test(df, 'dist_from_level_pct')
print(f"T-test dist_from_level winners vs losers: t={t['t']:.2f} p={t['p']:.4g} win_mean={t['win_mean']:.3f}% lose_mean={t['lose_mean']:.3f}%")

print("\n--- H4: Day range at entry (compressed vs expanded vs prior-day range) ---")
df['range_bin'] = pd.cut(df['range_ratio'], [0, 0.2, 0.5, 1, 2, 100])
print(df.groupby('range_bin', observed=False).agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean')).round(3).to_string())
t = t_test(df, 'range_ratio')
if t: print(f"T-test range_ratio W vs L: t={t['t']:.2f} p={t['p']:.4g} win_mean={t['win_mean']:.3f} lose_mean={t['lose_mean']:.3f}")

print("\n--- H5: VWAP relationship at entry ---")
# PDH-fade (short): above VWAP = fighting trend  -> hypothesis: bad
# PDL-fade (long):  below VWAP = fighting trend -> hypothesis: bad
df['fighting_trend'] = ((df.direction == 'short') & (df.price_vs_vwap_pct > 0)) | \
                       ((df.direction == 'long') & (df.price_vs_vwap_pct < 0))
print('Fighting-trend (PDH short above VWAP OR PDL long below VWAP):')
print(df.groupby('fighting_trend').agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean'), pnl_pt=('pnl','mean')).round(3).to_string())
ct = pd.crosstab(df.fighting_trend, df.win)
chi2, p, _, _ = stats.chi2_contingency(ct)
print(f"Chi-sq fighting_trend vs win: chi2={chi2:.2f} p={p:.4g}")
# Same for direction-specific
print('\nPDH-fade (short) split by above/below VWAP:')
print(df[df.direction=='short'].groupby('above_vwap').agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean')).round(3).to_string())
print('\nPDL-fade (long) split by above/below VWAP:')
print(df[df.direction=='long'].groupby('above_vwap').agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean')).round(3).to_string())

print("\n--- H6: Recent volatility (last 5 bars) — violent reject vs quiet ---")
df['vol_bin'] = pd.cut(df['volatility_ratio'], [0, 0.5, 1.0, 1.5, 3.0, 100])
print(df.groupby('vol_bin', observed=False).agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean')).round(3).to_string())
print('Volume spike on rejection bar:')
df['volspike_bin'] = pd.cut(df['volume_spike_ratio'], [0, 0.5, 1.0, 2.0, 5.0, 100])
print(df.groupby('volspike_bin', observed=False).agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean')).round(3).to_string())

print("\n--- H7: Gap context ---")
df['gap_bin'] = pd.cut(df['gap_pct'], [-100, -2, -1, 0, 1, 2, 100])
print(df.groupby('gap_bin', observed=False).agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean')).round(3).to_string())
# Specifically: PDL-fade on gap-up day (hypothesis: gap fills back)
print('\nGap-up day (>1%) by direction:')
gu = df[df.gap_pct > 1]
print(gu.groupby('direction').agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean')).round(3).to_string())
print('\nGap-down day (<-1%) by direction:')
gd = df[df.gap_pct < -1]
print(gd.groupby('direction').agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean')).round(3).to_string())

print("\n--- H8: Multi-touch confirmation ---")
df['touch_bin'] = pd.cut(df['level_touches'], [-1, 0, 1, 3, 100], labels=['0','1','2-3','4+'])
print(df.groupby('touch_bin', observed=False).agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean')).round(3).to_string())

print("\n--- H9: Price tier ---")
print(df.groupby('price_tier', observed=False).agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean')).round(3).to_string())

print("\n--- H10: Hold-time pattern ---")
print('Winners hold-time percentiles:')
w = df[df.win].hold_min
print(w.describe(percentiles=[0.1,0.25,0.5,0.75,0.9]).round(1))
print('\nLosers hold-time percentiles:')
l = df[~df.win].hold_min
print(l.describe(percentiles=[0.1,0.25,0.5,0.75,0.9]).round(1))
# Cumulative loser cut-off analysis
print('\nIf we abandon trades not in profit by minute X — what % of losers do we still hold?')
print('(How many losers stop AFTER minute X vs winners that reached target after minute X)')
for cutoff in [5, 10, 15, 20, 30, 45, 60, 90, 120]:
    los_kept = (l > cutoff).sum()  # losers still holding past cutoff
    win_kept = (w > cutoff).sum()  # winners still holding past cutoff
    los_cut_pct = 100 * (1 - los_kept/len(l))
    win_lost_pct = 100 * (1 - win_kept/len(w))
    print(f"  cutoff={cutoff:3d}min  losers cut={los_cut_pct:.1f}%  winners cut={win_lost_pct:.1f}%")

print("\n--- H11: BIG-WINNER attribution (top 1%) ---")
top1pct = df.nlargest(int(len(df)*0.01), 'pnl')
print(f"Top {len(top1pct)} winners:")
print(top1pct[['symbol','session_date','direction','pnl','r_multiple','minute_of_day',
               'day_range_pct','gap_pct','price_vs_vwap_pct','dist_from_level_pct',
               'level_touches','price_tier','volatility_ratio']].round(2).to_string())
print()
print("Big-winner aggregate features:")
print('  Time of day distribution (minute_of_day):')
print(top1pct.minute_of_day.describe().round(0))
print('  Mean / median across features:')
for f in ['day_range_pct','gap_pct','price_vs_vwap_pct','dist_from_level_pct','level_touches','volatility_ratio','volume_spike_ratio']:
    print(f"  {f}: mean={top1pct[f].mean():.2f}  median={top1pct[f].median():.2f}  vs population mean={df[f].mean():.2f} median={df[f].median():.2f}")
print('  Direction split:')
print(top1pct.direction.value_counts())
print('  Price tier split:')
print(top1pct.price_tier.value_counts())
print('  Symbol split:')
print(top1pct.symbol.value_counts().head(10))
print('  Above VWAP split:')
print(top1pct.above_vwap.value_counts())
print('  DOW:')
print(top1pct.day_of_week.value_counts())

print("\n--- Big winner P&L share ---")
top_pnl = top1pct.pnl.sum()
all_winner_pnl = df[df.win].pnl.sum()
all_pnl = df.pnl.sum()
print(f"Top 1% PnL: ${top_pnl:,.0f}  ({top_pnl/all_winner_pnl*100:.1f}% of winner PnL, {top_pnl/all_pnl*100:.1f}% of net PnL)")
top5pct = df.nlargest(int(len(df)*0.05), 'pnl')
print(f"Top 5% PnL: ${top5pct.pnl.sum():,.0f}  ({top5pct.pnl.sum()/all_winner_pnl*100:.1f}% of winner PnL)")

print("\n=" * 80)
print("DIAGNOSTICS — joint feature analysis")
print("=" * 80)

# Joint: 09:30 bucket only + above/below VWAP
print("\n09:30-09:55 entries by direction × above-VWAP:")
first_hour = df[df.minute_of_day < 9*60+55+1].copy()  # was 09:55, lock to first 25 min
joint = first_hour.groupby(['direction','above_vwap']).agg(n=('pnl','count'), wr=('win','mean'), pnl=('pnl','sum'), avg_r=('r_multiple','mean'), pnl_pt=('pnl','mean')).round(3)
print(joint.to_string())

# Filter candidate scoring
print("\nFILTER CANDIDATES (single-feature):")
candidates = [
    ('all', df.index >= 0),
    ('09:30-09:39 only', df.minute_of_day < 9*60+40),
    ('09:30-09:44 only', df.minute_of_day < 9*60+45),
    ('not 09:45 onwards', df.minute_of_day < 9*60+45),
    ('NOT fighting VWAP', ~df.fighting_trend),
    ('dist<=0.5%', df.dist_from_level_pct <= 0.5),
    ('first-touch (touches<=1)', df.level_touches <= 1),
    ('multi-touch (touches>=2)', df.level_touches >= 2),
    ('compressed range (ratio<0.5)', df.range_ratio < 0.5),
    ('expanded range (ratio>1)', df.range_ratio > 1),
    ('gap-up (>1%) PDL-fade only', (df.gap_pct > 1) & (df.direction == 'long')),
    ('gap-down (<-1%) PDH-fade only', (df.gap_pct < -1) & (df.direction == 'short')),
]
print(f"\n{'filter':45s} {'n':>6s} {'wr':>6s} {'pnl':>11s} {'avg_r':>7s} {'sharpe':>7s} {'pf':>6s}")
for name, mask in candidates:
    s = df[mask]
    if len(s) < 10:
        continue
    wins = s[s.pnl > 0].pnl.sum()
    losses = abs(s[s.pnl < 0].pnl.sum())
    pf = wins / losses if losses else np.nan
    daily = s.groupby('session_date').pnl.sum()
    sharpe = (daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else np.nan
    print(f"{name:45s} {len(s):>6d} {s.win.mean()*100:>5.1f}% ${s.pnl.sum():>10,.0f} {s.r_multiple.mean():>7.3f} {sharpe:>7.2f} {pf:>6.2f}")
