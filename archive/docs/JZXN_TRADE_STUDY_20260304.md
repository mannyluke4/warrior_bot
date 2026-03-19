# JZXN Trade Study — 2026-03-04
**Prepared by:** Duffy  
**For:** Perplexity — tuning analysis  
**Date:** 2026-03-05

---

## Background

JZXN appeared on the Warrior Trading scanner at 7:16 AM ET on 2026-03-04. It was the only Profile A qualified stock of the session (float 1.32M, micro-float, 57-91% gap). Ross Cameron reportedly made $50k+ on a trade that day — JZXN is the most likely candidate based on its profile.

Our bot captured a small portion of the move: **+$333 (+0.3R)**. The question is: what would it have taken to capture more?

---

## Full Verbose Backtest Output

```
Window: 07:16 → 12:00 ET | Tick mode | Profile A | 127,528 trades replayed

[07:16] ARMED entry=1.3400 stop=1.0900 R=0.2500 score=5.5
[07:17] ENTRY: 1.3600 stop=1.0900 R=0.2700 qty=3,703 shares score=5.5
[07:17] ARMED entry=1.4500 stop=1.2000 R=0.2500 score=5.5 (second armed, never entered)
[07:19] BEARISH_ENGULFING_EXIT @ 1.4500 → P&L: +$333 (+0.3R)
[07:20] CLASSIFIER: JZXN → uncertain (conf=0.30) — No strong pattern
[07:25] CLASSIFIER: reclassified uncertain → smooth_trend
[07:30] CLASSIFIER: reclassified smooth_trend → one_big_move
[07:54] ARMED @ 1.3600 stop=1.2500 R=0.1100 score=12.5 — tags: [ABCD, RED_TO_GREEN, VOLUME_SURGE, WHOLE_DOLLAR_NEARBY]
[07:55] 1M RESET (lost VWAP) — trade never entered
[09:52+] NO_ARM: stale_stock (no new session HOD in 154+ bars)
```

---

## What Happened — Timeline

### 7:16-7:19 AM: The Entry and Early Exit
- Bot armed at $1.34, entered at $1.36 with 3,703 shares
- Stop: $1.09 (R = $0.27)
- At 7:19 AM, a bearish engulfing candle fired → full exit at $1.45
- P&L: +$333 (+0.3R) — only captured a $0.09 move on a stock that ran much higher

### 7:19-7:30 AM: The Big Move — Bot Was Out
- After the exit, JZXN continued running
- Classifier evolved: uncertain → smooth_trend → one_big_move
- The bot correctly identified the pattern AFTER it was out of the position
- No re-entry because the cooldown/signal system had already exited

### 7:54 AM: High-Scoring Re-Entry Opportunity — Missed
- Score: 12.5 (exceptional — among the highest possible)
- Tags: ABCD pattern, Red-to-Green, Volume Surge, Whole Dollar Nearby
- Would have been a strong re-entry into the continuation
- **BUT:** Lost VWAP at 7:55 AM → 1M RESET fired, blocking the entry

### 9:52+ AM: Stale Stock Filter Kicks In
- No new session HOD in 154+ bars → stale_stock filter blocks all further arms
- Stock had peaked and was consolidating, so this filter was correct

---

## Root Causes — Why We Left Money on the Table

### Cause 1: Bearish Engulfing Exit Too Aggressive (PRIMARY)
The exit at 7:19 AM on a bearish engulfing candle was premature. On a micro-float stock with 1.32M shares and 57-91% gap, a single bearish engulfing candle in the first 3 minutes of the move is almost certainly noise, not reversal. The stock continued to run significantly after this exit.

**The data question:** How often does a bearish engulfing in the first 5 minutes of a micro-float 7am scanner stock represent a true reversal vs. temporary consolidation before continuation?

### Cause 2: Re-entry Blocked by VWAP Loss at 7:54 AM
At 7:54 AM, the bot armed with a score of 12.5 — the highest signal quality in the entire session. Tags included ABCD, Red-to-Green, Volume Surge, Whole Dollar Nearby. This was almost certainly the re-entry into the continuation move. One bar later, VWAP loss triggered a reset and killed the entry.

**The data question:** On high-score (12+) signals with ABCD + Volume Surge tags, does VWAP loss in the same bar as arming represent a real red flag, or is it a false negative on a fast-moving micro-float?

### Cause 3: Classifier Lag
The bot classified JZXN as "uncertain" at 7:20 AM, then correctly identified it as "one_big_move" by 7:30 AM — but by then the initial entry was already closed. The classification came 10 minutes too late to influence trade management.

---

## Key Questions for Perplexity

**Q1: Bearish Engulfing Filter on First 5 Minutes**
Should the bearish engulfing exit be suppressed or delayed during the first N minutes of a micro-float scanner stock's move? Specifically for Profile A stocks (micro-float, 7am scanner), the first bearish engulfing is frequently a false signal on high-momentum names.

Propose: Add a configurable `WB_BE_SUPPRESS_MINUTES` parameter (e.g., 5 minutes) that suppresses the bearish engulfing exit for the first N minutes after entry on Profile A stocks. Study question: what is the optimal value?

**Q2: High-Score VWAP Gate Exception**
When score ≥ 12.0 AND tags include ABCD + VOLUME_SURGE, should the VWAP loss reset be overridden? The 7:54 AM signal was essentially a perfect re-entry signal that got blocked by a single VWAP bar.

Propose: Add a `WB_HIGH_SCORE_VWAP_OVERRIDE` flag that allows entry when score ≥ threshold (e.g., 11.0) even if VWAP was momentarily lost. Risk: could increase false entries on weaker stocks.

**Q3: One_Big_Move Classifier — Earlier Detection**
The classifier correctly identified JZXN as "one_big_move" by 7:30 AM but started as "uncertain." On stocks with these attributes (micro-float, >50% gap, 7am scanner, high relative volume), should the classifier start in a more aggressive state rather than "uncertain"?

**Q4: Trailing Stop — Would It Have Helped Here?**
The trailing stop system (currently OFF) uses R-multiple escalation: BE at 3R, lock +1R at 5R, trail at 7R. With a $0.27R and 3,703 shares:
- 3R = $0.81 gain → BE at $1.63
- 5R = $1.35 gain → lock +1R at $1.63 floor  
- 7R = $1.89 gain → trail $0.15 below peak

Would the trailing stop have kept the bot in the trade longer on JZXN, or would it have exited before the bearish engulfing anyway?

---

## Summary

| | Result |
|---|---|
| Bot P&L | +$333 (+0.3R) |
| Entry | $1.36 @ 7:17 AM |
| Exit | $1.45 @ 7:19 AM (bearish engulfing) |
| Exit reason | Too early — first BE candle on fast micro-float |
| Missed opportunity | High-score re-entry at 7:54 AM (score 12.5, ABCD+Volume Surge) blocked by VWAP reset |
| Ross's reported P&L | ~$50,000+ |
| Gap between bot and human | Primarily the early exit + missed re-entry |

The bot found the right stock, took the right entry, and made a small profit. The failure was in exit management and re-entry logic, not in stock selection.

---

*Study by Duffy — 2026-03-05*  
*Data source: Alpaca ticks, Profile A, 07:16-12:00 ET window*
