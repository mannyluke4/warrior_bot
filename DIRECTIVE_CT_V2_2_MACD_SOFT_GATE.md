# DIRECTIVE: CT V2.2 — MACD Soft Gate + SHPH Unlock

**Date:** 2026-03-30
**Author:** Cowork (Opus)
**For:** CC (Sonnet)
**Priority:** P1 — CT V2.1 proved the lockout/cascade gate aren't the bottleneck. The quality gates are.
**Branch:** `v2-ibkr-migration`
**Prerequisite:** CT V2.1 (commit ecda119) must be in place.

---

## Context: The V2.1 Lesson

V2.1 reduced the lockout from 60→10 minutes and raised MAX_SQ_TRADES from 1→2. Result: regressions still perfect ($0 on all 5 stocks), but value-add was **worse** — EEIQ dropped from +$413 to $0, ASTC stayed at $0, RUBI lost $307.

CC's diagnosis is correct: **the MACD hard gate is the primary blocker.** After a squeeze, MACD goes negative during the pullback — that's normal digestion. But CT treats MACD negative as a hard reject that destroys all pullback context. Every potential CT entry on EEIQ and ASTC was killed by MACD.

The 60-minute lockout in V2 accidentally helped EEIQ because by 11:05, MACD had recovered. The shorter lockout meant CT started watching during the active sell-off phase → instant MACD hard reject.

