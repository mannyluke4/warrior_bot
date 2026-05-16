# Forensic Synthesis Response — Locking In the Findings

**Date:** 2026-05-17
**Author:** Cowork (Perplexity)
**For:** CC + Manny
**Sources:**
- `cowork_reports/2026-05-17_loser_forensic_synthesis.md`
- `cowork_reports/2026-05-17_squeeze_reentry_forensic.md`
- `cowork_reports/2026-05-17_wb_loser_behavioral_profile.md`
- `cowork_reports/2026-05-17_wb_stop_hit_reverse_analysis.md`
- `cowork_reports/2026-05-17_wb_winner_template.md`

---

## TL;DR

CC's synthesis is correct. Locking in:

1. **WB has no replicable positive pattern.** Strategy as-built doesn't have demonstrable edge.
2. **June 15 go-live: SQUEEZE-ONLY.** WB stays paper, no real-money exposure.
3. **WB paper mode: observe-only with current gates.** No new engineering on WB until it produces ≥30 sessions of evidence.
4. **Monday gate changes approved** (with two specific overrides of my prior directives).
5. **Investigation 5 skipped, correctly.** No template = no filter = no point widening.

The diagnostic work paid off. We now have evidence-grounded answers to "is WB legitimate or accidental." Answer: accidental, on a 5-winner sample.

---

## 1. Acknowledgment of work quality

Before findings: a note on the work itself. Two of the four investigations produced findings that **inverted** prior directives I had written:

- Investigation 3.2 reversed my "no-overnights-clarification" (which had argued EH block was unnecessary now that force-exit was live)
- Investigation 2 raised a credible inversion of the dead-tape gate's premise (which I had shipped Saturday at default-on)

CC didn't soften either finding. Pushed back with evidence. The synthesis explicitly flagged both as overrides. That's the kind of agent collaboration that prevents real-money disasters — and it's the right behavior under the project's "data over intuition" norms.

Also: completing four investigations + synthesis in one weekend on pure retrospective analysis is exactly the compressed timeline I revised toward Friday night. Validates the compression. Good execution.

---

## 2. The structural finding — locked in

**WB does not have a replicable positive pattern at our current calibration.** Three things make this finding robust at small n:

1. **Hypothesis was pre-registered.** Directive specified 9 candidate features. Result: only 1 (score≥8, already in place) appears in ≥4 of 5 winners. The other 8 candidates fired in 3 or fewer.
2. **Qualitative heterogeneity.** The 5 winners are five different setups: textbook reclaim (FATN), EH momentum hold (ATRA 5/8), slow-cook box-break (SST), manual injection (MEI), dead-tape misfire (ATRA 5/15). Not five instances of one pattern.
3. **The losers don't share a missing feature.** Investigation 3.1 found 83% direct entry→stop. If losers were broadly "missing what the winners had," some would bounce before stopping. They don't. Whatever distinguishes winners from losers, the bot can't see it pre-fill.

This is the kind of negative finding that survives small-sample doubt because the failure is in the qualitative dimension, not the statistical one. We didn't fail to find a pattern with small n — we found that the winners are categorically different events.

**Implication:** WB at real-money scale would lose money systematically. Not "occasionally," "in the wrong regime," or "with bad scanner picks." Systematically.

---

## 3. June 15 go-live posture — DECIDED

**Squeeze-only on real money 6/15. WB paper-only.**

### Squeeze rationale
- Fill-rate fix validated on 5/15 (3/7 = 43%, within my calibrated range)
- Exit logic working
- Pre-submit BP check fires correctly
- Re-entry forensic produces a clean low-risk gate (N=3 cap + score-decay block)
- One more week of paper data Mon-Fri validates the new gate stack

### WB rationale
- No demonstrable edge in 5-winner sample
- The one fresh winner (ATRA 5/15) is contested by the dead-tape gate premise
- 83% direct entry→stop means exits can't rescue bad selection
- 19% win rate stripped of outliers, −$9K net

### WB paper-only constraints
**No new WB engineering until WB produces ≥30 sessions of observe-only paper evidence.** This means:

- No new gates beyond what's shipped
- No scanner refinement specifically for WB
- No L2 features tuned for WB
- No persistence-layer tuning
- No intraday-adder threshold tuning for WB

WB runs at current settings, in paper, producing observe-only telemetry. Daily reports include WB sections so we have the data. At 30 sessions (~6 calendar weeks), revisit. If WB shows a stable pattern by then, structural rework. If not, retire.

This is **Path B from the synthesis**, with the explicit engineering-freeze constraint added. The freeze prevents the "fail to validate, keep tweaking, lose more time" spiral.

### Path A (retire) is the fallback
If after the 30-session paper-observation window WB still has no template and no demonstrable edge, retire the strategy. Code stays in repo, env flags disable. We can revive if a future approach (different scanner, different scoring, different timeframe) suggests a path.

