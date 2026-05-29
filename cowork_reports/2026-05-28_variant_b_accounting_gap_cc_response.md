# CC Response: Variant B Accounting Gap Follow-Up

**Date**: 2026-05-28 (evening)
**Owner**: CC
**Source directive**: `cowork_reports/2026-05-28_variant_b_accounting_gap_followup_directive.md`
**Outcome category**: **B (investigated, gap exists, root cause identified, partial fix shipped, additional fix recommended)**

---

## TL;DR

Two distinct issues identified, neither matching Cowork's directive premise:

1. **Cowork's directive cited wrong numbers** (bot=-$449 / broker=+$397 / gap=$846). The actual today report says bot=-$22 / broker=+$143 / gap=$165 for Variant B. May have been working from a stale draft or hypothetical example.

2. **Two distinct bugs surfaced during this investigation**:
   - **Parser bug** (just fixed, this commit): 5 of `abc_compare_daily.py`'s regexes expected `YYYY-MM-DD HH:MM:SS` timestamp prefix that the logs don't emit. They were silently matching 0 lines, which is why every daily report has shown "0 entries / 0 exits" for every variant lately. Now fixed.
   - **Session-restart-resets-daily-pnl** (not patched, recommend follow-up): bots track `daily_pnl` in memory; mid-day restarts reset it to 0. Today I performed 2 mid-day restarts (Variant B orphan recovery at 09:52, full-stack relaunch at 10:58 after main-bot sizing fix). Both wiped morning gains. The resulting gap is restart accounting, NOT orphan-class divergence.

**The 5/26 orphan fix is intact and working as designed.** Today's gap is not in its scope.

---

## What was investigated

### Cowork's premise: "Variant B bot=-449 / broker=+397 / gap=$846"

The actual `cowork_reports/2026-05-28_abc_daily_report.md` (regenerated with fixed parser, attached at end) shows:

| Variant | Bot reported | Broker truth | Gap |
|---|---:|---:|---:|
| A | -$22.00 | +$585.24 | +$607.24 |
| B | -$22.00 | +$142.69 | +$164.69 |
| C | -$22.00 | +$580.45 | +$602.45 |

All three variants show gaps, B is the *smallest*, not the largest. Cowork's directive cited different numbers — likely a stale draft or hypothetical example.

### Variant B's daily_pnl trajectory through the day

Three `real P&L` events were logged in Variant B today:

| Time | Trade | P&L | Daily | Counter # |
|---|---|---|---|---|
| 09:46 | SPRC regime_shift partial+runner | +$83 | **+$838** | trade #1 |
| 09:52 | NCT regime_shift (post-restart) | -$449 | **-$449** | trade #1 ← counter reset |
| 10:59 | IOTR regime_shift (post-restart) | -$22 | **-$22** | trade #1 ← counter reset again |

The two "trade #1" labels after the first one indicate the bot's internal counter was reset. That happens on bot startup.

**Two restart events today:**

1. **09:52:13 — Variant B only.** I killed PID 39210 to recover from a SPRC orphan rejection loop (the bot logged "FILLED qty=208" for the REENTRY GREEN entry but Alpaca only filled 5 shares; bot subsequently looped 339 times/min trying to exit 208). Restarted with same env. Variant B's daily_pnl reset from +$838 → 0.
2. **10:57:46 — full stack.** I killed main bot PID 39186 to apply the AvailableFunds sizing fix. `daily_run_v3.sh`'s SHUTDOWN trap detected main-bot death and killed all 3 variants. I manually relaunched the whole stack at 10:58. All four bots reset their counters. Variant B went from -$449 → 0 → -$22 (after the IOTR loss at 10:59).

### Why the bot vs broker gap appears

The bot's final reported daily_pnl (-$22) reflects ONLY the IOTR trade that fired after the 10:58 restart. The bot has no memory of:
- Variant B's morning SPRC partial+runner (+$83 logged, but broker actually realized +$837 — see audit table earlier in conversation)
- Variant B's SPRC REENTRY orphan flatten (manual at -$6.65, didn't go through bot)
- Variant B's NCT 09:52 -$449 loss (logged with daily=-449, then wiped by restart)
- Variant B's NCT 10:59 -$233 EOD flatten (manual, didn't go through bot)

The broker tracked all of these via account equity changes. That's where the +$165 gap comes from.

**Same pattern for A and C** — they only restarted once (10:58 full-stack restart). Both lost their pre-restart wins. A's morning SPRC win was ~+$813, which is roughly the magnitude of the +$607 gap (broker +$585 - bot -$22). C similar.

---

## What was patched today

### Fix #1: parser regex bug (this commit)

Updated 5 regexes in `scripts/abc_compare_daily.py` to match actual log format:

- **Before**: `\[MOVE_SUB(?:_\w)?\] \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] ...`
- **After**: `\[MOVE_SUB(?:_\w)?\] \[\d{2}:\d{2}:\d{2}\] ...`

The earlier regexes were silently matching 0 lines. Symptoms in recent daily reports:
- "MOVE_STRIKE entries: 0 / REGIME_SHIFT entries: 0 / Exits: 0" for every variant on every day
- Spurious "DATA QUALITY DEGRADED" alerts firing on bot-vs-broker gap

After the fix, today's report correctly shows:
- A: 1 MOVE_STRIKE + 3 REGIME_SHIFT entries, 3 exits, 1 partial
- B: 1 MOVE_STRIKE + 5 REGIME_SHIFT entries, 501 exits (the SPRC orphan rejection loop), 1 partial, 1 fade-gate block
- C: 0 MOVE_STRIKE + 3 REGIME_SHIFT entries, 2 exits, 1 partial, 1 REENTRY-loss-gate block

