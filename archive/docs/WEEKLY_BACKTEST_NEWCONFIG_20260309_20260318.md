# Weekly Backtest Report — New Config (Synced .env)
## March 9-18, 2026

## Overview
Re-ran all backtests after syncing the Mac Mini `.env` to match the MacBook Pro's optimized settings. This report compares old vs new config results and provides detailed trade analysis.

**Key Config Changes:**
| Setting | Old (Mac Mini) | New (Synced) |
|---------|---------------|-------------|
| `WB_MAX_LOSS_R` | 2.0 | **0.75** |
| `WB_MIN_GAP_PCT` | 5 | **10** |
| `WB_MAX_GAP_PCT` | 999 | **500** |
| `WB_MAX_FLOAT` | 50 | **10** |
| `WB_MIN_REL_VOLUME` | 1.5 | **2.0** |
| `WB_MAX_NOTIONAL` | 60000 | **50000** |
| `WB_CLASSIFIER_ENABLED` | missing | **1** |
| `WB_CONTINUATION_HOLD_ENABLED` | missing | **1** |
| `WB_PILLAR_GATES_ENABLED` | missing | **1** |
| `WB_ARM_EARLIEST_HOUR_ET` | missing | **7** |

---

## Weekly Summary Comparison

### Old Config (before .env sync)
| Day | Date | Trades | Wins | Losses | P&L |
|-----|------|--------|------|--------|-----|
| Mon | 03-09 | 2 | 0 | 2 | -$1,074 |
| Tue | 03-10 | 2 | 1 | 1 | +$2,399 |
| Wed | 03-11 | 0 | 0 | 0 | $0 |
| Thu | 03-12 | 2 | 1 | 1 | -$969 |
| Fri | 03-13 | 0 | 0 | 0 | $0 |
| Mon | 03-17 | 4 | 2 | 2 | -$77 |
| Tue | 03-18 | 2 | 1 | 1 | -$270 |
| **TOTAL** | | **12** | **4** | **6** | **+$9** |

### New Config (synced .env)
| Day | Date | Trades | Wins | Losses | P&L |
|-----|------|--------|------|--------|-----|
| Mon | 03-09 | 2 | 0 | 2 | -$1,074 |
| Tue | 03-10 | 2 | 1 | 1 | +$2,082 |
| Wed | 03-11 | 0 | 0 | 0 | $0 |
| Thu | 03-12 | 2 | 1 | 1 | -$619 |
| Fri | 03-13 | 0 | 0 | 0 | $0 |
| Mon | 03-17 | 4 | 1 | 3 | -$1,661 |
| Tue | 03-18 | 2 | 1 | 1 | -$139 |
| **TOTAL** | | **12** | **4** | **8** | **-$1,411** |

### Net Impact: Old +$9 → New -$1,411 (delta: **-$1,420**)

The new config made overall results worse, primarily driven by:
1. **LUNL flipped from +$464 to -$821** (0.75R max_loss_hit killed a winner)
2. **INKT loss deepened from -$349 to -$666** (continuation hold suppressed BE exit)
3. **TRT went from -$1,000 to -$1,700** (took 2 trades instead of 1, both max_loss_hit)

---

## Detailed Trade Log (New Config)

---

### Trade 1: HIMZ — Mon 03-09 — LOSS (-$675)
| Field | Value |
|-------|-------|
| **Symbol** | HIMZ |
| **Date** | 2026-03-09 |
| **Scanner** | Premarket discovery, gap +88.4%, float 6.0M, Profile B |
| **Tick Data** | 96,081 trades |
| **Entry Time** | 08:31 ET |
| **Entry Price** | $2.36 |
| **Stop** | $2.21 |
| **R** | $0.15 |
| **Position Size** | 6,666 shares |
| **Score** | 12.0 |
| **MACD Score** | 7.5 |
| **Tags** | ABCD, ASC_TRIANGLE, BULL_FLAG, FLAT_TOP, RED_TO_GREEN, VOLUME_SURGE |
| **Score Breakdown** | macd=7.5*0.6; bull_struct=+3; vol_surge=+2; r2g=+1.5; R>=0.08=+1 |
| **Exit Price** | $2.26 |
| **Exit Reason** | bearish_engulfing_exit_full |
| **P&L** | -$675 (-0.7R) |
| **Config Impact** | No change from old config |

