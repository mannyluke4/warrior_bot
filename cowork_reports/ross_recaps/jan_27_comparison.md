# Jan 27, 2025 — Ross vs Bot Comparison

## Summary
| Metric | Ross | Bot (SQ) | Bot (MP) |
|--------|------|----------|----------|
| Daily P&L | green (amount unknown from recap; JG +$15,558 per broker data) | $0 (0 trades) | $0 (0 trades) |
| Trades | AURL primary (+ JG per broker data) | 0 trades | 0 trades |
| Win Rate | green day | N/A | N/A |
| Best Trade | AURL (200%+ runner, P&L unknown) | — | — |
| Worst Trade | N/A | — | — |

**Combined bot P&L: $0 vs Ross's green day. Bot was completely idle — 0 trades across all strategies. Scanner found 4 tickers, none overlapped with Ross, and none generated entries.**

**Market context:** DeepSeek AI launch day — Chinese AI stocks surged 200%+, US large-cap tech crashed (NVDA -17%). A once-in-a-year catalyst event.

## Scanner Overlap

### Bot's Scanner Found (4 tickers)
| Ticker | Gap% | Float | PM Vol | Profile | Bot Traded? | Ross Traded? |
|--------|------|-------|--------|---------|-------------|--------------|
| TVGN | +52.5% | 0.88M | 5.65M | A | NO | NO |
| ICCT | +19.8% | 4.45M | 3.40M | A | NO | NO |
| GMHS | +19.9% | 3.89M | 220K | A | NO | NO |
| BCDA | +16.9% | 7.2M | 125K | B | NO | NO |

### Ross's Tickers NOT in Bot's Scanner (1+ tickers)
| Ticker | Ross P&L | Setup | Why Scanner Likely Missed |
|--------|----------|-------|--------------------------|
| AURL | green (amount unknown) | DeepSeek AI news squeeze, $8→$20+ (200%+ move) | **Price too high for scanner filters.** AURL ran from ~$8 to $20+ pre-market. At $20+ PM price, the stock may have exceeded the bot's price ceiling filter. Alternatively, float or volume characteristics didn't match scanner criteria. The 200%+ gap should have been unmissable on gap% alone — this is a significant scanner miss. |
| JG | +$15,558 (per broker data) | Chinese AI momentum (DeepSeek day) | Same DeepSeek catalyst. JG (Aurora Mobile) is a Chinese tech stock that ran on the same thematic. Scanner likely missed for similar reasons — price, float, or volume criteria not met during scan window. |

### Overlap: 0 of Ross's tickers — COMPLETE SCANNER WHIFF
Zero overlap between the bot's scanner and Ross's traded tickers. The scanner found 4 small, low-gap stocks (TVGN, ICCT, GMHS, BCDA) that had nothing to do with the day's dominant theme (DeepSeek/Chinese AI). Meanwhile, the biggest movers of the day — Chinese AI stocks running 200%+ — were completely invisible.

## Bot's Trades — What Happened

### V2 Megatest Results (Primary Backtest)
- **SQ Strategy:** 4 scanned → 4 passed → TVGN, ICCT, GMHS, BCDA → **0 trades, $0 P&L**
- **MP Strategy:** 4 scanned → 4 passed → **0 trades, $0 P&L**
- **MP+SQ Combined:** 4 scanned → 4 passed → **0 trades, $0 P&L**

The bot found 4 candidates but none generated entry signals. All 4 had relatively modest gaps (17-53%) and low PM volume compared to the day's real movers. TVGN was the strongest candidate at +52.5% gap and 5.65M PM volume, but even it didn't trigger.

### Continuous Scan / Expanded Results (Gates OFF)
The expanded continuous scan found additional tickers later in the day:
| Trade | Symbol | Time | Entry | Exit | Exit Reason | P&L | R-Mult |
|-------|--------|------|-------|------|-------------|-----|--------|
| 1 | YIBO | 10:38 | $11.22 | $11.20 | bearish_engulfing_exit_full | -$12 | -0.0R |
| 2 | YIBO | 10:46 | $15.70 | $15.51 | bearish_engulfing_exit_full | -$48 | -0.1R |
| 3 | TRAW | 09:12 | $7.20 | $7.05 | stop_hit | -$208 | -1.4R |
| 4 | VATE | 10:52 | $12.16 | $11.90 | stop_hit | -$210 | -1.3R |

**Gates OFF total: 4 trades, -$478.** All losers — YIBO (Chinese AI stock, 2 scratches), TRAW (stop hit), VATE (stop hit).

**Gates ON total: 1 trade (YIBO), -$12.** Quality gates correctly filtered out the 3 worst trades.

**Notable:** YIBO (Yibo Technology) is actually a Chinese AI-adjacent stock that ran on DeepSeek news — the continuous rescan found it at 10:38 AM, but only after the main move. The primary scanner at 7:15 AM missed ALL Chinese AI names including YIBO, AURL, and JG.

### Continuation Hold Results
YIBO appeared in the 5M continuation hold analysis with a -$1,016 loss and note "Entry at 10:38 (after 10:30 cutoff)" — confirming the timing was too late.

