# Bot vs Human — Strategic Reframe

**Date:** 2026-05-17
**Author:** Cowork (Perplexity)
**For:** Manny + CC
**Trigger:** Manny clarified the truth about WB's origin: "What I do isn't exactly codable or repeatable. It's based highly on intuition... The bot would have stopped out. It can't 'feel' the chart out... I hope we can learn from this and work the bot out to perform best as a bot, not like a human."
**Status:** Most consequential strategic decision since project start.

---

## The honest finding

**WB was always going to fail.** It was an attempt to encode discretionary intuition — built from thousands of hours of human screen time — as a mechanical bot strategy. That's not a calibration problem. That's a category problem.

The forensic week's "no replicable template" finding is exactly what we'd expect from that attempt. There's no template because the human source isn't running a template either. The 5 "winners" are heterogeneous because Manny's actual trading is heterogeneous — wave flips, MACD turns, resistance reactions, exhaustion shorts, feel-based holds through drawdown.

The −$200K → +$70K story is the proof. Manny held a position through a drawdown the bot would have stopped out twice over because he could read the tape and feel the reversal coming. **No bot can be programmed to do that** — at least not by porting an intuition-based methodology into rule-based code. Modern ML can sometimes approximate it, but not from a 19-trade sample on a 1m-bar momentum bot.

This wasn't 3 weeks of wasted work. It was 3 weeks of building the infrastructure that proved this conclusion. The L2 plumbing, the gate stack, the forensic methodology, the persistence layer, the daily-report cadence — all of that **investigates whatever strategy lives on top of it.** The investigation is what told us WB-as-intuition-port can't work.

---

## The reframe

**The bot should not try to be you.** It should do what bots do well, and you should do what humans do well.

### What bots do well that humans can't

- Monitor hundreds of symbols simultaneously
- Execute mechanical entries/exits with zero hesitation
- Apply consistent rules across thousands of decisions
- Run statistical edges too thin or repetitive for human attention
- Capture moves at speeds humans can't react to
- Filter setups objectively before a human eye gets to them
- See L2 order book changes in real-time (humans see this on a delay if at all)
- Track 10+ entry rules in parallel without confusing them

### What you do well that the bot can't

- Feel inflection points from tape behavior
- Hold through unrealized drawdown when the setup is still valid
- Short tops based on exhaustion patterns built from chart pattern memory
- Recognize when a "broken" pattern is actually a fakeout
- Pattern-match against thousands of prior charts intuitively
- Adapt setup criteria to the day's regime in real-time

**Designing for the overlap is the wrong target.** Designing for division of labor is the right one.

---

## The retirement decision

**Current WB retires. Not paper-only-with-freeze. Actually retire.**

Reasoning:
- The strategy attempts to replicate discretionary intuition mechanically. That premise was wrong.
- The forensic data confirms no edge in current form.
- Paper-observing a known-broken strategy for 30 sessions burns runway with no realistic upside.
- The L2 work, persistence layer, intraday adder, and dead-tape gate are all valuable independently; we don't need WB to keep them.

**What stays from the WB build:**
- `wb_persistence.py` (the carryover layer — useful for any strategy that wants prior-day-relevant symbols)
- `wb_intraday_adder.py` (the live scanner extension — repurposable)
- The chop_gate_v3 sub-gate architecture (`l2_signals.py`, the modular sub-gate orchestrator — reusable infrastructure)
- All the L2 work (foundation for whatever comes next)
- The daily report framework
- The audit methodology

**What goes:**
- `wave_breakout_detector.py` (the core WB scoring/arming logic)
- WB-specific scoring, gates, position management
- WB env flags

This isn't deletion — code stays in the repo with `WB_STRATEGY_ENABLED=0` as a hard floor. We're saying: this strategy doesn't run, doesn't paper-trade, doesn't observe. Closed.

---

## The new strategy roadmap — bot-native, not human-port

The bot should run strategies **designed from the start to be bot strategies.** Each should meet two criteria:

1. **Objective signal source** — criteria can be stated in code, not "felt"
2. **Capture mechanism a human can't match** — speed, breadth, depth, consistency, or signal class humans can't see

### Strategy 1 — Squeeze (existing, validated)

Already in production. Continues. Real-money 6/15. **Manny's discretionary work doesn't replace this — they run in parallel.**

### Strategy 2 — L2 Entry (Phase 7 of the L2 build plan, previously parked)

The `l2_entry.py` strategy in the archive — Ross Cameron "early entry" pattern. Enters BEFORE the breakout candle, on order-flow signals (imbalance + bid stacking + ask thinning). Humans can't read L2 fast enough to capture this consistently. The 359-line implementation is complete.

