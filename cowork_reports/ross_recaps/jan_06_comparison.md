# Jan 6, 2025 — Ross vs Bot Comparison

## Summary
| | Ross Cameron | Bot (MP v2) | Bot (SQ v2) |
|---|---|---|---|
| **Daily P&L** | +$2,825 | $0 | $0 |
| **Trades taken** | 3 (GDTC, RHE, ARBE) | 0 | 0 |
| **Scanner candidates** | 8 tickers | 5 tickers | 5 tickers |

## Scanner Overlap

### Bot's scanner found (5 stocks):
| Ticker | Gap% | PM Price | Float | Profile | Discovery |
|--------|------|----------|-------|---------|-----------|
| GDTC | +93.6% | $6.68 | N/A | X | 07:00 |
| MBOT | +66.4% | $3.56 | N/A | X | 04:00 |
| DHAI | +32.7% | $2.08 | 0.94M | A | 10:10 |
| LUCY | +18.2% | $6.55 | 5.05M | B | 09:45 |
| DTSS | +11.2% | $2.59 | 5.99M | B | 09:45 |

### Ross's tickers:
| Ticker | On Bot Scanner? | Ross Traded? | Ross Result | Notes |
|--------|----------------|-------------|-------------|-------|
| **GDTC** | ✅ YES | ✅ Yes | +$5,300 | Bot scanned it (profile X, no float) but took 0 trades |
| **RHE** | ❌ NO | ✅ Yes | Small net gain | $1.50→$7, pure momentum, no catalyst mentioned |
| **ARBE** | ❌ NO | ✅ Yes | +$4,200 | Nvidia news, $33.75→$50, 27M float |
| CRNC | ❌ NO | ❌ Passed | — | Continuation from Friday |
| FUBO | ❌ NO | ❌ Passed | — | 300M float too high |
| BOXL | ❌ NO | ❌ Passed | — | Halt levels too close |
| POI | ❌ NO | ❌ Passed | — | Too cheap |
| SPRC | ❌ NO | ❌ Passed | — | Too cheap |

### Bot-only tickers (not on Ross's radar):
| Ticker | Gap% | PM Price | Float | Profile |
|--------|------|----------|-------|---------|
| MBOT | +66.4% | $3.56 | N/A | X |
| DHAI | +32.7% | $2.08 | 0.94M | A |
| LUCY | +18.2% | $6.55 | 5.05M | B |
| DTSS | +11.2% | $2.59 | 5.99M | B |

Bot didn't trade any of these either (0 trades on the day across both configs).

## Key Findings

### 1. GDTC: Scanned but not traded
The bot found GDTC at 07:00 with a massive 93.6% gap — the #1 candidate on the scanner. But it was classified as profile "X" (no float data available), and the bot took zero trades. Ross made +$5,300 on GDTC buying the dip at $6.13 after a spike to $8, riding it to blue-sky ATH at $9.50.

**Question:** Did the missing float data disqualify GDTC from the simulation? Or did the strategy simply not find a valid setup entry on the 1-minute chart?

### 2. ARBE: Completely missed — $4,200 left on the table
ARBE was a $33 stock with 27M float that squeezed to $50 on Nvidia collaboration news. The bot's scanner didn't pick it up at all. Likely reasons:
- **Price too high?** At $33.75 entry, ARBE is well above typical small-cap scanner thresholds
- **Float too high?** 27M float may exceed scanner filters
- **Gap% too low?** The stock may not have had a massive premarket gap if it was already in the $30s

This is significant — Ross explicitly used pattern recognition from CRNC (Jan 3, also Nvidia keyword) to identify ARBE. The bot has no cross-day keyword/catalyst memory.

### 3. RHE: Completely missed — small gain
RHE went from $1.50 to $7 in ~2 minutes. Likely a sub-$2 stock that may have been filtered out by minimum price thresholds, or it moved too fast for the scanner's rescan interval to catch.

### 4. Bot had 0 trades on a day Ross made +$2,825
Both MP and SQ configs had zero trades and zero P&L. The bot's scanner found 5 stocks but none triggered a trade entry. This is a total whiff day.

## Diagnostic Questions
1. Why didn't GDTC (profile X) generate a trade? Was it the missing float, or no valid setup pattern?
2. What are the scanner's price/float ceiling filters? ARBE at $33/27M float is a different class of stock
3. Could a "news keyword" cross-day memory (like Ross's CRNC→ARBE Nvidia pattern) be implemented?
4. Should the scanner have a special "breaking news" mode for stocks that spike intraday from low prices (RHE $1.50→$7)?

## Running Totals (Jan 2-6)
| Metric | Value |
|--------|-------|
| Ross's total P&L (3 days) | +$19,505 |
| Bot's total P&L — MP (3 days) | -$107 |
| Bot's total P&L — SQ (3 days) | -$206 |
| Ross tickers scanned by bot | 1 of 8 (GDTC only) |
| Ross traded tickers scanned by bot | 1 of 3 (GDTC) |
| Ross traded tickers bot also traded | 0 of 3 |
