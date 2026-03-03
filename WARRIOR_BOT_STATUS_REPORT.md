# Warrior Bot — Project Status Report
## For Claude Code Context Recovery — March 3, 2026

---

## Executive Summary

We've completed a **137-stock L2 study** that definitively answered the question: what types of stocks does this bot trade well? The answer: **micro-float (<5M shares), pre-market (7am scanner) stocks** — 44% win rate, +$24,737 P&L. Everything else is net negative.

This has led to the **Multi-Profile Trading System** — a new architecture where each stock on the watchlist is tagged with a profile code (`:A`, `:B`, `:C`, `:X`) that tells the bot which configuration to use. This eliminates the tug-of-war where tuning for one stock type hurts another.

**Active directive: `MULTI_PROFILE_SYSTEM_DIRECTIVE.md`** — full architecture, profile definitions, and implementation plan.

---

## Current Architecture State

### What Exists in Repo

| Commit | Date | What It Did |
|--------|------|-------------|
| `b9522b4` | Mar 2 | L2 Phase 3: conditional stop tighten + 137-stock full study |
| `4c9126d` | Mar 2 | L2 Phase 3 Directive |
| `4793fe7` | Mar 2 | L2 Phase 2.5: hard gate warmup + stop-tighten disable |
| `178efc8` | Mar 2 | L2 Phase 2.5 Directive |
| `07c6685` | Mar 2 | L2 Deep Dive Phase 1+2 |
| `0b48c24` | Feb 27 | Phase 2.2: Classifier gate + suppression comparison |
| `aa0e12d` | Feb 27 | Phase 2.1: Classifier threshold tuning |
| `8f64b87` | Feb 27 | Phase 2: classifier.py creation |
| `025182ba` | Feb 27 | 108-stock behavior study expansion |

### Current Live Config (.env)

```
WB_EXIT_MODE=signal
WB_CLASSIFIER_ENABLED=1
WB_CLASSIFIER_SUPPRESS_ENABLED=0
WB_CLASSIFIER_VWAP_GATE=7
WB_CLASSIFIER_CASC_VWAP_MIN=8
WB_CLASSIFIER_SMOOTH_VWAP_MIN=10
WB_CLASSIFIER_RECLASS_ENABLED=1
WB_ENABLE_L2=0                           # L2 OFF (will be per-profile)
WB_L2_HARD_GATE_WARMUP_BARS=30           # From Phase 2.5
WB_L2_STOP_TIGHTEN_MIN_IMBALANCE=0.65    # From Phase 3
```

---

## The 137-Stock Study — Key Findings

### Overall Results
- 137 stocks tested, 75 traded, 62 had 0 trades
- **No-L2 baseline: -$196 total P&L** (essentially breakeven)
- **32% win rate** (24 winners, 50 losers)
- **L2 v3: -$7,771** (but 2 outliers account for -$14,101)
- **Excluding outliers: L2 delta = +$6,526**

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

### The Winning Profile (Combined)

| Filter | W/L | WR | P&L |
|---|---|---|---|
| Float < 5M + 7am scanner | 12/15 | **44%** | **+$24,737** |
| Float < 10M + 7am scanner | 13/19 | **41%** | **+$22,931** |
| Everything else | mixed | 24% | -$24,933 |

---

## Multi-Profile System (THE ACTIVE WORK)

### Architecture

Stocks are tagged with profile codes on watchlist add: `SYMBOL:PROFILE_CODE`

### Profiles

| Profile | Tag | Status | Description |
|---|---|---|---|
| A | `:A` (default) | **PROVEN** | Micro-float <5M, 7am scanner, L2 OFF |
| B | `:B` | CANDIDATE | Mid-float 5-50M, 7am scanner, L2 ON |
| C | `:C` | EARLY | Fast movers (HIND/GRI/ELAB), Fast Mode ON |
| X | `:X` | RESERVED | Unknown -- half size, conservative |

### Implementation Phases

1. **Phase 1**: Build profile infrastructure (profiles/ dir, parsing, config loader, --profile flag)
2. **Phase 2**: Lock in Profile A (extract current config, regression test)
3. **Phase 3**: Validate Profile B (27 mid-float stocks with L2)
4. **Phase 4**: Validate Profile C (Fast Mode stocks)

**Full details in `MULTI_PROFILE_SYSTEM_DIRECTIVE.md`**

---

## L2 Subsystem Status

### What We Know
- `l2_bearish_exit` is the dominant L2 mechanism (+$19,976 total helped delta across 28 stocks)
- L2 HURTS micro-float (thin order books = unreliable signals)
- L2 HELPS mid/large float (deeper books = accurate signals)
- Optimal float gate: `WB_L2_MIN_FLOAT_M=5` (best improvement: +$4,994)
- `l2_entry.py` standalone strategy: DEAD CODE -- zero unique setups across all tests
- GWAV and BNAI are structurally L2-incompatible (micro-float gap stocks at session open)

