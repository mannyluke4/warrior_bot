# YTD V2 Backtest Results: Top-5 Ranked + Trade Cap
## Generated 2026-03-16

Period: January 2 - March 12, 2026 (49 trading days)
Starting Equity: $30,000
Risk: 2.5% of equity (dynamic)
Max trades/day: 5 | Daily loss limit: $-1,500 | Max notional: $50,000
Scanner filter: PM vol >= 0 (no hard floor), gap 5-500%, float < 20M
Top 5 candidates per day by composite rank (70% volume + 20% gap + 10% float)

---

## Section 1: V1 vs V2 Comparison

| Metric | V1 Config A | V2 Config A | V2 Config B |
|--------|-------------|-------------|-------------|
| Total Trades | 184 (11 days) | 79 (49 days) | 87 (49 days) |
| Avg Trades/Day | 16.7 | 1.6 | 1.8 |
| Final Equity | $7,755 | $16,925 | $16,581 |
| Total P&L | -$22,245 | $-13,075 | $-13,419 |
| Total Return | -74.2% | -43.6% | -44.7% |

---

## Section 2: Summary - Config A vs Config B

| Metric | Config A (Gate=8) | Config B (No Gate) |
|--------|--------------------|--------------------|
| Final Equity | $16,925 | $16,581 |
| Total P&L | $-13,075 | $-13,419 |
| Total Return | -43.6% | -44.7% |
| Total Trades | 79 | 87 |
| Avg Trades/Day | 1.6 | 1.8 |
| Win Rate | 17/78 (22%) | 21/86 (24%) |
| Average Win | $+286 | $+262 |
| Average Loss | $-294 | $-291 |
| Profit Factor | 0.27 | 0.29 |
| Max Drawdown $ | $13,107 | $13,451 |
| Max Drawdown % | 43.7% | 44.8% |
| Largest Win | $+752 | $+744 |
| Largest Loss | $-994 | $-973 |

---

## Section 3: Monthly Breakdown

| Month | A P&L | A Trades | B P&L | B Trades |
|-------|-------|----------|-------|----------|
| Jan | $-6,266 | 34 | $-6,515 | 38 |
| Feb | $-2,814 | 29 | $-3,293 | 31 |
| Mar | $-3,995 | 16 | $-3,611 | 18 |

---

## Section 4: Daily Detail

