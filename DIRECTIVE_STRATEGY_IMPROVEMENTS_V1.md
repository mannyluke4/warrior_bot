# Directive: Strategy Improvements — Weekly Backtest Findings

**TARGET**: 🖥️ MacBook Pro CC (code changes) → 🖥️ Mac Mini CC (backtesting)
**Priority**: HIGH
**Date**: 2026-03-18
**Status**: DRAFT — findings being added incrementally

---

## Context

After syncing the Mac Mini's `.env` to match the MacBook Pro's optimized config, we re-ran the weekly backtest (Mar 9-18). The new config performed **worse** than the old: old config +$9 → new config -$1,411 (delta: -$1,420).

Three separate problems were identified through analysis of the `WEEKLY_BACKTEST_NEWCONFIG_20260309_20260318.md` and `VOLUME_PRESSURE_REPORT.md`:

| Problem | Dollar Impact (Weekly) | Root Cause |
|---------|----------------------|------------|
| 0.75R max loss cap | -$1,327 net | Too tight for ultra-low float volatility; also creates re-entry loophole |
| Continuation hold direction-blind | -$471 | Suppresses exits based on volume magnitude, ignores buy vs sell pressure |
| Re-entry after max_loss_hit | -$916 | 0.75R exit doesn't trigger same cooldown as stop_hit |

---

## Fix 1: Direction-Aware Continuation Hold

**Impact**: +$471 (INKT +$317, TLYS +$154)
**Confidence**: HIGH — clear logic fix, no ambiguity

### Problem

The continuation hold checks `vol_dom` (recent 5-bar volume / session average volume) to decide whether to suppress BE/TW exit signals. High vol_dom = "stock is active, hold the position." But it can't tell if the volume is buying or selling pressure.

**INKT example**: Stock entered at $20.02, immediately crashed. Continuation hold suppressed 3 consecutive BE exits because vol_dom was 2.9-3.5x. But that volume was pure selling — every post-entry bar was red. By the time the 4th BE exit fired, price had dropped from $19.38 to $18.80. Loss deepened from -$349 to -$666.

**TLYS example**: Continuation hold suppressed TW exits at $2.75 (vol_dom=4.0x). Stock dipped to $2.73 before the exit fired. Win shrank from +$231 to +$77.

### Volume Pressure Evidence

From `VOLUME_PRESSURE_REPORT.md`:
- **INKT post-entry buy ratio: 0%** — five straight red candles after entry
- **TLYS post-entry buy ratio: 37.5%** — sellers dominating after entry

The continuation hold was reading high volume as conviction. It was actually liquidation.

### Proposed Fix

In the continuation hold logic (`trade_manager.py` ~line 2173-2209), add a direction check using the 1-minute bars that are already available via the detector:

**Rule**: Do NOT suppress exit if both conditions are true:
1. Unrealized P&L is negative (price below entry)
2. 3 or more of the last 5 one-minute bars are red (close < open)

This means: if the position is underwater AND sellers are dominating the recent bars, let the exit signal fire regardless of vol_dom.

**Pseudocode:**
```python
# After existing vol_dom calculation (~line 2179)
# Add direction check
if det and hasattr(det, 'bars_1m') and len(det.bars_1m) >= 5:
    last_5 = list(det.bars_1m)[-5:]
    red_count = sum(1 for b in last_5 if b["c"] < b["o"])
    unrealized_r = (price - t.entry) / t.r if t.r > 0 else 0

    if unrealized_r < 0 and red_count >= 3:
        return False, ""  # Don't suppress — sellers dominating while underwater
```

**Gate**: `WB_CONT_HOLD_DIRECTION_CHECK=1` (ON by default, can disable for regression testing)

### Winner Safety Check

Checking against all winners in the weekly data:
- **GITS** (+$2,748): Post-entry 4/5 green, unrealized positive → would NOT trigger. Safe ✅
- **OKLL** (+$945): Post-entry 4/5 green, unrealized positive → would NOT trigger. Safe ✅
- **BMNZ #1** (+$118): Post-entry 5/5 green, unrealized positive → would NOT trigger. Safe ✅
- **TLYS** (+$77): Post-entry 2/5 green, but unrealized was briefly positive → needs careful check ⚠️

