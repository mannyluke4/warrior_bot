# Healthy Fluctuation Framework — Unified Design Document

**Date:** 2026-05-17
**Author:** Cowork (Perplexity), synthesizing 5 parallel research workstreams
**For:** Manny (review) → CC (build)
**Status:** Draft for Manny review. Build directive follows approval.

**Research inputs:**
- `research_vp_market_profile.md` — VP/Market Profile technical foundations
- `research_universe_selection.md` — Liquidity criteria and price-band selection
- `research_multi_strategy_architecture.md` — Multi-strategy patterns from production systems
- `research_candidate_strategies.md` — Portfolio of 10 candidate strategies, ranked
- `research_backtest_infrastructure.md` — Backtest framework selection + fidelity ceiling

---

## 1. The principle (locked in)

**Prices fluctuate. Healthy fluctuations have detectable, objective properties. The bot's job is to find them and execute on them with the speed, breadth, and consistency humans can't match.**

Five objective properties define a "healthy fluctuation":
1. **Real participation** — multiple market participants, volume confirms activity
2. **Predictable level structure** — moves respect identifiable levels
3. **Direction-able** — reversal-or-continuation pattern at the level the bot can detect
4. **Risk-definable** — clear failure point (stop)
5. **Edge-to-edge potential** — next level where reaction is likely (target)

Every strategy in this framework is one instance of:

```
strategy = (level_source, arrival_detector, confirmation_rule, stop_rule, target_rule)
```

---

## 2. Universe definition (data-driven, expanded for backtesting)

Manny's intuition — "higher prices fluctuate better" — has structural backing across five mechanisms documented in market microstructure literature: adverse selection compensation, HFT depth competition, institutional participation, fragmentation effects, and options-driven hedging flow.

**Decision (per Manny 5/17 review):** **Expand backtest universe to $10-$300.** Narrow based on data showing where strategies actually perform. Sector exclusions and time-of-day windows also data-driven, not pre-imposed.

### 2.1 Price tier eligibility

Per universe research §1.5 and §2:

| Price tier | Status | Reasoning |
|---|---|---|
| Sub-$5 (penny) | **EXCLUDE** | LULD ±75% bands trigger constantly. MM withdrawal. Penny-jumping HFT. Levels undefended. Not in backtest universe. |
| $5–$10 | **EXCLUDE** | LULD ±20% (under $3) or ±10% bands. Unreliable level structure. Not in backtest universe. |
| **$10–$20** | **INCLUDE in backtest** | Moderate level reliability. Data will tell us if strategies work here. |
| **$20–$100** | **INCLUDE in backtest** | Strong MM participation, deep HFT, institutional flow, high level reliability. |
| **$100–$200** | **INCLUDE in backtest** | Deepest book. Options-driven round-number levels. Very high level reliability. |
| **$200–$300** | **INCLUDE in backtest** | Same edge, reduced shares-per-position. Data will tell us if shares-per-trade is too constraining. |
| $300+ | EXCLUDE | Each lot too expensive vs $50-100K notional. Future expansion possible. |

### 2.2 Liquidity filters

Per universe research §3-4. Backtest sweep these to find optimal cuts:

```
WB_UNIVERSE_PRICE_MIN=10.00                     # 5/17: expanded from 20
WB_UNIVERSE_PRICE_MAX=300.00                    # 5/17: expanded from 200
WB_UNIVERSE_ADV_DOLLAR_MIN=10_000_000           # $10M daily dollar volume avg (sweep: 5/10/25/50M)
WB_UNIVERSE_TODAY_DOLLAR_VOL_MIN=25_000_000     # $25M today (sweep relative vol)
WB_UNIVERSE_FLOAT_SHARES_MIN=20_000_000         # 20M float minimum (sweep: 10/20/50M)
WB_UNIVERSE_FLOAT_SHARES_MAX=500_000_000        # 500M maximum
WB_UNIVERSE_DAY_RANGE_PCT_MIN=2.0               # 2% intraday range minimum (sweep)
```

For a $50-100K notional bot, target staying below 10% of ADV per session (institutional benchmark). The 1M-share ADV floor is hard floor for considering a symbol at all.

