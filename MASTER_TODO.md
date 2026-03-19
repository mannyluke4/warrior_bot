# Warrior Bot — Master Task Tracker
## Last Updated: 2026-03-19

This document tracks ALL open work items across every strategy and system. Updated by Cowork after each session. Lives in the repo so nothing gets lost.

---

## 🔴 CRITICAL — Scanner Alignment (Blocks Everything)

The live scanner has found ZERO usable stocks across 3 trading days. The live and backtest scanners use completely different data pipelines and criteria. Until they're aligned, we can't trust backtests OR trade live.

**Directive**: `DIRECTIVE_SCANNER_ALIGNMENT.md` — IN PROGRESS

| Task | Status | Owner | Notes |
|------|--------|-------|-------|
| **Phase 1: Fix `live_scanner.py`** | **✅ CODE PUSHED** | CC MBP | Commit `e9cbb88`. Thresholds, RVOL, ranking, watchlist format updated |
| **Phase 2: Align `scanner_sim.py`** | **✅ CODE PUSHED** | CC MBP | Same commit. Aligned to unified criteria |
| **Phase 3: Regenerate scanner data** | **DIRECTIVE SENT** | CC MM | `DIRECTIVE_MAC_MINI_SCANNER_VALIDATE.md`. Re-run scanner_sim for all 49 dates |
| **Phase 4: Align batch runner filters** | **✅ CODE PUSHED** | CC MBP | Same commit. RVOL≥2x, min PM vol 50K, gap≥10% |
| **Phase 5: Validate + re-run 49-day backtest** | **DIRECTIVE SENT** | CC MM | Verify VERO/ROLR/SXTC/GITS still selected. Full backtest with new data |
| Connect `live_scanner.py` to `daily_run.sh` | **NOT STARTED** | CC MM | After Phase 5 validates. Start alongside `bot.py`, disable `WB_ENABLE_DYNAMIC_SCANNER` |
| Verify Databento streaming costs | **NOT STARTED** | Manny | Usage-based pricing — need to confirm acceptable |
| Test: would ARTL have been found? | **IN DIRECTIVE** | CC MM | Part of Phase 5 validation. Generate scanner data for Mar 18 |

---

## 🟡 Strategy 1: Micro Pullback (Current Strategy)

### Completed (2026-03-18)
- [x] Fix 1: Direction-aware continuation hold (+$317) — `WB_CONT_HOLD_DIRECTION_CHECK=1`
- [x] Fix 2: Float-tiered max loss cap (+$937) — `WB_MAX_LOSS_R_TIERED=1`
- [x] Fix 3: max_loss_hit triggers cooldown (+$916) — `WB_MAX_LOSS_TRIGGERS_COOLDOWN=1`
- [x] Fix 4: No re-entry after loss (+$1,315) — `WB_NO_REENTRY_ENABLED=1`
- [x] Fix 5: TW profit gate at 1.5R (+$12,619) — `WB_TW_MIN_PROFIT_R=1.5`
- [x] Float data propagation fix (+$937)
- [x] 49-day backtest validated: +$19,072 (+63.6%), profit factor 3.38

### Open — Refinement Tasks

