# Claude Cowork Handoff — Warrior Bot Project
## Updated: 2026-03-18

**Your role**: Replace Perplexity as the strategy analyst / directive writer. You read the repo, analyze data, and produce `.md` directive files that Claude Code executes. **Do NOT modify code directly** — write directives to `~/Downloads/` and let Claude Code implement them.

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

### Uncommitted Changes (on MacBook Pro)
These are from the Exit Optimization work done 2026-03-17, not yet committed:
- `run_ytd_v2_backtest.py` — Mid-float risk cap + WB_MAX_LOSS_R=0.75 + consecutive loss stop
- `trade_manager.py` — Mid-float risk cap in live bot (qty capped for float >5M stocks)
- `EXIT_OPTIMIZATION_REPORT.md` — Full analysis report
- `YTD_V2_BACKTEST_RESULTS.md` — Updated with combined optimization results

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

### March 17, 2026
- Scanner found only 1 symbol: CRAQU ($11.50, gap=+10.5%, vol=1.8x)
- CRAQU had no seed bars (no premarket data) — zero trades
- Bot ran from 4:04 AM ET, heartbeat only, no activity
- This was the first run AFTER the Phase 2 alignment changes

### Known Live Issues
- Scanner is too restrictive with tightened filters — only 1 stock passed on Mar 17
- CRAQU is likely a unit (stock + warrant combo, hence "QU" suffix) — shouldn't be traded
- The bot runs on Mac Mini via cron (`daily_run.sh`) — pulls latest code, starts TWS/IBC, runs bot

### Historical Live Sessions (Feb-Mar 2026)
- Many sessions with bot crashes, restarts, configuration issues
- Feb 11-12 had large event logs (36MB-368MB) suggesting heavy trading or data issues
- Most recent clean sessions: Feb 24-27, Mar 2-5
- No session logs after Mar 5 until the Mar 17 automated run

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
1. **Commit + push exit optimization changes** — mid-float cap, 0.75R loss cap, consecutive loss stop are implemented but uncommitted on MacBook Pro
2. **Analyze today's live session** (Mar 18) — Manny mentioned having live test data from this morning
3. **Scanner too restrictive** — Mar 17 only found 1 stock (CRAQU). May need to relax filters or fix the scanner to exclude units/warrants

### Medium Priority
4. **L2 data integration** — Profile B stocks ran WITHOUT L2 in backtest. L2 could improve mid-float stock results. Need to build L2 caching infrastructure.
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
11dc3f6 Profile system retest: +$7,310 (+24.4%) vs current +$6,467 (+21.6%)
bf3e04c Phase 2: Align live bot to backtest — pillar gates, toxic filter, ranking formula
717093f Tick cache + notional fix: backtest now profitable (+$5,543, +18.5%)
4a8b94d Add daily report for 2026-03-17 first automated run
6683129 V2 Pillar backtest results + RVOL scanner data for all 49 dates
c4d8acd Revert to Alpaca feed — Databento produces different bar data
b409618 Ross Pillar gates + Databento feed + API retry logic
3703532 CRITICAL: Alpaca API 500 errors silently dropping winners from backtests
```

---

## 12. Workflow with Claude Code

1. You (Cowork) analyze data, identify optimizations, write a directive `.md` file
2. Save it to `~/Downloads/`
3. Tell Manny it's ready
4. Manny tells Claude Code: "check downloads for [directive name]"
5. Claude Code reads the directive and executes it
6. Claude Code produces a report, commits, pushes
7. You can read the report from the repo for the next iteration

**You have full read access to the repo. Use it.** Read trade logs, backtest results, scanner data, and the full .env to inform your analysis. The more context you pull from the actual data, the better your directives will be.

---

*Handoff created: 2026-03-18 | From: Claude Code | To: Claude Cowork*
