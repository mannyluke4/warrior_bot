# Architecture: Box / Range Trading Strategy

## Last Updated: 2026-04-02

---

## What This Is

A mean-reversion intraday strategy that activates AFTER the momentum window closes. When the squeeze system is done (10:00 AM ET), the bot switches to "box mode" — scanning for a completely different stock universe, identifying range-bound candidates, and trading bounces within the day's established range.

This is a **fully separate pipeline**: new scanner, new strategy file, new execution logic. It shares the bot's IBKR connection and Alpaca execution, but nothing else.

---

## Time Windows

```
PRE-MARKET   │  MOMENTUM WINDOW  │  BOX WINDOW             │ CLOSE
4:00 AM      │  7:00 - 10:00 AM  │  10:00 AM - 3:45 PM    │ 4:00 PM
             │  (squeeze + EPL)  │  (box/range)             │
             │                    │                          │
Scanner:     │  ibkr_scanner.py   │  box_scanner.py          │
Strategy:    │  squeeze_detector  │  box_strategy.py         │
             │  epl_mp_reentry    │                          │
```

### Handoff Rules

1. **Momentum → Box (10:00 AM ET)**:
   - If momentum has an open position, let it finish (exit naturally via SQ/EPL rules)
   - Box scanner activates at 10:00 AM regardless — it just can't enter while position is occupied
   - Once momentum position closes, box mode takes the position slot
   - If momentum has no position at 10:00, box takes over immediately

2. **Box → Momentum (next morning, 7:00 AM ET)**:
   - If box has an open position overnight: **NO** — box exits all positions by 3:45 PM ET (15-min buffer before close)
   - Box never holds overnight. Clean slate for momentum every morning.

