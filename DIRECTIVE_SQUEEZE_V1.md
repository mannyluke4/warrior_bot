# Directive: Strategy 2 — Squeeze / Breakout Entry (V1)

## Priority: HIGH
## Owner: CC
## Created: 2026-03-19

---

## Context

The micro pullback strategy is solid. Now we're adding the **second strategy module**: squeeze/breakout entry. This captures the **first leg** of momentum moves that the micro pullback misses (MP waits for impulse → pullback → ARM; squeeze enters on the initial breakout).

**Reference**: `STRATEGY_2_SQUEEZE_DESIGN.md` has the full design spec with all decisions locked in.

**ARTL 2026-03-18 example**: MP caught $7.62→$7.92 (+0.9R). The squeeze would have caught $5.50→$7.50+ (~2.5R) on the initial run. Combined: ~3.4R.

This directive has **4 phases**. Implement them in order.

---

## Pre-Flight

```bash
cd ~/warrior_bot
source venv/bin/activate
git pull origin v6-dynamic-sizing
```

Read `STRATEGY_2_SQUEEZE_DESIGN.md` before starting. It has all the rationale and edge cases.

---

## Phase 1: Create `squeeze_detector.py`

### What
New file implementing the squeeze/breakout detector with the same interface as `MicroPullbackDetector`.

### State Machine

```
IDLE  →  PRIMED  →  ARMED  →  TRIGGERED
```

- **IDLE → PRIMED**: On 1m bar close when ALL of:
  - Bar volume ≥ `WB_SQ_VOL_MULT` (default 3.0) × average volume of prior 1m bars
  - Bar volume ≥ `WB_SQ_MIN_BAR_VOL` (default 50,000)
  - Current price > VWAP
  - Bar is green (close > open)
  - Bar body ≥ `WB_SQ_MIN_BODY_PCT` (default 1.5%) of price
  - NOT already in a trade on this symbol (check via callback or flag)

- **PRIMED → ARMED**: When price breaks a **key level** (checked in `WB_SQ_LEVEL_PRIORITY` order):
  - `pm_high`: premarket high (passed in via `update_premarket_levels()` or constructor)
  - `whole_dollar`: nearest whole dollar above the bar's open
  - `pdh`: prior day high (if available)
  - The break can happen on the same bar that caused PRIMED, or within next `WB_SQ_PRIME_BARS` (default 3) 1m bars
  - On ARM, create `ArmedTrade` with `setup_type="squeeze"`

- **PRIMED → RESET**: If `WB_SQ_PRIME_BARS` bars pass without breaking a key level, OR volume drops below threshold, OR price drops below VWAP

- **ARMED → TRIGGERED**: Via `on_trade_price()` when tick confirms the break (same as MP)

### ArmedTrade Fields
```python
ArmedTrade(
    trigger_high=key_level + 0.02,   # Small buffer above breakout level
    stop_low=stop_price,              # See stop logic below
    entry_price=key_level + 0.02,
    r=entry_price - stop_low,
    score=calculated_score,
    score_detail="squeeze: vol=X.Xx avg, level=pm_high, ...",
    setup_type="squeeze",
    size_mult=probe_mult,             # 0.5 for first attempt, 1.0 after a winner
)
```

### Stop Placement
- `stop = min(low of last 3 bars before breakout bar)` — gives room for volatile squeeze action
- Cap: if `R > WB_SQ_MAX_R` (default $0.80) or `R > price * 0.05` (5%), skip the trade (too risky)

### Score Calculation
Simple scoring for V1:
- Base: 5.0
- Volume multiple above threshold: +1.0 per extra multiple (e.g. 6x avg = +3.0)
- PM bull flag detected (`get_premarket_bull_flag_high()` is not None): +2.0
- Gap ≥ 20%: +1.0
- VWAP distance healthy (price 2-15% above VWAP): +1.0
- Price above PM high (strongest level): +1.0
- Cap at 15.0

