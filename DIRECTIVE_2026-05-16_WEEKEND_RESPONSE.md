# Weekend Response — Audit Findings + Monday Directives

**Date:** 2026-05-16
**Author:** Cowork (Perplexity)
**For:** CC + Manny
**Sources:**
- `cowork_reports/2026-05-16_fchl_session_resume_fix.md` — P0.1 + P0.2 shipped
- `cowork_reports/2026-05-16_l2_async_refactor.md` — P1.1 shipped
- `cowork_reports/2026-05-16_dead_tape_gate_validation.md` — P1.2 shipped (validation gap noted)
- `cowork_reports/2026-05-16_squeeze_strategy_audit_weekly.md` — squeeze audit
- `cowork_reports/2026-05-16_wb_strategy_audit_weekly.md` — WB audit

---

## TL;DR

Three Saturday ships landed clean. Two audits delivered. The audits change the picture going into June 4 more than the ships do.

1. **P0 work closed cleanly.** FCHL/force-exit/L2-async-refactor/dead-tape-gate all shipped, all smoke-tested, Monday is real validation.
2. **Squeeze: don't touch.** Audit is essentially "we don't have enough data to refine yet." Approve CC's one suggested change (per-symbol attempts cap).
3. **WB: structural concern.** Strip MEI (manual), FCHL (infra), ODYS overnights → 19% win rate, −$9K over 16 fills. **The only fresh winner (ATRA 5/15 +$1,160) is a setup the new dead-tape gate would have vetoed.**
4. **June 4 go-live posture: revisit.** Squeeze is plausibly real-money ready after one more clean paper week. **WB is not.** Recommend squeeze-only on real money with WB paper-extended.
5. **Persistence layer: under review.** Net −$874 this week. With dead-tape gate enforcing, the persisted-symbol slice is exactly where the gate vetoes most often. Layer may become functionally inert. Decide after Monday's gate validation.

Monday's first session is the most consequential paper day of the project. The validations that haven't happened yet (dead-tape historical backfill, L2 first real verdicts, FCHL fix on a non-fixture position) all land in one session.

---

## 1. Saturday ships — acknowledged

CC delivered four pieces of work cleanly:

| Ship | Notes |
|---|---|
| **P0.1 FCHL session-resume** | Broker-as-source-of-truth check before mode decision + 7-day lookback to prior `open_trades.json`. Synthetic FCHL fixture passes. Existing `_resume_rehydrate` orphan-adoption path now actually runs. |
| **P0.2 Session-end force-exit** | Aggressive SELL LIMIT chain (1%/2%/3% offsets, never market orders — respects the user constraint). 19:55 ET trigger via background thread. Fires once per day per process via latch. |
| **P1.1 L2 async-thread refactor** | Dedicated bg asyncio loop in a daemon thread per process. Unique clientId per bot (42/43/44/45). Bot's main asyncio loop never touched. Sync wrapper uses `asyncio.run_coroutine_threadsafe`. All 4 entry paths re-enabled, observe-only. |
| **P1.2 Dead-tape gate** | `tape_quality.py` shipped. ATRA 5/15 vetoes correctly at dead_rate=0.80. **Historical-winner validation deferred — biggest open item for Monday.** |
| **P1.3 WB persistence race fix** | Bundled into the FCHL commit. Atomic write pattern. |

**Acknowledgment specifics worth calling out:**

- CC chose `force_exit` via SELL LIMIT chain rather than market orders unprompted. Respects the no-market-orders constraint that's been mentioned in passing all week. That's good attention to project conventions.
- The `_resume_rehydrate` insight — that orphan-adoption code already existed but never ran because `mode=cold` skipped it — is the kind of finding that produces a small fix with structural payoff. Good audit work.
- The L2 hot-patch direction was right; the Saturday refactor commits to it fully. The mistake on the `.attach()` approach was mine; the recovery was clean.

---

## 2. Squeeze audit response

### Approve as written