| Task | Status | Priority | Est. Impact | Notes |
|------|--------|----------|-------------|-------|
| **Missed re-entries after winning exits** | **ANALYZED — NOT A MP FIX** | LOW (for MP) | Belongs to Strategies 2-5 | Verbose sim analysis (2026-03-19): VERO goes silent 07:37-09:47 after exit, ROLR silent 08:44-10:50. Cause: MACD bearish + trend_down range check. These post-exit continuations are curl/extension patterns (Strategy 5), not micro pullbacks. The MP detector is correct to not re-arm. |
| **Feb-Mar bleed / loser avoidance** | **LIKELY RESOLVED BY SCANNER** | MEDIUM | Pending full YTD scan | Scanner alignment reduced candidates from 94-108/day to 0-2/day. Key dates backtest: 9 trades, 56% win rate, PF 7.66. Full YTD scan (55 days) running overnight will confirm if bleed is eliminated. |
| **Thin stock / min liquidity filter** | **✅ CODE PUSHED — THRESHOLD TBD** | HIGH | Saves ~$1,800 | `WB_MIN_SESSION_VOLUME` gate implemented (commit `df65a73`). Default 10K doesn't block FUTG (72K bar vol despite 312 ticks). 100K blocks FUTG, all winners unaffected. **ACTION: Validate threshold against full 55-day YTD scan before enabling in live.** Need more stocks to confirm 100K doesn't produce false positives. |
| **Trade setup type tagging** | **✅ CODE PUSHED** | HIGH | Prep for multi-strategy | `setup_type` field on OpenTrade/PendingEntry (commit `df65a73`). All trades tagged `"micro_pullback"`. Ready for future strategy modules. |
| **Post-windfall position sizing** | **NOT STARTED** | MEDIUM | Reduce drawdown | After VERO (+$17.5K), account jumps to $55K and 2.5% risk = $1,375/trade. Subsequent losses are amplified. Consider: risk cap, slower ramp, or fixed risk for N days after big win. |
| **Dynamic sizing in batch runner** | **NOTED** | LOW | Better backtest accuracy | Batch runner uses 2.5% of equity (compounding). Live bot uses flat $1,000 (`WB_RISK_DOLLARS`). These will diverge. Need to decide: does live bot also scale with equity? |

---

## 🟢 Strategy 2: Squeeze / Breakout Entry (V2 IMPLEMENTED — Validation Phase)

Squeeze/breakout detector captures first-leg momentum moves that MP misses. V1 implemented 2026-03-19, parabolic mode added same day, V2 conflict fixes (HOD gate, separate counters, dollar cap) landed same day.

**Files**: `squeeze_detector.py` (~420 lines), `simulate.py` (+340 lines exit/wiring)
**Design Doc**: `STRATEGY_2_SQUEEZE_DESIGN.md` — All 5 decisions locked
**Directives**: `DIRECTIVE_SQUEEZE_V1.md`, `DIRECTIVE_SQUEEZE_PARABOLIC.md`, `DIRECTIVE_SQUEEZE_FIXES_V2.md`

### V2 Results (4-stock validation, squeeze + parabolic + all fixes)
| Stock | MP-Only | Squeeze V2 | Delta | Trades |
|-------|---------|-----------|-------|--------|
| ARTL | +$922 | +$5,275 | +$4,353 | 2 squeeze (1W 1L) |
| VERO | +$18,583 | +$20,922 | +$2,339 | 1 MP + 3 squeeze (4W 0L) |
| ROLR | +$6,444 | +$16,195 | +$9,751 | 2 squeeze + 1 MP (3W 0L) |
| SXTC | +$2,213 | +$2,213 | $0 | No squeeze activity |
| **Total** | **$28,162** | **$44,605** | **+$16,443 (+58%)** | |

