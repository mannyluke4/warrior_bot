# YTD V2 Backtest Results: SQ-Only vs SQ + MP V2
## Generated 2026-03-27

Period: January 2 - March 20, 2026 (60 trading days)
Starting Equity: $30,000
Risk: 2.5% of equity (dynamic)
Max trades/day: 5 | Daily loss limit: $-3,000 | Max notional: $100,000
Scanner filter: PM vol >= 50,000 (no hard floor), gap 10-500%, float < 15M
Top 5 candidates per day by composite rank (70% volume + 20% gap + 10% float)

---

## Section 1: V1 vs V2 Comparison

| Metric | V1 Config A | V2 Config A | V2 Config B |
|--------|-------------|-------------|-------------|
| Total Trades | 184 (11 days) | 54 (60 days) | 53 (60 days) |
| Avg Trades/Day | 16.7 | 0.9 | 0.9 |
| Final Equity | $7,755 | $85,427 | $86,236 |
| Total P&L | -$22,245 | $+55,427 | $+56,236 |
| Total Return | -74.2% | +184.8% | +187.5% |

---

## Section 2: Summary - Baseline vs MP V2

| Metric | Baseline (SQ-Only) | V2 (SQ + MP V2) |
|--------|--------------------------|---------------------|
| Final Equity | $85,427 | $86,236 |
| Total P&L | $+55,427 | $+56,236 |
| Total Return | +184.8% | +187.5% |
| Total Trades | 54 | 53 |
| Avg Trades/Day | 0.9 | 0.9 |
| Win Rate | 27/53 (51%) | 30/52 (58%) |
| Average Win | $+2,849 | $+2,404 |
| Average Loss | $-826 | $-721 |
| Profit Factor | 3.58 | 4.54 |
| Max Drawdown $ | $7,836 | $6,914 |
| Max Drawdown % | 8.4% | 7.4% |
| Largest Win | $+11,827 | $+11,881 |
| Largest Loss | $-2,735 | $-2,295 |

---

## Section 3: Monthly Breakdown

| Month | A P&L | A Trades | B P&L | B Trades |
|-------|-------|----------|-------|----------|
| Jan | $+36,574 | 30 | $+36,331 | 31 |
| Feb | $+9,826 | 10 | $+10,132 | 10 |
| Mar | $+9,027 | 14 | $+9,773 | 12 |

---

## Section 4: Daily Detail

