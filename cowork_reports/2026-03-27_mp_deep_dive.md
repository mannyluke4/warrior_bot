# MP (Micro-Pullback) Deep Dive — Full Data for Cowork Review
## Date: 2026-03-27
## Purpose: Determine if MP can be fixed or should be scrapped

---

## The Problem

MP is not just underperforming squeeze — it's fundamentally broken. Over 15 months of IBKR data:

| Metric | MP-Only | SQ-Only |
|--------|---------|---------|
| P&L | **-$8,066 (-26.9%)** | **+$1,348,605 (+4,495%)** |
| Trades | 138 | 321 |
| Win Rate | **24%** | **90%** |
| Avg Winner | +$798 | +$4,756 |
| Avg Loser | -$341 | -$221 |
| Best Month | Jun 2025 (+$6,041) | Every month positive |
| Worst Month | Dec 2025 (-$4,262) | N/A |

MP lost money in **11 of 15 months**. It has a 24% win rate. When combined with SQ, it drags performance down (Mar 26: SQ alone +$1,671 → SQ+MP +$1,104).

---

## Exit Reason Breakdown

| Exit Reason | Count | Wins | P&L | Avg | Notes |
|-------------|-------|------|-----|-----|-------|
| bearish_engulfing_exit_full | 68 | 20 | +$14,215 | +$209 | Only profitable exit — but 48 losers |
| topping_wicky_exit_full | 20 | 12 | +$2,308 | +$115 | Marginally positive |
| max_loss_hit | 34 | 0 | -$19,122 | -$562 | **0% win rate, -$19K** — catastrophic |
| bail_timer | 8 | 0 | -$2,750 | -$344 | 0% win rate — dead trades |
| stop_hit | 6 | 0 | -$2,790 | -$465 | 0% win rate |
| trail_stop | 2 | 1 | +$73 | +$36 | Too rare to matter |

**Key insight:** `max_loss_hit` has 34 trades, ALL losers, totaling -$19,122. This single exit reason accounts for 237% of total losses. These are entries where price immediately moves against, hits the max loss cap, and gets stopped out. The entry timing or level selection is wrong.

---

## Monthly Breakdown

| Month | Trades | W/L | WR | P&L |
|-------|--------|-----|-----|-----|
| 2025-01 | 6 | 1W/5L | 16% | -$2,489 |
| 2025-02 | 6 | 1W/5L | 16% | -$703 |
| 2025-03 | 3 | 0W/3L | 0% | -$1,722 |
| 2025-04 | 4 | 1W/3L | 25% | -$91 |
| 2025-05 | 8 | 4W/4L | 50% | -$747 |
| 2025-06 | 9 | 2W/7L | 22% | +$6,041 |
| 2025-07 | 6 | 3W/3L | 50% | -$274 |
| 2025-08 | 8 | 0W/8L | 0% | -$3,375 |
| 2025-09 | 20 | 6W/14L | 30% | +$150 |
| 2025-10 | 24 | 6W/18L | 25% | -$2,050 |
| 2025-11 | 4 | 0W/4L | 0% | -$681 |
| 2025-12 | 17 | 3W/14L | 17% | -$4,262 |
| 2026-01 | 13 | 5W/8L | 38% | +$3,248 |
| 2026-02 | 5 | 0W/5L | 0% | -$423 |
| 2026-03 | 5 | 1W/4L | 20% | -$688 |

**Only 2 profitable months** (Jun 2025, Jan 2026), both carried by single big winners (AIFF +$5,602 and ROLR +$3,293).

---

## Top 10 Winners

| Date | Symbol | P&L | Exit |
|------|--------|-----|------|
| 2025-06-20 | AIFF | +$5,602 | bearish_engulfing |
| 2025-06-18 | LSE | +$4,602 | bearish_engulfing |
| 2026-01-14 | ROLR | +$3,293 | bearish_engulfing |
| 2025-09-04 | CIGL | +$1,987 | bearish_engulfing |
| 2025-09-03 | AIHS | +$1,558 | bearish_engulfing |
| 2025-09-04 | BRIA | +$1,266 | bearish_engulfing |
| 2025-09-02 | UUU | +$1,138 | bearish_engulfing |
| 2026-01-12 | OM | +$692 | bearish_engulfing |
| 2026-01-15 | AGPU | +$652 | topping_wicky |
| 2026-01-15 | BNKK | +$604 | topping_wicky |

All top winners exit via bearish_engulfing — the one exit that works. These are stocks that ran hard and MP caught the move, letting it ride until a reversal candle.

---

