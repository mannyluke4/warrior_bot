# L2 Full Build Plan — Methodical, No Time Pressure

**Date:** 2026-05-15
**Author:** Cowork (Perplexity)
**For:** CC
**Mission:** Wire L2 into the bot end-to-end. Work the steps in order, no shortcuts. Some steps will land in one session, others may span sessions. Quality and correctness over speed.
**Supersedes:** Both `DIRECTIVE_2026-05-15_L2_DEEP_DIVE.md` (too speculative on timelines) and `DIRECTIVE_2026-05-15_L2_LAYER1_TODAY.md` (cut too much to fit a deadline). This is the real plan.

---

## Approach

Work the build in **phases**. Each phase has clear inputs, deliverables, and acceptance criteria. Each phase produces a report. We do not move to the next phase until the current one validates.

**No time estimates.** The phases are sequenced by dependency, not by deadline. If a phase takes longer than expected, that's information — it means we found something we didn't know.

**The whole build runs in observe-only mode through the early phases.** We don't flip anything to live veto until we have telemetry showing the gates behave correctly. The bot keeps running its existing strategies the whole time; L2 is purely additive.

---

## Phase 0 — Pre-flight verification

Before touching any code, confirm prerequisites:

### 0.1 — IBKR subscription audit
- Check IB Gateway account market data subscriptions
- Confirm we have: Nasdaq TotalView (or equivalent NASDAQ L2), NYSE OpenBook (or equivalent NYSE L2)
- If only top-of-book is available, document that and continue (L2 still useful, just less informative)
- Output: a line in the Phase 0 report stating which feeds are subscribed

### 0.2 — IB Gateway version check
- Query IB Gateway version (TWS API method or About menu)
- If v974+: Smart depth is available; use it
- If older: single-exchange depth fallback; document version in report
- Output: version number + Smart-depth availability flag

### 0.3 — Slot capacity probe
- Mirror the existing TBT probe pattern at `scripts/probe_tickbytick_capacity.py`
- New script: `scripts/probe_market_depth_capacity.py`
- Subscribe `reqMktDepth` to test symbols one at a time until IBKR returns the limit error
- Output: confirmed slot count (likely 3 based on IBKR docs for 0-399 market data lines tier)

### 0.4 — Connection model decision
Check `data_engine.py` to determine whether the L2 feed should:
- **Share the existing IB connection** (preferred — one EventLoop, one connection, simpler state)
- **Use a separate client ID** (failure-isolated but more overhead)

CC's call based on what `data_engine.py` currently exposes. Document the decision in the Phase 0 report.

### 0.5 — Acceptance for Phase 0
- All four checks complete
- Subscription tier known
- Gateway version known
- Slot count confirmed
- Connection model decided
- Report: `cowork_reports/2026-05-XX_l2_phase0_preflight.md`

If subscriptions are missing or Gateway is incompatible, **escalate to Manny before continuing.** Don't try to work around missing subscriptions; we need to know before more code is written.

---

## Phase 1 — Module migration and integration plumbing

### 1.1 — Move archived files to live
```
archive/scripts/l2_signals.py    → warrior_bot/l2_signals.py
archive/scripts/l2_entry.py      → warrior_bot/l2_entry.py
archive/scripts/ibkr_feed.py     → warrior_bot/ibkr_feed.py
```

### 1.2 — Fix broken import in databento_feed.py
Line 25: `from l2_signals import L2Snapshot` should now resolve correctly. Verify the file imports cleanly with `python -c "import databento_feed"`.

### 1.3 — Smart-depth flag (conditional on Phase 0.2)
In `ibkr_feed.py:110`, modify `reqMktDepth` call:
```python
try:
    ticker = self.ib.reqMktDepth(contract, numRows=num_rows, isSmartDepth=True)
except TypeError:  # older Gateway doesn't support kwarg
    ticker = self.ib.reqMktDepth(contract, numRows=num_rows)
```
Document in Phase 1 report whether Smart depth was used or fallback was triggered.

### 1.4 — IBKRFeed → data_engine integration
Based on Phase 0.4 decision:

**If sharing the main connection:**
- Modify `IBKRFeed.__init__` to accept an existing `ib_insync.IB` instance instead of dialing one
- Add an `attach(ib_connection)` method that sets `self.ib = ib_connection; self._connected = True`
- `data_engine` creates the `IBKRFeed` instance during init and calls `feed.attach(data_engine.ib_connection)`