| Date | Scanned | Passed | Top N | A Trades | A P&L | A Equity | B Trades | B P&L | B Equity |
|------|---------|--------|-------|----------|-------|----------|----------|-------|----------|
| 2026-01-02 | 0 | 0 | 0 | 0 | $+0 | $30,000 no candidates (total=0, passed=0) | 0 | $+0 | $30,000 |
| 2026-01-03 | 0 | 0 | 0 | 0 | $+0 | $30,000 no candidates (total=0, passed=0) | 0 | $+0 | $30,000 |
| 2026-01-05 | 0 | 0 | 0 | 0 | $+0 | $30,000 no candidates (total=0, passed=0) | 0 | $+0 | $30,000 |
| 2026-01-06 | 1 | 1 | 1 | 0 | $+0 | $30,000 | 0 | $+0 | $30,000 |
| 2026-01-07 | 0 | 0 | 0 | 0 | $+0 | $30,000 no candidates (total=0, passed=0) | 0 | $+0 | $30,000 |
| 2026-01-08 | 1 | 1 | 1 | 2 | $-168 | $29,832 | 2 | $+656 | $30,656 |
| 2026-01-09 | 2 | 2 | 2 | 0 | $+0 | $29,832 | 0 | $+0 | $30,656 |
| 2026-01-12 | 2 | 2 | 2 | 3 | $+2,259 | $32,091 | 3 | $+3,043 | $33,699 |
| 2026-01-13 | 3 | 3 | 3 | 2 | $+4,374 | $36,465 | 2 | $+4,592 | $38,291 |
| 2026-01-14 | 4 | 4 | 4 | 3 | $+14,752 | $51,217 | 3 | $+10,175 | $48,466 |
| 2026-01-15 | 4 | 4 | 4 | 3 | $+510 | $51,727 | 3 | $+1,286 | $49,752 |
| 2026-01-16 | 5 | 5 | 5 | 2 | $+3,626 | $55,353 | 2 | $+3,486 | $53,238 |
| 2026-01-20 | 5 | 5 | 5 | 4 | $+5,187 | $60,540 | 4 | $+5,866 | $59,104 |
| 2026-01-21 | 4 | 4 | 4 | 2 | $+4,390 | $64,930 | 3 | $+4,274 | $63,378 |
| 2026-01-22 | 2 | 2 | 2 | 3 | $-3,821 | $61,109 | 3 | $-2,494 | $60,884 |
| 2026-01-23 | 3 | 3 | 3 | 1 | $+6,421 | $67,530 | 1 | $+6,400 | $67,284 |
| 2026-01-26 | 3 | 3 | 3 | 1 | $+422 | $67,952 | 1 | $+420 | $67,704 |
| 2026-01-27 | 5 | 5 | 5 | 2 | $-1,587 | $66,365 | 2 | $-1,581 | $66,123 |
| 2026-01-28 | 2 | 2 | 2 | 0 | $+0 | $66,365 | 0 | $+0 | $66,123 |
| 2026-01-29 | 3 | 3 | 3 | 0 | $+0 | $66,365 | 0 | $+0 | $66,123 |
| 2026-01-30 | 2 | 2 | 2 | 2 | $+209 | $66,574 | 2 | $+208 | $66,331 |
| 2026-02-02 | 3 | 3 | 3 | 0 | $+0 | $66,574 | 0 | $+0 | $66,331 |
| 2026-02-03 | 3 | 3 | 3 | 1 | $+2,095 | $68,669 | 1 | $+2,087 | $68,418 |
| 2026-02-04 | 1 | 1 | 1 | 0 | $+0 | $68,669 | 0 | $+0 | $68,418 |
| 2026-02-05 | 1 | 1 | 1 | 1 | $-532 | $68,137 | 1 | $-530 | $67,888 |
| 2026-02-06 | 1 | 1 | 1 | 1 | $+6,280 | $74,417 | 1 | $+6,257 | $74,145 |
| 2026-02-09 | 0 | 0 | 0 | 0 | $+0 | $74,417 no candidates (total=0, passed=0) | 0 | $+0 | $74,145 |
| 2026-02-10 | 1 | 1 | 1 | 0 | $+0 | $74,417 | 0 | $+0 | $74,145 |
| 2026-02-11 | 1 | 1 | 1 | 0 | $+0 | $74,417 | 0 | $+0 | $74,145 |
| 2026-02-12 | 0 | 0 | 0 | 0 | $+0 | $74,417 no candidates (total=0, passed=0) | 0 | $+0 | $74,145 |
| 2026-02-13 | 1 | 1 | 1 | 0 | $+0 | $74,417 | 0 | $+0 | $74,145 |
| 2026-02-17 | 2 | 2 | 2 | 3 | $-157 | $74,260 | 3 | $-155 | $73,990 |
| 2026-02-18 | 1 | 1 | 1 | 0 | $+0 | $74,260 | 0 | $+0 | $73,990 |
| 2026-02-19 | 1 | 1 | 1 | 2 | $+3,311 | $77,571 | 2 | $+3,298 | $77,288 |
| 2026-02-20 | 1 | 1 | 1 | 2 | $-1,171 | $76,400 | 2 | $-825 | $76,463 |
| 2026-02-23 | 0 | 0 | 0 | 0 | $+0 | $76,400 no candidates (total=0, passed=0) | 0 | $+0 | $76,463 |
| 2026-02-24 | 0 | 0 | 0 | 0 | $+0 | $76,400 no candidates (total=0, passed=0) | 0 | $+0 | $76,463 |
| 2026-02-25 | 0 | 0 | 0 | 0 | $+0 | $76,400 no candidates (total=0, passed=0) | 0 | $+0 | $76,463 |
| 2026-02-26 | 0 | 0 | 0 | 0 | $+0 | $76,400 no candidates (total=0, passed=0) | 0 | $+0 | $76,463 |
| 2026-02-27 | 1 | 1 | 1 | 0 | $+0 | $76,400 | 0 | $+0 | $76,463 |
| 2026-03-02 | 3 | 3 | 3 | 0 | $+0 | $76,400 | 0 | $+0 | $76,463 |
| 2026-03-03 | 0 | 0 | 0 | 0 | $+0 | $76,400 no candidates (total=0, passed=0) | 0 | $+0 | $76,463 |
| 2026-03-04 | 1 | 1 | 1 | 0 | $+0 | $76,400 | 0 | $+0 | $76,463 |
| 2026-03-05 | 2 | 2 | 2 | 2 | $+1,432 | $77,832 | 2 | $+1,704 | $78,167 |
| 2026-03-06 | 2 | 2 | 2 | 1 | $+11,827 | $89,659 | 1 | $+11,881 | $90,048 |
| 2026-03-09 | 1 | 1 | 1 | 0 | $+0 | $89,659 | 0 | $+0 | $90,048 |
| 2026-03-10 | 2 | 2 | 2 | 1 | $-1,195 | $88,464 | 1 | $-1,200 | $88,848 |
| 2026-03-11 | 1 | 1 | 1 | 0 | $+0 | $88,464 | 0 | $+0 | $88,848 |
| 2026-03-12 | 2 | 2 | 2 | 1 | $+170 | $88,634 | 1 | $+171 | $89,019 |
| 2026-03-13 | 1 | 1 | 1 | 0 | $+0 | $88,634 | 0 | $+0 | $89,019 |
| 2026-03-16 | 0 | 0 | 0 | 0 | $+0 | $88,634 no candidates (total=0, passed=0) | 0 | $+0 | $89,019 |
| 2026-03-17 | 0 | 0 | 0 | 0 | $+0 | $88,634 no candidates (total=0, passed=0) | 0 | $+0 | $89,019 |
| 2026-03-18 | 2 | 2 | 2 | 1 | $+2,042 | $90,676 | 1 | $+834 | $89,853 |
| 2026-03-19 | 4 | 4 | 4 | 1 | $+680 | $91,356 | 1 | $+674 | $90,527 |
| 2026-03-20 | 0 | 0 | 0 | 0 | $+0 | $91,356 no candidates (total=0, passed=0) | 0 | $+0 | $90,527 |
| 2026-03-23 | 1 | 1 | 1 | 2 | $+1,907 | $93,263 | 1 | $+2,623 | $93,150 |
| 2026-03-24 | 3 | 3 | 3 | 3 | $-3,315 | $89,948 | 2 | $-2,349 | $90,801 |
| 2026-03-25 | 0 | 0 | 0 | 0 | $+0 | $89,948 no candidates (total=0, passed=0) | 0 | $+0 | $90,801 |
| 2026-03-26 | 13 | 13 | 5 | 2 | $-4,521 | $85,427 | 2 | $-4,565 | $86,236 |
| 2026-03-27 | 0 | 0 | 0 | 0 | $+0 | $85,427 no candidates (total=0, passed=0) | 0 | $+0 | $86,236 |

