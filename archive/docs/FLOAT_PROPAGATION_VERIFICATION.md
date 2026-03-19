# Float Data Propagation — Verification Results
## 2026-03-18

## All Tests Pass

| Test | Float | Tier | Expected | Actual | Status |
|------|-------|------|----------|--------|--------|
| LUNL 03-17 | 0.17M | Ultra-low → NO cap | TW exit +$464 | **+$464** (+0.5R) | **PASS** ✅ |
| FLYT 03-12 | 0.31M | Ultra-low → NO cap | stop_hit ~-$1,200 | **-$1,044** (-1.2R) | **PASS** ✅ |
| ROLR 01-14 | 3.78M | Low → 0.85R cap | Survives | **+$3,242** (+3.2R) | **PASS** ✅ |
| VERO 01-16 | 1.6M | Low → 0.85R cap | +$9,166 | **+$9,166** (+9.2R) | **PASS** ✅ |

## Impact

| Trade | Before Float Fix | After Float Fix | Delta |
|-------|-----------------|----------------|-------|
| LUNL | -$821 (0.75R cap) | **+$464** (TW exit) | **+$1,285** |
| FLYT | -$696 (0.75R cap) | **-$1,044** (stop_hit) | **-$348** |
| **Net** | | | **+$937** |

## Updated Weekly P&L Progression

| Stage | P&L | Delta |
|-------|-----|-------|
| Old config (pre-sync) | +$9 | — |
| New config (synced, no fixes) | -$1,411 | -$1,420 |
| + All 4 strategy fixes | +$221 | +$1,632 |
| **+ Float propagation fix** | **+$1,158** | **+$937** |
