# Combined Portfolio Backtest — Squeeze + Framework + Tiered Sizing

**Date:** 2026-05-17
**Author:** Cowork (Perplexity)
**For:** CC + Manny
**Trigger:** Manny: "Can this pair with our squeeze strategy? Can we actually run a backtest that deploys squeeze, accounts for growth and sizing across this entire 5 year span?"
**Augments:** `DIRECTIVE_2026-05-17_FORENSIC_RESPONSE.md`, `DIRECTIVE_2026-05-17_SIZING_SCHEDULE.md`

---

## TL;DR

Yes — this is the right question and the right deployment model. **Squeeze (going to real-money 6/15) + framework strategies (going to paper Wave 4) will share an account in production**, so the right backtest models them as one unified portfolio with tiered sizing across 2020-2024.

Three challenges to solve:
1. **Squeeze backtest harness** — squeeze is currently tightly coupled to live execution paths. Needs a framework-compatible plugin or a parallel backtest-only harness.
2. **Disjoint universes** — squeeze targets small-cap gappers; framework targets $10-$300 mid/large caps. Likely zero ticker overlap, which means real interaction effects are minimal but the **shared equity pool** is the actual portfolio question.
3. **Tiered sizing** — `TieredSizer` doesn't exist yet (pending Wave 5 P1). Either build it now as part of this work, or simulate tier behavior in the backtest as a separate computation.

The valuable output: **combined annualized return, combined max drawdown, combined tier progression timeline, regime correlation between strategies, true portfolio Sharpe.** All things the per-strategy backtests can't answer.

---

## 1. Why this matters

The original Wave 4 framing assumed "framework strategies in paper, squeeze in real-money, separate paper accounts, separate everything." That's correct for the *deployment topology* but wrong for the *capital allocation reality*.

In actual production:
- Squeeze contributes equity growth to the same account framework strategies will eventually run on
- Tier advancement triggers off combined equity (per the sizing-schedule directive)
- Real-money decisions on framework strategies depend on whether they help or hurt the combined portfolio
- 6/15 squeeze cutover starts the equity-growth clock; framework strategies join the same account whenever they pass paper validation (~mid-August)

**The right validation question is: what does combined performance look like across 5 years of historical data with the proposed tier ladder?**

This answers questions the per-strategy backtests can't:

- If squeeze drawdown coincides with framework strategy strength (or vice versa), portfolio drawdown is bounded better than any individual.
- If both strategies drawdown together (correlated regimes), portfolio risk is worse than the headline numbers suggest.
- Tier 7 ($2500/signal) timeline shifts based on combined growth rate.
- Strategy retirement decisions could change — a strategy that's marginal alone might be a strong diversifier in the combined view.

---

## 2. Three challenges to solve

### 2.1 Squeeze backtest harness

