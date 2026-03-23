# DIRECTIVE: January 2025 Missed Stocks Backtest

**Date:** 2026-03-23
**From:** Cowork (Opus)
**For:** CC (Sonnet in terminal)
**Priority:** HIGH — Phase 2 analysis, determines if fixing the scanner is worth it

---

## Context

In January 2025, Ross Cameron traded 68+ unique tickers and made ~$406K. The bot's scanner found only 5 of them (7.4%). We have detailed recap data for every trading day showing what Ross traded, when he found it, and what he made.

**The question:** If the scanner had found all of Ross's stocks, what would the bot have done? If the bot would have been profitable on these stocks, fixing the scanner is the highest-leverage thing we can do. If the bot would have lost money, scanner coverage doesn't matter — exit management does.

## Objective

Run simulate.py on every Ross-traded stock from January 2025 that we have enough data to backtest. Use `--feed databento --tick-cache tick_cache/` to fetch and cache tick data. Run both SQ-enabled and MP+SQ configs.

---

## Step 1: Git Pull

```bash
cd ~/warrior_bot && git pull origin main
source venv/bin/activate
```

## Step 2: Environment Setup

For each run, use these base settings (matching the megatest ENV_BASE):

```bash
export WB_SQUEEZE_ENABLED=1
export WB_SQ_PARA_ENABLED=1
export WB_SQ_NEW_HOD_REQUIRED=1
export WB_SQ_MAX_LOSS_DOLLARS=500
export WB_MP_ENABLED=1
export WB_PILLAR_GATES_ENABLED=0    # OFF — we're testing if the bot CAN trade these, not if pillar gates allow them
export WB_ROSS_EXIT_ENABLED=0       # Baseline first
export WB_CLASSIFIER_ENABLED=1
export WB_EXHAUSTION_ENABLED=1
export WB_CONTINUATION_HOLD_ENABLED=1
export WB_MAX_NOTIONAL=50000
export WB_RISK_DOLLARS=1000
```

Note: `WB_PILLAR_GATES_ENABLED=0` is intentional. We want to know what the bot's strategies would do on these stocks. Pillar gates may have blocked some of them — that's a separate analysis.

## Step 3: Run the Backtests

### Group A: Stocks the scanner found AND the bot traded (control group — verify against known results)

These already have tick cache. Run first to validate the setup.

```bash
# ALUR — Jan 24 (Ross +$85,900, bot +$586)
python simulate.py ALUR 2025-01-24 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# YIBO — Jan 28 (Ross +$5,724, bot +$125)
python simulate.py YIBO 2025-01-28 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# SLXN — Jan 29 (Ross ~+$5,000, bot +$231)
python simulate.py SLXN 2025-01-29 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# AIFF — Jan 14 (Ross -$2,000, bot +$1,424)
python simulate.py AIFF 2025-01-14 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# WHLR — Jan 16 (Ross +$3,800, bot +$28)
python simulate.py WHLR 2025-01-16 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/
```

### Group B: Stocks the scanner found but bot DIDN'T trade

```bash
# INM — Jan 21 (Ross +$12,000, bot 0 trades despite #1 rank)
python simulate.py INM 2025-01-21 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# OST — Jan 14 (Ross +$1,800, bot 0 trades)
python simulate.py OST 2025-01-14 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/
```

### Group C: Ross's BIG winners the scanner MISSED ($5K+ P&L)

These are the most important. Use sim_start = time Ross first noticed the stock (from recaps). If unknown, use 07:00.

```bash
# XPON — Jan 2, +$15,000 (news squeeze)
python simulate.py XPON 2025-01-02 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# ESHA — Jan 9, +$15,556
python simulate.py ESHA 2025-01-09 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# INBS — Jan 9, +$18,444
python simulate.py INBS 2025-01-09 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# DGNX — Jan 23, +$22,997 (Chinese IPO day 2)
python simulate.py DGNX 2025-01-23 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# SGN — Jan 29, +$13,000
python simulate.py SGN 2025-01-29 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# SGN — Jan 31, +$20,000 (day 2 continuation)
python simulate.py SGN 2025-01-31 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# ARNAZ — Jan 28, +$12,000 (daily breakout + halt resumption)
python simulate.py ARNAZ 2025-01-28 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# JG — Jan 27, +$15,558 (Chinese AI DeepSeek)
python simulate.py JG 2025-01-27 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# AURL — Jan 27 (Chinese AI DeepSeek, 200% PM move)
python simulate.py AURL 2025-01-27 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# NEHC — Jan 22, +$8,636 (energy infrastructure)
python simulate.py NEHC 2025-01-22 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# BBX — Jan 22, +$13,036 (merger news, 2M float)
python simulate.py BBX 2025-01-22 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# ADD — Jan 14, +$5,810 (sub-1M float, VWAP reclaim)
python simulate.py ADD 2025-01-14 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# BTCT — Jan 21, +$5,500 (crypto inauguration theme)
python simulate.py BTCT 2025-01-21 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# SLRX — Jan 13, +$13,000 (merger news stair-step)
python simulate.py SLRX 2025-01-13 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# EVAC — Jan 24, +$5-10K (GLP-1 sympathy)
python simulate.py EVAC 2025-01-24 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/
```

