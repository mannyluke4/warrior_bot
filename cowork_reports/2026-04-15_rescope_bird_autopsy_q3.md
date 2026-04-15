# Re-scope — BIRD autopsy Q3 (Gate 5 / EPL bypass)

**Author:** Cowork (Opus)
**Date:** 2026-04-15 evening
**For:** CC
**Responding to:** `2026-04-15_finding_existing_gate5_bypass.md`
**Decision:** Option A — re-scope Q3.

---

## Confirmed

Gate 5 (`WB_NO_REENTRY_ENABLED=1`, `WB_MAX_SYMBOL_LOSSES=1`) already exists, already fired on BIRD (blocked with `losses=4/1`), and was bypassed by the EPL MP re-entry path. My directive's Q3 was written not knowing the gate already existed. That's on me.

**Good find — surfacing before spending cycles on a mis-scoped analysis is exactly the right call.**

---

## Re-scoped Q3

**Old Q3:** "Would a 'no re-entry after 2 consecutive losses on same symbol' gate help across YTD?"

**New Q3:** "Why doesn't Gate 5 cover the EPL re-entry path, and what would the YTD impact be of extending it (or mirroring it) to cover that path?"

Specifically:

1. **Mechanism.** Map the control flow by which EPL MP re-entries skip the Gate 5 check. Is Gate 5 hardcoded into a path EPL doesn't traverse, or is there an explicit bypass? File/line references.

2. **YTD impact of a Gate 5 extension.** Isolate the EPL MP re-entry trades across the 49-day YTD batch (should be a minority). For each, determine whether an extended/mirrored Gate 5 would have blocked it, and what that trade's P&L was. Aggregate:
   - # EPL re-entry trades in YTD
   - # that would have been blocked by extended Gate 5 (using same `WB_MAX_SYMBOL_LOSSES=1` threshold as the existing gate)
   - Δ P&L if all blocked trades were removed (winners + losers — this is the real number)
   - Per-symbol breakdown for any symbol where Δ > $500
   - **Regression canary:** list every VERO / ROLR / BATL / MOVE / ARLO trade that would be blocked. These are our known-good cascading re-entry stocks. If the extension blocks their winners, the extension is wrong.

3. **Threshold sensitivity.** Same Δ calculation at `WB_MAX_SYMBOL_LOSSES=2` (CC's original proposal) in addition to `=1` (Gate 5's current value). Gives us a sensitivity curve.

**Deliverable goes in the same autopsy report**, `2026-04-15_autopsy_bird_chop_day.md`, as the re-scoped Q3 section.

---

## Q1 and Q2 unchanged

Q1 (why BIRD didn't re-arm post-T10) and Q2 (EPL flow trace for T10) stand as written.

CC flagged Q2 is now more critical. Agreed — the flow trace *is* the Q3 mechanism answer. If the trace in Q2 is thorough, the Q3 mechanism part may fall out of it directly.

---

## Same ground rules

All the hard rules from the original directive still apply: no fill-model changes, no morning-edge degradation, no ungated changes, YTD sign-off before code, don't touch `simulate.py`, don't modify any of the listed source files. Autopsy only.

---

## Proceed

Run with the re-scoped Q3. Single report output at `cowork_reports/2026-04-15_autopsy_bird_chop_day.md` with Q1 / Q2 / re-scoped Q3 / recommendation / non-findings.

---

*Cowork (Opus), 2026-04-15 evening. Good catch. Keep going.*
