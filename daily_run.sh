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
    kill "$CAFFEINE_PID" 2>/dev/null || true
    cd ~/warrior_bot
    git add -f logs/ 2>/dev/null || true
    git commit -m "auto: daily logs ${TODAY}" 2>/dev/null || true
    git push origin v6-dynamic-sizing 2>/dev/null || true
    echo "=== Cleanup complete: $(date) ==="
}
trap cleanup EXIT

BOT_PID=""
IBC_PID=""

# Keep Mac awake for the entire trading session
caffeinate -dims -w $$ &
CAFFEINE_PID=$!
echo "caffeinate started (PID: $CAFFEINE_PID)"

echo "=== Daily run started: $(date) ==="

# 1. Pull latest code
cd ~/warrior_bot
git pull origin v6-dynamic-sizing 2>&1 || echo "WARN: git pull failed"

# 2. Activate venv
source ~/warrior_bot/venv/bin/activate

# 2b. Pre-flight smoke test: verify critical imports work before committing to a full run.
# Catches ModuleNotFoundError (like the Friday 3/20 crash) in 3 lines.
echo "Pre-flight: checking Python imports..."
python3 -c "from market_scanner import MarketScanner; from trade_manager import PaperTradeManager; print('Imports OK')" || {
    echo "FATAL: Pre-flight import check failed. Aborting before TWS launch."
    exit 1
}

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

# 4b. Post-launch health check: verify bot is still alive 10 seconds after launch.
# Catches immediate startup crashes (e.g., Friday 3/20 ModuleNotFoundError).
sleep 10
if ! kill -0 "$BOT_PID" 2>/dev/null; then
    echo "FATAL: bot.py crashed within 10s of launch. Check $LOG_FILE for details."
    exit 1
fi
echo "Bot health check passed (still running after 10s, PID: $BOT_PID)"

# 5. Watchdog loop: wait until 9:00 AM MT, checking bot health every 60s.
# This replaces the single long sleep so we detect mid-session crashes promptly.
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
        echo "ALERT: bot.py died at $(date)! Session ended early. Check $LOG_FILE."
        break
    fi
    sleep 60 || true
done

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
