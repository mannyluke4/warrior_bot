# Week of March 2–6, 2026 — Scanner Simulation Report

## Weekly Summary
- Total candidates scanned (across all 5 days): 153
- Passed profile filter (A + B): 39
- Bot took trades on: 6 stocks (9 total trades)
- Total P&L: **+$690**
- Win rate: 22.2% (2W / 7L)

## Daily Breakdown

| Date | Day | Candidates | Filtered A | Filtered B | Trades | Wins | Losses | P&L |
|------|-----|-----------|------------|------------|--------|------|--------|-----|
| 03-02 | Mon | 22 | 4 | 2 | 1 | 0 | 1 | -$2,812 |
| 03-03 | Tue | 37 | 6 | 2 | 2 | 1 | 1 | -$1,348 |
| 03-04 | Wed | 21 | 4 | 2 | 5 | 1 | 4 | +$5,961 |
| 03-05 | Thu | 39 | 9 | 2 | 1 | 0 | 1 | -$1,111 |
| 03-06 | Fri | 34 | 6 | 2 | 0 | 0 | 0 | $0 |
| **Total** | | **153** | **29** | **10** | **9** | **2** | **7** | **+$690** |

## Per-Stock Detail (Trades Only)

| Date | Ticker | Profile | Gap% | Entry | Exit | P&L | Exit Reason |
|------|--------|---------|------|-------|------|-----|-------------|
| 03-02 | WVVIP | A | +25.8% | $8.45 | $3.56 | -$2,812 | max_loss_hit (-2.8R) |
| 03-03 | RBNE | A | +32.3% | $3.68 | $3.74 | +$375 | topping_wicky_exit (+0.4R) |
| 03-03 | CRMX | A | +11.2% | $8.18 | $7.91 | -$1,723 | stop_hit (-1.7R) |
| 03-04 | CANF #1 | A | +16.9% | $7.32 | $6.83 | -$352 | bearish_engulfing_exit (-0.4R) |
| 03-04 | CANF #2 | A | +16.9% | $7.39 | $7.07 | -$432 | bearish_engulfing_exit (-0.4R) |
| 03-04 | CANF #3 | A | +16.9% | $7.72 | $9.57 | +$7,115 | topping_wicky_exit (+7.1R) |
| 03-04 | CANF #4 | A | +16.9% | $10.03 | $9.89 | -$215 | bearish_engulfing_exit (-0.2R) |
| 03-04 | EDSA | A | +13.1% | $5.26 | $5.18 | -$154 | bearish_engulfing_exit (-0.2R) |
| 03-05 | BTOG | A | +27.8% | $3.41 | $3.31 | -$1,111 | stop_hit (-1.1R) |

## Per-Stock Detail (No Trade — Why Not)

| Date | Ticker | Profile | Gap% | Reason No Trade |
|------|--------|---------|------|-----------------|
| 03-02 | RBNE | A | +29.1% | No setup armed (0 arms, 0 signals) |
| 03-02 | MARPS | A | +13.7% | No setup armed (0 arms, 0 signals) |
| 03-02 | TOPS | A | +10.9% | VWAP blocked arm (1 blocked — price below VWAP at trigger) |
| 03-02 | SND | B | +24.1% | No setup armed (0 arms, 0 signals) — low tick volume (995 trades) |
| 03-02 | INDO | B | +23.6% | Classifier: avoid (VWAP dist 5.1% < 7%, range 3.3% < 10%) |
| 03-03 | TOPS | A | +14.2% | No setup armed (0 arms, 0 signals) |
| 03-03 | EHLD | A | +11.9% | No setup armed — very thin (200 ticks, 20 sim bars) |
| 03-03 | MRAL | A | +11.5% | No setup armed (0 arms, 0 signals) |
| 03-03 | MTR | A | +10.9% | Armed 1 but no signal triggered (409 ticks) |
| 03-03 | DBGI | B | +19.5% | Classifier: avoid (VWAP dist 1.7% < 7%, range 4.2% < 10%) |
| 03-03 | SENS | B | +17.1% | Classifier: avoid (VWAP dist 1.6% < 7%, range 5.2% < 10%) |
| 03-04 | PCLA | A | +20.7% | Armed 1, signaled 1, but no entry (163 ticks — ultra-thin) |
| 03-04 | SOUX | A | +10.3% | No setup armed (0 arms, 0 signals) |
| 03-04 | HRZN | B | +18.0% | No setup armed (0 arms, 0 signals) |
| 03-04 | ANNA | B | +14.0% | No setup armed — thin (132 ticks) |
| 03-05 | EDSA | A | +19.4% | Classifier: avoid (VWAP dist 4.5% < 7%, range 1.9% < 10%) |
| 03-05 | CANF | A | +12.2% | Classifier: avoid (VWAP dist 3.5% < 7%, range 1.2% < 10%) |
| 03-05 | MRAL | A | +12.5% | No setup armed (0 arms, 0 signals) |
| 03-05 | RIOX | A | +12.0% | Classifier: avoid (VWAP dist 1.9% < 7%, range 4.7% < 10%) |
| 03-05 | SLNG | A | +11.6% | Classifier: avoid (VWAP dist 5.3% < 7%, range 5.2% < 10%) |
| 03-05 | MST | A | +11.1% | Classifier: avoid (VWAP dist 2.0% < 7%, range 1.0% < 10%) |
| 03-05 | MPL | A | +11.5% | No setup armed (0 arms, 0 signals) |
| 03-05 | HOOX | A | +10.0% | No setup armed (0 arms, 0 signals) |
| 03-05 | SHMD | B | +16.0% | No setup armed (0 arms, 0 signals) |
| 03-05 | DDC | B | +14.1% | No setup armed — ultra-thin (37 ticks) |

