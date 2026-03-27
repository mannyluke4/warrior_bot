# Warrior Bot — Master Task Tracker
## Last Updated: 2026-03-27 (Cowork session — EEIQ comparison, execution gap analysis)

This document tracks ALL open work items across every strategy and system. Updated by Cowork after each session. Lives in the repo so nothing gets lost.

---

## 🟢 COMPLETED — Jan 2025 Missed Stocks Backtest

**Result: Scanner is confirmed as the #1 bottleneck.** If the scanner had found all of Ross's January stocks, the bot would have made **+$42,818** vs ~$5,543 actual — a **7.7x multiplier**.

Key findings: 88% stock-level profitability, SQ is the only strategy that fires, 18-22% capture rate on Ross's P&L, bot beats Ross on all 3 of his losses. 10 tickers had no Databento data (likely OTC). 6 had data but 0 trades (large float, MACD gate, no ARM).

**Report:** `cowork_reports/2025-01_missed_stocks_backtest_results.md`

---

## 🟢 COMPLETED — Ross Exit V3 CUC Fix

CC implemented both CUC gates and ran the 4-config YTD comparison. **Result: CUC tuning alone cannot close the gap.** Best config (MinBars=5) improved V2 by +$2,049 but still -$8,750 vs baseline. The sq_target_hit architecture issue dominates (-$12,832).

**Code changes (merged):** `WB_ROSS_CUC_FLOOR_R` and `WB_ROSS_CUC_MIN_TRADE_BARS` in ross_exit.py
**Report:** `cowork_reports/2026-03-23_v3_cuc_comparison.md`
**Decision:** Phase 2 signal-at-level partials deferred. Focus shifts to scanner coverage (missed stocks backtest).

---

## 🔴 #1 PRIORITY — Scanner Coverage Improvement

The January 2025 missed stocks backtest proved the scanner is the highest-leverage fix. The bot found 7.4% of Ross's tickers (5/68) and left ~$37K on the table in one month. The bot IS profitable on these stocks — it just never sees them.

**Root causes of scanner misses (29 missed opportunities, Jan 2025):**

| Category | Count | % | Fix Approach |
|----------|-------|---|-------------|
| Scanner never found stock | 13 | 45% | Broader criteria, continuous rescan, news feed |
| Found but bot didn't trade | 5 | 17% | Already mostly fixed by SQ V2 (post-Jan addition) |
| Found AND traded (exit gap) | 3 | 10% | Ross exit refinement (in progress) |
| Sympathy/thematic plays | 3 | 10% | Sector momentum tracking (hard to automate) |
| Mid-morning discovery | 2 | 7% | Continuous intraday rescan |
| Unknown float (no float data) | 2 | 7% | Float data fallback / allow unknown-float with gates |
| Scanner timing (pre-7:15 move) | 1 | 3% | Earlier first scan or streaming mode |

**Scanner Gap Analysis COMPLETED (2026-03-23):**
Per-stock analysis of every profitable missed stock. 5 root cause categories: float too high (4 stocks, +$1,379), unknown float (4 stocks, +$12,178), not in data universe (10 stocks, no data), failed scanner gates (13 stocks, +$13,445), structural (3 stocks, $0).
**Report:** `cowork_reports/2026-03-23_scanner_gap_analysis.md`

