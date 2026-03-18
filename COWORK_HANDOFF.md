# Claude Cowork Handoff — Warrior Bot Project
## Updated: 2026-03-18

**Your role**: Replace Perplexity as the strategy analyst and directive writer for a multi-machine trading bot project. You have **full read/write access to the GitHub repo** — use it to read data, push directives, and coordinate work across machines.

---

## 0. Multi-Machine Architecture & Workflow

### The Setup
| Machine | Role | Claude Instance | What It Does |
|---------|------|----------------|-------------|
| **MacBook Pro** | Development | Claude Code (VS Code) | Backtesting, code changes, analysis |
| **Mac Mini** | Production | Claude Code (terminal) | Runs live bot daily, pushes logs/reports |
| **MacBook Pro** | Strategy | Claude Cowork (you) | Reads repo, writes directives, coordinates |

All three share the same GitHub repo (`mannyluke4/warrior_bot`, branch `v6-dynamic-sizing`).
The `.env` file is **gitignored** (contains API keys) — each machine has its own copy that must be synced manually via directives.

### Roles & Boundaries (IMPORTANT — prevents conflicts)

**Cowork (you) — Strategist / Coordinator**
- READ any file in the repo (`/Users/mannyluke/warrior_bot/`)
- WRITE directive `.md` files and save to `~/Downloads/`
- ANALYZE reports, trade logs, backtest results, .env config
- PLAN next optimizations, identify bugs, prioritize work
- DO NOT edit `.py` files, `.env`, or any code — that's CC's job
- DO NOT run backtests or simulations — that's CC's job
- DO NOT commit or push to git — that's CC's job

**MacBook Pro CC (VS Code) — Developer**
- EXECUTE directives from Cowork (code changes, backtests, analysis)
- EDIT all `.py` files, `.env`, config files
- RUN backtests, simulations, regressions
- COMMIT and PUSH code changes to the repo
- PRODUCE reports (backtest results, analysis) and commit them
- DO NOT write strategy directives — that's Cowork's job

**Mac Mini CC (terminal) — Production Operator**
- RUN the live bot daily via cron
- PUSH daily reports (`DAILY_REPORT_*.md`), weekly reports, trade logs
- EXECUTE Mac Mini-targeted directives (.env sync, bot config, production fixes)
- DO NOT run backtests or make strategy decisions

**Why this matters**: Cowork and MacBook Pro CC share the same filesystem. If both edit files at the same time, changes will collide. The rule is simple: **Cowork reads, CC writes.** Cowork's output is always a directive `.md` file, never a code edit.

### Communication Flow
```
                    ┌─────────────┐
                    │   Cowork    │
                    │  (you)      │
                    │  strategist │
                    └──────┬──────┘
                           │
                    reads repo / writes directives
                           │
              ┌────────────┼────────────┐
              ▼                         ▼
     ┌────────────────┐       ┌────────────────┐
     │  MacBook Pro   │       │   Mac Mini     │
     │  CC (dev)      │       │  CC (prod)     │
     │  backtests     │       │  live bot      │
     └────────────────┘       └────────────────┘
              │                         │
              └────── GitHub repo ──────┘
                   (shared state)
```

### Directive Targeting
Every directive you write MUST specify its target at the top:

```markdown
**TARGET**: 🖥️ MacBook Pro CC | 🖥️ Mac Mini CC | 🖥️ Both
```

Use these labels:
- **🖥️ MacBook Pro CC** — backtesting, code analysis, strategy experiments
- **🖥️ Mac Mini CC** — .env changes, live bot config, production fixes
- **🖥️ Both** — code changes that need to be on HEAD (committed + pushed)

### Status Updates via Repo
Each CC instance reports status by committing files to the repo:
- **Daily reports**: `DAILY_REPORT_YYYYMMDD.md` (Mac Mini pushes after each session)
- **Backtest reports**: `*_REPORT*.md` (MacBook Pro pushes after experiments)
- **Weekly reports**: `WEEKLY_BACKTEST_REPORT_*.md` (Mac Mini runs weekly backtests)

