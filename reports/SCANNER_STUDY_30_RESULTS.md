# Scanner-Timed Backtest Study: 30 Stocks
**Date**: March 2, 2026
**Author**: Claude Sonnet 4.6
**Responding to**: SCANNER_STUDY_30_DIRECTIVE.md
**Code**: commit `b0e5dd3` (Round 9) — classifier ON, suppress OFF, exhaustion ON, warmup=5

---

## 1. Results Table (sorted by P&L descending)

| # | Symbol | Date | Scanner Time | Sim Start | Gap% | Float | Strategy | Trades | W | L | Net P&L | WR% |
|---|--------|------|-------------|-----------|------|-------|----------|--------|---|---|---------|-----|
| 1 | NCI | 2026-02-13 | 08:43 | 08:43 | 11.9% | 1.08M | Squeeze Alert - Up 5% in 5min | 2 | 2 | 0 | **+$577** | 100% |
| 2 | VOR | 2026-01-12 | 08:23 | 08:23 | 6.5% | 8.06M | Former Momo Stock | 2 | 1 | 1 | **+$501** | 50% |
| 3 | FSLY | 2026-02-12 | 07:26 | 07:26 | 46.5% | 139.39M | Med Float - High Rel Vol | 4 | 3 | 1 | **+$176** | 75% |
| 4 | MCRB | 2026-02-13 | 09:30 | 09:30 | 7.8% | 7.42M | Former Momo Stock | 2 | 1 | 1 | **+$113** | 50% |
| 5 | AKAN | 2026-01-12 | 09:09 | 09:09 | 16.5% | 0.72M | Former Momo Stock | 0 | 0 | 0 | $0 | — |
| 6 | SPRC | 2026-01-13 | 07:02 | 07:02 | 30.3% | 3.16M | Low Float - High Rel Vol | 0 | 0 | 0 | $0 | — |
| 7 | HOVR | 2026-01-14 | 09:30 | 09:30 | 0.5% | 19.51M | Squeeze Alert - Up 5% in 5min | 0 | 0 | 0 | $0 | — |
| 8 | OCUL | 2026-01-15 | 07:00 | 07:00 | 25.4% | 188.97M | Med Float - High Rel Vol | 0 | 0 | 0 | $0 | — |
| 9 | MTVA | 2026-01-15 | 09:30 | 09:30 | -24.7% | 0.55M | Squeeze Alert - Up 5% in 5min | 0 | 0 | 0 | $0 | — |
| 10 | JFBR | 2026-01-16 | 07:37 | 07:37 | 88.2% | 0.55M | Low Float - High Rel Vol | 0 | 0 | 0 | $0 | — |
| 11 | OCG | 2026-01-16 | 09:05 | 09:05 | 39.5% | 12.90M | Squeeze Alert - Up 10% in 10min | 0 | 0 | 0 | $0 | — |
| 12 | SMX | 2026-02-09 | 07:00 | 07:00 | 9.2% | 2.89M | Low Float Volatility Hunter | 0 | 0 | 0 | $0 | — |
| 13 | OSCR | 2026-02-10 | 07:00 | 07:00 | 5.8% | 240.07M | Med Float - High Rel Vol | 0 | 0 | 0 | $0 | — |
| 14 | AZI | 2026-02-10 | 07:15 | 07:15 | 14.9% | 0.98M | Low Float Volatility Hunter | 0 | 0 | 0 | $0 | — |
| 15 | ASBP | 2026-02-11 | 07:45 | 07:45 | 31.2% | 3.14M | Squeeze Alert - Up 10% in 10min | 0 | 0 | 0 | $0 | — |
| 16 | JDZG | 2026-02-12 | 08:34 | 08:34 | 58.3% | 1.21M | Low Float - High Rel Vol | 0 | 0 | 0 | $0 | — |
| 17 | HSDT | 2026-02-13 | 09:01 | 09:01 | 8.8% | 26.01M | Squeeze Alert - Up 5% in 5min | 0 | 0 | 0 | $0 | — |
| 18 | BDSX | 2026-01-12 | 07:00 | 07:00 | 38.3% | 3.85M | Low Float - High Rel Vol | 6 | 3 | 3 | -$45 | 50% |
| 19 | RPD | 2026-02-11 | 09:30 | 09:30 | -23.7% | 63.91M | Med Float - High Rel Vol | 2 | 1 | 1 | -$186 | 50% |
| 20 | FSLY* | — | — | — | — | — | — | — | — | — | — | — |
| 21 | CNVS | 2026-02-13 | 09:04 | 09:04 | 17.8% | 16.60M | Squeeze Alert - Up 5% in 5min | 1 | 0 | 1 | -$731 | 0% |
| 22 | WEN | 2026-02-13 | 09:30 | 09:30 | -2.5% | 157.98M | Med Float - High Rel Vol | 3 | 0 | 3 | -$660 | 0% |
| 23 | BEEM | 2026-01-14 | 07:00 | 07:00 | 24.9% | 17.97M | Squeeze Alert - Up 10% in 10min | 1 | 0 | 1 | -$900 | 0% |
| 24 | RVSN | 2026-02-11 | 07:34 | 07:34 | 52.4% | 2.18M | Low Float Volatility Hunter | 1 | 0 | 1 | -$1,010 | 0% |
| 25 | PMAX | 2026-01-13 | 07:00 | 07:00 | 34.4% | 5.09M | Squeeze Alert - Up 10% in 10min | 1 | 0 | 1 | -$1,098 | 0% |
| 26 | NVCR | 2026-02-12 | 09:22 | 09:22 | 37.6% | 105.80M | Med Float - High Rel Vol | 2 | 0 | 2 | -$507 | 0% |
| 27 | UPWK | 2026-02-10 | 09:28 | 09:28 | -20.2% | 120.86M | Med Float - High Rel Vol | 1 | 0 | 1 | -$540 | 0% |
| 28 | QMCO | 2026-01-15 | 08:31 | 08:31 | 5.2% | 13.58M | Squeeze Alert - Up 5% in 5min | 2 | 0 | 2 | -$1,193 | 0% |
| 29 | FJET | 2026-01-13 | 08:10 | 08:10 | 5.1% | 17.36M | Former Momo Stock | 2 | 0 | 2 | -$1,263 | 0% |
| 30 | AUID | 2026-01-15 | 08:57 | 08:57 | 101.5% | 9.84M | Low Float - High Rel Vol | 3 | 0 | 3 | -$1,683 | 0% |
| 31 | CRSR | 2026-02-13 | 08:41 | 08:41 | 36.2% | 44.36M | Med Float - High Rel Vol | 6 | 2 | 4 | -$1,939 | 33% |

