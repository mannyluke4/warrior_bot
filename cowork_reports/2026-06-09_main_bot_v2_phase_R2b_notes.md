# Main Bot v2 Rebuild — Phase R2b Notes (Entry Path: RegimeShift)

**Date:** 2026-06-09
**Directive:** R2. **Status:** ✅ R2b shipped + smoke-tested, gated OFF. **R2 (entry) COMPLETE.**

## What changed (`bot_v3_hybrid.py`, all gated by `MOVE_STACK_ENABLED`)
1. Import `compute_stop_with_r_floor` from `exit_track_a` (self-gated on `WB_EXIT_TRACK_A_ENABLED`).
2. Config: `WB_REGIME_SHIFT_REQUIRE_ARMED` (1), `WB_REGIME_SHIFT_MAX_PER_SYMBOL` (1).
3. State: `state.regime_shift_armed_today` (set), `state.regime_shift_entries_per_symbol` (dict).
4. **`_move_risk_guards_block()`** — shared daily/risk guards (open_position, max-entries, box,
   daily-loss, consecutive-losses) so the bar-close regime path honors the same limits as
   `check_triggers` (which the per-tick path runs through). Inline, additive — does not touch
   `check_triggers`.
5. **`maybe_fire_regime_shift(symbol, bar)`** — port of `_maybe_fire_regime_shift` +
   `_open_regime_shift_position`: risk guards → `check_on_bar_close` fire → require_armed →
   per-symbol cap → FIRESTORM gate → entry-time cutoff → `compute_stop_with_r_floor(entry=bar.close,
   raw=bar.low)` → `enter_trade(_MoveArm(entry, stop, r, score=99), "regime_shift")`.
6. `on_bar_close_1m`: after the squeeze arm feed, add the symbol to `regime_shift_armed_today` when
   armed, then call `maybe_fire_regime_shift(symbol, bar)`.

## Smoke tests (pass)
- parse OK; import flag-off unchanged.
- fired + not-armed → blocked (require_armed) ✓
- fired + armed → routes to `enter_trade("regime_shift", entry=5.00, stop=4.60, r=0.40, score=99)` ✓
- over per-symbol cap → blocked ✓ · no-fire → no entry ✓ · open-position → blocked by risk guard ✓

## Deviations / deferred
- Sizing reuses the main bot's `enter_trade` (AvailableFunds), not the sub-bot's `_compute_qty`.
- Entry stop runs through Track A's R-floor (the entry-side piece); the full exit framework is R3.
- **Deferred (minor, not blocking R2):** fade-environment gate (off by default in the sub-bot too)
  and stay-armed MOVE_STRIKE continuation. Will fold into R3/cleanup if validation wants them.
- **New guard proposed by the 2026-06-09 avoidable-trades audit:** a halt-count entry gate (block
  after a symbol halts ≥N times today). Not in the original directive; strong candidate to add
  before R5 since today's worst avoidable losses were serially-halted names (CCTG 34 halts).

## Next: R3 — Exit path (Track A), **including the CCTG stop investigation**
Route move_strike/regime_shift positions through `exit_track_a` (phased drawdown + 1.5R partial +
HWM runner + R-floor). First task in R3: verify the exit honors the stop on a fast decline
(the CCTG halt was unfillable, but confirm there's no logic gap on a *tradeable* drop).
