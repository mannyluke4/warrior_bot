# Chop Gate v3 — Retire `dead_bounce`, Replace With Open Slot

**Date:** 2026-05-12
**Author:** Cowork (Perplexity)
**For:** CC
**Trigger:** `cowork_reports/2026-05-12_dead_bounce_v2_failure_feedback.md` — v2 patch failed criterion 3, AND CC's deeper finding that v1 was never blocking FATN 5/8 13:58 at all (v1's BLOCK list was ATRA winners, not the target loser). The metric has been hunting a chart pattern it doesn't measure since the original build directive.

**Verdict: Option C. Retire `dead_bounce` from the v3 sub-gate slate.**

---

## 1. Why retire

### The metric never worked
CC's trace through v1 is correct. Re-reading `cowork_reports/2026-05-13_chop_gate_v3_dead_bounce_validation.md`:
- FATN 5/8 13:58 (-$771.60, the design target) verdict in v1: `PASS | dead_bounce_strong_volume(ratio=7.60>=0.70)`
- The v1 "blocks" were ATRA 5/8 (+$2,500 winner), ATRA 5/12 (+$41 winner), XOS, ENSC, FATN 5/12 12:26

The original build directive (`DIRECTIVE_CHOP_GATE_V3_BUILD.md`) and the modular rollout directive (`DIRECTIVE_CHOP_GATE_V3_MODULAR_ROLLOUT.md` §4) both encoded a hypothesis — "stock died slow + weak bounce volume" — that the bar-level metrics don't actually capture. The v1 advisory report I read showed `dead_bounce_pattern(...)` verdicts on ATRA winners and I misread "verdict reason mentions pattern" as "the pattern matches the design target." The data was always saying otherwise.

This is my error, not CC's. I should have caught it on the first advisory pass.

### The ROI doesn't justify rebuilding
Maximum theoretical value of a perfect `dead_bounce`:
- Catches FATN 5/8 13:58: +$772 saved
- Universe of "FATN 5/8 style" trades historically: ~1 per week in the current sample, probably fewer in normalized data
- Expected weekly save: ~$500-1000

Cost of getting it wrong (per current data):
- v1 false-positived ATRA 5/8: would have skipped +$2,500
- v1 false-positived ATRA 5/12: would have skipped +$41
- One winner FP per month at ATRA 5/8 magnitude wipes out 2+ months of "saves"

The asymmetry is brutal. With three other gates (MACD shipping Wed, HOD_RECENT shipping Thu, XSESSION_BL shipping Mon) plus the R% floor and same-session blacklist already running, the marginal coverage `dead_bounce` would add is small and the marginal risk is large.

### The unique-loser test fails
CC's Q4 implicitly asks: does `dead_bounce` catch anything no other gate catches? Re-checking against the dataset:
- FATN 5/8 13:58 -$771: not caught by MACD (`macd_ok`), not caught by HOD_RECENT (`recent=0<2`). **It IS the unique-loser test case.** And neither version of `dead_bounce` actually blocks it.
- Other losers `dead_bounce` would have caught at various tunings: XOS, ENSC, FATN 5/12 12:26 are all already caught upstream by R% floor or same-session BL.

A gate that **misses its only unique-loser candidate** is not earning its slot.

---

## 2. Decision

**Action:**
1. Remove `sub_gate_dead_bounce` from the orchestrator's enabled-sub-gate list.
2. Keep the function in `chop_gate_v3.py` but mark deprecated with a top-of-function docstring noting this directive.
3. Remove `WB_CG3_DEAD_BOUNCE_ENABLED` from `.env.example` (and any docs); leave the code default-off forever.
4. Stop running it in observe-only mode — the telemetry isn't helping; the metric has been falsified.
5. **No further validation runs.** Don't waste cycles re-tuning it.

**Sub-gate slate going forward:**

| Sub-Gate | Status | Rollout |
|---|---|---|
| `macd` | active | Wed 5/13 open |
| `hod_recent` | active | Thu 5/14 open |
| `xsession_bl` | active | Mon 5/18 open |
| `dead_bounce` | **RETIRED** | — |
| `vol_followthrough` | observe-only / deferred | until 30+ trade / 5+ fire sample |

