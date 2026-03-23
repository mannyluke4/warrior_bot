# Claude Cowork Handoff — Warrior Bot Project
## Updated: 2026-03-23 (afternoon)

**Your role**: Strategy analyst and coordinator for a multi-machine trading bot project. You have **full read access to the GitHub repo** — use it to read data, analyze reports, and write directives. The master task list is in `MASTER_TODO.md`. Read it first.

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

**Next Step:** Deep analysis of WHY each missed stock wasn't found — which specific scanner filter rejected each one. Report in progress.

**Key Reports:**
- `cowork_reports/2025-01_missed_stocks_backtest_results.md` — Full backtest results
- `cowork_reports/missed_stocks_backtest_plan.md` — Per-stock miss log (89 entries)
- `DIRECTIVE_JAN2025_MISSED_STOCKS_BACKTEST.md` — Backtest directive (COMPLETED)

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

---

## 8. Manny's Working Style

- **Data-driven**: Always dig into the data before proposing fixes. No guessing.
- **Deep analysis**: Break everything down on a detailed technical level. Find the specific root cause.
- **Precise fixes**: Act on specific findings, not general context. Don't patch something that might catch a big trade.
- **One thing at a time**: Test each change individually before combining.
- **Ross methodology**: The bot should trade like Ross Cameron. His recaps are the benchmark.
- **Organized**: Keep `MASTER_TODO.md` current. Nothing should be forgotten between sessions.

---

*Handoff updated: 2026-03-23 | Scanner coverage is #1 priority (7.7x multiplier proven). Ross Exit V3 CUC fix COMPLETED. Jan 2025 missed stocks backtest COMPLETED (+$42,818 potential). Live bot on main with ross exit ON.*
