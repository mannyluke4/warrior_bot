# YTD V2 Backtest Results: Ross Exit V2 vs Baseline
## Generated 2026-03-24

Period: January 2 - March 20, 2026 (55 trading days)
Starting Equity: $30,000
Risk: 2.5% of equity (dynamic)
Max trades/day: 5 | Daily loss limit: $-1,500 | Max notional: $50,000
Scanner filter: PM vol >= 50,000 (no hard floor), gap 10-500%, float < 10M
Top 5 candidates per day by composite rank (70% volume + 20% gap + 10% float)

---

## Section 1: V1 vs V2 Comparison

| Metric | V1 Config A | V2 Config A | V2 Config B |
|--------|-------------|-------------|-------------|
| Total Trades | 184 (11 days) | 33 (55 days) | 28 (55 days) |
| Avg Trades/Day | 16.7 | 0.6 | 0.5 |
| Final Equity | $7,755 | $55,709 | $44,910 |
| Total P&L | -$22,245 | $+25,709 | $+14,910 |
| Total Return | -74.2% | +85.7% | +49.7% |

---

## Section 2: Summary - Baseline vs Ross Exit V2

| Metric | Baseline (Ross Exit OFF) | V2 (Ross Exit ON) |
|--------|--------------------------|---------------------|
| Final Equity | $55,709 | $44,910 |
| Total P&L | $+25,709 | $+14,910 |
| Total Return | +85.7% | +49.7% |
| Total Trades | 33 | 28 |
| Avg Trades/Day | 0.6 | 0.5 |
| Win Rate | 17/33 (52%) | 10/27 (37%) |
| Average Win | $+1,855 | $+1,998 |
| Average Loss | $-364 | $-298 |
| Profit Factor | 5.42 | 3.94 |
| Max Drawdown $ | $3,277 | $1,804 |
| Max Drawdown % | 5.9% | 3.9% |
| Largest Win | $+14,642 | $+12,981 |
| Largest Loss | $-1,250 | $-806 |

---

## Section 3: Monthly Breakdown

| Month | A P&L | A Trades | B P&L | B Trades |
|-------|-------|----------|-------|----------|
| Jan | $+18,170 | 17 | $+14,703 | 14 |
| Feb | $-1,419 | 7 | $-827 | 6 |
| Mar | $+8,958 | 9 | $+1,034 | 8 |

---

## Section 4: Daily Detail

