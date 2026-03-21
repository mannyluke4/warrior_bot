# P0 — STOP MEGATEST — sim_start bug invalidates all results

## Priority: P0 — IMMEDIATE (stop current megatest before doing anything else)
## Created: 2026-03-21 by Cowork (Opus)
## Blocks: Megatest, OOS corrected backtest, YTD corrected backtest, all simulations

### FIRST ACTION — Confirm Receipt

Before doing anything else, create `cowork_reports/directive_acknowledged.md` with the current timestamp confirming you've read this directive. This lets the team verify via Cowork that you've picked it up.

```markdown
# Directive Acknowledged
- Timestamp: [current time]
- Directive: DIRECTIVE_FIX_SIM_START_BUG.md
- Status: Read and beginning work
```

Then proceed with the steps below.

---

### HOURLY DIRECTIVE CHECK (Required for overnight/weekend runs)

During long-running tasks, check the `warrior_bot` folder for new or updated DIRECTIVE files at the top of every hour. Specifically:
- Look for any file matching `DIRECTIVE_*.md` that is newer than the last check
- If a new or modified directive is found, **READ IT IMMEDIATELY**
- If it contains a STOP instruction, halt the current task and follow the new directive
- Log each hourly check in the run log with a timestamp (e.g., `"Hourly directive check: no new directives"` or `"Hourly directive check: found DIRECTIVE_XYZ.md, reading now"`)

This prevents situations where a critical directive sits unread for hours while a long task runs.

---

## ⚠️ CRITICAL: State Machine Pollution Affects ALL Strategies — ALL Results Invalid

**This is not just a timing issue. This is a state machine corruption issue.**

When `sim_start=04:00` instead of `07:00`, the simulator processes 3 hours of dead pre-market bars as "live" signals through the detector state machine. This doesn't just shift trade timing — it **fundamentally corrupts the internal state** for every strategy:

- **EMAs, VWAP, and all indicators are seeded differently.** The detector builds its context from bars it thinks are "live" but are actually pre-market noise. By 07:00, the EMA values, VWAP anchor, and HOD tracking are all wrong compared to the correct seeding path.
- **The detector cycles through states on pre-market noise.** The state machine (impulse → pullback → ARM → trigger) processes 3 hours of low-volume pre-market bars as if they were real market action. It may ARM and disarm multiple times on noise before the real session even starts.
- **By the time real market action begins, the state machine is in a completely wrong state.** Setups that SHOULD fire don't fire. Setups that SHOULDN'T fire may fire on noise. The detector is not just "late" or "early" — it's seeing a different reality.

**Proven impact:** VERO on Jan 16, 2026 — the single biggest trade in the dataset (+$18,583 standalone) — produced **zero trades** in the megatest because the state machine was polluted by 3 hours of pre-market bars fed as live data.

### ALL megatest results are unreliable — every strategy, every combo

| Combo | Status | Why Invalid |
|-------|--------|-------------|
| MP-only | FAULTY | State pollution: 46% of candidates had wrong sim_start. EMA/VWAP seeding wrong for every stock with early sim_start. MP detector cycled through states on pre-market noise. |
| SQ-only | FAULTY | State pollution: Squeeze detector uses the same bar builders and state tracking. Wrong seeding means wrong HOD, wrong volume profiles, wrong level detection. Squeeze trades that fired may not exist with correct timing, and squeezes that should have fired may have been missed. |
| MP+SQ | FAULTY | Both detectors polluted. The +$130K headline number is meaningless. |
| All-three | FAULTY | All three detectors polluted. **VR showing 0 trades is a FALSE NEGATIVE until proven otherwise** (see below). |

### VR must be re-evaluated — 0 trades may be caused by the bug

The decision to shelve VR Strategy 4 was based on:
1. V1/V2/V3 tuning: 0 trades across 27 standalone test runs
2. Megatest all_three: 0 VR trades through 72+ days