**MUST ALSO CHECK**: All 10 winners from the 49-day backtest (SNSE, SXTC x2, BDSX, ROLR, AGPU, VERO, PMN, WHLR, TLYS) to ensure no winners are killed.

---

## Fix 2: 0.75R Max Loss Cap

**Impact**: -$1,327 net on weekly data; +$276 net on 49-day data
**Confidence**: UNDER INVESTIGATION — needs deeper analysis

### Problem

The 0.75R cap was validated as +$276 net positive on the 49-day backtest, but performed -$1,327 net negative on this week's data. The core issue:

**LUNL** (0.17M float, $13.00 stock): Dipped to -0.75R ($12.77) as normal low-float volatility noise, then recovered to $13.13 where a TW exit would have fired. The cap turned a +$464 winner into a -$821 loss. **Single-trade impact: -$1,285.**

**TRT**: The 0.75R cap exited at $6.16 (slightly above the $6.15 hard stop), which didn't register the same way as a stop_hit for cooldown purposes. This allowed a re-entry 6 minutes later — same stock, same failure, -$916 additional loss.

**FLYT**: The cap HELPED here — saved $504 by exiting at -0.75R before the full stop hit with slippage.

### Key Question

Is the 0.75R cap fundamentally flawed, or does it just need to be conditional?

**Hypothesis**: Ultra-low float stocks (< 1M shares) have wider natural price swings. A 0.75R dip is noise on a 0.17M float stock but a real failure signal on a 5M+ float stock.

### Full Data: Every Trade Affected by 0.75R Cap

**49-day backtest (Jan 2 - Mar 12):**

| Symbol | Date | Float | Old P&L | New P&L | Delta | Old Exit | New Exit |
|--------|------|-------|---------|---------|-------|----------|----------|
| ACON | Jan 08 | ~2M | -$762 | -$586 | +$176 | stop_hit | max_loss_hit |
| IOTR | Jan 22 | ~3M | -$1,067 | -$805 | +$262 | stop_hit | max_loss_hit |
| SXTP | Jan 22 | ~2M | -$1,067 | -$817 | +$250 | stop_hit | max_loss_hit |
| CYN | Jan 27 | 8.0M | -$999 | -$198 | +$801 | stop_hit | max_loss_hit |
| XHLD | Jan 27 | ~3M | -$440 | -$769 | -$329 | TW exit | max_loss_hit |
| QCLS | Mar 06 | ~4M | -$594 | -$773 | -$179 | BE exit | max_loss_hit |

**Weekly backtest (Mar 9-18):**

| Symbol | Date | Float | Old P&L | New P&L | Delta | Old Exit | New Exit |
|--------|------|-------|---------|---------|-------|----------|----------|
| FLYT | Mar 12 | 0.31M | -$1,200 | -$696 | +$504 | stop_hit | max_loss_hit |
| LUNL | Mar 17 | 0.17M | +$464 | -$821 | -$1,285 | TW exit | max_loss_hit |
| TRT #1 | Mar 17 | 4.99M | -$1,000 | -$784 | +$216 | stop_hit | max_loss_hit |
| TRT #2 | Mar 17 | 4.99M | N/A | -$916 | -$916 | N/A | re-entry bug |
| BMNZ #2 | Mar 18 | ~2M | -$411 | -$257 | +$154 | stop_hit | max_loss_hit |

### Analysis by Float Bucket

| Float Bucket | Trades | Cap Helped | Cap Hurt | Net Delta | Verdict |
|-------------|--------|------------|----------|-----------|---------|
| Ultra-low (<1M) | 2 | FLYT +$504 | LUNL -$1,285 | **-$781** | DANGEROUS — dips are noise |
| Low (1-5M) | 6 | ACON +$176, IOTR +$262, SXTP +$250, BMNZ +$154 | XHLD -$329, QCLS -$179 | **+$334** | Modestly positive |
| Mid (5M+) | 2 | CYN +$801, TRT +$216 | — | **+$1,017** | Clearly positive |
| **Total** | **10** | **+$2,363** | **-$1,793** | **+$570** | Positive overall but LUNL is an outlier |

