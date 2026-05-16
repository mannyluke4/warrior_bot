# Wave 3 Synthesis — Real-Data Portfolio + Walk-Forward Robustness

**Date:** 2026-05-16
**Author:** CC
**For:** Cowork (Perplexity) + Manny
**Sources:** `2026-05-16_wave3_portfolio_backtest.md` (Agent J — real Databento), `2026-05-16_wave3_robustness.md` (Agent K — regime-shifted synthetic)
**Per:** `DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md` §4

---

## TL;DR

**Survivor: PDH-Fade.** Every-year positive on real data 2020-2024, Sharpe 1.40-1.47 (fixed-dollar), quarter concentration 26.4%, 9,874 trades, +$582K on $100K. Independently passes Agent K's 4-gate robustness battery (walk-forward 100% win-months, parameter-stable, bootstrap CI > 0).

**Watch-list:** PDH-Breakout (real-data Sharpe 0.70, K-robustness pass, 2024 recovery year) and ORB-5min (real-data Sharpe 0.62-0.82, regime-sensitive). Neither clears the Sharpe ≥ 1.2 gate on real data, but both have directional edge and pass K's robustness — they can be re-evaluated post-Wave-5 once the catalyst-day filter is wired.

**Failed out:** VWAP-Mean-Reversion (no real-data edge; Wave 2's +35.74 Sharpe was a GBM-OU artifact). Round-Number $50-150 (no real-data edge despite K's borderline-pass on regime-rich synthetic). Both deferred or removed from framework.

