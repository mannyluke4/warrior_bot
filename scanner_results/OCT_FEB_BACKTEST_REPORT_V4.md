# Oct 2025 – Feb 2026 Backtest Report — V4 (Tier Restructure + B-Gate)

**Generated:** 2026-03-09
**Branch:** scanner-sim-backtest
**Dates:** Oct 1, 2025 – Feb 27, 2026 (102 trading days)
**Engine:** simulate.py --ticks (tick-by-tick replay)

## Headline Metrics

| Metric | Value |
|--------|-------|
| **Total P&L** | **$+4,672** |
| Total Sims | 166 |
| Active Trades (non-$0) | 31 |
| Winners | 13 |
| Losers | 18 |
| Win Rate (active) | 41.9% |
| Profitable Days | 12/69 |
| Cold Market Skips | 19 |
| Kill Switch Fires | 0 |

## Monthly Breakdown

| Month | Days | Sims | Active | W/L | P&L | Best Day | Worst Day |
|-------|------|------|--------|-----|-----|----------|-----------|
| Oct 2025 | 18 | 33 | 4 | 2/2 | $-24 | 2025-10-14 $+464 | 2025-10-10 $-789 |
| Nov 2025 | 12 | 25 | 6 | 1/5 | $-3,135 | 2025-11-14 $+583 | 2025-11-05 $-1,544 |
| Dec 2025 | 16 | 45 | 11 | 6/5 | $+2,429 | 2025-12-12 $+1,221 | 2025-12-31 $-612 |
| Jan 2026 | 13 | 27 | 7 | 3/4 | $+4,187 | 2026-01-16 $+4,264 | 2026-01-09 $-750 |
| Feb 2026 | 10 | 36 | 3 | 1/2 | $+1,215 | 2026-02-05 $+1,507 | 2026-02-02 $-268 |

## Version Comparison

| Metric | V1 (No Filters) | V2 (Protective) | V3 (SQS) | V4 (Jan-Feb) | V4 (Oct-Feb) |
|--------|-----------------|-----------------|----------|--------------|--------------|
| **Total P&L** | -$17,885 | -$8,938 | +$566 | +$5,402 | **$+4,672** |
| Total Sims | 51 | 161 | 26 | 63 | 166 |
| Active Trades | 9 | 25 | 20 | 10 | 31 |
| Win Rate | 17.6% | 4.3% | 34.6% | 40.0% | 41.9% |
| Profitable Days | 2/19 | 3/30 | 5/14 | 4/23 | 12/69 |
| Cold Market Skips | 0 | 8 | 8 | 8 | 19 |
| Kill Switch | 0 | 2 | 2 | 0 | 0 |

## Tier Performance

| Tier | Sims | P&L | Avg P&L |
|------|------|-----|---------|
| Shelved (SQS 7-9, $250) | 8 | $-634 | $-79 |
| A-tier (SQS 5-6, $750) | 114 | $+0 | $+0 |
| B-tier (SQS 4, $250) | 44 | $+0 | $+0 |

## B-Tier Quality Gate Stats

- SQS=4 candidates: **178**
- Passed (gap>=14% AND pm_vol>=10k): **44**
- Blocked: **134**
- B-tier P&L: **$+124**

## SQS Distribution

| Category | Count |
|----------|-------|
| Shelved (SQS 7-9) | 8 |
| A-tier (SQS 5-6) | 114 |
| B-tier (SQS 4, gate passed) | 44 |
| B-gate skip (SQS 4, gate failed) | 134 |
| SQS skip (0-3) | 129 |

## Equity Curve Summary

| Metric | Value |
|--------|-------|
| Starting Balance | $30,000 |
| Ending Balance | $34,672 |
| Total Return | 15.6% |
| Peak Balance | $34,696 (2026-02-05) |
| Max Drawdown | $3,742 (12.5%) |
| Drawdown Trough | 2025-11-11 |
| Longest Winning Streak | 3 days |
| Longest Losing Streak | 5 days |
| Buying Power (end) | $138,688 |

## Monster Trades (|P&L| >= $1,000)

