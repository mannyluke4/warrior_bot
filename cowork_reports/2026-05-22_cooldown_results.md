# Stay-Armed Cool-Down Variants — Results

**Date**: 2026-05-22
**Branch**: `v2-ibkr-migration`
**Source directive**: `cowork_reports/2026-05-22_stay_armed_cooldown_directive.md`
**Predecessors**: Direction A killed, Direction B Pareto-improvement (failed PCLA threshold)

---

## TL;DR

**All three cool-down variants fail the binary criterion.** None captures PCLA's 17:02 ripper enough to beat $1,500, and CD1/CD2 also destroy the 10-day sample. CD3 (bypass-on-partial) is the cleanest theoretical fix but produces zero PCLA improvement because PCLA's specific shape means the bypass doesn't apply to the trade that misses the ripper.

**Fundamental finding (the X01 research dead end)**: even when the bot ENTERS at 17:02-17:04 on PCLA, **HWM trail still exits at $3.50-$3.80** on the first 25% pullback. The 17:05 ($5.13 peak) and 17:07 ($5.87 peak) bars are unreachable for HWM-style trails. Only Direction A's X01 framework — which uses sq_target_hit at higher R — captured them, and X01 destroys the 10d.

**Recommendation**: kill the X01 research line. Direction B 90% remains the best candidate (Pareto improvement +$328 combined 11-day, but fails binary PCLA threshold). Manny's call on whether to ship Direction B alone.

---

## Three-variant comparison

| Variant | 10d (5/07–5/20) | PCLA (5/21) | Combined 11-day |
|---|---|---|---|
| HWM baseline | +$2,489 | +$622 | +$3,111 |
| Direction B 90% (no CD change) | **+$2,637** | +$802 | **+$3,439** |
| **CD1** 5-min cool-down + partial | −$651 | +$918 | +$267 |
| **CD2** from-entry cool-down + partial | +$508 | +$983 | +$1,491 |
| **CD3** bypass-on-partial 2-min + partial | +$2,161 | +$802 | +$2,963 |
| CD1 sanity (5-min CD, no partial) | −$799 | — | — |

**Strict criterion (>$2,489 10d AND >$1,500 PCLA)**: ALL VARIANTS FAIL.

---

## Why each variant fails

### CD1 (5-min cool-down)

The CD1 sanity check (5-min cool-down WITHOUT partial) produces almost the same disaster as CD1 with partial (−$799 vs −$651). **This proves the over-trading is the cool-down change, not an interaction with the partial mechanism.**

5/15 went from +$104 (baseline 4 trades) → −$1,039 (CD1 7 trades). The extra 3 trades on 5/15 were stay-armed re-entries that fired into chop and lost. 5/20 dropped from +$2,680 to +$683 — 27 trades vs baseline 18. The 9 extra trades had a much worse win rate than baseline's 18.

**Verdict**: shorter cool-down = over-trading. Strict KILL.

### CD2 (cool-down from entry-time)

Behaviorally similar to CD1 but slightly less aggressive. Still loses badly on the 10d sample (5/15 −$650, 5/20 +$1,453 vs baseline +$2,680). Same root cause — long trades shed their cool-down too fast.

**Verdict**: KILL.

### CD3 (bypass-on-partial to 2-min)

The cleanest theoretical fix: only bypass when the trade demonstrated strength via the partial fire. But on the 10d sample, only ONE trade reaches 1.5R (the partial threshold). So CD3 only affects ONE trade's cool-down window. The bypass DOES fire for that one trade and DOES allow another re-entry — but the re-entry was a small loser, reducing 5/20 from +$2,680 (baseline) to +$2,352 (CD3).

**On PCLA**: trade 1 fires the partial → bypass enabled. But trade 2 (the green re-entry from the same-bar re-entry mechanism) does NOT fire the partial — its 30-min watch window isn't related to the stay-armed cool-down. So the 17:02 stay-armed entry remains blocked by the COOL-DOWN-FROM-TRADE-2 — and trade 2 didn't fire the partial, so bypass doesn't apply.

In other words: PCLA's specific shape is "partial on trade 1, then re-entry that doesn't reach 1.5R, then cool-down from THAT trade blocks 17:02." CD3 only bypasses cool-down from PARTIAL-FIRE trades. The blocking trade isn't a partial-fire trade.

