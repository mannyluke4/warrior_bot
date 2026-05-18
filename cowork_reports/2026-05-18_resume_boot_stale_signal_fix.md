# Resume-Boot Stale-Signal Re-Firing — Root Cause + Reviewable Patch

**Date:** 2026-05-18
**Author:** CC (Opus)
**Scope:** READ-ONLY investigation + unified-diff patch artifact. No production files modified.
**Triggered by:** Max-chase missed-opportunity audit identified 6 of 14 chase-cap timeouts (43%) as resume-boot artifacts on SLE 2026-05-15 (16:17 → 17:50 ET).
**Constraint reminder:** Setup A is sacred. This patch goes to Cowork review before any rollout.

---

## TL;DR

The bug is a **race between `reqMktData` subscription and seed replay** combined with a **gap in the squeeze detector's `on_trade_price` gate**. On every intra-day resume:

1. `subscribe_symbol()` in `bot_v3_hybrid.py:1251` calls `reqMktData` BEFORE seed.
2. `seed_symbol_from_cache()` (line 1787-1894) replays the cached tick stream. This re-builds 1m bars; the original 07:54 ET volume-spike bar re-PRIMES + re-ARMs the squeeze detector at `trigger=$5.02`, exactly as it did the first time.
3. While the replay is still running, IBKR delivers a live tick via `pendingTickersEvent` → `on_ticker_update` → `check_triggers` → `sq.on_trade_price(price=$5.90+)`.
4. `on_trade_price` (`squeeze_detector.py:289-315`) checks `_seed_just_ended` but **NOT `_seeding`**. Since the seed-replay sequence has not yet completed (`_seeding=True`, `_seed_just_ended=False`), the gate is wide open. The detector is armed at $5.02 and the live tick is at $5.90+, so it fires `ENTRY SIGNAL @ 5.0200`.
5. `enter_trade()` ships a BUY limit at $5.09 against tape at $5.90+. Three retries × 10s, max-chase cap of 3.5% → ORDER TIMEOUT.
6. `validate_arm_after_seed` is called AFTER the live tick fired the entry. It uses `raw_ticks[-1]` (the last CACHED tick at ~$5.91), would correctly compute 17.7% stale-ratio and drop the arm — but `armed` is already `None` (cleared on line 310 when the live tick fired the entry). The post-seed gate is moot.

**Recommended fix:** **Option 2 + minor Option 1**. Block `on_trade_price` while `_seeding=True` (the missing one-line gate), AND change `validate_arm_after_seed` to consult the LIVE current price (`state.last_tick_price[symbol]`) instead of `raw_ticks[-1]`. This eliminates the race plus closes the cache-vs-wall-clock seam.

**Recommended rollout window:** Post-close tonight (Tuesday 2026-05-19 after 20:00 ET) → live first thing Wednesday 2026-05-20 morning. Or push to weekend if Cowork wants a longer staging window — the bug only fires on intra-day restarts (cron 2 AM is cold start, unaffected). Daytime trading uninterrupted.

---

## 1. Bug reproduction — SLE 2026-05-15 evening, walked through the log

### 1.1 Day timeline (from `logs/2026-05-15_daily.log`)

- **07:54 ET line 8766:** `[07:54 ET] SLE SQ | SQ_PRIMED: vol=143.3x avg, bar_vol=756,199, price=$5.5100`. The SLE squeeze detector found a 143× volume spike on the 07:54 bar with PARABOLIC score 11.0. It armed at `trigger=$5.02`.
- **07:54 ET line 8768:** `SQ_SEED_STALE_RESET: dropped arm @ $5.0200 (stop $4.9000) — current price $5.5000 is 9.6% above trigger (threshold 2.0%)`. The seed-stale gate dropped the arm on the FIRST cold-boot path — proving the gate works when nothing races it.
- **08:32 ET line 10377:** SLE re-arms on a new bar (different spike), ENTRY SIGNAL fires legitimately at $6.02, fills at $6.09 → exits at $6.29 (small win).
- **10:46 ET line 16304:** SLE arms again, ENTRY SIGNAL at $6.02, but tape has moved → chase-cap timeout. (Real signal miss, not the bug.)
- **16:17:15 ET line 30965:** First "stale-signal" ENTRY at $5.02. Bot was restarted at ~16:17 (intra-day, probably watchdog).

