# Phase 3: BE Suppression What-If Analysis

## Implementation

Added `WB_BE_SUPPRESS_MINUTES` env var to simulate.py. When set > 0, bearish engulfing exits are suppressed for the first N minutes after entry. Stop losses always fire. Default = 0 (disabled, current behavior).

---

## Baseline (WB_BE_SUPPRESS_MINUTES=0)

**27 Profile A sessions total P&L: $+25,748**

---

## Results by Suppression Window

### Per-Session Comparison

| # | Symbol | Date | Baseline | 3m | Delta | 5m | Delta | 10m | Delta |
|---|--------|------|----------|-----|-------|-----|-------|------|-------|
| 1 | ROLR | 2026-01-06 | -$1,422 | -$1,422 | $0 | -$1,422 | $0 | -$1,422 | $0 |
| 2 | ACON | 2026-01-08 | -$2,122 | -$2,158 | -$36 | -$2,158 | -$36 | -$2,158 | -$36 |
| 3 | APVO | 2026-01-09 | +$7,622 | +$7,622 | $0 | +$6,534 | -$1,088 | +$6,534 | -$1,088 |
| 4 | BDSX | 2026-01-12 | -$45 | -$1,863 | -$1,818 | -$1,762 | -$1,717 | -$1,568 | -$1,523 |
| 5 | PMAX | 2026-01-13 | -$1,098 | -$1,098 | $0 | -$1,098 | $0 | -$1,098 | $0 |
| 6 | ROLR | 2026-01-14 | +$1,644 | +$3,659 | +$2,015 | +$3,659 | +$2,015 | +$3,659 | +$2,015 |
| 7 | BNAI | 2026-01-16 | -$674 | -$965 | -$291 | +$308 | +$982 | +$308 | +$982 |
| 8 | GWAV | 2026-01-16 | +$6,735 | +$6,776 | +$41 | +$6,776 | +$41 | +$6,776 | +$41 |
| 9 | LCFY | 2026-01-16 | -$627 | -$742 | -$115 | -$742 | -$115 | -$742 | -$115 |
| 10 | ROLR | 2026-01-16 | -$1,228 | -$1,129 | +$99 | -$1,129 | +$99 | -$1,129 | +$99 |
| 11 | SHPH | 2026-01-16 | -$1,111 | -$1,111 | $0 | -$1,111 | $0 | -$1,111 | $0 |
| 12 | TNMG | 2026-01-16 | -$481 | -$692 | -$211 | -$1,000 | -$519 | -$1,000 | -$519 |
| 13 | **VERO** | **2026-01-16** | **+$6,890** | **-$1,823** | **-$8,713** | **-$2,294** | **-$9,184** | **+$5,823** | **-$1,067** |
| 14 | PAVM | 2026-01-21 | +$1,586 | +$936 | -$650 | +$936 | -$650 | +$936 | -$650 |
| 15 | MOVE | 2026-01-23 | -$156 | -$156 | $0 | -$999 | -$843 | -$999 | -$843 |
| 16 | SLE | 2026-01-23 | -$390 | -$390 | $0 | -$368 | +$22 | -$999 | -$609 |
| 17 | BCTX | 2026-01-27 | $0 | $0 | $0 | $0 | $0 | $0 | $0 |
| 18 | HIND | 2026-01-27 | +$260 | +$440 | +$180 | -$45 | -$305 | -$1,999 | -$2,259 |
| 19 | MOVE | 2026-01-27 | +$5,502 | +$5,868 | +$366 | +$5,868 | +$366 | +$5,868 | +$366 |
| 20 | SXTP | 2026-01-27 | -$2,078 | -$2,078 | $0 | -$2,078 | $0 | -$2,078 | $0 |
| 21 | BNAI | 2026-01-28 | +$5,610 | +$9,863 | +$4,253 | +$9,593 | +$3,983 | +$9,593 | +$3,983 |
| 22 | BNAI | 2026-02-05 | +$160 | +$1,652 | +$1,492 | -$841 | -$1,001 | -$129 | -$289 |
| 23 | MNTS | 2026-02-06 | +$862 | +$862 | $0 | +$862 | $0 | +$862 | $0 |
| 24 | ACON | 2026-02-13 | -$214 | -$214 | $0 | -$214 | $0 | -$214 | $0 |
| 25 | MLEC | 2026-02-13 | +$173 | +$235 | +$62 | +$206 | +$33 | +$580 | +$407 |
| 26 | SNSE | 2026-02-18 | -$125 | -$541 | -$416 | -$541 | -$416 | -$541 | -$416 |
| 27 | ENVB | 2026-02-19 | +$474 | +$795 | +$321 | -$77 | -$551 | -$654 | -$1,128 |

### Totals

| Metric | Baseline | 3m Suppress | 5m Suppress | 10m Suppress |
|--------|----------|-------------|-------------|--------------|
| **Total P&L** | **$+25,748** | **$+22,326** | **$+16,863** | **$+23,098** |
| **Net Impact** | — | **-$3,422** | **-$8,885** | **-$2,650** |
| Sessions improved | — | 9 | 8 | 7 |
| Sessions worsened | — | 8 | 12 | 12 |
| Sessions unchanged | — | 10 | 7 | 8 |

---

## Regression Benchmarks

