# Gap and Go Strategy Implementation

## Overview
Successfully added Gap and Go strategy to Warrior Bot, based on Ross Cameron's Warrior Trading methodology. This complements the existing Micro Pullback strategy.

---

## What Was Added

### 1. **Premarket High Tracking** ([bars.py](bars.py))
- Tracks premarket high (4:00 AM - 9:30 AM ET) per symbol
- Resets on new trading day
- Available via `get_premarket_high(symbol)`

### 2. **Premarket Bull Flag Detection** ([bars.py](bars.py))
- Automatically detects when price tests premarket high 3+ times
- Marks that level as a "bull flag high"
- Available via `get_premarket_bull_flag_high(symbol)`
- Uses 0.5% tolerance for detecting multiple touches

### 3. **Session Time Helpers** ([bars.py](bars.py))
New methods added:
- `is_premarket(ts_utc)` - checks if 4:00-9:30 AM ET
- `is_market_hours(ts_utc)` - checks if 9:30 AM-4:00 PM ET
- `is_golden_hour(ts_utc)` - checks if 9:30-10:00 AM ET (prime time)

### 4. **Gap and Go Entry Logic** ([micro_pullback.py](micro_pullback.py))
- New `update_premarket_levels()` method to receive PM high from bar builder
- Enhanced `on_trade_price()` to check for premarket high breakouts
- Triggers entry when price breaks:
  - Premarket bull flag high (if detected), OR
  - Premarket high (if no bull flag)
- Uses 2% stop or $0.10 (whichever is larger) below premarket level
- Separate scoring function `_score_gap_and_go()` (more lenient than micro pullback)

### 5. **Entry Signal Formats** ([micro_pullback.py](micro_pullback.py), [trade_manager.py](trade_manager.py))
New signal format:
```
GAP_AND_GO ENTRY @ 10.50 (break PM_HIGH) stop=10.30 R=0.20 score=6.5 macd_score=4.2 tags=[BULL_FLAG] why=...
```

Trade manager now parses both:
- `ENTRY SIGNAL` (micro pullback)
- `GAP_AND_GO ENTRY` (premarket breakout)

### 6. **Bot Integration** ([bot.py](bot.py))
- Passes premarket levels to detector on every trade
- Logs premarket high in bar close events
- Prints premarket summary when market opens:
  ```
  [09:30:00 ET] 📊 SYMBOL PREMARKET COMPLETE | PM_HIGH=10.50 PM_BF_HIGH=10.48
  ```
- Sends both micro pullback and Gap and Go signals to trade manager

### 7. **Configuration** ([.env](.env))
New environment variables:
```bash
# --- Gap and Go Strategy ---
WB_ENABLE_GAP_AND_GO=1          # Enable/disable Gap and Go
WB_GAP_AND_GO_MIN_SCORE=4       # Minimum score for Gap and Go (lower than micro pullback)
```

---

## How It Works

### **Morning Workflow:**

1. **Premarket (4:00 AM - 9:30 AM ET)**
   - Bot tracks highest price during premarket
   - Monitors for bull flag pattern (3+ touches near high)
   - Logs premarket activity

2. **Market Open (9:30 AM)**
   - Bot reports premarket summary to console
   - Marks premarket high and bull flag high as potential entry triggers

3. **Entry Trigger (9:30 AM - 4:00 PM ET)**
   - When price breaks above premarket high (or bull flag high)
   - AND price is above EMA9
   - AND meets minimum score threshold
   - → Generates `GAP_AND_GO ENTRY` signal
   - → Trade manager submits entry order

4. **Parallel with Micro Pullback**
   - Both strategies run simultaneously
   - Micro pullback looks for brief consolidations
   - Gap and Go looks for premarket breakouts
   - First valid signal triggers entry

---

## Ross Cameron Alignment

