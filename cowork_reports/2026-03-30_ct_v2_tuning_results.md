# CT V2 Tuning Results — Cascade Lockout + Soft Gates
## Date: 2026-03-30
## Commit: 0ddc81e
## Directive: DIRECTIVE_CT_V2_TUNING.md

---

## Result: ALL REGRESSIONS PASS AT $0 DELTA

After 4 prior attempts with regression failures (-$306, -$794, -$150, -$303), CT V2 now produces **exactly $0 interference** on every cascade stock tested.

---

## Phase 1: Regression Tests

| Stock | SQ-Only | SQ+CT | Delta | SQ Trades | CT Trades | Pass? |
|-------|---------|-------|-------|-----------|-----------|-------|
| VERO | +$562 | +$562 | **$0** | 3 (cascade) | 0 | **PASS** |
| ROLR | +$12,601 | +$12,601 | **$0** | 3 (cascade) | 0 | **PASS** |
| CRE | +$4,560 | +$4,560 | **$0** | 1 | 0 | **PASS** |
| BATL | +$2,194 | +$2,194 | **$0** | cascade | 0 | **PASS** |
| AHMA | +$2,156 | +$2,156 | **$0** | cascade | 0 | **PASS** |

---

## Phase 2: Value-Add Tests

| Stock | SQ-Only | SQ+CT | Delta | CT Entry | CT Exit | CT P&L |
|-------|---------|-------|-------|----------|---------|--------|
| **EEIQ** | +$1,671 | **+$2,084** | **+$413** | $8.83 @ 11:57 | $9.25 @ 11:59 | +$414 |
| ASTC | +$1,209 | +$1,209 | $0 | — | — | — (lockout covers window) |

### EEIQ Detail

| # | Time | Type | Entry | Stop | R | Exit | Reason | P&L |
|---|------|------|-------|------|---|------|--------|-----|
| 1 | 10:00 | **SQ** | $8.94 | $8.80 | $0.14 | $9.45 | sq_target_hit | +$1,671 |
| 2 | 11:57 | **CT** | $8.83 | $8.45 | $0.38 | $9.25 | sim_end | +$414 |

**Signal flow:**
- 10:00: SQ fires, exits at 10:05 (sq_target_hit, +$1,671)
- 10:05: `notify_squeeze_closed()` → lockout set to 11:05 (60 min)
- 10:05-11:05: CT completely inert — zero processing, zero state changes
- 11:05: Lockout expires, `check_pending_activation()` fires → CT enters WATCHING
- 11:05-11:57: CT monitors pullbacks, soft gates handle temporary VWAP/EMA violations
- 11:57: CT arms and enters at $8.83 (pullback low $8.45 as stop)
- 11:59: Sim ends with position at $9.25 → +$414

### ASTC Detail

ASTC had 2 SQ trades (10:17 and 10:18), so `_sq_trade_count = 2 > max_sq_for_ct = 1`. CT permanently blocked as cascade stock. Additionally, 60-min lockout from 10:23 exit would push CT past noon window close anyway. Double protection.

---

## What Fixed the Regression (Technical Detail)

### Previous Attempts and Why They Failed

| Attempt | Fix | VERO Delta | Root Cause of Failure |
|---------|-----|------------|----------------------|
| V1 (original) | None | -$306 | CT processed bars during SQ IDLE gaps between cascade legs |
| V1.1 (SQ IDLE gate) | Gate on `sq._state == "IDLE"` | -$306 | SQ bounces through IDLE between cascades |
| V1.2 (deferred activation) | Queue activation for IDLE check | -$150 | Activation fires during brief IDLE gap |
| V1.3 (10-min lockout) | Time-based lockout after SQ close | -$284 | 10 min too short — CT fires at 09:30, still loses |
| **V2 (this)** | **60-min lockout + cascade gate** | **$0** | **Cascade stocks blocked by trade count; single-SQ stocks get 60-min wait** |

### The Two-Layer Protection