**Phase 1 tasks (scanner architecture):**

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Analyze WHY 13 stocks weren't found | **COMPLETED** | **P0** | Report: `cowork_reports/2026-03-23_scanner_gap_analysis.md` |
| Enable unknown-float stock trading | **COMPLETED** | **P0** | Done 2026-03-23. WB_ALLOW_UNKNOWN_FLOAT=1 in .env; gate logic in run_ytd_v2_backtest.py |
| Fix continuous rescan (0 finds in Jan) | **✅ COMPLETED** | **P0** | Commit `6a91afe`. Cumulative 4AM→checkpoint volume, RVOL inline calc, gap 5% for RVOL≥10x. |
| Rename "unknown-float" terminology (was "Profile X") | **COMPLETED** | **P0** | Done 2026-03-23. All Python files, .env, docs updated. |
| Research: alt data feeds + float sources | **✅ COMPLETED** | **P1** | Perplexity deep dive done 2026-03-23. See findings below. |
| Add SEC EDGAR as Tier 5 float fallback | **✅ COMPLETED** | **P1** | Commit `6a91afe`. In both live_scanner.py and scanner_sim.py. CIK map + XBRL API. |
| Add float cache invalidation (clear stale Nones) | **✅ COMPLETED** | **P1** | Commit `6a91afe`. Clears None entries on load, forces re-lookup through full chain. |
| Add Alpha Vantage free tier as Tier 6 float | **✅ COMPLETED** | **P2** | Commit `6a91afe`. `WB_ALPHA_VANTAGE_API_KEY` env var (empty = disabled). 25 calls/day. |
| **Jan 2025 vs Jan 2026 comparison** | **DIRECTIVE WRITTEN** | **P0** | `DIRECTIVE_JAN_COMPARISON_V1.md`. Re-run scanner_sim for Jan 2025 with fixes, then backtest both months side-by-side. Validates all scanner + exit changes. |
| OTC coverage (Polygon + IBKR) | **DEFERRED** | **P3** | Polygon $199/mo + IBKR $18/mo. Manny declined for now. Would cover ~10 missing OTC tickers. Revisit after free-tier improvements are maximized. |
| News feed integration (catalyst detection) | **NOT STARTED** | **P2** | Ross's edge: news at 7:00 AM → scanner alert. Bot: gap-only |
| Sector/sympathy tracking | **NOT STARTED** | **P3** | EVAC (GLP-1 sympathy), BTCT (crypto theme) — hard to automate |

**Perplexity Research Findings (2026-03-23):**
- **Trade Ideas**: No programmatic API — browser-only. Not viable.
- **IEX Cloud**: Permanently shut down Aug 2024.
- **Polygon.io**: $199/mo covers OTC + real-time. Best option for OTC but cost deferred.
- **SEC EDGAR**: Free XBRL API, 10 req/s, `EntityCommonStockSharesOutstanding`. Covers ~80% of unknown-float failures. **ADOPTED → Item 4.**
- **Alpha Vantage**: Free tier 25 calls/day, has true `SharesFloat` field. **ADOPTED → Item 6.**
- **Float cache invalidation**: Clearing stale None entries prevents permanent lookup failures. **ADOPTED → Item 5.**
- **OTC stocks**: ~28% of Jan 2025 misses are OTC/pink sheet. Would need Polygon + IBKR ($217/mo). **DEFERRED** — Manny declined.
- **Alpaca cannot trade OTC stocks.** Databento EQUS.MINI = NMS only. Both are structural limitations.
- **Report:** `scanner_deep_dive_report.md` (Perplexity output)

**Free-tier recovery model:** Unknown-float gate ($8,035, done) + SEC EDGAR ($4,143 est) + rescan fix ($3-5K est) + cache invalidation (prevents future misses) = **+$15-17K/month potential** at zero additional cost.

**Key evidence:**
- `cowork_reports/2026-03-23_scanner_gap_analysis.md` — per-stock rejection analysis + recommendations
- `cowork_reports/2025-01_missed_stocks_backtest_results.md` — full backtest results
- `cowork_reports/missed_stocks_backtest_plan.md` — per-stock miss analysis
- `cowork_reports/ross_vs_bot_jan_2025.md` — January comparison summary
- `scanner_deep_dive_report.md` — Perplexity data feed + float source research

---

## 🔴 #2 PRIORITY — Execution Gap: Scaling & Multi-Leg Extraction

**The Problem:** On EEIQ (March 26), Ross made $37,860 while the bot's best-case estimate is $1,500–$3,000 — a **12–25x gap** on the same stock, same day. The bot correctly identified the stock (Profile A, 158% gap, 29.5x RVOL, sub-1M float) but can only capture ~5–8% of what a skilled discretionary trader extracts from a big runner.

**Root Cause:** Single-entry, single-exit architecture vs Ross's multi-leg, scaling, cushion-based approach. Ross made 5+ entries across $5.95–$8.80, pressing to 30K shares on conviction. The bot takes 1 entry at fixed risk and rides to 2R target.

**Report:** `cowork_reports/2026-03-27_eeiq_ross_vs_bot_comparison.md`

