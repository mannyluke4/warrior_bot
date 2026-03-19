# DIRECTIVE: V6.2 Profile B Filter Widening — More Candidates, Same Risk Cap
**Date:** 2026-03-10
**Branch:** v6-dynamic-sizing
**Priority:** HIGH — Profile B has edge (3.68:1 win/loss ratio) but too few trades. Widen the net.

---

## OBJECTIVE

Widen Profile B's candidate filters to increase trade volume while keeping the $250 risk cap as the safety net. Run the full backtest (Jan-Aug 2025 + Oct-Feb 2026) with widened filters and compare against the current baseline.

---

## CONTEXT

Profile B V6.2 baseline (current filters):
- 26 sims → 6 active trades (3W/3L) → +$1,459 P&L
- 50% WR, avg win $668, avg loss $181, win/loss ratio 3.68:1
- B-gate blocks 72% of SQS=4 candidates — this is the primary bottleneck
- $250 risk cap protects against oversized losses

---

## STEP 1: Implement Filter Changes

Make these changes in `run_backtest_v4_extended.py` (and `run_backtest_v4.py` if needed). Each change should be toggleable via env var so we can A/B test.

### Change 1: Raise float ceiling from 10M to 15M
```python
# OLD:
elif p == 'B' and 5.0 <= flt <= 10.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 25.0:

# NEW:
elif p == 'B' and 5.0 <= flt <= 15.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 35.0:
```
**Why:** The current 10M ceiling is arbitrary. Mid-float stocks up to 15M can still have momentum. Also widen gap cap from 25% to 35% — Profile A goes up to 40%, no reason B should be capped at 25%.

**Env toggle:** `WB_PROFILE_B_FLOAT_MAX=15` (default was effectively 10)
**Env toggle:** `WB_PROFILE_B_GAP_MAX=35` (default was effectively 25)

### Change 2: Raise max per day from 2 to 3
```python
# OLD:
profile_b = profile_b[:2]

# NEW:
profile_b = profile_b[:3]
```
**Why:** On busy days (like 2025-10-15 with 12 B candidates), we're cutting viable stocks. One more slot gives the best candidate by PM volume a chance.

**Env toggle:** `WB_PROFILE_B_MAX_PER_DAY=3` (default was 2)

### Change 3: Relax B-gate thresholds
```python
# OLD:
if gap < 14.0 or pm_vol < 10_000:

# NEW:
if gap < 12.0 or pm_vol < 5_000:
```
**Why:** The B-gate is blocking 72% of SQS=4 candidates. Relaxing from gap>=14% to >=12% and pm_vol>=10K to >=5K should let through candidates with moderate momentum that currently get killed. These are $250 risk trades — the downside is capped.

**Env toggle:** `WB_B_GATE_GAP_MIN=12` (default was 14)
**Env toggle:** `WB_B_GATE_VOL_MIN=5000` (default was 10000)

### DO NOT CHANGE:
- V6.2 risk cap: Profile B stays at $250 max regardless of SQS
- Profile A filters: NOTHING changes for Profile A
- Classifier thresholds: Leave as-is
- Signal mode exits: DO NOT suppress

---

## STEP 2: Run the Full Backtest (Both Periods)

Run with widened filters across:
1. Jan-Aug 2025 (158 days)
2. Oct 2025 - Feb 2026 (102 days)

This gives us the full ~260 day picture.

**NOTE:** Profile B uses Databento ticks. If Databento data isn't available for some new candidates (especially higher-float stocks), fall back to Alpaca ticks with a note. Track which feed was used per sim.

---

## STEP 3: Record Results — Compare Narrow vs Wide

### Profile B Funnel Comparison
| Stage | Narrow (Current) | Wide (New) | Delta |
|-------|-----------------|------------|-------|
| Scanner B candidates | ? | ? | ? |
| Pass price+gap+float filter | ? | ? | ? |
| Survive SQS + B-gate | ? | ? | ? |
| Actually simulated | 26 | ? | ? |
| Active trades | 6 | ? | ? |

### Profile B Performance Comparison
| Metric | Narrow (Baseline) | Wide (New) | Delta |
|--------|------------------|------------|-------|
| Total sims | 26 | ? | ? |
| Active trades | 6 | ? | ? |
| Win rate | 50% | ? | ? |
| Total P&L | +$1,459 | ? | ? |
| Avg win | $668 | ? | ? |
| Avg loss | -$181 | ? | ? |
| Win/loss ratio | 3.68:1 | ? | ? |

### Profile A Validation (MUST BE UNCHANGED)
| Metric | Before | After |
|--------|--------|-------|
| A total P&L | ? | ? |
| A win rate | ? | ? |

If Profile A numbers changed, STOP. The widening should only affect Profile B candidate selection.

### Per-Trade Detail (New B Trades Only)
List every NEW Profile B sim that didn't exist in the narrow backtest:

| Date | Symbol | SQS | Tier | Risk | P&L | Which filter let it through? |
|------|--------|-----|------|------|-----|------------------------------|

Tag each new trade with which filter change enabled it:
- FLOAT (float was 10-15M, previously excluded)
- GAP (gap was 25-35%, previously excluded)
- BGATE (previously blocked by B-gate)
- SLOT (previously cut by max-2/day)

---

## STEP 4: Decision Criteria

### GREEN — Keep widened filters:
- B win rate stays >= 40%
- Win/loss ratio stays >= 2.0:1
- No individual trade loses more than $300 (at $250 risk)
- More total trades with similar or better P&L per trade

### YELLOW — Partial rollback:
- Win rate drops to 30-40% but P&L is still positive
- One filter change is clearly hurting (e.g., float 10-15M stocks all lose)
- Roll back the underperforming filter, keep the others

### RED — Full rollback:
- Win rate drops below 30%
- Win/loss ratio drops below 1.5:1
- New trades are net negative
- Revert to narrow filters

---

## STEP 5: Save Results

Save to `PROFILE_B_WIDE_FILTER_RESULTS.md` in the repo root.

Report ALL results before making any permanent filter changes. Observation first — we decide together whether to keep the widened filters.

---

## KEY RULES (DO NOT VIOLATE)
- V6.2 risk cap: Profile B max $250 risk regardless of SQS — this is NON-NEGOTIABLE
- Signal mode cascading exits — DO NOT suppress
- Profile A uses Alpaca ticks; Profile B uses Databento ticks (Alpaca fallback OK with note)
- Starting account size: $30K
- Report results BEFORE deciding. Do not auto-commit widened filters as permanent.
- Profile A must be completely unchanged by this work
