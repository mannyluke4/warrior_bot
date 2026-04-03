# DIRECTIVE: Box Strategy Phase 2 — Build + Per-Candidate YTD Backtest

**Date:** April 3, 2026
**Author:** Cowork (Opus)
**For:** CC (Claude Code)
**Priority:** P1
**Depends on:** Phase 1 scanner complete (V2 multi-day, 664 candidates verified)

---

## What This Directive Covers

Two deliverables:

1. **Build `box_strategy.py`** — the entry/exit engine for mean-reversion box trading
2. **Build `box_backtest.py`** — a per-candidate backtester that runs the strategy on ALL 664 scanner results and produces per-candidate P&L for pattern analysis

This is NOT a combined backtest with squeeze. This is box-only, isolated, so we can measure the strategy's standalone edge before wiring anything into the live bot.

---

## Part 1: box_strategy.py

### Core Concept

Buy near the bottom of a proven 5-day range, sell near the top. The range is defined by the scanner's `range_high_5d` and `range_low_5d` — multi-day levels tested 2+ times each. This is mean-reversion, not momentum.

### Box Definition (From Scanner Output)

The scanner already computed everything. The strategy receives a candidate dict and uses its levels directly:

```python
box_top = candidate["range_high_5d"]       # 5-day resistance (tested 2+ times)
box_bottom = candidate["range_low_5d"]     # 5-day support (tested 2+ times)
box_range = box_top - box_bottom
box_mid = (box_top + box_bottom) / 2
```

**CRITICAL:** Do NOT recompute the box from intraday data. The box is the 5-day multi-day range from the scanner. Today's HOD/LOD are NOT the box — they're just used to check if the box is still intact.

### Entry Zones

```
┌─────────────── box_top (range_high_5d) ──── SELL ZONE (top 25%)
│                                              Exit target zone
│
│               box_mid (~VWAP)                Partial exit zone
│
│
└─────────────── box_bottom (range_low_5d) ── BUY ZONE (bottom 25%)
                                               Entry zone
```

```python
buy_zone_ceiling = box_bottom + box_range * (WB_BOX_BUY_ZONE_PCT / 100)  # default 25%
sell_zone_floor = box_top - box_range * (WB_BOX_SELL_ZONE_PCT / 100)      # default 25%
```

### Entry Signal — ALL Must Be True

1. **Price in buy zone:** `current_price <= buy_zone_ceiling`
2. **RSI oversold:** RSI(14) on 1-minute bars < `WB_BOX_RSI_OVERSOLD` (default 35)
3. **Reversal confirmation:** Current 1m bar is green (close > open) AND prior bar was red (close < open). This is the simplest reversal signal — a green bar after a red bar at support.
4. **Volume confirmation:** Current bar volume >= 1.0x the 20-bar average volume (not a dead stock, but no extreme spike needed)
5. **No open position:** Only one box position at a time
6. **Time gate:** Current time < `WB_BOX_LAST_ENTRY_ET` (default 14:30 ET)
7. **Box still valid:** Today's HOD hasn't broken box_top by > 0.5% AND today's LOD hasn't broken box_bottom by > 0.5%
8. **Session loss cap not hit:** Cumulative box losses today < `WB_BOX_MAX_LOSS_SESSION` (default $500)
9. **Re-entry limit not hit:** This symbol hasn't been entered `WB_BOX_MAX_ENTRIES_PER_STOCK` times today (default 2)

### RSI Computation

Standard RSI(14) on 1-minute closes:

```python
def compute_rsi(closes, period=14):
    """Standard Wilder RSI on a list of close prices."""
    if len(closes) < period + 1:
        return 50.0  # neutral if not enough data
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
```

### Position Sizing

```python
# Risk per trade = distance from entry to hard stop
risk_per_share = entry_price - hard_stop_price
shares = int(WB_BOX_MAX_NOTIONAL / entry_price)

# Cap by risk: if R is too small, notional cap controls; if R is large, risk cap controls
max_risk_dollars = 200  # max risk per individual trade (configurable)
if risk_per_share > 0:
    risk_shares = int(max_risk_dollars / risk_per_share)
    shares = min(shares, risk_shares)

notional = shares * entry_price
# Final notional must be <= WB_BOX_MAX_NOTIONAL
```

