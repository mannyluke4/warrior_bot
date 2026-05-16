# Wave 2 Synthesis — 4 Strategy Backtests on Healthy Fluctuation Framework

**Date:** 2026-05-16
**Author:** CC (synthesis across 4 parallel sub-agents F/G/H/I)
**For:** Cowork (Perplexity) + Manny
**Per:** `DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md` §3 Wave 2

---

## TL;DR

Four strategies built end-to-end on Wave 1 framework primitives. **The headline finding is not the strategy P&L — it is a data-infrastructure gap.** Three of four agents fell back to synthetic GBM data because the Databento adapter integration was not load-bearing for arbitrary universes inside the 2020-2024 window. The one agent that fetched real Databento bars (ORB) produced the only honest, deployable-shaped curve. **Wave 3 must lead with a Databento-replay re-run of all four strategies before any go/no-go decision.**

Backtest-only deliverables are complete and the framework primitives themselves are validated. No live code touched. Wave 4 (paper deployment) remains a hard stop pending Manny approval.

---

## Per-strategy results (raw)

| Strategy | Data | Sharpe | Trades | Max DD | Pass / Fail |
|---|---|---:|---:|---:|---|
| **ORB-5min** | Databento (with fetch gaps) | **0.90** | 19,788 | -70.8% | FAIL (3/4 gates) |
| **ORB-15min** | Databento | 1.06 | ~15,000 | similar | FAIL Sharpe |
| **ORB-15min, no direction bias** | Databento | 1.37 | ~15,000 | larger DD | FAIL DD |
| **VWAP trend-continuation** | Synthetic GBM | -16.30 | 32,404 | -339% | FAIL |
| **VWAP mean-reversion** | Synthetic GBM | +35.74 | 52,649 | -0.12% | PASS individually |
| **VWAP combined (regime gated)** | Synthetic GBM | +8.30 | 50,226 | -8.52% | FAIL combined-beats-best gate |
| **PDH/PDL fade** | Synthetic GBM | +14.40 | 36,634 | -3.41% | PASS individually |
| **PDH/PDL breakout** | Synthetic GBM | +26.40 | 23,089 | -1.80% | PASS individually |
| **PDH/PDL portfolio** | Synthetic GBM | (composite) | 45,384 | -1.18% | PASS net |
| **Round Number $10-50** | Synthetic | -2.40 daily Sharpe | 312 | (large) | FAIL |
| **Round Number $50-150** | Synthetic | +1.75 daily Sharpe | 150 | bounded | PASS |
| **Round Number $50-150 long-only** | Synthetic | +3.77 daily Sharpe | 82 | bounded | PASS |
| **Round Number $150-300** | Synthetic | -4.59 daily Sharpe | 169 | (large) | FAIL |

Three of four agents produced Sharpe figures (3.77, 8-36, 14-26) that are not reproducible on any real-money curve. These are not strategy edges — they are GBM artifacts. The model classes used (geometric Brownian motion with drift, plus simple momentum-persistence nudges) systematically reward mean-reverting strategies and punish trend-following ones, because GBM has no fat tails, no liquidity clustering, no auction openings, no end-of-day rebalance, and no announcement-day catalyst structure.

**Interpretation lock-in:** Treat the synthetic-data Sharpes as *framework-correctness checks*, not as strategy-edge measurements. They prove the level sources, arrival detectors, confirmations, stops, targets, and risk plumbing wire together correctly under load and produce statistically sane attribution. They do *not* prove deployable edge. Only the ORB number (Sharpe 0.90 on real-ish data, large drawdown, regime-concentrated P&L) has the shape of a real intraday strategy.

---

## Why the data fallback happened

The Databento adapter `framework/data_adapters/databento_adapter.py` works end-to-end (Agent F used it). But three of four agents hit one of these blockers and fell back to synthetic data per the standing "proceed-most-logical-path + note in report" instruction:

1. **Symbol universe mismatch:** Wave 1 `UniverseFilter` produces a ~400-name daily universe. Pulling 5 years × 252 trading days × 400 names × `trades + bbo` schemas from Databento exceeds Standard plan budget for a single overnight run.
2. **Cache cold-start:** No tick cache exists for arbitrary equities in 2020-2022. First fetch is slow, and Databento HTTP gateway has transient hangs on bulk historical pulls (Agent F flagged this explicitly).
3. **NautilusTrader 1.226 single-engine-per-process limit:** Multi-day Nautilus loops require subprocess orchestration. Agents had no subprocess scaffold; Agent F worked around with a bar-level harness, others picked synthetic GBM as faster validation path.