*Note: TRT #2 (-$916) excluded from float analysis — it's a re-entry bug (Fix 3), not a cap problem.*

### The Pattern

Ultra-low float stocks (<1M shares) have order books so thin that a 0.75R price dip is one or two trades moving the price — it's noise, not a signal that the trade has failed. LUNL at 0.17M float is extreme: the entire 10-bar history before ARM had total volume of ~19,000 shares. A few hundred shares hitting the bid can push price 0.75R.

Mid-float stocks (5M+) that hit 0.75R don't come back. CYN ($3.67 entry, 8M float) and TRT ($6.26, 5M float) both continued falling after the cap exit. The cap correctly cut these losses short.

Low-float stocks (1-5M) are a middle ground. The cap helped more than it hurt (+$334 net), but XHLD and QCLS show that dip-recovery trades do exist in this range.

### Proposed Fix: Float-Tiered Max Loss Cap

Replace the flat `WB_MAX_LOSS_R=0.75` with a float-aware system:

```
Float < 1M shares:   WB_MAX_LOSS_R = OFF (use hard stop only)
Float 1-5M shares:   WB_MAX_LOSS_R = 0.85
Float > 5M shares:   WB_MAX_LOSS_R = 0.75
```

**Implementation in `trade_manager.py`:**

```python
# At entry time, when float is known from scanner data:
float_m = float(os.getenv("WB_SCANNER_FLOAT_M", "0"))
if float_m > 0 and float_m < 1.0:
    max_loss_r = None  # No early exit cap — let hard stop manage risk
elif float_m >= 1.0 and float_m <= 5.0:
    max_loss_r = float(os.getenv("WB_MAX_LOSS_R_LOW_FLOAT", "0.85"))
else:
    max_loss_r = float(os.getenv("WB_MAX_LOSS_R", "0.75"))
```

**Gate env vars:**
- `WB_MAX_LOSS_R_TIERED=1` (master switch, OFF by default)
- `WB_MAX_LOSS_R_ULTRA_LOW_FLOAT=0` (0 = OFF for <1M float)
- `WB_MAX_LOSS_R_LOW_FLOAT=0.85` (1-5M float)
- `WB_MAX_LOSS_R=0.75` (5M+ float, existing var)
- `WB_MAX_LOSS_R_FLOAT_THRESHOLD_LOW=1.0` (boundary between ultra-low and low)
- `WB_MAX_LOSS_R_FLOAT_THRESHOLD_HIGH=5.0` (boundary between low and mid)

### Winner Safety Check

**CRITICAL**: Verify no winners are killed by the tiered caps.

From the 49-day backtest winner safety data (EXIT_OPTIMIZATION_REPORT.md):

| Winner | Float | Min Unrealized | Tier Cap | Survives? |
|--------|-------|---------------|----------|-----------|
| SNSE | ? | -0.07R | ? | ✅ Safe at any cap |
| SXTC #1 | ? | -0.22R | ? | ✅ Safe at any cap |
| SXTC #2 | ? | -0.33R | ? | ✅ Safe at any cap |
| BDSX | ? | -0.32R | ? | ✅ Safe at any cap |
| ROLR | 3.78M | -0.60R | 0.85R | ✅ Safe (0.60 < 0.85) |
| AGPU | ? | -0.33R | ? | ✅ Safe at any cap |
| VERO | 1.6M | -0.42R | 0.85R | ✅ Safe (0.42 < 0.85) |
| PMN | ? | -0.14R | ? | ✅ Safe at any cap |
| WHLR | ? | -0.51R | ? | Needs float check |
| TLYS | 9.29M | -0.31R | 0.75R | ✅ Safe (0.31 < 0.75) |

