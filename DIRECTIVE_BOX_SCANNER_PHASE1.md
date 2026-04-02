# DIRECTIVE: Box Scanner — Phase 1 (Scanner Only)

**Date:** April 2, 2026
**Author:** Cowork (Perplexity)
**For:** CC (Claude Code)
**Priority:** P1 — Build when live bot is stable
**Prereqs:** Read `ARCHITECTURE_BOX_STRATEGY.md` first — this directive implements Phase 1 only.

---

## What to Build

`box_scanner.py` — A new file. Completely separate from `ibkr_scanner.py`. Finds range-bound stocks after 10:00 AM ET for mean-reversion trading.

---

## Research Summary: What Makes a Good Box Candidate

Based on deep research across quantitative trading literature, IBKR API capabilities, and professional mean-reversion strategies, here are the evidence-backed scanner criteria:

### The Core Statistical Edge

**ADR Utilization is the #1 predictor.** When a stock has used 60-80% of its Average Daily Range by mid-morning, the probability of it staying within that range for the rest of the day is approximately 62-80% ([Edgeful ADR research](https://www.youtube.com/watch?v=LyRdL7hM8sE), [ForexTester ADR study](https://forextester.com/blog/average-daily-range-indicator/)). At 90%+ utilization, the probability jumps higher — the stock has "used up" its daily move and is likely to mean-revert within the established range.

