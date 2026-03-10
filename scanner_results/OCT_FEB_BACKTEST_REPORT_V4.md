# Oct 2025 – Feb 2026 Backtest Report — V4 (Tier Restructure + B-Gate)

**Generated:** 2026-03-09
**Branch:** scanner-sim-backtest
**Dates:** Oct 1, 2025 – Feb 27, 2026 (102 trading days)
**V4 Rules:** SQS tiers, B-gate, kill switch, cold market gate — ALL UNCHANGED

## Headline Metrics

| Metric | Value |
|--------|-------|
| **Total P&L** | **$+5,805** |
| Total Sims | 166 |
| Active Trades (non-$0) | 29 |
| Winners | 13 |
| Losers | 16 |
| Win Rate (active) | 44.8% |
| Profitable Days | 12/69 |
| Trading Days (total) | 102 |
| Cold Market Skips | 19 |
| Kill Switch Fires | 0 |

## Monthly Breakdown

| Month | Days | Sims | Active | W/L | P&L | Best Day | Worst Day |
|-------|------|------|--------|-----|-----|----------|-----------|
| 2025-10 | 23 | 33 | 4 | 2/2 | $+371 | 2025-10-14 ($+464) | 2025-10-10 ($-394) |
| 2025-11 | 19 | 25 | 5 | 1/4 | $-2,049 | 2025-11-14 ($+583) | 2025-11-05 ($-1,544) |
| 2025-12 | 22 | 45 | 10 | 6/4 | $+2,081 | 2025-12-12 ($+1,221) | 2025-12-31 ($-612) |
| 2026-01 | 19 | 27 | 7 | 3/4 | $+4,187 | 2026-01-16 ($+4,264) | 2026-01-09 ($-750) |
| 2026-02 | 19 | 36 | 3 | 1/2 | $+1,215 | 2026-02-05 ($+1,507) | 2026-02-02 ($-268) |

## Version Comparison

| Metric | V1 (No Filters) | V2 (Protective) | V3 (SQS+Sort) | V4 (Jan-Feb) | **V4 (Oct-Feb)** |
|--------|-----------------|-----------------|---------------|--------------|-----------------|
| **Total P&L** | -$17,885 | -$8,938 | +$566 | +$5,402 | **$+5,805** |
| Total Sims | 51 | 161 | 26 | 63 | 166 |
| Win Rate | 17.6% | 4.3% | 34.6% | 6.3% | 44.8% |
| Cold Market Skips | 0 | 8 | 8 | 8 | 19 |
| Kill Switch Fires | 0 | 2 | 2 | 0 | 0 |

## Tier Performance

| Tier | Sims | Active | W/L | P&L | Avg Win | Avg Loss |
|------|------|--------|-----|-----|---------|----------|
| Shelved | 8 | 2 | 0/2 | $-397 | $+0 | $-198 |
| A | 114 | 22 | 11/11 | $+6,078 | $+1,093 | $-540 |
| B | 44 | 5 | 2/3 | $+124 | $+327 | $-177 |

## SQS Distribution

| Category | Count |
|----------|-------|
| Shelved (SQS 7-9, $250) | 8 |
| A-tier (SQS 5-6, $750) | 114 |
| B-tier (SQS 4, $250, gate passed) | 44 |
| B-GATE SKIP (SQS 4, gate failed) | 134 |
| SQS SKIP (0-3) | 129 |

## B-Tier Quality Gate Stats

- SQS=4 candidates considered: **178**
- Passed gate (gap>=14% AND pm_vol>=10k): **44**
- Blocked by gate: **134**
- B-tier P&L (passed): **$+124**

## Equity Curve Summary

| Metric | Value |
|--------|-------|
| Starting Balance | $30,000 |
| Ending Balance | $35,805 |
| Total Return | +19.4% |
| Peak Balance | $35,829 (2026-02-05) |
| Max Drawdown | $2,632 (8.7%) |
| Max Win Streak | 3 days |
| Max Lose Streak | 4 days |
| Buying Power (4:1) | $143,220 |

## Monster Trades (|P&L| > $1,000)

**3 monster winners, 1 monster losers**

