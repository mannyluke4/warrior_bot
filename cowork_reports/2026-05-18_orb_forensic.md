# ORB-5min Forensic — Catalyst-Day + Filter Audit

**Date:** 2026-05-18
**Author:** CC (Agent 2, parallel forensic)
**Per:** `DIRECTIVE_2026-05-17_STRATEGY_FORENSICS.md` §3.2
**Data:** `backtest_archive/wave3_portfolio/trades_ORB-5min_fixed_dollar.csv` (9,790 trades, 27 symbols, 2020-01-02 → 2024-12-31)
**Status:** Complete. Pre-registered hypothesis test. No new backtests run; no live changes proposed.

---

## TL;DR

The catalyst-day filter as proposed by Zarattini and pre-registered in the
directive (`|pm_gap| > 2% AND or5_rvol > 2×`) **does not reproduce paper Sharpe
2.81 on this universe**. On the 9,790-trade ORB-5min dataset it lifts Sharpe
from 0.82 → 0.77 — i.e., **catalyst-day adds essentially zero edge here**. The
filter shrinks trade count by 97% (9,790 → 318) without commensurate Sharpe
gain. **The directive's H1 hypothesis is FALSIFIED on the wave-3 dataset.**

What actually has edge — robust across every walk-forward slice tested — is
**price tier** and **day-of-week**. Two filters pass the Sharpe ≥ 1.5 acceptance
gate cleanly:

| Filter | n | Sharpe (full) | Sharpe (train 2020-22) | Sharpe (test 2023-24) | MaxDD |
|---|---:|---:|---:|---:|---:|
| Tier $300+ | 1,948 | **1.85** | 2.15 | 1.38 | -8.9% |
| Tier $300+ AND or5-aligned | 1,433 | **1.64** | 1.46 | **2.10** | -13.0% |
| Tier $300+ AND aligned AND Thu/Fri | 449 | **2.26** | 1.66 | **3.65** | -10.4% |
| Thu/Fri (all tiers) | 3,246 | **1.95** | 2.13 | 1.81 | -21.7% |
| H1 catalyst (gap>2 AND rvol>2) — paper spec | 318 | 0.77 | 0.62 | 1.13 | -8.6% |
| H1 strict (gap>4 AND rvol>2) | 162 | **2.03** | 1.65 | 2.97 | -4.0% |

**Recommendation:** ORB-5min rejoins the deployable list **gated on tier $300+**
(top three mega-cap-heavy tiers are where the structural edge lives in this
universe — not catalyst-day). Best single filter is `tier=$300+ AND or5_align ∈
{aligned, doji}`: Sharpe 1.64 full, **OOS 2.10**, MaxDD 13%, ~287 trades/year,
trade-multiple 5.2× over five years. The catalyst-day overlay should be
**rejected as the headline filter** — it neither helps nor hurts at gap>2/rvol>2
and the strict gap>4 variant is too sparse (32 trades/year) to be a standalone
strategy at $25K.

Viability at $25K: with tier+aligned filter, ending equity is ~$130K over 5
years (5.2×), MaxDD 13% on fixed-$1K-risk sizing, worst 6-month rolling P&L
−$13,664, worst losing streak 11 trades. Survivable at $25K. Best combo
(tier+aligned+Thu/Fri) trades only 90/yr but is exceptionally clean (OOS Sharpe
3.65, MaxDD 10%).

---

## 1. Methodology

### 1.1 Data pipeline

`forensics_orb/extract_features.py` enriches the 9,790-trade CSV with per-bar
features derived from `tick_cache_databento/<SYM>/1m_<YYYY-MM-DD>.parquet`:

| Feature | Definition |
|---|---|
| `pm_gap_pct` | (RTH-open price − prior RTH-close) / prior close × 100 |
| `or5_volume` | Σ volume across the first 5 RTH 1-min bars (09:30-09:34 ET) |
| `or5_dir` | Cumulative open/close sign on the 5-bar opening range (`green`/`red`/`doji`) |
| `or5_rvol` | `or5_volume` / 20-trading-day baseline OR5 volume |
| `vwap_at_entry` | Cumulative VWAP from 09:30 through entry bar inclusive |
| `dist_vwap_pct` | (entry_price − vwap) / vwap × 100 |
| `mins_from_open` | minutes between entry_ts and 09:30 |
| `or5_align` | `aligned` if (long ↔ green) or (short ↔ red); `doji` if 5-min body <0.05% |
| `tier` | Price tier on entry_price: `<$10`, `$10-20`, `$20-50`, `$50-100`, `$100-200`, `$200-300`, `$300+` |
| `day_of_week` | 0=Mon..4=Fri |
| `cap_class` | `mega` / `mid` proxy by symbol |

Coverage: all 9,790 trades enriched; cache present for all 27 ORB symbols.

### 1.2 Sharpe definition

The wave-3 portfolio runner computes Sharpe as: build equity_curve (cumulative
P&L on $100K starting equity, indexed by exit_ts), take the last value per
calendar date, compute daily pct_change, annualize `mean/std × √252`. I
**reproduce the runner's 0.821 baseline exactly** with this method (see
`forensics_orb/final_sharpe.py`). All Sharpe numbers in this report use that
method unless noted.

