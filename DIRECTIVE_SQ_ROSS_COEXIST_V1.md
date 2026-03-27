# DIRECTIVE: SQ + Ross Exit Coexistence — V3 January Comparison

**Author**: Cowork (Opus)
**Date**: 2026-03-24
**For**: CC (Sonnet)
**Priority**: HIGH — This is the central hypothesis test from Perplexity's Squeeze Focus research

---

## Problem

V2 (Ross exit ON) showed that Ross 1m signals **help MP trades** (+$2,414 in Jan 2025) but **destroy SQ trades** (0 wins, multiple stops hit). Root cause: when `WB_ROSS_EXIT_ENABLED=1`, four guard lines in `simulate.py` block ALL mechanical squeeze exits:

```
Line 666:  if not t.tp_hit and not self.ross_exit_enabled:     ← blocks SQ pre-target trail + target hit
Line 703:  if t.tp_hit and ... and not self.ross_exit_enabled: ← blocks SQ post-target runner trail
Line 832:  if not t.tp_hit and not self.ross_exit_enabled:     ← blocks VR pre-target trail + target hit
Line 858:  elif not self.ross_exit_enabled:                    ← blocks VR post-target runner trail
```

This means SQ trades never take their clean 2R target exit. Instead they wait for 1m Ross signals, but fast squeeze moves spike and pull back within a single 1m bar — hitting hard stops instead of banking the 2R win.

**The fix**: Let SQ mechanical exits coexist with Ross 1m signals. SQ handles the core exit at 2R target. After the core exits, Ross signals handle the runner phase (CUC, MACD backstop, structural trail, etc.). This gives us the best of both worlds: reliable SQ profit-taking + Ross's superior runner management.

---

## Baseline Numbers (from completed runs on fresh scanner data)

```
              V1 (no Ross)           V2 (Ross ON, SQ blocked)
Jan 2025:     32 trades, +$3,423     29 trades, +$5,837
Jan 2026:     17 trades, +$16,409    12 trades*, +$13,620*
Combined:     49 trades, +$19,832    41 trades*, +$19,457*

* V2 Jan 2026 stalled at 16/21 days — must be finished first (Step 0)
```

---

## Step 0: Finish Stalled V2

V2 Jan 2026 is stuck at 16/21 days (stopped at Jan 23). Resume it before starting V3 so we have complete baselines.

```bash
cd /Users/mannyluke/warrior_bot
git pull
source venv/bin/activate
python run_jan_v2_comparison.py 2>&1 | tee -a jan_comparison_v2_output.txt
```

The runner has checkpoint/resume logic — it should pick up from Jan 23. Verify completion:
```bash
python3 -c "
import json
with open('jan_comparison_v2_state.json') as f:
    s = json.load(f)
print(f'Jan 2025: {len(s[\"jan2025\"][\"daily\"])}/21 days, {len(s[\"jan2025\"][\"trades\"])} trades, equity \${s[\"jan2025\"][\"equity\"]:,}')
print(f'Jan 2026: {len(s[\"jan2026\"][\"daily\"])}/21 days, {len(s[\"jan2026\"][\"trades\"])} trades, equity \${s[\"jan2026\"][\"equity\"]:,}')
"
```

Both months must show 21/21 days before proceeding.

---

## Step 1: Apply the Coexistence Fix in simulate.py

**Gate with a new env var** (OFF by default per project rules):

### 1a. Add env var declaration

Near the existing Ross exit env vars (around line 218-219), add:

```python
# SQ + Ross coexistence: let SQ mechanical exits (target hit, trail) work alongside Ross 1m signals
self.sq_ross_coexist = os.getenv("WB_SQ_ROSS_COEXIST", "0") == "1"
```

### 1b. Modify the four guard lines

**Line 666** — SQ pre-target phase:
```python
# BEFORE:
if not t.tp_hit and not self.ross_exit_enabled:

# AFTER:
if not t.tp_hit and (not self.ross_exit_enabled or self.sq_ross_coexist):
```

