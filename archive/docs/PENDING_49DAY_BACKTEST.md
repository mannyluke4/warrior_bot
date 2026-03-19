# Pending: 49-Day Full Backtest with All 5 Fixes

## Status: BLOCKED — Missing Tick Cache on Mac Mini

## What's Needed
Run `run_ytd_v2_backtest.py` with all 5 fixes enabled, starting equity $30,000. Previous baseline: +$7,580 (+25.3%). Expected: significantly higher — VERO alone adds +$9,417, ROLR adds +$3,202.

## Why It's Blocked
The 49-day batch runner requires the tick cache for deterministic replay:
- **Location on MacBook Pro**: `~/warrior_bot/tick_cache/`
- **Size**: ~202 MB, 240 stock/date pairs, 33.7M ticks
- **Format**: Local files (not in git — too large)

The Mac Mini does not have this cache. Running without it would:
1. Fetch all 33.7M ticks from Alpaca API (hours, rate-limited)
2. Produce non-deterministic results (API data may differ slightly from cached data)
3. Not be comparable to the MacBook Pro's baseline numbers

## How to Fix

### Option A: Copy tick cache from MacBook Pro (Recommended)
```bash
# On MacBook Pro:
rsync -avz ~/warrior_bot/tick_cache/ duffy@<mac-mini-ip>:~/warrior_bot/tick_cache/

# Or via external drive / AirDrop:
# Copy ~/warrior_bot/tick_cache/ folder to Mac Mini at same path
```

### Option B: Run on MacBook Pro instead
Have MacBook Pro CC run the full 49-day backtest with all fixes enabled. It already has the tick cache and can produce deterministic results.

**TARGET**: 🖥️ MacBook Pro CC
```bash
cd ~/warrior_bot
git pull origin v6-dynamic-sizing
# Sync .env with all 5 fixes enabled (see ENV_CHANGES_FOR_MAC_MINI.md)
python run_ytd_v2_backtest.py --tick-cache tick_cache/
```

### Option C: Generate tick cache on Mac Mini (Slow)
```bash
# This would download all ticks from Alpaca — takes several hours
python run_ytd_v2_backtest.py --ticks
# Ticks would be cached locally for future runs
```

## What We Know So Far (Standalone Results)
| Stock | Date | Previous | All 5 Fixes | Delta |
|-------|------|----------|-------------|-------|
| VERO | 01-16 | +$9,166 | **+$18,583** | +$9,417 |
| ROLR | 01-14 | +$3,242 | **+$6,444** | +$3,202 |
| LUNL | 03-17 | -$821 | **+$464** | +$1,285 |

These 3 stocks alone add +$13,904 to the baseline. The full 49-day run will also show how fixes affect the other 25+ trades.

## Estimated 49-Day Result
Previous baseline: +$7,580 (28 trades, 36% win rate, $30K starting equity)
Conservative estimate with all 5 fixes: **+$20,000+** (VERO and ROLR improvements alone account for +$12,619)

---

*Report created: 2026-03-18 | Mac Mini CC | Awaiting tick cache transfer or MacBook Pro CC execution*
