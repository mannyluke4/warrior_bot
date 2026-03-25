# Ross Cameron vs Bot — January 2025 Cross-Reference

## Top-Line Comparison

| Metric | Ross | Bot SQ | Bot MP | Bot All-Three |
|---|---|---|---|---|
| Trades | 88+ | 28 | 16 | 42 |
| P&L | **~$406,000** | **+$3,175** | **-$5,144** | **-$1,531** |
| Win Rate | ~78% | 61% | 0% | 40% |
| Unique Tickers | 68 | 15 | 15 | 23 |
| Avg P&L/Trade | +$4,614 | +$113 | -$322 | -$36 |

**JANUARY 2025 COMPLETE (22 trading days).** Ross made ~$406K. The bot (all-three) lost -$1,531. The gap is ~265x. SQ was the only net-positive strategy at +$3,175. MP was catastrophic at -$5,144 (0% win rate for the entire month).

---

## Ticker Overlap

**Both traded (5 tickers):** AIFF, ALUR, SLXN, WHLR, YIBO/YWBO

**Ross only — bot missed (69 tickers):** ADD, AEI, AMOD, ANYC, ARB, ARBE, ARNAZ, ARNZ, AURL, BACK, BBX, BLBX, BZI, CRNC, CYCC, DATS, DGNX, DXF, DXST, ESHA, FOXX, GD, GTBP, HOO, HOTH, INBS, INM, JFB, JG, KZIA, MFI, MII, MIMI, MLGO, MSAI, MVNI, NEHC, NITO, NLSP, NUKK, NXX, OST, OSTX, PAVS, PHIO, QLGN, SGN, SLRX, SPCB, SPRC, SZK, TGL, TPET, TRIO, VNC, VNCE, VRME, XHG, XPON, XXI, ZENA, ZEO

**Bot only — Ross didn't trade (19 tickers):** ATPC, BKYI, CYCN, IMDX, KAPA, LEDS, MYSE, NCEL, NTRB, NVNI, ORIS, PRFX, PTHS, SILO, STAI, VATE, VMAR

**Overlap rate:** 5 of Ross's 68+ tickers (7.4%). The bot and Ross traded almost entirely different stocks all month. **JANUARY FINAL.**

---

## Head-to-Head on Shared Tickers

| Date | Ticker | Ross P&L | Bot Setup | Bot P&L | Notes |
|---|---|---|---|---|---|
| Jan 14 | AIFF | -$2,000 | SQ: +$520, +$921; MP: -$17 | +$1,424 | Bot actually won this one. Ross lost on a dip buy. |
| Jan 16 | WHLR | +$3,800 | SQ: +$28 | +$28 | Bot found it, captured almost nothing (0.1R). |
| Jan 24 | ALUR | +$85,900 | SQ: +$506, -$9, +$89 | +$586 | Bot captured 0.7% of Ross's gain. Sizing is the story. |
| Jan 28 | YIBO/YWBO | +$5,724 | VR: +$125 (all-three) | +$125 | Bot found it and traded it. 46x P&L gap — sizing (19x) + exit (42% of range). |
| Jan 29 | SLXN | net positive (est. ~$5K) | SQ: +$231, All-Three: +$211 | +$231 | Both traded, both won. Ross built to $7K, gave back, lost $2K on re-entry. Bot took 1 clean trade. |

**Key insight on ALUR:** Ross sized aggressively on his A+ conviction play (+$47,000 on "ALRN" — confirmed as ALUR). The bot's fixed-size SQ entries on the same stock netted $586. Same ticker, same entry time (~7:01 AM), nearly same entry price ($8.04 bot vs ~$8.24 Ross) — 80x P&L difference purely from sizing and exit management. The bot exited at $8.40 (sq_target_hit); Ross rode it to $20. This is the single most important trade comparison in the entire series.

---

## Scanner Coverage of Ross's Big Winners ($10K+)

