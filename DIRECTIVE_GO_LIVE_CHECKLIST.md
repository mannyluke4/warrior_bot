# DIRECTIVE: Go Live Checklist — Real Money, Squeeze Only, 1 Trade/Day

**Date:** April 19, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code) to review and execute  
**Priority:** P0 — Must be completed before Monday April 20 market open  
**CAUTION:** This switches from paper trading to REAL MONEY. Every item must be verified.

---

## Pre-Flight: Verify Current State

Before changing anything, verify the current paper setup works:

- [ ] **1.** SSH/VNC into Mac Mini
- [ ] **2.** Run `cd ~/warrior_bot_v2 && git pull origin v2-ibkr-migration` — confirm latest code
- [ ] **3.** Run `python3 -c "import py_compile; py_compile.compile('bot_v3_hybrid.py', doraise=True); print('OK')"` — confirm syntax clean
- [ ] **4.** Run `cat .env` — record current settings as rollback reference
- [ ] **5.** Verify paper account balance on IBKR Dashboard — record starting balance

---

## Step 1: IBC Config (Switch Gateway to Live)

The IBC config controls whether Gateway starts in paper or live mode.

- [ ] **6.** Open IBC config: `nano ~/ibc/config.ini`
- [ ] **7.** Find `TradingMode` and change:
  ```ini
  # WAS:
  TradingMode=paper
  
  # CHANGE TO:
  TradingMode=live
  ```
- [ ] **8.** Verify `IbLoginId` and `IbPassword` are set to the LIVE account credentials (not the paper account username)
- [ ] **9.** Check if config has a `GatewayPort` setting. If so, verify it says `4001` (not `4002`). If there's no `GatewayPort` line, IBC uses the port from the TradingMode: live=4001, paper=4002.
- [ ] **10.** Save and close

**VERIFICATION:** After making changes, run:
```bash
grep -i "TradingMode\|GatewayPort\|IbLoginId" ~/ibc/config.ini
```
Expected output should show `TradingMode=live` and the correct login.

---

## Step 2: daily_run_v3.sh (Switch Port)

- [ ] **11.** Open: `nano ~/warrior_bot_v2/daily_run_v3.sh`
- [ ] **12.** Find the port assignment near the top and change:
  ```bash
  # WAS:
  IBKR_PORT=4002  # Gateway paper trading port
  
  # CHANGE TO:
  IBKR_PORT=4001  # Gateway LIVE trading port
  ```
- [ ] **13.** Save and close

**VERIFICATION:**
```bash
grep "IBKR_PORT=" ~/warrior_bot_v2/daily_run_v3.sh
```
Expected: `IBKR_PORT=4001`

---

## Step 3: .env File (Strategy Settings)

- [ ] **14.** Open: `nano ~/warrior_bot_v2/.env`
- [ ] **15.** Set or verify ALL of the following:

```bash
# === IBKR Connection (LIVE) ===
IBKR_PORT=4001
IBKR_CLIENT_ID=1

# === Broker ===
WB_BROKER=ibkr

# === Strategy: SQUEEZE ONLY ===
WB_SQUEEZE_ENABLED=1
WB_SQUEEZE_VERSION=1
WB_SQ_PARA_ENABLED=1

# === Everything else OFF ===
WB_SHORT_ENABLED=0
WB_BOX_ENABLED=0
WB_MP_ENABLED=0
WB_MP_V2_ENABLED=0
WB_CT_ENABLED=0
WB_EPL_ENABLED=0

# === PDT Protection: 1 trade per day ===
WB_MAX_DAILY_ENTRIES=1

# === Risk Management (conservative for live) ===
WB_RISK_PCT=0.025
WB_MAX_DAILY_LOSS=1500
WB_MAX_CONSECUTIVE_LOSSES=1
WB_SQ_TARGET_R=2.0
WB_SQ_TRAIL_R=1.5
WB_SQ_PARA_TRAIL_R=1.0
WB_MIN_R=0.06

# === Entry Execution ===
WB_ENTRY_RETRY_ENABLED=1
WB_ENTRY_MAX_RETRIES=3
WB_ENTRY_RETRY_TIMEOUT_SEC=10
WB_ENTRY_MAX_CHASE_PCT=2.0
WB_ENTRY_SLIPPAGE_MIN=0.05
WB_ENTRY_SLIPPAGE_PCT=0.005

# === Exit Safety ===
WB_BAIL_TIMER_ENABLED=1
WB_BAIL_TIMER_MINUTES=5

# === Position Sizing ===
WB_SCALE_NOTIONAL=1
WB_BUYING_POWER_PCT=0.50
WB_MAX_NOTIONAL=100000
WB_MAX_SHARES=100000

# === Trading Windows ===
WB_TRADING_WINDOWS=07:00-12:00,16:00-20:00
```

- [ ] **16.** Save and close