### Task Status
| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Define squeeze entry criteria | **✅ DONE** | — | Volume explosion (3x avg) + VWAP + green bar + body % + key level break |
| Design squeeze detector module | **✅ DONE** | — | IDLE → PRIMED → ARMED state machine, same interface as MP |
| Define squeeze exit rules | **✅ DONE** | — | Trail (1.5R), time stop (5 bars), VWAP loss, core+runner partial (75/25 at 2R) |
| Implement squeeze_detector.py | **✅ DONE** | — | All env vars gated, probe sizing, max attempts, PM confidence scoring |
| Wire into simulate.py | **✅ DONE** | — | Dual detector feed, squeeze priority, conflict resolution, TW/BE skip |
| Parabolic mode | **✅ DONE** | — | Level-based stop when consolidation R > cap. ARTL went from 0 entries to +$6,963 first trade |
| V2 Fix 1: HOD gate | **✅ DONE** | — | `WB_SQ_NEW_HOD_REQUIRED=1` — bar must make new session high. Blocks VERO bounce entry |
| V2 Fix 2: Separate entry counters | **✅ DONE** | — | Squeeze trades don't consume MP's max_entries slots. ROLR gets both strategies |
| V2 Fix 3: Dollar loss cap | **✅ DONE** | — | `WB_SQ_MAX_LOSS_DOLLARS=500` — catches gap-throughs on tight parabolic stops |
| Backtest regression | **✅ PASS** | — | VERO +$18,583, ROLR +$6,444 (squeeze OFF = unchanged) |
| **Add squeeze env vars to YTD runner** | **NOT STARTED** | **HIGH** | `run_ytd_v2_backtest.py` needs squeeze V2 env vars in ENV_BASE + setup_type parsing |
| **Run full 55-day YTD with squeeze ON** | **NOT STARTED** | **HIGH** | The definitive test — how many squeeze opportunities across full dataset |
| Port squeeze exits to trade_manager.py | **NOT STARTED** | LOW | For live bot. SimTradeManager has the logic — port after backtest validation |

### Squeeze V2 Env Vars (all gated, defaults = OFF or conservative)
```
WB_SQUEEZE_ENABLED=1           # Master gate (OFF by default)
WB_SQ_VOL_MULT=3.0             # Min volume multiple to trigger PRIMED
WB_SQ_MIN_BAR_VOL=50000        # Absolute min bar volume
WB_SQ_MIN_BODY_PCT=1.5         # Min candle body % for squeeze bar
WB_SQ_PRIME_BARS=3             # Bars to wait for level break after PRIMED
WB_SQ_MAX_R=0.80               # Max R for consolidation-based stop
WB_SQ_LEVEL_PRIORITY=pm_high,whole_dollar,pdh
WB_SQ_PROBE_SIZE_MULT=0.5      # Half size on first attempt
WB_SQ_MAX_ATTEMPTS=3           # Per-symbol squeeze attempt limit
WB_SQ_PARA_ENABLED=1           # Parabolic mode (level-based stop fallback)
WB_SQ_PARA_STOP_OFFSET=0.10    # Stop = breakout_level - offset
WB_SQ_PARA_TRAIL_R=1.0         # Tighter trail for parabolic (vs 1.5R normal)
WB_SQ_NEW_HOD_REQUIRED=1       # Bar must be at/making new session HOD
WB_SQ_MAX_LOSS_DOLLARS=500     # Absolute dollar cap on squeeze losses
WB_SQ_TARGET_R=2.0             # Core exit target
WB_SQ_CORE_PCT=75              # Core vs runner split
WB_SQ_RUNNER_TRAIL_R=2.5       # Runner trail distance
WB_SQ_STALL_BARS=5             # Time stop (bars without progress)
WB_SQ_VWAP_EXIT=1              # Exit on VWAP loss
WB_SQ_PM_CONFIDENCE=1          # PM bull flag adds to score
```

---

## 🟡 Strategy 3: Dip-Buy Into Support (NEW — Not Yet Built)

Ross bought ARTL's dip from $8.20 to $5.63 at $6.73 and rode the bounce to $7.60 (+$5,000). This is a countertrend buy — fundamentally different from pullback-on-trend.

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Define dip-buy entry criteria | **NOT STARTED** | MEDIUM | Manny to provide breakdown. Key elements: sharp pullback after squeeze, support level (VWAP, whole dollar), bounce confirmation |
| Design dip-buy detector module | **NOT STARTED** | MEDIUM | Needs concept of "support" — VWAP, prior day close, whole/half dollars |
| Define dip-buy exit rules | **NOT STARTED** | MEDIUM | Likely tighter stops than pullback trades |
| Implement and backtest | **NOT STARTED** | — | After design approved |

---

## 🟡 Strategy 4: VWAP Reclaim (NEW — Not Yet Built)

