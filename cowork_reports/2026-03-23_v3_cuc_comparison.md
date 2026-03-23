# V3 CUC Gate Comparison — YTD 2026
## Generated 2026-03-23

Period: Jan 2 - Mar 20, 2026 (55 trading days)
Starting Equity: $30,000

## All Configs Comparison

| Metric | A (Baseline) | B (V2) | C (MinBars=5) | D (FloorR=2) | E (Both) |
|--------|-------------|--------|---------------|--------------|----------|
| total_pnl | $+25,709 | $+14,910 | $+16,959 | $+15,924 | $+16,786 |
| total_trades | 33 | 28 | 27 | 27 | 26 |
| win_rate | 17/33 (52%) | 10/27 (37%) | 10/26 (38%) | 11/26 (42%) | 10/25 (40%) |
| avg_win | $+1,855 | $+1,998 | $+2,185 | $+1,885 | $+2,167 |
| avg_loss | $-364 | $-298 | $-306 | $-321 | $-326 |
| profit_factor | 5.42 | 3.94 | 4.47 | 4.31 | 4.44 |
| max_dd | $+3,277 | $+1,804 | $+1,764 | $+1,511 | $+1,730 |
| largest_win | $+14,642 | $+12,981 | $+13,293 | $+13,293 | $+13,293 |
| largest_loss | $-1,250 | $-806 | $-592 | $-579 | $-592 |

## CUC Exit Analysis

### V2 + MinBars=5
- CUC exits: 2
- CUC P&L: $+622
- Non-CUC exits: 25
- Non-CUC P&L: $+16,337
| Date | Symbol | Entry | Exit | Reason | P&L |
|------|--------|-------|------|--------|-----|
| 2026-01-20 | POLA | $2.90 | $3.01 | ross_cuc_exit | $+427 |
| 2026-03-19 | SER | $2.22 | $2.26 | ross_cuc_exit | $+195 |

### V2 + FloorR=2.0
- CUC exits: 1
- CUC P&L: $+1,942
- Non-CUC exits: 26
- Non-CUC P&L: $+13,982
| Date | Symbol | Entry | Exit | Reason | P&L |
|------|--------|-------|------|--------|-----|
| 2026-01-21 | SLGB | $3.04 | $3.53 | ross_cuc_exit | $+1,942 |

### V2 + MinBars=5 + FloorR=2.0
- CUC exits: 0
- CUC P&L: $+0
- Non-CUC exits: 26
- Non-CUC P&L: $+16,786


## Exit Reason Distribution

### V2 + MinBars=5
| Exit Reason | Count | Total P&L | Avg P&L |
|-------------|-------|-----------|---------|
| max_loss_hit | 6 | $-1,573 | $-263 |
| ross_doji_partial | 5 | $+4,940 | $+988 |
| ross_shooting_star | 4 | $+15,979 | $+3,994 |
| sq_stop_hit | 3 | $-1,114 | $-372 |
| stop_hit | 3 | $-1,473 | $-491 |
| sq_max_loss_hit | 2 | $-415 | $-208 |
| ross_cuc_exit | 2 | $+622 | $+311 |
| ross_topping_tail_warning | 1 | $-7 | $-7 |
| ross_gravestone_doji | 1 | $+0 | $+0 |

### V2 + FloorR=2.0
| Exit Reason | Count | Total P&L | Avg P&L |
|-------------|-------|-----------|---------|
| max_loss_hit | 6 | $-1,545 | $-258 |
| ross_shooting_star | 5 | $+16,130 | $+3,226 |
| ross_doji_partial | 5 | $+2,339 | $+467 |
| sq_stop_hit | 3 | $-1,114 | $-372 |
| stop_hit | 3 | $-1,440 | $-480 |
| sq_max_loss_hit | 2 | $-415 | $-208 |
| ross_cuc_exit | 1 | $+1,942 | $+1,942 |
| ross_topping_tail_warning | 1 | $+27 | $+27 |
| ross_gravestone_doji | 1 | $+0 | $+0 |

### V2 + MinBars=5 + FloorR=2.0
| Exit Reason | Count | Total P&L | Avg P&L |
|-------------|-------|-----------|---------|
| ross_doji_partial | 6 | $+5,355 | $+892 |
| max_loss_hit | 6 | $-1,573 | $-263 |
| ross_shooting_star | 4 | $+15,979 | $+3,994 |
| sq_stop_hit | 3 | $-1,114 | $-372 |
| stop_hit | 3 | $-1,473 | $-491 |
| sq_max_loss_hit | 2 | $-415 | $-208 |
| ross_topping_tail_warning | 1 | $+27 | $+27 |
| ross_gravestone_doji | 1 | $+0 | $+0 |