**You should read these files to stay informed.** Pull the latest before writing new directives.

### Your Workflow
1. Read reports, logs, trade data in the repo at `/Users/mannyluke/warrior_bot/`
2. Analyze and identify next optimization / fix
3. Write a directive `.md` file with clear TARGET label
4. Save to `~/Downloads/` — Manny will tell the target CC to check Downloads
5. After CC executes, read the resulting report from the repo
6. Iterate

---

## 1. What This Project Is

A Python day trading bot that detects micro-pullback setups on small-cap stocks and executes paper trades via Alpaca API. Built to replicate Ross Cameron's (Warrior Trading) methodology.

- **Owner**: Manny — day trader, prefers consistent $200-500 daily hits, methodical approach
- **Stage**: Paper trading on Alpaca with $30K account
- **Branch**: `v6-dynamic-sizing` (all work happens here)
- **Runs on**: Mac Mini (automated daily via cron) + MacBook Pro (development)
- **Repo**: GitHub, `mannyluke4/warrior_bot`

---

## 2. How the Bot Works (Architecture)

### Detection Flow
1. **Scanner** (`stock_filter.py`, `live_scanner.py`) — Scans market at 4AM ET, filters by Ross's 5 Pillars: gap >=10%, RVOL >=2x, price $2-$20, float <10M shares
2. **Seed bars** (4AM-start) build EMA9/VWAP/PM_HIGH context
3. **1-minute bars** → `MicroPullbackDetector` (state machine: IMPULSE → PULLBACK → ARM)
4. **Armed setups** trigger on tick price breaking trigger_high
5. **10-second bars** detect exit patterns (bearish engulfing, topping wicky)
6. **Classifier** (when enabled) categorizes stock at 5 minutes and adjusts exit thresholds

### Key Files
| File | Purpose |
|------|---------|
| `bot.py` | Live bot (Alpaca websocket, runs on Mac Mini) |
| `simulate.py` | Backtesting engine (tick + bar mode) |
| `micro_pullback.py` | Core 1-minute detector state machine |
| `trade_manager.py` | Order execution + exit management + filters |
| `bars.py` | TradeBarBuilder (VWAP/HOD/PM tracking) |
| `stock_filter.py` | Stock filtering and ranking for live bot |
| `run_ytd_v2_backtest.py` | 49-day YTD batch backtest runner |
| `run_ytd_v2_profile_backtest.py` | Profile system A/B backtest runner |
| `.env` | ALL config knobs (env vars control everything) |

### Exit Strategy
- `exit_mode = "signal"` — no fixed take-profit, let patterns manage exits
- **Bearish engulfing (BE)**: Detected on 10-second bars, exits full position
- **Topping wicky (TW)**: Detected on 10-second bars, exits full position
- **Cascading re-entry**: BE/TW exits free capital for re-entry on the next pullback (this is the core edge)
- **Stop loss**: Hard stop at entry - R (now capped at 0.75R via WB_MAX_LOSS_R)

---

## 3. Current State of the Bot

### Live Config (.env as of 2026-03-18)
```
WB_MODE=PAPER
WB_EXIT_MODE=signal
WB_CLASSIFIER_ENABLED=1
WB_EXHAUSTION_ENABLED=1         # Dynamic scaling handles big runners
WB_CONTINUATION_HOLD_ENABLED=1
WB_CONT_HOLD_5M_TREND_GUARD=1
WB_MAX_NOTIONAL=50000
WB_MAX_LOSS_R=0.75              # Tightened from 2.0 (exit optimization)
WB_PILLAR_GATES_ENABLED=1       # Ross Pillar entry-time gates
WB_BAIL_TIMER_ENABLED=1         # Exit if not profitable in 5 minutes
WB_BAIL_TIMER_MINUTES=5
WB_GIVEBACK_HARD_PCT=50         # Walk away at 50% giveback of daily peak
WB_MAX_CONSECUTIVE_LOSSES=3     # Stop after 3 consecutive losses
WB_WARMUP_SIZE_PCT=25           # Start at 25% size until $500 daily profit
WB_RISK_DOLLARS=1000
WB_MIN_GAP_PCT=10               # Tightened scanner (was 5%)
WB_MAX_FLOAT=10                 # Tightened (was 50M)
WB_MIN_REL_VOLUME=2.0           # Tightened (was 1.5x)
```

