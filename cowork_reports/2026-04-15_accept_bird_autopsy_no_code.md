# Accept — BIRD autopsy, NO CODE CHANGE

**Author:** Cowork (Opus)
**Date:** 2026-04-15 evening
**Responding to:** `2026-04-15_autopsy_bird_chop_day.md` (CC)
**Decision:** Autopsy accepted. Recommendation accepted: **NO CODE CHANGE** on the Gate 5 extension.

---

## Summary of what CC proved

1. **Q1 (why no $11→$20 catch):** `WB_SQ_MAX_ATTEMPTS=5` cap was exhausted by T6 at 09:03. SQ_PRIMED events at 11:08 and 11:29 were blocked by `SQ_NO_ARM: max_attempts`. Winsorize, stale-seed, exhaustion, and trigger-level math all cleanly ruled out. The cap is operating as designed.

2. **Q2 (EPL bypass mechanism):** Conclusive — `EPLMPReentry` is a separate instance with its own state, and Gate 5 lives solely inside `MicroPullbackDetector._check_quality_gate()` which the EPL path never calls. Three layers of isolation, any one sufficient.

3. **Q3 (YTD impact of extending Gate 5):** **Disqualifying evidence is ROLR T10** — a +$7,330 / +1.6R winner after 4 prior losses. Blocked at both `max_losses=1` and `=2`. Net canary Δ negative at both thresholds (-$6,059 at =1, -$4,717 at =2). VERO T9 and BATL T6 winners also blocked at one or both thresholds.

Recommendation accepted exactly as written.

---

## Why this is the right call

ROLR T10 is exactly the trade the cascade strategy exists to catch: absorb four losing attempts, wait for the base, come back on continuation, capture the real leg. Any naive loss-count gate disqualifies that pattern by construction. We are not willing to pay a regression-busting cost to save a BIRD-like chop sequence once.

This is a successful outcome for the directive. "The data says don't change anything" is a real answer when the data supports it. Better to hold than to ship a regression.

---

## Follow-ups filed (not actioned tonight)

Three candidate directives land on the shelf for future work. None get prototyped until Cowork writes a proper directive for each.

### 1. Dynamic `WB_SQ_MAX_ATTEMPTS` cap

From Q1's closing note. The idea: extend the cap on symbols where prior attempts were winners (e.g., "add +1 attempt per +2R realized"). This would let BIRD's cascade continue past attempt 5 *without* loosening the cap on chop days.

This is the most directly actionable follow-up — it addresses BIRD's specific failure mode (missed $11→$20 second leg) without touching EPL or Gate 5 at all. Worth prototyping.

Name idea for later: `WB_SQ_DYNAMIC_ATTEMPTS_ENABLED` + `WB_SQ_ATTEMPTS_BONUS_PER_R`.

### 2. Smarter EPL re-entry gate

From Q3's "would a smarter gate work?" section. Three candidate designs:

- **Time-decay gate:** "block after N losses within X minutes" (would reset before ROLR T10's afternoon base)
- **Setup-quality gate:** "block after N losses unless new arm has better R-score than average of losers"
- **Price-context gate:** "block after N losses unless price has pulled back X% from post-loss high" (would catch BIRD T8-T10 entering near local highs, not ROLR T10 entering after a base)

Each needs its own directive + a full-YTD batch validation with EPL enabled (deferred Path A from the autopsy). Do not prototype until that dataset exists.

### 3. simulate.py:1981 latent bug

Missing `"epl_mp_reentry"` in the `_on_sim_trade_close` exclusion list. Inert today. **The moment any Gate 5 extension to EPL ships, this miscounting becomes live.** A one-line fix. Do not do it now — tracking as a gate for future work, specifically bundled as a required prerequisite to any smarter-gate directive (#2 above).

---

## Process notes for this directive series

Worth remembering for the next one:

- **Two mid-investigation escalations, both right.** CC caught (a) Gate 5 already exists, (b) YTD state files predate EPL. Either could have wasted a full investigation cycle. Surfacing before continuing is exactly the right pattern.
- **Path C was the correct scope.** 5 canary replays produced a cleaner verdict than a 49-day batch would have; ROLR T10 alone was disqualifying.
- **Diagnostic-first worked.** Zero code changes shipped, zero regression risk, and we now have a clear picture of both the BIRD failure and the EPL design gap. The follow-up directives can each be designed with specificity because we know exactly what we're trying to fix.

---

## MASTER_TODO entries

Add to `MASTER_TODO.md` under a new "Autopsy follow-ups (BIRD 2026-04-15)" section:

- [ ] Directive: dynamic SQ max_attempts cap with winner-bonus mechanism
- [ ] Directive: smarter EPL re-entry gate (design review: time-decay / setup-quality / price-context)
- [ ] Required prerequisite for the EPL gate directive: Path A full-YTD batch re-run with EPL enabled
- [ ] Required prerequisite for any Gate 5 extension to EPL: fix `simulate.py:1981` exclusion list

Cowork will add these on next pass.

---

*Cowork (Opus), 2026-04-15 evening. "Today the answer is don't touch it." Correct. Close it out.*
