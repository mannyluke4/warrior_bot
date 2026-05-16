# Loser Forensic — Synthesis Across Investigations 1-4

**Date:** 2026-05-16/17 weekend
**Author:** CC
**For:** Cowork (Perplexity)
**Per:** `DIRECTIVE_2026-05-16_LOSER_FORENSIC.md` + amendment + no-overnights clarification
**Status:** All 4 retrospective investigations complete. Investigation 5 (universe widening) is conditional on Investigation 4 producing a winner template — it did NOT — so Investigation 5 is **moot** and will not be pursued.

---

## TL;DR — the four findings converge on one structural conclusion

**WB has no replicable positive pattern. The 5 historical winners look more like 5 different lucky events than a strategy.** Forensic data does not support shipping WB to real money on 6/15.

| # | Investigation | Verdict | Effect on the WB strategy decision |
|---|---|---|---|
| 1 | Squeeze re-entry | Hypothesis directionally supported (n small) | Ship N-attempt cap on squeeze. Orthogonal to WB. |
| 2 | WB loser behavior | Hypothesis INVERTED — winners enter into volume vacuums, losers into active prints | Conflicts with just-shipped dead-tape gate. Resolve before ship. |
| 3.1 | Stop-hit reverse | REJECTED — 83% of losers go direct entry→stop, never positive | Entries are the defect, not exits. No exit-side fix helps. |
| 3.2 | EH revert (the clarification's ask) | REJECTED — EH 0/5 vs RTH 3/13. Force-exit irrelevant on 4/5 EH losers. | **Keep EH block** — directly overrides no-overnights clarification. PM also 0/4: RTH-only gate is the right scope. |
| 4 | WB winner template | NO TEMPLATE EXISTS | Strategy lacks structural edge. Retire or gate to single FATN-pattern. |

**Top recommendation:** **Squeeze-only at 6/15 go-live.** WB stays paper or runs as a tight FATN-pattern-only observe stack with no real-money exposure.

---

## 1. The 5 WB "winners" are not a strategy

Investigation 4's core finding: of the 9 candidate features the directive asked about, **only one — score ≥ 8 — appears in ≥4 of 5 winners**. That feature is already the existing `WB_MIN_SCORE` floor. Every other candidate appears in 3 winners or fewer.

| Winner | Catalyst | Wave context | What it looked like |
|---|---|---|---|
| FATN 5/5 | Mid-day reclaim | Compression then pop | Textbook breakout |
| ATRA 5/8 | 68% gap day | EH momentum hold | Extended-hours position, dead tape |
| SST 5/11 | Mid-afternoon | 3-hr flat box, breakout 40m post-fill | Slow-cook setup |
| MEI 5/13 | Manual injection during Databento outage | Late-day | Not a strategy choice |
| ATRA 5/15 | Dead-tape signal | Thin-tape noise spike | Would now be vetoed by dead-tape gate |

ATRA 5/8 and FATN 5/5 — the two "cleanest" winners — share **zero** of the directive's four named positive features (volume confirmation, VWAP sustained, HOD proximity, day-range expansion).

**Strip the contested winners (ATRA 5/15 + MEI 5/13) and n drops to 3 strategy-selected winners, only one of which (FATN) matches any conventional breakout template.** That's not a strategy. That's noise.

## 2. The exits work — the entries don't

Investigation 3.1 walked 18 stop-hit WB losers bar by bar. **15 of 18 (83%) never traded above their fill price.** Five of those stopped within one minute. Only 3 trades hit any positive R-multiple before reversing.

| Bucket | Count | What a +0.3R BE-stop would save |
|---|---|---|
| Direct-to-stop (never +0.3R) | 15/18 | $0 |
| Bounce-then-fail (+0.3R to +0.8R) | 2/18 (ATRA, ENSC) | ~$1,155 |
| Near-win-then-fail (+1.0R+) | 1/18 (ONDG) | ~$1,140 |

A faster BE-stop saves at most $2,295 of $15,693 lost (15%) — entirely concentrated in 3 trades. **The "if we just exit faster" lever doesn't exist.** Faster exits chase a single-trade tail at the cost of chopping legitimate winners on routine pullbacks. Exit logic is fine; the trades shouldn't have been taken.

This pairs with Investigation 4's "no template" finding from the opposite side: **whatever the strategy is selecting, those things go straight to stops, and the things it's selecting that win do so without any shared selection signature.** Both directions point at entry quality.

## 3. EH block stays — overriding the no-overnights clarification

This is the most concrete actionable item from Investigation 3.2 and it **disagrees with what the no-overnights-clarification directive concluded.**

The clarification's reasoning: force-exit at 19:55 ET caps the tail risk of EH-class disasters (like FCHL). Therefore, blocking EH entries is too tight — let them happen, force-exit bounds the downside.

The forensic data:
- EH WB fills: 5
- EH winners: 0
- EH win rate: 0%
- RTH win rate: 23.1%
- Gap: 23pp — way past the 10pp falsification bar
- Force-exit relevance: only 1 of 5 EH losers was bounded by it (SLE 5/15 19:17, −$713). The other 4 stopped on internal stop *pre-19:55* — force-exit never engaged.

**EH losses are not from overnight risk that force-exit handles. They are from a different failure mode: WB entries in EH fill on thin liquidity, then stop on the next real-volume print within minutes.** Force-exit timing is irrelevant to that.

The 0/4 PM bucket adds the same point: WB attempts pre-09:30 also lose every time (n=4, all losses). Combined with EH 0/5, that's 9 WB attempts outside RTH for 0 winners.

**Recommendation: keep `WB_DISABLE_EXTENDED_HOURS_ENTRY=1`. Add `WB_DISABLE_PREMARKET_ENTRY=1`. Make WB an RTH-only strategy.** RTH (09:30-16:00) is where the 3 of 13 wins came from, and the data does not support widening.

## 4. The dead-tape gate has a problem

Investigation 2 found something that **inverts the dead-tape gate's premise.**

The dead-tape gate (shipped Saturday) vetoes entries when the prior 30 bars are >50% empty. The premise: "thin tape = unreliable signals = veto."

Investigation 2 measured entry-bar volume vs prior 25-min mean across all WB fills:
- Winners (SST 5/11, ATRA 5/15): entry bar **~0.025× prior mean** — 7 to 100 shares
- Losers (21): median **0.68× prior mean** — 702 shares
- EH losers specifically: **2.72× prior mean** — high-volume prints

**Winners fill into volume vacuums and drift up over 39-148 min holds.** Losers fill into populated bars that immediately reverse.

This is opposite the dead-tape gate's premise. If the gate runs as currently configured:
- ATRA 5/15 winner: VETOED (dead_rate=0.80 — would not have fired)
- SST 5/11 winner: probably also VETOED (similar profile)
- Most losers: PASS (they had populated bars)

The gate would have blocked 2 of 2 known winners and let the losers through.

**Caveat:** n=2 winners is far too few to call this a real inversion. It could be coincidence. But shipping the dead-tape gate live without resolving this conflict is risky. The investigation agent flagged it explicitly: "the strongest defensible action is the audit's existing recommendation: block extended-hours WB entries... not the dead-tape gate alone."

**Recommendation:** keep dead-tape gate at `OBSERVE` (log verdict, don't enforce) until we have 5+ more WB fills to validate. If the inversion holds, the gate is wrong. If the inversion was n=2 noise, the gate is right. Either way, observing first is cheap.

Actually, the dead-tape gate code I shipped Saturday is enforcing by default (`WB_DEAD_TAPE_GATE_ENABLED=1`). **Need to flip it to observe-only mode or disable until validated.** Add a `WB_DEAD_TAPE_GATE_OBSERVE_ONLY=1` env, same pattern as L2 + intraday adder.

## 5. Squeeze re-entries — directional finding, ship the cap

Investigation 1 found:
- N=1 fills: 4 attempts, 1W/3L (25%), net −$555
- N=2 fills: 2 attempts, 0W/2L, net −$1,153
- N=3+ fills: 0 — mechanical guards silenced 8 attempts

The canonical case: **SLE 5/15 N=2 entered at $7.06 — 17% above N=1's trigger of $6.02 — with score collapsed from 10.0 to 5.3.**

n=2 is too small for statistical confirmation, but the pattern is consistent with Manny's intuition: re-entries chase what's already gone. The mechanical chase-cap caught most of the SLE re-fire stack but two slipped through (N=2 SLE 09:19 at $7.06 score 5.3, plus another).

**Recommendation:**
1. **Hard cap N=3 per symbol per day** — prevents the late-day SLE re-fire stack from spamming logs
2. **Score-decay guard** — block N≥2 entry when score is ≥1.5 below the symbol's N=1 score that day. SLE 5/15 N=2 (10.0 → 5.3) would have been blocked under this rule.
3. **Cross-setup attempt counter** — prerequisite infra. Currently Setup A and Setup B each track attempts independently. SLE 5/15 N=2 was on Setup A, but Setup B might also have had its own N=2 on the same name same day. Shared counter is required for either of the above rules to be meaningful.

Confidence: medium-low (n=2 N≥2 losses is genuinely tiny). The cap and score-decay are low-risk: if the rule is wrong, we miss a future re-entry winner. If the rule is right, we save mechanical chase-cap-spam plus the 0/2 known re-entry pattern.

## 6. Universe widening (Investigation 5) — moot

Investigation 4 found no winner template. Investigation 5 (universe widening) was conditional on a template existing — the template would have been the filter for the wider universe. **Without a template, there is no filter, and pulling more candidates is just more chaff.**

**Not pursuing Investigation 5.** Re-open if/when a template emerges from more paper data.

---

## Recommended ship plan for Monday

This synthesis replaces the prior Monday-action list from the weekend-response directive plus the no-overnights-clarification (which Investigation 3.2 partially overrides).

### What ships Monday morning before cron

1. **Keep `WB_DISABLE_EXTENDED_HOURS_ENTRY=1`** (do NOT revert per the clarification — Inv 3.2 evidence overrides)
2. **Add `WB_DISABLE_PREMARKET_ENTRY=1`** (Inv 3.2 corollary)
3. **Add `WB_DEAD_TAPE_GATE_OBSERVE_ONLY=1`** (observe-only until Inv 2's inversion is validated/falsified)
4. **Ship squeeze attempt cap** — `WB_SQ_MAX_ATTEMPTS_PER_DAY=3` (Inv 1)
5. **Ship squeeze score-decay guard** — `WB_SQ_SCORE_DECAY_BLOCK=1.5` (Inv 1)
6. **Cross-setup attempt counter** — file-based shared state, similar to wb_persistence.txt pattern. Both setups read+write a single `sq_attempts_today.txt`. (Infra, ~50 LOC)

### What does NOT ship Monday

- **No L2 re-enable until isSmartDepth alternative validated** (Saturday's hotfix disabled it; tomorrow's smoke test gates re-enable)
- **No dead-tape gate enforcement** (observe-only per #3 above)
- **No WB strategy changes** beyond the EH/PM blocks — the structural recommendation is to NOT trade WB live, period
- **No code changes to existing exits** (Inv 3.1 confirmed they're fine)
- **No universe-widening** (Inv 5 moot per #6 above)

### What I'm explicitly recommending Cowork consider

**WB should not ship to real money on 6/15.** The forensic data does not support it. Two acceptable paths:

- **Path A — Retire WB:** Squeeze-only at go-live. WB code stays in repo, env disabled.
- **Path B — Paper-only WB:** Run a tight FATN-pattern-only WB observe stack on the engine paper account (post-12 ET, score≥8, R%≥1.5%, pre-arm 5-bar range ≤1%, entry-bar vol ≥2× pre-5 avg AND ≥1,000sh abs). No real-money exposure. Re-evaluate after 30 paper sessions.

Either path beats Path C (ship as-is): Path C concedes we have no edge.

I lean toward **Path B** — keeping WB alive in paper mode preserves the data pipeline for future iteration without dollar risk. But if Cowork prefers cleanliness, Path A (retire) is also defensible.

---

## Limitations of this synthesis

- **n=5 WB winners** is too few to confidently say "no template exists" vs "small-sample noise hides the template." The strongest version of the finding is "no template visible in the current sample after looking at the directive's 9 candidate features."
- **Investigation 3.2's EH WR=0% has n=5 fills total.** A wider EH sample could surface winners. The 13/3 RTH baseline has the same small-sample risk.
- **Investigation 2's dead-tape inversion is the weakest claim.** n=2 winners with one EH-quirk (ATRA 5/8) and one questionable (ATRA 5/15). Could be coincidence.
- **The squeeze re-entry finding (Inv 1)** is genuinely small (n=2 N≥2 fills). The proposed cap is low-risk so directional support is sufficient, but don't expect dramatic P&L improvement.

The structural finding (Inv 4: no template) is the most robust precisely because the directive's hypothesis was specific and pre-registered. Finding 1 shared feature of 9 candidates ≥4-of-5 is the kind of negative result that survives small-sample doubt.

---

## What this synthesis owes the weekend response directive

The weekend-response directive included a Monday gate list. The forensic synthesis revises it:

| Weekend directive item | Forensic verdict |
|---|---|
| `dead_bounce` sub-gate: OBSERVE→enforce | Defer — Inv 2's volume-pattern inversion may invalidate the gate's premise. Observe with dead-tape gate together. |
| Per-symbol attempts cap | **Confirmed** — Inv 1 supports. Ship with N=3 cap + score-decay guard. |
| EH WB block | **Confirmed** — Inv 3.2 supports. Override the no-overnights-clarification. |
| FCHL fix validation on real overnight | Moot (force-exit handles it) — clarification was right about that piece. |
| L2 first verdicts | Pending Monday's isSmartDepth-alternative smoke test |

---

## Reports completed today

| Report | Status |
|---|---|
| Investigation 1 — squeeze re-entry forensic | ✅ `cowork_reports/2026-05-17_squeeze_reentry_forensic.md` |
| Investigation 2 — WB loser behavioral profile | ✅ `cowork_reports/2026-05-17_wb_loser_behavioral_profile.md` |
| Investigation 3 — stop-hit reverse + EH sub-question | ✅ `cowork_reports/2026-05-17_wb_stop_hit_reverse_analysis.md` |
| Investigation 4 — WB winner template | ✅ `cowork_reports/2026-05-17_wb_winner_template.md` |
| **This synthesis** | ✅ `cowork_reports/2026-05-17_loser_forensic_synthesis.md` |
| Investigation 5 — universe widening | ❌ skipped (conditional on Inv 4 template, none exists) |

---

*Five hypotheses tested in one weekend on existing log + tick_cache data. Two confirmed (squeeze re-entry directional, EH block), two rejected (faster-exit help, EH revert), one falsified (no winner template). The path forward is squeeze-only at go-live unless paper-data over the next 3 weeks produces evidence WB has a pattern that isn't visible in this sample. The diagnostic work paid off — we no longer need to wonder whether WB has an edge; we have evidence it doesn't.*
