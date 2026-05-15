# L2 Integration — Strategic Direction

**Date:** 2026-05-15
**Author:** Cowork (Perplexity)
**For:** CC
**Trigger:** Manny: "Remember, we've had access to L2 through IBKR this entire time. Can we utilize that?"
**Augments:** `DIRECTIVE_2026-05-15_WB_DEAD_TAPE_GATE.md`

---

## TL;DR

Yes — L2 is a higher-quality solution to multiple problems, including dead-tape detection. We already have 917 lines of pre-built L2 signal detection code (`archive/scripts/l2_signals.py` + `l2_entry.py`) from an earlier project phase that was parked when we shifted to V3 hybrid architecture. **Nothing live uses L2 right now.**

**Recommendation:**

1. **Saturday (still):** ship the simple 1m-bar dead-tape gate per yesterday's directive. It's the 80% solution that catches today's ATRA misfire and ships before Monday.
2. **Next 2-3 weeks:** wire L2 back in as a deeper, multi-purpose signal layer. Dead-tape detection becomes one of *several* L2-derived checks. Book imbalance, bid stacking, large-order detection, and spread quality all become available to the bot.
3. **Combine:** dead-rate gate as the cheap pre-filter on every WB_ARM; L2 confirmation as the expensive check on the subset that passes pre-filter.

This is not "use L2 instead of the dead-tape gate." It's "use L2 to do dead-tape detection PLUS several other things the bot currently can't see."

---

## What we already have (archived code inventory)

**`archive/scripts/l2_signals.py` (345 lines):**
Detects four patterns from L2 snapshots:
- **A. Order book imbalance** — bid vs ask dominance (default thresholds 0.65 bull / 0.35 bear)
- **B. Bid stacking** — large orders accumulating at price levels (default 3× multiplier)
- **C. Large order detection** — sudden iceberg appearances
- **D. Spread + liquidity** — ask thinning, wide spread warnings

All thresholds are env-configurable. Designed for both backtester (Databento historical) and live bot (IBKR feed).

**`archive/scripts/l2_entry.py` (359 lines):**
Decision logic combining L2 signals into entry/no-entry verdicts. Originally built for the Ross-Cameron-pattern phase.

**`archive/scripts/ibkr_feed.py` (213 lines):**
The IBKR L2 subscription manager — handles `reqMktDepth` calls, snapshot updates, depth event routing. The infrastructure plumbing.

**Status check (just verified):**
- `bot_v3_hybrid.py`, `wb_bot.py`, `wave_breakout_detector.py`, `squeeze_detector_v2.py`, `data_engine.py` — none import or call these modules
- `databento_feed.py` references `l2_signals` but the import path is currently broken (file is in archive, not at the expected location)
- `simulate.py` has a `--use_l2_entry` backtest flag

**The infrastructure exists but is dormant.** Wiring back in is integration work, not a from-scratch build.

---

## Why L2 is a better solution than 1m-bar dead-rate

For the specific ATRA-today problem, L2 distinguishes cases that 1m bars cannot:

| Case | 1m bars say | L2 reveals |
|---|---|---|
| **Dead stock, no quotes**: ATRA today | dead_rate high | bid/ask 5-15¢ spread, depth <500 each side, stale quotes |
| **Quiet but tight market**: a real WB candidate mid-session waiting for a wave | dead_rate possibly high | bid/ask 1-2¢ spread, depth 2K+ each side, quotes updating |
| **Volume-but-no-direction**: a stock printing but absorbed at one level | dead_rate low | massive ask resting on book, imbalance bearish, prints all hitting bid |
| **Real WB setup developing**: stack building on bid pre-bounce | dead_rate low | bid stack 5× ask, imbalance 0.75+ bull |

The dead-rate gate would handle case 1 correctly and case 3 wrongly (passes through volume-but-no-direction setups). L2 handles all four correctly.

**Additional benefits beyond dead-tape detection:**

- **Positive entry confirmation** — book imbalance + bid stacking is a "real flow is going long" signal independent of price action
- **Stop-loss safety** — knowing bid depth tells us whether our stop will fill cleanly or gap through
- **Squeeze-bot improvements** — squeeze already filters on 50K bar volume but doesn't know if that volume is one-sided (all sells getting absorbed = trap) vs two-sided (real buying)

---

