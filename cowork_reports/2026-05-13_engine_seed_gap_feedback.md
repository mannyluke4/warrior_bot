# Engine Seed Gap — Setup B Squeeze Has Been a No-Op All Week

**Date:** 2026-05-13
**Author:** CC
**For:** Cowork (Perplexity)
**Severity:** P0 — invalidates A/B comparison on the squeeze side since the engine was first deployed
**Triggered by:** Investigating why Setup B's engine squeeze_bot never produces log events despite "stream healthy" status

---

## TL;DR

The unified data engine (`data_engine.py`) has a critical missing piece: **no historical-tick seeding at boot.** Setup A's main bot replays `reqHistoricalTicks` for each watchlist symbol through its `TradeBarBuilder` before live trading starts, populating `avg_vol` / VWAP / bar-history state in the squeeze detector. The engine has no equivalent — it subscribes to live data only and starts bar-building from the first live tick.

The squeeze detector requires `avg_vol` baseline to compute `vol_ratio` (the PRIME trigger condition, `WB_SQ_VOL_MULT=2.5×`). Without seeded history, `avg_vol` is undefined or zero for the first ~5-10 bars. By the time live volume builds enough baseline to make `vol_ratio` meaningful, the day's setup windows have largely passed.

**Result:** Setup B's squeeze_bot has been completely silent since the engine was first deployed. Its log shows 4 lines today (all startup), 0 PRIMED/ARMED/REJECT events across 9+ hours. The "Setup B squeeze drought" we've been observing for multiple sessions is not a market regime; it's a code bug.

---

## Evidence

**Engine boot sequence (today, 2026-05-13):**

```
[ENGINE] 04:00:09  Setup B Unified Data Engine starting
[ENGINE] 04:00:10  IBKR connected (accounts: ['DUQ143444'])
[ENGINE] 04:00:11  hello from wb_bot v1.0
[ENGINE] 04:00:11  hello from squeeze_bot v1.0
[ENGINE] 04:00:30  subscribed ATRA (snapshot)
[ENGINE] 04:00:30  subscribed CLNN (snapshot)
... (live subscriptions for each watchlist symbol)
```

**No "seeded" log lines.** No historical replay. Engine goes straight from "IBKR connected" to "subscribed (snapshot)" for live data only.

**Engine squeeze_bot log today (TOTAL):**

```
[SQUEEZE] BOOT: COLD (reason=no_marker, marker_age=n/a)
[SQUEEZE] 04:00:11  starting equity $88,797
[SQUEEZE] 04:00:11  connected to engine — fail-CLOSED until first healthy heartbeat
[SQUEEZE] 04:00:15  stream healthy — entries unlocked
```

**Four lines. All boot. Nothing else for 9 hours.** Compare to engine wb_bot (which doesn't need volume baseline) — 44 ATRA events alone.

**Setup A's main bot — same data, same SqueezeDetector class, working correctly:**

```python
# bot_v3_hybrid.py:1643 (paraphrased from the line we read)
# "Replay ticks through TradeBarBuilder (same path as live ticks and simulate.py)"
state.bar_builder_1m.on_trade(symbol, price, size, ts_utc)
```

Setup A fetches `reqHistoricalTicks` for each symbol and replays through `bar_builder_1m`. The detector reaches PRIME/ARM states properly because it has a populated baseline.

Today Setup A's main bot armed ATRA at 14:34 ET (entry signal logged, no_order due to `WB_MIN_R` floor — the OTHER hypothesis we've been tracking). Setup B's squeeze_bot saw the same ATRA ticks (84 ticks/12s confirmed via IPC probe) and produced nothing.

---

## Why wb_bot still works

The Wave Breakout detector scores waves based on:
1. Price oscillations
2. Magnitude % moves
3. Higher-high / higher-low structure
4. MACD direction
5. Bounce volume confirmation

None of these require an `avg_vol` baseline; they're computed from price action and per-bar volume comparisons. The wave detector can start scoring from the first 1m bar. WB has been producing events on Setup B normally.

The squeeze detector's reliance on `avg_vol` is the load-bearing differentiator.

---

## Why this wasn't caught earlier

1. **Engine + squeeze_bot don't crash** — they connect, sing "stream healthy", and silently consume ticks/bars. No error → no signal something is wrong.
2. **Wb_bot working normally** masked the issue — Setup B WAS visibly trading via WB.
3. **Sample size confound** — squeeze setups are rare even on Setup A (multiple days with 0 entries). "Setup B has 0 squeeze entries" looked like normal scarcity, not a bug.
4. **My own initial diagnosis was wrong** — I wrote off Setup B's 0-squeeze pattern as "market regime, same as Setup A." Then today Setup A armed ATRA while Setup B didn't, exposing the asymmetry. The user pushed back ("they should be getting the exact same data, something is off"), and the deeper investigation found this.

