# Directive: Pre-Trading Readiness Verification — 2026-03-20

## Priority: P0 — BLOCKING for tomorrow's session
## Owner: CC
## Created: 2026-03-19 (Cowork)

---

## Context

Today (2026-03-19) the live bot ran the entire session and **took zero trades**. Not because there
were no setups — CHNR gapped +70% with 380x RVOL and Ross Cameron made $5,200 on it — but because
**zero stocks passed the scanner filter at every single rescan** (4:04 AM through 10:30 AM ET).

Root cause identified: **critical bug in `stock_filter.py` line 79**.

---

## P0 BUG FIX: stock_filter.py Volume Calculation

### The Bug

```python
# stock_filter.py, line 79 (CURRENT — BROKEN)
volume = int(snap.latest_trade.size) if snap.latest_trade else 0
```

`snap.latest_trade.size` is the **lot size of the single most recent trade** (e.g., 100-500 shares).
It is NOT today's cumulative volume. So relative volume is calculated as:

```
rel_volume = 200 / 500,000 = 0.0004x   ← always fails the 2.0x threshold
```

This means **no stock can ever pass the RVOL filter**, regardless of how active it is.

### The Fix

Alpaca's snapshot includes `daily_bar` which has the current day's cumulative volume:

```python
# stock_filter.py, line 79 (FIXED)
# Use today's cumulative daily bar volume, not a single trade's lot size
if snap.daily_bar and snap.daily_bar.volume:
    volume = int(snap.daily_bar.volume)
elif snap.minute_bar and snap.minute_bar.volume:
    volume = int(snap.minute_bar.volume)
else:
    volume = int(snap.latest_trade.size) if snap.latest_trade else 0
```

### Verification

After the fix, run a quick sanity check:

```bash
cd ~/warrior_bot
source venv/bin/activate
python3 -c "
from stock_filter import StockFilter
import os
sf = StockFilter(os.getenv('APCA_API_KEY_ID'), os.getenv('APCA_API_SECRET_KEY'))
# Test with a stock that should have volume
info = sf.get_stock_info('AAPL')
if info:
    print(f'AAPL: price={info.price}, vol={info.volume:,}, avg_vol={info.avg_volume:,.0f}, rvol={info.rel_volume:.2f}x, gap={info.gap_pct:.1f}%')
    passes, reasons = sf.passes_filters(info)
    print(f'  Passes: {passes}  Reasons: {reasons}')
else:
    print('No data for AAPL')
"
```

Expected: AAPL volume should be in the millions (daily cumulative), not hundreds (single trade).
AAPL won't pass our gap filter (it's a mega-cap), but the RVOL should now be a sane number (0.5-2.0x).

### Evidence This Was the Problem

From today's daily log (`logs/2026-03-19_daily.log`):
- 8 rescans (4:04 AM, 7:30, 8:00, 8:30, 9:00, 9:30, 10:00, 10:30 ET)
- EVERY scan: "Passed: 0 stocks, Filtered: 500 stocks"
- CHNR had gap=+70.5%, RVOL=380.9x, float=0.52M — should have passed easily
- The bot heartbeated `watch=0 open=0` for 7 straight hours

---

## Secondary Checks (after P0 fix)

### Check 1: Cron Job Is Firing

Verify cron is scheduled for tomorrow (Friday):

```bash
crontab -l | grep daily_run
```

Expected: `0 2 * * 1-5 /Users/duffy/warrior_bot/daily_run.sh` (or similar, 2:00 AM MT = 4:00 AM ET)

If missing, add it:
```bash
(crontab -l 2>/dev/null; echo "0 2 * * 1-5 /Users/duffy/warrior_bot/daily_run.sh >> /Users/duffy/warrior_bot/logs/cron_\$(date +\%Y-\%m-\%d).log 2>&1") | crontab -
```

### Check 2: Git Push Succeeds

Today's log shows `WARN: git push failed` at shutdown. Verify push works:

```bash
cd ~/warrior_bot
git push origin v6-dynamic-sizing
```

If auth is stale, re-auth:
```bash
gh auth status
gh auth login   # if needed
```

### Check 3: TWS/IBC Auto-Login

Today's log shows TWS started successfully (line 7-8: `TWS started (IBC PID: 54155)`).
Verify it can still auto-login:

