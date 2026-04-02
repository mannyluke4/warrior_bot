# Directive: Candle Exit V2 — Volume-Confirmed 1m Signal Exits

**Date:** 2026-04-02
**Author:** Cowork (Opus)
**Target file:** `squeeze_detector_v2.py` → `check_exit()` method
**Gate:** `WB_SQV2_CANDLE_EXIT_V2=1` (default 0 = OFF, falls back to current mechanical exits)

---

## Problem Statement

The current candle exit system in V2's `check_exit()` fires topping wicky and bearish engulfing patterns on **10-second bars**. On parabolic stocks, 10s bars produce constant false reversal signals during continuation moves. ROLR trade log: *"10s bars had constant green-to-red patterns that triggered BE during continuation"* — Trade 3 entered at $5.91, BE exited at $7.71. Stock went to $22.28.

Result: candle exits **cost $1,671** vs rolling-HOD-only across 63 days.

Meanwhile, the mechanical 2R exits leave massive money on the table: 81% of trades are runners (2R+ continuation after exit), with an average +23R of additional movement available. `sq_target_hit` trades alone have +32.1R average continuation — $14,201/trade left behind.

Dynamic candle exits should capture this continuation by holding winners longer and exiting on real reversal signals, not 10s noise.

---

## Root Causes (From Data)

### 1. Wrong Timeframe
10-second bars generate noise patterns during parabolic moves. Ross Cameron reads **1-minute candles**. A 10s red bar is meaningless; a 1m bearish engulfing with volume expansion is a real distribution signal.

### 2. Inverted Profit Gate
Current code: `if unrealized >= 1.5R: tw_ok = False` — suppresses TW exits on high-profit trades. This means:
- Trade at +0.5R still building momentum → TW fires → kills runner early
- Trade at +5R rolling over → TW suppressed → rides it down

Should be the opposite: let low-profit trades breathe (they might become runners), protect high-profit trades aggressively.

### 3. No Volume Context
A bearish engulfing on 50K volume during a stock trading 1M/bar is noise. A bearish engulfing on 2M volume after a climax bar is distribution. Current implementation ignores volume entirely on exit signals.

---

## Implementation: Three-Tier Exit System

Replace the current `_check_candle_exit_10s()` with a new `_check_candle_exit_v2()` that uses **1-minute bars**, **profit tiers**, and **volume confirmation**.

### Tier 1: Capital Protection (unrealized < 1.0R)

Trade is not yet profitable enough to be a confirmed winner. Protect capital, but give room for the initial push.

**Signals that trigger full exit:**
- 1m bearish engulfing (current bar close < prior bar open, current bar open > prior bar close)
- 1m shooting star (upper wick ≥ 2x body, body in lower 30% of range)
- 1m gravestone doji (body ≤ 12% of range, upper wick ≥ 3x body)

**No volume confirmation required** at this tier — these are loss-prevention exits.

**Time gate:** Minimum 2 completed 1m bars in the trade before any candle exit can fire. This prevents the first consolidation bar from immediately triggering an exit.

**Env vars:**
- `WB_SQV2_T1_MIN_BARS=2` — minimum 1m bars before Tier 1 exits activate
- `WB_SQV2_T1_THRESHOLD_R=1.0` — upper bound of Tier 1

### Tier 2: Momentum Protection (1.0R ≤ unrealized < 3.0R)

Trade is profitable. The stock has proven it can move. Give it room to run, but exit on confirmed reversal signals.

**Signals that trigger full exit (volume-confirmed only):**
- 1m gravestone doji + exit bar volume ≥ 1.5x average of last 5 bars
- 1m shooting star + exit bar volume ≥ 1.5x average of last 5 bars

**Signals that trigger trail tighten (warning, not exit):**
- 1m bearish engulfing WITHOUT volume confirmation → tighten trailing stop to low of the engulfing bar (instead of full exit)
- 1m doji (body ≤ 12% of range) WITHOUT volume → tighten trailing stop to low of doji bar

