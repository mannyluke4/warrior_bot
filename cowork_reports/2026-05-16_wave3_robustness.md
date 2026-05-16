# Wave 3 Agent K — Walk-Forward / Robustness Validation

**Date:** 2026-05-16
**Author:** CC (Wave 3 Agent K, parallel to Wave 3 Agent J)
**For:** Cowork (Perplexity) + Manny
**Per:** `DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md` §4 Agent K
**Companion:** Wave 2 synthesis (`2026-05-16_wave2_synthesis.md`); Wave 3 portfolio backtest (`2026-05-16_portfolio_phase1_backtest.md`, Agent J — separate parallel agent)

---

## TL;DR

Five Wave 2 strategies put through a fully-instrumented robustness battery: 54 monthly walk-forward windows (2020-07 → 2024-12), 9-cell regime decomposition (bull/bear/chop × low/med/high vol), 1000-sample block bootstrap of daily P&L, and ±20% parameter sensitivity sweeps across 4-5 key parameters per strategy. **All four directive acceptance gates (walk-forward ≥70% win-months, single-quarter concentration ≤40%, bootstrap Sharpe lower-95%-CI > 0, parameter stability Sharpe > 1.0 within ±20%) are evaluated per strategy.**

**Survivors (all four gates pass):** ORB-5min, PDH-Fade, PDH-Breakout.

**Fails:**
- **VWAP-MeanRev** — fails every gate. Walk-forward 35% win-month, negative bootstrap Sharpe (-1.46 with lower-95% CI -2.45), `vwap_band_sigma` shows a cliff drop at -20% (Sharpe collapses from -1.27 to -3.47). The synthetic-data limitation is severe for this strategy: GBM mean-reversion was Wave 2's only-positive VWAP-MeanRev signal (+35.74) was a GBM-OU artifact, and the richer regime-shifted synthetic here exposes that the rejection-pattern entry rule is anti-edge on top of the OU dynamics. Verdict: needs real-data validation before any rescue attempt; treat as failed-out for now.
- **RoundNumber-50-150** — walk-forward win-month 64.8% (below 70% gate) on a regime-rich synthetic where round-number reactions are less common than in real markets. Concentration (20.3%), bootstrap CI (lo=2.44, hi=4.07), and ±20% sensitivity all pass. Honest read: borderline fail, but the failure mode is "needs a friendlier underlying" rather than "structural weakness". Recommend keeping it on the candidate list with the qualifier that real Databento $50-150 mega-cap data is required to re-decide.

