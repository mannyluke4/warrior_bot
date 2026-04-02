# CC Handoff — April 1, 2026

## SITUATION: V2 has never taken a trade. This is priority #1.

Today was the clearest demonstration yet. CYCN ran 300-400% on a merger catalyst. Ross made $7,400 on it. Our bot watched it go from $4.22 to $8.47 and did nothing. The squeeze detector sat at IDLE the entire session.

On top of that:
- IB Gateway failed to auto-start (36 retries, 180s timeout) despite CC manually starting at 2:30 AM ET
- live_scanner.py crashed on a Databento date boundary bug (EQUS.SUMMARY not available for current date)
- Bot was manually restarted at 08:38 ET, missing the entire premarket golden window

**Manny's words: "The fact that we haven't taken a single winning trade since project start, and v2 hasn't taken a trade period don't inspire confidence right now."**

---

## TODAY'S LOG ANALYSIS (2026-04-01)

### Infrastructure Failures
1. **daily_run.sh**: IB Gateway port 4002 never came up. 36 attempts over 180 seconds -> FATAL abort at 02:07 MT (04:07 ET). The bot didn't auto-start.
2. **live_scanner.py**: Databento EQUS.SUMMARY dataset only available through March 31. Scanner requested end=2026-04-01, got 422 data_end_after_available_end, crashed immediately.
3. **Manual restart at 08:38 ET**: Bot came up, IBKR catchup scan found 44 symbols, 4 passed filters (CYCN, BCG, RENX, ELAB). KIDZ re-subscribed via Databento bridge.

### What Happened With Each Stock
- **CYCN** ($4.22 -> $8.47, +100%): Squeeze detector stayed IDLE entire session. Never primed, never armed. Stock stair-stepped up gradually — no single explosive volume bar to trigger squeeze prime. Ross made $7,400.
- **RENX** ($2.30 -> $3.48 -> $2.40): SQ_PRIMED twice but SQ_NO_ARM: para_invalid_r (entry/stop too close). Ross made ~$600 then gave it back.
- **ELAB** ($7.19 -> $8.44 -> $7.00): Multiple SQ_REJECT: not_new_hod. Never primed.
- **BCG** ($3.08 -> $3.24 -> $2.59): Quiet. No squeeze activity.
- **KIDZ** ($2.85 -> $3.41): Low volume, no setup.

### Zero trades. Zero P&L.

---

## PRIORITY REWRITE

### P0-A: IB Gateway Startup Reliability
The bot must start reliably every single day without manual intervention.

1. Increase Gateway timeout from 180s to 300s (or exponential backoff)
2. Add retry loop: kill Gateway + IBC and try fresh launch if first attempt fails
3. Add health-check heartbeat: log loudly if bot isn't connected by 04:15 ET
4. Investigate WHY Gateway took >180s today — check ibc/logs/ on Mac Mini

### P0-B: Databento Scanner Date Bug
Trivial fix. In live_scanner.py load_prev_close(), request end = today - 1 day instead of end = today. Previous close data is always from the prior trading day.

### P0-C: CYCN Pattern Gap → L2 / Tape Reading Integration
CYCN stair-stepped $4.22→$8.47 with no single explosive bar (vol_ratio max 1.8x vs 3.0x required). The squeeze detector correctly classified this as "not a squeeze" — this is a tape-reading trade, the kind Ross makes using Level 2 and Time & Sales.

**Manny's direction:** "If it's a choppy stock that the bot isn't tuned to capture, then that's what it is. Ross himself reads the tape and uses level 2, two things that the bot does not utilize, even though we are paying for level 2 access."

**Critical discovery: L2 infrastructure ALREADY EXISTS in archive.**

The bot already did a full 137-stock L2 study (March 2, 2026) — see `archive/docs/L2_FULL_STUDY_RESULTS.md`. Key findings:
- Raw L2 v3: -$7,575 overall, BUT +$6,526 excluding 2 micro-float outliers (GWAV, BNAI)
- **L2 helps:** float ≥5M (+$172/stock avg), stocks discovered after 8am, positive gap stocks
- **L2 hurts:** float <5M (-$168/stock avg), pre-8am stocks, negative gap stocks
- **Recommendation:** `WB_L2_MIN_FLOAT_M=5` would flip L2 from -$7,575 to ~+$5,000 net
- `l2_bearish_exit` is the dominant mechanism (fired on 36 stocks)

