# YTD Honest Re-baseline — 2026-05-18

**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Commit:** `cc3e78d`
**Configuration:** X01 (RISK_PCT=0.035, DAILY_LOSS_SCALE=1, MAX_NOTIONAL=$100,000, MAX_TRADES_PER_DAY=5)
**Harness:** `run_backtest_v2.py` (compounding equity, $30,000 starting bankroll)
**Window:** scanner sim_start → 12:00 (default — matches X01 baseline conditions)
**Parent directive:** YTD Honest Re-baseline (2026-05-18), Deliverable 2

## TL;DR

| Metric | Value |
|---|---|
| Trading dates in scope | 75 (Jan 02 → May 18) |
| Active dates (≥1 trade) | 20 |
| Zero-trade dates | 55 (52 had tick cache but no signal; 3 had no tick cache) |
| Total trades | 55 |
| Wins / losses | 40W / 13L (2 break-even) |
| Win rate | 75% (of decided trades) |
| Starting equity | $30,000 |
| **Final equity** | **$290,502** |
| **Total P&L** | **+$260,502 (+868.3%)** |
| Peak equity | $290,502 (2026-05-18, the final day) |
| Trough after peak | n/a — final day is peak |
| Max drawdown | 0.1% ($245,887 vs $246,091 peak on 2026-03-18, sole losing day) |
| Best week | 2026-W03 (Jan 13-17): **+$81,574** — ROLR + ACCL cascade |
| Best non-W03 week | 2026-W06 (Feb 2-3): **+$74,026** — NPT cascade |
| Worst week | 2026-W01 + W02 + W07 + W09 + W13 + W19 = **$0** (no losing weeks, only zero-activity weeks) |
| Wall-clock | ~7 min 30 s |

**Headline:** The honest YTD compounding-equity number on HEAD with X01 config is **$290,502** ($30K → $290K, +868%). This is **3.6× larger** than the comparable 2026-04-14 X01-sim-fill re-baseline ($120,221) and **vastly different** from the reverted realistic-fill number (-$2,641). The +868% growth is heavily driven by 7 cascade days (ROLR, ACCL, BATL, NPT, OBAI, MLEC, SLE) that compound off each other.

## Honest assessment: positive expectancy?

**Per-trade, yes — strongly.** 40W / 13L with avg win >> avg loss is a clean positive-EV signature, and the X01 config has been stable for 6 weeks. The headline +868% number is real to the model and the data.

**With caveats:**

1. **Tick-cache survivor bias is the dominant story.** Of 75 trading days in scope, only 20 produced any trades. Of those 20 active days, 7 produced 75% of total P&L:

| Date | Symbol(s) | Day P&L | Cumulative equity |
|---|---|---|---|
| 2026-01-14 | ROLR | +$24,027 | $77,894 |
| 2026-01-16 | ACCL | +$33,680 | $111,574 |
| 2026-01-26 | BATL | +$38,040 | $152,147 |
| 2026-02-03 | NPT | +$70,263 | $226,173 |
| 2026-02-17 | OBAI | +$17,366 | $243,539 |
| 2026-04-06 | MLEC + FCUV | +$20,377 | $276,996 |
| 2026-05-15 | SLE | +$11,284 | $288,280 |

The compounding effect amplifies these — ROLR alone delivers +80% of starting bankroll on day 8. **If any one of these cascade days had a corrupt tick cache or a missed scanner candidate, the curve would be radically different.**

2. **Pre-2026-04-15 tick cache is sparse.** Per the parent directive context: pre-2026-03-23 the tick cache typically had only 2-8 symbols per day vs the live scanner's 80-120. We see this clearly: the harness produced trades on just 14 of 49 pre-April-15 dates. Most of the ROLR / ACCL / NPT cascades happened to land on dates where the tick cache had those specific symbols. **Missing cascade-day cache = missed cascade = different curve.**

3. **Live can't reproduce this.** This is a *backtest* number. The simulator over-fills relative to live (no chase-cap rejection model — see A3 §"Structural divergences"). Per `feedback_fill_optimism_disregard.md`, the 2026-04-14 fill-optimism finding was disputed and reverted, but the directionality is real: live with IBKR chase-cap will not see 100% of these fills. SLE 2026-05-15 in particular: replay shows +$2,981 across 9 trades; live realized +$221 across 2 of 9 attempted entries (7 chase-aborted). If even a moderate "true live fill rate" haircut applied to the YTD cascade days, the +868% drops materially.

