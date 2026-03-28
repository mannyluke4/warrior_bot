# DIRECTIVE: CT Regression Retest — Deferred Activation Fix

**Date:** 2026-03-28  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P0 — Must pass before any further CT work  
**Commit:** 43e7585 (deferred activation)

---

## What Changed

`notify_squeeze_closed()` no longer activates CT directly. It queues data into `_pending_activation`. The actual activation only happens via `check_pending_activation()`, which is called INSIDE the SQ IDLE gate in the bar-close path. This guarantees zero CT state changes during SQ cascades.

---

## Run These Tests In Order

### Test 1: VERO Regression (MUST MATCH)

```bash
# Baseline
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=0 WB_MP_ENABLED=0 WB_MP_V2_ENABLED=0 \
python3 simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/

# With CT
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 WB_MP_ENABLED=0 WB_MP_V2_ENABLED=0 \
python3 simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
```

**Pass:** Both produce IDENTICAL P&L. Zero CT trades. If delta is not exactly $0, STOP — the deferred activation is still leaking.

### Test 2: ROLR Regression (MUST MATCH)

```bash
# Baseline
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=0 WB_MP_ENABLED=0 WB_MP_V2_ENABLED=0 \
python3 simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/

# With CT
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 WB_MP_ENABLED=0 WB_MP_V2_ENABLED=0 \
python3 simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```

**Pass:** Both produce IDENTICAL P&L. Zero CT trades.

### Test 3: EEIQ Value-Add (verbose — see what CT does)

```bash
# Baseline
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=0 WB_MP_ENABLED=0 WB_MP_V2_ENABLED=0 \
python3 simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose

# With CT (verbose to see all CT signals)
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 WB_MP_ENABLED=0 WB_MP_V2_ENABLED=0 \
python3 simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose
```

**What to look for in verbose output:**
- `CT_ACTIVATED` — confirms deferred activation fired after SQ went idle
- `CT_WATCHING` — CT is hunting pullbacks
- `CT_PULLBACK` — pullback forming
- `CT_PRIMED` → `CT_ARMED` → `CT ENTRY SIGNAL` — the full success path
- `CT_REJECT: pullback volume too high (Xx squeeze avg)` — note the X value. If X < 1.5, it should have passed. If X > 1.5, the gate is working correctly.

**Pass:** SQ+CT P&L ≥ SQ-only. Ideal: CT fires at least one re-entry.

### Test 4: CRE Sanity

```bash
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 WB_MP_ENABLED=0 WB_MP_V2_ENABLED=0 \
python3 simulate.py CRE 2026-03-06 07:00 12:00 --ticks --tick-cache tick_cache/
```

**Pass:** Same P&L as SQ-only baseline (+$4,560).

---

## Results Template

| Test | SQ-Only | SQ+CT | Delta | CT Trades | Notes |
|------|---------|-------|-------|-----------|-------|
| VERO | | | MUST be $0 | 0 | |
| ROLR | | | MUST be $0 | 0 | |
| EEIQ | | | ≥$0 | | Paste reject reasons if 0 trades |
| CRE | | | $0 | 0 | |

---

## Decision Tree

```
VERO delta = $0 AND ROLR delta = $0?
  ├── YES → Regression fixed. Check EEIQ:
  │         ├── EEIQ CT fires with positive P&L → CT is working. Run full YTD A/B.
  │         ├── EEIQ CT fires with negative P&L → Gates need tuning. Note which exit lost.
  │         └── EEIQ CT doesn't fire → Note reject reasons. May need to:
  │               • Relax MACD gate (WB_CT_REQUIRE_MACD=0)
  │               • Relax retrace depth (WB_CT_MAX_RETRACE_PCT=65)
  │               • Check if volume gate is actually reading 1.50 default
  │
  └── NO → Deferred activation is still leaking. STOP.
           Log the exact P&L for both modes and the verbose output.
           Push to cowork_reports/ for analysis.
```

---

## If EEIQ Still Rejects All Pullbacks

Run with each gate relaxed individually to find which one is blocking:

```bash
# Test A: No MACD gate
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 WB_CT_REQUIRE_MACD=0 \
python3 simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose

# Test B: Deeper retrace allowed
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 WB_CT_MAX_RETRACE_PCT=65 \
python3 simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose

# Test C: No VWAP requirement
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 WB_CT_REQUIRE_VWAP=0 \
python3 simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose

# Test D: Wider volume gate
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 WB_CT_MIN_VOL_DECAY=3.0 \
python3 simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose
```

Report which relaxation (if any) lets CT fire, and what the trade result is. This tells us which gate to tune.