---

## 4. Backtest Infrastructure

### Gold Standard: Cached Tick Backtest
- **240 stock/date pairs**, 33.7M ticks, 202 MB in `tick_cache/`
- **49 trading days**: Jan 2 - Mar 12, 2026
- **Deterministic replay** — same data, same results every time
- **Runner**: `run_ytd_v2_backtest.py` — ranks top 5 stocks/day, sims each, tracks equity
- **Always use**: `--ticks --tick-cache tick_cache/`

### Results Timeline
| Date | Config | P&L | Return | Notes |
|------|--------|-----|--------|-------|
| Mar 16 | Baseline (flat risk, no opts) | +$6,467 | +21.6% | Config B, no score gate |
| Mar 17 | Profile system retest | +$7,310 | +24.4% | Profile A/B split helped |
| Mar 17 | Exit optimizations combined | +$7,580 | +25.3% | Mid-float cap + 0.75R loss cap |

### Key Numbers (Combined Optimized, Config B)
- 28 trades, 10 wins (36%), profit factor 2.03
- Peak equity: ~$43K (Jan 16, VERO day)
- Max drawdown: $5,838 (13.5%)
- Biggest win: VERO +$8,085 (9.2R)
- Biggest loss: -$817 (was -$1,067 before optimizations)

---

## 5. Recent Work Completed

### Phase 2: Live Bot Alignment (commit bf3e04c, Mar 17)
- Added pillar gates to `trade_manager.py` — blocks entries that fail Ross's 5 pillars
- Added toxic entry filters — blocks wide R% + crowded day, halves risk on cold market
- Updated `stock_filter.py` ranking formula to match backtest (40% RVOL + 30% vol + 20% gap + 10% float)
- Tightened scanner defaults: gap 5→10%, float 50M→10M, RVOL 1.5→2.0x, price $1→$2

### Profile System Retest (commit 11dc3f6, Mar 17)
- **Finding**: Old profile system (+$7,310) beats current flat system (+$6,467) by $843
- Profile A (micro-float <5M): full risk 2.5% equity
- Profile B (mid-float 5-10M): risk capped at $250
- Config 3 extras (bail timer, giveback, warmup) had zero additional impact
- L2 data was NOT available for Profile B — could improve results further
- Report: `PROFILE_RETEST_REPORT.md`

### Exit Optimization (Mar 17, uncommitted)
Four optimizations tested:

**Opt 1: Mid-float risk cap** — +$837, HIGH confidence
- Stocks with float >5M → risk capped at $250
- CYN stop hit: -$999 → -$250 (save $749)
- Implemented in batch runner + live bot

**Opt 2: WB_MAX_LOSS_R=0.75** — +$276, MEDIUM confidence
- Exit at -0.75R instead of waiting for -1.0R stop
- Helps: ACON, IOTR, SXTP stop hits saved $688
- Hurts: XHLD, QCLS dip then recover, cost $508
- Net: +$180 from 0.75R alone
- **CRITICAL**: 0.50R kills ROLR (+$2,578 winner that dips to -0.60R before running to +3.2R)

**Opt 3: Winner hold analysis** — NO CHANGE NEEDED
- BE exits are correct — stocks crash 18-37% below exit by session end
- SXTC ran to +64% after exit but closed -32% below exit
- The cascading re-entry system already captured the value

