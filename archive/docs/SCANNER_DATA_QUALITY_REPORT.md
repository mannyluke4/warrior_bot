# Scanner Data Quality Report — Why the Live Scanner Finds Nothing
## 2026-03-19

## The Problem
The live bot's scanner has found **zero stocks** across 3 trading days:
- **March 17**: 1 stock passed (CRAQU, a SPAC unit — useless)
- **March 18**: 0 stocks passed (filter fell back to unfiltered 500)
- **March 19**: 0 stocks passed across 6 re-scans (filter correctly returned empty)

Meanwhile, the backtest scanner (`scanner_sim.py`) finds 50-200 candidates per day on the same dates using the same filter thresholds.

## Root Cause: Two Completely Different Data Pipelines

### Backtest Scanner (`scanner_sim.py`) — Works Well
| Data Need | Source | Quality |
|-----------|--------|---------|
| Previous day close | Alpaca historical bars (bulk fetch, all symbols) | Reliable |
| Current price | Alpaca 1-min bars for specific time windows | Reliable |
| Gap % | Computed from historical bars vs prev close | Accurate |
| Volume | Summed from 1-min bars in window | Accurate |
| Relative volume | Current session vol / avg daily vol (20-day) | Accurate |
| Float | FMP API → yfinance fallback → known-floats cache | Good coverage |
| Universe | All active Alpaca symbols (~10K) | Complete |

### Live Scanner (`market_scanner.py` + `stock_filter.py`) — Broken
| Data Need | Source | Quality |
|-----------|--------|---------|
| Previous day close | `snap.previous_daily_bar.close` (Alpaca snapshot) | **Often NULL or stale for small caps** |
| Current price | `snap.latest_trade.price` (Alpaca snapshot) | OK but single point-in-time |
| Gap % | Computed from snapshot price vs snapshot prev close | **Fails when prev close is NULL → gap=0%** |
| Volume | `snap.latest_trade.size` (single trade size, NOT session volume) | **WRONG — this is one trade, not total volume** |
| Relative volume | Computed from 20-day historical bars per symbol (500 individual API calls) | **Slow, often returns 0.00x** |
| Float | Alpaca snapshot (usually NULL for small caps) → yfinance fallback | **Poor — Alpaca rarely has float, yfinance slow/unreliable** |
| Universe | Alpaca assets → price pre-filter → **capped at 500 random symbols** | **Lossy — best stocks may be #501** |

## Evidence: March 19 Filter Rejections

From today's event log, across 3,000 stock evaluations (6 scans × 500 stocks):

| Rejection Reason | Count | % of Total |
|-----------------|-------|------------|
| Gap too low (<10%) | 2,981 | **99%** |
| RVOL too low (<2.0x) | 2,976 | **99%** |
| Float too high (>10M) | 1,781 | 59% |

**99% of stocks show gap=0% and RVOL=0.00x.** This isn't because the market is dead — it's because the data pipeline is returning bad data.

### The RVOL Problem is the Worst
The `StockFilter.get_stock_info()` method computes relative volume by:
1. Fetching 20 days of daily bars for each individual symbol (1 API call per stock)
2. Computing average daily volume
3. Comparing current snapshot volume to the average

But `snap.latest_trade.size` returns the **size of the most recent single trade** (e.g., 100 shares), not the total session volume. So RVOL computes as:
```
rvol = 100 shares / 500,000 avg daily = 0.0002x
```
This means RVOL will **always** be near zero for every stock.

### The Gap% Problem
`snap.previous_daily_bar` returns NULL for many small-cap stocks, especially those that:
- Recently reverse-split (like ARTL)
- Trade thinly (low daily volume)
- Are newly listed

When prev close is NULL, the code falls back to using current price as prev close, resulting in gap=0%.

## What We're Paying For But Not Using

| Service | Cost | What It Could Do | Currently Used For |
|---------|------|-----------------|-------------------|
| **Alpaca Premium** | Paid | SIP data feed, historical bars | Snapshot API (weakest endpoint) |
| **Databento** | Paid | Real-time streaming ALL US equities, BBO + trades | `live_scanner.py` (not running) |
| **Interactive Brokers** | Paid | Real-time scanners, market data, fundamentals | TWS auto-login only (data unused) |
| **FMP API** | Paid | Float data, fundamentals, financial statements | Only used in `scanner_sim.py` (backtest) |
| **yfinance** | Free | Float fallback, basic fundamentals | Fallback in `live_scanner.py` + `stock_filter.py` |

