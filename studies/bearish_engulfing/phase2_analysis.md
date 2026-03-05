# Phase 2: Trade 1 Exit Analysis

## Q1: How many Trade 1 exits were bearish engulfing?

- **Bearish engulfing:** 16 / 27 (59%)
- **Other exits:** 11 / 27 (41%)

### BE Trade 1 exits:

| # | Symbol | Date | Entry | Exit | P&L | R-Mult | Min Held |
|---|--------|------|-------|------|-----|--------|----------|
| 1 | ACON | 2026-01-08 | 8.22 | 8.12 | $-122 | -0.1R | 0m |
| 2 | APVO | 2026-01-09 | 9.44 | 13.16 | $+7,622 | +7.6R | 4m |
| 3 | BDSX | 2026-01-12 | 7.60 | 7.53 | $-171 | -0.2R | 2m |
| 4 | ROLR | 2026-01-14 | 3.81 | 3.81 | $+0 | +0.0R | 1m |
| 5 | BNAI | 2026-01-16 | 6.68 | 6.60 | $-615 | -0.6R | 3m |
| 6 | GWAV | 2026-01-16 | 5.49 | 6.57 | $+7,713 | +7.7R | 12m |
| 7 | TNMG | 2026-01-16 | 3.96 | 3.71 | $-481 | -0.5R | 1m |
| 8 | VERO | 2026-01-16 | 3.52 | 3.55 | $+176 | +0.2R | 0m |
| 9 | MOVE | 2026-01-23 | 19.64 | 19.49 | $-156 | -0.2R | 3m |
| 10 | SLE | 2026-01-23 | 10.52 | 9.97 | $-390 | -0.4R | 3m |
| 11 | HIND | 2026-01-27 | 6.31 | 5.87 | $-709 | -0.7R | 0m |
| 12 | BNAI | 2026-01-28 | 68.70 | 69.03 | $+121 | +0.1R | 0m |
| 13 | BNAI | 2026-02-05 | 32.37 | 30.52 | $-512 | -0.5R | 0m |
| 14 | MLEC | 2026-02-13 | 7.71 | 7.32 | $-558 | -0.6R | 0m |
| 15 | SNSE | 2026-02-18 | 28.52 | 28.88 | $+146 | +0.1R | 0m |
| 16 | ENVB | 2026-02-19 | 3.00 | 3.37 | $+474 | +0.5R | 2m |

### Non-BE Trade 1 exits:

| # | Symbol | Date | Entry | Exit | Reason | P&L | R-Mult | Min Held |
|---|--------|------|-------|------|--------|-----|--------|----------|
| 1 | ROLR | 2026-01-06 | 2.74 | 2.54 | stop_hit | $-1,409 | -1.4R | 29m |
| 2 | PMAX | 2026-01-13 | 3.32 | 1.98 | stop_hit | $-1,098 | -1.1R | ? |
| 3 | LCFY | 2026-01-16 | 6.14 | 5.76 | topping_wicky_exit_full | $-463 | -0.5R | 3m |
| 4 | ROLR | 2026-01-16 | 21.02 | 20.41 | stop_hit | $-1,070 | -1.1R | 71m |
| 5 | SHPH | 2026-01-16 | 1.86 | 1.76 | stop_hit | $-1,111 | -1.1R | ? |
| 6 | PAVM | 2026-01-21 | 6.51 | 6.50 | trail_stop | $-92 | -0.1R | 24m |
| 7 | BCTX | 2026-01-27 | 4.91 | 4.91 | trail_stop | $+0 | +0.0R | ? |
| 8 | MOVE | 2026-01-27 | 19.23 | 21.03 | topping_wicky_exit_full | $+5,616 | +12.9R | 7m |
| 9 | SXTP | 2026-01-27 | 4.86 | 4.69 | stop_hit | $-1,300 | -1.3R | 50m |
| 10 | MNTS | 2026-02-06 | 5.82 | 5.98 | topping_wicky_exit_full | $+862 | +0.9R | 9m |
| 11 | ACON | 2026-02-13 | 2.69 | 2.67 | topping_wicky_exit_full | $-214 | -0.2R | 141m |

## Q2: Trade 1 P&L — BE vs Other

| Metric | BE Trade 1 | Non-BE Trade 1 |
|--------|-----------|---------------|
| Count | 16 | 11 |
| Total P&L | $+12,538 | $-279 |
| Avg P&L | $+784 | $-25 |
| Win Rate | 38% (6/16) | 18% (2/11) |
| Avg R-Multiple | +0.78R | +0.64R |

## Q3: Trade 1 BE Exit Speed

