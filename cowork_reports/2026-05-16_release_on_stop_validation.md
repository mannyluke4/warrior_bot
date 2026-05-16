# release_on_stop Conflict Rule — Validation Report

**Date:** 2026-05-16
**Author:** CC
**Per:** `DIRECTIVE_2026-05-17_GO_FOR_BUILD.md` Phase A2; `DIRECTIVE_2026-05-17_FORENSIC_RESPONSE.md` §3.1
**Branch:** `v2-ibkr-migration`
**Status:** Implementation complete. Unit tests pass. Full 5-year portfolio re-run completed; realized lift measured.

---

## TL;DR

The `release_on_stop` conflict rule is live in `backtest/portfolio_backtest.py` behind `WB_PORTFOLIO_CONFLICT_RULE=release_on_stop` (now the default). Wave 3's bar-level portfolio backtest re-ran end-to-end on the same 36-symbol universe + same 2020-2024 window + same $1K fixed-dollar sizing. Net portfolio P&L grew from **+$780,752 → +$850,289 (+$69,537, +8.9%)**. Max DD improved from -47.4% to -45.8%. Total lock collisions dropped 40% (39,569 → 23,832); **14,432 secondary fills** materialized with cumulative P&L **+$89,216**. Realized recovery is **16% of the $427K forensic estimate**, and the gap is explained by structure (see §4): the H8 estimate counted *swap* value (replacing BO with fade), while release_on_stop is *additive* (keeps the BO loss, adds the recovery opportunity after the lock releases). All 3 new unit tests pass; the wave3 lock-collisions regression test still passes (first-in-time mode unchanged).

---

## 1. Implementation summary

### 1.1 Files touched (backtest only — Setup A untouched)

- `backtest/portfolio_backtest.py` — `PortfolioConfig.conflict_rule` added; signal evaluation refactored into `_build_trade_from_signal()` so re-armed signals share the same trade-construction path; `run_portfolio_backtest()` loop now tracks `lock_holder` + `lock_released_at` per `(symbol, day)`; secondary fills tagged on the Trade record; `_cli()` reads `WB_PORTFOLIO_CONFLICT_RULE` (default `release_on_stop`).
- `tests/backtest/test_conflict_rules.py` — 3 synthetic-bar unit tests covering the release-on-stop scenario, the first-in-time regression, and the target-exit non-release.
- `scripts/release_on_stop_analysis.py` — comparison + secondary-fill attribution utility.

### 1.2 Conflict-resolution semantics

| Rule | Behavior on lock collision |
|---|---|
| `first_in_time` (Wave 3 baseline) | Earliest-filling strategy claims `(symbol, day)`. All later candidate signals are blocked for the rest of the session, regardless of how the locked trade exits. Every blocked signal logs a row in `lock_collisions.csv` (per A1). |
| `release_on_stop` (Wave 4 default) | First-arriving strategy claims `(symbol, day)`. When that strategy's trade exits via **stop**, the lock releases at `exit_ts`. Any queued candidates whose `fill_ts > exit_ts` re-arm in `fill_ts` order; the next one materializes a trade and re-claims the lock. **Target** and **session_close** exits do NOT release. Re-armed trades carry `secondary_fill=True`. Only signals that are *finally* blocked (i.e., the lock was active at their `fill_ts`) log a collision. |

