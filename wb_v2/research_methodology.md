# WB v2 — Research Methodology

**Date:** 2026-05-18
**Stage:** 0 (research only — no bot code, no deployment)
**Author:** Cowork (per `DIRECTIVE_2026-05-18_WB_V2_STAGE_0.md`)
**Status:** Foundation document for Stage 1

---

## Purpose of this document

This is the **methodology mirror** for WB v2. It exists so that anyone — Manny, future Cowork sessions, future CC sessions, or a stranger picking up this repo — can read it and immediately see one thing:

> **WB v2 is squeeze v1's playbook re-applied to a different setup author.**

Squeeze v1 took Ross Cameron's discretionary description of "volume spike + level break, ride to 2R" and walked it through a specific sequence of stages — tick audit, setup tagging, filter discovery, backtest, paper validation, live cutover — until it became a deployable strategy. WB v2 does the same thing to Manny's own discretionary description of his fluctuation-hunting trades.

The strategy author changes. The methodology does not.

This document is the foundation for Stage 1. It is **not** a final specification of WB v2. It defines *how we explore*, not *what we will deploy*.

---

## Philosophy: exploration is the methodology

The single most important framing to internalize before reading the rest of this doc:

> **Exploration is the methodology. It is not a deviation from the methodology.**

Squeeze v1 did not arrive fully-formed. Initial backtests of Ross's stated setup pointed in directions that didn't pan out. We followed the data through dead ends — Ross exit v2, classifier-gated exits, MP-first hybrid configurations — and each "failure" tightened the eventual winner. That exploratory loop was not a detour. It was the work.

Manny, verbatim (2026-05-18, 1:33 AM MDT):

> "If there was an exact way to make this work, then everyone would be doing it. This is a journey of discovery and exploration."

WB v2 is the next door we are opening. If a backtest mid-Stage-1 opens yet another door, we walk through it. If it closes, we come back and try the next one. Future strategy iterations — WB v3, WB v4, whatever comes after — get the same **exploration license**. No apologies for paths that don't pan out. No retroactive narrative-fitting on the wins.

The playbook below is the rail this exploration runs on. The rail does not predict where the train stops. It just keeps the train from going into a ditch.

---

## Manny's setup, verbatim

This is the source material for WB v2. Every operationalization choice in Stage 1 must trace back to a phrase in this quote.

> "While I was watching what the squeeze bot was trading, I simply opened the chart on the stocks that had the most ticks that appeared in the tick audits.
>
> I noticed that the prices were always fluctuating. I simply just watched the chart, waited for the price to reach a level of support, and added when MACD was green near the bottom, and snipped profits when it was about halfway back up the wave.
>
> It didn't always work. Sometimes I lost. But I just kept doing that. Always on the stock that had the most ticks on the bot's tick audit.
>
> I also short the stock when it looks like the exact same setup but opposite. Nearing resistance, MACD crossing to red.
>
> Ride the fluctuation."

Three words capture the strategy: **ride the fluctuation.** Everything Stage 1 builds has to serve that.

---

## The methodology mirror (mandatory table)

| Stage | Squeeze v1 (Ross Cameron) | WB v2 (Manny) |
|---|---|---|
| **1. Setup description (source material)** | Ross's recorded recaps + interviews: "volume spike on the 1m, level break (PM high / whole dollar / PDH), enter on the break, ride to 2R, trail a runner." | Manny's verbatim (above): "support level + MACD green near a wave bottom, long; resistance + MACD red near a wave top, short. Halfway-back-up scalp on the dominant tick-rate name of the day." |
| **2. Data source** | Live tick audit logs from `bot_v3_hybrid.py` (the squeeze bot during live paper) + Databento historical bars + Ross's daily recap videos. | Live tick audit logs from the squeeze bot (`tick_cache/`, the audit files Manny was actually eyeballing) + a new Stage 1 forward-trade log Manny fills in real time + Manny's chart screenshots when available. |
| **3. Universe definition** | Scanner-filtered watchlist: gap %, float, PM volume, RVOL gates. The scanner picks; the bot reacts. | "Most active stocks of the day" — top-N by tick rate / dollar volume / RVOL / range, refreshed intra-session from the same tick audit. The universe selector is *itself* a research artifact (Deliverable 3 mines it). |
| **4. Setup tagging (manual phase)** | Side-by-side comparison of bot trades vs. Ross daily recap. Trade logs per stock catalog when the bot agreed with Ross, when it diverged, why. `trade_logs/` directory grew this taxonomy. | Trade-intake template (Deliverable 4) — Manny enters every WB v2 candidate trade he eyeballs, with free-text fields for level type, MACD state, exit reason. **No pre-committed taxonomy.** The taxonomy emerges from the data. |
| **5. Operationalization candidates** | "Volume spike" → vol-mult of avg, with parameter sweep (2.0×, 2.5×, 3.0×). "Level break" → PM high, whole dollar, PDH, with toggles per level type. | "Level of support/resistance" → PDH/PDL, VWAP, anchored VWAP, pivots, round numbers, swing pivots, volume profile nodes. "MACD green near bottom" → histogram zero-cross, line/signal cross, histogram bottoming, with 12/26/9 and 5/13/5 variants. (Enumerated in Deliverable 2.) |
| **6. Setup taxonomy** | Squeeze, micro-pullback, post-squeeze continuation. Each got its own detector module (`squeeze_detector.py`, `micro_pullback.py`, `continuation_detector.py`) once the manual phase showed enough signal. | First-pass seed (Deliverable 5): Wave-Reversal Long, Wave-Reversal Short. Sub-types (level type × wave depth × time of day × MACD variant) emerge from the Stage 1 trade log — same way squeeze's sub-types emerged from per-stock trade logs. |
| **7. Filter discovery** | Megatest sweeps over the candidate parameter space across multiple sessions (49 days for the megatest). Filters that consistently separate winners from losers survive. The classifier project (Phase 2) was a filter-discovery project that didn't ship — we learned the dynamic-scaling baseline was already doing the work. | Stage 1 backtest sweeps over the operationalization candidates (level type × MACD variant × universe selector × timeframe) on the tick-audit-extracted universe. Filters that walk-forward (test ≥ train) survive. Filters that overfit get discarded — same posture as squeeze. |
| **8. Backtest** | `simulate.py` with `--ticks` mode, 07:00–12:00 ET window, tick cache as data source. Regression targets pinned (VERO +$34,479, ROLR +$54,654). YTD backtests via `run_ytd_v2_backtest.py`. | Same harness — `simulate.py --ticks` against tick cache. **WB v2 entries plug into a separate handler; exits reuse the squeeze exit primitives.** New regression targets get pinned at Stage 1 close. |
| **9. Exit logic** | Built fresh during squeeze v1: dollar loss cap → hard stop → tiered max-loss → pre-target trail (1.5R) → target (2.0R, 75% partial → 90% in X01) → runner parabolic trail. V1 vs V2 vs V3 megatest confirmed mechanical V1 best. | **REUSE the squeeze exit stack as-is.** Manny explicitly called this out: *"the exit strategy we were already using was working wonderfully. The bot is good at detecting exits."* No new exit code. Documented in Deliverable 6 (exit-reuse audit). |
| **10. Sizing** | Fixed $-risk per trade, then graduated to risk-percent of equity with daily-loss-scaling. X01 tuning landed at 3.5% risk + 5 max attempts. | Fixed-dollar at start, conservative: $200/signal proposed for paper. Actual gate set at Stage 1 close, same playbook step as squeeze. |
| **11. Paper validation** | Squeeze paper-traded for weeks before live, on Alpaca paper account. P&L tracked daily; backtest-vs-paper divergence triaged (tick cache persistence gap was the big one). | WB v2 paper account stays **idle** until Stage 1 produces a deploy-eligible spec. When it does, paper runs on the dedicated WB paper Alpaca account until Manny signs off. |
| **12. Live cutover** | 2026-06-04 real-money deadline for squeeze v3. Paper-to-live gate: positive paper P&L over N sessions + backtest agreement + Manny-signed-off spec. | Same gate. No live cutover from this directive. Stage 1 only produces a *candidate spec*; live cutover is its own future directive. |

