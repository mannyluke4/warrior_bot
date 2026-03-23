# Directive: Live Bot Full Audit & Update

## Priority: P0 — MUST COMPLETE BEFORE MARKET OPEN TOMORROW
## Owner: CC (Terminal)
## Created: 2026-03-23
## Context: Mac Mini live bot is 22 commits behind main. daily_run.sh pulls wrong branch.

---

## The Problem

`daily_run.sh` pulls/pushes `origin/v6-dynamic-sizing`. All development has moved to `main`. The v6 branch is a strict subset of main (0 commits on v6 not in main, 22 commits on main not in v6). The Mac Mini is running stale code missing critical changes:

- WB_MP_ENABLED gate (bot might be trying MP entries without the gate code)
- WB_ALLOW_PROFILE_X gate
- SQ exit fixes (Fix 1/2/3)
- Item 5: Conviction Sizing
- Item 6: Halt-Through Logic
- ALL ross exit wiring (ross_exit.py, bot.py hooks, trade_manager.py hooks)
- partial_taken vs tp_hit bug fix
- market_scanner.py P0 sort fix (may or may not be on v6 — it's in the merge commit)

Additionally, `daily_run.sh` starts TWS via IBC (Interactive Brokers), which the bot hasn't used in weeks. This wastes 90 seconds on startup and leaves a zombie Java process.

---

## Pre-Flight

```bash
cd ~/warrior_bot
source venv/bin/activate
```

**DO NOT `git pull` yet.** First, audit what's actually running.

---

## Step 1: Audit Current State on Mac Mini

### 1a. What branch is checked out?
```bash
git branch --show-current
git log --oneline -5
```
Expected: probably on `v6-dynamic-sizing` or a detached HEAD. Record what you find.

### 1b. Are there uncommitted changes?
```bash
git status
git diff --stat
```
If there are local changes that aren't on any branch, stash them:
```bash
git stash save "pre-audit-$(date +%Y%m%d)"
```

### 1c. What .env is the bot actually using?
```bash
# Check for the critical vars
grep -E "WB_ROSS_EXIT|WB_MP_ENABLED|WB_SQUEEZE_ENABLED|WB_PILLAR_GATES|WB_DATA_FEED" .env
```
Record the output.

### 1d. Is bot.py currently running?
```bash
ps aux | grep bot.py | grep -v grep
ps aux | grep -i tws | grep -v grep
```
Kill anything lingering from today's failed run:
```bash
pkill -f "bot.py" 2>/dev/null || true
pkill -f "java.*tws" 2>/dev/null || true
```

### 1e. Check for stale Alpaca websocket connections
The live bot audit found 99,934 failed reconnection attempts today due to a stale websocket holding a connection slot. We need to ensure no stale connections persist:
```bash
# Check for any lingering Python processes that might hold websocket connections
ps aux | grep -E "python.*bot|python.*alpaca" | grep -v grep
```
Kill any found.

---

## Step 2: Switch to Main Branch

```bash
# Ensure clean working tree
git stash save "pre-switch-$(date +%Y%m%d)" 2>/dev/null || true

# Switch to main and pull latest
git checkout main
git pull origin main

# Verify we're current
git log --oneline -5
```

The HEAD should be `f70c406 Merge branch 'claude/zealous-antonelli'` or newer.

---

## Step 3: Update daily_run.sh

Replace all `v6-dynamic-sizing` references with `main`:

### 3a. Change git pull branch
```bash
# Line 42: git pull origin v6-dynamic-sizing
# Change to: git pull origin main
```

### 3b. Change git push branch (in cleanup trap AND in step 7)
```bash
# Line 25: git push origin v6-dynamic-sizing
# Change to: git push origin main

# Line 113: git push origin v6-dynamic-sizing
# Change to: git push origin main
```

### 3c. Remove TWS/IBC startup (the bot uses Alpaca, not IBKR)

Remove or comment out the entire TWS section (lines 55-60):
```bash
# OLD:
# echo "Starting TWS via IBC..."
# ~/ibc/twsstartmacos.sh &
# IBC_PID=$!
# sleep 90  # TWS needs ~60-90s to fully log in
# echo "TWS started (IBC PID: $IBC_PID)"
```

Also remove/update the IBC_PID references:
- Line 18: `kill "$IBC_PID" 2>/dev/null || true` — remove or guard with `[ -n "$IBC_PID" ]`
- Line 20: `pkill -f "java.*tws"` — can keep as safety net
- Line 31: `IBC_PID=""` — remove or keep as no-op
- Line 102: `kill "$IBC_PID"` — remove or guard

### 3d. Add Alpaca websocket cleanup before bot start

Add this BEFORE "Starting bot..." (before line 64):
```bash
# Kill any stale Python processes that might hold Alpaca websocket connections
echo "Cleaning up stale connections..."
pkill -f "bot.py" 2>/dev/null || true
sleep 2
```

### 3e. Verify the final script makes sense

After edits, the flow should be:
1. Pull latest from `main`
2. Activate venv
3. Pre-flight import smoke test
4. Kill stale connections
5. Start bot.py
6. 10s health check
7. Watchdog loop until 9:00 AM MT
8. Shutdown
9. Push logs to `main`

---

## Step 4: Verify .env Matches Expected Config

The .env in git (on main) has these critical settings. Verify the Mac Mini's .env matches:

```
WB_ROSS_EXIT_ENABLED=0          # MUST be 0 (YTD showed -$17,815 regression)
WB_MP_ENABLED=0                 # MUST be 0 (0% win rate, -$3,947 in Jan 2025)
WB_SQUEEZE_ENABLED=1            # Primary strategy
WB_SQ_PARA_ENABLED=1            # Parabolic squeeze enabled
WB_PILLAR_GATES_ENABLED=1       # Ross Pillar entry-time gates
WB_CLASSIFIER_ENABLED=1         # Stock behavior classifier
WB_EXHAUSTION_ENABLED=1         # Dynamic scaling handles cascading stocks
WB_CONTINUATION_HOLD_ENABLED=1
WB_ENABLE_DYNAMIC_SCANNER=1     # Market scanner active
WB_DATA_FEED=alpaca             # Using Alpaca (not Databento yet)
WB_MAX_NOTIONAL=50000
WB_MAX_LOSS_R=0.75
WB_BAIL_TIMER_ENABLED=1
WB_BAIL_TIMER_MINUTES=5
```

If any of these don't match, update the Mac Mini's .env to match git.

**IMPORTANT:** The .env is gitignored (it has API keys). Copy the file from git but make sure the API keys are correct for the Mac Mini's Alpaca account.

---

## Step 5: Verify Key Files Match Main HEAD

Quick diff check — these should all be clean after switching to main:

```bash
git diff HEAD -- bot.py trade_manager.py market_scanner.py stock_filter.py ross_exit.py .env daily_run.sh
```

If there's ANY output, something is wrong. The Mac Mini should be running exactly what's on main HEAD.

---

## Step 6: Smoke Test

### 6a. Import test
```bash
python3 -c "
from market_scanner import MarketScanner
from trade_manager import PaperTradeManager
from ross_exit import RossExitManager
from micro_pullback import MicroPullbackDetector
print('All imports OK')
"
```

### 6b. Quick simulation test (confirms full pipeline works)
```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583 (1 trade)
```

### 6c. Scanner test
```bash
# Verify market_scanner.py sorts by volume before truncation (P0 fix)
grep -n "sort.*volume\|sorted.*volume" market_scanner.py
```

---

## Step 7: Cron Job Verification

```bash
crontab -l | grep daily_run
```

Should show: `0 2 * * 1-5 ~/warrior_bot/daily_run.sh` (or similar).

If the cron entry references `v6-dynamic-sizing` or a different script path, update it.

---

## Step 8: Commit and Push

```bash
git add daily_run.sh
git commit -m "Switch daily_run.sh to main branch, remove TWS/IBC, add websocket cleanup

- Pull/push main instead of v6-dynamic-sizing (v6 is 22 commits behind, fully merged)
- Remove TWS/IBC startup (bot uses Alpaca, saves 90s startup)
- Add stale connection cleanup before bot launch
- Fixes root cause of today's 0-trade session

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

git push origin main
```

---

## Step 9: Write Audit Report

Save a brief report to `cowork_reports/2026-03-23_live_bot_update.md` with:
1. What branch the Mac Mini was on before the switch
2. Any local changes found (stashed or lost)
3. .env differences found and fixed
4. Smoke test results
5. Confirmation that daily_run.sh now targets main

---

## Success Criteria

- [ ] Mac Mini is on `main` branch, up to date
- [ ] `daily_run.sh` pulls/pushes `main` (not v6-dynamic-sizing)
- [ ] TWS/IBC startup removed from daily_run.sh
- [ ] Websocket cleanup added to daily_run.sh
- [ ] .env matches expected config (especially ROSS_EXIT=0, MP=0, SQUEEZE=1)
- [ ] All imports pass
- [ ] VERO regression passes (+$18,583)
- [ ] Cron job verified
- [ ] Audit report committed
- [ ] `git push origin main` successful

---

## DO NOT

- Do NOT modify any .py files (bot.py, trade_manager.py, etc.) — they're correct on main
- Do NOT enable `WB_ROSS_EXIT_ENABLED=1` — it's disabled pending further work
- Do NOT merge v6 into main — main already has everything
- Do NOT delete the v6-dynamic-sizing branch (might need it for reference)
- Do NOT change any env var defaults beyond matching the expected config above