**Item 2 is now invalid.** The megatest's VR results cannot be used as evidence because the state machine pollution from wrong sim_start may be preventing the VR detector from recognizing valid VWAP reclaim patterns. VR's viability must be re-evaluated with corrected v2 data.

Item 1 (standalone tuning) used hardcoded sim_start times and is NOT affected by this bug. Those 27 runs showing 0 trades are still valid evidence. However, the standalone tests only covered a handful of manually-selected stocks. The full 297-day megatest with corrected timing is needed to confirm whether VR truly produces zero trades at scale.

**Bottom line: We have ZERO reliable megatest data right now.** All strategy conclusions, interaction effects, P&L numbers, and combo comparisons drawn from these results are suspect until the corrected v2 megatest completes.

---

## The Bug

The `resolve_precise_discovery()` function in `scanner_sim.py` (lines 570-573) is setting `sim_start` to the exact minute a stock first meets scanner filter criteria (gap >= 10%, cumulative volume >= 50K, price $2-$20), starting from **4:00 AM**. For many stocks, that's 04:00-04:05 AM.

This is wrong. `sim_start` should represent when the **scanner would have discovered the stock at a checkpoint**, not when the stock first met filter criteria in the dark of premarket. A stock that hits criteria at 4:00 AM wouldn't appear on the scanner until the 7:15 AM premarket scan or a later rescan checkpoint.

The bad logic (line 570-573):
```python
# Only update if earlier than current sim_start
if precise_start < old_start or old_start == "?":
    c["sim_start"] = precise_start  # <-- OVERWRITES with 04:00 AM etc.
```

This was introduced by commit `efa9b3f` ("Re-scan all 296 dates with precise discovery timestamps") which ran `resolve_precise_discovery()` across all 297 dates and overwrote sim_start values.

---

## Evidence

### Scale
- **405 out of 873 candidates (46%)** have `sim_start` before 7:00 AM
- **115 stocks** have `sim_start = 04:00` (the most common bad value)
- **419 candidates** have `sim_start` earlier than their own `first_seen_et` (backwards)

### VERO smoking gun
- VERO (Jan 16, 2026): `sim_start=04:00`, `first_seen=04:00`
- Standalone regression with `sim_start=07:00`: **+$18,583** (1 trade, 18.6R)
- Megatest MP-only with `sim_start=04:00`: **$0** (0 trades)
- When simulate.py gets `sim_start=04:00`, it feeds 3 hours of pre-market bars as "live" data instead of seed context. This shifts EMA/VWAP state and prevents the impulse-pullback-ARM pattern from triggering.

### Other examples
| Date | Symbol | sim_start (bad) | first_seen_et | What should be |
|------|--------|-----------------|---------------|----------------|
| 2026-01-16 | VERO | 04:00 | 04:00 | 07:00 (premarket) |
| 2025-05-22 | XAGE | 04:05 | 04:00 | 07:00 (premarket) |
| 2025-01-02 | VSME | 04:00 | 08:00 | 08:00 (rescan) |
| 2025-08-18 | MB | 09:41 | 10:00 | 10:00 (rescan) |
| 2025-01-21 | PTHS | 09:35 | 10:00 | 10:00 (rescan) |

### Megatest impact
- MP-only completed results: **invalid** (250 trades, -$14,483 net — but nearly half had wrong timing)
- MP+SQ currently running: **invalid** (same bad sim_start data)
- Both lost VERO's +$18,583 trade entirely, and likely missed or mishandled dozens of other big movers

---

## The Fix

### Step 1: Stop the megatest
Kill whatever megatest combo is currently running. The results are garbage.

### Step 2: Fix `resolve_precise_discovery()` in `scanner_sim.py`

The precise discovery time is useful metadata, but `sim_start` must respect scanner checkpoint timing. A stock cannot be traded before the scanner checkpoint that would have discovered it.

Replace the sim_start assignment logic (around line 567-573) with:

```python
if discovery_minute:
    precise_start = f"{discovery_minute.hour:02d}:{discovery_minute.minute:02d}"
    c["precise_discovery"] = precise_start

    # sim_start = the scanner checkpoint that would have found this stock
    # NOT the raw minute it first met criteria
    old_start = c.get("sim_start", "?")

    # Determine the correct sim_start based on scanner checkpoint logic:
    # - If discovered before 07:15 ET -> premarket stock -> sim_start = 07:00
    # - If discovered after 07:15 ET -> rescan stock -> sim_start = next checkpoint
    CHECKPOINTS = ["08:00", "08:30", "09:00", "09:30", "10:00", "10:30"]
    if precise_start < "07:15":
        correct_start = "07:00"
    else:
        correct_start = "10:30"  # default to last checkpoint
        for cp in CHECKPOINTS:
            if precise_start <= cp:
                correct_start = cp
                break

    c["sim_start"] = correct_start
    c["discovery_time"] = correct_start
    c["discovery_method"] = "precise"
else:
    c["precise_discovery"] = None
```

### Step 3: Re-run discovery resolution across all 297 dates

No Databento re-fetch needed. Just reprocess existing data with the corrected logic:

```bash
# Re-run scanner_sim.py in reprocess mode (or whatever the entry point is)
# to update all scanner_results/*.json with corrected sim_start values
python scanner_sim.py --reprocess-all  # or equivalent
```

If there's no `--reprocess-all` flag, the fix can be applied as a standalone script that:
1. Loads each `scanner_results/YYYY-MM-DD.json`
2. For each candidate, computes `correct_start` from `precise_discovery` using the checkpoint logic above
3. Updates `sim_start` and `discovery_time` in place
4. Writes the corrected JSON back

### Step 4: Verify the fix

Spot-check corrected values:
```python
# After fix, these should be true:
assert scanner["VERO"]["2026-01-16"]["sim_start"] == "07:00"  # was 04:00
assert scanner["VSME"]["2025-01-02"]["sim_start"] == "08:00"  # was 04:00, first_seen=08:00
assert scanner["MB"]["2025-08-18"]["sim_start"] == "10:00"    # was 09:41, first_seen=10:00
assert scanner["PTHS"]["2025-01-21"]["sim_start"] == "10:00"  # was 09:35, first_seen=10:00
```

Also verify: no candidates should have `sim_start < 07:00` after the fix.

### Step 5: Run standalone regression

```bash
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# TARGET: +$18,583

python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# TARGET: +$6,444
```

Regression should still pass — standalone sims use hardcoded times, not scanner data.

### Step 6: Project-Wide Bug Sweep & Verification (BLOCKS MEGATEST RESTART)

**DO NOT restart the megatest until this entire step is complete and documented.**

The sim_start bug was a symptom of a deeper problem: assumptions in the simulation pipeline that don't match how the live bot actually operates. Before committing to another multi-hour megatest run, CC must systematically verify there are no other hidden discrepancies.

#### ⚠️ IMPORTANT: Cowork Preliminary Audit Available

**Cowork has already completed a preliminary pipeline audit.** See:

```
cowork_reports/pipeline_audit_preliminary.md
```

This audit identified **13 potential bugs** (5 critical, 5 medium, 3 low) across the simulation pipeline. The critical findings that need immediate attention are:

1. **Overlapping trades across stocks** — The megatest runner iterates stocks sequentially and passes all trades to the day loop, but simulate.py can produce multiple trades per stock. The live bot is single-position (one open trade at a time). The sim may be counting overlapping positions that couldn't coexist in the live bot.

2. **Cumulative notional never releases** — `day_notional` in `_run_config_day()` only increases. When a trade exits, its notional is never freed. This means the notional cap gets consumed by early trades and blocks later ones, even after the early trades have closed. The live bot releases notional on exit.

3. **No ARM time gate in simulate.py** — The live bot has `WB_ARM_EARLIEST_HOUR_ET=7` which prevents the detector from arming before 7 AM ET. The sim has no equivalent gate. Combined with the sim_start bug, the detector could ARM on 4-5 AM pre-market noise.