| Task | Status | Priority | Est. Impact | Notes |
|------|--------|----------|-------------|-------|
| **Scaling in/out** | **NOT STARTED** | **P0** | **3–5x per-trade P&L** | Initial entry at probe size (50%), confirmation add at +0.5R held 2 bars, strength add on new level break. Requires multi-position tracking per symbol. Single biggest multiplier. |
| **Post-halt re-entry** | **NOT STARTED** | **P1** | **2–3x on halt stocks** | On halt resume, if price dips then reclaims pre-halt high within 3 bars, enter fresh. Pre-halt level as stop. Already tracking halts (ONCO halt/resume working 2026-03-27). |
| **Continuation pattern detection** | **NOT STARTED** | **P1** | **2x additional legs** | Inverted H&S, VWAP reclaim, curls — exactly the patterns Ross used for his $24K EEIQ trade. See Strategy 4 and 5 sections below. |
| **Dynamic session risk sizing** | **NOT STARTED** | **P2** | **1.5–2x on conviction** | When bot is up $X on the day, allow larger position size on high-conviction setups. Ross's "cushion press" turned $4.5K scalp into $37K day. |

**Realistic ceiling with all improvements:** ~$8K–$15K on a stock like EEIQ (~40% of Ross). Remaining gap is discretionary judgment that's extremely hard to automate.

---

## 🔴 CRITICAL — Live Bot Reliability (IBKR V2)

V2 migrated to IBKR on 2026-03-25. First 3 live sessions (March 25–27) produced **zero trades** across 3 days.

| Issue | Status | Notes |
|-------|--------|-------|
| TWS startup failure (port 7497 timeout) | **PARTIALLY FIXED** | daily_run.sh upgraded to 36 retries/180s, but March 27 still failed. Gateway/headless switch pending for Monday. |
| Volume=0 bug (lastSize not read) | **✅ FIXED** | Was the #1 blocker for March 26. All bars had vol=0, detector could never prime. |
| Competing live session (Error 10197) | **RESOLVED** | Caused by IBKR mobile login. Operational rule: no mobile/web during bot hours. |
| Runner position destroyed on target hit | **✅ FIXED** | pos["qty"] set before exit_trade() caused negative remaining. The $1.6K EEIQ bug. |
| Exit orders were market orders | **✅ FIXED** | Now limit orders with outsideRth=True for extended hours. |
| Halt detection spam | **✅ FIXED** | Debounced — prints once on halt, once on resume. |
| Bar-mode squeeze trigger wiring | **✅ FIXED** | simulate.py bar mode wasn't feeding sq_det at all. Now wired. |
| Scanner cutoff (legacy V1) | **✅ FIXED** | Replaced with dual-window support. |
| Stale detector state for evening | **✅ FIXED** | Detectors cleared on window transition. |
| **March 27 validation: still 0 trades** | **NEEDS INVESTIGATION** | Bot started at 09:07 ET (late), watched ONCO (halted 2x) and ARTL. Zero squeeze signals fired. Need backtest to determine if this is expected (no setups) or another bug. |

**Reports:** `cowork_reports/2026-03-26_morning_issues_and_fixes.md`, `cowork_reports/2026-03-26_morning_backtest.md`

---

## 🔴 CRITICAL — Live Bot Audit (Mac Mini) [SUPERSEDED by IBKR V2 section above]

Mac Mini was running stale code (v6-dynamic-sizing, 22 commits behind main). daily_run.sh updated to pull main. Additional issues: Alpaca websocket failures, scanner divergence.

**Directive**: `DIRECTIVE_LIVE_BOT_AUDIT_2026_03_23.md`

| Task | Status | Owner | Notes |
|------|--------|-------|-------|
| Switch Mac Mini to `main` branch | **daily_run.sh UPDATED** | CC | v6 had 0 unique commits vs main |
| Verify .env on Mac Mini | **PENDING** | CC | WB_ROSS_EXIT_ENABLED=0, WB_MP_ENABLED=0 |
| Smoke test bot.py on Mac Mini | **PENDING** | CC | Pre-flight import check + 10s health check |
| Verify cron schedule | **PENDING** | CC | 0 2 * * 1-5 (2 AM MT weekdays) |
| Investigate Alpaca websocket failures | **NOTED** | MEDIUM | 99,934 retries on 2026-03-23, 0 trades |
| Databento migration for live data | **NOT STARTED** | HIGH | Scanner divergence = 0 overlap between live and sim |

