# Directive — BIRD chop-day autopsy & YTD edge recovery

**Author:** Cowork (Opus)
**Date:** 2026-04-15 evening
**For:** CC (next iteration)
**Status:** Diagnostic-first directive. Zero code changes until the numbers justify them.
**Responding to:** `2026-04-15_report_fresh_day_backtest.md`

---

## The setup

Today BIRD ran $3 → $20 and the bot's backtest came out **-$1,909 / 10 trades (4W/6L)**. The morning was textbook (+$4,197 on the $3→$6 rip), then the bot gave it all back plus change trying to chase a second leg at $7-$11 and missed the $11→$20 blow-off entirely.

This is the best kind of day for finding edge: the data is there, the first leg proves the strategy works, and the failure is isolated to a specific sequence (T6–T10). Surgical opportunity.

**Goal:** understand *exactly* why the bot lost money on a day it should have made $10K+, quantify the fix across the 49-day YTD dataset, then — only then — ship a gated change.

---

## Ground rules (hard)

These are non-negotiable. Earlier iterations repeatedly slipped into them:

1. **No backtest fill-model changes.** Backtests test strategy, not order mechanics. If an idea requires "but the live bot wouldn't have filled that" to work, it's out of scope.
2. **No changes to the morning edge.** T1–T5 produced +$4,197. Any gate that degrades that sequence on BIRD, or degrades VERO (+$34,479) / ROLR (+$54,654) regressions, is rejected.
3. **No ungated changes.** Every candidate fix ships behind a `WB_*` env var default OFF. Today's config is what runs live tomorrow.
4. **YTD sign-off before code.** Any proposed gate must be validated across the 49-day YTD batch before I green-light implementation. N=1 BIRD is not enough.
5. **Don't touch simulate.py** unless the investigation specifically requires new instrumentation. `simulate.py` is shared with the regression path; behavior changes there put VERO/ROLR at risk.
6. **Don't re-run the BIRD backtest to "see if results changed."** The -$1,909 is deterministic with today's config. If you need to compare, introduce a single variable (e.g., one flag flipped) and diff.

---

## Investigation — three specific questions

### Q1: Why did the bot not catch the $11 → $20 final leg?

After T10 stopped out at 10:20, BIRD kept running to ~$20 intraday. The bot apparently never re-armed. Find out **exactly why**.

Possible causes to rule in/out:
- `WB_SQ_MAX_ATTEMPTS=5` already consumed (T1/T3/T5 all `sq_target_hit`, plus T6 `sq_stop_hit`, plus the MP-reentry logic on T8/T9/T10). Count the attempts against the squeeze cap specifically.
- Vol-baseline poisoned despite winsorize — check the 1m bar sequence on BIRD around 10:20–12:00 and confirm `avg_vol` stayed sane. This is the exact failure mode winsorize was supposed to prevent; if it recurred, that's a second directive.
- Stale-seed gate tripped on subsequent arms — log lines should show it.
- Trigger-level math (PM high, whole dollars, PDH) produced no breakable level between $11 and $20. Possible but surprising given round-number breaks at $12/$13/$14/$15.
- Exhaustion filter kicked in — for BIRD's intraday range this *should* have scaled up to permit re-entries (VERO logic), but confirm.

**Deliverable:** a single report section, `### Why BIRD didn't re-arm post-T10`, with the concrete mechanism identified (one of the above, or a new one) and the evidence from the sim log.

### Q2: Was the EPL MP re-entry on T10 correct behavior?

T8 and T9 were back-to-back losing `topping_wicky_exit_full` on BIRD within 16 minutes. T10 was an EPL MP re-entry that immediately stopped for -$3,005. Answer these:

- What event graduated BIRD into the EPL watchlist?
- Does EPL re-entry logic currently consider recent-trade outcomes on the same symbol, or only graduation?
- Is there a cooldown between EPL re-entries on the same symbol? How long?
- Was T10's arm on a different trigger (level / setup_type) than T8/T9, or the same one?

