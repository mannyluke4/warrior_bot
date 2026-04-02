# DIRECTIVE: CT V2 Tuning — Cascade Lockout, Soft Gates, Runner Capture

**Date:** 2026-03-30
**Author:** Cowork (Opus)
**For:** CC (Sonnet)
**Priority:** P1 — Squeeze is working, CT captures the next layer of profit
**Branch:** `v2-ibkr-migration`
**Prerequisite:** Infrastructure directive (Gateway + tick fix) is separate. CT is strategy work.

---

## Context

The squeeze strategy is proven: 39/39 on sq_target_hit, +$266K YTD, 82% win rate. Don't touch SQ.

The problem: on stocks that keep running after our 2R exit, we leave significant money on the table. Today's ASTC went $3.92→$6.48 — we exited at $4.14. SHPH on Jan 20 went $2.75→$25 — we exited at $2.75. EEIQ went $9.45→$12.70.

The SQ detector already SEES these continuations — it continues to PRIME and ARM at higher levels after we exit. It just can't act on them because of the `not_new_hod` gate. CT's job is to act on exactly those signals.

CT V1 (current implementation, commit 95cbcd9 through 6895999) validated the concept — EEIQ showed +$221 from 2 CT entries — but has two blocking issues:
1. Regression interference: VERO -$150, ROLR -$303 even with 0 CT trades
2. Overly harsh gate resets that discard valid pullbacks

See: `cowork_reports/2026-03-30_ct_deep_dive_analysis.md` for full forensic.

---

## What You're Changing (4 Items)

### Item 1: Cascade Lockout Timer (FIXES REGRESSION)

**Problem:** CT's deferred activation helps but doesn't eliminate regression. On VERO/ROLR, SQ bounces through IDLE between cascade legs. During those brief IDLE gaps, `check_pending_activation()` fires and CT starts counting cooldown bars — even though SQ is about to re-arm. The mere execution of CT's bar processing code during those gaps creates subtle sim differences.

**Fix:** Add a time-based lockout that prevents ALL CT processing for N minutes after the last SQ trade close. The lockout timer resets on every SQ trade close, so cascading stocks keep pushing it forward.

**Implementation in `continuation_detector.py`:**

```python
# New env var
self._cascade_lockout_min = float(os.getenv("WB_CT_CASCADE_LOCKOUT_MIN", "10"))
self._lockout_until: Optional[float] = None  # Unix timestamp

def notify_squeeze_closed(self, symbol, pnl, entry=0, exit_price=0, hod=0, avg_squeeze_vol=0):
    """Called when a squeeze trade closes. ALWAYS update lockout, even on losses."""
    if not self.enabled:
        return
    # ALWAYS reset the lockout timer — even losing SQ trades mean SQ is still active
    import time
    self._lockout_until = time.time() + (self._cascade_lockout_min * 60)

    if pnl <= 0:
        return  # Only stage activation on winning squeezes
    if self._reentry_count >= self._max_reentries:
        return

    self._pending_activation = { ... }  # existing code unchanged
```

**Implementation in `simulate.py` and `bot_ibkr.py` — the CT gate:**

```python
# Replace the existing CT gate:
#   _ct_sq_idle = (not sq_enabled) or (sq_det._state == "IDLE" and not sq_det._in_trade)
#   if ct_enabled and sim_mgr.open_trade is None and _ct_sq_idle:

# New gate:
import time
_ct_lockout_clear = (ct_det._lockout_until is None or time.time() > ct_det._lockout_until)
_ct_sq_idle = (not sq_enabled) or (sq_det._state == "IDLE" and not sq_det._in_trade)
if ct_enabled and sim_mgr.open_trade is None and _ct_sq_idle and _ct_lockout_clear:
    # CT processing allowed
```

**For simulate.py tick-mode time:** The sim uses bar timestamps, not `time.time()`. Use the bar's timestamp for comparison:

```python
# In the sim, convert bar time to epoch or just count minutes:
# Store lockout as "bar_time + lockout_minutes" instead of unix timestamp
self._lockout_until_bar_time: Optional[str] = None  # "HH:MM" format

def notify_squeeze_closed(self, ..., bar_time: str = ""):
    # Parse bar_time "HH:MM", add lockout minutes
    h, m = int(bar_time[:2]), int(bar_time[3:5])
    total_min = h * 60 + m + int(self._cascade_lockout_min)
    self._lockout_until_bar_time = f"{total_min // 60:02d}:{total_min % 60:02d}"
```

**Important:** During the lockout period, CT must do ZERO processing — no `on_bar_close_1m()`, no `check_pending_activation()`, no EMA/MACD updates. The CT object should be completely inert. Any code path that touches CT state should be gated.

