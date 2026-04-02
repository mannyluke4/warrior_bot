# DIRECTIVE: V3 Hybrid Bot — IBKR Data + Alpaca Execution

**Date:** April 1, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P0 — Build tonight, must be ready for April 2 pre-market  
**Branch:** `v2-ibkr-migration`

---

## The Problem

The V2 IBKR bot has not taken a single trade in 8 days of live sessions. Not one. Today (April 1), RENX fired 4 PRIMED events, ELAB fired 7 PRIMED events, and zero ARMEDs. The PRIMED → ARMED transition is failing because by the time the volume explosion fires, the stock is already above the PM high — so the "level break" check finds no fresh level to break.

Meanwhile, V1 (Alpaca execution) ran alongside today and DID take trades. Alpaca order execution works. IBKR order execution has never been proven live.

The V2 strategy logic (squeeze detection, candle exits) is validated in backtesting (+$197K). The IBKR data feed (scanner, tick data) is validated against TradingView. What's NOT validated is whether IBKR can execute orders in the heat of the moment on these volatile small-caps.

## The Solution: V3 Hybrid

**Use IBKR for what it's proven at (data) and Alpaca for what it's proven at (execution).**

```
V3 Architecture:
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  IB Gateway  │────▶│  V3 Hybrid   │────▶│   Alpaca    │
│  (data only) │     │   Bot        │     │ (execution) │
│              │     │              │     │             │
│ - Scanner    │     │ - SQ V2      │     │ - Buy       │
│ - Tick data  │     │ - Candle     │     │ - Sell      │
│ - RTVolume   │     │   exits      │     │ - Paper     │
│ - L2 (later) │     │ - Position   │     │   account   │
│              │     │   sizing     │     │             │
└─────────────┘     └──────────────┘     └─────────────┘
```

V3 is `bot_v3_hybrid.py` — a new file. Does NOT modify `bot_ibkr.py` (V2) or `bot.py` (V1).

---

## What V3 Takes From Each Version

### From V2 (`bot_ibkr.py`) — The Data Layer
- IB Gateway connection via ib_insync (port 4002)
- `ibkr_scanner.py` — pre-market scanner using IBKR's `reqScannerSubscription`
- `reqMktData` with generic tick 233 (RTVolume) for tick-by-tick data
- `reqHistoricalData` for ADV/fundamentals
- Bar builder (1-min bars from tick stream)
- VWAP calculation from tick data
- The entire tick subscription and monitoring system

### From V2 — The Strategy Layer
- `squeeze_detector_v2.py` (or V1 via `WB_SQUEEZE_VERSION` switch)
- Candle pattern exits (topping wicky, bearish engulfing)
- Position sizing (2.5% risk, notional cap, probe sizing)
- Daily P&L tracking, max daily loss
- All env vars and configuration

### From V1 (`bot.py` / `trade_manager.py`) — The Execution Layer
- Alpaca `TradingClient` for order submission
- `LimitOrderRequest` for entries
- `LimitOrderRequest` for exits
- Position monitoring via `client.get_all_positions()`
- Order fill verification via `client.get_order(order_id)`
- The proven submit → verify → confirm flow from trade_manager.py

---

## Build Instructions

### Step 1: Create `bot_v3_hybrid.py`

Start from `bot_ibkr.py` as the base. Make these changes:

**1a. Add Alpaca imports and client initialization:**
```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# In main():
alpaca_client = TradingClient(
    os.getenv("APCA_API_KEY_ID"),
    os.getenv("APCA_API_SECRET_KEY"),
    paper=os.getenv("APCA_PAPER", "true").lower() == "true"
)
state.alpaca = alpaca_client
```

**1b. Replace IBKR order placement with Alpaca:**

In `enter_trade()`, replace:
```python
# OLD (IBKR):
contract = Stock(symbol, 'SMART', 'USD')
order = LimitOrder('BUY', qty, limit_price)
trade = state.ib.placeOrder(contract, order)
```

With:
```python
# NEW (Alpaca):
req = LimitOrderRequest(
    symbol=symbol,
    qty=qty,
    side=OrderSide.BUY,
    type='limit',
    time_in_force=TimeInForce.DAY,
    limit_price=limit_price
)
order = state.alpaca.submit_order(req)
print(f"  ALPACA ORDER: {order.id} BUY {qty} {symbol} @ ${limit_price:.2f}", flush=True)
```

**1c. Replace IBKR exit orders with Alpaca:**

In `exit_trade()`, replace:
```python
# OLD (IBKR):
order = LimitOrder('SELL', qty, limit_price)
state.ib.placeOrder(contract, order)
```

With:
```python
# NEW (Alpaca):
req = LimitOrderRequest(
    symbol=symbol,
    qty=qty,
    side=OrderSide.SELL,
    type='limit',
    time_in_force=TimeInForce.DAY,
    limit_price=limit_price
)
order = state.alpaca.submit_order(req)
print(f"  ALPACA ORDER: {order.id} SELL {qty} {symbol} @ ${limit_price:.2f}", flush=True)
```

**1d. Add fill verification from V1:**

After placing an order, verify the fill:
```python
import time

def wait_for_fill(order_id, timeout=15):
    """Wait for Alpaca order to fill, with timeout."""
    for _ in range(timeout * 2):  # Check every 0.5s
        order = state.alpaca.get_order_by_id(order_id)
        if order.status == 'filled':
            return float(order.filled_avg_price), int(order.filled_qty)
        if order.status in ('cancelled', 'expired', 'rejected'):
            return None, 0
        time.sleep(0.5)
    # Timeout — cancel the order
    state.alpaca.cancel_order_by_id(order_id)
    return None, 0
```

