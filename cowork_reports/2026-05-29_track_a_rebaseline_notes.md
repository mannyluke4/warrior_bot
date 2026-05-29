# Track A YTD Re-baseline — Cooldown Removal Verdict

**Date**: 2026-05-29 (afternoon)
**Owner**: CC
**Source**: `cowork_reports/2026-05-29_sim_live_convergence_directive.md` Component 1 cascading consequence
**Status**: **PASS — Track A verdict unchanged. Monday's Variant B live flip is green-lit.**

---

## TL;DR

Re-ran Track A YTD acceptance backtests with sim cooldowns removed (Component 1 of the convergence directive). All 5 Phase 4 acceptance criteria still pass; combined delta moves from +$106,842 to +$101,621 (-$5,221, within ±$10K tolerance). FT-only stats are *bit-identical*. REGIME_SHIFT differs by $39. The entire delta change comes from MOVE_STRIKE trades, which Track A doesn't target.

**Monday's Variant B Track A live flip ships as scheduled.**

---

## Methodology

Two new YTD runs (2026-01-02 → 2026-05-28) with identical config to the original Track A acceptance runs, except sim cooldowns removed per Component 1:

- **Run F2'**: baseline, no Track A, cooldowns removed
- **Run E'**: Track A enabled, cooldowns removed

Identical universe source (tick_cache + sub-bot-log fallback), identical FT trigger thresholds, identical regime_shift detector config, `WB_ENTRY_TIME_CUTOFF_ET=23:59` workaround for the wall-clock sim bug.

Comparison vs original Run F2 / Run E (same backtest JSONs from yesterday).

---

## Top-line comparison

| Slice | F2 (old) | E (old) | Δ_old | F2' (new) | E' (new) | Δ_new | Δ change |
|---|---|---|---|---|---|---|---|
| All | -$157,022 | -$50,180 | **+$106,842** | -$151,514 | -$49,893 | **+$101,621** | -$5,221 |
| firestorm_trigger | -$101,197 | -$27,567 | +$73,630 | -$101,197 | -$27,567 | **+$73,630** | $0 |
| regime_shift | -$50,058 | -$20,796 | +$29,262 | -$50,019 | -$20,796 | **+$29,223** | -$39 |

The -$5,221 all-strategy delta change is concentrated in MOVE_STRIKE trades (the only setup affected by the removed cooldowns). FT and REGIME_SHIFT — the strategies Track A targets — are unchanged or off by single-digit dollars.

---

## Per-strategy detail

### firestorm_trigger — bit-identical

| Metric | Old | New |
|---|---|---|
| F2 trades | 647 | 647 |
| F2 WR | 47.7% | 47.7% |
| F2 P&L | -$101,197 | -$101,197 |
| E trades | 650 | 650 |
| E WR | 69.6% | 69.6% |
| E P&L | -$27,567 | -$27,567 |

Zero divergence. The FT detector has its own per-symbol cap (`WB_FIRESTORM_TRIGGER_MAX_PER_SYM=3`) which is enforced in `_maybe_fire_firestorm_trigger` independent of sim's `_symbol_cooldown_until`. Cooldown removal had no effect on FT.

### regime_shift — within rounding

REGIME_SHIFT delta moves from +$29,262 to +$29,223 (-$39 difference). Statistically zero. REGIME_SHIFT detector has its own per-symbol max (`WB_REGIME_SHIFT_MAX_PER_SYMBOL=1`) handled in `_maybe_fire_regime_shift`.

### Worst single trade — unchanged

Both runs show -$4,006 as the worst single FT/REGIME_SHIFT trade under Track A. Inside the -$5,000 acceptance floor.

---

## Phase 4 acceptance criteria — re-verified

| Criterion | Threshold | Original | New | Verdict |
|---|---|---|---|---|
| FT YTD delta | ≥ $40K | +$73,630 | +$73,630 | ✓ (1.8× threshold, unchanged) |
| REGIME_SHIFT YTD delta | ≥ $0 | +$29,262 | +$29,223 | ✓ |
| Combined YTD delta | ≥ $30K | +$106,842 | +$101,621 | ✓ (3.4× threshold) |
| Worst single trade | ≥ -$5K | -$4,006 | -$4,006 | ✓ |
| AMSS-class trace | informational | -$740 → -$580 | (not re-run; cooldowns unrelated to regime_shift exits) | — |

All quantitative criteria pass with materially the same margins as the original. No re-evaluation of variant slot allocation needed.

---

## What this means for the project

1. **Monday's Variant B live flip ships as scheduled** with `WB_MOVE_FIRESTORM_GATE_ENABLED=1 WB_MOVE_FIRESTORM_GATE_MIN_TICKS_PER_MIN=6000 WB_EXIT_TRACK_A_ENABLED=1` (per `cowork_reports/2026-05-29_variant_b_track_a_swap_impl_notes.md`).

2. **Sim cooldown removal was a correctness improvement that didn't change the Track A bottom line.** The cooldowns were silently restricting MOVE_STRIKE re-entries but not the regimes Track A targets. Removing them was the right call architecturally (sim/live parity) without disturbing the validated thesis.

3. **The -$5,221 MOVE_STRIKE delta is informational, not blocking.** MOVE_STRIKE is the V1-era setup that fires in only ~5% of arms (per Phase 1 anatomy). It's increasingly marginal relative to FT and REGIME_SHIFT, which are the active research/deployment targets.

4. **Component 3's "remediation" — raising sim's `WB_BT_MAX_TRIGGER_GAP_PCT` from 2.0 to 3.5%** — is still queued. That change would re-baseline every historical regression (VERO, ROLR, YTD compounding) and is a project-level decision. The current Track A re-baseline does NOT include that change.

---

## What's NOT included

- **Component 2 (bar-stream replay mode)**: still deferred to weekend. The Class A divergence on trade 1 (sim +$208 vs live -$169) remains unresolved.
- **STG-specific re-test on the new sim**: not run, because today's STG smoke (in `2026-05-29_stg_audit_resolution.md`) already confirmed cooldowns were not the blocker on STG. The Class B fix is the chase-cap (separate from cooldowns).
- **Chase-cap raise to 3.5%**: not shipped. Cowork should write a follow-up if the broader regression re-baseline is acceptable.
- **Live behavior changes**: zero. All work is sim-only.

---

## Cross-references

- Source directive: `cowork_reports/2026-05-29_sim_live_convergence_directive.md`
- Track A original results: `cowork_reports/2026-05-28_track_a_results.md`
- Component 1 + 3 commit (this work): commit `e132303`
- STG audit resolution: `cowork_reports/2026-05-29_stg_audit_resolution.md`
- Monday's Variant B swap impl: `cowork_reports/2026-05-29_variant_b_track_a_swap_impl_notes.md`
- New backtest JSONs:
  - `backtest_status/replay_subbot_YTD_F2_prime_baseline_no_cooldowns_2026-01-02_2026-05-28.json`
  - `backtest_status/replay_subbot_YTD_E_prime_track_a_no_cooldowns_2026-01-02_2026-05-28.json`