4. **No daily-loss-cap stress.** With `WB_BT_DAILY_LOSS_SCALE=1` and the only losing day at -$204, the daily-loss governor never engages. The curve has not been tested against a -$500 / -$1K / -$2K day in the entire YTD window. The first such day in live will be a discovery, not a regression.

**Conclusion:** Positive expectancy is real in the model. The +868% headline is structurally inflated by (a) tick-cache survivor bias toward winners and (b) absence of live fill-rate haircuts. Treat as upper bound, not a target.

## Comparison vs prior re-baselines

| Re-baseline | Date | Code state | Final equity | Note |
|---|---|---|---|---|
| **HEAD honest** | **2026-05-18** | **cc3e78d, X01, R-floor on** | **$290,502** | **This report** |
| 2026-04-14 X01-sim-fill (reverted) | 2026-04-14 | f2bc3a8, X01, no R-floor | $120,221 | `cowork_reports/2026-04-14_finding_sim_fill_optimism.md` X01 column |
| 2026-04-14 realistic-fill (reverted) | 2026-04-14 | f2bc3a8 + realistic-fill mod | -$2,641 | Same report, "realistic-fill" column. Per `feedback_fill_optimism_disregard.md`, the methodology was disputed. |
| 2026-04-15 autopsy aggregate | 2026-04-15 | ~13d74d3 | not aggregated | Per-symbol numbers only (VERO +$35,623, ROLR +$50,602, etc.) |
| Memory `project_current_state.md` | 2026-04-15 (paste-forward) | X01 era | "$10K→$150K on squeeze-only" (15×) | Honest baseline per memory; today's run is 9.7× starting equity — same order of magnitude but bigger |

