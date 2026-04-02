# CC Handoff — April 2, 2026

## SITUATION: V3 Hybrid Bot Live — Infrastructure Proven, Awaiting First Trade

V3 hybrid bot (`bot_v3_hybrid.py`) ran its first live session April 2. Zero trades — correct outcome for the day's stocks, confirmed by 100% backtest match. Infrastructure stable for 6 hours straight. This is the architecture going forward.

**Why V3 exists:**
- V1 (pure Alpaca): Took trades but had phantom position bug (cancel-replace race condition). VOR April 1 = unmanaged shares.
- V2 (pure IBKR): Never took a single trade in 8 live sessions. PRIMED→ARMED gap on fast movers — volume explosion and level break happen on the SAME bar, but V1/V2 require them on separate bars.
- V3 (hybrid): IBKR data (scanner, ticks, RTVolume) + Alpaca execution (orders, paper account). Proven data + proven execution.

---

## LATEST SESSION: April 2, 2026

**Bot:** V3 hybrid | **SQ detector:** V2 with rolling HOD gate | **Session:** 06:17–12:00 ET (manual start — cron 4 AM failed again)

### Watchlist (4 stocks)
- **BATL**: SQ_PRIMED at 07:10 (vol=3.3x), RESET after 3 bars — price needed $0.22 more to break PM high
- **SKYQ**: 128.6x volume explosion at 07:38 — but bot wasn't subscribed yet (scanner-move paradox). By discovery time (07:50), move was done.
- **TURB**: SQ_PRIMED at 09:40 (vol=6.4x), never ARMed — $4.00 whole dollar was +9% away
- **KIDZ**: Dead tape, 0-22 ticks/min, no activity

**Result:** 0 trades, $0 P&L. Backtest confirms 0 trades on all 4 stocks from actual discovery times. 100% match.

**Key insight — Scanner-Move Paradox:** The volume spike that creates the opportunity = the spike that makes the scanner discover the stock (SKYQ 07:38). Bot can't catch the initial move on scanner-discovered stocks. Mitigations: broader pre-market watchlist, faster scanner cycles, accept catching the 2nd move.

**Report:** `cowork_reports/2026-04-02_morning_progress.md`

---

## V1 INVESTIGATION (April 1)

V1 ran April 1 alongside V2: 4 trades (GVH -$330, APLX -$211, ELAB -$130, VOR phantom).

**VOR phantom root cause:** Cancel-replace race condition. Bot submits limit order → times out → sends cancel → order fills on Alpaca between cancel request and cancel confirmation → bot doesn't know about the fill → replacement order may also fill → phantom shares.

V3 fixes all phantom scenarios with 5 mechanisms: startup position reconciliation, fill verification with retry (no cancel-replace logic), 60s heartbeat position sync, exit order verification with market fallback, graceful shutdown position check.

**Report:** `cowork_reports/2026-04-01_v1_investigation.md`
**Directive:** `DIRECTIVE_V3_POSITION_SYNC.md`

---

## SQUEEZE V2 DETECTOR — Feature Test Results

`squeeze_detector_v2.py` (714 lines) built as a SEPARATE MODULE — V1 `squeeze_detector.py` is NOT TOUCHED. Import switch: `WB_SQUEEZE_VERSION=1|2`.

### 63-Day Backtest Results

| Config | P&L | Trades | WR | Delta vs V1 |
|--------|-----|--------|-----|------------|
| V1 baseline | +$154,849 | 26 | 73% | — |
| **V2 rolling HOD only** | **+$169,227** | **29** | **67%** | **+$14,378** |
| V2 all features ON | +$167,556 | 29 | 67% | +$12,707 |
| V2 base code, rolling HOD OFF | +$131,657 | — | — | -$23,192 (regression!) |

**Key findings:**
- **Rolling HOD is the only feature that matters.** V1's `_session_hod` accumulates across ALL bars including 4 AM seeds — a premarket spike blocks entries hours later. V2's `max(bars[-49:])` lets stale highs age out. This alone adds +$14,378 and 3 more trades.
- **Named features had zero impact:** COC, exhaustion gate, intra-bar ARM each produced ~$0 delta individually.
- **Candle exits COST $1,671** — they cut winners short. Currently OFF.
- **V2 base code has unexplained -$23K regression** when rolling HOD is OFF. Needs audit.

**Report:** `cowork_reports/2026-04-01_sq_v2_feature_tests.md`

---

## ACTIVE PRIORITIES

### P0: Mac Mini Sleep Prevention (NOT YET APPLIED)
Cron 4 AM launch fails daily because IB Gateway requires active display session. Fix:
```bash
sudo pmset -a sleep 0 displaysleep 0
caffeinate -dims &
```
Plus screen lock prevention. Manny has been manually starting at 4-6 AM MT.

