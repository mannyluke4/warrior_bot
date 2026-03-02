# L2 PHASE 2.5 DIRECTIVE — Three Targeted Fixes
**Date**: March 2, 2026  
**From**: Research Team (Perplexity)  
**To**: Claude Code  
**Priority**: HIGH — Apply these fixes, then re-run pilot + regressions to validate  

---

## CONTEXT

Phase 2 pilot test (10 stocks) revealed L2 is three features fighting each other:

| L2 Mechanism | Net Impact (Pilot) | Verdict |
|-------------|-------------------|---------|
| L2 exit signals (`l2_bearish_exit`) | **+$1,490** | KEEP — best L2 feature |
| L2 hard gate (mid-session, 30+ min) | **+$1,422** | KEEP — correctly blocks exhausted re-entries |
| L2 hard gate (session open, <30 min) | **-$1,107** (pilot) / **-$7,714** (GWAV regression) | FIX — blocks profitable gap runners |
| L2 stop tightening (bid stack → stop) | **-$1,381** | DISABLE — false floors on volatile small-caps |
| L2 score adjustments (±imbalance, spread) | ~neutral | KEEP — reasonable modifiers |
| L2 entry strategy (l2_entry.py) | $0 | SHELVE — zero unique setups detected |

Current L2 net effect: **-$43** (neutral — good and bad cancel out).  
Projected net effect after fixes: **+$2,912** improvement over baseline.

---

## FIX 1: L2 Hard Gate Warmup (`WB_L2_HARD_GATE_WARMUP_BARS`)

### Problem
The `NO_ARM L2_bearish` hard gate fires immediately on raw imbalance numbers. On gap stocks at open, the order book is flooded with limit sellers (profit-takers), creating sustained bearish imbalance (0.06–0.28) even while price moves up. This blocked +$1,107 in profitable FSLY trades and destroyed the GWAV regression (-$7,714).

### Root Cause
L2 has no context for what "normal" looks like for a specific stock. A 0.22 imbalance on GWAV at 07:01 looks bearish in absolute terms, but it's actually the natural state of a 30%+ gap stock at open — sellers are market-making against the premium.

### Fix
Add **per-symbol warmup** for the hard gate. L2 signals start computing from bar 1 (scores, exits, acceleration all active immediately), but the hard gate (`_l2_is_bearish()` → `NO_ARM`) stays disabled until the detector has processed N bars of L2 data for that symbol.

**New env variable:**
```bash
WB_L2_HARD_GATE_WARMUP_BARS=30    # Bars of L2 data before hard gate activates per symbol (default: 30)
```

**Implementation in `micro_pullback.py`:**

Track per-symbol L2 bar count:
```python
# In MicroPullbackDetector.__init__():
self._l2_bar_counts = {}  # {symbol: int} — bars of L2 data processed

# In on_bar_close_1m() where l2_state is received:
if l2_state is not None:
    sym = bar["symbol"]  # or however the symbol is accessed
    self._l2_bar_counts[sym] = self._l2_bar_counts.get(sym, 0) + 1
```

Modify the hard gate check (in both `_direct_entry_check()` and `_pullback_entry_check()`):
```python
# BEFORE (current):
if self.l2_hard_gate and self._l2_is_bearish(l2_state):
    return f"1M NO_ARM L2_bearish imbalance={imb:.2f}"

# AFTER (with warmup):
l2_warmup_bars = int(os.getenv("WB_L2_HARD_GATE_WARMUP_BARS", "30"))
l2_bars_seen = self._l2_bar_counts.get(symbol, 0)
if self.l2_hard_gate and l2_bars_seen >= l2_warmup_bars and self._l2_is_bearish(l2_state):
    return f"1M NO_ARM L2_bearish imbalance={imb:.2f} (bar {l2_bars_seen})"
```

