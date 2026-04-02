# Directive: Build EPL Framework (Extended Play List)

## Priority: P0
## Prereqs: Read `ARCHITECTURE_EXTENDED_PLAY_LIST.md` first — that's the design doc this implements.

---

## Context

When SQ hits its 2R target, 86% of those stocks are runners. Instead of trying to hold through the run, we take full profit at 2R and add the stock to an Extended Play List (EPL). Independent strategies then watch the EPL for re-entry setups with their own entries, stops, and exits.

This directive builds the **framework only** — the graduation hook, watchlist, strategy registry, and position arbitrator. No actual strategies yet (MP re-entry will be a separate directive).

---

## What To Build

### File: `epl_framework.py` (NEW)

This is the entire EPL framework in one file. Keep it self-contained.

#### 1. GraduationContext dataclass

```python
@dataclass
class GraduationContext:
    symbol: str
    graduation_time: datetime          # When SQ exited at 2R
    graduation_price: float            # Price at SQ 2R exit
    sq_entry_price: float              # Original SQ entry
    sq_stop_price: float               # Original SQ stop
    hod_at_graduation: float           # Session HOD when graduated
    vwap_at_graduation: float          # VWAP level at graduation
    pm_high: float                     # Premarket high
    avg_volume_at_graduation: float    # Running avg vol
    sq_trade_count: int                # How many SQ trades on this symbol so far
    r_value: float                     # Dollar value of 1R (entry - stop)
```

#### 2. EntrySignal and ExitSignal dataclasses

```python
@dataclass
class EntrySignal:
    symbol: str
    strategy: str              # Which EPL strategy name
    entry_price: float         # Limit or market
    stop_price: float          # Strategy's own stop
    target_price: Optional[float]  # Strategy's own target (None = trail-only)
    position_size_pct: float   # 1.0 = full EPL max notional
    reason: str                # Human-readable entry reason
    confidence: float          # 0-1 score for prioritization

@dataclass
class ExitSignal:
    symbol: str
    strategy: str
    exit_price: float
    exit_reason: str           # Strategy-specific reason
    exit_pct: float            # 1.0 = full exit, 0.5 = half
```

#### 3. EPLStrategy abstract base class

```python
class EPLStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def priority(self) -> int: ...

    @abstractmethod
    def on_graduation(self, ctx: GraduationContext) -> None: ...

    @abstractmethod
    def on_expiry(self, symbol: str) -> None: ...

    @abstractmethod
    def on_bar(self, symbol: str, bar: dict) -> Optional[EntrySignal]: ...

    @abstractmethod
    def on_tick(self, symbol: str, price: float, size: int) -> Optional[EntrySignal]: ...

    @abstractmethod
    def manage_exit(self, symbol: str, price: float, bar: Optional[dict]) -> Optional[ExitSignal]: ...

    @abstractmethod
    def reset(self, symbol: str) -> None: ...
```

#### 4. EPLWatchlist class

```python
class EPLWatchlist:
    def __init__(self, max_stocks: int, expiry_minutes: int):
        self._graduated: Dict[str, GraduationContext] = {}
        self._graduation_times: Dict[str, datetime] = {}
        self.max_stocks = max_stocks
        self.expiry_minutes = expiry_minutes

    def add(self, ctx: GraduationContext) -> None:
        """Add stock to EPL. If at max capacity, evict oldest. If symbol already present, update context (re-graduation)."""

    def remove(self, symbol: str) -> None:
        """Remove stock from EPL."""

    def is_graduated(self, symbol: str) -> bool:
        """Check if symbol is on EPL."""

    def get_context(self, symbol: str) -> Optional[GraduationContext]:
        """Get graduation context for symbol."""

    def check_expiry(self, current_time: datetime) -> List[str]:
        """Return list of symbols that have expired. Caller should remove them and notify strategies."""

    @property
    def symbols(self) -> List[str]:
        """All currently graduated symbols."""
```

#### 5. StrategyRegistry class

