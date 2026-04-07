# DIRECTIVE: Gate Stale Entries After Seed Replay

**Date:** April 7, 2026
**Author:** Cowork (Opus)
**For:** CC (Claude Code)
**Priority:** P0 — live bot placed 4 orders at stale prices on April 6, all failed
**Prereq:** Option C seed fix already deployed and validated (SEED_PARITY_REPORT.md confirms 100% parity)

---

## The Problem

After seed replay completes, the squeeze detector can be in ARMED state from historical price action. When the first live tick arrives, the bot immediately fires an entry signal at a price from hours ago. The stock has moved far away by then — the order either times out (best case) or fills into an instant loss (worst case).

**April 6 evidence (from ORDER_TIMEOUT_ANALYSIS.md):**

| Time (ET) | Symbol | Armed Price | Actual Price | Gap | Result |
|-----------|--------|-------------|-------------|-----|--------|
| 09:48 | FCUV | $8.45 | $9.23 | +$0.78 | Timeout (protective) |
| 16:03 | FCUV | $5.02 | $5.47 | +$0.43 | Timeout (protective) |
| 16:07 | MLEC | $10.02 | $11.60 | +$1.56 | Timeout (protective) |
| 16:10 | PRFX | $3.02 | $2.55 | -$0.47 | Would have filled into loss |

The seed correctly warms up EMA, VWAP, vol baselines, and HOD — that's working perfectly (Test 3 confirmed). But it should NOT generate trade entries from historical breakout levels.

---

## The Fix

### Core Concept
Add a `seed_complete` flag to the squeeze detector. After seeding finishes, suppress entry signals until the detector has seen enough live data to confirm the armed level is still relevant.

### Implementation

**Step 1: Add seed tracking to SqueezeDetector**

```python
# In squeeze_detector.py __init__:
self._seeding = False        # True during seed replay
self._seed_just_ended = False  # True after seed, before live validation
self._live_ticks_since_seed = 0
self._live_bars_since_seed = 0
```

**Step 2: Add seed lifecycle methods**

```python
def begin_seed(self):
    """Call before replaying seed ticks/bars."""
    self._seeding = True
    self._seed_just_ended = False
    self._live_ticks_since_seed = 0
    self._live_bars_since_seed = 0

def end_seed(self):
    """Call after seed replay completes, before live data starts."""
    self._seeding = False
    self._seed_just_ended = True
    self._live_ticks_since_seed = 0
    self._live_bars_since_seed = 0
```

**Step 3: Modify on_bar_close_1m to track live bars**

After the seed ends, count live bars. The detector should continue processing bars normally (updating EMA, vol averages, HOD, state transitions) — the only thing suppressed is the ENTRY SIGNAL output.

```python
def on_bar_close_1m(self, bar, vwap=None):
    if not self._seeding and self._seed_just_ended:
        self._live_bars_since_seed += 1
    # ... rest of existing logic unchanged
```

**Step 4: Modify on_tick (or wherever entry signals fire) to gate entries**

The entry signal is where a tick crosses the armed trigger price. This is the ONLY place we gate:

```python
# Where the entry signal would fire (tick crosses armed level):
if self._seed_just_ended:
    min_live_bars = int(os.environ.get("WB_SEED_GATE_BARS", "2"))
    if self._live_bars_since_seed < min_live_bars:
        # Log but don't signal entry
        return f"SQ_SEED_GATE: suppressed entry — only {self._live_bars_since_seed}/{min_live_bars} live bars since seed"
    else:
        # Enough live bars seen — clear the gate
        self._seed_just_ended = False
        # Fall through to normal entry signal
```

**Step 5: Handle state transitions during gate period**

During the gate period, the detector should STILL:
- ✅ Process bars (update EMA, VWAP, vol averages, HOD)
- ✅ Transition states (IDLE → PRIMED → ARMED)
- ✅ Reset if conditions invalidate (VWAP lost, prime expired, etc.)
- ❌ NOT fire entry signals (the only thing gated)

