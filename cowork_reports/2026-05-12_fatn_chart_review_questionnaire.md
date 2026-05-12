# FATN Chart Review — Chop Gate v3 Discovery Questionnaire

**Date:** 2026-05-12
**Author:** CC
**For:** Cowork (Perplexity)
**Trigger:** FATN today's stop-out (-$1,381) marks the 3rd losing trade on this single symbol in 5 sessions. Pattern is repeatable and our existing chop gate v2 isn't catching it.

**Attached (by Manny):** FATN intraday chart screenshot covering pre-market through ~12:00 ET on 2026-05-12.

---

## Why this symbol matters

FATN keeps generating a high-score WB arm, passing chop gate v2, getting filled, and stopping out within an hour. Manny looks at the chart and says it's "the exact kind of chart we should be avoiding" — visually obvious to a human, invisible to our current heuristic.

| Session | Outcome | P&L | R-mult | Notes |
|---|---|---:|---:|---|
| 2026-05-06 | LOSS | -$986 | -1.05R | thin small-cap, score=7. Triggered the choppy-stock-filter-P0 directive. |
| 2026-05-08 | LOSS | -$772 | -1.04R | score=10 CHOP_BYPASS, entry below VWAP, R% 1.47% post-fill |
| 2026-05-12 | LOSS | -$1,381 | -1.0R | score=8 normal-pass (not bypass), R% 1.35%, post-9 AM MT |

Three losses, ~$3,140 of paper P&L gone, three different scoring tiers. The strategy variable that ties them together isn't score — it's the **chart shape of FATN itself**.

---

## What the bot saw at today's entry

Engine WB bot, Setup B (PA-NEW account, $92K equity):

