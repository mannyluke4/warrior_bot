# Directive: Orphan Position Fix (sub-bot + main bot, all 3 levers)

**Date**: 2026-05-26
**Branch**: `v2-ibkr-migration`
**Owner**: CC
**Source**: `cowork_reports/2026-05-26_sub_bot_orphan_audit.md` (commit `84a56a0`). Today's A/B/C launch surfaced a real code bug: `_close_position()` unconditionally sets `self.position = None` after `_wait_for_fill` returns, even when the SELL didn't fill or only partial-filled. 5 orphan positions across A/B/C, ~$44K of net-long exposure on Variant C before Manny's manual flatten.
**Real-money go-live**: still ~2026-06-22 (timeline absorbs this fix).

---

**Pacing rule**: Fix ships before tomorrow's 02:00 MT cron OR sub-bots stay off until it does. No more days of corrupted variant data.

---

## Why all three levers, not just Lever 1

CC's audit recommended Lever 1 alone (cheap, stops the bleed) with Lever 3 as defense-in-depth. Manny chose all three because:

- **L1 alone fixes accounting** but doesn't reduce the orphan rate. The bot would still create orphans on slow-fill exits; it would just stop lying about P&L. The bot would also wait for the next tick to retry, which on a volatile day means several more seconds of bid-walking-away time.
- **L2 actively chases the bid** with cancel-then-replace at more aggressive prices. This is what actually closes the orphan rate, not just the accounting gap.
- **L3 is the safety net** that catches anything L1 and L2 miss. Already partially implemented in `bot_v3_hybrid.py:786` (`reconcile_positions_on_startup`) — needs periodic invocation, not boot-only.

The cost is ~150 LOC across two files. The benefit is end-of-day equity that matches the bot's reported daily_pnl — the prerequisite for any variant comparison to mean anything.

---

## Scope: BOTH sub-bot AND main bot

The audit raised this as an open question. The answer is yes — same bug class exists in `bot_v3_hybrid.py` in two places:

### Main bot bug location 1 — Wave Breakout exit (`bot_v3_hybrid.py:740-779`)

```python
fill_price, filled_qty = wait_for_fill(sell.order_id, timeout=15)
if filled_qty > 0 and fill_price is not None:
    # ... record trade ...
else:
    print(f"[WB] {symbol} EXIT NO-FILL — manual review", flush=True)

state.wb_positions.pop(symbol, None)  # ← UNCONDITIONAL pop
```

Same shape as sub-bot bug. Fix is the same Lever 1 pattern: keep position alive on no-fill / partial.

### Main bot bug location 2 — Squeeze exit (`bot_v3_hybrid.py:3873-3923`)

Worse than sub-bot, structurally:

```python
remaining = pos["qty"] - qty
if remaining <= 0:
    state.open_position = None  # ← cleared OPTIMISTICALLY before fill confirmed
else:
    pos["qty"] = remaining

def verify_exit_fill():  # runs ASYNC in background thread
    # ... polls broker for up to 30s ...
    if actual_qty == 0:
        print(f"⚠️ EXIT UNFILLED ...") # ← logs but state.open_position is already None
        return
```

The main bot was running on Alpaca paper until commit `2be7efe` moved it to IBKR paper today. So Variant B's main-bot-class orphans were probably happening on Alpaca for weeks under WB_BROKER=alpaca. Now they happen on IBKR with potentially different fill quality. Either way: needs fixing.

The good news: `reconcile_positions_on_startup` at `bot_v3_hybrid.py:786` already implements ~80% of Lever 3 — it just only runs at boot. Periodic invocation is most of the work.

---

## Lever 1 — Don't lie about P&L on partial / no-fill

### Sub-bot (`move_strike_subbot.py:1224-1282`)

In `_close_position`, after `_wait_for_fill` returns:

