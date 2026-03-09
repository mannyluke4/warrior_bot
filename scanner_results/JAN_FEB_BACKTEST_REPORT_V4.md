# Jan/Feb 2026 Backtest Report — V4 (Tier Restructure + B-Tier Quality Gate)

**Generated:** 2026-03-09
**Branch:** scanner-sim-backtest
**Dates:** Jan 2 – Feb 27, 2026 (38 trading days)

## Version Comparison

| Metric | V1 (No Filters) | V2 (Protective) | V3 (SQS + PM Sort) | V4 (Tier Restructure) |
|--------|-----------------|-----------------|---------------------|-----------------------|
| **Total P&L** | -$17,885 | -$8,938 | +$566 | **$+5,402** |
| Total Sims | 51 | 161 | 26 | 63 |
| Winners | 9 | 7 | 8 | 4 |
| Losers | — | 18 | 17 | 6 |
| Win Rate | 17.6% | 4.3% | 30.8% | 6.3% |
| Profitable Days | 2/19 | 3/30 | 5/15 | 4/23 |
| Cold Market Skips | 0 | 8 | 8 | 8 |
| Kill Switch Fires | 0 | 2 | 2 | 0 |

## V4 Tier Distribution

| Tier | SQS Range | Risk | Traded | P&L |
|------|-----------|------|--------|-----|
| Shelved (SQS 7-9) | $250 | 4 | $-147 |
| A-tier (SQS 5-6) | $750 | 42 | $+4,990 |
| B-tier (SQS 4 (gated)) | $250 | 17 | $+559 |
| B-GATE SKIP | SQS 4, failed gate | — | 56 blocked |
| SQS SKIP | SQS 0-3 | — | 48 skipped |
| **Total Traded** | | **63** | **$+5,402** |

## B-Tier Quality Gate Stats

- **Gate:** gap >= 14% AND pm_vol >= 10,000 (applies to SQS=4 only)
- **Passed:** 17
- **Blocked:** 56
- **B-tier P&L (passed only):** $+559

## Kill Switch Analysis

No kill switch activations.

## Per-Day Breakdown

| Date | Day P&L | Sims | Details |
|------|---------|------|---------|
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

## Cold Market Days Skipped

- 2026-01-03
- 2026-01-05
- 2026-01-08
- 2026-01-12
- 2026-01-14
- 2026-01-27
- 2026-02-03
- 2026-02-09
- 2026-02-10
- 2026-02-11
- 2026-02-13
- 2026-02-17
- 2026-02-24
- 2026-02-25
- 2026-02-26

## Per-Sim Detail

```
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
