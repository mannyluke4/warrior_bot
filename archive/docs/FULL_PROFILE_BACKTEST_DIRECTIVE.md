# Full 137-Stock Profile System Backtest

## Objective
Run every stock from the 137-stock study through the multi-profile system to measure the real before/after impact. This is the ultimate validation of the profile approach before tomorrow's live session.

## Background

**Baseline**: All 137 stocks ran with default settings → P&L: -$196 (basically breakeven). The bot was trading everything the same way — micro-floats, mid-floats, large-caps, 7am stocks, 9am stocks — all with the same config.

**Hypothesis**: By routing each stock to its correct profile (or skipping it entirely), we dramatically improve total P&L.

## Profile Rules

| Profile | Criteria | Config |
|---------|----------|--------|
| A (`:A`) | Micro-float <5M AND 7am scanner | L2 OFF, signal exits, max 2 entries |
| B (`:B`) | Mid-float 5-50M AND 7am scanner | L2 ON, warmup 30 bars, signal exits, max 3 entries |
| X (`:X`) | Everything else (non-7am, large-float, unknown) | L2 OFF, signal exits, max 2 entries (conservative) |

## Two Runs

### Run 1: A + B Only (Skip X stocks)
Only run the 73 stocks that fit Profile A or B. Skip the 64 Profile X stocks entirely.
This answers: **"What if we only traded what we're good at?"**

### Run 2: A + B + X (Nothing Skipped)
Same A and B stocks, but also run the 64 Profile X stocks with conservative settings.
This answers: **"Does trading the unknowns add or subtract value?"**

The delta between Run 1 and Run 2 tells us whether Profile X is worth deploying live.

---

## Stock Categorization

### Profile A — Micro-Float Pre-Market (57 stocks)

Run with: `python simulate.py SYMBOL DATE --profile A --ticks --feed databento --no-fundamentals`

