# Warrior Bot — Project Instructions

## What This Is
A Python trading bot that detects micro-pullback setups on small-cap stocks and executes trades via Alpaca API. Currently in paper trading mode undergoing a comprehensive behavior study.

## Critical Rules

### Backtesting
- **Always use `--ticks` mode** for backtests (matches live bot tick-by-tick replay)
- **Backtest window: 07:00-12:00 ET** (Ross Cameron's active hours)
- **Always run regression before pushing**: VERO +$6,890, GWAV +$6,735, ANPA +$2,088
  ```bash
  python simulate.py VERO 2026-01-16 07:00 12:00 --ticks
  python simulate.py GWAV 2026-01-16 07:00 12:00 --ticks
  python simulate.py ANPA 2026-01-09 07:00 12:00 --ticks
  ```
- Regression must pass with ALL env configs (classifier ON and OFF, etc.)

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
- Push to `origin main` after regression passes
- Commit messages should reference what changed and why
- Include `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`

## Key Architecture

### Detection Flow
1. Seed bars (4AM-start) build EMA/VWAP/PM_HIGH context
2. 1-minute bars feed `MicroPullbackDetector` (impulse -> pullback -> ARM)
3. Armed setups trigger on tick price breaking trigger_high
4. 10-second bars detect exit patterns (bearish engulfing, topping wicky)
5. Classifier (when enabled) categorizes stock at 5m and adjusts exit thresholds

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

### Detector Constructor
```python
det = MicroPullbackDetector()  # NO symbol argument
```

## Current Live Config (as of 2026-03-02)
```
WB_CLASSIFIER_ENABLED=1
WB_CLASSIFIER_SUPPRESS_ENABLED=0
WB_CLASSIFIER_VWAP_GATE=7
WB_CLASSIFIER_CASC_VWAP_MIN=8
WB_CLASSIFIER_SMOOTH_VWAP_MIN=10
WB_CLASSIFIER_RECLASS_ENABLED=1
WB_WARMUP_BARS=5
WB_EXHAUSTION_ENABLED=1   # KEEP ON — dynamic scaling handles cascading stocks correctly
```

### Exhaustion Filter + Dynamic Scaling (CRITICAL INSIGHT)
The exhaustion filter is enabled by default and works CORRECTLY for cascading stocks because of dynamic scaling:
- For big runners (VERO $3.50→$12+, ~243% range): `eff_vwap_pct = max(10%, 243 * 0.5) = 121.5%` → cascading re-entries pass ✅
- For smaller-move stocks (TURB at 21.7% above VWAP): threshold stays near 10% → blocked ✅
- **DO NOT implement a classifier-aware bypass** — it would break VERO regression ($6,890→$3,452)
- `WB_EXHAUSTION_ENABLED=0` HURTS cascading stocks due to LevelMap interaction (more early entries → more failed resistance levels recorded → optimal entry point blocked)

### Regression Targets (as of 2026-03-02)
All three regressions PASS with current defaults (exhaustion ON, classifier ON):
- VERO 2026-01-16: +$6,890 ✅
- GWAV 2026-01-16: +$6,735 ✅
- ANPA 2026-01-09: +$2,088 ✅

## Current Study Status (as of 2026-02-27)

### Completed
- Phase 1: BehaviorMetrics + 108-stock batch + analysis report
- Phase 2: Classifier (7 types, exit profiles, validation report)
- 11 detailed trade logs comparing bot vs Ross Cameron
- Fixes: stale filter, BE grace, profit gates, re-entry cooldown, vol floor

### Key Metrics
- 108 stocks, 133 trades, +$4,592 total P&L, 28% win rate
- Classifier gate saves $1,712 net (blocks losers, 1 false positive)
- Cascading stocks: avg +$2,043 (VERO, BATL, MOVE, ARLO)

### Known Gaps (research phase — no code changes yet)
- Scaling in/out (bot is all-or-nothing, Ross scales partials)
- Premarket runner detection (TWG ran 155% PM, bot got 0 trades)
- Post-halt re-entry (circuit breakers destroy state machine)
- Resistance tracking (bot enters same rejection zone repeatedly)