**If using separate connection:**
- IBKRFeed dials with its own client ID (env-configured)
- Document the new client ID assignment to avoid conflicts

### 1.5 — Singleton wiring in data_engine
Add to `data_engine.py`:
```python
from l2_signals import L2SignalDetector, L2Snapshot
from ibkr_feed import IBKRFeed

_l2_detector = L2SignalDetector()
_l2_feed = None  # initialized in data_engine startup

def init_l2_feed():
    global _l2_feed
    if _l2_feed is None:
        _l2_feed = IBKRFeed()
        # Attach or connect per Phase 0.4
    return _l2_feed
```

### 1.6 — Smoke tests
- `python -c "from l2_signals import L2SignalDetector, L2Snapshot; print('ok')"`
- `python -c "from ibkr_feed import IBKRFeed; print('ok')"`
- `python l2_signals.py` — runs the built-in CLI test, prints signals
- `python ibkr_feed.py <ACTIVE_SYMBOL> 5` — 5-second live snapshot listen against a current watchlist symbol

If any smoke test fails, fix before continuing.

### 1.7 — Acceptance for Phase 1
- Files moved
- All imports resolve
- Smart-depth status documented
- Connection model implemented (shared or separate)
- All smoke tests pass
- Report: `cowork_reports/2026-05-XX_l2_phase1_plumbing.md`

---

## Phase 2 — Snapshot helper + persistent subscription manager

### 2.1 — `request_l2_snapshot()` (one-shot snapshot for ARM-time evaluation)

In `data_engine.py`:
```python
import threading
from typing import Optional

def request_l2_snapshot(symbol: str, timeout_sec: float = 2.0) -> Optional[dict]:
    """
    Synchronous: subscribe → wait for first non-empty depth event → process → unsubscribe.
    Returns the L2 state dict or None.
    None means: timeout, subscription failure, empty book, OR L2 feed unavailable.
    Caller treats None as PASS (don't gate-block on infra failure).
    """
    feed = init_l2_feed()
    if not feed.is_connected:
        log_warning(f"L2 unavailable for {symbol}: feed not connected")
        return None

    received = {"snap": None}
    done = threading.Event()

    def on_snap(sym, snap):
        if not received["snap"] and snap.bids and snap.asks:
            received["snap"] = snap
            done.set()

    try:
        feed.subscribe_l2(symbol, on_snap, num_rows=10)
        if not done.wait(timeout_sec):
            log_warning(f"L2 timeout for {symbol} after {timeout_sec}s")
            return None

        _l2_detector.on_snapshot(received["snap"])
        return _l2_detector.get_state(symbol)

    except Exception as e:
        log_error(f"L2 snapshot request failed for {symbol}: {e}")
        return None
    finally:
        try:
            feed.unsubscribe_l2(symbol)
        except Exception:
            pass
```

### 2.2 — `L2SubscriptionManager` (persistent subscriptions for Layer 3 strategy + Layer 4 scanner)

Mirror the existing TBT manager at `bot_v3_hybrid.py:114-119`. Even though Layer 3 doesn't ship until later phases, build the manager primitive now so it's available.

In a new module `l2_subscription_manager.py`:
```python
class L2SubscriptionManager:
    """
    Manages persistent L2 subscriptions across the bot's slot budget.
    Ranks candidate symbols, subscribes top-N, drops lower-ranked,
    handles slot exhaustion gracefully.
    """
    def __init__(self, feed: IBKRFeed, detector: L2SignalDetector, max_slots: int):
        self.feed = feed
        self.detector = detector
        self.max_slots = max_slots
        self._subscribed: dict[str, dict] = {}  # symbol -> {callback, subscribed_at}
        self._lock = threading.Lock()

    def ensure_subscribed(self, symbol: str, priority: float):
        """Subscribe symbol if slots available. Drop lowest-priority if at limit and new priority is higher."""
        ...

    def release(self, symbol: str):
        """Drop subscription for a symbol."""
        ...

    def get_state(self, symbol: str) -> Optional[dict]:
        """Get current L2 state for a subscribed symbol."""
        return self.detector.get_state(symbol)

    def list_subscribed(self) -> list[str]:
        return list(self._subscribed.keys())

    def slot_usage(self) -> int:
        return len(self._subscribed)
```

Don't wire it in yet — just build the primitive. It activates in Phase 6.

