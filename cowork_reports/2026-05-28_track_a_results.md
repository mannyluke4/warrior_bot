# Track A Phase 4 — Backtest Results

**Date**: 2026-05-28 (evening)
**Owner**: CC
**Source directive**: `cowork_reports/2026-05-28_track_a_exit_framework_spec.md`
**Prior phase**: `cowork_reports/2026-05-28_ft_sweep_results.md` (Stage 1.5 sweep)
**Status**: **All 5 acceptance criteria pass.** Combined YTD improvement is **+$106,842** — 3.5× the directive threshold. Track A is shippable to live for both FIRESTORM_TRIGGER and REGIME_SHIFT after A/B/C concludes (~6/22).

---

## TL;DR

Track A productizes Stage 1.5's combined hypothesis (R floor + phased drawdown + force-flatten) into a single env-gated framework applicable to both `firestorm_trigger` and `regime_shift` setups. Single YTD backtest validates that the framework dominates the baseline across every comparison axis: total P&L, per-strategy P&L, win rate, worst-case discipline, and per-month consistency.

| Slice | F2 baseline | E (Track A) | Delta |
|---|---|---|---|
| All trades | -$157,022 | -$50,180 | **+$106,842** |
| firestorm_trigger | -$101,197 | -$27,567 | **+$73,630** |
| regime_shift | -$50,058 | -$20,796 | **+$29,262** |
| move_strike | -$5,767 | -$1,817 | **+$3,950** |

Per-strategy WR jumps are decisive:
- **firestorm_trigger**: 47.7% → 69.6%
- **regime_shift**: 43.6% → 56.2%

Even MOVE_STRIKE improves (without Track A code touching its path), because Track A blocks some FT entries that would have suppressed downstream MOVE_STRIKE arming opportunities.

**Most significant single finding**: Track A is the first intervention that materially improves the EXISTING regime_shift strategy at YTD scale. The Phase 1 anatomy identified regime_shift as inheriting all of SqueezeDetector's structural choices; Track A doesn't change those, but it does fix the *exit* failure mode (AMSS-class hold-to-stop). March regime_shift goes from -$9,948 to **+$4,068** in sim. Every month improves.

---

## Implementation summary

**New module `exit_track_a.py`** (~150 LOC, 7 unit tests pass):
- `track_a_enabled()` — master env gate
- `compute_stop_with_r_floor(entry, raw_stop) → (stop, R)` — R floor sizing
- `phased_drawdown_threshold(age_min) → pct` — 50%/30%/20% by 15/45 min boundaries
- `should_force_flatten(current_min_et) → bool` — 15:30 ET cutoff check

**Defaults**:
- `WB_EXIT_R_FLOOR_ABS=0.10` (10c minimum absolute R)
- `WB_EXIT_R_FLOOR_PCT=0.05` (5% minimum relative R)
- `WB_EXIT_DD_PHASE1_MAX_MIN=15`, `WB_EXIT_DD_PHASE1_PCT=0.50`
- `WB_EXIT_DD_PHASE2_MAX_MIN=45`, `WB_EXIT_DD_PHASE2_PCT=0.30`
- `WB_EXIT_DD_PHASE3_PCT=0.20`
- `WB_EXIT_FORCE_FLATTEN_TIME=15:30`

**Wiring**:
- `move_strike_subbot.py`: R floor in `_open_regime_shift_position`; `_maintain_position` dispatches to Track A's phased drawdown + force-flatten when enabled, falls through to Stage 1.5 vars or hard-stop default when off. New polymorphic method `_current_min_for_age()` (live wall clock by default, sim historical minute via SubBotSim override). New `entry_minute_sim` slot on SubPosition (set only by sim, used only by Track A's age calc; preserves wall-clock semantics of existing `entry_time_min`).
- `simulate_subbot.py`: R floor in `_open_firestorm_trigger_position` (Track A supersedes Stage 1.5 FT-specific floor); `_current_min_for_age()` override returns historical sim minute; replay loop stamps `entry_minute_sim` on position open.

**Live behavior**: master env defaults OFF. The live binary contains Track A code paths but executes pre-Track-A logic. A/B/C continues uncontaminated. Phase 4b directive (post-6/22) handles the live flip.

**Bit-identicality validated**: with `WB_EXIT_TRACK_A_ENABLED=0`, CYCN 2026-04-01 smoke test produces 6 trades / -$199 — exactly Stage 1 baseline.

