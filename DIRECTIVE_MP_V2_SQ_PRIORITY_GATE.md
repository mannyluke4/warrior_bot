# Directive: MP V2 — SQ Priority Gate + EEIQ Validation
## Priority: CRITICAL — Blocks Monday deployment
## Date: 2026-03-27
## Depends On: Commit 7c9d302 (MP V2 implementation)

---

## Problem

MP V2 (commit 7c9d302) regressed VERO from +$18,583 to +$15,692 (-$2,891).

**Root cause:** On cascading stocks (VERO), after the first SQ trade closes, `notify_squeeze_closed()` unlocks MP V2. If MP V2 arms and triggers before SQ re-arms, MP V2 takes the position slot. The bot ends up in an `mp_reentry` trade instead of a second squeeze entry. SQ's cascade — the proven $18.6K path — gets cannibalized.

**Fix:** SQ gets unconditional priority. MP V2 only triggers when SQ is not actively hunting.

---

## Step 1: Add SQ-Priority Gate in simulate.py

In the MP trigger section (both bar-mode and tick-mode paths), before executing an `mp_reentry` entry, check if the squeeze detector is actively engaged:

```python
# Before entering mp_reentry, check if SQ has priority
if _armed_setup_type == "mp_reentry" and sq_enabled:
    sq_state = sq_det._state  # "IDLE", "PRIMED", "ARMED"
    sq_in_trade = sq_det._in_trade
    if sq_state != "IDLE" or sq_in_trade:
        if verbose:
            print(f"  [{time_str}] MP_V2_DEFERRED: SQ has priority (state={sq_state}, in_trade={sq_in_trade})", flush=True)
        # Don't enter — let SQ take the next trade
        # But don't disarm MP — it may still be valid if SQ resets
        continue  # or equivalent flow control
```

**Where to insert (2 places in simulate.py):**
1. Bar-mode MP trigger path (~line 2619, after toxic/score/mp_enabled checks)
2. Tick-mode MP trigger path (~line 2908, after toxic/score/mp_enabled checks)

**Key detail:** Do NOT disarm the MP detector when deferring. If SQ fires and wins, great. If SQ resets without entering, the MP arm is still valid and can trigger on the next tick.

---

## Step 2: Add SQ-Priority Gate in bot_ibkr.py

In `check_triggers()`, same logic:

```python
# In check_triggers(), after "ENTRY SIGNAL" check for MP:
if _mp_setup_type == "mp_reentry" and SQ_ENABLED and symbol in state.sq_detectors:
    sq = state.sq_detectors[symbol]
    if sq._state != "IDLE" or sq._in_trade:
        print(f"[{now_str} ET] {symbol} MP_V2 | DEFERRED (SQ priority: state={sq._state})", flush=True)
        return  # Let SQ take it
```

---

## Step 3: Add Per-Re-Entry Cooldown

Current bug: cooldown only fires on the initial unlock (`notify_squeeze_closed`). After the first mp_reentry trade closes, the detector immediately starts hunting for the next pullback with zero cooldown.

In `micro_pullback.py`, when `_reentry_count` is incremented (currently done externally in simulate.py and bot_ibkr.py), also reset the cooldown:

```python
# Option A: Add a method to MicroPullbackDetector
def notify_reentry_closed(self):
    """Called when an mp_reentry trade closes. Resets cooldown for next re-entry."""
    self._reentry_count += 1
    self._cooldown_bars_remaining = self._reentry_cooldown
    self._full_reset_1m()
    # Re-set impulse (squeeze was still the impulse)
    self.in_impulse_1m = True
```

Replace the external `det._reentry_count += 1` calls in simulate.py and bot_ibkr.py with `det.notify_reentry_closed()`.

---

## Step 4: Env Var Gate (Safety)

Add one new env var to control the priority gate independently:

```
WB_MP_V2_SQ_PRIORITY=1   # Default ON — SQ always has priority over MP V2
```

