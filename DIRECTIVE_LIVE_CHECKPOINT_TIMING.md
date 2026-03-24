# Directive: Live Bot Checkpoint & Scanner Timing Parity

**Priority**: HIGH — must complete before next trading day (bot starts at 4 AM ET)
**Risk**: LOW — config-only changes, no strategy or exit logic touched
**Regression**: Run VERO + ROLR after to confirm no side effects (these don't use bot.py, but good hygiene)

## Context

The scanner_sim.py checkpoint schedule was updated to 12 data-driven checkpoints with a 9:30 cutoff (commit `a0a7f02`), but bot.py's rescan thread and live_scanner.py's write timing were not updated. This means the live bot rescans at different times than the backtest expects, and keeps adding stocks in the negative EV zone (post-9:30).

## Task 1: Update bot.py rescan checkpoints

**File**: `bot.py`, line ~673-675

**Current** (old 30-min schedule):
```python
RESCAN_CHECKPOINTS_ET = [
    (7, 30), (8, 0), (8, 30), (9, 0), (9, 30), (10, 0), (10, 30),
]
```

**Replace with** (12 data-driven checkpoints matching scanner_sim.py):
```python
RESCAN_CHECKPOINTS_ET = [
    (7, 0), (7, 15), (7, 30), (7, 45),
    (8, 0), (8, 10), (8, 15), (8, 30), (8, 45),
    (9, 0), (9, 15), (9, 30),
]
```

Also update the comment on line ~670 and the docstring on line ~684 to say "12 data-driven checkpoints" instead of "30-minute checkpoint approach".

**Why**: Golden hour (08:00-08:30) has 71% WR and +$26,875 — needs dense 10-15 min coverage. Post-9:30 is negative EV (-$2,430, 25% WR) — the 10:00 and 10:30 checkpoints must go. The rescan thread already exits after the last checkpoint, so removing 10:00/10:30 automatically stops rescanning at 9:30.

## Task 2: Update live_scanner.py write interval and cutoff

**File**: `live_scanner.py`, in the `run()` method (line ~627 onwards)

### 2a: Change write interval from 5 minutes to 1 minute

Find the sleep/interval logic after 7:14 AM that writes every 5 minutes and change to every 1 minute. The current code looks like:
```python
# After 7:14, continue writing every 5 minutes until 11:00 AM
```
Change interval to 1 minute (60 seconds instead of 300).

### 2b: Add 9:30 new-symbol cutoff

After 9:30 AM ET, the scanner should still write the watchlist (existing symbols stay), but should NOT add new symbols. This prevents late additions in the negative EV window.

In `write_watchlist()` or in the main loop, add a check:
```python
cutoff_et = now_et.replace(hour=9, minute=30, second=0)
if now_et >= cutoff_et:
    # After 9:30 — only write existing symbols, don't add new ones
    # (filter new_symbols to only include previously-seen symbols)
```

The exact implementation depends on how `write_watchlist` tracks symbols, but the intent is: after 9:30, the file can be rewritten (updating scores/ranks), but no symbol that wasn't already in the watchlist gets added.

### 2c: Change end time from 11:00 AM to 9:30 AM

```python
# Stop at 11:00 AM ET
```
Change to stop at 9:30 AM ET. After the cutoff, no new writes are needed — the bot already has its symbols.

**Why**: 1-minute writes catch emerging movers faster (scanner currently has 5-min lag from detection to bot subscription). 9:30 cutoff prevents the bot from subscribing to stocks in the negative EV window.

## Task 3: Fix stock_filter.py MAX_FLOAT default (one-liner)

**File**: `stock_filter.py`

Find the `MAX_FLOAT` default (likely `10` or `10.0`) and change to `15` to match `.env`:
```python
MAX_FLOAT = float(os.getenv("WB_MAX_FLOAT", "15"))  # was "10"
```

This is cosmetic (`.env` overrides at runtime), but keeps the code honest if `.env` is missing.

## Task 4: Investigate ROLR disappearance from scanner_sim (BUG)

**Priority**: HIGH — ROLR is a regression stock (+$6,444 standalone, +$233 batch)

ROLR (2026-01-14) disappeared from the new checkpoint scanner results despite having 288% gap, 59x RVOL, 3.6M float. The old scanner found it at the 08:30 checkpoint with `precise_discovery: 08:18`.

**Root cause hypothesis**: The new checkpoint windows are narrower. The old 08:30 checkpoint had a 30-minute window (08:00-08:30). The new 08:30 checkpoint has a 15-minute window (08:15-08:30). ROLR news broke at 08:18 — within the new window — so it should still be caught. Possible causes:

1. ROLR halted before 08:30 and Alpaca returned no bars in the 08:15-08:30 window
2. The cumulative volume fetch (4AM→checkpoint) failed silently
3. API timing edge case with the narrower window boundaries

**Debug steps**:
```bash
# Run scanner for just this date with verbose output
python scanner_sim.py 2026-01-14 2>&1 | tee /tmp/rolr_debug.txt

# Search output for ROLR mentions
grep -i rolr /tmp/rolr_debug.txt

# If ROLR doesn't appear in rescan output, add temp debug print:
# In find_emerging_movers(), after line 591 (gap_pct calc), add:
#   if sym == 'ROLR': print(f"  DEBUG ROLR: gap={gap_pct:.1f}% price={latest_price} window={label}")
#
# In resolve_precise_discovery(), after bar fetching, add:
#   if sym == 'ROLR': print(f"  DEBUG ROLR precise: {len(bar_list)} bars, cum_vol={cum_vol}")
```

**If ROLR is confirmed missing due to narrow windows**: The fix is to change `find_emerging_movers` to use cumulative windows (4AM→checkpoint) instead of incremental windows (prev_checkpoint→checkpoint) for the gap check. This ensures a stock that gaps mid-session is always caught regardless of which specific 10-15 minute slice its first bar falls in. The volume is already computed cumulatively (lines 764-788) — only the gap price check uses the narrow window.

**Scope**: This likely affects other mid-session gap stocks too (any stock whose first bars fall in a narrow halt window). Could explain some of the other pre-9:30 removals (NCEL, AIFF, SLXN).

## Verification

1. `grep -n "RESCAN_CHECKPOINTS" bot.py` — confirm 12 checkpoints, last is (9, 30)
2. `grep -n "11:00\|1[01]:00\|10:30\|interval\|sleep" live_scanner.py` — confirm no 11:00 references, 1-min interval
3. `grep -n "MAX_FLOAT" stock_filter.py` — confirm default is 15
4. ROLR appears in `scanner_results/2026-01-14.json` after fix
5. Run regression:
   ```bash
   WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
   WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
   ```
   Expected: VERO +$18,583, ROLR +$6,444
