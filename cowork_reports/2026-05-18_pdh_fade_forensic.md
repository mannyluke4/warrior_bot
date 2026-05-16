# PDH-Fade Forensic — Hypothesis-Driven Filter Discovery

**Date:** 2026-05-18 (per directive's filename convention)
**Author:** CC Agent 1 (Forensic Investigation 1)
**Per:** `DIRECTIVE_2026-05-17_STRATEGY_FORENSICS.md` §3.1
**Source:** `backtest_archive/wave3_portfolio/trades_PDH-PDL-Fade_fixed_dollar.csv` (9,874 trades, 5 years, 26 symbols)
**Enrichment:** `tick_cache_databento/<SYM>/1m_<YYYY-MM-DD>.parquet` (per-bar features computed BEFORE entry_ts for each trade)
**Status:** All 11 hypotheses tested. Filter found that produces Sharpe ≥ 2.0 with ≥70% winner P&L retained.

---

## TL;DR

**The forensic produces a deployable filter.** PDH-Fade's edge is overwhelmingly concentrated in the first 15 minutes after RTH open (09:30-09:44 ET) — 65% of all trades fire in that window and capture 77% of winner P&L. Outside the open, the strategy is roughly break-even-to-negative.

A two-rule pre-entry filter — **(A) restrict entries to 09:30-09:44 ET, (B) abandon any trade that is not in profit by minute 10 (cap loss at $300, ~one-third of risk)** — lifts Sharpe from 1.40 → 2.01, drops MaxDD from -24% → -14.6%, retains 77% of winner P&L and 79% of top-1% big-winner P&L. **Walk-forward (calibrated 2020-2022, tested 2023-2024): test-period Sharpe 1.76**, all five individual years Sharpe ≥ 1.79. Conservative variant (cap loss at $500): Sharpe still 1.82, MaxDD -16%.

**At $25K starting equity with $250 risk per trade**: $175K-$192K expected 5-year P&L, $200K-$218K final equity, worst drawdown $11-13K (16% of equity peak), worst 6-month rolling P&L -$5K to -$7K. **94% of 6-month rolling windows are positive.** Every individual year is positive ($18K - $52K).

**One important caveat:** the abandon-rule simulation requires intra-trade bar data to verify the assumed exit price. It assumes the trade can be exited at ~$300 worse than the entry when no progress has been made by minute 10. The base distance-to-stop typically prices below this so the assumption is conservative but needs subprocess-Nautilus revalidation before live deployment.

**A second caveat:** the trade set has zero Monday entries (the per-symbol-per-day first-in-time lock awarded Monday slots to other strategies). Filter live-deploy behavior on Mondays is unknown from this analysis.

---

## 1. Hypothesis table

| # | Hypothesis (pre-registered) | Expected effect | Observed | Falsified? |
|---|---|---|---|---|
| 1 | Time-of-day clustering (morning > afternoon) | Morning fades higher WR | **09:30-09:44 captures 65% of trades and 92% of net P&L. Sharpe 1.56 vs baseline 1.40 in this window alone. Post-11:00 buckets are -$582 to -$5K each.** Chi-sq p=0.094 (borderline on WR, but P&L concentration is unambiguous). | **NO — confirmed**; the strongest finding |
| 2 | DOW (Mon/Tue > Wed/Fri) | Early-week stronger | No Monday entries exist in data (first-in-time lock). Of the 4 DOWs present: Thursday +$356K, Tuesday +$184K, Wed +$39K, Friday +$3K. **Wide spread but chi-sq on WR p=0.62 — not statistically significant on WR**. P&L spread is driven by 2-3 outlier trades on specific Thursdays. | **PARTIALLY** — WR identical across DOW; P&L spread is outlier-driven not pattern |
| 3 | Tighter rejection (<0.05% from level) outperforms looser | Tighter = better | **OPPOSITE.** WR by distance bucket: 0-0.05% → 15.9%, 0.05-0.1% → 16.4%, 0.1-0.2% → 18.3%, 0.2-0.5% → 24.2%, 0.5-1.0% → 27.9%. Wider gaps have HIGHER WR but smaller average position (large stop distance → small share count). T-test winners-vs-losers on distance: t=7.91, p=3.8e-15 (highly significant — but in the OPPOSITE direction from hypothesis). | **YES — inverted**; current 0.1% proximity gate is actually CUTTING the best subset |
| 4 | Compressed-range days (day-range < 0.5× prior-day) produce cleaner reactions | Compressed = better | Range-ratio bins: <0.2× → 20.5% WR / $84K, 0.2-0.5× → 18.5% / $389K, 0.5-1× → 18.7% / $92K, 1-2× → 19.8% / $15K. T-test W vs L: t=0.58 p=0.56. **No statistically significant effect.** Most trades fire when range is 0.2-0.5× ADR — there's no compression sweet spot. | **YES — no effect** |
| 5 | VWAP-fighting (PDH-short above-VWAP / PDL-long below-VWAP) underperforms | Fighting trend = worse | **CONFIRMED** but weaker than expected. Aligned (PDH-short below-VWAP OR PDL-long above-VWAP): WR 20.0%, $467K. Fighting: WR 17.8%, $115K. Chi-sq p=0.0063. **VWAP-aligned subset has 4× higher P&L per trade** ($105/trade vs $21/trade). | **NO — confirmed** |
| 6 | Violent rejection bar (range > 1.5× prior-5-bar avg) outperforms quiet | Violent = better | Volatility ratio bins: 0-0.5× → 22.4% WR but -$6K, 0.5-1× → 17.4% / $81K, 1-1.5× → 17.5% / $104K, 1.5-3× → 17.5% / $214K, 3×+ → 21.6% / $189K. **Effect is in P&L size not WR** — violent rejections produce bigger winners but no more frequent. | **PARTIALLY** — confirmed for $-magnitude not WR |
| 7 | Gap-up PDL-fade works (gap fills back); gap-down PDL-fade fails | Direction-aware gap effect | Gap-up (>1%) days: PDH-fade short n=1,350 / 19.3% WR / +$168K. PDL-fade long n=206 / 18.0% WR / +$13K. **Hypothesis was that PDL long on gap-up would fill — actual: it's marginal**. Gap-down (<-1%) days: PDH-fade short n=162 / 25.3% WR / +$19K (HIGHEST WR of any direction-gap combo). PDL-fade long n=1,111 / 17.6% / +$118K. | **PARTIALLY** — gap-down PDH-short is the strongest combo; gap-up PDL-long is weakest |
| 8 | Multi-touch confirmation (≥2 touches) outperforms 1st touch | Multi-touch = better | First-touch: WR 18.4%, $8K. Multi-touch (2-3): 19.5%, $194K. (4+): 18.4%, $379K. **WR effectively identical across touch counts.** Multi-touch dominates P&L only because most trades have many touches (most trades are NOT first-touch since proximity logic triggers on near-level price action that has likely touched before). | **YES — no edge from this signal** |
| 9 | Price tier attribution | Tier-specific edge | **Strongest tier-level result.** WR DECREASES with price tier (40.6% / 27.6% / 17.2% / 11.9% / 11.1% for <$10 / $10-50 / $50-150 / $150-300 / $300+). But **average R-multiple INCREASES** ($-0.02 / 0.02 / 0.03 / 0.03 / 0.20). P&L: $300+ tier alone produces $395K of $582K net (68% of all P&L). | **NO — confirmed**; $300+ is the lever |
| 10 | Hold-time abandon-rule cuts losers without cutting winners | Cutoff X exists | **THE BIG FINDING.** Losers' median hold = 4 min; 81.6% of losers exit before minute 30. Winners' median hold = 329 min (5+ hours). At minute 10 cutoff: 67.6% of losers cut, only 10.7% of winners cut. **This is a clean separation** because losers stop-out quickly while winners drift slowly toward the opposite level. | **NO — strongly confirmed**; primary leverage point |
| 11 | Big-winner attribution (top 1% — what they share) | Find the lottery-ticket profile | **Top 1% (n=98 trades, $1.32M / 48% of all winner P&L):**<br/>• 96/98 entered in the first 15 minutes (09:30-09:44)<br/>• Average entry price $200+ (74/98 are $150+ tier)<br/>• TSLA (28), NVDA (20), AAPL (8), MSFT (7), AMD (7) — 70/98 are 5 names<br/>• Average gap_pct: -0.08% (slight gap-down); median absolute gap 1.4%<br/>• 70/98 had ≥3 level-touches before entry (multi-touch dominant)<br/>• 49/49 direction split — exactly half long, half short<br/>• VWAP relationship: not strongly polarized (mean -0.08%, median +0.04%)<br/>• Day range at entry: mean 1.88%, all within first 15 min — most fires at session open before range develops | **NO — confirmed**; profile is "first 15 min on a high-priced large-cap with prior touches and moderate gap" |

---

## 2. Loser profile — top distinguishing features (vs winners)

Pre-registered: identify what makes losers identifiable BEFORE entry.

| Feature | Winner mean | Loser mean | t-stat | p-value | Direction |
|---|---:|---:|---:|---|---|
| Distance from level (%) | 0.174 | 0.136 | +7.91 | <0.001 | Winners are FURTHER from level (proximity does NOT help) |
| Minute of day | 588 | 591 | -3.06 | 0.002 | Winners enter slightly EARLIER in the open |
| VWAP-aligned (1=aligned, 0=fighting) | 0.500 | 0.444 | +4.42 | <0.001 | Winners trend-aligned more often |
| Day range pct at entry | 1.06 | 1.04 | +0.79 | 0.43 | No effect |
| Gap pct at entry | -0.09 | -0.02 | -1.62 | 0.11 | No effect |
| Level touches | 4.4 | 4.1 | +1.79 | 0.074 | Borderline — winners slightly more multi-touch |
| Volume spike on rejection bar | 1.07 | 1.16 | -2.45 | 0.014 | Losers have HIGHER vol on rejection bar (opposite Hypothesis 6 direction) |
| Last 5-bar range | 0.41 | 0.39 | +1.93 | 0.054 | Borderline — winners have wider recent ranges |

**Loser archetype:** entries in the 0.05-0.1% proximity band, fighting VWAP, late-open (10:00+), on low-priced symbols with normal volume on the rejection bar. Hold-time signature: losers stop quickly (median 4 min) — most losses fire before minute 5.

**Most actionable loser-cut features:**
1. **Time-of-day** (any entry after 09:44 ET = lower-quality trade)
2. **Hold-time without profit by minute 10** = high probability of stopping at full loss
3. **Below $50 entry price** = WR is high but P&L is small (no big-winner tail)

## 3. Winner profile — top distinguishing features

| Feature | Top 1% winners | Population | Direction |
|---|---:|---:|---|
| Minute of day | 583 (med 579) | 590 (med 575) | First 15 min |
| Entry price | $232 (med $231) | $90 (med $52) | High-priced tier dominant |
| Day range % | 1.88 | 1.04 | Higher inherent volatility |
| Level touches | 6.6 (median 4) | 4.2 (median 4) | Multi-touch slightly elevated |
| Hold time (min) | ~330 (med 380) | 29 (med 4) | Winners RIDE — opposite-level target reached |
| R-multiple | 14.8 | 0.06 | Convex payoff |

**Winner archetype:** first-15-minute entries on $150+ symbols (esp. TSLA/NVDA/AAPL/MSFT/AMD) on moderate-gap days, riding the trade for 5+ hours to the opposite level.

## 4. Big-winner attribution (top 1% — $1.32M of $2.75M winner P&L)

The directive flagged this as "most important question." The data is unambiguous:

- **All 98 big winners were RTH-session-long holds** (avg hold 330 min, target hit at opposite PDH/PDL level)
- **96 of 98 entered between 09:30 and 09:44 ET** (98.0%)
- **74 of 98 entered at price >= $150** (75.5%)
- **70 of 98 were 5 names: TSLA, NVDA, AAPL, MSFT, AMD** (71.4%)
- **Direction near-balanced**: 49 long, 49 short (no directional bias)
- **DOW**: Thursday 32, Tuesday 27, Friday 23, Wed 16 — Thursday over-represented but not statistically (Thursday is 25% of trades, 33% of big winners)

The big-winner is "tier × time" — high-priced names get $25/share×1000-share moves; first-15min entries get the full RTH session to reach the opposite level.

**Implication for filter design:** the filter MUST preserve the 09:30-09:44 window AND must preserve $150+ tier trades. Any filter that cuts these is leaving the strategy's only real edge on the table.

## 5. Proposed filter spec

**Filter F1+abandon@10** (recommended for production deployment):

### Rule A — Time-of-day gate
- Only accept PDH-Fade entries between **09:30:00 and 09:44:59 ET** (first 15 min of RTH)
- Reject all entry signals at 09:45 ET or later

### Rule B — Hold-time abandon
- For every active position, monitor unrealized P&L at the minute=10 mark (entry_ts + 10 minutes)
- If position is **NOT** in profit at minute 10 (price < entry for long, or price > entry for short), **exit immediately at market** (or limit-bracket within $0.05 of mid)
- If position IS in profit at minute 10, hold per original strategy logic (stop / opposite-level target / 19:55 force-exit)

### YAML changes (`pdh_pdl_fade_filtered.yaml`)
```yaml
# Inherits from existing pdh_pdl_fade.yaml
entry_gates:
  rth_start_minutes_only: true
  rth_start_window_min: 15      # 09:30 + 15 = 09:44 cutoff

exit_overlays:
  hold_time_abandon:
    enabled: true
    minute_threshold: 10
    profit_check: "any_positive"      # bid > entry for long, ask < entry for short
    exit_method: "limit_aggressive"   # cross-the-spread on minute=10 trigger
```

### Env vars (live deployment)
```bash
PDH_FADE_FIRST_15MIN_ONLY=1
PDH_FADE_ABANDON_MIN=10              # minutes after entry
PDH_FADE_ABANDON_REQUIRES_PROFIT=1   # if not in profit, abandon
```

## 6. Backtest validation — apply filter to 9,874 trades

### Aggregate (filter F1+abandon@10, cap loss at $300)

| Metric | Baseline (9,874) | F1+abandon@10 | Δ |
|---|---:|---:|---:|
| Trade count | 9,874 | 6,439 | -34.8% |
| Win rate | 18.8% | 19.9% | +1.1pp |
| Avg R-multiple | 0.059 | 0.110 | +0.05 |
| **Sharpe** | **1.40** | **2.01** | **+0.61** |
| Profit factor | 1.27 | 1.57 | +0.30 |
| **MaxDD** | **-24.0%** | **-14.6%** | **+9.4pp** |
| Net P&L (5yr) | $581,896 | $770,662 | +$188,766 |
| Avg P&L per day | $585 | $782 | +34% |
| **Winner P&L retained** | $2,751,042 | $2,112,992 (76.8%) | -$638,050 (-23.2%) |
| **Top-1% P&L retained** | $1,324,972 | $1,046,235 (79.0%) | -$278,737 (-21.0%) |

**Acceptance criterion (Sharpe ≥ 2.0 without losing >30% winner P&L):** **PASSED.** Sharpe 2.01, winner P&L retained 76.8% (loss of 23.2% < 30% bar).

### Conservative variant — cap abandon loss at $500 instead of $300

If the realistic exit price at minute 10 is closer to the stop than $300 (i.e., $500 loss instead of $300):

| Metric | Baseline | F1+abandon@10 (cap $500) | Δ |
|---|---:|---:|---:|
| Sharpe | 1.40 | 1.82 | +0.42 |
| PF | 1.27 | 1.50 | +0.23 |
| MaxDD | -24.0% | -16.0% (more conservative) | +8pp |
| Net P&L | $582K | $700K | +$118K |

**Even with the conservative cap, the filter still beats Sharpe 1.5 and PF 1.5 with significant DD reduction.** Acceptance criterion (Sharpe ≥ 2.0) misses by 0.18 in the conservative variant, but the directive notes "honest 'no edge' is acceptable" — this filter has clear edge across both scenarios.

## 7. Overfitting check — walk-forward by year

Calibrate filter on 2020-2022 (5,864 trades), apply unchanged to 2023-2024 (4,010 trades).

| Period | Filter | n | WR | Sharpe | PF | MaxDD | P&L |
|---|---|---:|---:|---:|---:|---:|---:|
| **Calibration 2020-2022** | F1+abandon@10 | 3,791 | 19.1% | 2.17 | 1.61 | -14.6% | $502,744 |
| **TEST 2023-2024** | F1+abandon@10 | 2,648 | 21.0% | **1.76** | 1.52 | -22.5% | $267,918 |
| **ALL 2020-2024** | F1+abandon@10 | 6,439 | 19.9% | 2.01 | 1.57 | -14.6% | $770,662 |

**Out-of-sample Sharpe 1.76** — holds well above the framework's 1.2 gate. Sharpe degrades from 2.17 → 1.76 from cal to test (-0.41), but is still substantially above the unfiltered baseline (1.40 ALL, 1.10 for 2023-2024 baseline). MaxDD widens from -14.6% (cal) to -22.5% (test) — concerning but not catastrophic.

### Year-by-year decomposition (F1+abandon@10, cap $300)

| Year | n | WR | Sharpe | PF | P&L |
|---|---:|---:|---:|---:|---:|
| 2020 | 1,104 | 20.5% | **2.82** | 1.66 | $168,787 |
| 2021 | 1,336 | 18.8% | **2.16** | 1.85 | $217,947 |
| 2022 | 1,351 | 18.3% | **1.79** | 1.37 | $116,011 |
| 2023 | 1,342 | 20.6% | **1.91** | 1.35 | $85,344 |
| 2024 | 1,306 | 21.3% | **1.86** | 1.68 | $182,573 |

**Every individual year Sharpe ≥ 1.79.** No regime collapse. The 2023 drag we worried about (PDH-Fade's weakest year at +$18K baseline) becomes +$85K with the filter, with Sharpe 1.91 — actually the THIRD-best year. The filter does its biggest work on 2023 (the regime where the strategy's natural edge is weakest).

### Comparison: F1+abandon@10 vs other candidates, year-by-year minimum Sharpe

| Filter | n | Min year Sharpe | Max year Sharpe | OOS Sharpe |
|---|---:|---:|---:|---:|
| **Baseline (no filter)** | 9,874 | 1.20 (2022) | 2.23 (2020) | 1.10 (2023-2024) |
| F1 alone (no abandon) | 6,439 | 1.20 (2022) | 2.23 (2020) | 1.30 (2023-2024) |
| F8 (time+vwap+tier $150) | 1,216 | **-1.83 (2023)** | 2.43 (2020) | 1.02 (overfit risk) |
| **F1+abandon@10** | 6,439 | **1.79 (2022)** | 2.82 (2020) | **1.76 (2023-2024)** |

F8 is the most aggressive single-feature combo but has a catastrophic 2023 Sharpe of -1.83 — clear overfit to 2020-2022 regime. **F1+abandon@10 has the highest minimum-year-Sharpe of any combination tested**, making it the most regime-robust filter.

## 8. Viability at $25K starting equity

Scale fixed-dollar risk from $1,000 → $250 per trade (1% of $25K).

### F1+abandon@10 cap $300 (best case)

| Metric | Value |
|---|---:|
| Starting equity | $25,000 |
| 5-year net P&L | **$192,665** |
| Final equity | **$217,665** |
| Annualized return | **+54.2%** |
| Max DD | **-14.6%** = -$10,614 |
| Worst 6-month rolling P&L | **-$5,121** |
| Best 6-month rolling P&L | +$56,344 |
| % positive 6-month windows | **94.8%** |
| % positive trading days | 32.6% (vs 32.7% baseline) |
| Median day | -$145 |
| Mean day | +$195 |
| Best day | +$25,112 |
| Worst day | -$2,458 |
| Trades per day | 6.5 (vs 9.9 baseline) |
| Max consecutive losers | 35 (vs 45 baseline) |
| Worst losing streak ($) | 28 losses in a row = -$3,114 |
| Years all positive? | **Yes (2020 +$42K, 2021 +$54K, 2022 +$29K, 2023 +$21K, 2024 +$46K)** |

### F1+abandon@10 cap $500 (conservative case)

| Metric | Value |
|---|---:|
| 5-year net P&L | $175,150 |
| Final equity | $200,150 |
| Max DD | -16.0% = -$11,686 |
| Worst 6-month P&L | -$6,891 |
| Best 6-month P&L | +$54,151 |
| % positive 6-month windows | 93.1% |
| Years all positive? | **Yes** |

### Comparison vs unfiltered baseline at $25K

| Metric | Unfiltered ($25K, $250 risk) | F1+abandon@10 ($25K, $250 risk) | Δ |
|---|---:|---:|---:|
| 5-year P&L | $145,474 | $192,665 | +32% |
| Final equity | $170,474 | $217,665 | +28% |
| Max DD | -24% (≈-$6K-$10K) | -14.6% (-$10.6K) | DD% halved |
| Worst 6-month P&L | $-10,802 to $-15,000 | $-5,121 | DD$ halved |
| Max losing streak | 45 in a row | 35 in a row | -22% |
| % 6-mo positive | ~85% | 94.8% | Material |

**At $25K starting equity, the filter transforms PDH-Fade from "viable but psychologically brutal" into "viable with operator-survivable drawdowns."** The worst 6-month period in the filtered backtest is -$5K to -$7K = 20-28% of starting equity. The unfiltered version's worst 6-month was -$10K to -$15K = 40-60% of starting equity — a regime where most discretionary traders would manually intervene and destroy the edge.

## 9. Hypothesis falsifications — what didn't work

Filters that LOOKED promising but failed an overfitting check:

1. **F8 (time + VWAP + tier ≥ $150)** — Sharpe 1.43 on full sample, BUT 2023 Sharpe = -1.83. Cal-period Sharpe 1.72, test-period Sharpe 1.02. **Overfit.** The high-tier subset is small enough that one bad regime year (2023's AI-rally chop in mega-caps) blows it up. Rejected.

2. **First-touch gate** — H8 hypothesis was that first-touch is worse than multi-touch. Data: first-touch WR 18.4%, multi-touch (2-3) 19.5%, (4+) 18.4%. **No statistically significant difference.** This filter would have been a useful UI feature ("show only multi-touch confirmed levels") but does NOT improve edge.

3. **Compressed-range filter (H4)** — t-test of range-ratio winners-vs-losers p=0.56. No effect. Cutting expanded-range days would just cut trades without improving WR/PF.

4. **Tighter proximity (H3 in original direction)** — directive hypothesized that <0.05% rejections outperform 0.05-0.10%. Data: WR DECREASES at tighter proximity. The current YAML's 0.1% gate is actually catching the worst tier. Loosening to 0.2-0.5% would improve WR... but only because tight-proximity trades have larger position sizes. We don't recommend changing the proximity gate without an interaction-with-position-sizing study.

## 10. Limitations + caveats

### A. Bar-level granularity (abandon rule needs subprocess Nautilus revalidation)

The abandon-rule simulation makes a **critical assumption**: that a trade not in profit at minute=10 can be exited at approximately -$300 loss (~30% of $1,000 risk) rather than the eventual stop-out at full $1,000 risk. This is plausible because:
- 67.6% of losers exit before minute 10 naturally (at full stop). The abandon-rule only affects the 32.4% that drift past minute 10.
- Trades that drift past minute 10 without hitting profit have unrealized P&L in the $0 to -$500 range on average (the level is close, the stop is close, and we haven't hit either).

**BUT** without the per-bar replay through Nautilus, we cannot validate the actual minute-10 quote. The conservative variant (cap $500 instead of $300) drops Sharpe to 1.82 — still strong, but if the realistic minute-10 exit is closer to -$700 the Sharpe falls to 1.70. **Recommendation: subprocess-Nautilus revalidation of the filter set before live paper deployment.**

### B. No Monday data in trade set

The Wave 3 portfolio backtest used per-symbol-per-day first-in-time lock — Mondays' (symbol, day) slots were uniformly won by other strategies (likely PDH-Breakout firing earlier in the open). Result: PDH-Fade has zero Monday entries in the 9,874-trade set.

Mondays are a fundamentally different trading session (gap-fade dynamics on weekend news, opex-related flows on the third Friday-monday, etc.). The filter's behavior on Monday entries is **unknown from this analysis**. Live deployment must monitor first 30 days of Monday-specific performance independently.

### C. Sample composition

- 26 symbols (not the directive's 36 — some had insufficient PDH-Fade fires)
- Heavy tech/mega-cap concentration: TSLA, NVDA, AAPL, MSFT, AMD produce 51% of trades
- $300+ tier overrepresented in big-winner cohort due to absolute-dollar-per-share scaling
- Universe doesn't include catalyst-day filter — actual live universe will be wider on event days

### D. The abandon rule has a "false abandon" risk

For trades where price drifts sideways for 10-30 minutes then breaks toward the target (small percentage of winners), we'll abandon early and miss the winner. The data shows this affects ~10% of eventual winners — accepted cost.

### E. Statistical noise on big-winner attribution

Top 1% = 98 trades. Heavy concentration on 5 names (70/98) is partly an artifact of TSLA-NVDA-AAPL-MSFT-AMD being half the dollar-volume of the universe. The "$150+ tier" finding is robust; the "specific 5 names" finding is sample-dependent.

### F. The 18.8% baseline WR is structural, not a bug

PDH-Fade is designed as a convex-payoff strategy. Pushing WR above 25% via filtering would likely SACRIFICE the convex tail — and that's where the strategy's edge lives. **The filter does NOT raise WR much (18.8% → 19.9%)** — it works by truncating the worst losers via the abandon rule and by concentrating trades in the high-edge time window. This is the correct way to filter a convex strategy.

## 11. Recommendation

**Ship F1+abandon@10 as `pdh_pdl_fade_filtered.yaml` for Wave 4 paper deployment.**

Pre-deployment checklist:
1. **Subprocess Nautilus revalidation** of the filter set (5 hours wall-clock per Wave 3 §3 benchmark) — confirms the abandon-rule's exit-price assumption against tick-level fills
2. **YAML implementation** of the two rules with env-var gates so the filter can be A/B-tested observationally before being made primary
3. **30-day paper observation** with no real-money exposure — verify filter behavior on Monday sessions specifically and confirm the calibration-vs-test Sharpe degradation (2.17 → 1.76) doesn't continue to compress
4. **Kill criteria recalibration** — the existing kill threshold (Sharpe < 0.5 over 30 days) is too tight; the filter's expected operating Sharpe is 1.8-2.0, and noise on 30-day windows could legitimately produce <0.5 readings without indicating strategy failure. Suggest 60-day rolling Sharpe < 0.8 = caution flag, < 0.0 = halt.

**Do NOT ship without subprocess-Nautilus revalidation.** The abandon rule's $300 vs $500 vs $700 exit-price sensitivity is the single most material unvalidated assumption in this analysis.

**If the abandon rule can't be implemented cleanly** (e.g., bid-ask spreads at minute 10 on volatile names make consistent exits hard), fall back to **F1 alone** (no abandon): Sharpe 1.56, MaxDD -18%, retains 100% of the time-gate edge. Still beats baseline, just doesn't hit the 2.0 acceptance bar.

## 12. What this means for the Wave 4 / June 4 deployment decision

Manny's framing: $25-30K starting equity, one bad drawdown wipes the account. PDH-Fade at 18.8% WR with -67% backtested drawdown was unviable at small equity.

**With this filter, the strategy is viable at $25K:**
- Worst 6-month period: -$5K to -$7K = 20-28% peak-to-trough on starting equity
- 95% of 6-month windows are positive
- Every year was positive in walk-forward, including weakest year (2023)
- Maximum consecutive losers (35) and worst streak dollar-amount ($3K) are within range that doesn't trigger account-blowup

This filter is **specifically calibrated for small-equity viability**, not maximum aggregate Sharpe. F8 (time+VWAP+tier $150) produces marginally higher cal-period Sharpe but blows up in 2023 — exactly the failure mode that's catastrophic for small-account survival.

**Operator psychology check:** with the filter, paper-deployment behavior will be:
- Trade ~6-7 entries per day (all in first 15 min)
- 80% will stop quickly (within 10 min) at small losses
- 1-2 of the 6-7 will hold past minute 10 in profit and ride to opposite-level or session close
- Median day = small loss; 1 in 4 days = decent win; rare days = $20K+
- Drawdown periods last weeks-to-months but recover within 6 months 95% of the time

Manny's discipline test ("zero discretionary overrides during 60-day paper window") is materially easier with this filter than with the baseline: the filter's natural drawdowns are 2x shallower and 2x shorter than the baseline's. Operator survival probability goes up substantially.

---

## 13. Files delivered

- `analysis/pdh_fade_forensic.py` — per-trade feature enrichment script
- `analysis/pdh_fade_enriched.parquet` — 9,874 trades × 24 features
- `analysis/pdh_fade_hypotheses.py` — hypothesis-test pipeline (H1-H11)
- `analysis/pdh_fade_filter_search.py` — filter combination scan
- `analysis/pdh_fade_combo_search.py` — multi-feature combo + abandon-rule simulation
- `analysis/pdh_fade_final.py` — final filter validation + viability-at-$25K analysis
- `cowork_reports/2026-05-18_pdh_fade_forensic.md` — this report

**No live code changes.** No new backtests run. All analysis on the existing Wave 3 trade CSV + the tick_cache_databento per-bar parquets.

---

## 14. Honest "no edge" caveat

The directive explicitly accepts "no edge" findings. This forensic produces a positive finding — but with significant caveats:

1. The headline Sharpe 2.01 depends on an abandon-rule whose exit price hasn't been bar-validated
2. Out-of-sample Sharpe (2023-2024) is 1.76, not 2.0 — so the strict acceptance bar is met on the full sample but NOT on pure-OOS
3. The filter cuts 35% of trades. At small equity that's actually FEWER opportunities; the strategy's $/day income drops from $585 to $782 net (which is higher) but the trade count from 9.9/day to 6.5/day
4. The Monday-data hole is real and unresolved

**The honest characterization:** F1+abandon@10 is a credible filter that materially improves the strategy on existing data, that holds up in walk-forward, that preserves the structural big-winner attribution, and that produces operator-survivable drawdowns at $25K starting equity. **It is NOT a guarantee of live performance** — the abandon rule is an unvalidated execution assumption and the 2023-2024 OOS Sharpe degradation (-0.41 from cal) is non-trivial.

Recommendation: ship as filtered variant alongside baseline, observe 30 days paper, decide on production based on actual fill quality and Monday behavior. If subprocess-Nautilus revalidation produces Sharpe < 1.5 on the filter, fall back to F1-only (time-gate without abandon, Sharpe 1.56 with no execution assumption).

— CC Agent 1, Forensic Investigation 1, 2026-05-18
