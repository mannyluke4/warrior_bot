# Warrior Trading Scanner vs Our Scanner — Full Comparison Backtest

**Generated:** 2026-03-24
**Author:** CC (Sonnet) executing Cowork (Opus) directive
**Config:** V1 (SQ+MP enabled, Pillar gates OFF, Ross exit OFF, $1000 risk)
**Data:** 91 stocks from 10 trading days of Manny's manual WT scanner tracking

---

## Section A: Overall Results

```
Total stocks backtested:     91
Stocks with data:            91 (0 NO DATA — all resolved!)
Stocks with trades:          40 (44%)
Stocks with 0 trades:        51 (56%)
Total trades:                68
Total P&L:               +$52,504
Win Rate:                    53% (36W / 32L)
Strategy split:              43 SQ / 25 MP trades
```

### Per-Day Breakdown

| Day | Date | Stocks | Traded | Trades | P&L |
|-----|------|--------|--------|--------|-----|
| 1 | Jan 12 | 9 | 2 | 3 | +$2,241 |
| 2 | Jan 13 | 12 | 5 | 7 | +$9,742 |
| 3 | Jan 14 | 9 | 6 | 11 | +$17,555 |
| 4 | Jan 15 | 10 | 5 | 13 | +$11,761 |
| 5 | Jan 16 | 9 | 3 | 4 | +$478 |
| 6 | Feb 9 | 6 | 2 | 2 | +$5,981 |
| 7 | Feb 10 | 7 | 5 | 7 | +$2,271 |
| 8 | Feb 11 | 8 | 1 | 1 | +$312 |
| 9 | Feb 12 | 10 | 4 | 6 | +$2,851 |
| 10 | Feb 13 | 11 | 7 | 14 | -$688 |

**Jan week: +$41,777** (49 stocks, 21 traded, 38 trades)
**Feb week: +$10,727** (42 stocks, 19 traded, 30 trades)

Jan was 4x more profitable despite similar trade counts — the Jan week had bigger runners (ROLR, BCTX, CJMB, SPHL).

---

## Section B: Our Scanner vs WT Scanner

```
╔═══════════════════════════════════════════════════════════════════════════╗
║                  OUR SCANNER vs WT-ONLY STOCKS                          ║
╠════════════════════╦══════════════╦══════════════╦═════════════════════╣
║ Metric             ║ Our Scanner  ║ WT-Only      ║ Delta               ║
╠════════════════════╬══════════════╬══════════════╬═════════════════════╣
║ Total stocks       ║           11 ║           80 ║                     ║
║ Stocks traded      ║      7 (64%) ║     33 (41%) ║ Our scanner trades  ║
║                    ║              ║              ║ more often           ║
║ Total trades       ║           17 ║           51 ║                     ║
║ Total P&L          ║     +$41,839 ║     +$10,665 ║ +$10,665 on table   ║
║ Win Rate           ║          76% ║          45% ║ -31% lower          ║
║ Avg P&L/stock      ║      +$3,803 ║        +$133 ║                     ║
║ Avg P&L/trade      ║      +$2,461 ║        +$209 ║                     ║
╚════════════════════╩══════════════╩══════════════╩═════════════════════╝
```

### Key Finding: Our scanner already picks the BEST stocks

Our 11 stocks (12% of the total) captured **80% of the total P&L** ($41,839 / $52,504). The remaining 80 WT-only stocks added only $10,665 — but that's still meaningful money.

The WT-only stocks trade at much lower win rates (45% vs 76%) and much lower average P&L per trade ($209 vs $2,461). Our scanner's filters are working — they select for the highest-quality setups.

### What's on the table from WT-only stocks: +$10,665

However, this includes both winners and losers. The top WT-only performers:
1. **MNTS** (Feb 9): +$6,148 — 1.3M float, no gap data. Would pass our scanner with gap fix.
2. **PMI** (Feb 12): +$2,953 — 26.1M float. Too high for current filter.
3. **OM** (Jan 12): +$2,911 — 13.1M float. Just above our 10M max.
4. **SMX** (Feb 10): +$1,962 — micro float. Would pass our scanner.
5. **UPWK** (Feb 10): +$1,166 — 32.8M float. Too high.

---

