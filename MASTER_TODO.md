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
| **Thin stock / min liquidity filter** | **DIRECTIVE SENT** | HIGH | Saves ~$1,800 | FUTG (312 ticks, -$1,538) and INKT (312 ticks, -$349) were both illiquid. `WB_MIN_SESSION_VOLUME` gate at ARM time. See `DIRECTIVE_MP_REFINEMENTS_V1.md`. |
| **Trade setup type tagging** | **DIRECTIVE SENT** | HIGH | Prep for multi-strategy | `setup_type` field on OpenTrade for filtering backtests per strategy. See `DIRECTIVE_MP_REFINEMENTS_V1.md`. |
| **Post-windfall position sizing** | **NOT STARTED** | MEDIUM | Reduce drawdown | After VERO (+$17.5K), account jumps to $55K and 2.5% risk = $1,375/trade. Subsequent losses are amplified. Consider: risk cap, slower ramp, or fixed risk for N days after big win. |
| **Dynamic sizing in batch runner** | **NOTED** | LOW | Better backtest accuracy | Batch runner uses 2.5% of equity (compounding). Live bot uses flat $1,000 (`WB_RISK_DOLLARS`). These will diverge. Need to decide: does live bot also scale with equity? |

---

## 🟡 Strategy 2: Squeeze / Breakout Entry (NEW — Not Yet Built)

Ross's primary edge on ARTL. Enters on the first leg of a news-driven momentum move, not the pullback. Would have captured $1,500 on ARTL's $4.59→$8.19 initial squeeze.

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Define squeeze entry criteria | **NOT STARTED** | HIGH | Manny to provide detailed breakdown of the setup. Key elements: news catalyst, volume explosion, whole-dollar break, above VWAP |
| Design squeeze detector module | **NOT STARTED** | HIGH | Independent state machine, coexists with pullback detector |
| Define squeeze exit rules | **NOT STARTED** | HIGH | May differ from pullback exits — squeezes are faster, more volatile |
| Implement and backtest | **NOT STARTED** | — | After design approved |

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