| Date | Symbol | Profile | Tier | Risk | P&L |
|------|--------|---------|------|------|-----|
| 2026-01-16 | GWAV | A | A (SQS=6) | $750 | $+5,052 |
| 2025-12-12 | KPLT | A | A (SQS=6) | $750 | $+1,585 |
| 2026-02-05 | RIOX | A | A (SQS=5) | $750 | $+1,507 |
| 2025-11-05 | BQ | A | A (SQS=6) | $750 | $-1,544 |

## Kill Switch Analysis

No kill switch activations.

## Per-Day Breakdown

| Date | Day P&L | Sims | Details |
|------|---------|------|---------|
| 2025-10-01 | $+0 | 1 | UCFI:A SQS=6(A) $750 P&L=$+0 |
| 2025-10-06 | $+0 | 2 | QCLS:A SQS=5(A) $750 P&L=$+0; IONZ:B SQS=5(A) $750 P&L=$+0 |
| 2025-10-07 | $+0 | 1 | BTM:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-10-08 | $+0 | 3 | BIAF:A SQS=5(A) $750 P&L=$+0; DCOY:A SQS=5(A) $750 P&L=$+0; WLDS:A SQS=5(A) $750 P&L=$+0 |
| 2025-10-09 | $+0 | 1 | TCRT:A SQS=6(A) $750 P&L=$+0 |
| 2025-10-10 | $-394 | 1 | ATON:A SQS=5(A) $750 P&L=$-394 |
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
| 2025-11-03 | $-117 | 4 | BQ:A SQS=5(A) $750 P&L=$-117; CRCG:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; QCLS:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; SDST:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-11-05 | $-1,544 | 1 | BQ:A SQS=6(A) $750 P&L=$-1,544 |
| 2025-11-06 | $-417 | 5 | CRCG:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; AVX:A SQS=5(A) $750 P&L=$-417; GNPX:A SQS=5(A) $750 P&L=$+0; BMNG:A SQS=5(A) $750 P&L=$+0; CRWG:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-11-07 | $-554 | 1 | MSGM:A SQS=6(A) $750 P&L=$-554 |
| 2025-11-11 | $+0 | 2 | BODI:A SQS=5(A) $750 P&L=$+0; CRWG:B SQS=5(A) $750 P&L=$+0 |
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
| 2025-12-11 | $+0 | 2 | GLXG:A SQS=7(Shelved) $250 P&L=$+0; AMCI:A SQS=5(A) $750 P&L=$+0 |
| 2025-12-12 | $+1,221 | 6 | KPLT:A SQS=6(A) $750 P&L=$+1,585; CETX:A SQS=6(A) $750 P&L=$+0; BTTC:A SQS=6(A) $750 P&L=$-364; BMNG:A SQS=5(A) $750 P&L=$+0; GLXG:A SQS=5(A) $750 P&L=$+0; CRWG:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-12-15 | $+182 | 4 | ARBB:A SQS=5(A) $750 P&L=$+182; BMNG:A SQS=6(A) $750 P&L=$+0; CETX:A SQS=5(A) $750 P&L=$+0; CRWG:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
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

## Per-Sim Detail

