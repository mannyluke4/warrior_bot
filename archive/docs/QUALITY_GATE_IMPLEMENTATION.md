# Setup Quality Gate — Implementation Summary

## Overview
Five-gate quality filter system added to `micro_pullback.py` that scores setups before arming. Gates 1-4 are controlled by `WB_QUALITY_GATE_ENABLED` (OFF by default). Gate 5 is independently controlled by `WB_NO_REENTRY_ENABLED` (OFF by default).

The gate runs after the confirmation candle and before existing ARM gates (stale filter, LevelMap, exhaustion).

## The 5 Gates

| Gate | Name | What it checks | Action on fail |
|------|------|---------------|----------------|
| 1 | Clean Pullback | Retrace depth ≤65%, pullback vol ≤70% of impulse, ≤4 candles | Block ARM |
| 2 | Impulse Strength | Impulse move ≥2% of price, volume ≥1.5x avg bar vol | Block ARM |
| 3 | Volume Dominance | Recent 5-bar vol vs session avg | Warn/log only (never blocks) |
| 4 | Price/Float Sweet Spot | Price $3-$15 sweet spot (hard block <$2 or >$20) | Reduce size to 50% or block |
| 5 | No Re-entry | Max 1 loss per symbol, max 2 trades per symbol per session | Block ARM |

## Config Variables

```bash
# Master switch (Gates 1-4)
WB_QUALITY_GATE_ENABLED=0        # 0=off (default), 1=all gates active

# Gate 1: Clean Pullback
WB_MAX_PULLBACK_RETRACE_PCT=65   # Max % retrace of impulse range
WB_MAX_PB_VOL_RATIO=70           # Max pullback avg vol as % of impulse vol
WB_MAX_PB_CANDLES=4              # Max candles in pullback

# Gate 2: Impulse Strength
WB_MIN_IMPULSE_PCT=2.0           # Min impulse bar move as % of price
WB_MIN_IMPULSE_VOL_MULT=1.5      # Min impulse vol as multiple of avg bar vol

# Gate 3: Volume Dominance
# (no config — warn/log only)

# Gate 4: Price/Float Sweet Spot
WB_PRICE_SWEET_LOW=3.0           # Lower bound of sweet spot
WB_PRICE_SWEET_HIGH=15.0         # Upper bound of sweet spot

# Gate 5: No Re-entry (independent switch)
WB_NO_REENTRY_ENABLED=0          # 0=off (default), 1=on
WB_MAX_SYMBOL_LOSSES=1           # Max losses per symbol before blocking
WB_MAX_SYMBOL_TRADES=2           # Max total trades per symbol per session
```

## Regression Results (all gates OFF)

| Stock | Date | P&L | Baseline | Status |
|-------|------|-----|----------|--------|
| VERO | 2026-01-16 | +$6,890 | +$6,890 | PASS |
| GWAV | 2026-01-16 | +$6,735 | +$6,735 | PASS |
| ANPA | 2026-01-09 | +$2,088 | +$2,088 | PASS |

## Additional Fix
- `scanner_sim.py` line 265: changed gap threshold from `gap_pct < 10` to `gap_pct < 5` to match `live_scanner.py`.
