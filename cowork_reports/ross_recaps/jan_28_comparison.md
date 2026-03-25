# Jan 28, 2025 — Ross vs Bot Comparison

## Summary
| Metric | Ross | Bot (All-Three) | Bot (SQ) | Bot (MP) |
|--------|------|------------------|----------|----------|
| Daily P&L | +$21,000+ | +$125 | $0 (0 trades) | $0 (0 trades) |
| Trades | 5 tickers, multiple trades | 1 trade (YIBO) | 0 trades | 0 trades |
| Win Rate | 5/5 green tickers | 1/1 (100%) | N/A | N/A |
| Best Trade | ARNAZ +$12,000 | YIBO +$125 | — | — |
| Worst Trade | NLSP +$165 (smallest win) | — | — | — |

**Combined bot P&L: +$125 vs Ross's +$21,000+. The bot made 0.6% of Ross's total. Scanner found 1 of 5 Ross tickers (YIBO = Ross's YWBO), and traded it for +$125 via VR strategy. The 4 biggest misses were ARNAZ (+$12,000), QLGN (+$2,400), JFB (+$600), and NLSP (+$165).**

**Market context:** Day 2 of DeepSeek aftermath. Chinese AI theme fading but still active (YWBO/YIBO continuation). Biotech names (NLSP, QLGN) and daily breakout patterns (ARNAZ) provided the real opportunities. Mixed thematic day — no single dominant catalyst.

## Scanner Overlap

### Bot's Scanner Found (2 tickers)
| Ticker | Gap% | Float | PM Vol | Profile | Bot Traded? | Ross Traded? |
|--------|------|-------|--------|---------|-------------|--------------|
| YIBO | +92.2% | 7.13M | 15.14M | B | YES (+$125, VR entry) | YES (+$5,724 as "YWBO") |
| SNTG | +14.7% | 1.06M | 156K | A | NO (armed, no signal) | NO |

### Ross's Tickers NOT in Bot's Scanner (4 tickers)
| Ticker | Ross P&L | Setup | Why Scanner Likely Missed |
|--------|----------|-------|--------------------------|
| NLSP | +$165 | Biotech, ~800K float, pop and drop | **Low gap% or insufficient PM volume.** Biotech with low float but likely modest pre-market gap. Pop-and-drop setups often don't show strong gap% at scan time. |
| JFB | +$600 | DeepSeek integration news, quick scalp | **Theme fading / insufficient gap%.** DeepSeek day 2 — the integration news was a secondary catalyst. Likely didn't gap enough to clear scanner thresholds. |
| QLGN | +$2,400 | Biotech, low float, $4.75→$5.51 | **Biotech with insufficient gap% or PM volume.** Sub-$5 biotech, low float. Likely didn't meet the minimum gap% or PM volume thresholds. The move was intraday, not pre-market gapper. |
| ARNAZ | +$12,000 | Daily breakout "first candle to make new high", halt resumption dip-and-rip, $7.50→$14.00 | **Daily breakout pattern — not a gap play.** ARNAZ broke out on a daily chart "first candle to make new high" — this is a multi-day momentum pattern, not a pre-market gapper. The scanner looks for overnight gap + volume; ARNAZ was a daily chart breakout. This is a structural scanner limitation — it can't see multi-day chart patterns or intraday breakouts without a morning gap. |

### Overlap: 1 of 5 Ross tickers (20%) — YIBO/YWBO MATCH
The scanner found YIBO, which is the same stock Ross traded as "YWBO" — a Chinese AI-adjacent name continuing from the Jan 27 DeepSeek mania. This is the first scanner-Ross overlap since Jan 24 (ALUR). The bot traded it via the VR (VWAP Reclaim) strategy in the all-three variant, entering at $5.79 and exiting at $6.12 for +$125. Ross entered lower at $5.57 (VWAP reclaim breakout) and rode it to $6.36 for +$5,724 — a 46x P&L gap on the same stock.

## Bot's Trades — What Happened

### V2 Megatest Results (Primary Backtest)
- **All-Three Strategy:** 2 scanned → 2 passed → YIBO, SNTG → **1 trade on YIBO, +$125**
  - YIBO: Entry $5.79, Exit $6.12, vr_core_tp_1.5R exit, +$125 (WIN)
  - SNTG: Armed but no entry signal generated
- **SQ Strategy:** 2 scanned → 2 passed → **0 trades, $0 P&L**
- **MP Strategy:** 2 scanned → 2 passed → **0 trades, $0 P&L**
- **MP+SQ Combined:** 2 scanned → 2 passed → **0 trades, $0 P&L**

The all-three variant (which includes VR/VWAP Reclaim strategy) was the only one to trade. The VR strategy correctly identified the VWAP reclaim pattern on YIBO and entered at $5.79. However, the 1.5R target exit at $6.12 captured only $0.33/share of a $0.79/share move ($5.57→$6.36 range). Ross captured $0.79/share by riding the full VWAP reclaim breakout.

### YIBO/YWBO Head-to-Head
| Metric | Ross (YWBO) | Bot (YIBO) |
|--------|-------------|------------|
| Entry | $5.57 (VWAP reclaim) | $5.79 (VR entry) |
| Exit | $6.36 | $6.12 (vr_core_tp_1.5R) |
| $/Share | +$0.79 | +$0.33 |
| Shares (est) | ~7,245 (based on $5,724 P&L) | ~379 (based on $125 P&L) |
| P&L | +$5,724 | +$125 |
| Gap | — | **46x** |

The P&L gap comes from two compounding factors:
1. **Entry timing:** Ross entered $0.22 lower ($5.57 vs $5.79) — better VWAP reclaim read
2. **Exit management:** Ross held to $6.36 (full breakout), bot exited at $6.12 (1.5R target)
3. **Sizing:** Ross used ~7,245 shares vs bot's ~379 shares — **19x size difference**

This is a smaller version of the ALUR Jan 24 pattern (80x gap). The bot is in the right stock but undersized and exits too early.

## Ross's Trades — What Made Them Work

### YWBO (YIBO) — +$5,724
- **Catalyst:** Chinese AI stock, day 2 continuation from DeepSeek mania (Jan 27)
- **Setup:** VWAP reclaim breakout at $5.57, ran to $6.36
- **Why it worked:** Continuation momentum from a massive day-1 catalyst. Chinese AI theme still had legs. VWAP reclaim is a high-probability pattern on day-2 names.
- **Bot comparison:** Bot found it AND traded it — rare overlap. But captured only 2.2% of Ross's P&L due to sizing and exit differences.

### NLSP — +$165
- **Catalyst:** Biotech, ~800K float
- **Setup:** Pop and drop — small winner
- **Why it worked:** Took quick profit on the initial pop, avoided the drop. Small size, small win — ice-breaker trade.

### JFB — +$600
- **Catalyst:** DeepSeek integration news
- **Setup:** Quick scalp — theme fading
- **Why it worked:** Recognized the DeepSeek theme was fading by day 2 and took only a quick scalp. Discipline to not overstay.

### QLGN — +$2,400
- **Catalyst:** Biotech, low float
- **Setup:** Entered $4.75, ran to $5.51
- **Why it worked:** Classic low-float biotech squeeze. Sub-$5 entry with clear momentum, rode to $5.50 resistance area.

### ARNAZ — +$12,000 (Day's Big Winner)
- **Catalyst:** Daily breakout "first candle to make new high"
- **Setup:** Halt resumption dip-and-rip pattern, ran from $7.50 to $14.00
- **Why it worked:** Multi-day chart pattern — ARNAZ was setting up over multiple days, and Jan 28 was the breakout day when the "first candle made a new high." Ross entered the halt resumption dip, then rode the rip from $7.50 to $14.00 (87% move). This is a daily-timeframe pattern completely outside the bot's scanning capability.
- **Key insight:** This is NOT a pre-market gap play. ARNAZ was a daily chart breakout that Ross identified from multi-day price structure. The bot's scanner is built for overnight gap + PM volume — it has no way to identify daily breakout patterns.

## Key Takeaways

### 1. First Scanner Overlap in 4 Days — YIBO/YWBO
After complete whiffs on Jan 22, 23, and 27, the scanner finally overlapped with a Ross ticker. YIBO was the #1 ranked candidate (+92.2% gap, 15.1M PM volume) and the bot correctly identified it as the day's primary opportunity. The VR strategy fired and produced a winning trade. This is a positive signal — when the scanner finds the right stock, the VR strategy can work.

### 2. Exit Management Gap (46x) — Same Pattern as ALUR
Bot entered YIBO at $5.79 and exited at $6.12 via 1.5R target. Ross entered at $5.57 and rode to $6.36. The bot captured $0.33/share of a $0.79/share move (42% of range). Combined with the 19x sizing gap, this produces a 46x P&L difference. The pattern is consistent: bot exits at fixed R-targets, Ross rides winners.

### 3. ARNAZ Reveals a New Scanner Blindspot: Daily Breakouts
ARNAZ (+$12,000, $7.50→$14.00) was Ross's biggest win and represents a setup type the bot literally cannot detect: daily chart breakouts. "First candle to make new high" is a multi-day pattern requiring daily chart analysis. The scanner only looks at overnight gaps and pre-market volume. This is a structural limitation, not a tuning issue.

### 4. DeepSeek Theme Fading — Bot Found the Continuation
The bot correctly found YIBO as the DeepSeek day-2 continuation play. On Jan 27 (day 1), the scanner completely missed Chinese AI stocks. On Jan 28 (day 2), YIBO showed up as a massive gapper (+92.2%) with huge volume (15.1M) — the continuation gap made it scanner-visible. This suggests the scanner works better on day-2 continuation than on day-1 breakout for thematic events.

### 5. Biotech and Daily Breakout Patterns = Scanner Blindspots
Three of Ross's five tickers (NLSP, QLGN, ARNAZ) were either biotech pop-and-drops or daily breakout patterns — none of which the scanner is designed to find. JFB was a fading theme scalp. Only YWBO/YIBO was a classic gap-and-go that fit the scanner's profile.

## Missed P&L Estimate
- **ARNAZ** ($7.50→$14.00, 87% move): If the bot had found it with $50K notional at $7.50 = 6,667 shares. Ride 30% of move ($7.50→$9.45): 6,667 × $1.95 = +$13,000. Ride 50% ($7.50→$10.75): +$21,667. **This was a halt resumption dip-and-rip — the bot would need both a daily chart scanner AND halt resumption logic to capture this.**
- **QLGN** ($4.75→$5.51, 16% move): $50K notional at $4.75 = 10,526 shares. 30% capture: 10,526 × $0.23 = +$2,421.
- **JFB and NLSP**: Small scalps — missed opportunity is marginal (~$765 combined for Ross).

**Total estimated missed opportunity: ~$13,000-$21,000 (ARNAZ) + ~$2,400 (QLGN) + ~$765 (JFB/NLSP) = ~$16,000-$24,000.**

**Total bot missed P&L vs Ross: $21,000 (Ross) - $125 (bot) = ~$20,875 gap.**

## Tickers Added to Missed Stocks Backtest Plan
- NLSP (biotech pop, scanner miss)
- JFB (DeepSeek integration, scanner miss)
- QLGN (biotech low float, scanner miss)
- ARNAZ (daily breakout, scanner miss — structural limitation)

## Running Pattern Notes
Scanner overlap is back after a 4-day drought (Jan 22-27), but only on the Chinese AI continuation play. The bot's VR strategy produced a winning trade on YIBO — the first positive signal for VR on a Ross-overlapping ticker.

New patterns:
- **Day-2 continuation is scanner-visible:** YIBO missed on day 1 (Jan 27 DeepSeek) but found on day 2 (Jan 28). The overnight gap from continuation makes day-2 plays scanner-friendly.
- **Daily breakouts are a structural scanner blindspot:** ARNAZ "first candle new high" is a multi-day pattern. The scanner has no daily chart analysis capability. This is Ross's +$12K winner and represents an entirely new category of missed opportunity.
- **VR strategy shows promise on overlapping tickers:** The all-three variant's VR entry on YIBO was correct — it just needs wider exits and larger sizing.
- **Ross had 5/5 green tickers on Jan 28** — clean sweep, no losers. Mixed thematic day (Chinese continuation + biotech + daily breakout) favored Ross's diversified, discretionary approach.