| # | Symbol | Date | Float | Baseline P&L |
|---|--------|------|-------|--------------|
| 1 | ACON | 2026-01-06 | 0.7M | $0 (0 trades) |
| 2 | ACON | 2026-01-08 | 0.7M | -$2,122 |
| 3 | ACON | 2026-01-27 | 0.7M | $0 (0 trades) |
| 4 | ACON | 2026-02-13 | 0.7M | -$214 |
| 5 | APVO | 2026-01-09 | 0.9M | +$7,622 |
| 6 | APVO | 2026-02-05 | 0.9M | $0 (0 trades) |
| 7 | BCTX | 2026-01-16 | 1.7M | $0 (0 trades) |
| 8 | BCTX | 2026-01-27 | 1.7M | $0 |
| 9 | BDSX | 2026-01-12 | 3.7M | -$45 |
| 10 | BNAI | 2026-01-16 | 3.3M | -$674 |
| 11 | BNAI | 2026-01-28 | 3.3M | +$5,610 |
| 12 | BNAI | 2026-02-05 | 3.3M | +$160 |
| 13 | ELAB | 2026-01-06 | 0.2M | $0 (0 trades) |
| 14 | ELAB | 2026-01-08 | 0.2M | $0 (0 trades) |
| 15 | ELAB | 2026-01-09 | 0.2M | $0 (0 trades) |
| 16 | ENVB | 2026-02-19 | 0.5M | +$474 |
| 17 | FEED | 2026-01-16 | 0.8M | $0 (0 trades) |
| 18 | GRI | 2026-01-27 | 1.4M | $0 (0 trades) |
| 19 | GRI | 2026-01-28 | 1.4M | $0 (0 trades) |
| 20 | GWAV | 2026-01-06 | 0.8M | $0 (0 trades) |
| 21 | GWAV | 2026-01-16 | 0.8M | +$6,735 |
| 22 | GWAV | 2026-02-05 | 0.8M | $0 (0 trades) |
| 23 | GWAV | 2026-02-13 | 0.8M | $0 (0 trades) |
| 24 | HIND | 2026-01-16 | 1.5M | $0 (0 trades) |
| 25 | HIND | 2026-01-27 | 1.5M | +$260 |
| 26 | HIND | 2026-02-05 | 1.5M | $0 (0 trades) |
| 27 | LCFY | 2026-01-16 | 1.4M | -$627 |
| 28 | MLEC | 2026-01-06 | 0.7M | $0 (0 trades) |
| 29 | MLEC | 2026-01-28 | 0.7M | $0 (0 trades) |
| 30 | MLEC | 2026-02-13 | 0.7M | +$173 |
| 31 | MNTS | 2026-02-06 | 1.3M | +$862 |
| 32 | MOVE | 2026-01-23 | 0.6M | -$156 |
| 33 | MOVE | 2026-01-27 | 0.6M | +$5,502 |
| 34 | PAVM | 2026-01-16 | 0.7M | $0 (0 trades) |
| 35 | PAVM | 2026-01-21 | 0.7M | +$1,586 |
| 36 | PAVM | 2026-02-05 | 0.7M | $0 (0 trades) |
| 37 | PMAX | 2026-01-13 | 1.2M | -$1,098 |
| 38 | ROLR | 2026-01-06 | 3.6M | -$1,422 |
| 39 | ROLR | 2026-01-14 | 3.6M | +$1,644 |
| 40 | ROLR | 2026-01-16 | 3.6M | -$1,228 |
| 41 | ROLR | 2026-02-13 | 3.6M | $0 (0 trades) |
| 42 | RVSN | 2026-01-27 | 1.8M | $0 (0 trades) |
| 43 | RVSN | 2026-02-05 | 1.8M | $0 (0 trades) |
| 44 | SHPH | 2026-01-16 | 1.6M | -$1,111 |
| 45 | SLE | 2026-01-23 | 0.7M | -$390 |
| 46 | SLE | 2026-01-27 | 0.7M | $0 (0 trades) |
| 47 | SNSE | 2026-01-28 | 0.7M | $0 (0 trades) |
| 48 | SNSE | 2026-02-05 | 0.7M | $0 (0 trades) |
| 49 | SNSE | 2026-02-18 | 0.7M | -$125 |
| 50 | SXTP | 2026-01-27 | 0.9M | -$2,078 |
| 51 | SXTP | 2026-01-28 | 0.9M | $0 (0 trades) |
| 52 | TNMG | 2026-01-06 | 1.2M | $0 (0 trades) |
| 53 | TNMG | 2026-01-16 | 1.2M | -$481 |
| 54 | TWG | 2026-01-20 | 0.5M | $0 (0 trades) |
| 55 | VERO | 2026-01-06 | 1.6M | $0 (0 trades) |
| 56 | VERO | 2026-01-16 | 1.6M | +$6,890 |
| 57 | VERO | 2026-02-05 | 1.6M | $0 (0 trades) |

### Profile B — Mid-Float L2-Assisted (16 stocks)

Run with: `python simulate.py SYMBOL DATE --profile B --ticks --feed databento --no-fundamentals`

| # | Symbol | Date | Float | Baseline P&L | L2 P&L (from study) |
|---|--------|------|-------|-------------|---------------------|
| 1 | ANPA | 2026-01-06 | 12.5M | -$2,730 | -$2,730 |
| 2 | ANPA | 2026-01-09 | 12.5M | +$2,088 | +$5,091 |
| 3 | ANPA | 2026-02-13 | 12.5M | $0 (0 trades) | $0 |
| 4 | AZI | 2026-01-09 | 44.5M | $0 (0 trades) | $0 |
| 5 | AZI | 2026-01-16 | 44.5M | $0 (0 trades) | $0 |
| 6 | BATL | 2026-02-18 | 7.2M | -$499 | -$499 |
| 7 | BEEM | 2026-01-14 | 18.0M | -$900 | -$500 |
| 8 | FLYX | 2026-01-06 | 5.7M | $0 (0 trades) | $0 |
| 9 | FLYX | 2026-01-08 | 5.7M | +$473 | -$80 |
| 10 | FLYX | 2026-01-27 | 5.7M | $0 (0 trades) | $0 |
| 11 | FLYX | 2026-02-13 | 5.7M | $0 (0 trades) | $0 |
| 12 | IBIO | 2026-01-08 | 27.1M | $0 (0 trades) | $0 |
| 13 | IBIO | 2026-01-09 | 27.1M | -$267 | -$267 |
| 14 | OPTX | 2026-01-06 | 6.0M | -$78 | -$78 |
| 15 | OPTX | 2026-01-08 | 6.0M | -$223 | -$223 |
| 16 | OPTX | 2026-01-09 | 6.0M | -$1,479 | -$613 |

