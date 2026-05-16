# Loser Forensic — Amendment: Compress Timeline

**Date:** 2026-05-16
**Author:** Cowork (Perplexity)
**For:** CC
**Amends:** `DIRECTIVE_2026-05-16_LOSER_FORENSIC.md`
**Trigger:** Manny correctly flagged that the 5-day-per-investigation pacing is wrong — we already have a full week of WB trades plus prior-week data. These are retrospective analyses, not live experiments.

---

## What changes

The investigations 1-4 use **only historical data** (`tick_cache/`, `logs/`, the CC audit reports). They don't depend on live market hours. CC can run them in parallel, not sequentially, and they should land in **1-2 days total**, not a week.

Investigation 5 (universe widening) was already flagged as conditional and will need historical data sourcing (Databento/Polygon for non-watchlist symbols) — that one has real wall-clock cost.

---

## Revised sequencing

### Sunday 5/17 OR Monday 5/18 morning

CC works Investigations 1-4 in any order they prefer. All produce findings reports based on existing log + tick_cache data.

- **Investigation 1** (squeeze re-entry forensic): N-attempt buckets, win-rate analysis. ~2-3 hours.
- **Investigation 2** (WB loser behavioral profile): 11-bar windows + feature extraction. ~3-4 hours.
- **Investigation 3** (stop-hit reverse analysis): bar-by-bar unrealized R walkthrough. ~2 hours.
- **Investigation 4** (winner template): 11-bar windows for the 5 winners + shared-feature analysis. ~2-3 hours.

Total: ~half a day to a day of focused work. Could feasibly all land before Monday open.

### Monday 5/18 EOD

All four reports in. Plus the Monday production checklist (dead-tape historical backfill, L2 first verdicts, force-exit timing, dead_bounce enforce, EH block). The production work needs live market hours; the diagnostic work does not.

### Tuesday 5/19

Synthesis. **Based on Monday's findings + production data, decide what gates to ship for the rest of the paper week.** This is the strategic decision point, not Friday.

### Wednesday-Friday 5/20-22

A/B paper data on whatever new gates ship. Investigation 5 (universe widening) starts in parallel if Investigation 4 produced a usable template.

### Week 2 (5/26-30)

Paper data validates whatever shipped in week 1. Universe widening completes if Investigation 5 pursued. Real-money posture firms up.

### Week 3 (6/2-6)

Final A/B confirmations. Real-money posture locks.

### June 15

Cutover.

---

## What this changes about the calendar

| Old timeline (from `LOSER_FORENSIC.md`) | New timeline |
|---|---|
| Mon: Investigation 1 | Sun-Mon morning: Investigations 1-4 (parallel) |
| Tue: Investigation 2 | Mon EOD: All 4 reports in |
| Wed: Investigation 3 | Tue: synthesis + new-gate decisions |
| Thu: Investigation 4 | Wed-Fri: paper data on new gates + Inv 5 |
| Fri: synthesis | Wk 2-3: validation + Inv 5 + real-money decision |

We gain 4 days of useful paper-test runway by not waiting on the analysis.

---

## What still needs live market time

These don't compress:

1. **Dead-tape historical backfill** — needs Monday morning before market open (CC has to query historical tick_cache, which is local; this could even run Sunday)
2. **L2 first verdicts** — needs market open (Monday)
3. **Force-exit at 19:55 ET firing** — needs an EOD session (Monday)
4. **FCHL fix on real overnight position** — needs an actual overnight (Monday into Tuesday)
5. **Paper data on new gates** — needs market sessions to generate trades

So the production validations still take their normal calendar time. Only the forensics compress.

---

## What I should have said the first time

The earlier directive treated investigations as something that needed live runway. That was sloppy framing. **The forensics are pure analysis on already-collected data.** They could have run anytime in the past week. Running them now and getting answers before Tuesday is the correct sequencing.

Apologies for the wasted scoping in the original. CC can ignore the day-by-day cadence in `LOSER_FORENSIC.md` §"Sequencing and parallel work" and use the revised timeline above instead.

Everything else in `LOSER_FORENSIC.md` stays — hypotheses, methods, falsification criteria, output formats, acceptance criteria are unchanged.

---

## Updated reports CC owes

| When | Report |
|---|---|
| Sun 5/17 OR Mon 5/18 morning | All 4 investigation reports (1, 2, 3, 4) |
| Mon EOD 5/18 | Daily breakdown with all Monday production sections (dead-tape, L2, force-exit, dead_bounce, EH block, attempts) |
| Tue 5/19 | Synthesis report + new-gate proposals + which gates ship Wed |
| Wed-Fri 5/20-22 | Daily breakdowns + paper data on shipped gates |
| Investigation 5 — start Tue or Wed | Conditional on Inv 4 producing a template |
| Fri 5/22 OR end of week 2 | Universe-widening report if Inv 5 pursued |

---

## Tone

Thanks for the catch. The right framing is: we have all the data we need to answer the strategic questions now. The bot's past decisions are sitting in tick_cache and logs. The only reason to wait is if the analysis itself takes time — and it doesn't.

CC: feel free to start Investigation 1 today (Sunday) if you have capacity. The compressed timeline gives us week 1 to actually act on findings instead of just collect them.
