# CC Report: Morning Session — 2026-03-25
## Date: 2026-03-25
## Machine: Mac Mini

---

## ⚠️ P0 CRITICAL FINDING: Scanner RVOL Bug Invalidates All Batch Backtests

### The Bug

`scanner_sim.py` computes RVOL using **PM volume (4:00-7:15 AM only)** for ALL stocks — including rescan stocks discovered at 8:00, 8:45, 9:30. A stock that starts moving at 8:00 AM has near-zero PM volume before 7:15, so its RVOL is < 2.0 → **filtered out**.

The live bot (`stock_filter.py`) uses Alpaca's `daily_bar.volume` which is **cumulative for the entire day**. At 8:45, FEED shows RVOL = 19.2x → passes easily.

### Evidence (Today, 2026-03-25)

```
scanner_sim.py: 13 raw PM candidates → ALL 13 filtered by RVOL<2.0 or PM vol<50K → 0 remain
                18 rescan candidates found with real volume → ALL filtered → 0 total candidates

Live bot:       6 stocks passed (RBNE, FEED, MKDW, CVV, ANNA, CRCD)
```

The rescan even computed the correct cumulative volumes:
- FEED: 1,467,817 at 08:45 (but RVOL gate used stale PM-only volume → filtered)
- CODX: 1,765,301 at 08:00 (filtered)
- BIAF: 967,252 at 07:15 (filtered)

### Impact

**Every batch backtest that uses scanner_results JSON files is affected:**
- Megatest (+$130K) — understated, missing rescan stocks
- OOS 2025 Q4 (+$44K) — understated
- YTD Jan comparisons — understated
- All historical scanner data — systematically excludes stocks that built volume after 7:15 AM

**NOT affected:**
- Standalone regressions (VERO, ROLR) — these use simulate.py directly, no scanner
- Strategy logic, entry/exit behavior — these are correct (confirmed by today's live vs backtest comparison)

### Root Cause

In `scanner_sim.py`, the RVOL gate at Step 4a (line ~650) runs on `pm_volume` from the 4:00-7:15 PM scan. The rescan at Step 4b computes `cumulative vol 4AM-{checkpoint}` but this volume is NOT used to recompute RVOL. The gate uses the original stale PM-only number.

### Fix Required

Rescan stocks must have their RVOL recomputed using cumulative volume at discovery time, not PM-only volume. The cumulative volume is already being fetched — it just needs to be used for the RVOL calculation before the filter gate runs.

---

## Session Overview

- **Startup**: Clean at 4:04 AM ET, no websocket errors, no TWS
- **Scanner**: 6 stocks passed filters (RBNE, FEED, MKDW, CVV, ANNA, CRCD)
- **First ever live squeeze trade**: FEED at 09:36 ET
- **Result**: 1 trade, **-$271**

---

## Live Trading Activity

| Time | Stock | Event | Details |
|------|-------|-------|---------|
| 04:11 | MKDW | MP entry blocked | Score 3.5, WB_MP_ENABLED=0 |
| 06:40 | FEED | MP entry blocked | Score 11.0, WB_MP_ENABLED=0 |
| 08:01 | ANNA | SQ PRIMED+ARMED | Vol 101.5x avg! ARMED $8.02 [PARABOLIC] — never triggered (price didn't break) |
| 08:28 | FEED | SQ PRIMED | Vol 9.0x — no level break |
| 08:46 | FEED | SQ PRIMED | Vol 7.1x — no level break |
| 09:06 | FEED | SQ PRIMED | Vol 3.2x — no level break |
| **09:36** | **FEED** | **SQ ENTRY** | **Score 13.3, PM high break $2.78, PARABOLIC PROBE, qty=2,083** |
| **09:36** | **FEED** | **SQ EXIT** | **topping_wicky_exit_full → P&L = -$271** |
| 10:26 | MKDW | MP entry blocked | Score 10.5, WB_MP_ENABLED=0 |

---

## Live vs Backtest Comparison

Ran all 6 live bot stocks through simulate.py with identical settings (SQ ON, MP OFF, bail timer ON, --no-fundamentals):

| Stock | Live Bot | Backtest | Match? |
|-------|----------|----------|--------|
| RBNE | 0 trades | 0 trades | YES |
| **FEED** | **-$271** (TW exit) | **-$179** (sq_para_trail) | **PARTIAL** |
| MKDW | 0 trades | 0 trades | YES |
| CVV | 0 trades | 0 trades | YES |
| ANNA | 0 trades | 0 trades | YES |
| CRCD | 0 trades | 0 trades | YES |

**5 of 6 stocks match perfectly.** FEED is the discrepancy.

### FEED Discrepancy Detail

| Metric | Live Bot | Backtest |
|--------|----------|----------|
| Entry trigger | $2.78 | $2.78 |
| Entry fill | $2.88 | $2.80 |
| Exit price | $2.75 | $2.75 |
| Exit reason | `topping_wicky_exit_full` | `sq_para_trail_exit` |
| P&L | -$271 | -$179 |
| Qty | 2,083 | ~3,571 |

**Three root causes:**
1. **Entry slippage** — Live fill at $2.88 vs backtest $2.80. Expected with real order execution (limit + chase).
2. **Exit routing BUG** — Live used `topping_wicky_exit_full` (10s bar MP pattern exit) instead of squeeze's `sq_para_trail_exit`. The squeeze trade should have been routed through `_squeeze_manage_exits()` which doesn't use TW exits.
3. **Qty difference** — Live sized at 2,083 vs backtest ~3,571. Different entry price + possible sizing path difference.

---

## Scanner Divergence (Still Present)

| Source | Stocks Found |
|--------|-------------|
| Live bot (stock_filter.py) | 6 stocks: RBNE, FEED, MKDW, CVV, ANNA, CRCD |
| Scanner sim (scanner_sim.py) | **0 stocks** — 13 raw candidates, all filtered by RVOL/PM vol |

The scanner parity fix (all reading from .env) didn't resolve this. The fundamental issue is different data sources: live uses real-time Alpaca snapshots, scanner_sim uses historical 1m bars. They compute volume and RVOL differently.

---

## Action Items

| Priority | Item | Details |
|----------|------|---------|
| **P0** | **Fix squeeze exit routing in bot.py** | 10s bar TW/BE exits in `on_bar_close_10s()` fire on squeeze trades before `_manage_exits()` can route them. Need to skip pattern exits when `t.setup_type == "squeeze"`, same as simulate.py does. |
| P1 | Scanner sim finds 0 stocks for today | Different volume computation from live scanner. Need investigation. |
| P2 | Entry slippage ($2.88 vs $2.80) | Expected with live execution, but worth monitoring. |

---

## Milestone

**First live squeeze trade ever taken.** The full pipeline worked: SqueezeDetector → SQ_PRIMED → ARMED → ENTRY SIGNAL → trade_manager.on_signal → Alpaca order → fill. The exit routing bug is the remaining gap.
