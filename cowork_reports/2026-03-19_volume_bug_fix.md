# CC Report: P0 Volume Bug Fix — stock_filter.py
## Date: 2026-03-19
## Machine: Mac Mini

### What Was Done
Fixed critical bug in `stock_filter.py` line 79 where RVOL was calculated from `snap.latest_trade.size` (single trade lot, ~100-500 shares) instead of `snap.daily_bar.volume` (cumulative daily volume, ~millions). This caused RVOL to always be ~0.0004x, blocking every stock from the 2.0x threshold. The live bot watched nothing for 7 hours on 2026-03-19.

### The Fix
```python
# BEFORE (broken):
volume = int(snap.latest_trade.size) if snap.latest_trade else 0

# AFTER (fixed):
if snap.daily_bar and snap.daily_bar.volume:
    volume = int(snap.daily_bar.volume)
elif snap.minute_bar and snap.minute_bar.volume:
    volume = int(snap.minute_bar.volume)
else:
    volume = int(snap.latest_trade.size) if snap.latest_trade else 0
```

### Verification Results
```
AAPL: price=$249.30, vol=34,715,531, avg_vol=39,317,754, rvol=0.88x, gap=-0.3%
  Passes: False  Reasons: ['price $249.30 > $20.00', 'gap -0.3% < 10.0%', 'rel_vol 0.88x < 2.00x', 'float 14656.2M > 10.0M']
```
Volume is now 34.7M (daily cumulative) — was ~200 (single trade). RVOL 0.88x is sane for AAPL on a normal day.

### Infrastructure Checks
| Check | Result |
|-------|--------|
| Cron job | Active: `0 2 * * 1-5` (4 AM ET, Mon-Fri) |
| Git push | Working |
| Alpaca API | OK — SPY last $660.82 |
| Databento | Not installed (not needed for current scanner path) |
| Regression VERO | +$18,583 (pass) |
| Regression ROLR | +$6,444 (pass) |

### Key Observations
1. Bug was isolated to `stock_filter.py` (live bot only) — `simulate.py` and `scanner_sim.py` are unaffected.
2. The fix uses `daily_bar.volume` as primary, `minute_bar.volume` as fallback, `latest_trade.size` as last resort.
3. Squeeze is NOT enabled in .env — tomorrow trades MP-only (correct per validation status).
4. TWS/IBC auto-login worked today (PID 54155), the `AppleEvent timed out` is cosmetic Homebrew noise.

### Files Changed
- `stock_filter.py` — line 79 volume calculation fix
- `cowork_reports/2026-03-19_volume_bug_fix.md` (this file)