### 2.3 — Telemetry helpers
```python
def summarize_l2(state: Optional[dict]) -> str:
    if not state:
        return "l2=none"
    return (f"l2=imb:{state['imbalance']:.2f}({state.get('imbalance_trend','?')}) "
            f"spread:{state['spread_pct']:.2f}% "
            f"stack:{state.get('bid_stacking', False)} "
            f"lg_bid:{state.get('large_bid', False)} "
            f"lg_ask:{state.get('large_ask', False)} "
            f"thin_ask:{state.get('ask_thinning', False)}")
```

### 2.4 — Validation of `request_l2_snapshot()`
Write a 30-line standalone test that:
1. Calls `request_l2_snapshot("ATRA", 2.0)` against the live IBKR feed (during market hours)
2. Verifies returned dict has all expected keys: imbalance, imbalance_trend, bid_stacking, large_bid, large_ask, spread_pct, ask_thinning, signals
3. Calls it 5 times in rapid succession on different symbols, confirms each works
4. Verifies subscription is properly released (slot count returns to baseline)

Save to `scripts/test_l2_snapshot.py`. Run, verify pass.

### 2.5 — Acceptance for Phase 2
- `request_l2_snapshot()` returns valid state dict for live symbols
- 5 rapid-fire calls all succeed without slot exhaustion
- Subscriptions properly release
- `L2SubscriptionManager` primitive exists (not yet wired)
- Report: `cowork_reports/2026-05-XX_l2_phase2_helpers.md`

---

## Phase 3 — L2 filter integration (WB + squeeze ARM paths)

### 3.1 — Shared filter logic
In a new module `l2_filter.py`:
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class L2Verdict:
    action: str   # "PASS" or "VETO"
    reason: str

def compute_bid_depth_at_touch(state: dict, pct_window: float = 0.005) -> int:
    """Sum bid sizes within pct_window of best bid."""
    # Use bid_stack_levels if it's full bid list, or reconstruct from state
    # Implementation detail: l2_signals state may or may not include the full bid list;
    # if not, we need to expand L2SignalDetector to expose it
    ...

def evaluate_l2_filter_long(state: Optional[dict], cfg: dict) -> L2Verdict:
    """Evaluate L2 state for a long entry. Used by both WB and squeeze."""
    if state is None:
        return L2Verdict("PASS", "no_l2_data")

    if state["spread_pct"] > cfg["max_spread_pct"]:
        return L2Verdict("VETO", f"spread={state['spread_pct']:.2f}%>{cfg['max_spread_pct']}")

    if state["imbalance"] < cfg["min_imbalance"]:
        return L2Verdict("VETO", f"imbalance={state['imbalance']:.2f}<{cfg['min_imbalance']}")

    bid_depth = compute_bid_depth_at_touch(state)
    if bid_depth < cfg["min_bid_depth_touch"]:
        return L2Verdict("VETO", f"bid_depth_touch={bid_depth}<{cfg['min_bid_depth_touch']}")

    if state.get("large_ask") and cfg.get("block_large_ask", True):
        return L2Verdict("VETO", "large_ask_wall_above")

    if state.get("imbalance_trend") == "falling" and cfg.get("block_falling_trend", False):
        return L2Verdict("VETO", "imbalance_falling")

    return L2Verdict("PASS", f"imb={state['imbalance']:.2f}_spread={state['spread_pct']:.2f}%")
```

**Important:** `compute_bid_depth_at_touch` may require expanding `_SymbolL2State.to_dict()` to expose the raw bid/ask lists. The existing dict only has summary fields. Add `"raw_bids"` and `"raw_asks"` to the returned dict, or have the filter take both the state dict AND the raw L2Snapshot.

### 3.2 — WB ARM integration
In `wave_breakout_detector.py` (or wherever WB's ARM-to-submit path lives):

After all existing gates pass and before order submission:
```python
if WB_L2_FILTER_ENABLED:
    l2_state = request_l2_snapshot(symbol, timeout_sec=WB_L2_TIMEOUT_SEC)
    l2_verdict = evaluate_l2_filter_long(l2_state, _wb_l2_config())

    log_info(f"WB_ARM {symbol} score={score} R%={r_pct:.2f}% "
             f"{summarize_l2(l2_state)} l2_verdict={l2_verdict.action} "
             f"l2_reason={l2_verdict.reason}")

    if WB_L2_FILTER_OBSERVE_ONLY:
        pass  # log only, no enforcement
    else:
        if l2_verdict.action == "VETO":
            log_info(f"WB_ARM {symbol} BLOCKED by L2: {l2_verdict.reason}")
            return  # don't submit order
