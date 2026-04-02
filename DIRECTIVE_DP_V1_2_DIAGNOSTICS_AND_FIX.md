# DIRECTIVE: DP V1.2 — Diagnostics + PLAYING State Fix

**Date:** 2026-03-30
**Priority:** High
**Prerequisite:** Commit 1a70165 (DP V1.1)

---

## Context

V1.1 produced +$502 across 5 stocks. Positive direction, but the wave analysis estimates $22K-$45K of opportunity exists. ASTC got 1 trade instead of 4-5. ROLR got 0 DP trades on a stock that made 101 up-waves. We're capturing ~2% of the available opportunity. Two root causes identified:

### Root Cause 1: PLAYING state is zero-tolerance on Red signals (line 614)

In WATCHING state, DP gets 5 chances (consecutive fail patience). But the moment it transitions to PLAYING and takes one trade, line 614 applies:

```python
elif self.state == "PLAYING":
    if red > 0:
        self._go_done(f"playing_red_signal ({red}R: {detail_str})")
        return None
```

**This means ANY single red signal on ANY dip after the first trade → DONE forever.**

On ASTC, after the +$298 trade closes, the next dip probably scores 1 red somewhere (vol ratio spike, or prior bounce didn't make a new HOD yet) and DP dies. The staircase waves 4-10 with 40-54% retraces and new HODs every time never get scored.

**Fix:** PLAYING state should use the same scorecard logic as initial entry: require `min_green_signals` greens and `max_red_signals` reds. The default config allows 0 reds, so set `WB_DP_MAX_RED_SIGNALS_PLAYING=1` (allow 1 red in PLAYING state). The DONE triggers should be the structural ones (2 consecutive lower highs, below VWAP, >100% retrace) — not "any dip had a single red."

### Root Cause 2: Unknown — ROLR $0 DP trades needs investigation

ROLR is a monster runner ($4.32→$33.68). The SQ detector fires cascading entries at higher levels. Each time SQ re-arms, the simulate.py integration resets DP to IDLE. Hypothesis: SQ cascades so frequently on ROLR that DP never gets a window to evaluate dips — it keeps getting reset to IDLE before completing a single wave cycle.

---

## Part 1: Diagnostic Data Collection (DO FIRST)

Run all 5 stocks with **maximum verbosity** and capture the FULL DP decision log. We need to see EVERY wave detected, every scorecard evaluation, every state transition.

### Step 1: Add comprehensive logging

Add a `--dp-verbose` flag (or use existing `--verbose`) that prints:
- Every completed wave (up and down) with all fields: type, prices, move%, duration, volume, HOD status, VWAP/EMA position
- Every scorecard evaluation: all 6 signals with their Green/Yellow/Red classification
- Every state transition with the exact reason
- Every SQ priority reset (PLAYING → IDLE)
- Wave tracker stats: how many waves detected, current swing high/low

### Step 2: Run diagnostics on all 5 test stocks

```bash
# Run each with DP enabled + verbose, capture output to files
WB_DYNAMIC_PLAYER_ENABLED=1 python simulate.py ASTC 2026-03-30 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | tee /tmp/dp_astc.log
WB_DYNAMIC_PLAYER_ENABLED=1 python simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | tee /tmp/dp_eeiq.log
WB_DYNAMIC_PLAYER_ENABLED=1 python simulate.py CRE 2026-03-06 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | tee /tmp/dp_cre.log
WB_DYNAMIC_PLAYER_ENABLED=1 WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | tee /tmp/dp_rolr.log
WB_DYNAMIC_PLAYER_ENABLED=1 WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | tee /tmp/dp_vero.log
```

### Step 3: Also run ALUR (Jan 2025 — the $47K Ross gap stock)

```bash
WB_DYNAMIC_PLAYER_ENABLED=1 python simulate.py ALUR 2025-01-24 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | tee /tmp/dp_alur.log
```

### Step 4: Wave comparison validation

For ASTC and ROLR, compare the waves detected by `WaveTracker` (real-time, 1m bars, 2% reversal threshold) against the waves in `wave_analysis/ASTC_2026-03-30.md` and `wave_analysis/ROLR_2026-01-14.md` (from `analyze_runner_waves.py`).

Key questions:
- How many waves does WaveTracker detect vs analyze_runner_waves.py?
- Are the wave boundaries (start/end prices, times) aligned?
- If WaveTracker detects fewer waves, is the 2% reversal threshold too high for small price moves? (ASTC moves $0.10-$0.30 per wave on a $5 stock = 2-6%, so 2% reversal might be right. But ROLR moves $0.50-$3.00 per wave on a $5-$33 stock — the percentage math changes dramatically as price rises.)

---

## Part 2: PLAYING State Fix

### Change 1: Allow configurable reds in PLAYING state

Replace line 614:
```python
# BEFORE (zero-tolerance)
if red > 0:
    self._go_done(f"playing_red_signal ({red}R: {detail_str})")
    return None
```

With:
```python
# AFTER (configurable tolerance)
max_red_playing = int(os.getenv("WB_DP_MAX_RED_SIGNALS_PLAYING", "1"))
if red > max_red_playing:
    self._go_done(f"playing_red_signal ({red}R > {max_red_playing}: {detail_str})")
    return None
```

Also: when a dip in PLAYING state has reds but within tolerance, still require min_green_signals:
```python
if red <= max_red_playing and green >= self.min_green_signals:
    return self._generate_buy(dip_wave, bar_close, bar_time, green, vwap, ema)
else:
    # Skip this dip but don't go DONE — wait for the next one
    self.log.append(f"[{bar_time}] DP_PLAYING_SKIP: {green}G/{yellow}Y/{red}R, not entering but still alive")
    return None
```

**Keep the structural DONE triggers as-is:**
- 2 consecutive lower highs → DONE ✅
- Bar close below VWAP → DONE ✅
- Retrace >100% → DONE ✅
- Max trades/max loss → DONE ✅

These are the real "run is over" signals. Red on a single scorecard metric (e.g., vol ratio spiked to 1.6x on one dip) is NOT a terminal signal.

### Change 2: PLAYING skip counter with patience

Add a skip counter in PLAYING state (like WATCHING has):

```python
# In PLAYING state, after deciding not to enter:
self._playing_skip_count += 1
if self._playing_skip_count >= int(os.getenv("WB_DP_PLAYING_PATIENCE", "5")):
    self._go_done("playing_5_consecutive_skips")
    return None
# Reset on successful entry:
self._playing_skip_count = 0
```

### Change 3: New env vars

```bash
WB_DP_MAX_RED_SIGNALS_PLAYING=1    # Reds allowed per dip in PLAYING (default 1)
WB_DP_PLAYING_PATIENCE=5           # Consecutive skips before DONE in PLAYING
```

---

## Part 3: Re-test After Fix

Run all 6 stocks (original 5 + ALUR) with the PLAYING fix:

```bash
WB_DYNAMIC_PLAYER_ENABLED=1 python simulate.py ASTC 2026-03-30 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose
WB_DYNAMIC_PLAYER_ENABLED=1 python simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose
WB_DYNAMIC_PLAYER_ENABLED=1 python simulate.py CRE 2026-03-06 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose
WB_DYNAMIC_PLAYER_ENABLED=1 WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose
WB_DYNAMIC_PLAYER_ENABLED=1 WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose
WB_DYNAMIC_PLAYER_ENABLED=1 python simulate.py ALUR 2025-01-24 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose
```

### Expected Results

| Stock | SQ P&L (must match) | DP Target | Notes |
|-------|---------------------|-----------|-------|
| ASTC | +$1,209 | 3-5 DP trades, net +$500-$1,500 | Staircase waves 4-10 |
| EEIQ | +$1,671 | 1-2 DP trades, net +$0-$200 | Fades fast, limited upside |
| CRE | +$4,560 | 0 DP trades | Dead stock, correctly avoided |
| ROLR | +$12,601 | DP trades TBD | Monster runner — diagnostic first |
| VERO | +$562 | DP net ≥ $0 | Must not regress |
| ALUR | TBD | DP trades TBD | The $47K gap stock — our litmus test |

### Regression Gate
- SQ P&L for VERO and ROLR MUST match baseline (±$50 tolerance)
- If VERO regresses again, revert PLAYING fix and report diagnostic data only

---

## Part 4: Report

Write `cowork_reports/2026-03-30_dp_v1_2_results.md` with:

1. **Per-stock summary table:** SQ P&L, DP P&L, total, DP trade count
2. **ASTC wave-by-wave log:** Every wave WaveTracker detected, every scorecard evaluation, every entry/exit. Compare against wave_analysis expectations.
3. **ROLR investigation:** How many SQ re-arms? How many times DP reaches WATCHING? How many waves detected per WATCHING window? What kills DP each time?
4. **ALUR investigation:** Same detail as ROLR. How much of the $8→$20 run does DP capture?
5. **Wave comparison:** WaveTracker vs analyze_runner_waves.py wave counts for ASTC and ROLR. Any alignment issues?
6. **Scorecard signal histogram:** Across all stocks, which signals score Red most often? (This tells us which thresholds need the most tuning.)

---

## Deliverables

1. `dynamic_player.py` changes (PLAYING fix, env vars, enhanced logging)
2. `cowork_reports/2026-03-30_dp_v1_2_results.md` — comprehensive diagnostic report
3. Raw log files saved to `dp_logs/` directory (verbose output for Cowork analysis)
