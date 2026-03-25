# Phase 1 Test Results — For Perplexity
## Date: 2026-03-25
## Issue: "Connected from different IP" resolved by killing stale TWS + logging out other devices

---

## Results

### Test 1: SPY Pre-Market — PASS
```
Bars: 717
First: 2026-03-25 04:00:00-04:00
Pre-market bars: 330 (starting at 04:00)
First PM vol: 1,757
```
**Subscription is active. Pre-market data works for exchange-listed stocks.**

### Test 2: VERO Data Types — ALL FAIL (0 pre-market)
```
TRADES      : 390 total, 0 pre-market
MIDPOINT    : 390 total, 0 pre-market
BID_ASK     : 390 total, 0 pre-market
```
**VERO is on PINK exchange (OTC). IBKR does not store pre-market history for OTC stocks.**

### Test 3: VERO Historical Ticks — FAIL
```
Ticks: 0
```
**No tick-level pre-market data for OTC stocks either.**

### Test 4: FEED Today — PASS
```
Bars: 717
First: 2026-03-25 04:00:00-04:00
Pre-market bars: 330 (starting at 04:00)
First PM vol: 965
```
**FEED is NASDAQ-listed. Full pre-market history available.**

### Test 5: VERO Contract Details
```
Symbol=VERO Primary=PINK Exchange=SMART
```
**Confirmed OTC/PINK — explains the data gap.**

---

## Diagnosis

Following Perplexity's decision tree:
```
Test 1 (SPY pre-market?) → YES
└── Issue is stock-specific (OTC vs exchange-listed)
    └── VERO is PINK/OTC → IBKR doesn't store pre-market for OTC
    └── FEED is NASDAQ → Full pre-market available
```

**Pre-market data works for ALL exchange-listed stocks.** The gap is OTC-only.

---

## Impact on Migration

**Low impact.** Most of our squeeze candidates are exchange-listed (NASDAQ, ARCA, NYSE). The stocks we trade daily (FEED, MKDW, ARTL, ANNA, etc.) are all exchange-listed and will have full pre-market data from IBKR.

**VERO regression stock is OTC** — we'll need Databento or Alpaca for VERO's pre-market tick data in backtesting only. This is the fallback Perplexity described: IBKR for everything live + exchange-listed historical, Databento for OTC pre-market historical only.

**OTC trading permissions** are pending (9-day wait from financial profile update). Once enabled, IBKR may provide pre-market data for OTC stocks on the live feed — but historical pre-market for OTC may still be unavailable. Need to test once permissions are active.

---

## Questions for Perplexity

1. **Once OTC permissions are enabled, will IBKR historical data include pre-market for OTC stocks?** Or is this a permanent limitation of PINK exchange data?

2. **For the VERO regression: should we keep Databento tick cache as the pre-market data source for OTC backtesting?** The tick_cache already has 1.7M VERO ticks. simulate.py can continue using those.

3. **Should we proceed with Phase 2 (unified scanner) now?** The pre-market data issue only affects OTC backtesting, not the live scanner or execution pipeline. We can build the scanner and handle the OTC data gap as a separate concern.

---

## Next Steps (Recommended)

1. **Proceed to Phase 2** — the scanner doesn't need historical pre-market bars (it uses live reqScannerSubscription)
2. **Keep existing tick_cache** for OTC stock backtesting (VERO, etc.)
3. **Test OTC pre-market data again** once penny stock permissions are active (~1 week)
4. **Update IBKR port in config**: use 7497 (TWS paper), not 4002 (IB Gateway)
