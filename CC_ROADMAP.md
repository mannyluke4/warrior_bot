# CC Roadmap — Warrior Bot Phase Plan

**Date:** April 3, 2026
**Author:** Cowork (Opus)
**Purpose:** Single source of truth for all planned work, ordered by priority and dependency. Read this before starting any new directive.

---

## Current State (as of April 3, 2026)

**Live bot:** `bot_v3_hybrid.py` on Mac Mini. IBKR data + Alpaca execution. Squeeze V2 (rolling HOD gate ON, candle exits OFF). First live day April 2 — 0 trades, infrastructure stable 6 hours.

**Performance baselines:**
- SQ V1: +$154,849 (63-day, 26 trades, 73% WR)
- SQ V2 rolling HOD: +$169,227 (29 trades, 67% WR) — current best
- SQ + EPL (VWAP floor): +$252,804 (63-day megatest, 45 trades, 59% WR)
- Regression: VERO +$15,692, ROLR +$6,444

**Branch:** `v2-ibkr-migration` for bot_v3_hybrid.py work.

---

## Workstream A: Ship EPL to Live Bot

**Status:** Directive written (`DIRECTIVE_SHIP_EPL_TO_LIVE.md`), not yet started.
**Priority:** HIGH — proven +$83K uplift over SQ-only baseline.
**Dependency:** None. Can start immediately.

### What Ships
- `epl_framework.py` — GraduationContext, EPLWatchlist, StrategyRegistry, PositionArbitrator
- `epl_mp_reentry.py` — MP re-entry strategy with VWAP floor gate (`WB_EPL_MP_VWAP_FLOOR=1`)

### What Does NOT Ship
- `epl_vwap_reclaim.py` — leave in repo, do NOT register or import (0 trades on 63-day megatest, shelved)

### Integration Points (9 sections in bot_v3_hybrid.py)
1. Imports (epl_framework, epl_mp_reentry)
2. Strategy gates (reads own env vars)
3. BotState additions (epl_watchlist, epl_registry, epl_arbitrator)
4. EPL initialization in main()
5. Graduation hook in _squeeze_exit() — fires on SQ 2R target hit
6. EPL bar processing in on_bar_close_1m() — expiry, exit mgmt, entry signals
7. EPL tick processing in _process_ticker() — tick exits, entry triggers
8. New _enter_epl_trade() function — EPL-specific sizing via EPL_MAX_NOTIONAL
9. EPL exit routing in manage_exit() — setup_type.startswith("epl_") routes to strategy

### Key Rule
SQ always fires first via check_triggers(). EPL only when position is free and SQ is idle.

### Env Vars for Mac Mini .env
```bash
WB_EPL_ENABLED=1
WB_EPL_MAX_STOCKS=5
WB_EPL_EXPIRY_MINUTES=120
WB_EPL_MIN_GRADUATION_R=2.0
WB_EPL_MAX_TRADES_PER_GRAD=3
WB_EPL_MAX_NOTIONAL=50000
WB_EPL_MAX_LOSS_SESSION=1000
WB_EPL_MP_ENABLED=1
WB_EPL_MP_COOLDOWN_BARS=3
WB_EPL_MP_MAX_PULLBACK_BARS=5
WB_EPL_MP_MIN_R=0.06
WB_EPL_MP_STOP_PAD=0.01
WB_EPL_MP_TRAIL_R=1.5
WB_EPL_MP_TIME_STOP_BARS=5
WB_EPL_MP_VWAP_FLOOR=1
```

### Done When
- EPL wired into bot_v3_hybrid.py
- Regression still passes (VERO +$15,692, ROLR +$6,444)
- Bot starts cleanly on Mac Mini with EPL env vars set
- EPL is gated by `WB_EPL_ENABLED` (OFF by default, ON in Mac Mini .env)

---

## Workstream B: Box Strategy (5 Phases)

**Status:** Phase 1 scanner built (V1, single-day), failed validation. V2 directive written (multi-day range detection).
**Priority:** MEDIUM — new revenue stream for dead zone (10 AM - 3:45 PM), but unproven.
**Dependency:** Independent of Workstream A. Can run in parallel.

### Phase 1: Box Scanner V2 (Multi-Day) ← CURRENT
**Directive:** `DIRECTIVE_BOX_SCANNER_V2_MULTIDAY.md`

Build a scanner that finds stocks consolidating in a proven multi-day range (5-day lookback, levels tested 2+ times each). This replaces the failed V1 single-day approach.

**Key changes from V1:**
- 5-day range (not single-morning HOD/LOD)
- Split level test counting: `count_resistance_tests` (bar.high) and `count_support_tests` (bar.low) — separate functions, no double-counting
- Pull 30D of daily bars from IBKR (not 5D) — need 25+ trading days for SMA slope filter
- ADR utilization INVERTED: want LOW today-ADR (stock is quiet), not high
- Stock universe: IBKR HOT_BY_VOLUME (live), `box_universe.txt` ~200-300 liquid stocks (historical)
- New filters: SMA slope < 5% (no trending), no gaps > 5% in 5 days
- Scoring is buy-side only (rewards stocks near bottom of range)

**Build steps:**
1. Rewrite `box_scanner.py` with multi-day logic
2. Pull 30D of daily bars per candidate
3. Add split level test counting functions
4. Add SMA slope filter + gap filter
5. Add stock universe handling (live + historical modes)
6. Update scoring formula
7. Run across all YTD dates (Jan 2 - Apr 2)
8. Push results — **STOP** — we verify on charts before Phase 2

