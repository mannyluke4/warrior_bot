#!/bin/bash
# Daily automated trading run — Warrior Bot V3 (IBKR data + Alpaca execution)
# Triggered by cron: 0 2 * * 1-5 (2:00 AM MT, weekdays)

set -euo pipefail

LOG_DIR=~/warrior_bot_v2/logs
TODAY=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/${TODAY}_daily.log"
IBKR_PORT=4002  # Gateway paper (2026-04-28 — back to paper, no TV conflict per Manny)
mkdir -p "$LOG_DIR"

exec > >(tee -a "$LOG_FILE") 2>&1

# Cleanup trap: push logs even if the script crashes.
# IMPORTANT: kill only OUR PIDs, not `pkill -f` which matches ANY process
# with the same name — including a manually-restarted bot. The old pkill
# caused cascade kills every time we restarted the bot during a session
# (daily_run's watchdog detected the restart as a death, ran the trap,
# and pkill killed the fresh instance). Cost us multiple morning sessions.
cleanup() {
    echo "=== TRAP: cleanup at $(date) ==="
    [ -n "$BOT_PID" ] && kill "$BOT_PID" 2>/dev/null || true
    [ -n "$SUBBOT_PID" ] && kill "$SUBBOT_PID" 2>/dev/null || true
    [ -n "$SCANNER_PID" ] && kill "$SCANNER_PID" 2>/dev/null || true
    [ -n "$GW_WATCHDOG_PID" ] && kill "$GW_WATCHDOG_PID" 2>/dev/null || true
    [ -n "$CAFFEINE_PID" ] && kill "$CAFFEINE_PID" 2>/dev/null || true
    cd ~/warrior_bot_v2
    git add -f logs/ 2>/dev/null || true
    git commit -m "auto: v3 daily logs ${TODAY}" 2>/dev/null || true
    git push origin v2-ibkr-migration 2>/dev/null || true
    echo "=== Cleanup complete: $(date) ==="
}
trap cleanup EXIT

BOT_PID=""
SUBBOT_PID=""
SCANNER_PID=""
GW_WATCHDOG_PID=""
CAFFEINE_PID=""   # init early so cleanup trap can reference safely under set -u

# ── Step 0: Wake the display (no osascript, no keystroke) ────────────
# Per DIRECTIVE_AUTOSTART_PERMANENT_FIX.md (2026-04-28):
# osascript keystroke unlock fails silently when run from cron because
# cron has no GUI session / WindowServer connection. Replaced with
# caffeinate -u (acts as if user is active) which works headless.
# Lock screen disabled in System Settings (Layer 1) and auto-login
# enabled (Layer 2) handle the lock-state side; this script just wakes
# the display and pins it awake for the session.
echo "=== Waking screen ==="

# caffeinate -u: simulate user activity → wakes display, prevents sleep.
# -t 60: hold for 60s, long enough for the rest of startup.
caffeinate -u -t 60 &
echo "Display wake (caffeinate -u) sent"
sleep 5  # let display actually wake

# Verify wake worked. ioreg DevicePowerState: 4=on, 1=dim, 0=off.
# `|| true` defends against pipefail: on a headless Mac mini there may be
# no IODisplayWrangler at all, so grep returns 1 and the pipeline would
# blow up under `set -eo pipefail` before CAFFEINE_PID is initialized.
# 2026-04-29 fix — first cron run failed at this exact step.
DISPLAY_STATE=$(ioreg -n IODisplayWrangler -r -d 1 2>/dev/null \
    | grep -i "DevicePowerState" | awk '{print $NF}' | head -1 || true)
DISPLAY_STATE="${DISPLAY_STATE:-unknown}"
if [ "$DISPLAY_STATE" = "4" ]; then
    echo "Display ACTIVE (DevicePowerState=4)"
elif [ "$DISPLAY_STATE" = "1" ] || [ "$DISPLAY_STATE" = "0" ]; then
    echo "WARN: Display still in sleep state ($DISPLAY_STATE) — retrying wake"
    caffeinate -u -t 30 &
    sleep 5
else
    # No display detected (headless) or unknown state — caffeinate -u still
    # keeps the system awake even without a physical display.
    echo "Display state: $DISPLAY_STATE (continuing — caffeinate keeps system awake regardless)"
fi

# Persistent caffeinate for the entire session — keeps display + system
# awake until this shell exits. Linked to $$ so it dies with the script.
caffeinate -dims -w $$ &
CAFFEINE_PID=$!
echo "Persistent caffeinate started (PID: $CAFFEINE_PID)"

echo "=== V3 Hybrid daily run started: $(date) ==="

