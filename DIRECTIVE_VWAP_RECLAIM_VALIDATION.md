# Directive: VWAP Reclaim (Strategy 4) — Validation & Backtest

## Priority: HIGH
## Created: 2026-03-20 by Cowork (Opus)

---

## Context

Strategy 4 (VWAP Reclaim) has been implemented in two files:

1. **`vwap_reclaim_detector.py`** — New file. State machine: IDLE → BELOW_VWAP → RECLAIMED → ARMED → TRIGGERED. Detects Ross Cameron's "first 1-min candle to make a new high after VWAP reclaim" pattern.

2. **`simulate.py`** — Updated with full VR integration (init, seed, 1m detection, 1m exits, tick trigger, tick exits). Priority order: Squeeze > VWAP Reclaim > Micro Pullback.

**Design doc**: `DESIGN_VWAP_RECLAIM_DETECTOR.md`

All gated by `WB_VR_ENABLED=0` (OFF by default). No changes to bot.py (backtest-only for now).

---

## Phase 0: Git Pull + Review

```bash
cd ~/warrior_bot && git pull
# Review new files:
cat vwap_reclaim_detector.py
# Verify simulate.py changes compile:
python -c "import py_compile; py_compile.compile('simulate.py', doraise=True); print('OK')"
```

---

## Phase 1: Regression Check (CRITICAL — must pass before anything else)

VR is OFF by default, so existing regressions MUST be unchanged:

```bash
source venv/bin/activate

# VERO regression (target: +$18,583)
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/

# ROLR regression (target: +$6,444)
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```

**STOP if either regression fails.** Do not proceed to Phase 2.

---

## Phase 2: CHNR Manual Backtest (Known VWAP Reclaim Stock)

CHNR 2026-03-19 — Ross made +$2,506. 2 of 3 trades were VWAP reclaim setups.
Scanner precise discovery: 07:16 ET.

### 2a. First, run WITHOUT VR (baseline — should match known results):
```bash
WB_VR_ENABLED=0 WB_SQUEEZE_ENABLED=1 \
python simulate.py CHNR 2026-03-19 07:16 12:00 --ticks --tick-cache tick_cache/ -v
```

### 2b. Then, run WITH VR enabled:
```bash
WB_VR_ENABLED=1 WB_SQUEEZE_ENABLED=1 \
python simulate.py CHNR 2026-03-19 07:16 12:00 --ticks --tick-cache tick_cache/ -v
```

**Expected**: VR should detect at least one VWAP reclaim entry after the initial squeeze leg cools off and price dips below VWAP, then recovers.

### 2c. Record results:
| Config | Trades | P&L | Setup Types | Notes |
|--------|--------|-----|-------------|-------|
| MP+SQ only | ? | ? | ? | Baseline |
| MP+SQ+VR | ? | ? | ? | New |

---

## Phase 3: ARTL Manual Backtest (Known VWAP Reclaim Stock)

ARTL 2026-03-18 — Ross made +$9,653. Multiple VWAP reclaim attempts at 08:16.
Scanner checkpoint: 08:00 ET. (Precise discovery not yet resolved — use 08:00 for now.)

### 3a. Baseline:
```bash
WB_VR_ENABLED=0 WB_SQUEEZE_ENABLED=1 \
python simulate.py ARTL 2026-03-18 08:00 12:00 --ticks --tick-cache tick_cache/ -v
```

### 3b. With VR:
```bash
WB_VR_ENABLED=1 WB_SQUEEZE_ENABLED=1 \
python simulate.py ARTL 2026-03-18 08:00 12:00 --ticks --tick-cache tick_cache/ -v
```

### 3c. Record results:
| Config | Trades | P&L | Setup Types | Notes |
|--------|--------|-----|-------------|-------|
| MP+SQ only | ? | ? | ? | Baseline |
| MP+SQ+VR | ? | ? | ? | New |

---

## Phase 4: Full YTD Backtest (MP + Squeeze + VR) — DO NOT RUN YET

**STOP HERE.** Do NOT run the full YTD backtest. Write the Phase 5 report with CHNR + ARTL results first and commit it. Manny will review the results and decide whether to proceed with the full YTD run.

When approved, the full YTD procedure is:

### Option A: Use existing batch runner
Modify `run_ytd_v2_backtest.py` ENV_BASE to include:
```
WB_VR_ENABLED=1
```

Then run:
```bash
python run_ytd_v2_backtest.py --resume
```

### Option B: Manual loop (if batch runner needs modification)
For each date in the 55-day YTD dataset, run with VR enabled and record results.

**Key reporting**: Include per-strategy breakdown in the results:
- MP trades: count, win rate, P&L
- Squeeze trades: count, win rate, P&L
- VR trades: count, win rate, P&L
- Total

---

## Phase 5: Report

Write report to `cowork_reports/2026-03-20_vr_validation.md` with:

1. Regression status (PASS/FAIL)
2. CHNR results table (baseline vs VR)
3. ARTL results table (baseline vs VR)
4. YTD summary with per-strategy breakdown
5. Any issues or unexpected behavior
6. VR detector log snippets showing state transitions (BELOW_VWAP → RECLAIMED → ARMED → TRIGGERED or resets)

---

## VR Environment Variables Reference

```bash
# Detection
WB_VR_ENABLED=1
WB_VR_VOL_MULT=1.5          # Reclaim bar volume >= 1.5x avg
WB_VR_MIN_BODY_PCT=0.5      # Min body % for confirmation bar
WB_VR_MAX_BELOW_BARS=10     # Max bars below VWAP before reset
WB_VR_MAX_R=0.50            # Max risk per share
WB_VR_MAX_R_PCT=3.0         # Max R as % of price
WB_VR_MACD_GATE=0           # MACD filter (optional, off by default)
WB_VR_RECLAIM_WINDOW=3      # Bars to wait for new-high after reclaim
WB_VR_MAX_ATTEMPTS=2        # Max attempts per stock per session

# Sizing
WB_VR_PROBE_SIZE_MULT=0.5   # First attempt = 50% size
WB_VR_FULL_AFTER_WIN=1      # Full size after first winner

# Exits
WB_VR_CORE_PCT=75           # Core position %
WB_VR_TARGET_R=1.5          # Core TP at 1.5R
WB_VR_RUNNER_TRAIL_R=2.0    # Runner trails at 2.0R
WB_VR_VWAP_EXIT=1           # Exit all if VWAP lost (CRITICAL)
WB_VR_STALL_BARS=5          # Time stop after N bars no new high
WB_VR_TRAIL_R=1.5           # Pre-target trailing stop
WB_VR_MAX_LOSS_DOLLARS=300  # Dollar loss cap per VR trade
```

---

## Regression Targets (unchanged)
- VERO 2026-01-16: +$18,583
- ROLR 2026-01-14: +$6,444

---

*Directive by Cowork (Opus) — 2026-03-20*
