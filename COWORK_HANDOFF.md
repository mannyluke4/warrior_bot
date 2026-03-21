# Claude Cowork Handoff — Warrior Bot Project
## Updated: 2026-03-20 (afternoon)

**Your role**: Strategy analyst and coordinator for a multi-machine trading bot project. You have **full read access to the GitHub repo** — use it to read data, analyze reports, and write directives. The master task list is in `MASTER_TODO.md`. Read it first.

---

## 0. Architecture & Workflow

### The Setup
| Machine | Role | Claude Instances | What It Does |
|---------|------|-----------------|-------------|
| **Mac Mini** | PRIMARY | CC (terminal) + Cowork | Code changes, backtesting, live bot, strategy analysis |
| **MacBook Pro** | REMOTE/BACKUP | CC (VS Code) + Cowork | Remote access, weekend work, backup development |

All share the same GitHub repo (`mannyluke4/warrior_bot`, branch `v6-dynamic-sizing`).
The `.env` file is **gitignored** (contains API keys) — each machine has its own copy.

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
- **Branch**: `v6-dynamic-sizing` (all work happens here)
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
- **Bearish engulfing (BE)**: Detected on 10-second bars, exits full position
- **Topping wicky (TW)**: Detected on 10-second bars, exits full position — BUT suppressed above 1.5R profit (Fix 5, let BE handle runners)
- **Cascading re-entry**: BE/TW exits free capital for re-entry on the next pullback
- **Stop loss**: Hard stop at entry - R, with float-tiered max loss cap (Fix 2)

---

## 3. Current State (as of 2026-03-21)

### ⚠️ P0: sim_start Bug — ALL Megatest Results Invalid
A critical bug in `resolve_precise_discovery()` (commit `efa9b3f`) set `sim_start` to raw premarket times (e.g., 04:00 AM) instead of scanner checkpoint times. 46% of candidates affected (405/873). VERO produces $0 instead of +$18,583 with wrong timing. **All megatest results are faulty and must be re-run.**
- **Directive**: `DIRECTIVE_FIX_SIM_START_BUG.md` (P0, committed)
- **Pipeline audit**: `cowork_reports/pipeline_audit_preliminary.md` (13 potential bugs, 5 critical)
- **Live bot audit**: `cowork_reports/live_bot_audit.md` (19 bugs, 4 must-fix before Monday)
- **VR shelving decision**: V1/V2/V3 standalone results (0 trades) are still valid, but megatest VR=0 needs re-verification with corrected data
- **Next**: CC fixes sim_start + live bot bugs → verification tests → corrected v2 megatest

### Megatest V1 Results (FAULTY — do not use)
| Combo | P&L (FAULTY) | Trades | Status |
|-------|-------------|--------|--------|
| MP only | -$14,339 | 250 | ⚠️ Invalid — 46% wrong sim_start |
| SQ only | +$118,369 | 183 | ⚠️ Invalid |
| MP + SQ | +$130,621 | 298 | ⚠️ Invalid |
| All three | +$124,793 | 329 | ⚠️ Invalid |

### Strategy Fixes Implemented (2026-03-18)
Five data-backed fixes were implemented and validated:

| Fix | What It Does | Impact | Gate |
|-----|-------------|--------|------|
| 1 | Direction-aware continuation hold | +$317 | `WB_CONT_HOLD_DIRECTION_CHECK=1` |
| 2 | Float-tiered max loss cap | +$937 | `WB_MAX_LOSS_R_TIERED=1` |
| 3 | max_loss_hit triggers cooldown (bug fix) | +$916 | `WB_MAX_LOSS_TRIGGERS_COOLDOWN=1` |
| 4 | No re-entry after loss on same symbol | +$1,315 | `WB_NO_REENTRY_ENABLED=1` |
| 5 | TW profit gate — suppress TW above 1.5R | +$12,619 | `WB_TW_MIN_PROFIT_R=1.5` |

