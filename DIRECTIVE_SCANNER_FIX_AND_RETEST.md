# Directive: Scanner Bug Fixes, Filter Tuning, and Full Retest

**Priority**: HIGH — complete all phases before next trading day
**Risk**: MEDIUM — Phase 1 changes scanner_sim logic, Phases 2-3 are config-only
**Replaces**: DIRECTIVE_LIVE_CHECKPOINT_TIMING.md (all tasks absorbed here)

## Overview

Three categories of work, executed in strict phases with verification gates between each:

1. **Bug fix**: Cumulative window fix in `find_emerging_movers()` (ROLR disappearance)
2. **Filter investigation**: Debug why MNTS and SMX are missed, loosen filters if needed
3. **Config parity**: bot.py checkpoints, live_scanner.py timing, stock_filter.py + batch runner float cap
4. **Full rescan + backtest**: After all fixes verified

**CRITICAL**: Each phase has a verification step. Do NOT proceed to the next phase until verification passes.

---

## Phase 1: Fix Cumulative Window Bug (ROLR)

**Problem**: `find_emerging_movers()` in `scanner_sim.py` (line ~559-617) uses incremental windows (`prev_checkpoint → checkpoint`) to fetch bars. The narrower 15-minute windows from the new checkpoint schedule miss stocks that gap and halt within a single window. ROLR (2026-01-14, 288% gap, 3.6M float, 59x RVOL) disappeared from scanner results despite being a regression stock (+$6,444 standalone).

**Root cause**: Line 565-568 computes `win_start` from the previous checkpoint. For the 08:30 checkpoint, the window is 08:15-08:30. ROLR's news broke at 08:18, it halted quickly — if few/no bars exist in the narrow window, the stock is invisible to that checkpoint.

**Fix**: Change `win_start` in `find_emerging_movers()` to always use 4:00 AM ET (cumulative from session open). This matches how `resolve_precise_discovery()` already works (line 639-640: `hour=4, minute=0`).

**File**: `scanner_sim.py`, inside `find_emerging_movers()`, lines ~565-568

**Current code** (lines 565-568):
```python
        win_start = ET.localize(datetime.combine(
            date.date(), datetime.min.time().replace(hour=win_start_h, minute=win_start_m)))
        win_end = ET.localize(datetime.combine(
            date.date(), datetime.min.time().replace(hour=win_end_h, minute=win_end_m)))
```

**Replace `win_start` computation with**:
```python
        # CUMULATIVE window: always start from 4 AM to catch stocks that
        # gapped and halted within a narrow checkpoint slice.
        # Each checkpoint still only adds NEW stocks (found_symbols skip set),
        # so there's no double-counting.
        win_start = ET.localize(datetime.combine(
            date.date(), datetime.min.time().replace(hour=4, minute=0)))
        win_end = ET.localize(datetime.combine(
            date.date(), datetime.min.time().replace(hour=win_end_h, minute=win_end_m)))
```

**Also update** the `_build_checkpoint_windows` function (line 523-531) — the `prev_h, prev_m` fields are now unused for the bar fetch, but keep the function signature intact for backwards compatibility. Add a comment:
```python
def _build_checkpoint_windows(checkpoints):
    """Build (label, prev_h, prev_m, h, m) windows from checkpoint list.

    Note: prev_h/prev_m are retained for reference but find_emerging_movers()
    now uses cumulative windows (4AM → checkpoint) instead of incremental.
    """
```

**Also update** the docstring at line 540-546 to mention cumulative windows.

**Also fix** the cosmetic bug on line 822: change `"float {float_shares/1e6:.1f}M → skip (>10M)"` to `"skip (>15M)"`.

### Phase 1 Verification

Run scanner for ONLY 2026-01-14:
```bash
source venv/bin/activate
python scanner_sim.py --date 2026-01-14
```

**Check**: `cat scanner_results/2026-01-14.json | python -c "import json,sys; [print(s['symbol'],s['gap_pct']) for s in json.load(sys.stdin)]"`

**Expected**: ROLR appears with ~288% gap. Other stocks (BEEM, FEED, MVO, CMND) should still be present.

**Then run standalone regression**:
```bash
WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```
**Expected**: +$6,444

**DO NOT PROCEED TO PHASE 2 UNTIL ROLR IS CONFIRMED IN SCANNER AND REGRESSION PASSES.**

