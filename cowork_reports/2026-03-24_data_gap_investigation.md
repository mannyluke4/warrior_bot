# Scanner Data Gap Investigation — Final Report

**Date:** 2026-03-24
**Source:** Perplexity deep research (SEC EDGAR, exchange databases, news archives, video cross-reference)

---

## Executive Summary

Of the 10 "zero data" tickers from January 2025, **6 are transcription errors** from the video recaps, **2 are confirmed NASDAQ stocks** that should be in our data feeds, **1 was inactive/not trading**, and **1 remains unidentified**. The majority of the "missing" P&L is recoverable without changing data providers.

| Category | Count | Est. Ross P&L | Action |
|----------|-------|---------------|--------|
| Transcription errors (real ticker identified) | 5 | ~$44,290 | Fix ticker in master CSV, re-check scanner |
| Confirmed NASDAQ (should be in Databento/Alpaca) | 2 | ~$33,900 | Investigate why Databento missed them |
| Ticker inactive in Jan 2025 | 1 | ~$5-10K | Remove from analysis — not a real trade |
| Unidentifiable | 2 | ~$3,000 | Accept loss — likely transcription artifacts |

---

## Ticker-by-Ticker Findings

### 1. ESHA — ESH Acquisition Corp ✅ CONFIRMED NASDAQ

| Field | Value |
|-------|-------|
| Exchange (Jan 2025) | **NASDAQ Global Market** |
| Company | ESH Acquisition Corp (SPAC) |
| Ross P&L | +$15,556 |
| Ross Date | Jan 9, 2025 |
| Status | Active — pending merger with The Original Fit Factory |
| Related Tickers | ESHU (units), ESHAR (rights). No warrants. |

**Root cause of data gap:** Likely a SPAC with very low pre-market volume or Alpaca's `get_all_active_symbols()` filtered it out as low-liquidity. ESHA is a legitimate NASDAQ stock that Databento's XNAS feed should cover.

**Action:** Check if ESHA appears in Databento's symbol directory for January 2025. If yes, it's a scanner filter issue (gap%, volume, float thresholds). If no, it's a Databento SPAC coverage gap.

---

### 2. INBS — Intelligent Bio Solutions ✅ CONFIRMED NASDAQ

| Field | Value |
|-------|-------|
| Exchange (Jan 2025) | **NASDAQ Capital Market** |
| Company | Intelligent Bio Solutions Inc |
| Ross P&L | +$18,444 |
| Ross Date | Jan 9, 2025 |
| Float (Jan 2025) | ~4-5M shares pre-split (not 637K — that was a later figure) |
| Status | Active. Did 1-for-10 reverse split December 2025. |

