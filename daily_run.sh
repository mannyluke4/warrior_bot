#!/bin/bash
# Daily automated trading run — Mac Mini
# Triggered by cron: 0 2 * * 1-5 (2:00 AM MT, weekdays)

set -euo pipefail

LOG_DIR=~/warrior_bot/logs
TODAY=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/${TODAY}_daily.log"
mkdir -p "$LOG_DIR"

exec > >(tee -a "$LOG_FILE") 2>&1

# Cleanup trap: push logs even if the script crashes
cleanup() {
    echo "=== TRAP: cleanup at $(date) ==="
    kill "$BOT_PID" 2>/dev/null || true
    kill "$IBC_PID" 2>/dev/null || true
    pkill -f "bot.py" 2>/dev/null || true
    pkill -f "java.*tws" 2>/dev/null || true
    cd ~/warrior_bot
    git add -f logs/ 2>/dev/null || true
    git commit -m "auto: daily logs ${TODAY}" 2>/dev/null || true
    git push origin v6-dynamic-sizing 2>/dev/null || true
    echo "=== Cleanup complete: $(date) ==="
}
trap cleanup EXIT

BOT_PID=""
IBC_PID=""

echo "=== Daily run started: $(date) ==="

# 1. Pull latest code
cd ~/warrior_bot
git pull origin v6-dynamic-sizing 2>&1 || echo "WARN: git pull failed"

# 2. Activate venv
source ~/warrior_bot/venv/bin/activate

# 3. Start TWS via IBC (auto-login, wait for it to be ready)
echo "Starting TWS via IBC..."
~/ibc/twsstartmacos.sh &
IBC_PID=$!
sleep 90  # TWS needs ~60-90s to fully log in
echo "TWS started (IBC PID: $IBC_PID)"

# 4. Start the bot
echo "Starting bot..."
cd ~/warrior_bot
python3 bot.py >> "$LOG_FILE" 2>&1 &
BOT_PID=$!
echo "Bot started (PID: $BOT_PID)"

# 5. Wait until 9:00 AM MT (11:00 AM ET) — this is when trading window closes
# Calculate seconds until 9:00 AM MT using macOS (BSD) date
TARGET_HOUR=9
TARGET_MIN=0
NOW_EPOCH=$(date +%s)
TARGET_EPOCH=$(date -j -v${TARGET_HOUR}H -v${TARGET_MIN}M -v0S +%s)

if [ "$TARGET_EPOCH" -gt "$NOW_EPOCH" ]; then
    WAIT_SECS=$((TARGET_EPOCH - NOW_EPOCH))
    echo "Waiting ${WAIT_SECS}s until 9:00 AM MT..."
    sleep "$WAIT_SECS"
fi

# 6. Shut down
echo "=== Shutting down at $(date) ==="
kill "$BOT_PID" 2>/dev/null || true
sleep 5
kill "$IBC_PID" 2>/dev/null || true

# Force kill any lingering processes
pkill -f "bot.py" 2>/dev/null || true
pkill -f "java.*tws" 2>/dev/null || true

# 7. Commit and push logs
echo "Pushing logs..."
cd ~/warrior_bot
git add -f logs/ 2>/dev/null || true
git commit -m "auto: daily logs ${TODAY}" 2>/dev/null || true
git push origin v6-dynamic-sizing 2>/dev/null || echo "WARN: git push failed"

echo "=== Daily run complete: $(date) ==="