### Exit Rules (Priority Order)

Check these in order every tick/bar. First match wins.

**1. Box Invalidation Exit (highest priority)**
```python
# If today's price has broken the box by > 0.5% of box_range, exit immediately
# This means the mean-reversion thesis is dead
if current_price > box_top + box_range * 0.005:
    exit("box_invalidation_high")
if current_price < box_bottom - box_range * 0.005:
    exit("box_invalidation_low")
```

**2. Hard Stop**
```python
# Stop below box_bottom with a pad
hard_stop = box_bottom - (box_bottom * WB_BOX_STOP_PAD_PCT / 100)  # default 0.5%
if current_price <= hard_stop:
    exit("hard_stop")
```

**3. Time Stop**
```python
# Close all box positions at 3:45 PM ET — no overnight holds, non-negotiable
if current_time_et >= WB_BOX_HARD_CLOSE_ET:  # default 15:45
    exit("time_stop")
```

**4. Session Loss Cap**
```python
# If cumulative box P&L today hits -$500, close position and stop trading
if session_box_pnl + unrealized_pnl <= -WB_BOX_MAX_LOSS_SESSION:
    exit("session_loss_cap")
```

**5. Target Exit (sell zone)**
```python
# Full exit when price reaches the sell zone
if current_price >= sell_zone_floor:
    exit("target_sell_zone")
```

Note on partial exits: For the initial backtest, use FULL exit at sell zone. Partial exits add complexity — we'll optimize after we see baseline results. Keep it simple.

**6. VWAP Exit (optional mid-target)**
```python
# If WB_BOX_VWAP_EXIT_ENABLED=1, exit at VWAP when entry was below VWAP
# More conservative but potentially higher win rate
# DEFAULT: OFF for initial backtest (we want to see full box range performance)
if WB_BOX_VWAP_EXIT_ENABLED and current_price >= vwap and entry_price < vwap:
    exit("vwap_target")
```

**7. Trailing Stop**
```python
# Once price has moved > 50% of box_range from entry, activate trail
# Trail distance = 30% of box_range from peak
peak_price = max(peak_price, current_price)
trail_distance = box_range * (WB_BOX_TRAIL_PCT / 100)  # default 30%

# Only activate trail after meaningful profit (50% of range from entry)
if peak_price - entry_price >= box_range * 0.5:
    trail_stop = peak_price - trail_distance
    if current_price <= trail_stop:
        exit("trailing_stop")
```

### State Machine

```python
class BoxTradeState:
    """Tracks one box trade from entry to exit."""
    symbol: str
    entry_price: float
    entry_time: datetime
    shares: int
    box_top: float
    box_bottom: float
    box_range: float
    hard_stop: float
    peak_price: float  # highest price since entry (for trail)
    exit_price: float = None
    exit_time: datetime = None
    exit_reason: str = None
    pnl: float = None
```

### Re-Entry Rules

After a box trade exits (at target or via trail — NOT via stop/invalidation):
- Same box must still be valid (no breakout since last scan)
- Price must return to buy zone
- All entry criteria must be met again (RSI, reversal, volume)
- Re-entry count < `WB_BOX_MAX_ENTRIES_PER_STOCK` (default 2)

After a hard stop, box invalidation, or session loss cap: NO re-entry on that stock today.

---

## Part 2: box_backtest.py — Per-Candidate YTD Backtest

### What This Does

For EACH of the 664 scanner candidates, run box_strategy.py on that stock-date and record the result. This gives us a 664-row dataset we can analyze for patterns.

### Data Source

Pull 1-minute bars from IBKR for each candidate on its scan date. The backtest window is **10:00 AM - 3:45 PM ET** (box window only — momentum is 7-10 AM and not relevant here).

