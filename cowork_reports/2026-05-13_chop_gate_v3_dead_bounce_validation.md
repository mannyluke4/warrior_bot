# Chop Gate v3 — `dead_bounce` Sub-Gate Validation Report

**Date generated:** 2026-05-12T13:38:32-04:00
**Source repo:** /Users/duffy/warrior_bot_v2
**Sub-gate under test:** `dead_bounce` (others = observe-only)
**Sample size:** 21 closed WB trades

## Counts (this sub-gate alone)

| Outcome | Count |
|---|---:|
| blocked, was loser (saved) | 3 |
| blocked, was winner (false positive) | 2 |
| passed, was winner (preserved) | 2 |
| passed, was loser (not caught) | 14 |

## Acceptance criteria

| # | Criterion | Result | Detail |
|---|---|---|---|
| 1 | Advisory 1: zero winners blocked | FAIL | 2/4 winners preserved |
| 2 | Advisory 2: at least 1 loser blocked | PASS | 3/17 losers blocked |
| 3 | Advisory 3: top-3 winners preserved | FAIL | ATRA 2026-05-08 $+2,499.59 (BLOCK), SST 2026-05-11 $+2,090.40 (PASS), FATN 2026-05-05 $+1,073.59 (PASS) |

**Overall:** FAIL

## Per-trade decisions (chronological)

| Date | Time ET | Sym | Setup | Score | Outcome | P&L | R | Bars | `dead_bounce` verdict | Reason |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-05-05 | 10:42 | CLNN | subbot | 7 | LOSS | $-653.04 | -1.03 | 134 | PASS | dead_bounce_strong_volume(ratio=19.57>= 0.70) |
| 2026-05-05 | 11:08 | CLNN | subbot | 7 | LOSS | $-514.64 | -1.89 | 160 | PASS | dead_bounce_strong_volume(ratio=3.92>= 0.70) |
| 2026-05-05 | 11:56 | FATN | subbot | 8 | LOSS | $-955.38 | -1.26 | 174 | PASS | dead_bounce_reclaimed(price=$3.14>=mid=$3.13) |
| 2026-05-05 | 14:37 | CLNN | subbot | 9 | LOSS | $-673.20 | -1.35 | 365 | PASS | dead_bounce_strong_volume(ratio=2.58>= 0.70) |
| 2026-05-05 | 14:39 | FATN | subbot | 8 | WIN | $+1,073.59 | +1.46 | 324 | PASS | dead_bounce_hod_not_early(age=197m) |
| 2026-05-05 | 14:56 | CLNN | subbot | 7 | LOSS | $-1,051.82 | -1.03 | 384 | PASS | dead_bounce_strong_volume(ratio=13.30>= 0.70) |
| 2026-05-08 | 13:58 | FATN | subbot | 10 | LOSS | $-771.60 | -1.04 | 440 | PASS | dead_bounce_strong_volume(ratio=7.60>= 0.70) |
| 2026-05-08 | 15:01 | SST | subbot | 9 | LOSS | $-250.62 | -0.40 | 620 | PASS | dead_bounce_reclaimed(price=$3.99>=mid=$3.72) |
| 2026-05-08 | 17:09 | ATRA | subbot | 10 | WIN | $+2,499.59 | +2.51 | 772 | BLOCK | dead_bounce_pattern(drift=1,cum=$2.08,vol_ratio=0.18) |
| 2026-05-11 | 10:12 | NVOX | subbot | 9 | LOSS | $-37.09 | -0.47 | 372 | PASS | dead_bounce_reclaimed(price=$16.25>=mid=$16.00) |
| 2026-05-11 | 13:52 | ATRA | subbot | 10 | LOSS | $-513.24 | -1.16 | 550 | PASS | dead_bounce_hod_not_early(age=230m) |
| 2026-05-11 | 14:18 | SST | subbot | 9 | WIN | $+2,090.40 | +3.28 | 555 | PASS | dead_bounce_strong_volume(ratio=6.42>= 0.70) |
| 2026-05-11 | 18:30 | ATRA | subbot | 10 | LOSS | $-778.36 | -1.43 | 806 | PASS | dead_bounce_hod_not_early(age=503m) |
| 2026-05-12 | 05:31 | TRAW | wb_bot | 10 | LOSS | $-985.20 | -1.14 | 85 | PASS | dead_bounce_strong_volume(ratio=0.77>= 0.70) |
| 2026-05-12 | 05:48 | ODYS | wb_bot | 8 | LOSS | $-856.48 | -1.55 | 109 | PASS | dead_bounce_reclaimed(price=$4.67>=mid=$4.66) |
| 2026-05-12 | 06:29 | XOS | wb_bot | 10 | LOSS | $-735.27 | -1.20 | 150 | BLOCK | dead_bounce_pattern(drift=0,cum=$1.05,vol_ratio=0.02) |
| 2026-05-12 | 08:16 | ENSC | subbot | 9 | LOSS | $-643.54 | -1.03 | 252 | BLOCK | dead_bounce_pattern(drift=1,cum=$0.07,vol_ratio=0.17) |
| 2026-05-12 | 11:20 | SST | subbot | 10 | LOSS | $-869.55 | -1.10 | 356 | PASS | dead_bounce_reclaimed(price=$3.94>=mid=$3.89) |
| 2026-05-12 | 11:41 | FATN | wb_bot | 8 | LOSS | $-1,381.20 | -2.04 | 281 | PASS | dead_bounce_strong_volume(ratio=2.00>= 0.70) |
| 2026-05-12 | 12:20 | ATRA | wb_bot | 8 | WIN | $+41.15 | +0.23 | 393 | BLOCK | dead_bounce_pattern(drift=0,cum=$1.02,vol_ratio=0.41) |
| 2026-05-12 | 12:26 | FATN | wb_bot | 9 | LOSS | $-1,126.72 | -1.36 | 316 | BLOCK | dead_bounce_pattern(drift=0,cum=$0.24,vol_ratio=0.18) |

## Notes

- Per-sub-gate validation runs each sub-gate INDEPENDENTLY (other sub-gates in observe-only). Bars + MACD reconstructed from tick cache up to the exact moment of arm (no future leakage).
- Cross-session blacklist is built incrementally — each trade's decision sees only prior-day trades closed in the dataset.
- Advisory only — user reviews report before flipping WB_CG3_DEAD_BOUNCE_ENABLED=1. Expected: FATN 5/8 13:58 blocked, all winners passed.
