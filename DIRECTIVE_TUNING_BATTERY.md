# DIRECTIVE: Comprehensive Squeeze Tuning Battery

**Date:** April 8, 2026
**Author:** Cowork (Opus)
**For:** CC (Claude Code)
**Priority:** P1 — cold market gives us time to optimize before the next hot streak
**Scope:** 49 test configurations (29 individual + 18 combos + 2 conditional)

---

## Context

Current baseline: $30K → $357,511 (+$327,511), 39 trades, 60% WR, scaling notional (2x equity).

We want to find every tuning lever that improves on this — individually and in combination. Some random combo might be a diamond. Every test is catalogued with a unique ID so we can trace results back to exact configurations.

**DO NOT touch scanner parameters.** Scanner is validated against Ross Cameron's picks. Only squeeze detector, exit system, and risk management variables are in scope.

---

## Prerequisite: Add Env Var Overrides to run_backtest_v2.py

`RISK_PCT` and `DAILY_LOSS_LIMIT` are currently hardcoded constants in `run_backtest_v2.py`. Before running the battery, make them overridable from environment:

```python
# Replace:
RISK_PCT = 0.025
DAILY_LOSS_LIMIT = -3000

# With:
RISK_PCT = float(os.environ.get("WB_BT_RISK_PCT", "0.025"))
DAILY_LOSS_LIMIT = float(os.environ.get("WB_BT_DAILY_LOSS_LIMIT", "-3000"))
```

Also add support for a special scaling daily loss mode. When `WB_BT_DAILY_LOSS_SCALE=1`, set `DAILY_LOSS_LIMIT = -(equity * 0.02)` at the start of each day instead of using the fixed value. This lets the loss cap grow with the account.

**Gate these behind env vars with current values as defaults so the baseline is unchanged.**

---

## Baseline Reference (ID: B00)

All tests compare against this:

```
Label: BASELINE
Env overrides: (none — all defaults from ENV_BASE)
Flags: --scale-notional --equity 30000
Expected: +$327,511 / 39 trades / 60% WR
```

---

## PART 1: Individual Parameter Tests (29 tests)

Each test changes ONE variable from baseline. This isolates the effect of each lever.

### Entry Sensitivity (10 tests)

| ID | Label | Variable | Value | Baseline | Hypothesis |
|----|-------|----------|-------|----------|------------|
| I01 | VOL_MULT_2.5 | WB_SQ_VOL_MULT | 2.5 | 3.0 | Catches more setups (BBGI-like borderline spikes) |
| I02 | VOL_MULT_3.5 | WB_SQ_VOL_MULT | 3.5 | 3.0 | Fewer but higher-conviction entries |
| I03 | PRIME_2 | WB_SQ_PRIME_BARS | 2 | 3 | Faster arming after vol spike |
| I04 | PRIME_4 | WB_SQ_PRIME_BARS | 4 | 3 | More confirmation before arming |
| I05 | BODY_1.0 | WB_SQ_MIN_BODY_PCT | 1.0 | 1.5 | Allows smaller-body candles to prime |
| I06 | BODY_2.0 | WB_SQ_MIN_BODY_PCT | 2.0 | 1.5 | Only strong candles prime |
| I07 | PARA_0.15 | WB_SQ_PARA_STOP_OFFSET | 0.15 | 0.10 | Wider parabolic stop → bigger R → passes MIN_R |
| I08 | PARA_0.20 | WB_SQ_PARA_STOP_OFFSET | 0.20 | 0.10 | Even wider parabolic stop (BBGI would have R=$0.10, passes MIN_R=0.06) |
| I09 | ATTEMPTS_4 | WB_SQ_MAX_ATTEMPTS | 4 | 3 | One more try per stock per session |
| I10 | ATTEMPTS_5 | WB_SQ_MAX_ATTEMPTS | 5 | 3 | Two more tries (for cascading stocks like VERO/AHMA) |

### Exit Optimization (13 tests)