```python
class StrategyRegistry:
    def __init__(self):
        self._strategies: List[EPLStrategy] = []

    def register(self, strategy: EPLStrategy) -> None:
        """Add strategy, keep sorted by priority (highest first)."""

    def notify_graduation(self, ctx: GraduationContext) -> None:
        """Notify all strategies of a new graduation."""

    def notify_expiry(self, symbol: str) -> None:
        """Notify all strategies that a symbol expired from EPL."""

    def collect_entry_signals(self, symbol: str, bar: Optional[dict], tick_price: Optional[float], tick_size: Optional[int]) -> List[EntrySignal]:
        """Collect entry signals from all strategies for a symbol. Return sorted by confidence (highest first)."""

    def get_strategy(self, name: str) -> Optional[EPLStrategy]:
        """Look up strategy by name."""

    def reset_all(self, symbol: str) -> None:
        """Reset all strategies for a symbol (position closed)."""
```

#### 6. PositionArbitrator class

```python
class PositionArbitrator:
    def __init__(self, registry: StrategyRegistry, watchlist: EPLWatchlist):
        self._registry = registry
        self._watchlist = watchlist
        self._epl_session_pnl: float = 0.0  # Track EPL P&L for session loss cap
        self._epl_trade_count: Dict[str, int] = {}  # Per-symbol EPL trade count
        self._cooldown_until: Dict[str, datetime] = {}  # Per-symbol cooldown

    def can_epl_enter(self, symbol: str, sq_state: str, has_open_position: bool, current_time: datetime) -> bool:
        """
        Check all preconditions for EPL entry:
        1. EPL enabled (WB_EPL_ENABLED=1)
        2. Symbol is on EPL watchlist
        3. No open position (any strategy)
        4. SQ is not PRIMED or ARMED on this symbol (SQ priority)
        5. Cooldown expired for this symbol
        6. EPL session loss cap not breached
        7. Trade count for this symbol < max per graduation
        """

    def get_best_signal(self, signals: List[EntrySignal]) -> Optional[EntrySignal]:
        """Return highest-confidence signal, or None if none pass filters."""

    def record_epl_trade_result(self, symbol: str, pnl: float) -> None:
        """Update session P&L and trade count after EPL trade closes."""

    @property
    def session_loss_cap_hit(self) -> bool:
        """True if EPL session P&L <= -WB_EPL_MAX_LOSS_SESSION."""
```

#### 7. Env vars (read from os.environ with defaults)

```python
EPL_ENABLED = int(os.environ.get("WB_EPL_ENABLED", "0"))
EPL_MAX_STOCKS = int(os.environ.get("WB_EPL_MAX_STOCKS", "5"))
EPL_EXPIRY_MINUTES = int(os.environ.get("WB_EPL_EXPIRY_MINUTES", "60"))
EPL_MIN_GRADUATION_R = float(os.environ.get("WB_EPL_MIN_GRADUATION_R", "2.0"))
EPL_SQ_PRIORITY = int(os.environ.get("WB_EPL_SQ_PRIORITY", "1"))
EPL_COOLDOWN_BARS = int(os.environ.get("WB_EPL_COOLDOWN_BARS", "3"))
EPL_MAX_TRADES_PER_GRAD = int(os.environ.get("WB_EPL_MAX_TRADES_PER_GRAD", "3"))
EPL_MAX_NOTIONAL = float(os.environ.get("WB_EPL_MAX_NOTIONAL", os.environ.get("WB_MAX_NOTIONAL", "50000")))
EPL_MAX_LOSS_SESSION = float(os.environ.get("WB_EPL_MAX_LOSS_SESSION", "1000"))
```

**EPL_MAX_NOTIONAL defaults to WB_MAX_NOTIONAL** — same sizing as SQ per Manny's decision.

---

## Integration: simulate.py

### Hook 1: Graduation on sq_target_hit

In `_squeeze_tick_exits()`, after the existing `sq_target_hit` handling (around line 710-721), add:

```python
# After setting t.core_exit_reason = "sq_target_hit" and t.tp_hit = True:
if EPL_ENABLED and t.core_exit_reason == "sq_target_hit":
    realized_r = (price - t.entry) / t.r if t.r > 0 else 0
    if realized_r >= EPL_MIN_GRADUATION_R:
        ctx = GraduationContext(
            symbol=t.symbol,
            graduation_time=current_time,   # Parse from time_str
            graduation_price=price,
            sq_entry_price=t.entry,
            sq_stop_price=t.stop,
            hod_at_graduation=self._bar_builder.session_hod,  # Or however HOD is tracked
            vwap_at_graduation=self._bar_builder.vwap,
            pm_high=self._bar_builder.pm_high,
            avg_volume_at_graduation=self._bar_builder.avg_volume,  # May need to compute
            sq_trade_count=self._sq_trade_count.get(t.symbol, 1),
            r_value=t.r,
        )
        self._epl_watchlist.add(ctx)
        self._epl_registry.notify_graduation(ctx)
        log(f"[EPL] {t.symbol} graduated at ${price:.2f} (R={realized_r:.1f})")
```

