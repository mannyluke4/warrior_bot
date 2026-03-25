---
# Missed Stocks Backtest Plan

## Purpose
Collect all stocks Ross traded that the bot's scanner missed. Once we have a comprehensive list, backtest each one starting from the time Ross first noticed them (scanner alert or entry time) to see how the bot's strategies would have performed if the scanner had found them.

## Methodology
- For each missed stock: note the date, ticker, time Ross noticed it, Ross's P&L, setup type
- Backtest using simulate.py in --ticks mode starting from Ross's discovery time
- Compare bot's hypothetical result vs Ross's actual result
- This tells us: "If the scanner was fixed, how much would we capture?"

## Missed Stocks Log

### January 2025

| Date | Ticker | Time Noticed | Ross P&L | Setup Type | Ross Notes | Bot Scanner Had It? | Backtest Result |
|------|--------|-------------|----------|------------|------------|-------------------|-----------------|
| 2025-01-02 | XPON | ~post-7:30 AM | +$15,000 | news squeeze | 100% squeeze on breaking news, low float, ~30 min hold | No | PENDING |
| 2025-01-02 | OST | pre-7:00 AM | -$3,000 | momentum (no news) | Low float ~700K, no catalyst, two losing trades | No | PENDING |
| 2025-01-02 | SPCB | pre-market | not traded | watchlist only | On scanner but not traded | No | PENDING |
| 2025-01-02 | HOO | pre-market | not traded | watchlist only | On scanner but not traded | No | PENDING |
| 2025-01-03 | CRNC | ~8:00 AM | +$1,800 | squeeze/breakout (news) | Nvidia collaboration news, entered ~$9.60 for $10 break, max 4K shares | No | PENDING |
| 2025-01-03 | SPCB | pre-market | +$2,600 net | continuation/breakout (day 2) | Continuation from Jan 2, curl through $9, stair-step breakout, max 6K shares | No | PENDING |
| 2025-01-03 | NTO | pre-market | ~scratch (+$280 net) | momentum (news) | 20K shares for 2 cents, fee drag lesson, stock under $2 | No | PENDING |
| 2025-01-03 | TGL | pre-market | not traded | passed on | Up 400% but 30-cent total range too small | No | PENDING |
| 2025-01-03 | MFI | pre-market | not traded | passed on | Too cheap, tight range | No | PENDING |
| 2025-01-03 | CYCC | pre-market | not traded | passed on | Too cheap, tight range | No | PENDING |
| 2025-01-06 | RHE | ~8:00 AM | small net gain | dip-buy/pop-sell | $1.50→$7 in ~2 min, pure momentum, stopped when double top + below VWAP | No | PENDING |
| 2025-01-06 | ARBE | ~8:00 AM | +$4,200 | news squeeze | Nvidia collaboration news, entered $33.75 on 10s chart, squeezed to $50, 27M float | No | PENDING |
| 2025-01-06 | CRNC | pre-market | not traded (passed) | continuation | Continuation from Friday, went to $27 but Ross didn't re-enter | No | PENDING |
| 2025-01-06 | FUBO | pre-market | not traded (passed) | passed on | Disney news but 300M float too high | No | PENDING |
| 2025-01-06 | BOXL | pre-market | not traded (passed) | passed on | Halt levels too close, choppy | No | PENDING |
| 2025-01-06 | POI | pre-market | not traded (passed) | passed on | Too cheap | No | PENDING |
| 2025-01-06 | SPRC | pre-market | not traded (passed) | passed on | Too cheap | No | PENDING |
| 2025-01-07 | ZENA | 7:30 AM | +$998 | news squeeze (starter→add→add) | Breaking news, 8M float, scaled 1K→2K→3K shares, $8.33→$9.00 | No | PENDING |
| 2025-01-07 | CGBS | 7:36 AM | +$296.77 | low-float squeeze | 1.7M float, squeeze to $6.25→curl→$6.50, volume divergence warning | No | PENDING |
| 2025-01-07 | HOTH | 8:25 AM | +$1,000 | momentum first-pop | Up 300%, 30K shares, one trade only, didn't trust from prior experience | No | PENDING |
| 2025-01-07 | AMVS | pre-market | ~break-even | half-dollar breakout | 9.3M float, first trade huge win $6.50→$8.50, gave it all back on 2 re-entries | No | PENDING |
| 2025-01-07 | SPRC | pre-market | not traded (passed) | passed on | Too far below prior day's highs | No | PENDING |
| 2025-01-07 | IMRX | pre-market | not traded (missed) | big miss | $2.50→$5.70, 16M float, "risk check failed" blocked entry | No | PENDING |

