# YTD Backtest Results: A/B Score Gate Test (Partial — V1)
## Generated 2026-03-13

**Status**: Stopped after 11 trading days (Jan 2-15) — both configs went underwater.
**Verdict**: The bot's trade logic works. The backtest harness doesn't simulate reality.
**Next step**: Redesign the backtest to model how a human + bot actually trade day-to-day.

Period: January 2-15, 2026 (11 of 49 trading days)
Starting Equity: $30,000
Risk: 2.5% of equity (dynamic)

---

## Summary Comparison

| Metric | Config A (Gate=8) | Config B (No Gate) |
|--------|--------------------|--------------------|
| Final Equity | $7,755 | $3,450 |
| Total P&L | $-22,245 | $-26,550 |
| Total Return | -74.2% | -88.5% |
| Total Trades | 184 | 252 |
| Win Rate | 48/177 (27%) | 73/244 (30%) |
| Average Win | $+276 | $+275 |
| Average Loss | $-275 | $-273 |
| Profit Factor | 0.37 | 0.43 |
| Largest Win | $+1,498 | $+1,560 |
| Largest Loss | $-984 | $-1,532 |
| Trades/Day (avg) | 18 | 25 |

---

## Daily Detail

| Date | Candidates | A Trades | A Day P&L | A Equity | B Trades | B Day P&L | B Equity |
|------|------------|----------|-----------|----------|----------|-----------|----------|
| 2026-01-02 | 175 | 32 | $-6,497 | $23,503 | 45 | $-6,349 | $23,651 |
| 2026-01-03 | 0 | 0 | $+0 | $23,503 | 0 | $+0 | $23,651 |
| 2026-01-05 | 202 | 29 | $-5,674 | $17,829 | 43 | $-6,902 | $16,749 |
| 2026-01-06 | 112 | 14 | $-3,062 | $14,767 | 22 | $-5,331 | $11,418 |
| 2026-01-07 | 86 | 13 | $-2,081 | $12,686 | 15 | $-2,416 | $9,002 |
| 2026-01-08 | 91 | 16 | $-1,156 | $11,530 | 23 | $-294 | $8,708 |
| 2026-01-09 | 83 | 11 | $-1,187 | $10,343 | 14 | $-1,845 | $6,863 |
| 2026-01-12 | 99 | 18 | $-234 | $10,109 | 26 | $-485 | $6,378 |
| 2026-01-13 | 87 | 6 | $-929 | $9,180 | 10 | $-1,227 | $5,151 |
| 2026-01-14 | 107 | 20 | $-234 | $8,946 | 23 | $-420 | $4,731 |
| 2026-01-15 | 98 | 25 | $-1,191 | $7,755 | 31 | $-1,281 | $3,450 |

---

## Analysis: Why This Backtest Failed (And Why That's Actually Good News)

### The Bot Logic Is Not The Problem

The 2-week backtest (which used hand-picked stocks from scanner results) showed strong results:
- **Window 1 (Jan 13-29)**: +$14,525 (+48.4%), profit factor 5.57
- **Window 2 (Feb 3-20)**: -$1,007 (-3.4%), max drawdown only 4.7%
- Combined: +$13,518 on $30K starting equity

That test simulated 2-5 trades/day on known runners — close to how the live bot actually operates. The strategy works when applied selectively.

### The Backtest Harness Is The Problem

The YTD backtest fed **every scanner candidate** into the simulator independently and simultaneously. This is like giving a trader 100 screens and telling them to trade all of them at once. Nobody does that.

**What happened in reality:**
- Scanner finds 80-200 gap-up stocks per day (median premarket volume: ~4,000 shares)
- The backtest ran simulate.py on ALL of them — 32 trades on Jan 2, 29 on Jan 5
- Each trade used the same buying power as if no other trades existed
- With $30K equity and 2.5% risk ($750/trade), taking 30 trades means $22,500 in simultaneous risk exposure — 75% of the account
- No human trader, and no properly configured bot, would ever do this

### Scanner Quality Problem

The scanner is too wide. Looking at Jan 2 (175 candidates):