**Declining volume confirms range behavior.** When volume fades after an initial move, it means momentum traders have moved on and the stock is settling into equilibrium. [Interactive Brokers' own quant research](https://www.interactivebrokers.com/campus/ibkr-quant-news/mean-reversion-strategies-introduction-trading-strategies-and-more-part-i/) confirms this: "Decreasing volume suggests that price is consolidating, favouring mean reversion setups."

**VWAP proximity = equilibrium.** Stocks trading near VWAP are in balance between buyers and sellers. Deviations from VWAP tend to revert — this is the foundational concept behind institutional VWAP execution algorithms. A stock within 2-3% of VWAP at 10 AM is in equilibrium and a good box candidate.

---

## Scanner Criteria (Ordered by Importance)

### Tier 1: Must-Have Filters (Kill switches)

**1. ADR Utilization ≥ 60%**
```python
adr_20d = compute_20d_adr(ib, symbol)  # Average of (high - low) for last 20 daily bars
intraday_range = hod - lod
adr_util = intraday_range / adr_20d
# PASS if adr_util >= 0.60
```
- Compute ADR from IBKR `reqHistoricalData(contract, '', '20 D', '1 day', 'TRADES', ...)`
- This is the single most important filter. No ADR utilization = no box.
- **Why 60%:** Below 60%, the stock may still be trending (hasn't finished its daily move). Above 60%, the remaining range is statistically likely to stay contained.

**2. Price $5 - $100**
```python
# PASS if 5.0 <= last_price <= 100.0
```
- Below $5: too volatile, spreads too wide, prone to manipulation
- Above $100: requires too much capital per share for meaningful position sizing
- Sweet spot for range trading: $10-$50 (most institutional liquidity)

**3. Minimum Session Volume ≥ 200K shares by scan time**
```python
# PASS if session_volume >= 200000
```
- Need liquidity for clean fills on limit orders
- Low volume = wide spreads = slippage eats into box profits
- Can be computed from the bar builder: `sum(bar.volume for bar in session_bars)`

**4. Intraday Range 2% - 15%**
```python
range_pct = (hod - lod) / lod * 100
# PASS if 2.0 <= range_pct <= 15.0
```
- Below 2%: range too tight to profit after commissions/slippage
- Above 15%: stock is too volatile / still trending, not ranging
- This ensures the "box" is tradeable but not chaotic

### Tier 2: Quality Filters (Improve candidate selection)

**5. HOD and LOD Age ≥ 15 minutes**
```python
minutes_since_hod = (scan_time - last_new_hod_time).total_seconds() / 60
minutes_since_lod = (scan_time - last_new_lod_time).total_seconds() / 60
# PASS if minutes_since_hod >= 15 AND minutes_since_lod >= 15
```
- If the stock is still making new highs or lows, it's trending, not ranging
- 15 minutes of "stale" HOD/LOD = the range is established
- Track `last_new_hod_time` and `last_new_lod_time` from bar data

**6. VWAP Proximity ≤ 3%**
```python
vwap_dist_pct = abs(last_price - vwap) / vwap * 100
# PASS if vwap_dist_pct <= 3.0
```
- Stock near VWAP = in equilibrium
- Stock far from VWAP = may be trending or extended
- VWAP is already computed by the bar builder

**7. Volume Decline Ratio < 0.60**
```python
# Compare first 15 min of regular session to most recent 15 min before scan time
# For a 10:00 AM scan: early = 9:30-9:45, recent = 9:45-10:00
# For an 11:00 AM rescan: early = 9:30-9:45, recent = 10:45-11:00
early_vol = sum(bar.volume for bar in bars_930_to_945)
recent_vol = sum(bar.volume for bar in bars_last_15min)
vol_decline = recent_vol / early_vol if early_vol > 0 else 1.0
# PASS if vol_decline < 0.60
```
- Declining volume = momentum exhaustion = ranging behavior
- If recent volume equals or exceeds early volume, the stock is still actively moving
- **IMPORTANT for historical mode:** early_vol is ALWAYS the first 15 min of regular hours (9:30-9:45 ET) as the baseline. recent_vol is the last 15 min before scan time. This ensures the comparison is consistent regardless of scan time. Use 15-min windows (not 30-min) because at a 10:00 AM scan time, there's only 30 min of regular-hours data total.

**8. Low Recent Volatility (Stability Score)**
```python
import statistics
recent_closes = [bar.close for bar in bars_last_30]  # Last 30 1m bars
stdev = statistics.stdev(recent_closes) if len(recent_closes) > 1 else 0
stability = 1 - (stdev / (hod - lod)) if (hod - lod) > 0 else 0
# PASS if stability > 0.50 (stdev is less than 50% of the range)
```
- High stability = stock oscillates predictably within the range
- Low stability = jagged, unpredictable moves (bad for mean reversion)

### Tier 3: Enhancement Filters (Nice to have)

**9. Bid-Ask Spread Check**
```python
spread = ask - bid
spread_pct = spread / last_price * 100
# PREFER spread_pct < 0.5%
```
- Wide spreads eat into box profits (buy at ask, sell at bid = instant loss)
- Requires real-time quote data from IBKR
- **NOTE:** Not available in historical mode. Skip this filter during backtesting.

**10. Not in Earnings/Catalyst Window**
- Stocks with pending earnings or FDA dates may gap overnight or have erratic intraday behavior
- Hard to automate — defer to Phase 2 or manual filtering

---

## IBKR Scanner Implementation

### Option A: Post-Process the HOT_BY_VOLUME Universe (RECOMMENDED)

Use IBKR `reqScannerSubscription` with `HOT_BY_VOLUME` to get the initial universe (liquid, active stocks), then apply our custom box filters. This lets IBKR do the first cut on price/volume so we only pull detailed data for viable candidates.

```python
def scan_box_candidates(ib, scan_time_et):
    """Run at 10:00 AM ET. Returns ranked list of box candidates."""

    # Step 1: Get active stocks from IBKR scanner
    sub = ScannerSubscription()
    sub.instrument = "STK"
    sub.locationCode = "STK.US.MAJOR"
    sub.scanCode = "HOT_BY_VOLUME"  # High volume = liquid
    sub.numberOfRows = 100
    sub.abovePrice = 5.0
    sub.belowPrice = 100.0
    sub.aboveVolume = 200000

    results = ib.reqScannerData(sub)

    # Step 2: Apply cheap filters FIRST (price, volume) to reduce API calls
    # Step 3: Only pull ADR + intraday detail for stocks passing cheap filters
    candidates = []
    for r in results:
        symbol = r.contractDetails.contract.symbol

        # Compute ADR (20-day) — CACHED per symbol per date (see caching section)
        adr = compute_adr_cached(ib, symbol)

        # Get intraday data from bar builder or reqHistoricalData
        hod, lod, vwap, session_vol, bars = get_intraday_data(ib, symbol, scan_time_et)

        # Apply Tier 1 filters
        intraday_range = hod - lod
        if adr <= 0 or intraday_range <= 0:
            continue

        adr_util = intraday_range / adr
        if adr_util < 0.60:
            continue

        range_pct = (intraday_range / lod) * 100
        if not (2.0 <= range_pct <= 15.0):
            continue

        # Apply Tier 2 filters
        last_price = bars[-1].close if bars else 0
        vwap_dist = abs(last_price - vwap) / vwap * 100 if vwap > 0 else 99
        if vwap_dist > 3.0:
            continue

        # ... (remaining filters) ...

        # Score and rank
        score = compute_box_score(adr_util, vwap_dist, vol_decline, stability)
        candidates.append({
            "symbol": symbol,
            "price": last_price,
            "hod": hod,
            "lod": lod,
            "range_pct": range_pct,
            "adr_util": adr_util,
            "vwap": vwap,
            "vwap_dist_pct": vwap_dist,
            "session_volume": session_vol,
            "vol_decline_ratio": vol_decline,
            "stability": stability,
            "box_score": score,
        })

    # Sort by score, return top N
    candidates.sort(key=lambda c: c["box_score"], reverse=True)
    return candidates[:10]  # Top 10
```

### Option B: Use IBKR's Built-In Scan Codes

IBKR has scan codes that partially match our needs:
- `HOT_BY_VOLUME` — liquid stocks
- `NOT_OPEN` — stocks near their open (VWAP proximity proxy)
- `HIGH_VS_13W_HL` — stocks near their 13-week mid-range

But none of these directly scan for "range-bound" or "ADR utilization." **Recommend Option A** — start with HOT_BY_VOLUME for the universe, then apply our custom box filters.

### Historical Mode (for backtesting)

For backtesting, the scanner needs to work on historical data:

```python
def scan_box_historical(ib, date_str, scan_time_et="10:00"):
    """Scan for box candidates on a historical date."""
    # Use reqHistoricalData for each candidate's intraday bars
    # Compute HOD, LOD, VWAP, volume profile from 1-min bars
    # Apply the same filters as live mode
```

This is similar to how `ibkr_scanner.py` has `scan_historical()` — same pattern, different criteria.

**IMPORTANT: Historical mode universe discovery.**
In live mode, `HOT_BY_VOLUME` gives us the universe. In historical mode, there is no equivalent real-time scan. To get the initial universe for a historical date:
1. Use IBKR `reqScannerData` with `HOT_BY_VOLUME` — this returns TODAY's hot stocks, not historical. **NOT usable for backtesting.**
2. **Better approach:** Use `reqHistoricalData` with `TRADES` for a broad watchlist OR pull the day's most active stocks from a pre-built universe list. IBKR does not support historical scanner queries directly.
3. **Pragmatic solution:** Build a universe of ~200-300 liquid stocks ($5-$100, avg volume > 500K/day) once, and scan that list on each historical date by pulling their 1m bars. Cache the list. This is the same approach the momentum scanner's `scan_historical()` uses — it queries known-liquid symbols, not a dynamic scanner.

---

## ADR Caching (CRITICAL for performance)

**Cache ADR per-symbol per-date.** The 20-day ADR for a symbol is the same regardless of how many times we scan it on the same day. Do NOT re-fetch daily bars on every scan checkpoint.

```python
_adr_cache = {}  # {(symbol, date_str): adr_value}

def compute_adr_cached(ib, symbol, date_str=None):
    """Compute 20-day ADR with per-date caching."""
    if date_str is None:
        date_str = datetime.now(ET).strftime("%Y-%m-%d")

    cache_key = (symbol, date_str)
    if cache_key in _adr_cache:
        return _adr_cache[cache_key]

    adr = compute_20d_adr(ib, symbol, date_str)
    _adr_cache[cache_key] = adr
    return adr
```

For the YTD historical scan (~63 dates × ~200 symbols), this avoids re-fetching the same daily bars repeatedly. Also consider saving the cache to disk between runs (`adr_cache.json`) so interrupted runs can resume.

---

## IBKR Rate Limit Awareness

IBKR paces historical data requests: ~60 requests per 10 minutes for 1m bars, less restrictive for daily bars. For the YTD historical run:

- **Daily bars (ADR):** ~200 symbols × 1 request each = 200 requests. At IBKR's rate, ~30-40 min. Cacheable — only need to run once per symbol.
- **Intraday 1m bars:** ~200 symbols × 1 request per date × 63 dates = 12,600 requests. At IBKR's pace, this takes ~35 hours of wall-clock time.

**Mitigation:**
1. Apply price/volume filters from the HOT_BY_VOLUME scan BEFORE pulling intraday bars. This cuts the universe from 200 to ~30-50 per date.
2. Cache intraday bars to disk (same pattern as tick_cache/). If a symbol-date pair is already cached, skip the IBKR call.
3. Add `ib.sleep(0.5)` between requests to stay within pacing limits.
4. Log progress: `[BOX_SCAN] Date 14/63: fetching AAPL intraday bars...`

---

## Scoring Formula

```python
def compute_box_score(adr_util, vwap_dist_pct, vol_decline, stability, hod_age_min, lod_age_min):
    """Higher = better box candidate. Max theoretical score ~10."""

    score = 0.0

    # ADR utilization (0-3 points) — most important
    # 60% = 1.8, 80% = 2.4, 100% = 3.0
    score += min(adr_util, 1.0) * 3.0

    # VWAP proximity (0-2 points) — closer = better
    # 0% dist = 2.0, 1% = 1.3, 3% = 0.0
    vwap_score = max(0, 2.0 - (vwap_dist_pct * 0.67))
    score += vwap_score

    # Volume decline (0-1.5 points) — lower = better
    # 0.2 ratio = 1.5, 0.4 = 1.0, 0.6 = 0.5
    vol_score = max(0, 1.5 - (vol_decline * 2.5))
    score += vol_score

    # Stability (0-2 points) — higher = better
    score += stability * 2.0

    # Level age bonus (0-1.5 points) — older HOD/LOD = more established range
    age_min = min(hod_age_min, lod_age_min)
    age_score = min(age_min / 60, 1.0) * 1.5  # Max at 60+ min old
    score += age_score

    return round(score, 2)
```

---

## Output Format

Save scanner results to `scanner_results_box/YYYY-MM-DD.json`:

```json
{
    "scan_time_et": "10:00",
    "date": "2026-01-14",
    "candidates": [
        {
            "rank": 1,
            "symbol": "AAPL",
            "price": 178.50,
            "hod": 180.20,
            "lod": 176.80,
            "range_pct": 1.92,
            "adr_20d": 3.80,
            "adr_util": 0.89,
            "vwap": 178.30,
            "vwap_dist_pct": 0.11,
            "session_volume": 4500000,
            "vol_decline_ratio": 0.45,
            "stability": 0.72,
            "hod_age_min": 47,
            "lod_age_min": 62,
            "box_score": 8.5
        }
    ]
}
```

---

## VWAP Computation in Historical Mode

In live mode, VWAP comes from the bar builder. In historical mode, compute it from the 1m bars:

```python
def compute_vwap_from_bars(bars):
    """Compute VWAP from 1m bars: sum(typical_price * volume) / sum(volume)."""
    cum_tpv = 0.0
    cum_vol = 0
    for bar in bars:
        typical_price = (bar.high + bar.low + bar.close) / 3
        cum_tpv += typical_price * bar.volume
        cum_vol += bar.volume
    return cum_tpv / cum_vol if cum_vol > 0 else 0.0
```

Include only regular-hours bars (9:30+) in the VWAP calculation, matching standard market VWAP.

---

## Build Steps

1. Create `box_scanner.py` with `scan_box_candidates()` (live) and `scan_box_historical()` (backtest)
2. ADR computation via `reqHistoricalData` — 20 daily bars, cached per-symbol per-date (see caching section above)
3. Intraday data from `reqHistoricalData` 1-min bars for the session up to scan time
4. All filters from Tier 1 and Tier 2 above
5. Scoring formula as specified
6. Save results to `scanner_results_box/`
7. Build a `run_box_scanner_ytd.py` runner script that loops through all YTD dates and calls `scan_box_historical()` for each

## Test Steps

1. Run `scan_box_historical()` across all YTD dates (Jan 2 — Apr 2)
2. Produce a candidate list for each date
3. **STOP. Do not build the strategy yet.**
4. Push results. Cowork and Manny will verify candidates on TradingView.

---

## Env Vars (Scanner Only)

```bash
WB_BOX_MIN_PRICE=5.00
WB_BOX_MAX_PRICE=100.00
WB_BOX_MIN_RANGE_PCT=2.0
WB_BOX_MAX_RANGE_PCT=15.0
WB_BOX_MIN_ADR_UTIL=0.60
WB_BOX_MAX_VWAP_DIST_PCT=3.0
WB_BOX_MIN_SESSION_VOL=200000
WB_BOX_MIN_HOD_AGE_MIN=15
WB_BOX_MIN_LOD_AGE_MIN=15
WB_BOX_VOL_DECLINE_MAX=0.60
WB_BOX_SCAN_TIME_ET=10:00
```

---

## What NOT to Do

- Do NOT build box_strategy.py yet (Phase 2, after scanner validation)
- Do NOT wire into bot_v3_hybrid.py yet (Phase 5)
- Do NOT modify ibkr_scanner.py or any momentum code
- Do NOT trade box candidates — scanner only, output candidates for manual review
- Do NOT use the momentum scanner's stock universe — box scanner finds its OWN stocks
- Do NOT use Alpaca for any scanning — IBKR is the data source, Alpaca is execution ONLY