4. **VWAP seed calculation mismatch** — `bars.py` computes VWAP using `close × volume` for historical bars. The live bot uses `trade_price × trade_size` from the websocket feed. These produce different VWAP values, especially during volatile pre-market when close ≠ VWAP for 1-minute bars.

5. **resolve_precise_discovery corrupts checkpoint stocks too** — The sim_start bug doesn't just affect premarket stocks. Stocks discovered at rescan checkpoints (08:00, 09:30, etc.) also had their sim_start overwritten with the precise minute, e.g., sim_start=09:41 when it should be 10:00. This affects the "late discovery" stocks that are supposed to start simulating at the checkpoint, not before.

**CRITICAL: These are PRELIMINARY findings. CC must independently verify each one.** Cowork identified these through code reading and logical analysis, but has NOT run the actual code to confirm. Some findings may be wrong — the code may handle edge cases we didn't see, or the behavior may be intentional. For each finding:

1. **Read the audit report** (`cowork_reports/pipeline_audit_preliminary.md`) — it includes the specific code locations, expected vs actual behavior, and suggested verification tests for each bug
2. **Verify independently** — read the actual code, run the suggested tests, check if the behavior matches what the audit claims
3. **If confirmed, fix it** — gate with env var, re-run regression
4. **If not a real bug, document why** — so we don't re-investigate later
5. **Look for additional issues** the audit may have missed — Cowork's audit was code-reading only and may have gaps

**Do NOT blindly apply fixes based on the audit alone.** The audit is a starting point for CC's own investigation, not a set of instructions to execute without verification.

#### 6a. Audit the Full Simulation Pipeline

Walk through every step of the pipeline end-to-end. At each step, ask: **"Does this behave the same way the live bot would?"**

```
scanner_sim.py → candidate selection → run_megatest.py → simulate.py → bars.py → detector → trade_manager.py → exit logic
```

#### 6b. Specific Areas to Check

Each of these has been identified as a potential source of sim-vs-live divergence:

| Area | What to Check | Risk Level |
|------|--------------|------------|
| **Seed vs live bar classification** | Does simulate.py split bars at exactly the same point the live bot would? Are there edge cases where a bar straddles the sim_start boundary? | HIGH — this is the same class of bug as sim_start |
| **VWAP anchoring** | Does VWAP anchor at the same time in sim vs live? The live bot anchors at 4AM. Does simulate.py do the same regardless of sim_start? | HIGH — wrong anchor changes every VWAP-dependent signal |
| **EMA initialization** | Are EMAs seeded consistently between standalone regressions (sim_start=07:00) and megatest (sim_start=variable)? Does changing sim_start change the EMA seed values? | HIGH — EMAs drive impulse detection |
| **Position sizing** | Does the megatest runner calculate shares/notional the same way the live bot does? Check: risk computation, R value source, share rounding, notional calculation | MEDIUM — affects P&L magnitude but not trade selection |
| **Daily trade caps** | Does the megatest enforce MAX_TRADES_PER_DAY the same way? Does the live bot count across all strategies or per-strategy? | MEDIUM — affects which trades get taken on busy days |
| **Candidate ranking/selection** | Does the megatest's `load_and_rank()` pick the same top-N stocks the live bot's scanner would? Same composite score formula? Same filters? | MEDIUM — wrong selection = wrong stocks simulated |
| **Stop loss execution** | Does simulate.py handle stops the same way? Market orders vs limit? Slippage? Does it check stops on every tick or only on bar close? | MEDIUM — affects loss magnitudes |
| **Time filters** | Does the sim respect the same trading hours? Does the live bot refuse trades before 9:30 ET? Does the sim? Are there pre/post-market trade windows? | MEDIUM — could allow phantom trades |
| **Config loading** | Does the megatest pass the exact same .env config the live bot uses? Are there any env vars that differ? Diff the megatest's `ENV_BASE` against the live `.env`. | HIGH — config drift = different behavior |
| **State machine reset** | Does the detector reset cleanly between stocks within a single day? Between days? Or does state from stock A leak into stock B's simulation? | HIGH — state leakage = phantom signals |
| **Tick cache staleness** | Are cached ticks for 2026 dates still valid, or has the data source been corrected since they were fetched? | LOW — unlikely but worth a spot-check |