**ROLR is the critical check**: 3.78M float → falls in the 1-5M tier → cap would be 0.85R. ROLR's minimum unrealized was -0.60R. **ROLR survives at 0.85R.** (Reminder: 0.50R would have killed ROLR — this is why we never go below 0.75R on any tier.)

**LUNL** (0.17M float) would be in the ultra-low tier → NO cap → hard stop only. Under old config, LUNL held through the dip and exited at +$464 via TW. With tiered system, same result. ✅

### Expected Impact (Estimated)

Applying tiered caps retroactively to all affected trades:

| Trade | Float | Flat 0.75R Delta | Tiered Delta | Improvement |
|-------|-------|-------------------|--------------|-------------|
| LUNL | 0.17M | -$1,285 | $0 (no cap) | +$1,285 |
| FLYT | 0.31M | +$504 | $0 (no cap) | -$504 |
| XHLD | ~3M | -$329 | ~-$165 (0.85R) | +$164 |
| QCLS | ~4M | -$179 | ~-$90 (0.85R) | +$89 |
| All others | — | unchanged | unchanged | $0 |

**Estimated net improvement over flat 0.75R: ~+$1,034**

The big tradeoff: we lose FLYT's $504 savings (ultra-low float, no cap) but gain back LUNL's $1,285 flip. Net positive by ~$781 on the ultra-low tier alone. The 0.85R on 1-5M tier also helps by giving dip-recovery trades like XHLD and QCLS more room.

### What Needs Testing

MacBook Pro CC implements the tiered logic. Then Mac Mini CC runs:
1. **49-day backtest** with tiered caps → compare to flat 0.75R results
2. **Weekly backtest** (Mar 9-18) with tiered caps → verify LUNL is saved
3. **VERO standalone regression** → must still be +$9,166
4. **ROLR verification** → must survive the 0.85R cap (min unrealized -0.60R)

---

## Fix 3: Re-Entry After max_loss_hit

**Impact**: -$916 (TRT took 2 trades instead of 1)
**Confidence**: HIGH — likely a bug

### Problem

When the 0.75R cap triggers a `max_loss_hit` exit, it doesn't appear to activate the same cooldown logic as a `stop_hit` exit. This allowed TRT to re-enter 6 minutes after the first loss on the same stock.

**Old config**: TRT hit the hard stop at $6.15 → `stop_hit` → cooldown prevented re-entry → 1 trade, -$1,000.
**New config**: TRT hit 0.75R cap at $6.16 → `max_loss_hit` → no cooldown → re-entered at $6.28 → another max_loss_hit → 2 trades, -$1,700.

### Proposed Fix

In the cooldown/re-entry logic, treat `max_loss_hit` exits identically to `stop_hit` exits. A loss is a loss — the exit reason shouldn't determine whether the bot can re-enter the same stock.

**Gate**: This should probably be a bug fix, not a gated feature. But if we want to be safe: `WB_MAX_LOSS_TRIGGERS_COOLDOWN=1` (ON by default).

---

## Fix 4: Block Re-Entry After Loss on Same Symbol

