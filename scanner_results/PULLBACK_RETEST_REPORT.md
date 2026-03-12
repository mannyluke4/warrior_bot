# Pullback Mode Retest Report
**Date**: March 12, 2026
**Branch**: `v6-dynamic-sizing`
**Entry Mode**: `pullback` (3-bar impulse → pullback → trigger)
**Flags**: `--ticks --feed alpaca --no-fundamentals`
**Window**: 07:00–12:00 ET

---

## Run 1: Pullback Baseline (Gates OFF)

| Date | Symbols | Trades | Wins | Losses | Win Rate | P&L |
|------|---------|--------|------|--------|----------|-----|
| 2025-01-02 | AEI, RAIN, APM, BYAH, NEUP, PLRZ, COEP, CTEV | 0 | 0 | 0 | — | $0 |
| 2025-11-05 | WXM, BQ, NCEL, IPDN, VEEE, CYCU, NOTE, NPT | 0 | 0 | 0 | — | $0 |
| 2025-11-06 | EPSM, FLYT, GNPX, VEEE, CRCG, NHTC, NBIG, BMNG | 0 | 0 | 0 | — | $0 |
| 2026-01-06 | UUU, RKLZ, YDES, UXRP, NOMA, CYCN | 3 | 0 | 3 | 0% | -$1,281 |
| 2026-02-03 | ELAB, FATN, FIEE, SLGB, MTVA, AMCI, MIGI, CONX | 0 | 0 | 0 | — | $0 |
| **TOTAL** | **38 symbols** | **3** | **0** | **3** | **0%** | **-$1,281** |

### Baseline Trade Detail

| # | Symbol | Date | Time | Entry | Stop | R | Score | Exit | Reason | P&L | R-Mult |
|---|--------|------|------|-------|------|---|-------|------|--------|-----|--------|
| 1 | RKLZ | 2026-01-06 | 09:49 | $4.30 | $4.20 | $0.10 | 8.0 | $4.27 | bearish_engulfing_exit_full | -$323 | -0.3R |
| 2 | UXRP | 2026-01-06 | 07:02 | — | — | — | — | — | (2 trades, both losses) | -$958 | — |

### Baseline Armed-But-No-Trade Setups

| Symbol | Date | Armed At | Entry | Stop | R | Score | Why No Trade |
|--------|------|----------|-------|------|---|-------|--------------|
| APM | 2025-01-02 | 09:27 | $2.86 | $2.82 | $0.04 | 11.0 | Signal fired but no fill before structure reset |
| CYCU | 2025-11-05 | 08:03 | — | — | — | — | Armed, no trigger signal generated |
| EPSM | 2025-11-06 | 08:50 | — | — | — | — | Armed, no trigger signal generated |

---

## Run 2: Pullback with Gates ON

| Date | Trades (OFF) | Trades (ON) | Filtered | P&L (OFF) | P&L (ON) | Delta |
|------|-------------|-------------|----------|-----------|----------|-------|
| 2025-01-02 | 0 | 0 | 0 | $0 | $0 | $0 |
| 2025-11-05 | 0 | 0 | 0 | $0 | $0 | $0 |
| 2025-11-06 | 0 | 0 | 0 | $0 | $0 | $0 |
| 2026-01-06 | 3 | 0 | 3 | -$1,281 | $0 | +$1,281 |
| 2026-02-03 | 0 | 0 | 0 | $0 | $0 | $0 |
| **TOTAL** | **3** | **0** | **3** | **-$1,281** | **$0** | **+$1,281** |

---

## Gate Activity — Every Gate Check With Actual Numbers

### Setups that reached quality gate (8 total across all dates):