**Env var:**
```
WB_CT_CASCADE_LOCKOUT_MIN=10    # Minutes after last SQ trade close before CT activates
```

**Default 10 minutes.** On VERO (cascades over ~8 min), this keeps CT locked for the entire cascade. On EEIQ (single SQ trade at 10:00, no cascade), CT unlocks at 10:10 and starts watching — which aligns with the actual CT entry at 11:02 from the regression retest.

---

### Item 2: Soft Gate Failures (FIXES EEIQ FALSE REJECTS)

**Problem:** When a pullback temporarily fails a gate (dips below VWAP, or pullback volume is slightly high), CT hard-resets to WATCHING and throws away the pullback bar context. The pullback has to rebuild from scratch. On EEIQ, the stock recovered above VWAP within 1-2 bars but CT had already discarded the pullback.

**Fix:** Introduce "soft" vs "hard" gate failures. Soft gates pause CT and re-check on the next bar without discarding pullback context. Hard gates truly disqualify the setup.

**In `continuation_detector.py`, modify `on_bar_close_1m()` in the CT_PRIMED state:**

```python
# Current: all gates call self._reset() which discards pullback bars
# New: only hard gates reset. Soft gates return a "PAUSE" message.

if self._state == "CT_PRIMED":
    # SOFT GATES — pause and re-check next bar, keep pullback context

    # Gate 1: Volume decay (soft — can recover)
    if self._squeeze_vol and self._squeeze_vol > 0 and self._pullback_bars:
        pb_avg_vol = sum(b["v"] for b in self._pullback_bars) / len(self._pullback_bars)
        vol_ratio = pb_avg_vol / self._squeeze_vol
        if vol_ratio > self._min_vol_decay:
            self._state = "WATCHING"  # Go back to WATCHING but KEEP pullback bars
            return f"CT_PAUSE: volume high ({vol_ratio:.1f}x), re-checking"

    # Gate 2: VWAP (soft — stock can reclaim on next bar)
    if self._require_vwap and vwap and bar.close < vwap:
        self._state = "WATCHING"  # Keep pullback bars
        return f"CT_PAUSE: below VWAP (${bar.close:.2f} < ${vwap:.2f}), re-checking"

    # Gate 3: EMA (soft — same logic)
    if self._require_ema and self.ema and bar.close < self.ema:
        self._state = "WATCHING"  # Keep pullback bars
        return f"CT_PAUSE: below EMA (${bar.close:.2f} < ${self.ema:.2f}), re-checking"

    # HARD GATES — these truly disqualify the setup

    # Gate 4: MACD negative (hard — dump signal)
    if self._require_macd and not self.macd_state.bullish():
        return self._reset("CT_REJECT: MACD negative — dump, not dip")

    # Retrace and pullback length are already checked in WATCHING state (hard resets)

    # All gates passed — ARM
    ...
```

**Key difference:** When a soft gate fails, CT goes back to WATCHING but does NOT clear `self._pullback_bars`, `self._pullback_low`, `self._pullback_high`. On the next green bar, CT re-enters CT_PRIMED and re-checks all gates with the full pullback context preserved.

**The `_reset()` method (hard reset) remains unchanged** — it clears everything and is only called for MACD negative, retrace > 50%, pullback > 5 bars.

---

### Item 3: Pass Bar Time to CT for Sim-Accurate Lockout

**Problem:** `continuation_detector.py` currently uses no time reference. The lockout timer needs to work in both live mode (wall clock) and sim mode (bar timestamps).

**Fix:** Pass the bar time string to `notify_squeeze_closed()` and `on_bar_close_1m()`.

```python
def notify_squeeze_closed(self, symbol, pnl, entry=0, exit_price=0,
                          hod=0, avg_squeeze_vol=0, bar_time: str = ""):
    ...
    if bar_time:
        h, m = int(bar_time.split(":")[0]), int(bar_time.split(":")[1])
        lockout_min = h * 60 + m + int(self._cascade_lockout_min)
        self._lockout_until_minutes = lockout_min  # Minutes since midnight
    ...

def on_bar_close_1m(self, bar, vwap=None, bar_time: str = "") -> Optional[str]:
    ...
    # Check lockout
    if self._lockout_until_minutes is not None and bar_time:
        h, m = int(bar_time.split(":")[0]), int(bar_time.split(":")[1])
        current_min = h * 60 + m
        if current_min < self._lockout_until_minutes:
            return None  # LOCKED — zero processing
    ...
```

**In simulate.py:** Pass `time_str` to both methods where they're called (the `time_str` variable is already available at every call site).

---

### Item 4: Widen CT Target for Proven Runners (OPTIONAL — Gate Behind Env Var)

