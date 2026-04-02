# Directive: Ship EPL (MP Re-Entry + VWAP Floor Gate) to Live Bot V3

## Priority: P0
## Prereqs:
- Read `bot_v3_hybrid.py` — current live bot (1,576 lines, zero EPL awareness)
- Read `epl_framework.py` — framework classes (commit 6d52894)
- Read `epl_mp_reentry.py` — MP re-entry strategy (commit 65ce7cf)
- Read `simulate.py` lines 1935-1976 — EPL initialization + graduation hook
- Read `simulate.py` lines 2577-2648 — EPL 1m bar processing
- Read `simulate.py` lines 3054-3111 — EPL tick processing

---

## Context

### What's Been Proven

The EPL stack (SQ + MP re-entry + VWAP floor gate) produced **$252K on a 63-day megatest** — up from $169K SQ-only baseline (+$83K, +49%). The VWAP floor gate eliminated all 8 VWAP-loss losers while preserving the ROLR $22,930 re-entry winner.

| Config | Total P&L | Trades | Win Rate |
|--------|-----------|--------|----------|
| SQ only (baseline) | $169K | 29 | 67% |
| SQ + MP re-entry | $201K | 55 | 50% |
| SQ + MP + VWAP floor | **$252K** | **45** | **59%** |

### What Ships

- `epl_framework.py` — GraduationContext, EPLWatchlist, StrategyRegistry, PositionArbitrator (already in repo)
- `epl_mp_reentry.py` — MP re-entry strategy with VWAP floor gate (already in repo)
- Integration hooks in `bot_v3_hybrid.py` — **THIS IS WHAT CC BUILDS**

### What Does NOT Ship

- `epl_vwap_reclaim.py` — 0 trades on 63-day megatest. Leave in repo, do NOT register. Do NOT import.
- No new files to create. All changes go into `bot_v3_hybrid.py` and `.env`.

---

## Integration Changes (bot_v3_hybrid.py)

### 1. Imports (top of file, near line 48)

Add after the existing detector imports:

```python
from epl_framework import (
    EPL_ENABLED, EPL_MAX_NOTIONAL, EPL_MIN_GRADUATION_R,
    GraduationContext, EPLWatchlist, StrategyRegistry, PositionArbitrator,
)
from epl_mp_reentry import EPLMPReentry, EPL_MP_ENABLED
```

### 2. Strategy gate (near line 64, with other gates)

```python
# Already imported above via epl_framework / epl_mp_reentry
# EPL_ENABLED reads WB_EPL_ENABLED (default "0")
# EPL_MP_ENABLED reads WB_EPL_MP_ENABLED (default "0")
```

No new gate variables needed — the framework reads its own env vars.

### 3. BotState additions (class BotState, line 133)

Add these fields inside `__init__`:

```python
        # EPL (Extended Play List) — post-2R re-entry system
        self.epl_watchlist: EPLWatchlist = None
        self.epl_registry: StrategyRegistry = None
        self.epl_arbitrator: PositionArbitrator = None
```

### 4. EPL initialization (in `main()`, line 1324, after detector setup)

Find the section where squeeze/MP/CT detectors are initialized (somewhere after `main()` starts and connects to IBKR/Alpaca). Add EPL initialization nearby:

```python
    # ── EPL Framework (Extended Play List) ──
    if EPL_ENABLED:
        state.epl_watchlist = EPLWatchlist()
        state.epl_registry = StrategyRegistry()
        state.epl_arbitrator = PositionArbitrator(state.epl_registry, state.epl_watchlist)
        _epl_mp = EPLMPReentry()
        if EPL_MP_ENABLED:
            state.epl_registry.register(_epl_mp)
        print(f"EPL initialized: {state.epl_registry.strategy_count} strategies registered", flush=True)
    else:
        print("EPL disabled (WB_EPL_ENABLED=0)", flush=True)
```

### 5. Graduation hook in `_squeeze_exit()` (line 982)

This is the critical hook. When SQ hits 2R target and exits the core position, the stock graduates to the EPL watchlist.

Find the target hit section (around line 1013-1023):

```python
        # 3) Target hit — exit core, keep runner
        if r > 0 and price >= entry + (SQ_TARGET_R * r):
            pos["tp_hit"] = True
```

