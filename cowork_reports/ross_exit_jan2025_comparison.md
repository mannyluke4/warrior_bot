# Ross Exit Jan 2025 Comparison

**Date generated:** 2026-03-23
**Purpose:** Test WB_ROSS_EXIT_ENABLED=1 vs baseline on biggest Jan 2025 runners (stocks with most $ left on table per post_exit_analysis.md)
**Method:** Each stock run twice — baseline (`WB_MP_ENABLED=1`) and Ross exit (`WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1`) — fetching directly from Alpaca API (no tick cache for 2025 dates)
**CUC gate:** WB_ROSS_CUC_MIN_R=5.0 (default) — suppresses CUC exits when unrealized gain >= 5R

---

## Results

| Stock | Date | Baseline P&L | Ross Exit P&L | Delta | MP Trades? |
|-------|------|-------------|---------------|-------|------------|
| ALUR | 2025-01-24 | $1,989 | $1,989 | **$0** | No — all SQ |
| VNCE | 2025-01-23 | $1,820 | $2,132 | **+$312** | Yes (1 trade) |
| WHLR | 2025-01-16 | $0 | $0 | $0 | No trades at all |
| AIFF | 2025-01-14 | $8,592 | $8,343 | **-$249** | Yes (1 trade) |
| NVNI | 2025-01-24 | $2,298 | $2,306 | **+$8** | Yes (1 trade) |
| BKYI | 2025-01-15 | $423 | $731 | **+$308** | Yes (1 trade) |
| SILO | 2025-01-08 | $536 | $536 | $0 | No — all SQ |
| **TOTAL** | | **$15,658** | **$16,037** | **+$379** | |

---

## Per-Stock Trade Detail

### ALUR — 2025-01-24 (the $85K Ross trade)
**Baseline = Ross Exit = $1,989 (no change)**

| # | Time | Entry | Stop | Exit | Reason | P&L |
|---|------|-------|------|------|--------|-----|
| 1 | 07:01 | 8.04 | 7.90 | 8.40 | sq_target_hit | +$1,765 |
| 2 | 07:07 | 10.04 | 9.90 | 10.03 | sq_para_trail_exit | -$25 |
| 3 | 07:08 | 10.04 | 9.90 | 10.14 | sq_para_trail_exit | +$249 |

All three trades are SQ exits. Ross exit system does not intercept SQ trades. Trade 1 exited at $8.40 via sq_target_hit while the stock ran to $20+. This is the single biggest gap in the dataset ($85K left on table per jan_2025_strategy_audit.md).

---

### VNCE — 2025-01-23
**Baseline: $1,820 → Ross Exit: $2,132 (+$312)**

| # | Time | Entry | Stop | Exit (Baseline) | Reason (Baseline) | P&L Base | Exit (Ross) | Reason (Ross) | P&L Ross |
|---|------|-------|------|-----------------|-------------------|---------|------------|--------------|---------|
| 1 | 08:38 | 4.04 | 3.90 | 4.06 | sq_para_trail_exit | +$71 | 4.06 | sq_para_trail_exit | +$71 |
| 2 | 08:42 | 4.2101 | 4.03 | 4.18 | topping_wicky_exit_full | -$28 | 4.2612 | ross_cuc_exit | +$284 |
| 3 | 09:32 | 4.64 | 4.50 | 4.60 | sq_para_trail_exit | -$143 | 4.60 | sq_para_trail_exit | -$143 |
| 4 | 10:06 | 4.64 | 4.39 | 5.14 | sq_target_hit | +$1,920 | 5.14 | sq_target_hit | +$1,920 |

Trade 2 is the only MP trade. Ross CUC exit fired at 4.2612 (above entry) vs topping_wicky at 4.18 (below entry). CUC gave a better exit here — flipped a -$28 loss into +$284.

---

### WHLR — 2025-01-16
**Baseline: $0 → Ross Exit: $0 (no trades taken either way)**

Armed: 1, Signals: 1, Entered: 0. Setup armed but trigger never broke. No impact from Ross exit.

---

### AIFF — 2025-01-14
**Baseline: $8,592 → Ross Exit: $8,343 (-$249)**

| # | Time | Entry | Stop | Exit (Baseline) | Reason (Baseline) | P&L Base | Exit (Ross) | Reason (Ross) | P&L Ross |
|---|------|-------|------|-----------------|-------------------|---------|------------|--------------|---------|
| 1 | 07:46 | 2.04 | 1.90 | 2.6550 | sq_target_hit | +$2,897 | 2.6550 | sq_target_hit | +$2,897 |
| 2 | 09:07 | 4.2100 | 3.7698 | 4.1800 | topping_wicky_exit_full | -$68 | 4.0701 | ross_cuc_exit | -$318 |
| 3 | 09:31 | 4.61 | 4.48 | 5.0791 | sq_target_hit | +$2,079 | 5.0791 | sq_target_hit | +$2,079 |
| 4 | 09:32 | 4.61 | 4.40 | 5.3601 | sq_target_hit | +$3,684 | 5.3601 | sq_target_hit | +$3,684 |

