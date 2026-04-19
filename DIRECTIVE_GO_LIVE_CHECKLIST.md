# DIRECTIVE: Go Live Checklist — Real Money, Squeeze Only, 1 Trade/Day

**Date:** April 19, 2026
**Original author:** Cowork (Perplexity)
**Revised by:** Cowork (Opus), 2026-04-19 evening
**For:** CC (Claude Code) to execute
**Priority:** P0 — Must be completed before Monday April 20 market open
**CAUTION:** This switches from paper trading to REAL MONEY. Every item must be verified.

---

## Revision notes (Opus)

Perplexity's original checklist had the right structure. Changes made:

1. **Execution broker:** `WB_BROKER=ibkr` confirmed by Manny. All execution goes through `IBKRBroker` in `broker.py` — data AND execution on IBKR, Alpaca not used. This is a new execution path for the live bot; IBKRBroker is implemented but all paper validation was on AlpacaBroker. CC must verify IBKRBroker works on the live gateway before market open (Step 5 below).
2. **Preserved X01 tuning.** Perplexity's .env omitted the battle-tested X01 config (VOL_MULT, PRIME_BARS, MIN_BODY_PCT, MAX_ATTEMPTS, CORE_PCT, winsorize, stale-seed, pillar gates, etc.). These must remain. The directive now specifies only the lines to CHANGE or ADD — everything else stays as-is.
3. **Reverted `WB_SQ_TARGET_R` to 1.5.** Perplexity set 2.0, but X01 tuning specifically moved from 2.0→1.5 because 1.5 was more profitable in backtest (+$34K VERO vs +$18K at 2.0). Don't regress proven tuning on Day 1.
4. **Reduced `WB_MAX_NOTIONAL` to 25000.** Perplexity had $100K. Current paper is $50K. For first live trade with real money, half the paper size. Can scale up after the first week proves clean.
5. **Removed Alpaca steps.** No Alpaca API keys needed. No Alpaca port checks.
6. **Added `WB_BROKER=ibkr` verification step.** Must confirm IBKRBroker produces real fills on the live gateway.
7. **Tightened trading window.** Removed 16:00-20:00 for Day 1. Squeeze-only in the morning.
8. **Added phantom-P&L fix verification.** Today's commit `9b793f8` must be on the machine.

---

## Pre-Flight: Verify Current State

Before changing anything, verify the current setup works:

- [ ] **1.** SSH/VNC into Mac Mini
- [ ] **2.** `cd ~/warrior_bot_v2 && git pull origin v2-ibkr-migration` — confirm latest code (including phantom-P&L fix `9b793f8` and sim:1981 fix `89e52c5`)
- [ ] **3.** `python3 -c "import py_compile; py_compile.compile('bot_v3_hybrid.py', doraise=True); print('OK')"` — syntax clean
- [ ] **4.** Record current `.env` as rollback reference: `cp .env .env.paper_backup_20260419`
- [ ] **5.** Verify paper account status on Alpaca Dashboard — record final paper balance for posterity

---

## Step 1: IBC Config (Switch Gateway to Live)

- [ ] **6.** Open IBC config: `nano ~/ibc/config.ini`
- [ ] **7.** Change `TradingMode=paper` → `TradingMode=live`
- [ ] **8.** Verify `IbLoginId` and `IbPassword` are the LIVE account credentials (not paper)
- [ ] **9.** Verify `GatewayPort` is `4001` (or absent — IBC defaults live to 4001)
- [ ] **10.** Save and close

**VERIFICATION:**
```bash
grep -i "TradingMode\|GatewayPort\|IbLoginId" ~/ibc/config.ini
```
Expected: `TradingMode=live`, correct login, port 4001.

---

## Step 2: daily_run_v3.sh (Switch Port)

- [ ] **11.** Open: `nano ~/warrior_bot_v2/daily_run_v3.sh`
- [ ] **12.** Change `IBKR_PORT=4002` → `IBKR_PORT=4001`
- [ ] **13.** Save and close