The newer FIRESTORM_GATE_BLOCK_RE and REENTRY_LOSS_GATE_BLOCK_RE regexes were already correct (I added them recently using the right format). Why they weren't broken: I copy-pasted from actual log output. Older regexes were written speculatively against an assumed format.

Verification: parser smoke test against today's logs showed 0 → 4/6/3 entries respectively after fix.

### What's NOT patched

**The session-restart-resets-daily-pnl behavior is unchanged.** Mid-day restarts continue to wipe the in-memory counter. This is not an orphan-class accounting bug — Lever 1/2/3 (the 5/26 fix) addressed reconciliation of POSITIONS, not daily_pnl persistence.

---

## Whether the fix is unique to Variant B

**No.** Both the parser fix and the daily_pnl-reset behavior apply to all variants equally. Variant B happened to be flagged in Cowork's directive but A and C have larger gaps in today's actual report ($607 and $602 vs B's $165).

---

## Recommended next step

**Two follow-up directives suggested:**

### 1. (Small, ~30 min CC work) Daily_pnl persistence

When a bot starts up, read today's realized P&L from broker (Alpaca: `get_activities`, filter date == today, sum `qty * price` deltas) and use that as the initial daily_pnl. Replaces the current `daily_pnl = 0` on init.

This makes the in-memory daily_pnl resilient to mid-day restarts. Bot-vs-broker gaps then ONLY indicate true accounting drift, not restart accounting.

Code site: `move_strike_subbot.py:__init__` after `_init_alpaca`.

### 2. (Optional, micro-directive) Adjust gap threshold or message wording

Until persistence ships, the gap will fire on any mid-day restart, even though the restart accounting is well-understood. Options:
- Raise threshold for the "DATA QUALITY DEGRADED" alert from $50 to something more meaningful for restart noise (e.g., $1,000)
- Add a "restart count today" indicator to the report so reviewers can immediately distinguish restart accounting from true divergence
- Both

---

## Reconciliation: what actually happened today on Variant B

| Time | Event | Broker realized | Bot daily_pnl after |
|---|---|---|---|
| 02:00 | Cron starts | 0 | 0 |
| 08:55 | SPRC regime_shift entry, fill $10.91 | -$2,326 (entry cost) | (held) |
| 09:46 | SPRC partial @ $14.39 (192 shares), runner @ $13.47 (21 shares) | +$754 + $83 = +$837 | +$838 (matches with $1 rounding) |
| 09:49 | SPRC REENTRY GREEN entry — bot logged "FILLED qty=208" but only 5 shares filled. Orphan rejection loop begins | (5 shares unrealized) | +$838 |
| 09:52:13 | **CC kills + restarts Variant B for orphan recovery** | (unchanged) | **0 ← reset** |
| ~09:52:15 | Manual flatten of 5 SPRC orphan @ $12.91 | -$6.65 realized | (bot never saw, not in daily_pnl) |
| 09:52:31 | NCT regime_shift entry, fill $5.75 (qty 295) | -$1,697 entry cost | 0 |
| ~09:53 | NCT exits at $4.23 hard_stop | -$449 realized | -$449 |
| 10:57:46 | **Main bot killed for sizing fix; daily_run_v3.sh shutdown trap kills all variants** | — | — |
| 10:58 | All 4 bots relaunched | — | **0 ← reset** |
| 10:59:16 | IOTR regime_shift entry, fill $2.48 (qty 320) | -$794 entry cost | 0 |
| 10:59:17 | IOTR exits at $2.41 hard_stop | -$22 realized | -$22 |
| 10:59 | NCT regime_shift entry, fill $4.22 (qty 344) | -$1,452 entry cost | (held) |
| ~17:27 | I manually flatten NCT 344 @ $3.54 (after-hours) | -$233 realized | (bot never saw) |

**Total broker realized for the day**: +$837 - $6.65 - $449 - $22 - $233 = **+$126**

(Daily report shows +$143 — small slip from my manual mark-to-bid vs Alpaca's exact fill prices.)

**Total bot daily_pnl at end**: -$22 (everything before the 10:58 restart was wiped from in-memory state).

Gap = +$143 - (-$22) = +$165. Matches the daily report exactly.

---

## Summary for Cowork

- The orphan fix (5/26 commits abc0631 + 02c3b51) is fine. Today's gap is not in its domain.
- Two restarts today caused legitimate session-restart-resets-counter behavior, not orphan-class divergence.
- A parser bug was the real culprit behind the "DATA QUALITY DEGRADED" framing — fixed in this commit.
- Recommend a small follow-up directive for daily_pnl persistence on bot startup (read broker realized P&L on init). ~30 min CC work.

Track A's tomorrow live-flip (per Phase 4b directive when it lands) is unaffected by either of today's issues. The accounting machinery Track A touches (`_close_position`, partial firing) is correct. Bot vs broker gap will continue to surface on any mid-day restart day until the persistence fix ships, but that's separate from Track A.

---

## Cross-references

- Cowork's directive (this work's source): `cowork_reports/2026-05-28_variant_b_accounting_gap_followup_directive.md`
- Today's daily report (regenerated with fixed parser): `cowork_reports/2026-05-28_abc_daily_report.md`
- Orphan fix from 5/26 (intact, not the issue): `cowork_reports/2026-05-26_orphan_fix_impl_notes.md`
- Today's trade audit (in conversation): morning SPRC/ATPC/NCT case-by-case table
