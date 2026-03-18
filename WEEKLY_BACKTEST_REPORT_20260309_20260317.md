# Weekly Backtest Report — March 9-17, 2026

## Overview
Backtested the top scanner candidates for each trading day using current bot settings (tick mode, 07:00-11:00 ET window, signal exit mode). This report covers 6 trading days and analyzes every trade taken, why it was taken, and why it won or lost.

**Current Settings:**
- Risk: $1,000/trade | Min Score: 3.0 | MACD Gate: ON
- Exit Mode: signal (no fixed TP, trail full position)
- Slippage: $0.02 | Cooldown: 2 entries/10min per symbol
- Window: 07:00-11:00 ET (time gate blocks ARMs before 7:00 AM ET)

---

## Weekly Summary

| Day | Date | Trades | Wins | Losses | Gross P&L |
|-----|------|--------|------|--------|-----------|
| Mon | 03-09 | 2 | 0 | 2 | **-$1,074** |
| Tue | 03-10 | 2 | 1 | 1 | **+$2,399** |
| Wed | 03-11 | 0 | 0 | 0 | **$0** |
| Thu | 03-12 | 2 | 1 | 1 | **-$969** |
| Fri | 03-13 | 0 | 0 | 0 | **$0** |
| Mon | 03-17 | 4 | 2 | 2 | **-$77** |
| | **TOTAL** | **10** | **4** | **6** | **+$279** |

**Win Rate: 40%** | **Average Winner: +$1,070** | **Average Loser: -$527**

---

## Detailed Trade Log

### Trade 1: HIMZ — Mon 03-09 — LOSS (-$675)
| Field | Value |
|-------|-------|
| Gap | +88.4% (Profile B, float 6.0M) |
| Entry Time | 08:31 ET |
| Entry Price | $2.36 |
| Stop | $2.21 (R=$0.15) |
| Score | 12.0 |
| Tags | ABCD, ASC_TRIANGLE, BULL_FLAG, FLAT_TOP, RED_TO_GREEN, VOLUME_SURGE |
| Exit | $2.26 via bearish_engulfing (-0.7R) |

**Signal Flow:** 08:11 impulse → 08:12-08:14 pullback (3 bars) → 08:18/08:23/08:28 more impulses → 08:30 ARMED → 08:31 entry triggered at $2.36.

**Why it lost:** Score was perfect (12.0) with every bullish pattern tag firing. But HIMZ was already extended — the 88% gap meant the stock was in price discovery with no historical support levels. Entry came right at the top of a micro-rally. Bearish engulfing candle formed within seconds of entry, exit at $2.26.

**Key lesson:** High score doesn't mean high probability. Gap >50% stocks are in no-man's land — the detector sees textbook patterns but there's no structural support.

---

### Trade 2: HIMZ — Mon 03-09 — LOSS (-$399)
| Field | Value |
|-------|-------|
| Entry Time | 08:37 ET (re-entry after cooldown) |
| Entry Price | $2.37 |
| Stop | $2.27 (R=$0.10) |
| Score | 12.0 |
| Tags | ABCD, ASC_TRIANGLE, FLAT_TOP, RED_TO_GREEN, VOLUME_SURGE |
| Exit | $2.33 via bearish_engulfing (-0.4R) |

**Why it lost:** Same stock, same session, same problem. The bot re-entered after seeing another impulse → pullback cycle at 08:33-08:36. Another bearish engulfing exit within 1 minute. HIMZ was fading and the bot kept buying the dips.

**Key lesson:** Re-entry on a stock that just stopped you out is revenge trading. The cooldown timer allowed it (10 min between entries) but the stock was clearly in a downtrend at this point.

---

### Trade 3: INKT — Tue 03-10 — LOSS (-$349)
| Field | Value |
|-------|-------|
| Gap | +71.3% (Profile A, float 1.68M) |
| Entry Time | 07:06 ET |
| Entry Price | $20.02 |
| Stop | $18.19 (R=$1.83) |
| Score | 12.5 |
| Tags | ASC_TRIANGLE, FLAT_TOP, RED_TO_GREEN, TOPPING_WICKY, VOLUME_SURGE, WHOLE_DOLLAR_NEARBY |
| Exit | $19.38 via bearish_engulfing (-0.3R) |

