# DIRECTIVE: V2 Comprehensive System Fix — Everything That's Broken and How to Fix It

**Date:** 2026-03-28  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P0 — Must be fixed before Monday market open  
**Branch:** `v2-ibkr-migration`

---

## Executive Summary

After a full code audit of bot_ibkr.py (955 lines), ibkr_scanner.py (469 lines), ibkr_tick_fetcher.py (233 lines), daily_run.sh (150 lines), the March 27 logs, the ONCO/ARTL forensic report, and extensive research into IBKR API best practices — I found **13 distinct issues**, organized into 4 severity tiers. CC's infrastructure directive (DIRECTIVE_IBKR_INFRASTRUCTURE_FIX.md) covers some of these but misses several critical ones.

**The core problem:** The bot ran the WRONG CODE on March 27 morning. The log proves it: `daily_run.sh` was still using port 7497 and TWS, not the Gateway/4002 code that was pushed. `git pull` returned "Already up to date" because CC hadn't merged the Gateway changes to the remote branch before the 2:00 AM cron fired.

**The deeper problem:** Even if Gateway had started, the tick data pipeline has a fundamental architecture issue — `reqMktData` returns aggregated snapshots (~250ms), not individual trade prints. The bot's `on_ticker_update` processes `ticker.last` as if it's a trade-by-trade feed, but it's actually getting the last price from a batched snapshot. For thin pre-market stocks, this can mean minutes between updates.

---

## TIER 1: SHOW-STOPPERS (Must fix before Monday)

### Issue 1: Stale Code on Mac Mini — The Root Cause of March 27

**Evidence:** `logs/2026-03-27_daily.log` line 11: `"Waiting for TWS to accept connections on port 7497..."`. The pushed `daily_run.sh` uses port 4002 and Gateway. The Mac Mini ran old code.

**Root cause:** The git pull at 2:00 AM said "Already up to date" — meaning the Gateway switch commits hadn't been pushed to `v2-ibkr-migration` before the cron fired, OR the local working tree had uncommitted changes blocking the pull.

**Fix:**
1. Manually SSH/VNC into Mac Mini and verify the current state:
   ```bash
   cd ~/warrior_bot_v2
   git status
   git log --oneline -5
   cat daily_run.sh | grep -E "port|7497|4002|gateway|tws"
   ```
2. Force-pull the latest:
   ```bash
   git fetch origin v2-ibkr-migration
   git reset --hard origin/v2-ibkr-migration
   ```
3. Add a version check at the TOP of `daily_run.sh` that logs the actual file content:
   ```bash
   echo "daily_run.sh hash: $(md5 -q ~/warrior_bot_v2/daily_run.sh)"
   echo "bot_ibkr.py hash: $(md5 -q ~/warrior_bot_v2/bot_ibkr.py)"
   ```
   This proves which code actually ran.

### Issue 2: `reqMktData` Is NOT Tick-by-Tick — Architecture Mismatch

**The problem:** `reqMktData` returns aggregated market data snapshots every ~250ms. It does NOT deliver every individual trade print. The `ticker.last` field holds the last traded price at the time of the snapshot, and `ticker.lastSize` holds the size of the most recent trade print in that snapshot. Between snapshots, multiple trades can occur and the bot will only see the final one.