CC's analysis is appropriately humble — n=6 fills across one productive day is not a sample. The audit's strongest insight is also its bottom line: **the strategy's edge (if any) is being decided pre-entry by time-of-day × score × level × volume context, not by exit micromechanics.** Exits work; chase caps work; entries are the place to focus when more data lands.

### One action item from the audit — approved

**Per-symbol max-attempts-per-day cap.** The SLE re-fire stack in extended hours (6 attempts, 90 minutes) was wasted scanner/order bandwidth. CC's suggested cap of 3/day is fine.

### Spec for the cap

```
# Env (squeeze + WB share; symbol counter is per-strategy)
WB_MAX_ATTEMPTS_PER_SYMBOL_PER_DAY=3
WB_SQ_MAX_ATTEMPTS_PER_SYMBOL_PER_DAY=3
```

Counter resets at 00:00 ET each day. Counter increments on every order submission (fills, timeouts, BP-blocks, broker-rejects — all count). Once a symbol hits the cap, log `SQ_REJECT symbol=X reason=max_daily_attempts(3)` and skip future ARMs that day.

Implementation: a `dict[symbol, int]` on session state, persisted across restarts via `session_state/<today>/attempt_counts.json`. CC can fold the persistence into the existing session state schema.

### What I'm NOT directing on squeeze

- **Not** widening chase caps based on ONDG/QUCY 5/15 "misses." CC's counterpoint is correct: ATRA 5/13 filled and lost $906 in 3 minutes. Filling more isn't always better. Hold caps at current values.
- **Not** changing score floors. The week's data shows score=10 winning and score=11 losing — clearly noise at n=6.
- **Not** investigating Setup B's worse performance. CC correctly tagged this as likely fill-quality/latency (engine has had connection-reset and partial-fill events Setup A didn't). Worth tracking but not refactoring.
- **Not** acting on the time-of-day pattern. n=2 late-day losses on the same reconnect event is not a pattern.

---

## 3. WB audit response — this is the bigger issue

### The audit's central uncomfortable finding

