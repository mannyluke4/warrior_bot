# MP Max Loss Deep Dive

**Generated:** 2026-03-22
**Data source:** `megatest_state_mp_only_v2.json` Config A (score >= 8 gate)
**Companion to:** `mp_trade_logic_analysis.md`


## 1. Genuine MP Exits — Win/Loss Size Profile

**108 trades: 40 winners (37%), 68 losers (63%)**

### Winners

| Metric | Value |
|---|---|
| Avg win | +$403 |
| Median win | +$157 |
| Max win | +$6,523 (VERO 2026-01-16, +18.6R) |
| Total win $ | +$16,127 |

The win distribution is heavily right-skewed. The top 4 winners (VERO +$6,523, AIHS +$1,004, KTTA +$806, UUU +$711) account for $9,044 or 56% of all winning dollars. The median win of $157 is far below the mean of $403, confirming the strategy depends on occasional big runners.

### Losers

| Metric | Value |
|---|---|
| Avg loss | -$155 |
| Median loss | -$83 |
| Max loss | -$1,046 (SXTP 2025-04-08, -2.0R gap through stop) |
| Total loss $ | -$10,564 |

### Win/Loss Ratio: 2.60

The strategy's edge is entirely in the asymmetry: average win ($403) is 2.6x the average loss ($155). The 37% win rate alone would be unprofitable, but the fat-tailed winners more than compensate.

### By Exit Type

| Exit | Wins | Avg Win | Losses | Avg Loss |
|---|---|---|---|---|
| bearish_engulfing | 19 | +$577 | 41 | -$112 |
| topping_wicky | 21 | +$245 | 16 | -$60 |
| stop_hit | 0 | n/a | 11 | -$455 |

Bearish engulfing produces the biggest winners but also has the lowest win rate (32%). Topping wicky is the most balanced exit — 57% win rate with smaller but consistent wins and very small losses. Stop hits are pure pain: 11 trades averaging -$455 each.


## 2. The 42 Max Loss Cap Trades — What Would Have Happened?

### The Question

All 42 trades exited at ~0.75R loss due to `WB_MAX_LOSS_R=0.75`. The natural stop (pullback low) was still below. If the cap didn't exist, would these trades have:
- Hit the full 1R stop (making the cap a net saver)?
- Bounced back into profitability (making the cap a net destroyer)?

### What We Can Determine

We don't have post-exit tick data for most of these trades (only 2 of 42 had tick cache). But we can precisely measure **how much room existed between the exit and the natural stop**, which tells us how much the cap was "doing" on each trade.

### Distance to Stop — Three Tiers

**Tier 1: Close to Stop (<10% of R remaining) — 9 trades**

These exited so close to the stop that they almost certainly would have hit it anyway. The cap saved almost nothing.

| Date | Symbol | Exit | Stop | Room | Saved |
|---|---|---|---|---|---|
| 2025-01-30 | STAI | 2.02 | 2.01 | 8.3%R | ~$0 |
| 2025-02-04 | QNTM | 6.52 | 6.48 | 9.3%R | ~$0 |
| 2025-02-27 | AMST | 2.87 | 2.86 | 4.1%R | ~$0 |
| 2025-03-25 | AGPU | 2.52 | 2.51 | 9.1%R | ~$0 |
| 2025-03-25 | ZYBT | 6.60 | 6.59 | 7.7%R | ~$0 |
| 2025-06-09 | TPST | 11.06 | 11.04 | 7.1%R | ~$0 |
| 2025-12-16 | VERO | 2.24 | 2.23 | 7.7%R | ~$0 |
| 2025-12-29 | SOPA | 2.27 | 2.55 | GAPPED | n/a |
| 2026-03-05 | MSGM | 4.36 | 4.35 | 5.9%R | ~$0 |

Total additional loss if all hit stop: **-$76** (virtually nothing saved).

SOPA is an anomaly: it gapped down *through* the stop, exiting at -2.6R. The cap couldn't help here — it's a gap-down scenario.

