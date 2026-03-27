# Daily Recap Tracker — March 2026

## Purpose
Running daily comparison: what the bot's scanner found + backtest results vs Ross Cameron's actual recap. Updated every trading day. This is the live equivalent of the January 2025 missed stocks analysis.

## Methodology
- **Scanner**: `scanner_sim.py` output for the date (ground truth — live scanner has known divergence)
- **Backtest**: `simulate.py --ticks` on each scanner candidate with current config (SQ + MP both ON, unknown-float gate ON)
- **Ross**: Recap video notes — tickers, P&L, setup types, times
- **Comparison**: Scanner overlap, trade overlap, P&L gap

---

## Running Totals

| Metric | Value |
|--------|-------|
| Trading days tracked | 1 |
| Ross total P&L | +$7,600 |
| Bot total P&L (SQ fixes OFF) | -$325 |
| Bot total P&L (SQ fixes ON) | -$374 |
| Scanner overlap rate | 1/1 (100%) |
| Bot traded Ross's stock? | YES — but 4 trades vs Ross's ~40 round-trips |
| Biggest gap driver | Re-entry depth + scaling (bot max_entries vs Ross's 81 tickets) |

---

## Daily Log

### 2026-03-23 (Monday)

**Live bot status:** DOA — Alpaca websocket "connection limit exceeded", 0 trades all day.

**Scanner sim candidates (3):**

| Ticker | Gap% | Price | Float | RVOL | Discovery | SimStart | Profile |
|--------|------|-------|-------|------|-----------|----------|---------|
| UGRO | +46.8% | $3.20 | 0.67M | 33.0x | 07:06 | 07:00 | A |
| AHMA | +46.5% | $6.66 | 2.02M | 112.7x | 09:15 | 09:30 | A |
| WSHP | +20.0% | $14.00 | 1.33M | 2.2x | 07:58 | 08:00 | A |

**Live bot scanner (divergent — uses old stock_filter.py/Alpaca snapshots):**
ANNA, ARTL, SUNE — zero overlap with scanner_sim.

**Bot backtest results — SQ exit fixes OFF (first run):**

| Ticker | Trades | Strategy | P&L | Best Trade | Notes |
|--------|--------|----------|-----|------------|-------|
| UGRO | 4 | 3 SQ, 1 MP | +$50 | 07:12 SQ +$1,159 (+2.3R) | First SQ stopped out (-$429), second nailed +2.3R. MP trade lost -$324. Late SQ attempt lost -$357. |
| AHMA | 2 | 2 SQ | -$375 | 09:36 SQ +$1,696 (+3.4R) | First trade hit dollar loss cap (-$2,071, -4.1R!). Second trade recovered +$1,696. |
| WSHP | 0 | — | $0 | — | 0 armed, 0 signals. Low RVOL (2.2x) — weakest candidate. |
| **TOTAL** | **6** | **5 SQ / 1 MP** | **-$325** | — | SQ doing all the work. AHMA first trade -4.1R is brutal (gap-through on para stop?). |

**Bot backtest results — SQ exit fixes ON (re-run with PARTIAL+WIDE_TRAIL+RUNNER_DETECT+HALT_THROUGH):**

| Ticker | Trades | Strategy | P&L | Best Trade | Notes |
|--------|--------|----------|-----|------------|-------|
| UGRO | 4 | 3 SQ, 1 MP | +$358 | 08:03 SQ +$500 (+1.0R) | Trade 2 took partial at 2R (+$682), runner stopped at BE. Trade 4 new winner +$500. Net +$308 vs fixes OFF. |
| AHMA | 2 | 2 SQ | -$732 | 09:36 SQ +$1,339 (+2.7R) | First trade same -$2,071. Second: partial at 2R, runner gave back → net +$1,339 vs +$1,696 before. Net -$357 vs fixes OFF. |
| WSHP | 0 | — | $0 | — | Same — 0 armed, 0 signals. |
| **TOTAL** | **6** | **5 SQ / 1 MP** | **-$374** | — | SQ fixes: UGRO +$308, AHMA -$357. Net -$49 vs fixes OFF. Partial exit runner on AHMA didn't ride high enough. |

**SQ exit fix analysis:** The partial exit splits shares 50/50 at the 2R target. On AHMA, the runner half got stopped at breakeven instead of riding higher — net worse. On UGRO, the wider trail helped Trade 4 survive to +1.0R. The fixes are a wash on this single day. Need Jan comparison data to determine if the pattern holds at scale.

**Ross Cameron recap:** +$7,600 on UGRO only (81 tickets, cold market base-hits strategy)

| Ticker | Ross P&L | Setup Type | Time | On Bot Scanner? | Bot Traded? |
|--------|----------|------------|------|-----------------|-------------|
| UGRO | +$7,600 | Multi-setup: whole-dollar break, S/R flip, HOD anticipation, micro pullback scalps | 7:05 AM onwards, all morning | ✅ YES (#2 ranked) | ✅ YES (4 trades) |
| AHMA | not traded | — | — | ✅ YES (#1 ranked) | ✅ YES (2 trades) |

**Scanner overlap:** 1/1 Ross tickers found by bot (100%) — first time this has happened!
**P&L comparison (SQ fixes OFF):** Ross +$7,600 vs Bot -$325 (4.3% capture... of the wrong sign)
**P&L comparison (SQ fixes ON):** Ross +$7,600 vs Bot -$374

**Key insight — why the gap is so large:**
Ross made +$7,600 on UGRO with 81 tickets of high-frequency level-based scalping ($3.00 → $3.47 → $3.85 → $4.18 → $4.34). The bot took 4 trades on UGRO and netted +$50 to +$358 depending on config. The core problem isn't the scanner (it found UGRO at 07:06, Ross found it at ~07:05) — it's:
1. **Scaling**: Ross used 15K-share positions, adding/trimming constantly. Bot is all-or-nothing.
2. **Re-entry depth**: Ross took ~40 round-trips on UGRO. Bot took 4 and hit max_entries/cooldown limits.
3. **Level recognition**: Ross identified $3.47 as resistance-turned-support and traded it repeatedly. Bot doesn't track intraday S/R flips.
4. **AHMA skip was correct**: Ross explicitly passed on AHMA (no news, higher risk). Bot traded it and lost -$375 to -$732.

**Full recap:** `cowork_reports/ross_recaps/mar_23.md`

---

*Template for future days — copy this block:*

<!--
### 2026-03-XX (Day)

**Live bot status:** [status]

**Scanner sim candidates (N):**

| Ticker | Gap% | Price | Float | RVOL | Discovery | SimStart | Profile |
|--------|------|-------|-------|------|-----------|----------|---------|

**Bot backtest results:**

| Ticker | Trades | Strategy | P&L | Best Trade | Notes |
|--------|--------|----------|-----|------------|-------|
| **TOTAL** | — | — | — | — | — |

**Ross Cameron recap:**

| Ticker | Ross P&L | Setup Type | Time | On Bot Scanner? | Bot Traded? |
|--------|----------|------------|------|-----------------|-------------|

**Scanner overlap:** X/Y Ross tickers found by bot
**P&L comparison:** Ross $X,XXX vs Bot $X,XXX (XX% capture)
-->