| Date | Ticker | Ross P&L | Scanner Found? | Bot Traded? |
|---|---|---|---|---|
| Jan 2 | XPON | +$15,000 | NO | NO |
| Jan 9 | ESHA | +$15,556 | NO | NO |
| Jan 9 | INBS | +$18,444 | NO | NO |
| Jan 21 | INM | +$12,000 | YES | NO (selected but no entry) |
| Jan 23 | DGNX | +$22,997 | NO | NO |
| Jan 24 | ALUR | +$85,900 | YES | YES (+$586) |
| Jan 27 | JG | +$15,558 | NO | NO |
| Jan 28 | ARNZ | +$12,234 | NO | NO |
| Jan 29 | SGN | +$13,000 | NO | NO |
| Jan 30 | AMOD | positive (amount unknown) | YES (Profile X — found but filtered, no float data) | NO (Profile X blocked trading) |
| Jan 31 | SGN | +$20,000 | NO | NO |

**Scanner hit rate on Ross's big winners: 3 of 11 (27%). JANUARY FINAL.** The scanner missed 8 of Ross's 11 biggest plays. Of the 3 it found, only ALUR actually generated a bot trade (+$586 on a stock where Ross made +$85,900).

---

## Scanner Overlap by Day

Out of 22 trading days (Jan 2-31, full month), the scanner overlapped with at least one Ross ticker on **14 days (64%)**. Total scanner-Ross ticker overlaps across Jan: **15 tickers** out of Ross's 70+ unique tickers (21%). Jan 28-30 formed a three-day overlap streak — the longest in January: YIBO (+92.2% gap, Jan 28, bot +$125), SLXN (+57.8% gap, Jan 29, bot +$231), AMOD (+79.9% gap, Jan 30, bot blocked by Profile X). Two winning bot trades followed by a blocked trade due to missing float data. The scanner works best on massive gappers with huge PM volume (SLXN: +57.8%, 30.9M PM vol; YIBO: +92.2%, 15.1M PM vol; ALUR: +181%, 12.8M PM vol; AMOD: +79.9%, 6.3M PM vol).

Tickers the scanner correctly identified that Ross also traded: AEI, AIFF, ALUR, AMOD, INM, MSAI, OST (x3: Jan 2, 14, 24), SLXN (Jan 29), WHLR, YIBO, ZEO

---

## MP Strategy: Ross vs Bot

Ross took **4 MP trades** all month — all winners, +$11,750, 100% win rate. He's extremely selective with micro pullbacks: only taking them on tickers already proven with volume and momentum.

The bot took **14 MP trades** in January — **all losers**, -$3,947, 0% win rate. Every single MP trade lost money. Exit reasons: bearish_engulfing_exit (6), topping_wicky_exit (3), max_loss_hit (5).

**The bot's MP strategy is anti-correlated with Ross's approach.** Ross uses MP sparingly as a secondary re-entry on A+ names. The bot fires MP indiscriminately on anything that triggers, with no quality filter.

---

## SQ Strategy Comparison

Ross's squeeze/breakout: 37 trades, +$230,111, avg +$6,219/trade
Bot's SQ: 22 trades, +$3,599, avg +$164/trade

Ross's SQ win rate is higher (likely >75%) and his winners are 10-50x larger due to:
1. **Conviction sizing** — Ross loads up on A+ setups (ALUR $85K single trade)
2. **Better exit management** — Ross rides winners; bot's parabolic trail exits at +0.1R to +0.5R frequently
3. **Stock selection** — Ross's 5-pillar filter finds the tickers that actually move big

The bot's SQ strategy is net positive (+$3,599) which validates the setup concept, but the execution gap is massive.

---

## Actionable Takeaways

### 1. Scanner Gap is the #1 Problem
The bot's scanner only found 10 of Ross's 55+ tickers (18%). It missed XPON, ESHA, INBS, DGNX, JG, ARNZ, SGN, AURL — all $10K+ winners (AURL P&L unknown but 200%+ runner). The scanner needs to cast a wider net. Chinese stocks are a confirmed systematic blindspot (DGNX Jan 23, AURL/JG Jan 27).

