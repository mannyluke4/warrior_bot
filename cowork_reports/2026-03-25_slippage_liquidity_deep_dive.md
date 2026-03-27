# Slippage & Liquidity Deep Dive
## Date: 2026-03-25
## Author: Cowork (Opus) — Strategy Analyst
## Focus: The two factors that matter for live P&L

---

## Part 1: Slippage Impact Analysis

### How Slippage Works in the Current Backtest

The sim uses a **fixed $0.02 entry slippage** — it adds $0.02 to the trigger price as the fill. No exit slippage is modeled. This means every sq_target_hit (2R exit) and every sq_para_trail_exit uses the exact trigger price as the fill, with zero spread or delay.

### Position Size Reconstruction

From the backtest data, I can reconstruct approximate position sizes per equity tier. The sizing formula is:

```
risk_dollars = equity * 0.025
qty_risk = floor(risk_dollars / R)        # R = entry - stop
qty_notional = floor(MAX_NOTIONAL / fill_price)
qty = min(qty_risk, qty_notional, 100000)
```

For a typical squeeze trade on a $4 stock with R = $0.20:

| Equity Tier | Risk/Trade | qty_risk (R=$0.20) | qty_notional ($100K/$4) | Actual Qty | Notional |
|-------------|-----------|-------------------|------------------------|------------|----------|
| $30K (Tier 1) | $750 | 3,750 | 25,000 | 3,750 | $15,000 |
| $75K (Tier 2) | $1,875 | 9,375 | 25,000 | 9,375 | $37,500 |
| $150K (Tier 3) | $3,750 | 18,750 | 25,000 | 18,750 | $75,000 |
| $400K (Tier 4) | $10,000 | 50,000 | 25,000 | **25,000** | $100,000 |
| $750K (Tier 5) | $18,750 | 93,750 | 25,000 | **25,000** | $100,000 |
| $1.2M (Tier 6) | $30,000 | 150,000 | 25,000 | **25,000** | $100,000 |

**Key insight**: Above ~$200K equity, the $100K MAX_NOTIONAL cap becomes the binding constraint, NOT the 2.5% risk. So Tiers 4-6 are all trading roughly the same position size (~25,000 shares on a $4 stock). The compounding effect on P&L comes primarily from Tiers 1-3 where risk is the binding constraint.

For a $3 stock: qty_notional = 33,333. For a $6 stock: qty_notional = 16,667.

### Slippage Cost Per Trade by Tier

Slippage is applied per share, so the dollar cost is `slippage_per_share * qty * 2` (entry + exit):

**At $0.05 combined slippage (entry $0.03 + exit $0.02) — OPTIMISTIC:**

| Tier | Typical Qty | Slippage Cost | Avg Winner | Net Winner | Avg Loser | Net Loser |
|------|-------------|---------------|-----------|------------|-----------|-----------|
| Tier 1 (<$50K) | 3,750 | $188 | $1,522 | $1,334 | -$232 | -$420 |
| Tier 2 ($50-100K) | 9,375 | $469 | $2,146 | $1,677 | -$152 | -$621 |
| Tier 3 ($100-250K) | 18,750 | $938 | $7,664 | $6,726 | $0 | -$938 |
| Tier 4 ($250-500K) | 25,000 | $1,250 | $4,429 | $3,179 | -$131 | -$1,381 |
| Tier 5 ($500K-1M) | 25,000 | $1,250 | $5,735 | $4,485 | -$188 | -$1,438 |
| Tier 6 ($1M+) | 25,000 | $1,250 | $4,989 | $3,739 | -$257 | -$1,507 |

**Total P&L impact at $0.05: -$321 * $188 avg (Tier 1-2 weighted) to -$321 * $1,250 (Tier 4-6 cap)**

Weighted estimate across all 321 trades: **-$305,000** (reducing P&L from $1.35M to ~$1.04M)

**At $0.10 combined slippage (entry $0.06 + exit $0.04) — MODERATE/REALISTIC:**

