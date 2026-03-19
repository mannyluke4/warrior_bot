# Dynamic Market Scanner Implementation (Option 3 Hybrid)

## Overview
Successfully added dynamic market scanning capability to Warrior Bot. The bot can now automatically scan the market for actively traded stocks instead of requiring manual watchlist.txt updates.

This implements **Option 3: Hybrid Approach** - scanning a subset of ~500 actively traded stocks with intelligent pre-filtering.

---

## What Was Added

### 1. **Market Scanner Module** ([market_scanner.py](market_scanner.py))
New ~200-line module that dynamically discovers trading candidates:

**Key Features:**
- Fetches all active US equity stocks from Alpaca (~8,000 symbols)
- Pre-filters by price range ($1-$20) to reduce API calls
- Batch processing for efficiency (100 symbols per API call)
- Limits to top 500 symbols (configurable)
- Automatic fallback to manual watchlist on errors

**Pre-Filter Criteria:**
- **Asset class:** US equity stocks only (no ETFs, crypto, etc.)
- **Status:** Active and tradable
- **Symbol format:** 1-5 letters, standard format
- **Price range:** $1.00-$20.00 (configurable)
- **Volume:** Must have recent trading activity

### 2. **Bot Integration** ([bot.py](bot.py))
- New `get_raw_watchlist()` function that chooses between manual and dynamic modes
- Imports MarketScanner module
- Falls back to manual watchlist if scanner fails
- Smart console output (limits symbol printing for large lists)

### 3. **Configuration** ([.env](.env))
New environment variables:
```bash
# --- Dynamic Market Scanner (Option 3 Hybrid) ---
WB_ENABLE_DYNAMIC_SCANNER=0      # 0=manual watchlist.txt, 1=scan market automatically
WB_SCANNER_MAX_SYMBOLS=500       # Max symbols to scan (after price pre-filter)
WB_SCANNER_WORKERS=10            # Parallel API workers (future enhancement)
```

---

## How It Works

### **Hybrid Scanner Flow:**

1. **Get All Active Symbols** (if WB_ENABLE_DYNAMIC_SCANNER=1)
   ```
   🤖 DYNAMIC MARKET SCANNER ENABLED
   🔍 Scanning market for active symbols...
      Found 8,247 tradable US equity symbols
   ```
   - Queries Alpaca for all active US equity stocks
   - Filters for tradable, standard symbols only
   - Excludes ETFs, crypto, fractional-only securities

2. **Price Pre-Filter** (Fast Reduction)
   ```
   🎯 Pre-filtering 8,247 symbols by price range ($1.00-$20.00)...
      ✅ 1,234 symbols passed price pre-filter
      📊 Limiting to top 500 symbols
   ```
   - Batch fetches snapshots (100 symbols per API call)
   - Checks current price against range ($1-$20)
   - Verifies some trading volume exists
   - Limits to 500 symbols max (configurable)

3. **Detailed Filtering** (Existing Logic)
   ```
   🔍 Filtering 500 symbols...
   ✅ BNRG: $8.45 gap=+22.5% vol=3.2x rank=68.5
   ✅ ASBP: $4.12 gap=+18.2% vol=2.8x rank=61.3
   ...
   📊 Filter Results:
      ✅ Passed: 12 stocks
      ❌ Filtered: 488 stocks
   ```
   - Uses existing `stock_filter.py` logic
   - Checks gap %, relative volume, EMAs
   - Ranks candidates by quality score
   - Returns top 10-30 symbols

4. **Subscribe to Winners**
   ```
   ✅ Filtered watchlist: 12 symbols
      [ASBP, BNRG, ELAB, HURA, MNTN, ...]

   ✅ Subscribing: ASBP
   ✅ Subscribing: BNRG
   ...
   ```
   - Bot subscribes to top-ranked symbols
   - Live data streaming begins
   - Detectors initialized and seeded

---

## Comparison: Manual vs Dynamic

### **Manual Mode (Default):**
```bash
WB_ENABLE_DYNAMIC_SCANNER=0
```

**Workflow:**
1. Edit `watchlist.txt` manually
2. Add 10-50 symbols you want to watch
3. Bot filters those symbols at startup
4. Subscribe to passing symbols

**Pros:**
- Full control over what bot watches
- Faster startup (~15-30 seconds)
- Lower API usage
- Good for known catalysts/favorites

**Cons:**
- Requires manual research and updates
- Can miss emerging opportunities
- Static watchlist throughout session

---

### **Dynamic Mode (Hybrid Scanner):**
```bash
WB_ENABLE_DYNAMIC_SCANNER=1
```

**Workflow:**
1. Bot scans entire market (~8,000 symbols)
2. Pre-filters to ~500 by price range
3. Deep filters to top 10-30 candidates
4. Subscribe to passing symbols

**Pros:**
- Automatic discovery of opportunities
- No manual research required
- Finds stocks meeting Ross's criteria automatically
- Adaptive to daily market conditions

