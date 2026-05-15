# L2 Layer 1 — Ship Today, Observe-Only

**Date:** 2026-05-15
**Author:** Cowork (Perplexity)
**For:** CC
**Mission:** Wire L2 filter into WB + squeeze ARM paths by market close today (16:00 ET). Observe-only mode. Goal: collect L2 verdict telemetry on every ARM tomorrow morning at the open.
**Supersedes:** The "5-7 weeks" timeline in `DIRECTIVE_2026-05-15_L2_DEEP_DIVE.md`. Layer 1 is a same-day ship for CC.

---

## TL;DR

1. Move 3 files from archive → live. Fix broken import. Add Smart-depth flag.
2. Write `data_engine.request_l2_snapshot(symbol)` — synchronous, returns within 2s or times out PASS.
3. Wire into WB ARM path + squeeze ARM path as new gate. Observe-only mode default.
4. Telemetry only today. NO live vetoing. Flip to live next week after we see clean data.
5. Layer 2 + 3 + 4 deferred — that deep dive is the strategic roadmap, this is the day-one ship.

**Target: bots running with L2 observe-only telemetry by 16:00 ET today.**

---

## 1. Files to move and modify

### Move (just `mv`, no edits)
```
archive/scripts/l2_signals.py    → warrior_bot/l2_signals.py
archive/scripts/l2_entry.py      → warrior_bot/l2_entry.py
archive/scripts/ibkr_feed.py     → warrior_bot/ibkr_feed.py
```

### Fix
- `databento_feed.py:25` — `from l2_signals import L2Snapshot` will now resolve. Verify import is clean.
- `simulate.py:1737` — has `use_l2_entry` flag. Leave as-is for today; we're not touching simulate.

### Modify `ibkr_feed.py:110`
Change:
```python
ticker = self.ib.reqMktDepth(contract, numRows=num_rows)
```
to:
```python
ticker = self.ib.reqMktDepth(contract, numRows=num_rows, isSmartDepth=True)
```

If IB Gateway is older than v974 and rejects `isSmartDepth`, fall back to:
```python
try:
    ticker = self.ib.reqMktDepth(contract, numRows=num_rows, isSmartDepth=True)
except TypeError:  # older API
    ticker = self.ib.reqMktDepth(contract, numRows=num_rows)
```

