# Dynamic Player V1 — Test Results
## Date: 2026-03-30
## Commit: a5c69b7

---

## Test Matrix Results

| Stock | SQ-Only | SQ+DP | Delta | DP Trades | Status |
|-------|---------|-------|-------|-----------|--------|
| ASTC | +$1,209 | +$1,209 | $0 | 0 | Correct — dips too deep |
| EEIQ | +$1,671 | +$1,671 | $0 | 0 | Halt detection blocking |
| CRE | +$4,560 | +$4,560 | $0 | 0 | Halt detection blocking |
| ROLR | +$12,601 | +$12,601 | **$0** | 0 | **REGRESSION PASS** |
| VERO | +$562 | -$188 | **-$750** | ? | **REGRESSION FAIL** |

---

## ASTC Scorecard Detail

Three dips scored, all rejected:

| Dip Time | Retrace | VWAP | EMA | Duration | Vol Ratio | Prior HOD | Score | Action |
|----------|---------|------|-----|----------|-----------|-----------|-------|--------|
| 10:24 | 122% RED | above GREEN | above GREEN | 1m GREEN | 1.02x YELLOW | yes GREEN | 4G/1Y/1R | SKIP |
| 10:26 | 136% RED | above GREEN | below RED | 1m GREEN | 0.52x GREEN | no RED | 3G/0Y/3R | SKIP |
| 10:28 | 63% YELLOW | above GREEN | recovered YELLOW | 1m GREEN | 0.41x GREEN | no RED | 3G/2Y/1R | SKIP → DONE |

The first dip (122% retrace) is the shakeout — deep but VWAP/EMA hold. Second dip (136%) is worse — EMA broken, no new HOD. Third (63%) is better but still no new HOD. After 3 fails → DONE.

The wave analysis showed ASTC's best dips were at 10:35-10:57 (waves 4-10) with 40-54% retraces and new HODs every time. DP gives up before reaching them.

---

## Halt Detection Issue (EEIQ + CRE)

Both stocks trigger halt detection on every bar:
```
[10:05] DP: HALT DETECTED
[10:06] DP: HALT DETECTED
... (repeats every bar)
```

The 10% gap threshold is too tight for volatile small-caps. After a squeeze, price gaps between consecutive 1m bars regularly exceed 10%:
- EEIQ: SQ exit at $9.45, next bars oscillate $8-$12 = normal post-squeeze volatility
- CRE: SQ exit at $6.89, bars $5-$8 range = same

**Fix needed:** Increase halt threshold to 20-30%, or use actual IBKR halt detection (Tick Type 49) instead of price-gap heuristic.

---

## VERO Regression (-$750)

VERO shows -$750 with DP enabled vs +$562 SQ-only. Need verbose investigation to determine:
1. Did DP fire trades that lost money?
2. Did DP's state machine somehow affect SQ trade timing?
3. Is the halt detection interfering with the SQ cascade?

---

## Issues to Fix (Priority Order)

1. **Halt detection threshold** — increase from 10% to 25% to stop false halt triggers
2. **VERO regression** — investigate and fix
3. **Patience tuning** — ASTC needs DP to survive 3+ shakeout dips to reach the profitable ones
4. **"Prior HOD" gate** — early dips after SQ always score RED on this (HOD was set during squeeze, dips haven't recovered yet). Consider Yellow instead of Red for first 2-3 dips.
