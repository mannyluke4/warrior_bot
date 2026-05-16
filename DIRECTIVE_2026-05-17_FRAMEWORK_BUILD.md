# Healthy Fluctuation Framework — Build Directive

**Date:** 2026-05-17
**Author:** Cowork (Perplexity)
**For:** CC
**Status:** Approved design (`DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md`) → build initiated
**Parallel work:** Monday production checklist runs separately. This directive does not interfere with squeeze 6/15 go-live or any current paper strategies.

---

## TL;DR

Build the level-reaction framework + Phase 1 strategies in parallel agents. Backtest with NautilusTrader + Databento. No changes to existing live stack until Phase 1 strategies clear validation gates (backtest Sharpe ≥ 1.5, then 30 paper sessions).

CC spawns the agents below. Each works independently. Outputs land as code in `warrior_bot/framework/` and `warrior_bot/strategies/`. Sync points listed below.

---

## 0. Context — why we're building this

This directive is the result of a strategic reframe spanning three weeks of paper-trading data, four forensic investigations, and five research workstreams. Reading this section is **required** before starting any build work. Without it, the build decisions below will look arbitrary; with it, every choice is grounded in evidence.

### 0.1 What we tried that didn't work

**The Wave Breakout (WB) strategy attempted to encode discretionary intuition into a mechanical bot.** Manny had been profitable paper-trading manually using a feel-based methodology — watch the most-active small-caps, identify visual wave structures on 1m bars, strike on MACD flips or resistance reactions, hold through unrealized drawdown when the setup still looked valid. The −$200K → +$70K story is canonical: Manny held a position through a drawdown the bot would have stopped out twice over because he could read the tape and feel the reversal coming.

We tried to port that into code. WB was built around momentum-wave detection on 1m bars, scored with `vol_mult`, `vol_extra`, MACD, VWAP relationship, and HOD distance. It ran on a small-cap-gapper universe (~30 symbols from the squeeze scanner). It produced 19 P&L fills across 5 days (May 11-15) and 5 "winners" across the prior weeks.

**The forensic week (5/17) destroyed the strategy.** Four investigations, all on existing tick_cache + log data:

1. **Squeeze re-entry forensic:** N=2 re-entry fills lost 2/2 (directionally supports a re-entry cap, low confidence).
2. **WB loser behavioral profile:** Winners' entry-bar volume was 0.025× prior 25-min mean (7-100 shares). Losers' was 0.68× (702 shares). EH losers: 2.72×. **Winners entered into volume vacuums; losers entered into populated bars that immediately reversed.** This *inverts* the dead-tape gate we shipped Saturday morning.
3. **Stop-hit reverse-time analysis:** 15 of 18 stop-hit losers (83%) went direct entry→stop without ever hitting +0.3R. Faster exits would save at most $2,295 of $15,693 lost. **Exits aren't the problem. Entries are.**
4. **WB winner template:** Of 9 candidate features pre-registered in the directive, only `score≥8` (already in place) appears in ≥4 of 5 winners. **The 5 "winners" are 5 qualitatively different events** — textbook reclaim (FATN), EH momentum hold (ATRA 5/8), slow-cook box-break (SST), manual injection (MEI), dead-tape misfire (ATRA 5/15). Not five instances of one pattern.

Stripped of FCHL (infrastructure orphan, $13K loss), MEI (manual injection by an agent during a Databento outage), and ODYS overnights (eliminated by force-exit ship): **WB had 19% win rate, −$9,131 net over 16 P&L fills.** And the *only* fresh winner (ATRA 5/15 +$1,160) was a setup the dead-tape gate we shipped Saturday would have vetoed.

### 0.2 What we learned (the categorical insight)

WB wasn't badly calibrated. It was a **category mismatch**. WB attempted to encode discretionary intuition as a mechanical bot strategy. That premise was wrong. The forensic "no template exists" finding was structural — the human source isn't running a template either. The five "winners" looked heterogeneous because Manny's actual trading is heterogeneous.

Manny named this directly: *"What I do isn't exactly codable or repeatable. It's based highly on intuition... The bot would have stopped out. It can't 'feel' the chart out... I hope we can learn from this and work the bot out to perform best as a bot, not like a human."*

### 0.3 The reframe — bot-shaped, not human-port

The bot should not try to be Manny. It should do what bots do well, and Manny does what humans do well — separately. **Division of labor, not overlap.**

Manny then articulated the actual project goal — clearer than anything we'd had before: **"Prices fluctuate. Our goal is to find the healthiest fluctuation and take advantage of that healthy movement."**

This is the north star. WB, box, squeeze, Volume Profile — all of them are *methodologies* for finding healthy fluctuations. The bot's job is to find them and execute on them with the speed, breadth, and consistency humans can't match.

Five objective properties define a "healthy fluctuation" (all detectable by a bot):
1. Real participation — volume confirms activity, not one-print spikes
2. Predictable level structure — moves respect identifiable levels
3. Direction-able — reversal-or-continuation pattern at the level
4. Risk-definable — clear failure point (stop)
5. Edge-to-edge potential — measurable target

Every strategy in this framework is one instance of:
```
strategy = (level_source, arrival_detector, confirmation_rule, stop_rule, target_rule)
```