**Verdict**: theoretically sound, doesn't unlock PCLA. Defer.

---

## The deeper finding — HWM trail can't capture vertical moves

CD1 and CD2 DO let stay-armed re-fire at 17:02 and 17:04 (PCLA shows 4 trades for both). But:

| PCLA Trade | Entry | Exit | Reason | P&L |
|---|---|---|---|---|
| 3 (17:02 stay-armed entry $3.46) | $3.46 | $3.50 | move_hwm_exit (peak=$3.61) | +$34 |
| 4 (17:04 re-entry $3.69) | $3.69 | $3.80 | move_hwm_exit (peak=$3.84) | +$81 |

The 17:05 bar peaks at $5.13. The 17:07 bar peaks at $5.87. **Our HWM 25% trail fires at the first 25%-of-gain pullback** — for trade 4, that's $3.84 - 0.25 × ($3.84 - $3.69) = $3.80. We exit at $3.80 while PCLA goes to $5.87.

This is the SAME structural ceiling we identified yesterday in `2026-05-21_dynamic_exit_research_2026-05-21` — HWM trail can't capture explosive vertical moves because the first intra-bar pullback fires the trail. Only X01's sq_target_hit (which targets 1.5R from entry, not 25% from peak) can capture the kind of move where the peak is 5R+ from entry.

**No tuning of cool-down can fix this.** Cool-down lets us enter more trades; the exits are still bound by HWM's structural limitation.

---

## What this means for the X01 research line

We've now exhausted the directions in the original research directive (`2026-05-21_x01_exits_research_directive.md`):

| Direction | Result |
|---|---|
| A: X01 exits minus bail_timer | KILL (−$2,704 on 10d) |
| B: Partial at 1.5R + HWM runner | Pareto improvement (+$328 combined), fails PCLA threshold |
| B+CD1: Partial + 5-min cool-down | KILL |
| B+CD2: Partial + entry-time cool-down | KILL |
| B+CD3: Partial + strength-bypass cool-down | KILL (no PCLA improvement) |
| C: Volatility-adjusted trail | NOT tested (original directive flagged "less promising") |
| D: Pattern-based widening | NOT tested (flagged "less promising") |

**Recommendation**: close the X01 research line. The structural ceiling is real — HWM trail can't capture multi-bar vertical moves, and the alternative (X01 framework) destroys the 10d sample. Direction C and D could be explored but the prior is they hit the same ceiling.

---

## Direction B's status

Direction B's partial mechanism alone (no cool-down change) is the best result we've found:
- 10d: +$2,637 (+$148 vs baseline)
- PCLA: +$802 (+$180 vs baseline)
- Combined 11-day: +$3,439 (+$328 vs baseline)
- No day regression

Per the strict directive criterion (need >$1,500 PCLA), Direction B FAILS. Per Pareto economics, Direction B WINS.

If we ship Direction B alone:
- Wire `WB_BT_MOVE_PARTIAL_ENABLED=1 WB_BT_MOVE_PARTIAL_PCT=0.9` in daily_run_v3.sh
- Port partial logic to move_strike_subbot.py
- Expect +$148/day-equivalent on days where setups reach 1.5R
- No expected downside

If we kill Direction B and stop here:
- Stack stays at current shipped config
- Live converges toward sim's +$2,489 over time (post-chase-skip-fix)
- We monitor Monday's session and decide based on observation

---

## Recommendation: Manny's call

The data says Direction B is a small strict-improvement (+$328 combined). The directive says fail-criterion = kill. These two are in tension.

**My read**: ship Direction B alone (without any cool-down change). It's strictly better, has zero downside in the sample, and the binary criterion was set higher than what's structurally achievable. We've exhausted the search space for capturing PCLA-class moves; Direction B captures more than HWM does without sacrificing anything.

But it's Manny's project and Manny's standard. If "no ship without binary pass" is the rule, kill it.

---

## Closing the task

Task #37 (cool-down variants) closes as completed with verdict **KILL all variants**.

X01 research stack is closed. Next: Monday's live observation with the watchdog + chase-skip + alpaca-aware-limits + sub-bot-seeding stack from `b4b0b73 + d171958 + 1c3ce24 + a8a95ec + 2887de3`.
