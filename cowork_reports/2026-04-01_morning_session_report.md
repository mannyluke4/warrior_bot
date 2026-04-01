# Morning Session Report: 2026-04-01 (Wednesday)
## Branch: v2-ibkr-migration

---

## Executive Summary

**First morning with both V1 (Alpaca) and V2 (IBKR) running side by side.** V2 started at 02:34 ET but Gateway crashed at 04:04 ET (IBKR daily maintenance). Restarted at 08:38 ET. V1 ran the full session. Neither bot produced profitable trades — a tough morning for squeeze setups.

Key finding: **V1 sees more stocks than V2** because Alpaca scans ~10,000 stocks locally vs IBKR's `reqScannerData` returning a pre-filtered top-20. V1 found VOR and APLX; V2 never saw them.

---

## Timeline

| Time (ET) | Event |
|-----------|-------|
| 02:34 | V2 started manually, Gateway UP, bot connected, KIDZ from watchlist.txt |
| 02:34 | V1 started, scanning 500 symbols via Alpaca |
| 04:00 | V2 morning window opens, catchup scan finds 0 candidates (too early) |
| 04:04 | **V2 Gateway CRASHES** — IBKR daily maintenance window |
| 04:21 | V1: VOR entry signal at $18.50 (MP signal, premarket) |
| 04:38 | V1: VOR second entry signal at $18.85 |
| 07:54 | V1: APLX armed and entry signal at $11.92 (flat top breakout) |
| 08:31 | V1: APLX found by rescan (+41.2% gap) |
| 08:38 | **V2 restarted** — catchup scan finds BCG, CYCN, ELAB, KIDZ, RENX |
| 09:31 | V1: VOR squeeze entry at $19.32, chased 3 times, gave up — but Alpaca filled anyway |
| 09:33 | V1: APLX squeeze entry at $12.01, filled 2083 shares, immediately max_loss_hit → exit $11.90 |
| 09:33-09:43 | V2: RENX primed 4 times (3.2-5.1x volume) but never armed (no level break) |
| 09:51 | V1: NPT entry signal at $8.40 |
| 11:00 | V2 morning window closes. 0 trades. |
| 11:08 | V1 still running. 0 managed trades (VOR and APLX orphaned in Alpaca) |

---

## V2 (IBKR) — 0 Trades

| Stock | Discovery | Activity | Result |
|-------|-----------|----------|--------|
| KIDZ | watchlist.txt (yesterday) | IDLE all morning, low volume | No trade |
| BCG | Catchup 08:38 | IDLE, vol_ratio=0.2x | No trade |
| CYCN | Catchup 08:38 | IDLE, vol_ratio=1.0x | No trade |
| ELAB | Catchup 08:38 | SQ_REJECT: not_new_hod (below $8.44 HOD) | No trade |
| RENX | Catchup 08:38 | **SQ_PRIMED 4x** (3.2-5.1x vol) but never armed | No trade |

RENX was the closest to a trade — massive volume spikes at 09:33-09:43 but the price never broke PM high or a whole dollar level within the prime window.

---

## V1 (Alpaca) — 2 Orphaned Positions

V1 entered VOR and APLX but lost track of the positions. Alpaca dashboard shows both open; bot heartbeat shows `open=0`.

### VOR
- **09:31**: Squeeze entry signal at $19.32 (PM high break, score=15.0)
- Chased 3 times ($19.38 → $19.44 → $19.25), all timed out → GIVE UP
- **But Alpaca filled after the give-up** → orphaned position
- Backtest (IBKR ticks): Entry $19.34, bail timer exit at $19.32 = **-$12**

### APLX
- **09:33**: Squeeze entry at $12.00 (PM high break, flat top, score=15.0)
- Filled at $12.01 (2083 shares)
- Immediately hit max_loss_hit (0.8R > 0.75R cap) → exit submitted at $11.86
- Exit shows as filled in logs but **Alpaca still shows position open**
- Backtest (IBKR ticks): Entry $12.02, para trail exit at $11.99 = **-$107**

### GVH (V1 only)
- Entered $2.47, exited $2.34, **-$331** (max_loss_hit) — this one managed correctly

---

## Backtest Verification (IBKR Ticks)

Fetched real IBKR tick data for all three V1 stocks and compared bar mode vs tick mode:

| Stock | Bar Mode | Tick Mode | Notes |
|-------|----------|-----------|-------|
| VOR | -$249 (stop hit) | **-$12** (bail timer) | Bar mode false stop — tick path shows flat, not stop |
| APLX | -$391 (stop hit) | **-$107** (para trail) | Smaller loss on real ticks |
| NPT | 0 trades | 0 trades | Armed but never triggered |

**Bar mode overstates losses by 5x** on today's stocks. Real tick data shows much smaller losses. This reinforces why tick-mode backtesting is essential.

---

## V3 Databento Scanner Results

V3 unified scanner found 2 candidates for today:
- **BCG**: discovered 07:02, +80.6% gap, 1.5x RVOL, 2.76M float
- **CYCN**: discovered 07:15, +72.9% gap, 1.6x RVOL, 2.71M float

Neither VOR nor APLX passed V3's filters (VOR: price $19 near upper limit, APLX: $12 but low RVOL on Databento data). These were found by V1's broader Alpaca scan only.

---

## Infrastructure Issues

### 1. Gateway Crash at 04:04 ET
IBKR performs daily maintenance around 04:00-04:30 ET. The Gateway connection drops and doesn't recover. The reconnection logic in bot_ibkr.py should handle this but didn't catch it — the bot died silently.

**Fix needed:** Add IBKR maintenance window awareness — expect disconnection around 04:00-04:30, auto-reconnect after.

### 2. V1 Orphaned Positions
V1 lost track of VOR (filled after GIVE UP) and APLX (exit fill not registered). These positions are sitting unmanaged in Alpaca.

**Action needed:** Manually close VOR and APLX in Alpaca dashboard.

### 3. Databento Live Scanner Failed
`live_scanner.py` errored on today's date — Databento's historical API doesn't have today's data yet for ADV computation. Needs to use yesterday's ADV as fallback.

---

## Key Takeaways

1. **Scanner coverage is the #1 bottleneck.** V1 found VOR and APLX through Alpaca's broad 10K-stock scan. V2's IBKR scanner (20 stocks) and V3 Databento (filtered to 2) both missed them.

2. **Today was a losing morning regardless.** VOR -$12, APLX -$107, GVH -$331. The strategy correctly identified squeeze setups but the stocks didn't follow through. Not every squeeze works.

3. **V2 missing 04:00-08:38 is critical.** The IBKR maintenance crash cost 4.5 hours. RENX's prime activity at 09:33 happened after restart, but earlier opportunities may have been missed.

4. **Tick mode vs bar mode matters.** Bar mode showed -$640 total losses; tick mode showed -$119. Always use tick data for accurate P&L.

---

## Bot Status at Report Time

- **V2 (IBKR):** Dead zone (sleeping until 16:00 ET evening session)
- **V1 (Alpaca):** Running, 2 orphaned positions (VOR, APLX) in Alpaca
- **Gateway:** UP
- **Caffeinate:** Active