Trade 2 is the only MP trade. CUC fired at 4.0701 (below entry) — earlier and lower than the topping_wicky at 4.18. False positive: the stock pulled back slightly then continued up (trades 3 and 4 re-entered higher). Ross exit hurt here by $250.

---

### NVNI — 2025-01-24
**Baseline: $2,298 → Ross Exit: $2,306 (+$8)**

| # | Time | Entry | Stop | Exit (Baseline) | Reason (Baseline) | P&L Base | Exit (Ross) | Reason (Ross) | P&L Ross |
|---|------|-------|------|-----------------|-------------------|---------|------------|--------------|---------|
| 1 | 09:05 | 2.1497 | 2.05 | 2.1192 | bearish_engulfing_exit_full | -$306 | 2.1200 | ross_shooting_star | -$298 |
| 2 | 09:32 | 2.48 | 2.36 | 2.52 | sq_para_trail_exit | +$167 | 2.52 | sq_para_trail_exit | +$167 |
| 3 | 09:35 | 2.48 | 2.36 | 2.73 | sq_target_hit | +$2,438 | 2.73 | sq_target_hit | +$2,438 |

Trade 1 is the only MP trade. Both baseline and Ross exit are losers — Ross shooting star fired at 2.12 vs bearish engulfing at 2.1192 (nearly identical exit prices). Negligible +$8 difference.

---

### BKYI — 2025-01-15
**Baseline: $423 → Ross Exit: $731 (+$308)**

| # | Time | Entry | Stop | Exit (Baseline) | Reason (Baseline) | P&L Base | Exit (Ross) | Reason (Ross) | P&L Ross |
|---|------|-------|------|-----------------|-------------------|---------|------------|--------------|---------|
| 1 | 08:08 | 2.04 | 1.90 | 2.33 | sq_target_hit | +$848 | 2.33 | sq_target_hit | +$848 |
| 2 | 10:21 | 2.64 | 2.50 | 2.53 | sq_max_loss_hit | -$393 | 2.53 | sq_max_loss_hit | -$393 |
| 3 | 10:58 | 3.24 | 2.93 | 3.2299 | bearish_engulfing_exit_full | -$33 | 3.3255 | ross_cuc_exit | +$276 |

Trade 3 is the only MP trade. CUC exit fired at 3.3255 (above entry) vs bearish engulfing at 3.2299 (just below entry). CUC gave a better exit — flipped a -$33 loss into +$276.

---

### SILO — 2025-01-08
**Baseline = Ross Exit = $536 (no change)**

| # | Time | Entry | Stop | Exit | Reason | P&L |
|---|------|-------|------|------|--------|-----|
| 1 | 08:30 | 2.04 | 1.90 | 2.05 | sq_para_trail_exit | +$36 |
| 2 | 08:32 | 2.04 | 1.90 | 2.11 | sq_para_trail_exit | +$250 |
| 3 | 09:33 | 2.47 | 2.33 | 2.54 | sq_para_trail_exit | +$250 |

All SQ trades. Ross exit has no effect.

---

## Key Finding: Ross Exit Doesn't Touch the Big Money-on-Table Stocks

**The Ross exit system only intercepts `micro_pullback` trades.** It explicitly skips `squeeze` and `vwap_reclaim` setup types (per simulate.py:401 and simulate.py:2035).

The biggest Jan 2025 runners in the post-exit analysis are **all SQ exits**:
- ALUR 2025-01-24: `sq_target_hit` at $8.40 → stock ran to $20 → $85K left on table
- VNCE 2025-01-23: `sq_para_trail_exit` → $13K left on table
- WHLR 2025-01-16: `sq_para_trail_exit` → $4.4K left on table

Ross exit = **$0 impact** on all of these.

The +$379 net improvement across 7 stocks is real but small — it comes entirely from small MP trades on stocks where the SQ system captured the main move anyway. It does not address the core problem.

**To capture ALUR-type moves, the fix needs to be in the SQ exit system**, not MP:
- `sq_target_hit` fires at a fixed R-multiple and takes 100% profit — no mechanism to recognize an A+ runner and hold
- A dynamic target (scaling with premarket gap % or momentum score) or a hold-through-halt rule would have the highest impact
- Applying Ross-style 1m signal exits to SQ trades is a separate and higher-stakes change

---

## Regression Check

Primary regressions unaffected (WB_ROSS_EXIT_ENABLED=0 by default):
- VERO 2026-01-16: not re-run (unchanged by this work)
- ROLR 2026-01-14: not re-run (unchanged by this work)