## Top 10 Losers

| Date | Symbol | P&L | Exit |
|------|--------|-----|------|
| 2025-06-24 | INM | -$2,639 | max_loss_hit |
| 2025-05-13 | ELSE | -$908 | bail_timer |
| 2025-09-29 | SCOR | -$872 | max_loss_hit |
| 2025-01-13 | PHIO | -$746 | max_loss_hit |
| 2025-09-26 | EGG | -$720 | max_loss_hit |
| 2026-03-24 | LICN | -$664 | bail_timer |
| 2025-08-14 | SNOA | -$658 | max_loss_hit |
| 2025-06-23 | WFF | -$646 | max_loss_hit |
| 2025-07-01 | CLRO | -$645 | bail_timer |
| 2025-03-28 | ATON | -$642 | stop_hit |

Losers are dominated by max_loss_hit — immediate adverse moves after entry.

---

## Recent Data: Mar 26-27 (SQ+MP vs SQ-only)

### Mar 26 — EEIQ
| Mode | Trades | P&L |
|------|--------|-----|
| SQ-only | 1 (sq_target_hit +$1,671) | **+$1,671** |
| SQ+MP | 2 (MP max_loss -$566, SQ target +$1,671) | **+$1,104** |

MP entered EEIQ at 09:55 (5 minutes before the squeeze triggered at 10:00) and immediately ate a -$566 max_loss. Same stock, same setup — MP jumped in prematurely.

### Mar 27 — ONCO + ARTL
| Mode | Trades | P&L |
|------|--------|-----|
| SQ-only | 0 (ONCO armed, no trigger) | **$0** |
| SQ+MP | 5 (ONCO -$83, ARTL 4 trades -$2,416) | **-$2,499** |

MP turned a quiet day into a -$2,499 disaster.

---

## Diagnosis: What's Wrong

### 1. Entry Timing Is Too Early
MP uses impulse → pullback → ARM → trigger on pullback recovery. But on squeeze-type stocks, the real move hasn't started yet. MP enters during the early chop, gets stopped out, then the squeeze fires 5 minutes later. (See EEIQ Mar 26: MP at 09:55, SQ at 10:00.)

### 2. Stops Are Too Tight for the Volatility
34 max_loss_hit trades at 0% win rate means the stop placement doesn't match the stock's natural range. These stocks whipsaw through MP's stop level as part of normal pre-breakout volatility.

### 3. No Quality Filter on Entry
MP enters on any stock that shows an impulse + pullback pattern. It doesn't check: Is this stock about to break a key level? Is there institutional buying? Is the pullback constructive or just noise?

### 4. The Winners Are Actually Squeeze Trades
The big MP winners (AIFF +$5,602, LSE +$4,602, ROLR +$3,293) are stocks that squeezed. MP happened to be in the right place at the right time, but the squeeze detector would have caught them too — with better timing and tighter risk.

---

## Questions for Cowork

1. **Is MP worth fixing?** SQ alone produces +4,495% over 15 months. MP adds noise and losses.
2. **If fixing:** Can we restrict MP to only fire AFTER a squeeze attempt fails? (Use it as a secondary entry, not a primary one)
3. **Entry quality:** Should MP require a key level break (like SQ does) instead of just impulse+pullback?
4. **Stop placement:** Should MP use wider stops or dynamic stops based on ATR/range?
5. **Time filter:** Should MP be blocked before 9:30 ET? Most big losses are in pre-market chop.

---

## Complete Trade Log

138 trades attached below for analysis.