**Problem:** CT uses the same 2R target as SQ. But CT enters a stock that has already proven it runs. A wider target captures more of the move.

**Fix:** Add a CT-specific target multiplier.

```python
# In continuation_detector.py:
self._ct_target_r = float(os.getenv("WB_CT_TARGET_R", "3.0"))  # Default 3R vs SQ's 2R
```

**In simulate.py/trade_manager.py:** When the trade's `setup_type == "continuation"`, use `ct_target_r` instead of `sq_target_r` for the 2R target exit calculation.

**Env var:**
```
WB_CT_TARGET_R=3.0    # CT exits at 3R instead of SQ's 2R (OFF by default = same as SQ if not set)
```

**Gate this behind `WB_CT_WIDER_TARGET=0` (OFF by default).** Test with default 2R first. Enable wider target only after base CT is validated.

---

## What You're NOT Changing

1. **Squeeze detector** — zero changes to squeeze_detector.py
2. **SQ exit system** — sq_target_hit, sq_para_trail, sq_max_loss all unchanged
3. **CT state machine** — IDLE → SQ_CONFIRMED → WATCHING → CT_PRIMED → CT_ARMED → CT_TRIGGERED stays the same
4. **CT entry logic** — break of consolidation high, stop below pullback low, unchanged
5. **CT sizing** — probe 50% on first, full 100% on second, unchanged
6. **CT max re-entries** — 2 max, unchanged

---

## Implementation Order

1. **Item 1** (cascade lockout) — this is the regression fix, do it first
2. **Item 3** (bar time passing) — needed for Item 1 to work in sim
3. Run regression tests → must pass at $0 delta
4. **Item 2** (soft gates) — improves EEIQ capture
5. Run value-add tests → EEIQ must show improvement
6. **Item 4** (wider target) — optional, only after base validates
7. Run full test suite

---

## Test Suite

### Phase 1: Regression (MUST ALL PASS AT $0 DELTA)

```bash
cd ~/warrior_bot_v2

# VERO: Cascade stock. CT must never fire. $0 delta required.
echo "=== VERO SQ-only baseline ==="
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== VERO SQ+CT ==="
WB_CT_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/

# ROLR: Cascade stock. CT must never fire. $0 delta required.
echo "=== ROLR SQ-only baseline ==="
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== ROLR SQ+CT ==="
WB_CT_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/

# CRE: Single squeeze, no continuation. $0 delta required.
echo "=== CRE SQ-only baseline ==="
python simulate.py CRE 2026-03-06 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== CRE SQ+CT ==="
WB_CT_ENABLED=1 python simulate.py CRE 2026-03-06 07:00 12:00 --ticks --tick-cache tick_cache/

# NPT: Captured full move. $0 delta required.
echo "=== NPT SQ-only baseline ==="
python simulate.py NPT 2026-02-03 07:00 20:00 --ticks --tick-cache tick_cache/
echo "=== NPT SQ+CT ==="
WB_CT_ENABLED=1 python simulate.py NPT 2026-02-03 07:00 20:00 --ticks --tick-cache tick_cache/
```

**Pass criteria:** Every SQ+CT P&L must EXACTLY match SQ-only P&L. Zero delta. Not -$1, not +$1. Zero.

### Phase 2: Value-Add (CT MUST ADD P&L)

```bash
cd ~/warrior_bot_v2

# EEIQ: Should fire 1-2 CT entries after 10:05 SQ exit
echo "=== EEIQ SQ-only ==="
python simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== EEIQ SQ+CT (verbose) ==="
WB_CT_ENABLED=1 python simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | grep -E "CT_|SQ_|ENTRY|EXIT|P&L"

# ASTC: Should fire 1-2 CT entries after 10:17 SQ exit
echo "=== ASTC SQ-only ==="
python simulate.py ASTC 2026-03-30 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== ASTC SQ+CT (verbose) ==="
WB_CT_ENABLED=1 python simulate.py ASTC 2026-03-30 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | grep -E "CT_|SQ_|ENTRY|EXIT|P&L"

# SHPH: Should fire CT entries after $2.75 SQ exit — stock went to $25
echo "=== SHPH SQ-only ==="
python simulate.py SHPH 2026-01-20 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== SHPH SQ+CT (verbose) ==="
WB_CT_ENABLED=1 python simulate.py SHPH 2026-01-20 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | grep -E "CT_|SQ_|ENTRY|EXIT|P&L"

# ROLR: On ROLR, CT should NOT fire (lockout protects cascade).
# But check that the SQ cascade is completely unaffected.
```

**Pass criteria:**
- EEIQ: SQ+CT > SQ-only (CT adds incremental P&L)
- ASTC: SQ+CT > SQ-only (CT captures part of $4.14→$6.48 leg)
- SHPH: SQ+CT > SQ-only (CT captures part of $2.75→$25 move)
- All CT trades must be `setup_type=continuation`