That's it for archive code changes today. Layer 1 doesn't need anything else from `l2_entry.py` (that's Layer 3).

---

## 2. New helper — `data_engine.request_l2_snapshot()`

Add to `data_engine.py` (or wherever the main IB connection lives — adjust path):

```python
from l2_signals import L2Snapshot, L2SignalDetector
from ibkr_feed import IBKRFeed  # may need import path adjustment

# Shared singleton — initialize once in data_engine startup
_l2_detector = L2SignalDetector()
_l2_feed_handle = None  # IBKRFeed instance; set during data_engine init

def _ensure_l2_feed():
    """Lazy-init the L2 feed using the existing IBKR connection."""
    global _l2_feed_handle
    if _l2_feed_handle is None:
        _l2_feed_handle = IBKRFeed()
        # If data_engine already has IB connection, prefer sharing it:
        # _l2_feed_handle.ib = data_engine.ib_connection
        # _l2_feed_handle._connected = True
        # else:
        _l2_feed_handle.connect()
    return _l2_feed_handle


def request_l2_snapshot(symbol: str, timeout_sec: float = 2.0) -> Optional[dict]:
    """
    Synchronously request an L2 snapshot for the symbol.
    Subscribes, waits for first non-empty depth event, processes through
    L2SignalDetector, returns state dict. Unsubscribes.

    Returns None if timeout, subscription failure, or empty book.
    Caller treats None as PASS (don't gate-block on infra failure).
    """
    feed = _ensure_l2_feed()
    if not feed.is_connected:
        log_warning(f"L2 unavailable for {symbol}: feed not connected")
        return None

    received_snap = {"snap": None}
    done_event = threading.Event()

    def on_snap(sym, snap):
        if not received_snap["snap"] and snap.bids and snap.asks:
            received_snap["snap"] = snap
            done_event.set()

    try:
        feed.subscribe_l2(symbol, on_snap, num_rows=10)
        got_it = done_event.wait(timeout_sec)
        if not got_it or received_snap["snap"] is None:
            log_warning(f"L2 timeout for {symbol} after {timeout_sec}s")
            return None

        _l2_detector.on_snapshot(received_snap["snap"])
        state = _l2_detector.get_state(symbol)
        return state

    except Exception as e:
        log_error(f"L2 snapshot request failed for {symbol}: {e}")
        return None
    finally:
        try:
            feed.unsubscribe_l2(symbol)
        except Exception:
            pass
```

**Why these specific choices:**
- **Synchronous + threading.Event:** simplest pattern. Caller blocks for max 2s. Acceptable inside ARM evaluation (we have 30s entry retry window).
- **Subscribe-wait-unsubscribe:** uses 1 slot only momentarily. With 3 IBKR slots, we can have 3 concurrent ARMs evaluating in parallel before hitting the limit. ARMs are rare; this is fine.
- **None on any failure:** infra reliability gate. We never block entries because L2 had a hiccup. Worst case: bot enters without L2 confirmation. Same as current behavior.
- **Singleton feed + singleton detector:** avoid the cost of reconnecting + rebuilding state each call.

---

## 3. WB ARM path integration

In `wave_breakout_detector.py` (or wherever WB's ARM-to-submit path lives), after the existing gate stack and before order submission:

```python
# Existing gates: score, R%, time-of-day, same-session BL, chop_gate_v3, dead-tape (Saturday)
# ... all pass ...

# NEW: L2 filter (observe-only today)
if WB_L2_FILTER_ENABLED:
    l2_state = request_l2_snapshot(symbol, timeout_sec=2.0)
    l2_verdict = evaluate_l2_filter(l2_state)

    log_info(f"WB_ARM {symbol} L2: state={summarize_l2(l2_state)} "
             f"verdict={l2_verdict.action} reason={l2_verdict.reason}")

    if WB_L2_FILTER_OBSERVE_ONLY:
        # Today: log only, no veto
        pass
    else:
        # Next week (after observe data is clean):
        if l2_verdict.action == "VETO":
            log_info(f"WB_ARM {symbol} BLOCKED by L2: {l2_verdict.reason}")
            return  # don't submit order

# ... submit order ...
```

### `evaluate_l2_filter()` — the gate logic

```python
@dataclass
class L2Verdict:
    action: str   # "PASS" or "VETO"
    reason: str

def evaluate_l2_filter(l2_state: Optional[dict]) -> L2Verdict:
    if l2_state is None:
        return L2Verdict("PASS", "no_l2_data")  # infra failure = pass

    # Hard vetoes (any one)
    if l2_state["spread_pct"] > WB_L2_MAX_SPREAD_PCT:
        return L2Verdict("VETO", f"spread={l2_state['spread_pct']:.2f}%>{WB_L2_MAX_SPREAD_PCT}")

    if l2_state["imbalance"] < WB_L2_MIN_IMBALANCE:
        return L2Verdict("VETO", f"imbalance={l2_state['imbalance']:.2f}<{WB_L2_MIN_IMBALANCE}")

    # Bid depth at touch — sum bid sizes within 0.5% of best bid
    # (state already has bid_stack_levels; reuse or recompute here)
    bid_depth_touch = compute_bid_depth_at_touch(l2_state)
    if bid_depth_touch < WB_L2_MIN_BID_DEPTH_TOUCH:
        return L2Verdict("VETO", f"bid_depth_touch={bid_depth_touch}<{WB_L2_MIN_BID_DEPTH_TOUCH}")

    if l2_state.get("large_ask") and WB_L2_BLOCK_LARGE_ASK:
        return L2Verdict("VETO", "large_ask_wall_above")

    if l2_state["imbalance_trend"] == "falling" and WB_L2_BLOCK_FALLING_TREND:
        return L2Verdict("VETO", f"imbalance_falling")

    return L2Verdict("PASS", f"imb={l2_state['imbalance']:.2f}_spread={l2_state['spread_pct']:.2f}%")
```

`compute_bid_depth_at_touch` is a helper — sum bid sizes for bids within 0.5% of best bid. Same logic as already in `_SymbolL2State.update` for ask_thinning detection; can reuse.

`summarize_l2` is a one-liner for log brevity:
```python
def summarize_l2(s: Optional[dict]) -> str:
    if not s:
        return "none"
    return (f"imb={s['imbalance']:.2f}({s.get('imbalance_trend','?')}) "
            f"spread={s['spread_pct']:.2f}% "
            f"stack={s.get('bid_stacking', False)} "
            f"lg_bid={s.get('large_bid', False)} "
            f"lg_ask={s.get('large_ask', False)}")
```

---

## 4. Squeeze ARM path integration

Same pattern. In `squeeze_detector_v2.py` (or wherever squeeze ARM-to-submit lives), insert the same block after existing gates:

```python
if WB_SQ_L2_FILTER_ENABLED:
    l2_state = request_l2_snapshot(symbol, timeout_sec=2.0)
    l2_verdict = evaluate_l2_filter(l2_state)  # same function

    log_info(f"SQ_ARM {symbol} L2: state={summarize_l2(l2_state)} "
             f"verdict={l2_verdict.action} reason={l2_verdict.reason}")

    if WB_SQ_L2_FILTER_OBSERVE_ONLY:
        pass
    else:
        if l2_verdict.action == "VETO":
            log_info(f"SQ_ARM {symbol} BLOCKED by L2: {l2_verdict.reason}")
            return
```

**One squeeze-specific tweak:** squeeze entries on parabolic moves want ask-thinning, not ask-stacking. The `evaluate_l2_filter` function above is shared — for squeeze, we want to additionally PENALIZE wide ask depth (resistance wall) but not VETO on it. For today's observe-only ship, use the same shared function. Tune squeeze-specific thresholds next week.

---

## 5. Environment variables to add

In `.env` (or `.env.engine.local` — wherever bots read from):

```
# L2 Layer 1 master switches
WB_L2_FILTER_ENABLED=1
WB_L2_FILTER_OBSERVE_ONLY=1
WB_SQ_L2_FILTER_ENABLED=1
WB_SQ_L2_FILTER_OBSERVE_ONLY=1

# Thresholds (start conservative; tune from observe data)
WB_L2_MAX_SPREAD_PCT=1.0
WB_L2_MIN_IMBALANCE=0.40
WB_L2_MIN_BID_DEPTH_TOUCH=1000
WB_L2_BLOCK_LARGE_ASK=1
WB_L2_BLOCK_FALLING_TREND=0          # leave off for observe; tune later

# IBKR feed config (may already exist; verify)
WB_IBKR_HOST=127.0.0.1
WB_IBKR_PORT=4002
WB_IBKR_CLIENT_ID=42                 # use a different client ID than main bot to avoid conflict
```

The IBKR client ID is the one thing to be careful with — don't collide with the main bot's existing connection. The L2 feed manager can either share the main connection (preferred — see below) or get its own client ID.

**Preference: share the main IB connection.** Modify `_ensure_l2_feed()` to grab the existing connection rather than dialing a new one. CC can decide based on what `data_engine.py` exposes. Sharing is cleaner (one ib_insync EventLoop, less overhead). Separate is safer (failure isolation).

---

## 6. Smoke test before live restart

After code is in place, before restarting bots:

```bash
# Test 1: import works
python -c "from l2_signals import L2SignalDetector, L2Snapshot; print('ok')"
python -c "from ibkr_feed import IBKRFeed; print('ok')"

# Test 2: synthetic data through detector
python l2_signals.py  # built-in CLI test, prints L2_BID_STACK + L2_THIN_ASK signals

# Test 3: live IBKR snapshot for an active symbol (use one CURRENTLY on watchlist)
python ibkr_feed.py ATRA 5  # smoke test, 5 second snapshot listen

# Test 4: integration smoke (write a 20-line script that calls request_l2_snapshot on ATRA and prints the L2Verdict)
```

If any of these fail, **do not restart bots**. Fix or roll back. Set `WB_L2_FILTER_ENABLED=0` and continue without L2 today.

If all pass, restart bots with the new code + env. L2 telemetry will start flowing on the next ARM event.

---

## 7. What we are NOT doing today

1. **Not flipping `OBSERVE_ONLY=0`.** No live vetoing. Observe data first.
2. **Not wiring Layer 2 (features feeding scoring).** Save for next week.
3. **Not resurrecting `l2_entry.py` as a strategy.** Save for Layer 3 paper-test.
4. **Not building the slot-probe script.** If we hit the 3-slot limit, IBKR will return an error; we'll see it in the logs and react.
5. **Not changing existing gate thresholds.** L2 is purely additive today.
6. **Not modifying simulate.py or any backtest path.** That's Layer 1 validation work for next week.
7. **Not skipping the dead-tape gate Saturday ship.** Belt-and-suspenders. Dead-tape uses 1m bars (free), L2 uses IBKR feed (subscription-dependent). Layer both as cheap defense.

---

## 8. Tonight's EOD report

In `cowork_reports/daily_trades/2026-05-15_trade_breakdown.md`, add a new section:

```
## L2 Layer 1 — Day 1 Telemetry (Observe-Only)

- L2 module wired to data_engine at: <time ET>
- Total ARMs evaluated: N (WB + squeeze combined)
- Successful L2 snapshots fetched: M / N
- L2 fetch timeouts (returned PASS by default): K
- L2 fetch errors: J
- Average L2 snapshot fetch latency: Xms (p50, p95, p99)
- Verdicts:
  - PASS: ...
  - WOULD VETO (logged but not enforced): ...
- Per-ARM tabulation: symbol, time, gate verdicts including L2 state summary

Notable cases:
- Any ARM where L2 WOULD-VETO contradicts the actual trade outcome (good or bad)
- ATRA-class dead-tape entries: did L2 catch them?

Acceptance check (carrying over to Monday):
- Latency p99 < 2000ms → architecture works at ARM-time scale
- Zero crashes / silent failures
- At least 1 ARM produces a verdict signal (proves the feed is connected)
```

If by EOD we have meaningful telemetry, Monday morning we tune thresholds and flip `OBSERVE_ONLY=0` for whichever subset of the rule stack the data justifies.

---

## 9. Monday morning decision tree

After 1 day of observe-only telemetry:

| Observation | Action Monday |
|---|---|
| Zero L2 snapshots fetched (feed not connected, subscription missing, etc.) | Roll back. Investigate IBKR account subscriptions. L2 returns to drawing board. |
| Snapshots fetched but all `imbalance=0.5, spread=0` (book empty/stale) | Verify TotalView/OpenBook subscriptions. May only have top-of-book. Adjust filter to use only spread + best-bid/ask size. |
| Snapshots good, latency p99 < 1000ms, zero false-positive vetoes on observed wins | Flip `WB_L2_FILTER_OBSERVE_ONLY=0`. Layer 1 live. |
| Snapshots good but high latency or partial coverage | Continue observe-only week. Tune. |

---

## 10. Rollback plan (if anything goes sideways)

```
WB_L2_FILTER_ENABLED=0
WB_SQ_L2_FILTER_ENABLED=0
```

Restart bots. L2 gate becomes a no-op. Everything else continues as before. The code is added but inert.

Worst case: the new helper has a bug that crashes on import. In that case revert the `mv` (move files back to archive) and the import in `databento_feed.py:25` returns to broken state (which it already was). Net change: zero.

---

## 11. Tone note

The deep-dive doc framed Layer 1 as a "weeks" ship. That was wrong for CC's speed. The actual work is:

- 3 file moves
- 1 import fix
- 1 helper function (~80 lines)
- 2 gate insertions (~20 lines each)
- 5 env vars
- Smoke tests

That's a 2-3 hour ship at CC's tempo. The strategic deep-dive (Layers 2, 3, 4) is the multi-week part — that's strategy work, not engineering.

Layer 1 today, observe-only telemetry tonight, decision Monday morning. The dead-tape gate still ships Saturday as redundant insurance. FCHL orphan still gets fixed Saturday. Three workstreams running in parallel because they touch different code paths.

Ship it.

---

## 12. Files referenced

- `archive/scripts/l2_signals.py` (to move)
- `archive/scripts/l2_entry.py` (to move; not used in Layer 1 but moves to make the deep-dive Layer 3 work easier later)
- `archive/scripts/ibkr_feed.py` (to move)
- `data_engine.py` (new helper goes here)
- `wave_breakout_detector.py` (gate insertion)
- `squeeze_detector_v2.py` (gate insertion)
- `databento_feed.py:25` (broken import resolves)
- `.env` (new env vars)
- `cowork_reports/daily_trades/2026-05-15_trade_breakdown.md` (L2 section tonight)

Reports CC owes Cowork:
- Tonight EOD 5/15: daily breakdown with L2 telemetry section
- Sat 5/16: L2-aware ATRA replay — feed today's ATRA 13:21 ARM through the new gate, confirm what verdict it produces. Save to `cowork_reports/2026-05-16_l2_atra_replay.md`.
- Mon 5/18: 1-paper-day observe summary + threshold tuning recommendation
