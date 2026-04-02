# DIRECTIVE: Box Scanner V2 — Multi-Day Range Detection

**Date:** April 2, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P1  
**Replaces:** The single-day morning range approach from Phase 1. Keep `box_scanner.py` but rewrite the core logic.

---

## Why the Revision

Phase 1 results revealed a fundamental flaw: the morning HOD/LOD creates a "box" that the stock doesn't actually trade within after 10 AM. On April 1, all three candidates (LI, W, DKNG) set their HOD and LOD before 10 AM, then spent the afternoon session either sitting near the middle or slowly drifting toward the bottom. The "buy low, sell high within the box" thesis requires actual oscillation between the box top and bottom — and that didn't happen.

**The fix:** Use multi-day support/resistance levels that have been tested multiple times, not single-morning artifacts. A stock that has bounced off $20 three times in 5 days has real support at $20. A stock that happened to print a $18.56 LOD this morning at 9:15 AM does not.

---

## New Scanner Logic

### Step 1: Find the Multi-Day Range

For each candidate, pull **5 daily bars** (last 5 trading days) from IBKR:

```python
bars = ib.reqHistoricalData(
    contract, '', '5 D', '1 day', 'TRADES', useRTH=True
)
```

Compute:
```python
range_high_5d = max(bar.high for bar in daily_bars[-5:])
range_low_5d = min(bar.low for bar in daily_bars[-5:])
range_size = range_high_5d - range_low_5d
range_pct = (range_size / range_low_5d) * 100
```

### Step 2: Verify Multiple Tests of the Levels

This is the critical difference from V1. A real box has levels that HOLD — the stock approaches them and bounces, repeatedly.

```python
def count_level_tests(daily_bars, level, tolerance_pct=1.0):
    """Count how many days the stock tested a price level (within tolerance).
    A 'test' means the bar's high or low came within tolerance% of the level.
    """
    tests = 0
    tolerance = level * (tolerance_pct / 100)
    for bar in daily_bars:
        # Test of resistance (high approached the level)
        if abs(bar.high - level) <= tolerance:
            tests += 1
        # Test of support (low approached the level)
        if abs(bar.low - level) <= tolerance:
            tests += 1
    return tests

high_tests = count_level_tests(daily_bars, range_high_5d, tolerance_pct=1.0)
low_tests = count_level_tests(daily_bars, range_low_5d, tolerance_pct=1.0)

# REQUIRE: at least 2 tests of the high zone AND 2 tests of the low zone
# This confirms the box is real, not a one-time spike
```

**Why this matters:** If the 5-day high was only touched once (a single spike day) and the 5-day low was only touched once (a different single spike day), those aren't levels — they're outliers. We need levels that the stock has visited multiple times and bounced from.

### Step 3: Verify Stock Is Currently Inside the Range

```python
# Today's price must be INSIDE the 5-day range (not breaking out)
current_price = ticker.last  # or latest bar close
inside_range = range_low_5d <= current_price <= range_high_5d

# Also check: today's HOD and LOD haven't broken the 5-day range
today_hod = max(bar.high for bar in todays_bars)
today_lod = min(bar.low for bar in todays_bars)
range_intact = (today_hod <= range_high_5d * 1.005) and (today_lod >= range_low_5d * 0.995)
# Allow 0.5% tolerance for minor wicks
```

### Step 4: Compute Position Within the Range

```python
# Where is the stock within its 5-day box? (0% = at bottom, 100% = at top)
range_position_pct = ((current_price - range_low_5d) / range_size) * 100

# For BUY candidates: stock should be in the LOWER portion of the range
# (below 35% = approaching support)
# For SELL/exit: stock should be in the UPPER portion
# (above 65% = approaching resistance)
```

### Step 5: Apply Quality Filters

Keep the good filters from V1, adapted for multi-day:

**5a. Minimum Range Size**
```python
# Range must be wide enough to trade profitably
min_range_dollars = max(0.75, current_price * 0.03)  # At least $0.75 or 3% of price
# PASS if range_size >= min_range_dollars
```
This fixes the LI problem ($0.48 range was too tight).

