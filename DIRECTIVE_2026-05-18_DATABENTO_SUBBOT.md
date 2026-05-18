# Setup B → Databento Live Feed (Side-by-Side A/B)

**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Author:** Cowork (per Manny direction, Mon 5:07 PM MDT)
**Status:** GO — wire Setup B (`bot_alpaca_subbot.py`) to Databento live ticks for tomorrow's market open. Setup A unchanged on IBKR. Run side-by-side, compare.

---

## Manny's direction

> "IBKR requires $500 minimum just sitting there for us to actually use it. Then on top of that, we pay the market data subscriptions.
>
> Let's use the bot that WB was using for setup B. It's sitting unused today. We'll wire that one for Databento for data, and Alpaca for execution. Do we get live ticks from Databento? We should — we're paying for it.
>
> Let's set this up today, and run them side-by-side tomorrow."

---

## Pre-flight findings (verified by Cowork before drafting)

- **Databento ships live ticks via `databento.Live()` SDK.** `live_scanner.py:650` already uses it (currently for Databento TBBO trade stream feeding the scanner). We're paying for it. The feed is real and active.
- **`databento_feed.py` exists for historical only.** No live-feed module yet. Needs to be built.
- **`alpaca_feed.py` exists as a dormant drop-in `ib_insync.IB` shim.** Built for the May 4 Alpaca-data experiment. Documented as: *"a drop-in replacement for ib_insync.IB market-data layer ... mirrors the subset of ib_insync's IB API that bot_v3_hybrid.py uses."* **The same shape applies to a Databento live feed.** Use `alpaca_feed.py` as the architectural template.
- **Setup B bot (`bot_alpaca_subbot.py`) currently runs `IBKR data + Alpaca execution`.** It was switched FROM Alpaca data on 2026-05-04 after measurement showed Alpaca IEX captured **0.1–3.6% of the IBKR consolidated tick stream** on small-caps. **Databento is MBO-grade, not IEX-degraded — should match or beat IBKR on tick density.** Verifying this tomorrow is the entire point of the A/B.
- **Setup B's watchlist comes from Setup A.** Per the bot header: *"This sub-bot does NOT run its own scanner. It polls session_state/<today>/watchlist.json that the main bot writes."* Same universe, same seeding, only the broker differs. **For the Databento experiment, this stays — same watchlist, same symbols, only the data source differs.**
- **Setup B uses clientId=2 for IBKR.** Going to Databento means we drop the IBKR connection on Setup B entirely. No clientId conflict possible. Net simplification.

---

## What we're building

A new file: **`databento_live_feed.py`** — the same architectural pattern as `alpaca_feed.py`, but backed by `databento.Live()` instead of Alpaca's `StockDataStream`.

