# CT (Continuation Trading) Validation Results
## Date: 2026-03-28
## Branch: v2-ibkr-migration
## Data: IBKR historical ticks

---

## Summary: CT IS NOT READY FOR DEPLOYMENT

Two blocking issues:
1. **Regression failure** — CT degrades VERO (-$306) and ROLR (-$794), same SQ-priority interference seen with MP V2
2. **Volume gate too strict** — EEIQ's pullbacks all rejected due to "pullback volume too high"

---

## Test Results

| Test | Stock | SQ-Only P&L | SQ+CT P&L | Delta | CT Trades | Pass? |
|------|-------|------------|-----------|-------|-----------|-------|
| 1 | VERO | +$562 | +$256 | -$306 | ? | **FAIL** |
| 2 | ROLR | +$12,601 | +$11,807 | -$794 | ? | **FAIL** |
| 3 | EEIQ | +$1,671 | +$1,671 | $0 | 0 (rejected) | NEUTRAL |
| 4 | NPT | N/A | N/A | — | — | No tick data |
| 5 | CRE | +$4,560 | +$4,560 | $0 | 0 | PASS |
| 7 | ONCO | +$562 | +$562 | $0 | 0 | PASS |

---

## EEIQ Verbose Signal Log

CT activated after SQ trade closed at 10:05 ET. After 3-bar cooldown, CT began hunting pullbacks. Every pullback was rejected:

| Time | Event | Detail |
|------|-------|--------|
| 10:05 | CT_COOLDOWN | 2 bars remaining |
| 10:06 | CT_COOLDOWN | 1 bar remaining |
| 10:07 | CT_WATCHING | Cooldown expired, hunting pullbacks |
| 10:08-10:10 | CT_PULLBACK | 3 bars, low=$10.39 |
| 10:11 | **CT_REJECT** | pullback volume too high (1.6x squeeze avg) |
| 10:13-10:14 | CT_PULLBACK | 2 bars, low=$10.42 |
| 10:15 | **CT_REJECT** | pullback volume too high (1.1x squeeze avg) |
| 10:17-10:19 | CT_PULLBACK | 3 bars, low=$9.27 |
| 10:20 | **CT_REJECT** | pullback volume too high (1.1x squeeze avg) |
| 10:21-10:22 | CT_PULLBACK | 2 bars, low=$7.82 |
| 10:32 | **CT_REJECT** | pullback volume too high (0.9x squeeze avg) |
| 10:34-10:36 | CT_PULLBACK | 3 bars, low=$6.91 |

**Pattern:** EEIQ's pullbacks after the $8.94→$12.70 squeeze all had high volume (sell-offs). CT's volume decay gate requires pullback volume to be significantly lower than squeeze volume, which never happens on EEIQ because the sell-offs are almost as active as the buy-ups.

---

## Regression Issue Analysis

VERO dropped from +$562 to +$256 and ROLR from +$12,601 to +$11,807 with CT enabled. This is the same interference pattern seen with MP V2 — CT's state changes or position slot competition are affecting SQ's cascade entries.

**Root cause likely same as MP V2:** CT needs a stricter SQ-priority gate that completely defers when SQ is in any non-IDLE state.

---

## Recommendations

1. **Do not enable CT for live** — regression failures block deployment
2. **Fix SQ-priority gate** — same fix needed as MP V2 (CT defers when SQ is PRIMED/ARMED/in-trade)
3. **Relax volume decay gate** — try `WB_CT_MIN_VOL_DECAY=0.80` (allow pullback vol up to 80% of squeeze vol) instead of current setting
4. **Consider: is CT fundamentally different from MP V2?** Both attempt post-squeeze re-entries. MP V2 was -$54K drag, CT appears similar. The signal log shows the same pullback patterns being detected and rejected.

---

## Current Live Configuration (unchanged)

```
WB_SQUEEZE_ENABLED=1    # Primary strategy
WB_CT_ENABLED=0          # NOT READY
WB_MP_ENABLED=0          # Standalone MP dead
WB_MP_V2_ENABLED=0       # -$54K drag
```

SQ-only remains the proven path: $30K → $296K (+888%) YTD on IBKR ticks.