**VERIFICATION:**
```bash
grep "IBKR_PORT=" ~/warrior_bot_v2/daily_run_v3.sh
```
Expected: `IBKR_PORT=4001`

---

## Step 3: .env File (Targeted Changes Only)

**CRITICAL: Do NOT rewrite the entire .env. Only CHANGE or ADD the lines below. All existing X01 tuning, winsorize, stale-seed, pillar gates, exhaustion, continuation hold, entry slippage, bail timer, and scanner settings MUST remain untouched.**

- [ ] **14.** `cp .env .env.paper_backup_20260419` (if not done in step 4)
- [ ] **15.** Open: `nano ~/warrior_bot_v2/.env`
- [ ] **16.** Change or add ONLY these lines:

```bash
# === IBKR Connection (LIVE) ===
IBKR_PORT=4001
IBKR_CLIENT_ID=1

# === Execution broker: IBKR (not Alpaca) ===
WB_BROKER=ibkr

# === PDT Protection: 1 trade per day ===
WB_MAX_DAILY_ENTRIES=1

# === Conservative risk for Day 1 live ===
WB_RISK_PCT=0.025                # was 0.035 paper — conservative start
WB_MAX_DAILY_LOSS=500            # hard stop for Day 1 — single trade max loss
WB_MAX_CONSECUTIVE_LOSSES=1      # redundant with 1 entry/day but belt-and-suspenders

# === Position sizing: half of paper ===
WB_MAX_NOTIONAL=25000            # was 50000 paper — half size for first week
WB_BUYING_POWER_PCT=0.50

# === Trading window: morning only for Day 1 ===
WB_TRADING_WINDOWS=07:00-12:00

# === Everything non-squeeze OFF ===
WB_SHORT_ENABLED=0
WB_BOX_ENABLED=0
WB_MP_ENABLED=0
WB_MP_V2_ENABLED=0
WB_CT_ENABLED=0
WB_EPL_ENABLED=0
```

- [ ] **17.** Save and close

**DO NOT TOUCH these lines (must remain at X01 values):**
```bash
WB_SQUEEZE_ENABLED=1             # already set
WB_SQ_VOL_MULT=2.5
WB_SQ_PRIME_BARS=4
WB_SQ_MIN_BODY_PCT=2.0
WB_SQ_MAX_ATTEMPTS=5
WB_SQ_TARGET_R=1.5               # Perplexity had 2.0 — WRONG, keep at 1.5
WB_SQ_CORE_PCT=90
WB_SQ_VOL_WINSORIZE_ENABLED=1
WB_SQ_VOL_WINSORIZE_CAP=5.0
WB_SQ_SEED_STALE_GATE_ENABLED=1
WB_SQ_SEED_STALE_PCT=2.0
WB_NO_REENTRY_ENABLED=1
WB_MAX_SYMBOL_LOSSES=1
WB_MAX_SYMBOL_TRADES=2
WB_PILLAR_GATES_ENABLED=1
WB_WARMUP_BARS=5
WB_BAIL_TIMER_ENABLED=1
WB_BAIL_TIMER_MINUTES=5
WB_EXHAUSTION_ENABLED=1
WB_CONTINUATION_HOLD_ENABLED=1
WB_CONT_HOLD_5M_TREND_GUARD=1
WB_DAILY_LOSS_SCALE=1
# All WB_ENTRY_* slippage/retry settings — keep as-is
# All WB_SQ_PARA_* parabolic settings — keep as-is
# All WB_MIN/MAX scanner settings — keep as-is
```

**VERIFICATION:**
```bash
grep "IBKR_PORT\|WB_BROKER\|WB_SQUEEZE_ENABLED\|WB_MAX_DAILY_ENTRIES\|WB_MAX_DAILY_LOSS\|WB_SQ_TARGET_R\|WB_MAX_NOTIONAL\|WB_EPL_ENABLED" ~/warrior_bot_v2/.env
```
Expected:
```
IBKR_PORT=4001
WB_BROKER=ibkr
WB_SQUEEZE_ENABLED=1
WB_MAX_DAILY_ENTRIES=1
WB_MAX_DAILY_LOSS=500
WB_SQ_TARGET_R=1.5
WB_MAX_NOTIONAL=25000
WB_EPL_ENABLED=0
```

