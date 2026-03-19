# .env Changes for Mac Mini — Strategy Improvements V1

**TARGET**: 🖥️ Mac Mini CC
**Date**: 2026-03-18
**After**: `git pull` to get commit with these code changes

## New Env Vars to Add

All new features are **OFF by default** — enable them after testing confirms improvements.

```env
# --- Fix 1: Direction-aware continuation hold ---
WB_CONT_HOLD_DIRECTION_CHECK=0  # 1=don't suppress exits when underwater + 3/5 red bars

# --- Fix 2: Float-tiered max loss cap ---
WB_MAX_LOSS_R_TIERED=0          # 1=use float-aware tiers instead of flat 0.75R
WB_MAX_LOSS_R_ULTRA_LOW_FLOAT=0 # Cap for <1M float (0=OFF, hard stop only)
WB_MAX_LOSS_R_LOW_FLOAT=0.85    # Cap for 1-5M float
WB_MAX_LOSS_R_FLOAT_THRESHOLD_LOW=1.0   # Ultra-low/low boundary (millions)
WB_MAX_LOSS_R_FLOAT_THRESHOLD_HIGH=5.0  # Low/mid boundary (millions)

# --- Fix 3: max_loss_hit cooldown bug fix ---
WB_MAX_LOSS_TRIGGERS_COOLDOWN=0  # 1=max_loss_hit triggers same cooldown as stop_hit

# --- Fix 4: No re-entry after loss (already existed, now enabled) ---
WB_NO_REENTRY_ENABLED=1         # Block re-entry on same symbol after a loss

# --- Fix 5: TW profit gate (suppress TW on confirmed runners) ---
WB_TW_MIN_PROFIT_R=1.5          # Suppress TW exit when unrealized profit >= 1.5R (let BE handle runners)
```

## Changed Env Vars

None — all existing vars keep their current values.

## Recommended Live Values (after backtesting confirms)

```env
WB_CONT_HOLD_DIRECTION_CHECK=1
WB_MAX_LOSS_R_TIERED=1
WB_MAX_LOSS_R_ULTRA_LOW_FLOAT=0
WB_MAX_LOSS_R_LOW_FLOAT=0.85
WB_MAX_LOSS_TRIGGERS_COOLDOWN=1
WB_NO_REENTRY_ENABLED=1
WB_TW_MIN_PROFIT_R=1.5
```

## Testing Required Before Enabling

1. **49-day backtest** with all fixes ON → compare to +$7,580 baseline
2. **Weekly backtest** (Mar 9-18) with all fixes ON → compare to -$1,411
3. **VERO standalone regression** → NEW target **+$18,583** ✅ (verified on MacBook Pro — TW suppressed at 9.2R, BE exits at 18.6R)
4. **ROLR verification** → must survive 0.85R cap (min unrealized was -0.60R), expect ~+$6,444 with TW suppressed
5. Each fix in isolation + all combined