**Right after `pos["tp_hit"] = True` and BEFORE the exit_trade call**, add the graduation hook:

```python
            # EPL graduation: stock hit 2R target, add to watchlist
            if EPL_ENABLED and state.epl_watchlist is not None:
                realized_r = (price - entry) / r if r > 0 else 0
                if realized_r >= EPL_MIN_GRADUATION_R:
                    vwap = state.bar_builder_1m.get_vwap(symbol) if state.bar_builder_1m else 0
                    hod = state.bar_builder_1m.get_hod(symbol) if state.bar_builder_1m else 0
                    pm_high = state.bar_builder_1m.get_premarket_high(symbol) if state.bar_builder_1m else 0
                    ctx = GraduationContext(
                        symbol=symbol,
                        graduation_time=datetime.now(ET),
                        graduation_price=price,
                        sq_entry_price=entry,
                        sq_stop_price=stop,
                        hod_at_graduation=hod or 0,
                        vwap_at_graduation=vwap or 0,
                        pm_high=pm_high or 0,
                        avg_volume_at_graduation=0,
                        sq_trade_count=1,
                        r_value=r,
                    )
                    state.epl_watchlist.add(ctx)
                    state.epl_registry.notify_graduation(ctx)
                    now_str = datetime.now(ET).strftime("%H:%M:%S")
                    print(f"[{now_str} ET] [EPL] {symbol} GRADUATED @ ${price:.2f} "
                          f"(R={realized_r:.1f}, vwap=${vwap or 0:.2f}, hod=${hod or 0:.2f})", flush=True)
```

### 6. EPL bar processing in `on_bar_close_1m()` (line 580)

Add at the END of the function (after all existing SQ/MP/CT processing):

```python
    # ── EPL: 1m bar processing ──
    if EPL_ENABLED and state.epl_registry and state.epl_registry.strategy_count > 0:
        # Expiry check
        now_et = datetime.now(ET)
        expired = state.epl_watchlist.check_expiry(now_et)
        for esym in expired:
            state.epl_registry.notify_expiry(esym)
            state.epl_watchlist.remove(esym)
            print(f"[{now_str} ET] [EPL] {esym} expired from watchlist", flush=True)

        # EPL exit management (1m bar) for open EPL trades
        pos = state.open_position
        if pos and pos.get("setup_type", "").startswith("epl_"):
            epl_strat = state.epl_registry.get_strategy(pos["setup_type"])
            if epl_strat:
                bar_dict = {
                    "o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close,
                    "v": bar.volume, "green": bar.close >= bar.open, "vwap": vwap,
                }
                epl_exit = epl_strat.manage_exit(symbol, bar.close, bar_dict)
                if epl_exit:
                    now_str2 = datetime.now(ET).strftime("%H:%M:%S")
                    print(f"[{now_str2} ET] [EPL] {epl_exit.strategy} EXIT SIGNAL {symbol} "
                          f"@ ${epl_exit.exit_price:.2f} reason={epl_exit.exit_reason}", flush=True)
                    exit_trade(symbol, epl_exit.exit_price, pos["qty"], epl_exit.exit_reason)
                    # Record result for session loss cap
                    if state.epl_arbitrator:
                        epl_pnl = (epl_exit.exit_price - pos["entry"]) * pos["qty"]
                        state.epl_arbitrator.record_epl_trade_result(symbol, epl_pnl)
                    state.epl_registry.reset_all(symbol)

        # EPL entry signals (1m bar) — only when no open position and symbol is graduated
        if state.open_position is None and state.epl_watchlist.is_graduated(symbol):
            sq_state = state.sq_detectors[symbol]._state if (SQ_ENABLED and symbol in state.sq_detectors) else "IDLE"
            sq_in_trade = (SQ_ENABLED and symbol in state.sq_detectors and state.sq_detectors[symbol]._in_trade)
            now_et2 = datetime.now(ET)
            if state.epl_arbitrator.can_epl_enter(symbol, sq_state, sq_in_trade, now_et2):
                bar_dict = {
                    "o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close,
                    "v": bar.volume, "green": bar.close >= bar.open, "vwap": vwap,
                }
                signals = state.epl_registry.collect_entry_signals(symbol, bar_dict, None, None)
                best = state.epl_arbitrator.get_best_signal(signals)
                if best:
                    _enter_epl_trade(symbol, best)
```

