# SQ Post-Exit Analysis

**Date generated:** 2026-03-22  
**Trades analyzed:** 109  
**Sources:** megatest_sq_only_v2 + ytd_v2_backtest_state  

## Executive Summary

| Category | Count | % | Avg add. R | $ left on table |
|----------|-------|---|------------|-----------------|
| RUNNER | 88 | 81% | +23.0R | $977,937 |
| MODEST | 17 | 16% | +1.2R | $13,816 |
| GOOD_EXIT | 2 | 2% | +0.2R | $538 |
| PERFECT_EXIT | 2 | 2% | +-0.8R | $-2,460 |
| **TOTAL** | **109** | | | **$989,831** |

> **Total $ left on table (optimistic, all exit categories):** $989,831
> **From RUNNERS alone:** $977,937
> **From MODEST continuations:** $13,816

## Exit Reason Breakdown

| Exit Reason | Count | RUNNER% | MODEST% | GOOD_EXIT% | Avg add. R | Avg $ left |
|-------------|-------|---------|---------|------------|------------|------------|
| sq_para_trail_exit | 58 | 84% | 14% | 0% | +14.6R | $7,919 |
| sq_target_hit | 35 | 86% | 6% | 6% | +32.1R | $14,201 |
| sq_max_loss_hit | 12 | 67% | 33% | 0% | +5.6R | $2,045 |
| sq_trail_exit | 3 | 33% | 67% | 0% | +2.4R | $2,572 |
| sq_stop_hit | 1 | 0% | 100% | 0% | +1.4R | $1,200 |

## Runner Deep-Dive (2R+ post-exit continuation)

**88 trades** kept running 2R+ above exit price

