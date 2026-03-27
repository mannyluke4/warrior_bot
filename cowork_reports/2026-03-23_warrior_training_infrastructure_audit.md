# Warrior Training vs Bot Infrastructure — Full Audit

**Date:** 2026-03-23
**Source:** `ross_full_training_vs_bot_analysis.md` (commit 82e3bd5, v6 branch)
**Audited against:** Current `main` branch (post Ross Exit V2, post scanner alignment)

This audit maps every gap and recommendation from the Warrior Trading report against the current codebase, marking what's been addressed, what's still open, and what's changed in priority.

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ DONE | Fully implemented and live/testable |
| 🔧 IN PROGRESS | Code exists, being refined or tested |
| ⚠️ PARTIALLY ADDRESSED | Some coverage but gaps remain |
| ❌ NOT STARTED | No implementation yet |
| ➖ DEFERRED | Intentionally deprioritized or handled manually |

---

## Section 1: Stock Selection — The 5 Criteria

| # | Criterion | Ross's Number | Current Bot | Status | Notes |
|---|-----------|---------------|-------------|--------|-------|
| 1 | Price range | $2–$20 | `WB_MIN_PRICE=2.00`, `WB_MAX_PRICE=20.00` | ✅ DONE | Unchanged, exact match |
| 2 | Day gain ≥10% | ≥10% | `WB_MIN_GAP_PCT=10` | ✅ DONE | **IMPROVED since report.** Was 5% in scanner. Now 10% aligned to Ross Pillar standard |
| 3 | RVOL ≥5x | ≥5x | `WB_MIN_REL_VOLUME=2.0` | ⚠️ GAP | Report said 1.5x scanner + 2.0x pillar. Scanner now 2.0x, but still below Ross's 5x. No pillar RVOL gate found in .env. See analysis below. |
| 4 | News catalyst | Strongly preferred | Not checked | ➖ DEFERRED | We use gap% + RVOL as proxy. No change. Hard to automate. |
| 5 | Float <20M | <20M | `WB_MAX_FLOAT=20`, preferred <10M | ✅ DONE | Unchanged, good match |

### RVOL Deep Dive

The report flagged this as the #1 gap. Current state:

- Scanner: `WB_MIN_REL_VOLUME=2.0` (improved from 1.5x)
- Pillar gates: `WB_PILLAR_GATES_ENABLED=1` but no `WB_PILLAR_MIN_RVOL` found in `.env`
- Ross requires 5x minimum

**Assessment:** This is still a meaningful gap but needs careful handling. Raising to 5x could eliminate half our candidates. The right move is probably testing 3x as a middle ground in the YTD runner to see the trade-off between trade count and quality. Not urgent for the CUC fix work, but worth queuing for a follow-up backtest.

---

## Section 2: Entry Pattern

| Element | Ross | Bot | Status |
|---------|------|-----|--------|
| Micro pullback detection | Impulse → pullback → first candle makes new high | `micro_pullback.py` state machine: IDLE → IMPULSE → PULLBACK → ARM → trigger on tick | ✅ DONE |
| Stop at pullback low | Low of red candle(s) | Stop = pattern low | ✅ DONE |
| Wave 1 + Wave 2 | 2 waves then cautious | `WB_MAX_ENTRIES_PER_SYMBOL=2` | ✅ DONE |
| 30-second health check | "If not working in 30 seconds, something is wrong" | `WB_BAIL_TIMER_MINUTES=5` | ⚠️ GENEROUS | 5 min vs 30 sec. The bail timer covers the concept but is 10x slower than Ross's instinct. |
| Starter size at 25% | Must profit $1K before full size | `WB_WARMUP_SIZE_PCT=25`, threshold $500 | ✅ DONE | Threshold scaled to account size |

---

## Section 3: Exit Framework — The Big One

This is where the most change has happened since the report. The Ross Exit system (`ross_exit.py`) was built specifically to address the exit gaps.

### Report's Tier 1 Recommendations (Highest Impact)

| # | Recommendation | Status | Implementation | Notes |
|---|---------------|--------|----------------|-------|
| 1 | Move BE/TW from 10s → 1m bars | ✅ DONE | `WB_ROSS_EXIT_ENABLED=1` replaces 10s BE/TW with 1m candle signals | Currently OFF in live (V2 showed -$10,799 vs baseline). V3 CUC fix in progress. |
| 2 | Implement CUC as 1m confirmed exit | ✅ DONE | `ross_cuc_exit` in ross_exit.py. Requires ≥2 consecutive HH before lower-low fires. | 9 fires in YTD, but too aggressive. V3 adds floor-R and min-trade-bars gates. |
| 3 | Graduated partial exits (50% warning, 50% CUC) | ✅ DONE | `partial_50` on doji/topping tail, `full_100` on CUC/gravestone/shooting star | The framework is built. Doji fires 50% partial, then CUC/SS handles the rest. |
| 4 | Replace squeeze fixed-R targets with candle exits | ⚠️ BLOCKED | When `WB_ROSS_EXIT_ENABLED=1`, `sq_target_hit` is disabled in simulate.py. But V2 results show this costs $12,832. | This is the core tension. We've committed to candle exits over fixed targets, but need better candle exits (V3 CUC fix) before the numbers work. |