**Trail tighten mechanism:** When a warning fires, set `self._tight_trail_price = bar_1m.low`. On subsequent ticks, if price drops below `_tight_trail_price`, exit with reason `"candle_warning_trail"`. If price makes a new high, clear the tight trail.

**Env vars:**
- `WB_SQV2_T2_THRESHOLD_R=3.0` — upper bound of Tier 2
- `WB_SQV2_T2_VOL_MULT=1.5` — volume multiple for confirmed signals

### Tier 3: Runner Protection (unrealized ≥ 3.0R)

This is a confirmed runner. The stock has moved 3R+ in our favor. Protect the gain aggressively with high-quality signals only.

**Signals that trigger full exit:**
- 1m candle-under-candle: current bar low < prior bar low AND current bar close < prior bar close (two conditions, not just low break). This is Ross's primary sell signal.
- 1m climax reversal: bar makes new high of day, then closes in bottom 25% of its range, AND volume is highest of the session (climax bar followed by distribution)
- MACD bearish cross while price is below the high of the prior bar (divergence confirmation)

**Signals that trigger trail tighten:**
- 1m shooting star / gravestone (even without volume) → set tight trail at low of signal bar
- Any 1m bar that closes below VWAP → set tight trail at that bar's low

**Env vars:**
- `WB_SQV2_T3_THRESHOLD_R=3.0` — lower bound of Tier 3

---

## Volume Context Implementation

Add a rolling volume tracker to `check_exit()`. On each 1m bar close:

```python
self._exit_vol_history.append(bar_1m.volume)
if len(self._exit_vol_history) > 10:
    self._exit_vol_history.pop(0)

def _avg_recent_volume(self, n=5):
    """Average volume of last n 1m bars."""
    if len(self._exit_vol_history) < n:
        return 0
    return sum(self._exit_vol_history[-n:]) / n

def _is_volume_confirmed(self, bar_volume, mult=1.5):
    """True if bar volume exceeds mult * recent average."""
    avg = self._avg_recent_volume()
    if avg <= 0:
        return False
    return bar_volume >= mult * avg
```

Also track session max volume for climax detection:
```python
self._session_max_vol = max(self._session_max_vol, bar_1m.volume)

def _is_climax_volume(self, bar_volume):
    """True if this bar is the highest volume bar of the session."""
    return bar_volume >= self._session_max_vol
```

---

## State Management

### New State Variables (in `notify_trade_opened`)

```python
self._exit_vol_history = []          # Rolling 1m volume for avg calculation
self._session_max_vol = 0            # Highest 1m volume bar this session
self._tight_trail_price = None       # Set by Tier 2/3 warnings
self._bars_in_trade = 0             # Count of completed 1m bars since entry
self._entry_price_for_exit = entry   # Cached for tier calculations
self._r_value_for_exit = r           # Cached for tier calculations
```

### Bar Counter

Increment `self._bars_in_trade` on each 1m bar close while in a trade. Reset to 0 in `notify_trade_opened`.

### Tight Trail Logic

On every tick (`on_trade_price` or when `check_exit` is called):
```python
if self._tight_trail_price is not None:
    if price < self._tight_trail_price:
        self._tight_trail_price = None
        return "candle_warning_trail"
    if price > self._trade_high:  # New high clears the warning
        self._tight_trail_price = None
```

---

## check_exit() Flow (Revised)

When `WB_SQV2_CANDLE_EXIT_V2=1`:

```
1. Dollar loss cap check (unchanged)
2. Hard stop check (unchanged)
3. Tiered max loss check (unchanged)
4. IF tight_trail_price is set AND price < tight_trail_price → "candle_warning_trail"
5. IF new high → clear tight_trail_price, update trade_high
6. Calculate unrealized R: (price - entry) / r
7. Pre-target trailing stop (unchanged — mechanical backstop stays)
8. Target hit check (CHANGED — see below)
9. Post-target runner trail (CHANGED — see below)
10. Call _check_candle_exit_v2(bar_1m, unrealized_r)
```

### Critical Change: Target Hit Behavior

