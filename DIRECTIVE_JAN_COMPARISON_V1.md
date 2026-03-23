# DIRECTIVE: January 2025 vs January 2026 Side-by-Side Comparison

**Author**: Cowork (Opus)
**Date**: 2026-03-23 (v2 — adds SQ exit fixes)
**For**: CC (Sonnet)
**Purpose**: Run the full bot with ALL current fixes (scanner + squeeze exits + strategies) on both January 2025 and January 2026, then produce a side-by-side comparison report.

---

## Context

Scanner Fixes V1 just landed (commit `6a91afe`): unknown-float gate, rescan fix, EDGAR/AlphaVantage float fallbacks, cache invalidation. We need to validate these changes AND see how the full current config performs across two complete months.

**Why two months?**
- **Jan 2025**: We have Ross Cameron's actual trades for every day — this is the ground truth benchmark. Shows how much of the scanner gap we've closed.
- **Jan 2026**: Our existing baseline month with full tick cache. Shows current bot performance on stocks it actually found.

**IMPORTANT — Squeeze exit fixes included in this run:**
The current ENV_BASE in `run_ytd_v2_backtest.py` is MISSING the squeeze exit fixes. These were coded (simulate.py lines 195-205) but never added to the batch runner. The 2026-03-23 daily backtest showed AHMA hitting `sq_target_hit` and chopping at exactly 2R — the exact problem these fixes solve. This run enables ALL of them:
- `WB_SQ_PARTIAL_EXIT_ENABLED=1` — take 50% at target, let runner continue
- `WB_SQ_WIDE_TRAIL_ENABLED=1` — 2x wider parabolic trail for winners
- `WB_SQ_RUNNER_DETECT_ENABLED=1` — 3x trail when target hit in <5 min (fast runners)
- `WB_HALT_THROUGH_ENABLED=1` — don't stop-out during halt/grace periods

---

## Step 1: Re-generate January 2025 Scanner Results

The existing `scanner_results/2025-01-*.json` files were generated BEFORE the rescan fix. The rescan function found 0 stocks across all of January. Re-run `scanner_sim.py` for all 20 Jan 2025 trading days to:
- Pick up any new candidates from the fixed `find_emerging_movers()`
- Verify EDGAR/Alpha Vantage float fallbacks resolve previously-None floats
- Confirm cache invalidation clears stale Nones

**IMPORTANT**: Before re-running, back up the existing scanner results:
```bash
mkdir -p scanner_results/backup_2025_01_pre_v1
cp scanner_results/2025-01-*.json scanner_results/backup_2025_01_pre_v1/
```

Then re-run scanner_sim for each January 2025 date:
```bash
source venv/bin/activate
for date in 2025-01-02 2025-01-03 2025-01-06 2025-01-07 2025-01-08 2025-01-09 2025-01-10 2025-01-13 2025-01-14 2025-01-15 2025-01-16 2025-01-17 2025-01-21 2025-01-22 2025-01-23 2025-01-24 2025-01-27 2025-01-28 2025-01-29 2025-01-30 2025-01-31; do
    echo "=== $date ==="
    python scanner_sim.py $date
done
```

After re-run, compare old vs new:
```bash
python3 -c "
import json, os
for fname in sorted(os.listdir('scanner_results')):
    if not fname.startswith('2025-01') or not fname.endswith('.json'):
        continue
    with open(f'scanner_results/{fname}') as f:
        new = json.load(f)
    old_path = f'scanner_results/backup_2025_01_pre_v1/{fname}'
    if os.path.exists(old_path):
        with open(old_path) as f:
            old = json.load(f)
    else:
        old = []
    new_syms = {c['symbol'] for c in new}
    old_syms = {c['symbol'] for c in old}
    added = new_syms - old_syms
    rescan = [c for c in new if c.get('method') == 'rescan']
    if added or rescan:
        print(f'{fname}: {len(old)} → {len(new)} candidates (+{len(added)} new: {added}), {len(rescan)} via rescan')
    else:
        print(f'{fname}: {len(old)} → {len(new)} candidates (no change)')
"
```

**Capture the diff output** — this is key evidence of what the scanner fixes unlocked.

---

## Step 2: Build the Comparison Runner

Create `run_jan_v1_comparison.py` — a single script that runs BOTH months with identical config and produces a unified report.

### Config (identical for both months)

