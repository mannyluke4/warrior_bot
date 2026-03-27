# Ross vs Bot Comparison — January 7, 2025

## Overview

| Metric | Ross | Bot (MP only v2) | Bot (SQ only v2) |
|--------|------|-------------------|-------------------|
| Daily P&L | +$1,924.57 | $0 (no trades) | +$239 (2 trades) |
| Trades Taken | 4 stocks (ZENA, CGBS, HOTH, AMVS) | 0 | 2 (both MYSE) |
| Win Rate | ~75% (3 wins, 1 break-even) | N/A | 100% (2/2) |

## Scanner Overlap

### Ross's Tickers (7 total)
| Ticker | Ross Action | Bot Scanner Found? | Bot Traded? | Notes |
|--------|-------------|-------------------|-------------|-------|
| ZENA | +$998 | **NO** | No | 8M float, breaking news squeeze. Scanner completely missed. |
| CGBS | +$296.77 | **NO** | No | 1.7M float squeeze. Scanner completely missed. |
| HOTH | +$1,000 | **NO** | No | Up 300%, momentum. Scanner completely missed. |
| AMVS | ~break-even | **NO** | No | 9.3M float breakout. Scanner completely missed. |
| MSAI | passed (rolling over) | **YES** (+108% gap, 29.7M PM vol) | No (profile X, no float) | Both Ross and bot correctly avoided. Leading gapper but topping tail. |
| SPRC | passed (too far below highs) | **NO** | No | Ross passed on Jan 6 too. |
| IMRX | missed (risk check failed) | **NO** | No | $2.50→$5.70 big miss, 16M float. Scanner missed entirely. |

### Bot's Tickers (6 total)
| Ticker | Bot Scanner Found? | Bot Traded? | Ross Saw It? | Notes |
|--------|-------------------|-------------|--------------|-------|
| MSAI | Yes (+108% gap) | No (profile X) | Yes (passed) | Only overlap between Ross and bot scanner. |
| GETY | Yes (+76.7% gap) | No (profile X) | No | Ross didn't mention. |
| MYSE | Yes (+29.1% gap, 3.97M float) | **Yes — SQ only: 2 trades, +$239** | No | Bot's best pick of the day. Profile A. |
| CING | Yes (+10.1% gap, 5.6M float) | No | No | Profile B, no trades taken. |
| STAI | Yes (+20.3% gap, 1.0M float) | No | No | Discovered late (10:03 AM). Profile A. |
| AMOD | Yes (+21.5% gap) | No (profile X) | No | No float data available. |

## Key Findings

### 1. Minimal Scanner Overlap
Only 1 of Ross's 7 tickers appeared on the bot's scanner: MSAI. And that was a stock both correctly passed on. The bot's scanner missed all 4 of Ross's profitable/traded stocks (ZENA, CGBS, HOTH, AMVS) plus SPRC and IMRX.

### 2. Bot Found Its Own Winner
The bot's SQ strategy found MYSE (+29.1% gap, 3.97M float, profile A) and made +$239 on 2 squeeze trades. Ross didn't mention MYSE at all. This shows the bot can find tradeable stocks independently, but it's fishing in a completely different pond than Ross on days like this.

### 3. MP Strategy Sat Out Entirely
The MP-only strategy took 0 trades on Jan 7 despite having 3 stocks pass the filter (MYSE, STAI, CING). The MP strategy requires momentum-pop setups that apparently didn't trigger on any of these.

### 4. "Pop and Drop" Theme Hurt Both
Ross noted Jan 7 was a "pop and drop" day — MSAI, AMVS, and IMRX all round-tripped. The bot's scanner correctly filtered MSAI to profile X. The choppy, low-continuation environment meant even Ross took base-hit-sized positions.

### 5. Missed Revenue from Scanner Gaps
Ross made +$2,295 on stocks the bot's scanner missed (ZENA +$998, CGBS +$297, HOTH +$1,000). Even accounting for AMVS break-even, these were clean trades. If the scanner had found them, the bot could potentially have captured some of this.

### 6. Bot Traded a Stock Ross Didn't
The bot's SQ strategy traded MYSE for +$239. Ross never mentioned MYSE. This is a pure bot-originated trade — interesting because it was the bot's only activity and it was profitable.

## Scanner Gap Analysis
- Ross tickers missed by bot scanner: **6 of 7** (ZENA, CGBS, HOTH, AMVS, SPRC, IMRX)
- Bot tickers Ross didn't see: **5 of 6** (GETY, MYSE, CING, STAI, AMOD)
- Overlap: **1 of 12 unique tickers** (MSAI only) — 8.3% overlap rate
- Combined P&L on missed tickers: Ross made +$2,295 on stocks the bot missed

## Pattern: Why Did the Scanner Miss Ross's Stocks?
Likely reasons to investigate:
- **ZENA** (8M float): May have been filtered by gap% or PM volume thresholds at scan time
- **CGBS** (1.7M float): Low-float stock, may not have had sufficient gap% or PM volume
- **HOTH** (unknown float): Up 300% — possible the move happened too fast or discovery was late
- **AMVS** (9.3M float): Float on the higher side for the bot's typical range, may have been excluded
- **SPRC**: Also missed on Jan 6 — consistently outside bot's filter criteria
- **IMRX** (16M float): 16M float may exceed the bot's filter ceiling