```python
bars_1m = ib.reqHistoricalData(
    contract,
    endDateTime=f'{date_str.replace("-", "")} 16:00:00 US/Eastern',
    durationStr='1 D',
    barSizeSetting='1 min',
    whatToShow='TRADES',
    useRTH=True
)
# Filter to 10:00-15:45 ET only
box_bars = [b for b in bars_1m if time(10, 0) <= b.date.time() <= time(15, 45)]
```

**IMPORTANT:** Use `useRTH=True` so we get regular trading hours only. The box strategy does NOT trade pre-market.

### Backtest Logic Per Candidate

For each candidate in `scanner_results_box/{date}.json`:

1. Read the candidate's box definition: `range_high_5d`, `range_low_5d`, `price`, `vwap`
2. Pull 1m bars for that symbol on that date from IBKR
3. Feed bars into box_strategy: check entry criteria on each bar, manage exits
4. Record all trades (entries, exits, P&L, exit reason)
5. Record "no trade" results too (candidate was scanned but no entry triggered)

```python
for date_file in sorted(scanner_results_dir.glob("*.json")):
    date_str = date_file.stem  # e.g., "2026-01-02"
    with open(date_file) as f:
        scan_data = json.load(f)

    for candidate in scan_data["candidates"]:
        symbol = candidate["symbol"]
        # Pull 1m bars from IBKR for this symbol on this date
        bars = pull_1m_bars(ib, symbol, date_str)
        # Run strategy
        trades = run_box_strategy(candidate, bars)
        # Record results
        results.append({
            "date": date_str,
            "symbol": symbol,
            "box_score": candidate["box_score"],
            "range_high_5d": candidate["range_high_5d"],
            "range_low_5d": candidate["range_low_5d"],
            "range_pct": candidate["range_pct"],
            "range_position_pct": candidate["range_position_pct"],
            "high_tests": candidate["high_tests"],
            "low_tests": candidate["low_tests"],
            "adr_util_today": candidate["adr_util_today"],
            "vwap_dist_pct": candidate["vwap_dist_pct"],
            "sma_slope_pct": candidate["sma_slope_pct"],
            "avg_daily_vol_5d": candidate["avg_daily_vol_5d"],
            # Trade results
            "num_trades": len(trades),
            "total_pnl": sum(t.pnl for t in trades),
            "best_trade_pnl": max((t.pnl for t in trades), default=0),
            "worst_trade_pnl": min((t.pnl for t in trades), default=0),
            "exit_reasons": [t.exit_reason for t in trades],
            "win_rate": sum(1 for t in trades if t.pnl > 0) / max(len(trades), 1),
            "avg_hold_minutes": mean(t.hold_minutes for t in trades) if trades else 0,
        })
```

### Rate Limiting for IBKR

IBKR has strict rate limits on `reqHistoricalData`. 664 candidates × 1m bars = a LOT of requests.

```python
# IBKR allows ~60 historical data requests per 10 minutes
# Strategy: batch by date, cache aggressively

# 1. Group candidates by date
by_date = defaultdict(list)
for c in all_candidates:
    by_date[c["date"]].append(c)

# 2. For each date, pull bars for all symbols on that date
#    Cache to disk: box_backtest_cache/{date}/{symbol}.json
#    If cache exists, skip the IBKR request

# 3. Sleep 2 seconds between IBKR requests to stay under limits
import time
time.sleep(2)  # between each reqHistoricalData call
```

**Cache directory:** `box_backtest_cache/` — one JSON per symbol-date with the 1m bars. This lets us re-run the strategy with different parameters without re-pulling from IBKR.

### Handling Missing/Short Data

Some symbols on some dates may have:
- No 1m bar data available from IBKR (delisted, too illiquid, exchange issue)
- Very few bars (stock halted most of the day)
- IBKR connection timeouts

```python
# If IBKR returns < 60 bars (less than 1 hour of data), skip this candidate
if len(box_bars) < 60:
    results.append({
        ...candidate fields...,
        "num_trades": 0,
        "total_pnl": 0,
        "skip_reason": "insufficient_bars",
    })
    continue
```