### P1: V2 Base Code Regression Audit
V2 WITHOUT rolling HOD is -$23,192 worse than V1. Unexplained — code path differences between V1 and V2 base need audit. May be HOD calculation, level map, or volume computation differences.

### P1: Scanner Coverage / Scanner-Move Paradox
- Broader pre-market watchlist from Databento before open
- Faster IBKR scanner cycles (currently every 5 min)
- Unified Scanner V3 directive: `DIRECTIVE_UNIFIED_SCANNER_V3.md`

### P2: L2 Phase 2
Full infrastructure in archive. March 2 study: +$6,526 with float≥5M gate (against MP, not squeeze). Deferred until candle features prove out.

### P2: Candle Exit Tuning
Currently OFF (cost $1,671). Need higher profit gates or minimum time-in-trade before re-enabling.

---

## KEY FILES (New Since March)

| File | Purpose |
|------|---------|
| `bot_v3_hybrid.py` | **ACTIVE LIVE BOT** — 1576 lines, IBKR data + Alpaca execution |
| `squeeze_detector_v2.py` | SQ V2 module — 714 lines, rolling HOD gate, same interface as V1 |
| `daily_run_v3.sh` | V3 launch script (replaces daily_run.sh) |
| `DIRECTIVE_V3_HYBRID_BOT.md` | V3 architecture spec |
| `DIRECTIVE_V3_POSITION_SYNC.md` | 5 phantom position fixes |
| `SQUEEZE_V2_PLAN.md` | V2 roadmap (entry/exit/L2 improvements) |
| `SQUEEZE_V2_DECISIONS.md` | ⚠️ **0 BYTES** — upload was empty, needs re-upload from Perplexity |
| `AUDIT_ROSS_CANDLE_VS_V2.md` | Perplexity Ross candle strategy audit |

---

