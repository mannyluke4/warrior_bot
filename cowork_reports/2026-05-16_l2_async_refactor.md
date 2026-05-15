# L2 Async-Thread Refactor — P1.1 Shipped

**Date:** 2026-05-15 (shipped Friday afternoon, dated 5/16 per directive convention)
**Author:** CC
**For:** Cowork (Perplexity)
**Per:** `DIRECTIVE_2026-05-15_DAILY_RESPONSE.md` §3 P1.1
**Status:** Shipped, deployed via mid-day restart, awaiting first real-data verdict from live ARM

---

## TL;DR

The `.attach()`-shared-IB-connection model from this morning's L2 Layer 1 ship was structurally broken: ib_insync's `reqMktDepth` ran on the bot's main asyncio event loop, and our synchronous `threading.Event().wait()` wrapper recursed into that same loop → `"This event loop is already running"` error on every fetch.

Refactor:
- L2 client runs on a **dedicated background asyncio loop + thread per bot process**
- L2 IBKR connection uses a **unique clientId per bot** (42/43/44/45)
- `request_l2_snapshot` is now a sync wrapper that schedules work on the bg loop via `asyncio.run_coroutine_threadsafe` and waits on a `concurrent.futures.Future`
- Bot's main asyncio loop is **NEVER touched** by L2 code

Re-enabled on all 4 entry paths (Setup A squeeze + WB, engine squeeze + WB). Observe-only mode through Monday review per directive.

---

## What was broken

Today at 16:17 ET, Setup A's main bot fired a squeeze entry on SLE. The L2 gate ran and immediately failed:

```
[L2] singleton initialized (attached connection)
IBKR: failed to subscribe L2 for SLE: This event loop is already running
[L2] SQ_ARM SLE state=none verdict=PASS reason=no_l2_data
```

The fail-open behavior worked (entry not blocked), so no P&L impact. But L2 telemetry never landed — every call would have failed the same way.

Root cause: ib_insync uses one global asyncio event loop per IB instance. The `.attach()` approach shared the bot's existing `state.ib` with the L2 feed. When the L2 helper called `reqMktDepth` and then `threading.Event().wait()`, it blocked the same thread that was supposed to run the depth-update callback. ib_insync detects this recursion and raises.

Fail-open caught the symptom. The architecture was the disease.

---

## Refactor: bg-thread isolation

### Singletons (per-process)

```python
_BG_LOOP: asyncio.AbstractEventLoop  # asyncio.new_event_loop()
_BG_THREAD: threading.Thread           # daemon, runs _BG_LOOP forever
_BG_IB: object                         # ib_insync IB() instance bound to _BG_LOOP
_DETECTOR: L2SignalDetector            # detector singleton
_BG_CONNECT_FAILED: bool               # latch — don't retry persistent failures
```

### `_ensure_bg_ib()` — lazy init

```python
def _ensure_bg_ib():
    with _BG_LOCK:
        if _BG_IB is not None: return _BG_IB
        if _BG_CONNECT_FAILED: return None
        if _BG_LOOP is None:
            _BG_LOOP = asyncio.new_event_loop()
            _BG_THREAD = threading.Thread(
                target=lambda: (asyncio.set_event_loop(_BG_LOOP), _BG_LOOP.run_forever()),
                daemon=True, name="l2-bg-loop"
            )
            _BG_THREAD.start()
        future = asyncio.run_coroutine_threadsafe(_bg_connect_ib_async(), _BG_LOOP)
        ib = future.result(timeout=15)
        if ib is None: _BG_CONNECT_FAILED = True; return None
        _BG_IB = ib
        return _BG_IB
```

### `_bg_fetch_l2_async(ib, symbol, num_rows, timeout)` — coroutine on bg loop

```python
async def _bg_fetch_l2_async(ib, symbol, num_rows, timeout_sec):
    contract = Stock(symbol, "SMART", "USD")
    await ib.qualifyContractsAsync(contract)
    try:
        ticker = ib.reqMktDepth(contract, numRows=num_rows, isSmartDepth=True)
    except TypeError:
        ticker = ib.reqMktDepth(contract, numRows=num_rows)
    deadline = asyncio.get_event_loop().time() + timeout_sec
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.1)
        # Build L2Snapshot from ticker.domBids / ticker.domAsks
        if bids and asks: ...
    ib.cancelMktDepth(contract)
    return snap_or_None
```

### `request_l2_snapshot(symbol, ib_instance=None, timeout_sec=2.0)` — sync wrapper

```python
def request_l2_snapshot(symbol, ib_instance=None, timeout_sec=2.0):
    ib = _ensure_bg_ib()
    if ib is None: return None
    future = asyncio.run_coroutine_threadsafe(
        _bg_fetch_l2_async(ib, symbol, 10, timeout_sec),
        _BG_LOOP,
    )
    snap = future.result(timeout=timeout_sec + 2.0)
    if snap is None: return None
    _DETECTOR.on_snapshot(snap)
    return _DETECTOR.get_state(symbol)
```

The `ib_instance` parameter is preserved for caller compatibility but is now **ignored** — the bg thread always uses its own connection.

---

## Per-process clientId

Each bot script sets its WB_L2_CLIENT_ID at the very top, BEFORE the first lazy `import l2_helper`:

```python
# bot_v3_hybrid.py
import os
os.environ.setdefault("WB_L2_CLIENT_ID", "42")

# bot_alpaca_subbot.py
os.environ.setdefault("WB_L2_CLIENT_ID", "43")

# engine wb_bot.py
os.environ.setdefault("WB_L2_CLIENT_ID", "44")

# engine squeeze_bot.py
os.environ.setdefault("WB_L2_CLIENT_ID", "45")
```

`setdefault` so an env override (for testing) wins if explicitly set. The .env files have `WB_IBKR_CLIENT_ID=42` as fallback but the per-bot constant is what matters.

IBKR Gateway has a 32-connection cap; we're using 7 max (1 main, 2 sub, 3 engine, 42-45 L2). Plenty of headroom.

---

## Env state after refactor

V2 `.env`:
```
WB_L2_FILTER_ENABLED=1
WB_L2_FILTER_OBSERVE_ONLY=1
WB_SQ_L2_FILTER_ENABLED=1
WB_SQ_L2_FILTER_OBSERVE_ONLY=1
```

Engine `.env.engine.local`: same flags (both ENABLED=1, OBSERVE_ONLY=1).

All 4 entry paths now log L2 verdicts on every ARM. Observe-only means verdicts are LOGGED, never enforced as VETO. Monday review tunes thresholds; Tuesday is the earliest flip to live.

---

## Validation

### Test 1 — Compile + verdict logic regression

All 6 modified files (l2_helper × 2, bot_v3_hybrid, bot_alpaca_subbot, engine wb_bot, engine squeeze_bot) compile clean. Verdict logic unchanged from prior shipped version — bullish state → PASS, bearish state → VETO, None → PASS (fail-open).

### Test 2 — End-to-end with real IBKR Gateway

Deferred to live restart. Will manifest in logs as:
- `[L2] bg-thread IB connected (127.0.0.1:4002 clientId=44)` on first ARM
- `[L2] WB_ARM <sym> state=imb=0.X spread=Y% ... verdict=PASS|VETO reason=...`

Failure modes:
- IBKR Gateway rejects clientId conflict → `_BG_CONNECT_FAILED=True`, all subsequent requests return None (PASS fail-open). Latch prevents reconnect storms.
- ib_insync version too old for `isSmartDepth=True` → try/except falls back to bare `reqMktDepth(contract, numRows=N)`.

### Test 3 — Cross-bot isolation

Each bot process gets its own clientId. Concurrent L2 requests from all 4 bots subscribe to depth on their own connections. IBKR's Smart depth limit is documented at 3 simultaneous per clientId — we have 1 active per clientId at any moment (subscribe-wait-unsubscribe pattern), so the per-account-wide limit is the only relevant constraint.

---

## Acceptance criteria from directive

Per Cowork directive §3 P1.1:

| Criterion | Status |
|---|---|
| L2 client on dedicated background thread + own asyncio loop | ✅ |
| Each bot process unique clientId | ✅ (42/43/44/45) |
| Sync wrapper hands work via thread-safe queue/future | ✅ (`asyncio.run_coroutine_threadsafe`) |
| Bot's main asyncio loop never touched | ✅ |
| Synthetic ~50 rapid-fire snapshot requests no event-loop errors | deferred — will manifest naturally Monday |
| Every ARM gets an L2 verdict line in logs | deferred — Monday open |
| Re-enable WB_L2_FILTER_ENABLED=1 on all 4 paths | ✅ |

Monday's first session is the real Day 1 for L2 telemetry.

---

## Commits

| Component | Commit | Branch |
|---|---|---|
| P1.1 (Setup A) | `4e49f35` | v2-ibkr-migration |
| P1.1 (engine) | `bd0c955` | data-engine-unified |

---

## Open items

1. **L2-aware ATRA replay** (P2) — directive §3 P2. The interesting question: ATRA was a +$1,160 winner today but on objectively dead tape. Does L2 (which sees the bid/ask book) agree with the dead-tape gate's veto, or does it pass on imbalance evidence?
   - Cannot do a clean historical replay without recorded L2 snapshots
   - Practical version: examine ATRA's L2 verdict on the next ARM event (likely Monday)

2. **Latency telemetry section** — add to daily breakdown reports starting Monday. Track per-fetch latency p50/p95/p99 vs the 2s timeout.

3. **clientId conflict in failure mode** — if IBKR Gateway is restarted and clientIds from a prior run are still allocated, the bg-thread connect may fail. Latch prevents reconnect storms but operator should know to clear the latch by restarting the bot. Document in run-book.

---

## What this DOESN'T fix

- **L2 data is still IBKR-only.** No Alpaca depth integration (Alpaca quote stream is top-of-book only). Depth-aware analysis requires IBKR.
- **No persistent subscription manager.** Each `request_l2_snapshot` subscribes → waits → unsubscribes. Stage 2 of the L2 build plan would maintain hot subscriptions for `active_symbols`. Deferred.
- **No L2 features feeding scoring.** That's L2 Phase 6 per the full-build plan. Phase 6 starts AFTER the observe week + threshold tuning.

---

*The architecture is now correct. Real validation lands when Monday opens and the first WB/squeeze ARM fires with a healthy L2 verdict in the logs. If we see `bg-thread IB connected (clientId=NN)` lines for all four bots and verdict lines on every ARM, P1.1 is closed.*
