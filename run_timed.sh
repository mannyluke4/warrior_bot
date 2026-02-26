#!/bin/bash
# run_timed.sh — Launch warrior bot with caffeinate + auto-shutdown
#
# Usage:  ./run_timed.sh              (defaults to 12:00 ET shutdown)
#         ./run_timed.sh 11:30        (custom shutdown time, ET)

set -e
cd "$(dirname "$0")"

# --- Config ---
SHUTDOWN_ET="${1:-12:00}"   # Default: 12:00 PM Eastern
LOGFILE="bot_session_$(date +%Y%m%d_%H%M%S).log"

echo "========================================"
echo "  WARRIOR BOT — TIMED SESSION"
echo "========================================"
echo "  Shutdown time:  ${SHUTDOWN_ET} ET"
echo "  Log file:       ${LOGFILE}"
echo "  Mode:           $(grep WB_MODE .env | cut -d= -f2)"
echo "========================================"

# --- Calculate seconds until shutdown ---
# Convert shutdown time to today's date in ET, then to epoch
SHUTDOWN_EPOCH=$(TZ="America/New_York" date -j -f "%Y-%m-%d %H:%M" "$(TZ='America/New_York' date +%Y-%m-%d) ${SHUTDOWN_ET}" +%s 2>/dev/null)
NOW_EPOCH=$(date +%s)
SECONDS_LEFT=$((SHUTDOWN_EPOCH - NOW_EPOCH))

if [ "$SECONDS_LEFT" -le 0 ]; then
    echo "ERROR: Shutdown time ${SHUTDOWN_ET} ET has already passed today."
    exit 1
fi

HOURS=$((SECONDS_LEFT / 3600))
MINS=$(( (SECONDS_LEFT % 3600) / 60 ))
echo "  Time until shutdown: ${HOURS}h ${MINS}m"
echo "========================================"
echo ""

# --- Start caffeinate (prevent sleep) ---
caffeinate -i -w $$ &
CAFE_PID=$!
echo "Caffeinate started (PID: ${CAFE_PID})"

# --- Cleanup function ---
cleanup() {
    echo ""
    echo "[$(TZ='America/New_York' date '+%H:%M:%S ET')] Shutting down..."

    # Kill the bot process
    if [ -n "$BOT_PID" ] && kill -0 "$BOT_PID" 2>/dev/null; then
        kill "$BOT_PID" 2>/dev/null
        wait "$BOT_PID" 2>/dev/null
        echo "Bot stopped (PID: ${BOT_PID})"
    fi

    # Kill caffeinate
    if kill -0 "$CAFE_PID" 2>/dev/null; then
        kill "$CAFE_PID" 2>/dev/null
        echo "Caffeinate stopped"
    fi

    echo "Session ended. Log saved to: ${LOGFILE}"
    exit 0
}

trap cleanup EXIT INT TERM

# --- Start the bot ---
echo "[$(TZ='America/New_York' date '+%H:%M:%S ET')] Starting bot..."
source venv/bin/activate
python bot.py 2>&1 | tee "$LOGFILE" &
BOT_PID=$!
echo "Bot started (PID: ${BOT_PID})"
echo ""

# --- Wait until shutdown time ---
sleep "$SECONDS_LEFT" &
TIMER_PID=$!
wait "$TIMER_PID" 2>/dev/null

echo ""
echo "========================================"
echo "  SCHEDULED SHUTDOWN: ${SHUTDOWN_ET} ET"
echo "========================================"
cleanup
