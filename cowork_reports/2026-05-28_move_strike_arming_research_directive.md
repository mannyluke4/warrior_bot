# Research Directive: MOVE_STRIKE Arming — What Should Actually Wake the Sub-Bot?

**Date**: 2026-05-28 (afternoon)
**Owner**: Cowork (research-first; CC will only assist with data extraction and prototype implementation after Cowork lands a written verdict)
**Source**: Manny's manual MASK + ATPC scalp session today (2026-05-28, +$55,019 across 9 trades) on symbols the sub-bots were watching but did not enter. Today's sub-bot data shows only 7 ARMED events across 142 new-symbol subscriptions — a 5% arm rate that is leaving high-volatility moves on the table.
**Status**: Pure research. No code changes. Output is a written verdict + at most one prototype to A/B test in a future variant slot.

---

## Stated Problem

Manny's hypothesis: "The current scanner and watchlist for the move strikes are excellent. But the way the sub-bots arm on these positions is leaving better-complementary moves on the table." Today's MASK is the case study — a symbol where the bot was on the watchlist, ticks were flowing the entire morning, the price spent 2.5 hours rotating between $4.00 and $4.65 in a true firestorm (290 ticks/sec at peak), Manny scalped both sides for +$48K — and the sub-bot's MovementStrike detector did not arm until **12:19:43 @ $5.02**, after Manny's MASK book had already closed.

The MOVE_STRIKE arming criteria caught a *later, different* MASK setup (a breakout to fresh highs above $5). It missed the morning's bidirectional scalping range entirely.

Per Manny: "We can be catching better moves that complement what the move strike is actually designed for." The research is not "replace MOVE_STRIKE" — it's "understand what MOVE_STRIKE's edge is, then figure out whether a complementary arming signal would feed it better setups, *or* whether a parallel detector should run alongside it on the same tick stream."

---

## What I (CC) clarified about the current arming flow before writing this

1. **Universe**: The sub-bot's universe is identical to the main bot's scanner-driven watchlist. Main bot subscribes to symbols via `ibkr_scanner.py`, publishes ticks via the engine socket; sub-bot consumes whatever it sees. Manny is right that the scanner is doing its job — today the bot saw 142 unique symbols including the ones he traded manually.

2. **Arming**: The sub-bot's `MovementStrike` detector (`movement_strike.py`) runs INDEPENDENTLY on the sub-bot's own bar builder. It is NOT forwarded from the main bot — `engine_publisher.py` only publishes ticks, quotes, heartbeats, and subscription notices. No arm signal crosses the socket.

3. **What arming requires today**: MovementStrike triggers on bar-close evaluation; the detector requires a multi-bar lookback pattern (per `WB_BT_MOVE_LOOKBACK=5`, `WB_BT_MOVE_MULT=2.0`, `WB_BT_MOVE_STOP_LOOKBACK=10`). Today's `MASK ARMED entry=$5.02 stop=$4.90 R=$0.12 score=10.0` line says the detector wants a breakout-style structure — a recent high to break, a stop derived from a 10-bar low.

4. **Side**: All current sub-bot setups (MOVE_STRIKE, REGIME_SHIFT, REENTRY GREEN) are **LONG-ONLY**. Manny's MASK book was bidirectional.

5. **REGIME_SHIFT** has a separate detector keyed off body/baseline ratio (≥4×) and requires a prior MOVE_STRIKE arm on the symbol (`WB_REGIME_SHIFT_REQUIRE_ARMED=1`). So a regime_shift entry can never fire on a symbol MOVE_STRIKE never armed on — the universe of regime_shift candidates is a strict subset of the MOVE_STRIKE-armed universe. **This is a structural choke point that the research should examine.**

6. **REENTRY GREEN** triggers after a prior MOVE_STRIKE exit on the same symbol within 30 min — also a structural sub-domain of MOVE_STRIKE.

So the entire sub-bot pipeline pivots on what MovementStrike chooses to arm on. If MovementStrike's pattern is restrictive (and today's 5% arm rate suggests it is), every downstream setup inherits that restriction.

---

## Smoking-Gun Case Study: MASK 2026-05-28