**Backtest plan:** Run each Phase 1 strategy across the full $10-$300 universe. Bucket results by price tier ($10-20, $20-50, $50-100, $100-200, $200-300) and analyze Sharpe, win rate, R-multiple per bucket. Tighten universe to the tiers where strategies actually work.

### 2.3 Sector exclusions (data-driven)

**Decision (per Manny 5/17 review):** Don't pre-exclude sectors. Let backtest data tell us.

Research §10 flagged biotech (FDA binary events), energy E&P (oil-driven multi-input noise), shipping (cargo-rate noise) as historically problematic for level-reaction strategies. We'll include all sectors in backtest and review per-sector Sharpe/drawdown. If biotech turns out to be drag, exclude. If it's neutral or positive, keep.

```
WB_UNIVERSE_EXCLUDE_SECTORS = []                # populated post-backtest
```

**Backtest analysis output should include:** per-sector P&L attribution, per-sector trade count, per-sector drawdown contribution. Exclude only sectors that demonstrably hurt portfolio metrics.

### 2.4 Time-of-day windows (data-driven)

**Decision (per Manny 5/17 review):** Trade the full RTH window for now. Backtest will reveal whether midday is structurally weaker.

```
WB_TRADE_WINDOWS = [
    ("09:30", "15:55"),  # full RTH minus the last 5 min for safety
]
# Backtest analysis: bucket trades by hour, identify P&L by time-of-day
# Force-exit at 19:55 ET unchanged (no overnight holds)
```

**Backtest analysis output should include:** P&L by 30-minute bucket. If midday (11:30-13:30) is demonstrably worse, pause it. If first-30-min is full of false-breakouts, push start to 10:00. Let data make the call.

Research §11 evidence to keep in mind during analysis: first-half-hour return statistically predicts last-half-hour return; opening 30 min is the regime signal, not the entry zone.

### 2.5 VIX regime overlay (build hooks, default OFF, validate from data)

**Decision (per Manny 5/17 review):** Build the infrastructure to respect VIX-based size adjustment, but **default disabled**. Backtest with and without; flip on if data shows improvement.

```
WB_USE_VIX_REGIME=0                             # default disabled, enable post-validation
WB_VIX_REGIME_RULES:
  vix < 13          → 50% size or pause (insufficient realized range)
  vix 13 - 16       → 75% size
  vix 16 - 28       → 100% size (optimal regime)
  vix 28 - 35       → 75% size
  vix 35 - 45       → 50% size
  vix > 45          → pause
```

**Rationale:** VIX is free, real-time, always available — the hooks cost nothing to build. The question is whether the regime classification improves portfolio Sharpe. Backtest with VIX-on vs VIX-off across the universe period; if VIX-on doesn't improve risk-adjusted returns by ≥10%, leave it off.

**VIX definition recap:** CBOE Volatility Index, real-time 30-day expected S&P 500 volatility from options pricing. Free data via SPY options or direct VIX index quote. Updates every 15 seconds.

### 2.6 Universe estimated size

Applying the expanded $10-$300 filters to US equities: **approximately 400-800 names per day** depending on regime. The bot's scanner watches all of them, the framework selects trades from arrivals at qualifying levels.

For reference: current ~30-symbol watchlist is 1-2% of the new universe size. This is the breadth advantage the bot was always supposed to have but didn't.

---

## 3. Strategy portfolio (build set)

Per candidate strategy research §Executive Summary, ranked by edge × bot-shape × complexity × data-availability.

### 3.1 Phase 1 strategies (build first — low complexity, high edge confidence)

| # | Strategy | Status |
|---|---|---|
| **1** | **Opening Range Breakout (ORB)** | **Strongest empirical evidence.** Zarattini et al. (2024) SSRN paper: Sharpe 2.81, 36% alpha, 7,000 stocks tested. Stocks-in-Play filter is the real edge. |
| **2** | **VWAP Reversion / Breakout** | Strong as confluence/context, weaker as standalone. Use as both regime classifier and entry signal. |
| **3** | **Prior Day High/Low (PDH/PDL) Reactions** | Simple, robust, well-documented practitioner edge. Low complexity. |
| **4** | **Round Number / Whole-Dollar Reactions** | Already in production via squeeze. Becomes a level-source plugin. Options-OI cross-reference adds bot-only edge. |