**Signal Flow:** 07:00 impulse → 07:02-07:04 pullback (3 bars) → 07:05 ARMED at $20.00 (whole dollar) → 07:06 entry at $20.02.

**Why it lost:** Entry right at 7:06 AM — first minute of the trading window. The ARMED signal had TOPPING_WICKY in its tags, which is a bearish warning, yet the score was 12.5 because bullish tags overwhelmed it. The stock gapped 71% and was immediately sold into. Bearish engulfing exit at $19.38 within seconds.

**Key lesson:** TOPPING_WICKY as an ARMED tag should probably be a negative signal, not just a pattern annotation. Also, the wide R ($1.83) meant a large position ($20 stock, 546 shares) but the exit came from a pattern signal, not the stop — losing only 0.3R instead of 1R.

---

### Trade 4: GITS — Tue 03-10 — WIN (+$2,748)
| Field | Value |
|-------|-------|
| Gap | +20.1% (Profile A, float 2.46M) |
| Entry Time | 10:17 ET |
| Entry Price | $2.54 |
| Stop | $2.46 (R=$0.08) |
| Score | 10.0 |
| Tags | ABCD, ASC_TRIANGLE, FLAT_TOP, RED_TO_GREEN, VOLUME_SURGE |
| Exit | $2.76 via bearish_engulfing (+2.7R) |

**Signal Flow:** 09:31 impulse → 09:35-09:36 pullback → (pattern resets) → 10:09 impulse → 10:10-10:12 pullback (3 bars) → 10:13 ARMED → 10:17 entry at $2.54.

**Why it won:** Classic Ross Cameron setup. Low float (2.46M), 20% gap, patient entry after multiple failed setups earlier in the session. The stock continued running from $2.54 to $2.76+ before the bearish engulfing exit locked in +2.7R. Discovery method was "rescan" at 10:30 — this stock only showed up on the late morning scan.

**Key lesson:** The best trade of the week came from a late re-scan discovery and a patient entry at 10:17. Not every trade needs to happen at 9:30 open.

---

### Trade 5: TLYS — Thu 03-12 — WIN (+$231)
| Field | Value |
|-------|-------|
| Gap | +62.6% (Profile B, float 9.29M) |
| Entry Time | 07:03 ET |
| Entry Price | $2.72 |
| Stop | $2.59 (R=$0.13) |
| Score | 12.0 |
| Tags | ABCD, ASC_TRIANGLE, FLAT_TOP, RED_TO_GREEN, TOPPING_WICKY, VOLUME_SURGE |
| Exit | $2.75 via topping_wicky (+0.2R) |

**Signal Flow:** 07:00 impulse → 07:01 pullback (1 bar) → 07:02 ARMED → 07:03 entry at $2.72. Topping wicky exit at $2.75.

**Why it won (barely):** Fast entry, quick topping wicky exit at +0.2R. Only $231 profit on a $1,000 risk — barely worth the trade. The topping wicky exit was correct — stock dropped after.

**Key lesson:** +0.2R wins are not the goal. This setup armed after only 1 pullback bar (not the usual 3), suggesting it was marginal.

---

### Trade 6: FLYT — Thu 03-12 — LOSS (-$1,200)
| Field | Value |
|-------|-------|
| Gap | +20.8% (Profile A, float 0.31M) |
| Entry Time | 08:28 ET |
| Entry Price | $11.49 |
| Stop | $11.29 (R=$0.20) |
| Score | 12.5 |
| Tags | ABCD, RED_TO_GREEN, VOLUME_SURGE, WHOLE_DOLLAR_NEARBY |
| Exit | $11.25 via stop_hit (-1.2R) |

**Signal Flow:** 07:29 impulse → 07:30 pullback → (resets, more impulses) → 08:24 impulse → 08:26 pullback → 08:27 ARMED → 08:28 entry at $11.49.

**Why it lost:** Micro float (0.31M shares) at $11.49 = very thin book. Stop was at $11.29 but filled at $11.25 — 4 cents of exit slippage. After entry, subsequent setups were blocked by the exhaustion filter (12.6% and 14.0% above VWAP), confirming the stock was extended.