3. **Priority**: Momentum always has priority. If for any reason a momentum signal fires during box window (shouldn't happen with 10 AM cutoff, but safety), momentum wins.

---

## Stock Universe (Box Scanner)

The box scanner finds the **opposite** of what the momentum scanner finds. Momentum wants explosive micro-caps breaking out. Box wants established stocks oscillating in a defined range.

### Universe Parameters

| Parameter | Momentum Scanner | Box Scanner | Rationale |
|-----------|-----------------|-------------|-----------|
| Price | $2 - $20 | $5 - $100 | Higher-priced stocks range more predictably |
| Float | < 15M shares | No max (prefer > 20M) | Higher float = more institutional, less squeeze risk |
| Market cap | Micro/small cap | Small to mid cap | Larger companies = more predictable ranges |
| Gap % | 10% - 500% | Not a filter | Box doesn't care about gap — it cares about range behavior |
| Volume | High relative vol | Minimum absolute vol | Need liquidity, not spikes |
| Behavior | Breaking levels | Respecting levels | The fundamental difference |

### Box Scanner Criteria

The scanner runs at **10:00 AM ET** (or configurable) using IBKR data. It evaluates the morning session to find stocks that have established a range and are now oscillating within it.

#### Required Filters

1. **Minimum Intraday Range (HOD - LOD)**
   - `intraday_range_pct = (hod - lod) / lod * 100`
   - Minimum: 2% (need enough range to profit from bounces)
   - Maximum: 15% (too wide = still trending, unpredictable)
   - This ensures the "box" is big enough to trade but not so big it's chaotic

2. **ADR Utilization > 60%**
   - `adr_util = (hod - lod) / adr_20d`
   - The stock has already consumed 60%+ of its typical daily range by 10 AM
   - Statistical edge: when 60%+ of ADR is used by mid-morning, the remaining move tends to stay within the range (~80% of the time)
   - Compute ADR from 20-day daily bars via IBKR `reqHistoricalData`

3. **NOT Making New HOD/LOD Recently**
   - HOD and LOD must have been set at least N minutes ago (e.g., 15+ minutes)
   - If the stock is still actively making new highs or lows at 10 AM, it's trending, not ranging
   - Check: last new HOD time and last new LOD time both > 15 min ago

4. **Minimum Volume**
   - Session volume by 10 AM > some threshold (e.g., 200K shares, or configurable)
   - Need liquidity for clean entries/exits
   - Also: recent bar volume should be reasonable (not dead — volume too low means the stock stopped moving entirely)

5. **VWAP Proximity**
   - `abs(price - vwap) / vwap * 100 < threshold` (e.g., within 3% of VWAP)
   - Stocks near VWAP are in equilibrium — the gravitational center of the day's range
   - Stocks far from VWAP in one direction are trending, not ranging

6. **Declining Volume Profile**
   - Volume in the last 30 min should be lower than volume in the first 30 min of the session
   - `recent_vol / early_vol < 0.6` (recent volume is less than 60% of early volume)
   - Declining volume = momentum players have moved on = range-bound behavior

7. **Price Stability (Low Recent Volatility)**
   - Standard deviation of 1m closes over the last 15-30 bars should be low relative to the range
   - `stdev(closes[-30:]) / range < threshold`
   - Low volatility relative to range = stock is oscillating predictably, not making jagged moves

#### Optional / Enhancement Filters

8. **Multi-Test of Support/Resistance**
   - Stock has tested HOD or LOD zone 2+ times and bounced
   - This confirms the box is real (levels hold) rather than a coincidence
   - Hard to scan for at scan time — may be better as a strategy-level confirmation

9. **Sector/Industry Context**
   - Exclude stocks with pending earnings, FDA announcements, or other catalysts
   - Hard to automate — may be a future enhancement

10. **Spread Check**
    - Bid-ask spread < some % of price
    - Illiquid stocks with wide spreads eat into box profits

### Scanner Output

```python
{
    "symbol": "AAPL",
    "price": 178.50,
    "hod": 180.20,
    "lod": 176.80,
    "range_pct": 1.92,        # (hod - lod) / lod * 100
    "adr_20d": 3.80,          # 20-day average daily range in dollars
    "adr_pct": 2.13,          # ADR as % of price
    "adr_utilization": 0.89,  # (hod - lod) / adr_20d = 89%
    "vwap": 178.30,
    "vwap_dist_pct": 0.11,    # abs(price - vwap) / vwap * 100
    "session_volume": 4500000,
    "vol_decline_ratio": 0.45, # recent_vol / early_vol
    "last_new_hod_min_ago": 47,
    "last_new_lod_min_ago": 62,
    "box_score": 8.5,          # Composite ranking score
    "scan_time_et": "10:00",
}
```

### Ranking (box_score)

Higher score = better box candidate:

```
box_score = (
    + adr_utilization * 3.0          # Already used most of daily range (max ~3.0)
    + vwap_proximity * 2.0           # Near VWAP (max 2.0 when at VWAP)
    + vol_decline_factor * 1.5       # Volume fading (max 1.5)
    + range_quality * 2.0            # Range is well-defined (levels tested)
    + stability * 1.5                # Low recent volatility relative to range
)
```

### Re-scan Schedule

Unlike momentum (which scans pre-market and at checkpoints), the box scanner can:
- **Primary scan at 10:00 AM** — first box candidate selection
- **Re-scan at 11:00 AM** — re-evaluate, drop stocks that broke out of range, add new range-bound candidates
- **Optional: 12:00 PM** — one more check. After noon, the universe is usually stable.
- **No new entries after 2:30 PM** — not enough time for the trade to work before the 3:45 PM hard close

---

## Strategy: Box Trading (box_strategy.py)

### Core Concept

Draw a box around the morning's range. Buy near the bottom, sell near the top. Stop if the box breaks.

### Box Definition

```
BOX_TOP = HOD at scan time (resistance)
BOX_BOTTOM = LOD at scan time (support)
BOX_RANGE = BOX_TOP - BOX_BOTTOM
BOX_MID = (BOX_TOP + BOX_BOTTOM) / 2  (approximately VWAP)
```

### Entry Zones

The box is divided into zones:

```
┌─────────────────────────── BOX_TOP (HOD) ──── SELL ZONE (top 20%)
│
│           NEUTRAL ZONE (middle 60%)
│
└─────────────────────────── BOX_BOTTOM (LOD) ── BUY ZONE (bottom 20%)
```

- **Buy zone**: price is in the bottom 20-25% of the box
- **Sell zone**: price is in the top 20-25% of the box
- **Neutral zone**: no new entries (hold existing, or stay flat)

The percentages are configurable (env vars).

### Entry Signals

Buy when ALL of:
1. Price is in the buy zone (bottom 20-25% of box)
2. RSI(14) on 1m bars is oversold (< 30-35)
3. Price shows reversal confirmation:
   - Green bar (close > open) after red bar(s)
   - OR: hammer/doji candle pattern at support
   - OR: price bounced off BOX_BOTTOM and is moving up
4. Volume on the reversal bar is above recent average (confirmation, not exhaustion)
5. No open position
6. Time is before 2:30 PM ET (enough room for the trade to work)

### Exit Rules

1. **Target exit**: price reaches sell zone (top 20-25% of box)
   - Can be partial: take 75% at target, trail 25%

2. **VWAP target** (alternative): exit at VWAP if entry was below VWAP
   - More conservative, but higher win rate

3. **Hard stop**: price breaks below BOX_BOTTOM by a configurable pad (e.g., BOX_BOTTOM - 0.5% of price)
   - The thesis is blown — the box broke

4. **Trailing stop**: once profitable, trail at some distance
   - Trail from peak profit, not from entry
   - Distance = configurable fraction of box range (e.g., 30% of box range)

5. **Time stop**: 3:45 PM ET — close all box positions
   - Non-negotiable. Box never holds overnight.

6. **Box invalidation**: if price makes a new HOD or new LOD by more than a threshold, the box is broken
   - A new HOD by > 0.5% of box range = stock is trending up again, exit and don't re-enter
   - A new LOD by > 0.5% of box range = stock is breaking down, exit and don't re-enter

### Position Sizing

- Same notional cap as SQ: `WB_BOX_MAX_NOTIONAL` (default $50,000)
- Risk per trade: BOX_RANGE * 25% (from buy zone to stop is ~25% of range + pad)
- Size = risk_dollars / R, capped at max notional
- Separate session loss cap: `WB_BOX_MAX_LOSS_SESSION` (default $500 — conservative start)

### Re-Entry Rules

If a box trade exits at target (or via trail), the stock can be re-entered:
- Same box still valid (no new HOD/LOD breakouts)
- Price returns to buy zone
- All entry criteria met again
- Max re-entries per stock per day: configurable (default 2)

---

## File Architecture

| File | Purpose | Status |
|------|---------|--------|
| `box_scanner.py` | Box scanner — finds range-bound candidates at 10 AM | NEW |
| `box_strategy.py` | Box strategy — entry/exit logic, box management | NEW |
| `bot_v3_hybrid.py` | Orchestrator — switches between momentum and box modes | MODIFY (add mode switching) |

### box_scanner.py

- New file, completely separate from `ibkr_scanner.py`
- Uses the bot's existing IBKR connection (`state.ib`)
- Computes ADR from IBKR `reqHistoricalData` (20 daily bars)
- Reads intraday HOD/LOD/VWAP/volume from the bot's bar builders
- Returns ranked list of box candidates
- Also needs a `scan_historical()` mode for backtesting (same as ibkr_scanner has)

### box_strategy.py

- New file, completely separate from squeeze/MP/EPL
- Owns its own state machine, entry/exit logic, position tracking
- Interface similar to squeeze_detector but fundamentally different internals
- Receives 1m bars and ticks from the bot's bar builders
- Returns entry signals and exit signals

### Bot integration (bot_v3_hybrid.py)

- New `BOX_ENABLED` env var gate
- Time-based mode switching: `momentum_mode` vs `box_mode`
- At 10:00 AM: run box scanner, subscribe to box candidates, activate box strategy
- Box strategy gets its own `on_bar_close_1m_box()` and `check_triggers_box()` and `manage_exit_box()`
- Clean separation: momentum functions and box functions don't share detection state

---

## Env Vars (all gated, all OFF by default)

```bash
# === Box Strategy ===
WB_BOX_ENABLED=0                    # Master gate
WB_BOX_START_ET=10:00               # When box mode activates
WB_BOX_LAST_ENTRY_ET=14:30          # No new box entries after this time
WB_BOX_HARD_CLOSE_ET=15:45          # Close all box positions (15 min before market close)
WB_BOX_MAX_NOTIONAL=50000           # Position sizing cap
WB_BOX_MAX_LOSS_SESSION=500         # Session loss cap for box trades (conservative)
WB_BOX_MAX_ENTRIES_PER_STOCK=2      # Max re-entries per stock per day

# === Box Scanner ===
WB_BOX_MIN_PRICE=5.00
WB_BOX_MAX_PRICE=100.00
WB_BOX_MIN_RANGE_PCT=2.0            # Minimum intraday range %
WB_BOX_MAX_RANGE_PCT=15.0           # Maximum intraday range %
WB_BOX_MIN_ADR_UTIL=0.60            # Minimum ADR utilization (60%)
WB_BOX_MAX_VWAP_DIST_PCT=3.0        # Must be within 3% of VWAP
WB_BOX_MIN_SESSION_VOL=200000       # Minimum session volume by scan time
WB_BOX_MIN_HOD_AGE_MIN=15           # HOD must be at least 15 min old
WB_BOX_MIN_LOD_AGE_MIN=15           # LOD must be at least 15 min old
WB_BOX_VOL_DECLINE_MAX=0.60         # Recent vol must be < 60% of early vol
WB_BOX_RESCAN_TIMES=10:00,11:00     # Scan checkpoints

# === Box Entry/Exit ===
WB_BOX_BUY_ZONE_PCT=25              # Bottom 25% of box = buy zone
WB_BOX_SELL_ZONE_PCT=25             # Top 25% of box = sell zone
WB_BOX_RSI_OVERSOLD=35              # RSI threshold for buy signal
WB_BOX_RSI_OVERBOUGHT=65            # RSI threshold for sell signal (unused initially — long only)
WB_BOX_STOP_PAD_PCT=0.5             # Stop below LOD by this % of price
WB_BOX_TRAIL_PCT=30                 # Trail at 30% of box range from peak
WB_BOX_BREAKOUT_INVALIDATE_PCT=0.5  # Box invalid if HOD/LOD broken by > 0.5% of range
```

---

## Build Order

### Phase 1: Scanner Only (box_scanner.py)
- Build the scanner
- Run it on YTD dates to produce candidate lists
- Manual verification: pull up charts for selected stock-dates, confirm they're good box candidates
- Gate: only proceed to Phase 2 if scanner finds genuine range-bound stocks

### Phase 2: Strategy (box_strategy.py)
- Build the strategy logic
- Backtest a handful of manually-verified stock-dates
- Gate: only proceed if the strategy produces profitable trades on known-good candidates

### Phase 3: YTD Box-Only Backtest
- Run box strategy across all YTD dates using scanner output
- Evaluate: total P&L, win rate, avg winner vs avg loser, drawdown

### Phase 4: Combined Backtest (Squeeze + Box)
- Full YTD with both strategies: squeeze 7-10 AM, box 10 AM - close
- Compare: combined P&L vs squeeze-only baseline
- Confirm: box adds value, doesn't drag squeeze down, time windows don't conflict

### Phase 5: Ship to Live
- Wire into bot_v3_hybrid.py
- Time-based mode switching
- Paper trade for N days before going live

---

## Key Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Box breaks (trending resumes) | Hard stop below LOD + box invalidation exit |
| False range (coincidental HOD/LOD) | Multi-test confirmation, ADR utilization filter |
| Low profitability (range too tight) | Min range % filter, min R requirement |
| Competes with squeeze for position | Time-based separation, clean handoff |
| Slippage on entries (wide spreads) | Spread check in scanner, limit orders only |
| Dead stocks (no movement) | Min volume filter, declining vol ratio (not zero vol) |
| End-of-day risk | Hard 3:45 PM close, no overnight holds |

---

## What This Is NOT

- **Not a breakout strategy.** If the stock breaks out of the box, we EXIT, not enter.
- **Not momentum.** We're buying weakness (near LOD) and selling strength (near HOD).
- **Not the Darvas Box.** Darvas is a multi-day breakout strategy. Ours is intraday mean-reversion within a single-day range. Similar name, opposite philosophy.
- **Not short selling.** We're long only for now. Selling at the top of the box means exiting a long, not opening a short. Shorting can be added later as Phase 6 if the long-only strategy works.

---

*This document is the design blueprint. Each phase gets its own directive for CC.*
