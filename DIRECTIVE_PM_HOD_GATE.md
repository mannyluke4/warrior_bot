# DIRECTIVE: Test PM HOD Gate (WB_SQ_PM_HOD_GATE)

**Author**: Cowork (Opus)
**Date**: 2026-03-25
**For**: CC (Sonnet)
**Priority**: HIGH — Prototype is already in squeeze_detector.py, needs regression + comparison testing

---

## Context

The squeeze detector's IDLE→PRIMED gate currently requires `bar.high >= session_hod` (the running high-of-day built from seed bars). The problem: `session_hod` is **seed-bar-dependent**. The same stock with the same price action produces different detector behavior depending on when it was discovered by the scanner, because different sim_start times mean different numbers of seed bars, which means a different starting HOD threshold.

**CJMB Jan 15 was the proof case:**
- Discovered at 09:00 (old scanner): session_hod = ~$2.30 → detector fires on the right bar → +$1,028
- Discovered at 08:45 (new scanner): session_hod = ~$4.64 → detector fires prematurely on small moves → burns 3 attempts → $0

**The fix:** New env var `WB_SQ_PM_HOD_GATE` (default OFF). When ON, the HOD gate uses `premarket_high` (a fixed value from scanner data) instead of `session_hod`. This makes the detector discovery-time-invariant.

The code change is already committed to `squeeze_detector.py` (lines 44-46 for config, lines 163-176 for the gate logic) and `.env` (WB_SQ_PM_HOD_GATE=0).

---

## Step 0: Git Pull + Verify Code Is Present

```bash
cd /Users/mannyluke/warrior_bot
git pull
source venv/bin/activate
```

Verify the change exists:
```bash
grep "pm_hod_gate" squeeze_detector.py
# Should show: self.pm_hod_gate = os.getenv("WB_SQ_PM_HOD_GATE", "0") == "1"
# And the gate logic in on_bar_close_1m

grep "PM_HOD_GATE" .env
# Should show: WB_SQ_PM_HOD_GATE=0
```

---

## Step 1: Baseline Regression (Gate OFF)

Confirm existing behavior is unchanged with the new code (gate defaults to OFF):

```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

**STOP if either regression fails.** The gate is OFF so results MUST match exactly.

---

## Step 2: PM HOD Gate ON — Regression

Run the same stocks with the gate ON to check for regressions:

```bash
WB_MP_ENABLED=1 WB_SQ_PM_HOD_GATE=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Record P&L — may differ from baseline (that's OK, we're comparing)

WB_MP_ENABLED=1 WB_SQ_PM_HOD_GATE=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Record P&L
```

Record both results. Differences are expected — we need to understand WHY they differ (if they do).

---

## Step 3: CJMB Discovery-Time Invariance Test (THE KEY TEST)

This is the whole point. CJMB should produce similar results regardless of sim_start when the PM HOD gate is ON:

```bash
# Old discovery time (09:00) — was +$1,028 with session_hod gate
WB_MP_ENABLED=1 WB_SQ_PM_HOD_GATE=1 python simulate.py CJMB 2025-01-15 09:00 12:00 --ticks --tick-cache tick_cache/ -v

# New discovery time (08:45) — was $0 with session_hod gate
WB_MP_ENABLED=1 WB_SQ_PM_HOD_GATE=1 python simulate.py CJMB 2025-01-15 08:45 12:00 --ticks --tick-cache tick_cache/ -v
```

Use `-v` (verbose) for both runs. Capture the full output — we need to see every SQ_REJECT, SQ_PRIMED, SQ_ARMED message to trace the state machine.

**Success criteria**: Both sim_starts produce the same (or very similar) trade entries and P&L. If 08:45 now also catches the +$1,028 trade, the fix works.

---

## Step 4: Broader Comparison (if Steps 1-3 pass)

Run the full Jan comparison with gate ON vs OFF to measure net impact:

```bash
# Gate OFF (baseline — should already have results from prior runs)
python run_jan_v1_comparison.py 2>&1 | tee /tmp/jan_v1_gate_off.txt

# Gate ON
WB_SQ_PM_HOD_GATE=1 python run_jan_v1_comparison.py 2>&1 | tee /tmp/jan_v1_gate_on.txt
```

Compare total P&L, trade count, and win rate between the two runs.

---

## Step 5: Report

Write a report to `cowork_reports/2026-03-25_pm_hod_gate_results.md` with:

1. **Baseline regression**: VERO and ROLR with gate OFF — did they match targets?
2. **Gate ON regression**: VERO and ROLR P&L with gate ON — any changes and why?
3. **CJMB invariance test**: Full verbose output comparison for both sim_starts. Did the fix achieve discovery-time invariance?
4. **Broader impact**: Jan comparison totals (gate OFF vs ON) — net P&L delta
5. **Recommendation**: Should we enable WB_SQ_PM_HOD_GATE=1 as the new default?

---

## Step 6: Git Push

```bash
git add cowork_reports/2026-03-25_pm_hod_gate_results.md
git commit -m "PM HOD gate test results: premarket_high vs session_hod for squeeze PRIME gate

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main
```

---

## Important Notes

- The code change is ALREADY in squeeze_detector.py and .env — do NOT modify the implementation
- Gate is OFF by default — live bot behavior is unchanged until we explicitly flip it
- If VERO regresses with gate OFF, something else broke — investigate before proceeding
- The `-v` flag on CJMB runs is critical — we need the full state machine trace
- If Step 4 (broad comparison) shows a significant P&L drop with gate ON, that's useful data — report it honestly, don't try to fix it
