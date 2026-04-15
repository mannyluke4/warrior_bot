# HALT + requalify — BIRD autopsy + all downstream on Alpaca data

**Author:** Cowork (Opus)
**Date:** 2026-04-15 late evening
**For:** CC
**Type:** Stop-work + data-provenance audit + targeted re-run.
**Why:** Manny caught that today's BIRD backtest — and very likely everything downstream — was run on Alpaca historical ticks, not IBKR. Same failure mode as Friday 2026-04-10. Violates the standing rule: **IBKR for all data, Alpaca execution only, no silent Alpaca fallbacks.**

---

## What this invalidates until re-validated

Everything built on the BIRD 2026-04-15 number (`-$1,909`) or on canary replay numbers from today's autopsy:

- `2026-04-15_autopsy_bird_chop_day.md` — all three Q findings, including the ROLR T10 "disqualifying" result
- `2026-04-15_accept_bird_autopsy_no_code.md` — the "no code change" verdict may have been right *or* wrong, we don't know anymore
- `2026-04-15_design_dynamic_sq_attempts.md` — BIRD cited throughout as the motivating counter-example; the cumulative-R numbers driving the mechanism D recommendation came from Alpaca-sourced P&L
- `2026-04-15_completion_ytd_with_epl.md` — unclear if the runner pulled Alpaca or IBKR ticks; needs explicit verification

What is NOT invalidated:

- `simulate.py:1981` exclusion fix (directive 1 / commit `89e52c5`) — that's a structural bug, feed-agnostic. Stays landed.
- Session-resume work (`95bae57`, `7a9d0c9`) — that's live-bot machinery, orthogonal.
- The **structure** of the three follow-up directives (sim:1981 fix, dynamic SQ attempts, Path A YTD). The rationale for their *priority ordering* depends on what the IBKR re-run shows.

---

## Hard pause

**Do not proceed with:**
- Phase 2 prototype of dynamic SQ max_attempts (blocked on requalified BIRD number)
- YTD batch re-run with scanner_results regen + setup_type patch (blocked on tick-cache provenance audit)
- Any new directive derived from today's autopsy

Also hold on any continuation of Phase 2 design work citing BIRD numbers until step 3 below completes.

---

## What I need you to do

### Step 1 — Tick-cache provenance audit

For `tick_cache/` and `tick_cache_historical/` on disk:

1. Identify which subfolders / dates / symbols came from Alpaca vs IBKR. Look at headers, metadata, producer scripts, anything that makes feed origin unambiguous. If the files themselves are feed-agnostic (just `{t, p, v}` records), check:
   - Which script wrote them (git log for `cache_tick_data.py`, `ibkr_tick_fetcher.py`, any other producer)
   - Tick density / volume distribution — Alpaca and IBKR have different quirks (SPAC gaps, extended-hours coverage, micro-second vs second-level timestamps)
   - Any sidecar manifest files
2. Specifically verify: **what feed produced `tick_cache/2026-04-15/BIRD.json.gz`?** That's the file the autopsy's numbers came from.
3. Report a short table: which date ranges / symbols are IBKR-clean, which are Alpaca-tainted, which are unknown.

### Step 2 — Confirm today's autopsy data source

Go back through the autopsy's backtest commands. For each of BIRD 2026-04-15, VERO 2026-01-16, ROLR 2026-01-14, BATL 2026-01-26, MOVE 2026-01-23, ARLO: state explicitly what feed the ticks came from. If any came from Alpaca, flag it. If unclear, flag it.

### Step 3 — Re-run BIRD 2026-04-15 on confirmed-IBKR ticks

Use `ibkr_tick_fetcher.py` to pull fresh IBKR ticks for BIRD 2026-04-15, cache them to a clearly-named path (suggestion: `tick_cache_ibkr_verified/2026-04-15/BIRD.json.gz` or similar — don't overwrite the existing cache until provenance audit is done).

Re-run the same backtest command the autopsy used, with today's live config. Expected output:
- P&L for BIRD 2026-04-15 07:00-16:00 on IBKR ticks
- Trade-by-trade table (same format as autopsy)
- The key question: **does the $11→$20 afternoon leg get caught on IBKR ticks?** If IBKR has ticks Alpaca missed (or vice versa), that alone could change the T6/T7/T8/T9/T10 sequence and the cap-exhaustion timing.

### Step 4 — Re-run the autopsy's Q3 Path C canaries on IBKR

Same as step 3 for VERO 2026-01-16, ROLR 2026-01-14, BATL 2026-01-26, MOVE 2026-01-23, ARLO. If IBKR tick data doesn't exist for those historical dates, flag — that's its own problem and dictates whether the autopsy can be requalified at all or whether we need a different validation strategy.

### Step 5 — Delta report

At `cowork_reports/2026-04-16_requalified_bird_autopsy.md`:
- Per-symbol Alpaca-vs-IBKR P&L delta
- Whether the autopsy's three Q answers still hold
- Whether ROLR T10 is still "disqualifying" on IBKR ticks
- Recommendation: (a) autopsy conclusions stand → resume downstream directives as-is; (b) conclusions materially shift → Cowork rewrites directives from the new data.

---

## Hard rules

- **No Alpaca data anywhere in the re-run path.** Not even as a "we'll fill gaps with Alpaca" fallback. If IBKR is thin on a date, report the gap and stop — do NOT substitute.
- **No silent caching.** If you pull fresh IBKR ticks, the output path must be clearly labeled `_ibkr_verified` or equivalent so there's no future confusion.
- **No code changes to detectors, bot, or sim.** This is a data-provenance exercise.
- **No escalation of scope.** If provenance audit turns up other Alpaca-tainted datasets, list them and stop — don't start re-running everything unprompted.

---

## Meta — why this keeps happening

This is the second time in a week. Friday was the same failure mode and Manny flagged it then. Today's BIRD backtest fell into the same pit despite `feedback_ibkr_only_data.md` being the standing rule.

Going forward: **every backtest-producing directive Cowork writes from this point includes "IBKR ticks only, no Alpaca fallback" as an explicit hard rule in the directive body, not as an assumed standing order.** Cowork will enforce this on its own directives. CC: please read that line literally on every future directive — if the tick source isn't explicitly specified, stop and ask before running.

Updated memory entry: `feedback_alpaca_backtest_data_recurring.md`.

---

## What about the MBP sync work in flight

The MBP sync directive (Part 2 — push `warrior_manual`) is orthogonal and can proceed independently. Tick-cache / backtest work is separate from getting files onto the MBP. If you've already started step 1 of the MBP Part 2 directive, finish it. If not, you can pick either thread — they don't interfere.

---

*Cowork (Opus). Stop, audit, re-run on correct data, then decide. Don't build on a bad foundation twice.*
