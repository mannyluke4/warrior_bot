# Directive: Scanner Fixes V1 — Unknown-Float Trading + Rescan Fix + Terminology Cleanup

**Date:** 2026-03-23
**From:** Cowork (Opus)
**To:** CC (Sonnet)
**Priority:** HIGH — #1 project priority (scanner coverage)

---

## Context

The January 2025 missed stocks backtest proved the scanner is our #1 bottleneck: +$42,818 potential vs $5,543 actual (7.7x multiplier). This directive addresses the two most immediately actionable scanner fixes, plus a terminology cleanup that Manny explicitly requested.

**Reports to read first:**
- `cowork_reports/2026-03-23_scanner_gap_analysis.md` — Full gap analysis
- `cowork_reports/2025-01_missed_stocks_backtest_results.md` — Backtest results

---

## Item 1: Enable Unknown-Float Stock Trading

### What
Flip the existing gate ON so the bot can trade stocks where float data is unavailable but all other signals are strong. This was previously called "Profile X" — see Item 3 for the rename.

### Why
GDTC (+$4,393 bot P&L, +93.6% gap, 94x RVOL) and AMOD (+$3,642 bot P&L, +79.9% gap, 42x RVOL) were **already found by the scanner** but couldn't trade because the gate was OFF. Combined: +$8,035 from a config change.

### Steps

1. **In `.env`**, change:
   ```
   WB_ALLOW_PROFILE_X=0
   ```
   to (after Item 3 rename):
   ```
   WB_ALLOW_UNKNOWN_FLOAT=1
   ```
   Keep the existing safety thresholds — they're already conservative:
   - gap ≥ 50%
   - pm_vol ≥ 1,000,000
   - rvol ≥ 10x
   - 50% notional cap

2. **Validation backtest:** Run the January 2025 missed stocks backtest (or the full YTD megatest) with unknown-float trading ON. Verify GDTC and AMOD produce positive results. Check that no new garbage stocks slip through.

3. **Update `run_ytd_v2_backtest.py`** to respect the unknown-float gate (currently line 142 hard-skips `profile == "X"` with no gate check). It should match the `run_megatest.py` logic (lines 174-186) that checks the env var and applies the safety thresholds.

### Acceptance Criteria
- GDTC Jan 6 produces trades with positive P&L
- AMOD Jan 30 produces trades with positive P&L
- VERO regression still passes (+$18,583 with `WB_MP_ENABLED=1`)
- No new trades on junk stocks (check that safety gates filter effectively)

---

## Item 2: Fix Continuous Rescan in scanner_sim.py

### What
The `find_emerging_movers()` function in scanner_sim.py found **zero** stocks via rescan across ALL of January 2025 (66 total candidates, 0 via "rescan" method, all via "premarket" or "precise"). This means the continuous rescan system is not working.

### Why
Stocks like ZENA (news at 7:30 AM, 8M float, +$1,865 bot P&L), SGN (3.7M float, +$1,625 bot P&L), and NEHC (+$839 bot P&L) had valid fundamentals but weren't found by the 7:15 AM premarket scan. They should have been caught by the continuous rescan at 8:00, 8:30, 9:00, or 9:30 AM checkpoints.

### Diagnosis

The `find_emerging_movers()` function (lines 425-508) fetches 30-minute bar windows at each checkpoint. The issue is likely one or more of these:

1. **RVOL/PM volume gates applied to rescan candidates** (lines 651-654): The rescan candidates get the same RVOL ≥ 2.0 and PM vol ≥ 50K gates applied, but their "pm_volume" is calculated from only the 30-minute window — not cumulative from 4 AM. A stock that's been building volume all morning won't get credit for earlier volume in the rescan.

2. **`avg_daily_vol` may be zero for rescan candidates**: If a stock wasn't in the initial `fetch_avg_daily_volume()` universe (because it had no prior-day close data), RVOL can't be calculated.