Ross trades "the first 1-minute candle to make a new high" after price crosses back above VWAP. This is a specific entry signal the bot doesn't have.

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Define VWAP reclaim criteria | **NOT STARTED** | MEDIUM | Manny to provide breakdown. Key: price crosses above VWAP from below, first candle to make new high, volume confirmation |
| Design VWAP reclaim module | **NOT STARTED** | MEDIUM | May be simpler than squeeze/dip-buy — specific trigger condition |
| Define exit rules | **NOT STARTED** | MEDIUM | |
| Implement and backtest | **NOT STARTED** | — | After design approved |

---

## 🟡 Strategy 5: Curl / Extension (NEW — Not Yet Built)

Rounded bottom approach toward prior HOD. Ross uses this for continuation trades later in the session.

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Define curl entry criteria | **NOT STARTED** | LOW | Lower priority — session trade, less common |
| Design and implement | **NOT STARTED** | LOW | |

---

## 🔵 Architecture: Strategy Profile System

The framework that allows multiple strategy modules to coexist without conflicting.

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Design strategy profile architecture | **NOT STARTED** | HIGH | Each module: own state machine, own entry/exit rules, own reset logic. A TW reset in pullback doesn't affect squeeze module. Trade manager routes to correct module's exit rules. |
| Define trade manager routing logic | **NOT STARTED** | HIGH | When 2 modules want to enter same stock, who wins? When in a position, which module's exits apply? |
| Define shared vs module-specific settings | **NOT STARTED** | MEDIUM | Some settings (risk, notional cap) are global. Some (TW grace, R thresholds) are per-strategy. |
| Implement framework | **NOT STARTED** | — | After design approved, before adding new strategies |

---

## 🔵 Architecture: Detector Reset Tuning

The "extended candles" reset and TW resets during pullback phase are too aggressive on squeeze stocks. 9 resets in 45 minutes on ARTL.

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Review "extended candles" reset threshold | **NOT STARTED** | MEDIUM | Currently resets after 5-6 green candles. On a squeeze, that IS the move. May need to be RVOL-aware (disable for >10x RVOL stocks). |
| Review TW resets during PULLBACK phase | **NOT STARTED** | MEDIUM | TW killed 4 potential ARM formations on ARTL during 08:19-08:26. Should TW reset be softer during active pullback detection? |
| This may be resolved by strategy profiles | **NOTED** | — | If squeeze module ignores these resets, the problem goes away for squeeze stocks. Pullback detector may still benefit from softer resets. |

---

## 🟢 Infrastructure / Ops

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Sync tick cache to Mac Mini | **PARTIAL** | MEDIUM | 49-day backtest ran, but not all pairs may be cached. Rsync full `tick_cache/` to Mac Mini for complete deterministic replay. |
| Update CLAUDE.md with new regression targets | **NOT STARTED** | LOW | VERO now +$18,583 (was +$9,166). ROLR now +$6,444 (was +$3,242). |
| Update COWORK_HANDOFF.md with today's work | **NOT STARTED** | LOW | Current state, new fixes, new architecture direction. |
| Ross Cameron video analysis | **NOTED** | WHEN POSSIBLE | Manny wants to compare bot entries vs Ross's recaps. Can't watch videos — Manny would need to provide timestamps/summaries for key trades. |

---

## 📊 Current Performance Baseline

| Metric | Value | Date |
|--------|-------|------|
| 49-day backtest P&L | **+$19,072 (+63.6%)** | 2026-03-18 |
| Profit factor | **3.38** | 2026-03-18 |
| VERO regression | **+$18,583** | 2026-03-18 |
| ROLR regression | **+$6,444** | 2026-03-18 |
| Live trades taken | 1 (NUAI -$542) | 2026-03-18 |
| Live scanner status | **BROKEN — 0 stocks found in 3 days** | 2026-03-19 |

---

*This file is the single source of truth for all open work. Updated by Cowork after each session.*