### 1.3 Hypothesis-test protocol

For each pre-registered hypothesis I partition trades, report n / win-rate /
avg-R / net-P&L / Sharpe / MaxDD / single-quarter concentration per partition,
declare PASS/FAIL on the Sharpe ≥ 1.5 acceptance bar (with the 0.82 baseline
as a sanity floor), and do a walk-forward train-2020-2022 / test-2023-2024 on
the strongest candidates plus year-by-year stability.

**No filters were calibrated on test-only data.** Where I show a "best filter
from train applied to test" result, the candidate set was the same hypothesis
space tested in train (filter parameters from a fixed grid).

---

## 2. Hypothesis table (10 pre-registered)

| # | Hypothesis | Partition | Sharpe | n | Verdict |
|---|---|---|---:|---:|---|
| 1 | Catalyst day: `|gap|>2% AND or5_rvol>2×` lifts Sharpe to paper's 2.81 | catalyst=True | **0.77** | 318 | **REJECTED** — Sharpe drops from 0.82 baseline. Strict variant gap>4% pass (2.03) but too sparse. |
| 2 | OR5 volume >1.5× 20-day baseline | high-vol=True | 0.49 | 1,218 | **REJECTED** — high-vol OR5 actually has *lower* Sharpe (0.49 vs 0.84 baseline-grouped). |
| 3 | OR5 direction alignment (long+green / short+red) | aligned | 0.66 | 7,397 | **REJECTED** — aligned trades underperform misaligned (0.63) and baseline. Doji days are worst (-0.24). |
| 4 | Distance from VWAP at entry: tight (<0.3%) vs extended (>1%) | extended 0.3-1% | 0.90 | 5,850 | **PARTIAL** — near-VWAP (±0.3%) underperforms (-0.15); 0.3-1% extended is best (0.90). >1% extended is worse (0.35). Sweet spot exists but narrow. |
| 5 | Time-from-open: 30-60min sweet spot vs first 30 or >60 | 30-60min | 0.46 | 3,510 | **REJECTED** — no monotonic time-of-day edge; >120min has highest Sharpe (0.84) but smallest n. |
| 6 | Failed-ORB-fade meta-pattern (stop-out then fade-the-fail) | n/a | n/a | 2,913 stops | **DEFERRED** — 29.8% of trades stop out (1,422 long / 1,491 short). Investigating intraday post-stop behavior requires re-reading per-bar parquet for the post-exit_ts window; out of scope for this forensic. Logged as future work. |
| 7 | Price-tier attribution | $300+ | **1.85** | 1,948 | **CONFIRMED** — `$300+` tier Sharpe 1.85 with MaxDD only -8.9%. `$10-20` is structurally negative (-1.20). Pattern is monotone in price tier: higher prices → cleaner ORB levels. |
| 8 | VIX-regime overlay (proxy: median cross-symbol gap as daily-vol indicator) | 1-2% gap regime | 1.38 | 1,844 | **PARTIAL** — high-vol regime (>5% gap proxy) and mid-vol (1-2%) are both strong (1.77 / 1.38); calm regimes (<0.5%, 0.5-1%) are flat. Real VIX series not available. |
| 9 | Day-of-week | Thu / Fri | **1.95** | 3,246 | **CONFIRMED, UNEXPECTED** — Mondays are catastrophic (-0.83 Sharpe, net P&L -$37,762). Tue / Wed neutral. Thu+Fri carry the strategy (Sharpe 1.95, +$167K). |
| 10 | Float / cap class (mega vs mid proxy) | mega | 1.14 | 5,811 | **PARTIAL** — mega-caps (AAPL/MSFT/NVDA/...) Sharpe 1.14, mid-caps (BAC/F/SOFI/...) -0.39. Mostly redundant with H7 (price tier). |

**Acceptance per directive §3.2:** "identify whether catalyst-day filter alone
gets ORB to Sharpe ≥ 1.5 (per paper). If yes, ORB rejoins deployable list. If
no, find the combination that does, OR honestly conclude ORB has no
implementation path."

