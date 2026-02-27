# Classifier Validation Report

**Stocks analyzed**: 108

## Classification Distribution

| Type | Count | Avg P&L | Win Rate | Traded? |
|------|-------|---------|----------|---------|
| cascading | 11 | $+646 | 31% | YES |
| one_big_move | 12 | $+330 | 40% | YES |
| smooth_trend | 11 | $-117 | 8% | YES |
| early_bird | 16 | $+561 | 35% | YES |
| uncertain | 37 | $-336 | 17% | YES |
| avoid | 21 | $-82 | 40% | NO |

## Gate Effectiveness

- Stocks classified **AVOID**: 21
- Their actual avg P&L: **$-82** (confirms gate works)
- Stocks that **PASSED** the gate: 87
- Their actual avg P&L: **$+72**

## P&L Saved by Gate

- Stocks the gate would skip that had trades: 5
- Losses that would be avoided: **$2,613**
- Losers in avoided group: 3
- Winners in avoided group: 2 (would be false positives)
- Profits that would be missed: **$+901**
- Net savings: **$+1,712**

## BE Exit Suppression Hypothetical

For non-cascading types, what if BE exits had been suppressed?

### one_big_move (suppress BE under 1.5R)
- Stocks: 12
- Total BE exits: 0
- BE exits where stock went higher: 0
- Hypothetical additional P&L if held to 30m high: **$+0**

### smooth_trend (suppress BE under 1.0R)
- Stocks: 11
- Total BE exits: 0
- BE exits where stock went higher: 0
- Hypothetical additional P&L if held to 30m high: **$+0**

### early_bird (suppress BE under 0.5R)
- Stocks: 16
- Total BE exits: 0
- BE exits where stock went higher: 0
- Hypothetical additional P&L if held to 30m high: **$+0**

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
| avoid | - | - | 2 | 16 | - | 3 | - |
| cascading | 3 | 1 | - | 1 | - | 1 | 5 |
| early_bird | - | 6 | 3 | 4 | 2 | 1 | - |
| one_big_move | 1 | 2 | 5 | - | 1 | 2 | 1 |
| smooth_trend | - | - | 1 | 6 | - | 4 | - |
| uncertain | 1 | 2 | 4 | 20 | - | 7 | 3 |

## Notable Misclassifications

Stocks where classifier would have made things WORSE:

- **MNTS 2026-02-06**: P&L $+862 but classified AVOID (VWAP=3.2%, NH=0, range=6.4%)

## Top Performers by Classified Type

### cascading
- VERO 2026-01-16: $+6,890 (NH=15, VWAP=55.8%, range=92.2%)
- MOVE 2026-01-27: $+5,502 (NH=7, VWAP=7.4%, range=13.6%)
- BATL 2026-02-27: $+1,972 (NH=17, VWAP=12.8%, range=47.4%)
- TWG 2026-01-20: $+0 (NH=15, VWAP=33.9%, range=104.2%)
- INDO 2026-02-27: $-487 (NH=10, VWAP=6.4%, range=16.3%)

### one_big_move
- ALMS 2026-01-06: $+3,407 (NH=0, VWAP=32.1%, range=105.0%)
- ANPA 2026-01-09: $+2,088 (NH=1, VWAP=30.7%, range=136.2%)
- HIND 2026-01-27: $+1,621 (NH=0, VWAP=24.7%, range=153.7%)
- ENVB 2026-02-19: $+474 (NH=1, VWAP=22.2%, range=101.8%)
- MLEC 2026-02-13: $+173 (NH=0, VWAP=32.2%, range=158.0%)

### smooth_trend
- ROLR 2026-01-14: $+1,413 (NH=3, VWAP=15.8%, range=174.3%)
- AGIG 2026-02-27: $+0 (NH=9, VWAP=4.6%, range=12.6%)
- ELAB 2026-01-09: $+0 (NH=3, VWAP=3.1%, range=4.7%)
- FEED 2026-01-16: $+0 (NH=3, VWAP=1.9%, range=4.3%)
- HCTI 2026-02-27: $+0 (NH=3, VWAP=5.1%, range=13.9%)

### early_bird
- APVO 2026-01-09: $+7,622 (NH=1, VWAP=13.2%, range=58.1%)
- GWAV 2026-01-16: $+6,735 (NH=5, VWAP=17.1%, range=57.3%)
- CDIO 2026-02-27: $+791 (NH=3, VWAP=8.6%, range=19.2%)
- AZI 2026-01-06: $+782 (NH=1, VWAP=11.2%, range=24.0%)
- BNAI 2026-02-05: $+160 (NH=5, VWAP=21.0%, range=28.6%)