**Opt 4: Consecutive loss daily stop** — $0 impact (safety net)
- Stop after 2 consecutive losses per day
- No day in 49-day test triggered this
- Added to batch runner as infrastructure for future use

**Combined result**: $6,467 → $7,580 (+$1,113 / +17.2%)
Report: `EXIT_OPTIMIZATION_REPORT.md`

---

## 6. Live Trading Performance (Paper)

### March 18, 2026 — First Live Trade
- **NUAI**: -$542 loss at 4:22 AM ET (way too early — before 7:00 gate)
- Stock filter broke → unfiltered fallback let NUAI through
- R=$0.06 (too tight), huge position → big loss on small move
- Daily loss limit correctly stopped further trading
- **Mac Mini CC fixed**: filter fallback now returns empty set (no more unfiltered trades), added `WB_ARM_EARLIEST_HOUR_ET=7` time gate
- Report: `DAILY_REPORT_20260318.md`

### March 17, 2026
- Scanner found only 1 symbol: CRAQU ($11.50, gap=+10.5%, vol=1.8x)
- CRAQU had no seed bars (no premarket data) — zero trades
- Bot ran from 4:04 AM ET, heartbeat only, no activity

### Known Live Issues
- **Mac Mini .env is OUT OF SYNC** — missing many settings from MacBook Pro (see Section 13)
- Scanner may still be too restrictive with tightened filters
- CRAQU is likely a unit (stock + warrant combo, hence "QU" suffix) — shouldn't be traded
- The bot runs on Mac Mini via cron (`daily_run.sh`) — pulls latest code, starts TWS/IBC, runs bot

---

## 7. Critical Rules You Must Know

### DO NOT:
- Suggest disabling exhaustion filter — it uses dynamic scaling that handles cascading stocks correctly
- Suggest 0.50R max loss — kills ROLR, our biggest winner
- Suppress BE/TW exits in signal mode — they enable cascading re-entry
- Implement classifier-aware exhaustion bypass — breaks VERO regression
- Change behavior without an env var gate (OFF by default)

### ALWAYS:
- Use `--ticks` mode for backtests
- Use `--tick-cache tick_cache/` for deterministic replay
- Backtest window: 07:00-12:00 ET
- Test changes on multiple stocks before declaring them good
- Gate new features behind env vars
- Run VERO regression: `python simulate.py VERO 2026-01-16 07:00 12:00 --ticks` → must be +$9,166

### Regression Target
- VERO 2026-01-16: +$9,166 (1 trade, 9.2R) — standalone tick mode

---

## 8. What Needs Work Next

### Immediate (High Priority)
1. **Sync Mac Mini .env** — Mac Mini is missing classifier, continuation hold, pillar gates, 0.75R loss cap, scanner tightening, mid-float cap, bail timer, giveback, warmup, and consecutive loss settings. See Section 13 for the full canonical .env.
2. **Verify Mac Mini has latest code** — Exit optimization changes (commit `95c8799`) + filter fallback fix (commit `d5a0765`) need to be on Mac Mini HEAD
3. **Scanner too restrictive** — Mar 17 only found 1 stock (CRAQU). May need to relax filters or exclude units/warrants

### Medium Priority
4. **L2 data integration** — Profile B stocks ran WITHOUT L2 in backtest. L2 could improve mid-float stock results. Need to build L2 caching infrastructure. **Strong hunch this is a significant edge** — see EXIT_OPTIMIZATION_REPORT.md for details.
5. **Profile system decision** — Profile retest showed +$843 improvement. Combined with exit opts, profiles + exit opts would likely produce ~$8,400+. Decision needed: bring back profiles or keep flat system with mid-float cap?
6. **CLAUDE.md is stale** — Regression targets section still references old numbers. Current live config section needs update with new settings.

