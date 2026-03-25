# Jan 23, 2025 — Ross vs Bot Comparison

## Summary
| Metric | Ross | Bot (SQ) | Bot (MP) |
|--------|------|----------|----------|
| Daily P&L | ~$40,000+ | -$76 | $0 |
| Trades | 4 tickers (DGNX, DXST, MIMI, SPCB) | 3 trades (VNCE only) | 0 trades |
| Win Rate | 1/4 tickers big green, 1 small green, 2 scratch | 1W/2L on VNCE | N/A |
| Best Trade | DGNX +$22,997 | VNCE +$55 | — |
| Worst Trade | DXST ~breakeven (lost $3K on dip) | VNCE -$109 | — |

**Combined bot P&L: -$76 vs Ross's ~$40,000+ — gap of ~$40,076.**

## Scanner Overlap

### Bot's Scanner Found (4 tickers)
| Ticker | Vol | Rank | Bot Traded? | Ross Traded? |
|--------|-----|------|-------------|--------------|
| VNCE | 6,453,109 | #1 | YES (3 trades, -$76) | NO |
| LSH | 1,743,876 | #2 | NO | NO |
| HKPD | 1,516,830 | #3 | NO | NO |
| NTRB | 550,781 | #4 | NO | NO |

### Ross's Tickers NOT in Bot's Scanner (5 tickers)
| Ticker | Ross P&L | Setup | Why Scanner Likely Missed |
|--------|----------|-------|--------------------------|
| DGNX | +$22,997 | Chinese IPO day 2, Level 2 tape entry | IPO day 2 — likely didn't meet gap% threshold on day 2, or Chinese IPO characteristics (pricing, float reporting) confuse the scanner |
| DXST | ~breakeven | Chinese IPO chase | Same Chinese IPO issue — scanner may not handle fresh IPOs with unreliable float/volume data |
| MIMI | ~breakeven | Chinese IPO momentum | Third Chinese IPO — same scanner blindspot |
| SPCB | small positive | Breaking news (debt restructuring) | Debt restructuring news — may not have gapped enough pre-market, or float/price outside scanner parameters |
| DWTX | not traded (missed) | Biotech, $3.50→$7+ | Ross missed it too. Interesting: bot scanner had DWTX on Jan 21 (rank #2, +40.59% gap, 1.35M float) but NOT on Jan 23 when it actually ran 100% |

### Overlap: ZERO
The bot's scanner found **0 of Ross's 4 traded tickers** and **0 of 5 total tickers on Ross's radar**. Complete scanner whiff. The scanner found 4 tickers (VNCE, LSH, HKPD, NTRB) that were entirely off Ross's radar. Only VNCE generated bot trades, and those lost money.

## Bot's Trades — What Happened

### SQ Strategy (3 trades on VNCE, -$76)
| Trade | R-Multiple | Entry | Exit | Exit Reason | P&L |
|-------|-----------|-------|------|-------------|-----|
| 1 | 9.5 | $4.04 | $4.06 | sq_para_trail_exit | +$55 |
| 2 | 17.5 | $4.21 | $4.21 | topping_wicky_exit_full | -$22 |
| 3 | 11.0 | $4.64 | $4.60 | sq_para_trail_exit | -$109 |

VNCE was a $4 stock with 6.4M volume. The bot found a squeeze setup (R=9.5) and entered at $4.04, capturing a tiny +$0.02 move before the parabolic trail exited. Trade 2 was a scratch (topping wicky exit). Trade 3 entered higher at $4.64 and got caught in a pullback, losing $0.04/share.

All three trades show the bot's characteristic pattern: finding real setups but capturing only tiny moves (+$55 best) or taking small losses on re-entries (-$109 worst). Net effect: -$76 on a stock that wasn't on any experienced trader's radar.

### MP Strategy (0 trades, $0)
No MP signals triggered on any of the 4 scanner candidates.

## Ross's Trades — What Made Them Work

### DGNX (Chinese IPO Day 2) — +$22,997
- **Catalyst:** Chinese IPO, IPO'd prior afternoon, ~2.25M float
- **Pre-market:** Spiked to $24, pulled back significantly
- **Entry:** $15.55 — Ross read the Level 2 tape and spotted a large bidder holding that level
- **Execution:** Rode the squeeze from $15.55 to $20+, then took multiple dip trades on pullbacks
- **Key insight:** This is pure discretionary tape reading. Ross didn't enter on a chart pattern — he entered because he saw institutional-level buying on Level 2. This is extremely hard to automate. The $15.55 entry on a stock that pre-market hit $24 shows patience and conviction.
- **Why it worked:** Day 2 Chinese IPOs with sub-3M floats can have extreme squeezes. The pullback from $24 created a fear-driven dip that Ross exploited. The large bidder on Level 2 was the confirmation signal.

### DXST (Second Chinese IPO) — ~Breakeven
- **Catalyst:** Chinese IPO (same batch as DGNX)
- **Entry:** Chased from ~$7.50-$8.50
- **Move:** Ran to $14 (nearly 100% from entry zone)
- **Problem:** Failed dip trade re-entry cost ~$3K, wiping out chase profits
- **Key insight:** Even Ross gets burned chasing the second name in a thematic cluster. The DGNX win may have created overconfidence on DXST's dip.

### MIMI (Third Chinese IPO) — ~Breakeven
- **Near flush** — Ross narrowly avoided a loss
- **Key insight:** By the third Chinese IPO, the momentum was fading. Ross's risk management (quick cut) saved him from a red trade.

### SPCB (Debt Restructuring News) — Small Positive
- **Recurring name** — also appeared Jan 2 (watchlist) and Jan 3 (+$2,600)
- **Debt restructuring breaking news** — real catalyst
- **Smaller contribution** to the daily total

## Key Takeaways

### 1. Chinese IPO Day — A Scanner Blindspot Category
Jan 23 was dominated by three Chinese IPOs (DGNX, DXST, MIMI). The bot's scanner found NONE of them. This is a systematic scanner gap: Chinese IPOs often have unusual characteristics (unreliable float data from IPO prospectus, volatile pre-market pricing, day 2 gap patterns that differ from standard small-cap gappers). The scanner needs specific handling for recent IPOs.

### 2. Level 2 Tape Reading Is Ross's Unfair Advantage
The DGNX entry at $15.55 was based on reading a large bidder on Level 2 — not a chart pattern, not a gap%, not relative volume. This is a skill that takes years to develop and is essentially impossible to replicate algorithmically without real-time Level 2 data feeds and order flow analysis. This single discretionary read produced +$22,997.

### 3. DWTX: The One They Both Missed
DWTX (biotech) ran $3.50→$7+ on Jan 23. Ross missed it. The bot's scanner had DWTX on Jan 21 (rank #2 candidate, +40.59% gap, 1.35M float) but did NOT pick it up on Jan 23. This suggests DWTX's gap/volume characteristics were different on Jan 23 (possibly a delayed/intraday catalyst rather than a pre-market gap), which is exactly the type of setup the scanner misses.

### 4. Fourth Consecutive Trading Day of Complete Scanner Miss
Jan 17, 21, 22, and now 23 — four straight days with zero scanner overlap on Ross's traded tickers. The scanner's gap/volume/float thresholds are systematically missing the tickers that an experienced trader focuses on. This is no longer a coincidence; it's a structural problem.

### 5. Thematic Clustering — Ross Reads the Market's Theme
Ross identified "Chinese IPO day" as the theme and focused his attention there. The bot has no concept of thematic trading — it scans mechanically for gap/volume/float regardless of the day's narrative. Adding thematic awareness (e.g., clustering IPOs, sector momentum, news-driven themes) could help the scanner prioritize better.

## Missed P&L Estimate
If the bot had found DGNX and traded the squeeze from $15.55 to $20:
- $4.45/share move
- At bot's $50K max notional: ~3,215 shares × $4.45 = +$14,307
- Realistic 30-50% capture: +$4,300-$7,150

DXST and MIMI were breakeven for Ross, so missed P&L there is ~$0.

SPCB was a small positive — maybe +$500-$1,000 missed.

**Total missed opportunity: estimated $4,800-$8,150 if scanner had found DGNX and SPCB.**

## Tickers Added to Missed Stocks Backtest Plan
DGNX, DXST, MIMI, SPCB (4 tickers — all absent from bot's scanner)
DWTX also added (Ross missed it too, but big runner worth backtesting — bot had it on Jan 21 scanner but not Jan 23)

## Running Pattern Notes
This is the **4th consecutive trading day** (Jan 17, 21, 22, 23) where the bot's scanner missed ALL of Ross's traded tickers. The scanner found 0 of the 4 tickers Ross traded on Jan 23. Emerging patterns:
- **Chinese IPOs are completely invisible** to the scanner (3 IPOs missed on one day)
- **Recurring names** (SPCB appeared Jan 2, 3, and 23) don't get special treatment in the scanner
- **DWTX case:** The scanner found a stock 2 days earlier (Jan 21) but missed it on the day it actually ran 100% — suggests the scanner is gap-dependent and misses intraday/delayed catalysts
- **Level 2/tape reading setups** (Ross's DGNX entry) are fundamentally outside the bot's capability set
- The bot's Jan 23 activity (3 marginal trades on VNCE for -$76) exemplifies the "noise trading" problem — the bot trades what the scanner finds even when there's no real edge, while the actual opportunities are elsewhere entirely