## EDSA Note (March 4)
EDSA appears on March 4 as a Profile A candidate. The bot took 1 trade (-$154). Note: the live EDSA trade on March 3-4 was triggered by a reconcile bug, not the scanner. The classifier correctly flagged EDSA as "avoid" on March 5 (second appearance), preventing further losses.

## Observations

### Hot vs Cold Days
- **Wednesday March 4 was the only profitable day (+$5,961)**, driven entirely by CANF's cascading run ($5.00→$10+). One +7.1R winner offset three small losses.
- **Monday March 2 was the worst day (-$2,812)** — a single WVVIP trade hit max loss at -2.8R (price collapsed from $8.45 to $3.56).
- **Thursday March 5 and Tuesday March 3** were modestly negative. Friday March 6 had no trades.

### Profile A vs Profile B
- **Profile A generated all 9 trades.** Profile B produced zero trades across the entire week.
- Profile B candidates were consistently blocked: classifier "avoid" gates (INDO, DBGI, SENS), no setup armed (SND, HRZN, ANNA, SHMD, DDC), or insufficient ticks.
- This suggests the Profile B filter criteria may need adjustment, or these mid-float stocks simply don't produce micro-pullback patterns the bot recognizes.

### Classifier Accuracy
- The classifier correctly blocked 8 stocks as "avoid" this week (INDO, DBGI, SENS, EDSA×2, CANF×1, RIOX, SLNG, MST).
- On March 5, the classifier blocked CANF and EDSA — both of which had been profitable/traded the day before (CANF +$6,115 on 03-04). This illustrates how day-2 price action often lacks the momentum of the initial gap day.
- No false negatives observed (no clearly missed winners among blocked stocks).

### Key Patterns
1. **Cascading re-entry is the edge**: CANF's +$7,115 winner came on trade #3 after two small BE losses. Signal mode's cascading exits enabled the big catch.
2. **Thin tickers are dangerous**: WVVIP had the week's worst trade (-$2,812). Low-volume gap-ups can collapse without liquidity.
3. **Most filtered stocks never arm**: 15 of 25 no-trade stocks had 0 arms and 0 signals — the micro-pullback pattern simply didn't form.
4. **VWAP gate working correctly**: TOPS on 03-02 had 1 arm blocked by VWAP — price was below VWAP at trigger time.

### Comparison to Previous Backtest (Jan 13 – Mar 4, 5 dates)
| Metric | Previous 5 Dates | This Week (4 days + Fri) |
|--------|-----------------|--------------------------|
| Candidates | 213 | 153 |
| Trades | 51 | 9 |
| Win Rate | 17.6% | 22.2% |
| Net P&L | -$13,736 | +$690 |
| Best Day | Mar 4 +$4,096 | Mar 4 +$5,961 |

The week was marginally profitable (+$690), a significant improvement over the previous backtest's -$13,736. The difference: fewer trades (9 vs 51) means fewer losses, while the cascading edge still captures big runners (CANF). The classifier is aggressively filtering, which reduces both exposure and risk.
