# Real Regression + Bundled Deploy

**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Author:** Cowork (per Manny direction, Mon 2:16 PM MDT)
**Status:** GO — replace stale VERO/ROLR regression with incident-grounded regression, then deploy

---

## Why this directive exists

Manny: *"This is a new CC iteration. For some reason, they are always deferring to stale VERO/ROLR regressions. We need to see what the actual regression is, and start on all of that now."*

He's right. CC has been citing **VERO 2026-01-16 +$18,583** and **ROLR 2026-01-14 +$6,444** as the canonical regression battery in 15+ reports going back to March 2026. Two months later, through three major refactors, those targets are still pasted into reports — but today's SBFM report cites different numbers (+$34,479 / +$54,654) for the same dates. **The regression has drifted from authoritative to ritual.**

More importantly: VERO and ROLR don't exercise any of the failure modes we're trying to patch:

- VERO doesn't trigger BP=$0 (no DNS blip on that date)
- VERO doesn't trigger probe-rounding-to-zero (size_mult=1.0 throughout)
- ROLR doesn't trigger the resume-boot stale-signal loop (no intra-day restart)
- Neither has an R<$0.10 setup that the R-floor gate would reject

The incidents we're patching are **SBFM 2026-05-18, SLE 2026-05-15, LNKS 2026-05-14**. The regression suite must include those.

---

## What the real test surface actually is

| Surface | What's there |
|---|---|
| Code tests (`tests/backtest/`, `tests/framework/`) | 530+ tests, mostly framework. Almost zero coverage of `bot_v3_hybrid.py` sizing path. |
| Tick data (`tick_cache/`) | Sparse before 2026-03-23, dense April 2026 → today. ~35 sessions of squeeze-paper-quality replay data. |
| Scanner results (`scanner_results/*.json`) | Daily JSONs, April 2026 → today |
| Daily logs (`logs/*_daily.log`) | Every session April 2026 → today (~30 trading days) |
| Backtest harness | `simulate.py` (squeeze backtest), `portfolio_backtest.py` (framework) |
| Forensic scripts | `analyze_latency_diagnostic.py`, `forensic_*.py`, etc. |

The honest answer: **the regression we should be running is "replay April 2026 → today through the patched code and diff against actual live behavior, with explicit assertions on the three incident days."** That's what proves the fix works on the failures it was designed for.

---

## Stage A — Regression rebuild (CC, before any deploy)

### A1. Inventory current regression

CC produces `cowork_reports/2026-05-18_regression_inventory.md`:

- What automated tests exist that cover `bot_v3_hybrid.py:3000-3100` (sizing path)? List file:line.
- What automated tests exist for the resume-boot signal-rehydration path? List file:line.
- What automated tests exist for the R-floor gate (none expected — gate is new)? List file:line if any.
- VERO 2026-01-16: which expected-P&L number is correct, +$18,583 (March) or +$34,479 (today)? When did it change? Why? **Find the commit that changed the target.**
- ROLR 2026-01-14: same question, +$6,444 vs +$54,654.
- Why has CC been citing VERO/ROLR specifically across 15+ reports without re-grounding? Was there a directive establishing them as canonical, or did it become a ritual?

This is hygiene. We need to know what we have before we add to it.

### A2. Build incident-replay regression suite

CC creates `tests/regression/test_incident_replay.py` with these assertions, each grounded in actual logs/tick data:

**Test 1 — SBFM 2026-05-18 qty=0 skip**
- Setup: replay SBFM scanner state at 07:19 ET on 2026-05-18 with simulated `broker.get_buying_power() == 0` (or simulated `_c.get_account()` raising)
- Pre-patch behavior (regression baseline): bot submits 1-share order
- Post-patch expected: bot logs `BP_FETCH_FAIL`, falls back to cached BP if available, skips entry if no cache, OR sizes correctly with cached value
- Assertion: zero qty=1 orders, zero `qty=0` orders bypassed by `max(1, …)`

**Test 2 — SBFM with cached BP from prior call**
- Setup: same scanner state, but `_last_known_bp = $59,374` (a real BP value from earlier in the session)
- Post-patch expected: sizing uses cached BP, qty ≈ 7,348 base × 50% probe ≈ 3,674 shares
- Assertion: order qty in [3,000, 4,000] range

**Test 3 — SLE 2026-05-15 16:17 resume-boot suppression**
- Setup: replay SLE 16:17 ENTRY signal at $5.09 with bot `[RESUME]` event in the same minute, live tape at $5.85
- Pre-patch behavior: signal re-fires; chase-cap aborts; repeats every 30 minutes
- Post-patch expected: signal is suppressed (either via "rehydrated signal too far from current price" rule or "signal already-acted-on" persistence flag)
- Assertion: zero ENTRY orders submitted between 16:17 and 17:50 ET on SLE 2026-05-15

**Test 4 — LNKS 2026-05-14 R-floor rejection**
- Setup: replay LNKS scanner state at 13:48 ET with R=$0.06
- Pre-patch behavior: signal armed and submitted
- Post-patch expected (with `WB_MIN_ABSOLUTE_R=$0.10`): signal rejected with reason `R_BELOW_FLOOR`
- Assertion: zero ENTRY orders submitted for LNKS 2026-05-14 13:48

**Test 5 — runtime broker-mismatch assert**
- Setup: launch bot with `WB_BROKER=ibkr` while paper-account profile expects Alpaca
- Pre-patch behavior: silent — connects to wrong broker
- Post-patch expected: bot fails at boot with clear error
- Assertion: process exits with non-zero status and logs the mismatch

