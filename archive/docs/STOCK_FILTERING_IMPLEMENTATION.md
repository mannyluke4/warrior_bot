# Stock Filtering Implementation (Priority 2)

## Overview
Successfully added stock filtering based on Ross Cameron's Warrior Trading criteria. The bot now dynamically filters the watchlist on startup to focus on high-quality momentum candidates.

---

## What Was Added

### 1. **Stock Filter Module** ([stock_filter.py](stock_filter.py))
New module that implements Ross's selection criteria:

**Key Features:**
- Gap % calculation (current price vs. previous close)
- Relative volume screening (compares to 20-day average)
- Daily EMA position checks (20, 50, 200 EMA)
- Float filtering (placeholder - requires external data source)
- Quality ranking system
- Detailed logging of filter decisions

**Filter Thresholds (from PDF):**
- **Minimum gap:** 5% (configurable)
- **Preferred gap:** 20%
- **Max float:** 50M shares (prefer <10M)
- **Relative volume:** 1.5x average minimum
- **Price range:** $1.00 - $20.00 (small account focus)
- **EMA alignment:** Optional strict filter

### 2. **Bot Integration** ([bot.py](bot.py))
- Imports StockFilter module
- `filter_watchlist()` function applies filters on startup
- Ranks stocks by quality score
- Prints top candidates with gap %, relative volume, rank
- Falls back to unfiltered list if filtering fails
- Passes filtered watchlist to all components

### 3. **Configuration** ([.env](.env))
New environment variables:
```bash
# Stock Filtering (Ross Cameron Criteria)
WB_ENABLE_STOCK_FILTERING=1      # Enable/disable filtering
WB_MIN_GAP_PCT=5                 # Minimum gap % (5%)
WB_PREFERRED_GAP_PCT=20          # Preferred gap % (20%)
WB_MAX_FLOAT=50                  # Max float (50M shares)
WB_PREFERRED_MAX_FLOAT=10        # Preferred float (10M)
WB_MIN_REL_VOLUME=1.5            # Min relative volume (1.5x)
WB_REQUIRE_EMA_ALIGNMENT=0       # Require above all EMAs (strict)
WB_MIN_PRICE=1.00                # Min price ($1)
WB_MAX_PRICE=20.00               # Max price ($20)
```

---

## How It Works

### **Startup Flow:**

1. **Load Raw Watchlist** (from watchlist.txt)
   ```
   📋 Raw watchlist: 36 symbols
   ```

2. **Fetch Stock Data** (per symbol)
   - Get snapshot (current price, prev close, volume)
   - Get 20-day bars (for avg volume and EMAs)
   - Calculate gap %, relative volume, EMA alignment

3. **Apply Filters**
   - Check gap % >= 5%
   - Check relative volume >= 1.5x
   - Check price range ($1-$20)
   - Optional: EMA alignment
   - Optional: Float (if data available)

4. **Rank Passing Stocks**
   - Score based on:
     - Gap % (up to 30 points)
     - Relative volume (up to 20 points)
     - Float size (up to 20 points)
     - EMA alignment (15 points)
     - Price range preference (10 points)

5. **Output Top Candidates**
   ```
   ✅ Filtered watchlist: 12 symbols

   🎯 Top Candidates (by rank):
      BNRG: $8.45 gap=+22.5% vol=3.2x rank=68.5
      ASBP: $4.12 gap=+18.2% vol=2.8x rank=61.3
      ...
   ```

6. **Subscribe to Filtered Symbols**
   - Only filtered symbols get:
     - Live data subscription
     - Historical seeding
     - Detector initialization
     - Trade signals

---

## Example Console Output

```
=== Warrior Bot: LIVE DATA + 10s Bars + Micro Pullback + Gap and Go (PAPER EDITION) ===

📋 Raw watchlist: 36 symbols
   [ASBP, ASTI, BETA, BNRG, BUUU, ...]

🔍 Filtering 36 symbols...
✅ BNRG: $8.45 gap=+22.5% vol=3.2x rank=68.5
✅ ASBP: $4.12 gap=+18.2% vol=2.8x rank=61.3
❌ ASTI: gap 2.1% < 5.0%
❌ BETA: rel_vol 0.8x < 1.5x
...

📊 Filter Results:
   ✅ Passed: 12 stocks
   ❌ Filtered: 24 stocks

✅ Filtered watchlist: 12 symbols
   [ASBP, BNRG, ELAB, HURA, MNTN, ...]

🎯 Top Candidates (by rank):
   BNRG: $8.45 gap=+22.5% vol=3.2x rank=68.5
   ASBP: $4.12 gap=+18.2% vol=2.8x rank=61.3
   ELAB: $6.78 gap=+15.3% vol=2.1x rank=55.2
   ...
```

---

## Data Sources

### **Currently Using:**
- **Alpaca Snapshot API** - current price, prev close, volume
- **Alpaca Bars API** - 20-day history for average volume and EMAs

### **Not Yet Implemented:**
- **Float data** - Requires external source (options below)

### **Float Data Options:**

1. **yfinance Library** (Free, recommended)
   ```python
   pip install yfinance
   ```
   - Uncomment code in `stock_filter.py:get_float_estimate()`
   - Fetches from Yahoo Finance

2. **Polygon.io API** (Paid)
   - High-quality fundamental data
   - Requires API key

3. **Manual Database**
   - Maintain CSV/JSON with float data
   - Update periodically

4. **Skip Float Filtering** (Current)
   - Float filtering disabled
   - Returns `None` for all symbols
   - Other filters still work

---

## Ross Cameron Alignment