**Signal Flow:**
- 08:11 — 1M IMPULSE detected
- 08:12-08:14 — PULLBACK 1/3, 2/3, 3/3
- 08:18 — 1M IMPULSE (new cycle)
- 08:23 — 1M IMPULSE
- 08:25 — PULLBACK 1/3
- 08:28 — 1M IMPULSE
- 08:29 — PULLBACK 1/3
- 08:30 — **ARMED** entry=$2.34 stop=$2.21 R=$0.13 score=12.0
- 08:31 — **ENTRY** at $2.36 (slippage +$0.02), R adjusted to $0.15
- 08:31 — **BEARISH ENGULFING EXIT** at $2.26

**Why it lost:** Stock had already gapped 88% — extreme extension with no historical support. The detector saw every textbook bullish pattern (score 12.0, 6 tags) but the stock was in free-fall price discovery. Bearish engulfing formed within the same minute as entry. The wide gap meant buyers were exhausted.

**Old vs New:** Identical result. The 0.75R loss cap didn't trigger because the BE exit at -0.7R came first.

---

### Trade 2: HIMZ — Mon 03-09 — LOSS (-$399)
| Field | Value |
|-------|-------|
| **Entry Time** | 08:37 ET |
| **Entry Price** | $2.37 |
| **Stop** | $2.27 |
| **R** | $0.10 |
| **Position Size** | 9,970 shares |
| **Score** | 12.0 |
| **Tags** | ABCD, ASC_TRIANGLE, FLAT_TOP, RED_TO_GREEN, VOLUME_SURGE |
| **Exit Price** | $2.33 |
| **Exit Reason** | bearish_engulfing_exit_full |
| **P&L** | -$399 (-0.4R) |
| **Config Impact** | No change from old config |

**Signal Flow:**
- 08:33 — 1M IMPULSE (after trade 1 exit)
- 08:35 — PULLBACK 1/3
- 08:36 — **ARMED** entry=$2.35 stop=$2.27 R=$0.08 score=12.0
- 08:37 — **ENTRY** at $2.37, R adjusted to $0.10
- 08:38 — **BEARISH ENGULFING EXIT** at $2.33

**Why it lost:** Revenge trade on a fading stock. Same patterns fired again 6 minutes after the first loss. Stock continued its downtrend. BE exit limited the damage to -0.4R.

---

### Trade 3: INKT — Tue 03-10 — LOSS (-$666) ⚠️ WORSE THAN OLD
| Field | Value |
|-------|-------|
| **Symbol** | INKT |
| **Date** | 2026-03-10 |
| **Scanner** | Premarket discovery 05:35 ET, gap +71.3%, float 1.68M, Profile A |
| **Tick Data** | 304,349 trades |
| **Entry Time** | 07:06 ET |
| **Entry Price** | $20.02 |
| **Stop** | $18.19 |
| **R** | $1.83 |
| **Position Size** | 546 shares |
| **Score** | 12.5 |
| **MACD Score** | 7.5 |
| **Tags** | ASC_TRIANGLE, FLAT_TOP, RED_TO_GREEN, TOPPING_WICKY, VOLUME_SURGE, WHOLE_DOLLAR_NEARBY |
| **Score Breakdown** | macd=7.5*0.6; bull_struct=+3; vol_surge=+2; r2g=+1.5; whole=+0.5; R>=0.08=+1 |
| **Exit Price** | $18.80 |
| **Exit Reason** | bearish_engulfing_exit_full |
| **P&L** | -$666 (-0.7R) |
| **Old Config P&L** | -$349 (-0.3R) |
| **Config Impact** | **-$317 worse** — continuation hold suppressed 3 BE exits |

**Signal Flow:**
- 07:00 — 1M IMPULSE
- 07:02-07:04 — PULLBACK 1/3, 2/3, 3/3
- 07:05 — **ARMED** at $20.00 (whole dollar) score=12.5
- 07:06 — **ENTRY** at $20.02
- 07:06 — BE_SUPPRESSED (continuation_hold, vol_dom=3.5x, unreal_r=-0.3) at $19.38
- 07:06 — BE_SUPPRESSED (continuation_hold, vol_dom=3.5x, unreal_r=-0.4) at $19.32
- 07:07 — BE_SUPPRESSED (continuation_hold, vol_dom=2.9x, unreal_r=-0.4) at $19.32
- 07:08 — **BEARISH ENGULFING EXIT** at $18.80 (vol_dom finally dropped below threshold)