**VERIFICATION:**
```bash
grep "IBKR_PORT\|WB_BROKER\|WB_SQUEEZE_ENABLED\|WB_SHORT_ENABLED\|WB_MAX_DAILY_ENTRIES\|WB_MAX_DAILY_LOSS" ~/warrior_bot_v2/.env
```
Expected:
```
IBKR_PORT=4001
WB_BROKER=ibkr
WB_SQUEEZE_ENABLED=1
WB_SHORT_ENABLED=0
WB_MAX_DAILY_ENTRIES=1
WB_MAX_DAILY_LOSS=1500
```

---

## Step 4: Verify IB Gateway Starts in Live Mode

- [ ] **17.** Kill any running Gateway: `pkill -9 -f "java.*ibgateway"`
- [ ] **18.** Start Gateway manually: `~/ibc/gatewaystartmacos.sh -inline`
- [ ] **19.** Wait for it to connect (~2-3 minutes)
- [ ] **20.** Verify it's on port 4001:
  ```bash
  python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',4001)); s.close(); print('Gateway LIVE port 4001: UP')" 2>/dev/null || echo "Port 4001 NOT listening"
  ```
- [ ] **21.** Verify port 4002 is NOT active (paper Gateway not running):
  ```bash
  python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',4002)); s.close(); print('WARNING: Paper port 4002 also active!')" 2>/dev/null || echo "Port 4002 clear (good)"
  ```
- [ ] **22.** Connect and verify account type:
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
  **Expected:** `AccountType` should say something like `INDIVIDUAL` (not `PAPER_INDIVIDUAL` or `DU...` prefix). `NetLiquidation` should show your real account balance.

- [ ] **23.** Kill the test Gateway: `pkill -9 -f "java.*ibgateway"`

---

## Step 5: Pre-Market Dry Run (Optional but Recommended)

Before the 2 AM cron fires, do a manual test:

- [ ] **24.** At ~6:45 AM ET Monday, manually start:
  ```bash
  cd ~/warrior_bot_v2 && bash daily_run_v3.sh
  ```
- [ ] **25.** Watch the log: `tail -f ~/warrior_bot_v2/logs/2026-04-21_daily.log`
- [ ] **26.** Verify the boot banner shows:
  - `Port: 4001` (not 4002)
  - `Squeeze: ON`
  - `Short: OFF`
  - `Box: OFF`
  - `Max entries/day: 1`
  - `Max daily loss: $1,500`
  - `Broker: ibkr`
  - Account equity shows your REAL balance (not $29.5K paper)
- [ ] **27.** Verify scanner runs and finds candidates
- [ ] **28.** Watch for the first PRIMED event — if it fires, the system is working
- [ ] **29.** If comfortable, let it run. If nervous, `Ctrl+C` to kill and wait for more data.

---

## Step 6: Cron Verification

- [ ] **30.** Verify the cron is set for the daily run:
  ```bash
  crontab -l | grep daily_run
  ```
  Expected: `0 2 * * 1-5 /bin/bash ~/warrior_bot_v2/daily_run_v3.sh`
  
- [ ] **31.** Verify keep_alive.sh cron is active:
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

# 3. Switch .env back to paper
sed -i '' 's/IBKR_PORT=4001/IBKR_PORT=4002/' ~/warrior_bot_v2/.env

# 4. Switch daily_run_v3.sh back to paper
sed -i '' 's/IBKR_PORT=4001/IBKR_PORT=4002/' ~/warrior_bot_v2/daily_run_v3.sh

# 5. Switch IBC back to paper
sed -i '' 's/TradingMode=live/TradingMode=paper/' ~/ibc/config.ini

# 6. Restart in paper mode
cd ~/warrior_bot_v2 && bash daily_run_v3.sh
```

---

## Post-Launch Monitoring (Monday Morning)

- [ ] **32.** After first trade (or by 10 AM ET if no trades), check:
  - IBKR Dashboard: does the account show the trade?
  - Bot log: does it show FILL confirmation with real fill price?
  - Position sync: does heartbeat show the correct position?
- [ ] **33.** After first exit, verify:
  - P&L matches between bot log and IBKR Dashboard
  - Position is fully flat (no orphan shares)
  - `WB_MAX_DAILY_ENTRIES=1` prevented any second trade

---

## What CC Should Review Before Signing Off

1. The `preflight_port_check()` function in `bot_v3_hybrid.py` only checks ports 4002 and 7497 — add port 4001 to the check
2. Confirm `IBKRBroker.get_buying_power()` works on a live account (it reads `BuyingPower` tag from `accountValues`)
3. Confirm the `graceful_shutdown` handler closes any open positions on SIGTERM — we do NOT want the bot to die with real shares held
4. Verify the position reconciliation on startup (`reconcile_positions_on_startup`) works correctly when the account has real history

---

*This is real money. Triple-check everything. One trade, one day, prove it works.*
