# Profile C Validation Results

**Date**: March 3, 2026
**Config**: profiles/C.json — Fast Mode ON, min_bars=10, L2 OFF, max_entries=3
**Scope**: 32 zero-trade micro-float candidates + 6 Profile A regression stocks

---

## Verdict: NOT VALIDATED ❌

Profile C fails both success criteria:

1. **Fast Mode found 0 new trades** on 29 zero-trade stocks (needed ≥10 of 31)
2. **Profile C breaks VERO** by -$8,713 — far exceeds the $2K deterioration threshold

Profile C is NOT ready for live deployment. Config is preserved as a placeholder for future work.

---

## Phase 1: Zero-Trade Candidate Results

| Symbol | Date | Float | Prof A | Prof C | Delta | Status |
|--------|------|-------|--------|--------|-------|--------|
| HIND | 2026-01-16 | 1.5M | 0 trades | 0 trades | — | 0→0 |
| HIND | 2026-01-27 | 1.5M | +$260 (2tr) | +$260 (2tr) | $0 | Identical |
| HIND | 2026-02-05 | 1.5M | 0 trades | 0 trades | — | 0→0 |
| GRI | 2026-01-27 | 1.4M | 0 trades | 0 trades | — | 0→0 |
| GRI | 2026-01-28 | 1.4M | 0 trades | 0 trades | — | 0→0 |
| ELAB | 2026-01-06 | 0.2M | -$169 (1tr) | -$169 (1tr) | $0 | Identical |
| ELAB | 2026-01-08 | 0.2M | 0 trades | 0 trades | — | 0→0 |
| ELAB | 2026-01-09 | 0.2M | -$815 (1tr) | -$815 (1tr) | $0 | Identical |
| ACON | 2026-01-06 | 0.7M | 0 trades | 0 trades | — | 0→0 |
| ACON | 2026-01-27 | 0.7M | 0 trades | 0 trades | — | 0→0 |
| APVO | 2026-02-05 | 0.9M | 0 trades | 0 trades | — | 0→0 |
| BCTX | 2026-01-16 | 1.7M | 0 trades | 0 trades | — | 0→0 |
| FEED | 2026-01-16 | 0.8M | 0 trades | 0 trades | — | 0→0 |
| GWAV | 2026-01-06 | 0.8M | 0 trades | 0 trades | — | 0→0 |
| GWAV | 2026-02-05 | 0.8M | 0 trades | 0 trades | — | 0→0 |
| GWAV | 2026-02-13 | 0.8M | 0 trades | 0 trades | — | 0→0 |
| MLEC | 2026-01-06 | 0.7M | 0 trades | 0 trades | — | 0→0 |
| MLEC | 2026-01-28 | 0.7M | 0 trades | 0 trades | — | 0→0 |
| PAVM | 2026-01-16 | 0.7M | 0 trades | 0 trades | — | 0→0 |
| PAVM | 2026-02-05 | 0.7M | 0 trades | 0 trades | — | 0→0 |
| ROLR | 2026-02-13 | 3.6M | 0 trades | 0 trades | — | 0→0 |
| RVSN | 2026-01-27 | 1.8M | 0 trades | 0 trades | — | 0→0 |
| RVSN | 2026-02-05 | 1.8M | 0 trades | 0 trades | — | 0→0 |
| SLE | 2026-01-27 | 0.7M | 0 trades | 0 trades | — | 0→0 |
| SMX | 2026-02-09 | 0.0M | 0 trades | 0 trades | — | 0→0 |
| SNSE | 2026-01-28 | 0.7M | 0 trades | 0 trades | — | 0→0 |
| SNSE | 2026-02-05 | 0.7M | 0 trades | 0 trades | — | 0→0 |
| SXTP | 2026-01-28 | 0.9M | 0 trades | 0 trades | — | 0→0 |
| TNMG | 2026-01-06 | 1.2M | 0 trades | 0 trades | — | 0→0 |
| TWG | 2026-01-20 | 0.5M | 0 trades | 0 trades | — | 0→0 |
| VERO | 2026-01-06 | 1.6M | 0 trades | 0 trades | — | 0→0 |
| VERO | 2026-02-05 | 1.6M | 0 trades | 0 trades | — | 0→0 |

**Summary: 0 new trades found by Fast Mode across all 32 stocks.**

3 stocks (ELAB 01-06, ELAB 01-09, HIND 01-27) showed identical results to Profile A — Fast Mode neither helped nor hurt where the standard detector already had entries.

---

## Phase 2: Profile A Regression Check