This is a teachable instance for how silent failures hide in distributed systems: every component logs "I'm fine," the only signal of breakage was a downstream symptom (zero trades) that had a plausible competing explanation.

---

## A/B comparison implications

**The A/B comparison on the squeeze side has been invalid since the engine was deployed.** Setup A's "0 squeeze fills" days reflected the strategy + the WB_MIN_R floor + the chase-cap pattern. Setup B's "0 squeeze fills" days were just the bot being permanently disabled.

The cumulative impact:
- Daily breakdown reports for 5/11 + 5/12 claimed Setup A vs B parity on squeeze ("both 0 fills, market regime") — this was wrong
- Any tuning hypotheses derived from comparing squeeze outcomes are suspect
- The "diagnostic for ODYS/TRAW chase-cap" comparison stands valid (both setups were data-flowing on WB) but the squeeze diagnostic is corrupted

---

## The fix shipping today

Reuse Setup A's `tick_cache/<date>/<sym>.json.gz` files. The engine reads them at boot, replays through `TradeBarBuilder` (same code path Setup A uses), broadcasts the resulting bar messages to all connected clients. Bots receive bars in temporal order — historical seed bars first, then live bars seamlessly.

Implementation steps:
1. Add `_seed_symbol_from_cache(sym)` method to engine
2. Call for each watchlist symbol at boot (after IBKR connect, before live `reqMktData` subscriptions)
3. Call on intraday watchlist additions (the existing watchlist-poll loop)
4. Restart engine + both bots to validate

The natural bar-broadcast path is preserved — no IPC contract changes needed. Bots' detectors receive their first bar messages from cached history rather than from the first live tick. Once seeded, behavior is identical to Setup A's main bot.

---

## Architectural recommendation for v2

Today's fix uses cached tick files (already maintained by Setup A's session). That's pragmatic — it deduplicates a dependency. But for the unified data engine to be truly self-contained:

**Engine should fetch `reqHistoricalTicks` directly via its own clientId=3 IBKR connection at boot.** Not depend on Setup A's tick cache files. Otherwise the engine is co-dependent with Setup A — can't run standalone, can't run on a different machine that doesn't have Setup A's caches.

Suggested follow-up directive: add `_fetch_seed_history(sym)` to the engine that uses `reqHistoricalTicks` for the same window Setup A uses (04:00 ET → boot time). Cache results to a NEW engine-owned location (`tick_cache_engine/`). Setup A reads from its tree, engine reads from its own. Independence.

---

## Questions for Cowork

### Q1 — Validation
Does the architecture review buy off on the cache-reuse approach as a tactical fix today, with engine-native history fetch as a follow-up?

### Q2 — A/B data correction
Do we need to retroactively correct the A/B comparison reports for 5/11 and 5/12? They claimed "both setups 0 squeeze" as parity, which was misleading. Or do we just note this in tomorrow's report and move forward?

### Q3 — Detector startup contract
Is there value in adding a SEED_COMPLETE message to the IPC contract so bots know when historical data has finished replaying vs live? Today's approach lets bars flow naturally in temporal order, but bots can't distinguish historical from live.

### Q4 — Other detectors affected
Wave breakout works without seed because it doesn't need volume baseline. But are there OTHER fields on bars that the wave detector might use better with seeded data? E.g., session VWAP, HOD/LOD references? The MACD sub-gate that just shipped also reads historical bars to compute MACD state — same problem potentially.

### Q5 — Tomorrow's startup
After today's patch ships, what's the minimum smoke test for engine-side detector readiness? E.g., "engine logs `seeded {sym}: N ticks → M bars` for every watchlist symbol within 60s of boot" — should this be in the daily report contract?

---

## Files referenced

- `data_engine.py` — the bug surface
- `bot_v3_hybrid.py:1643` — Setup A's seed reference implementation
- `squeeze_detector.py:on_bar_close_1m` — the detector whose state machine starves without seed
- `bars.py:TradeBarBuilder` — shared bar-build infrastructure (both setups use this)
- Today's tick_cache files (we pre-populated PTBD/NSTS/MEI/VNET via `ibkr_tick_fetcher.py` earlier this afternoon — ready for engine seed-replay)

---

*The engine looked perfect on the surface — clean architecture, clean IPC, clean handler dispatch. The bug was an unmentioned dependency: squeeze relies on volume baseline, and seed was the silent prerequisite. Validators that say "I'm healthy" while their detector has nothing to detect ARE NOT actually saying what we think they're saying.*
