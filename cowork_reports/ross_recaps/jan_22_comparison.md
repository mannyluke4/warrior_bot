# Jan 22, 2025 — Ross vs Bot Comparison

## Summary
| Metric | Ross | Bot (MP) | Bot (SQ) |
|--------|------|----------|----------|
| Daily P&L | +$21,672 | $0 | $0 |
| Trades | 2 tickers, multiple trades | 0 trades | 0 trades |
| Win Rate | 2/2 tickers green | N/A | N/A |
| Best Trade | NEHC +$8,636 | — | — |
| Worst Trade | BBX (net positive, multiple trades) | — | — |

**Combined bot P&L: $0 vs Ross's +$21,672 — gap of $21,672.**

## Scanner Overlap

### Bot's Scanner Found (1 ticker)
| Ticker | Gap% | Float | Rank | Bot Traded? | Ross Traded? |
|--------|------|-------|------|-------------|--------------|
| GELS | 27.6% | 5.46M | #1 (only candidate) | NO (0 armed, 0 signals) | NO |

### Ross's Tickers NOT in Bot's Scanner (6 tickers)
| Ticker | Ross P&L | Setup | Why Scanner Likely Missed |
|--------|----------|-------|--------------------------|
| NEHC | +$8,636 | squeeze breakout after consolidation | Energy infrastructure catalyst — gap/volume likely below scanner thresholds or not enough pre-market movement by scan time |
| BBX | ~+$13,036 | premarket news squeeze (financing + merger) | $2M financing + merger news, 2M float — may not have met gap% threshold or PM volume cutoff at scan time |
| PDYN | not traded (passed) | passed on | 19M float too thick for Ross; scanner wouldn't have found it actionable either |
| IPA | not traded (passed) | passed on | 232M shares, too cheap — well outside scanner parameters |
| ASST | not traded (passed) | passed on | 110M shares, too cheap — well outside scanner parameters |
| ANYC | not traded (passed) | passed on | Pulled back too much — Ross passed for price action reasons |

### Overlap: ZERO
The bot's scanner found **0 of Ross's 2 traded tickers**. Complete scanner whiff on this day. The only scanner candidate (GELS) was not on Ross's radar at all, and the bot took 0 trades on it anyway (no armed signals in 24,729 ticks of data).

## Bot's Trades — What Happened

### MP Strategy (0 trades, $0)
No trades. GELS was the only candidate and generated 0 armed signals, 0 entry signals across all strategy modes. The price action on GELS simply didn't produce any patterns the bot's strategies look for.

### SQ Strategy (0 trades, $0)
Same as MP — GELS produced nothing. Zero armed, zero signals.

### Why GELS Didn't Trigger
GELS had a +27.6% gap with 3.72M PM volume and 5.46M float (Profile B). Despite decent volume, the stock's price action during the trading session apparently didn't form either a squeeze consolidation pattern (SQ) or a micro-pullback setup (MP). 24,729 ticks of data were processed with zero signals — this was a dead ticker for the bot's strategies.

## Ross's Trades — What Made Them Work

### NEHC (New Era Helium) — +$8,636
- **Catalyst:** Energy infrastructure (helium is critical for semiconductors, MRI, space)
- **Setup:** Squeeze breakout after consolidation — classic pattern
- **Execution:** Entered $4.58-$4.65, scaled to 30K shares (!), exited ~$5.17
- **Key insight:** Ross sized aggressively (30K shares) because the setup was clean and the catalyst was real. $0.52-$0.59 move on 30K shares = big P&L on a relatively small % move.

### BBX (BlackBox Stocks) — ~$13,036
- **Catalyst:** $2M financing + merger news, 2M float
- **Setup:** Pre-market momentum, ran from ~$3.10-$3.15 to $3.80
- **Execution:** Multiple trades, capturing the pre-market run
- **Key insight:** Ultra-low float (2M) + double catalyst (financing AND merger) = explosive pre-market action. Ross capitalized on multiple entries.

### Stocks Ross Passed On
Ross's passes are as informative as his trades:
- **PDYN:** 19M float — too thick for meaningful squeeze
- **IPA:** 232M shares outstanding — too cheap, no edge
- **ASST:** 110M shares — same reasoning
- **ANYC:** Pulled back too much — price action deteriorated

## Key Takeaways

### 1. Scanner Found NOTHING Ross Traded — Complete Miss Day
Jan 22 is the **worst scanner overlap day so far** in the series. Zero overlap. The bot's scanner found 1 ticker (GELS) that neither Ross nor the bot traded. Meanwhile Ross made +$21,672 on 2 tickers the scanner never saw.

### 2. Low-Scanner-Activity Day = High Risk of Missing Everything
Only 1 scanner candidate on Jan 22 (vs 5 on Jan 21, 4 on Jan 23). When the scanner finds very few stocks, the odds of those few overlapping with what's actually tradeable drop dramatically. The scanner's gap/volume thresholds may be too tight for days with more subtle catalysts.

### 3. NEHC and BBX Had Real Catalysts But Different Profiles
- NEHC: Energy infrastructure play, $4-5 price range, likely gapped up but possibly not 10%+ which is the scanner's minimum
- BBX: 2M float with merger + financing news — this SHOULD have been scanner-visible if it gapped enough. Worth investigating whether BBX met the gap threshold but was filtered out for another reason, or simply didn't gap enough pre-market.

### 4. Ross's Sizing on NEHC Is the Story
30K shares on a $4.60 stock = $138K notional. Ross used massive size because the setup was high-conviction. The bot's max notional is $50K. Even if the bot had found NEHC and traded it perfectly, it would have captured roughly 36% of Ross's position size at most.

### 5. Dead Days for the Bot
When the scanner finds only 1 ticker and that ticker generates 0 signals, the bot sits idle. This is actually capital preservation (no losses), but it means the bot's entire day depends on whether its narrow scanner finds the right stocks. On days like Jan 22, that dependency results in $0 vs Ross's $21,672.

## Missed P&L Estimate
If the bot had found NEHC and traded the squeeze breakout:
- Entry ~$4.60, exit ~$5.17 = $0.57/share
- At bot's $50K max notional: ~10,869 shares × $0.57 = +$6,195
- Even at 2.5% risk sizing (~$763 risk): still potentially +$2,000-$3,000

If the bot had also found BBX ($3.10→$3.80, 2M float squeeze):
- $0.70/share move, at $50K notional: ~16,129 shares × $0.70 = +$11,290 (unrealistic full capture)
- Realistic 30-50% capture: +$3,400-$5,650

**Total missed opportunity: estimated $5,000-$10,000 if scanner had found both tickers.**

## Tickers Added to Missed Stocks Backtest Plan
NEHC, BBX (2 tickers — both absent from bot's scanner)

Passed tickers (PDYN, IPA, ASST, ANYC) not added since Ross also passed on them.

## Running Pattern Notes
This is the **3rd consecutive trading day** (Jan 17, 21, 22) where the bot's scanner missed the majority of Ross's traded tickers. The pattern is clear: the scanner's gap% + volume thresholds are too narrow, especially for:
- Energy/commodity infrastructure plays (NEHC)
- Merger/financing news on ultra-low float stocks (BBX)
- Thematic momentum plays (TPET, BTCT from Jan 21)
- Breaking intraday news (NXX from Jan 21)

The scanner's sweet spot seems to be high-gap biotech names — it consistently finds those. But Ross trades a much wider universe of catalysts.