```python
sell_fill_px, sell_fill_qty = self._wait_for_fill(p.order_id_sell, timeout=15)

# CASE 1: Full fill. Record P&L, flatten position.
if sell_fill_qty == p.qty and sell_fill_px is not None:
    real_pnl = (sell_fill_px - p.fill_entry_price_or_entry()) * sell_fill_qty
    self.daily_pnl += real_pnl
    # ... record closed trade with real fills ...
    self.position = None
    return

# CASE 2: Partial fill. Record realized P&L on filled portion, keep residual alive.
if sell_fill_qty > 0 and sell_fill_qty < p.qty and sell_fill_px is not None:
    realized_pnl = (sell_fill_px - p.fill_entry_price_or_entry()) * sell_fill_qty
    self.daily_pnl += realized_pnl
    p.qty -= sell_fill_qty
    p.order_id_sell = None  # clear so we retry on next tick
    p.exit_pending = False
    print(f"{LOG_TAG} EXIT PARTIAL {p.symbol}: filled {sell_fill_qty}, "
          f"residual {p.qty} kept alive, realized pnl=${realized_pnl:+,.2f}")
    return

# CASE 3: Zero fill. No P&L recorded. Position stays alive entirely.
p.order_id_sell = None
p.exit_pending = False
print(f"{LOG_TAG} EXIT NO-FILL {p.symbol}: position alive, will retry next tick")
return
```

The bot's next tick will re-evaluate exit conditions on `p.qty` residual shares. If the original exit reason still applies, exit logic submits a fresh SELL. If price has moved enough that the original trigger no longer applies, the position waits for the next signal — which is the correct behavior (we wanted out, but maybe the market disagreed).

Note: `p.fill_entry_price_or_entry()` is shorthand for the existing logic — `p.fill_entry_price if p.fill_entry_price is not None else p.entry`. Factor into a helper for clarity.

### Main bot Wave Breakout path (`bot_v3_hybrid.py:740-779`)

```python
fill_price, filled_qty = wait_for_fill(sell.order_id, timeout=15)

# CASE 1: Full fill.
if filled_qty == qty and fill_price is not None:
    # ... existing record-trade logic ...
    state.wb_positions.pop(symbol, None)
    if symbol in state.wb_detectors:
        state.wb_detectors[symbol].mark_exited()
    persist_wb_state()
    return

# CASE 2: Partial fill. Record realized P&L on filled portion, decrement qty, keep alive.
if filled_qty > 0 and filled_qty < qty and fill_price is not None:
    pnl = (fill_price - pos["entry"]) * filled_qty
    state.wb_closed_trades.append({...})
    pos["qty"] -= filled_qty
    print(f"[WB] {symbol} EXIT PARTIAL filled={filled_qty} residual={pos['qty']}")
    persist_wb_state()
    return

# CASE 3: Zero fill. Position untouched.
print(f"[WB] {symbol} EXIT NO-FILL — position alive, will retry next tick")
return
```

### Main bot Squeeze path (`bot_v3_hybrid.py:3873-3923`)

The structural issue is harder because of the async pattern. Two options:

**Option A (preferred — minimal churn):** Don't clear `state.open_position` at line 3878. Move that clear INTO `verify_exit_fill` after confirming `actual_qty > 0`. If `actual_qty == 0`, leave the position intact. If partial, decrement.

```python
# Line 3873-3880 BECOMES:
# Capture qty for the async thread to verify against, but DO NOT mutate state.open_position yet.
intended_qty_for_exit = qty

def verify_exit_fill():
    # ... existing polling logic ...
    if actual_qty == 0:
        print(f"⚠️ EXIT UNFILLED: {symbol} ... position remains alive at qty={pos['qty']}")
        return  # state.open_position untouched
    
    # Fill happened (full or partial). Update state HERE, not before.
    pnl = (actual_price - entry_price) * actual_qty
    state.daily_pnl += pnl
    # ...
    if actual_qty >= pos["qty"]:
        state.open_position = None
    else:
        pos["qty"] -= actual_qty
```

**The race window:** between submission and `verify_exit_fill` completion, `manage_exit` might fire again and try to double-exit. Mitigate with an `exit_in_flight` flag on `pos`:

```python
pos["exit_in_flight"] = True
# ... submit order ...
def verify_exit_fill():
    try:
        # ... existing logic ...
    finally:
        pos["exit_in_flight"] = False
```

