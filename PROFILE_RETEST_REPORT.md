# Profile System Retest Report
## Generated 2026-03-17

Period: January 2 - March 12, 2026 (49 trading days)
Starting Equity: $30,000
Tick Cache: Deterministic replay (240 pairs, 33.7M ticks)

**Purpose**: Test whether the old profile system was wrongly scrapped due to faulty backtest data.

---

## Section 1: 3-Way Comparison

| Metric | Config 1 (Current) | Config 2 (Profiles) | Config 3 (Full) |
|--------|-------------------|--------------------|--------------------|
| Final Equity | $36,467 | $37,310 | $37,310 |
| Total P&L | $+6,467 | $+7,310 | $+7,310 |
| Total Return | +21.6% | +24.4% | +24.4% |
| Total Trades | 28 | 28 | 28 |
| Win Rate | 10/28 (36%) | 10/28 (36%) | 10/28 (36%) |
| Avg Win | $+1,491 | $+1,488 | $+1,488 |
| Avg Loss | $-469 | $-421 | $-421 |
| Profit Factor | 1.77 | 1.97 | 1.97 |
| Max Drawdown $ | $6,760 | $5,876 | $5,876 |
| Max Drawdown % | 15.7% | 13.6% | 13.6% |
| Largest Win | $+8,039 | $+8,048 | $+8,048 |
| Largest Loss | $-1,067 | $-1,068 | $-1,068 |
| Avg Trades/Day | 0.6 | 0.6 | 0.6 |

**Config 1**: Flat dynamic risk (2.5% of equity, $250-$1500), no profiles, score gate OFF
**Config 2**: Profile A = 2.5% ($250-$1500), Profile B = A/3 capped at $250. No bail timer.
**Config 3**: Config 2 + bail timer (5m), giveback (20%/50%), warmup sizing (25% until $500)
**L2 note**: Profile B runs WITHOUT L2 (tick cache has trade data only, no book data)

---

## Section 2: Profile A vs B Breakdown

### Config 2

| Metric | Profile A (Micro-Float) | Profile B (Mid-Float) |
|--------|------------------------|-----------------------|
| Trades | 25 | 3 |
| P&L | $+7,603 | $-293 |
| Win Rate | 9/25 (36%) | 1/3 (33%) |
| Avg P&L/Trade | $+304 | $-98 |

### Config 3

| Metric | Profile A (Micro-Float) | Profile B (Mid-Float) |
|--------|------------------------|-----------------------|
| Trades | 25 | 3 |
| P&L | $+7,603 | $-293 |
| Win Rate | 9/25 (36%) | 1/3 (33%) |
| Avg P&L/Trade | $+304 | $-98 |


---

## Section 3: Daily Equity Curve