### 7. EPL tick processing in `_process_ticker()` (line 1173)

Find the section near line 1227-1231:

```python
    # Check triggers
    check_triggers(symbol, price)

    # Manage exits
    if state.open_position and state.open_position["symbol"] == symbol:
        manage_exit(symbol, price)
```

Add EPL tick processing **between** check_triggers and manage_exit:

```python
    # Check triggers
    check_triggers(symbol, price)

    # ── EPL tick processing ──
    if EPL_ENABLED and state.epl_registry and state.epl_registry.strategy_count > 0:
        pos = state.open_position
        # EPL tick-level exit management
        if pos and pos.get("setup_type", "").startswith("epl_") and pos["symbol"] == symbol:
            epl_strat = state.epl_registry.get_strategy(pos["setup_type"])
            if epl_strat:
                epl_exit = epl_strat.manage_exit(symbol, price, None)
                if epl_exit:
                    now_str = datetime.now(ET).strftime("%H:%M:%S")
                    print(f"[{now_str} ET] [EPL] {epl_exit.strategy} EXIT {symbol} "
                          f"@ ${epl_exit.exit_price:.2f} reason={epl_exit.exit_reason}", flush=True)
                    exit_trade(symbol, epl_exit.exit_price, pos["qty"], epl_exit.exit_reason)
                    if state.epl_arbitrator:
                        epl_pnl = (epl_exit.exit_price - pos["entry"]) * pos["qty"]
                        state.epl_arbitrator.record_epl_trade_result(symbol, epl_pnl)
                    state.epl_registry.reset_all(symbol)
                    return  # Exit processed, skip normal exit management

        # EPL tick-level entry trigger (ARMED → entry)
        if state.open_position is None and state.epl_watchlist and state.epl_watchlist.is_graduated(symbol):
            sq_state = state.sq_detectors[symbol]._state if (SQ_ENABLED and symbol in state.sq_detectors) else "IDLE"
            sq_in_trade = (SQ_ENABLED and symbol in state.sq_detectors and state.sq_detectors[symbol]._in_trade)
            ts_et = datetime.now(ET)
            if state.epl_arbitrator.can_epl_enter(symbol, sq_state, sq_in_trade, ts_et):
                signals = state.epl_registry.collect_entry_signals(symbol, None, price, size)
                best = state.epl_arbitrator.get_best_signal(signals)
                if best:
                    _enter_epl_trade(symbol, best)
                    return  # Entered, skip normal trigger check below

    # Manage exits
    if state.open_position and state.open_position["symbol"] == symbol:
        manage_exit(symbol, price)
```

**WAIT — correction.** The EPL tick entry check should happen INSIDE `check_triggers()`, not in `_process_ticker()`. Otherwise it runs after `check_triggers` has already potentially entered a SQ trade. Let me restructure:

Actually, re-reading the flow: `check_triggers()` returns early if `state.open_position is not None`. And `_enter_epl_trade` (below) sets `state.open_position`. So the EPL tick entry in `_process_ticker` works correctly because:
1. `check_triggers()` runs — if SQ enters, sets open_position, returns
2. EPL tick block runs — sees open_position is set, skips entry, checks exit
3. OR: check_triggers finds nothing, EPL tick block sees open_position is None, checks entry

The ordering is correct as written. SQ always fires first via `check_triggers()`.

### 8. EPL entry function (new function, add near `enter_trade()` around line 946)