---

## Section 5: Trade-Level Detail

### Baseline (SQ-Only)

| Date | Symbol | Score | Entry | Exit | Reason | P&L |
|------|--------|-------|-------|------|--------|-----|
| 2026-01-08 | ACON | 9.9 | $8.04 | $8.32 | sq_target_hit | $+582 |
| 2026-01-08 | ACON | 18.5 | $8.21 | $7.95 | stop_hit | $-750 |
| 2026-01-12 | OM | 9.0 | $5.75 | $5.96 | bearish_engulfing_exit_full | $+1,043 |
| 2026-01-12 | OM | 7.0 | $6.04 | $6.35 | sq_target_hit | $+1,236 |
| 2026-01-12 | BDSX | 14.5 | $8.47 | $8.46 | bail_timer | $-20 |
| 2026-01-13 | AHMA | 12.5 | $9.65 | $9.59 | bearish_engulfing_exit_full | $-15 |
| 2026-01-13 | AHMA | 5.3 | $12.04 | $13.66 | sq_target_hit | $+4,389 |
| 2026-01-14 | ROLR | 11.0 | $4.04 | $5.28 | sq_target_hit | $+3,857 |
| 2026-01-14 | ROLR | 10.0 | $6.04 | $7.66 | sq_target_hit | $+5,026 |
| 2026-01-14 | ROLR | 14.5 | $9.33 | $16.43 | bearish_engulfing_exit_full | $+5,869 |
| 2026-01-15 | SPHL | 7.7 | $4.04 | $4.13 | sq_para_trail_exit | $+411 |
| 2026-01-15 | SPHL | 16.5 | $10.27 | $10.08 | bearish_engulfing_exit_full | $-312 |
| 2026-01-15 | BNKK | 6.2 | $5.04 | $5.13 | sq_para_trail_exit | $+411 |
| 2026-01-16 | VERO | 11.0 | $6.85 | $6.93 | sq_para_trail_exit | $+369 |
| 2026-01-16 | VERO | 6.2 | $6.85 | $7.51 | sq_target_hit | $+3,257 |
| 2026-01-20 | SHPH | 10.0 | $2.04 | $2.75 | sq_target_hit | $+6,288 |
| 2026-01-20 | SHPH | 10.0 | $3.04 | $3.04 | sq_para_trail_exit | $+0 |
| 2026-01-20 | SHPH | 17.0 | $3.32 | $3.03 | max_loss_hit | $-1,216 |
| 2026-01-20 | SHPH | 18.5 | $4.23 | $4.26 | bearish_engulfing_exit_full | $+115 |
| 2026-01-21 | SLGB | 10.0 | $3.04 | $4.00 | sq_target_hit | $+4,822 |
| 2026-01-21 | SLGB | 8.8 | $4.04 | $3.96 | sq_para_trail_exit | $-432 |
| 2026-01-22 | IOTR | 17.0 | $8.62 | $8.45 | bearish_engulfing_exit_full | $-575 |
| 2026-01-22 | SXTP | 17.0 | $7.29 | $6.87 | stop_hit | $-1,623 |
| 2026-01-22 | SXTP | 17.0 | $7.29 | $6.87 | stop_hit | $-1,623 |
| 2026-01-23 | SLE | 5.6 | $8.04 | $9.22 | sq_target_hit | $+6,421 |
| 2026-01-26 | BATL | 6.0 | $5.04 | $5.11 | sq_para_trail_exit | $+422 |
| 2026-01-27 | NUWE | 9.5 | $6.04 | $6.00 | sq_para_trail_exit | $-243 |
| 2026-01-27 | CYN | 15.0 | $3.67 | $3.48 | max_loss_hit | $-1,344 |
| 2026-01-30 | PMN | 11.5 | $19.54 | $20.27 | bearish_engulfing_exit_full | $+602 |
| 2026-01-30 | PMN | 18.5 | $19.54 | $19.18 | topping_wicky_exit_full | $-393 |
| 2026-02-03 | FIEE | 10.7 | $7.04 | $7.39 | sq_target_hit | $+2,095 |
| 2026-02-05 | RNAZ | 16.0 | $13.26 | $12.77 | topping_wicky_exit_full | $-532 |
| 2026-02-06 | FLYE | 11.0 | $6.04 | $7.12 | sq_target_hit | $+6,280 |
| 2026-02-17 | PLYX | 13.0 | $4.89 | $4.74 | bearish_engulfing_exit_full | $-290 |
| 2026-02-17 | PLYX | 13.0 | $4.57 | $4.70 | bearish_engulfing_exit_full | $+454 |
| 2026-02-17 | PLYX | 15.0 | $4.97 | $4.86 | bearish_engulfing_exit_full | $-321 |
| 2026-02-19 | RUBI | 17.0 | $3.15 | $3.10 | topping_wicky_exit_full | $-221 |
| 2026-02-19 | RUBI | 11.0 | $3.04 | $3.37 | sq_target_hit | $+3,532 |
| 2026-02-20 | CDIO | 15.5 | $3.07 | $3.00 | bearish_engulfing_exit_full | $-565 |
| 2026-02-20 | CDIO | 15.5 | $3.27 | $3.17 | bearish_engulfing_exit_full | $-606 |
| 2026-03-05 | GXAI | 8.2 | $2.04 | $2.22 | sq_target_hit | $+2,069 |
| 2026-03-05 | GXAI | 16.0 | $2.33 | $2.28 | bearish_engulfing_exit_full | $-637 |
| 2026-03-06 | CRE | 7.5 | $5.04 | $6.89 | sq_target_hit | $+11,827 |
| 2026-03-10 | VTAK | 9.0 | $2.34 | $2.26 | bearish_engulfing_exit_full | $-1,195 |
| 2026-03-12 | TLYS | 16.5 | $2.72 | $2.73 | topping_wicky_exit_full | $+170 |
| 2026-03-18 | ARTL | 13.5 | $7.62 | $7.92 | topping_wicky_exit_full | $+2,042 |
| 2026-03-19 | SUNE | 12.0 | $2.10 | $2.16 | sq_para_trail_exit | $+680 |
| 2026-03-23 | UGRO | 8.3 | $3.04 | $3.33 | sq_target_hit | $+2,646 |
| 2026-03-23 | UGRO | 8.0 | $3.39 | $3.28 | bearish_engulfing_exit_full | $-739 |
| 2026-03-24 | FEED | 17.5 | $2.41 | $2.39 | bearish_engulfing_exit_full | $-290 |
| 2026-03-24 | FEED | 17.5 | $2.41 | $2.39 | bearish_engulfing_exit_full | $-290 |
| 2026-03-24 | LICN | 17.0 | $5.68 | $4.80 | bail_timer | $-2,735 |
| 2026-03-26 | EEIQ | 18.0 | $8.01 | $7.22 | stop_hit | $-2,273 |
| 2026-03-26 | EEIQ | 16.5 | $7.96 | $7.39 | stop_hit | $-2,248 |

