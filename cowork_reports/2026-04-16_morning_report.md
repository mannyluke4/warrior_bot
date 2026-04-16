# Morning Session Report — 2026-04-16

**Author:** CC (Opus)
**Session window:** 04:00–11:00 ET momentum
**Bot state:** Alive, PID 18168, conn=OK throughout morning
**Scope:** Morning session only per Manny's direction. Afternoon and short-strategy work tracked separately.

---

## Headline

- **Alpaca truth: +$595.27** (MYSE, 1 buy + 2 sells, clean round-trip)
- **Bot log reports: +$463** — short by $132 due to two accounting bugs identified below
- **1 symbol traded (MYSE).** No other entries. WNW and WSHP armed but never triggered during morning window; both still armed as morning closed.

Alpaca is the ultimate truth; that's where the money actually is. Bot's internal P&L is wrong and needs fixing today.

---

## MYSE — the day's one trade

```
[07:17 ET] MYSE SQ | ARMED entry=6.0200 stop=5.9000 R=0.1200 score=5.0
           level=whole_dollar setup_type=squeeze [PARABOLIC] [PROBE=50%]
[07:17:00 ET] ENTRY SIGNAL @ 6.0200 (break 6.0200)
🟩 ENTRY: MYSE qty=4316 limit=$6.07 (slip=$0.050) stop=$5.9000 R=$0.1200
  FILL: MYSE @ $6.0199 qty=4316
  ALPACA EXIT: 9172883d  SELL 3884 MYSE @ $6.17   (target hit)
  ALPACA EXIT: 6ca8e85f  SELL 432 MYSE @ $6.04    (runner trail)
```

Clean entry (parabolic squeeze probe at whole-dollar $6.00), core exited at target, runner took out on trail. This was the squeeze strategy working as designed.

### Actual Alpaca fills (3 orders total)

| Time (ET) | Side | Qty | Avg Price |
|---|---|---|---|
| 05:17:02 | BUY | 4316 | $6.0199 |
| 05:17:22 | SELL | 3884 | $6.1700 |
| 05:21:12 | SELL | 432 | $6.0488 |

P&L = (3884 × 6.17 + 432 × 6.0488) − (4316 × 6.0199) = **+$595.27**

### Account confirmation

```
Equity:      $30,195.46
Last equity: $29,600.19
Daily delta: +$595.27
```

Alpaca account API confirms the $595.27.

---

## Two phantom-P&L bugs — need fixing today (P0)

### Bug 1 — Runner exit order partial-filled, bot's qty-math diverged

The runner exit order (`6ca8e85f`, SELL 432 @ $6.04 limit) was accepted by Alpaca but only partially filled at first — 149 shares sold immediately, the remaining 283 stayed open as `held_for_orders` on the same order ID. The bot:

- Logged `🟥 EXIT: MYSE qty=432 @ $6.0700 reason=sq_runner_trail P&L=$+22` **immediately** after submitting the order, treating the full 432 as exited at the **intended limit price** ($6.07), not Alpaca's eventual average fill ($6.0488).
- True runner P&L: (6.0488 − 6.0199) × 432 = **+$12.48**, not the +$22 the bot booked.
- Magnitude: +$9.52 over-report on this leg alone.

The target-hit order similarly had a price-discrepancy: bot's exit was booked at $6.20, but the Alpaca fill shows $6.17 (3 cents lower). 3884 × $0.03 = **-$116 over-report** on the target leg.

Combined over-report from price mismatch: ~$125.

### Bug 2 — Orphan-detection mistakenly counted `held_for_orders` as stranded

While the 283 shares were still "held" by the open runner order awaiting fill, the bot's `periodic_position_sync` fired three times at 60-second intervals. Each time:

```
⚠️ ORPHAN DETECTED: Alpaca holds MYSE qty=283 entry=$6.02 — bot unaware. Adopting.
ALPACA EXIT FAILED: {"available":"0","code":40310000,"existing_qty":"283",
"held_for_orders":"283","message":"insufficient qty available for order",
"related_orders":["6ca8e85f-5687-402b-8f7a-828fbcc12f91"],"symbol":"MYSE"}
ALPACA MARKET EXIT ALSO FAILED: (same error)
🟥 EXIT: MYSE qty=283 @ $5.70 reason=stop_hit P&L=$-91 daily=$+630
```