| Symbol | Date | Exit | Exit Price | +R avail | mins to peak | came back | Exit Reason | Score | $ left |
|--------|------|------|------------|----------|--------------|-----------|-------------|-------|--------|
| CWD | 2025-09-09 | 08:01 | 10.05 | +328.6R | 69m | N | sq_para_trail_exit | 7.8 | $82,128 |
| CYN | 2025-06-26 | 07:06 | 7.66 | +242.0R | 260m | N | sq_target_hit | 11.0 | $60,476 |
| CYN | 2025-06-26 | 07:07 | 8.65 | +234.9R | 259m | N | sq_target_hit | 11.0 | $58,709 |
| CYN | 2025-06-26 | 07:16 | 9.61 | +228.1R | 250m | N | sq_target_hit | 7.2 | $56,995 |
| ROLR | 2026-01-14 | 08:19 | 5.28 | +121.4R | 200m | N | sq_target_hit | 11.0 | $87,273 |
| ALUR | 2025-01-24 | 07:04 | 8.40 | +84.7R | 110m | N | sq_target_hit | 11.0 | $21,170 |
| ALUR | 2025-01-24 | 07:07 | 10.03 | +73.1R | 107m | Y | sq_para_trail_exit | 7.4 | $18,261 |
| STAK | 2025-06-16 | 07:10 | 4.53 | +37.1R | 16m | Y | sq_target_hit | 10.0 | $9,282 |
| INM | 2025-06-02 | 07:01 | 4.92 | +32.3R | 30m | Y | sq_target_hit | 10.0 | $51,171 |
| MBIO | 2025-07-07 | 09:11 | 3.17 | +27.4R | 82m | N | sq_para_trail_exit | 5.4 | $6,837 |
| CJMB | 2026-01-15 | 08:46 | 2.11 | +25.0R | 163m | N | sq_para_trail_exit | 11.0 | $22,774 |
| WAFU | 2025-02-25 | 09:35 | 4.21 | +23.4R | 23m | Y | sq_para_trail_exit | 11.0 | $24,714 |
| JTAI | 2025-02-14 | 09:04 | 5.04 | +22.6R | 59m | N | sq_para_trail_exit | 7.1 | $23,090 |
| NVNI | 2025-01-24 | 09:32 | 2.52 | +22.3R | 153m | N | sq_para_trail_exit | 11.0 | $5,582 |
| MBIO | 2025-07-07 | 09:34 | 4.15 | +20.4R | 59m | Y | sq_para_trail_exit | 6.4 | $5,087 |
| ANNA | 2026-03-20 | 07:08 | 4.93 | +19.1R | 289m | N | sq_max_loss_hit | 11.0 | $4,766 |
| SABS | 2025-07-21 | 08:02 | 4.00 | +18.6R | 104m | Y | sq_para_trail_exit | 11.0 | $4,640 |
| CJMB | 2026-01-15 | 08:47 | 3.06 | +18.2R | 162m | N | sq_para_trail_exit | 10.0 | $16,593 |
| SABS | 2025-07-21 | 09:37 | 4.35 | +16.1R | 9m | Y | sq_para_trail_exit | 12.0 | $4,016 |
| JTAI | 2025-02-14 | 09:09 | 6.05 | +15.4R | 54m | Y | sq_para_trail_exit | 6.7 | $15,710 |
| MYSE | 2025-03-25 | 09:52 | 3.86 | +14.8R | 37m | Y | sq_para_trail_exit | 6.2 | $19,338 |
| BATL | 2026-01-26 | 07:01 | 5.11 | +12.7R | 150m | Y | sq_para_trail_exit | 6.0 | $3,177 |
| RDGT | 2025-03-04 | 09:01 | 3.72 | +12.5R | 3m | Y | sq_target_hit | 10.0 | $3,124 |
| LIPO | 2025-02-06 | 07:02 | 5.93 | +11.2R | 51m | Y | sq_para_trail_exit | 6.5 | $11,437 |
| STAK | 2025-06-16 | 07:15 | 8.19 | +11.0R | 11m | Y | sq_target_hit | 7.1 | $2,749 |
| KIDZ | 2025-05-01 | 09:55 | 2.88 | +10.9R | 79m | N | sq_para_trail_exit | 6.7 | $15,329 |
| VNCE | 2025-01-23 | 08:39 | 4.06 | +10.8R | 99m | N | sq_para_trail_exit | 9.5 | $8,422 |
| QNTM | 2025-02-04 | 07:05 | 5.95 | +10.4R | 55m | Y | sq_target_hit | 10.0 | $8,855 |
| EVGN | 2025-06-10 | 07:04 | 1.93 | +10.1R | 10m | Y | sq_max_loss_hit | 6.5 | $2,535 |
| SXTP | 2025-04-08 | 09:44 | 3.03 | +9.9R | 17m | Y | sq_para_trail_exit | 11.0 | $13,719 |
| ARTL | 2026-03-18 | 07:42 | 6.97 | +9.8R | 134m | Y | sq_target_hit | 11.0 | $13,367 |
| BDSX | 2026-01-12 | 09:49 | 8.18 | +9.7R | 122m | N | sq_max_loss_hit | 9.2 | $7,052 |
| UOKA | 2026-02-09 | 09:36 | 2.88 | +9.6R | 8m | Y | sq_para_trail_exit | 11.0 | $13,456 |
| CNSP | 2025-05-13 | 07:06 | 2.13 | +8.9R | 5m | Y | sq_para_trail_exit | 11.0 | $12,753 |
| BSLK | 2025-07-17 | 07:04 | 3.56 | +8.6R | 136m | Y | sq_target_hit | 11.0 | $19,394 |
| BKYI | 2025-01-15 | 10:21 | 2.53 | +8.2R | 38m | Y | sq_max_loss_hit | 6.0 | $2,053 |
| COOT | 2025-10-15 | 07:08 | 3.94 | +8.2R | 27m | Y | sq_para_trail_exit | 10.0 | $2,053 |
| ACON | 2026-01-08 | 07:01 | 8.32 | +8.0R | 61m | Y | sq_target_hit | 9.9 | $5,695 |
| RDGT | 2025-03-04 | 09:03 | 4.44 | +7.4R | 1m | Y | sq_target_hit | 7.1 | $1,839 |
| AMST | 2025-02-27 | 09:36 | 3.32 | +7.3R | 51m | Y | sq_para_trail_exit | 12.0 | $8,458 |
| SXTP | 2025-07-15 | 07:02 | 3.76 | +7.2R | 2m | Y | sq_target_hit | 10.0 | $13,566 |
| WOK | 2025-02-20 | 07:17 | 5.02 | +7.0R | 145m | Y | sq_para_trail_exit | 7.9 | $7,224 |
| VNCE | 2025-01-23 | 09:32 | 4.60 | +6.9R | 46m | Y | sq_para_trail_exit | 11.0 | $5,410 |
| BIAF | 2026-03-13 | 09:37 | 2.05 | +6.8R | 36m | N | sq_para_trail_exit | 10.0 | $9,277 |
| APVO | 2025-09-16 | 08:32 | 2.44 | +6.8R | 8m | Y | sq_target_hit | 11.0 | $18,631 |
| SOPA | 2025-02-03 | 07:14 | 2.08 | +6.7R | 156m | Y | sq_para_trail_exit | 8.0 | $1,675 |
| EDSA | 2025-02-13 | 09:44 | 3.57 | +6.6R | 37m | Y | sq_para_trail_exit | 12.0 | $6,636 |
| REBN | 2025-02-03 | 07:01 | 7.32 | +6.3R | 0m | Y | sq_target_hit | 10.0 | $5,273 |
| SNTI | 2025-12-09 | 07:04 | 3.13 | +6.2R | 30m | Y | sq_para_trail_exit | 11.0 | $1,553 |
| SOBR | 2025-12-24 | 09:31 | 2.09 | +6.1R | 49m | Y | sq_para_trail_exit | 11.0 | $17,666 |
| SILO | 2025-01-08 | 09:33 | 2.54 | +5.9R | 31m | Y | sq_para_trail_exit | 11.0 | $1,481 |
| POLA | 2026-01-20 | 10:03 | 2.94 | +5.7R | 16m | Y | sq_para_trail_exit | 9.1 | $7,640 |
| WHLR | 2025-01-16 | 07:18 | 4.05 | +5.6R | 67m | Y | sq_para_trail_exit | 11.0 | $4,441 |
| AIFF | 2025-01-14 | 09:31 | 5.08 | +5.5R | 6m | Y | sq_target_hit | 11.0 | $1,386 |
| GLMD | 2025-03-17 | 09:43 | 2.73 | +5.5R | 14m | Y | sq_target_hit | 11.0 | $1,375 |
| ATER | 2025-03-19 | 09:34 | 2.73 | +5.5R | 33m | Y | sq_max_loss_hit | 12.0 | $1,369 |
| SNOA | 2025-03-10 | 09:38 | 2.79 | +5.3R | 54m | Y | sq_para_trail_exit | 12.0 | $6,797 |
| APM | 2025-08-21 | 09:59 | 3.11 | +5.2R | 55m | Y | sq_para_trail_exit | 7.7 | $1,303 |
| AMST | 2025-05-16 | 07:02 | 4.32 | +5.1R | 0m | Y | sq_target_hit | 6.6 | $7,446 |
| PRFX | 2025-08-19 | 08:31 | 2.88 | +5.1R | 67m | Y | sq_target_hit | 11.0 | $12,937 |
| GSUN | 2025-02-24 | 09:44 | 4.56 | +4.9R | 0m | Y | sq_target_hit | 11.0 | $5,047 |
| WOK | 2025-02-20 | 09:37 | 5.35 | +4.6R | 5m | Y | sq_para_trail_exit | 12.0 | $4,791 |
| SOPA | 2025-12-29 | 10:04 | 2.82 | +4.6R | 5m | Y | sq_para_trail_exit | 10.7 | $1,142 |
| EDBL | 2025-05-20 | 09:52 | 3.26 | +4.4R | 7m | Y | sq_para_trail_exit | 11.0 | $6,625 |
| LIXT | 2025-07-03 | 09:47 | 3.63 | +4.4R | 9m | Y | sq_para_trail_exit | 8.3 | $1,107 |
| ACON | 2025-03-03 | 07:06 | 7.00 | +4.3R | 146m | Y | sq_trail_exit | 7.0 | $5,371 |
| BATL | 2026-01-26 | 07:05 | 6.32 | +4.1R | 146m | Y | sq_target_hit | 7.7 | $1,017 |
| CYCN | 2025-01-31 | 09:42 | 3.91 | +4.0R | 11m | Y | sq_max_loss_hit | 12.0 | $3,415 |
| QNTM | 2025-02-04 | 07:06 | 6.96 | +4.0R | 54m | Y | sq_target_hit | 6.0 | $3,420 |
| MYSE | 2025-01-07 | 10:26 | 3.21 | +3.8R | 93m | N | sq_para_trail_exit | 11.0 | $2,816 |
| SLGB | 2026-01-21 | 07:17 | 4.00 | +3.7R | 21m | Y | sq_target_hit | 10.0 | $4,984 |
| ENVB | 2025-02-26 | 09:38 | 4.00 | +3.6R | 1m | Y | sq_target_hit | 11.0 | $4,028 |
| AGIG | 2025-06-13 | 10:38 | 19.27 | +3.3R | 0m | Y | sq_target_hit | 6.0 | $830 |
| ASNS | 2025-12-16 | 08:10 | 2.04 | +3.3R | 0m | Y | sq_para_trail_exit | 7.7 | $9,445 |
| VERO | 2025-04-09 | 07:04 | 12.98 | +3.2R | 158m | Y | sq_target_hit | 6.5 | $4,486 |
| BOF | 2025-10-21 | 07:08 | 2.93 | +3.1R | 29m | Y | sq_max_loss_hit | 9.8 | $785 |
| SOPA | 2025-02-03 | 09:31 | 2.32 | +3.1R | 19m | Y | sq_max_loss_hit | 12.0 | $766 |
| KTTA | 2025-05-06 | 09:54 | 3.38 | +2.9R | 11m | Y | sq_para_trail_exit | 11.0 | $4,173 |
| MSW | 2025-08-01 | 08:31 | 2.99 | +2.9R | 0m | Y | sq_target_hit | 10.0 | $6,881 |
| RDGT | 2025-03-04 | 09:05 | 5.08 | +2.8R | 0m | Y | sq_para_trail_exit | 5.7 | $696 |
| BOXL | 2026-02-04 | 07:16 | 1.98 | +2.8R | 187m | Y | sq_para_trail_exit | 9.2 | $3,930 |
| SLXN | 2025-01-29 | 10:30 | 2.49 | +2.7R | 5m | Y | sq_para_trail_exit | 9.2 | $2,313 |
| ICON | 2025-06-13 | 07:26 | 3.45 | +2.7R | 57m | Y | sq_target_hit | 5.9 | $4,592 |
| CNSP | 2025-05-13 | 07:09 | 3.01 | +2.6R | 2m | Y | sq_para_trail_exit | 6.5 | $3,703 |
| NAMM | 2025-10-13 | 10:18 | 4.59 | +2.6R | 1m | Y | sq_para_trail_exit | 8.1 | $643 |
| SNTI | 2025-04-28 | 07:06 | 6.95 | +2.3R | 0m | Y | sq_para_trail_exit | 8.4 | $571 |
| SPRC | 2026-01-13 | 07:05 | 2.06 | +2.3R | 14m | Y | sq_para_trail_exit | 7.7 | $1,641 |
| ORIS | 2025-01-02 | 07:13 | 2.92 | +2.1R | 11m | Y | sq_para_trail_exit | 10.0 | $1,554 |