### 3.2 Phase 2 strategies (build second — medium complexity, requires VP infrastructure)

| # | Strategy | Status |
|---|---|---|
| **5** | **Volume Profile / AMT** | The full POC/VAH/VAL/HVN/LVN level set with 80% rule re-entry and signal candle confirmation. Requires tick data for accurate profile reconstruction. |
| **6** | **Anchored VWAP from Key Events** | Pairs with VWAP and VP. Anchored from gap day, earnings, or major news. |

### 3.3 Phase 3 / Conditional

| # | Strategy | Status |
|---|---|---|
| **7** | **Multi-day Swing High/Low Breakout** | Useful as level-source plugin (5/10/20-day extremes). |
| **8** | **Box / Consolidation Breakout** | Lower priority — depends on accurate range detection. |
| **9** | **Mean Reversion at Std Dev Extremes** | DEFER — fails catastrophically on trend days without regime detection. |
| **10** | **L2 Order Book Imbalance** | DEFER — edge marginal at >1-second execution speeds for US equities. Build as confluence signal only, not standalone strategy. |

### 3.4 Squeeze (existing, validated)

Continues to run as configured. Real-money 6/15. **Migrates to the new framework architecture post-go-live**: squeeze becomes one instance of the level-reaction framework where:
- `level_source` = whole-dollar + premarket high
- `confirmation_rule` = breakout candle with vol_mult
- `stop_rule` = below level
- `target_rule` = parabolic trail + dollar cap

This migration is mechanical, not functional. Squeeze stays exactly what it is operationally; it just gets re-expressed in the unified framework.

---

## 4. Per-strategy specifications

### 4.1 Opening Range Breakout (ORB-5)

**Level source:** High and low of first 5-minute bar (09:30-09:35 ET).

**Arrival:** Price trades at or through ORH or ORL after 09:35.

**Confirmation:**
- Direction of opening 5-min bar sets bias (green → long bias, red → short bias)
- Relative volume in first 5 minutes ≥ 2.0× the symbol's 20-day average for that 5-min window (the "Stocks in Play" filter — this is what makes ORB work per Zarattini et al.)
- Breakout candle closes above ORH (long) or below ORL (short)
- Confluence bonus: ORB break aligns with PDH (long) or PDL (short)

**Stop:** Opposite side of opening range.

**Target:** Session close (per Zarattini paper) OR 2:1 R-multiple, whichever fires first. ATR-trailing stop activates at 1.5R for extension capture.

**Universe:** $20-200 price band, ≥2.0× RVOL today, ≥$25M today's dollar volume.