| Date | Scanned | Passed | Top N | A Trades | A P&L | A Equity | B Trades | B P&L | B Equity |
|------|---------|--------|-------|----------|-------|----------|----------|-------|----------|
| 2026-01-02 | 176 | 118 | 5 | 1 | $-787 | $29,213 | 1 | $-787 | $29,213 |
| 2026-01-03 | 0 | 0 | 0 | 0 | $+0 | $29,213 no candidates (total=0, passed=0) | 0 | $+0 | $29,213 |
| 2026-01-05 | 203 | 138 | 5 | 1 | $-365 | $28,848 | 1 | $-365 | $28,848 |
| 2026-01-06 | 114 | 91 | 5 | 1 | $-721 | $28,127 | 2 | $-833 | $28,015 |
| 2026-01-07 | 87 | 72 | 5 | 2 | $-896 | $27,231 | 2 | $-892 | $27,123 |
| 2026-01-08 | 95 | 81 | 5 | 3 | $-694 | $26,537 | 3 | $-692 | $26,431 |
| 2026-01-09 | 86 | 69 | 5 | 0 | $+0 | $26,537 | 1 | $-660 | $25,771 |
| 2026-01-12 | 103 | 84 | 5 | 2 | $+34 | $26,571 | 2 | $+32 | $25,803 |
| 2026-01-13 | 94 | 77 | 5 | 3 | $-1,417 | $25,154 | 4 | $-1,324 | $24,479 |
| 2026-01-14 | 108 | 79 | 5 | 3 | $+908 | $26,062 | 3 | $+883 | $25,362 |
| 2026-01-15 | 101 | 76 | 5 | 1 | $-158 | $25,904 | 1 | $-154 | $25,208 |
| 2026-01-16 | 101 | 73 | 5 | 1 | $-138 | $25,766 | 1 | $-134 | $25,074 |
| 2026-01-20 | 109 | 82 | 5 | 0 | $+0 | $25,766 | 0 | $+0 | $25,074 |
| 2026-01-21 | 127 | 96 | 5 | 3 | $+619 | $26,385 | 3 | $+602 | $25,676 |
| 2026-01-22 | 171 | 132 | 5 | 3 | $-1,754 | $24,631 | 4 | $-1,306 | $24,370 |
| 2026-01-23 | 101 | 85 | 5 | 1 | $-337 | $24,294 | 1 | $-333 | $24,037 |
| 2026-01-26 | 117 | 85 | 5 | 1 | $+752 | $25,046 | 1 | $+744 | $24,781 |
| 2026-01-27 | 105 | 85 | 5 | 2 | $-1,290 | $23,756 | 2 | $-1,276 | $23,505 |
| 2026-01-28 | 90 | 71 | 5 | 2 | $-662 | $23,094 | 2 | $-655 | $22,850 |
| 2026-01-29 | 89 | 70 | 5 | 4 | $+640 | $23,734 | 4 | $+635 | $23,485 |
| 2026-01-30 | 73 | 58 | 5 | 0 | $+0 | $23,734 | 0 | $+0 | $23,485 |
| 2026-02-02 | 137 | 105 | 5 | 0 | $+0 | $23,734 | 0 | $+0 | $23,485 |
| 2026-02-03 | 142 | 100 | 5 | 1 | $-298 | $23,436 | 2 | $-401 | $23,084 |
| 2026-02-04 | 90 | 70 | 5 | 0 | $+0 | $23,436 | 0 | $+0 | $23,084 |
| 2026-02-05 | 74 | 51 | 5 | 2 | $-404 | $23,032 | 2 | $-398 | $22,686 |
| 2026-02-06 | 361 | 199 | 5 | 3 | $-89 | $22,943 | 2 | $+37 | $22,723 |
| 2026-02-09 | 145 | 105 | 5 | 2 | $-320 | $22,623 | 2 | $-318 | $22,405 |
| 2026-02-10 | 111 | 74 | 5 | 3 | $-164 | $22,459 | 3 | $-164 | $22,241 |
| 2026-02-11 | 93 | 73 | 5 | 0 | $+0 | $22,459 | 0 | $+0 | $22,241 |
| 2026-02-12 | 81 | 66 | 5 | 2 | $-586 | $21,873 | 2 | $-581 | $21,660 |
| 2026-02-13 | 219 | 133 | 5 | 1 | $+83 | $21,956 | 1 | $+82 | $21,742 |
| 2026-02-17 | 95 | 71 | 5 | 3 | $-450 | $21,506 | 3 | $-447 | $21,295 |
| 2026-02-18 | 169 | 126 | 5 | 1 | $-544 | $20,962 | 1 | $-539 | $20,756 |
| 2026-02-19 | 90 | 77 | 5 | 4 | $-305 | $20,657 | 4 | $-303 | $20,453 |
| 2026-02-20 | 97 | 74 | 5 | 0 | $+0 | $20,657 | 1 | $-110 | $20,343 |
| 2026-02-23 | 93 | 71 | 5 | 1 | $-258 | $20,399 | 1 | $-254 | $20,089 |
| 2026-02-24 | 161 | 111 | 5 | 1 | $+141 | $20,540 | 1 | $+139 | $20,228 |
| 2026-02-25 | 234 | 135 | 5 | 2 | $+199 | $20,739 | 2 | $+195 | $20,423 |
| 2026-02-26 | 128 | 83 | 5 | 2 | $+16 | $20,755 | 2 | $+16 | $20,439 |
| 2026-02-27 | 67 | 48 | 5 | 1 | $+165 | $20,920 | 2 | $-247 | $20,192 |
| 2026-03-02 | 167 | 109 | 5 | 2 | $-818 | $20,102 | 2 | $-789 | $19,403 |
| 2026-03-03 | 93 | 69 | 5 | 1 | $-316 | $19,786 | 2 | $-193 | $19,210 |
| 2026-03-04 | 255 | 141 | 5 | 2 | $-621 | $19,165 | 3 | $-437 | $18,773 |
| 2026-03-05 | 128 | 88 | 5 | 3 | $-297 | $18,868 | 3 | $-290 | $18,483 |
| 2026-03-06 | 99 | 78 | 5 | 2 | $-146 | $18,722 | 2 | $-142 | $18,341 |
| 2026-03-09 | 115 | 88 | 5 | 3 | $-1,497 | $17,225 | 3 | $-1,465 | $16,876 |
| 2026-03-10 | 164 | 120 | 5 | 2 | $-332 | $16,893 | 2 | $-327 | $16,549 |
| 2026-03-11 | 120 | 91 | 5 | 0 | $+0 | $16,893 | 0 | $+0 | $16,549 |
| 2026-03-12 | 89 | 73 | 5 | 1 | $+32 | $16,925 | 1 | $+32 | $16,581 |

---

## Section 5: Trade-Level Detail

### Config A (Gate=8)