### 1.2 Buggy sequence at 16:17 ET

Reading lines 30962-30978 of `logs/2026-05-15_daily.log`:

```
[16:17 ET] SLE SQ | SQ_REJECT: not_new_hod (bar_high=$5.7400 < HOD=$5.9100)   ← cache replay bar
[16:17 ET] SLE SQ | SQ_PRIMED: vol=241.0x avg, bar_vol=756,199, price=$5.5100 ← REPLAYING 07:54 bar
  ARMED entry=5.0200 stop=4.9000 R=0.1200 score=11.0 level=whole_dollar...   ← re-armed at $5.02
[16:17:15 ET] SLE SQ | ENTRY SIGNAL @ 5.0200 (break 5.0200)                  ← LIVE tick fired
🟩 ENTRY: SLE qty=2956 limit=$5.09 (slip=$0.070) stop=$4.9000 R=$0.1200
  BROKER ORDER: 7e504bcf-... BUY 2956 SLE @ $5.09
  [RESUME] SLE: bridged gap (2.3m, capped 90m) → 46 ticks                     ← gap bridge AFTER entry
🔁 [RESUME] SLE: 472,278 ticks → 50 bars, EMA=5.9270 | drift=2.4m             ← seed END marker
✅ Subscribed: SLE                                                            ← subscribe_symbol returns
```

Two timestamp formats are diagnostic:
- `[16:17 ET]` (no seconds) — from `on_bar_close_1m` callback (`now_str = datetime.now(ET).strftime("%H:%M")`, line 2180)
- `[16:17:15 ET]` (with seconds) — from `check_triggers` (`now_str = datetime.now(ET).strftime("%H:%M:%S")`, line 2427)

