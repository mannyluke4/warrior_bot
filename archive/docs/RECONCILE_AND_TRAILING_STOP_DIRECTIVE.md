# Reconcile Bug Fix + Trailing Stop System Directive

## Priority Order
1. **CRITICAL**: Fix reconcile grace period (Bug 1) — blocker for live trading
2. **HIGH**: Trailing stop / profit lock system (Bug 2) — backtest on known runners
3. **MEDIUM**: Investigate bearish engulfing sensitivity on first bars after entry

---

## Bug 1: Reconcile Grace Period (CRITICAL)

### Problem
When the bot fills an order, Alpaca's paper trading API has a ~10-30 second propagation delay before the position appears. The reconcile check runs, sees `alp_qty=0` vs `bot_qty=7293`, and clears the internal position. This leaves the position:
- No stop monitoring
- No exit signal checks
- Completely unmanaged for the rest of the session

This happened on EDSA 2026-03-03. Price hit $2.774 vs a $2.92 stop — the stop never fired. Position was unprotected for 3+ hours.

### Fix

In the reconcile logic (likely `_reconcile_all_positions()` in `trade_manager.py` or `bot.py`):

```python
ENTRY_GRACE_SECONDS = 60  # Trust fill event for first 60 seconds

# When reconcile finds alp_qty == 0 and bot_qty > 0:
if bot_qty > 0 and alp_qty == 0:
    seconds_since_entry = (now - trade.entry_time).total_seconds()
    if seconds_since_entry < ENTRY_GRACE_SECONDS:
        logger.warning(
            f"RECONCILE GRACE: {symbol} has {bot_qty} bot shares but "
            f"Alpaca shows 0 — within {ENTRY_GRACE_SECONDS}s grace period "
            f"({seconds_since_entry:.0f}s since entry). Keeping position."
        )
        continue  # Skip this reconcile — trust the fill event
    else:
        # Normal reconcile behavior — position is stale
        logger.error(f"RECONCILE MISMATCH: {symbol} bot={bot_qty} alp={alp_qty} after grace period")
        # ... existing clear logic ...
```

### Verification
1. Read `trade_manager.py` and/or `bot.py` to find the exact reconcile logic
2. Understand what happens when `alp_qty != bot_qty` — does it clear, or just log?
3. Implement the grace period
4. Test by running EDSA 2026-03-03 in simulate.py to confirm the entry still works
5. **Regression**: Run all 6 Profile A regression stocks to confirm reconcile change doesn't break anything

### Important: Also check for the reverse case
If `alp_qty > 0` and `bot_qty == 0` (bot lost track but Alpaca has shares), the bot should:
- Log a critical warning
- Pick up the position and start managing it
- NOT silently ignore it

---

## Bug 2: Trailing Stop / Profit Lock System

### Overview
Currently the bot has a fixed stop (set at entry) and signal-based exits. There is no mechanism to raise the stop as a position gains. This means:
- A position can go from +$7,418 to +$3,959 with no protective action
- The only exits are the initial stop (never raised) or a signal exit (bearish engulfing)

### Proposed System

**Environment variables** (OFF by default, opt-in per profile):
```
WB_TRAILING_STOP_ENABLED=0          # Master switch
WB_TRAILING_STOP_BE_THRESHOLD_R=2   # Move stop to breakeven at 2R
WB_TRAILING_STOP_LOCK_THRESHOLD_R=4 # Move stop to +1R at 4R
WB_TRAILING_STOP_TRAIL_THRESHOLD_R=6 # Start trailing at 6R
WB_TRAILING_STOP_TRAIL_OFFSET=0.15  # Trail $0.15 below highest close
```

**Logic (checked on every 10-second bar close when position is open):**

```python
def check_trailing_stop(trade, current_price):
    """Adjust stop based on unrealized gain in R-multiples."""
    if not env_bool("WB_TRAILING_STOP_ENABLED"):
        return
    
    entry = trade.entry_price
    initial_stop = trade.stop_price
    R = entry - initial_stop  # Risk per share (for long positions)
    
    if R <= 0:
        return  # Safety check
    
    current_R = (current_price - entry) / R  # Current gain in R-multiples
    
    # Track highest R seen (for trailing)
    if not hasattr(trade, 'highest_r'):
        trade.highest_r = 0
        trade.highest_close = entry
    
    trade.highest_r = max(trade.highest_r, current_R)
    trade.highest_close = max(trade.highest_close, current_price)
    
    new_stop = trade.stop_price  # Start with current stop
    
    # Tier 1: Breakeven at 2R
    be_threshold = float(os.environ.get("WB_TRAILING_STOP_BE_THRESHOLD_R", "2"))
    if trade.highest_r >= be_threshold:
        new_stop = max(new_stop, entry)  # At least breakeven
    
    # Tier 2: Lock +1R at 4R
    lock_threshold = float(os.environ.get("WB_TRAILING_STOP_LOCK_THRESHOLD_R", "4"))
    if trade.highest_r >= lock_threshold:
        new_stop = max(new_stop, entry + R)  # At least +1R
    
    # Tier 3: Trail at 6R+
    trail_threshold = float(os.environ.get("WB_TRAILING_STOP_TRAIL_THRESHOLD_R", "6"))
    trail_offset = float(os.environ.get("WB_TRAILING_STOP_TRAIL_OFFSET", "0.15"))
    if trade.highest_r >= trail_threshold:
        trail_stop = trade.highest_close - trail_offset
        new_stop = max(new_stop, trail_stop)
    
    # Only raise stops, never lower
    if new_stop > trade.stop_price:
        logger.info(
            f"TRAILING STOP: {trade.symbol} raising stop "
            f"${trade.stop_price:.2f} → ${new_stop:.2f} "
            f"(current {current_R:.1f}R, peak {trade.highest_r:.1f}R)"
        )
        trade.stop_price = new_stop
```