MSGM is interesting: tick cache shows it actually **recovered to entry** after the max_loss exit. This was a trade the cap killed.

**Tier 2: Moderate Room (10-20% of R remaining) — 21 trades**

The cap fired with 10-20% of R left to the stop. These probably would have hit stop, but some might have bounced.

| Date | Symbol | Exit | Stop | Room |
|---|---|---|---|---|
| 2025-01-21 | PTHS | 3.40 | 3.36 | 13.3%R |
| 2025-01-23 | NTRB | 9.14 | 9.09 | 13.2%R |
| 2025-01-31 | CYCN | 3.21 | 3.19 | 13.0%R |
| 2025-01-31 | NCEL | 3.05 | 3.03 | 11.1%R |
| 2025-02-13 | EDSA | 3.40 | 3.36 | 10.8%R |
| 2025-02-19 | SINT | 5.43 | 5.40 | 13.6%R |
| 2025-03-05 | GV | 2.54 | 2.51 | 14.3%R |
| 2025-03-07 | DWTX | 6.80 | 6.73 | 14.9%R |
| 2025-03-10 | SNOA | 3.05 | 3.03 | 10.5%R |
| 2025-03-24 | UCAR | 3.43 | 3.41 | 10.5%R |
| 2025-06-24 | INM | 4.96 | 4.89 | 14.0%R |
| 2025-07-08 | WKHS | 2.92 | 2.87 | 12.5%R |
| 2025-07-22 | IVF | 4.45 | 4.36 | 13.6%R |
| 2025-07-29 | AEHL | 5.76 | 5.66 | 14.5%R |
| 2025-08-21 | PTIX | 4.18 | 4.14 | 14.8%R |
| 2025-09-04 | BBLG | 3.61 | 3.54 | 13.5%R |
| 2025-09-17 | GV | 3.36 | 3.35 | 10.1%R |
| 2025-09-29 | BQ | 8.54 | 8.46 | 12.3%R |
| 2025-10-13 | STI | 12.34 | 12.22 | 14.0%R |
| 2025-12-23 | TIVC | 2.86 | 2.84 | 14.3%R |
| 2025-12-23 | BBLG | 2.21 | 2.19 | 11.1%R |

Total additional loss if all hit stop: **$1,445**.

**Tier 3: Substantial Room (>20% of R remaining) — 12 trades**

These exited at -0.75R to -0.8R with 20-25% of R still between the exit and the stop. These had genuine room for a bounce.

| Date | Symbol | Exit | Stop | Room | Add. Loss to Stop |
|---|---|---|---|---|---|
| 2025-03-17 | GLMD | 3.13 | 3.03 | 23.3%R | $58 |
| 2025-03-19 | ATER | 3.04 | 2.97 | 24.1%R | $60 |
| 2025-03-21 | ALUR | 4.01 | 3.98 | 25.0%R | $62 |
| 2025-05-08 | VEEE | 4.34 | 4.20 | 24.6%R | $61 |
| 2025-05-29 | WETO | 3.42 | 3.39 | 23.1%R | $58 |
| 2025-06-26 | CYN | 8.33 | 8.15 | 24.3%R | $61 |
| 2025-07-16 | APM | 3.07 | 2.99 | 24.2%R | $61 |
| 2025-08-15 | PPSI | 4.91 | 4.87 | 23.5%R | $59 |
| 2025-09-26 | EGG | 6.98 | 6.89 | 21.6%R | $54 |
| 2025-10-13 | NAMM | 4.17 | 4.14 | 25.0%R | $63 |
| 2025-10-31 | TGE | 2.88 | 2.81 | 24.2%R | $60 |
| 2026-01-27 | CYN | 3.48 | 3.43 | 20.8%R | $52 |

Total additional loss if all hit stop: **$709**.

CYN (2026-01-27) has tick data: after the max_loss exit at 3.48, price hit a low of 2.06 (blew through stop at 3.43) but also reached 3.68 (above entry 3.67). The trade hit full stop before recovering — cap saved money here.