| Date | Symbol | Score | Entry | Exit | Reason | P&L |
|------|--------|-------|-------|------|--------|-----|
| 2026-01-02 | PAVS | 9.0 | $2.10 | $1.89 | stop_hit | $-787 |
| 2026-01-05 | RGTX | 10.5 | $14.81 | $14.70 | bearish_engulfing_exit_full | $-365 |
| 2026-01-06 | BNAI | 10.5 | $4.72 | $4.59 | stop_hit | $-721 |
| 2026-01-07 | NVVE | 12.0 | $3.69 | $3.47 | 5m_trend_guard_exit_exit_full | $-193 |
| 2026-01-07 | NVVE | 10.5 | $3.52 | $3.35 | stop_hit | $-703 |
| 2026-01-08 | ACON | 12.5 | $8.21 | $7.95 | stop_hit | $-680 |
| 2026-01-08 | SXTC | 12.5 | $2.78 | $2.75 | 5m_trend_guard_exit_exit_full | $-39 |
| 2026-01-08 | SXTC | 12.5 | $3.56 | $3.57 | bearish_engulfing_exit_full | $+25 |
| 2026-01-12 | BDSX | 12.5 | $8.47 | $8.66 | bearish_engulfing_exit_full | $+335 |
| 2026-01-12 | CRWG | 12.0 | $3.96 | $3.91 | bearish_engulfing_exit_full | $-301 |
| 2026-01-13 | XAIR | 10.0 | $1.31 | $1.27 | bearish_engulfing_exit_full | $-222 |
| 2026-01-13 | EVTV | 11.0 | $3.91 | $3.59 | stop_hit | $-664 |
| 2026-01-13 | AHMA | 10.5 | $8.77 | $8.25 | topping_wicky_exit_full | $-531 |
| 2026-01-14 | AHMA | 10.5 | $12.87 | $13.08 | topping_wicky_exit_full | $+227 |
| 2026-01-14 | AHMA | 9.8 | $14.02 | $15.13 | topping_wicky_exit_full | $+749 |
| 2026-01-14 | AHMA | 12.5 | $14.52 | $14.45 | bearish_engulfing_exit_full | $-68 |
| 2026-01-15 | SPHL | 10.5 | $10.27 | $10.08 | bearish_engulfing_exit_full | $-158 |
| 2026-01-16 | XAIR | 12.5 | $2.10 | $2.07 | topping_wicky_exit_full | $-138 |
| 2026-01-21 | GITS | 12.0 | $2.43 | $2.79 | topping_wicky_exit_full | $+463 |
| 2026-01-21 | SEGG | 10.5 | $2.22 | $2.29 | bearish_engulfing_exit_full | $+501 |
| 2026-01-21 | SEGG | 12.0 | $2.39 | $2.31 | bearish_engulfing_exit_full | $-345 |
| 2026-01-22 | IOTR | 11.0 | $8.62 | $8.14 | stop_hit | $-659 |
| 2026-01-22 | SXTP | 11.0 | $7.29 | $6.87 | stop_hit | $-659 |
| 2026-01-22 | NAMM | 12.5 | $2.25 | $2.17 | bearish_engulfing_exit_full | $-436 |
| 2026-01-23 | MOVE | 12.5 | $19.92 | $19.49 | bearish_engulfing_exit_full | $-337 |
| 2026-01-26 | MBAI | 12.5 | $2.24 | $2.82 | topping_wicky_exit_full | $+752 |
| 2026-01-27 | CYN | 12.0 | $3.67 | $3.43 | stop_hit | $-626 |
| 2026-01-27 | GDXD | 10.8 | $4.09 | $3.99 | stop_hit | $-664 |
| 2026-01-28 | SLGB | 9.5 | $3.44 | $3.04 | stop_hit | $-593 |
| 2026-01-28 | SLGB | 12.5 | $4.19 | $4.14 | bearish_engulfing_exit_full | $-69 |
| 2026-01-29 | FEED | 12.0 | $2.26 | $2.25 | topping_wicky_exit_full | $-45 |
| 2026-01-29 | FEED | 12.0 | $3.44 | $3.87 | topping_wicky_exit_full | $+620 |
| 2026-01-29 | FEED | 11.0 | $4.11 | $4.10 | bearish_engulfing_exit_full | $-17 |
| 2026-01-29 | FEED | 12.5 | $4.45 | $4.47 | bearish_engulfing_exit_full | $+82 |
| 2026-02-03 | NPT | 9.5 | $8.52 | $6.10 | stop_hit | $-298 |
| 2026-02-05 | RKLZ | 10.0 | $3.93 | $3.88 | topping_wicky_exit_full | $-165 |
| 2026-02-05 | RKLZ | 9.0 | $4.09 | $3.99 | topping_wicky_exit_full | $-239 |
| 2026-02-06 | WHLR | 9.5 | $3.12 | $3.18 | topping_wicky_exit_full | $+40 |
| 2026-02-06 | SMX | 10.5 | $15.92 | $15.90 | topping_wicky_exit_full | $-3 |
| 2026-02-06 | SMX | 12.5 | $17.30 | $16.38 | bearish_engulfing_exit_full | $-126 |
| 2026-02-09 | CRWG | 11.5 | $3.96 | $3.95 | bearish_engulfing_exit_full | $-34 |
| 2026-02-09 | CRWG | 12.5 | $4.24 | $4.13 | stop_hit | $-286 |
| 2026-02-10 | JZXN | 8.0 | $2.32 | $2.22 | topping_wicky_exit_full | $-90 |
| 2026-02-10 | JZXN | 11.0 | $2.36 | $2.48 | bearish_engulfing_exit_full | $+208 |
| 2026-02-10 | ASTI | 9.5 | $8.16 | $7.89 | stop_hit | $-282 |
| 2026-02-12 | JZXN | 12.5 | $2.08 | $1.96 | stop_hit | $-280 |
| 2026-02-12 | KPTI | 12.5 | $8.07 | $7.86 | stop_hit | $-306 |
| 2026-02-13 | APPX | 11.0 | $9.03 | $9.10 | topping_wicky_exit_full | $+83 |
| 2026-02-17 | PLYX | 10.5 | $4.89 | $4.74 | bearish_engulfing_exit_full | $-85 |
| 2026-02-17 | RIME | 12.5 | $5.02 | $4.86 | bearish_engulfing_exit_full | $-146 |
| 2026-02-17 | RIME | 8.5 | $4.82 | $4.70 | topping_wicky_exit_full | $-219 |
| 2026-02-18 | LRHC | 12.5 | $2.29 | $1.89 | max_loss_hit | $-544 |
| 2026-02-19 | RUBI | 11.0 | $3.15 | $3.10 | topping_wicky_exit_full | $-62 |
| 2026-02-19 | RIME | 12.5 | $3.17 | $3.13 | bearish_engulfing_exit_full | $-87 |
| 2026-02-19 | NAMM | 12.0 | $2.96 | $2.95 | bearish_engulfing_exit_full | $-15 |
| 2026-02-19 | NAMM | 12.0 | $3.11 | $3.06 | bearish_engulfing_exit_full | $-141 |
| 2026-02-23 | GNPX | 10.5 | $2.22 | $2.09 | stop_hit | $-258 |
| 2026-02-24 | CRWG | 12.0 | $4.13 | $4.18 | topping_wicky_exit_full | $+141 |
| 2026-02-25 | IONX | 12.0 | $10.46 | $10.38 | bearish_engulfing_exit_full | $-143 |
| 2026-02-25 | CDIO | 12.0 | $3.65 | $3.85 | topping_wicky_exit_full | $+342 |
| 2026-02-26 | IONX | 12.5 | $14.39 | $14.58 | bearish_engulfing_exit_full | $+105 |
| 2026-02-26 | IONX | 12.5 | $14.91 | $14.78 | bearish_engulfing_exit_full | $-89 |
| 2026-02-27 | SMJF | 12.0 | $2.32 | $2.40 | bearish_engulfing_exit_full | $+165 |
| 2026-03-02 | BATL | 12.5 | $12.04 | $11.44 | stop_hit | $-523 |
| 2026-03-02 | INDO | 12.5 | $9.02 | $8.76 | bearish_engulfing_exit_full | $-295 |
| 2026-03-03 | NPT | 12.5 | $7.69 | $7.18 | bearish_engulfing_exit_full | $-316 |
| 2026-03-04 | VCIG | 9.5 | $15.80 | $15.16 | topping_wicky_exit_full | $-127 |
| 2026-03-04 | RGTX | 9.0 | $6.13 | $6.04 | stop_hit | $-494 |
| 2026-03-05 | BATL | 12.0 | $17.35 | $17.35 | topping_wicky_exit_full | $+0 |
| 2026-03-05 | BATL | 12.5 | $19.77 | $19.57 | topping_wicky_exit_full | $-77 |
| 2026-03-05 | BATL | 10.5 | $22.58 | $22.31 | bearish_engulfing_exit_full | $-220 |
| 2026-03-06 | TPET | 8.8 | $2.16 | $2.14 | bearish_engulfing_exit_full | $-118 |
| 2026-03-06 | AIFF | 12.5 | $2.11 | $2.10 | topping_wicky_exit_full | $-28 |
| 2026-03-09 | HIMZ | 12.0 | $2.36 | $2.26 | bearish_engulfing_exit_full | $-316 |
| 2026-03-09 | HIMZ | 12.0 | $2.37 | $2.33 | bearish_engulfing_exit_full | $-187 |
| 2026-03-09 | CRCG | 10.5 | $3.55 | $3.25 | max_loss_hit | $-994 |
| 2026-03-10 | INKT | 12.5 | $20.02 | $18.80 | bearish_engulfing_exit_full | $-285 |
| 2026-03-10 | CRCG | 9.5 | $4.57 | $4.56 | topping_wicky_exit_full | $-47 |
| 2026-03-12 | TLYS | 12.0 | $2.72 | $2.73 | topping_wicky_exit_full | $+32 |

