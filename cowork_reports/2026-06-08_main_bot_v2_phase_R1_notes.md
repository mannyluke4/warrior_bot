# Main Bot v2 Rebuild — Phase R1 Notes (Detector Swap)

**Date:** 2026-06-08 (evening)
**Directive:** `cowork_reports/2026-06-08_main_bot_rebuild_directive.md`
**Phase:** R1 — detector swap (MovementStrike + RegimeShift + FirestormTrigger)
**Status:** ✅ shipped + smoke-tested. Gated OFF by default.

## What changed (`bot_v3_hybrid.py`, 3 edits)

1. **Flag + conditional import** (after the WaveBreakout gated import, ~line 113):
   - `MOVE_STACK_ENABLED = os.getenv("WB_MOVE_STACK_ENABLED", "0") == "1"`
   - When ON: `from movement_strike import MovementStrike`, `from firestorm_trigger import
     FirestormTrigger`, `from move_strike_subbot import RegimeShiftDetector`.
   - **When OFF (default): import graph + runtime behavior are byte-identical to the current
     squeeze build.** No new top-level imports execute. Squeeze path untouched = fallback.

2. **State dicts** (`BotState.__init__`, after `ct_detectors`):
   - `self.move_strikes`, `self.regime_shift_detectors`, `self.firestorm_triggers` (all `{}`).

3. **`init_detectors(symbol)`** (after the CT block): gated block that instantiates, per symbol,
   `MovementStrike(WB_BT_MOVE_LOOKBACK=5, WB_BT_MOVE_MULT=2.0, WB_BT_MOVE_STOP_LOOKBACK=10)`,
   and — if `WB_REGIME_SHIFT_ENABLED=1` — `RegimeShiftDetector(ratio=4.0, baseline=5,
   require_green=1)`. `FirestormTrigger` only if `WB_MOVE_FIRESTORM_TRIGGER_ENABLED=1`
   (default off — the FIRESTORM *gate* is a separate quiet-bar entry filter, added in R2).
   Mirrors `move_strike_subbot._ensure_symbol` (sub-bot:602-614) so R2/R3 consume
   identically-configured detectors.

## Smoke tests (all pass)
- `ast.parse` clean.
- Import with flag **off**: OK, `MOVE_STACK_ENABLED=False` (unchanged behavior).
- Import with flag **on**: OK, all three classes load.
- `init_detectors('TESTQ')` with flag on: MovementStrike + RegimeShiftDetector created with
  correct params; FirestormTrigger correctly None (gated off); re-init idempotent (same object).
- `bot_v3_hybrid` has a `__main__` guard (line 5369) → import is side-effect-free.

## Spec deviations / notes
- Directive cited `move_strike_subbot.py:540-570` for the detector init pattern; actual is
  `_ensure_symbol` at **:596-614** (used the real location).
- Used a **conditional import** (mirroring the existing WaveBreakout gate at :110-113) instead
  of a top-level import, so the off-path is zero-risk. Recommended pattern for the rest of the
  rebuild.
- `RegimeShiftDetector` is imported from `move_strike_subbot.py` (verified clean `__main__`
  guard, no import side effects). **TODO (rebuild cleanup):** extract it to its own
  `regime_shift_detector.py` and import from there in both bots — deferred to avoid touching the
  live sub-bot during the A/B/C test.
- R1 is detector *instantiation* only. Wiring detectors to the tick/bar handlers is R2 (entry
  path) / R3 (exit path).
- `.env` intentionally NOT modified — `WB_MOVE_STACK_ENABLED` stays unset (off) until R5 paper
  validation, so tomorrow's 2 AM cron launch runs the unchanged squeeze/sub-bot stack.

## New env knobs (all default OFF/safe)
`WB_MOVE_STACK_ENABLED` (master, off) · `WB_MOVE_FIRESTORM_TRIGGER_ENABLED` (off) ·
reuses existing `WB_BT_MOVE_*`, `WB_REGIME_SHIFT_*`, `WB_MOVE_FIRESTORM_GATE_*`.

## ⚠️ ARCHITECTURE CORRECTION (R1 amendment, 2026-06-09) — directive model is wrong

While reading the entry path for R2, found that the directive's **"REPLACE SqueezeDetectorV2
arming WITH MovementStrike + RegimeShift"** (directive §"What the main bot REPLACES") is
**inaccurate**. Verified in `move_strike_subbot.py`:
- `self.detectors[symbol]` is a **`SqueezeDetectorV2`** (:228, same class as main bot) created
  unconditionally in `_ensure_symbol`.
- `_maybe_enter` (:1405) only proceeds when **`det.armed is not None`** — i.e. it requires a
  **squeeze arm**. `det.on_bar_close_1m` is fed purely to set `det.armed` (:789 comment:
  *"this can set det.armed if conditions met"*).
- **MovementStrike does NOT arm** — `ms.update_and_check` is the intra-bar *trigger*, and
  `ms.get_consolidation_stop()` supplies the stop. The squeeze detector supplies the arm
  (entry level, score).

**So the real architecture is: SqueezeV2 ARMS → MovementStrike TRIGGERS → (parallel) RegimeShift
fires on bar-close → Track A exits.** The squeeze detector is *repurposed as the arming engine*,
not replaced. Its own entry/exit logic is bypassed (only `.armed` is consumed).

**Consequence:** the directive's plan to set `WB_SQUEEZE_ENABLED=0` would **kill arming → zero
move-strike entries.** Fixed in R1: `init_detectors` now creates the SqueezeDetectorV2 when
`SQ_ENABLED OR MOVE_STACK_ENABLED` (the arm is produced; squeeze's own trade paths stay gated
off via `SQ_ENABLED`). Smoke-tested: SQ-off + move-stack-on still yields an arming detector;
both-off leaks nothing.

**Directive needs updating** (Cowork): the "REPLACES SqueezeDetectorV2 arming" row is wrong —
squeeze arming is KEPT (arm-only). R2/R3 are designed on the corrected model below.

## Next: R2 — entry path swap (on the CORRECTED model)
Add `_maybe_enter_move_strike` + `_maybe_fire_regime_shift` to `bot_v3_hybrid.py`, gate order
FIRESTORM → REENTRY-loss → fade(off) → chase-cap → below-arm → BP-check → submit, reusing
`_verify_fill_with_retry` + AvailableFunds sizing.