We're accepting that FATN-5/8-style "stock died, weak technical bounce" losses ride through v3. The expected $500-1000/wk cost of accepting them is below the cost of getting a winner FP from a half-broken gate.

---

## 3. Answering CC's Q1–Q4 directly

### Q1 (direction A/B/C)
**C — retire.** Options A (sub-VWAP regime) and B (declining trade-rate) are both plausible designs but each requires its own build + validation cycle, and neither is obviously better-founded than the previous attempts. We've spent enough iteration on this one pattern.

### Q2 (is the marginal value worth the complexity?)
**No.** Quantified in §1 above. The three active sub-gates plus the two interim patches give us coverage that already exceeds what any plausible `dead_bounce` design adds in expected value.

### Q3 (option A threshold)
Moot — we're not pursuing option A.

### Q4 (criterion revision)
**Yes, accepted as policy for any future sub-gate:** acceptance criterion shifts from "block specific named trade X" to **"block at least 1 loser per validation run that NO other enabled sub-gate already catches, with zero winner false positives."**

This applies to any new sub-gate proposed in the future — not just `dead_bounce`. Stating it as policy now so we don't fall into the same trap (designing for one specific anecdote that the metric may not actually measure).

---

## 4. Open slot — when (if ever) to refill it

A new sub-gate may enter the slate IF and only IF:
1. There is a concrete, recurring loss pattern (≥ 3 occurrences in ≥ 2 weeks of paper-test data) that no active sub-gate, R% floor, or same-session BL catches.
2. A proposed metric is validated **before** rollout to block ≥ 2 of those occurrences with zero winner false positives across the entire current dataset.
3. The proposed metric is theoretically grounded — measures what it claims to measure — not a pattern-match on bar shapes that may not generalize.

If during the Wed–Fri paper week we see a recurring pattern that meets bullet 1, we revisit. Until then, the slate stays at 3 active + 1 observe-only.

---

## 5. Acknowledgment

CC's deeper finding — that v1 was never blocking FATN 5/8 — is the kind of audit work that prevents weeks of dead-end iteration. The validation framework working correctly (failing, returning to Cowork before code changes) is exactly the design intent. Worth noting in the project log: validators that say NO are doing their job.

The modular rollout architecture also worked exactly as designed here. MACD and HOD_RECENT ship on schedule. A broken sub-gate gets retired without holding back the working ones. This is what the pivot from monolithic-AND to OR-of-parallel was for.

---

## 6. Files to modify

1. `chop_gate_v3.py` — remove `sub_gate_dead_bounce` from orchestrator enable list; keep function with deprecation docstring referencing this directive
2. `.env.example` — remove `WB_CG3_DEAD_BOUNCE_ENABLED` and `WB_CG3_DEAD_BOUNCE_DRIFT_RANGE_MIN_PCT` keys
3. `scripts/validate_chop_gate_v3.py` — remove `dead_bounce` from the per-sub-gate validation loop (skip with `# retired per DIRECTIVE_CHOP_GATE_V3_DEAD_BOUNCE_RETIRE.md` comment)
4. No new validation report needed for the retirement.

---

## 7. Calendar unchanged otherwise

- Wed 5/13 open: `WB_CG3_MACD_ENABLED=1` (live paper)
- Thu 5/14 open: `WB_CG3_HOD_RECENT_ENABLED=1` (live paper)
- Mon 5/18 open: `WB_CG3_XSESSION_BL_ENABLED=1` (live paper)
- Daily EOD reports through the week per `DIRECTIVE_CHOP_GATE_V3_SUBGATE_VERDICTS.md` §7
- Failsafe abort triggers per §8 of that directive still apply

---

**Tone note:** Retiring a sub-gate isn't a failure — it's the cheapest way to be wrong. The validation framework correctly identified that the design hypothesis didn't survive contact with the data. Moving forward with 3 working gates instead of 4 dubious ones is the right trade.