| Tier | Typical Qty | Slippage Cost | Avg Winner | Net Winner | Avg Loser | Net Loser |
|------|-------------|---------------|-----------|------------|-----------|-----------|
| Tier 1 (<$50K) | 3,750 | $375 | $1,522 | $1,147 | -$232 | -$607 |
| Tier 2 ($50-100K) | 9,375 | $938 | $2,146 | $1,208 | -$152 | -$1,090 |
| Tier 3 ($100-250K) | 18,750 | $1,875 | $7,664 | $5,789 | $0 | -$1,875 |
| Tier 4 ($250-500K) | 25,000 | $2,500 | $4,429 | $1,929 | -$131 | -$2,631 |
| Tier 5 ($500K-1M) | 25,000 | $2,500 | $5,735 | $3,235 | -$188 | -$2,688 |
| Tier 6 ($1M+) | 25,000 | $2,500 | $4,989 | $2,489 | -$257 | -$2,757 |

Weighted estimate across all 321 trades: **-$610,000** (reducing P&L from $1.35M to ~$740K)

**At $0.15 combined slippage (entry $0.10 + exit $0.05) — CONSERVATIVE/THICK SPREADS:**

| Tier | Typical Qty | Slippage Cost | Avg Winner | Net Winner | Avg Loser | Net Loser |
|------|-------------|---------------|-----------|------------|-----------|-----------|
| Tier 1 (<$50K) | 3,750 | $563 | $1,522 | $959 | -$232 | -$795 |
| Tier 2 ($50-100K) | 9,375 | $1,406 | $2,146 | $740 | -$152 | -$1,558 |
| Tier 3 ($100-250K) | 18,750 | $2,813 | $7,664 | $4,851 | $0 | -$2,813 |
| Tier 4 ($250-500K) | 25,000 | $3,750 | $4,429 | $679 | -$131 | -$3,881 |
| Tier 5 ($500K-1M) | 25,000 | $3,750 | $5,735 | $1,985 | -$188 | -$3,938 |
| Tier 6 ($1M+) | 25,000 | $3,750 | $4,989 | $1,239 | -$257 | -$4,007 |

Weighted estimate across all 321 trades: **-$915,000** (reducing P&L from $1.35M to ~$435K)

### Slippage Summary Table

| Slippage Tier | Total Drag | Adjusted P&L | Adjusted Return | Win Rate Impact |
|---------------|------------|-------------|-----------------|-----------------|
| Current ($0.02 entry only) | ~$0 | $1,348,605 | +4,495% | 90% |
| $0.05 combined (optimistic) | ~$305K | **~$1,044K** | +3,479% | ~85% |
| $0.10 combined (realistic) | ~$610K | **~$739K** | +2,463% | ~78% |
| $0.15 combined (conservative) | ~$915K | **~$434K** | +1,446% | ~70% |

**Key takeaway**: Even at $0.15/share combined slippage — a worst-case scenario — the strategy is still profitable (+$434K, +1,446%). The edge is real, but the magnitude is 2-3x smaller than the backtest claims.

### Which Slippage Tier Is Realistic?

For small-cap squeeze trades ($2-$10 stocks, 1-10M float, premarket/early session):

- **Bid-ask spread**: Typically $0.02-$0.05 for these stocks during active trading. Wider ($0.05-$0.15) during thinner premarket periods before 8:30 AM.
- **Entry slippage** (buying into a squeeze): You're buying as the price breaks a level. Other buyers are competing. Realistic fill is $0.03-$0.08 above trigger. The sim assumes $0.02.
- **Exit slippage** (selling at target or on trail): Market orders into the bid, or limit orders that may not fill at the exact trail price. Realistic: $0.02-$0.05.
- **Market impact** (25,000 shares on thin book): On a $4 stock with 10,000 shares/min volume, buying 25,000 shares WILL move the price. This adds $0.05-$0.20 of additional slippage that compounds with spread.

**My assessment: $0.10 combined is the most realistic baseline for position sizes up to 15,000 shares. For 25,000+ shares, $0.15+ is more realistic due to market impact.**

This means the realistic P&L range is **$434K-$739K** — still excellent, but 2-3x below the claimed $1.35M.

---

## Part 2: Liquidity / Volume Analysis

### The Core Problem

The backtest buys shares without checking whether the stock has enough volume to absorb the order. On a squeeze trade, the bot enters on a level break — the exact moment when everyone else is also trying to buy. The order book is one-sided.

### Volume Data from Scanner Results

Here are actual PM volumes and daily volumes for traded stocks:

