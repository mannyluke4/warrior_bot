# Phase 2: VWAP-Blocked Arms Analysis

## Q1: How many arms were blocked by VWAP across all 28 sessions?

**Total: 15 blocked arms** across 10 sessions (36% of sessions had at least one blocked arm).

### Breakdown by score bucket:

| Score Bucket | Count | % of Total |
|-------------|-------|-----------|
| ≥ 12.0 | 6 | 40% |
| 10.0-11.9 | 3 | 20% |
| 8.0-9.9 | 0 | 0% |
| < 8.0 | 6 | 40% |

**Notable**: There are ZERO blocked arms in the 8-10 range. The distribution is bimodal — either very high conviction (≥10) or low conviction (<8). This makes the override decision cleaner.

---

## Q2: For high-score blocked arms (score ≥ 10), what happened after the block?

**9 blocked arms with score ≥ 10:**

| # | Symbol | Date | Score | Entry | Close@Block | %Below VWAP | Recovered? | Hyp P&L | Verdict |
|---|--------|------|-------|-------|-------------|-------------|-----------|---------|---------|
| 1 | JZXN | 03-04 | 12.5 | 1.36 | 1.25 | 0.3% | YES (30m) | +$1,909 | **VWAP WRONG** |
| 2 | PAVM | 01-21 | 12.5 | 15.00 | 12.65 | 0.7% | YES (5m) | +$352 | **VWAP WRONG** |
| 3 | PMAX | 01-13 | 12.5 | 3.45 | 2.01 | 22.4% | NO | -$21 | VWAP CORRECT |
| 4 | GWAV | 01-16 | 12.0 | 8.40 | 5.64 | 15.1% | NO | -$50 | VWAP CORRECT |
| 5 | ROLR | 01-14 | 12.0 | 9.60 | 6.68 | 8.7% | YES (5m) | +$8,413 | **VWAP WRONG** |
| 6 | SHPH | 01-16 | 12.0 | 1.69 | 1.63 | 1.9% | YES (5m) | +$1,002 | **VWAP WRONG** |
| 7 | SHPH | 01-16 | 11.5 | 1.69 | 1.66 | 0.1% | YES (5m) | +$1,375 | **VWAP WRONG** |
| 8 | PAVM | 01-21 | 10.5 | 13.15 | 12.31 | 3.3% | YES (5m) | +$3,564 | **VWAP WRONG** |
| 9 | BCTX | 01-27 | 10.0 | 4.82 | 4.66 | 0.6% | NO | -$412 | VWAP CORRECT |

### Summary:
- **6/9 (67%) were wrong blocks** — stock recovered and would have been profitable
- **3/9 (33%) were correct blocks** — stock didn't recover
- **Total hypothetical P&L if all 9 were overridden**: +$16,132
- **Correct blocks saved**: ~$483 in losses (PMAX -$21, GWAV -$50, BCTX -$412)
- **Net opportunity**: +$16,132 - $483 = **+$15,649** across all sessions

### Pattern in correct blocks:
- PMAX: 22.4% below VWAP — this is a crash, not a momentary dip
- GWAV: 15.1% below VWAP — also a crash
- BCTX: 0.6% below VWAP but only had 2 tags (no VOLUME_SURGE) — lower conviction

### Pattern in wrong blocks:
- Most had close within **0.1-3.3%** of VWAP (small dips)
- All had ABCD + RED_TO_GREEN tags
- 5/6 also had VOLUME_SURGE
- ROLR was 8.7% below but still recovered massively (halted and resumed)

---

## Q3: Is there a score threshold where VWAP blocks are consistently wrong?

### Score ≥ 10: 6/9 wrong blocks (67%)
- Hyp total if overridden: +$15,649 net
- Win rate on overrides: 67%

### Score ≥ 11: 6/8 wrong blocks (75%)
- Removes BCTX (score 10.0, lost -$412)
- Hyp total if overridden: +$16,061 net (removes -$412 loss + adds nothing)
- Win rate on overrides: 75%

### Score ≥ 12: 4/6 wrong blocks (67%)
- Removes BCTX and both PAVM 10.5
- Loses PAVM 10.5 (+$3,564) and SHPH 11.5 (+$1,375)
- Hyp total if overridden: +$11,605 net
- Win rate on overrides: 67%

### Clear breakpoint: **Score ≥ 11 is the sweet spot**
- Highest win rate (75%)
- Removes the one bad override (BCTX at 10.0)
- Keeps PAVM 10.5 (+$3,564) and SHPH 11.5 (+$1,375) which were both big winners
- Only 2 false positives: PMAX (22.4% below VWAP, genuine crash) and GWAV (15.1% below, genuine crash)

**Additional filter consideration**: Both PMAX and GWAV were >15% below VWAP at block time. If we add a secondary check (e.g., "only override if close is within 5% of VWAP"), we could eliminate both false positives and achieve 100% accuracy on score ≥ 11 blocks. But with only 8 samples, this may be overfitting.

---

## Q4: Do specific tag combinations correlate with VWAP blocks being wrong?

### Tag analysis for score ≥ 10 blocked arms:

| Tags Present | Count | Wrong Blocks | Win Rate |
|-------------|-------|-------------|----------|
| ABCD + VOL_SURGE + R2G | 7 | 5/7 | 71% |
| ABCD + R2G (no VOL_SURGE) | 2 | 1/2 | 50% |
| ABCD + VOL_SURGE + R2G + WHOLE | 3 | 2/3 | 67% |

### Key findings:
- **VOLUME_SURGE is the strongest indicator** that a VWAP block is wrong (71% vs 50% without it)
- **WHOLE_DOLLAR_NEARBY** doesn't add predictive value (67% vs 71% with VOL_SURGE alone)
- All wrong blocks had at least ABCD + RED_TO_GREEN
- **Tag count ≥ 3** (ABCD + VOL_SURGE + R2G minimum) correlates with 71% wrong-block rate
- **Tag count = 2** (ABCD + R2G only) has 50/50 odds — not reliable for override

### Tag-based filter potential:
A rule like "override if score ≥ 11 AND VOLUME_SURGE present" would capture 6 of the 7 winners while only including 2 losers (PMAX, GWAV — both deep VWAP crashes).

---

## Recommendation for Phase 3

Based on this analysis, test these three thresholds:
1. **WB_VWAP_OVERRIDE_MIN_SCORE = 10.0** — captures 9 blocked arms, 67% win rate
2. **WB_VWAP_OVERRIDE_MIN_SCORE = 11.0** — captures 8 blocked arms, 75% win rate (recommended)
3. **WB_VWAP_OVERRIDE_MIN_SCORE = 12.0** — captures 6 blocked arms, 67% win rate

The key risk is that overriding in PMAX and GWAV scenarios (deep VWAP loss) won't cause real damage because:
- The hypothetical losses from those overrides are small (-$21 and -$50)
- The stop loss would fire normally, limiting downside
- The potential upside from correct overrides (ROLR +$8,413, PAVM +$3,564) far outweighs