| Stock | Date | Baseline | 3m | Status | 5m | Status | 10m | Status |
|-------|------|----------|-----|--------|-----|--------|------|--------|
| VERO | 2026-01-16 | +$6,890 | -$1,823 | FAIL | -$2,294 | FAIL | +$5,823 | FAIL |
| GWAV | 2026-01-16 | +$6,735 | +$6,776 | PASS | +$6,776 | PASS | +$6,776 | PASS |
| APVO | 2026-01-09 | +$7,622 | +$7,622 | PASS | +$6,534 | FAIL | +$6,534 | FAIL |
| BNAI | 2026-01-28 | +$5,610 | +$9,863 | PASS | +$9,593 | PASS | +$9,593 | PASS |
| MOVE | 2026-01-27 | +$5,502 | +$5,868 | PASS | +$5,868 | PASS | +$5,868 | PASS |
| ANPA | 2026-01-09 | +$2,088 | +$2,088 | PASS | +$2,088 | PASS | +$2,088 | PASS |

### Regression Summary

| Window | Regressions Passed | Regressions Failed |
|--------|-------------------|-------------------|
| 3m | 5/6 | VERO (-$8,713) |
| 5m | 4/6 | VERO (-$9,184), APVO (-$1,088) |
| 10m | 4/6 | VERO (-$1,067), APVO (-$1,088) |

**ALL three suppression windows FAIL the VERO regression.** This is the critical blocker.

---

## Why VERO Breaks

VERO 2026-01-16 is the perfect example of why BE suppression is counterproductive for cascading stocks:

**Baseline (no suppression):**
1. Trade 1: Entry 07:03 @ $3.52, BE exit @ $3.55 (0m held) → +$176
2. Trade 2: Entry 07:04 @ $3.61, BE exit @ $3.61 (1m held) → $0
3. **Trade 3: Entry 07:14 @ $3.60, TW exit @ $4.68 (3m held) → +$7,713** ← the big winner
4. Trade 4: Entry 07:30 @ $5.89, stop hit → -$1,000

The first two quick BE exits **freed capital** to re-enter at $3.60 (basically the same price). The third entry then caught the real move to $4.68 for +$7,713. This is the cascading re-entry edge working perfectly.

**With 3m suppression:**
- Trade 1 BE suppressed → holds through, likely stops out or exits at a worse level
- The cascading re-entry sequence is disrupted
- Result: -$1,823 (a $8,713 swing)

The bot's signal mode strategy is specifically designed to exit early on weak patterns and re-enter on fresh setups. Suppressing BE exits breaks this core mechanism.

---

## Notable Session-Level Impacts

### Biggest Winners from Suppression
- **BNAI 2026-01-28:** +$4,253 with 3m — suppressed a $121 BE exit and held to much higher exit
- **ROLR 2026-01-14:** +$2,015 with 3m — similar pattern, held through initial chop
- **BNAI 2026-02-05:** +$1,492 with 3m — held through first BE dip

### Biggest Losers from Suppression
- **VERO 2026-01-16:** -$8,713 with 3m — destroyed cascading re-entry edge
- **BDSX 2026-01-12:** -$1,818 with 3m — held through BE into bigger loss
- **PAVM 2026-01-21:** -$650 with 3m — held through chop instead of clean re-entry

---

## Key Insight: The Suppression Paradox

BE suppression helps on **some** stocks (BNAI 01-28, ROLR 01-14) where the first BE is genuinely premature. But it catastrophically hurts on **cascading** stocks (VERO) where quick exit + re-entry is the optimal strategy.

The problem is that these two stock types look identical at the moment of Trade 1. You can't tell at entry time whether the BE exit will be premature or part of a cascading opportunity. The current system handles both cases reasonably — the VERO-type cascading behavior produces +$6,890 via quick exits and re-entries, while the BNAI-type behavior still captures the big move via later entries.

---

## RECOMMENDATION: DO NOT SHIP BE SUPPRESSION

**Decision: Close study — current behavior is correct, JZXN was an outlier.**

### Evidence

1. **All three suppression windows reduce total P&L across 27 Profile A sessions:**
   - 3m: -$3,422 net impact
   - 5m: -$8,885 net impact
   - 10m: -$2,650 net impact

2. **All three windows FAIL the VERO regression** — the single most important benchmark:
   - 3m: $+6,890 → -$1,823 (FAIL, -$8,713)
   - 5m: $+6,890 → -$2,294 (FAIL, -$9,184)
   - 10m: $+6,890 → +$5,823 (FAIL, -$1,067)

3. **The "too early" BE exit is a feature, not a bug.** On cascading stocks like VERO, quick BE exits free capital for re-entry at the same or better levels. The cascading re-entry edge (the bot's primary strategy in signal mode) depends on these exits.

4. **Phase 2 showed BE Trade 1 exits are NOT systematically worse:** BE Trade 1s averaged +$784 and 38% win rate vs non-BE Trade 1s at -$25 and 18% win rate. The BE exit mechanism is working correctly.

5. **JZXN's outcome was driven by the VWAP gate blocking re-entry, not by the early BE exit.** The bot correctly exited and would have re-entered — but the re-entry setup's VWAP distance exceeded the gate. That's a separate issue (VWAP gate override for high-score re-entries) and should be studied independently.

### What To Investigate Instead

The real opportunity from the JZXN study is not suppressing BE exits but rather:
- **VWAP gate override for high-score re-entries** (score > 10): JZXN had a 12.5-score re-entry at 07:54 that was blocked by VWAP distance. If the VWAP gate had an override for very high scores, the bot would have re-entered and captured more of the move.
- This is a lower-risk change that doesn't interfere with the cascading exit mechanism.

### Code Status
- simulate.py has been **reverted** to its original state (no BE suppression code)
- All regressions pass at baseline values
- No code changes to ship
