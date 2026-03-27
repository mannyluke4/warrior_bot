# January 2025 Strategy Misalignment Audit

**Generated:** 2026-03-22
**Period:** January 2–31, 2025 (22 trading days)
**Data sources:** 22 daily Ross vs Bot comparison files, ross_vs_bot_jan_2025.md monthly summary, v2 megatest state JSONs (all_three, sq_only, mp_only), mp_trade_logic_analysis.md, mp_max_loss_deep_dive.md, missed_stocks_backtest_plan.md
**Purpose:** Identify every strategy disconnect between the Warrior Bot and Ross Cameron's actual trading before making any code changes or backtesting adjustments.

---

## Executive Summary

Ross Cameron made approximately **$406,000** in January 2025 across 88+ trades with a 78% win rate. The bot (all-three config) lost **-$1,531** across 42 trades with a 40% win rate. The gap is ~265x.

Three structural problems explain nearly all of the gap, in priority order:

1. **Exit management** — On the 5 tickers both traded, the bot captured $2,394 while Ross captured ~$101,424. The bot left **~$99,000 on the table** on shared trades alone. The ALUR trade is the single most damning data point: same stock, same entry time, bot made $586, Ross made $85,900.

2. **MP strategy** — 0% win rate in the MP-only config (14 trades, -$3,947). Every single MP trade in January lost money. MP is a pure drag on the system.

