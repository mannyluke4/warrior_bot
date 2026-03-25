# PDT Protection Simulation: Squeeze-Only, $10K Start
## Generated 2026-03-19

Simulates a small account ($10K) trading the squeeze strategy under Pattern Day Trader
restrictions. Under $25K, the account is limited to 1 trade/day from the top-ranked
scanner candidate, Monday through Thursday only (no Friday trades). Once the account
crosses $25K, full multi-trade behavior unlocks on all weekdays.

Uses the same trade data from the Sep 2025–Mar 2026 continuous backtest, filtered to
squeeze trades only, with position sizes rescaled to the $10K starting balance and
2.5% risk per trade.

---

## Headline Numbers

| Metric | Value |
|--------|-------|
| Starting Balance | $10,000 |
| Ending Balance | $26,640 |
| Total P&L | +$16,640 |
| Total Return | +166.4% |
| Peak Equity | $26,640 |
| Max Drawdown | $201 (0.8%) |
| Total Trades | 40 |
| Win Rate | 29/40 (72%) |
| Avg P&L/Trade | +$416 |

---

## PDT Threshold Crossing

| Metric | Value |
|--------|-------|
| Unlock Date | **2026-03-18** |
| Unlock Equity | $26,420 |
| Calendar Days to Unlock | 197 (Sep 2 → Mar 18) |
| Trading Days to Unlock | 138 |
| Trades Taken Before Unlock | 39 |
| Trade That Crossed $25K | ARTL +$3,915 (+13.9R) |

The account spent nearly the entire 7-month period in PDT mode. ARTL's monster +13.9R
squeeze on Mar 18, 2026 was the trade that finally pushed the account from $22,505 over
the $25K threshold to $26,420. The very next day (Mar 19), SER was the first trade taken
in full/unlocked mode.

---

## Pre-PDT vs Post-PDT Comparison

| Metric | Pre-PDT (<$25K) | Post-PDT (>=$25K) |
|--------|-----------------|-------------------|
| Trades | 39 | 1 |
| Win Rate | 28/39 (72%) | 1/1 (100%) |
| Total P&L | +$16,420 | +$220 |
| Avg P&L/Trade | +$421 | +$220 |

Note: The post-PDT sample is only 1 trade (the simulation ends Mar 19), so no meaningful
comparison can be drawn yet. The real takeaway is that the squeeze strategy performed
extremely well even under severe PDT constraints.

---

## Monthly Breakdown

| Month | Mode | Start Equity | End Equity | P&L | Return | Trades | Win Rate |
|-------|------|-------------|-----------|-----|--------|--------|----------|
| 2025-09 | PDT | $10,000 | $13,548 | +$3,548 | +35.5% | 10 | 70% |
| 2025-10 | PDT | $13,548 | $16,866 | +$3,318 | +24.5% | 10 | 60% |
| 2025-11 | PDT | $16,866 | $17,275 | +$409 | +2.4% | 2 | 100% |
| 2025-12 | PDT | $17,275 | $18,392 | +$1,117 | +6.5% | 6 | 67% |
| 2026-01 | PDT | $18,392 | $22,426 | +$4,034 | +21.9% | 8 | 88% |
| 2026-02 | PDT | $22,426 | $22,505 | +$79 | +0.4% | 2 | 50% |
| 2026-03 | MIX | $22,505 | $26,640 | +$4,135 | +18.4% | 2 | 100% |
| **TOTAL** | | **$10,000** | **$26,640** | **+$16,640** | **+166.4%** | **40** | **72%** |

---

## Complete Trade Log

