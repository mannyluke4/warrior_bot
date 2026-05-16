# Loser Forensic — Characterize What Made Losers Lose, What Made Winners Win

**Date:** 2026-05-16
**Author:** Cowork (Perplexity)
**For:** CC
**Context:** Manny clarified: go-live runway is ~30 days (June 15), not 20 (June 4). The strategic question is no longer "is the bot ready" but "are the losses avoidable and are the wins repeatable?" Stock-selection tuning is downstream — first we need the per-trade forensic.

---

## What this directive is

A diagnostic workstream, not a build. Five investigations, each producing a findings report. **No code changes yet** — the goal of this round is to characterize the data so that subsequent gate-design decisions are evidence-based.

CC works these investigations in priority order, alongside the Monday paper-validation work. The L2 / dead-tape / FCHL / dead_bounce validation directives from this morning are not paused; this work runs in parallel.

Each investigation has a hypothesis to test, a method, and a falsification criterion (what data would prove the hypothesis wrong).

---

## Why this matters

Three weeks of strategy work has produced one structural finding: **WB strips down to 19% win rate when manual / infra / overnight events are removed.** Squeeze has too few fills to characterize at all. We don't actually know:

- Whether the losers share a behavioral signature the gates could catch
- Whether the winners share a positive signature we could optimize toward
- Whether re-entries are systematically worse than first entries (Manny's specific hypothesis)
- Whether universe widening would surface more winners or just more chaff
- Whether the wins are repeatable patterns or one-off variance

We have 30 days. Five days minimum for the new gate stack to prove out in paper. That leaves ~25 days for diagnostic work to actually find the strategic answers, not just deploy more filters.

This directive is the diagnostic plan.

---

## Investigation 1 — Re-entry forensic (squeeze)

### Hypothesis
**Manny's thesis: re-entries on the same symbol are nearly always losers.** The first squeeze attempt on a symbol per day captures the cleanest setup; subsequent attempts are entering after the easy money has left.

### Falsification criterion
If win rate on Nth attempt (N≥2) is statistically similar to 1st-attempt win rate across the audit window plus Jan-Apr backtest, hypothesis is rejected.

### Method
1. Tag every squeeze fill (audit week + Jan-Apr) by ordinal attempt number on that symbol that day. First fill = N=1; next fill on same symbol same day = N=2; etc.
2. Compute per-N bucket:
   - Number of fills
   - Win rate
   - Average R-multiple
   - Average hold time
   - Average time-since-prior-attempt
3. Statistical test: 1st-attempt vs Nth-attempt win rate. If samples allow, use bootstrap CI on the difference.
4. Look at the specific transitions:
   - For each N≥2 fill: what was the outcome of N-1? (win/loss)
   - For each N=2 fill: how long after N=1 did N=2 happen?
   - For each loser N: was it at the same level as the prior attempt, or a new level?

### Specific data to extract
- SLE 5/15 sequence: SLE #1 (08:32 fill +$468), SLE #2 (09:19 fill −$247), SLE #3-9 (chase-cap saves). Was SLE #2 trying the same setup as #1 at a different level, or a fresh wave?
- ATRA 5/13 +$1,160 → no subsequent ATRA squeeze that day = N=1 only (clean test)
- LESL 5/15 first squeeze that day → loser. N=1 still lost.

### Falsifying evidence within the audit week
LESL 5/15 was N=1 and still lost (−$533). So "1st attempt = winner" isn't universally true. The hypothesis is "Nth attempt usually loses," not "1st attempt always wins."

### Output
`cowork_reports/2026-05-XX_squeeze_reentry_forensic.md` with:
- Per-N bucket table
- Per-event narrative for any N≥2 fill
- Statistical conclusion + sample-size caveat
- If hypothesis holds: proposed action (cap N=1 only, OR steeper attempt cap than the directive-3, OR time-based cooldown)

### Acceptance
A report Manny can read and either agree "yes, kill re-entries" or "no, the data doesn't say that." Either outcome is useful.

---

## Investigation 2 — WB loser behavioral profile

### Hypothesis
WB losers share visible behavioral signatures in the 5 bars before and after entry that distinguish them from winners. Specifically: losers enter on noise spikes that don't sustain; winners enter on moves with multi-bar confirmation.

### Falsification criterion
If the 5-bar pre/post-entry profile is statistically indistinguishable between winners and losers, hypothesis is rejected.

### Method
For each WB P&L fill in the audit week (16 fills, excluding FCHL/MEI/overnights):

1. **Pre-entry 5-bar window (bars -5 through -1):**
   - Volume distribution (mean, median, max)
   - Bar range (high-low) distribution
   - VWAP relationship (% bars above VWAP)
   - Price drift direction (slope of close prices)

2. **Entry bar (bar 0):**
   - Volume vs prior 20-bar avg
   - Bar range vs prior 20-bar avg
   - VWAP relationship at fill
   - Distance from HOD at fill

3. **Post-entry 5-bar window (bars +1 through +5):**
   - Volume vs entry bar
   - Cumulative move (% from entry close)
   - Number of bars above entry price
   - Max unrealized peak (% above entry)
   - Time to first bar below stop level

### Specific cuts to make
- **Winner template:** SST 5/11, MEI 5/13, ATRA 5/15 (and ATRA 5/8 from prior weeks)
- **Loser archetypes (cluster manually first):**
  - Penny-stock-pop losers: ENSC ×3, CLNN ×1 — sub-dollar names with sub-penny R
  - Mid-cap fade losers: ATRA 5/11, ATRA 5/12, FATN ×2, TRAW, ODYS — $2-15 range, faded after entry
  - Late-session losers: SLE 5/15 19:17, ATRA 5/11 18:30, ODYS 5/13 18:27 — EH entries
  - Wave-deep losers: ODYS 5/11 wave 90, ATRA 5/11 wave 82 — very deep wave counts

4. For each cluster, find one or two distinguishing features vs winners.

### Output
`cowork_reports/2026-05-XX_wb_loser_behavioral_profile.md` with:
- Per-trade 11-bar (5 pre + entry + 5 post) data table
- Cluster-level summary statistics
- Identified distinguishing features (if any)
- Proposed metric per distinguishing feature
- Falsification result if the features don't separate winners from losers

### What to look for specifically
- **One-print spike pattern (ATRA 5/15-style):** entry bar volume is N× prior bars, but bar +1 has near-zero volume. If this pattern is repeatable across losers, the dead-tape gate already catches it. But there may be a tighter variant — e.g., "entry bar vol > 5× yet next bar vol < 0.2× entry bar."
- **VWAP-reject pattern:** entry above VWAP, bar +1 closes back below VWAP. If common in losers, could be a 1-bar confirmation requirement before fill.
- **Range-collapse pattern:** entry on a wide-range bar, next 3 bars all narrow. Indicates exhaustion print.
- **Stop-distance pattern:** how far is the stop from entry as % of recent ATR? Losers may have tighter stops relative to volatility.

### Acceptance
At least one statistically supportable distinguishing feature, OR a clean "no feature distinguishes them" conclusion. Both are actionable.

---

## Investigation 3 — Stop-hit reverse-time analysis

### Hypothesis
Many losers had a positive-unrealized-P&L window before stopping out — if so, a quicker exit trigger (move-stop-to-BE faster, or partial-out at +0.5R) would convert losses to scratches.

### Falsification criterion
If most losers move from entry directly to stop without ever hitting +0.3R, hypothesis is rejected and the answer is "don't enter, not exit faster."

### Method
For each stop-hit WB loser (13 of them in audit week):

1. Walk bars from entry forward to stop-hit
2. Per bar, compute unrealized R-multiple based on bar close
3. Find: max unrealized R-multiple, time-to-max, time-from-max-to-stop
4. Bucket:
   - Direct-to-stop: never hit +0.3R
   - Bounce-then-fail: hit +0.3R to +0.8R, then reversed
   - Near-win-then-fail: hit +1.0R+, then reversed (these would have been winners with tighter exit)

### Specific cases to check
- ATRA 5/11 13:52 −$513 (7m hold, $8.47 → $8.33). Did it ever tag $8.55+ in those 7 minutes?
- LESL 5/15 16:53 −$735 (7m, $3.09 → $3.01). Bars between?
- ATRA 5/11 18:30 −$778 (13m, $9.49 → $9.20). Did EH have any bounce?

### Output
`cowork_reports/2026-05-XX_wb_stop_hit_reverse_analysis.md` with:
- Per-trade bar-by-bar table
- Bucket distribution: % direct-to-stop, % bounce-then-fail, % near-win
- For the near-win bucket: would BE-stop at +0.5R have saved them?
- Proposed exit improvement if applicable

### Acceptance
Either "exits would help" with concrete spec, or "exits don't help — entries are the problem" with clean evidence.

---

## Investigation 4 — Winner template construction

### Hypothesis
The historical winners (FATN 5/5, ATRA 5/8, SST 5/11, MEI 5/13, ATRA 5/15) share positive features distinct from the losers. If yes, we can score-boost for those features and bias entry toward winner-like setups.

### Method
1. For each historical winner, extract the same 11-bar profile as Investigation 2
2. Document the qualitative narrative:
   - What was the catalyst (if any)? Pre-market news, gap, sympathy move?
   - What was the day-context (top gainer, sympathy to broader move, isolated)?
   - What was the wave structure (specifically — were these all "post-pullback wave-30+" or all "wave-1 morning breakouts" or mixed)?
3. Identify candidate positive features:
   - VWAP behavior (sustained above VWAP for N bars)
   - Volume confirmation (entry bar vol > X AND next bar vol > 0.5 × entry)
   - HOD distance at fill
   - Day-range expansion (HOD-LOD > N% of prior day's range)
   - Pre-entry consolidation (last 10 bars in tight range before breakout)

### Critical question: are the winners actually similar to each other?
- FATN 5/5 +$1,074 (afternoon reclaim of HOD)
- ATRA 5/8 +$2,499 (massive 68% gap, momentum day)
- SST 5/11 +$2,090 (wave-60, mid-afternoon)
- MEI 5/13 +$1,006 (manual injection, late-day)
- ATRA 5/15 +$1,160 (thin-tape — the controversial one)

**If these 5 winners are dissimilar from each other, the strategy has no replicable positive pattern.** That would be a structural finding.

### Output
`cowork_reports/2026-05-XX_wb_winner_template.md` with:
- 11-bar profile per winner
- Qualitative narrative per winner
- Identified shared features (or honest "they don't share much")
- Proposed scoring boost per shared feature
- If they don't share features: explicit recommendation to retire WB or pivot strategy

### Acceptance
Either a template that can be back-tested, OR a clean conclusion that no template exists.

---

## Investigation 5 — Universe widening

### Hypothesis
The current WB watchlist (~30 symbols populated by squeeze scanner) is too narrow. A wider universe (top-200 gainers each day with volume > 1M, regardless of squeeze filter) would surface additional WB-style setups that the current scanner blocks.

### Method
This is harder and more expensive. Suggest deferring until Investigations 1-4 produce a winner template (Investigation 4 output).

When ready:
1. Pull historical bar data for top-200 gainers each day from Jan-Apr (Polygon or Databento)
2. Run the WB detector against each
3. Filter detector ARMs against the winner template from Investigation 4
4. Compute hypothetical P&L using the same exit logic (stop, trailing stop, force-exit)
5. Compare against actual scanner-fed WB P&L for the same period

### Output (if pursued)
`cowork_reports/2026-XX-XX_wb_universe_widening.md`

### Acceptance
Either a clear "wider universe produces more winners at acceptable false-positive rate" with concrete scanner relaxation spec, OR "the scanner is fine, the strategy is the problem."

### Scope flag
**This investigation depends on Investigation 4 producing a winner template.** If Investigation 4 returns "no template exists," Investigation 5 has no filtering criterion and is pointless. Treat as conditional.

---

## Sequencing and parallel work

| Day | Diagnostic work | Production work |
|---|---|---|
| Mon 5/18 | Investigation 1 (squeeze re-entry forensic) | All Monday actions from `DIRECTIVE_2026-05-16_WEEKEND_RESPONSE.md` |
| Tue 5/19 | Investigation 2 (WB loser behavioral profile) | Daily breakdown; L2 observe data review |
| Wed 5/20 | Investigation 3 (stop-hit reverse analysis) | Daily breakdown |
| Thu 5/21 | Investigation 4 (winner template) | Daily breakdown |
| Fri 5/22 | Synthesis report — what did we learn, what changes | 5-day L2 observe summary; squeeze fix 5-day eval |
| Wk 5/26+ | Investigation 5 (universe widening), CONDITIONAL on Inv 4 producing a template | Whatever the synthesis says |

This is one investigation per day. Each one is achievable in a day if scoped correctly. The reports are smaller than the directives we've been writing (a few thousand words, focused on data, not infrastructure).

**Critical:** these investigations operate ONLY on data we already have (logs, tick_cache, prior cowork reports). No new live experiments needed for Investigations 1-4. Investigation 5 needs historical data we may have via Databento or Polygon — confirm before starting.

---

## What the diagnostic week produces

Best case: Friday 5/22 we have:
- Squeeze re-entry hypothesis confirmed or rejected
- WB loser behavioral profile with 1-2 distinguishing features
- Stop-hit analysis saying "exits help by X" or "exits don't help"
- Winner template with 1-3 shared features OR clean "no template" conclusion
- New gate proposals based on findings, each with prior-week back-validation

Worst case: Friday 5/22 we have:
- Confirmation that there's no behavioral signature distinguishing winners from losers
- Confirmation that winners don't share features
- Clean evidence that the strategy as currently constituted has no edge

Both outcomes are valuable. The worst case is the cheapest possible discovery that we need a different strategy or to retire WB entirely.

---

## What I'm NOT directing in this round

- **Not** running Jan-Apr backtests yet. Investigation 5 covers that but only conditionally.
- **Not** modifying the WB detector code. The detector saw the trades it took; we're analyzing those decisions, not changing them.
- **Not** writing new gates yet. The investigations produce *proposed* gates; we decide which to ship after seeing all 5 reports.
- **Not** changing the go-live posture again. June 15 cutover. Investigations 1-4 should land before any final decision on whether WB ships at all.
- **Not** dropping the Monday production checklist. Both workstreams run in parallel.

---

## Output format guidance for CC

Each investigation report should follow a standard structure:

1. **Hypothesis (one paragraph, plain language)**
2. **Method (bullets, replicable steps)**
3. **Data table (the raw numbers — let the reader audit)**
4. **Findings (bullets, what the data shows)**
5. **Falsification check (was the hypothesis disproven? to what extent?)**
6. **Proposed action (if any, with confidence label — high/medium/low)**
7. **Limitations (sample size, selection bias, missing data — be honest)**

Avoid: long preambles, decorative tables that don't change conclusions, "next steps" lists. Keep it tight.

---

## June 15 readiness — updated posture

With ~30 days runway, the decision tree changes:

**By end of week 1 (5/22):**
- Investigations 1-4 done
- Monday-Friday paper data on new gate stack
- L2 observe week complete
- Decision: do we have evidence that WB has an edge?

**By end of week 2 (5/29):**
- Synthesis findings deployed as new gates or score boosts
- A/B paper week — old gate stack on one paper account, new on another
- 5-day comparison data

**By end of week 3 (6/5):**
- Real-money posture decision finalized
- If WB shows edge with new gates: ship to real money 6/15 (squeeze + WB both)
- If WB shows no edge: squeeze-only real money 6/15, WB retired or pivoted

**By 6/15:**
- Real-money go-live with whatever the data justifies

This is the calmer path. Three weeks of evidence-based investigation rather than 30 days of frantic shipping.

---

## Tone

Manny's framing is the right one: **stock selection is downstream of trade quality.** If we can't characterize what makes a winner a winner, no amount of scanner tuning matters. The diagnostic work this week is exactly what the bot project has been missing — careful, slow, evidence-driven analysis instead of layered protection mechanisms.

CC has produced consistently honest reports. The squeeze and WB audits this evening were good examples — surfacing the "WB only wins on accidents" finding takes guts. This diagnostic work is the natural follow-on: turn the honest negative finding into either a positive path forward or a clean retirement.

The runway is enough. Use it.

---

## Files referenced

- `cowork_reports/2026-05-16_squeeze_strategy_audit_weekly.md` (the audit this builds on)
- `cowork_reports/2026-05-16_wb_strategy_audit_weekly.md` (same)
- `cowork_reports/2026-05-16_dead_tape_gate_validation.md` (Monday backfill produces input data for Investigation 2)
- `tick_cache/<date>/<symbol>.json.gz` (the bar data source for all investigations)
- `logs/2026-05-XX_*.log` (the decision-time context — what the bot saw)

## Reports CC owes

| When | Report |
|---|---|
| Mon EOD 5/18 | Investigation 1 — squeeze re-entry forensic |
| Tue EOD 5/19 | Investigation 2 — WB loser behavioral profile |
| Wed EOD 5/20 | Investigation 3 — stop-hit reverse analysis |
| Thu EOD 5/21 | Investigation 4 — winner template |
| Fri EOD 5/22 | Synthesis report — proposed gate changes with evidence |
| Conditional | Investigation 5 — universe widening |

All in addition to the daily trade breakdowns and the Monday production validations.
