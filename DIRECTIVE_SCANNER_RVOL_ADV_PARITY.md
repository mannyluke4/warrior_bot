# DIRECTIVE: Fix Scanner RVOL — Align ADV Source with Live Bot

**Author**: Cowork (Opus)
**Date**: 2026-03-25
**For**: CC (Sonnet)
**Priority**: P0 — Scanner RVOL bug invalidates all batch backtests. Investigation (2026-03-25_scanner_rvol_investigation.md) confirmed the root cause: ADV differs by 59x between scanner_sim.py and stock_filter.py.

---

## Context

The RVOL investigation confirmed **Scenario B**: ADV computation differs between scanner_sim and stock_filter, producing wildly different RVOL values for the same stock.

**FEED on 2026-03-25:**
| Source | Cumulative Vol | ADV | RVOL |
|--------|---------------|-----|------|
| scanner_sim.py | 1,467,817 | 6,832,393 | 0.21x → FILTERED |
| stock_filter.py | ~2,200,000 | ~115,000 | 19.2x → PASSES |

**59x ADV difference.** Both use `StockBarsRequest` with `TimeFrame.Day` and the same API keys. Something about the bar requests or post-processing produces fundamentally different ADV values.

---

## Step 0: Git Pull + Regression

```bash
cd /Users/mannyluke/warrior_bot
git pull
source venv/bin/activate
```

Quick regression:
```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

---

## Step 1: Trace Both ADV Code Paths for FEED

Write a standalone diagnostic script (NOT in scanner_sim or stock_filter — don't modify production code). The script should:

### 1a. Reproduce scanner_sim's ADV for FEED

```python
# Replicate fetch_avg_daily_volume() for FEED on 2026-03-25
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta
import pytz

ET = pytz.timezone("US/Eastern")
date = datetime(2026, 3, 25)
start = date - timedelta(days=35)

request = StockBarsRequest(
    symbol_or_symbols=["FEED"],
    timeframe=TimeFrame.Day,
    start=ET.localize(datetime.combine(start.date(), datetime.min.time())),
    end=ET.localize(datetime.combine(date.date(), datetime.min.time())),
)
# NOTE: No feed= parameter — this matches scanner_sim.py
bars = hist_client.get_stock_bars(request)
```

Print EVERY bar returned: date, open, high, low, close, volume. Compute the average.

### 1b. Reproduce stock_filter's ADV for FEED

```python
# Replicate get_stock_info() for FEED
from datetime import timezone
end = datetime.now(timezone.utc)
start = end - timedelta(days=60)

request = StockBarsRequest(
    symbol_or_symbols=["FEED"],
    timeframe=TimeFrame.Day,
    start=start,
    end=end,
    feed="sip",  # stock_filter explicitly sets this
)
bars = hist_client.get_stock_bars(request)
```

Print EVERY bar returned: date, open, high, low, close, volume. Take `bars[-20:]` and compute the average.

### 1c. Compare

Document:
- How many bars each request returns
- The date range of bars returned
- Individual bar volumes (look for outliers)
- Whether adding `feed="sip"` to scanner_sim's request changes the result
- Whether removing `feed="sip"` from stock_filter's request changes the result
- Whether the 60-day vs 35-day window makes a difference
- Whether today's partial bar is included in stock_filter's result

---

## Step 2: Test Additional Stocks

Run the same comparison for at least 3 more stocks from today's filtered list:
- CODX (ADV 3,170,572 in scanner_sim)
- MKDW (ADV 259,956 in scanner_sim)
- WTO (ADV 99,633 in scanner_sim — closest to passing at 1.02x RVOL)

This tells us if the divergence is FEED-specific or systematic.

---

## Step 3: Identify the Fix

Based on Step 1-2 findings, one of these should be the answer:

### If `feed="sip"` is the difference:
Add `feed="sip"` to scanner_sim's `fetch_avg_daily_volume()` request at line 339. One-line fix.

### If the date window is the difference:
Align scanner_sim's window (currently 35 days) with stock_filter's (60 days).

### If today's partial bar is inflating stock_filter's denominator:
stock_filter at line 118 uses `bars[-20:]` which may include today's partial bar with very low volume, dragging down the average. This would make the live bot's RVOL artificially HIGH. The fix would be to exclude today's bar from the average in stock_filter (or include it in scanner_sim, though that's less correct).

### If it's something else entirely:
Document what you find. Include the raw bar data for FEED from both code paths.

---

## Step 4: Implement the Fix

**Gate the fix**: `WB_SCANNER_ADV_FIX=1` (OFF by default) in scanner_sim.py's `fetch_avg_daily_volume()`.

When ON, apply whatever alignment was identified in Step 3. When OFF, old behavior unchanged.

**Do NOT modify stock_filter.py** — the live bot is working correctly. We're aligning scanner_sim TO match it.

---

## Step 5: Validate the Fix

### 5a. Re-run today's scanner with fix ON:
```bash
WB_SCANNER_ADV_FIX=1 python scanner_sim.py 2026-03-25 2>&1 | tee /tmp/scanner_fix_0325.txt
```

**Expected**: FEED, MKDW, ANNA, etc. should now appear as candidates with RVOL > 2.0 (matching what the live bot found).

### 5b. Re-run a known good date to check for regressions:
```bash
WB_SCANNER_ADV_FIX=1 python scanner_sim.py 2026-01-30 2>&1 | tee /tmp/scanner_fix_0130.txt
```

**Expected**: At least the same candidates as before (VIVS, PMN), plus potentially NEW ones that were previously filtered.

### 5c. Run Jan comparison with fix:
```bash
WB_SCANNER_ADV_FIX=1 python run_jan_v1_comparison.py 2>&1 | tee /tmp/jan_v1_adv_fix.txt
```

Record new total P&L and compare to previous ($17,891). If the fix lets more stocks through, P&L should increase.

---

## Step 6: Report

Write to `cowork_reports/2026-03-25_adv_parity_fix.md`:

1. **Root cause** — exact difference between the two ADV code paths (with raw bar data evidence)
2. **Fix applied** — what was changed and why
3. **Validation results**:
   - Today's scanner: how many candidates now pass? Do they match live bot's 6 stocks?
   - Jan 30: any new candidates?
   - Jan comparison: P&L delta from the fix
4. **Recommendation** — should WB_SCANNER_ADV_FIX be enabled by default?

---

## Step 7: Git Push

```bash
git add scanner_sim.py .env cowork_reports/2026-03-25_adv_parity_fix.md
git commit -m "Scanner ADV parity fix: align avg daily volume with live bot computation

Root cause of RVOL mismatch: scanner_sim and stock_filter compute ADV
differently, causing 59x divergence (FEED: 6.8M vs 115K). Gated fix
aligns scanner_sim's ADV source with the live bot.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main
```

---

## Critical Notes

- **Do NOT modify stock_filter.py or bot.py** — the live bot is correct, we're fixing the backtest scanner
- **Gate everything** with WB_SCANNER_ADV_FIX (OFF by default)
- The diagnostic script from Step 1 should be saved to `/tmp/adv_trace.py` for future reference — do NOT commit it
- If the fix produces dramatically different Jan comparison results (>$5K delta), that's expected — it means we were systematically missing stocks. Report the delta clearly.
- Standalone regressions (VERO, ROLR) are unaffected — they don't use the scanner