### 2. Kill or Radically Rework MP
Bot MP went 0-for-14 in January (-$3,947). Ross's 4 MP trades were all winners because he only uses MP as a selective re-entry, not a standalone strategy. Consider: MP only on tickers where a prior SQ trade already won.

### 3. Exit Management Bleeds Edge
Bot SQ repeatedly exited at +0.1R to +0.5R via parabolic trail. On ALUR, the bot made $586 where Ross made $85,900. The trail stop is cutting winners too early. Consider wider trails or tiered exits on high-conviction setups.

### 4. Sizing is a Feature, Not a Bug
Ross's conviction-based sizing is a core part of his edge. The bot uses fixed notional. Even without variable sizing, the bot could scale position size to the setup score (which is already computed).

### 5. Bot's Noise Trades
17 tickers the bot traded that Ross didn't touch. 28 trades, combined P&L -$2,617 (9W/19L). SQ portion was roughly flat (+$1,313) but MP portion was brutal (-$3,930). These are candidates for tighter filtering — the bot is entering names that a skilled trader wouldn't touch.

---

## Daily Notes

### Note on Jan 22 — Complete Scanner Whiff
The bot's scanner found only 1 ticker on Jan 22: GELS (+27.6% gap, 3.72M PM volume, 5.46M float, Profile B). GELS generated 0 armed signals, 0 entry signals, and 0 trades across all strategies (24,729 ticks, nothing). Meanwhile Ross made +$21,672 on NEHC (+$8,636, energy infrastructure squeeze breakout, 30K shares $4.58→$5.17) and BBX (~+$13,036, $2M financing + merger news, 2M float, $3.10→$3.80 multiple trades). Zero scanner overlap — NEHC and BBX were completely invisible. Worst scanner overlap day in the series. Bot's Jan 22: $0 P&L (no trades). Pure scanner gap — no selection or execution issues because the bot never had the right stocks.

### Note on Jan 24 — Best Overlap Day, Worst Exit Management Day
The bot's scanner found 5 tickers on Jan 24: ALUR (+181.1% gap, 12.8M PM vol, rank #1), NVNI (+59.0%, rank #3), ATXI (+12.0%, rank #2), OST (+57.0%, rank #4), PRFX (+12.2%, rank #5). Scanner overlapped on 2 of 4 Ross tickers (50%) — ALUR and OST — the best overlap since Jan 14. The bot traded ALUR (SQ: 3 trades, +$586), NVNI (SQ: 1 trade, +$42), and PRFX (MP: 1 trade, -$385). Combined bot P&L: +$201. Ross made +$81,400 — his biggest day of 2025. The ALUR comparison is devastating: bot entered at $8.04 at 7:01 AM (Ross entered ~$8.24 after 7:01 AM), stock ran to $20, bot exited at $8.40 via sq_target_hit for +$506. Ross made +$47,000 on the same stock. 80x P&L gap on identical timing. OST: scanner found it, bot correctly didn't trade it — Ross lost -$6K on OST (FOMO). Scanner missed EVAC (biotech sympathy play, no news, $8→$11) and ELAB (squeeze pullback, ~$3.60→$5.00). This day proves the exit management problem is now bigger than the scanner problem: the bot was in the right stock at the right time and captured 0.7% of Ross's gain. Ross's January MTD: ~$280,000.