#### 6c. Fix Protocol for Each Bug Found

For each potential discrepancy discovered:

1. **Document it** — what it is, where in the code, expected vs actual behavior
2. **Small verification test** — pick 1-2 known stocks, run with and without the fix, compare output
3. **If confirmed, fix it on the spot** — gate with an env var if there's any risk of regression
4. **Re-run standalone regression** — VERO +$18,583, ROLR +$6,444 must still pass
5. **Move on** — don't let one bug block the sweep of others

#### 6d. Pre-Megatest Verification Checkpoint

Before running v2, execute these targeted tests to verify the full pipeline is clean:

```bash
# Test 1: VERO (Jan 16, 2026) — must produce ~$18K MP trade with sim_start=07:00
# This is the primary regression. If this fails, STOP.
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# TARGET: +$18,583

# Test 2: ROLR (Jan 14, 2026) — standard regression
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# TARGET: +$6,444

# Test 3: ARTL (Mar 18, 2026) — verify squeeze fires AFTER discovery time (sim_start=08:00), not before
# Run with corrected sim_start from scanner_results
python simulate.py ARTL 2026-03-18 08:00 12:00 --ticks --tick-cache tick_cache/
# Compare: does the first trade timestamp fall after 08:00?

# Test 4: CWD (Sep 9, 2025) — verify trades only fire after discovery time
# scanner_results should show a non-07:00 sim_start for this stock
# Run with the corrected sim_start and verify no trades before that time

# Test 5: Run 2-3 random stocks through the MEGATEST RUNNER (not standalone simulate.py)
# to verify the full pipeline: scanner data → candidate selection → sim_start → simulate.py → trade output
# Pick stocks from different months (one early 2025, one late 2025, one 2026)
# Compare output against standalone simulate.py runs with the same parameters
```

#### 6e. Document Everything

Log ALL verification test results to a new file:

```
cowork_reports/pre_megatest_v2_verification.md
```

This file must include:
- Summary of pipeline audit findings (bugs found, bugs fixed, areas verified clean)
- Output of each verification test (command run, expected result, actual result, PASS/FAIL)
- List of all code changes made during the sweep (with commit hashes)
- Final go/no-go recommendation for starting the v2 megatest

#### 6f. User Review Gate

**The verification log must be complete and available for user review BEFORE the v2 megatest starts.** Do NOT start the megatest until:
- [ ] All pipeline audit areas in 6b have been checked (mark each as verified or fixed)
- [ ] All verification tests in 6d pass
- [ ] `cowork_reports/pre_megatest_v2_verification.md` is written and committed
- [ ] Standalone regressions pass (VERO +$18,583, ROLR +$6,444)
- [ ] No candidates have `sim_start < 07:00` in any scanner_results JSON

**Zero surprises in v2. Every known issue fixed, verified with small tests, documented, and reviewed before committing to a multi-hour run.**

---

### Step 7: Delete stale megatest results and restart v2 from scratch

**Only proceed here after Step 6 is complete and the verification log is written.**

```bash
# Keep _FAULTY files for comparison, delete the active state files
rm megatest_results/megatest_state_mp_only.json 2>/dev/null
rm megatest_results/megatest_state_mp_sq.json 2>/dev/null
rm megatest_results/megatest_state_sq_only.json 2>/dev/null
rm megatest_results/megatest_state_all_three.json 2>/dev/null
rm megatest_results/MEGATEST_RESULTS_mp_sq.md 2>/dev/null
rm megatest_results/MEGATEST_RESULTS_sq_only.md 2>/dev/null
rm megatest_results/megatest_sq_only.log 2>/dev/null
rm megatest_results/megatest_all_three.log 2>/dev/null

# Restart v2 megatest with corrected data
python run_megatest.py mp_only
```

