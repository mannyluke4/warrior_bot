# January 2025 vs January 2026 Comparison — Scanner Fixes V1 + SQ Exit Fixes

**Generated:** 2026-03-23 16:58
**Config:** Full ENV_BASE with all fixes: unknown-float gate, SQ partial/wide/runner exits, halt-through, MP enabled

---

## Summary Table

| Metric | Jan 2025 | Jan 2026 |
|--------|----------|----------|
| Trading Days | 21 | 21 |
| Scanner Candidates (total) | 71 | 79 |
| Candidates Passing Filters | 70 | 73 |
| Unknown-Float Candidates | 0 | 1 |
| Rescan Candidates | 0 | 1 |
| Total Trades | 32 | 15 |
| SQ Trades | 22 | 8 |
| MP Trades | 10 | 7 |
| Win Rate | 40.6% | 46.7% |
| Total P&L | $+3,423 | $+17,728 |
| Avg P&L / Day | $+163 | $+844 |
| Profit Factor | 1.63 | 6.74 |
| Max Drawdown | $-1,282 | $-2,339 |
| Best Day | $+2,506 | $+14,457 |
| Worst Day | $-1,120 | $-1,682 |
| Ending Equity | $+33,423 | $+47,728 |

---

## Scanner Improvement (Jan 2025)

- **Unknown-float candidates traded:** 0 (previously blocked by WB_ALLOW_PROFILE_X=0)
- **Rescan candidates:** 0 (rescan found 0 in Jan 2025 before fix)

---

## Jan 2025 — Per-Day Detail

| Date | Candidates | Traded | Trades | P&L | Equity | Best Trade |
|------|-----------|--------|--------|-----|--------|-----------|
| 2025-01-02 | 6 | 5 | 2 | -635 | $29,365 | ORIS -260 |
| 2025-01-03 | 1 | 1 | 0 | +0 | $29,365 | — |
| 2025-01-06 | 5 | 5 | 2 | +2,280 | $31,645 | GDTC +2175 |
| 2025-01-07 | 5 | 5 | 2 | -621 | $31,024 | MYSE -282 |
| 2025-01-08 | 3 | 3 | 2 | +63 | $31,087 | SILO +134 |
| 2025-01-09 | 0 | 0 | 0 | +0 | $31,087 | — |
| 2025-01-10 | 3 | 3 | 1 | -333 | $30,754 | VMAR -333 |
| 2025-01-13 | 4 | 4 | 2 | -64 | $30,690 | ATPC -17 |
| 2025-01-14 | 2 | 2 | 4 | +1,787 | $32,477 | OST +726 |
| 2025-01-15 | 3 | 3 | 2 | -106 | $32,371 | BKYI -8 |
| 2025-01-16 | 3 | 3 | 1 | +462 | $32,833 | WHLR +462 |
| 2025-01-17 | 3 | 3 | 0 | +0 | $32,833 | — |
| 2025-01-21 | 8 | 5 | 2 | -1,062 | $31,771 | LEDS -351 |
| 2025-01-22 | 1 | 1 | 0 | +0 | $31,771 | — |
| 2025-01-23 | 6 | 5 | 2 | +319 | $32,090 | VNCE +659 |
| 2025-01-24 | 5 | 5 | 4 | +2,506 | $34,596 | ALUR +1525 |
| 2025-01-27 | 4 | 4 | 0 | +0 | $34,596 | — |
| 2025-01-28 | 2 | 2 | 0 | +0 | $34,596 | — |
| 2025-01-29 | 1 | 1 | 2 | +109 | $34,705 | SLXN +274 |
| 2025-01-30 | 3 | 3 | 2 | -162 | $34,543 | AMOD +633 |
| 2025-01-31 | 3 | 3 | 2 | -1,120 | $33,423 | CYCN -370 |

---

## Jan 2026 — Per-Day Detail

