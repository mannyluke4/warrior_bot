# DIRECTIVE: Migrate Warrior Bot from Alpaca to Interactive Brokers

**Date:** 2026-03-25
**From:** Manny (via Perplexity full system audit + platform research)
**For:** Claude Code on Mac Mini
**Priority:** P0 — This replaces all other directives. Nothing else matters until this is done.
**IB Gateway:** Already installed on Mac Mini.

---

## Why We're Doing This

Alpaca was recommended by ChatGPT two months ago as a quick-start. It's the wrong platform for this strategy. The problems are structural and unfixable:

1. **Alpaca's snapshot API uses IEX (~3% of market volume). Their historical bars API uses SIP (100%).** This is a documented, confirmed architectural split that makes relative volume calculations meaningless between live and backtest. Our entire three-scanner problem, every RVOL bug CC has chased, every backtest-vs-live divergence — all trace back to this single root cause.

2. **Alpaca cannot trade OTC stocks.** Period. ~28% of Ross Cameron's January 2025 trades were on stocks Alpaca can't touch.

3. **Alpaca has no halt detection API.** The stocks we trade halt multiple times daily. We're flying blind.

4. **Alpaca paper fills ignore book depth.** Every backtest result on paper is inflated because Alpaca fills orders instantly regardless of actual liquidity.

IBKR solves all four problems. We already have the account and the gateway is on the Mac Mini.

---

## What We're Building

### The New Architecture (Simple)

```
IB Gateway (Mac Mini, always running)
    │
    ├── Scanner: reqScannerSubscription (pre-market gap-ups)
    │     → TOP_PERC_GAIN, price $2-$20, volume > 50K
    │     → Float lookup: FMP → yfinance → EDGAR (existing chain)
    │     → Output: ranked candidate list (same format as scanner_results/*.json)
    │
    ├── Live Data: reqMktData (5-10 symbols, ~250ms updates)
    │     → Feeds squeeze_detector.py and micro_pullback.py
    │     → Halt detection via Tick Type 49 (automatic)
    │
    ├── Execution: placeOrder / cancelOrder
    │     → Direct-access routing (IBKR Pro SmartRouting)
    │     → Pre-market from 4:00 AM ET
    │
    └── Historical Data: reqHistoricalData (1-min bars)
          → Same source as live → backtest/live parity
          → Used by simulate.py for backtesting

Python Stack:
    ├── ib_insync (community library, production-reliable)
    ├── squeeze_detector.py (KEEP AS-IS — this works)
    ├── simulate.py (KEEP core logic — refactor data input layer)
    ├── run_megatest.py (KEEP — refactor to use IBKR historical data)
    └── bot.py (REBUILD — new main loop using ib_insync)
```

### What We're Keeping (Proven, Working)

| Component | File | Lines | Why Keep |
|-----------|------|-------|----------|
| Squeeze detector | squeeze_detector.py | 419 | Clean state machine, 70% WR, 21x profit factor |
| Backtest engine | simulate.py (core) | ~2,500 | Exit logic is proven — squeeze trail, targets, stall timer |
| Megatest runner | run_megatest.py | 811 | Good orchestration — equity compounding, daily limits |
| Micro pullback detector | micro_pullback.py | 1,288 | Keep for now, may disable later based on data |

### What We're Deleting (Dead, Disabled, or Replaced)

| Component | File(s) | Lines | Why Delete |
|-----------|---------|-------|------------|
| Alpaca live scanner | live_scanner.py | 717 | Orphaned — never connected to bot.py. Uses Databento. |
| Alpaca market scanner | market_scanner.py | 176 | Replaced by IBKR reqScannerSubscription |
| Alpaca stock filter | stock_filter.py | 325 | Filter logic moves into unified IBKR scanner |
| VWAP reclaim detector | vwap_reclaim_detector.py | 430 | Shelved — 0 trades in all testing |
| Classifier | classifier.py, validate_classifier.py | 711 | Disabled since creation |
| Ross exit system | ross_exit.py | 325 | Disabled — V1 (mechanical exits) beats V2 consistently |
| Parabolic regime | parabolic.py | 243 | Disabled |
| Level map | levels.py | 255 | Disabled |
| Old backtest runners | run_jan_v1/v2, run_v3_cuc, run_oos, etc. | ~3,000 | Superseded by run_megatest.py |

**Estimated deletion: ~6,200 lines, ~150 env vars.**

