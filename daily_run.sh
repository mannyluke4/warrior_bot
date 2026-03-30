#!/bin/bash
# Daily automated trading run — Warrior Bot V2 (IBKR Gateway)
# Triggered by cron: 0 2 * * 1-5 (2:00 AM MT, weekdays)

set -euo pipefail

LOG_DIR=~/warrior_bot_v2/logs
TODAY=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/${TODAY}_daily.log"
IBKR_PORT=4002  # Gateway paper trading port
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

# ── Step 0: Wake the screen and ensure active desktop ────────────────
# IB Gateway needs a display context. Wake the Mac, unlock if needed.
echo "=== Waking screen and ensuring active desktop ==="

# 1. Force wake the display
caffeinate -u -t 30 &
WAKE_PID=$!
echo "Display wake signal sent"
sleep 3

# 2. Send escape key + click to dismiss screensaver/lock screen
# Requires: System Settings → Privacy & Security → Accessibility → add cron/bash/osascript
osascript -e 'tell application "System Events" to key code 53' 2>/dev/null || true
sleep 2

# 3. Type password to unlock (password in ~/.mac_unlock_pw, chmod 600)
if [ -f ~/.mac_unlock_pw ]; then
    MAC_PW=$(cat ~/.mac_unlock_pw)
    osascript -e "tell application \"System Events\"
        keystroke \"${MAC_PW}\"
        delay 1
        keystroke return
    end tell" 2>/dev/null || echo "WARN: keystroke failed — check Accessibility permissions"
else
    echo "WARN: ~/.mac_unlock_pw not found"
    echo "  Create: echo 'yourpassword' > ~/.mac_unlock_pw && chmod 600 ~/.mac_unlock_pw"
fi

echo "Waiting 10s for desktop session..."
sleep 10

# 4. Verify display is active
if osascript -e 'tell application "Finder" to activate' 2>/dev/null; then
    echo "Desktop session: ACTIVE"
else
    echo "WARN: Desktop may not be active — Gateway might fail"
fi

kill $WAKE_PID 2>/dev/null || true

# Keep Mac awake for the entire trading session
caffeinate -dims -w $$ &
CAFFEINE_PID=$!
echo "caffeinate started (PID: $CAFFEINE_PID)"

echo "=== V2 Daily run started: $(date) ==="

# 1. Pull latest code
cd ~/warrior_bot_v2
git pull origin v2-ibkr-migration 2>&1 || echo "WARN: git pull failed"
CODE_SHA=$(git rev-parse --short HEAD)
echo "Code version: $CODE_SHA ($(git log -1 --format='%s'))"
echo "daily_run.sh hash: $(md5 -q ~/warrior_bot_v2/daily_run.sh)"
echo "bot_ibkr.py hash: $(md5 -q ~/warrior_bot_v2/bot_ibkr.py)"

# 1b. NTP time sync — accurate bar timestamps depend on local clock
# NTP sync (non-sudo — sudo hangs in cron without a password)
sntp -S time.apple.com 2>&1 || echo "NTP sync skipped (non-root)"
echo "System time: $(date -u)"

# 2. Activate venv
source ~/warrior_bot_v2/venv/bin/activate

# 3. Pre-flight smoke test
echo "Pre-flight: checking Python imports..."
python3 -c "from ib_insync import IB; from squeeze_detector import SqueezeDetector; from ibkr_scanner import scan_premarket_live; print('V2 Imports OK')" || {
    echo "FATAL: Pre-flight import check failed. Aborting."
    exit 1
}

