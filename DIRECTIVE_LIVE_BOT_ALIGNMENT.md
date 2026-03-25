# DIRECTIVE: Live Bot ↔ Backtest Alignment

**Author**: Cowork (Opus)
**Date**: 2026-03-24
**For**: CC (Sonnet)
**Priority**: P0 — Without this, the live bot cannot take any trades
**Reference**: `cowork_reports/2026-03-24_live_bot_audit.md` (full audit)

---

## Problem

The live bot (bot.py + trade_manager.py) is fundamentally misaligned with the backtesting engine (simulate.py):

1. **No SqueezeDetector in bot.py** — the primary strategy (70% WR, +$118K megatest) doesn't exist in the live bot
2. **No squeeze exit logic in trade_manager.py** — sq_target_hit, squeeze trailing stop, dollar loss cap are all missing
3. **No bail timer in simulate.py** — live bot exits after 5 min unprofitable, backtest lets trades linger
4. **TradePlan/OpenTrade missing setup_type** — trade_manager treats everything as micro_pullback
5. **parse_plan() doesn't extract setup_type** — even though squeeze_detector emits `setup_type=squeeze` in its message

The net result: **WB_MP_ENABLED=0 and no squeeze = bot takes zero trades.**

---

## Step 0: Git Pull

```bash
cd /Users/mannyluke/warrior_bot
git pull
source venv/bin/activate
```

---

## Task 1: Wire SqueezeDetector into bot.py

### 1a: Add imports and global state

At the top of bot.py (near the existing MicroPullbackDetector import, ~line 17):

```python
from squeeze_detector import SqueezeDetector
```

Add global state (near the existing `detectors` dict, ~line 239):

```python
sq_detectors: dict[str, SqueezeDetector] = {}

def ensure_sq_detector(symbol: str) -> SqueezeDetector:
    if symbol not in sq_detectors:
        sq_det = SqueezeDetector()
        sq_det.symbol = symbol
        # Pass gap_pct for conviction floor gate
        info = _stock_info_cache.get(symbol)
        if info and hasattr(info, 'gap_pct'):
            sq_det.gap_pct = info.gap_pct
        sq_detectors[symbol] = sq_det
        print(f"SqueezeDetector created for {symbol}", flush=True)
    return sq_detectors[symbol]
```

Add the strategy gate (near MP_ENABLED, ~line 45):

```python
SQ_ENABLED = os.getenv("WB_SQUEEZE_ENABLED", "0") == "1"
```

### 1b: Seed squeeze detector on symbol subscribe

In `seed_symbol_from_history()` (~line 198-214), after the existing `det.seed_bar_close(...)` call, add:

```python
            if SQ_ENABLED:
                sq_det = ensure_sq_detector(symbol)
                sq_det.seed_bar_close(o, h, l, c, v)
```

### 1c: Feed 1m bars to squeeze detector

In `on_bar_close_1m()` (~line 413), after `msg = det.on_bar_close_1m(bar, vwap=vwap)`, add squeeze 1m bar processing:

```python
    # Squeeze detector: 1m bar processing
    if SQ_ENABLED:
        sq_det = ensure_sq_detector(symbol)
        # Feed premarket levels
        if bar_builder:
            sq_det.update_premarket_levels(pm_high, pm_bf_high)
        sq_msg = sq_det.on_bar_close_1m(bar, vwap=vwap)
        if sq_msg:
            log_event("signal_1m_squeeze", symbol, msg=sq_msg, close=bar.close, vwap=vwap)
            if PRINT_ARMED_ONLY and sq_msg.startswith("ARMED"):
                now_et_str = datetime.now(ET).strftime("%H:%M:%S")
                print(f"[{now_et_str} ET] {symbol} SQ | {sq_msg}", flush=True)
```

### 1d: Feed tick prices to squeeze detector for trigger

In `on_trade()` (~line 575-602), the existing code feeds `det.on_trade_price(price)` and checks for MP entry signals. Add squeeze trigger check BEFORE the MP check (squeeze has priority, same as simulate.py):

