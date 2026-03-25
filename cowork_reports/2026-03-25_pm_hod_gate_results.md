# PM HOD Gate Test Results

**Generated:** 2026-03-25
**Author:** CC (Sonnet) executing Cowork (Opus) directive
**Feature:** `WB_SQ_PM_HOD_GATE` — use premarket_high (fixed) instead of session_hod (seed-dependent) for squeeze IDLE->PRIMED gate

---

## 1. Baseline Regression (Gate OFF)

| Stock | Expected | Actual | Pass? |
|-------|----------|--------|-------|
| VERO 2026-01-16 | +$18,583 (T1) | +$18,583 (T1) | YES |
| ROLR 2026-01-14 | +$6,444 (T3) | +$6,444 (T3) | YES |

Both regression targets hit exactly. Gate OFF (default) does not alter existing behavior.

---

## 2. Gate ON Regression

| Stock | Gate OFF | Gate ON | Delta |
|-------|----------|---------|-------|
| VERO 2026-01-16 | +$20,922 (4T) | +$20,922 (4T) | $0 (identical) |
| ROLR 2026-01-14 | +$16,195 (3T) | +$16,195 (3T) | $0 (identical) |

**Result:** Gate ON produces identical results to gate OFF for both regression stocks. The premarket_high and session_hod thresholds are the same for these stocks.

---

## 3. CJMB Discovery-Time Invariance Test (THE KEY TEST)

### Results Matrix

| Config | sim_start=09:00 | sim_start=08:45 | Delta |
|--------|-----------------|-----------------|-------|
| Gate OFF | +$964 (1T) | +$5,846 (4T) | -$4,882 |
| Gate ON | +$964 (1T) | +$5,846 (4T) | -$4,882 |

**Result:** Gate ON produces IDENTICAL results to gate OFF for CJMB at both sim_starts.

### Why the Gate Has No Effect on CJMB

The verbose traces reveal the root cause:

**Gate OFF (08:45 start) — rejection messages:**
```
[09:32] SQ_REJECT: not_new_hod (bar_high=$3.4100 < HOD=$4.6400)
[09:38] SQ_REJECT: not_new_hod (bar_high=$3.8199 < HOD=$4.6400)
[09:43] SQ_REJECT: not_new_hod (bar_high=$4.2099 < HOD=$4.6400)
```

**Gate ON (08:45 start) — rejection messages:**
```
[09:32] SQ_REJECT: not_above_pm_high (bar_high=$3.4100 < PM_HIGH=$4.6400)
[09:38] SQ_REJECT: not_above_pm_high (bar_high=$3.8199 < PM_HIGH=$4.6400)
[09:43] SQ_REJECT: not_above_pm_high (bar_high=$4.2099 < PM_HIGH=$4.6400)
```

The threshold is **$4.6400 in both cases**. CJMB's premarket_high equals the session_hod built from seed bars. Switching the gate source changes nothing because both values are identical.

### The Real Source of Discovery-Time Sensitivity

The +$4,882 difference between 08:45 and 09:00 starts is NOT caused by the HOD gate. It's caused by the 09:00 start simply missing the 08:45-08:49 price action where 3 trades fired:

```
08:45 start catches:
  T1: 08:46 $2.04 → $2.11  sq_para_trail_exit  +$250
  T2: 08:46 $2.32 → $3.00  bearish_engulfing    +$936
  T3: 08:49 $3.04 → $4.11  sq_target_hit        +$3,696
  T4: 11:27 $4.68 → $4.96  sq_target_hit        +$964

09:00 start catches:
  T1: 11:27 $4.68 → $4.96  sq_target_hit        +$964
```

The 09:00 start misses the entire first move because it hasn't started yet. This is a sim_start coverage problem, not a gate calibration problem.

---

## 4. Broader Jan Comparison

### Gate OFF (baseline): +$46,123
### Gate ON: +$46,123

**Result:** Identical across all 42 trading days (Jan 2025 + Jan 2026). Every single day, trade count, and P&L matches perfectly.

The PM HOD gate has ZERO measurable impact across the entire Jan comparison dataset.

---

## 5. Recommendation

### Should we enable WB_SQ_PM_HOD_GATE=1 as the new default?

**No — not yet.** Here's why:

1. **No measurable impact:** Across all tested stocks (VERO, ROLR, CJMB, and the full Jan comparison), gate ON produces identical results to gate OFF. The feature is harmless but also useless with current data.

2. **The thesis was wrong for CJMB:** The original hypothesis was that different seed bar counts set different session_hod values, causing the detector to fire differently. In reality, CJMB's premarket_high ($4.64) equals the session_hod from seed bars. The discovery-time sensitivity comes from missing early price action, not from gate threshold differences.

3. **The feature may still be valuable for OTHER stocks** where premarket_high != session_hod. This could happen when:
   - A stock gaps up significantly in the last minutes before the scanner discovers it
   - Seed bars from 4AM include a premarket spike that inflates session_hod
   - The scanner discovers a stock mid-session after a large move

4. **Keep it gated OFF.** It's not hurting anything, it's well-implemented, and it may prove useful once we find a stock where PM_HIGH != session_hod. The code is clean and ready to activate.

### What Actually Needs Fixing

The real discovery-time sensitivity issue for CJMB is that the scanner discovers it at 08:45 instead of earlier. The bot needs to see the 08:45-08:49 price action to catch the best trades. Solutions:
- **Earlier scanner discovery** (already improved in Scanner Fixes V1)
- **Intraday scanner checkpoints** (catches session runners)
- **Continuous scanning** (future enhancement)

The PM HOD gate is a solution to a problem that doesn't exist in our current data. Keep it in the codebase as insurance.