---

## Step 4: Verify IB Gateway Starts in Live Mode

- [ ] **18.** Kill any running Gateway: `pkill -9 -f "java.*ibgateway"`
- [ ] **19.** Start Gateway: `~/ibc/gatewaystartmacos.sh -inline`
- [ ] **20.** Wait 2-3 minutes for connection
- [ ] **21.** Verify port 4001 is listening:
  ```bash
  python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',4001)); s.close(); print('Gateway LIVE port 4001: UP')" 2>/dev/null || echo "Port 4001 NOT listening"
  ```
- [ ] **22.** Verify port 4002 is NOT listening (paper Gateway not running):
  ```bash
  python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',4002)); s.close(); print('WARNING: Paper port 4002 also active!')" 2>/dev/null || echo "Port 4002 clear (good)"
  ```
- [ ] **23.** Connect and verify account type:
  ```bash
  cd ~/warrior_bot_v2 && source venv/bin/activate
  python3 -c "
  from ib_insync import IB
  ib = IB()
  ib.connect('127.0.0.1', 4001, clientId=99)
  acct = ib.accountValues()
  for v in acct:
      if v.tag in ('AccountType', 'NetLiquidation', 'BuyingPower') and v.currency == 'USD':
          print(f'{v.tag}: {v.value}')
  ib.disconnect()
  "
  ```
  **Expected:** `AccountType` should NOT show `PAPER` or `DU...` prefix. `NetLiquidation` should show Manny's real account balance.

- [ ] **24.** Kill the test Gateway: `pkill -9 -f "java.*ibgateway"`

---

## Step 5: IBKRBroker Execution Smoke Test (NEW — critical)

All paper validation was on AlpacaBroker. `WB_BROKER=ibkr` routes through `IBKRBroker` in `broker.py`. Before real money, verify the execution path works on the live gateway.

