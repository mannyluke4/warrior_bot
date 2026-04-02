# Squeeze V2 — Master Plan & Build Spec

**Date:** April 1, 2026
**Status:** APPROVED — Decisions are final. Build to spec.
**Sources:** Perplexity Ross Candle Audit, Perplexity Decision Report, L2 Full Study (March 2), April 1 morning log, V1 megatest results

---

## CRITICAL RULE: V2 Is a Separate Module

**`squeeze_detector.py` IS NOT TOUCHED.** Period.

V2 lives in a new file: `squeeze_detector_v2.py`. Completely independent module — own state machine, own entry logic, own exit logic. V1's file stays frozen.

The bot switches between them with a single env var:
```
WB_SQUEEZE_VERSION=1    # 1 = squeeze_detector.py (current, proven)
WB_SQUEEZE_VERSION=2    # 2 = squeeze_detector_v2.py (new build)
```

In `bot_ibkr.py` and `simulate.py`, the wiring is:
```python
if os.getenv("WB_SQUEEZE_VERSION", "1") == "2":
    from squeeze_detector_v2 import SqueezeDetectorV2 as SqueezeDetector
else:
    from squeeze_detector import SqueezeDetector
```

That's the only change to existing files — an import switch. If V2 fails, flip back to 1. Zero risk to V1.

**Why this matters:** V1 is proven at +$19,832 across 49 days. We haven't seen it live yet. We cannot risk breaking the one strategy that works in backtesting.

---

## Philosophy

V1 is mechanical: volume explosion → level break → trailing stop. It captures breakouts but is blind to what the candles are saying. Ross reads candles like a language — shapes tell him buyer/seller psychology in real time, before bars close.

V2 adds candle intelligence to both entries and exits. Level 2 / tape reading is deferred to Phase 2 — prove the free candle improvements first before spending Databento API budget on L2 data.

---

## Part 1: V2 Entry Logic

V2's state machine: IDLE → PRIMED → ARMED → TRIGGERED (same concept as V1, with additional intelligence at each transition).

### 1A: Candle-Over-Candle — HARD GATE

**Decision: REQUIRED. No COC = no PRIMED. Period.**

**What Ross does:** "Candle over candle" (current bar breaks high of prior bar) is his primary BUY signal. Volume without breakout structure is churning.

**What V1 does:** Checks volume + green + body + VWAP + HOD, but does NOT check whether the current bar breaks the prior bar's high.

**V2 implementation:** Before IDLE → PRIMED, verify:
```python
bar.high > prior_bar.high
```
If not, block transition and log:
```
SQ_REJECT: no_candle_over_candle (bar_high=$X.XX <= prior_high=$Y.YY)
```

This is NOT a score modifier. NOT optional via env var in initial build. Hard requirement.

Start strict — if backtest shows COC blocks too many winners, we can loosen it later with a separate decision.

### 1B: Doji/Exhaustion Gate Before ARM

**What Ross does:** If he sees a doji or shooting star at the top of a move, he does NOT buy the next candle. Momentum is fading.

**What V1 does:** No exhaustion check. A volume bar followed by a doji still ARMs if a level breaks.

**V2 implementation:** If the bar immediately preceding the ARM bar is `is_doji()` or `is_shooting_star()`, delay ARM by 1 bar — require fresh momentum confirmation. If the NEXT bar is also bearish, reset to IDLE.

### 1C: Intra-Bar ARM — OPTION A ONLY

**Decision: Option A. Intra-bar level break only. Do NOT implement Option B.**

**What Ross does:** Enters the MOMENT price breaks a level — doesn't wait for bar close. 30-60 seconds faster.

**What V1 does:** Level break detection waits for bar close in `on_bar_close_1m()`. 1-minute structural delay.