### Note on Jan 27 — DeepSeek Day, Complete Scanner Whiff on Chinese AI
The bot's scanner found 4 tickers on Jan 27: TVGN (+52.5% gap, 5.65M PM vol, 0.88M float), ICCT (+19.8%, 3.40M PM vol, 4.45M float), GMHS (+19.9%, 220K PM vol, 3.89M float), BCDA (+16.9%, 125K PM vol, 7.2M float). None were Chinese AI stocks. The v2 megatest generated **0 trades** across all strategies. Meanwhile, AURL (Aurora Limited, Chinese AI) ran $8→$20+ (200%+ move) on DeepSeek AI news — the biggest tech catalyst of the year — and was completely invisible to the scanner. JG (Aurora Mobile) also ran for +$15,558 (per broker data). Ross traded AURL using VWAP + dip/bounce structure, explicitly passing on large-cap shorts (NVDA -17%). Recap described as a green day but specific P&L not stated. The expanded continuous rescan found YIBO (Chinese AI) at 10:38 AM for 4 trades / -$478 (gates off), proving Chinese AI stocks were discoverable but not by the 7:15 AM scan. This is the second complete whiff in 6 trading days (Jan 22) and the second major Chinese stock miss in a week (Jan 23 IPOs). Chinese stocks are now a confirmed systematic scanner blindspot.

### Note on Jan 28 — YIBO/YWBO Overlap, ARNAZ Daily Breakout Miss
The bot's scanner found only 2 tickers on Jan 28: YIBO (+92.2% gap, 15.14M PM vol, 7.13M float, Profile B) and SNTG (+14.7% gap, 156K PM vol, 1.06M float, Profile A). YIBO is the same stock Ross traded as "YWBO" — Chinese AI continuation from DeepSeek day 1 (Jan 27). The all-three variant traded YIBO via VR (VWAP Reclaim) strategy: entry $5.79, exit $6.12 (vr_core_tp_1.5R), +$125. SQ, MP, and MP+SQ variants all generated 0 trades. Ross made +$21,000+ across 5 tickers: YWBO/YIBO (+$5,724, VWAP reclaim at $5.57→$6.36), NLSP (+$165, biotech pop), JFB (+$600, DeepSeek integration scalp), QLGN (+$2,400, biotech low float $4.75→$5.51), and ARNAZ (+$12,000, daily breakout "first candle new high" $7.50→$14.00 with halt resumption dip-and-rip). Scanner overlap: 1 of 5 Ross tickers (20%). On the shared ticker (YIBO), bot made +$125 vs Ross's +$5,724 — a 46x gap from sizing (19x) and exit management (42% of range captured). ARNAZ is a new category of scanner miss: daily chart breakout patterns are structurally invisible to the gap-based scanner. January MTD: Ross ~$325,000, bot ~-$300.

### Note on Jan 29 — SLXN Overlap, Back-to-Back Bot Wins, MVNI Mid-Morning Miss
The bot's scanner found only 1 ticker on Jan 29: SLXN (+57.8% gap, 30.9M PM vol, 3.0M float, Profile A). Textbook scanner candidate. All SQ-containing variants traded SLXN profitably: all-three +$211, SQ +$231, MP+SQ +$212. MP alone: 0 trades (0 armed, 0 signals despite Profile A). Ross also traded SLXN as his ice breaker — entry at $2.00 breakout, built to ~$7K, gave some back, then lost ~$2K on re-entry. Net positive est. ~$5K. Scanner missed 3 of 4 Ross tickers: VNCE (momentum squeeze $1.73→$3.40, positive), MVNI (+$3,900, day's anchor — third entry at 9:47 AM from $4.75→$7.50), SGN (minimal). This is the second consecutive day of scanner overlap and bot profitability (Jan 28: YIBO +$125, Jan 29: SLXN +$231) — the first back-to-back winning streak in the series. MVNI is a mid-morning discovery miss: Ross's $3,900 anchor came 2.5 hours after open, outside scanner's pre-market window. Ross total: +$24,000. January MTD: ~$350,000.