**Why it got worse:** The continuation hold feature (new config) saw high volume dominance (3.5x) and suppressed the first three bearish engulfing signals, hoping for a recovery. But INKT was a 71% gap stock in freefall — volume dominance was from panicked selling, not buying pressure. By the time the 4th BE fired at 07:08, price had dropped from $19.38 to $18.80.

**Key insight:** Continuation hold vol_dom doesn't distinguish between bullish and bearish volume. On a stock that's crashing, high volume dominance means selling pressure, not a reason to hold.

---

### Trade 4: GITS — Tue 03-10 — WIN (+$2,748) ✅ BEST TRADE
| Field | Value |
|-------|-------|
| **Symbol** | GITS |
| **Date** | 2026-03-10 |
| **Scanner** | Rescan discovery at 10:30 ET, gap +20.1%, float 2.46M, Profile A |
| **Tick Data** | 706 trades |
| **Entry Time** | 10:17 ET |
| **Entry Price** | $2.54 |
| **Stop** | $2.46 |
| **R** | $0.08 |
| **Position Size** | 12,484 shares |
| **Score** | 10.0 |
| **MACD Score** | 5.0 |
| **Tags** | ABCD, ASC_TRIANGLE, FLAT_TOP, RED_TO_GREEN, VOLUME_SURGE |
| **Score Breakdown** | macd=5.0*0.6; bull_struct=+3; vol_surge=+2; r2g=+1.5; R>=0.05=+0.5 |
| **Exit Price** | $2.76 |
| **Exit Reason** | bearish_engulfing_exit_full |
| **P&L** | +$2,748 (+2.7R) |
| **Old Config P&L** | +$2,748 (+2.7R) |
| **Config Impact** | No change |

**Signal Flow:**
- 09:31 — 1M IMPULSE (first attempt, later reset on trend down)
- 09:35-09:36 — PULLBACK 1/3, 2/3 (reset)
- 10:09 — 1M IMPULSE (second attempt)
- 10:10-10:12 — PULLBACK 1/3, 2/3, 3/3
- 10:13 — **ARMED** entry=$2.52 stop=$2.46 R=$0.06 score=10.0
- 10:17 — **ENTRY** at $2.54 (slippage +$0.02), R adjusted to $0.08
- 10:22-10:32 — Multiple impulse/pullback cycles while in trade (stock running)
- 10:24 — Second ARMED at $2.60 score=12.0 (not entered, already in trade)
- 10:33 — **BEARISH ENGULFING EXIT** at $2.76

**Why it won:** Textbook Ross Cameron trade. Low float (2.46M), moderate gap (+20%), patient late-morning entry after an earlier failed setup reset. The stock ran 22 cents from entry before the exit signal. Discovery was via late rescan (10:30 checkpoint) — would have been missed without the re-scan thread.

**Why it held:** A second ARMED signal at 10:24 (score 12.0) confirmed the momentum was real. The bot was already in the trade and let it run until the BE exit.

---

### Trade 5: TLYS — Thu 03-12 — WIN (+$77) ⚠️ SMALLER THAN OLD
| Field | Value |
|-------|-------|
| **Symbol** | TLYS |
| **Date** | 2026-03-12 |
| **Scanner** | Premarket discovery, gap +62.6%, float 9.29M, Profile B |
| **Tick Data** | 124,365 trades |
| **Entry Time** | 07:03 ET |
| **Entry Price** | $2.72 |
| **Stop** | $2.59 |
| **R** | $0.13 |
| **Position Size** | 7,692 shares |
| **Score** | 12.0 |
| **MACD Score** | 7.5 |
| **Tags** | ABCD, ASC_TRIANGLE, FLAT_TOP, RED_TO_GREEN, TOPPING_WICKY, VOLUME_SURGE |
| **Score Breakdown** | macd=7.5*0.6; bull_struct=+3; vol_surge=+2; r2g=+1.5; R>=0.08=+1 |
| **Exit Price** | $2.73 |
| **Exit Reason** | topping_wicky_exit_full |
| **P&L** | +$77 (+0.1R) |
| **Old Config P&L** | +$231 (+0.2R) |
| **Config Impact** | **-$154 worse** — continuation hold suppressed earlier TW exits (vol_dom=4.0x), final exit at lower price |