### Profile X — Everything Else (64 stocks)

Run with: `python simulate.py SYMBOL DATE --profile X --ticks --feed databento --no-fundamentals`

Only needed for Run 2. These are non-7am scanner stocks, large-floats (>50M), and unknowns.

| # | Symbol | Date | Float | Scanner | Reason | Baseline P&L |
|---|--------|------|-------|---------|--------|-------------|
| 1 | AAOI | 2026-02-18 | 72.0M | 07:00 | large-float | -$415 |
| 2 | AAOI | 2026-02-27 | 72.0M | 09:30 | non-7am | -$1,950 |
| 3 | ACCL | 2026-01-16 | 2.9M | 04:00 | non-7am | -$1,072 |
| 4 | AEVA | 2026-02-27 | 26.7M | 09:30 | non-7am | $0 |
| 5 | AGIG | 2026-02-27 | 8.7M | 08:00 | non-7am | $0 |
| 6 | AKAN | 2026-01-12 | 0.1M | 09:09 | non-7am | $0 |
| 7 | ALMS | 2026-01-06 | 66.3M | 07:00 | large-float | +$3,407 |
| 8 | ALMS | 2026-01-09 | 66.3M | 07:00 | large-float | -$1,154 |
| 9 | ALMS | 2026-01-16 | 66.3M | 07:00 | large-float | $0 |
| 10 | ALMS | 2026-02-13 | 66.3M | 07:00 | large-float | -$236 |
| 11 | ANNA | 2026-02-27 | 9.4M | 08:30 | non-7am | -$1,088 |
| 12 | ARLO | 2026-02-27 | 103.9M | 09:20 | non-7am | -$692 |
| 13 | ASBP | 2026-02-11 | 2.3M | 07:45 | non-7am | $0 |
| 14 | AUID | 2026-01-15 | 11.8M | 08:57 | non-7am | -$1,683 |
| 15 | AZI | 2026-01-06 | 44.5M | 07:27 | non-7am | +$783 |
| 16 | AZI | 2026-02-10 | 44.5M | 07:15 | non-7am | $0 |
| 17 | BATL | 2026-02-27 | 7.2M | 08:00 | non-7am | +$1,972 |
| 18 | CDIO | 2026-02-27 | 1.7M | 09:45 | non-7am | +$791 |
| 19 | CNVS | 2026-02-13 | 15.0M | 09:04 | non-7am | -$731 |
| 20 | CRSR | 2026-02-13 | 46.6M | 08:41 | non-7am | -$1,939 |
| 21 | FEED | 2026-01-09 | 0.8M | 07:29 | non-7am | $0 |
| 22 | FIGS | 2026-02-27 | 152.3M | 09:00 | non-7am | -$1,103 |
| 23 | FJET | 2026-01-13 | 18.5M | 08:10 | non-7am | -$1,263 |
| 24 | FSLY | 2026-02-12 | 142.9M | 07:26 | non-7am | +$176 |
| 25 | HCTI | 2026-02-27 | 0.1M | 08:00 | non-7am | $0 |
| 26 | HOVR | 2026-01-14 | 29.4M | 09:30 | non-7am | $0 |
| 27 | HSDT | 2026-02-13 | 30.1M | 09:01 | non-7am | $0 |
| 28 | IBIO | 2026-01-06 | 27.1M | 07:46 | non-7am | -$1,444 |
| 29 | INDO | 2026-02-27 | 9.5M | 08:00 | non-7am | -$487 |
| 30 | JDZG | 2026-02-12 | 2.8M | 08:34 | non-7am | $0 |
| 31 | JFBR | 2026-01-16 | ? | 07:37 | unknown float | $0 |
| 32 | KORE | 2026-02-27 | 7.6M | 08:00 | non-7am | $0 |
| 33 | LBGJ | 2026-02-27 | 16.7M | 09:00 | non-7am | -$110 |
| 34 | MCRB | 2026-02-13 | 6.8M | 09:30 | non-7am | +$113 |
| 35 | MRM | 2026-02-27 | 5.8M | 08:00 | non-7am | -$1,562 |
| 36 | MTVA | 2026-01-15 | 1.0M | 09:30 | non-7am | $0 |
| 37 | NAMM | 2026-02-27 | 6.8M | 08:00 | non-7am | $0 |
| 38 | NCI | 2026-02-13 | 3.5M | 08:43 | non-7am | +$577 |
| 39 | NGNE | 2026-02-27 | 5.0M | 08:00 | non-7am | $0 |
| 40 | NVCR | 2026-02-12 | 94.3M | 09:22 | non-7am | -$507 |
| 41 | OCG | 2026-01-16 | 0.1M | 09:05 | non-7am | $0 |
| 42 | OCUL | 2026-01-15 | 215.5M | 07:00 | large-float | $0 |
| 43 | ONMD | 2026-02-27 | 16.4M | 08:30 | non-7am | -$2,146 |
| 44 | OSCR | 2026-02-10 | 249.5M | 07:00 | large-float | $0 |
| 45 | PBYI | 2026-02-27 | 38.9M | 09:30 | non-7am | +$21 |
| 46 | QMCO | 2026-01-15 | 14.4M | 08:31 | non-7am | -$1,193 |
| 47 | RBNE | 2026-02-27 | 2.2M | 08:00 | non-7am | $0 |
| 48 | RELY | 2026-02-19 | 173.5M | 07:00 | large-float | -$1,090 |
| 49 | RPD | 2026-02-11 | 57.9M | 09:30 | non-7am | -$186 |
| 50 | RUN | 2026-02-27 | 228.3M | 09:30 | non-7am | $0 |
| 51 | RVSN | 2026-02-11 | 1.8M | 07:34 | non-7am | -$1,010 |
| 52 | SHPH | 2026-01-09 | 1.6M | 08:04 | non-7am | -$1,033 |
| 53 | SMX | 2026-02-09 | ? | 07:00 | unknown float | $0 |
| 54 | SND | 2026-02-27 | 27.3M | 09:00 | non-7am | $0 |
| 55 | SPRC | 2026-01-13 | 0.4M | 07:02 | non-7am | $0 |
| 56 | STKH | 2026-01-16 | 660.0M | 07:14 | non-7am | -$697 |
| 57 | STRZ | 2026-02-27 | 16.7M | 08:00 | non-7am | +$94 |
| 58 | STSS | 2026-01-16 | 20.3M | 07:01 | non-7am | $0 |
| 59 | TMDE | 2026-02-27 | 3.6M | 08:00 | non-7am | -$707 |
| 60 | TSSI | 2026-02-27 | 21.8M | 08:00 | non-7am | -$1,116 |
| 61 | UPWK | 2026-02-10 | 121.5M | 09:28 | non-7am | -$540 |
| 62 | VOR | 2026-01-12 | 7.2M | 08:23 | non-7am | +$501 |
| 63 | WEN | 2026-02-13 | 145.5M | 09:30 | non-7am | -$660 |
| 64 | XWEL | 2026-02-27 | 4.3M | 08:30 | non-7am | -$2,949 |