**5b. ADR Utilization (adapted)**
```python
# TODAY's range vs 20-day ADR
# For box trading, we WANT today's range to be SMALL relative to ADR
# (stock is quiet today, staying in the multi-day range)
today_range = today_hod - today_lod
adr_util_today = today_range / adr_20d

# PASS if adr_util_today < 0.80
# If today has already exceeded 80% of ADR, the stock is still moving
# and may break the box
```
Note: this is INVERTED from V1. V1 wanted HIGH ADR utilization (range exhausted). V2 wants LOW today-ADR (stock is quiet, staying in the bigger box).

**5c. Volume and Liquidity**
```python
# 5-day average daily volume > 500K
avg_daily_vol = mean(bar.volume for bar in daily_bars[-5:])
# PASS if avg_daily_vol >= 500000

# Today's volume by scan time > 100K (stock is alive, not dead)
# PASS if session_volume >= 100000
```

**5d. VWAP Proximity**
```python
# Stock near today's VWAP (within 2% — in equilibrium today)
vwap_dist_pct = abs(current_price - vwap) / vwap * 100
# PASS if vwap_dist_pct <= 2.0
```

**5e. Not Trending (Flat Moving Average)**
```python
# 20-day SMA should be relatively flat (not trending strongly)
# Compare SMA today vs SMA 5 days ago
sma_20 = mean(bar.close for bar in daily_bars[-20:])
sma_20_5d_ago = mean(bar.close for bar in daily_bars[-25:-5])
sma_slope_pct = ((sma_20 - sma_20_5d_ago) / sma_20_5d_ago) * 100

# PASS if abs(sma_slope_pct) < 5.0
# A SMA that moved more than 5% in 5 days = strong trend, not a range
```
This is from [SwingTradeBot](https://swingtradebot.com/blog/finding-range-bound-stocks): "Find stocks above their 200 DMA but flat with respect to their 50 & 10 DMAs." We adapt this to a shorter timeframe.

**5f. No Recent Breakout**
```python
# The stock should NOT have gapped more than 5% in the last 5 days
# A recent large gap suggests catalyst-driven movement, not range behavior
for i in range(1, len(daily_bars)):
    gap_pct = abs(daily_bars[i].open - daily_bars[i-1].close) / daily_bars[i-1].close * 100
    if gap_pct > 5.0:
        # FAIL — recent gap, this stock may not be range-bound
        break
```

---

## Scoring Formula (Revised)

```python
def compute_box_score_v2(high_tests, low_tests, range_position_pct, 
                         range_pct, vwap_dist_pct, adr_util_today,
                         vol_ratio, sma_slope_pct):
    """Higher = better box candidate. Max theoretical ~10."""
    
    score = 0.0
    
    # Level strength (0-3 points) — more tests = more reliable box
    # 2 tests each = 2.0, 3 tests each = 2.5, 4+ = 3.0
    level_score = min((high_tests + low_tests) / 4, 1.0) * 3.0
    score += level_score
    
    # Range position (0-2 points) — closer to bottom = better buy opportunity
    # 20% position = 2.0, 35% = 1.0, 50% (middle) = 0.0
    if range_position_pct <= 35:
        pos_score = (35 - range_position_pct) / 35 * 2.0
    else:
        pos_score = 0.0
    score += pos_score
    
    # Range quality (0-2 points) — wider range = more profit potential
    # 3% = 0.6, 5% = 1.0, 8% = 1.6, 10%+ = 2.0
    range_score = min(range_pct / 5.0, 1.0) * 2.0
    score += range_score
    
    # VWAP proximity (0-1.5 points)
    vwap_score = max(0, 1.5 - (vwap_dist_pct * 0.75))
    score += vwap_score
    
    # Quiet today (0-1.5 points) — low today-ADR = stock is calm
    quiet_score = max(0, 1.5 - (adr_util_today * 2.0))
    score += quiet_score
    
    return round(score, 2)
```

---

## Scanner Output Format (Same as V1, Extended)

```json
{
    "scan_time_et": "10:00",
    "date": "2026-04-01",
    "candidates": [
        {
            "symbol": "XYZ",
            "price": 45.20,
            "range_high_5d": 47.50,
            "range_low_5d": 43.00,
            "range_size": 4.50,
            "range_pct": 10.47,
            "high_tests": 3,
            "low_tests": 2,
            "range_position_pct": 48.9,
            "today_hod": 46.10,
            "today_lod": 44.80,
            "adr_util_today": 0.42,
            "vwap": 45.05,
            "vwap_dist_pct": 0.33,
            "avg_daily_vol_5d": 2500000,
            "session_volume": 850000,
            "sma_slope_pct": 1.2,
            "box_score": 7.8
        }
    ]
}
```

---

## What the Box Looks Like Now

```
┌─────────────── 5-Day High ($47.50) ──── SELL ZONE (tested 3x)
│                                          Big seller lives here.
│                                          We sell BEFORE they do.
│
│                   VWAP (~$45.05)          Optional partial exit
│
│
└─────────────── 5-Day Low ($43.00) ──── BUY ZONE (tested 2x)
                                          Big buyer lives here.
                                          We buy BEFORE they do.
```

The mental model: institutional order flow is stacked at these multi-day levels. A big buyer sits at the 5-day low (tested 2-3x and held every time). A big seller sits at the 5-day high (tested 2-3x and rejected every time). We front-run both:

- **Buy** in the lower 25% of the box, just above the big buyer's level
- **Target** the upper 25% of the box, just below the big seller's level
- **VWAP** is an optional partial profit point (take 50% at VWAP, let 50% ride to the top)

The key insight from the V1 failure: V1's levels were morning noise with no real orders behind them. Multi-day levels that have been tested and held multiple times DO have real institutional flow — that's WHY they held. The stock should genuinely oscillate between these levels because the orders are real.

---

## Build Steps

1. **Rewrite `box_scanner.py`** — replace single-morning logic with 5-day multi-day range detection
2. **Add level test counting** — count how many daily bars tested the high zone and low zone
3. **Add SMA slope filter** — reject trending stocks
4. **Add gap filter** — reject recent catalyst-driven gappers
5. **Update scoring** — weight level tests highest, add range position scoring
6. **Run across all YTD dates** — produce new candidate lists
7. **Push results — STOP — we verify on TradingView before proceeding**

---

## Env Vars (Updated)

```bash
# Multi-day range
WB_BOX_RANGE_LOOKBACK_DAYS=5       # How many daily bars to compute the range
WB_BOX_MIN_HIGH_TESTS=2            # Min times the high zone was tested
WB_BOX_MIN_LOW_TESTS=2             # Min times the low zone was tested  
WB_BOX_LEVEL_TOLERANCE_PCT=1.0     # How close a bar needs to get to count as a "test"
WB_BOX_MIN_RANGE_DOLLARS=0.75      # Minimum box width in dollars
WB_BOX_MAX_TODAY_ADR_UTIL=0.80     # Today must be calm (< 80% of ADR used)
WB_BOX_MAX_SMA_SLOPE_PCT=5.0       # SMA must be flat (< 5% change in 5 days)
WB_BOX_MAX_GAP_PCT=5.0             # No gaps > 5% in the lookback period
WB_BOX_MIN_AVG_VOL_5D=500000       # 5-day average volume minimum

# Kept from V1
WB_BOX_MIN_PRICE=5.00
WB_BOX_MAX_PRICE=100.00
WB_BOX_MIN_RANGE_PCT=2.0
WB_BOX_MAX_RANGE_PCT=15.0
WB_BOX_MAX_VWAP_DIST_PCT=2.0       # Tightened from 3.0
WB_BOX_MIN_SESSION_VOL=100000      # Lowered — we have avg_vol_5d as primary filter
WB_BOX_SCAN_TIME_ET=10:00
```

---

## What NOT to Do

- Do NOT keep the single-day morning range as the box definition — it doesn't work
- Do NOT require the stock to oscillate all the way from bottom to top — target VWAP/middle
- Do NOT skip the level test counting — it's the core of what makes this work
- Do NOT build the strategy yet — scanner first, verify, then Phase 2
- Do NOT use the same stock universe as the momentum scanner