### Runner Characteristics

**Exit reason distribution in runners:**
- sq_para_trail_exit: 49 (56%)
- sq_target_hit: 30 (34%)
- sq_max_loss_hit: 8 (9%)
- sq_trail_exit: 1 (1%)

| Metric | Runners | All SQ trades |
|--------|---------|---------------|
| Avg score at entry | 9.3 | 9.5 |
| Avg R size ($) | $0.143 | $0.150 |
| Avg R taken at exit | +1.8R | +1.6R |

**Timing:** 47/88 runner exits happen before 9 AM ET

## Modest Continuation (0.5–2R post-exit)

| Symbol | Date | Exit | Exit Price | +R avail | mins to peak | came back | Exit Reason |
|--------|------|------|------------|----------|--------------|-----------|-------------|
| ISPC | 2025-02-24 | 10:49 | 2.76 | +1.9R | 7m | Y | sq_max_loss_hit |
| ALUR | 2025-03-21 | 07:01 | 3.99 | +1.8R | 27m | Y | sq_para_trail_exit |
| LSE | 2025-03-19 | 07:25 | 16.01 | +1.5R | 0m | Y | sq_trail_exit |
| AYTU | 2025-05-15 | 11:37 | 2.27 | +1.5R | 3m | Y | sq_para_trail_exit |
| FATN | 2025-09-19 | 10:32 | 8.61 | +1.5R | 0m | Y | sq_trail_exit |
| REBN | 2025-02-03 | 08:04 | 7.90 | +1.4R | 0m | Y | sq_stop_hit |
| VEEE | 2025-09-05 | 09:48 | 3.28 | +1.3R | 2m | Y | sq_max_loss_hit |
| ATON | 2025-03-28 | 07:07 | 12.99 | +1.1R | 17m | Y | sq_target_hit |
| VMAR | 2025-01-10 | 09:55 | 3.76 | +1.0R | 0m | Y | sq_para_trail_exit |
| LEDS | 2025-01-21 | 09:37 | 2.34 | +1.0R | 0m | Y | sq_para_trail_exit |
| ZENA | 2025-04-24 | 08:08 | 3.05 | +1.0R | 0m | Y | sq_para_trail_exit |
| EVTV | 2026-02-20 | 07:07 | 2.05 | +1.0R | 6m | Y | sq_para_trail_exit |
| SER | 2026-03-19 | 09:31 | 2.30 | +1.0R | 0m | Y | sq_para_trail_exit |
| FEED | 2025-03-17 | 07:55 | 4.02 | +0.9R | 99m | Y | sq_para_trail_exit |
| SINT | 2025-02-19 | 10:56 | 5.88 | +0.8R | 0m | Y | sq_max_loss_hit |
| AIFF | 2025-05-05 | 08:45 | 4.93 | +0.7R | 1m | Y | sq_max_loss_hit |
| BOSC | 2025-05-29 | 08:52 | 7.80 | +0.6R | 0m | Y | sq_target_hit |