**1e. Keep ALL data feeds from IBKR:**

Do NOT change:
- `connect()` — still connects to IB Gateway on port 4002
- `subscribe_symbol()` — still uses `reqMktData(contract, '233', False, False)`
- `on_ticker_update()` — still processes IBKR tick data
- `on_bar_close_1m()` — still builds bars from IBKR ticks
- `scan_premarket_live()` — still uses IBKR scanner
- VWAP, EMA, squeeze detector — all unchanged

**1f. Get account equity from Alpaca instead of IBKR:**
```python
def get_account_equity():
    """Get current account equity from Alpaca."""
    account = state.alpaca.get_account()
    return float(account.equity)
```

### Step 2: Create `daily_run_v3.sh`

Copy from `daily_run.sh` with these changes:
- Set `WB_BOT_VERSION=3` (for logging)
- Add Alpaca env vars:
  ```bash
  export APCA_API_KEY_ID="<from .env>"
  export APCA_API_SECRET_KEY="<from .env>"
  export APCA_PAPER="true"
  ```
- Launch `python3 bot_v3_hybrid.py` instead of `python3 bot_ibkr.py`
- Still start IB Gateway via IBC (data feeds still need it)

### Step 3: Env Vars

V3 needs both sets of credentials in `.env`:

```bash
# IBKR (data only)
IBKR_PORT=4002
IBKR_CLIENT_ID=1

# Alpaca (execution)
APCA_API_KEY_ID=<existing key>
APCA_API_SECRET_KEY=<existing secret>
APCA_PAPER=true

# Strategy (same as V2)
WB_SQUEEZE_ENABLED=1
WB_SQUEEZE_VERSION=2    # Use V2 squeeze detector
WB_SQ_PARA_ENABLED=1
WB_CT_ENABLED=0          # CT still off
WB_MP_ENABLED=0
WB_MP_V2_ENABLED=0
```

---

## What V3 Does NOT Change

- `bot_ibkr.py` — untouched, can still run as V2
- `bot.py` — untouched, can still run as V1
- `squeeze_detector.py` — untouched
- `squeeze_detector_v2.py` — untouched
- `ibkr_scanner.py` — untouched
- `simulate.py` — untouched (backtests are unaffected)
- `trade_manager.py` — V3 does NOT use trade_manager.py. It handles orders directly via Alpaca's simple API.

---

## Known Alpaca Limitations to Handle

1. **Alpaca doesn't support pre-market orders before 7:00 AM ET** on the free plan. Premium plan (which Luke has) extends to 4:00 AM ET. Verify `time_in_force=TimeInForce.DAY` works for extended hours, or use `TimeInForce.GTC` if needed.

2. **Alpaca paper trading** uses IEX data (not SIP) for simulated fills. This means Alpaca's fill prices may differ slightly from IBKR's tick prices. The bot should use IBKR ticks for strategy decisions but expect Alpaca fills to be within ~$0.01-0.05 of the IBKR price.

3. **Position sync at startup:** On startup, check Alpaca for any open positions (from prior session or manual trades):
   ```python
   positions = state.alpaca.get_all_positions()
   for pos in positions:
       print(f"  EXISTING POSITION: {pos.symbol} qty={pos.qty} avg_entry=${pos.avg_entry_price}")
   ```

4. **Order routing:** Alpaca routes through Citadel/Virtu. For small-cap gappers with thin liquidity, fills may be slower than IBKR's direct-access routing. Monitor fill times in the logs.

---

## Testing Plan

1. **Tonight:** Build `bot_v3_hybrid.py`, verify it compiles and can connect to both IBKR and Alpaca
2. **Pre-market April 2:** Run V3 alongside V2 (different client IDs). V3 on Alpaca paper, V2 on IBKR paper.
3. **Compare:** Did V3 take trades that V2 missed? Were fills reasonable?

---

## Rollback

If V3 has issues:
- Switch `daily_run.sh` back to `bot_ibkr.py` (V2)
- Or switch to `bot.py` (V1) for pure Alpaca
- V3 is a new file — removing it breaks nothing

---

## The PRIMED → ARMED Gap (Root Cause Analysis)

While V3 solves the execution problem, here's what's happening with V2's zero trades:

RENX April 1: PRIMED at $2.82 (09:33 ET). PM_H was $2.41. The stock was ALREADY $0.41 above the PM high when PRIMED fired. The level break check looks for `bar.high > level` — but the bar that caused PRIMED is the SAME bar that broke the level. The detector requires PRIMED first, THEN level break on a SUBSEQUENT bar. By the time the next bar comes, the stock may have pulled back below the level.

**This is the fundamental architectural issue:** V2 requires volume explosion (PRIMED) and level break (ARMED) to happen on SEPARATE bars, in that order. But on fast-moving small-caps, they happen simultaneously — the volume explosion IS the level break.

The V2 intra-bar ARM feature (Option A from SQUEEZE_V2_DECISIONS.md) addresses this by checking level breaks on every tick while PRIMED. But even that may not help if PRIMED and level break happen in the same 1-minute bar.

**The real fix (for V2/V3):** Allow PRIMED + ARMED on the SAME bar if both conditions are met simultaneously. Check level break WITHIN the PRIMED transition:

```python
# In V2's on_bar_close_1m, after PRIMED fires:
if self._state == "PRIMED":
    # Check if this same bar also broke a level
    level_name, level_price = self._find_broken_level(bar.high)
    if level_name:
        self._try_arm(level_name, level_price, bar.close)
        # Now ARMED — tick trigger can fire on next tick
```

This should be added to `squeeze_detector_v2.py` as part of the V3 build.

---

*V3 = IBKR brain + Alpaca hands. Proven data + proven execution. Build tonight.*