### CRITICAL: Signal Mode Cascading Exits Must Still Work

The trailing stop is ADDITIVE to the existing signal exit system. It does NOT replace signal exits:
- Signal mode bearish engulfing → still fires exits as normal
- Trailing stop → raises the stop price floor
- Whichever triggers first wins
- **Never suppress signal exits** — this is the bot's core edge

### Backtest Plan

Run the 6 Profile A regression runners with trailing stop enabled to verify it helps:

| Stock | Date | Current P&L | With Trailing Stop |
|-------|------|-------------|-------------------|
| VERO | 2026-01-16 | +$6,890 | ? |
| GWAV | 2026-01-16 | +$6,735 | ? |
| APVO | 2026-01-09 | +$7,622 | ? |
| BNAI | 2026-01-28 | +$5,610 | ? |
| MOVE | 2026-01-27 | +$5,502 | ? |
| ANPA | 2026-01-09 | +$2,088 | ? |

**Success criteria**: Trailing stop should not reduce P&L by more than $500 on any of these. If it cuts a winner by >$1K, the thresholds need tuning.

**Also test on EDSA 2026-03-03** to see what the trailing stop would have produced vs the +$4,533 actual.

### Profile Integration

Once validated, trailing stop can be added to profile configs:
```json
// profiles/A.json
{
  "WB_TRAILING_STOP_ENABLED": "1",
  "WB_TRAILING_STOP_BE_THRESHOLD_R": "2",
  "WB_TRAILING_STOP_LOCK_THRESHOLD_R": "4",
  "WB_TRAILING_STOP_TRAIL_THRESHOLD_R": "6",
  "WB_TRAILING_STOP_TRAIL_OFFSET": "0.15"
}
```

Different profiles may want different trailing stop settings:
- Profile A (micro-float runners): Aggressive trailing — these move fast, protect gains
- Profile B (mid-float L2): May want wider trail offset — less volatile
- Profile X (conservative): Tightest trailing — minimize exposure on unknowns

---

## Bug 3: Bearish Engulfing Sensitivity on First Bars (MEDIUM)

### Problem
EDSA Trade 1: entered at $3.00, bearish engulfing fired at $2.97 just 1 minute later, sold for -$267. Price recovered to $3.19 on the very next bar.

The 10-second bar bearish engulfing exit may be too sensitive immediately after entry, when the position hasn't had time to develop.

### Possible Fix
Add a minimum hold period before signal exits can fire:
```
WB_MIN_HOLD_BARS=3  # Don't allow signal exits for first 3 bars (30 seconds)
```

### Caution
This conflicts with the core principle of signal mode cascading exits. A bad entry should be exited quickly. The question is whether 1 minute is "quickly" or "too quickly."

### Recommendation
**Defer this until after reconcile fix and trailing stop are done.** Analyze the 137-stock dataset to see how often the first-bar bearish engulfing exit is wrong (exits before a recovery) vs right (exits before further decline). If it's wrong >50% of the time, add a small hold period. If it's right most of the time, EDSA was just an outlier.

---

## Implementation Order

1. **Read the reconcile code** — understand exactly what happens today
2. **Implement grace period** — 60 seconds after fill, trust the fill
3. **Run Profile A regressions** — confirm nothing breaks
4. **Implement trailing stop** — env-gated, OFF by default
5. **Backtest trailing stop** on 6 Profile A stocks + EDSA
6. **If validated**: enable in Profile A config, commit
7. **Defer**: bearish engulfing sensitivity analysis

## Regression Benchmarks (MUST STILL PASS)

| Stock | Date | Profile | Expected P&L |
|-------|------|---------|-------------|
| VERO | 2026-01-16 | A | +$6,890 |
| GWAV | 2026-01-16 | A | +$6,735 |
| APVO | 2026-01-09 | A | +$7,622 |
| BNAI | 2026-01-28 | A | +$5,610 |
| MOVE | 2026-01-27 | A | +$5,502 |
| ANPA | 2026-01-09 | A | +$2,088 |
| ANPA | 2026-01-09 | B --ticks | +$5,091 |
| BATL | 2026-02-27 | B --ticks | +$4,522 |

---

*Directive created by Perplexity Computer — March 3, 2026, 11:52 AM MST*
*Priority: Reconcile fix is a BLOCKER for live real-money trading*