### V2 (SQ + MP V2)

| Date | Symbol | Score | Entry | Exit | Reason | P&L |
|------|--------|-------|-------|------|--------|-----|
| 2026-01-08 | ACON | 9.9 | $8.04 | $8.32 | sq_target_hit | $+582 |
| 2026-01-08 | ACON | 11.3 | $8.32 | $8.49 | sq_time_exit(5bars) | $+74 |
| 2026-01-12 | OM | 9.0 | $5.75 | $5.96 | bearish_engulfing_exit_full | $+1,072 |
| 2026-01-12 | OM | 7.0 | $6.04 | $6.35 | sq_target_hit | $+1,271 |
| 2026-01-12 | BDSX | 8.6 | $8.30 | $8.88 | sq_target_hit | $+700 |
| 2026-01-13 | AHMA | 12.5 | $9.65 | $9.59 | bearish_engulfing_exit_full | $-16 |
| 2026-01-13 | AHMA | 5.3 | $12.04 | $13.66 | sq_target_hit | $+4,608 |
| 2026-01-14 | ROLR | 11.0 | $4.04 | $5.28 | sq_target_hit | $+4,051 |
| 2026-01-14 | ROLR | 10.0 | $6.04 | $7.66 | sq_target_hit | $+5,279 |
| 2026-01-14 | ROLR | 14.5 | $9.33 | $11.54 | sq_target_hit | $+845 |
| 2026-01-15 | SPHL | 7.7 | $4.04 | $4.13 | sq_para_trail_exit | $+389 |
| 2026-01-15 | SPHL | 18.0 | $8.82 | $12.10 | sq_target_hit | $+508 |
| 2026-01-15 | BNKK | 6.2 | $5.04 | $5.13 | sq_para_trail_exit | $+389 |
| 2026-01-16 | VERO | 11.0 | $6.85 | $6.93 | sq_para_trail_exit | $+355 |
| 2026-01-16 | VERO | 6.2 | $6.85 | $7.51 | sq_target_hit | $+3,131 |
| 2026-01-20 | SHPH | 10.0 | $2.04 | $2.75 | sq_target_hit | $+6,047 |
| 2026-01-20 | SHPH | 10.0 | $3.04 | $3.04 | sq_para_trail_exit | $+0 |
| 2026-01-20 | SHPH | 17.0 | $3.32 | $3.03 | sq_max_loss_hit | $-292 |
| 2026-01-20 | SHPH | 18.5 | $4.23 | $4.26 | bearish_engulfing_exit_full | $+111 |
| 2026-01-21 | SLGB | 10.0 | $3.04 | $4.00 | sq_target_hit | $+4,707 |
| 2026-01-21 | SLGB | 8.8 | $4.04 | $3.96 | sq_para_trail_exit | $-422 |
| 2026-01-21 | SLGB | 9.8 | $3.85 | $3.84 | bail_timer | $-11 |
| 2026-01-22 | IOTR | 17.0 | $8.62 | $8.45 | bearish_engulfing_exit_full | $-561 |
| 2026-01-22 | SXTP | 17.0 | $7.29 | $6.92 | sq_trail_exit | $-349 |
| 2026-01-22 | SXTP | 17.0 | $7.29 | $6.87 | stop_hit | $-1,584 |
| 2026-01-23 | SLE | 5.6 | $8.04 | $9.22 | sq_target_hit | $+6,400 |
| 2026-01-26 | BATL | 6.0 | $5.04 | $5.11 | sq_para_trail_exit | $+420 |
| 2026-01-27 | NUWE | 9.5 | $6.04 | $6.00 | sq_para_trail_exit | $-242 |
| 2026-01-27 | CYN | 15.0 | $3.67 | $3.48 | max_loss_hit | $-1,339 |
| 2026-01-30 | PMN | 11.5 | $19.54 | $20.27 | bearish_engulfing_exit_full | $+600 |
| 2026-01-30 | PMN | 18.5 | $19.54 | $19.18 | topping_wicky_exit_full | $-392 |
| 2026-02-03 | FIEE | 10.7 | $7.04 | $7.39 | sq_target_hit | $+2,087 |
| 2026-02-05 | RNAZ | 16.0 | $13.26 | $12.77 | topping_wicky_exit_full | $-530 |
| 2026-02-06 | FLYE | 11.0 | $6.04 | $7.12 | sq_target_hit | $+6,257 |
| 2026-02-17 | PLYX | 13.0 | $4.89 | $4.74 | bearish_engulfing_exit_full | $-289 |
| 2026-02-17 | PLYX | 13.0 | $4.57 | $4.70 | bearish_engulfing_exit_full | $+453 |
| 2026-02-17 | PLYX | 15.0 | $4.97 | $4.86 | bearish_engulfing_exit_full | $-319 |
| 2026-02-19 | RUBI | 17.0 | $3.15 | $3.10 | topping_wicky_exit_full | $-220 |
| 2026-02-19 | RUBI | 11.0 | $3.04 | $3.37 | sq_target_hit | $+3,518 |
| 2026-02-20 | CDIO | 15.5 | $3.07 | $2.96 | sq_max_loss_hit | $-221 |
| 2026-02-20 | CDIO | 15.5 | $3.27 | $3.17 | bearish_engulfing_exit_full | $-604 |
| 2026-03-05 | GXAI | 8.2 | $2.04 | $2.22 | sq_target_hit | $+2,070 |
| 2026-03-05 | GXAI | 16.0 | $2.33 | $2.21 | sq_max_loss_hit | $-366 |
| 2026-03-06 | CRE | 7.5 | $5.04 | $6.89 | sq_target_hit | $+11,881 |
| 2026-03-10 | VTAK | 9.0 | $2.34 | $2.26 | bearish_engulfing_exit_full | $-1,200 |
| 2026-03-12 | TLYS | 16.5 | $2.72 | $2.73 | topping_wicky_exit_full | $+171 |
| 2026-03-18 | ARTL | 13.5 | $7.62 | $8.26 | sq_target_hit | $+834 |
| 2026-03-19 | SUNE | 12.0 | $2.10 | $2.16 | sq_para_trail_exit | $+674 |
| 2026-03-23 | UGRO | 8.3 | $3.04 | $3.33 | sq_target_hit | $+2,623 |
| 2026-03-24 | FEED | 17.5 | $2.41 | $2.39 | bearish_engulfing_exit_full | $-290 |
| 2026-03-24 | ELAB | 15.0 | $5.40 | $5.17 | max_loss_hit | $-2,059 |
| 2026-03-26 | EEIQ | 18.0 | $8.01 | $7.22 | stop_hit | $-2,295 |
| 2026-03-26 | EEIQ | 16.5 | $7.96 | $7.39 | stop_hit | $-2,270 |