**Signal Flow:**
- 07:00 — 1M IMPULSE
- 07:01 — PULLBACK 1/3
- 07:02 — **ARMED** entry=$2.70 stop=$2.59 R=$0.11 score=12.0
- 07:03 — **ENTRY** at $2.72, R adjusted to $0.13
- 07:03-07:05 — Multiple TW exit signals suppressed by continuation hold (vol_dom=4.0x)
- 07:06 — **TOPPING WICKY EXIT** at $2.73 (vol_dom finally dropped)

**Why it won less:** Continuation hold saw volume dominance of 4.0x and suppressed the earlier topping wicky exits when the stock was at $2.75. By the time it let go, price had dipped to $2.73. Old config (no continuation hold) exited at $2.75 for +$231.

---

### Trade 6: FLYT — Thu 03-12 — LOSS (-$696) ⚠️ BETTER THAN OLD
| Field | Value |
|-------|-------|
| **Symbol** | FLYT |
| **Date** | 2026-03-12 |
| **Scanner** | Premarket discovery, gap +20.8%, float 0.31M, Profile A |
| **Tick Data** | 2,594 trades |
| **Entry Time** | 08:28 ET |
| **Entry Price** | $11.49 |
| **Stop** | $11.29 |
| **R** | $0.20 |
| **Position Size** | 5,000 shares |
| **Score** | 12.5 |
| **MACD Score** | 7.5 |
| **Tags** | ABCD, RED_TO_GREEN, VOLUME_SURGE, WHOLE_DOLLAR_NEARBY |
| **Score Breakdown** | macd=7.5*0.6; bull_struct=+3; vol_surge=+2; r2g=+1.5; whole=+0.5; R>=0.08=+1 |
| **Exit Price** | $11.33 |
| **Exit Reason** | max_loss_hit (0.75R cap) |
| **P&L** | -$696 (-0.8R) |
| **Old Config P&L** | -$1,200 (-1.2R) |
| **Config Impact** | **+$504 better** — 0.75R cap exited earlier than the full stop |

**Signal Flow:**
- 07:29 — 1M IMPULSE
- 07:30 — PULLBACK 1/3 (setup resets multiple times)
- 08:24 — 1M IMPULSE
- 08:26 — PULLBACK 1/3
- 08:27 — **ARMED** entry=$11.47 stop=$11.29 R=$0.18 score=12.5
- 08:28 — **ENTRY** at $11.49, R adjusted to $0.20
- 08:28 — **MAX_LOSS_HIT** exit at $11.33 (price fell through 0.75R threshold)
- (Subsequent setups blocked by exhaustion filter: 12.6% and 14.0% above VWAP)

**Why it lost less:** The 0.75R max loss cap pulled the exit at $11.33 instead of waiting for the full stop at $11.25 (which had 4 cents of additional slippage to $11.25 in old config). Saved $504.

---

### Trade 7: OKLL — Mon 03-17 — WIN (+$945) ✅ BETTER THAN OLD
| Field | Value |
|-------|-------|
| **Symbol** | OKLL |
| **Date** | 2026-03-17 |
| **Scanner** | Rescan discovery at 08:30 ET, gap +19.9%, float 1.36M, Profile A |
| **Tick Data** | 40,501 trades |
| **Entry Time** | 08:11 ET |
| **Entry Price** | $10.05 |
| **Stop** | $9.89 |
| **R** | $0.16 |
| **Position Size** | 5,970 shares |
| **Score** | 11.0 |
| **MACD Score** | 5.0 |
| **Tags** | ABCD, RED_TO_GREEN, TOPPING_WICKY, VOLUME_SURGE, WHOLE_DOLLAR_NEARBY |
| **Score Breakdown** | macd=5.0*0.6; bull_struct=+3; vol_surge=+2; r2g=+1.5; whole=+0.5; R>=0.08=+1 |
| **Exit Price** | $10.24 |
| **Exit Reason** | bearish_engulfing_exit_full |
| **P&L** | +$945 (+1.2R) |
| **Old Config P&L** | +$896 (+0.9R) |
| **Config Impact** | **+$49 better** — slightly different exit timing |

**Signal Flow:**
- 08:08 — 1M IMPULSE
- 08:09 — PULLBACK 1/3
- 08:10 — **ARMED** entry=$10.03 stop=$9.89 R=$0.14 score=11.0
- 08:11 — **ENTRY** at $10.05, R=$0.16
- 08:11 — 1M IMPULSE (continuation)
- 08:13 — **BEARISH ENGULFING EXIT** at $10.24

