# CT (Post-Squeeze Continuation) Deep Dive Analysis

**Date:** 2026-03-30
**Author:** Cowork (Opus)
**Sources:** continuation_detector.py, simulate.py, DIRECTIVE_POST_SQUEEZE_CONTINUATION.md, ct_validation_results.md, ct_validation_v2.md, ct_regression_retest.md, definitive_ytd_sq_only.md, detailed_ytd_sq_mp_v2.md, 2026-03-30_morning_session_report.md, squeeze_detector.py signal logs

---

## The Thesis: SQ Works, But We're Leaving Money on the Table

The squeeze is printing money — 39/39 winners on sq_target_hit, +$263,939 YTD, 82% win rate. Don't touch it. The question is: **when the stock keeps running after our 2R exit, can we get back in safely?**

The answer, from the data: **yes, on specific stocks, the SQ detector itself is already seeing the continuation.** The SQ detector continues to PRIME and ARM at higher levels after we exit. The signal is there. We just aren't acting on it.

---

## Part 1: Which Stocks Actually Continue?

I analyzed all 23 active trading days in the 2026 YTD, focusing on SQ detector behavior after the first profitable exit. Here's what the data shows:

### Tier 1: Clear Continuation (SQ detector fires 3+ post-exit signals)

| Stock | Date | SQ P&L | Post-Exit Behavior | HOD After Exit | CT Opportunity |
|-------|------|--------|--------------------|----------------|----------------|
| **SHPH** | 01-20 | +$6,074 | 3 PRIMEs (193x, 139x, 8x vol), 4 ARMs → $4.74 | $25.11 (16:00) | **HUGE** — stock 10x'd from exit |
| **ROLR** | 01-14 | +$11,139 | 3 PRIMEs, 3 ARMs ($12.22, $17.80 levels) | $21.00+ | **HUGE** — multiple cascade levels |
| **AHMA** | 01-13 | +$9,807 | Escalating PRIMEs ($6.66→$10.13→$13.62) | $15.32 | **HIGH** — parabolic escalation |
| **ASTC** | 03-30 | +$1,209 | 3 PRIMEs ($4.47→$5.32), ARM at $5.60 | $6.48 | **HIGH** — today's live evidence |
| **EEIQ** | 03-26 | +$3,488 | 3 PRIMEs ($9.47→$11.10→$11.42), REJECTs below HOD $12.70 | $12.70 | **MEDIUM** — big move but choppy pullbacks |
| **RUBI** | 02-19 | +$7,737 | 5 PRIMEs (escalating), multiple REJECTs | $4.46 | **MEDIUM** — weakening momentum |

### Tier 2: Limited Continuation (1-2 post-exit signals, modest move)

| Stock | Date | SQ P&L | Post-Exit Behavior | CT Opportunity |
|-------|------|--------|--------------------|----------------|
| **BATL** | 01-26 | +$6,023 | 1 ARM at $6.02, PM PRIME at $6.45 | MEDIUM — fast cascade, little room |
| **SLGB** | 01-21 | +$4,474 | 3 PRIMEs at $3.98-$4.02, tight oscillation | LOW — stock stalled at $4.52 |
| **FLYE** | 02-06 | +$17,094 | 1 PRIME (66.9x vol), but 6 REJECTs | LOW — pullback too deep |

### Tier 3: No Continuation (SQ captured the full move)

| Stock | Date | SQ P&L | Post-Exit Behavior | CT Opportunity |
|-------|------|--------|--------------------|----------------|
| **NPT** | 02-03 | +$65,765 | 1 PRIME at $21.12, no pullback signals | NONE — captured $9→$21 in one trade |
| **CRE** | 03-06 | +$33,782 | 1 PRIME only, no subsequent signals | NONE — full move captured |
| **FIEE** | 02-03 | +$5,006 | 1 PRIME, no continuation | NONE — simple breakout |
| **INKT** | 03-10 | +$4,815 | No post-exit data | NONE — likely captured move |