---

## 🟡 Scanner Alignment (Mostly Complete)

| Task | Status | Owner | Notes |
|------|--------|-------|-------|
| Phase 1-4: Scanner code alignment | **✅ DONE** | CC | Commit `e9cbb88` |
| Phase 5: Validate with new data | **✅ DONE** | CC | YTD runner uses aligned scanner |
| Connect `live_scanner.py` to `daily_run.sh` | **NOT STARTED** | CC MM | Blocked by Databento cost verification |
| Verify Databento streaming costs | **NOT STARTED** | Manny | Usage-based pricing |
| Faster rescan for news-driven movers | **NOT STARTED** | HIGH | CHNR 44 min late |

---

## 🔴 Strategy 1: Micro Pullback — REDESIGNED as Post-Squeeze Re-Entry (MP V2)

### Standalone MP: SCRAPPED (-$8,066 over 15 months, 24% WR)
- `WB_MP_ENABLED=0` — keep OFF permanently
- 34 max_loss_hit trades at 0% WR (-$19,122) — entries during pre-squeeze noise
- Big MP winners (AIFF, LSE, ROLR) were all squeeze stocks — SQ catches them better
- March 27: SQ-only=$0, SQ+MP=-$2,499. MP turns quiet days into losses.
- **Report:** `cowork_reports/2026-03-27_mp_deep_dive.md`

### MP V2: Post-Squeeze Re-Entry — IMPLEMENTED, NEEDS SQ-PRIORITY FIX
Redesign MP as a re-entry module that only activates AFTER the squeeze detector has confirmed a stock is a legitimate mover. Core implementation done (commit 7c9d302), but **VERO regressed from +$18,583 to +$15,692** because MP V2 re-entries cannibalize SQ cascades on big runners.

**Design Doc:** `STRATEGY_MP_V2_REENTRY_DESIGN.md`
**Implementation Commit:** 7c9d302 (2026-03-27)
**Fix Directive:** `DIRECTIVE_MP_V2_SQ_PRIORITY_GATE.md`

**Key design decisions:**
1. MP stays DORMANT until SQ fires a trade on the symbol (win or loss)
2. 3-bar cooldown after SQ exit before MP starts looking
3. Skip impulse detection (squeeze WAS the impulse) — go straight to pullback monitoring
4. MACD gate relaxed (bearish MACD during post-squeeze pullback is the dip we want to buy)
5. Exits via SQ V1 mechanical system (not MP 10s bar exits)
6. Up to 3 re-entries per symbol per session
7. Probe sizing (50%) on first re-entry, full size on confirmation adds
8. **SQ has unconditional priority** — MP V2 defers when SQ is PRIMED/ARMED/in-trade (PENDING)

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| ~~Implement MP V2 DORMANT/COOLDOWN/ACTIVE state machine~~ | **DONE** | **P0** | Commit 7c9d302. State vars, cooldown, impulse skip, MACD relaxation |
| ~~Route MP V2 trades through SQ exit system~~ | **DONE** | **P0** | `setup_type="mp_reentry"` routes to SQ V1 exits in simulate.py + bot_ibkr.py |
| **Add SQ-priority gate (fix VERO regression)** | **NOT STARTED** | **P0 BLOCKER** | MP V2 defers when `sq_det._state != "IDLE"`. See `DIRECTIVE_MP_V2_SQ_PRIORITY_GATE.md` |
| **Add per-re-entry cooldown** | **NOT STARTED** | **P0** | `notify_reentry_closed()` method — resets cooldown between re-entries |
| **Validate: VERO returns to +$18,583** | **NOT STARTED** | **P0 BLOCKER** | Must pass before Monday deployment |
| **Validate: EEIQ shows MP V2 value-add** | **NOT STARTED** | **P0** | SQ-only vs SQ+V2 on EEIQ 2026-03-26. Proof that re-entries capture extra legs |
| **Full YTD backtest (SQ + MP V2)** | **NOT STARTED** | **P1** | 15-month IBKR dataset. Key check: 0 trades on days where SQ didn't fire |
| **Live paper observation (1 week)** | **NOT STARTED** | **P2** | Deploy alongside SQ, monitor for P&L add vs drag |

