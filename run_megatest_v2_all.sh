#!/bin/bash
# Run all 4 v2 megatest combos sequentially
# Logs to megatest_results/megatest_{combo}_v2.log

set -euo pipefail
cd ~/warrior_bot
source venv/bin/activate

LOG_DIR="megatest_results"
COMBOS="mp_only sq_only mp_sq all_three"

for COMBO in $COMBOS; do
    LOG="$LOG_DIR/megatest_${COMBO}_v2.log"
    echo "$(date): Starting $COMBO → $LOG"
    python run_megatest.py $COMBO > "$LOG" 2>&1
    echo "$(date): $COMBO complete"
done

echo "$(date): All 4 combos complete"
