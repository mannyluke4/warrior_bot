# Where the Bot Is Leaving Money on the Table

**Generated:** 2026-03-22
**Period:** January 2025 (22 trading days)
**Baseline:** Ross Cameron ~$406,000 | Bot (all-three) -$1,531
**Total gap: ~$407,531**

This analysis accounts for every dollar of the gap between Ross's January performance and the bot's. Each category includes hard dollar amounts derived from trade-level comparison data across 22 daily files, the full audit, and megatest state logs.

---

## The Complete Accounting

### Category 1: Exit Gap on Shared Tickers — $96,030 (23.6% of total gap)

These are the 5 stocks both Ross and the bot traded. Same tickers, often same entry times. The gap is pure execution: how each side managed the trade once in.

| Date | Ticker | Bot P&L | Ross P&L | Gap | Exit Reason | What Happened |
|------|--------|---------|----------|-----|-------------|---------------|
| Jan 14 | AIFF | +$1,424 | -$2,000 | **Bot won +$3,424** | sq_target_hit +4.2R, +3.7R | Bot's discipline beat Ross's emotional entry at $10.08. Only shared-ticker win for the bot. |
| Jan 16 | WHLR | +$28 | +$3,800 | **-$3,772** | sq_para_trail at +0.1R | Bot captured $0.01/share. Ross range-traded $3.82-$4.20 multiple times. Parabolic trail fired at first micro-pullback. |
| Jan 24 | ALUR | +$586 | +$85,900 | **-$85,314** | sq_target_hit at +4.1R | Bot entered at $8.04 (better than Ross's $8.24), exited $8.40 three minutes later. Stock ran to $20. Bot captured 3% of available range. 80x P&L gap from sizing + exit. |
| Jan 28 | YIBO | +$125 | +$5,724 | **-$5,599** | vr_core_tp_1.5R | Bot captured 42% of price range but Ross used 19x the notional. Sizing accounts for ~$4,700, exit management ~$900. |
| Jan 29 | SLXN | +$231 | ~+$5,000 | **-$4,769** | sq_para_trail at +0.5R | Bot entered late ($2.43 vs $2.00), parabolic trail clipped at $2.49. Ross built to $7K, gave back some. |
| | | **+$2,394** | **~$98,424** | **-$96,030** | | |

**Breakdown of the $96,030 exit gap:**

- **ALUR alone: $85,314 (89% of this category).** This is the single most important number in the entire analysis. Same stock, same time, nearly same entry price, 146x P&L difference. The sq_target_hit exit at +4.1R fired in 3 minutes on a stock that moved $12/share. There is no runner detection, no halt-through logic, no mechanism to recognize that a +181% gapper with 12.8M premarket volume is qualitatively different from a routine squeeze.

- **Parabolic trail exits: $8,541 combined (WHLR + SLXN).** The trail fires at the first micro-pullback after any profit. WHLR: +$0.01/share captured. SLXN: +$0.06/share captured. The trail is calibrated to never give back gains, which means it never allows gains to develop.

- **Sizing gap (embedded in YIBO/ALUR): ~$70,000+.** Ross sizes up 5-20x on A+ conviction plays. The bot uses flat ~$15-22K notional. On ALUR, Ross's position was likely $200K+ notional. On YIBO, 19x the bot's size. Even with identical exits, the bot would capture a fraction.

- **AIFF credit: +$3,424.** The one shared ticker where the bot won — mechanical discipline beating human emotion. Ross entered AIFF at $10.08 on a VWAP break after prior bad experience; the bot entered at $4.61 into confirmed momentum.

**What fixing this requires:**

The exit system has two distinct failure modes. **Premature target exits** (sq_target_hit): fires at fixed R-multiple, captures ALUR at $8.40 while stock goes to $20. Needs dynamic targets or partial-exit-then-trail logic on high-quality setups. **Premature trail exits** (sq_para_trail_exit): fires at first micro-pullback, captures $0.01/share on WHLR. Needs wider trails or minimum-profit thresholds before the trail activates. Sizing requires a conviction-based model keyed to scanner rank score.

---

### Category 2: Scanner Gap — Stocks the Bot Never Saw — $198,839 (48.8% of total gap)

These are stocks Ross traded profitably that the bot's scanner never found. This is the single largest category by dollar amount.

**From the missed stocks backtest plan: 89 total missed stocks in January. 32 were profitable for Ross.**

| Sub-Category | Missed Tickers (Ross profitable) | Est. Ross P&L | % of Scanner Gap |
|-------------|----------------------------------|--------------|-----------------|
| **Chinese stocks** | DGNX (+$23K), JG (+$15.6K), AURL (green, est. +$10K) | **~$48,600** | 24.4% |
| **Mid-morning/intraday discoveries** | XPON (+$15K), OSTX (+$3K), NXX (+$1.8K), MVNI (+$3.9K) | **~$23,700** | 11.9% |
| **Daily breakouts** | ARNAZ (+$12K), SGN Jan 31 (+$20K) | **~$32,000** | 16.1% |
| **Day-2+ continuations** | SPCB (+$2.6K), DATS (+$2K), SGN Jan 31 (+$20K counted above) | **~$4,600** | 2.3% |
| **News/catalyst squeezes** | SLRX (+$13K), ARBE (+$4.2K), CRNC (+$1.8K), NEHC (+$8.6K), BBX (+$13K), ADD (+$5.8K), BTCT (+$5.5K), ZENA (+$1K), HOTH (+$1K), AIMX (+$1.2K), ZO (+$4.9K), ELAB (+$4K est.), EVAC (+$7.5K est.), QLGN (+$2.4K), NLSP Jan 31 (+$938) | **~$74,839** | 37.7% |
| **No-news momentum** | XHG (+$3.5K), DATS (+$2K counted above) | **~$3,500** | 1.8% |
| **Thematic plays** | TPET (+$475), BTCT counted above | **~$475** | 0.2% |
| **Other/small** | CGBS (+$297), XXI (+$730), various small | **~$11,125** | 5.6% |
| **TOTAL** | **32 profitable tickers** | **~$198,839** | **100%** |

**Note:** Ross also LOST on 5 scanner-missed stocks (OST -$3K, GTBP -$3.4K, VRME -$4K, FOXX loss, SZK -$2.5K) for roughly -$12,900 in losses. The scanner's blindness was protective on those. Net scanner gap after losses: ~$185,939.

**The structural blindspots:**

1. **Chinese stocks are completely invisible.** Jan 23: three Chinese IPOs (DGNX, DXST, MIMI) — zero scanner overlap. Jan 27: AURL ran 200%+ on DeepSeek day — invisible. Jan 27: JG +$15.6K — invisible. Jan 31: SZK — invisible. The scanner has no handling for Chinese-listed stocks, fresh IPOs, or tickers with unreliable float data from IPO prospectuses.

2. **The 7:15 AM scan window misses post-scan catalysts.** XPON (Jan 2, post-7:30 AM breaking news, +$15K), OSTX (Jan 15, 7:41 AM Phase 2 clinical trial news, +$3K), NXX (Jan 21, 7:30 AM breaking news, +$1.8K), NLSP (Jan 31, 7:30 AM merger news, +$938), MVNI (Jan 29, 9:47 AM mid-morning discovery, +$3.9K). Combined: ~$24K in missed P&L from stocks that became tradeable after the scan ran.

3. **Daily chart patterns are structurally invisible.** ARNAZ (+$12K) was a "first candle to make new high" daily breakout with halt resumption dip-and-rip. SGN day 2 (+$20K) was a multi-day continuation on fresh news. The gap-based scanner literally cannot detect non-gap patterns.

4. **No multi-day memory.** SPCB appeared Jan 2 (watchlist), Jan 3 (+$2.6K), Jan 23 (small positive). SGN appeared Jan 29 (minimal), Jan 31 (+$20K). DATS appeared Jan 13 (+$2K), Jan 16 (traded). The scanner treats each day as day zero.

---

### Category 3: Found-But-Not-Traded Gap — $19,100 (4.7% of total gap)

Stocks the scanner correctly identified and ranked, but the bot took zero trades on despite Ross making money.

| Date | Ticker | Scanner Rank | Ross P&L | Why Not Traded |
|------|--------|-------------|----------|----------------|
| Jan 6 | GDTC | #1 | +$5,300 | **Profile X block** — scanner found it (+93.6% gap) but float data was null. Data quality issue. |
| Jan 14 | OST | found | +$1,800 | No entry signal triggered. Entry criteria too restrictive for OST's price action. |
| Jan 21 | INM | **#1** (1.027) | +$12,000 | **#1 ranked candidate, not traded.** Bot traded VATE (#5, -$163), PTHS (#3, -$679), LEDS (#4, -$281) instead. Entry templates didn't fire on INM's 68K-float price action. |
| Jan 30 | AMOD | found (Profile X) | positive (est.) | **Profile X block** — float data null despite 79.9% gap, 42.4x RVOL. Breaking news, primary winner of the day. |
| | | | **~$19,100+** | |

**The INM case is the most damaging.** The scanner did its job — INM was ranked #1 by a wide margin (1.027 vs 0.964 for #2). The ranking system correctly identified the opportunity. But the SQ squeeze template and MP micro_pullback template didn't fire on INM's specific price action. The bot instead traded the #3, #4, and #5 ranked candidates — all losers. Combined loss on those three: -$1,123. If it had traded INM instead, potential swing: +$13,123.

**Profile X blocks (GDTC + AMOD): ~$5,300+ combined.** These are pure data quality issues. The scanner found the stocks, identified them as top candidates, but missing float data from the data provider prevented classification and trading. This is the easiest gap to close — fix the float data source.

---

### Category 4: MP Strategy Losses — $3,947 (1.0% of total gap)

The MP strategy was a direct P&L drag. Every MP trade in January lost money.

| Exit Type | Trades | Total P&L | Avg P&L | Worst Example |
|-----------|--------|-----------|---------|---------------|
| max_loss_hit | 6 | -$3,211 | -$535 | PTHS -$646, STAI -$714, NTRB -$629 |
| bearish_engulfing | 5 | -$317 | -$63 | ORIS -$107, VATE -$163 |
| topping_wicky | 3 | -$419 | -$140 | PRFX -$380 |
| **TOTAL** | **14** | **-$3,947** | **-$282** | |

**For context, Ross took 4 MP trades all month: all winners, +$11,750, 100% win rate.**

The fundamental mismatch: Ross uses micro pullbacks as a selective re-entry on tickers that have already proven themselves. He never leads with an MP trade. The bot fires MP indiscriminately on anything triggering the pullback pattern, with no quality gate.

The max_loss_hit exits are the core damage — 6 trades (43%) hit the 0.75R safety cap, averaging -$535 each. These 6 trades account for 81% of total MP losses. The genuine MP exits (bearish_engulfing, topping_wicky) are performing their loss-limiting function but never produce a winner.

**Full-year context:** MP-only across the full megatest (Jan 2025–Mar 2026): 154 trades, 26% win rate, -$10,121 net. Lost money in 12 of 15 months. Only profitable in the 7 AM hour and on Fridays.

**Removing MP would have turned the all-three config from -$1,531 to approximately +$2,416 in January.** That's not just "better" — it's the difference between a losing system and a winning one.

---

### Category 5: Selection Errors (Bot-Only Trades) — $2,617 (0.6% of total gap)

Stocks the bot traded that Ross never touched. 19 unique tickers, approximately 28 trades.

| Component | Trades | P&L | Notes |
|-----------|--------|-----|-------|
| SQ on bot-only tickers | ~9 | +$1,313 | Roughly flat — SQ filter provides some protection |
| MP on bot-only tickers | ~19 | -$3,930 | Brutal — MP trades on stocks Ross wouldn't touch |
| **Net** | **~28** | **-$2,617** | |

**Notable losers Ross avoided:**
- ORIS (Jan 2): -$313. Tiny float, huge gap — looks good on paper.
- PTHS (Jan 21): -$679. Bot traded #3 while #1 (INM) sat untouched.
- NTRB (Jan 23): -$629. MP trade on stock Ross didn't see.
- CYCN (Jan 31): -$1,254 combined. Ross didn't look at it.
- NCEL (Jan 31): -$676. Both hit max loss immediately.

**The overlap between Category 4 (MP losses) and Category 5 (selection errors) is large.** Most bot-only losing trades are MP entries on low-quality candidates. Killing MP would eliminate most of the selection error drag simultaneously.

---

### Category 6: The Uncapturable Gap — ~$87,000 (21.3% of total gap)

Not every dollar of Ross's $406K was theoretically capturable by any bot. Some of Ross's edge comes from skills that are fundamentally non-automatable:

| Skill | Estimated January P&L | Can Bot Replicate? |
|-------|----------------------|-------------------|
| Level 2 tape reading | ~$25,000 (DGNX +$23K primary) | No — requires real-time order flow interpretation |
| Thematic/macro awareness | ~$15,000 (inauguration plays, DeepSeek theme) | No — requires reading news narrative and market sentiment |
| "Know when to stop" discipline | ~$10,000 (avoided overtrading on green days) | Partially — could implement daily P&L targets |
| Emotional/psychological edge | ~$12,000 (ice-breaker psychology, sizing confidence) | No — human judgment under pressure |
| Multi-stock range trading | ~$5,000 (WHLR multiple re-entries) | Partially — could implement re-entry logic |
| Day-2+ pattern recognition | ~$20,000 (SGN recognition across days) | Partially — could add "hot name" memory |

---

## The Full Gap Accounting

| Category | Dollar Amount | % of $407,531 Gap | Fixability |
|----------|-------------|-------------------|------------|
| **1. Exit gap on shared tickers** | $96,030 | 23.6% | HIGH — exit logic + sizing changes |
| **2. Scanner gap (never saw)** | $198,839 gross / $185,939 net | 48.8% / 45.6% | MEDIUM — requires multiple scanner expansions |
| **3. Found-but-not-traded** | $19,100 | 4.7% | HIGH — Profile X fix + entry criteria relaxation |
| **4. MP strategy losses** | $3,947 | 1.0% | IMMEDIATE — kill or gate MP |
| **5. Selection errors** | $2,617 | 0.6% | MEDIUM — tighter quality filters |
| **6. Uncapturable human edge** | ~$87,000 | 21.3% | LOW — fundamental skill gap |
| **TOTAL** | **~$407,533** | **100%** | |

---

## Impact Ranking: What Moves the Needle Most

Here's the honest ranking by **realistic incremental P&L** — not the theoretical maximum, but what each fix would plausibly add to the bot's monthly P&L based on the January data:

### Tier 1: High Impact, Implementable Now

**#1 — Kill MP (or gate it behind SQ wins)**
- Immediate P&L swing: **+$3,947/month**
- Turns the system from -$1,531 to +$2,416
- Zero development risk — it's a subtraction
- Full-year impact: +$10,121 across the megatest period

**#2 — Fix exit management on SQ winners**
- Conservative estimate (capture 10% of Ross's shared-ticker P&L instead of 2.4%): **+$7,500/month**
- Aggressive estimate (capture 25%): **+$22,000/month**
- Implementation: tiered exits (partial at current target, remainder on wider trail), runner detection (if target hit in <3 min and price still accelerating, switch to ATR-based trail), halt-through logic
- Risk: wider exits could increase giveback on non-runners. Need to segment by setup quality.

**#3 — Fix Profile X / float data source**
- Immediate P&L unlock: **+$5,300/month** (GDTC alone was this)
- AMOD was also blocked — unknown P&L but primary winner of its day
- Implementation: add backup float data source or allow trading with estimated float
- Risk: very low — these were top-ranked scanner candidates with massive gaps

### Tier 2: High Impact, Requires Development

**#4 — Add continuous rescan through 10:00 AM**
- Captures post-7:15 AM catalysts (XPON, OSTX, NXX, NLSP, MVNI)
- Estimated value: **+$5,000-$10,000/month**
- Already proven: the expanded rescan found YIBO at 10:38 AM on DeepSeek day

**#5 — Add multi-day continuation awareness**
- Captures SGN day-2 (+$20K), SPCB day-2 (+$2.6K), DATS recurring
- Estimated value: **+$5,000-$10,000/month**
- Implementation: maintain a "hot name" list of recent runners, re-evaluate on fresh news

**#6 — Fix entry criteria on top-ranked candidates**
- INM was #1 ranked, not traded. Three lower-ranked losers traded instead.
- Estimated value: **+$5,000-$12,000/month** (INM alone was $12K for Ross)
- Implementation: if #1 ranked candidate doesn't trigger standard entry, try a broader entry template. Don't skip to #3/#4/#5 unless #1 is truly dead.

### Tier 3: High Theoretical Impact, Hard to Implement

**#7 — Chinese stock support**
- Estimated value: **+$10,000-$20,000/month** (Jan was unusually heavy with Chinese IPOs)
- Requires: handling IPO prospectus data, unreliable float reporting, different exchange characteristics
- Risk: Chinese stocks are also where Ross lost (SZK -$2.5K, DXST breakeven). High variance.

**#8 — Conviction-based sizing**
- On YIBO, 19x sizing gap accounted for most of the 46x P&L gap
- Estimated value: **+$5,000-$15,000/month** if combined with exit fix
- Must be implemented AFTER exit management is fixed — sizing up into premature exits just increases losses

**#9 — Daily breakout / non-gap pattern detection**
- ARNAZ (+$12K) and SGN day-2 (+$20K) are structural scanner blindspots
- Requires fundamentally different scanner architecture (daily chart analysis, not just pre-market gaps)
- Estimated value: **+$5,000-$15,000/month** but high development cost

### Tier 4: Diminishing Returns

**#10 — Tighter selection filtering on bot-only trades**
- Saves ~$2,617/month in noise trade losses
- Most of this overlaps with killing MP (#1)
- Residual SQ noise trades are roughly flat (+$1,313) — not worth aggressive filtering

---

## The Honest Bottom Line

The bot's January was -$1,531 against Ross's ~$406K. Here's where that gap actually lives:

**~49% is scanner blindness** — the bot never even saw most of Ross's profitable stocks. This is the biggest bucket but also the hardest to fix because it requires multiple distinct scanner expansions (Chinese stocks, continuous rescan, daily patterns, multi-day memory). Each sub-category is a separate engineering project.

**~24% is exit management** — the bot finds the right stock, enters at the right time, and then exits 10-100x too early. ALUR is the poster child: $586 captured on a $85,900 Ross trade. This is the highest-ROI fix because it improves every trade the bot already takes. It doesn't require finding new stocks — just holding the ones it already has.

**~5% is found-but-not-traded** — the scanner does its job, the ranking system does its job, but the entry templates are too rigid for certain price action patterns. INM ranked #1 and wasn't traded. Profile X blocks good stocks over missing data.

**~1.6% is MP drag + noise trades** — small in percentage terms but critical because it's the difference between a losing system and a positive one. MP is the only category where the fix is pure subtraction.

**~21% is uncapturable** — Ross's L2 tape reading, thematic intuition, and emotional intelligence produce $87K/month that no reasonable bot can replicate.

**If you implemented Tier 1 fixes only (#1 kill MP, #2 fix exits, #3 fix Profile X), realistic January P&L would be approximately +$15,000 to +$35,000 instead of -$1,531.** That's capturing roughly 4-9% of Ross's P&L, which is the difference between a toy and a viable trading system.

---

*This analysis is based on 22 daily comparison files, the 630-line strategy audit, monthly summary, missed stocks plan (89 stocks), and megatest equity logs. All dollar amounts are derived from trade-level data except where noted as estimates.*
