# Classifier Validation Report

**Stocks analyzed**: 108

## Classification Distribution

| Type | Count | Avg P&L | Win Rate | Traded? |
|------|-------|---------|----------|---------|
| cascading | 5 | $+1,241 | 44% | YES |
| one_big_move | 12 | $+330 | 40% | YES |
| smooth_trend | 1 | $+1,413 | 40% | YES |
| early_bird | 16 | $+561 | 35% | YES |
| uncertain | 49 | $-291 | 15% | YES |
| avoid | 25 | $-68 | 40% | NO |

## Gate Effectiveness

- Stocks classified **AVOID**: 25
- Their actual avg P&L: **$-68** (confirms gate works)
- Stocks that **PASSED** the gate: 83
- Their actual avg P&L: **$+76**

## P&L Saved by Gate

- Stocks the gate would skip that had trades: 5
- Losses that would be avoided: **$2,613**
- Losers in avoided group: 3
- Winners in avoided group: 2 (would be false positives)
- Profits that would be missed: **$+901**
- Net savings: **$+1,712**

## Exit Suppression Hypothetical

For each type, what if BE/TW exits below the profile's R threshold had been suppressed?

### one_big_move (BE < 1.5R, TW < 2.0R)
- Stocks: 12
- **BE exits**: 17 total, **15 would be suppressed**
  - Of suppressed: 16 stock went higher afterward
  - Hypothetical gain: **$+23,914** / loss: **$-1,606**
- **TW exits**: 2 total, **1 would be suppressed**
  - Hypothetical gain: **$+2,036** / loss: **$-0**
- **Net impact**: **$+24,344**

### smooth_trend (BE < 1.0R, TW < 1.0R)
- Stocks: 1
- **BE exits**: 4 total, **3 would be suppressed**
  - Of suppressed: 4 stock went higher afterward
  - Hypothetical gain: **$+112,961** / loss: **$-0**
- **TW exits**: 0 total, **0 would be suppressed**
- **Net impact**: **$+112,961**

### early_bird (BE < 0.5R, TW < 0.5R)
- Stocks: 16
- **BE exits**: 19 total, **14 would be suppressed**
  - Of suppressed: 16 stock went higher afterward
  - Hypothetical gain: **$+15,925** / loss: **$-5,306**
- **TW exits**: 0 total, **0 would be suppressed**
- **Net impact**: **$+10,619**

### cascading (BE < 0.0R, TW < 0.0R)
- Stocks: 5
- **BE exits**: 7 total, **0 would be suppressed**
- **TW exits**: 2 total, **0 would be suppressed**
- **Net impact**: **$+0**

## Actual Best Type (Hindsight)

| Actual Type | Count | Avg P&L |
|-------------|-------|---------|
| cascading | 5 | $+3,080 |
| choppy | 11 | $-353 |
| mixed | 15 | $+239 |
| no_trade | 47 | $+0 |
| one_big_move | 3 | $+5,482 |
| should_have_avoided | 18 | $-910 |
| smooth_trend_clipped | 9 | $-1,176 |

## Confusion Matrix: Classified vs Actual

| Classified \ Actual | cascading | choppy | mixed | no_trade | one_big_move | should_have_avoided | smooth_trend_clipped |
|---|---|---|---|---|---|---|---|
| avoid | - | - | 2 | 20 | - | 3 | - |
| cascading | 1 | 1 | - | 1 | - | - | 2 |
| early_bird | - | 6 | 3 | 4 | 2 | 1 | - |
| one_big_move | 1 | 2 | 5 | - | 1 | 2 | 1 |
| smooth_trend | - | - | 1 | - | - | - | - |
| uncertain | 3 | 2 | 4 | 22 | - | 12 | 6 |

## Notable Misclassifications

Stocks where classifier would have made things WORSE:

- **MNTS 2026-02-06**: P&L $+862 but classified AVOID (VWAP=3.2%, NH=0, range=6.4%)

## Top Performers by Classified Type

### cascading
- VERO 2026-01-16: $+6,890 (NH=15, VWAP=55.8%, range=92.2%)
- BATL 2026-02-27: $+1,972 (NH=17, VWAP=12.8%, range=47.4%)
- TWG 2026-01-20: $+0 (NH=15, VWAP=33.9%, range=104.2%)
- TMDE 2026-02-27: $-707 (NH=6, VWAP=8.1%, range=21.2%)
- AAOI 2026-02-27: $-1,950 (NH=8, VWAP=8.8%, range=18.6%)

### one_big_move
- ALMS 2026-01-06: $+3,407 (NH=0, VWAP=32.1%, range=105.0%)
- ANPA 2026-01-09: $+2,088 (NH=1, VWAP=30.7%, range=136.2%)
- HIND 2026-01-27: $+1,621 (NH=0, VWAP=24.7%, range=153.7%)
- ENVB 2026-02-19: $+474 (NH=1, VWAP=22.2%, range=101.8%)
- MLEC 2026-02-13: $+173 (NH=0, VWAP=32.2%, range=158.0%)

### smooth_trend
- ROLR 2026-01-14: $+1,413 (NH=3, VWAP=15.8%, range=174.3%)

### early_bird
- APVO 2026-01-09: $+7,622 (NH=1, VWAP=13.2%, range=58.1%)
- GWAV 2026-01-16: $+6,735 (NH=5, VWAP=17.1%, range=57.3%)
- CDIO 2026-02-27: $+791 (NH=3, VWAP=8.6%, range=19.2%)
- AZI 2026-01-06: $+782 (NH=1, VWAP=11.2%, range=24.0%)
- BNAI 2026-02-05: $+160 (NH=5, VWAP=21.0%, range=28.6%)
