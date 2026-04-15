# Completion — simulate.py:1981 EPL exclusion fix

**Author:** CC (Opus)
**Date:** 2026-04-15 evening
**Directive:** `2026-04-15_directive_sim1981_exclusion_fix.md`
**Status:** Shipped.

---

## Diff

One line. `simulate.py:1981`:

```diff
-        if t.setup_type not in ("squeeze", "vwap_reclaim", "mp_reentry", "continuation", "dp_dip_entry"):
+        if t.setup_type not in ("squeeze", "vwap_reclaim", "mp_reentry", "continuation", "dp_dip_entry", "epl_mp_reentry"):
```

Comment on the line above also updated from `(squeeze/VR/mp_reentry/dp have own tracking)` → `(squeeze/VR/mp_reentry/dp/epl_mp have own tracking)`.

## Parallel spots

Checked `bot_v3_hybrid.py` for `record_trade_result` / `_session_trades` / `_session_losses`. **None found.** The live bot runs with `WB_MP_ENABLED=0`, so the standalone `MicroPullbackDetector` instance isn't active and the miscounting couldn't occur there anyway. No parallel fix needed.

## Validation — all zero-diff

| Run | Target | Measured | Δ |
|---|---|---|---|
| VERO 2026-01-16 07:00-12:00 | $+35,622 (session baseline) | $+35,622 | 0 |
| ROLR 2026-01-14 07:00-12:00 | $+50,602 (session baseline) | $+50,602 | 0 |
| BIRD 2026-04-15 08:15-16:00 | $-1,909 (autopsy baseline) | $-1,909 | 0 |

All three zero-diff. Counters were not being read anywhere, so removing the miscount changes nothing. Expected outcome.

## Green light

The counters are now correctly scoped: standalone MP's `_session_trades` / `_session_losses` only reflect standalone MP trades. Any future Gate 5 extension (the shelved options from the BIRD autopsy: time-decay, setup-quality, price-context) can read these counters without contamination from EPL activity.

Proceed on future EPL-gate directives without the pre-existing miscounting hazard.

## Commit

`[TBD after commit]` on `v2-ibkr-migration`. Co-Authored-By line included.

---

*CC (Opus). One line, three validations, clean.*
