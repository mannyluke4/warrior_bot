# DIRECTIVE: Re-run scanner_sim for January 2026 with Scanner Fixes V1

**Author**: Cowork (Opus)
**Date**: 2026-03-23
**For**: CC (Sonnet)
**Priority**: HIGH — Jan comparison V1/V2 results used STALE Jan 2026 scanner data

---

## Problem

The Jan 2025 vs Jan 2026 comparison backtests (V1 and V2) ran on **stale scanner data for Jan 2026**. Evidence:

- All 21 `scanner_results/2026-01-*.json` files dated **Mar 22 18:13** (yesterday)
- Scanner Fixes V1 committed at **Mar 23 15:18** (today) — commit `6a91afe`
- Jan 2025 JSONs WERE regenerated (timestamps 15:57-16:44) — Jan 2026 was NOT
- Jan 2026 JSONs still contain `"profile": "X"` (old name, not `"unknown"`)
- 6 stocks have `float_shares: null` that EDGAR/AlphaVantage should attempt to resolve:
  - SYPR (Jan 15), GIBO (Jan 23), MAAS (Jan 23), GXAI (Jan 26), NETG (Jan 27), DZZ (Jan 29)
- Rescan fix (cumulative 4AM→checkpoint volume) was never applied to Jan 2026

Jan 2025 re-run showed REAL changes: AMOD resolved from `profile=X, float=None` to `profile=B, float=8.08M`. ZEO dropped out. 4 new stocks appeared. 9 of 21 files changed. **We need the same treatment for Jan 2026.**

---

## Step 1: Back Up Existing Jan 2026 Scanner Results

```bash
source venv/bin/activate
mkdir -p scanner_results/backup_2026_01_pre_v1
cp scanner_results/2026-01-*.json scanner_results/backup_2026_01_pre_v1/
```

---

## Step 2: Clear Float Cache None Entries

The cache invalidation fix clears Nones on load, but force a clean state:

```bash
python3 -c "
import json
with open('float_cache.json') as f:
    cache = json.load(f)
before = len(cache)
cleaned = {k: v for k, v in cache.items() if v is not None}
dropped = before - len(cleaned)
with open('float_cache.json', 'w') as f:
    json.dump(cleaned, f, indent=2)
print(f'Cleared {dropped} stale None entries from float_cache.json')
"
```

---

## Step 3: Re-run scanner_sim for All Jan 2026 Dates

**DO NOT SKIP THIS STEP.** The comparison runner reads pre-existing JSONs — it does not call scanner_sim. You must regenerate the JSONs first.

```bash
for date in 2026-01-02 2026-01-03 2026-01-05 2026-01-06 2026-01-07 2026-01-08 2026-01-09 2026-01-12 2026-01-13 2026-01-14 2026-01-15 2026-01-16 2026-01-20 2026-01-21 2026-01-22 2026-01-23 2026-01-26 2026-01-27 2026-01-28 2026-01-29 2026-01-30; do
    echo "=== $date ==="
    python scanner_sim.py $date
done
```

---

## Step 4: Diff Old vs New Scanner Results

```bash
python3 -c "
import json, os

backup_dir = 'scanner_results/backup_2026_01_pre_v1'
current_dir = 'scanner_results'
total_new = 0
total_removed = 0
total_float_resolved = 0

for d in range(1, 32):
    fname = f'2026-01-{d:02d}.json'
    old_path = os.path.join(backup_dir, fname)
    new_path = os.path.join(current_dir, fname)

    if not os.path.exists(old_path) or not os.path.exists(new_path):
        continue

    with open(old_path) as f:
        old = json.load(f)
    with open(new_path) as f:
        new = json.load(f)

    old_syms = {c['symbol'] for c in old}
    new_syms = {c['symbol'] for c in new}
    added = new_syms - old_syms
    removed = old_syms - new_syms
    total_new += len(added)
    total_removed += len(removed)

    # Check float resolution
    old_nulls = {c['symbol'] for c in old if c.get('float_shares') is None}
    new_nulls = {c['symbol'] for c in new if c.get('float_shares') is None}
    resolved = old_nulls - new_nulls
    total_float_resolved += len(resolved)

    # Check profile rename
    old_x = {c['symbol'] for c in old if c.get('profile') == 'X'}
    new_x = {c['symbol'] for c in new if c.get('profile') == 'X'}

    changes = []
    if added: changes.append(f'+{added}')
    if removed: changes.append(f'-{removed}')
    if resolved: changes.append(f'float resolved: {resolved}')
    if old_x and not new_x: changes.append(f'profile X migrated: {old_x}')
    elif new_x: changes.append(f'STILL profile X: {new_x}')

    if changes:
        print(f'{fname}: {\" | \".join(changes)}')
    else:
        print(f'{fname}: no change')

print(f'')
print(f'TOTALS: +{total_new} new stocks, -{total_removed} removed, {total_float_resolved} floats resolved')
"
```

**Save the diff output** — this is the proof of what the scanner fixes actually unlocked for Jan 2026.

---

## Step 5: Re-run Both Comparison Backtests

The Jan 2026 state from V1 and V2 is now invalid (ran on stale scanner data). Wipe and re-run.

### V1 (no Ross exit):

```bash
# Wipe V1 state — Jan 2025 is fine (used fresh data), but Jan 2026 needs re-run
# Since both months share one state file, we need to wipe and re-run everything
rm -f jan_comparison_v1_state.json
python run_jan_v1_comparison.py 2>&1 | tee jan_comparison_v1_output.txt
```

### V2 (Ross exit ON):

```bash
rm -f jan_comparison_v2_state.json
python run_jan_v2_comparison.py 2>&1 | tee jan_comparison_v2_output.txt
```

**IMPORTANT:** V1 must complete before V2 starts (V2 report reads V1 results for comparison).

---

## Step 6: Regression Check

After scanner re-run, verify regressions still pass:

```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

These are standalone simulate.py runs — NOT affected by scanner_results/ JSONs. They should still pass, but verify for safety.

---

## Step 7: Commit and Push

```bash
git add scanner_results/2026-01-*.json scanner_results/backup_2026_01_pre_v1/ jan_comparison_v1_state.json jan_comparison_v1_output.txt jan_comparison_v2_state.json jan_comparison_v2_output.txt cowork_reports/2026-03-23_jan_comparison_v1.md cowork_reports/2026-03-23_jan_comparison_v2.md
git commit -m "$(cat <<'EOF'
Re-run Jan 2026 scanner + comparison backtests with scanner fixes applied

Jan 2026 scanner_results/ JSONs were stale (Mar 22, pre-scanner-fixes).
Re-ran scanner_sim for all 21 Jan 2026 dates with: EDGAR/AlphaVantage
float fallbacks, cache invalidation, rescan fix, Profile X→unknown rename.
Re-ran V1 (no Ross exit) and V2 (Ross exit ON) comparison backtests on
fresh scanner data.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## What We're Looking For

1. **Did EDGAR/AlphaVantage resolve any of the 6 null-float stocks?** (SYPR, GIBO, MAAS, GXAI, NETG, DZZ)
2. **Did the rescan fix surface new candidates?** The Jan 2025 re-run found 0 new rescan candidates, but Jan 2026 might be different.
3. **Do the V1/V2 comparison numbers change?** If new candidates appear and produce trades, both V1 and V2 P&L will shift.
4. **Does the Ross exit A/B delta change?** This is the central question — the V1 vs V2 comparison may look different with fresh scanner data.

This is a data integrity fix. The comparison backtests are only meaningful if both months use scanner data generated by the same code version.
