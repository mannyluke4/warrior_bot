# DIRECTIVE: P0 Fixes (April 1, 2026)

Three P0 items: two infrastructure bugs + one sim/live parity gap. All must ship before next trading day.

---

## Fix 1: Mac Mini Must Stay Awake and Logged In for IB Gateway

### Problem
IB Gateway is a Java GUI application — it requires an active display session to launch. The Mac Mini must be:
1. Powered on (not sleeping)
2. Screen active (not display-sleep)
3. User logged in with an active GUI session

On April 1, Manny booted the Mac Mini at 12:30 AM MT (2:30 AM ET), but IB Gateway appears to have restarted itself (daily reset) and failed to reconnect because the display session was no longer active. The bot didn't start. Manny didn't catch it until 6:30 AM MT (8:30 AM ET) — missing the entire premarket golden window.

On March 31, Manny woke up at 4:45 AM MT to manually log in and start the bot. It worked, but he shouldn't have to do this every day.

### Root Cause
This is NOT a timeout or retry issue in daily_run.sh. The script can't launch Gateway at all if macOS has put the display to sleep or if IB Gateway's daily auto-restart fails without an active screen session.

### Fix: Prevent macOS Sleep + Keep Display Session Alive

**Step 1: Disable all sleep via system settings (one-time)**
```bash
# Prevent system sleep entirely
sudo pmset -a sleep 0
sudo pmset -a disksleep 0

# Prevent display sleep (critical — Gateway needs the display session)
sudo pmset -a displaysleep 0

# Disable Power Nap and other sleep triggers
sudo pmset -a powernap 0
sudo pmset -a standby 0
sudo pmset -a autopoweroff 0

# Verify settings
pmset -g
```

**Step 2: Prevent screen lock**
System Settings → Lock Screen → set "Require password after screen saver begins or display is turned off" to **Never**. Or via command line:
```bash
defaults write com.apple.screensaver askForPassword -int 0
```

**Step 3: Keep the user session alive with caffeinate**
Add to the top of `daily_run.sh`, before the Gateway launch:
```bash
# Keep Mac awake for the entire trading session (4 AM - 12 PM ET = 8 hours)
caffeinate -dims -t 28800 &
CAFFEINATE_PID=$!
echo "caffeinate started (PID $CAFFEINATE_PID) — preventing sleep for 8 hours"
```
The `-dims` flags prevent display sleep (`-d`), idle sleep (`-i`), disk sleep (`-m`), and system sleep (`-s`).

**Step 4: Handle IB Gateway's daily auto-restart**
IB Gateway restarts itself daily (IBKR requirement). Add a post-restart check in daily_run.sh — after Gateway connects, monitor port 4002 in a background loop and log if it drops:
```bash
# Background watchdog: detect if Gateway drops and log it
(
    while true; do
        sleep 60
        if ! python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',$IBKR_PORT)); s.close()" 2>/dev/null; then
            echo "WARNING: Gateway port $IBKR_PORT dropped at $(date -u '+%Y-%m-%d %H:%M:%S UTC')" >> "$LOG_DIR/gateway_watchdog.log"
        fi
    done
) &
```

**Step 5: Add a health-check log line after successful start**
```bash
echo "HEALTH_OK: Bot connected at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
```

### IBC Auto-Restart Config
Check `~/ibc/config.ini` for these settings:
```ini
# IBC should auto-accept the daily restart
AcceptIncomingConnectionAction=accept
ExistingSessionDetectedAction=primary
```
If `ClosedownAt` is set, IBC will shut down Gateway at that time. Make sure it's either unset or set to a time AFTER market close (e.g., 17:00 ET).

### The retry loop from the original fix can stay as a belt-and-suspenders measure
The 2-attempt Gateway startup is still useful as a fallback if Gateway is slow to initialize even with the display active. But the PRIMARY fix is preventing macOS from sleeping in the first place.

### Regression
No regression impact — this is pure infrastructure, doesn't touch Python code.

---

## Fix 2: Databento Scanner Date Bug (live_scanner.py)

### Problem
On April 1, live_scanner.py crashed immediately on startup:
```
422 data_end_after_available_end
The dataset EQUS.SUMMARY has data available up to '2026-03-31 00:00:00+00:00'.
The `end` in the query ('2026-04-01 00:00:00+00:00') is after the available range.
```

### Root Cause
Line 299 of live_scanner.py:
```python
end_day = today_ts.date()  # Sets end to TODAY
```

Databento's EQUS.SUMMARY (daily OHLCV) dataset doesn't have the current day's data available until after market close. When the scanner starts at 4 AM, today's data doesn't exist yet.

### Fix (line 299 of live_scanner.py)
Change end_day to yesterday. We only need the previous close, not today's bar:

```python
# OLD:
end_day = today_ts.date()

# NEW:
end_day = (today_ts - pd.offsets.BusinessDay(1)).date()
```

That's it. One line.