| 2025-01-10 | AIFF | 8:00 AM | +$3,100 | momentum squeeze | Rapid $3→$6.24, 4 trades: main entry $5.23, break-even re-entry, 2 dip buys at $4.00, 10s chart entries | No | PENDING |
| 2025-01-10 | ARBE | 8:32 AM | small profit | news scalp | Breaking news, quick $2.75→$3.10 scalp, same stock from Jan 6 | No | PENDING |
| 2025-01-10 | XHG | mid-morning | +$3,500 | no-news continuation | NO NEWS, pure momentum, 5m+1m aligned pullback, 20K share positions chipping 5-8 cents | No | PENDING |
| 2025-01-10 | DTIL | pre-market | not traded (passed) | passed on | Gapped up, pulled back, re-squeezed — didn't trust it | No | PENDING |
| 2025-01-10 | DATS | pre-market | not traded (passed) | passed on | Secondary offering history, $3→$7 but didn't trust it | No | PENDING |

| 2025-01-13 | GTBP | ~7:00 AM | -$3,400 | momentum (too aggressive) | Jumped in too aggressive, flushed immediately, set defensive tone | No | PENDING |
| 2025-01-13 | DATS | pre-market | +$2,000 | no-news continuation pullback | Small size recovery mode, no news catalyst | No | PENDING |
| 2025-01-13 | XXI | pre-market | small profit | momentum scalp (news) | News but choppy action | No | PENDING |
| 2025-01-13 | PHIO | pre-market | net small profit | news squeeze (missed main) | HUGE MISS — 460% squeeze to $9.50, 168x RVOL, 514K float, all 5 criteria met, spooked by shelf registration | No | PENDING |
| 2025-01-13 | SLRX | pre-market | +$13K (bulk) | merger news stair-step breakout | 1.2M float, 1200x RVOL, $1.50→$5 stair-step, biggest winner of the day | No | PENDING |
| 2025-01-14 | ADD | 6:45 AM | +$5,810 | VWAP reclaim + curl off lows | News + sub-1M float + 20M volume, multiple trades targeting $3, stalled just under | No | PENDING |
| 2025-01-14 | NMHI | 7:00 AM | small profit | pre-market high breakout | Leading gapper, 114M volume, farm machinery, $3.18→$3.40 | No | PENDING |
| 2025-01-14 | VRME | 8:15 AM | -$4,000 | VWAP break (failed) | VWAP break entry, immediate violent rejection, emotional cascade from AIFF loss | No | PENDING |
| 2025-01-14 | ERNA | pre-market | not traded (scanner only) | watchlist only | On Ross's scanner but not traded | No | PENDING |
| 2025-01-15 | OSTX | 7:41 AM | ~+$3,000+ | news squeeze | Phase 2 clinical trial news, $4→$8.50 spike, 17M float, 10s chart micro pullback entry | No | PENDING |
| 2025-01-15 | EVAX | pre-market | small profit | momentum scalp | Partial fill at $4.50, pop to $5.40, quick exit | No | PENDING |
| 2025-01-15 | XXI | pre-market | +$730 | dip buy (recurring) | Recurring name, suspected recycled headlines, $7.70→$9.20 | No | PENDING |
| 2025-01-15 | SGBX | open bell | small winner | gap-and-go attempt | Modeled after AIFF, fizzled | No | PENDING |
| 2025-01-15 | QBTS | pre-market | not traded (scanner only) | watchlist only | On Ross's scanner but not traded | No | PENDING |
| 2025-01-15 | VMAR | pre-market | not traded (scanner only) | watchlist only | On Ross's scanner but not traded | No | PENDING |
| 2025-01-15 | MASS | pre-market | not traded (scanner only) | watchlist only | On Ross's scanner but not traded | No | PENDING |
| 2025-01-15 | COMP | pre-market | not traded (scanner only) | watchlist only | On Ross's scanner but not traded | No | PENDING |
| 2025-01-15 | LAES | pre-market | not traded (scanner only) | watchlist only | On Ross's scanner but not traded | No | PENDING |
| 2025-01-16 | DATS | pre-market | traded (P&L unknown) | daily breakout | Part of Jan 16 tickers, not individually detailed in recap | No | PENDING |
| 2025-01-16 | BMRA | pre-market | not traded (scanner only) | watchlist only | On Ross's scanner but not traded | No | PENDING |
| 2025-01-16 | ARQQ | pre-market | not traded (scanner only) | watchlist only | On Ross's scanner but not traded | No | PENDING |
| 2025-01-16 | XXII | pre-market | not traded (scanner only) | watchlist only | On Ross's scanner but not traded | No | PENDING |
| 2025-01-17 | ZO | pre-market | bulk of ~$4,864 | VWAP reclaim + range trading | Best trade of day, multiple re-entries $3.82-$4.20, 4-5 trades in tight range | No | PENDING |
| 2025-01-17 | AIMX | 8:00 AM | +$1,200 net | news breakout (failed first, dip buy second) | Real news catalyst, low float, first trade stopped -$500, second 5K shares $3.50→$4.00 = +$1,600 | No | PENDING |
| 2025-01-17 | NUKK | pre-market | not traded (avoided) | avoided | Up 73%, $36-38, 1M float, wide spreads 20-38 cents, weak catalyst, prior bad experience | No | PENDING |
| 2025-01-17 | VSS | pre-market | not traded (avoided) | avoided | Expanding into Brazil gaming, pre-market pops sold off, below VWAP all morning | No | PENDING |
| 2025-01-17 | BCAI | pre-market | not traded (avoided) | avoided | Pop-and-drop history | No | PENDING |
| 2025-01-17 | XCUR | pre-market | not traded (avoided) | avoided | Pop-and-drop history | No | PENDING |
| 2025-01-17 | LAES | pre-market | not traded (avoided) | avoided | Pop-and-drop history | No | PENDING |
| 2025-01-17 | INTC | pre-market | not traded (avoided) | avoided | Highest volume but no retail edge in large caps | No | PENDING |
| 2025-01-17 | BDMD | pre-market | not traded (scanner only) | watchlist only | On Ross's scanner but not traded | No | PENDING |