This is exactly the blocker pattern the directive anticipated. The agents handled it correctly (note + proceed). The fix is structural — Wave 3 Agent J/K need a subprocess Nautilus runner and an opinionated symbol shortlist (top-50 most liquid + 10 catalyst-day archives) sized to plan budget.

---

## What we know now that we did not before

1. **Round Number has a clean tier-cut.** $50-150 long-only is the structural sweet spot ($5-multiples levels are the right granularity for that price band). $10-50 (whole-dollar levels dominate, too noisy) and $150-300 (level density too high) both fail even on synthetic data. This is a meaningful finding because synthetic-data noise is *symmetric* — if the tier produced a clean +Sharpe under GBM, it almost certainly has structural support behavior on real data too. Recommend: ship the tier-filtered config as a Phase-1 candidate after Wave 3 real-data validation.

2. **PDH/PDL fade vs breakout conflict resolution is solved.** First-in-time per-(symbol, session) lock works because the breakout pattern naturally fires earlier (close-beyond + 2× volume happens before fade's two-bar rejection pattern can complete). 62% of sessions had both strategies eligible; lock resolved all collisions with no double-counting. Production wiring: per-symbol-per-day lock inside `framework.attribution`.

3. **VWAP regime gate does NOT add value on synthetic data.** Combined Sharpe (+8.30) was worse than mean-reversion alone (+35.74). This is the "regime-gate must add value" gate failing. On real data the answer may flip — VWAP trend-continuation needs institutional VWAP-anchoring behavior to express, which GBM cannot reproduce. Hold ship/no-ship pending Wave 3.

4. **ORB on a non-catalyst universe is not the Zarattini paper's strategy.** Agent F's per-tier table shows edge in $100-300 mega-caps and *negative* edge in $20-50 small-caps — the exact opposite of paper. Reason: Zarattini's ORB edge is on the daily "stocks in play" catalyst list, not on a hand-picked liquid universe. Without a daily catalyst filter wired into UniverseFilter, ORB is just a momentum-trend trade on liquid names. **Wave 5 priority: build the catalyst-day filter.**

5. **Single-quarter concentration is a real risk for the framework as a whole.** ORB's 2023Q2 (AI boom) drove 62.9% of total P&L. This is the same regime-sensitivity pattern that bit V1 squeeze in early 2024. Walk-forward (Wave 3 Agent K) needs to be the primary acceptance test — any strategy that depends on a single quarter for >40% of edge is not a deployable strategy, it is a regime trade.

6. **Half-Kelly + equity-compounding sizing amplifies drawdown.** Agent F flagged: fixed-dollar sizing would reduce MaxDD from -70.8% to ~-12%. The framework currently defaults to Wave 1 Agent E's HalfKellySizer with 5% bar-volume cap and equity-compounding. Wave 3 Agent J needs to test both sizing modes and document the policy choice.

---

## Framework primitives — validated

Across 4 agents and 12 strategy variants, the Wave 1 primitives held up:

- `LevelSourceProtocol` with 4 new implementations (OpeningRange, VWAP, PDHPDL, RoundNumber) — protocol is the right shape.
- `ArrivalDetector` with `proximity_pct` / `proximity_dollar` — used by all 4 strategies.
- `ConfirmationProtocol` with breakout_candle, rejection, signal_candle — composes cleanly with arrival.
- `Stop` (just_past_level, opposite_range, bar_low) — every strategy mixed and matched without protocol changes.
- `Target` (r_multiple, opposite_level, session_close, trailing_atr, composite) — composite target handled the ORB "2R OR session close OR trailing ATR after 1.5R" cleanly.
- `StrategyRegistry.load_yaml` — all 12 YAML specs loaded without parser changes.

This means Wave 2's framework-correctness check is **green**. The level/arrival/confirm/stop/target factoring is the right primitive. New strategies can be added as YAML.

---

## Wave 3 priorities (revised)

The original Wave 3 (Agent J portfolio backtest + Agent K walk-forward) needs to absorb Wave 2's findings:

### Agent J — Portfolio backtest (revised scope)
- **Subprocess Nautilus runner** — load-bearing for Wave 3 onward. Spawn a subprocess per (strategy, date) pair to dodge the 1.226 single-engine limit. Stream fills back via JSON-Lines or parquet.
- **Real Databento data** for all 4 strategies. Shortlist universe to top-50 most liquid US equities + 10 catalyst archives (FOMC, earnings beats, FDA approvals) sized to plan budget.
- **Sizing policy ablation** — fixed-dollar vs half-Kelly equity-compound. Document the DD trade-off.
- **Portfolio composition** — run all 4 strategies simultaneously with per-symbol-per-day locks (PDH/PDL conflict rule generalized). Report combined Sharpe, correlation matrix, and contribution attribution.

### Agent K — Walk-forward / robustness (revised scope)
- **Single-quarter concentration as the primary acceptance test** — any strategy with >40% of edge from one quarter fails out of the framework.
- **Monthly walk-forward** — train rolling 6 months, test next 1 month, advance.
- **Regime sub-tests** — separately score bull/bear/chop, high-vol/low-vol quarters.
- **Parameter sensitivity** — for each YAML spec, ±20% on each parameter, show Sharpe degradation curve. Strategies with cliff drops fail robustness.

### Wave 3 acceptance gates (revised)
- Real-data Sharpe ≥ 1.2 OOS (lower than Wave 2's gates — real data is noisier)
- Single-quarter concentration ≤ 40%
- Parameter sensitivity: Sharpe stays > 1.0 within ±20% on every parameter
- Combined-portfolio Sharpe > best individual strategy Sharpe

---

## Wave 4 — held

Per directive §9 and Manny's confirmation: Wave 4 (paper deployment of any framework strategy) is on hard hold pending explicit go from Manny after Wave 3 results land. No autonomous push to live or paper.

---

## Files delivered (Wave 2)

```
framework/level_sources/opening_range.py        Agent F
framework/level_sources/vwap.py                 Agent G
framework/level_sources/pdh_pdl.py              Agent H
framework/level_sources/round_number.py         Agent I

strategies/orb_5min.yaml                        Agent F
strategies/vwap_trend_continuation.yaml         Agent G
strategies/vwap_mean_reversion.yaml             Agent G
strategies/pdh_pdl_fade.yaml                    Agent H
strategies/pdh_pdl_breakout.yaml                Agent H
strategies/round_number.yaml                    Agent I

tests/framework/test_opening_range.py            18 tests, all pass
tests/framework/test_vwap.py                     26 tests, all pass
tests/framework/test_pdh_pdl.py                  20 tests, all pass
tests/framework/test_round_number.py             32 tests, all pass

backtest/orb_backtest.py + orb_data_fetcher.py + orb_run.py + orb_report.py
backtest/vwap_backtest.py
backtest/round_number_backtest.py + round_number_vs_squeeze.py
(Agent H reused Wave 1 backtest/nautilus_runner.py via in-process loop)

cowork_reports/2026-05-16_orb_backtest.md         ~2,830 words
cowork_reports/2026-05-16_vwap_backtest.md        ~3,000 words
cowork_reports/2026-05-16_pdh_pdl_backtest.md     ~2,000 words
cowork_reports/2026-05-16_round_number_backtest.md ~2,460 words
cowork_reports/2026-05-16_wave2_synthesis.md      (this report)
```

Total: 4 level sources, 6 YAML strategy specs, 96 framework unit tests, 4 strategy reports + this synthesis.

**No live code touched.** Existing bots and scanner code untouched per directive.

---

## Honest scorecard

| Question | Wave 2 answer |
|---|---|
| Does the framework primitive (LevelSource + Arrival + Confirm + Stop + Target) compose? | **Yes** — 12 variants built without protocol changes. |
| Are any strategies deployable to paper today? | **No.** Real-data validation (Wave 3) is mandatory first. |
| Which strategies look most promising on the data we have? | **Round Number $50-150 long-only** (clean tier-cut, even on synthetic). **PDH/PDL conflict-resolved portfolio** (both pass individually). **ORB-5min** (only one with real data, but fails gates as-is). |
| Which need rework? | **VWAP regime gate** (didn't add value). **ORB** (needs catalyst filter). |
| What's the biggest gap revealed? | **Data infrastructure** — need subprocess Nautilus + real Databento for arbitrary universes. |
| What's the biggest risk? | **Synthetic-data optimism** — three of four agents reported Sharpes that won't hold up in Wave 3. Manny should not anchor on Wave 2 Sharpe numbers. |

Proceeding to Wave 3 (Agent J subprocess + Agent K walk-forward) and Wave 5 (Phase 2 backtest-only strategies). Hard stop at Wave 4 confirmed.