## Section C: Performance by Float Bucket (THE KEY ANALYSIS)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                         P&L BY FLOAT BUCKET                                ║
╠═══════════╦════════╦════════╦════════╦══════════╦═════════╦════════════════╣
║ Float     ║ Stocks ║ Traded ║ Trades ║ P&L      ║ Win Rate║ P&L/Trade     ║
╠═══════════╬════════╬════════╬════════╬══════════╬═════════╬════════════════╣
║ < 1M      ║     12 ║      3 ║      7 ║  +$6,680 ║     71% ║      +$954    ║
║ 1-5M      ║     21 ║      9 ║     16 ║ +$14,138 ║     62% ║      +$884    ║
║ 5-10M     ║      5 ║      1 ║      1 ║    -$429 ║      0% ║      -$429    ║
║ 10-20M    ║     11 ║      6 ║      9 ║  +$1,424 ║     44% ║      +$158    ║
║ 20-50M    ║     16 ║      7 ║     11 ║  +$3,190 ║     45% ║      +$290    ║
║ 50-100M   ║      2 ║      1 ║      1 ║    -$378 ║      0% ║      -$378    ║
║ > 100M    ║      7 ║      4 ║      6 ║     -$81 ║     50% ║       -$14    ║
║ Unknown   ║     17 ║      9 ║     17 ║ +$27,960 ║     53% ║    +$1,645    ║
╚═══════════╩════════╩════════╩════════╩══════════╩═════════╩════════════════╝
```

### Clear Pattern:

1. **< 1M and 1-5M are the sweet spot**: 71% and 62% win rates, $954 and $884 per trade. These are our core.
2. **5-10M is a dead zone**: Only 1 trade, a loss. Small sample but concerning.
3. **10-20M is marginal**: 44% WR, +$158/trade. Some winners (OM +$2,911) but also losers (SRTS -$907).
4. **20-50M is surprisingly ok**: 45% WR, +$290/trade. PMI +$2,953 anchors this.
5. **50M+ is unprofitable**: Combined -$459 across 7 trades. Hard avoid.
6. **Unknown float stocks**: +$27,960 — This is huge. ROLR (+$18,353), BCTX (+$9,552), GWAV (+$2,019) are all unknown float. We MUST resolve these floats.

### Recommendation: Keep 10M max, but resolve unknown floats

The data shows < 5M float is clearly the best. Expanding to 15-20M would add ~$1,424 but also add noise and losses. The bigger opportunity is resolving the 17 unknown-float stocks — they contain $27,960 in P&L, and many are likely sub-5M floats.

---

## Section D: Performance by Discovery Time

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                      P&L BY DISCOVERY TIME                                 ║
╠════════════════╦════════╦════════╦════════╦══════════╦═════════════════════╣
║ Time Window    ║ Stocks ║ Traded ║ Trades ║ P&L      ║ Win Rate            ║
╠════════════════╬════════╬════════╬════════╬══════════╬═════════════════════╣
║ 07:00-07:30    ║     16 ║      9 ║     18 ║ +$10,091 ║  50%                ║
║ 07:30-08:00    ║      9 ║      3 ║      3 ║  +$9,206 ║  33%  (low N)       ║
║ 08:00-08:30    ║     17 ║      9 ║     17 ║ +$26,875 ║  71%  ← BEST       ║
║ 08:30-09:00    ║     21 ║     11 ║     19 ║  +$5,611 ║  53%                ║
║ 09:00-09:30    ║     16 ║      6 ║      7 ║  +$3,151 ║  43%                ║
║ 09:30-10:00    ║     12 ║      2 ║      4 ║  -$2,430 ║  25%  ← WORST      ║
╚════════════════╩════════╩════════╩════════╩══════════╩═════════════════════╝
```

### Clear Pattern:

1. **08:00-08:30 is the golden hour**: 71% win rate, +$26,875 P&L. This is when the strongest setups fire. ROLR, GSIT, FEED, MNTS, CJMB all discovered here.
2. **07:00-08:00 is solid**: +$19,297 combined. Early birds catch the worm. BCTX (07:40), SPHL (07:01) were big winners.
3. **08:30-09:00 is decent**: +$5,611, 53% WR. Acceptable but the edge is fading.
4. **09:00-09:30 is marginal**: +$3,151 but only 43% WR. PMI (+$2,953) carried this window.
5. **09:30+ is a losing proposition**: -$2,430, 25% WR. The bot should NOT be trading stocks discovered after 9:30.

### Recommendation: Weight discovery time heavily

- **Prime time: 07:00-08:30** — This is where 88% of the P&L comes from (+$46,172 / $52,504)
- **Acceptable: 08:30-09:00** — Modest edge, worth trading
- **Avoid: 09:30+** — Negative expected value. Consider a hard cutoff or reduced position sizing

---

## Section E: Performance by Strategy

```
Strategy breakdown across all 68 trades:
  SQ (squeeze):         43 trades (63%)
  MP (micro-pullback):  25 trades (37%)
```

SQ dominates the trade count. The SQ strategy fires more frequently on WT scanner stocks because many are low-float momentum plays — exactly what squeeze detection targets.

MP trades tend to come later in the session after the initial squeeze fades and the stock establishes a pullback pattern.

### Our Scanner vs WT-Only by Strategy

Our scanner stocks produced the highest-R trades (ROLR 4T/+$18,353, BCTX 1T/+$9,552). These are the stocks where both strategies align — the scanner picks the right stock, AND the stock produces clean setups.

