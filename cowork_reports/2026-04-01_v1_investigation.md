# V1 Bot Investigation — April 1, 2026

## Q1: What strategy was active?

```
WB_SQUEEZE_ENABLED=1     # Squeeze ON
WB_MP_ENABLED=0           # MP OFF
WB_ROSS_EXIT_ENABLED=0    # Ross exits OFF
WB_DATA_FEED=alpaca       # Alpaca data (NOT SIP — likely IEX)
WB_ENABLE_DYNAMIC_SCANNER=1  # Alpaca MarketScanner
```

All 4 trades were **squeeze entries** (setup_type=squeeze). MP fired multiple ENTRY SIGNALs on VOR, GVH, APLX, and ELAB in premarket but were blocked by `MP_DISABLED`.

## Q2: The 4 Trades

### Trade 1: VOR — PHANTOM (bot never filled, Alpaca may have)

- **09:31:02** — SQ PRIMED + ENTRY SIGNAL @ $19.32, R=$0.77, score=15.0
- **09:31** — ENTRY SUBMITTED, limit $19.38, qty=324
- **09:32** — ENTRY TIMEOUT after 32s, cancel requested
- **09:32** — ENTRY REPLACED x3 (limits: $19.44, $19.44, $19.25)
- **09:33** — ENTRY GIVE UP after 3 attempts

**Root cause:** VOR was moving fast. All 3 limit attempts timed out (30s each). The bot gave up. However, the directive says Alpaca shows VOR was bought (324 shares at 07:32) and manually sold at 09:11. This is a DIFFERENT VOR trade — **the 07:32 entry doesn't appear in the squeeze logs at all**. The MP detector fired VOR signals at 04:21 and 04:38 but they were blocked by MP_DISABLED. The 07:32 trade must be from a different source or the timestamp is misremembered.

**Alternatively:** One of the cancel-then-replace sequences may have raced — the cancel was requested but the original order filled on Alpaca's side before the cancel went through. The bot then submitted a replacement, which Alpaca rejected or double-filled. This is the classic phantom: **cancel races with fill**.

### Trade 2: GVH — Filled and exited cleanly

- **09:33:00** — SQ PRIMED + ENTRY SIGNAL @ $2.40, qty=2500
- **09:33** — ENTRY SUBMITTED, limit $2.53
- **09:33** — TIMEOUT, REPLACED with limit $2.54
- **~09:34** — Partial fills: +662, +1732, +63, +26, +13, +4 = **2500 total**
- **Fill adjusted:** $2.4724 avg (slip +$0.07)
- **MAX LOSS CAP** triggered: 0.8R loss > 0.75R cap
- **EXIT SUBMITTED** qty=2500, limit $2.33
- **EXIT FILL:** -2224 then -276 @ $2.34 = **fully exited**

**Result:** -$330 loss. **Clean lifecycle — no phantom.**

### Trade 3: APLX — Filled and exited cleanly

- **09:33:19** — SQ ENTRY SIGNAL @ $12.00 [PARABOLIC], qty=2083
- **09:33** — ENTRY SUBMITTED, limit $12.02
- **09:34** — TIMEOUT, REPLACED with limit $12.09
- **~09:34** — Partial fills: +1895, +66, +122 = **2083 total**
- **Fill adjusted:** $12.0116 avg
- **MAX LOSS CAP** triggered
- **EXIT SUBMITTED** qty=2083, limit $11.86
- **EXIT FILL:** -508 then -1575 @ $11.90 = **fully exited**

**Result:** -$211 loss. **Clean lifecycle — no phantom.**

Note: The directive says APLX had 2,083 orphaned shares. The logs show a full exit fill. The phantom may be from a DIFFERENT Alpaca order that filled during the cancel-replace sequence (same race condition as VOR).

### Trade 4: ELAB — Filled and exited cleanly

- **14:53:00** — SQ PRIMED + ENTRY SIGNAL @ $8.46 [PARABOLIC], qty=2083
- **14:53** — ENTRY SUBMITTED, limit $8.50
- **14:53** — FILL +2083 @ $8.4225 (negative slippage — good fill)
- **SQ_STOP_HIT** fired repeatedly (14+ times in logs — tick-level)
- **EXIT SUBMITTED** qty=2083, limit $8.31
- **EXIT FILL:** -2083 @ $8.36 = **fully exited**

**Result:** -$130 loss. **Clean lifecycle — no phantom.**

Note: The stop fired 14+ times because the tick handler kept checking while the exit order was pending. This is noisy but not harmful.

## Q3: Root Cause of Phantom Positions

The logs show **all exits filled cleanly** for GVH, APLX, and ELAB. The phantoms reported by the user are likely from the **cancel-replace race condition on VOR**:

1. Bot submits limit order
2. Order doesn't fill in 30s → bot sends cancel
3. **Between cancel request and cancel confirmation, Alpaca fills the order**
4. Bot doesn't see the fill (it already moved on to the replacement order)
5. Bot submits replacement order → may also fill
6. Result: Alpaca has filled shares the bot doesn't know about

This is the exact scenario Fix 2 (fill verification with retry) and Fix 3 (periodic position sync) in V3 are designed to prevent.

### VOR Specifically

VOR had **3 cancel-replace cycles**. Each one is a race window. If any of the "cancelled" orders actually filled, those shares became phantoms. The bot logged `ENTRY GIVE UP` and moved on, but Alpaca may have been holding 324 shares from one of the "cancelled" orders.

## Q4: Scanner

V1 was using `WB_ENABLE_DYNAMIC_SCANNER=1` — the Alpaca `MarketScanner`. Found VOR, GVH, APLX, ELAB through Alpaca's market data API with standard gap/volume/float filters.

## Q5: Data Feed

```
WB_DATA_FEED=alpaca
```

This means **IEX data** on Alpaca's free/paper tier (not SIP). IEX has known delays and gaps on small-caps. This likely contributed to:
- STALE FEED warnings on GVH and APLX (34-48s without updates)
- Slow fill detection (orders filling on Alpaca's side but IEX data lagging behind)

## Summary

| Trade | Symbol | P&L | Phantom? | Root Cause |
|-------|--------|-----|----------|------------|
| 1 | VOR | $-303* | YES | Cancel-replace race: order filled during cancel window |
| 2 | GVH | -$330 | No | Clean fill + max_loss exit |
| 3 | APLX | -$211 | Possible | Clean in logs, but replace race may have created dupe |
| 4 | ELAB | -$130 | No | Clean fill + stop_hit exit |

*VOR P&L from manual close, not bot exit.

**Total bot losses:** -$671 (GVH + APLX + ELAB). VOR's -$303 was user's manual close.

## V3 Fixes That Address This

1. **No cancel-replace logic** — V3 submits once, waits for fill with polling, cancels on timeout with post-cancel fill check
2. **Startup reconciliation** — catches any orphans from prior session
3. **60s heartbeat** — detects position drift during session
4. **IEX stale feed issue** — V3 uses IBKR ticks (real-time), not Alpaca/IEX for price data
