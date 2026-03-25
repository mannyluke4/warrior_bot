# Scanner Gap Analysis: Why Did We Miss These Stocks?

**Date:** 2026-03-23
**Analyst:** Cowork (Opus)
**Scope:** All profitable bot-tradeable stocks from January 2025 that the scanner missed
**Data Sources:** scanner_sim.py results, float_cache.json, backtest results, missed_stocks_backtest_plan.md

---

## Executive Summary

The bot's scanner found 5 of 68 Ross-traded tickers in January 2025 (7.4%). The January backtest proved the bot would have made +$42,818 if it had found all of them. This report examines WHY each profitable missed stock wasn't found, identifies the dominant rejection reasons, and recommends specific scanner changes.

**Key Finding:** There is no single "magic filter" to widen. The misses are spread across 5 distinct root causes, with **float ceiling** and **data availability** being the two largest categories. Fixing the scanner requires a multi-pronged approach.

---

## Current Scanner Criteria (scanner_sim.py + live_scanner.py)

| Filter | Threshold | Config Variable |
|--------|-----------|----------------|
| Price range | $2.00 – $20.00 | `MIN_PRICE`, `MAX_PRICE` |
| Gap % | ≥ 10% | `MIN_GAP_PCT` |
| Float | 100K – 10M shares | `MIN_FLOAT`, `MAX_FLOAT` |
| PM Volume | ≥ 50,000 | `MIN_PM_VOLUME` |
| Relative Volume | ≥ 2.0x | `MIN_RVOL` |
| Float unknown | **Reject** (live) / **Profile X** (sim) | `passes_float_filter()` |
| Junk filter | Preferred, warrants, units, leveraged ETFs | `is_junk_security()` |
| Data source | Alpaca active US equities | `get_all_active_symbols()` |
| Time window | Pre-market 4 AM–7:15 AM + rescan every 30 min through 10:30 AM | `SCAN_CHECKPOINTS` |

---

## Per-Stock Analysis: Why Each Profitable Miss Was Missed

### Category 1: Float Too High (>10M) — Scanner Rejects

These stocks exceed the `MAX_FLOAT=10M` ceiling. The scanner_sim `classify_profile()` returns "skip" for float >10M.

| Date | Symbol | Bot P&L | Float (M) | Gap% | Ross P&L | Setup | Notes |
|------|--------|---------|-----------|------|----------|-------|-------|
| 2025-01-06 | ARBE | **+$1,473** | 82.97 | ~+50% | +$4,200 | Nvidia news squeeze | 27M float per Ross. FMP shows 83M (shares outstanding, not float?). Either way, well above 10M. |
| 2025-01-03 | CRNC | +$154 | 43.64 | ~+20% | +$1,800 | Nvidia collaboration | Large-cap tech-adjacent. Way above float ceiling. |
| 2025-01-07 | HOTH | +$467 | 12.71 | ~+300% | +$1,000 | Momentum first-pop | Just 2.7M above ceiling. Could be recovered by raising to 15M. |
| 2025-01-15 | OSTX | -$715 | 26.88 | ~+100% | +$3,000 | Phase 2 clinical | Ross says 17M float. FMP shows 27M. Either way above 10M. |

**Subtotal: 4 stocks, +$1,379 bot P&L**

**Assessment:** ARBE and CRNC at 43-83M float are far outside Ross's own stated criteria (<20M). These are anomalies where Ross made exceptions for strong news catalysts. HOTH at 12.7M is borderline — raising the ceiling to 15M or 20M would capture it. OSTX at 17-27M is also borderline for Ross's criteria.

**Would widening help?** Raising `MAX_FLOAT` from 10M to 20M would capture HOTH (+$467) and possibly OSTX (depends on FMP vs actual float). But it would also introduce more large-float candidates that historically trade poorly for the bot — the bot's edge is in low-float squeezes.

### Category 2: No Float Data (Profile X / None) — Scanner Can't Classify

These stocks' floats couldn't be resolved by FMP or yfinance. The live scanner rejects them outright (`passes_float_filter()` returns False when float is None). The scanner_sim includes them as Profile X but the bot can't trade them.

| Date | Symbol | Bot P&L | Actual Float | Gap% | Ross P&L | Notes |
|------|--------|---------|-------------|------|----------|-------|
| 2025-01-02 | XPON | **+$3,321** | 9.3M (per notes) | +100% | +$15,000 | Float IS within range but FMP/yfinance returned None. |
| 2025-01-14 | VRME | **+$822** | Unknown | ~+30% | -$4,000 | Bot profitable on Ross's loss. No float data at all. |
| 2025-01-06 | GDTC | **+$4,393** | Unknown | +93.6% | +$5,300 | **Scanner DID find** (Profile X). Bot couldn't trade. |
| 2025-01-30 | AMOD | **+$3,642** | Unknown | +79.9% | positive | **Scanner DID find** (Profile X). Bot couldn't trade. |

