#!/bin/bash
# daily_run_engine.sh — Setup B (unified data engine) daily launcher.
#
# Per DIRECTIVE_UNIFIED_DATA_ENGINE_BUILD.md section "Phase 4: Daily
# Runner". Mirrors daily_run_v3.sh's wake/unlock/caffeinate/watchdog
# pattern but launches the engine + 2 thin bots instead of the dual
# Setup A bots. CRITICAL: this script must NEVER touch Setup A's files
# or processes — Setup A is sacred during the A/B period.
#
# Schedule (when ready): cron entry parallel to daily_run_v3.sh's
#   0 2 * * 1-5  ~/warrior_bot_v2_engine/daily_run_engine.sh
# (user adds the cron line manually after reviewing this script.)
#
# Failure policy: no auto-restart of engine or bots. If any of the 3
# processes dies, log and continue monitoring the rest until the
# trading window ends, then shut down cleanly. Manual investigation
# is the recovery path during A/B — we want failures visible in the
# data, not papered over.

set -euo pipefail

# ── CLI flag parsing ────────────────────────────────────────────────────
# The bots support --resume / --fresh; this launcher passes the same flag
# through to BOTH bots so cron can choose the boot mode at the launcher
# level. Usage:
#   ./daily_run_engine.sh            # default — bots auto-decide via marker
#   ./daily_run_engine.sh --resume   # force resume on both bots
#   ./daily_run_engine.sh --fresh    # force cold start on both bots
#
# Cron's primary call (02:00 MT) should be the default (no flag) so the
# bots auto-decide on whether a marker is present. Use --resume only for
# manual intra-day relaunches after a crash; use --fresh to deliberately
# wipe today's state before a re-test.
BOT_FLAG=""
case "${1:-}" in
    --resume|--fresh)
        BOT_FLAG="$1"
        ;;
    "")
        ;;
    *)
        echo "Usage: $0 [--resume | --fresh]"
        echo "  (no flag) — bots auto-decide via marker.json presence"
        echo "  --resume — force resume from today's marker"
        echo "  --fresh — force cold start (wipes session_state_engine/<date>/)"
        exit 64
        ;;
esac

# ── Paths ──────────────────────────────────────────────────────────────
# WORKTREE is this script's directory — kept self-contained so a copy
# of the worktree to another machine works without edits.
WORKTREE="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SETUP_A_REPO="$HOME/warrior_bot_v2"
LOG_DIR="$WORKTREE/logs"
TODAY=$(date +%Y-%m-%d)
ENGINE_LOG="$LOG_DIR/${TODAY}_engine.log"
SQUEEZE_LOG="$LOG_DIR/${TODAY}_squeeze_bot.log"
WB_LOG="$LOG_DIR/${TODAY}_wb_bot.log"
RUN_LOG="$LOG_DIR/${TODAY}_engine_run.log"
SOCKET_PATH="${ENGINE_IPC_SOCKET:-/tmp/warrior_engine.sock}"
IBKR_PORT=4002

mkdir -p "$LOG_DIR"

exec > >(tee -a "$RUN_LOG") 2>&1

# ── PIDs (declared early so the trap can reference safely under set -u) ─
ENGINE_PID=""
SQUEEZE_PID=""
WB_PID=""
CAFFEINE_PID=""