When OFF, MP V2 can compete freely with SQ (current broken behavior). This lets us A/B test later if we discover stocks where MP V2 re-entries are actually better than SQ cascades.

---

## Regression Tests

### Test 1: VERO Regression — MUST Return to +$18,583

```bash
WB_MP_ENABLED=1 WB_MP_V2_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
```

Expected: +$18,583 (SQ cascade unaffected, MP V2 deferred on every leg because SQ is always PRIMED/ARMED)

### Test 2: VERO SQ-Only Baseline (sanity check)

```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
```

Expected: +$18,583 (unchanged from pre-V2)

### Test 3: ROLR Regression

```bash
WB_MP_ENABLED=1 WB_MP_V2_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```

Expected: +$6,444 (should be unaffected — if SQ cascade dominates, MP V2 stays deferred)

### Test 4: EEIQ — MP V2 Value Add

```bash
WB_MP_ENABLED=1 WB_MP_V2_ENABLED=1 python simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/
```

This is the validation stock. EEIQ had one squeeze entry on 3/26, then Ross made the bulk of his $37.8K on continuation entries. If MP V2 catches even one re-entry after the SQ exits, that's incremental P&L the bot currently leaves on the table.

Run this BOTH ways:
- SQ only: `WB_MP_V2_ENABLED=0`
- SQ + MP V2: `WB_MP_V2_ENABLED=1`

Compare the P&L delta. This is the proof that MP V2 adds value.

### Test 5: EEIQ SQ-Only Baseline (with --no-fundamentals)

```bash
WB_MP_ENABLED=1 python simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --no-fundamentals
```

Note: EEIQ may need `--no-fundamentals` if Alpaca returns stale float data (known gap). Check whether the scanner filter blocks EEIQ without this flag.

### Test 6: Quiet Day — MP V2 Stays Dormant

```bash
WB_MP_ENABLED=1 WB_MP_V2_ENABLED=1 python simulate.py ONCO 2026-03-27 07:00 12:00 --ticks --tick-cache tick_cache/
```

Expected: 0 trades (no squeeze fires, MP V2 stays dormant)

---

## Success Criteria

| Test | Metric | Pass |
|------|--------|------|
| VERO | P&L | +$18,583 exactly |
| ROLR | P&L | +$6,444 exactly |
| EEIQ SQ-only | P&L | Baseline number |
| EEIQ SQ+V2 | P&L | > SQ-only baseline |
| ONCO | Trades | 0 |

**Monday deployment gate:** ALL of tests 1-3 must pass. Test 4 (EEIQ V2 > baseline) is desired but not blocking — if MP V2 doesn't fire on EEIQ, it means the stock's pullback pattern didn't match the detector's criteria, which is information not failure.

---

## Files to Modify

1. `micro_pullback.py` — Add `notify_reentry_closed()` method
2. `simulate.py` — Add SQ-priority gate in 2 trigger paths, replace `_reentry_count += 1` with `notify_reentry_closed()`
3. `bot_ibkr.py` — Add SQ-priority gate in `check_triggers()`, replace `_reentry_count += 1` with `notify_reentry_closed()`
4. `.env` — Add `WB_MP_V2_SQ_PRIORITY=1`

## Commit Message Template

```
Add SQ-priority gate for MP V2 re-entries + per-re-entry cooldown

Fixes VERO regression (+$15,692 → +$18,583): SQ now has unconditional
priority when PRIMED/ARMED/in-trade. MP V2 defers and retains arm state
for when SQ goes idle. Also adds per-re-entry cooldown via
notify_reentry_closed() to prevent rapid-fire losing re-entries.

New env var: WB_MP_V2_SQ_PRIORITY=1 (default ON)

Regression: VERO +$18,583, ROLR +$6,444
EEIQ validation: SQ-only=$X, SQ+V2=$Y (delta=$Z)
```
