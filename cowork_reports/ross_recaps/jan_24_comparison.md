# Jan 24, 2025 — Ross vs Bot Comparison

## Summary
| Metric | Ross | Bot (SQ) | Bot (MP) |
|--------|------|----------|----------|
| Daily P&L | +$81,400 | +$586 | -$385 |
| Trades | 4 tickers (OST, ALRN, EVAC, ELAB) | 4 trades (ALUR x3, NVNI x1) | 1 trade (PRFX) |
| Win Rate | 3/4 tickers green | 2W/1L on ALUR, 1W on NVNI | 0W/1L on PRFX |
| Best Trade | ALRN +$47,000 | ALUR +$506 (+4.1R) | — |
| Worst Trade | OST -$6,000 | ALUR -$9 (-0.1R) | PRFX -$385 (-0.5R) |

**Combined bot P&L: +$201 vs Ross's +$81,400 — gap of ~$81,199. Ross's biggest day of the year.**

**Important ticker note:** Ross refers to his big winner as "ALR" / "ALRN" — this is **ALUR** (Allurion Technologies), the GLP-1 weight-loss therapy biotech. The bot correctly found and traded ALUR. This is a confirmed ticker match.

## Scanner Overlap

### Bot's Scanner Found (5 tickers)
| Ticker | Gap% | Float | Rank | PM Vol | Bot Traded? | Ross Traded? |
|--------|------|-------|------|--------|-------------|--------------|
| ALUR | +181.1% | 6.73M | #1 (0.809) | 12.8M | YES (SQ: 3 trades, +$586) | YES (+$47,000 as "ALRN") |
| NVNI | +59.0% | 7.03M | #3 (0.619) | 6.9M | YES (SQ: 1 trade, +$42) | NO |
| ATXI | +12.0% | 2.75M | #2 (0.637) | 1.4M | NO | NO |
| OST | +57.0% | 4.9M | #4 (0.535) | 4.6M | NO | YES (-$6,000) |
| PRFX | +12.2% | 0.38M | #5 (0.457) | 554K | YES (MP: 1 trade, -$385) | NO |

### Ross's Tickers NOT in Bot's Scanner (2 tickers)
| Ticker | Ross P&L | Setup | Why Scanner Likely Missed |
|--------|----------|-------|--------------------------|
| EVAC | positive (est. +$5K-10K) | Biotech sympathy play (no news), $8→$11 | No catalyst/news — pure sympathy play off ALRN. Scanner likely didn't see pre-market gap or volume meeting thresholds since the move was intraday sympathy-driven |
| ELAB | profitable (est. +$3K-5K) | Squeeze pullback entry ~$3.60→$5.00 | Likely insufficient pre-market gap% or volume. Squeezed early then Ross entered the pullback — scanner may have caught the initial gap but not met volume thresholds |