---

## Phase 2: Debug MNTS and SMX Filter Blockers

**Context**: Two high-value WT stocks with low float that our scanner misses:
- **MNTS** (Feb 6 & Feb 9): +$6,148 P&L in WT comparison. Float = 1.3M (passes filter).
- **SMX** (Feb 9 & Feb 10): +$1,962 P&L in WT comparison. Float = micro (passes filter).

Both pass the float filter, so they must be blocked by gap%, RVOL, PM volume, or price. We need to diagnose before deciding whether to loosen anything.

### Step 2a: Diagnostic scan

Run scanner_sim with debug output for these dates:
```bash
python scanner_sim.py --date 2026-02-06 2>&1 | tee /tmp/mnts_feb06_debug.txt
python scanner_sim.py --date 2026-02-09 2>&1 | tee /tmp/mnts_feb09_debug.txt
python scanner_sim.py --date 2026-02-10 2>&1 | tee /tmp/smx_feb10_debug.txt
```

Check if MNTS/SMX appear anywhere in the output:
```bash
grep -i "MNTS" /tmp/mnts_feb06_debug.txt /tmp/mnts_feb09_debug.txt
grep -i "SMX" /tmp/mnts_feb09_debug.txt /tmp/smx_feb10_debug.txt
```

If they don't appear at all, they failed the gap check (gap < 10%) or price check ($2-$20). Add temporary debug prints:

In `compute_gap_candidates()` — wherever the gap/price filter is — add:
```python
if sym in ('MNTS', 'SMX'):
    print(f"  DEBUG {sym}: prev_close={pc}, pm_price={latest_price}, gap={gap_pct:.1f}%, vol={vol}")
```

In `find_emerging_movers()` at line ~591, add:
```python
if sym in ('MNTS', 'SMX'):
    print(f"  DEBUG {sym} rescan {label}: latest={latest_price}, gap={gap_pct:.1f}%")
```

### Step 2b: Evaluate findings

After diagnosis, one of these scenarios:

**Scenario A — gap < 10%**: These stocks are session runners (price runs DURING session, not gapping big premarket). Lowering the gap% threshold is risky — it adds a LOT of noise. **Do NOT lower gap% below 10%.** Instead, document the finding and move on. These stocks require a different detection mechanism (intraday momentum scanner), which is a future project.

**Scenario B — RVOL < 2.0 or PM volume < 50K**: These are early session stocks where volume hasn't built yet at scan time. This is more fixable:
- If RVOL is the blocker: Consider lowering `MIN_RVOL` from 2.0 to 1.5 for rescan checkpoints only (not premarket). Gate it with `WB_RESCAN_MIN_RVOL` env var, default 2.0.
- If PM volume is the blocker: Consider lowering `MIN_PM_VOLUME` from 50K to 25K for rescan checkpoints only. Gate with `WB_RESCAN_MIN_PM_VOL` env var, default 50000.

**Scenario C — price > $20**: Document and move on. We don't trade stocks above $20.

### Step 2c: Apply fix (if Scenario B)

If a filter change is warranted, implement it with an env var gate (OFF by default):
```python
# In run_scanner() where RVOL/PM gates are applied to emerging movers (line ~798-800):
rescan_min_rvol = float(os.getenv("WB_RESCAN_MIN_RVOL", os.getenv("WB_MIN_REL_VOLUME", "2.0")))
rescan_min_pm_vol = int(os.getenv("WB_RESCAN_MIN_PM_VOL", os.getenv("WB_MIN_PM_VOLUME", "50000")))
emerging = [c for c in emerging
            if (c.get("relative_volume") or 0) >= rescan_min_rvol
            and (c.get("pm_volume") or 0) >= rescan_min_pm_vol]
```

### Phase 2 Verification

If a filter change was applied, rescan ONLY the affected dates:
```bash
python scanner_sim.py --date 2026-02-06
python scanner_sim.py --date 2026-02-09
python scanner_sim.py --date 2026-02-10
```

**Check**: Do MNTS and/or SMX now appear in the scanner results?
```bash
for d in 2026-02-06 2026-02-09 2026-02-10; do echo "=== $d ==="; cat scanner_results/$d.json | python -c "import json,sys; [print(s['symbol']) for s in json.load(sys.stdin)]"; done
```

If Scenario A (gap < 10%), skip verification — just document the finding and proceed.