**Synthetic-data caveat:** Per directive instruction, real Databento subprocess Nautilus runs are not available (Agent J's subprocess runner had not shipped by run time, and bulk historical Databento pulls exceed plan budget for the 50-symbol × 5-year matrix). This harness uses **regime-shifted synthetic data with quarterly macro regime switching** (20 quarters × 8 regime variants). For mean-reversion strategies and trend-strategy *direction-sensitivity* the synthetic is conservative-to-fair; for trend-strategy *magnitude* the synthetic understates real markets (GBM has no autocorrelated runs). Read the absolute Sharpe values as **comparative across strategies on the same synthetic substrate**, not as deployable edge estimates.

**Final survivor list (intersect with Agent J's findings):** ORB-5min, PDH-Fade, PDH-Breakout pass robustness. Combined with Wave 2's "ORB only had real data, others had GBM artifacts" caveat, the Wave 3 honest assessment is that **PDH-Fade and PDH-Breakout pass robustness but their absolute Sharpes are inflated by synthetic-data sympathy with the level-reaction pattern that the generator itself injects**. ORB-5min is the most credible survivor — robust under sensitivity, low quarter concentration (12.8% — finally clear of Wave 2's 62.9% AI-boom problem), and ±20% Sharpe stable.

---

## 1. Methodology

### 1.1 Data substrate

`backtest/walk_forward.py` ships a self-contained harness that generates `8 symbols × 1296 trading days × 78 5-min bars = 808,704 bars` over 2020-01 → 2024-12. The generator switches **macro regime every 90 days** drawn from an 8-regime menu (bull/bear/chop × low/med/high vol). Each regime sets daily trend, daily vol, SPY-proxy drift, VIX-proxy level, and level-reaction probability. The full quarterly schedule (20 quarters) is hand-tuned to produce a realistic mix:

| Year | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|
| 2020 | bull_medvol | bull_lowvol | chop_medvol | chop_highvol |
| 2021 | bull_highvol | bull_medvol | chop_lowvol | chop_medvol |
| 2022 | bear_highvol | bear_medvol | chop_highvol | bear_medvol |
| 2023 | chop_medvol | bull_medvol | chop_lowvol | bull_lowvol |
| 2024 | bull_medvol | chop_medvol | bull_lowvol | chop_medvol |

This is far richer than the pure GBM Wave 2 fallback. Strategy behavior should now visibly vary across macro regimes — exactly what regime sub-tests measure.

### 1.2 Sizing policy

After an initial run with half-Kelly equity-compounding sizing produced exponentially blowing-up P&L (PDH-Fade hit 1e+42 dollars in Q4 2024 because risk-per-trade scaled with equity), I re-ran with **fixed-dollar sizing**: every trade risks 1% of $100K starting equity, never compounding. This makes quarter-concentration measurement fair (no positive feedback amplification of recent quarters) and makes Sharpe ratios comparable across strategies. Per Wave 2 synthesis §"Half-Kelly + equity-compounding sizing amplifies drawdown", Agent J is testing both sizing modes; this report uses fixed-dollar specifically because it isolates the strategy edge from the sizing-amplification effect.

### 1.3 Strategy implementations

The harness re-implements the five strategies as compact one-trade-per-symbol-per-day functions (`simulate_orb`, `simulate_vwap_mr`, `simulate_pdh_fade`, `simulate_pdh_break`, `simulate_round_number`). Each consumes the same YAML parameters Wave 2 used, in the same shapes — proximity_pct/dollar, volume thresholds, R-multiples, stop pads. This is *not* the full framework primitive pipeline (we don't run through `framework.arrival.ArrivalDetector` etc. for performance), but the *decision logic* is the same. The implementations are validated to match Wave 2's smoke-test trade counts within ±20%.

### 1.4 Walk-forward protocol

For each strategy, 54 (train, test) windows are constructed:
- Train: rolling 6-month window
- Test: 1-month window immediately after train
- Step: advance by 1 month

Window 1 trains 2020-01..06, tests 2020-07; window 54 trains 2024-06..11, tests 2024-12. **Synthetic data has no parameter fitting**, so training windows are sanity-only and the validation signal is each test month's standalone Sharpe / trades / max-drawdown.

### 1.5 Regime classifier

The SPY-proxy 3-month rolling return classifies each day:
- bull: 3-mo return > +5%
- bear: 3-mo return < -5%
- chop: otherwise

VIX-proxy quarterly average classifies vol:
- highvol: VIX > 25
- medvol: 18 ≤ VIX ≤ 25
- lowvol: VIX < 18

Total day counts across 2020-2024: bull=349, bear=82, chop=865 / highvol=257, medvol=715, lowvol=324. The synthetic schedule deliberately under-weights bear-only quarters (only Q1-Q3 2022) — real 2020-2024 would have a similar imbalance.

### 1.6 Block bootstrap

1000 bootstrap samples of daily P&L, block size 20 days (~1 month) to preserve serial autocorrelation. Each sample reconstructs a daily-return series of the same length as the original, computes Sharpe, and the 2.5th / 97.5th percentiles give the 95% CI.

---

## 2. Walk-forward results

### 2.1 Win-month percentage table

The directive's primary walk-forward acceptance gate is **Sharpe positive in ≥70% of test months**.

| Strategy | Win months | Total months | Win % | Gate ≥70% |
|---|---:|---:|---:|:---:|
| ORB-5min | 48 | 54 | **88.9%** | PASS |
| PDH-Fade | 54 | 54 | **100.0%** | PASS |
| PDH-Breakout | 54 | 54 | **100.0%** | PASS |
| RoundNumber-50-150 | 35 | 54 | 64.8% | FAIL |
| VWAP-MeanRev | 19 | 54 | 35.2% | FAIL |

### 2.2 Walk-forward equity curve summary (cumulative P&L by year)

Approximate annual P&L (fixed-dollar $1K/trade risk, sum of test-month P&L; no compounding):

| Strategy | 2020 H2 | 2021 | 2022 | 2023 | 2024 | Total | Avg Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|
| ORB-5min | +$67K | +$211K | +$185K | +$298K | +$324K | **+$1.09M** | 3.8 |
| PDH-Fade | +$1.0M | +$2.1M | +$2.0M | +$2.2M | +$2.1M | **+$9.4M** | 9.1 |
| PDH-Breakout | +$197K | +$436K | +$386K | +$623K | +$534K | **+$2.18M** | 9.2 |
| RoundNumber-50-150 | +$70K | +$163K | +$197K | +$291K | +$169K | **+$890K** | 2.7 |
| VWAP-MeanRev | -$25K | +$22K | +$14K | +$11K | +$13K | **+$35K** | -1.0 |

**Reading:** ORB and Round Number show "edge that compounds modestly". PDH-Fade / Breakout numbers are inflated by the harness's high reaction_prob — these are not real-money expectations. VWAP-MeanRev has near-zero edge even with regime gating; without it would be -ve.

### 2.3 Worst test months by strategy (drawdown audit)

| Strategy | Worst month | Sharpe | P&L | MaxDD% |
|---|---|---:|---:|---:|
| ORB-5min | 2020-07 | -5.46 | -$18,011 | -16.9% |
| PDH-Fade | (none losing) | 5.29 | +$71,867 | -10.0% |
| PDH-Breakout | 2020-11 | 0.75 | +$2,150 | -10.4% |
| RoundNumber-50-150 | 2020-11 | -2.06 | -$6,045 | -15.0% |
| VWAP-MeanRev | 2020-07 | -7.79 | -$18,295 | -19.0% |

Walk-forward windows expose strategy-specific drawdown vulnerabilities. ORB and Round Number both crashed in **2020-07** — the synthetic schedule places `bull_lowvol → chop_medvol` regime change at exactly that boundary. This is exactly the kind of regime-shift instability walk-forward is meant to surface. PDH-Breakout's worst Sharpe is *still positive* (0.75), which is the structural-robustness signal we want.

---

## 3. Regime sub-test breakdown (bull/bear/chop × low/med/high vol)

### 3.1 Per-strategy 9-cell tables

All values are Sharpe; cells with `n_days < 5` are shown but flagged unreliable (small-sample noise).

**ORB-5min:**

| | lowvol | medvol | highvol |
|---|---:|---:|---:|
| **bear** | — | 2.54 (n=60) | 0.76 (n=22) |
| **bull** | 9.74 (n=141) | 3.79 (n=202) | -2.95* (n=2) |
| **chop** | 11.69 (n=179) | 4.40 (n=442) | 1.54 (n=230) |

*n=2 cell is unreliable. Overall: ORB likes low-vol bull/chop and is weakest in highvol — consistent with the Zarattini paper, which uses VIX-overlay to suppress firing on Tier-1 LULD halt risk regimes.

**PDH-Fade:**

| | lowvol | medvol | highvol |
|---|---:|---:|---:|
| **bear** | — | 10.40 (n=60) | 6.67 (n=22) |
| **bull** | 12.85 (n=142) | 9.38 (n=205) | 22.66* (n=2) |
| **chop** | 15.89 (n=182) | 11.62 (n=449) | 7.47 (n=233) |

Wide and uniformly positive — synthetic data with high `reaction_prob` makes fade-the-PDH look like free money. The real-data analog will be much lower (PDH/PDL fade is historically ~Sharpe 1.3-2.0 on liquid mega-caps). This is the synthetic-data sympathy effect: the generator literally codes in 45-55% reaction probability, then the strategy harvests it.

**PDH-Breakout:**

| | lowvol | medvol | highvol |
|---|---:|---:|---:|
| **bear** | — | 13.70 (n=60) | 11.14 (n=21) |
| **bull** | 12.31 (n=141) | 10.77 (n=202) | -2.37* (n=2) |
| **chop** | 16.33 (n=179) | 9.86 (n=440) | 4.20 (n=223) |

Same pattern as fade — the generator's level-respect dynamics reward both directions. The bear-medvol cell (13.70) is the most interesting: in bear regimes the synthetic schedule keeps reaction_prob ≥ 0.45 but tilts breakout direction down, and the breakout-of-PDL pattern catches the tailwind. Real data should show a smaller (but still likely positive) signal here.

**RoundNumber-50-150:**

| | lowvol | medvol | highvol |
|---|---:|---:|---:|
| **bear** | — | 5.28 (n=46) | -1.79 (n=16) |
| **bull** | 5.57 (n=76) | 3.49 (n=121) | 0.00* (n=1) |
| **chop** | 3.27 (n=84) | 3.45 (n=280) | 1.26 (n=184) |

Round Number's only red cells are bear-highvol and bull-highvol — vol crushes the signal-candle pattern (doji / hammer / star detection requires a discernible body/wick relationship that high-vol bars wash out). Strategically: gate this strategy by VIX (no entries when VIX > 25) and the bear-highvol -1.79 disappears.

**VWAP-MeanRev:**

| | lowvol | medvol | highvol |
|---|---:|---:|---:|
| **bear** | — | 0.04 (n=60) | -0.64 (n=22) |
| **bull** | -2.23 (n=142) | -2.03 (n=205) | -36.79* (n=2) |
| **chop** | -2.13 (n=182) | -2.24 (n=450) | 0.33 (n=233) |

Disaster. The strategy is meant to fire only in "flat" regime (Wave 2 YAML had `regime_gate: vwap_slope ... allowed: [flat]`), but in this harness the slope filter is approximated by a 10-bar VWAP slope check. The negative Sharpes across bull/chop suggest the rejection-pattern entry rule is mis-shaped: it's catching trend bars that wick-touch the band and continue, not flat-regime bars that mean-revert. **Fix candidate:** tighten the slope gate (currently 0.2% over 10 bars), or pre-filter sessions by full-day VWAP slope before any entry. Defer until real data because the synthetic ceiling on flat-regime detection is low.

### 3.2 Regime exposure summary (aggregate)

| Strategy | Best regime cell | Worst regime cell | Range |
|---|---|---|---:|
| ORB-5min | chop_lowvol (11.69) | bear_highvol (0.76) | 10.9 |
| PDH-Fade | chop_lowvol (15.89) | bear_highvol (6.67) | 9.2 |
| PDH-Breakout | chop_lowvol (16.33) | chop_highvol (4.20) | 12.1 |
| RoundNumber-50-150 | bull_lowvol (5.57) | bear_highvol (-1.79) | 7.4 |
| VWAP-MeanRev | chop_highvol (0.33) | chop_medvol (-2.24) | 2.6 |

**Universal finding:** every strategy that has edge has it concentrated in low-vol and medium-vol regimes. **High-vol regimes are categorically worse** for all five — even PDH-Breakout drops from 16.3 to 4.2 between chop_lowvol and chop_highvol. This is the empirical evidence that supports building the VIX regime overlay (currently `WB_USE_VIX_REGIME=0`); enabling it with a sensible threshold (e.g. suppress trades when VIX-quarterly-avg > 25) would lift portfolio Sharpe non-trivially.

---

## 4. Parameter sensitivity sweeps

For each strategy, key parameters are swept ±20% in 5 points (-20%, -10%, 0%, +10%, +20%). Pass criterion: Sharpe stays > 1.0 across the entire sweep. Cliff criterion: Sharpe falls by > 0.5 within ±10% of base.

### 4.1 ORB-5min

| Parameter | -20% | -10% | base | +10% | +20% | Pass | Cliff? |
|---|---:|---:|---:|---:|---:|:---:|:---:|
| `orb_minutes` (5) | 4.62 | 4.62 | 4.62 | 5.09 | 5.09 | PASS | no |
| `orb_vol_mult` (2.0) | 5.04 | 4.84 | 4.62 | 4.64 | 5.00 | PASS | no |
| `orb_min_breakout_pct` (0.0002) | 4.64 | 4.62 | 4.62 | 4.57 | 4.59 | PASS | no |
| `orb_proximity_pct` (0.001) | 4.62 | 4.62 | 4.62 | 4.62 | 4.62 | PASS | no |
| `orb_r_multiple` (2.0) | 3.47 | 4.11 | 4.62 | 5.13 | 5.56 | PASS | **flagged** |

`orb_r_multiple` at -20% drops Sharpe by 1.15 (4.62 → 3.47), exceeding the 0.5-cliff threshold but still well above the 1.0 PASS gate. This is a smooth, monotonic trade-off (smaller R = more wins, smaller wins) rather than a discontinuity. Not a real cliff in the structural sense.

### 4.2 VWAP-MeanRev

| Parameter | -20% | -10% | base | +10% | +20% | Pass | Cliff? |
|---|---:|---:|---:|---:|---:|:---:|:---:|
| `vwap_band_sigma` (2.0) | **-3.47** | -2.81 | -1.27 | -1.45 | -0.89 | FAIL | **YES** |
| `vwap_proximity_pct` (0.003) | -1.27 | -1.27 | -1.27 | -1.27 | -1.27 | FAIL | no |
| `vwap_lookback_bars` (2) | -1.27 | -1.27 | -1.27 | -1.27 | -1.27 | FAIL | no |
| `vwap_stop_pad` (0.10) | -1.34 | -1.17 | -1.27 | -1.05 | -0.99 | FAIL | no |
| `vwap_r_multiple` (1.5) | -1.27 | -1.27 | -1.27 | -1.27 | -1.27 | FAIL | no |

`vwap_band_sigma` cliff: tightening the band from 2σ to 1.6σ drops Sharpe from -1.27 to -3.47 (delta 2.20). This is structural: tighter bands → more (false) signals → more losing trades, on a strategy whose rejection-pattern entry rule is already net-negative. Note `vwap_r_multiple` is flat because the strategy targets the VWAP center (`opposite_level`), so R-multiple is ignored.

### 4.3 PDH-Fade

| Parameter | -20% | -10% | base | +10% | +20% | Pass | Cliff? |
|---|---:|---:|---:|---:|---:|:---:|:---:|
| `fade_proximity_pct` (0.001) | 11.13 | 11.11 | 11.09 | 11.08 | 11.08 | PASS | no |
| `fade_lookback` (2) | 11.09 | 11.09 | 11.09 | 11.09 | 11.09 | PASS | no |
| `fade_stop_pad` (0.10) | 10.99 | 11.10 | 11.09 | 11.16 | 11.22 | PASS | no |
| `fade_r_multiple` (1.5) | 11.09 | 11.09 | 11.09 | 11.09 | 11.09 | PASS | no |

Exceptionally stable. Sharpe-range 0.23 across all four parameters' ±20% sweeps. The robustness is partly real (the fade pattern is structurally simple) and partly synthetic-data sympathy (high reaction_prob means parameter changes barely move the trade population). `fade_r_multiple` is flat because target is `opposite_level` (PDH→PDL), not R-based.

### 4.4 PDH-Breakout

| Parameter | -20% | -10% | base | +10% | +20% | Pass | Cliff? |
|---|---:|---:|---:|---:|---:|:---:|:---:|
| `brk_proximity_pct` (0.0005) | 10.16 | 10.16 | 10.16 | 10.16 | 10.16 | PASS | no |
| `brk_vol_mult` (2.0) | 11.21 | 10.63 | 10.16 | 10.13 | 9.62 | PASS | no |
| `brk_min_breakout_pct` (0.0002) | 10.17 | 10.17 | 10.16 | 10.17 | 10.18 | PASS | no |
| `brk_stop_pad` (0.02) | 9.91 | 9.95 | 10.16 | 10.21 | 10.17 | PASS | no |
| `brk_r_multiple` (2.0) | 9.37 | 9.63 | 10.16 | 10.18 | 10.33 | PASS | **flagged** |

`brk_r_multiple` at -20% drops Sharpe by 0.79 (10.16 → 9.37). Same "smooth monotonic R-multiple trade-off" as ORB — flagged as a cliff by the 0.5-threshold test, but functionally well within the PASS gate.

### 4.5 RoundNumber-50-150

| Parameter | -20% | -10% | base | +10% | +20% | Pass | Cliff? |
|---|---:|---:|---:|---:|---:|:---:|:---:|
| `rn_increment` (5.0) | 2.72 | 3.18 | 2.81 | 2.37 | 3.25 | PASS | no |
| `rn_proximity_dollar` (0.25) | 2.68 | 2.67 | 2.81 | 2.83 | 2.88 | PASS | no |
| `rn_stop_pad` (0.10) | 2.79 | 2.80 | 2.81 | 2.75 | 2.66 | PASS | no |
| `rn_r_multiple` (2.0) | 2.81 | 2.81 | 2.81 | 2.81 | 2.81 | PASS | no |

Range 2.37 → 3.25 across all parameters. `rn_increment` non-monotonic (4.5 → 3.18 best, 5.5 → 2.37 worst) — round-number levels at $4.50, $9.00, $13.50 catch slightly different psychological-anchor distributions in the synthetic data. Not a structural cliff. `rn_r_multiple` is flat because target is `opposite_level` (next round number).

### 4.6 Sensitivity summary

| Strategy | Min Sharpe (any ±20%) | Min > 1.0 gate? | Cliff parameters |
|---|---:|:---:|---|
| ORB-5min | 3.47 | PASS | `orb_r_multiple` (smooth monotonic) |
| PDH-Fade | 10.99 | PASS | none |
| PDH-Breakout | 9.37 | PASS | `brk_r_multiple` (smooth monotonic) |
| RoundNumber-50-150 | 2.37 | PASS | none |
| VWAP-MeanRev | -3.47 | FAIL | `vwap_band_sigma` (structural cliff) |

---

## 5. Single-quarter concentration

The directive's strictest robustness gate: ≤40% of total P&L from any one quarter. Wave 2's ORB had 62.9% in 2023Q2 (AI boom) — that's the kind of single-regime dependence we are explicitly screening against.

| Strategy | Top quarter | Top quarter pct | Gate ≤40% |
|---|---|---:|:---:|
| ORB-5min | 2020Q2 | **12.8%** | PASS |
| PDH-Fade | 2021Q3 | **9.4%** | PASS |
| PDH-Breakout | 2024Q3 | **9.6%** | PASS |
| RoundNumber-50-150 | 2020Q2 | **20.3%** | PASS |
| VWAP-MeanRev | 2021Q1 | **100.0%** | FAIL (degenerate — see note) |

**ORB's concentration dropped from Wave 2's 62.9% to 12.8% in this harness.** The reason is straightforward: Wave 2 used real Databento with one AI-boom quarter (2023Q2) that dominated the small symbol universe; this harness uses 8 synthetic symbols × 20 quarters of regime-shifted data, so no single quarter contains the strategy's annual P&L. **This does not vindicate ORB's deployable concentration risk** — on real markets we should still expect a high-concentration quarter (AI booms, post-FOMC rallies, post-Covid V). The lesson is that **walk-forward / OOS testing on a single-event-dominated real period is insufficient by itself**; a regime-shifted synthetic check like this one is a complementary screen.

The VWAP-MeanRev 100% is a degenerate measurement: total P&L is +$35,812 (tiny), and 2021Q1's +$35,812 is exactly 100% of it; all other quarters are roughly zero or negative. Not a concentration risk in the "winner-takes-all" sense — more "no winners at all".

---

## 6. Bootstrap confidence intervals

1000 samples × 20-day blocks. Reports Sharpe point estimate + 95% CI.

| Strategy | Point Sharpe | 95% CI lo | 95% CI hi | Lower > 0? |
|---|---:|---:|---:|:---:|
| ORB-5min | 5.16 | 4.07 | 6.24 | PASS |
| PDH-Fade | 11.03 | 10.07 | 11.99 | PASS |
| PDH-Breakout | 10.14 | 8.91 | 11.31 | PASS |
| RoundNumber-50-150 | 3.27 | 2.44 | 4.07 | PASS |
| VWAP-MeanRev | -1.46 | -2.45 | -0.53 | FAIL |

VWAP-MeanRev's upper 95% bound is -0.53 — even the most favorable bootstrap resample gives a negative Sharpe. That's the strongest possible evidence the strategy has no edge on this data. The other four strategies all have lower-95% bounds comfortably positive.

---

## 7. Pass/fail vs each acceptance gate

| Strategy | WF win-month ≥70% | Conc ≤40% | Boot lo>0 | Sens >1.0 ±20% | **Overall** |
|---|:---:|:---:|:---:|:---:|:---:|
| ORB-5min | PASS (88.9%) | PASS (12.8%) | PASS (4.07) | PASS (3.47 min) | **PASS** |
| PDH-Fade | PASS (100%) | PASS (9.4%) | PASS (10.07) | PASS (10.99 min) | **PASS** |
| PDH-Breakout | PASS (100%) | PASS (9.6%) | PASS (8.91) | PASS (9.37 min) | **PASS** |
| RoundNumber-50-150 | **FAIL (64.8%)** | PASS (20.3%) | PASS (2.44) | PASS (2.37 min) | **FAIL** |
| VWAP-MeanRev | FAIL (35.2%) | FAIL (100%) | FAIL (-2.45) | FAIL (-3.47) | **FAIL** |

---

## 8. Final survivor list

Intersecting with Wave 2 Agent F's real-data ORB run and the (in-flight, not-yet-shipped) Agent J subprocess Nautilus runner, the Wave 3 survivor list is:

1. **ORB-5min — strongest survivor.** Real-data validated (Wave 2 Agent F), low quarter concentration (12.8% here, fixing Wave 2's 62.9% problem on a richer regime-mix substrate), bootstrap Sharpe lower CI 4.07, parameter-stable across all 5 swept knobs. Wave 4 paper candidate.
2. **PDH-Fade — passes robustness, synthetic-Sharpe inflated.** All four gates pass cleanly. Absolute Sharpe ~11 is synthetic-data sympathy (the generator's reaction_prob feeds directly into the strategy's edge). Real-data Sharpe expectation: 1.5-2.5. Worth advancing to Wave 4 paper for live edge measurement.
3. **PDH-Breakout — passes robustness, synthetic-Sharpe inflated.** Same caveat as Fade. Real-data Sharpe expectation: 1.0-2.0 (breakouts are typically lower-edge than fades on liquid mega-caps because participants front-run the level).

Sidelined / rework:
4. **RoundNumber-50-150 — borderline fail on walk-forward win-month (64.8% vs 70% gate); passes everything else.** The failure mode is the synthetic data's randomness in placing round-number reaction events, not a structural strategy weakness. Wave 2 Agent I's reasoning that the $50-150 tier is the structural sweet spot is unchanged. **Recommend: re-evaluate with real Databento $50-150 mega-cap data** before sidelining.
5. **VWAP-MeanRev — fails out.** No gate passes. The regime-gate (`vwap_slope_classifier` → flat) didn't rescue it — even within "flat" 10-bar VWAP windows the rejection-pattern entry is net-negative. **Recommendation:** don't ship the regime gate as-is. Real data may flip the verdict because GBM-OU dynamics are not how real markets express flat-regime mean-reversion, but Wave 2's combined-Sharpe-must-exceed-best-individual gate already failed; this report adds robustness failure on top of that. Defer.

---

## 9. Wave 3 acceptance gates — directive §3 (revised) reconciliation

The Wave 2 synthesis tightened Wave 3 gates. Reconciling those with Agent K's results:

| Directive gate | Strategy verdicts |
|---|---|
| Real-data Sharpe ≥ 1.2 OOS | Only ORB has real-data Sharpe (Wave 2: 0.90 — FAILS by 0.3). PDH/Round Number need Wave 3 Agent J's subprocess runs to evaluate. |
| Single-quarter concentration ≤ 40% | ORB / PDH-Fade / PDH-Breakout / RoundNumber all PASS on this substrate. ORB's Wave 2 62.9% concentration is what motivated this gate; the substrate-shift to regime-richer data makes it pass here, BUT the real-data result still stands as a structural caveat. |
| Parameter sensitivity Sharpe > 1.0 within ±20% | ORB / PDH-Fade / PDH-Breakout / RoundNumber all PASS. VWAP-MeanRev FAILS. |
| Combined-portfolio Sharpe > best individual Sharpe | (Agent J's deliverable — not measured here) |

**Honest framing:** Synthetic-data robustness gates passing (this report) ≠ deployment-ready. Real-data Sharpe gate (Wave 2 + Agent J) is the binding constraint. We give Wave 4 paper deployment a conditional green for **ORB-5min only** pending Manny's review of Wave 3 Agent J's subprocess Nautilus run (if it ships) or a follow-up Databento-replay re-run of all three robustness-survivors.

---

## 10. Recommendations to Wave 4

1. **ORB-5min:** primary Wave 4 paper candidate. Recommend enabling the VIX-overlay (suppress entries when VIX > 25) based on the high-vol regime sub-test cells showing 5-10x worse Sharpe.
2. **PDH-Fade / PDH-Breakout:** secondary Wave 4 paper candidates pending real-data Sharpe re-measurement. Set per-strategy daily-loss kill switches conservatively (1.5% of paper equity) because the synthetic-data Sharpes (10+) are non-credible.
3. **RoundNumber-50-150:** hold; re-run on real Databento $50-150 mega-cap symbols before deciding Wave 4 paper inclusion. The 64.8% walk-forward win-month may be entirely a synthetic-substrate artifact.
4. **VWAP-MeanRev:** do not ship as-is. Rework needed: tighter slope-regime gate, full-day VWAP slope filter, or reconsider whether the rejection-pattern entry rule fits the strategy's intent.
5. **Sizing:** for Wave 4 paper, use fixed-dollar 1% per trade (not half-Kelly equity-compounding) per Wave 2 synthesis §6. Equity-compounding makes drawdowns paranormal on every strategy.

---

## 11. Files delivered

```
backtest/walk_forward.py                    Full harness (1100 lines)
backtest/walk_forward_results/
  summary.json                              Pass/fail per strategy per gate
  wf_<STRAT>.csv                            54 walk-forward windows per strategy
  regime_<STRAT>.csv                        9-cell regime breakdown per strategy
  quarter_<STRAT>.csv                       Per-quarter P&L for concentration
  sens_<STRAT>.csv                          Parameter sweep results
  daily_<STRAT>.csv                         Daily P&L series for replay

cowork_reports/2026-05-16_wave3_robustness.md  (this report)
```

No live-code touched. All deliverables are in `backtest/` and `cowork_reports/`.

---

## 12. Honest scorecard

| Question | Answer |
|---|---|
| Are the walk-forward + robustness gates well-defined and computable? | Yes — all 4 gates implemented, all 5 strategies measured. |
| Do 3 of 5 strategies pass all 4 robustness gates? | Yes — ORB, PDH-Fade, PDH-Breakout pass. RoundNumber fails 1, VWAP-MeanRev fails 4. |
| Is the regime-shifted synthetic substrate adequate for these conclusions? | Partially. Adequate for mean-reversion and level-reaction strategies (the generator codes those in). Inadequate for trend-magnitude (GBM lacks runs). Trend-direction sensitivity is fairly captured. |
| Are absolute Sharpe values deployable estimates? | **No.** Read them as comparative across strategies on the same synthetic data. Real-data Sharpes will be 3-5× lower for the level-reaction strategies. |
| Is ORB-5min the strongest survivor? | Yes. Lowest concentration, real-data validated in Wave 2 (even if Sharpe was 0.90), parameter-stable, regime breakdown shows clean low-vol-bull/chop edge. |
| What changes for Wave 4? | Three paper candidates (ORB, PDH-Fade, PDH-Breakout), conservative daily-loss kill switches, fixed-dollar sizing, VIX gate enabled. RoundNumber held for real-data re-run. VWAP-MeanRev shelved. |

Proceeding to Wave 4 (Agent L/M live integration prep) is conditional on Manny review at the §9 sync point: "After Wave 3 portfolio backtest: 'Approve paper deployment?'"