**Line 703** — SQ post-target runner phase:
```python
# BEFORE:
if t.tp_hit and t.qty_runner > 0 and t.runner_exit_price == 0 and not self.ross_exit_enabled:

# AFTER:
if t.tp_hit and t.qty_runner > 0 and t.runner_exit_price == 0 and (not self.ross_exit_enabled or self.sq_ross_coexist):
```

**Line 832** — VR pre-target phase:
```python
# BEFORE:
if not t.tp_hit and not self.ross_exit_enabled:

# AFTER:
if not t.tp_hit and (not self.ross_exit_enabled or self.sq_ross_coexist):
```

**Line 858** — VR post-target runner phase:
```python
# BEFORE:
elif not self.ross_exit_enabled:

# AFTER:
elif not self.ross_exit_enabled or self.sq_ross_coexist:
```

### 1c. Update comments on the guard blocks

Replace the comments above lines 663-664 and 830-831:
```python
# --- Pre-target phase (full position) ---
# When Ross exit is ON and coexist is OFF, skip mechanical trail and target exits entirely —
# Ross 1m signals handle all exits. When coexist is ON, SQ/VR mechanical exits
# run alongside Ross signals: SQ handles core exit at target, Ross handles runner.
```

### 1d. Add to .env

Append to the Ross exit block in `.env`:
```
WB_SQ_ROSS_COEXIST=0          # Let SQ mechanical exits coexist with Ross 1m signals
```

### 1e. Interaction note — what happens when BOTH fire

When coexist is ON and Ross is ON, both SQ mechanical exits AND Ross 1m signals are active. The interaction:

1. **SQ target hit fires first** (tick-level, at exactly 2R): sets `t.tp_hit = True`, exits core, keeps runner with stop at breakeven.
2. **Ross signals fire later** (1m bar close): CUC/MACD/structural trail can exit the runner.
3. **If Ross partial_50 fires before SQ target**: `on_ross_exit_signal` checks `t.tp_hit` — if False, it exits core and sets `t.tp_hit = True`. Then SQ post-target runner phase kicks in on subsequent ticks.
4. **No double-exit risk**: Once `t.tp_hit = True`, both SQ target-hit (line 689 `if t.r > 0 and price >= ...`) and Ross partial_50 (line 1006 `if t.tp_hit: return`) are no-ops.

The key insight: **SQ target hit at 2R is tick-level and fires instantly. Ross signals fire on 1m bar close.** For fast squeezes that spike to 2R and reverse within a minute, SQ catches the exit; Ross would miss it entirely.

---

## Step 2: Regression Check