The full ENV_BASE — copy from `run_ytd_v2_backtest.py` and ADD scanner + squeeze exit fixes:
```python
ENV_BASE = {
    # --- Core strategy ---
    "WB_CLASSIFIER_ENABLED": "1",
    "WB_CLASSIFIER_RECLASS_ENABLED": "1",
    "WB_EXHAUSTION_ENABLED": "1",
    "WB_WARMUP_BARS": "5",
    "WB_CONTINUATION_HOLD_ENABLED": "1",
    "WB_CONT_HOLD_5M_TREND_GUARD": "1",
    "WB_CONT_HOLD_5M_VOL_EXIT_MULT": "2.0",
    "WB_CONT_HOLD_5M_MIN_BARS": "2",
    "WB_CONT_HOLD_MIN_VOL_DOM": "2.0",
    "WB_CONT_HOLD_MIN_SCORE": "8.0",
    "WB_CONT_HOLD_MAX_LOSS_R": "0.5",
    "WB_CONT_HOLD_CUTOFF_HOUR": "10",
    "WB_CONT_HOLD_CUTOFF_MIN": "30",
    "WB_MAX_NOTIONAL": "50000",
    "WB_MAX_LOSS_R": "0.75",
    "WB_NO_REENTRY_ENABLED": "1",
    # --- Strategy 2: Squeeze V2 ---
    "WB_SQUEEZE_ENABLED": "1",
    "WB_SQ_VOL_MULT": "3.0",
    "WB_SQ_MIN_BAR_VOL": "50000",
    "WB_SQ_MIN_BODY_PCT": "1.5",
    "WB_SQ_PRIME_BARS": "3",
    "WB_SQ_MAX_R": "0.80",
    "WB_SQ_LEVEL_PRIORITY": "pm_high,whole_dollar,pdh",
    "WB_SQ_PROBE_SIZE_MULT": "0.5",
    "WB_SQ_MAX_ATTEMPTS": "3",
    "WB_SQ_PARA_ENABLED": "1",
    "WB_SQ_PARA_STOP_OFFSET": "0.10",
    "WB_SQ_PARA_TRAIL_R": "1.0",
    "WB_SQ_NEW_HOD_REQUIRED": "1",
    "WB_SQ_MAX_LOSS_DOLLARS": "500",
    "WB_SQ_TARGET_R": "2.0",
    "WB_SQ_CORE_PCT": "75",
    "WB_SQ_RUNNER_TRAIL_R": "2.5",
    "WB_SQ_TRAIL_R": "1.5",
    "WB_SQ_STALL_BARS": "5",
    "WB_SQ_VWAP_EXIT": "1",
    "WB_SQ_PM_CONFIDENCE": "1",
    "WB_PILLAR_GATES_ENABLED": "1",
    "WB_MP_ENABLED": "1",
    # --- NEW: Scanner fixes ---
    "WB_ALLOW_UNKNOWN_FLOAT": "1",
    # --- NEW: Squeeze exit fixes (were coded but OFF in batch runner) ---
    "WB_SQ_PARTIAL_EXIT_ENABLED": "1",   # 50% at target, runner continues
    "WB_SQ_WIDE_TRAIL_ENABLED": "1",     # 2x wider parabolic trail
    "WB_SQ_RUNNER_DETECT_ENABLED": "1",  # 3x trail when target hit <5 min
    "WB_HALT_THROUGH_ENABLED": "1",      # Don't stop-out during halts
}
```

### Dates

```python
JAN_2025_DATES = [
    "2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08",
    "2025-01-09", "2025-01-10", "2025-01-13", "2025-01-14", "2025-01-15",
    "2025-01-16", "2025-01-17", "2025-01-21", "2025-01-22", "2025-01-23",
    "2025-01-24", "2025-01-27", "2025-01-28", "2025-01-29", "2025-01-30",
    "2025-01-31",
]

JAN_2026_DATES = [
    "2026-01-02", "2026-01-03", "2026-01-05", "2026-01-06", "2026-01-07",
    "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13", "2026-01-14",
    "2026-01-15", "2026-01-16", "2026-01-20", "2026-01-21", "2026-01-22",
    "2026-01-23", "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29",
    "2026-01-30",
]
```

Note: Some Jan 2025 dates may not have scanner results (no JSON file = market holiday or no candidates). Skip gracefully.

### Runner Logic

Copy the `load_and_rank()`, `rank_score()`, and `run_sim()` functions from `run_ytd_v2_backtest.py` (keep them in sync). For each period:

1. Load scanner JSON for that date
2. Filter and rank candidates (top 5)
3. Sim each with `--ticks --tick-cache tick_cache/`
4. Track: equity curve, per-day P&L, per-trade details, strategy breakdown (SQ vs MP)
5. Use $30K starting equity, 2.5% risk, 5 trades/day cap, -$1,500 daily loss limit

### Output Format

Print a side-by-side summary table at the end:

