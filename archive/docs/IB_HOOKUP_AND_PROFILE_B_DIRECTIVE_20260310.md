# DIRECTIVE: Interactive Brokers Hookup + Profile B Overhaul
**Date:** 2026-03-10
**Priority:** HIGH — IB hookup is go. Profile B fix is the next performance unlock.
**Branch:** v6-dynamic-sizing

---

## PART 1: INTERACTIVE BROKERS L2 HOOKUP

The IBKR integration code is **already fully wired** in `bot.py` (lines 784-805). The bot auto-detects `WB_ENABLE_L2=1` and imports `ibkr_feed.py`. No new code needed — just configuration and testing.

### Step 1: Install dependency
```bash
pip install ib_insync
```

### Step 2: Set up IB Gateway
- Download and install **IB Gateway** (lightweight, headless) or use **TWS** (full UI)
- IB Gateway is preferred for always-on operation
- Start in **paper trading mode** first
- Configure API settings:
  - Enable ActiveX and Socket Clients
  - Socket port: `7497` (paper) or `4002` (live)
  - Allow connections from localhost
  - Uncheck "Read-Only API" (bot needs to subscribe to market data)

### Step 3: Configure .env
Add/update these environment variables:
```env
WB_ENABLE_L2=1
WB_IBKR_HOST=127.0.0.1
WB_IBKR_PORT=7497       # Paper trading port
WB_IBKR_CLIENT_ID=1
```

### Step 4: Market Data Subscriptions (REQUIRED)
In IB Account Management, subscribe to:
1. **US Securities Snapshot and Futures Value Bundle** — basic quotes
2. **NASDAQ TotalView + Enhanced Display Service (EDS)** — NASDAQ L2 depth
3. **NYSE Open Book** — NYSE L2 depth

Without these, the bot will connect but receive no L2 data. The subscriptions cost ~$15-25/month total.

### Step 5: Smoke Test
```bash
python ibkr_feed.py AAPL 10
```
This runs the built-in test: connects to IB Gateway, subscribes to AAPL L2 for 10 seconds, prints order book updates. If you see bid/ask depth printing, the connection works.

### Step 6: Integration Test with Bot
1. Add a known Profile B stock to the watchlist with `:B` tag
2. Run the bot with `WB_ENABLE_L2=1`
3. Watch console output for:
   - `[L2] Connected to IBKR` — connection established
   - `[L2] Subscribed: {SYMBOL}` — L2 feed active
   - `[L2] imbalance=0.XX stacking=True/False` — signals flowing
   - `[L2] HARD GATE BLOCK` — bearish L2 blocking entries (this is good)
   - `[L2] score_boost +X.X` — bullish L2 accelerating entries

### Troubleshooting
- **Connection refused**: IB Gateway not running or wrong port
- **No data flowing**: Market data subscriptions not active, or market is closed
- **"HMDS data farm connection is OK" but no L2**: Need TotalView/OpenBook subscriptions
- **Client ID conflict**: Another process already connected with same client_id. Change `WB_IBKR_CLIENT_ID`

---

## PART 2: PROFILE B OVERHAUL — RISK ARCHITECTURE FIX

### The Problem (Critical)
Profile B stocks (float 5-10M) can reach SQS >= 5 via volume + gap alone (they always get float_score = 0). When SQS >= 5, they get Tier A risk ($750/trade) — same as Profile A micro-floats. This is wrong. Mid-float stocks don't deserve the same conviction sizing.

**Evidence from V6.1 backtest (166 sims):**
- Tier A Profile B trades: 2 active, both losers = **-$2,598**
- Tier B Profile B trades: 2 active (1W/1L) = **+$138**
- If all B trades were capped at $250: total B loss = **-$728** (saves $1,732)

### The Fix: Profile Risk Cap
In the dynamic sizing / tier assignment logic, add a profile-aware risk cap:

```python
# After calculating risk from SQS tier:
if profile == 'B':
    risk = min(risk, 250)  # Profile B never exceeds $250 risk
```

This is the simplest, safest fix. Profile B proved profitable at $250 risk (Tier B) and catastrophic at $750 (Tier A). Cap it.

**Where to implement:** `run_backtest_v4.py` (backtest) and `bot.py` / `trade_manager.py` (live). Look for where `sqs_tier` maps to risk amount.

### DO NOT change the SQS scoring formula itself — it's validated for Profile A. This is a profile-level override only.

---

## PART 2B: BASELINE BACKTEST — RUN AFTER RISK CAP FIX

After implementing the Profile B risk cap ($250 max), re-run the full extended backtest to establish a clean baseline.

### Step 1: Run the backtest
```bash
python3 run_backtest_v4_extended.py
```
This runs all 166 sims (Profile A + Profile B) across the full Oct 2025 — Feb 2026 date range.

