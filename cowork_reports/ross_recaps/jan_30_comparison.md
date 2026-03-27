# Jan 30, 2025 — Ross vs Bot Comparison

## Summary
| Metric | Ross | Bot (All-Three v2) | Bot (SQ v2) | Bot (MP v2) |
|--------|------|---------------------|-------------|-------------|
| Daily P&L | positive (amount unknown) | -$714 | $0 (0 trades) | -$639 |
| Trades | 2 tickers (AMOD, FOXX) | 1 trade (STAI) | 0 trades | 1 trade (STAI) |
| Win Rate | 1/2 tickers profitable | 0/1 (0%) | N/A | 0/1 (0%) |
| Best Trade | AMOD (primary winner, breaking news) | — | — | — |
| Worst Trade | FOXX (loss, no news, late session) | STAI -$714 | — | STAI -$639 |

**Ross had a positive day led by AMOD on breaking news, but specific P&L was not stated. The bot lost money across all strategy variants that traded — the only trade was STAI (micro pullback), which hit max loss in 1 minute. The scanner DID find AMOD (+79.9% gap, 6.3M PM volume) but it was Profile X (no float data) and got filtered out before trading. FOXX was not on the scanner at all. This is a "scanner found it but couldn't trade it" day — the float data gap directly cost the bot a potential winner.**

**Market context:** AMOD was the day's leading momentum play with breaking news. Ross built a pre-market cushion and rode the post-open squeeze at 9:35-9:40 AM, giving back ~20% from peak. He stopped trading at ~10:30 AM after his 20% drawdown rule triggered. January MTD building toward $350K+.

## Scanner Overlap

### Bot's Scanner Found (3 tickers)
| Ticker | Gap% | Float | PM Vol | Profile | Bot Traded? | Ross Traded? |
|--------|------|-------|--------|---------|-------------|--------------|
| AMOD | +79.9% | N/A | 6.3M | X | NO (filtered — no float) | YES (primary winner) |
| BNZI | +42.0% | 2.34M | 9.0M | A | NO (selected but no entry) | NO |
| STAI | +34.0% | 1.0M | 8.6M | A | YES (-$714 all-three, -$639 MP) | NO |

### Ross's Tickers NOT in Bot's Scanner (1 ticker)
| Ticker | Ross P&L | Setup | Why Scanner Likely Missed |
|--------|----------|-------|--------------------------|
| FOXX (FOXO) | loss | late session, no news | **No catalyst, no significant gap.** Ross himself noted this was a low-conviction "make it back" trade late in the session. No news, no pre-market gap — scanner would never find this type of trade. |

### Overlap: 1 of 2 Ross tickers scanned (AMOD) — but NOT TRADED
The scanner found AMOD as the #1 gapper by gap% (+79.9%) but AMOD had null float data (Profile X), so it was filtered out of the trading candidates. Only BNZI and STAI were selected for trading. This is the second time in January the scanner found a Ross primary winner but couldn't trade it due to Profile X filtering (Jan 6 GDTC was the first). The float data gap is a direct, quantifiable scanner limitation.

FOXX was not on the scanner — it was a late-session, no-news trade that Ross himself described as low-conviction. This is not a meaningful scanner miss.

## Bot's Trades — What Happened

### V2 Megatest Results (Primary Backtest)
- **All-Three Strategy:** 3 scanned → 2 passed → BNZI, STAI → **1 trade on STAI, -$714**
  - STAI: entry $2.13 at 09:07, exit $2.02 at 09:08, reason: max_loss_hit, -0.9R
  - Notional: $13,827, setup: micro_pullback
  - Running equity: $30,473
- **SQ Strategy:** 3 scanned → 2 passed → BNZI, STAI → **0 trades, $0**
  - No SQ signals triggered on either BNZI or STAI
  - Running equity: $34,178
- **MP Strategy:** 3 scanned → 2 passed → BNZI, STAI → **1 trade on STAI, -$639**
  - STAI: entry $2.13 at 09:07, exit $2.02 at 09:08, reason: max_loss_hit, -0.9R
  - Notional: $12,372, setup: micro_pullback
  - Running equity: $27,250
- **MP+SQ Combined:** 3 scanned → 2 passed → BNZI, STAI → **1 trade on STAI, -$717**
  - STAI: entry $2.13 at 09:07, exit $2.02 at 09:08, reason: max_loss_hit, -0.9R
  - Notional: $13,881, setup: micro_pullback
  - Running equity: $30,567

The only trade across all variants was a micro_pullback on STAI that immediately failed — entered at $2.13, stopped out at $2.02 in under a minute. The SQ strategy correctly avoided this trade (no SQ signal triggered). BNZI generated 0 trades across all strategies despite being Profile A. The bot's scanner found the right stock (AMOD) but the float filter blocked it.

### STAI Trade Breakdown
| Metric | Bot (All-Three) | Bot (MP) |
|--------|-----------------|----------|
| Entry | $2.13 at 09:07 | $2.13 at 09:07 |
| Exit | $2.02 at 09:08 | $2.02 at 09:08 |
| Duration | ~1 minute | ~1 minute |
| Exit reason | max_loss_hit | max_loss_hit |
| P&L | -$714 | -$639 |
| R-Multiple | -0.9R | -0.9R |