| Field | Value | Comment |
|---|---|---|
| Entry time | 2026-05-12 11:41 ET (09:41 MT) | post-9 AM MT (passes Hypothesis #14) |
| Symbol | FATN | |
| Score | 8 | normal pass, not chop-bypass tier |
| IBKR signal price | $3.62 | |
| Alpaca ask at signal | (stale — fallback engaged, used 1.0% safety buffer) | |
| Limit submitted | $3.66 | `[FALLBACK]` due to stale quote |
| Fill price | $3.62 | $0.04 of price improvement |
| Stop | $3.5711 | |
| R | $0.0489 | |
| R% | 1.35% (vs candidate ≥1.5% threshold) | **fails Hypothesis #10** |
| Notional | $49,999 | $50K cap binding |
| Risk | $2,311 | 2.5% of equity |
| Hold time | 19 minutes | entry 11:41 → stop_hit 12:00 |
| Exit | $3.52 fill (intended limit $3.07, market gave price improvement) | |

The arm-time wave history showed: 4 prior up-waves with magnitudes 1.7%-2.5%, 3 down-waves with scores 5-6 — a textbook WB pattern. **The detector did its job.** The chop gate didn't catch the deeper problem.

---

## What our current chop gate v2 already checks (per 2026-05-06 design)

For a WB arm to fire entry, all of the following must pass:
- `R / spread ≥ 1.5×` — stop distance must be at least 1.5× the bid-ask spread
- `VWAP_dist_pct ≥ +0.75%` — entry above session VWAP
- `5-bar avg_vol ≥ 2,500 shares` — recent participation
- `degenerate_bars (O=H=L=C) ≤ 2 of last 5` — no single-print bars dominating
- Score-bypass available at ≥9 (chop_bypass overrides the above)

FATN today: score=8 (no bypass), passed all 5 criteria. **Yet it lost cleanly.**

So v2 is necessary but not sufficient. Something else about FATN's chart is informative that we aren't extracting.

---

## Hypothesis for the questionnaire

There is a small set of **chart-shape features** that a human eye picks up in a single glance — pattern recognition that's been built up across thousands of small-cap charts — that we haven't yet codified. This questionnaire is designed to extract those features from Perplexity's view of the attached chart so we can compute them from tick data and add them to chop gate v3.

Examples we've brainstormed but haven't confirmed:
- **Failed HOD attempts** — how many times has FATN tested its HOD today and rejected back? (Bot tracks HOD value but not the rejection count.)
- **Sideways range tightness** — bars compressed within a narrow band over N minutes (no momentum to ride).
- **Long wicks / indecision bodies** — wicks longer than bodies = rejection at both ends.
- **Time-since-last-HOD** — minutes since the symbol last printed at or above HOD. The longer, the more "dead."
- **VWAP slope flat-or-negative** — bot checks VWAP-distance but not VWAP-trajectory.
- **Spread-to-price ratio** — separate from R/spread, just the raw spread width as a % of price.

We don't know which (if any) of those is the dominant cue. Cowork's chart-reading view is.

---

## Questions for Cowork

### Q1 — Visual no-trade cues

Looking at the attached FATN chart (pre-market through entry at 09:41 MT and stop-out at 10:00 MT):

**What are the 3-5 specific visual features that immediately tell you this is a "thin chop, do not enter" setup?** Be as concrete as possible — point to bar shapes, level interactions, volume profile, anything observable in the chart.

### Q2 — Map each cue to a computable metric

For each cue you named in Q1, propose a metric we could compute from our tick cache (`tick_cache/<date>/FATN.json.gz` — per-tick `{price, size, ts}`):

Example template:
- Cue: "stock has tried HOD 4 times today and failed every time"
- Metric: `count of bars where high ≥ session_HOD × 0.99 AND next 3 bars closed below that high`

Aim for metrics that:
- Are deterministic from tick data (no human judgment needed at runtime)
- Have an obvious threshold (binary or single-number cutoff)
- Don't rely on data we don't already have (no L2, no fundamentals beyond float)

### Q3 — Threshold calibration (FATN-loser vs SST-winner)

We have a clean comparison pair:
- **FATN 2026-05-12 09:41 MT** — score=8, LOSER. The chart you're reviewing.
- **SST 2026-05-11 12:18 MT** — score=9, **WINNER +$2,090 / +3.28R**. Similar price tier (~$3.83 entry), similar R% (~2%), similar small-cap profile.

For each metric you propose in Q2, what threshold would have:
- (a) Rejected today's FATN setup, AND
- (b) Allowed yesterday's SST winner to fire?

If a metric can't separate these two cleanly, it's not informative — please mark it as such.

We'll provide SST tick cache data if useful: `tick_cache_alpaca/2026-05-11/SST.json.gz`.

### Q4 — Composite gate logic

Should chop gate v3 require **all** new features to pass, or **any N of M**? Our current v2 is all-required (AND logic). Some patterns are strict pass/fail; others might be majority-vote.

Specifically:
- Are any of the new features so high-signal that one alone is enough to veto?
- Are others useful but only as part of a basket?

### Q5 — Cross-session memory

Across 5/6, 5/8, and 5/12, FATN has been a loser on three different scoring tiers. That suggests a **per-symbol memory** beyond a single session.

Hypothesis: "Any symbol with ≥3 losses in the trailing 10 sessions is auto-blacklisted for the next 5 sessions."

Risks of this:
- Auto-blacklist might miss a setup-quality change (a stock that was chop yesterday might be a clean breakout today).
- Small-cap watchlist turnover is high; cross-session memory might rarely activate.

**Does this rule make sense to you?** If so, what window and threshold? If not, what's a better long-memory mechanism?

### Q6 — Anything else

Open-ended: what else jumps out from the chart that we haven't named? Even features we don't currently compute might be worth adding to our tick-cache extraction if they're load-bearing.

---

## Deliverable format we'd find most actionable

A markdown response with:
1. The 3-5 cues from Q1, ranked by your confidence
2. For each cue, the metric definition (Q2) + threshold (Q3)
3. The composite-gate proposal (Q4) — explicit logic
4. Yes/no on cross-session blacklist (Q5) with parameter recommendation
5. Anything from Q6

We'll wire whatever you propose into a `chop_gate_v3` env-gated module, paper-test for 5 sessions, then promote if the WR delta is positive.

---

## Supporting files

- This questionnaire: `cowork_reports/2026-05-12_fatn_chart_review_questionnaire.md`
- Original chop gate v2 design: `cowork_reports/2026-05-06_morning_choppy_stock_analysis.md`
- Project memory: `project_choppy_stock_filter_p0.md`
- FATN 5/8 trade detail (LOSS -$772): `cowork_reports/daily_trades/2026-05-08_trade_breakdown.md` (Trade #2)
- FATN 5/12 tick cache: `tick_cache/2026-05-12/FATN.json.gz` (will be in repo after EOD push)
- SST 5/11 winner detail (for Q3 comparison): `cowork_reports/daily_trades/2026-05-11_trade_breakdown.md`

---

*The bot can't see what your eye sees. This questionnaire is the bridge from visual pattern recognition to computable features. Your answers become the chop gate v3 spec.*