| Symbol | Date | Profile A (Expected) | Profile A (Actual) | Profile C | Delta | Status |
|--------|------|---------------------|-------------------|-----------|-------|--------|
| VERO | 2026-01-16 | +$6,890 | +$6,890 ✓ | **-$1,823** | **-$8,713** | ❌ FAIL |
| GWAV | 2026-01-16 | +$6,735 | +$6,735 ✓ | +$6,735 | $0 | ✅ OK |
| APVO | 2026-01-09 | +$7,622 | +$7,622 ✓ | +$7,622 | $0 | ✅ OK |
| BNAI | 2026-01-28 | +$5,610 | +$5,610 ✓ | +$3,985 | -$1,625 | ⚠️ WATCH |
| MOVE | 2026-01-27 | +$5,502 | +$5,502 ✓ | +$5,502 | $0 | ✅ OK |
| ANPA | 2026-01-09 | +$2,088 | +$2,088 ✓ | +$2,088 | $0 | ✅ OK |

**VERO fails badly.** Profile C takes 4 trades on VERO (vs Profile A's cleaner cascading sequence) because Fast Mode fires at 07:02 — the very first bar of the premarket session — at $3.52 with a tiny $0.17 R. These premature early entries at $3.52 and $3.61 are well below VERO's true setup level and consume the max_entries budget before the real move develops.

---

## Root Cause Analysis

### Why Fast Mode fails on zero-trade stocks

The zero-trade stocks (GWAV, MLEC, PAVM, GRI, etc.) are zero-trade because **there was no tradeable setup** on those dates — not because the standard entry timing was slightly off. Fast Mode can enter earlier in a setup, but it cannot manufacture a setup where none exists. If price didn't create the impulse-pullback-ARM pattern, Fast Mode also gets nothing.

These stocks were likely dormant on those dates (perhaps the catalyst was thin, or the gap didn't hold), and the bot correctly avoided them. No amount of early entry timing changes that.

### Why Fast Mode breaks VERO

VERO 2026-01-16 is a cascading runner that starts with small early moves at $3.50 before the real breakout at $5.50-$7.00. Fast Mode sees the early 07:02 ARM (score=12.0, 5882 shares) as a valid entry and fires immediately. This:
1. Consumes 1-2 entry slots on $3.52-$3.61 trades before the real move
2. Disrupts the bot's LevelMap resistance tracking (records failed attempts at early levels)
3. With max_entries=3, only 1 slot remains for the $5.89 entry that Profile A would have prioritized

With Databento ticks, Profile C/VERO improves to -$62 (vs -$1,823 Alpaca) — the early entries may hit differently with Databento's finer tick resolution. But it's still a regression vs Profile A's +$6,735 (Databento).

### Why Round 6.5 HIND result is not reproducible

Round 6.5 showed HIND: Standard -$3 → Fast Mode +$663 (with Databento). We confirmed HIND 2026-01-27 Profile A (Databento) = -$3, which matches the Round 6.5 "standard" baseline. But Profile C (Databento) on the same date also gives -$3. The Round 6.5 +$663 is not reproducible.

Likely explanation: Round 6.5 used a different version of the Fast Mode code (early development), or a different set of Fast Mode parameters (min_bars, entry buffer, stop mult) that were subsequently changed. The archived round config likely differed from what's in profiles/C.json today.

---

## Success Criteria Assessment

| Criterion | Target | Result |
|-----------|--------|--------|
| Fast Mode captures ≥10 of 31 zero-trade stocks | ≥10 new trades | 0 new trades ❌ |
| Net P&L from new trades is positive | Any positive | $0 (no trades to measure) ❌ |
| Profile A regressions not damaged >$2K | All ≤$2K loss | VERO -$8,713 ❌ |

**All three criteria fail.**

---

## What Profile C Would Need (Future Work)

Profile C is NOT rejected — the concept of a fast-mover profile is valid. But the current implementation needs:

1. **A mechanism to identify true fast movers pre-session**: Gap %, volume premarket, number of pre-market bars. Stocks that have been gapping all premarket without pullback may be Profile C candidates.

2. **A setup filter that prevents Profile C from firing on cascading setup stocks**: VERO, BNAI, GWAV 2026-01-16 — these are cascading stocks that need the full pullback cycle. Profile C should not fire when a proper impulse-pullback-ARM is still developing (it should only fire when fast anticipation entry is the only viable path).

3. **Re-investigation of the Round 6.5 HIND result**: The archived config that produced +$663 needs to be recovered to understand what parameter set made Fast Mode work on HIND.

4. **Possible live-only feature**: Fast Mode may require live tick data precision that neither Alpaca nor Databento historical data replicates well. The actual trigger may depend on microsecond tick timing that backtesting can't capture.

---

## Current Status

| Profile | Status | Regression Benchmarks |
|---------|--------|----------------------|
| A (Micro-Float Pre-Market) | ✅ VALIDATED | VERO, GWAV, APVO, BNAI, MOVE, ANPA |
| B (Mid-Float L2-Assisted) | ✅ VALIDATED | ANPA 2026-01-09 → +$5,091 |
| C (Fast Mover) | ❌ NOT VALIDATED — do not deploy | — |
| X (Unknown/Conservative) | ✅ Placeholder ready | — |

**Action**: Tag micro-float pre-market stocks as `:A` until Profile C is reworked. Do not use `:C` in live trading.

---

*Report generated: March 3, 2026*
*Config commit: 1ac601e (Profile B Validation)*
