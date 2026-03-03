# Warrior Bot — Project Status Report
## For Claude Code Context Recovery — March 3, 2026 (8:40 AM MST Update)

---

## Executive Summary

We've completed a **137-stock L2 study** that definitively answered the question: what types of stocks does this bot trade well? The answer: **micro-float (<5M shares), pre-market (7am scanner) stocks** — 44% win rate, +$24,737 P&L.

This led to the **Multi-Profile Trading System** — each stock on the watchlist is tagged with a profile code (`:A`, `:B`, `:C`, `:X`) that tells the bot which configuration to use.

**Current status**:
- Phase 1+2 COMPLETE: Infrastructure + Profile A lock-in (commit `2175c22`)
- Phase 3 COMPLETE: **Profile B VALIDATED** (commit `1ac601e`)
- Phase 4 IN PROGRESS: **Profile C validation** — directive in `PROFILE_C_VALIDATION_DIRECTIVE.md`
- **Goal**: All profiles validated today for tomorrow's live session

---

## Current Architecture State

### Recent Commits

| Commit | Date | What It Did |
|--------|------|-------------|
| `1ac601e` | Mar 3 | **Profile B Validation: 27 mid-float stocks — VALIDATED** |
| `34995bc` | Mar 3 | Profile B Validation Directive |
| `2175c22` | Mar 3 | Phase 1: Multi-Profile Trading System infrastructure |
| `0026b5a` | Mar 3 | Multi-Profile directive + status report |
| `b9522b4` | Mar 2 | L2 Phase 3: conditional stop tighten + 137-stock full study |

### Current Live Config (.env)

```
WB_EXIT_MODE=signal
WB_CLASSIFIER_ENABLED=1
WB_CLASSIFIER_SUPPRESS_ENABLED=0
WB_ENABLE_L2=0                           # L2 OFF globally (per-profile via B.json)
WB_L2_HARD_GATE_WARMUP_BARS=30
WB_L2_STOP_TIGHTEN_MIN_IMBALANCE=0.65
```

---

## Multi-Profile System

### Profile Status

| Profile | Tag | Status | Description |
|---|---|---|---|
| A | `:A` (default) | **PROVEN** ✅ | Micro-float <5M, 7am scanner, L2 OFF, 44% WR, +$24,737 |
| B | `:B` | **VALIDATED** ✅ | Mid-float 5-50M, 7am scanner, L2 ON, +$3,157 delta (Alpaca) / +$18,128 delta (Databento) |
| C | `:C` | **IN PROGRESS** 🔄 | Fast movers, Fast Mode ON, L2 OFF — `PROFILE_C_VALIDATION_DIRECTIVE.md` |
| X | `:X` | RESERVED | Unknown — max 2 entries, conservative |

### Profile B Key Findings (commit `1ac601e`)
- **All improvement from 7am scanner stocks** (+$3,158 delta)
- Non-7am mid-float stocks are flat — skip them entirely
- Max entries=3 is net positive (+$1,396)
- AZI (44.5M) and CRSR (46.6M) are known L2 losers — tag `:X` or skip
- simulate.py now auto-enables L2 from profile env var
- Full results in `PROFILE_B_VALIDATION_RESULTS.md`

### Profile B Regression Benchmarks
| Stock | Date | Command | Expected P&L |
|-------|------|---------|-------------|
| ANPA | 2026-01-09 | `--profile B --ticks` | +$5,091 |
| BATL | 2026-02-27 | `--profile B --ticks` | +$4,522 |

### Profile C Validation Plan
- 31 zero-trade 7am micro-float stocks to test with Fast Mode
- 6 Profile A regression checks (Fast Mode must not break winners)
- Full plan in `PROFILE_C_VALIDATION_DIRECTIVE.md`

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

### Profile A (MUST ALWAYS PASS)

| Stock | Date | Expected P&L | Notes |
|-------|------|-------------|-------|
| VERO | 2026-01-16 | +$6,890 | Cascading, 4 trades |
| GWAV | 2026-01-16 | +$6,735 | Early bird, 2 trades |
| APVO | 2026-01-09 | +$7,622 | Single massive winner |
| BNAI | 2026-01-28 | +$5,610 | 4-trade cascading |
| MOVE | 2026-01-27 | +$5,502 | 3-trade runner |
| ANPA | 2026-01-09 | +$2,088 | One_big_move (no-L2 baseline) |

### Profile B (VALIDATED)

| Stock | Date | Expected P&L | Notes |
|-------|------|-------------|-------|
| ANPA | 2026-01-09 | +$5,091 | `--profile B --ticks` |
| BATL | 2026-02-27 | +$4,522 | `--profile B --ticks` |

### Profile C (TBD — add after validation)

---

## Immediate Priorities

1. **EXECUTE `PROFILE_C_VALIDATION_DIRECTIVE.md`** — 31 zero-trade stocks + 6 regressions
2. After Profile C: run **last Friday's session** and **Monday's session** with all profiles active
3. **Tomorrow (Wed March 4)**: First live multi-profile session

---

## Known Issues / Open Items

### 1. Duffy (IronClaw AI Agent)
- Deferred until Lima VM isolation configured
- Will be trained as watchlist manager using profile identification rules

### 2. `WB_MAX_CONSEC_LOSSES=3` — user put a pin on this
- Revisit after all profiles validated

### 3. IBKR L2 Approval
- Still pending for live L2 data (Profile B needs this for live trading)

### 4. Databento Cost
- ~$0.023/stock for historical L2 data
- Live feed cost TBD

---

## User Preferences (CRITICAL)

- **Signal mode cascading exits must NEVER be suppressed** — this is the bot's core edge
- "I want 100 $6K winners, not one $90K winner every few weeks"
- Scanner appearance TIME matters — if bot took profits before scanner appearance, that P&L doesn't count
- January was hot, February was cold — sample from both to avoid bias
- For anything needing direct machine access, update this status document with solid direction
- User confirmed they cannot run backtests from Perplexity's end (no Alpaca API keys here)
- **"I'd rather have consistent $200-500 hits every day than losing 20k"**
- **Multi-profile system is the strategic direction** — don't tune global settings, tune per-profile
- **Goal: all profiles validated by March 3 for March 4 live session**

---

## File Map

| File | Purpose |
|------|---------|
| `PROFILE_C_VALIDATION_DIRECTIVE.md` | **ACTIVE DIRECTIVE** |
| `PROFILE_B_VALIDATION_RESULTS.md` | Profile B results (validated) |
| `PROFILE_B_VALIDATION_DIRECTIVE.md` | Profile B directive (completed) |
| `MULTI_PROFILE_SYSTEM_DIRECTIVE.md` | Full profile system architecture |
| `WARRIOR_BOT_STATUS_REPORT.md` | This file — context recovery |
| `profiles/A.json`, `B.json`, `C.json`, `X.json` | Profile configs |
| `profile_manager.py` | Profile parsing/apply/restore |
| `simulate.py` | Sim engine (supports `--profile` flag) |
| `classifier.py` | StockClassifier — AVOID gate |

---

*Report updated by Perplexity Computer — March 3, 2026, 8:40 AM MST*
*Active workstream: Profile C Validation → Full Session Replay*
