# Phase 3: VWAP Override What-If Results

## Implementation

Added `WB_VWAP_OVERRIDE_MIN_SCORE` to `micro_pullback.py`:
- When an armed setup would be killed by VWAP loss, and its score meets the threshold, the setup is protected for up to 3 bars (`WB_VWAP_OVERRIDE_MAX_BARS=3`)
- If VWAP is regained within 3 bars, the setup survives
- If VWAP stays lost after 3 bars, the reset happens anyway
- Default: `0` (disabled, current behavior preserved)

---

## Results: All Three Thresholds Identical

All three thresholds (10.0, 11.0, 12.0) produce **identical results** because every blocked arm with score ≥ 10 also has score ≥ 12 (there are no 10.0-11.9 blocked arms that behave differently from the 12.0+ ones in terms of the grace period behavior).

### Per-Session P&L Changes vs Baseline

| Session | Baseline | With Override | Delta | Why |
|---------|----------|--------------|-------|-----|
| ROLR 2026-01-14 | +$1,644 | +$869 | **-$775** | Override preserved tighter stop → full stop-out |
| SHPH 2026-01-16 | -$1,111 | -$1,838 | **-$727** | Override created additional losing trade |
| All other sessions | unchanged | unchanged | $0 | Override fired but didn't change entries |

### Aggregate Impact

| Metric | Value |
|--------|-------|
| 28-session baseline P&L | +$26,564 |
| 28-session override P&L | +$25,062 |
| **Total delta** | **-$1,502** |
| Sessions improved | 0 |
| Sessions degraded | 2 |
| Sessions unchanged | 26 |

### Regression Check (ALL PASS at all thresholds)

| Regression | Baseline | Override | Status |
|-----------|----------|---------|--------|
| VERO 2026-01-16 | +$6,890 | +$6,890 | PASS |
| GWAV 2026-01-16 | +$6,735 | +$6,735 | PASS |
| APVO 2026-01-09 | +$7,622 | +$7,622 | PASS |
| BNAI 2026-01-28 | +$5,610 | +$5,610 | PASS |
| MOVE 2026-01-27 | +$5,502 | +$5,502 | PASS |
| ANPA 2026-01-09 | +$2,088 | +$2,088 | PASS |

---

## Root Cause Analysis: Why the Override Fails

### Case 1: JZXN (the motivating case) — NO HELP

The armed setup had trigger_high=$1.36. At the VWAP dip:
- 07:55: close=$1.25, VWAP=$1.25 → override bar 1/3
- 07:56: close=$1.20 → override bar 2/3
- 07:57: close=$1.17 → override bar 3/3
- 07:58: grace expired → reset

The stock was $0.11-$0.19 below the trigger price during the entire grace period. The trigger never had a chance to fire. The stock eventually ran to $1.57 but took **30+ minutes** to recover — far beyond any reasonable grace period.

**Lesson**: The override can't help when the VWAP dip is large relative to the R. The stock needs to not only recover above VWAP but also reach the trigger_high, which is typically above the pre-dip closing price.

### Case 2: ROLR — MADE THINGS WORSE

**Baseline**: Armed at 08:19 (entry=9.60, stop=8.25). VWAP killed it at 08:22. A new setup formed at 08:23 with **wider stop** (entry=9.31, stop=6.75, R=2.56). Entered at 9.33, exited via BE at 8.74 → **-$229**.

**Override**: The 08:19 setup survived the VWAP dip. Entered at 9.62 with the **original tighter stop** (8.25). Stop hit → **-$1,003**.

The override **prevented the natural stop-widening** that occurs when the detector resets and rebuilds. The post-dip rebuild creates a setup with a wider stop (using the dip's low), which is better suited to the stock's volatility.

### Case 3: SHPH — CREATED AN EXTRA LOSING TRADE

**Baseline**: No entry until 10:46 (one trade, -$1,111).

**Override**: The 10:08 armed setup survived the 10:09-10:11 VWAP dip. At 10:13, VWAP regained, trigger hit → entered at 1.71. Exited at 1.63 via topping wicky → **-$727**. Then the 10:46 trade still happened → -$1,111. **Total: -$1,838**.

The override allowed an entry on a stock that was churning around VWAP — exactly the scenario the VWAP gate is designed to prevent.

---

## Why Phase 2's Hypothetical Analysis Was Misleading

Phase 2 showed 67% of high-score blocked arms "recovered" within 30 minutes, suggesting the VWAP gate was too aggressive. But this analysis was flawed:

1. **It assumed entry at the arm price** — but in reality, the trigger_high is often far above the VWAP-dip price. The stock needs to recover fully AND trigger, not just recover.

2. **It didn't account for cascade effects** — preserving a setup through a VWAP dip changes the entire downstream trade sequence. The natural reset-and-rebuild creates setups with wider stops that better match post-dip volatility.

3. **"Recovered in 30 minutes" ≠ "would have been a good entry"** — even if the stock eventually went higher, a 3-bar grace period is too short to capture that recovery, and a longer grace would allow bad entries.

---

## Recommendation

### **DO NOT SHIP THE VWAP OVERRIDE.**

Per the decision framework:
> *Override makes things worse → Close study — VWAP gate is correct even on high scores*

The VWAP gate is working correctly. When it kills high-score armed setups, it's protecting against real momentum loss. The bot's strength is the **natural reset-and-rebuild cycle** — when a setup is killed, the detector rebuilds with parameters (stop, R) that better reflect current conditions.

### What about JZXN's missed $50k opportunity?

JZXN's missed trade is **not a VWAP gate problem** — it's a **re-entry speed problem**. The stock dropped $0.11 below trigger in one bar and didn't recover for 30+ minutes. No reasonable VWAP override would have caught this.

The real fix for JZXN-type scenarios would be:
1. **Faster re-arming after VWAP recovery** — when a stock loses and regains VWAP, allow a new ARM to form more quickly
2. **VWAP-recross signal** — a dedicated signal that fires when a stock recrosses VWAP with high volume, rather than waiting for the full impulse/pullback/confirmation cycle

These are separate features, not modifications to the VWAP gate.

### Code Cleanup

The `WB_VWAP_OVERRIDE_MIN_SCORE` code should be **removed** (or kept disabled with `default=0`). The VWAP_BLOCKED_ARM logging can be kept as it provides useful diagnostic information.

---

*Study completed: March 5, 2026*
*Result: VWAP override rejected — VWAP gate is correct for all score levels*
*Next investigation: VWAP-recross re-entry signal (if prioritized)*
