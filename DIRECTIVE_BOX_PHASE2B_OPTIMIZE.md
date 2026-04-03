# DIRECTIVE: Box Phase 2B — Exit Optimization + Scanner Filter Tightening

**Date:** April 3, 2026
**Author:** Cowork (Opus)
**For:** CC (Claude Code)
**Priority:** P1
**Depends on:** Phase 2 backtest complete (160 trades, +$8,717, 62.5% WR)

---

## Context: What Phase 2 Told Us

The baseline backtest proved the box strategy has a real edge. But two clear optimization opportunities jumped out:

1. **156 of 160 trades exit via time stop at 3:45 PM.** The stock mean-reverts from the buy zone toward the middle, but rarely reaches the sell zone (top 25%). We're leaving money on the table by holding until close instead of taking profits at mid-box or VWAP.

2. **Certain filter combinations dramatically outperform.** Tight ranges (2-4%) hit 83% WR. High total tests (≥6) hit 76% WR. The combo (2-4% range + ≥6 tests) hits 79% WR at $120/trade. We can narrow the scanner to focus on these high-conviction setups.

This directive has two parts: **exit optimization** (capture gains earlier) and **scanner tightening** (trade only the best setups).

---

## Part 1: Exit Optimization — Run 4 Variants

Re-run the backtest on the same 661 candidates using the cached 1m bars (no new IBKR pulls needed — everything is in `box_backtest_cache/`). Run these 4 exit variants and compare:

### Variant A: Baseline (already done)
- Exit at sell zone (top 25%) or time stop at 3:45 PM
- Result: 160 trades, +$8,717, 62.5% WR, $54.48 avg

### Variant B: VWAP Exit
- Exit when price crosses above VWAP (if entry was below VWAP)
- If entry was above VWAP (rare, but possible near mid-box), use sell zone target
- Keep all other exits the same (hard stop, box invalidation, session loss cap, time stop)
- `WB_BOX_VWAP_EXIT_ENABLED=1`

### Variant C: Mid-Box Exit
- Exit when price reaches box_mid = (box_top + box_bottom) / 2
- This is the mean-reversion target — stock returns to the center
- New env var: `WB_BOX_MID_EXIT_ENABLED=1`
- Keep all other exits the same

### Variant D: Tiered Exit (Partial at VWAP, Rest at Sell Zone)
- Take 75% of position at VWAP
- Trail remaining 25% with trail stop (30% of box_range from peak)
- If trail doesn't trigger, time stop the remainder at 3:45 PM
- New env var: `WB_BOX_TIERED_EXIT_ENABLED=1`
- This tests whether capturing quick VWAP profits + riding a runner outperforms full exits

### Implementation Notes

Add a `--exit-variant` CLI flag to box_backtest.py:

```bash
python box_backtest.py --exit-variant baseline   # Variant A (already exists)
python box_backtest.py --exit-variant vwap        # Variant B
python box_backtest.py --exit-variant midbox      # Variant C
python box_backtest.py --exit-variant tiered      # Variant D
```

Each variant writes its own results:
- `box_backtest_results/variant_B_vwap/per_candidate.csv`
- `box_backtest_results/variant_B_vwap/all_trades.csv`
- `box_backtest_results/variant_C_midbox/per_candidate.csv`
- `box_backtest_results/variant_C_midbox/all_trades.csv`
- `box_backtest_results/variant_D_tiered/per_candidate.csv`
- `box_backtest_results/variant_D_tiered/all_trades.csv`

### Comparison Report

Generate `box_backtest_results/EXIT_VARIANT_COMPARISON.md` with a side-by-side table:

```
| Metric              | A: Baseline | B: VWAP | C: Mid-Box | D: Tiered |
|---------------------|-------------|---------|------------|-----------|
| Total trades        |             |         |            |           |
| Wins                |             |         |            |           |
| Win rate            |             |         |            |           |
| Total P&L           |             |         |            |           |
| Avg P&L/trade       |             |         |            |           |
| Avg hold (min)      |             |         |            |           |
| Profit factor       |             |         |            |           |
| Max drawdown        |             |         |            |           |
| Avg winner          |             |         |            |           |
| Avg loser           |             |         |            |           |
| % exits at target   |             |         |            |           |
| % exits at time     |             |         |            |           |
| Re-entries enabled* |             |         |            |           |
```

*Re-entry note: Variants B/C/D should produce MORE trades than baseline because exiting earlier frees the position slot for re-entries on the same stock. If a stock hits VWAP at 11:30 AM and drops back to the buy zone at 1:00 PM, the strategy can re-enter (up to max 2 per stock). Report the re-entry count for each variant.

Also include the per-variant breakdown by:
- Exit reason distribution
- Performance by range_pct bucket (same buckets as Phase 2 report)
- Performance by total_tests bucket

---

## Part 2: Scanner Filter Tightening

Based on Phase 2 correlation analysis, apply these tighter filters and re-run Variant A + the winning exit variant from Part 1.

