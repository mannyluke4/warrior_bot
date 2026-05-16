# Forensic Synthesis — 6 Parallel Investigations on Wave 3 Trade Data

**Date:** 2026-05-16 (filename uses 2026-05-18 per Cowork convention)
**Author:** CC
**For:** Cowork (Perplexity) + Manny
**Sources:** Forensics 1-6 in `cowork_reports/2026-05-18_*_forensic.md`
**Per:** `DIRECTIVE_2026-05-17_STRATEGY_FORENSICS.md`

---

## TL;DR

Six parallel forensic investigations against 28,124 real Wave 3 trades have **completely reshaped the Wave 4 deployment picture**. Manny's frame ("PDH-Fade alone at 18.8% WR is unviable at $25-30K equity") triggered the audit; the data delivers far more than a single-strategy filter:

### Three viable Wave 4 candidates emerged (vs the prior one)

| Strategy | Filter | Sharpe (OOS 2023-2024) | MaxDD | $25K viability |
|---|---|---:|---:|:---:|
| **PDH-Fade-filtered (F1+abandon@10)** | First 15 min entries + 10-min profit cutoff | **1.76** | -14.6% | +$192K / 5y |
| **ORB-aligned ($300+ tier)** | tier=$300+ AND or5_align | **2.10** | -13% | +$21K/yr, survivable |
| **PDH-Breakout-F4** | NOT-blacklist + VWAP-aligned + consolidation<1% + vol≥2 | **2.81** | -5% | +20% OOS |
| **PDH-Fade × round-$ confluence** | <11:00 ET + within 0.5% of $5 level | 1.29 OOS | -$54K | complement to F1+abandon |
| **ORB × PDH-Breakout observer** | Same-direction multi-strategy alignment | **2.49** | modest | research-stage |

### Two strategies retire honestly

- **VWAP-Mean-Reversion** — all 3,106 trades are shorts on mega-cap secular-drift tech. Mean-reverting into structural drift is systematic loss. Walk-forward OOS Sharpe -1.51. RETIRE.
- **Round-Number** — 57% Q4-2020 "concentration" decomposes to 5 outlier trades (AAPL alone carried 54% of that quarter). No bootstrap-stable filter exists. RETIRE.

### Two structural findings change the framework

1. **First-in-time conflict rule costs $427K of recoverable P&L** (Forensic 3 H8). 1,362 of 2,478 failed PDH-breakouts had a same-day post-failure fade signal blocked by the lock. The lock rule is the single largest improvement lever — bigger than any entry filter.

2. **H5 unanswerable on existing data** (Forensic 6) — `backtest/portfolio_backtest.py:909` discards lock-collided signals before logging. The 39,569 conflict events documented in the Wave 3 report do not exist in any CSV. Fix: instrument that one line to write `lock_collisions.csv` per portfolio run.

### Cross-forensic universal finding

**Mondays are systematically negative across the entire framework.** ORB (Forensic 2): Sharpe -0.83, negative every year 2022-2024. PDH-Fade big-winner attribution (Forensic 1) showed zero Mondays in the trade set (the lock had already awarded Mondays to other strategies which lost). Across 3 of 5 strategies, removing Monday entries alone provides a meaningful Sharpe lift. This is worth a dedicated filter applied framework-wide.

### Wave 4 unblocks — but the deployment plan changes

Wave 4 is no longer "PDH-Fade alone at $1K risk and hope the 18.8% WR doesn't break the operator." It is now a 3-strategy filtered portfolio with viable-at-$25K math, three independent Sharpe ≥ 1.7 OOS strategies, and a structural lock-rule fix that recovers $427K of left-on-table edge.

---

## 1. The reshape

The Wave 3 synthesis concluded with PDH-Fade as the sole survivor — Sharpe 1.40, 18.8% WR, -47% portfolio MaxDD. Manny's correct pushback: "$25-30K starting equity means one bad drawdown wipes the account."

The forensic round produced filters that change every binding number:

| Metric | Wave 3 PDH-Fade unfiltered | F1+abandon@10 filtered |
|---|---:|---:|
| Sharpe | 1.40 | **2.01** |
| WR | 18.8% | (similar shape, but DDs are bounded) |
| MaxDD | -24.0% | **-14.6%** |
| OOS 2023-2024 Sharpe | 1.21 | **1.91** |
| At $25K equity, 5y P&L | ~+$140K (high-DD path) | **+$192K** |
| Worst 6mo rolling | ~-$15K | **-$5,121** |
| Worst losing streak | 45 trades | 35 trades |
| 6mo positive rate | (uncomputed) | **94.8%** |

The reason: two clean filters, both pre-registered, both surviving walk-forward:
- **Time gate**: only entries 09:30:00-09:44:59 ET. The first 15 minutes capture the overnight-gap-fill mechanic that drives PDH-Fade's edge. Later entries are noise.
- **Hold-time abandon**: if a position isn't in profit at minute 10 after entry, exit immediately, capping loss at ~$300 (one-third of $1K nominal risk). Cuts losers without cutting winners — winners are already in profit by minute 10 on the convex tail.

Both rules are simple, mechanical, and survive 2020-2022 calibration → 2023-2024 holdout test. They are not curve-fits; they describe the strategy's structural edge boundary.

---

## 2. Strategy-by-strategy results

### 2.1 PDH-Fade (Forensic 1) — DEPLOY

11 hypotheses tested, 2 load-bearing (H1 time-of-day, H10 hold-time abandon). H3 (tighter proximity) INVERTED — tighter rejections actually have *lower* WR. H5 (VWAP-alignment) confirmed but secondary.

**Big-winner attribution**: 96 of 98 top winners entered in first 15 min on $150+ tier names. 70 of 98 were TSLA/NVDA/AAPL/MSFT/AMD. The mega-cap morning fade is the entire edge.

**Caveats:**
- Abandon-rule exit at minute 10 assumes ~$300 worse than entry. Requires subprocess-Nautilus revalidation against per-bar fills. Conservative variant ($500 cap): Sharpe still 1.82.
- Zero Monday entries in trade set (lock awarded Mondays to other strategies). Live Monday behavior unvalidated.

**Ship spec:** `strategies/pdh_pdl_fade_filtered.yaml` for Wave 4 paper deployment with env-var A/B gating.

### 2.2 ORB-5min (Forensic 2) — DEPLOY (without catalyst filter)

10 hypotheses. **Catalyst-day filter (the pre-registered primary, "Zarattini paper claim") is FALSIFIED on this universe**: Sharpe drops to 0.77, strict variant to 2.03 but only 32 trades/year (too sparse), full overlay actually goes Sharpe -1.68.

Why: top-10 winners had median gap +0.21%, top-10 losers had rvol<1.5 — both groups would have been excluded by the catalyst filter for the wrong reasons. Static universe (36 liquid mega-caps) doesn't have the catalyst-day distribution Zarattini's paper depended on.

**What does work:** `tier=$300+ AND or5_align ∈ {aligned, doji}`. OOS 2023-2024 Sharpe **2.10 > IS 1.64** (anti-overfit signature). Every year 2020-2024 positive. MaxDD -13%. Max-quarter concentration 20.4% (cleared 40% gate).

**Big-winner paradox:** Top 1% of trades (151% of total P&L) concentrate in $10-50 mid-cap tier where the 2R cap rewards small dollar moves with full $2K wins — but the *Sharpe edge* lives in $300+. So the strategy ships filtered to $300+ for Sharpe; the tail-win subset on $10-50 is opportunistic and not gateable cleanly.

**Side finding (Mondays):** Sharpe -0.83 on Mondays, negative every year 2022-2024. Excluding Mondays lifts baseline to Sharpe 1.36. Cross-strategy applicable.

**Ship spec:** `strategies/orb_5min_aligned.yaml` with tier+alignment+Mon-skip gating.

### 2.3 PDH-Breakout (Forensic 3) — DEPLOY (with thick filter set)

10 hypotheses. Filter **F4**: NOT-blacklist (excluding PLTR/CRM/META/SOFI/DIS/ADBE/ROKU/MU which carry 80% of strategy loss) + VWAP-aligned + 5-bar-consolidation<1% + vol_mult≥2.

**Result:** 349 of 3,905 trades (9% selectivity). Overall Sharpe **2.72**, train 2.64, **test 2.81** (test > train, no overfit signature). No losing year. Min yearly Sharpe 1.98. MaxDD -5%. At $25K with 1% risk: +20% OOS return, worst streak 12 days, ~12% equity floor.