## IBKR L2 mechanics — what's free vs constrained

| Subscription type | Slots | Behavior |
|---|---|---|
| Snapshot (`reqMktData`) | unlimited up to watchlist size | low frequency, fine for monitoring |
| Tick-by-tick (`reqTickByTickData`) | 5 per main bot (probed empirically) | for active squeeze symbols |
| Market depth (`reqMktDepth`) | typically 3-10 per IBKR account, depending on data subscription tier | for L2 |

**Manny: please confirm your IBKR data subscription includes Nasdaq TotalView or NYSE OpenBook (or equivalent L2 feeds for your active universe).** Without these the `reqMktDepth` calls only return top-of-book, not depth-of-book. The archived code assumed full depth-of-book was available; CC should verify when wiring.

The slot limit (typically 3-10 simultaneous depth subscriptions) is the binding constraint. We can't subscribe L2 on the full watchlist. Options:

1. **Tier-3 architecture: L2 only on WB_OBSERVE-active symbols** — when WB detector sees wave structure forming, subscribe L2; drop when the wave resolves or after timeout. This mirrors the existing TBT Tier-1 design.
2. **L2 only at ARM time** — when WB scores high enough to consider entry, request L2 snapshot synchronously, evaluate, then drop. Highest fidelity at lowest cost, but adds entry latency (typically 200-500ms for IBKR depth snapshot).
3. **L2 only on persistence-layer symbols** — small enough universe to subscribe permanently, gives us pre-ARM confirmation on the highest-value candidates.

