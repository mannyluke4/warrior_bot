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
    # A/B/C sub-bot variants (2026-05-23+)
    [ -n "$SUBBOT_PID_A" ] && kill "$SUBBOT_PID_A" 2>/dev/null || true
    [ -n "$SUBBOT_PID_B" ] && kill "$SUBBOT_PID_B" 2>/dev/null || true
    [ -n "$SUBBOT_PID_C" ] && kill "$SUBBOT_PID_C" 2>/dev/null || true
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
SUBBOT_PID_A=""
SUBBOT_PID_B=""
SUBBOT_PID_C=""
SCANNER_PID=""
GW_WATCHDOG_PID=""
CAFFEINE_PID=""   # init early so cleanup trap can reference safely under set -u

# DEGRADED MODE toggle (IBKR market-data outage, ~2026-07 window). Read from
# .env so the 2 AM cron picks it up. When =1, launch_main_bot runs
# watchlist_publisher.py (IBKR-free Databento watchlist for the manual bot)
# instead of the tick-blind main bot, and the sub-bots are skipped. The
# Databento scanner still runs and writes watchlist.txt. Set/clear it with a
# single line in .env: WB_ENGINE_DATA_DEGRADED=1  (default 0 = normal).
WB_ENGINE_DATA_DEGRADED=$(grep "^WB_ENGINE_DATA_DEGRADED=" ~/warrior_bot_v2/.env 2>/dev/null | tail -1 | cut -d'=' -f2 | tr -d ' "' )
export WB_ENGINE_DATA_DEGRADED
[ "${WB_ENGINE_DATA_DEGRADED:-0}" = "1" ] && echo "=== WB_ENGINE_DATA_DEGRADED=1 — DEGRADED (watchlist-only) startup ==="

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

# Float-forward scanner ranking (V2) — LIVE 2026-06-22 per Manny. Surfaces low-float
# (2x clean-day) names to the top of the watchlist that feeds the engine + manual bot.
# Also set =1 in .env (the robust source for load_dotenv consumers); exported here so
# any child that skips .env still inherits it. YTD-validated; see scanner_rank.py.
export WB_SCANNER_RANK_V2=1

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

# 6a-bis. Wipe yesterday's watchlist.txt before scanner runs.
# Defense for H#17 (watchlist freshness 2026-05-13). The bot's
# poll_watchlist() also mtime-checks the file, but actively truncating it
# at boot ensures: (1) scanner's first write becomes today's authoritative
# list, (2) if scanner fails (Databento outage, etc.), the file stays
# empty rather than inheriting yesterday's symbols, (3) no edge cases
# around mtime/timezone/clock drift on the mtime check.
echo "Wiping yesterday's watchlist.txt for a fresh session..."
: > ~/warrior_bot_v2/watchlist.txt

# 6b. Start the scanner (writes watchlist.txt). Normal = Databento
# live_scanner.py; DEGRADED (IBKR outage) = alpaca_scanner.py, because the
# real source (ibkr_scanner) is down AND the Databento EQUS.MINI live feed
# delivers ~0 volume (see project_ibkr_outage_degraded_watchlist). The Alpaca
# scanner filters on gap%+price (reliable on IEX) instead of volume.
cd ~/warrior_bot_v2
if [ "${WB_ENGINE_DATA_DEGRADED:-0}" = "1" ]; then
    echo "Starting alpaca_scanner.py (DEGRADED — Alpaca gapper scan)..."
    python3 alpaca_scanner.py >> "$LOG_DIR/${TODAY}_alpaca_scanner.log" 2>&1 &
    SCANNER_PID=$!
    echo "Alpaca scanner started (PID: $SCANNER_PID)"
else
    echo "Starting live_scanner.py..."
    python3 live_scanner.py >> "$LOG_DIR/${TODAY}_scanner.log" 2>&1 &
    SCANNER_PID=$!
    echo "Live scanner started (PID: $SCANNER_PID)"
fi
sleep 5

