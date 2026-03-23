# Research Directive: Small-Cap Data Feeds & Float Data Sources

**For:** Perplexity AI (deep research mode)
**From:** Manny (Warrior Bot project)
**Date:** 2026-03-23
**Purpose:** Evaluate alternative data feeds and float data providers for a Python trading bot that trades small-cap stocks

---

## Background

I run a Python day trading bot called Warrior Bot that detects micro-pullback and squeeze setups on small-cap stocks ($2-$20, float <10M shares) and executes paper trades via Alpaca API. The bot follows Ross Cameron's (Warrior Trading) methodology — gap-up small caps with high relative volume and low float.

### Current Data Infrastructure

**Live trading:**
- **Broker:** Alpaca Markets (paper account, websocket for real-time trades/quotes)
- **Scanner:** Custom `live_scanner.py` using Databento EQUS.MINI real-time stream for pre-market gap detection
- **Float data:** FMP (Financial Modeling Prep) API as primary, yfinance as fallback. Both fail on ~10% of small-cap tickers (returns None).

**Backtesting:**
- **Tick data:** Databento historical API, cached locally (33.7M ticks, 240 stock/date pairs)
- **Scanner sim:** Custom `scanner_sim.py` using Alpaca historical bars API for pre-market gap detection + float lookup

### The Problem We're Solving

We backtested all 68 stocks Ross Cameron traded in January 2025. Our scanner found only 5 of them (7.4%). The bot would have made +$42,818 if it had found all of them (vs $5,543 actual — 7.7x multiplier).

The misses fall into two categories this research addresses:

**Category A: Stocks not in our data universe (28% of misses, ~$76,800 Ross P&L)**
10 stocks had ZERO data in Databento or Alpaca. They appear to be OTC, pink sheet, or non-NMS listed stocks. Examples: ESHA, INBS, BBX, ARNAZ, AURL, EVAC, AIMX, ZO, NXX, MVNI. These are real stocks Ross traded profitably — they just aren't in Databento's NMS equity dataset.

**Category B: Float data unavailable (11% of misses, +$12,178 bot P&L)**
4 stocks were found by our scanner but couldn't trade because FMP and yfinance returned None for float data. Example: XPON had a valid 9.3M float but neither API resolved it. GDTC and AMOD were found with massive gaps (93%+ and 80%+) but blocked.

---

## Research Questions

### 1. Alternative Real-Time Data Feeds for Small-Cap/OTC Coverage

I need a data feed that covers the stocks Databento and Alpaca miss. Please research:

**a) Trade Ideas API**
- Ross Cameron uses Trade Ideas for his live scanner. Does Trade Ideas offer a programmatic API (REST or websocket)?
- What's the coverage universe? Does it include OTC/pink sheets?
- Real-time streaming or polling? Latency?
- Cost for API access (not just the desktop app)?
- Can I get pre-market data (4 AM ET onward)?
- Python SDK or library availability?

**b) Polygon.io**
- Real-time websocket API for trades/quotes — does it cover OTC stocks?
- Historical tick data availability for backtesting?
- How does their symbol universe compare to Databento EQUS.MINI?
- Cost tiers (specifically for real-time + historical + OTC)?
- Python SDK (`polygon-api-client`)?
- Pre-market data availability?

**c) Unusual Whales**
- Do they have a scanner API (not just the web dashboard)?
- Coverage of small-cap / low-float stocks?
- Real-time alerts or streaming?
- Cost?

**d) Benzinga Pro / Benzinga Newsfeed**
- Real-time news + scanner API?
- Can I filter by gap%, float, volume in the API?
- Pre-market coverage?
- Cost for API access?

**e) IEX Cloud**
- Symbol universe — does it include OTC/pink sheets?
- Real-time streaming vs delayed?
- Cost for real-time small-cap data?
- Historical data for backtesting?

**f) Alpaca vs other brokers for OTC**
- Can Alpaca trade OTC stocks at all? If not, which brokers support OTC trading with API access?
- Interactive Brokers TWS API — OTC coverage?
- Webull API — does it exist for programmatic trading?

**g) Any other data providers I should know about**
- Quiver Quant, Finviz API, StockTwits sentiment, Nasdaq TotalView, etc.
- Focus on providers that specifically cover the small-cap/micro-cap/OTC universe

### 2. Float Data Providers Beyond FMP and yfinance

Our current float lookup chain: hardcoded KNOWN_FLOATS dict → float_cache.json → FMP API → yfinance fallback. This fails on ~10% of small-cap tickers.

**Research:**

**a) SEC EDGAR**
- Can I programmatically pull shares outstanding / float from 10-Q, 10-K, or S-1 filings?
- How current is this data? (We need same-day accuracy for new IPOs and recent offerings)
- Is there a Python library for EDGAR parsing?
- Rate limits?

**b) Polygon.io Fundamentals**
- Do they provide float data? Shares outstanding?
- Coverage for micro-cap stocks?
- Real-time or quarterly updates?

**c) Alpha Vantage**
- Float data via their fundamentals endpoint?
- Coverage for small-caps?
- Rate limits on free vs paid tier?

**d) Intrinio**
- Fundamentals API with float data?
- Small-cap coverage?
- Cost?

**e) OpenBB / OpenBB SDK**
- Aggregates multiple data sources — does it improve float resolution?
- Which underlying sources does it use for float data?

**f) Direct exchange data**
- NASDAQ, NYSE, OTC Markets — do they provide float data via API?
- FINRA short interest reports — can these be used to derive float?

**g) Manual/crowdsourced approaches**
- Float data from earnings call transcripts or SEC filings parsed in bulk
- Services that track share issuances, offerings, reverse splits in real-time

### 3. Cost/Latency/Reliability Comparison

For the top 3-4 most promising options from each category, please provide:

| Provider | Coverage | Latency | Cost/mo | Python SDK | OTC? | Pre-market? | Historical? |
|----------|----------|---------|---------|------------|------|-------------|-------------|
| ... | ... | ... | ... | ... | ... | ... | ... |

### 4. Integration Recommendations

Given our architecture (Python 3.13, Alpaca websocket for execution, Databento for backtesting tick data, scanner_sim.py for historical scanning), which combination of providers would you recommend?

Prioritize:
1. **Coverage** — finding the stocks Ross trades that we currently miss
2. **Reliability** — consistent float data, minimal None returns
3. **Cost** — we're a solo trader, not a hedge fund. Under $500/month total preferred.
4. **Latency** — pre-market data by 4 AM ET is essential, sub-second not required
5. **Python friendliness** — good SDK or clean REST API

### 5. Specific Stocks to Test Coverage

These are the 10 stocks we had ZERO data for. For each provider you recommend, can you check whether they would have data for these tickers (as of January 2025)?

- ESHA, INBS, BBX, ARNAZ, AURL, EVAC, AIMX, ZO, NXX, MVNI

Also check these 4 where float data was missing:
- XPON, VRME, GDTC, AMOD

---

## Output Format

Please structure your response as:

1. **Executive Summary** — Top 2-3 recommendations with rationale
2. **Detailed Provider Analysis** — Each provider from sections 1 and 2
3. **Comparison Table** — Side-by-side matrix
4. **Integration Plan** — Concrete steps to add the recommended provider(s) to our Python bot
5. **Cost Summary** — Monthly cost for the recommended stack
6. **Coverage Verification** — Which of the 14 test tickers each provider covers

---

*This research will inform the next phase of Warrior Bot's scanner improvement. The goal is to go from finding 7.4% of Ross's stocks to >50% within 60 days.*