| 2025-01-21 | TPET | 7:00 AM | +$475 | thematic momentum (energy/inauguration) | Trio Petroleum, "drill baby drill" inauguration theme, 12K shares at $3.00, ice-breaker | No | PENDING |
| 2025-01-21 | NXX | 7:30 AM | +$1,800 | news breakout + dip buy | Suspected breaking news, entry $5.45→$6.30, reversed, dip at $4.59→$4.90, two trades | No | PENDING |
| 2025-01-21 | XTI | 9:00 AM | -$12 | news (failed) | Had news, immediately reversed, ruthless cut | No | PENDING |
| 2025-01-21 | BTCT | open | +$5,500 | thematic breakout (crypto/inauguration) | Bitcoin/crypto inauguration theme, break $8.60→$9.40 then break $10, two trades | No | PENDING |
| 2025-01-21 | TRIO | pre-market | not traded (scanner only) | watchlist only | On Ross's scanner but not traded | No | PENDING |
| 2025-01-21 | INDO | pre-market | not traded (scanner only) | watchlist only | On Ross's scanner but not traded | No | PENDING |
| 2025-01-22 | NEHC | pre-market | +$8,636 | squeeze breakout (energy infrastructure) | New Era Helium, energy infrastructure catalyst, entered $4.58-$4.65, scaled to 30K shares, exited ~$5.17 | No | PENDING |
| 2025-01-22 | BBX | pre-market | ~+$13,036 | premarket news squeeze | BlackBox Stocks, $2M financing + merger news, 2M float, entered ~$3.10-$3.15, ran to $3.80, multiple trades | No | PENDING |
| 2025-01-22 | PDYN | pre-market | not traded (passed) | passed on | 19M float too thick | No | PENDING |
| 2025-01-22 | IPA | pre-market | not traded (passed) | passed on | 232M shares, too cheap | No | PENDING |
| 2025-01-22 | ASST | pre-market | not traded (passed) | passed on | 110M shares, too cheap | No | PENDING |
| 2025-01-22 | ANYC | pre-market | not traded (passed) | passed on | Pulled back too much | No | PENDING |