# 7. Start the V3 hybrid bot
# 2026-05-26: main bot routes orders to IBKR paper (port 4002) via
# WB_BROKER=ibkr. This frees the MAIN_APCA Alpaca account to host
# Variant B of the live A/B/C fade-gate test (see launch_subbot B below)
# while keeping the main bot's squeeze strategy running in parallel.
# Replaces the 2026-05-23 escape hatch (WB_SQUEEZE_ENABLED=0). The
# Alpaca creds are still injected because state.alpaca is constructed at
# startup regardless of backend; order flow goes through state.broker
# (IBKRBroker) per bot_v3_hybrid.py:4842.
# .env is not sourced by this script (the bot uses load_dotenv internally),
# so extract the main-bot keys inline for the env-var injection below.
MAIN_APCA_KEY=$(grep "^MAIN_APCA_API_KEY_ID=" ~/warrior_bot_v2/.env | cut -d'=' -f2 | tr -d ' ')
MAIN_APCA_SECRET=$(grep "^MAIN_APCA_API_SECRET_KEY=" ~/warrior_bot_v2/.env | cut -d'=' -f2 | tr -d ' ')
if [ -z "$MAIN_APCA_KEY" ] || [ -z "$MAIN_APCA_SECRET" ]; then
    echo "FATAL: MAIN_APCA_API_KEY_ID / MAIN_APCA_API_SECRET_KEY missing from .env"
    exit 1
fi
echo "Starting bot_v3_hybrid.py (IBKR paper execution — squeeze re-enabled 2026-05-26)..."
cd ~/warrior_bot_v2
# launch_main_bot: (re)start bot_v3_hybrid.py and capture its PID into BOT_PID.
# Factored into a function 2026-06-02 so the watchdog can auto-restart the main
# bot IN PLACE rather than tearing down the whole stack (sub-bots included) when
# it dies. See the watchdog loop below (WB_MAIN_BOT_AUTORESTART).
#
# WB_TICK_LEVEL_ARM=1 — tick-level arming live as of 2026-05-19 per Manny's
# call. Backtest shows -53% vs $290K baseline, but backtest assumes fills at arm
# price (doesn't reflect live gap-up reality). Flag-OFF behavior preserved
# bit-identical in code; flip back by editing this line or env-override.
# WB_SCALE_NOTIONAL + WB_BUYING_POWER_PCT (2026-05-28): cap order notional at 85%
# of IBKR AvailableFunds (non-marginable small-caps need ~100% initial margin).
# WB_SUB_WATCHDOG_ENABLED=1: IBKR Tier-2 subscription-wedge observability (2026-05-26).
launch_main_bot() {
    cd ~/warrior_bot_v2
    # DEGRADED MODE (IBKR market-data outage, ~2026-07 window): the main bot
    # is tick-blind and would kill-loop. Run the IBKR-free watchlist_publisher
    # on the engine socket instead, so the manual bot still gets a Databento
    # watchlist + %chg/float/RVOL/ATH. The scanner (Databento) still runs above
    # and writes watchlist.txt; sub-bots are skipped below. This branch also
    # covers the watchdog's auto-restart (it calls launch_main_bot). Flip
    # WB_ENGINE_DATA_DEGRADED=1 (env/.env) to enable; default 0 = normal.
    if [ "${WB_ENGINE_DATA_DEGRADED:-0}" = "1" ]; then
        echo "=== DEGRADED MODE: launching watchlist_publisher.py (no main bot / no sub-bots) ==="
        WB_ENGINE_PUBLISH_ENABLED=1 \
        WB_ENGINE_TCP_PORT=9710 \
        WB_ENGINE_TCP_BIND=100.79.224.76 \
          python3 watchlist_publisher.py \
            >> "$LOG_DIR/${TODAY}_watchlist_publisher.log" 2>&1 &
        BOT_PID=$!
        return
    fi
    APCA_API_KEY_ID="$MAIN_APCA_KEY" \
    APCA_API_SECRET_KEY="$MAIN_APCA_SECRET" \
    WB_BROKER=ibkr \
    WB_EXPECTED_BROKER=ibkr \
    WB_TICK_LEVEL_ARM=1 \
    WB_ENGINE_PUBLISH_ENABLED=1 \
    WB_ENGINE_TCP_PORT=9710 \
    WB_ENGINE_TCP_BIND=100.79.224.76 \
    WB_SUB_WATCHDOG_ENABLED=1 \
    WB_BAR_STREAM_LOG_ENABLED=1 \
    WB_BAR_STREAM_LABEL=main_bot \
    WB_SCALE_NOTIONAL=1 \
    WB_BUYING_POWER_PCT=0.85 \
    WB_EQUITY_PCT=0.70 \
    WB_ENTRY_BLOCK_WINDOWS_ET=09:30-11:00,13:00-14:00 \
    WB_SYMBOL_LOSS_LOCKOUT=1 \
      python3 bot_v3_hybrid.py >> "$LOG_FILE" 2>&1 &
    BOT_PID=$!
}
launch_main_bot
echo "Bot started (PID: $BOT_PID)"