**Acceptance criteria for live ship:**
- Backtest 2016-2023 reproduces Sharpe ≥ 1.5 (50% haircut from paper's 2.81 for realism)
- Paper 30 sessions ≥ 50% win rate, R-multiple distribution mean ≥ +0.3R

### 4.2 VWAP Reversion / Breakout

**Two sub-strategies, regime-gated by VWAP slope:**

**Sub-A: Trend Continuation (when VWAP slope is non-flat)**
- Level: VWAP line itself
- Arrival: Price pulls back to VWAP from extended position
- Confirmation: Rejection candle at VWAP + volume decline on pullback
- Stop: 0.5 ATR past VWAP on the wrong side
- Target: Prior intraday extreme OR opposite ±2σ VWAP band

**Sub-B: Mean Reversion (when VWAP slope is flat AND price ≥ 2σ from VWAP)**
- Level: ±2σ or ±2.5σ VWAP bands
- Arrival: Price extends to band
- Confirmation: Rejection candle at band, RSI divergence, or close back inside band
- Stop: Just past band extreme
- Target: VWAP center (1:1) then ±1σ extension (2:1)

**Universe:** Same as ORB. Avoid sub-$20.

**Acceptance criteria:**
- Backtest: VWAP regime classifier improves combined Sharpe over either alone
- Paper 30 sessions per sub-strategy: positive expectancy, max drawdown < 5%

### 4.3 PDH/PDL Reactions

**Level source:** Prior session's high and low (RTH, not EH).

**Arrival:** Price approaches within 0.3% of PDH or PDL.

**Confirmation (rejection — fade trade):**
- Failed test: price touches level and closes back below (PDH) or above (PDL) within 2 bars
- Volume on failed test > volume on approach
- Hourly bias not in conflict (don't fade PDH on strong opening uptrend with VWAP slope up)

**Confirmation (breakout):**
- Close beyond level by ≥0.2%
- Volume on breakout > 1.5× preceding 20-bar avg
- VWAP relationship aligned (price above VWAP for long breakout)

**Stop:** Just past the level on the wrong side (fade) OR back inside the range (breakout).

**Target:** Edge-to-edge — if fading PDH, target PDL or 1.5R extension; if breaking PDH, target next swing high or 2R extension.

**Universe:** Same. Both fade and breakout coexist as separate strategy instances.

### 4.4 Round Number Reactions

**Level source:** Whole dollars (e.g., $50.00, $75.00, $100.00). For higher-priced stocks, $5 multiples ($150, $155, $160). For $100+ stocks with high options OI, the OI-weighted strike levels.

**Arrival:** Price approaches within $0.15 of a round level (calibratable by price tier).

**Confirmation:** Same signal-candle logic as VP (doji/hammer/shooting-star with volume confirmation + L2 imbalance check).

**Stop:** Just past the level.

**Target:** Next round number OR 2R, whichever closer.

**Universe:** Same. Particularly strong on $100+ stocks where options gamma anchors round numbers.

**Note:** This is mechanically similar to squeeze's whole-dollar level reactions, but operates on the new universe (mid-to-high price) and uses signal-candle confirmation instead of squeeze-style breakout. The two coexist as separate strategies in the registry.

### 4.5 Volume Profile / AMT (full Phase 2 spec)

**Level source:** Prior session's POC, VAH, VAL, plus all HVNs (volume ≥150% of avg bin) and LVNs (volume ≤30% of avg bin) from the prior RTH session. Reconstructed from Databento or Alpaca tick data.

**Arrival modes:**
- **Edge-to-edge:** Price arrives at VAH or VAL from inside VA
- **80% Rule:** Price opened outside VA, re-entered VA, held inside for ≥2 consecutive 30-min brackets
- **Profile shape:**
  - **D-shape (balanced):** Fade either extreme (VAH or VAL) toward POC
  - **P-shape (heavy top):** Only valid if close > 50% of day-range. Long pullbacks to POC or tail clusters.
  - **B-shape (heavy bottom):** Only valid if close < 50% of day-range. Short pullbacks to POC or tail clusters.
  - **I-shape (one-sided trend):** Trade WITH trend at small clusters within the thin profile

**Confirmation:**
1. Signal candle at the level: doji (body <10% of range), hammer (lower shadow ≥2× body, ≤0.1× body upper shadow), or shooting star (upper shadow ≥2× body, body in lower 25% of range)
2. Volume on signal candle > volume on prior candle
3. L2 confirmation: imbalance > 0.55 (for long) or < 0.45 (for short), bid stacking near level (long), or ask thinning above level (long)

**Stop:** Just past the HVN edge, into the LVN. For 80% Rule: just outside the VA boundary.

**Target:** Opposite edge of the profile (edge-to-edge). For D-shape rotations: POC. For P/B shapes: opposite POC/tail cluster.

**Universe:** Same. VP is most reliable on names with consistent daily participation patterns.

**Critical implementation note:** Per VP research §1.1, tick data is mandatory for accurate profile reconstruction. 1m bars produce POC errors of 2-10+ ticks. Use Databento `trades` schema or Alpaca SIP ticks. Restrict to RTH 09:30-16:00 ET.

### 4.6 Anchored VWAP

**Level source:** VWAP anchored to a specific event timestamp:
- Premarket high or low of catalyst day
- Open of earnings day
- News announcement timestamp
- Gap-day open

**Arrival, confirmation, stop, target:** Mirrors VWAP Reversion/Breakout (4.2), but with anchored VWAP replacing session VWAP.

**Why this matters:** Per universe research, gap-and-go and news-catalyst stocks form structurally different volume profiles. Their session VWAP is anchored to retail noise; anchored VWAP from the event is the level that institutional algos benchmark against.

---

## 5. Architecture (research-backed patterns)

### 5.1 Module structure

Per architecture research §1-2, adopt LEAN's five-module pipeline with strategy isolation:

```
warrior_bot/
├── framework/
│   ├── universe.py              # universe selection + filters
│   ├── level_sources/
│   │   ├── orb.py               # opening range high/low
│   │   ├── vwap.py              # session + anchored VWAP
│   │   ├── pdh_pdl.py           # prior day high/low
│   │   ├── round_number.py      # whole-dollar levels
│   │   ├── volume_profile.py    # POC/VAH/VAL/HVN/LVN
│   │   ├── swing.py             # multi-day swing extremes
│   │   └── box.py               # consolidation range bounds
│   ├── arrival.py               # arrival detection (proximity to level)
│   ├── confirmations/
│   │   ├── signal_candle.py     # doji/hammer/shooting-star
│   │   ├── breakout_candle.py   # close beyond level + vol
│   │   ├── acceptance.py        # ≥N bars inside (80% rule)
│   │   └── l2_confirm.py        # imbalance/stacking/thinning
│   ├── stops.py                 # stop placement strategies
│   ├── targets.py               # target placement strategies
│   ├── sizing.py                # unified position sizing
│   ├── registry.py              # StrategySpec + StrategyRegistry
│   ├── execution.py             # shared order routing
│   ├── risk.py                  # per-strategy + portfolio risk
│   └── attribution.py           # per-strategy P&L tracking
├── strategies/                  # strategy SPECS (YAML configs, not code)
│   ├── orb_5min.yaml
│   ├── vwap_reversion.yaml
│   ├── vwap_breakout.yaml
│   ├── pdh_pdl_fade.yaml
│   ├── pdh_pdl_break.yaml
│   ├── round_number.yaml
│   ├── volume_profile.yaml
│   ├── volume_profile_80_rule.yaml
│   └── anchored_vwap.yaml
├── squeeze_detector_v2.py       # existing, migrates to framework post-6/15
└── data_engine.py               # existing, gains framework integration
```

### 5.2 The StrategySpec interface (from architecture research §2)

```python
@dataclass
class StrategySpec:
    name: str
    enabled: bool
    universe_filters: list[UniverseFilter]
    level_source: LevelSourceProtocol
    arrival_detector: ArrivalProtocol
    confirmation_rule: ConfirmationProtocol
    stop_rule: StopRuleProtocol
    target_rule: TargetRuleProtocol
    risk_per_trade_pct: float
    max_concurrent_positions: int
    trade_windows: list[tuple[str, str]]  # ("10:00", "11:30")
    vix_size_multiplier: dict[str, float]  # VIX regime → size mult
```

Each strategy is a YAML spec instantiating these fields. New strategies = new YAML files, no code changes.

### 5.3 Concurrency / conflict resolution (architecture research §7)

Multiple strategies on the same symbol use **net aggregation with intent-level logging**:

- Each strategy emits a position intent (symbol, direction, target_notional, stop)
- A central aggregator nets intents into one broker order
- Per-strategy attribution preserved in metadata for daily reports
- If two strategies disagree on direction (long + short), the larger conviction wins; the loser's intent is logged as overridden

### 5.4 Per-strategy kill switches (architecture research §4)

```
WB_<STRATEGY>_DAILY_LOSS_LIMIT_PCT=2.0          # halts strategy at -2% account
WB_<STRATEGY>_DRAWDOWN_TRIGGER_PCT=5.0          # halts at -5% from peak
WB_<STRATEGY>_CONSECUTIVE_LOSSES_LIMIT=4        # halts after 4 consecutive losses
WB_PORTFOLIO_DAILY_LOSS_LIMIT_PCT=4.0           # halts ALL strategies
```

On trigger: close that strategy's positions, halt that strategy's signal processing for the rest of the session, log state, alert.

### 5.5 Capital allocation (data-driven)

**Decision (per Manny 5/17 review):** Whatever the data supports.

**Initial Phase 1 deployment:** Equal-weight across strategies, half-Kelly per strategy, 1% risk per trade as starting point. This is not a commitment — it's a starting baseline.

**Backtest will inform actual weighting:**
- Sharpe-weighted: strategies with stronger Sharpe get larger weight
- Risk-parity: equal volatility contribution
- Half-Kelly per strategy: per-strategy edge informs per-strategy sizing

Whichever method produces the best out-of-sample portfolio Sharpe in backtest wins. Re-evaluated quarterly from paper/live data.

### 5.6 Configuration (architecture research §10)

Hybrid model:
- **YAML files** for strategy specs (version-controlled, audit trail)
- **Environment variables** for secrets, deployment flags, kill switches
- **Database** for runtime state (positions, attempts, P&L history)

---

## 6. Backtest infrastructure (research-backed)

### 6.1 Framework selection — BACKTEST ONLY (clarified per Manny 5/17)

**Important clarification:** NautilusTrader is **not a replacement for IBKR.** IBKR is the broker (market data, order execution). NautilusTrader is a software framework that runs on our machine and connects to brokers (including IBKR).

What NautilusTrader replaces in our stack: **`simulate.py`** (our homegrown backtest harness). Nothing more.

What NautilusTrader does NOT replace:
- IBKR connection (Nautilus has its own IBKR adapter, but we keep using our existing one for live)
- Alpaca execution (live live)
- `l2_signals.py`, `ibkr_feed.py` (our code, stays)
- The current live bots (`bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, engine bots) — stay

NautilusTrader is open-source (LGPL-3.0), free, runs on our machine. **Cost: $0.**

**Use as backtest engine only.** Build the framework architecture in our own code (per §5). Backtest strategy specs via NautilusTrader. Promote validated specs to the existing live stack.

**Research framework: vectorbt** for parameter sweeps and alpha research. Vectorbt for quick iteration; NautilusTrader for realistic fill modeling and final validation.

**Do NOT use:** Backtrader, Zipline, LEAN. Substantial limitations for our use case.

### 6.2 Data sources

Per backtest research §1, §4:

| Data | Source | Use |
|---|---|---|
| Trade ticks (for VP reconstruction) | Databento `trades` schema OR Alpaca SIP premium | All VP backtests, fill modeling |
| L1 quotes | Databento `bbo` OR Alpaca | Realistic limit fill modeling |
| L2 MBP-10 (for L2-aware strategies) | Databento MBP-10 | Phase 2+ L2 strategy backtests |
| Corporate actions | Databento/Algoseek | Split/dividend adjustments |
| Historical bars (1m) | Existing tick_cache + Databento | All bar-based backtests |

**Databento subscription tier needed:** Standard plan ($199/mo) gives 1 month L2; Plus ($1,399/mo) gives full history. Start with Standard, upgrade if L2 strategies validate.

### 6.3 Fill modeling (backtest research §3)

Per backtest research, the practical fidelity ceiling for our stack is **85-90%** for strategies with 2-30 minute hold times. The remaining 10-15% gap is queue position uncertainty on limit orders.

Implementation:
- Cap orders at 5% of bar volume
- Use price-through (not touch) for confirmed fills
- Discount limit fills 20-40% for queue position when L3 unavailable
- Model slippage as function of position-to-bar ratio

### 6.4 Validation pipeline

```
1. Strategy spec defined in YAML
2. Backtest in NautilusTrader on 6 months of history (out-of-sample)
3. Walk-forward validation (3-month train, 1-month test, rolling)
4. Metrics: Sharpe ≥ 1.5, max drawdown ≤ 10%, profit factor ≥ 1.4, ≥100 trades
5. If pass: paper deploy for 30 sessions
6. If paper passes (criteria below): real-money candidate
7. Real-money: 25% notional for first 10 sessions, then 50%, then 100%
```

### 6.5 Multi-strategy backtest requirements (backtest research §2)

- Shared portfolio state across strategies
- Per-strategy fill tagging
- Identical conflict resolution logic as production
- Walk-forward at portfolio level, not per-strategy in isolation
- Anti-patterns to prevent: survivorship bias, look-ahead bias, multiple-comparison overfitting

---

## 7. Validation criteria (paper-ready, real-money-ready)

### 7.1 Paper-ready (backtest gates a strategy from observe-only to paper)

| Metric | Threshold |
|---|---|
| Backtest Sharpe (6mo OOS) | ≥ 1.5 |
| Backtest max drawdown | ≤ 10% |
| Backtest profit factor | ≥ 1.4 |
| Backtest trade count | ≥ 100 |
| Walk-forward robustness | Performance not concentrated in single quarter |

### 7.2 Real-money-ready (paper gates a strategy from paper to live capital)

| Metric | Threshold |
|---|---|
| Paper sessions | ≥ 30 |
| Paper Sharpe (rolling 20-session) | ≥ 1.2 |
| Paper max drawdown | ≤ 8% |
| Paper-vs-backtest consistency | Sharpe within 0.5 of backtest |
| Zero P0 production incidents in window | required |

### 7.3 Real-money rollout (from validation pass to full capital)

```
First 10 sessions:   25% target notional
Sessions 11-20:      50% target notional
Sessions 21-30:      75% target notional
Session 30+:         100% target notional
```

At any point: -5% drawdown reverts one tier. Two consecutive drawdown reverts pauses strategy.

---

## 8. Build plan (parallel workstreams CC can spawn)

CC works at agent speed. The plan is parallel from the start, not sequential.

### 8.1 Pre-build (this week, in parallel with Monday production checklist)

- **CW1.1:** Cowork synthesizes this design doc → Manny reviews → iterate
- **CW1.2:** Cowork drafts build directive (post-design-approval)
- **CC parallel:** Monday production checklist (gate changes, force-exit validation, L2 verdicts, squeeze N-cap)

### 8.2 Framework infrastructure (post-design-approval, all parallel)

CC spawns parallel agents for:

- **Agent A:** Set up NautilusTrader environment, Databento integration, build the BacktestEngine harness
- **Agent B:** Build framework/ module skeleton (registry, StrategySpec, protocols, level_source plugins for ORB, VWAP, PDH/PDL, round_number)
- **Agent C:** Build confirmation modules (signal_candle, breakout_candle, acceptance, l2_confirm)
- **Agent D:** Build sizing/risk/attribution modules
- **Agent E:** Build universe.py with all filters from §2
- **Agent F:** Migrate squeeze to the framework (squeeze becomes a YAML spec; existing code becomes a level_source plugin)

### 8.3 Phase 1 strategy implementations (parallel after infrastructure)

- **Agent G:** ORB-5 strategy + backtest + validation
- **Agent H:** VWAP Reversion + VWAP Breakout + regime classifier + backtest
- **Agent I:** PDH/PDL fade + PDH/PDL breakout + backtest
- **Agent J:** Round Number strategy + backtest

### 8.4 Phase 2 strategies (after Phase 1 paper-ready)

- **Agent K:** Volume Profile infrastructure (POC/VAH/VAL/HVN/LVN computation from tick data) + 80% Rule + signal candle confirmation + backtest
- **Agent L:** Anchored VWAP + backtest
- **Agent M:** L2 confirmation integration across all strategies (uses Phase 1 L2 work already shipped)

### 8.5 Validation phase (paper)

After backtests pass for each strategy, paper deployment begins. Multiple strategies run simultaneously on the same paper accounts via the strategy registry. Per-strategy attribution preserved in daily reports.

### 8.6 Real-money phase

When a strategy clears the 30-session paper validation, it graduates to real money via the rollout in §7.3. Squeeze is already in this phase as of 6/15.

---

## 9. Timeline (what's actually wall-clock-bound)

**Pacing principle:** Build phases compress to days, not weeks, when CC parallelizes. The bottlenecks are:
- Backtest data fidelity (waiting on subscription approvals if any)
- Paper validation periods (calendar-bound: 30 sessions = ~6 weeks)
- Real-money rollout tiers (calendar-bound: 30 sessions = ~6 weeks)

**Approximate calendar:**

| Date range | Status |
|---|---|
| 5/18-22 | This week: Monday production checklist + design doc approval + build directive |
| 5/26 onward | Framework infrastructure + Phase 1 strategy builds (CC parallel) |
| ~6/1-2 | Phase 1 backtests complete, paper deployment begins for strategies that pass |
| 6/15 | Squeeze real-money cutover (unchanged) |
| 6/15-7/15 | Phase 1 paper validation (30 sessions for each strategy) |
| ~7/15 | Phase 1 strategies that pass paper → real money rollout begins at 25% |
| 6/15 onward | Phase 2 strategies build + backtest in parallel |
| ~7/15-8/15 | Phase 2 paper validation |
| ~8/15+ | Phase 2 real-money rollouts |

Some strategies may validate faster than 30 sessions if performance is strong; others may take longer or fail. The calendar is approximate — the validation gates are the real constraint.

---

## 10. What this design does NOT include

1. **Manual trading lane** — confirmed dropped per Manny
2. **L2 Phase 7 (l2_entry as standalone strategy)** — stays parked. L2 *confirmation* signals integrate with existing strategies via Phase 2 Agent M. A standalone L2-entry strategy is a future consideration after Phase 1 + 2 validate.
3. **Crypto, futures, options** — equities only, US RTH. Future expansion possible.
4. **Overnight holds** — force-exit at 19:55 ET stands per Saturday's P0.2 ship.
5. **ML/AI-generated signals** — none of the strategies use ML. Pure rules. Future consideration after validation infrastructure is mature.
6. **Strategy mutual interaction** — strategies are independent. Future enhancement: strategy-correlation analysis and ensemble methods.

---

## 11. Manny review decisions (5/17) — LOCKED

1. **Universe:** $10-$300 for backtest. Narrow based on data. ✓
2. **Sector exclusions:** No pre-exclusion. Data-driven. ✓
3. **Time windows:** Full RTH 09:30-15:55. Data-driven narrowing. ✓
4. **VIX regime:** Build hooks, default OFF, validate from backtest. ✓
5. **Phase 1 portfolio:** ORB + VWAP + PDH/PDL + Round Number ✓
6. **Capital allocation:** Data-driven, no pre-committed weighting. ✓
7. **Validation thresholds:** Sharpe ≥ 1.5 / 30 paper sessions / 3-tier rollout. Acceptable. ✓
8. **NautilusTrader for BACKTEST ONLY** (clarified — NOT a replacement for IBKR or live stack). $0 cost, open-source. ✓
9. **Databento Standard plan** ($199/mo). ✓
10. **Nothing flagged as missing.** Build set is complete for Phase 1.

---

## 12. Next step

Manny reviews this doc, answers questions §11, flags any architectural concerns. Cowork updates the doc with feedback. Then the build directive lands and CC spawns parallel build agents.

Squeeze production work continues in parallel (Monday checklist, 5/22 evaluation, 6/15 real-money cutover) — unaffected by this design work.

---

## 13. Tone

Five research workstreams in ~30 minutes of parallel work produced ~25,000 words of technical foundation. The framework here is grounded in published academic research (Zarattini ORB study, Caginalp candlestick study, VWAP mean-reversion at 36-sigma significance), production-grade open-source patterns (LEAN, NautilusTrader, pysystemtrade), and rigorous market microstructure literature (LULD mechanics, MM participation curves, ADV thresholds).

The bot we're building is no longer "encode Manny's intuition." It's a portfolio of bot-shaped strategies, each backed by published edge evidence, executing on a universe selected for liquidity and level reliability, with full backtest validation gates before real money.

That's a real foundation. The framework is designed to be extended — new strategies are YAML files, not code rewrites. The build path is parallel. The validation gates are rigorous. Everything that comes next either fits this framework or doesn't.

Your call on the open questions §11. After that, build directive.