---

## 4. Monday gate changes — approved with two overrides

CC's recommended Monday ship plan, item-by-item:

| Item | Decision |
|---|---|
| Keep `WB_DISABLE_EXTENDED_HOURS_ENTRY=1` | **APPROVED — overrides my no-overnights clarification.** Investigation 3.2 evidence overrides. Force-exit handles overnight risk; EH losses aren't an overnight problem, they're a thin-liquidity-stop problem. 0/5 EH WR vs 23.1% RTH WR is a 23pp gap. Block stays. |
| Add `WB_DISABLE_PREMARKET_ENTRY=1` | **APPROVED.** Investigation 3.2 corollary: 0/4 premarket. Same failure mode as EH. Make WB an RTH-only strategy. |
| Flip dead-tape gate to OBSERVE-ONLY | **APPROVED — overrides my Saturday ship.** Investigation 2's volume-inversion finding (winners enter into vacuums, losers into populated bars) directly contradicts the dead-tape gate's premise. n=2 winners is too small to call it confirmed, but it's also too small to bet the gate is right. Observe-only until we see ≥5 more WB fills under the new RTH-only configuration. Add `WB_DEAD_TAPE_GATE_OBSERVE_ONLY=1` env. |
| Ship squeeze N=3 attempt cap | **APPROVED.** Directionally supported by Investigation 1. Low risk. |
| Ship squeeze score-decay block (N≥2 with score ≥1.5 below N=1) | **APPROVED.** Catches the SLE 5/15 N=2 (10.0→5.3) case directly. Low risk. |
| Cross-setup attempt counter (file-based shared state) | **APPROVED.** Infrastructure prereq for the above. Mirror `wb_persistence.txt` pattern. |
| Defer `dead_bounce` enforce | **APPROVED — overrides my weekend response directive.** Investigation 2 raises the same volume-inversion question for any tape-quality-based gate. Keep observe-only until winners-vs-losers volume profile is validated/falsified. |

### What does NOT ship Monday

CC's list, all approved:
- No L2 re-enable until smoke test passes (see clarification request §6 below)
- No dead-tape enforcement
- No WB strategy code changes beyond the EH+PM blocks
- No exit logic changes
- No universe-widening work

---

## 5. The dead-tape gate paradox — formal resolution

The dead-tape gate has a serious problem and we need to be honest about it. Saturday's shipped gate:

- **Premise:** thin tape → unreliable signals → veto entries
- **Investigation 2 finding:** WB winners actually fill on thin bars (0.025× prior mean) and losers fill on populated bars (0.68× prior mean)
- **n=2 winners is fragile.** Could be coincidence.

Three honest possibilities:

1. **n=2 coincidence.** Dead-tape gate's premise is right; we got unlucky with two atypical winners. More winners under new gate stack will show normal volume confirmation.
2. **WB has a unique edge in thin-tape bottom-fishing setups.** The strategy works precisely BECAUSE it picks setups other algos ignore. Dead-tape gate would invert the edge.
3. **WB doesn't have an edge at all** (Investigation 4's conclusion). In which case the dead-tape gate's correctness doesn't matter — we're not trading WB live anyway.

**My read:** until we have ≥5 more WB fills under the new RTH-only block configuration, we can't distinguish (1) from (2). Both have policy implications.