The fix: **make MACD a soft gate** (pause and re-check, don't destroy pullback context). CT will naturally wait through the MACD-negative digest phase, and when MACD turns positive, re-arm with its full pullback context intact.

Additionally, SHPH has 3 SQ trades — same count as ROLR. We need to test whether MAX_SQ_TRADES=3 is safe. This is done as a separate phase so we can stop if ROLR regresses.

---

## What You're Changing (2 Phases)

### Phase A: MACD Soft Gate (PRIMARY FIX)

**File:** `continuation_detector.py`

Change the MACD gate from hard to soft, matching the existing VWAP/EMA soft gates:

```python
# CURRENT (hard gate — destroys pullback context):
if self._require_macd and not self.macd_state.bullish():
    return self._reset("CT_REJECT: MACD negative — dump, not dip")

# NEW (soft gate — pause and re-check, keep pullback context):
if self._require_macd and not self.macd_state.bullish():
    self._state = "WATCHING"  # Go back to WATCHING but KEEP pullback bars
    return "CT_PAUSE: MACD negative, re-checking next bar"
```

**Where this appears:** In the `on_bar_close_1m()` method, inside the `CT_PRIMED` state handling. The MACD gate should be modified to match the pattern used for VWAP and EMA soft gates (which you already implemented in V2).

**What stays hard:** Retrace > 50% and pullback > 5 bars remain hard rejects. These indicate genuine exhaustion, not temporary digestion.

**Updated gate table:**

| Gate | Behavior | Rationale |
|------|----------|-----------|
| Volume too high | **Soft** (pause) | Can recover as selling dries up |
| Below VWAP | **Soft** (pause) | Stock can reclaim on next bar |
| Below EMA | **Soft** (pause) | Stock can reclaim on next bar |
| MACD negative | **Soft** (pause) ← CHANGED | Normal post-squeeze digestion, not a dump |
| Retrace > 50% | **Hard** (reset) | Genuine exhaustion |
| Pullback > 5 bars | **Hard** (reset) | Too long, momentum gone |

**Env var:** `WB_CT_REQUIRE_MACD=1` stays at 1. The gate still checks MACD — it just pauses instead of resetting. If you want to add a new env var `WB_CT_MACD_HARD=0` to toggle between hard/soft, that's fine but not required. The simpler approach: just change the behavior in code and let `REQUIRE_MACD=0` disable it entirely if needed.

---

### Phase B: Raise MAX_SQ_TRADES to 3 (UNLOCK SHPH)

**Only implement Phase B after Phase A passes regression.**

SHPH had 3 SQ entries ($2.04, $3.04, $4.04). The cascade ended by 08:13. The stock then ran from $4.04 to $25.11 — a $21 move that CT can't touch because MAX_SQ_TRADES=2 blocks 3-SQ stocks.

ROLR also has 3 SQ trades. This is the regression risk. But with MACD as a soft gate:
- If ROLR's post-cascade pullbacks have MACD negative the whole time → CT never arms → $0 delta
- If ROLR's post-cascade shows a brief MACD-positive window → CT could arm and potentially enter → regression risk

**We test this explicitly.** Phase B has its own regression check before proceeding.

**File:** `continuation_detector.py` and `.env`

```python
# Change default:
self._max_sq_for_ct = int(os.getenv("WB_CT_MAX_SQ_TRADES", "3"))
#                                                            ^^^ was "2"
```

**In `.env`:**
```bash
WB_CT_MAX_SQ_TRADES=3    # was 2 — allows CT on 3-SQ stocks (SHPH)
```

**What this changes:**
- Stocks with ≤3 SQ trades: CT allowed (SHPH ✅, ROLR ⚠️, EEIQ ✅, ASTC ✅)
- Stocks with 4+ SQ trades: CT blocked (VERO 5 trades ✅, others if 4+)

---

## Also: Investigate RUBI Counting Bug

CC's V2.1 report flagged that RUBI had 3 SQ trades (07:23, 08:43, 08:44) — which should have been blocked at MAX_SQ_TRADES=2. But CT fired anyway (and lost $307). Either:

1. One of the 3 "SQ trades" was actually a CT trade misrouted through the SQ path
2. The `_sq_trade_count` tracker isn't incrementing correctly
3. The 3rd trade happened at a different time than the first two, resetting the count somehow

**Please check the verbose output and confirm whether the count is tracking correctly.** This is important — if the cascade gate has a bug, it could compromise regression safety.

```bash
# Debug RUBI counting:
WB_CT_ENABLED=1 WB_CT_CASCADE_LOCKOUT_MIN=10 WB_CT_MAX_SQ_TRADES=2 WB_CT_COOLDOWN_BARS=2 python simulate.py RUBI 2026-02-19 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | grep -E "sq_trade_count|notify_squeeze|CT_BLOCKED|cascade"
```

---

## What You're NOT Changing

1. **Squeeze detector** — zero changes
2. **SQ exit system** — unchanged
3. **CT state machine** — same states, same transitions
4. **CT entry logic** — break of consolidation high, stop below pullback low
5. **Lockout timer** — stays at 10 minutes (V2.1 setting)
6. **Cooldown bars** — stays at 2 (V2.1 setting)
7. **Other soft gates** — VWAP/EMA/Volume remain soft (V2 setting)
8. **Hard gates** — Retrace >50% and pullback >5 bars remain hard rejects

---

## Implementation Order

1. **Phase A: MACD soft gate** — change the one gate
2. Run Phase A regression (5 stocks, $0 delta required)
3. Run Phase A value-add (EEIQ, ASTC — expect improvement)
4. **If Phase A passes:** Phase B: MAX_SQ_TRADES=3
5. Run Phase B regression (CRITICAL: test ROLR specifically)
6. Run Phase B value-add (SHPH — the big prize)
7. If Phase B causes ROLR regression → revert to MAX_SQ_TRADES=2 and keep MACD soft gate only
8. Investigate RUBI counting bug (can run in parallel)

---

## Test Suite

### Phase A Tests: MACD Soft Gate

#### A1: Regression (MUST ALL PASS AT $0 DELTA)

```bash
cd ~/warrior_bot_v2

# All 5 cascade/no-continuation stocks — $0 delta required
for stock_date in "VERO 2026-01-16" "ROLR 2026-01-14" "CRE 2026-03-06" "BATL 2026-01-26" "AHMA 2026-01-13"; do
    read stock date <<< "$stock_date"
    echo "=== $stock SQ-only ==="
    python simulate.py $stock $date 07:00 12:00 --ticks --tick-cache tick_cache/
    echo "=== $stock SQ+CT ==="
    WB_CT_ENABLED=1 python simulate.py $stock $date 07:00 12:00 --ticks --tick-cache tick_cache/
done
```

**If ANY regression fails → STOP. Do not proceed to A2 or Phase B.**

#### A2: Value-Add

```bash
cd ~/warrior_bot_v2

# EEIQ: The key test. MACD soft gate should allow CT to survive the pullback digest.
echo "=== EEIQ SQ-only ==="
python simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== EEIQ SQ+CT (verbose) ==="
WB_CT_ENABLED=1 python simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | grep -E "CT_|SQ_|ENTRY|EXIT|P&L|ARMED|TRIGGER|MACD|PAUSE"

# ASTC: Should now pass MACD gate during pullback.
echo "=== ASTC SQ-only ==="
python simulate.py ASTC 2026-03-30 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== ASTC SQ+CT (verbose) ==="
WB_CT_ENABLED=1 python simulate.py ASTC 2026-03-30 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | grep -E "CT_|SQ_|ENTRY|EXIT|P&L|ARMED|TRIGGER|MACD|PAUSE"
```

**Expected:**
- EEIQ: SQ+CT > SQ-only (CT enters after MACD recovers, with pullback context preserved)
- ASTC: SQ+CT > SQ-only (CT catches $4.14→$6.48 continuation)
- If BOTH show $0 delta still (CT never fires even with MACD soft), report the verbose gate output so we can diagnose further

---

### Phase B Tests: MAX_SQ_TRADES=3 (ONLY IF PHASE A PASSES)

#### B1: ROLR Regression (CRITICAL)

```bash
cd ~/warrior_bot_v2

# ROLR has exactly 3 SQ trades. With MAX_SQ_TRADES=3, CT is now ALLOWED.
# This MUST still show $0 delta — if CT fires and loses, it's a regression.
echo "=== ROLR SQ-only ==="
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== ROLR SQ+CT (verbose) ==="
WB_CT_ENABLED=1 WB_CT_MAX_SQ_TRADES=3 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | grep -E "CT_|SQ_|ENTRY|EXIT|P&L|ARMED|TRIGGER|cascade|lockout"

# Also re-test VERO (5 trades — should still be blocked at 4+)
echo "=== VERO SQ+CT (MAX_SQ=3) ==="
WB_CT_ENABLED=1 WB_CT_MAX_SQ_TRADES=3 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
```

**If ROLR regression fails (delta ≠ $0):**
- Revert MAX_SQ_TRADES to 2
- Keep MACD soft gate (Phase A change)
- Report: "Phase B failed — ROLR regression. SHPH locked behind cascade gate."
- We'll explore alternative SHPH unlock strategies in a separate directive

**If ROLR regression passes ($0 delta):**

#### B2: SHPH Value-Add (The Big Prize)

```bash
cd ~/warrior_bot_v2

# SHPH: 3 SQ entries ($2.04, $3.04, $4.04), cascade ends ~08:13
# Stock runs from $4.04 to $25.11. CT should capture part of this.
echo "=== SHPH SQ-only ==="
python simulate.py SHPH 2026-01-20 07:00 12:00 --ticks --tick-cache tick_cache/
echo "=== SHPH SQ+CT (verbose) ==="
WB_CT_ENABLED=1 WB_CT_MAX_SQ_TRADES=3 python simulate.py SHPH 2026-01-20 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 | grep -E "CT_|SQ_|ENTRY|EXIT|P&L|ARMED|TRIGGER|MACD|PAUSE|lockout"
```

**Expected:** SQ+CT > SQ-only. Even a modest capture of the $4→$25 move would be significant (+$1K–$5K).

---

### Phase C: Full YTD A/B (ONLY IF A+B PASS)

```bash
cd ~/warrior_bot_v2

# Full 59-day YTD comparison
# Config A: WB_CT_ENABLED=0 (SQ-only baseline: ~$266K)
# Config B: WB_CT_ENABLED=1 WB_CT_MAX_SQ_TRADES=3 (SQ + CT V2.2)
python run_ytd_v2_backtest.py
```

---

## Success Criteria

| Metric | Phase A | Phase B |
|--------|---------|---------|
| VERO regression | $0 delta | $0 delta |
| ROLR regression | $0 delta | **$0 delta (CRITICAL)** |
| CRE regression | $0 delta | $0 delta |
| BATL regression | $0 delta | $0 delta |
| AHMA regression | $0 delta | $0 delta |
| EEIQ value-add | SQ+CT > SQ-only | — |
| ASTC value-add | SQ+CT > SQ-only | — |
| SHPH value-add | — | SQ+CT > SQ-only |
| RUBI bug | Counting investigation | — |
| YTD total (Phase C) | — | > $266,258 |

---

## Env Var Summary (Changes from V2.1)

```bash
# CHANGED in this directive:
# Phase A: No env var changes — code change only (MACD hard→soft)
# Phase B: WB_CT_MAX_SQ_TRADES=3    # was 2

# UNCHANGED from V2.1:
WB_CT_ENABLED=0                   # Master gate (set to 1 for testing)
WB_CT_CASCADE_LOCKOUT_MIN=10      # 10 min lockout (V2.1 setting)
WB_CT_COOLDOWN_BARS=2             # 2 bar cooldown (V2.1 setting)
WB_CT_MAX_REENTRIES=2
WB_CT_MIN_PULLBACK_BARS=1
WB_CT_MAX_PULLBACK_BARS=5
WB_CT_MAX_RETRACE_PCT=50
WB_CT_MIN_VOL_DECAY=1.50
WB_CT_REQUIRE_VWAP=1              # Soft gate
WB_CT_REQUIRE_EMA=1               # Soft gate
WB_CT_REQUIRE_MACD=1              # Still checked, but now SOFT (code change)
WB_CT_PROBE_SIZE=0.5
WB_CT_FULL_SIZE=1.0
WB_CT_WIDER_TARGET=0
WB_CT_TARGET_R=3.0
```

---

## Commit Checklist

1. **Phase A commit:**
   - Change MACD gate from hard to soft in `continuation_detector.py`
   - Run A1 regression → $0 delta on all 5
   - Run A2 value-add → report EEIQ/ASTC results
   - Commit with results

2. **Phase B commit (separate, only if A passes):**
   - Change `WB_CT_MAX_SQ_TRADES` default from `"2"` to `"3"` in `continuation_detector.py`
   - Update `.env`
   - Run B1 regression → ROLR must be $0 delta
   - Run B2 value-add → report SHPH results
   - Commit with results

3. **RUBI investigation:** Separate from A/B. Can run in parallel. Report findings.

4. **Cowork report:** Before/after comparison of V2, V2.1, V2.2 (Phase A), V2.2 (Phase A+B)

---

## The Bottom Line

The squeeze proved the stock. MACD going negative during the pullback is the stock catching its breath, not dying. Making MACD a soft gate lets CT wait through the digest phase and re-arm when momentum returns — exactly what a human trader would do. And SHPH's $4→$25 run after a 3-trade cascade is too big to leave locked behind a gate designed for VERO's 5-trade cascade.

Phase A is the safe bet (one code change, no env vars). Phase B is the bigger unlock (SHPH) with a clear abort path if ROLR regresses.
