# Strategy Forensics — Five Parallel Investigations

**Date:** 2026-05-17
**Author:** Cowork (Perplexity)
**For:** CC
**Trigger:** Manny: "PDH-Fade as a hard-only option doesn't work for me. $25-30K starting equity means one bad drawdown wipes the account. We need to dig in much like we did for squeeze — analyze trades, find patterns, what do losers have in common, what do winners have in common, how can we use data to boost winning odds for each strategy including this one?"

---

## TL;DR

Five parallel forensic workstreams. One per Phase 1 strategy + portfolio cross-strategy analysis. Each follows the exact methodology of the WB forensic week (5/17): pre-register hypotheses, test against existing trade data, produce honest findings, propose filters, validate filters don't overfit.

**Goal:** Turn failed strategies into viable ones via pre-entry filters, and tighten PDH-Fade's win rate so it's viable at $25-30K starting equity.

**Constraint:** All work is on existing Wave 3 backtest data (`backtest_archive/wave3_portfolio/`). No new backtests until findings are in.

**Acceptance:** Each forensic produces (a) loser pattern findings, (b) winner pattern findings, (c) proposed filter spec with expected effect, (d) backtest validation of the filter showing improvement without overfitting.

---

## 1. Why this matters

The Wave 4 PDH-Fade-only deployment proposal had the right rigor (validation gates) but wrong premise: **it accepted the strategy as-given.** Per Manny's point, that's not viable at his actual starting equity.

The framework's value isn't a list of "passed gate / failed gate" decisions. It's **5 years × 36 symbols × 5 strategies of real trade data** that we can interrogate.

Three things this forensic round produces:

1. **Save lost strategies.** ORB at 0.82, PDH-Breakout at 0.70, possibly VWAP-MR and Round-Number — these are strategies where the *base* signal has edge but noise drowns it. The right filters could turn one or more into Sharpe ≥ 1.2.

2. **Reshape PDH-Fade.** 18.8% WR is what makes it brutal. If a pre-entry filter eliminates 50% of trades but the remaining trades have 30%+ WR, drawdowns shrink dramatically and the strategy becomes viable at smaller equity.

3. **Find confluence.** When 2 strategies signal on the same level at the same time, those trades probably behave differently. Confluence trades might be the highest-edge subset across the whole framework.

---

## 2. The forensic methodology (matches WB 5/17)

Each investigation follows this structure (mandatory):

1. **Hypothesis (pre-registered):** what feature do we expect distinguishes winners from losers?
2. **Method:** which trade subsets to compare, which features to extract from the bar data we have
3. **Data table:** raw numbers, not interpretation
4. **Findings:** what the data actually shows
5. **Falsification check:** was the hypothesis disproven? To what extent?
6. **Proposed filter:** if findings hold, what filter would have caught it?
7. **Filter backtest:** apply filter to the original trade set, report new Sharpe / WR / DD
8. **Overfitting check:** does the filter generalize across years? Walk-forward test.
9. **Limitations:** sample size, bias, missing data

**No interpretation before the data is in.** No filter ships without overfitting check.

---

## 3. Per-strategy forensic specs

### 3.1 PDH-Fade forensic (Agent 1)

**Goal:** Find a filter that boosts win rate from 18.8% to ≥30% while preserving the convex-payoff winner profile.

**Data source:** `backtest_archive/wave3_portfolio/trades_PDH-PDL-Fade_fixed_dollar.csv` (9,874 trades, 5 years).

**Pre-registered hypotheses (test all):**

1. **Time of day**: do winners cluster in specific 30-min buckets? Hypothesis: morning fades (09:35-11:00) have higher WR than afternoon (13:00-15:55) due to overnight gap-fill mechanics. Falsify: if no time-bucket has WR > 25%, hypothesis dies.

2. **Day of week**: Mon/Tue PDH-Fades vs Wed/Thu/Fri? Hypothesis: early-week fades work better (weekly range establishment). Falsify: WR delta < 3pp.

3. **Distance from level at entry**: how close to the level was the fail-test? Hypothesis: tighter rejections (within 0.05% of level) outperform loose ones (0.05-0.10%). The 0.1% proximity gate is current; maybe 0.05% is better.

4. **Day range at entry**: was the day's range already large (>2× ADR) or compressed (<0.5× ADR) at entry? Hypothesis: compressed-range days produce cleaner level reactions.