---

## Section 6: Exit Reason Distribution

### Baseline (SQ-Only)
| Exit Reason | Count | Total P&L | Avg P&L |
|-------------|-------|-----------|---------|
| bearish_engulfing_exit_full | 17 | $+2,248 | $+132 |
| sq_target_hit | 15 | $+64,327 | $+4,288 |
| sq_para_trail_exit | 8 | $+1,618 | $+202 |
| stop_hit | 5 | $-8,517 | $-1,703 |
| topping_wicky_exit_full | 5 | $+1,066 | $+213 |
| bail_timer | 2 | $-2,755 | $-1,378 |
| max_loss_hit | 2 | $-2,560 | $-1,280 |

### V2 (SQ + MP V2)
| Exit Reason | Count | Total P&L | Avg P&L |
|-------------|-------|-----------|---------|
| sq_target_hit | 19 | $+67,399 | $+3,547 |
| bearish_engulfing_exit_full | 11 | $-1,043 | $-95 |
| sq_para_trail_exit | 8 | $+1,563 | $+195 |
| topping_wicky_exit_full | 4 | $-971 | $-243 |
| sq_max_loss_hit | 3 | $-879 | $-293 |
| stop_hit | 3 | $-6,149 | $-2,050 |
| max_loss_hit | 2 | $-3,398 | $-1,699 |
| sq_time_exit(5bars) | 1 | $+74 | $+74 |
| bail_timer | 1 | $-11 | $-11 |
| sq_trail_exit | 1 | $-349 | $-349 |

