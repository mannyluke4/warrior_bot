# Jan 29, 2025 — Ross vs Bot Comparison

## Summary
| Metric | Ross | Bot (All-Three) | Bot (SQ) | Bot (MP) |
|--------|------|------------------|----------|----------|
| Daily P&L | +$24,000 | +$211 | +$231 | $0 (0 trades) |
| Trades | 4 tickers, multiple trades | 1 trade (SLXN) | 1 trade (SLXN) | 0 trades |
| Win Rate | 3/4 net positive tickers | 1/1 (100%) | 1/1 (100%) | N/A |
| Best Trade | MVNI +$3,900 | SLXN +$211 | SLXN +$231 | — |
| Worst Trade | SLXN re-entry -$2K | — | — | — |

**Combined best bot P&L: +$231 (SQ) vs Ross's +$24,000. The bot made ~1% of Ross's total. Scanner found 1 of 4 Ross tickers (SLXN), and traded it profitably across two strategy variants (+$211 all-three, +$231 SQ). The 3 biggest misses were MVNI (+$3,900 anchor trade), VNCE (positive, part of ~$9K combined), and SGN (minimal). The remaining ~$11K of Ross's P&L came from additional trades not individually detailed.**

**Market context:** Post-DeepSeek week. SLXN was the day's leading gapper (+57.8% gap, 30.9M PM volume) and the bot correctly identified it as the #1 candidate. Biotech/momentum names (VNCE, MVNI) provided separate opportunities the scanner missed. Ross's best trade (MVNI third entry at 9:47 AM) was a mid-morning momentum pattern.

## Scanner Overlap

### Bot's Scanner Found (1 ticker)
| Ticker | Gap% | Float | PM Vol | Profile | Bot Traded? | Ross Traded? |
|--------|------|-------|--------|---------|-------------|--------------|
| SLXN | +57.8% | 3.0M | 30.9M | A | YES (+$211 all-three, +$231 SQ) | YES (net positive, ice breaker) |

### Ross's Tickers NOT in Bot's Scanner (3 tickers)
| Ticker | Ross P&L | Setup | Why Scanner Likely Missed |
|--------|----------|-------|--------------------------|
| VNCE | positive (~$9K combined w/ SLXN) | momentum squeeze, $1.73→$3.40, entry $2.99 | **Low gap% or insufficient PM volume.** VNCE ran from $1.73 intraday — likely didn't gap enough pre-market to clear scanner thresholds. The move was intraday momentum, not a pre-market gapper. |
| MVNI | +$3,900 (anchor trade) | multiple trades, third entry 9:47 AM ~$4.75→$7.50 | **Mid-morning discovery / insufficient pre-market gap.** MVNI's big move came at 9:47 AM — well after the scanner's primary 7:15 AM scan. The first trade at ~$6.00 suggests some pre-market activity, but likely insufficient gap% or volume to trigger scanner thresholds. |
| SGN | minimal/partial | missed or partial | **Insufficient data.** Ross described this as not significant — likely didn't meet any scanner criteria. |

### Overlap: 1 of 4 Ross tickers (25%) — SLXN MATCH
The scanner found SLXN as its sole candidate on Jan 29 (+57.8% gap, 30.9M PM volume, 3.0M float, Profile A). This is a textbook scanner hit — massive gap, huge PM volume, low float. Both the all-three and SQ strategy variants traded SLXN profitably. The MP strategy found SLXN but generated 0 armed signals and 0 trades. This is the second consecutive day with scanner overlap (Jan 28: YIBO, Jan 29: SLXN) — a positive trend after the Jan 22-27 drought.

## Bot's Trades — What Happened

### V2 Megatest Results (Primary Backtest)
- **All-Three Strategy:** 1 scanned → 1 passed → SLXN → **1 trade, +$211**
  - SLXN: 594,329 ticks, armed=1, signals=1, trades=1, pnl=+$211
  - Running equity: $31,187
- **SQ Strategy:** 1 scanned → 1 passed → SLXN → **1 trade, +$231**
  - SLXN: 594,329 ticks, armed=1, signals=1, trades=1, pnl=+$231
  - Running equity: $34,178