**Why it won:** Clean setup. 20% gap, 1.36M float, entry near $10 whole dollar. Stock ran 19 cents before exit. Classic micro-pullback that worked exactly as designed.

---

### Trade 8: LUNL — Mon 03-17 — LOSS (-$821) ⚠️ FLIPPED FROM WIN
| Field | Value |
|-------|-------|
| **Symbol** | LUNL |
| **Date** | 2026-03-17 |
| **Scanner** | Rescan discovery at 10:00 ET, gap +10.3%, float 0.17M, Profile A |
| **Tick Data** | 1,610 trades |
| **Entry Time** | 09:59 ET |
| **Entry Price** | $13.00 |
| **Stop** | $12.72 |
| **R** | $0.28 |
| **Position Size** | 3,571 shares |
| **Score** | 12.5 |
| **Tags** | ABCD, RED_TO_GREEN, TOPPING_WICKY, VOLUME_SURGE, WHOLE_DOLLAR_NEARBY |
| **Exit Price** | $12.77 |
| **Exit Reason** | max_loss_hit (0.75R cap) |
| **P&L** | -$821 (-0.8R) |
| **Old Config P&L** | +$464 (+0.5R) |
| **Config Impact** | **-$1,285 worse** — 0.75R cap killed a winner |

**Signal Flow:**
- 07:09-09:42 — Multiple impulse/pullback cycles, all resetting
- 09:42 — 1M IMPULSE
- 09:45-09:46 — PULLBACK 1/3, 2/3
- 09:50-09:54 — More impulses and pullbacks
- 09:56 — **ARMED** entry=$12.98 stop=$12.72 R=$0.26 score=12.5
- 09:59 — **ENTRY** at $13.00, R=$0.28
- ?? — **MAX_LOSS_HIT** at $12.77 (price dipped 0.75R below entry)
- (In old config: price recovered and topping wicky exit fired at $13.13 for +$464)

**Why it flipped:** This is the critical failure of the 0.75R cap on this dataset. The stock dipped through the 0.75R threshold at $12.77, triggering the max_loss_hit exit. Under old config (2.0R cap), the bot held through the dip and the topping wicky exit caught the recovery at $13.13. The 0.75R cap was too tight for this stock's natural volatility.

**Key insight:** LUNL had 0.17M float — ultra-low float stocks are inherently more volatile. A 0.75R dip is normal noise, not a failed trade. The dip-then-recover pattern is exactly what micro-pullback trading expects.

---

### Trade 9: BIAF — Mon 03-17 — LOSS (-$85) ✅ BETTER THAN OLD
| Field | Value |
|-------|-------|
| **Symbol** | BIAF |
| **Date** | 2026-03-17 |
| **Scanner** | Rescan discovery at 08:00 ET, gap +19.9%, float 4.35M, Profile A |
| **Tick Data** | 316,628 trades |
| **Entry Time** | 09:50 ET |
| **Entry Price** | $2.85 |
| **Stop** | $2.61 |
| **R** | $0.24 |
| **Position Size** | 4,166 shares |
| **Score** | 12.0 |
| **Tags** | ABCD, ASC_TRIANGLE, FLAT_TOP, RED_TO_GREEN, VOLUME_SURGE |
| **Exit Price** | $2.83 |
| **Exit Reason** | topping_wicky_exit_full |
| **P&L** | -$85 (-0.1R) |
| **Old Config P&L** | -$437 (-0.4R) |
| **Config Impact** | **+$352 better** — TW exit fired earlier with new config |

**Signal Flow:**
- 07:28 — 1M IMPULSE
- 07:32-07:33 — ARMED at $2.41, then VWAP_BLOCKED_ARM reset (correctly blocked)
- 09:46 — New impulse
- 09:47-09:48 — PULLBACK 1/3, 2/3
- 09:49 — **ARMED** entry=$2.83 stop=$2.61 R=$0.22 score=12.0
- 09:50 — **ENTRY** at $2.85, R=$0.24
- 09:51 — **TOPPING WICKY EXIT** at $2.83

**Why it lost less:** Under new config, the TW exit fired almost immediately at $2.83 (-$0.02 from entry). Old config had a BE exit at $2.75 (-$437). The topping wicky detection may have been affected by classifier or other new settings.

---