5. **VWAP relationship at entry**: was price ABOVE VWAP for a PDH-fade (short) entry? Hypothesis: above-VWAP PDH-fades are fighting trend and lose more. Filter: only fade PDH when price is at-or-below VWAP at entry; only fade PDL when at-or-above VWAP.

6. **Recent volatility (last 5 bars)**: was the rejection bar a quiet "exhausted" candle or a violent reject? Hypothesis: violent reject (range > 1.5× prior 5-bar avg) has higher WR than quiet rejection.

7. **Gap context**: was today's open a gap up/down from prior close > 1%? Hypothesis: PDL-fade on gap-up day works (gap fills back); PDL-fade on gap-down day fails (continuation).

8. **Multi-touch confirmation**: did price touch this level multiple times today before the fade? Hypothesis: 2nd or 3rd touch fades work better than 1st touch (level has been "respected" already).

9. **Price tier**: real-data tier attribution already showed PDH-Fade is balanced across tiers (Wave 2 report §7.1). Re-validate on Wave 3 real data — is one tier outperforming?

10. **Hold-time pattern**: among winners, what's the distribution of hold times? Among losers? Is there a "if not by minute X, abandon" rule that cuts losers without cutting winners?

11. **Big-winner attribution**: the +$97K outlier and other massive winners — what features did they share? Were they multi-touch fades on specific tier? Specific time? Specific gap context? **This is the most important question** because winners drive 75%+ of P&L.

**Output:** `cowork_reports/2026-05-18_pdh_fade_forensic.md` with full hypothesis table, data, filter spec, backtest validation.

**Acceptance:** at least 1 filter that, applied retroactively, produces Sharpe ≥ 2.0 without losing more than 30% of winner P&L. If no such filter exists, document that honestly and the strategy stays paper-rejected at small equity.

---

### 3.2 ORB-5min forensic (Agent 2)

**Goal:** Validate the catalyst-day filter hypothesis (already flagged as expected lift). Find additional pre-entry filters.

**Data source:** `backtest_archive/wave3_portfolio/trades_ORB-5min_fixed_dollar.csv` (9,790 trades, 5 years).

**Background:** Real-data Sharpe 0.82 (just under 1.2 gate). Zarattini paper claims Sharpe 2.81 on catalyst-day universe specifically. The base signal has edge; the question is which subset.

**Pre-registered hypotheses:**

1. **Catalyst-day filter** (THE big one): premarket gap > 2% AND today's RVOL > 2× the 20-day baseline for that 5-min bar. Hypothesis: catalyst-day ORB has dramatically better Sharpe. Wave 5 work prerequisite — this report informs whether it's worth wiring.

2. **5-min bar volume**: was the opening 5-min bar high volume (>1.5× the typical opening bar)? Hypothesis: high-volume opens produce more reliable ORB levels.

3. **Opening bar direction**: green opening bar → ORB-long signals only, red opening bar → ORB-short only. Hypothesis: aligning ORB direction with opening bias improves WR.

4. **Distance from VWAP at breakout**: if breakout fires when price is already 1%+ above VWAP, is the move exhausted? Hypothesis: tighter VWAP-distance breakouts work better.

5. **Time-from-open**: ORB breakouts in first 30 min vs 30-60 min vs >60 min. Hypothesis: 30-90 min sweet spot.

6. **Failed-ORB reversal**: when an ORB-long fails and stops out, what's the next 30-min behavior? Is there a meta-pattern (ORB-fail-fade) we should code as a separate strategy?

7. **Tier attribution**: which price tier produces best ORB performance?

8. **VIX regime overlay** (re-validate independently): does ORB perform better in VIX 15-25 vs other regimes?

9. **Day of week**: Monday opens vs Friday opens — different ORB behavior?

10. **Float / market cap interaction**: smaller-float symbols in our universe vs mega-caps — does ORB favor one?

**Output:** `cowork_reports/2026-05-18_orb_forensic.md`

**Acceptance:** identify whether catalyst-day filter alone gets ORB to Sharpe ≥ 1.5 (per paper). If yes, ORB rejoins deployable list. If no, find the combination that does, OR honestly conclude ORB has no implementation path at our scale.

---

### 3.3 PDH-Breakout forensic (Agent 3)