| Date | Scanned | Passed | Top N | A Trades | A P&L | A Equity | B Trades | B P&L | B Equity |
|------|---------|--------|-------|----------|-------|----------|----------|-------|----------|
| 2026-01-02 | 2 | 2 | 2 | 0 | $+0 | $30,000 | 0 | $+0 | $30,000 |
| 2026-01-03 | 0 | 0 | 0 | 0 | $+0 | $30,000 no candidates (total=0, passed=0) | 0 | $+0 | $30,000 |
| 2026-01-05 | 1 | 1 | 1 | 0 | $+0 | $30,000 | 0 | $+0 | $30,000 |
| 2026-01-06 | 2 | 2 | 2 | 0 | $+0 | $30,000 | 0 | $+0 | $30,000 |
| 2026-01-07 | 2 | 2 | 2 | 0 | $+0 | $30,000 | 0 | $+0 | $30,000 |
| 2026-01-08 | 2 | 2 | 2 | 1 | $+582 | $30,582 | 1 | $-375 | $29,625 |
| 2026-01-09 | 4 | 4 | 4 | 0 | $+0 | $30,582 | 0 | $+0 | $29,625 |
| 2026-01-12 | 2 | 2 | 2 | 1 | $-327 | $30,255 | 1 | $-317 | $29,308 |
| 2026-01-13 | 7 | 7 | 5 | 1 | $+54 | $30,309 | 1 | $-366 | $28,942 |
| 2026-01-14 | 2 | 2 | 2 | 1 | $+241 | $30,550 | 1 | $+229 | $29,171 |
| 2026-01-15 | 6 | 5 | 5 | 2 | $+981 | $31,531 | 2 | $+807 | $29,978 |
| 2026-01-16 | 6 | 6 | 5 | 1 | $+14,642 | $46,173 | 1 | $+12,981 | $42,959 |
| 2026-01-20 | 8 | 8 | 5 | 1 | $+165 | $46,338 | 1 | $+804 | $43,763 |
| 2026-01-21 | 4 | 4 | 4 | 1 | $+3,690 | $50,028 | 1 | $+1,914 | $45,677 |
| 2026-01-22 | 4 | 4 | 4 | 2 | $-1,693 | $48,335 | 1 | $-737 | $44,940 |
| 2026-01-23 | 7 | 5 | 5 | 1 | $-661 | $47,674 | 1 | $-806 | $44,134 |
| 2026-01-26 | 5 | 4 | 4 | 3 | $+730 | $48,404 | 1 | $+963 | $45,097 |
| 2026-01-27 | 5 | 4 | 4 | 1 | $-198 | $48,206 | 1 | $-99 | $44,998 |
| 2026-01-28 | 3 | 3 | 3 | 0 | $+0 | $48,206 | 0 | $+0 | $44,998 |
| 2026-01-29 | 5 | 3 | 3 | 1 | $-36 | $48,170 | 1 | $-295 | $44,703 |
| 2026-01-30 | 2 | 2 | 2 | 0 | $+0 | $48,170 | 0 | $+0 | $44,703 |
| 2026-02-02 | 3 | 3 | 3 | 0 | $+0 | $48,170 | 0 | $+0 | $44,703 |
| 2026-02-03 | 5 | 4 | 4 | 0 | $+0 | $48,170 | 0 | $+0 | $44,703 |
| 2026-02-04 | 3 | 3 | 3 | 2 | $-499 | $47,671 | 0 | $+0 | $44,703 |
| 2026-02-05 | 1 | 1 | 1 | 0 | $+0 | $47,671 | 0 | $+0 | $44,703 |
| 2026-02-06 | 1 | 1 | 1 | 1 | $+83 | $47,754 | 1 | $-6 | $44,697 |
| 2026-02-09 | 1 | 1 | 1 | 0 | $+0 | $47,754 | 0 | $+0 | $44,697 |
| 2026-02-10 | 2 | 1 | 1 | 0 | $+0 | $47,754 | 0 | $+0 | $44,697 |
| 2026-02-11 | 4 | 4 | 4 | 0 | $+0 | $47,754 | 0 | $+0 | $44,697 |
| 2026-02-12 | 1 | 1 | 1 | 0 | $+0 | $47,754 | 0 | $+0 | $44,697 |
| 2026-02-13 | 3 | 3 | 3 | 1 | $-309 | $47,445 | 1 | $-325 | $44,372 |
| 2026-02-17 | 2 | 2 | 2 | 1 | $-185 | $47,260 | 1 | $-237 | $44,135 |
| 2026-02-18 | 2 | 2 | 2 | 0 | $+0 | $47,260 | 0 | $+0 | $44,135 |
| 2026-02-19 | 1 | 1 | 1 | 1 | $-141 | $47,119 | 2 | $+53 | $44,188 |
| 2026-02-20 | 5 | 4 | 4 | 1 | $-368 | $46,751 | 1 | $-312 | $43,876 |
| 2026-02-23 | 1 | 1 | 1 | 0 | $+0 | $46,751 | 0 | $+0 | $43,876 |
| 2026-02-24 | 1 | 1 | 1 | 0 | $+0 | $46,751 | 0 | $+0 | $43,876 |
| 2026-02-25 | 1 | 1 | 1 | 0 | $+0 | $46,751 | 0 | $+0 | $43,876 |
| 2026-02-26 | 1 | 1 | 1 | 0 | $+0 | $46,751 | 0 | $+0 | $43,876 |
| 2026-02-27 | 1 | 0 | 0 | 0 | $+0 | $46,751 no candidates (total=1, passed=0) | 0 | $+0 | $43,876 |
| 2026-03-02 | 3 | 3 | 3 | 0 | $+0 | $46,751 | 0 | $+0 | $43,876 |
| 2026-03-03 | 1 | 1 | 1 | 1 | $+1,476 | $48,227 | 1 | $+519 | $44,395 |
| 2026-03-04 | 2 | 2 | 2 | 0 | $+0 | $48,227 | 0 | $+0 | $44,395 |
| 2026-03-05 | 5 | 3 | 3 | 1 | $-1,134 | $47,093 | 1 | $-522 | $43,873 |
| 2026-03-06 | 3 | 3 | 3 | 1 | $+7,156 | $54,249 | 0 | $+0 | $43,873 |
| 2026-03-09 | 2 | 2 | 2 | 0 | $+0 | $54,249 | 0 | $+0 | $43,873 |
| 2026-03-10 | 3 | 3 | 3 | 0 | $+0 | $54,249 | 0 | $+0 | $43,873 |
| 2026-03-11 | 2 | 2 | 2 | 0 | $+0 | $54,249 | 0 | $+0 | $43,873 |
| 2026-03-12 | 2 | 2 | 2 | 1 | $+19 | $54,268 | 1 | $+0 | $43,873 |
| 2026-03-13 | 2 | 2 | 2 | 0 | $+0 | $54,268 | 0 | $+0 | $43,873 |
| 2026-03-16 | 0 | 0 | 0 | 0 | $+0 | $54,268 no candidates (total=0, passed=0) | 0 | $+0 | $43,873 |
| 2026-03-17 | 0 | 0 | 0 | 0 | $+0 | $54,268 no candidates (total=0, passed=0) | 0 | $+0 | $43,873 |
| 2026-03-18 | 2 | 2 | 2 | 1 | $+1,250 | $55,518 | 1 | $+1,053 | $44,926 |
| 2026-03-19 | 4 | 4 | 4 | 2 | $+337 | $55,855 | 2 | $+94 | $45,020 |
| 2026-03-20 | 2 | 2 | 2 | 2 | $-146 | $55,709 | 2 | $-110 | $44,910 |