### Step 8: Also re-run OOS and YTD corrected backtests

These use the same scanner_results data. Delete their state files and restart:
```bash
rm oos_2025q4_backtest_state.json
rm ytd_v2_backtest_state.json

python run_oos_2025q4_backtest.py
python run_ytd_v2_backtest.py
```

---

## What is NOT affected

- **Tick cache**: Raw tick data is fine, no re-fetch needed
- **Raw scanner candidate lists**: The stock lists themselves are correct. Only `sim_start` field is wrong.
- **Standalone regressions**: VERO/ROLR use hardcoded `07:00`, not scanner data
- **Live bot**: Uses real-time scanner with actual discovery timestamps, not this function
- **`precise_discovery` field**: Keep this — it's correct and useful as metadata. Just don't use it as `sim_start`.

---

## Why this matters

The original discovery timing bug (DIRECTIVE_FIX_DISCOVERY_TIMING.md) fixed the batch runners to USE sim_start from scanner data instead of hardcoding 07:00. That fix was correct. But then commit `efa9b3f` corrupted the scanner data itself by overwriting sim_start with raw discovery minutes instead of scanner checkpoint times. So the runners are correctly reading sim_start — but the sim_start values are wrong.

This is worse than the original bug in some ways: the old bug (hardcoded 07:00) was at least conservative for premarket stocks (correct for those found before 7:15). The new bug sends sim_start to 04:00 for 13% of all candidates, which is never correct for backtesting purposes.

---

## Naming Convention for Corrected Results

Cowork has renamed all existing faulty megatest results with a `_FAULTY` suffix. **Do NOT delete these** — keep them for comparison. The faulty files are:

- `megatest_state_mp_only_FAULTY.json`
- `megatest_state_mp_sq_FAULTY.json`
- `MEGATEST_RESULTS_mp_only_FAULTY.md`
- `megatest_mp_sq_FAULTY.log`

**All new corrected results must use `_CORRECTED` or `_v2` naming:**

| Purpose | Faulty (do not use) | Corrected (use this) |
|---------|--------------------|--------------------|
| MP-only state | `megatest_state_mp_only_FAULTY.json` | `megatest_state_mp_only_v2.json` |
| MP+SQ state | `megatest_state_mp_sq_FAULTY.json` | `megatest_state_mp_sq_v2.json` |
| SQ-only state | (never ran) | `megatest_state_sq_only_v2.json` |
| All-three state | (never ran) | `megatest_state_all_three_v2.json` |
| MP-only report | `MEGATEST_RESULTS_mp_only_FAULTY.md` | `MEGATEST_RESULTS_mp_only_CORRECTED.md` |
| Final summary | (never generated) | `MEGATEST_SUMMARY_CORRECTED.md` |

The `_v2` / `_CORRECTED` results are the trusted source. Any Cowork simulations (equity curves, PDT sims, dynamic cap sims) will be rebuilt from the corrected data once available.

**If run_megatest.py hardcodes state file names**, update them to use the `_v2` suffix before restarting. Check the `COMBO_OVERRIDES` or state file path construction in the runner.

---

## ADDITION: Dynamic Notional Cap & Scaling Variables

### Discovery from the Faulty Megatest

Even though the megatest results are invalid due to the sim_start bug, we found a **real structural flaw** in the static notional cap that would apply regardless of timing data:

**SQ-only hit a ceiling.** Once SQ-only equity exceeded ~$140K, the $50K static notional cap blocked trades on low-priced stocks ($2-$4). The math:
- Risk per trade = equity × 2.5% = $140K × 0.025 = $3,500
- Shares = risk / R = $3,500 / $0.14 = 25,000
- Notional = 25,000 × $2.00 = $50,000 → **hits cap → trade skipped**

This caused SQ-only to **skip 62 entire trading days** of squeeze trades from Aug 2025 onward, leaving **+$38,611** on the table. Meanwhile, MP+SQ outperformed SQ-only (+$130,621 vs +$118,369) specifically because MP losses kept equity ~$10-20K lower, keeping trades under the notional cap. The losing strategy paradoxically helped by preventing the winning strategy from self-sabotaging.

