# REENTRY Loss-Gate Broadening — Impl Notes

**Date**: 2026-05-27 (evening)
**Owner**: CC
**Source directive**: `cowork_reports/2026-05-27_reentry_loss_gate_broaden_directive.md`
**Supersedes**: `cowork_reports/2026-05-27_reentry_hwm_gate_impl_notes.md` (HWM-narrow scope, commit `58dd095`, replaced before its first cron run)

---

## TL;DR

Variant C's REENTRY gate is broadened from the HWM-only scope shipped this
morning to **all loss-class prior exits**. The motivation is today's AMSS
15:16 REENTRY GREEN disaster (-$577 in 1 second after a `regime_shift_hard_stop`),
which the HWM-narrow gate would have missed by one reason-string.

Clean rename, no migration burden — the HWM-narrow gate never saw a production
cron run.

---

## Code changes

### `move_strike_subbot.py`

- `__init__` (~line 313): renamed `reentry_hwm_gate_enabled` →
  `reentry_loss_gate_enabled`, `reentry_hwm_gate_window_min` →
  `reentry_loss_gate_window_min`. Env vars renamed
  `WB_MOVE_REENTRY_HWM_GATE_ENABLED` → `WB_MOVE_REENTRY_LOSS_GATE_ENABLED`,
  `WB_MOVE_REENTRY_HWM_GATE_WINDOW_MIN` → `WB_MOVE_REENTRY_LOSS_GATE_WINDOW_MIN`.
- `_try_fire_green_reentry` (~line 869): gate scope broadened from
  `prev_reason.startswith("move_hwm_exit")` to a 4-prefix any-of:
  - `move_hwm_exit` (kept)
  - `move_stop_prox_bail`
  - `move_hard_stop`
  - `regime_shift_hard_stop`
- Log line renamed `REENTRY_HWM_GATE_BLOCK` → `REENTRY_LOSS_GATE_BLOCK` and
  reformatted: `<symbol> reason=<prior_exit_reason> window_age_min=<minutes>`.
  Example: `REENTRY_LOSS_GATE_BLOCK AMSS reason=regime_shift_hard_stop window_age_min=2`.

### `daily_run_v3.sh`

- Variant C launch line updated to set `WB_MOVE_REENTRY_LOSS_GATE_ENABLED=1`
  and `WB_MOVE_REENTRY_LOSS_GATE_WINDOW_MIN=30`. Comment block updated to
  reference the broadening directive.

### `scripts/abc_compare_daily.py`

- `REENTRY_HWM_GATE_BLOCK_RE` → `REENTRY_LOSS_GATE_BLOCK_RE`, regex updated
  to match the new `reason=` / `window_age_min=` format.
- Aggregation keys renamed: `hwm_gate_blocks_total` →
  `loss_gate_blocks_total`, `hwm_gate_blocks_unique_syms` →
  `loss_gate_blocks_unique_syms`. The unified `gate_blocks_total` column
  in the daily report keeps the same name (still sums fade-gate + loss-gate).
- `VARIANTS[C]` label `"REENTRY-HWM-gate"` → `"REENTRY-loss-gate"`.
- Per-variant detail line in the daily markdown report:
  `- REENTRY-loss-gate blocks: <count> (<N> unique symbols)`.

---

## What does NOT trigger the gate

Per the directive's "false positives silently kill winners" guidance, the
gate matches only EXPLICIT loss-class prefixes. These exit reasons do NOT
trigger the gate:

- `regime_shift_partial` (the 1.5R partial-fill exit — a WIN exit)
- `move_take_profit` and any TP-class exits
- Manual exits, force-flatten exits, watchdog-driven exits

---

## Smoke test results

Out-of-bot smoke test (Python REPL, no IBKR needed):

| Prior exit reason          | Age (min) | Expected | Actual |
|----------------------------|-----------|----------|--------|
| `move_hwm_exit`            | 5         | FIRE     | FIRE ✅ |
| `move_hwm_exit_trailed`    | 15        | FIRE     | FIRE ✅ |
| `move_stop_prox_bail`      | 1         | FIRE     | FIRE ✅ |
| `move_hard_stop`           | 10        | FIRE     | FIRE ✅ |
| `regime_shift_hard_stop`   | 2         | FIRE     | FIRE ✅ |
| `regime_shift_hard_stop`   | 30        | FIRE     | FIRE ✅ (boundary) |
| `regime_shift_partial`     | 1         | PASS     | PASS ✅ |
| `move_take_profit`         | 5         | PASS     | PASS ✅ |
| `move_hwm_exit`            | 31        | PASS     | PASS ✅ (out of window) |
| `manual_close`             | 1         | PASS     | PASS ✅ |
| `force_flatten`            | 1         | PASS     | PASS ✅ |
| `watchdog_close`           | 1         | PASS     | PASS ✅ |

Parser smoke test (`scripts/abc_compare_daily.py`):
- Matches new format: `REENTRY_LOSS_GATE_BLOCK AMSS reason=regime_shift_hard_stop window_age_min=2` → parsed
  symbol=`AMSS`, reason=`regime_shift_hard_stop`, age=`2`. ✅
- Rejects old HWM format (clean break, no migration). ✅
- `VARIANTS[C]` label updated. ✅

---

## How tomorrow's cron will exercise this

- 02:00 MT cron launches Variant C with `WB_MOVE_REENTRY_LOSS_GATE_ENABLED=1`.
- Sub-bot init log will show:
  `[MOVE_SUB_C] [HH:MM:SS] init: reentry_loss_gate=on window=30min`
  (or equivalent — depends on existing init log layout; this gate already
  inherits the `__init__` debug print used for other knobs).
- Any AMSS-class event today recurs as: `REENTRY_LOSS_GATE_BLOCK <sym>
  reason=<prior> window_age_min=<n>`.
- `scripts/abc_compare_daily.py` end-of-day report will show
  `REENTRY-loss-gate blocks: N (M unique symbols)` under Variant C.

---

## Sanity checks before push

- `grep WB_MOVE_REENTRY_HWM_GATE` across `move_strike_subbot.py`,
  `daily_run_v3.sh`, `scripts/abc_compare_daily.py` returns 0 matches
  (only directive-doc paths reference it). ✅
- `grep REENTRY_HWM_GATE_BLOCK` returns 0 code matches. ✅

---

## Validation criteria (from directive §Validation criteria)

**Day 1 (tomorrow, 2026-05-28)**: at least one `REENTRY_LOSS_GATE_BLOCK`
line in Variant C's log if any AMSS-class events recur. If A/B/C all
clean (no REENTRY cycles fire), no block events expected.

**Cumulative criterion (~10 trading days)**:
- C beats A by ≥ $500 AND > 60% of gated re-entries were losses if taken
  → ship the broader scope to all variants.
- C trails A → narrow back to hard-stop-class only.
- Tied → continue observing.

---

## What this directive does NOT include

- No regime_shift entry-side changes (baseline-floor fix deferred to
  Phase 3c bar-stream data).
- No pre-partial drawdown exit for regime_shift (deferred to separate
  directive after Phase 3c data lands).
- No Variant A/B changes.

---

## Cross-references

- `cowork_reports/2026-05-27_amss_regime_long_hold_audit.md` — the audit
  that surfaced the broaden-scope requirement (recommendation #3).
- `cowork_reports/2026-05-27_reentry_hwm_gate_impl_notes.md` — superseded
  by this doc; HWM-narrow scope was the earlier morning ship.
- `cowork_reports/2026-05-27_reentry_loss_gate_broaden_directive.md` —
  the directive this implements.
