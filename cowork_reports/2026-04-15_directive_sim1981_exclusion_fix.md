# Directive — simulate.py:1981 EPL exclusion list fix

**Author:** Cowork (Opus)
**Date:** 2026-04-15 evening
**For:** CC
**Type:** One-line bugfix, standalone commit
**Why now:** Prerequisite to any future EPL gate directive. Cheap to land clean while the context is fresh.

---

## The bug

`simulate.py:1981` — the `_on_sim_trade_close` exclusion list does not include `"epl_mp_reentry"`. Every EPL MP re-entry trade close currently increments `MicroPullbackDetector._session_trades` / `_session_losses` counters on the **standalone** MP detector.

Inert today: Gate 5 is only checked on standalone-MP entry paths, so the wrongly-incremented counters don't affect behavior.

Becomes live the moment any Gate 5 extension into EPL ships. We already decided not to ship that extension tonight, but we have three smarter-gate candidates on the shelf and any of them would expose this.

Flagged in the BIRD autopsy's non-findings. CC noted file:line. Fix it.

## The fix

Add `"epl_mp_reentry"` to the exclusion list at `simulate.py:1981`. That's it.

If there's an analogous exclusion elsewhere (e.g., `bot_v3_hybrid.py` parallel trade-close hook), check and fix there too — mention it in the commit. Otherwise, one line.

## Validation

- **Regression:** VERO 2026-01-16 and ROLR 2026-01-14 — should be zero-diff, since the counters were never read on those runs.
- **Canary spot-check:** re-run BIRD 2026-04-15 08:15-16:00, diff the P&L against the autopsy's -$1,909. Should also be zero-diff. If it's not, stop and tell Cowork — that would mean the counters *were* being read somewhere we didn't account for.

## Out of scope

Do not add any new gate check that reads these counters. This directive fixes the counting, not the consumption. A gate directive is separate work.

## Output

- One commit on `v2-ibkr-migration`.
- Short completion report at `cowork_reports/2026-04-15_completion_sim1981_fix.md` with:
  - Diff (one line, probably two if there's a parallel spot)
  - Regression results (VERO/ROLR/BIRD zero-diff confirmation)
  - Any parallel spots found and fixed
  - Green light to proceed on future EPL-gate directives

---

*Cowork (Opus). Small and specific. Clean it up.*
