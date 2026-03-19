# Scanner Miss Report: ARTL — 2026-03-18

## The Miss
ARTL appeared on Warrior Trading's scanner on March 18. Ross Cameron made ~$9,000 on it. Our bot didn't even see it.

## ARTL Profile
| Metric | Value |
|--------|-------|
| Prev close (3/17) | $4.85 |
| Float | 0.7M (yfinance) / 2.1M (FMP) |
| PM high | $8.26 (+70% from prev close) |
| PM volume | 18.8M shares |
| Open (9:30) | $6.12 (+26% gap) |
| Session high | $8.34 at 9:56 AM (+72%) |
| Total volume | 58M shares |
| Avg daily vol (prior week) | ~100K shares |
| RVOL | **~580x** (58M / 100K) |

This is a perfect Ross Cameron stock: ultra-low float, massive gap, enormous relative volume, $2-$20 price range.

## Timeline
| Time (ET) | Price | Event |
|-----------|-------|-------|
| 04:01 | $4.85 | First premarket trade (quiet) |
| 07:41 | $4.59 → $6.97 | **EXPLOSION** — news catalyst, 62K shares in 1 min |
| 07:42 | $8.20 high | Peak of first spike (277K vol) |
| 07:43-07:50 | $5.63-$6.40 | Pullback and consolidation |
| 08:00-08:10 | $6.33-$8.26 | Second push to new highs (1.8M vol at 08:00) |
| 08:10 | $8.26 | PM high hit |
| 08:16 | $8.04 | Third push (1.1M vol) |
| 09:30 | $6.12 | Market open |
| 09:56 | $8.34 | Session high |

## Why Our Scanner Missed It

### Failure Point 1: ARTL never reached the StockFilter
ARTL does not appear in any event log (`stock_filtered_out` or `stock_passed_filter`). It was eliminated before the filter ever evaluated it.

### Failure Point 2: The 500-symbol cap
`MarketScanner.prefilter_by_price()` fetches Alpaca snapshots for all ~10,000 active symbols, keeps those in the $2-$20 range with volume > 0, then **caps at 500 symbols** (`WB_SCANNER_MAX_SYMBOLS=500`). The cap takes the first 500 from a set — essentially random. ARTL may have been stock #501.

### Failure Point 3: Snapshot data quality at scan time
The pre-filter uses `snap.latest_trade.price` and `snap.latest_trade.size`. At 4 AM, ARTL had only 218 shares traded at $4.85. The snapshot may have been stale or returned zero volume, causing it to fail the `volume > 0` check. Even at the 7:30 re-scan, the snapshot API may not have reflected the 07:41 explosion in real time.

### Failure Point 4: No gap/volume ranking in pre-filter
The pre-filter selects 500 symbols by price range only — it has **no concept of which stocks are gapping or have unusual volume**. A $3 stock with zero gap and a $3 stock gapping 70% with 580x RVOL are treated identically. The "most interesting" stocks are not prioritized.

### Failure Point 5: The StockFilter gap% calculation
Even if ARTL made it to the StockFilter, the filter computes gap% from `snap.previous_daily_bar.close`. For ARTL, Alpaca returned **no previous daily bar** (our test showed "No prev day bar found" for one API call). Without prev close, gap% computes as 0%, and the stock fails the 10% gap threshold.

## The Core Problem: Two Different Data Worlds

The **backtest scanner** (`scanner_sim.py`) works well because it:
1. Uses Alpaca historical bars for prev close (reliable)
2. Uses FMP API for float (accurate for small caps)
3. Has a known-floats cache
4. Fetches ALL symbols' bars in bulk, then filters
5. Re-scans at 30-min checkpoints with full bar data

The **live scanner** (`market_scanner.py` + `stock_filter.py`) fails because it:
1. Uses Alpaca snapshot API (often stale, missing data)
2. Fetches snapshots one-by-one per stock (500 API calls per scan)
3. No FMP fallback for float
4. Caps at 500 symbols randomly (not by quality)
5. Computes gap% from snapshots, not historical bars

## What Needs to Change

### Option A: Port scanner_sim.py logic to live
Use the same approach as the backtest: fetch previous day close via historical bars, compute gap% from actual bar data, use FMP for float. This is the most reliable but requires restructuring the live scanner.

### Option B: Use Databento for live scanning
You're paying for Databento already. `live_scanner.py` uses Databento to stream ALL US equity quotes and computes gaps in real time. It would have caught ARTL at 07:41 when the price spiked. This is what it was built for.

### Option C: Use IBKR for scanning
TWS has built-in scanners that can find gap-ups, unusual volume, etc. The IBC auto-login is already working.

### Option D: Hybrid — use Alpaca for universe, FMP/Databento for data
Keep the Alpaca asset list for the universe of tradable symbols, but use FMP for float data and either Databento or historical bars for gap/volume computation.

### Immediate Quick Fix
At minimum: remove the 500-symbol cap (or raise it significantly), add FMP float lookups to the live StockFilter, and use historical bars instead of snapshots for gap% computation.

## Impact
ARTL was a +$9,000 trade for Ross Cameron. With our current bot settings and the ARTL setup characteristics (low float, huge gap, massive volume, score would likely be 12+), the bot would have traded it successfully — **if the scanner had found it**.

The scanner is the bottleneck. The trading engine works. The detection works. The exits work. We just can't find the stocks.