### What We're Rebuilding

| Component | Current | New | Effort |
|-----------|---------|-----|--------|
| Scanner | 3 separate implementations | 1 unified IBKR scanner | Medium |
| Data feed | Alpaca websocket + Databento | ib_insync reqMktData | Medium |
| Execution | Alpaca REST orders | ib_insync placeOrder | Medium |
| Main loop | bot.py (Alpaca-centric) | bot_ibkr.py (ib_insync event loop) | Large |
| Backtest data | scanner_sim.py (Alpaca historical) | ibkr_scanner.py (IBKR historical) | Medium |
| Halt handling | None (blind) | Tick Type 49 callback | Small |

---

## Phase 1: Foundation (Days 1-3)

### Task 1.1: Install Dependencies + Verify Connection

```bash
pip install ib_insync
```

Write a test script `test_ibkr_connection.py`:
```python
from ib_insync import *

ib = IB()
ib.connect('127.0.0.1', 4002, clientId=1)  # 4002 = IB Gateway paper
print(f"Connected: {ib.isConnected()}")
print(f"Account: {ib.managedAccounts()}")

# Test market data
contract = Stock('AAPL', 'SMART', 'USD')
ib.qualifyContracts(contract)
ticker = ib.reqMktData(contract, '', False, False)
ib.sleep(2)
print(f"AAPL last: {ticker.last}, bid: {ticker.bid}, ask: {ticker.ask}")

ib.disconnect()
```

**Success criteria:** Connected, account returned, AAPL data received.

### Task 1.2: Pre-Market Scanner Test

Write `test_ibkr_scanner.py`:
```python
from ib_insync import *

ib = IB()
ib.connect('127.0.0.1', 4002, clientId=1)

# Pre-market gap-up scanner (Ross Cameron criteria)
sub = ScannerSubscription(
    instrument='STK',
    locationCode='STK.US.MAJOR',  # Later: STK.US for OTC
    scanCode='TOP_PERC_GAIN',
    abovePrice=2.0,
    belowPrice=20.0,
    aboveVolume=50000,
    marketCapBelow=500000000,  # $500M cap = small-cap filter
    numberOfRows=20,
)

# Request scanner results
results = ib.reqScannerData(sub)
print(f"Scanner returned {len(results)} results:")
for r in results[:10]:
    print(f"  {r.contractDetails.contract.symbol}: "
          f"rank={r.rank}, distance={r.distance}")

ib.disconnect()
```

**Success criteria:** Scanner returns 5-20 small-cap gap-up candidates pre-market.

### Task 1.3: Historical Data Test

Write `test_ibkr_historical.py`:
```python
from ib_insync import *
from datetime import datetime

ib = IB()
ib.connect('127.0.0.1', 4002, clientId=1)

# Fetch 1-min bars for a known stock on a known date
contract = Stock('VERO', 'SMART', 'USD')
ib.qualifyContracts(contract)

bars = ib.reqHistoricalData(
    contract,
    endDateTime='20260116 16:00:00 US/Eastern',
    durationStr='1 D',
    barSizeSetting='1 min',
    whatToShow='TRADES',
    useRTH=False,  # Include pre-market
    formatDate=1,
)

print(f"Got {len(bars)} bars for VERO on 2026-01-16")
if bars:
    print(f"First bar: {bars[0]}")
    print(f"Last bar: {bars[-1]}")
    # Find the bar with highest volume
    max_vol_bar = max(bars, key=lambda b: b.volume)
    print(f"Highest volume bar: {max_vol_bar}")

ib.disconnect()
```

**Success criteria:** Receives 1-min bars for VERO on Jan 16, 2026 (our +$18,583 regression stock). Compare bar count and volume to Databento data.

### Task 1.4: Halt Detection Test

```python
from ib_insync import *

ib = IB()
ib.connect('127.0.0.1', 4002, clientId=1)

contract = Stock('AAPL', 'SMART', 'USD')
ib.qualifyContracts(contract)

# Subscribe to market data including halt status
ticker = ib.reqMktData(contract, '', False, False)

def on_ticker_update(ticker):
    if ticker.halted is not None and ticker.halted != 0:
        print(f"HALT DETECTED: {ticker.contract.symbol} halted={ticker.halted}")
    # halted: -1 = N/A, 0 = not halted, 1 = regulatory, 2 = volatility

ticker.updateEvent += on_ticker_update
print("Monitoring for halts... (Ctrl+C to stop)")
ib.run()
```