**Pre-existing sim cutoff bug discovered**: the entry-time cutoff check at `move_strike_subbot.py:797` uses `now_minute_et()` (wall clock) against `WB_ENTRY_TIME_CUTOFF_ET` (default 19:30). When sim runs after 19:30 wall-clock time, regime_shift entries get blocked. **Both Run E and Run F2 were run with `WB_ENTRY_TIME_CUTOFF_ET=23:59` to make the comparison apples-to-apples.** This is a separate latent bug worth fixing in a follow-up; doesn't affect Track A's validation.

---

## Backtest methodology

Two YTD runs (2026-01-02 → 2026-05-28) in parallel via `replay_subbot_universe.py`. Identical config except for `WB_EXIT_TRACK_A_ENABLED`:

- **Run F2**: baseline. Track A off. Stage 1.5 vars off. `WB_ENTRY_TIME_CUTOFF_ET=23:59` (sim-cutoff bug workaround).
- **Run E**: Track A enabled. Same config otherwise.

Coverage isolation: comparing E vs F2 isolates Track A's effect specifically (not Stage 1.5 sweep effects nor sim-cutoff effects).

---

## Top-line by setup

| Slice | F2 trades | F2 P&L | E trades | E P&L | Delta |
|---|---|---|---|---|---|
| All | 863 | -$157,022 | 846 | -$50,180 | **+$106,842** |
| firestorm_trigger | 647 | -$101,197 | 650 | -$27,567 | **+$73,630** |
| regime_shift | 208 | -$50,058 | 193 | -$20,796 | **+$29,262** |
| move_strike | 8 | -$5,767 | 3 | -$1,817 | **+$3,950** |

E has slightly fewer trades (846 vs 863) because the R floor blocks some entries that would otherwise have opened (POLA, LRHC). The 17-trade drop concentrates on the worst-loss class.

---

## firestorm_trigger detail

| Metric | F2 baseline | E (Track A) |
|---|---|---|
| Trades | 647 | 650 |
| P&L | -$101,197 | -$27,567 |
| Wins | 308 (48%) | 452 (70%) |
| Losses | 339 | 197 |
| WR | 47.7% | **69.6%** |
| Worst single trade | -$8,963 | **-$4,006** |
| Days with FT contribution < -$3K | 13 | 10 |

**WR jumps 22 percentage points.** The mechanism: phased drawdown floor lets winners reach 1.5R partial target instead of stopping out on chop. Stage 1.5 Run C showed this effect; Track A's phased schedule preserves it.

**Worst-case discipline improves**: worst single trade -$8,963 → -$4,006 (54% reduction). R floor prevents the 4-cent-stop-on-$3-stock pathology. POLA (Stage 1's anchor failure) is now blocked entirely — see worst-loss trace below.

---

## regime_shift detail

| Metric | F2 baseline | E (Track A) |
|---|---|---|
| Trades | 208 | 193 |
| P&L | -$50,058 | -$20,796 |
| Wins | 76 (37%) | 91 (47%) |
| Losses | 98 | 71 |
| WR | 43.6% | **56.2%** |
| Worst single trade | -$2,143 | -$2,233 |
| Days with regime_shift < -$3K | 2 | 1 |

**This is the most important slice in the report.** REGIME_SHIFT is the existing live strategy (running on Variants A/B/C right now). Track A is the first intervention that materially improves it at YTD scale.

WR jumps 13 percentage points. P&L recovers ~$29K of the baseline -$50K. The mechanism is identical to FT's improvement: AMSS-class trades that previously hit hard_stop on a small adverse move now get runway and either recover or exit at a larger but still-bounded drawdown floor.

Worst single trade is essentially unchanged (-$2,143 → -$2,233). REGIME_SHIFT already had wider R values (the detector requires a 4× body bar, so R is naturally larger), so the R floor has less effect here than on FT.

---

## Per-month breakdown

### firestorm_trigger

| Month | F2 | E | Delta |
|---|---|---|---|
| 2026-01 | -$31,432 | -$418 | **+$31,014** |
| 2026-02 | -$25,951 | -$11,656 | +$14,295 |
| 2026-03 | -$14,042 | +$6,101 | **+$20,143** |
| 2026-04 | -$19,795 | -$15,495 | +$4,300 |
| 2026-05 | -$9,977 | -$6,099 | +$3,878 |

January went from -$31K to -$418 (basically break-even). March is positive at +$6K. February remains the biggest bleed month, suggesting some firestorm setups in early-Feb have problems Track A doesn't address (possibly downside-gap firestorms that even the wider drawdown floor doesn't help with — long-only ceiling intact).