| Time Bucket | Count | Sessions | Avg P&L |
|-------------|-------|----------|---------|
| < 2 min | 9 | ACON(01-08), ROLR(01-14), TNMG(01-16), VERO(01-16), HIND(01-27), BNAI(01-28), BNAI(02-05), MLEC(02-13), SNSE(02-18) | $-215 |
| 2-5 min | 6 | APVO(01-09), BDSX(01-12), BNAI(01-16), MOVE(01-23), SLE(01-23), ENVB(02-19) | $+1,127 |
| 5-10 min | 0 | — | — |
| > 10 min | 1 | GWAV(01-16) | $+7,713 |

## Q4: Trade 1 BE exits < 5 minutes — what happened next?

Found **15** sessions where Trade 1 exited via BE in < 5 minutes.

### ACON — 2026-01-08
- **Trade 1:** Entry 07:01 @ 8.22, Exit @ 8.12, P&L $-122 (-0.1R), held 0m
- **Re-entries:** 2 more trades
  - Trade 2: Entry 07:04 @ 8.21, Exit @ 7.94, stop_hit, P&L $-1,000 (-1.0R)
  - Trade 3: Entry 09:38 @ 8.52, Exit @ 8.19, stop_hit, P&L $-1,000 (-1.0R)
- **Session total:** $-2,122
- **Price exceeded BE exit?** YES — later trades touched 8.52 (BE exit was 8.12)

### APVO — 2026-01-09
- **Trade 1:** Entry 08:05 @ 9.44, Exit @ 13.16, P&L $+7,622 (+7.6R), held 4m
- **Re-entries:** None
- **Session total:** $+7,622
- **Price exceeded BE exit?** Unknown (no later trades or prices below)

### BDSX — 2026-01-12
- **Trade 1:** Entry 09:37 @ 7.60, Exit @ 7.53, P&L $-171 (-0.2R), held 2m
- **Re-entries:** 5 more trades
  - Trade 2: Entry 09:41 @ 7.52, Exit @ 7.54, bearish_engulfing_exit_full, P&L $+71 (+0.1R)
  - Trade 3: Entry 09:51 @ 8.48, Exit @ 8.57, bearish_engulfing_exit_full, P&L $+190 (+0.2R)
  - Trade 4: Entry 09:57 @ 8.80, Exit @ 8.70, bearish_engulfing_exit_full, P&L $-417 (-0.4R)
  - Trade 5: Entry 11:26 @ 7.95, Exit @ 7.99, bearish_engulfing_exit_full, P&L $+302 (+0.4R)
  - Trade 6: Entry 11:28 @ 8.03, Exit @ 8.03, bearish_engulfing_exit_full, P&L $-22 (-0.0R)
- **Session total:** $-47
- **Price exceeded BE exit?** YES — later trades touched 8.80 (BE exit was 7.53)

### ROLR — 2026-01-14
- **Trade 1:** Entry 08:06 @ 3.81, Exit @ 3.81, P&L $+0 (+0.0R), held 1m
- **Re-entries:** 4 more trades
  - Trade 2: Entry 08:08 @ 3.92, Exit @ 3.72, stop_hit, P&L $-1,000 (-1.0R)
  - Trade 3: Entry 08:19 @ 5.91, Exit @ 7.71, bearish_engulfing_exit_full, P&L $+3,186 (+3.2R)
  - Trade 4: Entry 08:24 @ 9.33, Exit @ 8.74, bearish_engulfing_exit_full, P&L $-229 (-0.2R)
  - Trade 5: Entry 08:36 @ 17.80, Exit @ 17.22, bearish_engulfing_exit_full, P&L $-313 (-0.3R)
- **Session total:** $+1,644
- **Price exceeded BE exit?** YES — later trades touched 17.80 (BE exit was 3.81)

### BNAI — 2026-01-16
- **Trade 1:** Entry 08:17 @ 6.68, Exit @ 6.60, P&L $-615 (-0.6R), held 3m
- **Re-entries:** 1 more trades
  - Trade 2: Entry 08:21 @ 6.76, Exit @ 6.75, bearish_engulfing_exit_full, P&L $-59 (-0.1R)
- **Session total:** $-674
- **Price exceeded BE exit?** YES — later trades touched 6.76 (BE exit was 6.60)

### TNMG — 2026-01-16
- **Trade 1:** Entry 07:01 @ 3.96, Exit @ 3.71, P&L $-481 (-0.5R), held 1m
- **Re-entries:** None
- **Session total:** $-481
- **Price exceeded BE exit?** Unknown (no later trades or prices below)

