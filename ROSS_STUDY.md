# Ross Cameron Strategy Study — Master List

## Process
1. Run simulation for ticker/date (full day including premarket)
2. Feed Ross's recap from his daily vlog
3. Compare bot vs Ross — note gaps
4. Update master list when patterns emerge across multiple examples
5. Implement changes once confident
6. Re-run all simulations to verify

**Note:** Simulations run from 04:00 AM, but in practice the bot wouldn't know about the stock until it hits the scanner. Ross's recaps usually mention scanner alert time — use this to determine which bot trades are realistic vs. unrealistic early entries.

---

## Master List of Potential Improvements

| # | Gap | Examples Seen | Confidence | Notes |
|---|-----|---------------|------------|-------|
| 1 | Extended move guard (max_green_1m) kills valid setups after strong impulse | MLEC 2/13, PAVM 1/21 | 2/5 | MLEC: reset at 8:10 (6 green). PAVM: killed 09:37 setup (6 green candles after open). ROLR: not triggered (bot caught early) |
| 2 | No HOD-break / flat-top breakout entry type | MLEC 2/13, ROLR 1/14 | 2/5 | MLEC: Ross entered break of HOD $8.49. ROLR: Ross entered break of $5. Bot only has pullback confirmation |
| 3 | No scaling in (adding to winners) | MLEC 2/13, PAVM 1/21, ROLR 1/14 | **3/5** | All 3 days Ross aggressively scaled in/out. ROLR: "all in" with full buying power, added on every whole-dollar break |
| 4 | Exit too passive — should sell into parabolic strength | MLEC 2/13, PAVM 1/21, ROLR 1/14 | **3/5** | All 3 days Ross sold at key levels. ROLR: took profit at $5.89, $7.20, $8.50, etc. Bot runners stopped at breakeven |
| 5 | Detection too slow for fast premarket movers | MLEC 2/13, PAVM 1/21, MNTS 2/6 | **3/5** | MLEC/PAVM: Ross entered 8:11-8:12, bot 2+ hrs late. MNTS: Ross at ~8AM, bot at 12:05PM. ROLR exception |
| 6 | Bot enters after the move is over, on a fading stock | PAVM 1/21, ROLR 1/14, MNTS 2/6 | **3/5** | PAVM: bot at $23 vs Ross $12. ROLR: trades 8-9 at $24/$32. MNTS: bot at $6.07 after stock faded from $9 |
| 7 | VWAP-loss resets during premarket chop kill re-entry opportunities | PAVM 1/21 | 1/5 | 7:57-8:10 saw multiple VWAP-loss resets. Ross entered during this exact window |
| 8 | No awareness of key technical levels (200 MA, whole/half dollars) | PAVM 1/21, ROLR 1/14 | 2/5 | PAVM: 200 MA rejection. ROLR: Ross used $5/$6/$8/$10 whole-dollar breaks for entries |
| 9 | No awareness that momentum is done — bot enters on faded/dead setups | ROLR 1/14, MNTS 2/6 | 2/5 | ROLR: late entries at $24/$32 gave back $2K. MNTS: entered at $6.07 after stock faded from $9, Ross already done |
| 10 | No catalyst/theme awareness | ROLR 1/14 | 1/5 | Ross identified "prediction market" theme as key driver. Bot purely technical |

---

## Tickers Tested

### 1. MLEC — Feb 13, 2026 (premarket + full day)

**Bot result:** 2 trades, 0 wins, -$2,513
- Trade 1: 08:20 entry $10.11, stopped out $8.61 (-$1,470)
- Trade 2: 11:53 entry $11.47, stopped out $10.76 (-$1,044)

**Ross result:** +$43,000 in 3 minutes (8:11-8:12 AM)
- Entered at $7.94 on break of HOD ($8.49 area), added at $7.97, $7.86
- Added on micro pullbacks at $10.42, $10.65
- Sold at $10.14, $10.09 into first red candle
- Missed second micro pullback to $12.50 (was getting tea)

**Key gaps identified:**
- Extended move guard killed the valid 8:10 setup (6 green candles > max 5)
- Bot entered 10 min late at $10.11 vs Ross at $7.94
- Ross scaled in; bot single entry
- Ross sold into strength; bot trailed down and stopped out
- Ross recognized the setup from scanner + level 2; bot purely chart-based

---

### 2. PAVM — Jan 21, 2026 (premarket + full day)

**Bot result:** 2 trades, 0 wins, -$2,513
- Trade 1: 10:36 entry $23.02, stopped out $21.55 (-$1,104)
- Trade 2: 12:59 entry $22.72, stopped out $21.00 (-$1,409)
- Premarket setups armed at 7:57 and 8:10 but both lost VWAP before trigger
- 09:37 setup killed by extended move guard (6 green candles)

**Ross result:** +$43,950 for the day
- Entered on second micro pullback at ~$12.31 with 15,000 shares in premarket (~8:12 AM)
- Stock ran from $12 to $15.37, rejected at 200 MA ($15.66)
- Went below VWAP, MACD went negative — Ross noted this as caution
- Later surged to $18, then $20, eventually hit $24.49
- Key insight: reverse split stocks tend to release positive news soon
- Ross used half-dollar and whole-dollar levels for entries/exits