### Note on Jan 30 — AMOD Profile X Block, STAI MP Loss, Three-Day Overlap Streak
The bot's scanner found 3 tickers on Jan 30: AMOD (+79.9% gap, 6.3M PM vol, 42.4x RVOL, Profile X — no float data), BNZI (+42.0% gap, 9.0M PM vol, 2.34M float, Profile A), and STAI (+34.0% gap, 8.6M PM vol, 1.0M float, Profile A). AMOD was Ross's primary winner (breaking news, pre-market cushion, post-open squeeze at 9:35-9:40 AM) but the bot couldn't trade it because float data was null (Profile X). The bot selected BNZI and STAI instead. The only trade was STAI via micro pullback: entry $2.13 at 09:07, exit $2.02 at 09:08, max_loss_hit, -$714 (all-three) / -$639 (MP) / -$717 (MP+SQ). SQ correctly generated 0 trades. Ross didn't trade STAI or BNZI. Ross also traded FOXX/FOXO (loss, no news, late-session "make it back" trade) — scanner correctly didn't find this non-gapper. This is the second Profile X blocking incident after GDTC (Jan 6) and extends the scanner overlap streak to 3 consecutive days (Jan 28-30) — the longest in January. Ross's day was positive (amount unknown), building toward $350K+ MTD. The bot lost money trading a stock Ross ignored while the stock Ross actually traded was blocked by a data gap.

### Note on Jan 31 — FINAL DAY, Zero Overlap, SGN Multi-Day Miss
The bot's scanner found 3 tickers on Jan 31: CYCN (+19% gap, 2.3M PM vol, 2.7M float, Profile A), NCEL (+36% gap, 13.9M PM vol, 2.1M float, Profile A), and IMDX (+14% gap, 105K PM vol, 7.8M float, Profile B). None overlapped with Ross's 3 tickers (SGN, NLSP, SZK). All-three: CYCN -$662 + NCEL -$676 = **-$1,338**, equity $29,135. SQ: CYCN -$579, equity $33,599. MP: CYCN -$592 + NCEL -$605 = **-$1,197**, equity $26,053. Ross made +$26,265: SGN (+$20K+ est., Army Bowl sponsorship news at 7:00 AM, recurring from Jan 29), NLSP (net +$938, merger news at 7:30 AM), SZK (-$2,500, reverse split Chinese stock trap). SGN highlights a new miss pattern: multi-day catalyst continuation. Ross recognized SGN from Jan 29 and sized up on fresh news at 7:00 AM. The scanner treats each day independently and can't detect day-2+ continuations. NLSP's 7:30 AM catalyst was after the 7:15 AM scan window — second time in 3 days. The Jan 28-30 overlap streak is broken. **January 2025 complete: Ross ~$406,000 vs Bot all-three -$1,531 (equity $29,135 from $30K start).**

### Note on Jan 23 — Chinese IPO Day, Another Complete Whiff
The bot's scanner found 4 tickers on Jan 23: VNCE (vol=6,453,109), LSH (vol=1,743,876), HKPD (vol=1,516,830), NTRB (vol=550,781). The bot traded only VNCE — 3 SQ trades for -$76 net (+$55, -$22, -$109). Meanwhile Ross made ~$40,000+ dominated by DGNX (+$22,997, Chinese IPO day 2, entered $15.55 via Level 2 tape reading, rode squeeze to $20+). Ross also traded DXST (~breakeven, second Chinese IPO chase to $14, lost $3K on failed dip), MIMI (~breakeven, third Chinese IPO near flush), and SPCB (small positive, debt restructuring news). Zero scanner overlap — all 3 Chinese IPOs and SPCB were completely invisible to the scanner. DWTX (biotech, $3.50→$7+) was missed by both Ross and the bot — notably, the bot's scanner had DWTX on Jan 21 (rank #2, +40.59% gap) but did NOT pick it up on Jan 23. This is the 4th consecutive trading day with zero or near-zero scanner overlap (Jan 17, 21, 22, 23). New pattern: Chinese IPOs are a complete scanner blindspot — 3 missed in one day. Ross's DGNX entry was based on Level 2 tape reading (large bidder at $15.55), a discretionary skill fundamentally outside the bot's capability.
