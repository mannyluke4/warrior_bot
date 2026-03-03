# Profile C Validation Directive

## Objective
Validate Profile C (Fast Movers — Fast Mode ON, L2 OFF) by backtesting micro-float stocks that the standard detector missed (zero-trade stocks) AND confirming Fast Mode doesn't break Profile A winners.

## Current Profile C Config (`profiles/C.json`)
```json
{
  "WB_FAST_MODE": "1",
  "WB_FAST_MODE_MIN_BARS": "10",
  "WB_ENABLE_L2": "0",
  "WB_EXIT_MODE": "signal",
  "WB_MAX_ENTRIES_PER_SYMBOL": "3"
}
```

## Background

Profile C targets micro-float stocks (<5M) that move too fast for the standard entry detector. These stocks complete their impulse before the bot's normal "wait for pullback → arm → trigger" sequence fires. Fast Mode uses anticipation entry (enters earlier in the setup) to catch these.

**Prior evidence**: HIND improved from -$3 to +$663 with Fast Mode + Databento tick data in Round 6.5 testing.

**Key distinction from Profile A**: Both are micro-float, 7am scanner. Profile A catches stocks with tradeable pullbacks. Profile C catches stocks that DON'T pull back — they just rip.

## Phase 1: Core Profile C Candidates (Zero-Trade Micro-Float Stocks)

These are micro-float stocks from the 137-stock study where the standard detector took ZERO trades. Fast Mode may capture setups here.

**Run each with**: `python simulate.py SYMBOL DATE --profile C --ticks --feed databento --no-fundamentals`

Also run each with `--profile A` as baseline to confirm Profile A also gets 0 trades (sanity check).

### Priority 1: Known Fast Movers (from directive)

| # | Symbol | Date | Float (M) | Scanner | Gap | Notes |
|---|--------|------|-----------|---------|-----|-------|
| 1 | HIND | 2026-01-16 | 1.5 | 07:00 | -0.6% | Known fast mover, 0 trades standard |
| 2 | HIND | 2026-02-05 | 1.5 | 07:00 | -0.6% | 0 trades standard |
| 3 | GRI | 2026-01-27 | 1.4 | 07:00 | -3.9% | 0 trades standard |
| 4 | GRI | 2026-01-28 | 1.4 | 07:00 | -3.9% | 0 trades standard |
| 5 | ELAB | 2026-01-06 | 0.2 | 07:00 | -4.2% | 0 trades standard, ultra-low float |
| 6 | ELAB | 2026-01-08 | 0.2 | 07:00 | -4.2% | 0 trades standard |
| 7 | ELAB | 2026-01-09 | 0.2 | 07:00 | -4.2% | 0 trades standard |

### Priority 2: Other Zero-Trade 7am Micro-Float (Likely Fast Movers)

| # | Symbol | Date | Float (M) | Scanner | Gap |
|---|--------|------|-----------|---------|-----|
| 8 | ACON | 2026-01-06 | 0.7 | 07:00 | 6.9% |
| 9 | ACON | 2026-01-27 | 0.7 | 07:00 | 6.9% |
| 10 | APVO | 2026-02-05 | 0.9 | 07:00 | -3.4% |
| 11 | BCTX | 2026-01-16 | 1.7 | 07:00 | 6.7% |
| 12 | FEED | 2026-01-16 | 0.8 | 07:00 | -3.8% |
| 13 | GWAV | 2026-01-06 | 0.8 | 07:00 | -1.4% |
| 14 | GWAV | 2026-02-05 | 0.8 | 07:00 | -1.4% |
| 15 | GWAV | 2026-02-13 | 0.8 | 07:00 | -1.4% |
| 16 | MLEC | 2026-01-06 | 0.7 | 07:00 | -21.7% |
| 17 | MLEC | 2026-01-28 | 0.7 | 07:00 | -21.7% |
| 18 | PAVM | 2026-01-16 | 0.7 | 07:00 | -0.2% |
| 19 | PAVM | 2026-02-05 | 0.7 | 07:00 | -0.2% |
| 20 | ROLR | 2026-02-13 | 3.6 | 07:00 | -6.2% |
| 21 | RVSN | 2026-01-27 | 1.8 | 07:00 | 0.6% |
| 22 | RVSN | 2026-02-05 | 1.8 | 07:00 | 0.6% |
| 23 | SLE | 2026-01-27 | 0.7 | 07:00 | 1.5% |
| 24 | SMX | 2026-02-09 | 0.0 | 07:00 | 4.0% |
| 25 | SNSE | 2026-01-28 | 0.7 | 07:00 | -2.3% |
| 26 | SNSE | 2026-02-05 | 0.7 | 07:00 | -2.3% |
| 27 | SXTP | 2026-01-28 | 0.9 | 07:00 | -4.8% |
| 28 | TNMG | 2026-01-06 | 1.2 | 07:00 | -0.7% |
| 29 | TWG | 2026-01-20 | 0.5 | 07:00 | -1.1% |
| 30 | VERO | 2026-01-06 | 1.6 | 07:00 | -9.1% |
| 31 | VERO | 2026-02-05 | 1.6 | 07:00 | -9.1% |

