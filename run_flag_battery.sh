#!/bin/bash
# Stage-2 flag battery: YTD backtest with one Class-A flag flipped per run.
# Baseline: $30K → $209,807 (squeeze-only, 2026-01-02 → 2026-04-30).

set -u

cd ~/warrior_bot_v2 || exit 1
source venv/bin/activate

OUT_DIR="logs/flag_battery_$(date +%Y%m%d_%H%M)"
mkdir -p "$OUT_DIR"
SUMMARY="$OUT_DIR/SUMMARY.md"

START_DATE="2026-01-02"
END_DATE="2026-04-30"
START_EQ="30000"

BASELINE_FINAL="209807"

# Flag definitions: "FLAG_NAME=VALUE  short_label"
# For ON-by-default flags we test flipping OFF (e.g. SEED_GATE_ENABLED=0).
FLAGS=(
  "WB_LEVEL_MAP_ENABLED=1                   level_map_on"
  "WB_SQ_RUNNER_DETECT_ENABLED=1            runner_detect_on"
  "WB_SQ_DYNAMIC_ATTEMPTS_ENABLED=1         dynamic_attempts_on"
  "WB_SQ_PARTIAL_EXIT_ENABLED=1             partial_exit_on"
  "WB_SEED_GATE_ENABLED=0                   seed_gate_off"
  "WB_SQ_SEED_STALE_GATE_ENABLED=0          stale_gate_off"
  "WB_SQ_WIDE_TRAIL_ENABLED=1               wide_trail_on"
  "WB_3TRANCHE_ENABLED=1                    3tranche_on"
  "WB_VOL_FLOOR_ENABLED=1                   vol_floor_on"
  "WB_PARABOLIC_REGIME_ENABLED=1            parabolic_regime_on"
)

{
  echo "# Stage-2 Flag Battery — $(date)"
  echo ""
  echo "Baseline (no overrides): \$30K → \$$BASELINE_FINAL (+599.4%)"
  echo "Window: $START_DATE → $END_DATE, squeeze-only"
  echo ""
  echo "| Flag | Setting | Final Equity | Δ vs Baseline | Trades | WR | Log |"
  echo "|------|---------|--------------|---------------|--------|-----|-----|"
} > "$SUMMARY"

for entry in "${FLAGS[@]}"; do
  # Split the entry on whitespace
  read -r flag_kv label <<< "$entry"
  flag_name="${flag_kv%%=*}"
  flag_val="${flag_kv##*=}"

  log_file="$OUT_DIR/${label}.log"
  start_ts=$(date +%s)
  echo "[$(date '+%H:%M:%S')] Starting: $flag_kv ($label)"

  env "$flag_kv" python3 -u run_ytd_backtest.py \
    --start "$START_DATE" --end "$END_DATE" \
    --squeeze-only --start-equity "$START_EQ" \
    > "$log_file" 2>&1

  rc=$?
  elapsed=$(( $(date +%s) - start_ts ))

  # Parse the final summary block
  final_eq=$(grep -E "EQUITY:" "$log_file" | tail -1 | grep -oE '\$[0-9,]+\s*\(' | head -1 | tr -d '$,( ')
  trades=$(grep -E "^SQUEEZE:" "$log_file" | tail -1 | grep -oE '[0-9]+ trades' | grep -oE '[0-9]+')
  wr=$(grep -E "^SQUEEZE:" "$log_file" | tail -1 | grep -oE '\([0-9]+% WR\)' | grep -oE '[0-9]+')

  if [ -z "$final_eq" ]; then
    final_eq="ERR"
    delta="—"
  else
    delta=$(( final_eq - BASELINE_FINAL ))
    if [ "$delta" -ge 0 ]; then delta="+$delta"; fi
  fi

  echo "[$(date '+%H:%M:%S')] Done: $label → eq=\$${final_eq:-ERR} (Δ$delta) [${elapsed}s, rc=$rc]"
  echo "| \`$flag_name\` | $flag_val | \$${final_eq:-ERR} | $delta | ${trades:-?} | ${wr:-?}% | [log](${label}.log) |" >> "$SUMMARY"
done

echo "" >> "$SUMMARY"
echo "Battery complete: $(date)" >> "$SUMMARY"
echo ""
echo "=== ALL DONE ==="
echo "Summary: $SUMMARY"
cat "$SUMMARY"