# 8. Post-launch health check
sleep 15
if ! kill -0 "$BOT_PID" 2>/dev/null; then
    echo "FATAL: bot_v3_hybrid.py crashed within 15s of launch. Check $LOG_FILE for details."
    exit 1
fi
echo "Bot health check passed (still running after 15s, PID: $BOT_PID)"
echo "HEALTH_OK: Bot connected at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

# 8a. Setup B sub-bot — MOVE_STRIKE + HWM v6 (2026-05-20 deploy).
#
# Architecture (no more Databento, no second IBKR session):
#   Main bot publishes ticks via engine_publisher.py (Unix socket).
#   This sub-bot connects as consumer, sees the SAME tick stream the main
#   bot processes. Sub-bot runs MOVE_STRIKE entry + HWM exit v6 on the
#   existing sub-bot Alpaca paper account (the original APCA_API_* keys
#   in .env — main bot uses MAIN_APCA_API_* via the override above).
#
# Strategy (validated in 10-day backtest, +$618 net):
#   - Entry: movement-anomaly trigger (intra-bar body > 2× rolling avg)
#   - Stop:  consolidation low of last 10 closed bars (cons_stop)
#   - Exit:  HWM trail 25% (widens to 50% on 2+ HHs), stop-prox bail at
#            25% of R, 30-min noact backstop, hard stop
#   - Risk:  $1000/trade, 50% probe sizing
#
# Failure here is NON-FATAL — main bot keeps running even if sub-bot
# can't start (engine_publisher just has no consumer).
# ════════════════════════════════════════════════════════════════════
# 8a. Live A/B/C Fade-Gate Test (2026-05-23 deploy, ends ~2026-06-17).
# Per cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md.
#
# Three parallel sub-bot processes, each connected to the engine socket
# (multi-reader) and authenticated to its OWN Alpaca paper account.
# Same code, same strategy stack — only the fade-gate config differs.
#
#   Variant A (control):  regime-shift ON, no fade-gate
#   Variant B (V1 VWAP):  regime-shift ON, VWAP fade-gate
#   Variant C (V4 BodyCV): regime-shift ON, body-CV fade-gate
#
# 3-4 weeks of live paper data settles V1 vs V4 (YTD said V1, Stage-1
# said V4, $100K disagreement). Real-money go-live pushed 6/04 → 6/22.
#
# Account assignment — keys come from .env:
#   A → APCA_API_KEY_ID / APCA_API_SECRET_KEY
#       (original sub-bot account, account PA3700N6RNS2)
#   B → MAIN_APCA_API_KEY_ID / MAIN_APCA_API_SECRET_KEY
#       (main bot's Alpaca, account PA3TP2ZON4MF — main bot's squeeze
#        is paused for the duration so this account is free)
#   C → VARIANT_C_APCA_API_KEY_ID / VARIANT_C_APCA_API_SECRET_KEY
#       (new account, keys provided 2026-05-23+)
# ════════════════════════════════════════════════════════════════════

