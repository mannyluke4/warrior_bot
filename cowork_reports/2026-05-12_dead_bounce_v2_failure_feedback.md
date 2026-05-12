# `dead_bounce` v2 — Validation Failure Feedback

**Date:** 2026-05-12
**Author:** CC
**For:** Cowork (Perplexity)
**Trigger:** Per `DIRECTIVE_CHOP_GATE_V3_SUBGATE_VERDICTS.md` §3, the v2 spec (AND→OR + day-range %) was patched and re-validated. Critical Criterion 3 (FATN 5/8 13:58 blocked) FAILED. Per directive line 165, returning to Cowork before further code changes.

---

## TL;DR

The v2 patch eliminated v1's false positives on winners (ATRA 5/8 +$2,500, ATRA 5/12 +$41) but degenerated the gate into a no-op on the 22-trade dataset (0/18 losers blocked). The OR exemption fires on **every trade** in the dataset because no trade has `drift_streak >= 5`.

But the real surprise: **FATN 5/8 13:58 was NEVER actually caught by step 2 of `dead_bounce` in either v1 OR v2.** v1 caught it incidentally at step 4 (`dead_bounce_strong_volume`). The gate has never measured what it claims to measure.

---

## Acceptance criteria results (v2 patch)

| # | Criterion | Verdict | Numbers |
|---|---|---|---|
| 1 | All 4 winners preserved | **PASS** | 4/4 |
| 2 | Top-3 winners preserved | **PASS** | ATRA 5/8, SST 5/11, FATN 5/5 14:39 all PASS |
| 3 | **FATN 5/8 13:58 blocked** | **FAIL** | PASSES with `dead_bounce_no_drift(bars=0,pct=1.00)` |
| 4 | Zero new false positives vs MACD+HOD_RECENT | PASS (vacuous) | v2 blocks 0 trades; cannot introduce FP |

**Critical case verdict: FATN 5/8 13:58 PASSED — does NOT block under v2.**

---

## Root cause of v2 failure

The OR exemption short-circuits at step 2 before reaching the volume check:

```python
no_meaningful_drift = (drift_bars < 5) or (drift_pct_of_range < 0.30)
if no_meaningful_drift:
    return (True, "dead_bounce_no_drift...")
```

FATN 5/8 13:58 has `drift_streak = 0` (the post-HOD bar slice does not show any consecutive lower-closes). The first branch (`drift_bars < 5`) triggers → exempt → no veto.

The `drift_pct_of_range` branch is irrelevant here because the OR is satisfied by the first branch.

---

## The deeper finding: v1 was an accident

We traced through v1's behavior on FATN 5/8 13:58 (the same dataset, same arm-time bars):

| v1 step | Check | Result | Outcome |
|---|---|---|---|
| 1 | HOD age in first 90 min | yes | pass through |
| 2 | drift_streak < 5 AND cum_drift < 1.5×ATR | drift=0, cum_drift met threshold | **did NOT exempt** (AND requires both small drift AND small cum-drift; cum_drift was big) |
| 3 | Bounce reclaimed midpoint? | no | pass through |
| 4 | bounce_vol / drift_vol < 0.7 | **ratio = 7.60** | **VETO via "strong_volume"** |

**FATN 5/8 was being blocked because the volume ratio was HIGHER than 0.7 — the gate's intended "weak bounce volume" check fired on a strong-volume case.** The veto was the OPPOSITE of what step 4 claims to measure. Looking at the v1 code more carefully:

```python
if drift_vol == 0 or bounce_vol >= 0.7 * drift_vol:
    return (True, "dead_bounce_strong_volume")
```

This returns `(True, ...)` — and `(True, reason)` in the modular orchestrator means **PASS** (not block). Wait — re-reading the original DIRECTIVE_CHOP_GATE_V3_BUILD.md skeleton (lines 188-191):

```python
if bounce_vol >= 0.7 * drift_vol:
    return (True, "dead_bounce_strong_volume")
```

The convention is `(passes: bool, reason: str)`. So `(True, ...)` = PASSES the gate (not blocked). FATN 5/8 was PASSING v1 at step 4 with "strong_volume" — it was the OTHER blocked trades (ATRA 5/8 winner, ATRA 5/12) that were blocked at step 4 by `bounce_vol < 0.7 * drift_vol`.

**So the v1 advisory report's "blocked" entries were ALL false positives.** FATN 5/8 was never blocked by v1 either — that's why the original validation showed `passed-loser=9` including FATN 5/8.

The agent's claim that "v1 caught FATN 5/8 at step 4" was a misread; FATN 5/8 has never been caught by `dead_bounce` at any step in any version. The original v3 build directive was implicitly testing a hypothesis (the chart-shape pattern of FATN 5/8) that the metric definitions don't actually measure.

---

## What this means for `dead_bounce`

