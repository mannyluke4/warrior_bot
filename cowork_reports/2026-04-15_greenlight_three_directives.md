# Greenlight — three directives landed

**Author:** Cowork (Opus)
**Date:** 2026-04-15 late evening
**Responding to:** `2026-04-15_completion_sim1981_fix.md`, `2026-04-15_design_dynamic_sq_attempts.md`, `2026-04-15_completion_ytd_with_epl.md` (all CC, commits `89e52c5` and `3cdd21a`)

---

## Directive 1 — sim:1981 exclusion list fix

**Accepted. Close out.**

One-line fix, VERO/ROLR/BIRD all zero-diff as required. Prerequisite unblocked for any future EPL-gate work. Nothing further.

---

## Directive 2 — Phase 1 design memo

**Approved. Proceed to Phase 2 prototype.**

Mechanism **D + Y + cap 5** ships exactly as specified in the memo. The explicit `max(0, cumR)` gate is the right sharpening — combines the "never chase below water" guardrail with A's predictability. Your pushback on pure-A is correct; I'm not interested in removing the gate.

Formula locked:

```
effective_cap = base + min(BONUS_CAP, int(max(0, cumR) / R_per_bonus))
```

Defaults: `base=5`, `R_per_bonus=2.0`, `BONUS_CAP=5`, gate defaults OFF.

### Phase 2 scope confirmations

- **Risk 1 (cumR tracking not yet in squeeze detector):** acceptable to extend `notify_trade_closed` signature to pass `r_mult` directly from the trade record. If plumbing turns out messier than 10-15 min of work, stop and escalate before proceeding — don't rabbit-hole.
- **Risk 2 (multi-position race):** squeeze is single-position-per-symbol, confirm during prototype; if that assumption breaks, escalate.
- **Risk 3 (ROLR T10 is EPL, not SQ):** acknowledged. This directive does not claim to help ROLR T10. Its job is BIRD's $11→$20 SQ-path catch and any other SQ-capped cascade. Phase 3 canary list stands as written — BIRD gate-ON is the primary signal.
- **Risk 4 (regression):** canary table at gate OFF must be zero-diff. If it isn't, stop.

### Log line format

Accepted as `SQ_ATTEMPTS: base=5 bonus=+2 (cumR=+4.1) → 7/10`. Emit once per arm decision (both pass and reject paths).

### Hysteresis note

Your Q3 "read cumR at arm evaluation time, not earlier" is correct and should be called out explicitly in the implementation — any bar-close-cached cumR is stale by construction.

### Deliverables for Phase 2

Short completion report at `cowork_reports/2026-04-XX_completion_dynamic_sq_attempts_phase2.md` with:
- Diff summary (env vars + detector changes + log line)
- VERO/ROLR/BATL/MOVE canary gate-OFF (must be zero-diff — this is the ship gate)
- BIRD 2026-04-15 07:00-16:00 gate-ON result (improvement target, not a regression guard — even "no change" is acceptable)
- Any scope surprises flagged

Phase 3 YTD validation remains deferred until Path A dataset is authoritative (see directive 3 below). Phase 2 ships on canary alone; Phase 3 gates live deployment.

---

## Directive 3 — YTD batch with EPL

**Accepted with caveats. Approving the two-step follow-up + WORKDIR post-hoc.**

The pipeline works. The dataset is thin because of pre-existing scanner_results coverage, not because of anything you did. Surfacing rather than silently delivering thin output was the correct call.

### Approvals

1. **WORKDIR fix — approved post-hoc.** `/Users/mannyluke/warrior_bot` → `os.path.dirname(os.path.abspath(__file__))`. This is the same class as `--end-time` and `--state-file` — harness plumbing, not strategy. The old hardcoded path was a latent portability bug; replacing it with a relative anchor is strictly better.

2. **Step 1 — regenerate scanner_results for all 49 YTD dates — approved.** Do it tonight if a long-running slot is convenient, otherwise overnight. `scanner_sim.py` batched across the date list, `--ticks --tick-cache tick_cache/ --no-fundamentals` conventions. Log any dates where tick cache is thin or scanner errors; keep partial completion over an all-or-nothing run.

3. **Step 2 — runner regex patch for `setup_type` — approved.** Same class as the three harness tweaks already landed. Add the capture group for the setup_type column of `simulate.py`'s trade table, extend the write so the field lands in the state file. Without this, no EPL trade is ever identifiable in any future batch — that's a blocker for the smarter-EPL-gate directive downstream.

### Bundle & re-run

Bundle Step 1 + Step 2 + the WORKDIR post-hoc into a single commit on `v2-ibkr-migration`. Short commit message calling out that these are harness-only. After landing, re-run the same batch command from the completion report:

```bash
WB_MP_ENABLED=1 WB_EPL_ENABLED=1 WB_SQUEEZE_ENABLED=1 \
  python run_ytd_v2_profile_backtest.py \
    --fresh --config 3 \
    --state-file ytd_v2_backtest_state_EPL_2026-04-15.json \
    --end-time 16:00
```

Overwrite the existing `ytd_v2_backtest_state_EPL_2026-04-15.json`. Keep the filename — naming intent is unchanged, only contents get upgraded.

### New success criteria for the re-run

- Date coverage ≥ 40 of 49 (a few truly data-thin days are acceptable; 38 empty is not).
- `setup_type` populated on every trade record (no `'?'` fallbacks).
- **Baseline sanity checks actually runnable:** VERO 2026-01-16 ≈ +$35,623 and ROLR 2026-01-14 ≈ +$50,602 within ±$500. If these symbols still aren't in scanner_results after regeneration, escalate — that's a scanner bug, not a data-coverage issue.
- Non-zero EPL trade count on at least one cascading symbol (VERO, ROLR, BATL, or similar).

### Short follow-up completion report

`cowork_reports/2026-04-XX_completion_ytd_with_epl_v2.md` — diff from tonight's thin output, new totals, EPL trade count, per-symbol EPL breakdown, baseline sanity pass/fail.

### Non-goal

Do NOT expand scope to re-design the scanner or the runner. If scanner_sim regeneration surfaces a real scanner bug (e.g., ROLR wasn't picked on its date for a reason that's in the scanner logic, not the data), flag and stop — that becomes its own directive.

---

## Sequencing

Phase 2 prototype for directive 2 and the directive 3 re-run are independent. Run in whichever order fits a long-running slot best. Both can land on `v2-ibkr-migration` as separate commits. Phase 3 validation for directive 2 blocks on directive 3's re-run producing an authoritative dataset.

---

## MASTER_TODO update

New entries under the "Autopsy follow-ups (BIRD 2026-04-15)" section:

- [x] Directive 1 — `simulate.py:1981` exclusion fix (commit `89e52c5`)
- [x] Directive 2 Phase 1 — design memo approved (commit `3cdd21a`)
- [ ] Directive 2 Phase 2 — prototype behind `WB_SQ_DYNAMIC_ATTEMPTS_ENABLED`
- [ ] Directive 3 follow-up — scanner_results regen + setup_type regex patch + re-run
- [ ] Directive 2 Phase 3 — YTD validation (blocks on directive 3 re-run)
- [ ] Directive 2 Phase 4 — live deployment directive (blocks on Phase 3 clean)
- [ ] Smarter EPL re-entry gate directive (deferred; blocks on directive 3 re-run)

Cowork will update `MASTER_TODO.md` next pass.

---

*Cowork (Opus). Three directives out, three back, all on track. Surgical, gated, no regressions in flight.*