---

## Section 5: Trade-Level Detail

### Baseline (Ross Exit OFF)

| Date | Symbol | Score | Entry | Exit | Reason | P&L |
|------|--------|-------|-------|------|--------|-----|
| 2026-01-08 | ACON | 9.9 | $8.04 | $8.32 | sq_target_hit | $+582 |
| 2026-01-12 | BDSX | 9.2 | $8.30 | $8.18 | sq_max_loss_hit | $-327 |
| 2026-01-13 | SPRC | 7.7 | $2.04 | $2.06 | sq_para_trail_exit | $+54 |
| 2026-01-14 | ROLR | 17.0 | $12.24 | $13.38 | topping_wicky_exit_full | $+241 |
| 2026-01-15 | CJMB | 7.8 | $4.68 | $4.96 | sq_target_hit | $+736 |
| 2026-01-15 | SPHL | 7.7 | $4.04 | $4.13 | sq_para_trail_exit | $+245 |
| 2026-01-16 | VERO | 15.6 | $3.58 | $5.81 | bearish_engulfing_exit_full | $+14,642 |
| 2026-01-20 | POLA | 9.1 | $2.90 | $2.94 | sq_para_trail_exit | $+165 |
| 2026-01-21 | SLGB | 10.0 | $3.04 | $4.00 | sq_target_hit | $+3,690 |
| 2026-01-22 | IOTR | 17.0 | $8.62 | $8.45 | bearish_engulfing_exit_full | $-443 |
| 2026-01-22 | SXTP | 16.0 | $7.29 | $6.87 | stop_hit | $-1,250 |
| 2026-01-23 | MOVE | 18.5 | $19.92 | $19.49 | bearish_engulfing_exit_full | $-661 |
| 2026-01-26 | BATL | 6.0 | $5.04 | $5.11 | sq_para_trail_exit | $+62 |
| 2026-01-26 | BATL | 6.1 | $5.04 | $5.31 | sq_target_hit | $+423 |
| 2026-01-26 | BATL | 7.7 | $6.04 | $6.32 | sq_target_hit | $+245 |
| 2026-01-27 | CYN | 15.5 | $3.67 | $3.48 | max_loss_hit | $-198 |
| 2026-01-29 | FEED | 15.0 | $4.11 | $4.10 | bearish_engulfing_exit_full | $-36 |
| 2026-02-04 | BOXL | 9.2 | $2.04 | $1.98 | sq_para_trail_exit | $-258 |
| 2026-02-04 | BOXL | 6.5 | $2.16 | $2.12 | sq_para_trail_exit | $-241 |
| 2026-02-06 | WHLR | 14.5 | $3.12 | $3.18 | topping_wicky_exit_full | $+83 |
| 2026-02-13 | RAIN | 12.5 | $2.70 | $2.66 | bearish_engulfing_exit_full | $-309 |
| 2026-02-17 | PLYX | 16.5 | $4.89 | $4.74 | bearish_engulfing_exit_full | $-185 |
| 2026-02-19 | RUBI | 16.0 | $3.15 | $3.10 | topping_wicky_exit_full | $-141 |
| 2026-02-20 | CDIO | 15.5 | $3.27 | $3.17 | bearish_engulfing_exit_full | $-368 |
| 2026-03-03 | MXC | 14.5 | $15.82 | $16.30 | topping_wicky_exit_full | $+1,476 |
| 2026-03-05 | MSGM | 8.5 | $4.52 | $4.36 | max_loss_hit | $-1,134 |
| 2026-03-06 | CRE | 7.5 | $5.04 | $6.89 | sq_target_hit | $+7,156 |
| 2026-03-12 | TLYS | 16.5 | $2.72 | $2.73 | topping_wicky_exit_full | $+19 |
| 2026-03-18 | ARTL | 14.5 | $7.62 | $7.92 | topping_wicky_exit_full | $+1,250 |
| 2026-03-19 | SER | 11.0 | $2.22 | $2.30 | sq_para_trail_exit | $+462 |
| 2026-03-19 | DLTH | 15.0 | $2.92 | $2.86 | bearish_engulfing_exit_full | $-125 |
| 2026-03-20 | ANNA | 11.0 | $5.04 | $4.93 | sq_max_loss_hit | $-98 |
| 2026-03-20 | ANNA | 8.3 | $5.04 | $4.96 | sq_trail_exit | $-48 |