The `[16:17:15 ET]` ENTRY SIGNAL is a LIVE TICK firing through `on_ticker_update`. It happens **before** the `🔁 [RESUME] SLE` line (the seed-function's terminal log) and **before** `✅ Subscribed: SLE`. Therefore the live tick fires WHILE seed_symbol_from_cache is still executing.

### 1.3 Repeated pattern — 5 more bot restarts that evening

| Restart | Time (ET) | Cache ticks replayed | Bridge gap | ENTRY @ | Tape giveup | Status |
|---|---|---|---|---|---|---|
| #1 | 16:17 | 472,278 | 2.3m | $5.09 | $5.90 | timeout (3.5% chase cap) |
| #2 | 16:25 | 472,468 | 2.1m | $5.09 | $5.97 | timeout |
| #3 | 17:16 | 475,083 | 2.1m | $5.09 | $6.09 | timeout |
| #4 | 17:25 | 475,203 | 2.3m | $5.09 | $5.82 | timeout |
| #5 | 17:46 | 475,525 | 2.3m | $5.09 | $5.88 | timeout |
| #6 | 17:50 | 475,589 | 2.6m | $5.09 | $5.93 | timeout |

Every restart re-runs the same buggy sequence. The 07:54 ET volume-spike bar (`vol=246.3x, bar_vol=756,199, price=$5.5100`) is permanently cached, so every cache replay re-arms at $5.02. Every restart pairs that arm with an instant live-tick fire because reqMktData is active.

Why restarts kept happening: extended-hours volatility + scanner thread hangs + watchdog → bot died → daily_run_v3.sh respawned. Each respawn = one buggy entry attempt = one chase-cap timeout = $0 fill but visible to Manny watching the tape.

---

## 2. Root cause analysis — file:line precision

### 2.1 The race window — `bot_v3_hybrid.py:1241-1275`

```python
def subscribe_symbol(symbol: str):
    if symbol in state.active_symbols:
        return
    contract = Stock(symbol, 'SMART', 'USD')
    state.ib.qualifyContracts(contract)
    state.contracts[symbol] = contract

    # Subscribe to market data with RTVolume (generic tick 233)
    ticker = state.ib.reqMktData(contract, '233', False, False)         # ← LIVE TICKS BEGIN
    state.tickers[symbol] = ticker

    # Initialize detectors
    init_detectors(symbol)

    # Seed — resume mode replays from tick_cache/<today>/<sym>.json.gz
    seeded_from_cache = False
    if state.boot_mode == "resume":
        seeded_from_cache = seed_symbol_from_cache(symbol)                # ← REPLAY (takes seconds for 472K ticks)
    if not seeded_from_cache:
        seed_symbol(symbol)

    state.active_symbols.add(symbol)
    state.tick_counts[symbol] = 0
    state.sub_retry_counts[symbol] = 0
    state.tier.setdefault(symbol, "snapshot")
    print(f"✅ Subscribed: {symbol}", flush=True)
    persist_watchlist()
```

`reqMktData` is dispatched at line 1251. IBKR can deliver tickers starting **immediately** — they arrive on the ib_insync asyncio loop's `pendingTickersEvent`, which routes to `on_ticker_update` (registered at line 4704 during main()). The seed-replay at line 1263 then runs synchronously in the same coroutine, but **during the replay, any `ib.sleep()` call yields the event loop, allowing pending ticker events to dispatch**.

In `seed_symbol_from_cache` itself there's no `ib.sleep()`. But it calls `_bridge_gap_for_symbol` (line 1855) which calls `ib.reqHistoricalTicks` + `state.ib.sleep(0.3)` (line 1752). Every 0.3s sleep is an event-loop yield. Live SLE ticks at $5.90+ get dispatched right there.

### 2.2 The missing gate — `squeeze_detector.py:289-315`

```python
def on_trade_price(self, price: float, is_premarket: bool = False) -> Optional[str]:
    if not self.enabled or self.armed is None:
        return None

    if price >= self.armed.trigger_high:
        # Seed gate: suppress stale entries after seed replay
        if self._seed_gate_enabled and self._seed_just_ended:           # ← only checks _seed_just_ended
            return (
                f"SQ_SEED_GATE: suppressed entry @ {self.armed.trigger_high:.4f} "
                ...
            )

        msg = (
            f"ENTRY SIGNAL @ {self.armed.entry_price:.4f} ..."
        )
        self.armed = None
        self._state = "IDLE"
        self._attempts += 1
        return msg

    return None
```

The seed-gate fires only AFTER seed (`_seed_just_ended=True`), for `WB_SEED_GATE_BARS` live bars. **It does NOT fire DURING seed (`_seeding=True`).** That's the bug. The original author assumed `on_trade_price` is only called for live ticks, and that during seed-replay nothing would call it — but the asyncio loop violates that assumption.

### 2.3 The stale-validator timing — `bot_v3_hybrid.py:1866-1874`

```python
if sq and raw_ticks:
    latest_price = float(raw_ticks[-1].get("p", 0))                     # ← LAST CACHED tick
    stale_msg = sq.validate_arm_after_seed(latest_price)
    if stale_msg:
        print(f"  [{symbol}] {stale_msg}", flush=True)
        armed = None

if sq:
    sq.end_seed()
```

Two problems:
1. `raw_ticks[-1]` is the last tick AT THE MOMENT OF CRASH. If the bot crashed at price $5.91 (matching SLE), the stale-check correctly sees a 17.7% gap and SHOULD drop the arm. But it runs AFTER the live-tick race has already fired the entry, so `armed` is None and the check no-ops.
2. Even fixing #1, the cache's last tick isn't always close to the live wall-clock price. A 90-minute gap-bridge could move the live price further. Using `state.last_tick_price[symbol]` (refreshed in `_process_trade_tick` line 3944) gives the live price.

### 2.4 Why `validate_arm_after_seed` is too late to help

Order of operations in `seed_symbol_from_cache`:
1. `begin_seed()` — `_seeding=True`
2. Replay cached ticks → bar_builder → `on_bar_close_1m` → detector ARMs (this is fine — arm-during-seed is intended)
3. Gap-bridge (with `ib.sleep(0.3)` between pages — **this is where live ticks race in**)
4. `validate_arm_after_seed(raw_ticks[-1])` — too late if the race already fired entry
5. `end_seed()` — `_seed_just_ended=True`, `_seeding=False`

The post-seed gate (step 5) is intended to suppress retroactive triggers from replay ticks. It works when no live tick races during steps 2-4. But the system requires extra defense:
- Defense A: Block `on_trade_price` during `_seeding=True` (prevent the race itself).
- Defense B: Move the stale-arm validation to use live price (resilient even if race somehow gets through).

---

## 3. Proposed fix — Option 2 + Option 1 (combined)

### 3.1 Decision

**Option 2 (skip pending-ENTRY replay) AND a strengthened Option 1 (live-price staleness check).**

Why both:
- **Option 2 alone** (block `on_trade_price` during `_seeding`) closes the race but doesn't defend against the case where the race happens through some other path (e.g. SHORT detector, MP detector, future detectors). It's the cheapest fix and addresses the specific SLE bug.
- **Option 1 alone** (live-price stale check after seed) doesn't help if the entry already fired before the check ran. It's necessary as a backup.
- **Combined** = defense in depth. The race window is closed (Option 2) AND if any other path bypasses it the stale arm is dropped before any subsequent live tick can re-trigger it (Option 1).

**Not Option 3** (TTL on pending ENTRYs): there is no persisted pending-ENTRY queue. The bug is signal-level (re-firing from detector state replay), not order-level (a queued unfilled order surviving restart). Open orders are correctly cancelled in `resume_reconcile` (`bot_v3_hybrid.py:848-1022`). Option 3 would solve a different bug class.

### 3.2 Unified diff (do NOT apply — review artifact)

```diff
diff --git a/squeeze_detector.py b/squeeze_detector.py
--- a/squeeze_detector.py
+++ b/squeeze_detector.py
@@ -286,12 +286,23 @@
     # ------------------------------------------------------------------
     # Tick trigger check
     # ------------------------------------------------------------------
     def on_trade_price(self, price: float, is_premarket: bool = False) -> Optional[str]:
         if not self.enabled or self.armed is None:
             return None

+        # Resume-boot race guard: while seed replay is in flight, live ticks
+        # delivered through ib_insync's asyncio loop can race the
+        # seed_symbol_from_cache pipeline and fire ENTRY SIGNAL against a
+        # stale ARM that hasn't yet been validated by validate_arm_after_seed.
+        # Block entries during _seeding; the post-seed _seed_just_ended gate
+        # then takes over until WB_SEED_GATE_BARS live bars confirm. See
+        # cowork_reports/2026-05-18_resume_boot_stale_signal_fix.md (SLE
+        # 2026-05-15 evening, 6 chase-cap aborts).
+        if self._seeding:
+            return None
+
         if price >= self.armed.trigger_high:
             # Seed gate: suppress stale entries after seed replay
             if self._seed_gate_enabled and self._seed_just_ended:
                 return (
                     f"SQ_SEED_GATE: suppressed entry @ {self.armed.trigger_high:.4f} "
                     f"— {self._live_bars_since_seed}/{self._seed_gate_bars} live bars "

diff --git a/bot_v3_hybrid.py b/bot_v3_hybrid.py
--- a/bot_v3_hybrid.py
+++ b/bot_v3_hybrid.py
@@ -1862,11 +1862,21 @@
         sq = state.sq_detectors.get(symbol)
         bar_count = len(sq.bars_1m) if sq else 0
         ema = sq.ema if sq else None
         armed = sq.armed if sq else None

         if sq and raw_ticks:
-            latest_price = float(raw_ticks[-1].get("p", 0))
+            # Prefer LIVE wall-clock price for staleness comparison —
+            # raw_ticks[-1] is the last cached tick at the moment of crash,
+            # which can be minutes/hours stale relative to the current tape.
+            # state.last_tick_price[symbol] is refreshed by _process_trade_tick
+            # on every live print (Tier 1 + Tier 2 paths). Fall back to the
+            # cached tick if no live price has arrived yet.
+            live_price = state.last_tick_price.get(symbol)
+            if live_price and live_price > 0:
+                latest_price = float(live_price)
+            else:
+                latest_price = float(raw_ticks[-1].get("p", 0))
             stale_msg = sq.validate_arm_after_seed(latest_price)
             if stale_msg:
                 print(f"  [{symbol}] {stale_msg}", flush=True)
                 armed = None
```

Same diff hunk applies to `bot_alpaca_subbot.py:2369-2378` (parallel sub-bot uses the same `seed_symbol_from_cache` helper — see `bot_alpaca_subbot.py:2296`). Patch both bots in the same commit.

### 3.3 What the fix does NOT change

- Cold boot (no resume): `_seeding` flips true→false within `seed_symbol` (`bot_v3_hybrid.py:1600` + `:1712`). Same race exists in theory but cold boot's seed uses `reqHistoricalTicks` which is a blocking IBKR call running before any live tick is received. The fix is still correct (harmless no-op) for cold boot.
- Stale-arm logic for cold boot: validate_arm_after_seed uses `all_ticks[-1].price` in cold path (`bot_v3_hybrid.py:1704`). The live-price fallback added in the patch does NOT touch cold boot — the patch is gated to `seed_symbol_from_cache` only.
- Other detectors: MicroPullback (`micro_pullback.py`), Continuation, Short, WaveBreakout. The seeding flag (`_seeding`) is squeeze-detector only. The bug-reproduced cases are all squeeze (SLE score 11.0 PARABOLIC). A separate audit may extend the fix to MP/CT if needed (recommend in Section 5.3).

---

## 4. Test plan

### 4.1 Unit-test addition (squeeze_detector)

File: `tests/test_squeeze_seed_race.py` (new)

```python
import pytest
from squeeze_detector import SqueezeDetector

def test_on_trade_price_blocks_during_seeding():
    """Resume-boot race regression — replay-window live tick must not fire ENTRY.

    Reproduces SLE 2026-05-15 16:17 evening bug: detector ARMed at trigger=$5.02
    during seed replay, then a live tick at $5.90 races in via ib_insync's
    asyncio loop before end_seed() is called. Pre-fix: returns ENTRY SIGNAL.
    Post-fix: returns None (blocked by _seeding gate).
    """
    sq = SqueezeDetector(symbol="SLE", ema_len=9)
    sq.enabled = True
    sq.begin_seed()
    # Hand-craft an arm — mimics the seed-replay pipeline arming the detector.
    from squeeze_detector import ArmedState  # adjust import to actual class
    sq.armed = ArmedState(
        trigger_high=5.02, stop_low=4.90, r=0.12,
        entry_price=5.02, score=11.0, score_detail="test",
        # ... fill other ArmedState fields per current schema
    )
    sq._state = "ARMED"
    # Simulate the live tick at $5.90+ racing in DURING seed.
    msg = sq.on_trade_price(price=5.90, is_premarket=False)
    assert msg is None, f"Expected suppression during _seeding, got: {msg}"
    assert sq.armed is not None, "Arm must not be cleared by suppressed call"

def test_on_trade_price_unblocks_after_end_seed():
    """end_seed sets _seed_just_ended; once enough live bars confirm,
    on_trade_price fires ENTRY SIGNAL normally."""
    sq = SqueezeDetector(symbol="SLE", ema_len=9)
    sq.enabled = True
    sq.begin_seed()
    sq.armed = ArmedState(trigger_high=5.02, ...)
    sq._state = "ARMED"
    sq.end_seed()
    # _seed_just_ended=True; on_trade_price still suppressed for SEED_GATE_BARS
    msg = sq.on_trade_price(price=5.90)
    assert msg and "SQ_SEED_GATE" in msg

def test_validate_arm_after_seed_uses_live_price_when_provided():
    """Stale-arm validator should accept the live price, not just cache tail."""
    sq = SqueezeDetector(symbol="SLE", ema_len=9)
    sq.enabled = True
    sq.begin_seed()
    sq.armed = ArmedState(trigger_high=5.02, ...)
    # Live price is $5.90 → 17.5% above trigger → must drop the arm.
    msg = sq.validate_arm_after_seed(current_price=5.90)
    assert msg and "SQ_SEED_STALE_RESET" in msg
    assert sq.armed is None
```

### 4.2 Integration test — `tests/test_resume_race_e2e.py` (new, fast)

Stub `state.ib` with a fake that:
- Returns 472K SLE ticks from `tick_cache/2026-05-15/SLE.json.gz` on `reqHistoricalTicks` (gap-bridge)
- Simulates a single live tick at $5.90 delivered via `pendingTickersEvent` ~50ms after `reqMktData` is called

Assert: `state.broker.orders_submitted == 0` after `subscribe_symbol("SLE")` returns. Pre-fix the test fails with one BUY @ $5.09; post-fix it passes.

### 4.3 Backtest regression (mandatory per CLAUDE.md)

```bash
source venv/bin/activate
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```

Expected: VERO +$34,479, ROLR +$54,654 unchanged (simulate.py does not run the resume path; the patch is no-op for backtests).

### 4.4 Live-data smoke test

After deploy, on the next intra-day restart (whether forced via `kill` or watchdog-triggered):
1. Confirm log contains `🔁 [RESUME] <sym>: N ticks → M bars` for every previously-subscribed symbol.
2. Confirm NO ENTRY SIGNAL log line appears between the `[RESUME] <sym>: bridged gap` line and the `✅ Subscribed: <sym>` line, for any previously-ARMED symbol whose live price has run >2% past trigger.
3. If a legitimate fresh ARM happens AFTER `✅ Subscribed: <sym>` and the live price re-tests the trigger, the entry must fire normally (post-`_seed_just_ended` window after WB_SEED_GATE_BARS).

### 4.5 Manual replay of SLE 2026-05-15 evening

Stage a synthetic test:
1. Copy `tick_cache/2026-05-15/SLE.json.gz` to a sandbox.
2. Set `state.boot_mode = "resume"`, current date forced to 2026-05-15.
3. Stub `reqMktData` to deliver one tick at $5.90 immediately after subscription.
4. Run `subscribe_symbol("SLE")`.
5. Assert log contains `SQ_SEED_STALE_RESET` (live-price validator dropped the arm) OR no ENTRY SIGNAL line (race guard blocked it). Either failure is acceptable; both succeeding is the bullseye.
6. Assert `state.pending_order is None`.

---

## 5. Rollout plan + risk assessment

### 5.1 Recommended window

**Post-close Tuesday 2026-05-19, 20:00 ET → live for Wednesday 2026-05-20 open.**

Why post-close tonight:
- The bug only manifests on intra-day restarts. During a calm overnight window, no restarts → no bug exposure.
- Wednesday is a normal trading day; we want the fix live before any 09:30 ET catalyst that could trigger a watchdog restart cycle.
- Cron 2 AM does a cold boot (no resume path). The fix is no-op for cold boot, so cron is unaffected.
- Manny's real-money go-live is **2026-06-04**. Every paper day between now and then is non-fungible calibration data (per project memory). Get this fix in fast.

Alternative: weekend deploy (Saturday 2026-05-22). Slower; more staging buffer; no advantage given the patch is small and well-gated.

### 5.2 Rollback plan

If smoke test fails:
1. `git revert` the commit
2. `daily_run_v3.sh` will pick up the reverted code on next watchdog restart
3. Fallback runtime escape hatch: set `WB_SEED_GATE_BARS=999` in `.env` → effectively disables ALL ENTRY signals post-seed-replay until the gate clears (which it never will at 999 bars). Use only in extremis.

### 5.3 Risk assessment

**Risks reviewed:**

| Risk | Severity | Mitigation |
|---|---|---|
| Legit fresh ARM during seed is blocked | LOW | The fix only blocks `on_trade_price` during `_seeding`. ARM creation (in `on_bar_close_1m`) is unchanged. After `end_seed()`, the normal `_seed_just_ended` gate covers WB_SEED_GATE_BARS bars, then full firing resumes. |
| Legit intra-day restart with pending fill about to land | LOW | `resume_reconcile` (lines 848-1022) already cancels all pending BUYs on restart. There's no "in-flight pending fill" preserved across restart. So the fix can't disrupt one. |
| Other detectors (MP, CT, Short) still have the same race | MEDIUM | Out of scope for this patch — only squeeze has emit evidence of the bug. Recommend follow-up: extend `_seeding` flag (or equivalent state machine) to all detectors that have arm-then-trigger semantics. Tracked in Section 6. |
| Live-price fallback in `validate_arm_after_seed` differs from cache-last-tick on cold boot | NONE | Patch is gated to `seed_symbol_from_cache` (line 1866-1872). Cold boot path (`seed_symbol`, line 1703-1708) is untouched. |
| Backtest regression | NONE | `simulate.py` does not call `seed_symbol_from_cache` or `state.last_tick_price`. The new `_seeding` check in `on_trade_price` is also unreachable in backtest because `simulate.py` does not call `begin_seed()` (it uses `seed_bar_close` directly, no replay-tick path). VERO/ROLR untouched. |
| Concurrency: `state.last_tick_price[symbol]` read in non-thread-safe context | LOW | dict reads in CPython are atomic under the GIL. The seed function and ticker handler both run on the main asyncio loop (ib_insync is single-threaded). No race on the read. |
| FCHL-style orphan resume path | NONE | FCHL fix (P0.1 in `2026-05-16_fchl_session_resume_fix.md`) operates at `decide_boot_mode` BEFORE seed. It's orthogonal to this fix. Both can coexist. |

**No-bug-introduced scenarios verified:**
- Cold start (no resume): unaffected, patch is no-op.
- Resume with no cached ticks for symbol: falls back to `seed_symbol` (line 1264), patch is no-op.
- Resume with cached ticks but no prior ARM: `armed=None` short-circuits both `on_trade_price` (line 290) and `validate_arm_after_seed` (line 131).
- Resume where live price is BELOW trigger (e.g. cooled off): `validate_arm_after_seed` keeps the arm (stale_ratio ≤ 2%), entry fires legitimately on the next live tick AFTER `_seed_just_ended` clears.

### 5.4 Observability — what to watch in the first session post-deploy

Add a one-line log when the new `_seeding` gate fires (recommended in patch but not in the minimal diff above):

```python
if self._seeding:
    # one-time log per arm, so we don't spam
    if not getattr(self, "_logged_seed_race_block", False):
        self._logged_seed_race_block = True
    return None
```

Or more verbose for the first week:

```python
if self._seeding:
    return f"SQ_SEED_RACE_BLOCK: live tick @ ${price:.2f} suppressed during seed replay (armed @ ${self.armed.trigger_high:.2f})"
```

Then grep the next morning's daily.log for `SQ_SEED_RACE_BLOCK` lines. Zero = fix is sufficient; many = need to also tackle defense-in-depth at the subscribe level.

---

## 6. Follow-ups (out of scope for this patch)

1. **Extend the `_seeding` gate to MP, CT, Short detectors.** Audit each `on_trade_price` to confirm none have the same race. Recommend a single shared base class or a per-detector seeding state machine to avoid drift.
2. **Reorder `subscribe_symbol` to seed BEFORE reqMktData.** This is the architecturally cleaner fix — no race window at all. Riskier (changes the subscription contract; need to verify IBKR doesn't lose initial ticks if reqMktData is delayed). Tracked as a follow-up DIRECTIVE; the current patch is the surgical near-term fix.
3. **Stamp `_signal_acted_on` per arm in `open_trades.json`-equivalent state.** Section 8.2 of the max-chase audit mentioned this — would let resume rehydrate "we already chased this signal, don't try again." Combined with #2 it's belt-and-suspenders.
4. **Investigate why the bot restarted 6 times in 90 minutes 2026-05-15 evening.** That's a separate watchdog/scanner stability issue. The fix here prevents the stale-signal-spam SYMPTOM but the root cause of frequent restarts is unaddressed.

---

## 7. Files referenced (all paths absolute)

- `/Users/duffy/warrior_bot_v2/bot_v3_hybrid.py:1241-1275` — `subscribe_symbol` (race site)
- `/Users/duffy/warrior_bot_v2/bot_v3_hybrid.py:1787-1894` — `seed_symbol_from_cache` (replay function)
- `/Users/duffy/warrior_bot_v2/bot_v3_hybrid.py:1866-1874` — stale-arm validator call (patch site B)
- `/Users/duffy/warrior_bot_v2/bot_v3_hybrid.py:3838-3955` — `on_ticker_update` → `_process_trade_tick` → `check_triggers` (race delivery path)
- `/Users/duffy/warrior_bot_v2/bot_v3_hybrid.py:2425-2481` — `check_triggers` → `sq.on_trade_price` (race endpoint)
- `/Users/duffy/warrior_bot_v2/bot_alpaca_subbot.py:2296-2400` — sub-bot's parallel `seed_symbol_from_cache` (also needs patch)
- `/Users/duffy/warrior_bot_v2/squeeze_detector.py:89-97` — `_seeding` / `_seed_just_ended` / `_seed_stale_pct` state
- `/Users/duffy/warrior_bot_v2/squeeze_detector.py:122-150` — `validate_arm_after_seed`
- `/Users/duffy/warrior_bot_v2/squeeze_detector.py:289-315` — `on_trade_price` (patch site A — the missing `_seeding` gate)
- `/Users/duffy/warrior_bot_v2/logs/2026-05-15_daily.log` — lines 30965-30978 (SLE 16:17 ET buggy sequence), repeated at 32262, 36999, 38471, 47105, 50455
- `/Users/duffy/warrior_bot_v2/tick_cache/2026-05-15/SLE.json.gz` — 477,498 cached ticks; replay-tail price $5.91 (index 472,278 at first restart)
- `/Users/duffy/warrior_bot_v2/cowork_reports/2026-05-18_max_chase_missed_opportunity_audit.md` — Section 8.2 flagged this exact issue as "fix the resume-boot stale-signal loop (HIGH PRIORITY)"

---

## 8. Sign-off checklist for Cowork

Cowork (Perplexity) review checklist before green-light:

- [ ] Confirm Option 2 + Option 1 combination is preferred over Option 1-only or Option 3.
- [ ] Confirm the diff is gated to `seed_symbol_from_cache` (resume-only); cold path untouched.
- [ ] Confirm sub-bot (`bot_alpaca_subbot.py`) is included in the patch.
- [ ] Confirm the rollout window (post-close 2026-05-19) and ack the Wednesday 2026-05-20 paper-trade exposure.
- [ ] Confirm regression command set (VERO + ROLR backtests) covers the no-regression bar.
- [ ] Confirm follow-up #1 (extend gate to MP/CT/Short) is captured for a separate DIRECTIVE.
- [ ] Optional: ack the runtime escape hatch (`WB_SEED_GATE_BARS=999`) as a panic-button fallback.

Once acked, CC (Sonnet) executes the patch + regression + push. No autonomous deploy.

---

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