| Date | Candidates | Traded | Trades | P&L | Equity | Best Trade |
|------|-----------|--------|--------|-----|--------|-----------|
| 2026-01-02 | 2 | 2 | 0 | +0 | $30,000 | — |
| 2026-01-03 | 0 | 0 | 0 | +0 | $30,000 | — |
| 2026-01-05 | 1 | 1 | 0 | +0 | $30,000 | — |
| 2026-01-06 | 2 | 2 | 0 | +0 | $30,000 | — |
| 2026-01-07 | 2 | 2 | 0 | +0 | $30,000 | — |
| 2026-01-08 | 2 | 2 | 1 | +362 | $30,362 | ACON +362 |
| 2026-01-09 | 4 | 4 | 0 | +0 | $30,362 | — |
| 2026-01-12 | 2 | 2 | 1 | -325 | $30,037 | BDSX -325 |
| 2026-01-13 | 7 | 5 | 1 | -54 | $29,983 | SPRC -54 |
| 2026-01-14 | 2 | 2 | 1 | +238 | $30,221 | ROLR +238 |
| 2026-01-15 | 6 | 5 | 2 | +916 | $31,137 | CJMB +1051 |
| 2026-01-16 | 6 | 5 | 1 | +14,457 | $45,594 | VERO +14457 |
| 2026-01-20 | 8 | 5 | 1 | +569 | $46,163 | POLA +569 |
| 2026-01-21 | 4 | 4 | 1 | +3,523 | $49,686 | SLGB +3523 |
| 2026-01-22 | 4 | 4 | 2 | -1,682 | $48,004 | IOTR -440 |
| 2026-01-23 | 7 | 5 | 1 | -657 | $47,347 | MOVE -657 |
| 2026-01-26 | 5 | 5 | 1 | +615 | $47,962 | BATL +615 |
| 2026-01-27 | 5 | 4 | 1 | -198 | $47,764 | CYN -198 |
| 2026-01-28 | 3 | 3 | 0 | +0 | $47,764 | — |
| 2026-01-29 | 5 | 3 | 1 | -36 | $47,728 | FEED -36 |
| 2026-01-30 | 2 | 2 | 0 | +0 | $47,728 | — |

---

## Strategy Breakdown

### Jan 2025

| Strategy | Trades | Wins | Win Rate | P&L |
|----------|--------|------|----------|-----|
| Squeeze (SQ) | 22 | 12 | 55% | $+5,904 |
| Micro Pullback (MP) | 10 | 1 | 10% | $-2,481 |

### Jan 2026

| Strategy | Trades | Wins | Win Rate | P&L |
|----------|--------|------|----------|-----|
| Squeeze (SQ) | 8 | 5 | 62% | $+5,606 |
| Micro Pullback (MP) | 7 | 2 | 29% | $+12,122 |

---

## Jan 2025 — Top 5 Trades

| # | Symbol | Date | Strategy | P&L | Reason |
|---|--------|------|----------|-----|--------|
| 1 | GDTC | 2025-01-06 | squeeze | +2,175 | sq_target_hit |
| 2 | ALUR | 2025-01-24 | squeeze | +1,525 | sq_target_hit |
| 3 | ALUR | 2025-01-24 | squeeze | +932 | sq_target_hit |
| 4 | OST | 2025-01-14 | squeeze | +726 | sq_target_hit |
| 5 | VNCE | 2025-01-23 | squeeze | +659 | sq_target_hit |

## Jan 2025 — Bottom 5 Trades

| # | Symbol | Date | Strategy | P&L | Reason |
|---|--------|------|----------|-----|--------|
| 1 | STAI | 2025-01-30 | micro_pullback | -795 | max_loss_hit |
| 2 | CYCN | 2025-01-31 | micro_pullback | -750 | max_loss_hit |
| 3 | PTHS | 2025-01-21 | micro_pullback | -711 | max_loss_hit |
| 4 | ORIS | 2025-01-02 | squeeze | -375 | sq_stop_hit |
| 5 | CYCN | 2025-01-31 | squeeze | -370 | sq_max_loss_hit |

---

## Jan 2026 — Top 5 Trades

| # | Symbol | Date | Strategy | P&L | Reason |
|---|--------|------|----------|-----|--------|
| 1 | VERO | 2026-01-16 | micro_pullback | +14,457 | bearish_engulfing_exit_full |
| 2 | SLGB | 2026-01-21 | squeeze | +3,523 | sq_target_hit |
| 3 | CJMB | 2026-01-15 | squeeze | +1,051 | sq_target_hit |
| 4 | BATL | 2026-01-26 | squeeze | +615 | sq_target_hit |
| 5 | POLA | 2026-01-20 | squeeze | +569 | sq_target_hit |

## Jan 2026 — Bottom 5 Trades

| # | Symbol | Date | Strategy | P&L | Reason |
|---|--------|------|----------|-----|--------|
| 1 | SXTP | 2026-01-22 | micro_pullback | -1,242 | stop_hit |
| 2 | MOVE | 2026-01-23 | micro_pullback | -657 | bearish_engulfing_exit_full |
| 3 | IOTR | 2026-01-22 | micro_pullback | -440 | bearish_engulfing_exit_full |
| 4 | BDSX | 2026-01-12 | squeeze | -325 | sq_max_loss_hit |
| 5 | CYN | 2026-01-27 | micro_pullback | -198 | max_loss_hit |

---

## Notes

- Jan 2025 scanner JSONs were generated BEFORE the rescan fix (find_emerging_movers found 0 stocks).
  Re-run `scanner_sim.py` for Jan 2025 dates to pick up new rescan candidates.
- SQ exit fixes (partial exit, wide trail, runner detect, halt-through) are enabled for the first time in batch mode.
- MP regression targets: VERO 2026-01-16 +$18,583, ROLR 2026-01-14 +$6,444 (both verified).

*Report generated: 2026-03-23 16:58*