### Key Finding

**6 of 23 active days (26%) had clear continuation opportunities.** Those 6 stocks represent the biggest moves of the year (SHPH, ROLR, AHMA are 3 of the top 5 P&L days). The stocks that continue are the ones that move the most — and those are exactly the ones where the 2R exit leaves the most money behind.

**Conservative CT uplift estimate:** If CT captured even 20-30% of the remaining range on just the Tier 1 stocks, that's roughly:

- SHPH: exit $2.75 → HOD $25.11 → even 20% of $22.36 range ≈ +$4,472 at 1000 shares
- ROLR: last exit $11.54 → HOD $21 → 20% of $9.46 ≈ +$1,892
- AHMA: last exit $13.66 → HOD $15.32 → smaller range, maybe +$500
- ASTC: exit $4.14 → HOD $6.48 → 30% of $2.34 ≈ +$700
- EEIQ: exit $9.45 → HOD $12.70 → 20% of $3.25 ≈ +$650

**Estimated incremental: +$8,000–$15,000 on 2026 YTD** from a strategy that fires on ~26% of active days.

---

## Part 2: What the Continuation Pattern Looks Like

Across all Tier 1 stocks, the continuation follows a consistent 4-phase pattern:

### Phase 1: SQ Exit (2R target hit)
The squeeze fires and the mechanical exit triggers. Stock is in a strong uptrend with confirmed volume.

### Phase 2: Pullback (1-5 bars)
The stock pulls back. This is the critical phase — the nature of the pullback tells you whether it's a healthy dip or a reversal.

