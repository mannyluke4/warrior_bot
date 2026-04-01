# Squeeze V2 — Decision Report & Build Instructions

**Date:** April 1, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Status:** APPROVED — These decisions are FINAL. Do not deviate.

---

## Context

CC: You are building `squeeze_detector_v2.py` based on `SQUEEZE_V2_PLAN.md`. This document answers the 5 open questions from that plan and provides explicit build instructions. **Follow these exactly. Do not invent alternative approaches, do not "improve" on these decisions, and do not skip steps because you think you know a better way.** If something is unclear, stop and ask — do not guess.

---

## Answers to the 5 Open Questions

### Q1: Intra-Bar ARM — Option A (Simpler)

**Decision: Option A. Intra-bar level break only. Do NOT implement Option B.**

How it works:
- PRIMED transition still happens on bar close (V1's proven volume explosion logic, unchanged)
- Once PRIMED, the tick stream (`on_trade_price`) watches for level breaks in real time
- When a tick breaks the level while PRIMED → transition to ARMED immediately
- This saves ~30 seconds on the ARM step compared to V1 (which waits for the next bar close to detect the level break)

What NOT to do:
- Do NOT move volume explosion detection to intra-bar
- Do NOT track cumulative mid-bar volume
- Do NOT change how PRIMED fires — it still requires a completed 1-minute bar with volume confirmation

Code sketch:
```python
def on_trade_price(self, price, is_premarket=False):
    # If PRIMED, check for level break on every tick (NEW in V2)
    if self._state == "PRIMED":
        level_name, level_price = self._find_broken_level(price)  # price, not bar.high
        if level_name is not None:
            self._try_arm(level_name, level_price, price)
            # If ARM succeeded, fall through to trigger check
    
    # If ARMED, check trigger (same as V1)
    if self._state == "ARMED" and self.armed:
        if price >= self.armed.trigger_high:
            self._state = "IDLE"
            return f"SQ ENTRY SIGNAL @ ${price:.2f}"
    
    return None
```

### Q2: Candle-Over-Candle — REQUIRED (Hard Gate)

**Decision: Hard gate. No COC = no PRIMED. Period.**

Before transitioning from IDLE to PRIMED, V2 must verify:
```python
bar.high > prior_bar.high
```

If the current bar has a volume explosion but does NOT break the prior bar's high, the transition is blocked. Log the rejection:
```
SQ_REJECT: no_candle_over_candle (bar_high=$X.XX <= prior_high=$Y.YY)
```

Do NOT implement this as a score modifier. Do NOT make it optional via env var in the initial build. It is a hard requirement for PRIMED.

Rationale: This is Ross Cameron's primary buy signal. Volume without breakout structure is churning. Start strict — if backtest data shows COC blocks too many winners, we can loosen it to scored later with a separate decision.

### Q3: L2 Integration — DEFERRED

**Decision: Do NOT build L2 features in the initial V2. Set all L2 env vars to 0 (OFF).**

```
WB_SQV2_L2_EXIT=0      # OFF — do not implement
WB_SQV2_L2_CONFIRM=0   # OFF — do not implement
```

The candle improvements (1A, 1B, 1C, 2A, 2B) can be tested on existing tick data with zero additional cost. L2 requires fetching Databento MBP-10 data (real money, real time). Prove the free improvements first.

What to do: Leave the env var declarations in `__init__` as placeholders with `# DEFERRED — Phase 2` comments. Do NOT write any L2 logic, do NOT import l2_signals.py, do NOT fetch any L2 data.

### Q4: V2 Exit Handler — Inside the Module

**Decision: All V2 exit logic lives inside `squeeze_detector_v2.py`.**

V2 is a self-contained module. The exit decision-making uses V2's internal state (forming candle shape, exhaustion tracking, bar history) and should not be spread across trade_manager.py.

Architecture:
```python
class SqueezeDetectorV2:
    def check_exit(self, price, bar=None, vwap=None) -> Optional[str]:
        """Called on every tick and on bar close. Returns exit reason or None.
        
        The bot/sim hooks into this and calls exit_trade() when a reason is returned.
        V2 makes the decision. The bot executes it.
        """
        # Dollar loss cap (same as V1)
        # Hard stop (same as V1)
        # Intra-bar wick shape warning (NEW — tighten trail, don't auto-exit)
        # Topping wicky on 10s bar close (NEW)
        # Bearish engulfing on 10s bar close (NEW)
        # Candle-under-candle on 1m bar close (NEW)
        # Trailing stop (same as V1 but adjusted by candle signals)
        # 2R target core exit (same as V1)
        # Runner trail (same as V1)
        return None
```

The bot/sim wiring is:
```python
# In the tick handler:
if state.open_position and sq_det_v2:
    exit_reason = sq_det_v2.check_exit(price)
    if exit_reason:
        exit_trade(symbol, price, qty, exit_reason)

# On 10s bar close:
if state.open_position and sq_det_v2:
    exit_reason = sq_det_v2.check_exit(price=bar.close, bar=bar)
    if exit_reason:
        exit_trade(symbol, bar.close, qty, exit_reason)
```

Do NOT put V2 exit logic in trade_manager.py. Do NOT modify V1's exit paths.

### Q5: Regression Targets — Portfolio Total Only

**Decision: V2 is measured against V1's portfolio total (+$19,832 across 49 days). Per-stock matching is NOT required.**

Run the full 49-day backtest. Compare:
- Total P&L (must be > $19,832)
- Total win rate (should be ≥ V1's rate)
- Total trade count (fewer trades at higher win rate is good)
- Max single-trade loss (no catastrophic blow-ups worse than V1's worst)

Per-stock differences are EXPECTED and ACCEPTABLE. The COC gate and exhaustion filter will skip some trades V1 took — that's the point. If VERO specifically does worse but the portfolio does better, that's a pass.

The only per-stock red flag: a single trade losing more than $5,000 that V1 didn't have. That gets investigated individually.

---

## Build Order (Do These In Sequence)

### Step 1: Create `squeeze_detector_v2.py`
- Copy V1's interface (same method signatures)
- Implement the IDLE → PRIMED → ARMED → TRIGGERED state machine
- Add COC hard gate (Q2) at the IDLE → PRIMED transition
- Add doji/exhaustion gate (Plan item 1B) at the PRIMED → ARMED transition
- Add intra-bar level break in `on_trade_price` while PRIMED (Q1)
- Keep V1's volume explosion, VWAP, HOD, and level break logic as the foundation

### Step 2: Implement V2 Exits Inside the Module
- Start with V1's mechanical exits (dollar cap, hard stop, trail, 2R target, runner)
- Add topping wicky detection on 10s bars
- Add bearish engulfing detection on 10s bars
- Add candle-under-candle on 1m bars (post-target only)
- Add intra-bar wick shape tracking (tighten trail, don't auto-exit)
- All with grace periods and profit gates matching the values CC just ported to bot_ibkr.py

### Step 3: Wire Into simulate.py
- Add the import switch (`WB_SQUEEZE_VERSION=1` vs `2`)
- V2 uses same interface — minimal wiring changes
- Verify V1 still works when `WB_SQUEEZE_VERSION=1`

### Step 4: Wire Into bot_ibkr.py
- Same import switch
- V2's `check_exit()` replaces the mechanical exit calls when version=2

### Step 5: Run Individual Feature Tests (Plan Phase 2)
- Test each feature one at a time against V1 baseline
- Record results in `backtest_status/sq_v2_feature_tests.md`
- Do NOT combine features until individual results are reviewed

### Step 6: Report Results
- Push results to `cowork_reports/2026-04-XX_sq_v2_results.md`
- Include: per-feature P&L delta, combined winner P&L, full 49-day comparison
- STOP and wait for review before combining features or deploying

---

## What NOT to Do

- Do NOT modify `squeeze_detector.py` (V1). Not one line.
- Do NOT modify `trade_manager.py` for V2 exits.
- Do NOT implement L2 features (deferred).
- Do NOT implement Option B intra-bar volume detection.
- Do NOT make COC a score modifier — it's a hard gate.
- Do NOT combine features before individual test results are reviewed.
- Do NOT invent new features not listed in SQUEEZE_V2_PLAN.md.
- Do NOT skip the individual feature testing phase.
- Do NOT "optimize" by changing multiple things at once.

---

## Env Vars (Final)

```bash
# Master switch
WB_SQUEEZE_VERSION=1              # 1 = V1 (default), 2 = V2

# V2 Entry (all ON by default in V2)
WB_SQV2_COC_REQUIRED=1           # Candle-over-candle hard gate
WB_SQV2_EXHAUSTION_GATE=1        # Doji/shooting star blocks ARM
WB_SQV2_INTRABAR_ARM=1           # ARM on intra-bar level break (Option A)
WB_SQV2_TREND_REQUIRED=0         # Trend filter — OFF initially, test separately

# V2 Exit (candle exits ON, experimental OFF)
WB_SQV2_CANDLE_EXITS=1           # Topping wicky + bearish engulfing
WB_SQV2_CUC_EXIT=0               # Candle-under-candle — OFF initially, test separately
WB_SQV2_INTRABAR_SHAPE=0         # Forming-bar wick — OFF initially, test separately

# V2 Level 2 (ALL OFF — DEFERRED)
WB_SQV2_L2_EXIT=0                # DEFERRED
WB_SQV2_L2_CONFIRM=0             # DEFERRED
WB_SQV2_L2_MIN_FLOAT_M=5         # Placeholder only
```

---

## Success Criteria

| Metric | V1 Baseline | V2 Must Beat |
|--------|-------------|-------------|
| 49-day P&L | +$19,832 | > +$19,832 |
| Win rate | ~64% | ≥ 64% |
| Max single loss | -$500 | ≤ -$500 |
| Trade count | 25 | No minimum (fewer at higher WR is fine) |
| V1 unchanged when VERSION=1 | Yes | Yes — regression test required |

---

*Decisions are FINAL. Build to spec. Test in sequence. Report results before combining or deploying.*
