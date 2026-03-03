# Warrior Bot — Project Status Report
## For Claude Code Context Recovery — March 3, 2026 (12:00 PM MST Update)

---

## Executive Summary

We've completed a **137-stock L2 study** that definitively answered the question: what types of stocks does this bot trade well? The answer: **micro-float (<5M shares), pre-market (7am scanner) stocks** — 44% win rate, +$24,737 P&L.

This led to the **Multi-Profile Trading System** — each stock on the watchlist is tagged with a profile code (`:A`, `:B`, `:C`, `:X`) that tells the bot which configuration to use.

**Full 137-stock backtest COMPLETE** — Profile A+B corrected view: **+$30,606** vs baseline -$196. Profile X saves money but is net negative (-$6,038). Decision: skip X in live trading, trade only A+B.

**CRITICAL LIVE TRADING BUGS FOUND** — EDSA 2026-03-03 live trade revealed two blockers:
1. **Reconcile clears positions during Alpaca propagation delay** — BLOCKER for live
2. **No trailing stop system** — position went from +$7,418 unrealized to +$4,533 realized

Both have directives written. **Reconcile fix must be done before tomorrow's live session.**

---

## Current Architecture State

### Recent Commits

| Commit | Date | What It Did |
|--------|------|-------------|
| `7a1f7ae` | Mar 3 | **CRITICAL: Reconcile grace period + trailing stop directive** |
| `2a11c6c` | Mar 3 | EDSA trade report: reconcile bug + trailing stop investigation |
| `f435705` | Mar 3 | Full 137-stock profile backtest: A+B validated, X skipped |
| `a9bdcaa` | Mar 3 | Profile C Validation: NOT VALIDATED |
| `47c39a4` | Mar 3 | Profile C Validation Directive + Status Report update |
| `1ac601e` | Mar 3 | Profile B Validation: VALIDATED |
| `2175c22` | Mar 3 | Phase 1: Multi-Profile Trading System infrastructure |

### Current Live Config (.env)

```
WB_EXIT_MODE=signal
WB_CLASSIFIER_ENABLED=1
WB_CLASSIFIER_SUPPRESS_ENABLED=0
WB_ENABLE_L2=0
WB_L2_HARD_GATE_WARMUP_BARS=30
WB_L2_STOP_TIGHTEN_MIN_IMBALANCE=0.65
```

---

## Multi-Profile System

### Profile Status

| Profile | Tag | Status | Description |
|---|---|---|---|
| A | `:A` (default) | **PROVEN** ✅ | Micro-float <5M, 7am scanner, L2 OFF, 44% WR, +$24,737 |
| B | `:B` | **VALIDATED** ✅ | Mid-float 5-50M, 7am scanner, L2 ON, +$4,859 Databento |
| C | `:C` | **NOT VALIDATED** ❌ | Fast Mode found 0 new trades, broke VERO by -$8,713. Do not use. |
| X | `:X` | **TESTED — SKIP IN LIVE** ⚠️ | -$6,038 but saves $16,290 vs uncontrolled. Skip in live. |

### Full 137-Stock Backtest Results (commit `f435705`)

**CRITICAL**: Databento ticks break Profile A. Profile A must use Alpaca ticks.

**Corrected View:**
- **Profile A + B only**: +$30,606 (baseline: -$196)
- **Profile X**: -$6,038 (saves $16,290 vs uncontrolled)
- **Decision**: Trade only A+B in live. Skip X.

### Scanner Time Window Finding
- SPRC (07:02, 0.4M float): should be Profile A — +$3,454
- STSS (07:01, 20.3M): should be Profile B
- **Directive**: `SCANNER_TIME_WINDOW_DIRECTIVE.md` — widen to 07:00-07:14

---

## EDSA Live Trade — Critical Bugs (March 3, 2026)

EDSA: 7,293 shares @ $3.03, stop $2.92, R=$0.11

### Bug 1: Reconcile Clears Position (CRITICAL BLOCKER)
- Alpaca propagation delay: reconcile saw alp_qty=0, cleared bot's 7,293 shares
- Position unmanaged 3+ hours. Stop never fired despite price hitting $2.774
- **Fix**: 60-second grace period. **Directive**: `RECONCILE_AND_TRAILING_STOP_DIRECTIVE.md`

### Bug 2: No Trailing Stop (HIGH)
- +$7,418 unrealized → +$4,533 realized (gave back ~$2,900)
- **Fix**: R-multiple trailing: 2R→BE, 4R→+1R, 6R→trail $0.15
- Env-gated, OFF by default. **Directive**: `RECONCILE_AND_TRAILING_STOP_DIRECTIVE.md`

### Bug 3: Bearish Engulfing First-Bar Sensitivity (MEDIUM — DEFERRED)
- Entered $3.00, exited $2.97 after 1 min, recovered to $3.19 next bar