| # | Date | Ticker | Time | Mode | Entry | Exit | R-Mult | P&L | Equity |
|---|------|--------|------|------|-------|------|--------|-----|--------|
| 1 | 2025-09-02 | HWH | 10:04 | PDT | $3.42 | $3.82 | +3.8R | +$475 | $10,475 |
| 2 | 2025-09-03 | AIHS | 07:48 | PDT | $4.04 | $4.10 | +0.4R | +$56 | $10,531 |
| 3 | 2025-09-04 | BBLG | 07:22 | PDT | $3.04 | $3.02 | -0.1R | -$19 | $10,512 |
| 4 | 2025-09-09 | BON | 08:38 | PDT | $3.04 | $2.93 | -0.8R | -$29 | $10,483 |
| 5 | 2025-09-10 | RBNE | 09:17 | PDT | $3.04 | $3.35 | +2.1R | +$278 | $10,761 |
| 6 | 2025-09-11 | GRI | 08:54 | PDT | $2.04 | $2.37 | +3.4R | +$459 | $11,220 |
| 7 | 2025-09-15 | MBAI | 07:34 | PDT | $3.04 | $3.13 | +0.6R | +$90 | $11,310 |
| 8 | 2025-09-16 | APVO | 08:31 | PDT | $2.04 | $2.44 | +3.3R | +$467 | $11,777 |
| 9 | 2025-09-22 | AVX | 07:01 | PDT | $5.04 | $6.51 | +12.5R | +$1,844 | $13,621 |
| 10 | 2025-09-24 | JZXN | 07:16 | PDT | $2.04 | $1.98 | -0.4R | -$73 | $13,548 |
| 11 | 2025-10-07 | CISS | 09:47 | PDT | $4.54 | $4.46 | -0.6R | -$95 | $13,453 |
| 12 | 2025-10-13 | NAMM | 07:34 | PDT | $4.04 | $3.96 | -0.6R | -$17 | $13,436 |
| 13 | 2025-10-14 | JDZG | 07:07 | PDT | $3.04 | $3.33 | +1.8R | +$300 | $13,736 |
| 14 | 2025-10-15 | COOT | 07:08 | PDT | $4.04 | $3.94 | -0.7R | -$21 | $13,715 |
| 15 | 2025-10-20 | **GNLN** | 08:31 | PDT | $4.04 | $6.39 | **+16.7R** | **+$2,855** | $16,570 |
| 16 | 2025-10-21 | BOF | 07:07 | PDT | $3.04 | $2.93 | -0.8R | -$23 | $16,547 |
| 17 | 2025-10-23 | IMCC | 09:19 | PDT | $3.04 | $3.09 | +0.4R | +$74 | $16,621 |
| 18 | 2025-10-27 | KITT | 09:08 | PDT | $2.04 | $2.13 | +0.6R | +$19 | $16,640 |
| 19 | 2025-10-28 | VSEE | 08:42 | PDT | $1.04 | $1.23 | +2.5R | +$74 | $16,714 |
| 20 | 2025-10-29 | ERNA | 09:17 | PDT | $2.04 | $2.12 | +0.7R | +$152 | $16,866 |
| 21 | 2025-11-06 | GMEX | 08:52 | PDT | $3.04 | $3.35 | +1.7R | +$348 | $17,214 |
| 22 | 2025-11-10 | VERO | 07:34 | PDT | $3.04 | $3.08 | +0.3R | +$265 | $17,275 |
| 23 | 2025-12-09 | OCG | 10:25 | PDT | $3.75 | $3.75 | +0.0R | $0 | $17,275 |
| 24 | 2025-12-16 | ASNS | 08:10 | PDT | $2.04 | $2.04 | +0.0R | $0 | $17,275 |
| 25 | 2025-12-18 | LONA | 09:40 | PDT | $7.91 | $8.05 | +0.4R | +$85 | $17,360 |
| 26 | 2025-12-24 | ELOG | 08:35 | PDT | $2.04 | $2.13 | +0.6R | +$139 | $17,499 |
| 27 | 2025-12-29 | BNAI | 09:31 | PDT | $1.95 | $2.24 | +2.1R | +$464 | $17,963 |
| 28 | 2025-12-30 | AEHL | 09:38 | PDT | $1.96 | $2.24 | +1.9R | +$429 | $18,392 |
| 29 | 2026-01-08 | ACON | 07:01 | PDT | $8.04 | $8.32 | +1.6R | +$357 | $18,749 |
| 30 | 2026-01-12 | BDSX | 09:49 | PDT | $8.30 | $8.18 | -0.9R | -$201 | $18,548 |
| 31 | 2026-01-13 | SPRC | 07:05 | PDT | $2.04 | $2.06 | +0.1R | +$33 | $18,581 |
| 32 | 2026-01-14 | **ROLR** | 08:19 | PDT | $4.04 | $5.28 | **+8.5R** | **+$1,965** | $20,546 |
| 33 | 2026-01-15 | CJMB | 08:46 | PDT | $2.04 | $2.11 | +0.5R | +$128 | $20,674 |
| 34 | 2026-01-20 | POLA | 10:03 | PDT | $2.90 | $2.94 | +0.3R | +$74 | $20,748 |
| 35 | 2026-01-21 | SLGB | 07:17 | PDT | $3.04 | $4.00 | +6.4R | +$1,653 | $22,401 |
| 36 | 2026-01-26 | BATL | 07:01 | PDT | $5.04 | $5.11 | +0.5R | +$25 | $22,426 |
| 37 | 2026-02-04 | BOXL | 07:16 | PDT | $2.04 | $1.98 | -0.4R | -$120 | $22,306 |
| 38 | 2026-02-09 | UOKA | 09:36 | PDT | $2.78 | $2.88 | +0.7R | +$199 | $22,505 |
| 39 | 2026-03-18 | **ARTL** | 07:42 | PDT | $5.04 | $6.97 | **+13.9R** | **+$3,915** | **$26,420** ★ PDT UNLOCK |
| 40 | 2026-03-19 | SER | 09:31 | FULL | $2.22 | $2.30 | +0.7R | +$220 | $26,640 |