**Important**: The graduation happens when `tp_hit` is set, which means the core position exits but a runner may still be held. That's fine — the EPL strategies won't enter while there's an open position (runner), and once the runner exits, EPL cooldown starts.

### Hook 2: EPL bar processing

In the main bar loop (around line 2748, after `det.on_bar_close_1m()`), add:

```python
if EPL_ENABLED:
    # Check expiry
    expired = self._epl_watchlist.check_expiry(current_time)
    for sym in expired:
        self._epl_registry.notify_expiry(sym)
        self._epl_watchlist.remove(sym)
        log(f"[EPL] {sym} expired from watchlist")

    # Collect EPL entry signals for graduated symbols
    if not self._has_open_position():  # No position from any strategy
        for epl_sym in self._epl_watchlist.symbols:
            if epl_sym == symbol:  # Only process current symbol's bar
                sq_state = self._sq_detectors[symbol]._state if symbol in self._sq_detectors else "IDLE"
                if self._epl_arbitrator.can_epl_enter(symbol, sq_state, False, current_time):
                    signals = self._epl_registry.collect_entry_signals(symbol, bar, None, None)
                    best = self._epl_arbitrator.get_best_signal(signals)
                    if best:
                        self._execute_epl_entry(best)
```

### Hook 3: EPL tick processing

In the tick loop (around line 2792, after `det.on_trade_price()`), if there's an open EPL position:

```python
if EPL_ENABLED and self._current_trade and self._current_trade.setup_type.startswith("epl_"):
    strategy = self._epl_registry.get_strategy(self._current_trade.setup_type)
    if strategy:
        exit_sig = strategy.manage_exit(symbol, price, None)
        if exit_sig:
            self._execute_epl_exit(exit_sig)
```

### Hook 4: EPL entry execution

New method:

```python
def _execute_epl_entry(self, signal: EntrySignal):
    """Execute an EPL entry. Creates a SimTrade with setup_type = signal.strategy."""
    # Calculate shares from EPL_MAX_NOTIONAL and signal.position_size_pct
    shares = int((EPL_MAX_NOTIONAL * signal.position_size_pct) / signal.entry_price)
    if shares < 1:
        return

    # Create SimTrade
    t = SimTrade(
        symbol=signal.symbol,
        entry=signal.entry_price,
        stop=signal.stop_price,
        qty_total=shares,
        setup_type=signal.strategy,  # e.g. "epl_mp_reentry", "epl_vwap_reclaim"
        # ... other fields
    )
    self._current_trade = t
    log(f"[EPL] {signal.strategy} ENTRY {signal.symbol} @ ${signal.entry_price:.2f}, "
        f"stop=${signal.stop_price:.2f}, reason={signal.reason}")
```

### Hook 5: EPL exit execution

New method:

```python
def _execute_epl_exit(self, signal: ExitSignal):
    """Execute an EPL exit. Closes position and records P&L."""
    t = self._current_trade
    pnl = (signal.exit_price - t.entry) * t.qty_total * signal.exit_pct
    self._epl_arbitrator.record_epl_trade_result(signal.symbol, pnl)

    if signal.exit_pct >= 1.0:
        # Full exit
        t.core_exit_price = signal.exit_price
        t.core_exit_reason = signal.exit_reason
        self._close(t)
        self._epl_registry.reset_all(signal.symbol)
        log(f"[EPL] {signal.strategy} EXIT {signal.symbol} @ ${signal.exit_price:.2f}, "
            f"reason={signal.exit_reason}, P&L=${pnl:.2f}")
    # Partial exit handling if needed later
```

---

## Integration: bot_v3_hybrid.py

Same pattern as simulate.py but with async order handling:

### Hook 1: Graduation

In the exit handler where `reason == "sq_target_hit"`, build GraduationContext and add to watchlist. The bot already has access to `bar_builder` for VWAP/HOD/PM_HIGH.

### Hook 2: Bar processing