# Extract variant C keys from .env (variants A and B use existing keys).
VARIANT_C_KEY=$(grep "^VARIANT_C_APCA_API_KEY_ID=" ~/warrior_bot_v2/.env | cut -d'=' -f2 | tr -d ' ')
VARIANT_C_SECRET=$(grep "^VARIANT_C_APCA_API_SECRET_KEY=" ~/warrior_bot_v2/.env | cut -d'=' -f2 | tr -d ' ')
A_KEY=$(grep "^APCA_API_KEY_ID=" ~/warrior_bot_v2/.env | cut -d'=' -f2 | tr -d ' ')
A_SECRET=$(grep "^APCA_API_SECRET_KEY=" ~/warrior_bot_v2/.env | cut -d'=' -f2 | tr -d ' ')

# Shared MOVE_STRIKE + HWM + regime-shift env block. The only thing
# that varies across variants is the fade-gate vars (added per-launch).
# Exported here so each `env ... python` invocation inherits.
launch_subbot() {
    local suffix="$1"
    local apca_key="$2"
    local apca_secret="$3"
    local fade_extra="$4"
    local log_path="$LOG_DIR/${TODAY}_move_strike_subbot_${suffix}.log"
    echo "Starting sub-bot variant $suffix (log: $log_path)..."
    if [ -z "$apca_key" ] || [ -z "$apca_secret" ]; then
        echo "WARN: variant $suffix has no API keys in .env — skipping launch."
        return 0
    fi
    # shellcheck disable=SC2086  # fade_extra intentionally splits
    env \
        WB_BT_MOVE_STRIKE=1 \
        WB_BT_MOVE_HWM_EXIT=1 \
        WB_BT_MOVE_LOOKBACK=5 \
        WB_BT_MOVE_MULT=2.0 \
        WB_BT_MOVE_STOP_LOOKBACK=10 \
        WB_BT_MOVE_CHASE_PCT=2.0 \
        WB_BT_MOVE_HWM_DRAWDOWN_PCT=0.25 \
        WB_BT_MOVE_HWM_WIDE_DD_PCT=0.50 \
        WB_BT_MOVE_HWM_HH_THRESHOLD=2 \
        WB_BT_MOVE_HWM_MIN_GAIN_PCT=2.0 \
        WB_BT_MOVE_HWM_STOP_PROX_PCT=25 \
        WB_BT_MOVE_HWM_NOACT_MIN=30 \
        WB_BT_MOVE_REENTRY_GREEN=1 \
        WB_BT_MOVE_REENTRY_LOOKBACK=10 \
        WB_BT_MOVE_REENTRY_WINDOW_MIN=30 \
        WB_BT_MOVE_REENTRY_MAX_PER_SYM=1 \
        WB_BT_MOVE_REENTRY_BLOCK_SAME_BAR=1 \
        WB_BT_MOVE_STAY_ARMED=1 \
        WB_BT_MOVE_STAY_ARMED_COOLDOWN_MIN=15 \
        WB_BT_MOVE_STAY_ARMED_MIN_GAP_PCT=2.0 \
        WB_BT_MOVE_MAX_BELOW_ARM_PCT=3.0 \
        WB_SUBBOT_RISK_DOLLARS=1000 \
        WB_EOD_FORCE_FLATTEN_ENABLED=1 \
        WB_ORPHAN_HARD_STOP_ENABLED=1 \
        WB_REGIME_SHIFT_ENABLED=1 \
        WB_REGIME_SHIFT_RATIO_THRESHOLD=4.0 \
        WB_REGIME_SHIFT_BASELINE_BARS=5 \
        WB_REGIME_SHIFT_TARGET_R=1.5 \
        WB_REGIME_SHIFT_PARTIAL_PCT=0.9 \
        WB_REGIME_SHIFT_REQUIRE_ARMED=1 \
        WB_REGIME_SHIFT_REQUIRE_GREEN_BAR=1 \
        WB_REGIME_SHIFT_RUNNER_STOP_TO_BE=1 \
        WB_REGIME_SHIFT_MAX_PER_SYMBOL=1 \
        WB_REGIME_SHIFT_PULLBACK_ENTRY=1 \
        WB_REGIME_SHIFT_PULLBACK_MAX_BARS=10 \
        WB_SUBBOT_EQUITY_PCT=0.70 \
        WB_ENTRY_BLOCK_WINDOWS_ET=09:30-11:00,13:00-14:00 \
        WB_SYMBOL_LOSS_LOCKOUT=1 \
        WB_SUBBOT_LOG_SUFFIX="$suffix" \
        WB_SUBBOT_APCA_API_KEY_ID="$apca_key" \
        WB_SUBBOT_APCA_API_SECRET_KEY="$apca_secret" \
        WB_BAR_STREAM_LOG_ENABLED=1 \
        WB_BAR_STREAM_LABEL="subbot_$suffix" \
        $fade_extra \
        python3 move_strike_subbot.py >> "$log_path" 2>&1 &
    eval "SUBBOT_PID_$suffix=\$!"
    local pid_var="SUBBOT_PID_$suffix"
    eval "echo \"  variant $suffix PID: \$$pid_var\""
}

