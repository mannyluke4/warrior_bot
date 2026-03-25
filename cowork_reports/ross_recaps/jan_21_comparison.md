# Jan 21, 2025 — Ross vs Bot Comparison

## Summary
| Metric | Ross | Bot (MP) | Bot (SQ) |
|--------|------|----------|----------|
| Daily P&L | +$28,026 | -$801 | -$281 |
| Trades | 5 tickers, ~8 trades | 2 trades | 1 trade |
| Win Rate | 4/5 tickers green | 0/2 | 0/1 |
| Best Trade | INMN +$12,000 | — | — |
| Worst Trade | XTI -$12 | PTHS -$646 | LEDS -$281 |

**Combined bot P&L: -$1,082 vs Ross's +$28,026 — gap of $29,108.**

## Scanner Overlap

### Bot's Scanner Found (5 tickers)
| Ticker | Gap% | Float | Rank | Bot Traded? | Ross Traded? |
|--------|------|-------|------|-------------|--------------|
| INM (=INMN) | 63.84% | 1.8M | 1.027 | NO | YES (+$12,000) |
| DWTX | 40.59% | 1.35M | 0.964 | NO | NO |
| PTHS | 55.79% | 1.23M | 0.728 | YES (MP: -$646) | NO |
| LEDS | 27.9% | 3.43M | 0.677 | YES (SQ: -$281) | NO |
| VATE | 23.29% | 4.2M | 0.597 | YES (MP: -$155) | NO |

### Ross's Tickers NOT in Bot's Scanner (6 tickers)
| Ticker | Ross P&L | Setup | Why Scanner Likely Missed |
|--------|----------|-------|--------------------------|
| TPET | +$475 | thematic momentum (energy) | Likely didn't meet gap/volume thresholds — $3 stock, inauguration theme play |
| NXX | +$1,800 | news breakout + dip buy | Breaking news mid-session, scanner likely didn't catch intraday catalyst |
| BTCT | +$5,500 | thematic breakout (crypto) | May not have met pre-market gap threshold, crypto inauguration theme |
| XTI | -$12 | news (failed) | Had news but immediately reversed; scanner may not have captured |
| TRIO | not traded | watchlist only | Scanner ticker, likely below thresholds |
| INDO | not traded | watchlist only | Scanner ticker, likely below thresholds |

## Bot's Trades — What Happened

### MP Strategy (2 trades, -$801)
1. **VATE** — Entry around open, exit 08:44, P&L -$155 (-0.2R), notional $22,164, micro_pullback setup
2. **PTHS** — Entry around open, exit 10:43, P&L -$646 (-0.9R), notional $9,089, micro_pullback setup

### SQ Strategy (1 trade, -$281)
1. **LEDS** — Entry $2.44, exit $2.34, 09:37, P&L -$281 (-0.7R), notional $13,734, squeeze setup, exited via sq_para_trail_exit

### Bot Did NOT Trade Stocks Ross Traded
The bot's scanner found INM (#1 ranked candidate!) but neither strategy took a trade on it. Ross made +$12,000 on INMN — his best trade of the day. This is the critical "found it but didn't trade it" gap.

### Bot Traded Stocks Ross Didn't Trade
VATE, PTHS, LEDS — all losers. Ross's scanner also showed these (or similar) names but he focused on higher-conviction catalyst-driven setups.

## Key Takeaways

### 1. Scanner Gap — Thematic/News Catalysts Invisible
The bot missed 4 of Ross's 5 traded tickers. The misses share a pattern: **thematic awareness** (inauguration → energy + crypto plays) and **intraday breaking news** (NXX). The bot's scanner relies on pre-market gap% and volume — it has no concept of macro themes or news catalysts.

### 2. Selection Gap — Found #1 but Traded #3, #4, #5
INM was the scanner's top-ranked candidate by a wide margin (1.027 vs 0.964 for #2). Yet the bot traded VATE (rank #5), PTHS (#3), and LEDS (#4) instead. This suggests the entry criteria for MP and SQ didn't trigger on INM's price action despite it being the strongest candidate. INM's 68K float (Ross noted "EXTREMELY LOW") may have created price action patterns that didn't match the bot's micro_pullback or squeeze templates.

### 3. Capital Preservation vs Opportunity Cost
Ross's -$12 ruthless cut on XTI preserved capital for BTCT +$5,500. The bot lost -$1,082 across 3 mediocre trades with no winners. The bot didn't display the same capital-preservation instinct — it kept trading lower-ranked names instead of waiting for the best setup.

### 4. Ice-Breaker Psychology (Not Applicable to Bot)
Ross used TPET (+$475) as an ice-breaker to get green early and lower emotional pressure for bigger trades. The bot has no emotional state, but the parallel lesson is: the bot should be more selective about which candidates it enters, potentially prioritizing the top-ranked scanner candidate rather than spreading across lower-ranked names.

### 5. Float Sensitivity
INMN's 68K float was the key feature that made it explosive. The bot's scanner recorded INM's float as 1.8M (likely the shares outstanding, not the true micro-float). If the bot's float filter had recognized the true float, INM would have been even more clearly the top pick.

## Missed P&L Estimate
If the bot had traded ONLY INM (its #1 ranked candidate) with even modest success:
- Ross made +$12,000 on INMN with 6-10K share positions
- Even capturing 20-30% of Ross's INMN move could have yielded +$2,400-$3,600
- Instead the bot lost -$1,082 on three mediocre trades
- **Potential swing: +$3,500 to +$4,700 improvement**

## Tickers Added to Missed Stocks Backtest Plan
TPET, NXX, XTI, BTCT, TRIO, INDO (6 tickers — all absent from bot's scanner)

Note: INM/INMN was found by the scanner but not traded — this is a **selection/execution gap**, not a scanner gap. Tracked separately in the backtest plan notes.