### Env Vars (all read in `__init__`)
```python
self.enabled = os.getenv("WB_SQUEEZE_ENABLED", "0") == "1"
self.vol_mult = float(os.getenv("WB_SQ_VOL_MULT", "3.0"))
self.min_bar_vol = int(os.getenv("WB_SQ_MIN_BAR_VOL", "50000"))
self.min_body_pct = float(os.getenv("WB_SQ_MIN_BODY_PCT", "1.5"))
self.prime_bars = int(os.getenv("WB_SQ_PRIME_BARS", "3"))
self.max_r = float(os.getenv("WB_SQ_MAX_R", "0.80"))
self.level_priority = os.getenv("WB_SQ_LEVEL_PRIORITY", "pm_high,whole_dollar,pdh").split(",")
self.pm_confidence = os.getenv("WB_SQ_PM_CONFIDENCE", "1") == "1"
self.max_attempts = int(os.getenv("WB_SQ_MAX_ATTEMPTS", "3"))
self.probe_size_mult = float(os.getenv("WB_SQ_PROBE_SIZE_MULT", "0.5"))
```

### Required Interface (match MicroPullbackDetector)
```python
class SqueezeDetector:
    def __init__(self):
        self.symbol: str = ""
        self.armed: Optional[ArmedTrade] = None
        self.ema: float = 0.0
        self.enabled: bool  # from WB_SQUEEZE_ENABLED

    def seed_bar_close(self, o, h, l, c, v):
        """Warm up indicators (EMA, volume history). No signals."""

    def on_bar_close_1m(self, bar: dict, vwap: float = None) -> Optional[str]:
        """
        Primary detection on 1m bar closes.
        Returns None or "ARMED entry=X stop=Y R=Z score=S setup_type=squeeze ..."
        """

    def on_trade_price(self, price: float, is_premarket: bool = False) -> Optional[str]:
        """
        Check if armed setup triggers on this tick.
        Returns None or "ENTRY SIGNAL @ X.XX (break Y.YY) stop=Z.ZZ R=W.WW ..."
        """

    def update_premarket_levels(self, pm_high: float, pm_bf_high: Optional[float] = None):
        """Set premarket context. Called by bot/simulator after PM data loaded."""

    def notify_trade_closed(self, symbol: str, pnl: float):
        """Track win/loss for probe → full size logic and max attempts."""

    def reset(self):
        """Reset state for new day/stock."""
```

### Messages (verbose output)
Use same format conventions as micro_pullback.py so verbose logs are consistent:
```
[HH:MM] SQ_PRIMED: vol=X.Xx avg, price=$Y above VWAP ($Z)
[HH:MM] SQ_ARMED: entry=$X stop=$Y R=$Z score=S level=pm_high
[HH:MM] SQ_RESET: reason (volume_died / vwap_lost / prime_expired)
[HH:MM] SQ_NO_ARM: reason (max_r_exceeded / max_attempts / etc)
```

---

## Phase 2: Squeeze Exit Logic in `simulate.py`

### What
Add squeeze-specific exit handling in `SimTradeManager`. Route based on `setup_type`.

### Exit Rules for `setup_type == "squeeze"`

**Pre-target (full position):**
1. **Hard stop**: price ≤ stop_low → exit all (same as MP)
2. **Trailing stop**: price drops `WB_SQ_TRAIL_R` (default 1.5) × R below peak → exit all
3. **Time stop**: no new high in `WB_SQ_STALL_BARS` (default 5) consecutive 1m bars → exit all
4. **VWAP loss**: 1m bar closes below VWAP (if `WB_SQ_VWAP_EXIT=1`) → exit all

**Post-target (partial exit — core + runner split):**
5. When price reaches `WB_SQ_TARGET_R` (default 2.0) × R above entry:
   - Exit core shares (`WB_SQ_CORE_PCT` = 75% of position)
   - Keep runner shares (25%)
   - Move runner stop to breakeven
6. **Runner trailing stop**: price drops `WB_SQ_RUNNER_TRAIL_R` (default 2.5) × R below peak → exit runner
7. **Runner VWAP loss**: same as #4 but only for remaining runner shares
8. **Runner time stop**: same as #3 but only for runner