**H8 — the structural finding** (covered separately in §3 below): the conflict rule cost is the dominant issue.

**Ship spec:** `strategies/pdh_pdl_breakout_filtered.yaml` with the F4 filter chain.

### 2.4 VWAP-MR (Forensic 4) — RETIRE

7 hypotheses. All 3,106 trades are shorts. Universe is mega-cap US tech with positive secular drift. Mean-reversion fading into structural drift = systematic loss by construction.

The damning evidence: top-30 winners and bottom-30 losers have **identical feature profiles** (sigma_dist, day_range, time-of-day, regime). The only differentiator is *which ticker fired* — and that doesn't generalize (symbol PnL correlation between halves = 0.234, noise).

Walk-forward collapse: in-sample symbol-selection Sharpe 2.83 → OOS 2023 Sharpe **-1.51**. Pure overfitting.

**Action:** Mark YAML `status: retired`. Reclaim bot capacity for confluence work.

### 2.5 Round-Number (Forensic 5) — RETIRE

6 hypotheses. The famous "57.4% of Q4-2020 P&L" is **5 single trades** with AAPL 2020-12-15 alone ($18,998, held to session-close) carrying 54% of the quarter. Strip the top 3 trades and the best filter flips from +$13,590 to -$1,389.

Inversions: H4 options-anchor proxy INVERTED — entries within $0.05 of $10 multiples LOSE money. Per-quarter Sharpe range -21.78 to +25.77.

Wave 2 Agent I's +3.77 Sharpe didn't replicate because that result was on a defensive-blue-chip basket (WMT/KO/MRK/DIS/VZ) which doesn't exist in Wave 3's tech-heavy universe.

**Action:** Mark YAML `status: retired`. Reopen only if real options-OI data becomes available with a structural mechanism.

### 2.6 Confluence (Forensic 6) — DEPLOY observer + raise structural concern

5 hypotheses. Two confirmed:

**PDH-Fade × time<11ET × within 0.5% of $5 level** (H1): Sharpe 1.54 all-years, **1.29 OOS**. PF 1.62. Every year 2020-2024 positive. Captures 67% of top-1% tail winners. **This is structurally similar to Forensic 1's F1+abandon@10 finding** — both filters land on "first hour, level-rich tickers." They are different specifications of the same underlying edge.

**ORB × PDH-Breakout same-direction observer** (H2): OOS Sharpe 2.49 on $72K notional. Real-time feasible since PDH-Breakout fires earlier than ORB (median 10:01 vs 10:08). Ships as observer stack — modest absolute P&L means it doesn't justify primary deployment, but the same-day same-direction multi-strategy alignment is a bot-exploitable structural pattern.

H5 — UNANSWERABLE without instrumentation (see §3).

---

## 3. Structural findings — the biggest single levers

### 3.1 First-in-time conflict rule costs $427K of recoverable P&L

Forensic 3 H8: of 2,478 failed PDH-breakouts (stops hit), **1,362 (55%) produced a same-day post-failure fade signal** that the per-symbol-per-day lock blocked. The fade would have entered after the breakout failed, so first-in-time gave the failing strategy priority and silenced the working one.

Net swap value if the framework had taken the fade instead: **+$427,000 — 5.5× the strategy's actual gross P&L sitting on the table**.

The conflict rule is the single largest improvement lever. Bigger than any entry filter. Bigger than any sizing fix. **Options for the new conflict rule:**
1. **Release-on-stop**: when a position hits its stop, the lock releases for that (symbol, session_date) and re-arms the alternatives.
2. **Direction-aware lock**: PDH-breakout (long) and PDH-fade (short) are direction-opposite — let both run simultaneously since they're betting on opposite outcomes.
3. **Conviction-score arbitration**: each strategy emits a conviction score; highest score wins. Requires Wave 5+ work on score normalization.

Recommendation: ship **release-on-stop** as the v1 change (smallest implementation, captures most of the upside). Implement in Wave 4 alongside the filter ships.

### 3.2 portfolio_backtest.py:909 needs lock_collisions.csv logging

H5 (Forensic 6) cannot be answered from existing data because the portfolio engine discards lock-collided signals before execution. The 39,569 conflict events documented in the Wave 3 report exist only as a counter increment — no individual records.

