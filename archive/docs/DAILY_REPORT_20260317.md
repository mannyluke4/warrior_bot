# Daily Report — 2026-03-17 (First Automated Run)

## Summary
First fully automated run of Warrior Bot on the Mac Mini. The automation pipeline (wake → cron → TWS → bot) worked end-to-end, but two issues prevented meaningful trading: the scanner ran too early and the Mac fell asleep mid-session.

## What Worked
- **pmset wake** fired at 1:55 AM MT, Mac booted
- **Cron** triggered `daily_run.sh` at 2:00 AM MT
- **git pull** pulled latest code successfully
- **TWS/IBC** started and logged in (PID 26435)
- **Bot** started at 2:01 AM MT (4:01 AM ET), connected to Alpaca feed
- **Dynamic scanner** ran, found 500 price-filtered symbols
- **StockFilter** ran Ross Cameron criteria on all 500
- Bot ran heartbeats continuously from 4:04 AM to 10:47 AM ET (~7 hours)
- **EXIT trap** fired at 9:00 AM MT, committed and pushed logs automatically

## What Didn't Work

### 1. Scanner Timing (Only 1 stock passed filters)
- Scanner ran at **4:04 AM ET** — deep premarket, almost nothing is gapping yet
- Of 500 price-filtered symbols, only **CRAQU** (a SPAC unit) passed gap/volume filters
- CRAQU had no historical bars → no seed data → effectively dead
- Result: `watch=0` all day, no trades

**Root cause:** `MarketScanner.scan_market()` runs once at startup. At 4 AM, there are no real gap-ups yet. The backtest's `scanner_sim.py` re-scans at 30-minute checkpoints (8:00, 8:30, 9:00, etc.) to catch emerging movers — the live bot didn't have this.

### 2. Mac Fell Asleep Mid-Session
- The `sleep $WAIT_SECS` command in daily_run.sh does not prevent macOS from sleeping
- Mac went to sleep sometime during the session
- Bot process was suspended (still technically running but frozen)
- When the Mac was manually woken, the bot was 5 minutes from scheduled shutdown

**Root cause:** No `caffeinate` was keeping the Mac awake during the trading session.

## Fixes Applied

### Fix 1: `caffeinate` in daily_run.sh
```bash
caffeinate -dims -w $$ &
```
- `-d` prevent display sleep
- `-i` prevent idle sleep
- `-m` prevent disk sleep
- `-s` prevent system sleep
- `-w $$` tied to script PID — dies when script exits
- Killed in cleanup trap

### Fix 2: Periodic Re-Scan Thread in bot.py
Added `rescan_thread()` that re-runs `MarketScanner` + `StockFilter` at 30-minute checkpoints matching the backtest:

| Checkpoint (ET) | Purpose |
|-----------------|---------|
| 7:30 | Early premarket movers |
| 8:00 | Mid premarket |
| 8:30 | Late premarket |
| 9:00 | Pre-open |
| 9:30 | Market open — biggest gap moves visible |
| 10:00 | Late morning movers |
| 10:30 | Final scan |

New symbols from re-scans are injected into the existing `watchlist_thread` via a shared `rescan_symbols` set. The watchlist thread automatically subscribes, seeds history, and creates detectors for new symbols.

## Config (Unchanged)
```
WB_MODE=PAPER
WB_ARM_TRADING=1
WB_ENABLE_DYNAMIC_SCANNER=1
WB_DATA_FEED=alpaca
WB_MAX_NOTIONAL=60000
```

## Tomorrow's Expected Flow
| Time (MT) | Time (ET) | Event |
|-----------|-----------|-------|
| 1:55 AM | 3:55 AM | Mac wakes (pmset) |
| 2:00 AM | 4:00 AM | Cron fires, caffeinate starts, TWS boots |
| 2:01 AM | 4:01 AM | Bot starts, initial scan (may find little) |
| 5:30 AM | 7:30 AM | First re-scan checkpoint — premarket movers appear |
| 6:00-7:30 AM | 8:00-9:30 AM | Re-scans every 30 min, watchlist grows |
| 7:30 AM | 9:30 AM | Market open — peak activity |
| 9:00 AM | 11:00 AM | Shutdown, logs pushed, Mac sleeps |

## Files Changed
- `daily_run.sh` — added caffeinate + cleanup
- `bot.py` — added `rescan_thread()`, updated `watchlist_thread()` to include rescan symbols
