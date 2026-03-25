# Jan 31, 2025 — Ross vs Bot Comparison (FINAL DAY OF JANUARY)

## Summary
| Metric | Ross | Bot (All-Three v2) | Bot (SQ v2) | Bot (MP v2) |
|--------|------|---------------------|-------------|-------------|
| Daily P&L | +$26,265 | -$1,338 | -$579 | -$1,197 |
| Trades | 3 tickers (SGN, NLSP, SZK) | 2 trades (CYCN, NCEL) | 2 trades (CYCN) | 2 trades (CYCN, NCEL) |
| Win Rate | 2/3 tickers profitable | 0/2 (0%) | 0/2 (0%) | 0/2 (0%) |
| Best Trade | SGN (pre-market squeeze +$5K first trade, squeezed to $5.00 at open) | — | — | — |
| Worst Trade | SZK (-$2,500, reverse split Chinese dump) | NCEL -$676 | CYCN -$579 | NCEL -$605 |

**Ross closed January with a strong +$26,265 day led by SGN (Army Bowl sponsorship news). The bot lost money across all strategy variants — CYCN and NCEL both hit max loss immediately. Zero scanner overlap: none of Ross's three tickers (SGN, NLSP, SZK) appeared in the bot's scanner. The bot found CYCN, NCEL, and IMDX — all three completely different from Ross's watchlist. This is a pure scanner gap day.**

**Market context:** Last trading day of January 2025. Ross's final January MTD: ~$406,000. SGN was a recurring name from Jan 29 — Ross recognized the Army Bowl sponsorship as fresh news and entered at 7:00 AM as an ice breaker. NLSP had merger agreement news at 7:30 AM. SZK was a reverse split Chinese stock trap that Ross took a loss on. Ross completed January as his best month in recent memory.

## Scanner Overlap

### Bot's Scanner Found (3 tickers)
| Ticker | Gap% | Float | PM Vol | Profile | Bot Traded? | Ross Traded? |
|--------|------|-------|--------|---------|-------------|--------------|
| CYCN | +19% | 2.7M | 2.3M | A | YES (-$662 all-three, -$592 MP, -$579 SQ) | NO |
| NCEL | +36% | 2.1M | 13.9M | A | YES (-$676 all-three, -$605 MP) | NO |
| IMDX | +14% | 7.8M | 105K | B | NO (filtered — low volume) | NO |

### Ross's Tickers NOT in Bot's Scanner (3 tickers)
| Ticker | Ross P&L | Setup | Why Scanner Likely Missed |
|--------|----------|-------|--------------------------|
| SGN | net positive (~$20K+ combined w/ first trade +$5K, open squeeze to $5.00) | pre-market news squeeze (Army Bowl sponsorship) | **Recurring name from Jan 29 — may not have gapped enough on day 2 to trigger scanner. 3.7M float (cached in scanner). Likely insufficient gap% or PM volume at 7:15 AM scan time.** SGN is becoming a pattern: Ross can identify multi-day catalysts the scanner treats as one-day events. |
| NLSP | net ~+$938 (first trade +$1,938, gave back ~$1K at open) | merger agreement news squeeze | **Low float (~800K) biotech with merger news. Second time missed in 3 days (also missed Jan 28). Likely sub-scanner thresholds on gap% or PM volume at scan time. Merger news dropped at 7:30 AM — after the 7:15 AM scan window.** |
| SZK | -$2,500 | reverse split Chinese stock | **Reverse split stocks often have distorted gap% calculations. Chinese stock with very low float (66K cached). Scanner may have filtered on reverse split flag or insufficient volume. Ross himself took a loss — this is not a meaningful scanner miss.** |

### Overlap: 0 of 3 Ross tickers scanned — COMPLETE WHIFF
Zero overlap on the final day of January. The bot and Ross traded entirely different universes. The bot found CYCN and NCEL (both Profile A stocks with respectable gaps) and lost money on both. Ross found SGN (recurring catalyst, 7:00 AM ice breaker), NLSP (merger news at 7:30 AM), and SZK (loss). The scanner's 7:15 AM snapshot completely missed both SGN's day-2 continuation and NLSP's 7:30 AM catalyst.

