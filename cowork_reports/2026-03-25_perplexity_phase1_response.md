# Perplexity Response: Phase 1 Historical Data Blocker

**Date:** 2026-03-25
**Re:** CC's Phase 1 status report — pre-market historical bars returning RTH only

---

## Manny's Account Status (Confirmed)

- Market data subscription: **ACTIVE** (US Securities Snapshot and Futures Value Bundle)
- Account type: IBKR Pro confirmed
- Penny Stocks / OTC permission: Not yet available (Financial Profile updated, 9-day wait for further changes)
- Paper account: DUQ143444
- TWS port: 7497

## Why Pre-Market Bars Are Missing

The market data subscription is active, so the data SHOULD be available. Run these diagnostics in order to isolate the cause:

### Test 1: High-Volume Stock (Rule Out Subscription Issue)

```python
from ib_insync import *

ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)

# SPY has massive pre-market volume — if this returns pre-market bars,
# the subscription is working and the issue is stock-specific
contract = Stock('SPY', 'SMART', 'USD')
ib.qualifyContracts(contract)

bars = ib.reqHistoricalData(
    contract,
    endDateTime='20260325 16:00:00 US/Eastern',
    durationStr='1 D',
    barSizeSetting='1 min',
    whatToShow='TRADES',
    useRTH=False,
    formatDate=1,
)

print(f"SPY bars: {len(bars)}")
if bars:
    print(f"First bar: {bars[0].date} (should be ~04:00 if pre-market works)")
    print(f"Last bar: {bars[-1].date}")
    # Count pre-market bars (before 09:30)
    pre_market = [b for b in bars if b.date.hour < 9 or (b.date.hour == 9 and b.date.minute < 30)]
    print(f"Pre-market bars (before 9:30): {len(pre_market)}")

ib.disconnect()
```

**If SPY returns pre-market bars:** Subscription works. Issue is VERO-specific (low pre-market volume = no trade prints = no bars with `whatToShow='TRADES'`).

**If SPY returns RTH only too:** Subscription may not be propagating to the paper account. Try the live account port instead (4001 if Gateway, 7496 if TWS).

### Test 2: Alternative Data Types (If Test 1 Shows Stock-Specific)

```python
# Try MIDPOINT instead of TRADES — captures bid/ask even when no trades print
# Small-cap pre-market often has quotes but few actual trades
for what_to_show in ['TRADES', 'MIDPOINT', 'BID_ASK', 'BID', 'ASK']:
    bars = ib.reqHistoricalData(
        contract,  # Use VERO or another small-cap
        endDateTime='20260116 16:00:00 US/Eastern',
        durationStr='1 D',
        barSizeSetting='1 min',
        whatToShow=what_to_show,
        useRTH=False,
        formatDate=1,
    )
    pre_mkt = [b for b in bars if b.date.hour < 9 or (b.date.hour == 9 and b.date.minute < 30)]
    print(f"{what_to_show:12s}: {len(bars)} total, {len(pre_mkt)} pre-market")
```

**Expected:** MIDPOINT and BID_ASK should return more pre-market bars than TRADES for small-caps, because bid/ask quotes exist even when no trades print.

### Test 3: Try reqHistoricalTicks (If Bars Don't Work)

```python
# Request actual tick-level data for the pre-market window
from datetime import datetime

contract = Stock('VERO', 'SMART', 'USD')
ib.qualifyContracts(contract)

ticks = ib.reqHistoricalTicks(
    contract,
    startDateTime='20260116 07:00:00 US/Eastern',
    endDateTime='20260116 09:30:00 US/Eastern',
    numberOfTicks=1000,
    whatToShow='TRADES',
    useRth=False,
)

print(f"Got {len(ticks)} ticks for VERO pre-market on 2026-01-16")
if ticks:
    print(f"First tick: {ticks[0]}")
    print(f"Last tick: {ticks[-1]}")
```

**If ticks work but bars don't:** We can build our own 1-min bars from tick data. More work but gives us the cleanest data possible.

### Test 4: Try Today's Date (If Historical Dates Fail)

```python
# Use empty string for endDateTime = "right now"
# This tests whether LIVE pre-market data is accessible
contract = Stock('FEED', 'SMART', 'USD')  # Today's active stock
ib.qualifyContracts(contract)

bars = ib.reqHistoricalData(
    contract,
    endDateTime='',  # Now
    durationStr='1 D',
    barSizeSetting='1 min',
    whatToShow='TRADES',
    useRTH=False,
    formatDate=1,
)

print(f"FEED today: {len(bars)} bars")
if bars:
    print(f"First bar: {bars[0].date}")
    pre_mkt = [b for b in bars if b.date.hour < 9 or (b.date.hour == 9 and b.date.minute < 30)]
    print(f"Pre-market bars: {len(pre_mkt)}")
```

### Test 5: Check Primary Exchange

```python
# IBKR sometimes needs primaryExchange specified for small-caps
contract = Stock('VERO', 'SMART', 'USD')
details = ib.reqContractDetails(contract)
for d in details:
    print(f"Symbol: {d.contract.symbol}, Primary: {d.contract.primaryExchange}, "
          f"Exchange: {d.contract.exchange}, SecType: {d.contract.secType}")
```

Small-cap stocks may need `primaryExchange='NASDAQ'` or `primaryExchange='ARCA'` explicitly set. If IBKR can't resolve the contract unambiguously, it may return limited data.

---

## Decision Tree

```
Test 1 (SPY pre-market bars?)
├── YES → Issue is small-cap specific
│   ├── Test 2 (MIDPOINT/BID_ASK has pre-market?) 
│   │   ├── YES → Use MIDPOINT for pre-market, TRADES for RTH
│   │   └── NO → Test 3 (historical ticks?)
│   │       ├── YES → Build bars from ticks
│   │       └── NO → IBKR doesn't store pre-market for this stock
│   └── Test 5 (contract resolution issue?)
└── NO → Subscription not propagating to paper account
    └── Try live account port (7496/4001)
    └── Or try: reqHistoricalData with keepUpToDate=True during live pre-market
```

## Fallback Plan (If IBKR Historical Pre-Market Is Genuinely Unavailable)

If none of the above works for small-cap pre-market historical bars, the cleanest fallback is:

**Use Databento for historical pre-market tick data (backtesting) + IBKR for everything live.**

This is NOT the three-scanner problem we had before, because:
- Live scanning: IBKR `reqScannerSubscription` (one source)
- Live data: IBKR `reqMktData` (one source)
- Live execution: IBKR `placeOrder` (one source)
- Backtest tick data: Databento (for the 4AM-9:30AM window only)
- Backtest RTH data: IBKR `reqHistoricalData` (matches live exactly)

The only "split" would be pre-market historical ticks — and Databento is genuinely good at this (we already have 33.7M ticks cached). The scanner, execution, and RTH data would all be unified on IBKR.

---

*Run these tests and report results. The most likely answer is Test 1 passes (subscription works) and Test 2 shows MIDPOINT captures pre-market for small-caps. That would be the simplest path forward.*
