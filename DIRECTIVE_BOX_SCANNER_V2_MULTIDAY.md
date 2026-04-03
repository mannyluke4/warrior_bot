# DIRECTIVE: Box Scanner V2 — Multi-Day Range Detection

**Date:** April 3, 2026
**Author:** Cowork (Perplexity + Opus review)
**For:** CC (Claude Code)
**Priority:** P1
**Replaces:** The single-day morning range approach from Phase 1. Keep `box_scanner.py` but rewrite the core logic.

---

## Why the Revision

Phase 1 results revealed a fundamental flaw: the morning HOD/LOD creates a "box" that the stock doesn't actually trade within after 10 AM. On April 1, all three candidates (LI, W, DKNG) set their HOD and LOD before 10 AM, then spent the afternoon session either sitting near the middle or slowly drifting toward the bottom. The "buy low, sell high within the box" thesis requires actual oscillation between the box top and bottom — and that didn't happen.

**The fix:** Use multi-day support/resistance levels that have been tested multiple times, not single-morning artifacts. A stock that has bounced off $20 three times in 5 days has real support at $20. A stock that happened to print a $18.56 LOD this morning at 9:15 AM does not.

---

## New Scanner Logic

### Step 1: Pull Historical Daily Bars

For each candidate, pull **30 calendar days** of daily bars from IBKR. We need 25+ trading days to compute the 20-day SMA and its 5-day-ago comparison. The 5-day range uses the most recent 5 bars.

```python
bars = ib.reqHistoricalData(
    contract, endDateTime, '30 D', '1 day', 'TRADES', useRTH=True
)
# endDateTime = '' for live mode (today)
# endDateTime = '20260401 16:00:00 US/Eastern' for historical mode (scan as of that date)

# Use last 5 bars for range, full set for SMA
daily_bars_5d = bars[-5:]
daily_bars_all = bars  # up to ~21 trading days in 30 calendar days
```

**Historical mode note:** When backtesting, set `endDateTime` to the scan date so that IBKR returns bars PRIOR to that date. This ensures no look-ahead bias. V1 already implemented this pattern in `scan_box_historical()` — reuse that approach.

### Step 2: Find the Multi-Day Range

```python
range_high_5d = max(bar.high for bar in daily_bars_5d)
range_low_5d = min(bar.low for bar in daily_bars_5d)
range_size = range_high_5d - range_low_5d
range_pct = (range_size / range_low_5d) * 100
```

### Step 3: Verify Multiple Tests of the Levels

This is the critical difference from V1. A real box has levels that HOLD — the stock approaches them and bounces, repeatedly.

**IMPORTANT:** Use separate functions for resistance (high) and support (low) tests. A resistance test means the bar's HIGH approached the level (price pushed UP toward it). A support test means the bar's LOW approached the level (price pushed DOWN toward it). Do NOT check both bar.high and bar.low against the same level — that double-counts.

```python
def count_resistance_tests(daily_bars, level, tolerance_pct=1.0):
    """Count how many days the bar's HIGH approached the resistance level.
    Only checks bar.high — a test of resistance means price pushed UP toward it.
    """
    tests = 0
    tolerance = level * (tolerance_pct / 100)
    for bar in daily_bars:
        if abs(bar.high - level) <= tolerance:
            tests += 1
    return tests

def count_support_tests(daily_bars, level, tolerance_pct=1.0):
    """Count how many days the bar's LOW approached the support level.
    Only checks bar.low — a test of support means price pushed DOWN toward it.
    """
    tests = 0
    tolerance = level * (tolerance_pct / 100)
    for bar in daily_bars:
        if abs(bar.low - level) <= tolerance:
            tests += 1
    return tests

high_tests = count_resistance_tests(daily_bars_5d, range_high_5d, tolerance_pct=1.0)
low_tests = count_support_tests(daily_bars_5d, range_low_5d, tolerance_pct=1.0)

# REQUIRE: at least 2 tests of the high zone AND 2 tests of the low zone
# This confirms the box is real, not a one-time spike
```

**Why this matters:** If the 5-day high was only touched once (a single spike day) and the 5-day low was only touched once (a different single spike day), those aren't levels — they're outliers. We need levels that the stock has visited multiple times and bounced from.

### Step 4: Verify Stock Is Currently Inside the Range

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

### Step 5: Compute Position Within the Range

```python
# Where is the stock within its 5-day box? (0% = at bottom, 100% = at top)
range_position_pct = ((current_price - range_low_5d) / range_size) * 100

# For BUY candidates: stock should be in the LOWER portion of the range
# (below 35% = approaching support)
# For SELL/exit: stock should be in the UPPER portion
# (above 65% = approaching resistance)
```

### Step 6: Apply Quality Filters

Keep the good filters from V1, adapted for multi-day:

**6a. Minimum Range Size**
```python
# Range must be wide enough to trade profitably
# Use WB_BOX_MIN_RANGE_PCT (default 2.0%) as the single source of truth
# Also enforce a hard dollar floor of $0.75 to avoid sub-penny-profit boxes
min_range_dollars = max(0.75, current_price * (WB_BOX_MIN_RANGE_PCT / 100))
# PASS if range_size >= min_range_dollars
```
This fixes the LI problem ($0.48 range was too tight).

**6b. ADR Utilization (adapted)**
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

**ADR computation:** Reuse the ADR cache from V1 (`box_adr_cache.json`). ADR = mean of (bar.high - bar.low) over last 20 daily bars. Pull from the 30D bars already fetched in Step 1.