```
APM 09:27 (2025-01-02):
  G0=PASS (no_reentry: losses=0/1, trades=0/10)
  G1=PASS (clean_pullback: retrace=44%, vol_ratio=37%, candles=1)
  G2=PASS (impulse_strength: impulse=9.3%, vol=5.2x)
  G3=PASS (volume_dominance: vol_ratio=2.8x_recent_vs_avg)
  G4=REDUCE (price_float: price=$2.86 outside $3.00-$15.00 sweet spot → size_mult=0.5)
  → ARMED [QG_SIZE=50%] — signal fired, no fill before structure reset

BYAH 07:25 (2025-01-02):
  G0=PASS (no_reentry: losses=0/1, trades=0/10)
  G1=FAIL (clean_pullback: retrace=119% > max 65%)
  G2=FAIL (impulse_strength: impulse_vol=0.0x < min 1.5x)
  G3=WARN (fading_volume: 0.2x_recent_vs_avg)
  G4=PASS (price=$5.86)
  → BLOCKED by Gate 1 + Gate 2. Threshold adjustment: G1 needs ≥119%, G2 needs vol data.

CYCU 08:03 (2025-11-05):
  G0=PASS (no_reentry: losses=0/1, trades=0/10)
  G1=FAIL (clean_pullback: retrace=132% > max 65%)
  G2=PASS (impulse_strength: impulse=4.2%, vol=6.4x)
  G3=PASS (volume_dominance: vol_ratio=1.8x)
  G4=REDUCE (price=$2.78 outside sweet spot → size_mult=0.5)
  → BLOCKED by Gate 1. Threshold adjustment: needs retrace max ≥132% to pass.
  NOTE: Baseline also didn't trade this — armed but no trigger signal.

EPSM 08:50 (2025-11-06):
  G0=PASS (no_reentry: losses=0/1, trades=0/10)
  G1=SKIP (zero_impulse_range)
  G2=FAIL (impulse_strength: impulse=0.0% < min 2.0%)
  G3=WARN (fading_volume: 0.3x)
  G4=PASS (price=$10.95)
  → BLOCKED by Gate 2. Threshold adjustment: impulse=0.0% — not close, genuine garbage setup.
  NOTE: Baseline also didn't trade this.

GNPX 08:05 (2025-11-06):
  G0=PASS (no_reentry: losses=0/1, trades=0/10)
  G1=FAIL (clean_pullback: retrace=83% > max 65%)
  G2=FAIL (impulse_strength: impulse=1.9% < min 2.0%)
  G3=PASS (volume_dominance: vol_ratio=1.1x)
  G4=PASS (price=$6.45)
  → BLOCKED by Gate 1 + Gate 2. Threshold adjustment: G1 needs ≥83%, G2 needs ≥1.9%.
  NOTE: Baseline also didn't trade this (never armed with gates OFF).

UUU 08:08 (2026-01-06):
  G0=PASS (no_reentry: losses=0/1, trades=0/10)
  G1=SKIP (zero_impulse_range)
  G2=FAIL (impulse_strength: impulse=0.0% < min 2.0%)
  G3=WARN (fading_volume: 0.2x)
  G4=PASS (price=$6.38)
  → BLOCKED by Gate 2. Impulse=0.0% — garbage setup.
  NOTE: Baseline also didn't trade this.

RKLZ 09:48 (2026-01-06):
  G0=PASS (no_reentry: losses=0/1, trades=0/10)
  G1=FAIL (clean_pullback: retrace=74% > max 65%)
  G2=FAIL (impulse_strength: impulse=0.9% < min 2.0%)
  G3=PASS (volume_dominance: vol_ratio=1.2x)
  G4=PASS (price=$4.28)
  → BLOCKED by Gate 1 + Gate 2. Threshold adjustment: G1 needs ≥74%, G2 needs ≥0.9%.
  NOTE: Baseline traded this and LOST -$323. Gates correctly blocked a loser.

UXRP 07:02 (2026-01-06) — 1st setup:
  G0=PASS (no_reentry: losses=0/1, trades=0/10)
  G1=PASS (clean_pullback: retrace=50%, vol_ratio=36%, candles=1)
  G2=FAIL (impulse_strength: impulse=0.3% < min 2.0%)
  G3=PASS (volume_dominance: vol_ratio=1.3x)
  G4=PASS (price=$14.99)
  → BLOCKED by Gate 2. Impulse=0.3% (microscopic move, not a real impulse).
  NOTE: Baseline traded this and LOST. Gates correctly blocked a loser.

UXRP 10:25 (2026-01-06) — 2nd setup:
  G0=PASS (no_reentry: losses=0/1, trades=0/10)
  G1=FAIL (clean_pullback: retrace=1312% > max 65%)
  G2=FAIL (impulse_strength: impulse=0.0% < min 2.0%)
  G3=WARN (fading_volume: 0.4x)
  G4=REDUCE (price=$15.06 outside sweet spot → size_mult=0.5)
  → BLOCKED by Gate 1 + Gate 2. Complete garbage: 1312% retrace, 0% impulse.
```