| Stock | Date | PM Price | PM Volume | Avg Daily Vol | Float | Typical 1m Bar Vol (est) |
|-------|------|----------|-----------|---------------|-------|------------------------|
| GDTC | 2025-01-06 | $4.04 | 6.6M | 91K | 3.7M | 10-50K |
| STAK | 2025-06-16 | $3.89 | 10.0M | 363K | 6.9M | 20-80K |
| TMDE | 2025-06-16 | $2.03 | 31.9M | 3.6M | 3.6M | 50-200K |
| LSE | 2025-06-16 | $6.92 | 2.9M | 95K | 1.5M | 5-30K |
| EVTV | 2025-09-15 | $5.01 | 7.8M | 242K | 3.0M | 15-60K |
| FRGT | 2025-09-15 | $10.30 | 3.8M | 137K | 0.5M | 5-25K |
| VERO | 2026-01-16 | $5.74 | 177.5M | 8.9M | 1.6M | 100K-500K |
| BIYA | 2026-01-16 | $6.14 | 6.0M | 395K | 0.1M | 10-40K |

**The "Typical 1m Bar Vol" is estimated as PM Volume / (total PM minutes, ~200) for the squeeze window. Actual bar volume varies enormously — some bars are 500K shares, others are 500.**

### Position Size vs. Bar Volume Analysis

At $100K MAX_NOTIONAL:

| Stock Price | Position Size | Needs Bar Vol > (10% rule) | Needs Bar Vol > (25% rule) |
|-------------|--------------|---------------------------|---------------------------|
| $2.00 | 50,000 shares | 500,000 | 200,000 |
| $3.00 | 33,333 shares | 333,333 | 133,333 |
| $4.00 | 25,000 shares | 250,000 | 100,000 |
| $6.00 | 16,667 shares | 166,667 | 66,667 |
| $10.00 | 10,000 shares | 100,000 | 40,000 |

The "10% rule" means the bot's order should be no more than 10% of the bar's volume — a conservative threshold where market impact is minimal. The "25% rule" is more aggressive but still considered manageable by institutional traders.

### Liquidity Flags by Stock Type

**Category A — HIGH LIQUIDITY (order < 10% of typical bar):**
- VERO ($5.74, 177M PM vol): Typical squeeze bar 200K-500K shares. 25,000 shares = 5-12% of bar. **FILLS FINE.**
- TMDE ($2.03, 31.9M PM vol): Typical bar 50-200K. 50,000 shares = 25-100% of bar. **MARGINAL on $2 stocks.**

**Category B — MODERATE LIQUIDITY (order 10-25% of bar):**
- GDTC ($4.04, 6.6M PM vol): Typical bar 10-50K. 25,000 shares = 50-250% of bar. **PROBLEMATIC.**
- STAK ($3.89, 10M PM vol): Typical bar 20-80K. 25,000 shares = 31-125% of bar. **PROBLEMATIC.**
- EVTV ($5.01, 7.8M PM vol): Typical bar 15-60K. 16,667 shares = 28-111% of bar. **PROBLEMATIC.**

**Category C — LOW LIQUIDITY (order > 25% of bar):**
- LSE ($6.92, 2.9M PM vol): Typical bar 5-30K. 16,667 shares = 56-333% of bar. **CANNOT FILL at this size.**
- FRGT ($10.30, 3.8M PM vol): Typical bar 5-25K. 10,000 shares = 40-200% of bar. **CANNOT FILL.**
- BIYA ($6.14, 6M PM vol, 0.1M float): 16,667 shares = 16.7% of ENTIRE FLOAT. **ABSOLUTELY CANNOT FILL.**

### Estimated Trade Distribution by Liquidity

Based on the scanner results data — typical small-cap squeeze stocks have PM volumes of 3-30M shares:

| Liquidity Category | % of Trades (est) | Impact on P&L |
|-------------------|-------------------|---------------|
| A: Fills cleanly (<10% of bar) | ~25% (80 trades) | Minimal — $0.02-$0.05 slippage |
| B: Fills with impact (10-50% of bar) | ~45% (145 trades) | Moderate — $0.05-$0.15 slippage |
| C: Cannot fill at full size (>50% of bar) | ~30% (96 trades) | Severe — must reduce position 50-75%, OR accept $0.20+ slippage |

### What Happens to P&L If We Cap Position Size at Liquidity Limits?

If we assume Category C trades can only fill at 50% of the intended size, and Category B trades experience 2x the slippage:

**Category A** (80 trades): $0.05 combined slippage → drag ~$30K
**Category B** (145 trades): $0.12 combined slippage (spread + impact) → drag ~$290K
**Category C** (96 trades): 50% position size + $0.15 slippage → P&L reduced by ~50% on these trades

Category C trades currently account for roughly $400K of the total P&L (96/321 * $1.35M, pro-rated). Cutting them in half: -$200K.

**Liquidity-adjusted total drag: ~$520K** (on top of the slippage drag)

---

## Part 3: Combined Realistic P&L Estimate

| Adjustment | P&L Impact | Running Total |
|-----------|-----------|---------------|
| Backtest claim | — | $1,348,605 |
| Slippage @ $0.10 average | -$610,000 | $738,605 |
| Liquidity haircut (Cat C at 50% size) | -$200,000 | $538,605 |
| Market impact on Cat B trades | -$145,000 | **$393,605** |

**Realistic P&L estimate: $350K-$550K** (range accounts for uncertainty in per-trade liquidity)

This still represents a **+1,167% to +1,833% return** on $30K over 15 months. That's an extraordinary result — far better than any retail trader achieves. But it's roughly **3-4x smaller** than the backtest claims.

---

## Part 4: What CC Needs to Do (Directive)

The analysis above uses estimated position sizes and estimated bar volumes. To get PRECISE numbers, CC needs to extract the actual per-trade data from simulate.py output. Here's the directive:

### DIRECTIVE: Per-Trade Slippage & Liquidity Extraction

**Goal**: Run the megatest again with enhanced logging to capture per-trade details needed for precise slippage/liquidity modeling.

**Option A (Preferred — Quick)**: Modify run_backtest_v2.py to capture MORE fields from simulate.py output:
- Entry price, exit price, R value, quantity, entry time, exit time
- The regex `TRADE_PAT` already captures some of this — extend it to include qty
- Save to a CSV: `megatest_trades_detailed.csv`

**Option B (Even Better — Slippage Sensitivity)**: Run the megatest 3x at different slippage levels:
1. `--slippage 0.05` (combined $0.05 entry, assume $0.05 exit via code tweak)
2. `--slippage 0.10`
3. `--slippage 0.15`

This gives us the ACTUAL slippage sensitivity rather than my estimates.

**Option C (Best — Volume Check)**: Add a `--min-bar-vol-pct` flag to simulate.py that checks the entry bar's volume against the position size. If `qty > bar_volume * pct_threshold`, either reduce qty to the threshold or skip the trade. Run at 10% and 25% thresholds.

**Priority**: Option B first (simplest, most informative), then Option C (harder but answers the liquidity question definitively).

**Regression**: After any code change, verify VERO +$18,583 and ROLR +$6,444 still pass.

---

## Part 5: Recommendations for Live Paper Trading (Tomorrow)

1. **Track every fill** — log the trigger price, intended qty, actual fill price, actual fill qty, and the bar volume at the time of entry. This is the single most important data to collect.

2. **Start with $50K MAX_NOTIONAL, not $100K** — this reduces position sizes by 50% and makes fills much more realistic on thin stocks. Scale up ONLY after confirming fills are clean.

3. **Set a volume floor** — if the stock's 1-min bar volume at entry time is below 50,000 shares, reduce position size to 25% of bar volume. This prevents the bot from being the entire tape.

4. **Compare live fills to backtest fills** — for every trade tomorrow, run the same stock through simulate.py and compare. The delta between live and backtest fills IS your slippage number.

5. **Realistic P&L expectations for day 1**: On a good day with 1-3 trades, expect $500-$3,000 gross profit before slippage, minus $200-$1,000 in execution costs = **$0-$2,000 net**. On a day with no setups (which is most days — only 121/301 dates had trades), expect $0.

---

## Bottom Line

The strategy has a real edge. Even after aggressive haircuts for slippage and liquidity, the backtest suggests **$350K-$550K over 15 months from $30K** — which is still a remarkable result. The key risks for live trading are:

1. **Slippage eats 45-70% of gross P&L** depending on position size and stock liquidity
2. **30% of backtested trades probably can't fill at full size** — these need reduced sizing or should be skipped
3. **The $100K MAX_NOTIONAL is too aggressive** for most small-cap squeeze entries — $50K is a safer starting point

Tomorrow's paper session will start producing real data on all three of these factors. That data is worth more than any backtest analysis.