# Launch all three.
# Variant A re-purposed 2026-05-28: was the pure control; now tests the
# FIRESTORM gate. Per cowork_reports/2026-05-28_ytd_tick_rate_audit.md
# (TBD), the live-week and YTD-sim both showed entries on quiet bars
# (prior-bar tick_count < 6000/min ≈ 100/sec) account for the bulk of
# losses while contributing ~zero edge. Block any entry (REGIME_SHIFT,
# MOVE_STRIKE, REENTRY) when prior bar's tick count is below threshold.
if [ "${WB_ENGINE_DATA_DEGRADED:-0}" = "1" ]; then
    echo "=== DEGRADED MODE: skipping sub-bots (they consume engine ticks, which are down) ==="
else
launch_subbot A "$A_KEY" "$A_SECRET" "WB_MOVE_FIRESTORM_GATE_ENABLED=1 WB_MOVE_FIRESTORM_GATE_MIN_TICKS_PER_MIN=6000"
# Variant B re-purposed 2026-05-29: V1 VWAP fade-gate retired after 4
# straight losing weeks (cumulative ~$5K below week-start). Per
# cowork_reports/2026-05-28_track_a_results.md and Manny's call to slot
# Track A live alongside FIRESTORM-gate (orthogonal defenses — entry
# filter + exit framework). Track A defaults: R floor max($0.10, 5% of
# entry); phased drawdown 50%/30%/20% by 15/45 min boundaries;
# force-flatten 15:30 ET. MAIN_APCA account being reset by Manny;
# new keys may be repointed but env-var name stays.
# Variant B RETIRED 2026-06-10 (per Manny): poorest performer of the A/B/C test
# (cumulative -$4,183, only one below $30k start, -$1,260 last-6-days). The
# MAIN_APCA account is being repurposed for Manny's own manual-bot paper practice,
# so we no longer launch B here to avoid a two-bots-on-one-account conflict.
# launch_subbot B "$MAIN_APCA_KEY" "$MAIN_APCA_SECRET" "WB_MOVE_FIRESTORM_GATE_ENABLED=1 WB_MOVE_FIRESTORM_GATE_MIN_TICKS_PER_MIN=6000 WB_EXIT_TRACK_A_ENABLED=1"
# Variant C re-purposed 2026-05-27: was V4 BodyCV fade-gate (fired
# exactly once on 5/27 and was immediately overridden by regime_shift),
# now tests the REENTRY-LOSS-gate (broadened 2026-05-27 evening). Per
# cowork_reports/2026-05-27_reentry_loss_gate_broaden_directive.md.
# Blocks REENTRY GREEN within WINDOW_MIN of ANY loss-class exit on
# the same symbol: move_hwm_exit, move_stop_prox_bail, move_hard_stop,
# regime_shift_hard_stop. Broadened after today's AMSS disaster
# (15:16 REENTRY GREEN -$577 in 1s after a regime_shift_hard_stop
# the HWM-narrow gate missed by one reason-string).
launch_subbot C "$VARIANT_C_KEY" "$VARIANT_C_SECRET" "WB_MOVE_REENTRY_LOSS_GATE_ENABLED=1 WB_MOVE_REENTRY_LOSS_GATE_WINDOW_MIN=30"