### Config B (No Gate)

| Date | Symbol | Score | Entry | Exit | Reason | P&L |
|------|--------|-------|-------|------|--------|-----|
| 2026-01-02 | PAVS | 9.0 | $2.10 | $1.89 | stop_hit | $-787 |
| 2026-01-05 | RGTX | 10.5 | $14.81 | $14.70 | bearish_engulfing_exit_full | $-365 |
| 2026-01-06 | ELAB | 5.5 | $11.75 | $11.40 | bearish_engulfing_exit_full | $-112 |
| 2026-01-06 | BNAI | 10.5 | $4.72 | $4.59 | stop_hit | $-721 |
| 2026-01-07 | NVVE | 12.0 | $3.69 | $3.47 | 5m_trend_guard_exit_exit_full | $-192 |
| 2026-01-07 | NVVE | 10.5 | $3.52 | $3.35 | stop_hit | $-700 |
| 2026-01-08 | ACON | 12.5 | $8.21 | $7.95 | stop_hit | $-678 |
| 2026-01-08 | SXTC | 12.5 | $2.78 | $2.75 | 5m_trend_guard_exit_exit_full | $-39 |
| 2026-01-08 | SXTC | 12.5 | $3.56 | $3.57 | bearish_engulfing_exit_full | $+25 |
| 2026-01-09 | APVO | 5.5 | $9.44 | $9.19 | stop_hit | $-660 |
| 2026-01-12 | BDSX | 12.5 | $8.47 | $8.66 | bearish_engulfing_exit_full | $+325 |
| 2026-01-12 | CRWG | 12.0 | $3.96 | $3.91 | bearish_engulfing_exit_full | $-293 |
| 2026-01-13 | XAIR | 10.0 | $1.31 | $1.27 | bearish_engulfing_exit_full | $-216 |
| 2026-01-13 | EVTV | 11.0 | $3.91 | $3.59 | stop_hit | $-645 |
| 2026-01-13 | AHMA | 7.5 | $7.12 | $7.16 | bearish_engulfing_exit_full | $+53 |
| 2026-01-13 | AHMA | 10.5 | $8.77 | $8.25 | topping_wicky_exit_full | $-516 |
| 2026-01-14 | AHMA | 10.5 | $12.87 | $13.08 | topping_wicky_exit_full | $+221 |
| 2026-01-14 | AHMA | 9.8 | $14.02 | $15.13 | topping_wicky_exit_full | $+728 |
| 2026-01-14 | AHMA | 12.5 | $14.52 | $14.45 | bearish_engulfing_exit_full | $-66 |
| 2026-01-15 | SPHL | 10.5 | $10.27 | $10.08 | bearish_engulfing_exit_full | $-154 |
| 2026-01-16 | XAIR | 12.5 | $2.10 | $2.07 | topping_wicky_exit_full | $-134 |
| 2026-01-21 | GITS | 12.0 | $2.43 | $2.79 | topping_wicky_exit_full | $+450 |
| 2026-01-21 | SEGG | 10.5 | $2.22 | $2.29 | bearish_engulfing_exit_full | $+487 |
| 2026-01-21 | SEGG | 12.0 | $2.39 | $2.31 | bearish_engulfing_exit_full | $-335 |
| 2026-01-22 | IOTR | 11.0 | $8.62 | $8.14 | stop_hit | $-641 |
| 2026-01-22 | NXTS | 4.0 | $2.86 | $3.01 | bearish_engulfing_exit_full | $+400 |
| 2026-01-22 | SXTP | 11.0 | $7.29 | $6.87 | stop_hit | $-641 |
| 2026-01-22 | NAMM | 12.5 | $2.25 | $2.17 | bearish_engulfing_exit_full | $-424 |
| 2026-01-23 | MOVE | 12.5 | $19.92 | $19.49 | bearish_engulfing_exit_full | $-333 |
| 2026-01-26 | MBAI | 12.5 | $2.24 | $2.82 | topping_wicky_exit_full | $+744 |
| 2026-01-27 | CYN | 12.0 | $3.67 | $3.43 | stop_hit | $-619 |
| 2026-01-27 | GDXD | 10.8 | $4.09 | $3.99 | stop_hit | $-657 |
| 2026-01-28 | SLGB | 9.5 | $3.44 | $3.04 | stop_hit | $-587 |
| 2026-01-28 | SLGB | 12.5 | $4.19 | $4.14 | bearish_engulfing_exit_full | $-68 |
| 2026-01-29 | FEED | 12.0 | $2.26 | $2.25 | topping_wicky_exit_full | $-44 |
| 2026-01-29 | FEED | 12.0 | $3.44 | $3.87 | topping_wicky_exit_full | $+614 |
| 2026-01-29 | FEED | 11.0 | $4.11 | $4.10 | bearish_engulfing_exit_full | $-17 |
| 2026-01-29 | FEED | 12.5 | $4.45 | $4.47 | bearish_engulfing_exit_full | $+82 |
| 2026-02-03 | NPT | 9.5 | $8.52 | $6.10 | stop_hit | $-293 |
| 2026-02-03 | CYN | 5.5 | $2.15 | $2.10 | bearish_engulfing_exit_full | $-108 |
| 2026-02-05 | RKLZ | 10.0 | $3.93 | $3.88 | topping_wicky_exit_full | $-162 |
| 2026-02-05 | RKLZ | 9.0 | $4.09 | $3.99 | topping_wicky_exit_full | $-236 |
| 2026-02-06 | WHLR | 9.5 | $3.12 | $3.18 | topping_wicky_exit_full | $+40 |
| 2026-02-06 | SMX | 10.5 | $15.92 | $15.90 | topping_wicky_exit_full | $-3 |
| 2026-02-09 | CRWG | 11.5 | $3.96 | $3.95 | bearish_engulfing_exit_full | $-34 |
| 2026-02-09 | CRWG | 12.5 | $4.24 | $4.13 | stop_hit | $-284 |
| 2026-02-10 | JZXN | 8.0 | $2.32 | $2.22 | topping_wicky_exit_full | $-90 |
| 2026-02-10 | JZXN | 11.0 | $2.36 | $2.48 | bearish_engulfing_exit_full | $+206 |
| 2026-02-10 | ASTI | 9.5 | $8.16 | $7.89 | stop_hit | $-280 |
| 2026-02-12 | JZXN | 12.5 | $2.08 | $1.96 | stop_hit | $-278 |
| 2026-02-12 | KPTI | 12.5 | $8.07 | $7.86 | stop_hit | $-303 |
| 2026-02-13 | APPX | 11.0 | $9.03 | $9.10 | topping_wicky_exit_full | $+82 |
| 2026-02-17 | PLYX | 10.5 | $4.89 | $4.74 | bearish_engulfing_exit_full | $-85 |
| 2026-02-17 | RIME | 12.5 | $5.02 | $4.86 | bearish_engulfing_exit_full | $-145 |
| 2026-02-17 | RIME | 8.5 | $4.82 | $4.70 | topping_wicky_exit_full | $-217 |
| 2026-02-18 | LRHC | 12.5 | $2.29 | $1.89 | max_loss_hit | $-539 |
| 2026-02-19 | RUBI | 11.0 | $3.15 | $3.10 | topping_wicky_exit_full | $-62 |
| 2026-02-19 | RIME | 12.5 | $3.17 | $3.13 | bearish_engulfing_exit_full | $-86 |
| 2026-02-19 | NAMM | 12.0 | $2.96 | $2.95 | bearish_engulfing_exit_full | $-15 |
| 2026-02-19 | NAMM | 12.0 | $3.11 | $3.06 | bearish_engulfing_exit_full | $-140 |
| 2026-02-20 | EVTV | 6.0 | $2.00 | $1.94 | bearish_engulfing_exit_full | $-110 |
| 2026-02-23 | GNPX | 10.5 | $2.22 | $2.09 | stop_hit | $-254 |
| 2026-02-24 | CRWG | 12.0 | $4.13 | $4.18 | topping_wicky_exit_full | $+139 |
| 2026-02-25 | IONX | 12.0 | $10.46 | $10.38 | bearish_engulfing_exit_full | $-141 |
| 2026-02-25 | CDIO | 12.0 | $3.65 | $3.85 | topping_wicky_exit_full | $+336 |
| 2026-02-26 | IONX | 12.5 | $14.39 | $14.58 | bearish_engulfing_exit_full | $+103 |
| 2026-02-26 | IONX | 12.5 | $14.91 | $14.78 | bearish_engulfing_exit_full | $-87 |
| 2026-02-27 | SMJF | 5.5 | $2.11 | $1.94 | stop_hit | $-409 |
| 2026-02-27 | SMJF | 12.0 | $2.32 | $2.40 | bearish_engulfing_exit_full | $+162 |
| 2026-03-02 | BATL | 12.5 | $12.04 | $11.44 | stop_hit | $-504 |
| 2026-03-02 | INDO | 12.5 | $9.02 | $8.76 | bearish_engulfing_exit_full | $-285 |
| 2026-03-03 | NPT | 4.0 | $5.87 | $5.90 | topping_wicky_exit_full | $+112 |
| 2026-03-03 | NPT | 12.5 | $7.69 | $7.18 | bearish_engulfing_exit_full | $-305 |
| 2026-03-04 | VCIG | 5.5 | $11.02 | $11.60 | bearish_engulfing_exit_full | $+166 |
| 2026-03-04 | VCIG | 9.5 | $15.80 | $15.16 | topping_wicky_exit_full | $-123 |
| 2026-03-04 | RGTX | 9.0 | $6.13 | $6.04 | stop_hit | $-480 |
| 2026-03-05 | BATL | 12.0 | $17.35 | $17.35 | topping_wicky_exit_full | $+0 |
| 2026-03-05 | BATL | 12.5 | $19.77 | $19.57 | topping_wicky_exit_full | $-75 |
| 2026-03-05 | BATL | 10.5 | $22.58 | $22.31 | bearish_engulfing_exit_full | $-215 |
| 2026-03-06 | TPET | 8.8 | $2.16 | $2.14 | bearish_engulfing_exit_full | $-115 |
| 2026-03-06 | AIFF | 12.5 | $2.11 | $2.10 | topping_wicky_exit_full | $-27 |
| 2026-03-09 | HIMZ | 12.0 | $2.36 | $2.26 | bearish_engulfing_exit_full | $-309 |
| 2026-03-09 | HIMZ | 12.0 | $2.37 | $2.33 | bearish_engulfing_exit_full | $-183 |
| 2026-03-09 | CRCG | 10.5 | $3.55 | $3.25 | max_loss_hit | $-973 |
| 2026-03-10 | INKT | 12.5 | $20.02 | $18.80 | bearish_engulfing_exit_full | $-281 |
| 2026-03-10 | CRCG | 9.5 | $4.57 | $4.56 | topping_wicky_exit_full | $-46 |
| 2026-03-12 | TLYS | 12.0 | $2.72 | $2.73 | topping_wicky_exit_full | $+32 |

