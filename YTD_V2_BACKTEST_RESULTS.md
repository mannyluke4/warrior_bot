# YTD V2 Backtest Results: Top-5 Ranked + Trade Cap
## Generated 2026-03-19

Period: January 2 - March 12, 2026 (9 trading days)
Starting Equity: $30,000
Risk: 2.5% of equity (dynamic)
Max trades/day: 5 | Daily loss limit: $-1,500 | Max notional: $50,000
Scanner filter: PM vol >= 50,000 (no hard floor), gap 10-500%, float < 10M
Top 5 candidates per day by composite rank (70% volume + 20% gap + 10% float)

---

## Section 1: V1 vs V2 Comparison

| Metric | V1 Config A | V2 Config A | V2 Config B |
|--------|-------------|-------------|-------------|
| Total Trades | 184 (11 days) | 9 (9 days) | 9 (9 days) |
| Avg Trades/Day | 16.7 | 1.0 | 1.0 |
| Final Equity | $7,755 | $50,411 | $50,411 |
| Total P&L | -$22,245 | $+20,411 | $+20,411 |
| Total Return | -74.2% | +68.0% | +68.0% |

---

## Section 2: Summary - Config A vs Config B

| Metric | Config A (Gate=8) | Config B (No Gate) |
|--------|--------------------|--------------------|
| Final Equity | $50,411 | $50,411 |
| Total P&L | $+20,411 | $+20,411 |
| Total Return | +68.0% | +68.0% |
| Total Trades | 9 | 9 |
| Avg Trades/Day | 1.0 | 1.0 |
| Win Rate | 5/9 (56%) | 5/9 (56%) |
| Average Win | $+4,695 | $+4,695 |
| Average Loss | $-766 | $-766 |
| Profit Factor | 7.66 | 7.66 |
| Max Drawdown $ | $1,234 | $1,234 |
| Max Drawdown % | 2.4% | 2.4% |
| Largest Win | $+15,980 | $+15,980 |
| Largest Loss | $-1,234 | $-1,234 |

---

## Section 3: Monthly Breakdown

| Month | A P&L | A Trades | B P&L | B Trades |
|-------|-------|----------|-------|----------|
| Jan | $+20,387 | 6 | $+20,387 | 6 |
| Feb | $+0 | 0 | $+0 | 0 |
| Mar | $+24 | 3 | $+24 | 3 |

---

## Section 4: Daily Detail

| Date | Scanned | Passed | Top N | A Trades | A P&L | A Equity | B Trades | B P&L | B Equity |
|------|---------|--------|-------|----------|-------|----------|----------|-------|----------|
| 2026-01-02 | 2 | 2 | 2 | 1 | $-1,234 | $28,766 | 1 | $-1,234 | $28,766 |
| 2026-01-03 | 0 | 0 | 0 | 0 | $+0 | $28,766 no candidates (total=0, passed=0) | 0 | $+0 | $28,766 |
| 2026-01-05 | 1 | 1 | 1 | 0 | $+0 | $28,766 | 0 | $+0 | $28,766 |
| 2026-01-06 | 2 | 2 | 2 | 0 | $+0 | $28,766 | 0 | $+0 | $28,766 |
| 2026-01-08 | 2 | 2 | 2 | 3 | $+872 | $29,638 | 3 | $+872 | $29,638 |
| 2026-01-14 | 2 | 2 | 2 | 1 | $+4,769 | $34,407 | 1 | $+4,769 | $34,407 |
| 2026-01-16 | 6 | 6 | 5 | 1 | $+15,980 | $50,387 | 1 | $+15,980 | $50,387 |
| 2026-03-10 | 3 | 3 | 3 | 2 | $-1,111 | $49,276 | 2 | $-1,111 | $49,276 |
| 2026-03-18 | 2 | 2 | 2 | 1 | $+1,135 | $50,411 | 1 | $+1,135 | $50,411 |

---

## Section 5: Trade-Level Detail

### Config A (Gate=8)

| Date | Symbol | Score | Entry | Exit | Reason | P&L |
|------|--------|-------|-------|------|--------|-----|
| 2026-01-02 | FUTG | 8.5 | $16.58 | $16.07 | stop_hit | $-1,234 |
| 2026-01-08 | ACON | 17.5 | $8.21 | $7.95 | stop_hit | $-719 |
| 2026-01-08 | SXTC | 11.5 | $3.21 | $3.46 | bearish_engulfing_exit_full | $+998 |
| 2026-01-08 | SXTC | 10.0 | $3.56 | $3.78 | bearish_engulfing_exit_full | $+593 |
| 2026-01-14 | ROLR | 15.5 | $9.33 | $16.43 | bearish_engulfing_exit_full | $+4,769 |
| 2026-01-16 | VERO | 15.6 | $3.58 | $5.81 | bearish_engulfing_exit_full | $+15,980 |
| 2026-03-10 | INKT | 18.5 | $20.02 | $19.38 | bearish_engulfing_exit_full | $-440 |
| 2026-03-10 | VTAK | 10.0 | $2.34 | $2.26 | bearish_engulfing_exit_full | $-671 |
| 2026-03-18 | ARTL | 14.5 | $7.62 | $7.92 | topping_wicky_exit_full | $+1,135 |