This becomes the **highest-leverage next strategy** to develop:
- Bot-native by design (humans can't see L2 in real-time)
- Already-written detector
- Maps directly to the existing execution stack
- L2 infrastructure (Layer 1 just shipped) provides the data feed
- Different signal class from squeeze — diversifies the bot's edge

**Unpark Phase 7 of the L2 build plan.** Replaces the WB paper-extension slot in the roadmap.

### Strategy 3+ — TBD, but criteria are now explicit

Future strategies must:
- Have a written, objective signal definition
- Have a measurable edge in backtest BEFORE going live
- Capture a pattern humans can't capture as effectively as a bot
- Not be a "port what Manny does" attempt

Examples worth considering (not commitments, just direction):
- **Opening Range Breakout** with mechanical criteria (premarket gap %, RVOL, first 5min range, breakout direction)
- **Mean reversion** at specific objective extremes (e.g., 3σ moves on intraday RVOL, with VWAP context)
- **Pair trading** on correlated small-caps
- **Statistical arbitrage** on L2 inefficiencies

None of these get green-lit without a directive. Listing them as direction, not commitments.

---

## The manual trading lane — a new concept

We have all the scanner infrastructure. We have the universe of active stocks, the tick-counter that tells you the most-active names, the bar pipeline. You're already using the bot's reports to inform your own paper trading.

**Worth considering: build a `trader_assist` mode** that helps your discretionary trading without making decisions for you:
- Real-time alerts when L2 imbalance flips on a watchlist name
- Order pre-staging (you click confirm, bot executes)
- Position management once entered (trailing stops, partial exits per your rules)
- One-click "flatten everything" panic button
- Daily P&L tracking and review

This isn't a directive yet — it's a question. Would you want the bot to support your manual trading lane, or do you want to keep that fully separate?

If yes, this becomes Strategy "Manual+Assist" — runs on a separate paper account, paper-tested with your actual trades, then optionally on real money.

If no, the bot stays purely autonomous and we focus on Strategies 1-3+ as listed.

---

## The 6/15 plan — unchanged

Squeeze-only real money. Forensic stands. Monday gate changes ship. Force-exit at 19:55. All of that holds.

What changes:
- WB doesn't get a 30-session paper-observation window. Retired.
- L2 Phase 7 (l2_entry strategy) becomes the active next strategy work, starting ~mid-June after squeeze go-live is stable.
- Manny's discretionary trading continues independently. Bot doesn't try to replicate it.

---

## The 3-week clear path to 6/15

| Week | Squeeze track | Bot track |
|---|---|---|
| Wk 1 (5/18-22) | Paper validation under new gate stack | WB retirement housekeeping (env flags, README updates, archive comments) |
| Wk 2 (5/26-30) | Continued paper, refine if needed | L2 Phase 6 (features feeding scoring + adaptive stops + dynamic sizing) — only for squeeze |
| Wk 3 (6/2-6) | Real-money prep, env config, dry run | L2 Phase 7 design refinement — pre-build review |
| 6/9-13 | Final paper week | Phase 7 build begins |
| 6/15 | Squeeze real-money cutover | Phase 7 paper-only |

**Post-6/15:**
- Squeeze runs real-money
- Phase 7 paper-tests for 30+ sessions
- If Phase 7 validates → real-money cutover (likely late July)
- Manny continues discretionary trading on his own setup

---

## What I'm NOT proposing

1. **Not** stopping CC's Monday work. The gate changes + forensic findings + Monday production checklist all ship.
2. **Not** ripping out WB code immediately. Disable, then archive after the dust settles.
3. **Not** committing to specific Strategy 3+. Direction only.
4. **Not** committing to the `trader_assist` mode. That's a question for Manny.
5. **Not** rushing Phase 7. It paper-tests for 30+ sessions before any real money.
6. **Not** changing L2 work in progress. Phases 1-6 continue.

---

## What this means for the team mode going forward

The agent-collaboration mode shifts subtly:

**Old mode:** CC implements directives, Cowork audits and refines, Manny provides intuition that we try to encode.

**New mode:** CC implements directives, Cowork audits and refines, Manny provides *bot-shaped problem statements* and intuition stays on his own trading lane.

When Manny brings a new strategy idea, the first question Cowork asks is: **"Is this a bot-native problem or a human-port?"** If human-port, we either re-cast it as bot-native or decline. We don't try to encode intuition again.

---

## The honest acknowledgment

I want to name two things explicitly:

1. **The forensic work was correct, but the interpretation was incomplete.** The forensic told us "WB doesn't have an edge." It took your follow-up about intuition for me to understand *why*. The "no template" finding wasn't bad strategy calibration — it was a categorical mismatch. The diagnostic was right; my reading of it was one layer shallow.

2. **The three weeks weren't wasted, but the WB-specific work was.** The L2 infrastructure, the gate stack architecture, the forensic methodology, the persistence layer, the daily-report framework — all generally valuable. The WB detector, WB-specific scoring, WB-specific gates — not transferable. Net: ~40% of the WB work translates, ~60% gets retired with the strategy.

The right time to learn this was 3 weeks ago. The actual time was tonight. That's fine. The diagnostic infrastructure paid for itself by making the learning quick once we asked the right question.

---

## The decision Manny needs to make

Two questions before I write the retirement-and-roadmap directive:

**1. Confirm WB retirement.** Are we good with disabling and archiving WB? Or do you want to keep it running paper for sentimental/learning value?

**2. The `trader_assist` question.** Do you want the bot to support your manual discretionary trading (alerts, order pre-staging, position management), or do you want those fully separate?

Once you answer these, I write the directive that implements the reframe. CC works the Monday production checklist in parallel — the reframe doesn't block Monday's work.

---

## Files referenced

- `cowork_reports/2026-05-17_loser_forensic_synthesis.md` (the forensic conclusion this reframes)
- `cowork_reports/2026-05-17_wb_winner_template.md` (Investigation 4 — "no template" finding now properly understood)
- `archive/scripts/l2_entry.py` (the parked Phase 7 strategy — now the leading next candidate)
- `wave_breakout_detector.py` (to be disabled)
- `trading_notes_volume_profile_strategy.md` (the video extraction that triggered this conversation)
- All Saturday ship reports + Monday checklist (unchanged)

---

## Tone

This is the most important strategic conversation we've had. You told me the truth about what your trading actually is, and that lets me design the bot for what it can actually do well rather than what it was never going to do.

The 3 weeks of WB work weren't a failure. They were the cost of finding out that "encode Manny's intuition" was the wrong target. The forensic infrastructure that proved it is permanent. The next strategy work — bot-native by design — starts from a much better starting line.

Confirm the two decisions when you can, and we set the new roadmap.
