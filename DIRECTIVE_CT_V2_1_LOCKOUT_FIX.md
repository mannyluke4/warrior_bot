# DIRECTIVE: CT V2.1 — Lockout Fix + Cascade Gate Tuning

**Date:** 2026-03-30
**Author:** Cowork (Opus)
**For:** CC (Sonnet)
**Priority:** P1 — CT V2 regression is clean but value-add is near-zero. These fixes unlock it.
**Branch:** `v2-ibkr-migration`
**Prerequisite:** CT V2 (commit 0ddc81e) must be in place. This directive modifies its parameters.

---

## Context: Why CT V2 Underperformed

CT V2 (commit 0ddc81e) achieved the critical goal: **$0 regression delta on all cascade stocks**. But it only added **+$413 on one stock (EEIQ)**. The deep dive analysis estimated +$8K–$15K of CT opportunity in the YTD data. Two configuration issues are suppressing CT's value:

### Issue 1: 60-Minute Lockout Is Far Too Long

The directive specified `WB_CT_CASCADE_LOCKOUT_MIN=10`. CC changed it to **60 minutes** based on earlier V1.3 testing where 10 min failed — but that was BEFORE the cascade gate (`_sq_trade_count > _max_sq_for_ct`) existed. The cascade gate is now the primary protection against regression. The lockout is a secondary safeguard.

**Impact:** On EEIQ, SQ exits at 10:05 → lockout until **11:05** → CT doesn't even start watching for an hour. The actual CT entry was at 11:57, nearly 2 hours after exit. With a 10-minute lockout, CT would start watching at 10:15 and could potentially catch earlier continuation setups in the 10:15–10:30 window.

**On faster-continuation stocks (SHPH, ROLR-style):** The best CT setups happen 2–15 minutes after SQ exit. A 60-minute lockout misses ALL of them. The continuation window closes long before the lockout expires.

### Issue 2: MAX_SQ_TRADES=1 Blocks Legitimate CT Candidates

ASTC had 2 SQ trades at 10:17 and 10:18 (one minute apart). With `MAX_SQ_TRADES=1`, `_sq_trade_count=2 > 1` → CT permanently blocked. But ASTC is NOT a VERO-style cascade. It's a stock that fired two quick squeezes and then kept running to $6.48. VERO fired 5 SQ trades. ROLR fired 3. These are different situations.

**The cascade gate should block 3+ SQ trades (true cascades), not 2.**

### Issue 3: SHPH Was Never Tested

SHPH ($2.75 → $25.11) is the single biggest CT opportunity in the dataset. Tick data exists in `tick_cache/2026-01-20/SHPH.json.gz`. The directive explicitly listed SHPH in Phase 2 but CC's report only covers EEIQ and ASTC.

---

## What You're Changing (3 Items)

### Item 1: Reduce Lockout to 10 Minutes

**File:** `.env` (and default in `continuation_detector.py`)

```python
# In continuation_detector.py, change the default:
self._cascade_lockout_min = float(os.getenv("WB_CT_CASCADE_LOCKOUT_MIN", "10"))
#                                                                         ^^^^ was "60"
```

**In `.env`:**
```bash
WB_CT_CASCADE_LOCKOUT_MIN=10    # was 60
```

**Rationale:** The cascade gate (`_sq_trade_count > _max_sq_for_ct`) is what blocks VERO/ROLR/AHMA, not the lockout timer. The lockout is a secondary buffer for stocks that just barely slip through the cascade gate. 10 minutes is sufficient:
- VERO cascades over ~8 min → 10-min lockout covers it, AND cascade gate blocks it anyway
- EEIQ single SQ at 10:05 → unlocks at 10:15 instead of 11:05 → 50 minutes more CT window
- ASTC last SQ at 10:18 → unlocks at 10:28 → catches $4.14→$6.48 continuation

---

### Item 2: Raise MAX_SQ_TRADES from 1 to 2

**File:** `.env` (and default in `continuation_detector.py`)

```python
# In continuation_detector.py, change the default:
self._max_sq_for_ct = int(os.getenv("WB_CT_MAX_SQ_TRADES", "2"))
#                                                            ^^^ was "1"
```

**In `.env`:**
```bash
WB_CT_MAX_SQ_TRADES=2    # was 1
```

**What this changes:**
- Stocks with 1 SQ trade: CT allowed (unchanged — EEIQ, CRE, SHPH if single-SQ)
- Stocks with 2 SQ trades: **CT now allowed** (NEW — ASTC)
- Stocks with 3+ SQ trades: CT blocked (unchanged — VERO, ROLR, AHMA, BATL)

**Regression safety:** VERO (5 trades), ROLR (3 trades), AHMA (cascade), BATL (cascade) all have 3+ SQ trades → still permanently blocked by cascade gate. $0 delta guaranteed on these stocks.

---

### Item 3: Reduce Cooldown from 3 to 2 Bars

**File:** `.env` (and default in `continuation_detector.py`)

