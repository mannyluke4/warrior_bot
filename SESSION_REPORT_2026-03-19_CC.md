# CC Session Report — 2026-03-19

## Machine: Mac Mini (CC Opus)
## Branch: v6-dynamic-sizing

---

## Directives Completed

### 1. DIRECTIVE_VERBOSE_SIMS.md

Ran 6 verbose tick-mode simulations to capture detector state changes for Cowork analysis of re-entry opportunities.

| Stock | Date | Ticks | Result | Key Finding |
|-------|------|-------|--------|-------------|
| VERO | Jan 16 | 1,696,214 | +$18,583 (18.6R) | After $5.81 exit, detector hit repeated RESETs (MACD bearish, topping wicky, trend down) — never re-armed despite run to $12+ |
| ROLR | Jan 14 | 878,325 | +$6,444 (6.5R) | 4 ARMs, 2 signals, 1 entry. Post-exit RESETs visible in 181-line log |
| SXTC | Jan 8 | 219,858 | +$2,213 (2 trades) | Cascading re-entry **worked** — the success case for comparison |
| ARTL | Mar 18 | 555,135 | +$922 (0.9R) | TW exit at $7.915, stock continued to $8.19+ |
| INKT | Mar 10 | 316,156 | -$349 (-0.3R) | BE exit, not max_loss — single ARM/signal |
| FUTG | Jan 2 | 312 | -$1,538 (-1.6R) | Max loss hit, only 312 ticks (very thin data) |

**Logs committed**: `verbose_logs/*.log` (force-added past .gitignore)

---

### 2. DIRECTIVE_MP_REFINEMENTS_V1.md

Three changes to support multi-strategy architecture and filter illiquid stocks.

#### Change 1: `WB_MIN_SESSION_VOLUME` Gate
- Blocks ARM on stocks with insufficient cumulative 1m bar volume
- Added to all 3 ARM paths: 10s `on_bar_close`, 1m direct entry, 1m pullback entry
- **OFF by default** (`0`). Enable with e.g. `WB_MIN_SESSION_VOLUME=10000`
- Tested: gate fires correctly (FUTG blocked at 100K threshold, VERO/ROLR/SXTC unaffected)
- **Note**: FUTG has 72K bar volume despite only 312 ticks — the 10K default won't block it. Tick count was misleading; bar volumes show real liquidity. Threshold may need tuning, or consider a tick-count-based gate instead.

#### Change 2: `setup_type` Field (Always-On Metadata)
- Added `setup_type: str = "micro_pullback"` to:
  - `SimTrade` (simulate.py)
  - `OpenTrade` (trade_manager.py)
  - `PendingEntry` (trade_manager.py)
- Propagated through all `OpenTrade` creation paths (3 sites in trade_manager.py)
- Logged in `position_closed` events in bot.py

#### Change 3: `setup_type` in Backtest State JSON
- Added `"setup_type": "micro_pullback"` to trade dicts in `run_ytd_v2_backtest.py`
- Future strategy modules will set their own type

**Regression**: VERO +$18,583, ROLR +$6,444 — both pass.

---

### 3. DIRECTIVE_SQUEEZE_V1.md

Full implementation of Strategy 2: Squeeze/Breakout entry module across 4 phases.

#### Phase 1: `squeeze_detector.py` (New File)
- **State machine**: IDLE → PRIMED → ARMED → TRIGGERED
- **PRIMED** on: volume explosion (3x avg + 50K min), green bar, body >= 1.5%, price > VWAP
- **ARMED** on: key level break (PM high, whole dollar, PDH — configurable priority via `WB_SQ_LEVEL_PRIORITY`)
- **Stop**: `min(low of last 3 bars before breakout)`, capped at `min(WB_SQ_MAX_R, 5% of price)`
- **Probe sizing**: 0.5x on first attempt, full size after first winner
- **Max attempts**: 3 per stock per day
- **Scoring**: base 5.0 + volume bonus + PM bull flag (+2) + gap 20%+ (+1) + VWAP distance (+1) + PM high break (+1), cap 15.0

#### Phase 2: Squeeze Exit Logic in `SimTradeManager`
- **Pre-target (full position)**:
  - Hard stop, max loss cap (same as MP)
  - Trailing stop: 1.5R below peak
  - Time stop: 5 bars no new high
  - VWAP loss: 1m close below VWAP
- **Post-target (core + runner split)**:
  - Core (75%) exits at 2.0R target
  - Runner (25%) trails at 2.5R below peak
  - Runner also exits on VWAP loss or time stop
- **Routed by `setup_type`** — MP exits completely untouched