| Date | Symbol | P&L | Exit Reason |
|------|--------|-----|-------------|
| 2025-01-06 | GDTC | +$108 | bearish_engulfing |
| 2025-01-13 | PHIO | -$746 | max_loss_hit |
| 2025-01-21 | DWTX | -$633 | max_loss_hit |
| 2025-01-23 | VNCE | -$48 | topping_wicky |
| 2025-01-23 | HKPD | -$624 | max_loss_hit |
| 2025-01-27 | FMST | -$546 | max_loss_hit |
| 2025-02-03 | SOPA | -$183 | bearish_engulfing |
| 2025-02-04 | QNTM | -$310 | max_loss_hit |
| 2025-02-13 | EDSA | -$89 | bail_timer |
| 2025-02-19 | SINT | -$291 | max_loss_hit |
| 2025-02-24 | ATCH | +$248 | topping_wicky |
| 2025-02-25 | WAFU | -$78 | topping_wicky |
| 2025-03-03 | POLA | -$574 | max_loss_hit |
| 2025-03-26 | OSRH | -$506 | max_loss_hit |
| 2025-03-28 | ATON | -$642 | stop_hit |
| 2025-04-22 | GELS | +$584 | bearish_engulfing |
| 2025-04-22 | GELS | -$68 | bearish_engulfing |
| 2025-04-22 | WNW | -$130 | topping_wicky |
| 2025-04-28 | GLMD | -$477 | max_loss_hit |
| 2025-05-06 | KTTA | -$85 | bearish_engulfing |
| 2025-05-13 | ELSE | -$908 | bail_timer |
| 2025-05-14 | INM | +$61 | topping_wicky |
| 2025-05-19 | PTIX | +$458 | topping_wicky |
| 2025-05-19 | PTIX | +$129 | bearish_engulfing |
| 2025-05-19 | DTSS | +$73 | trail_stop |
| 2025-05-29 | BOSC | $0 | trail_stop |
| 2025-05-29 | WETO | -$475 | max_loss_hit |
| 2025-06-04 | BAOS | -$183 | bearish_engulfing |
| 2025-06-09 | TAOX | -$41 | topping_wicky |
| 2025-06-10 | EVGN | -$179 | bearish_engulfing |
| 2025-06-18 | LSE | +$4,602 | bearish_engulfing |
| 2025-06-20 | AIFF | +$5,602 | bearish_engulfing |
| 2025-06-23 | WFF | -$646 | max_loss_hit |
| 2025-06-24 | INM | -$2,639 | max_loss_hit |
| 2025-06-27 | BBLG | -$77 | bearish_engulfing |
| 2025-06-30 | WBUY | -$398 | bearish_engulfing |
| 2025-07-01 | CLRO | -$645 | bail_timer |
| 2025-07-07 | MBIO | -$62 | bearish_engulfing |
| 2025-07-11 | CVM | +$282 | bearish_engulfing |
| 2025-07-11 | CVM | +$191 | bearish_engulfing |
| 2025-07-16 | NUWE | -$185 | topping_wicky |
| 2025-07-28 | CRVO | +$145 | topping_wicky |
| 2025-08-05 | AUUD | -$385 | bearish_engulfing |
| 2025-08-14 | SNOA | -$658 | max_loss_hit |
| 2025-08-14 | XPON | -$493 | bearish_engulfing |
| 2025-08-14 | BMRA | -$256 | bearish_engulfing |
| 2025-08-15 | PPSI | -$544 | max_loss_hit |
| 2025-08-19 | PRFX | -$244 | bearish_engulfing |
| 2025-08-21 | PTIX | -$584 | max_loss_hit |
| 2025-08-21 | APM | -$211 | bearish_engulfing |
| 2025-09-02 | SHFS | -$511 | bearish_engulfing |
| 2025-09-02 | UUU | +$1,138 | bearish_engulfing |
| 2025-09-02 | HWH | -$558 | bearish_engulfing |
| 2025-09-03 | STI | -$569 | max_loss_hit |
| 2025-09-03 | BTBD | -$33 | bearish_engulfing |
| 2025-09-03 | AIHS | $0 | bearish_engulfing |
| 2025-09-03 | AIHS | +$1,558 | bearish_engulfing |
| 2025-09-04 | CIGL | +$1,987 | bearish_engulfing |
| 2025-09-04 | CIGL | +$225 | bearish_engulfing |
| 2025-09-04 | BRIA | +$1,266 | bearish_engulfing |
| 2025-09-04 | BBLG | -$598 | max_loss_hit |
| 2025-09-05 | VEEE | -$587 | max_loss_hit |
| 2025-09-15 | MBAI | -$304 | bearish_engulfing |
| 2025-09-16 | SNTG | $0 | bail_timer |
| 2025-09-16 | SNTG | -$354 | bearish_engulfing |
| 2025-09-19 | FATN | +$93 | bearish_engulfing |
| 2025-09-22 | AIXC | -$562 | max_loss_hit |
| 2025-09-26 | EGG | -$720 | max_loss_hit |
| 2025-09-29 | JFB | -$449 | topping_wicky |
| 2025-09-29 | SCOR | -$872 | max_loss_hit |
| 2025-10-06 | SOPA | -$84 | bearish_engulfing |
| 2025-10-07 | BJDX | -$333 | stop_hit |
| 2025-10-08 | XBIO | +$35 | bearish_engulfing |
| 2025-10-08 | ACXP | -$281 | max_loss_hit |
| 2025-10-08 | BGMS | -$284 | max_loss_hit |
| 2025-10-09 | TCRT | -$79 | bearish_engulfing |
| 2025-10-10 | OLOX | +$300 | bearish_engulfing |
| 2025-10-13 | PMAX | -$329 | stop_hit |
| 2025-10-13 | NDRA | -$89 | bearish_engulfing |
| 2025-10-13 | STI | -$280 | max_loss_hit |
| 2025-10-14 | GWAV | -$90 | bearish_engulfing |
| 2025-10-14 | CYN | -$112 | topping_wicky |
| 2025-10-15 | COOT | +$280 | topping_wicky |
| 2025-10-15 | COOT | -$52 | bearish_engulfing |
| 2025-10-15 | PFAI | -$152 | bearish_engulfing |
| 2025-10-16 | LGCB | +$164 | topping_wicky |
| 2025-10-21 | BOF | -$98 | bearish_engulfing |
| 2025-10-23 | IMCC | -$269 | max_loss_hit |
| 2025-10-23 | OLOX | -$237 | max_loss_hit |
| 2025-10-23 | SLMT | +$342 | topping_wicky |
| 2025-10-24 | AIXC | -$56 | bearish_engulfing |
| 2025-10-29 | ERNA | -$277 | max_loss_hit |
| 2025-10-31 | DFSC | -$100 | bearish_engulfing |
| 2025-10-31 | DLHC | +$31 | bearish_engulfing |
| 2025-11-07 | MSGM | -$119 | bearish_engulfing |
| 2025-11-10 | MOVE | -$157 | bearish_engulfing |
| 2025-11-12 | CMCT | -$305 | stop_hit |
| 2025-11-21 | MNDR | -$100 | bearish_engulfing |
| 2025-12-01 | QTTB | -$316 | bearish_engulfing |
| 2025-12-02 | TAOP | -$346 | bearish_engulfing |
| 2025-12-03 | PMAX | +$361 | bearish_engulfing |
| 2025-12-03 | HTOO | -$584 | stop_hit |
| 2025-12-08 | CETX | -$257 | bearish_engulfing |
| 2025-12-09 | XCUR | -$498 | max_loss_hit |
| 2025-12-09 | AMCI | +$67 | topping_wicky |
| 2025-12-09 | AMCI | -$113 | bearish_engulfing |
| 2025-12-09 | VOR | -$101 | bearish_engulfing |
| 2025-12-15 | ARBB | -$500 | max_loss_hit |
| 2025-12-15 | GLSI | -$180 | bearish_engulfing |
| 2025-12-16 | VERO | -$498 | max_loss_hit |
| 2025-12-18 | LONA | -$276 | bearish_engulfing |
| 2025-12-23 | TIVC | -$446 | max_loss_hit |
| 2025-12-23 | OPTX | +$42 | topping_wicky |
| 2025-12-29 | SOPA | -$384 | max_loss_hit |
| 2025-12-31 | ANGH | -$233 | topping_wicky |
| 2026-01-12 | OM | +$692 | bearish_engulfing |
| 2026-01-12 | BDSX | -$13 | bail_timer |
| 2026-01-13 | AHMA | -$10 | bearish_engulfing |
| 2026-01-14 | ROLR | +$3,293 | bearish_engulfing |
| 2026-01-15 | SPHL | -$144 | bearish_engulfing |
| 2026-01-15 | BNKK | +$604 | topping_wicky |
| 2026-01-15 | AGPU | +$652 | topping_wicky |
| 2026-01-20 | SHPH | -$546 | max_loss_hit |
| 2026-01-20 | POLA | -$349 | bail_timer |
| 2026-01-21 | SLGB | -$80 | bearish_engulfing |
| 2026-01-22 | SXTP | -$597 | stop_hit |
| 2026-01-27 | CYN | -$461 | max_loss_hit |
| 2026-01-30 | PMN | +$207 | bearish_engulfing |
| 2026-02-10 | SPOG | -$86 | bearish_engulfing |
| 2026-02-17 | PLYX | $0 | bearish_engulfing |
| 2026-02-17 | PLYX | -$89 | bearish_engulfing |
| 2026-02-19 | RUBI | -$82 | bail_timer |
| 2026-02-20 | CDIO | -$166 | bearish_engulfing |
| 2026-03-18 | ARTL | +$521 | topping_wicky |
| 2026-03-19 | DLTH | -$290 | bearish_engulfing |
| 2026-03-23 | UGRO | -$185 | bearish_engulfing |
| 2026-03-24 | FEED | -$70 | bearish_engulfing |
| 2026-03-24 | LICN | -$664 | bail_timer |