Squeeze already operates within this framework — that's why it works. The Phase 1 strategies (ORB, VWAP, PDH/PDL, Round Number) are all level-reaction variants. Phase 2 adds Volume Profile and Anchored VWAP. Each is a YAML config plugging into the same primitive.

### 0.4 The video that informed Phase 2

Manny shared a [YouTube video](https://youtu.be/XMNUAJvReg0) from the Trading Notes channel — Volume Profile / Auction Market Theory methodology. The Signal Candle Model (LVN sweep → HVN edge reaction → doji/hammer/star with volume confirmation → edge-to-edge target) is the cleanest mechanical analog to what Manny actually does. Full extraction at `trading_notes_volume_profile_strategy.md`.

This isn't *the* methodology we're encoding — Manny does many things, not just VP. But it's the methodology that fits the framework most cleanly and serves as the Phase 2 reference implementation.

### 0.5 The research that grounded this build

Five parallel research workstreams produced ~25,000 words of technical foundation. All saved to `/home/user/workspace/`:

1. **`research_vp_market_profile.md`** (954 lines) — Mathematical definitions of POC, VAH, VAL, HVN, LVN. Steidlmayer's original CBOT bidirectional expansion algorithm. TPO vs Volume Profile tradeoffs. Profile shape classification (D, P, B, I). 80% Rule statistical backing (78-82% hit rate per MarketDelta/ShadowTrader). Exact candlestick pattern criteria (doji <10% body, hammer 2:1 lower shadow, shooting star with body in lower 25% of range). Auction Market Theory grounding. VWAP-as-proxy evidence (150K Bonferroni-significant results, 0.89pp edge per EdgeTools study). Caginalp & Laurent (2006) peer-reviewed candlestick study (36-sigma significance). L2/DOM integration patterns.

2. **`research_universe_selection.md`** (555 lines) — Why "higher prices fluctuate better" has structural backing: adverse selection compensation, HFT depth competition, institutional participation, fragmentation effects, options-driven hedging. LULD halt mechanics (±5% Tier-1, ±10% Tier-2, ±20% sub-$3, ±75% sub-$0.75). ADV thresholds (10% participation rate institutional benchmark; $10M ADV minimum). Float sweet spot (20M-200M for $50-100K notional). Sector exclusions analysis (biotech FDA binary events, energy multi-input noise, shipping rate noise). Time-of-day effects (10:00-11:30 + 13:30-15:50 historically best windows). VIX regime overlay (16-28 optimal).

3. **`research_multi_strategy_architecture.md`** (734 lines) — LEAN's five-module pipeline (Universe → Alpha → Portfolio → Risk → Execution). Plugin/composable strategy design as YAML configs, not code branches. A/B testing infrastructure (trade-level `strategy_id` tagging, sub-account separation, 50-100 trades per variant minimum, permutation tests). Per-strategy kill switches. Half-Kelly sizing as industry standard. Net aggregation with intent-level logging for concurrency. Case studies (LEAN, pysystemtrade, Citadel/Millennium pods, Renaissance, Two Sigma, Bridgewater).

4. **`research_candidate_strategies.md`** (517 lines) — 10 candidate strategies mapped to the framework. Ranked by edge evidence × bot-shape × engineering complexity. Top picks for Phase 1: ORB (Zarattini et al. 2024 SSRN paper, Sharpe 2.81, 7,000 stocks), VWAP (regime-gated), PDH/PDL, Round Number. Phase 2: Volume Profile, Anchored VWAP. Deferred: Multi-day swing, Box, Mean Reversion (regime detection failures), L2 Order Book Imbalance as standalone (edge marginal at >1-second execution).

5. **`research_backtest_infrastructure.md`** (629 lines) — NautilusTrader for production backtest (Rust core, 200K bars in 3s, native L2 replay, native Databento adapter, multi-strategy accounting). vectorbt for research/parameter sweeps. Avoid Backtrader/Zipline/LEAN. Databento Standard ($199/mo) provides trade ticks needed for accurate VP reconstruction. Fidelity ceiling 85-90% for 2-30 minute hold strategies. Multi-timeframe replay requirements. Realistic fill modeling (5% of bar volume cap, queue position uncertainty discount 20-40%).

### 0.6 What changed because of Manny's review (5/17)

The initial design proposed: $20-200 universe, pre-imposed sector exclusions, narrow time windows (10:00-11:30 + 13:30-15:50), VIX regime overlay enabled by default. Manny pushed back: **data-driven everything**.

Final locked decisions:
- Universe: **$10-$300** for backtest, narrow from data
- Sector exclusions: **None pre-imposed**, data-driven
- Time windows: **Full RTH 09:30-15:55**, narrow from data
- VIX regime: **Build hooks, default OFF**, validate from backtest
- Capital allocation: **Data-driven**, not pre-committed
- Phase 1 portfolio: ORB + VWAP + PDH/PDL + Round Number ✓
- Phase 2 portfolio: Volume Profile + Anchored VWAP ✓
- NautilusTrader: **Backtest ONLY** (not replacing IBKR, not replacing live stack — clarified to prevent rework)
- Databento Standard plan ($199/mo)
- Validation gates: Sharpe ≥ 1.5 backtest, 30 paper sessions, 3-tier real-money rollout

### 0.7 What stays unchanged from existing work

**Production live stack is untouched:**
- `bot_v3_hybrid.py` (Setup A main bot, squeeze)
- `bot_alpaca_subbot.py` (Setup A sub-bot, WB — being retired but still runs)
- `engine wb_bot.py`, `engine squeeze_bot.py` (Setup B engine)
- `squeeze_detector_v2.py` (working squeeze detector)
- `l2_signals.py`, `l2_entry.py`, `ibkr_feed.py` (Saturday's L2 work)
- `wb_persistence.py`, `wb_intraday_adder.py` (Saturday's persistence + adder)
- `force_exit.py`, `tape_quality.py`, `engine_bot_common.py` (Saturday's P0 ships)
- Data pipeline (Databento Live, Alpaca, IBKR Gateway)
- `data_engine.py` (Setup B engine data infrastructure)
- All scanner code, watchlist code, position management code

**6/15 squeeze-only real-money cutover** is the production milestone. This framework build does not affect it.

**WB retires** post-go-live regardless of framework build status. The new framework is its *successor*, not an extension.

### 0.8 Pacing context

Manny clarified early in 5/17 evening: *"CC can do the work of 100 skilled men's 1 week load in under an hour. Why wait a whole month when we can build it now and use the next 30 days to test and refine?"*

I had been falling into human-time framing repeatedly. The corrective: **plan rigorously, build in parallel, test exhaustively.** The build wall-clock is bounded by the slowest agent in each wave + Manny's review at sync points, not by sequential build time. Most agents below complete in <1 hour of CC work.

The constraints that ARE wall-clock-bound:
- Backtest data subscription (Databento Standard — Manny obtains, ~minutes-to-hours)
- Paper validation periods (calendar-bound: 30 sessions = ~6 weeks)
- Real-money rollout tiers (calendar-bound: 30 sessions = ~6 weeks)

For the build itself, parallel agent capacity is the only meaningful constraint. CC: use it.

---

## 1. Build principles

1. **Plan rigorously, build fast, validate exhaustively.** CC works at agent speed; the constraint is correctness, not engineering hours.
2. **Existing live stack is untouched.** No edits to `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `engine wb_bot.py`, `squeeze_detector_v2.py`, `l2_signals.py`, `ibkr_feed.py`, or any current production code. The framework lives in a new directory tree.
3. **YAML-driven strategy specs.** New strategies are new `.yaml` files in `strategies/`, not code changes. Build modular plugins (level sources, confirmations, stops, targets) such that the framework can compose any strategy from configuration alone.
4. **NautilusTrader for backtest only.** Do not migrate live execution. Backtest produces validated strategy specs; specs deploy to existing live infrastructure later.
5. **Every component ships with tests.** Unit tests for plugins, integration tests for strategy composition, backtest harness tests for fill modeling.
6. **Every strategy ships with a backtest report** before being marked validated.

---

## 2. Module structure (final)

```
warrior_bot/
├── framework/                                # NEW — the level-reaction framework
│   ├── __init__.py
│   ├── universe.py                          # universe selection + filters
│   ├── level_sources/
│   │   ├── __init__.py
│   │   ├── base.py                          # LevelSourceProtocol
│   │   ├── opening_range.py                 # ORB level source
│   │   ├── vwap.py                          # session + anchored VWAP
│   │   ├── pdh_pdl.py                       # prior day high/low
│   │   ├── round_number.py                  # whole-dollar levels
│   │   ├── volume_profile.py                # POC/VAH/VAL/HVN/LVN (Phase 2)
│   │   ├── swing.py                         # multi-day swing extremes (deferred)
│   │   └── box.py                           # consolidation range (deferred)
│   ├── arrival.py                           # generic arrival detection
│   ├── confirmations/
│   │   ├── __init__.py
│   │   ├── base.py                          # ConfirmationProtocol
│   │   ├── signal_candle.py                 # doji/hammer/shooting-star
│   │   ├── breakout_candle.py               # close beyond level + vol
│   │   ├── acceptance.py                    # ≥N bars inside (80% rule)
│   │   ├── rejection.py                     # failed-test pattern (PDH/PDL fade)
│   │   ├── l2_confirm.py                    # imbalance/stacking/thinning wrapper
│   │   └── volume_confirm.py                # volume threshold checks
│   ├── stops.py                             # stop placement strategies
│   ├── targets.py                           # target placement strategies
│   ├── sizing.py                            # unified position sizing (half-Kelly)
│   ├── registry.py                          # StrategySpec + StrategyRegistry
│   ├── attribution.py                       # per-strategy P&L tracking
│   ├── risk.py                              # per-strategy + portfolio kill switches
│   ├── vix_regime.py                        # VIX classifier (hooks built, default off)
│   ├── data_adapters/
│   │   ├── __init__.py
│   │   ├── databento_adapter.py             # historical data ingestion
│   │   ├── alpaca_adapter.py                # backtest with our paper data
│   │   └── ibkr_adapter.py                  # live data (Phase 2 — for live integration)
│   └── reports/
│       ├── __init__.py
│       └── per_strategy_breakdown.py        # daily report generator
├── strategies/                              # NEW — YAML strategy specs
│   ├── orb_5min.yaml
│   ├── vwap_trend_continuation.yaml
│   ├── vwap_mean_reversion.yaml
│   ├── pdh_pdl_fade.yaml
│   ├── pdh_pdl_breakout.yaml
│   ├── round_number.yaml
│   ├── volume_profile.yaml                  # Phase 2
│   ├── volume_profile_80_rule.yaml          # Phase 2
│   └── anchored_vwap.yaml                   # Phase 2
├── backtest/                                # NEW — backtest harness
│   ├── __init__.py
│   ├── nautilus_runner.py                   # NautilusTrader wrapper
│   ├── vectorbt_runner.py                   # research/parameter sweep
│   ├── walk_forward.py                      # walk-forward validation
│   ├── metrics.py                           # Sharpe, drawdown, profit factor, etc.
│   └── reports/                             # backtest output reports
└── tests/
    ├── framework/                           # unit tests for each plugin
    ├── strategies/                          # integration tests per strategy spec
    └── backtest/                            # backtest harness tests
```

**Critical rule:** None of this touches existing `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, engine bots, `squeeze_detector_v2.py`, `l2_signals.py`, `ibkr_feed.py`, `wb_persistence.py`, `wb_intraday_adder.py`. Those are production. They stay.

---

## 3. Agent assignments

CC spawns these as parallel subagents. Each has a clear deliverable and acceptance criteria. Agents work independently; sync points are explicit.

### Wave 1 — Infrastructure (start immediately, all parallel)

#### Agent A — Backtest infrastructure
**Goal:** NautilusTrader + Databento integration, working backtest harness.

**Deliverables:**
1. `backtest/nautilus_runner.py` — wraps NautilusTrader's `BacktestEngine`. Takes a strategy spec + universe + date range, returns trade log + metrics.
2. `backtest/vectorbt_runner.py` — vectorbt wrapper for parameter sweeps.
3. `framework/data_adapters/databento_adapter.py` — ingests Databento historical trade ticks (`trades` schema) and quote data (`bbo` schema). Converts to NautilusTrader's data format. Caches locally to `tick_cache_databento/`.
4. Documentation: how to obtain Databento Standard subscription, sample API calls, data format.
5. Sample backtest: run any trivial buy-and-hold strategy on AAPL Q1 2024 data, confirm output matches sanity expectations.

**Tests:**
- Unit: data adapter correctly converts Databento records to Nautilus bar/tick objects
- Integration: backtest of buy-and-hold AAPL Q1 2024 returns correct P&L within 1% of theoretical
- Performance: backtest 200K bars in <30 seconds

**Acceptance:** sample backtest runs end-to-end. Report saved to `cowork_reports/2026-05-XX_backtest_infra_validation.md`.

**Databento subscription:** Standard plan, $199/mo. If Manny hasn't subscribed yet, document the steps and pause. If subscription exists, proceed.

---

#### Agent B — Framework skeleton + plugin protocols
**Goal:** The core abstractions that all strategies plug into.

**Deliverables:**
1. `framework/registry.py` — `StrategySpec` dataclass, `StrategyRegistry` with YAML loader.
2. `framework/level_sources/base.py` — `LevelSourceProtocol` with method signatures: `compute_levels(symbol, history) → LevelSet`, `update_intraday(bar) → None`, etc.
3. `framework/confirmations/base.py` — `ConfirmationProtocol` with `check_confirmation(level, bars, l2_state) → ConfirmationResult`.
4. `framework/stops.py` — `StopRuleProtocol` with built-in implementations: `JustPastLevel`, `OppositeRange`, `InLVN`, `BarLow`.
5. `framework/targets.py` — `TargetRuleProtocol` with built-in implementations: `OppositeLevel`, `RMultiple`, `SessionClose`, `EdgeToEdge`, `TrailingATR`.
6. `framework/arrival.py` — `ArrivalDetector` with proximity-based detection (configurable proximity window per strategy).
7. Stub YAML loader: parse a `.yaml` spec → instantiate `StrategySpec` with correct plugin classes.

**Tests:**
- Unit: YAML loader correctly instantiates plugin classes
- Unit: each stop rule and target rule produces expected output on synthetic inputs
- Integration: round-trip a complete StrategySpec through YAML → registry → spec object

**Acceptance:** YAML loader can parse a complete strategy spec and instantiate all plugins without runtime errors.

---

#### Agent C — Universe filter
**Goal:** Daily universe scanner producing the symbol list every strategy operates on.

**Deliverables:**
1. `framework/universe.py` — `UniverseFilter` class. Takes a date, returns list of symbols passing all filters per design §2.
2. Filters implemented:
   - Price band ($10-$300 default, configurable)
   - ADV dollar volume (10M default)
   - Today's relative volume vs 20-day baseline
   - Float shares min/max
   - Day-range percentage
   - Sector exclusions (empty by default per Manny decision, configurable)
3. Data source: Databento for historical, IBKR scanner subscription for live (live integration is Phase 2 — for now, just historical).
4. Output: pickle/parquet of daily universe to `universe_cache/<date>.parquet`.

**Tests:**
- Unit: each filter correctly applies to synthetic data
- Integration: run universe filter for 2024-01-15, confirm output is reasonable (200-800 symbols)
- Sanity: top 10 dollar-volume symbols in output match known top-volume names that day

**Acceptance:** Universe filter produces a reasonable 2024-01-15 list. Report shows symbol count + sample to `cowork_reports/2026-05-XX_universe_validation.md`.

---

#### Agent D — Confirmation modules
**Goal:** All confirmation patterns Phase 1 needs.

**Deliverables:**
1. `framework/confirmations/signal_candle.py` — doji, hammer, shooting star detection per VP research §7. Exact mathematical criteria specified there.
2. `framework/confirmations/breakout_candle.py` — close beyond level + volume confirmation. Used by ORB and squeeze migration.
3. `framework/confirmations/acceptance.py` — N consecutive bars inside a zone (for 80% rule). Phase 2 but build now.
4. `framework/confirmations/rejection.py` — failed-test pattern: price touches level, closes back on the wrong side within 2 bars. Used by PDH/PDL fade.
5. `framework/confirmations/volume_confirm.py` — volume threshold checks (relative volume, vs prior bar, vs 20-day avg).
6. `framework/confirmations/l2_confirm.py` — wraps existing `l2_signals.py` for backtest use. Takes a snapshot (or reconstructed snapshot from L2 historical), returns confirmation verdict.

**Tests:**
- Unit: each pattern matches/rejects synthetic candle examples correctly
- Edge cases: zero-range bars, NaN volumes, missing prior bars all handled gracefully

**Acceptance:** Each confirmation pattern has ≥10 synthetic test cases covering valid signal, valid rejection, ambiguous cases.

---

#### Agent E — Sizing / risk / attribution
**Goal:** Position sizing, kill switches, and per-strategy P&L tracking.

**Deliverables:**
1. `framework/sizing.py` — half-Kelly position sizing per strategy. Takes (account equity, risk_per_trade_pct, stop_distance, fill_price) → share count. Caps at 10% of bar volume per research §3.
2. `framework/risk.py` — kill switches: per-strategy daily loss, per-strategy drawdown, consecutive losses, portfolio daily loss. State persisted to disk per architecture research §9.
3. `framework/attribution.py` — per-strategy trade log, P&L tracking, win rate, R-multiple distribution, Sharpe.
4. `framework/vix_regime.py` — VIX classifier with hooks per design §2.5. Default `WB_USE_VIX_REGIME=0`.

**Tests:**
- Unit: half-Kelly sizing produces expected share counts on synthetic inputs
- Unit: kill switches correctly trigger on synthetic drawdown sequences
- Unit: attribution correctly aggregates multi-strategy trades
- Unit: VIX classifier produces correct regime label for known VIX values

**Acceptance:** Sizing produces shares-per-trade for sample portfolio. Kill switch fires correctly. Attribution report matches manual P&L calculation on synthetic trades.

---

### Wave 2 — Level sources + Phase 1 strategies (parallel after Wave 1)

Each strategy gets a dedicated agent. Wave 2 begins after Wave 1 modules pass their acceptance criteria.

#### Agent F — Opening Range Breakout (ORB)
**Spec per design §4.1:**

```yaml
# strategies/orb_5min.yaml
name: "ORB-5min"
enabled: true
level_source:
  type: opening_range
  params:
    minutes: 5
    use_5min_direction_bias: true
arrival_detector:
  type: proximity
  params:
    proximity_pct: 0.001       # within 0.1% of level
confirmation_rule:
  type: breakout_candle
  params:
    min_vol_mult_today_vs_baseline: 2.0
    min_breakout_pct: 0.0002
    require_close_beyond: true
stop_rule:
  type: opposite_range
target_rule:
  type: composite
  params:
    primary: r_multiple
    r_multiple: 2.0
    fallback: session_close
    activate_trailing_at_r: 1.5
    trailing_atr_mult: 1.5
risk_per_trade_pct: 1.0
max_concurrent_positions: 5
trade_windows: [["09:35", "15:55"]]
vix_size_multiplier:
  use_vix: false              # off by default
```

**Deliverables:**
1. `framework/level_sources/opening_range.py` — computes ORH/ORL from first 5-min bar
2. YAML spec above
3. Backtest report: ORB-5 on 2016-2023 historical (Zarattini paper period) — reproduce paper-level metrics
4. Sensitivity analysis: 5-min vs 15-min vs 30-min opening range
5. Universe attribution: which price tiers ($10-20, $20-50, etc.) ORB actually performs in

**Acceptance gates:**
- Backtest Sharpe ≥ 1.5 on 2020-2023 OOS (50% haircut from paper's 2.81)
- ≥ 100 trades in OOS period
- Max drawdown ≤ 10%
- Walk-forward robustness: performance not concentrated in one quarter

**Report:** `cowork_reports/2026-05-XX_orb_backtest.md`. If criteria pass → paper deployment ready.

---

#### Agent G — VWAP (trend continuation + mean reversion)
**Spec per design §4.2:**

Two YAML specs: `vwap_trend_continuation.yaml` and `vwap_mean_reversion.yaml`. Both share a `level_source: vwap` plugin but differ in arrival, confirmation, stop, target.

**Deliverables:**
1. `framework/level_sources/vwap.py` — session VWAP + ±N σ bands (configurable)
2. VWAP slope classifier — determines which sub-strategy applies (regime gate)
3. Both YAML specs
4. Backtest report comparing: VWAP-trend alone, VWAP-revert alone, regime-gated combined
5. Universe attribution

**Acceptance gates (per strategy):**
- Backtest Sharpe ≥ 1.2 (lower bar than ORB since this is hybrid)
- ≥ 100 trades
- Max drawdown ≤ 10%
- Combined-vs-individual: regime-gated combined Sharpe ≥ better of either individual

**Report:** `cowork_reports/2026-05-XX_vwap_backtest.md`

---

#### Agent H — PDH/PDL (fade + breakout)
**Spec per design §4.3:**

Two YAML specs: `pdh_pdl_fade.yaml` and `pdh_pdl_breakout.yaml`. Share level_source, differ in confirmation/stop/target.

**Deliverables:**
1. `framework/level_sources/pdh_pdl.py` — prior session RTH high/low
2. Both YAML specs
3. Backtest report
4. Conflict resolution: if PDH-fade and PDH-breakout both signal, which wins? Document the rule.

**Acceptance gates:**
- Per-strategy Sharpe ≥ 1.3
- ≥ 100 trades each
- Max drawdown ≤ 10%

**Report:** `cowork_reports/2026-05-XX_pdh_pdl_backtest.md`

---

#### Agent I — Round Number
**Spec per design §4.4:**

```yaml
# strategies/round_number.yaml
name: "Round-Number"
enabled: true
level_source:
  type: round_number
  params:
    increments:                            # configurable per price tier
      "10_50": [1.00, 5.00]                # $10-50 stocks: whole dollar + $5
      "50_150": [5.00]                     # $50-150 stocks: $5 levels
      "150_300": [5.00, 10.00]             # $150+ stocks: $5 and $10
    options_oi_overlay: false              # Phase 2 enhancement
arrival_detector:
  type: proximity
  params:
    proximity_dollar:                       # absolute dollar proximity by tier
      "10_50": 0.10
      "50_150": 0.25
      "150_300": 0.50
confirmation_rule:
  type: signal_candle
  params:
    patterns: [doji, hammer, shooting_star]
    require_volume_increase: true
    require_l2_confirm: true               # uses existing l2_signals.py
stop_rule:
  type: just_past_level
  params:
    pad_dollar:
      "10_50": 0.05
      "50_150": 0.10
      "150_300": 0.25
target_rule:
  type: composite
  params:
    primary: next_round_number
    fallback: r_multiple
    r_multiple: 2.0
risk_per_trade_pct: 1.0
max_concurrent_positions: 3
trade_windows: [["09:30", "15:55"]]
```

**Deliverables:**
1. `framework/level_sources/round_number.py`
2. YAML spec
3. Backtest report — pay particular attention to per-price-tier performance (this is where universe expansion to $10-300 gets validated)
4. Comparison vs existing squeeze: where does round-number fire that squeeze doesn't, and vice versa

**Acceptance gates:**
- Per-tier Sharpe (where strategy fires) ≥ 1.3
- ≥ 100 trades total
- Max drawdown ≤ 10%

**Report:** `cowork_reports/2026-05-XX_round_number_backtest.md`

---

### Wave 3 — Cross-strategy integration + portfolio validation (after Wave 2)

#### Agent J — Multi-strategy portfolio backtest
**Goal:** Run all four Phase 1 strategies simultaneously on the same paper account, validate concurrency, capital allocation, attribution.

**Deliverables:**
1. Portfolio backtest config: all four strategies enabled, equal-weight starting allocation
2. Capital allocation sweep: equal-weight vs Sharpe-weighted vs half-Kelly per strategy
3. Concurrency stress test: synthetic day where all four strategies fire on the same symbol — confirm net aggregation works
4. Attribution validation: per-strategy P&L sums to portfolio P&L exactly

**Acceptance gates:**
- Portfolio Sharpe ≥ best-individual-strategy Sharpe (diversification benefit)
- Portfolio max drawdown ≤ 12%
- Capital allocation method that produces best OOS Sharpe wins (data-driven per Manny's decision)
- Concurrency tests pass

**Report:** `cowork_reports/2026-05-XX_portfolio_phase1_backtest.md`

---

#### Agent K — Walk-forward + robustness
**Goal:** Validate strategies are robust, not curve-fit.

**Deliverables:**
1. Walk-forward: 3-month train, 1-month test, rolling across 2020-2024
2. Parameter sensitivity: vary key parameters ±20%, check Sharpe stability
3. Regime decomposition: bull (2020-2021), bear (2022), choppy (2023-2024) — per-regime Sharpe
4. VIX regime test: run portfolio with VIX-on vs VIX-off. If VIX-on improves Sharpe by ≥10%, recommend enabling.
5. Time-of-day analysis: P&L by 30-min bucket. Recommend narrowing the all-day window if data supports.
6. Sector analysis: P&L by sector. Recommend exclusions if data supports.

**Report:** `cowork_reports/2026-05-XX_phase1_robustness.md` — informs final pre-paper config.

---

### Wave 4 — Live integration prep (after Wave 3 validation passes)

Only proceeds if Phase 1 strategies pass all backtest acceptance gates.

#### Agent L — Live data adapter
**Goal:** Connect framework to existing IBKR + Alpaca live data for paper deployment.

**Deliverables:**
1. `framework/data_adapters/ibkr_adapter.py` — pulls live data from existing IBKR connection (shared with current bots)
2. Bridge layer: framework consumes the same tick/bar feed as `bot_v3_hybrid.py`
3. Paper account configuration: which paper account runs the framework (recommend: the 4th unused paper account that was reserved)

**Acceptance:** Framework subscribes to live IBKR feed, processes a real symbol, generates ARM events identical to backtest behavior given the same input.

---

#### Agent M — Live execution integration
**Goal:** Connect framework to Alpaca for paper execution.

**Deliverables:**
1. Execution adapter: framework strategy signals → Alpaca paper orders
2. Order management: trailing stops, partial exits, force-exit at 19:55 (mirrors existing force-exit pattern)
3. Daily report integration: framework P&L flows into existing daily breakdown schema

**Acceptance:** Framework places a paper trade on the reserved 4th paper account. Daily report shows the trade attributed to the correct strategy.

---

### Wave 5 — Phase 2 strategies (build during Phase 1 paper validation)

These can begin as soon as Wave 1 + 2 infrastructure is solid. They run in parallel with Phase 1 paper validation.

#### Agent N — Volume Profile / AMT
Full POC/VAH/VAL/HVN/LVN infrastructure per design §4.5 and VP research §1-9.

**Deliverables:**
1. `framework/level_sources/volume_profile.py` — POC, VAH, VAL, HVN, LVN computation from tick data per VP research mathematical definitions
2. Profile shape classifier — D/P/B/I per VP research §4
3. Two YAML specs: `volume_profile.yaml` (edge-to-edge fade) and `volume_profile_80_rule.yaml` (VA re-entry)
4. Backtest report
5. Specific validation: does VP backtest replicate Trading Notes video methodology?

**Acceptance gates:** same as Phase 1 strategies.

---

#### Agent O — Anchored VWAP
**Spec per design §4.6.** Anchored from gap day, earnings day, or news catalyst.

**Deliverables:**
1. `framework/level_sources/vwap.py` — extend session VWAP module to support anchoring from arbitrary timestamps
2. Catalyst detection: gap day (open > prior close × 1.05 or < × 0.95), earnings day (via earnings calendar — Databento has this)
3. YAML spec
4. Backtest report

**Acceptance gates:** same as Phase 1.

---

#### Agent P — L2 confirmation enhancement across all strategies
**Goal:** Wire `l2_confirm` into Phase 1 strategies retroactively.

**Deliverables:**
1. Update Phase 1 YAML specs to include L2 confirmation as optional confirmation_rule component
2. Backtest comparison: Phase 1 strategies with L2 confirmation vs without
3. Decision matrix: which strategies benefit from L2 confirmation, which don't

**Note:** This depends on having historical L2 data (Databento MBP-10 schema, may require Plus subscription upgrade). If Standard plan only includes L1, this agent's scope reduces to "build the integration, defer the validation until Plus subscription justifies."

---

## 4. Squeeze migration (Wave 5 conditional)

Squeeze is currently in `squeeze_detector_v2.py` and goes real-money 6/15 in its current form. Squeeze migration to the framework is **post-6/15 work**, not part of this build.

When migrated (post-go-live):
1. New YAML: `strategies/squeeze.yaml` with level_source=round_number+pm_high, confirmation=breakout_candle, etc.
2. Existing `squeeze_detector_v2.py` becomes a level_source plugin (extracted from), then deprecated
3. Live integration switches from existing bot to framework-based execution
4. Real-money rollout tiered to prevent regression

Do not begin squeeze migration until at least one Phase 1 strategy has cleared paper validation. Acceptance: framework has proven it can host a live strategy without regressions.

---

## 5. Validation gates (must pass before any strategy goes paper or live)

### Backtest → Paper

Per design §7.1:
- Backtest Sharpe (6-month OOS) ≥ 1.5
- Max drawdown ≤ 10%
- Profit factor ≥ 1.4
- ≥ 100 trades in OOS period
- Walk-forward robustness: performance not concentrated in single quarter

### Paper → Real Money

Per design §7.2:
- ≥ 30 paper sessions
- Paper Sharpe (rolling 20-session) ≥ 1.2
- Paper max drawdown ≤ 8%
- Paper-vs-backtest consistency: Sharpe within 0.5 of backtest
- Zero P0 production incidents

### Real Money Rollout

Per design §7.3:
- First 10 sessions: 25% target notional
- Sessions 11-20: 50%
- Sessions 21-30: 75%
- Session 30+: 100%
- -5% drawdown reverts one tier; two consecutive reverts pause strategy

---

## 6. Reports CC owes

### Wave 1 (infrastructure)
- `cowork_reports/2026-05-XX_backtest_infra_validation.md` — Agent A
- `cowork_reports/2026-05-XX_framework_skeleton.md` — Agent B
- `cowork_reports/2026-05-XX_universe_validation.md` — Agent C
- `cowork_reports/2026-05-XX_confirmations_unit_tests.md` — Agent D
- `cowork_reports/2026-05-XX_sizing_risk_attribution.md` — Agent E

### Wave 2 (Phase 1 strategy backtests)
- `cowork_reports/2026-05-XX_orb_backtest.md` — Agent F
- `cowork_reports/2026-05-XX_vwap_backtest.md` — Agent G
- `cowork_reports/2026-05-XX_pdh_pdl_backtest.md` — Agent H
- `cowork_reports/2026-05-XX_round_number_backtest.md` — Agent I

### Wave 3 (portfolio + robustness)
- `cowork_reports/2026-05-XX_portfolio_phase1_backtest.md` — Agent J
- `cowork_reports/2026-05-XX_phase1_robustness.md` — Agent K

### Wave 4 (live prep)
- `cowork_reports/2026-05-XX_framework_live_integration.md` — Agents L+M combined

### Wave 5 (Phase 2)
- `cowork_reports/2026-05-XX_volume_profile_backtest.md` — Agent N
- `cowork_reports/2026-05-XX_anchored_vwap_backtest.md` — Agent O
- `cowork_reports/2026-05-XX_l2_confirmation_integration.md` — Agent P

Plus a synthesis report after each Wave: what passed, what didn't, what changes for the next Wave.

---

## 7. What CC should NOT do

1. **Do not modify existing live code.** Production stays as-is.
2. **Do not try to migrate squeeze yet.** That's post-6/15 work.
3. **Do not deploy to a real paper account until backtest validation passes.** Wave 4 only after Wave 3 acceptance.
4. **Do not commit to specific capital allocation method.** Data-driven per design §5.5.
5. **Do not enable VIX regime by default.** Build hooks, default off, validate from backtest.
6. **Do not pre-exclude sectors or narrow universe.** Backtest first, decide from data.
7. **Do not stop the Monday production checklist.** That work runs in parallel and ships separately.

---

## 8. Parallelization guidance

CC should spawn agents in waves with sync points:

**Wave 1:** Agents A, B, C, D, E in parallel. Sync when all acceptance criteria pass. ~5 agents.

**Wave 2:** Agents F, G, H, I in parallel (after Wave 1 acceptance). Each does its own backtest. ~4 agents.

**Wave 3:** Agents J, K in parallel (after Wave 2 acceptance). ~2 agents.

**Wave 4:** Agents L, M in sequence (after Wave 3 acceptance and Manny approval to start paper). ~2 agents.

**Wave 5:** Agents N, O, P in parallel (can begin during Wave 4 paper validation). ~3 agents.

Total: ~16 agent-tasks across 5 waves. Most agents work in <1 hour at CC speed. Wall-clock for full Phase 1 + Phase 2 build is bounded by the slowest agent in each wave + Manny's review time at sync points, not by sequential build time.

---

## 9. Sync points where Manny weighs in

1. **After Wave 1 acceptance:** "Is the framework architecture sound? Anything to revise before strategy builds?"
2. **After Wave 2 individual strategy backtests:** "Do these results justify portfolio integration?"
3. **After Wave 3 portfolio backtest:** "Approve paper deployment?"
4. **After 30 paper sessions per strategy:** "Approve real-money rollout?"
5. **Post-6/15 (squeeze stable):** "Begin squeeze migration to framework?"

---

## 10. What this directive does NOT change

1. **6/15 squeeze-only real money cutover** — stands
2. **Monday production checklist** — CC works it in parallel with this build
3. **All Saturday ships** (FCHL fix, force-exit, L2 async, dead-tape gate) — stand
4. **Existing live bots** — untouched
5. **Persistence layer + intraday adder** — continue running for current strategies
6. **WB retirement** — stands. The new framework is successor, not extension.

---

## 11. Tone

This is the largest build directive of the project — but each piece is small and well-scoped. CC has the agent capacity to run all of Wave 1 in parallel, all of Wave 2 in parallel after that, etc. The wall-clock isn't months; it's the time it takes to spawn agents, get results, sync, and iterate.

Quality matters more than speed. Every component has tests. Every strategy has a backtest with acceptance criteria. Nothing ships to paper without backtest validation; nothing ships to real money without paper validation.

This is the bot we should have been building from the start. The path is clear, the pieces are specified, the validation gates are rigorous. Build it.

---

## 12. Files referenced

- `DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md` — the design this build implements
- `research_vp_market_profile.md` — VP technical foundations
- `research_universe_selection.md` — universe rationale
- `research_multi_strategy_architecture.md` — architecture patterns
- `research_candidate_strategies.md` — Phase 1 + 2 strategy specs
- `research_backtest_infrastructure.md` — NautilusTrader + Databento selection
- `trading_notes_volume_profile_strategy.md` — video extraction (Phase 2 reference)
- Existing live code (UNTOUCHED): `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, engine bots, `squeeze_detector_v2.py`, `l2_signals.py`, `ibkr_feed.py`, `wb_persistence.py`, `wb_intraday_adder.py`
- All Saturday ship reports — stand

---

## 13. Start when ready

CC: Wave 1 begins as soon as Databento Standard subscription is in place. If Manny has not subscribed yet, that's the only external blocker; otherwise spawn the 5 Wave 1 agents now.

Squeeze production work continues in parallel. The Monday checklist, 5/22 squeeze evaluation, and 6/15 cutover are entirely separate workstreams from this build.

Welcome to the framework era.
