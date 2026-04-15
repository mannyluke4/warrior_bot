# Design Memo — Dynamic `WB_SQ_MAX_ATTEMPTS` with winner-bonus (Phase 1)

**Author:** CC (Opus)
**Date:** 2026-04-15 evening
**Directive:** `2026-04-15_directive_dynamic_sq_max_attempts.md`
**Status:** Phase 1 deliverable — four design questions answered, awaiting Cowork sign-off before prototype.
**Scope reminder:** squeeze detector only. No EPL, no standalone MP, no box.

---

## Goal

Let cascades continue past attempt 5 when prior attempts proved the stock is working, without loosening the cap on symbols that are just chopping. Concrete counter-example from today: BIRD 2026-04-15 hit `WB_SQ_MAX_ATTEMPTS=5` at T6 (09:03) and missed the $11→$20 afternoon leg. Concrete guard-rail: any dynamic cap must not hand runaway slots to a symbol that is underwater.

---

## Question 1 — Bonus mechanism

### Candidates (from directive)

- **A. Linear R-bonus.** `bonus = int(cumulative_r / R_per_bonus)`. Simple + explicit.
- **B. Win-count bonus.** `bonus = wins − losses` (or `wins − 2·losses`). Decouples from R.
- **C. Hit-rate floor.** Extend cap only while WR on symbol ≥ X%. Adapts to symbol behavior.
- **D. R-recovered bonus.** Extend cap only while symbol's cumulative R stays net positive. "Never chase below water."

### Evaluation against the BIRD / ROLR contrasts

Both BIRD and ROLR hit the cap mid-day. They diverge in *what happened after*:

| Signal | BIRD (chop counterexample) | ROLR (cascade we want to preserve) |
|---|---|---|
| Cumulative R at cap moment | roughly +3.4R (morning winners less T4/T6 losses) | roughly +5.0R+ (T3 alone was +4.0R) |
| Next attempt outcome | more losses through T8/T9/T10 | T10 @ 11:27 was +1.6R winner |
| Net realized-R trajectory | cumulative R turned negative by T10 | cumulative R stayed strongly positive all day |

Let me apply each mechanism to the "should we extend at the moment the base cap is hit?" decision:

| Mechanism | BIRD at cap | ROLR at cap | Cleanest to ROLR, punishes BIRD? |
|---|---|---|---|
| **A. Linear R-bonus (R_per=2.0)** | +3.4R → +1 attempt | +5.0R → +2 attempts | Extends *both* — doesn't distinguish |
| **B. Win-count bonus** | 3W 2L → +1 | 2W 0L → +2 | Extends both |
| **C. Hit-rate floor (>50%)** | 3W 2L = 60% → pass | 2W 0L = 100% → pass | Extends both |
| **D. R-recovered bonus** | net +R at cap moment → +bonus allowed | net +R → +bonus allowed | Extends both at T6 moment, BUT ... |

At *the moment the cap hits*, all four would extend for BIRD too. The differentiator must be **what the mechanism does on subsequent arms as the symbol's state evolves**. That's where D wins: by the time BIRD would try to arm again at 11:08, cumulative R has turned negative. D blocks the late-day attempt. A/B still allow it (R or W/L counts are monotonic-ish and slow to flip).

### Secondary ranking considerations

- **Tunability.** A has one knob (`R_per_bonus`). D has one knob (the "net positive R" floor). B has two (win weight, loss weight). C has one (WR floor). All four are tunable.
- **Predictability.** A is the most predictable — a user can pre-compute the expected bonus for a known cumulative R. D is also predictable but has a cliff (net R going from +0.01 to -0.01 changes behavior).
- **Failure mode in extremes.** If a symbol runs a single massive trade (e.g., ROLR T3 = +4R) and then nothing, A gives many bonus attempts despite no continuation signal; D does too, but any subsequent loss that pushes net-R negative stops it immediately. D is more self-correcting.
- **Cliff-edge risk under D.** A symbol that's +0.1R after one winner + one small loser could go from "allowed +2 bonus" to "allowed 0 bonus" on a single -0.2R chop attempt. That's the mechanism's *point* — but it could cause weirdness where the bot is mid-arming and the cap tightens on the same bar. Solvable with hysteresis (e.g., "cap tightens only on next new arm evaluation, not during an in-flight trigger window").

### Recommendation

**D. R-recovered bonus** as Cowork leaned, with a sharpening:

> Dynamic cap = `base + int(max(0, cumulative_r) / R_per_bonus)` capped by `+BONUS_CAP`.