This was a quick failure — the micro pullback setup on STAI reversed almost immediately. Ross did not trade STAI, correctly avoiding it. This is another data point supporting the "kill or rework MP" thesis: MP fired on STAI (a stock Ross wouldn't touch) and lost money in under a minute.

## Ross's Trades — What Made Them Work

### AMOD — Primary Winner (Breaking News)
- **Catalyst:** Breaking news (specific catalyst not detailed in recap)
- **Setup:** Pre-market cushion built, post-open squeeze at 9:35-9:40 AM
- **Scanner data:** +79.9% gap, 6.3M PM volume, 42.4x relative volume, no float data available
- **Why it worked:** Breaking news on a low-priced stock ($2.77 PM price) with massive relative volume (42x normal). Ross built a position in pre-market, then rode the 9:35-9:40 AM squeeze. Gave back ~20% from peak — disciplined exit using his drawdown rule.
- **Bot comparison:** Scanner found AMOD but couldn't trade it (Profile X, null float). If the bot had traded AMOD, this could have been a winning day. The +79.9% gap and 42x RVOL suggest this was an A+ setup that the float filter unnecessarily blocked.

### FOXX (FOXO) — Loss (No News)
- **Catalyst:** None — no news
- **Setup:** Late-session trade, part of "make it back" mentality
- **Why it failed:** No catalyst, low conviction. Ross described this as the result of chasing after giving back gains on AMOD. Classic tilt trade.
- **Bot comparison:** Scanner correctly didn't find this — it's not the type of stock the scanner should be looking for.

## Key Takeaways

### 1. AMOD: Scanner Found It, Float Filter Blocked It — Profile X Problem Recurs
This is the second time in January the scanner found a Ross primary winner but the Profile X filter (null float data) prevented trading. Jan 6 GDTC (+93.6% gap, Ross made +$5,300) was the first instance. AMOD had all the hallmarks of an A+ setup: +79.9% gap, 6.3M PM volume, 42.4x relative volume, breaking news catalyst. The ONLY reason the bot didn't trade it was missing float data. This is a solvable problem — either find an alternative float data source, or allow Profile X stocks to trade with conservative sizing when other metrics (gap%, PM volume, RVOL) are strong enough.

### 2. Bot Traded the Wrong Stock — STAI MP Failure Continues the Pattern
The bot skipped AMOD (the day's winner) and instead traded STAI via micro pullback — a stock Ross didn't even look at. The trade lasted 1 minute, lost -$714, and was a max_loss_hit. This is MP's 16th consecutive loss or no-trade on a Ross-relevant ticker. The SQ strategy correctly avoided STAI (0 trades), reinforcing that SQ has better signal quality than MP.

### 3. Three Consecutive Scanner Overlap Days — But Diminishing Returns
Jan 28: YIBO (+$125 bot), Jan 29: SLXN (+$231 bot), Jan 30: AMOD (found but not traded). The scanner has now overlapped with a Ross ticker three days running — the longest streak in January. But Jan 30 shows the overlap was "hollow" — the scanner found the right stock but couldn't act on it. The streak is: Win, Win, Blocked.

### 4. Ross's Discipline: 20% Drawdown Rule and Early Stop
Ross stopped trading at ~10:30 AM after giving back too much from his AMOD peak — applying his 20% drawdown rule. He then took one more trade (FOXX, loss) in a "make it back" moment he acknowledged was low-conviction. The self-awareness about the FOXX trade as a tilt play is notable — even Ross's discipline slips sometimes, but he keeps the damage contained.

### 5. SQ Strategy's Best Decision: Not Trading
On a day where the only MP trade lost -$714, the SQ strategy generated 0 trades and $0 P&L. Sometimes the best trade is no trade. SQ's signal quality filter continues to outperform MP's trigger-happy approach.

## Missed P&L Estimate
- **AMOD:** Scanner found it (+79.9% gap, $2.77 PM price). If the bot had been allowed to trade it with $50K notional at $2.77 = 18,051 shares. Ross rode the 9:35-9:40 squeeze and gave back 20% from peak. Conservative estimate: if the bot captured even a small portion of the move (say 10-15 cents), that's 18,051 × $0.12 = +$2,166. A larger capture (30 cents) = +$5,415. **The float filter cost the bot somewhere between +$2,000 and +$5,000 on a conservative estimate.**
- **FOXX:** Not worth estimating — no news, late session, loss for Ross too.

**The gap on Jan 30 isn't a scanner problem — the scanner worked. It's a data quality problem (missing float) that turned a potential winning day into a losing one.**

## Tickers Added to Missed Stocks Backtest Plan
- FOXX/FOXO (no-news late session trade, scanner miss — not meaningful)

Note: AMOD is NOT a scanner miss — it was found but filtered out. This should be tracked separately as a "Profile X blocked trade" alongside Jan 6 GDTC.

## Running Pattern Notes
Three consecutive days of scanner overlap (Jan 28: YIBO, Jan 29: SLXN, Jan 30: AMOD). First time the scanner has found a Ross ticker three days running. However, the quality of the overlap is uneven: two winning bot trades followed by a blocked trade due to missing float data.

Patterns updated:
- **Profile X blocking is now a confirmed recurring problem:** AMOD (Jan 30) and GDTC (Jan 6) are both cases where the scanner found the stock, gap% and volume were excellent, but null float data prevented trading. Two instances in one month is enough to prioritize a fix.
- **MP strategy continues its losing streak:** STAI -$714 is another quick MP failure. The running record: 0 wins out of 15+ MP trades on days with Ross overlap. SQ correctly avoided the STAI trade.
- **Bot trades stocks Ross ignores, ignores stocks Ross trades:** On Jan 30, the bot traded STAI (Ross didn't touch it) and didn't trade AMOD (Ross's primary winner). This is the inverse selection problem at its most visible.
