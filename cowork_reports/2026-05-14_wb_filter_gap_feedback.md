# WB Filter Gap — Watchlist Is Squeeze-Shaped, WB Winners Live Outside Its Bounds

**Date:** 2026-05-14
**Author:** CC
**For:** Cowork (Perplexity)
**Severity:** P1 — directly impacts daily P&L. WB winners have been hidden behind a stale-watchlist carryover effect that we just fixed. The fix may now block winners we previously captured by accident.
**Triggered by:** Manny's pushback after today's 0-candidate morning ("we need WB candidates"). Investigation found that **every WB winner over the past 8 sessions had pre-market volume far below the squeeze 30K floor.** The watchlist carryover that quietly kept these symbols visible has been removed by yesterday's daily-wipe deploy.

---

## TL;DR

The live scanner has ONE filter set, designed for squeeze setups (gap≥5%, price $2-20, float≤20M, RVOL≥1.5, pm_volume≥30,000). Across 8 trading days (2026-05-04 → 2026-05-13), the sub-bot took 19 WB trades — 4 wins / 15 losses. **All 4 winners had pre-market volume well below the 30K floor** (FATN ~1K, ATRA 4,103, SST 171, MEI <500). Two of four had gap_pct below 10%. They reached the watchlist by side channels: (a) `watchlist.txt` carryover from prior days, or (b) huge gap (ATRA +68%) dwarfing the PM volume miss.

Yesterday we shipped a `watchlist.txt` wipe at boot (commit a38ce72) specifically to eliminate stale carryover. **That fix likely also eliminates the side channel that produced 3 of our 4 recent WB winners.** The same data argues for a WB-specific intraday candidate path — but the sample is too small for confident filter design, and the losers also passed the squeeze gate. We are asking Cowork for a deeper research dive before committing to scope.

---

## Evidence

### Per-trade table (n=19; **winners bolded**)

| # | Date | Sym | Enter ET | Exit ET | Fill $ | Exit $ | P&L | Score |
|---|------|-----|----------|---------|--------|--------|-----|-------|
| 1 | 05-05 | CLNN | 10:42 | 10:46 | 6.91 | 6.82 | -$653 | 7 |
| 2 | 05-05 | CLNN | 11:08 | 11:09 | 6.82 | 6.75 | -$515 | 7 |
| 3 | 05-05 | FATN | 11:56 | 12:00 | 3.16 | 3.10 | -$955 | 8 |
| 4 | 05-05 | CLNN | 14:37 | 14:38 | 6.69 | 6.60 | -$673 | 9 |
| **5** | **05-05** | **FATN** | **14:39** | **14:41** | **3.28** | **3.35** | **+$1,074** | **8** |
| 6 | 05-05 | CLNN | 14:56 | 15:01 | 6.70 | 6.56 | -$1,052 | 7 |
| 7 | 05-08 | SST | 15:01 | 15:03 | 3.99 | 3.97 | -$251 | 9 |
| 8 | 05-08 | FATN | 13:58 | 15:43 | 3.26 | 3.21 | -$772 | 10 |
| **9** | **05-08** | **ATRA** | **17:09** | **19:37** | **8.65** | **9.08** | **+$2,500** | **10** |
| 10 | 05-11 | NVOX | 10:12 | 10:13 | 16.22 | 16.20 | -$37 | 9 |
| 11 | 05-11 | ATRA | 13:52 | 14:05 | 8.47 | 8.33 | -$513 | 10 |
| **12** | **05-11** | **SST** | **14:18** | **15:01** | **3.83** | **4.09** | **+$2,090** | **9** |
| 13 | 05-11 | ATRA | 18:30 | 19:02 | 9.49 | 9.20 | -$778 | 10 |
| 14 | 05-12 | ENSC | 08:16 | 08:19 | 0.3291 | 0.3210 | -$644 | 9 |
| 15 | 05-12 | SST | 11:20 | 11:21 | 3.94 | 3.83 | -$870 | 10 |
| 16 | 05-12 | ENSC | 14:54 | 14:57 | 0.3354 | 0.3285 | -$519 | 9 |
| 17 | 05-12 | TRAW | 15:17 | 15:18 | 1.82 | 1.78 | -$661 | 9 |
| 18 | 05-13 | ENSC | 11:53 | 11:59 | 0.3011 | 0.2941 | -$509 | 10 |
| **19** | **05-13** | **MEI** | **16:06** | **16:19** | **14.05** | **14.23** | **+$366** | **7** |

**Window totals:** 21% win rate. Gross winners +$6,030. Gross losers -$8,411. Net -$2,381.

### Pre-market stats for the 4 winners

| Winner | gap_pct | float_m | pm_volume | Mechanism on watchlist |
|--------|---------|---------|-----------|------------------------|
| FATN 05-05 | ~+5% | unknown | ~1K | Carryover from prior session's `watchlist.txt` |
| ATRA 05-08 | **+68.5%** | 4.25 | **4,103** | Gap so large it overrode PM-volume miss |
| SST 05-11 | **+17.6%** | 4.54 | **171** | Carryover (last fresh scan: 05-07) |
| MEI 05-13 | ~+4–5% | unknown | <500 | **Never appeared in scanner log at all** — bypass path |

**4 of 4 winners had pm_volume well below the 30K floor.**

### The side channels we just closed

