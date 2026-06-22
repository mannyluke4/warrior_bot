#!/bin/bash
# Clean mid-session relaunch of sub-bots A and C ONLY (never re-run daily_run_v3.sh
# mid-session — it stacks duplicate stacks). Mirrors the launch_subbot env block in
# daily_run_v3.sh verbatim. Use after a sub-bot code change. Sub-bots must be FLAT.
set -u
cd ~/warrior_bot_v2
source ~/warrior_bot_v2/venv/bin/activate
LOG_DIR=~/warrior_bot_v2/logs
TODAY=$(date +%Y-%m-%d)

echo "Killing existing sub-bots..."
pkill -9 -f move_strike_subbot.py 2>/dev/null || true
sleep 2

VARIANT_C_KEY=$(grep "^VARIANT_C_APCA_API_KEY_ID=" ~/warrior_bot_v2/.env | cut -d'=' -f2 | tr -d ' ')
VARIANT_C_SECRET=$(grep "^VARIANT_C_APCA_API_SECRET_KEY=" ~/warrior_bot_v2/.env | cut -d'=' -f2 | tr -d ' ')
A_KEY=$(grep "^APCA_API_KEY_ID=" ~/warrior_bot_v2/.env | cut -d'=' -f2 | tr -d ' ')
A_SECRET=$(grep "^APCA_API_SECRET_KEY=" ~/warrior_bot_v2/.env | cut -d'=' -f2 | tr -d ' ')

launch_subbot() {
    local suffix="$1" apca_key="$2" apca_secret="$3" fade_extra="$4"
    local log_path="$LOG_DIR/${TODAY}_move_strike_subbot_${suffix}.log"
    echo "Relaunching sub-bot variant $suffix (log: $log_path)..."
    if [ -z "$apca_key" ] || [ -z "$apca_secret" ]; then
        echo "WARN: variant $suffix has no API keys — skipping."; return 0
    fi
    # shellcheck disable=SC2086
    env \
        WB_BT_MOVE_STRIKE=1 WB_BT_MOVE_HWM_EXIT=1 WB_BT_MOVE_LOOKBACK=5 WB_BT_MOVE_MULT=2.0 \
        WB_BT_MOVE_STOP_LOOKBACK=10 WB_BT_MOVE_CHASE_PCT=2.0 WB_BT_MOVE_HWM_DRAWDOWN_PCT=0.25 \
        WB_BT_MOVE_HWM_WIDE_DD_PCT=0.50 WB_BT_MOVE_HWM_HH_THRESHOLD=2 WB_BT_MOVE_HWM_MIN_GAIN_PCT=2.0 \
        WB_BT_MOVE_HWM_STOP_PROX_PCT=25 WB_BT_MOVE_HWM_NOACT_MIN=30 WB_BT_MOVE_REENTRY_GREEN=1 \
        WB_BT_MOVE_REENTRY_LOOKBACK=10 WB_BT_MOVE_REENTRY_WINDOW_MIN=30 WB_BT_MOVE_REENTRY_MAX_PER_SYM=1 \
        WB_BT_MOVE_REENTRY_BLOCK_SAME_BAR=1 WB_BT_MOVE_STAY_ARMED=1 WB_BT_MOVE_STAY_ARMED_COOLDOWN_MIN=15 \
        WB_BT_MOVE_STAY_ARMED_MIN_GAP_PCT=2.0 WB_BT_MOVE_MAX_BELOW_ARM_PCT=3.0 WB_SUBBOT_RISK_DOLLARS=1000 \
        WB_EOD_FORCE_FLATTEN_ENABLED=1 WB_ORPHAN_HARD_STOP_ENABLED=1 WB_REGIME_SHIFT_ENABLED=1 \
        WB_REGIME_SHIFT_RATIO_THRESHOLD=4.0 WB_REGIME_SHIFT_BASELINE_BARS=5 WB_REGIME_SHIFT_TARGET_R=1.5 \
        WB_REGIME_SHIFT_PARTIAL_PCT=0.9 WB_REGIME_SHIFT_REQUIRE_ARMED=1 WB_REGIME_SHIFT_REQUIRE_GREEN_BAR=1 \
        WB_REGIME_SHIFT_RUNNER_STOP_TO_BE=1 WB_REGIME_SHIFT_MAX_PER_SYMBOL=1 WB_SUBBOT_EQUITY_PCT=0.70 \
        WB_ENTRY_BLOCK_WINDOWS_ET=09:30-11:00,13:00-14:00 WB_SYMBOL_LOSS_LOCKOUT=1 \
        WB_SUBBOT_LOG_SUFFIX="$suffix" WB_SUBBOT_APCA_API_KEY_ID="$apca_key" \
        WB_SUBBOT_APCA_API_SECRET_KEY="$apca_secret" WB_BAR_STREAM_LOG_ENABLED=1 \
        WB_BAR_STREAM_LABEL="subbot_$suffix" $fade_extra \
        python3 move_strike_subbot.py >> "$log_path" 2>&1 &
    echo "  variant $suffix PID: $!"
}

launch_subbot A "$A_KEY" "$A_SECRET" "WB_MOVE_FIRESTORM_GATE_ENABLED=1 WB_MOVE_FIRESTORM_GATE_MIN_TICKS_PER_MIN=6000"
launch_subbot C "$VARIANT_C_KEY" "$VARIANT_C_SECRET" "WB_MOVE_REENTRY_LOSS_GATE_ENABLED=1 WB_MOVE_REENTRY_LOSS_GATE_WINDOW_MIN=30"
sleep 10
echo "--- running sub-bots ---"
ps aux | grep move_strike_subbot.py | grep -v grep | awk '{print "  PID", $2}'
