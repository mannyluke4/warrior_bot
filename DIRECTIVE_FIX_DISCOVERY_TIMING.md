# Directive: Fix Backtest Discovery Timing Bias

## Priority: P0 — Affects validity of ALL backtest numbers
## Owner: CC
## Created: 2026-03-19 (Cowork)

---

## What's Wrong

The batch runners (`run_oos_2025q4_backtest.py` line 412, `run_ytd_v2_backtest.py` same
pattern) hardcode `sim_start = "07:00"` for every stock, ignoring the per-stock
`sim_start` field in the scanner results JSON.

The scanner simulation (`scanner_sim.py`) correctly tracks when each stock was discovered:
premarket stocks get `sim_start=07:00`, rescan stocks get their actual discovery time
(08:00, 08:30, 09:00, 09:30, 10:00, or 10:30). This field is saved in
`scanner_results/{date}.json` and is already correct. The runner just doesn't use it.

**Result: the backtest can take trades on a stock BEFORE the scanner would have found it.**

**Impact quantified (Cowork analysis, 2026-03-19):**

| Metric | Value |
|--------|-------|
| Total trades across OOS + YTD | 119 |
| Trades with lookahead bias (trade time < discovery time) | **48 (40%)** |
| P&L from lookahead trades | **+$35,787 (46% of total)** |
| P&L from clean trades | +$42,699 (54% of total) |

**Worst offenders (biggest P&L from trades before discovery):**

| Stock | Date | Trade Time | Discovery Time | Gap | P&L |
|-------|------|-----------|---------------|-----|-----|
| ARTL | 2026-03-18 | 07:42 | 08:00 | 18m | +$9,512 |
| ROLR | 2026-01-14 | 08:19, 08:26 | 08:30 | 11m, 4m | +$7,678 |
| AKAN | 2025-10-01 | 09:42 | 10:00 | 18m | +$3,794 |
| CWD | 2025-09-09 | 07:37, 07:45, 07:47 | 08:00 | 23m, 15m, 13m | +$3,293 |
| MAMO | 2025-09-18 | 07:42 | 08:00 | 18m | +$2,616 |
| VSEE | 2025-10-28 | 08:42, 09:01, 09:02 | 09:30 | 48m, 29m, 28m | +$1,998 |
| BNAI | 2025-12-29 | 09:31 | 10:00 | 29m | +$1,881 |
| AEHL | 2025-12-30 | 09:38 | 10:00 | 22m | +$1,731 |
| GMEX | 2025-11-06 | 08:52 | 09:00 | 8m | +$1,502 |
| GRI | 2025-09-11 | 08:54 | 09:00 | 6m | +$1,682 |

**The live bot does NOT have this bug.** `bot.py` uses a real-time `rescan_thread()` that
only adds stocks when they're actually discovered. This is purely a backtest issue — but
it means all backtest numbers (OOS, YTD, continuous equity, dynamic cap, PDT sim) are
potentially overstated.

---

## The Fix

### Step 1: One-line fix in both runners

**`run_oos_2025q4_backtest.py` — line 412:**
```python
# BEFORE (buggy):
sim_start = "07:00"  # Always sim from market prep — not discovery time

# AFTER (fixed):
sim_start = c.get("sim_start", "07:00")  # Respect scanner discovery time
```

**`run_ytd_v2_backtest.py` — apply identical fix** (search for same pattern).

That's it. The scanner data already has the correct `sim_start` per stock. Premarket
stocks already have `sim_start=07:00` so they're unaffected. Rescan stocks will now
start their simulation at their actual discovery time.

### Step 2: Verify scanner data has `sim_start` for all dates

Quick sanity check before re-running:

```bash
cd ~/warrior_bot
source venv/bin/activate

python3 -c "
import json, os
scanner_dir = 'scanner_results'
missing = []
for f in sorted(os.listdir(scanner_dir)):
    if not f.endswith('.json'): continue
    with open(os.path.join(scanner_dir, f)) as fh:
        data = json.load(fh)
    for c in data:
        if 'sim_start' not in c:
            missing.append((f, c['symbol']))
if missing:
    print(f'MISSING sim_start in {len(missing)} candidates:')
    for f, s in missing[:20]:
        print(f'  {f}: {s}')
else:
    print('All candidates have sim_start field.')
"
```

If any are missing, the default `"07:00"` in `c.get("sim_start", "07:00")` preserves
current behavior for those stocks — no regression risk.

### Step 3: Clear state and re-run OOS backtest

```bash
cd ~/warrior_bot
source venv/bin/activate
git pull

# Back up current (biased) results for comparison
cp oos_2025q4_backtest_state.json oos_2025q4_backtest_state_BIASED.json
cp OOS_2025Q4_BACKTEST_RESULTS.md OOS_2025Q4_BACKTEST_RESULTS_BIASED.md

# Clear state to force full re-run
rm oos_2025q4_backtest_state.json

# Re-run with fixed discovery timing
python run_oos_2025q4_backtest.py 2>&1 | tee oos_2025q4_fixed_timing.log
```

**Expected runtime:** ~3-4 hours (85 days × ~20 stocks × tick replay). Can run overnight.

### Step 4: Re-run YTD backtest

```bash
cp ytd_v2_backtest_state.json ytd_v2_backtest_state_BIASED.json
rm ytd_v2_backtest_state.json

python run_ytd_v2_backtest.py 2>&1 | tee ytd_v2_fixed_timing.log
```

### Step 5: Compare biased vs corrected results

After both re-runs complete, generate a comparison report:

```bash
python3 << 'EOF'
import json

# Load biased and corrected
with open('oos_2025q4_backtest_state_BIASED.json') as f:
    biased = json.load(f)
with open('oos_2025q4_backtest_state.json') as f:
    corrected = json.load(f)

bt = biased['config_b']['trades']
ct = corrected['config_b']['trades']

print(f"BIASED:    {len(bt)} trades, ${sum(t['pnl'] for t in bt):+,} P&L")
print(f"CORRECTED: {len(ct)} trades, ${sum(t['pnl'] for t in ct):+,} P&L")
print(f"DELTA:     {len(ct) - len(bt)} trades, ${sum(t['pnl'] for t in ct) - sum(t['pnl'] for t in bt):+,} P&L")

# Identify trades that disappeared, shifted, or survived
biased_set = {(t['symbol'], t['date'], t['time']): t for t in bt}
corrected_set = {(t['symbol'], t['date'], t['time']): t for t in ct}

survived = set(biased_set.keys()) & set(corrected_set.keys())
eliminated = set(biased_set.keys()) - set(corrected_set.keys())
new_trades = set(corrected_set.keys()) - set(biased_set.keys())

print(f"\nSurvived (same time): {len(survived)}")
print(f"Eliminated: {len(eliminated)}")
print(f"New/shifted: {len(new_trades)}")

# Detail the eliminated trades
if eliminated:
    elim_pnl = sum(biased_set[k]['pnl'] for k in eliminated)
    print(f"\nEliminated trades total P&L: ${elim_pnl:+,}")
    for k in sorted(eliminated):
        t = biased_set[k]
        print(f"  {t['date']} {t['symbol']} {t['time']} {t['setup_type']} ${t['pnl']:+,}")
EOF
```

### Step 6: Document the impact

Write results to `cowork_reports/2026-03-XX_discovery_timing_fix.md` covering:

1. How many of the 48 lookahead trades were eliminated vs survived with later entries
2. New corrected P&L for OOS, YTD, and combined
3. Updated regression targets (VERO and ROLR should be unaffected since they're
   standalone mode, but verify)
4. Whether the strategy is still profitable after correction
5. Updated continuous equity curve and dynamic cap numbers

### Step 7: Update regression targets if needed

The standalone regressions (VERO +$18,583, ROLR +$6,444) should be **unaffected** — those
run `simulate.py` directly with explicit start times, not through the batch runner. Verify:

```bash
# These should produce identical results
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```

If the batch runner's corrected YTD numbers change significantly, update
`YTD_V2_BACKTEST_RESULTS.md` and `OOS_2025Q4_BACKTEST_RESULTS.md`.

---

## What We Expect

**Likely outcomes after the fix:**

1. **Trade count drops.** Some of the 48 lookahead trades will be eliminated entirely
   (the stock setup occurred before discovery, and by discovery time the move is over).

2. **Some trades shift to later entries.** A stock discovered at 08:00 might still set up
   a squeeze at 08:15 — the trade survives but at a different (possibly worse) entry.

3. **P&L drops but strategy remains profitable.** The clean 71 trades already net +$42,699.
   Even if all 48 lookahead trades are eliminated (unlikely), the strategy is still
   strongly positive.

4. **Squeeze hit rate may drop.** Many of the best squeeze entries were early-morning
   momentum plays on rescan stocks. Later discovery = later entry = smaller R-multiple.

5. **ROLR and ARTL are key tests.** ROLR was discovered at 08:30, first trade at 08:19
   (11 min gap). ARTL discovered at 08:00, traded at 07:42 (18 min gap). Both had strong
   moves that continued after discovery — they likely survive but with smaller P&L.

**What would be concerning:**
- If corrected OOS P&L goes negative, the squeeze edge may be weaker than believed
- If corrected win rate drops below 50%, the strategy's risk/reward changes fundamentally
- If max drawdown increases significantly, the risk profile is worse than modeled

**What would be reassuring:**
- Corrected OOS P&L remains positive (even if lower)
- Win rate stays above 50%
- The strategy still beats buy-and-hold on a risk-adjusted basis

---

## Downstream Impact

Once corrected results are available, Cowork needs to re-run these simulations
(all stored in `cowork_reports/`):

| Report | File | Status |
|--------|------|--------|
| OOS summary | `2026-03-19_oos_2025q4_results.md` | Needs update |
| Continuous equity curve | `2026-03-19_continuous_equity_curve.md` | Needs re-run |
| Dynamic notional cap sim | `2026-03-19_dynamic_notional_cap_simulation.md` | Needs re-run |
| PDT squeeze-only sim | `2026-03-19_pdt_squeeze_only_simulation.md` | Needs re-run |

**Do NOT make live scaling decisions until the corrected backtest is complete.**

---

## Git

After the fix and re-run:

```bash
git add run_oos_2025q4_backtest.py run_ytd_v2_backtest.py
git add OOS_2025Q4_BACKTEST_RESULTS.md YTD_V2_BACKTEST_RESULTS.md
git add oos_2025q4_backtest_state.json ytd_v2_backtest_state.json
git add cowork_reports/
git commit -m "P0: Fix backtest discovery timing — respect scanner sim_start instead of hardcoding 07:00

The batch runners were starting all simulations at 07:00 regardless of when the
scanner discovered each stock. This created lookahead bias on 48/119 trades (40%)
worth +\$35,787 in P&L. Fixed by using the per-stock sim_start field from scanner
results, which already had correct discovery timestamps.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main
```
