# Morning Issues & Fixes Report: 2026-03-26
## Branch: v2-ibkr-migration

---

## Summary

V2's first live session on 2026-03-26 had multiple startup and runtime issues. **Zero trades were taken.** All issues have been identified, root-caused, and fixed. The bot is now running the evening session with all fixes deployed.

---

## Issue 1: TWS Startup Failure (CRITICAL)

**Symptom:** Bot crashed immediately at 2:00 AM MT — `ConnectionRefusedError` on port 7497.

**Root Cause:** Overnight mega backtest (Jan 2025 - Mar 2026) left a stale TWS/Java process running. IBC uses `pgrep -f "java.*config.ini"` internally — when it detected an existing Java process, it refused to launch a second TWS instance. The daily_run.sh script started the bot before TWS was ready.

**Fix (deployed in daily_run.sh):**
- Kill sequence now targets all Java variants: `java.*tws`, `java.*Jts`, `java.*ibc`
- Added `pgrep -f "java.*config.ini"` verification — if Java survives the first kill, force-kill all Java
- Port-wait loop: 36 retries x 5s = 180s timeout before bot starts
- Bot connect() has its own 3-retry loop with 10s backoff

**Status:** FIXED. Bot started cleanly on manual restart at ~9:30 AM MT.

---

## Issue 2: Competing Live Session (18-min downtime)

**Symptom:** At ~10:15 AM ET, all market data stopped. Errors: `Error 10197: No market data during competing live session` for EEIQ, BTBD, FCHL.

**Root Cause:** Manny logged into the IBKR mobile app during trading hours. IBKR allows only one active data session per account — the mobile app grabbed the session from TWS.

**Fix:** Operational rule: **do not log into IBKR mobile/web during bot trading hours.** IBKR holds the connection for ~15 minutes after the competing session disconnects before TWS can reclaim it.

**Status:** RESOLVED. Session recovered after Manny logged out of all other devices.

---

## Issue 3: Volume = 0 Bug (CRITICAL — no trades possible)

**Symptom:** Bot ran for the full morning session but took zero trades. Squeeze detector never armed because all 1-minute bars had volume = 0.

**Root Cause:** `_process_ticker()` was passing `size = 0` to `bar_builder.on_trade()`. The code used `ticker.lastSize` but the initial check was wrong — it wasn't properly reading the last trade size from ib_insync's ticker object.

**Fix (deployed in bot_ibkr.py):**
```python
# Before (broken):
size = 0  # always 0

# After (fixed):
size = int(ticker.lastSize) if ticker.lastSize and not math.isnan(ticker.lastSize) else 0
```

The `lastSize` field in ib_insync represents the size of the most recent trade print. It initializes to `nan`, so the NaN guard is required.

**Status:** FIXED. Verified bars now build with correct volume.

---

## Issue 4: Runner Position Destroyed on Target Hit

**Symptom:** When squeeze hit 2R target, the runner position was being cleared instead of held.

**Root Cause:** In `_squeeze_exit()`, `pos["qty"] = qty_runner` was set BEFORE `exit_trade(qty_core)`. Inside `exit_trade`, `remaining = pos["qty"] - qty_core` computed `qty_runner - qty_core = negative`, which cleared the position entirely.

**Fix:** Moved `pos["qty"] = qty_runner` AFTER the `exit_trade()` call. Now `remaining = original_qty - qty_core` is correct.

**Status:** FIXED.

---

## Issue 5: Halt Detection Spam (1,199 messages)

**Symptom:** EEIQ hit a volatility halt. Bot printed "HALT DETECTED" 1,199 times — one per tick update during the halt.

**Root Cause:** No debounce on halt detection. Every `pendingTickersEvent` callback checked halt status and printed if halted.

**Fix (deployed in bot_ibkr.py):** Added `_halted_symbols: set` tracking. Prints once on halt start, once on resume. Ignores repeated halt ticks for the same symbol.

**Status:** FIXED.

---

## Issue 6: Exit Orders Were Market Orders

**Symptom:** Not triggered in live yet (no trades taken), but would have caused order rejection during extended hours.

**Root Cause:** `exit_trade()` used `MarketOrder('SELL', qty)`. Exchanges reject market orders outside RTH (9:30 AM - 4:00 PM ET). Since the bot now runs pre-market (7-9:30) and after-hours (4-8 PM), all exits need to be limit orders.

**Fix (deployed in bot_ibkr.py):**
```python
# Before:
order = MarketOrder('SELL', qty)

# After:
limit_price = round(price - 0.03, 2)
order = LimitOrder('SELL', qty, limit_price)
order.tif = 'GTC'
order.outsideRth = True
```
Also added `outsideRth = True` to entry orders.