3. **Scanner/selection gaps** — The scanner found only 7.4% of Ross's tickers (5 of 68). It missed 8 of Ross's 11 biggest winners ($10K+ trades). Even when it found the right stock (INM ranked #1 on Jan 21), the bot often traded lower-ranked losers instead.

---

## Part 1: Exit Management Audit (PRIORITY #1)

### 1.1 Shared-Ticker Trade-Level Breakdown

These are the 5 tickers where both Ross and the bot traded the same stock in January. This is the cleanest apples-to-apples comparison possible.

#### ALUR — January 24 (The Single Most Important Trade Comparison)

| Metric | Ross | Bot (SQ, all-three config_a) |
|---|---|---|
| Entry price | ~$8.24 | $8.04 |
| Entry time | ~7:01 AM | 7:01 AM |
| Exit price | Rode to ~$20 | $8.40 (trade 1) |
| P&L | **+$85,900** | **+$586** (3 trades net) |
| Exit reason | Held through multiple halts | sq_target_hit at +4.1R |
| Stock's actual high | ~$20+ | ~$20+ |

Bot trade detail:
- Trade 1: Entry $8.04, exit $8.40, +$506, sq_target_hit at 07:04 (+4.1R)
- Trade 2: Entry $10.04, exit $10.03, -$9, sq_para_trail_exit at 07:07 (-0.1R)
- Trade 3: Entry $10.04, exit $10.14, +$89, sq_para_trail_exit at 07:08 (+0.7R)

**The bot entered BEFORE Ross at a BETTER price ($8.04 vs $8.24) and exited 3 minutes later at $8.40.** The stock then ran to $20 — a $12/share move. The sq_target_hit exit at +4.1R was technically "working as designed" but represents a catastrophic missed opportunity. The bot captured $0.36 of a $12.00 move — **3% of the available range**.

**Dollar gap: $85,314.** This single trade accounts for more than the entire month's performance difference.

**Root cause:** The sq_target_hit exit fires at a fixed R-multiple. On a stock that gaps 181% premarket with explosive momentum, a 4.1R target is reached in 3 minutes and leaves the vast majority of the move uncaptured. There is no mechanism to recognize that ALUR was a once-a-month A+ runner that warranted holding.

#### WHLR — January 16

| Metric | Ross | Bot (SQ) |
|---|---|---|
| Entry price | ~$3.82 | $4.04 |
| Exit price | ~$4.20+ (multiple trades in range) | $4.05 |
| P&L | **+$3,800** | **+$28** |
| Exit reason | Range-traded $3.82–$4.20 multiple times | sq_para_trail_exit at +0.1R |
| Stock's actual high | Well above $4.20 (squeeze through $4) | Well above $4.20 |

Bot trade detail:
- Single trade: Entry $4.04, exit $4.05, +$28, sq_para_trail_exit at 07:18 (+0.1R)

**The bot captured $0.01/share on a stock Ross range-traded for $3,800.** The parabolic trail exit fired after capturing just +0.1R — one penny of profit. The scanner correctly found WHLR (Profile A, 190K float, 53.6% gap) but the exit management gave back virtually the entire opportunity.

**Dollar gap: $3,772.** The parabolic trail exit is the culprit — it's designed to protect against reversals but on a trending stock it clips the trade at the first micro-pullback.

#### YIBO/YWBO — January 28

| Metric | Ross | Bot (VR, all-three) |
|---|---|---|
| Entry price | $5.57 | $5.79 |
| Exit price | ~$6.36 | $6.12 |
| P&L | **+$5,724** | **+$125** |
| Exit reason | Held for full VWAP reclaim move | vr_core_tp_1.5R |
| Stock's actual high | ~$6.36+ | ~$6.36+ |

Bot trade detail:
- Single trade: Entry $5.79, exit $6.12, +$125, vr_core_tp_1.5R at 09:31–09:32

**The bot captured 42% of the stock's range** but Ross's 46x P&L advantage came from two factors: (1) sizing — Ross used ~19x the notional, and (2) exit management — Ross captured the full move to $6.36 while the bot exited at $6.12 via the 1.5R target.

**Dollar gap: $5,599.** This is primarily a sizing gap (19x), with exit management contributing the rest.

#### SLXN — January 29

| Metric | Ross | Bot (SQ) |
|---|---|---|
| Entry price | ~$2.00 breakout | $2.43 |
| Exit price | Built to ~$7K, gave back | $2.49 |
| P&L | **~+$5,000 net** | **+$231** |
| Exit reason | Multiple trades, gave back some | sq_para_trail_exit at +0.5R |

Bot trade detail:
- Single trade: Entry $2.43, exit $2.49, +$231, sq_para_trail_exit at 10:30 (+0.5R)

**Dollar gap: ~$4,769.** The bot entered late ($2.43 vs Ross's $2.00) and exited after capturing only +0.5R via the parabolic trail.

#### AIFF — January 14 (Bot OUTPERFORMED Ross)

| Metric | Ross | Bot (combined) |
|---|---|---|
| Entry price | ~$10.08 (VWAP break) | $4.21 (MP), $4.61 (SQ) |
| P&L | **-$2,000** | **+$1,424** |
| Exit reason | Sharp rejection after reluctant entry | SQ: sq_target_hit at +4.2R and +3.7R |

Bot trade detail:
- MP trade: Entry $4.21, exit $4.18, -$17, topping_wicky_exit at 09:07–09:10
- SQ trade 1: Entry $4.61, exit $5.08, +$520, sq_target_hit at 09:31 (+4.2R)
- SQ trade 2: Entry $4.61, exit $5.36, +$921, sq_target_hit at 09:32–09:36 (+3.7R)

**The bot outperformed Ross by $3,424 on this ticker.** Ross entered emotionally at $10.08 after his prior AIFF experience; the bot entered mechanically at $4.61 and caught clean squeeze targets. This is the bot working exactly as designed — mechanical discipline beating human emotion.

### 1.2 Exit Mechanism Analysis Across All January Bot Trades

Using the all-three config_a data (removing duplicates from config_b):

| Exit Reason | Trades | Wins | Losses | Net P&L | Avg P&L |
|---|---|---|---|---|---|
| sq_target_hit | 3 | 3 | 0 | +$1,947 | +$649 |
| sq_para_trail_exit | 13 | 9 | 4 | +$159 | +$12 |
| sq_max_loss_hit | 1 | 0 | 1 | -$98 | -$98 |
| bearish_engulfing_exit_full | 5 | 0 | 5 | -$342 | -$68 |
| topping_wicky_exit_full | 5 | 2 | 3 | +$75 | +$15 |
| max_loss_hit | 4 | 0 | 4 | -$2,731 | -$683 |
| vr_core_tp_1.5R | 1 | 1 | 0 | +$125 | +$125 |

**Key findings:**

1. **sq_target_hit is the only high-conviction winner** — 3 for 3, +$1,947 total, avg +$649/trade. But it fires too early on big runners (ALUR: exited at $8.40, stock went to $20).

2. **sq_para_trail_exit is the most frequent exit** — 13 trades, marginally positive (+$159 net), but it's clipping winners at +0.1R to +0.5R. WHLR (+$28 on a +$3,800 Ross trade) and SLXN (+$231 on a ~+$5,000 Ross trade) were both killed by the parabolic trail. It captures 9 small wins but leaves massive money on the table.

3. **max_loss_hit is devastating** — 4 trades, all losers, -$2,731. Average loss of $683. These are PTHS (-$679), STAI (-$714), CYCN (-$662), NCEL (-$676) — all MP trades that hit the 0.75R cap.

4. **bearish_engulfing exits are consistently small losers** — -$68 avg. Not catastrophic but never winning in January.

### 1.3 Total Money Left on the Table (Shared Tickers)

| Date | Ticker | Bot P&L | Ross P&L | Gap | Primary Cause |
|---|---|---|---|---|---|
| Jan 14 | AIFF | +$1,424 | -$2,000 | Bot won by $3,424 | Bot discipline > human emotion |
| Jan 16 | WHLR | +$28 | +$3,800 | -$3,772 | Parabolic trail exit at +0.1R |
| Jan 24 | ALUR | +$586 | +$85,900 | -$85,314 | sq_target_hit at +4.1R, fixed sizing |
| Jan 28 | YIBO | +$125 | +$5,724 | -$5,599 | 1.5R target + 19x sizing gap |
| Jan 29 | SLXN | +$231 | ~+$5,000 | -$4,769 | Parabolic trail at +0.5R |
| **TOTALS** | | **+$2,394** | **~+$98,424** | **-$96,030** | |

**The bot left approximately $96,000 on the table across just 5 shared tickers.** Removing the AIFF outperformance, the gap on the other 4 tickers is $99,454.

### 1.4 Exit Management Diagnosis

The exit system has two distinct failure modes:

**Failure Mode A — Premature Target Exits (sq_target_hit):**
The sq_target_hit exit fires at a fixed R-multiple and takes full profit. On ALUR, this triggered at +4.1R ($8.04→$8.40) while the stock ran to $20. The target was calibrated for average trades, not A+ runners. On AIFF, the same mechanism worked perfectly (+4.2R and +3.7R captures). The problem isn't the mechanism itself — it's the lack of differentiation between "exit here" and "hold for a runner."

**Failure Mode B — Premature Trail Exits (sq_para_trail_exit):**
The parabolic trail exit fires at the first sign of a micro-pullback after any profit. On WHLR, it exited at +$0.01/share (+0.1R). On SLXN, it exited at +$0.06/share (+0.5R). On ORIS (Jan 2), two trades: one hit for -0.9R instantly, one caught +0.3R. The trail is too tight — it's optimized to avoid giving back gains but in practice it clips every trade before meaningful profit develops.

**What Ross does differently:** Ross uses a combination of (1) holding through halts on A+ setups (ALUR), (2) range-trading with multiple re-entries on range-bound stocks (WHLR), and (3) building to a target and scaling out (SLXN). None of these behaviors exist in the bot's exit logic.

---

## Part 2: MP Strategy Audit

### 2.1 January MP Trades — Complete Record (MP-Only Config A)

The MP-only configuration produced **14 trades in January 2025, all losers, -$3,947, 0% win rate.**

| Date | Symbol | Entry | Exit | P&L | R-Mult | Exit Reason | Hold Time |
|---|---|---|---|---|---|---|---|
| Jan 2 | ORIS | $2.80 | $2.78 | -$107 | -0.1R | bearish_engulfing | 2 min |
| Jan 13 | ATPC | $2.69 | $2.68 | -$17 | -0.0R | bearish_engulfing | 2 min |
| Jan 13 | KAPA | $2.69 | $2.62 | -$47 | -0.2R | bearish_engulfing | 1 min |
| Jan 14 | AIFF | $4.21 | $4.18 | -$17 | -0.1R | topping_wicky | 3 min |
| Jan 15 | BKYI | $3.24 | $3.23 | -$8 | -0.0R | bearish_engulfing | 2 min |
| Jan 21 | PTHS | $3.66 | $3.40 | -$646 | -0.9R | max_loss_hit | 1 min |
| Jan 21 | VATE | $7.14 | $7.09 | -$155 | -0.2R | bearish_engulfing | 2 min |
| Jan 23 | NTRB | $9.47 | $9.14 | -$629 | -0.9R | max_loss_hit | <1 min |
| Jan 23 | VNCE | $4.17 | $4.15 | -$48 | -0.1R | topping_wicky | 3 min |
| Jan 24 | NVNI | $2.97 | $2.89 | -$83 | -0.3R | bearish_engulfing | <1 min |
| Jan 24 | PRFX | $4.20 | $4.10 | -$354 | -0.5R | topping_wicky | 3 min |
| Jan 30 | STAI | $2.13 | $2.02 | -$639 | -0.9R | max_loss_hit | 1 min |
| Jan 31 | CYCN | $3.34 | $3.21 | -$592 | -0.9R | max_loss_hit | <1 min |
| Jan 31 | NCEL | $3.21 | $3.05 | -$605 | -0.9R | max_loss_hit | 3 min |

### 2.2 Exit Reason Breakdown

| Exit Type | Count | Total P&L | Avg P&L | Avg R-Mult |
|---|---|---|---|---|
| bearish_engulfing | 5 | -$317 | -$63 | -0.12R |
| topping_wicky | 3 | -$419 | -$140 | -0.23R |
| max_loss_hit | 6 | -$3,211 | -$535 | -0.88R |
| **Total** | **14** | **-$3,947** | **-$282** | -0.39R |

**The max_loss_hit exits are the core damage.** 6 of 14 trades (43%) hit the 0.75R safety cap, averaging -$535 each. These 6 trades account for 81% of the total MP loss.

The bearish_engulfing and topping_wicky exits are performing their loss-limiting function (small, quick losses averaging -$63 and -$140), but they never produce a winner in January. The strategy enters and immediately encounters adverse price action on every trade.

### 2.3 MP vs SQ on the Same Days and Stocks

On days where both MP and SQ strategies traded the same stock:

**AIFF (Jan 14):**
- MP: Entry $4.21, exit $4.18, -$17 (topping_wicky)
- SQ: Entry $4.61, exit $5.08/$5.36, +$1,441 (sq_target_hit)
- **SQ outperformed MP by $1,458 on the same stock.** MP entered 24 minutes earlier at a slightly lower price but got stopped out on a wicky pattern. SQ entered later into confirmed momentum and caught the squeeze.

**VNCE (Jan 23):**
- MP: Entry $4.17, exit $4.15, -$48 (topping_wicky)
- SQ: Entry $4.04/$4.64, net -$76 across 3 trades in all-three
- SQ-only: Entry $4.04/$4.64/$4.64, net +$1,444 (third trade hit sq_target_hit for +$1,500)
- **In SQ-only, the strategy found a $1,500 winner that the all-three config missed** because the earlier MP entry consumed a trade slot.

**BKYI (Jan 15):**
- MP: Entry $3.24, exit $3.23, -$8
- SQ: Entry $2.64, exit $2.53, -$98 (sq_max_loss_hit)
- Both lost on BKYI — validating that this was a bad stock to trade (Ross also passed on it).

### 2.4 Ross's MP Usage vs Bot's MP Usage

From the monthly summary:
- **Ross took 4 MP trades all month — all winners, +$11,750, 100% win rate.**
- **The bot took 14 MP trades — all losers, -$3,947, 0% win rate.**

Ross uses micro pullbacks extremely selectively — only as a secondary re-entry on tickers that have already proven themselves with volume and momentum. He never leads with an MP trade. The bot fires MP indiscriminately on anything that triggers the pullback pattern, with no quality gate for "this stock has already proven it can run."

### 2.5 MP Drag Quantification

If we removed MP entirely from January:

| Config | With MP | Without MP (SQ-only equivalent) | Improvement |
|---|---|---|---|
| All-three | -$1,531 | +$2,416 (approx) | +$3,947 |
| MP-only | -$3,947 | $0 | +$3,947 |

**Removing MP would have turned the all-three config from -$1,531 to approximately +$2,416 in January** — a swing of nearly $4,000. MP is not just underperforming; it is actively destroying the edge that SQ generates.

### 2.6 Full-Year MP Context

The January performance is not an anomaly. From the full megatest (Jan 2025–Mar 2026):
- MP-only: 154 trades, 26% win rate, -$10,121 net P&L
- MP lost money in 12 of 15 months
- January 2025 was the worst month: -$3,947
- The strategy has an 18-trade maximum consecutive loss streak
- Only profitable in the 7:00 AM hour; every other hour is net negative
- Only profitable on Fridays; every other day is net negative

The "genuine MP" trades (excluding max_loss_hit) are actually marginally profitable (+$5,563 on 108 trades, 37% win rate) — but the 42 max_loss_hit trades (-$15,425) destroy the edge. The core pullback pattern has a faint signal buried under layers of bad entries.

---

## Part 3: Selection & Filtering Gaps

### 3.1 Scanner Coverage Overview

| Metric | Value |
|---|---|
| Ross's unique tickers in January | 68+ |
| Bot scanner's unique tickers | ~40 |
| Overlap (both saw) | 15 tickers (21%) |
| Both traded | 5 tickers (7.4%) |
| Ross traded, bot missed entirely | 63+ tickers |
| Bot traded, Ross didn't | 19 tickers |

### 3.2 Scanner Misses on Ross's Big Winners ($10K+)

| Date | Ticker | Ross P&L | Scanner Found? | Bot Traded? | Why Missed |
|---|---|---|---|---|---|
| Jan 2 | XPON | +$15,000 | NO | NO | Mid-morning breaking news, not a gap play |
| Jan 9 | ESHA | +$15,556 | NO | NO | Day not in comparison files |
| Jan 9 | INBS | +$18,444 | NO | NO | Day not in comparison files |
| Jan 21 | INM | +$12,000 | **YES** (#1 rank) | **NO** | Found but not traded — entry criteria didn't fire |
| Jan 23 | DGNX | +$22,997 | NO | NO | Chinese IPO — systematic blindspot |
| Jan 24 | ALUR | +$85,900 | **YES** (#1 rank) | **YES** (+$586) | Traded but exit management captured 0.7% |
| Jan 27 | JG | +$15,558 | NO | NO | Chinese AI stock — scanner blindspot |
| Jan 28 | ARNAZ | +$12,234 | NO | NO | Daily breakout pattern — structural limitation |
| Jan 29 | SGN | +$13,000 | NO | NO | Likely insufficient gap/volume at scan time |
| Jan 30 | AMOD | positive | **YES** (Profile X) | **NO** | Found but blocked — no float data |
| Jan 31 | SGN | +$20,000 | NO | NO | Multi-day continuation — scanner treats each day fresh |

**Scanner hit rate on $10K+ winners: 3 of 11 (27%).** Of those 3:
- ALUR: traded, captured 0.7% of Ross's gain
- INM: found but not traded
- AMOD: found but blocked by Profile X (no float data)

**Total missed P&L on $10K+ winners the scanner didn't find: ~$132,789.** Total missed P&L on $10K+ winners the scanner found but bot didn't trade effectively: ~$97,000+ (ALUR, INM, AMOD combined).

### 3.3 Profile X Blocks

Two stocks were found by the scanner but couldn't be traded because float data was missing:

| Date | Ticker | Gap% | Ross P&L | What Happened |
|---|---|---|---|---|
| Jan 6 | GDTC | +93.6% | +$5,300 | Scanner found at 07:00, classified Profile X, 0 trades. Ross bought the dip at $6.13, rode to $9.50. |
| Jan 30 | AMOD | +79.9% | positive (unknown) | Scanner found, Profile X, 0 trades. Breaking news, primary winner of the day. |

**Combined missed P&L from Profile X blocks: $5,300+ (minimum).** This is a data quality issue — the scanner correctly identifies the stock but the missing float data prevents it from being traded. Fixing the float data source would immediately unlock these opportunities.

### 3.4 "Found But Not Traded" Cases

These are stocks the scanner found and ranked, but the bot took 0 trades on:

| Date | Ticker | Rank | Profile | Ross P&L | What Happened |
|---|---|---|---|---|---|
| Jan 6 | GDTC | #1 | X | +$5,300 | Profile X blocked |
| Jan 14 | OST | found | A | +$1,800 | No entry signal triggered |
| Jan 16 | WHLR | found | A | +$3,800 | SQ got +$28, MP got nothing |
| Jan 17 | BTCT | #3 | B | small profit | 0 trades despite selection |
| Jan 21 | INM | **#1** (1.027) | — | +$12,000 | **#1 ranked, not traded. Bot traded #3, #4, #5 instead.** |
| Jan 30 | AMOD | found | X | positive | Profile X blocked |

**The INM case (Jan 21) is the most damaging selection gap.** INM was ranked #1 by the scanner with a score of 1.027 — the highest-ranked candidate of the day by a wide margin. Despite this, the bot traded VATE (#5, -$163), PTHS (#3, -$679), and LEDS (#4, -$281) instead. All three lost money. INM would have been Ross's +$12,000 winner with an extremely low 68K float.

The root cause: the bot's entry criteria (micro_pullback and squeeze templates) didn't fire on INM's specific price action pattern, so lower-ranked stocks that did produce entry signals were traded instead. The ranking system correctly identified the opportunity but the entry logic couldn't capitalize on it.

### 3.5 Systematic Scanner Blindspots

Analysis of the 89 missed stocks reveals several structural blindspots:

**1. Chinese stocks (confirmed systematic blindspot):**
- Jan 23: DGNX (+$22,997), DXST, MIMI — all Chinese IPOs, zero scanner overlap
- Jan 27: AURL (200%+ move), JG (+$15,558) — Chinese AI stocks on DeepSeek day
- Jan 31: SZK — Chinese reverse split

**2. Mid-morning/intraday catalyst discoveries:**
- Jan 2: XPON — breaking news post-7:30 AM
- Jan 15: OSTX — Phase 2 clinical trial news at 7:41 AM
- Jan 21: NXX — breaking news at 7:30 AM
- Jan 29: MVNI — Ross's anchor trade discovered at 9:47 AM (+$3,900)
- The scanner's 7:15 AM primary window misses anything that emerges later

**3. Daily chart breakout patterns:**
- Jan 28: ARNAZ (+$12,000) — "first candle to make new high" daily breakout, halt resumption dip-and-rip. The gap-based scanner literally cannot detect this pattern.

**4. Multi-day continuation plays:**
- Jan 3: SPCB day-2 continuation (+$2,600)
- Jan 13: DATS no-news continuation (+$2,000)
- Jan 16: DATS recurring runner
- Jan 31: SGN day-2 continuation (+$20,000)
- The scanner treats each day independently with no memory of prior runners

**5. Thematic/macro awareness:**
- Jan 21: TPET (inauguration energy theme), BTCT (inauguration crypto theme) — Ross identified these through macro awareness; the bot has no concept of market themes

**6. No-news momentum stocks:**
- Jan 10: XHG (+$3,500) — no catalyst, pure momentum continuation. Ross's biggest winner that day.
- These stocks don't gap enough premarket to trigger the scanner

### 3.6 Bot-Only Trades (Ross Didn't Touch)

The bot traded 19 tickers that Ross never mentioned. Combined P&L on these "noise trades": approximately -$2,617 (9 wins, 19 losses).

Notable examples:
- ORIS (Jan 2): -$313. 0.2M float, 76.5% gap — looks good on paper but Ross ignored it
- KAPA (Jan 13): -$47. 8.69M float — Ross never mentioned it
- PTHS (Jan 21): -$679. Bot traded #3 ranked stock while ignoring #1 (INM)
- LEDS (Jan 21): -$281. Bot traded #4 while ignoring #1
- NTRB (Jan 23): -$629. MP-only trade on a stock Ross didn't see
- CYCN (Jan 31): -$1,254 combined (MP + SQ). Neither on Ross's radar
- NCEL (Jan 31): -$676. Neither on Ross's radar

**The bot is trading stocks that a skilled human trader wouldn't touch, and losing money on them.** The SQ portion of these noise trades was roughly flat (+$1,313) but the MP portion was brutal (-$3,930).

---

## Part 4: Pattern Analysis

### 4.1 What Winning Bot Trades Have in Common

Using all-three config_a January winners (trades with positive P&L):

| Date | Symbol | Strategy | Entry | P&L | R-Mult | Exit Reason | Key Characteristics |
|---|---|---|---|---|---|---|---|
| Jan 7 | MYSE | SQ | $3.19 | +$53 | +0.1R | sq_para_trail | 29.1% gap, 3.97M float, Profile A |
| Jan 7 | MYSE | SQ | $3.19 | +$185 | +0.5R | sq_para_trail | Same stock, second trade |
| Jan 8 | SILO | SQ | $2.47 | +$62 | +0.5R | sq_para_trail | Bot-only stock |
| Jan 10 | VMAR | SQ | $3.73 | +$80 | +0.2R | sq_para_trail | 84.9% gap, 0.87M float, Profile A |
| Jan 14 | AIFF | SQ | $4.61 | +$520 | +4.2R | sq_target_hit | 63.4% gap, 6.3M float |
| Jan 14 | AIFF | SQ | $4.61 | +$921 | +3.7R | sq_target_hit | Same stock, second trade |
| Jan 16 | WHLR | SQ | $4.04 | +$28 | +0.1R | sq_para_trail | 53.6% gap, 190K float, Profile A |
| Jan 21 | VATE | MP | $7.23 | +$320 | +0.8R | topping_wicky | Only MP winner in all-three config |
| Jan 23 | VNCE | SQ | $4.04 | +$55 | +0.1R | sq_para_trail | Vol=6.45M |
| Jan 24 | ALUR | SQ | $8.04 | +$506 | +4.1R | sq_target_hit | 181% gap, 12.8M PM vol |
| Jan 24 | ALUR | SQ | $10.04 | +$89 | +0.7R | sq_para_trail | Re-entry |
| Jan 24 | PRFX | MP | $4.06 | +$174 | +0.5R | topping_wicky | 12.2% gap |
| Jan 28 | YIBO | VR | $5.79 | +$125 | +1.0R | vr_core_tp_1.5R | 92.2% gap, Chinese AI |
| Jan 29 | SLXN | SQ | $2.43 | +$211 | +0.5R | sq_para_trail | 57.8% gap, 30.9M PM vol |

**Winner profile:**
- **100% of winners with P&L > $100 are SQ or VR trades** (not MP-only)
- **The biggest winners use sq_target_hit exits** — AIFF ($520, $921) and ALUR ($506)
- **Most SQ winners have massive premarket gaps** — ALUR 181%, YIBO 92%, VMAR 85%, AIFF 63%, SLXN 58%, WHLR 54%
- **Low float tends to correlate with bigger moves** — WHLR (190K), VMAR (870K)
- **Entry time skews early** — 7:00–9:30 AM for the biggest winners

### 4.2 What Losing Bot Trades Have in Common

Using all-three config_a January losers:

| Date | Symbol | Strategy | Entry | P&L | R-Mult | Exit Reason |
|---|---|---|---|---|---|---|
| Jan 2 | ORIS | SQ | $3.04 | -$321 | -0.9R | sq_para_trail |
| Jan 2 | ORIS | MP | $2.80 | -$107 | -0.1R | bearish_engulfing |
| Jan 13 | ATPC | MP | $2.69 | -$17 | -0.0R | bearish_engulfing |
| Jan 13 | KAPA | MP | $2.69 | -$47 | -0.2R | bearish_engulfing |
| Jan 14 | AIFF | MP | $4.21 | -$17 | -0.1R | topping_wicky |
| Jan 15 | BKYI | SQ | $2.64 | -$98 | -0.8R | sq_max_loss_hit |
| Jan 15 | BKYI | MP | $3.24 | -$8 | -0.0R | bearish_engulfing |
| Jan 21 | LEDS | SQ | $2.44 | -$280 | -0.7R | sq_para_trail |
| Jan 21 | PTHS | MP | $3.66 | -$679 | -0.9R | max_loss_hit |
| Jan 21 | VATE | MP | $7.14 | -$163 | -0.2R | bearish_engulfing |
| Jan 23 | VNCE | MP | $4.21 | -$22 | -0.0R | topping_wicky |
| Jan 23 | VNCE | SQ | $4.64 | -$109 | -0.3R | sq_para_trail |
| Jan 24 | ALUR | SQ | $10.04 | -$9 | -0.1R | sq_para_trail |
| Jan 24 | PRFX | MP | $4.20 | -$380 | -0.5R | topping_wicky |
| Jan 30 | STAI | MP | $2.13 | -$714 | -0.9R | max_loss_hit |
| Jan 31 | CYCN | MP | $3.34 | -$662 | -0.9R | max_loss_hit |
| Jan 31 | NCEL | MP | $3.21 | -$676 | -0.9R | max_loss_hit |

**Loser profile:**
- **MP trades dominate the loser list** — 11 of 17 losing trades are MP
- **max_loss_hit trades are the biggest individual losers** — averaging -$683 each
- **Losing trades on stocks Ross didn't trade** — ORIS, KAPA, BKYI, LEDS, PTHS, NTRB, STAI, CYCN, NCEL. The bot is picking fights Ross wouldn't enter.
- **Quick exits (< 1 min hold time)** — Most MP losers exit within 1-2 minutes, suggesting immediate adverse price action after entry
- **Late entries** — KAPA at 11:15 AM, PTHS at 10:42 AM, NTRB at 11:45 AM. The full-year data confirms post-8 AM MP entries are net negative.

### 4.3 Ross Setup Types vs Bot Capability

Based on the January recaps, Ross used these setup types:

| Setup Type | Frequency | Ross Est. P&L | Bot Can Capture? | Notes |
|---|---|---|---|---|
| Squeeze/breakout (news) | ~37 trades | +$230K+ | **Partially** — SQ strategy exists but exits too early | Best alignment area |
| Dip buy / VWAP reclaim | ~15 trades | +$50K+ | **Partially** — VR strategy exists but limited | Jan 28 YIBO was VR |
| Daily breakout (first candle new high) | ~5 trades | +$30K+ | **No** — scanner can't detect daily patterns | ARNAZ, SGN |
| Level 2 tape reading | ~3 trades | +$25K+ | **No** — bot has no L2 capability | DGNX was pure tape read |
| Sympathy / thematic play | ~5 trades | +$15K+ | **No** — no macro awareness | BTCT, TPET, EVAC |
| Micro pullback re-entry | ~4 trades | +$11.75K | **Theoretically** — MP exists but 0% WR in Jan | Ross uses MP very selectively |
| No-news momentum | ~5 trades | +$10K+ | **No** — scanner requires gap/catalyst | XHG, DATS |
| Chinese IPO/stock plays | ~5 trades | +$35K+ | **No** — systematic scanner blindspot | DGNX, AURL, JG |

**The bot is best positioned for squeeze/breakout setups** — this is where SQ already generates positive P&L. The exit management fix would have the biggest impact here because the bot is already entering the right trades, just exiting too early.

**The bot is structurally incapable of capturing** daily breakouts, L2 tape reads, sympathy plays, and no-news momentum. These represent ~$80K+ of Ross's January P&L and would require fundamental new capabilities.

### 4.4 Day-Level Performance Correlation

| Date | Ross P&L | Bot P&L | Gap | Best Explanation |
|---|---|---|---|---|
| Jan 2 | +$12,000 | -$313 | -$12,313 | Scanner missed XPON (+$15K) |
| Jan 3 | +$4,800 | $0 | -$4,800 | Zero scanner overlap |
| Jan 6 | +$2,825 | $0 | -$2,825 | GDTC Profile X block |
| Jan 7 | +$1,925 | +$239 | -$1,686 | Scanner miss (ZENA, CGBS, HOTH) |
| Jan 8 | unknown | +$62 | — | Bot found SILO independently |
| Jan 9 | +$34,000 | $0* | -$34,000 | No comparison file; massive miss |
| Jan 10 | +$9,500 | +$81 | -$9,419 | Scanner miss + late VMAR entry |
| Jan 13 | +$13,785 | -$64 | -$13,849 | Scanner missed SLRX, PHIO |
| Jan 14 | +$5,634 | +$1,424 | -$4,210 | Scanner missed ADD; bot won AIFF |
| Jan 15 | +$4,978 | $0* | -$4,978 | Zero trades despite 3 candidates |
| Jan 16 | +$5,667 | +$28 | -$5,639 | WHLR found, exit captured 0.7% |
| Jan 17 | +$4,864 | $0 | -$4,864 | Scanner missed ZO, AIMX |
| Jan 21 | +$28,026 | -$1,082 | -$29,108 | INM #1 ranked, not traded |
| Jan 22 | +$21,672 | $0 | -$21,672 | Complete scanner whiff (1 candidate) |
| Jan 23 | ~$40,000 | -$76 | -$40,076 | Chinese IPO blindspot |
| Jan 24 | +$81,400 | +$201 | -$81,199 | ALUR exit captured 0.7% |
| Jan 27 | green | $0* | — | DeepSeek day, Chinese AI blindspot |
| Jan 28 | +$21,000 | +$125 | -$20,875 | ARNAZ daily breakout miss |
| Jan 29 | +$24,000 | +$211 | -$23,789 | Parabolic trail clipped SLXN |
| Jan 30 | green | -$714 | — | AMOD Profile X; traded STAI (loser) |
| Jan 31 | +$26,265 | -$1,338 | -$27,603 | SGN multi-day continuation miss |

*Where the bot's comparison file shows $0 but all-three had some activity, the all-three config is used.

**The 5 worst gap days by dollar amount:**
1. Jan 24: -$81,199 (ALUR exit management)
2. Jan 23: -$40,076 (Chinese IPO blindspot)
3. Jan 9: -$34,000 (data gap)
4. Jan 21: -$29,108 (INM found but not traded + scanner misses)
5. Jan 31: -$27,603 (SGN multi-day continuation)

---

## Part 5: Actionable Findings & Priority Recommendations

### Priority 1: Fix Exit Management

**Problem:** The bot exits winners 10-100x too early. sq_target_hit and sq_para_trail_exit are both calibrated for average trades, not runners.

**Evidence:** ALUR ($586 vs $85,900), WHLR ($28 vs $3,800), YIBO ($125 vs $5,724), SLXN ($231 vs ~$5,000).

**Potential fixes:**
- Implement tiered exits: take partial at current target, let remainder run with a wider trail
- Add "runner detection" — if a stock hits target within 3 minutes and is still accelerating, switch to a time-based or ATR-based trail instead of closing
- Implement halt-through logic — if a stock halts up, hold through the halt (Ross's ALUR strategy)
- Widen the parabolic trail — the current trail clips at the first micro-pullback. Even a 2x wider trail would have captured significantly more on WHLR and SLXN

**Estimated impact:** If the bot captured just 10% of Ross's P&L on shared tickers (instead of 2.4%), that's +$9,800 incremental — turning the month solidly profitable.

### Priority 2: Kill or Radically Rework MP

**Problem:** 0% win rate in January (14 trades, -$3,947). The full-year data shows 26% win rate, -$10,121, with profitability entirely dependent on a single outlier (VERO +$6,523).

**Evidence:** Every MP metric is negative. The max_loss_hit exits account for 81% of January losses. The strategy is anti-correlated with Ross's MP usage (Ross: 4 trades, 100% WR, +$11,750).

**Options:**
1. **Kill MP entirely** — Simplest option. SQ-only was net positive (+$3,175 in Jan). Removing MP adds ~$4K/month.
2. **MP only as re-entry** — Only fire MP on tickers where SQ already won. This mirrors Ross's behavior.
3. **MP only in first hour** — The 7 AM hour is the only profitable time window. Hard cutoff after 8 AM.
4. **Widen the max_loss_cap to 1.0R** — The 0.75R cap is creating certain losers. The genuine MP exits (bearish engulfing, topping wicky) at natural stops show 37% win rate and +$5,563 net. Let those patterns do their job.

**Estimated impact of killing MP:** +$3,947 in January alone. +$10,121 over the full megatest period.

### Priority 3: Fix Scanner Coverage

**Problem:** Scanner found only 7.4% of Ross's tickers. Missed 8 of 11 big winners.

**Sub-priorities:**
1. **Fix Profile X / float data** — GDTC (+$5,300) and AMOD (positive) were found but blocked by missing float data. This is a data source fix, not a strategy fix.
2. **Add continuous rescan through 10 AM** — Multiple misses came from stocks that emerged after the 7:15 AM scan (OSTX at 7:41 AM, NXX at 7:30 AM, MVNI at 9:47 AM). The Jan 27 data proves Chinese AI stocks were discoverable at 10:38 AM.
3. **Add Chinese stock support** — Systematic blindspot confirmed across Jan 23, 27, 28, 31. This is $35K+ in missed P&L.
4. **Add multi-day continuation awareness** — SGN (Jan 29 → Jan 31, +$20K), SPCB (Jan 2 → Jan 3, +$2,600), DATS (recurring across 3 days). The scanner needs a "hot name" memory.
5. **Add daily breakout detection** — ARNAZ (+$12,000) was a daily chart pattern invisible to the gap-based scanner.

### Priority 4: Fix Selection Logic

**Problem:** Even when the scanner finds the right stock, the bot sometimes trades lower-ranked losers instead.

**Evidence:** Jan 21 — INM ranked #1 (1.027), bot traded VATE (#5, -$163), PTHS (#3, -$679), LEDS (#4, -$281). Combined loss: -$1,082. INM would have been +$12,000 for Ross.

**Fix:** If the #1 ranked stock doesn't generate an entry signal, investigate why before trading lower-ranked alternatives. Consider: the ranking is correct, the entry criteria are too restrictive for certain price action patterns.

### Priority 5: Implement Conviction Sizing

**Problem:** The bot uses flat notional sizing (~$15-22K per trade) regardless of setup quality. Ross sizes aggressively on A+ setups (ALUR: he made $85,900 on a single stock).

**Evidence:** On YIBO, the 46x P&L gap was 19x from sizing and the remainder from exit management. Even with perfect exits, the bot would capture a fraction of Ross's P&L on conviction plays.

**Fix:** Scale position size to the scanner rank score. A stock ranked 1.027 (INM) should get 2-3x the notional of a stock ranked 0.597 (VATE).

---

## Appendix A: Complete January 2025 Bot Trade Log (All-Three Config A)

| Date | Symbol | Strategy | Entry | Exit | P&L | R-Mult | Exit Reason |
|---|---|---|---|---|---|---|---|
| Jan 2 | ORIS | SQ | $3.04 | $2.92 | -$321 | -0.9R | sq_para_trail_exit |
| Jan 2 | ORIS | SQ | $3.04 | $3.08 | +$115 | +0.3R | sq_para_trail_exit |
| Jan 2 | ORIS | MP | $2.80 | $2.78 | -$107 | -0.1R | bearish_engulfing |
| Jan 7 | MYSE | SQ | $3.19 | $3.21 | +$53 | +0.1R | sq_para_trail_exit |
| Jan 7 | MYSE | SQ | $3.19 | $3.26 | +$185 | +0.5R | sq_para_trail_exit |
| Jan 8 | SILO | SQ | $2.47 | $2.54 | +$62 | +0.5R | sq_para_trail_exit |
| Jan 10 | VMAR | SQ | $3.73 | $3.76 | +$80 | +0.2R | sq_para_trail_exit |
| Jan 13 | ATPC | MP | $2.69 | $2.68 | -$17 | -0.0R | bearish_engulfing |
| Jan 13 | KAPA | MP | $2.69 | $2.62 | -$47 | -0.2R | bearish_engulfing |
| Jan 14 | AIFF | MP | $4.21 | $4.18 | -$17 | -0.1R | topping_wicky |
| Jan 14 | AIFF | SQ | $4.61 | $5.08 | +$520 | +4.2R | sq_target_hit |
| Jan 14 | AIFF | SQ | $4.61 | $5.36 | +$921 | +3.7R | sq_target_hit |
| Jan 15 | BKYI | SQ | $2.64 | $2.53 | -$98 | -0.8R | sq_max_loss_hit |
| Jan 15 | BKYI | MP | $3.24 | $3.23 | -$8 | -0.0R | bearish_engulfing |
| Jan 16 | WHLR | SQ | $4.04 | $4.05 | +$28 | +0.1R | sq_para_trail_exit |
| Jan 21 | LEDS | SQ | $2.44 | $2.34 | -$280 | -0.7R | sq_para_trail_exit |
| Jan 21 | PTHS | MP | $3.66 | $3.40 | -$679 | -0.9R | max_loss_hit |
| Jan 21 | VATE | MP | $7.14 | $7.09 | -$163 | -0.2R | bearish_engulfing |
| Jan 21 | VATE | MP | $7.23 | $7.47 | +$320 | +0.8R | topping_wicky |
| Jan 23 | VNCE | SQ | $4.04 | $4.06 | +$55 | +0.1R | sq_para_trail_exit |
| Jan 23 | VNCE | MP | $4.21 | $4.21 | -$22 | -0.0R | topping_wicky |
| Jan 23 | VNCE | SQ | $4.64 | $4.60 | -$109 | -0.3R | sq_para_trail_exit |
| Jan 24 | ALUR | SQ | $8.04 | $8.40 | +$506 | +4.1R | sq_target_hit |
| Jan 24 | ALUR | SQ | $10.04 | $10.03 | -$9 | -0.1R | sq_para_trail_exit |
| Jan 24 | ALUR | SQ | $10.04 | $10.14 | +$89 | +0.7R | sq_para_trail_exit |
| Jan 24 | PRFX | MP | $4.06 | $4.17 | +$174 | +0.5R | topping_wicky |
| Jan 24 | PRFX | MP | $4.20 | $4.10 | -$380 | -0.5R | topping_wicky |
| Jan 28 | YIBO | VR | $5.79 | $6.12 | +$125 | +1.0R | vr_core_tp_1.5R |
| Jan 29 | SLXN | SQ | $2.43 | $2.49 | +$211 | +0.5R | sq_para_trail_exit |
| Jan 30 | STAI | MP | $2.13 | $2.02 | -$714 | -0.9R | max_loss_hit |
| Jan 31 | CYCN | MP | $3.34 | $3.21 | -$662 | -0.9R | max_loss_hit |
| Jan 31 | NCEL | MP | $3.21 | $3.05 | -$676 | -0.9R | max_loss_hit |

**32 trades total (config_a). 15 winners, 17 losers. Net P&L: -$865 (config_a); -$1,531 per megatest equity tracking which includes both configs and equity-based sizing effects.**

---

## Appendix B: Scanner Overlap by Day

| Date | Bot Candidates | Ross Tickers | Overlap | Ross Traded Bot Found | Bot Traded Ross Found |
|---|---|---|---|---|---|
| Jan 2 | 4 | 5 | 1 (AEI) | 0 | 0 |
| Jan 3 | 1 | 6 | 0 | 0 | 0 |
| Jan 6 | 5 | 8 | 1 (GDTC) | 0 | 0 |
| Jan 7 | 6 | 7 | 1 (MSAI) | 0 | 0 |
| Jan 8 | — | — | — | — | — |
| Jan 9 | — | — | — | — | — |
| Jan 10 | 2 | 6 | 1 (VMAR) | VMAR | VMAR |
| Jan 13 | 4 | 6 | 1 (ATPC) | ATPC | ATPC |
| Jan 14 | 3 | 6 | 2 (AIFF, OST) | AIFF | AIFF |
| Jan 15 | 3 | 10 | 1 (BKYI) | 0 | 0 |
| Jan 16 | 3 | 5 | 1 (WHLR) | WHLR | WHLR |
| Jan 17 | 4 | 11 | 2 (ZEO, BTCT) | 0 | 0 |
| Jan 21 | 5 | 11 | 1 (INM) | 0 | 0 |
| Jan 22 | 1 | 6 | 0 | 0 | 0 |
| Jan 23 | 4 | 7 | 0 | 0 | 0 |
| Jan 24 | 5 | 4 | 2 (ALUR, OST) | ALUR | ALUR |
| Jan 27 | 4 | 3+ | 0 | 0 | 0 |
| Jan 28 | 2 | 5 | 1 (YIBO) | YIBO | YIBO |
| Jan 29 | 1 | 4 | 1 (SLXN) | SLXN | SLXN |
| Jan 30 | 3 | 2+ | 1 (AMOD) | 0 | 0 |
| Jan 31 | 3 | 3 | 0 | 0 | 0 |

**Days with zero scanner overlap: 6 of 20 mapped days (30%).**
**Days where the bot traded a stock Ross also traded: 7 of 20 (35%).**

---

## Appendix C: The Three Problem Areas — Dollar Impact Summary

| Problem Area | Estimated January Impact | Fix Complexity | Fix Timeline |
|---|---|---|---|
| Exit management (shared tickers) | -$96,030 left on table | Medium — trail/target logic changes | Can backtest immediately |
| MP strategy drag | -$3,947 direct losses | Low — kill or gate MP | Immediate |
| Scanner misses (Ross traded, bot missed) | -$200K+ in missed opportunities | High — data sources, rescan, Chinese stocks | Multi-week |
| Selection gaps (found but not traded) | -$17,000+ (INM, GDTC, AMOD, OST) | Medium — entry criteria relaxation | Can backtest |
| Sizing gap (flat vs conviction) | ~50% of shared-ticker gap | Medium — scoring-based sizing | After exit fix |

**Total addressable gap in January: ~$300K+, but realistically the bot needs to capture 10-15% of Ross's P&L to be viable, which means targeting $40-60K/month.** The exit management fix alone, applied to the 5 shared tickers, could add $10-15K. Combined with killing MP (+$4K) and fixing Profile X blocks (+$5K), the bot could have been +$15-20K in January instead of -$1,531.

---

*This audit establishes the baseline for all subsequent development work. No code changes should be made without reference to these findings.*