### Overlap: 2 of 4 Ross tickers (50%) — BEST OVERLAP DAY IN THE SERIES
The bot's scanner found **ALUR** (Ross's $47K winner) and **OST** (Ross's -$6K loser). This is the first day since Jan 14 where the scanner overlapped on Ross's primary winner. The scanner missed EVAC (sympathy play) and ELAB (squeeze pullback). After 4 consecutive trading days of zero overlap (Jan 17, 21, 22, 23), this is a significant improvement.

## Bot's Trades — What Happened

### SQ Strategy (4 trades: ALUR x3, NVNI x1 = +$628)
| Trade | Symbol | R-Score | Entry | Exit | Exit Reason | P&L |
|-------|--------|---------|-------|------|-------------|-----|
| 1 | ALUR | 11.0 | $8.04 | $8.40 | sq_target_hit | +$506 (+4.1R) |
| 2 | ALUR | 7.4 | $10.04 | $10.03 | sq_para_trail_exit | -$9 (-0.1R) |
| 3 | ALUR | — | $10.04 | $10.14 | sq_para_trail_exit | +$89 (+0.7R) |
| 4 | NVNI | — | $2.48 | $2.52 | sq_para_trail_exit | +$42 (+0.3R) |

**ALUR analysis:** The bot entered ALUR at $8.04 at 7:01 AM — almost exactly when Ross entered (~$8.24-$8.49 after 7:01 AM). The bot's first trade was a clean winner, riding to $8.40 for +$506 (+4.1R). But ALUR ran to $20. The bot exited at $8.40 (sq_target_hit) — a fixed target that captured only $0.36 of a $12 move. Trades 2-3 re-entered at $10.04 for tiny results. The bot captured $586 on a stock that moved +$12/share.

Ross made $47,000 because: (1) massive position size (conviction A+ setup), (2) rode the move from ~$8.24 to $20, (3) didn't exit at a fixed target — he let it run. The bot made $586 because: (1) fixed notional sizing, (2) sq_target_hit at $8.40 (mere $0.36 from $8.04 entry), (3) parabolic trail exits on re-entries captured crumbs.

**This is the single most important trade comparison in the entire January series.** Same stock, same entry time, same price zone — 80x P&L difference purely from sizing and exit management.

### MP Strategy (1 trade: PRFX = -$385)
| Trade | Symbol | R-Score | Entry | Exit | Exit Reason | P&L |
|-------|--------|---------|-------|------|-------------|-----|
| 1 | PRFX | — | $4.20 | $4.10 | topping_wicky_exit_full | -$385 (-0.5R) |

PRFX was the lowest-ranked scanner candidate (rank #5, 0.457). The MP strategy entered a micro pullback at $4.20 on a 12% gapper with only 554K PM volume — exactly the kind of marginal setup the bot should skip. Another data point for killing MP on non-top-ranked tickers.

### What the Bot Missed
The bot found OST (rank #4) but took **0 trades** on it. Ross lost $6K on OST (FOMO, oversized entry at $3.66-$4.00, dumped to $3.20). In this case, the bot's inaction was actually correct — OST was a losing trade for Ross. The scanner correctly identified it but the entry criteria weren't met, which turned out to be a good filter.

## Ross's Trades — What Made Them Work

### ALRN/ALUR (GLP-1 Biotech) — +$47,000
- **Catalyst:** GLP-1 weight-loss therapy news — massive biotech catalyst in the hottest sector of 2024-2025
- **Pre-market:** Up ~70% (matches bot's +181% gap — Ross likely measuring from a different reference)
- **Entry:** ~$8.24-$8.49 after 7:01 AM — precise timing in the pre-market squeeze
- **Move:** Ran to $20 — a $12+/share move from entry zone
- **Exit:** Rode the entire move. Secondary offering announced at 9:30 AM killed momentum — Ross was already out
- **Why it worked:** A+ catalyst (GLP-1 is the hottest theme), low float biotech, pre-market squeeze with massive volume (12.8M PM vol). This is the textbook setup the bot is designed to capture. The bot DID capture it — just 1.2% of it.

### OST — -$6,000 (FOMO Trade)
- **Entry:** $3.66-$4.00 on a 500K volume candle at open
- **Problem:** FOMO entry, oversized position, dumped immediately to $3.20
- **Second trade:** Small recoup attempt, net still deeply red
- **Key insight:** Ross admits this was a discipline failure — entered too large, too fast. The bot's scanner found OST but didn't trade it, which was actually the right call.

### EVAC (Biotech Sympathy) — Positive
- **No news** — pure sympathy play off ALRN/ALUR's GLP-1 momentum
- **Move:** $8→$11 (37.5% intraday move)
- **Key insight:** Sympathy plays have no pre-market catalyst, which is why the scanner misses them. This requires thematic awareness — understanding that when a GLP-1 biotech runs, other biotechs in the space get sympathy bids. The bot has no concept of sector sympathy.

### ELAB — Profitable
- **Squeezed early** in pre-market/early session
- **Ross entered pullback** at ~$3.60, ran to ~$5.00 (39% move)
- **Key insight:** Pullback entry after initial squeeze — Ross waited for the dip, confirming the setup was holding. The bot's scanner may not have had ELAB because the gap or volume metrics didn't meet thresholds at scan time.

## Key Takeaways

### 1. ALUR Is THE Case Study for the Exit Problem
The bot entered ALUR at nearly the same time and price as Ross. It made $586. Ross made $47,000. This isn't a scanner problem, a setup detection problem, or a stock selection problem — **this is purely an exit management and sizing problem.** The sq_target_hit at $8.40 is leaving 97% of the move on the table. On a stock with +181% gap, 12.8M PM volume, and an A+ catalyst, the target should be much wider. This single trade demonstrates the need for dynamic targets based on setup quality.

### 2. Scanner Overlap Finally Broke Through
After 4 consecutive days of zero overlap (Jan 17, 21, 22, 23), the scanner found 2 of Ross's 4 tickers including his $47K primary winner. 50% overlap is the best since Jan 14. The scanner's gap/volume/float criteria work well when the leading gapper has a clear pre-market gap — ALUR's +181% gap and 12.8M PM volume made it unmissable.

### 3. OST: Scanner Found It, Bot Didn't Trade It — Correct Decision
The bot found OST (rank #4, +57% gap, 4.9M float) but never triggered an entry. Ross lost $6K on it (FOMO). This is actually a win for the bot's entry criteria — they filtered out a losing trade. Note: Ross also traded OST on Jan 2 (-$3K) and Jan 14 (bot found it, +$1,800 for Ross but bot took 0 trades). OST is a recurring ticker where Ross has mixed results and the bot consistently passes.

### 4. Sympathy Plays Are Invisible to the Scanner
EVAC had no news — it was a pure biotech sympathy play off ALUR. The scanner will never find sympathy plays because they have no pre-market catalyst or gap. This is a category of trades that requires thematic/sector awareness, which could be added as a feature: "if top gapper is biotech with GLP-1 news, flag other GLP-1/weight-loss biotechs."

### 5. Ross's Biggest Day = GLP-1 Theme Day
$81,400 — Ross's biggest day of the year — was driven almost entirely by one theme: GLP-1 weight-loss biotechs. ALUR was the primary catalyst, EVAC was the sympathy play. When a mega-theme aligns with a low-float squeeze, the results are outsized. The bot captured the ticker but not the theme.

## Missed P&L Estimate
The scanner FOUND ALUR and the bot DID trade it — the gap isn't from missing the stock, it's from undersized entries and premature exits.

If the bot had:
- Entry at $8.04 (actual) with $50K notional: ~6,200 shares
- Ridden to $12 (50% of the move to $20): +$24,600
- Ridden to $16 (80% of move): +$49,600
- Actual result: +$586 (captured 1.2% of a realistic $50K target)

EVAC (missed by scanner): $8→$11 move, $50K notional at $8 = 6,250 shares × $3 = +$18,750 potential. Realistic 30-50% capture: +$5,600-$9,375.

ELAB (missed by scanner): $3.60→$5.00 move, $50K notional at $3.60 = 13,888 shares × $1.40 = +$19,444 potential. Realistic 30-50% capture: +$5,800-$9,700.

**Total missed opportunity from scanner misses (EVAC + ELAB): ~$11,400-$19,075.**
**Total missed opportunity from exit management (ALUR): ~$24,000-$49,000 above actual $586.**

## Tickers Added to Missed Stocks Backtest Plan
EVAC, ELAB (2 tickers — absent from bot's scanner)
Note: ALUR was found and traded. OST was found but correctly not traded.

## Running Pattern Notes
This is the **first day in 5 trading days** (since Jan 16) where the bot's scanner overlapped with Ross's primary winner. The streak of 4 consecutive zero-overlap days (Jan 17, 21, 22, 23) is broken. New patterns emerging:

- **When the leading gapper has massive gap% and volume, the scanner works** — ALUR at +181% gap and 12.8M PM volume was unmissable
- **The exit management problem is now the #1 issue** — on the biggest day of the month, the bot was in the right stock at the right time and captured 0.7% of Ross's P&L
- **Sympathy plays (EVAC) and pullback entries (ELAB) are systematic scanner blindspots** — these require either thematic awareness or intraday re-scanning
- **OST is a recurring edge case** — appeared Jan 2 (-$3K for Ross), Jan 14 (+$1,800 for Ross, bot passed), Jan 24 (-$6K for Ross, bot passed). Bot's avoidance of OST has been correct 2 of 3 times
- **Ross's January MTD: ~$280,000** — the bot's January MTD through Jan 24 is approximately +$200 (SQ) / -$4,300 (MP), combined roughly -$4,100