# 1. Pull latest code
cd ~/warrior_bot_v2
git pull origin v2-ibkr-migration 2>&1 || echo "WARN: git pull failed"
CODE_SHA=$(git rev-parse --short HEAD)
echo "Code version: $CODE_SHA ($(git log -1 --format='%s'))"
echo "daily_run_v3.sh hash: $(md5sum ~/warrior_bot_v2/daily_run_v3.sh 2>/dev/null || shasum ~/warrior_bot_v2/daily_run_v3.sh 2>/dev/null | cut -d' ' -f1 || echo 'n/a')"
echo "bot_v3_hybrid.py hash: $(md5sum ~/warrior_bot_v2/bot_v3_hybrid.py 2>/dev/null || shasum ~/warrior_bot_v2/bot_v3_hybrid.py 2>/dev/null | cut -d' ' -f1 || echo 'n/a')"
echo "bot_alpaca_subbot.py hash: $(md5sum ~/warrior_bot_v2/bot_alpaca_subbot.py 2>/dev/null || shasum ~/warrior_bot_v2/bot_alpaca_subbot.py 2>/dev/null | cut -d' ' -f1 || echo 'n/a')"
echo "alpaca_feed.py hash: $(md5sum ~/warrior_bot_v2/alpaca_feed.py 2>/dev/null || shasum ~/warrior_bot_v2/alpaca_feed.py 2>/dev/null | cut -d' ' -f1 || echo 'n/a')"

# 1b. NTP time sync — accurate bar timestamps depend on local clock
# NTP sync (non-sudo — sudo hangs in cron without a password)
sntp -S time.apple.com 2>&1 || echo "NTP sync skipped (non-root)"
echo "System time: $(date -u)"

# 2. Activate venv
source ~/warrior_bot_v2/venv/bin/activate

# 3. Pre-flight smoke test
echo "Pre-flight: checking Python imports..."
python3 -c "from ib_insync import IB; from squeeze_detector import SqueezeDetector; from ibkr_scanner import scan_premarket_live; from alpaca.trading.client import TradingClient; print('V3 Imports OK')" || {
    echo "FATAL: Pre-flight import check failed. Aborting."
    exit 1
}
# Sub-bot imports — non-fatal if these break, but log loudly so we know.
python3 -c "from alpaca_feed import AlpacaFeed, Stock; from broker import AlpacaBroker; print('Sub-bot Imports OK')" || {
    echo "WARN: Sub-bot import check failed — sub-bot will be skipped."
}

# 4. Kill any stale Gateway/TWS/Java/bot before starting fresh
echo "Killing stale processes..."
pkill -9 -f "bot_ibkr.py" 2>/dev/null || true
# 5. Reuse existing gateway if it's already authenticated. The pkill-and-
# restart pattern caused 2 AM cron failures: IBKR's server-side session
# from yesterday's gateway didn't clear in 5s after hard-kill, blocking
# the fresh login. If port $IBKR_PORT is already listening, the gateway
# is healthy — skip kill+restart entirely. New gateway only spawned when
# port is genuinely down.
if python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',$IBKR_PORT)); s.close()" 2>/dev/null; then
    echo "Gateway already up on port $IBKR_PORT — reusing existing session (no kill/restart)"
    IBC_PID=""
else
    echo "Gateway port $IBKR_PORT down — killing stale java and starting fresh..."
    pkill -9 -f "java.*ibgateway" 2>/dev/null || true
    pkill -9 -f "java.*IBGateway" 2>/dev/null || true
    pkill -9 -f "java.*tws" 2>/dev/null || true
    pkill -9 -f "java.*Jts" 2>/dev/null || true
    pkill -9 -f "java.*ibc" 2>/dev/null || true
    pkill -9 -f "java.*IBC" 2>/dev/null || true
    # 30s gives IBKR's server-side session time to clear after hard-kill,
    # avoiding "session already active" rejections on the fresh login.
    sleep 30
    if pgrep -f "java.*config.ini" > /dev/null 2>&1; then
        echo "WARNING: Java still alive, force killing all java..."
        pkill -9 -f "java" 2>/dev/null || true
        sleep 3
    fi
    echo "All stale processes cleared."
    echo "Starting IB Gateway via IBC..."
    ~/ibc/gatewaystartmacos.sh -inline &
    IBC_PID=$!
fi

# Wait for Gateway to open port 4002
# IBC + Gateway login takes ~3 minutes typically. Allow up to 6 minutes.
echo "Waiting for IB Gateway on port $IBKR_PORT..."
GW_READY=0
for i in $(seq 1 72); do
    if python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',$IBKR_PORT)); s.close()" 2>/dev/null; then
        echo "Gateway is up on port $IBKR_PORT (after ~$((i*5))s)"
        GW_READY=1
        break
    fi
    echo "  attempt $i/72: port $IBKR_PORT not ready yet, waiting 5s..."
    sleep 5
done

if [ "$GW_READY" -eq 0 ]; then
    echo "FATAL: IB Gateway did not open port $IBKR_PORT within 360 seconds. Aborting."
    exit 1
fi

# 6. Kill any stale bot processes
echo "Cleaning up stale connections..."
pkill -f "bot_v3_hybrid.py" 2>/dev/null || true
pkill -f "bot_alpaca_subbot.py" 2>/dev/null || true
sleep 2