| ID | Label | Variable | Value | Baseline | Hypothesis |
|----|-------|----------|-------|----------|------------|
| I11 | TARGET_1.5 | WB_SQ_TARGET_R | 1.5 | 2.0 | More frequent target hits, smaller per-trade |
| I12 | TARGET_2.5 | WB_SQ_TARGET_R | 2.5 | 2.0 | Bigger target, fewer hits |
| I13 | TARGET_3.0 | WB_SQ_TARGET_R | 3.0 | 2.0 | Much bigger target, test if runners carry it |
| I14 | CORE_50 | WB_SQ_CORE_PCT | 50 | 75 | Sell half at target, keep half as runner |
| I15 | CORE_60 | WB_SQ_CORE_PCT | 60 | 75 | Moderate: 60% core, 40% runner |
| I16 | CORE_90 | WB_SQ_CORE_PCT | 90 | 75 | Lock in 90% at target, tiny 10% runner |
| I17 | TRAIL_1.0 | WB_SQ_TRAIL_R | 1.0 | 1.5 | Tighter pre-target trail — exits quicker on weakness |
| I18 | TRAIL_2.0 | WB_SQ_TRAIL_R | 2.0 | 1.5 | Looser pre-target trail — more room to breathe |
| I19 | RUNNER_2.0 | WB_SQ_RUNNER_TRAIL_R | 2.0 | 2.5 | Tighter runner trail — locks more post-target profit |
| I20 | RUNNER_3.0 | WB_SQ_RUNNER_TRAIL_R | 3.0 | 2.5 | Looser runner — lets big moves fully extend |
| I21 | BAIL_3 | WB_BAIL_TIMER_MINUTES | 3 | 5 | Cut dead trades faster |
| I22 | BAIL_7 | WB_BAIL_TIMER_MINUTES | 7 | 5 | More patience for slow breakouts |
| I23 | BAIL_OFF | WB_BAIL_TIMER_ENABLED | 0 | 1 | No time-based exit — rely on stops only |

### Risk Management (6 tests)

| ID | Label | Variable | Value | Baseline | Hypothesis |
|----|-------|----------|-------|----------|------------|
| I24 | LOSS_5K | WB_BT_DAILY_LOSS_LIMIT | -5000 | -3000 | Higher daily loss cap — more room on volatile days |
| I25 | LOSS_SCALE | WB_BT_DAILY_LOSS_SCALE | 1 | 0 | Daily loss = 2% of equity (grows with account) |
| I26 | CONSEC_2 | WB_MAX_CONSECUTIVE_LOSSES | 2 | 3 | Stop earlier after losing streak |
| I27 | CONSEC_5 | WB_MAX_CONSECUTIVE_LOSSES | 5 | 3 | More chances after losses |
| I28 | RISK_3.0 | WB_BT_RISK_PCT | 0.030 | 0.025 | 3% risk per trade — 20% bigger positions |
| I29 | RISK_3.5 | WB_BT_RISK_PCT | 0.035 | 0.025 | 3.5% risk — 40% bigger positions |

---

## PART 2: Combination Tests (18 tests)

These test logically paired changes that might interact.

### Exit System Combos (6 tests)

| ID | Label | Changes from Baseline | Hypothesis |
|----|-------|-----------------------|------------|
| C01 | EXIT_CONSERVATIVE | TARGET_R=1.5, CORE_PCT=90 | Take profit early and take most of it — base-hit machine |
| C02 | EXIT_AGGRESSIVE | TARGET_R=2.5, CORE_PCT=50 | Higher target, bigger runner position — cascade maximizer |
| C03 | EXIT_QUICK_LOCK | TARGET_R=1.5, TRAIL_R=1.0 | Low target + tight trail — fastest profit lock |
| C04 | EXIT_LET_IT_RUN | TARGET_R=2.5, TRAIL_R=2.0, RUNNER_TRAIL_R=3.0 | Maximize every winner — loose everything |
| C05 | EXIT_BIG_RUNNER | CORE_PCT=50, RUNNER_TRAIL_R=2.0 | Half runner position, tight runner trail — balanced |
| C06 | EXIT_MEGA_RUNNER | CORE_PCT=50, RUNNER_TRAIL_R=3.5 | Half runner position, very loose trail — VERO/AHMA maximizer |