### Fix 1: Dynamic Notional Cap (P1 — implement in v2 megatest)

Add a dynamic notional cap that scales with equity. Gate with `WB_DYNAMIC_NOTIONAL_CAP=1` (OFF by default):

```python
if os.getenv("WB_DYNAMIC_NOTIONAL_CAP", "0") == "1":
    base_cap = int(os.getenv("WB_NOTIONAL_CAP_BASE", "50000"))      # Floor
    headroom = int(os.getenv("WB_NOTIONAL_CAP_HEADROOM", "20000"))   # Added to equity
    hard_cap = int(os.getenv("WB_NOTIONAL_CAP_HARD", "150000"))      # Ceiling
    notional_cap = min(equity + headroom, hard_cap)
    notional_cap = max(notional_cap, base_cap)  # Never go below base
else:
    notional_cap = MAX_NOTIONAL  # Static $50K (current behavior)
```

Scaling behavior:
| Equity | Dynamic Cap | Static Cap | Effect |
|--------|-------------|------------|--------|
| $30,000 | $50,000 | $50,000 | Same |
| $50,000 | $70,000 | $50,000 | +$20K headroom |
| $70,000 | $90,000 | $50,000 | +$40K headroom |
| $100,000 | $120,000 | $50,000 | +$70K headroom |
| $130,000 | $150,000 | $50,000 | Hard ceiling reached |
| $200,000 | $150,000 | $50,000 | Capped at $150K |

### Fix 2: Audit of All Scaling Variables

Review every parameter in the megatest/batch runner for scaling behavior. For each: is it static or dynamic, and should it change?

| Parameter | Current Value | Scales? | Recommendation |
|-----------|--------------|---------|----------------|
| **Notional cap** | $50,000 static | No | **CHANGE** → dynamic (see Fix 1 above) |
| **Risk per trade** | 2.5% of equity | Yes (already) | Keep. Scales naturally with equity. |
| **Daily loss limit** | -$1,500 static | No | **Consider dynamic**: at $30K equity this is -5% (aggressive). At $150K it's -1% (very tight). Recommend: `max(-$1,500, equity * -0.03)` so it scales to -3% of equity but never below -$1,500. Gate with `WB_DYNAMIC_DAILY_LOSS=1`. |
| **Max trades/day** | 5 static | No | Keep static. This is a discipline limit, not a sizing parameter. 5 trades/day is Ross Cameron's typical max regardless of account size. |
| **Max consecutive losses** | 2 (Config A) / unlimited (Config B) | No | Keep static. This is a behavioral guard, not sizing-related. |
| **Share count** | Computed: risk / R | Yes (already) | Scales with equity via risk. No change needed — but the NOTIONAL CAP is what blocks it (Fix 1). |
| **Min entry score** | 8.0 (Config A) / 0 (Config B) | No | Keep static. Score quality shouldn't change with account size. |
| **Mid-float risk cap** | $250 for float > 5M | Static dollar amount | **Consider dynamic**: at $30K equity, $250 risk is 0.83% (reasonable). At $150K, it's 0.17% (too small to matter). Recommend: `min(risk, equity * 0.005)` for mid-float stocks. Low priority — few mid-float candidates pass the scanner anyway. |
| **Stop distance / R value** | Set by detector, not configurable | N/A | No change. R is determined by price action, not account size. |
| **Warmup bars** | 5 bars | N/A | Not sizing-related. No change. |

### V2 Megatest: Testing Plan

The corrected megatest (v2) should test BOTH the sim_start fix AND the dynamic notional cap. Suggested approach:

**Config A vs Config B split:**
- **Config A**: Corrected sim_start + **static** notional cap ($50K) + min_score=8.0
- **Config B**: Corrected sim_start + **dynamic** notional cap (equity+$20K, max $150K) + min_score=0

