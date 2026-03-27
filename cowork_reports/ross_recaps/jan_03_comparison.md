# Jan 3, 2025 — Ross vs Bot Comparison

## Summary
| | Ross | Bot |
|---|---|---|
| **Daily P&L** | +$4,800 | $0 (no trades) |
| **Stocks Traded** | CRNC, SPCB, NTO | None (SYNX selected, no entry triggered) |
| **Scanner Tickers** | TGL, MFI, CYCC, NITO, CRNC, SPCB | SYNX only |

## Scanner Overlap: ZERO
The bot's scanner found only **SYNX** (gap +65.7%, float 2.54M, profile A, discovered 9:49 AM).
Ross's scanner had: TGL, MFI, CYCC, NITO, CRNC, SPCB — **none overlapping** with the bot.

Ross did not mention SYNX at all.

## Bot's Activity
- **SYNX** was selected by both mp_only and sq_only configs
- Despite selection, **0 trades were generated** on either config — no valid entry signal materialized
- Both configs ended Jan 3 flat (mp_only equity: $29,893 / sq_only equity: $29,794)

## Ross's Trades the Bot Missed

### CRNC (+$1,800)
- **Why bot missed:** Not on scanner. CRNC had Nvidia collaboration news but was likely filtered out due to higher float or price range not matching bot's scanner criteria.
- **Setup:** Squeeze/breakout on news catalyst, entered ~$9.60 targeting $10 break, max 4K shares.
- **Ross's note:** Higher float than preferred but Nvidia keyword was the "one pillar exception."

### SPCB (+$2,600 net)
- **Why bot missed:** Not on scanner. SPCB was a day-2 continuation play from Jan 2. The bot's scanner also missed SPCB on Jan 2 (already logged in missed stocks plan).
- **Setup:** Continuation/breakout, curl through $9, stair-step pattern, max 6K shares.
- **Ross's note:** ~$1K-$1.2K giveback on the last trade of the sequence.

### NTO (~scratch, +$280 net)
- **Why bot missed:** Not on scanner. Stock was under $2 — likely below the bot's minimum price filter.
- **Setup:** Momentum on news, 20K shares for 2 cents/share.
- **Lesson:** Fee drag on cheap stocks makes them unviable. Ross concluded stocks under $2 with 20-30 cent ranges don't work with direct-access fees. This validates the bot likely being correct to filter these out.

## Stocks Ross Passed On (also not on bot scanner)
- **TGL:** Up 400% but only 30-cent total range — too thin to trade
- **MFI:** Too cheap, tight range
- **CYCC:** Same as MFI

## Bot Traded Stocks Ross Didn't Trade
- **SYNX:** Bot selected it but generated no trades. Ross didn't mention it. The stock gapped +65.7% with 2.54M float — meets profile A criteria but no entry materialized in backtesting.

## Key Takeaways

1. **Complete scanner miss again:** Like Jan 2, the bot's scanner found zero of Ross's tickers. Two trading days in and there's been zero overlap between Ross's watchlist and the bot's scanner output.

2. **Bot found only 1 candidate total:** On a day with "4 penny stocks up 100%+", the bot's scanner found only SYNX. This is an extremely thin pipeline.

3. **Scanner timing matters:** SYNX wasn't discovered until 9:49 AM. Ross was already trading by 8:00 AM (CRNC). The bot's late discovery further limited its options.

4. **$4,800 left on table:** Ross made +$4,800 on stocks the bot never saw. Even the "scratch" trade on NTO validates the bot's price filter — cheap stocks are fee traps.

5. **Continuation plays not captured:** SPCB was a day-2 play. The bot's scanner doesn't appear to have a mechanism for tracking multi-day setups that carry over.

6. **"One pillar exception" pattern:** Ross overrode his normal float preference for CRNC because the Nvidia keyword was strong enough. The bot's rigid filter criteria can't make this kind of judgment call.

7. **SYNX no-trade is notable:** The bot correctly identified SYNX as a candidate but generated no entry. Worth investigating whether SYNX actually had a tradeable setup or if the bot was right to stay out.
