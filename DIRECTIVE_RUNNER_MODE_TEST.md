# DIRECTIVE: Runner Mode Test + Tick Wave Analysis

**Date:** 2026-03-30
**Author:** Cowork (Opus)
**For:** CC (Sonnet)
**Priority:** P1 — This is our next strategy iteration. CT is shelved.
**Branch:** `v2-ibkr-migration`

---

## Context

CT (Continuation Trading) is shelved after 4 iterations producing max +$413. The deep dive across 18 Ross comparison files revealed the real problem: **the bot exits too early, not that it enters too late.** ALUR Jan 24: bot entered at $8.04 (same as Ross), exited at $8.40 (sq_target_hit), stock went to $20. Ross made $47K, bot made $586. Same entry, 80x P&L gap — purely from exit management.

The SQ cascade already re-enters at higher levels. But the exits (2R target, tight parabolic trail) leave 80-95% of big runners on the table.

This directive has TWO goals:
1. **Test runner mode** using the existing partial exit infrastructure
2. **Extract tick-level wave data** on our best runners so we can study how big moves actually behave — dips, bounces, volume patterns — and design smarter "play the stock" logic in the next iteration

---

## Part 1: Runner Mode Test

### What Exists Already

The sim already has partial exit + runner infrastructure (gated OFF):
```
WB_SQ_PARTIAL_EXIT_ENABLED=0   # Partial exit at sq_target_hit
WB_SQ_PARTIAL_PCT=50            # % to sell at target (keep rest as runner)
WB_SQ_RUNNER_DETECT_ENABLED=0   # Wider trail if target hit in <5 min
WB_SQ_RUNNER_TRAIL_R=2.5        # Runner trail in R-multiples
WB_SQ_PARA_TRAIL_R=1.0          # Standard parabolic trail
```

This was tested before and V1 (no partials) won. But the runner trail was at 2.5R — which on a $0.14 R-value is only $0.35. That's extremely tight for a runner on a $8→$20 stock. The trail needs to be much wider for big runners.

### Test Matrix

Run these 4 configs on the 6 target stocks and the full regression suite:

**Config A: Baseline (current V1, no runner)**
```bash
# No env overrides needed — this is the default
python simulate.py [STOCK] [DATE] 07:00 12:00 --ticks --tick-cache tick_cache/
```

**Config B: Runner with 5R trail**
```bash
WB_SQ_PARTIAL_EXIT_ENABLED=1 WB_SQ_PARTIAL_PCT=50 WB_SQ_RUNNER_TRAIL_R=5.0 \
python simulate.py [STOCK] [DATE] 07:00 12:00 --ticks --tick-cache tick_cache/
```

**Config C: Runner with 5m-low trail (NEW — see implementation below)**
```bash
WB_SQ_PARTIAL_EXIT_ENABLED=1 WB_SQ_PARTIAL_PCT=50 WB_SQ_RUNNER_TRAIL_MODE=5m_low \
python simulate.py [STOCK] [DATE] 07:00 12:00 --ticks --tick-cache tick_cache/
```

**Config D: Runner with VWAP trail (NEW)**
```bash
WB_SQ_PARTIAL_EXIT_ENABLED=1 WB_SQ_PARTIAL_PCT=50 WB_SQ_RUNNER_TRAIL_MODE=vwap \
python simulate.py [STOCK] [DATE] 07:00 12:00 --ticks --tick-cache tick_cache/
```

### New Trail Modes to Implement

In `simulate.py`, in the section that handles runner trailing after sq_target_hit:

```python
# New env var for runner trail mode
runner_trail_mode = os.getenv("WB_SQ_RUNNER_TRAIL_MODE", "r_multiple")  # "r_multiple" | "5m_low" | "vwap"
```

**Mode "5m_low":** After sq_target_hit fires the partial exit, the runner portion's trail stop = the low of the most recently COMPLETED 5-minute candle. Updated every time a new 5m candle closes with a higher low. Floor: never trail below entry price (breakeven protection).

