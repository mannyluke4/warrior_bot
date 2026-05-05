# Dual-Feed Architecture — Stage 2 of TBT Migration

**Date:** 2026-05-05
**Author:** CC
**Per directive:** `DIRECTIVE_TICKBYTICK_MIGRATION.md` (Stage 2)
**Predecessor:** `cowork_reports/2026-05-05_tickbytick_capacity.md` (cap=5 confirmed)
**Status:** ✅ Plumbing complete, dormant. No live behavior change until Stage 3 turns it on.

---

## What changed

Both `bot_v3_hybrid.py` and `bot_alpaca_subbot.py` now have a two-tier
subscription model wired in. Every watchlist symbol lives in one of two tiers:

| Tier | API call | Cadence | Symbol cap |
|---|---|---|---|
| **Tier 2 (default)** | `reqMktData(contract, '233', False, False)` | 250ms snapshots | unlimited |
| **Tier 1 (opt-in)** | `reqTickByTickData(contract, 'AllLast', 0, False)` | every print | **5** (probed) |

Tier 2 is the existing path — it has not been removed. Tier 1 is new. Symbols
move between tiers via `subscribe_tick_by_tick(sym)` /
`unsubscribe_tick_by_tick(sym)`. Stage 3 will decide *when* to call those;
Stage 2 only adds the plumbing.

## Code-level changes

### Module-level constants

Near the other strategy gates (~line 91):

```python
TBT_ENABLED = os.getenv("WB_TBT_ENABLED", "0") == "1"
TBT_MAX_SUBSCRIPTIONS = int(os.getenv("WB_TBT_MAX", "5"))
```

Master gate is OFF until Stage 3 ships. The runtime cap matches the Stage 1
probe; if a future probe finds a higher cap, override via env var.

### BotState fields

```python
self.tier: dict = {}                        # symbol → "snapshot" | "tick_by_tick"
self.tbt_tickers: dict = {}                 # symbol → ib_insync Ticker
self.tbt_last_processed_index: dict = {}    # how far we've drained ticker.tickByTicks
self.tbt_subscribed_at: dict = {}           # when promoted (for cooldown)
```

### `subscribe_tick_by_tick(symbol, reason)` / `unsubscribe_tick_by_tick(symbol, reason)`

Defined right after `subscribe_symbol`. Idempotent. Both log a structured
`[TIER] PROMOTE` / `[TIER] DEMOTE` line with the reason, capacity, and (for
demote) how long the symbol held its slot.

`subscribe_tick_by_tick` enforces `TBT_MAX_SUBSCRIPTIONS` as a backstop: even
if Stage 3 mistakenly tries to oversubscribe, the helper refuses and returns
`False`. Stage 3 is the source of truth on which 5 symbols win the slots, but
this guard keeps a Stage 3 bug from crashing the live bot.

### `on_ticker_update` dispatch

```python
def on_ticker_update(tickers):
    state.last_on_ticker_fire = datetime.now(ET)
    for ticker in tickers:
        sym = ticker.contract.symbol if ticker.contract else None
        if sym and state.tier.get(sym) == "tick_by_tick":
            _drain_tick_by_tick_ticker(ticker)
        else:
            _process_ticker(ticker)
```

Crucial dedupe: a Tier 1 symbol's ticker still receives `reqMktData` snapshot
updates (because we don't cancel that subscription). When `pendingTickersEvent`
fires for that ticker, the dispatch routes it to `_drain_tick_by_tick_ticker`,
which only reads `ticker.tickByTicks`. The snapshot fields are silently
ignored — no double-counting.

### `_drain_tick_by_tick_ticker(ticker)`

New function. Walks `ticker.tickByTicks[last_idx:]`, feeds each entry through
the same downstream that snapshot ticks use:

1. Update `state.tick_counts` / `state.last_tick_time` / `state.last_tick_price`
2. Call `_process_trade_tick(symbol, price, size, ts)` for every print

`tk.time` from `reqTickByTickData` is a UTC `datetime`; we convert to ET to
match the rest of the bot's timestamp convention.

### `_process_trade_tick(symbol, price, size, ts)` — extracted helper

The post-extraction body of the old `_process_ticker` (tick-buffer append,
live-tick counter, bar builders, box bar builder, `check_triggers`, EPL,
squeeze + short exits, WB tick handling) was extracted into this shared
helper without any logic change. Both Tier 1 and Tier 2 paths feed it. By
keeping all downstream consumers in one function, Stage 2 cannot accidentally
introduce path-specific behavioral drift.

### `_process_ticker(ticker)` — Tier 2 only

Now only runs the snapshot-specific extraction (read `ticker.last`,
`ticker.lastSize`, fall back to bid/ask for health monitoring) and then
delegates to `_process_trade_tick` if it has a real trade. Body shrunk
materially.

### Default tier on subscribe

`subscribe_symbol` now ends with `state.tier.setdefault(symbol, "snapshot")`.
Same as before behaviorally — every symbol the bot subscribes to starts on
the snapshot path until something explicitly promotes it.

## Behavior change at runtime

**Zero, until Stage 3.** Stage 2 alone is structurally complete but
functionally inert: nothing in the code calls `subscribe_tick_by_tick`, so
no symbol ever leaves Tier 2, so the dispatch always takes the
`else: _process_ticker(ticker)` branch — which is the legacy code path
factored into a shared helper, line-for-line equivalent.

This is exactly what the directive intends. The Stage 2 PR is safe to ship
mid-trading-day in principle, though we'll let the live bots run on the
already-loaded code (Python loads at process start) and the next restart
will pick up the new module.

## Why it's safe

The dispatch fall-through cases all preserve old behavior:

- `ticker.contract is None`: dispatch hits `else` branch → `_process_ticker`
  hits the same `if not contract: return` it always had.
- `state.tier.get(sym)` returns `None` (symbol subscribed before Stage 2):
  `None != "tick_by_tick"`, so → `_process_ticker`. Old path.
- `state.tier[sym] == "snapshot"`: `!= "tick_by_tick"` → `_process_ticker`.
  Old path.
- `state.tier[sym] == "tick_by_tick"`: only possible if `subscribe_tick_by_tick`
  was called, which doesn't happen yet in Stage 2.

So the new dispatch is a strict superset of the old: it adds a new branch
without changing any existing one.

## What Stage 3 needs to add

- `manage_tier1_subscriptions()` running every 30s
- Priority scoring (1000 / 500 / 200 / 100 / 50 / 20-50 / 0 from the directive)
- Cooldown enforcement (`can_demote(sym)`: at least 5 min in Tier 1 + no active
  position + no PRIMED/ARMED/WAVE_OBSERVING≥5 detector state)
- Wiring of the `[TIER] STATUS` periodic log line
- Acceptance check #5 from the directive (next-day historical tick comparison
  on a Tier-1-promoted symbol)

The plumbing is in place. Stage 3 is the policy layer on top.

## Files modified

- `bot_v3_hybrid.py` — TBT constants, BotState fields, subscribe/unsubscribe
  helpers, `on_ticker_update` dispatch, `_drain_tick_by_tick_ticker`,
  refactored `_process_ticker`, new `_process_trade_tick` extracted helper.
- `bot_alpaca_subbot.py` — same edits, mirrored.
- `cowork_reports/2026-05-05_dual_feed_architecture.md` — this file.

Both bots `py_compile` clean. No tests added (Stage 2 is plumbing; Stage 3
will need behavior tests for promotion/demotion).

---

*Stage 2 is the dual carriageway. Stage 3 is the traffic light deciding
who gets to use the fast lane.*
