#!/bin/bash
# run_tuning_battery.sh — Run all 47 tuning tests
# Usage: bash run_tuning_battery.sh 2>&1 | tee tuning_results/battery.log

cd ~/warrior_bot_v2
source venv/bin/activate
mkdir -p tuning_results backtest_status

BASE="--start 2026-01-02 --end 2026-04-02 --equity 30000 --scale-notional"
PARALLEL=4
PIDS=()

run_test() {
    local id="$1"
    local label="$2"
    shift 2
    echo "[$(date +%H:%M:%S)] START $id: $label [$@]"
    eval "$@ python run_backtest_v2.py $BASE --label '${id}_${label}' --status-file 'tuning_${id}.md'" \
        > "tuning_results/${id}.log" 2>&1 &
    PIDS+=($!)
    if [ ${#PIDS[@]} -ge $PARALLEL ]; then
        wait "${PIDS[0]}" 2>/dev/null || true
        PIDS=("${PIDS[@]:1}")
    fi
}

wait_all() {
    for pid in "${PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
    PIDS=()
}

echo "============================================================"
echo "  TUNING BATTERY: 47 tests, $PARALLEL parallel"
echo "  $(date)"
echo "============================================================"

# BASELINE
run_test B00 BASELINE
wait_all

# PART 1: Entry (10)
echo "--- ENTRY SENSITIVITY ---"
run_test I01 VOL_MULT_2.5 WB_SQ_VOL_MULT=2.5
run_test I02 VOL_MULT_3.5 WB_SQ_VOL_MULT=3.5
run_test I03 PRIME_2 WB_SQ_PRIME_BARS=2
run_test I04 PRIME_4 WB_SQ_PRIME_BARS=4
wait_all
run_test I05 BODY_1.0 WB_SQ_MIN_BODY_PCT=1.0
run_test I06 BODY_2.0 WB_SQ_MIN_BODY_PCT=2.0
run_test I07 PARA_0.15 WB_SQ_PARA_STOP_OFFSET=0.15
run_test I08 PARA_0.20 WB_SQ_PARA_STOP_OFFSET=0.20
wait_all
run_test I09 ATTEMPTS_4 WB_SQ_MAX_ATTEMPTS=4
run_test I10 ATTEMPTS_5 WB_SQ_MAX_ATTEMPTS=5
wait_all

# PART 1: Exit (13)
echo "--- EXIT OPTIMIZATION ---"
run_test I11 TARGET_1.5 WB_SQ_TARGET_R=1.5
run_test I12 TARGET_2.5 WB_SQ_TARGET_R=2.5
run_test I13 TARGET_3.0 WB_SQ_TARGET_R=3.0
run_test I14 CORE_50 WB_SQ_CORE_PCT=50
wait_all
run_test I15 CORE_60 WB_SQ_CORE_PCT=60
run_test I16 CORE_90 WB_SQ_CORE_PCT=90
run_test I17 TRAIL_1.0 WB_SQ_TRAIL_R=1.0
run_test I18 TRAIL_2.0 WB_SQ_TRAIL_R=2.0
wait_all
run_test I19 RUNNER_2.0 WB_SQ_RUNNER_TRAIL_R=2.0
run_test I20 RUNNER_3.0 WB_SQ_RUNNER_TRAIL_R=3.0
run_test I21 BAIL_3 WB_BAIL_TIMER_MINUTES=3
run_test I22 BAIL_7 WB_BAIL_TIMER_MINUTES=7
wait_all
run_test I23 BAIL_OFF WB_BAIL_TIMER_ENABLED=0
wait_all

# PART 1: Risk (6)
echo "--- RISK MANAGEMENT ---"
run_test I24 LOSS_5K WB_BT_DAILY_LOSS_LIMIT=-5000
run_test I25 LOSS_SCALE WB_BT_DAILY_LOSS_SCALE=1
run_test I26 CONSEC_2 WB_MAX_CONSECUTIVE_LOSSES=2
run_test I27 CONSEC_5 WB_MAX_CONSECUTIVE_LOSSES=5
wait_all
run_test I28 RISK_3.0 WB_BT_RISK_PCT=0.030
run_test I29 RISK_3.5 WB_BT_RISK_PCT=0.035
wait_all

# PART 2: Exit Combos (6)
echo "--- EXIT COMBOS ---"
run_test C01 EXIT_CONSERVATIVE WB_SQ_TARGET_R=1.5 WB_SQ_CORE_PCT=90
run_test C02 EXIT_AGGRESSIVE WB_SQ_TARGET_R=2.5 WB_SQ_CORE_PCT=50
run_test C03 EXIT_QUICK_LOCK WB_SQ_TARGET_R=1.5 WB_SQ_TRAIL_R=1.0
run_test C04 EXIT_LET_IT_RUN WB_SQ_TARGET_R=2.5 WB_SQ_TRAIL_R=2.0 WB_SQ_RUNNER_TRAIL_R=3.0
wait_all
run_test C05 EXIT_BIG_RUNNER WB_SQ_CORE_PCT=50 WB_SQ_RUNNER_TRAIL_R=2.0
run_test C06 EXIT_MEGA_RUNNER WB_SQ_CORE_PCT=50 WB_SQ_RUNNER_TRAIL_R=3.5
wait_all

# PART 2: Entry Combos (4)
echo "--- ENTRY COMBOS ---"
run_test C07 ENTRY_LOOSE WB_SQ_VOL_MULT=2.5 WB_SQ_PARA_STOP_OFFSET=0.15
run_test C08 ENTRY_FASTEST WB_SQ_VOL_MULT=2.5 WB_SQ_PRIME_BARS=2
run_test C09 ENTRY_STRICT WB_SQ_VOL_MULT=3.5 WB_SQ_MIN_BODY_PCT=2.0
run_test C10 ENTRY_PERSISTENT WB_SQ_MAX_ATTEMPTS=5 WB_BAIL_TIMER_MINUTES=3
wait_all

# PART 2: Risk Combos (3)
echo "--- RISK COMBOS ---"
run_test C11 RISK_SIZE_UP WB_BT_RISK_PCT=0.030 WB_BT_DAILY_LOSS_LIMIT=-5000
run_test C12 RISK_SCALE_UP WB_BT_RISK_PCT=0.030 WB_BT_DAILY_LOSS_SCALE=1
run_test C13 RISK_BIG_TIGHT WB_BT_RISK_PCT=0.035 WB_MAX_CONSECUTIVE_LOSSES=2
wait_all

# PART 2: Cross-Category (5)
echo "--- CROSS-CATEGORY COMBOS ---"
run_test C14 CROSS_BASE_HIT WB_SQ_VOL_MULT=2.5 WB_SQ_TARGET_R=1.5 WB_SQ_CORE_PCT=90
run_test C15 CROSS_CASCADE WB_SQ_VOL_MULT=2.5 WB_SQ_TARGET_R=2.5 WB_SQ_CORE_PCT=50 WB_SQ_RUNNER_TRAIL_R=3.0
run_test C16 CROSS_QUICK_BIG WB_BT_RISK_PCT=0.030 WB_SQ_TARGET_R=1.5 WB_SQ_TRAIL_R=1.0
run_test C17 CROSS_MAX_RIDE WB_BT_RISK_PCT=0.030 WB_SQ_TARGET_R=2.5 WB_SQ_TRAIL_R=2.0 WB_SQ_RUNNER_TRAIL_R=3.0 WB_BT_DAILY_LOSS_SCALE=1
wait_all
run_test C18 CROSS_BBGI_FIX WB_SQ_VOL_MULT=2.5 WB_SQ_PARA_STOP_OFFSET=0.20 WB_SQ_MAX_ATTEMPTS=4 WB_SQ_TARGET_R=1.5
wait_all

echo ""
echo "============================================================"
echo "  BATTERY COMPLETE: $(date)"
echo "============================================================"
echo ""

# Collect and rank results
echo "--- LEADERBOARD ---"
echo ""
printf "%-6s %-25s %12s %8s %6s\n" "ID" "Label" "P&L" "Trades" "WR"
echo "--------------------------------------------------------------"
for f in tuning_results/[BIC]*.log; do
    id=$(basename "$f" .log)
    pnl=$(grep "P&L:" "$f" 2>/dev/null | tail -1 | sed 's/.*P&L: \$\([^ ]*\).*/\1/' || echo "???")
    trades=$(grep "Trades:" "$f" 2>/dev/null | tail -1 | sed 's/.*Trades: \([0-9]*\).*/\1/' || echo "?")
    wr=$(grep "WR:" "$f" 2>/dev/null | tail -1 | sed 's/.*WR: \([^ ]*\).*/\1/' || echo "?")
    label=$(grep "FINAL:" "$f" 2>/dev/null | tail -1 | sed 's/.*FINAL: //' || echo "$id")
    printf "%-6s %-25s %12s %8s %6s\n" "$id" "$label" "$pnl" "$trades" "$wr"
done | sort -t'$' -k3 -rn