```python
def _enter_epl_trade(symbol: str, signal):
    """Place EPL entry order via Alpaca. Uses EPL_MAX_NOTIONAL for sizing."""
    entry = signal.entry_price
    stop = signal.stop_price
    r = entry - stop

    if r <= 0 or r < MIN_R:
        print(f"  [EPL] SKIP: R={r:.4f} < min {MIN_R}", flush=True)
        return

    # EPL sizing: use EPL_MAX_NOTIONAL (same as SQ notional by default)
    qty = int(math.floor(EPL_MAX_NOTIONAL * signal.position_size_pct / max(entry, 0.01)))
    qty = min(qty, MAX_SHARES)

    if qty <= 0:
        return

    limit_price = round(entry + 0.02, 2)
    now_str = datetime.now(ET).strftime("%H:%M:%S")
    print(f"[{now_str} ET] [EPL] 🟩 ENTRY: {symbol} strategy={signal.strategy} "
          f"qty={qty} limit=${limit_price:.2f} stop=${stop:.4f} R=${r:.4f} "
          f"reason={signal.reason}", flush=True)

    try:
        req = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
            extended_hours=True,
        )
        alpaca_order = state.alpaca.submit_order(req)
        order_id = str(alpaca_order.id)
        print(f"  [EPL] ALPACA ORDER: {order_id} BUY {qty} {symbol} @ ${limit_price:.2f}", flush=True)
    except Exception as e:
        print(f"  [EPL] ALPACA ORDER FAILED: {e}", flush=True)
        return

    state.open_position = {
        "symbol": symbol,
        "qty": qty,
        "entry": limit_price,
        "stop": stop,
        "r": r,
        "score": signal.confidence * 10,
        "setup_type": signal.strategy,  # "epl_mp_reentry"
        "peak": limit_price,
        "tp_hit": False,
        "entry_time": datetime.now(ET),
        "order_id": order_id,
        "is_parabolic": False,
        "fill_confirmed": False,
    }

    # Store pending order for timeout check
    state.pending_order = {
        "order_id": order_id,
        "placed_time": datetime.now(ET),
        "timeout_seconds": 15,
    }

    # Mark strategy as in-trade
    epl_strat = state.epl_registry.get_strategy(signal.strategy)
    if epl_strat and hasattr(epl_strat, 'mark_in_trade'):
        epl_strat.mark_in_trade(symbol)

    # Reuse existing fill verification thread
    import threading
    def verify_epl_fill():
        for _ in range(30):
            try:
                o = state.alpaca.get_order_by_id(order_id)
                if o.status == 'filled':
                    actual_price = float(o.filled_avg_price)
                    actual_qty = int(float(o.filled_qty))
                    if state.open_position and state.open_position.get("order_id") == order_id:
                        state.open_position["entry"] = actual_price
                        state.open_position["qty"] = actual_qty
                        state.open_position["peak"] = max(state.open_position["peak"], actual_price)
                        state.open_position["stop"] = actual_price - r
                        state.open_position["fill_confirmed"] = True
                        state.pending_order = None
                        print(f"  [EPL] FILL: {symbol} @ ${actual_price:.4f} qty={actual_qty}", flush=True)
                    return
                if o.status in ('cancelled', 'expired', 'rejected'):
                    print(f"  [EPL] ORDER {o.status.upper()}: {symbol} {order_id}", flush=True)
                    if state.open_position and state.open_position.get("order_id") == order_id:
                        state.open_position = None
                        state.pending_order = None
                    return
            except Exception as e:
                print(f"  [EPL] FILL CHECK ERROR: {e}", flush=True)
            time.sleep(0.5)
        print(f"  [EPL] ORDER TIMEOUT: cancelling {order_id}", flush=True)
        try:
            state.alpaca.cancel_order_by_id(order_id)
        except Exception:
            pass
        if state.open_position and state.open_position.get("order_id") == order_id:
            state.open_position = None
            state.pending_order = None

    threading.Thread(target=verify_epl_fill, daemon=True).start()
```

### 9. EPL exit routing in `manage_exit()` (line 949)

Current code (line 976):
```python
    if setup_type in ("squeeze", "mp_reentry", "continuation"):
        _squeeze_exit(symbol, price, pos)
    else:
        _mp_exit(symbol, price, pos)
```

Change to:
```python
    if setup_type.startswith("epl_"):
        return  # EPL exits handled in _process_ticker / on_bar_close_1m via strategy.manage_exit()
    elif setup_type in ("squeeze", "mp_reentry", "continuation"):
        _squeeze_exit(symbol, price, pos)
    else:
        _mp_exit(symbol, price, pos)
```

This prevents the normal SQ/MP exit logic from running on EPL trades. EPL strategies manage their own exits.

---

## Add to .env (Mac Mini)

