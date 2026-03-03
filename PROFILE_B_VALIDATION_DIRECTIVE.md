# Profile B Validation Directive

## Objective
Validate Profile B (mid-float 5–50M stocks, L2 enabled) by backtesting all 27 mid-float stocks from the 137-stock study using `--profile B`. Compare results against NoL2 baseline to determine if Profile B improves or hurts performance on this stock class.

## Current Profile B Config (`profiles/B.json`)
```json
{
  "WB_ENABLE_L2": "1",
  "WB_L2_HARD_GATE_WARMUP_BARS": "30",
  "WB_L2_STOP_TIGHTEN_MIN_IMBALANCE": "0.65",
  "WB_EXIT_MODE": "signal",
  "WB_CLASSIFIER_ENABLED": "1",
  "WB_CLASSIFIER_SUPPRESS_ENABLED": "0",
  "WB_FAST_MODE": "0",
  "WB_MAX_ENTRIES_PER_SYMBOL": "3"
}
```

## Phase 1: Run All 27 Mid-Float Stocks with `--profile B`

Run each stock/date combo below with `--profile B --ticks --feed databento`. Capture the P&L for each.

**IMPORTANT**: Use `--ticks --feed databento` for all runs (tick-level fidelity). Use `--no-fundamentals` to speed up batch runs.

### Stock List (27 runs)

| # | Symbol | Date | Float (M) | Scanner Time | NoL2 P&L (baseline) |
|---|--------|------|-----------|-------------|---------------------|
| 1 | ANPA | 2026-01-06 | 12.5 | 07:00 | -$2,730 |
| 2 | AZI | 2026-01-06 | 44.5 | 07:27 | +$783 |
| 3 | IBIO | 2026-01-06 | 27.1 | 07:46 | -$1,444 |
| 4 | OPTX | 2026-01-06 | 6.0 | 07:00 | -$78 |
| 5 | FLYX | 2026-01-08 | 5.7 | 07:00 | +$473 |
| 6 | OPTX | 2026-01-08 | 6.0 | 07:00 | -$223 |
| 7 | ANPA | 2026-01-09 | 12.5 | 07:00 | +$2,088 |
| 8 | IBIO | 2026-01-09 | 27.1 | 07:00 | -$267 |
| 9 | OPTX | 2026-01-09 | 6.0 | 07:00 | -$1,479 |
| 10 | VOR | 2026-01-12 | 7.2 | 08:23 | +$501 |
| 11 | FJET | 2026-01-13 | 18.5 | 08:10 | -$1,263 |
| 12 | BEEM | 2026-01-14 | 18.0 | 07:00 | -$900 |
| 13 | AUID | 2026-01-15 | 11.8 | 08:57 | -$1,683 |
| 14 | QMCO | 2026-01-15 | 14.4 | 08:31 | -$1,193 |
| 15 | CNVS | 2026-02-13 | 15.0 | 09:04 | -$731 |
| 16 | CRSR | 2026-02-13 | 46.6 | 08:41 | -$1,939 |
| 17 | MCRB | 2026-02-13 | 6.8 | 09:30 | +$113 |
| 18 | BATL | 2026-02-18 | 7.2 | 07:00 | -$499 |
| 19 | ANNA | 2026-02-27 | 9.4 | 08:30 | -$1,088 |
| 20 | BATL | 2026-02-27 | 7.2 | 08:00 | +$1,972 |
| 21 | INDO | 2026-02-27 | 9.5 | 08:00 | -$487 |
| 22 | LBGJ | 2026-02-27 | 16.7 | 09:00 | -$110 |
| 23 | MRM | 2026-02-27 | 5.8 | 08:00 | -$1,562 |
| 24 | ONMD | 2026-02-27 | 16.4 | 08:30 | -$2,146 |
| 25 | PBYI | 2026-02-27 | 38.9 | 09:30 | +$21 |
| 26 | STRZ | 2026-02-27 | 16.7 | 08:00 | +$94 |
| 27 | TSSI | 2026-02-27 | 21.8 | 08:00 | -$1,116 |

### Batch Script

