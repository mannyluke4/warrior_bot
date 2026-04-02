# DIRECTIVE: V3 Position Sync — Fix Phantom Position Problem

**Date:** April 1, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P0 — Must be included in the V3 hybrid build  
**Context:** This morning (April 1), V1 bot placed trades via Alpaca that FILLED on Alpaca's side, but the bot lost awareness of them. CC confirmed from the bot's perspective there were "no open trades" while the Alpaca dashboard showed active positions. User had to manually close positions on the Alpaca dashboard.

---

## The Problem

The bot submits an order to Alpaca, then either:
1. Doesn't wait long enough for the fill confirmation
2. Gets an error/timeout and assumes the order didn't fill
3. Crashes or restarts between order submission and fill verification
4. The fill event arrives but the bot's internal state doesn't update

In any of these cases, the bot thinks it has no position, but Alpaca has real shares. The bot then:
- Stops managing exits (no stop loss, no target, no trailing stop)
- May try to enter another trade on the same or different symbol
- Leaves the user holding unmanaged positions that can bleed money

This is the single most dangerous bug in an automated trading system.

---

## Required Fixes for V3

### Fix 1: Startup Position Reconciliation

**On every bot startup**, query Alpaca for ALL open positions and reconcile against internal state.

```python
def reconcile_positions_on_startup():
    """Check Alpaca for positions the bot doesn't know about."""
    positions = state.alpaca.get_all_positions()
    
    if not positions:
        print("  Position sync: No open positions on Alpaca. Clean start.", flush=True)
        return
    
    for pos in positions:
        symbol = pos.symbol
        qty = int(pos.qty)
        avg_entry = float(pos.avg_entry_price)
        unrealized_pnl = float(pos.unrealized_pl)
        market_value = float(pos.market_value)
        
        print(f"  ⚠️ ORPHAN POSITION FOUND: {symbol} qty={qty} "
              f"entry=${avg_entry:.2f} unrealized=${unrealized_pnl:+,.2f} "
              f"value=${market_value:,.2f}", flush=True)
        
        # Option A: Auto-adopt the position into bot's state
        # (so exit management kicks in)
        if state.open_position is None:
            state.open_position = {
                "symbol": symbol,
                "entry": avg_entry,
                "qty": qty,
                "r": avg_entry * 0.03,  # Estimate R as 3% of entry
                "stop": avg_entry * 0.97,  # Estimate stop at -3%
                "target": avg_entry * 1.06,  # Estimate 2R target at +6%
                "peak": avg_entry,
                "fill_confirmed": True,  # It's already filled
                "setup_type": "orphan_adopted",
                "window": "unknown",
            }
            print(f"  → Adopted {symbol} into bot state. Exit management active.", flush=True)
        else:
            # Bot already has a position — can't adopt a second one
            # EMERGENCY: close the orphan immediately
            print(f"  → Bot already has position in {state.open_position['symbol']}. "
                  f"CLOSING orphan {symbol}.", flush=True)
            close_orphan_position(symbol, qty)

# Call this in main() right after Alpaca client initialization:
reconcile_positions_on_startup()
```

### Fix 2: Fill Verification with Retry

After EVERY order submission, verify the fill. If verification fails, check again. If the order filled but the bot missed it, adopt the position.