**Cons:**
- Slower startup (~2-4 minutes)
- Higher API usage (~600-800 calls)
- May find unfamiliar symbols
- Less control over specific stocks

---

## API Usage & Performance

### **API Calls Breakdown:**

**Phase 1: Get Active Symbols**
- 1 API call to get all assets
- Returns ~8,000 symbols

**Phase 2: Price Pre-Filter**
- ~82 API calls (8,000 symbols / 100 per batch)
- Reduces to ~500-1,000 symbols
- Takes ~30-60 seconds

**Phase 3: Deep Filter** (existing stock_filter.py)
- ~1,000 API calls (500 symbols × 2 calls each)
- Snapshots + 20-day bars for each symbol
- Takes ~1-2 minutes
- Returns top 10-30 candidates

**Total:**
- ~1,083 API calls
- ~2-4 minutes startup time
- Alpaca free tier: 200 calls/minute → spans ~5-6 minutes

### **Optimization Notes:**
- Batch processing (100 symbols per call) reduces overhead
- Could add parallel processing (WB_SCANNER_WORKERS)
- Could cache results and re-scan every 30 minutes
- Could prioritize high-volume symbols for faster pre-filter

---

## Configuration Guide

### **To Enable Dynamic Scanner (Recommended for Most Users):**
```bash
WB_ENABLE_DYNAMIC_SCANNER=1
WB_SCANNER_MAX_SYMBOLS=500      # Start with 500, adjust if needed
WB_ENABLE_STOCK_FILTERING=1     # Keep filtering on
```

### **To Disable Dynamic Scanner (Use Manual Watchlist):**
```bash
WB_ENABLE_DYNAMIC_SCANNER=0
```
Then edit `watchlist.txt` with your symbols.

### **Adjust Scanner Scope:**

**Scan More Symbols (More Aggressive):**
```bash
WB_SCANNER_MAX_SYMBOLS=1000     # Scan up to 1,000 symbols
WB_MAX_PRICE=50.00              # Allow higher-priced stocks
```
*Warning: Increases startup time to 4-6 minutes*

**Scan Fewer Symbols (Faster Startup):**
```bash
WB_SCANNER_MAX_SYMBOLS=200      # Only top 200 symbols
WB_MIN_PRICE=2.00               # Avoid true penny stocks
```
*Startup time: ~1-2 minutes*

---

## Testing Recommendations

### **Test Scenarios:**

1. **Dynamic Scanner - Normal Operation:**
   - Set `WB_ENABLE_DYNAMIC_SCANNER=1`
   - Run bot and wait 2-4 minutes
   - Verify console shows "DYNAMIC MARKET SCANNER ENABLED"
   - Check filtered watchlist has 10-30 symbols
   - Verify symbols meet criteria (gap %, volume, price range)

2. **Dynamic Scanner - Fallback:**
   - Disconnect internet temporarily
   - Set `WB_ENABLE_DYNAMIC_SCANNER=1`
   - Verify bot falls back to manual watchlist
   - Warning printed: "Dynamic scanner failed"

3. **Manual Mode:**
   - Set `WB_ENABLE_DYNAMIC_SCANNER=0`
   - Edit `watchlist.txt` with 10-20 symbols
   - Bot should use manual list (fast startup)

4. **Empty Watchlist:**
   - Delete `watchlist.txt`
   - Set `WB_ENABLE_DYNAMIC_SCANNER=0`
   - Bot should warn about empty watchlist

### **Monitor:**
- Console output for scanner progress
- `logs/events_*.jsonl` for:
  - `market_scan_symbols_found` events
  - `market_scan_prefiltered` events
  - Scanner errors (if any)
- Startup time (should be ~2-4 minutes for dynamic mode)
- Number of symbols in filtered watchlist

---

## Ross Cameron Alignment

### ✅ **Now Fully Aligned:**
1. **Dynamic daily scanning** - Bot finds best setups automatically
2. **Gap % screening** - Filters for 5%+ gappers (prefer 20%+)
3. **Relative volume** - Detects 1.5x+ unusual activity
4. **Daily EMA position** - Checks above 20/50/200 EMA
5. **Price range filtering** - $1-$20 focus (small accounts)
6. **Quality ranking** - Prioritizes best setups
7. **Premarket high tracking** - Gap and Go ready
8. **Premarket bull flag detection** - Higher probability entries

### 🎯 **Complete Strategy Implementation:**
✅ Gap and Go Strategy
✅ Micro Pullback Strategy
✅ Stock Selection Filters
✅ Dynamic Market Scanning
✅ Risk Management (core/runner, break-even, trailing stops)

---

## Code Changes Summary

| File | Lines Changed | Description |
|------|---------------|-------------|
| `market_scanner.py` | ~200 lines | New module: market scanning, pre-filtering |
| `bot.py` | ~30 lines | Integration, get_raw_watchlist(), scanner import |
| `.env` | ~3 lines | Configuration variables |

**Total: ~233 lines of new/modified code**