# 4. Kill any stale Gateway/TWS/Java/bot before starting fresh
echo "Killing stale processes..."
pkill -9 -f "bot_ibkr.py" 2>/dev/null || true
pkill -9 -f "java.*ibgateway" 2>/dev/null || true
pkill -9 -f "java.*IBGateway" 2>/dev/null || true
pkill -9 -f "java.*tws" 2>/dev/null || true
pkill -9 -f "java.*Jts" 2>/dev/null || true
pkill -9 -f "java.*ibc" 2>/dev/null || true
pkill -9 -f "java.*IBC" 2>/dev/null || true
sleep 5
# Verify Java is truly dead (IBC uses pgrep to check)
if pgrep -f "java.*config.ini" > /dev/null 2>&1; then
    echo "WARNING: Java still alive, force killing all java..."
    pkill -9 -f "java" 2>/dev/null || true
    sleep 3
fi
echo "All stale processes cleared."

# 5. Start IB Gateway via IBC (headless — no GUI, no AppleScript dependency)
echo "Starting IB Gateway via IBC..."
~/ibc/gatewaystartmacos.sh -inline &
IBC_PID=$!

# Wait for Gateway to open port 4002
echo "Waiting for IB Gateway on port $IBKR_PORT..."
GW_READY=0
for i in $(seq 1 36); do
    if python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',$IBKR_PORT)); s.close()" 2>/dev/null; then
        echo "Gateway is up on port $IBKR_PORT (after ~$((i*5))s)"
        GW_READY=1
        break
    fi
    echo "  attempt $i/36: port $IBKR_PORT not ready yet, waiting 5s..."
    sleep 5
done

if [ "$GW_READY" -eq 0 ]; then
    echo "FATAL: IB Gateway did not open port $IBKR_PORT within 180 seconds. Aborting."
    exit 1
fi

# 6. Kill any stale bot processes
echo "Cleaning up stale connections..."
pkill -f "bot_ibkr.py" 2>/dev/null || true
sleep 2

# 7. Start the V2 bot
echo "Starting bot_ibkr.py..."
cd ~/warrior_bot_v2
python3 bot_ibkr.py >> "$LOG_FILE" 2>&1 &
BOT_PID=$!
echo "Bot started (PID: $BOT_PID)"

# 8. Post-launch health check
sleep 15
if ! kill -0 "$BOT_PID" 2>/dev/null; then
    echo "FATAL: bot_ibkr.py crashed within 15s of launch. Check $LOG_FILE for details."
    exit 1
fi
echo "Bot health check passed (still running after 15s, PID: $BOT_PID)"

# 9. Watchdog loop: wait until 6:05 PM MT (8:05 PM ET) — 5 min after evening window closes
# Bot handles its own dual-window schedule (morning 7-12 ET, evening 4-8 PM ET)
# and sleeps during the dead zone automatically. Watchdog just ensures it stays alive.
TARGET_HOUR=18
TARGET_MIN=5
TARGET_EPOCH=$(date -j -v${TARGET_HOUR}H -v${TARGET_MIN}M -v0S +%s)

echo "Watchdog: monitoring bot until 6:05 PM MT / 8:05 PM ET ($(date -r $TARGET_EPOCH))..."
echo "  Bot runs: morning 7:00-12:00 ET, sleeps 12:00-16:00, evening 16:00-20:00 ET"
while true; do
    NOW_EPOCH=$(date +%s)
    if [ "$NOW_EPOCH" -ge "$TARGET_EPOCH" ]; then
        echo "All trading windows closed. Proceeding to shutdown."
        break
    fi
    if ! kill -0 "$BOT_PID" 2>/dev/null; then
        echo "ALERT: bot_ibkr.py died at $(date)! Session ended early. Check $LOG_FILE."
        break
    fi
    sleep 60 || true
done

# 10. Shut down
echo "=== Shutting down at $(date) ==="
kill "$BOT_PID" 2>/dev/null || true
sleep 5
pkill -f "bot_ibkr.py" 2>/dev/null || true

# 11. Commit and push logs
echo "Pushing logs..."
cd ~/warrior_bot_v2
git add -f logs/ 2>/dev/null || true
git commit -m "auto: v2 daily logs ${TODAY}" 2>/dev/null || true
git push origin v2-ibkr-migration 2>/dev/null || echo "WARN: git push failed"

echo "=== V2 Daily run complete: $(date) ==="