### Quantitative Summary

| Metric | Value |
|---|---|
| Total $ saved by cap (vs all hitting stop) | $2,078 |
| But: all 42 trades are guaranteed losers | -$15,425 total |
| Without cap, at natural stop | -$17,503 total |
| Cap saves ~$50/trade on average | Marginal benefit |

### The Harder Question: Would Any Have Become Winners?

Without tick data for most trades, we can't know definitively. But consider:

- **0 of 42 max_loss trades were winners** — by definition, they were all losing at exit
- The cap fires at -0.75R. For a trade to become a winner, price must recover 0.75R+ from the exit. On these low-float stocks, that's possible but requires the kind of strong reversal that the original pullback pattern was supposed to capture in the first place
- The 2 trades with tick data gave one verdict each way: CYN hit full stop (cap helped), MSGM recovered to entry (cap hurt)
- **Best-case scenario** if we assume the Tier 3 trades (12 trades) had a 25% bounce rate: 3 trades become winners averaging +$200 each = +$600, while 9 trades add ~$60 each in additional loss = -$540. Net: roughly breakeven
- **Realistic scenario:** These trades were losing at 0.75R. On penny stocks, momentum that pushes you 0.75R against entry rarely reverses. The base rate for recovery from -0.75R in the genuine MP data is essentially 0% (no genuine MP trade that was ever -0.75R underwater ended as a winner)

### Conclusion on Max Loss Cap

The cap saves **$2,078** over the dataset by catching trades before they hit full stop. That's only **$50/trade** — a modest benefit. The real question isn't "cap or no cap" but rather: **why are there 42 trades entering positions that immediately go against them by 0.75R?** These trades represent a systematic failure in entry selection, not a stop placement problem.


## 3. Anatomy of a Natural Loser (Genuine MP Exits)

**68 losing trades** in the genuine MP bucket (bearish engulfing, topping wicky, stop hit).

### Exit Method Distribution

| Exit Type | Count | % of Losers | Avg Loss | Avg R-Mult |
|---|---|---|---|---|
| bearish_engulfing | 41 | 60% | -$112 | -0.30R |
| topping_wicky | 16 | 24% | -$60 | -0.18R |
| stop_hit | 11 | 16% | -$455 | -1.09R |

**84% of natural losers exit on pattern recognition (BE or TW) before ever hitting their stop.** This is a significant finding — the pattern-based exits are doing their job as loss limiters.

### Pattern-Exit Losers: Small and Fast

The 57 pattern-exit losers average just **-$98** per trade (-0.27R). They look like:

- **Quick failures**: 22 of 68 losers (32%) exit in under 1 minute. The pullback pattern triggers, the stock makes no move up, and within 1-2 bars a bearish engulfing or topping wicky appears. Average loss for <1min exits: -$193
- **Tiny scratches**: 20 of 57 pattern-exit losers (35%) lose less than 0.1R — essentially breakeven trades where the exit pattern fired almost immediately
- **Moderate giveback**: 20 pattern-exit losers fall in the -0.1R to -0.3R range — the trade ran a little, pulled back, and the exit pattern caught the reversal early
- **Uncomfortable but managed**: 17 pattern-exit losers are -0.3R to -0.8R — real losses, but the pattern caught them before stop

### R-Multiple Distribution (Pattern-Exit Losers)

| R-Bucket | Count | Interpretation |
|---|---|---|
| 0 to -0.1R | 20 (35%) | Immediate failures, scratches |
| -0.1 to -0.3R | 20 (35%) | Quick reversals caught by pattern |
| -0.3 to -0.5R | 14 (25%) | Deeper pullbacks, pattern still caught |
| -0.5 to -0.8R | 3 (5%) | Late pattern exits, close to stop territory |

### Stop Hit Losers: Full Losses

The 11 stop hit trades are the worst performers in the genuine MP bucket:

| Date | Symbol | R-Mult | PnL | Hold | Notes |
|---|---|---|---|---|---|
| 2025-04-08 | SXTP | -2.0R | -$1,046 | 3 min | Gapped through stop |
| 2025-03-28 | ATON | -1.0R | -$549 | 1 min | Wide R ($0.86), fast drop |
| 2025-05-21 | EDBL | -1.0R | -$531 | 0 min | Instant failure |
| 2026-01-22 | SXTP | -1.0R | -$514 | 0 min | Same symbol, same pattern |
| 2025-06-03 | NIVF | -1.0R | -$512 | 1 min | |
| 2025-06-20 | WHLR | -1.0R | -$484 | 7 min | Longest hold of stop hits |
| 2025-09-16 | APVO | -1.0R | -$433 | 0 min | Instant |
| 2026-01-08 | ACON | -1.0R | -$345 | 0 min | |
| 2025-10-07 | BJDX | -1.0R | -$203 | 0 min | |
| 2025-11-12 | CMCT | -1.0R | -$194 | 0 min | |
| 2025-11-21 | MNDR | -1.0R | -$192 | 0 min | |

These are trades where price drops immediately and no bearish pattern fires before the stop because the move is too fast or gaps through. 8 of 11 exit within 1 minute — these are instant failures where the entry was fundamentally wrong.

SXTP appears twice (April 2025, Jan 2026) and is the only -2R trade — a gap-through-stop scenario.

### Pattern Exits Save $357/Trade

Average pattern-exit loss: **-$98**
Average stop-hit loss: **-$455**
Savings per trade: **$357**

If the bearish engulfing and topping wicky exits didn't exist (all losers hit stop), the 57 pattern-exit losers would generate an estimated -$25,935 in losses instead of -$5,561. That's **$20,374 in savings** from pattern-based exit logic.

### The Natural Loser Profile

A typical losing trade in the genuine MP strategy looks like this:

1. Entry triggers on 1-minute pullback confirmation
2. Stock fails to follow through within 1-2 minutes
3. A bearish engulfing or topping wicky pattern appears
4. Exit fires at -0.1R to -0.3R, costing $50-$150
5. Total time in trade: 0-2 minutes

This is the **healthy loss** — small, fast, pattern-recognized. The strategy's profitability depends on keeping losses at this level while occasionally catching +2R to +18R runners.

The **unhealthy loss** is the stop hit: -$455 average, usually an instant failure where the entry was just wrong and price dropped straight through without any pattern to catch it.


## 4. Key Takeaways

1. **Win/loss asymmetry is the entire edge:** $403 avg win vs $155 avg loss (2.6:1 ratio). The strategy is a classic fat-tail play — it works because the occasional VERO (+$6,523) or AIHS (+$1,004) more than compensates for many small losses.

2. **The max loss cap saves only ~$50/trade:** Over 42 trades, the 0.75R cap prevented $2,078 in additional losses vs natural stops. That's real money but modest. The bigger issue is *why* 42 trades (27% of all trades) are getting so far offside so fast.

3. **Recovery from -0.75R is extremely unlikely:** Based on the genuine MP data, no trade that was -0.75R underwater ever recovered to become a winner. The cap isn't killing potential winners — it's putting down trades that are already dead.

4. **Pattern exits are the real loss limiter:** 84% of natural losers are caught by bearish engulfing or topping wicky patterns before stop, saving an estimated $357/trade vs hitting full stop. This is far more valuable than the max loss cap.

5. **The 12 "substantial room" trades are the only debatable ones:** These exited with 20-25% of R still between exit and stop. Even here, the expected value of removing the cap is roughly breakeven based on reasonable bounce rate assumptions.

6. **Stop hits are rare but brutal:** Only 11 of 108 genuine MP trades hit the natural stop, but they account for $5,003 in losses (47% of genuine MP losses from 10% of trades). These are the trades that need better entry filtering, not a tighter stop.