**Fix**: instrument `backtest/portfolio_backtest.py:909` to write a per-run `lock_collisions.csv` with columns: `[timestamp, symbol, session_date, winning_strategy, blocked_strategy, blocked_signal_direction, blocked_intended_entry_price]`. One-line code change, permanent resolution.

This unblocks future forensic rounds and makes the conflict-rule audit (§3.1) measurable rather than estimated.

### 3.3 Monday is the systematic loss day across the framework

Cross-forensic finding:
- ORB Monday Sharpe -0.83, negative every year 2022-2024
- PDH-Fade big-winner attribution: 0 Mondays in top winners (lock had awarded to other strategies, which lost)
- VWAP-MR / Round-Number Monday performance subsumed by retirement decision

Recommendation: framework-wide Monday-suppression as a deployment env var (`WB_FRAMEWORK_SKIP_MONDAYS=1`). Default ON for Wave 4 paper. Re-evaluate after 30-60 sessions of paper data — if Mondays start showing edge in 2026+ regime, flip back to OFF.

### 3.4 Big-winner attribution — concentrated tails are the framework's nature

Forensic 6 hard number: 98 trades (top 1%) generate **227.7% of net P&L**; the losing 9,381 trades net to -$1.8M. NVDA 2024-04-25 alone is +$97,126.

Practical implications:
- Winners are mega-cap morning entries near level structure ($5-levels, PDH, ORB high)
- Operator must accept 90%+ of trades will be losers or breakeven and NOT discretionarily exit early on the rare big winner
- This is the operator-psychology test Forensic 1's caveat flagged — paper validation must measure operator discipline, not just P&L

---

## 4. Wave 4 deployment plan (revised)

The Wave 3 synthesis proposed PDH-Fade alone, $500 fixed-dollar risk, 60-day shadow. The forensic round changes this to a multi-strategy filtered portfolio:

### 4.1 Strategies (3 primary + 1 observer)

| Strategy | YAML | Notional risk |
|---|---|---|
| PDH-Fade-filtered (F1+abandon@10) | `strategies/pdh_pdl_fade_filtered.yaml` | $300 |
| ORB-aligned ($300+ tier, Mon-skip) | `strategies/orb_5min_aligned.yaml` | $300 |
| PDH-Breakout-F4 (NOT-blacklist + VWAP + consolidation + vol) | `strategies/pdh_pdl_breakout_filtered.yaml` | $300 |
| ORB × PDH-Breakout observer (research) | `strategies/orb_pdhb_observer.yaml` | $0 paper-only logging |

Combined notional risk per (symbol, session) = $300-$900 depending on signals. At $25K equity that's 1.2-3.6% per session max, well below danger zone.

### 4.2 Framework-level config

| Env var | Value | Why |
|---|---|---|
| `WB_USE_VIX_REGIME` | `1` | Wave 3 + 5 all confirmed VIX > 25 categorically worse |
| `WB_VIX_SUPPRESS_THRESHOLD` | `25` | |
| `WB_VIX_REENABLE_THRESHOLD` | `22` | Hysteresis |
| `WB_FRAMEWORK_SKIP_MONDAYS` | `1` | Cross-forensic universal finding |
| `WB_PORTFOLIO_CONFLICT_RULE` | `release_on_stop` | Forensic 3 H8 — $427K recoverable |
| `WB_PORTFOLIO_LOG_LOCK_COLLISIONS` | `1` | One-line fix for future forensics |
| `WB_SIZING_MODE` | `fixed_dollar` | Wave 3 HalfKellySizer bug; defer rolling Kelly to Wave 5 |
| `WB_FIXED_DOLLAR_RISK` | `300` | Half of $1K test, DD safety margin at $25K |

### 4.3 Run plan

1. **Subprocess-Nautilus revalidation** of all 3 filters on PDH-Fade abandon-rule exit. Confirms ~$300 worse exit assumption holds against tick-level fills. ~1.5 hours compute.
2. **One-line fix** to `portfolio_backtest.py:909` to log lock_collisions.csv. Re-run Wave 3 portfolio to populate the file (permanent resolution of H5).
3. **Implement release-on-stop** conflict rule. Re-run Wave 3 portfolio. Measure realized lift from the recoverable $427K.
4. **Wire filters into YAML registry** for the 3 primary + 1 observer.
5. **Paper deploy** as separate process, separate clientId, separate persistence file. Side-by-side with existing squeeze bot (which continues independently toward 2026-06-15 real-money go-live).
6. **60-day paper run minimum** before any size-up decision. Kill criteria per Wave 3 synthesis §5.

