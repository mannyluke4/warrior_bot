# DIRECTIVE: Box Phase 3 — Ship Box Strategy to Live Bot

**Date:** April 3, 2026
**Author:** Cowork (Opus)
**For:** CC (Claude Code)
**Priority:** P1
**Depends on:** Phase 2B complete (midbox exit + Vol Sweet Spot filter confirmed: 75% WR, 5.07 PF, $74.45 avg/trade)

---

## What This Directive Covers

Wire the box strategy into `bot_v3_hybrid.py` so it runs live alongside momentum. Box trades during the afternoon (10:00 AM - 3:45 PM ET) while momentum trades the morning (7:00 AM - 10:00 AM ET). This is a PAPER TRADING deployment — we're validating live behavior before real capital.

---

## Critical Safety Rules

1. **`WB_BOX_ENABLED=0` by default.** The entire box system is gated. Nothing changes unless this is explicitly set to `1`.
2. **Box NEVER interferes with momentum.** If momentum has an open position, box cannot enter. Period. Momentum always has priority.
3. **Box has its own position slot.** The bot needs two position tracking slots: `state.open_position` (momentum, existing) and `state.box_position` (box, new). These are independent.
4. **Wait — ACTUALLY, one position at a time.** Alpaca paper account has limited buying power. For safety in paper trading, we enforce: if EITHER momentum or box has an open position, the other cannot enter. Later (Phase 5) we can allow simultaneous positions when we're on a real account with sufficient capital. Gate this with `WB_BOX_SIMULTANEOUS=0` (default OFF).
5. **Box has its own daily loss cap.** `WB_BOX_MAX_LOSS_SESSION=500` — tracked independently from momentum's daily loss tracking.
6. **No box entries on Fridays.** `WB_BOX_SKIP_FRIDAY=1` — confirmed negative EV from backtest.
7. **Hard close at 3:45 PM.** Non-negotiable. Box never holds into close or overnight.

---

## Architecture Changes

### 1. New Imports in bot_v3_hybrid.py

```python
# Box strategy (gated)
BOX_ENABLED = os.getenv("WB_BOX_ENABLED", "0") == "1"
BOX_SIMULTANEOUS = os.getenv("WB_BOX_SIMULTANEOUS", "0") == "1"

if BOX_ENABLED:
    from box_scanner import scan_box_candidates
    from box_strategy import BoxStrategyEngine
```

### 2. New State Fields in BotState

```python
class BotState:
    def __init__(self):
        # ... existing fields ...

        # Box strategy state
        self.box_position: dict = None        # {symbol, qty, entry, engine, ...}
        self.box_engine: BoxStrategyEngine = None  # active box engine
        self.box_candidates: list[dict] = []  # current box scanner candidates
        self.box_active_symbol: str = None    # symbol we're subscribed to for box
        self.box_bar_builder_1m: TradeBarBuilder = None  # separate bar builder for box
        self.box_daily_pnl: float = 0.0       # box-specific daily P&L tracking
        self.box_daily_trades: int = 0
        self.box_closed_trades: list[dict] = []
        self.last_box_scan_time: datetime = None
```

### 3. Trading Window Restructure

The current dead zone (12:00-16:00) needs to become active for box trading. Change the window handling:

```python
# Current: TRADING_WINDOWS = "07:00-12:00,16:00-20:00"
# New: the MOMENTUM windows stay the same, but the bot stays awake for box

MOMENTUM_WINDOWS_STR = os.getenv("WB_MOMENTUM_WINDOWS", "07:00-12:00,16:00-20:00")
BOX_WINDOW_START = _parse_time(os.getenv("WB_BOX_START_ET", "10:00"))
BOX_WINDOW_END = _parse_time(os.getenv("WB_BOX_HARD_CLOSE_ET", "15:45"))
BOX_LAST_ENTRY = _parse_time(os.getenv("WB_BOX_LAST_ENTRY_ET", "14:30"))
```