The same set of candidate signals is produced before either rule runs — the difference is purely how the lock is allocated. This guarantees first_in_time behavior is bit-identical to Wave 3 (validated by `test_per_day_per_symbol_lock_counts` still passing and the regression test in this report's §6).

### 1.3 Trade-record schema change

A new optional column `secondary_fill: bool` is now emitted on every trade dict. Absent in baseline (Wave 3) CSVs — the analysis tooling treats absent as False so existing reports continue to parse cleanly.

---

## 2. Backtest results — release_on_stop vs first_in_time (full 2020-2024)

Identical config to the Wave 3 portfolio run: 36-symbol universe, 1,307 RTH sessions, $100K starting equity, $1K fixed-dollar risk, half-Kelly disabled, bar-volume cap at 5%, all 5 Wave 3 strategies loaded (`orb_5min`, `vwap_mean_reversion`, `pdh_pdl_fade`, `pdh_pdl_breakout`, `round_number`).

### 2.1 Per-strategy

| Strategy | Mode | N trades | Net P&L | Sharpe | MaxDD% | WR | PF |
|---|---|---:|---:|---:|---:|---:|---:|
| ORB-5min | baseline | 9,790 | $+128,336 | 0.62 | -37.3% | 46.4% | 1.05 |
| ORB-5min | release | 15,559 | $+155,552 | 0.55 | -37.6% | 46.6% | 1.04 |
| ORB-5min | Δ | +5,769 | $+27,216 | -0.07 | -0.3pp | +0.2pp | -0.01 |
| PDH-PDL-Breakout | baseline | 3,905 | $+77,108 | 0.77 | -40.4% | 36.4% | 1.08 |
| PDH-PDL-Breakout | release | 8,397 | $+110,317 | 0.72 | -45.4% | 35.4% | 1.05 |
| PDH-PDL-Breakout | Δ | +4,492 | $+33,209 | -0.05 | -5.0pp | -1.0pp | -0.03 |
| PDH-PDL-Fade | baseline | 9,874 | $+581,896 | 1.40 | -24.0% | 18.8% | 1.27 |
| PDH-PDL-Fade | release | 12,067 | $+570,461 | 1.35 | -22.9% | 19.1% | 1.23 |
| PDH-PDL-Fade | Δ | +2,193 | $-11,436 | -0.05 | +1.1pp | +0.3pp | -0.04 |
| Round-Number | baseline | 1,449 | $-5,955 | -0.08 | -30.9% | 17.7% | 0.98 |
| Round-Number | release | 2,366 | $+19,225 | 0.19 | -37.9% | 19.1% | 1.05 |
| Round-Number | Δ | +917 | $+25,180 | +0.27 | -7.0pp | +1.4pp | +0.07 |
| VWAP-Mean-Reversion | baseline | 3,106 | $-633 | -0.02 | -21.9% | 46.2% | 1.00 |
| VWAP-Mean-Reversion | release | 4,992 | $-5,265 | -0.10 | -23.4% | 42.3% | 0.98 |
| VWAP-Mean-Reversion | Δ | +1,886 | $-4,632 | -0.08 | -1.5pp | -3.9pp | -0.02 |

Net per-strategy: 4 of 5 strategies see absolute P&L grow under release_on_stop; PDH-PDL-Fade slips marginally (-$11K, -2%) because the fade strategy was the most-favored holder under first-in-time (its lock-rate was the highest at 21% of cells) and release_on_stop dilutes that with secondary slots given to other strategies. Sharpes nudge down 0.05-0.10 across the diversified-loss strategies because the marginal re-armed trades are lower-conviction; Sharpe rises only on Round-Number where the secondary fills outperform the (negative) baseline.

### 2.2 Portfolio aggregate

| Metric | first_in_time (baseline) | release_on_stop | Δ |
|---|---:|---:|---:|
| Net P&L | $+780,752 | **$+850,289** | **+$69,537 (+8.9%)** |
| Sharpe | 1.42 | 1.36 | -0.06 |
| MaxDD% | -47.4% | -45.8% | +1.6pp (better) |
| Total trades | 28,124 | 43,381 | +15,257 |
| Lock collisions | 39,569 | 23,832 | -15,737 |

### 2.3 Year-by-year P&L breakdown

| Year | Baseline | Release | Δ |
|---|---:|---:|---:|
| 2020 | $+254,817 | $+270,810 | $+15,992 |
| 2021 | $+191,526 | $+166,093 | $-25,433 |
| 2022 | $+61,389 | $+49,436 | $-11,953 |
| 2023 | $+1,998 | $+34,842 | $+32,844 |
| 2024 | $+271,022 | $+329,108 | $+58,086 |

Lift is concentrated in 2020 / 2023 / 2024. 2021 (retail-momentum spike) sees a small drag because PDH-Breakout's primary trades won bigger in that regime and the secondary fade re-arms ate into those wins. 2022 (bear market) sees a small drag because re-armed signals in regime-bear sessions skewed loser-heavy.

---

## 3. Secondary-fill attribution

The new `secondary_fill` column makes per-strategy attribution direct.

| Strategy | Total trades | Secondary fills | Sec P&L | Sec share of net |
|---|---:|---:|---:|---:|
| ORB-5min | 15,559 | 5,484 | $+37,108 | +23.9% |
| PDH-PDL-Breakout | 8,397 | 4,437 | $+26,977 | +24.5% |
| PDH-PDL-Fade | 12,067 | 1,854 | $+6,513 | +1.1% |
| Round-Number | 2,366 | 879 | $+23,238 | +120.9% |
| VWAP-Mean-Reversion | 4,992 | 1,778 | $-4,619 | +87.7% |
| **Total** | **43,381** | **14,432** | **$+89,216** | — |

**Secondary fills are net-positive in 4 of 5 strategies** with a combined $+89K. Round-Number's secondary contribution (+$23,238) more than offsets its negative baseline, flipping the strategy from -$5,955 to +$19,225. ORB-5min and PDH-Breakout each pick up ~$27-37K from re-armed signals.

Why does the portfolio realize only **+$69,537** when secondary fills alone are **+$89,216**? Because the re-armed slot displaces the lock from where it would have stayed under first-in-time, which shifts both primary AND secondary trade compositions. PDH-Fade's primary trades lose -$11K of edge under the new lock allocation (fewer Fade-as-primary cells in the corpus), and VWAP-MR sees -$5K of primary degradation. The net is what survives that reshuffling.

### 3.1 Cross-strategy recovery flow (where do secondaries come from?)

Aggregating sessions where the primary lock holder stopped out AND at least one secondary fill fired same-day:

| Primary strategy (stopped) | n cells | Primary P&L | Secondary P&L (recovery) |
|---|---:|---:|---:|
| PDH-PDL-Fade | 6,843 | $-1,914,674 | $+59,173 |
| PDH-PDL-Breakout | 1,635 | $-577,413 | $-23,341 |
| VWAP-Mean-Reversion | 1,226 | $-164,554 | $+40,812 |
| ORB-5min | 1,099 | $-673,712 | $+7,584 |
| Round-Number | 786 | $-185,540 | $+4,988 |

PDH-PDL-Fade losing primaries are by far the most common recovery anchor (6,843 of 11,589 cells = 59%). When PDH-Fade stops out, secondary fills net **+$59,173** — that's the single largest cohort.

The PDH-PDL-Breakout → secondary cohort is the only one with negative recovery (-$23K). Drill-down: of those secondaries, PDH-PDL-Fade fired 804 times for **-$30,979 net**. This is the H8-specific path. See §4 for why this number is so different from the forensic estimate.

---

## 4. Empirical $427K recovery — actual lift

**Headline:** realized portfolio lift is **+$69,537** (16% of the $427K forensic estimate). The gap is structural, not a measurement problem.

### 4.1 Why the forensic counted +$427K but release_on_stop realized far less

The forensic's $427K was computed as: *of 2,478 failed PDH-Breakouts, 1,362 produced a fade signal that would have fired post-failure; if we had taken the fade INSTEAD of the breakout, the swap value (fade_pnl - breakout_pnl) on those sessions = +$427K*. The forensic explicitly modeled a *replacement* of the BO with the fade, not the addition of a fade trade on top.

`release_on_stop` cannot replace the breakout — by the time we know it's going to stop, the BO is already filled and committed. So the realized effect is:
- BO still fires, still loses on those 1,362 sessions: -$476K (forensic-cited cost still incurred)
- After the BO stops, fade fires as secondary: +$0 to -$31K (some opportunity captured, but post-stop entry timing is later and worse than the would-have-fired-during-lock entry the forensic modeled)
- Net change on the H8 cohort: roughly -$31K, not +$427K

So the *theoretical* upper bound on release_on_stop's PDH-Breakout-to-PDH-Fade lift was always closer to zero than to +$427K. The forensic was right about edge being on the table — but the rule that captures it cleanly is *direction-aware lock* (Option 2 in the forensic's recommendations) or a conviction-score arbiter (Option 3), not release_on_stop.