Strip three things from this week's WB data:
- **FCHL −$13,453** (infrastructure, not strategy)
- **MEI +$1,006** (manual watchlist injection, strategy didn't choose it)
- **ODYS −$1,300 overnight events** (extended-hours into next-AM, will be eliminated by P0.2 force-exit)

Remaining: **16 P&L fills, 3 winners, 13 losers, 19% win rate, −$9,131 net.** That's not a calibration cost. That's a strategy that's losing money systematically.

And — this is the part that has to be said aloud — **the only fresh winner under the current rule set is ATRA 5/15 (+$1,160), which the dead-tape gate we just shipped would have vetoed.**

### My honest read

I had been treating WB as "validated by FATN 5/5 / ATRA 5/8 / SST 5/11 / MEI 5/13" — four winners across two weeks. CC's audit forces a tighter reading:

- **MEI** was manual injection. Strategy didn't surface it.
- **SST 5/11 +$2,090** is one trade, one ticker, wave-60 (anomalous depth).
- **ATRA 5/8 +$2,499** was a 68% gap day — would the dead-tape gate pass it? CC's synthetic validation says yes. **Real-bar validation pending Monday.**
- **FATN 5/5 +$1,074** — also pending real-bar validation.

If Monday's dead-tape backfill shows FATN 5/5 or ATRA 5/8 was also dead-tape entries, **the strategy's entire historical evidence base collapses to "SST 5/11 + manual MEI."** That's not enough to defend going live.

If both pass dead-tape validation, we still have the structural question: this week's 16 fills produced 3 winners. The persistence layer is feeding mostly losers. Score=10 is 0/5.

### What I'm directing for WB on Monday

**Tighten 1: Block extended-hours entries.** No WB ARMs after 17:30 ET until session-resume is proven on a non-fixture overnight position. Env: `WB_DISABLE_EXTENDED_HOURS_ENTRY=1`.

Reasoning: 6 EH fills this week, 0 winners, −$15,257 incl FCHL or −$1,804 excl. SLE 5/15 19:17 was correctly force-closed at 19:55 (−$713 vs market move). But the FCHL precedent says one date-boundary slip away from a real-money disaster. Until we see force-exit fire correctly on a real overnight situation, EH entries are pure tail risk.

**Tighten 2: Flip `dead_bounce` from OBSERVE to enforce.** CC's audit found ONDG 5/15 14:07 would have been vetoed (drift=0, cum=$1.93, vol_ratio=0.09). That trade lost $1,198. With one clean would-veto and no false positives this week, promote to enforce.

```
WB_CG3_DEAD_BOUNCE_ENABLED=1
```

(This reverses the May 12 retirement directive partially — the dead_bounce I retired was v1, which never blocked its target. CC's current implementation has a working version per the audit.)

**Tighten 3: Per-symbol max-attempts/day cap (same as squeeze).** ATRA had 5 fills this week on Setup A alone. The dead-tape + same-session-blacklist should reduce this, but the explicit cap is belt-and-suspenders.

**Do NOT change yet:**
- Score floor (keeping at 7; raising to 8 would have removed MEI's wins and changed nothing else)
- R% floor (keeping at 1.5%; mixed at borderline but no clear cutpoint)
- Post-11 ET time gate (works as-is)
- Trailing stop / dollar loss cap (exits worked on every loser this week — strategy losses are about entries, not exits)

### What needs more thought before next week

The persistence layer's real value vs the dead-tape gate's blocking pattern. Persisted-symbol entries are exactly the slice the dead-tape gate vetoes most often (since "persisted" tends to correlate with "traded through setup and now in consolidation"). If Monday's data shows dead-tape vetoes the majority of persistence-fed entries, the layer is functionally inert under the new gate stack.

That's not necessarily bad — vetoes are vetoes, the gate is doing its job. But it raises the question: **what's persistence FOR if its candidates can't get through the gate stack?** Possibilities:

1. The dead-tape threshold is too tight, and a relaxation specifically for persistence-fed candidates restores their feasibility
2. Persistence's value is in the wave-tracker continuity (the bot knows about ongoing waves it didn't scan today), not in surfacing new entries — and the actual entry decision should still go through the gate stack
3. Persistence is a net-negative concept that should be retired

I don't want to decide this on Saturday. Monday's data points to the answer.

---

## 4. June 4 go-live posture — revised

**Current posture per Friday's directive:** if Saturday's P0 lands clean, 5 paper days (5/18–5/22 + 5/26) before cutover.

**Revised posture per the audits:**

| Component | Go-live ready? |
|---|---|
| Squeeze fill-rate fix | ✅ validated 5/15 |
| Pre-submit BP check | ✅ validated 5/15 |
| FCHL session-resume fix | ⚠ synthetic pass; need real overnight validation |
| P0.2 force-exit | ⚠ synthetic pass; need real EOD validation |
| L2 Layer 1 (observe) | ⚠ shipped, needs first live verdicts Monday |
| Dead-tape gate | ⚠ shipped, needs historical-winner backfill |
| Squeeze strategy edge | ⚠ need more data — 6 fills isn't a sample |
| **WB strategy edge** | ❌ **not demonstrated** — 19% win rate, −$9K stripped |

### Recommendation

**Squeeze-only on real money June 4. WB stays paper for 2-4 more weeks.**

Reasoning:
- Squeeze has the fill-rate fix validated, BP check validated, exit logic validated. One more clean paper week and it's plausibly real-money worthy.
- WB has no demonstrated edge after removing the manual/infra/overnight events. Going live with a money-losing strategy on real money 20 days from now is not the rational call.
- WB can stay paper as long as we want. Two more weeks of paper data lets us see whether the new gate stack (dead-tape, dead_bounce enforced, EH block, session-resume hardened) restores positive expectancy. If yes, ship to real money 6/18 or 6/25. If no, structural rework or retirement.

This is **your call**, Manny. The data argues for the split-rollout approach, but you have context I don't (your tolerance for paper-extended timelines, what the day-trading psychology looks like running squeeze-only, whether "WB paper while squeeze real" creates awkward UX for the agent rosters).

If you want WB on real money 6/4 anyway, **at minimum** I'd want:
1. Confirmed P0.1+P0.2 working on a real overnight position (Monday-Tuesday)
2. Confirmed dead-tape doesn't veto historical winners (Monday backfill)
3. Confirmed dead_bounce-enforce doesn't false-positive (Mon-Tue paper)
4. WB notional cut by 50% (from $30K to $15K) until paper data shows positive expectancy
5. WB extended-hours blocked entirely

### Hard floor (regardless of split decision)

**FCHL fix must be validated on a non-synthetic position before June 4.** No exception. If Monday's data doesn't include a force-exit or session-resume event, run a deliberate test: have CC submit a small paper position late Monday afternoon, observe whether force-exit fires correctly at 19:55 ET, observe whether next-morning boot recovers correctly. If either fails, defer cutover until they pass.

---

## 5. The dead-tape gate paradox

CC's report is candid: real-bar validation against FATN 5/5, ATRA 5/8, SST 5/11, MEI 5/13 is deferred to Monday. The whole strategy's defensibility depends on the outcome.

**Three possible outcomes:**

| Outcome | Implication |
|---|---|
| **All 4 winners PASS dead-tape** | Gate is correctly calibrated. ATRA 5/15 false-positive is acceptable (correlation between thin tape and bad expectancy is real even when this individual trade won). Ship gate as-is, persistence layer still has value. |
| **2-3 winners PASS, 1-2 VETO** | Threshold needs tuning. Raise `WB_DEAD_TAPE_MAX_DEAD_RATE` to 0.6 or 0.7. Re-validate. Persistence layer survives with a slightly more permissive gate. |
| **All 4 winners VETO** | Strategy structurally relies on dead-tape entries. Either accept losing those wins (gate as-is, strategy loses what little edge it has) or retire the dead-tape gate (gate-off, strategy stays vulnerable to ATRA-5/15-class misfires). Forces a real decision. |

Monday's backfill is the most important single validation outstanding. CC should run it first thing.

---

## 6. Monday action list (priority order)

| # | Item | Owner | Acceptance |
|---|------|-------|-----------|
| 1 | Pull historical 1m bars from `tick_cache` for FATN 5/5, ATRA 5/8, SST 5/11, MEI 5/13. Reconstruct 30-min pre-entry tape. Run through `tape_quality.is_dead_tape`. Append to dead-tape validation report. | CC | All 4 winners PASS at default threshold, OR tune threshold and re-validate |
| 2 | L2 Layer 1: confirm `bg-thread IB connected (clientId=NN)` lines appear for all 4 bots within 60s of cron. First WB/squeeze ARM produces a verdict line. | CC + observe | Telemetry flowing on every ARM |
| 3 | Force-exit at 19:55 ET: if any open positions exist, confirm SELL LIMIT chain fires correctly. If no positions, confirm `should_force_exit_now()` returns True at 19:55 and False at 19:54. | CC | Logged behavior matches spec |
| 4 | Flip `WB_CG3_DEAD_BOUNCE_ENABLED=1` (enforce). Per audit, would have saved ONDG 5/15. | CC | Reverses partial retirement directive |
| 5 | Add `WB_DISABLE_EXTENDED_HOURS_ENTRY=1` for WB. No ARMs after 17:30 ET. | CC | EH entries skipped with log line |
| 6 | Per-symbol max-attempts/day cap (3) for both squeeze and WB. | CC | Counter persists across restarts |
| 7 | EOD daily breakdown report includes: L2 latency p50/p95/p99, dead-tape verdict count, dead_bounce-enforce vetoes, EH block hits, per-symbol attempt counts | CC | Per existing template plus new sections |
| 8 | Update CLAUDE.md / project rules: "Any IO that blocks synchronously on an event-loop callback must run on its own asyncio loop in its own thread." (Codifying the L2 lesson.) | CC | Brief addition |

---

## 7. What I'm NOT directing

1. **Not** structural changes to squeeze strategy. Wait for more data.
2. **Not** changes to WB score floor or R% floor. Wait for more data.
3. **Not** advancing past Phase 6 in the L2 full-build plan. Phases 7-8 stay parked.
4. **Not** retiring the persistence layer or intraday adder. Both continue running. Decisions on retirement come after Monday's data.
5. **Not** flipping L2 OBSERVE_ONLY=0 yet. Observe week first, then tune, then enforce.

---

## 8. Reports CC owes

| When | Report | Status |
|---|---|---|
| Mon 5/18 morning | Append historical-winner validation to `cowork_reports/2026-05-16_dead_tape_gate_validation.md` | required before market open |
| Mon EOD 5/18 | `cowork_reports/daily_trades/2026-05-18_trade_breakdown.md` with L2 + dead-tape + force-exit + dead_bounce-enforce + EH-block + attempt-counter sections | new daily |
| Tue 5/19 | Decision memo on Jan-Apr WB backtest commission with liquidity-aware execution — per existing plan | per existing |
| Fri 5/22 | Cumulative 5-day L2 observe summary + threshold tuning recommendation | per L2 build plan Phase 4 |
| Fri 5/22 | 5-day squeeze fix evaluation per yesterday's directive | per existing |

---

## 9. For Manny: the call to make

The one strategic decision needing your sign-off this weekend:

**Go-live posture options:**

A) **Squeeze + WB both real money 6/4.** Higher exposure, ~$30-50K capital at risk. Requires all gate validations to pass clean. WB's lack of demonstrated edge means likely small losses in the first weeks while we tune.

B) **Squeeze-only real money 6/4. WB stays paper until 6/18-6/25 or longer.** Lower exposure. Cleanest possible go-live. WB extension period lets the new gate stack prove out without real-money pressure.