**Remove all temporary debug prints before proceeding.**

**DO NOT PROCEED TO PHASE 3 UNTIL PHASE 2 IS COMPLETE (diagnosed, fixed if applicable, verified).**

---

## Phase 3: Config Parity Fixes

These are config-only changes that don't affect scanner_sim.py results but keep the live bot aligned.

### Task 3a: Update bot.py rescan checkpoints

**File**: `bot.py`, line ~673-675

Replace:
```python
RESCAN_CHECKPOINTS_ET = [
    (7, 30), (8, 0), (8, 30), (9, 0), (9, 30), (10, 0), (10, 30),
]
```

With:
```python
RESCAN_CHECKPOINTS_ET = [
    (7, 0), (7, 15), (7, 30), (7, 45),
    (8, 0), (8, 15), (8, 30), (8, 45),
    (9, 0), (9, 15), (9, 30),
]
```

Update the comment and docstring to say "11 data-driven checkpoints" (matching scanner_sim.py `_CUSTOM_CHECKPOINTS`).

### Task 3b: Update live_scanner.py timing

**File**: `live_scanner.py`, `run()` method (line ~627+)

1. Change write interval from 5 minutes to 1 minute (60s instead of 300s)
2. Add 9:30 AM ET new-symbol cutoff: after 9:30, don't add new symbols to watchlist
3. Change end time from 11:00 AM to 9:30 AM (or 9:31 to allow the final 9:30 write)

### Task 3c: Fix stock_filter.py MAX_FLOAT default

**File**: `stock_filter.py`

Change the MAX_FLOAT default from `"10"` to `"15"`:
```python
MAX_FLOAT = float(os.getenv("WB_MAX_FLOAT", "15"))  # was "10"
```

### Task 3d: Fix run_jan_v1_comparison.py float cap

**File**: `run_jan_v1_comparison.py`, line 39

Change:
```python
MAX_FLOAT_MILLIONS = 10
```

To:
```python
MAX_FLOAT_MILLIONS = float(os.getenv("WB_MAX_FLOAT", "15"))
```

This ensures the batch runner respects the same float cap as scanner_sim.py and .env. Without this fix, stocks like OM (13.1M float) pass the scanner but get filtered by the batch runner.

### Phase 3 Verification

```bash
grep -n "RESCAN_CHECKPOINTS" bot.py
grep -n "MAX_FLOAT" stock_filter.py
grep -n "MAX_FLOAT_MILLIONS" run_jan_v1_comparison.py
grep -n "11:00\|interval\|sleep.*300" live_scanner.py
```

Confirm:
- bot.py: 11 checkpoints, last is (9, 30), no (10, 0) or (10, 30)
- stock_filter.py: default "15"
- run_jan_v1_comparison.py: reads from env or defaults to 15
- live_scanner.py: no 11:00 references, 60s interval

---

## Phase 4: Full Rescan

After all fixes are verified, rescan ALL dates for both months.

### Backup existing results first:
```bash
# Backup Jan 2025
mkdir -p scanner_results/backup_jan2025_pre_phase4
cp scanner_results/2025-01-*.json scanner_results/backup_jan2025_pre_phase4/ 2>/dev/null

# Backup Jan 2026
mkdir -p scanner_results/backup_jan2026_pre_phase4
cp scanner_results/2026-01-*.json scanner_results/backup_jan2026_pre_phase4/ 2>/dev/null
```

### Run batch scan:
```bash
# Jan 2025 (21 dates)
for d in 2025-01-02 2025-01-03 2025-01-06 2025-01-07 2025-01-08 2025-01-09 2025-01-10 2025-01-13 2025-01-14 2025-01-15 2025-01-16 2025-01-17 2025-01-21 2025-01-22 2025-01-23 2025-01-24 2025-01-27 2025-01-28 2025-01-29 2025-01-30 2025-01-31; do
    echo "=== Scanning $d ==="
    python scanner_sim.py --date $d
done

# Jan 2026 (21 dates)
for d in 2026-01-02 2026-01-03 2026-01-05 2026-01-06 2026-01-07 2026-01-08 2026-01-09 2026-01-12 2026-01-13 2026-01-14 2026-01-15 2026-01-16 2026-01-20 2026-01-21 2026-01-22 2026-01-23 2026-01-26 2026-01-27 2026-01-28 2026-01-29 2026-01-30; do
    echo "=== Scanning $d ==="
    python scanner_sim.py --date $d
done
```