**Test 6 — VERO 2026-01-16 control**
- Run the unmodified VERO replay through the patched code
- Assertion: P&L matches the actual current target (we'll know which after A1)

**Test 7 — ROLR 2026-01-14 control**
- Same as Test 6, ROLR control

CC reports per-test PASS/FAIL with full diffs. Output: `cowork_reports/2026-05-18_incident_regression_results.md`.

### A3. April 2026 → today replay

CC runs the patched bot in replay mode against every session from 2026-04-01 → 2026-05-18 (skip 5/18 as the patch-target day) and produces a session-by-session diff:

- For each session: were entries the same? Was P&L the same? Were any orders submitted that weren't submitted live? Were any orders skipped that were submitted live?
- Expected divergences (i.e., the patches doing their job):
  - SLE 2026-05-15 evening: 6 chase-cap aborts → 0 (resume-boot fix)
  - LNKS 2026-05-14 13:48: 1 entry → 0 (R-floor)
  - Possibly other low-R signals filtered (R-floor catches more than just LNKS)
- Unexpected divergences are bugs.

Output: `cowork_reports/2026-05-18_april_to_may_replay_diff.md` + per-session CSV.

**Time estimate (CC, do not assume — measure):** if each session takes 3 minutes to replay, 30 sessions = 90 minutes. If it takes 10 minutes, 5 hours. Report actual wall-clock when complete.

---

## Stage B — Bundled deploy (post-A2 + A3 PASS)

Four patches, all to `bot_v3_hybrid.py` and sibling files. Apply in this order:

1. **qty=1 floor removal** (`bot_v3_hybrid.py:3048` — remove `max(1, …)`)
2. **Resume-boot stale-signal fix** (per `2026-05-18_resume_boot_stale_signal_fix.md`)
3. **R-floor gate** (per `2026-05-18_r_floor_gate_design.md`, env var `WB_MIN_ABSOLUTE_R=$0.10`)
4. **Runtime broker-mismatch assert** (boot-time check that `WB_BROKER` matches the configured paper-account expectation)

Sibling files needing the same patches:
- `bot_alpaca_subbot.py` (Setup B path)
- `simulate.py` (backtest fill model — gets the qty=1 fix mirror; resume-boot doesn't apply; R-floor applies as a backtest-time setup filter)
- `bot_v3_hybrid.py:3206-3207` (EPL graduation path — same `max(1, …)` shape, check for the same bug)

After patches applied, re-run Stage A2 + A3. If any assertion fails, **revert and diagnose**.

If all assertions pass, push to `v2-ibkr-migration` and the next 02:00 MT cron picks up the changes.

---

## Stage C — Tomorrow's monitoring

The first session running with all four fixes deserves close attention. CC produces an evening report:

- Did the bot fire any entries today?
- Did any premarket signal trigger BP-fetch fallback (cached value used)? If yes, log the cache age and the resulting qty.
- Did the runtime broker-mismatch assert fire at any point? (It shouldn't — but if it does, that's a config drift.)
- Did the resume-boot suppression engage? (Only if there's a restart event; rare on a clean session.)
- Did the R-floor gate reject any signals? Log each one.

Output: `cowork_reports/2026-05-19_post_deploy_monitoring.md`.

---

## Hard constraints

- **Setup A is sacred caveat:** the four patches DO touch `bot_v3_hybrid.py`. That's been the designated exception path since the SBFM incident — Setup A is sacred *to changes that aren't directive-approved*. These four are explicitly approved.
- Branch: `v2-ibkr-migration` only.
- No market orders. No broker stops. No overnights. Force-exit at 19:55.
- Squeeze 6/15 real-money cutover unchanged.
- No bypass of regression. **Stage A2 and A3 must pass before Stage B applies.**

---

## CC work queue (priority order)

1. **A1: Regression inventory.** Find the truth about VERO/ROLR target drift. ~30 min.
2. **A2: Incident-replay regression suite.** 7 tests. ~2-3 hr.
3. **A3: April → May replay diff.** ~90 min - 5 hr depending on replay throughput.
4. **B: Bundled deploy.** Apply all four patches. Re-run A2 + A3. ~1 hr.
5. **C: Tomorrow's evening report.** Monitoring summary.

**Total wall-clock estimate:** 4-9 hours from now (Mon 2:16 PM MDT). Could finish tonight if A3 is fast; could extend to Tuesday morning if A3 is slow. **Do not assume — measure and report actuals.**

---

## What's NOT in this directive

- Broker latency investigation (Tracks 1, 2, 3 from `DIRECTIVE_2026-05-18_BROKER_LATENCY_INVESTIGATION.md`) continues independently. Track 1 (April single-shot audit) and Track 3 (Lightspeed research) already have output and need Cowork synthesis later. Track 2 (instrumentation) starts as soon as feasible.
- WB v2 Stage 0 — already in progress.
- Engine framework Wave 4 paper monitoring — already running.

---

## The deeper lesson

VERO/ROLR were valid regression targets in March. They're stale today because we didn't re-anchor. The Stage A1 hygiene work — finding when targets drifted, what they should be, and how the citation became ritual — matters beyond this deploy. Going forward:

- **Every directive that approves a patch must specify what the regression targets are by date.**
- **Every regression citation must include the run date.** "VERO +$18,583 (run 2026-03-19)" is honest. "VERO +$18,583 (regression pass)" is ritual.
- **Whenever an incident exposes a failure mode, the incident becomes a regression target.** SBFM, SLE, LNKS join the suite as of today.

GO.