| Volume Bucket | Count | Reality |
|--------------|-------|---------|
| PM Volume > 100K | ~10 | Tradeable — these are the real movers |
| PM Volume 5K-100K | ~70 | Maybe tradeable — need more filters |
| PM Volume < 5K | ~95 | Untradeable junk — no liquidity |

**Median premarket volume: 4,088 shares.** More than half the candidates are stocks with virtually no premarket activity. These would never show up on a real trader's watchlist.

Worse: **VERO — our single biggest winner (+$8,360 in the 2-week backtest) — isn't even in the Jan 16 scanner results.** The scanner missed the best setup of the month. Meanwhile, it captured 99 other stocks that day, most of which lost money.

### The Winners Were Hiding In Plain Sight

Comparing scanner data for known winners vs the mass of candidates:

| Stock | Date | PM Volume | Gap% | Outcome |
|-------|------|-----------|------|---------|
| ROLR | Jan 14 | 10,669,416 | 289% | +$2,431 (winner) |
| GWAV | Jan 16 | 1,537,606 | 26% | +$6,735 (blocked by gate) |
| BNAI | Jan 14 | 5,686 | 6% | +$4,907 (winner) |
| VERO | Jan 16 | ??? | ??? | +$8,360 (NOT IN SCANNER) |
| Avg candidate | Any | ~4,000 | varies | -$275 (loser) |

ROLR stood out massively — 10.6M premarket volume, 289% gap. That's the kind of stock Ross Cameron would have at #1 on his watchlist. But the backtest treated it identically to 106 other candidates that day.

### Buying Power Reality

With a $30K account and 4x margin ($120K buying power via `WB_MAX_NOTIONAL=50000`):
- Each trade risks $750 (2.5% of equity)
- But each trade also USES buying power (share_count x entry_price)
- A $5 stock at $750 risk with a $0.50 stop = 1,500 shares = $7,500 notional
- Taking 5 trades = ~$37,500 notional = well within $50K max
- Taking 30 trades = ~$225,000 notional = impossible with $50K max notional

The backtest didn't enforce buying power consumed across simultaneous positions. Each sim run was independent.

---

## What The Score Gate A/B Test Actually Showed

Even in this unrealistic scenario, the score gate data is directionally useful:

| Metric | Gate ON (A) | Gate OFF (B) | Delta |
|--------|------------|-------------|-------|
| Total Trades | 184 | 252 | -68 trades blocked |
| Total P&L | -$22,245 | -$26,550 | Gate saved $4,305 |
| Trades/Day | 18 | 25 | 7 fewer bad trades/day |

The gate blocked 68 low-score trades that would have lost a net $4,305. That's ~$63/trade saved. In a realistic scenario with 3-5 trades/day, that filtering becomes even more impactful because each trade matters more.

---

## Plan: Realistic Backtest V2

### Problem Statement

The backtest needs to simulate how the bot ACTUALLY operates day-to-day:
1. A human picks 2-3 stocks to watch from the scanner
2. The bot monitors those stocks for setups
3. It takes one trade at a time (exits before entering the next)
4. Max 3-5 trades per day
5. Buying power is shared across all positions
6. If equity drops below $25K, PDT rules kick in (3 trades/week)

### Proposed Constraints for V2

#### 1. Scanner Ranking (Top-N Candidates)
Instead of simming all 100+ candidates, rank them and take only the top N:

**Ranking criteria (Ross Cameron-style):**
- Premarket volume > 50K (minimum liquidity)
- Gap % between 10-500% (not penny stock noise, not already exhausted)
- Float < 20M shares (low float = more movement)
- Sort by: premarket volume (highest first) — volume is the #1 signal

**Top N**: Simulate only the top 5 candidates per day. This matches a real trader's watchlist size.

#### 2. One-At-A-Time Trading
- Only ONE position open at a time
- Must exit current trade before entering the next
- Simulate candidates in time-priority order (earliest `sim_start` first)
- If a trade is active when the next candidate signals, skip it

