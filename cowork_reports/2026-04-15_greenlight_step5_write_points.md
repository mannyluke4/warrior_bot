# Green Light — Step 5 write points (commit 95bae57)

**Author:** Cowork (Opus)
**Date:** 2026-04-15 late afternoon
**Reviewing:** commit `95bae57` — "session_state + bot_v3_hybrid: wire step 5 write points"
**Verdict:** Approved. Proceed to step 6 (tick-replay seed replacement).

---

## What I checked

Read the full diff for `bot_v3_hybrid.py`, `session_state.py`, and `test_session_state.py`. Cross-checked the schema trim against the no-standing-exits finding. Traced each write point against the reactive-exit architecture to confirm the write happens at the right instant.

## What's right

1. **Schema trim applied correctly.** 19 fields, three phantom order-ID fields gone. `order_id` (entry) retained. Test fixture updated + "missing field" test now uses `peak` which still exists — clean.

2. **Write-on-fill is the protected-state moment.** `_verify_fill_with_retry` persists only when `fill_confirmed=True` and `position_attr == "open_position"`. That matches the revised rule: fill = `manage_exit()` is armed = durable. Box deferred to v1 follow-up, as expected.

3. **Peak-advance gate is correct.** The persist in `manage_exit` is guarded by `if price > pos["peak"]`, so it fires only on new highs, not every tick. Frequency bound is realistic.

4. **tp_hit transition stamps + persists cleanly.** `partial_filled_at` stamped before the core exit, `partial_filled_qty` stamped before `exit_trade` flips qty, then a second persist after qty shifts to runner. Brief mid-transition inconsistency is immediately corrected — fine.

5. **Full exit correctly writes `[]`.** Line 1649 sets `state.open_position = None` before the `persist_open_trades()` call at 1651. `persist_open_trades` writes `[]` when no fill-confirmed position, which is what we want on full close.

6. **Partial exit writes updated qty.** In `exit_trade`, `pos["qty"] = remaining` is set before the persist, so the shrunken position makes it to disk.

7. **Watchlist write points on both subscribe paths.** Momentum (`subscribe_symbol`) and box (`subscribe_box_symbol`) both call `persist_watchlist`. `subscribed_at` preserved for existing symbols (not overwritten on rewrite) — good for audit.

8. **Risk flush thread wired in `main()` after Alpaca connect.** 60s belt-and-suspenders is correct scope — not the primary write path, just safety net.

9. **Persistence errors logged but non-fatal.** Every persist_* helper try/except wrapped. Trading hot path is protected from a bad JSON write.

10. **Read-side warning logs landed.** Dropped non-dict and schema-invalid entries now log with symbol + error. Silent filtering no longer hides writer bugs.

## Minor observations (not blockers)

- `_open_position_to_trade_record` treats `target_r` as 0 for non-squeeze setups. That's schema-honest but means a future MP re-enable will resume positions with `target_r=0`. Fine for v1 since MP is gated OFF; flag for when MP comes back.
- `bail_timer_start` is aliased to `entry_time`. Matches how the bail timer is actually evaluated today (duration from entry). Documented in the docstring — good.
- `exit_mode` pulled from `WB_EXIT_MODE` env each write. Cheap, and keeps the record in sync if the env is ever hot-swapped. Fine.

## Edge cases deferred to step 7 (correct)

- Qty reconciliation on rehydrate (partial fill during crash window): step 7 will cross-check `state.open_position.qty` against Alpaca's reported position. Step 5 correctly doesn't try to handle this yet.
- Orphan position flatten: step 7.
- Pending BUY + all SELL cancellation: step 7.

## Proceed

Clear to start step 6. The review boundary there is where tick-replay starts interacting with detector state machines, so I'll want eyes on the diff before it lands — same pattern as this review.

Nothing else blocks.

---

*Cowork (Opus), 2026-04-15 late afternoon. Write points are clean. Go.*
