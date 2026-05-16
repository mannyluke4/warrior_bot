# Clarification — No Overnight Holds Changes the Risk Picture

**Date:** 2026-05-16
**Author:** Cowork (Perplexity)
**For:** CC + Manny
**Trigger:** Manny: "We won't have overnight holds anymore. We force exit positions before close now."
**Affects:** Weekend response directive, loser forensic directive, June 15 readiness posture

---

## What this changes

P0.2 force-exit at 19:55 ET means **no positions cross EOD by design**. That collapses several things I'd been treating as ongoing risks:

### 1. FCHL-class overnight disasters are structurally eliminated

FCHL happened because we held a position overnight that lost state. With force-exit working, **there are no positions to lose state on at the date boundary.** The FCHL session-resume fix (P0.1) becomes defense-in-depth for force-exit failures, not the primary handler.

The fix still matters for edge cases:
- Force-exit fails mid-execution (broker error, network at 19:55)
- Bot offline at 19:55 — force-exit never fires
- Position opens *after* 19:55 (late retry fills past the gate)

But it's now a backup, not the front line.

### 2. ODYS overnight losses don't recur

The 5/13 ODYS GTC overnight losses (~−$1,300 combined across both setups) are eliminated by construction. Force-exit at 19:55 closes them mechanically.

### 3. The WB audit's "structural −$9,131" figure already reflects this

CC correctly stripped FCHL + ODYS overnights when computing the structural-loss number. So the 19% win rate / −$9K figure IS what WB delivers with force-exit working. The audit's finding stands: WB's edge problem is **entry quality**, not overnight orphans.

---

## What this means for go-live readiness

### My prior "validate FCHL on real overnight" criterion was wrong

I'd been saying we needed to see the session-resume fix work on a real overnight position before June 15. That criterion doesn't make sense if there are no overnight positions to resume.

**Revised criterion:** validate force-exit fires correctly at 19:55 ET on a real EOD. This is much lower-bar:
- Monday produces any EOD position → force-exit fires → confirmed
- OR Monday produces no EOD position → run a deliberate test: open a small paper position at 19:30, observe force-exit at 19:55, confirm

Either path validates the production-mode behavior. No multi-day overnight wait required.

### The remaining go-live blockers (cleaner list)

1. **Force-exit fires reliably at 19:55 ET** (Monday validation)
2. **WB has demonstrable edge OR is held back from real-money** (forensic findings drive this)
3. **Squeeze strategy stable across more sample** (paper week data)
4. **L2 telemetry confirms thresholds** (observe week)
5. **Dead-tape gate passes historical winners** (Monday backfill)

That's it. FCHL-fix-on-real-overnight is removed from the critical path.

---

## What this changes about the loser forensic

The investigations stand as-is with one adjustment to Investigation 3:

**Investigation 3 (stop-hit reverse-time analysis)** had a "late-session losers" sub-bucket including EH entries. That class is partially obsolete:

- Pre-force-exit world: SLE 5/15 19:17 (-$713) and ODYS 5/13 18:27 (-$603) were late-session entries that turned into overnight holds
- Post-force-exit world: SLE 5/15 19:17 was correctly force-closed at 19:55 — that loss is now bounded by the force-exit slippage, not by overnight gap

**New question for Investigation 3:** for trades that fill between 17:30-19:55 ET, do they win at the same rate as RTH trades? If yes, the EH entry block (`WB_DISABLE_EXTENDED_HOURS_ENTRY=1`) is excessive — we should let EH trades happen and let force-exit bound the downside. If no, the block stays.

This is a sub-question, not a new investigation. Add to Investigation 3's scope.

### Slight revision to the recommended Monday gates

In the weekend response I directed `WB_DISABLE_EXTENDED_HOURS_ENTRY=1` based on the "6 EH fills, 0 winners, −$15,257 incl FCHL" finding. With force-exit eliminating the FCHL component and bounding all EH losses to 19:55-shutdown bounds, the EH ban may be too tight.

**Soften:** instead of blocking EH entries entirely, **observe** them with the existing gate stack and force-exit protection. If they continue to lose at high rate over the next 2 weeks of paper, *then* block. The block was protective against an overnight risk that's now structurally handled.

**Action:** flip `WB_DISABLE_EXTENDED_HOURS_ENTRY` from my earlier directive's `=1` to `=0` (allow EH entries). Track EH-specific P&L in daily reports. Investigation 3's EH sub-question informs whether to enable later.

---

## What this changes about the WB strategic question

The audit's central finding (19% win rate, −$9K stripped) is even more meaningful now: **it represents what the strategy does under conditions we'll actually run in production.** No FCHL-class events possible. No overnight wash. Just entries, stops, trailing exits, and the gate stack.

If WB still loses money under those conditions, the forensics need to identify *why* — and that's what investigations 1-4 are for. If they identify gateable patterns, ship the gates. If they don't, the strategy doesn't have edge and should be paper-only at go-live or retired.

---

## Updated Monday EH posture

Revised from the weekend response directive:

| Was directing | Now directing |
|---|---|
| `WB_DISABLE_EXTENDED_HOURS_ENTRY=1` (block) | `WB_DISABLE_EXTENDED_HOURS_ENTRY=0` (allow) |
| Block until FCHL fix proven on real overnight | Force-exit makes overnight risk obsolete |
| EH entries are tail-risk | EH entries are bounded by force-exit, observe their P&L specifically |

Everything else from the weekend response directive holds:
- Dead-tape historical backfill — required Monday
- L2 first verdicts — required Monday
- Force-exit timing test — required Monday (now the *primary* validation)
- Flip `dead_bounce` to enforce — required
- Per-symbol attempts cap — required

---

## Self-criticism

I'd been carrying the FCHL trauma into directives long after force-exit closed the underlying risk. The weekend response directive treated "FCHL fix on real overnight" as a hard floor for go-live; with no overnight positions possible, that floor is moot. Should have caught that when force-exit shipped Saturday morning, not waited for Manny to point it out.

Lesson: when an infrastructure change closes a class of risks, revisit the directives that were written under the old assumption. The whole gate stack should be reconsidered through the "no overnight" lens — not just FCHL.

---

## Reports CC owes — refreshed

| When | Report | Status |
|---|---|---|
| Sun 5/17 or Mon AM | All 4 forensic investigations (parallel) | per amendment |
| Mon EOD | Daily breakdown with force-exit firing as primary validation focus | new emphasis |
| Mon EOD | Dead-tape historical backfill appended | required |
| Tue 5/19 | Synthesis + Monday-gates decision (including: does EH block need to come back?) | per amendment |
| Wk 1-3 | Standard daily breakdowns + L2 observe + paper data | per existing |
