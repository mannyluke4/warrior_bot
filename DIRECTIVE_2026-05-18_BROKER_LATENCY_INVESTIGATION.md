# Broker Latency Investigation — Three Parallel Tracks

**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Author:** Cowork (per Manny direction, Mon 12:23 PM MDT)
**Status:** GO — investigation only, no production changes

---

## Why this directive exists

The Mon 12:09 PM max-chase audit definitively answered ONE question: for the 8 events that hit the chase-cap with `num_retries=2`, the first tick after submission was already past the limit on 6 of 8. Those 8 are unwinnable.

**It did not answer the question Manny actually has:**

> "Each retry attempt, the price is a bit higher. The bot found a good move, but just couldn't get in, and instead of riding the price up, we just see the price move up in the retry attempts. Ever since we switched back to Alpaca, we've been missing big moves that I am pretty sure Ross's recaps talk about him making big money on."

The audit explicitly flagged this gap (§4.3, §5.3, §8.3):
- "the pre-retry 'no fill in 10s' events (15+ in April 2026) are a separate failure mode... a fill-latency issue the chase-cap audit doesn't expose"
- "Latency analysis is INFERRED, not measured... A more rigorous audit would require timestamping at sub-second granularity"

We're going to measure, not speculate. Three parallel tracks; results converge into one decision document on broker stack.

**Squeeze 6/15 real-money cutover stays unchanged.** This investigation runs in parallel with squeeze paper validation and the engine framework Wave 4. Any broker migration decision happens **post-6/15** with real data on both sides.

---

## Track 1 — April 2026 single-shot timeout audit

### Question

For the ~15 single-shot "Entry order cancelled after 10s — no fill" events in April 2026 (pre-retry path), was the limit actually reachable but missed due to broker round-trip latency? This is the failure mode most likely to expose true broker-side latency.

### CC tasks

1. Identify all single-shot timeout events in April 2026 daily logs. Pattern: `"Entry order cancelled after 10s — no fill"` (without the chase-cap message).
2. For each event, walk the tick stream from ENTRY signal through 10s post-submit and capture:
   - First tick at or below `original_limit + $0.02`
   - First tick at or below `original_limit + $0.05`
   - First tick at or below `original_limit + $0.10`
   - Number of distinct ticks within reachable price band during the 10s window
   - Aggregate share volume traded at-or-below original limit during the window (proxy for whether a real broker could have filled our share count)
3. Classify each event:
   - **Fillable-at-limit:** tape traded at `original + $0.02` with sufficient volume → likely a true fill-latency miss
   - **Fillable-with-slippage:** tape traded within $0.10 with sufficient volume → likely a fill-latency miss with realistic slippage
   - **Unfillable:** tape never traded within $0.10 of limit during the window → not a broker problem, it's a vertical move
4. Counterfactual P&L for fillable events: walk forward from the simulated fill price using existing 2R target / stop logic, with adverse 0.5% slippage.
5. Output: `cowork_reports/2026-05-19_april_singleshot_timeout_audit.md` + `cowork_reports/2026-05-19_april_singleshot_simulations.csv`.

### Decision criteria the audit should report

