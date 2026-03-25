# PERPLEXITY RESEARCH DIRECTIVE: Scanner Data Gap Investigation

**Date**: 2026-03-24
**Context**: Warrior Bot trading bot misses stocks that Ross Cameron trades because they're not in our Databento/Alpaca data feeds. We need to understand WHY each stock is missing and whether we can fix it.

---

## Background

Our bot uses Databento for tick data and Alpaca for symbol universe + order execution. In January 2025, Ross Cameron traded 10 stocks that had ZERO data in our feeds. Combined, Ross made ~$76,800 on these stocks. We need to figure out which ones are actually recoverable.

## Research Tasks

### Task 1: Verify Exchange Listings (January 2025)

For each of the 10 stocks below, determine:
1. **What exchange was it listed on in January 2025?** (NASDAQ, NYSE, NYSE Arca, OTC Pink, OTCQX, OTCQB, TSX, etc.)
2. **Is it still listed today, or was it delisted/ticker-changed?** If ticker changed, what's the new ticker?
3. **What was the approximate float in January 2025?**
4. **What was the company name?** (Some of these tickers may be transcription errors from Ross Cameron's daily recap videos)

| Ticker | Ross P&L (Jan 2025) | Ross Trade Date | Notes from Recap |
|--------|---------------------|-----------------|------------------|
| ESHA | +$15,556 | Jan 9 | ESH Acquisition Corp — we KNOW this is NASDAQ |
| INBS | +$18,444 | Jan 9 | Intelligent Bio Solutions — we KNOW this is NASDAQ, 637K float |
| BBX | +$13,036 | Jan 22 | "BlackBox Stocks" per recap — actual company trades as BBXIA/BBXIB on OTC |
| ARNAZ | +$12,000 | Jan 28 | "Daily breakout + halt resumption" — no US listing found |
| AURL | green | Jan 27 | "Chinese AI stock (DeepSeek)" — only match is Indian pharma |
| EVAC | +$5-10K | Jan 24 | "GLP-1 sympathy play" — EQV Ventures Acquisition on NYSE |
| AIMX | +$1,200 | Jan 17 | "News breakout" — only match is a crypto token |
| ZO | +$4,864 | Jan 17 | "VWAP reclaim range trading" — only match is Turkish utility |
| NXX | +$1,800 | Jan 21 | "News breakout" — only match is Canadian mining (TSXV) |
| MVNI | +$3,900 | Jan 29 | "Mid-morning multi-trade" — no match found at all |

### Task 2: Databento Coverage Investigation

For ESHA, INBS, and EVAC — all confirmed on NASDAQ/NYSE:

1. **Does Databento cover these symbols?** Check Databento's symbol directory or documentation for XNAS (NASDAQ) and XNYS (NYSE) coverage.
2. **Are there known gaps for SPACs, low-volume stocks, or newly-listed securities?** ESHA and EVAC are both SPACs — does Databento have reduced coverage for blank check companies?
3. **Could there be a symbol mapping issue?** Some platforms use different suffixes for SPACs (e.g., ESHA vs ESHA.U for units, EVAC vs EVAC= for warrants). Did we query the right symbol?
4. **What about Alpaca's coverage?** Does Alpaca's `get_all_active_symbols()` include these tickers? Alpaca filters some low-liquidity names.

### Task 3: BBX Ticker Mismatch

BBX Capital Inc. trades as BBXIA (Class A) and BBXIB (Class B) on OTC after a 2020 spin-off from the old BBX Capital Corporation (which traded on NYSE as BBX).

1. **Which ticker did Ross actually trade?** Was it BBXIA, BBXIB, or the old BBX? Check his Jan 22, 2025 recap for the exact ticker shown on screen.
2. **Does Databento/Alpaca cover OTC stocks like BBXIA?** Databento's XNAS feed includes some OTC names. Is BBXIA in scope?
3. **If not Databento, what data provider covers OTC?** Options: IEX Cloud, Polygon.io, OTC Markets API.

### Task 4: Alternative Data Sources for Missing Stocks

For the stocks genuinely outside our data universe:

1. **What data providers cover the broadest US equity universe?** Compare: Databento, Polygon.io, IEX Cloud, Trade Ideas, Benzinga, Quandl/Nasdaq Data Link.
2. **Does any single provider cover ALL of: NASDAQ, NYSE, OTC Pink, OTCQX, OTCQB?**
3. **What does Ross Cameron use for his scanner?** Trade Ideas is known — does their API provide tick-level data, or just scanner alerts?
4. **Cost comparison for providers that cover OTC:**
   - Polygon.io: pricing for real-time OTC data
   - IEX Cloud: pricing for OTC coverage
   - Databento: do they offer OTC add-on feeds?
5. **Latency considerations:** We need tick-level data for backtesting AND real-time data for live trading. Which providers support both use cases?

### Task 5: Verify Ticker Accuracy

Some of these tickers may be transcription errors from Ross Cameron's video recaps. Common issues:
- Ross shows ticker on screen briefly; AI transcript may misread it
- Similar-looking tickers get confused (AURL vs AUR, AIMX vs AMIX, etc.)

For ARNAZ, AURL, AIMX, ZO, NXX, MVNI:
1. **Search Ross Cameron's Warrior Trading YouTube channel** for his January 2025 daily recaps on the specific dates listed above.
2. **Cross-reference with his trade log** if available publicly (Warrior Trading sometimes publishes monthly summaries).
3. **Check common small-cap/penny stock databases** (OTC Markets, PennyStockNews, StocksToTrade) for these tickers around those dates.
4. **Search for news catalysts** on those dates — if a stock ran 50%+ on Jan 17, Jan 21, etc., financial news sites would have covered it.

---

## Deliverable

A report with:
1. **Confirmed exchange listing** for each of the 10 stocks (or "cannot verify" with explanation)
2. **Root cause** for each data gap (Databento coverage gap, OTC, ticker mismatch, or transcription error)
3. **Recommended fix** for each recoverable stock
4. **Data provider recommendation** for expanding coverage to OTC if needed, with pricing
5. **Corrected tickers** for any transcription errors identified

Save the report to: `cowork_reports/2026-03-24_data_gap_investigation.md`

---

## Priority

This is research only — no code changes. The goal is to understand the gap so we can make informed decisions about which data providers to add.

Ross made ~$76,800 on these 10 stocks in January alone. Even at our ~20% capture rate, that's ~$15K/month we're leaving on the table. Understanding which stocks are recoverable tells us whether the investment in an additional data feed is worth it.