## Good Exits & Perfect Exits (exit roughly correct)

- **Good exits** (<0.5R above exit): 2 trades
- **Perfect exits** (stock below exit): 2 trades
- Combined: 4 trades (4% of all SQ exits)

## Focus: sq_target_hit exits

These are the fixed-target exits where the bot capped profit. How often was that a mistake?

- Runner after target hit: 30/35 (86%)
- Modest continuation: 2/35 (6%)
- Good/perfect exit: 3/35 (9%)

Total $ left by exiting at target (runners): **$495,998**
Total $ left by exiting at target (modest):  $1,637

| Symbol | Date | R taken | +R available | Verdict |
|--------|------|---------|-------------|---------|
| CYN | 2025-06-26 | +12.8R | +242.0R | RUNNER |
| CYN | 2025-06-26 | +4.3R | +234.9R | RUNNER |
| CYN | 2025-06-26 | +3.9R | +228.1R | RUNNER |
| ROLR | 2026-01-14 | +8.5R | +121.4R | RUNNER |
| ALUR | 2025-01-24 | +4.1R | +84.7R | RUNNER |
| STAK | 2025-06-16 | +11.2R | +37.1R | RUNNER |
| INM | 2025-06-02 | +6.0R | +32.3R | RUNNER |
| RDGT | 2025-03-04 | +4.4R | +12.5R | RUNNER |
| STAK | 2025-06-16 | +7.8R | +11.0R | RUNNER |
| QNTM | 2025-02-04 | +7.8R | +10.4R | RUNNER |
| ARTL | 2026-03-18 | +13.9R | +9.8R | RUNNER |
| BSLK | 2025-07-17 | +3.8R | +8.6R | RUNNER |
| ACON | 2026-01-08 | +1.6R | +8.0R | RUNNER |
| RDGT | 2025-03-04 | +2.6R | +7.4R | RUNNER |
| SXTP | 2025-07-15 | +15.0R | +7.2R | RUNNER |
| APVO | 2025-09-16 | +3.3R | +6.8R | RUNNER |
| REBN | 2025-02-03 | +2.6R | +6.3R | RUNNER |
| AIFF | 2025-01-14 | +4.2R | +5.5R | RUNNER |
| GLMD | 2025-03-17 | +2.7R | +5.5R | RUNNER |
| AMST | 2025-05-16 | +2.7R | +5.1R | RUNNER |

## Focus: sq_para_trail_exit exits

Para trail exits — trailing stop got hit. Did the stock recover?

- Runner after para trail: 49/58 (84%)
- Modest continuation: 8/58 (14%)
- Good/perfect exit: 1/58 (2%)

## Key Signal Analysis: What Distinguishes Runners?

At the moment of exit, what features predict a runner vs a good exit?

**Score >= 10:**
- In runners: 49/88 (56%)
- In good exits: 2/2 (100%)

**Exit time buckets:**

| Time bucket | Total | Runners | RUNNER% |
|-------------|-------|---------|---------|
| 07:00-07:30 | 41 | 36 | 88% |
| 07:30-08:00 | 2 | 1 | 50% |
| 08:00-09:00 | 16 | 10 | 62% |
| 09:00-10:00 | 39 | 34 | 87% |
| 10:00+ | 11 | 7 | 64% |

**R multiple at exit vs runner rate:**

| R taken at exit | Total | Runners | RUNNER% |
|-----------------|-------|---------|---------|
| <0R | 38 | 28 | 74% |
| 0-1R | 35 | 29 | 83% |
| 1-3R | 15 | 11 | 73% |
| 3-6R | 8 | 8 | 100% |
| 6R+ | 13 | 12 | 92% |

## Candidate Exit Rule: "Let It Run" Signal

Based on the data above, when should we NOT exit at the SQ target?

Looking for a rule of the form:
> *If [condition], extend target / trail instead of taking fixed profit*

**Rule candidate: Exit before 8 AM AND score >= 10**
- 21 trades match
- 17 are runners (81%)
- $ at risk: $293,367 recoverable