- How many of the ~15 events fall in each classification bucket?
- Total counterfactual P&L of fillable events?
- Per-symbol breakdown (any names show up in Ross's public recaps for those dates? CC doesn't need to verify Ross's recaps; just flag if obvious symbols appear).
- Latency upper bound: what's the median time-to-first-fillable-tick across fillable events? If sub-second, the bot is clearly losing fills to broker round-trip. If multi-second, even a fast broker may not help.

### What this track does NOT do

- Does not modify production code.
- Does not propose a broker switch.
- Does not measure live latency (Track 2 does that).

---

## Track 2 — Sub-second order-path instrumentation

### Question

What is the actual distribution of submit → broker-ack → fill (or timeout) latency on Alpaca for live squeeze entries? Right now we have only inferred latency (`num_retries × 10s`). We need a real distribution.

### CC tasks

1. Add sub-second timestamping to the order submission path. Capture and persist:
   - `t_signal`: ENTRY_SIGNAL timestamp (already exists)
   - `t_submit`: pre-broker-API-call timestamp
   - `t_ack`: broker-ack received timestamp (Alpaca order acknowledged)
   - `t_first_status_change`: first status change after acknowledgment
   - `t_fill`: fill timestamp (if filled)
   - `t_timeout` or `t_chase_cap_abort`: timeout timestamp
   - `tick_at_t_submit`: best bid/ask/last at t_submit
   - `tick_at_t_ack`: best bid/ask/last at t_ack
   - `tick_at_t_fill_or_timeout`: best bid/ask/last at fill/timeout
2. Persist as `order_latency_records/<date>/<order_id>.json`. Append-only, never modify.
3. **Setup A constraint:** the instrumentation must be added in a way that does NOT modify `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `squeeze_detector_v2.py`, or any sacred file. Two acceptable patterns:
   - **Wrapper / decorator approach:** instrument the broker client class via a thin wrapper that lives in a NEW file (e.g., `instrumentation/order_latency_wrapper.py`) and is injected at bot start.
   - **Out-of-band log scraper:** if the broker SDK already emits the relevant lifecycle events to logs, parse them post-hoc into the persistent records. Lower fidelity but zero touch.
   - **CC chooses based on what's safest. If neither is feasible without touching a sacred file, CC pauses and reports back.**
4. Deploy instrumentation to the squeeze paper bots **only**. Engine framework already has its own logging; don't perturb the Wave 4 launch.
5. Let it run for 50-100 orders (likely 2-3 sessions of squeeze paper activity).
6. Output a Track 2 report once N≥50: `cowork_reports/2026-05-2?_alpaca_latency_distribution.md` with:
   - Median, P50, P90, P95, P99 of each latency component
   - Per-tier breakdown (premarket / regular / extended)
   - Histogram of t_signal → t_fill_or_timeout
   - Cross-tabulation: what fraction of timeouts had a tick at-or-below original_limit during the submit→timeout window? (This is the live-data version of Track 1's question.)
7. **Hard constraint:** no production decisions made until N≥50. Resist the temptation to read tea leaves on small samples.

### What this track does NOT do

- Does not modify any squeeze logic.
- Does not change order behavior. **Pure observability.**
- Does not test alternative brokers; that's Track 3.

---

## Track 3 — Lightspeed (and alternatives) API research

### Question

If Tracks 1 and 2 confirm a real broker-latency cost, is Lightspeed (or another low-latency execution broker) a viable migration target? What's the API maturity, paper environment, limit-only support, and migration friction?

### CC tasks

Pure research; no implementation.

1. **Lightspeed Trading** — evaluate their API stack:
   - REST/WebSocket/FIX availability
   - Documentation quality and recency
   - Paper trading / sandbox environment availability
   - Limit-only order support (we have a hard "no market orders" constraint)
   - Stop-order semantics (we have a hard "no broker stops" constraint — broker stops only, our soft stops at fill)
   - Reported median order-ack latency from public sources / forum posts
   - Symbol coverage for small-cap squeeze candidates ($2-$30, microfloat) — some prime-broker-style firms gate access to harder-to-borrow names; we trade those
   - Account minimums and pricing structure
   - Onboarding friction (margin agreement, KYC, time-to-account)
2. **Comparable alternatives** — produce 2-line summaries on:
   - DAS Trader Pro / DAS API
   - CenterPoint Securities
   - Cobra Trading
   - TradeStation (we already have notes from earlier in the project; refresh)
   - Webull (probably too retail; rule out quickly if so)
3. **Comparison matrix:** Alpaca vs. Lightspeed vs. top alternative on these axes:
   - Median ack latency (public estimates)
   - Limit-only support
   - No-broker-stops support
   - Paper environment
   - Small-cap symbol coverage
   - API maturity (REST + WebSocket + FIX availability)
   - Estimated migration effort (days)
   - Pricing per fill / per share
4. Output: `cowork_reports/2026-05-2?_broker_alternatives_research.md` + comparison matrix as CSV.

### Constraints the research must respect

- **No market orders** — anywhere we'd ever consider switching to.
- **No broker stops** — bot manages stops via soft-stop limit-order chains.
- **Limit-only execution** — non-negotiable.
- **Symbol coverage** — must support the squeeze universe (small-cap micro-float names).
- **Paper environment** — must exist; we don't deploy real-money on a broker we haven't paper-tested first.

### What this track does NOT do

- Does not start any migration work.
- Does not commit to any broker.
- Does not slip the **6/15 squeeze real-money cutover on Alpaca**.

---

## Convergence — the broker decision document

Once all three tracks have output, Cowork synthesizes into:

**`cowork_reports/2026-05-2?_broker_stack_decision.md`** — a single document with:
- Track 1 finding: real fill-latency cost in dollars over April 2026 sample
- Track 2 finding: live Alpaca latency distribution
- Track 3 finding: best-fit alternative broker with comparison matrix
- Cowork recommendation: stay on Alpaca / migrate to alternative / further investigation needed
- Migration plan if recommendation is to switch (timeline, paper validation period, real-money cutover)
- Manny decision required

**Decision happens post-6/15 squeeze real-money cutover.** Squeeze ships on Alpaca as planned. If the data says migrate, we migrate **after** the real-money squeeze stack is operational and documented.

---

## What's NOT in this directive

The other items from §8 of the max-chase audit:

- **§8.2 resume-boot stale-signal fix** — Manny pasted those recommendations to CC separately; that work is in flight.
- **§8.4 `WB_MIN_ABSOLUTE_R=$0.10` floor** — Manny pasted; CC should treat as a separate small-scope task.
- **§8.5 backtest tick-realism gate** — queued for later, not part of this directive.

---

## Hard constraints

- Setup A is sacred. No modifications to `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, engine bots, `squeeze_detector_v2.py`, `l2_signals.py`, `ibkr_feed.py`, `wb_persistence.py`, `wb_intraday_adder.py`. Track 2 instrumentation lives in a new wrapper file or out-of-band scraper.
- Branch: `v2-ibkr-migration` only.
- Squeeze 6/15 real-money cutover unchanged.
- Engine framework Wave 4 paper deploy unchanged.
- WB v2 Stage 0 unchanged.
- No live deployment from this directive — pure investigation.

---

## CC work queue

In priority order. Track 2 has the longest wall-clock because it needs N≥50 live orders.

1. **Now (parallel with §8.2 resume-boot fix):**
   - Track 1: April 2026 single-shot timeout audit (~3-4 hr)
   - Track 3: Lightspeed + alternatives research (~2-3 hr)

2. **As soon as feasible:**
   - Track 2: deploy sub-second instrumentation to squeeze paper bots (no Setup A modifications). Begin collecting orders.

3. **When Track 2 reaches N≥50:**
   - Track 2 report

4. **When all three tracks have output:**
   - Cowork synthesis → broker stack decision document

---

## Reminder

Manny's exact words: *"Ever since we switched back to Alpaca, we've been missing big moves that I am pretty sure Ross's recaps talk about him making big money on."*

That's a hypothesis with both market-evidence and pattern-match weight behind it. We're going to measure it properly. If it's real, we have data to commit to a migration. If it's not, we save ourselves a broker switch we don't need.

Either way, evidence-driven.

GO.
