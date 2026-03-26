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

Ran all 5 morning candidates (EEIQ, FCHL, NDLS, BTBD, FATN) through `simulate.py` for 2026-03-26 07:00-12:00 ET:

| Symbol | Ticks in Cache | Result | Notes |
|--------|---------------|--------|-------|
| EEIQ | 3,270 (11:44-11:47 ET only) | No trades | Only 3 min of tick data — main move/halt was ~10 AM ET, not captured |
| BTBD | 7,538 | No trades | Armed 3 times but never triggered (no level break) |
| FCHL | 479 | No trades | Insufficient tick data |
| NDLS | 55 | No trades | Insufficient tick data |
| FATN | 148 | No trades | Insufficient tick data |

**Why the backtest shows 0 trades:** The Databento tick cache for today is sparse — EEIQ's real action (the halt spike around 10 AM ET) wasn't captured. The tick cache only has a 3-minute window at 11:44 ET, well after the move. This is a **data coverage gap**, not a strategy failure.

**Why the live bot also took 0 trades:** The volume=0 bug (Issue 3) meant all 1-minute bars had zero volume. The squeeze detector requires `min_bar_vol=50,000` to prime — with volume=0, it could never arm. Even though the live bot was receiving real-time data from IBKR during EEIQ's move, the volume wasn't being passed to the bar builder.

**Bottom line:** Two independent problems — (1) live bot had the volume bug blocking detection, (2) backtest can't reproduce it because Databento didn't cache the ticks from the key timeframe. The volume=0 bug is now fixed. Future mornings will have the bot building bars with real volume from IBKR, and EEIQ-type setups will be detectable.

---

## Current State (as of 4:00 PM ET)

- Bot running dual-window schedule: morning 7-12 ET + evening 4-8 PM ET
- All 9 issues above are fixed and deployed
- Evening session started at 16:00 ET with 13 scanner candidates, 5 subscribed
- All orders are limit orders with `outsideRth=True`
- TWS connection stable, no competing sessions
