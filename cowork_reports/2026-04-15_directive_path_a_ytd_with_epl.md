# Directive — Path A: full-YTD batch regeneration with EPL enabled

**Author:** Cowork (Opus)
**Date:** 2026-04-15 evening
**For:** CC
**Type:** Data generation. No code changes to bot/sim/detectors.
**Why:** Prerequisite for the smarter-EPL-gate directive and for Phase 3 YTD validation of the dynamic SQ attempts directive. Current YTD state files predate EPL (per `2026-04-15_finding_ytd_predates_epl.md`).

---

## Goal

Produce an authoritative YTD state dataset that includes EPL MP re-entry trades. Once this exists, any future gate or tuning directive can measure its aggregate YTD delta against a real population of EPL trades rather than inferring from 5-day canaries.

## Config

Use today's live `.env` config verbatim. Specifically required:

- `WB_SQUEEZE_ENABLED=1`
- `WB_MP_ENABLED=1` (sim convention per CLAUDE.md)
- `WB_EPL_ENABLED=1`
- X01 tuning: `WB_SQ_VOL_MULT=2.5`, `WB_SQ_PRIME_BARS=4`, `WB_SQ_MIN_BODY_PCT=2.0`, `WB_SQ_MAX_ATTEMPTS=5`, `WB_SQ_TARGET_R=1.5`, `WB_SQ_CORE_PCT=90`, `WB_RISK_PCT=0.035`
- `WB_SQ_VOL_WINSORIZE_ENABLED=1`, `WB_SQ_VOL_WINSORIZE_CAP=5.0`
- `WB_SQ_SEED_STALE_GATE_ENABLED=1`, `WB_SQ_SEED_STALE_PCT=2.0`
- `WB_NO_REENTRY_ENABLED=1`, `WB_MAX_SYMBOL_LOSSES=1`, `WB_MAX_SYMBOL_TRADES=2`
- `WB_PILLAR_GATES_ENABLED=1`, `WB_WARMUP_BARS=5`, `WB_BAIL_TIMER_ENABLED=1`

Any new live flag that lands before this runs should be folded in — the point is to mirror live exactly.

## Scope

All dates with cached tick data. Per CC's finding: ~28 days / 240 pairs / 34M ticks in current cache.

- Use `run_ytd_v2_profile_backtest.py` (or the current equivalent batch runner — don't invent a new one) with the config above.
- Window: `07:00 16:00` (extended to catch afternoon legs and box-session activity; matches the backtesting convention established in the entry-slippage directive).
- `--ticks --tick-cache tick_cache/ --no-fundamentals` per CLAUDE.md.

## Output

- `ytd_v2_backtest_state_EPL_2026-04-15.json` in the existing `backtest_status/` or wherever the batch runner writes. Naming should be explicit that this is the EPL-enabled dataset so it can't be confused with the March pre-EPL files.
- Short summary report at `cowork_reports/2026-04-15_completion_ytd_with_epl.md` including:
  - Date range actually run
  - Total trades (SQ / EPL / other split)
  - Net P&L
  - Per-symbol EPL trade count for any symbol with ≥1 EPL trade
  - Baseline sanity check: VERO 2026-01-16 and ROLR 2026-01-14 totals should match the canary replay numbers from the BIRD autopsy (+$35,623 and +$50,602 respectively) within ±$500 drift

## Sanity / guardrails

- Do not modify any `.py` in the detector or bot path. This is a data run. If the batch runner itself needs a one-line tweak to write EPL trade records correctly, flag it and stop for Cowork review.
- If the batch runner throws on any specific date, log and continue — a missing day is better than a silent failure. Report all skipped dates in the summary.
- Expected wall time: 30-90 min per CC's estimate. Run overnight if needed. No urgency on when it completes, only that the output is authoritative.

## Hard rules

- Zero code changes to behavior-affecting files.
- Do not cherry-pick dates. The dataset's value is in its completeness.
- Do not change `.env` to run this — pass env vars explicitly on the batch runner's command line if needed.

## What this does NOT do

- Does not prototype, analyze, or recommend any gate.
- Does not make any config change decision.
- Does not update CLAUDE.md or live config.

This is pure dataset generation. The smarter-gate directive reads this file; this directive produces it.

## Deliverable ordering

This can run in parallel with the dynamic-SQ-attempts Phase 1 design memo. No dependency between them until dynamic-SQ-attempts reaches Phase 3 validation.

---

*Cowork (Opus). Data first, analysis later, code last. Kick it off when a long-running slot is convenient.*
