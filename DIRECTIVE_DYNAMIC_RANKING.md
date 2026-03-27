# Directive: Dynamic Ranking + MIN_CLAIM_VOL Raise

**Priority**: HIGH — ranking distortion identified as root cause of -$1,941 P&L regression
**Risk**: MEDIUM — changes scanner_sim.py ranking logic, must pass regression
**Prereq**: `git pull` first (always)

## Background

The cumulative window fix (commit 8017aac) correctly recovered ROLR but introduced a ranking distortion. Stocks discovered early (e.g., 07:15) get locked into `found_symbols` with low cumulative volume. Since volume is 40% of the composite ranking score, their rank tanks — and they can displace better stocks on the final list.

**Example**: CJMB on Jan 15 2026 went from 16.6M volume (rank #1, old scanner) to 440K volume (rank #4, new scanner). Lost +$1,028 trade.

**Root cause**: Two problems in `find_emerging_movers()`:
1. Once `found_symbols.add(sym)` fires at a checkpoint, the stock is NEVER re-evaluated at later checkpoints — its volume/RVOL are frozen at discovery time
2. The step 4b cumulative volume update (lines 778-803) fetches volume up to `discovery_time`, NOT the final checkpoint — so a stock found at 07:15 gets 4AM→07:15 volume even in the final sort at line 824

**Contrast**: bot.py already re-ranks dynamically — every rescan re-fetches snapshots and calls `set_symbol_ranks()` to fully replace rankings. scanner_sim.py needs to match this behavior.

---

## Phase 1: Raise MIN_CLAIM_VOL Threshold

**Goal**: Prevent premature claiming of low-volume stocks.

**File**: `scanner_sim.py`, `find_emerging_movers()`, line 614

**Current**:
```python
MIN_CLAIM_VOL = 50_000
```

**Change**: Read from env var, default 500_000:
```python
MIN_CLAIM_VOL = int(os.getenv("WB_MIN_CLAIM_VOL", "500000"))
```

**Why 500K**: The old incremental scanner naturally had higher volume at discovery because windows were narrower (missed low-vol early bars). 500K is conservative — ensures a stock has meaningful activity before locking in. ROLR had 38K at 08:15 (would still wait) and 2M+ at 08:30 (would claim). CJMB had 440K at early checkpoint (would wait) but 16.6M later (would claim with correct volume).

**Also add to `.env`** with comment:
```bash
WB_MIN_CLAIM_VOL=500000       # Min cumulative vol to claim a stock in scanner rescan
```

### Phase 1 Verification
Run scanner on 2026-01-14 only and confirm ROLR still appears:
```bash
source venv/bin/activate
python scanner_sim.py 2026-01-14
```
Check output — ROLR must be present. If ROLR disappears, lower threshold to 250000 and retest.

---

## Phase 2: Dynamic Re-Ranking at Every Checkpoint

**Goal**: Previously-discovered stocks get their volume/RVOL/gap updated at EVERY subsequent checkpoint, not just at discovery time.

**File**: `scanner_sim.py`, `find_emerging_movers()`, lines 560-639

### Current Logic (BROKEN)
```
for each checkpoint:
    check_symbols = all_symbols - found_symbols   # SKIPS previously found stocks
    for each symbol in check_symbols:
        if passes gap/price/vol gates:
            found_symbols.add(sym)   # LOCKED — never revisited
```

### New Logic (DYNAMIC)
```
for each checkpoint:
    # 1. Discover NEW stocks (same as before, minus found_symbols)
    # 2. UPDATE existing stocks with latest volume/gap from cumulative window

    # After processing new stocks:
    for existing_candidate in all_candidates_so_far:
        fetch cumulative bars 4AM → this checkpoint
        update pm_volume, gap_pct, pm_price with latest values

    # Re-rank ALL candidates (new + existing) at this checkpoint
```

### Implementation Details

**Step A**: Change the loop structure in `find_emerging_movers()`:
1. Keep the existing `found_symbols` skip set for NEW discovery (don't double-add)
2. After discovering new stocks at each checkpoint, add an UPDATE pass over ALL previously-found stocks
3. For each previously-found stock, fetch bars from 4AM → current checkpoint
4. Update `pm_volume`, `pm_price`, `gap_pct` on the existing candidate dict
5. The final sort at line 824 will now use up-to-date values

**Step B**: Return updated candidates (not just new ones):
- Currently `find_emerging_movers()` returns only `all_new` (newly discovered stocks)
- It needs to ALSO update the `existing_candidates` list that was passed in
- Option 1: Mutate the existing_candidates in-place (they're dicts, passed by reference)
- Option 2: Return both new and updated candidates
- **Prefer Option 1** — mutate in-place. The `existing_candidates` dicts are already in the `candidates` list in `run_scanner()`. Mutating them updates the originals.

**Step C**: Refactor function signature:
```python
def find_emerging_movers(prev_close, existing_candidates, date_str, avg_daily_vol):
```
Add `avg_daily_vol` parameter so we can recompute RVOL during updates.

**Step D**: The update pass per checkpoint:
```python
# After new-stock discovery in the checkpoint loop, UPDATE existing candidates
for c in existing_candidates + all_new:  # all_new = candidates found at prior checkpoints
    sym = c["symbol"]
    if sym in check_symbols:
        continue  # just processed as new discovery
    # Fetch cumulative bars 4AM → this checkpoint
    try:
        request = StockBarsRequest(
            symbol_or_symbols=[sym],
            timeframe=TimeFrame.Minute,
            start=four_am,
            end=win_end,
        )
        bars = hist_client.get_stock_bars(request)
        bar_list = bars.data.get(sym, [])
        if bar_list:
            cum_vol = sum(b.volume for b in bar_list if b.volume)
            latest_price = bar_list[-1].close
            new_gap = (latest_price - c["prev_close"]) / c["prev_close"] * 100
            c["pm_volume"] = cum_vol
            c["pm_price"] = round(latest_price, 4)
            c["gap_pct"] = round(new_gap, 2)
            # Update RVOL
            adv = avg_daily_vol.get(sym)
            if adv and adv > 0:
                c["relative_volume"] = round(cum_vol / adv, 2)
    except Exception:
        pass  # keep existing values
```

**Step E**: Remove the step 4b cumulative volume update (lines 778-803) — it's now redundant since every checkpoint already updates cumulative volume. The RVOL assignment at lines 805-811 is also handled inside the loop now.

**IMPORTANT: API call optimization**. The update pass fetches bars for EACH existing candidate at EACH checkpoint. To minimize API calls:
- Batch symbols into chunks (same as the discovery pass, chunk_size=1000)
- Only update candidates that were found at a PRIOR checkpoint (not the current one)
- The max candidates at any checkpoint is ~20-30, so this is manageable

### Phase 2 Verification
Run scanner on 2026-01-15 (the CJMB date) and check:
```bash
python scanner_sim.py 2026-01-15
```
- CJMB should have updated volume (millions, not 440K) in final output
- CJMB rank should be higher than it was in the post-fix scanner
- Compare output against `scanner_results/backup_jan2026_pre_phase4/2026-01-15.json` — rankings should be closer to the old (pre-cumulative-fix) order

Also run 2026-01-14:
```bash
python scanner_sim.py 2026-01-14
```
- ROLR must still appear
- Volume should reflect 08:30 checkpoint data (millions), not 08:15 (38K)

---

## Phase 3: Full Rescan Both Months

**Gate**: Phase 1 + Phase 2 verification must pass first.

### Backup existing results
```bash
mkdir -p scanner_results/backup_pre_dynamic_ranking
cp scanner_results/2025-01-*.json scanner_results/backup_pre_dynamic_ranking/
cp scanner_results/2026-01-*.json scanner_results/backup_pre_dynamic_ranking/
```

### Run full rescan
```bash
# Jan 2025 (all dates in run_jan_v1_comparison.py JAN_2025_DATES)
for f in scanner_results/2025-01-*.json; do
    date=$(basename "$f" .json)
    echo "=== Scanning $date ==="
    python scanner_sim.py "$date"
done

# Jan 2026 (all dates in JAN_2026_DATES)
for f in scanner_results/2026-01-*.json; do
    date=$(basename "$f" .json)
    echo "=== Scanning $date ==="
    python scanner_sim.py "$date"
done
```

### Phase 3 Verification
Spot-check 3 dates per month:
- Confirm JSON files updated (check timestamps)
- Confirm stock counts reasonable (3-8 per day)
- Confirm no empty JSONs

---

## Phase 4: Full Month Backtests

### Clear stale state
```bash
rm -f jan_comparison_v1_state.json
```

### Run backtests
```bash
WB_MP_ENABLED=1 python run_jan_v1_comparison.py 2>&1 | tee jan_comparison_dynamic_ranking_output.txt
```

### Phase 4 Verification
1. Check Jan 2025 P&L — should be ≥ +$3,423 (old pre-cumulative-fix baseline)
2. Check Jan 2026 P&L — should be ≥ +$16,409 (old pre-cumulative-fix baseline)
3. Combined should be ≥ +$19,832 (V1 megatest target)
4. Save output for comparison

---

## Phase 5: Standalone Regression

**CRITICAL**: These MUST pass. If either fails, the directive has NOT succeeded.

```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

### Phase 5 Verification
- VERO P&L = +$18,583 ✅
- ROLR P&L = +$6,444 ✅
- If either fails, STOP and report. Do NOT proceed to git push.

---

## Phase 6: Commit and Push

Only after Phase 5 passes:

```bash
git add scanner_sim.py .env scanner_results/
git commit -m "Dynamic ranking: re-score at every checkpoint + raise MIN_CLAIM_VOL to 500K

- find_emerging_movers() now updates volume/RVOL/gap for ALL candidates at each
  checkpoint, not just newly-discovered ones. Fixes ranking distortion where
  early-discovered stocks got locked with low volume scores.
- MIN_CLAIM_VOL raised from 50K to 500K (env: WB_MIN_CLAIM_VOL) to prevent
  premature claiming of low-activity stocks.
- Step 4b cumulative volume update removed (redundant with per-checkpoint updates).
- Matches bot.py behavior: ranks are dynamic, updated at every watchlist refresh.

Regression: VERO +\$18,583, ROLR +\$6,444

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

git push origin main
```

---

## Summary of Changes

| What | Where | Change |
|------|-------|--------|
| MIN_CLAIM_VOL | scanner_sim.py line 614 | 50K → 500K (env-gated: WB_MIN_CLAIM_VOL) |
| Dynamic re-ranking | scanner_sim.py find_emerging_movers() | Update ALL candidates' volume/RVOL/gap at every checkpoint |
| Step 4b cleanup | scanner_sim.py lines 778-811 | Remove redundant cumulative vol fetch (now in checkpoint loop) |
| Env var | .env | Add WB_MIN_CLAIM_VOL=500000 |

**No changes to bot.py** — it already re-ranks dynamically on every rescan.

---

## Rollback Plan

If regression fails and root cause is unclear:
1. Restore scanner results from backup: `cp scanner_results/backup_pre_dynamic_ranking/* scanner_results/`
2. Revert MIN_CLAIM_VOL: set `WB_MIN_CLAIM_VOL=50000` in .env
3. The `found_symbols` skip-set logic can be restored by reverting the update pass