### V2 (Ross Exit ON)

| Date | Symbol | Score | Entry | Exit | Reason | P&L |
|------|--------|-------|-------|------|--------|-----|
| 2026-01-08 | ACON | 9.9 | $8.04 | $7.90 | sq_stop_hit | $-375 |
| 2026-01-12 | BDSX | 9.2 | $8.30 | $8.18 | sq_max_loss_hit | $-317 |
| 2026-01-13 | SPRC | 7.7 | $2.04 | $1.90 | sq_stop_hit | $-366 |
| 2026-01-14 | ROLR | 17.0 | $12.24 | $13.38 | ross_cuc_exit | $+229 |
| 2026-01-15 | CJMB | 7.8 | $4.68 | $5.13 | ross_shooting_star | $+1,171 |
| 2026-01-15 | SPHL | 7.7 | $4.04 | $3.90 | sq_stop_hit | $-364 |
| 2026-01-16 | VERO | 15.6 | $3.58 | $5.66 | ross_shooting_star | $+12,981 |
| 2026-01-20 | POLA | 9.1 | $2.90 | $3.11 | ross_cuc_exit | $+804 |
| 2026-01-21 | SLGB | 10.0 | $3.04 | $3.53 | ross_cuc_exit | $+1,914 |
| 2026-01-22 | IOTR | 17.0 | $8.62 | $8.31 | ross_cuc_exit | $-737 |
| 2026-01-23 | MOVE | 18.5 | $19.92 | $19.36 | ross_cuc_exit | $-806 |
| 2026-01-26 | BATL | 6.0 | $5.04 | $6.15 | ross_doji_partial | $+963 |
| 2026-01-27 | CYN | 15.5 | $3.67 | $3.48 | max_loss_hit | $-99 |
| 2026-01-29 | FEED | 15.0 | $4.11 | $4.10 | ross_doji_partial | $-295 |
| 2026-02-06 | WHLR | 14.5 | $3.12 | $3.18 | ross_topping_tail_warning | $-6 |
| 2026-02-13 | RAIN | 12.5 | $2.70 | $2.61 | max_loss_hit | $-325 |
| 2026-02-17 | PLYX | 16.5 | $4.89 | $4.48 | max_loss_hit | $-237 |
| 2026-02-19 | RUBI | 16.0 | $3.15 | $3.11 | ross_cuc_exit | $-105 |
| 2026-02-19 | RUBI | 6.7 | $4.04 | $4.08 | ross_shooting_star | $+158 |
| 2026-02-20 | CDIO | 15.5 | $3.27 | $3.18 | ross_cuc_exit | $-312 |
| 2026-03-03 | MXC | 14.5 | $15.82 | $16.00 | ross_shooting_star | $+519 |
| 2026-03-05 | MSGM | 8.5 | $4.52 | $4.36 | max_loss_hit | $-522 |
| 2026-03-12 | TLYS | 16.5 | $2.72 | $2.72 | ross_gravestone_doji | $+0 |
| 2026-03-18 | ARTL | 14.5 | $7.62 | $8.00 | ross_doji_partial | $+1,053 |
| 2026-03-19 | SER | 11.0 | $2.22 | $2.26 | ross_cuc_exit | $+188 |
| 2026-03-19 | DLTH | 15.0 | $2.92 | $2.83 | max_loss_hit | $-94 |
| 2026-03-20 | ANNA | 11.0 | $5.04 | $4.93 | sq_max_loss_hit | $-98 |
| 2026-03-20 | ANNA | 8.3 | $5.04 | $5.02 | ross_cuc_exit | $-12 |

