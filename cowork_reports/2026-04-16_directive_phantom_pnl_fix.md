# Directive — P0 phantom-P&L fix (exit booking + orphan detection)

**Author:** Cowork (Opus)
**Date:** 2026-04-16 morning
**For:** CC
**Type:** Live-bot bugfix, P0. Two separate fixes in `bot_v3_hybrid.py`.
**Why:** Bot reported +$463, Alpaca truth is +$595.27. Two root causes: premature exit-P&L booking and phantom losses from orphan-detection misfires. Both actively corrupt `state.daily_pnl` on every trade with partial fills or runner exits. Must land before tomorrow's session.

---

## Bug 1 — Exit P&L booked at submission time, not fill time

### Problem

`exit_trade()` records P&L using the *intended* price + full qty at order submission, before Alpaca's fill comes back. Entry path already does this correctly via `_verify_fill_with_retry` (reads `filled_avg_price` / `filled_qty`). Exit path doesn't.

Today's impact: target leg over-reported by $116 (bot used $6.20, Alpaca filled at $6.17 × 3884 shares), runner over-reported by ~$10.

### Fix

Defer P&L recording in `exit_trade()` until Alpaca reports the fill:

- On `status=filled`: record `filled_qty × (filled_avg_price - entry_price)`.
- On `partially_filled`: record only the filled portion. The unfilled portion stays as an open order — don't book it.
- On `cancelled` / `rejected` / `expired`: record nothing. Shares are still held; orphan reconciliation will handle them.

**Do NOT change the entry path.** Entry already works correctly. This fix makes exit match entry.

### Implementation notes

- The exit order may already have a retry/verify pattern like entry. If so, extend it. If not, adding a lightweight poll (same `_verify_fill_with_retry` pattern, up to 30 sec for exit to confirm) is acceptable.
- If Alpaca's order status API is slow (>10 sec delay to confirmed fill on a market order), log a warning but still wait — don't fall back to booking at intended price.

---

## Bug 2 — Orphan detection misidentifies `held_for_orders` as stranded

### Problem

`periodic_position_sync()` sees Alpaca position for MYSE (283 shares), doesn't find it in `state.open_trades`, declares orphan, tries to flatten. Alpaca correctly rejects (shares are `held_for_orders` by the still-open runner exit order). But the bot logs the flatten as if it succeeded, recording phantom P&L.

Today's impact: 3 phantom losses totaling -$258 booked against `state.daily_pnl` for exits that never happened.

### Fix

Before declaring an orphan, cross-reference the symbol's Alpaca position against open orders:

```
open_orders = api.get_orders(status="open", symbols=[symbol])
held_qty = sum(o.qty - o.filled_qty for o in open_orders if o.side == "sell")
if position_qty <= held_qty:
    # Shares are in-flight on existing exit orders, not orphaned
    log(f"MYSE position {position_qty} accounted for by open orders (held={held_qty}), skipping orphan")
    continue
```

Only flatten the *difference* if `position_qty > held_qty`.

**Critical:** if the flatten order fails (Alpaca rejects for `insufficient qty available`), do NOT record P&L. A rejected order means zero shares changed hands. Today's behavior of logging P&L on a rejected order is the direct cause of the phantom losses.

### Defense in depth

Even after fixing the orphan detection, add a guard in the P&L recording path: if the exit order's Alpaca status is `rejected` or the response includes `code: 40310000` (insufficient qty), skip P&L recording entirely. This catches any future edge case where a reconciliation exit fails.

---

## Scope

- **Files:** `bot_v3_hybrid.py` only.
- **Sim impact:** none. `simulate.py` doesn't have Alpaca order flows.
- **Gate:** no env-var gate needed. These are correctness fixes to order accounting, not behavior changes. The old behavior (booking phantom P&L on rejected orders) is never desirable.
- **Branch:** `v2-ibkr-migration`.

---

## Validation

No regression canary applies here (this is live-bot order execution, not sim). Validation path:

1. **Code review by Cowork:** once the fix is committed, upload the diff. Cowork will review for (a) exit P&L only recorded after confirmed fill, (b) orphan path checks `held_for_orders` before flattening, (c) rejected orders never record P&L.
2. **Next live session test:** tomorrow morning's first trade with a partial fill or runner exit confirms:
   - `state.daily_pnl` matches Alpaca account delta at session end
   - No orphan-detection log entries for shares that are `held_for_orders`
   - Exit P&L logged only after fill confirmation

---

## Out of scope

- Don't change heartbeat cadence. 2/min is fine. If Manny wants more frequent, that's a separate conversation.
- Don't touch WNW/WSHP armed states. Those carry into the afternoon naturally.
- Don't add exit slippage tracking or fill-rate analytics. That's separate research. Keep this fix narrow.

---

## Deliverable

One commit on `v2-ibkr-migration`. Completion report at `cowork_reports/2026-04-16_completion_phantom_pnl_fix.md` with:
- Diff summary (which functions changed, what changed in each)
- Before/after trace showing the MYSE scenario would have been handled correctly
- Confirmation: rejected orders produce zero P&L records

---

*Cowork (Opus). The strategy worked. The bookkeeping didn't. Fix the books, don't touch the strategy.*
