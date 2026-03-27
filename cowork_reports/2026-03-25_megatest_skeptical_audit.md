# Megatest Skeptical Audit: $30K → $1.38M Claims
## Date: 2026-03-25
## Author: Cowork (Opus) — Strategy Analyst
## Verdict: Results are NOT trustworthy. Multiple critical biases inflate P&L by 5-20x.

---

## Executive Summary

The V2 IBKR mega backtest claims $30K → $1,378,605 (+4,495%) over 15 months with a 90% win rate. **This is too good to be true, and the data confirms it.** I found six compounding problems that, together, likely inflate the real-world P&L by somewhere between 5x and 20x. The strategy has a real edge — the V1 results on capped notional were promising — but the V2 megatest is not a reliable estimate of live performance.

**Manny should NOT treat these numbers as a realistic performance target.** The first live paper session tomorrow will be the real test.

---

## Problem 1: Unchecked Compounding Creates Fantasy Position Sizes

**Severity: CRITICAL**

The backtest compounds equity at 2.5% risk per trade with no ceiling. Here's what that actually means in practice:

| Equity | Risk/Trade (2.5%) | MAX_NOTIONAL Cap | Shares at $4 | Shares at $3 |
|--------|-------------------|------------------|--------------|--------------|
| $30,000 | $750 | $100,000 | 25,000 | 33,333 |
| $100,000 | $2,500 | $100,000 | 25,000 | 33,333 |
| $500,000 | $12,500 | $100,000 | 25,000 | 33,333 |
| $1,000,000 | $25,000 | $100,000 | 25,000 | 33,333 |

The $100K MAX_NOTIONAL cap means position sizes are actually capped at 25,000-33,333 shares on $3-4 stocks. But here's the problem: **at $1M equity, you're risking $25,000 per trade on a $100K position in a $3 small-cap stock.** That's a 25% risk-to-notional ratio, meaning the stop is only $0.75 below entry. On a stock that gaps and moves in $0.50 increments premarket, a single bad fill wipes out your entire risk budget.

More importantly, the **dollar P&L per trade scales linearly with risk**, so late-period trades are printing $10K-$40K per winner. This is the compounding illusion — the same 2R winner that made $1,500 in January 2025 makes $40,000 in late 2025, not because the strategy got better, but because the bet size grew 27x.

**The V1 megatest on the same period**: +$118,369 (394.6% return) with $50K MAX_NOTIONAL and the same 2.5% risk. That's 1/11th of V2's claim. The $100K notional cap and compounding equity explain roughly a 2-3x difference, but NOT an 11x difference. Something else is wrong.

---

## Problem 2: Scanner Results Are Post-Hoc (Survivorship Bias)

**Severity: CRITICAL**

The scanner_results JSON files were regenerated on March 25 using `ibkr_historical` discovery method. This means:

1. **The scanner ran after the fact**, using historical IBKR data to determine which stocks gapped enough, had sufficient volume, and met filter criteria. A live scanner running at 7:15 AM would see a DIFFERENT universe of candidates — some that looked good at 7:15 faded by 8:00, and some that weren't gapping at 7:15 exploded by 8:30.

2. **The backfill covered 244 dates in 2025 and 57 dates in 2026 (301 total)**. That's the entire trading calendar. A live scanner on January 6, 2025 didn't have the benefit of knowing GDTC would be the day's runner. The historical scanner sees the *final* gap%, volume, and RVOL for the premarket window, not the evolving picture a live scanner processes.

3. **Only stocks that met the filters appear in the JSON.** A live scanner might have surfaced 50 candidates that day, 30 of which met initial filters, 15 of which faded before the bot could trade them. The JSON only contains the 3-7 that survived filtering — this is classic survivorship bias.

