# Main Bot v2 Rebuild — Phase R2a Notes (Entry Path: MOVE_STRIKE)

**Date:** 2026-06-09 (early)
**Directive:** `cowork_reports/2026-06-08_main_bot_rebuild_directive.md` (R2)
**Status:** ✅ R2a (MOVE_STRIKE entry) shipped + smoke-tested, gated OFF.
**Remaining in R2 → R2b:** RegimeShift firing, fade-environment gate, stay-armed continuation.

## Architecture (corrected model from R1)
SqueezeV2 **arms** (bar-close) → MovementStrike **triggers** (intra-bar, every tick while
armed) + supplies the consolidation stop → route to the main bot's `enter_trade()` (reuses
AvailableFunds sizing + `_verify_fill_with_retry` + `_presubmit_bp_check` + single-position
`state.open_position`). No squeeze-arm replacement — squeeze is the arming engine.

## What changed (`bot_v3_hybrid.py`, all gated by `MOVE_STACK_ENABLED`)
1. **Config** (after the move-stack import): `WB_MOVE_FIRESTORM_GATE_ENABLED` (off),
   `WB_MOVE_FIRESTORM_GATE_MIN_TICKS_PER_MIN` (6000), `WB_BT_MOVE_CHASE_PCT` (2.0),
   `WB_BT_MOVE_MAX_BELOW_ARM_PCT` (0).
2. **State:** `state.move_prev_arm_state` (tracks squeeze arm across bars for MovementStrike reset).
3. **`_MoveArm`** adapter (trigger_high/stop_low/r/score/size_mult) so move entries reuse `enter_trade`.
4. **`_move_firestorm_blocks`** — FIRESTORM quiet-bar gate (Variant A), ported.
5. **`maybe_enter_move_strike(symbol, price)`** — faithful port of `_maybe_enter`: entry-time
   cutoff → require squeeze arm → `ms.update_and_check` (per-tick) → consolidation-stop check →
   FIRESTORM gate → chase-cap + below-arm filter (arm preserved on skip) → `enter_trade(symbol,
   _MoveArm(...), "move_strike")` → consume arm.
6. **`check_triggers`:** move-stack trigger block added after the daily/risk guards, before the
   squeeze block; returns if it entered (single-position).
7. **`on_bar_close_1m`:** squeeze feed gate opened to `(SQ_ENABLED OR MOVE_STACK_ENABLED)` so the
   arm is produced when squeeze trading is off; on a None→armed transition, `MovementStrike.reset_history()`
   (mirrors sub-bot:795-801).

## Smoke tests (pass)
- parse OK; import with flag **off** unchanged (`MOVE_STACK_ENABLED=False`).
- Entry decision (flag on, `enter_trade` + `ms` mocked):
  - clean trigger above stop, within chase cap → routes to `enter_trade("move_strike", trigger=5.10,
    stop=5.00, r=0.10, score=9.0)`, arm consumed ✓
  - no arm → no entry ✓
  - +4% chase (cap 2%) → SKIP, arm preserved ✓

## Notes / deviations
- Verified `MovementStrike` docstring: must be fed **every tick** — handled by `check_triggers`
  calling `maybe_enter_move_strike` per tick (feeds `ms` while armed); reset on arm transition so
  the rolling average is post-arm only.
- Did **not** port the sub-bot's Alpaca submission / `_compute_qty` — directive says reuse the
  main bot's IBKR `enter_trade` sizing (AvailableFunds). The `_MoveArm` adapter bridges them.
- `.env` unchanged → flag off → cron launches the unchanged squeeze/sub-bot stack.
- REENTRY-loss gate hook is marked for R4; fade gate + stay-armed + regime-shift are R2b.

## Next: R2b — RegimeShift firing in `on_bar_close_1m` (`_maybe_fire_regime_shift`) + fade gate.
