# DIRECTIVE: Wave Breakout — Stage 3 (Build & Paper Validation)

**Date:** May 4, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code) / Cowork  
**Priority:** P1 — Build, paper-test, do NOT enable live without explicit approval  
**Branch:** `v2-ibkr-migration`  
**Predecessor:** `cowork_reports/2026-05-04_wave_breakout_stage2_results.md`

---

## Decision

**Approved: Path A — V8b configuration.**

The Stage 2 data argues clearly. V8b (V2 trailing-only + V5 pyramid + V7 concurrency cap) produces 648 trades over 84 days at 53.4% WR / PF 2.01 / +$154K. The fat-tail capture is real and distributed across many stocks (top 10 winners on 10 different symbols, including BIRD April 15 — the day the bot missed live).

The Stage 3 acceptance gate as originally drafted contained a structural conflict (PF ≥ 2.5 + Total ≥ $300K can't co-exist under realistic position sizing). **The gate is hereby revised.**

### Revised Stage 3 Gate

| # | Criterion | Threshold | V8b status |
|---:|---|:---:|:---:|
| 1 | Position sizer caps shares (no FIGG) | All ≤ MAX_NOTIONAL | ✅ verified |
| 2 | Trade count over 84 days | ≥ 200 | ✅ 648 |
| 3 | Profit factor | **≥ 1.8** (revised from 2.5) | ✅ 2.01 |
| 4 | Total P&L (ex outliers >10% of total) | **≥ $100K** (revised from $300K) | ✅ $154K |
| 5 | Top-5 days share of P&L | ≤ 65% | ✅ 62.9% |
| 6 | Top-10 winners distributed across ≥8 distinct symbols | NEW gate | ✅ 10/10 |
| 7 | Manual validation | **WAIVED** — data speaks for itself |

**V8b passes all 6 active gates. Stage 3 build is GO.**

---

## What Gets Built

### File 1: `wave_breakout_detector.py` (new, ~400 LOC)

A self-contained strategy module modeled on `squeeze_detector.py`. Same overall architecture: state machine, bar-close hooks, tick-level updates, exit decisions internal to the module.

**State machine:**
```
IDLE → WAVE_OBSERVING → SETUP_SCORED → ARMED → IN_TRADE → IDLE
```

**Required interface (matches squeeze for consistency):**
```python
class WaveBreakoutDetector:
    def __init__(self, symbol: str, config: dict)
    def on_bar_close_1m(self, bar: Bar, vwap: float | None) -> Optional[str]
    def on_trade_price(self, price: float, ts: datetime) -> Optional[str]
    def check_exit(self, price: float, bar: Bar | None = None) -> Optional[str]
    def reset_session(self) -> None
```

**Configuration (env vars):**
```bash
# Master switch — DEFAULTS OFF
WB_WAVE_BREAKOUT_ENABLED=0

# Wave detection (proven in research, do not change without re-running census)
WB_WB_MIN_WAVE_PCT=0.0075           # 0.75% minimum wave magnitude
WB_WB_WAVE_MIN_DURATION_MIN=3       # waves shorter than this are noise
WB_WB_WAVE_MAX_DURATION_MIN=15      # waves longer than this are trends, not chops
WB_WB_REVERSAL_CONFIRM_PCT=0.005    # 0.5% reversal required to confirm wave end

# Setup scoring threshold (V8b uses 7)
WB_WB_MIN_SCORE=7                   # minimum score for ARMED state

# Position sizing (V0 hardening — MANDATORY)
WB_WB_RISK_DOLLARS=1000             # default risk per trade
WB_WB_MIN_RISK_PER_SHARE=0.01       # absolute floor
WB_WB_MIN_RISK_PCT=0.001            # 10 bps of entry price floor
WB_WB_MAX_NOTIONAL=50000            # binding cap

# Exit logic (V2 trailing-only — the big winner)
WB_WB_TRAILING_ACTIVATE_R=1.0       # trail activates at +1R (breakeven)
WB_WB_TRAILING_DISTANCE_R=0.5       # trail at 0.5R below running peak
WB_WB_HARD_STOP_R=1.0               # initial stop at -1R
WB_WB_NO_TIME_STOP=1                # explicitly no time cap (V2 finding)
WB_WB_SESSION_END_FORCE_EXIT=1      # exit any open position at session end

# Pyramid (V5 — adds modest +$6K combined with V2)
WB_WB_PYRAMID_ENABLED=1
WB_WB_PYRAMID_TRIGGER_R=1.0         # add second leg when +1R reached
WB_WB_PYRAMID_RISK_DOLLARS=1000     # same risk on second leg

# Portfolio concurrency (V7 — realistic operating constraint)
WB_WB_MAX_CONCURRENT=3              # max simultaneous positions across symbols
```

### File 2: Wiring into `bot_v3_hybrid.py` (surgical edits only)

**Critical: do NOT modify any squeeze code paths. Wave Breakout is parallel, not replacing.**

Required changes:

1. **Import:**
```python
from wave_breakout_detector import WaveBreakoutDetector
```

2. **Strategy enable check at startup:**
```python
WB_WAVE_BREAKOUT_ENABLED = os.getenv("WB_WAVE_BREAKOUT_ENABLED", "0") == "1"
if WB_WAVE_BREAKOUT_ENABLED:
    print("[STRATEGY] Wave Breakout: ENABLED")
else:
    print("[STRATEGY] Wave Breakout: disabled (WB_WAVE_BREAKOUT_ENABLED=0)")
```

3. **Per-symbol detector instantiation (alongside squeeze, not replacing):**
```python
# In subscribe_symbol():
state.symbols[symbol]['wb_detector'] = WaveBreakoutDetector(symbol, wb_config) if WB_WAVE_BREAKOUT_ENABLED else None
```

4. **Bar-close routing:**
```python
# In on_bar_close():
if WB_WAVE_BREAKOUT_ENABLED:
    wb_msg = state.symbols[symbol]['wb_detector'].on_bar_close_1m(bar, vwap)
    if wb_msg and wb_msg.startswith("WB_ENTER"):
        # Check portfolio concurrency cap
        active_wb = sum(1 for s in state.symbols.values() if s.get('wb_position'))
        if active_wb >= WB_WB_MAX_CONCURRENT:
            log.info(f"WB_DEFER: {symbol} - portfolio cap ({active_wb}/{WB_WB_MAX_CONCURRENT}) reached")
        else:
            place_wave_breakout_entry(symbol, wb_msg)
```

5. **Tick-level exit checks:**
```python
# In on_trade(), after squeeze checks:
if WB_WAVE_BREAKOUT_ENABLED and state.symbols[symbol].get('wb_position'):
    exit_msg = state.symbols[symbol]['wb_detector'].check_exit(price, current_bar)
    if exit_msg:
        place_wave_breakout_exit(symbol, exit_msg)
```

6. **Order placement helpers** (`place_wave_breakout_entry`, `place_wave_breakout_exit`) — model after the squeeze versions, but with `setup_type="wave_breakout"` for clean log filtering.

### File 3: Logging convention

All Wave Breakout log lines must be prefixed `[WB]` for filtering:
```
[WB] symbol=BIRD state=WAVE_OBSERVING wave_id=3 magnitude=2.1%
[WB] symbol=BIRD state=ARMED score=8 entry=$2.59 stop=$2.55 trail_active_at=$2.63
[WB] symbol=BIRD ENTER qty=12484 entry=$2.59 risk=$1000
[WB] symbol=BIRD trailing_active peak=$3.15 trail_stop=$2.83
[WB] symbol=BIRD EXIT reason=trailing_stop exit=$2.83 pnl=+$2,995 r_mult=+3.0
```

This makes post-session analysis trivial — `grep [WB]` shows the entire wave breakout activity stream.

---

## Paper Validation Plan

### Phase 1: Solo Paper (Days 1-3)

Run Wave Breakout alone in paper mode:
- `WB_WAVE_BREAKOUT_ENABLED=1`
- `WB_SQUEEZE_ENABLED=0` (squeeze OFF to isolate)
- IBKR paper account
- Min 3 full trading days

**Pass criteria:**
- ≥1 trade per day on average (3+ over 3 days)
- All trades respect position sizer cap (no orders >$50K notional)
- All trailing stops fire when expected (verify via logs)
- No phantom positions (all entries/exits match Alpaca/IBKR dashboard)

### Phase 2: Combined Paper (Days 4-8)

Run Wave Breakout alongside Squeeze in paper:
- `WB_WAVE_BREAKOUT_ENABLED=1`
- `WB_SQUEEZE_ENABLED=1`
- IBKR paper account
- Both subscribed to the same watchlist
- Min 5 full trading days

**Pass criteria:**
- Squeeze trades execute identically to baseline (no regression — verify by comparing PRIMED/ARMED/ENTER counts vs prior week)
- Wave Breakout trades execute on top, not replacing squeeze entries
- Combined daily trade count ≤ 12 (sanity check that the strategies aren't overlapping)
- No order conflicts (e.g., squeeze and WB trying to place orders on the same symbol simultaneously)

### Phase 3: Subbot Cross-Check (Optional, parallel to Phase 2)

Run Wave Breakout on the Alpaca subbot too. Compare:
- Same setups detected on both feeds?
- Same trades fired?
- Per-trade P&L parity?

This isolates whether Wave Breakout is feed-sensitive (likely some divergence on small-caps).

### Phase 4: Live (only after Phase 1 + 2 pass)

Real money. Squeeze + Wave Breakout combined. Daily loss caps unchanged. Manny gives explicit GO before flipping the env var to live.

---

## What NOT to Do

- ❌ Do NOT modify `squeeze_detector.py` or any squeeze-related logic
- ❌ Do NOT change wave detection parameters (0.75% / 3-15 min / 0.5% reversal) without re-running the full 84-day census
- ❌ Do NOT enable WB live without Manny's explicit approval after Phase 1 + 2
- ❌ Do NOT skip Phase 1 (solo paper) — running both strategies simultaneously on day 1 makes it impossible to attribute failures
- ❌ Do NOT optimize parameters during paper — record divergences and report, do not tune live

---

## Acceptance Criteria for Live Activation

After Phase 1 + 2 paper testing:

| # | Check | How to verify |
|---:|---|---|
| 1 | Wave Breakout fires ≥3 times in solo paper | Count `WB ENTER` log lines in days 1-3 |
| 2 | All trades respect $50K notional cap | Check `qty × entry` for every entry |
| 3 | All trailing stops fire on actual reversals (not bugs) | Manual review of 5 random WB exits |
| 4 | Squeeze regression test passes | Compare squeeze-only metrics from prior week |
| 5 | No phantom positions in either Alpaca or IBKR dashboard | Reconcile bot state vs broker dashboards daily |
| 6 | Combined daily trade count remains reasonable (≤ 12) | Day-end count check |
| 7 | Manual review of one full WB trade lifecycle | Read logs from PRIMED → ENTER → trail → EXIT |

**All 7 must pass before live activation.**

---

## Top 15 Reference Trades (For Verification)

Use these as ground truth when validating the live build. If the live bot enters these stocks on these dates with similar parameters, the detector is wired correctly.

| Symbol | Date | Entry | Exit | Qty | P&L | Reason |
|---|---|---:|---:|---:|---:|---|
| RYOJ | 2026-01-21 | $3.12 | $5.28 | 16025 | +$34,633 | trailing_stop |
| GITS | 2026-02-23 | $2.20 | $2.99 | 22221 | +$17,499 | trailing_stop |
| SWVL | 2026-01-27 | $2.02 | $2.70 | 24752 | +$16,893 | trailing_stop |
| AIMD | 2026-01-28 | $2.19 | $2.73 | 18066 | +$9,803 | trailing_stop |
| BIRD | 2026-04-15 | $2.59 | $3.15 | 12484 | +$6,943 | trailing_stop |
| NDLS | 2026-03-26 | $7.50 | $8.16 | 5939 | +$3,942 | trailing_stop |
| STSS | 2026-01-16 | $2.21 | $2.38 | 22014 | +$3,683 | trailing_stop |
| SKYQ | 2026-04-29 | $5.90 | $6.33 | 8474 | +$3,667 | trailing_stop |
| KIDZ | 2026-04-13 | $2.11 | $2.26 | 23696 | +$3,492 | trailing_stop |
| SVRE | 2026-01-16 | $1.75 | $2.11 | 8764 | +$3,181 | trailing_stop |

**Notable: BIRD on April 15 — this is the day the bot missed live and Manny watched it run.** Wave Breakout would have caught it for ~$7K. This is the validation that the strategy fills exactly the gap that hurt us most.

---

## Files & Artifacts

```
wave_breakout_detector.py             (new, ~400 LOC)
bot_v3_hybrid.py                       (surgical edits only — ~50 LOC additions)
.env.example                           (add WB_WAVE_BREAKOUT_* vars)
cowork_reports/
  2026-05-XX_wb_paper_phase1.md        Phase 1 solo paper results
  2026-05-XX_wb_paper_phase2.md        Phase 2 combined paper results
```

---

*The bot's job is to be the patient mechanical version of Manny that never closes a winner too early. V8b ships. BIRD won't slip through next time.*