```python
        # --- Squeeze trigger (priority over MP) ---
        if SQ_ENABLED and trade_manager:
            sq_det = ensure_sq_detector(symbol)
            sq_armed_before = sq_det.armed  # Capture before trigger check
            sq_msg = sq_det.on_trade_price(price, is_premarket=in_premarket)
            if sq_msg and sq_msg.startswith("ENTRY SIGNAL") and sq_armed_before:
                now = datetime.now(ET).strftime("%H:%M:%S")
                print(f"[{now} ET] {symbol} SQ | {sq_msg}", flush=True)
                print(f"🟩 Sending SQ to trade_manager: {symbol}", flush=True)
                trade_manager.on_signal(symbol, sq_msg)
                sq_det.notify_trade_opened()
```

**IMPORTANT**: The squeeze trigger check must come BEFORE the existing MP `det.on_trade_price(price)` block, and should only fire if `trade_manager` has no open position on that symbol. Check simulate.py line 2502: `if sq_enabled and _sq_armed_before is not None and sim_mgr.open_trade is None:`. In bot.py, this translates to checking `symbol not in trade_manager.open and symbol not in trade_manager.pending`.

### 1e: Feed trade close notifications to squeeze detector

When a trade closes, the squeeze detector needs to know (for its per-symbol loss gate). In trade_manager.py, find where trade close events are logged and add a callback. The cleanest way: add an `on_trade_close_callbacks` list to `PaperTradeManager` and have bot.py register a callback at startup:

```python
# In bot.py, after trade_manager is initialized (~line 860):
def _on_live_trade_close(symbol, setup_type, pnl):
    if SQ_ENABLED and setup_type == "squeeze":
        sq_det = ensure_sq_detector(symbol)
        sq_det.notify_trade_closed(symbol, pnl)

trade_manager.on_trade_close_callback = _on_live_trade_close
```

And in trade_manager.py, call `self.on_trade_close_callback(symbol, t.setup_type, realized_pnl)` when a trade is fully closed (in the `_exit` method or wherever the final position-closed event is logged).

---

## Task 2: Add setup_type to TradePlan and OpenTrade

### 2a: Update TradePlan dataclass (~line 123)

```python
@dataclass
class TradePlan:
    entry: float
    stop: float
    r: float
    take_profit: float
    score: float = 0.0
    setup_type: str = "micro_pullback"  # NEW: "squeeze", "vwap_reclaim", etc.
    size_mult: float = 1.0              # NEW: from ArmedTrade for probe sizing
```

### 2b: Update parse_plan() (~line 717)

Add setup_type extraction to the regex parsing. After the score extraction (~line 744-747):

```python
        # Extract setup_type if present
        setup_type = "micro_pullback"  # default
        st_match = re.search(r"setup_type=(\w+)", msg)
        if st_match:
            setup_type = st_match.group(1)

        # Extract size_mult if present (squeeze probe sizing)
        size_mult = 1.0
        sm_match = re.search(r"size_mult=([0-9]*\.?[0-9]+)", msg)
        if sm_match:
            size_mult = float(sm_match.group(1))

        return TradePlan(entry=entry, stop=stop, r=r, take_profit=tp,
                        score=score, setup_type=setup_type, size_mult=size_mult)
```

### 2c: Propagate setup_type to OpenTrade

In the `on_signal()` method (~line 1126), the `setup_type` needs to flow through to the Alpaca order and eventually to the `OpenTrade`. Currently `OpenTrade.setup_type` defaults to `"micro_pullback"` and is only set from `getattr(p, 'setup_type', 'micro_pullback')` when adopting from a pending order.

In on_signal(), after `plan = self.parse_plan(msg)`, propagate setup_type to the pending order:

Find where `self.pending[symbol]` is set (in `_submit_entry_order` or similar). Ensure `setup_type=plan.setup_type` is stored on the pending entry so it flows through to `OpenTrade` when the fill arrives.

**Also update squeeze_detector.py**: The message already includes `setup_type=squeeze` (line 200). Verify it also includes `size_mult=X` if the ArmedTrade has a `size_mult` attribute. Check simulate.py line 2514: `size_mult=_sq_armed_before.size_mult`. The squeeze message should emit `size_mult={self.armed.size_mult:.2f}` so parse_plan can extract it.

---

## Task 3: Port Squeeze Exit Logic to trade_manager.py

This is the hardest task. simulate.py's `_squeeze_tick_exits()` (lines 608-727) must be ported to trade_manager.py's `_manage_exits()`.

