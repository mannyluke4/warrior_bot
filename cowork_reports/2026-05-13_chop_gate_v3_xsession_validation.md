# Chop Gate v3 — `xsession_bl` Sub-Gate Validation Report

**Date generated:** 2026-05-12T13:38:32-04:00
**Source repo:** /Users/duffy/warrior_bot_v2
**Sub-gate under test:** `xsession_bl` (others = observe-only)
**Sample size:** 21 closed WB trades

## Counts (this sub-gate alone)

| Outcome | Count |
|---|---:|
| blocked, was loser (saved) | 0 |
| blocked, was winner (false positive) | 0 |
| passed, was winner (preserved) | 4 |
| passed, was loser (not caught) | 17 |

## Acceptance criteria

| # | Criterion | Result | Detail |
|---|---|---|---|
| 1 | Advisory 1: zero winners blocked | PASS | 4/4 winners preserved |
| 2 | Advisory 2: at least 1 loser blocked | FAIL | 0/17 losers blocked |
| 3 | Advisory 3: top-3 winners preserved | PASS | ATRA 2026-05-08 $+2,499.59 (PASS), SST 2026-05-11 $+2,090.40 (PASS), FATN 2026-05-05 $+1,073.59 (PASS) |

**Overall:** FAIL

## Per-trade decisions (chronological)

| Date | Time ET | Sym | Setup | Score | Outcome | P&L | R | Bars | `xsession_bl` verdict | Reason |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-05-05 | 10:42 | CLNN | subbot | 7 | LOSS | $-653.04 | -1.03 | 134 | PASS | xbl_insufficient_history(0<3) |
| 2026-05-05 | 11:08 | CLNN | subbot | 7 | LOSS | $-514.64 | -1.89 | 160 | PASS | xbl_insufficient_history(0<3) |
| 2026-05-05 | 11:56 | FATN | subbot | 8 | LOSS | $-955.38 | -1.26 | 174 | PASS | xbl_insufficient_history(0<3) |
| 2026-05-05 | 14:37 | CLNN | subbot | 9 | LOSS | $-673.20 | -1.35 | 365 | PASS | xbl_insufficient_history(0<3) |
| 2026-05-05 | 14:39 | FATN | subbot | 8 | WIN | $+1,073.59 | +1.46 | 324 | PASS | xbl_insufficient_history(0<3) |
| 2026-05-05 | 14:56 | CLNN | subbot | 7 | LOSS | $-1,051.82 | -1.03 | 384 | PASS | xbl_insufficient_history(0<3) |
| 2026-05-08 | 13:58 | FATN | subbot | 10 | LOSS | $-771.60 | -1.04 | 440 | PASS | xbl_insufficient_history(2<3) |
| 2026-05-08 | 15:01 | SST | subbot | 9 | LOSS | $-250.62 | -0.40 | 620 | PASS | xbl_insufficient_history(0<3) |
| 2026-05-08 | 17:09 | ATRA | subbot | 10 | WIN | $+2,499.59 | +2.51 | 772 | PASS | xbl_insufficient_history(0<3) |
| 2026-05-11 | 10:12 | NVOX | subbot | 9 | LOSS | $-37.09 | -0.47 | 372 | PASS | xbl_insufficient_history(0<3) |
| 2026-05-11 | 13:52 | ATRA | subbot | 10 | LOSS | $-513.24 | -1.16 | 550 | PASS | xbl_insufficient_history(1<3) |
| 2026-05-11 | 14:18 | SST | subbot | 9 | WIN | $+2,090.40 | +3.28 | 555 | PASS | xbl_insufficient_history(1<3) |
| 2026-05-11 | 18:30 | ATRA | subbot | 10 | LOSS | $-778.36 | -1.43 | 806 | PASS | xbl_insufficient_history(1<3) |
| 2026-05-12 | 05:31 | TRAW | wb_bot | 10 | LOSS | $-985.20 | -1.14 | 85 | PASS | xbl_insufficient_history(0<3) |
| 2026-05-12 | 05:48 | ODYS | wb_bot | 8 | LOSS | $-856.48 | -1.55 | 109 | PASS | xbl_insufficient_history(0<3) |
| 2026-05-12 | 06:29 | XOS | wb_bot | 10 | LOSS | $-735.27 | -1.20 | 150 | PASS | xbl_insufficient_history(0<3) |
| 2026-05-12 | 08:16 | ENSC | subbot | 9 | LOSS | $-643.54 | -1.03 | 252 | PASS | xbl_insufficient_history(0<3) |
| 2026-05-12 | 11:20 | SST | subbot | 10 | LOSS | $-869.55 | -1.10 | 356 | PASS | xbl_insufficient_history(2<3) |
| 2026-05-12 | 11:41 | FATN | wb_bot | 8 | LOSS | $-1,381.20 | -2.04 | 281 | PASS | xbl_ok(rsum=-0.84,w=1,l=2) |
| 2026-05-12 | 12:20 | ATRA | wb_bot | 8 | WIN | $+41.15 | +0.23 | 393 | PASS | xbl_ok(rsum=-0.08,w=1,l=2) |
| 2026-05-12 | 12:26 | FATN | wb_bot | 9 | LOSS | $-1,126.72 | -1.36 | 316 | PASS | xbl_ok(rsum=-0.84,w=1,l=2) |

## Notes

- Per-sub-gate validation runs each sub-gate INDEPENDENTLY (other sub-gates in observe-only). Bars + MACD reconstructed from tick cache up to the exact moment of arm (no future leakage).
- Cross-session blacklist is built incrementally — each trade's decision sees only prior-day trades closed in the dataset.
- Advisory only — flipping WB_CG3_XSESSION_BL_ENABLED=1 is Monday 5/18. Expected: FATN blacklisted by 5/12, ATRA never blacklisted, CLNN not blacklisted by THIS gate (CLNN handled by MACD same-day).