## REGRESSION TARGETS
```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$15,692

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

## GIT
- git pull first
- git push after regression passes
- Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

---

## 0. Architecture & Workflow

### The Setup
| Machine | Role | Claude Instances | What It Does |
|---------|------|-----------------|-------------|
| **Mac Mini** | PRIMARY | CC (terminal) + Cowork | Code changes, backtesting, live bot, strategy analysis |
| **MacBook Pro** | REMOTE/BACKUP | CC (VS Code) + Cowork | Remote access, weekend work, backup development |

All share the same GitHub repo (`mannyluke4/warrior_bot`, branch `main`).
The `.env` file is **gitignored** (contains API keys) — each machine has its own copy.

### V3 Hybrid Architecture
```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  IB Gateway  │────▶│  V3 Hybrid   │────▶│   Alpaca    │
│  (data only) │     │   Bot        │     │ (execution) │
│              │     │              │     │             │
│ - Scanner    │     │ - SQ V2      │     │ - Buy       │
│ - Tick data  │     │ - Position   │     │ - Sell      │
│ - RTVolume   │     │   sync       │     │ - Paper     │
│              │     │ - Exit mgmt  │     │   account   │
└─────────────┘     └──────────────┘     └─────────────┘
```

### Roles & Boundaries

**Cowork (you) — Strategist / Coordinator**
- READ any file in the repo
- WRITE directive `.md` files into the repo folder
- ANALYZE reports, trade logs, backtest results, .env config
- PLAN next optimizations, identify bugs, prioritize work
- UPDATE `MASTER_TODO.md` after each session
- DO NOT edit `.py` files, `.env`, or any code — that's CC's job
- DO NOT run backtests or simulations — that's CC's job
- DO NOT commit or push to git — that's CC's job

**CC (on whichever machine) — Developer / Operator**
- EXECUTE directives from Cowork (code changes, backtests, analysis)
- EDIT all `.py` files, `.env`, config files
- RUN backtests, simulations, regressions
- COMMIT and PUSH code changes to the repo
- PRODUCE reports and commit them
- RUN the live bot daily via cron (Mac Mini)

**Rule**: Cowork reads, CC writes. Cowork's output is always a directive `.md` file, never a code edit.

### Key Documents
| File | Purpose |
|------|---------|
| `MASTER_TODO.md` | **Single source of truth** for all open work. Read this first. |
| `COWORK_HANDOFF.md` | This file — project context for new Cowork sessions |
| `CLAUDE.md` | Project instructions for Claude Code instances |
| `.env` | All config knobs — read before suggesting changes |

---

## 1. What This Project Is

A Python day trading bot that detects squeeze breakout setups on small-cap stocks. Uses IBKR for real-time data and Alpaca for paper trade execution. Built to replicate Ross Cameron's (Warrior Trading) methodology.

- **Owner**: Manny — day trader, prefers consistent $200-500 daily hits, methodical approach
- **Stage**: Paper trading on Alpaca with $30K account
- **Branch**: `main`
- **Repo**: GitHub, `mannyluke4/warrior_bot`
- **Active bot**: `bot_v3_hybrid.py` (V1 and V2 bots frozen)

---

## 2. How the Bot Works

### V3 Detection Flow
1. **Scanners**: IBKR `reqScannerSubscription` (STK.US.MAJOR) + Databento `live_scanner.py` (writes watchlist.txt, bridged into V3)
2. **Seed bars** (4AM-start) build EMA/VWAP/PM_HIGH context from IBKR tick data
3. **1-minute bars** from IBKR ticks → `SqueezeDetectorV2` (volume spike → level break, rolling HOD gate)
4. **Armed setups** trigger on tick price breaking level (PM high, whole dollar, PDH)
5. **Orders execute via Alpaca** — limit entry, fill verification, no cancel-replace
6. **Exits**: dollar loss cap → hard stop → tiered max_loss → pre-target trail → 2R target → runner trail
7. **Position sync**: startup reconciliation + 60s heartbeat + exit verification + graceful shutdown

### Key Files
| File | Purpose |
|------|---------|
| `bot_v3_hybrid.py` | **ACTIVE** live bot — IBKR data + Alpaca execution (1576 lines) |
| `squeeze_detector_v2.py` | SQ V2 detector — rolling HOD gate (714 lines) |
| `squeeze_detector.py` | SQ V1 detector — FROZEN, do not modify |
| `simulate.py` | Backtesting engine (tick + bar mode) |
| `bot_ibkr.py` | V2 pure-IBKR bot — FROZEN |
| `bot.py` | V1 pure-Alpaca bot — FROZEN |
| `trade_manager.py` | Order execution + exit management |
| `bars.py` | TradeBarBuilder (VWAP/HOD/PM tracking) |
| `live_scanner.py` | Databento real-time scanner (writes watchlist.txt) |
| `scanner_sim.py` | Backtest scanner (generates scanner_results/*.json) |
| `daily_run_v3.sh` | V3 launch script |
| `.env` | ALL config knobs |

---

## 3. Current State (as of 2026-04-02)

### Live Performance
| Date | Bot | Trades | P&L | Notes |
|------|-----|--------|-----|-------|
| April 1 | V1 (Alpaca) | 4 | -$671 + VOR phantom | Cancel-replace race → phantom position |
| April 1 | V2 (IBKR) | 0 | $0 | 8th consecutive session with 0 trades |
| April 2 | V3 (hybrid) | 0 | $0 | Correct outcome — 100% backtest match, infrastructure stable 6h |

### Backtest Performance
| Config | P&L (63 days) | Trades | WR |
|--------|--------------|--------|-----|
| SQ V1 | +$154,849 | 26 | 73% |
| SQ V2 rolling HOD | +$169,227 | 29 | 67% |
| SQ V2 all features | +$167,556 | 29 | 67% |

---

## 4. Critical Rules

### DO NOT:
- Modify `squeeze_detector.py` — V1 is FROZEN, V2 is the separate module
- Disable exhaustion filter — dynamic scaling handles cascading stocks correctly
- Set max loss cap below 0.75R on any tier — kills ROLR
- Change behavior without an env var gate (OFF by default)

### ALWAYS:
- Use `--ticks --tick-cache tick_cache/` for backtests
- Backtest window: 07:00-12:00 ET
- Test changes on multiple stocks before declaring them good
- Gate new features behind env vars (OFF by default)
- Run regression after any change: VERO +$15,692, ROLR +$6,444

---

## 5. Manny's Working Style

- **Data-driven**: Always dig into the data before proposing fixes. No guessing.
- **Deep analysis**: Break everything down on a detailed technical level. Find the specific root cause.
- **Precise fixes**: Act on specific findings, not general context.
- **One thing at a time**: Test each change individually before combining.
- **Ross methodology**: The bot should trade like Ross Cameron. His recaps are the benchmark.
- **Organized**: Keep `MASTER_TODO.md` current. Nothing should be forgotten between sessions.

---

*Handoff updated: 2026-04-02 | V3 hybrid bot live — IBKR data + Alpaca execution. First session: 0 trades (correct), infrastructure proven stable. SQ V2 rolling HOD = +$14,378 over V1. Phantom positions fixed. pmset still needed for reliable cron starts.*