cleanup() {
    echo "=== TRAP: cleanup at $(date) ==="
    # SIGTERM the three processes; each one handles its own graceful
    # shutdown (engine broadcasts stream_paused before closing).
    for pid in "$SQUEEZE_PID" "$WB_PID" "$ENGINE_PID"; do
        [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
    done
    sleep 5
    # If anything is still alive, SIGKILL it.
    for pid in "$SQUEEZE_PID" "$WB_PID" "$ENGINE_PID"; do
        [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null || true
    done
    [ -n "$CAFFEINE_PID" ] && kill "$CAFFEINE_PID" 2>/dev/null || true
    # Best-effort socket cleanup.
    [ -e "$SOCKET_PATH" ] && rm -f "$SOCKET_PATH" 2>/dev/null || true

    # Push logs (commit to the worktree's branch — data-engine-unified).
    # Failure here must not crash the cleanup; logs surviving in the
    # worktree are still recoverable manually.
    cd "$WORKTREE"
    git add -f logs/ 2>/dev/null || true
    git commit -m "auto: engine daily logs ${TODAY}" 2>/dev/null || true
    git push origin data-engine-unified 2>/dev/null || \
        echo "WARN: git push origin data-engine-unified failed (non-fatal)"
    echo "=== Cleanup complete: $(date) ==="
}
trap cleanup EXIT

# ── Wake / unlock / caffeinate (same pattern as daily_run_v3.sh) ───────
echo "=== Setup B engine daily run started: $(date) ==="
echo "  Worktree: $WORKTREE"
echo "  Logs dir: $LOG_DIR"

caffeinate -u -t 60 &
sleep 5
caffeinate -dims -w $$ &
CAFFEINE_PID=$!
echo "Persistent caffeinate started (PID: $CAFFEINE_PID)"

# Pull the latest code (worktree's branch).
cd "$WORKTREE"
git pull origin data-engine-unified 2>&1 || echo "WARN: git pull failed"
CODE_SHA=$(git rev-parse --short HEAD)
echo "Code version: $CODE_SHA ($(git log -1 --format='%s'))"

# Activate the SHARED venv (Setup A's venv — we never install our own
# dependencies for Setup B; everything we need is already there).
if [ ! -d "$SETUP_A_REPO/venv" ]; then
    echo "FATAL: shared venv not found at $SETUP_A_REPO/venv — Setup A "
    echo "must be installed before Setup B can launch."
    exit 1
fi
# shellcheck disable=SC1091
source "$SETUP_A_REPO/venv/bin/activate"

# Pre-flight import smoke test.
echo "Pre-flight: imports..."
python3 -c "
import engine_ipc, data_engine, squeeze_bot, wb_bot, engine_bot_common
print('Setup B imports OK')
" || { echo "FATAL: import check failed"; exit 1; }

# Verify Alpaca creds are configured. Prefer .env.engine.local (gitignored
# secrets) over .env.engine (committed template with <FILL_IN> placeholders).
ENV_FILE="$WORKTREE/.env.engine.local"
[ -f "$ENV_FILE" ] || ENV_FILE="$WORKTREE/.env.engine"
if grep -E '^APCA_API_(KEY_ID|SECRET_KEY)=<' "$ENV_FILE" >/dev/null; then
    echo "FATAL: $ENV_FILE has placeholder Alpaca credentials. "
    echo "Create $WORKTREE/.env.engine.local (gitignored) with real PA-NEW keys."
    exit 1
fi

# Gateway readiness check. Setup A's daily_run_v3.sh is the canonical
# Gateway owner; if it ran first (cron alignment) the gateway is already
# up. We only verify the port is listening — we never start or restart
# the gateway here (touching Setup A's gateway = risk to Setup A).
echo "Checking IB Gateway on port $IBKR_PORT..."
GW_READY=0
for i in $(seq 1 36); do
    if python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',$IBKR_PORT)); s.close()" 2>/dev/null; then
        echo "Gateway is up on port $IBKR_PORT (after ~$((i*5))s)"
        GW_READY=1
        break
    fi
    echo "  attempt $i/36: Gateway port $IBKR_PORT not ready yet, waiting 5s..."
    sleep 5
done
if [ "$GW_READY" -eq 0 ]; then
    echo "FATAL: Gateway not up on port $IBKR_PORT after 180s. "
    echo "Setup A's daily_run_v3.sh is responsible for starting the Gateway. "
    echo "Did its cron entry run earlier? Aborting Setup B."
    exit 1
fi

# Clean any stale Setup B socket from a prior crash (cleanup trap removes
# on graceful exit; this defends against ungraceful exits).
[ -e "$SOCKET_PATH" ] && rm -f "$SOCKET_PATH" 2>/dev/null || true

# Also kill any stale Setup B processes (NOT Setup A — those names are
# different and we filter narrowly).
pkill -f "warrior_bot_v2_engine/data_engine.py"   2>/dev/null || true
pkill -f "warrior_bot_v2_engine/squeeze_bot.py"   2>/dev/null || true
pkill -f "warrior_bot_v2_engine/wb_bot.py"        2>/dev/null || true
sleep 2

# ── Launch engine first ────────────────────────────────────────────────
echo "Starting data_engine.py..."
cd "$WORKTREE"
python3 "$WORKTREE/data_engine.py" >> "$ENGINE_LOG" 2>&1 &
ENGINE_PID=$!
echo "Engine started (PID: $ENGINE_PID, log: $ENGINE_LOG)"

# Wait for the IPC socket to appear (engine creates it after IBKR
# connect succeeds + asyncio.start_unix_server fires).
echo "Waiting for IPC socket at $SOCKET_PATH..."
SOCKET_READY=0
for i in $(seq 1 30); do
    if [ -S "$SOCKET_PATH" ]; then
        echo "IPC socket is up (after ~${i}s)"
        SOCKET_READY=1
        break
    fi
    if ! kill -0 "$ENGINE_PID" 2>/dev/null; then
        echo "FATAL: engine died before socket appeared. See $ENGINE_LOG"
        exit 1
    fi
    sleep 1
done
if [ "$SOCKET_READY" -eq 0 ]; then
    echo "FATAL: socket $SOCKET_PATH did not appear within 30s. Engine may "
    echo "still be retrying IBKR connect. See $ENGINE_LOG"
    exit 1
fi

# ── Launch the 2 bots in parallel ──────────────────────────────────────
# Pass the same boot-mode flag to both bots so they observe the same
# session policy. With no flag, each bot auto-decides via its own
# session_state_engine/<date>/<bot_id>/marker.json.
if [ -n "$BOT_FLAG" ]; then
    echo "Boot flag: $BOT_FLAG (passed to both bots)"
fi
echo "Starting squeeze_bot.py${BOT_FLAG:+ $BOT_FLAG}..."
python3 "$WORKTREE/squeeze_bot.py" ${BOT_FLAG:+$BOT_FLAG} >> "$SQUEEZE_LOG" 2>&1 &
SQUEEZE_PID=$!
echo "Squeeze bot started (PID: $SQUEEZE_PID, log: $SQUEEZE_LOG)"

echo "Starting wb_bot.py${BOT_FLAG:+ $BOT_FLAG}..."
python3 "$WORKTREE/wb_bot.py" ${BOT_FLAG:+$BOT_FLAG} >> "$WB_LOG" 2>&1 &
WB_PID=$!
echo "WB bot started (PID: $WB_PID, log: $WB_LOG)"

# Health-check after 15s — same shape as daily_run_v3.sh.
sleep 15
for name_pid in "engine:$ENGINE_PID" "squeeze:$SQUEEZE_PID" "wb:$WB_PID"; do
    name="${name_pid%%:*}"
    pid="${name_pid##*:}"
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "WARN: $name (PID $pid) died within 15s of launch. See its log."
        # Don't abort the script — per directive, no auto-restart. We let
        # the survivors continue. Most useful failure mode is "engine ok,
        # one bot crashed" → other bot keeps producing data.
    else
        echo "$name OK (PID $pid)"
    fi
done

# ── Watchdog loop ──────────────────────────────────────────────────────
# Bots are session-aware via their detectors; we just block until the
# evening trading window closes (mirror daily_run_v3.sh's 18:05 MT /
# 20:05 ET target). No auto-restart per directive.
TARGET_HOUR=18
TARGET_MIN=5
TARGET_EPOCH=$(date -j -v${TARGET_HOUR}H -v${TARGET_MIN}M -v0S +%s)
echo "Watchdog: monitoring until $(date -r $TARGET_EPOCH)..."
while true; do
    NOW_EPOCH=$(date +%s)
    if [ "$NOW_EPOCH" -ge "$TARGET_EPOCH" ]; then
        echo "Trading windows closed. Proceeding to shutdown."
        break
    fi
    # Log liveness on each minute. If a process died, log loudly but
    # keep watching the rest (per failure-mode table in directive).
    if [ -n "$ENGINE_PID" ] && ! kill -0 "$ENGINE_PID" 2>/dev/null; then
        echo "ALERT: data_engine.py died at $(date). See $ENGINE_LOG."
        echo "       Bots will fail-CLOSED on socket close; no auto-restart per directive."
        ENGINE_PID=""
    fi
    if [ -n "$SQUEEZE_PID" ] && ! kill -0 "$SQUEEZE_PID" 2>/dev/null; then
        echo "ALERT: squeeze_bot.py died at $(date). See $SQUEEZE_LOG."
        SQUEEZE_PID=""
    fi
    if [ -n "$WB_PID" ] && ! kill -0 "$WB_PID" 2>/dev/null; then
        echo "ALERT: wb_bot.py died at $(date). See $WB_LOG."
        WB_PID=""
    fi
    # If everything is dead, no point continuing.
    if [ -z "$ENGINE_PID" ] && [ -z "$SQUEEZE_PID" ] && [ -z "$WB_PID" ]; then
        echo "All 3 processes are dead. Exiting watchdog."
        break
    fi
    sleep 60 || true
done

# ── Graceful shutdown (cleanup trap will SIGTERM if anything still alive) ──
echo "=== Setup B engine daily run complete: $(date) ==="
