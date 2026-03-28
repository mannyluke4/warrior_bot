# Directive: Implement MP V2 — Post-Squeeze Re-Entry
## Priority: HIGH — Target Monday deployment alongside SQ
## Date: 2026-03-27
## Design Doc: `STRATEGY_MP_V2_REENTRY_DESIGN.md`

---

## Context

Standalone MP is dead (-$8,066, 24% WR, 15 months). But the concept — catching pullback re-entries on confirmed movers — is exactly what Ross does after his initial squeeze scalp. EEIQ: Ross made $37.8K, mostly from re-entries after the initial breakout. MP V2 redesigns the detector as a post-squeeze re-entry module.

**Key principle:** MP V2 does NOTHING until the squeeze detector says "this stock is in play."

---

## Implementation Steps

### Step 1: Add Unlock/Cooldown State to MicroPullbackDetector

In `micro_pullback.py`:

```python
# New state variables in __init__():
self._sq_confirmed: bool = False       # Unlocked by squeeze trade close
self._cooldown_bars_remaining: int = 0  # Bars to wait before active detection
self._reentry_count: int = 0           # Re-entries taken this session
self._mp_v2_enabled = os.getenv("WB_MP_V2_ENABLED", "0") == "1"
self._reentry_cooldown = int(os.getenv("WB_MP_REENTRY_COOLDOWN_BARS", "3"))
self._max_reentries = int(os.getenv("WB_MP_MAX_REENTRIES", "3"))
self._reentry_macd_gate = os.getenv("WB_MP_REENTRY_MACD_GATE", "0") == "1"
self._reentry_use_sq_exits = os.getenv("WB_MP_REENTRY_USE_SQ_EXITS", "1") == "1"
self._reentry_min_r = float(os.getenv("WB_MP_REENTRY_MIN_R", "0.06"))
```

Add unlock method (called by simulate.py/bot_ibkr.py when SQ trade closes):
```python
def notify_squeeze_closed(self, symbol: str, pnl: float):
    """Called when a squeeze trade closes. Unlocks MP V2 re-entry detection."""
    if not self._mp_v2_enabled:
        return
    self._sq_confirmed = True
    self._cooldown_bars_remaining = self._reentry_cooldown
```

### Step 2: Gate on_bar_close_1m() for V2 Mode

At the TOP of `on_bar_close_1m()`, after indicator updates but before entry logic:

```python
# MP V2 gate: if V2 is enabled, standalone MP logic is bypassed entirely.
# V2 only runs when squeeze has confirmed the stock.
if self._mp_v2_enabled:
    if not self._sq_confirmed:
        return None  # Stay dormant
    if self._cooldown_bars_remaining > 0:
        self._cooldown_bars_remaining -= 1
        return f"MP_V2 COOLDOWN ({self._cooldown_bars_remaining} bars remaining)"
    if self._reentry_count >= self._max_reentries:
        return f"MP_V2 MAX_REENTRIES ({self._reentry_count}/{self._max_reentries})"
    # Fall through to detection logic, but use V2-specific behavior...
```

### Step 3: Skip Impulse Detection for V2

In `_pullback_entry_check()` (or wherever the impulse→pullback→confirm cycle runs), when `self._mp_v2_enabled and self._sq_confirmed`:

- Skip the impulse requirement. The squeeze was the impulse.
- Go directly to looking for pullback bars (red/lower-close bars after the squeeze exit).
- The first pullback bar starts the pullback counter.
- Confirm on green recovery candle (same as current logic).

**Suggested approach:** Set `self.in_impulse_1m = True` when `_sq_confirmed` activates. This lets the existing pullback→confirm logic run without needing a new impulse.

### Step 4: Relax MACD Gate for V2

When `self._mp_v2_enabled`:
- Change `self.macd_hard_gate` behavior: MACD bearish cross should NOT reset structure. After a squeeze, MACD going bearish IS the pullback we want to buy.
- Use `self._reentry_macd_gate` (default OFF) to control this. When OFF, MACD resets are suppressed for post-squeeze entries.

### Step 5: Tag Re-Entry Trades