### Priority 3: HIND Traded Date (Fast Mode vs Standard)

| # | Symbol | Date | Float (M) | Scanner | NoL2 P&L | Notes |
|---|--------|------|-----------|---------|----------|-------|
| 32 | HIND | 2026-01-27 | 1.5 | 07:00 | +$260 | Had 2 trades with standard |

Run with both `--profile A` and `--profile C` to compare.

## Phase 2: Regression Check — Fast Mode on Profile A Winners

**CRITICAL**: Fast Mode must NOT break Profile A's proven winners. Run the 6 Profile A regression stocks with `--profile C` to verify:

| Symbol | Date | Profile A P&L | Run with Profile C |
|--------|------|--------------|-------------------|
| VERO | 2026-01-15 | +$6,890 | Must not deteriorate significantly |
| GWAV | 2026-01-16 | +$6,735 | Must not deteriorate significantly |
| APVO | 2026-01-09 | +$7,622 | Must not deteriorate significantly |
| BNAI | 2026-02-27 | +$5,610 | Must not deteriorate significantly |
| MOVE | 2026-01-06 | +$5,502 | Must not deteriorate significantly |
| ANPA | 2026-01-09 | +$2,088 | Must not deteriorate significantly |

**Acceptable outcome**: If Fast Mode slightly changes results (±$500) that's fine. If it breaks a winner by >$2K, Profile C needs a differentiation mechanism.

## Batch Script

