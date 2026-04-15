# Finding — No-reentry gate already exists, EPL bypasses it

**Author:** CC (Opus)
**Date:** 2026-04-15 evening
**For:** Cowork (Q3 scope decision before autopsy continues)
**Status:** Escalation — directive's Q3 premise doesn't match code state.

---

## What I found

The "no re-entry after loss on same symbol" gate **already exists** and is **currently active in sim**. It lives in `micro_pullback.py` as Gate 5. The `.env` reads:

```
WB_QUALITY_GATE_ENABLED=0      # master: only Gate 5 runs when off
WB_NO_REENTRY_ENABLED=1        # Gate 5: block re-entry after a loss
WB_MAX_SYMBOL_LOSSES=1         # stricter than CC's proposed "2"
WB_MAX_SYMBOL_TRADES=2
```

Gate 5 source: `micro_pullback.py:900 _gate5_no_reentry()`, tracked via `_session_losses` / `_session_trades` (lines 170–171), wired in at line 932.

## What the BIRD sim shows

Two `QUALITY_GATE` lines in today's `simulate.py BIRD 08:15 16:00` output:

```
QUALITY_GATE symbol=BIRD gate=no_reentry result=PASS losses=0/1 trades=0/2
QUALITY_GATE symbol=BIRD gate=no_reentry result=FAIL reason=losses_4_>=_max_1
```

The gate failed (blocked) with losses=4, max=1. But BIRD still produced 10 trades. T8, T9, T10 all fired *after* the gate should have been blocking — meaning those trades went through a path that does not consult Gate 5.

Most likely path: `epl_mp_reentry.py` (EPL MP re-entry framework), which was rebuilt after the MP detector was deprecated. T10's exit reason is literally `epl_mp_stop_hit`; T8 and T9 are `topping_wicky_exit_full` (MP-style signal exit), consistent with MP detector firing inside the EPL re-entry path.

## Implication for the directive's Q3

The directive asks to simulate a "no re-entry after 2 consecutive losses on same symbol" gate across YTD and compute the delta. But:

- A stricter version (max_losses=1) of that gate is already live in sim.
- The real question is not "should this gate exist?" but "why doesn't it cover the EPL path?"
- A post-hoc filter of the YTD trade log as directed would conflate "gate fires now" trades with "gate would fire under CC's proposal" trades, making the delta uninterpretable.

## Two scope options for Cowork

**A. Re-scope Q3.** Investigate why Gate 5 doesn't apply to EPL re-entries, then quantify the YTD impact of *extending* Gate 5 (or adding a mirror gate) to the EPL path. Still autopsy-only, no code changes.

**B. Proceed as written.** Produce the table Cowork asked for, but flag this finding in the Non-findings section and offer (A) as the follow-up directive.

I lean **A**. The delta is cheaper to compute (EPL trades are a minority of YTD trades, easy to isolate), more informative (tells us exactly what a gate extension would save), and directly actionable. But the directive is explicit that autopsy + YTD analysis is the full scope, so I'll run whichever you pick.

## Q1 and Q2 are unaffected

Q1 (why BIRD didn't re-arm post-T10) and Q2 (EPL flow trace for T10) still stand as written — if anything, Q2 is now *more* critical because it's the mechanism by which Gate 5 was bypassed.

---

*CC, 2026-04-15 evening. Surfacing before continuing.*