**Impact**: +$1,315 weekly (HIMZ #2 +$399, TRT #2 +$916); $0 impact on 49-day backtest
**Confidence**: HIGH — data is unambiguous, aligns with Ross Cameron methodology

### Problem

The detector is stateless between trades. After an exit and `_full_reset()`, all memory of the previous trade is gone. When a new IMPULSE → PULLBACK → ARM cycle forms minutes later on the same stock, the detector evaluates it independently and often ARMs again with a high score — because the micro-structure looks identical to the first attempt.

The bot isn't revenge trading emotionally. It genuinely sees what looks like a valid setup. But the stock has already shown it doesn't cooperate with this strategy today.

### How Re-Entry Currently Works

There are **two separate cooldown systems** in `trade_manager.py`:

**System 1 — Stop-hit cooldown** (lines 947-953, 1593-1595):
- Triggers ONLY on `reason == "stop_hit"` (literal string match)
- Sets a time-based cooldown of 5 min
- Does NOT trigger on `max_loss_hit`, `bearish_engulfing_exit_full`, or any other exit reason

**System 2 — Per-symbol entry counter** (lines 1132-1152, 1215-1225):
- Counts entries per symbol regardless of outcome
- After `WB_MAX_ENTRIES_PER_SYMBOL=2` entries, starts 10-min cooldown
- Doesn't care if trades won or lost — just counts entries

Neither system prevents re-entry after a loss specifically. System 1 only catches `stop_hit`. System 2 allows a second entry before cooldown kicks in.

### What The Data Shows

**49-day backtest — same-symbol re-entries:**
- SXTC Jan 08: Trade 1 +$1,058, Trade 2 +$628 → re-entry after WIN. Cascading pattern working perfectly.
- No other same-symbol re-entries exist in 28 trades.

**A "no re-entry after loss" rule has ZERO impact on 49-day results** — the only re-entry (SXTC) was after a win. No winners are blocked.

**Weekly backtest — re-entries after loss:**

| Re-entry | First Trade | Re-entry P&L | Saved by blocking |
|----------|------------|-------------|-------------------|
| HIMZ #2 | HIMZ #1 -$675 (BE) | -$399 | +$399 |
| TRT #2 | TRT #1 -$784 (0.75R) | -$916 | +$916 |
| **Total** | | | **+$1,315** |

**Weekly backtest — re-entries after win:**

| Re-entry | First Trade | Re-entry P&L | Impact if blocked |
|----------|------------|-------------|-------------------|
| BMNZ #2 | BMNZ #1 +$118 (TW) | -$257 | Would save $257 but also blocks SXTC-type cascading |

### Proposed Fix

Enable the existing `WB_NO_REENTRY_ENABLED` flag (currently OFF at line 176 of `.env`).

This flag already exists in the codebase. It blocks re-entry on a symbol after a loss, but allows re-entry after a win. This is exactly what we want:
- Blocks: HIMZ #2 (after -$675 loss) ✅
- Blocks: TRT #2 (after -$784 loss) ✅
- Allows: SXTC #2 (after +$1,058 win) ✅ — preserves cascading re-entry edge
- Allows: BMNZ #2 (after +$118 win) — still loses, but blocking would also kill SXTC cascading

### Winner Safety Check

- **SXTC cascading re-entry (Jan 08)**: First trade won +$1,058 → flag allows re-entry → second trade wins +$628. **Safe** ✅
- **All other 49-day winners**: None are re-entries. **Safe** ✅

### Why This Aligns With Ross Cameron

Ross's biggest losses come from re-entering stocks that already stopped him out. His methodology: if a stock shows you it's not working, move on. The bot should do the same. This flag was likely disabled during the old profile system or based on faulty backtest data — now that backtests are trustworthy, the data clearly supports enabling it.

---

## Implementation Plan

### Phase 1: MacBook Pro CC — Code Changes

All four fixes in one commit. Each gated by an env var (OFF by default).

1. **Fix 1 — Direction-aware continuation hold**
   - File: `trade_manager.py` (~line 2173-2209)
   - Add red bar count check before suppressing exits
   - Gate: `WB_CONT_HOLD_DIRECTION_CHECK=1`

2. **Fix 2 — Float-tiered max loss cap**
   - File: `trade_manager.py` (wherever max_loss_r is applied)
   - Read float from scanner env var, select cap by tier
   - Gates: `WB_MAX_LOSS_R_TIERED=1`, `WB_MAX_LOSS_R_ULTRA_LOW_FLOAT=0`, `WB_MAX_LOSS_R_LOW_FLOAT=0.85`

3. **Fix 3 — max_loss_hit triggers cooldown**
   - File: `trade_manager.py` (exit/cooldown logic, line 1593-1595)
   - Change `if reason == "stop_hit"` to `if reason in ("stop_hit", "max_loss_hit")`
   - Gate: `WB_MAX_LOSS_TRIGGERS_COOLDOWN=1` (ON by default — this is a bug fix)

4. **Fix 4 — No re-entry after loss on same symbol**
   - File: `.env` — set `WB_NO_REENTRY_ENABLED=1`
   - Code already exists in `trade_manager.py` (Quality Gate 5)
   - No code changes needed — just enable the existing flag

Push to repo. Add `.env` change notes for Mac Mini.

### Phase 2: Mac Mini CC — Testing

Run all tests in parallel:

1. **49-day backtest** with all four fixes ON → compare to current baseline (+$7,580)
2. **Weekly backtest** (Mar 9-18) with all four fixes ON → compare to current (-$1,411)
3. **VERO standalone regression** → must be +$9,166
4. **ROLR standalone check** → verify survives 0.85R cap

Also run each fix in isolation to measure individual contribution:
- Fix 1 only (continuation hold direction check)
- Fix 2 only (float-tiered cap)
- Fix 3 only (cooldown bug fix)
- Fix 4 only (no re-entry after loss)
- All four combined

### Expected Combined Impact

| Fix | Weekly Impact (Est.) | 49-Day Impact (Est.) |
|-----|---------------------|---------------------|
| Fix 1: Continuation hold direction | +$471 | TBD |
| Fix 2: Float-tiered cap | +$1,034 | ~+$253 |
| Fix 3: max_loss_hit cooldown bug | +$916 | $0 (no instances) |
| Fix 4: No re-entry after loss | +$1,315 | $0 (no instances) |
| **Combined estimate** | **~+$3,736** | **TBD** |

Note: Fix 3 and Fix 4 overlap on TRT — Fix 3 would have blocked TRT #2 via cooldown, and Fix 4 would have blocked it via no-re-entry-after-loss. The combined impact is not simply additive. TRT #2's $916 is counted once, not twice.

**Deduplicated estimate: ~+$2,820** (weekly -$1,411 → roughly +$1,409).

## Critical Rules

- **DO NOT** remove the max loss cap entirely — it's a net positive overall, just needs to be smarter
- **DO NOT** set any cap below 0.75R — kills ROLR (+$2,578)
- **DO NOT** disable the exhaustion filter as part of these changes
- **Gate all changes** with env vars OFF by default
- **Run VERO regression** before and after — must be +$9,166
- All changes must be tested individually AND combined before declaring them ready
- Include `.env` change report for Mac Mini CC (see below)

---

## Handoff Notes

### For MacBook Pro CC:
1. Implement Fixes 1-3 in `trade_manager.py` (Fix 4 is just an .env change)
2. Gate everything behind env vars, OFF by default
3. Commit and push to `v6-dynamic-sizing`
4. **Include a `.env` change report** in the commit (or as a separate `ENV_CHANGES_FOR_MAC_MINI.md`) listing every new env var added, with default values and recommended live values. Mac Mini CC will use this to sync their `.env`.

### For Mac Mini CC:
1. `git pull` after MacBook Pro CC pushes
2. Update `.env` per the change report from MacBook Pro CC
3. Enable all four fixes:
   - `WB_CONT_HOLD_DIRECTION_CHECK=1`
   - `WB_MAX_LOSS_R_TIERED=1`
   - `WB_MAX_LOSS_R_ULTRA_LOW_FLOAT=0`
   - `WB_MAX_LOSS_R_LOW_FLOAT=0.85`
   - `WB_MAX_LOSS_TRIGGERS_COOLDOWN=1`
   - `WB_NO_REENTRY_ENABLED=1`
4. Run tests in parallel:
   - 49-day backtest (all fixes ON) → compare to +$7,580 baseline
   - Weekly backtest Mar 9-18 (all fixes ON) → compare to -$1,411
   - VERO standalone regression → must be +$9,166
   - ROLR standalone → must survive 0.85R cap
   - Each fix in isolation + all combined
5. Push results report to repo

---

*Directive finalized: 2026-03-18 | Status: READY FOR IMPLEMENTATION*