The `max(0, ...)` is the "never chase below water" rule made explicit: negative cumulative R contributes zero bonus slots. Any bonus already consumed on positive cumulative R stays consumed (attempts already used don't refund), but no further bonus accrues once R dips below 0.

This combines D's guardrail with A's numeric predictability — effectively a *gated* A where the gate is "cumR > 0."

If Cowork prefers pure-A (ignore the gate) to keep it simpler, the tradeoff is loss of the guardrail: pure-A would extend BIRD's cap even as it was underwater at attempt #7+. Given the directive's explicit concern about chop days, the gate is worth the one extra condition.

### Disagreement flag

I'm aligned with Cowork's D lean. If Cowork wanted pure-A (no guard), I'd push back on that specifically. Mechanism C (hit-rate floor) is second-best — it survives the BIRD case about as well, but it's harder to reason about against small-sample noise ("what's my WR when I've taken 2 trades?") and Cowork didn't lean it.

---

## Question 2 — Bonus cap

### Proposal in directive

Hard ceiling at `WB_SQ_MAX_ATTEMPTS + WB_SQ_ATTEMPTS_BONUS_CAP` (defaults: 5 + 5 = 10 max).

### Evaluation

ROLR 2026-01-14 produced **11 trades** over the full day. Even with base=5, the trades continued via EPL/MP paths not gated by attempts. So 10 SQ attempts is generous for realistic cases. VERO 2026-01-16 had 14 trades but similarly most were EPL-path. No observed case in today's canary set would require >10 SQ attempts.

A symbol that legitimately needs more than 10 SQ attempts in one session is either:
- A multi-leg cascade with sustained volume (rare; hall of fame material)
- An artifact of aggressive priming with low-quality setups

The BONUS_CAP=5 ceiling is a reasonable guardrail. I'd accept it as-is.

### Edge case — the initial attempt

The base cap is 5. Bonus adds up to 5 more. But we're also planning to gate bonus accrual behind "cumR > 0." That means until the first winning trade, bonus is 0 and effective cap is 5. No regression on symbols that don't generate early winners — they behave like today. ✓

### Recommendation

**Accept the directive's cap at +5 (absolute max 10 attempts).** Ship with defaults.

---

## Question 3 — Loss-reversal semantics

### Candidates (from directive)

- **X. Monotonic — once earned, never lost.** Simple but naive.
- **Y. Stateless recompute each evaluation.** `bonus = int(max(0, cumR) / R_per_bonus)` recomputed at every arm check.
- **Z. Bonus applies only if most recent attempt was a winner.** Strictest.

### Evaluation

Under mechanism D + Y together:

- BIRD after T6 (at cap): cumR ~ +3.4R → bonus = int(3.4/2.0) = 1 → effective cap = 6.
- BIRD if T7 (attempt 6) is a loss pushing cumR to, say, +1.4R: bonus now = int(1.4/2.0) = 0 → effective cap = 5. **But attempt #6 has already been taken.** So the "current cap" is 5, "already taken" is 6 → next arm request is denied.
- If cumR drops below 0 entirely: bonus = int(max(0, ...)/2) = 0 → cap = 5, still denied.

This behavior is exactly what we want: the moment the symbol stops earning its way, we stop giving it slots. No runaway extensions during chop.

Mechanism X (monotonic) would *not* do this. Once BIRD earned the +1 bonus at T6, a subsequent loss wouldn't revoke it. That's too permissive for chop days.

Mechanism Z (only after immediate winner) is too strict — it would break ROLR's T10, which came several losses after ROLR's last winner (T3 at 08:26, then T6/T7/T8 losses, then T10 winner). Under Z, T10 wouldn't qualify because the trade immediately before it was a loser.

### Recommendation

**Y. Stateless recompute.** Aligns with Cowork's lean. Bonus is derived from the running cumulative-R snapshot at each arm decision. No hysteresis needed on the accrual side; natural hysteresis on the consumption side ("already-taken attempts don't refund").

Minor implementation note for Phase 2: the "hysteresis on in-flight trigger windows" concern from Q1 means the arm-check should read cumR *at arm evaluation time*, not earlier in the pipeline. Don't cache cumR from bar-close events before the tick that actually triggers.

---

## Question 4 — Scope

### Directive's rule

Squeeze detector only. No EPL, no standalone MP, no box. Confirmed aligned.

### Implementation site

`squeeze_detector.py`'s `max_attempts` check. Location confirmed via grep: the cap lives in the arm-rejection path where the `SQ_NO_ARM: max_attempts (N/M)` log line is emitted. Need to find the exact function; deferring to Phase 2 file:line identification.

Env vars to add (per directive):

- `WB_SQ_DYNAMIC_ATTEMPTS_ENABLED` (default `0`) — master gate.
- `WB_SQ_ATTEMPTS_R_PER_BONUS` (default `2.0`) — R realized per +1 bonus slot.
- `WB_SQ_ATTEMPTS_BONUS_CAP` (default `5`) — max bonus slots on top of base.

Base `WB_SQ_MAX_ATTEMPTS=5` unchanged.

### Log line (per directive)

`SQ_ATTEMPTS: base=5 bonus=+2 (cumR=+4.1) → 7/10`

Concrete format, implementable as a single f-string at the arm-decision log site. Adding for every arm decision gives enough granularity to debug chop-day cap thrash without flooding the log on quiet days.

### Data dependency

The mechanism needs the detector to know the symbol's running cumulative R. Squeeze detector already tracks `notify_trade_closed(symbol, pnl)` per the BIRD autopsy's EPL trace — but that's pnl, not R. If cumulative R isn't already tracked per symbol in `SqueezeDetector`, it needs to be added. Phase 2 task.

Implementation sketch (Phase 2, for reference, not code):
- Add `_cumulative_r: dict[str, float]` to `SqueezeDetector.__init__`.
- Update it in `notify_trade_closed(symbol, pnl)`: requires passing in the trade's `r` value too, or computing R from pnl and the stored arm R. Cleaner: pass `r_mult` directly from the trade record at close time.
- Read in the arm-evaluation path, compute dynamic cap, allow or reject.

---

## Summary answer to directive's Phase 1 asks

| Question | Answer |
|---|---|
| 1. Mechanism | **D. R-recovered bonus** with explicit `max(0, cumR)` gate. Combines guardrail + numeric predictability. |
| 2. Cap | **+5 bonus slots** (absolute max 10). Ships as directive default. |
| 3. Loss-reversal | **Y. Stateless recompute.** Bonus = `int(max(0, cumR) / R_per_bonus)` at each arm check. |
| 4. Scope | **Squeeze detector only.** No EPL/MP/box. Env vars + log format per directive. |

Formula:

```
effective_cap = base + min(BONUS_CAP, int(max(0, cumR) / R_per_bonus))
```

With defaults:
- `base = WB_SQ_MAX_ATTEMPTS = 5`
- `R_per_bonus = 2.0`
- `BONUS_CAP = 5`
- Gate: `WB_SQ_DYNAMIC_ATTEMPTS_ENABLED=1` to activate; `0` preserves legacy.

---

## Predicted impact (pre-prototype)

Back-of-envelope from canary data, assuming mechanism D+Y ships as specified:

| Symbol | Date | cumR at cap moment | Bonus earned | Effect |
|---|---|---|---|---|
| BIRD | 2026-04-15 | ~+3.4R (then decays to 0 or negative) | +1 at T6, revoked by T8/T9 | Attempts 6 taken, 7+ blocked once underwater |
| ROLR | 2026-01-14 | ~+5.0R (stays positive) | +2 sustained | SQ attempts 6–7 allowed if triggers occur |
| VERO | 2026-01-16 | Never hit base cap | N/A | No behavior change |
| BATL | 2026-01-26 | ~+0.5R then negative | +0 (gated) | No extension |
| MOVE | 2026-01-23 | Never hit base cap | N/A | No behavior change |

Predicted wins: ROLR possibly picks up additional SQ attempts that are currently capped (needs Phase 3 validation to know if triggers actually occur and what P&L they produce).
Predicted losses: None expected. BIRD doesn't retroactively take T7+ under this mechanism because cumR turns negative before attempt 7 would evaluate.

---

## Risks flagged

1. **Cumulative-R tracking may not exist in squeeze detector yet.** If adding it requires non-trivial plumbing, Phase 2 scope expands. Need to confirm in first 10 min of prototype work. If it's messy, bring back to Cowork for scope adjustment.
2. **Interaction with `notify_trade_closed` race on multi-position symbols.** If two SQ trades close at nearly the same tick, the cumR update order matters. Squeeze detector is single-position-per-symbol, so this shouldn't occur — but verify during prototype.
3. **The ROLR T10 case is EPL, not SQ.** This directive won't help ROLR T10 directly (that was an EPL trade). Where it *would* help ROLR is on any mid-day SQ setup that was capped by base=5. Need to check ROLR verbose log to confirm such setups existed (Phase 3 validation task).
4. **Regression compatibility.** Gate defaults to OFF. All canaries zero-diff at gate OFF. Verifiable during Phase 2.

---

## Awaiting Cowork approval

If approved, Phase 2 prototype follows:
1. Add env vars + default-off gate.
2. Track `_cumulative_r` on squeeze detector.
3. Compute effective cap at arm-decision site.
4. Add `SQ_ATTEMPTS:` log line.
5. Run VERO/ROLR canary at gate OFF (must be zero-diff).
6. Run BIRD canary at gate ON (must pick up the $11→$20 leg if triggers fire, or at least not make BIRD worse).
7. Commit on `v2-ibkr-migration` with short completion report.

Phase 3 YTD validation deferred until the EPL-enabled YTD dataset exists (directive 3 in parallel).

If disapproved: happy to re-evaluate any of Q1-Q4 with different constraints.

---

*CC (Opus). Mechanism with teeth. D + Y survives both canaries cleanly.*
