# Jan/Feb 2026 Backtest Report — V3 (SQS + PM Volume Sort)

**Generated:** 2026-03-09
**Branch:** scanner-sim-backtest
**Dates:** Jan 2 – Feb 27, 2026 (38 trading days)

## Version Comparison

| Metric | V1 (No Filters) | V2 (Protective) | V3 (SQS + PM Sort) |
|--------|-----------------|-----------------|---------------------|
| **Total P&L** | -$17,885 | -$8,938 | **$+566** |
| Total Sims | 51 | 161 | 154 |
| Winners | 9 | 7 | 8 |
| Losers | — | 18 | 18 |
| Win Rate | 17.6% | 4.3% | 5.2% |
| Profitable Days | 2/19 | 3/30 | 5/30 |
| Cold Market Skips | 0 | 8 | 8 |
| Kill Switch Fires | 0 | 2 | 0 |

## SQS Distribution

| Tier | SQS Range | Risk | Count | P&L |
|------|-----------|------|-------|-----|
| A+ (7-9) | $1,000 | 4 | $-588 |
| B (5-6) | $500 | 42 | $+3,328 |
| C (3-4) | $250 | 108 | $-2,174 |
| Skip (0-2) | $0 | 13 | N/A |
| **Total** | | 167 | $+566 |

## Kill Switch Analysis

No kill switch activations.

## Per-Day Breakdown