### Phase 3: Edge Cases

```bash
# BATL: Fast cascade — lockout should prevent CT, but stock consolidates at $6.45
# If lockout expires before session end, CT might find a late entry. Either way, SQ P&L must be unchanged.
echo "=== BATL SQ+CT ==="
WB_CT_ENABLED=1 python simulate.py BATL 2026-01-26 07:00 12:00 --ticks --tick-cache tick_cache/

# AHMA: Parabolic escalation — SQ cascades ($7→$10→$12→$13.66)
# Lockout should prevent CT during the cascade. After cascade exhausts, CT may find a late entry.
echo "=== AHMA SQ+CT ==="
WB_CT_ENABLED=1 python simulate.py AHMA 2026-01-13 07:00 12:00 --ticks --tick-cache tick_cache/

# RUBI: Multiple SQ entries with weakening momentum
echo "=== RUBI SQ+CT ==="
WB_CT_ENABLED=1 python simulate.py RUBI 2026-02-19 07:00 12:00 --ticks --tick-cache tick_cache/
```

### Phase 4: Full YTD A/B

Only after Phases 1-3 pass:

```bash
cd ~/warrior_bot_v2

# Modify run_ytd_v2_backtest.py:
# Config A: WB_CT_ENABLED=0 (current SQ-only baseline)
# Config B: WB_CT_ENABLED=1 (SQ + CT)
# Run full 59-day YTD on IBKR tick data
# Compare total P&L, per-day P&L, CT trade count, CT win rate
python run_ytd_v2_backtest.py
```

---

## Success Criteria

| Metric | Requirement |
|--------|------------|
| VERO regression | $0 delta (SQ+CT = SQ-only exactly) |
| ROLR regression | $0 delta |
| CRE regression | $0 delta |
| NPT regression | $0 delta |
| EEIQ value-add | SQ+CT > SQ-only |
| ASTC value-add | SQ+CT > SQ-only |
| SHPH value-add | SQ+CT > SQ-only |
| CT win rate | > 40% across all CT trades |
| YTD SQ+CT total | > $266,258 (SQ-only baseline) |
| SQ trades unchanged | Every SQ trade in SQ+CT mode must match SQ-only mode exactly |

---

## Env Var Summary (New/Changed)

```bash
# New in this directive:
WB_CT_CASCADE_LOCKOUT_MIN=10     # Minutes after last SQ close before CT can process bars

# Unchanged from prior CT:
WB_CT_ENABLED=0                   # Master gate (0=OFF, 1=ON)
WB_CT_COOLDOWN_BARS=3             # Post-lockout cooldown before watching
WB_CT_MAX_REENTRIES=2             # Max CT trades per symbol per session
WB_CT_MIN_PULLBACK_BARS=1         # Min pullback bars
WB_CT_MAX_PULLBACK_BARS=5         # Max pullback bars
WB_CT_MAX_RETRACE_PCT=50          # Max retracement %
WB_CT_MIN_VOL_DECAY=1.50          # Pullback vol / squeeze vol threshold
WB_CT_REQUIRE_VWAP=1              # Require above VWAP
WB_CT_REQUIRE_EMA=1               # Require above 9 EMA
WB_CT_REQUIRE_MACD=1              # Require positive MACD
WB_CT_PROBE_SIZE=0.5              # First re-entry sizing
WB_CT_FULL_SIZE=1.0               # Second re-entry sizing

# Optional (Item 4 — gated OFF):
WB_CT_WIDER_TARGET=0              # OFF by default; when ON, CT uses WB_CT_TARGET_R
WB_CT_TARGET_R=3.0                # CT target multiplier (vs SQ's 2R)
```

---

## Commit Checklist

1. `continuation_detector.py` — cascade lockout, soft gates, bar_time passing
2. `simulate.py` — pass bar_time to CT methods, lockout gate in both tick and bar mode paths
3. `bot_ibkr.py` — same lockout gate, pass current time to CT methods
4. `.env` — add `WB_CT_CASCADE_LOCKOUT_MIN=10`
5. Run Phase 1 regression → commit only if $0 delta
6. Run Phase 2 value-add → commit with results
7. Cowork report with before/after comparison

---

## The Bottom Line

SQ is perfect. CT's only job is to capture the second wave on stocks where SQ already proved the stock is a runner. The cascade lockout ensures CT never interferes with SQ's cascade mechanism. The soft gates ensure CT doesn't discard valid pullbacks. On stocks like ASTC ($4.14→$6.48), SHPH ($2.75→$25), and EEIQ ($9.45→$12.70), even modest CT capture adds thousands per occurrence.