4. **Candidate ranking**: The runner takes `cands[:5]` — the top 5 from each JSON. How were they ranked? If ranked by gap_pct or volume (metrics correlated with the day's performance), the top 5 are systematically the best opportunities. A live scanner might have ranked them differently at discovery time.

**How much does this inflate results?** The V1 megatest used a different set of scanner_results (Alpaca-era, with the RVOL bug). V2 regenerated them with IBKR data and "fixed" the RVOL computation. But today's morning report showed that scanner_sim found **0 stocks** while the live bot found **6** — the RVOL bug was supposedly fixed, yet scanner parity still doesn't exist. This suggests the "fixed" IBKR scanner_results may actually be selecting a *different* (and possibly more favorable) stock universe than a live scanner would.

---

## Problem 3: No Slippage Model Worth the Name

**Severity: HIGH**

The simulate.py code applies a fixed $0.02 slippage on entry (line 363: `fill_price = entry + self.slippage`). The batch runner doesn't pass any `--slippage` argument, so it uses the hardcoded default.

**Reality check on slippage for small-cap squeeze trades:**

| Scenario | Realistic Slippage | Bot Assumes |
|----------|-------------------|-------------|
| Entry on PM high break ($4.00 level) | $0.05-$0.15 (spread + momentum) | $0.02 |
| Entry at 08:15 golden hour (thin book) | $0.10-$0.30 | $0.02 |
| Exit on sq_target_hit (2R, taking profit) | $0.03-$0.10 (market order into bid) | $0.00 |
| Exit on sq_para_trail (parabolic reversal) | $0.05-$0.20 (fast reversal, spread widens) | $0.00 |

**Per-trade slippage cost estimate**: $0.08-$0.25 combined entry+exit, on 15,000-25,000 shares = **$1,200-$6,250 per trade.**

With 321 trades, at a conservative $1,500 average slippage: **$481,500 in unmodeled slippage costs.** That's 35% of the total claimed P&L.

At $3,000 average (more realistic for large positions in thin premarket books): **$963,000 — wiping out 71% of the P&L.**

---

## Problem 4: No Volume/Liquidity Validation

**Severity: HIGH**

The position sizing code (simulate.py lines 368-382) calculates quantity from risk, notional cap, and buying power — but **never checks whether the stock actually traded enough volume to fill the order.**

A $100K position in a $4 stock = 25,000 shares. These are small-cap stocks with floats of 1-10M shares. During the premarket squeeze window (7:00-9:30 AM):

- A typical 1-minute bar might show 5,000-30,000 shares of volume
- Taking 25,000 shares in a single minute would consume the entire bar's volume in many cases
- In reality, this would move the price $0.10-$0.50 against you (market impact)
- The backtest assumes: you fill 25,000 shares at $4.02 (trigger + $0.02 slippage) with zero market impact

**This is the single most unrealistic assumption.** Market impact on small-cap squeezes is enormous. When you buy 25,000 shares of a $4 stock that's squeezing through PM high, you ARE the squeeze. The backtest acts as if you're an invisible observer who can take any size without affecting the price.

---

## Problem 5: The Drawdown Is Impossibly Small

**Severity: RED FLAG**

The analysis shows a max drawdown of **-$322 (0.89%)**. Over 321 trades across 15 months. This is physically impossible for a real trading strategy.

For context:
- Renaissance Technologies' Medallion Fund (the most successful quant fund in history) has had drawdowns of 10-20%
- Ross Cameron, trading the exact same setups, has weeks where he gives back $20K-$50K
- Any strategy with a 10% loss rate should, over 321 trades, produce at least 5-10 consecutive losing streaks

**A 48-trade win streak (May 6 – July 2, 2025)**: The probability of 48 consecutive wins with a true 90% win rate is 0.90^48 = 0.5%. With a more realistic 60-70% win rate, it's essentially impossible.

**This drawdown profile is a signature of look-ahead bias or overfitting.** The strategy "knows" which stocks to pick because the scanner_results were generated after the fact.

---

## Problem 6: The V1 → V2 Gap Is Unexplainable

**Severity: HIGH**

| Metric | V1 Megatest (SQ-only) | V2 Megatest (IBKR) |
|--------|----------------------|---------------------|
| Period | Jan 2025 – Mar 2026 | Jan 2025 – Mar 2026 |
| Total P&L | +$118,369 | +$1,348,605 |
| Trades | 183 | 321 |
| Win Rate | 70% | 90% |
| MAX_NOTIONAL | $50,000 | $100,000 |
| Scanner Data | Alpaca (buggy RVOL) | IBKR (regenerated) |

The V2 result is **11.4x higher** than V1. What explains this?

- **2x MAX_NOTIONAL** ($50K → $100K): accounts for roughly 2x P&L increase
- **More trades** (183 → 321): V2 found 138 additional trades. These come from the regenerated IBKR scanner_results, which surface a different (and apparently much more profitable) stock universe
- **Win rate jump** (70% → 90%): This 20-point jump is enormous. If the strategy logic is identical, the only thing that changed is the input data (which stocks get backtested). A 20-point WR jump from changing scanner data alone suggests the new scanner_results are selecting a more favorable universe.

**The 138 additional trades are the smoking gun.** They contribute roughly +$750K in incremental P&L (assuming they perform at the average). These trades didn't exist in V1 because the Alpaca scanner had the RVOL bug. But the question is: would a LIVE IBKR scanner have found them? Given that today's live bot found 6 stocks while scanner_sim found 0, the answer is: we don't know.

---

## Problem 7: Reality Check — Ross Cameron Comparison

Ross Cameron is arguably the best small-cap day trader alive. He trades the same setups with:
- 20+ years of experience
- Multiple monitors, Level 2, tape reading
- Real-time news feeds and catalysts
- $500K-$1M+ in trading capital
- Direct-access routing on real exchanges

His publicly reported results:
- **Full year 2025**: ~$480K total — and that included some $100K+ losses and small account challenges
- **January 2025**: ~$180K (his best month in years)
- **January 2026**: ~$90K

Ross made $480K in 2025 trading the same small-cap setups with 20+ years of experience, $500K-$1M in capital, Level 2 tape reading, real-time news, and direct-access routing. Our bot claims **$1.35M from $30K starting capital in just 15 months.** That means the bot allegedly made 2.8x what Ross made in 2025 alone — starting with 1/20th of his capital and none of his qualitative advantages.

Even if we account for compounding (the bot's edge compounds faster from $30K than Ross's edge from $500K because percentage returns scale better at small sizes), the claim is extraordinary. The bot would need to be better than Ross at stock selection AND execution AND exits AND risk management, simultaneously, with no news reading, no tape reading, and no human judgment.

The more likely explanation: the backtest is flattering the strategy with unrealistic assumptions.

---

## What's Real vs. What's Fantasy

| Aspect | Assessment |
|--------|-----------|
| **The strategy has an edge** | LIKELY REAL — V1 at $50K notional showed +$118K over 15 months, and individual stock regressions (VERO +$18,583, ROLR +$6,444) are consistent |
| **90% win rate** | FANTASY — inflated by post-hoc scanner selection. Real win rate is likely 55-65% based on V1 data (70%) minus live execution degradation |
| **sq_target_hit is the money maker** | REAL — 2R mechanical exits on squeeze trades is a sound approach |
| **$1.35M total P&L** | FANTASY — realistic range is $50K-$150K on $30K starting capital over 15 months, after accounting for slippage, market impact, and realistic scanner coverage |
| **$100K notional on $3 stocks** | PARTIALLY REAL — achievable on liquid names (FEED, MKDW) but NOT on many small-caps in the dataset |
| **Compounding at 2.5%** | THEORETICALLY SOUND but practically limited by liquidity and market impact at higher equity levels |

---

## Recommendations for Tomorrow's Live Session

1. **Do NOT expect $1.35M in 15 months.** A realistic target for V2 paper trading is $500-$2,000/day on good days, with a 50-60% hit rate on trading days.

2. **Watch slippage closely.** Compare every live fill to the backtest's assumed fill. Track the delta. This is the single most important metric for validating the backtest.

3. **Track scanner vs. backtest coverage.** How many of tomorrow's scanner candidates match what scanner_sim would have produced? If there's still divergence, the backtest universe is unreliable.

4. **Run the megatest with FIXED $50K notional and NO compounding** to get a baseline that strips out the compounding illusion. This gives you a per-trade edge estimate that's actually comparable to real-world results.

5. **Run the megatest with $0.10 combined slippage** to see what happens when you add realistic execution costs. If the strategy dies at $0.10 slippage, the edge is too thin for live trading.

6. **The V1 megatest (+$118K, 70% WR, 183 trades) is a much more reliable baseline** than V2. Use V1 as the "this is probably what we'll actually see" number, and V2 as the theoretical ceiling with perfect execution and perfect stock selection.

---

## Bottom Line

The strategy is real. The backtest numbers are not. The V2 megatest is a best-case fantasy that compounds six separate optimistic assumptions (post-hoc scanner selection, no slippage, no market impact, no liquidity constraints, uncapped compounding, and hindsight stock ranking). Each one alone might add 20-50% to the P&L. Together, they multiply into a 10-20x overstatement.

**What the bot can realistically do with $30K:** Make $50-$150K in a year if the strategy's edge holds up in live trading, the scanner finds good candidates in real time, and execution slippage is manageable. That's still an exceptional result — it just isn't $1.35M.

The first live paper session tomorrow will teach us more in one morning than any backtest ever could.
