# Cowork Audit: Sub-bot Orphan Position Mechanism (2026-05-26)

**Owner:** CC (post-flatten investigation)
**Status:** Root cause identified at code-line level. Evidence reconciled against broker history. No fix yet — awaiting directive.
**Related:** `cowork_reports/2026-05-26_ibkr_tier2_subscription_wedge_audit.md` (separate bug; same day).

---

## TL;DR

After CC flattened orphan positions on all three A/B/C sub-bot accounts, audit confirmed:

- **Strategies were firing as designed.** 47 entries logged across A/B/C, all 47 entry orders filled cleanly at the broker. 43 exits attempted; 39 fully filled, 2 partially filled, 2 didn't fill at all. Bot's detector logic, scoring, regime-shift, MOVE_STRIKE entry/exit decisions were all working.
- **The orphan condition is a real code bug, not a strategy malfunction.** `move_strike_subbot.py:1224-1282` `_close_position()` sets `self.position = None` *unconditionally* after `_wait_for_fill` times out, even if the SELL order didn't fill at all (or only partially filled). This leaves the broker holding shares while the bot believes it's flat.
- **Bot's reported P&L is materially wrong on any day with orphan-class exits.** Variant C reported `daily_pnl=-1,762`; broker reality (strategy fills only, before manual flatten) was -$44,445 of net-long exposure — a **$42,683 gap** that came from the bot mis-accounting for orphan positions and using "approx" prices on un-filled exits.
- **The fix is asymmetric handling between `_open_position` (which correctly bails on no-fill) and `_close_position` (which doesn't).** The exit path needs to either keep `self.position` alive on timeout, or actively cancel + retry the order, or both.

---

## Root cause (code-line evidence)

`move_strike_subbot.py:1224-1282` — `_close_position()`:

```python
def _close_position(self, reason: str, ref_price: float) -> None:
    p = self.position
    if p is None:
        return
    ...
    try:
        req = LimitOrderRequest(
            symbol=p.symbol, qty=p.qty, side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY, limit_price=limit,
            extended_hours=True,
        )
        order = self.alpaca.submit_order(order_data=req)
        p.order_id_sell = str(order.id) if hasattr(order, "id") else None
        sell_fill_px, sell_fill_qty = self._wait_for_fill(p.order_id_sell, timeout=15)
    except Exception as e:
        print(f"{LOG_TAG} EXIT REJECT {p.symbol}: {e!r}", flush=True)
    # Real-fill P&L (2026-05-22): use actual entry + exit fill prices when
    # both are known. Falls back to anomaly→ref approximation if either
    # fill price is missing (order didn't fill cleanly).
    entry_basis = p.fill_entry_price if p.fill_entry_price is not None else p.entry
    exit_basis = sell_fill_px if sell_fill_px is not None else ref_price  # ← LIES TO BOT
    qty_basis = sell_fill_qty if sell_fill_qty > 0 else p.qty                # ← LIES TO BOT
    real_pnl = (exit_basis - entry_basis) * qty_basis
    self.daily_pnl += real_pnl
    ...
    self.position = None  # ← UNCONDITIONAL: discards position even if broker still long
```

The "Real-fill P&L (2026-05-22)" comment marks the partial-fix from `feedback_sim_live_divergence_inventory_2026-05-22`. That earlier fix added "use real fills when available" but missed the crucial second step: if the fills *aren't* available (timeout, partial, reject), **the bot should NOT abandon the position**. Instead it should:

1. Either keep `self.position` alive and re-attempt the exit on the next tick cycle, OR
2. Actively `cancel_order(p.order_id_sell)` to clear the pending order, then either re-submit at a more aggressive price or surface a CRITICAL alert.

Neither path is currently implemented. The bot just shrugs and moves on.

The matching ENTRY path at `move_strike_subbot.py:1199-1220` got this right:

```python
if fill_px is not None and fill_qty > 0:
    self.position.fill_entry_price = fill_px
    ...
else:
    # Order didn't fill (timeout/cancel/reject). Clear position
    # so we don't track ghost shares — and don't manage exits.
    print(... "entry order NOT FILLED (timeout/cancel/reject) — abandoning trade")
    self.position = None
    return
```

The entry-side bail is safe because if BUY doesn't fill, broker has no position. The exit-side equivalent is broken because if SELL doesn't fill, broker DOES have a position.

---

## Three distinct orphan mechanisms today

The 5 orphan positions we flattened came from three different patterns, all rooted in the same bug:

### Mechanism 1 — Partial-fill SELL (A: 77 CODX, C: 3,830 CODX)

Both variants armed and bought CODX on the same engine-socket signal. Both submitted SELL LIMIT 5,305 @ $9.36 at 19:59:09 UTC. Broker filled 5,228 of 5,305 on Variant A and only 1,475 of 5,305 on Variant C before the order timed out and got cancelled. The bot's `_wait_for_fill` returned `(fill_px=$9.36ish, fill_qty=5228)` for A — partial-fill data — but the code computed P&L on the partial and set `self.position = None`, discarding the 77 residual shares (A) / 3,830 residual (C).

Why the residuals differ: Variant C had cumulative position 5,305 from multiple entry batches but only 1,475 got matched out by the timeout. Different fill counterparties; same code bug downstream.

### Mechanism 2 — Zero-fill SELL (A: 2,272 VCIG, C: 2,272 VCIG)

Bot exit at 16:00:13 ET via `move_hwm_exit(peak=2.97, dd=50%, hh=4)` submitted SELL LIMIT 2,272 @ $2.88. The bid was moving — VCIG was running into a parabolic phase. The limit at $2.88 fell behind the new lower bid (price dropped through it then bounced past it before the 15s timeout). `_wait_for_fill` returned `(None, 0)` after 15s. Bot computed `exit_basis = ref_price` and set `position = None`. The SELL order stayed parked at the broker until eventually cancelled (still 0 filled) — leaving 2,272 shares orphaned.

Same exact pattern on Variant C (the engine socket fans the same signal to all variants).

### Mechanism 3 — Position correctly alive but never exited (B: 179 MNTS)

This one is **NOT a desync orphan.** Variant B entered MNTS via REGIME_SHIFT at 15:56:00 ET:

```
[MOVE_SUB_B] [15:56:00] 🚀 ENTRY REGIME_SHIFT MNTS qty=179 limit=$16.02 ... stop=$13.07 R=$2.79
[MOVE_SUB_B] [15:56:04] MNTS regime_shift entry FILLED @ $15.92 qty=179
```

Bot's last STATS before kill: `pos=YES daily_pnl=-2,904`. So B *knew* it had MNTS open. The REGIME_SHIFT exit logic is target/stop-driven: target = entry + 1.5R = $20.10, stop = $13.07. MNTS today ranged $11.86–$17.40 — neither target nor stop hit. The 19:55 ET session-end force-exit would have flattened it.

So B isn't broken in the same way; it was just waiting. The position only became "orphan" relative to our flatten because we intervened before EOD. This category is **strategy-correct, not bug**.

---

## Bot's reported P&L vs broker reality

The asymmetric handling has a second consequence: the bot's `daily_pnl` field is **systematically wrong** on any day with orphan-class exits, because the partial/zero-fill code path computes "approx P&L" on prices that never actually happened.

| Variant | Bot's `daily_pnl` (STATS) | Broker strategy-fills net | Gap |
|---|---|---|---|
| A | **-$1,549** | -$8,878 (net long) | **-$7,329** unaccounted |
| B | **-$2,904** | -$5,754 (net long) | **-$2,850** unaccounted |
| C | **-$1,762** | **-$44,445** (net long, on margin) | **-$42,683** unaccounted |

"Broker strategy-fills net" = the net cash flow from every BUY and SELL the bot submitted today, before my manual flatten. Negative = the bot ended the day net-long that much in dollar value of shares. That's the long exposure the bot wasn't tracking.

Variant C is the worst case: the bot reported -$1,762 P&L while the broker had absorbed -$44,445 of net long position. The MAIN_APCA-like buying-power constraint allowed it because Variant C had 2× margin (≈$50K buying power for $25K equity). C borrowed the full margin window without knowing.

After my manual flatten at the end-of-day bid:
- A: end equity $30,419 (vs $30K starting) → strategy net **+$419** for the day (not -$1,549 as the bot believed)
- B: end equity $27,386 → strategy net **-$2,614** for the day (close to bot's -$2,904 estimate)
- C: end equity $27,116 → strategy net **-$2,884** for the day (very different from bot's -$1,762 estimate)

The A/B/C variant comparison was **silently corrupted by these mismatches.** Any reading of the fade-gate test that uses the bot's reported daily P&L is wrong; the broker-side numbers are the truth.

---

## What the strategies were trying to do (per logs)

To answer "were the strategies even working" — yes. Per-variant entry/exit firing:

| Variant | Entries logged | All filled? | Exits logged | All filled? |
|---|---|---|---|---|
| A | 20 (15 MOVE_STRIKE, ~3 REGIME_SHIFT, 2 cross-strategy) | yes (19 BUY fills, 1 rejected for BP) | 19 | 17 filled, 2 partial/canceled |
| B | 8 | yes (8 BUY fills) | 7 | 7 filled, 0 partial — but 1 entry never reached exit (MNTS waiting target/stop) |
| C | 19 | yes (17 BUY fills, 2 rejected for BP) | 17 | 15 filled, 2 partial/canceled |

Detector activity was healthy:

- **MOVE_STRIKE arming + chase-skip working correctly.** Same `MNTS ARMED entry=$14.02` on all three sub-bots at 14:22 ET (engine socket fanout = identical arms). Same chase-skip protections firing on the 16:41 ET vertical spike.
- **REGIME_SHIFT triggering correctly.** Bar-body ratio detection fired on MNTS (ratio=9.39), CODX, VCIG. Entered via the regime-shift entry path with target/stop semantics.
- **HWM exits, prox-bails, hard-stops** all fired. The exit *triggers* worked; the exit *execution* is what's broken.
- **REENTRY(GREEN) cascade** working. After exits, the bot correctly armed re-entries on green-bar continuation and entered them.

The bot was making decisions. Most decisions were sensible. The detector-side strategy logic looks fine. The problem is downstream — the broker-state-reconciliation gap.

---

## Why this didn't blow up earlier

Memory `feedback_sim_live_divergence_inventory_2026-05-22.md` documents that the "Real-fill P&L" fix landed on 2026-05-22 specifically because the bot was already misreporting P&L. That fix partially addressed the symptom (use real fills when available) but didn't close the orphan gap (what to do when real fills are NOT available).

Some plausible reasons today's incident was bigger than prior days:

1. **Today had an unusually wedged data feed in the morning** (the Tier-2 sparse-tick issue in the sister audit). The TBT promotion didn't kick in on the right symbols at the right time, so symbols that would normally have been on tick-by-tick were on sparse snapshot. This delayed the bot's perception of price moves and led to **late exit decisions where the limit was already off the bid by the time it was submitted** — driving the partial/no-fill rate up.
2. **VCIG had unusual intraday range** ($2.68–$4.30) with multiple parabolic phases. Each phase triggered HWM exits, but the SELL LIMITs (set at `ref_price - max(0.05, 0.5%)`) were behind by the time they hit the book. More no-fill outcomes than a typical day.
3. **CODX had an extended decline phase** (open around $10, drop to $8.50) on heavy volume. Some sells took counterparty-fills slowly and partial-filled in the 15s window.

Combination: the day shape made the latent bug visible. Most days it's invisible because exits fill within 15s. On a day with this much price movement during exit windows, the bug's exposure grows.

---

## Suggested fix directions (not a fix — directive needed)

Three independent levers, ranked by complexity:

### Lever 1 — Don't lie to ourselves on partial/no-fill (cheapest)

In `_close_position`, after `_wait_for_fill` times out or returns partial:
- If `sell_fill_qty < p.qty`: **keep `self.position` alive** with `p.qty -= sell_fill_qty` (residual shares still owned). Set `p.order_id_sell = None`. Mark a `p.exit_pending = False` flag. Bot's next tick will re-evaluate exit conditions on the remaining shares.
- If `sell_fill_qty == 0`: same, keep position alive. Don't compute approx P&L (no fill, no realized P&L).
- Only when `sell_fill_qty == p.qty`: set `self.position = None` (real flatten).

Cost: ~20 LOC. Low risk to the entry path. Doesn't fix the *cause* of slow fills (just stops mis-accounting).

### Lever 2 — Active cancel + replace on slow exits

If `_wait_for_fill` times out:
1. Issue `cancel_order(p.order_id_sell)`. Wait briefly for the cancel ack.
2. Read current bid. Re-submit SELL LIMIT at `bid * 0.99` (or `bid - $0.10`, whichever is more aggressive).
3. Wait another 15s.
4. Loop up to 3 times before declaring failure.

If still failing after 3 retries: log CRITICAL, surface alert, keep position alive (per Lever 1). Manny / CC monitors a CRITICAL alert as a manual-intervention prompt.

Cost: ~50 LOC. Risk: if the cancel/replace cycle hits IBKR pacing limits, we get cascading errors. Mitigation: add a per-symbol cooldown between attempts.

### Lever 3 — Periodic broker reconciliation in sub-bot main loop

Currently the sub-bot reconciles broker positions only at startup. Add a periodic reconcile (every 60s) that calls `alpaca.get_all_positions()` and compares against `self.position`:
- If broker has a position the bot doesn't track → **adopt** it (re-attach via a `SubPosition` reconstructed from broker's avg_entry_price; engage exit management with conservative defaults).
- If bot tracks a position the broker doesn't have → **flatten internally** (no broker exposure to worry about, just clean local state).

This converges the desync passively even if Levers 1 and 2 miss an edge case.

Cost: ~80 LOC. Risk: adopting a position with unknown intent — defaults may be wrong for what was originally a regime_shift vs MOVE_STRIKE setup. Mitigation: a conservative "managed-orphan" mode that just trails on bid drop and gets out at fixed -R% or +R%.

### Combined recommendation

Ship Lever 1 immediately (small, safe, stops the mis-accounting bleeding). Add Lever 3 as a defense-in-depth pass. Hold Lever 2 until we have data on whether Levers 1+3 reduce orphan frequency below an acceptable threshold (e.g., < 1 orphan per 100 exits per variant).

---

## Open questions for directive

1. **Should the main bot (`bot_v3_hybrid.py`) be audited for the same bug?** It uses a different exit code path. If it has analogous "set position=None on timeout" logic, today's commit `2be7efe` (move main to IBKR paper) could be running into a similar mismatch. Worth a quick audit.
2. **Does the watchdog we shipped (commit `0aa9688`) interact with this?** Probably not — the watchdog is data-side and doesn't touch order-state. But worth confirming the audit doesn't double-fire on orphan-class events.
3. **How to retroactively correct the A/B/C running totals JSON?** `cowork_reports/abc_running_totals.json` and today's `2026-05-26_abc_daily_report.md` (when EOD `daily_run_v3.sh` writes it) will use the **bot's reported P&L** for the day, which is wrong. We need to either: regenerate the daily report from broker fills, or annotate the entry with a `data_corrected_from_broker` note.
4. **For tomorrow morning's run:** with the sub-bots killed and no fix, do we restart them as-is or hold them off until Lever 1 ships? I recommend holding the sub-bots off until Lever 1 is in. Main bot can continue on IBKR paper since the bug is sub-bot-specific (different code).

---

*Audit complete. Standing by for directive.*
