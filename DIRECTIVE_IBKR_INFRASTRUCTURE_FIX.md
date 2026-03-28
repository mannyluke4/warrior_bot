# DIRECTIVE: IBKR Infrastructure Fix — Gateway + Tick Data + Scanner Preservation

**Date:** 2026-03-27
**Author:** Cowork (Opus)
**For:** CC (Sonnet)
**Priority:** P0 — Monday morning must work
**Branch:** `v2-ibkr-migration`

---

## Context

March 27 forensic: Ross made +$20,869 on ONCO and ARTL. The bot made $0. Three compounding infrastructure failures killed the session:

1. **TWS autostart failed** — AppleEvent timeout after 36 retries, bot didn't start until manual intervention at 09:07 ET (100% of Ross's P&L was earned before 09:30 ET)
2. **Near-zero tick data** — Even after subscribing at 09:07, ONCO received 12 ticks and ARTL received 61 ticks across a 2+ hour session. The `on_ticker_update` callback essentially never fired
3. **Scanner results overwritten** — `scanner_results/2026-03-27.json` is empty `[]` because each scan overwrites the file, destroying evidence from previous checkpoints
4. **Evening f-string crash** — `ValueError: Invalid format specifier` on line 278 of `bot_ibkr.py` kills the entire tick→bar→detector pipeline for every bar close event

This has happened 4 consecutive mornings. The gap isn't strategy — the gap is infrastructure.

See: `cowork_reports/2026-03-27_onco_artl_forensic.md` for full analysis.

---

## Phase 1: Gateway Headless Switch (CRITICAL)

### Problem
`daily_run.sh` was already updated to use Gateway mode (`gatewaystartmacos.sh -inline`, port 4002), but the March 27 cron log shows it still tried port 7497 and used the TWS AppleEvent path. Either the machine hadn't pulled the latest code, or there's a code path mismatch.

### Tasks

1. **Verify `daily_run.sh` is actually using Gateway on the live machine**
   - Confirm the file at `~/warrior_bot_v2/daily_run.sh` uses `gatewaystartmacos.sh -inline` (not `twsstartmacos.sh`)
   - Confirm port check targets 4002 (not 7497)
   - Confirm `bot_ibkr.py` defaults to port 4002 (check `IBKR_PORT` env var or hardcoded default)

2. **Add explicit git pull at the TOP of daily_run.sh** (before anything else)
   - The March 27 cron log shows `git pull` happened but still ran stale code — verify the pull actually updates the working tree
   - Add a checksum or version echo after pull so the log proves which code version ran

3. **Kill pattern cleanup**
   - Current kill patterns in daily_run.sh: `java.*ibgateway`, `java.*IBGateway`, `java.*tws`, `java.*Jts`
   - Add `pkill -f "java.*IBC"` to catch IBC launcher processes
   - Add 2-second sleep after kills before starting Gateway

4. **Fallback: If Gateway fails to open port 4002 within 180s, log the failure clearly and exit**
   - Don't silently fall through to bot startup with no connection
   - The current `FATAL: TWS did not open port 7497` message should say Gateway/4002

### Verification
```bash
# Manually run daily_run.sh and confirm:
# 1. Log shows "Starting IB Gateway" (not TWS)
# 2. Port check targets 4002
# 3. Bot connects on first attempt
# 4. No AppleEvent errors in log
```

---

## Phase 2: Tick Data Drought Fix (CRITICAL)

### Problem
After subscribing via `reqMktData(contract, '', False, False)` at 09:07 ET, the bot received essentially zero ticks until 11:12 ET. The `on_ticker_update` callback wasn't firing. 12 ticks for ONCO and 61 for ARTL across a 2+ hour session is a 99.9% deficit.

Current subscription code (`bot_ibkr.py` ~line 171):
```python
state.ib.reqMktData(contract, '', False, False)
```

Current tick processing (`bot_ibkr.py` ~line 591-620):
```python
def on_ticker_update(self, tickers):
    for ticker in tickers:
        self._process_ticker(ticker)
```

No health checking, no tick counting, no resubscription logic.

### Tasks

1. **Add per-symbol tick counter and 60-second audit log**
   ```
   # Every 60 seconds in the heartbeat, log:
   "{symbol}: {tick_count} ticks in last 60s, last_price={price}, last_tick_time={time}"
   ```
   - Track `tick_counts: Dict[str, int]` on the bot state
   - Reset counts each heartbeat interval
   - This is the #1 diagnostic — we need to see tick flow in real time

2. **Add subscription health check with automatic resubscription**
   - After `reqMktData`, wait 10 seconds, then check if any ticks have arrived for that symbol
   - If zero ticks after 10s: log a WARNING, call `cancelMktData(contract)`, wait 2s, re-call `reqMktData`
   - Retry up to 3 times before logging CRITICAL and moving on
   - This catches the "subscribe succeeds but IBKR isn't actually streaming" failure mode

3. **Add competing session detection**
   - March 26 had Error 10197 (mobile app wiped subscriptions)
   - Log and handle Error 10197 explicitly: re-subscribe all active symbols immediately
   - On ANY `ib.errorEvent`, if the error code relates to market data (10197, 354, 2104, 2106, 2158), log the full error and trigger a re-check of all subscriptions

4. **Ensure single connection — no port conflicts**
   - At bot startup, verify that ONLY port 4002 is in use (not both 7497 and 4002)
   - Add a pre-flight check: `lsof -i :7497` and `lsof -i :4002` — if both are occupied, log CRITICAL and abort
   - The March 27 session had 3 manual restarts on two different ports — zombie connections may have confused IBKR's data routing

