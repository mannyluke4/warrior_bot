# CT Validation V2 — After SQ IDLE Gate + Volume Decay Fix
## Date: 2026-03-28
## Commit: a0c77ad (SQ IDLE gate + volume decay 0.50→1.50)

---

## Results: Regressions Still Failing

| Test | Stock | SQ-Only | SQ+CT | Delta | CT Trades | Pass? |
|------|-------|---------|-------|-------|-----------|-------|
| 1 | VERO | +$562 | +$256 | **-$306** | 0 | **FAIL** |
| 2 | ROLR | +$12,601 | +$11,807 | **-$794** | 0 | **FAIL** |
| 3 | EEIQ | +$1,671 | +$1,671 | $0 | 0 (rejected) | NEUTRAL |
| 5 | CRE | +$4,560 | +$4,560 | $0 | 0 | PASS |
| 7 | ONCO | +$562 | +$562 | $0 | 0 | PASS |

---

## Why the Fix Didn't Work

The SQ IDLE gate (`sq_det._state == "IDLE"`) is correct but insufficient. On cascading stocks like VERO:

1. SQ trade 1 closes at 07:16 → SQ resets to IDLE momentarily
2. `notify_squeeze_closed()` fires → CT enters COOLDOWN
3. CT counts down cooldown bars (07:19, 07:20, 07:21)
4. SQ re-primes on the next volume bar — but there's a gap where SQ is IDLE
5. During that gap, CT processes bars and starts WATCHING/PULLBACK detection
6. CT's state changes (even without entering a trade) subtly affect the sim flow

The SQ IDLE gate checks `_state == "IDLE"` at the moment of bar processing, but SQ bounces through IDLE between cascade legs. CT is processing bars during those brief IDLE windows.

---

## EEIQ Signal Log (volume gate relaxed to 1.50x)

Volume decay threshold is now 1.50x (was 0.50x). Some pullbacks now pass closer to threshold but the densest ones still reject:

| Time | Event | Volume Ratio |
|------|-------|-------------|
| 10:11 | CT_REJECT | 1.6x (still over 1.5x) |
| 10:15 | CT_REJECT | 1.1x (would pass new gate!) |
| 10:20 | CT_REJECT | 1.1x (would pass!) |
| 10:32 | CT_REJECT | 0.9x (would pass!) |
| 10:37 | CT_REJECT | 0.8x (would pass!) |

Wait — the 1.1x and 0.9x pullbacks are BELOW the 1.5x threshold but still rejecting. **The volume gate change may not have taken effect.** The continuation_detector.py change was `0.50→1.50` but the log still shows rejections at ratios below 1.5x.

Possible issue: the detector is reading the old default from an env var override, or there's a second volume check.

---

## Recommended Fix

**For regression:** Instead of checking SQ state at bar-process time, use a time-based lockout:
```python
# CT stays locked for N minutes after ANY SQ trade close
# Don't rely on SQ._state which bounces through IDLE between cascades
_ct_lockout_until = None  # Set to timestamp when SQ trade closes
_ct_lockout_minutes = 5   # Lock CT out for 5 min after SQ trade

# When SQ trade closes:
_ct_lockout_until = now + timedelta(minutes=5)

# CT gate:
if _ct_lockout_until and now < _ct_lockout_until:
    return  # CT locked out
```

**For volume gate:** Verify `WB_CT_MIN_VOL_DECAY` env var is being read correctly in the continuation_detector and that the default change from 0.50 to 1.50 actually propagates.

---

## Status: CT Still Not Ready

Keep `WB_CT_ENABLED=0` for live. SQ-only at +$296K YTD remains the config.