### Report's Tier 2 Recommendations

| # | Recommendation | Status | Implementation | Notes |
|---|---------------|--------|----------------|-------|
| 5 | MACD negative → hard exit | ✅ DONE | `ross_macd_cross` in ross_exit.py. MACD histogram < 0 → full exit. Softens to partial_50 above 5R. | Needs ~35 bars warmup. Works immediately in YTD backtest. |
| 6 | 20 EMA break → hard exit | ✅ DONE | `ross_ema20_break` in ross_exit.py. 1m close below 20 EMA → full exit. | Active when ross exit is enabled. |
| 7 | 9 EMA extension → partial exit (sell 50%) | ❌ NOT STARTED | No 9 EMA tracker in ross_exit.py. Only EMA20 and EMA12/26 for MACD. | This is Ross's "yellow light" — extended above 9 EMA means sell half. Not yet built. |
| 8 | Entry time cutoff (no entries after 11/12) | ➖ MANUAL | `WB_ARM_EARLIEST_HOUR_ET=7` sets floor but no ceiling. No `WB_ARM_LATEST_HOUR_ET`. | Being handled manually per user. Backtest window is 07:00–12:00 anyway. |

### Report's Tier 3 Recommendations

| # | Recommendation | Status | Implementation | Notes |
|---|---------------|--------|----------------|-------|
| 9 | Raise RVOL gate to ≥3x | ❌ NOT STARTED | Still at 2.0x | See RVOL analysis above |
| 10 | Enable rank-grace | ⚠️ BUILT, NOT TESTED | `WB_RANK_GRACE_ENABLED=0`. Code exists in trade_manager.py and run_megatest.py. | Never tested in YTD backtest. Could be a quick win. |
| 11 | Structural trail (low of last green 1m candle) | ✅ DONE | `WB_ROSS_STRUCTURAL_TRAIL=1` in ross_exit.py. Trail ratchets to low of last green bar, floored at entry + $0.01. | Active when ross exit is enabled. |
| 12 | Revise stall timer to use candle signals | ⚠️ PARTIALLY | Ross exit replaces the old stall/BE/TW system when enabled, but bail timer still uses simple time check. | Bail timer is independent of ross exit. Could be improved to check for negative candle signals instead. |

---

## Section 4: Indicators

| Indicator | Ross's Use | Bot Status | Notes |
|-----------|-----------|------------|-------|
| 9 EMA | First support; extended = sell half | ❌ NOT IN EXIT SYSTEM | Used in detector for entry quality, but NOT in ross_exit.py as an exit signal. Gap #7 from report still open. |
| 20 EMA | Second support; break = exit | ✅ DONE | `ross_ema20_break` backstop in ross_exit.py |
| 200 EMA | Major S/R | ⚠️ SCANNER ONLY | `stock_filter.py` uses EMA200 for scanner filtering. Not used for entry/exit decisions. |
| VWAP | Above = bullish; below = exit | ✅ DONE | `ross_vwap_break` backstop in ross_exit.py. Also used in squeeze exit. |
| MACD | Diverging = trade; converging = exit | ✅ DONE | Entry: `WB_MACD_HARD_GATE=1`. Exit: `ross_macd_cross` backstop. Both sides covered. |
| Volume bars | Confirm buying surge | ✅ DONE | Squeeze detector uses volume explosion (3x avg) |

---

## Section 5: Risk Management

| Rule | Ross | Bot | Status | Issue? |
|------|------|-----|--------|--------|
| Daily goal | $5,000 (scales to account) | `WB_DAILY_GOAL=500` | ✅ | Scaled appropriately |
| Max daily loss = daily goal | Equal | `WB_MAX_DAILY_LOSS=3000` vs `WB_DAILY_GOAL=500` | ⚠️ MISMATCH | **Loss limit is 6x the goal.** Ross says never lose more in one day than you make in one day. Current config allows losing $3,000 on a $500 goal day. This should be tightened. |
| Give-back 50% hard stop | Walk away at 50% of peak | `WB_GIVEBACK_HARD_PCT=50` | ✅ | Exact match |
| Give-back 20% warning | Halve risk | `WB_GIVEBACK_WARN_PCT=20` | ✅ | Exact match |
| Max consecutive losses | 3 implied | `WB_MAX_CONSECUTIVE_LOSSES=3` | ✅ | Exact match |
| Starter size at 25% | Until +$1K | `WB_WARMUP_SIZE_PCT=25`, threshold $500 | ✅ | Scaled to account |

