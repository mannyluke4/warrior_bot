#!/bin/bash
# Daily automated trading run — Warrior Bot V2 (IBKR)
# Triggered by cron: 0 2 * * 1-5 (2:00 AM MT, weekdays)

set -euo pipefail

LOG_DIR=~/warrior_bot_v2/logs
TODAY=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/${TODAY}_daily.log"
mkdir -p "$LOG_DIR"

exec > >(tee -a "$LOG_FILE") 2>&1

# Cleanup trap: push logs even if the script crashes
cleanup() {
    echo "=== TRAP: cleanup at $(date) ==="
    kill "$BOT_PID" 2>/dev/null || true
    pkill -f "bot_ibkr.py" 2>/dev/null || true
    kill "$CAFFEINE_PID" 2>/dev/null || true
    cd ~/warrior_bot_v2
    git add -f logs/ 2>/dev/null || true
    git commit -m "auto: daily logs ${TODAY}" 2>/dev/null || true
    git push origin v2-ibkr-migration 2>/dev/null || true
    echo "=== Cleanup complete: $(date) ==="
}
trap cleanup EXIT

BOT_PID=""

# Keep Mac awake for the entire trading session
caffeinate -dims -w $$ &
CAFFEINE_PID=$!
echo "caffeinate started (PID: $CAFFEINE_PID)"

echo "=== V2 Daily run started: $(date) ==="

# 1. Pull latest code
cd ~/warrior_bot_v2
git pull origin v2-ibkr-migration 2>&1 || echo "WARN: git pull failed"

# 2. Activate venv
source ~/warrior_bot_v2/venv/bin/activate

# 3. Pre-flight smoke test
echo "Pre-flight: checking Python imports..."
python3 -c "from ib_insync import IB; from squeeze_detector import SqueezeDetector; from ibkr_scanner import scan_premarket_live; print('V2 Imports OK')" || {
    echo "FATAL: Pre-flight import check failed. Aborting."
    exit 1
}

# 4. Start TWS via IBC (needed for IBKR API)
echo "Starting TWS via IBC..."
~/ibc/twsstartmacos.sh &
IBC_PID=$!
sleep 90  # TWS needs ~60-90s to fully log in
echo "TWS started (IBC PID: $IBC_PID)"

# 5. Kill any stale bot processes
echo "Cleaning up stale connections..."
pkill -f "bot_ibkr.py" 2>/dev/null || true
sleep 2

# 6. Start the V2 bot
echo "Starting bot_ibkr.py..."
cd ~/warrior_bot_v2
python3 bot_ibkr.py >> "$LOG_FILE" 2>&1 &
BOT_PID=$!
echo "Bot started (PID: $BOT_PID)"

# 7. Post-launch health check
sleep 15
if ! kill -0 "$BOT_PID" 2>/dev/null; then
    echo "FATAL: bot_ibkr.py crashed within 15s of launch. Check $LOG_FILE for details."
    exit 1
fi
echo "Bot health check passed (still running after 15s, PID: $BOT_PID)"

# 8. Watchdog loop: wait until 9:00 AM MT (11:00 AM ET)
TARGET_HOUR=9
TARGET_MIN=0
TARGET_EPOCH=$(date -j -v${TARGET_HOUR}H -v${TARGET_MIN}M -v0S +%s)

echo "Watchdog: monitoring bot until 9:00 AM MT ($(date -r $TARGET_EPOCH))..."
while true; do
    NOW_EPOCH=$(date +%s)
    if [ "$NOW_EPOCH" -ge "$TARGET_EPOCH" ]; then
        echo "Trading window closed. Proceeding to shutdown."
        break
    fi
    if ! kill -0 "$BOT_PID" 2>/dev/null; then
        echo "ALERT: bot_ibkr.py died at $(date)! Session ended early. Check $LOG_FILE."
        break
    fi
    sleep 60 || true
done

# 9. Shut down
echo "=== Shutting down at $(date) ==="
kill "$BOT_PID" 2>/dev/null || true
sleep 5
pkill -f "bot_ibkr.py" 2>/dev/null || true

# 10. Commit and push logs
echo "Pushing logs..."
cd ~/warrior_bot_v2
git add -f logs/ 2>/dev/null || true
git commit -m "auto: v2 daily logs ${TODAY}" 2>/dev/null || true
git push origin v2-ibkr-migration 2>/dev/null || echo "WARN: git push failed"

echo "=== V2 Daily run complete: $(date) ==="
