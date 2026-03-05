# Scanner Sim Status Report
**Date:** 2026-03-05  
**Prepared by:** Duffy  
**Branch:** scanner-sim-backtest

---

## Status: RUNNING CORRECTLY — No Gap Bug

The gap calculation is correct. Earlier concern was a false alarm — I was double-multiplying in the analysis script. Raw JSON data has correct values.

## Results Summary (4 of 5 dates complete)

| Date | Market | Candidates | Profile A | Profile B | Profile X |
|------|--------|------------|-----------|-----------|-----------|
| 2026-01-13 | Hot | 30 | 0 | 0 | 30 |
| 2026-01-15 | Hot | 39 | 5 | 15 | 19 |
| 2026-02-10 | Cold | 48 | 8 | 15 | 25 |
| 2026-02-12 | Cold | 81 | 14 | 16 | 51 |
| 2026-03-04 | Hot | TBD | TBD | TBD | TBD |

## Issues Found

### Issue 1: Jan 13 has ZERO A/B classifications
All 30 candidates on Jan 13 classified as Profile X because yfinance returned null float for every stock. The candidates are real (SPRC +80%, ATON +60%, ELAB +27% etc.) but float data is missing.

**Root cause:** yfinance doesn't have float data for many micro/small-cap stocks that are no longer publicly traded or have been delisted. Jan 13 stocks were apparently all in this category.

**Impact:** We can't classify these without float data. Need an alternative float source for historical small-caps.

**Possible fix:** 
- Use FMP (Financial Modeling Prep) free tier for float data — better coverage of small-caps
- Use Alpaca's asset data which may include shares_outstanding
- Hardcode known floats from the study data (SPRC is a known Profile A stock)

### Issue 2: node_modules committed to repo
The playwright npm package was accidentally committed. Needs a .gitignore entry for `node_modules/`.

### Issue 3: Mar 4 not yet run
The 5th test date (2026-03-04) hasn't been scanned yet.

## Sample Profile A Candidates Found

**Jan 15 (Hot market):**
- MTVA: +63.6% gap, 0.98M float, Profile A ✅
- GCDT: +16.7% gap, 3.04M float, Profile A ✅  
- ICON: +12.9% gap, 0.69M float, Profile A ✅
- WOK: +11.0% gap, 1.22M float, Profile A ✅
- AGPU: +13.7% gap, 1.82M float, Profile A ✅

**Feb 10 (Cold market):**
- TNMG: +26.6% gap, 1.15M float, Profile A ✅ (known regression stock!)
- PLYX: +24.4% gap, 1.34M float, Profile A ✅
- XHLD: +23.5% gap, 1.27M float, Profile A ✅
- MNTS: +16.2% gap, 1.34M float, Profile A ✅ (known study stock!)
- FEED: +14.3% gap, 0.85M float, Profile A ✅
- EIKN: +11.9% gap, 1.50M float, Profile A ✅
- SKIL: +10.7% gap, 4.50M float, Profile A ✅
- VRCA: +13.1% gap, 3.32M float, Profile A (7:15 AM) ✅

**TNMG and MNTS are both in the 137-stock study — scanner sim is finding the RIGHT stocks. ✅**

## Next Steps

1. Fix Jan 13 float lookup (FMP or alternative source)
2. Run Mar 4 scan
3. Fix .gitignore for node_modules
4. Run backtests on all A/B candidates via simulate.py
5. Compare vs WT scanner data

---

*Prepared by Duffy — 2026-03-05*