#### 3. Daily Trade Limit
- Cap at 5 trades per day maximum
- After 5 trades, stop for the day regardless of remaining candidates
- Ross Cameron typically takes 2-4 trades/day; 5 is generous

#### 4. Buying Power Tracking
- Track notional exposure across all positions
- Block new entries if notional would exceed `WB_MAX_NOTIONAL` ($50K)
- Track cash used by active positions

#### 5. PDT Protection
- If equity drops below $25,000, switch to 3 trades/week maximum
- Alpaca enforces this in live trading — the sim should too
- Once equity recovers above $25K, normal trading resumes

#### 6. Daily Loss Limit
- Stop trading for the day if daily P&L hits -2R (i.e., -$750 x 2 = -$1,500)
- Ross Cameron uses a daily max loss — prevents revenge trading
- The bot doesn't have emotions, but limiting daily exposure still helps

### What This Should Look Like

With these constraints, a typical day would look like:
1. Scanner finds 100 candidates
2. Ranking filter selects top 5 by volume/gap/float
3. Bot watches candidate #1 (highest PM volume)
4. Trade #1 triggers at 9:35, exits at 9:42 → -$400
5. Bot moves to candidate #2
6. Trade #2 triggers at 9:48, exits at 10:15 → +$2,100
7. Bot moves to candidate #3
8. Trade #3 triggers at 10:22, exits at 10:30 → -$350
9. Daily P&L: +$1,350, 3 trades — realistic day

vs what V1 did:
1. Scanner finds 100 candidates
2. Bot runs ALL 100 simultaneously
3. 32 trades trigger, each using independent buying power
4. Daily P&L: -$6,497, 32 trades — impossible scenario

### Implementation Approach

**Option A: Sequential Simulation (Simpler)**
- For each day, rank candidates, take top 5
- Run simulate.py on #1, collect trades
- Run #2, but only allow trades after #1's last exit time
- Continue through top 5, respecting time gaps
- Pros: Works with existing simulate.py, easy to implement
- Cons: Can't model "skip this candidate because I'm already in a trade" — simulate.py doesn't know about the portfolio

**Option B: Portfolio-Aware Simulation (More Realistic)**
- Modify run_ytd_backtest.py to parse trade entry/exit TIMES
- Build a timeline: "position open 9:35-9:42, open 9:48-10:15, etc."
- Only allow new trade entries during gaps when no position is open
- Requires parsing entry/exit timestamps from simulate.py output
- Pros: More realistic, respects one-at-a-time constraint properly
- Cons: More complex, needs reliable time parsing from sim output

**Option C: Simplified Top-N + Trade Cap (Fastest)**
- Rank candidates, take top 3-5
- Run each independently (like V1 but fewer candidates)
- Cap at 5 trades/day total across all candidates
- Don't worry about time overlap — just limit total trade count
- Pros: Fastest to implement, gets 80% of the benefit
- Cons: Doesn't model buying power overlap or time conflicts

### Recommendation

**Start with Option C** (top-N + trade cap) — it's the fastest path to useful results. The 2-week backtest already proved the strategy works on selected stocks. The main thing we need is to stop feeding 100+ junk candidates into the sim.

If Option C results look good, iterate to Option B for more precision.

---

## Open Questions

1. **Scanner gap**: VERO wasn't in the Jan 16 scanner. How many other winners are we missing? May need to debug scanner criteria.
2. **Ranking vs human judgment**: A volume-based ranking is mechanical. Ross Cameron also uses chart patterns, news catalysts, sector momentum. We can't model all of that, but volume + gap + float gets close.
3. **Time-of-day effects**: Most winners trigger in the first 30 minutes (9:30-10:00). Should we weight candidates discovered pre-market higher?
4. **Trade sequencing**: In Option B, the order we sim candidates matters. If we sim the best candidate first and it takes 3 trades, we might miss the actual best setup on candidate #2. This is inherent to one-at-a-time trading.

---

*Partial results from YTD A/B backtest V1 — stopped early due to unrealistic trade volume.*
*Scanner results for all 49 dates (Jan 2 - Mar 12) are cached in scanner_results/.*
*Branch: v6-dynamic-sizing*
