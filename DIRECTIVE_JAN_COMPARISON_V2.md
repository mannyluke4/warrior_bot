# DIRECTIVE: January 2025 vs January 2026 — V2 (Ross Exit Enabled)

**Author**: Cowork (Opus)
**Date**: 2026-03-23
**For**: CC (Sonnet)
**Purpose**: Re-run the January comparison with `WB_ROSS_EXIT_ENABLED=1` to measure the impact of 1m signal-based exits across two full months. This is the A/B counterpart to V1 (which ran without Ross exit).

---

## Context

V1 (`DIRECTIVE_JAN_COMPARISON_V1.md`) ran both months with scanner fixes + SQ exit fixes but WITHOUT Ross exit. V1 results are the baseline:
- **Jan 2025 (V1)**: 21 days, 32 trades, +$3,423, equity $33,423
- **Jan 2026 (V1)**: 21 days, TBD (just completed — check `jan_comparison_v1_state.json`)

V2 adds `WB_ROSS_EXIT_ENABLED=1`. When Ross exit is ON:
- **Replaces**: 10s BE/TW pattern exits, fixed R trails (signal mode trail=0.99 = no-op)
- **Keeps**: hard stop, max_loss_hit, bail timer (fire on every tick)
- **Uses**: 1m candle signals (CUC, doji 50% partial, gravestone, shooting star, topping tail) + MACD/EMA20/VWAP backstops
- **Structural trailing stop**: `t.stop` ratchets up to low of last green 1m candle
- **MACD warmup**: ~35 bars before MACD backstop active; pattern exits work after bar 2

**This is the central question**: Does Ross exit improve or hurt when combined with all the other fixes across a full month of data?

---

## Step 0: Confirm V1 Results

Before starting V2, confirm V1 is fully complete:
```bash
python3 -c "
import json
with open('jan_comparison_v1_state.json') as f:
    s = json.load(f)
print(f'Jan 2025: {len(s[\"jan2025\"][\"daily\"])} days, {len(s[\"jan2025\"][\"trades\"])} trades, equity \${s[\"jan2025\"][\"equity\"]:,}')
print(f'Jan 2026: {len(s[\"jan2026\"][\"daily\"])} days, {len(s[\"jan2026\"][\"trades\"])} trades, equity \${s[\"jan2026\"][\"equity\"]:,}')
"
```
Both months should show 21 days. If V1 is incomplete, finish it first — V2 report depends on V1 as the baseline.

---

## Step 1: Build the V2 Runner

Create `run_jan_v2_comparison.py` — clone from `run_jan_v1_comparison.py` with these changes:

### 1a. ENV_BASE — add Ross exit vars