And gate `manage_exit` on `not pos.get("exit_in_flight", False)`.

**Option B (more churn, more correct):** Refactor to synchronous wait, similar to sub-bot. Larger blast radius — not recommended unless Option A's race window proves problematic in testing.

---

## Lever 2 — Active cancel + replace on slow exits

### Sub-bot

After `_wait_for_fill` times out in `_close_position`, before falling back to Lever 1's "keep alive" path:

```python
if sell_fill_qty == 0 and self._exit_retry_count.get(p.symbol, 0) < EXIT_MAX_RETRIES:
    # Cancel the un-filled order.
    try:
        self.alpaca.cancel_order_by_id(p.order_id_sell)
        time.sleep(0.5)  # let cancel ack
    except Exception as e:
        print(f"{LOG_TAG} EXIT CANCEL FAIL {p.symbol}: {e!r}")

    # Read current bid via existing bid-fetch path
    bid = self._get_current_bid(p.symbol)  # add helper if not present
    if bid is None:
        # Fall through to Lever 1 path — keep position alive
        return
    
    # Aggressive re-price: bid * (1 - EXIT_AGGRESSIVE_DISCOUNT_PCT)
    new_limit = bid * (1 - EXIT_AGGRESSIVE_DISCOUNT_PCT)
    new_limit = max(new_limit, p.fill_entry_price_or_entry() * 0.50)  # safety floor
    
    print(f"{LOG_TAG} EXIT RETRY {p.symbol} attempt={...} bid=${bid:.4f} new_limit=${new_limit:.4f}")
    # ... re-submit, re-wait ...
    self._exit_retry_count[p.symbol] = self._exit_retry_count.get(p.symbol, 0) + 1
```

After `EXIT_MAX_RETRIES` (default 3), fall through to Lever 1 path: keep position alive, log CRITICAL, surface alert.

Add env vars:

```
WB_EXIT_RETRY_ENABLED=1
WB_EXIT_MAX_RETRIES=3
WB_EXIT_AGGRESSIVE_DISCOUNT_PCT=0.005   # 0.5% below current bid on retry
WB_EXIT_RETRY_TIMEOUT_SEC=10            # shorter than initial 15s — bid moves fast
WB_EXIT_SAFETY_FLOOR_PCT=0.50           # never sell below 50% of entry — sanity
```

### Main bot

Equivalent treatment in both `bot_v3_hybrid.py:740-779` (WB path) and `bot_v3_hybrid.py:3873+` (squeeze path). Share helper code where possible.

The squeeze path's async `verify_exit_fill` makes Lever 2 trickier to wire in. Recommendation: when `verify_exit_fill` detects `actual_qty == 0` and `exit_retry_count < EXIT_MAX_RETRIES`, schedule a follow-up exit attempt via a small synchronous helper rather than nesting more async logic.

---

## Lever 3 — Periodic broker reconciliation

### Sub-bot (new code)

Add `_reconcile_with_broker(self, now)` method, called from main loop every `WB_RECONCILE_INTERVAL_SEC` (default 60):

```python
def _reconcile_with_broker(self, now: datetime.datetime):
    if (now - self._last_reconcile_at).total_seconds() < WB_RECONCILE_INTERVAL_SEC:
        return
    self._last_reconcile_at = now
    
    try:
        broker_positions = self.alpaca.get_all_positions()
    except Exception as e:
        print(f"{LOG_TAG} RECONCILE FAIL: {e!r}")
        return
    
    broker_syms = {p.symbol: p for p in broker_positions}
    bot_sym = self.position.symbol if self.position else None
    
    # Case 1: Broker has position bot doesn't track → adopt.
    for sym, bpos in broker_syms.items():
        if sym == bot_sym:
            continue  # bot already knows
        # Adopt with conservative defaults
        adopted_entry = float(bpos.avg_entry_price)
        adopted_qty = int(float(bpos.qty))
        if adopted_qty <= 0:
            continue  # shorts handled elsewhere
        print(f"{LOG_TAG} RECONCILE ADOPT {sym} qty={adopted_qty} entry=${adopted_entry:.4f}")
        # Build a minimal SubPosition with stop = entry * 0.95 (conservative -5%)
        # and target = entry * 1.05 (conservative +5%). Mark as orphan_adopted.
        self.position = SubPosition(
            symbol=sym,
            entry=adopted_entry,
            qty=adopted_qty,
            stop=adopted_entry * 0.95,
            target=adopted_entry * 1.05,
            setup_type="orphan_adopted",
            fill_entry_price=adopted_entry,
            entry_time=now,
        )
    
    # Case 2: Bot tracks position broker doesn't have → flatten internally.
    if bot_sym and bot_sym not in broker_syms:
        print(f"{LOG_TAG} RECONCILE FLATTEN {bot_sym}: bot tracked but broker has no shares")
        self.position = None
```