### Phase 4 Verification

Quick sanity check — ROLR must be in Jan 14:
```bash
cat scanner_results/2026-01-14.json | python -c "import json,sys; syms=[s['symbol'] for s in json.load(sys.stdin)]; print('ROLR present:', 'ROLR' in syms); print('All:', syms)"
```

Print a summary table of stock counts per date:
```bash
for f in scanner_results/2025-01-*.json scanner_results/2026-01-*.json; do
    d=$(basename $f .json)
    n=$(python -c "import json; print(len(json.load(open('$f'))))")
    echo "$d: $n stocks"
done
```

---

## Phase 5: Full Month Backtests

### Important: Delete stale state file first
The old `jan_comparison_v1_state.json` has cached results from the previous scanner. Delete it to force a clean run:

```bash
rm -f jan_comparison_v1_state.json
```

### Run the comparison:
```bash
source venv/bin/activate
python run_jan_v1_comparison.py 2>&1 | tee jan_comparison_v1_output.txt
```

This runs BOTH Jan 2025 (21 dates) and Jan 2026 (21 dates) with the new scanner results.

### Phase 5 Verification

Check the output summary table at the end. Key metrics to report:

1. **Jan 2025**: Total P&L, trade count, win rate
2. **Jan 2026**: Total P&L, trade count, win rate
3. **VERO 2026-01-16**: Should still be the monster trade (~+$14K)
4. **ROLR 2026-01-14**: Should now appear with trades (was missing before)
5. **Any new stocks**: Note which stocks are new vs the previous run

Compare against previous results:
- Previous Jan 2025: 32 trades, +$3,423, 40.6% WR
- Previous Jan 2026: 17 trades, +$16,409, 41.2% WR

---

## Phase 6: Regression

Final sanity check — standalone regression must still pass:

```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

---

## Git

After all phases pass:
```bash
git add -A
git commit -m "Scanner fixes: cumulative window, filter tuning, config parity

Phase 1: Changed find_emerging_movers() to use cumulative windows (4AM→checkpoint)
  instead of incremental windows — fixes ROLR disappearance and other halt-gap stocks.
Phase 2: [FILL IN — what was found for MNTS/SMX, what was changed if anything]
Phase 3: bot.py 11 checkpoints, live_scanner.py 1min/9:30 cutoff, stock_filter + batch
  runner float cap aligned to 15M from .env.
Phase 4-5: Full rescan and month backtests with new scanner.

Jan 2025: [FILL IN P&L] | Jan 2026: [FILL IN P&L]
Regression: VERO +\$18,583 ✓ | ROLR +\$6,444 ✓

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

git push origin main
```

---

## Quick Reference: What Changed and Why

| Change | File | Why |
|--------|------|-----|
| Cumulative window (4AM→checkpoint) | scanner_sim.py | ROLR and other halt-gap stocks invisible in narrow windows |
| MNTS/SMX filter debug | scanner_sim.py | +$8,110 P&L sitting on table — need diagnosis first |
| bot.py 11 checkpoints | bot.py | Match scanner_sim, remove negative-EV post-9:30 rescans |
| live_scanner.py 1-min writes + 9:30 cutoff | live_scanner.py | Faster detection, stop adding late stocks |
| stock_filter.py default 15M | stock_filter.py | Match .env (cosmetic — .env overrides at runtime) |
| run_jan_v1_comparison.py float cap 15M | run_jan_v1_comparison.py | Was hardcoded to 10M — filtered out OM (13.1M, +$2,911) |

## Context Notes for CC

- **BCTX (+$9,552) is NOT missing** — it's in our scanner on Jan 13 (80.76% gap, 1.7M float, disc 07:40). The WT list showed it on Jan 16/27 which are continuation days, not gap days.
- **OM (+$2,911) is NOW in our scanner** after the 15M float cap raise. But the batch runner at 10M was filtering it back out — Task 3d fixes that.
- The `_CUSTOM_CHECKPOINTS` list in scanner_sim.py has 11 entries (not 12 — there's no 08:10). Bot.py should match: 11 checkpoints.
- Phase 2 is intentionally investigative — don't pre-commit to a filter change. If MNTS/SMX fail because gap < 10% (session runners, not gappers), the correct answer is "leave filters alone" and document.