**What stays active during warmup (bar 1 onward):**
- ✅ L2 score adjustments in `_score_setup()` (bearish book = -3 penalty, bullish = +4.5 bonus)
- ✅ L2 exit signals via `check_l2_exit()` (l2_bearish_exit, l2_ask_wall)
- ✅ L2 acceleration (impulse/confirmation waiver when bullish strength ≥ 3)
- ✅ L2 pullback reset (bearish during pullback → reset state machine)

**What is disabled during warmup:**
- ❌ Hard gate veto (`NO_ARM L2_bearish`) — the only thing held back

**Log line**: When the hard gate WOULD have fired but warmup prevents it:
```python
if self.l2_hard_gate and self._l2_is_bearish(l2_state) and l2_bars_seen < l2_warmup_bars:
    logger.info(f"1M L2_bearish_warmup imbalance={imb:.2f} bar={l2_bars_seen}/{l2_warmup_bars} (gate inactive)")
```

Also add the new variable to `.env.example`:
```bash
# WB_L2_HARD_GATE_WARMUP_BARS=30  # Bars of L2 data per symbol before hard gate activates (0=immediate)
```

---

## FIX 2: Disable L2 Stop Tightening via Bid Stacking

### Problem
When L2 detects bid stacking near current price, the stop is moved to the highest stacked bid level. This creates tighter stops → smaller R → larger position sizes → compounding losses when the "floor" breaks.

Pilot evidence:
- **CRSR T2**: Stop $6.17 → $6.32 (bid stack), R shrunk to $0.09, position 9,360 shares. Brief dip = -$842 vs -$193 baseline.
- **QMCO T1**: Stop $7.70 → $8.05 (bid stack), bigger loss on stop hit (-$1,000 vs -$143).
- **Net**: -$1,381 across the pilot.

### Root Cause
Bid stacking on volatile small-caps is ephemeral. Market makers and algorithms place and pull stacked orders rapidly. The "support" L2 detects can evaporate in seconds, but the stop is already set.

### Fix — Option A (Recommended): Widen-Only Rule

Change the bid-stack stop logic so it can only **move the stop further from entry** (wider/safer), never **closer to entry** (tighter/riskier):

**In both `_direct_entry_check()` and `_pullback_entry_check()`:**

```python
# BEFORE (current — can tighten or widen):
if l2_state is not None and l2_state.get("bid_stack_levels"):
    stack_prices = [p for p, _ in l2_state["bid_stack_levels"]]
    if stack_prices:
        highest_stack = max(stack_prices)
        if highest_stack > raw_stop and highest_stack < entry:
            raw_stop = highest_stack

# AFTER (widen-only — stack can only provide BETTER support, not tighter):
# DISABLED: L2 bid-stack stop tightening removed per Phase 2.5 directive.
# Bid stacking on volatile small-caps creates false floors that compound losses.
# If re-enabling, consider widen-only: only allow if highest_stack < raw_stop
# (i.e., stack provides support BELOW the price-action stop, confirming it).
```

For now, simply **comment out** the bid-stack stop adjustment block entirely. Add a log line so we can still see the data:

```python
if l2_state is not None and l2_state.get("bid_stack_levels"):
    stack_prices = [p for p, _ in l2_state["bid_stack_levels"]]
    if stack_prices:
        highest_stack = max(stack_prices)
        logger.info(f"L2 bid_stack at {highest_stack:.4f} (stop={raw_stop:.4f}, entry={entry:.4f}) [NO ADJUSTMENT — disabled]")
```

Also do the same in `l2_entry.py._find_stop()` if it has the same pattern.

### Fix — Option B (Alternative): Env-Gated

If you prefer to keep it toggleable:
```bash
WB_L2_STOP_TIGHTEN_ENABLED=0   # Allow L2 bid stacking to tighten stops (0=off, 1=on)
```
Default to `0` (off). This way we can re-enable it later if we find conditions where it works.

**Go with Option B** — add the env var, default to `0`, so we can toggle it back on if the full study reveals conditions where it helps.

Add to `.env.example`:
```bash
# WB_L2_STOP_TIGHTEN_ENABLED=0   # Allow L2 bid stacking to adjust stops (0=disabled, 1=enabled). Disabled by default — bid stacking on volatile small-caps creates false floors.
```