---

## Batch Script

```bash
#!/bin/bash
# Full 137-Stock Profile System Backtest
# Run from repo root
# This runs ALL stocks with their assigned profile using Databento tick data

RESULTS_FILE="full_profile_backtest_results.csv"
echo "symbol,date,float_m,scanner_time,profile,baseline_pnl,profile_pnl,profile_trades,reason" > $RESULTS_FILE

run_profiled() {
    local sym=$1 date=$2 float=$3 scanner=$4 profile=$5 baseline=$6 reason=$7
    echo "=== $sym $date (Profile $profile) ==="
    
    OUT=$(python simulate.py $sym $date --profile $profile --ticks --feed databento --no-fundamentals 2>&1)
    PNL=$(echo "$OUT" | grep "Gross P&L" | sed 's/.*\$//;s/,.*//' | tr -d ' +')
    TRADES=$(echo "$OUT" | grep "Trades:" | head -1 | sed 's/.*Trades: //;s/ .*//')
    
    PNL=${PNL:-0}
    TRADES=${TRADES:-0}
    
    echo "  Profile $profile: \$$PNL ($TRADES trades) | Baseline: \$$baseline"
    echo "$sym,$date,$float,$scanner,$profile,$baseline,$PNL,$TRADES,$reason" >> $RESULTS_FILE
}

echo "============================================"
echo "  RUN 1 + 2: ALL 137 STOCKS WITH PROFILES"
echo "============================================"
echo ""

echo "--- PROFILE A: Micro-Float Pre-Market (57 stocks) ---"
run_profiled ACON 2026-01-06 0.7 "07:00" A 0 "micro-float_7am"
run_profiled ACON 2026-01-08 0.7 "07:00" A -2122 "micro-float_7am"
run_profiled ACON 2026-01-27 0.7 "07:00" A 0 "micro-float_7am"
run_profiled ACON 2026-02-13 0.7 "07:00" A -214 "micro-float_7am"
run_profiled APVO 2026-01-09 0.9 "07:00" A 7622 "micro-float_7am"
run_profiled APVO 2026-02-05 0.9 "07:00" A 0 "micro-float_7am"
run_profiled BCTX 2026-01-16 1.7 "07:00" A 0 "micro-float_7am"
run_profiled BCTX 2026-01-27 1.7 "07:00" A 0 "micro-float_7am"
run_profiled BDSX 2026-01-12 3.7 "07:00" A -45 "micro-float_7am"
run_profiled BNAI 2026-01-16 3.3 "07:00" A -674 "micro-float_7am"
run_profiled BNAI 2026-01-28 3.3 "07:00" A 5610 "micro-float_7am"
run_profiled BNAI 2026-02-05 3.3 "07:00" A 160 "micro-float_7am"
run_profiled ELAB 2026-01-06 0.2 "07:00" A 0 "micro-float_7am"
run_profiled ELAB 2026-01-08 0.2 "07:00" A 0 "micro-float_7am"
run_profiled ELAB 2026-01-09 0.2 "07:00" A 0 "micro-float_7am"
run_profiled ENVB 2026-02-19 0.5 "07:00" A 474 "micro-float_7am"
run_profiled FEED 2026-01-16 0.8 "07:00" A 0 "micro-float_7am"
run_profiled GRI 2026-01-27 1.4 "07:00" A 0 "micro-float_7am"
run_profiled GRI 2026-01-28 1.4 "07:00" A 0 "micro-float_7am"
run_profiled GWAV 2026-01-06 0.8 "07:00" A 0 "micro-float_7am"
run_profiled GWAV 2026-01-16 0.8 "07:00" A 6735 "micro-float_7am"
run_profiled GWAV 2026-02-05 0.8 "07:00" A 0 "micro-float_7am"
run_profiled GWAV 2026-02-13 0.8 "07:00" A 0 "micro-float_7am"
run_profiled HIND 2026-01-16 1.5 "07:00" A 0 "micro-float_7am"
run_profiled HIND 2026-01-27 1.5 "07:00" A 260 "micro-float_7am"
run_profiled HIND 2026-02-05 1.5 "07:00" A 0 "micro-float_7am"
run_profiled LCFY 2026-01-16 1.4 "07:00" A -627 "micro-float_7am"
run_profiled MLEC 2026-01-06 0.7 "07:00" A 0 "micro-float_7am"
run_profiled MLEC 2026-01-28 0.7 "07:00" A 0 "micro-float_7am"
run_profiled MLEC 2026-02-13 0.7 "07:00" A 173 "micro-float_7am"
run_profiled MNTS 2026-02-06 1.3 "07:00" A 862 "micro-float_7am"
run_profiled MOVE 2026-01-23 0.6 "07:00" A -156 "micro-float_7am"
run_profiled MOVE 2026-01-27 0.6 "07:00" A 5502 "micro-float_7am"
run_profiled PAVM 2026-01-16 0.7 "07:00" A 0 "micro-float_7am"
run_profiled PAVM 2026-01-21 0.7 "07:00" A 1586 "micro-float_7am"
run_profiled PAVM 2026-02-05 0.7 "07:00" A 0 "micro-float_7am"
run_profiled PMAX 2026-01-13 1.2 "07:00" A -1098 "micro-float_7am"
run_profiled ROLR 2026-01-06 3.6 "07:00" A -1422 "micro-float_7am"
run_profiled ROLR 2026-01-14 3.6 "07:00" A 1644 "micro-float_7am"
run_profiled ROLR 2026-01-16 3.6 "07:00" A -1228 "micro-float_7am"
run_profiled ROLR 2026-02-13 3.6 "07:00" A 0 "micro-float_7am"
run_profiled RVSN 2026-01-27 1.8 "07:00" A 0 "micro-float_7am"
run_profiled RVSN 2026-02-05 1.8 "07:00" A 0 "micro-float_7am"
run_profiled SHPH 2026-01-16 1.6 "07:00" A -1111 "micro-float_7am"
run_profiled SLE 2026-01-23 0.7 "07:00" A -390 "micro-float_7am"
run_profiled SLE 2026-01-27 0.7 "07:00" A 0 "micro-float_7am"
run_profiled SNSE 2026-01-28 0.7 "07:00" A 0 "micro-float_7am"
run_profiled SNSE 2026-02-05 0.7 "07:00" A 0 "micro-float_7am"
run_profiled SNSE 2026-02-18 0.7 "07:00" A -125 "micro-float_7am"
run_profiled SXTP 2026-01-27 0.9 "07:00" A -2078 "micro-float_7am"
run_profiled SXTP 2026-01-28 0.9 "07:00" A 0 "micro-float_7am"
run_profiled TNMG 2026-01-06 1.2 "07:00" A 0 "micro-float_7am"
run_profiled TNMG 2026-01-16 1.2 "07:00" A -481 "micro-float_7am"
run_profiled TWG 2026-01-20 0.5 "07:00" A 0 "micro-float_7am"
run_profiled VERO 2026-01-06 1.6 "07:00" A 0 "micro-float_7am"
run_profiled VERO 2026-01-16 1.6 "07:00" A 6890 "micro-float_7am"
run_profiled VERO 2026-02-05 1.6 "07:00" A 0 "micro-float_7am"

echo ""
echo "--- PROFILE B: Mid-Float L2-Assisted (16 stocks) ---"
run_profiled ANPA 2026-01-06 12.5 "07:00" B -2730 "mid-float_7am"
run_profiled ANPA 2026-01-09 12.5 "07:00" B 2088 "mid-float_7am"
run_profiled ANPA 2026-02-13 12.5 "07:00" B 0 "mid-float_7am"
run_profiled AZI 2026-01-09 44.5 "07:00" B 0 "mid-float_7am"
run_profiled AZI 2026-01-16 44.5 "07:00" B 0 "mid-float_7am"
run_profiled BATL 2026-02-18 7.2 "07:00" B -499 "mid-float_7am"
run_profiled BEEM 2026-01-14 18.0 "07:00" B -900 "mid-float_7am"
run_profiled FLYX 2026-01-06 5.7 "07:00" B 0 "mid-float_7am"
run_profiled FLYX 2026-01-08 5.7 "07:00" B 473 "mid-float_7am"
run_profiled FLYX 2026-01-27 5.7 "07:00" B 0 "mid-float_7am"
run_profiled FLYX 2026-02-13 5.7 "07:00" B 0 "mid-float_7am"
run_profiled IBIO 2026-01-08 27.1 "07:00" B 0 "mid-float_7am"
run_profiled IBIO 2026-01-09 27.1 "07:00" B -267 "mid-float_7am"
run_profiled OPTX 2026-01-06 6.0 "07:00" B -78 "mid-float_7am"
run_profiled OPTX 2026-01-08 6.0 "07:00" B -223 "mid-float_7am"
run_profiled OPTX 2026-01-09 6.0 "07:00" B -1479 "mid-float_7am"

echo ""
echo "--- PROFILE X: Everything Else (64 stocks) ---"
run_profiled AAOI 2026-02-18 72.0 "07:00" X -415 "large-float"
run_profiled AAOI 2026-02-27 72.0 "09:30" X -1950 "non-7am"
run_profiled ACCL 2026-01-16 2.9 "04:00" X -1072 "non-7am"
run_profiled AEVA 2026-02-27 26.7 "09:30" X 0 "non-7am"
run_profiled AGIG 2026-02-27 8.7 "08:00" X 0 "non-7am"
run_profiled AKAN 2026-01-12 0.1 "09:09" X 0 "non-7am"
run_profiled ALMS 2026-01-06 66.3 "07:00" X 3407 "large-float"
run_profiled ALMS 2026-01-09 66.3 "07:00" X -1154 "large-float"
run_profiled ALMS 2026-01-16 66.3 "07:00" X 0 "large-float"
run_profiled ALMS 2026-02-13 66.3 "07:00" X -236 "large-float"
run_profiled ANNA 2026-02-27 9.4 "08:30" X -1088 "non-7am"
run_profiled ARLO 2026-02-27 103.9 "09:20" X -692 "non-7am"
run_profiled ASBP 2026-02-11 2.3 "07:45" X 0 "non-7am"
run_profiled AUID 2026-01-15 11.8 "08:57" X -1683 "non-7am"
run_profiled AZI 2026-01-06 44.5 "07:27" X 783 "non-7am"
run_profiled AZI 2026-02-10 44.5 "07:15" X 0 "non-7am"
run_profiled BATL 2026-02-27 7.2 "08:00" X 1972 "non-7am"
run_profiled CDIO 2026-02-27 1.7 "09:45" X 791 "non-7am"
run_profiled CNVS 2026-02-13 15.0 "09:04" X -731 "non-7am"
run_profiled CRSR 2026-02-13 46.6 "08:41" X -1939 "non-7am"
run_profiled FEED 2026-01-09 0.8 "07:29" X 0 "non-7am"
run_profiled FIGS 2026-02-27 152.3 "09:00" X -1103 "non-7am"
run_profiled FJET 2026-01-13 18.5 "08:10" X -1263 "non-7am"
run_profiled FSLY 2026-02-12 142.9 "07:26" X 176 "non-7am"
run_profiled HCTI 2026-02-27 0.1 "08:00" X 0 "non-7am"
run_profiled HOVR 2026-01-14 29.4 "09:30" X 0 "non-7am"
run_profiled HSDT 2026-02-13 30.1 "09:01" X 0 "non-7am"
run_profiled IBIO 2026-01-06 27.1 "07:46" X -1444 "non-7am"
run_profiled INDO 2026-02-27 9.5 "08:00" X -487 "non-7am"
run_profiled JDZG 2026-02-12 2.8 "08:34" X 0 "non-7am"
run_profiled JFBR 2026-01-16 0 "07:37" X 0 "unknown_float"
run_profiled KORE 2026-02-27 7.6 "08:00" X 0 "non-7am"
run_profiled LBGJ 2026-02-27 16.7 "09:00" X -110 "non-7am"
run_profiled MCRB 2026-02-13 6.8 "09:30" X 113 "non-7am"
run_profiled MRM 2026-02-27 5.8 "08:00" X -1562 "non-7am"
run_profiled MTVA 2026-01-15 1.0 "09:30" X 0 "non-7am"
run_profiled NAMM 2026-02-27 6.8 "08:00" X 0 "non-7am"
run_profiled NCI 2026-02-13 3.5 "08:43" X 577 "non-7am"
run_profiled NGNE 2026-02-27 5.0 "08:00" X 0 "non-7am"
run_profiled NVCR 2026-02-12 94.3 "09:22" X -507 "non-7am"
run_profiled OCG 2026-01-16 0.1 "09:05" X 0 "non-7am"
run_profiled OCUL 2026-01-15 215.5 "07:00" X 0 "large-float"
run_profiled ONMD 2026-02-27 16.4 "08:30" X -2146 "non-7am"
run_profiled OSCR 2026-02-10 249.5 "07:00" X 0 "large-float"
run_profiled PBYI 2026-02-27 38.9 "09:30" X 21 "non-7am"
run_profiled QMCO 2026-01-15 14.4 "08:31" X -1193 "non-7am"
run_profiled RBNE 2026-02-27 2.2 "08:00" X 0 "non-7am"
run_profiled RELY 2026-02-19 173.5 "07:00" X -1090 "large-float"
run_profiled RPD 2026-02-11 57.9 "09:30" X -186 "non-7am"
run_profiled RUN 2026-02-27 228.3 "09:30" X 0 "non-7am"
run_profiled RVSN 2026-02-11 1.8 "07:34" X -1010 "non-7am"
run_profiled SHPH 2026-01-09 1.6 "08:04" X -1033 "non-7am"
run_profiled SMX 2026-02-09 0 "07:00" X 0 "unknown_float"
run_profiled SND 2026-02-27 27.3 "09:00" X 0 "non-7am"
run_profiled SPRC 2026-01-13 0.4 "07:02" X 0 "non-7am"
run_profiled STKH 2026-01-16 660.0 "07:14" X -697 "non-7am"
run_profiled STRZ 2026-02-27 16.7 "08:00" X 94 "non-7am"
run_profiled STSS 2026-01-16 20.3 "07:01" X 0 "non-7am"
run_profiled TMDE 2026-02-27 3.6 "08:00" X -707 "non-7am"
run_profiled TSSI 2026-02-27 21.8 "08:00" X -1116 "non-7am"
run_profiled UPWK 2026-02-10 121.5 "09:28" X -540 "non-7am"
run_profiled VOR 2026-01-12 7.2 "08:23" X 501 "non-7am"
run_profiled WEN 2026-02-13 145.5 "09:30" X -660 "non-7am"
run_profiled XWEL 2026-02-27 4.3 "08:30" X -2949 "non-7am"

echo ""
echo "=== FULL PROFILE BACKTEST COMPLETE ==="
echo "Results saved to: $RESULTS_FILE"
echo ""
echo "=== SUMMARY ==="
echo "Profile A stocks: $(grep ',A,' $RESULTS_FILE | wc -l)"
echo "Profile B stocks: $(grep ',B,' $RESULTS_FILE | wc -l)"
echo "Profile X stocks: $(grep ',X,' $RESULTS_FILE | wc -l)"
echo ""
echo "Profile A total P&L:"
grep ',A,' $RESULTS_FILE | awk -F',' '{sum+=$7} END {printf "$%d\n", sum}'
echo "Profile B total P&L:"
grep ',B,' $RESULTS_FILE | awk -F',' '{sum+=$7} END {printf "$%d\n", sum}'
echo "Profile X total P&L:"
grep ',X,' $RESULTS_FILE | awk -F',' '{sum+=$7} END {printf "$%d\n", sum}'
echo ""
echo "Run 1 (A+B only, skip X):"
grep -E ',A,|,B,' $RESULTS_FILE | awk -F',' '{sum+=$7} END {printf "$%d\n", sum}'
echo "Run 2 (A+B+X):"
awk -F',' 'NR>1 {sum+=$7} END {printf "$%d\n", sum}' $RESULTS_FILE
echo ""
echo "Baseline (all default, no profiles): -$196"
```