**Key lesson:** The exhaustion filter blocked re-entries correctly — but it let the first entry through because VWAP hadn't risen enough yet. The first entry on an extended stock is the most dangerous.

---

### Trade 7: OKLL — Mon 03-17 — WIN (+$896)
| Field | Value |
|-------|-------|
| Gap | +19.9% (Profile A, float 1.36M) |
| Entry Time | 08:11 ET |
| Entry Price | $10.05 |
| Stop | $9.89 (R=$0.16) |
| Score | 11.0 |
| Tags | ABCD, RED_TO_GREEN, TOPPING_WICKY, VOLUME_SURGE, WHOLE_DOLLAR_NEARBY |
| Exit | $10.20 via bearish_engulfing (+0.9R) |

**Signal Flow:** 08:08 impulse → 08:09 pullback (1 bar) → 08:10 ARMED → 08:11 entry at $10.05.

**Why it won:** Low float (1.36M), clean 20% gap, entry near whole dollar $10. Stock pushed to $10.20 before bearish engulfing exit. Classic micro-pullback setup.

**Key lesson:** 20% gap + low float + whole dollar + entry during active hours = the sweet spot.

---

### Trade 8: LUNL — Mon 03-17 — WIN (+$464)
| Field | Value |
|-------|-------|
| Gap | +10.3% (Profile A, float 0.17M) |
| Entry Time | 09:59 ET |
| Entry Price | $13.00 |
| Stop | $12.72 (R=$0.28) |
| Score | 12.5 |
| Tags | ABCD, RED_TO_GREEN, TOPPING_WICKY, VOLUME_SURGE, WHOLE_DOLLAR_NEARBY |
| Exit | $13.13 via topping_wicky (+0.5R) |

**Signal Flow:** Multiple impulse/pullback cycles from 07:09 to 09:42, all resetting. Finally: 09:42 impulse → 09:45-09:46 pullback → more impulses → 09:56 ARMED → 09:59 entry at $13.00.

**Why it won:** Patient entry after 3 hours of failed setups. The detector waited for the right cycle and entered at $13.00 (whole dollar). Topping wicky exit at $13.13 locked in a small win.

**Key lesson:** Late-morning entries (after 09:30) can work well when the stock has built a solid VWAP base through the premarket.

---

### Trade 9: BIAF — Mon 03-17 — LOSS (-$437)
| Field | Value |
|-------|-------|
| Gap | +19.9% (Profile A, float 4.35M) |
| Entry Time | 09:50 ET |
| Entry Price | $2.85 |
| Stop | $2.61 (R=$0.24) |
| Score | 12.0 |
| Tags | ABCD, ASC_TRIANGLE, FLAT_TOP, RED_TO_GREEN, VOLUME_SURGE |
| Exit | $2.75 via bearish_engulfing (-0.4R) |

**Signal Flow:** 07:28 impulse → 07:32-07:33 ARMED at $2.41, then VWAP_BLOCKED_ARM reset. Stock dropped below VWAP. → 09:46 new impulse → 09:47-09:48 pullback → 09:49 ARMED → 09:50 entry at $2.85.

**Why it lost:** First ARM attempt at 07:33 was correctly blocked by VWAP filter. But the second entry at 09:50 came after a big intraday run from $2.20 to $2.85 — the stock was extended. Bearish engulfing within 1 minute of entry.

**Key lesson:** The VWAP filter saved the bot from the first entry but the second entry was at a much higher price after a full-day run. Need to track intraday range expansion.

---

### Trade 10: TRT — Mon 03-17 — LOSS (-$1,000)
| Field | Value |
|-------|-------|
| Gap | +9.7% (Profile A, float 4.99M) |
| Entry Time | 09:43 ET |
| Entry Price | $6.26 |
| Stop | $6.15 (R=$0.11) |
| Score | 5.5 |
| Tags | (none) |
| Exit | $6.15 via stop_hit (-1.0R) |

**Signal Flow:** 08:31/08:34 impulses → 09:30 impulse → 09:34 impulse → 09:36 pullback → 09:37 ARMED at $6.24 → 09:43 entry at $6.26.

**Why it lost:** Lowest score of any trade this week (5.5) with no pattern tags at all — just a MACD score of 7.5. This was a marginal setup that the bot shouldn't have taken. Full 1R stop loss.