## Trade Detail (All Configs)

### V2 + MinBars=5
| Date | Symbol | Entry | Exit | Reason | P&L |
|------|--------|-------|------|--------|-----|
| 2026-01-08 | ACON | $8.04 | $7.90 | sq_stop_hit | $-375 |
| 2026-01-12 | BDSX | $8.30 | $8.18 | sq_max_loss_hit | $-317 |
| 2026-01-13 | SPRC | $2.04 | $1.90 | sq_stop_hit | $-366 |
| 2026-01-14 | ROLR | $12.24 | $16.94 | ross_shooting_star | $+945 |
| 2026-01-15 | CJMB | $4.68 | $5.13 | ross_shooting_star | $+1,200 |
| 2026-01-15 | SPHL | $4.04 | $3.90 | sq_stop_hit | $-373 |
| 2026-01-16 | VERO | $3.58 | $5.66 | ross_shooting_star | $+13,293 |
| 2026-01-20 | POLA | $2.90 | $3.01 | ross_cuc_exit | $+427 |
| 2026-01-21 | SLGB | $3.04 | $3.82 | ross_doji_partial | $+3,003 |
| 2026-01-22 | IOTR | $8.62 | $8.14 | stop_hit | $-592 |
| 2026-01-23 | MOVE | $19.92 | $19.13 | stop_hit | $-592 |
| 2026-01-26 | BATL | $5.04 | $6.15 | ross_doji_partial | $+963 |
| 2026-01-27 | CYN | $3.67 | $3.48 | max_loss_hit | $-99 |
| 2026-01-29 | FEED | $4.11 | $4.10 | ross_doji_partial | $-309 |
| 2026-02-06 | WHLR | $3.12 | $3.18 | ross_topping_tail_warning | $-7 |
| 2026-02-13 | RAIN | $2.70 | $2.61 | max_loss_hit | $-340 |
| 2026-02-17 | PLYX | $4.89 | $4.48 | max_loss_hit | $-248 |
| 2026-02-19 | RUBI | $3.15 | $2.94 | stop_hit | $-289 |
| 2026-02-20 | CDIO | $3.27 | $3.13 | max_loss_hit | $-248 |
| 2026-03-03 | MXC | $15.82 | $16.00 | ross_shooting_star | $+541 |
| 2026-03-05 | MSGM | $4.52 | $4.36 | max_loss_hit | $-544 |
| 2026-03-12 | TLYS | $2.72 | $2.72 | ross_gravestone_doji | $+0 |
| 2026-03-18 | ARTL | $7.62 | $8.00 | ross_doji_partial | $+1,096 |
| 2026-03-19 | SER | $2.22 | $2.26 | ross_cuc_exit | $+195 |
| 2026-03-19 | DLTH | $2.92 | $2.83 | max_loss_hit | $-94 |
| 2026-03-20 | ANNA | $5.04 | $4.93 | sq_max_loss_hit | $-98 |
| 2026-03-20 | ANNA | $5.04 | $5.29 | ross_doji_partial | $+187 |