### ✅ **Now Implemented:**
1. **Premarket high tracking** - Core requirement for Gap and Go
2. **Premarket bull flag detection** - Higher probability setups
3. **Entry trigger on breakout** - Break of premarket levels
4. **9:30-10 AM awareness** - Golden hour tracking (infrastructure ready)

### ⏳ **Still Missing (Lower Priority):**
- Float filtering (<50M shares)
- Gap % screening (20%+, minimum 5%)
- Daily chart EMA checks (above 20/50/200 EMA)
- News catalyst detection
- Dynamic daily scanning vs. static watchlist
- 1-min and 5-min pullback setups (only micro pullbacks currently)

---

## Configuration Guide

### **To Enable Gap and Go:**
```bash
WB_ENABLE_GAP_AND_GO=1
WB_GAP_AND_GO_MIN_SCORE=4
```

### **To Disable Gap and Go (use only Micro Pullback):**
```bash
WB_ENABLE_GAP_AND_GO=0
```

### **Scoring Thresholds:**
- `WB_MIN_SCORE=6` - Micro pullback minimum score (more selective)
- `WB_GAP_AND_GO_MIN_SCORE=4` - Gap and Go minimum score (less selective)

Gap and Go is typically cleaner/simpler, so lower score threshold is appropriate.

---

## Testing Recommendations

### **Monitor These Outputs:**

1. **Premarket Summary (at 9:30 AM):**
   ```
   [09:30:00 ET] 📊 BNRG PREMARKET COMPLETE | PM_HIGH=8.50 PM_BF_HIGH=8.48
   ```

2. **Gap and Go Entry Signals:**
   ```
   [09:31:15 ET] BNRG | GAP_AND_GO ENTRY @ 8.50 (break PM_HIGH) stop=8.33 R=0.17 ...
   ```

3. **Log Files:**
   - Check `logs/events_<run_id>.jsonl`
   - Look for `"event": "premarket_complete"`
   - Look for `"event": "signal_fast"` with `GAP_AND_GO` message

### **Test Scenarios:**

1. **Premarket Activity:**
   - Add symbols that gap up premarket
   - Watch for premarket high tracking
   - Verify bull flag detection if applicable

2. **Market Open Breakout:**
   - Watch for Gap and Go signals at/after 9:30 AM
   - Verify entry orders submitted to Alpaca
   - Check stop loss placement (2% or $0.10 below PM high)

3. **Parallel Operation:**
   - Both Gap and Go and Micro Pullback should work simultaneously
   - Either strategy can trigger entry
   - No conflicts expected

---

## Code Changes Summary

| File | Lines Changed | Description |
|------|---------------|-------------|
| `bars.py` | ~80 lines | Premarket tracking, bull flag detection, session helpers |
| `micro_pullback.py` | ~120 lines | Gap and Go entry logic, scoring, premarket level updates |
| `bot.py` | ~40 lines | Integration, premarket level passing, console output |
| `trade_manager.py` | ~20 lines | Parse Gap and Go signal format |
| `.env` | ~2 lines | Configuration variables |

**Total: ~260 lines of new/modified code**

---

## Next Steps (Priority 2 & 3)

### **Stock Selection Filters (High Impact):**
- Float filtering (<50M shares) - critical for momentum
- Gap % calculation - identify true "gappers"
- Daily EMA position checks - filter weak charts
- Relative volume - detect unusual activity
- Dynamic scanner vs. static watchlist

### **Multiple Timeframe Setups:**
- 5-min pullback setups (less aggressive)
- 1-min pullback setups (moderate)
- Keep micro pullbacks for fastest entries

### **Risk Management:**
- Daily max loss enforcement
- Three consecutive losers = stop trading
- "Breakout or bailout" 5-minute timer

---

## Questions or Issues?

- Check `logs/events_*.jsonl` for detailed event logs
- Console will show premarket highs and Gap and Go signals
- All Gap and Go entries are marked with `GAP_AND_GO ENTRY` prefix
- Scoring is slightly more lenient than micro pullback (threshold=4 vs 6)

Happy trading! 🚀
