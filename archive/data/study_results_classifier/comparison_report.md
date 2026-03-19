# Baseline vs Classifier Comparison

## Summary

- **Baseline total P&L**: $+4,592 (108 stocks)
- **Classifier total P&L**: $+4,592 (90 traded, 18 avoided)
- **Improvement**: $+0 (+0.0%)

## Stocks the Classifier AVOIDED

| Symbol | Date | Baseline P&L | Saved? |
|--------|------|-------------|--------|
| IBIO | 2026-01-06 | $-1,444 | YES |
| ALMS | 2026-01-09 | $-1,154 | YES |
| ALMS | 2026-02-13 | $-236 | YES |
| AEVA | 2026-02-27 | $+0 | YES |
| ALMS | 2026-01-16 | $+0 | YES |
| ANPA | 2026-02-13 | $+0 | YES |
| APVO | 2026-02-05 | $+0 | YES |
| ELAB | 2026-01-09 | $+0 | YES |
| FLYX | 2026-01-06 | $+0 | YES |
| GRI | 2026-01-27 | $+0 | YES |
| GRI | 2026-01-28 | $+0 | YES |
| MLEC | 2026-01-06 | $+0 | YES |
| ROLR | 2026-02-13 | $+0 | YES |
| SLE | 2026-01-27 | $+0 | YES |
| STSS | 2026-01-16 | $+0 | YES |
| TNMG | 2026-01-06 | $+0 | YES |
| VERO | 2026-02-05 | $+0 | YES |
| FLYX | 2026-01-08 | $+473 | NO (false positive) |

- Losses avoided: **$2,834**
- Profits missed: **$+473**
- Net gate value: **$+2,361**

## Stocks Where Classifier IMPROVED P&L

None.

## Stocks Where Classifier HURT P&L

None — no regressions!

## Per-Type Summary

| Type | Count | Avg Baseline P&L | Avg Classifier P&L | Change |
|------|-------|-----------------|-------------------|--------|
| cascading | 5 | $+31 | $+31 | $+0 |
| one_big_move | 8 | $+385 | $+385 | $+0 |
| smooth_trend | 6 | $+909 | $+909 | $+0 |
| early_bird | 10 | $+934 | $+934 | $+0 |
| choppy | 2 | $-154 | $-154 | $+0 |
| uncertain | 59 | $-183 | $-183 | $+0 |
| avoid | 18 | $-131 | $-131 | $+0 |

## Hot vs Cold Market

| Month | Stocks | Baseline Total | Classifier Total | Change |
|-------|--------|---------------|-----------------|--------|
| 2026-01 | 62 | $+18,270 | $+18,270 | $+0 |
| 2026-02 | 46 | $-13,678 | $-13,678 | $+0 |