This is documented by IBKR: _"Streaming market data values... is not tick-by-tick but consists of aggregate snapshots taken several times per second."_ ([IBKR API docs](https://interactivebrokers.github.io/tws-api/md_request.html))

For liquid stocks, this is fine — you get multiple updates per second. For thin pre-market small-caps (ONCO at 7 AM with maybe 1 trade every 10-30 seconds), you might get one snapshot update per minute or less, because IBKR only sends updates when something changes.

**Current code (bot_ibkr.py line 189):**
```python
ticker = state.ib.reqMktData(contract, '', False, False)
```

The empty `genericTickList` parameter means we're NOT requesting RTVolume (generic tick 233), which provides Time & Sales data including the actual trade price, size, and VWAP for every trade.

**Fix — Add RTVolume (Generic Tick 233):**
```python
# Request streaming data WITH RTVolume for Time & Sales
ticker = state.ib.reqMktData(contract, '233', False, False)
```

Generic tick 233 (RTVolume) returns a semicolon-delimited string with: last trade price, last trade size, trade time, total volume, VWAP, and whether the trade was from a single market maker. This is the closest thing to tick-by-tick data available through `reqMktData`.

To process RTVolume, add handling in `_process_ticker`:
```python
def _process_ticker(ticker):
    contract = ticker.contract
    if not contract:
        return
    symbol = contract.symbol

    # Process RTVolume ticks (Time & Sales, every trade print)
    if hasattr(ticker, 'rtVolume') and ticker.rtVolume:
        # RTVolume format: "price;size;time;totalVolume;vwap;single"
        # This fires for every trade print, not just snapshots
        pass  # rtVolume is parsed automatically by ib_insync into ticker fields

    # Existing processing...
    price = ticker.last
    # ... (rest of existing code)
```

**ALSO consider `reqTickByTickData`** for the active trading symbol (the one we're actually in a position on or about to enter). This gives true tick-by-tick data but is limited to 1 subscription per connection for paper accounts. Use it for the HOT symbol only:
```python
# When entering a position or when SQ is ARMED:
ticker = state.ib.reqTickByTickData(contract, 'AllLast')
# ticker.tickByTicks will contain every individual trade
```

### Issue 3: Scanner Cancels Market Data Subscriptions It Just Created

**The problem (ibkr_scanner.py line 133-155):**
```python
ticker = ib.reqMktData(contract, '', False, False)
ib.sleep(1)
# ... get price, volume, gap_pct ...
ib.cancelMktData(contract)  # <-- CANCELS IT!
```

The scanner subscribes to each candidate to get price/volume data, then CANCELS the subscription. But `bot_ibkr.py` then calls `subscribe_symbol()` which calls `reqMktData` again. This double-subscribe-cancel-resubscribe pattern can confuse IBKR's data routing, especially if pacing violations occur (>50 requests/second causes disconnects).

**Fix:** The scanner should use snapshot mode (one-time data request) instead of subscribing and canceling:
```python
# In scan_premarket_live(), change:
ticker = ib.reqMktData(contract, '', True, False)  # snapshot=True
ib.sleep(2)  # Snapshots need a bit more time
# ... get data ...
# NO NEED to cancel — snapshot auto-completes
```

Or even better, use `ib.reqTickers(*contracts)` which is specifically designed for getting snapshots of multiple contracts efficiently:
```python
contracts = [Stock(r.contractDetails.contract.symbol, 'SMART', 'USD') for r in results]
ib.qualifyContracts(*contracts)
tickers = ib.reqTickers(*contracts)
# All data available immediately
```

### Issue 4: `on_ticker_update` Uses `ticker.last` Which Can Be NaN for Long Periods

**The problem (bot_ibkr.py line 678):**
```python
price = ticker.last
if price is None or price <= 0 or math.isnan(price):
    return
```

For thin pre-market stocks, `ticker.last` can remain NaN for extended periods after subscription because no trades have occurred since subscribing. The bot silently drops these updates and never processes them.

Meanwhile, `ticker.bid` and `ticker.ask` may have valid values — there could be a live market with bid/ask spread but no actual trades. The bot misses this entirely.

**Fix:** Fall back through price sources:
```python
# Get the best available price
price = None
for attr in ('last', 'close', 'bid', 'ask'):
    p = getattr(ticker, attr, None)
    if p is not None and not math.isnan(p) and p > 0:
        price = p
        break

if price is None:
    return

# BUT: only feed to bar builder and trigger checks on TRADE prices (last),
# not bid/ask. Use bid/ask for health monitoring only.
is_trade = ticker.last is not None and not math.isnan(ticker.last) and ticker.last > 0
if is_trade:
    # Feed to bar builder, check triggers, manage exits
    ...
else:
    # Just update health monitoring
    state.last_tick_price[symbol] = price
    state.last_tick_time[symbol] = ts
```

### Issue 5: Entry Price Uses Limit Above Trigger — But Fill Is Not Verified

**The problem (bot_ibkr.py line 469-493):**
```python
limit_price = round(entry + 0.02, 2)
order = LimitOrder('BUY', qty, limit_price)
trade = state.ib.placeOrder(contract, order)

state.open_position = {
    "entry": limit_price,  # <-- ASSUMES fill at limit_price
    # ...
}
```

The bot records `limit_price` as the entry, but the actual fill could be at any price up to the limit. For a $5 stock, $0.02 above trigger is fine. But the position tracking uses the limit price, not the actual fill price. This means:
- P&L calculations are wrong (off by up to $0.02/share × qty)
- Stop/target levels computed from entry are slightly wrong
- If the order doesn't fill at all (price gapped past limit), the bot thinks it's in a position but has no actual shares

**Fix:** Register a fill callback and update the position with the actual fill price:
```python
def on_order_filled(trade, fill):
    """Update position with actual fill price."""
    if state.open_position and state.open_position.get('order_id') == trade.order.orderId:
        actual_price = fill.execution.price
        actual_qty = fill.execution.shares
        state.open_position['entry'] = actual_price
        state.open_position['qty'] = int(actual_qty)
        # Recalculate stop/target based on actual fill
        r = state.open_position['r']
        state.open_position['stop'] = actual_price - r
        print(f"  FILL: {trade.contract.symbol} @ ${actual_price:.4f} qty={actual_qty}", flush=True)

# In main(), after connecting:
ib.execDetailsEvent += on_order_filled
# Or use the trade object's fill event:
# trade.fillEvent += on_fill
```

Also add a timeout: if the order isn't filled within 10 seconds, cancel it and clear the pending position:
```python
# After placing order:
state.pending_order = {
    'trade': trade,
    'placed_time': datetime.now(ET),
    'timeout_seconds': 10,
}
# In the main loop or a separate check:
if state.pending_order:
    elapsed = (datetime.now(ET) - state.pending_order['placed_time']).total_seconds()
    if elapsed > state.pending_order['timeout_seconds']:
        state.ib.cancelOrder(state.pending_order['trade'].order)
        state.open_position = None
        state.pending_order = None
        print("  ORDER TIMEOUT: Entry order cancelled", flush=True)
```

---

## TIER 2: CRITICAL (Fix before Monday if possible)

### Issue 6: Exit Orders Also Not Fill-Verified

**The problem (bot_ibkr.py line 588-593):**
```python
limit_price = round(price - 0.03, 2)
order = LimitOrder('SELL', qty, limit_price)
state.ib.placeOrder(contract, order)
```

Same problem as entry — the exit assumes it fills at `price`, but the order is a limit at `price - $0.03`. If the stock is crashing fast, the marketable limit might not fill. The bot records the P&L as if the exit happened, but the shares might still be held.

**Fix:** Add fill verification for exits too. But more importantly, for exits use a wider marketable limit or a market order during RTH:
```python
# For urgent exits (stop hit, max loss), use aggressive pricing:
if reason in ('sq_stop_hit', 'sq_dollar_loss_cap', 'sq_max_loss_hit'):
    # Very aggressive limit to simulate market order
    limit_price = round(price * 0.97, 2)  # 3% below current price
else:
    limit_price = round(price - 0.03, 2)
```

### Issue 7: Equity Calculation Is Intraday-Only — Doesn't Compound Across Days

**The problem (bot_ibkr.py line 449):**
```python
current_equity = STARTING_EQUITY + state.daily_pnl  # Intraday equity
# TODO: fetch actual account equity from IBKR for multi-day compounding
```

The bot resets to $30K starting equity every day. If you made $5K yesterday, today's risk calc still uses $30K as the base. The backtest compounds ($30K → $296K in 60 trades), but live doesn't.

**Fix:** Fetch actual account equity from IBKR at startup:
```python
def get_account_equity():
    """Get current account equity from IBKR."""
    account_values = state.ib.accountValues()
    for av in account_values:
        if av.tag == 'NetLiquidation' and av.currency == 'USD':
            return float(av.value)
    return STARTING_EQUITY  # Fallback

# In main(), after connecting:
actual_equity = get_account_equity()
print(f"Account equity: ${actual_equity:,.0f}")
```

Then use this as the base for position sizing. For paper trading this matters less, but for live it's the difference between the backtest's compounding returns and flat $30K sizing.

### Issue 8: Single Position Limit — Misses Multi-Stock Days

**The problem (bot_ibkr.py line 391):**
```python
if state.open_position is not None:
    return  # Already in a position — no new entries
```

The bot can only hold one position at a time. If ONCO squeezes at 7:05 and ARTL squeezes at 7:08, it can only take one. The backtest runs single-threaded per symbol, so this isn't visible there, but in live trading this means missing the second (potentially bigger) play.

Ross routinely trades 2-3 stocks simultaneously on hot mornings.

**This is NOT a quick fix** — it requires rearchitecting position tracking from a single dict to a dict-of-dicts keyed by symbol. Flag for a future sprint, but be aware this is a structural limitation that will underperform the backtest on multi-stock days.

### Issue 9: No Reconnection Logic — A Disconnect Kills the Session

**The problem:** If the IBKR connection drops (network blip, Gateway restart, nightly server reset), the bot crashes or hangs. There's no reconnection logic.

**Fix:** Add a connection watchdog in the main loop:
```python
# In the main loop:
if not state.ib.isConnected():
    print("🔴 CONNECTION LOST — attempting reconnect...", flush=True)
    for attempt in range(5):
        try:
            state.ib.disconnect()
            time.sleep(5)
            state.ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
            # Re-wire events
            state.ib.pendingTickersEvent += on_ticker_update
            state.ib.errorEvent += on_ib_error
            # Re-subscribe all active symbols
            for symbol in list(state.active_symbols):
                contract = state.contracts[symbol]
                ticker = state.ib.reqMktData(contract, '233', False, False)
                state.tickers[symbol] = ticker
            print(f"  Reconnected on attempt {attempt + 1}", flush=True)
            break
        except Exception as e:
            print(f"  Reconnect attempt {attempt + 1} failed: {e}", flush=True)
            time.sleep(10)
```

---

## TIER 3: IMPORTANT (Fix this week)

### Issue 10: Scanner Uses `STK.US.MAJOR` — Misses OTC

**The problem (ibkr_scanner.py line 111):**
```python
locationCode='STK.US.MAJOR',  # TODO: STK.US for OTC once permissions active
```

There's a TODO comment noting OTC stocks are excluded. Once Luke's OTC permissions are active (~April 3), this needs to change to `'STK.US'` to include OTC gappers. Many of Ross's biggest winners are OTC.

### Issue 11: Scanner Calls `compute_adv()` Per Symbol — Very Slow

**The problem:** Each scanner candidate triggers a separate `reqHistoricalData` call for 30 days of daily bars to compute ADV. With 20 candidates, that's 20 sequential API calls × 1.5s each = 30 seconds minimum. During pre-market when speed matters most, this is a 30-second delay.

**Fix:** Cache ADV values. Most stocks' ADV doesn't change significantly day-to-day. Cache for 24 hours:
```python
ADV_CACHE = {}  # symbol -> (adv, timestamp)
ADV_CACHE_TTL = 86400  # 24 hours

def compute_adv_cached(ib, symbol, date_str=None):
    now = time.time()
    if symbol in ADV_CACHE:
        adv, cached_at = ADV_CACHE[symbol]
        if now - cached_at < ADV_CACHE_TTL:
            return adv
    adv = compute_adv(ib, symbol, date_str)
    ADV_CACHE[symbol] = (adv, now)
    return adv
```

### Issue 12: Bar Builder Timestamps Use Local Clock, Not Exchange Time

**The problem (bot_ibkr.py line 686):**
```python
ts = datetime.now(ET)
```

The tick timestamp is the Mac Mini's local clock, not the exchange timestamp. IBKR's `reqMktData` doesn't provide a timestamp — the ib_insync library adds it from your local clock. This is documented: _"Realtime data returned by TWS from reqMktData() does not contain a timestamp. ib_insync itself adds the timestamp using your computer clock."_ ([Groups.io TWS API forum](https://groups.io/g/twsapi/topic/source_of_the_ticks/80674602))

If the Mac Mini's clock drifts even 5 seconds, bar boundaries shift and squeeze detection timing changes. For a 1-minute bar builder that needs accurate bin boundaries, this matters.

**Fix:** Sync the Mac Mini clock via NTP, and log the clock skew at startup:
```bash
# In daily_run.sh, add after git pull:
sudo sntp -sS time.apple.com 2>&1 || echo "NTP sync failed"
echo "System time: $(date -u)"
```

---

## TIER 4: IMPROVEMENT (Next sprint)

### Issue 13: No `ib.reqContractDetails` Before Subscribing

**Best practice from experienced IBKR API developers:**
_"During startup, we use reqContractDetails to retrieve a contract object for each instrument instead of making our own contract objects. This way you get the most up-to-date instrument details and a contract object that has all fields initialized."_ ([Groups.io TWS API forum](https://groups.io/g/twsapi/topic/going_to_have_to_reconsider/95817693))

Currently the bot creates contracts with `Stock(symbol, 'SMART', 'USD')` and calls `qualifyContracts()`, but doesn't use `reqContractDetails` to get full instrument info (trading hours, exchange status, tick size, etc.). This could prevent issues with delisted symbols, exchange changes, or instruments that have unusual characteristics.

---

## Priority Execution Order

| # | Issue | Time | Impact |
|---|-------|------|--------|
| 1 | Stale code on Mac Mini | 5 min | No fix works if wrong code runs |
| 2 | Add RTVolume (tick 233) | 5 min | 10x more data from IBKR |
| 3 | Scanner snapshot mode | 10 min | Prevents subscription conflicts |
| 5 | Fill verification for entries | 20 min | P&L tracking accuracy |
| 6 | Fill verification for exits | 15 min | Prevents phantom positions |
| 9 | Reconnection logic | 15 min | Survives network blips |
| 4 | Fallback price sources | 10 min | Handles thin pre-market |
| 7 | Fetch real account equity | 10 min | Proper compounding |
| 10 | OTC scanner (when ready) | 2 min | More candidates |
| 11 | ADV cache | 10 min | Faster scanner |
| 12 | NTP time sync | 2 min | Accurate bars |

**Total estimated time: ~2 hours of focused work.**

---

## CC's Existing Directive vs This One

CC's `DIRECTIVE_IBKR_INFRASTRUCTURE_FIX.md` correctly identifies:
- ✅ Gateway switch verification (our Issue 1)
- ✅ Tick health monitoring and resubscription (partially addresses Issue 2)
- ✅ Scanner results preservation (already implemented in current code)
- ✅ F-string bug fix (already in the latest push)
- ✅ Competing session error handling (already implemented)

**This directive adds:**
- 🆕 RTVolume generic tick 233 — the single biggest improvement to data quality
- 🆕 Scanner using snapshot mode instead of subscribe/cancel
- 🆕 Fill verification for entries and exits
- 🆕 Fallback price sources for thin stocks
- 🆕 Account equity fetch for proper compounding
- 🆕 Reconnection logic for dropped connections
- 🆕 NTP time sync
- 🆕 ADV caching for faster scanning

---

## Verification Checklist (Monday Morning)

Before market open Monday, verify:

1. [ ] `daily_run.sh` on Mac Mini uses port 4002 and Gateway (not TWS/7497)
2. [ ] `git log -1` on Mac Mini matches latest commit on remote
3. [ ] Log shows "Connected" to port 4002 (not 7497)
4. [ ] Log shows "TICK AUDIT" lines with non-zero tick counts within 60s of subscribing
5. [ ] RTVolume data flowing (if implemented): look for more frequent ticker updates
6. [ ] No `ValueError: Invalid format specifier` in logs
7. [ ] Scanner results file has timestamped snapshots (not overwritten to `[]`)
8. [ ] Bot stays alive through morning session without crashing

---

## The Honest Assessment

The strategy is proven — $30K → $296K on IBKR tick data, sq_target_hit 39/39. But we're on Day 4 of live testing and have $0 to show for it because the infrastructure keeps failing before the strategy even gets a chance to run. The fixes in this directive are not exotic — they're basic plumbing that any production trading system needs:

1. Make sure the right code runs
2. Make sure data actually arrives
3. Make sure orders actually fill
4. Make sure the connection survives

Get these four things right and the strategy will do the rest.