### Why this works
The method is called `load_prev_close()` — it only needs historical data through yesterday. The 21-business-day window (line 298) fetches enough history for average daily volume calculation. Ending on the prior business day instead of today is actually more correct semantically.

### Edge case
On Monday mornings, `BusinessDay(1)` correctly gives Friday. On days after holidays, it correctly skips to the last trading day. The `pd.offsets.BusinessDay` handles US market holidays.

### Regression
No regression impact — this fix only affects the live scanner's data fetch. Backtests use different data paths.

---

## Verification
After deploying both fixes:
1. Run `daily_run.sh` manually and confirm Gateway connects
2. Run `python live_scanner.py` and confirm it loads prev_close without crashing
3. Verify the bot reaches "Bot running" state and starts receiving ticks

## Git
```
git pull
# apply fixes
git add daily_run.sh live_scanner.py
git commit -m "P0-infra: Gateway retry loop + Databento date bug fix

- daily_run.sh: 2-attempt Gateway startup with full kill+retry on failure
- live_scanner.py: end_day = today - 1 business day (EQUS.SUMMARY not available for current day)
- Both caused total bot failure on April 1

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push
```

---

## Fix 3: Port Candle-Based Exits to Live Bot (bot_ibkr.py)

### Problem
`simulate.py` generates candle exit signals (topping_wicky, bearish_engulfing, parabolic_exhaustion) on 10s and 1m bar closes. `bot_ibkr.py` has ZERO candle-based exits. The live bot is structurally dumber than the simulator — it rides the trailing stop all the way down instead of reading reversal patterns.

This is NOT a new feature. It's a parity fix. The sim has had these exits since inception and the V1 megatest results (+$19,832) INCLUDE them. The live bot is running without them.

### What Already Exists (don't reinvent)
- `candles.py` — `is_bearish_engulfing()`, `is_doji()`, `is_shooting_star()` (all correct, tested)
- `patterns.py` — `PatternDetector` class with `TOPPING_WICKY` detection (lines 339-356)
- `trade_manager.py` — `on_exit_signal()` method (lines 2821-2905) already handles:
  - `topping_wicky`, `bearish_engulfing`, `parabolic_exhaustion`
  - `l2_bearish`, `l2_ask_wall`
  - Halt suppression (lines 2836-2837)
  - Grace period logic (line 2839)
  - Profit gate suppression
- `simulate.py` — Reference implementation:
  - 10s bar pattern exits: lines 2231-2287
  - 1m bar pattern exits: lines 2539-2565
  - Grace period helpers: `_in_tw_grace()`, `_in_be_grace()`
  - Profit gate: `WB_TW_MIN_PROFIT_R`, `WB_BE_MIN_PROFIT_R`

### What's Missing in bot_ibkr.py
- No import of `candles` or `patterns` modules
- No `PatternDetector` instance per symbol
- No candle pattern analysis on bar close events
- No calls to `trade_manager.on_exit_signal()`
- `_squeeze_exit()` (lines 666-716) is purely mechanical: dollar cap, hard stop, trailing stop, 2R target

### Fix
1. Import candle detection:
   ```python
   from candles import is_bearish_engulfing
   from patterns import PatternDetector
   ```

2. In per-symbol state, instantiate a `PatternDetector`:
   ```python
   state.pattern_det = PatternDetector()
   ```

3. On 10s bar close, feed the bar to pattern detection and check for exits:
   ```python
   # In the 10s bar close handler:
   state.pattern_det.update(bar.open, bar.high, bar.low, bar.close, bar.volume)
   if "TOPPING_WICKY" in state.pattern_det.last_patterns:
       if not _in_tw_grace(time_str):
           trade_mgr.on_exit_signal(symbol, "topping_wicky")

   # Bearish engulfing check (current vs previous 10s bar):
   if prev_10s and is_bearish_engulfing(bar.open, bar.high, bar.low, bar.close,
                                         prev_10s.open, prev_10s.high, prev_10s.low, prev_10s.close):
       if not _in_be_grace(time_str):
           trade_mgr.on_exit_signal(symbol, "bearish_engulfing")
   ```

4. Port grace period and profit gate logic from simulate.py. Look at the exact conditions used there and replicate.

### Gate
`WB_SQ_CANDLE_EXITS_ENABLED=1` — ON by default. This matches sim behavior. Can be turned OFF to isolate impact.

### Regression
Run VERO and ROLR regression with `WB_SQ_CANDLE_EXITS_ENABLED=1`. Results should match existing V1 numbers since simulate.py already has these exits. If they DON'T match, the port has a bug.

### Git
```
git add bot_ibkr.py
git commit -m "P0: Port candle-based exits from sim to live bot

- Import candles/patterns modules into bot_ibkr.py
- Instantiate PatternDetector per symbol
- Generate topping_wicky and bearish_engulfing exit signals on 10s/1m bars
- Wire through trade_manager.on_exit_signal() (already handles these)
- Port grace period + profit gate logic from simulate.py
- Gated: WB_SQ_CANDLE_EXITS_ENABLED=1 (ON by default, parity with sim)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push
```