# Health check — non-fatal (any single variant crash doesn't abort the test).
sleep 15
for suffix in A B C; do
    pid_var="SUBBOT_PID_$suffix"
    pid="${!pid_var}"
    if [ -z "$pid" ]; then
        echo "  variant $suffix not launched (missing keys)"
        continue
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "WARN: variant $suffix crashed within 15s — see logs/${TODAY}_move_strike_subbot_${suffix}.log"
        eval "SUBBOT_PID_$suffix=\"\""
    else
        echo "  variant $suffix health-check OK (PID $pid)"
    fi
done
fi  # end WB_ENGINE_DATA_DEGRADED sub-bot skip

# 8a-NEW. Healthy Fluctuation Framework live runner (Wave 4 paper).
# DISABLED 2026-05-19 per Manny's call — running squeeze-only tomorrow.
# Framework was competing with Setup A for IBKR data subscriptions
# (10197 "competing live session" errors all day). Re-enable by
# uncommenting the launch block below.
FRAMEWORK_PID=""
# FRAMEWORK_LOG="$LOG_DIR/${TODAY}_framework.log"
# echo "Starting framework.run_live (Wave 4 paper deploy)..."
# WB_FRAMEWORK_IB_CLIENT_ID=51 \
#   python3 -m framework.run_live >> "$FRAMEWORK_LOG" 2>&1 &
# FRAMEWORK_PID=$!
# echo "Framework started (PID: $FRAMEWORK_PID, log: $FRAMEWORK_LOG)"
# sleep 15
# if ! kill -0 "$FRAMEWORK_PID" 2>/dev/null; then
#     echo "WARN: framework.run_live crashed within 15s — continuing without framework."
#     FRAMEWORK_PID=""
# else
#     echo "Framework health check passed (still running after 15s, PID: $FRAMEWORK_PID)"
# fi

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

# 8d. Detached health watchdog (2026-06-03): session-independent auto-recovery
# for whole-stack-down and TICK DROUGHT (bot alive but data-blind). Survives even
# if this daily_run dies (it relaunches it). Idempotent — skip if already up.
# Logs to logs/health_watchdog.log. Not tracked by the cleanup trap on purpose:
# it self-exits at 20:10 ET and we WANT it alive if daily_run itself crashes.
if ! pgrep -f health_watchdog.sh >/dev/null 2>&1; then
    nohup /bin/zsh ~/warrior_bot_v2/health_watchdog.sh >/dev/null 2>&1 &
    echo "Health watchdog started (detached)"
else
    echo "Health watchdog already running — reusing"
fi

# 9. Watchdog loop: wait until 6:05 PM MT (8:05 PM ET) — 5 min after evening window closes
# Bot handles its own dual-window schedule (morning 7-12 ET, evening 4-8 PM ET)
# and sleeps during the dead zone automatically. Watchdog just ensures it stays alive.
TARGET_HOUR=18
TARGET_MIN=5
TARGET_EPOCH=$(date -j -v${TARGET_HOUR}H -v${TARGET_MIN}M -v0S +%s)

# Main-bot auto-restart accounting (2026-06-02). When the main bot dies mid-
# session the watchdog now restarts it in place and leaves the sub-bots running,
# instead of the old behavior that tore the whole stack down. Bounded so a hard
# crash-loop can't thrash forever.
BOT_RESTARTS=0
MAX_BOT_RESTARTS="${WB_MAX_BOT_RESTARTS:-10}"