---

## Gate Hit Rate Table

| Gate | Setups Checked | Passed | Failed | Skipped | Trades Blocked | Notes |
|------|---------------|--------|--------|---------|----------------|-------|
| G0: No Re-entry | 8 | 8 | 0 | 0 | 0 | Never triggers on first attempt |
| G1: Clean Pullback | 8 | 2 | 5 | 1 | 2 (RKLZ, UXRP) | Most common blocker (retrace > 65%) |
| G2: Impulse Strength | 8 | 2 | 6 | 0 | 3 (RKLZ, UXRP×2) | Catches fake impulses (0.0-1.9%) |
| G3: Volume Dominance | 8 | 5 | 0 | 0 | 0 | Warns only, never blocks alone |
| G4: Price/Float | 8 | 4 | 0 | 0 | 0 | Reduces size, never blocks |

**Key insight**: Gates 1 and 2 are the only gates that actually block. Gate 2 (impulse strength) is the primary filter — it caught 6 of 8 setups as having < 2.0% impulse, meaning most "impulses" detected by the state machine are noise, not real moves.

---

## Key Observations

### 1. The Bigger Problem: Pullback Mode Barely Trades At All

Across 38 symbols over 5 dates, only **6 setups armed** (gates OFF) and only **3 resulted in trades** — all losses. The issue isn't the quality gates; it's that the pullback detector is extremely selective by design:
- Most stocks don't form clean 3-bar impulse patterns
- Many setups reset due to: MACD bearish cross, trend failure, topping wicky, pullback too long, weak trigger candle
- Of the few that arm, many never get a trigger signal

### 2. Gates Correctly Blocked All 3 Losing Trades

The quality gates saved $1,281 by blocking:
- **RKLZ** (-$323): Gate 1 failed (retrace 74%), Gate 2 failed (impulse 0.9%). Tiny impulse, deep retrace — textbook bad setup.
- **UXRP** (-$958, 2 trades): Gate 2 failed both times (impulse 0.3% and 0.0%). Not real impulses at all.

### 3. APM Was the Only Setup That Passed All Gates

APM on 2025-01-02 had a legitimate setup:
- 9.3% impulse, 5.2x volume, 44% retrace, 1 pullback candle
- Score 11.0 with MACD 7.5, ABCD pattern, red-to-green
- BUT: price $2.86 triggered Gate 4 REDUCE (50% size)
- Signal fired but no fill before structure collapsed
- **This is the one setup we WANT to take** but it didn't execute

### 4. These 5 Dates May Be Poor Representatives

3 trades across 5 dates with 38 symbols is very thin data. The directive noted "Duffy mentioned 7 trades" — the 7 may have come from different stocks or dates. Consider expanding the test set to get more armed setups and a meaningful sample size.

### 5. Gate 2 (Impulse Strength) Is Doing the Heavy Lifting

6 of 8 setups failed Gate 2 with impulse < 2.0%. The 2.0% threshold seems well-calibrated — it's catching genuinely weak impulses (0.0%, 0.3%, 0.9%) while passing real ones (9.3%, 4.2%). No threshold adjustment recommended for Gate 2.

### 6. Gate 1 Threshold Could Be Explored

5 of 8 setups failed Gate 1 (retrace > 65%). Values ranged from 74% to 1312%. The legitimate setup (APM) had 44% retrace. A threshold of 75% would pass one more setup (RKLZ at 74%) but that setup was a $323 loser, so the current 65% threshold is protecting us.

---

## Recommendation

The quality gates are working correctly on this sample — they saved $1,281 by blocking 3 losers and only passed 1 legitimate setup (which didn't execute for unrelated reasons). However, the sample is too small to draw firm conclusions. The real question is: **why does pullback mode produce so few setups?** That's a detector tuning question, not a gate threshold question.

---

*Report generated by Claude Code — 2026-03-12*
*Directive: PULLBACK_MODE_RETEST_DIRECTIVE.md*