| Date | Day P&L | Sims | Details |
|------|---------|------|---------|
| 2026-01-02 | $+105 | 5 | QBTZ:A SQS=5(B) $500 P&L=$+248; EKSO:A SQS=4(C) $250 P&L=$-151; AMCI:A SQS=4(C) $250 P&L=$+0; RAIN:A SQS=3(C) $250 P&L=$+0; SOPA:B SQS=3(C) $250 P&L=$+8 |
| 2026-01-06 | $+0 | 1 | NOMA:A SQS=5(B) $500 P&L=$+0 |
| 2026-01-07 | $-250 | 6 | BMNG:A SQS=6(B) $500 P&L=$+0; ASTI:A SQS=4(C) $250 P&L=$+0; BNAI:A SQS=4(C) $250 P&L=$+0; DWTX:A SQS=4(C) $250 P&L=$+0; ANGH:A SQS=4(C) $250 P&L=$-250; VNCE:A SQS=3(C) $250 P&L=$+0 |
| 2026-01-09 | $-500 | 6 | ICON:A SQS=7(A+) $1000 P&L=$+0; CETX:A SQS=7(A+) $1000 P&L=$+0; FEED:A SQS=6(B) $500 P&L=$-500; MST:A SQS=4(C) $250 P&L=$+0; RBNE:A SQS=3(C) $250 P&L=$+0; HIMZ:B SQS=3(C) $250 P&L=$+0 |
| 2026-01-12 | $+0 | 1 | CLNN:B SQS=3(C) $250 P&L=$+0 |
| 2026-01-13 | $+203 | 5 | ADBG:A SQS=3(C) $250 P&L=$+0; ATRA:A SQS=4(C) $250 P&L=$+0; ELAB:A SQS=4(C) $250 P&L=$-426; WATT:A SQS=4(C) $250 P&L=$+629; FIGG:A SQS=3(C) $250 P&L=$+0 |
| 2026-01-15 | $-90 | 3 | AGPU:A SQS=5(B) $500 P&L=$-90; BMNG:A SQS=5(B) $500 P&L=$+0; AGIG:B SQS=3(C) $250 P&L=$+0 |
| 2026-01-16 | $+2,269 | 8 | GWAV:A SQS=6(B) $500 P&L=$+3,369; RAYA:A SQS=5(B) $500 P&L=$+0; MLEC:A SQS=5(B) $500 P&L=$-525; GNPX:A SQS=4(C) $250 P&L=$+0; ELAB:A SQS=3(C) $250 P&L=$+0; JL:A SQS=4(C) $250 P&L=$-575; RGNT:A SQS=3(C) $250 P&L=$+0; FIGG:A SQS=3(C) $250 P&L=$+0 |
| 2026-01-21 | $+111 | 4 | BAOS:A SQS=4(C) $250 P&L=$+583; CJMB:A SQS=4(C) $250 P&L=$-472; MNTS:A SQS=4(C) $250 P&L=$+0; HIMZ:B SQS=3(C) $250 P&L=$+0 |
| 2026-01-22 | $+0 | 6 | RAYA:A SQS=6(B) $500 P&L=$+0; EVTV:A SQS=4(C) $250 P&L=$+0; NBIG:A SQS=4(C) $250 P&L=$+0; QSU:A SQS=3(C) $250 P&L=$+0; CRWG:B SQS=3(C) $250 P&L=$+0; GDXD:B SQS=3(C) $250 P&L=$+0 |
| 2026-01-23 | $-588 | 2 | DRCT:A SQS=7(A+) $1000 P&L=$-588; MNTS:A SQS=4(C) $250 P&L=$+0 |
| 2026-01-26 | $-323 | 9 | DRCT:A SQS=5(B) $500 P&L=$+0; QCLS:A SQS=4(C) $250 P&L=$-23; ASTI:A SQS=4(C) $250 P&L=$-300; MLEC:A SQS=4(C) $250 P&L=$+0; VMAR:A SQS=5(B) $500 P&L=$+0; IOTR:A SQS=4(C) $250 P&L=$+0; XCUR:A SQS=3(C) $250 P&L=$+0; TNMG:A SQS=4(C) $250 P&L=$+0; HUBC:A SQS=5(B) $500 P&L=$+0 |
| 2026-01-27 | $+0 | 1 | DRCT:A SQS=4(C) $250 P&L=$+0 |
| 2026-01-28 | $-837 | 6 | MKDW:A SQS=4(C) $250 P&L=$+0; ENVB:A SQS=5(B) $500 P&L=$+0; ASTI:A SQS=3(C) $250 P&L=$-529; GRI:A SQS=4(C) $250 P&L=$+0; CGTL:A SQS=4(C) $250 P&L=$+0; CRWG:B SQS=3(C) $250 P&L=$-308 |
| 2026-01-29 | $+0 | 10 | SER:A SQS=6(B) $500 P&L=$+0; BMNG:A SQS=6(B) $500 P&L=$+0; ROLR:A SQS=3(C) $250 P&L=$+0; GRI:A SQS=4(C) $250 P&L=$+0; NBIG:A SQS=4(C) $250 P&L=$+0; DRCT:A SQS=4(C) $250 P&L=$+0; SOUX:A SQS=4(C) $250 P&L=$+0; MST:A SQS=5(B) $500 P&L=$+0; NAMM:B SQS=5(B) $500 P&L=$+0; CRWG:B SQS=3(C) $250 P&L=$+0 |
| 2026-02-02 | $-346 | 9 | FEED:A SQS=6(B) $500 P&L=$-179; GRI:A SQS=4(C) $250 P&L=$+0; IOTR:A SQS=4(C) $250 P&L=$+0; MNTS:A SQS=4(C) $250 P&L=$-167; SXTP:A SQS=5(B) $500 P&L=$+0; MKDW:A SQS=4(C) $250 P&L=$+0; ACON:A SQS=4(C) $250 P&L=$+0; BTOG:A SQS=5(B) $500 P&L=$+0; BATL:B SQS=4(C) $250 P&L=$+0 |
| 2026-02-03 | $+0 | 6 | CRMG:A SQS=4(C) $250 P&L=$+0; ADBG:A SQS=3(C) $250 P&L=$+0; MST:A SQS=4(C) $250 P&L=$+0; IOTR:A SQS=4(C) $250 P&L=$+0; UUU:A SQS=4(C) $250 P&L=$+0; NAMM:B SQS=3(C) $250 P&L=$+0 |
| 2026-02-04 | $-18 | 9 | RGTX:A SQS=4(C) $250 P&L=$+0; MRAL:A SQS=3(C) $250 P&L=$+0; ASTI:A SQS=3(C) $250 P&L=$+85; MPL:A SQS=4(C) $250 P&L=$+0; XCUR:A SQS=3(C) $250 P&L=$-259; BAIG:A SQS=5(B) $500 P&L=$+0; NUWE:A SQS=5(B) $500 P&L=$+0; RIOX:A SQS=4(C) $250 P&L=$+0; CRWG:B SQS=3(C) $250 P&L=$+156 |
| 2026-02-05 | $+1,005 | 14 | RGTX:A SQS=5(B) $500 P&L=$+0; CRMG:A SQS=4(C) $250 P&L=$+0; NBIG:A SQS=5(B) $500 P&L=$+0; BAIG:A SQS=5(B) $500 P&L=$+0; RIOX:A SQS=5(B) $500 P&L=$+1,005; HOOX:A SQS=4(C) $250 P&L=$+0; MST:A SQS=5(B) $500 P&L=$+0; SXTC:A SQS=5(B) $500 P&L=$+0; SOUX:A SQS=5(B) $500 P&L=$+0; ROLR:A SQS=3(C) $250 P&L=$+0; NUWE:A SQS=5(B) $500 P&L=$+0; MPL:A SQS=4(C) $250 P&L=$+0; CRWG:B SQS=4(C) $250 P&L=$+0; NAMM:B SQS=3(C) $250 P&L=$+0 |
| 2026-02-06 | $+0 | 2 | MB:A SQS=4(C) $250 P&L=$+0; GDXD:B SQS=3(C) $250 P&L=$+0 |
| 2026-02-11 | $+0 | 5 | PLYX:A SQS=4(C) $250 P&L=$+0; FEED:A SQS=4(C) $250 P&L=$+0; PHGE:A SQS=4(C) $250 P&L=$+0; RVSN:A SQS=4(C) $250 P&L=$+0; EDHL:A SQS=4(C) $250 P&L=$+0 |
| 2026-02-12 | $-24 | 10 | RGTX:A SQS=4(C) $250 P&L=$+0; ASTI:A SQS=4(C) $250 P&L=$-24; HOOX:A SQS=5(B) $500 P&L=$+0; STI:A SQS=3(C) $250 P&L=$+0; RIOX:A SQS=4(C) $250 P&L=$+0; PLYX:A SQS=4(C) $250 P&L=$+0; SOUX:A SQS=4(C) $250 P&L=$+0; SLON:A SQS=4(C) $250 P&L=$+0; CRMX:A SQS=5(B) $500 P&L=$+0; BAIG:A SQS=4(C) $250 P&L=$+0 |
| 2026-02-13 | $-151 | 2 | ASTI:A SQS=3(C) $250 P&L=$-151; CRMX:A SQS=4(C) $250 P&L=$+0 |
| 2026-02-17 | $+0 | 2 | QSU:A SQS=3(C) $250 P&L=$+0; NAII:A SQS=4(C) $250 P&L=$+0 |
| 2026-02-18 | $+0 | 4 | BENF:A SQS=7(A+) $1000 P&L=$+0; OBAI:A SQS=5(B) $500 P&L=$+0; UGRO:A SQS=6(B) $500 P&L=$+0; PLYX:A SQS=5(B) $500 P&L=$+0 |
| 2026-02-19 | $+0 | 1 | BENF:A SQS=4(C) $250 P&L=$+0 |
| 2026-02-20 | $+0 | 7 | NBIG:A SQS=4(C) $250 P&L=$+0; MPL:A SQS=4(C) $250 P&L=$+0; BAIG:A SQS=4(C) $250 P&L=$+0; EDHL:A SQS=5(B) $500 P&L=$+0; ROLR:A SQS=3(C) $250 P&L=$+0; CRWG:B SQS=4(C) $250 P&L=$+0; AGIG:B SQS=4(C) $250 P&L=$+0 |
| 2026-02-23 | $+0 | 3 | ABTS:A SQS=5(B) $500 P&L=$+0; ANPA:A SQS=4(C) $250 P&L=$+0; BESS:A SQS=5(B) $500 P&L=$+0 |
| 2026-02-26 | $+0 | 1 | NCI:A SQS=4(C) $250 P&L=$+0 |
| 2026-02-27 | $+0 | 6 | MRAL:A SQS=4(C) $250 P&L=$+0; SOUX:A SQS=5(B) $500 P&L=$+0; NBIG:A SQS=5(B) $500 P&L=$+0; CRMX:A SQS=4(C) $250 P&L=$+0; FOFO:A SQS=3(C) $250 P&L=$+0; CRWG:B SQS=5(B) $500 P&L=$+0 |