### Strategy 2: Squeeze / Breakout (2026-03-19, V2 COMPLETE)
New strategy module captures first-leg momentum moves. Three iterations in one day:
- **V1**: Basic squeeze detector. R-cap blocked all parabolic first legs.
- **Parabolic mode**: Level-based stop fallback when consolidation R exceeds cap. ARTL went from 0 entries to +$6,963.
- **V2 fixes**: HOD gate (blocks bounce entries), separate entry counters (squeeze doesn't block MP), dollar loss cap (catches gap-throughs).
- **Result**: 4-stock total went from $28,162 (MP-only) to $44,605 (+58%).
- **Next**: Full 55-day YTD backtest with squeeze enabled. See `DIRECTIVE_SQUEEZE_YTD_OVERNIGHT.md`.

### Strategy 4: VWAP Reclaim (2026-03-20, SHELVED — pending re-verification)
New strategy module detects Ross's "first 1-min candle to make new high after VWAP reclaim" pattern.
- **V1/V2/V3 standalone tuning**: 27 test runs, 0 VR trades (VALID — used hardcoded sim_start)
- **Megatest all_three**: 0 VR trades (INVALID — sim_start bug may have caused false negatives)
- **Status**: Shelved for now. Will re-verify with corrected v2 megatest data. If still 0 trades at scale, confirm shelving.
- **Gate**: `WB_VR_ENABLED=0` (OFF by default)
- **Design doc**: `DESIGN_VWAP_RECLAIM_DETECTOR.md`

### Scanner Alignment (2026-03-19, IN PROGRESS)
The live scanner was completely broken (0 stocks found in 3 days). Root cause: Alpaca snapshot API returns stale/null data for small caps. Solution: switch to Databento-powered `live_scanner.py` (already built).

Both scanners (live and backtest) are being aligned to use identical Ross Pillar criteria. See `DIRECTIVE_SCANNER_ALIGNMENT.md`.

### Last Validated Backtest
- **49-day MP-only (Jan 2 - Mar 12)**: +$19,072 (+63.6%), profit factor 3.38, 28 trades
- **4-stock squeeze V2 validation**: +$44,605 total across ARTL, VERO, ROLR, SXTC (+58% vs MP-only)
- **VERO regression (squeeze OFF)**: +$18,583 (1 trade, 18.6R — unchanged)
- **ROLR regression (squeeze OFF)**: +$6,444 (1 trade, 6.4R — unchanged)

### Live Config (.env, all fixes enabled, squeeze LIVE in paper)
```
WB_MODE=PAPER
WB_EXIT_MODE=signal
WB_RISK_DOLLARS=1000
WB_MAX_NOTIONAL=50000
WB_CLASSIFIER_ENABLED=1
WB_EXHAUSTION_ENABLED=1
WB_CONTINUATION_HOLD_ENABLED=1
WB_PILLAR_GATES_ENABLED=1
WB_ARM_EARLIEST_HOUR_ET=7
WB_CONT_HOLD_DIRECTION_CHECK=1
WB_MAX_LOSS_R_TIERED=1
WB_MAX_LOSS_R_ULTRA_LOW_FLOAT=0
WB_MAX_LOSS_R_LOW_FLOAT=0.85
WB_MAX_LOSS_TRIGGERS_COOLDOWN=1
WB_NO_REENTRY_ENABLED=1
WB_TW_MIN_PROFIT_R=1.5
WB_SQUEEZE_ENABLED=1          # LIVE in paper (2026-03-19)
WB_SQ_PARA_ENABLED=1
WB_SQ_NEW_HOD_REQUIRED=1
WB_SQ_MAX_LOSS_DOLLARS=500
# VR (backtest validation pending — NOT live yet)
# WB_VR_ENABLED=1
```

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
| `YTD_V2_BACKTEST_RESULTS.md` | Latest 49-day backtest results |
| `ALL_FIXES_BACKTEST_RESULTS.md` | Validation of all 5 fixes |

---

## 8. Manny's Working Style

- **Data-driven**: Always dig into the data before proposing fixes. No guessing.
- **Deep analysis**: Break everything down on a detailed technical level. Find the specific root cause.
- **Precise fixes**: Act on specific findings, not general context. Don't patch something that might catch a big trade.
- **One thing at a time**: Test each change individually before combining.
- **Ross methodology**: The bot should trade like Ross Cameron. His recaps are the benchmark.
- **Organized**: Keep `MASTER_TODO.md` current. Nothing should be forgotten between sessions.

---

*Handoff updated: 2026-03-21 | P0 sim_start bug found, megatest results invalid, directive + audits committed for CC*