This is important: if the detector is ARMED from seed data but the stock drops below VWAP during the gate period, it should reset normally. The gate doesn't freeze the detector — it just prevents stale entries.

**Step 6: Wire into bot_v3_hybrid.py**

In the seed/subscribe flow where historical ticks are replayed:

```python
# Before seed replay:
detector.begin_seed()

# Replay seed ticks through TradeBarBuilder...
for tick in seed_ticks:
    bar_builder.on_trade(symbol, tick['p'], tick['s'], tick['t'])
    # on_trade triggers on_bar_close_1m when bars complete

# After seed replay:
detector.end_seed()

# Live ticks now flow normally — gate handles suppression
```

**Step 7: Log the gate events**

When a seed gate suppression fires, log it clearly so we can see it in daily logs:

```
[07:58:01 ET] FCUV SQ | SQ_SEED_GATE: suppressed entry @ $8.45 — 0/2 live bars since seed (stock at $9.23)
[07:59:01 ET] FCUV SQ | SQ_SEED_GATE: suppressed entry @ $8.45 — 1/2 live bars since seed
[08:00:01 ET] FCUV SQ | Seed gate cleared — 2 live bars seen, detector fully live
```

Include the current actual price in the suppression log so we can see how stale the armed level is.

---

## Env Var

```
WB_SEED_GATE_BARS=2    # Minimum live bars before allowing entries after seed (default 2)
```

Default of 2 means the detector needs to see 2 full 1-minute bars of live data before it can fire entries. This gives 2 minutes of live price discovery — enough to confirm the armed level is still relevant, without missing fast setups.

**Gate this feature with an env var for the gate itself:**

```
WB_SEED_GATE_ENABLED=1   # ON by default — this fixes a confirmed live bug
```

Normally we gate features OFF by default. This one should be ON by default because:
1. The bug is confirmed (4 stale orders on April 6)
2. Without the gate, the bot will place losing orders every time it seeds
3. The gate is purely defensive — it never prevents a legitimate live entry, only stale seed entries

---

## What NOT to Change

- Do NOT change `_avg_prior_vol()` or `vol_ratio` computation — Test 1 confirmed these are fine
- Do NOT change the limit price buffer ($0.02) or order timeout (10s) — these are not the issue
- Do NOT change the seed replay itself (Option C) — Test 3 confirmed it achieves perfect parity
- Do NOT reset the detector after seeding — the armed state from seed data is useful context, it just shouldn't trigger immediate entries

---

## Validation

After implementing, re-run the April 6 backtest:

```bash
WB_MP_ENABLED=1 WB_SEED_GATE_ENABLED=1 python simulate.py FCUV 2026-04-06 07:00 12:00 --ticks --tick-cache tick_cache/
```

The sim should produce the SAME trades as before (seed gate only affects the live bot path, not the sim's organic replay). Verify the gate doesn't accidentally suppress legitimate sim entries.

Also run regression:
```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```

Targets: VERO +$15,692, ROLR +$6,444.

---

## Edge Cases to Consider

1. **Stock discovered during active session (not cold start):** If the bot discovers a new stock mid-session (rescan), it seeds that stock while already running. The gate should apply per-symbol — gating FCUV's seed shouldn't block an unrelated MLEC entry.

2. **Very short seed (stock just discovered):** If the seed has only a few bars (stock appeared on scanner 2 minutes ago), the gate still applies. Even 2 bars of live data is enough to confirm the armed level is fresh.

3. **Detector resets during gate:** If the detector goes ARMED during seed → resets (VWAP lost) during gate → re-arms from live data, the re-arm is a legitimate live entry. The gate should clear when `_seed_just_ended` is False (which happens after `min_live_bars` are seen, regardless of state transitions).

4. **Multiple seeds for same symbol:** If a symbol is re-seeded (reconnect, rescan), call `begin_seed()` again — this resets the gate counters.

---

*Directive by Cowork (Opus). For CC execution.*
