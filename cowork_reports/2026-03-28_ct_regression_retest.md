# CT Regression Retest — Deferred Activation + Volume Gate Fix
## Date: 2026-03-28
## Commits: 82c0bbf (deferred activation), .env fix (CT_MIN_VOL_DECAY 0.50→1.50)

---

## Results

| Test | SQ-Only | SQ+CT | Delta | CT Trades | Pass? |
|------|---------|-------|-------|-----------|-------|
| VERO | +$562 | +$412 | -$150 | 0 | **FAIL** (improved from -$306) |
| ROLR | +$12,601 | +$12,298 | -$303 | 0 | **FAIL** (improved from -$794) |
| EEIQ | +$1,671 | +$1,892 | **+$221** | **2** | **PASS** |
| CRE | +$4,560 | +$4,560 | $0 | 0 | PASS |

---

## EEIQ: CT FIRES AND ADDS VALUE

Two continuation entries after the squeeze:

| # | Time | Entry | Stop | R | Exit | Reason | P&L |
|---|------|-------|------|---|------|--------|-----|
| SQ | 10:00 | $8.94 | $8.80 | $0.14 | $9.45 | sq_target_hit | +$1,671 |
| CT1 | 11:02 | $8.57 | $8.14 | $0.43 | ? | ? | ? |
| CT2 | 11:11 | $8.90 | $8.16 | $0.74 | ? | ? | ? |
| **Total** | | | | | | | **+$1,892** |

CT added +$221 in incremental P&L on EEIQ. The signal flow:
1. SQ fires at 10:00, exits at 10:05 (sq_target_hit)
2. CT activates at 10:05, 3-bar cooldown
3. CT watches pullbacks from 10:07-11:01 — rejects due to volume (1.6x), MACD negative, below EMA, below VWAP
4. Stock recovers above VWAP/EMA around 11:00
5. CT arms at 11:01 ($8.55 entry, $8.14 stop) → enters at 11:02
6. CT arms again at 11:06 ($8.88 entry) → enters at 11:11

The gates worked correctly — rejected the dangerous 10:08-10:50 sell-off period and only entered when the stock recovered above VWAP and EMA.

---

## Volume Gate Bug Found & Fixed

**Root cause of all prior "pullback volume too high" rejections at 0.9x, 0.8x etc:**

`.env` had `WB_CT_MIN_VOL_DECAY=0.50` which overrode the code default of 1.50. The code was correctly changed to 1.50 default, but `.env` still had the old 0.50 value. Since simulate.py inherits env vars, the stricter threshold was applied at runtime.

**Fix:** Updated `.env` to `WB_CT_MIN_VOL_DECAY=1.50`.

After fix, reject reasons shifted from "volume too high" to legitimate quality gates (MACD, EMA, VWAP) which correctly blocked entries during the sell-off.

---

## Regression Still Leaking

VERO: -$150 (improved from -$306)
ROLR: -$303 (improved from -$794)

The deferred activation fix improved things significantly but CT is still causing subtle interference. The CT detector is being imported/initialized even on VERO/ROLR which may affect the sim in ways we haven't identified yet.

Possible causes:
- CT's `on_bar_close_1m` is being called during SQ IDLE gaps (briefly between cascade legs)
- CT object initialization changes some shared state
- The `check_pending_activation` call inside the SQ IDLE gate is running and changing CT state

---

## Decision Tree Result

```
VERO delta = $0? → NO (-$150)
→ Deferred activation still leaking. But significantly improved.
→ EEIQ shows CT adds value (+$221 with 2 entries)
→ Recommendation: investigate remaining VERO/ROLR interference, but CT concept is validated on EEIQ
```

---

## Next Steps

1. Investigate remaining VERO/ROLR regression (small but non-zero)
2. Consider: is -$150/$303 acceptable given CT's +$221 on EEIQ? Need YTD A/B to answer
3. Run full YTD A/B if Cowork decides regression is close enough