```bash
#!/bin/bash
# Profile C Validation — Fast Movers
# Run from repo root

RESULTS_FILE="profile_c_results.csv"
echo "symbol,date,float_m,scanner_time,profile_a_pnl,profile_c_pnl,delta,profile_a_trades,profile_c_trades" > $RESULTS_FILE

run_compare() {
    local sym=$1 date=$2 float=$3 scanner=$4
    echo "=== $sym $date ==="
    
    # Run Profile A (baseline)
    OUT_A=$(python simulate.py $sym $date --profile A --ticks --feed databento --no-fundamentals 2>&1)
    PNL_A=$(echo "$OUT_A" | grep "Gross P&L" | sed 's/.*\$//;s/,.*//' | tr -d ' +')
    TRADES_A=$(echo "$OUT_A" | grep "Trades:" | head -1 | sed 's/.*Trades: //;s/ .*//')
    
    # Run Profile C (fast mode)
    OUT_C=$(python simulate.py $sym $date --profile C --ticks --feed databento --no-fundamentals 2>&1)
    PNL_C=$(echo "$OUT_C" | grep "Gross P&L" | sed 's/.*\$//;s/,.*//' | tr -d ' +')
    TRADES_C=$(echo "$OUT_C" | grep "Trades:" | head -1 | sed 's/.*Trades: //;s/ .*//')
    
    PNL_A=${PNL_A:-0}
    PNL_C=${PNL_C:-0}
    TRADES_A=${TRADES_A:-0}
    TRADES_C=${TRADES_C:-0}
    
    echo "  Profile A: $PNL_A ($TRADES_A trades) | Profile C: $PNL_C ($TRADES_C trades)"
    echo "$sym,$date,$float,$scanner,$PNL_A,$PNL_C,,$TRADES_A,$TRADES_C" >> $RESULTS_FILE
}

echo "--- Phase 1: Known Fast Movers ---"
run_compare HIND 2026-01-16 1.5 "07:00"
run_compare HIND 2026-01-27 1.5 "07:00"
run_compare HIND 2026-02-05 1.5 "07:00"
run_compare GRI  2026-01-27 1.4 "07:00"
run_compare GRI  2026-01-28 1.4 "07:00"
run_compare ELAB 2026-01-06 0.2 "07:00"
run_compare ELAB 2026-01-08 0.2 "07:00"
run_compare ELAB 2026-01-09 0.2 "07:00"

echo "--- Phase 1b: Other Zero-Trade 7am Micro-Float ---"
run_compare ACON 2026-01-06 0.7 "07:00"
run_compare ACON 2026-01-27 0.7 "07:00"
run_compare APVO 2026-02-05 0.9 "07:00"
run_compare BCTX 2026-01-16 1.7 "07:00"
run_compare FEED 2026-01-16 0.8 "07:00"
run_compare GWAV 2026-01-06 0.8 "07:00"
run_compare GWAV 2026-02-05 0.8 "07:00"
run_compare GWAV 2026-02-13 0.8 "07:00"
run_compare MLEC 2026-01-06 0.7 "07:00"
run_compare MLEC 2026-01-28 0.7 "07:00"
run_compare PAVM 2026-01-16 0.7 "07:00"
run_compare PAVM 2026-02-05 0.7 "07:00"
run_compare ROLR 2026-02-13 3.6 "07:00"
run_compare RVSN 2026-01-27 1.8 "07:00"
run_compare RVSN 2026-02-05 1.8 "07:00"
run_compare SLE  2026-01-27 0.7 "07:00"
run_compare SMX  2026-02-09 0.0 "07:00"
run_compare SNSE 2026-01-28 0.7 "07:00"
run_compare SNSE 2026-02-05 0.7 "07:00"
run_compare SXTP 2026-01-28 0.9 "07:00"
run_compare TNMG 2026-01-06 1.2 "07:00"
run_compare TWG  2026-01-20 0.5 "07:00"
run_compare VERO 2026-01-06 1.6 "07:00"
run_compare VERO 2026-02-05 1.6 "07:00"

echo "--- Phase 2: Profile A Regression with Profile C ---"
run_compare VERO 2026-01-15 1.6 "07:00"
run_compare GWAV 2026-01-16 0.8 "07:00"
run_compare APVO 2026-01-09 0.9 "07:00"
run_compare BNAI 2026-02-27 0.4 "07:00"
run_compare MOVE 2026-01-06 0.1 "07:00"
run_compare ANPA 2026-01-09 12.5 "07:00"

echo ""
echo "=== PROFILE C VALIDATION COMPLETE ==="
echo "Results saved to: $RESULTS_FILE"
cat $RESULTS_FILE
```

## Phase 3: Analysis

### 3a. Fast Mode Pickup Rate
- How many of the 31 zero-trade stocks did Profile C find trades on?
- What's the net P&L of those new trades?
- Are they mostly winners or losers?

### 3b. Fast Mode vs Standard on HIND 01-27
- Standard: +$260 (2 trades)
- Fast Mode: ??? — does earlier entry improve or hurt?

### 3c. Profile A Regression
- Do any of the 6 Profile A winners deteriorate by >$2K with Profile C?
- If yes, we need a way to distinguish C from A at tagging time
- If no, Profile C could potentially be the default for all micro-float

### 3d. Profile C vs Profile A Decision Matrix
After results, build a clear rule:
- "If micro-float stock pulled back and armed → Profile A worked → tag :A"
- "If micro-float stock ripped with no pullback → 0 trades standard → tag :C"
- Key question: Can we tell BEFORE the session which one it'll be?

## Success Criteria

Profile C is VALIDATED if:
- Fast Mode captures trades on ≥30% of the zero-trade stocks (≥10 of 31)
- Net P&L from those new trades is positive (any amount — turning $0 into profit)
- Profile A regressions are not significantly damaged (<$2K deterioration each)

Profile C NEEDS WORK if:
- Fast Mode generates mostly losing trades on these stocks
- Fast Mode breaks Profile A winners
- Fast Mode fires on zero-trade stocks but the trades are all small ($0 ± $100)

Profile C is REJECTED if:
- Fast Mode makes everything worse
- Cannot distinguish C from A stocks pre-session

## Reference

### Profile C Settings vs Profile A
| Setting | Profile A | Profile C |
|---------|-----------|-----------|
| Fast Mode | OFF | ON |
| Fast Mode Min Bars | N/A | 10 |
| L2 | OFF | OFF |
| Exit Mode | signal | signal |
| Max Entries | 2 | 3 |

### From Round 6.5 Testing
- HIND: Standard → -$3, Fast Mode + Databento → +$663
- Fast Mode min_bars=10 was the tuned setting