### V2 + FloorR=2.0
| Date | Symbol | Entry | Exit | Reason | P&L |
|------|--------|-------|------|--------|-----|
| 2026-01-08 | ACON | $8.04 | $7.90 | sq_stop_hit | $-375 |
| 2026-01-12 | BDSX | $8.30 | $8.18 | sq_max_loss_hit | $-317 |
| 2026-01-13 | SPRC | $2.04 | $1.90 | sq_stop_hit | $-366 |
| 2026-01-14 | ROLR | $12.24 | $16.94 | ross_shooting_star | $+945 |
| 2026-01-15 | CJMB | $4.68 | $5.13 | ross_shooting_star | $+1,200 |
| 2026-01-15 | SPHL | $4.04 | $3.90 | sq_stop_hit | $-373 |
| 2026-01-16 | VERO | $3.58 | $5.66 | ross_shooting_star | $+13,293 |
| 2026-01-20 | POLA | $2.90 | $2.98 | ross_doji_partial | $+414 |
| 2026-01-21 | SLGB | $3.04 | $3.53 | ross_cuc_exit | $+1,942 |
| 2026-01-22 | IOTR | $8.62 | $8.14 | stop_hit | $-579 |
| 2026-01-23 | MOVE | $19.92 | $19.13 | stop_hit | $-579 |
| 2026-01-26 | BATL | $5.04 | $6.15 | ross_doji_partial | $+963 |
| 2026-01-27 | CYN | $3.67 | $3.48 | max_loss_hit | $-99 |
| 2026-01-29 | FEED | $4.11 | $4.10 | ross_doji_partial | $-302 |
| 2026-02-06 | WHLR | $3.12 | $3.18 | ross_topping_tail_warning | $+27 |
| 2026-02-13 | RAIN | $2.70 | $2.61 | max_loss_hit | $-332 |
| 2026-02-17 | PLYX | $4.89 | $4.48 | max_loss_hit | $-242 |
| 2026-02-19 | RUBI | $3.15 | $2.94 | stop_hit | $-282 |
| 2026-02-19 | RUBI | $4.04 | $4.08 | ross_shooting_star | $+161 |
| 2026-02-20 | CDIO | $3.27 | $3.13 | max_loss_hit | $-244 |
| 2026-03-03 | MXC | $15.82 | $16.00 | ross_shooting_star | $+531 |
| 2026-03-05 | MSGM | $4.52 | $4.36 | max_loss_hit | $-534 |
| 2026-03-12 | TLYS | $2.72 | $2.72 | ross_gravestone_doji | $+0 |
| 2026-03-18 | ARTL | $7.62 | $8.00 | ross_doji_partial | $+1,077 |
| 2026-03-19 | DLTH | $2.92 | $2.83 | max_loss_hit | $-94 |
| 2026-03-20 | ANNA | $5.04 | $4.93 | sq_max_loss_hit | $-98 |
| 2026-03-20 | ANNA | $5.04 | $5.29 | ross_doji_partial | $+187 |

### V2 + MinBars=5 + FloorR=2.0
| Date | Symbol | Entry | Exit | Reason | P&L |
|------|--------|-------|------|--------|-----|
| 2026-01-08 | ACON | $8.04 | $7.90 | sq_stop_hit | $-375 |
| 2026-01-12 | BDSX | $8.30 | $8.18 | sq_max_loss_hit | $-317 |
| 2026-01-13 | SPRC | $2.04 | $1.90 | sq_stop_hit | $-366 |
| 2026-01-14 | ROLR | $12.24 | $16.94 | ross_shooting_star | $+945 |
| 2026-01-15 | CJMB | $4.68 | $5.13 | ross_shooting_star | $+1,200 |
| 2026-01-15 | SPHL | $4.04 | $3.90 | sq_stop_hit | $-373 |
| 2026-01-16 | VERO | $3.58 | $5.66 | ross_shooting_star | $+13,293 |
| 2026-01-20 | POLA | $2.90 | $2.98 | ross_doji_partial | $+414 |
| 2026-01-21 | SLGB | $3.04 | $3.82 | ross_doji_partial | $+3,003 |
| 2026-01-22 | IOTR | $8.62 | $8.14 | stop_hit | $-592 |
| 2026-01-23 | MOVE | $19.92 | $19.13 | stop_hit | $-592 |
| 2026-01-26 | BATL | $5.04 | $6.15 | ross_doji_partial | $+963 |
| 2026-01-27 | CYN | $3.67 | $3.48 | max_loss_hit | $-99 |
| 2026-01-29 | FEED | $4.11 | $4.10 | ross_doji_partial | $-309 |
| 2026-02-06 | WHLR | $3.12 | $3.18 | ross_topping_tail_warning | $+27 |
| 2026-02-13 | RAIN | $2.70 | $2.61 | max_loss_hit | $-340 |
| 2026-02-17 | PLYX | $4.89 | $4.48 | max_loss_hit | $-248 |
| 2026-02-19 | RUBI | $3.15 | $2.94 | stop_hit | $-289 |
| 2026-02-20 | CDIO | $3.27 | $3.13 | max_loss_hit | $-248 |
| 2026-03-03 | MXC | $15.82 | $16.00 | ross_shooting_star | $+541 |
| 2026-03-05 | MSGM | $4.52 | $4.36 | max_loss_hit | $-544 |
| 2026-03-12 | TLYS | $2.72 | $2.72 | ross_gravestone_doji | $+0 |
| 2026-03-18 | ARTL | $7.62 | $8.00 | ross_doji_partial | $+1,097 |
| 2026-03-19 | DLTH | $2.92 | $2.83 | max_loss_hit | $-94 |
| 2026-03-20 | ANNA | $5.04 | $4.93 | sq_max_loss_hit | $-98 |
| 2026-03-20 | ANNA | $5.04 | $5.29 | ross_doji_partial | $+187 |