- **MP Strategy:** 1 scanned → 1 passed → SLXN → **0 trades, $0 P&L**
  - SLXN: 594,329 ticks, armed=0, signals=0, trades=0
  - Running equity: $27,889
- **MP+SQ Combined:** 1 scanned → 1 passed → SLXN → **1 trade, +$212**
  - SLXN: 594,329 ticks, armed=1, signals=1, trades=1, pnl=+$212
  - Running equity: $31,284

All strategy variants that include SQ found a trade on SLXN. MP alone did not arm — consistent with the MP strategy's chronic underperformance (0-for-14 in January). The SQ variant captured the most at +$231.

### SLXN Head-to-Head
| Metric | Ross | Bot (SQ) | Bot (All-Three) |
|--------|------|----------|------------------|
| Entry | $2.00 breakout | unknown (megatest log) | unknown (megatest log) |
| First trade result | Built to ~$7K, gave some back | +$231 | +$211 |
| Re-entry | Lost ~$2K | N/A (1 trade only) | N/A (1 trade only) |
| Net P&L | Net positive (est. ~$5K) | +$231 | +$211 |

Ross took multiple trades on SLXN — his first entry at $2.00 breakout built to ~$7K profit before giving some back, then a re-entry lost ~$2K. The bot took a single trade for +$211-$231. Without detailed entry/exit prices from the megatest log, we can estimate Ross netted ~$5K on SLXN vs the bot's ~$231 — roughly a 22x gap. The pattern is consistent: bot takes one modest trade, Ross sizes up and takes multiple swings.

## Ross's Trades — What Made Them Work

### SLXN — Net Positive (Ice Breaker)
- **Catalyst:** Leading gapper, +57.8% gap, 30.9M PM volume
- **Setup:** Breakout over $2.00, squeezed from ~$1.80→$2.00+
- **Why it worked:** Classic low-float gapper with massive volume. The $2.00 breakout was a clean whole-dollar level. Ross built to $7K, gave back some, then lost $2K on re-entry — disciplined to take what the market gave.
- **Bot comparison:** Both found and traded SLXN. Bot captured $211-$231 with a single trade. Ross's multiple entries show his style of building position and managing through the move.

### VNCE — Positive
- **Catalyst:** Momentum squeeze
- **Setup:** Ran $1.73→$3.40, entered $2.99 for $3 break, ran to $3.30
- **Why it worked:** Clean half/whole-dollar breakout at $3.00 — textbook entry with the round number as the trigger. Combined with SLXN for ~$9K early.
- **Bot comparison:** Scanner missed it. VNCE was likely an intraday mover that didn't gap enough pre-market.

### MVNI — ~+$3,900 (Day's Anchor)
- **Catalyst:** Momentum, multi-trade approach
- **Setup:** First trade at ~$6.00 lost $500. Re-entry broke even. Third entry at 9:47 AM from ~$4.75, ran to $7.50.
- **Why it worked:** Persistence. Ross took two losing/scratch trades before finding the right entry. The 9:47 AM third trade caught MVNI at $4.75 — a full $1.25 below the first entry at $6.00 — and rode it to $7.50 (58% move). This shows Ross's ability to re-calibrate mid-day and find better entries after initial losses.
- **Bot comparison:** Scanner missed MVNI entirely. The 9:47 AM entry time suggests this was a mid-morning discovery, well outside the scanner's primary pre-market window.

### SGN — Minimal
- **Notes:** Not significant in the day's P&L. Partial or missed.

## Key Takeaways

### 1. Second Consecutive Scanner Overlap — SLXN
After the Jan 22-27 drought, the scanner has now overlapped on two consecutive days: YIBO (Jan 28) and SLXN (Jan 29). Both were Profile A or B candidates with massive gap% and PM volume. This is the scanner working as designed — when a stock gaps big with huge volume and low float, the scanner finds it. SLXN was arguably the perfect scanner candidate: +57.8% gap, 30.9M PM volume, 3.0M float.

