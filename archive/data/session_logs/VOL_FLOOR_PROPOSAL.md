# Proposal: Volatility-Adjusted Position Sizing ("Vol Floor")

## Status: IMPLEMENTED (code ready), NEEDS TUNING (parameter optimization)

---

## The Problem

**Discovered 2026-02-27 live session on ANNA:**

The bot entered ANNA at $4.06 with R=$0.09 (stop at $3.97). On a $4 stock with a 39.5% gap, $0.09 is only 2.2% of room — a single normal price wick blows through it. The bot sized 11,111 shares and got stopped out twice (-$1,029 and -$1,300 live). The stock then spiked to $5.04.

The R was structurally correct (pullback low), but too tight for the stock's actual volatility. With wider stops and proportionally smaller position, the bot stays in through normal volatility and catches the move.

---

## The Solution

**New feature: `_vol_floor_stop()`** — widens stops when R is too small relative to volatility.

Two mechanisms (takes the wider):
1. **ATR-based floor**: `min_stop_distance = vol_floor_atr_mult * avg_bar_range` (uses existing `_bar_ranges_1m` deque)
2. **Price-based floor**: `min_stop_distance = vol_floor_pct% * entry_price`

When activated:
- Stop moves DOWN (farther from entry)
- R increases
- Position size decreases (same $1K risk / larger R = fewer shares)
- Trade survives normal volatility
- `[VOL_FLOOR]` tag appears in ARM messages

When vol floor is active, halt override is skipped (they have opposite goals).

---

## Implementation (Complete)

### Files Changed
- **`micro_pullback.py`**: New `_vol_floor_stop()` method, new env vars, applied in all 3 ARM paths
- **`.env.example`**: Added `WB_VOL_FLOOR_ENABLED`, `WB_VOL_FLOOR_ATR_MULT`, `WB_VOL_FLOOR_PCT`

### Files NOT Changed
- `simulate.py` — wider R flows through automatically
- `trade_manager.py` — `size_qty()` already handles any R value
- `bars.py`, `bot.py` — no changes needed

### New Env Vars
```env
WB_VOL_FLOOR_ENABLED=0          # 0=off, 1=on
WB_VOL_FLOOR_ATR_MULT=1.5       # Min stop = mult * avg_bar_range (last 14 bars)
WB_VOL_FLOOR_PCT=0              # Min stop as % of entry price (e.g., 5 = 5%)
```

---

## Test Results

### ANNA 2026-02-27 (The Motivating Case)

| Metric | No Vol Floor | Vol Floor (5%) | Change |
|--------|-------------|----------------|--------|
| Trade 1 R | $0.11 | $0.22 | 2x wider |
| Trade 1 qty | 9,090 | 4,484 | 2x smaller |
| Trade 1 exit | stop_hit | bearish_engulfing | Controlled exit |
| Trade 1 P&L | -$1,088 | -$537 | **+$551 saved** |
| Trade 2 | $0 (trail) | $0 (trail) | Same |
| **Total** | **-$1,088** | **-$537** | **+$551** |

With the wider stop, trade 1 survived the initial dip. Instead of hitting the hard stop at $3.97, the bearish engulfing signal exited at $3.96 — a softer, controlled exit. Loss cut nearly in half.

### MRM 2026-02-27 (Today's Other Loser)

| Metric | No Vol Floor | Vol Floor (5%) |
|--------|-------------|----------------|
| Trade 1 | -$1,088 (stop) | -$333 (BE exit) |
| Trade 2 | $0 | -$757 (BE exit) |
| **Total** | **-$1,088** | **-$1,090** |

Similar total, but different mechanics — smaller positions with bearish engulfing exits instead of hard stops.

### 10-Stock Regression Suite (WB_VOL_FLOOR_PCT=5)

| Stock | Baseline | Vol Floor (5%) | Diff | Category |
|-------|----------|----------------|------|----------|
| ROLR | +$1,413 | +$2,929 | **+$1,516** | Shakeout survivor |
| PAVM | -$2,800 | +$1,824 | **+$4,624** | Shakeout survivor |
| ACON | -$2,122 | -$1,129 | **+$993** | Loss reduction |
| FLYX | -$703 | +$255 | **+$958** | Turned winner |
| LCFY | -$627 | -$604 | **+$23** | Neutral |
| TNMG | -$481 | -$481 | **$0** | Unchanged |
| MLEC | +$173 | -$459 | **-$632** | Reduced profit |
| ANPA | +$4,368 | +$1,384 | **-$2,984** | Reduced profit |
| VERO | +$6,890 | +$4,722 | **-$2,168** | Reduced profit |
| GWAV | +$6,735 | +$2,701 | **-$4,034** | Reduced profit |
| **TOTAL** | **+$12,846** | **+$11,142** | **-$1,704** | **Net regression** |

