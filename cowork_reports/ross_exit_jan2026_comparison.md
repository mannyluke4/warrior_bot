# Ross Exit System — Jan 2026 Comparison Report

**Generated:** 2026-03-22
**Method:** Tick-mode backtest, 07:00–12:00 ET, tick_cache/
**Baseline:** `WB_MP_ENABLED=1`
**Ross exit:** `WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1`
**Scope:** All 100 Jan 2026 stocks in tick_cache; only stocks with non-zero baseline P&L shown in detail.

---

## Stocks With Trades (Non-Zero Baseline)

| Stock | Date | Baseline P&L | Ross Exit P&L | Delta | Ross Signals Fired |
|-------|------|-------------|---------------|-------|-------------------|
| SNSE | 2026-01-02 | +$1,045 | +$1,295 | **+$250** | ross_vwap_break |
| RKLZ | 2026-01-05 | -$198 | +$48 | **+$246** | ross_cuc_exit |
| SOLT | 2026-01-05 | -$264 | -$165 | **+$99** | ross_doji_partial |
| MNTS | 2026-01-07 | +$92 | +$92 | $0 | — |
| NVVE | 2026-01-07 | -$371 | -$674 | **-$303** | ross_cuc_exit |
| ACON | 2026-01-08 | -$20 | +$480 | **+$500** | — (exit timing shift) |
| IPW | 2026-01-08 | -$1,075 | +$94 | **+$1,169** | ross_shooting_star |
| SXTC | 2026-01-08 | +$2,213 | +$565 | **-$1,648** | ross_cuc_exit, ross_doji_partial |
| BDSX | 2026-01-12 | +$174 | +$5 | **-$169** | ross_cuc_exit |
| CLRB | 2026-01-12 | -$636 | -$368 | **+$268** | ross_cuc_exit |
| AHMA | 2026-01-13 | +$3,163 | +$3,652 | **+$489** | ross_cuc_exit |
| AHMA | 2026-01-14 | -$314 | -$314 | $0 | — |
| ROLR | 2026-01-14 | +$16,195 | +$18,650 | **+$2,455** | ross_doji_partial |
| AGPU | 2026-01-15 | +$926 | +$1,092 | **+$166** | ross_cuc_exit |
| CEPT | 2026-01-15 | -$360 | -$290 | **+$70** | — (exit timing shift) |
| CJMB | 2026-01-15 | +$4,017 | +$4,017 | $0 | — |
| SPHL | 2026-01-15 | +$4,575 | +$4,139 | **-$436** | ross_cuc_exit |
| LCFY | 2026-01-16 | -$426 | -$426 | $0 | — |
| VERO | 2026-01-16 | +$20,922 | +$11,904 | **-$9,018** | ross_cuc_exit |
| BNAI | 2026-01-21 | -$1,945 | -$1,945 | $0 | — |
| GITS | 2026-01-21 | -$418 | -$435 | **-$17** | — |
| SLGB | 2026-01-21 | +$2,759 | +$2,759 | $0 | — |
| IOTR | 2026-01-22 | -$2,537 | -$2,829 | **-$292** | ross_cuc_exit |
| SXTP | 2026-01-22 | -$1,821 | -$1,321 | **+$500** | — (exit timing shift) |
| AUST | 2026-01-23 | -$250 | $0 | **+$250** | ross_shooting_star |
| MOVE | 2026-01-23 | +$5,452 | +$5,282 | **-$170** | ross_cuc_exit |
| BATL | 2026-01-26 | +$2,925 | +$2,925 | $0 | — |
| NVVE | 2026-01-26 | +$6,102 | +$6,102 | $0 | — |
| CYN | 2026-01-27 | -$792 | -$396 | **+$396** | — (exit timing shift) |
| NUWE | 2026-01-27 | -$143 | -$143 | $0 | — |
| XHLD | 2026-01-27 | -$440 | -$256 | **+$184** | ross_doji_partial |
| SLGB | 2026-01-28 | +$5,951 | +$5,568 | **-$383** | — (exit timing shift) |
| FEED | 2026-01-29 | +$609 | -$159 | **-$768** | ross_cuc_exit |
| PMN | 2026-01-30 | +$363 | +$815 | **+$452** | ross_cuc_exit |

---

## Totals (Trading Stocks Only)

| Metric | Baseline | Ross Exit | Delta |
|--------|----------|-----------|-------|
| **Total P&L** | **+$65,473** | **+$59,763** | **-$5,710** |
| Stocks with trades | 34 | 34 | — |
| Stocks improved | — | 15 | — |
| Stocks hurt | — | 11 | — |
| Stocks unchanged | — | 8 | — |

---

## Ross Signal Breakdown

| Signal | Times Fired | Net Delta (stocks where fired) |
|--------|-------------|-------------------------------|
| `ross_cuc_exit` | 13 | -$7,094 |
| `ross_doji_partial` | 4 | +$2,401 |
| `ross_shooting_star` | 2 | +$1,419 |
| `ross_vwap_break` | 1 | +$250 |

---

## Key Observations

### The VERO Problem (-$9,018)
- Baseline: Trade 1 holds all the way to BE exit at `bearish_engulfing_exit_full`, capturing +$18,583 (18.6R)
- Ross exit: `ross_cuc_exit` fires at 4.94 (07:21), locking in only +$11,333 (11.3R)
- The early exit causes the bot to re-enter 3x in a choppy regime post-11R, losing $571 on those re-entries
- **Root cause:** `ross_cuc_exit` is too aggressive on multi-bar runners. Ross's CUC exit is designed for the first red candle after a long green run — but VERO keeps running after the "CUC" candle, so the early exit misses the full 18.6R move.

### SXTC Problem (-$1,648)
- Baseline: +$2,213 (clean trend hold)
- Ross exit: `ross_cuc_exit` + `ross_doji_partial` chop the trade into fragments, netting only +$565
- Similar pattern: early partial exit disrupts the hold on a genuine runner

### FEED Problem (-$768)
- Baseline: +$609 (steady trend exit)
- Ross exit: `ross_cuc_exit` fires too early, converting a winner to -$159

### Bright Spots
- **ROLR +$2,455**: `ross_doji_partial` correctly takes partial at 1.8R when 3rd trade stalls at $9.34, enabling re-entry at $14.04 for +$7,053 (28.3R). Net improvement.
- **IPW +$1,169**: `ross_shooting_star` flips a -$1,075 loser to +$94 by exiting early on a shooting star pattern — stops a bad trade before full stop hit.
- **ACON +$500**: Exit timing shift (not a named Ross signal) turns -$20 into +$480. Re-entry dynamics improved.
- **AHMA 01-13 +$489**: `ross_cuc_exit` correctly clips a partial, enabling a better re-entry sequence.

---

## Verdict

**Net impact: -$5,710 (-8.7%) on Jan 2026 tick-cache universe.**

The Ross exit system is **net negative** due primarily to VERO (-$9,018) — where `ross_cuc_exit` fires prematurely on the biggest runner of the month, cutting the trade from 18.6R to 11.3R.

`ross_doji_partial` and `ross_shooting_star` are both net positive individually. `ross_cuc_exit` is net negative, dragging the system down.

**Recommendation:** Consider gating `ross_cuc_exit` to only fire when:
- The unrealized gain is below a threshold (e.g., < 5R), OR
- The stock has already printed a confirmed reversal (not just a red candle after green run)

This would protect VERO-class runners while still using the CUC signal for smaller/choppier setups.

---

*All runs: tick mode, WB_MP_ENABLED=1, risk=$1000, slippage=$0.02, exit=signal*