| Date | C1 Equity | C1 P&L | C2 Equity | C2 P&L | C3 Equity | C3 P&L |
|------|-----------|--------|-----------|--------|-----------|--------|
| 2026-01-02 | $30,784 | $+784 | $30,784 | $+784 | $30,784 | $+784 |
| 2026-01-03 | $30,784 | $+0 | $30,784 | $+0 | $30,784 | $+0 |
| 2026-01-05 | $30,784 | $+0 | $30,784 | $+0 | $30,784 | $+0 |
| 2026-01-06 | $30,784 | $+0 | $30,784 | $+0 | $30,784 | $+0 |
| 2026-01-07 | $30,498 | $-286 | $30,498 | $-286 | $30,498 | $-286 |
| 2026-01-08 | $31,422 | $+924 | $31,422 | $+924 | $31,422 | $+924 |
| 2026-01-09 | $31,422 | $+0 | $31,422 | $+0 | $31,422 | $+0 |
| 2026-01-12 | $31,819 | $+397 | $31,819 | $+397 | $31,819 | $+397 |
| 2026-01-13 | $31,804 | $-15 | $31,804 | $-15 | $31,804 | $-15 |
| 2026-01-14 | $34,382 | $+2,578 | $34,382 | $+2,578 | $34,382 | $+2,578 |
| 2026-01-15 | $35,118 | $+736 | $35,119 | $+737 | $35,119 | $+737 |
| 2026-01-16 | $43,157 | $+8,039 | $43,167 | $+8,048 | $43,167 | $+8,048 |
| 2026-01-20 | $43,157 | $+0 | $43,167 | $+0 | $43,167 | $+0 |
| 2026-01-21 | $42,706 | $-451 | $42,716 | $-451 | $42,716 | $-451 |
| 2026-01-22 | $40,572 | $-2,134 | $40,580 | $-2,136 | $40,580 | $-2,136 |
| 2026-01-23 | $39,764 | $-808 | $39,963 | $-617 | $39,963 | $-617 |
| 2026-01-26 | $39,764 | $+0 | $39,963 | $+0 | $39,963 | $+0 |
| 2026-01-27 | $38,332 | $-1,432 | $39,273 | $-690 | $39,273 | $-690 |
| 2026-01-28 | $38,332 | $+0 | $39,273 | $+0 | $39,273 | $+0 |
| 2026-01-29 | $38,332 | $+0 | $39,273 | $+0 | $39,273 | $+0 |
| 2026-01-30 | $38,679 | $+347 | $39,629 | $+356 | $39,629 | $+356 |
| 2026-02-02 | $38,679 | $+0 | $39,629 | $+0 | $39,629 | $+0 |
| 2026-02-03 | $38,679 | $+0 | $39,629 | $+0 | $39,629 | $+0 |
| 2026-02-04 | $38,679 | $+0 | $39,629 | $+0 | $39,629 | $+0 |
| 2026-02-05 | $38,679 | $+0 | $39,629 | $+0 | $39,629 | $+0 |
| 2026-02-06 | $38,746 | $+67 | $39,698 | $+69 | $39,698 | $+69 |
| 2026-02-09 | $38,746 | $+0 | $39,698 | $+0 | $39,698 | $+0 |
| 2026-02-10 | $38,746 | $+0 | $39,698 | $+0 | $39,698 | $+0 |
| 2026-02-11 | $38,746 | $+0 | $39,698 | $+0 | $39,698 | $+0 |
| 2026-02-12 | $38,746 | $+0 | $39,698 | $+0 | $39,698 | $+0 |
| 2026-02-13 | $38,746 | $+0 | $39,698 | $+0 | $39,698 | $+0 |
| 2026-02-17 | $38,595 | $-151 | $39,543 | $-155 | $39,543 | $-155 |
| 2026-02-18 | $38,595 | $+0 | $39,543 | $+0 | $39,543 | $+0 |
| 2026-02-19 | $38,480 | $-115 | $39,425 | $-118 | $39,425 | $-118 |
| 2026-02-20 | $38,320 | $-160 | $39,261 | $-164 | $39,261 | $-164 |
| 2026-02-23 | $38,102 | $-218 | $39,038 | $-223 | $39,038 | $-223 |
| 2026-02-24 | $38,102 | $+0 | $39,038 | $+0 | $39,038 | $+0 |
| 2026-02-25 | $38,102 | $+0 | $39,038 | $+0 | $39,038 | $+0 |
| 2026-02-26 | $38,102 | $+0 | $39,038 | $+0 | $39,038 | $+0 |
| 2026-02-27 | $38,102 | $+0 | $39,038 | $+0 | $39,038 | $+0 |
| 2026-03-02 | $38,102 | $+0 | $39,038 | $+0 | $39,038 | $+0 |
| 2026-03-03 | $38,102 | $+0 | $39,038 | $+0 | $39,038 | $+0 |
| 2026-03-04 | $38,102 | $+0 | $39,038 | $+0 | $39,038 | $+0 |
| 2026-03-05 | $38,102 | $+0 | $39,038 | $+0 | $39,038 | $+0 |
| 2026-03-06 | $37,522 | $-580 | $38,443 | $-595 | $38,443 | $-595 |
| 2026-03-09 | $37,522 | $+0 | $38,443 | $+0 | $38,443 | $+0 |
| 2026-03-10 | $36,397 | $-1,125 | $37,291 | $-1,152 | $37,291 | $-1,152 |
| 2026-03-11 | $36,397 | $+0 | $37,291 | $+0 | $37,291 | $+0 |
| 2026-03-12 | $36,467 | $+70 | $37,310 | $+19 | $37,310 | $+19 |

---

## Section 4: Trade-Level Detail

### Config 2