### Research / Investigation
7. **Scaling in/out** — Bot is all-or-nothing, Ross scales partials. Could improve risk-adjusted returns.
8. **Post-halt re-entry** — Circuit breakers destroy the state machine. Need a recovery mechanism.
9. **Resistance tracking** — Bot enters the same rejection zone repeatedly. Need level memory.
10. **Premarket runner detection** — TWG ran 155% PM, bot got 0 trades. Missing entire category.

---

## 9. Key Reports in Repo

| File | What It Contains |
|------|-----------------|
| `PROFILE_RETEST_REPORT.md` | 3-way comparison: flat vs profiles vs profiles+extras |
| `EXIT_OPTIMIZATION_REPORT.md` | 4 optimizations tested, trade-by-trade comparison |
| `YTD_V2_BACKTEST_RESULTS.md` | Latest 49-day backtest results (combined opts) |
| `CLAUDE.md` | Project instructions for Claude Code (slightly stale) |
| `.env` | All configuration knobs — READ THIS before suggesting changes |
| `CACHED_BACKTEST_REPORT_20260317.md` | Original baseline backtest report |
| `V2_PILLAR_BACKTEST_REPORT_20260316.md` | Ross Pillar gates analysis |

---

## 10. Directive Format

When writing directives, use this format (save to `~/Downloads/DIRECTIVE_NAME.md`):

```markdown
# Directive: [Title]

## Context
[What we know, what data shows]

## Objective
[Clear goal]

## Implementation Plan
[Step-by-step with code snippets if needed]

## Test Plan
[How to verify — always use cached tick backtest]

## Critical Rules
[What NOT to do, safety checks]

## Expected Outcomes
[What success looks like, estimated impact]
```

Key principles:
- One change at a time, test each solo first
- Always include backtest verification steps
- Include winner safety checks for any loss-related changes
- Gate new features behind env vars (OFF by default)
- Reference specific trade data from reports to support recommendations

---

## 11. Git History (Recent)

```
2ec9841 Merge branch 'v6-dynamic-sizing' (sync MacBook Pro + Mac Mini)
95c8799 Exit optimization: mid-float cap + 0.75R loss cap + consec loss stop
7b040a4 Add weekly backtest report Mar 9-17: 12 trades, +$279 net
d5a0765 Fix filter fallback + add pre-market time gate
87af565 Add daily report for 2026-03-18: first live trade (NUAI -$542)
11dc3f6 Profile system retest: +$7,310 (+24.4%) vs current +$6,467 (+21.6%)
bf3e04c Phase 2: Align live bot to backtest — pillar gates, toxic filter, ranking formula
717093f Tick cache + notional fix: backtest now profitable (+$5,543, +18.5%)
```

---

## 12. Workflow with Claude Code

See **Section 0** for the full multi-machine architecture and communication flow.

Quick reference:
1. You (Cowork) analyze data from the repo, identify optimizations
2. Write a directive `.md` file with **TARGET** label at the top
3. Either push to repo as `DIRECTIVE_*.md` or save to `~/Downloads/`
4. Tell Manny which CC instance should execute it
5. CC executes, produces a report, commits + pushes
6. You read the report from the repo for the next iteration

**You have full read access to the repo** at `/Users/mannyluke/warrior_bot/` (same machine). Read any file directly — no need to clone or pull. Do NOT edit code files or commit/push; that's CC's job. Your output is always a directive `.md` file saved to `~/Downloads/`.

---

## 13. Mac Mini .env Sync Task (URGENT)

The Mac Mini's `.env` is **significantly out of date**. It's missing many settings that were added/changed on the MacBook Pro during Phase 2 alignment and exit optimization work.

**TARGET**: 🖥️ Mac Mini CC

### Settings the Mac Mini MUST have (non-secret, copy verbatim):

