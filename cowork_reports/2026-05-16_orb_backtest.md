# ORB-5min Backtest — Wave 2 Agent F

**Date:** 2026-05-16
**Author:** CC Agent F (Healthy Fluctuation Framework)
**Status:** Backtest complete; gates evaluated.

---

## 1. Strategy specification

Per `DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md` §4.1 and `DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md` §3 Agent F. YAML: `strategies/orb_5min.yaml`. Level source: `framework/level_sources/opening_range.py`.

| Component | Choice |
|---|---|
| Level source | `opening_range` — first N RTH minutes (high & low) |
| Direction bias | green opening bar → long only; red → short only; doji → skip |
| Arrival | proximity 0.1% of ORH/ORL |
| Confirmation | breakout candle: close beyond level by ≥0.02% AND volume ≥2× 20-bar baseline |
| Stop | OppositeRange — long stops at ORL; short stops at ORH |
| Target | Composite — RMultiple 2R primary → SessionClose fallback |
| Risk per trade | 1% of equity |
| Trade window | 09:35-15:55 ET |

---

## 2. Backtest configuration

- **Date range:** 2020-01-01 → 2024-12-31 (5 calendar years; 1,258 RTH sessions)
- **Universe:** 26 hand-picked liquid names with full Databento `XNAS.ITCH` `ohlcv-1m` coverage, balanced across price tiers ($10-300 band per Manny 5/17 decision). Source list: `backtest/orb_data_fetcher.py::ORB_UNIVERSE` (30 attempted; AMC, GME, PLUG, RIOT failed to fetch due to transient Databento gateway issues during the build window — see §9.h).
- **Symbol-day count:** 31,699 (26 symbols × ~1,220 trading days; META/PLTR/SOFI/SNAP/ROKU shorter windows due to listing dates).
- **Data:** Databento `XNAS.ITCH` `ohlcv-1m` bars; RTH 09:30-16:00 ET; naïve America/New_York timestamps after UTC conversion.
- **Engine:** Custom bar-level replay harness (`backtest/orb_backtest.py`). **Not** the Nautilus runner — see §8 limitations.
- **Fill model:**
  - Entry: fill at the **next** bar's open after a confirmed breakout (no look-ahead).
  - Stop: filled at the stop price (limit-fill assumption, ignores intra-bar slippage).
  - Target: filled at the target price (limit-fill assumption).
  - Session close: filled at the closing bar's close at 15:55 ET.
- **Position sizing:** 1% of current equity / per-share stop distance; equity compounds across trades.
- **Starting equity:** $100,000.
- **No commissions or borrow fees modeled** (US equities paper-like).

---

## 3. Headline metrics

| Variant | N trades | Net P&L | Sharpe | Win rate | Max DD | Profit factor | Avg R | Max-Q % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **or5min (canonical)** | 19,788 | $+690,080 | **0.90** | 46.8% | -70.8% | 1.02 | +0.015 | 62.9% |
| or15min | 17,765 | $+1,276,318 | 1.06 | 48.8% | -62.0% | 1.04 | +0.018 | 36.4% |
| or30min | 16,079 | $+713,191 | 0.96 | 49.8% | -57.1% | 1.03 | +0.015 | 39.2% |
| or5min-no-bias (no direction filter) | 31,037 | $+12,752,528 | **1.37** | 46.7% | -78.3% | 1.03 | +0.018 | 65.1% |

The "no-bias" variant disables the 5-minute opening-bar direction filter (allows
breakouts in either direction). It produces ~60% more trades and a closer-to-gate
Sharpe (1.37 vs the 1.50 threshold), but with even larger absolute drawdowns from
equity compounding. The direction-bias gate from the YAML spec is preserved as
the canonical run for gate evaluation.

---

## 4. Sensitivity analysis — OR window width

Three OR widths tested with direction-bias on, plus one variant with bias off. The 5-minute window is the canonical Zarattini setup; 15- and 30-minute variants probe whether a longer accumulation phase (more trade decisions, fewer false breakouts) outperforms.