5. **Wire `pendingTickersEvent` as backup**
   - `ib_insync` has `ib.pendingTickersEvent` which fires when any ticker has pending updates
   - Currently only `on_ticker_update` is wired — add a secondary listener on `pendingTickersEvent` that logs if tickers are pending but `on_ticker_update` hasn't fired in 30+ seconds

### Verification
```bash
# Run bot with Gateway connected, subscribe to any active stock
# Verify in log:
# 1. "ONCO: 47 ticks in last 60s" (non-zero tick counts)
# 2. If 0 ticks: see resubscription attempts
# 3. No Error 10197 or competing session warnings
```

---

## Phase 3: Scanner Results Preservation

### Problem
`bot_ibkr.py` line ~658 saves scanner results with:
```python
json.dump(merged, f)
```
Each scan overwrites the file. On March 27, the final scan (which found 0 candidates) overwrote all previous results, leaving `scanner_results/2026-03-27.json` as `[]`. We lost all evidence of what the scanner found at 09:07, 09:12, and 09:20.

### Tasks

1. **Switch to append-mode scanner snapshots**
   - Instead of overwriting, load existing file first, then append new results with a timestamp:
   ```python
   # Pseudocode:
   existing = json.load(f) if file exists else []
   snapshot = {
       "timestamp": datetime.now(timezone.utc).isoformat(),
       "scan_time_et": current_et_time,
       "candidates": merged
   }
   existing.append(snapshot)
   json.dump(existing, f)
   ```
   - Each checkpoint gets its own timestamped entry
   - Empty scans still get recorded (so we can see "09:34 ET: 0 candidates")

2. **Add symbol tracking to scanner log**
   - When a symbol appears in one scan but not the next, log: `"ARTL dropped from scanner at 09:29 ET (was present at 09:20 ET)"`
   - This creates an audit trail for the "ARTL disappeared" scenario

### Verification
```bash
# After a morning session, scanner_results/YYYY-MM-DD.json should contain:
# - Multiple timestamped entries
# - Each entry shows what candidates were found at that checkpoint
# - Symbols that drop between scans are logged
```

---

## Phase 4: F-String Bug Fix

### Problem
`bot_ibkr.py` line 278 has a malformed f-string in the diagnostic bar logging:
```
ValueError: Invalid format specifier '.2f if vwap else 0:.2f' for object of type 'float'
```

This crashes the entire `on_ticker_update → on_trade → on_bar_close → on_bar_close_1m` pipeline. Every tick that triggers a bar close kills all processing for that tick. 424 occurrences in the evening log.

### Tasks

1. **Fix the f-string syntax**
   - Find the malformed format specifier on or near line 278
   - The pattern `{vwap:.2f if vwap else 0:.2f}` is invalid Python
   - Correct form: `{(vwap if vwap else 0):.2f}` or `{vwap:.2f}` with a None guard before the f-string

2. **Add try/except guard around ALL diagnostic logging**
   - Diagnostic prints should NEVER crash the trading pipeline
   - Wrap in `try/except Exception` with a one-line error log
   - The trading logic must be resilient to logging failures

### Verification
```bash
# Run bot, verify no ValueError in logs
# Verify bar close events process normally with diagnostic output
```

---

## Phase 5: Regression Testing

After all fixes, verify nothing broke:

### IBKR-Specific Tests
```bash
# 1. Gateway startup test (manual)
# - Run daily_run.sh
# - Confirm Gateway starts, port 4002 opens, bot connects
# - Confirm log shows tick counts within 60s of subscription

# 2. Tick health test (manual, during market hours or extended hours)
# - Subscribe to any liquid stock
# - Verify tick counts > 0 in heartbeat logs within 60s
# - Verify resubscription fires if you manually cancel data (optional stress test)
```

### Backtest Regression (MUST PASS)
```bash
cd ~/warrior_bot_v2
source ../warrior_bot/venv/bin/activate

# VERO regression (target: +$15,692)
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/

# ROLR regression (target: +$6,444)
WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```

These changes are infrastructure-only (no strategy logic changes), so regressions should pass unchanged. But verify anyway — butterfly effects are real.

---

## Success Criteria

| Metric | Before | After |
|--------|--------|-------|
| Gateway autostart | ❌ AppleEvent timeout 4 days in a row | ✅ Headless Gateway starts reliably |
| Time to first tick | Never (0 ticks for hours) | < 15 seconds after subscription |
| Tick count per symbol | 12 (ONCO), 61 (ARTL) over 2 hours | Thousands per hour for active stocks |
| Scanner evidence | Overwritten to `[]` | Timestamped snapshots preserved |
| Diagnostic logging | Crashes pipeline (ValueError) | Safely guarded, never crashes trading |
| VERO regression | +$15,692 | +$15,692 (unchanged) |
| ROLR regression | +$6,444 | +$6,444 (unchanged) |

---

## Priority Order

1. **Phase 4** (f-string fix) — 2 minutes, prevents evening crashes tonight
2. **Phase 1** (Gateway verification) — 10 minutes, ensures Monday autostart works
3. **Phase 2** (tick data fix) — 30 minutes, the deepest problem
4. **Phase 3** (scanner preservation) — 15 minutes, evidence trail
5. **Phase 5** (regression) — 5 minutes, safety net

**Monday morning target: Bot auto-starts via Gateway at 04:00 ET, receives ticks within 15 seconds of subscription, and generates its first SQ signal on whatever the market gives us.**