| Time (ET) | Manny's trade | MASK price | Sub-bot status | Notes |
|-----------|---------------|------------|----------------|-------|
| 09:06 | Closed LONG -$25,607 | 4.65→4.36 | not armed | bot watching MASK since 02:00 |
| 09:40 | Closed SHORT +$25,607 | 4.36→4.07 | not armed | tick rate ramping |
| 09:41 | Closed LONG +$11,479 | 4.07→4.20 | not armed | |
| 09:46 | Closed SHORT +$11,914 | 4.21→4.09 | not armed | |
| 09:52 | Closed LONG -$6,014 | 4.16→4.10 | not armed | |
| 09:58 | Closed LONG +$16,878 | 4.19→4.36 | not armed | 290 ticks/sec firestorm window |
| 11:39 | Closed SHORT +$7,812 | 4.27→4.19 | not armed | |
| 12:13 | Closed SHORT +$5,594 | 4.30→4.24 | not armed | |
| **12:19:43** | — | $5.02 | **MASK ARMED** | bot's first arm — at price 30% higher than Manny's entire morning |
| 12:17 | Closed SHORT +$7,355 (ATPC) | — | — | different symbol |

**Total Manny on MASK: +$48,071 over 7 hours of bidirectional scalping. Sub-bot took zero MASK trades.**

The sub-bot was tracking MASK, processing every tick, building bars correctly (verified via `bar_stream/2026-05-28_subbot_A.jsonl`). What it *didn't* see was a "5-bar high break + 10-bar stop low" pattern in the $4.00-$4.65 range because the range was symmetric — MASK kept making fresh swing-highs and swing-lows on roughly the same boundaries. MovementStrike is calibrated for *directional breakout structure*, not *bidirectional range volatility*. The 12:19 arm fired only when MASK finally broke through $5.

---

## Research Questions

**Group A — What is MOVE_STRIKE's actual edge?**
1. Across the full YTD-sim trade set (`backtest_status/replay_subbot_YTD_v3_tickcache_universe_2026-01-02_2026-05-28.json`, 219 trades), what is the *post-arm price-action profile* of winning vs losing MOVE_STRIKE entries? Does the detector's structural-bias match where the wins come from?
2. Is there a tighter version of MovementStrike (e.g., requiring HOD break + prior-bar tick density + volume confirmation) that would have higher WR with fewer false arms?
3. Conversely, is there a *looser* version that would arm on the bidirectional-scalping setups Manny traded today?

**Group B — Are there complementary arming paths?**
4. Could a separate detector arm on **range-bound volatility** (high tick rate + tight intra-bar range + symmetric body distribution)? What would such a detector's entry/stop semantics look like — bracket orders straddling the range? Mean-reversion entries at range edges?
5. Could a **VWAP-touch reversion** detector arm on symbols where price keeps rejecting at VWAP from both sides? Today's MASK rotated around the 4.20-4.30 zone for hours.
6. Could a **micro-pullback-style** continuation detector arm faster on firestorm-class symbols (>100 ticks/sec) without requiring the full MovementStrike 5-bar lookback?

**Group C — Should the sub-bot trade short?**
7. The strategy is long-only. Manny's MASK book was 5L / 3S (the LONG side actually lost $14,521 net; the SHORT side won $62,592). If the sub-bot had a symmetric arming path, what would the YTD-sim look like?
8. What are the operational implications? Short-side requires `is_shortable()` checks (broker.py already has this for IBKR), HTB-list handling, separate stop semantics. Magnitude of work to add?

**Group D — Quantify the missed-firestorm gap**
9. For each YTD day with a tick_cache, generate the set of symbol-minutes where prior 1m bar had ≥6000 ticks (FIRESTORM bucket). For each, was the sub-bot armed at that minute? If not, why not (no MovementStrike trigger structure, max_per_symbol exhausted, etc.)?
10. Sort the missed firestorm minutes by subsequent 5m / 15m / 60m price travel. What would a "any firestorm bar → arm" detector have produced if backtested with MOVE_STRIKE-like entry/exit semantics?

**Group E — Interaction with shipped FIRESTORM gate**
11. The FIRESTORM gate (commit `c1cd28a`, shipping on Variant A tomorrow) is a NEGATIVE filter (block on quiet bars). Could a complementary POSITIVE trigger be derived from the same signal — "FIRESTORM_TRIGGER" arms on a bar that just crossed the 6000-tick threshold, independent of MovementStrike pattern? Implications for over-firing.

---

## Data Assets Available

| Asset | Purpose | Location |
|-------|---------|----------|
| Tick cache | Per-symbol minute-resolution tick lists, YTD | `tick_cache/<date>/<sym>.json.gz` (~101 days) |
| Bar streams (since 2026-05-28) | Per-bot per-symbol 1m bars with tick_count + first/last tick ts | `logs/bar_stream/<date>_<label>.jsonl` |
| Sub-bot daily logs | Every ARMED, EVERY ENTRY, every EXIT, every REENTRY WATCH | `logs/<date>_move_strike_subbot_<A\|B\|C>.log` |
| Sim-only YTD trade table | 219 trades across Jan-May, with entry time + symbol + setup + pnl | `backtest_status/replay_subbot_YTD_v3_tickcache_universe_2026-01-02_2026-05-28.json` |
| Manny's manual trade book today | Ground-truth example of what we *should* be catching | this conversation (paste) |
| Scanner_results | What the main bot's scanner picked daily (when populated) | `scanner_results/<date>.json` |
| Live A/B/C compare daily | Variant-level summary | `cowork_reports/<date>_abc_daily_report.md` |