### Trade 10: TRT — Mon 03-17 — LOSS (-$784) ⚠️ TRADE 1 OF 2
| Field | Value |
|-------|-------|
| **Symbol** | TRT |
| **Date** | 2026-03-17 |
| **Scanner** | Rescan discovery at 10:00 ET, gap +9.7%, float 4.99M, Profile A |
| **Tick Data** | 381 trades |
| **Entry Time** | 09:43 ET |
| **Entry Price** | $6.26 |
| **Stop** | $6.15 |
| **R** | $0.11 |
| **Position Size** | 7,989 shares |
| **Score** | 5.5 |
| **MACD Score** | 7.5 |
| **Tags** | (none) |
| **Score Breakdown** | macd=7.5*0.6; R>=0.08=+1 |
| **Exit Price** | $6.16 |
| **Exit Reason** | max_loss_hit (0.75R cap) |
| **P&L** | -$784 (-0.9R) |
| **Old Config P&L (single trade)** | -$1,000 (-1.0R) |

**Signal Flow:**
- 08:31, 08:34, 09:30, 09:34 — Multiple impulses
- 09:36 — PULLBACK 1/3
- 09:37 — **ARMED** entry=$6.24 stop=$6.15 R=$0.09 score=5.5
- 09:43 — **ENTRY** at $6.26, R=$0.11
- 09:43 — **MAX_LOSS_HIT** at $6.16

**Why it lost:** Lowest score of any trade (5.5) with zero pattern tags. Only MACD score + R-size bonus. Stock had no bullish structure at all. The 0.75R cap pulled the exit at $6.16 instead of the full stop at $6.15 — minimal difference.

---

### Trade 11: TRT — Mon 03-17 — LOSS (-$916) ⚠️ TRADE 2 (NEW)
| Field | Value |
|-------|-------|
| **Entry Time** | 09:49 ET |
| **Entry Price** | $6.28 |
| **Stop** | $6.15 |
| **R** | $0.13 |
| **Position Size** | 7,968 shares |
| **Score** | 5.5 |
| **Tags** | RED_TO_GREEN |
| **Exit Price** | $6.16 |
| **Exit Reason** | max_loss_hit (0.75R cap) |
| **P&L** | -$916 (-0.9R) |
| **Old Config** | This trade didn't exist (old config only took 1 trade) |

**Signal Flow:**
- 09:44 — 1M IMPULSE (after trade 1 exit)
- 09:46-09:47 — PULLBACK 1/3, 2/3
- 09:48 — **ARMED** entry=$6.26 stop=$6.15 R=$0.11 score=5.5
- 09:49 — **ENTRY** at $6.28, R=$0.13
- 09:49 — **MAX_LOSS_HIT** at $6.16

**Why this trade exists:** Under old config, the first TRT trade hit the full stop at $6.15, and the cooldown timer prevented re-entry. Under new config, the 0.75R cap exited at $6.16 (slightly above the stop), which meant the loss was recorded differently, potentially allowing the re-entry sooner. Same result: immediate failure.

**Combined TRT impact:** Old: 1 trade, -$1,000. New: 2 trades, -$1,700. **Delta: -$700 worse.**

---

### Trade 12: BMNZ — Tue 03-18 — WIN (+$118)
| Field | Value |
|-------|-------|
| **Symbol** | BMNZ |
| **Date** | 2026-03-18 |
| **Tick Data** | 11,055 trades |
| **Entry Time** | 08:45 ET |
| **Entry Price** | $16.99 |
| **Stop** | $16.80 |
| **R** | $0.19 |
| **Position Size** | 3,531 shares |
| **Score** | 10.1 |
| **Tags** | ABCD, ASC_TRIANGLE, RED_TO_GREEN, VOLUME_SURGE, WHOLE_DOLLAR_NEARBY |
| **Exit Price** | $17.03 |
| **Exit Reason** | topping_wicky_exit_full |
| **P&L** | +$118 (+0.2R) |
| **Old Config P&L** | +$141 (+0.2R) |

**Signal Flow:**
- Multiple impulse/pullback cycles from 07:00
- 08:42 — 1M IMPULSE
- 08:43 — PULLBACK 1/3
- 08:44 — **ARMED** entry=$16.97 stop=$16.80 R=$0.17 score=10.1
- 08:45 — **ENTRY** at $16.99, R=$0.19
- 08:48 — **TOPPING WICKY EXIT** at $17.03

---