### Filter Set 1: "Proven Box" (Conservative)
```bash
WB_BOX_MIN_RANGE_PCT=2.0       # Keep minimum at 2%
WB_BOX_MAX_RANGE_PCT=6.0       # Tighten from 15% → 6% (wider ranges underperform)
WB_BOX_MIN_HIGH_TESTS=2        # Keep at 2
WB_BOX_MIN_LOW_TESTS=2         # Keep at 2
WB_BOX_MIN_TOTAL_TESTS=5       # NEW: require 5+ total tests (was 4 implicit min)
WB_BOX_MIN_PRICE=15.00         # Raise from $5 → $15 (sub-$15 stocks: 44% WR, $10 avg)
```

### Filter Set 2: "High Conviction" (Aggressive)
```bash
WB_BOX_MIN_RANGE_PCT=2.0
WB_BOX_MAX_RANGE_PCT=4.0       # Tight range only (83% WR bucket)
WB_BOX_MIN_HIGH_TESTS=3        # 3+ resistance tests
WB_BOX_MIN_LOW_TESTS=3         # 3+ support tests (total ≥ 6)
WB_BOX_MIN_PRICE=15.00
WB_BOX_MAX_ADR_UTIL=0.50       # Low today-ADR (stock is quiet today)
```

### Filter Set 3: "Volume Sweet Spot"
Same as Filter Set 1, plus:
```bash
WB_BOX_SKIP_FRIDAY=1           # NEW: Fridays are nearly zero EV ($4 avg P&L)
```

### Implementation

Add a `--filter-set` CLI flag:

```bash
python box_backtest.py --exit-variant [winner] --filter-set proven    # Filter Set 1
python box_backtest.py --exit-variant [winner] --filter-set highconv  # Filter Set 2
python box_backtest.py --exit-variant [winner] --filter-set volsweet  # Filter Set 3
```

Each filter set re-evaluates which candidates from `scanner_results_box/*.json` pass the tighter filters, then runs the strategy only on those. Output to:
- `box_backtest_results/filter_proven/`
- `box_backtest_results/filter_highconv/`
- `box_backtest_results/filter_volsweet/`

### Filter Comparison Report

Generate `box_backtest_results/FILTER_COMPARISON.md`:

```
| Metric              | Baseline (all) | Proven Box | High Conviction | Vol Sweet Spot |
|---------------------|----------------|------------|-----------------|----------------|
| Candidates passing  |                |            |                 |                |
| Candidates traded   |                |            |                 |                |
| Total trades        |                |            |                 |                |
| Win rate            |                |            |                 |                |
| Total P&L           |                |            |                 |                |
| Avg P&L/trade       |                |            |                 |                |
| Profit factor       |                |            |                 |                |
| Worst trade         |                |            |                 |                |
| Max daily loss      |                |            |                 |                |
| Consistency*        |                |            |                 |                |
```

*Consistency = % of trading days with positive box P&L. We need this number to be high (>60%) before scaling up size.

Also include for each filter set:
- The symbols that pass the filter (shows us our actual trading universe)
- Per-symbol P&L (are the same winners still winning?)
- Monthly breakdown (is it consistent Jan/Feb/Mar or front-loaded?)

---

## Part 3: Combined Best Config Report

After Parts 1 and 2, generate one final report: `box_backtest_results/BEST_CONFIG_REPORT.md`

Pick the best exit variant × best filter set combo and show:

1. **The recommended config** — exact env var values
2. **Full P&L curve** — cumulative P&L day by day (as a text table, no chart needed)
3. **Worst-case analysis** — max drawdown, worst 5 trades, longest losing streak
4. **Scaling projection** — what the P&L would be at $75K and $100K notional (simple linear scale from $50K base, since we're not hitting liquidity limits on these stocks)
5. **Universe snapshot** — the actual symbols and frequency in the filtered set. How many unique stocks are we trading? How many trade days have candidates?

This report is what we'll use to decide whether to increase position size and move to Phase 3 (live integration).

---

## Execution Order

1. `git pull`
2. Add `--exit-variant` support to box_backtest.py (modify box_strategy.py to support VWAP/midbox/tiered exits)
3. Run Variants B, C, D (use cached bars — should be fast)
4. Generate EXIT_VARIANT_COMPARISON.md
5. **Decide winning exit variant** — pick the one with highest avg P&L/trade AND win rate > 60%
6. Add `--filter-set` support
7. Run 3 filter sets with the winning exit variant
8. Generate FILTER_COMPARISON.md
9. Generate BEST_CONFIG_REPORT.md with the optimal combo
10. `git push`
11. **STOP** — push and stop. We review before any live integration.

---

## What NOT to Do

- Do NOT re-pull 1m bars from IBKR — use the cached data in `box_backtest_cache/`
- Do NOT modify the baseline results in `box_backtest_results/` — write variant results to subdirectories
- Do NOT wire anything into bot_v3_hybrid.py
- Do NOT change box_scanner.py — filter tightening is applied at backtest time by re-filtering scanner output, not by changing the scanner itself
- Do NOT use Alpaca for anything
- Do NOT proceed past step 11