```

`_wb_l2_config()` reads the WB_L2_* env vars and returns the dict.

### 3.3 — Squeeze ARM integration
Same pattern in `squeeze_detector_v2.py` (or wherever squeeze ARM-to-submit lives). Use `WB_SQ_L2_*` env prefix for squeeze-specific thresholds.

### 3.4 — Env vars
```
# Master switches
WB_L2_FILTER_ENABLED=1
WB_L2_FILTER_OBSERVE_ONLY=1
WB_SQ_L2_FILTER_ENABLED=1
WB_SQ_L2_FILTER_OBSERVE_ONLY=1

# Snapshot timeout
WB_L2_TIMEOUT_SEC=2.0

# WB thresholds
WB_L2_MAX_SPREAD_PCT=1.0
WB_L2_MIN_IMBALANCE=0.40
WB_L2_MIN_BID_DEPTH_TOUCH=1000
WB_L2_BLOCK_LARGE_ASK=1
WB_L2_BLOCK_FALLING_TREND=0   # off for observe; tune later

# Squeeze thresholds (start same as WB; tune later)
WB_SQ_L2_MAX_SPREAD_PCT=1.0
WB_SQ_L2_MIN_IMBALANCE=0.40
WB_SQ_L2_MIN_BID_DEPTH_TOUCH=1000
WB_SQ_L2_BLOCK_LARGE_ASK=1
WB_SQ_L2_BLOCK_FALLING_TREND=0

# IBKR L2 (if separate client ID)
WB_IBKR_L2_CLIENT_ID=42
```

### 3.5 — Replay test: ATRA 5/15
Before any restart, run an offline replay:
- Reconstruct the L2 state ATRA had at 13:21:01 ET today (best available from logs or live re-fetch on current state)
- Feed through `evaluate_l2_filter_long`
- Confirm verdict is VETO (or document why it isn't, and refine thresholds)
- Save to `cowork_reports/2026-05-XX_l2_atra_replay.md`

If ATRA today doesn't VETO with default thresholds, **tighten thresholds before restarting bots.** The whole point of this gate is to catch ATRA-class entries.

### 3.6 — Acceptance for Phase 3
- L2 filter integrated in both WB and squeeze paths
- Observe-only mode default
- ATRA replay confirms expected veto behavior (or thresholds tuned to make it so)
- Smoke test passes
- Report: `cowork_reports/2026-05-XX_l2_phase3_filter.md`

After Phase 3 acceptance, restart bots. L2 telemetry starts flowing on every ARM.

---

## Phase 4 — Observe week (live data collection)

### 4.1 — Daily reports
Every EOD during observe period, the daily trade breakdown includes an L2 section:

```
## L2 Layer 1 — Day N Telemetry (Observe-Only)