### Entry Sensitivity Combos (4 tests)

| ID | Label | Changes from Baseline | Hypothesis |
|----|-------|-----------------------|------------|
| C07 | ENTRY_LOOSE | VOL_MULT=2.5, PARA_STOP_OFFSET=0.15 | More priming + wider parabolic stops |
| C08 | ENTRY_FASTEST | VOL_MULT=2.5, PRIME_BARS=2 | Lowest barrier to arming |
| C09 | ENTRY_STRICT | VOL_MULT=3.5, MIN_BODY_PCT=2.0 | Highest conviction entries only |
| C10 | ENTRY_PERSISTENT | MAX_ATTEMPTS=5, BAIL_TIMER_MINUTES=3 | More tries but cut losers fast |

### Risk Combos (3 tests)

| ID | Label | Changes from Baseline | Hypothesis |
|----|-------|-----------------------|------------|
| C11 | RISK_SIZE_UP | RISK_PCT=0.030, DAILY_LOSS_LIMIT=-5000 | Bigger positions, higher daily cap |
| C12 | RISK_SCALE_UP | RISK_PCT=0.030, DAILY_LOSS_SCALE=1 | Bigger positions, scaling daily cap with equity |
| C13 | RISK_BIG_TIGHT | RISK_PCT=0.035, CONSEC_LOSSES=2 | Biggest positions, shortest leash |

### Cross-Category Combos (5 tests)

| ID | Label | Changes from Baseline | Hypothesis |
|----|-------|-----------------------|------------|
| C14 | CROSS_BASE_HIT | VOL_MULT=2.5, TARGET_R=1.5, CORE_PCT=90 | More entries + quick profits = consistent base hits |
| C15 | CROSS_CASCADE | VOL_MULT=2.5, TARGET_R=2.5, CORE_PCT=50, RUNNER_TRAIL_R=3.0 | More entries + maximize cascading runners |
| C16 | CROSS_QUICK_BIG | RISK_PCT=0.030, TARGET_R=1.5, TRAIL_R=1.0 | Bigger size + quick exits = high turnover |
| C17 | CROSS_MAX_RIDE | RISK_PCT=0.030, TARGET_R=2.5, TRAIL_R=2.0, RUNNER_TRAIL_R=3.0, DAILY_LOSS_SCALE=1 | Bigger size + loose exits + scaling cap = max upside |
| C18 | CROSS_BBGI_FIX | VOL_MULT=2.5, PARA_STOP_OFFSET=0.20, MAX_ATTEMPTS=4, TARGET_R=1.5 | Designed to catch setups like BBGI (wider entry, quick target) |

---

## PART 3: Conditional Tests (2 tests — run AFTER Parts 1 & 2)

These depend on results from the individual and combo tests.

| ID | Label | What to Do |
|----|-------|------------|
| X01 | BEST_COMBO | Take every individual test that BEAT the baseline. Combine ALL of their changes into one run. If conflicting (e.g., two different TARGET_R values won), use the one with higher P&L. |
| X02 | BEST_CURATED | Review all Part 1 + Part 2 results. Hand-pick the combination that maximizes P&L while keeping WR ≥ 55% and max drawdown reasonable. This is the "if you could only pick one config" answer. |

---

## Execution

### How to Run Each Test

```bash
# Example for I01:
WB_SQ_VOL_MULT=2.5 python run_backtest_v2.py --start 2026-01-02 --end 2026-04-02 --equity 30000 --scale-notional --label "I01_VOL_MULT_2.5" --status-file tuning_I01.md

# Example for C14 (multiple overrides):
WB_SQ_VOL_MULT=2.5 WB_SQ_TARGET_R=1.5 WB_SQ_CORE_PCT=90 python run_backtest_v2.py --start 2026-01-02 --end 2026-04-02 --equity 30000 --scale-notional --label "C14_CROSS_BASE_HIT" --status-file tuning_C14.md

# For risk tests requiring script-level overrides:
WB_BT_RISK_PCT=0.030 WB_BT_DAILY_LOSS_LIMIT=-5000 python run_backtest_v2.py --start 2026-01-02 --end 2026-04-02 --equity 30000 --scale-notional --label "C11_RISK_SIZE_UP" --status-file tuning_C11.md
```

