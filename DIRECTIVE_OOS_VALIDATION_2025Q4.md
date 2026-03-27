# Directive: Out-of-Sample Validation — 2025 Q4 (Sep-Dec)

## Priority: HIGH — Overfit detection before live scaling
## Owner: CC
## Created: 2026-03-19 (Cowork)

---

## Why This Matters

All bot tuning — detector thresholds, exit logic, classifier, squeeze V2, exhaustion filter,
dynamic scaling — was developed and validated against **Jan-Mar 2026 data**. If the strategy
is overfit to that window, it will fail in live trading. We need to prove the edge holds on
data the bot has **never seen during development**.

**Sep-Dec 2025** is the ideal test window:
- Completely untouched by any tuning decisions
- Different market regime (pre-election volatility, holiday seasonality)
- 64 trading days of scanner data already exist (Oct-Dec)
- Sep needs to be scanned fresh (~20 trading days)

---

## Phase 0: Re-Scan with Aligned Criteria

The existing 2025 scanner data (Oct-Dec) is in the **old format** — it's missing
`relative_volume` and `avg_daily_volume` fields that the batch runner's filter needs
(`MIN_RVOL=2.0` requires `relative_volume`). Sep has no data at all.

### Step 0a: Generate Sep 2025 scanner data

```bash
cd ~/warrior_bot
source venv/bin/activate

# Generate all Sep 2025 trading days
for d in 2025-09-02 2025-09-03 2025-09-04 2025-09-05 2025-09-08 2025-09-09 \
         2025-09-10 2025-09-11 2025-09-12 2025-09-15 2025-09-16 2025-09-17 \
         2025-09-18 2025-09-19 2025-09-22 2025-09-23 2025-09-24 2025-09-25 \
         2025-09-26 2025-09-29 2025-09-30; do
    echo "Scanning $d..."
    python scanner_sim.py --date "$d" 2>&1 | tail -1
done
```

### Step 0b: Re-scan Oct-Dec with aligned format

The old JSONs are missing `relative_volume` / `avg_daily_volume`. Re-run scanner_sim.py
for all Oct-Dec dates to get the aligned format:

```bash
# Re-scan all existing Oct-Dec dates
for f in scanner_results/2025-10-*.json scanner_results/2025-11-*.json scanner_results/2025-12-*.json; do
    d=$(basename "$f" .json)
    echo "Re-scanning $d..."
    python scanner_sim.py --date "$d" 2>&1 | tail -1
done
```

**Verify** at least one file has the new format:
```bash
python3 -c "
import json
with open('scanner_results/2025-10-20.json') as f:
    data = json.load(f)
assert 'relative_volume' in data[0], 'MISSING relative_volume — rescan failed!'
print(f'OK: {len(data)} candidates, has relative_volume')
"
```

**Expected time**: Scanner fetches PM data from Databento. ~1-2 min per date, so ~90 min total
for ~85 dates. Consider running overnight if needed.

---

## Phase 1: Create the OOS Runner Script

Copy `run_ytd_v2_backtest.py` → `run_oos_2025q4_backtest.py` and change ONLY the DATES list
and state file:

```python
# Changes needed:
DATES = [
    # September 2025
    "2025-09-02", "2025-09-03", "2025-09-04", "2025-09-05", "2025-09-08",
    "2025-09-09", "2025-09-10", "2025-09-11", "2025-09-12", "2025-09-15",
    "2025-09-16", "2025-09-17", "2025-09-18", "2025-09-19", "2025-09-22",
    "2025-09-23", "2025-09-24", "2025-09-25", "2025-09-26", "2025-09-29",
    "2025-09-30",
    # October 2025
    "2025-10-01", "2025-10-02", "2025-10-03", "2025-10-06", "2025-10-07",
    "2025-10-08", "2025-10-09", "2025-10-10", "2025-10-13", "2025-10-14",
    "2025-10-15", "2025-10-16", "2025-10-17", "2025-10-20", "2025-10-21",
    "2025-10-22", "2025-10-23", "2025-10-24", "2025-10-27", "2025-10-28",
    "2025-10-29", "2025-10-30", "2025-10-31",
    # November 2025
    "2025-11-03", "2025-11-04", "2025-11-05", "2025-11-06", "2025-11-07",
    "2025-11-10", "2025-11-11", "2025-11-12", "2025-11-13", "2025-11-14",
    "2025-11-17", "2025-11-18", "2025-11-19", "2025-11-20", "2025-11-21",
    "2025-11-24", "2025-11-25", "2025-11-26", "2025-11-28",
    # December 2025
    "2025-12-01", "2025-12-02", "2025-12-03", "2025-12-04", "2025-12-05",
    "2025-12-08", "2025-12-09", "2025-12-10", "2025-12-11", "2025-12-12",
    "2025-12-15", "2025-12-16", "2025-12-17", "2025-12-18", "2025-12-19",
    "2025-12-22", "2025-12-23", "2025-12-24", "2025-12-26", "2025-12-29",
    "2025-12-30", "2025-12-31",
]

STATE_FILE = "oos_2025q4_backtest_state.json"
```

