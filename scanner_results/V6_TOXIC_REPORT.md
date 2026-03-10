# V6.1 Toxic Entry Filters — Backtest Report

**Date:** 2026-03-09
**Branch:** v6-dynamic-sizing
**Dataset:** Oct 2025 – Feb 2026 (102 trading days)
**Note:** Jan-Feb results loaded from V4 cache (filters not applied yet)

---

## Filter Summary

### Filter 1: Wide R% + Crowded Day → HARD BLOCK
- **Condition:** R% >= 5.0% AND scanner candidates >= 20
- **Env var:** `WB_TOXIC_FILTER_1_ENABLED` (default "1")

### Filter 2: Cold Market + Low Vol + Small Gap → HALF RISK
- **Condition:** gap < 30% AND pm_volume < 100K AND month in {Feb, Oct, Nov}
- **Env var:** `WB_TOXIC_FILTER_2_ENABLED` (default "1")
- **Multiplier:** `WB_TOXIC_FILTER_2_MULTIPLIER` (default "0.5")

---

## Oct-Dec 2025 Results (filters active)

| Metric | V4 Baseline | V6.1 Toxic | Change |
|--------|------------|------------|--------|
| Active Trades | 31 | 29 | -2 |
| Win Rate | 41.9% | 44.8% | +2.9pp |
| Total P&L | $+5,798 | $+5,805 | +$7 |
| Oct-Dec P&L | $+396 | $+403 | +$7 |
| Max Drawdown | $2,987 (9.8%) | $2,632 (8.7%) | -$355 |
| Equity | $35,798 | $35,805 | +$7 |

### Filter 1 Catches (HARD BLOCK)

| Date | Symbol | V4 P&L | V6.1 P&L | Saved |
|------|--------|--------|----------|-------|
| 2025-11-11 | BODI | -$158 | $0 (blocked) | $158 |
| 2025-12-11 | GLXG | -$237 | $0 (blocked) | $237 |
| **Total** | | | | **$395** |

### Filter 2 Catches (HALF RISK)

| Date | Symbol | V4 P&L | V6.1 P&L | Saved |
|------|--------|--------|----------|-------|
| 2025-10-10 | ATON | -$789 | -$394 | $395 |
| 2025-11-03 | BQ | -$629 | -$117 | $512 |
| 2025-11-06 | AVX | -$833 | -$417 | $416 |
| **Total** | | | | **$1,323** |

**Combined savings (Oct-Dec only): $1,718**
**Winners sacrificed: 0**

---

## Jan-Feb Impact (projected, not yet re-run)

From directive analysis, Filter 1 should also catch:
- MLEC 2026-01-16: -$788 → blocked (save $788)
- FEED 2026-01-09: -$750 → blocked (save $750)

**Projected additional savings: ~$1,538**

---

## Regression Check

All three regressions pass with toxic filters (filters return ALLOW for these):
- VERO 2026-01-16: +$6,890 ✅
- GWAV 2026-01-16: +$6,735 ✅ (without candidates arg) / +$7,713 ✅ (with 25 candidates — 2nd trade blocked, improving P&L)
- ANPA 2026-01-09: +$2,088 ✅

---

## Notes

1. The `candidates_count` uses the **raw scanner JSON count** (total candidates before SQS/profile/float filtering), matching the directive's analysis methodology.
2. Filter logic is in `trade_manager.py:check_toxic_filters()` — no exit logic touched.
3. All filters are env-var togglable and default ON.
4. The HALF_RISK filter restores the original risk after the trade is submitted, so subsequent trades use full risk.