**Archived code (ready to revive):**
- `archive/scripts/l2_signals.py` — L2SignalDetector: imbalance, bid stacking, large orders, ask thinning
- `archive/scripts/l2_entry.py` — L2EntryDetector: enters when book shows buyers stacking BEFORE breakout
- `databento_feed.py` — Already fetches MBP-10 (10 bid/ask levels) from Databento, caches as .dbn.zst
- `trade_manager.py` lines 2821-2860 — Already handles `l2_bearish` and `l2_ask_wall` signals (plumbing exists!)
- `bot_ibkr.py` — Missing link: no `reqMktDepth()` call, no L2 subscription

**The gap:** The March 2 study ran L2 against the **micro-pullback** detector. Squeeze V1 became primary March 24. L2 has NOT been evaluated against squeeze trades yet.

**Recommended path (discuss with Manny):**
1. P1: Re-run L2 study against squeeze V1 config with float ≥5M gate
2. If positive: Wire `reqMktDepth()` into bot_ibkr.py → feed L2SignalDetector → generate signals for trade_manager.py
3. Separately evaluate L2EntryDetector for CYCN-type "stair-step" stocks

**Manny also confirmed:** Premium Databento subscription has historical L2 data — L2 strategies CAN be backtested (not just observed live).

---

## P1: SQUEEZE V2 PLANNING (Build After P0 Ships)

Full plan in `SQUEEZE_V2_PLAN.md`. Summary:

**Entry improvements:** candle-over-candle confirmation, doji/exhaustion gate, intra-bar ARM, trend filter
**Exit improvements:** intra-bar candle shape reading, candle-under-candle, L2 bearish exits (float ≥5M gate)
**L2 integration:** Re-evaluate March 2 L2 study against squeeze V1, wire reqMktDepth into bot_ibkr if positive

Every feature is individually gated (OFF by default), backtested against V1 baseline (+$19,832), and only combined after independent validation. See plan for full backtest methodology.

---

## SECONDARY PRIORITIES
- Unified Scanner V3: Directive in DIRECTIVE_UNIFIED_SCANNER_V3.md
- Scaling In/Out: Biggest multiplier but requires bot to take trades first

