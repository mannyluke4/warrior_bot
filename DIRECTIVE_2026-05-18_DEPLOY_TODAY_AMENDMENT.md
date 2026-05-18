# DEPLOY TODAY — Amendment to `DIRECTIVE_2026-05-18_REAL_REGRESSION_AND_DEPLOY.md`

**Date:** 2026-05-18
**Time issued:** 14:19 MDT (20:19 UTC)
**Branch:** `v2-ibkr-migration`
**Author:** Cowork (per Manny direction, Mon 2:19 PM MDT)
**Status:** OVERRIDE — full suite ships TODAY before market open tomorrow

---

## Manny's directive (verbatim)

> "We need to push the full suite today. If we missed a 780% move, we need to do everything we can today to fix it before tomorrow's start. No waiting when there are still full workdays to utilize."

This supersedes the "could finish tonight; could extend to Tuesday morning" framing in the parent directive. **Today is the deadline.** All of Stage A, B, and C must land before tomorrow's 02:00 MT cron (10 hours and 41 minutes from now).

---

## What changes from the parent directive

Nothing structural. Same five-step plan: A1 → A2 → A3 → B → C. **What changes is the wall-clock target and the parallelization:**

- **A1 (regression inventory)** — start NOW, 30 min target
- **A2 (incident-replay suite)** — start NOW in parallel with A1, 2-3 hr target
- **A3 (April → May replay)** — start as soon as A2 has the test harness up, can run unattended while CC works on B
- **B (bundled deploy + re-run A2 + A3)** — apply patches as soon as A2 + A3 PASS, re-run, push
- **C (tomorrow's evening monitoring report)** — written tomorrow after market close, not blocking deploy

CC must not serialize what can be parallelized. The regression inventory (A1) does not block test authoring (A2). The April replay (A3) is mostly waiting on data — it can run in the background while CC writes patches for Stage B.

---

## Hard wall-clock targets

| Stage | Latest acceptable finish (MDT) | Latest acceptable finish (UTC) |
|---|---|---|
| A1 + A2 (test suite green pre-patch) | 18:00 MDT | 00:00 UTC (Tue) |
| A3 (replay diff complete) | 20:00 MDT | 02:00 UTC (Tue) |
| B (patches applied, A2+A3 re-run PASS, pushed) | 23:00 MDT | 05:00 UTC (Tue) |
| Cron picks up at 02:00 MT | 02:00 MDT (Tue) | 08:00 UTC (Tue) |

**If any stage slips past its target, CC pauses and reports.** Cowork or Manny decides whether to push remaining time, descope, or revert to the original Tuesday-evening window. **Do not silently miss the deadline.**

---

## Parallelization map

CC can run these concurrently:

```
NOW ─────────────────────────────────────────────────────────────────────►
│
├─ A1 (inventory) ──┐
│                   │
├─ A2 (test harness)─┴──┐
│                       │
├─ A3 (replay) ─────────┴──┐
│                          │
├─ Patch authoring ────────┘ ← apply once A2 PASS pre-patch
│
└─ B (apply + re-run + push)
```

A2 must show all 7 tests **failing** in the expected pre-patch direction before patches apply. That proves the tests actually exercise the bug, instead of passing trivially.

---

## Descope rules — if time slips

If by **20:00 MDT** A3 hasn't completed, CC has two options:

**Option 1 — descope A3 to a smoke-replay.** Replay only the 3 incident days (SBFM 5/18, SLE 5/15, LNKS 5/14) plus 5 random sessions from April. Get A3 to PASS in 30 min instead of hours. Less coverage, still catches the targeted bugs.

**Option 2 — descope deploy to qty=1 floor + broker-mismatch assert only.** Both are tiny, both have direct-incident A2 tests, both are pure safety. The other two patches (resume-boot, R-floor) ship Tuesday evening with full A3 done right.

**Cowork preference: Option 1 first.** If even smoke-replay can't finish by 22:00 MDT, fall back to Option 2.

CC must NOT silently widen the regression window (e.g., "I'll just re-run the 3 incident tests and call A3 done"). Descope decisions are explicit and reported.

---

## What CC must NOT do (failure modes to avoid)

1. **Do not assume any wall-clock estimate.** Manny: *"Never assume workload time with CC."* Measure each stage's actual time, report it.
2. **Do not skip the pre-patch failing-test check.** If A2 tests pass before patches are applied, the tests are wrong, not the code.
3. **Do not paper over an unexpected divergence in A3.** If a session diff shows behavior changes that the patches weren't designed to cause, halt and diagnose. That's a bug, not a "close enough."
4. **Do not push to `main`.** Only `v2-ibkr-migration`.
5. **Do not deploy without re-running A2 + A3 post-patch.** Pre-patch tests prove the suite is real; post-patch tests prove the patches work.
6. **Do not skip sibling-file patches.** `bot_alpaca_subbot.py`, `simulate.py`, EPL graduation path at `bot_v3_hybrid.py:3206-3207` get the same treatment as `bot_v3_hybrid.py`. Missing one is a regression bomb.

---

## Reporting cadence — every 2 hours

CC posts a one-line status update to chat at 16:30 MDT, 18:30 MDT, 20:30 MDT, 22:30 MDT until deploy lands or descope is invoked:

```
[16:30 MDT] A1 done (target drift docs in <file>). A2 5/7 tests written, 0/7 passing (expected). A3 not started — waiting for A2.
```

Cowork and Manny can intervene if a stage is sliding. Silence is not acceptable on a same-day deploy.

---

## What's not in scope today

- Broker latency investigation (Tracks 1, 2, 3) — continues independently, no priority bump
- WB v2 Stage 0 — continues independently, no priority bump
- Engine framework Wave 4 monitoring — continues independently
- Backtest tick-realism gate (§8.5 of max-chase audit) — still queued, not today

If CC has cycles left after the deploy lands, **rest, do not start the next thing.** Tomorrow morning's premarket is what matters.

---

## Reminder

Today's missed SBFM was a 780% move where Ross made $18K. The bot saw it, armed correctly, was disabled by a sizing-path bug, took 1 share. Tomorrow's premarket will have its own SBFM-class candidate. Whether the bot catches it depends on whether these patches are live before 02:00 MT.

GO.