| 2025-01-23 | DGNX | pre-market | +$22,997 | IPO day 2 squeeze (Level 2 tape) | Chinese IPO, ~2.25M float, IPO'd prior afternoon, PM spiked $24, entered $15.55 via Level 2 large bidder, rode to $20+, multiple dip trades | No | PENDING |
| 2025-01-23 | DXST | pre-market | ~breakeven | Chinese IPO chase | Second Chinese IPO, chased $7.50-$8.50, ran to $14, lost ~$3K on failed dip re-entry | No | PENDING |
| 2025-01-23 | MIMI | pre-market | ~breakeven | Chinese IPO momentum | Third Chinese IPO, near flush, narrowly avoided loss | No | PENDING |
| 2025-01-23 | SPCB | at open | small positive | breaking news (debt restructuring) | Recurring name (also Jan 2-3), debt restructuring news catalyst | No | PENDING |
| 2025-01-23 | DWTX | missed by Ross | not traded | biotech runner | Ran $3.50→$7+ (100% move), Ross missed it too. Bot scanner had DWTX on Jan 21 (rank #2, +40.59% gap) but NOT on Jan 23 | No (Jan 23); Yes (Jan 21) | PENDING |
| 2025-01-24 | EVAC | intraday | positive (est. +$5K-10K) | biotech sympathy (no news) | Pure sympathy play off ALRN/ALUR GLP-1 momentum, $8→$11, no catalyst — scanner can't catch sympathy plays | No | PENDING |
| 2025-01-24 | ELAB | early AM | profitable (est. +$3K-5K) | squeeze pullback entry | Squeezed early, Ross entered pullback ~$3.60, ran to ~$5.00, likely insufficient PM gap% or vol for scanner | No | PENDING |
| 2025-01-27 | AURL | pre-7AM (DeepSeek news) | green (amount unknown) | DeepSeek AI news squeeze | Chinese AI-adjacent, $8→$20+ (200%+ PM move), VWAP + dip/bounce entries. Biggest tech news of the year. Scanner found 0 Chinese AI stocks. | No | PENDING |
| 2025-01-28 | NLSP | intraday | +$165 | biotech pop and drop | ~800K float biotech, quick pop-and-drop scalp. Small ice-breaker trade. | No | PENDING |
| 2025-01-28 | JFB | intraday | +$600 | DeepSeek integration scalp | DeepSeek integration news, day 2 theme fading, quick scalp only. | No | PENDING |
| 2025-01-28 | QLGN | intraday | +$2,400 | biotech low-float squeeze | Biotech, low float, entered $4.75, ran to $5.51. Classic sub-$5 biotech squeeze. | No | PENDING |
| 2025-01-28 | ARNAZ | intraday | +$12,000 | daily breakout + halt resumption | "First candle to make new high" daily chart breakout. Halt resumption dip-and-rip, $7.50→$14.00 (87% move). NOT a pre-market gap play — daily timeframe pattern. Structural scanner limitation. | No | PENDING |
| 2025-01-29 | VNCE | pre-market/intraday | positive (part of ~$9K combined w/ SLXN) | momentum squeeze | Ran $1.73→$3.40, entered $2.99 for $3 break, ran to $3.30. Likely insufficient pre-market gap% to trigger scanner. Intraday mover. | No | PENDING |
| 2025-01-29 | MVNI | 9:47 AM (third entry) | +$3,900 | multi-trade momentum | First trade at ~$6.00 lost $500, re-entry broke even, third entry at 9:47 AM from ~$4.75→$7.50 (58% move). Mid-morning discovery — well outside scanner's 7:15 AM window. Day's anchor trade. | No | PENDING |

| 2025-01-30 | FOXX (FOXO) | late session | loss | no-news late chase | No news, low conviction. Ross's "make it back" trade after giving back AMOD gains. Not a meaningful scanner miss. | No | PENDING |
| 2025-01-31 | SGN | 7:00 AM | +$20,000+ (est.) | news squeeze (day-2 continuation) | Army Bowl sponsorship news on recurring name from Jan 29. Ice breaker $3.40, added $3.55/$3.59, squeezed to $4.00 first trade +$5K, then open squeeze to $5.00. Multi-day catalyst awareness. | No | PENDING |
| 2025-01-31 | NLSP | 7:30 AM | net ~+$938 | merger agreement news squeeze | Merger news at 7:30 AM (after scan window). Entry $2.50, squeezed to $3.40. First trade +$1,938, gave back ~$1K at open. Second time missed in 3 days (also Jan 28). | No | PENDING |
| 2025-01-31 | SZK | pre-market | -$2,500 | reverse split Chinese stock | Reverse split Chinese stock with news. Entry ~$3.30, dumped immediately. 66K float (cached). Not a meaningful miss — Ross also lost. | No | PENDING |

*(January 2025 complete — 22 trading days processed)*

## Profile X Blocked Trades (Scanner Found but Couldn't Trade)
These are NOT scanner misses — the scanner found them, but missing float data (Profile X) prevented trading.

| Date | Ticker | Gap% | PM Vol | RVOL | Ross P&L | Notes |
|------|--------|------|--------|------|----------|-------|
| 2025-01-06 | GDTC | +93.6% | unknown | unknown | +$5,300 | Scanner found, Profile X, 0 trades |
| 2025-01-30 | AMOD | +79.9% | 6.3M | 42.4x | positive (amount unknown) | Scanner found, Profile X, 0 trades. Breaking news, primary winner of the day. |

## Summary Stats (updated as data accumulates)
- Total missed stocks: 89 (Jan 2-3, Jan 6-7, Jan 10, Jan 13-17, Jan 21-24, Jan 27-31) — **JANUARY COMPLETE**
- Missed stocks Ross traded profitably: 32 (XPON +$15K, CRNC +$1.8K, SPCB +$2.6K, ARBE +$4.2K, ZENA +$998, CGBS +$297, HOTH +$1K, AIFF +$3.1K, XHG +$3.5K, DATS +$2K, SLRX +$13K, ADD +$5.8K, OSTX ~+$3K, XXI +$730, DATS Jan 16 P&L unknown, ZO bulk of ~$4.9K, AIMX +$1.2K, TPET +$475, NXX +$1.8K, BTCT +$5.5K, NEHC +$8.6K, BBX ~+$13K, DGNX +$23K, EVAC est. +$5-10K, ELAB est. +$3-5K, AURL green amount unknown, QLGN +$2.4K, ARNAZ +$12K, JFB +$600, VNCE positive, MVNI +$3.9K, SGN Jan 31 +$20K+)
- Missed stocks Ross traded at a loss: 5 (OST -$3K, GTBP -$3.4K, VRME -$4K, FOXX Jan 30 loss, SZK Jan 31 -$2.5K)
- Missed stocks Ross scratched/small: 15 (NTO ~$280 net, RHE small net gain, AMVS ~break-even, ARBE small profit Jan 10, XXI small profit Jan 13, PHIO net small profit, NMHI small profit, EVAX small profit, SGBX small winner, XTI -$12 scratch, DXST ~breakeven, MIMI ~breakeven, SPCB small positive Jan 23, NLSP +$165 Jan 28, NLSP +$938 Jan 31)
- Missed stocks — Ross also missed (big runners worth backtesting): 1 (DWTX $3.50→$7+ on Jan 23)
- Profile X blocked trades (scanner found, couldn't trade): 2 (GDTC Jan 6 +$5.3K for Ross, AMOD Jan 30 positive for Ross)
- Backtests completed: 0
- Hypothetical bot P&L on missed stocks: PENDING

### Note on Jan 6 GDTC
GDTC was the one Ross ticker the bot's scanner DID find (93.6% gap, discovered 07:00). However, GDTC was profile "X" (no float data) and the bot took 0 trades on the day. Ross made +$5,300 on GDTC. This is a "scanner found it but bot didn't trade it" case — worth investigating separately from scanner misses.

### Note on Jan 13 ATPC
ATPC was the one Ross ticker the bot's scanner DID find (+96% gap, 25.2M PM volume, 0.43M float, Profile A, rank #1). The bot traded ATPC at 07:05 (micro_pullback), entry $2.69, exit $2.68, P&L -$17 — essentially a scratch. Ross also made only a small profit on ATPC. The massive misses were SLRX (merger news, 1.2M float, 1200x RVOL, Ross made ~$13K) and PHIO (460% squeeze, 514K float, 168x RVOL). The bot found only 1 of 6 Ross tickers on this day.

### Note on Jan 14 AIFF & OST (Scanner Found)
AIFF and OST were the two Ross tickers the bot's scanner DID find on Jan 14. AIFF: +63.4% gap, 8.9M PM volume, 6.3M float, Profile B, discovered 07:45. The bot traded AIFF via both strategies — MP lost -$17 (scratch), SQ made +$1,441 across two trades (entries ~$4.61, exits $5.08 and $5.36). Combined bot AIFF P&L: **+$1,424**. Ross LOST -$2,000 on AIFF (reluctant VWAP break at $10.08, sharp rejection). The bot outperformed Ross by $3,424 on this single ticker. OST: +43.8% gap, 6.0M PM volume, 4.9M float, Profile A, discovered 07:14. Bot took 0 trades on OST despite finding it. Ross made +$1,800. The big scanner miss was ADD (+$5,810 for Ross, sub-1M float, 20M volume) — the bot's biggest missed opportunity of the day.

### Note on Jan 15 BKYI (Scanner Found)
BKYI was the only Ross ticker the bot's scanner found on Jan 15 (+65.7% gap, 27.8M PM volume, 9.6M float, Profile B, discovered 08:07). The bot took 0 trades on BKYI. Ross also **passed** on BKYI (negative prior experience, pop-and-reverse history, underwhelming catalyst) despite it being up 140%. The bot also found RENX (Profile X, no float) and MGIH (Profile A, 1.25M float) — neither appeared on Ross's radar. The scanner missed all 4 stocks Ross actually traded (OSTX, EVAX, XXI, SGBX) and all 5 additional watchlist tickers (QBTS, VMAR, MASS, COMP, LAES). This was a complete scanner whiff on the day's actionable opportunities. Ross noted CPI coming in below expectations caused the S&P to gap up big, which paradoxically hurt small-cap momentum by scattering buyer attention.

### Note on Jan 16 WHLR (Scanner Found)
WHLR was the one Ross ticker the bot's scanner DID find on Jan 16 (+53.6% gap, 11.9M PM volume, 0.19M float, Profile A, discovered 04:05). Ross made +$3,800 on WHLR. However, the bot took 0 trades on the day across both MP and SQ strategies. The scanner also found PMAX (+79.6% gap, Profile A) and AMBO (+16.7% gap, Profile A), neither of which appeared on Ross's radar. The scanner missed DATS, BMRA, ARQQ, and XXII from Ross's list.

### Note on Jan 7 MSAI
MSAI was the one Ross ticker the bot's scanner DID find (+108% gap, 29.7M PM volume, discovered 04:01). However, MSAI was profile "X" (no float data) so the bot filtered it out and took 0 trades. Ross noted MSAI was the leading gapper at 6:15 AM but had a topping tail by 7:00 AM and was already rolling over — he passed on it too. This is a "scanner found it, both bot and Ross correctly passed" case.

### Note on Jan 17 ZEO & BTCT (Scanner Found)
The bot's scanner found 4 tickers on Jan 17: VS (+70.8% gap, 1.76M float, Profile A), ZEO (+72.7% gap, Profile X, no float data), ISPC (+28.1% gap, 9.77M float, Profile B), and BTCT (+26.7% gap, 7.18M float, Profile B). Of these, ZEO and BTCT appeared on Ross's radar. ZEO: Ross saw it but avoided it (sector strength, no catalyst, prior pop-and-drops). BTCT: Ross traded it for a small profit (Bitcoin-related squeeze $5→$7.50, dip buy after squeeze, bounced to $7.20). The bot selected VS (#1, rank 0.952), ISPC (#2, rank 0.613), and BTCT (#3, rank 0.443) for both MP and SQ strategies, but took **0 trades** on all of them across both strategies. The bot completely missed ZO (Ross's best trade, VWAP reclaim range trading $3.82-$4.20, bulk of ~$4,864 day) and AIMX (news breakout, net +$1,200). This was a low-activity day (Friday before 3-day MLK weekend) — Ross traded conservatively with fewer than 10 trades and still made ~$4,864. VS and ISPC did not appear on Ross's radar at all.

### Note on Jan 27 — DeepSeek Day, Complete Scanner Whiff on Chinese AI
The bot's scanner found 4 tickers on Jan 27: TVGN (+52.5% gap, 5.65M PM vol, 0.88M float, Profile A), ICCT (+19.8% gap, 3.40M PM vol, 4.45M float, Profile A), GMHS (+19.9% gap, 220K PM vol, 3.89M float, Profile A), and BCDA (+16.9% gap, 125K PM vol, 7.2M float, Profile B). None of these were Chinese AI stocks. The v2 megatest generated **0 trades** across all strategies (SQ, MP, and combined). Meanwhile, AURL (Aurora Limited, Chinese AI-adjacent) ran from $8 to $20+ on DeepSeek news — a 200%+ pre-market move — completely invisible to the scanner. JG (Aurora Mobile, Chinese tech) was also a $15.5K winner per broker data. The expanded continuous rescan found YIBO (Chinese AI) at 10:38 AM with 4 trades for -$478 (gates off) — proving Chinese AI stocks were discoverable, just not by the 7:15 AM primary scan. This is the second complete scanner whiff in 6 trading days (Jan 22 was the other) and the second time Chinese stocks were a major miss (Jan 23 Chinese IPOs were the first). Ross traded AURL using VWAP and dip/bounce structure, explicitly passing on large-cap shorts (NVDA -17%). P&L not stated in recap.

### Note on Jan 24 ALUR & OST (Scanner Found)
ALUR and OST were the two Ross tickers the bot's scanner DID find on Jan 24. ALUR: +181.1% gap, 12.8M PM volume, 6.73M float, Profile B, rank #1 (0.809), discovered 04:01. The bot traded ALUR via SQ strategy — 3 trades for +$586 (+$506, -$9, +$89). Ross made +$47,000 on the same stock ("ALRN") — GLP-1 weight-loss therapy biotech news. Bot entered at $8.04 at 7:01 AM, nearly identical to Ross's entry (~$8.24 after 7:01 AM). The stock ran to $20. The bot's sq_target_hit exit at $8.40 captured $0.36 of a $12 move — 3% of the available range. This is the most extreme example of the exit management gap in the entire January series (80x P&L difference on the SAME stock at the SAME time). OST: +57.0% gap, 4.6M PM volume, 4.9M float, Profile A, rank #4 (0.535), discovered 06:41. Bot took 0 trades — correct decision, as Ross lost -$6,000 on OST (FOMO entry). Scanner missed EVAC (biotech sympathy, no news, $8→$11) and ELAB (squeeze pullback, ~$3.60→$5.00). This was the best scanner overlap day since Jan 14 — 2 of 4 Ross tickers found (50%), including his primary $47K winner.

### Note on Jan 28 — YIBO/YWBO Overlap, ARNAZ Daily Breakout Miss
The bot's scanner found 2 tickers on Jan 28: YIBO (+92.2% gap, 15.14M PM vol, 7.13M float, Profile B) and SNTG (+14.7% gap, 156K PM vol, 1.06M float, Profile A). YIBO is the same stock Ross traded as "YWBO" — Chinese AI continuation from DeepSeek day. The bot traded YIBO via VR strategy (all-three variant): entry $5.79, exit $6.12, +$125. Ross entered at $5.57 and rode to $6.36 for +$5,724 (46x gap). Scanner missed 4 of 5 Ross tickers: NLSP (biotech pop, +$165), JFB (DeepSeek integration, +$600), QLGN (biotech squeeze, +$2,400), and ARNAZ (daily breakout, +$12,000). ARNAZ is particularly notable — it was a "first candle to make new high" daily chart breakout with halt resumption dip-and-rip ($7.50→$14.00), a setup type the scanner literally cannot detect. This represents a new category of structural scanner limitation beyond the existing gap-based approach.

### Note on Jan 29 — SLXN Overlap, MVNI Mid-Morning Miss
The bot's scanner found only 1 ticker on Jan 29: SLXN (+57.8% gap, 30.9M PM vol, 3.0M float, Profile A). This was a textbook scanner hit — massive gap, huge volume, low float. All SQ-containing strategy variants traded SLXN profitably: all-three +$211, SQ +$231, MP+SQ +$212. MP alone generated 0 trades despite SLXN being Profile A. Ross also traded SLXN as his ice breaker, building to ~$7K profit before giving back — net positive but mixed. The bot missed 3 of 4 Ross tickers: VNCE (momentum squeeze $1.73→$3.40, likely insufficient pre-market gap), MVNI (+$3,900, anchor trade with 9:47 AM third entry at $4.75→$7.50, mid-morning discovery), and SGN (minimal). This is the second consecutive day with scanner overlap and bot profitability — the best streak in January. MVNI highlights the mid-morning discovery blindspot: Ross's best trade came 2.5 hours after open from a third attempt after two failed entries.

### Note on Jan 21 INM (Scanner Found)
The bot's scanner found 5 tickers on Jan 21: INM (+63.84% gap, 1.8M float, rank 1.027), DWTX (+40.59% gap, 1.35M float, rank 0.964), PTHS (+55.79% gap, 1.23M float, rank 0.728), LEDS (+27.9% gap, 3.43M float, rank 0.677), and VATE (+23.29% gap, 4.2M float, rank 0.597). INM is the same stock as Ross's INMN (his +$12,000 best trade — biotech Alzheimer's news, 68K float EXTREMELY LOW). Despite INM being the #1 ranked candidate, the bot did NOT trade INM. Instead: MP traded VATE (-$155, -0.2R) and PTHS (-$646, -0.9R); SQ traded LEDS (-$281, -0.7R). The bot picked the 3 worst-performing candidates and skipped the best one. The scanner missed TPET (+$475 for Ross, thematic energy), NXX (+$1,800, news breakout), BTCT (+$5,500, crypto theme), and XTI (-$12, scratch). Ross made +$28,026; the bot lost -$1,082. This is both a scanner gap (missed 4/5 traded tickers) AND a selection/execution gap (found INM but didn't trade it).