### Daily Loss Limit Mismatch

This is worth flagging. Ross's rule is symmetric: daily goal = max daily loss. With `WB_DAILY_GOAL=500` and `WB_MAX_DAILY_LOSS=3000`, the bot can lose 6 days of gains in one bad day. In the YTD backtest, the runner uses `WB_MAX_DAILY_LOSS=1500` which is 3x the goal — still above Ross's 1:1, but more conservative than the live .env.

**Recommendation:** Align `WB_MAX_DAILY_LOSS` closer to `WB_DAILY_GOAL`. Consider $750-$1000 as a compromise (1.5-2x goal rather than 6x).

---

## Section 6: What's Been Addressed Since the Report

The report was written against commit `82e3bd5` on `v6-dynamic-sizing`. Since then:

1. **Branch consolidation:** v6 merged into main (v6 was 22 commits behind, 0 unique). All work now on `main`.

2. **Ross Exit system built and tested:** The entire Tier 1 + most of Tier 2 exit recommendations are implemented in `ross_exit.py`. Signal hierarchy: doji/topping tail (50% partial) → gravestone/shooting star/CUC (100%) → MACD/EMA20/VWAP backstops.

3. **Scanner alignment completed:** `WB_MIN_GAP_PCT` raised from 5 to 10 (Ross Pillar), `WB_MIN_REL_VOLUME` raised from 1.5 to 2.0, scanners aligned between live and sim.

4. **YTD backtest infrastructure:** `run_ytd_v2_backtest.py` runs 55-day A/B comparisons. Baseline +$25,709 established.

5. **Pillar gates live:** `WB_PILLAR_GATES_ENABLED=1` enforces Ross's entry-time criteria.

6. **MP gated off by default:** `WB_MP_ENABLED=0` (since 2026-03-22). Squeeze is now primary.

---

## Section 7: Remaining Gaps — Priority Ranked

### Priority A: Active Work (directives in progress)

| Gap | What | Directive |
|-----|------|-----------|
| CUC too aggressive | V3 adds floor-R + min-trade-bars gates | `DIRECTIVE_ROSS_EXIT_V3_CUC_FIX.md` |
| Live bot stale code | Mac Mini switched to main, audit pending | `DIRECTIVE_LIVE_BOT_AUDIT_2026_03_23.md` |

### Priority B: Next Up (after V3 CUC fix results)

| Gap | What | Est. Effort | Expected Impact |
|-----|------|-------------|-----------------|
| **9 EMA extension warning** | Add 9 EMA tracker to ross_exit.py, fire partial_50 when price extended above it | ~50 lines | Ross's #1 "yellow light". Could improve partial timing on runners. |
| **Daily loss limit mismatch** | Tighten `WB_MAX_DAILY_LOSS` from 3000 to ~750 | Config change | Prevents catastrophic daily losses per Ross's 1:1 rule |
| **RVOL threshold testing** | Test 3x and 5x RVOL in YTD runner | YTD run | Higher quality stock selection, fewer bad trades |
| **Rank-grace testing** | Enable `WB_RANK_GRACE_ENABLED=1`, test in YTD runner | YTD run | Ross's "collective obviousness" — focus on #1 stock |

### Priority C: Research / Future

| Gap | What | Notes |
|-----|------|-------|
| 200 EMA as S/R | Add to entry scoring or exit awareness | Low priority — scanner already filters below 200 EMA |
| Level 2 / Tape reading | Live bot has l2_bearish signals, need to verify wiring | Can't backtest; live verification only |
| Bail timer tightening | 5 min → 2-3 min, or signal-based | Minor improvement, bail timer rarely fires in YTD data |
| News catalyst detection | Integrate news API for real-time catalyst confirmation | Complex, possibly out of scope |

---

## Section 8: Scorecard Summary

**Report identified 12 recommendations across 3 tiers.**

| Tier | Total | Done | In Progress | Open | Deferred |
|------|-------|------|-------------|------|----------|
| Tier 1 (Highest Impact) | 4 | 3 | 1 (CUC refinement) | 0 | 0 |
| Tier 2 (High Impact) | 4 | 2 | 0 | 1 (9 EMA) | 1 (time cutoff — manual) |
| Tier 3 (Refinement) | 4 | 1 | 0 | 2 (RVOL, rank-grace) | 1 (stall timer — partially done) |
| **Total** | **12** | **6 (50%)** | **1 (8%)** | **3 (25%)** | **2 (17%)** |

The bot has addressed 50% of the original recommendations fully, with another 8% actively being refined. The biggest remaining gaps are the 9 EMA extension signal and RVOL threshold — both queued for after V3 CUC fix results come in.

---

*Audit compiled 2026-03-23 by Cowork against current main branch. Cross-referenced: ross_exit.py, trade_manager.py, .env, bot.py, simulate.py, run_ytd_v2_backtest.py*