**Key gaps identified:**
- Ross entered at $12.31 at 8:12 AM; bot first entry at $23.02 at 10:36 AM (2.5 hrs late, nearly 2x the price)
- Extended move guard killed the 09:37 setup (6 green candles after open)
- Premarket VWAP-loss resets (7:57-8:10) killed two armed setups that Ross traded through
- Ross recognized 200 MA as key resistance ($15.66) — bot has no awareness of daily MAs
- Ross scaled in during premarket; bot entered once at the worst possible level
- Bot's two entries were both near the top of the move ($23-24 area) after the stock had already run from $12
- Ross sold into strength at key levels; bot held and got stopped both times

---

### 3. ROLR — Jan 14, 2026 (premarket + full day)

**Bot result:** 9 trades, 4 wins, 5 losses, +$2,920 (44.4% win rate)
**Realistic result (scanner hit 8:18, trades 4-9 only): -$2,146**
- Trade 1: 08:04 entry $3.73, core TP $3.80 (+$506), runner stopped BE (+$0)
- Trade 2: 08:08 entry $3.82, stopped out $3.70 (-$1,200)
- Trade 3: 08:15 entry $3.91, core TP $5.89 (+$5,840), runner stopped $3.86 (-$80) — BIG WINNER
- Trade 4: 08:25 entry $9.33, stopped out $8.16 (-$1,073)
- Trade 5: 08:28 entry $12.24, core TP $17.90 (+$1,081), runner stopped $13.15 (+$94)
- Trade 6: 11:24 entry $16.11, stopped out $15.68 (-$1,023)
- Trade 7: 11:27 entry $17.98, core TP $20.25 (+$751), runner stopped $18.23 (+$45)
- Trade 8: 12:45 entry $24.33, stopped out $21.51 (-$1,021)
- Trade 9: 13:38 entry $32.15, stopped out $30.79 (-$1,000)

**Ross result:** +$85,000 for the day
- Scanner alert at 8:18 AM. Catalyst: "prediction market space" theme (Crypto.com partnership)
- Entered on break of $5 after dip to $4.60, filled avg ~$5.17 — "all in" with full buying power
- Took profits at $5.89, $6.40, $7.20, adding back on breakouts of whole dollars ($6.50, $8)
- Aggressively scaled in/out: profit at key levels, add back on breakouts, buy dips
- Stock hit blue sky breakout above ATH ($8), squeezed through $10, $12, $14, $15-$21
- Decreased size as price increased (couldn't afford as many shares at $15-20)
- Stopped trading when MACD went negative at $18 — "risk too high for potential additional profit"
- $52,000 profit in first 5 minutes alone

**Key gaps identified:**
- Bot actually caught early premarket (8:04 at $3.73) — BEFORE Ross ($5.17 at ~8:18). Detection worked here
- But bot made $2,920 vs Ross's $85,000 — 29x difference on same stock
- Biggest gap: scaling. Ross went "all in" and aggressively scaled in/out. Bot took 9 separate small positions
- Bot's Trade 3 ($3.91→$5.89) was a monster but only core TP hit — runner stopped at breakeven. Ross held and rode to $21
- Bot kept re-entering late: trades 8 ($24.33) and 9 ($32.15) were near the day's peak, both stopped out for -$2,021
- Ross knew when to stop — quit when MACD went negative. Bot had no session awareness
- Ross used whole/half dollar levels ($5, $6.50, $8, $10) for entries. Bot purely pattern-based
- Ross identified the catalyst theme as key conviction driver

---

### 4. MNTS — Feb 6, 2026 (premarket + full day)

**Bot result:** 1 trade, 0 wins, -$1,236
- Trade 1: 12:05 entry $6.07, stopped out $5.92 (-$1,236)
- Only 1 setup armed all day — bot mostly sat idle
- No premarket entries detected

**Ross result:** +$9,000
- Scanner hit at $8.18 just after 8:00 AM. Catalyst: NASA partnership
- Bought the dip for the curl back through $8
- Stock ran through $8.20, $8.40, $8.50, $8.60, all the way to $9 — took profit
- Tried second dip buy for retest of $9, but big sellers appeared, stock dropped below $8.40
- Momentum was done — did not re-enter

**Key gaps identified:**
- Ross entered at ~$8 around 8:00 AM; bot entered at $6.07 at 12:05 PM — 4 hours late, stock already faded from $9 to $6
- Ross recognized NASA catalyst as the driver; bot purely technical
- Ross knew momentum was dead when sellers appeared at $9 and stock dropped below $8.40 — stopped trading
- Bot entered at noon on a fading setup the best move was long over
- Ross took quick profit into strength at $9; bot got stopped on a low-quality late setup
- This was a relatively contained move ($8→$9) — bot's 3-bar pattern detection too slow for this type of quick pop