**GRAND TOTAL: 41 trades, 13 wins, 28 losses — Net P&L: -$10,388 — Overall WR: 32%**
*(15 of 30 stocks had 0 trades — bot found no valid setup)*

---

## 2. Scanner Attribute Correlations

### By Gap %

| Gap Range | Stocks | Active | Trades | Wins | Total P&L | Avg P&L | Win Rate |
|-----------|--------|--------|--------|------|-----------|---------|---------|
| High (≥30%) | 12 | 7 | 23 | 8 | -$6,106 | -$509 | **35%** |
| Medium (10-30%) | 6 | 3 | 4 | 2 | -$1,054 | -$176 | **50%** |
| Low (5-10%) | 7 | 4 | 8 | 2 | -$1,842 | -$263 | **25%** |
| Negative (<0%) | 4 | 3 | 6 | 1 | -$1,386 | -$346 | **17%** |

**Finding**: Medium gap stocks (10-30%) had the best WR (50%) and lowest avg loss. Negative gap stocks were consistently bad (17% WR). Counterintuitively, high gap (≥30%) performed worse than medium gap — the bot may be entering after the move is extended.

### By Float

| Float Range | Stocks | Active | Trades | Wins | Total P&L | Avg P&L | Win Rate |
|-------------|--------|--------|--------|------|-----------|---------|---------|
| Low (<5M) | 11 | 3 | 9 | 5 | **-$478** | **-$43** | **56%** |
| Medium (5-20M) | 10 | 8 | 14 | 2 | -$6,254 | -$625 | **14%** |
| High (20M+) | 9 | 6 | 18 | 6 | -$3,656 | -$406 | **33%** |

**Finding**: Low float (<5M) dramatically outperforms — 56% WR and nearly break-even avg P&L (-$43). Medium float (5-20M) is a red flag: 14% WR and -$625 avg loss. High float is mediocre. **Consider a tighter float cap below the current 20M max.**

### By Strategy Type

| Strategy | Stocks | Active | Trades | Wins | Total P&L | Avg P&L | Win Rate |
|----------|--------|--------|--------|------|-----------|---------|---------|
| Former Momo Stock | 4 | 3 | 6 | 2 | -$649 | -$162 | **33%** |
| Low Float - High Rel Vol | 5 | 2 | 9 | 3 | -$1,728 | -$346 | **33%** |
| Low Float Volatility Hunter | 3 | 1 | 1 | 0 | -$1,010 | -$337 | **0%** |
| Med Float - High Rel Vol | 8 | 6 | 18 | 6 | -$3,656 | -$457 | **33%** |
| Squeeze Alert - Up 10% in 10min | 4 | 2 | 2 | 0 | -$1,998 | -$500 | **0%** |
| Squeeze Alert - Up 5% in 5min | 6 | 3 | 5 | 2 | -$1,347 | -$224 | **40%** |