echo "Watchdog: monitoring bot until 6:05 PM MT / 8:05 PM ET ($(date -r $TARGET_EPOCH))..."
echo "  Bot runs: morning 7:00-12:00 ET, sleeps 12:00-16:00, evening 16:00-20:00 ET"
while true; do
    NOW_EPOCH=$(date +%s)
    if [ "$NOW_EPOCH" -ge "$TARGET_EPOCH" ]; then
        echo "All trading windows closed. Proceeding to shutdown."
        break
    fi
    if [ -n "$BOT_PID" ] && ! kill -0 "$BOT_PID" 2>/dev/null; then
        # Main bot died mid-session. OLD behavior: break → fall through to the
        # shutdown that ALSO killed the sub-bots (cost us full sessions). NEW
        # (2026-06-02): auto-restart the main bot in place and keep the sub-bots
        # running. Set WB_MAIN_BOT_AUTORESTART=0 to restore tear-down-on-death.
        if [ "${WB_MAIN_BOT_AUTORESTART:-1}" != "1" ]; then
            echo "ALERT: bot_v3_hybrid.py died at $(date)! WB_MAIN_BOT_AUTORESTART=0 → ending session early. Check $LOG_FILE."
            break
        elif [ "$BOT_RESTARTS" -lt "$MAX_BOT_RESTARTS" ]; then
            BOT_RESTARTS=$((BOT_RESTARTS + 1))
            echo "ALERT: bot_v3_hybrid.py died at $(date). Auto-restarting in place (attempt $BOT_RESTARTS/$MAX_BOT_RESTARTS); sub-bots untouched. Check $LOG_FILE."
            launch_main_bot
            sleep 15
            if kill -0 "$BOT_PID" 2>/dev/null; then
                echo "Main bot restarted OK (PID: $BOT_PID)."
            else
                echo "WARN: restarted main bot died within 15s — will retry next tick."
            fi
        else
            echo "ALERT: bot_v3_hybrid.py hit max restarts ($MAX_BOT_RESTARTS). Leaving the main bot DOWN but keeping sub-bots alive until EOD. Check $LOG_FILE."
            BOT_PID=""   # stop re-checking a dead PID; loop runs on to TARGET_EPOCH
        fi
    fi
    # Framework is non-critical — log if it dies but keep watching the main bot.
    if [ -n "$FRAMEWORK_PID" ] && ! kill -0 "$FRAMEWORK_PID" 2>/dev/null; then
        echo "WARN: framework.run_live died at $(date). Squeeze main bot continuing alone."
        FRAMEWORK_PID=""
    fi
    # A/B/C sub-bot variants are non-critical — log if any die but keep watching the others.
    for suffix in A B C; do
        pid_var="SUBBOT_PID_$suffix"
        pid="${!pid_var}"
        if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
            echo "WARN: sub-bot variant $suffix died at $(date)."
            eval "SUBBOT_PID_$suffix=\"\""
        fi
    done
    sleep 60 || true
done

# 10. Shut down
echo "=== Shutting down at $(date) ==="
kill "$BOT_PID" 2>/dev/null || true
[ -n "$FRAMEWORK_PID" ] && kill "$FRAMEWORK_PID" 2>/dev/null || true
[ -n "$SUBBOT_PID_A" ] && kill "$SUBBOT_PID_A" 2>/dev/null || true
[ -n "$SUBBOT_PID_B" ] && kill "$SUBBOT_PID_B" 2>/dev/null || true
[ -n "$SUBBOT_PID_C" ] && kill "$SUBBOT_PID_C" 2>/dev/null || true
sleep 5
pkill -f "bot_v3_hybrid.py" 2>/dev/null || true
pkill -f "move_strike_subbot.py" 2>/dev/null || true
pkill -f "framework.run_live" 2>/dev/null || true

# 10a. A/B/C daily comparison report (2026-05-23+, runs for ~3-4 weeks).
# Non-fatal — failure here doesn't block log push.
echo "Generating A/B/C daily comparison report..."
cd ~/warrior_bot_v2
./venv/bin/python scripts/abc_compare_daily.py "${TODAY}" \
    > "$LOG_DIR/${TODAY}_abc_compare.log" 2>&1 \
    || echo "WARN: abc_compare_daily.py failed — see $LOG_DIR/${TODAY}_abc_compare.log"

# 11. Commit and push logs
echo "Pushing logs..."
cd ~/warrior_bot_v2
git add -f logs/ 2>/dev/null || true
git add -f cowork_reports/${TODAY}_abc_daily_report.md cowork_reports/abc_running_totals.json 2>/dev/null || true
git commit -m "auto: v3 daily logs ${TODAY}" 2>/dev/null || true
git push origin v2-ibkr-migration 2>/dev/null || echo "WARN: git push failed"

echo "=== V3 Hybrid daily run complete: $(date) ==="