**Layer 1: Cascade Gate (`_sq_trade_count > _max_sq_for_ct`)**
- Tracks how many SQ trades fired on the symbol
- Default `_max_sq_for_ct = 1` → if SQ fired 2+ trades, CT is permanently blocked
- This catches VERO (3 SQ trades), ROLR (3), BATL, AHMA
- `check_pending_activation()` clears `_pending_activation` and returns "CT BLOCKED: cascade stock"

**Layer 2: 60-Minute Lockout (`_cascade_lockout_min = 60`)**
- Every SQ trade close resets the lockout timer (even losses)
- CT does ZERO processing during lockout — no `on_bar_close_1m()`, no state changes
- Uses bar timestamp (minutes since midnight) for sim accuracy
- On single-SQ stocks like EEIQ: SQ at 10:05 → lockout until 11:05 → CT enters at 11:57

---

## Soft Gates (Item 2)

Changed volume/VWAP/EMA gates from hard reset to soft pause:

| Gate | Old Behavior | New Behavior |
|------|-------------|-------------|
| Volume too high | `_reset()` → discard all pullback bars | `state = WATCHING` → keep pullback context |
| Below VWAP | `_reset()` → discard | `state = WATCHING` → keep pullback context |
| Below EMA | `_reset()` → discard | `state = WATCHING` → keep pullback context |
| **MACD negative** | `_reset()` → discard | **UNCHANGED** (hard gate — dump signal) |
| **Retrace > 50%** | `_reset()` → discard | **UNCHANGED** (hard gate) |
| **Pullback > 5 bars** | `_reset()` → discard | **UNCHANGED** (hard gate) |

This allows CT to recover when a stock briefly dips below VWAP during a pullback and reclaims on the next bar. Previously this destroyed the pullback context and required rebuilding from scratch.

---

## Wider CT Target (Item 4 — Gated OFF)

Added `WB_CT_WIDER_TARGET=0` (default OFF) and `WB_CT_TARGET_R=3.0`. When enabled, CT trades use 3R target instead of SQ's 2R. Not tested yet — base CT must validate at YTD level first.

---

## Next Steps

1. **Full YTD A/B** — Run `run_backtest_v2.py --ab-ct` across all 59 days with IBKR ticks
2. **SHPH validation** — SHPH went $2.75→$25 on Jan 20. Does CT capture part of that? (Need to verify tick data)
3. **Enable for live** — If YTD shows positive delta, set `WB_CT_ENABLED=1` in .env
4. **Wider target test** — After base validates, try `WB_CT_WIDER_TARGET=1` on EEIQ/SHPH to see if 3R captures more

---

## Env Vars (Current State)

```bash
WB_CT_ENABLED=0                    # OFF — awaiting YTD validation
WB_CT_CASCADE_LOCKOUT_MIN=60       # 60 min after last SQ close (was 10)
WB_CT_MAX_SQ_TRADES=1              # CT only on single-SQ stocks (cascades blocked)
WB_CT_COOLDOWN_BARS=3              # 3-bar cooldown after lockout expires
WB_CT_MAX_REENTRIES=2              # Max 2 CT trades per symbol
WB_CT_MIN_VOL_DECAY=1.50           # Pullback vol < 1.5x squeeze avg
WB_CT_REQUIRE_VWAP=1               # Soft gate
WB_CT_REQUIRE_EMA=1                # Soft gate
WB_CT_REQUIRE_MACD=1               # Hard gate
WB_CT_MAX_RETRACE_PCT=50           # Hard gate
WB_CT_MAX_PULLBACK_BARS=5          # Hard gate
WB_CT_WIDER_TARGET=0               # OFF — not yet tested
WB_CT_TARGET_R=3.0                 # Available when wider target enabled
```

---

## The Bottom Line

CT V2 is the first iteration that passes all regression tests at exactly $0 delta while adding measurable value (+$413 on EEIQ). The cascade gate + 60-minute lockout combination ensures CT never touches cascade stocks (where SQ is optimal) and only activates on single-squeeze stocks where the continuation move is genuinely uncaptured.

Ready for YTD validation.