- ARMs evaluated: N (WB: x, Squeeze: y)
- L2 snapshots fetched: M / N
- Snapshot fetch outcomes: success=A, timeout=B, error=C, empty_book=D
- Latency: p50=X ms, p95=Y ms, p99=Z ms
- Verdicts: PASS=p, WOULD_VETO=v
- Per-ARM tabulation with L2 state and verdict (and actual trade outcome if filled)
- WOULD_VETO breakdown by reason: spread=a, imbalance=b, depth=c, large_ask=d
```

### 4.2 — Cumulative analysis across observe week
After 5 paper days (or until we have enough data — whichever comes first), produce:

`cowork_reports/2026-05-XX_l2_observe_summary.md`

Key questions to answer:
1. What fraction of ARMs got an L2 snapshot? (target: >90%)
2. What's the latency distribution? (target: p99 < 2s)
3. How many WOULD_VETOs happened? Were any of them on actual winners?
4. What's the precision/recall of each veto rule?
5. Should thresholds be tightened or loosened?

### 4.3 — Threshold tuning
Based on observe data, propose:
- Should `WB_L2_MAX_SPREAD_PCT` move from 1.0 to a different value?
- Should `WB_L2_MIN_IMBALANCE` move?
- Should `WB_L2_BLOCK_FALLING_TREND` flip from 0 to 1?
- Are squeeze-specific thresholds needed?

Each threshold change is justified by data in the report.

### 4.4 — Acceptance for Phase 4
- 5 days (or sufficient sample) of telemetry collected
- Observe summary report produced
- Threshold tuning recommendations made
- Go/no-go decision: are we ready to flip OBSERVE_ONLY=0?

If yes → Phase 5. If no → continue observe or adjust thresholds and re-validate.

---

## Phase 5 — Enable live veto

### 5.1 — Threshold updates
Apply tuning recommendations from Phase 4.

### 5.2 — Flip enforcement
```
WB_L2_FILTER_OBSERVE_ONLY=0
WB_SQ_L2_FILTER_OBSERVE_ONLY=0
```

### 5.3 — Validation period
First 3 days of live veto: daily reports include L2 ENFORCED section:
- Vetoes today: N (with reasons)
- ARMs that would have been winners had they entered: 0 expected (we want zero)
- ARMs that would have been losers and got correctly blocked: track

### 5.4 — Acceptance for Phase 5
- 3 days of live veto with zero false-positive winner blocks
- Cumulative P&L impact: net positive (or at minimum break-even)
- Report: `cowork_reports/2026-05-XX_l2_live_3day.md`

If false-positive winner blocks happen → revert to observe-only, tune, retry.

---

## Phase 6 — L2 features feed scoring + adaptive stops + dynamic sizing

This is what the deep-dive called "Layer 2." It's not deferred — it ships once Phase 5 is stable. The infrastructure is already done; this is feature additions.

### 6.1 — WB score boost from L2
In `wave_breakout_detector.py`, the WB scoring function adds an L2 sub-score:
```python
def _l2_score_boost(l2_state: dict) -> tuple[float, str]:
    boost = 0.0
    parts = []
    if l2_state["imbalance"] > 0.65:
        boost += 1.5; parts.append("imb_bull+1.5")
    if l2_state.get("bid_stacking"):
        boost += 1.0; parts.append("bid_stack+1.0")
    if l2_state.get("large_bid"):
        boost += 1.5; parts.append("lg_bid+1.5")
    if l2_state.get("large_ask"):
        boost -= 2.0; parts.append("lg_ask-2.0")
    if l2_state.get("ask_thinning"):
        boost += 1.0; parts.append("thin_ask+1.0")
    return boost, ";".join(parts)
```

Env: `WB_L2_SCORE_BOOST_ENABLED=1` (start observe-only — log the boost separately, don't apply yet, ~3 days).

### 6.2 — Squeeze score boost from L2
Similar function in `squeeze_detector_v2.py`. Squeeze-specific weighting:
- `thin_ask` is more bullish for squeeze breakouts than WB (resistance clearing)
- `large_ask` is more punitive (resistance wall blocks breakout)
- `imbalance_bull` is confirmatory but lighter weight (squeeze fires on price, L2 confirms)

### 6.3 — Adaptive stop placement
Use the existing `_find_stop` logic from `l2_entry.py`. Adapt to WB and squeeze entries:
```python
def adaptive_stop_long(l2_state: dict, default_stop: float, current_bar_low: float) -> tuple[float, str]:
    """If bid stacking is confirmed by imbalance, use highest stack level as stop.
    Otherwise return default_stop."""
    stack_levels = l2_state.get("bid_stack_levels", [])
    if stack_levels and l2_state["imbalance"] >= WB_L2_STOP_TIGHTEN_MIN_IMBALANCE:
        highest_stack = max(p for p, _ in stack_levels)
        stop = highest_stack - WB_L2_STOP_PAD
        stop = min(stop, current_bar_low - WB_L2_STOP_PAD)
        return stop, f"l2_stack_stop@{highest_stack:.3f}"
    return default_stop, "default_stop"
```

Env: `WB_L2_ADAPTIVE_STOP_ENABLED=1` (observe-only first — log the would-be stop alongside the actual default stop; compare).

### 6.4 — Dynamic position sizing
```python
def adaptive_size_multiplier(l2_state: dict) -> float:
    """Returns a multiplier on target_notional based on book quality.
    Range: 0.5 to 1.25"""
    if l2_state is None:
        return 1.0  # no data, neutral

    bid_depth = compute_bid_depth_at_touch(l2_state)

    if bid_depth >= WB_L2_SIZE_DEPTH_CAP_SHARES:  # deep book
        return WB_L2_SIZE_BOOST_DEEP
    elif bid_depth <= WB_L2_SIZE_DEPTH_FLOOR_SHARES:  # thin book
        return WB_L2_SIZE_REDUCE_THIN
    else:  # linear interpolation in between
        ratio = (bid_depth - WB_L2_SIZE_DEPTH_FLOOR_SHARES) / (WB_L2_SIZE_DEPTH_CAP_SHARES - WB_L2_SIZE_DEPTH_FLOOR_SHARES)
        return WB_L2_SIZE_REDUCE_THIN + ratio * (WB_L2_SIZE_BOOST_DEEP - WB_L2_SIZE_REDUCE_THIN)
