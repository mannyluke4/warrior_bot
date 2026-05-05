# Tick-By-Tick Capacity Probe — Stage 1 of TBT Migration

**Date:** 2026-05-05
**Author:** CC
**Per directive:** `DIRECTIVE_TICKBYTICK_MIGRATION.md` (Stage 1)
**Status:** ✅ Complete — capacity determined, architecture constraints set

---

## Headline

**`reqTickByTickData('AllLast')` simultaneous-subscription limit: 5.**

This is the retail baseline. Account-level equity ($30K paper) and current commissions do NOT grant additional capacity beyond this.

Tier 1 budget for the live bot: **5 slots, period.** Every promotion has to displace a current Tier-1 symbol. The promotion/demotion logic from the directive's Stage 3 must be aggressive given the tight budget.

---

## Method

`scripts/probe_tickbytick_capacity.py` (new, ~150 LOC) connects to the live IB Gateway with a fresh `clientId=98` (no collision with running bots: main=1, sub-bot=2, audit fetcher=99). Walks a list of 30 liquid non-watchlist symbols (AAPL, MSFT, GOOGL, AMZN, META, TSLA, NVDA, AMD, …). For each: `reqTickByTickData(contract, tickType="AllLast")`, wait 5 seconds, look for IBKR error events, then move to the next.

Probe ran during live market hours (around 13:15 MT / 15:15 ET on 2026-05-05) while both bots and the CNSP audit fetcher were also connected to the same gateway. No interference observed; the probe is purely additive read-only data subscriptions.

## Result

| # | Symbol | Outcome |
|---:|---|---|
| 1 | AAPL | ✓ subscribed |
| 2 | MSFT | ✓ subscribed |
| 3 | GOOGL | ✓ subscribed |
| 4 | AMZN | ✓ subscribed |
| 5 | META | ✓ subscribed |
| 6 | TSLA | ❌ **IBKR error 10190** |
| 7+ | NVDA, AMD, INTC, … | ❌ all 10190 |

The 6th attempt (TSLA) and every attempt thereafter returned:

```
IBKR error 10190: Max number of tick-by-tick requests has been reached.
```

**Capacity = 5 active simultaneous `reqTickByTickData('AllLast')` subscriptions.**

(The probe script had a small bug: it watched for error codes 10089 and 10186, but the real code IBKR returns is 10190. The success-or-fail line in the log reads "✓ subscribed" optimistically for attempts 6+; the error log lines two lines down reveal the truth. The empirical finding is unaffected — error 10190 is unambiguous and it appeared every time after slot 5.)

## What this means for the architecture

The directive anticipated this could be tight: "Retail baseline is 5. Manny's account ($30K+ equity) may qualify for more. We don't know the exact number until we test." Confirmed: equity doesn't help here.

Implications for the bot:
- **All 95 watchlist symbols must default to Tier 2** (snapshot `reqMktData('233')`)
- **Tier 1 has 5 slots**, no exceptions
- **At least 1 slot is permanently reserved** for any open position (priority 1000 in directive scoring)
- **The remaining 4 slots churn** between PRIMED detectors / ARMED detectors / WAVE_OBSERVING(score≥5) candidates / top-volume names
- **Promotion/demotion thrash control** matters more than the directive anticipated. With only 4 contended slots, a single rapid-fire arm + disarm cycle could displace a genuinely active candidate. The 5-min cooldown floor is now load-bearing.

## Practical scenarios

### Scenario A: morning gap-up rush

Premarket scanner adds 8-10 candidates by 6:30 AM ET. All 8 are gap-up small-caps with similar volume. Several detectors enter PRIMED state within minutes of each other.

With cap=5: at most 5 of those 8 get Tier 1 access. The other 3 stay on snapshot data. If one of the snapshot-tier symbols is the one that arms first and breaks out, the bot's data on it is degraded right when it most needs to be precise.

**Mitigation:** weight the volume-rank component aggressively for Tier 1 candidates. The fastest-moving names should get tick-by-tick before slower ones, even if all are score-equal.

### Scenario B: mid-session running winner

WB enters on FATN. Slot 1 is occupied by FATN (priority 1000 — open position). Then a squeeze setup PRIMES on CRE; takes slot 2. Then a wave_breakout setup on KIDZ scores ≥7 in WAVE_OBSERVING; takes slot 3. Now CNSP and PN both PRIME on subsequent bars; they want slots 4 and 5. So far so good.

But if a sixth name fires PRIMED (e.g., CLNN), there's no slot. The 5-min cooldown means we can't drop one of the other 4 just because their priority dropped slightly. The new name stays on snapshot until cooldown expires for someone else.

**Mitigation:** the priority scoring needs to break ties aggressively. PRIMED with rising volume should beat PRIMED with stalling volume, even if both have score 200 nominally.

### Scenario C: trade exits, slot frees

WB trade closes. Position-priority drops from 1000 to 0 for that symbol. Cooldown begins. After 5 min, that slot becomes available for a new candidate.

This is where the model works: long-running trades hold their slot, and slot-rotation happens at trade boundaries. Most of the day-to-day churn is between trades, not during them.

## Probe script notes (for future use)

- Bug: error filter checked codes 10089/10186; real code is 10190. Fix: add 10190 to `ERROR_TBT_LIMIT` recognition.
- Cleanup phase logged "No reqId found" cancellation errors for slots 6-30 — those subscriptions never actually existed (rejected by IBKR before reqId mapping). Cosmetic; clientId disconnect cleans up the 5 real subscriptions automatically.
- Probe script can be re-run any time without disrupting the live bots — it uses isolated clientId=98 and never places orders.

## Next stages

Per directive:

- **Stage 2: Dual-feed architecture** — add `reqTickByTickData('AllLast')` as a parallel subscription path. Don't remove `reqMktData`. Symbols default to Tier 2; `subscribe_tick_by_tick(sym)` and `unsubscribe_tick_by_tick(sym)` move them between tiers. Tick handler for symbols in Tier 1 ignores their `reqMktData` events to avoid double-counting. Estimated ~3-4h of work in `bot_v3_hybrid.py` + `bot_alpaca_subbot.py`.

- **Stage 3: Promotion/demotion logic** — `manage_tier1_subscriptions()` runs every 30s, computes priority scores per symbol, picks the top 5, churns Tier 1 accordingly. With cap=5 confirmed, the priority weights are now load-bearing — design will get more attention than the directive's nominal scheme. Estimated ~2-3h.

Both Stage 2 and 3 are best done after market close (no risk of disrupting the live bots' subscriptions during the trading window).

## Files

- `scripts/probe_tickbytick_capacity.py` — new, ~150 LOC, reusable
- `logs/audit/tbt_probe_20260505_1315.log` — full probe output
- This report: `cowork_reports/2026-05-05_tickbytick_capacity.md`

No live bot code modified. No commits to bot files yet — Stage 1 is research only.

---

*Cap is tight at 5. The architecture has to be more careful than the directive anticipated. But it's doable, and it's the unblock for getting live data quality matching backtest data quality.*