```python
# Pseudocode for 5m_low trail:
if runner_trail_mode == "5m_low" and t.core_exit_reason == "sq_target_hit":
    # Get the most recent completed 5m candle low
    # (use bars_5m[-1].low if available, or compute from 1m bars)
    recent_5m_low = get_last_completed_5m_low(bars_1m, current_time)
    runner_stop = max(t.entry, recent_5m_low)  # Floor at entry price
    if price <= runner_stop:
        exit runner: "runner_5m_trail"
```

**Mode "vwap":** Runner trail = VWAP. If price drops below VWAP, exit runner. Floor: entry price.

```python
if runner_trail_mode == "vwap" and t.core_exit_reason == "sq_target_hit":
    runner_stop = max(t.entry, vwap)
    if price <= runner_stop:
        exit runner: "runner_vwap_trail"
```

**Mode "r_multiple":** Existing behavior — trail at N*R below current high. This is what `WB_SQ_RUNNER_TRAIL_R=5.0` uses.

### 5-Minute Bar Calculation

The sim already has 1m bars. To get 5m lows, group the most recent 5 completed 1m bars and take the min low:

```python
def get_last_completed_5m_low(bars_1m, current_minute):
    """Get the low of the most recently completed 5-minute bar."""
    # Find the most recent 5-min boundary that's already closed
    # e.g., at 08:13, the last completed 5m bar is 08:05-08:10 (bars 08:05, 08:06, 08:07, 08:08, 08:09)
    last_5m_boundary = (current_minute // 5) * 5
    # Get the 5 bars from (last_5m_boundary - 5) to (last_5m_boundary - 1)
    # These are the bars of the COMPLETED 5m candle
    relevant_bars = [b for b in bars_1m if (last_5m_boundary - 5) <= b.minute < last_5m_boundary]
    if not relevant_bars:
        return 0
    return min(b.low for b in relevant_bars)
```

Adapt this to however 1m bars are stored in the sim — the key is using COMPLETED 5m candles, not the current forming one.

### Gate Everything

```python
# All new behavior gated:
WB_SQ_RUNNER_TRAIL_MODE=r_multiple  # default = existing behavior, no change
```

Only "5m_low" and "vwap" modes are new code. The "r_multiple" mode is the existing runner trail.

---

### Test Stocks

**Value-add stocks (expect runner improvement):**

| Stock | Date | Why | Bot Baseline | Stock HOD |
|-------|------|-----|-------------|-----------|
| ALUR | 2025-01-24 | $8→$20, bot exits at $8.40 | +$2,306 | $20.00 |
| GDTC | 2025-01-06 | $6.68→$9.50, 2 cascade entries | +$4,352 | $9.50 |
| SHPH | 2026-01-20 | $2.75→$25, 3 cascade entries | +$3,115 | $25.11 |
| AMOD | 2025-01-30 | 3 cascade entries, strong continuation | +$3,788 | — |
| INM | 2025-01-21 | $7→$9.20, Ross made $12K | +$2,123 | $9.20 |

**Regression stocks (must be $0 delta or better):**

| Stock | Date | Why | Bot Baseline |
|-------|------|-----|-------------|
| VERO | 2026-01-16 | Cascade stock, must not degrade | +$562 |
| ROLR | 2026-01-14 | Cascade stock | +$12,601 |
| CRE | 2026-03-06 | Single SQ, no continuation | +$4,560 |

```bash
cd ~/warrior_bot_v2

echo "============================================"
echo "=== RUNNER MODE TEST — 4 CONFIGS × 8 STOCKS"
echo "============================================"

for stock_info in "ALUR 2025-01-24" "GDTC 2025-01-06" "SHPH 2026-01-20" "AMOD 2025-01-30" "INM 2025-01-21" "VERO 2026-01-16" "ROLR 2026-01-14" "CRE 2026-03-06"; do
    read stock date <<< "$stock_info"
    echo ""
    echo "=== $stock $date ==="

    echo "--- Config A: Baseline ---"
    python simulate.py $stock $date 07:00 12:00 --ticks --tick-cache tick_cache/

    echo "--- Config B: Runner 5R trail ---"
    WB_SQ_PARTIAL_EXIT_ENABLED=1 WB_SQ_PARTIAL_PCT=50 WB_SQ_RUNNER_TRAIL_R=5.0 \
    python simulate.py $stock $date 07:00 12:00 --ticks --tick-cache tick_cache/

    echo "--- Config C: Runner 5m-low trail ---"
    WB_SQ_PARTIAL_EXIT_ENABLED=1 WB_SQ_PARTIAL_PCT=50 WB_SQ_RUNNER_TRAIL_MODE=5m_low \
    python simulate.py $stock $date 07:00 12:00 --ticks --tick-cache tick_cache/

    echo "--- Config D: Runner VWAP trail ---"
    WB_SQ_PARTIAL_EXIT_ENABLED=1 WB_SQ_PARTIAL_PCT=50 WB_SQ_RUNNER_TRAIL_MODE=vwap \
    python simulate.py $stock $date 07:00 12:00 --ticks --tick-cache tick_cache/
done
```

