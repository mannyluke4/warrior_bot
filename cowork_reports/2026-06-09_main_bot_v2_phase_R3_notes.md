# Main Bot v2 Rebuild — Phase R3 Notes (Exit Path: Track A + HWM)

**Date:** 2026-06-09. **Directive:** R3. **Status:** ✅ shipped + smoke-tested, gated OFF.

## CCTG stop investigation (the R3 pre-task — RESOLVED)
Confirmed in code + tape: CCTG's "blow past the stop" was a **52-min volatility halt**
(10:30 $4.22 → reopen 11:22 $1.91), not a logic gap. With Track A **off** (Variant A) the exit
is the raw hard stop `price ≤ $3.66`; with Track A **on** (Variant B) it's the **% drawdown floor**
(~20% after 45 min ≈ $3.86). CCTG never *traded* in either range before the halt, so **both
frameworks were correct but un-fillable**. The bot detected the halt and exited on the first
post-reopen tick. No fix needed. (Verified the same logic now lives in `_move_stack_exit`.)

## What changed (`bot_v3_hybrid.py`, gated by `MOVE_STACK_ENABLED`)
1. Imports: `track_a_enabled`, `phased_drawdown_threshold`, `should_force_flatten` from
   `exit_track_a`; `HWMExitConfig` + `evaluate as hwm_evaluate` from `hwm_exit`; module-level
   `_MOVE_HWM_CFG`. **Key: `hwm_evaluate` is read-only and dict-compatible** → the main bot's
   position dict is passed straight in, no adapter.
2. Config: `WB_REGIME_SHIFT_TARGET_R` (1.5), `WB_REGIME_SHIFT_PARTIAL_PCT` (0.9).
3. `manage_exit` dispatch: `setup_type in (move_strike, regime_shift)` → `_move_stack_exit`. The
   5-min bail timer is skipped for move-stack (HWM's own 30-min noact-bail handles it, per parity).
4. **`_move_stack_exit`** — port of `_maintain_position`:
   - lazy-init/maintain `cum_low`, `entry_time_min`, `hh_count`, `move_partial_fired` on the dict.
   - **regime_shift pre-partial:** Track A force-flatten → phased-drawdown floor (Track A on) /
     hard stop (Track A off) → 1.5R partial. No HWM trail until partial fires.
   - **move_strike + post-partial runner:** `hwm_evaluate` (its own hard stop + stop-prox/noact
     bails + adaptive HWM trail).
5. **`_fire_move_partial`** — sells 90% at 1.5R, raises stop to BE, keeps the runner under HWM;
   mirrors the squeeze core/runner partial (`exit_trade(partial_qty)` then shrink `pos['qty']`).

## Smoke tests (all pass)
- parse + import (off unchanged).
- regime hard-stop (Track A off) `price≤stop` → `regime_shift_hard_stop` ✓
- regime hold (above stop, below target) → HOLD ✓
- regime 1.5R partial → fires 360/400, runner=40, `move_partial_fired=True`, stop→BE ✓
- regime Track A: dd 7.5%<50% → HOLD; dd 52.5%≥50% → `regime_shift_drawdown_floor` ✓
- regime force-flatten after 15:30 → `regime_shift_force_flatten` ✓
- move_strike `price≤stop` → `move_hard_stop`; HWM trail (peak 5.0, 25% dd) → `move_hwm_exit` ✓

## Deviations / deferred
- `hh_count` defaults to 0 (higher-high tracking on bar closes not yet ported). Effect: the HWM
  trail uses the base 25% drawdown rather than widening to 50% on multi-HH runners — slightly
  tighter, conservative. **Follow-up:** port the per-symbol HH counter on bar closes.
- Still deferred from R2: fade-environment gate (off by default) + stay-armed continuation.
- Proposed (from 2026-06-09 avoidable-trades audit): halt-count entry gate — add before R5.

## Status: entry (R1+R2) + exit (R3) = the move-stack is functionally complete.
## Next: R4 — REENTRY-loss gate (Variant C), then R5 paper validation (needs .env activation + restart).