```bash
#!/bin/bash
# Profile B Validation — 27 mid-float stocks
# Run from repo root. Ensure .env has APCA and DATABENTO keys.

RESULTS_FILE="profile_b_results.csv"
echo "symbol,date,float_m,scanner_time,profile_b_pnl,profile_b_trades,nol2_baseline_pnl" > $RESULTS_FILE

run_sim() {
    local sym=$1 date=$2 float=$3 scanner=$4 baseline=$5
    echo "=== Running $sym $date (Profile B) ==="
    OUTPUT=$(python simulate.py $sym $date --profile B --ticks --feed databento --no-fundamentals 2>&1)
    # Extract P&L from "Gross P&L: $X" line
    PNL=$(echo "$OUTPUT" | grep "Gross P&L" | sed 's/.*\$//;s/,.*//' | tr -d ' +')
    TRADES=$(echo "$OUTPUT" | grep "Trades:" | head -1 | sed 's/.*Trades: //;s/ .*//')
    echo "$sym,$date,$float,$scanner,${PNL:-0},${TRADES:-0},$baseline" >> $RESULTS_FILE
    echo "$OUTPUT" | tail -20
    echo ""
}

# January 2026 (hot market)
run_sim ANPA 2026-01-06 12.5 "07:00" -2730
run_sim AZI  2026-01-06 44.5 "07:27" 783
run_sim IBIO 2026-01-06 27.1 "07:46" -1444
run_sim OPTX 2026-01-06 6.0  "07:00" -78
run_sim FLYX 2026-01-08 5.7  "07:00" 473
run_sim OPTX 2026-01-08 6.0  "07:00" -223
run_sim ANPA 2026-01-09 12.5 "07:00" 2088
run_sim IBIO 2026-01-09 27.1 "07:00" -267
run_sim OPTX 2026-01-09 6.0  "07:00" -1479
run_sim VOR  2026-01-12 7.2  "08:23" 501
run_sim FJET 2026-01-13 18.5 "08:10" -1263
run_sim BEEM 2026-01-14 18.0 "07:00" -900
run_sim AUID 2026-01-15 11.8 "08:57" -1683
run_sim QMCO 2026-01-15 14.4 "08:31" -1193

# February 2026 (cold market)
run_sim CNVS 2026-02-13 15.0 "09:04" -731
run_sim CRSR 2026-02-13 46.6 "08:41" -1939
run_sim MCRB 2026-02-13 6.8  "09:30" 113
run_sim BATL 2026-02-18 7.2  "07:00" -499
run_sim ANNA 2026-02-27 9.4  "08:30" -1088
run_sim BATL 2026-02-27 7.2  "08:00" 1972
run_sim INDO 2026-02-27 9.5  "08:00" -487
run_sim LBGJ 2026-02-27 16.7 "09:00" -110
run_sim MRM  2026-02-27 5.8  "08:00" -1562
run_sim ONMD 2026-02-27 16.4 "08:30" -2146
run_sim PBYI 2026-02-27 38.9 "09:30" 21
run_sim STRZ 2026-02-27 16.7 "08:00" 94
run_sim TSSI 2026-02-27 21.8 "08:00" -1116

echo ""
echo "=== PROFILE B VALIDATION COMPLETE ==="
echo "Results saved to: $RESULTS_FILE"
cat $RESULTS_FILE
```

## Phase 2: Analysis (After Runs Complete)

After all 27 runs, analyze `profile_b_results.csv`:

### 2a. Overall Comparison
- **Total Profile B P&L** vs **Total NoL2 Baseline P&L** (-$14,893)
- Previously known L2 total for these stocks was -$12,999 (delta +$1,894)
- Profile B adds max_entries=3 and classifier — does that change anything vs raw L2?

### 2b. 7am vs Non-7am Split
The 137-stock analysis showed:
- **7am subset (11 stocks)**: NoL2 = -$4,276, L2 = -$2,728 (L2 helps by $1,548)
- **Non-7am subset (16 stocks)**: NoL2 = -$10,617, L2 = -$10,271 (L2 barely helps, $346)

Key question: **Should Profile B be restricted to 7am-only scanner stocks?**
Non-7am mid-float stocks lose heavily regardless of L2 status. Filtering them out could dramatically reduce Profile B's bleed.

### 2c. Per-Stock Winners vs Losers
Identify which stocks Profile B improved vs hurt:
- Stocks where Profile B > NoL2 → Good candidates for Profile B
- Stocks where Profile B < NoL2 → Profile B hurts, may need different profile or skip
- Stocks where Profile B ≈ NoL2 (±$100) → L2 didn't matter, profile overhead was neutral

### 2d. Max Entries Impact
Profile B sets `WB_MAX_ENTRIES_PER_SYMBOL=3` vs default 2. Check:
- How many stocks used a 3rd entry?
- Did 3rd entries help or hurt?
- Should this be 2 instead of 3?

## Phase 3: Profile B Tuning (If Needed)

Based on Phase 2 results, potential adjustments:

1. **Scanner time filter**: If non-7am stocks consistently lose, add scanner time gate
2. **Max entries**: Drop to 2 if 3rd entries are net negative
3. **Warmup bars**: Currently 30 — could test 20 or 40
4. **Imbalance threshold**: Currently 0.65 — could test 0.55 or 0.75
5. **Float sub-ranges**: Maybe 5-15M behaves differently than 15-50M

## Success Criteria

Profile B is VALIDATED if:
- Total Profile B P&L > Total NoL2 P&L (L2 adds value)
- OR: A clear subset (e.g., 7am-only) shows significant improvement
- Profile B doesn't make any individual stock dramatically worse (>$2K deterioration)

Profile B NEEDS WORK if:
- Profile B P&L ≈ NoL2 P&L (L2 adds nothing, just costs data fees)
- Some stocks get significantly worse with Profile B
- The only improvement is from one outlier (ANPA 01-09)

## Reference Data

### From L2 Phase 3 Study (137 stocks)
- Mid-float (5-50M): L2 delta = +$1,894 across 27 stocks
- L2 helps most on float 10-20M range
- L2 warmup 30 bars was optimal in prior testing
- ANPA 2026-01-09 is the big swing: NoL2 +$2,088 → L2 +$5,091 (+$3,003)

### Profile B Settings vs Profile A
| Setting | Profile A | Profile B |
|---------|-----------|----------|
| L2 | OFF | ON |
| Warmup | N/A | 30 bars |
| Imbalance | N/A | 0.65 |
| Exit Mode | signal | signal |
| Classifier | ON | ON |
| Fast Mode | OFF | OFF |
| Max Entries | 2 | 3 |