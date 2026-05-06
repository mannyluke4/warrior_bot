# TBT Drain Bug Diagnosis & Fix
## 2026-05-06

**Author:** CC
**For:** Cowork
**Trigger:** Today's `WB_TBT_ENABLED=1` failure — Tier 1 symbols silently going data-blind hours after subscription
**Status:** ✅ Root cause identified, fix shipped to both bots; still gated OFF until Manny re-flips

---

## TL;DR

The `_drain_tick_by_tick_ticker()` function tracked a `last_processed_index` across event-loop cycles assuming `ticker.tickByTicks` was an accumulating list. **It's not** — ib_insync clears the list between cycles. Once `last_idx` walked past the (always-short) list, every subsequent cycle silently dropped all per-print data. KBSX last live tick at 04:01 ET = 6.5h stale. ERNA last live tick at 09:31 ET while Alpaca showed it actively trading. Confirmed via `scripts/probe_tbt_event_flow.py`. Removed the index tracking; iterate `ticker.tickByTicks` per event.

---

## Diagnostic probe

Wrote `scripts/probe_tbt_event_flow.py` to subscribe ERNA via both `reqMktData` and `reqTickByTickData`, hook `pendingTickersEvent`, and watch for 30 seconds. Two findings, both important:

### Finding 1: ib_insync uses ONE Ticker object for both subscriptions

```
snapshot_ticker id: 4443857952
tbt_ticker id     : 4443857952
SAME OBJECT?      : True
```

Reasoning earlier (in `cowork_reports/2026-05-06_morning_choppy_stock_analysis.md`) suggested two distinct Ticker objects. **Wrong.** When the same contract is subscribed via both APIs, ib_insync returns the same `Ticker`. Snapshot fields (`.last`, `.lastSize`) and per-print fields (`.tickByTicks`) live on the same object. Each `pendingTickersEvent` fires once per ticker per cycle, regardless of which subscription produced the update.

### Finding 2: `tickByTicks` is per-cycle, not accumulating

Sample of the probe output:

```
[evt #11] tickByTicks_len=1
[evt #12] tickByTicks_len=1
[evt #13] tickByTicks_len=2
[evt #14] tickByTicks_len=1   ← went DOWN. List was cleared between #13 and #14.
[evt #15] tickByTicks_len=1
[evt #20] tickByTicks_len=0   ← back to zero
```

ib_insync clears `ticker.tickByTicks` between event-loop cycles. The list contains only the per-print events that arrived since the last `pendingTickersEvent`. The original Stage 2 code I shipped assumed accumulation:

```python
last_idx = state.tbt_last_processed_index.get(symbol, 0)
new_ticks = ticker.tickByTicks[last_idx:]
...
state.tbt_last_processed_index[symbol] = len(ticker.tickByTicks)
```

Walkthrough of how this fails:

| evt # | tickByTicks state | last_idx coming in | new_ticks slice | last_idx after | Outcome |
|---|---|---|---|---|---|
| 11 | `[t1]` | 0 | `[t1]` | 1 | ✓ processes t1 |
| 12 | `[t2]` (cleared, refilled) | 1 | `[]` | 1 | ✗ misses t2 |
| 13 | `[t3, t4]` | 1 | `[t4]` | 2 | ✗ misses t3 |
| 14 | `[t5]` | 2 | `[]` (out of bounds) | 1 | ✗ misses t5 |
| 15+ | … | always > len | always `[]` | … | ✗ misses everything |

After the first cycle's tick, `last_idx` is permanently stuck above whatever short value `len(ticker.tickByTicks)` ever takes. Drain returns early ("no new ticks"), and Tier 1 symbols become silently data-blind. Snapshot ticker updates (the `.last`/`.lastSize` path) ARE delivered but get routed to the same drain function, find empty `tickByTicks`, and silently drop. So both data paths are blocked.

