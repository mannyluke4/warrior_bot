# VWAP-Mean-Reversion Forensic — Agent 4

**Date:** 2026-05-18 (analysis prep)
**Author:** CC (Forensic Agent 4, parallel)
**For:** Cowork (Perplexity) / synthesis
**Directive:** `DIRECTIVE_2026-05-17_STRATEGY_FORENSICS.md` §3.4
**Background reading:** `cowork_reports/2026-05-16_vwap_backtest.md` (Wave 2 synthetic +35.74 Sharpe), `cowork_reports/2026-05-17_loser_forensic_synthesis.md` (methodology)
**Data:** `backtest_archive/wave3_portfolio/trades_VWAP-Mean-Reversion_fixed_dollar.csv` (3,106 trades, 5y, 27 symbols, all SHORT)
**Enriched dataset:** `backtest_archive/wave3_portfolio/trades_VWAP-MR_enriched.parquet` (this report's working file)
**Feature script:** `scripts/forensic_vwap_mr.py`

---

## TL;DR — verdict: RETIRE

VWAP-MR has no replicable edge on this universe at this implementation. The forensic confirms what the headline Sharpe 0.04 already told us:

1. **Top-30 winners and bottom-30 losers have nearly identical feature profiles.** Same σ-distance, same time-of-day, same day-range, same regime distribution. The only differentiating feature is which ticker the trade fired on — i.e. survivor symbol bias.
2. **Walk-forward symbol selection collapses out of sample.** Best in-sample subset (2020-2022 positive symbols, regime=flat, 10:00–11:30) produces IS daily Sharpe 2.83 → OOS daily Sharpe **−1.51** when applied to 2023 unseen data. Classic overfitting signature.
3. **The rules-only filter (no symbol cherry-picking) lands at daily Sharpe 0.79 over 5 years**, below the 1.2 acceptance bar. Two of five years are net negative.
4. **All 3,106 trades are shorts in a universe with structural +drift.** Mean-reversion implementation fades into a 5-year bull market in mega-cap tech. That's not a fixable parameter; it's a structural mismatch between the strategy spec (symmetric OU fades) and the data-generating process (drifting GBM with regime persistence).
5. **Big winners are tail-driven.** NVDA's entire +$13K contribution comes from 5 trades; the other 84 trades net +$78. META's +$9.2K is 2022-Q3-concentrated (the 2022 crash creating one-sided mean reversion). Without those quarter-specific moves, the strategy is dead flat.
6. **Viability at $25K:** even with the best rules-only filter, max drawdown is $6,496 (26.0% of $25K), 34 of 60 months are negative, worst losing streak 10 trades. Not viable.

**Recommendation: retire VWAP-Mean-Reversion.** Do not promote to filtered-strategy variant. Remove from the Phase 1 portfolio. Reclaim the capacity for confluence trades on strategies that do have edge (PDH-Fade, ORB filtered).

---

## 1. Pre-registered hypothesis table

| # | Hypothesis | Result | Falsified? |
|---|---|---|---|
| 1 | VWAP slope regime gate worked (flat-only entries) | **PARTIAL FAIL.** 2,460 (79%) trades fired on flat. 638 (20.5%) fired on classified `trending_up`. 8 on `trending_down`. The regime gate is leaky vs. my re-classifier at threshold 2e-5/bar. Removing trending entries fixes ~$2,450 of losses (small absolute impact). | Partially falsified — the gate exists but is implementation-dependent. |
| 2 | σ-extreme tightening (2.5σ, 3σ) improves edge | **FAIL — INVERTED.** True σ-distance ≥ 2.0 trades (n=141) lose −$1,275, WR 76.6%, daily Sharpe −1.73 (worst!). Tight stops + small wins inside band = negative expectancy. Strategy is mis-named: most "VWAP-MR" trades fire at σ_dist 1.5–2.0, not 2.0+. | Falsified — bigger σ filter loses more. |
| 3 | Time-since-touch (quick vs sustained drift at extreme) | **N/A.** All 3,106 trades had `time_since_2σ_bars = 1` (single-bar overshoot). No multi-bar drift entries exist in the dataset — the rejection rule fires on the bar of overshoot. Hypothesis untestable on this data. | Untestable. |
| 4 | Day-type filter (chop only) | **PARTIAL SUPPORT, NOT ACTIONABLE.** Day-range pct 1–1.5 has marginal edge ($6.4K net, daily Sharpe 1.04 in 10:00–10:30 window). Day-range > 2.5% is brutal (−$3.6K, daily Sharpe drops 2.5σ). But excluding wide-range days doesn't lift overall Sharpe ≥ 1.2. | Weak/partial support; insufficient lift. |
| 5 | Time-of-day filter (middle session only) | **SUPPORT, INSUFFICIENT.** 10:00–11:30 window is the only non-negative one: $10,849 / 800 trades / daily Sharpe 0.79. First 30 min (09:30–10:00, n=1,583) is −$6,557. Last hour (15:00–16:00, n=63) is −$2,268. Filter works but ceilinged below the gate. | Direction confirmed; magnitude insufficient. |
| 6 | Per-symbol filter (universe trimming) | **APPARENT WIN, FALSIFIED BY WALK-FORWARD.** Dropping AAPL/MSFT/MU/NFLX/INTC lifts in-sample to daily Sharpe 0.87 (net +$25.7K). But: symbol-PnL correlation across 2020-22 and 2023-24 halves is only **0.234** (weak). Walk-forward calib-on-2020-22 → test-2023 produces OOS daily Sharpe **−1.51**. Symbol selection overfits. | Falsified — fails OOS. |
| 7 | Drawdown attribution: concentrated symbols/dates | **CONFIRMED but NOT FIXABLE.** −$22.4K max-DD (Jan 2020 → Jul 2022) is dominated by MSFT (−$7.3K), AAPL (−$3.8K), INTC (−$2.2K) — i.e. the strategy systematically shorted the strongest secular performers. Fixing this requires knowing the future bull leaders, which is the overfitting hypothesis #6 in disguise. | Confirmed; remediation circular. |

---

## 2. Data summary (baseline)

| Metric | Value |
|---|---|
| Trades | 3,106 (all SHORT) |
| Date range | 2020-01-02 to 2024-12-31 (5y) |
| Symbols | 27 (mega-cap & large-cap US: AAPL, MSFT, NVDA, META, TSLA, AAL, F, BAC, CSCO, ... ) |
| Net P&L | **−$633** |
| Win rate | 46.2% |
| Mean R | −0.0002 |
| Std R | 0.315 |
| Trade-level Sharpe | −0.0006 |
| Daily Sharpe (ann., from `metrics.json`) | **+0.037** |
| Profit factor | 0.997 |
| Max DD ($) | −$22,363 |
| Max DD (%) | −21.9% |
| Avg hold | 13.3 min (median 2 min) |
| Exit reasons | stop 52.7%, target 44.8%, session_close 2.5% |

**Baseline characterization:** essentially break-even with high churn (3,100 trades / 5y ≈ 620/yr), modest per-trade variance, and large drawdown periods that match secular bull legs in the universe.

---

## 3. Loser & winner profiles

### 3.1 Top-10 winners

| # | Symbol | Date | Entry time | P&L | R |
|---|---|---|---|---|---|
| 1 | TSLA | 2023-01-11 | 09:57 | +$4,341 | +4.34 |
| 2 | TSLA | 2022-08-29 | 10:17 | +$4,027 | +4.03 |
| 3 | NVDA | 2023-09-29 | 10:12 | +$3,275 | +3.28 |
| 4 | META | 2022-11-01 | 10:03 | +$3,076 | +3.08 |
| 5 | META | 2022-07-29 | 10:01 | +$2,790 | +2.79 |
| 6 | NVDA | 2024-12-19 | 10:16 | +$2,786 | +2.79 |
| 7 | AAPL | 2022-01-04 | 09:57 | +$2,731 | +2.73 |
| 8 | NVDA | 2024-06-03 | 10:31 | +$2,661 | +2.66 |
| 9 | AVGO | 2021-07-26 | 10:06 | +$2,579 | +2.58 |
| 10 | TSLA | 2023-02-09 | 09:53 | +$2,415 | +2.42 |

**Winner concentration:** top 30 trades (≈1%) = +$66,475 net (≈49% of all winning P&L). Top 50 = $87K (43% of total gains). Strategy P&L is tail-driven.

### 3.2 Top-10 losers

| # | Symbol | Date | Entry time | P&L | R |
|---|---|---|---|---|---|
| 1 | AAPL | 2020-09-25 | 09:53 | −$1,000 | −1.00 |
| 2 | AAPL | 2021-03-23 | 10:11 | −$1,000 | −1.00 |
| 3 | AVGO | 2023-05-15 | 11:27 | −$1,000 | −1.00 |
| 4 | NFLX | 2024-04-01 | 14:22 | −$1,000 | −1.00 |
| 5 | AAPL | 2023-02-02 | 09:46 | −$1,000 | −1.00 |
| 6 | MSFT | 2022-04-18 | 10:03 | −$1,000 | −1.00 |
| 7 | NVDA | 2023-02-27 | 09:49 | −$1,000 | −1.00 |
| 8 | TSLA | 2022-09-20 | 10:42 | −$1,000 | −1.00 |
| 9 | TSLA | 2024-06-27 | 09:56 | −$1,000 | −1.00 |
| 10 | AAPL | 2023-03-29 | 09:50 | −$1,000 | −1.00 |

Loser profile is **completely uninformative**: every loser is a clean stop-out at −1R. Strategy stops are tight; once you're wrong, you're done. No variation, no signature.

### 3.3 Side-by-side feature comparison (TOP 30 winners vs BOTTOM 30 losers)

| Feature | Top-30 winners | Bottom-30 losers | Delta |
|---|---|---|---|
| sigma_dist median | 1.65 | 1.23 | +0.42 (winners are *slightly* more extreme — but huge overlap) |
| pct_above_vwap median | 0.380% | 0.323% | +0.06pp |
| day_range_pct median | 1.29% | 1.36% | −0.07pp (essentially identical) |
| momentum_5bar_pct median | 0.279% | 0.147% | +0.13pp |
| bar_vol_ratio median | 0.87 | 0.83 | +0.04 |
| min_of_session median | 35 | 22 | +13 min |
| regime (flat/trend) | 21/9 | 21/9 | identical |

**This is the most damning chart in the report.** The features the strategy could plausibly key on are essentially identical between the most-profitable and least-profitable trades. The only feature with material separation is *which ticker the trade was on*, and that doesn't generalize out of sample (see §5).

### 3.4 Big-winner attribution

Top 30 winners by symbol: NVDA 8, TSLA 6, AAPL 6, AMD 4, META 3, MSFT 2, AVGO 1.

NVDA alone:
- Total NVDA P&L: +$13,043 over 89 trades.
- Top 5 NVDA trades: +$12,965.
- **Remaining 84 NVDA trades: +$78.**

META alone:
- Total META P&L: +$9,249 over 109 trades.
- 2022 alone: +$7,245 (the META crash year, when the stock fell 64% — making a short-only mean-reversion strategy temporarily print money).

The "big winner attribution" answer for VWAP-MR is: **bull-leg-leading mega-caps that had idiosyncratic 1-day reversal moves in the 10:00–10:30 window**. Those aren't tradable as a pattern; they're the byproduct of which stocks happened to crash on which days. We don't have a signal that pre-identifies them.

---

## 4. Hypothesis deep-dives

### 4.1 H1 — VWAP slope filter implementation

The Wave 2 design specified `regime_gate: { source: vwap_slope, last_n_bars: 10, allowed: [flat] }`. My re-classifier (same 10-bar VWAP slope at threshold 2e-5/bar) confirms 79.2% of trades fired in `flat`, but 20.5% leaked into `trending_up`. The most likely explanations:

(a) The Wave 3 backtester used a different threshold (looser definition of "flat").
(b) The classifier ran on synthetic-style cumulative VWAP, but real intraday VWAP has different smoothness — the same threshold catches different sessions.

**Impact:** trending_up trades net −$2,450 over 638 trades (−$3.84/trade avg). Even fully removing them improves net P&L from −$633 to +$1,674, but daily Sharpe only rises to 0.06. Not a fix.

**Note on the synthetic-vs-real collapse:** Wave 2 reported revert-strategy Sharpe +35.74 on synthetic data. The OU process used in synthetic generation is *symmetric* by construction — every overshoot mean-reverts. Real-world equities have asymmetric drift (mega-cap tech +secular up). A short-only mean-reversion fade implementation has structurally negative expectancy when the universe has positive drift. The Wave 2 report flagged this: "the OU process IS the canonical mean-reversion model… real-data OOS is the right test bed." Real-data OOS now exists and confirms the structural mismatch. **The Sharpe didn't collapse — it was never real on this universe.**

### 4.2 H2 — σ-extreme tightening

| σ-distance at entry | n | net | WR | mean R | daily Sharpe |
|---|---|---|---|---|---|
| < 1.5 | 1,209 | −$24,327 | 57.7% | −0.020 | (negative) |
| 1.5–2.0 | 1,756 | +$24,969 | 35.9% | +0.014 | small + |
| 2.0–2.5 | 139 | −$1,294 | 76.8% | −0.009 | strongly − |
| 2.5–3.0 | 2 | +$19 | 50% | — | — |

**Counter-intuitive but consistent:** the strategy's profitable band is σ_dist 1.5–2.0, *not* the headline ≥2σ extreme. At 2σ+, win rate is high but R-multiple is negative — i.e. winners pay less than 1R while losers pay full 1R. Tighter σ thresholds make this worse. The current implementation's profitable behavior is "fade near-2σ before it gets there", which contradicts the strategy's narrative entirely.

### 4.3 H4 — Day-type filter

| Day range so far | n | net | WR | daily Sharpe |
|---|---|---|---|---|
| < 0.5% | 211 | −$2,332 | 63.5% | (neg) |
| 0.5–1% | 1,453 | −$975 | 49.2% | flat |
| 1–1.5% | 881 | +$6,474 | 42.7% | +0.07 |
| 1.5–2.5% | 480 | −$1,267 | 36.7% | (neg) |
| 2.5–5% | 77 | −$3,570 | 41.6% | (very neg) |
| 5%+ | 4 | +$1,037 | 75% | (n too small) |

Day-range 1–1.5% is the sweet spot for VWAP-MR (chop-day signature). But the lift is small (+$6.5K over 881 trades = +$7.34/trade) and only emerges combined with other filters.

### 4.4 H5 — Time-of-day

| Time window | n | net | WR | mean R |
|---|---|---|---|---|
| 09:30–10:00 | 1,583 | −$6,557 | 53.0% | −0.004 |
| 10:00–10:30 | 641 | +$13,119 | 44.6% | +0.020 |
| 10:30–11:30 | 310 | +$468 | 36.5% | +0.002 |
| 11:30–12:30 | 200 | −$1,351 | 35.0% | −0.007 |
| 12:30–15:00 | 309 | −$4,044 | 33.3% | −0.013 |
| 15:00–16:00 | 63 | −$2,268 | 39.7% | −0.036 |

Tightest concentration of P&L: 10:00–10:30 alone produces +$13.1K over 641 trades (daily Sharpe 1.04 in this window). This is **before** the regime / symbol filters that would deplete the sample further.

### 4.5 H7 — Drawdown attribution

Worst drawdown −$22,363 spans Jan 2020 → Jul 2022 (1,267 trades during the drawdown period, net −$22,091). Symbol breakdown of the DD period:

| Symbol | DD-period n | DD-period P&L |
|---|---|---|
| AAPL | 80 | −$8,147 |
| MSFT | 94 | −$7,274 |
| TSLA | 17 | −$4,390 |
| INTC | 93 | −$2,927 |
| MU | 51 | −$1,839 |
| ADBE | 69 | −$1,804 |
| NVDA | 40 | −$1,547 |
| NFLX | 48 | −$1,454 |

Drawdown is **structurally concentrated in the strongest-bull mega-caps** during the 2020–2021 ZIRP/bull rally. Mean-reversion-shorting AAPL during +175% appreciation guarantees losses; the data confirms exactly this mechanism. Symbol filter would "fix" the DD historically, but the symbol identity is only knowable in hindsight — see §5 walk-forward.

---

## 5. Overfitting check (walk-forward)

### 5.1 Rolling 3-year calibration

Calibrate symbol selection (drop net-negative symbols) on rolling 3-year window, apply rules (regime=flat + 10:00–11:30) on next-year OOS.

| Calib window | Test year | IS n | IS net | IS daily Sharpe | OOS n | OOS net | **OOS daily Sharpe** |
|---|---|---|---|---|---|---|---|
| 2020–2022 | 2023 | 203 | +$13,259 | 2.83 | 68 | **−$1,433** | **−1.51** |
| 2021–2023 | 2024 | 145 | +$10,192 | 2.77 | 59 | +$7,494 | +3.65 |
| 2022–2024 | 2025 | 218 | +$18,549 | 3.15 | — | — | — |

**The first walk-forward window collapses entirely OOS.** A naïve practitioner would have calibrated on 2020–2022, shipped the filter, then watched it lose money in 2023.

The second window (calib 2021–2023, test 2024) works — but 2024 contained the late-year NVDA rally + Q4 mega-cap volatility that happened to favor short fades. We can't claim the recipe is stable; we can only claim it worked on 1 of 2 OOS years.

### 5.2 Rules-only walk-forward (no symbol selection)

| Calib window | Test year | IS daily Sharpe | OOS daily Sharpe |
|---|---|---|---|
| 2020–2022 | 2023 | 0.64 | −0.45 |
| 2021–2023 | 2024 | 1.04 | +1.88 |

Rules-only is more stable but the 2023 OOS is still negative. **No version of this filter passes a strict OOS test on consecutive years.**

### 5.3 Symbol persistence check

Per-symbol P&L correlation between halves (2020–2022 vs 2023–2024): **r = 0.234**.

Examples of symbols flipping sign:
- AVGO: +$2,154 → −$4,685
- AAL: +$1,129 → −$247
- CSCO: +$2,048 → −$1,102
- MSFT: −$7,236 → −$581 (huge swing in magnitude)

Symbol-level edge is essentially noise. The Wave 3 backtest happened to overlap a period where META 2022 crash + NVDA 2023–24 rally compensated for the AAPL/MSFT systematic shorts. Re-run on a different 5-year window and the result would shift materially.

---

## 6. Proposed filter spec (for completeness — RECOMMEND NOT SHIPPING)

If a "least-bad" version of VWAP-MR were forced to ship, the rules-only specification would be:

```yaml
# strategies/vwap_mean_reversion_filtered.yaml (NOT RECOMMENDED — see verdict)
inherit_from: vwap_mean_reversion.yaml
filters:
  regime_gate:
    source: vwap_slope
    last_n_bars: 10
    flat_threshold_pct_per_bar: 0.00002  # tightened from leaky baseline
    allowed: [flat]
  time_of_day_gate:
    entry_window_et: ["10:00", "11:30"]   # skip first 30 min + late session
  day_range_gate:
    min_pct: 0.5     # exclude dead-tape early
    max_pct: 2.0     # exclude trending-day overshoots
```

**Expected behavior (in-sample, no symbol filter):** n ≈ 700–800/5y, net +$10K, daily Sharpe 0.7–0.8, max DD ≈ −$6.5K.

**Does not clear the §3.4 acceptance gate (Sharpe ≥ 1.2 with day-type filter).** Per directive: "either find subset with Sharpe ≥ 1.2, OR conclude honestly no edge on this universe. Retirement is a valid outcome."

---

## 7. Viability at $25K starting equity (only if filter shipped)

Using the rules-only filter above (n=800 over 5y at $1K risk per trade):

| Metric | Value | Notes |
|---|---|---|
| Trades/year | ~160 | ~3/week |
| Max DD ($) | −$6,496 | |
| Max DD as % of $25K | **−26.0%** | catastrophic at this account size |
| Negative months | 34 of 60 (57%) | majority of months underwater |
| Worst month | −$2,493 | 10% of equity in a single month |
| Worst losing streak | 10 trades | psychologically punishing at small size |
| Worst 3-month roll | −$2,492 | |
| Annual net (best case) | +$2,170 / yr | not commensurate with the drawdown risk |

**Not viable at $25K.** 26% drawdown on the *best* filter at *fixed* risk sizing would force survival-mode position cuts that destroy the already-fragile expected return.

---

## 8. Why this strategy collapsed from synthetic Sharpe 35.7 → real Sharpe 0.04

Three reinforcing reasons:

1. **Universe asymmetry.** All 3,106 trades are short (the strategy reads only the upper-band overshoots in this implementation; the lower-band side never triggers in the data we have). Mega-cap US tech 2020-2024 has +secular drift. Short-only mean reversion fades into structural drift = systematic loss.
2. **Single-bar timing.** Entry fires on the bar of overshoot; stop is just past the band (≈+$0.10–0.15 above entry). Real intraday tape has continuation noise inside σ-bands; the timing-sensitive entry stops out before mean reversion materializes. Median hold is 2 minutes.
3. **OU vs GBM.** The Wave 2 synthetic harness used Ornstein-Uhlenbeck dynamics in flat regimes — the canonical mean-reversion model. Real flat sessions still have drift, momentum persistence, and microstructure noise that OU lacks. The Wave 2 report explicitly flagged this as a known limitation and recommended real-data OOS in Wave 3. Wave 3 has now confirmed the limitation.

The framework code is correct. The strategy logic is internally consistent. The mismatch is between strategy assumption (symmetric mean reversion) and universe behavior (drifting mega-caps).

---

## 9. Limitations

1. **Sample size.** 3,106 trades looks large but concentrates 5 years × 27 symbols. Filters that survive walk-forward have n ≈ 50–200 in OOS — borderline for reliable inference.
2. **Universe is the Phase 1 mega-cap list.** A different universe (e.g. low-priced small-caps under $20) might show different mean-reversion behavior. Out of scope for this directive.
3. **One-side fade only.** The data shows zero long trades. Whether that's the implementation skipping below-VWAP setups or the bar data not producing them is unclear; either way it caps the strategy's ceiling.
4. **No transaction-cost modeling.** Even the rules-only filter's +$10.8K is gross of commissions/slippage. At ~800 trades, $1 commission per side adds ~$1,600 of cost — wiping out ~15% of headline net.
5. **The synthetic-vs-real Sharpe collapse is now explained, but the explanation is structural, not parametric.** No reasonable change to the existing strategy spec rescues the edge.

---

## 10. Final verdict

**Retire VWAP-Mean-Reversion from the Phase 1 portfolio.**

The data is unambiguous: no filter survives walk-forward without hindsight symbol selection; the rules-only fallback nets +$10.8K over 5 years (≈ $2.2K/year) at −26% drawdown on a $25K account, well outside any reasonable risk envelope. Big-winner attribution shows tail-driven P&L on idiosyncratic mega-cap reversals that are not pattern-tradable. The strategy's synthetic Sharpe 35.7 came from an OU-process artifact and was never reachable on real drifting equities with the implementation as specified.

Concrete actions:
1. Remove VWAP-Mean-Reversion from Wave 4 / Phase 1 deployment plans.
2. Mark `strategies/vwap_mean_reversion.yaml` as `status: retired` in the registry; keep the YAML for archaeological reference.
3. Reclaim the bot capacity it would have consumed; prioritize confluence trades (Agent 6) and PDH-Fade filtered (Agent 1) which have demonstrated edge.
4. Optional: revisit VWAP-MR only if (a) we move to a small-cap universe with documented mean-reverting behavior, or (b) the implementation is re-designed for symmetric long/short with much wider σ thresholds (≥3σ) and longer hold horizons (60+ min), and that re-design passes its own pre-registered forensic on fresh data.

This is the most likely retirement candidate per directive §3.4 background. The data confirms the prior. **Honest no-edge conclusion is the right call.**

---

## 11. Files

- `scripts/forensic_vwap_mr.py` — feature enrichment (this report's working code)
- `backtest_archive/wave3_portfolio/trades_VWAP-MR_enriched.parquet` — 3,106 trades with computed features at entry
- `backtest_archive/wave3_portfolio/trades_VWAP-Mean-Reversion_fixed_dollar.csv` — source (unmodified)
- `cowork_reports/2026-05-16_vwap_backtest.md` — Wave 2 synthetic backtest (referenced)
- `cowork_reports/2026-05-17_loser_forensic_synthesis.md` — methodology pattern followed

No live code touched. No new backtests run. Analysis only, on existing Wave 3 trade data, per directive §6.
