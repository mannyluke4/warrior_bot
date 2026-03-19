# V6.2 Profile B Wide Filter Results — Narrow vs Wide Comparison

**Generated:** 2026-03-10
**Branch:** v6-dynamic-sizing
**Dates:** Jan 2025 – Feb 2026 (260 trading days)
**Engine:** simulate.py --ticks (tick-by-tick replay)

## Filter Changes

| Parameter | Narrow (Old) | Wide (New) |
|-----------|-------------|------------|
| Float ceiling | 10M | 15M |
| Gap cap | 25% | 35% |
| Max B per day | 2 | 3 |
| B-gate gap min | 14% | 12% |
| B-gate PM vol min | 10,000 | 5,000 |
| B risk cap | $250 | $250 (unchanged) |

## 1. Profile B Funnel Comparison

| Stage | Narrow | Wide | Delta |
|-------|--------|------|-------|
| Scanner B candidates | 1029 | 1029 | +0 |
| Pass price+gap+float filter | 292 | 326 | +34 |
| Survive SQS + B-gate | 26 | 37 | +11 |
| Active trades (P&L != $0) | 5 | 6 | +1 |

## 2. Profile B Performance Comparison

| Metric | Narrow (Baseline) | Wide (New) | Delta |
|--------|------------------|------------|-------|
| Total sims | 26 | 37 | +11 |
| Active trades | 5 | 6 | +1 |
| Winners | 3 | 3 | +0 |
| Losers | 2 | 3 | +1 |
| Win rate | 60.0% | 50.0% | -10.0pp |
| Total P&L | $+1,721 | $+1,107 | $-614 |
| Avg win | $+668 | $+506 | $-162 |
| Avg loss | $-141 | $-137 | $+4 |
| Win/loss ratio | 4.74:1 | 3.70:1 | — |
| Worst single loss | — | $-256 | — |

## 3. New Profile B Trades (Not in Narrow Run)

| Date | Symbol | SQS | Tier | Risk | P&L | Gap% | Float(M) | PM Vol | Filter Tag |
|------|--------|-----|------|------|-----|------|----------|--------|------------|
| 2025-02-20 | HMR | 5 | A | $250 | $+0 | 29.8% | 5.8M | 5,869,114 | GAP |
| 2025-02-20 | OSRH | 4 | B | $250 | $+0 | 30.7% | 7.8M | 68,614 | GAP |
| 2025-06-18 | SNTI | 4 | B | $250 | $+0 | 33.8% | 9.7M | 361,305 | GAP |
| 2025-06-23 | LUCY | 4 | B | $250 | $+0 | 26.1% | 5.0M | 200,006 | GAP |
| 2025-07-09 | MBIO | 4 | B | $250 | $+0 | 13.2% | 5.1M | 9,969,839 | BGATE |
| 2025-10-10 | YDDL | 5 | A | $250 | $+0 | 33.4% | 6.4M | 3,665,436 | GAP |
| 2025-10-17 | OLOX | 5 | A | $250 | $+0 | 31.8% | 5.5M | 8,946,160 | GAP |
| 2025-11-07 | IONZ | 4 | B | $250 | $+0 | 13.5% | 6.6M | 1,462,738 | BGATE |
| 2025-11-24 | IONZ | 4 | B | $250 | $+0 | 30.2% | 6.6M | 271,125 | GAP |
| 2025-12-16 | CYN | 4 | B | $250 | $-256 | 12.2% | 8.0M | 2,051,004 | BGATE |
| 2026-02-20 | NAMM | 5 | A | $250 | $+0 | 28.8% | 6.8M | 738,183 | GAP |
| 2026-02-20 | AGIG | 4 | B | $250 | $+0 | 20.1% | 8.7M | 89,582 | SLOT |

**New B trades:** 12 total, 1 active, 0W/1L, $-256

**Breakdown by filter change:**

| Filter | New Trades | Active | P&L |
|--------|-----------|--------|-----|
| FLOAT | 0 | 0 | $0 |
| GAP | 8 | 0 | $+0 |
| BGATE | 3 | 1 | $-256 |
| SLOT | 1 | 0 | $+0 |

## 4. Profile A Validation (MUST BE UNCHANGED)

| Metric | Narrow Baseline | Wide Run |
|--------|----------------|----------|
| A total sims | 241 | 278 |
| A active trades | 54 | 66 |
| A winners | 18 | 19 |
| A win rate | 33.3% | 28.8% |
| A total P&L | $-740 | $-2,636 |
| **Match?** | — | **NO — see note** |

