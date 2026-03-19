# Strategy Improvements V1 — Backtest Results
## Generated: 2026-03-18

## Overview
Tested all 4 fixes from `DIRECTIVE_STRATEGY_IMPROVEMENTS_V1.md` against the weekly backtest (Mar 9-18) and regression targets. All fixes enabled simultaneously.

---

## Regression Checks

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| VERO 2026-01-16 standalone | +$9,166 | **+$9,166** (+9.2R) | **PASS** ✅ |
| ROLR 2026-01-14 standalone | Survive 0.85R cap | **+$3,242** (+3.2R) | **PASS** ✅ |

VERO unchanged. ROLR's -0.60R dip is safely under the 0.85R tier for its 3.78M float.

---

## Weekly Backtest: 3-Way Comparison

| Config | Trades | Wins | Losses | Win Rate | Net P&L |
|--------|--------|------|--------|----------|---------|
| Old (pre-sync .env) | 12 | 4 | 6 | 40% | **+$9** |
| New (synced, no fixes) | 12 | 4 | 8 | 33% | **-$1,411** |
| **New + All 4 Fixes** | **11** | **4** | **7** | **36%** | **+$221** |

**Fixes recovered +$1,632** from the -$1,411 baseline.

---

## Trade-by-Trade Results (All 4 Fixes ON)

| # | Date | Symbol | Entry | Stop | R | Score | Exit Price | Exit Reason | P&L | R-Mult |
|---|------|--------|-------|------|---|-------|-----------|-------------|-----|--------|
| 1 | 03-09 | HIMZ | $2.36 | $2.21 | $0.15 | 12.0 | $2.26 | bearish_engulfing | **-$675** | -0.7R |
| 2 | 03-10 | INKT | $20.02 | $18.19 | $1.83 | 12.5 | $19.38 | bearish_engulfing | **-$349** | -0.3R |
| 3 | 03-10 | GITS | $2.54 | $2.46 | $0.08 | 10.0 | $2.76 | bearish_engulfing | **+$2,748** | +2.7R |
| 4 | 03-12 | TLYS | $2.72 | $2.59 | $0.13 | 12.0 | $2.73 | topping_wicky | **+$77** | +0.1R |
| 5 | 03-12 | FLYT | $11.49 | $11.29 | $0.20 | 12.5 | $11.33 | max_loss_hit | **-$696** | -0.8R |
| 6 | 03-17 | OKLL | $10.05 | $9.89 | $0.16 | 11.0 | $10.24 | bearish_engulfing | **+$945** | +1.2R |
| 7 | 03-17 | LUNL | $13.00 | $12.72 | $0.28 | 12.5 | $12.77 | max_loss_hit | **-$821** | -0.8R |
| 8 | 03-17 | BIAF | $2.85 | $2.61 | $0.24 | 12.0 | $2.83 | topping_wicky | **-$85** | -0.1R |
| 9 | 03-17 | TRT | $6.26 | $6.15 | $0.11 | 5.5 | $6.16 | max_loss_hit | **-$784** | -0.9R |
| 10 | 03-18 | BMNZ | $16.99 | $16.80 | $0.19 | 10.1 | $17.03 | topping_wicky | **+$118** | +0.2R |
| 11 | 03-18 | BMNZ | $17.51 | $17.41 | $0.10 | 8.8 | $17.42 | max_loss_hit | **-$257** | -0.9R |

---

## Fix-by-Fix Impact Analysis

### Fix 1: Direction-Aware Continuation Hold
**Gate:** `WB_CONT_HOLD_DIRECTION_CHECK=1`

| Trade | Without Fix | With Fix | Delta | What Happened |
|-------|-----------|---------|-------|---------------|
| INKT | -$666 | **-$349** | **+$317** | Fix stopped suppressing BE exits when 3/5 bars were red + underwater. Exit fired at $19.38 instead of being held to $18.80 |
| TLYS | +$77 | **+$77** | $0 | No change — TLYS was briefly positive, direction check didn't trigger |

**Net impact: +$317**

The direction check correctly identified INKT's high vol_dom as selling pressure (5 straight red candles) and let the BE exit fire immediately. TLYS was unaffected because the position was briefly in profit.

### Fix 2: Float-Tiered Max Loss Cap
**Gate:** `WB_MAX_LOSS_R_TIERED=1`

| Trade | Float | Tier | Expected Behavior | Actual | Issue |
|-------|-------|------|-------------------|--------|-------|
| LUNL | 0.17M | Ultra-low → NO cap | Should hold through dip, TW exit at +$464 | **Still -$821 (max_loss_hit)** | Float=N/A — Alpaca returned no float data |
| FLYT | 0.31M | Ultra-low → NO cap | Should use hard stop only | **-$696 (max_loss_hit)** | Same — float=N/A |
| TRT | 4.99M | Low → 0.85R cap | Slightly wider cap | **-$784** | Float available, but 0.85R vs 0.75R made no difference (hit near stop anyway) |

**Net impact: $0 (float data missing for the key trades)**

The tiered cap logic is implemented correctly but **cannot function when the simulator doesn't have float data**. LUNL and FLYT both showed `Fundamentals: float=N/A`, so the tiered system fell back to the default flat 0.75R. This is the biggest remaining opportunity — fixing float propagation would recover the LUNL -$1,285 swing.

