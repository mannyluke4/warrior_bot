# DIRECTIVE: Scanner RVOL Bug — Diagnose + Fix

**Author**: Cowork (Opus)
**Date**: 2026-03-25
**For**: CC (Sonnet)
**Priority**: P0 — This bug means ALL batch backtests are understated (megatest, OOS, Jan comparisons)

---

## Context

The morning live test (2026-03-25) revealed scanner_sim.py produces **0 candidates** for today while the live bot found 6 stocks. The live bot uses `stock_filter.py` (Alpaca snapshots) for RVOL; scanner_sim computes RVOL from historical bars. Both should produce similar results, but they don't.

**What Cowork already did:**
1. Added **diagnostic logging** to both PM candidates (Step 4a) and emerging movers (Step 4b) — every candidate now prints `pm_vol`, `ADV`, `RVOL` before the gate runs
2. Added **missing ADV backfill** — if emerging stocks aren't in the initial `avg_daily_vol` dict (from `get_all_active_symbols()`), fetch their ADV separately before computing RVOL
3. Both changes are in `scanner_sim.py`, syntax verified

**What we DON'T know yet:**
- The exact reason each stock failed the RVOL gate today (was ADV missing? Was RVOL legitimately < 2.0? Was the cumulative vol fetch failing?)
- Whether the missing-ADV backfill actually captures new stocks
- Whether this was a one-day API fluke or a systematic issue

---

## Step 0: Git Pull + Verify

```bash
cd /Users/mannyluke/warrior_bot
git pull
source venv/bin/activate
```

Verify the diagnostic logging is present:
```bash
grep "RESCAN.*pm_vol.*ADV.*RVOL" scanner_sim.py
# Should show the new diagnostic print line

grep "missing from initial lookup" scanner_sim.py
# Should show the ADV backfill block
```

Quick regression (scanner changes don't affect standalone sims, but verify anyway):
```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

---

## Step 1: Reproduce Today's Scanner (diagnostic run)

Run scanner_sim for today (2026-03-25) and capture the FULL output:

```bash
python scanner_sim.py 2026-03-25 2>&1 | tee /tmp/scanner_diag_0325.txt
```

**What to look for in the output:**
- `PM {SYMBOL}: pm_vol=X ADV=Y RVOL=Z` — shows why each PM candidate was filtered
- `RESCAN {SYMBOL}: pm_vol=X ADV=Y RVOL=Z` — shows why each rescan candidate was filtered
- `Fetching ADV for N emerging stocks missing from initial lookup` — were any stocks missing?
- `ADV lookup FAILED` — if so, those stocks are invisible to the scanner

**Record in the report:**
- How many PM candidates found and why each was filtered
- How many rescan candidates found and why each was filtered
- For the 6 stocks the live bot found (RBNE, FEED, MKDW, CVV, ANNA, CRCD): are they in the scanner output at all? If yes, what were their RVOL values?

---

## Step 2: Run Historical Date (known good)

Run a date we know produced results to verify the diagnostics don't break anything:

```bash
python scanner_sim.py 2026-01-30 2>&1 | tee /tmp/scanner_diag_0130.txt
```

Expected: should produce candidates (at minimum VIVS with RVOL ~9.77x). Verify the diagnostic logging works and RVOL values match the JSON output.

---

## Step 3: Analyze the Root Cause

Based on Step 1 output, determine which scenario is happening:

### Scenario A: ADV is missing (None)
- Stocks aren't in `avg_daily_vol` dict → RVOL = None → filtered
- **Fix**: The backfill code Cowork added should handle this. If it's working, report "Scenario A fixed by backfill"
- If backfill also fails, investigate WHY (stock not in Alpaca universe? < 3 days history?)

### Scenario B: ADV is too high (RVOL legitimately < 2.0)
- Stock has high normal volume, so even with strong premarket activity, RVOL stays low
- **This is correct behavior** — these aren't truly unusual-volume stocks
- However: the live bot may be computing RVOL differently (e.g., Alpaca's snapshot RVOL uses time-weighted comparison, not full-day average)
- Report the exact numbers so we can decide if the threshold needs adjusting

### Scenario C: Cumulative volume fetch is failing
- The try/except at lines 789-803 silently catches errors
- `pm_volume` stays at the small window-only value
- **Fix**: Check for "cumulative vol fetch error" messages in the output

### Scenario D: API non-determinism
- `get_all_active_symbols()` returns different universes on different days
- A stock active today might not have been returned by the API when fetching historical data
- **The ADV backfill should mitigate this** — report whether it does

---

## Step 4: Run Jan Comparison with Diagnostics

Run the Jan comparison to see how many stocks are being lost:

```bash
python run_jan_v1_comparison.py 2>&1 | tee /tmp/jan_v1_rvol_diag.txt
```

**Key question**: How many rescan candidates are found vs filtered? This tells us the magnitude of the batch backtest understatement.

Compare to previous Jan comparison result (should be in `jan_comparison_v1_state.json`). If the ADV backfill captures new stocks, P&L should increase.

---

## Step 5: Report

Write report to `cowork_reports/2026-03-25_scanner_rvol_investigation.md`:

1. **Today's diagnostic run** — full breakdown of every candidate, their pm_vol/ADV/RVOL, why they passed or failed
2. **Which scenario** (A/B/C/D or combination) explains the 0-stock result
3. **ADV backfill impact** — did the new code capture stocks that were previously invisible?
4. **Jan comparison delta** — did P&L change with the diagnostic build?
5. **Recommendation** — what further fix is needed (if any) beyond the diagnostics + backfill already added

---

## Step 6: Git Push

```bash
git add scanner_sim.py cowork_reports/2026-03-25_scanner_rvol_investigation.md
git commit -m "Scanner RVOL investigation: diagnostic logging + ADV backfill for emerging stocks

P0 bug from morning live test — scanner_sim produces 0 candidates while
live bot found 6 stocks. Added per-candidate RVOL diagnostics and ADV
backfill for stocks missing from the initial avg_daily_vol dict.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main
```

---

## Important Notes

- Do NOT change RVOL thresholds or filter logic yet — we need the diagnostic data first
- The scanner_sim changes are diagnostic + backfill only — they don't change filter behavior for stocks that already had ADV
- Standalone regressions (VERO, ROLR) are unaffected — they don't use the scanner
- If Step 1 shows the backfill captures new stocks, that's already a partial fix
- The REAL fix may require adjusting how RVOL is computed for premarket hours (time-weighted vs full-day average), but we need data first
