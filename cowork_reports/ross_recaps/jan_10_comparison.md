# Jan 10, 2025 — Bot vs Ross Comparison

## Day Context
- Friday post-holiday (Jimmy Carter mourning day Thu), slow low-volume day
- Leading gapper only up 45% — weak day signal
- Ross called it a "base hit day" from 7:30 AM

## Ross's Results
- **Daily P&L: +$9,500.22**
- 4 stocks traded: VMAR (+$1,361), AIFF (+$3,100), ARBE (small profit), XHG (+$3,500)
- 2 stocks passed on: DTIL, DATS

## Bot's Results

### Scanner
- **Found:** VMAR (84.9% gap, 21.7M PM vol, 0.87M float, Profile A) and STAI (33% gap)
- **Missed:** AIFF, ARBE, XHG, DTIL, DATS, ARTL, CX, PAVS, ARB

### Bot Trades

**MP (Momentum Push) Strategy:**
- Selected VMAR and STAI as candidates
- **0 trades executed** — no MP setups triggered

**SQ (Squeeze) Strategy:**
- **VMAR: +$81** (entry $3.73, exit $3.76, stop $3.59, +0.2R, squeeze setup, parabolic trail exit at 09:55)
- 1 trade total

### Bot Daily P&L: +$81

## Head-to-Head: VMAR
| Metric | Ross | Bot (SQ) |
|--------|------|----------|
| P&L | +$1,361 | +$81 |
| Entry | ~$3.00 support bounce | $3.73 squeeze |
| Exit | ~$3.25 | $3.76 |
| Setup | Support bounce at round $3.00 | Squeeze w/ parabolic trail |
| Time | 7:00 AM (pre-market) | 9:55 AM exit |

Ross entered much earlier (7 AM premarket on the support bounce at $3.00) and captured significantly more of the move. The bot entered late at $3.73 during the squeeze phase and only captured 3 cents.

## Stocks Ross Traded That Bot Missed Entirely

### AIFF (+$3,100)
- Ross traded 4 times during rapid acceleration from $3→$6.24
- Main entry at $5.23, 10-second chart entries, dip buys at $4.00
- **Bot scanner did not find AIFF at all**
- **NOTE:** On Jan 14, the monthly comparison showed the bot OUTPERFORMED Ross on AIFF (+$1,424 vs -$2,000). But that was a different date — the bot did NOT trade AIFF on Jan 10.

### ARBE (small profit)
- Ross scalped $2.75→$3.10 on breaking news at 8:32 AM
- Same stock from Jan 6 where Ross made +$4,200
- Bot missed ARBE on both Jan 6 AND Jan 10

### XHG (+$3,500)
- No-news pure momentum continuation — biggest winner of the day
- 5m+1m aligned pullback, 20K share positions chipping 5-8 cents
- Bot scanner did not find XHG
- Irony: the no-news stock outperformed all 3 news stocks

## Bot Traded, Ross Didn't

**STAI** — Bot selected STAI (33% gap) as a candidate but did not actually execute any trades on it. Ross did not mention STAI.

## Key Takeaways

1. **Scanner gap is the core issue:** Bot only found 1 of Ross's 4 traded stocks, and even on VMAR it entered late and captured a fraction of the move
2. **$9,419 left on the table:** Ross made +$9,500 vs bot's +$81 — a $9,419 gap, almost entirely due to scanner misses
3. **No-news stocks invisible to bot:** XHG (Ross's biggest winner at +$3,500) had no catalyst — the bot's scanner likely requires a gap/news trigger and would never find these
4. **AIFF on Jan 10 vs Jan 14:** The bot's +$1,424 AIFF outperformance happened on Jan 14, not Jan 10. On Jan 10, the bot missed AIFF entirely. This means the bot can trade AIFF well when it finds it — the scanner just didn't flag it on this particular day.
5. **ARBE recurring miss:** Bot missed ARBE on both Jan 6 (Ross +$4,200) and Jan 10 (Ross small profit). This is a pattern worth investigating — ARBE had news catalysts both times.
6. **Premarket entry advantage:** Ross's VMAR entry at $3.00 (7 AM) vs bot's $3.73 (9:55 AM) shows the value of earlier entries. Ross captured 16x more profit on the same stock.