**Rule candidate: sq_target_hit AND score >= 10**
- 25 trades match
- 20 are runners (80%)
- $ recoverable (in runners): $406,929

## Detailed Trade Log

| # | Symbol | Date | ExitT | Entry | Exit$ | R | R-taken | +R post | minsToPeak | CameBack | Reason | Category |
|---|--------|------|-------|-------|-------|---|---------|---------|------------|----------|--------|----------|
| 1 | CWD | 2025-09-09 | 08:01 | 10.04 | 10.05 | 0.14 | +0.1R | +328.6R | 69m | N | sq_para_trail_exit | **RUNNER** |
| 2 | CYN | 2025-06-26 | 07:06 | 6.04 | 7.66 | 0.14 | +12.8R | +242.0R | 260m | N | sq_target_hit | **RUNNER** |
| 3 | CYN | 2025-06-26 | 07:07 | 8.04 | 8.65 | 0.14 | +4.3R | +234.9R | 259m | N | sq_target_hit | **RUNNER** |
| 4 | CYN | 2025-06-26 | 07:16 | 9.04 | 9.61 | 0.14 | +3.9R | +228.1R | 250m | N | sq_target_hit | **RUNNER** |
| 5 | ROLR | 2026-01-14 | 08:19 | 4.04 | 5.28 | 0.14 | +8.5R | +121.4R | 200m | N | sq_target_hit | **RUNNER** |
| 6 | ALUR | 2025-01-24 | 07:04 | 8.04 | 8.40 | 0.14 | +4.1R | +84.7R | 110m | N | sq_target_hit | **RUNNER** |
| 7 | ALUR | 2025-01-24 | 07:07 | 10.04 | 10.03 | 0.14 | -0.1R | +73.1R | 107m | Y | sq_para_trail_exit | **RUNNER** |
| 8 | STAK | 2025-06-16 | 07:10 | 3.04 | 4.53 | 0.14 | +11.2R | +37.1R | 16m | Y | sq_target_hit | **RUNNER** |
| 9 | INM | 2025-06-02 | 07:01 | 4.04 | 4.92 | 0.14 | +6.0R | +32.3R | 30m | Y | sq_target_hit | **RUNNER** |
| 10 | MBIO | 2025-07-07 | 09:11 | 3.04 | 3.17 | 0.14 | +0.9R | +27.4R | 82m | N | sq_para_trail_exit | **RUNNER** |
| 11 | CJMB | 2026-01-15 | 08:46 | 2.04 | 2.11 | 0.14 | +0.5R | +25.0R | 163m | N | sq_para_trail_exit | **RUNNER** |
| 12 | WAFU | 2025-02-25 | 09:35 | 4.18 | 4.21 | 0.14 | +0.2R | +23.4R | 23m | Y | sq_para_trail_exit | **RUNNER** |
| 13 | JTAI | 2025-02-14 | 09:04 | 5.04 | 5.04 | 0.14 | +0.0R | +22.6R | 59m | N | sq_para_trail_exit | **RUNNER** |
| 14 | NVNI | 2025-01-24 | 09:32 | 2.48 | 2.52 | 0.12 | +0.3R | +22.3R | 153m | N | sq_para_trail_exit | **RUNNER** |
| 15 | MBIO | 2025-07-07 | 09:34 | 4.20 | 4.15 | 0.14 | -0.4R | +20.4R | 59m | Y | sq_para_trail_exit | **RUNNER** |
| 16 | ANNA | 2026-03-20 | 07:08 | 5.04 | 4.93 | 0.14 | -0.8R | +19.1R | 289m | N | sq_max_loss_hit | **RUNNER** |
| 17 | SABS | 2025-07-21 | 08:02 | 4.04 | 4.00 | 0.14 | -0.3R | +18.6R | 104m | Y | sq_para_trail_exit | **RUNNER** |
| 18 | CJMB | 2026-01-15 | 08:47 | 3.04 | 3.06 | 0.14 | +0.1R | +18.2R | 162m | N | sq_para_trail_exit | **RUNNER** |
| 19 | SABS | 2025-07-21 | 09:37 | 4.44 | 4.35 | 0.14 | -0.6R | +16.1R | 9m | Y | sq_para_trail_exit | **RUNNER** |
| 20 | JTAI | 2025-02-14 | 09:09 | 6.04 | 6.05 | 0.14 | +0.1R | +15.4R | 54m | Y | sq_para_trail_exit | **RUNNER** |
| 21 | MYSE | 2025-03-25 | 09:52 | 3.82 | 3.86 | 0.14 | +0.3R | +14.8R | 37m | Y | sq_para_trail_exit | **RUNNER** |
| 22 | BATL | 2026-01-26 | 07:01 | 5.04 | 5.11 | 0.14 | +0.5R | +12.7R | 150m | Y | sq_para_trail_exit | **RUNNER** |
| 23 | RDGT | 2025-03-04 | 09:01 | 3.04 | 3.72 | 0.14 | +4.4R | +12.5R | 3m | Y | sq_target_hit | **RUNNER** |
| 24 | LIPO | 2025-02-06 | 07:02 | 6.04 | 5.93 | 0.14 | -0.8R | +11.2R | 51m | Y | sq_para_trail_exit | **RUNNER** |
| 25 | STAK | 2025-06-16 | 07:15 | 7.04 | 8.19 | 0.14 | +7.8R | +11.0R | 11m | Y | sq_target_hit | **RUNNER** |
| 26 | KIDZ | 2025-05-01 | 09:55 | 2.76 | 2.88 | 0.14 | +0.9R | +10.9R | 79m | N | sq_para_trail_exit | **RUNNER** |
| 27 | VNCE | 2025-01-23 | 08:39 | 4.04 | 4.06 | 0.14 | +0.1R | +10.8R | 99m | N | sq_para_trail_exit | **RUNNER** |
| 28 | QNTM | 2025-02-04 | 07:05 | 5.04 | 5.95 | 0.14 | +7.8R | +10.4R | 55m | Y | sq_target_hit | **RUNNER** |
| 29 | EVGN | 2025-06-10 | 07:04 | 2.04 | 1.93 | 0.14 | -0.8R | +10.1R | 10m | Y | sq_max_loss_hit | **RUNNER** |
| 30 | SXTP | 2025-04-08 | 09:44 | 3.07 | 3.03 | 0.14 | -0.3R | +9.9R | 17m | Y | sq_para_trail_exit | **RUNNER** |
| 31 | ARTL | 2026-03-18 | 07:42 | 5.04 | 6.97 | 0.14 | +13.9R | +9.8R | 134m | Y | sq_target_hit | **RUNNER** |
| 32 | BDSX | 2026-01-12 | 09:49 | 8.30 | 8.18 | 0.14 | -0.9R | +9.7R | 122m | N | sq_max_loss_hit | **RUNNER** |
| 33 | UOKA | 2026-02-09 | 09:36 | 2.78 | 2.88 | 0.14 | +0.7R | +9.6R | 8m | Y | sq_para_trail_exit | **RUNNER** |
| 34 | CNSP | 2025-05-13 | 07:06 | 2.04 | 2.13 | 0.14 | +0.6R | +8.9R | 5m | Y | sq_para_trail_exit | **RUNNER** |
| 35 | BSLK | 2025-07-17 | 07:04 | 3.04 | 3.56 | 0.14 | +3.8R | +8.6R | 136m | Y | sq_target_hit | **RUNNER** |
| 36 | BKYI | 2025-01-15 | 10:21 | 2.64 | 2.53 | 0.14 | -0.8R | +8.2R | 38m | Y | sq_max_loss_hit | **RUNNER** |
| 37 | COOT | 2025-10-15 | 07:08 | 4.04 | 3.94 | 0.14 | -0.7R | +8.2R | 27m | Y | sq_para_trail_exit | **RUNNER** |
| 38 | ACON | 2026-01-08 | 07:01 | 8.04 | 8.32 | 0.14 | +1.6R | +8.0R | 61m | Y | sq_target_hit | **RUNNER** |
| 39 | RDGT | 2025-03-04 | 09:03 | 4.04 | 4.44 | 0.14 | +2.6R | +7.4R | 1m | Y | sq_target_hit | **RUNNER** |
| 40 | AMST | 2025-02-27 | 09:36 | 3.37 | 3.32 | 0.14 | -0.4R | +7.3R | 51m | Y | sq_para_trail_exit | **RUNNER** |
| 41 | SXTP | 2025-07-15 | 07:02 | 2.04 | 3.76 | 0.11 | +15.0R | +7.2R | 2m | Y | sq_target_hit | **RUNNER** |
| 42 | WOK | 2025-02-20 | 07:17 | 5.04 | 5.02 | 0.14 | -0.1R | +7.0R | 145m | Y | sq_para_trail_exit | **RUNNER** |
| 43 | VNCE | 2025-01-23 | 09:32 | 4.64 | 4.60 | 0.14 | -0.3R | +6.9R | 46m | Y | sq_para_trail_exit | **RUNNER** |
| 44 | BIAF | 2026-03-13 | 09:37 | 2.03 | 2.05 | 0.10 | +0.2R | +6.8R | 36m | N | sq_para_trail_exit | **RUNNER** |
| 45 | APVO | 2025-09-16 | 08:32 | 2.04 | 2.44 | 0.14 | +3.3R | +6.8R | 8m | Y | sq_target_hit | **RUNNER** |
| 46 | SOPA | 2025-02-03 | 07:14 | 2.04 | 2.08 | 0.10 | +0.4R | +6.7R | 156m | Y | sq_para_trail_exit | **RUNNER** |
| 47 | EDSA | 2025-02-13 | 09:44 | 3.43 | 3.57 | 0.14 | +1.0R | +6.6R | 37m | Y | sq_para_trail_exit | **RUNNER** |
| 48 | REBN | 2025-02-03 | 07:01 | 7.04 | 7.32 | 0.14 | +2.6R | +6.3R | 0m | Y | sq_target_hit | **RUNNER** |
| 49 | SNTI | 2025-12-09 | 07:04 | 3.04 | 3.13 | 0.14 | +0.6R | +6.2R | 30m | Y | sq_para_trail_exit | **RUNNER** |
| 50 | SOBR | 2025-12-24 | 09:31 | 2.08 | 2.09 | 0.14 | +0.1R | +6.1R | 49m | Y | sq_para_trail_exit | **RUNNER** |
| 51 | SILO | 2025-01-08 | 09:33 | 2.47 | 2.54 | 0.14 | +0.5R | +5.9R | 31m | Y | sq_para_trail_exit | **RUNNER** |
| 52 | POLA | 2026-01-20 | 10:03 | 2.90 | 2.94 | 0.14 | +0.3R | +5.7R | 16m | Y | sq_para_trail_exit | **RUNNER** |
| 53 | WHLR | 2025-01-16 | 07:18 | 4.04 | 4.05 | 0.14 | +0.1R | +5.6R | 67m | Y | sq_para_trail_exit | **RUNNER** |
| 54 | AIFF | 2025-01-14 | 09:31 | 4.61 | 5.08 | 0.13 | +4.2R | +5.5R | 6m | Y | sq_target_hit | **RUNNER** |
| 55 | GLMD | 2025-03-17 | 09:43 | 2.44 | 2.73 | 0.14 | +2.7R | +5.5R | 14m | Y | sq_target_hit | **RUNNER** |
| 56 | ATER | 2025-03-19 | 09:34 | 2.84 | 2.73 | 0.14 | -0.8R | +5.5R | 33m | Y | sq_max_loss_hit | **RUNNER** |
| 57 | SNOA | 2025-03-10 | 09:38 | 2.89 | 2.79 | 0.14 | -0.7R | +5.3R | 54m | Y | sq_para_trail_exit | **RUNNER** |
| 58 | APM | 2025-08-21 | 09:59 | 3.06 | 3.11 | 0.14 | +0.4R | +5.2R | 55m | Y | sq_para_trail_exit | **RUNNER** |
| 59 | AMST | 2025-05-16 | 07:02 | 4.04 | 4.32 | 0.14 | +2.7R | +5.1R | 0m | Y | sq_target_hit | **RUNNER** |
| 60 | PRFX | 2025-08-19 | 08:31 | 2.04 | 2.88 | 0.14 | +6.1R | +5.1R | 67m | Y | sq_target_hit | **RUNNER** |
| 61 | GSUN | 2025-02-24 | 09:44 | 4.28 | 4.56 | 0.14 | +2.6R | +4.9R | 0m | Y | sq_target_hit | **RUNNER** |
| 62 | WOK | 2025-02-20 | 09:37 | 5.42 | 5.35 | 0.14 | -0.5R | +4.6R | 5m | Y | sq_para_trail_exit | **RUNNER** |
| 63 | SOPA | 2025-12-29 | 10:04 | 2.92 | 2.82 | 0.14 | -0.7R | +4.6R | 5m | Y | sq_para_trail_exit | **RUNNER** |
| 64 | EDBL | 2025-05-20 | 09:52 | 3.31 | 3.26 | 0.14 | -0.4R | +4.4R | 7m | Y | sq_para_trail_exit | **RUNNER** |
| 65 | LIXT | 2025-07-03 | 09:47 | 3.68 | 3.63 | 0.14 | -0.4R | +4.4R | 9m | Y | sq_para_trail_exit | **RUNNER** |
| 66 | ACON | 2025-03-03 | 07:06 | 7.04 | 7.00 | 0.26 | -0.2R | +4.3R | 146m | Y | sq_trail_exit | **RUNNER** |
| 67 | BATL | 2026-01-26 | 07:05 | 6.04 | 6.32 | 0.14 | +2.0R | +4.1R | 146m | Y | sq_target_hit | **RUNNER** |
| 68 | CYCN | 2025-01-31 | 09:42 | 4.03 | 3.91 | 0.14 | -0.9R | +4.0R | 11m | Y | sq_max_loss_hit | **RUNNER** |
| 69 | QNTM | 2025-02-04 | 07:06 | 6.04 | 6.96 | 0.11 | +7.7R | +4.0R | 54m | Y | sq_target_hit | **RUNNER** |
| 70 | MYSE | 2025-01-07 | 10:26 | 3.19 | 3.21 | 0.14 | +0.1R | +3.8R | 93m | N | sq_para_trail_exit | **RUNNER** |
| 71 | SLGB | 2026-01-21 | 07:17 | 3.04 | 4.00 | 0.14 | +6.4R | +3.7R | 21m | Y | sq_target_hit | **RUNNER** |
| 72 | ENVB | 2025-02-26 | 09:38 | 3.60 | 4.00 | 0.14 | +2.4R | +3.6R | 1m | Y | sq_target_hit | **RUNNER** |
| 73 | AGIG | 2025-06-13 | 10:38 | 18.54 | 19.27 | 0.14 | +5.3R | +3.3R | 0m | Y | sq_target_hit | **RUNNER** |
| 74 | ASNS | 2025-12-16 | 08:10 | 2.04 | 2.04 | 0.14 | +0.0R | +3.3R | 0m | Y | sq_para_trail_exit | **RUNNER** |
| 75 | VERO | 2025-04-09 | 07:04 | 12.04 | 12.98 | 0.47 | +1.5R | +3.2R | 158m | Y | sq_target_hit | **RUNNER** |
| 76 | BOF | 2025-10-21 | 07:08 | 3.04 | 2.93 | 0.14 | -0.8R | +3.1R | 29m | Y | sq_max_loss_hit | **RUNNER** |
| 77 | SOPA | 2025-02-03 | 09:31 | 2.43 | 2.32 | 0.14 | -0.8R | +3.1R | 19m | Y | sq_max_loss_hit | **RUNNER** |
| 78 | KTTA | 2025-05-06 | 09:54 | 3.31 | 3.38 | 0.14 | +0.5R | +2.9R | 11m | Y | sq_para_trail_exit | **RUNNER** |
| 79 | MSW | 2025-08-01 | 08:31 | 2.04 | 2.99 | 0.14 | +6.9R | +2.9R | 0m | Y | sq_target_hit | **RUNNER** |
| 80 | RDGT | 2025-03-04 | 09:05 | 5.04 | 5.08 | 0.14 | +0.3R | +2.8R | 0m | Y | sq_para_trail_exit | **RUNNER** |
| 81 | BOXL | 2026-02-04 | 07:16 | 2.04 | 1.98 | 0.14 | -0.4R | +2.8R | 187m | Y | sq_para_trail_exit | **RUNNER** |
| 82 | SLXN | 2025-01-29 | 10:30 | 2.43 | 2.49 | 0.11 | +0.5R | +2.7R | 5m | Y | sq_para_trail_exit | **RUNNER** |
| 83 | ICON | 2025-06-13 | 07:26 | 3.04 | 3.45 | 0.14 | +2.4R | +2.7R | 57m | Y | sq_target_hit | **RUNNER** |
| 84 | CNSP | 2025-05-13 | 07:09 | 3.04 | 3.01 | 0.14 | -0.2R | +2.6R | 2m | Y | sq_para_trail_exit | **RUNNER** |
| 85 | NAMM | 2025-10-13 | 10:18 | 4.54 | 4.59 | 0.14 | +0.4R | +2.6R | 1m | Y | sq_para_trail_exit | **RUNNER** |
| 86 | SNTI | 2025-04-28 | 07:06 | 7.04 | 6.95 | 0.14 | -0.6R | +2.3R | 0m | Y | sq_para_trail_exit | **RUNNER** |
| 87 | SPRC | 2026-01-13 | 07:05 | 2.04 | 2.06 | 0.14 | +0.1R | +2.3R | 14m | Y | sq_para_trail_exit | **RUNNER** |
| 88 | ORIS | 2025-01-02 | 07:13 | 3.04 | 2.92 | 0.14 | -0.9R | +2.1R | 11m | Y | sq_para_trail_exit | **RUNNER** |
| 89 | ISPC | 2025-02-24 | 10:49 | 2.87 | 2.76 | 0.14 | -0.8R | +1.9R | 7m | Y | sq_max_loss_hit | **MODEST** |
| 90 | ALUR | 2025-03-21 | 07:01 | 4.04 | 3.99 | 0.14 | -0.4R | +1.8R | 27m | Y | sq_para_trail_exit | **MODEST** |
| 91 | LSE | 2025-03-19 | 07:25 | 16.04 | 16.01 | 0.46 | -0.1R | +1.5R | 0m | Y | sq_trail_exit | **MODEST** |
| 92 | AYTU | 2025-05-15 | 11:37 | 2.27 | 2.27 | 0.12 | +0.0R | +1.5R | 3m | Y | sq_para_trail_exit | **MODEST** |
| 93 | FATN | 2025-09-19 | 10:32 | 8.55 | 8.61 | 0.44 | +0.1R | +1.5R | 0m | Y | sq_trail_exit | **MODEST** |
| 94 | REBN | 2025-02-03 | 08:04 | 8.04 | 7.90 | 0.14 | -1.0R | +1.4R | 0m | Y | sq_stop_hit | **MODEST** |
| 95 | VEEE | 2025-09-05 | 09:48 | 3.39 | 3.28 | 0.14 | -0.8R | +1.3R | 2m | Y | sq_max_loss_hit | **MODEST** |
| 96 | ATON | 2025-03-28 | 07:07 | 12.04 | 12.99 | 0.47 | +1.8R | +1.1R | 17m | Y | sq_target_hit | **MODEST** |
| 97 | VMAR | 2025-01-10 | 09:55 | 3.73 | 3.76 | 0.14 | +0.2R | +1.0R | 0m | Y | sq_para_trail_exit | **MODEST** |
| 98 | LEDS | 2025-01-21 | 09:37 | 2.44 | 2.34 | 0.14 | -0.7R | +1.0R | 0m | Y | sq_para_trail_exit | **MODEST** |
| 99 | ZENA | 2025-04-24 | 08:08 | 3.04 | 3.05 | 0.14 | +0.1R | +1.0R | 0m | Y | sq_para_trail_exit | **MODEST** |
| 100 | EVTV | 2026-02-20 | 07:07 | 2.04 | 2.05 | 0.12 | +0.1R | +1.0R | 6m | Y | sq_para_trail_exit | **MODEST** |
| 101 | SER | 2026-03-19 | 09:31 | 2.22 | 2.30 | 0.12 | +0.7R | +1.0R | 0m | Y | sq_para_trail_exit | **MODEST** |
| 102 | FEED | 2025-03-17 | 07:55 | 4.04 | 4.02 | 0.14 | -0.1R | +0.9R | 99m | Y | sq_para_trail_exit | **MODEST** |
| 103 | SINT | 2025-02-19 | 10:56 | 6.00 | 5.88 | 0.14 | -0.9R | +0.8R | 0m | Y | sq_max_loss_hit | **MODEST** |
| 104 | AIFF | 2025-05-05 | 08:45 | 5.04 | 4.93 | 0.14 | -0.8R | +0.7R | 1m | Y | sq_max_loss_hit | **MODEST** |
| 105 | BOSC | 2025-05-29 | 08:52 | 6.04 | 7.80 | 0.14 | +12.1R | +0.6R | 0m | Y | sq_target_hit | **MODEST** |
| 106 | GV | 2025-03-05 | 09:38 | 2.39 | 2.68 | 0.14 | +1.9R | +0.4R | 2m | Y | sq_target_hit | **GOOD_EXIT** |
| 107 | SNES | 2025-03-13 | 07:09 | 3.04 | 3.33 | 0.14 | +1.6R | +0.0R | 0m | Y | sq_target_hit | **GOOD_EXIT** |
| 108 | LPCN | 2025-06-09 | 08:02 | 4.04 | 3.98 | 0.14 | -0.4R | +-0.8R | 0m | Y | sq_para_trail_exit | **PERFECT_EXIT** |
| 109 | DRMA | 2025-03-27 | 08:32 | 2.04 | 2.52 | 0.14 | +2.9R | +-0.9R | 0m | Y | sq_target_hit | **PERFECT_EXIT** |

---
*Generated by analyze_sq_post_exit.py*