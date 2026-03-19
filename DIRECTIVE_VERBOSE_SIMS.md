# Directive: Verbose Simulations for Micro Pullback Refinement

## Priority: HIGH — Blocks refinement work
## Owner: CC (Mac Mini or MBP)
## Created: 2026-03-19

---

## Objective

Run verbose tick-mode simulations on key winning stocks from the aligned scanner results. We need to see **every detector state change** — every ARM, RESET, entry, exit, suppression — to understand exactly where re-entry opportunities are being missed after winning exits.

The goal is NOT to change any code. The goal is to produce detailed logs that Cowork can analyze to design the next round of refinements.

---

## Pre-Flight

```bash
cd ~/warrior_bot
source venv/bin/activate
git pull origin v6-dynamic-sizing
```

---

## Simulations to Run

Run each command below and **capture full output to a log file**. The `-v` flag enables verbose detector logging. All env vars must match the batch runner's `ENV_BASE` plus the .env settings (especially the Fix 1-5 gates).

### 1. VERO — Jan 16 (our $15,980 winner — did we miss re-entries after exit?)

```bash
WB_CLASSIFIER_ENABLED=1 WB_CLASSIFIER_RECLASS_ENABLED=1 WB_EXHAUSTION_ENABLED=1 \
WB_WARMUP_BARS=5 WB_CONTINUATION_HOLD_ENABLED=1 WB_CONT_HOLD_5M_TREND_GUARD=1 \
WB_MAX_NOTIONAL=50000 WB_MAX_LOSS_R=0.75 WB_NO_REENTRY_ENABLED=1 \
WB_TW_MIN_PROFIT_R=1.5 WB_MAX_LOSS_R_TIERED=1 WB_MAX_LOSS_TRIGGERS_COOLDOWN=1 \
WB_CONT_HOLD_DIRECTION_CHECK=1 \
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
  2>&1 | tee verbose_logs/VERO_2026-01-16_verbose.log
```

**What we need to see:**
- The one trade: entry, hold behavior, exit at $5.81
- After exit: every ARM attempt, RESET reason, exhaustion block, stale filter, cooldown
- VERO went from ~$5.81 to $12+. Why didn't the detector re-arm for a second entry?

### 2. ROLR — Jan 14 (our $4,769 winner — 4 ARMs, 2 signals, 1 trade)

```bash
WB_CLASSIFIER_ENABLED=1 WB_CLASSIFIER_RECLASS_ENABLED=1 WB_EXHAUSTION_ENABLED=1 \
WB_WARMUP_BARS=5 WB_CONTINUATION_HOLD_ENABLED=1 WB_CONT_HOLD_5M_TREND_GUARD=1 \
WB_MAX_NOTIONAL=50000 WB_MAX_LOSS_R=0.75 WB_NO_REENTRY_ENABLED=1 \
WB_TW_MIN_PROFIT_R=1.5 WB_MAX_LOSS_R_TIERED=1 WB_MAX_LOSS_TRIGGERS_COOLDOWN=1 \
WB_CONT_HOLD_DIRECTION_CHECK=1 \
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
  2>&1 | tee verbose_logs/ROLR_2026-01-14_verbose.log
```

**What we need to see:**
- Which ARM converted to the $9.33 entry and why the others didn't
- After exit at $16.43: every ARM attempt, RESET, block reason
- ROLR went from ~$16.43 to $22.28. What stopped re-entry?
- Was it MAX_SYMBOL_TRADES=2? Exhaustion? Stale filter? MACD?

### 3. SXTC — Jan 8 (our cascading winner — 2 trades, +$1,591)

```bash
WB_CLASSIFIER_ENABLED=1 WB_CLASSIFIER_RECLASS_ENABLED=1 WB_EXHAUSTION_ENABLED=1 \
WB_WARMUP_BARS=5 WB_CONTINUATION_HOLD_ENABLED=1 WB_CONT_HOLD_5M_TREND_GUARD=1 \
WB_MAX_NOTIONAL=50000 WB_MAX_LOSS_R=0.75 WB_NO_REENTRY_ENABLED=1 \
WB_TW_MIN_PROFIT_R=1.5 WB_MAX_LOSS_R_TIERED=1 WB_MAX_LOSS_TRIGGERS_COOLDOWN=1 \
WB_CONT_HOLD_DIRECTION_CHECK=1 \
python simulate.py SXTC 2026-01-08 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
  2>&1 | tee verbose_logs/SXTC_2026-01-08_verbose.log
```