## Section 6b: Head-to-Head Trade Comparison

Trades on same date + symbol in both configs:

| Date | Symbol | Baseline P&L | V2 P&L | Delta | Baseline Exit | V2 Exit |
|------|--------|-------------|--------|-------|---------------|---------|
| 2026-01-08 | ACON | $-168 | $+656 | $+824 | sq_target_hit, stop_hit | sq_target_hit, sq_time_exit(5bars) |
| 2026-01-12 | BDSX | $-20 | $+700 | $+720 | bail_timer | sq_target_hit |
| 2026-01-12 | OM | $+2,279 | $+2,343 | $+64 | bearish_engulfing_exit_full, sq_target_hit | bearish_engulfing_exit_full, sq_target_hit |
| 2026-01-13 | AHMA | $+4,374 | $+4,592 | $+218 | bearish_engulfing_exit_full, sq_target_hit | bearish_engulfing_exit_full, sq_target_hit |
| 2026-01-14 | ROLR | $+14,752 | $+10,175 | $-4,577 | sq_target_hit, sq_target_hit, bearish_engulfing_exit_full | sq_target_hit, sq_target_hit, sq_target_hit |
| 2026-01-15 | BNKK | $+411 | $+389 | $-22 | sq_para_trail_exit | sq_para_trail_exit |
| 2026-01-15 | SPHL | $+99 | $+897 | $+798 | sq_para_trail_exit, bearish_engulfing_exit_full | sq_para_trail_exit, sq_target_hit |
| 2026-01-16 | VERO | $+3,626 | $+3,486 | $-140 | sq_para_trail_exit, sq_target_hit | sq_para_trail_exit, sq_target_hit |
| 2026-01-20 | SHPH | $+5,187 | $+5,866 | $+679 | sq_target_hit, sq_para_trail_exit, max_loss_hit, bearish_engulfing_exit_full | sq_target_hit, sq_para_trail_exit, sq_max_loss_hit, bearish_engulfing_exit_full |
| 2026-01-21 | SLGB | $+4,390 | $+4,274 | $-116 | sq_target_hit, sq_para_trail_exit | sq_target_hit, sq_para_trail_exit, bail_timer |
| 2026-01-22 | IOTR | $-575 | $-561 | $+14 | bearish_engulfing_exit_full | bearish_engulfing_exit_full |
| 2026-01-22 | SXTP | $-3,246 | $-1,933 | $+1,313 | stop_hit, stop_hit | sq_trail_exit, stop_hit |
| 2026-01-23 | SLE | $+6,421 | $+6,400 | $-21 | sq_target_hit | sq_target_hit |
| 2026-01-26 | BATL | $+422 | $+420 | $-2 | sq_para_trail_exit | sq_para_trail_exit |
| 2026-01-27 | CYN | $-1,344 | $-1,339 | $+5 | max_loss_hit | max_loss_hit |
| 2026-01-27 | NUWE | $-243 | $-242 | $+1 | sq_para_trail_exit | sq_para_trail_exit |
| 2026-01-30 | PMN | $+209 | $+208 | $-1 | bearish_engulfing_exit_full, topping_wicky_exit_full | bearish_engulfing_exit_full, topping_wicky_exit_full |
| 2026-02-03 | FIEE | $+2,095 | $+2,087 | $-8 | sq_target_hit | sq_target_hit |
| 2026-02-05 | RNAZ | $-532 | $-530 | $+2 | topping_wicky_exit_full | topping_wicky_exit_full |
| 2026-02-06 | FLYE | $+6,280 | $+6,257 | $-23 | sq_target_hit | sq_target_hit |
| 2026-02-17 | PLYX | $-157 | $-155 | $+2 | bearish_engulfing_exit_full, bearish_engulfing_exit_full, bearish_engulfing_exit_full | bearish_engulfing_exit_full, bearish_engulfing_exit_full, bearish_engulfing_exit_full |
| 2026-02-19 | RUBI | $+3,311 | $+3,298 | $-13 | topping_wicky_exit_full, sq_target_hit | topping_wicky_exit_full, sq_target_hit |
| 2026-02-20 | CDIO | $-1,171 | $-825 | $+346 | bearish_engulfing_exit_full, bearish_engulfing_exit_full | sq_max_loss_hit, bearish_engulfing_exit_full |
| 2026-03-05 | GXAI | $+1,432 | $+1,704 | $+272 | sq_target_hit, bearish_engulfing_exit_full | sq_target_hit, sq_max_loss_hit |
| 2026-03-06 | CRE | $+11,827 | $+11,881 | $+54 | sq_target_hit | sq_target_hit |
| 2026-03-10 | VTAK | $-1,195 | $-1,200 | $-5 | bearish_engulfing_exit_full | bearish_engulfing_exit_full |
| 2026-03-12 | TLYS | $+170 | $+171 | $+1 | topping_wicky_exit_full | topping_wicky_exit_full |
| 2026-03-18 | ARTL | $+2,042 | $+834 | $-1,208 | topping_wicky_exit_full | sq_target_hit |
| 2026-03-19 | SUNE | $+680 | $+674 | $-6 | sq_para_trail_exit | sq_para_trail_exit |
| 2026-03-23 | UGRO | $+1,907 | $+2,623 | $+716 | sq_target_hit, bearish_engulfing_exit_full | sq_target_hit |
| 2026-03-24 | FEED | $-580 | $-290 | $+290 | bearish_engulfing_exit_full, bearish_engulfing_exit_full | bearish_engulfing_exit_full |
| 2026-03-26 | EEIQ | $-4,521 | $-4,565 | $-44 | stop_hit, stop_hit | stop_hit, stop_hit |

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