**Success criteria:** Halt detection callback is wired and prints status. (May not trigger on AAPL — test on a volatile small-cap during market hours.)

---

## Phase 2: Unified Scanner (Days 3-5)

### Task 2.1: Build `ibkr_scanner.py`

This replaces scanner_sim.py, live_scanner.py, market_scanner.py, AND stock_filter.py. ONE file, ONE code path.

```python
"""
ibkr_scanner.py — Unified pre-market gap-up scanner using IBKR API.
Used by BOTH the live bot AND the backtest runner.

Live mode: reqScannerSubscription + reqMktData for real-time candidates
Backtest mode: reqHistoricalData for historical candidates on a given date
"""
```

**Core functions:**

```python
def scan_premarket_live(ib: IB) -> list[dict]:
    """Live mode: scan for pre-market gap-up candidates RIGHT NOW.
    Returns list of {symbol, gap_pct, volume, price, float_shares, rank}."""
    
def scan_historical(ib: IB, date_str: str, checkpoint_time: str) -> list[dict]:
    """Backtest mode: reconstruct what the scanner would have seen
    at checkpoint_time on date_str using historical data.
    Returns same format as scan_premarket_live."""

def get_float(symbol: str) -> float | None:
    """Float lookup: FMP → yfinance → EDGAR → AlphaVantage.
    (Reuse existing chain — this part works.)"""

def rank_candidates(candidates: list[dict]) -> list[dict]:
    """Rank by composite score: 70% volume + 20% gap + 10% float.
    (Same ranking logic as current run_megatest.py.)"""

def filter_candidates(candidates: list[dict]) -> list[dict]:
    """Apply Ross Cameron 5 Pillars:
    - Price $2-$20
    - Gap >= 10%
    - RVOL >= 2x (using IBKR ADV from reqMktData tick type 21)
    - Float < 15M
    - PM volume >= 50K
    Returns filtered + ranked list."""
```

**Key design principle:** `scan_historical()` must use the SAME RVOL computation as `scan_premarket_live()`. The ADV source must be identical. This is the whole point of the migration.

**RVOL computation (unified):**
```python
def compute_rvol(ib: IB, symbol: str, current_volume: int) -> float:
    """Compute relative volume using IBKR's average daily volume.
    Uses reqMktData tick type 21 (avgVolume) for live mode.
    Uses reqHistoricalData 20-day average for backtest mode.
    BOTH use the same underlying IBKR data source."""
```

### Task 2.2: Float Data Integration

IBKR does NOT provide float natively in its scanner. We keep the existing float lookup chain:

1. FMP API (existing, works for ~90% of tickers)
2. yfinance fallback (existing)
3. SEC EDGAR (added recently, free)
4. Alpha Vantage (added recently, free tier)

This is called AFTER the scanner returns candidates, not during scanning. The scanner uses market cap as a proxy filter (marketCapBelow=500M), then float is checked on the 10-20 results.

### Task 2.3: Output Format

Scanner outputs to `scanner_results/{date}.json` in the SAME format as current files so run_megatest.py works without changes:

```json
[
  {
    "symbol": "FEED",
    "prev_close": 1.43,
    "pm_price": 2.20,
    "gap_pct": 53.8,
    "pm_volume": 250000,
    "first_seen_et": "07:15",
    "sim_start": "07:15",
    "avg_daily_volume": 350000,
    "relative_volume": 19.2,
    "float_shares": 800000,
    "float_millions": 0.8,
    "profile": "A"
  }
]
```

---

## Phase 3: Rebuild bot.py (Days 5-8)

### Task 3.1: New Main Loop (`bot_ibkr.py`)

The new bot uses ib_insync's event-driven architecture instead of Alpaca's websocket polling:

```python
"""
bot_ibkr.py — Warrior Bot main loop using IBKR via ib_insync.

Simplified flow:
1. Connect to IB Gateway
2. Run pre-market scanner (ibkr_scanner.scan_premarket_live)
3. Subscribe to top 5 candidates (reqMktData)
4. Feed price updates to squeeze_detector / micro_pullback
5. On signal: place order via IBKR
6. Manage exits via trade_manager (squeeze exit logic)
7. At 9:30 ET: stop scanning for new symbols
8. At 12:00 ET: close any open positions, shut down
"""
```

