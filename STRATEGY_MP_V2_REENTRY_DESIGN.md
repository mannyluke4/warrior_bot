# Strategy: MP V2 — Post-Squeeze Re-Entry
## Design Doc — Cowork Session 2026-03-27

---

## Executive Summary

Redesign MP from a standalone entry strategy into a **post-squeeze re-entry module**. MP only activates on stocks where the squeeze detector has already confirmed the stock is a legitimate mover. This eliminates MP's core failure mode (entering pre-squeeze chop) while preserving its pullback detection mechanics for catching the second, third, and fourth legs of big runners.

**Data justification:** MP standalone lost $8,066 over 15 months (24% WR, 138 trades). The 34 max_loss_hit trades (0% WR, -$19,122) are almost entirely entries during pre-squeeze noise. Meanwhile, MP's big winners (AIFF +$5,602, LSE +$4,602, ROLR +$3,293) were all stocks that squeezed — MP happened to catch the move but with worse timing than SQ would have.

**Ross parallel:** On EEIQ, Ross's first entry was a breakout scalp (= our squeeze). Every subsequent entry was a dip-buy, pattern recognition, or continuation trade on a stock he'd already confirmed was in play. That's exactly what this redesign enables.

---

## Design Decisions

### Decision 1: Unlock Condition

**When does MP activate on a symbol?**

MP stays dormant (IDLE, not processing bars for entry signals) until ONE of these conditions is met:

| Unlock Trigger | Rationale |
|---------------|-----------|
| SQ trade closed (any outcome) | Stock confirmed in play. Even a losing SQ trade means the stock showed squeeze characteristics. |
| SQ armed + triggered but no fill | Stock showed the pattern, just missed on execution. Still in play. |

