# Live Bot Reliability Audit — 2026-03-21

**Scope:** All live bot components (bot.py, market_scanner.py, trade_manager.py, data_feed.py, live_scanner.py, stock_filter.py, daily_run.sh, logger.py, session_manager.py). Excludes simulation/backtest pipeline.

**Context:** The live bot missed every trading day the week of March 17-20, 2026. This audit identifies every failure point found in the code and logs.

---

## Executive Summary

The bot had **four different failure modes** across four trading days this week. The root causes range from a missing file import crash (Friday) to a silent "zero candidates" scenario that ran the bot all day watching nothing (Mon/Tue/Thu). The architecture has no watchdog, no health checks, and no alerting, meaning every failure was discovered hours later by manual inspection.

**Critical findings: 8 | Medium findings: 11 | Low findings: 6**

---

## THIS WEEK'S FAILURES (Root Cause Analysis)

### Day 1: Monday 3/17 — Scanner returned 1 stock (CRAQU), essentially idle all day
- **What happened:** Dynamic scanner found 10,103 symbols → price pre-filter passed 3,241 → limit to 500 → stock_filter.py filtered 499 of 500 out. Only CRAQU passed (a SPAC unit, likely not even tradable). Bot ran 5 hours watching 1 illiquid symbol.
- **Root cause:** The MarketScanner pre-filter uses `set(list(passing_symbols)[:500])` — this takes an *arbitrary* 500 from 3,241. Since Python sets are unordered, this is essentially random. The 500 symbols sent to the expensive stock_filter step are random stocks in the $2-$20 range, NOT the most active or most gapping ones.
- **Severity:** CRITICAL — this is why the bot is useless most days
- **Could have caused this week's missed days:** YES — this is the primary cause for Mon/Tue/Thu

### Day 2: Tuesday 3/18 — 0 stocks passed filters, fallback loaded 500 random symbols
- **What happened:** Same random-500 issue. Zero passed filters. But the `filter_watchlist` fallback returned the *raw unfiltered* set of 500 random symbols. Bot subscribed to all 500, got data, but no stock_info cache was populated (0 symbols cached). Without stock_info, the quality gate/pillar gates have no gap_pct/rvol data → all signals would be allowed but the symbols are garbage.
- **Root cause:** Same scanner randomness + the fallback behavior (line 153 of bot.py returns `symbols` unfiltered when filtering fails) means the bot ends up watching 500 random $2-$20 stocks with zero fundamental data.
- **Severity:** CRITICAL
- **Could have caused this week's missed days:** YES

### Day 3: Thursday 3/19 — 0 stocks passed filters, empty watchlist, bot idle all day
- **What happened:** Same scanner randomness. Zero passed filters. But this time the fallback path returned an empty set (not the unfiltered fallback). Bot ran from 4:04 AM to shutdown with `watch=0` symbols the entire session. Heartbeat shows 0 symbols continuously.
- **Root cause:** The `filter_watchlist` function in bot.py returns `set()` when no stocks pass (line 128-129), and the rescan thread found 0 new symbols too. The bot sat completely idle for the entire trading session.
- **Severity:** CRITICAL
- **Could have caused this week's missed days:** YES — entire session wasted

### Day 4: Friday 3/20 — Import crash (ModuleNotFoundError: market_scanner)
- **What happened:** `from market_scanner import MarketScanner` failed with `ModuleNotFoundError`. Bot crashed immediately at startup. The cron script didn't detect the crash (it just `sleep`s until 9 AM MT regardless).
- **Root cause:** market_scanner.py was apparently moved to archive/ at some point, or the working directory was wrong. The `python3 bot.py` command runs in `~/warrior_bot` but the cwd may not have been set correctly after the `cd ~/warrior_bot` in the cron script.
- **Manual fix applied:** The file was restored and a manual run was started at 11:40 AM ET (too late for most trading). Only found ARTL and RDGT.
- **Severity:** CRITICAL
- **Could have caused this week's missed days:** YES — Friday was a total loss

---

## FINDING 1: MarketScanner Pre-Filter Selects Random Symbols (Not Best Candidates)

**File:** `market_scanner.py` line 136
**Severity:** CRITICAL (will cause missed trades every single day)

```python
# Current code:
passing_symbols = set(list(passing_symbols)[:self.max_symbols_to_scan])
```

**Bug:** When 3,200+ symbols pass the price pre-filter, this takes an arbitrary 500. Python `set` iteration order is non-deterministic. The 500 symbols sent to `stock_filter.py` for expensive API calls are essentially random, NOT sorted by gap%, volume, or any relevance metric.

