# Backtest Report: Trading Window Comparison — YTD 2026
## Date: 2026-03-26
## Branch: v2-ibkr-migration

---

## Objective

Test whether adding an **evening session (4PM-8PM ET)** to the existing morning session (7AM-12PM ET) captures meaningful additional edge. Also test whether a full-day window (4AM-8PM) reveals hidden midday opportunities.

---

## Results Summary

| Mode | Final Equity | P&L | Return | Trades | WR | Avg Win | Avg Loss |
|------|-------------|-----|--------|--------|----|---------|----------|
| **Morning + Evening** | **$291,106** | **+$261,106** | **+870.4%** | 50 | 93% (46W/3L) | $+5,698 | $-331 |
| Morning Only (baseline) | $150,221 | +$120,221 | +400.7% | 36 | 97% (34W/1L) | $+3,545 | $-321 |
| Full Day (4AM-8PM) | $144,392 | +$114,392 | +381.3% | 36 | 97% (34W/1L) | $+3,374 | $-321 |
| Morning + Evening (unlimited stocks) | $291,106 | +$261,106 | +870.4% | 50 | 93% (46W/3L) | $+5,698 | $-331 |

**Starting balance: $30,000 for all runs. Date range: Jan 2 - Mar 25, 2026 (57 trading days).**

---

## Key Findings

### 1. Evening Session Doubles Returns
The morning+evening combined run produced **+870% vs +400%** (morning only). The evening window adds **14 extra trades** and **+$141K** in additional profit. The edge is real and significant.

### 2. Midday Dead Zone Is Genuinely Dead
Full day (4AM-8PM) produced the **exact same 36 trades** as morning only — zero midday trades. The squeeze edge lives in pre-market momentum (morning) and after-hours catalysts (evening). The 12PM-4PM window is empty.

### 3. 5-Stock Limit Is Not the Bottleneck
Removing the 5-stock scanner cap produced **identical results** (50 trades, $291K). Scanner filters average 1.8 candidates/day — the quality filters are already tight enough. The 5-stock cap is a safety net that rarely fires.

### 4. sq_target_hit Remains Undefeated
Across all runs, the 2R mechanical target exit is **34/34 winners** ($254,740) in the combined run. The strategy's core edge holds in both windows.

---

## Exit Reason Breakdown (Morning + Evening Combined)

| Reason | Count | Wins | P&L |
|--------|-------|------|-----|
| sq_target_hit | 34 | 34 | +$254,740 |
| sq_para_trail_exit | 15 | 12 | +$6,696 |
| sq_max_loss_hit | 1 | 0 | -$330 |

---

## Evening Session Standout Trades

| Date | Symbol | P&L | Exit |
|------|--------|-----|------|
| Jan 13 | BCTX | +$13,343 | sq_target_hit |
| Jan 13 | AHMA | +$4,104 | sq_target_hit |
| Feb 3 | FIEE/NPT | +$70,771 (day) | sq_target_hit |
| Mar 6 | CRE | +$33,782 (day) | sq_target_hit |

---

## Scanner Candidate Distribution

- Average candidates per day: **1.8**
- Max candidates in one day: **10** (Mar 26, 2026)
- Days with >5 candidates: **1 out of 57**

---

## Actions Taken

Based on these results, the following changes were deployed:

### 1. Dual-Window Trading Schedule
- `WB_TRADING_WINDOWS=07:00-12:00,16:00-20:00` replaces old `SCAN_CUTOFF_HOUR` / `SHUTDOWN_HOUR`
- Bot sleeps during 12PM-4PM dead zone, auto-closes positions at window boundaries
- Shuts down after 8PM ET

### 2. Scanner Runs Continuously
- Removed V1's scanner cutoff feature — scanner runs during all active windows
- Fresh rescan when evening session opens

### 3. All Orders Are Limit Orders
- Entry: Limit buy + $0.02 pad, `outsideRth=True`
- Exit: Changed from MarketOrder to LimitOrder - $0.03, `outsideRth=True`
- Required for extended-hours trading (exchanges reject market orders outside RTH)

### 4. Evening Session Resets
- Detectors cleared on dead zone → active transition (morning state is stale)
- Bar builders rebuilt fresh for evening session
- Dead zone position auto-close with fallback price (last → bid → close)

### 5. Watchdog Extended
- daily_run.sh watchdog now runs until 6:05 PM MT (8:05 PM ET) to cover both sessions
- Single process, no restart needed between sessions

---

## Methodology

All backtests used:
- IBKR scanner data (unified, trustworthy RVOL)
- Tick-mode simulation via simulate.py
- Dynamic equity-based sizing: 2.5% of equity per trade
- $100K max notional (4x margin)
- 5 max trades per day, -$3K daily loss limit
- Bail timer: 5 minutes
