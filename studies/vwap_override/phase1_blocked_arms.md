# Phase 1: VWAP-Blocked Armed Setups

## Summary

Across **28 sessions** (27 Profile A + JZXN), the simulator found **15 armed setups** that were killed by VWAP loss ("1M RESET (lost VWAP)").

Sessions with blocked arms: 10/28 (36%)
Sessions with zero blocked arms: 18/28 (64%)

---

## All Blocked Arms (sorted by score, descending)

| # | Symbol | Date | Time | Score | Tags | Entry | Stop | R | Close@Block | VWAP@Block | %Below VWAP | Recovered 5m? | Recovered 10m? | Recovered 30m? | Max High 30m | Hyp P&L (30m) |
|---|--------|------|------|-------|------|-------|------|---|-------------|------------|-------------|---------------|----------------|----------------|--------------|---------------|
| 1 | JZXN | 2026-03-04 | 07:55 | **12.5** | ABCD,VOL_SURGE,R2G,WHOLE | 1.3600 | 1.2500 | 0.11 | 1.2500 | 1.2541 | 0.3% | YES | YES | YES | 1.5700 | +$1,909 |
| 2 | PAVM | 2026-01-21 | 08:28 | **12.5** | ABCD,VOL_SURGE,R2G,WHOLE | 15.0000 | 12.5600 | 2.44 | 12.6484 | 12.7321 | 0.7% | YES | YES | YES | 15.8600 | +$352 |
| 3 | PMAX | 2026-01-13 | 08:13 | **12.5** | ABCD,VOL_SURGE,R2G,WHOLE | 3.4499 | 1.9820 | 1.47 | 2.0100 | 2.5899 | 22.4% | NO | NO | NO | 3.4195 | -$21 |
| 4 | GWAV | 2026-01-16 | 08:20 | **12.0** | ABCD,VOL_SURGE,R2G | 8.3997 | 5.4100 | 2.99 | 5.6400 | 6.6420 | 15.1% | NO | NO | NO | 8.2505 | -$50 |
| 5 | ROLR | 2026-01-14 | 08:22 | **12.0** | ABCD,VOL_SURGE,R2G | 9.6000 | 8.2463 | 1.35 | 6.6800 | 7.3194 | 8.7% | YES | YES | YES | 21.0000 | +$8,413 |
| 6 | SHPH | 2026-01-16 | 10:09 | **12.0** | ABCD,VOL_SURGE,R2G | 1.6899 | 1.6000 | 0.09 | 1.6301 | 1.6621 | 1.9% | YES | YES | YES | 1.7800 | +$1,002 |
| 7 | SHPH | 2026-01-16 | 10:14 | **11.5** | ABCD,VOL_SURGE,R2G | 1.6900 | 1.6100 | 0.08 | 1.6600 | 1.6619 | 0.1% | YES | YES | YES | 1.8000 | +$1,375 |
| 8 | PAVM | 2026-01-21 | 08:30 | **10.5** | ABCD,VOL_SURGE,R2G | 13.1500 | 12.3900 | 0.76 | 12.3076 | 12.7265 | 3.3% | YES | YES | YES | 15.8600 | +$3,564 |
| 9 | BCTX | 2026-01-27 | 08:20 | **10.0** | ABCD,R2G | 4.8200 | 4.6500 | 0.17 | 4.6609 | 4.6912 | 0.6% | NO | NO | NO | 4.7500 | -$412 |
| 10 | MNTS | 2026-02-06 | 08:01 | **5.5** | — | 5.6700 | 5.4731 | 0.20 | 5.3900 | 5.4277 | 0.7% | NO | NO | NO | 5.6000 | -$355 |
| 11 | SLE | 2026-01-23 | 09:07 | **5.5** | — | 11.4700 | 8.1807 | 3.29 | 8.6500 | 9.1537 | 5.5% | YES | YES | YES | 11.5000 | +$9 |
| 12 | SNSE | 2026-02-18 | 08:56 | **5.5** | — | 29.9900 | 25.4900 | 4.50 | 26.8200 | 27.8814 | 3.8% | NO | YES | YES | 36.9500 | +$1,545 |
| 13 | TNMG | 2026-01-16 | 07:08 | **4.5** | WHOLE | 4.2200 | 3.4700 | 0.75 | 3.7500 | 3.7822 | 0.9% | NO | NO | NO | 3.8700 | -$467 |
| 14 | SLE | 2026-01-23 | 09:15 | **4.0** | — | 10.6100 | 9.7100 | 0.90 | 10.0400 | 10.1856 | 1.4% | NO | NO | NO | 10.5000 | -$122 |
| 15 | TNMG | 2026-01-16 | 07:03 | **4.0** | — | 4.2400 | 3.5700 | 0.67 | 3.7400 | 3.7628 | 0.6% | NO | NO | NO | 4.2200 | -$30 |

---

## Score Distribution

| Score Bucket | Count | Recovered 30m | VWAP Correct (blocked rightly) |
|-------------|-------|---------------|-------------------------------|
| ≥ 12.0 | 6 | 4/6 (67%) | 2/6 (PMAX, GWAV) |
| 10.0-11.9 | 3 | 2/3 (67%) | 1/3 (BCTX) |
| 8.0-9.9 | 0 | — | — |
| < 8.0 | 6 | 2/6 (33%) | 4/6 |

---

## Key Observations

1. **JZXN confirmed**: The motivating case (score 12.5, blocked at 07:55) shows price ran from $1.25 to $1.57 within 30 minutes — a massive missed opportunity.

2. **ROLR 2026-01-14 is the biggest miss**: Score 12.0 blocked at $6.68, stock ran to $21.00 within 30 minutes. Hypothetical P&L: +$8,413.

3. **High-score blocks (≥10) have 67% recovery rate** — meaning VWAP was wrong to block in 2/3 of cases.

4. **Low-score blocks (<8) have 33% recovery rate** — VWAP was correct to block in 2/3 of cases.

5. **Close at block vs stop**: In 3/15 cases, the close at block was at or below the armed stop (would_stop=true), meaning even with an override the stop would likely have fired. But in JZXN and ROLR, the stock recovered despite close being at/below stop.

6. **PMAX and GWAV were deeply below VWAP** (22.4% and 15.1% respectively) — these were genuine crashes, not momentary dips. The VWAP gate was absolutely right to block these.

---

## Sessions with Blocked Arms

| Session | Blocked Arms | Scores | Baseline P&L |
|---------|-------------|--------|-------------|
| PMAX 2026-01-13 | 1 | 12.5 | -$1,098 |
| ROLR 2026-01-14 | 1 | 12.0 | +$1,644 |
| GWAV 2026-01-16 | 1 | 12.0 | +$6,735 |
| SHPH 2026-01-16 | 2 | 12.0, 11.5 | -$1,111 |
| TNMG 2026-01-16 | 2 | 4.5, 4.0 | -$481 |
| PAVM 2026-01-21 | 2 | 12.5, 10.5 | +$1,586 |
| SLE 2026-01-23 | 2 | 5.5, 4.0 | -$390 |
| BCTX 2026-01-27 | 1 | 10.0 | +$0 |
| MNTS 2026-02-06 | 1 | 5.5 | +$862 |
| SNSE 2026-02-18 | 1 | 5.5 | -$125 |
| JZXN 2026-03-04 | 1 | 12.5 | +$817 |
