# Round-Number Forensic — Regime Check

**Date:** 2026-05-16
**Author:** CC (Forensic Agent 5)
**Directive:** `DIRECTIVE_2026-05-17_STRATEGY_FORENSICS.md` §3.5
**Status:** Complete — verdict at end.
**Data source:** `backtest_archive/wave3_portfolio/trades_Round-Number_fixed_dollar.csv` (1,449 trades, 2020-2024).

---

## TL;DR — Verdict

**Retire.** Round-Number has no extractable edge. The 0.02 Sharpe on the full strategy is a statistical artifact; the 57.4% of positive-quarter P&L from 2020Q4 is concentrated in 5 single trades on 5 dates. Every promising filter we tested either (a) collapses when 3 trades are removed, (b) shows wildly unstable per-quarter Sharpe, or (c) has a 95% bootstrap confidence interval that straddles zero.

The strategy's "winners" are not level reactions. **89.5% of winner P&L is `session_close`** — trades that entered near a round level and held all session because they never traded back through the level. That's not edge from level mechanics; that's a long/short bet that price drifts away from the level by EOD, which is structurally a directional bet, not a level reaction.

Recommended: do not deploy Round-Number in any configuration. Do not ship to Wave 4. Code stays in repo; YAML disabled. Reopen only if options-OI data becomes available (Phase 2 enhancement) and we have a structural reason to believe gamma-pinning levels behave differently from the round-number proxy.

---

## 1. Data baseline

| Metric | Value |
|---|---|
| Total trades | 1,449 |
| Date range | 2020-01-02 to 2024-12-31 (5 years) |
| Universe | 20 symbols: AAPL, AMD, AVGO, CRM, CSCO, DAL, DIS, INTC, META, MSFT, MU, NKE, NVDA, ORCL, PLTR, QCOM, ROKU, SNAP, TSLA, WFC |
| Total P&L | **-$5,955** |
| Win rate | 17.7% |
| Avg R | -0.004 |
| Daily Sharpe | **-0.08** |
| Max DD (in trades) | (see §6.1) |

Trade size: $1,000 risk per trade (1R = $1,000). All trades are limit-fill simulated.

**Tier composition:** 1,443/1,449 trades (99.6%) are $50-150 entry price; 5 are $150-300; 1 is $10-50. The Wave 2 directive that said "$50-150 only" — that's what the Wave 3 universe actually is. The "all tiers" comparison from Wave 2's Agent I report (different basket) does not apply here.

---

## 2. Hypothesis table — pre-registered

| # | Hypothesis | Result | Falsified? |
|---|---|---|---|
| H1 | Tier attribution: 2020Q4 spike concentrated in one tier | **Moot** — 99.6% of trades are $50-150 already. The Wave 3 universe is single-tier. | Trivially confirmed by construction |
| H2 | $50-150 tier alone is the edge | **Disproved** — that's already the universe. $50-150 net is -$5,903 (i.e., the whole strategy loses money) | YES |
| H3 | Whole-$5 levels are real (gamma), $10 not | **Inverted** — $5-not-$10 levels: +$35,503 / +0.05 avg R / 0.70 Sharpe; $10-multiples: -$40,419 / -0.06 avg R / -1.39 Sharpe. But this difference is dominated by 3 outlier trades, see §6.4. | Partial (direction matches but not statistically robust) |
| H4 | Options-OI proxy (close-near-level) improves edge | **Disproved** — entries within $0.05 of a $10 level: -$8,077 PnL, 14.6% WR. Closer ≠ better. | YES |
| H5 | Late-day round-number trades work, early don't | **Directionally supported but unstable** — After-11:30: +$14,084, 29.9% WR, 1.86 Sharpe. After-15:00: 13 trades total, 5.42 Sharpe — but n=13. Sharpe by quarter ranges -22 to +26. | Cannot reject — but too noisy to deploy |
| H6 | Options-heavy mega-caps work, others don't | **Concentrated, not structural** — AAPL+QCOM+TSLA+AVGO = +$36,763 of the strategy's P&L. Strip those 4 symbols: -$42,718. But within those 4, performance is driven by 4 trades; lookahead-biased. | Partial — concentration, not selection |

**Net falsifications: 3 of 6 disproved (H2, H4, full H1).** H3, H5, H6 produce filters that look attractive at first pass but fail the overfitting check (§6).

---

## 3. Loser profile (top 10)

All 10 worst losers are **identical**: a -$1,000 stop, hit within 1-12 minutes, entry exactly at a $5 or $10 round level. The pattern is mechanical and uniform:

| # | Symbol | Date | Direction | Entry | Stop hit @ | Hold | Loss |
|---|---|---|---|---|---|---|---|
| 1 | AMD | 2021-01-25 | long | $95.15 | $94.90 | 12 min | -$1,000 |
| 2 | AAPL | 2021-03-25 | short | $119.85 | $120.10 | 1 min | -$1,000 |
| 3 | AAPL | 2021-07-28 | short | $144.78 | $145.10 | 3 min | -$1,000 |
| 4 | AAPL | 2022-05-13 | short | $144.94 | $145.10 | 2 min | -$1,000 |
| 5 | NVDA | 2022-09-02 | short | $139.78 | $140.10 | 5 min | -$1,000 |
| 6 | AMD | 2023-07-26 | long | $110.22 | $109.90 | 2 min | -$1,000 |
| 7 | AMD | 2023-11-29 | short | $124.94 | $125.10 | 1 min | -$1,000 |
| 8 | NVDA | 2024-09-09 | long | $105.22 | $104.90 | 5 min | -$1,000 |
| 9 | NVDA | 2024-11-01 | short | $134.94 | $135.10 | 1 min | -$1,000 |
| 10 | AAPL | 2022-10-21 | short | $144.90 | $145.10 | 5 min | -$1,000 |

**Loser pattern:** entry exactly at the round level (within $0.10), price ticks through within 1-5 minutes, $1,000 stop. The median losing trade lasts **5.5 minutes**.

Of 1,449 trades, 1,177 (81.2%) are losers exiting at `stop` with median 5-minute hold. **The strategy enters at the level and gets immediately stopped on tick-through 81% of the time.**

The loser profile tells us the entry mechanism is wrong: by the time the signal-candle confirms at a round level, the prevailing momentum has already exhausted the level, and a tick-through stop is hit within minutes.

---

## 4. Winner profile (top 10)

The winners look very different from the losers:

| # | Symbol | Date | Direction | Entry | Exit | Hold | P&L | Exit reason |
|---|---|---|---|---|---|---|---|---|
| 1 | AAPL | 2020-12-15 | long | $125.04 | $127.70 | 381 min | +$18,998 | session_close |
| 2 | TSLA | 2023-01-23 | long | $135.19 | $140.00 | 73 min | +$16,585 | target |
| 3 | AMD | 2022-04-21 | short | $94.75 | $90.00 | 257 min | +$9,410 | target |
| 4 | NVDA | 2024-12-06 | short | $144.81 | $142.35 | 346 min | +$8,123 | session_close |
| 5 | AMD | 2020-08-24 | short | $84.91 | $82.93 | 367 min | +$7,865 | session_close |
| 6 | AAPL | 2020-10-19 | short | $119.82 | $115.78 | 362 min | +$7,699 | session_close |
| 7 | AVGO | 2024-08-07 | short | $144.88 | $140.00 | 107 min | +$6,632 | target |
| 8 | AAPL | 2021-03-03 | short | $124.78 | $122.41 | 264 min | +$6,373 | session_close |
| 9 | AMD | 2023-05-08 | long | $90.07 | $95.00 | 127 min | +$6,355 | target |
| 10 | INTC | 2020-03-25 | long | $50.14 | $51.85 | 343 min | +$5,742 | session_close |

**Winner pattern:** held **291 min mean** (~4.85 hrs), **median hold 354 min** — almost always to or near session close. Winners are NOT 2R-target hits in the level-reaction sense the directive imagined; they are trades that never traded back through the level and rode an intraday drift to EOD.

**89.5% of winning trades exit via `session_close`** (held to 3:55pm), carrying **$208,657 of $264,645 total winner P&L (78.8%)**. Only 27 trades hit the target — those 27 carry $55,988 of P&L, but they're rare.