### VERO — 2026-01-16
- **Trade 1:** Entry 07:03 @ 3.52, Exit @ 3.55, P&L $+176 (+0.2R), held 0m
- **Re-entries:** 3 more trades
  - Trade 2: Entry 07:04 @ 3.61, Exit @ 3.61, bearish_engulfing_exit_full, P&L $+0 (+0.0R)
  - Trade 3: Entry 07:14 @ 3.60, Exit @ 4.68, topping_wicky_exit_full, P&L $+7,713 (+7.7R)
  - Trade 4: Entry 07:30 @ 5.89, Exit @ 5.57, stop_hit, P&L $-1,000 (-1.0R)
- **Session total:** $+6,889
- **Price exceeded BE exit?** YES — later trades touched 5.89 (BE exit was 3.55)

### MOVE — 2026-01-23
- **Trade 1:** Entry 10:55 @ 19.64, Exit @ 19.49, P&L $-156 (-0.2R), held 3m
- **Re-entries:** None
- **Session total:** $-156
- **Price exceeded BE exit?** Unknown (no later trades or prices below)

### SLE — 2026-01-23
- **Trade 1:** Entry 09:10 @ 10.52, Exit @ 9.97, P&L $-390 (-0.4R), held 3m
- **Re-entries:** None
- **Session total:** $-390
- **Price exceeded BE exit?** Unknown (no later trades or prices below)

### HIND — 2026-01-27
- **Trade 1:** Entry 08:05 @ 6.31, Exit @ 5.87, P&L $-709 (-0.7R), held 0m
- **Re-entries:** 1 more trades
  - Trade 2: Entry 08:10 @ 6.19, Exit @ 6.83, bearish_engulfing_exit_full, P&L $+970 (+1.0R)
- **Session total:** $+261
- **Price exceeded BE exit?** YES — later trades touched 6.83 (BE exit was 5.87)

### BNAI — 2026-01-28
- **Trade 1:** Entry 09:48 @ 68.70, Exit @ 69.03, P&L $+121 (+0.1R), held 0m
- **Re-entries:** 3 more trades
  - Trade 2: Entry 09:49 @ 69.72, Exit @ 67.91, stop_hit, P&L $-1,046 (-1.0R)
  - Trade 3: Entry 10:41 @ 74.91, Exit @ 85.89, topping_wicky_exit_full, P&L $+6,772 (+6.8R)
  - Trade 4: Entry 11:24 @ 76.12, Exit @ 75.50, bearish_engulfing_exit_full, P&L $-236 (-0.2R)
- **Session total:** $+5,611
- **Price exceeded BE exit?** YES — later trades touched 85.89 (BE exit was 69.03)

### BNAI — 2026-02-05
- **Trade 1:** Entry 07:01 @ 32.37, Exit @ 30.52, P&L $-512 (-0.5R), held 0m
- **Re-entries:** 1 more trades
  - Trade 2: Entry 07:06 @ 32.20, Exit @ 32.94, bearish_engulfing_exit_full, P&L $+673 (+0.7R)
- **Session total:** $+161
- **Price exceeded BE exit?** YES — later trades touched 32.94 (BE exit was 30.52)

### MLEC — 2026-02-13
- **Trade 1:** Entry 08:10 @ 7.71, Exit @ 7.32, P&L $-558 (-0.6R), held 0m
- **Re-entries:** 3 more trades
  - Trade 2: Entry 08:11 @ 7.92, Exit @ 9.25, bearish_engulfing_exit_full, P&L $+1,821 (+1.8R)
  - Trade 3: Entry 08:27 @ 11.52, Exit @ 11.30, bearish_engulfing_exit_full, P&L $-90 (-0.1R)
  - Trade 4: Entry 10:48 @ 10.27, Exit @ 9.55, stop_hit, P&L $-999 (-1.0R)
- **Session total:** $+174
- **Price exceeded BE exit?** YES — later trades touched 11.52 (BE exit was 7.32)

### SNSE — 2026-02-18
- **Trade 1:** Entry 10:41 @ 28.52, Exit @ 28.88, P&L $+146 (+0.1R), held 0m
- **Re-entries:** 1 more trades
  - Trade 2: Entry 10:46 @ 30.24, Exit @ 29.50, bearish_engulfing_exit_full, P&L $-271 (-0.3R)
- **Session total:** $-125
- **Price exceeded BE exit?** YES — later trades touched 30.24 (BE exit was 28.88)

### ENVB — 2026-02-19
- **Trade 1:** Entry 08:01 @ 3.00, Exit @ 3.37, P&L $+474 (+0.5R), held 2m
- **Re-entries:** None
- **Session total:** $+474
- **Price exceeded BE exit?** Unknown (no later trades or prices below)

### Q4 Summary
- Sessions with Trade 1 BE < 5m: **15**
- Trade 1 total P&L in these sessions: **$+4,825**
- Full session total P&L for these sessions: **$+18,841**
- Sessions where later trades recovered: 8/15