```bash
# === EPL: Extended Play List (post-2R re-entry) ===
WB_EPL_ENABLED=1
WB_EPL_MAX_STOCKS=5
WB_EPL_EXPIRY_MINUTES=120
WB_EPL_MIN_GRADUATION_R=2.0
WB_EPL_MAX_TRADES_PER_GRAD=3
WB_EPL_MAX_NOTIONAL=50000
WB_EPL_MAX_LOSS_SESSION=1000

# === EPL: MP Re-Entry ===
WB_EPL_MP_ENABLED=1
WB_EPL_MP_COOLDOWN_BARS=3
WB_EPL_MP_MAX_PULLBACK_BARS=5
WB_EPL_MP_MIN_R=0.06
WB_EPL_MP_STOP_PAD=0.01
WB_EPL_MP_TRAIL_R=1.5
WB_EPL_MP_TIME_STOP_BARS=5
WB_EPL_MP_VWAP_FLOOR=1
```

---

## What NOT To Do

1. **Do NOT import or register `epl_vwap_reclaim.py`.** It produced 0 trades. Leave it in the repo, do not wire it in.
2. **Do NOT change SQ exit logic.** The graduation hook fires within `_squeeze_exit` but does not alter exit behavior — SQ still exits the core at 2R and trails the runner exactly as before.
3. **Do NOT change SQ entry logic.** `check_triggers()` runs SQ first. EPL entries only fire when position is free and SQ is idle.
4. **Do NOT add EPL to `daily_run_v3.sh`.** No startup changes needed — the bot reads env vars and the framework self-initializes.
5. **Do NOT create a new branch.** All changes go on `v2-ibkr-migration`.

---

## Testing

### Smoke test (no market needed)

1. Set `WB_EPL_ENABLED=1`, `WB_EPL_MP_ENABLED=1` in `.env`
2. Start `bot_v3_hybrid.py`
3. Confirm log output: `EPL initialized: 1 strategies registered`
4. Confirm no import errors
5. Confirm SQ detection still works normally (PRIMED/ARMED/entry signals)

### Live verification

On the next trading day with a SQ 2R hit:
1. Confirm `[EPL] SYMBOL graduated` log line appears
2. Confirm EPL MP re-entry starts WATCHING (log: `[EPL:MP] SYMBOL graduated → WATCHING`)
3. If pullback occurs above VWAP → confirm ARM + entry signal
4. If pullback breaches VWAP → confirm VWAP floor blocks ARM (log: `RESET: pullback low below VWAP floor`)
5. Confirm SQ trades are completely unchanged (same entries, exits, P&L)

### Regression check

Before pushing, run the standalone regression to confirm SQ is unchanged:

```bash
WB_EPL_ENABLED=1 WB_EPL_MP_ENABLED=1 WB_EPL_MP_VWAP_FLOOR=1 \
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
```

VERO should still produce SQ trades + any EPL trades. SQ P&L portion must match baseline.

---

## Logging

All EPL log lines prefixed with `[EPL]`:
- `[HH:MM:SS ET] [EPL] STAK GRADUATED @ $8.50 (R=2.1, vwap=$7.20, hod=$8.55)`
- `[HH:MM:SS ET] [EPL:MP] STAK graduated → WATCHING (cooldown=3 bars)`
- `[HH:MM:SS ET] [EPL:MP] STAK PULLBACK detected (close=$8.10 < prev_close=$8.30)`
- `[HH:MM:SS ET] [EPL:MP] STAK ARMED: trigger=$8.35, stop=$8.05, R=0.30`
- `[HH:MM:SS ET] [EPL:MP] STAK RESET: pullback low below VWAP floor ($7.15 < $7.20)`
- `[HH:MM:SS ET] [EPL] 🟩 ENTRY: STAK strategy=epl_mp_reentry qty=5882 limit=$8.52`
- `[HH:MM:SS ET] [EPL] epl_mp_reentry EXIT STAK @ $9.10 reason=epl_mp_time_exit(5bars)`

---

## Commit

```
Ship EPL MP re-entry + VWAP floor gate to live bot V3

Wire EPL framework into bot_v3_hybrid.py: graduation hook on SQ 2R
target hit, EPL bar/tick processing for entry signals and exit
management, EPL-specific order sizing (EPL_MAX_NOTIONAL), session
loss cap tracking.

Backtest-proven: $252K on 63-day megatest (+$83K over SQ-only baseline).
VWAP floor gate eliminates all VWAP-loss losers. MP re-entry catches
shallow pullbacks on runners that hit 2R.

WB_EPL_ENABLED=1 + WB_EPL_MP_ENABLED=1 to activate.
VR intentionally excluded (0 trades on megatest).
```