---

## FIX 3: No Changes to l2_entry.py (Shelved)

The standalone L2 entry strategy found zero unique setups across all 10 pilot stocks. The micro_pullback detector always gets there first. **No code changes needed** — it's already behind the `--l2-entry` flag and doesn't fire unless explicitly invoked.

No action required. Just noting it for the record.

---

## VALIDATION PLAN

After implementing Fix 1 and Fix 2, run the following in order:

### Step 1: Regression Check (no L2)
```bash
python simulate.py VERO 2026-01-16 --ticks     # Expected: +$6,890
python simulate.py GWAV 2026-01-16 --ticks     # Expected: +$6,735
python simulate.py ANPA 2026-01-09 --ticks     # Expected: +$2,088
```
These must be **unchanged** — Fix 1 and Fix 2 only affect behavior when `--l2` is passed.

### Step 2: Regression Check (with L2)
```bash
python simulate.py VERO 2026-01-16 --ticks --l2     # Expected: +$6,890 (same as without L2)
python simulate.py GWAV 2026-01-16 --ticks --l2     # Expected: FIXED — should be close to +$6,735 now
python simulate.py ANPA 2026-01-09 --ticks --l2     # Expected: +$5,091 or better (was improved by L2)
```
**GWAV is the critical test.** The 07:01 entry should no longer be blocked (within warmup window). If GWAV with `--l2` returns close to +$6,735, the warmup fix is working.

### Step 3: Re-run 10 Pilot Stocks (with L2 + fixes)
Re-run all 10 pilot stocks with `--l2` and the new config:
```bash
WB_L2_HARD_GATE_WARMUP_BARS=30
WB_L2_STOP_TIGHTEN_ENABLED=0
```

Record results in the same format as `L2_PILOT_RESULTS.md`. Create `L2_PILOT_RESULTS_V2.md`.

**Expected improvements:**
- FSLY: Should recover some/all of the -$1,188 loss (early entries no longer blocked)
- CRSR: Should recover some/all of the -$1,115 loss (no stop tightening)
- QMCO: Should improve (no stop tightening on T1)
- NCI, BDSX, MCRB: Should be unchanged or slightly better (exit signals unaffected)

### Step 4: Compare
Create a comparison table:

```markdown
| Symbol | No L2 | L2 v1 (current) | L2 v2 (with fixes) | v2 Delta vs No-L2 |
|--------|-------|-----------------|--------------------|--------------------|
| NCI    | +$577 | +$1,012         | ???                | ???                |
...
```

---

## DELIVERABLES

| Item | Priority |
|------|----------|
| `WB_L2_HARD_GATE_WARMUP_BARS` implementation + .env.example | Must |
| `WB_L2_STOP_TIGHTEN_ENABLED` implementation + .env.example | Must |
| Warmup log line (gate inactive during warmup) | Must |
| Bid-stack log line (no adjustment, disabled) | Should |
| Regression check without L2 (3 stocks, unchanged) | Must |
| Regression check with L2 (3 stocks, GWAV must pass) | Must |
| `L2_PILOT_RESULTS_V2.md` — 10-stock re-run with fixes | Must |
| Comparison table (no-L2 vs L2-v1 vs L2-v2) | Must |

---

## IMPORTANT NOTES

- **Signal mode cascading exits must NOT be suppressed** — this is the bot's core edge. These L2 fixes work WITH signal exits.
- **Do NOT modify `l2_signals.py`** — the signal detection logic is fine. We're only changing how `micro_pullback.py` consumes the signals.
- **Do NOT modify `check_l2_exit()`** — L2 exit signals are the best-performing feature. Leave them exactly as-is.
- **Do NOT touch l2_entry.py** — it's shelved, not removed.
- After these fixes validate, the next step is scaling to the full 93+ stock study with L2 enabled.

---

*Directive authored by Research Team — March 2, 2026*  
*Reference: L2_PILOT_RESULTS.md, L2_INFRASTRUCTURE_AUDIT.md*