### ✅ **Now Implemented:**
1. **Gap % screening** - Identify 5%+ (prefer 20%+) gappers
2. **Relative volume** - Detect 1.5x+ unusual activity
3. **Daily EMA position** - Above 20/50/200 EMA (optional strict)
4. **Price range filtering** - $1-$20 focus (small accounts)
5. **Quality ranking** - Prioritize best setups
6. **Dynamic filtering** - Applied on startup

### ⏳ **Still Missing:**
- **Float filtering** - Need external data source
- **News catalyst detection** - Would require news API
- **Periodic re-filtering** - Currently filters once at startup
- **Scanner UI** - Console output only

### ✅ **Major Win:**
Previously, the bot watched ALL 36 symbols blindly.
Now, it focuses on **top 10-15 momentum candidates** meeting Ross's criteria.

---

## Configuration Guide

### **To Enable Filtering (Default):**
```bash
WB_ENABLE_STOCK_FILTERING=1
```

### **To Disable Filtering (Use Full Watchlist):**
```bash
WB_ENABLE_STOCK_FILTERING=0
```

### **Adjust Filter Thresholds:**

**More Aggressive (Allow More Stocks):**
```bash
WB_MIN_GAP_PCT=3                 # Lower from 5%
WB_MIN_REL_VOLUME=1.0            # Lower from 1.5x
WB_MAX_PRICE=50.00               # Increase from $20
```

**More Selective (Fewer, Higher Quality):**
```bash
WB_MIN_GAP_PCT=10                # Raise from 5%
WB_PREFERRED_GAP_PCT=30          # Raise from 20%
WB_MIN_REL_VOLUME=2.5            # Raise from 1.5x
WB_REQUIRE_EMA_ALIGNMENT=1       # Enforce EMA filter
```

**Small Account Focus (Ross's Recommendation):**
```bash
WB_MIN_PRICE=1.50                # Avoid penny stocks
WB_MAX_PRICE=10.00               # Focus on $1.50-$10
```

---

## Ranking System

Stocks are scored on 0-100+ scale:

| Component | Max Points | Description |
|-----------|-----------|-------------|
| Gap % | 30 | Higher gap = more points (cap at 50%) |
| Relative Volume | 20 | Higher volume = more points (cap at 5x) |
| Float Size | 20 | Lower float = more points |
| EMA Alignment | 15 | All 3 EMAs aligned = bonus |
| Price Range | 10 | $1.50-$10 sweet spot |

**Example Scores:**
- **Excellent:** 70+ points (gap 25%+, vol 3x+, low float, aligned)
- **Good:** 50-70 points (gap 15%+, vol 2x+)
- **Acceptable:** 30-50 points (meets minimums)

---

## Performance Impact

### **Startup Time:**
- **Without filtering:** ~5 seconds
- **With filtering (36 symbols):** ~15-30 seconds
  - 36 snapshot API calls
  - 36 bars API calls (20 days each)
  - EMA calculations

### **API Call Limit:**
- Alpaca free tier: 200 requests/minute
- Filtering uses: 2 calls per symbol
- 36 symbols = 72 calls
- **Well within limits**

### **Optimization:**
- Calls run sequentially (could parallelize)
- Future: Cache results, re-filter less frequently

---

## Testing Recommendations

### **Test Scenarios:**

1. **Normal Operation:**
   - Start bot with filtering enabled
   - Verify 5-15 symbols pass filters
   - Check console shows gap %, rel volume, rank

2. **No Stocks Pass:**
   - Set very strict filters (gap 50%, vol 10x)
   - Bot should fallback to full watchlist
   - Warning printed

3. **Filtering Disabled:**
   - Set `WB_ENABLE_STOCK_FILTERING=0`
   - Bot uses full watchlist (no filtering)

4. **API Errors:**
   - Disconnect internet temporarily
   - Bot should fallback to full watchlist
   - Error logged

### **Monitor:**
- Check `logs/events_*.jsonl` for:
  - `stock_passed_filter` events
  - `stock_filtered_out` events with reasons
  - Filter criteria logged per symbol

---

## Next Steps (Priority 3)

### **Float Data Integration:**
Add yfinance for float filtering:
```python
pip install yfinance
```
Uncomment code in `stock_filter.py:get_float_estimate()`

### **Periodic Re-Filtering:**
- Re-filter every 30 minutes
- Catch new gappers that emerge
- Drop stocks that fade

### **Scanner Display:**
- Rich console table
- Live updating ranks
- Watchlist changes highlighted

### **News Catalyst Detection:**
- Integrate Alpaca News API
- Flag stocks with breaking news
- Bonus points in ranking

---

## Code Changes Summary

| File | Lines Changed | Description |
|------|---------------|-------------|
| `stock_filter.py` | ~400 lines | New module: filtering, ranking, data fetching |
| `bot.py` | ~50 lines | Integration, filter_watchlist(), startup flow |
| `.env` | ~9 lines | Configuration variables |

**Total: ~460 lines of new/modified code**

---

## Troubleshooting

### **Problem: No stocks pass filters**
**Solution:** Lower thresholds (gap 3%, rel vol 1.0x) or disable filtering

### **Problem: Too many stocks pass**
**Solution:** Raise thresholds (gap 10%, rel vol 2.5x) or require EMA alignment

### **Problem: Slow startup**
**Solution:** Reduce watchlist size or disable filtering temporarily

### **Problem: Float filtering not working**
**Solution:** Install yfinance and uncomment code in stock_filter.py

---

Great progress! The bot now focuses on high-quality momentum candidates like Ross teaches. 🚀