Copy V1's ENV_BASE and add the Ross exit block. Full ENV_BASE:
```python
ENV_BASE = {
    # --- Core strategy ---
    "WB_CLASSIFIER_ENABLED": "1",
    "WB_CLASSIFIER_RECLASS_ENABLED": "1",
    "WB_EXHAUSTION_ENABLED": "1",
    "WB_WARMUP_BARS": "5",
    "WB_CONTINUATION_HOLD_ENABLED": "1",
    "WB_CONT_HOLD_5M_TREND_GUARD": "1",
    "WB_CONT_HOLD_5M_VOL_EXIT_MULT": "2.0",
    "WB_CONT_HOLD_5M_MIN_BARS": "2",
    "WB_CONT_HOLD_MIN_VOL_DOM": "2.0",
    "WB_CONT_HOLD_MIN_SCORE": "8.0",
    "WB_CONT_HOLD_MAX_LOSS_R": "0.5",
    "WB_CONT_HOLD_CUTOFF_HOUR": "10",
    "WB_CONT_HOLD_CUTOFF_MIN": "30",
    "WB_MAX_NOTIONAL": "50000",
    "WB_MAX_LOSS_R": "0.75",
    "WB_NO_REENTRY_ENABLED": "1",
    # --- Strategy 2: Squeeze V2 ---
    "WB_SQUEEZE_ENABLED": "1",
    "WB_SQ_VOL_MULT": "3.0",
    "WB_SQ_MIN_BAR_VOL": "50000",
    "WB_SQ_MIN_BODY_PCT": "1.5",
    "WB_SQ_PRIME_BARS": "3",
    "WB_SQ_MAX_R": "0.80",
    "WB_SQ_LEVEL_PRIORITY": "pm_high,whole_dollar,pdh",
    "WB_SQ_PROBE_SIZE_MULT": "0.5",
    "WB_SQ_MAX_ATTEMPTS": "3",
    "WB_SQ_PARA_ENABLED": "1",
    "WB_SQ_PARA_STOP_OFFSET": "0.10",
    "WB_SQ_PARA_TRAIL_R": "1.0",
    "WB_SQ_NEW_HOD_REQUIRED": "1",
    "WB_SQ_MAX_LOSS_DOLLARS": "500",
    "WB_SQ_TARGET_R": "2.0",
    "WB_SQ_CORE_PCT": "75",
    "WB_SQ_RUNNER_TRAIL_R": "2.5",
    "WB_SQ_TRAIL_R": "1.5",
    "WB_SQ_STALL_BARS": "5",
    "WB_SQ_VWAP_EXIT": "1",
    "WB_SQ_PM_CONFIDENCE": "1",
    "WB_PILLAR_GATES_ENABLED": "1",
    "WB_MP_ENABLED": "1",
    # --- Scanner fixes ---
    "WB_ALLOW_UNKNOWN_FLOAT": "1",
    # --- Squeeze exit fixes ---
    "WB_SQ_PARTIAL_EXIT_ENABLED": "1",
    "WB_SQ_WIDE_TRAIL_ENABLED": "1",
    "WB_SQ_RUNNER_DETECT_ENABLED": "1",
    "WB_HALT_THROUGH_ENABLED": "1",
    # --- NEW in V2: Ross Cameron 1m signal exits ---
    "WB_ROSS_EXIT_ENABLED": "1",           # Master switch — replaces 10s BE/TW exits
    "WB_ROSS_MIN_BARS": "2",               # Min 1m bars before any signal fires
    "WB_ROSS_CUC_ENABLED": "1",            # Candle Under Candle → 100% exit
    "WB_ROSS_DOJI_ENABLED": "1",           # Doji → 50% partial
    "WB_ROSS_GRAVESTONE_ENABLED": "1",     # Gravestone doji → 100% exit
    "WB_ROSS_SHOOTING_STAR_ENABLED": "1",  # Shooting star → 100% exit
    "WB_ROSS_TOPPING_TAIL_ENABLED": "1",   # Topping tail (green w/ big wick) → 50% partial
    "WB_ROSS_MACD_ENABLED": "1",           # MACD histogram negative → 100% backstop
    "WB_ROSS_EMA20_ENABLED": "1",          # Close below 20 EMA → 100% backstop
    "WB_ROSS_VWAP_ENABLED": "1",           # Close below VWAP → 100% backstop
    "WB_ROSS_STRUCTURAL_TRAIL": "1",       # Trail = low of last green 1m candle
    "WB_ROSS_CUC_FLOOR_R": "0.0",         # CUC fires at any R (0 = disabled)
    "WB_ROSS_CUC_MIN_TRADE_BARS": "0",    # No CUC suppression window (0 = disabled)
    "WB_ROSS_BACKSTOP_MIN_R": "0.0",       # Backstops always full strength (0 = no softening)
}
```

### 1b. Fresh state file

Use `jan_comparison_v2_state.json` (NOT v1). No resuming from V1.

### 1c. Output file

Use `jan_comparison_v2_output.txt`.

### 1d. Fix the None float crash from V1

In the candidate printing line, guard against `None` values:
```python
f"gap={c.get('gap_pct', 0) or 0:.0f}% float={c.get('float_millions', 0) or 0:.1f}M"
```
Apply this to ALL format strings that touch `gap_pct` or `float_millions`.

### 1e. Everything else identical to V1

Same dates, same `load_and_rank()`, same risk model ($30K equity, 2.5% risk, 5 trades/day, -$1,500 daily loss limit), same tick cache, same scanner JSONs.

---

## Step 2: Regression Check

Ross exit replaces 10s pattern exits for ALL trade types. Verify MP regressions still hold:

```bash
source venv/bin/activate

# VERO: MP trade — Ross exit active, SQ exit fixes also on
WB_MP_ENABLED=1 WB_ROSS_EXIT_ENABLED=1 WB_SQ_PARTIAL_EXIT_ENABLED=1 WB_SQ_WIDE_TRAIL_ENABLED=1 WB_SQ_RUNNER_DETECT_ENABLED=1 WB_HALT_THROUGH_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# IMPORTANT: VERO result WILL CHANGE vs V1 because Ross exit replaces BE/TW exits.
# V1 baseline: +$18,583 (BE exit at 18.6R). Record V2 result — this IS the test.

# ROLR: MP trade
WB_MP_ENABLED=1 WB_ROSS_EXIT_ENABLED=1 WB_SQ_PARTIAL_EXIT_ENABLED=1 WB_SQ_WIDE_TRAIL_ENABLED=1 WB_SQ_RUNNER_DETECT_ENABLED=1 WB_HALT_THROUGH_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# V1 baseline: +$6,444. Record V2 result.
```

**NOTE**: Unlike V1 regression checks, we EXPECT the numbers to change here. Ross exit uses different signals (1m CUC/doji/gravestone vs 10s BE/TW). Record both V1 and V2 results for the report. If results go catastrophically negative (like -$5K+), stop and investigate before running the full batch.

---

## Step 3: Run It

```bash
source venv/bin/activate
python run_jan_v2_comparison.py 2>&1 | tee jan_comparison_v2_output.txt
```

This runs from scratch — all 21 days for each month. ~40+ dates x 5 stocks x tick replay.

---

## Step 4: Produce V2 Report