### 3a: Add squeeze exit env vars to PaperTradeManager.__init__()

```python
# Squeeze exit config (must match simulate.py exactly)
self.sq_target_r = float(os.getenv("WB_SQ_TARGET_R", "2.0"))
self.sq_trail_r = float(os.getenv("WB_SQ_TRAIL_R", "1.5"))
self.sq_runner_trail_r = float(os.getenv("WB_SQ_RUNNER_TRAIL_R", "2.5"))
self.sq_para_trail_r = float(os.getenv("WB_SQ_PARA_TRAIL_R", "1.0"))
self.sq_max_loss_dollars = float(os.getenv("WB_SQ_MAX_LOSS_DOLLARS", "500"))
self.sq_wide_trail_enabled = os.getenv("WB_SQ_WIDE_TRAIL_ENABLED", "0") == "1"
self.sq_trail_multiplier = float(os.getenv("WB_SQ_TRAIL_MULTIPLIER", "1.5"))
self.sq_runner_detect_enabled = os.getenv("WB_SQ_RUNNER_DETECT_ENABLED", "0") == "1"
self.sq_ross_coexist = os.getenv("WB_SQ_ROSS_COEXIST", "0") == "1"
```

### 3b: Add squeeze exit routing in _manage_exits()

In `_manage_exits()` (~line 2881), after the peak tracking but before the existing exit checks, add a setup_type router:

```python
        # Route by setup_type
        if t.setup_type == "squeeze":
            self._squeeze_manage_exits(symbol, t, bid)
            return
```

### 3c: Create _squeeze_manage_exits() method

Port `_squeeze_tick_exits()` from simulate.py (lines 608-727) to a new method in PaperTradeManager. The logic is identical, but adapted for live:

- Use `bid` instead of `price` (with the same phantom bid guards already in _manage_exits)
- Use `self._exit(symbol, qty=..., reason=..., price=bid)` instead of setting `t.core_exit_price` directly
- Keep the dollar loss cap, hard stop, max_loss tiered, pre-target trail, sq_target_hit, and runner trail — all in the same order as simulate.py
- Track `_sq_target_hit_time` per trade (on OpenTrade) for runner detection

The full method should mirror simulate.py's `_squeeze_tick_exits()` exactly:

```
1. Dollar loss cap (WB_SQ_MAX_LOSS_DOLLARS)
2. Hard stop
3. Max loss cap (tiered by float)
4. Pre-target: squeeze trailing stop + sq_target_hit at 2R
5. Post-target: runner trailing stop
```

**Key difference from simulate.py**: In live, the `_exit()` method submits a limit order to Alpaca. For sq_target_hit (partial exit), you need to exit `qty_core` and keep `qty_runner`. Use the existing `_exit(symbol, qty=t.qty_core, ...)` pattern.

### 3d: Add sq_target_hit_time to OpenTrade

```python
@dataclass
class OpenTrade:
    # ... existing fields ...
    sq_target_hit_time: Optional[datetime] = None  # When sq_target_hit fired (for runner detection)
```

---

## Task 4: Add Bail Timer to simulate.py

The live bot exits unprofitable trades after `WB_BAIL_TIMER_MINUTES` (default 5). simulate.py doesn't do this, meaning backtests can show trades that recover after 10+ minutes that the live bot would have already exited.

### 4a: Add bail timer config to SimTradeManager.__init__()

```python
self.bail_timer_enabled = os.getenv("WB_BAIL_TIMER_ENABLED", "1") == "1"
self.bail_timer_minutes = float(os.getenv("WB_BAIL_TIMER_MINUTES", "5"))
```

### 4b: Track entry time

SimTrade already has `entry_time: str` but it's a string like "09:31". Add a method to compute minutes elapsed:

```python
def _minutes_since_entry(self, t: SimTrade, time_str: str) -> float:
    """Minutes between entry_time and current time_str (HH:MM format)."""
    def to_min(s):
        parts = s.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    return to_min(time_str) - to_min(t.entry_time)
```

### 4c: Add bail timer check to on_tick()

In `on_tick()`, after the peak update but before the setup_type routing (before line 466), add:

```python
        # Bail timer: exit if unprofitable after N minutes
        if self.bail_timer_enabled and t.entry_time:
            minutes_in = self._minutes_since_entry(t, time_str)
            if minutes_in >= self.bail_timer_minutes:
                unrealized = price - t.entry
                if unrealized <= 0:
                    t.core_exit_price = price
                    t.core_exit_time = time_str
                    t.core_exit_reason = "bail_timer"
                    if t.qty_runner > 0:
                        t.runner_exit_price = price
                        t.runner_exit_time = time_str
                        t.runner_exit_reason = "bail_timer"
                    self._close(t)
                    return
```

This matches trade_manager.py's bail timer logic (~line 2956-2976).

---

## Task 5: Clean Up Classifier Config

.env has `WB_CLASSIFIER_ENABLED=1` but nothing reads it in either bot.py or simulate.py. Set it to 0 to reflect reality:

In `.env`:
```
WB_CLASSIFIER_ENABLED=0          # Not wired into bot or simulator (research only)
```

---

## Task 6: Regression Test

```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
```
**Expected**: +$18,583

```bash
WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```
**Expected**: +$6,444

**Also run a squeeze-specific regression** to verify the bail timer doesn't break squeeze results:
```bash
WB_SQUEEZE_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
```
Compare P&L before and after bail timer addition.

---

## Task 7: Commit + Push

```bash
git add bot.py trade_manager.py simulate.py squeeze_detector.py .env
git commit -m "$(cat <<'EOF'
Wire SqueezeDetector into live bot + align exits with backtest

Critical alignment fixes between bot.py and simulate.py:
- Import and wire SqueezeDetector into bot.py (1m bars + tick triggers)
- Add setup_type to TradePlan/OpenTrade (was hardcoded micro_pullback)
- Port squeeze exit logic to trade_manager.py (_squeeze_manage_exits)
  - sq_target_hit, squeeze trailing stop, dollar loss cap, runner trail
- Add bail timer to simulate.py (matches live bot's 5-min unprofitable exit)
- Set WB_CLASSIFIER_ENABLED=0 (not wired into anything)

Without this, live bot had zero strategies enabled and took zero trades.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## Validation Checklist

- [ ] bot.py imports SqueezeDetector and creates per-symbol instances
- [ ] bot.py feeds 1m bars to squeeze detector (on_bar_close_1m)
- [ ] bot.py feeds tick prices to squeeze detector (on_trade) with priority over MP
- [ ] trade_manager.py parse_plan() extracts setup_type and size_mult from message
- [ ] trade_manager.py TradePlan has setup_type field
- [ ] trade_manager.py OpenTrade gets setup_type from pending order
- [ ] trade_manager.py _manage_exits() routes squeeze trades to dedicated exit method
- [ ] trade_manager.py _squeeze_manage_exits() matches simulate.py _squeeze_tick_exits()
- [ ] simulate.py has bail timer (WB_BAIL_TIMER_ENABLED, WB_BAIL_TIMER_MINUTES)
- [ ] VERO regression: +$18,583 (MP mode)
- [ ] ROLR regression: +$6,444 (MP mode)
- [ ] .env WB_CLASSIFIER_ENABLED=0

---

## Files Modified

| File | What Changed |
|------|-------------|
| `bot.py` | SqueezeDetector import, sq_detectors dict, 1m bar feed, tick trigger, trade close callback |
| `trade_manager.py` | TradePlan.setup_type, parse_plan() extraction, OpenTrade propagation, _squeeze_manage_exits() |
| `simulate.py` | Bail timer (config, time calc, on_tick check) |
| `squeeze_detector.py` | Emit size_mult in message (if not already) |
| `.env` | WB_CLASSIFIER_ENABLED=0 |

---

## What NOT to Do

- Do NOT change any squeeze detector parameters (entry thresholds, score gates, etc.)
- Do NOT change any squeeze exit thresholds (target R, trail widths, etc.)
- Do NOT enable WB_VR_ENABLED in bot.py yet (VR is not validated for live)
- Do NOT remove the WB_MP_ENABLED gate (keep MP gatable even after squeeze is wired in)
- Do NOT change the live scanner or scanner_sim.py (separate directive handles that)

---

*This directive addresses all findings from the 2026-03-24 live bot audit. The goal is parity: what the backtest simulates is exactly what the live bot trades.*