After SQ detector processes a bar, check EPL watchlist for entry signals. Same `can_epl_enter()` check.

### Hook 3: Exit routing

In `_manage_exits()` (trade_manager.py line 3022), add a route for EPL setup types:

```python
if t.setup_type.startswith("epl_"):
    strategy = self._epl_registry.get_strategy(t.setup_type)
    if strategy:
        exit_sig = strategy.manage_exit(symbol, float(bid), current_bar)
        if exit_sig:
            self._exit(symbol, qty=t.qty_total, reason=exit_sig.exit_reason, price=float(bid))
    return
```

This goes BEFORE the existing squeeze routing.

### Hook 4: Entry execution

Use existing `_enter()` or order submission logic, but with EPL sizing and the EPL strategy's stop/target.

---

## Integration: .env

Add these to `.env` (all OFF by default):

```bash
# === EPL Framework ===
WB_EPL_ENABLED=0
WB_EPL_MAX_STOCKS=5
WB_EPL_EXPIRY_MINUTES=60
WB_EPL_MIN_GRADUATION_R=2.0
WB_EPL_SQ_PRIORITY=1
WB_EPL_COOLDOWN_BARS=3
WB_EPL_MAX_TRADES_PER_GRAD=3
WB_EPL_MAX_NOTIONAL=50000
WB_EPL_MAX_LOSS_SESSION=1000
```

---

## What NOT To Do

1. **Do NOT build any actual strategies yet.** This directive is framework only. MP re-entry will be a separate directive.
2. **Do NOT modify SQ exit logic.** The graduation hook reads from the existing exit — it doesn't change what SQ does.
3. **Do NOT change single-position architecture.** EPL uses the same `open_position` / `_current_trade` slot. One position at a time.
4. **Do NOT add regression tests against old targets.** EPL is new — evaluate fresh.
5. **Do NOT change the runner trail.** After sq_target_hit, the existing runner trail logic continues as-is. EPL graduation happens at the moment of target hit, but EPL strategies can't enter until the runner position also closes.

---

## Testing

### Unit test: `test_epl_framework.py`

Write basic tests for:
1. `EPLWatchlist`: add, remove, expiry, max capacity eviction, re-graduation
2. `StrategyRegistry`: register, notify, collect signals sorted by confidence
3. `PositionArbitrator`: can_epl_enter checks (all 7 preconditions), session loss cap, trade count limit
4. `GraduationContext`: builds correctly from mock trade data

### Smoke test with simulate.py

Run VERO 2026-01-16 with `WB_EPL_ENABLED=1` (no strategies registered). Confirm:
- Graduation events fire on each sq_target_hit
- Log shows `[EPL] VERO graduated at $X.XX`
- No EPL entries (no strategies registered)
- SQ behavior is **identical** to EPL_ENABLED=0 (framework is passive)

---

## Logging

All EPL log lines prefixed with `[EPL]` for easy filtering:
- `[EPL] VERO graduated at $8.50 (R=2.1)` — graduation event
- `[EPL] VERO expired from watchlist` — expiry
- `[EPL] epl_mp_reentry ENTRY VERO @ $8.20, stop=$7.80, reason=pullback_break` — entry
- `[EPL] epl_mp_reentry EXIT VERO @ $9.10, reason=trail_stop, P&L=$450.00` — exit
- `[EPL] Session loss cap hit ($-1,050). EPL dormant.` — kill switch
- `[EPL] VERO blocked: SQ is ARMED (SQ priority)` — SQ priority

---

## Deliverables

1. `epl_framework.py` — all classes above
2. Integration hooks in `simulate.py` (graduation + bar/tick processing + entry/exit execution)
3. Integration hooks in `bot_v3_hybrid.py` / `trade_manager.py` (same pattern, async orders)
4. `.env` additions
5. `test_epl_framework.py` — unit tests
6. Smoke test: VERO with EPL_ENABLED=1, no strategies, confirms zero behavior change

---

## Commit

Single commit with message:
```
Add EPL framework: graduation hook, watchlist, strategy registry, position arbitrator

Framework for Extended Play List — when SQ hits 2R, stock graduates to
EPL watchlist. Independent strategies (not yet built) will plug into
this framework for re-entry with own entries/stops/exits.

WB_EPL_ENABLED=0 by default. No strategies registered = zero behavior change.
```