**Current state:** Squeeze runs in `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `engine wb_bot.py`, etc. — tightly coupled to live IBKR/Alpaca execution paths. Squeeze does NOT have a clean backtest harness analogous to the framework's `backtest/portfolio_backtest.py`.

**Two paths forward:**

**Path A — Framework-compatible squeeze plugin** (cleaner, more work)

Wrap squeeze's signal logic into a `LevelSourceProtocol` and plug it into the framework backtest engine. The framework already supports this architecture; squeeze becomes one more strategy in the registry alongside PDH-Fade, ORB, etc.

- Effort: ~1 day CC work
- Long-term value: high — squeeze migrates to framework eventually anyway (per prior directive, post-6/15 work)
- Validation cost: medium — need to confirm squeeze backtest output matches squeeze's actual 2024-2026 live behavior

**Path B — Standalone squeeze backtest harness** (faster, technical debt)

Build a separate backtest engine that replays squeeze logic against historical data, outputs per-trade CSV in the same schema as framework strategies. Then merge CSVs at portfolio analysis time.

- Effort: ~2-3 hours CC work
- Long-term value: low — duplicate code path, maintenance burden
- Validation cost: low — just compare squeeze CSV output against framework CSV schema

**Recommendation: Path A.** The work is already on the post-6/15 roadmap (squeeze migration to framework). Doing it now gets us:
- Combined portfolio backtest immediately
- Squeeze migration completed earlier than scheduled
- One unified backtest engine, not two

### 2.2 Disjoint universes

**Squeeze universe:** small-cap gappers, $2-30 price band, premarket gap >5%, RVOL >2×, float <30M, scanner-driven daily.

**Framework universe:** $10-$300 (post Manny 5/17 expansion), liquidity-filtered, persistent ~36 symbols mid/large cap.

**Overlap:** Likely zero on most days. Squeeze's small-cap gappers and framework's mid/large caps don't cross. There may be rare days where a $10-30 stock qualifies for both universes (squeeze on the gap-up + framework on the level-reaction), but those are edge cases.

**Implication:** The conflict resolution rule (per-symbol-per-day lock) almost never fires across the squeeze/framework boundary. The two strategies are effectively independent at the trade level.

**But the portfolio-level interaction is real:**
- Shared equity pool means squeeze losses reduce framework's available risk budget at the next tier
- Tier advancement requires combined equity milestones
- Correlated drawdown periods (e.g., March 2020 COVID, May 2022 mega-cap selloff) may hit both strategies simultaneously even if they trade different tickers

**Backtest spec:** run both universes in parallel through the same equity simulator. Each trade adjusts shared equity. Tier rules apply to combined equity. No need to handle conflict resolution across the universe boundary because empirically it almost never triggers.

### 2.3 Tiered sizing implementation

**Current state:** `TieredSizer` doesn't exist. Wave 5 P1 work specifies fixing `HalfKellySizer`; the tier system is on top of that.

**Two paths forward:**

**Path A — Build TieredSizer as part of this work** (cleaner)

Implement the 9-tier ladder per `DIRECTIVE_2026-05-17_SIZING_SCHEDULE.md` directly into `framework/sizing.py`. Both the backtest and live deployment use the same code path.

- Effort: ~half a day CC work
- Validates the tier rules empirically before live deployment
- Surfaces edge cases (e.g., what if equity straddles a tier threshold mid-session?)

**Path B — Simulate tier behavior in the backtest harness** (faster)

Compute equity progression as a post-processing step on the trade CSVs. Tier transitions inferred from running equity. No live code changes required for the backtest.

- Effort: ~2 hours CC work  
- Doesn't validate live tier code (which we'd build later)
- Simpler for backtest-only purposes

**Recommendation: Path A.** Same reasoning as squeeze migration — TieredSizer is on the roadmap anyway. Building it now gives us live-deployable code AND the backtest in one workstream.

---

## 3. The proposed combined backtest

### 3.1 Universe

- **Squeeze universe**: reconstructed from historical small-cap gappers per its existing scanner logic. Constraint: requires premarket data + float data for arbitrary historical small-caps. Confirm we have this in `tick_cache_databento/` or fetch what's missing from Databento.
- **Framework universe**: existing 36 mega/large-cap symbols, $10-$300 per Manny's expansion.

### 3.2 Strategies enabled

| Strategy | Source |
|---|---|
| Squeeze (existing live config) | wrapped as framework plugin per Path A above |
| PDH-Fade-filtered (F1+abandon@10) | from forensic response |
| ORB-aligned ($300+ tier) | from forensic response |
| PDH-Breakout-F4 (thick filter) | from forensic response |

(VWAP-MR and Round-Number retired per forensic response — not in combined backtest.)

### 3.3 Sizing

- Initial equity: **$25,000**
- Tier 1 starting: **$300/signal**
- Tier ladder: 9 tiers per sizing schedule directive
- Advancement/retreat rules: per sizing schedule directive
- Auto-advancement: enabled in backtest (this is the whole point — see how fast the account scales)

### 3.4 Concurrency rules

- Per-symbol-per-day lock: yes (existing framework rule)
- Cross-universe: not applicable (disjoint universes)
- Multi-strategy fires same session: each strategy contributes to that session's drawn risk budget
- Combined session risk cap: 6% (slightly higher than 3.6% to allow squeeze + 3 framework strategies all firing same day)

### 3.5 Period

**2020-01-02 → 2024-12-31** (5 years, same as framework Wave 3).

### 3.6 Output deliverables

The combined backtest report needs to include:

1. **Combined equity curve** — single line, $25K start to final equity
2. **Per-strategy attribution** — how much of total P&L came from each strategy
3. **Tier progression timeline** — which year/quarter each tier was reached
4. **Combined drawdown analysis** — worst drawdowns by depth and duration
5. **Regime correlation matrix** — squeeze vs each framework strategy by quarter
6. **Comparative table** — combined vs squeeze-alone vs framework-alone vs any single strategy
7. **What-if scenarios:**
   - Squeeze-alone (no framework) — what does the account look like?
   - Framework-alone (no squeeze) — what does the account look like?
   - Combined — does total P&L exceed sum of parts? Does combined drawdown bound better?
8. **Tier-7 timeline** — when does the combined account reach $250K (= $2500/signal)? With and without framework participation?
9. **Worst-case scenarios** — what happens if 2022 happens again? If COVID March 2020 happens again?
10. **Validation gates** — does the combined portfolio still pass acceptance (Sharpe ≥ 1.5, drawdown ≤ 25%, profit factor ≥ 1.4)?

---

## 4. Engineering work breakdown

CC spawns four parallel agents:

### Agent 1 — Squeeze framework migration
Wrap squeeze logic into framework-compatible plugins:
- `framework/level_sources/squeeze.py` (new — squeeze's signal extraction)
- `framework/confirmations/squeeze_breakout.py` (existing breakout pattern, parameterized for squeeze)
- `strategies/squeeze.yaml` (new spec)
- Validation: backtest squeeze on its existing tick_cache; compare output to squeeze's known 2024-2026 live performance to confirm parity

Acceptance: backtest of squeeze in 2024-2026 reproduces known live behavior within ~10%.

Report: `cowork_reports/2026-05-XX_squeeze_framework_migration.md`

### Agent 2 — TieredSizer build
Implement the 9-tier ladder in `framework/sizing.py`:
- New `TieredSizer(SizerProtocol)` class
- `framework/sizing_tiers.yaml` config file
- Advancement/retreat rules per sizing schedule directive
- Tests: synthetic equity curves driving tier transitions

Acceptance: unit tests pass for all advancement/retreat scenarios + integration test in a small backtest run.

Report: `cowork_reports/2026-05-XX_tiered_sizer_build.md`

### Agent 3 — Squeeze historical data validation
Confirm squeeze can run against 2020-2024 history:
- Query what data is in `tick_cache_databento/` for each year
- For squeeze candidates needing premarket gap + RVOL data, identify gaps
- Fetch missing data from Databento as needed
- Document the squeeze universe size per day across 2020-2024

Acceptance: report shows squeeze can run against any session 2020-2024 with no missing data warnings.

Report: `cowork_reports/2026-05-XX_squeeze_historical_data_audit.md`

### Agent 4 — Combined portfolio backtest harness
Build the unified backtest:
- `backtest/combined_portfolio_backtest.py`
- Consumes Agent 1's squeeze plugin + framework strategies
- Uses Agent 2's TieredSizer
- Single shared equity pool
- Per-day, per-strategy contribution tracking
- Output: trade CSV + equity curve parquet + summary JSON

Run after Agents 1-3 complete. Generate the combined backtest report per §3.6 above.

Report: `cowork_reports/2026-05-XX_combined_portfolio_backtest.md`

---

## 5. What we expect to find (informed prediction)

### 5.1 Likely positive findings

- **Combined annualized return ≥ best individual.** The forensic response projected $250-$300K over 5y on framework alone. Adding squeeze (which is real-money-bound for 6/15) likely adds another $100-200K based on squeeze's 2024-2026 live performance extrapolated.
- **Tier 7 timeline accelerated.** From ~Year 4-5 (framework alone) to ~Year 3 (combined).
- **Drawdown smoothing during regime mismatches.** When mega-cap framework strategies suffer (e.g., 2022), small-cap squeeze may compensate.
- **Combined Sharpe likely exceeds individuals.** Two uncorrelated edge streams compound efficiently.

### 5.2 Likely negative findings

- **Correlated drawdowns in March 2020 / late 2022.** Both strategies probably suffered in COVID and bear markets. The combined drawdown number may not be much better than either alone.
- **Squeeze contribution may be smaller than expected.** Squeeze's edge depends on small-cap retail-mania regimes. If 2020-2022 were strong and 2023-2024 weaker for squeeze, combined backtest may show a tilted contribution.
- **Tier 7 unrealistic if backtests overstate live performance.** Both squeeze and framework backtests have ~85-90% fidelity to live execution. A 47% annualized return in backtest may translate to 35-40% live, pushing Tier 7 timeline back to Year 5-6.

### 5.3 The number that matters most

**Combined max drawdown.** If it's <25%, the combined portfolio is viable at $25K. If it's >40%, the account doesn't survive long enough to reach the upper tiers. The forensic response projected -10% to -18% portfolio drawdown for framework alone; adding squeeze should help (different universe) or hurt (correlated regime). The combined backtest answers this empirically.

---

## 6. What this directive is NOT proposing

1. **Not** changing the 6/15 squeeze real-money cutover. Squeeze still goes live on schedule with its current configuration.
2. **Not** changing the Wave 4 paper deployment plan for framework strategies.
3. **Not** combining squeeze + framework into a single live process before paper validation completes.
4. **Not** modifying any squeeze strategy logic. The migration is a re-wrapping, not a redesign.

---

## 7. Decisions Manny needs to make

This adds one more decision to the prior 7:

**Decision 8:** Approve the combined portfolio backtest workstream?
- Yes = CC spawns Agents 1-4, delivers combined backtest report alongside framework Wave 4 readiness work
- No = Wave 4 deployment proceeds without combined backtest validation (squeeze + framework remain separate planning concerns)

**Cowork recommendation: Yes.** The combined backtest is the single most important validation for real-money deployment of framework strategies post-paper. Without it, we're guessing at how framework adds to an account already running squeeze. With it, we have empirical answer for tier timeline, combined drawdown, and Tier-7-realistic-arrival.

The work parallelizes with the existing forensic-response execution sequence. Agent 1 (squeeze migration) and Agent 2 (TieredSizer) need to happen anyway — this just sequences them earlier.

---

## 8. Sequencing with existing directives

If Manny approves all 8 decisions (5 forensic + 2 sizing + this combined backtest):

**Wave A — Pre-Wave-4 prep (CC parallel agents):**
1. One-line `lock_collisions.csv` fix
2. Implement release-on-stop conflict rule
3. Subprocess Nautilus revalidation of PDH-Fade abandon-rule
4. Wire 3 filtered framework YAML specs
5. Retire VWAP-MR + Round-Number YAMLs

**Wave B — Combined portfolio prep (parallel with Wave A):**
6. Squeeze framework migration (Agent 1)
7. TieredSizer build (Agent 2)
8. Squeeze historical data audit (Agent 3)

**Wave C — Combined portfolio validation (after A+B):**
9. Combined portfolio backtest (Agent 4)
10. Cowork synthesis: combined report → reviewable answer to Manny's question

**Wave D — Wave 4 paper deployment:**
11. Paper deploy framework strategies at Tier 1 $300/signal
12. 60-day paper validation
13. Real-money decision based on paper data + combined backtest evidence

Wave A and Wave B run simultaneously. Wave C blocks on both. Wave D blocks on C.

---

## 9. Reports CC owes

| When | Report |
|---|---|
| Per Wave A | All 5 prep tasks per forensic response directive |
| Wave B Agent 1 | `2026-05-XX_squeeze_framework_migration.md` |
| Wave B Agent 2 | `2026-05-XX_tiered_sizer_build.md` |
| Wave B Agent 3 | `2026-05-XX_squeeze_historical_data_audit.md` |
| Wave C Agent 4 | `2026-05-XX_combined_portfolio_backtest.md` |
| After Wave C | Cowork synthesis combining the combined backtest insights with the forensic-response decisions |

---

## 10. Tone

This is exactly the question that should have been asked sooner. The framework was being validated in isolation; squeeze was being deployed in isolation; the actual production reality of "they share an account" wasn't being tested.

The answer is yes, it can pair with squeeze. The backtest gives us empirical answer to combined drawdown, tier progression, and whether the diversification benefit is real or imagined. The work parallelizes with the existing forensic-response execution sequence and produces lasting value (squeeze migrates to framework earlier than originally scheduled; TieredSizer becomes live-deployable).

Right question, right time, right tools available. CC builds it.

---

## 11. Files referenced

- `DIRECTIVE_2026-05-17_FORENSIC_RESPONSE.md` (3-strategy framework deployment plan)
- `DIRECTIVE_2026-05-17_SIZING_SCHEDULE.md` (9-tier ladder)
- `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `engine wb_bot.py` (existing squeeze code)
- `squeeze_detector_v2.py` (squeeze signal logic to wrap)
- `backtest/portfolio_backtest.py` (existing framework backtest)
- `framework/sizing.py` (gains TieredSizer)
- `framework/sizing_tiers.yaml` (new config)
- `tick_cache_databento/` (data source — needs audit for squeeze universe coverage)
- `backtest/combined_portfolio_backtest.py` (new harness)