### Step 2: Record BEFORE vs AFTER comparison
Capture these metrics split by profile:

| Metric | Profile A (before) | Profile A (after) | Profile B (before) | Profile B (after) |
|--------|-------------------|-------------------|--------------------|--------------------|  
| Total P&L | +$7,885 | ? | -$2,460 | ? |
| Win Rate | 50% (12W/12L) | ? | 25% (1W/3L) | ? |
| Max Drawdown | -$2,632 (8.8%) | ? | ? | ? |
| Avg Win | $1,217 (Tier A) | ? | ? | ? |
| Avg Loss | -$534 (Tier A) | ? | ? | ? |
| Combined P&L | +$5,425 | ? | — | — |
| Combined Max DD | -$5,355 (17.3%) | ? | — | — |

### Step 3: Validate expectations
- Profile A numbers should be **unchanged** (risk cap only affects B)
- Profile B P&L should improve from -$2,460 toward approximately -$728
- Combined max drawdown should shrink significantly (the -$5,355 was driven by B's $750 losses)
- If Profile A numbers changed at all, something went wrong — the risk cap touched code it shouldn't have

### Step 4: Save the results
Save the full output to `PROFILE_B_RISK_CAP_BASELINE.md` in the repo root. This is our new baseline for all future Profile B work.

**IMPORTANT:** The "before" numbers above are from the V6.1 run. If the codebase has evolved since then, the before numbers may shift slightly. That's fine — what matters is the A-to-B delta and the before-to-after delta on Profile B specifically.

---

## PART 3: PROFILE B — INVESTIGATION QUEUE

These are observation/analysis tasks. Do NOT implement fixes yet. Gather data first, then we decide together.

### Investigation 1: Classifier Sensitivity for Mid-Float
The classifier thresholds (VWAP distance 7%, range gate 10%, cascade 6 new highs + 3 pullbacks) were tuned for micro-float < 5M stocks. Mid-float stocks may behave differently.

**Task:** When running Profile B backtests, log:
- How often B stocks hit the VWAP gate vs A stocks
- How often B stocks hit the range gate vs A stocks  
- How often B stocks trigger cascade exit vs A stocks
- Average VWAP distance at entry for B vs A stocks

### Investigation 2: B-Gate Coverage Gap
The B-Gate (gap >= 14% AND pm_vol >= 10K) only applies to Tier B stocks (SQS = 4). Tier A Profile B stocks (SQS >= 5) bypass it entirely.

**Task:** Once the risk cap is in place, verify: does the B-gate now apply to all Profile B trades? (It should, since they're all Tier B after the cap.)

### Investigation 3: L2 Threshold Calibration for Live IB
The L2 thresholds (imbalance 0.65 bull, 0.30 bear, 30-bar warmup) were tuned on Databento MBP-10 historical data. Live IB data updates differently.

**Task:** Once IB is connected, run the bot in observation mode (paper, small size) and log:
- Average imbalance values from IB vs what Databento showed
- How often the hard gate fires
- Whether the 30-bar warmup is appropriate for IB's update frequency
- Any cases where L2 signals look wrong (bullish imbalance during price drops, etc.)

### Investigation 4: CRWG — The Repeat Offender
CRWG appears 7 times in Profile B data. It scored SQS=4 five times ($250 risk) and SQS=5 twice ($750 risk). The one time it traded at $750 risk, it lost $1,572.

**Task:** Track if CRWG continues to show up on Profile B after the risk cap fix. If it keeps losing at $250 risk too, we may need a symbol-level blacklist or a "repeat loser" penalty.

---

## PART 4: PRIORITY STACK (Updated)

1. ~~Fix wins/losses~~ → Profile A is performing well (+$7,885, 26.3%, 50% WR)
2. ~~Dynamic position scaling~~ → V6 dynamic sizing implemented
3. **[NOW] Profile B overhaul** → Risk cap fix, then investigation queue
4. **[NOW] IB Gateway hookup** → Config + smoke test + integration test
5. **[NEXT] Profile B classifier tuning** → Based on investigation data
6. **[SHELF] Profile C** → On hold until B is fixed

---

## PART 5: KEY RULES (DO NOT VIOLATE)

- Signal mode cascading exits — DO NOT suppress exits in signal mode (this is the bot's core edge)
- Profile A uses Alpaca ticks for backtesting; Profile B uses Databento ticks
- Starting account size is always $30K
- Dynamic sizing: 2.5% of equity, $250 floor, $1,500 ceiling, recalculate daily
- January 2026 was hot market, February 2026 was cold — sample from both to avoid bias
- Observation first — no knee-jerk fixes. Gather data, then decide.
- "I'm fine sacrificing those winners if it means way smaller losers"
