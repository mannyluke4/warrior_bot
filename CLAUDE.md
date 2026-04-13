# Warrior Bot — Project Instructions

## What This Is
A Python trading bot that detects squeeze breakout and micro-pullback setups on small-cap stocks and executes trades via Alpaca API. Currently in paper trading mode. Squeeze is the primary strategy (V1 config); micro-pullback is gated OFF.

## Critical Rules

### Backtesting
- **Always use `--ticks` mode** for backtests (matches live bot tick-by-tick replay)
- **Backtest window: 07:00-12:00 ET** (Ross Cameron's active hours)
- **Always run regression before pushing**: VERO +$34,479, ROLR +$54,654
  ```bash
  WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
  WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
  ```
  Note: `WB_MP_ENABLED=1` required since Item 1 (2026-03-22) gated MP off by default.
- VERO target history: +$9,166 (pre-Fix 5) → +$18,583 (2026-03-18, Fix 5 TW profit gate) → +$15,692 (2026-03-27, system-wide optimization) → +$34,479 (2026-04-08, X01 tuning: 3.5% risk + 5 max attempts)
- GWAV and ANPA no longer produce trades in standalone mode (detector evolution)

### Code Changes
- **All new features gated by env vars** (OFF by default) to prevent regressions
- Never modify existing behavior without a gate — butterfly effects are real
- Test on multiple stocks before declaring a fix works
- The `.env` file has all config knobs — read it before adding new ones
- `exit_mode = "signal"` is the primary strategy (cascading re-entry via BE/TW exits)
- In signal mode, do NOT suppress BE/TW exits — they enable the cascading re-entry edge

### Environment
- Python 3.13, activate venv first: `source venv/bin/activate`
- Run from `/Users/mannyluke/warrior_bot/`
- Ignore Homebrew stderr noise about macOS 26.1

### Git
- **Always `git pull` at the start of every directive** — Manny works from MBP too
- **Always `git push` at the end of every directive** — keeps all machines in sync
- Push to `origin main` after regression passes
- Commit messages should reference what changed and why
- Include `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
- Cowork (Opus) updates docs (MASTER_TODO, COWORK_HANDOFF, CLAUDE.md, etc.) and commits locally — CC pushes on next run

## Key Architecture

### Detection Flow
1. Seed bars (4AM-start) build EMA/VWAP/PM_HIGH context
2. 1-minute bars feed `SqueezeDetector` (volume spike → level break) and/or `MicroPullbackDetector` (impulse → pullback → ARM)
3. Squeeze: armed on volume/body criteria, triggers on tick price breaking level (PM high, whole dollar, PDH)
4. MP: armed setups trigger on tick price breaking trigger_high
5. Squeeze exits: dollar loss cap → hard stop → max_loss tiered → pre-target trail → 2R target (partial) → runner trail
6. MP exits: 10-second bars detect exit patterns (bearish engulfing, topping wicky), signal mode trail
7. Classifier (currently disabled) categorizes stock at 5m and adjusts exit thresholds

### File Map
| File | Purpose |
|------|---------|
| `bot.py` | Live bot (Alpaca websocket) |
| `simulate.py` | Backtesting engine (tick + bar mode) |
| `micro_pullback.py` | Core 1m detector state machine |
| `trade_manager.py` | Order execution + exit management |
| `bars.py` | TradeBarBuilder (VWAP/HOD/PM tracking) |
| `classifier.py` | Stock behavior classifier (Phase 2) |
| `validate_classifier.py` | Classifier validation script |
| `analyze_study.py` | Study analysis + report generation |
| `run_study.sh` | Batch study runner |
| `study_stocks.txt` | Active stock list for batch runs |
| `study_data/*.json` | Per-stock behavioral metrics (108 files) |
| `study_results/` | Analysis reports, CSVs, charts |
| `trade_logs/` | Detailed per-stock trade analysis markdown |
| `squeeze_detector.py` | Squeeze/breakout detector (level breaks on volume) |
| `live_scanner.py` | Real-time Databento scanner (writes watchlist.txt) |
| `scanner_sim.py` | Historical backtesting scanner |
| `stock_filter.py` | Bot rescan filter (reads all thresholds from .env) |
| `market_scanner.py` | Alpaca API scanner (used by bot.py rescan thread) |
| `cowork_reports/` | Cowork session reports and audits |

### Detector Constructor
```python
det = MicroPullbackDetector()  # NO symbol argument
```

## Current Live Config (as of 2026-04-08, X01 tuning)
```
# === Strategy ===
WB_MP_ENABLED=0              # Micro-pullback OFF (gated since 2026-03-22)
WB_SQUEEZE_ENABLED=1         # Squeeze is the primary strategy (wired into live bot 2026-03-24)
WB_ROSS_EXIT_ENABLED=0       # Ross exits OFF — V1 mechanical exits proven best
WB_CLASSIFIER_ENABLED=0      # Classifier not wired into bot/sim (research only)
WB_EXHAUSTION_ENABLED=1      # KEEP ON — dynamic scaling handles cascading stocks correctly
WB_CONTINUATION_HOLD_ENABLED=1
WB_CONT_HOLD_5M_TREND_GUARD=1
WB_MAX_NOTIONAL=50000        # Aligned to batch runner ENV_BASE
WB_PILLAR_GATES_ENABLED=1    # Ross Pillar entry-time gates in live bot
WB_WARMUP_BARS=5
WB_BAIL_TIMER_ENABLED=1      # 5-min unprofitable exit (live bot only, added to sim 2026-03-24)
WB_BAIL_TIMER_MINUTES=5

# === X01 Tuning (deployed 2026-04-08) ===
WB_SQ_VOL_MULT=2.5          # was 3.0
WB_SQ_PRIME_BARS=4           # was 3
WB_SQ_MIN_BODY_PCT=2.0       # was 1.5
WB_SQ_MAX_ATTEMPTS=5         # was 3
WB_SQ_TARGET_R=1.5           # was 2.0
WB_SQ_CORE_PCT=90            # was 75
WB_RISK_PCT=0.035            # was 0.025
WB_DAILY_LOSS_SCALE=1        # 2% of equity scaling

# === Seed-staleness arm validation (added 2026-04-13) ===
WB_SQ_SEED_STALE_GATE_ENABLED=1  # drops stale arms at seed end; set 0 for diff
WB_SQ_SEED_STALE_PCT=2.0         # threshold: current_price > trigger_high * 1.02 → drop

# === Scanner (all 3 scanners now read from .env — parity fix 2026-03-24) ===
WB_MIN_GAP_PCT=10
WB_MAX_GAP_PCT=500
WB_MIN_PRICE=2.00
WB_MAX_PRICE=20.00
WB_MAX_FLOAT=15              # Raised from 10M (WT comparison: AMIX 12.9M = +$4,111)
WB_MIN_REL_VOLUME=2.0
WB_MIN_PM_VOLUME=50000
```

### Strategy: Squeeze Focus V1
V1 config confirmed best by megatest comparison (2026-03-24):
- V1 (+$19,832) > V2 (+$18,514) > V3 (+$16,333)
- V1 uses SQ mechanical exits only (dollar loss cap, hard stop, tiered max_loss, pre/post-target trails)
- V2 added Ross 1m signal exits (slight drag on squeeze trades)
- V3 added Ross + SQ coexistence (worst of both worlds)

### Ross Exit System (available but OFF)
`WB_ROSS_EXIT_ENABLED=0` — disabled after V1 proven superior for squeeze.
When ON, it replaces 10s BE/TW pattern exits with 1m candle signals (CUC, doji, gravestone, shooting star) + MACD/EMA20/VWAP backstops. May be revisited if MP is re-enabled (designed for MP-style trades).

### Scanner Checkpoints
scanner_sim.py uses 12 data-driven checkpoints (updated 2026-03-24):
`7:00, 7:15, 7:30, 7:45, 8:00, 8:10, 8:15, 8:30, 8:45, 9:00, 9:15, 9:30`
- Dense coverage during golden hour (08:00-08:30, 71% WR, +$26,875)
- Hard 9:30 cutoff (post-09:30 is negative EV: -$2,430, 25% WR)
- **NOTE**: bot.py `RESCAN_CHECKPOINTS_ET` still uses old 7-checkpoint 30-min schedule — needs updating to match

### Exhaustion Filter + Dynamic Scaling (CRITICAL INSIGHT)
The exhaustion filter is enabled by default and works CORRECTLY for cascading stocks because of dynamic scaling:
- For big runners (VERO $3.50→$12+, ~243% range): `eff_vwap_pct = max(10%, 243 * 0.5) = 121.5%` → cascading re-entries pass ✅
- For smaller-move stocks (TURB at 21.7% above VWAP): threshold stays near 10% → blocked ✅
- **DO NOT implement a classifier-aware bypass** — it would break VERO regression
- `WB_EXHAUSTION_ENABLED=0` HURTS cascading stocks due to LevelMap interaction (more early entries → more failed resistance levels recorded → optimal entry point blocked)

### Regression Targets (as of 2026-04-08, X01 tuning)
Primary standalone regression (deterministic, tick mode):
- VERO 2026-01-16: +$34,479 ✅ (shifted from +$15,692 after X01 tuning: 3.5% risk, 5 max attempts, VOL_MULT 2.5, TARGET_R 1.5, CORE_PCT 90)
- ROLR 2026-01-14: +$54,654 ✅ (shifted from +$6,444 after X01 tuning — compounding equity amplifies gains)
Note: GWAV and ANPA no longer produce trades in standalone mode due to detector
evolution (R=0.04 < MIN_R=0.06 for GWAV, no ARMs for ANPA). The batch runner
(run_ytd_v2_backtest.py) with tick cache produces +$19,832 (V1) across 49 days.

## Current Study Status (as of 2026-03-24)

### Completed
- Phase 1: BehaviorMetrics + 108-stock batch + analysis report
- Phase 2: Classifier (7 types, exit profiles, validation report)
- 11 detailed trade logs comparing bot vs Ross Cameron
- Fixes: stale filter, BE grace, profit gates, re-entry cooldown, vol floor
- Live bot alignment: squeeze wired in, exit logic ported, bail timer added (2026-03-24)
- Scanner parity: all 3 scanners read from .env (2026-03-24)
- Scanner checkpoint optimization: 12 data-driven checkpoints in scanner_sim (2026-03-24)
- V1/V2/V3 exit comparison: V1 confirmed best (2026-03-24)

### Key Metrics
- 108 stocks, 133 trades, +$4,592 total P&L, 28% win rate (MP-era study)
- Squeeze megatest (V1, 49 days): +$19,832
- Classifier gate saves $1,712 net (blocks losers, 1 false positive)
- Cascading stocks: avg +$2,043 (VERO, BATL, MOVE, ARLO)

### Known Gaps (research phase — no code changes yet)
- Scaling in/out (bot is all-or-nothing, Ross scales partials)
- Premarket runner detection (TWG ran 155% PM, bot got 0 trades)
- Post-halt re-entry (circuit breakers destroy state machine)
- Resistance tracking (bot enters same rejection zone repeatedly)
- Unknown-float stocks: 17 in WT study, $27,960 P&L sitting on the table
- ESHA/INBS Databento SPAC coverage gap ($34K Ross P&L unrecoverable)
- Stale fundamentals bug: standalone sims re-fetch float from Alpaca (get 0.0M for some stocks); use `--no-fundamentals` to match batch runner
- bot.py rescan checkpoints still old 30-min schedule (scanner_sim updated, bot.py not)
- live_scanner.py still 5-min writes until 11:00 AM (directive called for 1-min writes, 9:30 cutoff)
- stock_filter.py MAX_FLOAT default hardcoded to 10M (overridden by .env at runtime, but default is wrong)