This explains every observation from this morning:
- KBSX last tick at 04:01 ET (6.5h stale by audit time): TBT subscribed at boot, processed first batch, then index broke. 6.5h of bot-side blindness while KBSX continued to trade in the market.
- ERNA actively trading at 14:36 UTC (1s ago per Alpaca), bot perception 09:31 ET (~5h stale): same pattern.
- "🔴 CRITICAL: no ticks after 3 resubscription attempts" spam: audit_tick_health correctly detected the drought; my dismissal of it as "premarket quiet" was wrong.
- Both main and sub-bot affected identically: same code path, same bug.

---

## Fix

In both `bot_v3_hybrid.py` and `bot_alpaca_subbot.py` (mirrored):

```python
def _drain_tick_by_tick_ticker(ticker):
    contract = ticker.contract
    if not contract:
        return
    symbol = contract.symbol
    tbt_events = list(ticker.tickByTicks or [])

    if tbt_events:
        # Per-print path — high-fidelity stream we promoted for.
        for tk in tbt_events:
            ...  # parse, update tick_counts, last_tick_time, last_tick_price,
                 # then call _process_trade_tick if price/size valid
        return

    # No per-print events this cycle — refresh health metrics from snapshot
    # so audit_tick_health doesn't false-alarm on briefly quiet TBT cycles
    # while .last is clearly live. Do NOT bump tick_counts here (those are
    # trade events only).
    last_attr = getattr(ticker, "last", None)
    if last_attr is not None and not (isinstance(last_attr, float) and math.isnan(last_attr)) and last_attr > 0:
        state.last_tick_time[symbol] = datetime.now(ET)
        state.last_tick_price[symbol] = float(last_attr)
```

Key differences from the broken code:
1. **No `last_idx` tracking.** Each event sees the current contents of `tickByTicks`; ib_insync's per-cycle reset is the truth source.
2. **Snapshot fallback for health monitoring.** When `tickByTicks` is empty but `.last` is fresh, refresh `last_tick_time` so the audit doesn't fire CRITICAL on a TBT-only-quiet symbol whose snapshot is still alive.
3. `state.tbt_last_processed_index` is now dead state — kept for now to avoid touching subscribe/cancel paths, will clean up in a follow-up.

---

## Re-deployment plan

The fix is shipped (commit pending push) but **TBT is still gated OFF** (`WB_TBT_ENABLED=0` in `.env`). Before re-enabling, want to:

1. Sub-bot: keep TBT off until tradability gate validates (separate P0).
2. Once tradability gate is validated, re-enable TBT on sub-bot, watch one session for `[TIER]` log behavior plus tick-count audit lines showing actual progression on Tier 1 symbols.
3. Verify acceptance criterion #5 from `DIRECTIVE_TICKBYTICK_MIGRATION.md`: pull next-day historical tick fetch for one Tier-1-promoted symbol, compare to bot-captured count, target within 5%.
4. Mirror to main bot.

---

## Lessons

- **`tail -F` style assumptions on third-party event surfaces are dangerous.** I assumed `tickByTicks` accumulated; the doc/source for ib_insync would have clarified. Probe scripts FIRST, code SECOND.
- **A two-symptom failure (KBSX stale 6.5h + ERNA actively trading but invisible) deserved more diagnostic time before being blamed on "market quiet."** I spent 6 hours dismissing the symptom; Manny had to call it out. Saved as `feedback_trading_hours_monitoring.md` operationally; this is the same lesson at the engineering level.
- **The original Stage 2 plumbing didn't have a smoke test.** Before deploying for live data, an integration test that subscribes one symbol and verifies tick flow over a known period would have caught this. Worth adding for any future live-data path changes.

---

## Files

- `scripts/probe_tbt_event_flow.py` — diagnostic probe (new, ~120 LOC, reusable)
- `bot_v3_hybrid.py` — drain fix
- `bot_alpaca_subbot.py` — drain fix mirrored
- This report