| Date | Symbol | Profile | Risk | Entry | Exit | Reason | P&L | R-Mult |
|------|--------|---------|------|-------|------|--------|-----|--------|
| 2026-01-02 | SNSE | A | $750 | $12.68 | $13.14 | bearish_engulfing_exit_full | $+784 | +1.0R |
| 2026-01-07 | NVVE | A | $769 | $3.74 | $3.61 | bearish_engulfing_exit_full | $-286 | -0.4R |
| 2026-01-08 | ACON | A | $762 | $8.21 | $7.95 | stop_hit | $-762 | -1.0R |
| 2026-01-08 | SXTC | A | $762 | $3.21 | $3.46 | bearish_engulfing_exit_full | $+1,058 | +1.4R |
| 2026-01-08 | SXTC | A | $762 | $3.56 | $3.78 | bearish_engulfing_exit_full | $+628 | +0.8R |
| 2026-01-12 | BDSX | A | $786 | $8.47 | $8.66 | bearish_engulfing_exit_full | $+397 | +0.5R |
| 2026-01-13 | AHMA | A | $795 | $9.65 | $9.59 | bearish_engulfing_exit_full | $-15 | -0.0R |
| 2026-01-14 | ROLR | A | $794 | $9.33 | $12.90 | topping_wicky_exit_full | $+2,578 | +3.2R |
| 2026-01-15 | SPHL | A | $859 | $10.27 | $10.08 | bearish_engulfing_exit_full | $-209 | -0.2R |
| 2026-01-15 | AGPU | A | $860 | $8.32 | $8.65 | topping_wicky_exit_full | $+946 | +1.1R |
| 2026-01-16 | VERO | A | $878 | $3.58 | $4.68 | topping_wicky_exit_full | $+8,048 | +9.2R |
| 2026-01-21 | GITS | A | $1079 | $2.48 | $2.40 | bearish_engulfing_exit_full | $-451 | -0.4R |
| 2026-01-22 | IOTR | A | $1068 | $8.62 | $8.14 | stop_hit | $-1,068 | -1.0R |
| 2026-01-22 | SXTP | A | $1068 | $7.29 | $6.87 | stop_hit | $-1,068 | -1.0R |
| 2026-01-23 | MOVE | A | $1014 | $19.92 | $19.49 | bearish_engulfing_exit_full | $-555 | -0.5R |
| 2026-01-23 | AUST | B | $250 | $2.37 | $2.35 | topping_wicky_exit_full | $-62 | -0.2R |
| 2026-01-27 | XHLD | A | $999 | $2.55 | $2.37 | topping_wicky_exit_full | $-440 | -0.4R |
| 2026-01-27 | CYN | B | $250 | $3.67 | $3.43 | stop_hit | $-250 | -1.0R |
| 2026-01-30 | PMN | A | $982 | $19.54 | $20.27 | bearish_engulfing_exit_full | $+356 | +0.4R |
| 2026-02-06 | WHLR | A | $990 | $3.12 | $3.18 | topping_wicky_exit_full | $+69 | +0.1R |
| 2026-02-17 | PLYX | A | $992 | $4.89 | $4.74 | bearish_engulfing_exit_full | $-155 | -0.3R |
| 2026-02-19 | RUBI | A | $989 | $3.15 | $3.10 | topping_wicky_exit_full | $-118 | -0.2R |
| 2026-02-20 | ABTS | A | $986 | $4.41 | $4.31 | bearish_engulfing_exit_full | $-164 | -0.3R |
| 2026-02-23 | GNPX | A | $981 | $2.23 | $2.19 | bearish_engulfing_exit_full | $-223 | -0.5R |
| 2026-03-06 | QCLS | A | $976 | $4.72 | $4.58 | bearish_engulfing_exit_full | $-595 | -0.6R |
| 2026-03-10 | VTAK | A | $961 | $2.34 | $2.26 | bearish_engulfing_exit_full | $-512 | -0.5R |
| 2026-03-10 | INKT | A | $961 | $20.02 | $18.80 | bearish_engulfing_exit_full | $-640 | -0.7R |
| 2026-03-12 | TLYS | B | $250 | $2.72 | $2.73 | topping_wicky_exit_full | $+19 | +0.1R |

### Config 3