Mirrors the subset of `ib_insync.IB` that `bot_alpaca_subbot.py` reaches for. Specifically (from grep of the bot's IBKR usage):

- `connect()` / `isConnected()` / `managedAccounts()` — connection lifecycle
- `qualifyContracts(contract)` — symbol resolution (Databento uses raw symbols, no contract qualification needed; method becomes a no-op or lookup)
- `reqMktData(contract, '233', ...)` — Tier 2 snapshot stream → Databento TBBO subscription
- `reqTickByTickData(contract, "AllLast", ...)` — Tier 1 per-print stream → Databento `trades` schema subscription on MBO/TBBO
- `cancelMktData(contract)` / `cancelTickByTickData(contract, "AllLast")` — unsubscribe
- `reqHistoricalTicks(...)` — used for seed-replay → Databento `Historical()` (already proven)
- `sleep(N)` — yield-and-drain pattern (per `alpaca_feed.py` pattern: stream thread enqueues, main thread drains on sleep, fires `pendingTickersEvent` with updated Ticker set)
- Ticker objects with `.last`, `.lastSize`, `.time` fields

Threading model: same as `alpaca_feed.py` — one daemon stream thread owning the asyncio loop, queue-passing to main thread, all ticker mutation on main thread.

---

## Account allocation tomorrow morning

| Bot | Data | Execution | Status |
|---|---|---|---|
| **Setup A (`bot_v3_hybrid.py`)** | **IBKR** (unchanged) | Alpaca paper (clientId=51, MAIN_APCA keys) | Sacred — no changes |
| **Setup B (`bot_alpaca_subbot.py`)** | **Databento** (NEW) | Alpaca paper (existing Setup B keys) | Migration target |
| Engine paper (framework) | IBKR (unchanged) | Alpaca paper (separate clientId) | Wave 4 paper, untouched |
| WB paper account | (idle) | (idle) | WB v2 research, no live deploy |

Both Setup A and Setup B watch the same universe (Setup B mirrors A's watchlist). Tomorrow we get a clean A/B comparison: same symbols, same scanner, different data feeds.

---

## What CC builds

### 1. `databento_live_feed.py`

New file. Architectural template: `alpaca_feed.py`. Backing library: `databento.Live()` (already a project dependency).

**Subscription shape:**
- Schema: `trades` (per-print stream) for Tier 1 — equivalent to `reqTickByTickData('AllLast')`
- Schema: `tbbo` (top-of-book bid/offer + trades) for Tier 2 — equivalent to `reqMktData('233')`
- Dataset: confirm with CC which is included in our Standard subscription. Likely `XNAS.ITCH` (Nasdaq) and/or `DBEQ.BASIC` (consolidated). **Verify against billing before building, not after.**
- Symbols: subscribed dynamically as Setup B's watchlist polls `session_state/<today>/watchlist.json`

**Ticker shape compatibility:**
- `Ticker.last` ← Databento trade event price
- `Ticker.lastSize` ← Databento trade event size
- `Ticker.time` ← Databento ts_event (nanosecond precision; convert to UTC datetime)
- `pendingTickersEvent` fires on main thread sleep drain, same shape ib_insync delivers

**Connection lifecycle:**
- `connect()` → instantiate `db.Live(key=...)` and start daemon thread
- `isConnected()` → check stream thread health
- `disconnect()` → close stream cleanly, drain remaining queue

**Resume support:**
- `reqHistoricalTicks` → `db.Historical()` call, same data shape, already proven in `databento_feed.py`

### 2. `bot_alpaca_subbot.py` modifications

Minimal. Add a feed-selector gate at boot:

```python
WB_SUBBOT_DATA_FEED = os.getenv("WB_SUBBOT_DATA_FEED", "ibkr").lower()
```

When `WB_SUBBOT_DATA_FEED=databento`:
- Skip IBKR Gateway connection entirely
- Instantiate `DatabentoLiveFeed` instead of `IB()`
- All other behavior identical (same watchlist polling, same Alpaca execution, same persistence, same logging)

When `WB_SUBBOT_DATA_FEED=ibkr` (default): existing behavior.

This way Setup B can flip back to IBKR data instantly if Databento has issues, no code re-deploy needed.

### 3. `daily_run_v3.sh` — Setup B launch

Update the Setup B launch block to set `WB_SUBBOT_DATA_FEED=databento`. Drop the IBKR clientId=2 dependency for Setup B since it's no longer needed.

**Important: Setup A's launch block stays exactly as-is.** Same IBKR Gateway dependency, same clientId, same data path. Sacred.

### 4. Parity validation harness

Once running tomorrow, we need to compare Setup A (IBKR) vs Setup B (Databento) on:

- **Tick count per symbol per minute** — does Databento see as many prints as IBKR?
- **First-tick timing** — when a new candidate is added, how fast does each feed deliver the first tick?
- **Trigger detection latency** — when both detectors see the same price level break, what's the timestamp delta between Setup A's signal and Setup B's signal?
- **Signal-to-fill latency** — from each bot's ENTRY signal → broker order submission → broker fill timestamp. (Both bots execute on Alpaca, so the broker side is constant.)
- **Trade counts** — same 10 symbols, same scanner, both bots running parallel: do they fire the same number of entries? Same ones?

CC builds `scripts/compare_subbot_vs_main.py` (or extends existing latency-diagnostic tool) that parses both bots' logs after market close tomorrow and produces:
- `cowork_reports/2026-05-19_databento_vs_ibkr_subbot_comparison.md`
- `cowork_reports/2026-05-19_databento_vs_ibkr_subbot_per_symbol.csv`

This is the deliverable that decides whether the migration is good.

---

## What CC must NOT do

- **Do NOT modify `bot_v3_hybrid.py`** (Setup A). Setup A is sacred. The new `WB_SUBBOT_DATA_FEED` switch lives in `bot_alpaca_subbot.py` only.
- **Do NOT modify `live_scanner.py`.** It already uses Databento; no change needed.
- **Do NOT modify the framework Wave 4 paper deploy.** Engine paper bot still runs on IBKR.
- **Do NOT touch `ibkr_feed.py` or `databento_feed.py` historical paths.** New file, new module.
- **Do NOT push real-money execution to Databento data.** Squeeze 6/15 cutover stays on IBKR data + Alpaca exec stack. Databento experiment is paper-only until the A/B data justifies the cutover.

---

## Pre-launch validation (CC)

Before tomorrow's 02:00 MT cron picks up the new Setup B configuration:

### 0. **Databento subscription-limit reconnaissance** (CRITICAL — do this first)

**Why this exists:** IBKR caps Tier 1 (`reqTickByTickData('AllLast')`) at **5 simultaneous subscriptions per client** (`bot_v3_hybrid.py:119` `TBT_MAX_SUBSCRIPTIONS=5`). The entire Tier 1/Tier 2 architecture — with `manage_tier1_subscriptions` rotating the 5 highest-volume symbols into the per-print stream while the rest ride on 250ms snapshots — exists because of this cap. **If Databento has analogous limits and we don't discover them until mid-session, we'll silently drop ticks on candidates and not know why.**

CC must answer ALL of the following before any other Databento work proceeds. **No assumptions, no "probably unlimited."** Verify each against the actual `db.Live()` SDK behavior and Databento's published limits.

1. **Per-connection symbol cap on `db.Live().subscribe(...)`.** Is there a maximum number of symbols a single Live session can subscribe to concurrently?
2. **Per-account concurrent-stream cap.** How many simultaneous `db.Live()` sessions can our API key hold open? (Setup B + scanner already uses one for the scanner; what does adding a second do?)
3. **Per-schema bandwidth / message-rate limits.** Does Databento throttle `trades` or `tbbo` streams above a certain msg/sec? Documented soft caps?
4. **Subscription-modify behavior.** Can we add/remove symbols from an active subscription mid-session, or do we need to tear down and reconnect? (IBKR allows mid-session add/remove; Databento's behavior here drives the rotation logic.)
5. **Dataset coverage.** Confirm the live tier of `XNAS.ITCH` and/or `DBEQ.BASIC` (or whichever datasets we're paying for on Standard) covers the small-cap squeeze universe. Our universe includes microfloat names — some discount data feeds gate access to harder-to-borrow / illiquid names. Verify against an actual subscription test, not the docs.
6. **Latency floor.** What's Databento's documented or measured first-tick latency from venue trade to client receipt? (For comparison to IBKR's typical 1-2s consolidated tape.)
7. **Authentication / session quirks.** Does the live API have time-of-day windows, quota refreshes, session-resume semantics, anything weird that would surprise us during a long-running session?
8. **Failure modes.** What happens when the connection drops mid-session? Auto-reconnect, exponential backoff, manual reconnect required? How does `db.Live()` signal disconnection to client code?

Output: `cowork_reports/2026-05-18_databento_subscription_limits.md`. Each question has a verified answer with citation (Databento docs URL + commit/section, or empirical test result with the actual SDK call). **"I think" or "probably" answers are not acceptable.**

**If any answer reveals a limit tighter than IBKR's** (e.g., ≤5 symbol cap, or strict tear-down-to-modify behavior), CC pauses the build and reports. We design the bot's subscription strategy around the *real* constraints, not the assumed ones. The Tier 1/Tier 2 rotation logic in Setup A may need to be mirrored on Setup B if caps are present.

**If limits are looser than IBKR's** (e.g., 100+ symbol cap, free mid-session add/remove), Setup B can flatten the architecture — just subscribe to the entire watchlist as Tier 1 equivalent. Different code path, different complexity profile.

**Either outcome is fine.** What's not fine is finding out tomorrow during market hours.

### 1. Verify Databento Live subscription is active

Run a 60-second smoke test: `db.Live().subscribe(dataset=..., schema="trades", symbols=["AAPL", "TSLA"])`, count messages, confirm the stream is delivering. Output to `cowork_reports/2026-05-18_databento_live_smoke.md`.

### 2. Verify Setup B can run end-to-end with the new feed against a small test universe

Manual smoke test, 10 minutes, 3 symbols. Confirm no crashes, ticks flow, the existing detector wiring works against Databento ticker objects.

### 3. Verify Setup A is untouched

`git diff` of `bot_v3_hybrid.py` shows zero changes.

### 4. Verify the launcher behavior

Dry-run `daily_run_v3.sh` with `WB_DRYRUN=1` (or whatever exists) — confirm Setup A launches with IBKR, Setup B launches with Databento.

### 5. Stress-test against the discovered limits

Once step 0 has answered the limit questions, build a **subscribe-to-N-symbols-and-watch** test that pushes Setup B near the documented cap (or 50 symbols if no cap exists) for 5 minutes. Confirm:
- All N streams deliver ticks at expected density
- No silent drops or capped messages
- Memory / CPU behavior is sane
- Mid-session subscription add/remove works as documented

Output: `cowork_reports/2026-05-18_databento_stress_test.md`. If we discover a real cap, this is also where we measure how the bot's existing watchlist-poll loop behaves at the limit — graceful rotation, hard refusal, or silent failure.

### Failure handling

If any pre-launch check fails, **roll back** to `WB_SUBBOT_DATA_FEED=ibkr` and report. **Do not flag it for tomorrow** — we'll catch up the next day.

---

## What we're learning tomorrow

This is a **measurement run**, not a commitment. Tomorrow's data answers five questions:

1. **Tick density:** does Databento match or beat IBKR for small-cap squeeze candidates?
2. **Latency:** is signal-detection time on Databento competitive with IBKR?
3. **Coverage:** does the squeeze detector fire on the same setups using Databento ticks as it does using IBKR ticks?
4. **Reliability:** does the Databento live stream stay up cleanly through a full session, or are there drops/reconnects?
5. **Subscription elasticity:** how does Databento behave at and around its discovered subscription limits during real market activity? (Pre-launch step 5 stresses this synthetically; tomorrow validates it under live load.)

If all five are good → we have a path to retire IBKR data and the $500 minimum + market-data-subscription stack. **The decision happens after the data lands, not before.**

If any are bad → Setup B reverts to IBKR data, we keep the current architecture, and we know what we know.

---

## Out of scope tomorrow

These don't get touched:

- Squeeze 6/15 real-money cutover — stays on the current stack regardless of Databento results
- Setup A — sacred, no modifications
- Engine framework Wave 4 — running independently on IBKR
- WB v2 Stage 0 — research workstream, no deploy
- Broker latency investigation (Tracks 1, 2, 3) — independent, ongoing

A successful Databento A/B doesn't trigger an immediate IBKR rip-out. It builds the case for one, **post-6/15.**

---

## Reporting

CC posts a status update when:
- `databento_live_feed.py` is built and smoke-tested
- Setup B is wired and dry-run-validated
- Setup A is verified untouched
- Tomorrow's session ends and the comparison report lands

---

## The reminder

We're already paying for Databento. Setup B is sitting unused. Tomorrow's market open is 16 hours away. Building the data-source independence we'd need to drop IBKR is a few hours of work — the kind of work that pays compounding returns the moment we finish it. Even if we don't migrate, we have the *option* to migrate, and we have measurement data on what we'd be giving up or gaining.

GO.
