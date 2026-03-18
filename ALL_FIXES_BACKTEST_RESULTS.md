# All 5 Fixes — Full Backtest Validation
## Generated: 2026-03-18

## Regression Tests

| Test | Previous | Expected | Actual | Status |
|------|----------|----------|--------|--------|
| VERO 01-16 | +$9,166 | +$18,583 | **+$18,583** (+18.6R) | **PASS** ✅ |
| ROLR 01-14 | +$3,242 | ~+$6,444 | **+$6,444** (+6.4R) | **PASS** ✅ |
| LUNL 03-17 | -$821 → +$464 | +$464 | **+$464** (+0.5R) | **PASS** ✅ |

VERO doubled (+$9,417 more) thanks to Fix 5 (TW profit gate). ROLR nearly doubled (+$3,202 more). LUNL protected by Fix 2 (tiered cap).

---

## Weekly Backtest — Full Progression

| Stage | Trades | Wins | Losses | Win Rate | Net P&L |
|-------|--------|------|--------|----------|---------|
| Old config (pre-sync) | 12 | 4 | 6 | 40% | +$9 |
| Synced config (no fixes) | 12 | 4 | 8 | 33% | -$1,411 |
| Fixes 1-4 only | 11 | 4 | 7 | 36% | +$221 |
| Fixes 1-4 + float propagation | 11 | 5 | 6 | 45% | +$1,158 |
| **All 5 fixes (incl TW profit gate)** | **11** | **5** | **6** | **45%** | **+$1,158** |

Fix 5 (TW profit gate at 1.5R) had **no additional impact on the weekly data** — none of the weekly TW exits were above 1.5R at exit time, so the gate never fired. The weekly improvement is entirely from Fixes 1-4 + float propagation.

Fix 5's value shows on the 49-day data (VERO +$9,417, ROLR +$3,202) where the big runners live.

---

## Weekly Trade Detail (All 5 Fixes ON)

| # | Date | Symbol | Float | Entry | Exit | R | Score | Exit Reason | P&L | R-Mult |
|---|------|--------|-------|-------|------|---|-------|-------------|-----|--------|
| 1 | 03-09 | HIMZ | 6.0M | $2.36 | $2.26 | $0.15 | 12.0 | bearish_engulfing | **-$675** | -0.7R |
| 2 | 03-10 | INKT | 1.68M | $20.02 | $19.38 | $1.83 | 14.0 | bearish_engulfing | **-$349** | -0.3R |
| 3 | 03-10 | GITS | 2.46M | $2.54 | $2.76 | $0.08 | 10.5 | bearish_engulfing | **+$2,748** | +2.7R |
| 4 | 03-12 | TLYS | 9.29M | $2.72 | $2.73 | $0.13 | 12.0 | topping_wicky | **+$77** | +0.1R |
| 5 | 03-12 | FLYT | 0.31M | $11.49 | $11.25 | $0.20 | 14.0 | stop_hit | **-$1,044** | -1.2R |
| 6 | 03-17 | OKLL | 1.36M | $10.05 | $10.24 | $0.16 | 12.5 | bearish_engulfing | **+$945** | +1.2R |
| 7 | 03-17 | LUNL | 0.17M | $13.00 | $13.13 | $0.28 | 14.0 | topping_wicky | **+$464** | +0.5R |
| 8 | 03-17 | BIAF | 4.35M | $2.85 | $2.83 | $0.24 | 12.5 | topping_wicky | **-$85** | -0.1R |
| 9 | 03-17 | TRT | 4.99M | $6.26 | $6.16 | $0.11 | 6.0 | max_loss_hit | **-$784** | -0.9R |
| 10 | 03-18 | BMNZ | 2.0M | $16.99 | $17.03 | $0.19 | 10.6 | topping_wicky | **+$118** | +0.2R |
| 11 | 03-18 | BMNZ | 2.0M | $17.51 | $17.42 | $0.10 | 9.3 | max_loss_hit | **-$257** | -0.9R |

### Trades Blocked by Fixes:
- **HIMZ #2** (03-09): Blocked by Fix 4 (no re-entry after loss) — would have lost -$399
- **TRT #2** (03-17): Blocked by Fixes 3+4 (cooldown + no re-entry) — would have lost -$916

---

## Fix Impact Summary

| Fix | Description | Weekly Impact | Standalone Impact |
|-----|------------|--------------|-------------------|
| 1 | Direction-aware cont hold | +$317 (INKT) | — |
| 2 | Float-tiered max loss cap | +$1,285 (LUNL) - $348 (FLYT) = +$937 | — |
| 3 | max_loss_hit cooldown | Overlaps Fix 4 | — |
| 4 | No re-entry after loss | +$1,315 (HIMZ#2 + TRT#2) | — |
| 5 | TW profit gate (1.5R) | $0 on weekly | VERO +$9,417, ROLR +$3,202 |
| **Combined** | | **+$2,569 vs synced baseline** | **+$12,619 on runners** |

---

## Key Metrics

| Metric | Value |
|--------|-------|
| Weekly P&L (all 5 fixes) | **+$1,158** |
| VERO standalone | **+$18,583** (was +$9,166) |
| ROLR standalone | **+$6,444** (was +$3,242) |
| Total improvement vs synced baseline | **+$2,569** (weekly) + **$12,619** (runners) |
| Blocked revenge trades | 2 (saved $1,315) |
| Win rate | 45.5% (up from 33%) |

---

## Ready for Live Trading

All 5 fixes validated. Mac Mini `.env` is synced with:
```
WB_CONT_HOLD_DIRECTION_CHECK=1
WB_MAX_LOSS_R_TIERED=1
WB_MAX_LOSS_R_ULTRA_LOW_FLOAT=0
WB_MAX_LOSS_R_LOW_FLOAT=0.85
WB_MAX_LOSS_TRIGGERS_COOLDOWN=1
WB_NO_REENTRY_ENABLED=1
WB_TW_MIN_PROFIT_R=1.5
```

Code is on HEAD, regressions pass, ready for tomorrow's session.
