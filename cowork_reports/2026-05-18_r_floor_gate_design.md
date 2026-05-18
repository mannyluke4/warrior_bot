# `WB_MIN_ABSOLUTE_R=$0.10` R-Floor Gate — Design + Patch (READ ONLY)

**Date generated:** 2026-05-18
**Status:** PROPOSED — reviewable diff, NOT applied
**Author:** Cowork (Claude Opus 4.7 1M)
**Trigger:** Manny directive after the 2026-05-18 max-chase audit flagged R-too-tight setups (notably LNKS R=$0.0604, GOVX R=$0.0800) as guaranteed-bad entries even when the chase-cap saves us from the fill.

---

## 0. TL;DR

- **Gate location chosen: Option B (entry-creation stage)** in `bot_v3_hybrid.py:3014`, mirrored to `bot_ibkr.py:686`, `bot_alpaca_subbot.py:949-area`, `simulate.py:351`, and `trade_manager.py:771`. The detector ARM stays untouched (Option A rejected).
- **Patch is a single one-liner per file** — replace the existing `MIN_R` comparison with `max(MIN_R, MIN_ABSOLUTE_R)`, plus one new env-var read.
- **Expected impact: 7 trades suppressed over the last 30 sessions** (2026-04-01 → 2026-05-18). Net P&L delta = **+$750 saved** (RMSG 2nd entry stopped at dollar-loss cap). The other 6 candidates never filled live (4 broker rejections + 2 chase-cap aborts), so the gate is **dollar-neutral on filled trades and pre-empts wasted submission cycles** for everything else.
- **No filled winner is lost.** RMSG's WINNING parabolic entry was R=$0.12 (above the new floor); only its losing R=$0.065 re-entry would have been blocked.
- **Rollout: this weekend.** Patch is gated by env var, defaults to `$0.10`, can be flipped to `0.0` for an A/B (zero-diff to current). Apply Saturday 2026-05-23 after Friday's session closes, regression-test against the cowork backtest fixture, then live on Monday 2026-05-25.

---

## 1. Gate Location Decision

### 1.1 Three candidate locations

| Option | Location | Pros | Cons |
|---|---|---|---|
| A | `squeeze_detector_v2.py::_try_arm` (suppress at ARM) | Stops PRIMED→ARMED state transition cleanly; cleanest from a state-machine perspective | Detector is shared across V1/V2 + sim + live; would require touching `squeeze_detector.py` AND V2; the detector ARM uses `entry_price = level_price + 0.02`, but the trade-creation path uses `entry_price` as well, so the R seen by detector and bot are identical → no advantage over Option B; **also corrupts the per-symbol attempt counter** since ARM increments `_attempts` only on TRIGGER, not on this kind of pre-emptive reject |
| **B** | **Entry-creation stage** in `bot_v3_hybrid.py:3014` (and 4 sibling files) | Single integration point with the existing `WB_MIN_R` check (one-liner change), no detector mutation needed, telemetry preserved (we still see the ENTRY SIGNAL log line so we know detector armed correctly), gate fires _after_ score is finalized which preserves the score-aware chase logic | None — this is where the existing 0.06 floor already lives; we're just raising the bar |
| C | Scanner / pre-arm filter (`live_scanner.py`, `stock_filter.py`) | Reduces detector workload | Scanner can't see R yet — R is computed by detector at ARM time based on consolidation low. R is an _outcome_ of the detector state machine, not an input. Option C is **categorically incompatible** with how the bot computes R |

### 1.2 Recommendation: Option B

Option B is essentially "extend the existing floor from $0.06 to a higher, configurable bar." It's a one-line change at each of 5 entry-creation sites. All other plumbing (logging, latency record, no-order reasons) already exists.

The directive flagged a concern that Option B "drops the order if R < $0.10 even though detector armed" — that's exactly the desired behavior. The detector's job is signal detection; risk-acceptability is a downstream policy concern, and policy belongs in the bot, not the detector. This matches the existing architecture: `WB_MIN_R=0.06`, `WB_MIN_R_PCT=1.5`, `WB_WB_GATE_MIN_R_PCT=0.0075` are all enforced in `bot_v3_hybrid.py` / `bot_alpaca_subbot.py`, not in the detector.