The adopted-position handling uses conservative ±5% stops/targets because we don't know what setup_type the original entry was. If it was a regime-shift entry that had a 1.5R target, we don't honor that — we just protect the residual.

### Main bot

Rename `reconcile_positions_on_startup` → `reconcile_positions` and have it skip the startup-only logging. Call it from the main loop every 60s in addition to startup.

The main bot's `reconcile_positions_on_startup` already handles the adopt + flatten cases for `state.open_position`. The main change is making it idempotent for periodic invocation: don't re-print the same orphan warnings every cycle, only print on state CHANGE.

Add `state.last_reconcile_at` and gate.

---

## Today's A/B/C data treatment

Per Manny's decision: log broker reconstruction in today's daily report but exclude from variant comparison math.

### Implementation

In `scripts/abc_compare_daily.py`, add a `reconstruct_from_broker(account_key, account_secret)` helper that:

1. Calls `alpaca.get_account()` for end-of-day equity
2. Compares against starting equity ($30K)
3. Returns the broker-truth daily P&L per variant

In today's report only (special-case the 2026-05-26 date), include both:

```markdown
## Variant P&L — 2026-05-26 (DATA CORRUPTED BY ORPHAN BUG)

| Variant | Bot reported | Broker truth | Gap | Note |
|---|---|---|---|---|
| A | -$1,549 | +$419 | -$1,968 | Bot under-reported A by $2K |
| B | -$2,904 | -$2,614 | -$290 | Bot over-reported B by $290 |
| C | -$1,762 | -$2,884 | +$1,122 | Bot over-reported C by $1K |

**Variant comparison excluded for 2026-05-26.** Orphan-position accounting bug (audit: `2026-05-26_sub_bot_orphan_audit.md`) silently corrupted bot's reported P&L. Broker-truth numbers above are documented for historical record only; they should NOT be used to inform the variant decision because the orphan rate per variant is itself a confound (different exits = different orphan exposure = different "real" outcomes).
```

Going forward (2026-05-27 onward, post-fix), the daily report uses broker-truth as the canonical signal. The bot's reported `daily_pnl` becomes a sanity-check field, not the source of truth.

### A/B/C running totals JSON

Add a `data_corrected` flag per day. Today's entry gets `data_corrected: "excluded_for_orphan_bug"`. Subsequent days get `data_corrected: false` if bot vs broker agree within $50, or `data_corrected: "broker_truth_used"` if they diverge.

---

## Sub-bot launch tomorrow

Per Manny: sub-bots stay OFF until Lever 1 ships. Main bot can continue running on IBKR paper (squeeze + WB exit bugs are the same class, but main bot has the partial Lever 3 already via `reconcile_positions_on_startup`).

**Decision tree for tomorrow morning:**

- If CC ships Lever 1 BEFORE 02:00 MT cron → daily_run_v3.sh launches all 4 bots normally. Lever 2 and 3 may land same-day or next-day.
- If CC ships Lever 1 AFTER 02:00 MT cron → comment out the 3 sub-bot launch lines in daily_run_v3.sh for the day. Main bot still runs. Lose one day of A/B/C clock.
- If CC can't ship Lever 1 within 24h → escalate scope (drop Lever 2 or 3 from initial ship, get Lever 1 in tomorrow, follow up with Lever 2+3 later this week).