### Parallelization

Tests are independent — run as many in parallel as the machine can handle. Each takes ~5 minutes. With 4 parallel processes, the full battery (49 tests) takes ~65 minutes. With 8 parallel, ~35 minutes.

Suggested batching:
- **Batch 1:** I01-I10 (entry tests) — 10 runs
- **Batch 2:** I11-I23 (exit tests) — 13 runs
- **Batch 3:** I24-I29 (risk tests) — 6 runs
- **Batch 4:** C01-C18 (combos) — 18 runs
- **Batch 5:** X01-X02 (conditional, after reviewing 1-4)

### Output

All status files go to `backtest_status/tuning_*.md`.

After all tests complete, generate a master comparison report:

```
tuning_results/TUNING_MASTER_REPORT.md
```

---

## Master Report Format

The master report should contain:

### 1. Leaderboard (all 49+ tests ranked by P&L)

| Rank | ID | Label | P&L | Trades | WR | Avg Win | Avg Loss | Profit Factor | Max DD | vs Baseline |
|------|------|-------|-----|--------|------|---------|----------|---------------|--------|-------------|
| 1 | X01 | BEST_COMBO | $??? | ?? | ??% | $??? | $??? | ?.? | $??? | +$???  |
| 2 | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| ... | B00 | BASELINE | $327,511 | 39 | 60% | $14,942 | -$1,077 | — | — | — |

### 2. Individual Parameter Impact (sorted by P&L delta from baseline)

For each variable tested, show what moving it up/down did:

```
TARGET_R:  1.5 = $???  |  [2.0 = $327,511]  |  2.5 = $???  |  3.0 = $???
CORE_PCT:  50 = $???   |  60 = $???          |  [75 = $327,511] |  90 = $???
VOL_MULT:  2.5 = $???  |  [3.0 = $327,511]  |  3.5 = $???
...
```

### 3. Top 5 Breakdown

For the top 5 configurations, include:
- Full daily P&L breakdown
- Exit reason distribution
- Comparison of which specific trades differ from baseline
- Max consecutive loss streak
- Largest single-day loss and gain

### 4. Recommendation

Based on all results, recommend:
- **Conservative config:** Best P&L with WR ≥ 60% and max DD < $10K
- **Aggressive config:** Highest absolute P&L regardless of drawdown
- **Balanced config:** Best risk-adjusted returns (highest profit factor)

Include the exact env var settings for each recommended config.

---

## Important Notes

- **Do NOT modify ENV_BASE defaults.** Each test overrides via env vars at runtime.
- **Scaling notional is ON for all tests** (`--scale-notional`). This is the live config.
- **Starting equity is $30K for all tests.** Consistent baseline.
- **Date range: 2026-01-02 to 2026-04-02** for all tests (64 trading days).
- **If a test fails or errors, log it and move on.** Don't block the battery on one failure.
- **Save raw state JSON for every test** (the `--status-file` flag also generates a `_state.json`). We may want to drill into specific trades later.

---

## Quick Reference: All 49 Test Env Overrides

### Individual (29)