**Subtotal: 4 stocks, +$12,178 bot P&L**

**Assessment:** This is the highest-value category. XPON alone is +$3,321 and had a valid float (9.3M) — the scanner just couldn't look it up. GDTC and AMOD were FOUND by the scanner but rejected because Profile X can't trade. `WB_ALLOW_PROFILE_X=0` currently blocks them.

**Would widening help?** YES — significant impact:
- Enable `WB_ALLOW_PROFILE_X=1` with safety gates (gap≥50%, pm_vol≥1M, rvol≥10x, 50% notional) → captures GDTC (+$4,393) and AMOD (+$3,642) immediately.
- Improve float resolution: Add more data sources (SEC EDGAR, Polygon.io, manual cache for frequent tickers) → captures XPON (+$3,321) and VRME (+$822).

### Category 3: Not In Data Universe (Alpaca/Databento Gaps)

These stocks had NO Databento tick data in the backtest AND are not in the float cache — strongly suggesting they're not in the NMS equity universe accessible via Alpaca/Databento. They may be OTC, pink sheets, or foreign-listed ADRs.

| Date | Symbol | Bot P&L | Ross P&L | Notes |
|------|--------|---------|----------|-------|
| 2025-01-09 | ESHA | N/A | +$15,556 | No Databento data. Likely OTC. |
| 2025-01-09 | INBS | N/A | +$18,444 | 637K float per FMP, but no Databento data. |
| 2025-01-22 | BBX | N/A | +$13,036 | No data. "BlackBox Stocks" — possibly OTC. |
| 2025-01-28 | ARNAZ | N/A | +$12,000 | No data. Daily breakout + halt resumption. |
| 2025-01-27 | AURL | N/A | green | No data. Chinese AI stock (DeepSeek). |
| 2025-01-24 | EVAC | N/A | +$5-10K | No data. GLP-1 sympathy play. |
| 2025-01-17 | AIMX | N/A | +$1,200 | No data. News breakout. |
| 2025-01-17 | ZO | N/A | +$4,864 | No data. VWAP reclaim range trading. |
| 2025-01-21 | NXX | N/A | +$1,800 | No data. News breakout. |
| 2025-01-29 | MVNI | N/A | +$3,900 | No data. Mid-morning multi-trade. |

**Subtotal: 10 stocks, bot P&L unknown (no data to backtest), Ross P&L ~$76,800**

**Assessment:** These stocks represent the LARGEST Ross P&L opportunity but are fundamentally outside our data infrastructure. They can't be found by our scanner because they don't exist in Alpaca or Databento feeds. Ross is accessing these through his broker's direct market data, which includes OTC/pink sheet stocks.

**Would widening help?** NO — not a filter issue. This requires a different data feed entirely. Options: (1) Trade Ideas scanner API, (2) Benzinga/Finviz real-time scanners, (3) IEX Cloud, (4) direct OTC Markets data.

### Category 4: Present in Data But Didn't Pass Scanner Gates (Gap/Volume/RVOL)

These stocks are in the Alpaca universe (float cache shows data OR they appear in adjacent days) but weren't in the scanner results for the day Ross traded them. The most likely explanation is insufficient pre-market volume, sub-10% gap at scan time, or late-morning emergence.

