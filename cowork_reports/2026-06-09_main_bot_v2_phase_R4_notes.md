# Main Bot v2 Rebuild — Phase R4 Notes (REENTRY-loss gate)

**Date:** 2026-06-09. **Directive:** R4. **Status:** ✅ shipped + smoke-tested, gated OFF.
**This completes the code build (R1–R4). Next is R5 paper validation (runtime).**

## What changed (`bot_v3_hybrid.py`, gated)
1. Config: `WB_MOVE_REENTRY_LOSS_GATE_ENABLED` (off), `WB_MOVE_REENTRY_LOSS_GATE_WINDOW_MIN` (30);
   loss-class prefixes = `move_hwm_exit`, `move_stop_prox_bail`, `move_hard_stop`,
   `regime_shift_hard_stop`, `regime_shift_drawdown_floor` (added the Track A floor vs the sub-bot
   list for parity with R3's exit reasons).
2. State: `state.last_exit_reason_by_symbol` = {symbol: (reason, exit_minute_et)}.
3. `_move_exit_and_record(symbol, price, qty, reason)` — wraps `exit_trade` for full closes and
   records the reason+minute; all `_move_stack_exit` full-close paths route through it (the 1.5R
   partial does NOT record — position still open).
4. `_reentry_loss_gate_blocks(symbol)` — blocks if the last exit was loss-class and within the
   window. Wired into both `maybe_enter_move_strike` and `maybe_fire_regime_shift` (after FIRESTORM).

## Smoke tests (pass)
- no prior exit → allow · loss exit 5min ago → BLOCK · loss exit 40min ago → allow (outside window)
- winning exit (`regime_shift_partial`) 2min ago → allow (not loss-class) · record written correctly.

## ✅ BUILD COMPLETE — move-stack fully ported, all gated behind `WB_MOVE_STACK_ENABLED`
| Phase | What | Commit |
|---|---|---|
| R1 | MovementStrike + RegimeShift + FirestormTrigger detectors (+ squeeze-arm correction) | 0815718 / ac3c79e |
| R2 | Entry: MOVE_STRIKE (per-tick) + RegimeShift (bar-close) → enter_trade | 08f83a6 / 6fd89e1 |
| R3 | Exit: Track A drawdown floor / hard stop / force-flatten / 1.5R partial + HWM trail | e55218c |
| R4 | REENTRY-loss gate | (this) |

## R5 activation (NOT yet flipped — this is the runtime validation phase)
The build is one config block away from paper validation. To start R5, set in `.env`:
```
WB_MOVE_STACK_ENABLED=1
WB_SQUEEZE_ENABLED=0            # retire squeeze trading (arm still produced for the move-stack)
WB_REGIME_SHIFT_ENABLED=1
WB_MOVE_FIRESTORM_GATE_ENABLED=1   # Variant A's defensive gate (validated winner)
WB_EXIT_TRACK_A_ENABLED=1          # Variant B's R-floor + phased drawdown (fixes tight-R oversize)
WB_MOVE_REENTRY_LOSS_GATE_ENABLED=1  # Variant C
WB_EOD_FORCE_FLATTEN_ENABLED=1
```
…then restart the main bot. Recommend flipping at the **next session open (6/10)** for a clean
full paper day, not a cold mid-evening start. Acceptance criteria (directive R5): +$1k net over
≥3 days, no >3% single-day loss, entries/exits behave per spec, no infra breakage, no Error-201.

## Remaining follow-ups (non-blocking, fold into R5 tuning)
- hh_count bar-close tracking (R3 deferral — HWM trail currently uses base 25% dd).
- fade-environment gate + stay-armed continuation (R2 deferrals, off by default in sub-bot too).
- Halt-count entry gate (from the 2026-06-09 avoidable-trades audit — strong add before real money).