**Key simplifications vs current bot.py:**
- No Alpaca websocket complexity
- No separate rescan thread — IBKR scanner auto-updates
- No watchlist.txt file — scanner output is in-memory
- No separate market_scanner.py / stock_filter.py — ibkr_scanner.py handles everything
- Halt detection is automatic via Tick Type 49

### Task 3.2: Refactor trade_manager.py

**Delete:** All Alpaca-specific code (TradingClient, LimitOrderRequest, etc.)
**Replace with:** ib_insync order methods
**Keep:** All exit logic (squeeze exits, stops, trailing, etc.)
**Delete:** Ross exit system, VWAP reclaim exits, parabolic regime, continuation hold variants, 3-tranche exits, conviction sizing, all disabled features

**Target: trade_manager.py drops from 3,187 lines to ~1,500 lines.**

The remaining code should handle:
- Position sizing (dynamic equity-based)
- Order placement via IBKR (entry + exit)
- Squeeze exit ladder (hard stop → max loss → trail → 2R target → runner trail)
- Daily risk management (max loss, giveback, consecutive losses)
- Halt detection response (cancel pending orders on halt, resume after)

### Task 3.3: Wire Squeeze Detector

```python
# In bot_ibkr.py:
# On each reqMktData update (~250ms):
for symbol in active_symbols:
    price = tickers[symbol].last
    # Feed to squeeze detector's 1-minute bar aggregator
    bar_builder.update(symbol, price, timestamp)

# On each 1-minute bar close:
for symbol in active_symbols:
    bar = bar_builder.get_completed_bar(symbol)
    signal = squeeze_detectors[symbol].on_bar_close_1m(bar, vwap=vwap)
    if signal:
        trade_manager.on_signal(symbol, signal)
```

---

## Phase 4: Backtest Data Migration (Days 8-10)

### Task 4.1: Rebuild scanner_sim for IBKR

Replace the current scanner_sim.py (Alpaca historical bars) with an IBKR-based version that calls `ibkr_scanner.scan_historical()`.

