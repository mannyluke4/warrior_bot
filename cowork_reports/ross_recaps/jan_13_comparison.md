# Jan 13, 2025 — Ross vs Bot Comparison

## Summary
| | Ross | Bot (MP) | Bot (SQ) |
|---|---|---|---|
| **Daily P&L** | +$13,784.94 | -$64 | $0 (no trades) |
| **Trades** | 6 tickers | 2 trades | 0 trades |
| **Win Rate** | ~4W/1L/1 scratch | 0W/2L | N/A |

## Bot Scanner Results (4 candidates found)
| Ticker | Gap% | PM Price | Float | PM Volume | RVOL | Profile | Selected? |
|--------|------|----------|-------|-----------|------|---------|-----------|
| KAPA | +126.3% | $2.19 | 8.69M | 19.4M | 177x | B | Yes (#2) |
| ATPC | +96.0% | $2.47 | 0.43M | 25.2M | 92x | A | Yes (#1) |
| SLXN | +20.1% | $2.33 | 3.0M | 4.75M | 5.6x | A | Yes (#3) |
| GRNQ | +16.9% | $2.21 | N/A | 344K | 2.3x | X | No (filtered) |

## Ross's Tickers vs Bot Scanner
| Ross Ticker | Bot Scanner Found? | Bot Traded? | Notes |
|-------------|-------------------|-------------|-------|
| **GTBP** | **NO** | No | Ross's first trade, -$3,400. Scanner completely missed it. |
| **DATS** | **NO** | No | No-news continuation. Ross made +$2,000. Scanner missed it. |
| **XXI** | **NO** | No | News but choppy. Ross made small profit. Scanner missed it. |
| **ATPC** | **YES** | **YES** | Bot selected #1 (96% gap, 0.43M float, Profile A). Bot traded at 07:05, micro_pullback setup, entry $2.69, exit $2.68, P&L: **-$17**. Ross also made only a small profit here. |
| **PHIO** | **NO** | No | HUGE miss. 460% squeeze, 514K float, 168x RVOL — this was the day's biggest mover. Scanner completely missed it. |
| **SLRX** | **NO** | No | MASSIVE miss. Merger news, 1.2M float, 1200x RVOL, +328%. Ross made the bulk of his +$13K here. Scanner completely missed it. |

## Bot Trades (MP Strategy)
### Trade 1: ATPC (micro_pullback)
- Entry: $2.69 at 07:05 → Exit: $2.68 at 07:07
- Stop: $2.25 | R: $0.44
- P&L: **-$17** (-0.0R)
- Exit reason: bearish_engulfing_exit_full
- Notes: Both configs (A & B) took identical trade. Quick in-and-out, essentially a scratch loss.

### Trade 2: KAPA (micro_pullback)
- Entry: $2.69 at 11:15 → Exit: $2.62 at 11:16
- Stop: $2.34 | R: $0.35
- P&L: **-$47** (-0.2R)
- Exit reason: bearish_engulfing_exit_full
- Notes: KAPA was NOT one of Ross's tickers at all. Bot traded a stock Ross didn't even mention.

## Bot Traded Stocks Ross Didn't Trade
- **KAPA** (+126.3% gap, 8.69M float, Profile B): Bot took a micro_pullback trade at 11:15 AM, lost $47. Ross never mentioned KAPA. The bot also selected SLXN (#3) but took no trades on it.

## Key Findings

### Scanner Miss Analysis
The bot's scanner missed **5 of 6** Ross tickers on Jan 13. The only overlap was ATPC. The biggest misses:

1. **SLRX** — Ross's biggest winner (+$13K). Merger news, 1.2M float, 1200x RVOL. This is exactly the kind of stock the bot should find. The stair-step breakout from $1.50→$5 pre-market was textbook.

2. **PHIO** — 460% squeeze, 514K float, 168x RVOL. Even Ross called this a "huge miss" for himself — he only caught small dip pieces despite the stock meeting all 5 of his criteria. The bot didn't even see it on the scanner.

3. **GTBP** — Ross lost $3,400 here jumping in too aggressively. Missing this one may have actually been fortunate.

4. **DATS** — No-news continuation, Ross made +$2,000 in recovery mode with small size.

5. **XXI** — News but choppy, small profit for Ross.

### Performance Gap
- Ross: +$13,784.94
- Bot: -$64
- Delta: **$13,849** in Ross's favor
- The gap is almost entirely explained by the scanner missing SLRX and PHIO. These two stocks alone accounted for the vast majority of Ross's P&L.

### What the Bot Did Right
- ATPC was correctly identified as the #1 ranked stock (highest rank score 1.026)
- The bot's ATPC trade was essentially a scratch (-$17), similar to Ross's small profit outcome
- Quick exit on bearish engulfing preserved capital

### What Went Wrong
- Scanner missed the day's two biggest movers (SLRX, PHIO) — both had characteristics the scanner should catch (low float, massive RVOL, huge gaps)
- Bot traded KAPA (a stock Ross didn't touch) and lost money
- SQ strategy found zero setups across all 3 selected stocks