## Analysis — After Results

### 1. Total P&L Comparison
| Scenario | P&L | vs Baseline |
|----------|-----|-------------|
| Baseline (all default) | -$196 | — |
| Run 1: A + B only | ??? | ??? |
| Run 2: A + B + X | ??? | ??? |

### 2. Per-Profile Breakdown
- Profile A: P&L, win rate, avg winner, avg loser
- Profile B: P&L, L2 delta vs no-L2
- Profile X: P&L — is it net positive or negative?

### 3. Key Questions
- How much of the baseline's losses came from Profile X stocks?
- Does Databento tick data change any Profile A results vs the Alpaca baseline?
- Is Profile X worth deploying, or should we just skip those stocks?

### 4. January vs February
Break down by month to confirm the profile system works in both hot and cold markets.

## Success Criteria

The profile system is validated if:
- Run 1 (A+B) is significantly positive (>$10K improvement over baseline)
- Profile A Databento results match or improve on known Alpaca numbers
- Profile B shows the L2 improvement seen in validation
- The answer to "should we trade Profile X stocks?" is clear

## Important Notes

- Profile A uses the **same config as the original study** (no-L2, signal exits, max 2 entries) — so Profile A results should closely match the baseline no-L2 numbers for those stocks. Any differences are from Databento tick data vs Alpaca.
- Profile B results will differ because B enables L2, warmup gate, and max 3 entries.
- Profile X uses conservative settings — the question is whether conservative saves money vs the uncontrolled baseline.
- Write results to `FULL_PROFILE_BACKTEST_RESULTS.md` with the analysis.

---

*Directive created by Perplexity Computer — March 3, 2026, 9:35 AM MST*
*137 stocks, 3 profiles, 1 definitive answer*