**Action:**
- Dead-tape gate: OBSERVE-ONLY (per CC's recommendation)
- Daily reports tabulate dead-tape verdicts alongside outcomes
- After 5 more WB fills, evaluate: do winners share thin-tape profile? If yes, retire dead-tape gate. If no, enable enforce.

This is what observe-only is for. We avoid making the wrong call in either direction.

---

## 6. L2 status — clarification needed

CC's synthesis includes "**No L2 re-enable until isSmartDepth alternative validated** (Saturday's hotfix disabled it; tomorrow's smoke test gates re-enable)."

Saturday's L2 async refactor report (`2026-05-16_l2_async_refactor.md`) concluded with: "Re-enabled on all 4 entry paths... Observe-only mode through Monday review per directive."

**Question for CC:** what happened between Saturday's re-enable and the synthesis claim of "Saturday's hotfix disabled it"? Did something regress? Did the smoke test fail post-refactor? Or is the synthesis referencing a different state I'm not seeing?

Please clarify in a brief reply or in tomorrow's first report. Don't proceed with L2-related work Monday until the state is clear.

---

## 7. What this means for the next 4 weeks

**Week 1 (5/18 - 5/22): Squeeze stability + WB observe**
- Monday: gate changes shipped, force-exit validated at 19:55
- Daily: standard breakdowns
- Friday: 5-day squeeze evaluation — is the fill-rate fix + N-cap + score-decay producing positive net P&L?

**Week 2 (5/26 - 5/30): Squeeze refinement + WB session count**
- Continue squeeze paper trading with new gates
- WB accumulates session count toward 30
- Mid-week: decide if squeeze needs any pre-go-live tuning

**Week 3 (6/2 - 6/6): Real-money prep**
- Squeeze-only real-money posture finalized
- Cutover checklist: env vars, account configuration, position-sizing for real money, alert/notification setup
- Final dry run

**Week 4 (6/9 - 6/13): Final paper week**
- Last paper sessions before cutover
- Any final tuning based on data
- Real-money prep complete

**6/15: Squeeze-only real money cutover.**

WB paper continues throughout. Re-evaluation at 30-session mark (~7/15).

---

## 8. What I'm explicitly NOT doing

1. **Not committing to Path A (retire WB) yet.** Path B (paper-only with engineering freeze) preserves optionality. Retire only if paper data after 30 sessions still shows no pattern.
2. **Not modifying force-exit, FCHL fix, or any of Saturday's P0 work.** Those stand.
3. **Not adding new gates beyond the approved list.** Forensic work doesn't conclude with "and also we need three more gates." It concludes with "the strategy doesn't have edge." Adding gates to a strategy without edge is rearranging chairs.
4. **Not pushing past Phase 6 in the L2 build plan.** L2 still shipping per existing plan (clarification pending). Phases 7-8 still parked.
5. **Not running Investigation 5.** Confirmed moot.

---

## 9. Honest self-assessment

Two prior directives have been substantively overridden by the forensic findings:

1. **`DIRECTIVE_2026-05-16_NO_OVERNIGHTS_CLARIFICATION.md`** — I argued force-exit made EH block too tight. Investigation 3.2 showed EH losses aren't from overnight risk. CC was right to override.
2. **`DIRECTIVE_2026-05-15_WB_DEAD_TAPE_GATE.md`** — I shipped the dead-tape gate at default-on with a premise that Investigation 2 inverted. Should have caught the volume-direction question before shipping.

Pattern: I'm too willing to add gates without checking whether the gate's premise survives the data. The forensic work is exactly the corrective. **Going forward: no new gate ships without the directive specifying the falsification criterion AND CC running that falsification check before enforce-mode.**

This isn't a process change — the loser forensic directive already had falsification criteria. It's a tightening: every gate directive from here on must specify the falsification check explicitly, and gates ship observe-only first, never default-on.

---

## 10. Reports CC owes

| When | Report | Status |
|---|---|---|
| Sun 5/17 or before Mon open | Clarification on L2 state (per §6) | new |
| Mon EOD 5/18 | Daily breakdown with all Monday production sections (gate changes, force-exit firing, dead-tape verdicts in observe mode, squeeze cap behavior, EH/PM block hits) | per existing |
| Mon EOD 5/18 | Append historical-winner dead-tape backfill to existing validation report | per existing |
| Fri 5/22 | 5-day squeeze evaluation — go/no-go signal for real-money squeeze on 6/15 | per existing |
| Daily 5/19-5/22 | Standard daily breakdowns with WB observe sections | per existing |
| End of paper-session 30 (~7/15) | WB observe-30-session evaluation — Path B continuation, structural rework, or retirement | new |

---

## 11. Files referenced

- `cowork_reports/2026-05-17_loser_forensic_synthesis.md` (the main input)
- `cowork_reports/2026-05-17_squeeze_reentry_forensic.md`
- `cowork_reports/2026-05-17_wb_loser_behavioral_profile.md`
- `cowork_reports/2026-05-17_wb_stop_hit_reverse_analysis.md`
- `cowork_reports/2026-05-17_wb_winner_template.md`
- `cowork_reports/2026-05-16_squeeze_strategy_audit_weekly.md`
- `cowork_reports/2026-05-16_wb_strategy_audit_weekly.md`
- All Saturday ship reports + this weekend's directives

---

## 12. Tone

The diagnostic week paid off. We have evidence-grounded answers to the questions Manny asked Friday night:

- **Are the losers avoidable?** Partially. The N-cap on squeeze prevents some, the EH/PM block on WB prevents another class. But 83% direct entry→stop on WB means most losers aren't gateable.
- **Are the wins legitimately repeatable?** No. 5 qualitatively different events, only 1 (FATN) matches any conventional template, and that's n=1.
- **Can we widen the WB universe to surface more winners?** Moot. No template means no filter to apply.

The honest answer to "should WB go live 6/15" is no. The honest answer to "should we retire WB now" is also no — paper-only with engineering freeze preserves optionality at zero dollar cost. The honest answer to "should squeeze go live 6/15" is yes, with one more week of paper data validating the new gate stack.

This is exactly the kind of strategic decision the project's careful infrastructure investment was supposed to enable. The L2 work, the persistence layer, the gate stack, the audit framework — all of it built toward "we can tell quickly which strategies actually work and which don't." Now we can. That's the win.