**Healthy pullback signature (from SHPH, ROLR, AHMA, ASTC):**
- 1-3 red bars, not 5+
- Volume DECLINES on the pullback bars (sellers drying up)
- Price holds above a reference point (VWAP, 9 EMA, or the squeeze entry price)
- MACD stays positive or flat (hasn't crossed below zero)

**Dump signature (stocks that DON'T continue):**
- 3+ red bars with INCREASING volume
- Price slices through VWAP and 9 EMA
- MACD crosses negative
- New lows on each bar

### Phase 3: Consolidation (0-3 bars)
After the pullback, the stock consolidates in a tight range. This is where the green bar appears and sets the trigger level.

### Phase 4: Breakout
Price breaks the consolidation high. This is the CT entry point.

### Timing

| Stock | SQ Exit → CT PRIME Gap | Pullback Bars | Time to Re-Entry |
|-------|------------------------|---------------|-------------------|
| SHPH | ~1 min | 1-2 | 2-5 min |
| ROLR | ~2 min | 1-3 | 3-8 min |
| AHMA | ~3 min | 2-4 | 5-15 min |
| ASTC | ~6 min | 2-3 | 6-12 min |
| EEIQ | ~57 min | 8+ (choppy) | 57 min |

**Pattern: The best CT setups happen FAST (2-15 minutes after SQ exit).** EEIQ is the outlier — its continuation took almost an hour because the pullback was severe ($9.45→$7.82). The CT detector correctly rejected all the dangerous early pullbacks on EEIQ and waited for recovery above VWAP/EMA before arming.

---

## Part 3: What's Wrong with CT Right Now

### Problem 1: Regression Interference (BLOCKING)

CT currently degrades VERO by -$150 and ROLR by -$303, even when CT fires ZERO trades on those stocks. The mere presence of CT changes the sim output.

**Root cause analysis:** The deferred activation pattern (commit 43e7585) helped but didn't eliminate the problem. On cascading stocks:

1. SQ trade closes → `notify_squeeze_closed()` stages CT pending activation
2. SQ resets to IDLE momentarily between cascade legs
3. `check_pending_activation()` fires during that brief IDLE window
4. CT enters COOLDOWN, starts counting bars
5. CT's `on_bar_close_1m()` runs during SQ IDLE gaps, updating CT's internal EMA/MACD state
6. This doesn't change any SQ state directly, but `on_bar_close_1m()` returns status messages that affect the verbose logging path, and the mere execution of CT's code during bar processing introduces subtle timing differences

**The fix:** CT must be completely inert during SQ cascades. Not just "deferred activation" — zero code execution. The simplest approach:

```python
# Option A: Time-based lockout (recommended by CT validation v2)
# CT locks for N minutes after ANY SQ trade close, not just
# until SQ._state == IDLE (which bounces between cascades)
_ct_lockout_until = None

def on_sq_trade_close(timestamp):
    _ct_lockout_until = timestamp + timedelta(minutes=10)

# CT gate:
if now < _ct_lockout_until:
    return  # Zero CT processing — not even EMA/MACD updates

# Option B: Trade count gate
# CT only activates after the Nth SQ trade on this symbol,
# meaning the cascade has played out
_sq_trade_count = 0

def on_sq_trade_close():
    _sq_trade_count += 1

# CT gate:
if _sq_trade_count < 3:  # Wait for at least 3 SQ trades to fire
    return  # SQ cascade still active
```

**Option A is simpler and more robust.** The 10-minute lockout ensures CT never touches a cascading stock during the cascade phase. If the stock is still running after 10 minutes of no SQ trades, THEN CT can start watching.

### Problem 2: Volume Gate Was Misconfigured (FIXED)

The original directive specified `min_vol_decay=0.50` (pullback volume must be < 50% of squeeze volume). This was too strict — EEIQ's pullbacks were all above 50% because the sell-offs were almost as active as the buy-ups. CC fixed this to 1.50 in the regression retest (commit 82c0bbf) and confirmed the .env override was the root cause.

**Current setting:** `WB_CT_MIN_VOL_DECAY=1.50` — pullback volume can be up to 1.5x squeeze volume. This is much more permissive and correctly passed EEIQ's pullbacks.

**Recommendation:** This seems about right. The goal of the volume gate is to catch dumps (high-volume sell-offs), not to require perfect silence. A 1.5x threshold lets through healthy pullbacks while still blocking panic selling.

### Problem 3: Gate Ordering Creates False Rejects

In the current code, the gates fire in this order:
1. Volume decay check
2. VWAP check
3. EMA check
4. MACD check

When any gate fires, CT resets to WATCHING and starts fresh. This means a pullback that temporarily dips below VWAP (gate 2) but recovers above it on the next bar gets completely thrown away — the pullback bars are reset and CT starts from scratch.

**The EEIQ signal log proves this is a problem:** CT rejected multiple pullbacks during the 10:08-10:50 sell-off (correctly), but then also rejected the 10:50-11:00 recovery pullbacks because each new attempt was measured from scratch (no memory of the prior valid pullback structure).

**Recommendation:** Instead of hard-resetting on gate failure, CT should "pause" and re-check gates on the next bar. Only hard-reset on truly disqualifying conditions (retrace > 50%, pullback > 5 bars, MACD negative).

### Problem 4: CT Doesn't Know About the SQ Cascade Pattern

CT treats every post-squeeze situation identically. But the data shows two very different scenarios:

**Scenario A: Cascade stocks (VERO, ROLR, BATL)**
- SQ fires 3-5 trades in rapid succession at escalating levels
- Each SQ trade captures a leg of the move
- CT would interfere with the cascade if it activated too early
- CT is only useful AFTER the cascade exhausts (SQ stops arming)

**Scenario B: Single-squeeze-then-continue stocks (EEIQ, ASTC, SHPH)**
- SQ fires 1-2 trades, then goes IDLE and stays IDLE
- The stock continues running but SQ doesn't re-arm (maybe because volume drops below the PRIME threshold, or because HOD gate blocks it)
- CT is valuable here because SQ has given up but the stock hasn't

**CT should differentiate between these scenarios.** The simplest signal: how many SQ trades have fired. If SQ has fired 3+ trades → it's a cascade → let SQ handle it. If SQ has fired 1-2 trades and then goes IDLE for 5+ minutes → it's a single-squeeze-then-continue → CT should activate.

---

## Part 4: What the SQ Detector Already Sees

This is the crucial insight: **the SQ detector is already seeing the continuation.** After the initial exit, the SQ detector continues to:

- PRIME on new volume spikes (SHPH 193.8x, ROLR 280x)
- ARM at new levels ($12.22, $17.80 on ROLR)
- REJECT only because of `not_new_hod` (bar_high < session HOD)

The `not_new_hod` rejection is what kills SQ re-entries on continuation stocks. After the initial squeeze establishes a HOD, the stock pulls back, and the next volume spike doesn't make a new HOD — so SQ rejects it. But this is EXACTLY the pullback pattern CT is designed to catch.

**CT doesn't need its own detection logic for identifying volume spikes or momentum.** The SQ detector is already doing that work. CT just needs to:

1. Notice when SQ is PRIMING but REJECTING (stock has volume + momentum but can't break HOD)
2. Track the pullback between the HOD and the current price
3. Arm when the pullback holds support and price breaks back above the local consolidation high

This suggests a simpler architecture than what's currently built.

---

## Part 5: Recommendations for the Directive

### Recommendation 1: Fix the Regression First (P0)

Implement the time-based lockout for CT during SQ cascades:

```
WB_CT_CASCADE_LOCKOUT_MIN=10   # Minutes after last SQ trade close before CT can activate
```

CT does ZERO processing (no EMA updates, no MACD updates, no bar counting) until the lockout expires AND SQ is IDLE. The lockout timer resets on every SQ trade close, so on cascading stocks it keeps pushing forward.

**Test:** VERO and ROLR must show $0 delta with CT enabled. Since the lockout would be 10 minutes and VERO/ROLR cascade within minutes, CT would never activate on these stocks.

### Recommendation 2: Add SQ Trade Count Awareness

```
WB_CT_MIN_SQ_TRADES=1   # Minimum SQ trades before CT unlocks
```

CT only activates after at least N SQ trades have fired on this symbol this session. Default 1 (activate after any winning SQ trade). Could be raised to 2 for more conservative behavior.

Combined with the lockout, this means: "SQ fired at least 1 winning trade, AND it's been 10 minutes since the last SQ trade closed, AND SQ is IDLE" → CT starts watching.

### Recommendation 3: Leverage SQ Detector State for Pullback Identification

Instead of CT building its own pullback detection from scratch, CT should read from the SQ detector:

- `sq_det.bars_1m` — the rolling 50-bar window of 1m bars (volume, OHLC)
- `sq_det._session_hod` — the HOD to measure retracement against
- `sq_det._avg_prior_vol()` — the baseline volume for decay comparison

This eliminates the need for CT to track its own squeeze context (`_squeeze_entry`, `_squeeze_exit`, `_squeeze_high`, `_squeeze_vol`). CT reads it directly from the SQ detector state, which is always current.

### Recommendation 4: Softer Gate Failure (Pause, Don't Reset)

Change the gate failure behavior:

| Gate | Current: Reset to WATCHING | Proposed: Behavior |
|------|---------------------------|-------------------|
| Volume too high | Hard reset, lose pullback | **Pause** — re-check on next bar, keep pullback bars |
| Below VWAP | Hard reset | **Pause** — VWAP can be regained on next bar |
| Below 9 EMA | Hard reset | **Pause** — EMA can be regained |
| MACD negative | Hard reset | **Hard reset** — MACD negative is a real dump signal |
| Retrace > 50% | Hard reset | **Hard reset** — pullback too deep, thesis dead |
| Pullback > 5 bars | Hard reset | **Hard reset** — taking too long, momentum lost |

Only MACD negative, retrace too deep, and pullback too long should hard-reset. Volume, VWAP, and EMA should be "soft gates" that CT re-checks each bar without losing the pullback context.

### Recommendation 5: Wider Trail on CT Trades

CT trades should use the same SQ exit system but with a modified target. The 2R mechanical exit is perfect for the initial squeeze (short-duration breakout), but CT is entering a stock that has already proven it runs. CT should hold longer:

```
WB_CT_TARGET_R=3.0       # CT target = 3R instead of SQ's 2R
WB_CT_TRAIL_WIDER=1       # CT uses wider trailing stop (2x SQ trail width)
```

This is consistent with Ross's behavior — he sizes up on continuations and holds for bigger moves because the stock has already proven itself.

### Recommendation 6: Maximum 2 CT Entries Per Symbol (Keep This)

The current `WB_CT_MAX_REENTRIES=2` is correct. Ross's "three strikes" rule translates to: 1 SQ trade + 2 CT trades = 3 total. After 3 entries on the same stock, walk away.

---

## Part 6: Validation Test Plan

### Regression Suite (MUST ALL PASS AT $0 DELTA)

| Test | Stock | Date | Expected CT Trades | Expected Delta |
|------|-------|------|--------------------|----------------|
| 1 | VERO | 2026-01-16 | 0 (cascade lockout) | $0 |
| 2 | ROLR | 2026-01-14 | 0 (cascade lockout) | $0 |
| 3 | CRE | 2026-03-06 | 0 (no pullback pattern) | $0 |
| 4 | NPT | 2026-02-03 | 0 (captured full move) | $0 |

### Value-Add Suite (CT MUST ADD P&L)

| Test | Stock | Date | Expected Behavior |
|------|-------|------|-------------------|
| 5 | EEIQ | 2026-03-26 | CT fires 1-2 entries after 10:05, adds > $0 |
| 6 | ASTC | 2026-03-30 | CT fires 1-2 entries after $4.14 exit, captures $4.14→$5+ leg |
| 7 | SHPH | 2026-01-20 | CT fires after $2.75 exit, captures some of $2.75→$25 move |

### YTD A/B Test

| Config A (Control) | Config B (Test) |
|-------------------|-----------------|
| SQ-only (current) | SQ + CT (new) |
| WB_CT_ENABLED=0 | WB_CT_ENABLED=1 |
| Baseline: +$266,258 | Must exceed: +$266,258 |

**Success criteria:** Config B > Config A AND zero regression on any individual stock that had $0 CT trades.

---

## Part 7: What We're NOT Doing

1. **NOT touching the squeeze exit system.** sq_target_hit at 2R is 39/39 winners. Don't touch it.
2. **NOT making CT standalone.** CT ONLY fires after a profitable SQ trade on the same symbol.
3. **NOT using CT on cascading stocks.** The 10-minute lockout ensures VERO/ROLR/BATL patterns are handled purely by SQ's cascade mechanism.
4. **NOT adding new indicators.** CT uses the same EMA, MACD, VWAP that SQ already tracks. No Fibonacci, no order flow, no new complexity.
5. **NOT changing position sizing logic.** CT uses probe (50%) on first re-entry, full (100%) on second. This matches the current code and Ross's cushion behavior.

---

## Summary: The Path to a Working CT

| Step | Action | Blocks |
|------|--------|--------|
| 1 | Implement 10-minute cascade lockout | Regression fix (P0) |
| 2 | Add SQ trade count awareness | Scenario differentiation |
| 3 | Soften gate failures (pause vs reset) | EEIQ false rejects |
| 4 | Leverage SQ detector state directly | Simpler, more accurate context |
| 5 | Add wider CT target (3R vs 2R) | Better capture on proven runners |
| 6 | Run regression suite → $0 delta on VERO/ROLR | Deployment gate |
| 7 | Run value-add suite → EEIQ, ASTC, SHPH show incremental P&L | Validation |
| 8 | Run YTD A/B → SQ+CT > SQ-only | Final proof |

**The bottom line:** The SQ detector is already seeing the continuation. CT just needs to act on what SQ sees but can't trade (because of the HOD gate). Fix the regression interference, soften the gate failures, and CT will catch the $4.14→$6.48 ASTC leg and the $2.75→$25 SHPH leg that we're currently leaving on the table.