### Prior MP Fixes (Historical — Applied to Standalone MP, May Carry Over)
- [x] Fix 1: Direction-aware continuation hold (+$317) — `WB_CONT_HOLD_DIRECTION_CHECK=1`
- [x] Fix 2: Float-tiered max loss cap (+$937) — `WB_MAX_LOSS_R_TIERED=1`
- [x] Fix 3: max_loss_hit triggers cooldown (+$916) — `WB_MAX_LOSS_TRIGGERS_COOLDOWN=1`
- [x] Fix 4: No re-entry after loss (+$1,315) — `WB_NO_REENTRY_ENABLED=1`
- [x] Fix 5: TW profit gate at 1.5R (+$12,619) — `WB_TW_MIN_PROFIT_R=1.5`

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

## 🟡 Strategy 4: VWAP Reclaim (NEW — Not Yet Built) ⬆️ PRIORITY UPGRADED

Ross trades "the first 1-minute candle to make a new high" after price crosses back above VWAP. This is a specific entry signal the bot doesn't have. **CHNR analysis (2026-03-19) shows this was Ross's bread-and-butter pattern — 2 of his 3 actual trade sequences were VWAP reclaim setups.**

**Evidence across two live-day analyses:**
- **CHNR 2026-03-19**: VWAP curl trade (scratched -$67) + VWAP break into $6.00 (+$2k). Ross's primary setup.
- **ARTL 2026-03-18**: VWAP reclaim was part of Ross's re-entry sequence after the initial squeeze.

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Define VWAP reclaim criteria | **NOT STARTED** | **HIGH** | Key: price crosses above VWAP from below, first candle makes new high, volume confirmation. MACD filter (Ross skipped CHNR longs when MACD negative). |
| Design VWAP reclaim module | **NOT STARTED** | **HIGH** | May be simpler than squeeze — specific trigger condition. Entry on VWAP reclaim, exit at prior resistance/whole dollar. |
| Define exit rules | **NOT STARTED** | MEDIUM | |
| Implement and backtest | **NOT STARTED** | — | After design approved |

---

## 🟡 Strategy 5: Curl / Extension (NEW — Not Yet Built) ⬆️ PRIORITY UPGRADED

Rounded bottom approach toward prior HOD. Ross uses this for continuation trades later in the session. **CHNR analysis (2026-03-19) confirms this is Ross's biggest winner pattern — his +$2,000 curl from $5.00 support was the day's best trade.**

**Evidence across two live-day analyses:**
- **CHNR 2026-03-19**: Curl from $5.00 support after deep pullback → squeeze to $6.00 (+$2k). His best actual trade.
- **ARTL 2026-03-18**: Ross's best ARTL trade was also a curl pattern (gradual recovery into prior HOD).

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Define curl entry criteria | **NOT STARTED** | **HIGH** | Key elements: gradual rounded-bottom recovery after pullback, approaching prior support/resistance zone. Needs concept of "support" (VWAP, whole dollar, prior consolidation) |
| Design and implement | **NOT STARTED** | **HIGH** | More complex than VWAP reclaim — needs multi-bar pattern recognition for rounded bottom shape |

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
| YTD 2026 morning (IBKR data) | **+$120,221** (36 trades, 97% WR, $30K → $150K) | 2026-03-26 |
| Full megatest Jan 2025–Mar 2026 | **+$1,348,605** (321 trades, 90% WR, $30K → $1.38M) | 2026-03-26 |
| Realistic megatest (slippage adj) | **$350K–$550K** estimated | 2026-03-25 |
| EEIQ execution gap vs Ross | Bot ~$1.5–3K vs Ross $37.8K (12–25x) | 2026-03-27 |
| Jan 2025 missed stocks potential | **+$42,818** (7.7x vs actual $5,543) | 2026-03-23 |
| VERO regression | **+$18,583** (requires `WB_MP_ENABLED=1`) | 2026-03-18 |
| ROLR regression | **+$6,444** (requires `WB_MP_ENABLED=1`) | 2026-03-18 |
| Live bot status | **0 trades across 3 days** (Mar 25–27, IBKR V2) | 2026-03-27 |

---

*This file is the single source of truth for all open work. Updated by Cowork after each session.*