The live bot uses the **weakest data source** (Alpaca snapshots) for its most critical function (scanning), while three paid premium services sit idle.

## The `live_scanner.py` Solution Already Exists

`live_scanner.py` was built specifically for this problem. It:
1. Streams ALL US equity quotes via Databento (`EQUS.MINI` dataset)
2. Computes gap% in real time using previous-day close (bulk fetched via Databento Historical)
3. Filters by price ($2-$20), gap (≥5%), and float (via FMP + yfinance + known-floats cache)
4. Writes qualifying candidates to `watchlist.txt` continuously from 7:00-11:00 AM ET
5. Updates every 5 minutes as new candidates emerge

It would have caught ARTL at **07:41 AM** when the price spiked from $4.59 to $6.97 — within seconds of the move.

**Why it's not running:** The current setup was configured for "simplest working setup first" — Alpaca only, no Databento. This was the right decision for initial automation, but the scanner quality gap is now the #1 bottleneck.

## Comparison: What Each Scanner Would Find on March 18

| Scanner | Candidates Found | ARTL Found? | First Alert |
|---------|-----------------|-------------|-------------|
| `market_scanner.py` (live, Alpaca snapshots) | 0 passing filter | **NO** | Never |
| `scanner_sim.py` (backtest, Alpaca historical) | ~100+ candidates | Yes (in rescan) | ~08:00 ET |
| `live_scanner.py` (Databento streaming) | Would find all gappers | **YES** | **07:41 ET** |
| Warrior Trading scanner (Ross's) | All gappers | **YES** | **07:30-07:40 ET** |

## Options for Fixing the Scanner

### Option A: Activate `live_scanner.py` (Databento) — Fastest Fix
- Already built and tested
- Uses Databento subscription you're already paying for
- Real-time gap detection across all US equities
- Would have caught ARTL at 07:41
- Writes to `watchlist.txt` which bot already reads
- **Risk:** Databento costs are usage-based — need to verify streaming costs

### Option B: Port `scanner_sim.py` Logic to Live
- Use Alpaca historical bars (not snapshots) for prev close and volume
- Use FMP API for float data (already have the key)
- Fetch bars in bulk rather than per-symbol snapshots
- More reliable than snapshots but still not real-time
- **Risk:** Slower than Databento, may miss fast movers like ARTL

### Option C: Use IBKR Scanners
- TWS has built-in market scanners (top gainers, unusual volume, etc.)
- Can be accessed programmatically via `ib_insync`
- Already have TWS running and auto-logging in
- **Risk:** Need to build the integration, IBKR API can be quirky

### Option D: Hybrid — Databento for Scanning, Alpaca for Execution
- `live_scanner.py` finds candidates via Databento streaming
- Bot reads `watchlist.txt` and subscribes via Alpaca data feed
- Execution stays on Alpaca paper trading
- This is likely the intended architecture based on how the files are structured
- **Risk:** Two data feeds running simultaneously

### Recommended Path: Option D (Hybrid)
The code already exists for this. `live_scanner.py` writes to `watchlist.txt`, `bot.py` reads from `watchlist.txt`. The pieces just need to be connected:
1. Start `live_scanner.py` in `daily_run.sh` alongside `bot.py`
2. Disable `WB_ENABLE_DYNAMIC_SCANNER` (don't use the broken Alpaca scanner)
3. Bot reads `watchlist.txt` in manual mode, picks up Databento scanner candidates
4. Keep Alpaca as the data feed for price streaming and execution

## Impact
The scanner is the #1 bottleneck. The trading engine works (+$19K on 49-day backtest). The exits work (5 fixes validated). The detection works (score 12.0 on ARTL when it finally ARM'd). But none of that matters if the scanner can't find the stocks.

ARTL alone was a $9,653 opportunity for Ross. Our bot could have captured $922 even with the late entry. With a working scanner alerting at 07:41 and the methodology improvements discussed in the ARTL gap analysis, the capture rate would be much higher.

---

*Report created: 2026-03-19 | Mac Mini CC*