---

## Part 2: Tick Wave Analysis (THE IMPORTANT PART)

This is where we gather the raw data to design the next iteration. We need to see exactly what happens tick-by-tick on big runners AFTER our SQ exit — every dip, every bounce, every volume shift.

### What To Extract

Write a script `analyze_runner_waves.py` that:

1. Loads IBKR tick data for a stock/date from tick_cache
2. Runs the SQ sim to identify all SQ entry/exit points
3. Starting from the FIRST sq_target_hit exit, builds a wave analysis of the continuation:

```python
# Output for each stock: a JSON + human-readable report showing:

{
    "stock": "ALUR",
    "date": "2025-01-24",
    "sq_exit_price": 8.40,
    "sq_exit_time": "07:05",
    "hod": 20.00,
    "hod_time": "09:15",
    "continuation_range_pct": 138.1,  # ($20 - $8.40) / $8.40

    # Wave analysis: every swing high/low after SQ exit
    "waves": [
        {
            "wave": 1,
            "type": "up",
            "start_price": 8.40,
            "end_price": 10.50,
            "start_time": "07:05",
            "end_time": "07:12",
            "duration_min": 7,
            "move_pct": 25.0,
            "avg_volume_per_min": 150000,
            "tick_count": 4200,
            "new_hod": true
        },
        {
            "wave": 2,
            "type": "down",    # THIS IS A DIP — potential re-entry
            "start_price": 10.50,
            "end_price": 9.80,
            "start_time": "07:12",
            "end_time": "07:15",
            "duration_min": 3,
            "retrace_pct": 33.3,  # retraced 33% of wave 1
            "avg_volume_per_min": 80000,  # volume declining on dip = healthy
            "tick_count": 1200,
            "held_above_vwap": true,
            "held_above_prior_wave_low": true
        },
        {
            "wave": 3,
            "type": "up",
            "start_price": 9.80,
            "end_price": 14.00,
            // ...
        },
        // ... continue until stock stops making new highs
    ],

    # Summary stats
    "total_up_waves": 5,
    "total_down_waves": 4,
    "avg_up_wave_pct": 18.5,
    "avg_down_wave_retrace_pct": 28.0,
    "avg_dip_duration_min": 2.5,
    "avg_dip_volume_vs_rally": 0.55,  # dip volume is 55% of rally volume
    "final_wave_type": "down",  # the LAST wave = the reversal
    "final_wave_retrace_pct": 65.0,  # the reversal retraced much deeper
    "final_wave_volume_vs_rally": 1.8,  # reversal had MORE volume than rally = dump
}
```

### Wave Detection Algorithm

A "wave" is a directional move between swing points. Use 1-minute bars for swing detection:

```python
def detect_waves(bars_1m, start_time):
    """
    Detect swing highs and lows using 1-minute bars.

    A swing high: bar where high > prior bar high AND high > next bar high
    A swing low: bar where low < prior bar low AND low < next bar low

    Build alternating up/down waves between swing points.
    """
    waves = []
    # ... implementation
    return waves
```

For each wave, also compute:
- **Volume ratio:** avg volume during this wave vs avg volume during prior wave (declining volume on dips = healthy pullback)
- **VWAP position:** did the dip hold above VWAP? (important support level)
- **EMA position:** did the dip hold above 9 EMA on 1m?
- **Retrace %:** how deep was the dip relative to the prior up-wave?
- **Duration:** how long was the dip? (1-3 bars = healthy, 5+ bars = momentum fading)
- **New HOD:** did the up-wave make a new session high of day?
- **Whole dollar levels:** did the wave interact with whole dollar levels ($10, $15, $20)?