**6c. Volume and Liquidity**
```python
# 5-day average daily volume > 500K
avg_daily_vol = mean(bar.volume for bar in daily_bars_5d)
# PASS if avg_daily_vol >= 500000

# Today's volume by scan time > 100K (stock is alive, not dead)
# PASS if session_volume >= 100000
```

**6d. VWAP Proximity**
```python
# Stock near today's VWAP (within 2% — in equilibrium today)
vwap_dist_pct = abs(current_price - vwap) / vwap * 100
# PASS if vwap_dist_pct <= 2.0
```

**6e. Not Trending (Flat Moving Average)**
```python
# 20-day SMA should be relatively flat (not trending strongly)
# Compare SMA today vs SMA 5 days ago
# Uses daily_bars_all from Step 1 (need 25+ trading days)
sma_20_now = mean(bar.close for bar in daily_bars_all[-20:])
sma_20_5d_ago = mean(bar.close for bar in daily_bars_all[-25:-5])
sma_slope_pct = ((sma_20_now - sma_20_5d_ago) / sma_20_5d_ago) * 100

# PASS if abs(sma_slope_pct) < 5.0
# A SMA that moved more than 5% in 5 days = strong trend, not a range
```

**Edge case:** If fewer than 25 trading days available (e.g., stock IPO'd recently), skip this filter and log a warning. Do NOT fail — just skip.

**6f. No Recent Breakout**
```python
# The stock should NOT have gapped more than 5% in the last 5 days
# A recent large gap suggests catalyst-driven movement, not range behavior
for i in range(1, len(daily_bars_5d)):
    gap_pct = abs(daily_bars_5d[i].open - daily_bars_5d[i-1].close) / daily_bars_5d[i-1].close * 100
    if gap_pct > 5.0:
        # FAIL — recent gap, this stock may not be range-bound
        break
```

---

## Stock Universe

The box scanner uses a **different stock universe** from the momentum scanner.

**Live mode:** Use IBKR `reqScannerData` with `scanCode='HOT_BY_VOLUME'` to get today's actively-traded stocks, then filter by price ($5-$100) and apply all quality filters above. This is the same IBKR scanner V1 used.

**Historical mode:** IBKR does not support historical scanner queries. Use a pre-built universe file:

```python
# box_universe.txt — one symbol per line
# ~200-300 liquid stocks: S&P 500 constituents + popular mid-caps
# Pre-filtered for avg daily volume > 500K and price $5-$100
# Generate once, reuse across all backtest dates
# Update quarterly or when major index reconstitutions happen
```

For the initial YTD backtest, reuse the same ~200 liquid stock universe from V1's `scan_box_historical()`. If V1 didn't persist one, generate it: pull S&P 500 constituents from a static list, add popular mid-cap tickers (e.g., IBKR `TOP_VOLUME_RATE` scanner on a recent date), deduplicate, save to `box_universe.txt`.

---

## Scoring Formula (Revised)

**Note:** This scoring formula is buy-side only — it rewards stocks near the BOTTOM of the range. The strategy Phase 2 will handle sell-side exits separately (target upper zone of range). The scanner's job is to find the best BUY entry candidates.

```python
def compute_box_score_v2(high_tests, low_tests, range_position_pct,
                         range_pct, vwap_dist_pct, adr_util_today,
                         vol_ratio, sma_slope_pct):
    """Higher = better box BUY candidate. Max theoretical ~10."""

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
2. **Pull 30D of daily bars** — need 25+ trading days for SMA slope filter (not just 5D)
3. **Add split level test counting** — `count_resistance_tests` (bar.high vs high) and `count_support_tests` (bar.low vs low) as separate functions
4. **Add SMA slope filter** — reject trending stocks (requires 25 trading days of data)
5. **Add gap filter** — reject recent catalyst-driven gappers
6. **Add stock universe handling** — live mode: IBKR HOT_BY_VOLUME. Historical mode: `box_universe.txt` file (~200-300 liquid stocks)
7. **Update scoring** — weight level tests highest, add range position scoring (buy-side only)
8. **Run across all YTD dates** — produce new candidate lists
9. **Push results — STOP — we verify on TradingView before proceeding**

---

## Env Vars (Updated)

```bash
# Multi-day range
WB_BOX_RANGE_LOOKBACK_DAYS=5       # How many daily bars to compute the range
WB_BOX_MIN_HIGH_TESTS=2            # Min times the high zone was tested (bar.high near level)
WB_BOX_MIN_LOW_TESTS=2             # Min times the low zone was tested (bar.low near level)
WB_BOX_LEVEL_TOLERANCE_PCT=1.0     # How close a bar needs to get to count as a "test"
WB_BOX_MIN_RANGE_DOLLARS=0.75      # Hard dollar floor for minimum box width
WB_BOX_MAX_TODAY_ADR_UTIL=0.80     # Today must be calm (< 80% of ADR used)
WB_BOX_MAX_SMA_SLOPE_PCT=5.0       # SMA must be flat (< 5% change in 5 days)
WB_BOX_MAX_GAP_PCT=5.0             # No gaps > 5% in the lookback period
WB_BOX_MIN_AVG_VOL_5D=500000       # 5-day average volume minimum

# Kept from V1
WB_BOX_MIN_PRICE=5.00
WB_BOX_MAX_PRICE=100.00
WB_BOX_MIN_RANGE_PCT=2.0           # Min range as % of price (primary source of truth for range filter)
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
- Do NOT use Alpaca for scanning or data — IBKR for data, Alpaca for execution ONLY
- Do NOT pull only 5D of daily bars — you need 30D (25+ trading days) for the SMA slope filter
