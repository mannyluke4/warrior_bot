# Phase 2.2 Comparison: Baseline vs Classifier+Suppression

## Summary

| Config | Stocks Traded | Total P&L | Avg P&L/Stock |
|--------|--------------|-----------|---------------|
| Baseline (OFF) | 108 | $+4,592 | $+43 |
| Classifier (gate only) | 90 | $+6,953 | $+77 |
| **Classifier+Suppress** | **90** | **$+5,332** | **$+59** |

- Gate avoided: 18 stocks
- Suppression impact: **$-1,621** on traded stocks

## Stocks the Classifier AVOIDED (Gate)

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

## Exit Suppression Impact

| Symbol | Date | Type | Baseline P&L | Suppress P&L | Delta |
|--------|------|------|-------------|-------------|-------|
| ALMS | 2026-01-06 | one_big_move | $+3,407 | $+3,776 | $+369 |
| SNSE | 2026-02-18 | one_big_move | $+88 | $-249 | $-337 |
| HIND | 2026-01-27 | one_big_move | $+1,621 | $-33 | $-1,654 |

- Stocks improved: **1** ($+369)
- Stocks regressed: **2** ($-1,991)
- Net suppression value: **$-1,621**

## Regression Check

Stocks where classifier+suppress P&L DECREASED vs baseline:

| Symbol | Date | Type | Baseline | Suppress | Regression |
|--------|------|------|----------|----------|------------|
| HIND | 2026-01-27 | one_big_move | $+1,621 | $-33 | $-1,654 |
| SNSE | 2026-02-18 | one_big_move | $+88 | $-249 | $-337 |

## Per-Type Impact

| Type | Stocks | Baseline Avg | Suppress Avg | Delta |
|------|--------|-------------|-------------|-------|
| cascading | 5 | $+31 | $+31 | $+0 |
| one_big_move | 8 | $+385 | $+183 | $-203 |
| smooth_trend | 6 | $+909 | $+909 | $+0 |
| early_bird | 10 | $+934 | $+934 | $+0 |
| choppy | 2 | $-154 | $-154 | $+0 |
| uncertain | 59 | $-183 | $-183 | $+0 |
| avoid | 18 | $-131 | $-131 | $+0 |

## Hot vs Cold Market

| Month | Stocks | Baseline | Gate Only | Gate+Suppress |
|-------|--------|----------|----------|---------------|
| 2026-01 | 62 | $+18,270 | $+20,395 | $+16,985 |
| 2026-02 | 46 | $-13,678 | $-13,442 | $-14,015 |

## Today's Session (2026-02-27)

| Symbol | Type | Baseline P&L | Suppress P&L | Delta |
|--------|------|-------------|-------------|-------|
| BATL | uncertain | $+1,972 | $+1,972 | $+0 |
| CDIO | uncertain | $+791 | $+791 | $+0 |
| STRZ | cascading | $+94 | $+94 | $+0 |
| PBYI | uncertain | $+21 | $+21 | $+0 |
| AEVA | avoid | $+0 | $+0 | $+0 |
| AGIG | smooth_trend | $+0 | $+0 | $+0 |
| HCTI | uncertain | $+0 | $+0 | $+0 |
| KORE | uncertain | $+0 | $+0 | $+0 |
| NAMM | uncertain | $+0 | $+0 | $+0 |
| NGNE | uncertain | $+0 | $+0 | $+0 |
| RBNE | uncertain | $+0 | $+0 | $+0 |
| RUN | early_bird | $+0 | $+0 | $+0 |
| SND | uncertain | $+0 | $+0 | $+0 |
| LBGJ | one_big_move | $-110 | $-110 | $+0 |
| XYZ | uncertain | $-248 | $-248 | $+0 |
| INDO | uncertain | $-487 | $-487 | $+0 |
| ARLO | smooth_trend | $-692 | $-692 | $+0 |
| TMDE | uncertain | $-707 | $-707 | $+0 |
| ANNA | smooth_trend | $-1,088 | $-1,088 | $+0 |
| FIGS | uncertain | $-1,103 | $-1,103 | $+0 |
| TSSI | uncertain | $-1,116 | $-1,116 | $+0 |
| MRM | uncertain | $-1,417 | $-1,417 | $+0 |
| AAOI | cascading | $-1,950 | $-1,950 | $+0 |
| ONMD | uncertain | $-2,146 | $-2,146 | $+0 |
| XWEL | early_bird | $-2,949 | $-2,949 | $+0 |

- Stocks traded: 24, avoided: 1
- Baseline total: $-11,135
- Suppress total: $-11,135
- Delta: $+0
