# WB v2 Stage 0 — Fluctuation-Hunter Research

**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Author:** Cowork (per Manny direction, Mon 1:33–1:38 AM MDT)
**Status:** GO — research-only stage, no deployment

---

## Philosophy (read this first)

**Exploration is the methodology. It is not a deviation from the methodology.**

WB v1 started from Manny's discretionary description. Initial backtests pointed in a different direction; we explored it honestly, and it didn't pay off. That was not a mistake. That was the work.

Manny: *"If there was an exact way to make this work, then everyone would be doing it. This is a journey of discovery and exploration."*

WB v2 is another door. If a future backtest opens yet another door, we walk through it. If it closes, we come back and try another. **Future iterations of WB get the same exploration license — no apologies for paths that don't pan out.**

---

## What WB v2 is

A strategy reverse-engineered from how Manny actually trades, using the same playbook we used to turn Ross Cameron's discretionary squeeze setup into the squeeze bot. **Not** an attempt to encode Manny's intuition. **Not** a hybrid bot/human function.

Manny in his own words (1:33 AM MDT):

> "While I was watching what the squeeze bot was trading, I simply opened the chart on the stocks that had the most ticks that appeared in the tick audits.
>
> I noticed that the prices were always fluctuating. I simply just watched the chart, waited for the price to reach a level of support, and added when MACD was green near the bottom, and snipped profits when it was about halfway back up the wave.
>
> It didn't always work. Sometimes I lost. But I just kept doing that. Always on the stock that had the most ticks on the bot's tick audit.
>
> I also short the stock when it looks like the exact same setup but opposite. Nearing resistance, MACD crossing to red.
>
> Ride the fluctuation."

That's the strategy. Hunt the most active stocks of the day, wait for fluctuation extremes, ride the move back toward the middle.

---

## The setup, in bot-translatable terms

