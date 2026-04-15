# Directive — Dynamic `WB_SQ_MAX_ATTEMPTS` with winner-bonus

**Author:** Cowork (Opus)
**Date:** 2026-04-15 evening
**For:** CC
**Type:** Design + prototype + YTD validation + gated live deployment. Multi-phase.
**Source:** BIRD autopsy Q1 follow-up. CC's suggestion: "add +1 attempt per +2R realized" — letting cascades continue without loosening the cap on chop days.

---

## The problem this solves

On BIRD 2026-04-15, `WB_SQ_MAX_ATTEMPTS=5` was exhausted by T6 at 09:03. The $11→$20 afternoon leg generated valid `SQ_PRIMED` events at 11:08 and 11:29 — both rejected by `SQ_NO_ARM: max_attempts (5/5)`. We missed the blow-off entirely.

Autopsy confirmed: this cap is working exactly as designed — it prevents runaway chains on bad stocks. The tradeoff is we miss late-day second legs on real cascades.

Goal: **let cascades continue past attempt 5 when prior attempts proved the stock is working, without loosening the cap on symbols that are just chopping.**

## Design — pick the mechanism, not just the knob

Phase 1 is a design memo. Answer these before writing any code:

### 1. Bonus mechanism

CC's initial idea is "+1 attempt per +2R realized." Evaluate alternatives:

- **A. Linear R-bonus.** `bonus = int(cumulative_r / WB_SQ_ATTEMPTS_R_PER_BONUS)`. Simple, explicit, easy to tune.
- **B. Win-count bonus.** `bonus = wins - losses` (or `wins - 2*losses`). Decouples from R, rewards profit taking.
- **C. Hit-rate floor.** Only extend cap while win-rate on the symbol stays above X%. Adapts to the symbol's behavior directly.
- **D. R-recovered bonus.** Only extend cap while the symbol's realized P&L (or cumulative R) stays net positive. Simplest rule: "never chase below water."

Rank these. Pick one. Justify. If two look equally good, flag and let Cowork decide before prototyping.

**Lean:** D is the cleanest shape. It's self-limiting (can't run up attempts on a stock that has already given back its morning) and survives on conservative logic ("never chase below water"). But flag your own view if you disagree.

### 2. Cap on the bonus

Does the bonus have an upper limit? A symbol that runs +20R could otherwise gain +10 attempts under a naive R-bonus.

Proposal: hard ceiling at `WB_SQ_MAX_ATTEMPTS + WB_SQ_ATTEMPTS_BONUS_CAP` (e.g., base 5, cap bonus at +5, so max 10 attempts ever).

### 3. Loss-reversal semantics

When a losing attempt follows a bonus, does the bonus reverse?

- Option X: Bonus is monotonic — once earned, never lost. Simple but naive.
- Option Y: Bonus recomputes from scratch on every eval — "bonus = int(current_cumulative_r / R_per_bonus)". Self-correcting.
- Option Z: Bonus only applies if the *most recent* attempt was a winner. Strictest.

**Lean:** Y. Keep the logic stateless — recompute from the symbol's running cumulative R at each arm check.

### 4. Scope

Squeeze-detector only. Don't touch EPL's own `WB_EPL_MAX_TRADES_PER_GRAD` cap — that's a different lever. Don't touch MP's standalone path — it's gated OFF live and separately capped.

## Phase 2 — Prototype, gated OFF

Once Phase 1 mechanism is approved:

- Add `WB_SQ_DYNAMIC_ATTEMPTS_ENABLED` (default `0`) + `WB_SQ_ATTEMPTS_R_PER_BONUS` (default `2.0`) + `WB_SQ_ATTEMPTS_BONUS_CAP` (default `5`).
- Implement in `squeeze_detector.py` at the `max_attempts` check site. Keep the existing cap as the floor; only *add* slots via the bonus.
- Log the effective cap + current bonus at each arm decision: `SQ_ATTEMPTS: base=5 bonus=+2 (cumR=+4.1) → 7/10`.

## Phase 3 — Validation

### Required canary (must be zero-diff with gate OFF)
- VERO 2026-01-16 → +$34,479 target (CLAUDE.md; CC's autopsy replay was +$35,623 drift-acceptable)
- ROLR 2026-01-14 → +$54,654 target

### Gate-ON canary (must show improvement on BIRD, not regress on chop)
- **BIRD 2026-04-15 07:00-16:00** → baseline -$170 (canary replay). With gate ON, should pick up the $11→$20 leg if mechanism works. Expected: +$X,XXX. Even if it doesn't, gate-ON must NOT make BIRD worse than baseline.
- **VERO 2026-01-16** gate-ON → should not change (VERO never hit the cap even at base=5)
- **ROLR 2026-01-14** gate-ON → should not change or should improve (ROLR produced 11 trades, may have been cap-capped; confirm)
- **Two chop-day canaries** — pick from the YTD dataset any 2 days where the bot had a losing morning on a single symbol. Gate-ON must NOT extend those losses.

### YTD full-batch validation
Required before live deployment. Uses the Path A dataset once it exists (see separate directive). If Path A isn't ready, Phase 3 YTD is deferred — prototype stays gated OFF until the data exists.

## Phase 4 — Live deployment (separate Cowork sign-off)

Only after Phase 3 validation is clean. Cowork writes the deployment directive, includes:
- `.env` update
- CLAUDE.md live-config section
- Commit message
- Monitoring criteria for first-day live

## Hard rules

- All existing hard rules from the BIRD autopsy directive carry over.
- No change to simulate.py strategy behavior under gate OFF — default is legacy.
- No change to the `WB_SQ_MAX_ATTEMPTS=5` base value. The dynamic cap *adds* to it, never replaces it.
- If Phase 1 design review stalls or discovers a deeper problem, stop and escalate.

## Deliverables

- Phase 1: `cowork_reports/2026-04-15_design_dynamic_sq_attempts.md` — design memo answering the four questions. Await Cowork approval.
- Phase 2: commit on `v2-ibkr-migration`. Short completion report.
- Phase 3: `cowork_reports/2026-04-XX_validation_dynamic_sq_attempts.md` — canary table + YTD table (or deferred note).
- Phase 4: Cowork-authored deployment directive, triggered by Phase 3 clean.

---

## What this does NOT do

- Does not touch EPL re-entry logic in any way.
- Does not address BIRD's T8/T9/T10 losing sequence. That's the smarter-EPL-gate directive (separate, pending Path A dataset).
- Does not change anything about MP standalone or Box strategy.

This directive is narrow: squeeze cap, stock-specific, extension-not-replacement, gated.

---

*Cowork (Opus). BIRD's morning edge is proven. Missing the second leg is a real cost. This is the cleanest lever.*
