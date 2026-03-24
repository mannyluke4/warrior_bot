# CC Report: Full Live Bot Session — 2026-03-24
## Date: 2026-03-24
## Machine: Mac Mini

---

## Morning Run (04:00 - 11:00 ET)

### Startup
- Cron fired at 2:00 AM MT (4:00 AM ET), pulled from `main`
- Pre-flight imports passed, stale connection cleanup ran
- **No websocket errors** — connected immediately (yesterday's fix worked)
- Scanner found **1 stock**: BIAF (gap +62%, RVOL 2.7x, float 4.3M)

### Trading Activity
- **0 trades, 0 ARMs, 0 signals** all morning
- BIAF had thin premarket activity (50-300 shares/bar), lots of "trend failure strong" resets
- No squeeze volume explosions triggered
- `watch=0` display bug persisted (cosmetic — reads empty watchlist.txt vs dynamic subscriptions)

### Scanner Divergence (Again)
| Source | Stocks Found |
|--------|-------------|
| Live bot (stock_filter.py) | BIAF |
| Scanner sim (scanner_sim.py) | ELAB, FEED, LICN |

Different scanners, different stocks. The scanner parity fix was pushed later in the day.

---

## Changes Made Today

### 1. SQ + Ross Exit Coexistence (V3 Comparison)
- Added `WB_SQ_ROSS_COEXIST` env var to simulate.py (4 guard lines modified)
- Ran 3-way Jan comparison: V1 (SQ only) vs V2 (Ross only) vs V3 (SQ+Ross)
- Result: V1 +$19,832 > V2 +$18,514 > V3 +$16,333
- sq_target_hit exits restored (0 in V2 → 9 in V3, all winners +$7,136)
- But Ross signals cut runners → V3 underperforms V1 by $3,499
- **Decision: V1 (SQ mechanical only) remains best config**

### 2. Scanner Overhaul — Profile X Removal
- Removed ALL unknown-float filtering from 9 runner files
- `live_scanner.py`: `passes_float_filter()` now returns True for unknown float
- Deleted `WB_ALLOW_UNKNOWN_FLOAT` env var and all gating constants
- Unknown-float stocks now treated identically to known-float stocks

### 3. Scanner Checkpoints — Manual Tuning
- Changed from dynamic 5-min to manual checkpoint list
- **12 checkpoints**: 7:00, 7:15, 7:30, 7:45, 8:00, 8:10, 8:15, 8:30, 8:45, 9:00, 9:15, 9:30 → CUTOFF
- Tighter in the 8:00-8:30 window, 9:30 hard cutoff for new discoveries

### 4. Live Bot Alignment (P0 — Biggest Change)
**Wired SqueezeDetector into the live bot for the first time:**

| Component | What Changed |
|-----------|-------------|
| bot.py | Import SqueezeDetector, SQ_ENABLED gate, sq_detectors dict, ensure_sq_detector(), seed on subscribe, 1m bar feed, tick trigger (priority over MP), trade close callback |
| trade_manager.py | setup_type + size_mult on TradePlan, parse_plan() extracts setup_type from message, propagated to PendingEntry, _squeeze_manage_exits() method (dollar loss cap, hard stop, max_loss tiered, pre-target trail, sq_target_hit partial exit, runner trail) |
| simulate.py | Bail timer added (WB_BAIL_TIMER_ENABLED, matches live bot's 5-min unprofitable exit) |
| .env | WB_CLASSIFIER_ENABLED set to 0 (not wired into anything) |

### 5. Scanner Filter Parity
- `live_scanner.py` + `scanner_sim.py` now read ALL thresholds from .env
- Previously hardcoded: gap%, price range, float cap, RVOL, PM volume
- Single source of truth: change .env once → all 3 scanners update

### 6. SSH Setup
- Enabled Remote Login on Mac Mini
- Tailscale installed for remote access from phone
- Manny can now SSH into Mac Mini from anywhere via Termius

---

## Backtest: What Today Should Have Looked Like

Scanner sim found 3 candidates (vs live bot's 1):

| Stock | Gap | RVOL | Float | Discovery | Trades | P&L | Notes |
|-------|-----|------|-------|-----------|--------|-----|-------|
| **ELAB** | +48% | 5x | 2.1M | 07:00 | 2 | **+$670** | Squeeze target hit +$1,027, para trail -$357. Blocked by stale float data without --no-fundamentals |
| FEED | +43% | 28x | 0.85M | 08:15 | 0 | $0 | MACD bearish, HOD gate blocked bounce |
| LICN | +23% | 15x | 0.76M | 09:20 | 0 | $0 | MP armed score 16.5 but WB_MP_ENABLED=0. No squeeze. |

**Theoretical day total: +$670** (ELAB squeeze only)

### Bug Found: Stale Fundamentals
- simulate.py re-fetches float from Alpaca API, got 0.0M for ELAB
- Scanner JSON correctly had 2.1M
- Quality gate blocked entry (0.0M < 0.5M minimum)
- Batch runners use `--no-fundamentals` (pass scanner data via env vars) — unaffected
- Standalone sims need `--no-fundamentals` to match batch runner behavior

---

## Full Audit Results (End of Day)

### CRITICAL Issues: 0

### All Systems Verified:

| System | Status |
|--------|--------|
| Imports (all modules) | PASS |
| Branch (main, up to date) | PASS |
| Cron (2 AM MT weekdays) | PASS |
| .env (15 critical vars) | PASS |
| Squeeze in bot.py (7 integration points) | PASS |
| Squeeze exits in trade_manager (6 checkpoints) | PASS |
| Simulator alignment (bail timer, coexist, MP gate) | PASS |
| No stale processes | PASS |
| Alpaca API | PASS (SPY $655.32) |
| Scanner parity (3 scanners → .env) | PASS |
| daily_run.sh flow (9 steps) | PASS |
| Git clean (scanner_results committed) | PASS |

### Warnings (non-blocking):
1. stock_filter.py MAX_FLOAT default (10M vs .env 15M) — overridden at runtime
2. Stale TWS/IBC text references in daily_run.sh — cosmetic only
3. CLAUDE.md slightly stale (docs say ROSS_EXIT=1, CLASSIFIER=1 but both are 0)

---

## Commits Today (9 total)

| Commit | Description |
|--------|-------------|
| `bbb32c3` | SQ + Ross exit coexistence fix + V3 Jan comparison |
| `5fcf05f` | Scanner overhaul: remove Profile X + 10-min checkpoints |
| `80759ac` | Scanner: 2.5-min checkpoints (quickly revised) |
| `5d6ee78` | Scanner: 5-min checkpoints (revised again) |
| `aef59a1` | Post-overhaul Jan backtest (identical — scanner data not refreshed) |
| `d0a013f` | **Wire SqueezeDetector into live bot + align exits** |
| `e9b14d1` | Scanner filter parity: all 3 scanners read from .env |
| `a0a7f02` | Scanner checkpoints: manual tuning with 9:30 cutoff |
| `1a5de42` | Commit scanner_results to prevent morning conflicts |

---

## What's Different for Tomorrow

1. **Squeeze is live** — first time ever. Bot can now take squeeze trades via the full pipeline: SqueezeDetector → on_trade_price trigger → trade_manager.on_signal → Alpaca order → _squeeze_manage_exits
2. **Scanner parity** — all 3 scanners read from .env. Should find the same stocks.
3. **No websocket issues** — stale connection cleanup in daily_run.sh
4. **Manual checkpoints** — 12 windows from 7:00 to 9:30 cutoff
5. **Profile X removed** — unknown-float stocks pass through at full notional

---

## Files Changed Today

| File | Changes |
|------|---------|
| bot.py | SqueezeDetector integration (import, detectors, seed, 1m feed, tick trigger, callback) |
| trade_manager.py | TradePlan.setup_type, parse_plan extraction, _squeeze_manage_exits method, sq exit config |
| simulate.py | Bail timer, WB_SQ_ROSS_COEXIST guard lines |
| scanner_sim.py | Checkpoints (manual list), .env parity for gap/price/float thresholds |
| live_scanner.py | .env parity for all filter thresholds, unknown float pass-through |
| .env | WB_CLASSIFIER_ENABLED=0, WB_SQ_ROSS_COEXIST=0, WB_MIN_PM_VOLUME, WB_MAX_SCANNER_SYMBOLS |
| run_jan_v3_comparison.py | V3 runner (SQ+Ross coexist) |
| 7 runner files | Profile X / unknown-float removal |
