# DIRECTIVE: Tick-By-Tick Data Migration — Close the 80% Live Data Gap

**Date:** May 5, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P0 — blocking. Every day on the current `reqMktData` path is a wasted paper test.  
**Branch:** `v2-ibkr-migration`  
**Predecessor:** `cowork_reports/2026-05-05_live_tick_gap_critical.md`

---

## Problem (Confirmed)

The live `reqMktData('233', ...)` path is delivering 13-20% of the consolidated tape. This is documented IBKR API behavior, not a bug:

> "Top Of Book Market Data (Level I) is **not tick-by-tick** but consists of aggregated snapshots taken at intra-second intervals... For stocks/futures the interval is **250 ms**."  
> — [IBKR Quant Blog](https://www.interactivebrokers.com/campus/ibkr-quant-news/ibkr-market-data-from-real-time-bars-to-ticks/)

> "**`reqTickByTickData` provides information about every trade or bid or ask**, whereas `reqMktData` provides snapshot data averaged over a 250 ms interval."  
> — [TWS API Forum confirmation](https://groups.io/g/twsapi/topic/reqtickbytick_vs_reqmktdata/14477612)

Backtests are clean (built from `reqHistoricalTicks`, which delivers full tape). Live is degraded. The strategy is being tested in paper on data the strategy was never tuned against.

**Subscriptions are NOT the issue.** Manny's account has NASDAQ TotalView, NYSE OpenBook, NYSE ArcaBook, all relevant Network A/B/C feeds. The full tape is being broadcast — the bot just isn't asking for it the right way.

## Constraint

`reqTickByTickData` has a per-account simultaneous-subscription limit determined by equity and commissions. Retail baseline is 5. Manny's account ($30K+ equity) may qualify for more. We don't know the exact number until we test.

The bot currently subscribes to ~95 symbols on a busy day. **We cannot put 95 symbols on tick-by-tick.** Architecture has to be tiered.

## Solution Architecture

Two-tier subscription model:

| Tier | API | Granularity | Symbol count | Purpose |
|---|---|---|---|---|
| **Tier 1** | `reqTickByTickData('AllLast')` | Every print | Up to N (where N = account limit, TBD) | Symbols actively in or approaching a setup |
| **Tier 2** | `reqMktData('233')` | 250ms snapshots | All other watchlist symbols | Awareness layer — "is this stock waking up?" |

Symbols flow between tiers based on setup state. The 5-15 minutes BEFORE a stock fires a setup is when we need full data resolution. The other hours, snapshot data is fine because we're just monitoring.

## Stages

### Stage 1: Probe Tick-by-Tick Account Limit

A standalone script that:
1. Connects to IB Gateway
2. Subscribes to `reqTickByTickData('AllLast')` for active stocks one at a time
3. After each successful subscription, waits 5 seconds and checks for events
4. Reports the symbol count where IBKR returns error 10089 ("Requested market data requires additional subscription") or 10186 ("Max number of tick-by-tick requests has been reached") or otherwise fails
5. The number that succeeds = our Tier 1 capacity

Save findings to: `cowork_reports/2026-05-XX_tickbytick_capacity.md`

This determines architecture. If it's 5, the promotion logic has to be aggressive. If it's 50+, we can be lazy about it.

### Stage 2: Dual-Feed Architecture

Add `reqTickByTickData` as a parallel subscription path alongside the existing `reqMktData`. **Do not remove the existing path.** Both run simultaneously.

In `bot_v3_hybrid.py`:

1. **New subscription state per symbol:**
```python
state.symbols[sym] = {
    ...existing fields...
    "tier": "snapshot",  # or "tick_by_tick"
    "tbt_req_id": None,
    "tbt_subscribed_at": None,
}
```

2. **New subscribe/unsubscribe functions:**
```python
def subscribe_tick_by_tick(sym):
    """Promote symbol to Tier 1. Subscribes to reqTickByTickData('AllLast')."""
    
def unsubscribe_tick_by_tick(sym):
    """Demote to Tier 2. Cancels tick-by-tick, retains reqMktData snapshot."""
```

3. **Tick handler that ignores `reqMktData` events for symbols also subscribed to tick-by-tick** (to avoid double-counting):
```python
def on_ticker_update(tickers):
    for ticker in tickers:
        sym = ticker.contract.symbol
        if state.symbols[sym].get("tier") == "tick_by_tick":
            continue  # Ignore — tick-by-tick handler will process
        process_snapshot_tick(ticker)

def on_tick_by_tick_all_last(req_id, time, price, size, attribs, exchange, special_conditions):
    sym = state.tbt_req_id_to_sym.get(req_id)
    if not sym:
        return
    process_real_tick(sym, time, price, size)
```

4. **At session start, set up Tier 2 (snapshot) for the entire watchlist** — same as current behavior. No Tier 1 yet (until promotion logic in Stage 3).

### Stage 3: Promotion / Demotion Logic

A symbol gets promoted to Tier 1 when ANY of these are true:

1. **Squeeze detector reaches PRIMED state** for that symbol
2. **Wave Breakout detector reaches WAVE_OBSERVING with a recent qualifying wave** (score ≥ 5 — early warning, before ARM)
3. **Bot has an open position** in that symbol (always Tier 1 while in a trade)
4. **Symbol is in top-N most active by volume in the last 5 minutes** (where N = floor(Tier 1 capacity / 2), the "active hunt" reserve)

A symbol gets demoted from Tier 1 when ALL of these are true:

1. No open position
2. No detector in PRIMED / ARMED / WAVE_OBSERVING(score≥5) state
3. Not in the top-N volume reserve
4. Has been Tier 1 for at least 5 minutes (cooldown — don't thrash subscriptions)

**Tier 1 capacity management:**

```python
def manage_tier1_subscriptions():
    """Called every 30 seconds. Promotes/demotes based on state."""
    capacity = TIER1_MAX_SUBSCRIPTIONS  # from Stage 1 probe
    candidates = []  # symbols that should be Tier 1, with priority scores
    
    for sym, sym_state in state.symbols.items():
        priority = compute_tier1_priority(sym, sym_state)
        if priority > 0:
            candidates.append((sym, priority))
    
    candidates.sort(key=lambda x: -x[1])
    target_tier1 = set(sym for sym, _ in candidates[:capacity])
    
    current_tier1 = set(sym for sym, s in state.symbols.items() if s["tier"] == "tick_by_tick")
    
    # Promote new
    for sym in target_tier1 - current_tier1:
        subscribe_tick_by_tick(sym)
    
    # Demote dropped
    for sym in current_tier1 - target_tier1:
        if can_demote(sym):  # cooldown + no active position
            unsubscribe_tick_by_tick(sym)
```

**Priority scoring (highest first):**
- 1000: open position (must always be Tier 1)
- 500: detector ARMED
- 200: detector PRIMED
- 100: WAVE_OBSERVING with score ≥ 7
- 50: WAVE_OBSERVING with score ≥ 5
- 20-50: top volume in last 5 min (scaled by volume rank)
- 0: nothing notable — eligible for demotion

### Logging Convention

Every promote/demote event must be logged:

```
[TIER] PROMOTE BIRD reason=squeeze_primed (replacing CRWG, oldest_priority=20)
[TIER] DEMOTE CRWG reason=cooldown_expired_no_signal (was_tier1_for=312s)
[TIER] STATUS tier1=[BIRD,FATN,RECT,KIDZ,CNSP] tier2=87 capacity=5
```

This is the audit trail for verifying the tiered model is working as designed.

## Stage Outputs

```
cowork_reports/2026-05-XX_tickbytick_capacity.md       # Stage 1 probe results
bot_v3_hybrid.py                                         # Stage 2 + 3 changes
cowork_reports/2026-05-XX_dual_feed_architecture.md     # Stage 2 architecture notes
cowork_reports/2026-05-XX_tier_management_design.md     # Stage 3 design + scoring rationale
```

## What NOT to Do

- ❌ Do NOT remove the existing `reqMktData` subscription code. Tier 2 still uses it.
- ❌ Do NOT subscribe all 95 watchlist symbols to tick-by-tick. The cap exists; honor it.
- ❌ Do NOT promote/demote symbols faster than every 30 seconds. Subscription churn has cost.
- ❌ Do NOT keep symbols in Tier 1 indefinitely after the setup expires. The 5-minute cooldown is to prevent thrashing, not to permanently hold idle subscriptions.
- ❌ Do NOT modify backtest code. Backtest reads from `reqHistoricalTicks` and is already correct. Only the live data path needs changes.

## Acceptance Criteria

After Stage 3 deploys:

| # | Check | How to verify |
|---:|---|---|
| 1 | Tier 1 capacity is correctly configured for the account | Probe script run, capacity logged in startup banner |
| 2 | Symbols in active setups are always Tier 1 | Audit logs: every PRIMED event has a corresponding [TIER] PROMOTE within 30s |
| 3 | Open positions are always Tier 1 | No symbol with `state.position is not None` should be in Tier 2 |
| 4 | Tier 1 doesn't thrash | No symbol bounces between tiers more than once per minute under normal conditions |
| 5 | Daily live tick capture for tier-1-promoted symbols matches `reqHistoricalTicks` within 5% | Pull next-day historical fetch for one Tier-1-promoted symbol; compare counts |
| 6 | Detector behavior on Tier 1 symbols matches backtest expectations | Run squeeze and WB detectors on the same symbol on the same day in live and backtest, compare state transitions |

Criterion 5 is the proof point. If a symbol that was in Tier 1 from PRIMED through trade close has a tick count within 5% of the historical fetch for that symbol/day, the migration worked.

## Why This Is The Last Major Infrastructure Block

Once the live feed delivers complete data:
- Detector behavior on live should match backtest behavior
- Stop slippage should drop dramatically (no more "missed the stop because we only saw 1 in 5 prints")
- The 53.4% WR / 2.01 PF projection is testable for real
- Live trades become a meaningful signal about strategy edge, not a degraded shadow of it

The June 4 PDT deadline is when paper testing has to convert to real money. Every day until then is calibrating against the current degraded feed, which means we're tuning to the wrong target. Migration is blocking.

---

*Backtest is right. Live needs to catch up. Tiered subscriptions get us there.*