---

## Section 6: Score Gate Difference (Trades in B but not A)

| Date | Symbol | Score | Entry | Exit | Reason | P&L (in B) |
|------|--------|-------|-------|------|--------|------------|
| 2026-01-06 | ELAB | 5.5 | $11.75 | $11.40 | bearish_engulfing_exit_full | $-112 |
| 2026-01-09 | APVO | 5.5 | $9.44 | $9.19 | stop_hit | $-660 |
| 2026-01-13 | AHMA | 10.5 | $8.77 | $8.25 | topping_wicky_exit_full | $-516 |
| 2026-01-22 | NXTS | 4.0 | $2.86 | $3.01 | bearish_engulfing_exit_full | $+400 |
| 2026-02-03 | CYN | 5.5 | $2.15 | $2.10 | bearish_engulfing_exit_full | $-108 |
| 2026-02-20 | EVTV | 6.0 | $2.00 | $1.94 | bearish_engulfing_exit_full | $-110 |
| 2026-02-27 | SMJF | 12.0 | $2.32 | $2.40 | bearish_engulfing_exit_full | $+162 |
| 2026-03-03 | NPT | 12.5 | $7.69 | $7.18 | bearish_engulfing_exit_full | $-305 |
| 2026-03-04 | VCIG | 5.5 | $11.02 | $11.60 | bearish_engulfing_exit_full | $+166 |
| 2026-03-04 | VCIG | 9.5 | $15.80 | $15.16 | topping_wicky_exit_full | $-123 |