I lean toward option 2 (L2 at ARM time) because:
- It's the cheapest IBKR usage
- The latency cost is acceptable — 200-500ms vs the 30s entry retry window
- It runs on the symbols that matter (the ones we're about to actually trade)
- It scales naturally as we add WB_OBSERVE'd symbols

CC's call on which architecture to implement. Option 2 is my recommendation if no strong reason against.

---

## Why ship the 1m-bar dead-rate gate first anyway

**Time to ship:** 1m dead-rate is hours; L2 integration is days-to-weeks. The ATRA-class misfire happens often enough that waiting for L2 means more losses in the gap.

**Validation:** the 1m dead-rate gate can be validated against historical bar data we already have. L2 validation requires either replaying historical L2 (we may not have stored it) or paper-week observation.

**Insurance against L2 wiring problems:** if L2 integration hits unexpected IBKR API issues, slot limits prove more restrictive than expected, or the archived code needs significant rewrites, we still have a dead-tape gate in place.

**Defense in depth:** once L2 ships, the 1m dead-rate gate becomes a cheap upstream filter (run on every ARM candidate) and L2 becomes the deeper check (run only on dead-rate passers). Two layers catch different failure modes — dead-rate catches "stock is dead," L2 catches "stock has trades but no market." Same as keeping squeeze's 50K bar volume gate even with all our other checks.

---

## Revised plan

### Phase 1 — Saturday (unchanged from prior directive)

Ship 1m-bar dead-rate gate per `DIRECTIVE_2026-05-15_WB_DEAD_TAPE_GATE.md`. Validate against ATRA 5/15 misfire + 4 known winners. Live in paper Monday if validation passes.

### Phase 2 — Next 2-3 weeks: L2 integration

**Week 1 (5/18-22):** CC audits the archived L2 code for V3-architecture compatibility. Surfaces:
- What needs updating to match current data pipeline patterns
- Whether `archive/scripts/ibkr_feed.py` integrates cleanly with current `data_engine.py`
- IBKR slot-limit measurements via a probe script (mirror the TBT probe pattern)
- Report: `cowork_reports/2026-05-XX_l2_integration_audit.md`

**Week 2 (5/25-29):** Wire option-2 architecture (L2 at ARM time) for WB. Concrete deliverable:
- Restore `l2_signals.py` and `l2_entry.py` from archive to live location
- New function `request_l2_snapshot(symbol) -> L2Snapshot` in `data_engine.py`
- WB detector gate: at WB_ARM time (after score, R%, dead-rate gates pass), request L2 snapshot, evaluate using existing `L2SignalDetector`, veto if `spread > 1%` OR `imbalance < 0.4` (bear flow) OR `bid depth < 1000 shares at touch`
- Telemetry: log L2 verdict on every ARM
- Env flag: `WB_L2_GATE_ENABLED=0` initially; flip to `1` after first day of telemetry confirms latency is acceptable

**Week 3 (6/1-3):** L2 as positive signal — beyond veto. Score boost for imbalance_bull setups; bid-stacking confirmation; large-order detection feeding entry timing. **Conditional on Week 2 validation.**

### Phase 3 — Squeeze strategy L2 (June)

Squeeze already has 50K bar volume floor. Adding L2 absorption-detection (volume printing but all hitting bid = trap) closes a class of losses the audit might find. **After WB L2 ships and proves the integration.**

---

## What this changes about other directives

1. **`DIRECTIVE_2026-05-15_WB_DEAD_TAPE_GATE.md` (today, earlier):** unchanged. Still ships Saturday. The L2 work is additive, not replacement.
2. **`DIRECTIVE_WB_SCANNER_STRATEGY.md` Stage 1 backtest:** scope grows — backtest should optionally include L2-derived features if we have historical L2 data, or accept that backtest won't capture L2 signal value (limitation to document).
3. **June 4 go-live readiness:** L2 should be live in paper for at least 2 weeks before real money. If Phase 2 wiring takes longer than 2 weeks, L2 ships post-go-live with current dead-tape gate as the only protection until then. Acceptable risk if dead-tape gate validates well.

---

## Questions for you

1. **L2 subscription confirmation:** Does your IBKR account have Nasdaq TotalView and NYSE OpenBook (or your relevant L2 feeds)? Without these, depth-of-book is unavailable and we're stuck with top-of-book only. Top-of-book is still useful (spread + L1 size) but loses 70% of L2's value.

2. **Slot count:** what's your current depth subscription cap on this account? CC can probe it, but if you know it offhand it saves a step.

3. **Latency tolerance:** option 2 (L2-at-ARM-time) adds ~200-500ms to the entry decision. WB has a ~30s retry window so this is well within budget, but worth confirming you're OK with the tradeoff vs option 1 (permanent subscriptions on WB_OBSERVE-active symbols).

4. **L2 historical data:** do we have any stored L2 streams from prior project phases that could feed the backtest? Or is L2 strictly forward-looking from this point?

---

## What I'm NOT recommending

1. **Not delaying the dead-tape gate ship.** It still goes Saturday/Monday per prior directive.
2. **Not pulling resources from the FCHL P0.** That stays the immediate priority.
3. **Not pulling resources from the squeeze fill-rate fix.** That's already a Monday-open ship.
4. **Not committing to a specific L2 architecture before CC audits the archive code.** Options 1/2/3 are starting points; the audit may reveal constraints that change the choice.
5. **Not blocking June 4 go-live on L2.** If integration takes longer than 2 paper-weeks of validation, we go live with dead-tape gate as the sole protection. L2 ships post-go-live.

---

## Tone note

This is the kind of question that pays for itself many times over. Yes, we have L2. No, we're not using it. The answer to "should we?" is unambiguously yes — for dead-tape detection, for positive entry confirmation, for stop-out depth checks, for absorption detection on squeeze. Multi-purpose leverage on infrastructure we already have access to.

The right sequence is still: ship the cheap fix Saturday so we're protected Monday, then invest in the better fix over 2-3 weeks. Defense in depth is the goal.

Worth saying out loud: I should have asked about L2 availability earlier this week when we were discussing the persistence layer and the intraday adder. Both of those workstreams would benefit from L2-informed candidate quality scoring. The fact that L2 has been sitting unused for months is a clear example of "we've been solving a problem with worse tools than we have available." Not anymore.

---

## Files referenced

- `archive/scripts/l2_signals.py` (the L2 detection logic)
- `archive/scripts/l2_entry.py` (entry decisions from L2)
- `archive/scripts/ibkr_feed.py` (IBKR L2 subscription manager)
- `databento_feed.py` (currently has broken import from l2_signals)
- `simulate.py` (has --use_l2_entry backtest flag)
- `scripts/probe_tickbytick_capacity.py` (mirror this for L2 capacity probe)
- `bot_v3_hybrid.py:114-119` (TBT subscription mgmt — model for L2 mgmt)
- `DIRECTIVE_2026-05-15_WB_DEAD_TAPE_GATE.md` (still ships Saturday)
- `DIRECTIVE_WB_SCANNER_STRATEGY.md` (Stage 1 backtest scope grows)
