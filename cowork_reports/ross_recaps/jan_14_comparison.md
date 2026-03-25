# Jan 14, 2025 — Ross vs Bot Comparison

## Daily Totals
| | P&L | Trades |
|---|---|---|
| **Ross Cameron** | +$5,633.64 | 6 tickers (ADD, NMHI, OST, AIFF, VRME + recovery trades) |
| **Bot (combined)** | +$1,424 | 1 ticker (AIFF only) |

## Ticker-by-Ticker Breakdown

### AIFF — Bot Outperformed Ross
| | Ross | Bot (MP) | Bot (SQ) | Bot Combined |
|---|---|---|---|---|
| P&L | **-$2,000** | -$17 | +$1,441 | **+$1,424** |
| Entry | ~$10.08 (VWAP break) | $4.21 (09:07) | $4.61 (09:31) | — |
| Exit | sharp rejection | $4.18 (topping_wicky) | $5.08, $5.36 (targets hit) | — |
| Result | Loss — reluctant entry, slow grind then rejection | Scratch — quick exit | Two wins — squeeze targets hit | **+$3,424 outperformance** |

**The irony:** Ross's AIFF loss (-$2K) was driven by emotional re-entry on a stock he'd traded Jan 10. He entered a VWAP break at $10.08, got a slow grind followed by sharp rejection, and the 200 EMA at $5 acted as resistance. The bot, meanwhile, entered much lower ($4.21 and $4.61), caught the squeeze from $4.61 to $5.36, and hit its targets cleanly. Ross's emotional attachment to a prior winner burned him; the bot's mechanical approach worked perfectly.

### ADD — Scanner Miss (Ross's biggest winner)
| Ross | Bot |
|---|---|
| +$5,810 | Not traded — **scanner missed it** |
| 6:45 AM spotted, 7:00 AM traded | — |
| News + sub-1M float + 20M volume | — |
| VWAP reclaim, multiple trades targeting $3 | — |

This was the day's biggest missed opportunity. ADD had all the characteristics the bot looks for (news catalyst, sub-1M float, massive volume) but didn't appear in the scanner results.

### OST — Scanner Found, Bot Didn't Trade
| Ross | Bot |
|---|---|
| +$1,800 | Not traded — **scanner found it but 0 trades** |
| Mid-morning, 1m chart bounce | Scanner: +43.8% gap, 6.0M PM vol, 4.9M float, Profile A |
| Confirmation re-entry after prior-day round-trip | Discovered 07:14 |

The bot's scanner found OST (Profile A, good metrics) but didn't execute any trades. Ross made $1,800 on a mid-morning 1m chart bounce — a setup type the bot may not be configured to catch.

### NMHI — Scanner Miss
| Ross | Bot |
|---|---|
| Small profit | Not traded — **scanner missed it** |
| 7:00 AM, leading gapper | — |
| Pre-market high breakout $3.18→$3.40 | — |

### VRME — Scanner Miss (but Ross lost)
| Ross | Bot |
|---|---|
| -$4,000 | Not traded — **scanner missed it** |
| VWAP break entry, immediate violent rejection | — |
| Emotional cascade from AIFF loss | — |

The bot dodging VRME was actually beneficial. Ross's VRME loss was emotionally driven — cascading from his AIFF loss. Missing it saved the bot from a potential -$4K.

### ERNA — Scanner Miss (neither traded)
| Ross | Bot |
|---|---|
| Not traded (scanner only) | Not traded — **scanner missed it** |

## Scanner Performance
| Metric | Count |
|---|---|
| Ross's tickers | 6 (ADD, NMHI, OST, AIFF, VRME, ERNA) |
| Bot scanner found | 2 (AIFF, OST) |
| Bot scanner missed | 4 (ADD, NMHI, VRME, ERNA) |
| Scanner hit rate | 33% (2/6) |
| Bot also found (not Ross) | SNGX (+16% gap, 69.7x RVOL, Profile X) |

## Key Insights

**1. AIFF outperformance validates the bot's mechanical approach.** Ross lost $2K on AIFF because of emotional factors — it was a "repeat from Jan 10," he entered reluctantly at $10.08 on a VWAP break, and suffered a sharp rejection. The bot entered lower, hit squeeze targets, and made $1.4K. This is a textbook case of the bot's discipline beating human emotion.

**2. The emotional cascade pattern is exactly what the bot avoids.** Ross went from +$10K peak to +$4,300 in ~15 minutes (AIFF -$2K → VRME -$4K), giving back 60% of his peak. The bot, having no emotions, was immune to this. Even though it missed VRME entirely, that was a net positive — VRME was a -$4K loss for Ross.

**3. ADD is the biggest missed opportunity.** Sub-1M float, news catalyst, 20M volume, spotted at 6:45 AM — this had all the hallmarks of a bot-friendly trade. Ross made +$5,810. Understanding why the scanner missed ADD should be a priority.

**4. OST "found but not traded" gap.** The scanner found OST with strong Profile A metrics, but the bot took zero trades. Ross's OST entry was a mid-morning 1m chart bounce — a setup that may fall outside the bot's current strategy timeframes.

**5. Net comparison is deceptive.** Ross: +$5,634 vs Bot: +$1,424 looks like Ross won by $4,210. But if the bot had found ADD and performed similarly to Ross (+$5,810), the bot would have been at +$7,234 — beating Ross by $1,600. The scanner miss, not strategy performance, was the limiting factor.

## Hypothetical Bot P&L (if scanner found all tickers)
- AIFF (actual): +$1,424
- ADD (backtest needed): PENDING
- OST (backtest needed): PENDING — scanner found it but bot didn't trade
- NMHI (backtest needed): PENDING
- VRME (would likely have lost): PENDING
- ERNA (neither traded): N/A