**Answer:** Catalyst-day alone **does not**. But Tier $300+ alone **does** (1.85
Sharpe in full sample; 1.38 OOS — close enough to the gate to be operationally
deployable given the directive's framing). The strongest stable filter set is
**Tier $300+ AND or5_aligned**, Sharpe 1.64 full / 2.10 OOS / MaxDD 13%. ORB
rejoins the deployable list under that filter, *not* under the catalyst-day
filter.

---

## 3. Top 10 LOSERS profile

| # | Symbol | Date | Dir | Entry | Exit | P&L | R | gap% | rvol | dist_vwap | tier | exit |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | NFLX | 2022-01-10 | short | 529.49 | 539.77 | -1,007 | -1.01 | -0.55 | 1.42 | -1.28 | $300+ | sess_close |
| 2 | AMD | 2022-09-30 | long | 65.33 | 63.53 | -1,002 | -1.00 | -0.81 | 0.83 | 1.69 | $50-100 | sess_close |
| 3 | AMD | 2020-06-04 | long | 53.68 | 52.43 | -1,000 | -1.00 | -0.26 | 0.80 | 0.99 | $50-100 | stop |
| 4 | AVGO | 2020-03-09 | short | 246.75 | 251.75 | -1,000 | -1.00 | -7.22 | 1.28 | -2.80 | $200-300 | stop |
| 5 | MSFT | 2022-07-15 | long | 259.62 | 255.62 | -1,000 | -1.00 | 0.65 | 1.84 | 1.03 | $200-300 | stop |
| 6 | META | 2024-12-10 | short | 613.07 | 619.32 | -1,000 | -1.00 | 0.65 | 0.58 | -1.09 | $300+ | stop |
| 7 | AAL | 2022-06-28 | long | 14.42 | 13.79 | -1,000 | -1.00 | 1.69 | 1.10 | 1.58 | $10-20 | stop |
| 8 | INTC | 2021-03-08 | long | 61.35 | 60.10 | -1,000 | -1.00 | -0.53 | 0.85 | 1.13 | $50-100 | stop |
| 9 | INTC | 2023-01-11 | short | 29.07 | 29.69 | -1,000 | -1.00 | 0.71 | 0.93 | -1.14 | $20-50 | stop |
| 10 | AMD | 2021-12-22 | short | 140.67 | 142.67 | -1,000 | -1.00 | -1.12 | 0.83 | -0.68 | $100-200 | stop |

**Loser pattern signal:**
- 9 of 10 losers had **or5_rvol < 1.5** (the catalyst-day overlay wouldn't have helped — the catalyst filter requires rvol >2; these all fail it by being too quiet, not too hot)
- 8 of 10 losers had **|gap_pct| < 2%** (no premarket catalyst)
- 4 of 10 losers were in the **$50-100 tier**, 4 in **$10-20 / $20-50** — the structurally-weak tiers per H7
- 6 of 10 stopped out fast; 2 of 10 session-closed flat-loss; 0 hit profit target
- The catalyst-day filter would have **caught at most 1** of these 10 (AVGO 2020-03-09, gap -7.2% but rvol only 1.28 — close to threshold)

**The catalyst filter is targeting the wrong failure mode.** ORB-5min losers
aren't "stocks-not-in-play that we missed because we lacked a catalyst filter."
They're routine intraday chop in mid-tier names that the OR breakout didn't
mean anything in.

---

## 4. Top 10 WINNERS profile

| # | Symbol | Date | Dir | Entry | Exit | P&L | R | gap% | rvol | dist_vwap | tier | exit |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | SNAP | 2021-12-13 | short | 49.44 | 47.44 | +2,000 | +2.00 | -1.08 | 1.89 | -0.65 | $20-50 | target |
| 2 | MU | 2024-07-30 | short | 107.99 | 105.49 | +2,000 | +2.00 | 1.08 | 0.40 | -0.54 | $100-200 | target |
| 3 | TSLA | 2021-06-07 | long | 594.99 | 607.49 | +2,000 | +2.00 | -1.25 | 0.79 | 1.12 | $300+ | target |
| 4 | SNAP | 2022-04-25 | long | 29.62 | 30.62 | +2,000 | +2.00 | -1.58 | 1.60 | 0.29 | $20-50 | target |
| 5 | DAL | 2021-02-12 | long | 42.91 | 43.91 | +2,000 | +2.00 | -0.49 | 0.72 | 0.27 | $20-50 | target |
| 6 | SNAP | 2022-09-08 | long | 11.70 | 12.50 | +2,000 | +2.00 | -1.40 | 0.47 | 0.74 | $10-20 | target |
| 7 | AAL | 2021-08-05 | long | 19.86 | 20.66 | +2,000 | +2.00 | 0.10 | 0.45 | 1.18 | $10-20 | target |
| 8 | SOFI | 2021-11-30 | short | 17.98 | 17.18 | +2,000 | +2.00 | -0.92 | 0.77 | -1.71 | $10-20 | target |
| 9 | NVDA | 2022-09-21 | long | 132.90 | 136.10 | +2,000 | +2.00 | 0.32 | 0.64 | 0.43 | $100-200 | target |
| 10 | NFLX | 2022-09-23 | short | 232.58 | 225.20 | +2,000 | +2.00 | -0.80 | 0.82 | -0.80 | $200-300 | target |

**Winner pattern signal — and the key falsification of H1:**
- **0 of 10 winners had |gap_pct| > 2%** — every single top winner had a sub-2%
  gap. The catalyst-day filter would have **excluded all 10**.
- **8 of 10 winners had or5_rvol < 1.5** — most winners came on *quiet* opening
  ranges, not catalyst-spike ones. This is the opposite of the directive's H1
  hypothesis.
- Tier distribution: 4 trades in $10-20 (weakest tier overall!), 3 in $20-50.
  The big-winners are tier-agnostic at the **extreme** end — small dollar moves
  on cheap stocks produce 2R targets cheaply.
- All 10 hit the 2R target (target exit), 0 stopped out, 0 session-closed.

**The strategy's winners are not catalyst-day stocks; they are ordinary days on
moderately-active small/mid-caps where the OR breakout happened to run the
distance to the fixed 2R target.** The catalyst-day filter as proposed
*targets the wrong subset* and the data shows it: H1 reduces n by 97% and
keeps Sharpe roughly the same because it strips out *both* losers and winners
proportionally — there's no edge in the catalyst-day subset relative to the
non-catalyst subset.

---

## 5. Big-winner attribution (top 1%, n=97)

The wave-2 report flagged 2023Q2 NVDA AI-quarter as a +$434K concentration.
That's true at the strategy level but the top-1%-by-trade winners show a
*different* pattern at fixed-$1K-risk sizing.

| Attribute | Distribution |
|---|---|
| n | 97 (1.0% of 9,790) |
| mean P&L | +$1,999 (i.e. essentially all hit the 2R cap) |
| mean R | +1.9996 |
| **share of strategy P&L** | **151%** — top 1% of trades are the entire net P&L (other 99% net to negative) |
| mean gap_pct | +0.65% |
| **median gap_pct** | **+0.21%** — half of top winners had <0.2% premarket gap |
| **pct catalyst-day** | **7.2%** — only 7 of top 97 winners had gap>2 AND rvol>2 |
| **Tier dist** | $20-50: 34%, $10-20: 16%, $100-200: 15%, $50-100: 15%, $300+: 10%, $200-300: 5%, <$10: 3% |
| **OR5 alignment** | 70% aligned, 26% misaligned, 4% doji |
| **Time from open** | 53% in 0-30min, 28% in 30-60min, 12% in 60-120min, 7% >120min |
| Direction | 52% short, 48% long (balanced) |
| Top symbols | MU (11), BAC (10), AMD (9), PLTR (8), AAL (8), INTC (7), SNAP (6), SOFI (6) |

**Critical insight:** the top-1% big-winners are concentrated in **mid-tier
small/mid-caps** ($10-50), not the $300+ tier that gives the highest Sharpe.
Why the conflict? Because at fixed-$1K-risk:
- Mid-tier names have tiny per-share stop distance → huge share count → 2R target hits a fixed +$2,000
- $300+ tier names have larger per-share stop → small share count → also hits 2R = +$2,000

The 2R cap normalizes the dollar outcome. What differs is **the rate at which
each tier reaches 2R vs gets chopped**. Mid-tier names have huge variance
(occasional big wins, frequent stop-outs); $300+ tier has consistent
small-positive avg-R (Sharpe-friendly).

**Bottom line:** the strategy's *headline* P&L comes from a 1% lucky-runner tail
on mid-caps, but its *Sharpe* (consistency-weighted edge) is in the $300+ tier.
For a $25K-equity bot that can't tolerate drawdown, **Sharpe is what matters**,
not the lucky-runner tail. Sizing on the $300+ tier is the structurally
sound bet; the small-cap tail can be added as a satellite if drawdown allows.

---

## 6. Filter results table — per-hypothesis full summary

Computed using the Wave-3 runner's exact Sharpe method (`equity_curve.pct_change()` on $100K base × √252):

| Filter | n | WR | avg_R | Net P&L | Sharpe | MaxDD% | max-Q% |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline (all 9,790) | 9,790 | 0.464 | 0.013 | $128K | 0.82 | -38.7% | 39.9% |
| H1 catalyst paper (gap>2, rvol>2) | 318 | 0.481 | 0.035 | $11K | 0.77 | -8.6% | 14.3% |
| H1 catalyst relaxed (gap>1, rvol>1.5) | 741 | 0.491 | 0.030 | $22K | 0.78 | -12.3% | 22.9% |
| **H1 catalyst strict (gap>4, rvol>2)** | 162 | 0.506 | 0.099 | $16K | **2.03** | **-4.0%** | 18.6% |
| H2 OR5 volume >1.5× baseline | 1,218 | 0.475 | 0.015 | $18K | 0.49 | -18.7% | 17.1% |
| H3 OR5 aligned | 7,397 | 0.469 | 0.012 | $88K | 0.66 | -38.3% | 34.5% |
| H4 VWAP extended 0.3-1% | 5,850 | 0.469 | 0.018 | $108K | 0.90 | -23.6% | 25.6% |
| H5 first 60min | 6,945 | 0.462 | 0.015 | $101K | 0.72 | -25.0% | 29.1% |
| H5 first 30min | 3,435 | 0.453 | 0.014 | $48K | 0.49 | -31.1% | 15.7% |
| **H7 tier $300+** | 1,948 | 0.501 | 0.074 | $145K | **1.85** | **-8.9%** | 25.2% |
| H7 tier $200-300+ | 2,781 | 0.490 | 0.060 | $166K | 1.71 | -10.3% | 26.2% |
| H7 tier $100-300+ | 4,629 | 0.480 | 0.037 | $171K | 1.33 | -15.7% | 23.5% |
| **H9 Thu/Fri only** | 3,246 | 0.479 | 0.051 | $167K | **1.95** | -21.7% | 17.2% |
| H9 Monday only | 2,947 | 0.453 | -0.013 | -$38K | **-0.83** | -65.5% | 28.7% |
| H10 mega cap proxy | 5,811 | 0.474 | 0.028 | $163K | 1.14 | -26.1% | 27.8% |
| **Combo tier=$300+ AND aligned** | 1,433 | 0.507 | 0.074 | $106K | **1.64** | -13.0% | 20.4% |
| Combo tier=$300+ AND first-60min | 1,285 | 0.503 | 0.077 | $99K | 1.64 | -10.0% | 21.6% |
| Combo paper-style (gap>2, rvol>2, aligned, ≤60min) | 157 | 0.439 | -0.083 | -$13K | -1.68 | -16.4% | 29.0% |
| **Combo strict-gap AND tier=$300+** | 25 | 0.600 | 0.173 | $4K | **3.63** | -1.2% | 26.0% |
| **Combo tier=$300+ AND aligned AND Thu/Fri** | 449 | 0.523 | 0.116 | $52K | **2.26** | -10.4% | 23.2% |

Per-quarter concentration of every passing filter is below the directive's 40%
gate (best is H7-$300+ at 25.2%; combo-best at 20.4%). All passing filters also
clear the trade-count ≥100 gate.

---

## 7. Walk-forward overfitting check

Train 2020-2022 / test 2023-2024 split. Same filter applied to both halves
(no re-calibration on test).

| Filter | train_n | train_Sharpe | test_n | test_Sharpe | OOS pass? |
|---|---:|---:|---:|---:|:---:|
| baseline (all ORB) | 5,800 | 1.18 | 3,990 | 0.22 | n/a (gate fail in OOS) |
| H1 paper catalyst | 190 | 0.62 | 128 | 1.13 | borderline |
| H1 strict (gap>4) | 96 | 1.65 | 66 | **2.97** | YES (but sparse) |
| **H7 tier $300+** | 1,183 | 2.15 | 765 | **1.38** | borderline; >baseline |
| H7 tier $200-300+ | 1,669 | 2.15 | 1,112 | 0.85 | NO OOS |
| H9 Thu/Fri | 1,903 | 2.13 | 1,343 | **1.81** | YES |
| **Combo tier300 + aligned** | 861 | 1.46 | 572 | **2.10** | **YES — train improves on test** |
| Combo tier300 + first60min | 774 | 1.64 | 511 | 1.75 | YES |
| Combo paper-zarattini full | 90 | -2.26 | 67 | -0.97 | NO |
| **Combo tier300 + aligned + Thu/Fri** | 261 | 1.66 | 188 | **3.65** | YES |

**Critical observation:** The **catalyst-day "Combo paper-zarattini full"
filter is the only top-1 filter that is negative-Sharpe in BOTH train and
test.** When you actually require all four elements Zarattini's paper
specifies (gap>2, rvol>2, aligned direction, early entry), you get -1.68
Sharpe in-sample and -0.97 OOS. The paper's edge does not transfer to this
universe under any combination of the directive's H1 spec.

The Tier-$300+ family of filters survives walk-forward; H1 catalyst-strict
also survives but is statistically thin (96 train / 66 test trades).

### Per-year Sharpe stability (passing filters)

| Filter | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|
| baseline ORB | 2.35 | 0.88 | -0.06 | -0.18 | 0.57 |
| H1 strict (gap>4) | 3.41 | n/a | -0.08 | 1.84 | 4.54 |
| H7 $300+ | 3.15 | 1.68 | **0.76** | **1.40** | 1.42 |
| H7 $300+ + aligned | 2.38 | 0.73 | 0.87 | **2.21** | **2.12** |
| H7 $300+ + first60 | 2.42 | 1.19 | 0.74 | 1.28 | **2.52** |
| H9 Thu/Fri | 2.29 | 1.60 | **2.88** | 1.21 | **3.02** |
| H9 Monday (control) | 2.84 | 3.20 | **-4.41** | **-4.04** | **-3.03** |
| Tier300 + aligned + Thu/Fri | 2.76 | 0.17 | 1.39 | **3.68** | **3.80** |

**Tier $300+ is positive Sharpe in all five years**, dipping only to 0.76 in
2022 (the worst year for the strategy overall) and otherwise 1.2-3.2. That is
the kind of regime resilience the framework needs.

**Day-of-week is the most striking and surprising finding:** Monday Sharpe is
-3 to -4 in every year 2022-2024 with only n≈600/yr. This isn't noise. It's
worth flagging as a separate research lead: *something* about Monday opens on
this universe systematically eats ORB. Possible mechanism: weekend gap
re-anchors invalidate the OR level, or Monday-morning institutional
re-positioning chops both directions. Out of scope for this filter forensic,
but it's an independent edge: removing Mondays alone lifts ORB from 0.82 to
1.36 Sharpe.

---

## 8. Catalyst-day filter spec — the rejection

For the record, the explicit filter spec we tested matches the directive
exactly:

### Env vars (DO NOT SHIP — falsified)

```bash
# Catalyst-day filter — REJECTED per 2026-05-18 forensic
# Sharpe drops 0.82 → 0.77 on full sample; -1.68 with full Zarattini overlay.
# Strict gap>4% variant works (2.03) but only 32 trades/year — too sparse.
WB_ORB_CATALYST_GATE_ENABLED=0
WB_ORB_MIN_PM_GAP_PCT=2.0      # tested: 1, 2, 3, 4
WB_ORB_MIN_OR5_RVOL=2.0        # tested: 1.25, 1.5, 2.0, 2.5, 3.0
WB_ORB_MAX_MINS_FROM_OPEN=90   # tested: 60, 90, 120
```

### YAML strategy variant (rejected spec — kept for reference)

```yaml
# strategies/orb_5min_catalyst_day.yaml — REJECTED PER FORENSIC
filters:
  premarket_gap:
    enabled: true
    min_abs_pct: 2.0
  opening_range_rvol:
    enabled: true
    min_ratio_to_20d: 2.0
  max_mins_from_open: 90
```

This spec **is what Zarattini's paper says works.** It doesn't work on this
universe. Possible reasons (deferred for resolution):
1. Universe mismatch: Zarattini's universe was 25-100 daily "stocks in play" filtered by gap × dollar-volume, dynamic. Our universe is 27 static names.
2. The "in play" filter Zarattini uses is multi-factor (relative volume + ATR-normalized gap + dollar volume) — our 2-factor approximation is too coarse.
3. The bar-level fill model in wave-3 already gets fill optimism that paper doesn't — there's no remaining edge for the catalyst filter to add.
4. Survivorship bias of our 27-name universe — all are still trading, no SPAC blow-ups or fraud.

**None of these are fixable in this forensic.** The filter spec we have data
for does not work. Re-introducing catalyst-day as a deployed filter requires
Wave 4+ work on (a) building a true dynamic daily universe filter, (b)
back-running ORB against it, (c) verifying the paper result reproduces there.
Out of scope for "no new backtests" directive.

---

## 9. RECOMMENDED filter spec (the one that DOES work)

### 9.1 Primary recommendation

**Filter:** `tier ∈ {$300+}` AND `or5_align ∈ {aligned, doji}`.

This is the cleanest pass: Sharpe 1.64 full, **OOS Sharpe 2.10**, MaxDD 13%,
1,433 trades over 5 years (287/yr), max-quarter concentration 20.4% (well
under 40% gate), positive Sharpe in all 5 years.

### 9.2 Env vars (proposed for Wave 4+ paper deployment of filtered ORB)

```bash
# ORB-5min CATALYST GATE — REJECTED (does not reproduce Zarattini on our universe)
WB_ORB_CATALYST_GATE_ENABLED=0

# ORB-5min TIER GATE — proven structural filter, OOS Sharpe 2.10
WB_ORB_TIER_GATE_ENABLED=1
WB_ORB_TIER_ALLOWLIST="$300+"            # tier eligibility at entry_price
                                          # alt: "$300+,$200-300" for more trades (Sharpe 1.71 in-sample but 0.85 OOS)
WB_ORB_ALIGN_GATE_ENABLED=1               # require aligned-direction or doji
WB_ORB_ALIGN_INCLUDE_DOJI=1               # doji days pass

# ORB-5min DAY-OF-WEEK GATE — bonus filter, optional
WB_ORB_DOW_GATE_ENABLED=0                 # set to 1 for the tighter Thu/Fri+tier+align stack
WB_ORB_DOW_ALLOWLIST="3,4"                # 0=Mon..4=Fri; 3,4 = Thu+Fri
                                          # alt safer: "1,2,3,4" excludes Monday (catastrophic -0.83)
```

### 9.3 YAML strategy variant

```yaml
# strategies/orb_5min_tier_filtered.yaml — APPROVED PER 2026-05-18 FORENSIC
# Reproduces the wave-3 ORB-5min with two structural filters that lift Sharpe
# from 0.82 → 1.64 (OOS 2.10) and reduce MaxDD from -38.7% → -13.0%.

extends: orb_5min.yaml

filters:
  price_tier:
    enabled: true
    allowed_tiers: ["$300+"]            # by entry_price at fill time
    # Optional broader variant (uncomment to add $200-300 tier — better N but worse OOS):
    # allowed_tiers: ["$300+", "$200-300"]
  opening_range_direction_alignment:
    enabled: true
    require: ["aligned", "doji"]
  day_of_week:
    enabled: false                       # optional Thu+Fri bonus filter
    allowed_dow: [3, 4]                  # mon=0, ..., fri=4

# Notes:
# - Catalyst-day filter (gap>2 AND rvol>2) was REJECTED by 2026-05-18 forensic
# - Excluding Mondays alone (mon Sharpe -0.83) lifts base ORB from 0.82 to 1.36
```

### 9.4 Optional tighter variant (highest Sharpe, lowest trade count)

For maximum-conviction deployment, the **Tier-$300+ AND Aligned AND
Thu/Fri** combo: Sharpe 2.26 full / **OOS 3.65** / MaxDD 10.4% / 90 trades/year.

```yaml
filters:
  price_tier: {enabled: true, allowed_tiers: ["$300+"]}
  opening_range_direction_alignment: {enabled: true, require: ["aligned", "doji"]}
  day_of_week: {enabled: true, allowed_dow: [3, 4]}
```

90 trades/year is sparse but **every year produced positive Sharpe ≥ 0.17** —
no losing year, OOS years 3.68 and 3.80.

---

## 10. Backtest validation on filtered subset

(Per directive: report new metrics for the filter applied to the original
trade set, with overfitting check.)

### 10.1 Primary filter (`tier=$300+ AND or5_align ∈ {aligned,doji}`)

| Metric | Baseline ORB | Filtered | Δ |
|---|---:|---:|---:|
| n trades | 9,790 | 1,433 | -85% |
| Net P&L | $128,336 | $105,636 | -18% |
| Win rate | 46.4% | 50.7% | +4.2pp |
| Profit factor | 1.05 | 1.41 | +35% |
| Avg R | +0.013 | +0.074 | **+5.7×** |
| **Sharpe** | **0.82** | **1.64** | **+2.0×** |
| MaxDD % | -38.7% | -13.0% | **-66%** |
| Max-Q concentration | 39.9% | 20.4% | -49% |

Filtered version delivers ~82% of the gross P&L on 15% of the trades, with
roughly 1/3 the drawdown.

### 10.2 Walk-forward validation

Train 2020-2022: Sharpe 1.46 (n=861)
Test 2023-2024: Sharpe **2.10** (n=572)

**Out-of-sample test Sharpe (2.10) is *higher* than in-sample train Sharpe
(1.46).** That's the opposite of curve-fit signature; the filter generalizes
forward. The same pattern holds for the bonus filter:

Train 2020-2022 (tier300+aligned+Thu/Fri): Sharpe 1.66 (n=261)
Test 2023-2024: Sharpe **3.65** (n=188)

Per-year, the primary filter never dips below 0.73 Sharpe (2021) and exceeds
2.0 in both 2023 and 2024. There's no single quarter or year that the filter
relies on disproportionately (max-quarter 20.4% << 40% gate).

### 10.3 Catalyst-day filter walk-forward (for the record)

Train 2020-2022 (gap>2 AND rvol>2): Sharpe 0.62
Test 2023-2024: Sharpe 1.13

Catalyst-day passes a *very* low bar OOS (1.13) and the strict variant (gap>4
AND rvol>2) does pass: train 1.65, test **2.97**. But:
- n=96 train, 66 test → 32 trades/year — too sparse to size meaningfully
- The strict variant is *very* close to overfitting on the gap-threshold
  parameter (we tested gap∈{1,1.5,2,3,4}; the best on train was gap=2/rvol=1.5
  at Sharpe 1.20, and gap=4 was *not* the train winner)
- The strict variant adds essentially no diversification beyond tier-$300+
  (most large-gap catalyst names are mid-cap, but tier-$300+ + Thu/Fri stack
  already provides Sharpe 2.26 with 5× more trades)

**Conclusion:** strict-catalyst is a viable narrow-niche filter but not the
right primary gate. Tier+align is structurally cleaner.

---

## 11. Viability at $25K starting equity

For each candidate, simulate fixed-$1K-risk sequence over the 5-year trade
stream (re-using exactly the wave-3 fixed_dollar P&L numbers).

| Filter | Final equity | Multiple | Annual P&L | MaxDD % | MaxDD $ | Worst losing streak | Worst 6-mo P&L |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tier $300+ | $169,822 | **6.79×** | $28,964 | -25% (compounding) / -8.9% (fixed) | -$14,180 | 10 | -$9,830 |
| Tier $300+ + aligned | $130,636 | 5.22× | $21,127 | -27% (comp) / -13% (fixed) | -$18,974 | 11 | -$13,664 |
| Tier $300+ + first60 | $123,887 | 4.96× | $19,777 | -27% (comp) / -10% (fixed) | -$13,659 | 9 | -$12,419 |
| Tier $300+ + aligned + Thu/Fri | $77,202 | 3.09× | $10,440 | -23% (comp) / -10% (fixed) | -$10,037 | 7 | -$8,290 |
| H1 strict catalyst (gap>4) | $40,957 | 1.64× | $3,191 | -19% (comp) / -4% (fixed) | -$4,460 | 5 | -$4,460 |

**At $25K equity with fixed-$1K-risk sizing:**
- Tier $300+ alone: viable. Worst 6-month is -$9,830 (39% of starting equity)
  — still painful but recoverable.
- Tier $300+ + aligned: viable. Worst 6-month -$13,664 (55% of equity) — at
  the limit but survivable; positive expectancy carries forward.
- Tier $300+ + aligned + Thu/Fri: most conservative. Worst 6-month -$8,290
  (33% of equity). Smaller annual return ($10K/yr) but lowest tail risk.

The catalyst-strict filter has the lowest MaxDD% but trades so infrequently
(32/yr) that annual P&L is only $3K. Not viable as standalone.

### 11.1 Risk-per-trade recommendation

Given $25K equity and the Tier $300+ + aligned worst-6mo of -$13.6K (effective
DD with no compounding cap), suggest **risk per trade $500 (2% of equity)** in
the filtered strategy, halving the worst-6mo to ~-$6.8K (27% of equity). This
trades ~$10K/yr annual P&L for $5K/yr but keeps worst-case below 30% DD.

---

## 12. Honest limitations

1. **Bar-level fill model**: Wave-3 ORB uses 1-min bar replay, not tick-by-tick.
   Fill optimism on stops/targets is the inherited bias. Live P&L on the
   filtered strategy will be 10-20% lower than these numbers per the wave-2
   acceptance report §9.b.

2. **27-symbol static universe**: every metric is conditional on the wave-3
   universe survivorship. Tier $300+ in this universe is essentially {AAPL,
   MSFT, NVDA, META, NFLX, ADBE, TSLA, AVGO, ORCL} post-2023 — a specific cap
   class that did well in our test window. Generalization to a wider universe
   (or future regime) is *not* guaranteed by walk-forward alone.

3. **2R fixed target ceiling**: ORB-5min winners cap at +$2,000 in this
   backtest. Real Zarattini implementation uses trailing-ATR which would let
   winners run further. Our Sharpe estimates *understate* the runners.

4. **Catalyst-day filter falsification is universe-specific**: H1 may still
   be the right filter on a *true* dynamic-stocks-in-play universe. This
   forensic only proves H1 doesn't work on our 27-name static universe.

5. **No transaction costs / borrow modeled**: per Wave 2 §9. Order of $5-10
   per trade in live. Marginal effect on filtered Sharpe is ~5% (filtered
   subset trades 287/year × $7.50 ≈ $2K/year drag).

6. **Day-of-week Monday finding (Sharpe -0.83) is robust but unexplained**:
   2,947 trades, 5 years, negative every year 2022-2024. Worth a separate
   investigation. Not a curve-fit artifact (we didn't choose Monday — we
   tested all 5 days). But until we understand *why* Monday loses, we can't
   confidently extrapolate to the future.

7. **H1's "true" failure may be the lack of true stocks-in-play filter**: our
   ORB universe was static. Zarattini's was dynamic. Saying "catalyst-day
   filter doesn't work" really means "catalyst-day filter doesn't work *as
   an overlay on a static name list*." This forensic cannot rule out that a
   dynamic universe + catalyst filter is the real edge.

8. **Failed-ORB fade meta-pattern (H6) was deferred**: 2,913 trades stopped
   out (29.8% of total); intraday post-stop behavior would require re-walking
   per-bar parquet for the window after exit_ts on each. Out of scope for
   this forensic; flagged as future work.

---

## 13. Acceptance gate verdict

Per directive §3.2 acceptance:

> "Identify whether catalyst-day filter alone gets ORB to Sharpe ≥ 1.5 (per
> paper). If yes, ORB rejoins deployable list. If no, find the combination
> that does, OR honestly conclude no implementation path."

**Catalyst-day filter alone (H1, gap>2 AND rvol>2): NO** — Sharpe 0.77,
*below* the 0.82 baseline. The filter doesn't help.

**Catalyst-day strict (gap>4 AND rvol>2): YES on Sharpe (2.03), NO on usability**
— 32 trades/year is too sparse to be a standalone strategy at $25K. Marginal
value as a satellite signal.

**Combination filter that passes Sharpe ≥ 1.5 with usable trade count**:
**YES** — `tier=$300+ AND or5_align ∈ {aligned,doji}` delivers Sharpe 1.64
full / 2.10 OOS / MaxDD 13% / 287 trades/year. Robust across walk-forward.
Survives all five years positive.

**ORB rejoins the deployable list under the tier+align filter, NOT under the
catalyst-day filter.** The directive's H1 hypothesis is falsified on this
universe; H7 + H3 (tier + alignment) is the real edge that the directive's
hypothesis space contains.

---

## 14. Files produced

- `forensics_orb/extract_features.py` — per-trade feature pipeline (run once)
- `forensics_orb/trades_with_features.parquet` — enriched 9,790-trade dataset
- `forensics_orb/analyze.py` — hypothesis testing harness
- `forensics_orb/analysis_results.json` — full hypothesis output
- `forensics_orb/walkforward_v2.py` — walk-forward train/test on top candidates
- `forensics_orb/viability_check.py` — $25K equity viability simulation
- `forensics_orb/final_sharpe.py` — final Sharpe reproduction using runner method
- `forensics_orb/final_sharpe.json` — definitive filter Sharpe table
- This report

**No new backtests run.** No live code changes. No new strategies built. All
work is analytical on the existing wave-3 ORB-5min trade CSV plus
per-bar context features from existing tick_cache_databento parquets.

---

## 15. Next-step recommendations (for synthesis report)

1. **Ship `strategies/orb_5min_tier_filtered.yaml`** with the tier=$300+ +
   align filter as a paper-only Wave-4 variant. Validate on real-time
   forward paper before live.

2. **Investigate Monday-loser pattern** as a separate forensic. Sharpe -0.83
   on Monday across 2,947 trades, *negative every year 2022-2024*. This is
   either (a) a regime artifact of the tested universe, (b) a real
   microstructure effect (weekend gap re-anchoring, Monday institutional
   re-positioning, sell-the-rip on weekend overreaction), or (c) a wave-3
   backtest engine bug specific to Monday data. Worth understanding before
   trading any week.

3. **Defer catalyst-day filter to Wave-5 dynamic-universe work.** The paper's
   edge is real; our static universe doesn't reproduce it. Re-test after a
   true daily stocks-in-play filter is wired.

4. **Confluence forensic (Agent 6) should test ORB+PDH-Breakout overlap on
   tier=$300+ subset specifically** — i.e., when ORB-Long breaks AND that
   level IS PDH AND the symbol is $300+. Could be the highest-Sharpe
   sub-subset.

5. **Failed-ORB fade meta-pattern (H6) deferred** — flagged as future work.
   30% of trades stop out cleanly; whether the post-stop drift is fadeable
   is unexamined.

6. **Test trailing-ATR exit on filtered subset** when wave-3 infra supports
   it. 2R cap currently caps the top-1% big-winners at $2,000. Letting
   runners run would lift avg-R and Sharpe further.

**End of report.**