**Goal:** PDH-Breakout was 0.70 Sharpe — below 1.2 gate but directionally positive. Find what's eating the edge.

**Data source:** `backtest_archive/wave3_portfolio/trades_PDH-PDL-Breakout_fixed_dollar.csv` (3,905 trades, 5 years).

**Background:** Wave 2 noted breakout strategies typically have higher win rate (68% synthetic) but smaller average winners. Real data showed -40.4% MaxDD which is brutal. Something specific is going wrong.

**Pre-registered hypotheses:**

1. **Drawdown attribution**: which months/symbols/setups caused the worst drawdowns? Is it concentrated or distributed? If concentrated, what was happening in those periods?

2. **First-touch vs N-th touch**: is PDH-breakout on first attempt of the level vs second/third attempt different?

3. **Time-since-level-set**: a PDH from yesterday vs a PDH from a wider gap (multi-day gap due to weekend). Hypothesis: fresh PDH > stale PDH.

4. **Volume confirmation strength**: directive currently requires 2× volume. Test 1.5×, 3×, 5× thresholds.

5. **VWAP relationship**: was price above VWAP when PDH broke (continuation) vs below (failed breakout from oversold)? Hypothesis: above-VWAP PDH-breakouts work much better.

6. **Pre-breakout consolidation**: was there a tight range under PDH (consolidation) or a vertical run-up to PDH (exhausted breakout)? Hypothesis: consolidation breakouts > exhausted breakouts.

7. **Day-range expansion**: by the time of breakout, was today's range already > yesterday's range? If yes, level may be exhausted.

8. **Failed PDH-breakouts**: do they pair with successful PDH-fades on the same day? If so, the conflict-resolution rule (first-in-time wins) might be giving us the worst of both — we take the breakout that fails and miss the fade that works. Audit the same-day overlap losses.

9. **Trailing stop behavior**: the 2R target with 1.5R trailing — is trailing too tight on real volatility? Look at exit-reason distribution.

10. **Tier attribution**: similar to others.

**Output:** `cowork_reports/2026-05-18_pdh_breakout_forensic.md`

**Acceptance:** identify whether a subset of PDH-Breakout has Sharpe ≥ 1.5. If yes, propose the filter set. If not, conclude breakout is structurally worse than fade and retire it.

---

### 3.4 VWAP-MR forensic (Agent 4)

**Goal:** VWAP-MR was 0.04 Sharpe — essentially noise. Is there a buried signal?

**Data source:** `backtest_archive/wave3_portfolio/trades_VWAP-Mean-Reversion_fixed_dollar.csv` (3,106 trades, 5 years).

**Background:** Wave 2 synthetic Sharpe was 35.74. Real Sharpe is 0.04. This is the biggest synthetic-to-real Sharpe collapse in the framework. Worth understanding why.

**Pre-registered hypotheses:**

1. **VWAP slope filter**: the YAML had a regime gate (flat-VWAP → mean-revert, sloped-VWAP → trend-continue). Was this implemented correctly? Verify trade tags by regime, check whether MR trades only fired on flat-VWAP days.

2. **Standard deviation extreme**: trades fired at 2σ from VWAP. Test 2.5σ and 3σ thresholds — at what extreme does mean-reversion actually work?

3. **Time-since-touch**: how long had price been at the VWAP band before the entry trigger? Quick touches vs sustained drift at extreme.

4. **Day-type filter**: trending days vs chop days. Hypothesis: VWAP-MR can ONLY work on chop days. On trend days, "mean reversion at 2σ" is just buying every breakout to die.

5. **Time-of-day**: VWAP becomes less useful late in session (gravitates as the band stabilizes). Hypothesis: VWAP-MR only works in middle of session, not first hour or last hour.

6. **Universe filter**: which symbols had ANY positive contribution? Maybe VWAP-MR works on specific stock characteristics (tight range, no news, etc).

7. **Drawdown attribution**: -21.9% MaxDD on what's basically a noise-strategy means trades cluster losses badly. Are losses concentrated on specific symbols or dates?

**Output:** `cowork_reports/2026-05-18_vwap_mr_forensic.md`

**Acceptance:** either find the subset where VWAP-MR has Sharpe ≥ 1.2 (with day-type filter), OR conclude honestly that the strategy doesn't have edge on this universe.

**Note:** This is the strategy most likely to be retired. That's a valid outcome.