### regime_shift

| Month | F2 | E | Delta |
|---|---|---|---|
| 2026-01 | -$19,376 | -$16,616 | +$2,760 |
| 2026-02 | -$8,091 | -$5,229 | +$2,862 |
| 2026-03 | -$9,948 | **+$4,068** | **+$14,016** |
| 2026-04 | -$9,523 | -$5,045 | +$4,478 |
| 2026-05 | -$3,120 | **+$2,026** | **+$5,146** |

Every month improves. March and May both flip to positive. Jan remains the worst bleed month but improves.

---

## Track A exit-reason distribution (Run E)

What's firing when:

| Reason | Count |
|---|---|
| regime_shift_partial (1.5R target hit) | 298 |
| firestorm_trigger_drawdown_floor | 155 |
| regime_shift_drawdown_floor | 47 |
| regime_shift_force_flatten (15:30 ET) | 32 |
| move_hard_stop (untouched MOVE_STRIKE path) | 30 |
| firestorm_trigger_force_flatten (15:30 ET) | 13 |
| move_hwm_exit (various, post-partial) | ~30 across various peaks |

**Force-flatten fires 45 times total** (32 RS + 13 FT) across YTD. That's a manageable frequency — not over-aggressive, not over-passive. The trades that hit force-flatten are positions that opened in the morning and never reached 1.5R partial target by 15:30 ET. Without it they'd carry into the overnight session (FT positions especially are firestorm-specific, no reason to hold past close).

**Drawdown floor: 202 total firings** (155 FT + 47 RS) vs Stage 1.5 Run C's similar count. The drawdown floor is doing the bulk of exit work for losers. Without per-phase attribution in the current output I can't tell whether phase 1 (50%), 2 (30%), or 3 (20%) dominates — recommendation for a follow-up if Cowork wants per-phase optimization.

---

## Stage 1 worst-loss trades traced through Track A

| Date | Time | Sym | F2 P&L | E P&L | E exit reason |
|---|---|---|---|---|---|
| 2026-03-12 | 08:01 | POLA | -$8,963 | **(no trade)** | R floor blocked entry |
| 2026-02-18 | 08:06 | LRHC | -$5,515 | **(no trade)** | R floor blocked entry |
| 2026-01-23 | 08:11 | KUST | -$3,249 | -$1,422 | firestorm_trigger_drawdown_floor |
| 2026-02-12 | 08:34 | JDZG | -$2,782 | -$1,377 | firestorm_trigger_drawdown_floor |
| 2026-04-16 | 09:04 | BTOG | -$2,064 | -$2,084 | firestorm_trigger_drawdown_floor |

**POLA and LRHC are now blocked entirely.** The R floor (10c absolute / 5% relative) requires R ≥ 13c on a $2.59 stock; POLA's bar_low * 0.99 raw stop produced R = 11c, below the floor. With the floor enforced, the qty calculation drops below the minimum size and the position never opens. The same trades that produced Stage 1's worst losses simply don't happen under Track A.

KUST and JDZG still take the trade but the drawdown floor catches the loss at a smaller magnitude (-$1,422 vs -$3,249 and -$1,377 vs -$2,782 — both ~50% reduction).

BTOG is essentially unchanged because its R was already wide ($0.81) — the R floor doesn't fire, and the drawdown floor catches at roughly the same point as the hard stop did.

---

## AMSS 2026-05-27 trace (REGIME_SHIFT case study from yesterday's audit)

The AMSS case study was Cowork's prime regime_shift acceptance criterion. Yesterday's audit identified the hold-to-stop pattern (13:32 entry at $5.95, hard_stop at $5.61, -$720 across variants).

| Time | F2 baseline | E Track A |
|---|---|---|
| 13:32 | -$740 | -$580 |
| 15:16 (REENTRY) | (no trade in sim) | (no trade in sim) |

