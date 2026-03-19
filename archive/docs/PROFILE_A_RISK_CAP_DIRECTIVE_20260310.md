# DIRECTIVE: Profile A Risk Cap — Universal Sizing for All Market Regimes
**Date:** 2026-03-10
**Branch:** v6-dynamic-sizing
**Priority:** HIGH — Profile A is overfitting to familiar dates. Apply the same risk discipline that makes Profile B stable.

---

## CONTEXT — WHY WE'RE DOING THIS

Profile A performance degrades every time we expand the test range:

| Test Period | Profile A P&L | Win Rate | Notes |
|-------------|--------------|----------|-------|
| Jan-Feb 2026 (V4) | +$5,402 | ~40% | Familiar data, heavily optimized |
| Oct-Feb 2026 (V4 ext) | +$7,885 | 50% | Similar hot market, still looked great |
| Jan-Aug 2025 (V6.2) | -$6,218 | 22% | FIRST NEW DATES — collapsed |
| Full 14 months (fresh) | -$2,636 | 28.8% | Net negative across all data |

Profile B, by contrast, holds steady across all date ranges because it has a universal $250 risk cap. Profile A's problem isn't stock selection — it's that $750 risk on SQS 5+ stocks creates outsized losses when the market regime doesn't cooperate.

**Hypothesis:** If we cap Profile A's risk like we cap Profile B's, the system should survive cold/choppy markets without needing regime-specific filters.

---

## STEP 1: Implement Profile A Risk Cap

### Change: Cap Profile A risk at $500 regardless of SQS

In the SQS/tier assignment logic:

```python
# OLD:
if sqs >= 7:
    return sqs, "Shelved", 250
elif sqs >= 5:
    return sqs, "A", 750       # <-- This is the problem
elif sqs >= 4:
    return sqs, "B", 250
else:
    return sqs, "Skip", 0

# NEW:
if sqs >= 7:
    return sqs, "Shelved", 250
elif sqs >= 5:
    return sqs, "A", 500       # <-- Capped at $500
elif sqs >= 4:
    return sqs, "B", 250
else:
    return sqs, "Skip", 0
```

**Env toggle:** `WB_PROFILE_A_RISK_CAP=500` (default was effectively 750)

This should be a simple env var so we can test multiple values (400, 500, 600) without code changes.

