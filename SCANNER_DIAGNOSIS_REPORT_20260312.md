# SCANNER DIAGNOSIS — FINDINGS REPORT
## For Perplexity | March 12, 2026

---

## CONTEXT

We ran a 5-date backtest (Jan 2 2025, Nov 5 2025, Nov 6 2025, Jan 6 2026, Feb 3 2026) and found almost zero overlap between Ross's actual trades and the bot's scanner candidates. Claude Code diagnosed all 10 Ross tickers to find out exactly why.

---

## THE ANSWER: THE SCANNER ISN'T BROKEN

The overlap problem is not a filter calibration issue. It's structural. The scanner is correctly built to find **premarket gap-ups** (gap ≥5%, price $2-$20, float 100K-50M, window 4AM-11AM). Ross doesn't only trade premarket gap-ups.

---

## FINDINGS BY CATEGORY

### Category 1: Ross Traded Intraday Patterns, Not Gap-Ups (3 stocks, +$6,500)

| Ticker | Ross P&L | What Actually Happened |
|--------|----------|------------------------|
| OPTX | +$3,600 | Gapping DOWN -7.3% premarket. Ross caught an intraday squeeze at 8:26 AM. |
| SPCB | +$2,400 | Gapping DOWN -33% premarket. Ross caught the bounce from $3.70 to $4.50. Alpaca shows open at $5.55 — price mismatch possibly a pre-split artifact. |
| ALM | +$500 net | Flat (-1.4% gap), 167M float. An intraday breakout, not a gap-up. |

**Implication:** These are gap-DOWN reversals and intraday momentum plays. They require a fundamentally different scanner. Adding them would mean expanding the strategy, not fixing a filter.

---

### Category 2: No Alpaca Data (3 stocks, FTEEL was +$3,224)

| Ticker | Ross P&L | Status |
|--------|----------|--------|
| FTEEL | +$3,224 | Zero Alpaca data — prev close, premarket, and regular hours all missing |
| NUAAI | -$400 | Zero Alpaca data (Ross lost — missing it helped) |
| CERO | untested | Zero Alpaca data + prev close was $0.095 (penny stock, sub-$2 filter would block anyway) |

**Implication:** FTEEL is the only meaningful data gap loss. Databento may have it — worth checking. But this is 1 stock across 5 dates. Not a systemic scanner failure.

---

### Category 3: Late Mover — Actionable Miss (1 stock, +$3,500)

| Ticker | Ross P&L | What Happened |
|--------|----------|----------------|
| ELAB | +$3,500 | +50% gap, 2.1M float, $8.46 price — passes all filters. But zero Alpaca premarket bars before 9:05 AM. Scanner only checks 4:00-7:15 AM premarket window. |

**Implication:** This is the one legitimate scanner fix. ELAB had no premarket trading on Alpaca — the gap happened overnight with no PM activity. A supplemental check at 9:30-9:35 AM for stocks that gap ≥5% at open (vs. prev close) but had no PM bars would catch ELABs. **Low risk** — same float/price/gap filters apply, 8-symbol cap still enforced.

---

### Category 4: Sub-$2 Penny Stocks (2 stocks, -$4,826 — good misses)

| Ticker | Ross P&L | Why Filtered |
|--------|----------|--------------|
| LNAI | -$3,926 | Price $1.19 (under $2 floor), gap only +1.7%, unknown float |
| CCTG | -$900 | Price $0.84 premarket (under $2 floor) — had a 35.7% gap and good float, but price too low |

**Implication:** Both were losers for Ross. The $2 minimum filter saved us money here. Do NOT lower it.

---

### Category 5: Already on the Scanner (1 stock, +$852)

| Ticker | Ross P&L | Status |
|--------|----------|--------|
| AEI | +$852 | Correctly identified — 58.7% gap, 3.86M float, top candidate Jan 2. Bot had it but lost on the trade. Entry execution, not scanner. |

---

## SUMMARY TABLE

| Root Cause | # Stocks | Ross P&L Impact | Action Needed? |
|------------|----------|-----------------|----------------|
| Intraday plays (not gap-ups) | 3 | +$6,500 | No — different strategy |
| No Alpaca data | 3 | +$3,224 (FTEEL) | Maybe — check Databento for FTEEL |
| Late mover (no PM bars) | 1 | +$3,500 (ELAB) | Yes — 9:30 gap-at-open check |
| Sub-$2 penny (correctly filtered) | 2 | -$4,826 | No — filters working correctly |
| Already on scanner | 1 | +$852 | No — execution issue, not scanner |

---

## BUG FOUND: Gap Threshold Mismatch

`scanner_sim.py` uses **10% gap minimum** (line 265).  
`live_scanner.py` uses **5% gap minimum** (line 52).

The 5-date backtest ran with the stricter 10% threshold. No Ross stocks were affected by this mismatch (the ones with gaps had gaps well above 10%; the ones without gaps were negative), but it needs to be corrected so backtest results match live behavior.

---

## WHAT THIS MEANS FOR STRATEGY

The scanner overlap problem is **primarily a strategy scope question**, not a filter fix.

Ross trades multiple patterns:
- Premarket gap-ups (what the bot scans for) ✅
- Intraday momentum plays (gap-downs that squeeze, flat-opens that break out) ❌ not in scope
- Catalyst-driven bounces ❌ not in scope

If we want the bot to trade what Ross trades, we need to decide: **expand the scanner** to cover intraday patterns, or **stay in the gap-up lane** and accept that we'll miss some of Ross's trades.

Given the data, staying in the gap-up lane and fixing execution quality (via the Setup Quality Gate) is likely the higher-ROI path. The intraday plays are harder to systematize and carry higher execution risk.

---

## RECOMMENDED NEXT STEPS (Already In Progress)

1. **Scanner fix (Claude Code — in progress):** Align scanner_sim.py gap threshold to 5% (match live_scanner.py). Add 9:30 gap-at-open supplemental check for ELAB-type stocks.

2. **Setup Quality Gate (Claude Code — queued):** The bigger lever. The scanner IS finding some right stocks — the problem is the bot takes low-quality entries on them. 5 binary gates based on Ross's actual entry criteria (clean pullback, impulse strength, no re-entry after loss, etc.).

3. **Perplexity research question:** Is it worth building an intraday momentum scanner in addition to the gap-up scanner? What would that architecture look like? OPTX (+$3,600) and SPCB (+$2,400) suggest there's edge there, but the strategy would be materially different.

---

*Diagnosis executed by Claude Code | Compiled by Duffy | March 12, 2026*