### The Tradeoff

**Winners (stocks that shakeout then recover):**
- PAVM: +$4,624 improvement (biggest single improvement)
- ROLR: +$1,516
- ACON, FLYX: ~+$1K each

**Losers (stocks where tight R + re-entry is the edge):**
- GWAV: -$4,034 (fewer shares on spike capture)
- ANPA: -$2,984 (fewer shares)
- VERO: -$2,168 (fewer shares)

**Root cause of regression:** The 5% price floor is too blunt. It reduces position size on ALL stocks, including ones where the original tight R was correct and the bot profits from spike-capture with full position.

---

## The Tuning Problem (FOR WEB CLAUDE REVIEW)

The vol floor correctly identifies the ANNA/PAVM pattern (tight R → shakeout → missed move). But it over-applies to VERO/GWAV/ANPA where tight R + signal re-entry is the winning strategy.

### Potential Solutions to Evaluate

#### Option A: Lower percentage (3% instead of 5%)
Less aggressive widening. May reduce regression on winners while still helping shakeout cases. Need to test.

#### Option B: Only activate when R < threshold % of entry
Example: Only widen when R/entry < 2%. This means a $5 stock with R=$0.10 (2%) gets widened, but R=$0.15 (3%) doesn't. Protects against the most extreme cases without blanket application.

#### Option C: Gap-based activation
Only activate vol floor when gap > 20% (highly volatile stocks). Normal-gap stocks keep original sizing. Theory: high-gap stocks are more prone to violent shakeouts.

#### Option D: ATR-only (no price floor)
Remove the price-percentage floor entirely. Only use avg_bar_range. This means the floor only activates when the stock's recent bars are actually volatile. Problem: ANNA's pre-breakout bars were tiny, so ATR alone didn't help.

#### Option E: Hybrid — ATR during active movement, price floor on first entry only
Use price floor only for the first ARM (before we have volatility data), then switch to ATR floor for re-entries when we have real bar range data.

#### Option F: Score-based activation
Only apply vol floor when conviction is high (score > 10). If the bot is highly confident, give the trade room to breathe. Low-confidence trades keep tight stops for capital protection.

#### Option G: Selective by stock characteristics
Combine multiple signals: gap% > 20% AND R/entry < 3% AND score > 8 → activate vol floor. This creates a "high conviction on a volatile stock with tight R" trigger.

---

## Key Questions for Review

1. **Is the tradeoff acceptable?** PAVM alone gained +$4,624, but GWAV lost -$4,034. The vol floor turns some losers into winners but shrinks winners. Is this the right direction?

2. **Which activation criteria?** The 5% blanket is too broad. What combination of conditions should gate the vol floor?

3. **Should this be separate from halt override?** Currently they're mutually exclusive (vol floor active = skip halt override). Should they coexist with different priorities?

4. **What about the exit side?** Wider stops help entries, but the bearish engulfing exits are the same. Should wider-stop trades also have wider exit thresholds?

5. **Target stocks**: ANNA, PAVM, ACON, FLYX, ROLR all benefit. These are volatile small-caps prone to shakeouts. Is there a profile we can define?

---

## Current Code State

- Feature is implemented and env-gated (`WB_VOL_FLOOR_ENABLED=0` = OFF by default)
- Safe to commit — zero impact when disabled
- Ready for parameter sweep testing once activation criteria are decided

---

## Also Found This Session

### Critical Bug Fix: IEX → SIP WebSocket Feed (ALREADY COMMITTED)

The live bot's WebSocket was defaulting to IEX (single exchange, ~0.2% of volume) instead of SIP (full consolidated tape). This means:
- Every live trade the bot ever took was based on partial data
- Backtests used SIP data — live and backtest were never seeing the same data
- BATL missed +$4,450 because IEX bars had wrong prices/PM_HIGH/R calculations
- **Fix: one line in `data_feed.py`** — `feed=AlpacaDataFeed.SIP`
- Already committed and pushed: `ce5d427`

### Live Trades 2026-02-27
- MRM: -$1,029 (stop hit, clean execution, IEX data)
- ANNA: -$1,029 + -$1,300 = -$2,329 (both stop hit on shakeout, IEX data)
- BATL: $0 (missed — R too small due to IEX data)