### L2 Config (v3, from Phase 3)
```
WB_L2_HARD_GATE_WARMUP_BARS=30
WB_L2_STOP_TIGHTEN_MIN_IMBALANCE=0.65
```

### Going Forward
- L2 will be controlled per-profile (OFF for Profile A, ON for Profile B)
- No more global L2 toggle -- the profile system handles it
- IBKR L2 approval still pending for live data

---

## Classifier Status

### What Works
- **AVOID gate**: +$2,361 net savings, ON for live trading
- **K-means clusters** identified 5 behavior types (cascading, one_big_move, smooth_trend, choppy, early_bird)
- **VWAP distance** = #1 predictor (r = +0.306)

### What Doesn't Work
- **BE suppression**: Net negative (-$1,621) due to threshold being too aggressive
- **5-minute snapshot classification**: Most stocks are "uncertain" at 5 minutes
- **Exit profiles per type**: Theoretically sound but too few stocks affected in practice

### Going Forward
- Classifier stays ON (gate only, no suppression)
- Profile system supersedes the classifier's per-type exit profiles
- The classifier's gate logic may need profile-specific thresholds

---

## Known Issues / Open Items

### 1. QTTB Investigation
- Directive sent earlier, results status unknown
- Check if QTTB_INVESTIGATION_DIRECTIVE.md has been executed

### 2. Duffy (IronClaw AI Agent)
- Deferred until Lima VM isolation configured (security concerns)
- Will be trained as watchlist manager using profile identification rules
- SOUL.md and identity files need to be written once VM is ready

### 3. Entry Timing Problem (TURB example from March 2)
- Bot enters breakouts at exhausted resistance levels
- Classifier correctly doesn't block these (VWAP is strong)
- Needs separate entry quality filter (not part of profile system)

### 4. `WB_MAX_CONSEC_LOSSES=3` -- user put a pin on this
- Even with Level 2 data, consecutive losses can cascade
- Revisit after Profile B is validated

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

### Profile B (TBD -- add after validation)

| Stock | Date | Expected P&L | Notes |
|-------|------|-------------|-------|
| ANPA | 2026-01-09 | +$5,091 | With L2 enabled |

---

## User Preferences (CRITICAL)

- **Signal mode cascading exits must NEVER be suppressed** -- this is the bot's core edge
- "I want 100 $6K winners, not one $90K winner every few weeks"
- Scanner appearance TIME matters -- if bot took profits before scanner appearance, that P&L doesn't count
- "We don't care about the initial run. The initial runner sets off our alert, then we take that 9-12k and move on"
- January was hot, February was cold -- sample from both to avoid bias
- For anything needing direct machine access, update this status document with solid direction
- User confirmed they cannot run backtests from Perplexity's end (no Alpaca API keys here)
- VERO/GWAV/ANPA regression benchmarks may need to evolve as profiles are tuned
- **"I'd rather have consistent $200-500 hits every day than losing 20k"** -- drives the multi-profile approach
- **Multi-profile system is the strategic direction** -- don't tune global settings, tune per-profile

---

## File Map

| File | Purpose |
|------|---------|
| `MULTI_PROFILE_SYSTEM_DIRECTIVE.md` | **ACTIVE DIRECTIVE** -- full profile system architecture |
| `WARRIOR_BOT_STATUS_REPORT.md` | This file -- context recovery |
| `profiles/A.json` | Profile A config (to be created) |
| `profiles/B.json` | Profile B config (to be created) |
| `classifier.py` | StockClassifier -- AVOID gate, behavior types |
| `simulate.py` | Main simulation engine |
| `l2_signals.py` | L2 signal processing |
| `l2_entry.py` | L2 entry strategy (DEAD CODE) |
| `study_data/*.json` | Raw per-stock study data |
| `L2_FULL_STUDY_RESULTS.md` | 137-stock L2 study results |
| `L2_INFRASTRUCTURE_AUDIT.md` | 547-line L2 code audit |

---

## Immediate Priorities

1. **EXECUTE `MULTI_PROFILE_SYSTEM_DIRECTIVE.md`** -- Phase 1 (infrastructure) + Phase 2 (Profile A lock-in)
2. Do NOT touch Profile A trading logic -- just formalize what already works
3. After Phase 2: move to Phase 3 (Profile B validation with L2)
4. Check QTTB_INVESTIGATION_DIRECTIVE.md status

---

*Report updated by Perplexity Computer -- March 3, 2026, 5:48 AM MST*
*Active workstream: Multi-Profile Trading System*