This generates new scanner_results/*.json files using IBKR data. The RVOL computation is now identical to live because it uses the same IBKR API.

### Task 4.2: Regenerate All Scanner Results

```bash
# Regenerate scanner_results for all dates
python3 ibkr_scanner.py --mode backfill --start 2025-01-02 --end 2026-03-25
```

This creates fresh scanner_results/*.json for every trading day using IBKR historical data. These files feed directly into run_megatest.py.

### Task 4.3: Run Fresh Megatest

```bash
python3 run_megatest.py sq_only
python3 run_megatest.py mp_sq
```

On the new IBKR-sourced scanner data. Compare results to the old Alpaca-sourced megatest. The numbers will be different — that's the point. The new numbers are trustworthy.

---

## Phase 5: Validation + Go-Live (Days 10-14)

### Task 5.1: Regression Tests

| Test | Expected | Source |
|------|----------|--------|
| VERO 2026-01-16 | +$18,583 (squeeze) | IBKR historical bars |
| ROLR 2026-01-14 | +$6,444 (squeeze) | IBKR historical bars |
| Full YTD baseline | Compare to Alpaca version | Fresh scanner_results |

### Task 5.2: Paper Trading (IBKR Paper)

Run the new bot_ibkr.py on IBKR paper account for 3-5 trading days. Focus on:
- Scanner finding the right stocks pre-market
- Squeeze detector firing signals
- Orders submitting and filling
- Exit logic triggering correctly
- Halt detection working

Paper fills won't be realistic for low-float stocks (this is true of ALL paper environments). Focus on testing the pipeline, not P&L.

### Task 5.3: Small Live Testing

Once paper validates the pipeline:
- Fund IBKR live account with initial capital
- Trade at 25% of target size (matching warmup protocol)
- 10-20 shares per signal for fill quality data
- Compare actual fills to backtest assumptions
- Build slippage model from real data
- Gradually scale up as confidence builds

---

## Environment Variable Cleanup

### Keep (Essential)
```
# Strategy
WB_SQUEEZE_ENABLED=1
WB_MP_ENABLED=0
WB_RISK_DOLLARS=1000

# Scanner
WB_MIN_GAP_PCT=10
WB_MAX_GAP_PCT=500
WB_MIN_PRICE=2.00
WB_MAX_PRICE=20.00
WB_MAX_FLOAT=15
WB_MIN_REL_VOLUME=2.0
WB_MIN_PM_VOLUME=50000

# Squeeze params
WB_SQ_VOL_MULT=3.0
WB_SQ_MIN_BAR_VOL=50000
WB_SQ_TARGET_R=2.0
WB_SQ_TRAIL_R=1.5
WB_SQ_RUNNER_TRAIL_R=2.5
WB_SQ_STALL_BARS=5
WB_SQ_MAX_LOSS_DOLLARS=500
WB_SQ_CORE_PCT=75

# Risk management
WB_MAX_DAILY_LOSS=500
WB_DAILY_GOAL=500
WB_GIVEBACK_HARD_PCT=50
WB_MAX_CONSECUTIVE_LOSSES=3
WB_BAIL_TIMER_ENABLED=1
WB_BAIL_TIMER_MINUTES=5

# Sizing
WB_MAX_NOTIONAL=50000
WB_MAX_SHARES=100000
WB_MIN_R=0.06
WB_WARMUP_SIZE_PCT=25
WB_WARMUP_SIZE_THRESHOLD=500

# IBKR
IBKR_HOST=127.0.0.1
IBKR_PORT=4002           # 4002=paper, 4001=live
IBKR_CLIENT_ID=1
```

### Delete (Everything else — ~200 env vars)
All Ross exit vars, all VWAP reclaim vars, all classifier vars, all parabolic vars, all continuation hold vars, all 3-tranche vars, all Alpaca vars, all Databento vars, all conviction sizing vars, all level map vars, all profile B vars, etc.

---

## IBKR Setup Checklist

- [x] IB Gateway installed on Mac Mini
- [ ] Enable "United States (Penny Stocks)" trading permissions in Client Portal
- [ ] Verify IBKR Pro account (not Lite) — needed for 4 AM pre-market + direct routing
- [ ] Subscribe to US equity market data package (if not already active)
- [ ] Install `ib_insync`: `pip install ib_insync`
- [ ] Install IBC for automated gateway login (optional but recommended for cron)
- [ ] Test connection with test_ibkr_connection.py
- [ ] Test pre-market scanner with test_ibkr_scanner.py
- [ ] Test historical data with test_ibkr_historical.py

---

## What NOT to Do

- Do NOT try to keep Alpaca as a fallback. Clean break. Two brokers = two code paths = the same problem we have now.
- Do NOT port the Ross exit system. It's disabled and V1 (mechanical) is proven better.
- Do NOT port the VWAP reclaim, classifier, parabolic, or level map features. They're all disabled.
- Do NOT keep live_scanner.py. It was never connected to the bot.
- Do NOT try to make IBKR paper fills "realistic." No paper environment can simulate low-float fills. Use small live lots instead.
- Do NOT keep Databento subscription during migration. Evaluate after 60 days if IBKR historical data has gaps.

---

## Success Criteria

After this migration:
1. **ONE scanner** used by both live bot and backtest — same data source, same RVOL math
2. **Scanner finds the same stocks** in backtest replay as it would have found live
3. **Backtest P&L is trustworthy** — no more "are these numbers real?" doubt
4. **Live bot detects halts** — Tick Type 49 fires on all subscribed symbols
5. **Codebase is under 8,500 lines** with fewer than 60 env vars
6. **OTC stocks are accessible** once Penny Stocks permission is enabled
7. **Fresh megatest on IBKR data** establishes the true baseline

---

## Timeline

| Phase | Days | What |
|-------|------|------|
| 1: Foundation | 1-3 | Install, connect, test scanner/data/halts |
| 2: Unified Scanner | 3-5 | Build ibkr_scanner.py, replace all 3 scanners |
| 3: Rebuild bot.py | 5-8 | New main loop, prune trade_manager.py |
| 4: Backtest Migration | 8-10 | Regenerate scanner_results, fresh megatest |
| 5: Validation | 10-14 | Regressions, paper trading, small live lots |

**Two weeks to a clean, trustworthy system.** The strategy works. The exits work. We just need plumbing that doesn't lie to us.

---

*Directive based on: Full system audit (259 env vars, 3 scanners, 11K lines), platform comparison research (Alpaca IEX/SIP split confirmed), megatest V2 results (squeeze 70% WR, 21x PF), Ross Cameron methodology analysis (Jan 2025: 74 trades, $348K). Generated by Perplexity 2026-03-25.*