```python
# In continuation_detector.py, change the default:
self._cooldown_bars = int(os.getenv("WB_CT_COOLDOWN_BARS", "2"))
#                                                           ^^^ was "3"
```

**In `.env`:**
```bash
WB_CT_COOLDOWN_BARS=2    # was 3
```

**Rationale:** After the lockout expires, CT enters a 3-bar cooldown before it starts watching for pullbacks. Combined with 10-minute lockout, the total delay is lockout + 3 minutes = 13 minutes. On fast-continuation stocks (SHPH, ASTC), the optimal CT window is 2–15 minutes after SQ exit. Reducing cooldown to 2 bars brings total delay to 12 minutes, giving CT one more bar of opportunity.

---

## What You're NOT Changing

1. **All CT code logic** — state machine, gates, soft/hard resets, entry/exit — unchanged
2. **Squeeze detector** — zero changes
3. **Cascade gate logic** — same code, just different threshold
4. **Lockout mechanism** — same code, just shorter duration
5. **Soft gates** — already working correctly from V2

---

## Test Suite

### Phase 1: Regression (MUST ALL PASS AT $0 DELTA)

These stocks all have 3+ SQ trades → cascade gate blocks CT → must be identical.

```bash
cd ~/warrior_bot_v2

# VERO: 5 SQ trades → cascade gate blocks CT. Must be $0 delta.
echo "=== VERO SQ-only ==="
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== VERO SQ+CT ==="
WB_CT_ENABLED=1 WB_CT_CASCADE_LOCKOUT_MIN=10 WB_CT_MAX_SQ_TRADES=2 WB_CT_COOLDOWN_BARS=2 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/

# ROLR: 3 SQ trades → cascade gate blocks CT. Must be $0 delta.
echo "=== ROLR SQ-only ==="
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== ROLR SQ+CT ==="
WB_CT_ENABLED=1 WB_CT_CASCADE_LOCKOUT_MIN=10 WB_CT_MAX_SQ_TRADES=2 WB_CT_COOLDOWN_BARS=2 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/

# CRE: 1 SQ trade, no continuation. $0 delta expected.
echo "=== CRE SQ-only ==="
python simulate.py CRE 2026-03-06 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== CRE SQ+CT ==="
WB_CT_ENABLED=1 WB_CT_CASCADE_LOCKOUT_MIN=10 WB_CT_MAX_SQ_TRADES=2 WB_CT_COOLDOWN_BARS=2 python simulate.py CRE 2026-03-06 07:00 12:00 --ticks --tick-cache tick_cache/

# BATL: Cascade stock (3+ trades). $0 delta expected.
echo "=== BATL SQ-only ==="
python simulate.py BATL 2026-01-26 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== BATL SQ+CT ==="
WB_CT_ENABLED=1 WB_CT_CASCADE_LOCKOUT_MIN=10 WB_CT_MAX_SQ_TRADES=2 WB_CT_COOLDOWN_BARS=2 python simulate.py BATL 2026-01-26 07:00 12:00 --ticks --tick-cache tick_cache/

# AHMA: Cascade stock (3+ trades). $0 delta expected.
echo "=== AHMA SQ-only ==="
python simulate.py AHMA 2026-01-13 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== AHMA SQ+CT ==="
WB_CT_ENABLED=1 WB_CT_CASCADE_LOCKOUT_MIN=10 WB_CT_MAX_SQ_TRADES=2 WB_CT_COOLDOWN_BARS=2 python simulate.py AHMA 2026-01-13 07:00 12:00 --ticks --tick-cache tick_cache/
```

**Pass criteria:** Every SQ+CT P&L must EXACTLY match SQ-only P&L. $0 delta. If ANY regression fails, STOP and report — do not continue to Phase 2.

### Phase 2: Value-Add (CT MUST ADD P&L)

```bash
cd ~/warrior_bot_v2

# EEIQ: Known CT candidate. Should fire earlier with 10-min lockout (vs 60-min).
echo "=== EEIQ SQ-only ==="
python simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== EEIQ SQ+CT (verbose) ==="
WB_CT_ENABLED=1 WB_CT_CASCADE_LOCKOUT_MIN=10 WB_CT_MAX_SQ_TRADES=2 WB_CT_COOLDOWN_BARS=2 python simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | grep -E "CT_|SQ_|ENTRY|EXIT|P&L|ARMED|TRIGGER"

# ASTC: Was blocked by cascade gate (2 SQ trades). NOW allowed with MAX_SQ_TRADES=2.
echo "=== ASTC SQ-only ==="
python simulate.py ASTC 2026-03-30 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== ASTC SQ+CT (verbose) ==="
WB_CT_ENABLED=1 WB_CT_CASCADE_LOCKOUT_MIN=10 WB_CT_MAX_SQ_TRADES=2 WB_CT_COOLDOWN_BARS=2 python simulate.py ASTC 2026-03-30 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | grep -E "CT_|SQ_|ENTRY|EXIT|P&L|ARMED|TRIGGER"

# SHPH: The big one. $2.75 → $25.11. Was NOT TESTED in V2.
# Tick data: tick_cache/2026-01-20/SHPH.json.gz
echo "=== SHPH SQ-only ==="
python simulate.py SHPH 2026-01-20 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== SHPH SQ+CT (verbose) ==="
WB_CT_ENABLED=1 WB_CT_CASCADE_LOCKOUT_MIN=10 WB_CT_MAX_SQ_TRADES=2 WB_CT_COOLDOWN_BARS=2 python simulate.py SHPH 2026-01-20 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | grep -E "CT_|SQ_|ENTRY|EXIT|P&L|ARMED|TRIGGER"

# RUBI: Medium continuation opportunity, multiple SQ entries with weakening momentum
echo "=== RUBI SQ-only ==="
python simulate.py RUBI 2026-02-19 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== RUBI SQ+CT (verbose) ==="
WB_CT_ENABLED=1 WB_CT_CASCADE_LOCKOUT_MIN=10 WB_CT_MAX_SQ_TRADES=2 WB_CT_COOLDOWN_BARS=2 python simulate.py RUBI 2026-02-19 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | grep -E "CT_|SQ_|ENTRY|EXIT|P&L|ARMED|TRIGGER"
```