**2026-01-02**: 0 scanned → 0 passed filter → none selected
**2026-01-03**: 0 scanned → 0 passed filter → none selected
**2026-01-05**: 0 scanned → 0 passed filter → none selected
**2026-01-06**: 1 scanned → 1 passed → CYCN(vol=24,518,284)
**2026-01-07**: 0 scanned → 0 passed filter → none selected
**2026-01-08**: 1 scanned → 1 passed → ACON(vol=11,784,125)
**2026-01-09**: 2 scanned → 2 passed → KUST(vol=3,108,145), ICON(vol=3,982,030)
**2026-01-12**: 2 scanned → 2 passed → OM(vol=9,559,536), BDSX(vol=6,603,568)
**2026-01-13**: 3 scanned → 3 passed → IOTR(vol=12,847,145), AHMA(vol=14,958,906), BCTX(vol=2,768,739)
**2026-01-14**: 4 scanned → 4 passed → ROLR(vol=17,810,770), BEEM(vol=21,555,609), CMND(vol=753,435), MVO(vol=1,741,256)
**2026-01-15**: 4 scanned → 4 passed → SPHL(vol=28,802,736), BNKK(vol=34,912,388), CJMB(vol=24,916,150), AGPU(vol=1,417,444)
**2026-01-16**: 5 scanned → 5 passed → VERO(vol=177,545,815), LCFY(vol=17,084,453), ACCL(vol=12,207,399), BIYA(vol=6,025,767), TNMG(vol=7,779,900)
**2026-01-20**: 5 scanned → 5 passed → TWG(vol=20,256,874), SHPH(vol=58,513,550), BTTC(vol=36,881,033), IVF(vol=62,300,914), POLA(vol=6,495,307)
**2026-01-21**: 4 scanned → 4 passed → SLGB(vol=33,814,616), BOXL(vol=53,073,853), LSTA(vol=2,448,095), AQMS(vol=6,253,591)
**2026-01-22**: 2 scanned → 2 passed → IOTR(vol=21,000,221), SXTP(vol=71,255,485)
**2026-01-23**: 3 scanned → 3 passed → RVYL(vol=4,751,174), SLE(vol=2,323,965), BGL(vol=7,935,163)
**2026-01-26**: 3 scanned → 3 passed → BATL(vol=93,528,376), GXAI(vol=55,428,473), ARAI(vol=15,535,024)
**2026-01-27**: 5 scanned → 5 passed → NUWE(vol=46,133,979), HIND(vol=28,457,154), CYN(vol=40,720,913), NETG(vol=79,949), PHGE(vol=4,143,064)
**2026-01-28**: 2 scanned → 2 passed → MRNO(vol=30,841,530), AIMD(vol=16,568,995)
**2026-01-29**: 3 scanned → 3 passed → SER(vol=31,413,597), DCX(vol=12,413,258), ZSTK(vol=370,387)
**2026-01-30**: 2 scanned → 2 passed → PMN(vol=2,944,784), VIVS(vol=16,214,876)
**2026-02-02**: 3 scanned → 3 passed → SWVL(vol=23,542,960), CISS(vol=19,734,846), IPW(vol=2,147,509)
**2026-02-03**: 3 scanned → 3 passed → FATN(vol=26,103,089), FIEE(vol=825,963), NPT(vol=9,473,451)
**2026-02-04**: 1 scanned → 1 passed → CIGL(vol=6,485,980)
**2026-02-05**: 1 scanned → 1 passed → RNAZ(vol=4,679,443)
**2026-02-06**: 1 scanned → 1 passed → FLYE(vol=3,438,653)
**2026-02-09**: 0 scanned → 0 passed filter → none selected
**2026-02-10**: 1 scanned → 1 passed → SPOG(vol=409,845)
**2026-02-11**: 1 scanned → 1 passed → ELAB(vol=2,451,975)
**2026-02-12**: 0 scanned → 0 passed filter → none selected
**2026-02-13**: 1 scanned → 1 passed → RAIN(vol=66,996)
**2026-02-17**: 2 scanned → 2 passed → OBAI(vol=12,123,021), PLYX(vol=7,806,455)
**2026-02-18**: 1 scanned → 1 passed → BENF(vol=5,179,374)
**2026-02-19**: 1 scanned → 1 passed → RUBI(vol=35,276,105)
**2026-02-20**: 1 scanned → 1 passed → CDIO(vol=18,641,414)
**2026-02-23**: 0 scanned → 0 passed filter → none selected
**2026-02-24**: 0 scanned → 0 passed filter → none selected
**2026-02-25**: 0 scanned → 0 passed filter → none selected
**2026-02-26**: 0 scanned → 0 passed filter → none selected
**2026-02-27**: 1 scanned → 1 passed → KORE(vol=1,127,119)
**2026-03-02**: 3 scanned → 3 passed → TMDE(vol=54,683,505), RBNE(vol=6,840,539), RLYB(vol=839,558)
**2026-03-03**: 0 scanned → 0 passed filter → none selected
**2026-03-04**: 1 scanned → 1 passed → ADVB(vol=3,551,793)
**2026-03-05**: 2 scanned → 2 passed → MTEK(vol=12,603,353), GXAI(vol=63,122,380)
**2026-03-06**: 2 scanned → 2 passed → CRE(vol=9,367,330), IBG(vol=7,448,492)
**2026-03-09**: 1 scanned → 1 passed → AGH(vol=13,109,263)
**2026-03-10**: 2 scanned → 2 passed → VTAK(vol=29,135,478), INKT(vol=3,242,228)
**2026-03-11**: 1 scanned → 1 passed → SXTP(vol=8,487,387)
**2026-03-12**: 2 scanned → 2 passed → POLA(vol=17,478,820), TLYS(vol=14,927,080)
**2026-03-13**: 1 scanned → 1 passed → EDHL(vol=2,414,053)
**2026-03-16**: 0 scanned → 0 passed filter → none selected
**2026-03-17**: 0 scanned → 0 passed filter → none selected
**2026-03-18**: 2 scanned → 2 passed → ARTL(vol=12,379,125), ZENA(vol=4,680,843)
**2026-03-19**: 4 scanned → 4 passed → CHNR(vol=16,881,783), SUNE(vol=14,392,765), SER(vol=30,171,461), DLTH(vol=3,070,308)
**2026-03-20**: 0 scanned → 0 passed filter → none selected
**2026-03-23**: 1 scanned → 1 passed → UGRO(vol=28,440,583)
**2026-03-24**: 3 scanned → 3 passed → FEED(vol=33,907,715), ELAB(vol=8,803,515), LICN(vol=112,527)
**2026-03-25**: 0 scanned → 0 passed filter → none selected
**2026-03-26**: 13 scanned → 13 passed → EEIQ(vol=112,623,435), FCHL(vol=46,804,609), NDLS(vol=1,672,264), AIFF(vol=109,781,455), FATN(vol=4,551,592)
**2026-03-27**: 0 scanned → 0 passed filter → none selected