**IMPORTANT:** The bot's main loop currently sleeps 30s during dead zone (`ib.sleep(30 if state.in_dead_zone else 1)`). With box enabled, the "dead zone" concept changes — the bot is only truly dead after BOTH momentum and box windows have closed. During 12:00-15:45, momentum is asleep but box is active.

New helper functions:

```python
def in_momentum_window(now_et: datetime) -> bool:
    """True if we're in a momentum trading window."""
    t = now_et.time()
    return any(start <= t <= end for start, end in MOMENTUM_WINDOWS)

def in_box_window(now_et: datetime) -> bool:
    """True if box is enabled and we're in the box window."""
    if not BOX_ENABLED:
        return False
    t = now_et.time()
    return BOX_WINDOW_START <= t <= BOX_WINDOW_END

def in_any_active_window(now_et: datetime) -> bool:
    """True if either momentum or box is active."""
    return in_momentum_window(now_et) or in_box_window(now_et)

def past_all_windows(now_et: datetime) -> bool:
    """True if all trading is done for the day."""
    t = now_et.time()
    # Past the last momentum window AND past box window
    past_momentum = all(t > end for _, end in MOMENTUM_WINDOWS)
    past_box = (not BOX_ENABLED) or (t > BOX_WINDOW_END)
    return past_momentum and past_box
```

### 4. Box Scanner Integration

The box scanner runs at configurable checkpoints. Unlike momentum's scanner (which runs pre-market + during session), the box scanner runs at 10:00 AM and optionally at 11:00 AM.

```python
BOX_SCAN_CHECKPOINTS = [
    time_cls(10, 0),
    time_cls(11, 0),
]

def run_box_scanner():
    """Run box scanner at checkpoint times."""
    if not BOX_ENABLED:
        return
    now = datetime.now(ET)

    # Skip Fridays
    if now.weekday() == 4 and os.getenv("WB_BOX_SKIP_FRIDAY", "1") == "1":
        return

    # Check if it's time for a scan
    if state.last_box_scan_time:
        # Only scan at designated checkpoints
        elapsed = (now - state.last_box_scan_time).total_seconds()
        if elapsed < 300:  # Don't re-scan within 5 minutes
            return

    current_time = now.time()
    should_scan = False
    for checkpoint in BOX_SCAN_CHECKPOINTS:
        # Scan if we're within 2 minutes of a checkpoint and haven't scanned recently
        if abs((now.replace(hour=checkpoint.hour, minute=checkpoint.minute, second=0) - now).total_seconds()) < 120:
            should_scan = True
            break

    if not should_scan:
        return

    print(f"\n📦 Box scanner running at {now.strftime('%H:%M')} ET...", flush=True)
    try:
        candidates = scan_box_candidates(state.ib)

        # Apply Vol Sweet Spot filters
        filtered = []
        for c in candidates:
            rp = c.get("range_pct", 0)
            total_tests = c.get("high_tests", 0) + c.get("low_tests", 0)
            price = c.get("price", 0)
            adr_util = c.get("adr_util_today", 999)

            if rp < 2.0 or rp > 6.0:
                continue
            if total_tests < 5:
                continue
            if price < 15.0:
                continue
            if adr_util > 0.8:
                continue

            filtered.append(c)

        state.box_candidates = sorted(filtered, key=lambda x: x.get("box_score", 0), reverse=True)
        state.last_box_scan_time = now

        print(f"  📦 Box candidates: {len(state.box_candidates)} passed Vol Sweet Spot filter "
              f"(from {len(candidates)} raw)", flush=True)
        for c in state.box_candidates[:5]:
            print(f"    {c['symbol']}: score={c['box_score']:.1f}, range={c['range_pct']:.1f}%, "
                  f"tests={c['high_tests']}H/{c['low_tests']}L, price=${c['price']:.2f}", flush=True)
    except Exception as e:
        print(f"  📦 Box scanner error: {e}", flush=True)
        traceback.print_exc()
```

