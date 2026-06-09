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

## Next: R2 — entry path swap
Add `_maybe_enter_move_strike` + `_maybe_fire_regime_shift` to `bot_v3_hybrid.py`, gate order
FIRESTORM → REENTRY-loss → fade(off) → chase-cap → below-arm → BP-check → submit, reusing
`_verify_fill_with_retry` + AvailableFunds sizing.