| Date | Symbol | Bot P&L | Float (M) | Probable Rejection | Ross P&L | Notes |
|------|--------|---------|-----------|-------------------|----------|-------|
| 2025-01-07 | ZENA | **+$1,865** | 8.36 | PM vol or RVOL too low at 7:15 scan | +$998 | 8M float within range. Ross found at 7:30 AM on breaking news. Scanner likely didn't have enough PM data by 7:15. |
| 2025-01-29 | SGN | **+$1,625** | 3.70 | PM vol or gap < 10% at scan time | +$13,000 | 3.7M float within range. Jan 29 scanner found only SLXN. |
| 2025-01-31 | SGN | -$179 | 3.70 | PM vol or gap < 10% at scan time | +$20,000 | Day 2 continuation. Scanner found CYCN, NCEL, IMDX — not SGN. |
| 2025-01-13 | SLRX | **+$613** | Not cached | Alpaca data issue? Or late PM emergence | +$13,000 | 1.2M float per Ross, 1200x RVOL. Should have been a screaming candidate. |
| 2025-01-21 | BTCT | **+$1,499** | 7.18 | Gap < 10% at PM scan? Or PM vol too low | +$5,500 | Scanner found BTCT on Jan 17 (26.7% gap). On Jan 21 (crypto inauguration theme), it wasn't in results despite same float. Probably insufficient pre-market gap. |
| 2025-01-22 | NEHC | **+$839** | Not cached | Data gap or PM vol insufficient | +$8,636 | "New Era Helium" — energy infrastructure. Scanner found only GELS on Jan 22. |
| 2025-01-13 | DATS | -$262 | Not cached | Continuation play (no gap?) | +$2,000 | "No-news continuation" — may not have gapped ≥10%. |
| 2025-01-10 | XHG | -$539 | Not cached | Mid-morning discovery | +$3,500 | "NO NEWS, pure momentum" — emerged mid-morning. |
| 2025-01-02 | OST | **+$6,876** | 4.90 | Gap < 10% at scan time | -$3,000 | OST found on Jan 14 (+43.8% gap) and Jan 24 (+57% gap) but NOT Jan 2. Gap may have been lower on Jan 2. |
| 2025-01-27 | JG | **+$1,327** | Not cached | Chinese stock not in Alpaca? | +$15,558 | Aurora Mobile (Chinese tech). DeepSeek AI day. May not be in Alpaca universe. |
| 2025-01-03 | SPCB | -$219 | 4.44 | PM vol or gap insufficient at scan time | +$2,600 | Day 2 continuation. Float within range (4.4M). |
| 2025-01-28 | QLGN | $0 (0 trades) | Not cached | PM vol or RVOL too low | +$2,400 | "Biotech low-float squeeze." Even if found, bot took 0 trades. |
| 2025-01-24 | ELAB | $0 (0 trades) | Not cached | Insufficient PM gap/vol | +$3-5K | "Squeeze pullback." Even if found, bot had 0 trades (MACD gate blocked). |

**Subtotal: 13 stocks, +$13,445 bot P&L (on stocks with data+trades)**

**Assessment:** This is the most actionable category. These stocks EXIST in our data universe, have float within range (where known), but failed the pre-market scanning window criteria — usually because:
- News broke after the 7:15 AM primary scan (ZENA at 7:30, SGN at open)
- Gap was insufficient at pre-market scan time but developed by open (BTCT, OST Jan 2, SPCB)
- Pure momentum/continuation plays with no pre-market gap (DATS, XHG)
- Scanner didn't have enough pre-market data volume to compute RVOL

### Category 5: Structural Limitations (Scanner Can't Detect This Setup Type)

| Date | Symbol | Bot P&L | Ross P&L | Setup | Why Structurally Unmatchable |
|------|--------|---------|----------|-------|--------------------------|
| 2025-01-28 | ARNAZ | N/A (no data) | +$12,000 | Daily chart breakout | "First candle to make new high" on DAILY chart. Not a pre-market gap play. Scanner only looks at intraday gaps. |
| 2025-01-14 | ADD | $0 (0 trades) | +$5,810 | VWAP reclaim + curl | 1989% gap — extreme PM runner. Even if scanner found it, bot took 0 trades (no ARM formed). |
| 2025-01-23 | DGNX | $0 (0 trades) | +$22,997 | IPO day 2 | 92.9M float. 36.89M in FMP. Way too large for bot. |

**Subtotal: $0 bot P&L (none tradeable even if found)**

---

## Rejection Reason Summary

| Category | # Stocks | Bot P&L | Ross P&L | % of Total Misses | Fixable? |
|----------|---------|---------|----------|-------------------|----------|
| 1. Float too high (>10M) | 4 | +$1,379 | +$10,000 | 11% | Partially (raise to 15-20M) |
| 2. No float data (Profile X) | 4 | +$12,178 | +$24,300 | 11% | **YES** (Profile X gates + better data) |
| 3. Not in data universe | 10 | N/A | ~$76,800 | 28% | Needs new data feed |
| 4. Failed scanner gates | 13 | +$13,445 | ~$77,000 | 36% | **YES** (scanner improvements) |
| 5. Structural limitations | 3 | $0 | +$40,807 | 8% | Not practical |
| **TOTAL** | **34** | **+$27,002** | **~$228,907** | | |

*Note: Groups A (control) and B (found-not-traded) from backtest are excluded since the scanner DID find those stocks.*

---

## The Filter Rejection Waterfall

To understand which filter is the biggest bottleneck, here's the rejection waterfall for the 13 "failed scanner gates" stocks — the ones that ARE in our data universe but weren't found:

| Rejection Reason | Count | Example Stocks | Estimated Impact |
|-----------------|-------|----------------|-----------------|
| **Insufficient PM data at scan time** | 5-6 | ZENA, SGN, BTCT (Jan 21), NEHC, SLRX | Stocks had news catalysts that broke after the 7:15 scan window, or PM volume was too thin to compute RVOL. |
| **Gap < 10% at scan time** | 3-4 | OST (Jan 2), SPCB (Jan 3), DATS | Continuation/momentum plays that didn't have a qualifying pre-market gap. |
| **Mid-morning emergence** | 2-3 | XHG, MVNI (if in Alpaca) | Stocks that emerged after 10:30 AM (scanner's last checkpoint). |
| **Not in Alpaca symbols** | 1-2 | JG (Chinese ADR?) | May not be in `get_all_active_symbols()` due to exchange listing. |

**The dominant pattern:** Most of these stocks had valid fundamentals (float, price, gap) but the scanner didn't have enough pre-market data to confirm them. The scanner requires BOTH gap ≥10% AND PM volume ≥50K AND RVOL ≥2.0x — all measured from Alpaca's pre-market bars ending at 7:15 AM. Stocks with breaking news after 7:00 AM or thin pre-market volume get missed even if they explode at 9:30.

The continuous rescan (8:00-10:30 AM, every 30 min) SHOULD catch these, but it only uses 30-min bar windows — it may miss stocks that spike within a window or that need intraday volume to trigger.

---

## Recommendations

### PRIORITY 1: Enable Profile X Trading (+$8,035 immediate, +$12,178 with better float data)

**What:** Set `WB_ALLOW_PROFILE_X=1` with existing safety gates (gap≥50%, pm_vol≥1M, rvol≥10x, 50% notional).

**Evidence:** GDTC (+$4,393 at 83% capture rate!) and AMOD (+$3,642, 3/3 wins, 100% win rate) were FOUND by the scanner but couldn't trade because of Profile X rejection. Both had massive gaps (93.6% and 79.9%) and huge relative volume.

**Risk:** Profile X stocks are unknowns — some may be high-float stocks that trade poorly. The 50% notional limit + strict gate thresholds (gap≥50%, rvol≥10x) provide safety.

**Implementation:** Config change only — the code already exists.

### PRIORITY 2: Improve Float Resolution (+$4,143)

**What:** Add more float data sources beyond FMP and yfinance:
- KNOWN_FLOATS dictionary expansion (add all Ross-traded tickers manually)
- SEC EDGAR bulk filing parser (shares outstanding from 10-Q/10-K)
- Polygon.io fundamentals API as tertiary fallback
- Manual override file (`float_overrides.json`) for frequently-traded tickers

**Evidence:** XPON had a valid 9.3M float but neither FMP nor yfinance could resolve it. VRME also had no data. With manual caching from Ross's recaps, we'd catch these.

**Risk:** Low — this is purely a data quality improvement. Wrong float data could misclassify stocks, but the worst case is Profile X (already handled by P1 above).

### PRIORITY 3: Faster/More Frequent Rescanning (+$5,000-8,000 estimated)

**What:** Increase rescan frequency from every 30 minutes to every 5-10 minutes. Extend the scan window to 11:00 AM.

**Evidence:** ZENA (news at 7:30 AM), SGN (news-driven gap), NEHC, and SLRX all had valid fundamentals but were missed because the scanner didn't catch their pre-market activity in time. More frequent rescans would capture stocks whose volume/gap criteria are met between the 30-minute checkpoints.

**The live scanner already does this** — it streams Databento data continuously and writes watchlist every 5 minutes. The gap is in scanner_sim.py which only rescans at fixed 30-minute intervals.

**Risk:** More candidates = more noise. Mitigated by existing rank-score system (top 5 only trade).

### PRIORITY 4: Lower Gap Threshold for Intraday Movers (+$1,000-3,000 estimated)

**What:** Add a secondary scan pass with relaxed criteria for stocks showing momentum patterns AFTER the open:
- Gap ≥ 5% (vs 10%) for stocks with intraday volume surge (>3x avg first-hour volume)
- Only applies after 9:30 AM when RTH data is available
- Capped at 2 additional candidates per rescan

**Evidence:** DATS (+$2,000 Ross, continuation play), XHG (+$3,500 Ross, pure momentum), SPCB (continuation) didn't have pre-market gaps ≥10% but were big movers intraday. Ross catches these because his scanner runs on a shorter threshold ("hitting scanners at +10%" per his quote, but he also watches momentum through the morning).

**Risk:** More candidates from lower-quality setups. The bot's SQ strategy already gates quality via volume explosion and squeeze detection — a lower gap threshold just gets them on the radar, it doesn't force trades.

### PRIORITY 5: Float Ceiling Adjustment (Conditional, +$467-2,000)

**What:** Raise `MAX_FLOAT` from 10M to 15M (NOT 20M).

**Evidence:** Only HOTH (12.7M float, +$467) would be captured by raising to 15M. ARBE (83M) and CRNC (44M) are way above any reasonable ceiling. OSTX (17-27M) is borderline.

**Risk:** More large-float stocks = potentially worse SQ performance. The bot's edge is strongest in <10M float squeezes. Analysis showed scanner rank score already captures float quality — raising the ceiling may not help much.

**Recommendation:** Test 15M vs 10M in the next megatest run. If the additional candidates are net profitable, keep it. Don't go above 20M.

### PRIORITY 6: Alternative Data Feeds (Long-term, highest potential)

**What:** Integrate a secondary scanner source that covers OTC/pink sheet/non-NMS stocks.

**Evidence:** 10 stocks (28% of misses) had zero data in Databento/Alpaca. These included ESHA (+$15,556 Ross), INBS (+$18,444 Ross), BBX (+$13,036 Ross), ARNAZ (+$12,000 Ross). Combined Ross P&L: ~$76,800.

**Options:**
1. **Trade Ideas API** — Ross uses Trade Ideas for his scanner. Direct integration.
2. **Benzinga Newsfeed** — Real-time news + gap scanner. Covers broader universe.
3. **IEX Cloud** — Broader equity coverage including OTC-eligible names.
4. **Polygon.io real-time** — Alternative to Databento with broader symbol coverage.

**Risk:** Additional API costs. OTC stocks have wider spreads and thinner books — bot execution may suffer. Need a separate risk profile for OTC names.

---

## Impact Model: Expected P&L Improvement by Fix

| Priority | Fix | Expected Monthly Bot P&L Gain | Effort | Confidence |
|---------|-----|------------------------------|--------|------------|
| P1 | Enable Profile X | +$8,035/mo | Config change | **HIGH** (proven in backtest) |
| P2 | Better float data | +$4,143/mo | 2-3 days | **HIGH** (XPON was valid 9.3M float) |
| P3 | Faster rescanning | +$3,000-5,000/mo | Already live (live_scanner) | **MEDIUM** (depends on news timing) |
| P4 | Lower intraday gap | +$1,000-3,000/mo | 1 day | **LOW** (untested hypothesis) |
| P5 | Float ceiling 15M | +$467-2,000/mo | Config change | **LOW** (only HOTH clearly benefits) |
| P6 | Alt data feeds | +$5,000-15,000/mo | Weeks | **MEDIUM** (huge upside but execution risk) |
| **Total** | | **+$21,645 – $37,178/mo** | | |

*Based on January 2025 data. Actual results will vary.*

---

## What We Should NOT Change

1. **Don't lower RVOL below 2.0x** — Analysis from prior session showed scanner rank score already captures RVOL signal effectively. Going to 1.5x would add noise without quality.

2. **Don't remove the 10% gap minimum for pre-market** — This is Ross's stated criterion. Sub-10% pre-market gaps are continuation/momentum plays that require a fundamentally different detection approach (P4 handles this separately).

3. **Don't raise MAX_FLOAT above 20M** — ARBE (83M) and CRNC (44M) are anomalies, not patterns. The bot's SQ strategy works best on low-float squeezes.

4. **Don't add news feed as a PRIMARY filter** — News is extremely hard to parse in real-time. Gap% + RVOL + PM volume serve as effective proxies for "something unusual is happening."

---

## Recommended Implementation Order

1. **Immediate (CC directive):** Enable `WB_ALLOW_PROFILE_X=1` in .env, run January 2025 backtest with Profile X enabled. Verify GDTC and AMOD results.

2. **Next directive:** Expand KNOWN_FLOATS dictionary with all January 2025 Ross tickers we have actual float data for. Add float_overrides.json mechanism for manual entries.

3. **Scanner_sim improvement:** Verify continuous rescan is working correctly — scanner_sim found 0 stocks via "Continuous rescan" method across all of January (all were "premarket" or "precise"). This suggests the rescan function may not be surfacing new candidates effectively.

4. **Megatest validation:** Run full megatest with Profile X enabled + expanded floats to confirm net P&L improvement across 49+ days, not just January.

5. **Research phase:** Evaluate Trade Ideas API or Polygon.io for broader symbol coverage.

---

*Report compiled 2026-03-23 by Cowork (Opus). Cross-referenced: scanner_sim.py, live_scanner.py, float_cache.json, scanner_results/2025-01-*.json, backtest results, missed_stocks_backtest_plan.md*