When `sq_target_hit` fires (price reaches 2R), **do NOT exit the full position.** Instead:
- Log "sq_target_hit" for tracking purposes
- Set `self._trade_tp_hit = True`
- Switch to Tier 3 exit logic
- The actual exit comes from candle signals, not the target itself

This is the fundamental difference from V1. In V1, `sq_target_hit` = exit 75% immediately. In Candle Exit V2, `sq_target_hit` = acknowledgment that we're in runner territory, let candle signals manage the exit.

**Env var:** `WB_SQV2_TARGET_IS_EXIT=0` — when 0, target hit does NOT trigger an exit, only tier promotion. When 1, reverts to V1 behavior (immediate exit on target). Default 0.

**IMPORTANT:** The mechanical trailing stop remains as a backstop at all tiers. If candle exits don't fire and the trail catches the trade, that's fine — the trail is the safety net. Candle exits are the improvement layer on top.

---

## _check_candle_exit_v2() Implementation

```python
def _check_candle_exit_v2(self, bar_1m, unrealized_r: float) -> Optional[str]:
    """
    Volume-confirmed 1m candle exit signals, tiered by profit level.
    Returns exit reason string or None.
    """
    if bar_1m is None or self._bars_in_trade < self._t1_min_bars:
        return None

    o, h, l, c = bar_1m.open, bar_1m.high, bar_1m.low, bar_1m.close
    rng = h - l
    if rng <= 0:
        return None

    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    is_red = c < o
    is_green = c > o

    # Need prior bar for engulfing/CUC
    prev = self._prior_1m_bar  # Must be stored on each bar close
    if prev is None:
        return None

    prev_o, prev_h, prev_l, prev_c = prev.open, prev.high, prev.low, prev.close

    vol_confirmed = self._is_volume_confirmed(bar_1m.volume, self._t2_vol_mult)

    # ── Detect patterns ──
    is_shooting_star = (upper_wick >= 2 * body and body > 0
                        and (min(o, c) - l) <= 0.3 * rng)
    is_gravestone = (body <= 0.12 * rng and upper_wick >= 3 * body
                     and rng > 0.001)
    is_bearish_engulf = (is_red and is_green_bar(prev)
                         and c < prev_o and o > prev_c)
    is_doji = body <= 0.12 * rng and rng > 0.001
    is_cuc = (l < prev_l and c < prev_c)
    is_climax_reversal = (h >= self._trade_high
                          and (c - l) <= 0.25 * rng
                          and self._is_climax_volume(bar_1m.volume))

    # ── TIER 1: Capital Protection (< 1.0R) ──
    if unrealized_r < self._t1_threshold:
        if is_bearish_engulf:
            return "t1_bearish_engulfing_exit"
        if is_shooting_star:
            return "t1_shooting_star_exit"
        if is_gravestone:
            return "t1_gravestone_exit"
        return None

    # ── TIER 2: Momentum Protection (1.0R - 3.0R) ──
    if unrealized_r < self._t3_threshold:
        # Full exit on volume-confirmed reversal
        if is_gravestone and vol_confirmed:
            return "t2_gravestone_vol_exit"
        if is_shooting_star and vol_confirmed:
            return "t2_shooting_star_vol_exit"
        # Warning (trail tighten) on unconfirmed patterns
        if is_bearish_engulf:
            self._tight_trail_price = l
            # Don't return — this is a warning, not an exit
        if is_doji:
            self._tight_trail_price = l
        return None

    # ── TIER 3: Runner Protection (≥ 3.0R) ──
    if is_cuc:
        return "t3_candle_under_candle_exit"
    if is_climax_reversal:
        return "t3_climax_reversal_exit"
    # MACD check (if available on the bar)
    if hasattr(bar_1m, 'macd') and hasattr(bar_1m, 'macd_signal'):
        if (bar_1m.macd < bar_1m.macd_signal
                and h < prev_h):
            return "t3_macd_divergence_exit"
    # Warnings
    if is_shooting_star or is_gravestone:
        self._tight_trail_price = l
    if hasattr(bar_1m, 'vwap') and c < bar_1m.vwap:
        self._tight_trail_price = l
    return None
```