**Impact:** The entire stock_filter pipeline receives random $2-$20 stocks instead of today's actual gap-up movers. This is why 499/500 fail filters every day — the scanner is sending Ford, Uber, and random SPACs instead of the day's momentum stocks.

**Fix:** Sort by a relevance proxy before truncating. The snapshot data already has price/volume:
```python
# Sort by volume descending before truncating
# (requires storing volume during prefilter_by_price)
ranked = sorted(passing_symbols_with_vol, key=lambda x: x[1], reverse=True)
passing_symbols = set(s for s, v in ranked[:self.max_symbols_to_scan])
```

---

## FINDING 2: No Bot Startup Health Check / Crash Detection

**File:** `daily_run.sh` lines 57-72
**Severity:** CRITICAL (will cause full missed days on crash)

```bash
python3 bot.py >> "$LOG_FILE" 2>&1 &
BOT_PID=$!
echo "Bot started (PID: $BOT_PID)"
# ... then just sleeps until 9 AM MT
sleep "$WAIT_SECS"
```

**Bug:** The script launches bot.py in the background, captures the PID, then immediately sleeps for 7 hours. If bot.py crashes 1 second after launch (as happened Friday), the script has no idea. It happily sleeps until 9 AM, then runs cleanup on a process that died hours ago.

**Impact:** Any startup crash = full missed trading day with zero alerting.

**Fix:** Add a post-launch health check:
```bash
python3 bot.py >> "$LOG_FILE" 2>&1 &
BOT_PID=$!
sleep 10
if ! kill -0 "$BOT_PID" 2>/dev/null; then
    echo "FATAL: bot.py crashed within 10s of launch!"
    # Send alert (pushover, email, SMS)
    exit 1
fi
```

Also add a watchdog loop that checks every 60 seconds:
```bash
while kill -0 "$BOT_PID" 2>/dev/null; do
    sleep 60
done
echo "ALERT: bot.py died at $(date)!"
# Send notification
```

---

## FINDING 3: No Alerting / Notification System

**File:** Entire codebase
**Severity:** CRITICAL (silent failures discovered hours later)

**Bug:** There is zero alerting infrastructure. No Pushover, no Slack webhook, no email, no SMS. Every failure this week was discovered by manually inspecting logs after the trading session ended.

**Impact:** Even if the bot crashes at 4:01 AM, nobody knows until they manually check, usually after market close.

**Fix:** Add a notification function called on:
1. Bot startup success ("Bot online, watching N symbols")
2. Bot crash/exit (in the cleanup trap)
3. Zero watchlist scenario ("WARNING: 0 symbols passed filters")
4. First trade signal of the day ("First ARM signal: ARTL")
5. Any trade execution

Pushover is ~10 lines of code:
```python
import requests
def notify(msg):
    requests.post("https://api.pushover.net/1/messages.json", data={
        "token": os.getenv("PUSHOVER_APP_TOKEN"),
        "user": os.getenv("PUSHOVER_USER_KEY"),
        "message": msg
    })
```

---

## FINDING 4: Zero-Symbol Watchlist Doesn't Trigger Abort or Alert

**File:** `bot.py` lines 791-811
**Severity:** CRITICAL (bot runs all day doing nothing)

**Bug:** When `filtered_watchlist` is empty (0 symbols), the bot continues to full initialization — creates bar builders, trade manager, starts all threads, connects to the data feed — then runs until killed. It's a fully operational bot watching zero symbols.

```python
filtered_watchlist = set()  # empty!
# ...proceeds to start everything anyway...
feed = create_feed(...)
bar_builder = TradeBarBuilder(...)
trade_manager = PaperTradeManager()
# ...starts 5 background threads...
feed.run()  # blocks forever, processing zero symbols
```

**Impact:** As seen Thursday 3/19 — the bot ran for 5+ hours with `watch=0` on every heartbeat. Entire session wasted.

**Fix:**
```python
if not filtered_watchlist:
    print("FATAL: No symbols passed filters. Aborting.", flush=True)
    notify("ALERT: Zero symbols passed filters — bot not trading today!")
    # Still start rescan thread to catch late movers
    # But alert the operator immediately
```

---

## FINDING 5: Rescan Thread Can't Recover a Zero-Watchlist Day

**File:** `bot.py` lines 617-689
**Severity:** MEDIUM (missed opportunities on days that start slow)

**Bug:** The rescan thread runs the same broken MarketScanner → StockFilter pipeline. If the initial scan returns garbage, rescans will too (same random-500 selection). Even when rescans find good symbols, the rescan checkpoints stop at 10:30 AM ET — if nothing was found by then, no more rescans.