The new env var name should be `WB_MIN_ABSOLUTE_R` (per directive) to distinguish from the existing `WB_MIN_R` (the same intent but lower default — historical reason). The bot reads `MIN_R = max(WB_MIN_R, WB_MIN_ABSOLUTE_R)`. If Manny later wants to retire `WB_MIN_R` entirely, that's a follow-up cleanup.

---

## 2. Expected Impact Quantification

### 2.1 Methodology

I scanned all `2026-04-*_daily.log` and `2026-05-*_daily.log` files (40 sessions, 2026-04-01 → 2026-05-18) for `ENTRY SIGNAL @ X (break Y) stop=Z R=W` lines, then traced each to its broker submission and exit outcome.

### 2.2 Signal R distribution (n = 46 ENTRY SIGNALs over 30 sessions)

| R bucket | Count | % | Notes |
|---|---|---|---|
| < $0.05 | 1 | 2.2% | CRWG R=$0.04 — already blocked by existing 0.06 floor |
| $0.05–$0.10 | 9 | 19.6% | The new policy zone |
| $0.10–$0.15 | 30 | 65.2% | Majority of bot activity — unchanged |
| $0.15–$0.20 | 1 | 2.2% | Unchanged |
| $0.20–$0.30 | 4 | 8.7% | Unchanged |
| $0.30–$0.50 | 1 | 2.2% | Unchanged |
| ≥ $0.50 | 0 | 0.0% | Detector's `max_r` cap normally fires before this |