Save to `cowork_reports/2026-03-23_jan_comparison_v2.md` with:

### Section 1: V1 vs V2 Summary (THE KEY TABLE)

```
╔════════════════════════════════════════════════════════════════════════════════════╗
║            ROSS EXIT A/B: V1 (no Ross) vs V2 (Ross ON)                           ║
╠═══════════════════════════════╦═══════════════╦═══════════════╦════════════════════╣
║ Metric                        ║  V1 (no Ross) ║  V2 (Ross ON) ║  Delta            ║
╠═══════════════════════════════╬═══════════════╬═══════════════╬════════════════════╣
║ Jan 2025 Total P&L            ║  $X,XXX       ║  $X,XXX       ║  +/-$X,XXX        ║
║ Jan 2025 Win Rate             ║  XX%          ║  XX%          ║  +/-X%            ║
║ Jan 2025 Trades               ║  XX           ║  XX           ║  +/-X             ║
║ Jan 2026 Total P&L            ║  $X,XXX       ║  $X,XXX       ║  +/-$X,XXX        ║
║ Jan 2026 Win Rate             ║  XX%          ║  XX%          ║  +/-X%            ║
║ Jan 2026 Trades               ║  XX           ║  XX           ║  +/-X             ║
║ Combined P&L (both months)    ║  $X,XXX       ║  $X,XXX       ║  +/-$X,XXX        ║
║ VERO standalone               ║  +$18,583     ║  $X,XXX       ║  +/-$X,XXX        ║
║ ROLR standalone               ║  +$6,444      ║  $X,XXX       ║  +/-$X,XXX        ║
╚═══════════════════════════════╩═══════════════╩═══════════════╩════════════════════╝
```

### Section 2: Per-Month Detail

Same tables as V1 report — per-day breakdown for each month showing candidates, trades, P&L, equity.

### Section 3: Exit Reason Analysis

This is the most important diagnostic section. For V2 trades, group by exit reason:
- `ross_cuc` — how many, avg P&L, avg R
- `ross_doji_partial` — how many, avg P&L
- `ross_gravestone` — how many, avg P&L
- `ross_shooting_star` — how many, avg P&L
- `ross_topping_tail` — how many, avg P&L
- `ross_macd_backstop` — how many, avg P&L (note: only active after ~35 bars)
- `ross_ema20_backstop` — how many, avg P&L
- `ross_vwap_backstop` — how many, avg P&L
- `ross_structural_trail` — how many, avg P&L
- Non-Ross exits (hard stop, max_loss, bail timer) — how many, avg P&L

### Section 4: Trade-by-Trade Comparison

For every stock+date that appears in BOTH V1 and V2, show:
```
Symbol  Date        V1 Exit Reason          V1 P&L    V2 Exit Reason          V2 P&L    Delta
GDTC    2025-01-06  sq_target_hit           +$2,175   ross_structural_trail   +$X,XXX   +/-$XXX
...
```

This is how we identify whether Ross exit is letting winners run longer or cutting them short.

### Section 5: Strategy Breakdown (SQ vs MP)

Compare SQ and MP performance separately between V1 and V2. Ross exit affects both, but differently:
- MP trades: Ross exit replaces 10s BE/TW exits (major change)
- SQ trades: Ross exit replaces sq_target_hit hard exit (also major change — interacts with partial exit)

### Section 6: Verdict

Based on the data, state clearly:
- Does Ross exit improve total P&L?
- Does it improve win rate?
- Does it help more on MP or SQ trades?
- Are there specific exit signals that are too aggressive (cutting winners) or too loose (giving back gains)?
- Recommendation: should `WB_ROSS_EXIT_ENABLED=1` stay in the live config?

---

## Step 5: Commit and Push

```bash
git add run_jan_v2_comparison.py jan_comparison_v2_state.json jan_comparison_v2_output.txt cowork_reports/2026-03-23_jan_comparison_v2.md
git commit -m "$(cat <<'EOF'
Jan comparison V2: Ross exit A/B test (WB_ROSS_EXIT_ENABLED=1)

Re-ran Jan 2025 + Jan 2026 with Ross Cameron 1m signal exits enabled.
Compared against V1 baseline (same config minus Ross exit).
Includes exit reason analysis and trade-by-trade V1 vs V2 comparison.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## What We're Looking For

1. **Net P&L impact**: Does Ross exit make more or less money than 10s BE/TW exits?
2. **Winner retention**: Do big runners (VERO, SPHL, AIFF) exit at higher or lower prices?
3. **Loser management**: Do the 1m signals cut losers faster or slower than the 10s patterns?
4. **MACD warmup gap**: Early trades (first 35 min) only have pattern exits, no backstops. Does this create a vulnerability window?
5. **SQ interaction**: Ross exit replaces sq_target_hit. With partial exit ON, does Ross exit improve the runner phase?
6. **Consistency**: Is the Ross exit effect consistent across both months, or is it stock-dependent?

This is the definitive A/B test. V1 is the control, V2 is the treatment.