### Group D: Ross's medium winners ($1K-$5K P&L)

```bash
# CRNC — Jan 3, +$1,800 (Nvidia news)
python simulate.py CRNC 2025-01-03 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# SPCB — Jan 3, +$2,600 (day 2 continuation)
python simulate.py SPCB 2025-01-03 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# ARBE — Jan 6, +$4,200 (Nvidia news)
python simulate.py ARBE 2025-01-06 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# XHG — Jan 10, +$3,500 (no-news continuation)
python simulate.py XHG 2025-01-10 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# OSTX — Jan 15, +$3,000 (Phase 2 clinical trial)
python simulate.py OSTX 2025-01-15 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# ZENA — Jan 7, +$998 (breaking news)
python simulate.py ZENA 2025-01-07 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# QLGN — Jan 28, +$2,400 (biotech squeeze)
python simulate.py QLGN 2025-01-28 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# AIMX — Jan 17, +$1,200 (news breakout)
python simulate.py AIMX 2025-01-17 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# ZO — Jan 17, ~$4,864 (VWAP reclaim range trading)
python simulate.py ZO 2025-01-17 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# NXX — Jan 21, +$1,800 (news breakout)
python simulate.py NXX 2025-01-21 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# DATS — Jan 13, +$2,000 (no-news continuation)
python simulate.py DATS 2025-01-13 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# MVNI — Jan 29, +$3,900 (multi-trade, best entry 9:47 AM)
python simulate.py MVNI 2025-01-29 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# ELAB — Jan 24, +$3-5K (squeeze pullback)
python simulate.py ELAB 2025-01-24 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# HOTH — Jan 7, +$1,000 (momentum first-pop)
python simulate.py HOTH 2025-01-07 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/
```

### Group E: Ross's losses/scratches (important for calibration)

```bash
# OST — Jan 2, -$3,000 (no news momentum)
python simulate.py OST 2025-01-02 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# GTBP — Jan 13, -$3,400 (too aggressive)
python simulate.py GTBP 2025-01-13 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# VRME — Jan 14, -$4,000 (VWAP break failed)
python simulate.py VRME 2025-01-14 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/
```

### Group F: Profile X stocks (scanner found, no float data)

```bash
# GDTC — Jan 6, Ross +$5,300
python simulate.py GDTC 2025-01-06 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/

# AMOD — Jan 30, Ross positive
python simulate.py AMOD 2025-01-30 07:00 12:00 --ticks --feed databento --tick-cache tick_cache/
```

**TOTAL: 37 backtests** (5 control + 2 found-not-traded + 15 big winners + 12 medium winners + 3 losses)

---

## Step 4: Collect Results

For each run, record in a results file `cowork_reports/2025-01_missed_stocks_backtest_results.md`:

| Date | Symbol | Group | Ross P&L | Bot Trades | Bot P&L | Best Setup | Exit Reasons | Notes |
|------|--------|-------|----------|------------|---------|------------|--------------|-------|

Include:
- Number of trades (MP vs SQ breakdown)
- Total P&L per symbol
- Exit reasons for each trade
- Whether MP or SQ (or both) fired
- If 0 trades: note why (no ARM, no squeeze trigger, etc.)
- Peak unrealized P&L if visible in logs

---

## Step 5: Summary Analysis

At the end, compute:

1. **If scanner found ALL Ross stocks:** Total bot P&L across all 37 backtests
2. **Group breakdown:** What % of Ross's P&L would the bot have captured per group?
3. **Strategy effectiveness:** How many of Ross's winners did SQ trigger on? MP? Neither?
4. **"0 trade" rate:** How many of these stocks produce 0 bot trades even with tick data?
5. **Exit gap:** For stocks where the bot DID trade, what was the avg capture rate vs Ross's P&L?

---

## Step 6: Commit

```bash
git add tick_cache/ cowork_reports/2025-01_missed_stocks_backtest_results.md
git commit -m "Jan 2025 missed stocks backtest: 37 Ross tickers tested

Backtested all January 2025 Ross Cameron tickers against current bot
(SQ+MP). Fetched tick data via Databento for stocks the scanner missed.
Results determine whether scanner coverage improvement is worth pursuing.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main
```

---

## Important Notes

- **Databento costs:** Each fetch pulls trade-level tick data for one symbol-day. Monitor API usage. If costs are a concern, prioritize Group C (big winners) first.
- **Some tickers may not resolve in Databento.** If a symbol fails (delisted, OTC-only, ticker change), note it in the results and move on.
- **Run times:** Each backtest takes 30-90 seconds in tick mode. Total estimated: ~30-45 minutes for all 37.
- **Pillar gates are OFF** so we see what the strategies CAN do, not what the current filters allow.
- **If a stock produces 0 trades with both SQ and MP enabled**, that's important data — it means even perfect scanner coverage wouldn't have helped on that stock.

## Success Criteria

- All 37 backtests complete (or noted as failed with reason)
- Results table populated with per-stock P&L
- Summary analysis answering the 5 questions above
- All tick data cached for future re-runs
