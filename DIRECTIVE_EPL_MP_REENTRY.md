# Directive: EPL Strategy — MP Re-Entry (Post-2R Graduation)

## Priority: P0
## Prereqs:
- Read `ARCHITECTURE_EXTENDED_PLAY_LIST.md` — the EPL design doc
- Read `epl_framework.py` — the framework you already built (commit 6d52894)
- Read `micro_pullback.py` — the existing MP V2 detection logic to salvage

---

## Context

The EPL framework is built (graduation hook, watchlist, strategy registry, position arbitrator). Now we need the first strategy to plug into it: **MP Re-Entry**.

When SQ hits 2R, the stock graduates to the EPL watchlist. MP Re-Entry then watches for a pullback → confirmation → re-entry pattern. 83% of runners pull back before continuing, so this is the most common re-entry opportunity.

**What's different from old MP V2:**
- Only activates after 2R graduation (not any SQ close)
- Has its own exit logic (not routed through SQ exits)
- Doesn't interfere with SQ position (SQ exits fully at 2R first)
- Uses EPL framework for position arbitration

**What's salvageable from existing micro_pullback.py:**
- The 1-minute pullback detection (red bar, lower close, wick pullback)
- The trigger candle validation (hammer, bullish engulfing, strong close)
- Stop/entry calculation (trigger_high = entry, pullback_low = stop)
- Quality gates (clean pullback, impulse strength)
- MACD gate suppression for post-squeeze pullbacks

---

## Part 1: Build the Strategy

### File: `epl_mp_reentry.py` (NEW)

Implements `EPLStrategy` from `epl_framework.py`.

```python
class EPLMPReentry(EPLStrategy):
    """
    MP Re-Entry: Detects micro-pullback re-entry after SQ 2R graduation.

    State machine per symbol:
    IDLE → WATCHING → PULLBACK → ARMED → (entry or reset)

    IDLE: Not tracking this symbol (pre-graduation or post-expiry)
    WATCHING: Graduated, waiting for pullback bars to appear
    PULLBACK: Counting pullback bars (1-3 red/lower bars)
    ARMED: Confirmation candle seen, waiting for tick to break trigger_high
    """
```

#### Properties

```python
@property
def name(self) -> str:
    return "epl_mp_reentry"

@property
def priority(self) -> int:
    return 50  # Below SQ (100), above other EPL strategies
```

#### Env Vars

```python
# All OFF by default, all read from os.environ
EPL_MP_ENABLED = int(os.environ.get("WB_EPL_MP_ENABLED", "0"))
EPL_MP_COOLDOWN_BARS = int(os.environ.get("WB_EPL_MP_COOLDOWN_BARS", "3"))
EPL_MP_MAX_PULLBACK_BARS = int(os.environ.get("WB_EPL_MP_MAX_PULLBACK_BARS", "3"))
EPL_MP_MIN_R = float(os.environ.get("WB_EPL_MP_MIN_R", "0.06"))
EPL_MP_MACD_GATE = int(os.environ.get("WB_EPL_MP_MACD_GATE", "0"))  # OFF = suppress MACD for post-squeeze
EPL_MP_STOP_PAD = float(os.environ.get("WB_EPL_MP_STOP_PAD", "0.01"))
```

#### Per-Symbol State

```python
@dataclass
class MPReentryState:
    phase: str = "IDLE"            # IDLE, WATCHING, PULLBACK, ARMED
    graduation_ctx: Optional[GraduationContext] = None
    cooldown_bars: int = 0         # Bars remaining in cooldown
    pullback_count: int = 0        # Number of pullback bars seen
    pullback_low: float = float('inf')  # Lowest low during pullback
    trigger_high: float = 0.0      # High of confirmation candle
    entry_price: float = 0.0       # = trigger_high
    stop_price: float = 0.0        # = pullback_low - pad
    r_value: float = 0.0           # entry - stop
    bars_since_graduation: int = 0 # Track time
    last_bar: Optional[dict] = None
    prev_bar: Optional[dict] = None
```

#### on_graduation(ctx)

```python
def on_graduation(self, ctx: GraduationContext) -> None:
    if not EPL_MP_ENABLED:
        return
    state = self._get_or_create_state(ctx.symbol)
    state.graduation_ctx = ctx
    state.phase = "WATCHING"
    state.cooldown_bars = EPL_MP_COOLDOWN_BARS  # Wait N bars before looking
    state.bars_since_graduation = 0
    state.pullback_count = 0
    state.pullback_low = float('inf')
    log(f"[EPL:MP] {ctx.symbol} graduated → WATCHING (cooldown={EPL_MP_COOLDOWN_BARS} bars)")
```