The exit order failed both ways (limit + market fallback) — Alpaca correctly rejected because the shares were already committed to the open runner order. **But the bot still logged a $-91 P&L entry** as if the exit had happened.

This repeated 3 times as the runner order stayed partially open:
- -$91 at 283 × ($5.70 − $6.02) — failed, but recorded
- -$110 at 283 × ($5.63 − $6.02) — failed, but recorded
- -$57 at 283 × ($5.82 − $6.02) — failed, but recorded
- **Total phantom losses: -$258**

None of these 3 events touched Alpaca's position. Zero shares changed hands. But `state.daily_pnl` got -$258 added to it.

### Why the bot's +$463 is wrong

```
Target hit (bot log):   +$699  (actual Alpaca: +$582.60, over by $116)
Runner (bot log):        +$22  (actual Alpaca:  +$12.48, over by $10)
Phantom -$91:            -$91  (didn't happen)
Phantom -$110:          -$110  (didn't happen)
Phantom -$57:            -$57  (didn't happen)
Bot total:              +$463

Alpaca truth:           +$595.27
Bot error:              -$132  (net under-report)
```

The price over-report ($126) minus the phantom loss over-report ($258) = $132 under-reported total.

### Root-cause files

- `bot_v3_hybrid.py:exit_trade()` — records P&L using the intended `price` argument + full `qty` at the moment of order submission, before any Alpaca-side fill confirmation. Should mirror the entry path's approach (`_verify_fill_with_retry` already uses Alpaca's actual `filled_avg_price` / `filled_qty`).
- `bot_v3_hybrid.py:reconcile_positions_on_startup()` + `periodic_position_sync()` — treats any Alpaca position the bot "doesn't know about" as an orphan to flatten. Must check if `held_for_orders > 0` on that symbol first; if yes, the shares are already being acted on, don't double-flatten.

### P0 fix today

1. `exit_trade()` verification — defer P&L recording until Alpaca reports `status=filled` on the exit order. On `partially_filled`, record only the actually-filled qty and average price. On `cancelled` / `rejected`, record nothing.
2. `reconcile/orphan` — query `get_open_positions` + `get_orders(status="open")` together. If a position's `qty` ≤ sum of `held_for_orders` on that symbol, treat it as in-flight, not orphan.

Both are bot-side only; sim is unaffected.

---

## Armed setups that didn't trigger

| Symbol | Arm price | Outcome |
|---|---|---|
| WNW | $6.02 | Still armed at 11:00 ET — never broke trigger, price ran 4.30–6.10 range without a clean break |
| WSHP | $17.02 | Still armed at 11:00 ET — hovered 15.50–17.20 range, tested trigger but no break high enough to arm entry |

Both carried into the box window. Worth watching both in this afternoon's session since they're already in "memory."

---

## Heartbeat cadence (clarification, not a bug)

Bot prints status lines at `now.second < 2` in the main loop — **2 lines per minute** (at :00 and :01 seconds). This is the designed cadence in `bot_v3_hybrid.py:2826`. Historical sessions show the same pattern; 2026-04-15's 09:xx ET gap was the IBKR-data-farm connectivity crisis dominating the log, not a throttle change.

If more-frequent heartbeats are wanted, one-line fix: change `now.second < 2` → `now.second % 15 == 0` (4/min) or `now.second % 5 == 0` (12/min).

---

## Morning session summary

- **Alpaca P&L: +$595.27** (authoritative)
- **Trades: 1 MYSE round-trip** (1 buy + 2 sells on Alpaca's books)
- **Bot log P&L: +$463** (incorrect — two accounting bugs above)
- **Symbols watched: 5** (BTOG, KIDZ, MYSE, WNW, WSHP)
- **Arms still open at close: 2** (WNW, WSHP carry into afternoon)
- **Uptime: clean** — conn=OK across the session, no tick droughts, no CRITICAL messages
- **Gateway health: stable** after this morning's manual restart (nightly-reset issue from 2026-04-15 → 2026-04-16 noted separately)

---

*CC (Opus), 2026-04-16 late morning. Phantom P&L fix lands today. Squeeze strategy itself is working — that's the good news underneath the accounting issue.*
