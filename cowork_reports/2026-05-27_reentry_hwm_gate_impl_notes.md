# Implementation Notes: REENTRY-HWM-gate (Variant C re-purpose)

**Directive:** `cowork_reports/2026-05-27_reentry_hwm_gate_live_directive.md`
**Status:** Shipped, smoke-tested, ready for tomorrow's 02:00 MT cron.

---

## What landed

### Code changes

**`move_strike_subbot.py`** — env-gated REENTRY-HWM-gate check added to `_try_fire_green_reentry`. Also tracks last-exit-reason-per-symbol in `_close_position`.

- New env vars (defaults preserve old behavior — gate OFF):
  - `WB_MOVE_REENTRY_HWM_GATE_ENABLED=0` (master gate)
  - `WB_MOVE_REENTRY_HWM_GATE_WINDOW_MIN=30` (only gate if prior exit within N min)
- New `self._last_exit_reason_by_symbol: dict[str, tuple[str, int]]` populated in CASE 1 (full close) of `_close_position`. Maps symbol → (exit_reason, exit_minute_et).
- Gate check at line 854 of `_try_fire_green_reentry`: if enabled AND prior exit started with `move_hwm_exit` AND was within `WINDOW_MIN`, log `REENTRY_HWM_GATE_BLOCK <sym>` and skip the entry (pops the watch).

**`daily_run_v3.sh:359`** — Variant C launch line updated:
```diff
- launch_subbot C "$VARIANT_C_KEY" "$VARIANT_C_SECRET" "WB_MOVE_FADE_BODY_CV_THRESHOLD=2.0"
+ launch_subbot C "$VARIANT_C_KEY" "$VARIANT_C_SECRET" "WB_MOVE_REENTRY_HWM_GATE_ENABLED=1 WB_MOVE_REENTRY_HWM_GATE_WINDOW_MIN=30"
```
Variants A (no gate) and B (V1 VWAP fade) unchanged.

**`scripts/abc_compare_daily.py`** — parser + report updates:
- New `REENTRY_HWM_GATE_BLOCK_RE` regex
- `parse_log()` returns new fields: `hwm_gate_blocks_total`, `hwm_gate_blocks_unique_syms`, `gate_blocks_total`
- Account-snapshot table column renamed `Fade blocks` → `Gate blocks`, value pulled from `gate_blocks_total`
- Per-variant detail now lists REENTRY-HWM-gate blocks if any fired
- `VARIANTS` constant: variant C label changed from `"V4 BodyCV"` to `"REENTRY-HWM-gate"`

### What did NOT change

- `move_strike_subbot.py` REENTRY BREAK code path (per directive — separate trigger, out of scope)
- Live regime_shift entry path (regime_shift never goes through REENTRY pipeline)
- Initial MOVE_STRIKE entries (gate fires only on REENTRY GREEN)
- Variants A and B configs

---

## Smoke test results

`/tmp/hwm_gate_smoke.py` — 4 unit-style scenarios:

| # | Scenario | Expected | Result |
|---|---|---|---|
| 1 | Gate ON, prior HWM exit 10 min ago | BLOCK | ✓ blocked + log line + watch popped |
| 2 | Gate ON, prior HWM exit 45 min ago (outside 30 min window) | ALLOW | ✓ allowed re-entry |
| 3 | Gate ON, prior exit was move_stop_prox_bail (not HWM) | ALLOW | ✓ allowed re-entry |
| 4 | Gate OFF, prior HWM exit 5 min ago | ALLOW | ✓ allowed re-entry |

Sample log line emitted by Test 1:
```
[MOVE_SUB] [18:34:01] REENTRY_HWM_GATE_BLOCK VCIG prior_exit=move_hwm_exit(peak=3.50,dd=25%,hh=2) min_ago=10
```

---

## Operational impact

### A/B/C clock reset

Per directive: pre-change A/B/C variant comparison data shouldn't be mixed with post-change data. Today's (2026-05-27, Day 1 post-orphan-fix) A/B/C data remains useful for absolute strategy-economics analysis (the regime_shift ASTC +$1,110 trade is real evidence regardless of variant config), but variant-comparison reporting starts fresh from Day 1 = tomorrow 2026-05-28.

### What we expect to see on Day 1

Per Day-1 hypothesis from the deep-dive, the pattern is rare (n=2 on 2026-05-27). If similar conditions repeat:
- Expect 1-2 `REENTRY_HWM_GATE_BLOCK` events per active day on Variant C
- Variant A will continue to take those re-entries (no gate)
- Variant B's V1 VWAP fade may or may not block the same re-entries (different mechanism)

### Acceptance for the gate (cumulative over ~10 days)

| Condition | Decision |
|---|---|
| Variant C beats Variant A by ≥ $500 cumulative AND blocked re-entries would have lost in A | Ship the gate across all variants |
| Variant C trails Variant A | Revert the gate |
| Essentially tied (within $500) | Defer; revisit after Phase 3c bar-construction work enables backtest evaluation |

---

## What this directive does NOT include

Per directive scope:
- No backtest validation (Phase 3c blocked on bar-construction)
- No REENTRY BREAK changes
- No gate on initial entries
- No regime_shift changes

---

## Variant lineup after this change

| Variant | Config | Test purpose |
|---|---|---|
| A | No gates, no fade | Control baseline |
| B | V1 VWAP fade (entries below VWAP blocked) | Test V1 fade-gate value |
| C | REENTRY-HWM-gate (re-entries after HWM exit within 30 min blocked) | Test the Day-1 hypothesis |

Pairwise comparisons isolate single-gate effects. A vs B = V1 VWAP value. A vs C = HWM-gate value. B vs C = comparing two different gate mechanisms (not strictly apples-to-apples but informative).

If we want to re-introduce V4 BodyCV later, that's a 4th paper account + separate directive.

---

## Files changed (commit ready)

- `move_strike_subbot.py` — gate logic + last-exit tracking
- `daily_run_v3.sh` — Variant C env vars
- `scripts/abc_compare_daily.py` — parser + report

Files NOT changed but worth flagging for follow-up:
- `simulate_subbot.py` — could mirror the gate logic for backtest reproducibility, but blocked on Phase 3c validation passing first
- `cowork_reports/abc_running_totals.json` — will be regenerated by tomorrow's EOD report run

---

*Implementation complete. Standing by for tomorrow's 02:00 MT cron to fire the new Variant C config.*