- [ ] **25.** Start Gateway in live mode (if not already running from Step 4)
- [ ] **26.** Run a minimal smoke test — CC should write a short script that:
  1. Connects to IBKR on port 4001 (clientId=98, different from bot's clientId=1)
  2. Instantiates `IBKRBroker(ib)`
  3. Calls `broker.get_buying_power()` — verify it returns the real account's buying power
  4. Calls `broker.get_positions()` — verify it returns empty list (no open positions)
  5. **Do NOT submit a real order.** Just verify the read paths work.
  6. Disconnect

- [ ] **27.** Verify `preflight_port_check()` in `bot_v3_hybrid.py` includes port 4001. Currently only checks 4002 and 7497. **Add 4001 to the check.** One-line fix.

- [ ] **28.** Verify `graceful_shutdown` handler behavior: on SIGTERM, it logs open positions and warns — it does NOT auto-flatten. This is correct for real money. Confirm no code path between SIGTERM and an auto-close-all.

---

## Step 6: Pre-Market Dry Run (REQUIRED, not optional)

- [ ] **29.** At ~6:45 AM ET Monday, manually start:
  ```bash
  cd ~/warrior_bot_v2 && bash daily_run_v3.sh
  ```
- [ ] **30.** Watch the log: `tail -f ~/warrior_bot_v2/logs/2026-04-20_daily.log`
- [ ] **31.** Verify the boot banner shows:
  - `Port: 4001` (not 4002)
  - `Broker: ibkr` (not alpaca)
  - `Squeeze: ON`
  - `Short: OFF`, `Box: OFF`, `EPL: OFF`
  - `Max entries/day: 1`
  - `Max daily loss: $500`
  - `Max notional: $25,000`
  - Account equity shows REAL balance (not ~$30K paper)
- [ ] **32.** Verify scanner runs and finds candidates
- [ ] **33.** Watch for the first PRIMED event — if it fires, the system is working
- [ ] **34.** If everything looks clean, let it trade. If anything is off, `Ctrl+C` immediately.

---

## Step 7: Cron Verification

- [ ] **35.** Verify daily cron:
  ```bash
  crontab -l | grep daily_run
  ```
  Expected: `0 2 * * 1-5 /bin/bash ~/warrior_bot_v2/daily_run_v3.sh`

- [ ] **36.** Verify keep_alive cron:
  ```bash
  crontab -l | grep keep_alive
  ```
  Expected: `*/2 4-20 * * 1-5 /bin/bash ~/warrior_bot_v2/keep_alive.sh`

---

## Emergency Rollback

If anything goes wrong, switch back to paper IMMEDIATELY:

```bash
# 1. Kill the bot
pkill -f bot_v3_hybrid.py

# 2. Kill Gateway
pkill -9 -f "java.*ibgateway"

# 3. Restore paper .env
cp ~/warrior_bot_v2/.env.paper_backup_20260419 ~/warrior_bot_v2/.env

# 4. Switch daily_run_v3.sh back to paper
sed -i '' 's/IBKR_PORT=4001/IBKR_PORT=4002/' ~/warrior_bot_v2/daily_run_v3.sh

# 5. Switch IBC back to paper
sed -i '' 's/TradingMode=live/TradingMode=paper/' ~/ibc/config.ini

# 6. Restart in paper mode
cd ~/warrior_bot_v2 && bash daily_run_v3.sh
```

**If the bot has an open position when you rollback:** do NOT kill it mid-trade. Wait for the exit, then rollback. Or manually close the position in IBKR Trader Workstation / web portal first.

---

## Post-Launch Monitoring (Monday Morning)

- [ ] **37.** After first trade (or by 10 AM ET if no trades), check:
  - IBKR Dashboard: does the account show the trade?
  - Bot log: does it show FILL confirmation with real fill price?
  - P&L in bot log matches `verify_exit_fill` actual Alpaca price (now using IBKR fills)
  - Position sync shows correct position
- [ ] **38.** After first exit, verify:
  - P&L matches between bot log and IBKR account
  - Position is fully flat (no orphan shares)
  - `WB_MAX_DAILY_ENTRIES=1` prevented any second trade attempt
  - No phantom P&L entries in the log
- [ ] **39.** Report results to Manny immediately after first round-trip completes

---

## What CC Must Review Before Signing Off

1. `preflight_port_check()` — add port 4001 to the check (currently only 4002 + 7497)
2. `IBKRBroker.get_buying_power()` — confirm it returns real buying power on live account
3. `IBKRBroker.submit_order()` — read the code path end-to-end; confirm it handles limit + market orders, partial fills, and rejections correctly
4. `graceful_shutdown` — confirm it does NOT auto-flatten (correct for real money)
5. Phantom-P&L fix from today (`9b793f8`) — confirm it's on the machine and not reverted
6. `verify_exit_fill` daemon — confirm it works with `IBKRBroker.get_order_status()` (was validated against AlpacaBroker; verify the IBKRBroker implementation returns the same shape)

---

## Summary of Perplexity changes (for the record)

| Setting | Perplexity original | Opus revision | Reason |
|---|---|---|---|
| `WB_BROKER` | `ibkr` | `ibkr` | Confirmed by Manny |
| `WB_SQ_TARGET_R` | `2.0` | `1.5` (keep X01) | X01 tuning proved 1.5 > 2.0 in backtest |
| `WB_MAX_NOTIONAL` | `100000` | `25000` | Half paper size for Day 1 real money |
| `WB_MAX_DAILY_LOSS` | `1500` | `500` | Tighter for 1 trade/day |
| `WB_TRADING_WINDOWS` | `07:00-12:00,16:00-20:00` | `07:00-12:00` | Morning only, Day 1 |
| X01 tuning vars | Omitted | Must remain | Battle-tested config, no regression |
| IBKRBroker smoke test | Not included | Added as Step 5 | New execution path needs verification |
| Alpaca steps | Included | Removed | Not using Alpaca for execution |

---

*This is real money. The strategy is proven. The execution path is new. Verify the plumbing, then let it trade.*
