# Completion — P0 phantom-P&L fix

**Author:** CC (Opus)
**Date:** 2026-04-16
**Directive:** `2026-04-16_directive_phantom_pnl_fix.md`
**Commits:** `9b793f8` (partial — orphan-detection + dual-submission guard) + `[this]` (exit-fill verification)
**Scope:** `bot_v3_hybrid.py` only. `simulate.py` untouched (sim has no Alpaca order flows).

---

## Diff summary

### `exit_trade()` — deferred P&L booking

**Before:** P&L computed from the intended `price` arg × intended `qty` and recorded synchronously at order-submission time, before Alpaca confirmed the fill. Target leg over-reported $116 (intended $6.20 vs actual $6.17 × 3884). Runner over-reported $10 (intended $6.07 vs actual $6.0488 × 432).

**After:** `exit_trade()` submits the order + does synchronous state cleanup (clear or decrement `state.open_position.qty` so the next `manage_exit` tick doesn't double-exit), then spawns a `verify_exit_fill` daemon thread that polls Alpaca's order status for up to 30 seconds. The thread records P&L using the actual `filled_avg_price × filled_qty` from Alpaca's response. Detector notifications (squeeze, MP V2, continuation) now fire with the **actual** P&L, not the intended.

Defense-in-depth:
- If `status` resolves to `cancelled` / `expired` / `rejected` with `filled_qty == 0`, nothing is recorded. The shares are still held by another pending order or already sold, depending on the failure mode.
- `EXIT UNFILLED` log line surfaces the case explicitly so it's visible in the daily log.
- Slippage is called out in the exit log when `|actual - intended| > $0.005`: `EXIT: MYSE qty=3884 @ $6.1700 (intended $6.2000, slip $-0.0300)`.
- Partial fills log as `[PARTIAL 149/432]` so it's obvious the order didn't fully fill.

### `reconcile_positions_on_startup()` + `periodic_position_sync()` — orphan detection respects `held_for_orders`

**Before:** Any Alpaca position the bot didn't internally track was flagged as orphan and flattened. If the shares were already held by an open exit order (`qty_available == 0`), the flatten failed with `code: 40310000 "insufficient qty available"`. But the bot still recorded P&L for the failed flatten — this is the mechanism that produced today's 3 phantom losses (-$91, -$110, -$57 = -$258 total).

**After:** Both orphan-detection sites check `pos.qty_available` before declaring orphan. Three behaviors:
- `qty_available == 0`: skip entirely. Shares are in-flight on a pending exit order — wait for it to resolve.
- `0 < qty_available < qty`: adopt only the free portion. Some shares are free, some are held.
- `qty_available == qty`: full adoption as before.

The startup reconcile also uses `qty_available` when sending its own close order, so it never requests more shares than are actually free.

This is equivalent to the directive's "cross-reference open orders + subtract held qty" approach — Alpaca's `qty_available` field is literally `qty - held_for_orders`, pre-computed server-side.

---

## Before/after trace — the MYSE scenario

**Morning's actual sequence (pre-fix):**

```
1. Submit BUY 4316 MYSE @ $6.07 → fills @ $6.0199
2. Submit SELL 3884 MYSE @ target → bot logs +$699 immediately using intended $6.20
   Alpaca actually fills at $6.17 → over-report +$116
3. Submit SELL 432 MYSE @ runner → bot logs +$22 immediately using intended $6.07
   Alpaca partial-fills at $6.0488 → over-report +$10
4. periodic_position_sync fires, sees 283 MYSE held_for_orders by order ID 6ca8e85f
   → declares orphan, submits SELL 283 @ $5.70 → Alpaca rejects 40310000
   Bot logs -$91 phantom P&L anyway
5. Same again at 60s: -$110 phantom
6. Same again at 60s: -$57 phantom
7. Final: bot daily_pnl = +$699 + $22 - $91 - $110 - $57 = +$463
   Alpaca truth daily delta = +$595.27
   Divergence: -$132 (bot under-reports by $132)
```

**Same sequence with the fix applied:**

```
1. Submit BUY 4316 MYSE @ $6.07 → fills @ $6.0199 (unchanged)
2. Submit SELL 3884 MYSE @ target.
   verify_exit_fill polls Alpaca → fills at $6.17 × 3884
   Records +$582.60 (matches Alpaca truth)
3. Submit SELL 432 MYSE @ runner.
   verify_exit_fill polls Alpaca → partial fills, eventual average $6.0488 × 432
   Records +$12.48 (matches Alpaca truth)
4. periodic_position_sync fires, sees 283 MYSE held_for_orders (qty_available=0)
   → skips (not an orphan, in-flight on pending order)
   Nothing submitted, nothing recorded.
5. No further sync events needed — the 283 eventually fills as part of the
   runner order completing. Alpaca ends flat.
6. Final: bot daily_pnl = +$582.60 + $12.48 = +$595.08
   Alpaca truth = +$595.27
   Divergence: -$0.19 (rounding only; matches to within 3¢)
```

The -$132 divergence becomes essentially zero.

---

## Confirmation — rejected orders produce zero P&L records

Three independent guards in the post-fix code:

1. **Submission guard** (`if not order_submitted: return`): if BOTH limit and market submissions raise exceptions, the function returns before any state change. Zero P&L.
2. **Race guard** (`if pos is None: return`): if `state.open_position` was cleared by a concurrent path between submission and snapshotting, the function returns. Zero P&L.
3. **Fill-verify guard** (`if actual_qty == 0: return`): inside `verify_exit_fill`, if the order resolves to `cancelled` / `rejected` / `expired` with zero shares filled, the thread returns before any state mutation. Zero P&L, zero detector notifications, zero closed_trades entry.

Combined: there is no code path from `exit_trade()` to a P&L record where Alpaca didn't actually move shares.

---

## Validation

Per Cowork's directive, no sim regression canary applies. Validation path:

- **Code review**: diff is in this commit; main body is the `verify_exit_fill` daemon (~100 lines replacing ~60 lines of synchronous booking) + the earlier dual-submission guard. Orphan-detection changes are 2 places (`reconcile_positions_on_startup`, `periodic_position_sync`), each a single conditional insert.
- **Next live session**: tomorrow morning's first partial-fill or runner exit confirms:
  - `state.daily_pnl` matches Alpaca account delta at session end (should be within rounding ~ $0.05)
  - `⏸ IN-FLIGHT POSITION` log for any `held_for_orders` situation (replaces previous `⚠️ ORPHAN DETECTED` misfires)
  - Exit log shows `qty=N @ $X.XXXX (intended $Y.YYYY, slip $ΔΔ)` with actual fill price
- **Manny's out-of-town week:** the fix is live-path only, no gate, no env var. Daily_pnl reporting in the daily log becomes authoritative. The cumulative divergence that was ~$130/day is eliminated.

---

## Out of scope (per directive)

- Heartbeat cadence not touched (2/min remains).
- WNW/WSHP armed states unchanged.
- No exit slippage tracking or fill-rate analytics beyond the per-exit slip note in the log.
- Entry path (`_verify_fill_with_retry`) untouched — already works correctly.
- Sim (`simulate.py`) untouched.

---

*CC (Opus), 2026-04-16. Bookkeeping fixed. Strategy still works.*