### Implementation Notes

The `SimTrade` dataclass already has `qty_core` and `qty_runner` fields. For squeeze trades:
- Set `qty_core = int(total * WB_SQ_CORE_PCT / 100)`
- Set `qty_runner = total - qty_core`
- This mirrors how 3-tranche mode works but with different percentages and exit rules

Add these env vars to `SimTradeManager.__init__`:
```python
self.sq_trail_r = float(os.getenv("WB_SQ_TRAIL_R", "1.5"))
self.sq_stall_bars = int(os.getenv("WB_SQ_STALL_BARS", "5"))
self.sq_target_r = float(os.getenv("WB_SQ_TARGET_R", "2.0"))
self.sq_core_pct = int(os.getenv("WB_SQ_CORE_PCT", "75"))
self.sq_runner_trail_r = float(os.getenv("WB_SQ_RUNNER_TRAIL_R", "2.5"))
self.sq_vwap_exit = os.getenv("WB_SQ_VWAP_EXIT", "1") == "1"
```

Route exit logic in `on_tick()` and `on_bar_close()`:
```python
if trade.setup_type == "squeeze":
    self._check_squeeze_exits(trade, price, time_str, vwap, ...)
else:
    # existing MP exit logic (unchanged)
```

### Verbose Output
```
[HH:MM] SQ_TRAIL_EXIT @ $X.XX (peak=$Y.YY, trail=Z.ZR)
[HH:MM] SQ_TIME_EXIT @ $X.XX (N bars no new high)
[HH:MM] SQ_VWAP_EXIT @ $X.XX (close below VWAP $Y.YY)
[HH:MM] SQ_TARGET_HIT @ $X.XX (+Z.ZR) — core exit, runner trailing
[HH:MM] SQ_RUNNER_EXIT @ $X.XX (trail/vwap/time)
```

---

## Phase 3: Wire Into `simulate.py`

### What
Instantiate squeeze detector alongside micro pullback detector, feed both the same bar/tick data.

### Integration Points

**1. Instantiation (after line ~1147):**
```python
det = MicroPullbackDetector()
det.symbol = symbol

# Squeeze detector
from squeeze_detector import SqueezeDetector
sq_det = SqueezeDetector()
sq_det.symbol = symbol
sq_enabled = os.getenv("WB_SQUEEZE_ENABLED", "0") == "1"
```

**2. Seed phase — feed both detectors:**
```python
det.seed_bar_close(o, h, l, c, v)
if sq_enabled:
    sq_det.seed_bar_close(o, h, l, c, v)
```

**3. Premarket levels — pass to squeeze detector:**
After bar_builder computes PM high, pass it:
```python
if sq_enabled:
    pm_high = bar_builder.get_premarket_high(symbol)
    pm_bf = bar_builder.get_premarket_bull_flag_high(symbol)
    if pm_high:
        sq_det.update_premarket_levels(pm_high, pm_bf)
```

**4. 1m bar close — feed both, check squeeze first:**
```python
# Existing MP detection
msg = det.on_bar_close_1m(bar_dict, vwap=vwap)

# Squeeze detection (only if not already in a trade)
sq_msg = None
if sq_enabled and not sim_mgr.has_open_trade(symbol):
    sq_msg = sq_det.on_bar_close_1m(bar_dict, vwap=vwap)
```

**5. Tick loop — check both armed states, squeeze priority:**
```python
# Check squeeze trigger first (priority over MP)
if sq_enabled and sq_det.armed is not None:
    sq_trigger = sq_det.on_trade_price(price, is_premarket=is_premarket)
    if sq_trigger and "ENTRY SIGNAL" in sq_trigger:
        # ... submit squeeze trade (same flow as MP, but armed = sq_det.armed)
        # Pass setup_type="squeeze" through to SimTrade

# Then check MP trigger (only if squeeze didn't fire)
elif det.armed is not None:
    trigger_msg = det.on_trade_price(price, is_premarket=is_premarket)
    # ... existing MP flow
```