### Trade 13: BMNZ — Tue 03-18 — LOSS (-$257) ⚠️ BETTER THAN OLD
| Field | Value |
|-------|-------|
| **Entry Time** | 10:49 ET |
| **Entry Price** | $17.51 |
| **Stop** | $17.41 |
| **R** | $0.10 |
| **Score** | 8.8 |
| **Exit Price** | $17.42 |
| **Exit Reason** | max_loss_hit (0.75R cap) |
| **P&L** | -$257 (-0.9R) |
| **Old Config P&L** | -$411 (-1.2R) |
| **Config Impact** | **+$154 better** — 0.75R cap limited the loss |

---

## Impact Analysis: 0.75R Max Loss Cap

The biggest single change in the new config. Here's how it affected each trade:

| Trade | Symbol | Old P&L | New P&L | Delta | Verdict |
|-------|--------|---------|---------|-------|---------|
| HIMZ #1 | HIMZ | -$675 | -$675 | $0 | No effect (BE exit first) |
| HIMZ #2 | HIMZ | -$399 | -$399 | $0 | No effect (BE exit first) |
| INKT | INKT | -$349 | -$666 | -$317 | **Worse** (cont hold, not 0.75R) |
| GITS | GITS | +$2,748 | +$2,748 | $0 | No effect (winner) |
| TLYS | TLYS | +$231 | +$77 | -$154 | **Worse** (cont hold, not 0.75R) |
| FLYT | FLYT | -$1,200 | -$696 | **+$504** | **Better** (0.75R saved $504) |
| OKLL | OKLL | +$896 | +$945 | +$49 | Slightly better |
| LUNL | LUNL | +$464 | -$821 | **-$1,285** | **Much worse** (0.75R killed winner) |
| BIAF | BIAF | -$437 | -$85 | **+$352** | **Better** (TW exit, not 0.75R) |
| TRT #1 | TRT | -$1,000 | -$784 | +$216 | Slightly better |
| TRT #2 | TRT | N/A | -$916 | -$916 | **New loss** (re-entry) |
| BMNZ #1 | BMNZ | +$141 | +$118 | -$23 | Slightly worse |
| BMNZ #2 | BMNZ | -$411 | -$257 | **+$154** | **Better** (0.75R saved $154) |

**0.75R Cap Scorecard:**
- Helped: FLYT (+$504), BMNZ#2 (+$154), TRT#1 (+$216) = **+$874 saved**
- Hurt: LUNL (-$1,285), TRT#2 (-$916 new loss) = **-$2,201 cost**
- **Net impact of 0.75R cap: -$1,327**

## Impact Analysis: Continuation Hold

| Trade | Old P&L | New P&L | Delta | What Happened |
|-------|---------|---------|-------|---------------|
| INKT | -$349 | -$666 | -$317 | Suppressed 3 BE exits (vol_dom 2.9-3.5x) on crashing stock |
| TLYS | +$231 | +$77 | -$154 | Suppressed TW exits (vol_dom 4.0x), exited at lower price |
| **Net** | | | **-$471** | Hurt on both trades |

---

## Summary of Findings

### What the New Config Does Better
1. **FLYT**: 0.75R cap saved $504 (exited before full stop hit with slippage)
2. **BIAF**: TW exit caught the reversal earlier (-$85 vs -$437)
3. **BMNZ#2**: 0.75R cap limited late-session loss

### What the New Config Does Worse
1. **LUNL**: 0.75R cap killed a +$464 winner (dip-then-recover on ultra-low float)
2. **TRT**: 0.75R cap enabled a revenge re-entry that lost another $916
3. **INKT**: Continuation hold suppressed exits on a crashing stock
4. **TLYS**: Continuation hold reduced a small win by $154

### Key Observations
1. **The 0.75R cap is too tight for ultra-low float stocks** — LUNL (0.17M float) naturally dips 0.75R before recovering. The cap needs to be float-aware or widened.
2. **Continuation hold can't distinguish bullish vs bearish volume** — INKT's high vol_dom was selling pressure, not buying pressure. The hold made losses worse.
3. **Re-entry after 0.75R exit is dangerous** — TRT took a second loss because the 0.75R exit left it slightly above the hard stop, potentially resetting the cooldown.
4. **The scanner tightening (gap 10%, float 10M, RVOL 2.0) had no visible impact** — all the same stocks appeared in both runs because they were selected manually for backtesting.
5. **GITS (+$2,748) carried the entire week** — without it, new config would be -$4,159.