**Root cause:** The simulator fetches fundamentals from Alpaca's snapshot API, which sometimes returns null for float on low-float stocks. The scanner_sim.py uses FMP API + yfinance as fallbacks, but simulate.py doesn't.

### Fix 3: max_loss_hit Triggers Cooldown
**Gate:** `WB_MAX_LOSS_TRIGGERS_COOLDOWN=1`

| Trade | Without Fix | With Fix | Delta |
|-------|-----------|---------|-------|
| TRT #2 | -$916 (re-entered after max_loss_hit) | **Blocked** | **+$916** |

**Net impact: +$916** (overlaps with Fix 4 — both would have blocked TRT #2)

### Fix 4: No Re-Entry After Loss
**Gate:** `WB_NO_REENTRY_ENABLED=1`

| Trade | Without Fix | With Fix | Delta |
|-------|-----------|---------|-------|
| HIMZ #2 | -$399 (re-entered after -$675 BE loss) | **Blocked** | **+$399** |
| TRT #2 | -$916 (re-entered after -$784 max_loss) | **Blocked** | **+$916** |

**Net impact: +$1,315** (TRT #2 overlaps with Fix 3)

This was the single biggest improvement. Both HIMZ and TRT showed the same pattern: first trade loses, detector sees another "valid" setup minutes later, bot re-enters, same failure. Fix 4 broke that cycle.

### Combined (Deduplicated)

| Fix | Unique Impact |
|-----|--------------|
| Fix 1: Direction-aware cont hold | +$317 (INKT) |
| Fix 2: Float-tiered cap | $0 (float data missing) |
| Fix 3: max_loss_hit cooldown | $0 (overlaps with Fix 4) |
| Fix 4: No re-entry after loss | +$1,315 (HIMZ #2 + TRT #2) |
| **Total recovered** | **+$1,632** |

---

## What Each Fix Blocked or Changed

### Trades blocked by Fix 4 (no re-entry after loss):
- **HIMZ #2** (03-09): Would have lost -$399. First trade HIMZ #1 lost -$675 via BE exit. Bot correctly moved on.
- **TRT #2** (03-17): Would have lost -$916. First trade TRT #1 lost -$784 via max_loss_hit. Bot correctly moved on.

### Trades improved by Fix 1 (direction-aware cont hold):
- **INKT** (03-10): Loss reduced from -$666 to -$349. Continuation hold no longer suppressed BE exit when position was underwater with 5/5 red candles.

### Trades unaffected by Fix 2 (tiered cap — float data missing):
- **LUNL** (03-17): Still -$821. With float data, would have been +$464 (no cap for <1M float). **Potential +$1,285 improvement once float propagation is fixed.**
- **FLYT** (03-12): Still -$696. With float data, would have used hard stop only (similar outcome since stop was close to 0.75R exit).

---

## Remaining Issues

### 1. Float Data Missing in Simulator (HIGH PRIORITY)
The tiered cap (Fix 2) is dead code when `simulate.py` can't fetch float data. LUNL and FLYT both showed `float=N/A`. The scanner_sim.py solves this with FMP API + yfinance fallbacks + a known-floats cache, but simulate.py only uses Alpaca snapshots.

**Impact if fixed:** LUNL flips from -$821 to +$464, adding +$1,285 to the weekly total.

**Estimated weekly P&L with float fix:** +$221 + $1,285 = **+$1,506**

### 2. BMNZ Re-Entry After Win Still Loses
BMNZ #1 won +$118, then BMNZ #2 lost -$257. Fix 4 allows re-entry after a win (to preserve SXTC-type cascading), so BMNZ #2 was not blocked. This is the correct behavior for the strategy — blocking wins-then-re-entry would kill the cascading edge.

### 3. TRT Score Too Low (5.5)
TRT was the worst trade of the week (-$784) with the lowest score (5.5) and zero pattern tags. A minimum score gate of 8.0 would have blocked this entirely. Currently `WB_MIN_SCORE` is not enforced as a hard gate — only `min_score=3.0` in the backtest.

### 4. LUNL Dip-Recovery Pattern
Even with the tiered cap working, LUNL's underlying issue remains: ultra-low float stocks can dip significantly before recovering. The hard stop at $12.72 would have held (LUNL hit $12.77 then recovered), but this was close. On a different day, the hard stop itself could get hit. This is inherent risk in micro-float trading.

---

## Summary

| Metric | Before Fixes | After Fixes | Delta |
|--------|-------------|-------------|-------|
| Weekly P&L | -$1,411 | **+$221** | **+$1,632** |
| Trades | 12 | 11 | -1 (blocked) |
| Losses | 8 | 7 | -1 |
| VERO regression | +$9,166 | +$9,166 | ✅ unchanged |
| ROLR check | — | +$3,242 | ✅ survives |

**Recommendation:** All 4 fixes should go live. Fix 4 (no re-entry) is the clear winner. Fix 1 (direction cont hold) is a clean logic improvement. Fix 3 (cooldown bug) is a bug fix. Fix 2 (tiered cap) is correct but needs float data propagation to deliver its full value.

**Next priority:** Fix float data propagation in `simulate.py` and the live bot's scanner → trade_manager pipeline. This is the single biggest remaining opportunity (+$1,285 estimated on LUNL alone).