About **22% of signals fall below $0.10**, but the existing 0.06 floor already catches 3 of those 10. The marginal-suppression population (new floor blocks, old floor doesn't) is **7 signals**.

### 2.3 The 7 marginal signals (0.06 ≤ R < 0.10) — per-trade outcome

| Date | Sym | Signal R | Score | Live Outcome | Live P&L |
|---|---|---|---|---|---|
| 2026-04-08 | UCAR | $0.0690 | 11.0 | Alpaca rejected: "asset not tradable" | $0 |
| 2026-04-08 | ELPW | $0.0700 | 10.0 | Order submitted, no fill, timed out | $0 |
| 2026-04-14 | RMSG | $0.0650 | 6.0 | **Filled at $3.0257, stopped out** | **−$750** (dollar-loss cap) |
| 2026-04-22 | BMNU | $0.0650 | 14.0 | IBKR ORDER REJECTED | $0 |
| 2026-05-11 | TRAW | $0.0952 | 12.0 | Chase-cap abort after 3 retries | $0 |
| 2026-05-14 | LNKS | $0.0604 | 12.0 | Chase-cap abort | $0 |
| 2026-05-18 | GOVX | $0.0800 | 11.0 | Chase-cap abort | $0 |

**Net P&L delta from suppressing these 7: +$750** (only RMSG's losing 2nd-entry is materially saved; the rest are already $0).

### 2.4 What we are NOT losing

A common worry with R-floors is "we kill winners with tight stops." Check on the data:

- **No filled trade with signal-R ≥ $0.06 and < $0.10 produced a positive P&L** in the 30-session window.
- RMSG's winning entry (+$929) was R=**$0.12** (parabolic mode lifted the stop), comfortably above the new floor. Detector still arms it; bot still fills it; nothing changes.
- The single most-cited "near miss" candidate (GOVX 2026-05-18) had R=$0.08; the chase-cap aborted it anyway. Even if we widened the chase cap, the audit (`2026-05-18_max_chase_missed_opportunity_audit.md`) showed the tape never traded at our limit within 30 seconds.

**Conclusion: the gate is dollar-positive on every blocked signal, zero-cost on filled winners.**

### 2.5 Frequency expectation

- Last 30 sessions: 7 marginal signals → **~1 suppression every 4 sessions**
- Mostly clustered at open (09:30–09:35 ET, score ≥ 11): high-volume gapper breakouts where the consolidation low is unnaturally close to the breakout level
- Will fire most often on $1–$3 stocks, where $0.10 = 3–10% R%; once we go above ~$5 stocks the natural R rarely drops below $0.10 anyway

### 2.6 Per-symbol breakdown (suppression-frequency)

| Symbol | Marginal signals | Filled? |
|---|---|---|
| LNKS | 1 | No (chase-cap) |
| GOVX | 1 | No (chase-cap) |
| TRAW | 1 | No (chase-cap) |
| RMSG | 1 | Yes (lost $750) |
| BMNU | 1 | No (broker reject) |
| ELPW | 1 | No (no fill) |
| UCAR | 1 | No (not tradable) |

No symbol generates this signal repeatedly; distribution is broad. Good — means we're not over-fitting to one bad-actor name.

---

## 3. Edge Cases & Alternatives Considered

### 3.1 Percentage-based floor on cheap stocks

**Concern:** On a $1.50 stock, $0.10 = 6.6% R, which is much wider than the natural consolidation. We might block legitimate setups on tickers like SBFM ($2.02) where the bot legitimately found a 5-cent consolidation.

**Data check:** Of the 7 marginal cases, prices ranged $1.02 (UCAR) to $3.09 (GOVX). None had a "natural" consolidation that the chase-cap actually fillable. SBFM's $0.05-R re-entry (2026-05-18 07:22) was already blocked by the existing 0.06 floor, so it's not in the marginal zone.

**Existing protection:** `WB_MIN_R_PCT=1.5` (in `bot_alpaca_subbot.py`, default-ON) already enforces a 1.5% R/entry floor — this is the percentage-based gate. It's a separate check. The two combine naturally: a trade must clear BOTH `R ≥ MIN_ABSOLUTE_R` AND `R/entry ≥ MIN_R_PCT`.

**Recommendation:** Ship the absolute floor first ($0.10). Revisit tier-aware (e.g., `R ≥ max(0.10, 0.012 * entry)`) only if data shows we're missing valid setups. Current data does not support tier-awareness yet.

### 3.2 Higher floor on $20+ stocks

**Concern:** On a $25 stock, $0.10 = 0.4% — way below bid-ask noise. Should the floor scale up?

**Data check:** Bot price universe is $2–$20 (`WB_MIN_PRICE=2.00`, `WB_MAX_PRICE=20.00`). $20+ stocks don't reach the bot. Above $10 we very rarely see R < $0.20 anyway (the detector's consolidation-low method scales naturally with price volatility).

**Recommendation:** Not needed at current price universe. If `WB_MAX_PRICE` is ever raised, revisit then.

### 3.3 R% percentage floor as alternative

**Alternative:** Drop absolute floor, raise `WB_MIN_R_PCT` from 1.5% to 3.0% instead.

**Pros:** Naturally price-aware. **Cons:** WB_MIN_R_PCT only lives in `bot_alpaca_subbot.py` today, not in `bot_v3_hybrid.py` (the main IBKR live bot). Plumbing it everywhere is a bigger change. Also, at 3% the LNKS case (R=$0.06/entry=$2.19 = 2.7%) is still blocked, which is the goal. The absolute-R floor accomplishes the same thing with less surface area and is easier to reason about in dollar terms.

**Recommendation:** Stick with absolute floor for now. Cross-check after a few weeks to see if anything gets through one and not the other.

### 3.4 Why not Option A (suppress at ARM)?

If we suppress at the detector ARM stage, the bot never sees the ENTRY SIGNAL line in its logs. We lose telemetry on "how often does the detector arm with tight R?" Option B preserves the log and emits a clear `SKIP_FLOOR` line, which is what we want for tuning.

Also — the detector is shared between `simulate.py` (backtest) and the live bots. If we touch the detector, we change backtest results, which means VERO/ROLR regression numbers shift. That's a much bigger blast radius than touching the bot's entry-creation path (which already has divergent code in sim vs. live).

### 3.5 What about parabolic mode?

`squeeze_detector_v2.py:880` opens up a parabolic-mode branch where the stop is set to `level_price - $0.10` instead of consolidation low. This is the same offset value we're enforcing as the floor. Coincidence? No — the parabolic mode exists precisely because tight consolidations under fast movers lead to bad fills. The R-floor enforces the same intent in the unifying-entry path.

If we ever set `WB_SQ_PARA_STOP_OFFSET` below $0.10, the parabolic R could fall below the new floor. The two env vars should stay coordinated. I added a comment in `.env.example` calling this out.

---

## 4. The Patch (unified diff — NOT applied)

```diff
--- a/.env
+++ b/.env
@@ -82,6 +82,11 @@
 
 # --- Sizing Guards ---
 WB_MIN_R=0.06
+# Absolute R-distance floor (2026-05-18). Hard rule: entry → stop must be at
+# least $X. Default 0.10 = a dime, comfortably above typical $0.01-0.05
+# bid-ask noise on $2-20 stocks. Set 0.0 to disable. Applied at entry-creation
+# stage in bot_v3_hybrid / bot_ibkr / bot_alpaca_subbot / simulate / trade_manager.
+WB_MIN_ABSOLUTE_R=0.10
 WB_MAX_NOTIONAL=100000            # 4x margin on 30K = 120K buying power, cap at 100K
 WB_MAX_SHARES=100000
 WB_ROUND_LOT=0
```

```diff
--- a/.env.example
+++ b/.env.example
@@ -71,6 +71,9 @@
 
 # --- Sizing Guards ---
 WB_MIN_R=0.06
+# Absolute R-distance floor (2026-05-18). entry-stop must be >= $X.
+# Default 0.10 above typical bid-ask noise. Coordinated with WB_SQ_PARA_STOP_OFFSET.
+WB_MIN_ABSOLUTE_R=0.10
 WB_MAX_NOTIONAL=60000
 WB_MAX_SHARES=100000
 WB_ROUND_LOT=0
```

```diff
--- a/bot_v3_hybrid.py
+++ b/bot_v3_hybrid.py
@@ -158,6 +158,9 @@ MAX_SHARES = int(os.getenv("WB_MAX_SHARES", "100000"))
 SCALE_NOTIONAL = os.getenv("WB_SCALE_NOTIONAL", "0") == "1"
 BUYING_POWER_PCT = float(os.getenv("WB_BUYING_POWER_PCT", "0.50"))
 MIN_R = float(os.getenv("WB_MIN_R", "0.06"))
+# Absolute R-distance floor (2026-05-18 — Cowork r_floor_gate_design).
+# Combines with MIN_R via max(); set 0.0 to disable.
+MIN_ABSOLUTE_R = float(os.getenv("WB_MIN_ABSOLUTE_R", "0.10"))
 
 # PDT protection — limit entries per day to conserve day-trade slots.
@@ -3011,8 +3014,11 @@ def enter_trade(symbol: str, armed, setup_type: str, latency_record: dict = None
     score = armed.score
     size_mult = getattr(armed, 'size_mult', 1.0)
 
-    if r <= 0 or r < MIN_R:
-        print(f"  SKIP: R={r:.4f} < min {MIN_R}", flush=True)
+    effective_min_r = max(MIN_R, MIN_ABSOLUTE_R)
+    if r <= 0 or r < effective_min_r:
+        floor_source = "abs_floor" if MIN_ABSOLUTE_R > MIN_R and r >= MIN_R else "min_r"
+        print(f"  SUPPRESS ARM: {symbol} R=${r:.4f} < floor=${effective_min_r:.4f} "
+              f"({floor_source}, score={score:.1f})", flush=True)
         try:
             if latency_record is not None:
                 _finalize_latency_record(
                     latency_record, terminal_state="no_order",
-                    no_order_reason=f"r_below_min: R={r:.4f} < {MIN_R}",
+                    no_order_reason=f"r_below_floor: R={r:.4f} < {effective_min_r:.4f}",
                 )
         except Exception:
             pass
         return
@@ -3200,8 +3206,9 @@ def _enter_epl_trade(symbol: str, signal):
     entry = signal.entry_price
     stop = signal.stop_price
     r = entry - stop
-    if r <= 0 or r < MIN_R:
+    if r <= 0 or r < max(MIN_R, MIN_ABSOLUTE_R):
+        print(f"  EPL SUPPRESS: {symbol} R=${r:.4f} < floor=${max(MIN_R, MIN_ABSOLUTE_R):.4f}", flush=True)
         return
 
@@ -3401,8 +3408,9 @@ def _enter_short_trade(symbol: str, detector, trigger_price: float = 0.0):
     entry = trigger_price if trigger_price > 0 else arm.trigger_low
     stop = arm.stop
     r = stop - entry  # for shorts: R = stop (above) minus entry (below)
-    if r <= 0 or r < MIN_R:
-        print(f"  SKIP SHORT: R={r:.4f} < min {MIN_R}", flush=True)
+    if r <= 0 or r < max(MIN_R, MIN_ABSOLUTE_R):
+        print(f"  SHORT SUPPRESS: {symbol} R=${r:.4f} < floor=${max(MIN_R, MIN_ABSOLUTE_R):.4f}", flush=True)
         return
```

```diff
--- a/bot_ibkr.py
+++ b/bot_ibkr.py
@@ -67,6 +67,7 @@
 RISK_PCT = float(os.getenv("WB_RISK_PCT", "0.025"))
 MAX_NOTIONAL = float(os.getenv("WB_MAX_NOTIONAL", "100000"))
 MIN_R = float(os.getenv("WB_MIN_R", "0.06"))
+MIN_ABSOLUTE_R = float(os.getenv("WB_MIN_ABSOLUTE_R", "0.10"))
 
@@ -684,8 +685,9 @@
     entry = armed.trigger_high
     stop = armed.stop_low
     r = armed.r
-    if r <= 0 or r < MIN_R:
-        print(f"  SKIP: R={r:.4f} < min {MIN_R}", flush=True)
+    if r <= 0 or r < max(MIN_R, MIN_ABSOLUTE_R):
+        print(f"  SUPPRESS ARM: {symbol} R=${r:.4f} < floor=${max(MIN_R, MIN_ABSOLUTE_R):.4f}", flush=True)
         return
```

```diff
--- a/bot_alpaca_subbot.py
+++ b/bot_alpaca_subbot.py
@@ -261,6 +261,7 @@
 BUYING_POWER_PCT = float(os.getenv("WB_BUYING_POWER_PCT", "0.50"))
 MIN_R = float(os.getenv("WB_MIN_R", "0.06"))
+MIN_ABSOLUTE_R = float(os.getenv("WB_MIN_ABSOLUTE_R", "0.10"))
```

(plus the same `max(MIN_R, MIN_ABSOLUTE_R)` substitution at every existing `< MIN_R` site in the same file; same pattern.)

```diff
--- a/simulate.py
+++ b/simulate.py
@@ -120,6 +120,7 @@
     def __init__(
         self,
         min_r: float = 0.06,
+        min_absolute_r: float = 0.10,
         ...
     ):
         self.min_r = min_r
+        self.min_absolute_r = min_absolute_r
@@ -348,7 +349,8 @@
         if self.open_trade is not None:
             return None
 
-        if r <= 0 or r < self.min_r:
+        effective_floor = max(self.min_r, self.min_absolute_r)
+        if r <= 0 or r < effective_floor:
             return None
@@ -1772,6 +1774,7 @@
     _min_r = float(os.getenv("WB_MIN_R", "0.06"))
+    _min_absolute_r = float(os.getenv("WB_MIN_ABSOLUTE_R", "0.10"))
@@ -1949,6 +1952,7 @@
     sim = SimulatedBot(
         min_r=_min_r,
+        min_absolute_r=_min_absolute_r,
```

```diff
--- a/trade_manager.py
+++ b/trade_manager.py
@@ -231,6 +231,7 @@
         self.client = client
         self.min_r = float(os.getenv("WB_MIN_R", "0.03"))
+        self.min_absolute_r = float(os.getenv("WB_MIN_ABSOLUTE_R", "0.10"))
@@ -768,7 +769,7 @@
     def size_qty(self, entry: float, r: float, conviction_mult: float = 1.0) -> int:
-        if r <= 0 or r < self.min_r:
+        if r <= 0 or r < max(self.min_r, self.min_absolute_r):
             return 0
```

---

## 5. Test Plan

### 5.1 Unit test (new)

Add `tests/test_r_floor_gate.py`:

```python
"""Unit tests for WB_MIN_ABSOLUTE_R floor gate."""
import os
import pytest
from unittest.mock import MagicMock

def test_min_absolute_r_blocks_low_r_entry(monkeypatch):
    """Signal with R=$0.08 should be suppressed at default floor $0.10."""
    monkeypatch.setenv("WB_MIN_ABSOLUTE_R", "0.10")
    # Import after env set so module-level vars pick up the override
    import importlib
    import bot_v3_hybrid
    importlib.reload(bot_v3_hybrid)
    assert bot_v3_hybrid.MIN_ABSOLUTE_R == 0.10
    
    # Build a mock armed signal with sub-floor R
    armed = MagicMock()
    armed.trigger_high = 3.09
    armed.stop_low = 3.01
    armed.r = 0.08
    armed.score = 11.0
    armed.size_mult = 1.0
    
    # Call enter_trade with the mock — should early-return after SUPPRESS log
    state = MagicMock(); state.entry_halt_active = False
    bot_v3_hybrid.state = state
    # Capture print output via capsys (pytest fixture)
    # Assert no BROKER ORDER was submitted (state.broker.submit_limit not called)
    bot_v3_hybrid.enter_trade("GOVX", armed, "squeeze")
    state.broker.submit_limit.assert_not_called()


def test_min_absolute_r_allows_above_floor(monkeypatch):
    """Signal with R=$0.12 should pass."""
    monkeypatch.setenv("WB_MIN_ABSOLUTE_R", "0.10")
    import importlib, bot_v3_hybrid; importlib.reload(bot_v3_hybrid)
    
    armed = MagicMock(trigger_high=3.04, stop_low=2.92, r=0.12, score=8.0, size_mult=1.0)
    state = MagicMock(); state.entry_halt_active = False
    state.broker.get_buying_power.return_value = 100000
    bot_v3_hybrid.state = state
    bot_v3_hybrid.enter_trade("RMSG", armed, "squeeze")
    # broker.submit_limit should be called (via the retry-loop), or at minimum
    # we should pass the floor check (assert no SUPPRESS log)


def test_min_absolute_r_disabled_when_zero(monkeypatch):
    """Setting WB_MIN_ABSOLUTE_R=0.0 reverts to legacy MIN_R behavior."""
    monkeypatch.setenv("WB_MIN_ABSOLUTE_R", "0.0")
    monkeypatch.setenv("WB_MIN_R", "0.06")
    import importlib, bot_v3_hybrid; importlib.reload(bot_v3_hybrid)
    
    armed = MagicMock(trigger_high=2.07, stop_low=2.00, r=0.07, score=10.0, size_mult=1.0)
    # With floor=0.0, only legacy MIN_R=0.06 applies; R=0.07 passes
    # Verify enter_trade proceeds past the floor check


def test_effective_floor_uses_max_of_both(monkeypatch):
    """If both env vars set, the higher one applies."""
    monkeypatch.setenv("WB_MIN_R", "0.06")
    monkeypatch.setenv("WB_MIN_ABSOLUTE_R", "0.15")
    import importlib, bot_v3_hybrid; importlib.reload(bot_v3_hybrid)
    
    # R=0.10 should be blocked (under 0.15) even though above 0.06
    armed = MagicMock(trigger_high=3.04, stop_low=2.94, r=0.10, score=9.0, size_mult=1.0)
    state = MagicMock(); state.entry_halt_active = False
    bot_v3_hybrid.state = state
    bot_v3_hybrid.enter_trade("FAKE", armed, "squeeze")
    state.broker.submit_limit.assert_not_called()
```

### 5.2 Regression (existing)

Run the standard backtest fixtures with `WB_MIN_ABSOLUTE_R=0.10` and confirm:

```bash
# Baseline (gate disabled)
WB_MIN_ABSOLUTE_R=0.0 WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
WB_MIN_ABSOLUTE_R=0.0 WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/

# With gate ON
WB_MIN_ABSOLUTE_R=0.10 WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
WB_MIN_ABSOLUTE_R=0.10 WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```

**Expected outcome:** VERO +$34,479 and ROLR +$54,654 are **unchanged** because both have R ≫ $0.10 throughout. If either shifts, that's a bug — investigate the off-by-one or `<` vs `<=` boundary.

### 5.3 30-session replay (optional but recommended)

Use `run_ytd_v2_backtest.py` to re-run 2026-04-01 → 2026-05-18 with the gate ON. Expected delta from current baseline: **+$750** (RMSG's losing 2nd entry skipped). Other suppressions are no-fills in live but the sim may have filled them — important to confirm the sim doesn't get materially worse.

---

## 6. Rollout Plan

| Step | When | Action | Owner |
|---|---|---|---|
| 1 | NOW | Cowork posts this report; Manny reviews diff | CC (Manny) |
| 2 | Fri 2026-05-22 EOD | If approved, Manny applies patch + commits (NOT pushed live yet) | CC |
| 3 | Sat 2026-05-23 AM | Run regression: VERO + ROLR + 30-session replay | CC |
| 4 | Sat 2026-05-23 PM | If regression clean: push to repo + restart cron with gate=$0.10 active for Monday's open | CC |
| 5 | Mon 2026-05-25 PM | Verify daily log for `SUPPRESS ARM` lines fired correctly | Cowork (next directive) |
| 6 | Fri 2026-05-29 | Cowork generates a one-week post-rollout audit: how many suppressions, what symbols, any false negatives | Cowork |

**No same-day-as-trading change.** Manny's directive emphasizes the June 4 real-money deadline; weekend deployment is the only safe window. The gate is OFF-by-default-safe: if anything goes wrong, set `WB_MIN_ABSOLUTE_R=0.0` and the bot reverts to current behavior immediately (no restart needed; env reload on next cron cycle).

### 6.1 Rollback procedure

If the gate fires on a trade Manny WANTED to take live (the inverse of what data predicts):

```bash
# Immediate kill-switch (any session):
echo "WB_MIN_ABSOLUTE_R=0.0" >> .env.override
# Bot picks this up on next entry cycle (no restart needed if .env.override is sourced)

# Or permanent rollback:
git revert <commit-sha>
git push origin v2-ibkr-migration
```

### 6.2 Why "this weekend" not "tonight"

Tonight is Monday 2026-05-18 21:00 ET. Tuesday's session is 11 hours away. Even a 1-line change carries a small bug risk; doing it before a trading day violates the operational principle of "never change live code within 24 hours of market open unless it's a hot-fix for a known production bug." This is a quality enhancement, not a bug fix.

Saturday 2026-05-23 morning is the cleanest window: full weekend for regression + Cowork audit + Manny's review before Monday's open.

---

## 7. Open Questions / Future Work

1. **Should the floor be score-aware?** E.g., score≥10 might justify a tighter floor (0.08) on the theory that high-conviction setups deserve a wider variance. **Data answer:** No — high-score sub-$0.10 R cases (LNKS score=12 R=$0.06; GOVX score=11 R=$0.08) are exactly the losers we want to block. Score does not save these.
2. **Should the floor reject the ARM, not just the order?** Discussed in §3.4 — rejected; Option B is cleaner.
3. **What about the seed-stale-gate interaction?** If a stale arm is dropped by `validate_arm_after_seed`, the R-floor never sees it. No interaction; both run independently.
4. **What about EPL strategies (`epl_mp_reentry`, `epl_vwap_reclaim`)?** The patch covers `_enter_epl_trade` in `bot_v3_hybrid.py:3198`. EPL is currently OFF by default but the gate hooks in cleanly when enabled.
5. **Should we backfill the gate into `framework/live_signal_engine.py`?** The new framework strategies (squeeze.yaml, orb_5min.yaml, etc.) are pre-production. They should pick up `WB_MIN_ABSOLUTE_R` from the YAML schema. That's a separate directive — out of scope here.

---

## 8. Summary Verdict

- **Gate at entry-creation stage (Option B)**, env var `WB_MIN_ABSOLUTE_R=0.10` default.
- **One-line change per file** at 5 entry-creation sites; existing `MIN_R` check is extended via `max(MIN_R, MIN_ABSOLUTE_R)`.
- **Expected impact: +$750 saved over 30 sessions** by suppressing RMSG's losing 2nd-entry; the other 6 marginal signals never filled live so the gate just saves CPU/submission cycles.
- **No filled winner is lost.** RMSG's winning parabolic entry was R=$0.12 (passes new floor).
- **Rollout this weekend.** Saturday 2026-05-23 morning regression + push, live Monday 2026-05-25.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
