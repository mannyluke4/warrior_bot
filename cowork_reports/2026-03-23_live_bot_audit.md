# CC Report: Live Bot Audit — 2026-03-23
## Date: 2026-03-23
## Machine: Mac Mini

---

### Executive Summary

The bot ran all day but took **0 trades**. Two compounding issues:

1. **Alpaca websocket "connection limit exceeded"** — bot was blind from 04:04 to 09:30 AM ET (5.5 hours, 99,934 failed retries). Likely caused by stale websocket connection from weekend Dispatch sessions.

2. **Scanner divergence** — even after websocket recovered, the live `stock_filter.py` found different stocks (ANNA, ARTL, SUNE) than `scanner_sim.py` (UGRO, AHMA, WSHP). The live stocks produced 0 backtest trades; the sim stocks would have produced +$373 (UGRO) and -$375 (AHMA).

**Net result: $0 live, ~$0 theoretical (scanner sim stocks were roughly breakeven).**

---

### Issue 1: Alpaca Websocket Failure — CRITICAL

**Timeline:**
- 04:04 AM ET: Bot starts, scanner finds 3 stocks (ANNA, ARTL, SUNE)
- 04:04 AM ET: Websocket auth fails — "connection limit exceeded"
- 04:04 - 09:30 AM ET: **99,934 failed reconnection attempts** (5.5 hours)
- 09:30 AM ET: Websocket finally connects, data starts flowing
- 09:30 - 12:00 PM ET: Data flows normally but no squeeze setups trigger

**Root cause:** Alpaca limits concurrent websocket connections per API key. A stale connection from the weekend (Dispatch sessions running backtests that may have opened websockets) was likely still holding a slot.

**This is not the first Alpaca data reliability issue.** Previous incidents:
- 2026-03-19: `stock_filter.py` using `latest_trade.size` instead of `daily_bar.volume` (P0 bug)
- 2026-03-20: Bot crash from `market_scanner.py` import (indirect — stale pyc from Alpaca-dependent code)
- 2026-03-23: Websocket connection limit (this incident)

**Recommendation: Migrate data feed to Databento.** Use Alpaca ONLY for order execution. Databento subscription is already paid for and `live_scanner.py` exists (Databento streaming). This eliminates Alpaca as a single point of failure for both scanning AND data feed.

---

### Issue 2: Scanner Divergence — HIGH

**Live bot found (via `stock_filter.py` + Alpaca REST snapshots):**
| Stock | Gap | RVOL | Float | Backtest P&L |
|-------|-----|------|-------|-------------|
| ANNA | +87% | 17.9x | 9.5M | **$0** (0 trades) |
| ARTL | +17% | 3.3x | 0.7M | **$0** (0 trades, 3K ticks) |
| SUNE | +20% | 2.1x | 3.4M | **$0** (0 trades) |

**Scanner sim found (via `scanner_sim.py` + historical 1m bars):**
| Stock | Gap | RVOL | Float | Discovery | Backtest P&L |
|-------|-----|------|-------|-----------|-------------|
| UGRO | +47% | 33x | 0.67M | 07:00 | **+$373** (3 trades) |
| AHMA | +47% | 113x | 2.0M | 09:30 | **-$375** (2 trades) |
| WSHP | +20% | 2.2x | 1.3M | 08:00 | **$0** (0 trades) |

**Why the divergence:**
- `stock_filter.py` uses Alpaca's real-time snapshot (`daily_bar.volume`) at scan time
- `scanner_sim.py` uses historical bars to compute PM volume and RVOL
- Different data sources → different volume/gap calculations → different candidates
- UGRO (the only winner) was completely missed by the live scanner

**Recommendation:** If migrating to Databento for data, the live scanner should use the same data source as `scanner_sim.py` to eliminate this divergence.

---

### Issue 3: Backtest Detail

**UGRO 2026-03-23 (scanner sim candidate, discovered 07:00):**
```
    #    TIME    ENTRY     STOP       R  SCORE     EXIT  REASON                     P&L  R-MULT
    1   07:07   3.0400   2.9000  0.1400   11.0   2.9200  sq_para_trail_exit        -429    -0.9R
    2   07:12   3.0400   2.9300  0.1100    9.3   3.3300  sq_target_hit            +1159    +2.3R
    3   08:03   4.0400   3.9000  0.1400    7.0   3.9400  sq_para_trail_exit        -357    -0.7R
Total: +$373 (1W/2L)
```
Classic squeeze probe pattern: small loss → winner → re-entry loss. Net positive.

**AHMA 2026-03-23 (scanner sim candidate, discovered 09:30):**
```
    #    TIME    ENTRY     STOP       R  SCORE     EXIT  REASON                     P&L  R-MULT
    1   09:31   6.7000   6.5600  0.1400   10.2   6.1200  sq_dollar_loss_cap        -2071    -4.1R
    2   09:36   6.7000   6.5600  0.1400    7.5   7.2000  sq_target_hit            +1696    +3.4R
Total: -$375 (1W/1L)
```
Dollar cap fired on trade 1 (-$2,071 capped from what would have been worse), trade 2 was a strong winner.

**ANNA, ARTL, SUNE (live bot candidates): All $0, 0 trades.**

---

### Issue 4: watch=0 Display Bug — LOW

The heartbeat shows `watch=0` because it reads from `watchlist.txt` (empty when using dynamic scanner) instead of counting dynamically subscribed symbols. Bot was actually receiving data for subscribed stocks. Cosmetic only.

---

### Databento Migration Considerations

**Current architecture:**
- Alpaca REST → `stock_filter.py` (live scanning)
- Alpaca Websocket → `bot.py` (live data feed for trades/quotes)
- Alpaca REST → `trade_manager.py` (order execution)
- Alpaca REST → `scanner_sim.py` / `simulate.py` (backtesting)

**Proposed architecture:**
- **Databento streaming** → live scanning + data feed (trades/quotes)
- **Alpaca REST** → order execution ONLY
- Databento historical → backtesting (already partially in place)

**What already exists:**
- `live_scanner.py` — Databento streaming scanner (writes watchlist files)
- `DATABENTO_API_KEY` in `.env` — subscription active
- `data_feed.py` — abstraction layer with `create_feed()` that supports multiple backends

**What needs work:**
- Wire Databento feed into `bot.py`'s data pipeline (replace Alpaca websocket)
- Ensure `data_feed.py` Databento backend handles trades + quotes
- Test latency: Databento vs Alpaca for order-relevant price updates
- Verify Databento has the same symbols/data quality as Alpaca SIP feed

**Risk:** Splitting data (Databento) from execution (Alpaca) adds a dependency boundary. Price seen by scanner may differ slightly from price at execution. Need to verify latency delta is acceptable.

---

### Action Items

| Priority | Item | Owner |
|----------|------|-------|
| P0 | Kill stale websocket connections before bot start (add to `daily_run.sh`) | CC/Cowork |
| P1 | Test Databento as primary data feed in paper mode | CC/Cowork |
| P1 | Align live scanner with scanner_sim criteria (or replace with Databento) | Cowork |
| P2 | Fix watch=0 heartbeat display | CC |
| P2 | Add websocket connection health monitoring/alerting | CC |

---

### Files
- `cowork_reports/2026-03-23_live_bot_audit.md` (this file)