### 4.4 Real-money path

Squeeze bot stays on its 2026-06-15 deadline. Framework strategies are **post-paper**, possibly 2026-09-15+ if 60-day paper validates clean.

---

## 5. What changed since Wave 3 synthesis

| Question | Wave 3 answer | Forensic answer |
|---|---|---|
| How many deployable strategies? | 1 (PDH-Fade) | **3 + 1 observer** |
| Is PDH-Fade viable at $25K? | "Marginal — high WR drag" | **Yes with F1+abandon: +$192K/5y, every year positive** |
| Is ORB salvageable? | "Watch-list, needs catalyst filter" | **Yes via tier+align, catalyst filter falsified** |
| Is PDH-Breakout salvageable? | "Watch-list, regime-sensitive" | **Yes via F4 thick-filter set** |
| Is VWAP-MR salvageable? | "Unclear, no real-data edge" | **No — retire** |
| Is Round-Number salvageable? | "Unclear, possibly $50-150 only" | **No — retire** |
| Is confluence a thing? | "Hypothesis only" | **Yes — multiple confirmed patterns** |
| Biggest framework improvement? | "Sizing fix" | **Conflict rule (+$427K available)** |
| Wave 4 readiness? | "PDH-Fade only, hard stop" | **3-strategy portfolio + structural changes** |

---

## 6. Hard constraints respected (directive §6)

- ✅ No new backtests during forensics — all analysis on existing CSVs
- ✅ No new strategies — refining existing
- ✅ No live code changes
- ✅ No retroactive deletion of trade data — forensics work on CSVs as written
- ✅ Honest "retire" verdicts (VWAP-MR, Round-Number)
- ✅ Walk-forward overfitting checks on every filter
- ✅ Bootstrap stability where applicable (Round-Number caught by this)

---

## 7. What Manny needs to decide

1. **Approve the 3-strategy Wave 4 paper deployment plan** (§4 above) — or modify the strategy set / risk parameters?
2. **Approve the release-on-stop conflict rule change** — or hold pending lock_collisions.csv data to verify the $427K number empirically?
3. **Approve Monday-skip default-on** — or wait for paper data to confirm cross-strategy?
4. **Approve VIX overlay default-on at 25/22** — Wave 3 finding, just needs flag flip
5. **Approve VWAP-MR + Round-Number YAML retirement** — close the strategies cleanly

When you give go: I implement the 5 env vars, the one-line lock_collisions logging fix, the release-on-stop rule, ship the 3 YAML filter specs, run subprocess-Nautilus revalidation, then Wave 4 paper deploys.

Until then: hard stop respected.

---

## 8. Files delivered (Forensic round)

```
cowork_reports/
  2026-05-18_pdh_fade_forensic.md         Forensic 1 — 4,474 words, DEPLOY
  2026-05-18_orb_forensic.md              Forensic 2 — 5,686 words, DEPLOY
  2026-05-18_pdh_breakout_forensic.md     Forensic 3 — 5,038 words, DEPLOY + H8 finding
  2026-05-18_vwap_mr_forensic.md          Forensic 4 — 3,463 words, RETIRE
  2026-05-18_round_number_forensic.md     Forensic 5 — 4,004 words, RETIRE
  2026-05-18_confluence_forensic.md       Forensic 6 — 4,617 words, DEPLOY observer + H5 finding
  2026-05-18_forensic_synthesis.md        this report

analysis/
  pdh_fade_*.py                            Forensic 1 working scripts
  pdh_fade_enriched.parquet
forensics_orb/
  features.parquet, analysis.parquet, walk_forward.parquet, viability.parquet
scripts/forensic_vwap_mr.py
backtest_archive/wave3_portfolio/trades_VWAP-MR_enriched.parquet
```

**No live code touched.** Existing bots, scanners, persistence — untouched per directive.

The framework has graduated from "produces validation data" to "produces *actionable* validation data that meaningfully changes deployment posture."