**What we're NOT doing:**
- MP does NOT unlock on SQ PRIMED alone (too early — many primes don't arm)
- MP does NOT unlock based on time or bar count (no "after 30 minutes, try MP")
- MP does NOT fire on stocks where SQ never engaged at all

**Implementation:** Add a per-symbol `_sq_confirmed: bool` flag to MP. Set it `True` when the squeeze detector's `notify_trade_closed()` fires for that symbol. MP's `on_bar_close_1m()` short-circuits with `return None` when `_sq_confirmed` is `False`.

### Decision 2: Cooldown After Squeeze Exit

**How long after the squeeze exits does MP wait?**

Immediate re-entry after a squeeze exit is dangerous — the stock may be dumping. MP should wait for the pullback to stabilize.

**Proposal:** MP activates N bars after the squeeze trade closes. During those N bars, MP is in "observation mode" — updating EMA/MACD/patterns but not looking for setups.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `WB_MP_REENTRY_COOLDOWN_BARS` | 3 | 3 minutes gives the stock time to find a level. Too long = miss the move. Too short = enter the dump. |

The cooldown begins when `_sq_confirmed` flips to True. After N bars of `on_bar_close_1m()`, MP transitions to active detection.

### Decision 3: Entry Mechanics — Keep or Modify?

**The existing MP entry logic is mostly sound for re-entries.** The impulse→pullback→confirm cycle is exactly what a post-squeeze dip-buy looks like:

- **Impulse** = the squeeze move itself (already happened, confirmed by SQ)
- **Pullback** = stock pulls back 1-3 bars after the squeeze (this is the dip Ross buys)
- **Confirm** = green recovery candle with hammer/engulfing body (Ross's "reclaim" candle)

**What needs to change:**

| Current Behavior | Problem | Fix |
|-----------------|---------|-----|
| Impulse detection requires 3 consecutive green bars | Post-squeeze, the impulse already happened. Don't require it again. | Skip impulse detection when `_sq_confirmed`. Start directly in "looking for pullback" mode. |
| MACD hard gate resets structure on bearish cross | After a squeeze, MACD may go bearish during the pullback. That's normal — it's the dip we want to buy. | Relax MACD gate for post-squeeze entries. Use MACD as a warning, not a hard reset. |
| Stop = pullback low - pad | Correct for re-entry. The pullback low after a squeeze is a natural support level. | Keep as-is. |
| Exhaustion filter blocks entries far from VWAP | Post-squeeze stocks ARE far from VWAP. Dynamic scaling already handles this for SQ. | Apply same dynamic scaling to MP post-squeeze entries (already partially implemented). |

### Decision 4: Stop Placement & Risk

Post-squeeze re-entries should have **wider stops** than original MP. The stock has already proven it can move — a tight stop gets whipsawed by normal retracement volatility.

**Proposal:**
| Parameter | Current MP | MP V2 (Post-Squeeze) | Rationale |
|-----------|-----------|----------------------|-----------|
| Stop | Pullback low - $0.01 | Pullback low - ATR(14) * 0.5 | ATR-aware stop accounts for post-squeeze volatility |
| Min R | $0.03 | $0.06 | Slightly wider to avoid noise, but still tight |
| Max R | None | $0.80 (same as SQ) | Cap risk per trade |
| Size | 100% of risk allocation | 50% initially (probe), 100% on confirmation add | Scaling in — start small, add on strength |

### Decision 5: Exit Mechanics

Post-squeeze re-entries should use **the same mechanical exit system as SQ** (V1 exits), not the current MP 10-second bar exits (bearish_engulfing, topping_wicky). The V1 SQ exits are proven: dollar loss cap → hard stop → tiered max_loss → pre-target trail → 2R target → runner trail.

**Rationale:** The MP-specific exits (bearish_engulfing_exit_full, topping_wicky_exit_full) are responsible for many small wins that cap upside. On a confirmed squeeze stock, we want to let the move run with wider trails, just like SQ does.

**Implementation:** Tag re-entry trades as `setup_type="mp_reentry"` and route them through the squeeze exit logic in trade_manager, not the MP 10s exit logic.

### Decision 6: Multiple Re-Entries

**Allow up to N re-entries per symbol per session.**

Ross made 5+ entries on EEIQ. The bot should be able to re-enter a confirmed stock multiple times as long as the pattern keeps setting up.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `WB_MP_MAX_REENTRIES` | 3 | Cap at 3 to limit damage on fading stocks. Each re-entry requires a fresh pullback→confirm cycle. |
| Re-entry after loss | Allowed (1 time) | If first re-entry fails, allow one more attempt. Stock may have found a new level. |
| Re-entry after win | Always allowed (up to max) | Winner confirms the stock is still running. |

### Decision 7: Key Level Awareness (Enhancement)

**New for MP V2:** Re-entries should prefer entries near key levels, not just any pullback.

The existing `level_map` in MP already tracks resistance/support. For post-squeeze re-entries, add a **preference score** (not a hard gate) for entries near:
- Prior squeeze entry level (now support)
- Whole dollar levels
- VWAP (if stock pulls back to VWAP and bounces)
- Prior consolidation zone

This is a scoring bonus, not a requirement. Some great re-entries happen at levels that aren't obvious (like Ross's $7.20 entry on the inverted H&S).

---

## State Machine: MP V2

```
DORMANT ──[sq_confirmed]──► COOLDOWN ──[N bars]──► ACTIVE
                                                      │
                                              ┌───────┴───────┐
                                              ▼               ▼
                                         PULLBACK ──► ARMED ──► TRIGGERED
                                              │                    │
                                              ▼                    ▼
                                           RESET            enter_trade()
                                              │                    │
                                              ▼                    ▼
                                         ACTIVE              [exit via SQ V1 exits]
                                         (look for                 │
                                          next setup)              ▼
                                                            notify_mp_trade_closed()
                                                                   │
                                                    ┌──────────────┴──────────┐
                                                    ▼                         ▼
                                              ACTIVE (if < max)         DORMANT (if max reached)
```

Key differences from current MP:
1. Starts in DORMANT (not IDLE/looking)
2. Requires external unlock signal from SQ
3. Cooldown period before first detection attempt
4. Skips impulse detection (squeeze was the impulse)
5. Exits via SQ V1 mechanical system, not MP 10s bars
6. Multiple re-entries allowed up to cap

---

## Env Vars (All Gated, OFF by Default)

```bash
# === MP V2: Post-Squeeze Re-Entry ===
WB_MP_V2_ENABLED=0              # Master gate (OFF by default, independent of WB_MP_ENABLED)
WB_MP_REENTRY_COOLDOWN_BARS=3   # Bars to wait after squeeze exit before looking
WB_MP_MAX_REENTRIES=3           # Max re-entry attempts per symbol per session
WB_MP_REENTRY_MIN_R=0.06        # Minimum R for re-entry (wider than standalone MP)
WB_MP_REENTRY_STOP_ATR_MULT=0.5 # Stop = pullback_low - (ATR * this mult)
WB_MP_REENTRY_PROBE_SIZE=0.5    # First re-entry at 50% size
WB_MP_REENTRY_USE_SQ_EXITS=1    # Route through SQ V1 exit system (not MP 10s exits)
WB_MP_REENTRY_MACD_GATE=0       # MACD hard gate OFF for re-entries (0 = off, 1 = on)
WB_MP_REENTRY_LEVEL_BONUS=1     # Score bonus for entries near key levels
```

---

## What We're NOT Changing

1. **Standalone MP (`WB_MP_ENABLED`)** — stays OFF. It's a separate gate. Can still be turned on for testing but not recommended for live.
2. **SQ detector** — no changes. It already has `notify_trade_closed()` and `_has_winner`. MP V2 consumes these signals.
3. **SQ V1 exits** — no changes. MP V2 re-entries route through the same exit logic.
4. **MP detector internals** — the impulse/pullback/confirm state machine stays. We just add a DORMANT gate at the top and skip the impulse requirement when post-squeeze.

---

## Testing Plan

### Phase 1: Validate on Known Winners (Regression)
Run MP V2 on stocks where we know the squeeze fired and the stock continued:
- **VERO 2026-01-16**: SQ entry at ~$5, stock ran to $12.70. Does MP V2 catch re-entries on the pullbacks?
- **EEIQ 2026-03-26**: SQ entry at $8.94. Does MP V2 enter on the $7.20 dip (Ross's big trade)?
- **ROLR 2026-01-14**: Already has both SQ and MP trades. Does MP V2 improve timing?

### Phase 2: Full YTD Backtest (SQ + MP V2)
Run the 15-month IBKR dataset with SQ + MP V2 enabled:
- Compare: SQ-only P&L vs SQ+MP_V2 P&L
- Verify: MP V2 does not produce trades on days where SQ didn't fire (zero false activations)
- Check: max_loss_hit count should drop dramatically (ideally <5, from current 34)

### Phase 3: Live Observation
- Deploy with `WB_MP_V2_ENABLED=1` in paper trading
- Monitor for 1 week
- Key metric: does MP V2 add P&L or drag, compared to SQ-only?

---

## Expected Impact

| Scenario | Est. P&L Impact |
|----------|----------------|
| Current SQ-only (baseline) | $0 (reference) |
| SQ + MP V2 on EEIQ-type day | +$2,000–$5,000 additional (1-2 re-entries on pullbacks) |
| SQ + MP V2 on quiet day (no SQ fires) | $0 (MP V2 stays dormant — no damage) |
| SQ + MP V2 on fading stock | -$300–$600 max (1 failed re-entry, capped by SQ exits) |

The critical improvement: **on days where SQ doesn't fire, MP V2 does nothing.** This eliminates the -$2,499 type damage we saw on March 27 where standalone MP turned a quiet day into a loss.

---

## Files Referenced
- `cowork_reports/2026-03-27_mp_deep_dive.md` — CC's MP data analysis (138 trades, exit breakdown)
- `cowork_reports/2026-03-27_eeiq_ross_vs_bot_comparison.md` — Ross vs bot execution gap
- `squeeze_detector.py` — SQ state machine, `notify_trade_closed()` interface
- `micro_pullback.py` — MP state machine, `on_bar_close_1m()` entry logic
- `simulate.py` — SQ/MP routing, `setup_type` tagging