WT-only stocks still produced some excellent SQ trades (MNTS +$6,148, PMI +$2,953, OM +$2,911) but at much lower consistency.

---

## Section F: Top 10 Performers

| Rank | Ticker | Date | Trades | P&L | Float | Our Scanner? |
|------|--------|------|--------|-----|-------|-------------|
| 1 | ROLR | Jan 14 | 4 | +$18,353 | ? | YES |
| 2 | BCTX | Jan 13 | 1 | +$9,552 | ? | YES |
| 3 | MNTS | Feb 9 | 1 | +$6,148 | 1.3M | no |
| 4 | CJMB | Jan 15 | 4 | +$5,846 | 1.4M | YES |
| 5 | SPHL | Jan 15 | 4 | +$4,682 | 0.5M | YES |
| 6 | PMI | Feb 12 | 1 | +$2,953 | 26.1M | no |
| 7 | OM | Jan 12 | 2 | +$2,911 | 13.1M | no |
| 8 | GWAV | Jan 16 | 1 | +$2,019 | ? | YES |
| 9 | SMX | Feb 10 | 2 | +$1,962 | 0.0M | no |
| 10 | AHMA | Jan 13 | 2 | +$1,813 | 2.0M | YES |

### Bottom 5 Performers

| Rank | Ticker | Date | Trades | P&L | Float | Our Scanner? |
|------|--------|------|--------|-----|-------|-------------|
| 1 | WEN | Feb 13 | 1 | -$1,523 | 145.5M | no |
| 2 | KULR | Jan 14 | 2 | -$1,289 | 42.6M | no |
| 3 | NUKK | Jan 13 | 1 | -$1,214 | ? | no |
| 4 | NUKK | Jan 16 | 2 | -$1,115 | ? | no |
| 5 | SRTS | Feb 13 | 3 | -$907 | 13.7M | no |

**Pattern:** All 5 worst performers are WT-only stocks. 3 of 5 have float > 10M. Our scanner correctly filtered these out.

---

## Section G: The Bot's Pillars (Recommendations)

Based on this 91-stock, 10-day study, the bot's optimal stock selection criteria are:

### Pillar 1: Float < 5M (ideally < 3M)
- Stocks with < 5M float: 71%/62% win rate, +$884-954/trade
- Stocks with > 50M float: losing money overall
- **Action:** Keep current 10M max. Do NOT expand. Focus on resolving unknown floats.

### Pillar 2: Discovery Time 07:00-08:30
- 88% of all P&L ($46,172) comes from stocks discovered before 08:30
- 08:00-08:30 is the single best 30-minute window (71% WR, +$26,875)
- Stocks discovered after 09:30 have NEGATIVE expected value (-$2,430)
- **Action:** Implement time-weighted position sizing or hard cutoff at 09:30

### Pillar 3: Our Scanner Already Selects Winners
- 12% of stocks (our scanner's picks) = 80% of P&L
- Our scanner stocks: 76% WR, +$2,461/trade
- WT-only stocks: 45% WR, +$209/trade
- **Action:** Trust the scanner filters. The incremental P&L from WT-only stocks (+$10,665) comes with much higher risk.

### Pillar 4: SQ Strategy Dominance
- 63% of all trades are SQ (squeeze) entries
- SQ fires more frequently and earlier in the session
- MP fires later as a follow-up strategy
- **Action:** SQ remains the primary strategy for scanner-driven trading

### Pillar 5: Avoid High-Float Noise
- Every stock in the bottom 5 is either high-float or unknown-float from the WT-only group
- WEN (145M float), KULR (42.6M), SRTS (13.7M) — all losses
- **Action:** The 10M float max is a feature, not a limitation

---

## What +$10,665 From WT-Only Stocks Means

If we added the full WT scanner feed, the bot would make an additional ~$10,665 over these 10 days. But:

- It would also take 51 additional trades at 45% win rate (vs 76%)
- The added risk and drawdown from 80 additional stocks may not be worth it
- The best WT-only performers (MNTS, PMI, OM) could potentially be caught by:
  - Resolving unknown floats (MNTS at 1.3M would pass our filters)
  - Adding intraday scanner checkpoints (some were session runners)
  - Modest float cap increase to 15M (OM at 13.1M)

### Net recommendation:
1. **Resolve unknown floats** — Biggest bang for buck. 17 unknown-float stocks contain $27,960.
2. **Add intraday scanner checkpoints** — Catches session runners our PM-only scanner misses.
3. **Consider 15M float cap** — Would add OM (+$2,911) and a few others, net positive.
4. **Hard cutoff at 09:30** — Stocks discovered after 09:30 are negative EV.
5. **Do NOT add full WT feed** — Marginal gains with significantly lower quality.
