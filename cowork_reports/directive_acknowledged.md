# Directive Acknowledged
- Timestamp: 2026-03-21 (session start)
- Directive: DIRECTIVE_FIX_SIM_START_BUG.md
- Status: Read and beginning work

## Summary of Work Plan

### Priority 1: 4 MUST-FIX Live Bot Bugs (before Monday market open)
1. Scanner sort — market_scanner.py line 136: sort passing_symbols by volume before truncating to 500
2. Crash detection — daily_run.sh: add post-launch kill -0 health check + watchdog loop
3. Zero-symbol abort — bot.py: alert and log when filtered_watchlist is empty
4. Pre-flight smoke test — daily_run.sh: import check before launching bot.py

### Priority 2: Fix sim_start bug in scanner_sim.py
- resolve_precise_discovery() sets sim_start to raw criteria-met time (4 AM) instead of scanner checkpoint
- Fix: map precise_discovery to nearest scanner checkpoint (07:00, 08:00, 08:30, 09:00, 09:30, 10:00, 10:30)
- Then reprocess all 297 dates

### Priority 3: Run verification tests
- VERO +$18,583, ROLR +$6,444 standalone regressions
- ARTL and random stocks through full pipeline
- Document in cowork_reports/pre_megatest_v2_verification.md

### DO NOT start v2 megatest until user reviews verification log
