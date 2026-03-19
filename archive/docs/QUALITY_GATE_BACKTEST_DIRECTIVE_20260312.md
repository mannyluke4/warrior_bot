# QUALITY GATE BACKTEST DIRECTIVE
## For Claude Code (Duffy) | March 12, 2026

---

## STOP: OLD REGRESSIONS ARE RETIRED

**Do NOT run VERO, GWAV, or ANPA regressions anymore.** Those were Profile A baselines from the old system. Profiles are gone. The scoring gate is gone. The old system is gone. Checking whether new code reproduces old results is counterproductive — it constrains new changes to preserve behavior we deliberately eliminated.

**The new baseline is the 5-date backtest:**

| Date | Trades | Wins | Win Rate | P&L |
|------|--------|------|----------|-----|
| 2025-01-02 | 6 | 2 | 33% | -$755 |
| 2025-11-05 | 2 | 0 | 0% | -$1,029 |
| 2025-11-06 | 6 | 1 | 17% | -$2,436 |
| 2026-01-06 | 5 | 2 | 40% | -$332 |
| 2026-02-03 | 5 | 0 | 0% | -$1,874 |
| **TOTAL** | **24** | **5** | **21%** | **-$6,426** |

Every future change is measured against this table. Better P&L = good. Fewer bad trades = good. Old regressions = irrelevant.

---

## TASK: RUN 5-DATE BACKTEST WITH QUALITY GATES ON

### Step 1: Config Changes

Enable the quality gate and re-entry protection with these settings:

```bash
WB_QUALITY_GATE_ENABLED=1

# Gate 1: Clean Pullback (use defaults)
WB_MAX_PULLBACK_RETRACE_PCT=65
WB_MAX_PB_VOL_RATIO=70
WB_MAX_PB_CANDLES=4

# Gate 2: Impulse Strength (use defaults)
WB_MIN_IMPULSE_PCT=2.0
WB_MIN_IMPULSE_VOL_MULT=1.5

# Gate 3: Volume Dominance — warn/log only (no config needed)

# Gate 4: Price/Float Sweet Spot (use defaults)
WB_PRICE_SWEET_LOW=3.0
WB_PRICE_SWEET_HIGH=15.0

# Gate 5: Re-entry protection — ON, but don't cap total trades
WB_NO_REENTRY_ENABLED=1
WB_MAX_SYMBOL_LOSSES=1       # Block re-entry after 1 loss on a symbol
WB_MAX_SYMBOL_TRADES=10      # Set high — do NOT cap cascading winners
```

**Key change from initial implementation:** `WB_MAX_SYMBOL_TRADES=10` instead of 2. The value of 2 was killing cascading re-entries on winning stocks, which is the bot's core edge. The goal of Gate 5 is to prevent **revenge trading after a loss** — not to cap winners. Ross's #1 loss pattern ($18K across 6 trades) was re-entering the same stock after losing on it.

### Step 2: Run the 5 Dates

Same dates, same parameters as the previous backtest:
- `--ticks --feed alpaca --no-fundamentals`
- Window: 07:00-12:00 ET
- Dates: 2025-01-02, 2025-11-05, 2025-11-06, 2026-01-06, 2026-02-03

### Step 3: Report Format

For each date, report:

**A. Trade-by-trade comparison (gates OFF vs gates ON)**

| Symbol | Gates OFF Result | Gates ON Result | What Changed |
|--------|-----------------|-----------------|--------------|
| AEI | -$1,481 (stop_hit) | [new result] | [which gate filtered or passed it] |
| ... | ... | ... | ... |

**B. Gate activity log**

For each setup that was evaluated by the quality gate, report:
- Symbol
- Which gates it passed
- Which gates it failed (and why — include the actual numbers)
- Whether it was blocked or allowed

Example:
```
MOVE: Gate 1 FAIL (retrace 78% > max 65%) | Gate 2 FAIL (impulse 1.1% < min 2.0%) → BLOCKED
RKLZ: Gate 1 PASS (retrace 42%) | Gate 2 PASS (impulse 3.8%) | Gate 4 PASS ($4.50) → ARMED
```

**C. Summary table**

| Date | Trades (OFF) | Trades (ON) | Filtered | P&L (OFF) | P&L (ON) | Delta |
|------|-------------|-------------|----------|-----------|----------|-------|
| 2025-01-02 | 6 | ? | ? | -$755 | ? | ? |
| ... | | | | | | |
| **TOTAL** | **24** | **?** | **?** | **-$6,426** | **?** | **?** |

**D. Gate hit rate**

| Gate | Times Checked | Times Failed | Trades Blocked | $ Saved (losses avoided) | $ Lost (winners filtered) |
|------|--------------|-------------|----------------|------------------------|--------------------------|
| 1: Clean Pullback | ? | ? | ? | ? | ? |
| 2: Impulse Strength | ? | ? | ? | ? | ? |
| 3: Volume Dominance | ? | ? | (warn only) | N/A | N/A |
| 4: Price/Float | ? | ? | ? | ? | ? |
| 5: No Re-entry | ? | ? | ? | ? | ? |

### Step 4: Do NOT Tune Yet

Run with the default thresholds first. We need to see raw results before adjusting anything. If Gate 1 filters everything, we'll widen the threshold. If Gate 2 lets garbage through, we'll tighten it. But we need data first.

---

## WHAT SUCCESS LOOKS LIKE

- **Fewer trades** (filtering low-quality setups)
- **Higher win rate** (remaining trades are better quality)
- **Less negative P&L** (even if still negative — we're improving, not expecting perfection)
- **Feb 3 should have near-zero trades** (Ross's no-trade day — the bot took 5 losers last time)

We are NOT expecting profitability from this single change. We're expecting the quality gate to **cut the worst trades** while preserving the decent ones. If P&L goes from -$6,426 to -$3,000, that's a significant win.

---

## IMPORTANT REMINDERS

1. **No old regressions.** VERO/GWAV/ANPA are retired. Don't run them.
2. **Don't change Gate 5 back to MAX_SYMBOL_TRADES=2.** The value should be 10. Let winners cascade.
3. **Log everything.** Every gate check, every pass/fail, every threshold comparison. We'll need the raw data to tune.
4. **Scanner fix already done** (gap threshold 10%→5%). That change is included in this backtest automatically.

---

*Directive from Perplexity Computer | March 12, 2026*
