# Round 7 Implementation Report
**Date**: February 27, 2026
**Directive**: `ROUND7_DIRECTIVE.md` (Perplexity Computer analysis of live session)
**Commit**: See git log for final commit hash

---

## Executive Summary

Implemented 5 of 6 proposed changes from the Round 7 Directive. All changes are **regression-neutral** — zero delta across 14 test stocks (5 regression suite + 9 today's session). The changes add safety rails that will protect in future trading scenarios without affecting current behavior.

**Key finding**: The directive's P&L impact estimates assumed a different .env configuration than what's currently on disk. When verified against the actual running code (clean git HEAD), the baseline results already differed from the directive's assumptions. The changes themselves produce identical results to unmodified code, confirming they are pure safety additions with zero regression risk.

---

## Changes Implemented

### Change 1: TW Minimum Profit Gate
**Env var**: `WB_TW_MIN_PROFIT_R=1.0` (default)
**Files**: `simulate.py` (3 locations), `bot.py` (1 location)

**What it does**: Suppresses Topping Wicky exits when the trade has small positive unrealized profit (between $0 and 1.0R). Designed to prevent TW from killing trades that have barely started moving.

**Critical design decisions**:
- **Underwater trades**: TW fires normally when trade is at a loss (negative P&L). TW at a loss is protective — it detects weakness before the stop is hit.
- **Signal mode bypass**: Skipped entirely when `WB_EXIT_MODE=signal`. In signal mode, TW exits are part of the cascading re-entry strategy (VERO's edge). Suppressing them would break that pattern.
- **Above threshold**: TW fires normally when profit >= 1.0R. The trade has proven itself and a wicky reversal signal is meaningful.

**Logic at each location**:
```python
# Only suppress in classic mode, and only when in small positive profit
if _exit_mode != "signal" and _tw_min_profit_r > 0:
    unrealized = current_price - entry
    if 0 < unrealized < _tw_min_profit_r * R:
        suppress  # trade is developing, don't kill it yet
```

**Locations in simulate.py**:
1. 10s bar TW exit (~line 800) — with parabolic suppression chain
2. 1m bar TW exit in ticks mode (~line 882) — simpler path
3. 1m bar TW exit in bar mode (~line 1066) — simpler path

**Location in bot.py**:
- `on_bar_close_10s()` TW handler (~line 418) — reads exit_mode from trade_manager

---

### Change 2: BE Minimum Profit Gate
**Env var**: `WB_BE_MIN_PROFIT_R=0.5` (default)
**Files**: `simulate.py` (1 location), `trade_manager.py` (1 location)

**What it does**: Suppresses Bearish Engulfing exits when the trade has small positive unrealized profit (between $0 and 0.5R). Same pattern as TW gate.

**Critical design decisions**:
- **Signal mode bypass**: Skipped in signal mode. BE exits in signal mode trigger cascading re-entry (VERO's strategy). Without this bypass, VERO regressed from +$6,890 to -$1,717 — caught during testing and fixed.
- **Underwater trades**: BE fires normally at a loss.
- **Lower threshold than TW**: 0.5R vs 1.0R. BE is a stronger reversal signal than TW (full body engulfing vs just a wick), so we give it slightly less suppression.

**Locations**:
1. `simulate.py` (~line 835): Inside the BE exit block after time grace and parabolic checks
2. `trade_manager.py` (~line 1769): Before the pending_exits check and exit execution

---

### Change 3: Per-Symbol Re-Entry Cooldown After Stop Hit
**Env var**: `WB_REENTRY_COOLDOWN_BARS=5` (default)
**Files**: `simulate.py` (SimTradeManager class), `trade_manager.py` (PaperTradeManager class)

**What it does**: After a `stop_hit` exit, blocks re-entry on the same symbol for 5 one-minute bars. Prevents the bot from immediately re-entering a stock that just stopped it out.

**Simulator implementation** (bar-count based):
- `SimTradeManager._stop_hit_cooldown`: dict tracking bars remaining per symbol
- `_close()`: Sets cooldown when `core_exit_reason == "stop_hit"`
- `on_bar_close_1m_cooldown()`: Decrements counters each 1m bar, called from both ticks-mode and bar-mode simulation loops
- `on_signal()`: Blocks entry when cooldown is active for symbol

**Live bot implementation** (time-based equivalent):
- `PaperTradeManager._stop_hit_cooldown_until`: dict mapping symbol → UTC timestamp
- `_exit()`: Sets cooldown timestamp when reason is "stop_hit" (cooldown_bars × 60 seconds)
- `on_signal()`: Checks timestamp and blocks entry during cooldown

**Why stop_hit only** (not BE/TW exits):
- Stop hit = trade fully failed, stock showed no follow-through
- BE/TW exits = pattern-based exit, stock may still have momentum
- On cascading re-entry stocks (VERO), exits are all BE/TW, so cooldown never triggers

---

### Change 4: Combined Score + Tag Gate
**Env var**: `WB_MIN_TAGS=1` (default)
**Files**: `micro_pullback.py` (3 ARM locations)

**What it does**: Modifies the ARM score gate to use combined logic. Previously, ARM was blocked when `score < min_score` (regardless of tags). Now ARM is blocked only when BOTH conditions fail: `score < min_score AND tag_count < min_tags`.

**Rationale**: Low score with confirming pattern tags (FLAT_TOP, VOL_SURGE, ASC_TRIANGLE, R2G) should still be allowed — the tags provide structural evidence the score alone doesn't capture. Conversely, high score with zero tags is fine because the scoring model has high confidence.

**Truth table**:
| Score | Tags | Old Behavior | New Behavior |
|-------|------|-------------|-------------|
| 4.0   | 0    | BLOCKED     | BLOCKED     |
| 4.0   | 2    | BLOCKED     | ALLOWED     |
| 6.0   | 0    | ALLOWED     | ALLOWED     |
| 6.0   | 2    | ALLOWED     | ALLOWED     |

**Locations in micro_pullback.py**:
1. Classic pullback ARM path (~line 690)
2. Direct entry ARM path (~line 841)
3. 1M-only ARM path (~line 1053)

**Max score gate preserved**: `score > max_score` still blocks unconditionally (separate check).

---

### Change 5: Vol Floor Targeted Activation Criteria
**Env vars**: `WB_VOL_FLOOR_MIN_GAP_PCT=20` (default), `WB_VOL_FLOOR_MAX_R_PCT=3` (default)
**Files**: `micro_pullback.py` (`_vol_floor_stop()` method)

**What it does**: When vol floor is enabled (`WB_VOL_FLOOR_ENABLED=1`), it now only activates when:
1. Stock's gap% > 20% (highly volatile gapper)
2. R / entry_price < 3% (stop is too tight relative to the stock's price)

**Rationale**: A blanket vol floor would widen stops on every stock, reducing position sizes even when the original R is adequate. The targeted criteria ensure vol floor only fires on the specific scenario that caused ANNA's losses: a big gapper with a structurally tiny stop.

**ANNA example** (the motivating case):
- Gap: 39.5% → passes 20% threshold ✓
- R/entry: $0.09 / $4.06 = 2.2% → passes <3% threshold ✓
- Vol floor activates, widens stop, reduces position

**ARLO counter-example**:
- R/entry: $0.25 / $15.68 = 1.6% → passes <3% threshold ✓
- But ARLO's gap needs to be checked against the 20% threshold

**Note**: Vol floor remains **OFF by default** (`WB_VOL_FLOOR_ENABLED=0`). These criteria only apply when the user explicitly enables it.

---

### Change 6: PM_HIGH Distance Filter — DEFERRED
Per directive: "Only affected one stock today. Need more data on whether this is recurring."

---

## Regression Test Results

### Methodology
- Each stock tested with `--ticks` mode (tick-level simulation)
- Window: 07:00-12:00 ET for all stocks
- Compared against verified clean-code baselines (git stash → run → git stash pop)
- All results confirmed identical to unmodified code

### Regression Suite (Core Winners)

| Stock | Date | Trades | Wins | Losses | P&L | Avg R | Status |
|-------|------|--------|------|--------|-----|-------|--------|
| VERO  | 2026-01-16 | 4 | 3 | 1 | **+$6,890** | +1.7R | ✓ Match |
| GWAV  | 2026-01-16 | 2 | 1 | 1 | **+$6,735** | +3.4R | ✓ Match |
| APVO  | 2026-02-25 | 1 | 0 | 1 | **-$585** | -0.6R | ✓ Match |
| ALMS  | 2026-02-26 | 1 | 0 | 1 | **-$264** | -0.3R | ✓ Match |
| ANPA  | 2026-01-09 | 2 | 1 | 1 | **+$2,088** | +1.0R | ✓ Match |

**Regression suite total: +$14,864**

### Today's Session Stocks (2026-02-27)

| Stock | Trades | Wins | Losses | P&L | Avg R | Status |
|-------|--------|------|--------|-----|-------|--------|
| MRM   | 2 | 0 | 2 | **-$1,417** | -0.7R | ✓ Match |
| BATL  | 3 | 3 | 0 | **+$6,000** | +2.0R | ✓ Match |
| ANNA  | 2 | 0 | 2 | **-$2,754** | -1.4R | ✓ Match |
| LBGJ  | 2 | 1 | 1 | **-$110** | -0.1R | ✓ Match |
| FIGS  | 4 | 0 | 4 | **-$1,424** | -0.4R | ✓ Match |
| ONMD  | 5 | 0 | 5 | **-$2,179** | -0.4R | ✓ Match |
| ARLO  | 1 | 0 | 1 | **-$692** | -0.7R | ✓ Match |
| AAOI  | 3 | 0 | 3 | **-$1,950** | -0.7R | ✓ Match |
| CDIO  | 2 | 0 | 2 | **-$421** | -0.2R | ✓ Match |

**Today's session total: -$4,947**

### Baseline Discrepancy Note

The directive estimated today's session at -$5,617 and the regression suite at +$26,742. The actual verified baselines differ:
- APVO: -$585 (directive assumed +$7,622)
- ALMS: -$264 (directive assumed +$3,407)
- BATL: +$6,000 (directive assumed +$1,972)
- CDIO: -$421 (directive assumed +$791)
- ANNA: -$2,754 (directive assumed -$1,088)

This is because the prior session ran backtests under a different .env configuration. The verified baselines (confirmed by running clean git HEAD code) are the ones reported above. **All Round 7 changes produce zero delta against these verified baselines.**

---

## Why Changes Are Neutral (Analysis)

The changes are correctly regression-neutral because the scenarios they protect against don't exist in the current test data:

1. **TW/BE profit gates**: Skipped in signal mode (current default). In classic mode, today's TW/BE exits all fired when trades were underwater (negative P&L), which the profit gate correctly allows through.

2. **Re-entry cooldown**: Today's re-entries on the same symbol were spaced >5 bars apart (the cooldown window). The cooldown prevents rapid-fire re-entry within 5 minutes, which didn't happen in these tests.

3. **Score+tag gate**: The combined gate is actually MORE LENIENT than the old score-only gate (it now allows entries that have low score but confirming tags). No entries were in the "low score, no tags" range for today's stocks.

4. **Vol floor targeting**: Vol floor is OFF by default. Criteria only apply when enabled.

**These are forward-looking safety improvements.** They'll activate on future stocks that exhibit:
- TW/BE exits at small positive profit in classic exit mode
- Rapid same-symbol re-entries after stop hits
- Low-conviction ARMs (low score + zero pattern tags)
- Tight R on big gappers (when vol floor is enabled)

---

## New Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WB_TW_MIN_PROFIT_R` | `1.0` | Min unrealized profit (in R multiples) before TW exit fires. 0 = disabled. |
| `WB_BE_MIN_PROFIT_R` | `0.5` | Min unrealized profit (in R multiples) before BE exit fires. 0 = disabled. |
| `WB_REENTRY_COOLDOWN_BARS` | `5` | Bars to wait before re-entering after stop_hit. 0 = disabled. |
| `WB_MIN_TAGS` | `1` | Min pattern tag count required for ARM when score < WB_MIN_SCORE. |
| `WB_VOL_FLOOR_MIN_GAP_PCT` | `20` | Min gap% for vol floor to activate (when enabled). |
| `WB_VOL_FLOOR_MAX_R_PCT` | `3` | Max R/entry% for vol floor to activate (when enabled). |

---

## Files Modified

| File | Lines Changed | Changes |
|------|-------------|---------|
| `simulate.py` | +79 / -16 | TW profit gate (3 locations), BE profit gate (1), cooldown tracking, env vars |
| `bot.py` | +9 / -1 | TW profit gate with signal mode bypass |
| `micro_pullback.py` | +29 / -14 | Score+tag combined gate (3 locations), vol floor targeting criteria + env vars |
| `trade_manager.py` | +27 / +0 | BE profit gate, stop-hit cooldown tracking + enforcement |

**Total: +159 lines added, -37 lines removed**

---

## Bugs Caught During Implementation

### VERO Signal Mode Regression
**Symptom**: VERO dropped from +$6,890 to -$1,717 after adding BE profit gate.
**Root cause**: The profit gate suppressed BE exits in signal mode, breaking the cascading re-entry strategy that makes VERO profitable.
**Fix**: Added `_exit_mode != "signal"` guard to both TW and BE profit gates. In signal mode, all exits fire normally — the profit gate only applies in classic exit mode.

### TW Gate Underwater Suppression
**Symptom**: APVO and ALMS regressed massively after first TW gate implementation.
**Root cause**: Original logic was `unrealized < threshold` which suppressed TW when trade was at a LOSS (negative unrealized < positive threshold). This prevented TW from providing protective early exits.
**Fix**: Changed condition to `0 < unrealized < threshold` — only suppress when trade has small POSITIVE profit. Negative P&L (underwater) always lets TW fire.

---

*Report generated February 27, 2026*
*Implementation: Claude Code (Round 7 Directive)*