---

### 3.5 Round-Number forensic (Agent 5)

**Goal:** Round-Number was 0.02 Sharpe and 57.4% quarterly concentration. Find whether it's a real strategy or just regime noise.

**Data source:** `backtest_archive/wave3_portfolio/trades_Round-Number_fixed_dollar.csv` (1,449 trades, 5 years).

**Background:** 57.4% of positive-quarter P&L came from 2020Q4 (per Wave 3 quarterly heatmap). That's a regime trade, not an evergreen strategy.

**Pre-registered hypotheses:**

1. **Tier attribution**: which price tier produced the 2020Q4 spike? If concentrated in one tier, does removing other tiers fix the strategy?

2. **$50-150 tier specifically**: directive originally specified $50-150 tier; Wave 2 retried tiers. What does $50-150 alone look like?

3. **Whole-dollar vs $5-dollar levels**: were trades at $50.00 different from trades at $55.00 or $52.50? Hypothesis: only the whole-$5 levels are real (gamma pinning).

4. **Options-OI overlay**: directive flagged this as Phase 2 enhancement. Can we approximate with available data — do trades near round numbers that ALSO have visible options activity (proxy: large round-number close at session end) work better?

5. **Time-of-day**: round-number levels often trigger end-of-day flows. Hypothesis: late-day round-number trades work; early-day don't.

6. **Symbol filter**: which symbols had positive contribution? Maybe RN only works on options-heavy mega-caps.

**Output:** `cowork_reports/2026-05-18_round_number_forensic.md`

**Acceptance:** either find a tightly-filtered subset with Sharpe ≥ 1.2, OR retire the strategy.

**Note:** Like VWAP-MR, likely retirement candidate.

---

### 3.6 Cross-strategy confluence forensic (Agent 6)

**Goal:** When multiple strategies signal on the same symbol at the same time, those trades probably behave differently. Find whether confluence creates a higher-edge subset.

**Data source:** All 5 strategy CSVs + the 39,569 conflict events from Wave 3 portfolio backtest.

**Pre-registered hypotheses:**

1. **PDH-Fade + Round-Number confluence**: when PDH coincides with a round-$ level (e.g., AAPL PDH at $202.50, both PDH and a $2.50 level), do those fades work better?

2. **PDH-Breakout + ORB confluence**: when ORB-Long breaks the opening-range high AND that high IS the PDH, do those breakouts work better?

3. **VWAP-aligned confluence**: any strategy signaling AT a VWAP level (PDH coincides with VWAP, etc) — does the VWAP confluence add edge?

4. **Multi-strategy "all-aligned" days**: days where all 4 directional strategies agree on direction — what's the day P&L on those days vs split days?

5. **First-in-time penalty**: the conflict rule currently picks first-in-time. Does that always pick the wrong trade? Audit the 39,569 conflict events — would the OTHER strategy have produced better P&L on those days?

**Output:** `cowork_reports/2026-05-18_confluence_forensic.md`

**Acceptance:** identify whether confluence-based filter produces higher-edge subset across strategies. This might be the most important agent — confluence is exactly the kind of pattern a bot can exploit that humans can't (multi-strategy parallel monitoring).

---

## 4. Sync points

After all 6 forensics land (likely same day given parallel agents):

1. **Synthesis report** by Cowork: which filters work, which strategies become viable, which retire
2. **Manny review**: pick the deployable subset
3. **Filter implementation** by CC: ship the validated filters as YAML strategy variants (e.g., `pdh_pdl_fade_filtered.yaml`)
4. **Backtest revalidation** of the filtered strategy set: portfolio Sharpe, drawdown, viable-at-$25K analysis
5. **Wave 4 decision (revised)**: paper-deploy the new filtered strategy set, not raw PDH-Fade

---

## 5. Specific deliverables per forensic

Each forensic report must include:

- **Hypothesis table**: 8-12 pre-registered hypotheses + falsification result
- **Loser profile section**: top 10 features that distinguish losers from winners (with statistical significance)
- **Winner profile section**: top 10 features that distinguish winners from losers
- **Big-winner attribution**: what made the top 1% of winners big
- **Proposed filter spec**: env vars + YAML changes that would apply the findings
- **Backtest validation**: apply filter, report new metrics (Sharpe, WR, MaxDD, trade count, profit factor, R-distribution)
- **Overfitting check**: walk-forward by year (filter calibrated on 2020-2022 applied to 2023-2024)
- **Viability at $25K starting equity**: with the filtered strategy, what's the expected drawdown, worst losing streak, and 6-month worst-case P&L?