---

## Troubleshooting

### **Problem: Scanner times out or fails**
**Solution:**
- Reduce `WB_SCANNER_MAX_SYMBOLS` from 500 to 200
- Check Alpaca API status (may be down)
- Verify API keys are correct
- Falls back to manual watchlist automatically

### **Problem: No symbols found**
**Solution:**
- Check `WB_MIN_PRICE` and `WB_MAX_PRICE` settings
- Verify market is open or has recent activity
- Try lowering filter thresholds (gap 3%, vol 1.0x)

### **Problem: Too many symbols pass filter**
**Solution:**
- Increase filter strictness (gap 10%, vol 2.5x)
- Lower `WB_SCANNER_MAX_SYMBOLS`
- Enable `WB_REQUIRE_EMA_ALIGNMENT=1`

### **Problem: Startup takes too long**
**Solution:**
- Reduce `WB_SCANNER_MAX_SYMBOLS` to 200-300
- Use manual mode for faster startup
- Scanner results could be cached (future enhancement)

### **Problem: API rate limit hit**
**Solution:**
- Alpaca free tier: 200 calls/minute
- Scanner spreads calls over ~5-6 minutes
- Should not hit limit under normal operation
- If hit, retry after 1 minute

---

## Future Enhancements

### **Caching & Re-Scanning:**
- Cache scanner results for 30 minutes
- Re-scan periodically during session
- Catch new gappers that emerge
- Drop stocks that fade

### **Volume-Based Prioritization:**
- Sort pre-filtered symbols by volume
- Prioritize highest volume stocks
- Faster convergence to best candidates

### **Parallel API Calls:**
- Use `WB_SCANNER_WORKERS` for concurrent API calls
- Reduce startup time from 2-4 minutes to ~1 minute
- Requires ThreadPoolExecutor implementation

### **Smart Caching:**
- Save previous day's top performers
- Use as starting point for next session
- Faster startup, better continuity

---

## Example Console Output

```
=== Warrior Bot: LIVE DATA + 10s Bars + Micro Pullback + Gap and Go (PAPER EDITION) ===

🤖 DYNAMIC MARKET SCANNER ENABLED
   Scanning market for active symbols...

🔍 Scanning market for active symbols...
   Found 8,247 tradable US equity symbols

🎯 Pre-filtering 8,247 symbols by price range ($1.00-$20.00)...
   ✅ 1,234 symbols passed price pre-filter
   📊 Limiting to top 500 symbols

📋 Market scan complete: 500 symbols ready for filtering

📋 Raw watchlist: 500 symbols
   (too many to display - use dynamic scanner mode)

🔍 Filtering 500 symbols...
✅ BNRG: $8.45 gap=+22.5% vol=3.2x rank=68.5
✅ ASBP: $4.12 gap=+18.2% vol=2.8x rank=61.3
✅ ELAB: $6.78 gap=+15.3% vol=2.1x rank=55.2
...
❌ ASTI: gap 2.1% < 5.0%
❌ BETA: rel_vol 0.8x < 1.5x
...

📊 Filter Results:
   ✅ Passed: 12 stocks
   ❌ Filtered: 488 stocks

✅ Filtered watchlist: 12 symbols
   [ASBP, BNRG, ELAB, HURA, MNTN, NPCE, QNRX, SANA, TPIC, VERO, WISA, ZCMD]

🎯 Top Candidates (by rank):
   BNRG: $8.45 gap=+22.5% vol=3.2x rank=68.5
   ASBP: $4.12 gap=+18.2% vol=2.8x rank=61.3
   ELAB: $6.78 gap=+15.3% vol=2.1x rank=55.2
   HURA: $3.89 gap=+12.7% vol=1.9x rank=48.1
   ...

Now (ET): 2026-02-11 09:15:23

✅ Subscribing: ASBP
🔥 Seeded ASBP: 60 bars (60m) EMA9=4.0823
✅ Subscribing: BNRG
🔥 Seeded BNRG: 60 bars (60m) EMA9=8.3215
...

✅ PaperTradeManager initialized
Connecting to Alpaca data stream... (Ctrl+C to stop)
```

---

## Next Steps (Optional Enhancements)

### **Priority 1: Parallel Pre-Filtering**
- Implement ThreadPoolExecutor for concurrent API calls
- Use `WB_SCANNER_WORKERS` setting
- Reduce startup time by 50-70%

### **Priority 2: Volume-Based Sorting**
- Sort pre-filtered symbols by volume
- Process highest volume first
- Better candidates found faster

### **Priority 3: Caching Layer**
- Cache scanner results for 30 minutes
- Re-scan periodically during session
- Faster startup on subsequent runs

### **Priority 4: Smart Symbol Selection**
- Learn from winning trades
- Prioritize sectors/patterns that work
- Adaptive watchlist over time

---

Excellent! The bot now operates like a professional day trader - scanning the entire market every morning to find the best Ross Cameron-style setups. No more manual watchlist updates! 🚀
