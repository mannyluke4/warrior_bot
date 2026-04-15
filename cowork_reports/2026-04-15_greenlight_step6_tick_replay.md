# Green Light — Step 6 tick-replay seed (commit 7a9d0c9)

**Author:** Cowork (Opus)
**Date:** 2026-04-15 evening
**Reviewing:** commit `7a9d0c9` — "bot_v3_hybrid: tick-replay seed for resume mode (step 6)"
**Verdict:** Approved. Proceed to step 7 (order/position reconciliation).

---

## What's right

1. **Cache becomes authoritative from 04:00 ET.** Cold-path `seed_symbol` now appends fetched historical ticks to `state.tick_buffer` under `_tick_buffer_lock`. The 30s flush thread writes them to disk. Clean: lock serializes vs. live callbacks + flush swap, zero-size/zero-price ticks skipped at write time so the cache doesn't carry garbage.

2. **Resume-path mirrors cold path below the fetch.** `seed_symbol_from_cache` runs `begin_seed` → replay ticks through `bar_builder_1m.on_trade` (and box builder if enabled) → `validate_arm_after_seed` → `end_seed`. Identical sequence to cold seed, so detector state reconstructs the same way.

3. **Safety invariant held.** Replay ticks flow only through `bar_builder_1m.on_trade`, never through `on_ticker_update → on_trade_price`. No retroactive ENTRY signals. This is the architectural guard the cold seed has always relied on, and it's honored here.

4. **Fall-through logic is correct.** `subscribe_symbol` only tries the cache when `state.boot_mode == "resume"`, and any miss or read error returns False → cold IBKR seed runs. A newly-subscribed symbol post-crash (not in cache) seeds from IBKR without drama.

5. **Cache robustness.** Missing file, empty file, corrupt gzip/JSON, per-tick malformed entry — all handled without crashing boot. Exceptions during replay fall back to cold seed; detector state from the partial replay gets re-initialized by `begin_seed` in the cold path (idempotent per CC's note).

6. **Clock-drift log lands per the earlier ask.** Each per-symbol resume one-liner shows ticks/bars/EMA/ARMED + drift between last replayed tick and wall-clock. Exactly what was requested for post-mortem visibility.

7. **Gate still off by default.** Resume-path is reachable but inert without `WB_SESSION_RESUME_ENABLED=1` — correct staging, since position rehydrate (step 7) hasn't landed.

## Minor observations (not blockers)

- **Drift log edge case:** `f"{drift_sec/60:.1f}m" if drift_sec else "?"` — if drift is exactly 0 (unlikely in practice but possible), it'll print `?`. Should be `if drift_sec is not None`. Cosmetic.
- **Cache dedup on fallback:** If `seed_symbol_from_cache` gets past a partial replay and then falls back to cold `seed_symbol`, the cold path will re-append IBKR ticks to `tick_buffer` → flush → cache grows with duplicates on disk. Detector state is fine (cold path rebuilds cleanly), but the on-disk cache for that symbol could have repeated ticks for the rest of the day. Rare (requires mid-replay exception), and simulate.py is untouched so regression is unaffected. Log-and-move-on is acceptable for v1; flag for step 8 crash-injection testing to confirm we don't see it in practice.
- **`latest_price` for stale-arm validation** uses `raw_ticks[-1]["p"]` directly without the malformed-entry skip. Worst case is a bad-tick KeyError inside `.get("p", 0)` returns 0, and `validate_arm_after_seed(0.0)` flags the arm stale — which is the safe default. Fine.

## Confirmed out of scope (correctly deferred to step 7)

- Pending BUY cancellation
- Unconditional SELL cancellation
- Orphan-position flatten with `WB_RESUME_FLATTEN_ORPHANS` gate
- Qty drift reconciliation between persisted `open_trades.json` and Alpaca's reported position
- Rehydrate of `state.open_position` from the trade record

## Proceed

Step 7 is the last detector-adjacent review boundary in this series. Same pattern: land the diff, pause, I read, green-light, then step 8 (crash-injection) and step 9 (regression) can run without ceremony.

Nothing else blocks.

---

*Cowork (Opus), 2026-04-15 evening. Replay path is clean. Go.*