---

## Suggested Research Phases

**Phase 1 — Anatomy of current arming (1-2 hrs)**
- Read `movement_strike.py` carefully. Document the exact arm criteria
  (lookback windows, body thresholds, score formula).
- Trace a single armed example end-to-end (e.g., today's MASK 12:19:43)
  showing each predicate the detector evaluated.
- Document the structural assumption: "this is a strategy that wants
  what shape of price action."

**Phase 2 — Quantify what gets missed (2-4 hrs)**
- Iterate over all `tick_cache/<date>/<sym>.json.gz` files for YTD.
- For each (symbol, minute) with a FIRESTORM bar (≥6000 ticks), check:
  - Was the sub-bot subscribed to this symbol at this minute?
  - Did MovementStrike arm on it within the next 5/10/30 min?
  - What was the subsequent 5m / 30m / 60m price range?
- Output: distribution of "missed firestorm" magnitudes. Is the total
  missed price-action large enough to matter, or are most firestorms
  symbols that DID get caught later?

**Phase 3 — Prototype alternative detectors (4-8 hrs, only if Phase 2 says signal exists)**
- Three sketch detectors, each backtest-able via the existing harness:
  - **FIRESTORM_TRIGGER**: arms on the bar that crosses the tick threshold.
  - **VWAP_ROTATION**: arms when N bars in a row have crossed VWAP in
    alternating directions.
  - **RANGE_VOLATILITY**: arms when N bars of high tick count have
    bodies < 25% of range AND total range > X%.
- Backtest each across YTD-sim. Report WR, P&L, overlap with current
  MOVE_STRIKE arms.

**Phase 4 — Bidirectional consideration (4 hrs, separate side-quest)**
- Audit `broker.py` and `move_strike_subbot.py` for what's needed to
  add short-side entries. Probably non-trivial: separate stop math,
  shortable-cache, HTB rejections, exit semantics inverted.
- Estimate: ship-or-defer based on Phase 2/3 magnitude.

**Phase 5 — Written verdict**
- Single cowork report:
  `cowork_reports/2026-MM-DD_move_strike_arming_research_verdict.md`.
- Sections: anatomy, missed-firestorm magnitude, prototype results,
  ship recommendation (with Variant slot proposal if applicable).
- Decision input for Manny: "should we ship X to Variant D / replace
  one of A/B/C?"

---

## What this directive does NOT include

- **No implementation in the research phase.** Phases 3-4 are sketch-and-backtest only. Live wiring happens (if at all) in a follow-up directive.
- **No new variant slot allocation.** The sub-bot live test is still A/B/C as of 2026-05-28. If Phase 5 says "ship," Manny will decide whether to displace a current variant or add a fourth account.
- **No scanner / watchlist changes.** Universe is treated as fixed. Manny is explicit that the scanner is fine.
- **No FIRESTORM-gate threshold tuning.** The 100/s default is locked for Variant A's live trial; tuning waits for that data.

---

## Cross-references

- `cowork_reports/2026-05-27_subbot_harness_rebuild_directive.md` — built the harness Phase 2/3 will use
- `cowork_reports/2026-05-28_firestorm_gate_impl_notes.md` — the gate that Phase 5 verdict will compose with
- `cowork_reports/2026-05-27_amss_regime_long_hold_audit.md` — case study where REGIME_SHIFT fired on a quiet consolidation; relevant to Group A
- `feedback_quiet_means_broken.md` — durable memory rule that motivates Group B/D
- Today's conversation contains: live-week 47-trade analysis, YTD-sim 219-trade analysis, MASK case study, Manny's 9-trade manual book

---

## Open questions for Manny before Cowork starts

1. **Time budget**: Are we ok with Cowork taking ~1-2 days on this? Phases 1-2 are tractable in a half-day; Phases 3-4 are the big chunks.
2. **Output preference**: Do you want one consolidated report at the end, or staged drops (Phase 1 verdict → Phase 2 data → Phase 3 prototypes)?
3. **Bidirectional priority**: Group C (add short side) is potentially the largest engineering lift. Does it stay in scope, or get split into its own directive?
4. **Constraint check**: Any setups you'd want explicitly *excluded* from consideration (e.g., martingale-style adds, no-stop strategies)? Standing rules already disallow market orders and broker stops — anything else?