## REGRESSION TARGETS
```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$15,692

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

## GIT
- git pull first
- git push after regression passes
- Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

---

## 0. Architecture & Workflow

### The Setup
| Machine | Role | Claude Instances | What It Does |
|---------|------|-----------------|-------------|
| **Mac Mini** | PRIMARY | CC (terminal) + Cowork | Code changes, backtesting, live bot, strategy analysis |
| **MacBook Pro** | REMOTE/BACKUP | CC (VS Code) + Cowork | Remote access, weekend work, backup development |

All share the same GitHub repo (`mannyluke4/warrior_bot`, branch `main`).
The `.env` file is **gitignored** (contains API keys) — each machine has its own copy.
**NOTE (2026-03-23):** Branch switched from `v6-dynamic-sizing` to `main`. v6 was 22 commits behind main with 0 unique commits. Mac Mini daily_run.sh updated.

### Roles & Boundaries

**Cowork (you) — Strategist / Coordinator**
- READ any file in the repo
- WRITE directive `.md` files into the repo folder
- ANALYZE reports, trade logs, backtest results, .env config
- PLAN next optimizations, identify bugs, prioritize work
- UPDATE `MASTER_TODO.md` after each session
- DO NOT edit `.py` files, `.env`, or any code — that's CC's job
- DO NOT run backtests or simulations — that's CC's job
- DO NOT commit or push to git — that's CC's job

**CC (on whichever machine) — Developer / Operator**
- EXECUTE directives from Cowork (code changes, backtests, analysis)
- EDIT all `.py` files, `.env`, config files
- RUN backtests, simulations, regressions
- COMMIT and PUSH code changes to the repo
- PRODUCE reports and commit them
- RUN the live bot daily via cron (Mac Mini)

**Rule**: Cowork reads, CC writes. Cowork's output is always a directive `.md` file, never a code edit.

### Key Documents
| File | Purpose |
|------|---------|
| `MASTER_TODO.md` | **Single source of truth** for all open work. Read this first. |
| `COWORK_HANDOFF.md` | This file — project context for new Cowork sessions |
| `CLAUDE.md` | Project instructions for Claude Code instances |
| `.env` | All config knobs — read before suggesting changes |

---

## 1. What This Project Is

A Python day trading bot that detects micro-pullback setups on small-cap stocks and executes paper trades via Alpaca API. Built to replicate Ross Cameron's (Warrior Trading) methodology.

- **Owner**: Manny — day trader, prefers consistent $200-500 daily hits, methodical approach
- **Stage**: Paper trading on Alpaca with $30K account
- **Branch**: `main` (switched from `v6-dynamic-sizing` on 2026-03-23)
- **Repo**: GitHub, `mannyluke4/warrior_bot`

---

## 2. How the Bot Works

### Detection Flow
1. **Scanner** (`live_scanner.py` via Databento) — streams all US equities, filters by Ross's 5 Pillars: gap ≥10%, RVOL ≥2x, price $2-$20, float <10M
2. **Seed bars** (4AM-start) build EMA9/VWAP/PM_HIGH context
3. **1-minute bars** → `MicroPullbackDetector` (state machine: IMPULSE → PULLBACK → ARM)
4. **Armed setups** trigger on tick price breaking trigger_high
5. **10-second bars** detect exit patterns (bearish engulfing, topping wicky)
6. **Classifier** categorizes stock at 5 minutes and adjusts exit thresholds

### Key Files
| File | Purpose |
|------|---------|
| `bot.py` | Live bot (Alpaca websocket, runs on Mac Mini) |
| `simulate.py` | Backtesting engine (tick + bar mode) — includes squeeze exit/wiring |
| `micro_pullback.py` | Core 1-minute detector state machine |
| `squeeze_detector.py` | Strategy 2: Squeeze/breakout detector (IDLE → PRIMED → ARMED) |
| `vwap_reclaim_detector.py` | Strategy 4: VWAP Reclaim detector (IDLE → BELOW_VWAP → RECLAIMED → ARMED) |
| `trade_manager.py` | Order execution + exit management + filters |
| `bars.py` | TradeBarBuilder (VWAP/HOD/PM tracking) |
| `live_scanner.py` | Databento real-time scanner (writes watchlist.txt) |
| `scanner_sim.py` | Backtest scanner (generates scanner_results/*.json) |
| `stock_filter.py` | Legacy live scanner (Alpaca snapshots — BROKEN, being replaced) |
| `run_ytd_v2_backtest.py` | 55-day YTD batch backtest runner |
| `.env` | ALL config knobs (env vars control everything) |

### Exit Strategy
- `exit_mode = "signal"` — no fixed take-profit, let patterns manage exits
- **When `WB_ROSS_EXIT_ENABLED=1`**: 1m candle signals replace 10s BE/TW exits. Signal hierarchy: Tier 1 warnings (doji/topping tail → 50% partial), Tier 2 confirmed (gravestone/shooting star/CUC → 100%), Tier 3 backstops (VWAP/EMA20/MACD → 100%). Structural trail = low of last green 1m candle.
- **When `WB_ROSS_EXIT_ENABLED=0` (current live)**: 10s BE/TW exits, TW suppressed above 1.5R, cascading re-entry
- **Stop loss**: Hard stop at entry - R, with float-tiered max loss cap (Fix 2)

---

## 3. Current State (as of 2026-03-23)

### #1 PRIORITY — Scanner Coverage Improvement

**The Problem:** Bot found only 5/68 (7.4%) of Ross's January 2025 tickers. Scanner coverage is the single biggest bottleneck.

**Proof It Matters — January 2025 Missed Stocks Backtest (COMPLETED 2026-03-23):**
- Backtested all 41 Ross-traded tickers from Jan 2025 against current bot config
- **Total potential P&L: +$42,818** (vs $5,543 actual — **7.7x multiplier**)
- 25/41 stocks had data AND trades; 88% stock-level profitability
- Bot BEATS Ross on all 3 of his loss days (OST: Ross -$3K → Bot +$6,876)
- SQ is doing virtually all the work; MP dormant on this dataset
- 10 tickers had no Databento data; 6 had data but 0 trades

**Scanner Miss Categories (from missed_stocks_backtest_plan.md):**
- 45% scanner never found at all (13 stocks) — THIS IS THE MAIN TARGET
- 17% found but didn't trade (5) — entry logic, not scanner
- 10% exit gap (3) — exit timing, not scanner
- 10% sympathy/thematic (3) — hard to detect programmatically
- 7% mid-morning movers (2) — need continuous rescan
- 7% unknown-float (2) — missing float data
- 3% timing (1) — scan timing window

**Scanner Fixes V1 — ALL 6 ITEMS COMPLETED (commit `6a91afe`, `7e2d7f0`):**
1. ✅ Enable unknown-float trading (`WB_ALLOW_UNKNOWN_FLOAT=1`) — safety gates: gap≥50%, pm_vol≥1M, rvol≥10x, 50% notional cap
2. ✅ Fix continuous rescan — cumulative 4AM→checkpoint volume, RVOL inline calc, gap 5% for RVOL≥10x
3. ✅ Rename "Profile X" → "unknown-float" across entire codebase (backward compat for old scanner JSONs)
4. ✅ SEC EDGAR as Tier 5 float fallback — free, 10 req/s, CIK map + XBRL API
5. ✅ Float cache invalidation — clears stale None entries on load, forces re-lookup
6. ✅ Alpha Vantage as Tier 6 float fallback — `WB_ALPHA_VANTAGE_API_KEY` env var, 25 calls/day free

**Float lookup chain (updated):** KNOWN_FLOATS → float_cache → FMP → yfinance → SEC EDGAR → Alpha Vantage

**Free-tier recovery model:** +$15-17K/month potential at zero additional cost.

**OTC coverage deferred:** Polygon $199/mo + IBKR $18/mo would cover ~10 missing OTC tickers. Manny declined for now.

**Regression PASSED:** VERO +$18,583 ✅, ROLR +$6,444 ✅

**Key Reports:**
- `cowork_reports/2025-01_missed_stocks_backtest_results.md` — Full backtest results
- `cowork_reports/missed_stocks_backtest_plan.md` — Per-stock miss log (89 entries)
- `cowork_reports/2026-03-23_scanner_gap_analysis.md` — Per-stock rejection analysis
- `scanner_deep_dive_report.md` — Perplexity data feed + float source research
- `DIRECTIVE_JAN2025_MISSED_STOCKS_BACKTEST.md` — Backtest directive (COMPLETED)
- `DIRECTIVE_SCANNER_FIXES_V1.md` — Scanner fixes directive (ALL 6 ITEMS COMPLETED)

### Ross Exit System — V2 Backtested, V3 CUC Fix COMPLETED

**Ross Exit V2 YTD Results (55 days, Jan 2 - Mar 20 2026):**

| Metric | Baseline (Ross Exit OFF) | V2 (Ross Exit ON) | Delta |
|--------|--------------------------|---------------------|-------|
| Total P&L | **+$25,709** | +$14,910 | **-$10,799** |
| Total Trades | 33 | 28 | -5 |
| Win Rate | 52% | 37% | -15pp |
| Max Drawdown | $3,277 | $1,804 | -$1,473 (better) |

**V3 CUC Fix Results (COMPLETED 2026-03-23):**
- Config C (MinBars=5): +$16,959, best single CUC fix (+$2,049 vs V2)
- Config D (FloorR=2): +$15,924
- Config E (Both): +$16,786 — CUC exits reduced to 0
- **Conclusion:** CUC tuning alone cannot close the gap. The sq_target_hit architecture issue dominates.
- **Decision:** Ross exit is ON in live (.env), but scanner improvement is higher leverage than further exit tuning.

**Key Reports:**
- `cowork_reports/ross_exit_video_analysis.md` — Ross Cameron exit methodology deep dive
- `cowork_reports/ross_exit_analysis.md` — 19 daily recaps reverse-engineered
- `cowork_reports/2026-03-23_ytd_ross_exit_v2_comparison.md` — YTD V2 results
- `cowork_reports/2026-03-23_ross_exit_v3_variations.md` — V3 variation design + modeling
- `cowork_reports/2026-03-23_v3_cuc_comparison.md` — V3 CUC comparison results

### Live Bot Audit (2026-03-23)

Mac Mini was running `v6-dynamic-sizing` branch (22 commits behind main). `daily_run.sh` updated to pull/push `main`. Full audit directive: `DIRECTIVE_LIVE_BOT_AUDIT_2026_03_23.md`.

Issues found on 2026-03-23:
- Alpaca websocket failure (99,934 failed retries, 0 trades)
- Scanner divergence: live (ANNA, ARTL, SUNE) vs sim (UGRO, AHMA, WSHP) — zero overlap
- Recommendation: Databento migration for data feed

**Live Config (.env on Mac Mini):**
```
WB_ROSS_EXIT_ENABLED=0         # OFF — V2 showed -$10,799 vs baseline
WB_MP_ENABLED=0                # OFF by default (gated 2026-03-22)
WB_SQUEEZE_ENABLED=1           # Primary strategy
WB_PILLAR_GATES_ENABLED=1
WB_CLASSIFIER_ENABLED=1
```

### Regression Targets
- VERO 2026-01-16: **+$18,583** (with `WB_MP_ENABLED=1`)
- ROLR 2026-01-14: **+$6,444** (with `WB_MP_ENABLED=1`)
- Note: `WB_MP_ENABLED=1` required since Item 1 (2026-03-22) gated MP off by default

---

## 4. Critical Rules

### DO NOT:
- Disable exhaustion filter — dynamic scaling handles cascading stocks correctly
- Set max loss cap below 0.75R on any tier — kills ROLR (+$6,444 winner dips to -0.60R)
- Suppress BE exits in signal mode — they enable cascading re-entry AND now catch runners that TW used to cut short
- Change behavior without an env var gate (OFF by default)
- Remove TW entirely — it saves $3,131 on trades below 1.5R

### ALWAYS:
- Use `--ticks --tick-cache tick_cache/` for backtests
- Backtest window: 07:00-12:00 ET
- Test changes on multiple stocks before declaring them good
- Gate new features behind env vars (OFF by default)
- Run VERO regression after any change: must be +$18,583 (updated from +$9,166 after Fix 5)
- Read `MASTER_TODO.md` at the start of every session
- Update `MASTER_TODO.md` at the end of every session

---

## 5. Backtest Infrastructure

### Gold Standard: Cached Tick Backtest
- **240 stock/date pairs**, 33.7M ticks, 202 MB in `tick_cache/`
- **49 trading days**: Jan 2 - Mar 12, 2026
- **Deterministic replay** — same data, same results every time
- **Runner**: `run_ytd_v2_backtest.py` — ranks top 5 stocks/day, sims each, tracks equity
- **Always use**: `--ticks --tick-cache tick_cache/`

### Regression Targets (as of 2026-03-19)
- VERO 2026-01-16: **+$18,583** (1 trade, 18.6R — TW suppressed at 9.2R, BE exits at 18.6R)
- ROLR 2026-01-14: **+$6,444** (1 trade, 6.4R — TW suppressed at 3.2R, BE exits at 6.4R)

---

## 6. Strategy Profile Roadmap

The bot currently has ONE strategy: micro-pullback (IMPULSE → PULLBACK → ARM → breakout). Ross Cameron uses 5-6 different setups on any stock. ARTL analysis (Mar 18) showed the bot captured $922 while Ross made $9,653 — a 90% gap because the bot only has the pullback setup.

**Strategy modules** (each independent, coexisting):
1. **Micro Pullback** — LIVE in paper, being refined
2. **Squeeze / Breakout** — LIVE in paper (V2, 2026-03-19)
3. **Dip-Buy** — planned (not started)
4. **VWAP Reclaim** — IMPLEMENTED, needs CC validation backtest (2026-03-20)
5. **Curl / Extension** — planned (not started)

Each module will have its own state machine, entry/exit rules, and reset logic. A TW reset in the pullback module won't affect the squeeze module.

See `MASTER_TODO.md` for detailed task lists per strategy.

---

## 7. Key Reports in Repo

| File | What It Contains |
|------|-----------------|
| `MASTER_TODO.md` | **All open work items** — read this first |
| `DIRECTIVE_SCANNER_ALIGNMENT.md` | Scanner unification plan (in progress) |
| `DIRECTIVE_STRATEGY_IMPROVEMENTS_V1.md` | Fixes 1-5 detailed analysis |
| `TW_EXIT_ANALYSIS_REPORT.md` | TW is net -$9,694 — led to Fix 5 |
| `TW_CHARACTERISTICS_REPORT.md` | R-mult at exit is the key discriminator |
| `WINNER_EXIT_ANALYSIS_REPORT.md` | Money left on table analysis |
| `VOLUME_PRESSURE_REPORT.md` | Buy/sell ratio at entry time |
| `ARTL_METHODOLOGY_GAP_ANALYSIS.md` | Bot vs Ross: 90% gap, 5 methodology gaps |
| `STRATEGY_2_SQUEEZE_DESIGN.md` | Squeeze strategy full design spec — all 5 decisions locked |
| `DIRECTIVE_SQUEEZE_FIXES_V2.md` | V2 conflict fixes (HOD gate, counters, dollar cap) |
| `DESIGN_VWAP_RECLAIM_DETECTOR.md` | Strategy 4 full design spec |
| `DIRECTIVE_VWAP_RECLAIM_VALIDATION.md` | VR V1 validation directive (0 trades) |
| `DIRECTIVE_VR_TUNING_V2.md` | VR V2 wider thresholds (0 trades) |
| `DIRECTIVE_VR_TUNING_V3.md` | VR V3 code fix + R-cap $1.00 + 20% severe_loss |
| `CHNR_2026-03-19_METHODOLOGY_GAP_ANALYSIS.md` | CHNR gap analysis — 2/3 trades were VR |
| `SCANNER_DATA_QUALITY_REPORT.md` | Why live scanner finds 0 stocks |
| `YTD_V2_BACKTEST_RESULTS.md` | Latest 55-day YTD backtest results (Ross Exit A/B) |
| `ALL_FIXES_BACKTEST_RESULTS.md` | Validation of all 5 fixes |
| `DIRECTIVE_ROSS_EXIT_V3_CUC_FIX.md` | V3 CUC fix directive for CC |
| `DIRECTIVE_LIVE_BOT_AUDIT_2026_03_23.md` | Mac Mini live bot audit directive |
| `DIRECTIVE_YTD_2026_ROSS_EXIT_V2.md` | YTD A/B backtest directive (completed) |
| `DIRECTIVE_SCANNER_FIXES_V1.md` | Scanner fixes V1 — all 6 items COMPLETED |
| `RESEARCH_DIRECTIVE_DATA_FEEDS_AND_FLOAT_SOURCES.md` | Perplexity research directive (completed) |
| `scanner_deep_dive_report.md` | Perplexity output — data feed + float source research |
| `cowork_reports/2026-03-23_scanner_gap_analysis.md` | Per-stock scanner miss analysis (34 stocks, 5 categories) |

---

## 8. Manny's Working Style

- **Data-driven**: Always dig into the data before proposing fixes. No guessing.
- **Deep analysis**: Break everything down on a detailed technical level. Find the specific root cause.
- **Precise fixes**: Act on specific findings, not general context. Don't patch something that might catch a big trade.
- **One thing at a time**: Test each change individually before combining.
- **Ross methodology**: The bot should trade like Ross Cameron. His recaps are the benchmark.
- **Organized**: Keep `MASTER_TODO.md` current. Nothing should be forgotten between sessions.

---

*Handoff updated: 2026-04-01 | P0 directive: Gateway retry + Databento date fix + candle exits port. SQUEEZE_V2_PLAN.md created with full entry/exit/L2 improvement roadmap. V1 baseline = +$19,832. All V2 features gated OFF by default, backtest-first.*