### 5. Box Symbol Subscription

When the box scanner finds candidates, subscribe to the top one (highest box_score) for tick/bar data. If a box trade exits and the candidate is invalidated, move to the next candidate.

```python
def subscribe_box_symbol(symbol: str):
    """Subscribe to a box candidate for 1m bar data via IBKR."""
    if symbol in state.active_symbols:
        # Already subscribed (maybe momentum is watching it too — unlikely but possible)
        return

    contract = Stock(symbol, "SMART", "USD")
    state.ib.qualifyContracts(contract)
    ticker = state.ib.reqMktData(contract, '233', False, False)

    state.contracts[symbol] = contract
    state.tickers[symbol] = ticker
    state.active_symbols.add(symbol)
    state.box_active_symbol = symbol
    state.tick_counts[symbol] = 0

    print(f"  📦 Subscribed to {symbol} for box trading", flush=True)
```

### 6. Box Bar Processing

Box needs its own 1m bar builder (separate from momentum's). Box does NOT need 10s bars — it operates on 1m bars only.

```python
def on_box_bar_close_1m(bar):
    """Process 1-minute bar for box strategy."""
    if not BOX_ENABLED or not state.box_engine:
        return
    if bar.symbol != state.box_active_symbol:
        return

    now = datetime.now(ET)

    # Feed bar to box engine
    result = state.box_engine.on_bar(bar)

    if result is None:
        # Engine might have opened a new trade internally
        if state.box_engine.active_trade and not state.box_position:
            # Box engine signaled an entry
            trade = state.box_engine.active_trade
            _enter_box_trade(bar.symbol, trade)
    elif result:
        # Exit signal
        if state.box_position:
            _exit_box_trade(bar.symbol, state.box_engine.active_trade, result)
```

**CRITICAL:** The box bar builder must be SEPARATE from the momentum bar builder. Momentum bar builder feeds `on_bar_close_1m` which runs squeeze/MP detection. Box bar builder feeds `on_box_bar_close_1m` which runs box strategy. They must not cross-contaminate.

```python
# In main(), after existing bar builder init:
if BOX_ENABLED:
    state.box_bar_builder_1m = TradeBarBuilder(
        on_bar_close=on_box_bar_close_1m, et_tz=ET, interval_seconds=60
    )
```

### 7. Box Trade Entry via Alpaca

```python
def _enter_box_trade(symbol: str, trade_state):
    """Enter a box trade via Alpaca."""
    # Safety checks
    if not BOX_SIMULTANEOUS and state.open_position:
        print(f"  📦 Box entry blocked — momentum position open ({state.open_position['symbol']})", flush=True)
        return
    if state.box_position:
        print(f"  📦 Box entry blocked — box position already open", flush=True)
        return
    if state.box_daily_pnl <= -float(os.getenv("WB_BOX_MAX_LOSS_SESSION", "500")):
        print(f"  📦 Box entry blocked — session loss cap hit (${state.box_daily_pnl:.2f})", flush=True)
        return

    entry_price = trade_state.entry_price
    shares = trade_state.shares
    notional = entry_price * shares

    print(f"\n📦 BOX ENTRY: {symbol} {shares} shares @ ${entry_price:.2f} "
          f"(notional ${notional:,.0f})", flush=True)
    print(f"  Box: ${state.box_engine.box_bottom:.2f} - ${state.box_engine.box_top:.2f} "
          f"(range ${state.box_engine.box_range:.2f})", flush=True)
    print(f"  Stop: ${state.box_engine.hard_stop_price:.2f}", flush=True)

    try:
        order = LimitOrderRequest(
            symbol=symbol,
            qty=shares,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=round(entry_price + 0.02, 2),  # Slight buffer for fill
        )
        result = state.alpaca.submit_order(order)

        state.box_position = {
            "symbol": symbol,
            "qty": shares,
            "entry": entry_price,
            "order_id": result.id,
            "fill_confirmed": False,
            "setup_type": "box",
            "engine": state.box_engine,
        }
        print(f"  📦 Order submitted: {result.id}", flush=True)
    except Exception as e:
        print(f"  📦 BOX ORDER FAILED: {e}", flush=True)
```

### 8. Box Trade Exit via Alpaca

```python
def _exit_box_trade(symbol: str, trade_state, reason: str):
    """Exit a box trade via Alpaca."""
    if not state.box_position or state.box_position["symbol"] != symbol:
        return

    qty = state.box_position["qty"]
    exit_price = trade_state.exit_price if trade_state else 0
    pnl = (exit_price - state.box_position["entry"]) * qty if exit_price else 0

    print(f"\n📦 BOX EXIT: {symbol} {qty} shares @ ${exit_price:.2f} "
          f"reason={reason} P&L=${pnl:+,.2f}", flush=True)

    try:
        order = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            limit_price=round(exit_price - 0.02, 2),  # Slight buffer for fill
        )
        state.alpaca.submit_order(order)
    except Exception as e:
        print(f"  📦 EXIT ORDER FAILED: {e} — attempting market order", flush=True)
        try:
            from alpaca.trading.requests import MarketOrderRequest
            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            state.alpaca.submit_order(order)
        except Exception as e2:
            print(f"  📦 MARKET ORDER ALSO FAILED: {e2} — POSITION LEFT OPEN!", flush=True)
            return

    state.box_daily_pnl += pnl
    state.box_daily_trades += 1
    state.box_closed_trades.append({
        "symbol": symbol,
        "setup_type": "box",
        "reason": reason,
        "pnl": pnl,
        "entry": state.box_position["entry"],
        "exit": exit_price,
    })
    state.box_position = None
```

### 9. Tick Routing

In `_process_ticker()`, ticks for box symbols must be routed to the box bar builder in addition to the momentum bar builder (if applicable).

```python
def _process_ticker(ticker):
    # ... existing tick processing ...

    # Route to box bar builder if this is a box symbol
    if BOX_ENABLED and state.box_bar_builder_1m and symbol == state.box_active_symbol:
        state.box_bar_builder_1m.on_tick(symbol, price, size, tick_time)
```

**IMPORTANT:** If the symbol happens to be in BOTH the momentum scanner and box scanner (unlikely — different universes, but possible), ticks route to BOTH bar builders. They're independent state machines, this is fine.

### 10. Main Loop Changes

The main loop needs to:
- Run box scanner at checkpoints
- Subscribe to box candidates
- Keep the bot awake during box window (no more sleeping during 12:00-15:45)
- Force-close box positions at 3:45 PM
- Include box in the heartbeat log

```python
# In main loop:
while True:
    now = datetime.now(ET)

    if past_all_windows(now):
        break

    momentum_active = in_momentum_window(now)
    box_active = in_box_window(now) and BOX_ENABLED
    any_active = momentum_active or box_active

    if any_active:
        # Existing momentum logic (scanner, poll_watchlist, etc.)
        if momentum_active:
            run_scanner()
            poll_watchlist()
            check_halts()
            audit_tick_health()
            periodic_position_sync()

        # Box logic
        if box_active:
            run_box_scanner()

            # If we have box candidates but no box engine, set up the top candidate
            if state.box_candidates and not state.box_engine and not state.box_position:
                top = state.box_candidates[0]
                subscribe_box_symbol(top["symbol"])
                state.box_engine = BoxStrategyEngine(top, exit_variant="midbox")
                print(f"  📦 Box engine initialized: {top['symbol']} "
                      f"(score {top['box_score']:.1f})", flush=True)

            # Force close box position at 3:45 PM
            if now.time() >= BOX_WINDOW_END and state.box_position:
                sym = state.box_position["symbol"]
                ticker = state.tickers.get(sym)
                if ticker and ticker.last and not math.isnan(ticker.last):
                    _exit_box_trade(sym, state.box_engine.active_trade if state.box_engine else None, "time_stop")
                    state.box_engine = None

    # Dead zone: only when NEITHER is active
    if not any_active:
        if not state.in_dead_zone:
            state.in_dead_zone = True
            # ... existing dead zone entry logic ...

    # Sleep: 1s if anything active, 30s if fully dead
    ib.sleep(1 if any_active else 30)
```

### 11. Graceful Shutdown

Add box position handling to the shutdown sequence:

```python
def graceful_shutdown(signum, frame):
    # ... existing momentum position warning ...

    # Also check box position
    if state.box_position:
        sym = state.box_position["symbol"]
        print(f"  ⚠️ BOX POSITION OPEN AT SHUTDOWN: {sym} "
              f"qty={state.box_position['qty']}", flush=True)
```

And in the `finally` block:
```python
finally:
    # Close momentum position
    if state.open_position:
        # ... existing ...

    # Close box position
    if state.box_position:
        sym = state.box_position["symbol"]
        ticker = state.tickers.get(sym)
        if ticker and ticker.last:
            _exit_box_trade(sym, state.box_engine.active_trade if state.box_engine else None, "shutdown")
```

### 12. Session Summary

Update the summary at end of day:

```python
print(f"  Momentum Trades: {state.daily_trades}")
print(f"  Momentum P&L: ${state.daily_pnl:+,.0f}")
if BOX_ENABLED:
    print(f"  Box Trades: {state.box_daily_trades}")
    print(f"  Box P&L: ${state.box_daily_pnl:+,.2f}")
    for t in state.box_closed_trades:
        print(f"    📦 {t['symbol']} box {t['reason']}: ${t['pnl']:+,.2f}")
print(f"  COMBINED P&L: ${state.daily_pnl + state.box_daily_pnl:+,.2f}")
```

---

## Vol Sweet Spot Filter Config (hardened from Phase 2B)

These are the backtest-proven filter values. Set them as env var defaults:

```bash
# === Box Strategy (ALL OFF by default) ===
WB_BOX_ENABLED=0
WB_BOX_SIMULTANEOUS=0              # Don't allow box + momentum positions simultaneously (paper safety)
WB_BOX_SKIP_FRIDAY=1               # Fridays are negative EV

# === Box Scanner Filters (Vol Sweet Spot) ===
WB_BOX_MIN_RANGE_PCT=2.0
WB_BOX_MAX_RANGE_PCT=6.0
WB_BOX_MIN_TOTAL_TESTS=5           # NEW env var: high_tests + low_tests >= 5
WB_BOX_MIN_PRICE=15.00
WB_BOX_MAX_ADR_UTIL=0.80

# === Box Strategy (midbox exit) ===
WB_BOX_MID_EXIT_ENABLED=1          # Use midbox target (Phase 2B winner)
WB_BOX_BUY_ZONE_PCT=25
WB_BOX_SELL_ZONE_PCT=25
WB_BOX_RSI_OVERSOLD=35
WB_BOX_RSI_PERIOD=14
WB_BOX_STOP_PAD_PCT=0.5
WB_BOX_TRAIL_PCT=30
WB_BOX_TRAIL_ACTIVATION_PCT=50
WB_BOX_BREAKOUT_INVALIDATE_PCT=0.5
WB_BOX_MAX_NOTIONAL=50000
WB_BOX_MAX_LOSS_SESSION=500
WB_BOX_MAX_ENTRIES_PER_STOCK=2
WB_BOX_MAX_RISK_PER_TRADE=200

# === Box Time Windows ===
WB_BOX_START_ET=10:00
WB_BOX_LAST_ENTRY_ET=14:30
WB_BOX_HARD_CLOSE_ET=15:45
WB_BOX_SCAN_CHECKPOINTS=10:00,11:00
```

---

## Handoff Rules (Momentum ↔ Box)

These rules prevent the two strategies from stepping on each other:

1. **10:00 AM:** Box scanner activates. If momentum has an open position, box waits. Box engine initializes but cannot enter until the position slot is free.

2. **Momentum closes after 10:00 AM:** Box can now enter if it has a candidate in the buy zone. The position slot is free.

3. **Box has a position, momentum wants to enter:** This can happen if a momentum scanner catchup triggers between 10:00-12:00. With `WB_BOX_SIMULTANEOUS=0`: momentum is BLOCKED. Box has the slot. Momentum must wait. This is the safe default — momentum is more profitable per-trade, but we don't want to exit a winning box trade to chase a momentum entry. With `WB_BOX_SIMULTANEOUS=1` (future): both can coexist. Requires sufficient account capital.

4. **12:00 PM:** Momentum window ends. If momentum has an open position, the existing window-close logic exits it. Box continues.

5. **3:45 PM:** Box hard close. All box positions exit. Bot enters true dead zone until 4:00 PM evening window (if enabled).

---

## BoxStrategyEngine Modifications

The existing `BoxStrategyEngine` was built for backtesting (processes bars sequentially). For live use, it needs one adaptation: instead of computing position size internally, it should signal intent and let the bot handle Alpaca order submission.

Add a method to check if the engine wants to enter (without actually creating the trade):

```python
def wants_entry(self) -> Optional[dict]:
    """Returns entry signal dict if conditions are met, else None.
    Does NOT open the trade internally — the bot handles execution."""
    # This replaces the internal _open_trade() call for live mode
    pass

def confirm_entry(self, entry_price: float, shares: int):
    """Bot calls this after Alpaca fill confirmed to sync engine state."""
    pass

def confirm_exit(self, exit_price: float):
    """Bot calls this after Alpaca exit fill confirmed."""
    pass
```

Alternatively, the simpler approach: let the engine manage its own state as it does in backtesting, and have the bot read `engine.active_trade` to know when entries/exits happen. The bot then executes on Alpaca and the engine's internal P&L tracking serves as a shadow ledger. **Use this simpler approach for Phase 3.**

---

## Build Steps

1. `git pull`
2. Add all new env vars to `.env` file (commented out, `WB_BOX_ENABLED=0`)
3. Modify `bot_v3_hybrid.py`:
   - Add box imports and gates
   - Add BotState box fields
   - Add helper functions (in_momentum_window, in_box_window, in_any_active_window)
   - Update past_all_windows to account for box window
   - Add run_box_scanner(), subscribe_box_symbol()
   - Add on_box_bar_close_1m(), _enter_box_trade(), _exit_box_trade()
   - Update _process_ticker() to route to box bar builder
   - Update main loop: box scanner, box engine init, force close, dead zone logic
   - Update graceful_shutdown and finally block
   - Update session summary
4. Test with `WB_BOX_ENABLED=0` — verify existing momentum behavior is UNCHANGED (regression)
5. Test with `WB_BOX_ENABLED=1` — verify box scanner runs at 10 AM, candidates appear, engine initializes
6. Run regression: VERO +$15,692, ROLR +$6,444 (these are momentum-only, must not change)
7. `git push`
8. **STOP** — push and stop. We'll do paper trading validation manually.

---

## What NOT to Do

- Do NOT change any existing momentum logic — box is purely additive
- Do NOT allow box entries during momentum window (7:00-10:00) — box is afternoon only
- Do NOT use Alpaca for any data — IBKR for all market data, Alpaca for execution only
- Do NOT enable `WB_BOX_SIMULTANEOUS` by default — paper account capital constraint
- Do NOT skip the `WB_BOX_ENABLED=0` regression — butterfly effects are real
- Do NOT modify box_strategy.py's core logic — it's backtest-proven. Only add the live integration hooks if needed.
- Do NOT hold box positions past 3:45 PM under ANY circumstances
- Do NOT allow box to trade before 10:00 AM — that's momentum time