---

## Section 6: Exit Reason Distribution

### Baseline (Ross Exit OFF)
| Exit Reason | Count | Total P&L | Avg P&L |
|-------------|-------|-----------|---------|
| bearish_engulfing_exit_full | 8 | $+12,515 | $+1,564 |
| sq_para_trail_exit | 7 | $+489 | $+70 |
| sq_target_hit | 6 | $+12,832 | $+2,139 |
| topping_wicky_exit_full | 6 | $+2,928 | $+488 |
| sq_max_loss_hit | 2 | $-425 | $-212 |
| max_loss_hit | 2 | $-1,332 | $-666 |
| stop_hit | 1 | $-1,250 | $-1,250 |
| sq_trail_exit | 1 | $-48 | $-48 |

### V2 (Ross Exit ON)
| Exit Reason | Count | Total P&L | Avg P&L |
|-------------|-------|-----------|---------|
| ross_cuc_exit | 9 | $+1,163 | $+129 |
| max_loss_hit | 5 | $-1,277 | $-255 |
| ross_shooting_star | 4 | $+14,829 | $+3,707 |
| sq_stop_hit | 3 | $-1,105 | $-368 |
| ross_doji_partial | 3 | $+1,721 | $+574 |
| sq_max_loss_hit | 2 | $-415 | $-208 |
| ross_topping_tail_warning | 1 | $-6 | $-6 |
| ross_gravestone_doji | 1 | $+0 | $+0 |

## Section 6b: Head-to-Head Trade Comparison

Trades on same date + symbol in both configs:

| Date | Symbol | Baseline P&L | V2 P&L | Delta | Baseline Exit | V2 Exit |
|------|--------|-------------|--------|-------|---------------|---------|
| 2026-01-08 | ACON | $+582 | $-375 | $-957 | sq_target_hit | sq_stop_hit |
| 2026-01-12 | BDSX | $-327 | $-317 | $+10 | sq_max_loss_hit | sq_max_loss_hit |
| 2026-01-13 | SPRC | $+54 | $-366 | $-420 | sq_para_trail_exit | sq_stop_hit |
| 2026-01-14 | ROLR | $+241 | $+229 | $-12 | topping_wicky_exit_full | ross_cuc_exit |
| 2026-01-15 | CJMB | $+736 | $+1,171 | $+435 | sq_target_hit | ross_shooting_star |
| 2026-01-15 | SPHL | $+245 | $-364 | $-609 | sq_para_trail_exit | sq_stop_hit |
| 2026-01-16 | VERO | $+14,642 | $+12,981 | $-1,661 | bearish_engulfing_exit_full | ross_shooting_star |
| 2026-01-20 | POLA | $+165 | $+804 | $+639 | sq_para_trail_exit | ross_cuc_exit |
| 2026-01-21 | SLGB | $+3,690 | $+1,914 | $-1,776 | sq_target_hit | ross_cuc_exit |
| 2026-01-22 | IOTR | $-443 | $-737 | $-294 | bearish_engulfing_exit_full | ross_cuc_exit |
| 2026-01-23 | MOVE | $-661 | $-806 | $-145 | bearish_engulfing_exit_full | ross_cuc_exit |
| 2026-01-26 | BATL | $+730 | $+963 | $+233 | sq_para_trail_exit, sq_target_hit, sq_target_hit | ross_doji_partial |
| 2026-01-27 | CYN | $-198 | $-99 | $+99 | max_loss_hit | max_loss_hit |
| 2026-01-29 | FEED | $-36 | $-295 | $-259 | bearish_engulfing_exit_full | ross_doji_partial |
| 2026-02-06 | WHLR | $+83 | $-6 | $-89 | topping_wicky_exit_full | ross_topping_tail_warning |
| 2026-02-13 | RAIN | $-309 | $-325 | $-16 | bearish_engulfing_exit_full | max_loss_hit |
| 2026-02-17 | PLYX | $-185 | $-237 | $-52 | bearish_engulfing_exit_full | max_loss_hit |
| 2026-02-19 | RUBI | $-141 | $+53 | $+194 | topping_wicky_exit_full | ross_cuc_exit, ross_shooting_star |
| 2026-02-20 | CDIO | $-368 | $-312 | $+56 | bearish_engulfing_exit_full | ross_cuc_exit |
| 2026-03-03 | MXC | $+1,476 | $+519 | $-957 | topping_wicky_exit_full | ross_shooting_star |
| 2026-03-05 | MSGM | $-1,134 | $-522 | $+612 | max_loss_hit | max_loss_hit |
| 2026-03-12 | TLYS | $+19 | $+0 | $-19 | topping_wicky_exit_full | ross_gravestone_doji |
| 2026-03-18 | ARTL | $+1,250 | $+1,053 | $-197 | topping_wicky_exit_full | ross_doji_partial |
| 2026-03-19 | DLTH | $-125 | $-94 | $+31 | bearish_engulfing_exit_full | max_loss_hit |
| 2026-03-19 | SER | $+462 | $+188 | $-274 | sq_para_trail_exit | ross_cuc_exit |
| 2026-03-20 | ANNA | $-146 | $-110 | $+36 | sq_max_loss_hit, sq_trail_exit | sq_max_loss_hit, ross_cuc_exit |

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
**2026-01-07**: 2 scanned → 2 passed → CDIO(vol=6,536,915), NVVE(vol=15,642,799)
**2026-01-08**: 2 scanned → 2 passed → ACON(vol=4,695,008), SXTC(vol=2,345,330)
**2026-01-09**: 4 scanned → 4 passed → FEED(vol=2,868,491), KUST(vol=2,700,325), ICON(vol=3,622,622), APVO(vol=3,993,762)
**2026-01-12**: 2 scanned → 2 passed → BDSX(vol=5,401,463), SUGP(vol=218,401)
**2026-01-13**: 7 scanned → 7 passed → XAIR(vol=71,249,379), IOTR(vol=11,884,420), PMAX(vol=10,271,808), AHMA(vol=10,117,699), SPRC(vol=11,816,128)
**2026-01-14**: 2 scanned → 2 passed → ROLR(vol=10,669,416), CMND(vol=460,213)
**2026-01-15**: 6 scanned → 5 passed → CJMB(vol=16,555,670), SPHL(vol=5,016,154), CHNR(vol=125,588), AGPU(vol=237,778), NUWE(vol=62,102)
**2026-01-16**: 6 scanned → 6 passed → VERO(vol=26,831,003), ACCL(vol=10,272,856), BIYA(vol=7,050,459), LCFY(vol=143,179), GWAV(vol=1,537,606)
**2026-01-20**: 8 scanned → 8 passed → BTTC(vol=29,798,487), TWG(vol=9,478,348), IVF(vol=43,686,384), ICON(vol=12,463,348), POLA(vol=4,490,129)
**2026-01-21**: 4 scanned → 4 passed → GITS(vol=25,657,515), SLGB(vol=15,293,392), LSTA(vol=1,890,202), BOXL(vol=13,705,568)
**2026-01-22**: 4 scanned → 4 passed → NXTS(vol=21,390,097), IOTR(vol=22,198,275), SXTP(vol=13,877,243), RAYA(vol=7,955,230)
**2026-01-23**: 7 scanned → 5 passed → MOVE(vol=7,698,221), RVYL(vol=5,400,826), AUST(vol=2,868,732), RAYA(vol=3,987,249), KUST(vol=1,727,561)
**2026-01-26**: 5 scanned → 4 passed → BATL(vol=69,454,863), MBAI(vol=3,302,918), ARAI(vol=6,451,557), STAI(vol=749,277)
**2026-01-27**: 5 scanned → 4 passed → NUWE(vol=44,961,800), XHLD(vol=7,858,738), PHGE(vol=3,841,638), CYN(vol=4,255,770)
**2026-01-28**: 3 scanned → 3 passed → AIMD(vol=14,577,647), MRNO(vol=24,078,277), BBGI(vol=483,760)
**2026-01-29**: 5 scanned → 3 passed → SER(vol=26,039,627), FEED(vol=40,631,634), ZSTK(vol=409,368)
**2026-01-30**: 2 scanned → 2 passed → PMN(vol=1,484,456), VIVS(vol=10,777,851)
**2026-02-02**: 3 scanned → 3 passed → SWVL(vol=3,874,975), CISS(vol=19,182,335), IPW(vol=3,241,138)
**2026-02-03**: 5 scanned → 4 passed → FATN(vol=19,689,792), NPT(vol=3,557,700), CYN(vol=24,521,510), FIEE(vol=808,084)
**2026-02-04**: 3 scanned → 3 passed → ELPW(vol=31,138,608), CIGL(vol=5,720,243), BOXL(vol=23,869,470)
**2026-02-05**: 1 scanned → 1 passed → RNAZ(vol=2,728,563)
**2026-02-06**: 1 scanned → 1 passed → WHLR(vol=4,175,931)
**2026-02-09**: 1 scanned → 1 passed → ELTK(vol=423,304)
**2026-02-10**: 2 scanned → 1 passed → SPOG(vol=205,695)
**2026-02-11**: 4 scanned → 4 passed → BNRG(vol=7,093,915), ELAB(vol=3,242,923), SIF(vol=89,139), DFSC(vol=148,573)
**2026-02-12**: 1 scanned → 1 passed → VTAK(vol=84,170)
**2026-02-13**: 3 scanned → 3 passed → JDZG(vol=8,588,420), RAIN(vol=73,431), SIF(vol=95,144)
**2026-02-17**: 2 scanned → 2 passed → OBAI(vol=9,878,007), PLYX(vol=5,456,965)
**2026-02-18**: 2 scanned → 2 passed → BENF(vol=5,824,265), LRHC(vol=8,844,996)
**2026-02-19**: 1 scanned → 1 passed → RUBI(vol=8,486,662)
**2026-02-20**: 5 scanned → 4 passed → ANPA(vol=1,545,342), BJDX(vol=2,812,762), CDIO(vol=9,818,698), BIYA(vol=240,927)
**2026-02-23**: 1 scanned → 1 passed → GNPX(vol=1,627,057)
**2026-02-24**: 1 scanned → 1 passed → GRAN(vol=193,626)
**2026-02-25**: 1 scanned → 1 passed → INBS(vol=468,877)
**2026-02-26**: 1 scanned → 1 passed → SMJF(vol=2,871,906)
**2026-02-27**: 1 scanned → 0 passed filter → none selected
**2026-03-02**: 3 scanned → 3 passed → TMDE(vol=47,462,115), RBNE(vol=4,938,148), RLYB(vol=824,538)
**2026-03-03**: 1 scanned → 1 passed → MXC(vol=69,245)
**2026-03-04**: 2 scanned → 2 passed → VCIG(vol=4,955,408), ADVB(vol=4,872,809)
**2026-03-05**: 5 scanned → 3 passed → MTEK(vol=16,314,662), HTOO(vol=4,026,558), MSGM(vol=108,060)
**2026-03-06**: 3 scanned → 3 passed → CRE(vol=8,851,611), IBG(vol=7,190,524), QCLS(vol=1,772,571)
**2026-03-09**: 2 scanned → 2 passed → AGH(vol=8,225,206), OPTX(vol=1,294,570)
**2026-03-10**: 3 scanned → 3 passed → INKT(vol=4,446,474), VTAK(vol=20,624,502), PIII(vol=76,664)
**2026-03-11**: 2 scanned → 2 passed → SXTP(vol=4,552,651), CYN(vol=1,629,601)
**2026-03-12**: 2 scanned → 2 passed → POLA(vol=7,192,426), TLYS(vol=9,533,749)
**2026-03-13**: 2 scanned → 2 passed → BIAF(vol=58,819,656), EDHL(vol=2,511,571)
**2026-03-16**: 0 scanned → 0 passed filter → none selected
**2026-03-17**: 0 scanned → 0 passed filter → none selected
**2026-03-18**: 2 scanned → 2 passed → ARTL(vol=5,389,390), ZENA(vol=2,863,072)
**2026-03-19**: 4 scanned → 4 passed → CHNR(vol=16,578,027), SER(vol=16,357,200), SUNE(vol=6,611,877), DLTH(vol=874,194)
**2026-03-20**: 2 scanned → 2 passed → RDGT(vol=52,226), ANNA(vol=1,506,902)

