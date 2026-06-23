#!/bin/zsh
# ─────────────────────────────────────────────────────────────────────────────
# Session-independent health + tick-drought watchdog (2026-06-03).
# Runs DETACHED (nohup) so it survives Claude-Code session death / context
# compaction — the thing that kept reaping the in-session Monitors. Complements
# daily_run_v3.sh's process-watchdog by catching what that one can't:
#   1. whole stack down (daily_run itself died) → relaunch daily_run_v3.sh
#   2. TICK DROUGHT — bot process alive but data-blind (subscription wedge).
#      Rule (Manny, 100% track record): during market hours there are ALWAYS
#      ticks; silence = broken, never "quiet". Fix per project history = restart.
#      We kill the data-blind bot; daily_run_v3.sh's watchdog auto-restarts it
#      fresh (keeping sub-bots alive), which re-subscribes and clears the wedge.
# All actions logged to logs/health_watchdog.log for post-hoc investigation.
# Conservative + rate-limited so it cannot thrash. Exits after EOD (20:10 ET).
# ─────────────────────────────────────────────────────────────────────────────
cd ~/warrior_bot_v2 || exit 1
LOG=~/warrior_bot_v2/logs/health_watchdog.log
et_hm() { echo $((10#$(TZ=America/New_York date +%H%M))); }
log() { echo "$(TZ=America/New_York date '+%Y-%m-%d %H:%M:%S ET') $1" >> "$LOG"; }

log "=== health_watchdog started (pid $$) ==="
drought_n=0; last_kill=0; last_relaunch=0
scanner_empty_n=0; last_scanner_alarm=0
STALE_SEC=120              # bar_stream stale beyond this = suspect
KILL_COOLDOWN=600          # >=10 min between drought-kills (anti-thrash)
RELAUNCH_COOLDOWN=600      # >=10 min between stack relaunches
SCANNER_ALARM_COOLDOWN=1800  # >=30 min between scanner-feed alarms

while true; do
  TODAY=$(date +%Y-%m-%d)
  BS="logs/bar_stream/${TODAY}_main_bot.jsonl"
  ehm=$(et_hm); dow=$(TZ=America/New_York date +%u); now=$(date +%s)
  # market-data hours 07:00-20:00 ET, weekdays
  if [ "$dow" -le 5 ] && [ "$ehm" -ge 700 ] && [ "$ehm" -lt 2000 ]; then
    drun=$(pgrep -f daily_run_v3 >/dev/null && echo 1 || echo 0)
    bot=$(pgrep -f bot_v3_hybrid.py >/dev/null && echo 1 || echo 0)

    if [ "$drun" = 0 ]; then
      # Whole stack is unmanaged — daily_run died (its watchdog can't restart
      # anything if it's the thing that's gone). Relaunch it like the cron does.
      if [ $(( now - last_relaunch )) -gt "$RELAUNCH_COOLDOWN" ]; then
        log "STACK DOWN: daily_run_v3 not running → relaunching (cron-style)"
        nohup /bin/zsh ~/warrior_bot_v2/daily_run_v3.sh \
          >> ~/warrior_bot_v2/logs/cron_${TODAY}.log 2>&1 &
        last_relaunch=$now; drought_n=0
      fi
    elif [ "$bot" = 1 ] && [ -f "$BS" ]; then
      # daily_run alive (it auto-restarts bot process-death). We own DATA-death.
      age=$(( now - $(stat -f %m "$BS") ))
      if [ "$age" -gt "$STALE_SEC" ]; then
        drought_n=$((drought_n + 1))
        log "tick-drought check: bar_stream stale ${age}s (strike ${drought_n}/2)"
      else
        drought_n=0
      fi
      if [ "$drought_n" -ge 2 ] && [ $(( now - last_kill )) -gt "$KILL_COOLDOWN" ]; then
        nsym=$(grep -vc '^#' watchlist.txt 2>/dev/null || echo 0)
        log "TICK DROUGHT CONFIRMED: bar_stream stale ${age}s, watchlist=${nsym}. Market is OPEN — this is a data wedge, not quiet. Killing data-blind bot; daily_run watchdog will restart it fresh to re-subscribe."
        pkill -f bot_v3_hybrid.py
        last_kill=$now; drought_n=0
      fi
    fi

    # Scanner-feed health (2026-06-23): an empty watchlist during core RTH means
    # the Databento live feed is delivering ~0 volume (rvol collapses → 0
    # candidates), as on 6/19-6/22. A restart can't fix an upstream feed problem,
    # so we ALERT (desktop notification) instead of killing anything.
    if [ "$ehm" -ge 945 ] && [ "$ehm" -lt 1555 ]; then
      nsym=$(grep -vc '^#' watchlist.txt 2>/dev/null || echo 0)
      if [ "$nsym" -eq 0 ]; then
        scanner_empty_n=$((scanner_empty_n + 1))
      else
        scanner_empty_n=0
      fi
      if [ "$scanner_empty_n" -ge 10 ] && [ $(( now - last_scanner_alarm )) -gt "$SCANNER_ALARM_COOLDOWN" ]; then
        log "SCANNER FEED ALARM: watchlist empty ~$((scanner_empty_n / 2)) min during RTH — Databento live feed likely delivering ~0 volume (cf. 6/22). NOT auto-restarting (upstream feed issue). Verify the live feed."
        osascript -e 'display notification "Watchlist empty during market hours — Databento live feed likely down. Check the feed." with title "⚠️ WB SCANNER FEED DOWN" sound name "Basso"' 2>/dev/null || true
        last_scanner_alarm=$now
      fi
    fi
  fi
  [ "$(et_hm)" -ge 2010 ] && { log "=== EOD — health_watchdog exiting ==="; break; }
  sleep 30
done
