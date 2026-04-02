# Cowork Session Summary — April 1-2, 2026

**Session:** Claude Code (Opus 4.6)
**Duration:** ~12 hours across Apr 1-2
**Branch:** v2-ibkr-migration

---

## What Was Built

### 1. P0 Infrastructure Fixes (Apr 1)
- **Gateway watchdog** in daily_run.sh — background port monitor, HEALTH_OK log
- **Databento date bug** — live_scanner.py end_day fix (422 crash)
- **Candle exits ported to live bot** — TW/BE on 10s bars in bot_ibkr.py

### 2. Squeeze Detector V2 (Apr 1)
- **squeeze_detector_v2.py** — new module, drop-in replacement for V1
- COC hard gate, exhaustion gate, intra-bar ARM, rolling HOD gate
- Self-contained exit logic via check_exit()
- **Rolling HOD gate = the real winner** (+$14K over V1)
- Wired into simulate.py + bot_ibkr.py via WB_SQUEEZE_VERSION=1|2

### 3. V3 Hybrid Bot (Apr 1-2)
- **bot_v3_hybrid.py** — IBKR data + Alpaca execution
- Position safety: startup reconciliation, 60s heartbeat sync, fill verification, graceful shutdown
- **daily_run_v3.sh** — launch script with live_scanner.py + Gateway watchdog
- Cron updated to V3

### 4. V3 First Live Session (Apr 2 morning)
- Ran 06:17-12:00 ET, 4 stocks watched (BATL, SKYQ, TURB, KIDZ)
- 2 PRIMEDs, 0 trades — correct behavior confirmed by backtest
- Scanner-move paradox identified (SKYQ's discovery spike = the trade)
- **100% sim-vs-live match** on all 4 stocks

### 5. EPL Framework (Apr 2)
- **epl_framework.py** — GraduationContext, EPLWatchlist, StrategyRegistry, PositionArbitrator
- 21 unit tests, all passing
- Graduation hook fires on sq_target_hit in simulate.py

### 6. EPL MP Re-Entry Strategy (Apr 2)
- **epl_mp_reentry.py** — pullback detection after 2R graduation
- Own exits: hard stop, 1.5R trail, VWAP loss, 5-bar time stop
- ROLR: $17K → $54K with EPL (+$36K from re-entries)
- Full YTD: $201K (55 trades, 50% WR)

### 7. VWAP Floor Gate (Apr 2)
- Block EPL ARM when pullback low < VWAP
- Eliminated all 8 VWAP-loss losers
- **Full YTD: $252K** (45 trades, 59% WR) — best config

### 8. EPL VWAP Reclaim (Apr 2)
- **epl_vwap_reclaim.py** — deep pullback re-entry
- 0 trades on 63-day YTD — pattern doesn't exist on micro-caps
- Built and gated OFF

### 9. Candle Exit V2 (Apr 2)
- Tiered 1m exits: T1 (capital <1R), T2 (momentum 1-3R), T3 (runner ≥3R)
- Volume confirmation, tight trail mechanism, target-as-promotion
- $21K on megatest (worse — runner trail catches trades before candle patterns fire)
- Gated OFF, needs trail loosening

### 10. EPL Shipped to Live Bot (Apr 2)
- Full EPL wiring in bot_v3_hybrid.py
- Graduation hook, bar/tick processing, entry/exit execution
- .env: WB_EPL_ENABLED=1, WB_EPL_MP_ENABLED=1, WB_EPL_MP_VWAP_FLOOR=1

### 11. Box Scanner Phase 1 (Apr 2)
- **box_scanner.py** — ADR-based range scanner for mean-reversion
- Filters: ADR utilization ≥60%, price $5-100, VWAP proximity ≤3%, volume decline, stability
- Live + historical modes with ADR caching
- **First scan (Apr 1 @ 10:00 ET): LI (7.3), W (6.5), DKNG (6.3)**

### 12. Exhaustion Score Dataset (Apr 2)
- 33 trades analyzed at 2R target hit
- 10 missing tick caches fetched from Databento
- Threshold 4 best: flags 50% done stocks, 14% false positives
- VWAP distance = strongest done-vs-runner signal

---

## Key Numbers

| Config | YTD P&L | Trades | WR |
|--------|---------|--------|-----|
| V1 baseline | $154,849 | 26 | 73% |
| V2 rolling HOD only | $169,227 | 29 | 67% |
| V2 + EPL MP re-entry | $201,461 | 55 | 50% |
| **V2 + EPL + VWAP floor** | **$252,804** | **45** | **59%** |

**Best config: $30K → $283K (+842%) in 63 trading days.**

---

## Live Bot Status

- **V3 hybrid** running on Mac Mini (IBKR data + Alpaca execution)
- **Squeeze V2** with rolling HOD gate
- **EPL MP Re-Entry** with VWAP floor gate enabled
- **Cron:** daily_run_v3.sh at 2:00 AM MT weekdays
- **Pending:** pmset sleep prevention (sudo required)

---

## Box Scanner First Results (Apr 1 @ 10:00 ET)

| Rank | Symbol | Score | Price | Range | ADR Util | VWAP Dist | Vol Decline | Stability |
|------|--------|-------|-------|-------|----------|-----------|-------------|-----------|
| 1 | LI | 7.3 | $18.65 | 2.6% | 103% | 0.9% | 0.29 | 0.80 |
| 2 | W | 6.5 | $75.01 | 4.4% | 72% | 1.0% | 0.24 | 0.81 |
| 3 | DKNG | 6.3 | $22.30 | 3.3% | 67% | 0.3% | 0.52 | 0.88 |

**For Cowork/Manny review:** Pull 1m charts on TradingView for these 3 stocks on April 1, 10:00 AM onward. Did they stay range-bound? Would box trades (buy at LOD, sell at HOD) have been profitable?

---

## Files Created/Modified

| File | Action |
|------|--------|
| squeeze_detector_v2.py | NEW — V2 detector with candle intelligence |
| bot_v3_hybrid.py | NEW — IBKR data + Alpaca execution |
| daily_run_v3.sh | NEW — V3 launch script |
| epl_framework.py | NEW — EPL framework |
| epl_mp_reentry.py | NEW — MP re-entry strategy |
| epl_vwap_reclaim.py | NEW — VWAP reclaim strategy (0 trades) |
| box_scanner.py | NEW — Range-bound stock scanner |
| run_box_scanner_ytd.py | NEW — YTD scanner runner |
| test_epl_framework.py | NEW — 21 unit tests |
| analyze_exhaustion_data.py | NEW — Exhaustion score data gathering |
| simulate.py | MODIFIED — V2 wiring, EPL hooks |
| bot_ibkr.py | MODIFIED — V2 import switch, candle exits |
| daily_run.sh | MODIFIED — Gateway watchdog |
| live_scanner.py | MODIFIED — Databento date fix |
| .env | MODIFIED — V2, EPL, box scanner vars |