### DO NOT CHANGE:
- Profile B risk cap: stays at $250
- SQS scoring logic: unchanged (SQS still determines WHICH stocks to trade)
- Cold market gate: leave as-is (we may remove it later but one change at a time)
- Signal mode exits: DO NOT suppress (this is the bot's core edge)
- B-gate thresholds: leave as-is
- Classifier: leave as-is

---

## STEP 2: Run the Full 260-Day Backtest

Run with the $500 A cap across BOTH periods:
1. **Jan-Aug 2025** (158 trading days) — the "validation" set
2. **Oct 2025-Feb 2026** (102 trading days) — the "training" set

Use the SAME code, single pass, all dates. No composite of separate runs.

**Profile A uses Alpaca ticks. Profile B uses Databento ticks.**

---

## STEP 3: Record Results — Three-Way Comparison

### Profile A: $750 vs $500 Risk Cap

| Metric | A @ $750 (baseline) | A @ $500 (new) | Delta |
|--------|-------------------|----------------|-------|
| Total sims | ? | ? | ? |
| Active trades | ? | ? | ? |
| Winners | ? | ? | ? |
| Losers | ? | ? | ? |
| Win rate | ? | ? | ? |
| Total P&L | ? | ? | ? |
| Avg win | ? | ? | ? |
| Avg loss | ? | ? | ? |
| Win/loss ratio | ? | ? | ? |
| Max drawdown ($) | ? | ? | ? |
| Max drawdown (%) | ? | ? | ? |

### Profile A by Period (The Key Test)

| Metric | Jan-Aug 2025 @ $750 | Jan-Aug 2025 @ $500 | Delta |
|--------|--------------------|--------------------|-------|
| P&L | -$6,218 | ? | ? |
| Win rate | 22% | ? | ? |
| Avg loss | -$404 | ? | ? |

| Metric | Oct-Feb 2026 @ $750 | Oct-Feb 2026 @ $500 | Delta |
|--------|--------------------|--------------------|-------|
| P&L | +$7,885 | ? | ? |
| Win rate | 50% | ? | ? |

**THE CRITICAL QUESTION:** Does the $500 cap reduce the Jan-Aug 2025 damage enough to make the combined system net positive, while still capturing enough upside in Oct-Feb?

### Profile B Validation (MUST BE UNCHANGED)

| Metric | Before | After |
|--------|--------|-------|
| B total P&L | ? | ? |
| B win rate | ? | ? |

If Profile B numbers changed, STOP. This change should only affect Profile A sizing.

### Combined System

| Metric | Old ($750 A) | New ($500 A) | Delta |
|--------|-------------|-------------|-------|
| Combined P&L | ? | ? | ? |
| Combined max DD | ? | ? | ? |
| Ending equity | ? | ? | ? |

---

## STEP 4: Per-Period P&L Curve

Break the P&L into monthly buckets so we can see how the cap affects each regime:

| Month | A P&L @ $750 | A P&L @ $500 | B P&L | Combined @ $500 |
|-------|-------------|-------------|-------|-----------------|
| Jan 2025 | ? | ? | ? | ? |
| Feb 2025 | ? | ? | ? | ? |
| Mar 2025 | ? | ? | ? | ? |
| Apr 2025 | ? | ? | ? | ? |
| May 2025 | ? | ? | ? | ? |
| Jun 2025 | ? | ? | ? | ? |
| Jul 2025 | ? | ? | ? | ? |
| Aug 2025 | ? | ? | ? | ? |
| (gap - Sep 2025) | — | — | — | — |
| Oct 2025 | ? | ? | ? | ? |
| Nov 2025 | ? | ? | ? | ? |
| Dec 2025 | ? | ? | ? | ? |
| Jan 2026 | ? | ? | ? | ? |
| Feb 2026 | ? | ? | ? | ? |

This is the real test. We want to see:
- ✅ Cold months (Apr, May, Jun) should lose LESS with the cap
- ✅ Hot months (Jan 2026, Oct 2025) should still be positive (smaller wins OK)
- ✅ No single month should crater the account

---

## STEP 5: Decision Criteria

### GREEN — Keep $500 cap:
- Combined system (A+B) is net positive across full 260 days
- Jan-Aug 2025 Profile A loss is reduced by at least 30% vs $750
- Oct-Feb 2026 Profile A is still positive (even if smaller)
- No single month loses more than $2,000

### YELLOW — Try $400 cap next:
- Combined system is still negative but closer to breakeven
- Jan-Aug 2025 improved but not enough
- Pattern is in the right direction

### RED — Risk cap alone isn't enough:
- Combined system is worse or similar
- The cap is cutting winners more than it's limiting losers
- Need a different approach (regime-adaptive sizing, fewer filters, etc.)

---

## STEP 6: Save Results

Save to `PROFILE_A_RISK_CAP_RESULTS.md` in the repo root.

Report ALL results before making any permanent changes. We observe first, decide together.

---

## KEY RULES (DO NOT VIOLATE)
- Profile B stays at $250 risk — NON-NEGOTIABLE
- Signal mode cascading exits — DO NOT suppress
- Profile A uses Alpaca ticks; Profile B uses Databento ticks
- Starting account size: $30K
- Single pass across all dates — no compositing separate runs
- Report results BEFORE deciding. Do not auto-commit as permanent.
- If the env var approach is simpler, just use `WB_PROFILE_A_RISK_CAP=500`

---

## PHILOSOPHY

We are no longer optimizing for a specific date range. We are building a system that works everywhere. Profile B proved this is possible — small risk, let the edge compound over time. Profile A needs the same discipline.

The question isn't "how do we make Jan-Feb 2026 more profitable?" It's "how do we make the system survive 14 months of real market conditions?"

If $500 works, great. If it doesn't, we try $400. If no fixed cap works, we revisit the entire A framework. But we start simple.