Log skips but don't fail — we want results for as many candidates as possible.

---

## Output Format

### Per-Candidate Results: `box_backtest_results/per_candidate.csv`

One row per candidate (664 rows). Include ALL scanner fields plus trade results:

```csv
date,symbol,box_score,range_high_5d,range_low_5d,range_pct,range_position_pct,high_tests,low_tests,adr_util_today,vwap_dist_pct,sma_slope_pct,avg_daily_vol_5d,price,num_trades,total_pnl,best_trade_pnl,worst_trade_pnl,win_rate,avg_hold_minutes,exit_reasons,skip_reason
```

### Per-Trade Detail: `box_backtest_results/all_trades.csv`

One row per trade (could be 0, 1, or 2 per candidate):

```csv
date,symbol,entry_time,entry_price,exit_time,exit_price,shares,pnl,pnl_pct,exit_reason,hold_minutes,box_top,box_bottom,box_range,rsi_at_entry,bar_volume_at_entry
```

### Summary Report: `box_backtest_results/YTD_BOX_STRATEGY_REPORT.md`

Generate a markdown report with:

**1. Overall Stats**
- Total candidates tested, total with trades, total skipped
- Total trades, wins, losses, win rate
- Total P&L, average P&L per trade, average P&L per candidate
- Best trade, worst trade, max drawdown

**2. Exit Reason Breakdown**
- Count and P&L by exit reason (target_sell_zone, trailing_stop, hard_stop, time_stop, box_invalidation, session_loss_cap)
- This tells us WHERE the strategy's edge comes from (or doesn't)

**3. Performance by Scanner Score**
- Group candidates by box_score buckets (5-6, 6-7, 7-8, 8+)
- P&L, win rate, avg P&L for each bucket
- **KEY QUESTION:** Do higher-scored candidates perform better?

**4. Performance by Range Characteristics**
- By range_pct buckets (2-4%, 4-6%, 6-8%, 8-10%, 10%+)
- By range_position_pct at scan time (0-15%, 15-25%, 25-35%)
- By high_tests + low_tests (4 total, 5, 6, 7+)
- **KEY QUESTION:** What range characteristics predict success?

**5. Performance by Stock Characteristics**
- By price bucket ($5-15, $15-30, $30-50, $50-100)
- By avg_daily_vol_5d bucket
- By adr_util_today bucket
- By sma_slope_pct bucket
- **KEY QUESTION:** What kind of stock works best for box trading?

**6. Performance by Symbol**
- P&L by symbol (some symbols appear 20-30 times)
- **KEY QUESTION:** Are there consistently profitable box stocks?

**7. Performance by Day of Week / Month**
- P&L by day of week, by month
- **KEY QUESTION:** Are there seasonal or day-of-week patterns?

**8. Correlation Analysis**
- Which scanner fields correlate most with positive P&L?
- Rank-order correlation (Spearman) between each numeric scanner field and total_pnl
- This is the most important analysis — it tells us which filters to tighten

**9. "If We Only Traded These" Analysis**
- Show what happens if we apply stricter filters based on findings:
  - Only box_score >= 7
  - Only range_pct >= 4%
  - Only high_tests + low_tests >= 5
  - Only stocks that appeared 10+ times in YTD
  - Combinations of the above
- For each filter: trade count, total P&L, win rate, avg P&L

---

## Env Vars for box_strategy.py