---

## Operational impact

- **3-4 week A/B/C clock**: today (2026-05-26) data discarded for variant comparison. Tomorrow (2026-05-27) is now Day 1 effectively. Decision date shifts from ~2026-06-17 to ~2026-06-18 if we lose tomorrow too. Real-money date ~2026-06-22 unchanged because timeline includes buffer.
- **YTD backtest reframe**: the YTD's −$17,897 was sim-only, no orphan bug, so that result stands. But the *live* operating numbers we'd been monitoring for weeks have been bug-corrupted. Variant A today: bot said -$1,549, broker said +$419. If this directional bias is typical, our prior on live strategy economics improves substantially.
- **No real money exposure today**: paper accounts. Manny manually flattened the orphans. Lever 1 alone prevents this from happening even on paper.

---

## What this directive does NOT change

- Watchdog (commit `0aa9688`) keeps running unchanged. Independent codepath, no interaction.
- A/B/C test variant definitions unchanged.
- Real-money go-live still ~2026-06-22.
- Regime-shift, fade-gate, chase-skip-arm-preservation fixes all stay in.

---

## Deliverable

`cowork_reports/2026-05-26_orphan_fix_impl_notes.md`:
- Which levers shipped in this commit and which (if any) were deferred
- Smoke test: simulate a partial-fill or no-fill scenario, confirm position stays alive
- Smoke test: confirm `_reconcile_with_broker` correctly adopts a planted orphan and flattens a phantom
- Any spec deviations and why (e.g., if Lever 2's bid-fetch helper required more wiring than scoped)
- Sample log lines for each new path (EXIT PARTIAL, EXIT NO-FILL, EXIT RETRY, RECONCILE ADOPT, RECONCILE FLATTEN)

---

## Sequencing

Order of operations for CC:

1. **Lever 1 sub-bot** (~30 min) — minimal viable fix, stops mis-accounting immediately
2. **Lever 1 main bot WB path** (~20 min) — sister bug, simple shape
3. **Lever 1 main bot squeeze path** (~45 min) — tricky async pattern, needs `exit_in_flight` flag
4. **Smoke test Lever 1** — simulate partial fill, confirm position stays alive on retry
5. **Lever 3 sub-bot** (~30 min) — new `_reconcile_with_broker` method
6. **Lever 3 main bot** (~20 min) — periodic invocation of existing `reconcile_positions_on_startup`
7. **Smoke test Lever 3** — plant a synthetic orphan, confirm adoption
8. **Lever 2 sub-bot + main bot** (~60 min) — cancel + replace logic, env-gated
9. **Smoke test Lever 2** — timeout scenarios, retry behavior
10. **`abc_compare_daily.py` broker-truth reconstruction** (~30 min)
11. **Update today's A/B/C report with the corruption note**
12. **Push, commit message**: `fix: orphan position handling (Levers 1-3, sub-bot + main bot)`

Target: Lever 1 (steps 1-4) ships within ~2 hours. Full directive done within ~4 hours.

If CC can ship Lever 1 alone before tonight's downtime ends (whenever Manny goes to bed), daily_run_v3.sh launches all 4 bots normally at 02:00 MT. Levers 2 and 3 land before tomorrow's market close, in time for the next day's clean comparison.

---

## Open questions for Manny

1. **Lever 2's "aggressive discount pct"** — I scoped 0.5% below current bid as the aggressive re-price. Is that too aggressive (lose money on the difference) or not aggressive enough (still slow-fills)? Default to 0.5%, tunable.
2. **Lever 3 adopted-position conservative defaults** — ±5% stops/targets feels right for unknown intent, but a regime-shift entry typically uses 1.5R target. We'd be selling the runner too early. Acceptable for v1 — we're prioritizing not losing the position over optimizing the exit. Worth revisiting once we have data.
3. **Should main bot's `state.open_short` (line 1120, 1149, 3658, 3755) get the same treatment?** Same bug pattern likely. Out of scope for this directive unless you flag it as needed.