# 6b. Start Databento live scanner (writes watchlist.txt for the bot)
echo "Starting live_scanner.py..."
cd ~/warrior_bot_v2
python3 live_scanner.py >> "$LOG_DIR/${TODAY}_scanner.log" 2>&1 &
SCANNER_PID=$!
echo "Live scanner started (PID: $SCANNER_PID)"
sleep 5

# 7. Start the V3 hybrid bot
echo "Starting bot_v3_hybrid.py..."
cd ~/warrior_bot_v2
python3 bot_v3_hybrid.py >> "$LOG_FILE" 2>&1 &
BOT_PID=$!
echo "Bot started (PID: $BOT_PID)"

# 8. Post-launch health check
sleep 15
if ! kill -0 "$BOT_PID" 2>/dev/null; then
    echo "FATAL: bot_v3_hybrid.py crashed within 15s of launch. Check $LOG_FILE for details."
    exit 1
fi
echo "Bot health check passed (still running after 15s, PID: $BOT_PID)"
echo "HEALTH_OK: Bot connected at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

# 8a. Start the Alpaca sub-bot in parallel (live A/B against IBKR data feed).
# Reads main bot's session_state/<today>/watchlist.json for symbol selection.
# Writes its own state to session_state_alpaca/ + tick_cache_alpaca/. Trades
# on a separate Alpaca paper account; main bot is unaffected.
# Failure here is NON-fatal — the main bot must keep running even if the
# sub-bot can't start.
SUBBOT_LOG="$LOG_DIR/${TODAY}_subbot_alpaca.log"
# Sub-bot configuration for tomorrow's Phase 1: WB solo on the sub-bot
# (squeeze stays on the main bot). The sub-bot's own startup forces
# WB_BROKER=alpaca, IBKR_CLIENT_ID=2, and the *_alpaca state dirs.
# Strategy gates we override here at launch:
#   WB_SQUEEZE_ENABLED=0           — sub-bot does not run squeeze (main does)
#   WB_WAVE_BREAKOUT_ENABLED=1     — sub-bot runs WB Phase 1 paper validation
# To change tomorrow's split, edit these two lines.
echo "Starting bot_alpaca_subbot.py (IBKR data + Alpaca exec; WB Phase 1 paper)..."
WB_SQUEEZE_ENABLED=0 WB_WAVE_BREAKOUT_ENABLED=1 \
  python3 bot_alpaca_subbot.py >> "$SUBBOT_LOG" 2>&1 &
SUBBOT_PID=$!
echo "Sub-bot started (PID: $SUBBOT_PID, log: $SUBBOT_LOG)"

# Sub-bot health check — non-fatal (don't abort the session if it fails).
sleep 15
if ! kill -0 "$SUBBOT_PID" 2>/dev/null; then
    echo "WARN: bot_alpaca_subbot.py crashed within 15s — continuing without sub-bot."
    echo "      See $SUBBOT_LOG for details."
    SUBBOT_PID=""
else
    echo "Sub-bot health check passed (still running after 15s, PID: $SUBBOT_PID)"
fi

# 8b. Gateway watchdog — detect if Gateway port drops during session
(
    while true; do
        sleep 60
        if ! python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',$IBKR_PORT)); s.close()" 2>/dev/null; then
            echo "WARNING: Gateway port $IBKR_PORT dropped at $(date -u '+%Y-%m-%d %H:%M:%S UTC')" >> "$LOG_DIR/gateway_watchdog.log"
            echo "WARNING: Gateway port $IBKR_PORT dropped at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
        fi
    done
) &
GW_WATCHDOG_PID=$!
echo "Gateway watchdog started (PID: $GW_WATCHDOG_PID)"

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
        echo "ALERT: bot_v3_hybrid.py died at $(date)! Session ended early. Check $LOG_FILE."
        break
    fi
    # Sub-bot is non-critical — log if it dies but keep watching the main bot.
    if [ -n "$SUBBOT_PID" ] && ! kill -0 "$SUBBOT_PID" 2>/dev/null; then
        echo "WARN: bot_alpaca_subbot.py died at $(date). Main bot continuing alone."
        SUBBOT_PID=""
    fi
    sleep 60 || true
done

# 10. Shut down
echo "=== Shutting down at $(date) ==="
kill "$BOT_PID" 2>/dev/null || true
[ -n "$SUBBOT_PID" ] && kill "$SUBBOT_PID" 2>/dev/null || true
sleep 5
pkill -f "bot_v3_hybrid.py" 2>/dev/null || true
pkill -f "bot_alpaca_subbot.py" 2>/dev/null || true

# 11. Commit and push logs
echo "Pushing logs..."
cd ~/warrior_bot_v2
git add -f logs/ 2>/dev/null || true
git commit -m "auto: v3 daily logs ${TODAY}" 2>/dev/null || true
git push origin v2-ibkr-migration 2>/dev/null || echo "WARN: git push failed"

echo "=== V3 Hybrid daily run complete: $(date) ==="