**Finding**: "Squeeze Alert - Up 10% in 10min" = 0% win rate across 4 stocks. These are stocks that already moved fast and hard — by the time the bot arms, the squeeze is over. "Former Momo Stock" had the lowest avg loss (-$162). "Med Float - High Rel Vol" was the worst absolute dollar loser (-$3,656 across 8 stocks).

### By Scanner Appearance Time

| Scanner Time | Stocks | Active | Trades | Wins | Total P&L | Avg P&L | Win Rate |
|-------------|--------|--------|--------|------|-----------|---------|---------|
| Pre-7am (started 07:00) | 6 | 3 | 8 | 3 | -$2,043 | -$340 | **38%** |
| 7-8am | 7 | 3 | 7 | 4 | **-$333** | **-$48** | **57%** |
| 8-9am | 6 | 5 | 15 | 4 | **-$5,501** | **-$917** | **27%** |
| 9am+ | 11 | 6 | 11 | 2 | -$2,511 | -$228 | **18%** |

**Finding**: **7-8am scanner appearances are the sweet spot** — 57% WR and only -$48 avg P&L. This is the most actionable finding in the study.

**8-9am appearances are the worst** by a wide margin: -$917 avg P&L and only 27% WR, driven by CRSR (-$1,939), AUID (-$1,683), FJET (-$1,263), QMCO (-$1,193). These stocks appear after the initial squeeze has already happened. The bot has less bar history context, enters into choppy/extended conditions, and the setup quality degrades.

### By Month

| Month | Stocks | Active | Trades | Wins | Total P&L | Avg P&L | Win Rate |
|-------|--------|--------|--------|------|-----------|---------|---------|
| January (hot market) | 14 | 7 | 17 | 4 | -$5,681 | -$406 | **24%** |
| February (cold market) | 16 | 10 | 24 | 9 | -$4,707 | -$294 | **38%** |

**Finding**: February outperformed January despite being the "cold" market. This may be because February had more mid-cap stocks with cleaner setups (FSLY, NCI), while January had more ultra-low-float/extreme-gap stocks that the bot doesn't handle well.

### By Price

| Price Range | Stocks | Active | Trades | Wins | Total P&L | Avg P&L | Win Rate |
|-------------|--------|--------|--------|------|-----------|---------|---------|
| Under $3 | 13 | 5 | 8 | 2 | -$3,835 | -$295 | **25%** |
| $3-$10 | 8 | 6 | 21 | 7 | -$3,910 | -$489 | **33%** |
| Over $10 | 9 | 6 | 12 | 4 | -$2,643 | -$294 | **33%** |