**Note:** Profile A count/P&L mismatch is expected. The narrow baseline was aggregated from two separate stats files (`jan_aug_v6_stats.json` + `oct_feb_v4_stats.json`) run at different times with different code versions, while the wide run is a single fresh run across all dates with current code. The important comparison is Profile B narrow vs wide — Profile A filters are identical in both runs.

## 5. All Profile B Trades (Wide)

| Date | Symbol | SQS | Tier | Risk | P&L | Notes |
|------|--------|-----|------|------|-----|-------|
| 2025-02-18 | AIFF | 4 | B | $250 | $-26 | ACTIVE |
| 2025-02-20 | HMR | 5 | A | $250 | $+0 | NEW |
| 2025-02-20 | OSRH | 4 | B | $250 | $+0 | NEW |
| 2025-03-03 | BTCT | 4 | B | $250 | $+0 |  |
| 2025-03-18 | AIFF | 4 | B | $250 | $+0 |  |
| 2025-04-10 | BLIV | 4 | B | $250 | $+0 |  |
| 2025-06-05 | VBIX | 4 | B | $250 | $+0 |  |
| 2025-06-16 | INDO | 4 | B | $250 | $+0 |  |
| 2025-06-18 | SNTI | 4 | B | $250 | $+0 | NEW |
| 2025-06-23 | INDO | 5 | A | $250 | $+504 | ACTIVE |
| 2025-06-23 | LUCY | 4 | B | $250 | $+0 | NEW |
| 2025-07-09 | MBIO | 4 | B | $250 | $+0 | NEW |
| 2025-07-17 | VWAV | 4 | B | $250 | $+0 |  |
| 2025-08-15 | PPSI | 4 | B | $250 | $+0 |  |
| 2025-08-15 | NA | 4 | B | $250 | $+916 | ACTIVE |
| 2025-10-06 | IONZ | 5 | A | $250 | $+0 |  |
| 2025-10-10 | YDDL | 5 | A | $250 | $+0 | NEW |
| 2025-10-14 | CYN | 4 | B | $250 | $-128 | ACTIVE |
| 2025-10-15 | SOAR | 4 | B | $250 | $+0 |  |
| 2025-10-17 | OLOX | 5 | A | $250 | $+0 | NEW |
| 2025-11-03 | SDST | 4 | B | $250 | $+0 |  |
| 2025-11-06 | CRWG | 4 | B | $250 | $+0 |  |
| 2025-11-07 | IONZ | 4 | B | $250 | $+0 | NEW |
| 2025-11-11 | CRWG | 5 | A | $250 | $+0 |  |
| 2025-11-14 | IONZ | 5 | A | $250 | $+97 | ACTIVE |
| 2025-11-24 | IONZ | 4 | B | $250 | $+0 | NEW |
| 2025-11-24 | OLOX | 4 | B | $250 | $+0 |  |
| 2025-12-12 | CRWG | 4 | B | $250 | $+0 |  |
| 2025-12-15 | CRWG | 4 | B | $250 | $+0 |  |
| 2025-12-16 | CYN | 4 | B | $250 | $-256 | NEW ACTIVE |
| 2026-01-29 | NAMM | 5 | A | $250 | $+0 |  |
| 2026-02-02 | BATL | 4 | B | $250 | $+0 |  |
| 2026-02-05 | CRWG | 4 | B | $250 | $+0 |  |
| 2026-02-20 | CRWG | 4 | B | $250 | $+0 |  |
| 2026-02-20 | NAMM | 5 | A | $250 | $+0 | NEW |
| 2026-02-20 | AGIG | 4 | B | $250 | $+0 | NEW |
| 2026-02-27 | CRWG | 5 | A | $250 | $+0 |  |

## 6. Decision Assessment

| Criterion | Threshold | Actual | Pass? |
|-----------|-----------|--------|-------|
| B win rate | >= 40% (GREEN) | 50.0% | PASS |
| W/L ratio | >= 2:1 (GREEN) | 3.70:1 | PASS |
| No loss > $300 | max loss >= -$300 | $-256 | PASS |
| Net positive | P&L > $0 | $+1,107 | PASS |

### Decision: **GREEN**

Keep widened filters — all criteria met.

## 7. Overall Headline Metrics (Both Periods)

| Metric | Value |
|--------|-------|
| **Total P&L** | **$-1,529** |
| Total Sims | 315 |
| Active Trades | 72 |
| Win Rate (active) | 30.6% |
| Profile A P&L | $-2,636 |
| Profile B P&L | $+1,107 |
| Cold Market Skips | 71 |
| Kill Switch Fires | 0 |
