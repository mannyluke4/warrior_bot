# Chop Gate v3 — Historical Validation Report

**Date generated:** 2026-05-12T13:38:32-04:00
**Source repo:** /Users/duffy/warrior_bot_v2
**Sample size:** 21 closed WB trades

## Bucket counts

| Outcome | Count |
|---|---:|
| blocked, was loser (saved) | 2 |
| blocked, was winner (false positive) | 0 |
| passed, was winner (preserved) | 4 |
| passed, was loser (not caught) | 15 |

## Acceptance criteria

| # | Criterion | Result | Detail |
|---|---|---|---|
| 1 | Criterion 1: blocked losers / total losers >= 60% | FAIL | 2/17 = 12% (threshold 60%) |
| 2 | Criterion 2: passed winners / total winners >= 90% | PASS | 4/4 = 100% (threshold 90%) |
| 3 | Criterion 3: top-3 winners by P&L all preserved | PASS | ATRA 2026-05-08 $+2,499.59 (PASS), SST 2026-05-11 $+2,090.40 (PASS), FATN 2026-05-05 $+1,073.59 (PASS) |
| 4 | Criterion 4: all FATN losses blocked | FAIL | 2026-05-05 $-955.38 PASS, 2026-05-08 $-771.60 PASS, 2026-05-12 $-1,381.20 PASS, 2026-05-12 $-1,126.72 PASS |

**Overall:** FAIL

## Per-trade decisions (chronological)

| Date | Time ET | Sym | Setup | Score | Outcome | P&L | R | Bars | MACD-ready | failed_HOD | MACD-curl | no-followthrough | Blacklisted | v3 decision | Reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-05-05 | 10:42 | CLNN | subbot | 7 | LOSS | $-653.04 | -1.03 | 134 | Y | 0 | Y | N | N | BLOCK | macd:macd_rolling_over |
| 2026-05-05 | 11:08 | CLNN | subbot | 7 | LOSS | $-514.64 | -1.89 | 160 | Y | 0 | Y | N | N | BLOCK | macd:macd_rolling_over |
| 2026-05-05 | 11:56 | FATN | subbot | 8 | LOSS | $-955.38 | -1.26 | 174 | Y | 5 | N | N | N | PASS | passed_all_enabled |
| 2026-05-05 | 14:37 | CLNN | subbot | 9 | LOSS | $-673.20 | -1.35 | 365 | Y | 0 | N | N | N | PASS | passed_all_enabled |
| 2026-05-05 | 14:39 | FATN | subbot | 8 | WIN | $+1,073.59 | +1.46 | 324 | Y | 4 | N | N | N | PASS | passed_all_enabled |
| 2026-05-05 | 14:56 | CLNN | subbot | 7 | LOSS | $-1,051.82 | -1.03 | 384 | Y | 0 | N | N | Y | PASS | passed_all_enabled |
| 2026-05-08 | 13:58 | FATN | subbot | 10 | LOSS | $-771.60 | -1.04 | 440 | Y | 0 | N | N | N | PASS | passed_all_enabled |
| 2026-05-08 | 15:01 | SST | subbot | 9 | LOSS | $-250.62 | -0.40 | 620 | Y | 2 | N | N | N | PASS | passed_all_enabled |
| 2026-05-08 | 17:09 | ATRA | subbot | 10 | WIN | $+2,499.59 | +2.51 | 772 | Y | 0 | N | N | N | PASS | passed_all_enabled |
| 2026-05-11 | 10:12 | NVOX | subbot | 9 | LOSS | $-37.09 | -0.47 | 372 | Y | 0 | N | N | N | PASS | passed_all_enabled |
| 2026-05-11 | 13:52 | ATRA | subbot | 10 | LOSS | $-513.24 | -1.16 | 550 | Y | 0 | N | N | N | PASS | passed_all_enabled |
| 2026-05-11 | 14:18 | SST | subbot | 9 | WIN | $+2,090.40 | +3.28 | 555 | Y | 0 | N | N | N | PASS | passed_all_enabled |
| 2026-05-11 | 18:30 | ATRA | subbot | 10 | LOSS | $-778.36 | -1.43 | 806 | Y | 1 | N | N | N | PASS | passed_all_enabled |
| 2026-05-12 | 05:31 | TRAW | wb_bot | 10 | LOSS | $-985.20 | -1.14 | 85 | Y | 1 | N | N | N | PASS | passed_all_enabled |
| 2026-05-12 | 05:48 | ODYS | wb_bot | 8 | LOSS | $-856.48 | -1.55 | 109 | Y | 4 | N | N | N | PASS | passed_all_enabled |
| 2026-05-12 | 06:29 | XOS | wb_bot | 10 | LOSS | $-735.27 | -1.20 | 150 | Y | 0 | N | N | N | PASS | passed_all_enabled |
| 2026-05-12 | 08:16 | ENSC | subbot | 9 | LOSS | $-643.54 | -1.03 | 252 | Y | 0 | N | N | N | PASS | passed_all_enabled |
| 2026-05-12 | 11:20 | SST | subbot | 10 | LOSS | $-869.55 | -1.10 | 356 | Y | 0 | N | N | N | PASS | passed_all_enabled |
| 2026-05-12 | 11:41 | FATN | wb_bot | 8 | LOSS | $-1,381.20 | -2.04 | 281 | Y | 3 | N | N | N | PASS | passed_all_enabled |
| 2026-05-12 | 12:20 | ATRA | wb_bot | 8 | WIN | $+41.15 | +0.23 | 393 | Y | 0 | N | N | N | PASS | passed_all_enabled |
| 2026-05-12 | 12:26 | FATN | wb_bot | 9 | LOSS | $-1,126.72 | -1.36 | 316 | Y | 3 | N | N | Y | PASS | passed_all_enabled |

## Notes

- Cross-session blacklist is built CHRONOLOGICALLY: a trade's v3 decision sees only prior-day trades, never same-day or future-day outcomes.
- Tick cache: tries `tick_cache_alpaca/<date>/<sym>.json.gz` first (Setup A's isolated cache), then `tick_cache/<date>/` (main bot), then `tick_cache_historical/`. A `Bars` count of 0 means no cache was found for that symbol/date — v3 still runs but with no intraday signal (all three metrics return their no-warning default).
- 'MACD-ready=N' means there weren't enough closed bars to build 3 history points, so macd_rolling_over returns False by default. This is the same fail-OPEN behavior live bots will see early in the session before bar history accumulates.
- 'passed_v2' is implicit: every trade in this dataset got a broker fill, so v2 (or the score>=9 chop_bypass) must have let it through. v3 is therefore evaluated only against the v2-pass population — the population it would actually see in live.
