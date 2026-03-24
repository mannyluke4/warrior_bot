# DIRECTIVE: Squeeze Focus V1 — Fix sq_target_hit + Squeeze-Only Validation

**Date:** 2026-03-23
**From:** Manny (via Perplexity research session)
**For:** Claude Code on Mac Mini
**Priority:** P0 — Do this before any other work

---

## Context

Megatest V2 data is conclusive. Squeeze is the strategy:

| Metric | Squeeze Only | Micro Pullback (in mp_sq) |
|---|---|---|
| Trades | 183 | 132 |
| Win Rate | 70% | 33% |
| Net P&L | +$118,369 | -$4,688 |
| Profit Factor | 21.66 | <1.0 |
| Green Months | 11/12 (92%) | Mostly red |
| Avg Loss | -$104 | -$732 |
| Max Drawdown | $525 (0.4%) | N/A |

MP's entire +$12K contribution to mp_sq comes from ONE trade (ROLR +$21,653). Without it, MP is -$26,341 across 297 days. We're leaning into squeeze.

The Ross Exit V2 comparison showed a -$10,799 underperformance vs baseline. Root cause analysis identified the #1 issue: **line 666 in simulate.py** blocks `sq_target_hit` when `WB_ROSS_EXIT_ENABLED=1`. This single line is responsible for -$12,832 in lost revenue.

---

## Task 1: Fix sq_target_hit Coexistence with Ross Exit

**Problem:** When `WB_ROSS_EXIT_ENABLED=1`, simulate.py line 666 skips the entire pre-target squeeze exit block:

```python
# Current code (line 666):
if not t.tp_hit and not self.ross_exit_enabled:
    # squeeze trailing stop... (SKIPPED)
    # squeeze target hit at 2R... (SKIPPED)
```

This means squeeze trades never hit their 2R target. Instead they wait for a 1m candle signal from RossExitManager, but many squeeze moves spike fast and pull back within the same 1-minute bar — so they hit the hard stop or dollar loss cap instead of taking the clean 2R exit.