**V2 implementation:**
- PRIMED transition still happens on bar close (V1's proven volume explosion logic, unchanged)
- Once PRIMED, `on_trade_price()` watches for level breaks on every tick
- When a tick breaks the level while PRIMED → ARM immediately
- Saves ~30s on the ARM step

What NOT to do:
- Do NOT move volume explosion detection to intra-bar
- Do NOT track cumulative mid-bar volume
- Do NOT change how PRIMED fires — it still requires a completed 1m bar

```python
def on_trade_price(self, price, is_premarket=False):
    # If PRIMED, check for level break on every tick (NEW in V2)
    if self._state == "PRIMED":
        level_name, level_price = self._find_broken_level(price)
        if level_name is not None:
            self._try_arm(level_name, level_price, price)

    # If ARMED, check trigger (same as V1)
    if self._state == "ARMED" and self.armed:
        if price >= self.armed.trigger_high:
            self._state = "IDLE"
            return f"SQ ENTRY SIGNAL @ ${price:.2f}"

    return None
```

### 1D: Trend/Chop Filter

**What Ross does:** Only trades at "strong trends at potential pivots." Ignores sideways/choppy action.

**What V1 does:** Has a stale stock filter but no explicit trend/chop detection.

**V2 implementation:** Over the last N bars (e.g., 5), check for higher highs and higher lows. If range-bound, skip PRIMED. Could use ATR compression or consecutive higher-high count.

**Status:** OFF initially (`WB_SQV2_TREND_REQUIRED=0`). Test separately after core features are validated.

---

## Part 2: V2 Exit Logic

**Decision: All V2 exit logic lives INSIDE `squeeze_detector_v2.py`.** V2 is self-contained. Do NOT put V2 exits in trade_manager.py. Do NOT modify V1's exit paths.

V2 exits build on V1's mechanical stops and add candle intelligence.

### Architecture

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

Bot/sim wiring:
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

### 2A: Intra-Bar Candle Shape Reading

**What Ross does:** Watches the CURRENT (incomplete) candle. Long upper wick developing = sellers rejecting. Exits immediately.

**What V1 does:** Only processes completed bars. Blind to forming candle shape.

**V2 implementation:** Track forming bar shape on every tick:
- `forming_upper_wick = current_high - max(current_open, last_price)`
- `wick_to_body_ratio = forming_upper_wick / max(forming_body, 0.01)`
- If ratio > 2.0 AND in trade AND price > 1R from entry → tighten trailing stop (don't auto-exit, protect profit)

**Status:** OFF initially (`WB_SQV2_INTRABAR_SHAPE=0`). Test separately.

### 2B: Candle-Under-Candle Exit

**What Ross does:** "Candle under candle" is his primary SELL signal.

**V2 implementation:** After bar close, if `bar.low < prior_bar.low` AND in trade → fire exit. Apply only post-target-hit to preserve runner management.

**Status:** OFF initially (`WB_SQV2_CUC_EXIT=0`). Test separately. (CUC had mixed results in Ross Exit V3 study — re-evaluate in V2 context.)

### 2C: Candle Pattern Exits (Topping Wicky, Bearish Engulfing)

Native to V2 from the start. Topping wicky on 10s bars, bearish engulfing on 10s/1m bars, with grace periods and profit gates built in.

**Status:** ON by default (`WB_SQV2_CANDLE_EXITS=1`).

---

## Part 3: Level 2 / Tape Reading — DEFERRED TO PHASE 2

**Decision: Do NOT build L2 features in the initial V2 build.**

The candle improvements (1A, 1B, 1C, 2A, 2B, 2C) can be tested on existing tick data with zero additional cost. L2 requires fetching Databento MBP-10 data (real money, real API calls). Prove the free improvements first.

Leave env var declarations in `__init__` as placeholders with `# DEFERRED — Phase 2` comments. Do NOT write L2 logic, do NOT import l2_signals.py, do NOT fetch L2 data.

```bash
WB_SQV2_L2_EXIT=0        # DEFERRED — Phase 2
WB_SQV2_L2_CONFIRM=0     # DEFERRED — Phase 2
WB_SQV2_L2_MIN_FLOAT_M=5 # Placeholder only
```

### What exists for Phase 2 (when we're ready):
- `archive/scripts/l2_signals.py` — L2SignalDetector (277 lines): imbalance, bid stacking, large orders, ask thinning
- `archive/scripts/l2_entry.py` — L2EntryDetector (360 lines): enters when book shows buyers accumulating
- `databento_feed.py` — Fetches MBP-10 from Databento, caches as `.dbn.zst`
- `trade_manager.py` — Already handles `l2_bearish` and `l2_ask_wall` signals
- March 2 study: L2 is net positive with float ≥5M gate (+$6,526 across 135 stocks)
- Gap: study ran against MP trades, NOT squeeze. Needs re-evaluation.

### L2 for CYCN-type gradual movers: DEFERRED beyond V2
Different strategy entirely. Defer to V3 or separate module.

---

## Part 4: Build Order (Do These In Sequence)

### Step 1: Create `squeeze_detector_v2.py`
- Copy V1's interface (same method signatures)
- Implement IDLE → PRIMED → ARMED → TRIGGERED state machine
- Add COC hard gate (1A) at IDLE → PRIMED
- Add doji/exhaustion gate (1B) at PRIMED → ARMED
- Add intra-bar level break in `on_trade_price` while PRIMED (1C, Option A)
- Keep V1's volume explosion, VWAP, HOD, and level break logic as foundation

### Step 2: Implement V2 Exits Inside the Module
- Start with V1's mechanical exits (dollar cap, hard stop, trail, 2R target, runner)
- Add topping wicky detection on 10s bars
- Add bearish engulfing detection on 10s bars
- Add candle-under-candle on 1m bars (post-target only)
- Add intra-bar wick shape tracking (tighten trail, don't auto-exit)
- All with grace periods and profit gates

### Step 3: Wire Into simulate.py
- Add the import switch (`WB_SQUEEZE_VERSION` = 1 vs 2)
- V2 uses same interface — minimal wiring changes
- Verify V1 still works when VERSION=1

### Step 4: Wire Into bot_ibkr.py
- Same import switch
- V2's `check_exit()` replaces mechanical exit calls when VERSION=2

### Step 5: Run Individual Feature Tests
Test each feature one at a time against V1 baseline. Record in `cowork_reports/sq_v2_feature_tests.md`. Do NOT combine features until individual results are reviewed.

### Step 6: Report Results
Push to `cowork_reports/2026-04-XX_sq_v2_results.md`. Include per-feature P&L delta, combined winner P&L, full 49-day comparison. STOP and wait for review before combining or deploying.

---

## Part 5: Backtest Plan

### Phase 1: Build V2 Module (Steps 1-4 above)

### Phase 2: Test Each Feature Independently
Run 49-day megatest with `WB_SQUEEZE_VERSION=2`, each feature enabled one at a time:

| Test | Feature Enabled | Others | Compare Against |
|------|----------------|--------|----------------|
| A | COC hard gate (1A) | OFF | V1 (+$19,832) |
| B | Doji/exhaustion gate (1B) | OFF | V1 |
| C | Intra-bar ARM (1C) | OFF | V1 |
| D | Candle pattern exits (2C) | OFF | V1 |
| E | Candle-under-candle exit (2B) | OFF | V1 |
| F | Intra-bar shape exits (2A) | OFF | V1 |
| G | Trend filter (1D) | OFF | V1 |

Each test reports: total P&L delta, win rate delta, per-stock breakdown.

### Phase 3: Combine Winners
Enable all individually-positive features together. Watch for butterfly effects. Combined result must beat V1.

### Phase 4: Stress Test
Run V2 candidate on full 137-stock dataset, new March-April tick data, edge cases.

### Phase 5: L2 Phase 2 (if candle features prove out)
Only then fetch MBP-10 data and test L2 exits/confirmations on top of validated V2.

### Phase 6: Live Deployment
1. `WB_SQUEEZE_VERSION=2` in .env
2. Paper trade 1 week
3. Compare live vs V1
4. Positive → V2 primary. Negative → flip back to 1.

---

## Architecture

```
bot_ibkr.py / simulate.py
    │
    ├── if WB_SQUEEZE_VERSION=1 → squeeze_detector.py     (UNTOUCHED, frozen)
    │
    └── if WB_SQUEEZE_VERSION=2 → squeeze_detector_v2.py  (new build)
                                      │
                                      ├── Entry: V1 core + COC hard gate
                                      │          + exhaustion gate + intra-bar ARM
                                      │          + trend filter (optional)
                                      │
                                      ├── Exit via check_exit():
                                      │   V1 mechanical stops
                                      │   + candle patterns (TW, BE)
                                      │   + candle-under-candle (optional)
                                      │   + intra-bar shape (optional)
                                      │
                                      └── Same interface as V1:
                                          .on_bar_close_1m(bar, vwap)
                                          .on_trade_price(price)
                                          .seed_bar_close(o, h, l, c, v)
                                          .check_exit(price, bar, vwap)  ← NEW
                                          .reset()
                                          .armed → ArmedTrade or None
```

---

## Env Vars (Final)

```bash
# Master switch
WB_SQUEEZE_VERSION=1              # 1 = V1 (default), 2 = V2

# V2 Entry (ON by default in V2)
WB_SQV2_COC_REQUIRED=1           # Candle-over-candle hard gate
WB_SQV2_EXHAUSTION_GATE=1        # Doji/shooting star blocks ARM
WB_SQV2_INTRABAR_ARM=1           # ARM on intra-bar level break (Option A)
WB_SQV2_TREND_REQUIRED=0         # Trend filter — OFF initially, test separately

# V2 Exit (candle exits ON, experimental OFF)
WB_SQV2_CANDLE_EXITS=1           # Topping wicky + bearish engulfing
WB_SQV2_CUC_EXIT=0               # Candle-under-candle — OFF initially
WB_SQV2_INTRABAR_SHAPE=0         # Forming-bar wick — OFF initially

# V2 Level 2 (ALL DEFERRED — Phase 2)
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

**Regression: Portfolio total only.** Per-stock differences are expected and acceptable. The COC gate and exhaustion filter will skip some V1 trades — that's the point. Only red flag: a single trade losing >$5,000 that V1 didn't have.

---

## What NOT to Do

- Do NOT modify `squeeze_detector.py` (V1). Not one line.
- Do NOT modify `trade_manager.py` for V2 exits.
- Do NOT implement L2 features (deferred to Phase 2).
- Do NOT implement Option B intra-bar volume detection.
- Do NOT make COC a score modifier — it's a hard gate.
- Do NOT combine features before individual test results are reviewed.
- Do NOT invent new features not listed here.
- Do NOT skip the individual feature testing phase.
- Do NOT "optimize" by changing multiple things at once.

---

## What's NOT in V2

- **L2 standalone entries (CYCN-type):** Separate strategy. Defer to V3.
- **Scaling in/out:** Orthogonal. Separate initiative.
- **Post-halt re-entry:** Infrastructure problem, not detector logic.
- **ML-based candle reading:** Research phase. Maybe V4.

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-01 | V2 is a NEW FILE, not modifications to V1 | V1 proven, can't risk breaking it |
| 2026-04-01 | Single env var switch V1 ↔ V2 | Zero-risk rollback |
| 2026-04-01 | Same interface as V1 | Drop-in replacement |
| 2026-04-01 | COC is a hard gate, not scored | Ross's primary signal. Start strict, loosen if needed. |
| 2026-04-01 | Intra-bar ARM = Option A only | Simpler. Don't move volume detection to intra-bar. |
| 2026-04-01 | All V2 exits inside the module | Self-contained. Don't spread across trade_manager. |
| 2026-04-01 | Regression = portfolio total, not per-stock | COC gate will change per-stock P&L. Total is what matters. |
| 2026-04-01 | L2 deferred to Phase 2 | Prove free candle improvements first. L2 costs API budget. |
| 2026-04-01 | CYCN-type entries deferred beyond V2 | Different strategy, not a squeeze mod |
| 2026-04-01 | V1 baseline (+$19,832) is the bar | Everything must beat this or it doesn't ship |

---

*Approved: April 1, 2026*
*Sources: AUDIT_ROSS_CANDLE_VS_V2.md (Perplexity), SQUEEZE_V2_DECISIONS.md (Perplexity), L2_FULL_STUDY_RESULTS.md, V1 megatest*