1. **`watchlist.txt` carryover.** Until 2026-05-13 EOD, `watchlist.txt` was overwritten in-place but never wiped at boot. Symbols from prior days persisted. Both FATN 05-05 and SST 05-11 wins came from this. The 2026-05-13 wipe-at-boot commit eliminates this.

2. **Huge-gap PM bypass.** ATRA 05-08 at +68.5% gap passed despite 4K PM volume. This is intentional: very-large gaps with even thin PM action are exceptional setups. This channel still works.

3. **Unknown bypass for MEI 05-13.** Never appeared in `2026-05-13_scanner.log`. Either added by a manual path, an intraday bot rescan that didn't go through `live_scanner.py`, or another code path. Worth tracing.

---

## Analysis

The squeeze scanner's `pm_volume ≥ 30,000` floor is a strategy-specific gate: squeeze setups require pre-market participation to confirm institutional interest. **WB is structurally different.** It detects intraday wave structure (oscillations, higher-highs / higher-lows, MACD direction, bounce volume) — it does not require pre-market activity. A stock that goes nowhere overnight then catches a regular-hours wave is a perfect WB setup and a non-event for squeeze.

The carryover effect masked this mismatch for weeks. Every "WB candidate" arrived having passed squeeze filters (correctly or via persistence), and WB scored them on intraday behavior. When carryover happened to land a PM-quiet symbol on the watchlist, WB sometimes caught its intraday wave. Now that the wipe is in place, that fortuitous overlap disappears.

The losers don't refute this: WB took losses on stocks that *did* pass squeeze filters (CLNN, NVOX, ATRA, ENSC, TRAW). Score 9-10 wave qualifications produced bad fills. Removing the PM gate would not have changed those losers — they were already on the watchlist. So loosening WB's universe widens the funnel of winners *and losers* — net effect depends on intraday WB filtering (sustained RVOL, time-of-day, wave context), not just on getting more candidates.

---

## Questions for Cowork

### Q1 — Is n=4 enough to act on, or do we need a backtest?

Four winners is a small sample. Should we run a WB backtest over Jan–Apr 2026 against a synthetic "relaxed universe" (gap≥3%, no PM floor, price $2-30) to estimate net P&L vs. the current squeeze-filtered universe? If yes, what's the minimum sample (number of trades) at which the relaxation decision becomes statistically credible?

### Q2 — What's the optimal intraday WB filter?

The analysis-report recommendation is: intraday candidate adder polling every 15 min during RTH for (gap≥3% AND intraday RVOL≥3× AND price $2-30). What additional gates does Perplexity recommend for WB specifically — given that the live scanner is built around premarket signals that don't apply post-9:30? Specifically: should we filter by VWAP relationship, by HOD proximity, by MACD direction at scan time, by time-of-day (e.g., kill candidates added after 14:00 ET)?

### Q3 — Should we restore the carryover deliberately?

The wipe eliminated a side channel that *generated* 3 of 4 WB winners but also *invisibly* let stale symbols sit on the list and cost us losses. Is there a smarter version — e.g., "carry forward a symbol IF it had a WB_OBSERVE wave_id ≥ N in the prior session" — that captures WB upside without re-introducing stale-watchlist bugs? Or is the wipe-at-boot the right primitive and we just need a WB-native scanner?

### Q4 — Trace MEI 05-13's bypass path.

MEI 05-13 won (+$366) without appearing in the scanner log. How did it get on the watchlist? Was it from `bot_v3_hybrid.poll_watchlist`, a manual addition, or a different rescan code path? Mapping this answer would tell us whether MEI-class winners are a routine sustained channel or a one-off fluke.

### Q5 — Are there losers on the current watchlist that a WB-aware filter would have rejected?

Looking at the 15 losers: how many were WB-mismatched setups that a WB-specific intraday filter would have rejected pre-entry? If most losers passed a WB-specific filter too, then loosening the universe gets us bad trades faster. If most losers would have been rejected by an intraday WB gate (e.g., low RVOL at scan time, MACD against, post-14:00 entry), then a WB-native scanner is a clear net-positive.

### Q6 — Multi-strategy scanner architecture.

The current scanner is monolithic (one filter, one watchlist). Should we move toward two parallel scanners (squeeze + WB) writing to two separate watchlist files, with the bot subscribing to both? Or is a single "tagged" watchlist (each symbol annotated `passed_squeeze=True/False, passed_wb=True/False`) cleaner? Tradeoffs?

---

## Files referenced

- `~/warrior_bot_v2/cowork_reports/2026-05-14_wb_vs_squeeze_filter_analysis.md` (the underlying data report)
- `~/warrior_bot_v2/logs/2026-05-{04..13}_subbot_alpaca.log` (trade source)
- `~/warrior_bot_v2/scanner_results/live_2026-05-{07,08,11,14}_*.json` (PM snapshots — partial coverage)
- `~/warrior_bot_v2/live_scanner.py` (single filter set lives here)
- `~/warrior_bot_v2/daily_run_v3.sh` lines 174-184 (watchlist wipe at boot — the just-shipped change)
- `~/warrior_bot_v2/.env` (active filter values: gap≥5%, price 2-20, float≤20M, rvol≥1.5, pm_vol≥30K)

---

*The squeeze scanner has been the only scanner. WB has been trading whatever the squeeze scanner happened to hand it, plus what stale carryover left in the file. We have just removed the stale channel. The data says we may have removed the channel where WB actually wins. We need Cowork's depth on this before deciding whether a WB-native intraday adder ships today, or whether we wait for a real backtest.*