```bash
# Check IBC config exists
ls -la ~/ibc/twsstartmacos.sh
cat ~/ibc/config.ini | head -5
```

The `AppleEvent timed out` error (line 11 of cron log) is cosmetic Homebrew noise — not a problem.

### Check 4: Alpaca API Keys Valid

```bash
cd ~/warrior_bot
source venv/bin/activate
python3 -c "
from alpaca.data.historical import StockHistoricalDataClient
import os
from dotenv import load_dotenv
load_dotenv()
client = StockHistoricalDataClient(os.getenv('APCA_API_KEY_ID'), os.getenv('APCA_API_SECRET_KEY'))
from alpaca.data.requests import StockSnapshotRequest
snap = client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=['SPY']))
spy = snap.get('SPY')
print(f'API OK — SPY last: \${spy.latest_trade.price:.2f}')
"
```

### Check 5: .env Squeeze Config (NOT YET — informational only)

Squeeze V2 is **NOT enabled in .env** — this is correct. Squeeze should NOT go live until the
55-day YTD backtest validates it. Current .env has no `WB_SQUEEZE_ENABLED` var, which defaults
to 0 (disabled). Do NOT add squeeze vars to .env yet.

Tomorrow's live session should trade with **MP-only strategy** (the validated configuration).

### Check 6: Databento API Key (for live_scanner.py)

The .env has `DATABENTO_API_KEY` set. If the live scanner is used instead of market_scanner,
verify it connects:

```bash
python3 -c "
import databento as db
import os
from dotenv import load_dotenv
load_dotenv()
client = db.Historical(os.getenv('DATABENTO_API_KEY'))
print('Databento API key valid')
"
```

### Check 7: Regression After Bug Fix

After fixing the volume bug, run regression to make sure nothing else changed:

```bash
cd ~/warrior_bot
source venv/bin/activate

# These should still produce the same results (they don't use stock_filter.py)
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

The regression test is a safety net — `stock_filter.py` is only used by `bot.py` (live scanner),
not by `simulate.py`. So the fix should be isolated. But run regression anyway.

---

## Execution Order

1. **Fix stock_filter.py line 79** (P0 — do this first)
2. **Run the volume sanity check** (verify the fix works)
3. **Run regression** (VERO +$18,583, ROLR +$6,444)
4. **Verify cron, git push, API keys** (Checks 1-4)
5. **Commit and push**:

```bash
git add stock_filter.py
git commit -m "Fix P0: stock_filter volume using latest_trade.size instead of daily_bar.volume

The scanner used snap.latest_trade.size (single trade lot, ~100-500 shares)
instead of snap.daily_bar.volume (cumulative daily volume, ~millions).
This caused rel_volume to always be ~0.0004x, so the 2.0x RVOL threshold
blocked every stock. Result: bot watched nothing for 7 hours on 2026-03-19
while CHNR (gap +70%, RVOL 380x) traded perfectly for Ross.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin v6-dynamic-sizing
```

6. **Write recap** to `cowork_reports/2026-03-19_volume_bug_fix.md`

---

## What Success Looks Like

After the fix, tomorrow's 4:04 AM scan should show something like:

```
📊 Filter Results:
   ✅ Passed: 3-8 stocks
   ❌ Filtered: 492-497 stocks

🎯 Top Candidates (by rank):
   XYZZ: $4.50 gap=+45.2% vol=12.3x float=2.1M rank=68.4
   ABCD: $7.80 gap=+22.1% vol=5.7x  float=4.5M rank=52.1
```

And heartbeats should show `watch=3` (or whatever passes) instead of `watch=0`.

---

## Notes

- The `market_scanner.py` module file appears to have been moved to `archive/scripts/` but the
  `.pyc` in `__pycache__/` is still being loaded. This works but is fragile. Consider restoring
  `market_scanner.py` to the top-level directory if it's still needed by bot.py.
- The live_scanner.py (Databento streaming) is a separate system from the market_scanner
  (Alpaca REST polling). The bot currently uses market_scanner for discovery + stock_filter for
  qualification. The live_scanner writes watchlist files but bot.py only reads them in manual mode.
- Today's `daily_run.sh` ran cleanly (cron fired at 2:00 AM MT, TWS started, bot started).
  The ONLY issue was the volume bug preventing any stock from passing filters.

---

*Directive created by Cowork — 2026-03-19*
