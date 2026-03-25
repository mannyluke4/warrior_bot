# DIRECTIVE: Full Year Backtest — Jan 2025 to Mar 2026

**Date:** 2026-03-25
**For:** Any CC session on Mac Mini
**Priority:** HIGH — Run as soon as 2025 backfill completes
**Depends on:** 2025 IBKR scanner backfill (check: `tail -5 ~/warrior_bot_v2/backfill_2025_full.log`)

---

## Pre-Check

Verify the 2025 backfill is complete:

```bash
cd ~/warrior_bot_v2
grep "BACKFILL COMPLETE" backfill_2025_full.log
# Should show: BACKFILL COMPLETE: XXX dates, XXX total candidates

# Also verify scanner data exists
ls scanner_results/2025-01-*.json | wc -l
# Should be ~20 files for January 2025
```

If the backfill is still running, wait. Check progress with:
```bash
tail -5 ~/warrior_bot_v2/backfill_2025_full.log
```

---

## Step 1: Run Full Year Backtest

```bash
cd ~/warrior_bot_v2
source venv/bin/activate
python run_backtest_v2.py --start 2025-01-02 --end 2026-03-25 --label "Full Year Jan 2025 - Mar 2026 (IBKR Data)"
```

**Progress file:** `backtest_status/current_run.md` — check anytime from any session:
```bash
cat ~/warrior_bot_v2/backtest_status/current_run.md
```

**Expected runtime:** 30-60 minutes (most tick data is cached)

---

## Step 2: Review Results

The progress file will show final results when complete. Key metrics to report:

1. Total P&L and return %
2. Trade count, win rate
3. Monthly breakdown (which months were strongest/weakest)
4. Comparison to YTD 2026 alone (+$120,221 / +400.7%)
5. OOS validation: does 2025 (unseen data) show similar edge to 2026 (development data)?

---

## Step 3: Commit Results

```bash
cd ~/warrior_bot_v2
git add backtest_status/ scanner_results/2025-*.json
git commit -m "Full year backtest: Jan 2025 - Mar 2026 on IBKR data

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push origin v2-ibkr-migration
```

---

## Context

- V2 IBKR migration complete (Phases 0-5)
- Scanner data uses unified IBKR RVOL (no more Alpaca IEX/SIP split)
- YTD 2026 alone: $30K → $150K (+400.7%), 97% WR, 36 trades
- Jan 2026 alone: $30K → $87K (+189.8%), 83% WR, 30 trades
- Strategy: SQ-only, mechanical exits, 2.5% dynamic risk, $100K max notional
- Bot is set up for live paper trading tomorrow (cron at 2 AM MT)

This is the definitive backtest on trustworthy data. The numbers from this run
are what we base all live trading decisions on.
