# YTD Backtest Results: A/B Score Gate Test (Partial)
## Generated 2026-03-13

**Status**: Stopped after 11 trading days (Jan 2–15) — both configs went underwater.
**Root cause**: Scanner finds 80-200 candidates/day → bot takes 18-25 trades/day → overtrading.
**Live bot constraint**: Only watches 1 stock at a time, takes 2-5 trades/day max.

Period: January 2–15, 2026 (11 of 49 trading days)
Starting Equity: $30,000
Risk: 2.5% of equity (dynamic)

---

## Summary Comparison

| Metric | Config A (Gate=8) | Config B (No Gate) |
|--------|--------------------|--------------------|
| Final Equity | $7,755 | $3,450 |
| Total P&L | $-22,245 | $-26,550 |
| Total Return | -74.2% | -88.5% |
| Total Trades | 184 | 252 |
| Win Rate | 48/177 (27%) | 73/244 (30%) |
| Average Win | $+276 | $+275 |
| Average Loss | $-275 | $-273 |
| Profit Factor | 0.37 | 0.43 |
| Largest Win | $+1,498 | $+1,560 |
| Largest Loss | $-984 | $-1,532 |
| Trades/Day (avg) | 18 | 25 |

---

## Daily Detail

| Date | Candidates | A Trades | A Day P&L | A Equity | B Trades | B Day P&L | B Equity |
|------|------------|----------|-----------|----------|----------|-----------|----------|
| 2026-01-02 | 175 | 32 | $-6,497 | $23,503 | 45 | $-6,349 | $23,651 |
| 2026-01-03 | 0 | 0 | $+0 | $23,503 | 0 | $+0 | $23,651 |
| 2026-01-05 | 202 | 29 | $-5,674 | $17,829 | 43 | $-6,902 | $16,749 |
| 2026-01-06 | 112 | 14 | $-3,062 | $14,767 | 22 | $-5,331 | $11,418 |
| 2026-01-07 | 86 | 13 | $-2,081 | $12,686 | 15 | $-2,416 | $9,002 |
| 2026-01-08 | 91 | 16 | $-1,156 | $11,530 | 23 | $-294 | $8,708 |
| 2026-01-09 | 83 | 11 | $-1,187 | $10,343 | 14 | $-1,845 | $6,863 |
| 2026-01-12 | 99 | 18 | $-234 | $10,109 | 26 | $-485 | $6,378 |
| 2026-01-13 | 87 | 6 | $-929 | $9,180 | 10 | $-1,227 | $5,151 |
| 2026-01-14 | 107 | 20 | $-234 | $8,946 | 23 | $-420 | $4,731 |
| 2026-01-15 | 98 | 25 | $-1,191 | $7,755 | 31 | $-1,281 | $3,450 |

---

## Key Findings

### 1. Overtrading is the #1 Problem
- Scanner finds 80-200 gap-up candidates per day
- Bot detects micro-pullback setups on 15-45 of them
- In reality, the live bot watches ONE stock at a time and takes 2-5 trades/day
- The backtest simulates every candidate independently — unrealistic

### 2. Score Gate Helps But Can't Fix Overtrading
- Config A (gate=8) lost $22,245 vs Config B (no gate) lost $26,550
- Gate saves ~$4,300 by blocking low-score entries
- But even with the gate, 18 trades/day is ~4x too many

### 3. Win Rate and Edge Are Marginal at Scale
- ~27% win rate with avg win ≈ avg loss → negative expectancy
- The edge exists only on SELECTED setups (high score, confirmed runner)
- Spraying across 100+ candidates dilutes the edge

### 4. What Needs to Change for Realistic Simulation
- **One-at-a-time constraint**: Only enter a new trade after the current one exits
- **Daily trade limit**: Cap at 3-5 trades/day (matches Ross Cameron's pace)
- **Scanner ranking**: Sort candidates by score/gap/volume, sim only top N
- **PDT protection**: Stop trading if equity drops below $25,000

---

*Partial results from YTD A/B backtest — stopped early due to unrealistic trade volume.*
*Scanner results for all 49 dates (Jan 2 – Mar 12) are cached in scanner_results/.*
*Branch: v6-dynamic-sizing*