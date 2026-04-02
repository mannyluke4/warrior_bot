# DIRECTIVE: Dynamic Player V1

**Date:** 2026-03-30
**Priority:** High
**Prerequisite:** Read `cowork_reports/2026-03-30_dynamic_player_wave_analysis.md` for full analysis

---

## Overview

Build a **Dynamic Player (DP)** — a post-squeeze trading system that dynamically enters dips and exits bounces based on real-time wave analysis. This replaces both CT (shelved) and static runner mode (rejected).

**Core principle:** The DP reads the chart as it moves. It enters when a dip looks healthy, exits on the bounce, and stops when the chart says the run is over. Each stock gets its own "best fit" — not a static trail.

**Critical constraint:** DP must NOT interfere with Squeeze detection, entry, or exit logic. DP only activates AFTER the last SQ position is fully closed. If SQ re-arms while DP is active, SQ takes priority and DP goes to DONE.

---

## Phase 1: Build `dynamic_player.py`

### File: `dynamic_player.py` (new file)

### State Machine

```
IDLE → WATCHING → PLAYING → DONE
```

**IDLE:**
- Default state. DP is not active.
- Transition to WATCHING: When a SQ trade exits (any exit reason: sq_target_hit, trailing, stop, etc.)
- On transition: Record the SQ exit price and time. Start wave tracking.

**WATCHING:**
- Purpose: Evaluate if this stock is worth playing dynamically.
- Track the first complete up-wave and down-wave after SQ exit.
- Score the first dip using the Buyable Dip Scorecard (see below).
- Transition to PLAYING: If dip scores ≥ `min_green_signals` green and ≤ `max_red_signals` red.
- Transition to DONE: If dip has any Red signal (at default config), or dip takes >5 min, or price closes 1m bar below VWAP.

**PLAYING:**
- Active trading state. System generates BUY/SELL signals.
- On each completed down-wave: Score the dip. If it passes → generate BUY signal at the wave reversal point.
- On each up-wave peak (or reversal detection): Generate SELL signal.
- Track: consecutive lower highs, VWAP position, wave count.
- Transition to DONE: Any of:
  - A dip scores Red on retrace (>80%) or VWAP (below)
  - Two consecutive bounces fail to make new HOD
  - Price closes 1m bar below VWAP
  - Max trades per stock reached
  - Max loss per stock reached
  - SQ re-arms (PRIMED or ARMED state detected)

**DONE:**
- Terminal. No more DP trades for this stock.
- Log the reason for DONE transition.

### Wave Tracking

Port the swing detection logic from `analyze_runner_waves.py` into real-time operation. The wave tracker needs to work on 1-minute bars (not tick-level — keep it simple for V1).

```python
class WaveTracker:
    """Tracks up-waves and down-waves on 1m bars."""

    def __init__(self):
        self.waves = []          # List of completed waves
        self.current_wave = None  # Current in-progress wave
        self.swing_high = None
        self.swing_low = None
        self.hod = None          # High of day

    def on_bar(self, bar):
        """Process each 1m bar. Detect wave reversals."""
        # A wave reversal occurs when:
        # - Current wave is UP and bar.close < swing_high * (1 - reversal_threshold)
        # - Current wave is DOWN and bar.close > swing_low * (1 + reversal_threshold)
        # Use reversal_threshold = 0.02 (2%) to filter noise
        pass

    def get_last_completed_wave(self):
        """Return the most recently completed wave."""
        pass

    def get_prior_up_wave(self):
        """Return the up-wave before the current/last down-wave."""
        pass
```

