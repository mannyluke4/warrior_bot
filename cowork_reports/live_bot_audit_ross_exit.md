# Live Bot Audit — Ross Exit Integration
**Date:** 2026-03-23
**Auditor:** Claude Sonnet 4.6 (CC)
**Purpose:** Pre-live-trading audit verifying Ross exit system is safe, correct, and consistent with live config.

---

## 1. Import / Syntax Check

| Module | Result |
|---|---|
| `bot.py` | ✅ Clean |
| `trade_manager.py` | ✅ Clean |
| `ross_exit.py` | ✅ Clean |

---

## 2. .env Consistency

- `WB_ROSS_EXIT_ENABLED=1` ✅ Present and ON
- All Ross exit sub-flags present and ON: `WB_ROSS_CUC_ENABLED`, `WB_ROSS_DOJI_ENABLED`, `WB_ROSS_GRAVESTONE_ENABLED`, `WB_ROSS_SHOOTING_STAR_ENABLED`, `WB_ROSS_MACD_ENABLED`, `WB_ROSS_EMA20_ENABLED`, `WB_ROSS_VWAP_ENABLED`, `WB_ROSS_STRUCTURAL_TRAIL=1`
- `WB_ROSS_CUC_MIN_R` not in .env → defaults to 5.0 in code ✅ (acceptable)
- `WB_ROSS_MIN_BARS=2` ✅
- No conflicting old SQ exit flags — SQ exits (`sq_target_hit`, `sq_para_trail`) still fire in sim/backtest but are gated OFF in live signal mode (Ross 1m signals replace pattern exits) ✅
- Classifier, exhaustion, pillar gates, continuation hold all consistent with CLAUDE.md "Current Live Config" ✅

---

## 3. Code Path Audit — trade_manager.py

### 3a. Call path: `on_bar_close_1m_ross_exit()`
- Called from `bot.py:on_bar_close_1m()` at line 478, gated by `getattr(trade_manager, 'ross_exit_enabled', False)` ✅
- Receives: `symbol, bar.open, bar.high, bar.low, bar.close, vwap=vwap`
- VWAP sourced from canonical 10s `bar_builder.get_vwap()` ✅
- Internally gated: returns immediately if `not self.ross_exit_enabled` ✅

### 3b. 10s BE/TW exits properly bypassed
- `trade_manager.on_bar_close()` (10s bars) runs `_manage_exits` first, then at line 2697: if `ross_exit_enabled and symbol in self.open: return` — bypasses all BE/TW pattern detection ✅
- `bot.py:on_bar_close_10s()` TW exit path gated by `not getattr(trade_manager, 'ross_exit_enabled', False)` ✅

### 3c. Hard stops still active with Ross exit ON
`_manage_exits` runs on every 10s bar tick regardless of Ross exit:
- Max loss cap (`max_loss_hit`) ✅
- Bail timer (`bail_timer`) ✅
- Hard stop / trail stop in signal mode (`stop_hit` / `trail_stop`) ✅
- Structural trailing stop (Ross) ratchets `t.stop` upward on green 1m bars ✅

### 3d. `_get_ross_mgr()` — lazy creation
- Creates `RossExitManager()` on first access per symbol ✅
- Does NOT pass any arguments (correct — config read from env at construction) ✅

### 3e. `reset()` on trade open
- Called at two locations: line 874 (`_ensure_open_trade_from_alpaca`) and line 1546 (`_check_pending_entry` fully-filled path) ✅
- Clears `partial_taken` and `bars_since_entry` ✅
- `_last_green_bar_low` intentionally NOT reset (structural trail carries price context from pre-entry bars) ✅

### 3f. Partial exit share count
- `qty_exit = t.qty_core if t.qty_core > 0 else max(1, t.qty_total // 2)` ✅
- With Ross split (50/50): `qty_core = qty_total // 2` → exits exactly half ✅
- `_check_pending_exit` else-block handles unknown reason strings (Ross reason strings all fall here): decrements `qty_core` first, then `qty_runner` ✅

### 3g. `_exit()` call path
- Used for both partial and full exits ✅
- Re-entry cooldown only triggers on `stop_hit` / `max_loss_hit`, NOT on Ross exit reasons ✅ (intentional — Ross exits are planned signal exits, not panic stops)

---

## 4. Bug Found and Fixed

### BUG: `t.tp_hit` vs `mgr.partial_taken` conflation in `on_bar_close_1m_ross_exit`

**Root cause:** `t.tp_hit` is set by two independent mechanisms:
1. Signal mode BE trigger in `_manage_exits` (line 3011): when `bid >= entry + 3R`, `t.tp_hit = True` to activate BE floor — **no shares are sold**
2. Ross doji partial path (line 2599): `t.tp_hit = True` after core shares are sold

**Before fix:** Lines 2584 and 2603 checked `t.tp_hit` to decide:
- Skip partial if "already taken"
- Exit only runner (not full position) on `full_100`