The right-hand column is the playbook. The left-hand column is the *proof the playbook works*. Squeeze v1 went the full distance — Ross's verbatim → live, real-money-imminent strategy. WB v2 is starting at row 1 of the same column.

---

## What is different about WB v2 (and why those differences are still on-rail)

A faithful methodology mirror has to acknowledge the places where the analog isn't 1:1. These differences are *parameter changes within the playbook*, not departures from it.

**Difference 1: Strategy author.** Ross is a public figure with hours of recorded recaps. Manny is the trader sitting next to us. The data-collection step is faster (no transcript mining) and more precise (we can ask follow-ups). The methodology step — turn a discretionary description into bot-translatable terms — is identical.

**Difference 2: The exit stack already exists.** Squeeze v1 had to build its exit primitives from scratch. WB v2 inherits them. This shortens the timeline by weeks but does not change the methodology — squeeze v1 *also* would have reused exits if they had existed. Reuse is a sequencing optimization, not a methodology change.

**Difference 3: Setup A is sacred.** Squeeze v1 was free to modify its own primary file (`bot_v3_hybrid.py`). WB v2 cannot. This means the WB v2 entry handler lives in a separate module under `wb_v2/` that **calls** the squeeze exit primitives as a read-only library. The methodology accommodates this constraint with no change in spirit.

**Difference 4: Exploration framing is now explicit.** Squeeze v1's exploration license was implicit — we just did the work and reported. WB v2 names it. This is a documentation upgrade, not a methodology change. Future iterations inherit the explicit framing.

---

## Stage 1 — what this methodology enables

This document is the foundation for Stage 1, not a substitute for it. Stage 1 will:

1. Backtest each `level × MACD-operationalization × universe-selector × timeframe` combination on the tick-audit-extracted universe.
2. Filter-discover: which combinations separate winners from losers, walk-forward.
3. Stage-gate: at least one combination with Sharpe ≥ 1.0 OOS, anti-overfit (test ≥ train), MaxDD bounded.
4. Produce a deploy-eligible spec for Manny review.

Stage 1 will follow this playbook even if the early backtests point somewhere unexpected. **Especially** if they point somewhere unexpected — that's where the squeeze v1 winners came from.

---

## Reading order for someone picking this up cold

1. This document (you are here).
2. `wb_v2/setup_taxonomy_seed.md` — first-pass setup tags from Manny's verbatim.
3. `wb_v2/operationalization_candidates.md` — candidate definitions for "level," "MACD," "most active." *(Deliverable 2; pending.)*
4. `wb_v2/tick_audit_universe_extraction.md` — the universe data mined from the squeeze bot's tick audits. *(Deliverable 3; pending.)*
5. `wb_v2/trade_intake_template.csv` — the forward-log Manny fills during Stage 1. *(Deliverable 4; pending.)*
6. `wb_v2/exit_reuse_audit.md` — which squeeze exit primitives WB v2 reuses, with file:line references. *(Deliverable 6; pending.)*

When all six land, the Stage 0 synthesis report triggers Manny review and the Stage 1 directive.

---

## Reminder, verbatim from Manny

> "Ride the fluctuation."

That's the strategy. This document is the rail the train runs on. The train still has to ride.