#### on_bar(symbol, bar) — The Core Detection

This is where the pullback state machine lives. Port the logic from `micro_pullback.py`'s `_pullback_entry_check()` (lines 970-1172), adapted for EPL:

```python
def on_bar(self, symbol: str, bar: dict) -> Optional[EntrySignal]:
    if not EPL_MP_ENABLED:
        return None
    state = self._states.get(symbol)
    if not state or state.phase == "IDLE":
        return None

    state.bars_since_graduation += 1
    state.prev_bar = state.last_bar
    state.last_bar = bar

    # --- COOLDOWN ---
    if state.cooldown_bars > 0:
        state.cooldown_bars -= 1
        return None

    # --- WATCHING: Look for pullback bars ---
    if state.phase == "WATCHING":
        if self._is_pullback_bar(bar, state.prev_bar):
            state.phase = "PULLBACK"
            state.pullback_count = 1
            state.pullback_low = bar["l"]
            log(f"[EPL:MP] {symbol} PULLBACK started (bar low={bar['l']:.2f})")
        return None

    # --- PULLBACK: Count pullback bars, wait for confirmation ---
    if state.phase == "PULLBACK":
        if self._is_pullback_bar(bar, state.prev_bar):
            state.pullback_count += 1
            state.pullback_low = min(state.pullback_low, bar["l"])
            if state.pullback_count > EPL_MP_MAX_PULLBACK_BARS:
                log(f"[EPL:MP] {symbol} RESET: pullback too long ({state.pullback_count} bars)")
                state.phase = "WATCHING"
                state.pullback_count = 0
                state.pullback_low = float('inf')
            return None

        # Green bar after pullback — check if it's a valid trigger
        if bar["green"] and state.pullback_count >= 1:
            if self._is_valid_trigger(bar, state.prev_bar):
                # ARM
                entry = bar["h"]
                stop = state.pullback_low - EPL_MP_STOP_PAD
                r = entry - stop
                if r < EPL_MP_MIN_R:
                    log(f"[EPL:MP] {symbol} RESET: R too small ({r:.4f} < {EPL_MP_MIN_R})")
                    state.phase = "WATCHING"
                    state.pullback_count = 0
                    state.pullback_low = float('inf')
                    return None

                state.phase = "ARMED"
                state.trigger_high = entry
                state.entry_price = entry
                state.stop_price = stop
                state.r_value = r
                log(f"[EPL:MP] {symbol} ARMED: trigger={entry:.2f}, stop={stop:.2f}, R={r:.4f}")
                return None  # Wait for tick to break trigger_high
            else:
                log(f"[EPL:MP] {symbol} RESET: weak trigger candle")
                state.phase = "WATCHING"
                state.pullback_count = 0
                state.pullback_low = float('inf')
                return None

        # Neither pullback nor valid trigger — reset
        state.phase = "WATCHING"
        state.pullback_count = 0
        state.pullback_low = float('inf')
        return None

    return None  # ARMED state handled in on_tick
```

#### on_tick(symbol, price, size) — Trigger Break

```python
def on_tick(self, symbol: str, price: float, size: int) -> Optional[EntrySignal]:
    if not EPL_MP_ENABLED:
        return None
    state = self._states.get(symbol)
    if not state or state.phase != "ARMED":
        return None

    if price >= state.trigger_high:
        signal = EntrySignal(
            symbol=symbol,
            strategy=self.name,
            entry_price=state.entry_price,
            stop_price=state.stop_price,
            target_price=None,  # Trail-only, no fixed target
            position_size_pct=1.0,  # Full EPL notional
            reason=f"pullback_break trigger={state.trigger_high:.2f} pb_low={state.pullback_low:.2f}",
            confidence=self._compute_confidence(state),
        )
        log(f"[EPL:MP] {symbol} ENTRY SIGNAL @ {price:.2f} (break {state.trigger_high:.2f})")
        # Reset to WATCHING for potential next pullback
        state.phase = "WATCHING"
        state.pullback_count = 0
        state.pullback_low = float('inf')
        return signal

    return None
```

#### _is_pullback_bar() — Port from micro_pullback.py line 1008