C) **Both real money 6/4 but WB at half notional.** Compromise. WB at $15K instead of $30K notional, EH blocked, all gates live. Lets WB earn its way up.

D) **Defer the whole cutover to 6/18 or 6/25.** If anything in Monday-Friday data raises new concerns. This is the conservative fallback.

My recommendation is **B**. Squeeze has roughly demonstrated edge (one win-loss day is a sample of one, but the fix and exit mechanics work). WB doesn't have demonstrated edge after stripping outliers. Going live with a strategy losing 81% of its trades is unjustified.

But you have context I don't and this is a real call worth thinking about before Monday opens.

---

## 10. Tone

Three Saturday ships closed cleanly. Two audits delivered honest reads that change the picture in important ways. The WB audit specifically — strip MEI, strip FCHL, strip overnights → 19% win rate — is the kind of finding that prevents weeks of real-money damage. Better to know now than mid-June.

The team is operating at high quality. CC's audit honesty (admitting MEI was manual, admitting the only fresh winner would be vetoed) is exactly the rigor we need 20 days from real money. The fact that audit-led iteration is producing structural insight rather than just performance tuning means the loop is working.

Monday's session will tell us more about the project's readiness than the previous two weeks combined. The validations queued for that day are exactly the ones that matter most.

---

## 11. Files referenced

- `cowork_reports/2026-05-16_fchl_session_resume_fix.md`
- `cowork_reports/2026-05-16_l2_async_refactor.md`
- `cowork_reports/2026-05-16_dead_tape_gate_validation.md`
- `cowork_reports/2026-05-16_squeeze_strategy_audit_weekly.md`
- `cowork_reports/2026-05-16_wb_strategy_audit_weekly.md`
- `tape_quality.py` (new, shipped Saturday)
- `force_exit.py` (new, shipped Saturday)
- `l2_helper.py` (refactored Saturday)
- `engine_bot_common.py:decide_boot_mode` (FCHL fix)
- `DIRECTIVE_2026-05-15_DAILY_RESPONSE.md` (Saturday's prioritization, now closed)
- `DIRECTIVE_2026-05-15_WB_DEAD_TAPE_GATE.md` (validation ongoing)
- `DIRECTIVE_2026-05-15_L2_FULL_BUILD.md` (Phase 1-3 effectively closed Saturday)
