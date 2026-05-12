# Chop Gate v3 — `hod_recent` Sub-Gate Validation Report

**Date generated:** 2026-05-12T13:38:32-04:00
**Source repo:** /Users/duffy/warrior_bot_v2
**Sub-gate under test:** `hod_recent` (others = observe-only)
**Sample size:** 21 closed WB trades

## Counts (this sub-gate alone)

| Outcome | Count |
|---|---:|
| blocked, was loser (saved) | 2 |
| blocked, was winner (false positive) | 0 |
| passed, was winner (preserved) | 4 |
| passed, was loser (not caught) | 15 |

## Acceptance criteria

| # | Criterion | Result | Detail |
|---|---|---|---|
| 1 | Advisory 1: zero winners blocked | PASS | 4/4 winners preserved |
| 2 | Advisory 2: at least 1 loser blocked | PASS | 2/17 losers blocked |
| 3 | Advisory 3: top-3 winners preserved | PASS | ATRA 2026-05-08 $+2,499.59 (PASS), SST 2026-05-11 $+2,090.40 (PASS), FATN 2026-05-05 $+1,073.59 (PASS) |

**Overall:** PASS

## Per-trade decisions (chronological)

| Date | Time ET | Sym | Setup | Score | Outcome | P&L | R | Bars | `hod_recent` verdict | Reason |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-05-05 | 10:42 | CLNN | subbot | 7 | LOSS | $-653.04 | -1.03 | 134 | PASS | hod_recent_ok(0<2) |
| 2026-05-05 | 11:08 | CLNN | subbot | 7 | LOSS | $-514.64 | -1.89 | 160 | PASS | hod_recent_ok(0<2) |
| 2026-05-05 | 11:56 | FATN | subbot | 8 | LOSS | $-955.38 | -1.26 | 174 | BLOCK | hod_recent_attempts=2_no_bottom_fish(vwap=Y,macd_up=N,below_mid=N) |
| 2026-05-05 | 14:37 | CLNN | subbot | 9 | LOSS | $-673.20 | -1.35 | 365 | PASS | hod_recent_ok(0<2) |
| 2026-05-05 | 14:39 | FATN | subbot | 8 | WIN | $+1,073.59 | +1.46 | 324 | PASS | hod_recent_ok(1<2) |
| 2026-05-05 | 14:56 | CLNN | subbot | 7 | LOSS | $-1,051.82 | -1.03 | 384 | PASS | hod_recent_ok(0<2) |
| 2026-05-08 | 13:58 | FATN | subbot | 10 | LOSS | $-771.60 | -1.04 | 440 | PASS | hod_recent_ok(0<2) |
| 2026-05-08 | 15:01 | SST | subbot | 9 | LOSS | $-250.62 | -0.40 | 620 | BLOCK | hod_recent_attempts=2_no_bottom_fish(vwap=Y,macd_up=N,below_mid=N) |
| 2026-05-08 | 17:09 | ATRA | subbot | 10 | WIN | $+2,499.59 | +2.51 | 772 | PASS | hod_recent_ok(0<2) |
| 2026-05-11 | 10:12 | NVOX | subbot | 9 | LOSS | $-37.09 | -0.47 | 372 | PASS | hod_recent_ok(0<2) |
| 2026-05-11 | 13:52 | ATRA | subbot | 10 | LOSS | $-513.24 | -1.16 | 550 | PASS | hod_recent_ok(0<2) |
| 2026-05-11 | 14:18 | SST | subbot | 9 | WIN | $+2,090.40 | +3.28 | 555 | PASS | hod_recent_ok(0<2) |
| 2026-05-11 | 18:30 | ATRA | subbot | 10 | LOSS | $-778.36 | -1.43 | 806 | PASS | hod_recent_ok(1<2) |
| 2026-05-12 | 05:31 | TRAW | wb_bot | 10 | LOSS | $-985.20 | -1.14 | 85 | PASS | hod_recent_ok(0<2) |
| 2026-05-12 | 05:48 | ODYS | wb_bot | 8 | LOSS | $-856.48 | -1.55 | 109 | PASS | hod_recent_ok(0<2) |
| 2026-05-12 | 06:29 | XOS | wb_bot | 10 | LOSS | $-735.27 | -1.20 | 150 | PASS | hod_recent_ok(0<2) |
| 2026-05-12 | 08:16 | ENSC | subbot | 9 | LOSS | $-643.54 | -1.03 | 252 | PASS | hod_recent_ok(0<2) |
| 2026-05-12 | 11:20 | SST | subbot | 10 | LOSS | $-869.55 | -1.10 | 356 | PASS | hod_recent_ok(0<2) |
| 2026-05-12 | 11:41 | FATN | wb_bot | 8 | LOSS | $-1,381.20 | -2.04 | 281 | PASS | hod_recent_attempts=3_but_bottom_fish(vwap=Y,macd_up=Y,below_mid=N) |
| 2026-05-12 | 12:20 | ATRA | wb_bot | 8 | WIN | $+41.15 | +0.23 | 393 | PASS | hod_recent_ok(0<2) |
| 2026-05-12 | 12:26 | FATN | wb_bot | 9 | LOSS | $-1,126.72 | -1.36 | 316 | PASS | hod_recent_ok(0<2) |

## Notes

- Per-sub-gate validation runs each sub-gate INDEPENDENTLY (other sub-gates in observe-only). Bars + MACD reconstructed from tick cache up to the exact moment of arm (no future leakage).
- Cross-session blacklist is built incrementally — each trade's decision sees only prior-day trades closed in the dataset.
- Advisory only — user reviews report before flipping WB_CG3_HOD_RECENT_ENABLED=1. Expected: FATN 5/12 entries blocked, FATN 5/5 14:39 winner passed.