| Date | Symbol | Tier | Risk | P&L |
|------|--------|------|------|-----|
| 2026-01-16 | GWAV | A (SQS=6) | $750 | $+5,052 |
| 2025-12-12 | KPLT | A (SQS=6) | $750 | $+1,585 |
| 2026-02-05 | RIOX | A (SQS=5) | $750 | $+1,507 |
| 2025-11-05 | BQ | A (SQS=6) | $750 | $-1,544 |

- Monster winners: **3** (total: $+8,144)
- Monster losers: **1** (total: $-1,544)
- GWAV is **NOT** an anomaly — 3 monster winners found

## Kill Switch Analysis

No kill switch activations across entire test period.

## Per-Day Breakdown

| Date | Day P&L | Sims | Details |
|------|---------|------|---------|
| 2025-10-01 | $+0 | 1 | UCFI:A SQS=6(A) $750 P&L=$+0 |
| 2025-10-06 | $+0 | 2 | QCLS:A SQS=5(A) $750 P&L=$+0; IONZ:B SQS=5(A) $750 P&L=$+0 |
| 2025-10-07 | $+0 | 1 | BTM:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-10-08 | $+0 | 3 | BIAF:A SQS=5(A) $750 P&L=$+0; DCOY:A SQS=5(A) $750 P&L=$+0; WLDS:A SQS=5(A) $750 P&L=$+0 |
| 2025-10-09 | $+0 | 1 | TCRT:A SQS=6(A) $750 P&L=$+0 |
| 2025-10-10 | $-789 | 1 | ATON:A SQS=5(A) $750 P&L=$-789 |
| 2025-10-13 | $+0 | 2 | YHGJ:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; XBIO:A SQS=5(A) $750 P&L=$+0 |
| 2025-10-14 | $+464 | 3 | JDZG:A SQS=6(A) $750 P&L=$+720; RGTZ:A SQS=5(A) $750 P&L=$+0; CYN:B SQS=4(B) $250 P&L=$-256 [B-GATE:PASS] |
| 2025-10-15 | $+301 | 2 | AWX:A SQS=5(A) $750 P&L=$+301; SOAR:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-10-16 | $+0 | 4 | MAMK:A SQS=6(A) $750 P&L=$+0; SLGB:A SQS=6(A) $750 P&L=$+0; ARBB:A SQS=5(A) $750 P&L=$+0; BGMS:A SQS=5(A) $750 P&L=$+0 |
| 2025-10-17 | $+0 | 1 | QCLS:A SQS=5(A) $750 P&L=$+0 |
| 2025-10-20 | $+0 | 1 | SINT:A SQS=6(A) $750 P&L=$+0 |
| 2025-10-22 | $+0 | 3 | BDSX:A SQS=6(A) $750 P&L=$+0; RYOJ:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; AGMH:A SQS=5(A) $750 P&L=$+0 |
| 2025-10-24 | $+0 | 1 | WOK:A SQS=5(A) $750 P&L=$+0 |
| 2025-10-27 | $+0 | 3 | SLGB:A SQS=6(A) $750 P&L=$+0; NEUP:A SQS=5(A) $750 P&L=$+0; MAMK:A SQS=5(A) $750 P&L=$+0 |
| 2025-10-29 | $+0 | 1 | JLHL:A SQS=5(A) $750 P&L=$+0 |
| 2025-10-30 | $+0 | 1 | CRCG:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-10-31 | $+0 | 2 | GWAV:A SQS=5(A) $750 P&L=$+0; NUWE:A SQS=5(A) $750 P&L=$+0 |
| 2025-11-03 | $-629 | 4 | BQ:A SQS=5(A) $750 P&L=$-629; CRCG:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; QCLS:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; SDST:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-11-05 | $-1,544 | 1 | BQ:A SQS=6(A) $750 P&L=$-1,544 |
| 2025-11-06 | $-833 | 5 | CRCG:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; AVX:A SQS=5(A) $750 P&L=$-833; GNPX:A SQS=5(A) $750 P&L=$+0; BMNG:A SQS=5(A) $750 P&L=$+0; CRWG:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-11-07 | $-554 | 1 | MSGM:A SQS=6(A) $750 P&L=$-554 |
| 2025-11-11 | $-158 | 2 | BODI:A SQS=5(A) $750 P&L=$-158; CRWG:B SQS=5(A) $750 P&L=$+0 |
| 2025-11-13 | $+0 | 2 | CMCT:A SQS=5(A) $750 P&L=$+0; BMNG:A SQS=5(A) $750 P&L=$+0 |
| 2025-11-14 | $+583 | 2 | ARBB:A SQS=6(A) $750 P&L=$+0; IONZ:B SQS=5(A) $750 P&L=$+583 |
| 2025-11-17 | $+0 | 3 | CRCG:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; CYCU:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; BMNG:A SQS=5(A) $750 P&L=$+0 |
| 2025-11-19 | $+0 | 1 | BMNG:A SQS=5(A) $750 P&L=$+0 |
| 2025-11-20 | $+0 | 2 | BMNG:A SQS=5(A) $750 P&L=$+0; MRAL:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-11-24 | $+0 | 1 | OLOX:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-11-25 | $+0 | 1 | BMNG:A SQS=5(A) $750 P&L=$+0 |
| 2025-12-01 | $+0 | 1 | BMNG:A SQS=5(A) $750 P&L=$+0 |
| 2025-12-02 | $+0 | 2 | TAOP:A SQS=7(Shelved) $250 P&L=$+0; QTTB:A SQS=5(A) $750 P&L=$+0 |
| 2025-12-05 | $+417 | 4 | QCLS:A SQS=7(Shelved) $250 P&L=$+0; BMNG:A SQS=5(A) $750 P&L=$+346; SUGP:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; DFSC:A SQS=4(B) $250 P&L=$+71 [B-GATE:PASS] |
| 2025-12-08 | $+614 | 5 | DRMA:A SQS=5(A) $750 P&L=$+0; GURE:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; LICN:A SQS=5(A) $750 P&L=$+0; ALOY:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; FGI:A SQS=5(A) $750 P&L=$+614 |
| 2025-12-09 | $-250 | 4 | XCUR:A SQS=6(A) $750 P&L=$+0; CETX:A SQS=7(Shelved) $250 P&L=$-250; CMCT:A SQS=5(A) $750 P&L=$+0; PHGE:A SQS=5(A) $750 P&L=$+0 |
| 2025-12-10 | $+0 | 2 | XCUR:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; QCLS:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-12-11 | $-237 | 2 | GLXG:A SQS=7(Shelved) $250 P&L=$-237; AMCI:A SQS=5(A) $750 P&L=$+0 |
| 2025-12-12 | $+1,221 | 6 | KPLT:A SQS=6(A) $750 P&L=$+1,585; CETX:A SQS=6(A) $750 P&L=$+0; BTTC:A SQS=6(A) $750 P&L=$-364; BMNG:A SQS=5(A) $750 P&L=$+0; GLXG:A SQS=5(A) $750 P&L=$+0; CRWG:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-12-15 | $+767 | 4 | ARBB:A SQS=5(A) $750 P&L=$+767; BMNG:A SQS=6(A) $750 P&L=$+0; CETX:A SQS=5(A) $750 P&L=$+0; CRWG:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-12-16 | $+0 | 3 | SQFT:A SQS=6(A) $750 P&L=$+0; WATT:A SQS=6(A) $750 P&L=$+0; ARTV:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-12-17 | $+0 | 2 | BMNG:A SQS=5(A) $750 P&L=$+0; JLHL:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-12-18 | $+509 | 2 | PCSA:A SQS=4(B) $250 P&L=$-250 [B-GATE:PASS]; BMNG:A SQS=5(A) $750 P&L=$+759 |
| 2025-12-22 | $+0 | 2 | BMNG:A SQS=5(A) $750 P&L=$+0; AMCI:A SQS=5(A) $750 P&L=$+0 |
| 2025-12-23 | $+0 | 1 | DWTX:A SQS=5(A) $750 P&L=$+0 |
| 2025-12-30 | $+0 | 3 | RIOX:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; GVH:A SQS=5(A) $750 P&L=$+0; MTEX:A SQS=5(A) $750 P&L=$+0 |
| 2025-12-31 | $-612 | 2 | ULY:A SQS=5(A) $750 P&L=$-612; EKSO:A SQS=5(A) $750 P&L=$+0 |
| 2026-01-02 | $+372 | 1 | QBTZ:A SQS=5(A) $750 P&L=$+372 |
| 2026-01-06 | $+0 | 1 | NOMA:A SQS=5(A) $750 P&L=$+0 |
| 2026-01-07 | $+0 | 3 | BMNG:A SQS=6(A) $750 P&L=$+0; ASTI:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; BNAI:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2026-01-09 | $-750 | 3 | ICON:A SQS=7(Shelved) $250 P&L=$+0; CETX:A SQS=7(Shelved) $250 P&L=$+0; FEED:A SQS=6(A) $750 P&L=$-750 |
| 2026-01-13 | $+0 | 1 | ATRA:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2026-01-15 | $-135 | 2 | AGPU:A SQS=5(A) $750 P&L=$-135; BMNG:A SQS=5(A) $750 P&L=$+0 |
| 2026-01-16 | $+4,264 | 3 | GWAV:A SQS=6(A) $750 P&L=$+5,052; RAYA:A SQS=5(A) $750 P&L=$+0; MLEC:A SQS=5(A) $750 P&L=$-788 |
| 2026-01-21 | $+583 | 1 | BAOS:A SQS=4(B) $250 P&L=$+583 [B-GATE:PASS] |
| 2026-01-22 | $+0 | 2 | RAYA:A SQS=6(A) $750 P&L=$+0; EVTV:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2026-01-23 | $-147 | 1 | DRCT:A SQS=7(Shelved) $250 P&L=$-147 |
| 2026-01-26 | $+0 | 3 | DRCT:A SQS=5(A) $750 P&L=$+0; VMAR:A SQS=5(A) $750 P&L=$+0; HUBC:A SQS=5(A) $750 P&L=$+0 |
| 2026-01-28 | $+0 | 1 | ENVB:A SQS=5(A) $750 P&L=$+0 |
| 2026-01-29 | $+0 | 5 | SER:A SQS=6(A) $750 P&L=$+0; BMNG:A SQS=6(A) $750 P&L=$+0; GRI:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; MST:A SQS=5(A) $750 P&L=$+0; NAMM:B SQS=5(A) $750 P&L=$+0 |
| 2026-02-02 | $-268 | 4 | FEED:A SQS=6(A) $750 P&L=$-268; SXTP:A SQS=5(A) $750 P&L=$+0; BTOG:A SQS=5(A) $750 P&L=$+0; BATL:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2026-02-04 | $+0 | 2 | BAIG:A SQS=5(A) $750 P&L=$+0; NUWE:A SQS=5(A) $750 P&L=$+0 |
| 2026-02-05 | $+1,507 | 9 | RGTX:A SQS=5(A) $750 P&L=$+0; NBIG:A SQS=5(A) $750 P&L=$+0; BAIG:A SQS=5(A) $750 P&L=$+0; RIOX:A SQS=5(A) $750 P&L=$+1,507; MST:A SQS=5(A) $750 P&L=$+0; SXTC:A SQS=5(A) $750 P&L=$+0; SOUX:A SQS=5(A) $750 P&L=$+0; NUWE:A SQS=5(A) $750 P&L=$+0; CRWG:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2026-02-06 | $+0 | 1 | MB:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2026-02-12 | $-24 | 4 | RGTX:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; ASTI:A SQS=4(B) $250 P&L=$-24 [B-GATE:PASS]; HOOX:A SQS=5(A) $750 P&L=$+0; CRMX:A SQS=5(A) $750 P&L=$+0 |
| 2026-02-18 | $+0 | 4 | BENF:A SQS=7(Shelved) $250 P&L=$+0; OBAI:A SQS=5(A) $750 P&L=$+0; UGRO:A SQS=6(A) $750 P&L=$+0; PLYX:A SQS=5(A) $750 P&L=$+0 |
| 2026-02-19 | $+0 | 1 | BENF:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2026-02-20 | $+0 | 4 | NBIG:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; EDHL:A SQS=5(A) $750 P&L=$+0; CRWG:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; AGIG:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2026-02-23 | $+0 | 3 | ABTS:A SQS=5(A) $750 P&L=$+0; ANPA:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; BESS:A SQS=5(A) $750 P&L=$+0 |
| 2026-02-27 | $+0 | 4 | MRAL:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; SOUX:A SQS=5(A) $750 P&L=$+0; NBIG:A SQS=5(A) $750 P&L=$+0; CRWG:B SQS=5(A) $750 P&L=$+0 |
