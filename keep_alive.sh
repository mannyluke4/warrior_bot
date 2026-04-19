#!/bin/bash
# keep_alive.sh — Self-healing bot watchdog. Cron every 2 minutes.
#
# Checks: (1) Gateway port 4002 alive, (2) bot_v3_hybrid.py running.
# If Gateway is down: restart it via IBC, wait for port.
# If bot is down: restart it directly (NOT via daily_run_v3.sh).
#
# This replaces the old single-shot check_bot.sh with a proper
# auto-restart loop. The bot should NEVER stay down for more than
# ~2 minutes during trading hours.
#
# Cron line (add via `crontab -e`):
#   */2 4-20 * * 1-5 /bin/bash ~/warrior_bot_v2/keep_alive.sh
#
# That fires every 2 minutes, 4 AM - 8 PM MT, weekdays only.
# Outside those hours, the bot is expected to be down (no trading).

set -euo pipefail

LOG=~/warrior_bot_v2/logs/keep_alive_$(date +%Y-%m-%d).log
BOT_DIR=~/warrior_bot_v2
# Read IBKR_PORT from .env so it works for both paper (4002) and live (4001)
IBKR_PORT=$(grep "^IBKR_PORT=" ~/warrior_bot_v2/.env 2>/dev/null | cut -d= -f2 | tr -d ' ' || echo "4002")
BOT_SCRIPT="bot_v3_hybrid.py"
DAILY_LOG="$BOT_DIR/logs/$(date +%Y-%m-%d)_daily.log"

log() { echo "[$(date '+%H:%M:%S')] $1" >> "$LOG"; }

# ── Gateway check ──
GW_UP=false
if python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',$IBKR_PORT)); s.close()" 2>/dev/null; then
    GW_UP=true
fi

if [ "$GW_UP" = false ]; then
    log "⚠️ Gateway DOWN — starting IBC..."
    ~/ibc/gatewaystartmacos.sh -inline > /dev/null 2>&1 &
    # Wait up to 5 minutes for port
    for i in $(seq 1 60); do
        if python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',$IBKR_PORT)); s.close()" 2>/dev/null; then
            log "✅ Gateway UP after ~$((i*5))s"
            GW_UP=true
            break
        fi
        sleep 5
    done
    if [ "$GW_UP" = false ]; then
        log "❌ Gateway failed to start within 300s — giving up this cycle"
        exit 1
    fi
fi

# ── Bot check ──
if pgrep -f "$BOT_SCRIPT" > /dev/null 2>&1; then
    # Bot is running — nothing to do
    exit 0
fi

# Bot is down — restart it
log "⚠️ Bot DOWN — restarting..."

# Kill any stale daily_run_v3.sh watchdogs to prevent cascade kills
pkill -f "daily_run_v3.sh" 2>/dev/null || true
sleep 1

cd "$BOT_DIR"
source "$BOT_DIR/venv/bin/activate"
nohup python3 "$BOT_SCRIPT" >> "$DAILY_LOG" 2>&1 &
NEW_PID=$!
disown

# Quick health check
sleep 15
if kill -0 "$NEW_PID" 2>/dev/null; then
    log "✅ Bot restarted PID=$NEW_PID"
else
    log "❌ Bot failed to start (died within 15s)"
fi