When MP V2 creates an `ArmedTrade`:
```python
self.armed = ArmedTrade(
    trigger_high=trigger_high,
    stop_low=stop_low,
    entry_price=entry,
    r=r,
    score=score,
    score_detail=detail,
    setup_type="mp_reentry",  # NEW TAG
    size_mult=0.5 if self._reentry_count == 0 else 1.0,  # Probe first, full after
)
```

### Step 6: Route Exits in simulate.py / bot_ibkr.py

In the exit routing logic, when `setup_type == "mp_reentry"`:
- Route through `_squeeze_exit()` (V1 mechanical exits), NOT the MP 10s bar exits
- This gives re-entries the same exit treatment as squeeze trades: dollar loss cap → hard stop → tiered max_loss → pre-target trail → 2R target → runner trail

### Step 7: Wire notify_squeeze_closed in simulate.py / bot_ibkr.py

Where SQ trades are closed (in `_check_exit()` or wherever `sq_det.notify_trade_closed()` is called):
```python
# After squeeze trade closes:
sq_det.notify_trade_closed(symbol, pnl)
mp_det.notify_squeeze_closed(symbol, pnl)  # NEW — unlocks MP V2
```

### Step 8: Track Re-Entry Count

When an MP V2 trade closes:
```python
if t.setup_type == "mp_reentry":
    mp_det._reentry_count += 1
```

---

## Testing

### Regression 1: SQ-Only Unchanged
```bash
# These must still pass — MP V2 OFF by default, SQ should be unaffected:
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

### Regression 2: MP V2 Adds Value on Known Winners
```bash
# Run with MP V2 enabled alongside SQ:
WB_MP_V2_ENABLED=1 WB_SQUEEZE_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: ≥ $18,583 (SQ trade + MP re-entries on pullbacks)

WB_MP_V2_ENABLED=1 WB_SQUEEZE_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: ≥ $6,444

# EEIQ — the EEIQ comparison target. Run in bar mode (no tick cache for EEIQ):
WB_MP_V2_ENABLED=1 WB_SQUEEZE_ENABLED=1 python simulate.py EEIQ 2026-03-26 07:00 12:00
# Expected: SQ entry + at least 1 MP V2 re-entry on pullback
```

### Regression 3: MP V2 Does Nothing on Quiet Days
```bash
# Run on March 27 candidates (SQ didn't fire):
WB_MP_V2_ENABLED=1 WB_SQUEEZE_ENABLED=1 python simulate.py ONCO 2026-03-27 07:00 12:00
WB_MP_V2_ENABLED=1 WB_SQUEEZE_ENABLED=1 python simulate.py ARTL 2026-03-27 07:00 12:00
# Expected: 0 MP V2 trades (SQ didn't fire → MP stays dormant)
```

### Regression 4: No Standalone MP Trades
```bash
# Verify old MP behavior is fully gated:
WB_MP_V2_ENABLED=1 WB_MP_ENABLED=0 WB_SQUEEZE_ENABLED=0 python simulate.py EEIQ 2026-03-26 07:00 12:00
# Expected: 0 trades (SQ off → MP V2 never unlocks, standalone MP off)
```

---

## Env Vars Summary

```bash
WB_MP_V2_ENABLED=0                # Master gate — OFF by default
WB_MP_REENTRY_COOLDOWN_BARS=3     # Bars after SQ exit before MP V2 looks
WB_MP_MAX_REENTRIES=3             # Max re-entries per symbol per session
WB_MP_REENTRY_MIN_R=0.06          # Wider min R than standalone MP (0.03)
WB_MP_REENTRY_MACD_GATE=0         # MACD hard gate OFF for re-entries
WB_MP_REENTRY_USE_SQ_EXITS=1      # Route through SQ V1 exit system
WB_MP_REENTRY_PROBE_SIZE=0.5      # First re-entry at 50% size
```

---

## Important Notes

- `WB_MP_ENABLED` (standalone MP) stays OFF. It's a separate gate from `WB_MP_V2_ENABLED`.
- The SQ detector needs NO changes. MP V2 consumes signals the SQ detector already emits.
- All new env vars default to OFF or conservative values. Zero behavior change until explicitly enabled.
- The `setup_type="mp_reentry"` tag is critical for exit routing. Do not reuse "micro_pullback".