### Stocks to Analyze

```bash
cd ~/warrior_bot_v2

# Big runners — these are the stocks where continuation matters most
python analyze_runner_waves.py ALUR 2025-01-24 --tick-cache tick_cache/
python analyze_runner_waves.py GDTC 2025-01-06 --tick-cache tick_cache/
python analyze_runner_waves.py SHPH 2026-01-20 --tick-cache tick_cache/
python analyze_runner_waves.py AMOD 2025-01-30 --tick-cache tick_cache/
python analyze_runner_waves.py INM 2025-01-21 --tick-cache tick_cache/

# 2026 runners for cross-validation
python analyze_runner_waves.py VERO 2026-01-16 --tick-cache tick_cache/
python analyze_runner_waves.py ROLR 2026-01-14 --tick-cache tick_cache/
python analyze_runner_waves.py EEIQ 2026-03-26 --tick-cache tick_cache/
python analyze_runner_waves.py ASTC 2026-03-30 --tick-cache tick_cache/

# Stocks that DIDN'T continue (control group) — what does the "done" signal look like?
python analyze_runner_waves.py CRE 2026-03-06 --tick-cache tick_cache/
python analyze_runner_waves.py NPT 2026-02-03 --tick-cache tick_cache/
```

### Output

Save each analysis to `wave_analysis/[STOCK]_[DATE].json` and `wave_analysis/[STOCK]_[DATE].md` (human-readable).

Also generate a **summary comparison** across all stocks: `wave_analysis/summary.md` with:
- Average dip retrace % on stocks that kept running vs stocks that were done
- Average dip volume ratio (dip vol / rally vol) on runners vs non-runners
- Average dip duration on runners vs non-runners
- What the "final wave" (the actual reversal) looked like vs the healthy dips

This is the data Manny and I need to see to design the next iteration of the strategy — what patterns signal "this dip is buyable" vs "this stock is done."

---

## Part 3: Combined Report

After running Parts 1 and 2, write a single report: `cowork_reports/2026-03-30_runner_mode_test_results.md` with:

1. **Runner mode test matrix** — all 4 configs × 8 stocks, P&L comparison table
2. **Best config determination** — which trail mode (5R, 5m-low, VWAP) produced the best results?
3. **Wave analysis summary** — key patterns from the tick data
4. **The "done" signal** — what distinguishes the final reversal dip from a healthy buyable dip?
5. **Regression check** — any degradation on VERO/ROLR/CRE?

---

## Implementation Order

1. Add `WB_SQ_RUNNER_TRAIL_MODE` env var and "5m_low" / "vwap" trail modes to `simulate.py`
2. Run Part 1 test matrix (4 configs × 8 stocks)
3. Write `analyze_runner_waves.py` script
4. Run Part 2 wave analysis on 11 stocks
5. Generate Part 3 combined report
6. Commit all results

---

## Env Var Summary (New)

```bash
# New in this directive:
WB_SQ_RUNNER_TRAIL_MODE=r_multiple    # "r_multiple" (default/existing) | "5m_low" | "vwap"

# Existing (being tested with new values):
WB_SQ_PARTIAL_EXIT_ENABLED=0          # Gate for partial exit at sq_target_hit
WB_SQ_PARTIAL_PCT=50                  # % to exit at target (50 = keep 50% as runner)
WB_SQ_RUNNER_TRAIL_R=5.0              # R-multiple trail (only when mode=r_multiple)
```

---

## The Bottom Line

This directive does two things. First, it tests whether the existing runner infrastructure — with better trail parameters — can capture more of big runners like ALUR ($8→$20). Second, and more importantly, it extracts the tick-level wave data we need to design a smarter "play the stock" strategy: take profit on the wave, re-enter on the dip, take profit again, and know when the dips stop bouncing = the run is over.

The wave analysis data is the foundation. The runner mode test tells us if a simple trail approach works. If it does, great. If it doesn't, the wave data tells us what the right approach is.