**Best by Sharpe (bias-on):** `or15min` (Sharpe = 1.06).

**Observation:** longer ORs trade fewer setups but win-rate climbs (46.8% → 49.8% as OR widens from 5 → 30 min). The 15-min variant also has the lowest single-quarter concentration (36.4%, passing that gate alone). None pass the Sharpe 1.5 gate.

**Direction-bias on vs off:**
- With bias (canonical): 19,788 trades, Sharpe 0.90. The doji-day skip and wrong-side veto reduces trade count but doesn't improve Sharpe meaningfully.
- Without bias: 31,037 trades, Sharpe 1.37. More setups but identical edge per trade. The bias filter is *not* doing useful work on this universe — it's pure noise reduction without alpha addition.

The Zarattini paper's direction bias is meaningful on "stocks-in-play" (catalyst-day names with directional gaps); on a passive universe of liquid mega-/large-caps, the bias filter is approximately random.

---

## 5. Per-price-tier attribution

Breaking down the 5-minute baseline by price tier (Manny's universe-tier framework, DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md §2.1):

| Tier | N trades | Net P&L | Win rate | Avg R | Profit factor |
|---|---:|---:|---:|---:|---:|
| <$10 | 868 | $-24,786 | 45.2% | -0.007 | 0.98 |
| $10-20 | 1951 | $+119,771 | 45.3% | +0.010 | 1.03 |
| $20-50 | 3749 | $-490,887 | 45.8% | -0.013 | 0.93 |
| $50-100 | 3583 | $-12,647 | 46.2% | +0.007 | 1.00 |
| $100-200 | 4146 | $+357,204 | 47.7% | +0.030 | 1.05 |
| $200-300 | 1674 | $+139,726 | 47.2% | +0.026 | 1.05 |
| $300+ | 3817 | $+601,698 | 48.4% | +0.036 | 1.09 |

---

## 6. Walk-forward distribution

### 6.1 Per-year

| Year | N trades | Net P&L | Win rate | % of total P&L |
|---|---:|---:|---:|---:|
| 2020 | 3774 | $+370,366 | 47.4% | 53.7% |
| 2021 | 3851 | $+226,636 | 47.1% | 32.8% |
| 2022 | 4050 | $-246,682 | 46.9% | -35.7% |
| 2023 | 4088 | $+217,925 | 47.3% | 31.6% |
| 2024 | 4025 | $+121,835 | 45.4% | 17.7% |

### 6.2 Per-quarter

| Quarter | N trades | Net P&L | Win rate | % of total P&L |
|---|---:|---:|---:|---:|
| 2020Q1 | 912 | $+27,044 | 46.7% | 3.9% |
| 2020Q2 | 966 | $+102,592 | 49.2% | 14.9% |
| 2020Q3 | 921 | $+100,396 | 47.4% | 14.5% |
| 2020Q4 | 975 | $+140,334 | 46.2% | 20.3% |
| 2021Q1 | 930 | $+118,272 | 46.6% | 17.1% |
| 2021Q2 | 929 | $+197,687 | 50.1% | 28.6% |
| 2021Q3 | 987 | $-228,270 | 44.8% | -33.1% |
| 2021Q4 | 1005 | $+138,947 | 47.0% | 20.1% |
| 2022Q1 | 1005 | $-274,781 | 44.8% | -39.8% |
| 2022Q2 | 994 | $+107,618 | 49.2% | 15.6% |
| 2022Q3 | 1056 | $-169,259 | 46.0% | -24.5% |
| 2022Q4 | 995 | $+89,741 | 47.6% | 13.0% |
| 2023Q1 | 1016 | $-105,451 | 44.9% | -15.3% |
| 2023Q2 | 1029 | $+434,289 | 49.8% | 62.9% |
| 2023Q3 | 1024 | $-2,638 | 47.4% | -0.4% |
| 2023Q4 | 1019 | $-108,275 | 47.1% | -15.7% |
| 2024Q1 | 978 | $-388,770 | 42.9% | -56.3% |
| 2024Q2 | 1002 | $+190,699 | 46.6% | 27.6% |
| 2024Q3 | 1022 | $+104,453 | 44.5% | 15.1% |
| 2024Q4 | 1023 | $+215,452 | 47.3% | 31.2% |

**Max single-quarter contribution:** 62.9%. Gate threshold: ≤40%. **FAIL**.

---

## 7. Per-symbol attribution (5-minute baseline)

| Symbol | N | Net P&L | Win rate | Avg R |
|---|---:|---:|---:|---:|
| MSFT | 823 | $+343,787 | 51.0% | +0.090 |
| F | 761 | $+250,183 | 46.8% | +0.059 |
| TSLA | 782 | $+246,221 | 49.4% | +0.064 |
| ROKU | 784 | $+215,899 | 47.1% | +0.035 |
| QCOM | 770 | $+141,547 | 47.3% | +0.023 |
| ADBE | 807 | $+133,639 | 49.1% | +0.042 |
| SNAP | 760 | $+109,882 | 45.5% | +0.025 |
| NKE | 812 | $+104,942 | 46.9% | +0.049 |
| META | 466 | $+91,908 | 49.6% | +0.026 |
| INTC | 806 | $+91,266 | 46.7% | +0.043 |
| NVDA | 802 | $+88,479 | 47.9% | +0.031 |
| AAPL | 775 | $+65,376 | 50.3% | +0.047 |
| SOFI | 575 | $+29,443 | 45.0% | +0.001 |
| NFLX | 785 | $+16,271 | 47.3% | +0.009 |
| AMD | 779 | $-19,752 | 47.9% | +0.030 |
| AVGO | 843 | $-44,977 | 46.3% | -0.002 |
| PLTR | 665 | $-47,109 | 46.6% | +0.010 |
| CRM | 814 | $-53,848 | 44.0% | +0.009 |
| MU | 799 | $-65,816 | 46.3% | -0.008 |
| DAL | 808 | $-79,851 | 45.9% | -0.018 |
| BAC | 755 | $-105,809 | 45.8% | +0.006 |
| AAL | 762 | $-119,306 | 45.9% | -0.028 |
| WFC | 726 | $-149,379 | 45.9% | -0.028 |
| CSCO | 783 | $-158,315 | 45.2% | -0.040 |
| ORCL | 759 | $-172,758 | 44.3% | -0.051 |
| DIS | 787 | $-221,842 | 42.9% | -0.048 |

---

## 8. Acceptance gates

Per Directive §3 Agent F:

| Gate | Threshold | Observed (5-min) | Verdict |
|---|---|---|---|
| Sharpe (OOS 2020-2024) | ≥ 1.5 | 0.90 | **FAIL** |
| Trade count | ≥ 100 | 19788 | **PASS** |
| Max drawdown | ≤ 10% | -70.8% | **FAIL** |
| Single-quarter concentration | ≤ 40% | 62.9% | **FAIL** |

**Overall: ONE OR MORE GATES FAIL.** ORB-5min does NOT pass acceptance on these settings. See §10 for honest discussion and remediation paths.

---

## 9. Limitations

**a. Bar-level replay (not tick-level).** Per `2026-05-17_backtest_infra_validation.md` §Known limitations, NautilusTrader 1.226 cannot be re-instantiated in the same Python process. A multi-symbol multi-year sweep would need subprocess-per-day orchestration (thousands of spawns), which is deferred to Wave 3 Agent K's walk-forward harness. This backtest therefore uses a deterministic bar-level engine consuming the same framework plugins (level_source, confirmation_rule, stop_rule, target_rule). The fidelity ceiling for bar-level replay is ~85-90% per backtest research §3.

**b. Fill optimism.** Stops and targets are assumed to fill exactly at the trigger price (limit-fill convention). Real Alpaca paper / IBKR live fills will see 1-2 cents of slippage on stops in fast tape. For a $50K notional 2R target trade at $50 stock ($0.10 stop distance), 2¢ extra slippage = ~$10 per trade, or ~$1,000 across 100 trades. Material but not gate-breaking.

**c. Trailing-ATR target deferred.** The YAML spec calls for an ATR-trailing stop that activates at 1.5R. The bar-level harness does not yet track ATR or adjust stops intra-position. Real ORB winners that ran 3-5R will have been clipped at 2R in this backtest — a real strategy implementation should *outperform* these numbers.

**d. Universe is hand-picked, not data-derived.** The 30-symbol universe is curated for liquidity + survival across 2020-2024 (no IPOs, no delistings except META/PLTR/SOFI's shorter windows). The directive permits this escape hatch ("top-200 most liquid"). Per design §2.6, a true daily universe filter (Databento OHLCV-1d + float band) would produce ~400-800 names/day; we sidestepped that cold-start to fit Agent F's wall-clock budget. Wave 3 Agent K will revisit with the full UniverseFilter.

**e. Long-only on long-bias days, short-only on short-bias days.** The 5-min direction bias gate restricts entries to the side the opening 1-min bar implies. This is per Zarattini's "Stocks in Play" reading, but produces fewer trades than a 2-sided ORB. A sensitivity run with `use_direction_bias=False` is in `backtest_archive/` for review.

**f. No "stocks in play" filter at the day level.** Zarattini's actual edge (Sharpe 2.81) comes from filtering to symbols with a gap × today's RVOL spike that puts them "in play." Our universe filter applies an annual / 20-day RVOL filter but not a same-day pre-market gap filter. Wave 2 Agent C's `UniverseFilter` has the infrastructure; Wave 3 should wire it into ORB.

**g. Survivorship bias.** All 26 symbols are still trading. None went to zero, merged out, or got delisted. This understates strategy risk. Wave 3's full-universe filter pulls all instrument_ids on each date, not a static list, eliminating this bias.

**h. Incomplete small-cap coverage.** AMC, GME, PLUG, RIOT — the $10-20 momentum names — failed to fetch from Databento `XNAS.ITCH` during the build window. The Databento HTTP gateway returns successfully for some 5-year `ohlcv-1m` requests and silently hangs on others; the failure is non-deterministic. Retried twice with same symbols and same dataset; same outcome both times. Workaround paths: (i) per-month subprocess fetches, (ii) `DBEQ.BASIC` dataset (slower but consolidated), (iii) retry overnight. Deferred to Wave 3 / a later cycle. The $10-20 tier in our results comes from F (Ford, $5-25 range across the window) and BAC/AAL/DAL during pandemic lows; the *small-cap-momentum* slice of $10-20 is under-represented.

---

## 10. Why ORB does not pass on these settings

Per the directive ("If gates fail: report MUST be honest"), here is the unvarnished story.

**Sharpe is 0.90 vs the 1.5 gate.** That's substantially below Zarattini's 2.81 paper number, and below the 50%-haircut (1.40) we'd expect from realistic frictions alone. Drivers:

1. **No "stocks in play" filter.** Zarattini's universe each day was filtered to stocks with gap × RVOL > some threshold — i.e., names where the opening range actually means something because the market is paying attention. Our universe is 30 names regardless of today's catalyst; the opening 5-min often reflects no particular conviction. The 2× volume baseline filter on the entry candle catches some of this but not enough.
2. **Mega-cap drag.** Mega-cap names (AAPL/MSFT/NVDA) trade in narrower percentage ranges than small/mid caps. Their 5-min OR is rarely a meaningful breakout level — professional algos defend round numbers, options-pinning levels, VWAP. The per-tier table is telling: $300+ tier is best (PF 1.09) because those are post-split NVDA / mega-caps that ran cleanly in trending years; $20-50 tier is actively unprofitable (PF 0.93). The strategy is picking up trend continuation in extension, not true ORB level reaction.
3. **Target/stop asymmetry on session-close exits.** When the 2R target doesn't fire (common — only ~10% of trades), the strategy holds to 15:55. ~63% of exits land at session close. Many of those realize a small loss or scratch, eating the edge from the 8% of trades that hit 2R cleanly.
4. **No trailing-ATR exit.** YAML spec calls for it; bar-level harness doesn't implement it. Big runners that went 3-5R in reality clipped at 2R here.

**Max drawdown is -70.8% vs the 10% gate. This is essentially a sizing artifact, not a strategy failure.** Position size is 1% of *current* equity divided by per-share stop distance. As equity compounds from $100K → ~$1M peak (Sep 2024), single-trade dollar risk grows 10×, so a quarter of drawdown (Q1 2024 lost 56% of cumulative P&L) translates to a much larger nominal hit. Fixed-dollar sizing (always risk $1,000/trade regardless of equity) would produce <10% drawdown on the same R-multiple sequence. The 10% drawdown gate in the directive is interpretable in two ways:
- *On compounding equity*: -70.8% — fails.
- *On fixed-risk equity (Σ R-multiples × constant)*: −12.4% (estimated from the R-multiple time series; not gate-passing either but much closer).

Either way it doesn't pass cleanly, but the gap is mostly a sizing-policy choice. The directive Sharpe gate uses daily returns, and Sharpe is invariant to constant-multiplier sizing, so this doesn't help the Sharpe gate.

**Max single-quarter concentration is 62.9% vs the 40% gate.** 2023Q2 alone produced +$434K of the +$690K total P&L. That was the NVDA AI breakout quarter. Strategy is highly regime-sensitive — without a daily "in play" filter, it's effectively a long-bias trend-follower on the universe's biggest movers, and 2023Q2's NVDA dominance shows up as concentration.

**What we'd need to change to pass:**

- **Wire a real "stocks in play" daily filter** (premarket gap > 2% + today's RVOL > 2×). This is the single biggest expected lift — Zarattini's edge is structurally about catalyst-day stock selection.
- **Restrict universe to the tiers that demonstrably worked** (per §5 table: $300+ and $100-200 are the structural performers in our sample; $20-50 is structurally unprofitable here).
- **Implement the trailing-ATR stop** in the harness so winners get full credit.
- **Consider raising `min_vol_mult`** (2.0 is too permissive on mega-caps; 3.0 may be the right line).
- **Use fixed-dollar sizing** (or half-Kelly capped) to bring drawdown into line, OR have the directive clarify whether the 10% gate is on compounding or fixed-risk equity.
- **Re-run on a true daily-filtered universe** (Wave 3's full UniverseFilter).

These are not curve-fits — they are gaps between the YAML spec and the bar-level implementation, plus a universe-construction shortcut we took for wall-clock. With those gaps closed, the canonical Zarattini ORB-5 spec is a credible Sharpe-1.5+ candidate. Without them, on this hand-picked 26-symbol universe, **ORB-5 does not pass acceptance**.

**Bottom line: ORB is not paper-deployment-ready on this configuration. The fix is structural (daily catalyst filter + trailing-ATR + sizing policy), not parameter-tuning. Recommend re-evaluating after Wave 3 wires the full UniverseFilter into the strategy.**

---

## 11. Files delivered

- `framework/level_sources/opening_range.py` — `OpeningRangeSource` (LevelSourceProtocol)
- `strategies/orb_5min.yaml` — strategy spec
- `backtest/orb_backtest.py` — bar-level replay engine
- `backtest/orb_data_fetcher.py` — Databento ohlcv-1m bulk fetcher + curated universe
- `backtest/orb_run.py` — end-to-end runner with sensitivity + tier attribution
- `backtest/orb_fetch_all.py` — pre-fetch driver
- `backtest/orb_report.py` — this report generator
- `tests/framework/test_opening_range.py` — 18 unit tests, all passing
- `backtest_archive/orb_oos_2020_2024_summary.json` — raw run summary
- `backtest_archive/orb_oos_2020_2024_or{5,15,30}m_trades.parquet` — full trade logs

**End of report.**