---

## 6. Hard constraints

1. **No new backtests until forensics are in.** This is analysis, not iteration.
2. **No new strategies in this round.** Phase 1 + Phase 2 set is locked. We're refining what exists.
3. **No live deployment changes.** Production track (squeeze 6/15) is untouched.
4. **No retroactive deletion of trade data.** Forensics work on the existing CSVs as written. Re-runs only happen after forensic recommendations are agreed.
5. **Honest "no edge" findings are acceptable.** If VWAP-MR or Round-Number truly has no edge, document that and retire. We're not curve-fitting our way to survival.

---

## 7. What this directive is NOT

- Not a Wave 4 deployment directive (that's still pending Manny's decision and now contingent on these findings)
- Not a new framework feature build (existing primitives are sufficient)
- Not a live trading change (paper-only investigation)
- Not new strategy R&D (refining existing strategies)

---

## 8. Why this is the right move

Per Manny's framing: we now have *excellent data* for 12 strategies. The forensic methodology proved itself with WB (killed a non-edge strategy cleanly). Now apply it constructively — turn the failures into wins by finding which subsets work.

This is exactly the analytical work the framework was built to enable. The same agent capacity that ran 5 waves overnight can run 6 forensics in parallel. Most agents complete in 30-60 minutes given the data is already on disk.

The output: a smaller, sharper set of strategies that are actually viable at Manny's real starting equity. PDH-Fade with a 30%+ WR filter changes the deployment math completely. ORB with a catalyst-day filter could be the second viable strategy. Confluence trades might be the highest-edge subset.

---

## 9. Reports CC owes

| When | Report | Status |
|---|---|---|
| Parallel | `2026-05-18_pdh_fade_forensic.md` | Agent 1 |
| Parallel | `2026-05-18_orb_forensic.md` | Agent 2 |
| Parallel | `2026-05-18_pdh_breakout_forensic.md` | Agent 3 |
| Parallel | `2026-05-18_vwap_mr_forensic.md` | Agent 4 |
| Parallel | `2026-05-18_round_number_forensic.md` | Agent 5 |
| Parallel | `2026-05-18_confluence_forensic.md` | Agent 6 |
| After all 6 land | Cowork writes the synthesis | Cowork |

---

## 10. Files referenced

- `backtest_archive/wave3_portfolio/trades_PDH-PDL-Fade_fixed_dollar.csv` (9,874 trades)
- `backtest_archive/wave3_portfolio/trades_ORB-5min_fixed_dollar.csv` (9,790 trades)
- `backtest_archive/wave3_portfolio/trades_PDH-PDL-Breakout_fixed_dollar.csv` (3,905 trades)
- `backtest_archive/wave3_portfolio/trades_VWAP-Mean-Reversion_fixed_dollar.csv` (3,106 trades)
- `backtest_archive/wave3_portfolio/trades_Round-Number_fixed_dollar.csv` (1,449 trades)
- `backtest_archive/wave3_portfolio/metrics_fixed_dollar.json`
- `tick_cache_databento/<SYM>/1m_<YYYY-MM-DD>.parquet` (for pulling per-bar context features)
- `cowork_reports/2026-05-16_wave3_portfolio_backtest.md` (the input baseline)
- `cowork_reports/2026-05-17_loser_forensic_synthesis.md` (the methodology reference from WB forensic week)

---

## 11. Tone

This is the moment the framework justifies its existence. We have 28,124 real trades sitting in CSV files. Each one has features we can extract from the underlying bar data. The same methodology that killed WB cleanly can now build viable filtered strategies cleanly.

Manny's $25-30K starting equity constraint reframes the validation gates entirely. PDH-Fade at 18.8% WR is unviable. PDH-Fade with a filter that gets it to 30%+ WR is potentially viable. We don't know until we look.

CC: 6 parallel agents. Existing data only. Findings reports, not opinions. Filter proposals validated by backtest, not by intuition. If nothing works for any strategy, that's a valid outcome — and tells us this universe doesn't support framework strategies at small equity, which is itself useful.

Go.
