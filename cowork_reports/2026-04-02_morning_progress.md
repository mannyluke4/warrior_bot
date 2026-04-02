# V3 Hybrid Bot — Morning Session Report (April 2, 2026)

**Bot version:** V3 Hybrid (IBKR data + Alpaca execution)
**Squeeze detector:** V2 with rolling HOD gate
**Session start:** 06:17 ET (manual restart — cron's 4 AM launch failed, Gateway didn't open port 4002 in time)
**Session end:** 12:00 ET (dead zone)
**Result:** 0 trades, $0 P&L. Successful infrastructure shakedown.

---

## Verdict: Successful First Live Session

V3 ran for 6 hours without crashes, connection drops, or phantom positions. All systems worked:
- IBKR data feed: stable, 1800-2800 ticks/min across 4 symbols
- Alpaca execution: connected, position sync clean, no orphans
- Squeeze V2 detector: fired correctly on volume spikes
- Gateway watchdog: monitored port 4002 throughout
- Databento scanner: contributed KIDZ via watchlist.txt bridge
- Tick cache: saved to disk for backtesting

No trades is the correct outcome for today's stocks — confirmed by backtesting against live tick data.

---

## Watchlist: 4 Stocks

### BATL (Batalon Brands)
- **PM high:** $5.48 | **VWAP:** ~$5.17
- **07:10 ET — SQ_PRIMED:** vol=3.3x, bar_vol=57,773, price=$5.25 above VWAP
- **07:13 ET — SQ_RESET:** prime_expired (3 bars, no level break)
- Price needed $0.22 more to break PM high. Faded after, never recovered.
- **Backtest confirms:** 0 trades. Correct.

### SKYQ (SkyQuest Technology)
- **PM high:** $6.51 | **VWAP:** ~$5.50
- **Discovered:** 07:36 ET by IBKR scanner (first appearance)
- **07:38 ET:** Massive volume explosion (128.6x avg, 197K shares). Broke $6.00 whole dollar.
- **Bot missed it** — SKYQ wasn't subscribed until the scanner found it at 07:36, and the move that triggered the scanner IS the move that created the trade.
- **Backtest from 07:00:** Sim finds 1 trade (+$36, entered 07:39, exited immediately via para trail). Marginal.
- **Backtest from 07:50 (actual discovery time):** 0 trades. Armed once but never triggered. Matches live bot exactly.
- **09:00 ET spike:** $6.07→$6.50 (vol=2.0x avg). Did NOT trigger PRIMED — vol_ratio only 2.0x vs 3.0x threshold.
- Faded hard after, closed at $4.11.

### TURB (Turbine Truck Engines)
- **PM high:** $4.76 | **VWAP:** ~$3.49
- Faded all morning from $3.90 to $3.25
- **09:40 ET — SQ_PRIMED:** vol=6.4x, bar_vol=116,929, price=$3.67 above VWAP. Big green bar.
- Stayed PRIMED but never ARMed — nearest level was $4.00 whole dollar (+9% away). Too far.
- **Backtest confirms:** 0 trades. Correct.

### KIDZ (OraSure/KIDZ)
- **Source:** Databento scanner (watchlist.txt)
- **PM high:** $4.05 | **VWAP:** ~$3.58
- Essentially dead tape all morning. 0-22 ticks per minute. No squeeze activity.
- **Backtest confirms:** 0 trades. Correct.

---

## Squeeze Detector Activity

| Time | Symbol | Event | Outcome |
|------|--------|-------|---------|
| 07:10 | BATL | SQ_PRIMED (3.3x vol) | RESET after 3 bars — no level break |
| 07:38 | SKYQ | 128.6x vol spike | Bot wasn't subscribed yet (scanner latency) |
| 09:40 | TURB | SQ_PRIMED (6.4x vol) | Stayed PRIMED — $4.00 level too far (+9%) |

---

## Key Insight: Scanner-Move Paradox

The SKYQ 07:38 move illustrates a fundamental limitation: **the volume spike that creates the trade opportunity is the same spike that makes the scanner discover the stock.** By the time the bot subscribes and builds enough bars, the initial move is done.

Possible mitigations:
1. Pre-load a broader watchlist from Databento before market open (already partially done via live_scanner.py)
2. Faster IBKR scanner cycles (currently every 5 min)
3. Accept that the bot catches the *second* move, not the first — and size accordingly

---

## Backtest vs Live Comparison

| Stock | Live Bot | Sim (from discovery time) | Match? |
|-------|----------|--------------------------|--------|
| BATL | 0 trades | 0 trades | YES |
| SKYQ | 0 trades | 0 trades (from 07:50) | YES |
| TURB | 0 trades | 0 trades | YES |
| KIDZ | 0 trades | 0 trades | YES |

**100% match.** The detector logic is working correctly. The bot made the right decisions given what it could see.

---

## Infrastructure Issues

1. **Cron launch failed at 4 AM:** Gateway didn't open port 4002 within 180s. Root cause: display session inactive. Fix: `sudo pmset -a sleep 0 displaysleep 0` (not yet applied).
2. **Manual restart at 06:17 ET:** Gateway came up in ~10s with active display. Bot ran cleanly for remainder of session.

---

## Next Steps

- Wait for Ross Cameron's daily recap to compare his trades vs bot's watchlist
- Apply pmset sleep prevention for reliable cron starts
- Consider lowering vol_mult threshold (3.0x → 2.5x?) for stocks near PM high
- Evaluate broader pre-market watchlist loading to mitigate scanner-move paradox

---

*Morning session: successful infrastructure validation. V3 hybrid architecture proven stable. Awaiting Ross comparison for strategy insights.*