```python
def _is_pullback_bar(self, bar: dict, prev_bar: Optional[dict]) -> bool:
    """Three types of pullback bars (same as micro_pullback.py)."""
    if not bar["green"]:
        return True  # Red candle = pullback
    if prev_bar and bar["c"] <= prev_bar["c"]:
        return True  # Green but lower close
    # Wick pullback: large lower wick, small body
    rng = bar["h"] - bar["l"]
    if rng > 0:
        lower_wick = min(bar["o"], bar["c"]) - bar["l"]
        body = abs(bar["c"] - bar["o"])
        if (lower_wick / rng) >= 0.45 and (body / rng) <= 0.35:
            return True
    return False
```

#### _is_valid_trigger() — Port from micro_pullback.py lines 1034-1043

```python
def _is_valid_trigger(self, bar: dict, prev_bar: Optional[dict]) -> bool:
    """Three valid trigger patterns (same as micro_pullback.py)."""
    rng = bar["h"] - bar["l"]
    if rng <= 0:
        return False

    # Reject shooting star
    upper_wick = bar["h"] - max(bar["o"], bar["c"])
    body = abs(bar["c"] - bar["o"])
    if rng > 0 and (upper_wick / rng) >= 0.6 and (body / rng) <= 0.25:
        return False  # Shooting star

    # Valid: hammer, bullish engulfing, or strong close
    lower_wick = min(bar["o"], bar["c"]) - bar["l"]
    is_hammer = (lower_wick / rng) >= 0.5 and (body / rng) <= 0.4
    bull_engulf = prev_bar and bar["c"] > prev_bar["o"] and bar["o"] < prev_bar["c"]
    strong_close = bar["c"] >= (bar["l"] + 0.75 * rng)

    return is_hammer or bull_engulf or strong_close
```

#### manage_exit() — OWN exits, not SQ

This is the critical difference from old MP V2. The strategy owns its exits entirely.

```python
def manage_exit(self, symbol: str, price: float, bar: Optional[dict]) -> Optional[ExitSignal]:
    """
    EPL MP Re-Entry exit rules (independent of SQ):
    1. Hard stop at pullback low (stop_price)
    2. Trail at 1.5R once profitable
    3. VWAP loss = exit (if bar data available)
    4. Time stop: 5 bars without new high = exit
    """
    state = self._states.get(symbol)
    if not state or not hasattr(state, '_in_trade') or not state._in_trade:
        return None

    # 1. Hard stop
    if price <= state.stop_price:
        return ExitSignal(
            symbol=symbol,
            strategy=self.name,
            exit_price=price,
            exit_reason="epl_mp_stop_hit",
            exit_pct=1.0,
        )

    # 2. Trailing stop at 1.5R once profitable
    pnl_r = (price - state.entry_price) / state.r_value if state.r_value > 0 else 0
    if pnl_r >= 1.5:
        trail_stop = price - (1.5 * state.r_value)
        if not hasattr(state, '_trail_stop') or trail_stop > state._trail_stop:
            state._trail_stop = trail_stop
        if price <= state._trail_stop:
            return ExitSignal(
                symbol=symbol,
                strategy=self.name,
                exit_price=price,
                exit_reason=f"epl_mp_trail_exit(R={pnl_r:.1f})",
                exit_pct=1.0,
            )

    # 3. VWAP loss (checked on bar close)
    if bar and bar.get("vwap") and price < bar["vwap"]:
        return ExitSignal(
            symbol=symbol,
            strategy=self.name,
            exit_price=price,
            exit_reason="epl_mp_vwap_loss",
            exit_pct=1.0,
        )

    # 4. Time stop: 5 bars without new high
    if bar:
        if not hasattr(state, '_bars_in_trade'):
            state._bars_in_trade = 0
            state._trade_peak = state.entry_price
        state._bars_in_trade += 1
        if bar["h"] > state._trade_peak:
            state._trade_peak = bar["h"]
            state._bars_no_new_high = 0
        else:
            if not hasattr(state, '_bars_no_new_high'):
                state._bars_no_new_high = 0
            state._bars_no_new_high += 1
        if state._bars_no_new_high >= 5:
            return ExitSignal(
                symbol=symbol,
                strategy=self.name,
                exit_price=price,
                exit_reason=f"epl_mp_time_exit({state._bars_no_new_high}bars)",
                exit_pct=1.0,
            )

    return None
```

#### _compute_confidence() — For arbitrator prioritization

