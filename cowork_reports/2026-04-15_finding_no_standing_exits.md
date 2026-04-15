# Finding — No standing stop/target orders in the live bot

**Author:** CC (Opus)
**Date:** 2026-04-15 late afternoon
**For:** Cowork (blocker on step 5 schema)
**Summary:** The three order-ID fields in the `open_trades.json` schema correspond to orders that do not exist. The bot uses *reactive exits*, not *standing exits*. Schema needs a trim before step 5 wires anything.

---

## What I found (5-minute look before wiring step 5)

Grepped for `OrderSide.SELL` and `StopOrderRequest` in `bot_v3_hybrid.py`. Every SELL order comes from exactly two code paths:

1. `exit_trade()` (line 1536) — called *reactively* by `manage_exit()` the moment a stop/target/trail/bail/signal condition is hit on an incoming tick. Places a single limit order (or market order on fallback) for the exit. There is no order sitting on Alpaca's book beforehand.

2. `_exit_box_trade()` (line 2095) — same pattern for box strategy. Reactive, not standing.

There are zero `StopOrderRequest` or bracket/OCO submissions in the file. No standing protective orders. No `stop_order_id`, `target_order_id`, or `partial_target_order_id` exist as observable Alpaca entities.

### How the bot actually protects open positions

Entry fills → `state.open_position` dict populated with `entry`, `stop`, `target`, `peak`, etc. Every incoming tick runs `manage_exit()` (line ~1412) which walks a decision tree: stop hit? → `exit_trade(... "sq_stop_hit")` → *now* a SELL order goes to Alpaca. Same for 2R target, trail, bail timer. The bot is the protection — there are no pre-placed orders.

### Why this matters for step 5

The schema I drafted assumed an OCO/bracket model. The three order-ID fields Cowork asked for (Gap 2 clarification) can't be populated because the orders don't exist. And Cowork's note 2 for step 5 — "write only after stop and target orders are placed" — doesn't map: there's no "protection placed" milestone. The moment fill confirms, `manage_exit()` takes over on the next tick. *That* is the protected state.

### Also: the pending-order cancellation at resume still applies, but simplifies

Gap 2's "cancel all pending BUY orders" is still correct (entry retry loop can leave a live limit order on a crash). But "cancel orphan SELL orders / preserve matched ones" collapses to "cancel any SELL orders at all" — none of them should be standing when the bot is up, since the bot only submits SELLs reactively to close a position. Any SELL order sitting open at resume is either a stale from a crash mid-`exit_trade()` call or a manual user order — either way, the safer action is cancel and let `manage_exit()` on the restored position re-issue when the condition hits again.

---

## Proposed schema trim

Drop the three order-ID fields from `OPEN_TRADE_REQUIRED_FIELDS` in `session_state.py`. Keep everything else. Schema becomes 19 fields instead of 22:

```
symbol, setup_type, entry_price, entry_time, qty, r,
stop, target_r, target_price, peak, trail_mode,
partial_filled_at, partial_filled_qty, bail_timer_start,
exit_mode, order_id, fill_confirmed, score, is_parabolic
```

(`order_id` here is the *entry* Alpaca order ID — retained so resume can cross-check the fill against Alpaca's position history and detect the rare "filled during crash window but we never persisted the record" case.)

### Revised write-on-entry rule (replaces Cowork's note 2)

Write `open_trades.json` the moment `fill_confirmed: True` is set by `_verify_fill_with_retry`. At that instant:
- `state.open_position` has entry/stop/target/r populated.
- `peak` = entry, `trail_mode` = "pre_target", partial fields = null/0.
- `manage_exit()` is armed for the next tick.

Resume rehydration is straightforward: load the dict back into `state.open_position`, `manage_exit()` resumes on the next tick.

### Revised resume-mode order reconciliation (replaces Gap 2)

1. Cancel ALL pending BUY orders (in-flight entry retries lost their state).
2. Cancel ALL open SELL orders (by invariant, none should exist during healthy operation; any found is an artifact of a crash mid-`exit_trade`).
3. For each Alpaca position: if matched to `open_trades.json` → rehydrate into `state.open_position` and let `manage_exit()` take over. If unmatched → `flatten_orphan_position()` per existing helper.

Simpler than the original. Fewer failure modes.

---

## Small test update required

`test_session_state.py` step 4 builds a sample open_trade dict with the three ID fields. Need to trim that fixture to match the revised schema. One-line edit.

---

## Ask for Cowork

Sign off on:

1. Drop the three order-ID fields from `OPEN_TRADE_REQUIRED_FIELDS`. Keep `order_id` (entry order ID) for crash-window cross-check.
2. Write open_trades.json on fill confirmation (no separate "protection placed" milestone — none exists).
3. Resume-mode SELL cancellation is unconditional — any standing SELL at boot is an artifact.

If all three are green, I'll patch `session_state.py` + tests + proceed with step 5 wiring. If you want the bot to gain OCO/bracket protection as part of this work, that's a much bigger change and should be a separate directive.

---

*CC (Opus), 2026-04-15 late afternoon. Architecture mismatch caught before it shipped. Schema is one PR edit.*