### EDSA Final P&L: +$4,533

---

## The 137-Stock Study — Key Findings

### Float Is Everything

| Float Bucket | Stocks | No-L2 P&L | L2 Delta | Bot Verdict |
|---|---|---|---|---|
| < 5M (micro) | 34 | **+$20,344** | **-$12,569** | Bot WINS here, L2 HURTS |
| 5-10M (small) | 11 | -$2,357 | +$663 | L2 slight help |
| 10-50M (mid) | 16 | -$12,536 | +$1,231 | L2 helps |
| > 50M (large) | 14 | -$5,647 | +$3,100 | L2 helps most |

### Scanner Time Is Everything

| Scanner Time | W/L | Win Rate | P&L |
|---|---|---|---|
| 7:00 AM | 17/28 | **38%** | **+$20,452** |
| 8:00-8:59 | 4/12 | 25% | -$14,022 |
| 9:00+ | 3/9 | 25% | -$5,554 |

---

## Regression Benchmarks

### Profile A (use Alpaca ticks, NOT Databento)

| Stock | Date | Expected P&L | Notes |
|-------|------|-------------|-------|
| VERO | 2026-01-16 | +$6,890 | Cascading, 4 trades |
| GWAV | 2026-01-16 | +$6,735 | Early bird, 2 trades |
| APVO | 2026-01-09 | +$7,622 | Single massive winner |
| BNAI | 2026-01-28 | +$5,610 | 4-trade cascading |
| MOVE | 2026-01-27 | +$5,502 | 3-trade runner |
| ANPA | 2026-01-09 | +$2,088 | One_big_move (no-L2 baseline) |

### Profile B (use Databento ticks)

| Stock | Date | Expected P&L | Notes |
|-------|------|-------------|-------|
| ANPA | 2026-01-09 | +$5,091 | `--profile B --ticks` |
| BATL | 2026-02-27 | +$4,522 | `--profile B --ticks` |

---

## Immediate Priorities

1. **CRITICAL — Reconcile grace period fix** — BLOCKER. See `RECONCILE_AND_TRAILING_STOP_DIRECTIVE.md`
2. **HIGH — Trailing stop system** — See `RECONCILE_AND_TRAILING_STOP_DIRECTIVE.md`
3. **MEDIUM — Scanner time window** — See `SCANNER_TIME_WINDOW_DIRECTIVE.md`
4. **Tomorrow (Tue March 4)**: Live session — requires reconcile fix minimum

---

## Known Issues / Open Items

1. **Duffy/IronClaw**: Deferred until Lima VM isolation configured
2. **WB_MAX_CONSEC_LOSSES=3**: Pinned, revisit after trailing stop
3. **IBKR L2 Approval**: Pending for live Profile B
4. **Databento Cost**: ~$0.023/stock historical, live TBD
5. **Profile A = Alpaca ticks only** (methodology, not bug)
6. **Bearish engulfing sensitivity**: Deferred, needs 137-stock analysis
7. **Regression benchmarks may evolve**: User noted

---

## User Preferences (CRITICAL)

- **Signal mode cascading exits must NEVER be suppressed**
- "I want 100 $6K winners, not one $90K winner every few weeks"
- Scanner TIME matters — pre-scanner profits don't count
- Sample from both hot (Jan) and cold (Feb) markets
- For machine work, update this status doc with direction
- Cannot run backtests from Perplexity (no Alpaca API keys)
- **"Consistent $200-500 hits > losing 20k then one 5k hit"**
- Multi-profile is the strategic direction
- **"Let's leave nothing on the table!"**

---

## File Map

| File | Purpose |
|------|---------|
| `RECONCILE_AND_TRAILING_STOP_DIRECTIVE.md` | **ACTIVE — CRITICAL** |
| `SCANNER_TIME_WINDOW_DIRECTIVE.md` | **ACTIVE — MEDIUM** |
| `EDSA_TRADE_REPORT_20260303.md` | EDSA live trade analysis |
| `FULL_PROFILE_BACKTEST_RESULTS.md` | 137-stock results |
| `PROFILE_C_VALIDATION_RESULTS.md` | Profile C (NOT validated) |
| `PROFILE_B_VALIDATION_RESULTS.md` | Profile B (validated) |
| `MULTI_PROFILE_SYSTEM_DIRECTIVE.md` | Profile system architecture |
| `WARRIOR_BOT_STATUS_REPORT.md` | This file |
| `profiles/A.json`, `B.json`, `C.json`, `X.json` | Profile configs |
| `profile_manager.py` | Profile parsing/apply/restore |
| `simulate.py` | Sim engine (`--profile` flag) |
| `classifier.py` | StockClassifier — AVOID gate |

---

*Report updated by Perplexity Computer — March 3, 2026, 12:00 PM MST*
*Active workstream: Reconcile fix (BLOCKER) → Trailing stop → Scanner window widening*