**Root cause of data gap:** Same as ESHA — this is a legitimate NASDAQ stock. The 637K float figure in the directive was incorrect (that's a post-reverse-split number). Actual Jan 2025 float was 4-5M shares, which is within our scanner parameters.

**Action:** Same as ESHA — check Databento symbol coverage. This should be findable.

---

### 3. BBX → **BLBX (Blackboxstocks Inc)** 🔄 TRANSCRIPTION ERROR

| Field | Value |
|-------|-------|
| Correct Ticker | **BLBX** (NASDAQ) |
| Wrong Ticker | BBX (transcript misread) |
| Company | Blackboxstocks Inc |
| Ross P&L | Part of Jan 22 recap |
| Ross Date | Jan 22, 2025 |
| Jan 22 Price Action | Open $3.33 → High $6.00, +226% on 237.5M shares |
| Catalyst | $2M financing for potential merger ([GlobeNewswire](https://www.globenewswire.com/news-release/2025/01/22/3013413/0/en/Blackboxstocks-Inc-Secures-Financing-of-up-to-2-000-000-in-Anticipation-of-Potential-Merger.html)) |

**Root cause:** The transcript AI misread "BLBX" as "BBX" from the video. Ross said "Blackbox Stocks" which trades as BLBX on NASDAQ. BBX Capital (OTC: BBXIA/BBXIB) is a completely different company with no material news on that date.

**Action:** Update master CSV: BBX → BLBX. BLBX is NASDAQ-listed and already appears in our recap data under the correct ticker for Jan 22. Our scanner should find BLBX — it was up 226% on massive volume.

---

### 4. ARNAZ → **RNAZ (TransCode Therapeutics)** 🔄 TRANSCRIPTION ERROR

| Field | Value |
|-------|-------|
| Correct Ticker | **RNAZ** (NASDAQ) |
| Wrong Ticker | ARNAZ (transcript misread — Ross pronounces it "AR-naz") |
| Company | TransCode Therapeutics Inc |
| Ross P&L | +$12,234 |
| Ross Date | Jan 28, 2025 |
| Jan 28 Price Action | Open $161.84 → High $327.88, 100%+ intraday with circuit breaker halts |
| Evidence | Ross confirmed on camera (Feb 5, 2026 video) calling RNAZ "ARnaz". ClayTrader's Jan 28 video also lists RNAZ as the halting stock of that day. Jan 29 scanner watchlist includes RNAZ. |

**Root cause:** Ross pronounces the ticker "AR-naz" and the transcript AI interpreted the leading "AR" sound as part of the ticker, producing "ARNAZ" instead of "RNAZ".

**Action:** Update master CSV: ARNAZ → RNAZ. RNAZ is NASDAQ-listed. Check if our scanner found it on Jan 28 — at $161+ price, it's above our $20 max price filter, so the scanner would correctly exclude it. This is a Ross trade outside our price parameters, not a data gap.

---

### 5. AURL → **JG (Aurora Mobile Limited)** 🔄 TRANSCRIPTION ERROR

| Field | Value |
|-------|-------|
| Correct Ticker | **JG** (NASDAQ) |
| Wrong Ticker | AURL (transcript confusion with "Aurora") |
| Company | Aurora Mobile Limited (Chinese AI/tech company) |
| Ross P&L | +$15,558 (our master CSV already has JG correctly for Jan 27) |
| Ross Date | Jan 27, 2025 |
| Context | DeepSeek AI hype day — JG integrated DeepSeek R1 LLM |
| Evidence | Ross's Jan 27 video "Day Trading DeepSeek Breaking News" explicitly confirms JG as his primary trade |

**Root cause:** "AURL" was likely a transcript artifact from Ross saying "Aurora" (JG = Aurora Mobile). Our master CSV already has JG correctly logged for Jan 27 with +$15,558. This is a **duplicate entry** — not a missing stock.

**Action:** Remove AURL from the "missing" list entirely. JG is already in the master CSV and is already in our scanner results (NASDAQ-listed, within price range).

---

### 6. ZO → **ZEO (Zeo Energy Corp)** 🔄 TRANSCRIPTION ERROR

| Field | Value |
|-------|-------|
| Correct Ticker | **ZEO** (NASDAQ) |
| Wrong Ticker | ZO (truncated — the "E" was dropped in transcription) |
| Company | Zeo Energy Corp |
| Ross P&L | Part of Jan 17 recap |
| Ross Date | Jan 17, 2025 |
| Jan 17 Price Action | Up 52.99%, trading $2.88-$3.88 on 33.5M shares |
| Catalyst | Green technology announcement |

**Root cause:** The transcript dropped the "E" from ZEO, producing "ZO". Our Jan 17 recap notes already mention ZEO as a stock Ross discussed. ZEO is NASDAQ-listed.

**Action:** Update master CSV: ZO → ZEO. Check if our scanner found ZEO on Jan 17 — it was up 53% with huge volume in our price range. This should be findable.

---

### 7. EVAC — ⛔ DID NOT TRADE IN JANUARY 2025

| Field | Value |
|-------|-------|
| Status | **No security traded as EVAC on any exchange in January 2025** |
| History | Edwards Group Limited (EVAC on NASDAQ) was acquired and delisted January 10, 2014. EQV Ventures Acquisition Corp II (EVAC on NYSE) didn't IPO until July 2, 2025. |
| Gap | Between January 2014 and July 2025, EVAC was a dormant/delisted ticker |

**Root cause:** The transcript extracted "EVAC" from a Jan 24 recap, but no stock traded under this ticker in January 2025. This is either a transcription error for a different ticker, or Ross mentioned a ticker that was displayed incorrectly in the video overlay.

**Action:** Remove from analysis. This is not a recoverable data gap — the stock didn't exist as a tradeable security in January 2025.

---

### 8. AIMX — ❓ UNIDENTIFIED (Low Confidence)

| Field | Value |
|-------|-------|
| Best guess | AIXI (Xiao-I Corporation, NASDAQ) |
| Confidence | LOW |
| Ross P&L | +$1,200 |
| Ross Date | Jan 17, 2025 |
| Evidence | AIXI is an AI-named ticker that moved $5.37→$5.86 on Jan 17 with small volume. The visual/phonetic match AIMX→AIXI is plausible but unconfirmed. |

**Action:** Flag as unidentifiable. At +$1,200, this is low-impact. If AIXI, it's NASDAQ-listed and within our universe.

---

### 9. NXX — ❓ UNIDENTIFIED (Low Confidence)

| Field | Value |
|-------|-------|
| Best guess | Unknown — no strong match found |
| Confidence | LOW |
| Ross P&L | +$1,800 |
| Ross Date | Jan 21, 2025 |
| Context | Entry ~$5.45, targeting $6, with 3000 shares on bounce trade |

**Action:** Flag as unidentifiable. At +$1,800, this is moderate impact but without a confirmed ticker, we can't act on it.

---

### 10. MVNI / NVNI — ⚠️ PRICE MISMATCH (Transcription Error)

| Field | Value |
|-------|-------|
| Ticker in CSV | NVNI |
| Ticker from "missing" list | MVNI |
| Problem | **NVNI traded at $0.15-$0.55 in January 2025** — the $6.00 entry price in our master CSV is impossible |
| Ross Date | Jan 29, 2025 |
| Context | Entry $6.00, exit $6.50, +$3,920, "daily breakout, resistance at $6.86" |

**Root cause:** The master CSV entry for NVNI on Jan 29 at $6.00 has the wrong ticker. NVNI (Nvni Group Limited) was a sub-$0.50 penny stock in January 2025. The actual stock Ross traded at $6.00 on Jan 29 with resistance at $6.86 has not been identified. Note: the Jan 29 scanner watchlist from the video also shows "RNAZ" alongside NVNI, suggesting possible confusion.

**Action:** Flag the NVNI Jan 29 entry in the master CSV as incorrect ticker. The actual stock is unidentified. At +$3,920 this is moderate impact.

---

## Summary: What's Actually Recoverable

### Confirmed NASDAQ stocks we should find (investigate Databento coverage):
| Ticker | Ross P&L | Priority |
|--------|----------|----------|
| ESHA | +$15,556 | HIGH — SPAC on NASDAQ, check Databento XNAS |
| INBS | +$18,444 | HIGH — NASDAQ Capital Market, should be in feeds |
| **Subtotal** | **+$34,000** | |

### Transcription errors now corrected (check if scanner finds them):
| Wrong Ticker | Correct Ticker | Exchange | Ross P&L | Already in Scanner? |
|-------------|---------------|----------|----------|---------------------|
| BBX | **BLBX** | NASDAQ | Part of Jan 22 | Check |
| ARNAZ | **RNAZ** | NASDAQ | +$12,234 | No — $161+ price exceeds our $20 max |
| AURL | **JG** | NASDAQ | +$15,558 | Already in CSV correctly — DUPLICATE |
| ZO | **ZEO** | NASDAQ | Part of Jan 17 | Check |

### Not recoverable:
| Ticker | Reason | Ross P&L |
|--------|--------|----------|
| EVAC | Did not trade in Jan 2025 | ~$5-10K (remove) |
| AIMX | Unidentifiable | +$1,200 |
| NXX | Unidentifiable | +$1,800 |
| MVNI/NVNI | Wrong ticker, real stock unidentified | +$3,920 |

---

## Recommendations

1. **Immediate: Fix master CSV** — Update BBX→BLBX, ARNAZ→RNAZ, ZO→ZEO, remove AURL (duplicate of JG), remove EVAC (didn't exist), flag NVNI Jan 29 as incorrect.

2. **Investigate Databento SPAC coverage** — ESHA and INBS are both NASDAQ-listed and represent +$34K of Ross's P&L. If Databento doesn't carry them, this is a legitimate data gap worth escalating. If Databento does carry them, it's a scanner filter issue.

3. **Check scanner for BLBX and ZEO** — Both are NASDAQ stocks that had massive moves on their respective dates. If our scanner missed them, it's a filter tuning issue (gap%, float, RVOL thresholds).

4. **Accept RNAZ as out-of-scope** — At $161+ per share, RNAZ is well above our $20 max price filter. This is by design — Ross's trade was outside our parameters.

5. **Net impact of corrections:** The "10 stocks with zero data" problem shrinks to **2 genuinely missing NASDAQ stocks** (ESHA, INBS worth +$34K) plus **2-3 scanner filter misses** (BLBX, ZEO). The rest are transcription errors, duplicates, or non-existent stocks.

---

*Sources: SEC EDGAR filings, NASDAQ symbol directory, GlobeNewswire press releases, Ross Cameron YouTube recaps (Jan 2025), ClayTrader Jan 28 video analysis, StocksToTrade news archive, Investing.com historical prices, Yahoo Finance historical data*