**Pass criteria:**
- EEIQ: SQ+CT > SQ-only (expect same or better than V2's +$413)
- ASTC: SQ+CT > SQ-only (CT should now fire — was blocked in V2)
- SHPH: SQ+CT > SQ-only (first time being tested — this is the big validation)
- RUBI: SQ+CT >= SQ-only (nice-to-have, not required)

### Phase 3: Full YTD A/B (Only After Phases 1-2 Pass)

```bash
cd ~/warrior_bot_v2

# Run full 59-day YTD with CT V2.1 settings
WB_CT_ENABLED=1 WB_CT_CASCADE_LOCKOUT_MIN=10 WB_CT_MAX_SQ_TRADES=2 WB_CT_COOLDOWN_BARS=2 python run_ytd_v2_backtest.py

# Compare against SQ-only baseline ($266,258)
```

---

## Success Criteria

| Metric | Requirement |
|--------|------------|
| VERO regression | $0 delta |
| ROLR regression | $0 delta |
| CRE regression | $0 delta |
| BATL regression | $0 delta |
| AHMA regression | $0 delta |
| EEIQ value-add | SQ+CT > SQ-only |
| ASTC value-add | SQ+CT > SQ-only |
| SHPH value-add | SQ+CT > SQ-only |
| YTD total | > $266,258 (SQ-only baseline) |
| SQ trades unchanged | Every SQ trade in SQ+CT must match SQ-only exactly |

---

## Env Var Summary (Changes from V2)

```bash
# CHANGED in this directive:
WB_CT_CASCADE_LOCKOUT_MIN=10     # was 60 — reduced to match original directive
WB_CT_MAX_SQ_TRADES=2            # was 1 — allow CT on 2-SQ stocks (ASTC)
WB_CT_COOLDOWN_BARS=2            # was 3 — one bar faster

# UNCHANGED:
WB_CT_ENABLED=0                   # Master gate (set to 1 for testing)
WB_CT_MAX_REENTRIES=2
WB_CT_MIN_PULLBACK_BARS=1
WB_CT_MAX_PULLBACK_BARS=5
WB_CT_MAX_RETRACE_PCT=50
WB_CT_MIN_VOL_DECAY=1.50
WB_CT_REQUIRE_VWAP=1
WB_CT_REQUIRE_EMA=1
WB_CT_REQUIRE_MACD=1
WB_CT_PROBE_SIZE=0.5
WB_CT_FULL_SIZE=1.0
WB_CT_WIDER_TARGET=0
WB_CT_TARGET_R=3.0
```

---

## Commit Checklist

1. Change 3 defaults in `continuation_detector.py`:
   - `WB_CT_CASCADE_LOCKOUT_MIN` default: `"60"` → `"10"`
   - `WB_CT_MAX_SQ_TRADES` default: `"1"` → `"2"`
   - `WB_CT_COOLDOWN_BARS` default: `"3"` → `"2"`
2. Update `.env` with new values
3. Run Phase 1 regression → must pass at $0 delta on ALL 5 stocks
4. Run Phase 2 value-add → report CT trades on EEIQ, ASTC, SHPH, RUBI
5. Write cowork report with before/after comparison
6. If Phase 1 and 2 pass, run Phase 3 (full YTD A/B)

---

## The Bottom Line

CT V2 proved the architecture works — $0 regression, clean implementation. But the parameters were too conservative: a 60-minute lockout and a 1-stock cascade gate meant CT could barely fire. These three parameter changes (10-min lockout, 2-SQ gate, 2-bar cooldown) should unlock CT on the stocks where continuation is most valuable — ASTC, SHPH, and faster EEIQ entries — while maintaining $0 regression on all cascade stocks (3+ SQ trades).

The cascade gate is the real protection. The lockout is just a belt on top of the suspenders.