---

## Section 9: Robustness Checks

### Config A
- P&L without top 3 winners: $+30,891
- Top 3 winners: $+24,536
- Longest consecutive losing streak (days): 2
- Win/loss count (excl breakeven): 27W / 26L

### Config B
- P&L without top 3 winners: $+31,698
- Top 3 winners: $+24,538
- Longest consecutive losing streak (days): 2
- Win/loss count (excl breakeven): 30W / 22L


---

## Section 10: Strategy Breakdown (MP vs Squeeze)

### Config A
| Strategy | Trades | Wins | Losses | Win Rate | Total P&L | Avg P&L |
|----------|--------|------|--------|----------|-----------|---------|
| Micro Pullback | 31 | 7 | 24 | 23% | $-10,518 | $-339 |
| Squeeze | 23 | 20 | 2 | 87% | $+65,945 | $+2,867 |

### Config B
| Strategy | Trades | Wins | Losses | Win Rate | Total P&L | Avg P&L |
|----------|--------|------|--------|----------|-----------|---------|
| Micro Pullback | 21 | 5 | 16 | 24% | $-11,572 | $-551 |
| Squeeze | 32 | 25 | 6 | 78% | $+67,808 | $+2,119 |

---

*Generated from YTD V2 backtest | Top-5 ranked, 5 trade cap, daily loss limit | Tick mode, Alpaca feed, dynamic sizing | Branch: v6-dynamic-sizing*