```bash
# Entry
I01: WB_SQ_VOL_MULT=2.5
I02: WB_SQ_VOL_MULT=3.5
I03: WB_SQ_PRIME_BARS=2
I04: WB_SQ_PRIME_BARS=4
I05: WB_SQ_MIN_BODY_PCT=1.0
I06: WB_SQ_MIN_BODY_PCT=2.0
I07: WB_SQ_PARA_STOP_OFFSET=0.15
I08: WB_SQ_PARA_STOP_OFFSET=0.20
I09: WB_SQ_MAX_ATTEMPTS=4
I10: WB_SQ_MAX_ATTEMPTS=5

# Exit
I11: WB_SQ_TARGET_R=1.5
I12: WB_SQ_TARGET_R=2.5
I13: WB_SQ_TARGET_R=3.0
I14: WB_SQ_CORE_PCT=50
I15: WB_SQ_CORE_PCT=60
I16: WB_SQ_CORE_PCT=90
I17: WB_SQ_TRAIL_R=1.0
I18: WB_SQ_TRAIL_R=2.0
I19: WB_SQ_RUNNER_TRAIL_R=2.0
I20: WB_SQ_RUNNER_TRAIL_R=3.0
I21: WB_BAIL_TIMER_MINUTES=3
I22: WB_BAIL_TIMER_MINUTES=7
I23: WB_BAIL_TIMER_ENABLED=0

# Risk
I24: WB_BT_DAILY_LOSS_LIMIT=-5000
I25: WB_BT_DAILY_LOSS_SCALE=1
I26: WB_MAX_CONSECUTIVE_LOSSES=2
I27: WB_MAX_CONSECUTIVE_LOSSES=5
I28: WB_BT_RISK_PCT=0.030
I29: WB_BT_RISK_PCT=0.035
```

### Combos (18)

```bash
# Exit combos
C01: WB_SQ_TARGET_R=1.5 WB_SQ_CORE_PCT=90
C02: WB_SQ_TARGET_R=2.5 WB_SQ_CORE_PCT=50
C03: WB_SQ_TARGET_R=1.5 WB_SQ_TRAIL_R=1.0
C04: WB_SQ_TARGET_R=2.5 WB_SQ_TRAIL_R=2.0 WB_SQ_RUNNER_TRAIL_R=3.0
C05: WB_SQ_CORE_PCT=50 WB_SQ_RUNNER_TRAIL_R=2.0
C06: WB_SQ_CORE_PCT=50 WB_SQ_RUNNER_TRAIL_R=3.5

# Entry combos
C07: WB_SQ_VOL_MULT=2.5 WB_SQ_PARA_STOP_OFFSET=0.15
C08: WB_SQ_VOL_MULT=2.5 WB_SQ_PRIME_BARS=2
C09: WB_SQ_VOL_MULT=3.5 WB_SQ_MIN_BODY_PCT=2.0
C10: WB_SQ_MAX_ATTEMPTS=5 WB_BAIL_TIMER_MINUTES=3

# Risk combos
C11: WB_BT_RISK_PCT=0.030 WB_BT_DAILY_LOSS_LIMIT=-5000
C12: WB_BT_RISK_PCT=0.030 WB_BT_DAILY_LOSS_SCALE=1
C13: WB_BT_RISK_PCT=0.035 WB_MAX_CONSECUTIVE_LOSSES=2

# Cross-category combos
C14: WB_SQ_VOL_MULT=2.5 WB_SQ_TARGET_R=1.5 WB_SQ_CORE_PCT=90
C15: WB_SQ_VOL_MULT=2.5 WB_SQ_TARGET_R=2.5 WB_SQ_CORE_PCT=50 WB_SQ_RUNNER_TRAIL_R=3.0
C16: WB_BT_RISK_PCT=0.030 WB_SQ_TARGET_R=1.5 WB_SQ_TRAIL_R=1.0
C17: WB_BT_RISK_PCT=0.030 WB_SQ_TARGET_R=2.5 WB_SQ_TRAIL_R=2.0 WB_SQ_RUNNER_TRAIL_R=3.0 WB_BT_DAILY_LOSS_SCALE=1
C18: WB_SQ_VOL_MULT=2.5 WB_SQ_PARA_STOP_OFFSET=0.20 WB_SQ_MAX_ATTEMPTS=4 WB_SQ_TARGET_R=1.5
```

### Conditional (2)

```
X01: Combine all individual winners (determined after Parts 1-2 complete)
X02: Hand-curated best config (determined after reviewing all results)
```

---

*Directive by Cowork (Opus). For CC execution. Run the full battery — every data point matters.*
