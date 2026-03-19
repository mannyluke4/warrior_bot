# DIRECTIVE: V6.2 Expanded Backtest — Jan-Aug 2025 Profile B Sample Expansion
**Date:** 2026-03-10
**Branch:** v6-dynamic-sizing
**Priority:** HIGH — Profile B has only 2 trades in 5 months. We need more data before making any tuning decisions.

---

## OBJECTIVE

Run the V6.2 backtest across the Jan-Aug 2025 scanner data (154 dates) to expand the Profile B sample size. The Oct 2025 — Feb 2026 data gives us only 16 B sims (2 trades). Adding Jan-Aug 2025 could 3-4x that, giving us enough data to identify real patterns.

---

## CONTEXT

Profile B's investigation revealed:
- Classifier filters B stocks at the same ~85% rate as A stocks (working correctly)
- Only 2 B trades in 102 days — not enough to optimize anything
- The repo already has 154 scanner JSON files from Jan-Aug 2025 (commit 00274071)
- V6.2 risk cap ($250 max for Profile B) must be active for all runs

---

## STEP 1: Run Extended Backtest on Jan-Aug 2025

Use `run_backtest_v4_extended.py` (or adapt it) to process the Jan-Aug 2025 scanner dates. The scanner JSON files are already in `scanner_results/` (2025-01-02.json through 2025-08-15.json).

**Critical settings:**
- V6.2 Profile B risk cap MUST be active (`if profile == 'B' and risk > 250: risk = 250`)
- Profile A: Alpaca ticks (`--ticks --no-fundamentals`)
- Profile B: Databento ticks (`--ticks --feed databento --l2 --no-fundamentals`)
- Starting equity: $30K
- Dynamic sizing: 2.5% of equity, $250 floor, $1,500 ceiling
- Signal mode exits: DO NOT suppress

**Important:** If the extended backtest script only covers Oct-Feb dates, it needs to be updated to include the Jan-Aug 2025 date range. The scanner JSON files already exist — the script just needs to iterate over them.

---

## STEP 2: Record Profile B Results Separately

We need Profile B metrics isolated. Track:

### Profile B — Jan-Aug 2025
| Metric | Value |
|--------|-------|
| Total B sims | ? |
| Active B trades (P&L ≠ $0) | ? |
| B trade rate | ? |
| B wins / B losses | ? |
| B win rate | ? |
| B total P&L | ? |
| B avg win | ? |
| B avg loss | ? |

### Profile B — Full Period (Jan 2025 — Feb 2026)
Combine Jan-Aug 2025 + Oct 2025 — Feb 2026 for the complete picture.

| Metric | Oct-Feb Only | Jan-Aug Only | Combined |
|--------|-------------|-------------|----------|
| Total B sims | 16 | ? | ? |
| Active B trades | 2 | ? | ? |
| B total P&L | +$70 | ? | ? |

### Per-Trade Profile B Detail (Jan-Aug 2025)
List every Profile B sim:

| Date | Symbol | SQS | Tier | Risk | P&L | Notes |
|------|--------|-----|------|------|-----|-------|

---

## STEP 3: Profile B Candidate Funnel (Jan-Aug 2025)

Track the funnel to understand candidate flow:

| Stage | Count |
|-------|-------|
| Scanner B candidates (float 5-10M) | ? |
| Pass price + gap filter | ? |
| Survive max-2/day + SQS + B-gate | ? |
| Actually trade (P&L ≠ $0) | ? |

---

## STEP 4: Profile A Comparison (Jan-Aug 2025)

Also capture Profile A results for the same period so we can compare:

| Metric | Profile A | Profile B |
|--------|-----------|-----------|
| Total sims | ? | ? |
| Active trades | ? | ? |
| Total P&L | ? | ? |
| Win rate | ? | ? |

---

## STEP 5: Save Results

Save to `PROFILE_B_EXPANDED_BACKTEST_RESULTS.md` in the repo root.

This becomes our expanded baseline. If Profile B has enough trades (6+), we can start identifying patterns. If it still only has 2-3 trades, we'll know the current filters are too tight and need widening.

---

## STEP 6: Decision Point

Based on results, one of these paths:

**If 6+ Profile B trades:** Enough data to analyze patterns. Look at:
- Which B stocks win vs lose — what characteristics differ?
- Do winning B stocks have specific PM volume ranges?
- Do winning B stocks cluster in certain months/market conditions?
- Is the L2 system helping or hurting?

**If < 6 Profile B trades:** Sample size still too small. Next step is widening filters:
- Raise float ceiling from 10M to 15M
- Raise gap cap from 25% to 35%
- Raise max-per-day from 2 to 3
- Re-run the full backtest with wider filters

Do NOT implement filter changes without reporting results first. We decide together.

---

## KEY RULES (DO NOT VIOLATE)
- Signal mode cascading exits — DO NOT suppress exits in signal mode
- Profile A uses Alpaca ticks; Profile B uses Databento ticks
- Starting account size is always $30K
- V6.2 risk cap: Profile B max $250 risk regardless of SQS
- January 2026 was hot market, February 2026 was cold — report any similar patterns in Jan-Aug 2025
- Report ALL results before making any changes. Observation first.