## Bot's Trades — What Happened

### V2 Megatest Results (Primary Backtest)
- **All-Three Strategy:** 3 scanned → 3 passed → CYCN, NCEL, IMDX → **2 trades, -$1,338**
  - CYCN: 14.3 score, entry $3.34, exit $3.21, reason: max_loss_hit, **-$662**
  - NCEL: 16.5 score, entry $3.21, exit $3.05, reason: max_loss_hit, **-$676**
  - Running equity: $29,135
- **SQ Strategy:** 3 scanned → passed → **2 trades on CYCN, -$579**
  - CYCN: trade 1 sq_max_loss_hit, trade 2 sq_max_loss_hit, trade 3 sq_para_trail_exit (-$213)
  - Running equity: $33,599
- **MP Strategy:** 3 scanned → passed → **2 trades, -$1,197**
  - CYCN: entry $3.34, exit $3.21, max_loss_hit, **-$592**
  - NCEL: entry $3.21, exit $3.05, max_loss_hit, **-$605**
  - Running equity: $26,053
- **MP+SQ Combined:** 3 scanned → passed → **2 trades on CYCN, -$579**
  - CYCN: sq_max_loss_hit (-$366), sq_para_trail_exit (-$213)
  - Running equity: $33,599

Both CYCN and NCEL were fast failures — max loss hit within minutes. Ross didn't trade either stock. The bot is again trading stocks Ross ignores while missing stocks Ross trades.

### CYCN & NCEL Trade Breakdown
| Metric | CYCN (All-Three) | NCEL (All-Three) |
|--------|-------------------|-------------------|
| Entry | $3.34 | $3.21 |
| Exit | $3.21 | $3.05 |
| Duration | ~minutes | ~minutes |
| Exit reason | max_loss_hit | max_loss_hit |
| P&L | -$662 | -$676 |
| Ross traded? | NO | NO |

Both trades reversed immediately after entry. Ross didn't look at either ticker. This continues the pattern of the bot trading "scanner finds" that experienced traders would avoid.

## Ross's Trades — What Made Them Work

### SGN — Primary Winner (Army Bowl Sponsorship News)
- **Catalyst:** Army Bowl sponsorship — fresh news on a stock Ross already knew from Jan 29
- **Setup:** Ice breaker at 7:00 AM. Entry $3.40, added at $3.55 and $3.59, squeezed to $4.00. First trade +$5K. Later at the open, squeezed to $5.00 but action was choppy.
- **Why it worked:** Multi-day awareness. Ross recognized SGN from Jan 29 and jumped on fresh news immediately at 7:00 AM. Building a position pre-market with adds on confirmation, then riding the squeeze. The open trade was choppier but still net positive.
- **Bot comparison:** Scanner didn't find SGN. Even if it had, the 7:00 AM entry was before the 7:15 AM scan. Ross's edge here is pattern recognition across days — seeing a name he already knows with new catalyst.

### NLSP — Merger Agreement News
- **Catalyst:** Merger agreement news at 7:30 AM
- **Setup:** Entry at $2.50, squeezed to $3.40. First trade +$1,938. Gave back ~$1K at the open on a failed breakout attempt.
- **Why it worked:** Classic biotech merger news squeeze. Low float (~800K), strong catalyst, quick move. Ross took the first trade cleanly but over-traded at the open.
- **Bot comparison:** Scanner missed NLSP again (also missed Jan 28). The 7:30 AM news arrival was after the scanner's window. This is a recurring timing gap — news-driven catalysts that arrive between 7:15-8:00 AM are invisible to the one-shot scan.

### SZK — Reverse Split Chinese Stock (Loss)
- **Catalyst:** News on a reverse split Chinese stock
- **Setup:** Entry ~$3.30, immediately dumped. Loss of -$2,500.
- **Why it failed:** Reverse splits create artificial price levels. Chinese stocks with reverse splits are particularly treacherous — the float is often distorted and selling pressure from the split overwhelms any catalyst.
- **Bot comparison:** Scanner didn't find SZK either, which is actually a good thing — this was a losing trade.

## Key Takeaways