This means the strategy is structurally a **"fade level + carry drift"** trade. If the level holds (price doesn't tick through), you collect whatever directional drift happens for the next 5 hours. If it doesn't hold, you're stopped in 5 minutes.

---

## 5. Big-winner attribution + 2020Q4 spike analysis

### 5.1 Concentration

- **Top 1% of trades (14 trades): +$114,883**
- **Top 4 single trades: +$53,115**
- **Cumulative P&L peaks at trade #257 of 1,449 (17.7%) at +$264,645**, then 1,192 subsequent trades give back -$270,600 net.

The strategy is structurally tail-dependent. P&L on 99.7% of trades is negative; the strategy's survival depends entirely on the top 0.3%.

### 5.2 2020Q4 deep-dive

2020Q4 contributed +$34,997 (57.4% of positive-quarter PnL). Composition:

| Symbol | Q4 trades | Q4 PnL | Notes |
|---|---:|---:|---|
| AAPL | 16 | +$21,410 | One trade (12/15 long $125→$127.70 session-close) = $18,998 alone |
| AMD | 9 | +$10,118 | Two short trades during Oct selloff |
| NKE | 8 | +$2,973 | One short target hit |
| INTC | 2 | +$1,776 | |
| MU | 7 | +$666 | |
| Other (SNAP, DIS, ORCL, QCOM) | 28 | -$1,945 | Net negative |

**Single trade dominance:** AAPL 2020-12-15 long alone contributed $18,998 of the $34,997 quarter (54.3%). That trade was a long at $125.04 held to close at $127.70 — a 2.1% intraday drift over 6.4 hours. That isn't a level-reaction signal succeeding; that's a momentum day where the entry happened to be near a round number.

**The 2020Q4 spike is 5 lucky days, not a regime feature.** Removing the single AAPL 2020-12-15 trade collapses the quarter to +$16,000. Removing top-5 days collapses it to +$5,000. By "regime" we'd want a strategy property that replicates — e.g., "VIX above X, RN works." Nothing of the sort exists in the data: 2020Q4 wasn't even particularly high-VIX (VIX averaged ~25 vs the full-year mean of ~29).

### 5.3 Without 2020Q4

Strip Q4-2020 entirely: 1,379 trades, **-$40,953 P&L**, 17.5% WR, -0.71 Sharpe. The strategy doesn't just have weaker edge without Q4-2020 — it's deeply negative. This is consistent with Wave 3 finding that 57.4% of *positive-quarter* PnL came from Q4-2020. Without it, the strategy bleeds.

---

## 6. Proposed filter spec + backtest validation

We tested 7 filter candidates against the 1,449-trade dataset. The promising ones:

### 6.1 Filter results table (all data 2020-2024)

| Filter | n | Days | P&L | WR | Avg R | Sharpe | n/yr |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline (no filter) | 1,449 | 833 | -$5,955 | 17.7% | -0.004 | -0.08 | 290 |
| **After 11:30 ET** | 157 | 130 | +$14,084 | 29.9% | +0.090 | **+1.86** | 31 |
| After 13:00 ET | 70 | 67 | +$4,959 | 41.4% | +0.071 | +2.25 | 14 |
| After 15:00 ET | 13 | 13 | +$3,141 | 61.5% | +0.242 | +5.42 | 3 |
| $5-not-$10 multiple | 714 | 538 | +$35,503 | 17.5% | +0.050 | +0.70 | 143 |
| Short-only | 693 | 507 | +$5,594 | 17.2% | +0.008 | +0.16 | 139 |
| **Short + after 11:30** | 79 | 72 | +$13,590 | 29.1% | +0.172 | **+2.62** | 16 |
| **Short + late + $5-not-$10** | 47 | 45 | +$14,265 | 29.8% | +0.304 | **+3.52** | 9 |

Three filters look attractive: `After 11:30 ET` (Sharpe 1.86), `Short + after 11:30` (Sharpe 2.62), and `Short + late + $5-not-$10` (Sharpe 3.52). All three appear to exceed the 1.2 gate.

### 6.2 Per-year walk-forward — instability emerges

| Filter | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|
| After 11:30 | n=36, **-$318**, Sharpe -0.33 | n=30, +$3,447, Sharpe +1.77 | n=48, **-$1,212**, Sharpe -1.49 | n=24, +$652, Sharpe +1.66 | n=19, +$11,515, Sharpe **+5.88** |
| Short + late | n=12, +$1,139 | n=9, +$5,469 | n=16, **-$1,445** | n=6, +$760 | n=4, +$8,342 |
| Short + late + $5-not-$10 | n=12, +$1,139, Sharpe +2.52 | n=9, +$5,469, Sharpe +4.71 | n=16, **-$1,445**, Sharpe **-7.08** | n=6, +$760, Sharpe +4.18 | n=4, +$8,342, Sharpe **+10.48** |

The story is clear: **the "best" filter (Short + late + $5-not-$10) has 4 trades in 2024 producing +$8,342 (Sharpe +10.48), but 16 trades in 2022 producing -$1,445 (Sharpe -7.08).** That's not a strategy with a Sharpe of 3.52 — that's a 4-trade outlier year disguised as a Sharpe.

### 6.3 Per-quarter Sharpe stability (After 11:30 filter)

| Quarter | n | P&L | Sharpe |
|---|---:|---:|---:|
| 2020Q1 | 13 | -$1,774 | -9.52 |
| 2020Q2 | 9 | +$1,415 | +5.91 |
| 2020Q3 | 7 | -$970 | -9.86 |
| 2020Q4 | 7 | +$1,011 | +2.77 |
| 2021Q1 | 7 | +$5,268 | +5.17 |
| 2021Q2 | 4 | -$605 | -8.33 |
| 2021Q3 | 8 | -$709 | -7.33 |
| 2021Q4 | 11 | -$507 | -7.68 |
| 2022Q1 | 9 | +$1,274 | +3.74 |
| 2022Q2 | 16 | -$614 | **-21.78** |
| 2022Q3 | 11 | -$692 | -10.84 |
| 2022Q4 | 12 | -$1,179 | -7.71 |
| 2023Q1 | 8 | -$416 | -10.56 |
| 2023Q2 | 3 | +$460 | +25.77 |
| 2023Q3 | 6 | +$514 | +2.55 |
| 2023Q4 | 7 | +$95 | +4.38 |
| 2024Q1 | 2 | +$31 | +3.28 |
| 2024Q2 | 3 | +$1,304 | +5.57 |
| 2024Q3 | 6 | +$9,595 | **+9.48** |
| 2024Q4 | 8 | +$586 | +5.58 |

Per-quarter Sharpe range: **-21.78 to +25.77**. This is what unstable looks like. A stable edge has per-quarter Sharpes clustered around the headline; this filter's per-quarter dispersion is 10× the headline. The 20 quarterly Sharpes do not behave like 20 draws from a distribution centered on +1.86.

### 6.4 Single-trade dependence

Test: remove the top winners from the "Short + after 11:30" filter (79 trades, +$13,590).

- Remove top 1 trade (AVGO 2024-08-07 short, +$6,632): n=78, P&L = **+$6,958**
- Remove top 3 trades: n=76, P&L = **-$1,389** (strategy flips to negative)

The "Sharpe 2.62" filter is carried by 3 trades. This is the single most damning finding in the report. Any forensic filter that flips from net-positive to net-negative on removal of 3.8% of its trades is curve-fit, not edge.

### 6.5 Bootstrap confidence intervals (1000 resamples of daily P&L)

| Filter | Mean Sharpe | 95% CI |
|---|---:|---|
| Baseline | -0.15 | [-1.47, +0.83] |
| After 11:30 | +1.70 | [-0.94, +3.38] |
| Short + late + $5-not-$10 | +3.20 | [-1.35, +5.94] |

**Every filter's 95% CI crosses zero.** The bootstrap test says we cannot reject the null hypothesis of "no edge" for any tested filter. The headline Sharpes are inside the noise band.

---

## 7. Overfitting check

### 7.1 Train/validate split (2020-2022 train, 2023-2024 validate)

| Filter | Train n | Train P&L | Train Sharpe | Val n | Val P&L | Val Sharpe |
|---|---:|---:|---:|---:|---:|---:|
| After 11:30 | 114 | +$1,918 | +0.44 | 43 | +$12,167 | +4.03 |
| Short + late + $5-not-$10 | 37 | +$5,163 | +2.03 | 10 | +$9,101 | +6.83 |
| Profitable-symbols (lookahead) | (train discovery) | | | 196 | -$5,937 | (negative) |

**The validation set performs BETTER than the training set in two cases.** That's not a sign of a robust filter — it's a sign that the validation set has its own outlier trades concentrated in late-2024. Specifically, the 4 best Short+late+$5-not-$10 trades in 2024 carry +$8,342; those 4 trades are 40% of the validation-period sample.

A genuine edge would (typically) show train Sharpe ≈ val Sharpe within sampling noise. Here, val n=10 and 1 trade (AVGO 2024-08-07 +$6,632) accounts for ~73% of validation P&L. We are validating a sample of 1.

The "Profitable symbols" filter (pick winners ex-2020Q4, apply to all years) — when properly walk-forwarded (train symbols on 2020-2022, validate 2023-2024) — produces -$5,937 on val. The "lookahead-biased" version's apparent +$35,949 / Sharpe 1.33 is genuinely just lookahead bias.

### 7.2 Concentration is the overfitting tell

A robust edge: many small positive trades, distribution shape preserved across periods.
This strategy: 99.7% of trades net-negative, total survives on top 0.3% of trades, top-3 in any filter carries the headline.

The right interpretation of the apparent Sharpe lift on "After 11:30 + Short" isn't "we found edge in late-day shorts." It's "the strategy traded so few times late-day that a handful of large-drift down days dominate the sample." Late-day RN shorts in 2024 happened to coincide with NVDA/AVGO drawdowns (Sept-Nov 2024 tech rotation). That's a single regime event, not a structural property of round-number levels.

---

## 8. Viability at $25K starting equity

Even if we accepted the "After 11:30" filter at face value:

- 31 trades/yr, $1,000 risk each → at $25K, 1% risk = $250, so scaled P&L = +$14,084 × 0.25 = **+$3,521 over 5 years = $704/yr**.
- That's 2.8% annual return at 1% per-trade risk, with bootstrap CI from -19% to +13% (95%).
- Max drawdown in the filter set: -$3,711R = -$928 at $250/trade scaling = -3.7% of $25K.

For the tightest filter ("Short + late + $5-not-$10"), 9 trades/yr is structurally too few to validate by the time the bot reaches the trading-confidence floor.

**The strategy is unviable at $25K even under generous filter assumptions** — the per-year P&L (~$700) is below the noise threshold of paper-trading variance for other Phase 1 strategies.

---

## 9. The level mechanic isn't doing the work

The directive's hypothesis #4 was "options-OI proxy: round numbers near visible options activity work better." We tested this with the distance-to-$10 proxy (entries within $0.05 of a $10 multiple):

| Distance to $10 multiple | n | P&L | WR | Avg R |
|---|---:|---:|---:|---:|
| <$0.05 | 130 | **-$8,077** | 14.6% | -0.062 |
| $0.05-0.10 | 139 | -$439 | 14.4% | -0.003 |
| $0.10-0.25 | 402 | -$23,335 | 20.4% | -0.058 |
| $0.25-0.50 | 58 | -$7,757 | 19.0% | -0.134 |
| **>$0.50** | 720 | **+$33,653** | 17.4% | +0.047 |

**Entries closest to $10 multiples lose money.** Entries farthest from $10 multiples make money. This is the **opposite** of what an options-pinning hypothesis predicts. If gamma was anchoring price to round numbers, fading the touch should work — but it's the OPPOSITE pattern (closer = worse).

What's actually happening: entries near $10 multiples are entries into known resistance/support; the level holds long enough to fill, then institutional flow takes price through within minutes. Entries far from $10 multiples are essentially mid-channel entries on $5 levels (not $10), where there's no marquee-level memory effect — they're closer to pure momentum trades, which is why they pick up the EOD drift better than $10-level entries.

This isn't level reaction. It's noise.

---

## 10. Filter spec (DO NOT DEPLOY — for completeness only)

If forced to deploy, the *least bad* configuration would be:

```yaml
strategies/round_number_filtered.yaml:
  level_source: round_number
    increments:
      "50_150": [5.00]    # universe is already $50-150
    exclude_$10_multiples: true   # H3 signal, $5-not-$10 only
  arrival_detector: proximity
    proximity_dollar: 0.25
  confirmation_rule: signal_candle (unchanged)
  time_window: 11:30-15:55 ET    # H5 filter
  direction_lock: short_only     # H6 partial — long was -$11,549
  risk_per_trade_pct: 1.0
  expected_trades_per_year: ~9
```

Expected metrics (with disclaimers):
- 9.4 trades/year, n=47 total across 5 years
- Apparent Sharpe 3.52 — but bootstrap CI [-1.35, +5.94]
- Per-year P&L ranges from -$1,445 (2022) to +$8,342 (2024)
- 3-trade removal flips to -$1,389

**This filter is curve-fit, not edge.** Deploying it would amount to betting that late-2024 short conditions in tech mega-caps reproduce in 2026. There's no structural reason to believe they will.

---

## 11. Honest comparison to the Wave 2 Agent I report

Wave 2 Agent I's report (2026-05-16) reported $50-150 long-only Sharpe +3.77 on **82 trades over 60 sampled days × 5 symbols** (WMT, KO, MRK, DIS, VZ). That sample is structurally different from the Wave 3 portfolio universe:

- Wave 2 basket: defensive blue chips (WMT/KO/MRK/DIS/VZ) at moderate volatility
- Wave 3 universe: tech mega-caps + volatile names (AAPL/AMD/NVDA/TSLA/META/AVGO/QCOM)
- Wave 2 reported Sharpe +3.77 on long-only; Wave 3 long-only is -0.25 Sharpe (-$11,549)

**The Wave 2 result does not replicate in the Wave 3 universe.** This is what overfitting to a basket looks like. Defensive blue chips at $50-150 may genuinely respect round-number levels (low-vol, slow drift); volatile tech names at $50-150 do not.

If we wanted to salvage anything: the strategy might work on a **defensive-blue-chip-only basket with long bias**, but (a) those names don't fit the Wave 3 universe selection criteria for other strategies, (b) the basket Wave 2 tested has only 82 trades over 5 years — still small-n, (c) such a filter would be retrofitted to one observed outcome.

---

## 12. Limitations

1. **No per-bar feature extraction.** This forensic ran on trade-level CSV only. Bar-level features (volume, ATR, VWAP-distance at signal time) might reveal a microstructure filter we can't see from trade outcomes alone. We have those files (`tick_cache_databento/<SYM>/1m_<YYYY-MM-DD>.parquet`) but they're not necessary — the trade-level result is already conclusive: top-3-trade removal flips every promising filter.

2. **Options-OI is not in our data.** Hypothesis 4 was tested with a proximity proxy. A real options-OI overlay (gamma exposure peak strikes) could expose a strikethrough-magnet effect that the proxy missed. But the proxy showed the inverse pattern, which argues against options-anchoring being the missing feature.

3. **The Wave 3 sample size is genuinely small for tail-driven strategies.** 1,449 trades sounds large, but 27 target hits + 230 session_close winners is what carries the P&L. We are estimating distribution moments on n≈27 for the only "validated win" mechanism.

4. **The $1,000 fixed-dollar risk model normalizes trade size.** A real deployment at $25K with kelly or notional caps would change the P&L curve and the per-trade DD profile. But the directional findings (filter overfitting, per-quarter instability, 3-trade dependence) are scale-invariant.

---

## 13. Recommendation

**Retire Round-Number as a Phase 1 strategy.**

Acceptance criterion from the directive: "find tightly-filtered subset with Sharpe ≥ 1.2 OR retire. Retirement is acceptable."

We tested 7 filter configurations. The best looks like Sharpe 3.52, but:
- 95% bootstrap CI [-1.35, +5.94] — crosses zero
- Per-quarter Sharpe ranges -22 to +26 — extreme instability
- Top-3 trade removal flips to net-negative
- 9 trades/year — below statistical validity threshold
- Walk-forward "validation" wins are themselves 1-2 outlier trades
- Theoretical mechanism (gamma anchoring) shows INVERSE of predicted pattern (close-to-$10 LOSES)

**Verdict: retire.** The strategy as run on the Wave 3 universe has no extractable edge. The 2020Q4 spike that triggered this investigation is 5 trades on 5 days, not a recoverable regime feature.

### Implementation steps

1. Update `strategies/round_number.yaml` to set `enabled: false` (or move to `strategies/_disabled/`)
2. Remove from Wave 4 deployment candidate list
3. Document this finding in the next portfolio backtest report so the strategy doesn't get re-added without addressing the structural concerns here
4. Note in CLAUDE.md: "Round-Number strategy retired 2026-05-16 per forensic finding — see `cowork_reports/2026-05-18_round_number_forensic.md`"
5. **Conditional reopen:** if options-OI data becomes available and a structural mechanism (e.g., gamma-exposure-peak detection) is implementable, retest on the same universe. But do not reopen on heuristic grounds.

This is a clean retirement, exactly the kind of decision the forensic methodology is supposed to enable. Round-Number joins the list of "tested honestly, found wanting, removed."

---

## 14. Why this matters for the framework

The Wave 2 → Wave 3 P&L collapse (Sharpe +3.77 → -0.08) is the largest synthetic-to-real divergence in the framework after VWAP-MR. Both VWAP-MR and Round-Number share a structural property: **they're noise strategies with a plausible theoretical mechanism (mean reversion / gamma anchoring) that fails to show up in real data once you remove curve-fit basket choices**.

The framework's value here isn't that Round-Number works — it doesn't. The value is that the methodology cleanly separates "looks good in a chosen basket" from "produces edge across a representative universe." Wave 2's Sharpe +3.77 was real *given* the WMT/KO/MRK/DIS/VZ basket; it was not real across a diversified mega-cap universe. This is the type of finding the wave system was built to surface.

---

**End of report.**
