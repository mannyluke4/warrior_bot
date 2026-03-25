# IBKR Migration — Phase 1 Status Update
## Date: 2026-03-25
## For: Perplexity Investigation

---

## Phase 0: COMPLETE
- V1 preserved at `/Users/duffy/warrior_bot/` on `main` branch
- V2 at `/Users/duffy/warrior_bot_v2/` on `v2-ibkr-migration` branch
- All critical files verified in v2

## Phase 1: Foundation Tests

### 1.1 Connection — PASS
```
Connected: True
Account: DUQ143444 (paper)
Port: 7497 (TWS paper, NOT 4002 — IBC starts TWS, not IB Gateway)
AAPL: last=252.97, bid=252.97, ask=253.00
```

### 1.2 Pre-Market Scanner — PASS
```python
sub = ScannerSubscription(
    instrument='STK',
    locationCode='STK.US.MAJOR',
    scanCode='TOP_PERC_GAIN',
    abovePrice=2.0,
    belowPrice=20.0,
    aboveVolume=50000,
    marketCapBelow=500000000,
    numberOfRows=20,
)
```
Returned 20 results. Visible: MKDW (rank 1), ARMG (rank 5), LUNL (rank 6) — all from today's live session.

### 1.3 Historical Data — PARTIAL (NEEDS INVESTIGATION)
```python
bars = ib.reqHistoricalData(
    contract,  # VERO
    endDateTime='20260116 16:00:00 US/Eastern',
    durationStr='1 D',
    barSizeSetting='1 min',
    whatToShow='TRADES',
    useRTH=False,  # Should include pre-market
    formatDate=1,
)
```

**Result: 390 bars, ALL regular trading hours (9:30-16:00). Zero pre-market bars.**

Also tried `endDateTime='20260116 20:00:00 US/Eastern'` — same result.

**This is a problem for our strategy.** The squeeze detector needs 7:00-9:30 AM data. If IBKR doesn't return pre-market 1-min bars for historical dates, we can't backtest the most critical trading window.

**Questions for Perplexity:**

1. **Does IBKR `reqHistoricalData` return pre-market (4:00-9:30 AM) bars for small-cap stocks?** The `useRTH=False` parameter should include extended hours, but we're getting RTH only. Is this a paper account limitation? A data subscription issue? Or does IBKR genuinely not store pre-market 1-min bar history for small-caps?

2. **Is there a different `whatToShow` value that captures pre-market?** We used `TRADES`. Other options include `MIDPOINT`, `BID`, `ASK`, `BID_ASK`. Would any of these return pre-market bars?

3. **Does the `durationStr` matter?** We used `1 D`. Would `16 H` or `86400 S` produce different results?

4. **Is this specific to the paper account (DUQ143444)?** Does a live IBKR Pro account with US equity data subscription return pre-market bars that paper doesn't?

5. **Is there a minimum trading volume threshold?** VERO is a small-cap ($3-$12 range, 1.6M float). Does IBKR only store pre-market bars for stocks with sufficient pre-market volume?

6. **What about `reqHistoricalTicks()`?** Would requesting tick-level data for the pre-market window (4:00-9:30) work as an alternative to 1-min bars?

### 1.4 Halt Detection — PASS
```
AAPL: halted=0.0 (not halted) — Tick Type 49 working
FEED: halted=nan (after hours, data not available) — expected
```

---

## Blocking Issue

The pre-market historical data gap is the only blocker. If IBKR can't provide pre-market 1-min bars for backtesting, we have three options:

1. **Use IBKR for live + Databento/Alpaca for historical pre-market** (defeats the single-source goal)
2. **Use `reqHistoricalTicks()` for pre-market and build bars ourselves** (more work but clean)
3. **Accept RTH-only backtests and validate pre-market behavior through live paper trading** (fastest but less rigorous)

Need Perplexity's input on which option is realistic before proceeding to Phase 2.

---

## Environment Notes
- IBC starts TWS (not IB Gateway) on Mac Mini — port 7497 not 4002
- ib_insync already installed in venv
- Paper account: DUQ143444
- TWS version: 10.44