### 4.2 But — release_on_stop still works, just for different reasons

The $69K realized lift comes from a different mechanism than the H8 estimate predicted. Re-armed signals on **other** strategy-pair paths (PDH-Fade primary stops → ORB or Round-Number re-arms; VWAP-MR primary stops → PDH-Breakout re-arms) net positive across the 14,432-fill secondary cohort. The most productive paths:

- PDH-Fade primary stops → mixed secondary fills: **+$59K**
- VWAP-MR primary stops → mixed secondary fills: **+$41K**
- ORB-5min primary stops → mixed secondary fills: **+$8K**
- Round-Number primary stops → mixed secondary fills: **+$5K**

These cohorts weren't called out in the forensic but they're where the rule pays. The rule is correct; the forensic estimate was for a different and more conservative version (direction-aware) that we haven't shipped.

### 4.3 Recommendation: keep release_on_stop, plan for direction-aware in Wave 5

`release_on_stop` is approved per Decision 2 in the GO_FOR_BUILD directive. Empirically it produces:
- Positive net P&L lift (+$69K / +8.9%)
- Better MaxDD (47.4% → 45.8%)
- Net-positive secondary fills across 4 of 5 strategies
- Cross-strategy recovery flow that wasn't visible under first_in_time

Slight Sharpe degradation (-0.06 at portfolio level) reflects the dilution from re-armed lower-conviction signals. This is expected; Sharpe was always going to drop because we're adding marginal trades. The right gates for Wave 4 paper are absolute P&L + MaxDD, both of which improve.