```python
def _compute_confidence(self, state: MPReentryState) -> float:
    """Score 0-1 for prioritization. Higher = more confident."""
    score = 0.5  # Base

    # Shallow pullback (1-2 bars) = higher confidence than deep (3 bars)
    if state.pullback_count <= 2:
        score += 0.2

    # Tight R (good risk:reward) = higher confidence
    if state.r_value <= 0.10:
        score += 0.1

    # Early in session = higher confidence
    if state.bars_since_graduation <= 10:
        score += 0.1

    return min(score, 1.0)
```

#### on_expiry() and reset()

```python
def on_expiry(self, symbol: str) -> None:
    state = self._states.get(symbol)
    if state:
        state.phase = "IDLE"
        log(f"[EPL:MP] {symbol} expired from EPL")

def reset(self, symbol: str) -> None:
    state = self._states.get(symbol)
    if state:
        state.phase = "WATCHING" if state.graduation_ctx else "IDLE"
        state.pullback_count = 0
        state.pullback_low = float('inf')
        state.cooldown_bars = EPL_MP_COOLDOWN_BARS
        # Clear trade tracking
        for attr in ('_in_trade', '_trail_stop', '_bars_in_trade', '_trade_peak', '_bars_no_new_high'):
            if hasattr(state, attr):
                delattr(state, attr)
        log(f"[EPL:MP] {symbol} reset → {state.phase}")
```

---

## Part 2: Wire the EPL Execution Hooks in simulate.py

The framework build (commit 6d52894) has the graduation hook but is **missing entry/exit execution**. These must be wired now.

### Hook: Register MP Re-Entry strategy

Near the EPL framework initialization (around line 1940-1942), after creating the registry:

```python
from epl_mp_reentry import EPLMPReentry

_epl_mp = EPLMPReentry()
if EPL_MP_ENABLED:
    _epl_registry.register(_epl_mp)
```

### Hook: EPL bar processing (MISSING — wire now)

After the existing 1m bar processing (after `det.on_bar_close_1m()`), add:

```python
if EPL_ENABLED and not self._has_open_trade():
    # Check expiry
    expired = _epl_watchlist.check_expiry(current_time)
    for sym in expired:
        _epl_registry.notify_expiry(sym)
        _epl_watchlist.remove(sym)

    # Feed bar to EPL strategies for graduated symbols
    if symbol in _epl_watchlist.symbols:
        sq_state = sq_det._state if sq_enabled else "IDLE"
        if _epl_arbitrator.can_epl_enter(symbol, sq_state, False, current_time):
            signals = _epl_registry.collect_entry_signals(symbol, bar_dict, None, None)
            best = _epl_arbitrator.get_best_signal(signals)
            if best:
                _execute_epl_entry(best, current_time)
```

Also feed bars to EPL strategies for exit management when in an EPL trade:

```python
if EPL_ENABLED and self._current_trade and self._current_trade.setup_type.startswith("epl_"):
    strategy = _epl_registry.get_strategy(self._current_trade.setup_type)
    if strategy:
        exit_sig = strategy.manage_exit(symbol, bar_dict["c"], bar_dict)
        if exit_sig:
            _execute_epl_exit(exit_sig, current_time)
```

### Hook: EPL tick processing (MISSING — wire now)

In the tick loop, after existing tick processing:

```python
# EPL tick-level entry trigger (ARMED → entry)
if EPL_ENABLED and not self._has_open_trade():
    if symbol in _epl_watchlist.symbols:
        sq_state = sq_det._state if sq_enabled else "IDLE"
        if _epl_arbitrator.can_epl_enter(symbol, sq_state, False, current_time):
            signals = _epl_registry.collect_entry_signals(symbol, None, price, size)
            best = _epl_arbitrator.get_best_signal(signals)
            if best:
                _execute_epl_entry(best, current_time)

# EPL tick-level exit management
if EPL_ENABLED and self._current_trade and self._current_trade.setup_type.startswith("epl_"):
    strategy = _epl_registry.get_strategy(self._current_trade.setup_type)
    if strategy:
        exit_sig = strategy.manage_exit(symbol, price, None)
        if exit_sig:
            _execute_epl_exit(exit_sig, current_time)
```

### Hook: EPL entry execution (MISSING — build now)