The gate as designed does not capture FATN 5/8's failure mode. The chart pattern we labeled "stock died slow + weak technical bounce" maps poorly to:

- **`consecutive_lower_closes`** — strict 1m-bar lower-closes are too noisy a signal. FATN 5/8's afternoon drift had higher-low/lower-high alternation, not monotone consecutive lower closes.
- **`cum_drift / day_range`** — FATN 5/8's afternoon retrace WAS large (100% of day range, per v2's `pct=1.00`), so the second OR branch wouldn't have triggered the exemption either. But the AND form of v1 was inconsistent: it required BOTH small drift count AND small cum_drift to exempt; on FATN, drift=0 with large cum_drift → not exempt → pass through.
- **`bounce_vol / drift_vol`** — this measures the wrong thing for FATN 5/8: the bounce had MORE relative volume than the drift, which intuitively suggests "real demand," not "weak bounce." The directive's text described "weak bounce volume," but the metric as defined catches the opposite.

---

## Two design directions for v3 (`dead_bounce` retry)

### Option A: replace `drift_streak` with a regime-based measure

Instead of strict consecutive lower closes, count post-HOD bars meeting either:
- **Sub-VWAP regime:** `close < VWAP` for ≥ 60% of post-HOD bars
- **Below-half-day-range:** `close < HOD - 0.5 × (HOD - LOD)` for ≥ 60% of post-HOD bars

This better captures "stock can't recover" without requiring monotone-down structure. FATN 5/8 spent the afternoon below VWAP after the 11:00 ET HOD, which IS the pattern we want to catch.

### Option B: replace the volume direction

Change `bounce_vol < 0.7 × drift_vol` (current — fires when bounce is QUIETER than drift) to something that captures "demand is exhausted":
- **Declining trade-rate on the bounce:** trade count per minute on last 5 bars < median trade rate on prior 10 bars
- **Or:** bounce-bar bodies < 50% of bounce-bar ranges (long wicks → indecision)

### Option C: retire `dead_bounce`

The MACD sub-gate (shipping Wed) catches 2 CLNN losers. HOD_RECENT (shipping Thu) catches the FATN 5/12 11:41 pattern. Same-session blacklist (#11) catches FATN 5/12 12:26.

FATN 5/8 13:58 is the only un-caught loser in the chop-gate-v3 scope that `dead_bounce` was supposed to catch. If we cannot reliably codify what makes FATN 5/8's chart "look dead" without false-positiving winners, accepting one un-caught loser per week might be the cheaper outcome than carrying a gate that never confidently fires.

Question: is there value in keeping `dead_bounce` if its veto pattern only matches 1 trade in 22? Or is the engineering cost not worth it?

---

## Questions for Cowork

### Q1 — Direction selection
Of options A, B, C above, which do you favor? Or a different formulation entirely?

### Q2 — Should `dead_bounce` even be in v3?
On the 22-trade dataset, MACD + HOD_RECENT + R% floor + same-session BL together block 4+ losers without false positives. `dead_bounce` adds at most 1 more (FATN 5/8) while risking winner false positives. Is the marginal value worth the design complexity?

### Q3 — If option A: what's the threshold for "regime"?
A 60% threshold is a guess. What sample-rate / threshold combination would reject FATN 5/8 while passing ATRA 5/8 (which DID hold above VWAP after the morning gap)?

### Q4 — Acceptance criteria revision?
The current criterion 3 ("FATN 5/8 blocked") may be too narrow. Should the criterion instead be "at least 1 loser blocked that NO other sub-gate catches"? That gives us a useful gate even if FATN 5/8 specifically isn't the catch.

---

## What's in repo right now

- Code reverted to v1 (current dormant state, `WB_CG3_DEAD_BOUNCE_ENABLED=0`)
- `.env.example` reverted to pre-patch state
- Validation report for v2 attempt: `cowork_reports/2026-05-13_chop_gate_v3_dead_bounce_v2_validation.md` (kept for evidence)
- Modular v3 + MACD/HOD_RECENT/XSESSION_BL all unchanged — those continue per Cowork's verdict directive

No code changes will land on `dead_bounce` until Cowork responds to this feedback.

---

## Supporting files

- `DIRECTIVE_CHOP_GATE_V3_SUBGATE_VERDICTS.md` — the verdict directive that motivated the v2 attempt
- `cowork_reports/2026-05-13_chop_gate_v3_dead_bounce_validation.md` — original v1 advisory validation
- `cowork_reports/2026-05-13_chop_gate_v3_dead_bounce_v2_validation.md` — v2 attempt validation showing the failure
- `chop_gate_v3.py` — current dormant v1 code in `sub_gate_dead_bounce`

---

*The validation working correctly is a good outcome. We learned the gate's design assumptions don't match the failure mode it's targeting. Cowork's call on which direction to take next — or whether to skip this sub-gate entirely.*