This isolates two variables per combo:
1. Static vs dynamic notional cap (the main question)
2. Score gating (existing A/B split)

For each of the 4 combos (mp_only, sq_only, mp_sq, all_three), we get:
- Config A: conservative (score gate + static cap)
- Config B: aggressive (no score gate + dynamic cap)

**Alternatively**, if CC prefers to isolate variables cleanly, run 6 combos instead of 4:
- mp_only_static, mp_only_dynamic
- sq_only_static, sq_only_dynamic
- mp_sq_static, mp_sq_dynamic

But this doubles runtime (~100 hours). The A/B split within each combo is more practical.

**Key metric to watch:** Does SQ-only with dynamic cap outperform MP+SQ with static cap? If yes, the notional cap was the entire reason MP+SQ beat SQ-only, and MP adds no real value. If SQ-only-dynamic still trails MP+SQ-dynamic, then MP genuinely contributes.

---

---

## ADDITION: Live Bot Reliability Audit — 4 MUST-FIX Before Monday

### Full audit: `cowork_reports/live_bot_audit.md`

Cowork completed a live bot reliability audit (separate from the simulation pipeline). **19 bugs found (8 critical, 6 medium, 5 low).** The live bot missed every single trading day the week of March 17-20, 2026 — four different failure modes across four days.

The #1 finding: `set(list(passing_symbols)[:500])` in `market_scanner.py` line 136 takes an **arbitrary random 500** from 3,200+ symbols that pass the price pre-filter. Python `set` iteration is non-deterministic. The scanner is sending random $2-$20 stocks to the expensive stock_filter step instead of the day's actual gap-up movers. This caused 3 of 4 missed days this week (Mon/Tue/Thu).

### ⚠️ MUST-FIX BEFORE MONDAY (4 items)

These are blocking live trading. CC must independently verify each finding in `cowork_reports/live_bot_audit.md` and fix before market open Monday:

1. **Scanner sort** (Finding 1) — Sort `passing_symbols` by volume/gap% descending before truncating to 500. The snapshot data already has price/volume available during `prefilter_by_price`. ~20 lines in `market_scanner.py`.

2. **Crash detection** (Findings 2, 3) — `daily_run.sh` launches bot.py in background, then sleeps 7 hours. If bot.py crashes 1 second later (as happened Friday 3/20), nobody knows. Add a post-launch `kill -0 $BOT_PID` health check after 10 seconds, plus a watchdog loop. Add Pushover/webhook alerting for crash, zero-symbol, and first-trade events. ~50 lines in `daily_run.sh` + new `notify()` function.

3. **Abort on zero symbols** (Finding 4) — When `filtered_watchlist` is empty, bot.py currently starts all threads and runs all day watching nothing (happened Thursday 3/19). Add: if 0 symbols after filtering, send alert and log clearly. ~5 lines in `bot.py`.

4. **Pre-flight smoke test** (Finding 6) — `python3 -c "from market_scanner import MarketScanner; from trade_manager import PaperTradeManager; print('Imports OK')"` before launching bot.py. Friday's crash was a `ModuleNotFoundError` that would have been caught by a 1-line smoke test. ~3 lines in `daily_run.sh`.

### Remaining 15 bugs

The remaining 15 bugs (Findings 5-19) should be reviewed and prioritized alongside the 13 simulation pipeline bugs from `cowork_reports/pipeline_audit_preliminary.md`. Categories:

- **Should fix this week:** live_scanner.py integration (Finding 14), feed reconnection loop (Finding 9), stock_filter parallelization (Finding 10), thread health monitoring (Finding 8), filter fallback fix (Finding 11)
- **Nice to have:** log rotation (Finding 13), AppleEvent timeout investigation (Finding 19), reconcile rate limiting (Finding 18)

**Same protocol as the simulation audit: read the report, verify independently, fix if confirmed, document if not a real bug.**

---

*Directive by Cowork (Opus) — 2026-03-21, updated with scaling analysis + live bot audit*
