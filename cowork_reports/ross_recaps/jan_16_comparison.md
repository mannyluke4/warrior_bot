# Jan 16, 2025 — Ross vs Bot Comparison

## Summary
- **Ross P&L:** +$5,667
- **Bot P&L:** $0 (no trades taken)
- **Gap:** -$5,667

## Bot Scanner Results (3 tickers found)

| Ticker | Gap% | PM Price | Float | Profile | Discovery | PM Volume |
|--------|------|----------|-------|---------|-----------|-----------|
| PMAX | +79.6% | $2.48 | 0.38M | A | 04:00 | 10.4M |
| WHLR | +53.6% | $3.61 | 0.19M | A | 04:05 | 11.9M |
| AMBO | +16.7% | $2.38 | 0.07M | A | 07:47 | 1.1M |

## Ross's Scanner Tickers (5 total, from monthly summary)
WHLR, DATS, BMRA, ARQQ, XXII

## Cross-Reference: Overlap

### Scanner found + Ross saw
- **WHLR** — Bot scanner found it (Profile A, 0.19M float, +53.6% gap, discovered 04:05). Ross made **+$3,800** on WHLR. Bot took 0 trades despite finding it. This is a "scanner found it but bot didn't trade it" case — the bot's best opportunity of the day was sitting right there.

### Scanner found + Ross did NOT mention
- **PMAX** — Profile A (0.38M float, +79.6% gap), bot's top scanner result. Not on Ross's radar. Unknown why Ross didn't trade it — possibly too cheap or no catalyst.
- **AMBO** — Profile A (0.07M float, +16.7% gap), smaller gap. Not mentioned by Ross.

## What the Bot Missed

### Stocks Ross traded/saw that the bot's scanner missed entirely

| Ticker | Ross P&L | Setup | Why Scanner Likely Missed |
|--------|----------|-------|--------------------------|
| DATS | Traded (P&L not individually detailed) | Daily breakout | DATS appeared on Jan 10 (passed) and Jan 13 (+$2K) — recurring name, may not have met gap% threshold on Jan 16 |

### Stocks on Ross's watchlist the bot missed
- BMRA, ARQQ, XXII — on Ross's monthly summary scanner list but not traded

## Bot Trades on Stocks Ross Didn't Trade
None — the bot took 0 trades on Jan 16 across both MP and SQ strategies.

## Recap Detail Level
This recap is **less detailed** than most — the video ("Surprise Daily Breakout Setup at 9:30am ET") didn't identify specific tickers by name. Trade details are inferred from price action descriptions and the monthly summary. Key facts:
- Trade 1: Lower-priced stock (~$3-6 range), breaks of $6 level, +$1,500, max 6K shares
- Trade 2: Entry $3.82, targeting $4.06 double top, squeezed through $4, first trade of the day
- Monthly summary confirms WHLR (+$3,800) and DATS as the main tickers

Based on the price descriptions, Trade 2 (entry $3.82) likely aligns with WHLR (PM price $3.61, would have opened near that range). Trade 1 (breaks of $6 level) may be DATS or another ticker that reached the $6 range.

## Key Takeaways

1. **WHLR: scanner found it, bot didn't trade it.** This is the third time we've seen this pattern (also GDTC Jan 6, BKYI Jan 15). The scanner is surfacing the right stock but the bot's trade entry logic isn't triggering. WHLR was Profile A, low float (190K), massive gap (+53.6%), massive PM volume (11.9M) — a textbook A-setup that the bot should have traded.

2. **Zero bot trades again.** The bot has now had 0-trade days on Jan 6, Jan 7, Jan 10, Jan 13, Jan 14 (MP only), Jan 15, and Jan 16. The pattern of "scanner finds candidates but bot doesn't trade" is persistent.

3. **Low-catalyst week context.** Ross described this as a "some opportunities but nothing insane" week with no powerful catalyst-driven movers. He adapted by sizing down and taking base hits. The bot's lack of trades during a week Ross still made +$5,667 suggests the entry criteria may be too strict.

4. **DATS recurring.** DATS has now appeared on Jan 10, Jan 13, and Jan 16 across Ross's recaps. It's a multi-day runner the scanner keeps missing. This pattern of recurring names that build momentum over days is a scanner gap worth investigating.

5. **Scanner found 1 of 5 Ross tickers.** Coverage ratio of 20% — slightly below the overall average. The scanner found the most important one (WHLR, Ross's biggest winner) but couldn't capitalize on it.