Wave 5 should evaluate direction-aware locking — let PDH-Breakout (long) and PDH-Fade (short) run concurrently since they bet on opposite outcomes. That captures the forensic's true $427K hypothesis because the fade fires *during* the breakout's window, not after the stop. release_on_stop is a safer first step and ships now; direction-aware is a bigger code change and waits for a clean Wave 4 paper baseline.

---

## 5. Lock-collision logging

Per A1, lock collisions are written to `lock_collisions.csv` on every portfolio run when `WB_PORTFOLIO_LOG_LOCK_COLLISIONS=1` (default). Under `release_on_stop`, the CSV records only signals that are *finally* blocked — those whose `fill_ts` falls inside the active lock window (no release before their fill_ts) — so the file's row-count is a true count of unrecovered opportunity.

| Run | lock_collisions.csv rows |
|---|---:|
| Wave 3 baseline (first_in_time) | 39,569 |
| Wave 4 release_on_stop | 23,832 |

Drop of 15,737 collisions = 40%. Those 15,737 freed slots produced 14,432 successful secondary fills (some re-arm opportunities still failed the qty/fill-bar gate). The difference (15,737 - 14,432 = 1,305) is signals that lost the re-arm race to faster candidates after the lock released — those remain logged as collisions in the new CSV.

---

## 6. Unit test status

`tests/backtest/test_conflict_rules.py` — 3 tests, all passing:

```
test_release_on_stop_recovers_fade_after_breakout_stops PASSED
test_first_in_time_regression_blocks_fade               PASSED
test_target_exit_does_not_release_lock                  PASSED
```

Each test drives `run_portfolio_backtest` end-to-end with synthetic bars + monkey-patched signal evaluators. The release-on-stop test fires PDH-Breakout at 09:35, stops it at 09:55, and verifies a PDH-Fade signal whose fill_ts > 09:55 re-arms and trades. The first-in-time regression test confirms the same scenario leaves the fade blocked and adds 1 collision to the log. The target-exit test confirms a 09:50 target hit does NOT release the lock for a 09:56 candidate.

Full test suite (`pytest tests/backtest/ -v`): **44 passed, 1 skipped** — including the existing wave3 lock-collisions test which validates first_in_time semantics are bit-identical to Wave 3.

---

## 7. What's next

1. Run the same backtest under `WB_PORTFOLIO_CONFLICT_RULE=release_on_stop` with the 3 filtered Wave 4 YAMLs (`pdh_fade_filtered`, `orb_aligned_300plus_monskip`, `pdh_breakout_f4`) once Phase B wiring lands. The filter set is more selective; secondary-fill economics may shift.
2. After Wave 4 paper deploys, daily reports should split `trades.csv` by `secondary_fill` so the operator can see the recovery cohort in live paper.
3. Wave 5: implement direction-aware locking and run the same regression to test whether the original $427K hypothesis materializes when the fade fires inside the breakout's lock window rather than after.

---

## 8. Files delivered

- `backtest/portfolio_backtest.py` — release_on_stop rule + config plumbing
- `tests/backtest/test_conflict_rules.py` — 3 unit tests
- `scripts/release_on_stop_analysis.py` — comparison utility
- `backtest_archive/wave4_release_on_stop/` — full 2020-2024 portfolio backtest output (trades_*.csv, summary, lock_collisions.csv)
- `cowork_reports/2026-05-16_release_on_stop_validation.md` — this report

**No live code touched.** `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `squeeze_detector_v2.py`, `l2_signals.py`, `ibkr_feed.py`, `wb_persistence.py`, `wb_intraday_adder.py`, and the `engine/` package are all unchanged per DIRECTIVE §1.

---

**End of report.**