**What we need to see:**
- The cascading re-entry worked here. Why? What was different vs VERO/ROLR?
- After the 2nd trade exit: was there a 3rd opportunity? What blocked it?

### 4. ARTL — Mar 18 (our $1,135 winner — TW exit, left money on table)

```bash
WB_CLASSIFIER_ENABLED=1 WB_CLASSIFIER_RECLASS_ENABLED=1 WB_EXHAUSTION_ENABLED=1 \
WB_WARMUP_BARS=5 WB_CONTINUATION_HOLD_ENABLED=1 WB_CONT_HOLD_5M_TREND_GUARD=1 \
WB_MAX_NOTIONAL=50000 WB_MAX_LOSS_R=0.75 WB_NO_REENTRY_ENABLED=1 \
WB_TW_MIN_PROFIT_R=1.5 WB_MAX_LOSS_R_TIERED=1 WB_MAX_LOSS_TRIGGERS_COOLDOWN=1 \
WB_CONT_HOLD_DIRECTION_CHECK=1 \
python simulate.py ARTL 2026-03-18 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
  2>&1 | tee verbose_logs/ARTL_2026-03-18_verbose.log
```

**What we need to see:**
- Entry at $7.62, TW exit at $7.92. Was TW profit gate evaluated? Why did TW fire?
- After exit: re-entry attempts? ARTL continued to $8.19+ (micro pullback opportunities)
- What blocked further entries?

### 5. INKT — Mar 10 (a loser, -$440 — understand why it failed)

```bash
WB_CLASSIFIER_ENABLED=1 WB_CLASSIFIER_RECLASS_ENABLED=1 WB_EXHAUSTION_ENABLED=1 \
WB_WARMUP_BARS=5 WB_CONTINUATION_HOLD_ENABLED=1 WB_CONT_HOLD_5M_TREND_GUARD=1 \
WB_MAX_NOTIONAL=50000 WB_MAX_LOSS_R=0.75 WB_NO_REENTRY_ENABLED=1 \
WB_TW_MIN_PROFIT_R=1.5 WB_MAX_LOSS_R_TIERED=1 WB_MAX_LOSS_TRIGGERS_COOLDOWN=1 \
WB_CONT_HOLD_DIRECTION_CHECK=1 \
python simulate.py INKT 2026-03-10 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
  2>&1 | tee verbose_logs/INKT_2026-03-10_verbose.log
```

**What we need to see:**
- Entry at $20.02, BE exit at $19.38. What triggered the BE?
- Was this a stock that should have been avoided? (detector quality issue vs bad luck)
- Did the stock eventually recover? If so, was there a missed re-entry?

### 6. FUTG — Jan 2 (biggest loser, -$1,234 — understand the failure)

```bash
WB_CLASSIFIER_ENABLED=1 WB_CLASSIFIER_RECLASS_ENABLED=1 WB_EXHAUSTION_ENABLED=1 \
WB_WARMUP_BARS=5 WB_CONTINUATION_HOLD_ENABLED=1 WB_CONT_HOLD_5M_TREND_GUARD=1 \
WB_MAX_NOTIONAL=50000 WB_MAX_LOSS_R=0.75 WB_NO_REENTRY_ENABLED=1 \
WB_TW_MIN_PROFIT_R=1.5 WB_MAX_LOSS_R_TIERED=1 WB_MAX_LOSS_TRIGGERS_COOLDOWN=1 \
WB_CONT_HOLD_DIRECTION_CHECK=1 \
python simulate.py FUTG 2026-01-02 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
  2>&1 | tee verbose_logs/FUTG_2026-01-02_verbose.log
```

**What we need to see:**
- Entry at $16.58, stop hit at $16.07. What was the setup quality? Score?
- How quickly did the stop get hit? Was the R too tight?
- Did the stock recover after the stop hit? Or was this a legitimate loser?

---

## Setup

Create the output directory first:

```bash
mkdir -p verbose_logs
```

---

## Output

After all 6 sims complete:
1. Commit the verbose_logs/ directory
2. `git push origin v6-dynamic-sizing`

Cowork will analyze the logs and design the next round of micro pullback refinements.

---

## DO NOT

- Do NOT change any code
- Do NOT modify .env settings
- Do NOT run regression — this is read-only analysis
- The verbose logs may be large (VERO/ROLR have 800K+ ticks). That's fine — we need the detail.