**Deliverable:** a flow trace of EPL decision-making for BIRD from graduation → T10, with file/line references.

### Q3: Would a "no re-entry after 2 consecutive losses on same symbol" gate help across YTD?

This is the CC-proposed gate from the backtest report. Before any code, **quantify the YTD impact**.

- Batch-run the 49-day YTD dataset with the gate simulated (via a simple post-hoc filter of the existing trade log, no code change needed for this step — just analyze `run_ytd_v2_backtest.py` output).
- Report: how many trades get filtered, aggregate P&L delta, per-symbol breakdown of the biggest wins and losses attributable to the filter.
- Specifically look for VERO cascading re-entries — those are the regression canary. If the gate filters a VERO cascade trade that went on to be a winner, the gate is wrong by construction.

**Deliverable:** a table of `(YTD P&L without gate, YTD P&L with gate, Δ, # trades filtered, # filter-decisions-that-would-have-saved-money, # filter-decisions-that-would-have-blocked-a-winner)`, plus a per-symbol breakdown for any symbol with Δ > $500.

---

## Parameters to hold constant

During this investigation, do not change:
- Any X01 tuning values (`WB_SQ_VOL_MULT=2.5`, `WB_SQ_MAX_ATTEMPTS=5`, `WB_SQ_TARGET_R=1.5`, `WB_SQ_CORE_PCT=90`, `WB_RISK_PCT=0.035`)
- `WB_SQ_VOL_WINSORIZE_ENABLED=1` / `WB_SQ_VOL_WINSORIZE_CAP=5.0`
- `WB_SQ_SEED_STALE_GATE_ENABLED=1` / `WB_SQ_SEED_STALE_PCT=2.0`
- `WB_EXHAUSTION_ENABLED=1`
- `WB_MP_ENABLED=1` in sim, `=0` in live (CLAUDE.md convention)

The `.env` is the control group. If an investigation step needs a flag flipped, flip it, record the diff, flip it back.

---

## Output

Single report: `cowork_reports/2026-04-15_autopsy_bird_chop_day.md`

Sections:

1. **Q1 answer** — why no $11→$20 catch. Mechanism + evidence.
2. **Q2 answer** — EPL re-entry flow + T10 trace.
3. **Q3 answer** — YTD impact table.
4. **Recommendation** — one of:
   - `NO CODE CHANGE` — investigation resolved it diagnostically, root cause is something we already have a gate for and it just didn't fire right.
   - `PROTOTYPE GATE` — the data supports a specific gated feature. Include: proposed env var name, default value, exact trigger condition, expected YTD delta, regression risk assessment (VERO/ROLR/49-day).
   - `ESCALATE` — you found something unexpected that needs Cowork judgment before proceeding (e.g., winsorize didn't hold, EPL has a deeper design gap).
5. **Non-findings** — anything you ruled out and why. Helps prevent re-investigating next time a similar day comes up.

---

## What success looks like

A week from now, someone reads `2026-04-15_autopsy_bird_chop_day.md` and understands:
- Which specific mechanism caused the bot to lose on a winner-day
- Whether this is a recurring pattern or a one-off
- What the evidence says we should (or shouldn't) change
- What we chose NOT to change and why

If the data says "no change," that's a successful outcome. The goal is precision, not motion.

---

## Scope boundary

This directive is autopsy + YTD analysis only. Prototyping, implementation, testing, and live deployment of any gate is a **separate directive** that Cowork will write *after* reading the report and approving the recommendation.

Do not write code that modifies `bot_v3_hybrid.py`, `squeeze_detector.py`, `epl_framework.py`, `epl_mp_reentry.py`, `trade_manager.py`, or `micro_pullback.py`. New analysis scripts under `tools/` or `scripts/` are fine if you need them.

---

*Cowork (Opus), 2026-04-15 evening. Surgical — measure twice, cut once. The bot made money on the morning; find out what it took back in the afternoon and why.*