3. **Gap threshold still 10% at rescan**: Some stocks start the day flat and develop momentum after open. The 10% gap requirement may be too high for intraday movers found via rescan.

4. **`existing_candidates` parameter**: `find_emerging_movers()` receives the premarket candidates list and skips those symbols. But `resolve_precise_discovery()` runs AFTER the rescan (line 661), and it re-timestamps candidates. There may be an ordering issue where precise discovery is stealing candidates that would have been rescan candidates.

### Steps

1. **Debug**: Add logging to `find_emerging_movers()` to show:
   - How many symbols are checked at each checkpoint
   - How many pass the gap/price filter
   - How many get rejected by RVOL/PM vol gates
   - Which specific symbols were close but missed

2. **Fix cumulative volume**: Change rescan volume calculation to use cumulative volume from 4 AM to checkpoint time, not just the 30-minute window volume. This means fetching bars from `4:00 AM to checkpoint_time` for new candidates (or at minimum, from the start of the day's activity).

3. **Fix RVOL calculation**: Ensure `avg_daily_vol` is available for ALL active symbols checked in the rescan, not just the ones that had premarket bars.

4. **Consider lowering rescan gap threshold**: For the rescan specifically (not the initial premarket scan), consider accepting stocks at ≥ 5% gap if they have very high RVOL (≥ 10x) and strong PM volume (≥ 200K). This would catch momentum/continuation plays that don't have a massive premarket gap.

5. **Validation**: Re-run scanner_sim for January 2025 and verify:
   - Rescan now finds ≥ 5 new candidates across the month
   - ZENA (Jan 7, 7:30 AM), SGN (Jan 29/31), NEHC (Jan 22) appear in results
   - No regression on existing premarket candidates

### Acceptance Criteria
- `find_emerging_movers()` returns > 0 candidates for at least 5 days in January 2025
- ZENA appears as a candidate on Jan 7
- VERO regression still passes (+$18,583 with `WB_MP_ENABLED=1`)

---

## Item 3: Rename "Profile X" to "Unknown Float" Everywhere

### What
Remove ALL references to "Profile X" in the codebase. Replace with "unknown float" or "unknown-float" as appropriate. This is a terminology cleanup that Manny explicitly requested — the term causes confusion.

### Why
"Profile X" sounds like a special trading profile. It's not. It just means "we don't have float data for this stock." The new name should be self-explanatory.

### Rename Map

**Environment variables (.env):**
```
OLD: WB_ALLOW_PROFILE_X=0   # Allow unknown-float (Profile X) stocks...
NEW: WB_ALLOW_UNKNOWN_FLOAT=1   # Allow stocks with unknown float if gap>=50%, pm_vol>=1M, rvol>=10x (50% notional cap)
```

**Python constants (run_megatest.py, lines 34-39):**
```python
# OLD:
ALLOW_PROFILE_X = int(os.environ.get("WB_ALLOW_PROFILE_X", "0")) == 1
PROFILE_X_MIN_GAP = 50.0
PROFILE_X_MIN_PM_VOL = 1_000_000
PROFILE_X_MIN_RVOL = 10.0
PROFILE_X_NOTIONAL_FACTOR = 0.5

# NEW:
ALLOW_UNKNOWN_FLOAT = int(os.environ.get("WB_ALLOW_UNKNOWN_FLOAT", "0")) == 1
UNKNOWN_FLOAT_MIN_GAP = 50.0
UNKNOWN_FLOAT_MIN_PM_VOL = 1_000_000
UNKNOWN_FLOAT_MIN_RVOL = 10.0
UNKNOWN_FLOAT_NOTIONAL_FACTOR = 0.5
```

**Profile classification (scanner_sim.py, line 160-170):**
```python
# OLD:
def classify_profile(float_shares: float | None) -> str:
    """Classify stock by float: A (<5M), B (5-10M), X (>10M or unknown)."""
    if float_shares is None:
        return "X"

# NEW:
def classify_profile(float_shares: float | None) -> str:
    """Classify stock by float: A (<5M), B (5-10M), unknown (no data)."""
    if float_shares is None:
        return "unknown"
```

**All code comparisons — change `"X"` to `"unknown"`:**

Active files to change (NOT archive/ or .claude/worktrees/):

| File | Line(s) | Change |
|------|---------|--------|
| `scanner_sim.py` | 163 | `return "X"` → `return "unknown"` |
| `run_megatest.py` | 34-39 | Constants renamed (see above) |
| `run_megatest.py` | 175 | `profile == "X"` → `profile == "unknown"` |
| `run_megatest.py` | 176 | `ALLOW_PROFILE_X` → `ALLOW_UNKNOWN_FLOAT` |
| `run_megatest.py` | 184 | `"_profile_x"` → `"_unknown_float"` |
| `run_megatest.py` | 484-487 | Comment + `"_profile_x"` → `"_unknown_float"`, constant rename |
| `run_ytd_v2_backtest.py` | 142 | `profile == "X"` → `profile == "unknown"` (+ add gate logic from Item 1) |
| `run_ytd_v2_profile_backtest.py` | 155 | `profile == "X"` → `profile == "unknown"` |
| `run_oos_2025q4_backtest.py` | 148 | `profile == "X"` → `profile == "unknown"` |
| `run_jan_compare.py` | 85, 125 | `"WB_ALLOW_PROFILE_X"` → `"WB_ALLOW_UNKNOWN_FLOAT"`, `profile == "X"` → `profile == "unknown"` |
| `run_jan_comparison.py` | 39, 51 | `"WB_ALLOW_PROFILE_X"` → `"WB_ALLOW_UNKNOWN_FLOAT"` |
| `cache_tick_data.py` | 100, 105 | `profile == "X"` → `profile == "unknown"` |
| `.env` | line 78 | Full line replacement (see above) |

**Documentation files to update:**

| File | What to Change |
|------|---------------|
| `CLAUDE.md` | Replace "Profile X" with "unknown-float" in all mentions |
| `COWORK_HANDOFF.md` | Replace "Profile X" with "unknown-float" in scanner miss categories and config sections |
| `MASTER_TODO.md` | Replace "Profile X" with "unknown-float" |

**DO NOT touch:**
- `archive/` directory (historical, leave as-is)
- `.claude/worktrees/` (transient, will be cleaned up)
- `scanner_results/*.json` (historical data — old JSONs will have `"profile": "X"`, new ones will have `"profile": "unknown"`)
- `cowork_reports/` (historical analysis — leave as-is, the reports describe what existed at the time)

**Backward compatibility:** Since old scanner JSON files contain `"profile": "X"`, all code that checks for unknown-float must check for BOTH values during the transition:
```python
if profile in ("X", "unknown") or float_m is None or float_m == 0:
```
This ensures old cached scanner results still work. Add a comment: `# "X" is legacy name for unknown-float, kept for backward compat with old scanner JSONs`

### Acceptance Criteria
- `grep -r "Profile X" *.py *.md .env` returns zero hits (excluding archive/, .claude/worktrees/, cowork_reports/)
- `grep -r "PROFILE_X" *.py .env` returns zero hits (excluding archive/, .claude/worktrees/)
- All backtests produce identical results before and after rename
- VERO regression still passes (+$18,583 with `WB_MP_ENABLED=1`)

---

## Execution Order

1. **Item 3 first** (rename) — pure refactor, no behavior change. Commit.
2. **Item 1 second** (enable unknown-float) — config + code change in `run_ytd_v2_backtest.py`. Commit.
3. **Item 2 third** (rescan fix) — debugging + code change in `scanner_sim.py`. Commit.
4. **Run regression** after all three: VERO +$18,583 (with `WB_MP_ENABLED=1`).
5. **Push to origin main.**

---

## Regression

After all changes:
```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

---

*Directive created 2026-03-23 by Cowork (Opus). Reference: cowork_reports/2026-03-23_scanner_gap_analysis.md*