**CRITICAL**: Do NOT change ENV_BASE, filters, thresholds, STARTING_EQUITY, or any other
config. The ENTIRE point is to run the EXACT same bot config against unseen data.

---

## Phase 2: Run the OOS Backtest

```bash
cd ~/warrior_bot
source venv/bin/activate
python run_oos_2025q4_backtest.py 2>&1 | tee oos_2025q4_results.log
```

Save the report as `OOS_2025Q4_BACKTEST_RESULTS.md` (the script should auto-generate this —
rename the output if needed).

---

## Phase 3: Compare Against Jan-Mar 2026 Baseline

Create a comparison table in the results doc. Here are the Jan-Mar 2026 baseline numbers
to compare against:

### Jan-Mar 2026 Baseline (from YTD_V2_BACKTEST_RESULTS.md)

| Metric | Baseline (Jan-Mar 2026) |
|--------|------------------------|
| Trading days | 54 |
| Total P&L | +$34,600 (+115.3%) |
| Total trades | 38 |
| Win rate | 53% (20W/18L) |
| Profit factor | 5.61 |
| Max drawdown | $2,877 (4.5%) |
| Avg win | $2,105 |
| Avg loss | $417 |
| Largest win | $16,966 |
| Largest loss | $1,234 |
| MP trades | 21 (24% WR, +$15,330) |
| Squeeze trades | 17 (88% WR, +$19,270) |
| Green days | 54% of trading days |
| Avg P&L green day | ~$2,200 |
| Avg P&L red day | ~$430 |

### What "Pass" Looks Like

The OOS results DON'T need to match the baseline exactly. Different market conditions will
produce different absolute numbers. Here's what we're looking for:

**GREEN FLAGS (strategy is robust):**
- Positive total P&L (even if much smaller than baseline)
- Win rate within 15 percentage points of baseline (38-68%)
- Profit factor > 1.5 (baseline is 5.61, but even 1.5 = real edge)
- Max drawdown < 15% of starting equity
- Squeeze WR stays above 65% (baseline 88%)
- MP shows same pattern: low WR but fat-tail winners
- Bot sits out quiet days (doesn't force trades)

**YELLOW FLAGS (investigate, may not be a problem):**
- Lower total P&L but still positive — could just be quieter market
- Fewer trades — scanner may find fewer candidates in this window
- No huge cascading winners — those are rare by nature
- Squeeze WR drops to 60-65% — small sample, could be variance

**RED FLAGS (possible overfitting):**
- Negative total P&L
- Win rate drops below 30%
- Profit factor < 1.0
- Max drawdown > 20%
- Squeeze becomes a net loser
- Lots of trades but almost all losers (bot is triggering on noise)
- Dramatically more trades than baseline (filters too loose)

---

## Phase 4: Document Findings

Write a recap to `cowork_reports/` with:

1. OOS headline numbers vs baseline comparison table
2. Monthly breakdown (Sep / Oct / Nov / Dec)
3. Strategy breakdown (MP vs Squeeze)
4. Top 3 winners and top 3 losers
5. Any red/yellow flags identified
6. Recommendation: confidence level for live scaling

Also save:
- `oos_2025q4_backtest_state.json` (full state)
- `oos_2025q4_results.log` (verbose output)
- `OOS_2025Q4_BACKTEST_RESULTS.md` (formatted report)

---

## Phase 5: Regression Check

After everything, verify the primary regression hasn't been disturbed:

```bash
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

---

## Execution Notes

- **Scanner re-scan (Phase 0) is the bottleneck** — it may take 60-90 min to scan ~85 dates.
  Consider running this first, then the backtest can be fast (tick cache will build as it goes).
- **Tick data for 2025 is NOT cached** — the backtest will need to fetch from Databento for
  every stock/date. This will be SLOW (similar to the 2-hour-for-10-days experience). Plan
  for 3-6 hours total runtime. Consider running overnight.
- The OOS script is a COPY of the YTD runner — no code changes to the bot itself.
- Commit the OOS runner script and results, but NOT any changes to the main bot config.

---

## Quick Reference: Expected Timeline

| Phase | Est. Time | Notes |
|-------|-----------|-------|
| 0: Re-scan | 60-90 min | Databento API calls, parallelizable |
| 1: Create script | 5 min | Copy + edit DATES |
| 2: Run backtest | 3-6 hours | No tick cache for 2025 data |
| 3: Compare | 15 min | Mostly automated by report generator |
| 4: Document | 10 min | Write recap |
| 5: Regression | 2 min | Cached, fast |

**Recommendation**: Run Phase 0 + 2 overnight. Review results in the morning.

---

*Directive created by Cowork — 2026-03-19*
*Purpose: Overfit detection before live scaling decisions*
