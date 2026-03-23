# DIRECTIVE: Daily Recap Backtest — 2026-03-23

**Author**: Cowork (Opus)
**Date**: 2026-03-23 (v2 — adds SQ exit fixes)
**For**: CC (Sonnet)
**Purpose**: Re-run today's backtest with squeeze exit fixes enabled. Previous run used default config (SQ exit fixes OFF), which caused `sq_target_hit` to chop at exactly 2R instead of letting runners run.

---

## Context

The first backtest showed AHMA's second trade hitting `sq_target_hit` at +3.4R and exiting — but with `WB_SQ_PARTIAL_EXIT_ENABLED=0`, this was a full exit at the target rather than a 50% partial with a runner. The squeeze exit fixes (partial exit, wide trail, runner detect) are coded in simulate.py but were never added to the batch runner's ENV_BASE. This re-run uses the same config as the Jan comparison directive.

## Tick Data

Already cached (commit `21907d3`):
```
tick_cache/2026-03-23/UGRO.json.gz  (3.8 MB)
tick_cache/2026-03-23/AHMA.json.gz  (1.4 MB)
tick_cache/2026-03-23/WSHP.json.gz  (139 KB)
```

---

## Step 1: Re-run Backtests with Full Config

Use this exact env for all 3 stocks — matches the Jan comparison directive ENV_BASE:

```bash
source venv/bin/activate

COMMON_ENV="WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_ALLOW_UNKNOWN_FLOAT=1 \
WB_PILLAR_GATES_ENABLED=1 WB_CLASSIFIER_ENABLED=1 WB_CLASSIFIER_RECLASS_ENABLED=1 \
WB_EXHAUSTION_ENABLED=1 WB_WARMUP_BARS=5 \
WB_CONTINUATION_HOLD_ENABLED=1 WB_CONT_HOLD_5M_TREND_GUARD=1 \
WB_NO_REENTRY_ENABLED=1 WB_MAX_NOTIONAL=50000 WB_MAX_LOSS_R=0.75 \
WB_SQ_VOL_MULT=3.0 WB_SQ_MIN_BAR_VOL=50000 WB_SQ_MIN_BODY_PCT=1.5 \
WB_SQ_PRIME_BARS=3 WB_SQ_MAX_R=0.80 \
WB_SQ_LEVEL_PRIORITY=pm_high,whole_dollar,pdh \
WB_SQ_PROBE_SIZE_MULT=0.5 WB_SQ_MAX_ATTEMPTS=3 \
WB_SQ_PARA_ENABLED=1 WB_SQ_PARA_STOP_OFFSET=0.10 WB_SQ_PARA_TRAIL_R=1.0 \
WB_SQ_NEW_HOD_REQUIRED=1 WB_SQ_MAX_LOSS_DOLLARS=500 \
WB_SQ_TARGET_R=2.0 WB_SQ_CORE_PCT=75 \
WB_SQ_RUNNER_TRAIL_R=2.5 WB_SQ_TRAIL_R=1.5 \
WB_SQ_STALL_BARS=5 WB_SQ_VWAP_EXIT=1 WB_SQ_PM_CONFIDENCE=1 \
WB_SQ_PARTIAL_EXIT_ENABLED=1 \
WB_SQ_WIDE_TRAIL_ENABLED=1 \
WB_SQ_RUNNER_DETECT_ENABLED=1 \
WB_HALT_THROUGH_ENABLED=1"
```

```bash
# UGRO — discovered 07:06, sim from 07:00
eval $COMMON_ENV \
WB_SCANNER_GAP_PCT=46.79 WB_SCANNER_RVOL=33.04 WB_SCANNER_FLOAT_M=0.67 \
python simulate.py UGRO 2026-03-23 07:00 12:00 --ticks --tick-cache tick_cache/

# AHMA — discovered 09:15, sim from 09:30
eval $COMMON_ENV \
WB_SCANNER_GAP_PCT=46.55 WB_SCANNER_RVOL=112.66 WB_SCANNER_FLOAT_M=2.02 \
python simulate.py AHMA 2026-03-23 09:30 12:00 --ticks --tick-cache tick_cache/

# WSHP — discovered 07:58, sim from 08:00
eval $COMMON_ENV \
WB_SCANNER_GAP_PCT=19.97 WB_SCANNER_RVOL=2.21 WB_SCANNER_FLOAT_M=1.33 \
python simulate.py WSHP 2026-03-23 08:00 12:00 --ticks --tick-cache tick_cache/
```

---

## Step 2: Compare Against Previous Run (SQ Fixes OFF)

Previous results (SQ exit fixes OFF):
```
UGRO: 4 trades (3 SQ, 1 MP), +$50
  - 07:12 SQ stopped out -$429
  - 07:12 SQ +$1,159 (+2.3R) ← did this hit sq_target_hit?
  - 07:18 MP -$324
  - Late SQ -$357

AHMA: 2 trades (2 SQ), -$375
  - First SQ: -$2,071 (-4.1R) ← dollar loss cap
  - 09:36 SQ: +$1,696 (+3.4R) ← sq_target_hit at 2R, got 3.4R exit?

WSHP: 0 trades

TOTAL: 6 trades, -$325
```

For each stock, note what changed with fixes ON:
- Did UGRO's +2.3R trade keep a runner portion?
- Did AHMA's second trade hold a runner past the 2R target?
- Did the wide trail prevent any of the stop-outs?

---

## Step 3: Output Summary

Print results in this format:

```
=== 2026-03-23 BACKTEST RESULTS (SQ exit fixes ON) ===

UGRO (gap +46.8%, rvol 33.0x, float 0.67M, sim 07:00-12:00):
  Trade 1: [time] [entry] → [exit] [reason] [P&L] [R-mult] [setup_type]
  ...
  TOTAL: X trades, $XXX P&L

AHMA (gap +46.5%, rvol 112.7x, float 2.02M, sim 09:30-12:00):
  ...
  TOTAL: X trades, $XXX P&L

WSHP (gap +20.0%, rvol 2.2x, float 1.33M, sim 08:00-12:00):
  ...
  TOTAL: X trades, $XXX P&L

DAY TOTAL: X trades, $X,XXX P&L (X SQ / X MP)

=== COMPARISON: SQ Fixes OFF vs ON ===
           Fixes OFF    Fixes ON    Delta
UGRO:      +$50         $XXX        +$XXX
AHMA:      -$375        $XXX        +$XXX
WSHP:      $0           $0          $0
TOTAL:     -$325        $XXX        +$XXX
```

---

## Step 4: No Separate Commit Needed

This is a re-run with different config — no new tick data or code changes. Just report the results back. Cowork will update the daily tracker.

---

## Key Question

The -$325 with fixes OFF was disappointing. With the partial exit + runner detection + wide trail, does AHMA's second trade (which hit 3.4R) keep a runner that rides higher? That's the whole thesis behind the SQ exit fixes.