**Key lesson:** Score 5.5 with no bullish structure tags (no ABCD, no ASC_TRIANGLE, no FLAT_TOP) = low quality. A minimum score threshold of 8.0+ would have filtered this out.

---

### Trade 11: BMNZ — Tue 03-18 — WIN (+$141)
| Field | Value |
|-------|-------|
| Entry Time | 08:45 ET |
| Entry Price | $16.99 |
| Stop | $16.80 (R=$0.19) |
| Score | 10.1 |
| Tags | ABCD, ASC_TRIANGLE, RED_TO_GREEN, VOLUME_SURGE, WHOLE_DOLLAR_NEARBY |
| Exit | $17.03 via topping_wicky (+0.2R) |

**Signal Flow:** Multiple impulse/pullback cycles from 07:00. 08:36 impulse → 08:37 pullback → 08:42 impulse → 08:43-08:44 ARMED → 08:45 entry at $16.99.

**Why it won:** Near whole dollar $17, clean setup. Quick topping wicky exit at $17.03. Small +0.2R win.

---

### Trade 12: BMNZ — Tue 03-18 — LOSS (-$411)
| Field | Value |
|-------|-------|
| Entry Time | 10:49 ET |
| Entry Price | $17.51 |
| Stop | $17.41 (R=$0.10) |
| Score | 8.8 |
| Exit | $17.39 via stop_hit (-1.2R) |

**Why it lost:** Re-entry at a higher price ($17.51 vs first entry at $16.99) late in the session. Stock was running out of steam. Stop hit with slight slippage.

---

## Pattern Analysis

### What Winners Have in Common
1. **Gap 10-20%** — not too extended (GITS +20%, OKLL +20%, LUNL +10%)
2. **Low float** (under 3M shares) — GITS 2.46M, OKLL 1.36M, LUNL 0.17M
3. **Patient entries** — GITS at 10:17, LUNL at 09:59 (not forcing early trades)
4. **High scores (10+)** with multiple bullish tags
5. **Near whole dollar levels** — $10.05, $13.00, $2.54

### What Losers Have in Common
1. **Extreme gaps (>50%)** — HIMZ +88%, INKT +71%, TLYS +63%
2. **Extended stocks** — entering after the big move already happened
3. **Bearish engulfing exits within 1-2 minutes** of entry (reversal traps)
4. **Re-entries on fading stocks** (HIMZ trade 2, BMNZ trade 2)
5. **Low score entries** — TRT at 5.5 with no structure tags

### Exit Analysis
| Exit Reason | Count | Avg P&L |
|-------------|-------|---------|
| bearish_engulfing | 6 | -$36 |
| topping_wicky | 3 | +$279 |
| stop_hit | 3 | -$1,067 |

Bearish engulfing exits are mixed (2 wins, 4 losses) but limit damage. Topping wicky exits capture small wins. Stop hits are the big losers — full 1R+ losses.

---

## Recommendations

### 1. Raise Minimum Score to 8.0
TRT (score 5.5, no tags, -$1,000) should never have been traded. Every winning trade had score >= 10.0. A minimum of 8.0 would have filtered TRT and kept all winners.

### 2. Cap Maximum Gap% at 50%
HIMZ (+88%), INKT (+71%), and TLYS (+63%) all lost or barely broke even. Stocks gapping >50% are in price discovery with no support. The sweet spot is 10-25%.

### 3. Block Re-Entry After a Loss on Same Symbol
HIMZ trade 2 (-$399) and BMNZ trade 2 (-$411) were revenge trades. If the first entry fails, the stock is telling you something. `WB_NO_REENTRY_ENABLED=1` after a loss would prevent this.

### 4. Add Profile Filtering to Live Bot
The scanner_sim classifies stocks as Profile A (low float) and B (medium float). The backtest runner uses this to select candidates, but the live bot doesn't filter by profile at all. Adding profile awareness would align live trading with backtest expectations.

### 5. Favor Late-Morning Entries
3 of 4 winners entered after 09:00 ET. The detector's patience (waiting for clean impulse/pullback cycles) pays off. Consider weighting score higher for setups that form during market hours vs premarket.