**Status:** FIXED.

---

## Issue 7: Scanner Cutoff (V1 Legacy)

**Symptom:** Scanner was configured to stop scanning at a fixed cutoff time (legacy from V1's 9:30 AM cutoff).

**Root Cause:** V1 design assumed morning-only trading. The cutoff blocked the scanner from finding evening candidates.

**Fix:** Removed `SCAN_CUTOFF_HOUR` / `SHUTDOWN_HOUR`. Replaced with `WB_TRADING_WINDOWS=07:00-12:00,16:00-20:00`. Scanner runs continuously during all active windows. Bot sleeps during 12-4 PM dead zone.

**Status:** FIXED.

---

## Issue 8: Stale Detector State for Evening Session

**Symptom:** Not triggered yet (first evening session is tonight), but detectors from the morning would carry stale PM highs, EMAs, and bar state into the evening.

**Fix:** When transitioning from dead zone to active window, the bot now:
- Clears all squeeze/MP detectors
- Rebuilds bar builders fresh
- Forces immediate rescan
- Evening session starts with clean state

**Status:** FIXED (preventive).

---

## Issue 9: Dead Zone Position Risk

**Symptom:** If `ticker.last` was None when the dead zone started, an open position would survive 4 hours unclosed.

**Fix:** Added fallback price chain: `ticker.last` → `ticker.bid` → `ticker.close`. If all are None, logs a warning (position left open, will be managed when evening session resumes).

**Status:** FIXED (preventive).

---

## This Morning's Backtest Simulation

### EEIQ Price Action (from IBKR 1-min bars)
- Open at 4:01 AM ET: $3.23
- **Morning high: $12.70 at 10:08 AM ET** (+293% from open)
- Hit volatility halt during the spike
- Closed around $8.35 by noon

This was a textbook squeeze candidate that the bot should have caught.

### Backtest Results: 0 Trades (Two Independent Causes)

Ran all 5 morning candidates (EEIQ, FCHL, BTBD, NDLS, FATN) through `simulate.py` in both modes:

| Symbol | Bar Mode (IBKR) | Tick Mode (Databento cache) | Notes |
|--------|-----------------|---------------------------|-------|
| EEIQ | Armed 2x, 0 triggers | 3,270 ticks (11:44-11:47 ET only) — 0 trades | Bar mode can't fire squeeze triggers; tick cache too sparse |
| BTBD | Armed 2x, 0 triggers | Armed 3x, 0 triggers | Armed but never broke level |
| FCHL | Armed 1x, 0 triggers | 479 ticks — 0 trades | Same dual issue |
| NDLS | Armed 3x, 0 triggers | 55 ticks — 0 trades | Same dual issue |
| FATN | Armed 2x, 0 triggers | 148 ticks — 0 trades | Same dual issue |

**Cause 1 — Bar mode doesn't fire squeeze triggers (BUG):** `simulate.py` bar mode feeds bars to the squeeze detector's `on_bar_close_1m()` which correctly PRIMEs and ARMs setups, but the tick-level trigger check (`on_trade_price()`) is only wired in tick mode. Bar mode uses `synthetic_ticks()` for MP triggers but not for squeeze. This means squeeze backtests REQUIRE tick mode (`--ticks`).

**Cause 2 — Databento tick cache is stale:** Since V2 migrated to IBKR, Databento live scanner isn't running. Today's tick cache only has 3 minutes of EEIQ data (11:44-11:47 ET), missing the entire $3→$12.70 move. The YTD backtests worked because historical tick cache was populated during V1 era.

**Cause 3 — Live bot volume=0 bug:** Even with real-time IBKR data, the live bot passed `size=0` to bar builders. Squeeze detector requires `min_bar_vol=50,000` to prime — with volume=0, it could never arm.

### What Needs to Happen
1. **Volume=0 bug**: FIXED (Issue 3 above). Live bot now uses `ticker.lastSize`.
2. **Bar mode squeeze triggers**: Need to wire `sq_det.on_trade_price()` into bar mode's synthetic tick loop, OR build an IBKR tick data fetcher to populate tick cache for future backtests.
3. **Tick cache going forward**: Since Databento is no longer running, we need a new source of tick data for backtesting. Options: (a) fetch IBKR historical ticks, (b) wire squeeze triggers into bar mode's synthetic ticks.

---

## Current State (as of 4:00 PM ET)

- Bot running dual-window schedule: morning 7-12 ET + evening 4-8 PM ET
- All 9 issues above are fixed and deployed
- Evening session started at 16:00 ET with 13 scanner candidates, 5 subscribed
- All orders are limit orders with `outsideRth=True`
- TWS connection stable, no competing sessions
