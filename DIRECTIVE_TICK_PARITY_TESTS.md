# DIRECTIVE: Tick Data Parity Tests — RTVolume vs Historical + Order Execution Analysis

**Date:** April 7, 2026
**Author:** Cowork (Opus)
**For:** CC (Claude Code)
**Priority:** P1 — determines whether backtest results are achievable live
**Prereq:** April 6 seed bar fix (Option C) already deployed

---

## Context

CC's April 7 tick data parity report identified a **4x tick count gap** and **3.5x volume gap** between IBKR RTVolume (live feed) and IBKR `reqHistoricalTicks` (backtest data). Both are IBKR — different APIs with different granularity.

The entire YTD backtest portfolio (+$211K momentum, +$19,832 squeeze) was built on `reqHistoricalTicks` data. The live bot runs on RTVolume. We need to know if the squeeze detector behaves the same on both feeds.

Additionally, the live bot armed 4 times on April 6 and got **zero fills** — every entry order timed out. This is a separate execution issue that needs analysis.

Finally, the seed bar fix (Option C) needs validation: does the morning detector state match organic replay now?

**This directive has 3 independent tests. Run them all.**

---

## Test 1: vol_ratio Parity — RTVolume vs Historical Ticks

### Goal
Determine whether `vol_ratio` (the squeeze detector's arming threshold) computes the same value when fed RTVolume ticks vs `reqHistoricalTicks` ticks for the same stock-date-bar.

### Why This Matters
`_avg_prior_vol()` in `squeeze_detector.py` averages ALL prior 1m bar volumes (cumulative, not windowed). `vol_ratio = current_bar_volume / avg_prior_vol`. If RTVolume undercounts proportionally across both spike bars and quiet bars, the ratio is preserved and the detector fires on the same setups. If spikes are compressed more than quiet bars (plausible — rapid trade prints during volume explosions are exactly what an aggregator consolidates), then `vol_ratio` is systematically lower live, and the detector is harder to arm.

### Method

**Step 1: Pull historical ticks for April 6 test stocks.**
Use `ibkr_tick_fetcher.py` (or `ib.reqHistoricalTicks()` directly) to fetch tick-level historical data for:
- FCUV on 2026-04-06 (the backtest found 2 trades, +$1,224)
- MLEC on 2026-04-06 (the backtest found 1 trade, -$416)

Save to a separate directory (NOT overwriting the live tick cache):
```
tick_cache_historical/2026-04-06/FCUV.json.gz
tick_cache_historical/2026-04-06/MLEC.json.gz
```

**Step 2: Build a comparison harness.**
Create `test_vol_ratio_parity.py` that:

1. Loads BOTH tick sources for the same symbol-date:
   - RTVolume ticks from `tick_cache/2026-04-06/{symbol}.json.gz` (live data)
   - Historical ticks from `tick_cache_historical/2026-04-06/{symbol}.json.gz`

2. Replays each through an independent `TradeBarBuilder` + `SqueezeDetector` instance (same config, same .env settings).

3. For each 1m bar that closes, records:
   - Bar timestamp (ET)
   - Bar volume (from each source)
   - `avg_prior_vol` (from each source)
   - `vol_ratio` (from each source)
   - Detector state after the bar (IDLE/PRIMED/ARMED)

4. Outputs a comparison table:

```
Bar Time (ET) | RTVol Vol | Hist Vol | RTVol avg | Hist avg | RTVol ratio | Hist ratio | RTVol state | Hist state
07:00         |   12,345  |  45,678  |    8,901  |  32,456  |     1.4x    |     1.4x   | IDLE        | IDLE
07:01         |   38,901  | 142,345  |    9,123  |  33,456  |     4.3x    |     4.3x   | PRIMED      | PRIMED
...
```

5. At the end, prints a summary:
   - Average `vol_ratio` difference across all bars
   - Max `vol_ratio` divergence on any single bar
   - Whether both detectors armed on the same bars (Y/N for each bar)
   - Whether both detectors reached ARMED with the same entry price

**Step 3: Also run ADVB on April 7** (since that's the stock from the original parity report with known 4x gap). Pull historical ticks for ADVB 2026-04-07 and compare. Even though there were no squeeze setups, seeing how `vol_ratio` tracks across a full session is valuable.

### Expected Outcomes
- **If ratios track within 20%**: RTVolume undercount is proportional → detector will fire on same setups live. No action needed.
- **If ratios diverge >20% (especially on spike bars)**: RTVolume compresses spikes → need to either calibrate `WB_SQ_VOL_MULT` for live, or switch to `reqTickByTickData('AllLast')`.

### Output
Save the comparison data to:
```
parity_tests/vol_ratio_comparison_FCUV_20260406.csv
parity_tests/vol_ratio_comparison_MLEC_20260406.csv
parity_tests/vol_ratio_comparison_ADVB_20260407.csv
parity_tests/VOL_RATIO_PARITY_REPORT.md
```

---

## Test 2: Order Execution Analysis — Why 4 ARMEDs Got 0 Fills

### Goal
Determine why every entry order on April 6 timed out with no fill, and whether the limit pricing or timeout is too tight.

### The Data

Four orders placed, all timed out after 10 seconds:

| Time (ET) | Symbol | Entry Price | Limit (entry+$0.02) | Stop | R | Score |
|-----------|--------|-------------|---------------------|------|---|-------|
| 09:48:00 | FCUV | $8.45 | $8.47 | $8.27 | $0.18 | 9.2 |
| 16:03:26 | FCUV | $5.02 | $5.04 | $4.90 | $0.12 | 11.0 |
| 16:07:26 | MLEC | $10.02 | $10.04 | $9.90 | $0.12 | 10.0 |
| ~16:10 | PRFX | $3.02 | ~$3.04 | $2.90 | $0.12 | 7.6 |

### Method

**Step 1: For each order, check actual trade prices in the 10-second window after the order was placed.**

Using the RTVolume tick cache (`tick_cache/2026-04-06/{symbol}.json.gz`), find all ticks within 10 seconds after each entry signal time. Check:
- Did the stock actually trade at or below the limit price during those 10 seconds?
- What was the bid/ask spread around that time? (If RTVolume includes bid/ask, use it; otherwise note as unknown.)
- What volume traded in that 10-second window?

**Step 2: Classify each timeout.**

For each order, determine the likely cause:
- **Price never reached limit**: Stock was above $8.47 for the entire 10s window → limit too tight, or the entry signal fired late
- **Price reached limit but low volume**: Stock traded at $8.47 but only a few hundred shares → liquidity too thin to fill 2,062 shares
- **Price blew through**: Stock dropped through the entry zone too fast → order would have filled into a losing trade anyway (timeout was protective)

**Step 3: Recommendations.**

Based on findings, recommend:
- Should `limit_price = entry + 0.02` be widened? (e.g., `+ 0.05` or `+ 0.5%`)
- Should the 10-second timeout be extended? (e.g., 15s, 20s)
- Should any of these changes be gated by env var? (YES — always gate.)
- Are the afternoon entries (16:00+) worth pursuing at all, or is post-close liquidity too thin?

### Output
```
parity_tests/ORDER_TIMEOUT_ANALYSIS.md
```

---

## Test 3: Seed Fix Validation — Does Option C Match Organic Replay?

### Goal
Confirm that the tick-level seeding (Option C) produces the same squeeze detector state as organic replay for the morning session on April 6.

### Why This Matters
Option C was deployed mid-day April 6. We saw it produce ARMEDs in the afternoon. But we've never directly compared the detector's bar-by-bar state after Option C seeding vs organic replay to confirm they're truly identical.

### Method

**Step 1: Simulate the live bot's seed path.**

Write `test_seed_parity.py` that:
1. Loads FCUV RTVolume ticks from `tick_cache/2026-04-06/FCUV.json.gz`
2. Splits ticks at the discovery time (07:58 ET for FCUV per scanner_results)
3. **Path A (organic):** Replay ALL ticks from market open through `TradeBarBuilder` + `SqueezeDetector`
4. **Path B (seeded):** Use ticks before 07:58 to build bars via `TradeBarBuilder`, then replay the rest organically — simulating what the live bot does post-Option-C

Both paths use the same `SqueezeDetector` config from .env.

**Step 2: Compare detector state at every 1m bar boundary after 07:58.**

Record for both paths:
- Bar volume
- `avg_prior_vol`
- `vol_ratio`
- Detector state (IDLE/PRIMED/ARMED)
- EMA9 value
- Session HOD

**Step 3: If there's any divergence, identify the root cause.**

Common culprits:
- Bar boundaries not aligning (seed bars vs organic bars have different close times)
- Volume accumulation differences in the final partial bar before discovery time
- EMA initialization path difference

### Output
```
parity_tests/SEED_PARITY_REPORT.md
```

---

## Running the Tests

### Prerequisites
- IBKR Gateway running (needed for `reqHistoricalTicks` in Test 1)
- Existing tick cache at `tick_cache/2026-04-06/` (RTVolume live data)
- Python venv activated

### Execution Order
Tests 1, 2, and 3 are independent — run in any order. Test 2 only uses existing tick cache data (no IBKR connection needed). Tests 1 and 3 can run in parallel if IBKR is connected.

### Gate Rules
These tests are READ-ONLY analysis. They do not modify any production code, do not affect the live bot, and do not change any config. The test scripts and output go in `parity_tests/` directory.

If results suggest calibration changes (e.g., lowering `WB_SQ_VOL_MULT` for live), **do NOT implement them automatically**. Write the recommendation in the report. Manny and Cowork will review before any production changes.

---

## Deliverables Checklist

- [ ] `test_vol_ratio_parity.py` — Test 1 harness
- [ ] `test_seed_parity.py` — Test 3 harness
- [ ] `tick_cache_historical/2026-04-06/FCUV.json.gz` — Historical ticks
- [ ] `tick_cache_historical/2026-04-06/MLEC.json.gz` — Historical ticks
- [ ] `tick_cache_historical/2026-04-07/ADVB.json.gz` — Historical ticks
- [ ] `parity_tests/vol_ratio_comparison_FCUV_20260406.csv`
- [ ] `parity_tests/vol_ratio_comparison_MLEC_20260406.csv`
- [ ] `parity_tests/vol_ratio_comparison_ADVB_20260407.csv`
- [ ] `parity_tests/VOL_RATIO_PARITY_REPORT.md` — Test 1 findings + recommendation
- [ ] `parity_tests/ORDER_TIMEOUT_ANALYSIS.md` — Test 2 findings + recommendation
- [ ] `parity_tests/SEED_PARITY_REPORT.md` — Test 3 findings

---

*Directive by Cowork (Opus). For CC execution.*