## Cold Market Days Skipped

- 2026-01-03
- 2026-01-05
- 2026-01-08
- 2026-01-14
- 2026-02-09
- 2026-02-10
- 2026-02-24
- 2026-02-25

## Per-Sim Detail

```
  2026-01-02   QBTZ :A SQS=5(B) risk=$500 P&L=$+248
  2026-01-02   EKSO :A SQS=4(C) risk=$250 P&L=$-151
  2026-01-02   AMCI :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-02   RAIN :A SQS=3(C) risk=$250 P&L=$+0
  2026-01-02   SOPA :B SQS=3(C) risk=$250 P&L=$+8
  2026-01-06   NOMA :A SQS=5(B) risk=$500 P&L=$+0
  2026-01-07   BMNG :A SQS=6(B) risk=$500 P&L=$+0
  2026-01-07   ASTI :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-07   BNAI :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-07   DWTX :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-07   ANGH :A SQS=4(C) risk=$250 P&L=$-250
  2026-01-07   VNCE :A SQS=3(C) risk=$250 P&L=$+0
  2026-01-09   ICON :A SQS=7(A+) risk=$1000 P&L=$+0
  2026-01-09   CETX :A SQS=7(A+) risk=$1000 P&L=$+0
  2026-01-09   FEED :A SQS=6(B) risk=$500 P&L=$-500
  2026-01-09    MST :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-09   RBNE :A SQS=3(C) risk=$250 P&L=$+0
  2026-01-09   HIMZ :B SQS=3(C) risk=$250 P&L=$+0
  2026-01-12   CLNN :B SQS=3(C) risk=$250 P&L=$+0
  2026-01-13   ADBG :A SQS=3(C) risk=$250 P&L=$+0
  2026-01-13   ATRA :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-13   ELAB :A SQS=4(C) risk=$250 P&L=$-426
  2026-01-13   WATT :A SQS=4(C) risk=$250 P&L=$+629
  2026-01-13   FIGG :A SQS=3(C) risk=$250 P&L=$+0
  2026-01-15   AGPU :A SQS=5(B) risk=$500 P&L=$-90
  2026-01-15   BMNG :A SQS=5(B) risk=$500 P&L=$+0
  2026-01-15   AGIG :B SQS=3(C) risk=$250 P&L=$+0
  2026-01-16   GWAV :A SQS=6(B) risk=$500 P&L=$+3,369
  2026-01-16   RAYA :A SQS=5(B) risk=$500 P&L=$+0
  2026-01-16   MLEC :A SQS=5(B) risk=$500 P&L=$-525
  2026-01-16   GNPX :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-16   ELAB :A SQS=3(C) risk=$250 P&L=$+0
  2026-01-16     JL :A SQS=4(C) risk=$250 P&L=$-575
  2026-01-16   RGNT :A SQS=3(C) risk=$250 P&L=$+0
  2026-01-16   FIGG :A SQS=3(C) risk=$250 P&L=$+0
  2026-01-21   BAOS :A SQS=4(C) risk=$250 P&L=$+583
  2026-01-21   CJMB :A SQS=4(C) risk=$250 P&L=$-472
  2026-01-21   MNTS :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-21   HIMZ :B SQS=3(C) risk=$250 P&L=$+0
  2026-01-22   RAYA :A SQS=6(B) risk=$500 P&L=$+0
  2026-01-22   EVTV :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-22   NBIG :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-22    QSU :A SQS=3(C) risk=$250 P&L=$+0
  2026-01-22   CRWG :B SQS=3(C) risk=$250 P&L=$+0
  2026-01-22   GDXD :B SQS=3(C) risk=$250 P&L=$+0
  2026-01-23   DRCT :A SQS=7(A+) risk=$1000 P&L=$-588
  2026-01-23   MNTS :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-26   DRCT :A SQS=5(B) risk=$500 P&L=$+0
  2026-01-26   QCLS :A SQS=4(C) risk=$250 P&L=$-23
  2026-01-26   ASTI :A SQS=4(C) risk=$250 P&L=$-300
  2026-01-26   MLEC :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-26   VMAR :A SQS=5(B) risk=$500 P&L=$+0
  2026-01-26   IOTR :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-26   XCUR :A SQS=3(C) risk=$250 P&L=$+0
  2026-01-26   TNMG :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-26   HUBC :A SQS=5(B) risk=$500 P&L=$+0
  2026-01-27   DRCT :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-28   MKDW :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-28   ENVB :A SQS=5(B) risk=$500 P&L=$+0
  2026-01-28   ASTI :A SQS=3(C) risk=$250 P&L=$-529
  2026-01-28    GRI :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-28   CGTL :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-28   CRWG :B SQS=3(C) risk=$250 P&L=$-308
  2026-01-29    SER :A SQS=6(B) risk=$500 P&L=$+0
  2026-01-29   BMNG :A SQS=6(B) risk=$500 P&L=$+0
  2026-01-29   ROLR :A SQS=3(C) risk=$250 P&L=$+0
  2026-01-29    GRI :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-29   NBIG :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-29   DRCT :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-29   SOUX :A SQS=4(C) risk=$250 P&L=$+0
  2026-01-29    MST :A SQS=5(B) risk=$500 P&L=$+0
  2026-01-29   NAMM :B SQS=5(B) risk=$500 P&L=$+0
  2026-01-29   CRWG :B SQS=3(C) risk=$250 P&L=$+0
  2026-02-02   FEED :A SQS=6(B) risk=$500 P&L=$-179
  2026-02-02    GRI :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-02   IOTR :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-02   MNTS :A SQS=4(C) risk=$250 P&L=$-167
  2026-02-02   SXTP :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-02   MKDW :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-02   ACON :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-02   BTOG :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-02   BATL :B SQS=4(C) risk=$250 P&L=$+0
  2026-02-03   CRMG :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-03   ADBG :A SQS=3(C) risk=$250 P&L=$+0
  2026-02-03    MST :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-03   IOTR :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-03    UUU :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-03   NAMM :B SQS=3(C) risk=$250 P&L=$+0
  2026-02-04   RGTX :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-04   MRAL :A SQS=3(C) risk=$250 P&L=$+0
  2026-02-04   ASTI :A SQS=3(C) risk=$250 P&L=$+85
  2026-02-04    MPL :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-04   XCUR :A SQS=3(C) risk=$250 P&L=$-259
  2026-02-04   BAIG :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-04   NUWE :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-04   RIOX :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-04   CRWG :B SQS=3(C) risk=$250 P&L=$+156
  2026-02-05   RGTX :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-05   CRMG :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-05   NBIG :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-05   BAIG :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-05   RIOX :A SQS=5(B) risk=$500 P&L=$+1,005
  2026-02-05   HOOX :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-05    MST :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-05   SXTC :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-05   SOUX :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-05   ROLR :A SQS=3(C) risk=$250 P&L=$+0
  2026-02-05   NUWE :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-05    MPL :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-05   CRWG :B SQS=4(C) risk=$250 P&L=$+0
  2026-02-05   NAMM :B SQS=3(C) risk=$250 P&L=$+0
  2026-02-06     MB :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-06   GDXD :B SQS=3(C) risk=$250 P&L=$+0
  2026-02-11   PLYX :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-11   FEED :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-11   PHGE :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-11   RVSN :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-11   EDHL :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-12   RGTX :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-12   ASTI :A SQS=4(C) risk=$250 P&L=$-24
  2026-02-12   HOOX :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-12    STI :A SQS=3(C) risk=$250 P&L=$+0
  2026-02-12   RIOX :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-12   PLYX :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-12   SOUX :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-12   SLON :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-12   CRMX :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-12   BAIG :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-13   ASTI :A SQS=3(C) risk=$250 P&L=$-151
  2026-02-13   CRMX :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-17    QSU :A SQS=3(C) risk=$250 P&L=$+0
  2026-02-17   NAII :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-18   BENF :A SQS=7(A+) risk=$1000 P&L=$+0
  2026-02-18   OBAI :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-18   UGRO :A SQS=6(B) risk=$500 P&L=$+0
  2026-02-18   PLYX :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-19   BENF :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-20   NBIG :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-20    MPL :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-20   BAIG :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-20   EDHL :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-20   ROLR :A SQS=3(C) risk=$250 P&L=$+0
  2026-02-20   CRWG :B SQS=4(C) risk=$250 P&L=$+0
  2026-02-20   AGIG :B SQS=4(C) risk=$250 P&L=$+0
  2026-02-23   ABTS :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-23   ANPA :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-23   BESS :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-26    NCI :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-27   MRAL :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-27   SOUX :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-27   NBIG :A SQS=5(B) risk=$500 P&L=$+0
  2026-02-27   CRMX :A SQS=4(C) risk=$250 P&L=$+0
  2026-02-27   FOFO :A SQS=3(C) risk=$250 P&L=$+0
  2026-02-27   CRWG :B SQS=5(B) risk=$500 P&L=$+0
```
