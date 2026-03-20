# Directive: Weekend Megatest — Full Strategy Matrix

## Priority: HIGH (run overnight / over the weekend)
## Created: 2026-03-20 by Cowork (Opus)
## Depends on: VR V3 code fix (DIRECTIVE_VR_TUNING_V3.md Phase 1) must be applied first
## Depends on: Scanner re-scan should be complete (297 dates, Jan 2025 - Mar 2026)

---

## Overview

Run every meaningful strategy combination across the full 297-day dataset (Jan 2025 - today). This gives us the definitive answer on which strategy combos work, how they interact, and where VR stands even at this early stage.

**7 strategy combos × 297 days × ~5 stocks/day = ~10,000+ simulations**

This will take many hours. Run sequentially (one combo at a time) to avoid overloading the machine.

---

## Phase 0: Prerequisites

### 0a. Git Pull
```bash
cd ~/warrior_bot && git pull origin main
source venv/bin/activate
```

### 0b. Apply VR V3 Code Fix (if not already done)
The `severe_vwap_loss` fix from `DIRECTIVE_VR_TUNING_V3.md` Phase 1 must be applied first:
- Add `WB_VR_SEVERE_VWAP_LOSS_PCT` env var to `vwap_reclaim_detector.py` `__init__`
- Replace hardcoded `5.0` on line ~168 with `self.severe_vwap_loss_pct`
- Default: 20.0

### 0c. Regression Check
```bash
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# TARGET: +$18,583

python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# TARGET: +$6,444
```
If regression fails, STOP. Fix the issue before proceeding.

### 0d. Verify Scanner Data Coverage
```bash
ls scanner_results/20*.json | grep -E '/[0-9]{4}-[0-9]{2}-[0-9]{2}\.json$' | wc -l
# Should be ~297 files covering 2025-01-02 through 2026-03-20
```

---

## Phase 1: Create Megatest Runner

Create `run_megatest.py` — a wrapper around the existing batch backtest that:

1. **Accepts strategy combo as CLI argument**
2. **Overrides ENV_BASE per combo** (controls which strategies are ON/OFF)
3. **Uses combo-specific state files** (so runs don't clobber each other)
4. **Covers ALL 297 dates** (Jan 2025 - today, auto-discovered from scanner_results/)
5. **Writes combo-specific results** to `megatest_results/`

### Strategy Combos

| Combo ID | MP | SQ | VR | State File | Description |
|----------|----|----|-----|------------|-------------|
| `mp_only` | ON | OFF | OFF | `megatest_state_mp_only.json` | Baseline — micro pullback alone |
| `sq_only` | OFF* | ON | OFF | `megatest_state_sq_only.json` | Squeeze alone (no MP entries) |
| `vr_only` | OFF* | OFF | ON | `megatest_state_vr_only.json` | VR alone (data gathering) |
| `mp_sq` | ON | ON | OFF | `megatest_state_mp_sq.json` | Current live config |
| `mp_vr` | ON | OFF | ON | `megatest_state_mp_vr.json` | MP + VR (no squeeze) |
| `sq_vr` | OFF* | ON | ON | `megatest_state_sq_vr.json` | SQ + VR (no MP) |
| `all_three` | ON | ON | ON | `megatest_state_all_three.json` | Everything on |

*Note on "OFF" for MP: The micro pullback detector is always active (no env var gate). To truly disable MP entries, add a gate: `WB_MP_SUPPRESS_ENTRIES=1`. When this is set, the detector still runs (needed for EMA/state) but `on_trade_price` returns None before checking triggers. This is a small code change — see implementation notes below.

**If adding an MP gate is too complex**, an alternative approach: run all 7 combos but for "sq_only", "vr_only", and "sq_vr", just filter the results post-hoc by `setup_type` field. The trade output already tags each trade as `micro_pullback`, `squeeze`, or `vr`. CC can parse the output and only count trades matching the active strategies.

### Implementation Notes

**Option A: Add MP suppress gate (preferred, more accurate)**

In `micro_pullback.py`, `on_trade_price()` method, add at the top:
```python
if os.getenv("WB_MP_SUPPRESS_ENTRIES", "0") == "1":
    return None
```
This keeps all state tracking intact but prevents MP from arming/triggering.

**Option B: Post-hoc filtering (simpler, slightly less accurate)**

Run all combos with MP always on, then filter trades by `setup_type`. Less accurate because MP trades may affect the daily P&L limit / consecutive loss counter, but good enough for a first pass.

CC should decide which approach is more practical. Both are acceptable.

### ENV_BASE Overrides Per Combo

The runner should start with the current `ENV_BASE` from `run_ytd_v2_backtest.py` as the baseline, then apply these overrides:

```python
COMBO_OVERRIDES = {
    "mp_only": {
        "WB_SQUEEZE_ENABLED": "0",
        "WB_VR_ENABLED": "0",
    },
    "sq_only": {
        "WB_SQUEEZE_ENABLED": "1",
        "WB_VR_ENABLED": "0",
        "WB_MP_SUPPRESS_ENTRIES": "1",  # Option A only
    },
    "vr_only": {
        "WB_SQUEEZE_ENABLED": "0",
        "WB_VR_ENABLED": "1",
        "WB_MP_SUPPRESS_ENTRIES": "1",  # Option A only
        "WB_VR_MAX_R": "1.00",
        "WB_VR_MAX_R_PCT": "5.0",
        "WB_VR_RECLAIM_WINDOW": "5",
        "WB_VR_MAX_BELOW_BARS": "20",
        "WB_VR_MAX_ATTEMPTS": "3",
        "WB_VR_SEVERE_VWAP_LOSS_PCT": "20.0",
    },
    "mp_sq": {
        "WB_SQUEEZE_ENABLED": "1",
        "WB_VR_ENABLED": "0",
    },
    "mp_vr": {
        "WB_SQUEEZE_ENABLED": "0",
        "WB_VR_ENABLED": "1",
        "WB_VR_MAX_R": "1.00",
        "WB_VR_MAX_R_PCT": "5.0",
        "WB_VR_RECLAIM_WINDOW": "5",
        "WB_VR_MAX_BELOW_BARS": "20",
        "WB_VR_MAX_ATTEMPTS": "3",
        "WB_VR_SEVERE_VWAP_LOSS_PCT": "20.0",
    },
    "sq_vr": {
        "WB_SQUEEZE_ENABLED": "1",
        "WB_VR_ENABLED": "1",
        "WB_MP_SUPPRESS_ENTRIES": "1",  # Option A only
        "WB_VR_MAX_R": "1.00",
        "WB_VR_MAX_R_PCT": "5.0",
        "WB_VR_RECLAIM_WINDOW": "5",
        "WB_VR_MAX_BELOW_BARS": "20",
        "WB_VR_MAX_ATTEMPTS": "3",
        "WB_VR_SEVERE_VWAP_LOSS_PCT": "20.0",
    },
    "all_three": {
        "WB_SQUEEZE_ENABLED": "1",
        "WB_VR_ENABLED": "1",
        "WB_VR_MAX_R": "1.00",
        "WB_VR_MAX_R_PCT": "5.0",
        "WB_VR_RECLAIM_WINDOW": "5",
        "WB_VR_MAX_BELOW_BARS": "20",
        "WB_VR_MAX_ATTEMPTS": "3",
        "WB_VR_SEVERE_VWAP_LOSS_PCT": "20.0",
    },
}
```

### VR Env Vars (V3 thresholds for all VR-enabled combos)

Every combo that has `WB_VR_ENABLED=1` must also include:
```
WB_VR_MAX_R=1.00
WB_VR_MAX_R_PCT=5.0
WB_VR_RECLAIM_WINDOW=5
WB_VR_MAX_BELOW_BARS=20
WB_VR_MAX_ATTEMPTS=3
WB_VR_SEVERE_VWAP_LOSS_PCT=20.0
```

### Date Discovery

Instead of a hardcoded DATES list, discover dates dynamically:
```python
import glob
dates = sorted([
    os.path.basename(f).replace('.json', '')
    for f in glob.glob('scanner_results/20??-??-??.json')
])
```

### Existing Fix Env Vars (always ON for all combos)

These are the validated fixes from our study. They stay ON for every combo:
```
WB_CONT_HOLD_DIRECTION_CHECK=1
WB_MAX_LOSS_R_TIERED=1
WB_MAX_LOSS_TRIGGERS_COOLDOWN=1
WB_NO_REENTRY_ENABLED=1
WB_TW_MIN_PROFIT_R=1.5
```

---

## Phase 2: Run All 7 Combos

Run them sequentially. Each combo resumes from its own state file if interrupted.

**Suggested order** (most important first, in case we need to stop early):

```bash
# 1. MP only — the baseline everything else is measured against
python run_megatest.py mp_only

# 2. MP + SQ — current live config, need full-scale validation
python run_megatest.py mp_sq

# 3. All three — the "everything on" config we're building toward
python run_megatest.py all_three

# 4. SQ only — isolate squeeze's contribution
python run_megatest.py sq_only

# 5. MP + VR — see if VR adds anything to MP alone
python run_megatest.py mp_vr

# 6. VR only — raw VR data (may be 0 or near-0 trades, that's fine)
python run_megatest.py vr_only

# 7. SQ + VR — probably lowest priority
python run_megatest.py sq_vr
```

Each run will auto-fetch tick data from Alpaca for any stock/date not in the cache. This means the tick cache will grow significantly. **That's fine and expected** — the cached data will be useful for all future backtests.

---

## Phase 3: Report

Write report to `megatest_results/MEGATEST_SUMMARY.md` with:

### 3a. Strategy Comparison Table

| Combo | Total P&L | # Trades | Win Rate | Profit Factor | Max DD | Sharpe | Best Day | Worst Day |
|-------|-----------|----------|----------|---------------|--------|--------|----------|-----------|
| MP only | ? | ? | ? | ? | ? | ? | ? | ? |
| SQ only | ? | ? | ? | ? | ? | ? | ? | ? |
| VR only | ? | ? | ? | ? | ? | ? | ? | ? |
| MP + SQ | ? | ? | ? | ? | ? | ? | ? | ? |
| MP + VR | ? | ? | ? | ? | ? | ? | ? | ? |
| SQ + VR | ? | ? | ? | ? | ? | ? | ? | ? |
| All three | ? | ? | ? | ? | ? | ? | ? | ? |

### 3b. Interaction Analysis

For each strategy pair, calculate the **interaction effect**:
- `interaction(MP,SQ) = P&L(MP+SQ) - P&L(MP) - P&L(SQ)`
  - Positive = synergy (strategies complement each other)
  - Negative = interference (strategies hurt each other)
  - Zero = independent (strategies don't interact)

### 3c. Per-Strategy Trade Breakdown

Using `setup_type` tags from the trade output:
- How many trades did each strategy produce across all combos?
- Average P&L per trade by strategy type
- Win rate by strategy type
- Which stocks/dates did each strategy uniquely capture (trades the other strategies missed)?

### 3d. VR-Specific Analysis

Since VR is in early tuning:
- Total VR trades across all VR-enabled combos
- If VR trades > 0: list every VR trade with stock, date, entry, exit, P&L
- Which stocks triggered VR? Are they the expected VR-pattern stocks?
- If VR trades == 0: note this clearly — VR may need fundamental rethinking

### 3e. Equity Curves

For each combo, produce the daily equity data in CSV format:
`megatest_results/{combo_id}_daily.csv` with columns: date, day_pnl, equity, trades, wins, losses

### 3f. Period Breakdown

Split results into two periods to check for overfitting:
- **In-sample**: Jan 2026 - Mar 2026 (where our fixes were developed)
- **Out-of-sample**: Jan 2025 - Dec 2025 (true OOS, fixes never saw this data)

| Combo | IS P&L | IS Win% | OOS P&L | OOS Win% | OOS/IS Ratio |
|-------|--------|---------|---------|----------|-------------|

OOS/IS ratio > 0.5 = good generalization. < 0.3 = likely overfit.

---

## Phase 4: Commit and Push

```bash
git add run_megatest.py megatest_results/ DIRECTIVE_WEEKEND_MEGATEST.md
git commit -m "Megatest: 7 strategy combos × 297 days — weekend batch run

Results in megatest_results/. Strategy comparison, interaction analysis,
per-strategy breakdowns, equity curves, and IS/OOS validation.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin v6-dynamic-sizing
```

---

## Failure Handling

- If a combo crashes mid-run, it should resume from its state file on restart
- If Alpaca rate-limits tick fetches, add a 1-second delay between stocks or switch to cached-only mode (`--tick-cache tick_cache/ --cached-only` if that flag exists, or skip stocks not in cache)
- If a single stock sim times out (>5 min), skip it and log the skip
- **Do not rerun completed combos** — the state files track progress

---

## Expected Runtime

Rough estimate based on existing batch runner performance:
- ~297 dates × ~5 stocks/day × ~30 sec/sim = ~12.4 hours per combo
- 7 combos = ~87 hours total
- With caching speedup (ticks already cached for many dates): maybe ~50-60 hours
- Should finish by Monday morning if started Friday evening

**If running out of time**, priorities are:
1. `mp_only` (baseline)
2. `mp_sq` (current live config)
3. `all_three` (target config)
4. Everything else is bonus

---

*Directive by Cowork (Opus) — 2026-03-20*