Each wave should track:
- `type`: "UP" or "DOWN"
- `start_price`, `end_price`, `start_time`, `end_time`
- `move_pct`: Price change percentage
- `duration`: In minutes
- `volume`: Total volume during the wave
- `made_new_hod`: Boolean — did this up-wave make a new high of day?
- `vwap_position`: "above" or "below" (use bar's VWAP from TradeBarBuilder)
- `ema9_position`: "above" or "below"

### Buyable Dip Scorecard

Score each completed down-wave on 6 signals:

```python
def score_dip(self, dip_wave, prior_up_wave, current_vwap, current_ema9):
    """Score a dip wave. Returns (green_count, yellow_count, red_count)."""
    green = yellow = red = 0

    # 1. Retrace %
    retrace_pct = abs(dip_wave.move_pct) / abs(prior_up_wave.move_pct) * 100
    if retrace_pct < self.max_retrace_green:  # default 50
        green += 1
    elif retrace_pct < self.max_retrace_red:  # default 80
        yellow += 1
    else:
        red += 1

    # 2. VWAP position
    if dip_wave.end_price > current_vwap:
        green += 1
    elif dip_wave.low_touched_vwap_and_recovered:  # touched but closed above
        yellow += 1
    else:
        red += 1

    # 3. EMA9 position
    if dip_wave.end_price > current_ema9:
        green += 1
    elif dip_wave.broke_ema_and_recovered_within_1m:
        yellow += 1
    else:
        red += 1

    # 4. Dip duration
    if dip_wave.duration <= self.max_dip_dur_green:  # default 2 min
        green += 1
    elif dip_wave.duration <= self.max_dip_dur_red:  # default 4 min
        yellow += 1
    else:
        red += 1

    # 5. Volume ratio (dip volume/min vs prior up volume/min)
    vol_ratio = (dip_wave.volume / max(dip_wave.duration, 1)) / \
                (prior_up_wave.volume / max(prior_up_wave.duration, 1))
    if vol_ratio < self.max_vol_ratio_green:  # default 1.0
        green += 1
    elif vol_ratio < self.max_vol_ratio_red:  # default 1.5
        yellow += 1
    else:
        red += 1

    # 6. Prior up-wave made new HOD?
    if prior_up_wave.made_new_hod:
        green += 1
    elif prior_up_wave.end_price > self.hod * 0.97:  # within 3%
        yellow += 1
    else:
        red += 1

    return green, yellow, red
```

### Entry Logic

When a dip passes the scorecard (≥ `min_green_signals` green, ≤ `max_red_signals` red):

- **Entry trigger:** First 1m bar that closes above the dip wave's low (the reversal bar).
- **Entry price:** Close of the reversal bar.
- **Position size:** Full size ($50K notional) if 5-6 green. Half size if 3-4 green.
- **Stop loss:** The lower of:
  - Entry price * (1 - hard_stop_pct/100)  (default 2%)
  - Dip wave low price

### Exit Logic

While in a DP position:

1. **Wave reversal exit (primary):** When the up-wave shows a reversal (1m bar closes significantly below the wave's swing high), exit at that bar's close. This is the "take profit on the bounce" mechanism.

2. **Hard stop:** If price drops to stop loss level, exit immediately.

3. **Time stop:** If position is flat or negative after `time_stop_min` minutes (default 3), exit at market.

4. **VWAP stop:** If a 1m bar closes below VWAP while in position, exit immediately (the stock is breaking down).

### Halt Detection

If a 1m bar has a price gap >10% from the prior bar (indicating a circuit breaker halt):
- If in WATCHING: Transition to a HALT_PAUSE sub-state.
- If in PLAYING with no position: Enter HALT_PAUSE.
- If in PLAYING with a position: Hold. Set a tighter trail (1% from current price).
- HALT_PAUSE: Wait for `halt_recovery_waves` (default 3) consecutive waves where all prices stay above VWAP. Then re-evaluate using the scorecard.

---

## Phase 2: Integrate into simulate.py

### Changes to simulate.py

1. **Import and instantiate:**
```python
from dynamic_player import DynamicPlayer

# In the per-stock setup:
dp_enabled = os.getenv("WB_DYNAMIC_PLAYER_ENABLED", "0") == "1"
if dp_enabled:
    dynamic_player = DynamicPlayer(config)  # Pass env-based config
```

2. **Hook into SQ exit:**
When a SQ position closes (in the exit handling section), notify the DP:
```python
if dp_enabled and exit_reason:
    dynamic_player.on_sq_exit(exit_price, exit_time, current_vwap, current_ema9)
```

3. **Feed bars to DP:**
In the 1m bar processing loop, after SQ detector processing:
```python
if dp_enabled and dynamic_player.state != "IDLE":
    dp_signal = dynamic_player.on_bar(bar, current_vwap, current_ema9, current_hod)
    if dp_signal == "BUY" and not in_position:
        # Execute DP entry through TradeManager
        # entry_reason = "dp_dip_entry"
        pass
    elif dp_signal == "SELL" and in_position and position_reason.startswith("dp_"):
        # Execute DP exit through TradeManager
        pass
```

4. **SQ priority gate:**
If SQ detector state is PRIMED or ARMED while DP is active:
```python
if sq_detector.state in ("PRIMED", "ARMED") and dynamic_player.state == "PLAYING":
    dynamic_player.force_done("sq_rearm")
    # Close any open DP position
```

5. **Tracking:**
DP trades should be logged with entry_reason `dp_dip_entry` and exit_reason `dp_wave_exit`, `dp_hard_stop`, `dp_time_stop`, `dp_vwap_stop`, or `dp_sq_priority`.

### Entry reason tags
- `dp_dip_entry` — entered on a scorecard-passing dip
- Exit reasons: `dp_wave_exit`, `dp_hard_stop`, `dp_time_stop`, `dp_vwap_stop`, `dp_sq_priority`, `dp_max_trades`, `dp_max_loss`

---

## Phase 3: Configuration (.env additions)

```bash
# === Dynamic Player ===
WB_DYNAMIC_PLAYER_ENABLED=0      # OFF by default
WB_DP_MAX_RETRACE_GREEN=50       # % retrace threshold for green score
WB_DP_MAX_RETRACE_RED=80         # % retrace threshold for red score
WB_DP_MAX_DIP_DURATION_GREEN=2   # minutes for green score
WB_DP_MAX_DIP_DURATION_RED=4     # minutes for red score
WB_DP_MAX_VOL_RATIO_GREEN=1.0    # vol ratio for green score
WB_DP_MAX_VOL_RATIO_RED=1.5      # vol ratio for red score
WB_DP_MIN_GREEN_SIGNALS=3        # minimum greens to enter
WB_DP_MAX_RED_SIGNALS=0          # maximum reds allowed to enter
WB_DP_HARD_STOP_PCT=2.0          # % below entry for hard stop
WB_DP_TIME_STOP_MIN=3            # minutes unprofitable → exit
WB_DP_MAX_TRADES_PER_STOCK=10    # max DP trades on one symbol
WB_DP_MAX_LOSS_PER_STOCK=2000    # max cumulative DP loss before DONE
WB_DP_HALT_RECOVERY_WAVES=3      # waves above VWAP needed after halt
WB_DP_WAVE_REVERSAL_THRESHOLD=0.02  # 2% swing reversal detection
```

---

## Phase 4: Testing

### Step 1 — Unit validation on 3 stocks:
```bash
WB_DYNAMIC_PLAYER_ENABLED=1 python simulate.py ASTC 2026-03-30 07:00 12:00 --ticks --tick-cache tick_cache/
WB_DYNAMIC_PLAYER_ENABLED=1 python simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/
WB_DYNAMIC_PLAYER_ENABLED=1 python simulate.py CRE 2026-03-06 07:00 12:00 --ticks --tick-cache tick_cache/
```

Expected:
- ASTC: SQ P&L unchanged. DP should produce 3-5 additional profitable trades.
- EEIQ: SQ P&L unchanged. DP should produce 0-1 additional trades (fades quickly).
- CRE: SQ P&L unchanged. DP should produce 0 trades (correctly identified as dead).

### Step 2 — Regression:
```bash
WB_DYNAMIC_PLAYER_ENABLED=1 WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
WB_DYNAMIC_PLAYER_ENABLED=1 WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```

Expected:
- SQ P&L unchanged from baseline (VERO +$562, ROLR +$12,601)
- DP adds positive P&L on top
- Total should be SQ baseline + DP uplift

### Step 3 — Full batch:
Run all 10 wave analysis stocks. Report SQ P&L (must match baseline) + DP P&L (incremental).

### Step 4 — 49-day regression:
Full `run_ytd_v2_backtest.py` with DP enabled. SQ total must still be +$19,832 (or within $100 tolerance). DP P&L is additive.

---

## Deliverables

1. `dynamic_player.py` — complete module
2. `simulate.py` changes — DP integration (gated)
3. `.env` additions — all DP config vars
4. Test results report — per-stock breakdown of SQ vs DP P&L
5. Updated `CLAUDE.md` — document DP as available strategy

---

## Notes

- V1 uses 1-minute bars for wave detection (not tick-level). This is simpler and matches the existing bar infrastructure. If V1 shows promise, V2 can move to tick-level for faster entries.
- The wave reversal threshold (2%) may need tuning. Too tight = false reversals. Too loose = late exits. Start at 2% and adjust based on test results.
- The scorecard thresholds are derived from the wave analysis data but are configurable. If a stock type consistently scores differently, the thresholds can be tuned per-classifier-type in a future version.
- DP entries count toward the same daily loss limit as SQ trades. The `max_loss_per_stock` is a DP-specific guardrail on top of that.
