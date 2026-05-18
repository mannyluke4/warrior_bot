# Deploy Amendment — Full Suite, Same Day

**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Author:** Cowork (per Manny direction, Mon 2:19–2:24 PM MDT)
**Status:** Amendment to `DIRECTIVE_2026-05-18_REAL_REGRESSION_AND_DEPLOY.md` — full suite ships today; deferred Tuesday-evening window is no longer the target.

---

## Manny's directive

> "We need to push the full suite today. If we missed a 780% move, we need to do everything we can today to fix it before tomorrow's start."

Same five-step plan from the parent directive (A1 → A2 → A3 → B → C). What changes is the target landing point: **all of A and B should land before tomorrow's 02:00 MT cron.** C (post-deploy monitoring) is written tomorrow after the session.

---

## Parallelization

CC has multiple agents and is expected to use them. The work below is decomposed so independent threads can run concurrently:

- **Thread 1 — A1: Regression inventory.** Self-contained. Produces `cowork_reports/2026-05-18_regression_inventory.md` per the parent directive. Does not block anything else.
- **Thread 2 — A2: Incident-replay test suite.** Self-contained authoring. Tests are designed to fail pre-patch and pass post-patch. Does not block anything else.
- **Thread 3 — A3: April → May replay.** Once A2's harness exists, A3 can run unattended in the background while other threads work.
- **Thread 4 — Patch authoring.** The four patches (qty=1 floor removal, resume-boot stale-signal fix, R-floor gate, runtime broker-mismatch assert) plus sibling-file mirrors. Authored as soon as A2 confirms the tests fail in the expected pre-patch direction.
- **Thread 5 — B (deploy).** Once all of A2 + A3 PASS pre-patch and the patches are written, apply patches, re-run A2 + A3 post-patch, and push to `v2-ibkr-migration` if green.

CC chooses the agent allocation. Threads 1, 2, 3, and 4 do not depend on each other for correctness — only Thread 5 has hard upstream dependencies.

---

## What each thread produces

### Thread 1 — A1: Regression inventory

`cowork_reports/2026-05-18_regression_inventory.md` answers:

- What automated tests exist that cover `bot_v3_hybrid.py:3000-3100` (sizing path)? List file:line.
- What automated tests exist for the resume-boot signal-rehydration path? List file:line.
- VERO 2026-01-16: which expected P&L is the current correct target — +$18,583 (cited in March 2026 reports) or +$34,479 (cited in today's SBFM report)? When did it change? Which commit?
- ROLR 2026-01-14: same question, +$6,444 vs +$54,654.
- Was there an original directive establishing VERO/ROLR as canonical regression, or did it become a copy-paste ritual?

### Thread 2 — A2: Incident-replay test suite

`tests/regression/test_incident_replay.py` containing seven tests:

1. **SBFM 2026-05-18 qty=0 skip** — replay SBFM scanner state at 07:19 ET with simulated `_c.get_account()` raising. Pre-patch: bot submits 1 share. Post-patch: bot logs `BP_FETCH_FAIL`, falls back to cached BP, or skips. Assertion: zero qty=1 orders.
2. **SBFM with cached BP** — same scanner state but `_last_known_bp = $59,374`. Post-patch expected: order qty in [3,000, 4,000].
3. **SLE 2026-05-15 16:17 resume-boot suppression** — replay SLE 16:17 ENTRY at $5.09 with `[RESUME]` event in same minute, live tape at $5.85. Post-patch expected: zero ENTRY orders submitted between 16:17 and 17:50 ET.
4. **LNKS 2026-05-14 R-floor rejection** — replay LNKS scanner state at 13:48 ET with R=$0.06 and `WB_MIN_ABSOLUTE_R=$0.10`. Post-patch expected: rejected with reason `R_BELOW_FLOOR`.
5. **Runtime broker-mismatch assert** — launch with `WB_BROKER=ibkr` while paper-account profile expects Alpaca. Post-patch expected: process exits with non-zero status.
6. **VERO 2026-01-16 control** — run unmodified VERO replay through the patched code. Assertion uses the actual current target (resolved by A1).
7. **ROLR 2026-01-14 control** — same as test 6.

Output: `cowork_reports/2026-05-18_incident_regression_results.md` with per-test pre-patch and post-patch PASS/FAIL.

### Thread 3 — A3: April → May replay

Run the patched bot in replay mode against every session 2026-04-01 → 2026-05-17 (exclude 5/18 as the patch-target day). Per session, diff: same entries? Same fills? Same P&L? Any unexpected divergence?

Expected divergences (the patches doing their job):
- SLE 2026-05-15 evening: 6 chase-cap aborts → 0 (resume-boot fix)
- LNKS 2026-05-14 13:48: 1 entry → 0 (R-floor)
- Possibly other low-R signals filtered

Unexpected divergences halt the deploy.

Output: `cowork_reports/2026-05-18_april_to_may_replay_diff.md` plus per-session CSV.

### Thread 4 — Patch authoring

Four patches to author:

1. **qty=1 floor removal** — `bot_v3_hybrid.py:3048` and sibling files (`bot_alpaca_subbot.py`, `simulate.py`, EPL graduation path at `bot_v3_hybrid.py:3206-3207` if it has the same pattern).
2. **Resume-boot stale-signal fix** — per `cowork_reports/2026-05-18_resume_boot_stale_signal_fix.md`, applied to `bot_v3_hybrid.py` and `bot_alpaca_subbot.py`.
3. **R-floor gate** — per `cowork_reports/2026-05-18_r_floor_gate_design.md`, env var `WB_MIN_ABSOLUTE_R=$0.10`. Applied to `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `simulate.py`.
4. **Runtime broker-mismatch assert** — boot-time check that `WB_BROKER` matches the paper-account profile expectation. Fails loud at boot.

Authored ready to apply. Not applied until Thread 5.

### Thread 5 — B: Deploy

Preconditions:
- Thread 1 (A1) complete
- Thread 2 (A2) tests authored and showing expected pre-patch failures
- Thread 3 (A3) complete with diffs reviewed and unexpected divergences resolved (none expected; halt if found)
- Thread 4 patches authored

Sequence:
1. Apply all four patches to `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `simulate.py`, EPL graduation path
2. Re-run A2 — all 7 tests must PASS
3. Re-run A3 — diff must show only expected divergences
4. Push to `v2-ibkr-migration`

If A2 or A3 post-patch fails, revert and diagnose. Do not push partial.

---

## Stage C — Tomorrow's post-deploy monitoring

Written tomorrow after market close. Captures:
- Did the bot fire any entries?
- Did any premarket signal trigger BP-fetch fallback (cached value used)? Log the cache age and resulting qty.
- Did the runtime broker-mismatch assert fire? (It shouldn't.)
- Did the resume-boot suppression engage? (Only on a restart event.)
- Did the R-floor gate reject any signals? Log each.

Output: `cowork_reports/2026-05-19_post_deploy_monitoring.md`.

Stage C does not block the deploy.

---

## Hard guardrails

1. **Pre-patch tests must FAIL** in the expected direction. If A2 tests pass before patches are applied, the tests are wrong, not the code.
2. **Post-patch tests must PASS.** Both A2 and A3 must be re-run after patches are applied; pre-patch results are not sufficient.
3. **Unexpected A3 divergences halt the deploy.** Diagnose, don't paper over.
4. **Sibling files get the same treatment.** Missing one creates a regression bomb.
5. **Branch: `v2-ibkr-migration` only.** Not `main`.
6. **No descope without explicit approval.** If any stage cannot complete, CC posts a report describing what's blocking and proposes options. Cowork or Manny decides.

---

## Reporting

CC posts a status update at each significant transition (each thread complete, blockers, post-patch test results, push). Format: which thread, what's done, what's pending, any blockers. No fixed cadence — just write when there's something to report.

---

## Out of scope today

These workstreams continue independently and are not affected by this directive:

- Broker latency investigation (Tracks 1, 2, 3)
- WB v2 Stage 0 research
- Engine framework Wave 4 paper monitoring
- Backtest tick-realism gate (queued, not now)

---

GO.