---

## Section 9: Robustness Checks

### Config A
- P&L without top 3 winners: $+221
- Top 3 winners: $+25,488
- Longest consecutive losing streak (days): 4
- Win/loss count (excl breakeven): 17W / 16L

### Config B
- P&L without top 3 winners: $-1,156
- Top 3 winners: $+16,066
- Longest consecutive losing streak (days): 5
- Win/loss count (excl breakeven): 10W / 17L


---

## Section 10: Strategy Breakdown (MP vs Squeeze)

### Config A
| Strategy | Trades | Wins | Losses | Win Rate | Total P&L | Avg P&L |
|----------|--------|------|--------|----------|-----------|---------|
| Micro Pullback | 17 | 6 | 11 | 35% | $+12,861 | $+757 |
| Squeeze | 16 | 11 | 5 | 69% | $+12,848 | $+803 |

### Config B
| Strategy | Trades | Wins | Losses | Win Rate | Total P&L | Avg P&L |
|----------|--------|------|--------|----------|-----------|---------|
| Micro Pullback | 23 | 10 | 12 | 43% | $+16,430 | $+714 |
| Squeeze | 5 | 0 | 5 | 0% | $-1,520 | $-304 |

---

*Generated from YTD V2 backtest | Top-5 ranked, 5 trade cap, daily loss limit | Tick mode, Alpaca feed, dynamic sizing | Branch: v6-dynamic-sizing*