#### Phase 3: Simulator Wiring
- Both detectors consume same bar/tick feed
- Squeeze trigger checked **before** MP (priority)
- 10s pattern exits (TW, BE) skip squeeze trades
- After squeeze exit, MP can ARM for continuation
- Trade close notifies both detectors (quality gate + squeeze attempt tracking)

#### Phase 4: Validation Results

**Regression (squeeze OFF)**:
- VERO: +$18,583 — pass
- ROLR: +$6,444 — pass

**VERO with squeeze ON**:
| # | Time | Entry | Exit | Reason | P&L | Type |
|---|------|-------|------|--------|-----|------|
| 1 | 07:14 | $3.58 | $5.81 | bearish_engulfing_exit_full | +$18,583 | micro_pullback |
| 2 | 10:08 | $6.85 | $7.51 | sq_target_hit | +$1,259 | squeeze |
| **Total** | | | | | **+$19,842** | |

Squeeze is additive: MP captured the big move, squeeze caught a second-leg breakout for +$1,259.

**ARTL with squeeze ON**:
- Squeeze PRIMED 6 times but R-cap blocked all ARM attempts (parabolic move = consolidation lows too far from entry)
- MP trade unaffected: +$922
- R-cap working as designed — protects against outsized risk on volatile first legs

---

## Env Vars Added This Session

### MP Refinements
| Var | Default | Purpose |
|-----|---------|---------|
| `WB_MIN_SESSION_VOLUME` | `0` (off) | Minimum cumulative 1m bar volume before ARM allowed |

### Squeeze Detector
| Var | Default | Purpose |
|-----|---------|---------|
| `WB_SQUEEZE_ENABLED` | `0` (off) | Master gate for squeeze detector |
| `WB_SQ_VOL_MULT` | `3.0` | Bar volume must be Nx average to qualify |
| `WB_SQ_MIN_BAR_VOL` | `50000` | Minimum absolute bar volume |
| `WB_SQ_MIN_BODY_PCT` | `1.5` | Minimum bar body as % of price |
| `WB_SQ_PRIME_BARS` | `3` | Max bars in PRIMED state before reset |
| `WB_SQ_MAX_R` | `0.80` | Max R (risk per share) allowed |
| `WB_SQ_LEVEL_PRIORITY` | `pm_high,whole_dollar,pdh` | Order to check breakout levels |
| `WB_SQ_PM_CONFIDENCE` | `1` | Use PM behavior to boost score |
| `WB_SQ_MAX_ATTEMPTS` | `3` | Max squeeze attempts per stock per day |
| `WB_SQ_PROBE_SIZE_MULT` | `0.5` | First attempt = half size |
| `WB_SQ_TRAIL_R` | `1.5` | Pre-target trailing stop in R-multiples |
| `WB_SQ_STALL_BARS` | `5` | Time stop: exit if no new high in N bars |
| `WB_SQ_TARGET_R` | `2.0` | Core profit target in R-multiples |
| `WB_SQ_CORE_PCT` | `75` | % of shares that are core (exit at target) |
| `WB_SQ_RUNNER_TRAIL_R` | `2.5` | Runner trailing stop in R-multiples |
| `WB_SQ_VWAP_EXIT` | `1` | Exit on 1m close below VWAP |

---

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `squeeze_detector.py` | **Created** | ~260 lines |
| `simulate.py` | Modified | +340 lines (squeeze exits, wiring, setup_type) |
| `trade_manager.py` | Modified | +7 lines (setup_type on dataclasses, propagation) |
| `micro_pullback.py` | Modified | +18 lines (session volume gate) |
| `run_ytd_v2_backtest.py` | Modified | +1 line (setup_type in trade dict) |
| `verbose_logs/*.log` | **Created** | 6 files, 611 lines total |

---

## Observations for Cowork

1. **Squeeze R-cap is tight on parabolic stocks**: ARTL and VERO both had squeeze PRIMEs blocked because `min(low of last 3 bars)` produces very wide stops on fast movers. The 5%-of-price cap rejects most first-leg entries. This is conservative by design — may need tuning after broader backtesting.

2. **Squeeze works best on second legs**: VERO's squeeze entry at 10:08 (+$1,259) came after consolidation narrowed the stop distance. The squeeze detector may be more valuable as a "re-entry after pullback" tool than a first-leg catcher.

3. **FUTG volume mismatch**: 312 ticks but 72K bar volume — tick count is misleading for liquidity assessment. Consider a tick-count gate or RVOL-based gate instead of raw volume.

4. **Verbose logs show clear re-entry blockers**: VERO post-exit had MACD bearish cross → topping wicky → trend down chain. ROLR similar. These are legitimate blocks, not bugs — future re-entry capture needs a different strategy module (dip-buy or VWAP reclaim).

---

*Generated by CC (Claude Opus 4.6) on Mac Mini — 2026-03-19*