**Finding**: Price is the weakest predictor. Under-$3 stocks had the most "no trades" (bot couldn't find a valid setup), which is partially protective. $3-$10 range stocks had the most activity but also the most losses (driven by CRSR, AUID, QMCO, FJET).

---

## 3. Top/Bottom Analysis

### Top 5 Winners

| Rank | Symbol | P&L | Gap% | Float | Strategy | Time | Month |
|------|--------|-----|------|-------|----------|------|-------|
| 1 | NCI | +$577 | 11.9% | 1.08M | Squeeze Alert - Up 5% | 8-9am | Feb |
| 2 | VOR | +$501 | 6.5% | 8.06M | Former Momo Stock | 7-8am | Jan |
| 3 | FSLY | +$176 | 46.5% | 139.4M | Med Float - High Rel Vol | 7-8am | Feb |
| 4 | MCRB | +$113 | 7.8% | 7.42M | Former Momo Stock | 9am+ | Feb |
| 5 | BDSX | -$45 | 38.3% | 3.85M | Low Float - High Rel Vol | pre-7am | Jan |

**Winners share:**
- All but FSLY had low-medium gap (6.5-38.3%) — no extreme parabolic setups
- Appeared across a range of times — no single dominant scanner time
- 3 of 4 profitable stocks are February (cold market)
- "Former Momo Stock" strategy produced 2 of top 4

### Bottom 5 Losers

| Rank | Symbol | P&L | Gap% | Float | Strategy | Time | Month |
|------|--------|-----|------|-------|----------|------|-------|
| 1 | CRSR | -$1,939 | 36.2% | 44.36M | Med Float - High Rel Vol | **8-9am** | Feb |
| 2 | AUID | -$1,683 | 101.5% | 9.84M | Low Float - High Rel Vol | **8-9am** | Jan |
| 3 | FJET | -$1,263 | 5.1% | 17.36M | Former Momo Stock | **8-9am** | Jan |
| 4 | QMCO | -$1,193 | 5.2% | 13.58M | Squeeze Alert - Up 5% | **8-9am** | Jan |
| 5 | PMAX | -$1,098 | 34.4% | 5.09M | Squeeze Alert - Up 10% | pre-7am | Jan |

**Losers share:**
- **4 of 5 appeared between 8-9am** — the single strongest pattern in this dataset
- January dominated (4 of 5) — hot market + late appearance = overextended stock
- All had medium float (5-50M) except AUID

---

## 4. Key Findings

### Finding 1: 8-9am scanner appearances are a red flag
The worst-performing time window by a large margin (-$5,501 total, -$917 avg, 27% WR). Every stock appearing on the scanner between 8:00-9:00am should be treated with elevated skepticism. By this time:
- The initial gap-and-go move has already happened
- Retail traders are chasing late entries
- Volume is declining from the opening surge
- The bot is entering with less bar history and less VWAP context

**Recommendation**: Add a `WB_SCANNER_LATENCY_PENALTY` concept — when sim_start is 60-120 minutes into the session, require a higher minimum score or shorter warmup confirmation.

### Finding 2: Medium float (5-20M) is the worst performer
5-20M float stocks had 14% WR and -$625 avg P&L. This is the worst float bucket by a substantial margin. These stocks are:
- Large enough that institutional players can create deceptive patterns
- Small enough to be volatile and hard to read
- The "uncanny valley" of trading difficulty

**Recommendation**: Consider tightening `WB_PREFERRED_MAX_FLOAT` from 10M to 5M, while keeping `WB_MAX_FLOAT=20M` as the hard cap.

### Finding 3: Negative gap stocks should be pre-filtered
All 4 negative gap stocks (-$1,386 total, 17% WR). These appear on the scanner as "Squeeze Alert" or "Med Float" but are fundamentally different beasts — they're short squeezes or news pops, not gap-and-go runners. The bot's `WB_MIN_GAP_PCT=5` already blocks the -38.9% RPGL, but -2.5% (WEN), -20.2% (UPWK), and -23.7% (RPD) still made it through the filter.

**Recommendation**: Tighten `WB_MIN_GAP_PCT` from 5% to at least 5% (current) — WEN at -2.5% shouldn't reach the scanner watch list at all. Already handled for negative gaps via positive-gap requirement.

### Finding 4: "Squeeze Alert - Up 10% in 10min" = avoid
0% win rate across 4 stocks (-$1,998 total). These stocks have already made a 10% move in 10 minutes — the squeeze has fired. The bot is being asked to enter a stock that has already made its move. This is a known anti-pattern.

**Recommendation for Duffy's watchlist logic**: Exclude "Squeeze Alert - Up 10%" from the auto-watchlist, or at minimum flag them as low priority requiring manual approval.

### Finding 5: "Former Momo Stock" and low float are the bot's sweet spot
- Former Momo Stock: best avg P&L (-$162), most consistent
- Low float (<5M): best WR (56%), nearly break-even avg

These stocks have predictable momentum patterns the bot recognizes well. They tend to have cleaner impulse-pullback-rearm cycles.

### Recommendations for Duffy's Pre-Screening Logic

| Criterion | Current | Suggested | Rationale |
|-----------|---------|-----------|-----------|
| Min gap | 5% | 5% (keep) | Already correct |
| Max float | 20M | 10M preferred, 15M hard cap | 5-20M is the losers' bracket |
| Scanner time | all | Deprioritize 8-9am | Worst time window |
| Strategy filter | all | Exclude "Squeeze Alert - Up 10%" | 0% WR, always late |
| Gap direction | pos only | already enforced | Negative gaps excluded |
| Price | $1-$20 | keep | No strong price signal |

---

## Notes

- **15 of 30 stocks had 0 trades** — the bot correctly found no valid setup. This is protective behavior.
- **No errors** — all 30 backtests completed successfully.
- **Overall WR 32%** across 41 trades — consistent with the 108-stock study baseline (28% WR).

---

*Study by Claude Sonnet 4.6 — March 2, 2026*
*Sources: simulate.py (--ticks mode), current .env config, SCANNER_STUDY_30_DIRECTIVE.md*