**Blocking bugs discovered in Wave 3:**
1. **HalfKellySizer suppresses all returns** — flat $98-104K final equity across all 5 strategies vs $95-682K in fixed-dollar mode. Root cause: per-trade edge/variance estimate is structurally tiny on noisy intraday setups, and the 5% bar-volume cap binds wrong on liquid mega-caps. Fix in Wave 5; ship fixed-dollar $1K risk for Wave 4 paper.
2. **VIX > 25 regime is categorically worse for all 5 strategies** (K's universal finding). The framework has a VIX-overlay hook (`framework/vix_regime.py`, default OFF). Recommend ENABLING for Wave 4 paper — suppress entries when VIX > 25. Expected effect: lower trade count, higher per-trade Sharpe.
3. **ATR trailing stop missing from bar-level engine** — winners clip at 2R when YAML calls for trailing after 1.5R. Real strategy edge likely understated. Fix in Wave 5 by re-running survivors through the Nautilus subprocess runner (already shipped).
4. **Combined portfolio MaxDD -47.4%** even with fixed-dollar. Wave 4 paper must start at half size ($500 risk) for first 60 days.

Wave 4 (paper deployment) remains hard stop pending Manny approval. Wave 5 priorities locked.

---

## 1. Survivor selection — the load-bearing decision

The intersection of J's real-data Sharpe gate (≥ 1.2) AND K's 4-gate synthetic robustness battery is exactly **one** strategy: **PDH-Fade**.

| Strategy | J: Real Sharpe (fixed_dollar) | J: Every year positive? | K: 4 gates pass? | Combined verdict |
|---|---:|:---:|:---:|---|
| **PDH-Fade** | **1.40-1.47** | **YES** (every year) | **YES (all 4)** | **DEPLOY CANDIDATE** |
| PDH-Breakout | 0.70-0.77 | NO (3 of 5 years negative) | YES | Watch-list — re-eval post-Wave-5 |
| ORB-5min | 0.62-0.82 | NO (2022-2023 losing) | YES | Watch-list — needs catalyst filter |
| VWAP-MR | -0.02 to 0.04 | NO (flat) | NO (fails all 4) | Defer / remove |
| Round-Number $50-150 | -0.08 | NO (wash) | Borderline (1 fail) | Defer / remove |

### Why PDH-Fade is the clear winner

1. **Real-data 5-year positive in every single year** — $134K, $160K, $92K, $18K, $178K. This is the rarest property in the test: positive through 2020 COVID, 2021 retail mania, 2022 bear, 2023 AI boom, 2024 mega-cap chop. None of the other strategies have all-5-positive.
2. **Low quarterly concentration (26.4%)** — edge is spread across regimes, not concentrated in one quarter like ORB's Wave 2 problem (62.9% in 2023Q2 AI boom).
3. **Robustness gates all pass** independently in K's synthetic harness (100% walk-forward win-months, parameter-stable, bootstrap Sharpe lower-CI > 0).
4. **Trade volume sufficient for paper validation** — 9,874 trades over 5 years = ~8 trades/day on the 36-symbol universe. Even at 1 trade/day post-VIX-filter, that's 252 trades/year, statistically meaningful.

### The trap: 18.8% win rate

PDH-Fade has an 18.8% win rate. Profit factor 1.27 says wins are 5-6× larger than losses on average (avg R 0.06 — small positive). Live psychology of trading an 18.8% WR strategy is brutal — operator may force discretionary overrides during 10+ losing trade streaks (which will happen at 18.8% WR). **Wave 4 paper must measure not just P&L but operator-side discipline.** If you start tweaking it after a losing streak, the edge is gone.

---

## 2. Sizing bug — must-fix before Wave 4

| Mode | ORB-5min | VWAP-MR | PDH-Fade | PDH-Breakout | Round-Number |
|---|---:|---:|---:|---:|---:|
| Half-Kelly equity-compound | $97,801 | $100,281 | $103,685 | $99,392 | $99,773 |
| Fixed-dollar $1K risk | $228,336 | $99,367 | **$681,896** | $177,108 | $94,045 |

Half-Kelly mode produced **6-7× smaller spread** across strategies than fixed-dollar. Reading the math:

```python
# framework/sizing.py HalfKellySizer
fraction = max(0, 0.5 * (expected_edge / variance))     # half-Kelly
qty_raw = (fraction * equity * risk_pct) / risk_per_share
qty_volume_capped = min(qty_raw, bar_volume * 0.05)     # 5% of bar volume
```

Two problems:

**(a) `expected_edge / variance` is structurally tiny on intraday noise.** Per-trade edge is on the order of 0.001-0.06 R; per-trade variance is 0.5-1.0 R². Fraction ≈ 0.0005-0.06. After half-Kelly (×0.5), 1% equity risk pct, $100K equity: dollar risk per trade ≈ $0.25-$30. The strategy fires but rounds to 0-2 shares per trade.

**(b) `bar_volume * 0.05` cap binds the wrong way on mega-caps.** AAPL average minute volume = ~300K shares. 5% = 15K shares. At $200/share, that's $3M position — enormous. The cap is set for small-cap protection but on mega-caps it never binds, so it doesn't help.

**Wave 5 fix:**
1. Replace global `expected_edge / variance` with a 50-trade rolling per-strategy estimate.
2. Replace 5% bar-volume cap with 0.1% of ADV-in-dollars cap (institutional standard).
3. Add a minimum position floor (e.g., $500 risk) so the strategy fires meaningfully even on tiny-edge days.

**For Wave 4 paper:** ship **fixed-dollar $500 risk** (half of $1K test value, per drawdown caution above). Migrate to fixed-dollar with rolling Kelly in Wave 5 only after paper validates the underlying edge.

---

## 3. VIX overlay — must-enable before Wave 4

K's universal finding across all 5 strategies: **high-vol regimes (VIX > 25) are categorically worse**.

| Strategy | chop_lowvol Sharpe | chop_highvol Sharpe | Δ |
|---|---:|---:|---:|
| ORB-5min | 4.2 | 1.1 | -3.1 |
| PDH-Fade | 8.7 | 3.5 | -5.2 |
| PDH-Breakout | 16.3 | 4.2 | -12.1 |
| VWAP-MR | 0.4 | -2.1 | -2.5 |
| Round-Number | 2.8 | 0.9 | -1.9 |

(K's numbers are on regime-rich synthetic, so absolute values are inflated; the *direction* is consistent and load-bearing.)

The framework already has the overlay built (`framework/vix_regime.py`) but it's default-OFF (`WB_USE_VIX_REGIME=0`). For Wave 4 paper:

```
WB_USE_VIX_REGIME=1
WB_VIX_SUPPRESS_THRESHOLD=25    # block new entries when VIX spot > 25
WB_VIX_REENABLE_THRESHOLD=22    # hysteresis — re-enable when VIX drops to 22
```

Trade-count impact: of 1,307 sessions in J's run, ~257 had VIX > 25 (per K's regime decomposition). Roughly 20% of trading days would be suppressed. PDH-Fade alone would drop from 9,874 to ~7,900 trades over 5 years — still statistically meaningful.

**Per-strategy Sharpe lift estimate:** All survivors are categorically better in lower-vol regimes. PDH-Fade real-data Sharpe of 1.40 (mixed VIX) likely lifts to 1.7-2.0 with VIX > 25 entries removed.

---

## 4. Wave 5 priorities (locked)

Per Wave 2 synthesis §10 + Wave 3 J §12 + Wave 3 K findings:

### P0 — Before paper deployment (must complete)
1. **HalfKellySizer fix** (rolling Kelly + ADV-dollars cap) — `framework/sizing.py`. Tests + bench.
2. **Wire VIX overlay default-ON for survivor strategies** — env var + spec field in YAML registry.
3. **Nautilus subprocess runner end-to-end validation of PDH-Fade** — full 5-strategy × 36-symbol × 1,307-day sweep takes ~16 hours but for survivor-only it's 36 × 1,307 ≈ 1.5 hours. Confirms bar-level Sharpe holds at tick-level fidelity.

### P1 — Wave 5 backtest only (Manny's hard stop applies)
4. **Catalyst-day universe filter** (premarket gap > 2% AND today's RVOL > 2×) — Wave 1 Agent C built the infrastructure; not wired into strategy loop. Re-evaluate ORB-5min with catalyst filter.
5. **ATR trailing stop in bar-level engine** — winners clip at 2R when YAML calls for trailing-after-1.5R. Re-run survivors with trailing implemented.
6. **Volume Profile, Anchored VWAP, L2 confirmation** — Wave 5 Phase 2 strategies per directive §5.

### P2 — Production hardening (Wave 6+)
7. Per-strategy conviction-score arbitration (vs first-in-time lock).
8. Tier-aware YAML deployment config (Round-Number $50-150 at registry layer, not signal layer).
9. Commission + borrow rate modeling in backtest.
10. Survivorship-bias-free universe filter.

---

## 5. Wave 4 — held

Per directive §9 and Manny's confirmation 2026-05-16: Wave 4 (paper deployment of framework strategies) is on hard hold pending explicit go.

When go is given, the Wave 4 plan should be:

1. **Single strategy:** PDH-Fade only, no portfolio.
2. **Sizing:** fixed-dollar $500 risk (half test size).
3. **Filters on:** VIX > 25 suppress, hysteresis to 22.
4. **Universe:** the 36-symbol Databento shortlist used in Wave 3 (don't expand until paper validates).
5. **Run length:** 60 trading days minimum before any size-up decision.
6. **Kill criteria:** Sharpe < 0.5 over 30+ days → halt. Max DD > 15% → halt. Operator discretionary overrides > 5 → halt and review.
7. **No co-listing with existing squeeze bot.** Separate Alpaca paper account, separate clientId, separate persistence file. Compare net P&L head-to-head.

Real-money go-live deadline 2026-06-04 is still ~3 weeks away (real date: 2026-06-15 per recent slip). 60 trading days of paper-PDH-Fade from a hypothetical 2026-05-19 start ends ~2026-08-12 — well past June 15. So Wave 4 paper does NOT block June 15 real-money go-live for the *existing squeeze bot*. The framework's PDH-Fade is a separate track.

---

## 6. Files delivered (Wave 3)

```
backtest/portfolio_backtest.py             1,004 lines — bar-level multi-strategy engine
backtest/nautilus_subprocess_runner.py     248 lines — Wave 4 prep
backtest/walk_forward.py                   1,339 lines — K's robustness harness
backtest/wave3_report.py                   631 lines — J's reporter

backtest_archive/wave3_portfolio/
  summary_half_kelly.json
  summary_fixed_dollar.json
  trades_*_{half_kelly,fixed_dollar}.{parquet,csv}  (15 files)
  portfolio_equity_*.parquet (2 files)

backtest/walk_forward_results/
  summary.json
  5 × per-strategy CSVs × 5 metric types = 25 files

cowork_reports/
  2026-05-16_wave3_portfolio_backtest.md  Agent J real-data report
  2026-05-16_wave3_robustness.md          Agent K walk-forward report
  2026-05-16_wave3_synthesis.md           this report
```

No live code touched. Existing bots, scanners, persistence — all untouched per directive.

---

## 7. Open questions for Cowork

1. **Sizing fix priority.** Ship fixed-dollar $500 risk for Wave 4 paper *now*, fix HalfKellySizer in Wave 5? Or block Wave 4 on sizing fix? I recommend ship-with-fixed-dollar; the sizing fix is a multi-day Wave 5 task and the paper validation can use $500 fixed.
2. **VIX overlay calibration.** Threshold 25 is K's empirical regime boundary. Real-data validation of 22/25 hysteresis on PDH-Fade specifically would be a 30-minute additional run. Worth doing before Wave 4?
3. **Watch-list strategies.** PDH-Breakout and ORB-5min have directional edge but fail Sharpe gate. Acceptable to re-evaluate them post-catalyst-filter (Wave 5), or pull them entirely?
4. **Subprocess Nautilus re-validation.** PDH-Fade Wave 3 fidelity is bar-level (~85-90% of tick-level per research). Tick-level revalidation = 1.5 hours of compute. Run before Wave 4 paper, or accept bar-level for paper and re-validate at real-money go-live?
5. **2026-06-15 real-money deadline.** This is for the *existing squeeze bot*, not the framework. Framework + PDH-Fade is a separate track. Confirm Cowork still treats June 15 as squeeze-bot-only?

Proceeding to Wave 5 (Phase 2 strategies — backtest only, no paper). Hard stop at Wave 4 confirmed.