**Done when:** YTD scanner results pushed. We (Cowork + Manny) visually verify candidates on TradingView. DO NOT proceed to Phase 2 until we give the green light.

### Phase 2: Box Strategy Build
**Directive:** Not yet written. Will be written after Phase 1 verification.
**Dependency:** Phase 1 scanner verified.

Build `box_strategy.py` — the entry/exit logic for range-bound trading:

- **Entry:** Buy in lower 25% of 5-day box, RSI oversold confirmation, reversal candle
- **Exit targets:** VWAP partial (50%), upper 25% of box (remaining 50%)
- **Stops:** Hard stop below 5-day LOD (with pad), trail at 30% of box range
- **Time stop:** Force close by 3:45 PM ET — no overnight holds
- **Session loss cap:** $500 max box losses per day

Env vars: `WB_BOX_ENABLED`, `WB_BOX_START_ET=10:00`, `WB_BOX_LAST_ENTRY_ET=14:30`, `WB_BOX_HARD_CLOSE_ET=15:45`, `WB_BOX_MAX_NOTIONAL=50000`, `WB_BOX_MAX_LOSS_SESSION=500`

### Phase 3: Box-Only YTD Backtest
**Dependency:** Phase 2 strategy built.

Run box strategy in isolation across all YTD dates. No squeeze, no EPL — box only. Evaluate:
- Total P&L, win rate, average win/loss, max drawdown
- Time-of-day performance (does 10 AM entry beat 1 PM entry?)
- Best/worst candidates — what distinguishes them?
- Session loss cap effectiveness

**Done when:** Results reviewed. We decide go/no-go for Phase 4.

### Phase 4: Combined Backtest (Squeeze + Box)
**Dependency:** Phase 3 looks good.

Run the full system: squeeze 7-10 AM, box 10 AM - 3:45 PM. Validate:
- No position conflicts (single position slot, time window separation)
- Momentum finishes naturally before box activates
- Box doesn't hurt squeeze P&L (no interference)
- Combined P&L > squeeze-only P&L
- If momentum has a position at 10 AM, box waits (momentum priority)

### Phase 5: Ship Box to Live Bot
**Dependency:** Phase 4 passes.

Wire box strategy into `bot_v3_hybrid.py`:
- Time-based mode switching (squeeze mode → box mode at 10 AM ET)
- Box scanner activation at 10 AM
- Box entry/exit logic
- Position handoff rules (momentum finishes, box takes over)
- `WB_BOX_ENABLED=0` by default, ON in Mac Mini .env
- Paper trade for at least 1 week before any live capital

---

## Workstream C: Known Issues & Fixes

These are independent items from MASTER_TODO. Lower priority than A and B, but should be addressed when convenient.

### C1. Bot Rescan Checkpoints (Quick Fix)
`bot_v3_hybrid.py` still uses old 7-checkpoint 30-min schedule for `RESCAN_CHECKPOINTS_ET`. Should match scanner_sim's 12 data-driven checkpoints:
```
7:00, 7:15, 7:30, 7:45, 8:00, 8:10, 8:15, 8:30, 8:45, 9:00, 9:15, 9:30
```
Hard 9:30 cutoff (post-09:30 is negative EV).

### C2. Mac Mini pmset Sleep Prevention
Mac Mini sleeps overnight, cron at 4 AM fails. Need:
```bash
sudo pmset -a sleep 0
sudo pmset -a disablesleep 1
```
Or a caffeinate wrapper in daily_run_v3.sh.

### C3. stock_filter.py MAX_FLOAT Default
Hardcoded to 10M but .env overrides to 15M at runtime. Fix the default to match .env.

### C4. live_scanner.py Write Frequency
Still 5-min writes until 11:00 AM. Directive called for 1-min writes with 9:30 cutoff. Not blocking anything, but should be aligned.

### C5. V2 Base Code Regression Audit
SQ V2 base code (rolling HOD OFF) has an unexplained -$23K regression vs V1. Not blocking (rolling HOD is always ON), but worth understanding.

---

## Execution Order

```
Priority 1 (Now):
├── Workstream A: Ship EPL to live bot
│   └── Single directive, 9 integration points
│
├── Workstream B Phase 1: Box Scanner V2 (multi-day)
│   └── Rewrite box_scanner.py, run YTD, push results, STOP
│
└── C1: Bot rescan checkpoints (quick fix, do alongside A)

Priority 2 (After Phase 1 verification):
├── Workstream B Phase 2: Box Strategy build
├── Workstream B Phase 3: Box-only backtest
└── C2: pmset fix (do anytime)

Priority 3 (After box proven):
├── Workstream B Phase 4: Combined backtest
├── Workstream B Phase 5: Ship box to live
└── C3-C5: Cleanup items
```

---

## Rules (Always Apply)

1. **All new features gated by env vars** (OFF by default)
2. **Always run regression before pushing:** VERO +$15,692, ROLR +$6,444
3. **Always `git pull` at start, `git push` at end**
4. **IBKR = data/scanning, Alpaca = execution ONLY**
5. **Cowork (Opus) writes plans/docs, CC writes code** — never the other way around
6. **Backtest window: 07:00-12:00 ET, always `--ticks` mode**
7. **Do NOT proceed past verification gates** — wait for Cowork/Manny green light
8. **Push to `v2-ibkr-migration` branch** for bot_v3_hybrid.py work