The coexistence fix should NOT change MP trades (they don't have SQ target/trail logic). Verify:

```bash
source venv/bin/activate

# VERO regression — MP trade, should be unchanged from V1 baseline
WB_MP_ENABLED=1 WB_ROSS_EXIT_ENABLED=1 WB_SQ_ROSS_COEXIST=1 WB_SQ_PARTIAL_EXIT_ENABLED=1 WB_SQ_WIDE_TRAIL_ENABLED=1 WB_SQ_RUNNER_DETECT_ENABLED=1 WB_HALT_THROUGH_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# VERO is MP-only. Ross exit IS active (changes result vs V1) but coexist should not change vs V2.
# Record result and compare to V2 VERO (should be identical).

# ROLR regression — MP trade
WB_MP_ENABLED=1 WB_ROSS_EXIT_ENABLED=1 WB_SQ_ROSS_COEXIST=1 WB_SQ_PARTIAL_EXIT_ENABLED=1 WB_SQ_WIDE_TRAIL_ENABLED=1 WB_SQ_RUNNER_DETECT_ENABLED=1 WB_HALT_THROUGH_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Same — should match V2 ROLR exactly.
```

**If VERO or ROLR differ from V2** (not V1 — V2 is the correct comparison for Ross-ON trades), STOP and investigate. The coexist flag should only affect SQ/VR strategy trades.

---

## Step 3: Build the V3 Runner

Create `run_jan_v3_comparison.py` — clone from `run_jan_v2_comparison.py` with these changes:

### 3a. ENV_BASE — add coexist var

Copy V2's ENV_BASE (which already has all Ross exit vars) and add:
```python
    # --- NEW in V3: SQ + Ross coexistence ---
    "WB_SQ_ROSS_COEXIST": "1",        # Let SQ mechanical exits work alongside Ross 1m signals
```

Full ENV_BASE for V3 (V2 + one new var):
```python
ENV_BASE = {
    # --- Core strategy ---
    "WB_CLASSIFIER_ENABLED": "1",
    "WB_CLASSIFIER_RECLASS_ENABLED": "1",
    "WB_EXHAUSTION_ENABLED": "1",
    "WB_WARMUP_BARS": "5",
    "WB_CONTINUATION_HOLD_ENABLED": "1",
    "WB_CONT_HOLD_5M_TREND_GUARD": "1",
    "WB_CONT_HOLD_5M_VOL_EXIT_MULT": "2.0",
    "WB_CONT_HOLD_5M_MIN_BARS": "2",
    "WB_CONT_HOLD_MIN_VOL_DOM": "2.0",
    "WB_CONT_HOLD_MIN_SCORE": "8.0",
    "WB_CONT_HOLD_MAX_LOSS_R": "0.5",
    "WB_CONT_HOLD_CUTOFF_HOUR": "10",
    "WB_CONT_HOLD_CUTOFF_MIN": "30",
    "WB_MAX_NOTIONAL": "50000",
    "WB_MAX_LOSS_R": "0.75",
    "WB_NO_REENTRY_ENABLED": "1",
    # --- Strategy 2: Squeeze V2 ---
    "WB_SQUEEZE_ENABLED": "1",
    "WB_SQ_VOL_MULT": "3.0",
    "WB_SQ_MIN_BAR_VOL": "50000",
    "WB_SQ_MIN_BODY_PCT": "1.5",
    "WB_SQ_PRIME_BARS": "3",
    "WB_SQ_MAX_R": "0.80",
    "WB_SQ_LEVEL_PRIORITY": "pm_high,whole_dollar,pdh",
    "WB_SQ_PROBE_SIZE_MULT": "0.5",
    "WB_SQ_MAX_ATTEMPTS": "3",
    "WB_SQ_PARA_ENABLED": "1",
    "WB_SQ_PARA_STOP_OFFSET": "0.10",
    "WB_SQ_PARA_TRAIL_R": "1.0",
    "WB_SQ_NEW_HOD_REQUIRED": "1",
    "WB_SQ_MAX_LOSS_DOLLARS": "500",
    "WB_SQ_TARGET_R": "2.0",
    "WB_SQ_CORE_PCT": "75",
    "WB_SQ_RUNNER_TRAIL_R": "2.5",
    "WB_SQ_TRAIL_R": "1.5",
    "WB_SQ_STALL_BARS": "5",
    "WB_SQ_VWAP_EXIT": "1",
    "WB_SQ_PM_CONFIDENCE": "1",
    "WB_PILLAR_GATES_ENABLED": "1",
    "WB_MP_ENABLED": "1",
    # --- Scanner fixes ---
    "WB_ALLOW_UNKNOWN_FLOAT": "1",
    # --- Squeeze exit fixes ---
    "WB_SQ_PARTIAL_EXIT_ENABLED": "1",
    "WB_SQ_WIDE_TRAIL_ENABLED": "1",
    "WB_SQ_RUNNER_DETECT_ENABLED": "1",
    "WB_HALT_THROUGH_ENABLED": "1",
    # --- Ross Cameron 1m signal exits ---
    "WB_ROSS_EXIT_ENABLED": "1",
    "WB_ROSS_MIN_BARS": "2",
    "WB_ROSS_CUC_ENABLED": "1",
    "WB_ROSS_DOJI_ENABLED": "1",
    "WB_ROSS_GRAVESTONE_ENABLED": "1",
    "WB_ROSS_SHOOTING_STAR_ENABLED": "1",
    "WB_ROSS_TOPPING_TAIL_ENABLED": "1",
    "WB_ROSS_MACD_ENABLED": "1",
    "WB_ROSS_EMA20_ENABLED": "1",
    "WB_ROSS_VWAP_ENABLED": "1",
    "WB_ROSS_STRUCTURAL_TRAIL": "1",
    "WB_ROSS_CUC_FLOOR_R": "0.0",
    "WB_ROSS_CUC_MIN_TRADE_BARS": "0",
    "WB_ROSS_BACKSTOP_MIN_R": "0.0",
    # --- NEW in V3: SQ + Ross coexistence ---
    "WB_SQ_ROSS_COEXIST": "1",
}
```

### 3b. Fresh state file

Use `jan_comparison_v3_state.json` (NOT v1 or v2).

### 3c. Output file

Use `jan_comparison_v3_output.txt`.

### 3d. Fix the None float crash

Same guard as V2:
```python
f"gap={c.get('gap_pct', 0) or 0:.0f}% float={c.get('float_millions', 0) or 0:.1f}M"
```

### 3e. Everything else identical to V2

Same dates, same `load_and_rank()`, same risk model ($30K equity, 2.5% risk, 5 trades/day, -$1,500 daily loss limit), same tick cache, same scanner JSONs.

---

## Step 4: Run It

```bash
source venv/bin/activate
python run_jan_v3_comparison.py 2>&1 | tee jan_comparison_v3_output.txt
```

---

## Step 5: Produce V3 Report

Save to `cowork_reports/2026-03-24_jan_comparison_v3.md` with:

### Section 1: Three-Way A/B/C Summary (THE KEY TABLE)

```
╔══════════════════════════════════════════════════════════════════════════════════════════════════╗
║              SQ + ROSS COEXISTENCE: V1 vs V2 vs V3                                             ║
╠════════════════════════════╦═══════════════╦═══════════════╦═══════════════╦══════════════════════╣
║ Metric                     ║ V1 (SQ only)  ║ V2 (Ross only)║ V3 (SQ+Ross)  ║ V3 vs V1 Delta     ║
╠════════════════════════════╬═══════════════╬═══════════════╬═══════════════╬══════════════════════╣
║ Jan 2025 P&L               ║ +$3,423       ║ +$5,837       ║ $X,XXX        ║ +/-$X,XXX           ║
║ Jan 2025 Win Rate          ║ 41%           ║ 34%           ║ XX%           ║ +/-X%               ║
║ Jan 2025 Trades            ║ 32            ║ 29            ║ XX            ║ +/-X                ║
║ Jan 2026 P&L               ║ +$16,409      ║ $X,XXX        ║ $X,XXX        ║ +/-$X,XXX           ║
║ Jan 2026 Win Rate          ║ 41%           ║ XX%           ║ XX%           ║ +/-X%               ║
║ Jan 2026 Trades            ║ 17            ║ XX            ║ XX            ║ +/-X                ║
║ Combined P&L               ║ +$19,832      ║ $X,XXX        ║ $X,XXX        ║ +/-$X,XXX           ║
║ VERO standalone            ║ +$18,583      ║ $X,XXX        ║ $X,XXX        ║ (should match V2)   ║
║ ROLR standalone            ║ +$6,444       ║ $X,XXX        ║ $X,XXX        ║ (should match V2)   ║
╚════════════════════════════╩═══════════════╩═══════════════╩═══════════════╩══════════════════════╝
```

**Fill in V2 numbers after Step 0 completes V2.**

### Section 2: Exit Reason Analysis

For V3 trades, group by exit reason. The key question: do we see `sq_target_hit` exits again (which were absent in V2)?

- `sq_target_hit` — how many, avg P&L, avg R (these were ZERO in V2 — should reappear in V3)
- `sq_trail_exit` / `sq_para_trail_exit` — how many, avg P&L
- `ross_cuc`, `ross_doji_partial`, `ross_gravestone`, `ross_shooting_star`, `ross_topping_tail` — how many, avg P&L
- `ross_macd_backstop`, `ross_ema20_backstop`, `ross_vwap_backstop` — how many, avg P&L
- `ross_structural_trail` — how many, avg P&L
- Non-strategy exits (hard stop, max_loss, bail timer) — how many, avg P&L

### Section 3: SQ Trade Comparison (V1 vs V2 vs V3)

For every SQ trade that appears in V1, show how it did in V2 and V3:
```
Symbol  Date        V1 Exit           V1 P&L    V2 Exit           V2 P&L    V3 Exit           V3 P&L
AHMA    2025-01-XX  sq_target_hit     +$800     ross_stop_hit     -$375     sq_target_hit     +$XXX
...
```

This is the definitive table — it shows exactly which SQ trades were rescued by the coexistence fix.

### Section 4: Strategy Breakdown (SQ vs MP across all 3 versions)

```
           V1 SQ    V1 MP    V2 SQ    V2 MP    V3 SQ    V3 MP
Trades:    XX       XX       XX       XX       XX       XX
Win Rate:  XX%      XX%      XX%      XX%      XX%      XX%
P&L:       $X,XXX   $X,XXX   $X,XXX   $X,XXX   $X,XXX   $X,XXX
```

MP numbers should be identical across V2 and V3 (coexist only affects SQ/VR).

### Section 5: Runner Analysis

For SQ trades that hit the 2R target in V3:
- How many had runners that were subsequently exited by Ross signals?
- What Ross signal exited the runner? (CUC, MACD backstop, structural trail, etc.)
- Did the runner add or subtract value vs V1's mechanical runner trail?

### Section 6: Verdict

State clearly:
1. Does V3 (SQ+Ross combined) beat V1 (SQ only)?
2. Does V3 beat V2 (Ross only)?
3. Is V3 the best configuration overall?
4. Should `WB_SQ_ROSS_COEXIST=1` be added to the live config alongside `WB_ROSS_EXIT_ENABLED=1`?
5. Any signals that should be tuned or disabled?

---

## Step 6: Commit and Push

```bash
git add simulate.py .env run_jan_v3_comparison.py jan_comparison_v3_state.json jan_comparison_v3_output.txt cowork_reports/2026-03-24_jan_comparison_v3.md
# Also add V2 completion files if Step 0 updated them:
git add jan_comparison_v2_state.json jan_comparison_v2_output.txt
git commit -m "$(cat <<'EOF'
SQ + Ross exit coexistence fix + V3 Jan comparison

Added WB_SQ_ROSS_COEXIST env var: when ON, SQ mechanical exits
(target hit at 2R, trailing stops) coexist with Ross 1m signal
exits. SQ handles core profit-taking, Ross handles runner phase.
Previously, Ross exit completely blocked SQ mechanical exits
(lines 666, 703, 832, 858 in simulate.py).

V3 comparison: Jan 2025 + Jan 2026 with SQ+Ross combined.
Three-way A/B/C: V1 (SQ only) vs V2 (Ross only) vs V3 (combined).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## What We're Looking For

1. **SQ target hits restored**: V2 had ZERO `sq_target_hit` exits. V3 should have them back. This alone should rescue several trades.
2. **Best of both worlds**: SQ catches the clean 2R exit on fast spikes. Ross manages the runner with 1m intelligence (CUC, MACD, structural trail) instead of a dumb trailing R multiplier.
3. **MP unchanged**: Coexist flag only affects SQ/VR guard lines. MP trades should be identical to V2.
4. **Combined P&L**: V3 should be the highest of all three versions — SQ profits from V1 + MP profits from V2.
5. **Runner value**: Does Ross's 1m signal management of the post-target runner beat V1's mechanical runner trail?

This is the hypothesis that Perplexity identified: mechanical exits for profit-taking, 1m signals for runner management. V3 tests it.