**6. Conflict resolution:**
- If squeeze enters, set a flag so MP doesn't also arm: `mp_blocked_by_squeeze = True`
- After squeeze exits, clear flag: `mp_blocked_by_squeeze = False`
- Pass squeeze trade close info back: `sq_det.notify_trade_closed(symbol, pnl)`

**7. VWAP pass-through for squeeze exits:**
The squeeze exit logic needs current VWAP. It's already available from `bar_builder.vwap(symbol)`. Pass it to `sim_mgr` on each 1m bar close.

### Do NOT change
- The existing MP detection flow
- The existing exit logic for `setup_type == "micro_pullback"`
- Any env var defaults that would affect MP behavior
- The regression targets (VERO +$18,583, ROLR +$6,444)

---

## Phase 4: Backtest Validation

### Test 1: Regression (squeeze OFF)
Squeeze is OFF by default. Verify MP unchanged:
```bash
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

### Test 2: ARTL with squeeze ON
```bash
WB_SQUEEZE_ENABLED=1 python simulate.py ARTL 2026-03-18 07:00 12:00 --ticks --tick-cache tick_cache/ -v 2>&1 | head -80
```
**Expected**: See `SQ_PRIMED` and `SQ_ARMED` messages in the first 10 minutes. Squeeze entry around $5-6 range. Squeeze exit with positive P&L. MP may still fire later for continuation.

### Test 3: VERO with squeeze ON
```bash
WB_SQUEEZE_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/ -v 2>&1 | head -80
```
**Expected**: Squeeze may fire on early VERO move. If it does, it should produce a positive trade. MP should still fire for the big continuation move. Total P&L should be ≥ MP-only P&L.

### Test 4: Key dates batch (squeeze ON)
```bash
WB_SQUEEZE_ENABLED=1 python run_key_dates_backtest.py
```
Compare total P&L vs squeeze-OFF baseline ($50,411). Report both numbers.

---

## Regression

**CRITICAL**: After all changes, squeeze OFF must reproduce:
```bash
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```
- VERO: +$18,583
- ROLR: +$6,444

If these change, something leaked. Roll back and investigate.

---

## Post-Flight

```bash
git add squeeze_detector.py simulate.py
git commit -m "Strategy 2: Squeeze/breakout detector + simulator integration

Phase 1: squeeze_detector.py — IDLE→PRIMED→ARMED state machine
  - Volume explosion (3x avg) + VWAP + key level break detection
  - Configurable level priority (pm_high, whole_dollar, pdh)
  - Probe sizing (0.5x) on first attempts, 3 max attempts per stock
  - PM confidence scoring (bull flag, gap size, volume trend)
Phase 2: Squeeze exit logic in SimTradeManager
  - Trailing stop (1.5R), time stop (5 bars), VWAP loss exit
  - Core+runner partial exits (75/25 split at 2R target)
  - Separate from MP exits — routed by setup_type field
Phase 3: Simulator wiring — both detectors consume same feed
  - Squeeze priority over MP, conflict resolution
  - After squeeze exit, MP can ARM for continuation

All gated by WB_SQUEEZE_ENABLED=0 (OFF by default)
MP regression unchanged: VERO +\$18,583, ROLR +\$6,444

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin v6-dynamic-sizing
```

---

## Notes for CC

- **Do NOT touch `micro_pullback.py`** — squeeze is a separate module
- **Do NOT touch `trade_manager.py` yet** — squeeze exits go in `simulate.py`'s `SimTradeManager` first. We'll port to live `trade_manager.py` after backtest validation.
- **Import `ArmedTrade` from `micro_pullback.py`** — reuse the dataclass, don't duplicate it
- The `bars.py` `TradeBarBuilder` already tracks premarket high, VWAP, HOD — use those
- If ARTL tick cache doesn't exist yet, the sim will fall back to API (slow but works)
- Read `STRATEGY_2_SQUEEZE_DESIGN.md` for full rationale on every decision