```bash
# === Box Strategy Master Gate ===
WB_BOX_STRATEGY_ENABLED=0           # OFF by default (scanner still runs independently)

# === Entry ===
WB_BOX_BUY_ZONE_PCT=25              # Bottom 25% of box = buy zone
WB_BOX_SELL_ZONE_PCT=25             # Top 25% of box = sell zone (target)
WB_BOX_RSI_OVERSOLD=35              # RSI(14) must be below this to enter
WB_BOX_RSI_PERIOD=14                # RSI lookback period (1m bars)
WB_BOX_REVERSAL_CONFIRM=1           # Require green bar after red bar at support
WB_BOX_MIN_BAR_VOL_RATIO=1.0        # Current bar vol must be >= this × 20-bar avg

# === Exit ===
WB_BOX_STOP_PAD_PCT=0.5             # Hard stop pad below box_bottom (% of price)
WB_BOX_TRAIL_PCT=30                 # Trail distance as % of box_range
WB_BOX_TRAIL_ACTIVATION_PCT=50      # Trail activates after price moves this % of box_range from entry
WB_BOX_BREAKOUT_INVALIDATE_PCT=0.5  # Box invalid if breached by this % of box_range
WB_BOX_VWAP_EXIT_ENABLED=0          # OFF for initial backtest — test full range first
WB_BOX_MAX_RISK_PER_TRADE=200       # Max dollar risk per individual trade

# === Session ===
WB_BOX_START_ET=10:00               # Box window opens
WB_BOX_LAST_ENTRY_ET=14:30          # No new entries after this
WB_BOX_HARD_CLOSE_ET=15:45          # Force close all box positions
WB_BOX_MAX_NOTIONAL=50000           # Max position size
WB_BOX_MAX_LOSS_SESSION=500         # Max cumulative box losses per day
WB_BOX_MAX_ENTRIES_PER_STOCK=2      # Max re-entries per stock per day
```

---

## Build Steps

1. **`git pull`** — sync with latest
2. **Build `box_strategy.py`** — entry/exit logic as specified above, with the RSI computation, state machine, and all exit rules
3. **Build `box_backtest.py`** — reads scanner_results_box/*.json, pulls 1m bars from IBKR, runs strategy on each candidate, caches bars to disk, outputs CSV + report
4. **Run the backtest** across all 664 candidates. This will take a while due to IBKR rate limits — expect 20-40 minutes for the full YTD. Use the bar cache so re-runs are fast.
5. **Generate the report** — per_candidate.csv, all_trades.csv, and YTD_BOX_STRATEGY_REPORT.md with all the analysis sections above
6. **Push everything** — `box_strategy.py`, `box_backtest.py`, results directory, report
7. **STOP** — push results and stop. We (Cowork + Manny) will review the patterns before deciding next steps. Do NOT proceed to Phase 3/4 integration.

---

## What NOT to Do

- Do NOT use single-day HOD/LOD as the box — use the 5-day `range_high_5d`/`range_low_5d` from scanner results
- Do NOT use Alpaca for any data — IBKR for ALL historical data
- Do NOT implement partial exits — full exits only for the initial backtest (simplicity)
- Do NOT wire anything into bot_v3_hybrid.py — this is standalone
- Do NOT skip the per-candidate CSV output — that's the whole point (pattern analysis)
- Do NOT fail silently on missing data — log skips to the report with skip_reason
- Do NOT ignore IBKR rate limits — cache bars to disk, sleep between requests
- Do NOT re-pull bars if cache exists — `box_backtest_cache/{date}/{symbol}.json`
- Do NOT proceed past step 7 — STOP after pushing results

---

## Key Questions We're Trying to Answer

After the backtest, we'll look at the data and answer:

1. **Does the box strategy have a positive edge at all?** (Total P&L > 0, win rate > 40%)
2. **Which scanner score range produces the best results?** (Tighten score filter)
3. **Which range characteristics predict success?** (Tighten range filters)
4. **Are there "box stocks" that consistently work?** (Build a curated universe)
5. **What exit reason dominates?** (Tells us where to optimize next)
6. **Is the entry signal strong enough, or do we need more confirmation?** (RSI + reversal sufficient?)
7. **What's the optimal buy zone %?** (Is 25% too wide? Too narrow?)
8. **Should we use VWAP exit instead of sell zone?** (Run with both ON, compare)

The answers to these questions determine whether Phase 3 (box-only YTD backtest) is worth running, or whether we need to revise the strategy first.