```

Env:
```
WB_L2_ADAPTIVE_SIZE_ENABLED=1
WB_L2_SIZE_DEPTH_CAP_SHARES=10000
WB_L2_SIZE_DEPTH_FLOOR_SHARES=2000
WB_L2_SIZE_BOOST_DEEP=1.25
WB_L2_SIZE_REDUCE_THIN=0.50
```

(Observe-only first.)

### 6.5 — Observe period
Each of the three Phase-6 features ships observe-only first. Daily reports track:
- Score boost / penalty per ARM (does the L2 boost agree with eventual outcome?)
- Adaptive stop placement: would-be R vs actual R; would-be win rate at the closer stop
- Adaptive sizing: would-be position size vs actual; would-be P&L delta

After 5 paper days for each feature, evaluate and flip live one at a time.

### 6.6 — Acceptance for Phase 6
For each of the three features:
- 5 days observe-only telemetry
- Evidence-based recommendation: enable, tune, or rollback
- Sequenced enablement: one feature live, validate 3 days, then next feature
- Report per feature: `cowork_reports/2026-05-XX_l2_feature_<name>.md`

---

## Phase 7 — L2 as a strategy (resurrect `l2_entry.py`)

**Status: PARKED.** Per Manny's decision 2026-05-15: Phase 7 is deferred until Phases 0-6 are fully stable. When it lands, L2 entry runs on a **4th Alpaca paper account** alongside the existing Setup A (subbot) + Setup B (engine) + the third paper account from the unified-data-engine work. We have a whole unused IBKR paper account capacity and an unused Alpaca paper account slot — that's the home for L2 strategy when its time comes.

Do not begin Phase 7 work until told explicitly. Phases 0-6 are the current scope.

Kept in this directive for context and so the architecture choices in Phases 1-2 (the L2SubscriptionManager primitive in particular) account for Phase 7's eventual needs.

---

### Phase 7 design (for reference — do not implement yet)

This is the deep-dive's "Layer 3." Genuinely new strategy work. Ships after Phase 6 because:
- Phases 1-2 give us the data plumbing
- Phase 3-5 prove L2 signals are real and trustworthy
- Phase 6 proves we can integrate L2 features without breaking things
- Phase 7 builds on all that

### 7.1 — Audit `l2_entry.py` for V3 architecture compatibility
- Verify `MACDState` import path matches current macd module
- Verify bar object expectations match what the current detector pipeline produces
- Verify `seed_bar_close` integration with the historical data warming pipeline
- Identify any V3-specific changes needed

### 7.2 — Activate `L2SubscriptionManager` (from Phase 2.2)
Wire the manager into the bot's main loop:
- Rank watchlist symbols by WB score (or squeeze score, or both — TBD)
- Subscribe top-N (where N = available slots - reserve for ARM-time snapshots)
- Re-rank every 30s (mirror TBT manage interval)

### 7.3 — Add L2 entry detector to the per-symbol pipeline
For each L2-subscribed symbol, instantiate `L2EntryDetector` and feed it:
- 1m bar closes (via existing bar pipeline)
- L2 state updates (via the L2SignalDetector singleton)

On `L2EntryDetector.armed` event, execute through the same order-submission infrastructure as WB and squeeze, with `setup_type='l2_entry'`.

### 7.4 — Stop and exit management
L2 entries get the same exit infrastructure as other strategies. The stop returned by `L2ArmedTrade.stop_low` plugs in directly.

### 7.5 — Position sync and tracking
Add `l2_entry` to:
- `session_state/{date}/wb_bot/open_trades.json` schema
- Position sync logic
- Exit triggers
- Per-strategy P&L reporting in daily breakdowns

### 7.6 — Paper-only flag
```
WB_L2_ENTRY_STRATEGY_ENABLED=1
WB_L2_ENTRY_PAPER_ONLY=1     # safety — refuse to trade L2-entry setups on real money until 7.X
```

The `PAPER_ONLY` flag is enforced in the order-submission path. Belt-and-suspenders before real money.

### 7.7 — Extended paper test
Run L2-entry strategy in paper alongside WB and squeeze for at least 4 weeks. Daily reports include:
- L2-entry trades: count, win rate, average P&L, R-multiple distribution
- Comparison to squeeze and WB outcomes on the same symbols
- Slot contention: how often did L2-entry want a symbol that wasn't subscribed?

### 7.8 — Acceptance for Phase 7
After 4+ weeks of paper:
- ≥30 L2-entry trades executed in paper
- Win rate ≥ 45%
- Per-trade P&L expectancy positive
- No infrastructure failures (slot exhaustion handled gracefully, no orphan positions, etc.)
- Report: `cowork_reports/2026-XX-XX_l2_strategy_4week.md`
- Decision: enable on real money (flip PAPER_ONLY=0), keep in paper longer, or retire

---

## Phase 8 — L2-derived candidate scanner

**Status: PARKED with Phase 7.** Same rationale — depends on persistent L2 subscriptions, scheduled for the 4th paper account work alongside Phase 7. Do not implement yet.

Kept for context.

---

### Phase 8 design (for reference — do not implement yet)

This is "Layer 4" from the deep-dive. Runs alongside or replaces the intraday adder depending on data.

### 8.1 — Standing L2 scanner architecture
- Subscribe L2 to top-N symbols from the squeeze scanner's gainers/movers list
- Rotate every 5-10 seconds (faster than Phase 7's per-symbol persistent subscriptions)
- On any symbol showing strong bullish L2 (imbalance > 0.7 + bid stacking + 2+ consecutive bullish snapshots), emit as a candidate

### 8.2 — Output integration
Candidates surfaced by the L2 scanner write to `wb_observed_today.txt` (which feeds `wb_persistence.txt`). They show up in tomorrow's watchlist via the persistence layer's normal flow.

Alternative path: surface for same-day consideration by writing to a separate file `wb_l2_candidates_today.txt` that the bot's intraday adder consumes.

### 8.3 — Slot contention
Phase 7 (L2 strategy) and Phase 8 (L2 scanner) both want persistent slots. Resolution:
- Phase 7 wins for currently-relevant symbols (top WB-score watchlist names)
- Phase 8 gets remaining slots for discovery (gainers/movers not on watchlist)
- If slots saturate, scanner pauses; resumes when a slot frees

May force the quote-booster purchase decision. Document slot pressure in daily reports through Phase 8.

### 8.4 — Acceptance for Phase 8
- Scanner runs for 2 weeks
- ≥1 candidate per week not already on the watchlist
- Of surfaced candidates, ≥30% develop into legitimate setups within 30 min
- Slot management graceful (no errors, no manual intervention required)

---

## Phase 9 — Backtest integration (L2 historical replay)

This is forward-looking. Wire L2 into the simulate.py backtester so we can answer "would L2 have changed historical outcomes?" rigorously.

### 9.1 — Historical L2 data source
Two options:
- **Forward-recorded:** save L2 snapshots to disk during Phase 4+. After a month we have replayable data. Limitations: only covers symbols we subscribed to.
- **Databento:** if your Databento subscription includes depth data (e.g., ITCH for Nasdaq), we can replay historical books for any small-cap. Verify subscription.

### 9.2 — Backtest L2 integration
- Modify `simulate.py` to accept L2 historical data alongside bar/tick data
- Feed L2Snapshots into `L2SignalDetector` at appropriate timestamps
- The `--use_l2_entry` flag (already present at line 1737) becomes functional
- Backtest can now produce L2-aware results

### 9.3 — Historical L2 analysis
Run backtests against past months to:
- Validate Phase 5 vetoes (would they have blocked historical losers?)
- Validate Phase 6 features (would scoring boosts have improved P&L?)
- Validate Phase 7 strategy (would L2-entry have produced winners?)

---

## Phase 10 — Real-money readiness

Tied to June 4 PDT-rule retirement / real-money go-live.

Required for real-money cutover:
- Phase 5 (L2 filter live) complete and stable for ≥1 week
- Optional but strongly recommended: Phase 6 (features) complete and stable
- Phase 7 (L2 strategy) stays in paper for first month of real money — too new to risk
- Phase 9 (backtest) complete enough to confirm filter behavior on historical data

Pre-cutover checklist:
- All L2 env flags reviewed and set correctly for real money
- IBKR account L2 subscriptions confirmed still active
- L2 telemetry confirmed flowing reliably during paper trading the week before cutover
- Quote booster purchase decision made (3 slots vs 7 slots based on actual contention observed)

---

## Cross-phase telemetry standards

Every L2-related ARM, fill, or evaluation logs a standard line:

```
[<UTC ts>] L2 <SETUP_TYPE> <SYMBOL> phase=<phase> action=<action>
  state=imb:0.65(rising) spread:0.32% stack:T lg_bid:F lg_ask:F thin_ask:T
  verdict=PASS reason=imb=0.65_spread=0.32%
  bid_depth_touch=4500 stop_l2=9.79 stop_default=8.84 size_mult=1.15