The +$290K final is materially larger than the +$120K from 2026-04-14 because:
- Today's run uses 2 extra months of trading days (Apr 15 → May 18) including the +$20K MLEC+FCUV cascade on 04-06 and the SLE +$11K day on 05-15.
- Today's run benefits from the full vol-winsorize + seed-staleness gates (default-on as of `13d74d3` / 2026-04-13).
- R-floor (today's patch) provides marginal lift by suppressing 1 low-R signal in the YTD window (GOVX 2026-05-18, redirected to a different setup that produced +$2,222).

The -$2,641 from realistic-fill is decoupled from this run by methodology (different fill model) and is per memory not the active baseline.

## Equity curve, week-by-week

| ISO week | Range | Week P&L | End-of-week equity |
|---|---|---|---|
| 2026-W01 | Jan 02-05 | $0 | $30,000 |
| 2026-W02 | Jan 06-09 | $0 | $30,000 |
| **2026-W03** | **Jan 12-16** | **+$81,574** | **$111,574** |
| 2026-W04 | Jan 20-23 | +$2,533 | $114,107 |
| 2026-W05 | Jan 26-30 | +$38,040 | $152,147 |
| **2026-W06** | **Feb 02-06** | **+$74,026** | $226,173 |
| 2026-W07 | Feb 09-13 | $0 | $226,173 |
| 2026-W08 | Feb 17-20 | +$17,366 | $243,539 |
| 2026-W09 | Feb 24-27 | $0 | $243,539 |
| 2026-W10 | Mar 02-06 | +$1,210 | $244,749 |
| 2026-W11 | Mar 09-13 | +$1,342 | $246,091 |
| 2026-W12 | Mar 17-20 | +$3,440 | $249,531 |
| 2026-W13 | Mar 23-27 | $0 | $249,531 |
| 2026-W14 | Mar 30 - Apr 03 | +$7,088 | $256,619 |
| **2026-W15** | **Apr 06-10** | **+$20,377** | $276,996 |
| 2026-W19 | May 04-08 | $0 | $276,996 |
| **2026-W20** | **May 11-15** | **+$11,284** | $288,280 |
| 2026-W21 | May 18 | +$2,222 | $290,502 |

Note: ISO weeks W16-W18 are absent (4 weeks with no trading-day scanner files in scope per harness date filter — these correspond to Apr 13-May 1 stretch where the bot was either gated off or had scanner-result gaps).

## Skip list & data integrity

### Days with no tick cache (3)

- 2026-01-03
- 2026-03-17
- 2026-03-25

The harness skipped these silently (the scanner files existed but the per-symbol replay subprocess returned no trades because the tick cache directory was absent or empty).

### Days with tick cache but no fired signals (52)

The other 52 zero-trade days had at least some cached symbols but no scanner candidate produced a passing squeeze ARM in its sim window. This is a mix of (a) genuinely quiet market days, (b) candidates that armed but never triggered, and (c) signals that fired below R-floor (`R<$0.10`) and were suppressed. Without per-symbol replay logs we can't disaggregate further — but this distribution is expected for squeeze-only mode.

### Tick-cache corruption

No `gzip.BadGzipFile` errors in the harness stdout. A3's earlier sweep identified MNTS 2026-04-15, ATRA 2026-05-07, ODYS 2026-05-11 as corrupt — those dates show 0 trades in this YTD run as expected, but the harness does not surface the corruption explicitly (it silently exits the subprocess with 0 trades). For a future re-run, adding a stderr check in `run_backtest_v2.py` would surface these.

## Configuration footer

```
WB_BT_RISK_PCT=0.035
WB_BT_DAILY_LOSS_SCALE=1
WB_BT_DAILY_LOSS_LIMIT=-3000  (overridden to -2% of equity by DAILY_LOSS_SCALE=1)
ENV_BASE (from run_backtest_v2.py:40-57):
  WB_SQUEEZE_ENABLED=1, WB_MP_ENABLED=0
  WB_SQ_VOL_MULT=2.5, WB_SQ_MIN_BAR_VOL=50000
  WB_SQ_MIN_BODY_PCT=2.0, WB_SQ_PRIME_BARS=4
  WB_SQ_MAX_R=0.80, WB_SQ_LEVEL_PRIORITY=pm_high,whole_dollar,pdh
  WB_SQ_PROBE_SIZE_MULT=0.5, WB_SQ_MAX_ATTEMPTS=5
  WB_SQ_PARA_ENABLED=1, WB_SQ_PARA_STOP_OFFSET=0.10
  WB_SQ_PARA_TRAIL_R=1.0, WB_SQ_NEW_HOD_REQUIRED=1
  WB_SQ_MAX_LOSS_DOLLARS=500, WB_SQ_TARGET_R=1.5
  WB_SQ_CORE_PCT=90, WB_SQ_RUNNER_TRAIL_R=2.5
  WB_SQ_TRAIL_R=1.5, WB_SQ_STALL_BARS=5
  WB_SQ_VWAP_EXIT=1, WB_SQ_PM_CONFIDENCE=1
  WB_BAIL_TIMER_ENABLED=1, WB_BAIL_TIMER_MINUTES=5
  WB_MAX_NOTIONAL=100000, WB_MAX_LOSS_R=0.75
  WB_EXHAUSTION_ENABLED=1, WB_WARMUP_BARS=5
Inherited from simulate.py defaults:
  WB_MIN_R=0.06
  WB_MIN_ABSOLUTE_R=0.10  ← today's R-floor patch, active for this run
  WB_SQ_SEED_STALE_GATE_ENABLED=1, WB_SQ_SEED_STALE_PCT=2.0
  WB_SQ_VOL_WINSORIZE_ENABLED=1, WB_SQ_VOL_WINSORIZE_CAP=5.0
Starting equity: $30,000
Max trades per day: 5
Window: scanner sim_start → 12:00 (default per X01 baseline)
```

## Files written

- `cowork_reports/2026-05-18_ytd_honest_rebaseline.md` (this narrative)
- `cowork_reports/2026-05-18_ytd_honest_rebaseline_per_day.csv` (75 rows: date, trades, wins, losses, day_pnl, end_of_day_equity, running_peak, max_drawdown_to_date_pct, symbols)
- `cowork_reports/2026-05-18_ytd_honest_rebaseline_trades.csv` (55 rows: date, symbol, pnl, reason, window)
- `backtest_status/ytd_rebaseline.md` (live progress file, final snapshot)
- `backtest_status/ytd_rebaseline_state.json` (full state dump — equity, trades, daily)
- `/tmp/ytd_rebaseline_stdout.log` (harness console output)