| Element | Description |
|---|---|
| **Universe** | "Most active stocks of the day" — top-N by tick activity / volume / RVOL, refreshed intra-session. Defined dynamically, not from a watchlist. |
| **Chart timeframe** | **1m primary** (Manny's actual usage). 5m to be tested in parallel as a secondary track. |
| **Long entry** | Price at a support level + MACD turning green near a wave low |
| **Short entry** | Price at a resistance level + MACD turning red near a wave high (mirror) |
| **Exit logic** | **REUSE THE EXISTING SQUEEZE EXIT STACK.** Manny: *"the exit strategy we were already using was working wonderfully. The bot is good at detecting exits."* No new exit code is built for WB v2. |
| **Position sizing** | Fixed-dollar at start, conservative (same playbook as squeeze v1). $200/signal proposed for paper validation; actual gate set during Stage 1. |
| **Hold style** | Intraday only. No overnights. Force-exit at 19:55 ET applies (already wired). |

---

## What "operationalization" needs to test

Manny's description has two phrases that need concrete bot equivalents. **CC's Stage 0 job is to enumerate candidates for each, not to pick one yet.**

### "Level of support / resistance"

Candidate definitions to test in Stage 1:
- Prior-day high/low (PDH/PDL)
- Intraday VWAP
- Anchored VWAP from session open
- Pivot points (classic / Fibonacci / Camarilla)
- Round-number levels ($1, $5, $10 increments by tier)
- Recent swing highs/lows on the 1m chart (n-bar fractals)
- Volume profile high-volume nodes (POC, VAH, VAL) — already partially built in framework Phase 2

CC compiles the candidate list with a one-line "what each represents" note. We pick the subset to backtest in Stage 1.

### "MACD green near bottom" / "MACD red near top"

Candidate operationalizations:
- MACD histogram crossing zero from below (long) / above (short)
- MACD line crossing signal line near a multi-bar low/high
- MACD histogram bottoming (consecutive bars of decreasing-magnitude negative) and turning
- Standard parameters (12/26/9) plus a faster variant (5/13/5) given 1m timeframe
- Combined with a "near a level" gate so the MACD signal doesn't fire mid-channel

CC compiles candidate list with default parameter set per candidate. Stage 1 backtest picks winners.

### "Most active stocks of the day"

This is the universe selector. Candidate definitions:
- Top-N by total dollar volume so far this session
- Top-N by tick rate (Manny's original trigger: he used the squeeze bot's tick audit)
- Top-N by RVOL (current volume / 30-day average at same time-of-day)
- Top-N by intraday range (high − low) / open
- A composite score combining 2-3 of the above

CC needs to pull the squeeze bot's existing tick-audit data to ground-truth what Manny saw when he was eyeballing this. That data is already on disk — no new collection needed.

---

## Stage 0 deliverables (this week, in parallel with engine framework Wave 4 paper)

CC produces these to set up Stage 1. **No new bot code yet, no live deployment.**

### Deliverable 1 — `wb_v2/research_methodology.md`

A methodology doc that explicitly maps:
- Squeeze v1 process (Ross's described setup → tick audit → setup tags → filter discovery → backtest → paper) **vs.**
- WB v2 process (Manny's described setup → tick-audit data + Stage 1 forward log → setup tags → filter discovery → backtest using existing exit stack → paper)

Reads as a methodology mirror, not code. Anyone reading it should see "this is squeeze v1's playbook re-applied."

### Deliverable 2 — `wb_v2/operationalization_candidates.md`

The three candidate-lists above (level definitions, MACD operationalizations, universe-selector definitions). Each candidate gets:
- A one-line description
- Default parameters
- Where it's already implemented in the codebase, if anywhere
- Backtestability: whether existing tick-cache / Databento data is sufficient, or whether new data is needed

### Deliverable 3 — `wb_v2/tick_audit_universe_extraction.md` and `wb_v2/extracted_universe.csv`

CC mines the existing squeeze bot tick audit logs for the past 30-60 sessions and produces a per-day "most active stocks" list using each candidate definition (volume / tick rate / RVOL / range / composite). This is the data Manny was eyeballing — we need it in tabular form to define the bot universe.

Output:
- `wb_v2/extracted_universe.csv` — date | symbol | volume_rank | tick_rate_rank | rvol_rank | range_rank | composite_score
- Markdown report describing the extraction, distributions, and notable patterns

### Deliverable 4 — `wb_v2/trade_intake_template.csv`

Columns Manny fills going forward to build the v2 trade log:
- timestamp_entry, timestamp_exit (ISO 8601 ET)
- symbol
- side (long / short)
- entry_price, exit_price
- size_shares, entry_dollars
- chart_timeframe (1m / 5m)
- level_type (free text — Manny describes the level he saw: "PDH", "VWAP reclaim", "$5 round level", "swing low at 09:42", etc.)
- macd_state (free text — "green crossing zero", "histogram bottomed", etc.)
- exit_reason (free text — "halfway back up", "stopped", "MACD rolled", etc.)
- screenshot_path (optional)
- notes (1 line)

The free-text fields are intentional — they let Manny describe what he saw without pre-committing to a taxonomy. CC clusters the taxonomy from the data in Stage 1.

### Deliverable 5 — `wb_v2/setup_taxonomy_seed.md`

Cowork's first-pass guess at the setup taxonomy based on Manny's description:
- **Wave-Reversal Long:** support level + MACD green near bottom
- **Wave-Reversal Short:** resistance level + MACD red near top

Possible sub-types to cluster from the trade log later:
- Level type (PDH/PDL vs VWAP vs swing pivot vs round-number)
- Wave depth (deep pullback vs shallow chop)
- Time of day (morning vs midday vs late session)

This is a discussion seed, not a final taxonomy. Manny edits or replaces.

### Deliverable 6 — `wb_v2/exit_reuse_audit.md`

CC documents which functions / modules from the squeeze bot's exit stack will be reused by WB v2, with file:line references:
- `force_exit.py` (already proven — limit-only, 19:55 force-flat)
- `sq_para_trail` exit logic (the parabolic trail Manny called out as "working wonderfully")
- `sq_target` exit logic
- Any other exit primitives the squeeze bot uses

This audit is read-only. **The squeeze bot's exit code is NOT modified.** WB v2 will *call* these primitives from a separate WB v2 entry handler.

---

## Stage 1 — what happens after Stage 0 lands (next week, pending Manny review)

NOT in scope for this directive, but Stage 0 is sized so Stage 1 can start cleanly:

- Backtest each combination (level × MACD operationalization × universe selector × timeframe) on tick-audit-extracted universe data
- Filter discovery: which combinations separate winners from losers, walk-forward
- Stage gate: at least one combination with Sharpe ≥1.0 OOS, anti-overfit (test > train), MaxDD bounded
- Paper deploy criteria documented and Manny-signed-off

---

## Hard constraints

- Setup A is sacred. No modifications to `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, engine bots, `squeeze_detector_v2.py`, `l2_signals.py`, `ibkr_feed.py`, `wb_persistence.py`, `wb_intraday_adder.py`. **Squeeze exit primitives are read-only references for WB v2.**
- Old WB stays at `WB_STRATEGY_ENABLED=0`. WB v2 is a new code path under `wb_v2/` directory.
- Branch: `v2-ibkr-migration` only.
- No live deployment from this directive. Stage 0 is research only.
- WB paper Alpaca account stays idle until Stage 1 produces a deploy-eligible spec.

---

## Account allocation (recap)

| Alpaca paper account | Strategy | Status |
|---|---|---|
| Squeeze paper | Squeeze v3 | LIVE — 6/15 real-money cutover unchanged |
| Engine paper | Healthy Fluctuation Framework (3 strategies + TieredSizer) | LIVE Monday 5/18 (this morning) |
| WB paper | WB v2 (fluctuation-hunter) | RESEARCH ONLY — not deployed until Stage 1 passes |

---

## CC work queue for WB v2 Stage 0

In priority order. Estimate: 2–4 hours of work; not gated on the engine deploy.

1. `wb_v2/research_methodology.md`
2. `wb_v2/operationalization_candidates.md`
3. `wb_v2/tick_audit_universe_extraction.md` + `wb_v2/extracted_universe.csv`
4. `wb_v2/trade_intake_template.csv`
5. `wb_v2/setup_taxonomy_seed.md`
6. `wb_v2/exit_reuse_audit.md`

When all six land, post a Stage 0 synthesis report:

`cowork_reports/2026-05-1?_wb_v2_stage0_synthesis.md`

That synthesis triggers Manny review and the Stage 1 directive.

---

## Reminder (verbatim from Manny)

> "Ride the fluctuation."

That's the strategy in three words. Everything in this directive serves that.

GO.