---

## Env Var Summary

All new env vars, all default OFF or conservative:

| Var | Default | Purpose |
|-----|---------|---------|
| `WB_SQV2_CANDLE_EXIT_V2` | `0` | Master gate — 0 = old mechanical exits, 1 = new tiered candle exits |
| `WB_SQV2_TARGET_IS_EXIT` | `0` | 0 = target hit promotes to Tier 3 (no exit), 1 = V1 behavior (exit on target) |
| `WB_SQV2_T1_MIN_BARS` | `2` | Minimum 1m bars before any candle exit fires |
| `WB_SQV2_T1_THRESHOLD_R` | `1.0` | Upper bound of Tier 1 |
| `WB_SQV2_T2_THRESHOLD_R` | `3.0` | Upper bound of Tier 2 / lower bound of Tier 3 |
| `WB_SQV2_T2_VOL_MULT` | `1.5` | Volume multiple required for confirmed Tier 2 signals |

---

## Wiring Into simulate.py

The existing wiring calls `sq_det.check_exit()` on 10s bar close (lines 2216-2233). Changes needed:

1. **Pass 1m bar data to check_exit.** The `bar_1m` parameter already exists in the signature but may not be populated. On each 1m bar close, pass the completed bar. On 10s bar closes, pass `bar_1m=None` (candle exit V2 ignores 10s bars entirely).

2. **Increment bar counter.** Call a new method `sq_det.on_1m_bar_close_exit(bar_1m)` that updates `_bars_in_trade`, `_exit_vol_history`, `_session_max_vol`, and `_prior_1m_bar`.

3. **Handle target-not-exit.** When `WB_SQV2_TARGET_IS_EXIT=0` and `check_exit` returns `"sq_target_hit"`, log it but do NOT call `sim_mgr.on_exit_signal()`. Instead just set the internal flag.

4. **Handle trail tighten.** The tight trail check happens inside `check_exit` on every call (not just 1m bar closes). This means the existing 10s/tick frequency of `check_exit` calls still catches the trail break promptly — we just don't use 10s bars for pattern detection.

---

## What NOT To Do

- **Do NOT remove the mechanical trailing stop.** It remains as a backstop. Candle exits sit on top of it. If the candle system is too slow to catch a reversal, the mechanical trail catches it.
- **Do NOT change any V1 behavior.** This is gated behind `WB_SQV2_CANDLE_EXIT_V2=1`. When gate is OFF, everything works exactly as before.
- **Do NOT use 10-second bars for candle patterns.** The entire point is moving to 1m timeframe for signal quality.
- **Do NOT touch `squeeze_detector.py`.** V1 is frozen. All changes in V2.
- **Do NOT hardcode tier thresholds.** Everything comes from env vars so we can tune after seeing results.

---

## Success Criteria

Run the 63-day backtest with:
```bash
WB_SQV2_CANDLE_EXIT_V2=1
WB_SQV2_TARGET_IS_EXIT=0
WB_SQUEEZE_VERSION=2
WB_SQV2_ROLLING_HOD=1
```

Compare against Test 4 baseline (rolling HOD only, $169,227). We expect the candle exit system to capture more of the runner continuation that the mechanical 2R exit leaves behind.

Also run VERO and ROLR standalone to see per-stock behavior on known runners.

---

## Build Order

1. Add new env vars and state variables to `squeeze_detector_v2.py`
2. Implement `_check_candle_exit_v2()` method
3. Implement volume tracking (`_exit_vol_history`, `_avg_recent_volume`, `_is_volume_confirmed`, `_is_climax_volume`)
4. Implement tight trail logic in `check_exit()` main flow
5. Modify target hit behavior (exit vs tier promotion based on gate)
6. Add `on_1m_bar_close_exit()` method for bar counting and state updates
7. Wire 1m bar data through `simulate.py`
8. Test with gate ON and gate OFF (gate OFF must be identical to current behavior)

---

*Directive written: 2026-04-02 | Cowork (Opus)*
*Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>*