**Bug scenario:**
1. Trade opens; price runs to 3R+ → signal mode sets `t.tp_hit = True` (no shares sold)
2. Doji fires → `if t.tp_hit: return` → **partial silently skipped**
3. Full_100 fires → `qty_exit = t.qty_runner = 50` → **only 50 of 100 shares exited**
4. 50 "core" shares stranded; eventually hit by hard stop or next Ross bar signal

**Fix applied (2026-03-23):** Replace `t.tp_hit` checks with `mgr.partial_taken`:
- `mgr.partial_taken` is ONLY set when a Ross doji partial actually fires
- Signal-mode BE trigger does NOT touch `mgr.partial_taken`
- Both cases now correctly handled:
  - `mgr.partial_taken = True` → doji already fired → exit runner only on full_100 ✅
  - `mgr.partial_taken = False` (even if `t.tp_hit = True` from BE) → exit full position ✅

**File:** `trade_manager.py` lines 2584, 2603

---

## 5. Signal Mode Compatibility

### Re-entry after Ross exit
- Ross exit calls `_exit()` → on fill, `t.qty_total → 0` → position cleared from `open[]`
- MicroPullbackDetector state machine runs independently — continues running during and after exits
- When new ARM signal fires, bot re-enters normally → `reset()` called on Ross manager ✅

### BE/TW exits vs cascading re-entry
- With Ross exit OFF: BE/TW on 10s bars triggered re-entry via "small exit → re-arm → re-enter"
- With Ross exit ON: BE/TW on 10s bars bypassed; Ross 1m signals take that role
- Re-entry mechanism is identical — exit clears position, detector re-arms independently ✅

### Signal mode trail interaction
- `WB_SIGNAL_TRAIL_PCT=0.99` → `t.stop = t.peak * 0.01` (effectively no mechanical trail)
- Ross structural stop ratchets `t.stop` upward via green bar lows — dominates in practice ✅
- No conflict: both only move stop UP via `max()` ✅

---

## 6. Data Flow — bot.py

### 1m bar feed
- `bar_builder_1m = TradeBarBuilder(on_bar_close=on_bar_close_1m, ..., interval_seconds=60)` ✅
- `bar_builder_1m.on_trade()` called on every tick ✅
- Completed 1m bars fire `on_bar_close_1m(bar)` callback ✅
- `on_bar_close_1m` calls `on_bar_close_1m_ross_exit(symbol, bar.open, bar.high, bar.low, bar.close, vwap=vwap)` ✅

### VWAP sourcing
- VWAP for Ross exits comes from `bar_builder.get_vwap(symbol)` (10s canonical builder) ✅
- This is the same VWAP used for setup detection and other exits — consistent ✅

---

## 7. Edge Cases

### Cold start with existing position
- Reconcile thread calls `_ensure_open_trade_from_alpaca()` → calls `ross_exit_manager.reset()` ✅
- Ross manager EMA indicators start cold (not seeded from history)
- Seed bars in `seed_symbol_from_history()` do NOT feed RossExitManager — **noted, acceptable**
- During warmup: pattern exits (CUC, doji, gravestone, shooting star) active from bar 2+; MACD/EMA20 backstops available after 20-35 bars (~20-35 minutes after first live bar)

### First 1m bar of session
- `_bars_since_entry < _min_bars (2)` guard prevents any signal on first bar ✅
- Indicators update even on bars where no signal fires (warm-up happens continuously) ✅

### MACD warmup
- EMA12 seeds after 12 bars, EMA26 after 26, signal line after 26+9=35 bars
- `macd_histogram is not None` guard in ross_exit.py prevents backstop from firing before warmup ✅
- VWAP/EMA20 backstops also independently guarded (`e20 is not None`, `vwap and vwap > 0`) ✅

---

## 8. Regression Results

Both run with `WB_ROSS_EXIT_ENABLED=0 WB_MP_ENABLED=1` (Ross exit off — validates base behavior unchanged):

| Symbol | Date | P&L | Target | Status |
|---|---|---|---|---|
| VERO | 2026-01-16 | +$18,583 (trade #1, 18.6R) | +$18,583 | ✅ PASS |
| ROLR | 2026-01-14 | +$6,444 (trade #3, 6.5R) | +$6,444 | ✅ PASS |

---

## 9. Summary

**No crash paths identified.** Bot can start safely tomorrow morning.

**One bug found and fixed:** `t.tp_hit` vs `mgr.partial_taken` in `on_bar_close_1m_ross_exit` — partial would have been silently skipped and full exits would have left half the position stranded when a trade hit 3R+ before any Ross signal fired. Fixed by using `mgr.partial_taken` which is only set when a Ross doji partial actually fires.

**Known acceptable limitations (not bugs):**
- Ross manager EMAs not seeded from history — MACD/EMA20 backstops inactive for first ~35 min of each bot start
- Re-entry after partial+full exit relies on the detector re-arming naturally (same mechanism as before)
- `WB_ROSS_CUC_MIN_R` not explicitly in .env — uses code default of 5.0 (documented in ross_exit.py)
