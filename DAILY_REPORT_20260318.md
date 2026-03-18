# Daily Report — 2026-03-18 (First Live Trade)

## Summary
Second automated run. All infrastructure fixes from yesterday worked — Mac stayed awake, re-scans fired on schedule. Bot took its first live (paper) trade on NUAI at 4:22 AM ET, lost $542, and correctly shut down trading for the day via the daily loss limit.

## Infrastructure: All Green
| Component | Status | Notes |
|-----------|--------|-------|
| pmset wake | OK | Mac woke at 1:55 AM MT |
| caffeinate | OK | Kept Mac awake entire session, killed cleanly at shutdown |
| TWS/IBC | OK | Started and logged in |
| Bot startup | OK | Dynamic scanner ran, 500 symbols pre-filtered |
| Re-scan thread | OK | All 7 checkpoints fired (7:30–10:30 ET) |
| Shutdown | OK | Clean exit at 9:00 AM MT, trap fired, logs pushed |

### Re-Scan Results
| Checkpoint (ET) | New Symbols Found |
|-----------------|-------------------|
| 7:30 | 500 (initial batch — first scan at 4AM found nothing useful) |
| 8:00 | 2 (LONA, NSPR) |
| 8:30 | 2 (ILAG, WAI) |
| 9:00 | 1 (RGTU) |
| 9:30 | 2 (CLOU, PLTA) |
| 10:00 | 1 (GRDX) |
| 10:30 | (scanning when bot shut down) |

## The Trade: NUAI (-$542)

### Timeline
| Time (ET) | Event |
|-----------|-------|
| 04:06 | 1M IMPULSE detected at $5.50 |
| 04:07–04:17 | 3-bar pullback ($5.46–$5.49) |
| 04:19 | **ARMED** entry=$5.50 stop=$5.44 R=$0.06 score=5.0 |
| 04:22:04 | **ENTRY SIGNAL** — price broke $5.50 trigger |
| 04:22:05 | ENTRY SUBMITTED: 4,166 shares @ limit $5.54 |
| 04:22:05 | **ENTRY FILL** @ $5.53 (slippage +$0.03 above trigger) |
| 04:22:21 | **STOP HIT** — price fell through $5.44 stop |
| 04:22:21 | EXIT FILL @ $5.40 (4,166 shares) |
| 04:22:21 | **POSITION CLOSED** — P&L: **-$542** |
| 04:22:21 | `daily_stopped_max_loss` triggered (loss $542 > limit $500) |

### Why It Lost
- **4 AM premarket, low liquidity** — NUAI had thin order books, fill slipped 3¢ above trigger
- **Tiny R ($0.06)** — with slippage to $5.53, effective risk was $0.09 per share but position was sized for $0.06 R
- **4,166 shares × $0.13 loss = -$542** — stop at $5.44 was hit, exit filled at $5.40 (another 4¢ slippage on exit)
- Stock had no gap/volume characteristics of a Ross Cameron candidate — it was in the unfiltered 500

### Daily Loss Limit Worked Correctly
After the -$542 loss exceeded `WB_MAX_DAILY_LOSS=500`, the bot stopped taking new trades. All subsequent signals were ignored:

| Time (ET) | Symbol | Score | Outcome |
|-----------|--------|-------|---------|
| 04:25 | LYTS | 5.5 | Blocked (daily loss stop) |
| 04:26 | SHIP | 4.0 | Blocked |
| 04:43 | GLUE | 5.5 | Blocked |
| 04:50 | IREG | 3.1 | Blocked |
| 05:04 | ANPA | 5.5 | Blocked |
| 05:51 | OCGN | 6.0 | Blocked |
| 06:24 | JANX | 5.5 | Blocked |
| 06:44 | BMNZ | 11.0 | Blocked (best signal of the day) |
| 07:22 | UMC | 4.3 | Blocked |
| 07:29 | AMZD | 2.1 | Blocked |

## Issues Identified

### 1. Stock Filter Fallback — No Filtering Applied
The log shows `stock_info cached: 0 symbols` despite `Filtered watchlist: 500 symbols`. This means the StockFilter likely threw an exception and fell through to the unfiltered fallback (`return symbols` in the except block). The bot subscribed to all 500 price-filtered symbols without any gap/volume/float filtering.

**Impact:** NUAI would likely not have passed Ross Cameron criteria (5%+ gap, relative volume, low float). The bot traded a random $5 stock in premarket.

### 2. Premarket Trading at 4 AM
The bot armed and traded at 4:19 AM ET — far too early. Ross Cameron trades the 9:30 AM open window. Even the scanner's earliest useful checkpoint is 7:30 AM. Trading at 4 AM means:
- No liquidity (wide spreads, bad fills)
- No real gap data (stocks haven't started moving)
- Tiny R values (tight stops that get clipped by noise)

### 3. Position Size vs R
With R=$0.06 and `WB_RISK_DOLLARS=1000`, the bot sized at 16,666 shares (capped to 4,166 by notional limit). Even so, 4,166 × $5.50 = $22,913 notional on a $0.06 R trade is aggressive for a premarket illiquid stock.

## Recommendations for Tomorrow

1. **Fix the stock filter** — investigate why it returned 0 cached stock_info. The filter should be applying gap%, float, and relative volume checks before any trades are taken.

2. **Consider a time gate** — don't ARM before 7:00 or 7:30 AM ET. Premarket before that is too thin for reliable entries. The backtest window starts at 7:00 AM ET for a reason.

3. **Review MIN_R** — `WB_MIN_R=0.06` may be too low for live trading. A $0.06 stop gets eaten by a single tick of slippage.

## Session Stats
| Metric | Value |
|--------|-------|
| Symbols subscribed | ~508 |
| ARMED signals | 12 |
| Entry signals | 11 |
| Trades taken | 1 |
| Trades blocked (daily loss) | 10 |
| Daily P&L | **-$542** |
| Bot uptime | 04:05–10:47 ET (~6.7 hours) |
| Mac stayed awake | Yes (caffeinate worked) |