```python
def _execute_epl_entry(signal: EntrySignal, current_time):
    """Execute an EPL entry. Creates SimTrade with EPL strategy's setup_type."""
    shares = int((EPL_MAX_NOTIONAL * signal.position_size_pct) / signal.entry_price)
    if shares < 1:
        return

    t = SimTrade(
        symbol=signal.symbol,
        entry=signal.entry_price,
        stop=signal.stop_price,
        qty_total=shares,
        setup_type=signal.strategy,  # "epl_mp_reentry"
        entry_time=current_time,
    )
    # Mark strategy as in-trade
    strategy = _epl_registry.get_strategy(signal.strategy)
    if strategy:
        state = strategy._states.get(signal.symbol)
        if state:
            state._in_trade = True
            state._trail_stop = 0.0
            state._bars_in_trade = 0
            state._trade_peak = signal.entry_price
            state._bars_no_new_high = 0

    self._current_trade = t
    print(f"  [EPL] {signal.strategy} ENTRY {signal.symbol} @ ${signal.entry_price:.2f}, "
          f"stop=${signal.stop_price:.2f}, R={t.r:.4f}, shares={shares}, "
          f"reason={signal.reason}", flush=True)
```

### Hook: EPL exit execution (MISSING — build now)

```python
def _execute_epl_exit(signal: ExitSignal, current_time):
    """Execute an EPL exit. Close position, record P&L, notify arbitrator."""
    t = self._current_trade
    pnl = (signal.exit_price - t.entry) * t.qty_total * signal.exit_pct

    t.core_exit_price = signal.exit_price
    t.core_exit_reason = signal.exit_reason
    t.core_exit_time = str(current_time)

    # Record in arbitrator for session loss cap tracking
    _epl_arbitrator.record_epl_trade_result(signal.symbol, pnl)

    # Reset strategy state
    _epl_registry.reset_all(signal.symbol)

    self._close(t)
    print(f"  [EPL] {signal.strategy} EXIT {signal.symbol} @ ${signal.exit_price:.2f}, "
          f"reason={signal.exit_reason}, P&L=${pnl:.2f}", flush=True)
```

### Hook: Expiry check in bar loop

Add to the 1m bar processing section:

```python
if EPL_ENABLED:
    expired = _epl_watchlist.check_expiry(current_time)
    for sym in expired:
        _epl_registry.notify_expiry(sym)
        _epl_watchlist.remove(sym)
        if verbose:
            print(f"  [EPL] {sym} expired from watchlist", flush=True)
```

---

## Part 3: Wire EPL in bot_v3_hybrid.py (Live Trading)

Same pattern as simulate.py. The key integration points:

1. **Import & init** — Create EPLWatchlist, StrategyRegistry, PositionArbitrator, register EPLMPReentry
2. **Graduation hook** — In exit handler when `reason == "sq_target_hit"`, build GraduationContext and add
3. **Bar processing** — After SQ bar processing, feed bar to EPL strategies
4. **Tick processing** — Check for EPL ARMED triggers and exit management
5. **Entry execution** — Use existing order submission with EPL sizing
6. **Exit routing in trade_manager.py** — Add `if t.setup_type.startswith("epl_"):` route BEFORE squeeze routing (line 3022)

---

## Part 4: Add .env Vars

```bash
# === EPL: MP Re-Entry ===
WB_EPL_MP_ENABLED=0
WB_EPL_MP_COOLDOWN_BARS=3
WB_EPL_MP_MAX_PULLBACK_BARS=3
WB_EPL_MP_MIN_R=0.06
WB_EPL_MP_MACD_GATE=0
WB_EPL_MP_STOP_PAD=0.01
```

---

## Part 5: Testing

### Unit test: `test_epl_mp_reentry.py`

Test the strategy in isolation:
1. `on_graduation` → state transitions to WATCHING after cooldown
2. Pullback detection: red bar → PULLBACK, 2 red bars → count=2, 4 red bars → reset
3. Trigger validation: hammer → ARMED, shooting star → reset, strong close → ARMED
4. `on_tick` trigger break: price >= trigger_high → EntrySignal returned
5. Exit: hard stop, trail at 1.5R, VWAP loss, 5-bar time stop
6. Reset: phase back to WATCHING, cooldown applied

### Backtest: Known runners

Run against the 30 runner stocks from post-exit analysis. These are the stocks where we KNOW there was more to capture after 2R:

**Top priority (biggest runners with confirmed pullbacks):**
```bash
# STAK 2025-06-16 — +37.1R available, confirmed pullback
WB_EPL_ENABLED=1 WB_EPL_MP_ENABLED=1 python simulate.py STAK 2025-06-16 07:00 12:00 --ticks --tick-cache tick_cache/

# RDGT 2025-03-04 — +12.5R available, confirmed pullback
WB_EPL_ENABLED=1 WB_EPL_MP_ENABLED=1 python simulate.py RDGT 2025-03-04 07:00 12:00 --ticks --tick-cache tick_cache/

# ARTL 2026-03-18 — +9.8R available, confirmed pullback
WB_EPL_ENABLED=1 WB_EPL_MP_ENABLED=1 python simulate.py ARTL 2026-03-18 07:00 12:00 --ticks --tick-cache tick_cache/

# QNTM 2025-02-04 — +10.4R available, confirmed pullback
WB_EPL_ENABLED=1 WB_EPL_MP_ENABLED=1 python simulate.py QNTM 2025-02-04 07:00 12:00 --ticks --tick-cache tick_cache/

# BATL 2026-01-26 — +4.1R available, confirmed pullback
WB_EPL_ENABLED=1 WB_EPL_MP_ENABLED=1 python simulate.py BATL 2026-01-26 07:00 12:00 --ticks --tick-cache tick_cache/
```

**Also test the "done" stocks (should produce 0 EPL trades or small losses):**
```bash
# GV 2025-03-05 — only +0.4R post-exit (done stock)
WB_EPL_ENABLED=1 WB_EPL_MP_ENABLED=1 python simulate.py GV 2025-03-05 07:00 12:00 --ticks --tick-cache tick_cache/

# DRMA 2025-03-27 — pulled back below entry (done stock)
WB_EPL_ENABLED=1 WB_EPL_MP_ENABLED=1 python simulate.py DRMA 2025-03-27 07:00 12:00 --ticks --tick-cache tick_cache/
```

**For each stock, report:**
- Number of SQ trades and their P&L (should be unchanged from EPL_ENABLED=0)
- Number of EPL:MP entries and their P&L
- Entry price, stop price, exit price, exit reason for each EPL trade
- Total combined P&L (SQ + EPL)

### Regression: SQ unchanged

Run VERO 2026-01-16 with EPL ON. SQ behavior must be identical to EPL OFF:
```bash
# EPL ON, no strategies should fire (VERO hits target, EPL watches, but MP re-entry may or may not trigger)
WB_EPL_ENABLED=1 WB_EPL_MP_ENABLED=1 WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
```

Compare SQ trades and P&L to baseline. SQ portion must be unchanged. Any EPL trades are additive.

---

## What NOT To Do

1. **Do NOT modify micro_pullback.py.** Build `epl_mp_reentry.py` as a new file. The existing MP V2 code stays untouched.
2. **Do NOT use SQ exits for EPL trades.** The whole point is that EPL strategies have their own exit logic. Route EPL exits through the strategy's `manage_exit()`, not through `_squeeze_manage_exits()`.
3. **Do NOT bind to old regression targets.** This is a new system — evaluate it on its own merits.
4. **Do NOT change SQ behavior.** EPL is additive. When EPL is OFF, everything must work identically to before.

---

## Logging

All log lines prefixed with `[EPL:MP]`:
- `[EPL:MP] STAK graduated → WATCHING (cooldown=3 bars)`
- `[EPL:MP] STAK PULLBACK started (bar low=4.20)`
- `[EPL:MP] STAK ARMED: trigger=4.35, stop=4.19, R=0.16`
- `[EPL:MP] STAK ENTRY SIGNAL @ 4.36 (break 4.35)`
- `[EPL:MP] STAK EXIT: epl_mp_trail_exit(R=3.2), P&L=$520.00`
- `[EPL:MP] STAK RESET: pullback too long (4 bars)`
- `[EPL:MP] Session loss cap hit ($-1,050). EPL dormant.`

---

## Deliverables

1. `epl_mp_reentry.py` — Full strategy implementation
2. Execution hooks wired in `simulate.py` (entry collection, exit routing, entry/exit execution, expiry check)
3. Execution hooks wired in `bot_v3_hybrid.py` / `trade_manager.py`
4. `.env` additions (6 new vars)
5. `test_epl_mp_reentry.py` — Unit tests
6. Backtest results for 5+ runner stocks + 2 done stocks
7. VERO regression check (SQ unchanged)

## Commit

Single commit:
```
Add EPL MP Re-Entry strategy + wire execution hooks

First EPL strategy: detects micro-pullback re-entry after SQ 2R graduation.
Own exits (hard stop, 1.5R trail, VWAP loss, time stop). Wires up the
missing EPL execution hooks in simulate.py (entry/exit/expiry).

WB_EPL_MP_ENABLED=0 by default. Backtest results for N runner stocks included.
```