```
  2025-10-01   UCFI :A SQS=6(A) risk=$750 P&L=$+0
  2025-10-06   QCLS :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-06   IONZ :B SQS=5(A) risk=$750 P&L=$+0
  2025-10-07    BTM :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-10-08   BIAF :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-08   DCOY :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-08   WLDS :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-09   TCRT :A SQS=6(A) risk=$750 P&L=$+0
  2025-10-10   ATON :A SQS=5(A) risk=$750 P&L=$-394
  2025-10-13   YHGJ :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-10-13   XBIO :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-14   JDZG :A SQS=6(A) risk=$750 P&L=$+720
  2025-10-14   RGTZ :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-14    CYN :B SQS=4(B) risk=$250 P&L=$-256 [B-GATE:PASS]
  2025-10-15    AWX :A SQS=5(A) risk=$750 P&L=$+301
  2025-10-15   SOAR :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-10-16   MAMK :A SQS=6(A) risk=$750 P&L=$+0
  2025-10-16   SLGB :A SQS=6(A) risk=$750 P&L=$+0
  2025-10-16   ARBB :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-16   BGMS :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-17   QCLS :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-20   SINT :A SQS=6(A) risk=$750 P&L=$+0
  2025-10-22   BDSX :A SQS=6(A) risk=$750 P&L=$+0
  2025-10-22   RYOJ :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-10-22   AGMH :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-24    WOK :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-27   SLGB :A SQS=6(A) risk=$750 P&L=$+0
  2025-10-27   NEUP :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-27   MAMK :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-29   JLHL :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-30   CRCG :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-10-31   GWAV :A SQS=5(A) risk=$750 P&L=$+0
  2025-10-31   NUWE :A SQS=5(A) risk=$750 P&L=$+0
  2025-11-03     BQ :A SQS=5(A) risk=$750 P&L=$-117
  2025-11-03   CRCG :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-11-03   QCLS :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-11-03   SDST :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-11-05     BQ :A SQS=6(A) risk=$750 P&L=$-1,544
  2025-11-06   CRCG :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-11-06    AVX :A SQS=5(A) risk=$750 P&L=$-417
  2025-11-06   GNPX :A SQS=5(A) risk=$750 P&L=$+0
  2025-11-06   BMNG :A SQS=5(A) risk=$750 P&L=$+0
  2025-11-06   CRWG :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-11-07   MSGM :A SQS=6(A) risk=$750 P&L=$-554
  2025-11-11   BODI :A SQS=5(A) risk=$750 P&L=$+0
  2025-11-11   CRWG :B SQS=5(A) risk=$750 P&L=$+0
  2025-11-13   CMCT :A SQS=5(A) risk=$750 P&L=$+0
  2025-11-13   BMNG :A SQS=5(A) risk=$750 P&L=$+0
  2025-11-14   ARBB :A SQS=6(A) risk=$750 P&L=$+0
  2025-11-14   IONZ :B SQS=5(A) risk=$750 P&L=$+583
  2025-11-17   CRCG :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-11-17   CYCU :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-11-17   BMNG :A SQS=5(A) risk=$750 P&L=$+0
  2025-11-19   BMNG :A SQS=5(A) risk=$750 P&L=$+0
  2025-11-20   BMNG :A SQS=5(A) risk=$750 P&L=$+0
  2025-11-20   MRAL :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-11-24   OLOX :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-11-25   BMNG :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-01   BMNG :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-02   TAOP :A SQS=7(Shelved) risk=$250 P&L=$+0
  2025-12-02   QTTB :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-05   QCLS :A SQS=7(Shelved) risk=$250 P&L=$+0
  2025-12-05   BMNG :A SQS=5(A) risk=$750 P&L=$+346
  2025-12-05   SUGP :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-12-05   DFSC :A SQS=4(B) risk=$250 P&L=$+71 [B-GATE:PASS]
  2025-12-08   DRMA :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-08   GURE :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-12-08   LICN :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-08   ALOY :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-12-08    FGI :A SQS=5(A) risk=$750 P&L=$+614
  2025-12-09   XCUR :A SQS=6(A) risk=$750 P&L=$+0
  2025-12-09   CETX :A SQS=7(Shelved) risk=$250 P&L=$-250
  2025-12-09   CMCT :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-09   PHGE :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-10   XCUR :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-12-10   QCLS :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-12-11   GLXG :A SQS=7(Shelved) risk=$250 P&L=$+0
  2025-12-11   AMCI :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-12   KPLT :A SQS=6(A) risk=$750 P&L=$+1,585
  2025-12-12   CETX :A SQS=6(A) risk=$750 P&L=$+0
  2025-12-12   BTTC :A SQS=6(A) risk=$750 P&L=$-364
  2025-12-12   BMNG :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-12   GLXG :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-12   CRWG :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-12-15   ARBB :A SQS=5(A) risk=$750 P&L=$+182
  2025-12-15   BMNG :A SQS=6(A) risk=$750 P&L=$+0
  2025-12-15   CETX :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-15   CRWG :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-12-16   SQFT :A SQS=6(A) risk=$750 P&L=$+0
  2025-12-16   WATT :A SQS=6(A) risk=$750 P&L=$+0
  2025-12-16   ARTV :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-12-17   BMNG :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-17   JLHL :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-12-18   PCSA :A SQS=4(B) risk=$250 P&L=$-250 [B-GATE:PASS]
  2025-12-18   BMNG :A SQS=5(A) risk=$750 P&L=$+759
  2025-12-22   BMNG :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-22   AMCI :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-23   DWTX :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-30   RIOX :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-12-30    GVH :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-30   MTEX :A SQS=5(A) risk=$750 P&L=$+0
  2025-12-31    ULY :A SQS=5(A) risk=$750 P&L=$-612
  2025-12-31   EKSO :A SQS=5(A) risk=$750 P&L=$+0
  2026-01-02   QBTZ :A SQS=5(A) risk=$750 P&L=$+372
  2026-01-06   NOMA :A SQS=5(A) risk=$750 P&L=$+0
  2026-01-07   BMNG :A SQS=6(A) risk=$750 P&L=$+0
  2026-01-07   ASTI :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-01-07   BNAI :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-01-09   ICON :A SQS=7(Shelved) risk=$250 P&L=$+0
  2026-01-09   CETX :A SQS=7(Shelved) risk=$250 P&L=$+0
  2026-01-09   FEED :A SQS=6(A) risk=$750 P&L=$-750
  2026-01-13   ATRA :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-01-15   AGPU :A SQS=5(A) risk=$750 P&L=$-135
  2026-01-15   BMNG :A SQS=5(A) risk=$750 P&L=$+0
  2026-01-16   GWAV :A SQS=6(A) risk=$750 P&L=$+5,052
  2026-01-16   RAYA :A SQS=5(A) risk=$750 P&L=$+0
  2026-01-16   MLEC :A SQS=5(A) risk=$750 P&L=$-788
  2026-01-21   BAOS :A SQS=4(B) risk=$250 P&L=$+583 [B-GATE:PASS]
  2026-01-22   RAYA :A SQS=6(A) risk=$750 P&L=$+0
  2026-01-22   EVTV :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-01-23   DRCT :A SQS=7(Shelved) risk=$250 P&L=$-147
  2026-01-26   DRCT :A SQS=5(A) risk=$750 P&L=$+0
  2026-01-26   VMAR :A SQS=5(A) risk=$750 P&L=$+0
  2026-01-26   HUBC :A SQS=5(A) risk=$750 P&L=$+0
  2026-01-28   ENVB :A SQS=5(A) risk=$750 P&L=$+0
  2026-01-29    SER :A SQS=6(A) risk=$750 P&L=$+0
  2026-01-29   BMNG :A SQS=6(A) risk=$750 P&L=$+0
  2026-01-29    GRI :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-01-29    MST :A SQS=5(A) risk=$750 P&L=$+0
  2026-01-29   NAMM :B SQS=5(A) risk=$750 P&L=$+0
  2026-02-02   FEED :A SQS=6(A) risk=$750 P&L=$-268
  2026-02-02   SXTP :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-02   BTOG :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-02   BATL :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-02-04   BAIG :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-04   NUWE :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-05   RGTX :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-05   NBIG :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-05   BAIG :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-05   RIOX :A SQS=5(A) risk=$750 P&L=$+1,507
  2026-02-05    MST :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-05   SXTC :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-05   SOUX :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-05   NUWE :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-05   CRWG :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-02-06     MB :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-02-12   RGTX :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-02-12   ASTI :A SQS=4(B) risk=$250 P&L=$-24 [B-GATE:PASS]
  2026-02-12   HOOX :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-12   CRMX :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-18   BENF :A SQS=7(Shelved) risk=$250 P&L=$+0
  2026-02-18   OBAI :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-18   UGRO :A SQS=6(A) risk=$750 P&L=$+0
  2026-02-18   PLYX :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-19   BENF :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-02-20   NBIG :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-02-20   EDHL :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-20   CRWG :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-02-20   AGIG :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-02-23   ABTS :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-23   ANPA :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-02-23   BESS :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-27   MRAL :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-02-27   SOUX :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-27   NBIG :A SQS=5(A) risk=$750 P&L=$+0
  2026-02-27   CRWG :B SQS=5(A) risk=$750 P&L=$+0
```