```python
def submit_and_verify_entry(symbol, qty, limit_price):
    """Submit entry order and verify fill. Returns True if filled."""
    req = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY,
        type='limit',
        time_in_force=TimeInForce.DAY,
        limit_price=limit_price
    )
    
    try:
        order = state.alpaca.submit_order(req)
        order_id = order.id
        print(f"  ORDER SUBMITTED: {order_id} BUY {qty} {symbol} @ ${limit_price:.2f}", flush=True)
    except Exception as e:
        print(f"  ORDER FAILED: {e}", flush=True)
        return False
    
    # Wait for fill with timeout
    filled_price, filled_qty = wait_for_fill(order_id, timeout=15)
    
    if filled_price is not None:
        print(f"  FILLED: {symbol} {filled_qty} shares @ ${filled_price:.2f}", flush=True)
        # Update position with actual fill price
        state.open_position["entry"] = filled_price
        state.open_position["qty"] = filled_qty
        state.open_position["fill_confirmed"] = True
        # Recalculate stop/target based on actual fill
        r = state.open_position["r"]
        state.open_position["stop"] = filled_price - r
        state.open_position["target"] = filled_price + (r * SQ_TARGET_R)
        return True
    else:
        # Order didn't fill in time — but check one more time
        # (the order may have filled between our last check and cancel)
        try:
            final_check = state.alpaca.get_order_by_id(order_id)
            if final_check.status == 'filled':
                filled_price = float(final_check.filled_avg_price)
                filled_qty = int(final_check.filled_qty)
                print(f"  LATE FILL DETECTED: {symbol} {filled_qty} @ ${filled_price:.2f}", flush=True)
                state.open_position["entry"] = filled_price
                state.open_position["qty"] = filled_qty
                state.open_position["fill_confirmed"] = True
                return True
        except Exception:
            pass
        
        # Truly no fill — clean up
        print(f"  NO FILL: {symbol} order timed out / cancelled", flush=True)
        state.open_position = None
        return False
```

### Fix 3: Periodic Position Sync (Heartbeat)

Every 60 seconds during the trading session, verify that the bot's internal state matches Alpaca's actual positions.

```python
def periodic_position_sync():
    """Called every 60 seconds. Verifies bot state matches Alpaca reality."""
    try:
        positions = state.alpaca.get_all_positions()
    except Exception as e:
        print(f"  Position sync error: {e}", flush=True)
        return
    
    alpaca_symbols = {pos.symbol: pos for pos in positions}
    
    # Case 1: Bot thinks it has a position, but Alpaca doesn't
    if state.open_position and state.open_position.get("fill_confirmed"):
        bot_symbol = state.open_position["symbol"]
        if bot_symbol not in alpaca_symbols:
            print(f"  ⚠️ POSITION DESYNC: Bot thinks it holds {bot_symbol}, "
                  f"but Alpaca shows no position. Clearing bot state.", flush=True)
            # Position was likely closed manually or by Alpaca risk management
            state.open_position = None
    
    # Case 2: Alpaca has a position the bot doesn't know about
    if not state.open_position:
        for symbol, pos in alpaca_symbols.items():
            qty = int(pos.qty)
            avg_entry = float(pos.avg_entry_price)
            print(f"  ⚠️ ORPHAN DETECTED: Alpaca holds {symbol} qty={qty} "
                  f"entry=${avg_entry:.2f} — bot unaware. Adopting.", flush=True)
            state.open_position = {
                "symbol": symbol,
                "entry": avg_entry,
                "qty": qty,
                "r": avg_entry * 0.03,
                "stop": avg_entry * 0.97,
                "target": avg_entry * 1.06,
                "peak": avg_entry,
                "fill_confirmed": True,
                "setup_type": "orphan_adopted",
                "window": "unknown",
            }
            break  # Only adopt one (single-position bot)
    
    # Case 3: Bot and Alpaca both have a position — verify quantities match
    if state.open_position and state.open_position.get("fill_confirmed"):
        bot_symbol = state.open_position["symbol"]
        if bot_symbol in alpaca_symbols:
            alp_qty = int(alpaca_symbols[bot_symbol].qty)
            bot_qty = state.open_position["qty"]
            if alp_qty != bot_qty:
                print(f"  ⚠️ QTY MISMATCH: Bot thinks {bot_qty} shares, "
                      f"Alpaca shows {alp_qty}. Updating bot.", flush=True)
                state.open_position["qty"] = alp_qty
```

### Fix 4: Exit Order Verification

Same problem can happen on exits — bot sends a sell order, assumes it filled, clears the position, but the order didn't actually fill. Result: bot thinks it's flat, but it still holds shares.