### 1. FINAL Day Scanner Overlap: 0/3 — Ends January on a Whiff
The last day of January produced zero overlap between Ross and the bot. The three-day overlap streak (Jan 28-30: YIBO, SLXN, AMOD) is broken. Over the full month, scanner overlap was inconsistent: 14 of 22 trading days had at least one overlap ticker, but the quality and tradability of those overlaps varied wildly.

### 2. SGN: The Multi-Day Catalyst Problem
SGN appeared Jan 29 (minimal for Ross) and Jan 31 (major winner, +$20K+ estimated). Ross's ability to track names across days and re-engage on fresh news is a skill the scanner can't replicate. The scanner treats each day independently — a stock that gapped Jan 29 won't necessarily gap enough Jan 31 to re-trigger. This is a new pattern category: "day-2+ continuation on fresh catalyst."

### 3. NLSP: The Post-7:15 AM News Timing Gap (Recurring)
NLSP had merger news at 7:30 AM — 15 minutes after the scanner's snapshot. This is the second time in 3 days NLSP was missed (also Jan 28). Many breaking news catalysts arrive in the 7:00-8:30 AM window. A continuous or rolling rescan would catch these. The scanner's rigid 7:15 AM cutoff is a documented weakness.

### 4. Bot Loses on Both Trades — 0% Win Rate Pattern Continues
CYCN and NCEL both hit max loss immediately. The bot has now gone 0-for-2 on this day across all variants. The all-three variant's equity drops to $29,135. Over the full month, the bot's win rate on non-Ross stocks is extremely poor.

### 5. SQ vs MP: SQ Loses Less
On Jan 31, the SQ strategy lost -$579 while MP lost -$1,197. SQ's relatively tighter loss management continues to outperform MP's approach, even on losing days. Over the full month, SQ is the only net-positive strategy (+$3,754 entering this day).

## Missed P&L Estimate
- **SGN:** Scanner miss. Ross entered at $3.40, squeezed to $4.00 (first trade) then $5.00 (open). If the bot had found SGN and entered at $3.40 with $50K notional = ~14,700 shares. Conservative capture of 30 cents = +$4,400. Optimistic capture of 60 cents = +$8,800. **Scanner miss cost: ~$4,400 to $8,800.**
- **NLSP:** Scanner miss. Ross entered $2.50, squeezed to $3.40 (90-cent range). If bot entered at $2.50 with $50K notional = 20,000 shares. Conservative 20-cent capture = +$4,000. **Scanner miss cost: ~$2,000 to $4,000.**
- **SZK:** Ross lost -$2,500. Bot would likely also have lost. **Not a meaningful miss.**

**Combined estimated missed opportunity: +$6,000 to +$13,000 on SGN and NLSP.**

## Tickers Added to Missed Stocks Backtest Plan
- SGN (day-2 Army Bowl sponsorship news, scanner miss — recurring multi-day catalyst)
- NLSP (merger agreement 7:30 AM, scanner miss — post-scan-window news)
- SZK (reverse split Chinese loss, scanner miss — not meaningful, Ross also lost)

## Running Pattern Notes — FINAL JANUARY SUMMARY

This completes 22 trading days of daily Ross vs Bot comparison for January 2025.

**Scanner overlap streak:** The Jan 28-30 three-day streak (YIBO, SLXN, AMOD) was broken on Jan 31 with zero overlap. The scanner's hit rate was 14/22 days with at least one overlap (64%), but only 5 of Ross's 65+ unique tickers were both scanned AND traded by the bot (7.7%).

**Strategy performance final:** SQ is the only viable strategy. MP went 0-for-14+ all month. The combined strategy bleeds money from MP trades that SQ correctly avoids.

**January's three biggest problems:**
1. **Scanner gap** — missed 85%+ of Ross's tickers, including most $10K+ winners
2. **Exit management** — on shared tickers (especially ALUR), bot captured pennies of dollar moves
3. **MP strategy** — 100% loss rate, actively destroys capital

**January is complete. Final Ross P&L: ~$406,000. Final bot all-three P&L: ~$27,797 equity (from $30K start = -$2,203). The gap is ~185x.**