```env
# --- Mode ---
WB_MODE=PAPER
WB_ARM_TRADING=1
WB_ENTRY_MODE=pullback
WB_EXIT_MODE=signal

# --- Exit Signals ---
WB_BE_TRIGGER_R=3.0
WB_SIGNAL_TRAIL_PCT=0.99
WB_EXIT_ON_BEAR_ENGULF=1
WB_EXIT_ON_TOPPING_WICKY=1

# --- Max Loss Cap (Exit Optimization) ---
WB_MAX_LOSS_R=0.75

# --- Risk ---
WB_RISK_DOLLARS=1000
WB_MAX_NOTIONAL=50000
WB_MIN_R=0.06

# --- Scanner (Tightened to Ross Pillar standards) ---
WB_ENABLE_STOCK_FILTERING=1
WB_MIN_GAP_PCT=10
WB_MAX_GAP_PCT=500
WB_MAX_FLOAT=10
WB_PREFERRED_MAX_FLOAT=10
WB_MIN_REL_VOLUME=2.0
WB_MIN_PRICE=2.00
WB_MAX_PRICE=20.00

# --- Classifier ---
WB_CLASSIFIER_ENABLED=1
WB_CLASSIFIER_RECLASS_ENABLED=1
WB_CLASSIFIER_SUPPRESS_ENABLED=0
WB_CLASSIFIER_VWAP_GATE=7
WB_CLASSIFIER_CASC_VWAP_MIN=8
WB_CLASSIFIER_SMOOTH_VWAP_MIN=10

# --- Exhaustion Filter ---
WB_EXHAUSTION_ENABLED=1
WB_EXHAUSTION_VWAP_PCT=10
WB_EXHAUSTION_MOVE_PCT=50
WB_EXHAUSTION_VOL_RATIO=0.4
WB_TREND_STRONG_RANGE_PCT=5
WB_EXHAUSTION_VWAP_RANGE_MULT=0.5
WB_EXHAUSTION_MOVE_RANGE_MULT=1.5

# --- Continuation Hold ---
WB_CONTINUATION_HOLD_ENABLED=1
WB_CONT_HOLD_5M_TREND_GUARD=1
WB_CONT_HOLD_5M_VOL_EXIT_MULT=2.0
WB_CONT_HOLD_5M_MIN_BARS=2
WB_CONT_HOLD_MIN_VOL_DOM=2.0
WB_CONT_HOLD_MIN_SCORE=8.0
WB_CONT_HOLD_MAX_LOSS_R=0.5
WB_CONT_HOLD_CUTOFF_HOUR=10
WB_CONT_HOLD_CUTOFF_MIN=30

# --- Pillar Gates (Ross 5 Pillar entry-time gates) ---
WB_PILLAR_GATES_ENABLED=1

# --- Bail Timer ---
WB_BAIL_TIMER_ENABLED=1
WB_BAIL_TIMER_MINUTES=5

# --- Daily Risk Management ---
WB_DAILY_GOAL=500
WB_MAX_DAILY_LOSS=500
WB_GIVEBACK_HARD_PCT=50
WB_GIVEBACK_WARN_PCT=20
WB_MAX_CONSECUTIVE_LOSSES=3

# --- Warmup Sizing ---
WB_WARMUP_SIZE_PCT=25
WB_WARMUP_SIZE_THRESHOLD=500

# --- Stale Stock Filter ---
WB_STALE_STOCK_FILTER=1
WB_STALE_MAX_BARS_NO_HOD=30
WB_STALE_SESSION_HOD_BARS=120

# --- Warmup Bars ---
WB_WARMUP_BARS=5

# --- Time Gate (added after NUAI incident) ---
WB_ARM_EARLIEST_HOUR_ET=7

# --- Data Feed ---
WB_DATA_FEED=alpaca
```

**Instructions for Mac Mini CC**: Compare your current `.env` with these values. Add any missing keys. Update any that differ. **DO NOT touch API keys** (APCA_API_KEY_ID, APCA_API_SECRET_KEY, DATABENTO_API_KEY, FMP_API_KEY) — keep whatever is already on the Mac Mini.

---

*Handoff created: 2026-03-18 | Updated: 2026-03-18 | From: Claude Code | To: Claude Cowork*