```
╔═══════════════════════════════════════════════════════════════════════╗
║            JANUARY COMPARISON: 2025 vs 2026                         ║
╠═══════════════════════════════╦═══════════════╦═══════════════════════╣
║ Metric                        ║  Jan 2025     ║  Jan 2026             ║
╠═══════════════════════════════╬═══════════════╬═══════════════════════╣
║ Trading Days                  ║  XX           ║  XX                   ║
║ Scanner Candidates (total)    ║  XX           ║  XX                   ║
║ Candidates Passing Filters    ║  XX           ║  XX                   ║
║ Unknown-Float Candidates      ║  XX           ║  XX                   ║
║ Rescan Candidates             ║  XX           ║  XX                   ║
║ Total Trades                  ║  XX           ║  XX                   ║
║ SQ Trades / MP Trades         ║  XX / XX      ║  XX / XX              ║
║ Win Rate                      ║  XX%          ║  XX%                  ║
║ Total P&L                     ║  $XX,XXX      ║  $XX,XXX              ║
║ Avg P&L / Day                 ║  $X,XXX       ║  $X,XXX               ║
║ Profit Factor                 ║  X.XX         ║  X.XX                 ║
║ Max Drawdown                  ║  $X,XXX       ║  $X,XXX               ║
║ Best Day                      ║  $XX,XXX      ║  $XX,XXX              ║
║ Worst Day                     ║  -$X,XXX      ║  -$X,XXX              ║
║ Ending Equity                 ║  $XX,XXX      ║  $XX,XXX              ║
╚═══════════════════════════════╩═══════════════╩═══════════════════════╝
```

Also print per-day detail for each month:
```
Date        Candidates  Traded  Trades  P&L       Equity    Best Trade
2025-01-02  3           2       4       +$1,234   $31,234   GDTC +$800
...
```

And save full results to JSON state file: `jan_comparison_v1_state.json`

---

## Step 3: Run It

```bash
source venv/bin/activate
python run_jan_v1_comparison.py 2>&1 | tee jan_comparison_v1_output.txt
```

This will take a while (40+ dates × 5 stocks × tick replay). Let it run.

---

## Step 4: Regression Check

The SQ exit fixes ONLY affect squeeze trades. MP regressions should be unchanged, but verify:
```bash
WB_MP_ENABLED=1 WB_SQ_PARTIAL_EXIT_ENABLED=1 WB_SQ_WIDE_TRAIL_ENABLED=1 WB_SQ_RUNNER_DETECT_ENABLED=1 WB_HALT_THROUGH_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583 (VERO is MP-only, SQ fixes should not affect it)

WB_MP_ENABLED=1 WB_SQ_PARTIAL_EXIT_ENABLED=1 WB_SQ_WIDE_TRAIL_ENABLED=1 WB_SQ_RUNNER_DETECT_ENABLED=1 WB_HALT_THROUGH_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444 (ROLR is MP-only, SQ fixes should not affect it)
```

If either regression CHANGES (should not — these are MP trades), stop and investigate before proceeding.

---

## Step 5: Produce Report

Save a markdown report to `cowork_reports/2026-03-23_jan_comparison_v1.md` with:

1. **Summary table** (the side-by-side from above)
2. **Scanner improvement metrics**: How many new candidates did the fixes add in Jan 2025? How many via rescan? How many unknown-float stocks now tradeable?
3. **Per-day detail** for both months
4. **Top 5 trades** for each month (symbol, date, strategy, P&L)
5. **Bottom 5 trades** for each month
6. **Strategy breakdown**: SQ vs MP trade count, win rate, and P&L for each month
7. **Jan 2025 vs Ross**: For dates where we have Ross's actual P&L (from `cowork_reports/missed_stocks_backtest_plan.md`), show bot P&L vs Ross P&L side by side
8. **SQ exit fix impact**: Note any trades where the partial/runner/wide-trail changed the outcome vs what a hard sq_target_hit exit would have done

---

## Step 6: Commit and Push

```bash
git add run_jan_v1_comparison.py jan_comparison_v1_state.json jan_comparison_v1_output.txt cowork_reports/2026-03-23_jan_comparison_v1.md scanner_results/backup_2025_01_pre_v1/
git commit -m "$(cat <<'EOF'
Jan 2025 vs Jan 2026 comparison: scanner fixes + SQ exit fixes

Re-ran scanner_sim for Jan 2025 with: unknown-float gate, rescan fix,
EDGAR/AlphaVantage float fallbacks, cache invalidation. Backtested both
months with SQ exit fixes enabled (partial exit, wide trail, runner detect,
halt-through) — these were coded but previously missing from batch runner.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## What We're Looking For

1. **Scanner fix validation**: Do we see MORE candidates in Jan 2025 after the rescan fix? Do unknown-float stocks (GDTC, AMOD, etc.) now get traded?
2. **SQ exit fix impact**: Do the partial/runner/trail fixes improve SQ trade P&L vs the hard 2R target chop?
3. **Bot consistency**: Is the bot profitable in BOTH months, or is Jan 2025 an anomaly?
4. **Strategy mix**: Is SQ still doing all the work, or does MP contribute in Jan 2025?
5. **Daily consistency**: How many green days vs red days in each month?
6. **Ross comparison**: On the Jan 2025 dates where we know Ross's P&L, what % are we capturing?

This is the definitive "before/after" test for all the work done this month.
