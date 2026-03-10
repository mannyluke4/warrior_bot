# V6.2 Profile B Risk Cap — Backtest Validation Report
**Date:** 2026-03-10
**Branch:** v6-dynamic-sizing
**Dataset:** Oct 2025 – Feb 2026 (102 trading days)

---

## The Fix
Profile B stocks (float 5-10M) can reach SQS>=5 via PM volume + gap alone (float always scores 0 for B).
When SQS>=5, they were getting Tier A risk ($750) — same as micro-float Profile A. This was wrong.

**Fix:** `if profile == 'B' and risk > 250: risk = 250`

---

## Key Trade Changes

| Date | Symbol | V6.1 Risk | V6.1 P&L | V6.2 Risk | V6.2 P&L | Saved |
|------|--------|-----------|----------|-----------|----------|-------|
| 2025-11-11 | CRWG | $750 | -$1,572 | $250 | **-$262** | **+$1,310** |
| 2025-11-14 | IONZ | $750 | -$1,026 | $250 | **+$194** | **+$1,220** |

*IONZ flipped from loser to winner at the smaller position size — L2 gate worked properly at $250 risk.*

All other Profile B trades were already at $250 risk (SQS=4, Tier B) — no change.

---

## Impact Summary

| Metric | V6.1 | V6.2 | Change |
|--------|------|------|--------|
| Profile A P&L | +$7,885 | +$7,885 | **$0** (unchanged ✅) |
| Profile B P&L | -$2,460 | **~+$70** | **+$2,530** |
| **Combined P&L** | **+$5,425** | **~+$7,955** | **+$2,530** |
| Max Drawdown | -$5,355 (17.3%) | **~-$3,073 (~9.9%)** | **-$2,282 less** |

*Drawdown improvement: CRWG and IONZ drove the entire November -$5,355 hole.
With the cap, November drawdown shrinks from -$5,355 to ~-$3,073.*

---

## Profile B Full Trade List (V6.2)

| Date | Symbol | Profile | SQS | Risk | P&L | Notes |
|------|--------|---------|-----|------|-----|-------|
| 2025-10-06 | IONZ | B | 5 | $250 | $0 | Cap applied (was Tier A) |
| 2025-10-14 | CYN | B | 4 | $250 | +$263 | No change |
| 2025-10-15 | SOAR | B | 4 | $250 | $0 | No change |
| 2025-11-03 | SDST | B | 4 | $250 | $0 | No change |
| 2025-11-06 | CRWG | B | 4 | $250 | -$125 | No change |
| 2025-11-11 | CRWG | B | 5 | **$250** | **-$262** | Cap applied (was $750, -$1,572) |
| 2025-11-14 | IONZ | B | 5 | **$250** | **+$194** | Cap applied (was $750, -$1,026) |
| 2025-11-24 | OLOX | B | 4 | $250 | $0 | No change |
| 2025-12-12 | CRWG | B | 4 | $250 | $0 | No change |
| 2025-12-15 | CRWG | B | 4 | $250 | $0 | No change |
| 2026-01-29 | NAMM | B | 5 | **$250** | $0 | Cap applied (was Tier A) |
| 2026-02-02 | BATL | B | 4 | $250 | $0 | No change |
| 2026-02-05 | CRWG | B | 4 | $250 | $0 | No change |
| 2026-02-20 | CRWG | B | 4 | $250 | $0 | No change |
| 2026-02-20 | AGIG | B | 4 | $250 | $0 | No change |
| 2026-02-27 | CRWG | B | 5 | **$250** | $0 | Cap applied (was Tier A) |

**Profile B V6.2 Net: ~+$70** (was -$2,460)

---

## Validation
- ✅ Profile A numbers: **unchanged** at +$7,885
- ✅ CRWG cap confirmed in spot check: -$1,572 → -$262
- ✅ IONZ cap confirmed in spot check: -$1,026 → +$194
- ✅ Toggle works: WB_PROFILE_B_RISK_CAP=0 restores V6.1 behavior

---

*Report by Duffy — 2026-03-10*