### 2. Bot Profitably Traded the Scanner Hit — Both SQ and VR Strategies
Unlike many previous days where the scanner found a Ross ticker but the bot didn't trade it (INM Jan 21, WHLR Jan 16), both the SQ and all-three variants successfully entered and exited SLXN profitably. The SQ strategy's +$231 is modest but positive. Combined with the Jan 28 YIBO VR trade (+$125), the bot has now had back-to-back winning days on scanner-overlapping tickers — a first in the series.

### 3. MVNI 9:47 AM Entry — Mid-Morning Discovery Blindspot
Ross's best trade of the day (MVNI, +$3,900) came at 9:47 AM — 2.5 hours after market open. This is a pattern we've seen before: Ross's biggest winners sometimes come from mid-morning re-entries or late discoveries. The scanner's primary window (7:15 AM pre-market) can't catch these. MVNI's first trade at ~$6.00 was early but lost $500 — the real money was in the 9:47 AM re-entry at $4.75 after the stock pulled back hard.

### 4. P&L Gap Remains Massive: $24K vs $231 (104x)
Even on a day where the scanner correctly found the #1 stock and the bot traded it profitably, Ross made 104x more. The gap comes from:
- **3 additional tickers** Ross traded that the scanner missed (VNCE, MVNI, SGN)
- **Multiple entries on SLXN** — Ross took at least 2 swings vs bot's 1 trade
- **Sizing** — Ross built to ~$7K profit on the first SLXN entry alone, suggesting significantly larger share count

### 5. MP Strategy Still Dead — 0 Trades on a Perfect Profile A Candidate
SLXN was Profile A with 3.0M float, 30.9M PM volume — exactly the type of stock MP should fire on. Yet MP generated 0 armed signals and 0 trades. The SQ and all-three variants both found winning trades on SLXN. MP's inability to fire even on A-grade candidates reinforces the "kill or rework MP" recommendation.

## Missed P&L Estimate
- **MVNI** ($4.75→$7.50, 58% move at 9:47 AM entry): If the bot had found it with $50K notional at $4.75 = 10,526 shares. Ride 30% of move ($4.75→$5.58): 10,526 × $0.83 = +$8,737. Ride 50% ($4.75→$6.13): +$14,526. **However, this was a mid-morning discovery — the bot would need intraday re-scanning capability to catch this.**
- **VNCE** ($2.99→$3.30, 10% move): $50K notional at $2.99 = 16,722 shares. 30% capture: 16,722 × $0.09 = +$1,505. Small opportunity but clean setup.
- **SGN**: Minimal — not enough detail to estimate.

**Total estimated missed opportunity: ~$8,700-$14,500 (MVNI) + ~$1,500 (VNCE) = ~$10,000-$16,000.**

**Total bot missed P&L vs Ross: $24,000 (Ross) - $231 (bot best) = ~$23,769 gap.**

## Tickers Added to Missed Stocks Backtest Plan
- VNCE (momentum squeeze, scanner miss — insufficient pre-market gap)
- MVNI (multi-trade momentum, scanner miss — mid-morning discovery)

## Running Pattern Notes
Two consecutive days with scanner overlap (Jan 28: YIBO, Jan 29: SLXN) and two consecutive bot winning days on the overlapping tickers. This is the best scanner performance streak in the January series.

Patterns:
- **Scanner works on massive gappers:** SLXN (+57.8% gap, 30.9M PM vol) and YIBO (+92.2% gap, 15.1M PM vol) were both massive gappers that the scanner correctly identified. The scanner is most reliable on the "obvious" gappers.
- **Mid-morning entries remain a blindspot:** MVNI's $3,900 came at 9:47 AM. The scanner's pre-market-only window systematically misses these opportunities.
- **MP strategy continues to fail:** 0 trades on a Profile A candidate (SLXN) while SQ and VR found winning trades. This is the 15th consecutive MP loss or no-trade on a Ross-overlapping ticker.
- **Ross's P&L concentration:** ~$3,900 of the $24K came from MVNI's third trade — one well-timed entry after two failures. The bot doesn't have the "persistence through losing trades" capability that Ross uses to find better entries.