---

## Skipped Friday Opportunities

Under PDT rules, Fridays are off-limits. Here's what was left on the table (at original sizing):

| Date | Ticker | Orig P&L | Outcome |
|------|--------|----------|---------|
| 2025-09-05 | HOUR | -$245, +$1,124 | Net positive |
| 2025-09-12 | COCP | +$326, +$317 | Winner |
| 2025-09-12 | UOKA | -$413 | Loser |
| 2025-09-19 | AGMH | +$1,093 | Winner |
| 2025-10-31 | FMFC | +$866 | Winner |
| 2026-02-20 | EVTV | +$59 | Breakeven |
| 2026-03-13 | BIAF | +$136 | Small winner |

Total missed at original sizing: ~+$3,263. At the smaller PDT account size, this would
have been roughly +$1,000–$1,500 — meaningful but not account-changing. The PDT Friday
restriction costs about 5-10% of total returns.

---

## Key Observations

1. **$10K → $26.6K in 7 months with only 40 trades.** The squeeze strategy is viable
   even under severe PDT constraints. The 72% win rate and +$416 avg win are strong.

2. **Max drawdown is absurdly low: $201 (0.8%).** The 1-trade/day constraint naturally
   limits exposure. The worst day was BDSX on Jan 12, 2026 (-$201). The account never
   experienced a meaningful drawdown at any point.

3. **PDT unlock took 197 calendar days.** The $10K → $25K journey required patience.
   The account crossed $20K in mid-January but then plateaued in February before ARTL's
   monster trade pushed it over the line.

4. **Three monster trades drove most of the P&L:** GNLN +$2,855 (Oct 20), ROLR +$1,965
   (Jan 14), and ARTL +$3,915 (Mar 18). These three trades alone account for $8,735 —
   over half the total P&L.

5. **The 1-trade/day constraint forced good selection.** By only taking the first squeeze
   signal from the top-ranked candidate, the simulation avoided many of the marginal
   re-entry trades that sometimes lose money. The 72% win rate compares favorably to the
   67% squeeze win rate in the unconstrained OOS backtest.

6. **Nov-Dec was thin but positive.** Only 8 trades across two months, but still netted
   +$1,526. The bot sat out quiet days rather than forcing mediocre setups.

7. **Friday cost is manageable.** ~$1,500 left on the table from skipped Fridays over
   the entire 7-month period. Worth it for PDT compliance.

---

## Methodology

- All squeeze trades from the Sep 2025–Mar 2026 combined dataset
- Under $25K: 1 trade/day, top candidate by scanner rank_score, Mon–Thu only
- Over $25K: all squeeze trades from all candidates, all weekdays
- Position sizing: 2.5% of equity per trade, $50K notional cap
- P&L rescaled from original $30K-start backtest: `new_pnl = orig_pnl × (pdt_equity / orig_equity_at_date)`
- "Top candidate" = highest rank_score from scanner selection log (70% PM volume + 20% gap + 10% float)
- When top candidate had multiple squeeze signals same day, only the first (earliest) was taken