**Fix:** Let `sq_target_hit` fire as a tick-level mechanical exit (same as hard stop and max_loss_hit), regardless of Ross exit state. The squeeze trailing stop should ALSO remain active pre-target (it's the pre-2R safety net). After the core exits at 2R, hand the runner to Ross exit signals for post-target management.

**Specifically, change line 666 from:**
```python
if not t.tp_hit and not self.ross_exit_enabled:
```

**To:**
```python
if not t.tp_hit:
```

This re-enables BOTH the squeeze trailing stop AND the squeeze target hit for squeeze trades, even when Ross exit is on. Ross exit will still handle:
- All micro_pullback exits (if MP is enabled)
- Squeeze runner management AFTER sq_target_hit fires (via 1m candle signals)
- The structural trailing stop on the runner

**Also fix line 703** (post-target runner phase):
```python
# Current:
if t.tp_hit and t.qty_runner > 0 and t.runner_exit_price == 0 and not self.ross_exit_enabled:
```

Change to let the squeeze runner trail coexist with Ross exit. When Ross exit is on, the runner should be managed by BOTH the mechanical squeeze runner trail AND Ross 1m signals — whichever fires first. This means removing the `and not self.ross_exit_enabled` guard, BUT also wiring Ross exit signals to close the runner if a 1m signal fires before the mechanical trail does.

**Test:** Re-run the YTD 2026 comparison (Ross Exit V2 vs baseline) with this fix. The `sq_target_hit` line in the exit reason table should reappear, and the P&L gap should narrow significantly.

**Regression:** VERO +$18,583 and ROLR +$6,444 with Ross exit OFF must still pass.

---

## Task 2: Run Squeeze-Only Megatest on Fresh Scanner Data

After the rescan fix landed (14 new candidates in Jan 2026, 73→84 unique), CC was running V2 on the fresh data when Dispatch dropped. Pick up where that left off.

**Run the following:**

```bash
python3 run_megatest.py sq_only
```

On the fresh/expanded scanner data. This is the definitive test of squeeze performance with the broader candidate pool.

**Also run mp_sq** so we can see if MP's contribution changes with more candidates:
```bash
python3 run_megatest.py mp_sq
```

**Report both results** in a new cowork report with:
- sq_only P&L, trades, win rate, profit factor, monthly breakdown
- mp_sq P&L with MP vs SQ breakdown (same format as megatest_state_mp_sq.json)
- Delta from the old scanner data results (sq_only was +$118,369)
- Whether MP's contribution changes with more candidates

---

## Task 3: Ross Exit V2 Retest (After Task 1 Fix)

After the sq_target_hit fix is in place, re-run the YTD 2026 Ross Exit comparison:

```
Config A: WB_ROSS_EXIT_ENABLED=0 (baseline)
Config B: WB_ROSS_EXIT_ENABLED=1 (with sq_target_hit fix)
```

**Expected outcome:** The -$10,799 gap should narrow to roughly -$2,000 to +$2,000. The sq_target_hit revenue (+$12,832 in baseline) should now appear in BOTH configs. If V2 is within $2K of baseline, Ross exit is viable for live.

**Report:** Update `cowork_reports/2026-03-23_ytd_ross_exit_v2_comparison.md` with V3 results.

---

## Task 4: Squeeze Risk Sizing Analysis

Once Tasks 1-3 are complete and we have fresh data, run a sensitivity analysis on squeeze risk sizing:

| Config | Risk % | Starting Equity | Description |
|--------|--------|----------------|-------------|
| A | 2.5% | $30,000 | Current (baseline) |
| B | 3.5% | $30,000 | Moderate increase |
| C | 5.0% | $30,000 | Aggressive |

For each config, report:
- Total P&L, win rate, profit factor
- Max drawdown $ and % from peak
- Worst month
- Largest single loss

This is informational only — we won't change live risk until we see these numbers. But with a 0.4% max drawdown at 2.5%, there's likely significant room.

---

## Priority Order

1. **Task 1** — Fix sq_target_hit (30 minutes, code change + regression test)
2. **Task 3** — Ross Exit V2 retest with fix (1-2 hours, YTD run)
3. **Task 2** — Fresh scanner megatest sq_only + mp_sq (overnight run)
4. **Task 4** — Risk sizing analysis (after Task 2 completes)

---

## What NOT to Do

- Do NOT disable micro_pullback yet. Run it in mp_sq for comparison data. We may disable it later based on results, but we want the A/B data first.
- Do NOT change any squeeze entry parameters. Only the exit architecture (sq_target_hit coexistence) changes.
- Do NOT enable Ross exit in live until Task 3 shows it within $2K of baseline.
- Do NOT size up risk in live until Task 4 data is reviewed by Manny.

---

## Files to Modify

| File | Change |
|------|--------|
| `simulate.py` line ~666 | Remove `and not self.ross_exit_enabled` from pre-target guard |
| `simulate.py` line ~703 | Allow squeeze runner trail to coexist with Ross exit |
| `run_megatest.py` | No changes needed (already supports sq_only and mp_sq combos) |

## Success Criteria

- [ ] sq_target_hit appears in V2 (Ross ON) exit reason table
- [ ] YTD V2 vs baseline gap narrows to within $2K
- [ ] VERO regression: +$18,583 (Ross OFF)
- [ ] ROLR regression: +$6,444 (Ross OFF)
- [ ] Fresh scanner megatest sq_only completes with results reported
- [ ] Risk sizing analysis for 2.5%, 3.5%, 5.0% completed

---

*Directive from Perplexity research session 2026-03-23. Analysis based on megatest V2 (297 days), Ross Exit V2 comparison (55 days), Ross Cameron January 2025 trade data (74 trades), and ross_exit.py code review.*