```python
def submit_and_verify_exit(symbol, qty, limit_price, reason):
    """Submit exit order and verify fill."""
    req = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.SELL,
        type='limit',
        time_in_force=TimeInForce.DAY,
        limit_price=limit_price
    )
    
    try:
        order = state.alpaca.submit_order(req)
        order_id = order.id
    except Exception as e:
        print(f"  EXIT ORDER FAILED: {e} — EMERGENCY MARKET SELL", flush=True)
        # Fallback: market order
        try:
            from alpaca.trading.requests import MarketOrderRequest
            market_req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY
            )
            order = state.alpaca.submit_order(market_req)
            order_id = order.id
        except Exception as e2:
            print(f"  EMERGENCY MARKET SELL ALSO FAILED: {e2}", flush=True)
            print(f"  *** MANUAL INTERVENTION REQUIRED: {qty} {symbol} still held ***", flush=True)
            return False
    
    # Verify fill
    filled_price, filled_qty = wait_for_fill(order_id, timeout=15)
    
    if filled_price is not None:
        print(f"  EXIT FILLED: {symbol} {filled_qty} shares @ ${filled_price:.2f} ({reason})", flush=True)
        return True
    else:
        # Exit didn't fill — try market order as emergency
        print(f"  EXIT LIMIT DIDN'T FILL — emergency market sell", flush=True)
        try:
            from alpaca.trading.requests import MarketOrderRequest
            market_req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY
            )
            order = state.alpaca.submit_order(market_req)
            filled_price, filled_qty = wait_for_fill(order.id, timeout=10)
            if filled_price:
                print(f"  EMERGENCY EXIT FILLED: ${filled_price:.2f}", flush=True)
                return True
        except Exception as e:
            print(f"  *** ALL EXIT ATTEMPTS FAILED: {e} ***", flush=True)
            print(f"  *** MANUAL INTERVENTION REQUIRED ***", flush=True)
        return False
```

### Fix 5: Graceful Shutdown Position Check

When the bot shuts down (end of session, SIGTERM, etc.), verify positions are flat:

```python
import signal

def graceful_shutdown(signum, frame):
    """On shutdown, verify no orphan positions."""
    print("\n🛑 SHUTDOWN SIGNAL RECEIVED", flush=True)
    
    # Check for open positions
    try:
        positions = state.alpaca.get_all_positions()
        if positions:
            for pos in positions:
                print(f"  ⚠️ POSITION OPEN AT SHUTDOWN: {pos.symbol} "
                      f"qty={pos.qty} P&L=${float(pos.unrealized_pl):+,.2f}", flush=True)
            print("  *** POSITIONS LEFT OPEN — WILL NEED MANUAL MANAGEMENT ***", flush=True)
        else:
            print("  All positions flat. Clean shutdown.", flush=True)
    except Exception as e:
        print(f"  Could not check positions at shutdown: {e}", flush=True)
    
    sys.exit(0)

# In main():
signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGINT, graceful_shutdown)
```

---

## Summary

| Fix | What It Prevents |
|-----|-----------------|
| Startup reconciliation | Orphan positions from prior crash/restart |
| Fill verification with retry | Orders that fill but bot misses the confirmation |
| Periodic sync (60s heartbeat) | Drift between bot state and Alpaca reality |
| Exit order verification + market fallback | Failed exits leaving bot holding shares |
| Graceful shutdown check | End-of-day orphan awareness |

**All five fixes are REQUIRED in `bot_v3_hybrid.py`.** This is not optional. The phantom position problem is the highest-risk bug in any automated trading system — it means unmanaged real-money exposure.

---

## V1 Log Investigation

If possible, retrieve the V1 logs from the Mac Mini:
```bash
# On Mac Mini:
cat /Users/duffy/warrior_bot/logs/2026-04-01*.log | grep "ENTRY\|FILL\|ORDER\|submit\|error\|timeout\|position"
```

Push to `cowork_reports/2026-04-01_v1_phantom_position_investigation.md` for analysis. This will tell us exactly where V1's awareness broke — was it a timeout on the fill check? A crash between submit and verify? An error that was swallowed?