**Total P&L of blocked trades**: $-1,206
**Score gate net impact**: $+1,206 (positive = gate helped)

---

## Section 7: Missed Opportunities (Hindsight)

### Known Winners - Did They Make the Top 5?

| Stock | Date | Scanner Status | Known P&L | In Top 5? |
|-------|------|----------------|-----------|-----------|
| BNAI | 2026-01-14 | PM vol 5,686 — below 50K filter | +$4,907 | NO |
| ROLR | 2026-01-14 | PM vol 10.6M — should be #1 | +$2,431 | YES (#1) |
| GWAV | 2026-01-16 | PM vol 1.5M — should make top 5 | +$6,735 (blocked by gate) | NO |
| VERO | 2026-01-16 | NOT IN SCANNER | +$8,360 | YES (#1) |

---

## Section 8: Daily Selection Log

**2026-01-02**: 176 scanned → 118 passed → PAVS(vol=1,069,778), SMX(vol=676,738), SOLT(vol=421,526), CRWG(vol=310,693), ANGH(vol=255,873)
**2026-01-03**: 0 scanned → 0 passed filter → none selected
**2026-01-05**: 203 scanned → 138 passed → CRWG(vol=932,961), RGTX(vol=821,243), SOLT(vol=377,020), CRCG(vol=233,997), BMNG(vol=211,990)
**2026-01-06**: 114 scanned → 91 passed → CYCN(vol=8,666,636), ELAB(vol=1,758,309), NOMA(vol=2,704,087), BNAI(vol=2,214,351), SOPA(vol=2,133,477)
**2026-01-07**: 87 scanned → 72 passed → NVVE(vol=15,642,799), CDIO(vol=6,536,915), MNTS(vol=1,226,841), RKLZ(vol=380,299), GNPX(vol=376,825)
**2026-01-08**: 95 scanned → 81 passed → ACON(vol=4,695,008), SXTC(vol=2,345,330), QBTZ(vol=1,380,187), WOK(vol=1,239,718), ELAB(vol=1,093,179)
**2026-01-09**: 86 scanned → 69 passed → APVO(vol=3,993,762), ICON(vol=3,622,622), KUST(vol=2,700,325), CETX(vol=2,092,132), WHLR(vol=705,328)
**2026-01-12**: 103 scanned → 84 passed → BDSX(vol=5,401,463), CRWG(vol=5,562,025), NCEL(vol=571,640), INDO(vol=460,787), SOLT(vol=281,263)
**2026-01-13**: 94 scanned → 77 passed → XAIR(vol=71,249,379), ATON(vol=15,497,753), EVTV(vol=20,644,267), AHMA(vol=10,117,699), SPRC(vol=11,816,128)
**2026-01-14**: 108 scanned → 79 passed → ROLR(vol=10,669,416), CRWG(vol=1,035,853), AHMA(vol=719,372), QBTZ(vol=782,256), CMND(vol=460,213)
**2026-01-15**: 101 scanned → 76 passed → CJMB(vol=16,555,670), SPHL(vol=5,016,154), EVTV(vol=7,819,294), CGTL(vol=1,639,092), CEPT(vol=1,496,203)
**2026-01-16**: 101 scanned → 73 passed → VERO(vol=26,831,003), ACCL(vol=10,272,856), BIYA(vol=7,050,459), TNMG(vol=5,424,692), XAIR(vol=2,416,808)
**2026-01-20**: 109 scanned → 82 passed → IVF(vol=43,686,384), BTTC(vol=29,798,487), TWG(vol=9,478,348), ICON(vol=12,463,348), SDST(vol=7,850,312)
**2026-01-21**: 127 scanned → 96 passed → GITS(vol=25,657,515), SLGB(vol=15,293,392), BOXL(vol=13,705,568), BNAI(vol=11,526,265), SEGG(vol=2,861,700)
**2026-01-22**: 171 scanned → 132 passed → IOTR(vol=22,198,275), NXTS(vol=21,390,097), SXTP(vol=13,877,243), RAYA(vol=7,955,230), NAMM(vol=6,699,518)
**2026-01-23**: 101 scanned → 85 passed → DRCT(vol=30,258,671), MOVE(vol=7,698,221), RVYL(vol=5,400,826), SOPA(vol=6,631,154), RAYA(vol=3,987,249)
**2026-01-26**: 117 scanned → 85 passed → BATL(vol=69,454,863), EVTV(vol=14,135,691), ARAI(vol=6,451,557), MBAI(vol=3,302,918), OCG(vol=2,236,615)
**2026-01-27**: 105 scanned → 85 passed → NUWE(vol=44,961,800), XHLD(vol=7,858,738), PHGE(vol=3,841,638), CYN(vol=4,255,770), GDXD(vol=2,604,622)
**2026-01-28**: 90 scanned → 71 passed → MRNO(vol=24,078,277), AIMD(vol=14,577,647), SLGB(vol=10,150,532), GRI(vol=6,728,516), KUST(vol=4,000,884)
**2026-01-29**: 89 scanned → 70 passed → FEED(vol=40,631,634), SER(vol=26,039,627), GLL(vol=16,059,468), GCTK(vol=10,534,265), GDXD(vol=5,789,596)
**2026-01-30**: 73 scanned → 58 passed → VIVS(vol=10,777,851), CISS(vol=6,082,995), LRHC(vol=4,088,644), RKLZ(vol=4,103,680), GLL(vol=3,345,144)
**2026-02-02**: 137 scanned → 105 passed → CISS(vol=19,182,335), RKLZ(vol=3,926,393), SWVL(vol=3,874,975), IPW(vol=3,241,138), DOGZ(vol=1,320,433)
**2026-02-03**: 142 scanned → 100 passed → FATN(vol=19,689,792), NPT(vol=3,557,700), CYN(vol=4,151,101), FIEE(vol=808,084), PLTG(vol=385,780)
**2026-02-04**: 90 scanned → 70 passed → ELPW(vol=31,138,608), BOXL(vol=23,869,470), CIGL(vol=5,720,243), EVTV(vol=6,821,397), RKLZ(vol=3,008,315)
**2026-02-05**: 74 scanned → 51 passed → CISS(vol=8,570,203), RNAZ(vol=2,728,563), RKLZ(vol=2,129,496), GDXD(vol=503,686), HIMZ(vol=427,171)
**2026-02-06**: 361 scanned → 199 passed → BATL(vol=12,746,104), WHLR(vol=4,175,931), SMX(vol=1,414,662), IONX(vol=1,132,995), RGTX(vol=966,072)
**2026-02-09**: 145 scanned → 105 passed → UOKA(vol=22,276,513), CRWG(vol=3,763,051), OKLL(vol=830,933), ELTK(vol=423,304), MNTS(vol=319,338)
**2026-02-10**: 111 scanned → 74 passed → JZXN(vol=2,422,672), VELO(vol=1,242,742), ASTI(vol=720,079), RKLZ(vol=339,970), IPW(vol=236,363)
**2026-02-11**: 93 scanned → 73 passed → BNRG(vol=7,093,915), ELAB(vol=3,242,923), RKLZ(vol=2,355,742), SUNE(vol=1,643,462), PRFX(vol=392,846)
**2026-02-12**: 81 scanned → 66 passed → JZXN(vol=1,020,130), FEED(vol=432,931), QBTZ(vol=395,601), KPTI(vol=298,762), SOLT(vol=215,808)
**2026-02-13**: 219 scanned → 133 passed → JDZG(vol=8,588,420), CRWG(vol=2,171,917), APPX(vol=1,340,612), SUNE(vol=1,009,640), OKLL(vol=549,750)
**2026-02-17**: 95 scanned → 71 passed → OBAI(vol=9,878,007), PLYX(vol=5,456,965), RIME(vol=6,504,001), AMDD(vol=1,509,549), CGTL(vol=284,874)
**2026-02-18**: 169 scanned → 126 passed → LRHC(vol=8,844,996), BENF(vol=5,824,265), RIME(vol=5,697,100), CRWG(vol=1,877,603), OBAI(vol=1,267,373)
**2026-02-19**: 90 scanned → 77 passed → CISS(vol=9,560,675), RUBI(vol=8,486,662), RIME(vol=2,236,956), NAMM(vol=563,997), CDIO(vol=374,626)
**2026-02-20**: 97 scanned → 74 passed → BJDX(vol=2,812,762), EVTV(vol=2,011,738), FIGG(vol=2,032,943), ANPA(vol=1,545,342), NAMM(vol=738,183)
**2026-02-23**: 93 scanned → 71 passed → GNPX(vol=1,627,057), PBM(vol=1,129,050), BATL(vol=1,017,865), RKLZ(vol=416,947), AIDX(vol=296,568)
**2026-02-24**: 161 scanned → 111 passed → RIME(vol=6,865,920), CRWG(vol=3,229,581), CDIO(vol=1,717,325), FIGG(vol=1,734,584), RGTX(vol=970,974)
**2026-02-25**: 234 scanned → 135 passed → IONX(vol=1,305,731), CDIO(vol=1,260,466), RGTX(vol=1,189,974), APPX(vol=815,625), OKLL(vol=710,471)
**2026-02-26**: 128 scanned → 83 passed → CRCG(vol=14,168,245), HCTI(vol=3,215,960), SMJF(vol=2,871,906), CRMG(vol=1,415,271), IONX(vol=1,181,194)
**2026-02-27**: 67 scanned → 48 passed → CDIO(vol=1,293,670), RKLZ(vol=295,975), SMJF(vol=279,199), MRAL(vol=162,917), SOUX(vol=155,633)
**2026-03-02**: 167 scanned → 109 passed → TMDE(vol=47,462,115), BATL(vol=11,513,703), CRCG(vol=10,924,670), RBNE(vol=4,938,148), INDO(vol=3,027,663)
**2026-03-03**: 93 scanned → 69 passed → TMDE(vol=12,365,521), NPT(vol=3,862,933), GLL(vol=1,434,319), RBNE(vol=1,220,317), CISS(vol=941,164)
**2026-03-04**: 255 scanned → 141 passed → VCIG(vol=4,955,408), DFSC(vol=2,355,167), CRCG(vol=1,944,393), CRWG(vol=1,226,816), RGTX(vol=535,294)
**2026-03-05**: 128 scanned → 88 passed → MTEK(vol=16,314,662), HTOO(vol=4,026,558), BATL(vol=4,741,664), TMDE(vol=2,112,626), RKLZ(vol=1,673,660)
**2026-03-06**: 99 scanned → 78 passed → TPET(vol=39,111,323), CRE(vol=8,851,611), AIFF(vol=9,965,062), IBG(vol=7,190,524), QCLS(vol=1,772,571)
**2026-03-09**: 115 scanned → 88 passed → HIMZ(vol=16,565,425), TPET(vol=20,313,467), AGH(vol=8,225,206), OPTX(vol=1,294,570), CRCG(vol=860,012)
**2026-03-10**: 164 scanned → 120 passed → VTAK(vol=20,624,502), INKT(vol=4,446,474), CRCG(vol=5,912,456), HIMZ(vol=2,802,204), TMDE(vol=290,889)
**2026-03-11**: 120 scanned → 91 passed → HIMZ(vol=13,859,962), SXTP(vol=4,552,651), ACXP(vol=2,229,703), TMDE(vol=1,841,643), CODX(vol=1,012,394)
**2026-03-12**: 89 scanned → 73 passed → TLYS(vol=9,533,749), RBNE(vol=2,854,546), HIMZ(vol=2,348,246), TMDE(vol=942,206), DTCK(vol=514,799)

---

## Section 9: Robustness Checks

### Config A
- P&L without top 3 winners: $-15,196
- Top 3 winners: $+2,121
- Longest consecutive losing streak (days): 7
- Win/loss count (excl breakeven): 17W / 61L

### Config B
- P&L without top 3 winners: $-15,505
- Top 3 winners: $+2,086
- Longest consecutive losing streak (days): 8
- Win/loss count (excl breakeven): 21W / 65L

---

*Generated from YTD V2 backtest | Top-5 ranked, 5 trade cap, daily loss limit | Tick mode, Alpaca feed, dynamic sizing | Branch: v6-dynamic-sizing*