Additionally, the rescan thread calls `filter_watchlist(raw)` which re-runs the expensive per-symbol API calls on another random 500. This takes 3-5 minutes per rescan, during which symbols are not being discovered.

**Fix:** The rescan should use a much smaller, targeted universe. Instead of re-running the full scanner, it should query just the top gap-up movers (which Alpaca's "most active" endpoint can provide in 1 API call).

---

## FINDING 6: `daily_run.sh` Doesn't Verify Working Directory or Python Environment

**File:** `daily_run.sh` lines 41-57
**Severity:** MEDIUM (contributed to Friday's crash)

```bash
cd ~/warrior_bot
git pull origin v6-dynamic-sizing 2>&1 || echo "WARN: git pull failed"
source ~/warrior_bot/venv/bin/activate
# ... later ...
cd ~/warrior_bot
python3 bot.py >> "$LOG_FILE" 2>&1 &
```

**Bugs:**
1. `git pull` can introduce merge conflicts that break files silently. The `|| echo "WARN"` continues even on conflict.
2. No verification that `market_scanner.py` (or any critical file) exists after git pull.
3. No `python3 -c "import market_scanner"` smoke test before launching.
4. If `venv` activation fails silently, system Python is used instead (different packages).

**Fix:** Add pre-flight checks:
```bash
cd ~/warrior_bot || exit 1
source venv/bin/activate || exit 1
python3 -c "from market_scanner import MarketScanner; from trade_manager import PaperTradeManager; print('Imports OK')" || exit 1
```

---

## FINDING 7: `console_heartbeat` Swallows All Exceptions Silently

**File:** `bot.py` lines 492-508

**Severity:** MEDIUM (hides diagnostic info)

```python
def console_heartbeat():
    while not stop_flag.is_set():
        try:
            # ...
        except Exception:
            pass  # ← swallows everything
        time.sleep(10)
```

**Bug:** If `trade_manager.open` throws (e.g., threading issue), the heartbeat silently stops providing useful info. The `pass` should at least log the error.

**Fix:** Replace `pass` with `log_event("exception", None, where="console_heartbeat", error=traceback.format_exc())`.

---

## FINDING 8: `pending_heartbeat` Can Crash Silently

**File:** `bot.py` lines 510-518

**Severity:** MEDIUM (orders could hang forever)

```python
def pending_heartbeat():
    while not stop_flag.is_set():
        try:
            if trade_manager:
                trade_manager.check_pending_entries()
                trade_manager.check_pending_exits()
        except Exception:
            log_event(...)
        time.sleep(0.5)
```

This is better (exceptions are logged), but if `check_pending_entries()` raises something not caught by the inner try (like a `SystemExit` or `KeyboardInterrupt`), the thread dies and pending orders are never checked again. Since it's a daemon thread, no one notices.

**Fix:** The main `feed.run()` loop should periodically check that critical threads are alive:
```python
if not hb.is_alive():
    print("CRITICAL: pending_heartbeat thread died!", flush=True)
    notify("ALERT: pending_heartbeat thread died!")
```

---

## FINDING 9: No `feed.run()` Reconnection Logic

**File:** `bot.py` lines 870-881, `data_feed.py`

**Severity:** MEDIUM (network blip = session over)

```python
try:
    feed.run()
except KeyboardInterrupt:
    print("\nStopped by user.", flush=True)
except Exception:
    print("🔥 Bot crashed with exception:", flush=True)
    traceback.print_exc()
finally:
    stop_flag.set()
```

**Bug:** If the Alpaca websocket disconnects (which Alpaca does periodically for maintenance), `feed.run()` throws an exception and the bot exits. There is zero reconnection logic. The `AlpacaFeed` wraps `StockDataStream` which has some built-in reconnect, but if that fails, the bot is dead.

**Fix:** Wrap in a reconnection loop:
```python
max_retries = 5
for attempt in range(max_retries):
    try:
        feed.run()
        break  # clean exit
    except KeyboardInterrupt:
        break
    except Exception:
        log_event("feed_disconnected", None, attempt=attempt)
        if attempt < max_retries - 1:
            time.sleep(5 * (attempt + 1))  # backoff
            feed = create_feed(API_KEY, API_SECRET)
            # re-subscribe all symbols
        else:
            notify("FATAL: Feed disconnected after max retries")
```

---

## FINDING 10: StockFilter Makes 500 Sequential API Calls at Startup

**File:** `stock_filter.py` lines 271-325
**Severity:** MEDIUM (slow startup, rate limiting risk)

```python
for symbol in sorted(symbols):  # 500 symbols, sequentially
    info = self.get_stock_info(symbol)  # 2 API calls per symbol (snapshot + 60-day bars)
```

**Bug:** This loop makes ~1,000 Alpaca API calls sequentially at startup. At ~100ms per call, that's ~100 seconds. During this time, the bot isn't watching anything. If Alpaca rate-limits (200 calls/minute), this will take even longer or fail entirely.

**Impact:** The startup filtering takes 2-5 minutes. During this time, stocks are gapping and the bot misses early movers.

**Fix:**
1. Use ThreadPoolExecutor for parallel API calls (market_scanner.py already imports it but doesn't use it here).
2. Batch snapshot requests (Alpaca supports multi-symbol snapshots — market_scanner.py already does this).
3. Cache the 60-day bar data (it doesn't change intraday).

---

## FINDING 11: `filter_watchlist` Fallback Returns Unfiltered Set (Sometimes)

**File:** `bot.py` line 153

**Severity:** MEDIUM (500 random symbols without fundamental data)

```python
except Exception as e:
    print(f"⚠️ Stock filtering failed: {e}", flush=True)
    return symbols  # Fallback to unfiltered ← returns 500 random symbols!
```

**Bug:** When the filter crashes, the fallback returns the full raw watchlist. But `stock_info_cache` is empty because filtering didn't complete. The bot now watches 500 symbols with zero fundamental data — quality gates and pillar gates have no gap/rvol info and will either pass everything blindly or block everything.

**Fix:** On filter failure, return an empty set and alert:
```python
except Exception as e:
    notify(f"ALERT: Stock filtering crashed: {e}")
    return set()  # Don't trade garbage
```

---

## FINDING 12: API Keys Exposed in .env (Checked Into Git)

**File:** `.env` lines 2-3, 138, 240
**Severity:** MEDIUM (security risk)

The `.env` file contains live API keys:
- Alpaca paper trading keys
- Databento API key
- FMP API key

The `.gitignore` includes `.env`, but the file is present in the repo. If this repo is ever made public or shared, all keys are exposed.

**Fix:** Verify `.env` is in `.gitignore` and has never been committed. Run `git log --all --full-history -- .env` to check. Consider rotating keys.

---

## FINDING 13: No Log Rotation

**File:** `logger.py`
**Severity:** LOW (disk fill risk over weeks)

Each run creates a new `events_<run_id>.jsonl` file. The March 18 events file is already 14MB for one day. Daily logs (`2026-03-18_daily.log`) hit 1.1MB. Over weeks/months, this will fill disk.

**Fix:** Add log rotation (logrotate config or periodic cleanup of files >7 days old).

---

## FINDING 14: `live_scanner.py` and `bot.py` Are Two Separate Systems That Don't Coordinate

**File:** `live_scanner.py`, `bot.py`
**Severity:** MEDIUM (architectural confusion)

There are two independent scanner systems:
1. `live_scanner.py` — Databento-based real-time scanner (writes to `watchlist.txt`)
2. `market_scanner.py` — Alpaca-based scanner (used by bot.py when `WB_ENABLE_DYNAMIC_SCANNER=1`)

They don't share code or coordinate. The `.env` has `WB_ENABLE_DYNAMIC_SCANNER=1`, meaning bot.py uses the inferior Alpaca scanner, NOT the Databento live_scanner.

**Fix:** Either:
- Run `live_scanner.py` first (it writes watchlist.txt), then start `bot.py` with `WB_ENABLE_DYNAMIC_SCANNER=0` so it reads from watchlist.txt
- OR integrate live_scanner's logic into bot.py's startup

---

## FINDING 15: `set -euo pipefail` in daily_run.sh Conflicts With Background Processes

**File:** `daily_run.sh` line 5
**Severity:** LOW

`set -e` causes the script to exit on any command failure. But background processes (`bot.py &`, `caffeinate &`) that fail won't trigger this — only foreground commands will. However, the `kill "$BOT_PID"` in cleanup will fail if the bot already crashed, and `set -e` would exit the cleanup trap. The `|| true` suffixes handle this, but it's fragile.

---

## FINDING 16: TWS/IBC 90-Second Sleep Is Not Verified

**File:** `daily_run.sh` line 51
**Severity:** LOW

```bash
~/ibc/twsstartmacos.sh &
IBC_PID=$!
sleep 90  # TWS needs ~60-90s to fully log in
```

If TWS takes longer (first login of the week, 2FA prompt, update), the bot starts before TWS is ready. This matters when `WB_DATA_FEED=ibkr`, but currently the feed is set to `alpaca`, so this isn't an active issue.

---

## FINDING 17: `on_trade` and `on_quote` Callbacks Are Synchronous

**File:** `data_feed.py` lines 77-88
**Severity:** LOW

The Alpaca feed uses `async def _handler` but calls the synchronous `callback()` directly. This blocks the event loop for each trade/quote. With 500 subscribed symbols, trade processing delays can cause stale prices.

**Fix:** Use a queue to decouple the event loop from trade processing, or ensure callbacks are non-blocking.

---

## FINDING 18: Reconcile Thread Has No Rate Limiting on API Calls

**File:** `trade_manager.py` lines 812-830
**Severity:** LOW

The reconcile thread runs every 3 seconds and calls `get_open_position()` + `get_orders()` for every symbol in the universe. With 20+ symbols, that's 40+ API calls every 3 seconds. Every 10th cycle, it also calls `get_all_positions()`.

At scale, this could hit Alpaca's rate limit (200 requests/minute).

---

## FINDING 19: `AppleEvent timed out` Error Appears Every Day

**File:** All cron logs
**Severity:** LOW (cosmetic, but may indicate TWS issues)

Every single day shows: `18:82: execution error: Terminal got an error: AppleEvent timed out. (-1712)`

This is likely from TWS/IBC trying to interact with the macOS GUI. It doesn't crash the bot, but it may indicate TWS isn't fully initialized or the display server isn't available.

---

## RESILIENCE CHECKLIST

| Scenario | Current Behavior | Status |
|---|---|---|
| Network blip | Feed dies, bot exits, no restart | FAIL |
| API rate limit | Unhandled — stock_filter makes 1000 calls | FAIL |
| Bad data from feed | on_trade has try/except, logged | OK |
| Clean shutdown | stop_flag.set() in finally | OK |
| Restart mid-day and pick up | Manual (cp last_session_symbols.txt watchlist.txt) | PARTIAL |
| Zero candidates from scanner | Bot runs all day watching nothing | FAIL |
| Startup crash | Cron sleeps 7 hours, nobody knows | FAIL |
| Thread death | No monitoring, daemon threads die silently | FAIL |
| Disk full from logs | No rotation | FAIL |

---

## PRIORITY FIX LIST (Ordered by Impact)

### Must Fix Before Monday (Critical)

1. **Fix MarketScanner pre-filter to sort by volume/activity before truncating** (Finding 1)
   - This alone caused 3 of 4 missed days this week
   - ~20 lines of code change in `market_scanner.py`

2. **Add startup crash detection + alerting** (Findings 2, 3)
   - Add post-launch `kill -0` check in daily_run.sh
   - Add Pushover/webhook notifications for crash/zero-symbol/first-trade
   - ~50 lines total

3. **Abort or alert on zero-symbol watchlist** (Finding 4)
   - Add a check after filtering: if 0 symbols, send alert and log clearly
   - ~5 lines

4. **Add pre-flight import smoke test** (Finding 6)
   - `python3 -c "import bot"` before launching
   - ~3 lines in daily_run.sh

### Should Fix This Week (Medium)

5. **Integrate live_scanner.py with bot.py** or switch to running live_scanner first (Finding 14)
6. **Add feed.run() reconnection loop** (Finding 9)
7. **Parallelize stock_filter API calls** (Finding 10)
8. **Add thread health monitoring** (Finding 8)
9. **Fix filter_watchlist fallback** to not return unfiltered garbage (Finding 11)

### Nice to Have (Low)

10. Log rotation (Finding 13)
11. Investigate AppleEvent timeout (Finding 19)
12. Rate limit reconcile API calls (Finding 18)

---

## APPENDIX: Log Evidence Summary

| Date | Cron Log | Daily Log | Outcome |
|---|---|---|---|
| Mon 3/17 | Bot started OK | 1 stock (CRAQU) passed filter, idle all day | MISSED |
| Tue 3/18 | Bot started OK | 0 passed filter, fallback to 500 random, no stock_info | MISSED |
| Thu 3/19 | Bot started OK | 0 passed filter, 0 watchlist, empty heartbeats all day | MISSED |
| Fri 3/20 | Bot started OK | `ModuleNotFoundError: market_scanner` crash at import | MISSED |
| Fri 3/20 (manual) | N/A | Started at 11:40 AM ET, found ARTL+RDGT, too late for AM session | PARTIAL |