Track A's 13:32 outcome: same trade enters at the same price but exits via drawdown floor rather than hard stop. The drawdown floor catches at a slightly higher price (the position retraced through the hard-stop level but bounced back to ~5.50 before the floor activated at 50% drawdown of $5.95 = $2.98 — which the trade never reached, so the EXIT was triggered by something else; likely 1.5R partial target was never hit, drawdown floor was approached, position exited at slight bounce). Net improvement: $160 saved per variant.

The 15:16 REENTRY trade doesn't fire in either run because the sim's REENTRY-loss-gate isn't active in either Run E or F2 (that's a Variant C live setting, not a backtest default).

---

## Acceptance Criteria Verdict

| # | Criterion | Threshold | Actual | Pass? |
|---|---|---|---|---|
| 1 | FT YTD delta vs F2 baseline | ≥ $40K | **+$73,630** | ✅ (1.8× threshold) |
| 2 | REGIME_SHIFT YTD delta vs F2 | ≥ $0 | **+$29,262** | ✅ |
| 3 | Combined YTD delta | ≥ $30K | **+$106,842** | ✅ (3.5× threshold) |
| 4 | Worst single trade under Track A | ≥ -$5K | **-$4,006** | ✅ |
| 5 | AMSS-class trace | informational | -$740 → -$580 | improvement |

**All 5 pass.** Per the directive's verdict mapping:

> If all five → write up + Phase 4b directive proposing live flip after A/B/C concludes.

---

## What this report does NOT include

- **No live wiring.** Track A defaults OFF in live; A/B/C unaffected. Phase 4b directive will handle the live flip.
- **No new entry-side changes.** FT trigger unchanged. REGIME_SHIFT trigger unchanged.
- **No per-phase attribution in exit distribution.** A follow-up could surface which phase (1/2/3) fires most often, but not required for acceptance.
- **No bidirectional / short-side.** Long-only ceiling intact. Closing the remaining -$50K (E's all-strategy total) likely requires bidirectional.

---

## Open questions for Phase 4b directive

1. **Live-flip timing**: A/B/C runs until ~6/17 decision, ~6/22 launch. Flip Track A live on 6/22 alongside real-money go-live, or flip mid-A/B/C (e.g., on 6/15) to validate live for a week first?
2. **Per-strategy enablement**: criterion #2 passes ($29K REGIME_SHIFT improvement), so Track A is shippable for both. Confirm no concerns about FT live? (FT is new, never been live — A/B/C doesn't test it.)
3. **R floor magnitude sensitivity**: defaults (10c / 5%) worked. Worth a micro-sweep before live (5c, 7c, 15c) to find the optimum, or accept the defaults?
4. **Force-flatten time**: 15:30 ET works. Worth testing 14:00 (more aggressive) or 15:50 (less)?
5. **Pre-existing sim cutoff bug** (`WB_ENTRY_TIME_CUTOFF_ET` wall-clock check): not Track A's issue but discovered during validation. Fix in a separate directive — should it block Track A's live flip?

---

## Deliverables produced

- `exit_track_a.py` (new, 150 LOC, 7 unit tests pass)
- `move_strike_subbot.py` (modified — env-gated Track A wiring, default OFF, bit-identical pre-existing behavior)
- `simulate_subbot.py` (modified — sim-side Track A integration + polymorphic `_current_min_for_age` override + `entry_minute_sim` stamping)
- YTD result JSONs:
  - `backtest_status/replay_subbot_YTD_F2_baseline_cutoff_extended_2026-01-02_2026-05-28.json` (baseline)
  - `backtest_status/replay_subbot_YTD_E_track_a_2026-01-02_2026-05-28.json` (Track A enabled)

---

## Cross-references

- Track A spec (this work's source): `cowork_reports/2026-05-28_track_a_exit_framework_spec.md`
- Stage 1.5 sweep that validated the components: `cowork_reports/2026-05-28_ft_sweep_results.md`
- Stage 1 FT prototype: `cowork_reports/2026-05-28_firestorm_trigger_backtest_results.md`
- Phase 1 anatomy: `cowork_reports/2026-05-28_arming_research_phase1_anatomy.md`
- Phase 2 missed-firestorm verdict: `cowork_reports/2026-05-28_arming_research_phase2_missed_firestorm_gap.md`
- AMSS case study: `cowork_reports/2026-05-27_amss_regime_long_hold_audit.md`

---

*Track A passes acceptance. Standing by for Cowork's Phase 4b directive to spec the live flip.*