| Date | Symbol | Profile | Risk | Entry | Exit | Reason | P&L | R-Mult |
|------|--------|---------|------|-------|------|--------|-----|--------|
| 2026-01-02 | SNSE | A | $750 | $12.68 | $13.14 | bearish_engulfing_exit_full | $+784 | +1.0R |
| 2026-01-07 | NVVE | A | $769 | $3.74 | $3.61 | bearish_engulfing_exit_full | $-286 | -0.4R |
| 2026-01-08 | ACON | A | $762 | $8.21 | $7.95 | stop_hit | $-762 | -1.0R |
| 2026-01-08 | SXTC | A | $762 | $3.21 | $3.46 | bearish_engulfing_exit_full | $+1,058 | +1.4R |
| 2026-01-08 | SXTC | A | $762 | $3.56 | $3.78 | bearish_engulfing_exit_full | $+628 | +0.8R |
| 2026-01-12 | BDSX | A | $786 | $8.47 | $8.66 | bearish_engulfing_exit_full | $+397 | +0.5R |
| 2026-01-13 | AHMA | A | $795 | $9.65 | $9.59 | bearish_engulfing_exit_full | $-15 | -0.0R |
| 2026-01-14 | ROLR | A | $794 | $9.33 | $12.90 | topping_wicky_exit_full | $+2,578 | +3.2R |
| 2026-01-15 | SPHL | A | $859 | $10.27 | $10.08 | bearish_engulfing_exit_full | $-209 | -0.2R |
| 2026-01-15 | AGPU | A | $860 | $8.32 | $8.65 | topping_wicky_exit_full | $+946 | +1.1R |
| 2026-01-16 | VERO | A | $878 | $3.58 | $4.68 | topping_wicky_exit_full | $+8,048 | +9.2R |
| 2026-01-21 | GITS | A | $1079 | $2.48 | $2.40 | bearish_engulfing_exit_full | $-451 | -0.4R |
| 2026-01-22 | IOTR | A | $1068 | $8.62 | $8.14 | stop_hit | $-1,068 | -1.0R |
| 2026-01-22 | SXTP | A | $1068 | $7.29 | $6.87 | stop_hit | $-1,068 | -1.0R |
| 2026-01-23 | MOVE | A | $1014 | $19.92 | $19.49 | bearish_engulfing_exit_full | $-555 | -0.5R |
| 2026-01-23 | AUST | B | $250 | $2.37 | $2.35 | topping_wicky_exit_full | $-62 | -0.2R |
| 2026-01-27 | XHLD | A | $999 | $2.55 | $2.37 | topping_wicky_exit_full | $-440 | -0.4R |
| 2026-01-27 | CYN | B | $250 | $3.67 | $3.43 | stop_hit | $-250 | -1.0R |
| 2026-01-30 | PMN | A | $982 | $19.54 | $20.27 | bearish_engulfing_exit_full | $+356 | +0.4R |
| 2026-02-06 | WHLR | A | $990 | $3.12 | $3.18 | topping_wicky_exit_full | $+69 | +0.1R |
| 2026-02-17 | PLYX | A | $992 | $4.89 | $4.74 | bearish_engulfing_exit_full | $-155 | -0.3R |
| 2026-02-19 | RUBI | A | $989 | $3.15 | $3.10 | topping_wicky_exit_full | $-118 | -0.2R |
| 2026-02-20 | ABTS | A | $986 | $4.41 | $4.31 | bearish_engulfing_exit_full | $-164 | -0.3R |
| 2026-02-23 | GNPX | A | $981 | $2.23 | $2.19 | bearish_engulfing_exit_full | $-223 | -0.5R |
| 2026-03-06 | QCLS | A | $976 | $4.72 | $4.58 | bearish_engulfing_exit_full | $-595 | -0.6R |
| 2026-03-10 | VTAK | A | $961 | $2.34 | $2.26 | bearish_engulfing_exit_full | $-512 | -0.5R |
| 2026-03-10 | INKT | A | $961 | $20.02 | $18.80 | bearish_engulfing_exit_full | $-640 | -0.7R |
| 2026-03-12 | TLYS | B | $250 | $2.72 | $2.73 | topping_wicky_exit_full | $+19 | +0.1R |


---

## Section 5: Key Divergences

### Stocks treated differently by profile system

**Profile B stocks (mid-float, reduced risk):**
- 2026-01-23 AUST: risk capped, P&L $-62
- 2026-01-27 CYN: risk capped, P&L $-250
- 2026-03-12 TLYS: risk capped, P&L $+19
- **Total B-stock P&L**: $-293

---

## Section 6: The Verdict

| System | P&L | Return | Win Rate | Max DD |
|--------|-----|--------|----------|--------|
| Current (no profiles) | $+6,467 | +21.6% | 10/28 (36%) | $6,760 |
| Profiles Validated | $+7,310 | +24.4% | 10/28 (36%) | $5,876 |
| Profiles Full | $+7,310 | +24.4% | 10/28 (36%) | $5,876 |

**Profile system vs Current**: $+843 (Config 2), $+843 (Config 3)

**OUTCOME 1**: Profile system is significantly better. Consider re-integration.

---

*Generated from profile retest backtest | Cached tick data (deterministic) | Branch: v6-dynamic-sizing*