## Ross's Trades — What Made Them Work

### AURL (Aurora Limited) — GREEN (P&L unknown)
- **Catalyst:** DeepSeek AI model launch — the biggest AI news event of 2025. Chinese company built an AI model rivaling US frontier models at a fraction of the cost. Sent shockwaves through the tech world.
- **Pre-market:** $8 → $20+ (200%+ move)
- **Entry strategy:** VWAP and dip/bounce structure on 10s/1m charts
- **Why it worked:** Massive thematic catalyst (Chinese AI), likely low float, enormous pre-market volume. Every Chinese tech/AI-adjacent stock surged. Ross correctly identified AURL as the small-cap play while passing on large-cap shorts (NVDA -17%, GOOGL, META all red).
- **Key decision:** Ross explicitly passed on shorting large-cap tech — staying in his lane with small-cap longs. This is discipline: the DeepSeek news made NVDA a tempting short, but Ross knows his edge is in small-cap squeezes, not large-cap directional bets.

### JG (Aurora Mobile) — +$15,558 (per broker data)
- JG appears in the monthly tracking as a $15K+ winner on Jan 27
- Another Chinese tech stock (Aurora Mobile — confusingly similar name to AURL/Aurora Limited)
- Ran on the same DeepSeek thematic catalyst
- Not mentioned in the video recap, but shows up in P&L data

## Key Takeaways

### 1. DeepSeek Day Was a Complete Scanner Blindspot
The biggest market event of the year produced 200%+ moves in Chinese AI stocks, and the bot's scanner found **zero** of them. The scanner picked up TVGN (+52.5%), ICCT (+19.8%), GMHS (+19.9%), and BCDA (+16.9%) — none of which were related to the day's dominant theme. This is a thematic awareness gap: the scanner has no concept of "today's catalyst is Chinese AI, so scan for Chinese AI-adjacent tickers."

### 2. Chinese Stocks Are a Recurring Scanner Blindspot
This is the second time Chinese stocks have been a major miss:
- **Jan 23:** Chinese IPO day — DGNX (+$23K for Ross), DXST, MIMI all missed
- **Jan 27:** DeepSeek day — AURL (200%+ mover), JG (+$15.5K) both missed
- The scanner may have structural issues with Chinese-listed companies (ADRs, variable float data, different trading characteristics).

### 3. The Bot Was Completely Idle on a Monster Day
Zero trades across SQ and MP strategies on one of the most active trading days of the year. The 4 scanner candidates were too weak to trigger entries. Meanwhile, Chinese AI stocks were running 200%+ with massive volume. The expanded continuous scan found YIBO (Chinese AI) but only at 10:38 AM — over 3 hours after the main pre-market action.

### 4. Thematic Catalyst Days Expose the Scanner's Biggest Weakness
Days with a dominant theme (DeepSeek AI, Chinese IPOs, inauguration crypto, GLP-1 biotech) produce the biggest moves and the biggest scanner misses. The bot scans for gap%, volume, and float — it has no awareness of what the catalyst IS or which sector is in play. On thematic days, Ross's contextual awareness gives him a massive edge.

### 5. Ross's Discipline on Large-Cap Shorts
Ross passed on NVDA (-17%), GOOGL, and META despite massive moves. He knows his edge is small-cap longs, not large-cap directional bets. This is a key insight: the DeepSeek news created opportunity on BOTH sides (short US tech, long Chinese AI), and Ross correctly identified which side of the trade matched his skillset.

## Missed P&L Estimate
AURL ran from ~$8 to $20+ (200%+ move, ~$12/share). If the bot had found it:
- $50K notional at $8 = 6,250 shares
- Ride to $14 (50% of move to $20): 6,250 × $6 = +$37,500
- Ride to $18 (83% of move): 6,250 × $10 = +$62,500
- Realistic 30% capture: 6,250 × $3.60 = +$22,500

JG: +$15,558 for Ross — unknown move range, but another significant miss.

**Total estimated missed opportunity: $22,500-$62,500+ (AURL alone) + $15,558 (JG).**

## Tickers Added to Missed Stocks Backtest Plan
AURL (1 ticker — absent from bot's scanner)
Note: JG was already listed in the monthly summary big winners table. Both are Chinese AI thematic plays missed on DeepSeek day.

## Running Pattern Notes
This is the **second complete scanner whiff in the last 6 trading days** (Jan 22 was the other). The pattern is clear:
- **Thematic/catalyst days** (DeepSeek, Chinese IPOs, inauguration) → scanner misses everything
- **Normal gap days** (individual stock news) → scanner works reasonably well (Jan 24: 50% overlap)

New patterns:
- **Chinese stocks are systematically missed** — Jan 23 IPOs + Jan 27 DeepSeek = 5+ major Chinese tickers missed in one week
- **Bot idle days correlate with Ross's thematic wins** — when the market has a dominant theme, Ross thrives and the bot sits out
- **The continuous rescan found YIBO at 10:38 AM** — Chinese AI was eventually discoverable, but the 7:15 AM primary scan missed it entirely. Earlier rescan windows or thematic pre-screening could help.