```

This format unifies across all phases — Phase 3 only fills `state` and `verdict`; Phase 6 adds `stop_l2` and `size_mult`; Phase 7 adds entry-specific fields. Makes log parsing for daily reports straightforward.

---

## Files & rollback

### Files touched (cumulative across all phases)
```
warrior_bot/l2_signals.py                  (moved from archive in Phase 1)
warrior_bot/l2_entry.py                    (moved from archive in Phase 1)
warrior_bot/ibkr_feed.py                   (moved from archive in Phase 1)
warrior_bot/l2_filter.py                   (new in Phase 3)
warrior_bot/l2_subscription_manager.py     (new in Phase 2, activated in Phase 7)
warrior_bot/data_engine.py                 (modified in Phase 1, 2)
warrior_bot/wave_breakout_detector.py      (modified in Phase 3, 6)
warrior_bot/squeeze_detector_v2.py         (modified in Phase 3, 6)
warrior_bot/bot_v3_hybrid.py               (modified in Phase 7 — strategy integration)
warrior_bot/databento_feed.py              (broken import resolves in Phase 1)
warrior_bot/simulate.py                    (modified in Phase 9 — backtest integration)
warrior_bot/.env                           (env vars added in each phase)
scripts/probe_market_depth_capacity.py     (new in Phase 0)
scripts/test_l2_snapshot.py                (new in Phase 2)
```

### Rollback per phase
Any phase can be rolled back by setting its master `_ENABLED` env flag to `0` and restarting. Code stays in place but is inert.

Hard rollback (uninstall): revert the file moves, restore the archive layout. Net change: the broken import in `databento_feed.py:25` returns to broken state (which is its current state anyway). Zero risk.

---

## Per-phase report list

| Phase | Report |
|---|---|
| 0 | `cowork_reports/2026-05-XX_l2_phase0_preflight.md` |
| 1 | `cowork_reports/2026-05-XX_l2_phase1_plumbing.md` |
| 2 | `cowork_reports/2026-05-XX_l2_phase2_helpers.md` |
| 3 | `cowork_reports/2026-05-XX_l2_phase3_filter.md` + ATRA replay |
| 4 | Daily breakdowns with L2 sections + final `cowork_reports/2026-05-XX_l2_observe_summary.md` |
| 5 | `cowork_reports/2026-05-XX_l2_live_3day.md` |
| 6 | One report per sub-feature (score, stop, size) |
| 7 | `cowork_reports/2026-XX-XX_l2_strategy_4week.md` |
| 8 | `cowork_reports/2026-XX-XX_l2_scanner_2week.md` |
| 9 | `cowork_reports/2026-XX-XX_l2_backtest_validation.md` |

---

## What this plan is and isn't

**Is:** the complete sequenced build for everything L2-related. Phases gated by acceptance criteria, not by calendar.

**Isn't:**
- A deadline-driven race
- A list of optional items — Phases 0 through 6 are all required; Phase 7 is the next strategy work; Phase 8 is an alternative to or complement of the intraday adder; Phase 9 enables rigorous backtest; Phase 10 is just the real-money confirmation
- A replacement for the dead-tape gate ship (still ships Saturday)
- A replacement for FCHL fix (still ships separately, P0)
- A replacement for the squeeze fill-rate fix (already in CC's queue from yesterday)

These run in parallel because they touch different code paths.

---

## CC: where to start

Begin at Phase 0. Don't write any new code until Phase 0 finishes. The subscription audit + Gateway version check + slot probe are pre-requisites — if any of those reveal a problem we don't expect, the design changes.

When Phase 0 acceptance lands, work Phase 1. When Phase 1 acceptance lands, work Phase 2. And so on.

**Current scope: Phases 0 through 6.** Phase 7 (L2 strategy) and Phase 8 (L2 scanner) are parked for the 4th-paper-account work later. Phase 9 (backtest) and Phase 10 (real-money) remain in scope as written.

After Phase 6 acceptance, pause and check in. We'll decide together whether to begin Phase 7 prep, return to other workstreams (squeeze improvements, FCHL hardening, etc.), or just run Phases 0-6 in production for a stretch to see if anything else surfaces.

If you hit something unexpected in any phase, pause and report. We'd rather understand the surprise than push through it.

Quality over speed. There's no clock on this. Just the work.
