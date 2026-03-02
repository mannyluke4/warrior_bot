#!/bin/bash
# Scanner-Timed Backtest Study — 30 stocks
# Each stock starts from its scanner appearance time (or 07:00 if pre-7am)
# Config: Current .env (classifier ON, suppress OFF, exhaustion ON, warmup=5)

source venv/bin/activate

OUTDIR="/tmp/scanner_study_30"
mkdir -p "$OUTDIR"

echo "=== Scanner-Timed Backtest Study: 30 Stocks ==="
echo "Config: Current .env (classifier ON, suppress OFF, exhaustion ON, warmup=5)"
echo "Running all 30 in parallel..."
echo ""

run_sim() {
    local sym=$1 date=$2 start=$3
    python simulate.py "$sym" "$date" "$start" 12:00 --ticks > "$OUTDIR/${sym}_${date}.txt" 2>&1
}

# January 2026 (hot market) — 14 stocks
run_sim BDSX 2026-01-12 07:00 &
run_sim VOR  2026-01-12 08:23 &
run_sim AKAN 2026-01-12 09:09 &
run_sim PMAX 2026-01-13 07:00 &
run_sim SPRC 2026-01-13 07:02 &
run_sim FJET 2026-01-13 08:10 &
run_sim BEEM 2026-01-14 07:00 &
run_sim HOVR 2026-01-14 09:30 &
run_sim OCUL 2026-01-15 07:00 &
run_sim QMCO 2026-01-15 08:31 &
run_sim AUID 2026-01-15 08:57 &
run_sim MTVA 2026-01-15 09:30 &
run_sim JFBR 2026-01-16 07:37 &
run_sim OCG  2026-01-16 09:05 &

# February 2026 (cold market) — 16 stocks
run_sim SMX  2026-02-09 07:00 &
run_sim OSCR 2026-02-10 07:00 &
run_sim AZI  2026-02-10 07:15 &
run_sim UPWK 2026-02-10 09:28 &
run_sim RVSN 2026-02-11 07:34 &
run_sim ASBP 2026-02-11 07:45 &
run_sim RPD  2026-02-11 09:30 &
run_sim FSLY 2026-02-12 07:26 &
run_sim JDZG 2026-02-12 08:34 &
run_sim NVCR 2026-02-12 09:22 &
run_sim CRSR 2026-02-13 08:41 &
run_sim NCI  2026-02-13 08:43 &
run_sim HSDT 2026-02-13 09:01 &
run_sim CNVS 2026-02-13 09:04 &
run_sim MCRB 2026-02-13 09:30 &
run_sim WEN  2026-02-13 09:30 &

wait
echo "=== All 30 complete ==="