### Config B (No Gate)

| Date | Symbol | Score | Entry | Exit | Reason | P&L |
|------|--------|-------|-------|------|--------|-----|
| 2026-01-02 | FUTG | 8.5 | $16.58 | $16.07 | stop_hit | $-1,234 |
| 2026-01-08 | ACON | 17.5 | $8.21 | $7.95 | stop_hit | $-719 |
| 2026-01-08 | SXTC | 11.5 | $3.21 | $3.46 | bearish_engulfing_exit_full | $+998 |
| 2026-01-08 | SXTC | 10.0 | $3.56 | $3.78 | bearish_engulfing_exit_full | $+593 |
| 2026-01-14 | ROLR | 15.5 | $9.33 | $16.43 | bearish_engulfing_exit_full | $+4,769 |
| 2026-01-16 | VERO | 15.6 | $3.58 | $5.81 | bearish_engulfing_exit_full | $+15,980 |
| 2026-03-10 | INKT | 18.5 | $20.02 | $19.38 | bearish_engulfing_exit_full | $-440 |
| 2026-03-10 | VTAK | 10.0 | $2.34 | $2.26 | bearish_engulfing_exit_full | $-671 |
| 2026-03-18 | ARTL | 14.5 | $7.62 | $7.92 | topping_wicky_exit_full | $+1,135 |

---

## Section 6: Score Gate Difference (Trades in B but not A)

No trades differ between A and B in the top-5 selected candidates.

---

## Section 7: Missed Opportunities (Hindsight)

### Known Winners - Did They Make the Top 5?

| Stock | Date | Scanner Status | Known P&L | In Top 5? |
|-------|------|----------------|-----------|-----------|
| BNAI | 2026-01-14 | PM vol 5,686 — below 50K filter | +$4,907 | NO |
| ROLR | 2026-01-14 | PM vol 10.6M — should be #1 | +$2,431 | YES (#1) |
| GWAV | 2026-01-16 | PM vol 1.5M — should make top 5 | +$6,735 (blocked by gate) | YES (#5) |
| VERO | 2026-01-16 | NOT IN SCANNER | +$8,360 | YES (#1) |

---

## Section 8: Daily Selection Log

**2026-01-02**: 2 scanned → 2 passed → FUTG(vol=78,316), SNSE(vol=279,226)
**2026-01-03**: 0 scanned → 0 passed filter → none selected
**2026-01-05**: 1 scanned → 1 passed → UUU(vol=142,844)
**2026-01-06**: 2 scanned → 2 passed → NOMA(vol=2,704,087), CYCN(vol=8,666,636)
**2026-01-08**: 2 scanned → 2 passed → ACON(vol=4,695,008), SXTC(vol=2,345,330)
**2026-01-14**: 2 scanned → 2 passed → ROLR(vol=10,669,416), CMND(vol=460,213)
**2026-01-16**: 6 scanned → 6 passed → VERO(vol=26,831,003), ACCL(vol=10,272,856), BIYA(vol=7,050,459), LCFY(vol=143,179), GWAV(vol=1,537,606)
**2026-03-10**: 3 scanned → 3 passed → INKT(vol=4,446,474), VTAK(vol=20,624,502), PIII(vol=76,664)
**2026-03-18**: 2 scanned → 2 passed → ARTL(vol=5,389,390), ZENA(vol=2,863,072)

---

## Section 9: Robustness Checks

### Config A
- P&L without top 3 winners: $-1,473
- Top 3 winners: $+21,884
- Longest consecutive losing streak (days): 1
- Win/loss count (excl breakeven): 5W / 4L

### Config B
- P&L without top 3 winners: $-1,473
- Top 3 winners: $+21,884
- Longest consecutive losing streak (days): 1
- Win/loss count (excl breakeven): 5W / 4L

---

*Generated from YTD V2 backtest | Top-5 ranked, 5 trade cap, daily loss limit | Tick mode, Alpaca feed, dynamic sizing | Branch: v6-dynamic-sizing*