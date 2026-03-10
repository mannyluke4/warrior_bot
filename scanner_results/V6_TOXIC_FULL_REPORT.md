# V6.1 Toxic Entry Filters — Full Re-Run Report

**Date:** 2026-03-09
**Branch:** v6-dynamic-sizing
**Dataset:** Oct 2025 – Feb 2026 (102 trading days)
**Change:** ALL 102 dates re-run fresh with toxic filters active
**Previous:** Jan-Feb was loaded from V4 cache (filters not applied)

## V4 Baseline vs V6.1 Full Comparison

| Metric | V4 Baseline | V6.1 Full | Change |
|--------|------------|-----------|--------|
| **Total P&L** | **$+5,798** | **$+5,425** | $-373 |
| Total Sims | 166 | 166 | +0 |
| Active Trades | 31 | 28 | -3 |
| Win Rate | 41.9% | 46.4% | +4.5pp |
| Max Drawdown | $2,987 (9.8%) | $5,355 (17.3%) | $+2,368 |
| Ending Equity | $35,798 | $35,425 | $-373 |

## Filter 1 Catches: Wide R% + Crowded Day → HARD BLOCK
**Condition:** R% >= 5.0% AND scanner candidates >= 20

No Filter 1 catches detected in output files.
(Note: blocked trades may show $0 P&L — check sim output for TOXIC BLOCK lines)

## Filter 2 Catches: Cold + Low Vol + Small Gap → HALF RISK
**Condition:** gap < 30% AND pm_volume < 100K AND month in {Feb, Oct, Nov}

No Filter 2 catches detected in output files.

## Key Jan-Feb Targets

- MLEC 2026-01-16 (R%=7.1%, 25 candidates): **N/A** — classifier blocked as "avoid" (0 signals, 0 trades)
- FEED 2026-01-09 (R%=6.4%, 21 candidates): **N/A** — armed 4 times but 0 signals fired (0 trades)

**Note:** Both MLEC and FEED generated zero entry signals with current code, so the toxic
filters never had a chance to fire. The projected losses (-$788 MLEC, -$750 FEED) from the
directive analysis were based on earlier code. With current V4 code (classifier + exhaustion
filter + signal mode), these stocks self-filter before reaching the toxic entry check.

**Conclusion:** Toxic filters had **zero** impact across all 102 days. All 5 originally-targeted
stocks (BODI, GLXG, ATON, BQ, AVX) also show different P&L than the directive analysis,
suggesting the targets were identified from a prior code version. The current V4 codebase
already handles these cases through classifier gates and signal quality.

## Monthly Breakdown

| Month | Days | Sims | Active | W/L | P&L | Best Day | Worst Day |
|-------|------|------|--------|-----|-----|----------|-----------|
| 2025-10 | 23 | 33 | 4 | 3/1 | $+890 | 2025-10-14 ($+983) | 2025-10-10 ($-394) |
| 2025-11 | 19 | 25 | 7 | 0/7 | $-5,355 | 2025-11-25 ($+0) | 2025-11-11 ($-1,572) |
| 2025-12 | 22 | 45 | 10 | 6/4 | $+2,081 | 2025-12-12 ($+1,221) | 2025-12-31 ($-612) |
| 2026-01 | 19 | 27 | 4 | 3/1 | $+6,594 | 2026-01-16 ($+5,786) | 2026-01-23 ($-147) |
| 2026-02 | 19 | 36 | 3 | 1/2 | $+1,215 | 2026-02-05 ($+1,507) | 2026-02-02 ($-268) |

## Equity Curve Summary

| Metric | Value |
|--------|-------|
| Starting Balance | $30,000 |
| Ending Balance | $35,425 |
| Total Return | +18.1% |
| Peak Balance | $35,449 (2026-02-05) |
| Max Drawdown | $5,355 (17.3%) |
| Max Win Streak | 3 days |
| Max Lose Streak | 6 days |

## Tier Performance

| Tier | Sims | W/L | P&L | Avg Win | Avg Loss |
|------|------|-----|-----|---------|----------|
| Shelved | 8 | 0/2 | $-397 | $+0 | $-198 |
| A | 114 | 10/10 | $+5,304 | $+1,217 | $-687 |
| B | 44 | 3/3 | $+518 | $+306 | $-133 |

## Monster Trades (|P&L| > $1,000)

**3 monster winners, 3 monster losers**

| Date | Symbol | Profile | Tier | Risk | P&L |
|------|--------|---------|------|------|-----|
| 2026-01-16 | GWAV | A | A (SQS=6) | $750 | $+5,786 |
| 2025-12-12 | KPLT | A | A (SQS=6) | $750 | $+1,585 |
| 2026-02-05 | RIOX | A | A (SQS=5) | $750 | $+1,507 |
| 2025-11-14 | IONZ | B | A (SQS=5) | $750 | $-1,026 |
| 2025-11-05 | BQ | A | A (SQS=6) | $750 | $-1,544 |
| 2025-11-11 | CRWG | B | A (SQS=5) | $750 | $-1,572 |

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
| 2025-10-14 | $+983 | 3 | JDZG:A SQS=6(A) $750 P&L=$+720; RGTZ:A SQS=5(A) $750 P&L=$+0; CYN:B SQS=4(B) $250 P&L=$+263 [B-GATE:PASS] |
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
| 2025-11-06 | $-542 | 5 | CRCG:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; AVX:A SQS=5(A) $750 P&L=$-417; GNPX:A SQS=5(A) $750 P&L=$+0; BMNG:A SQS=5(A) $750 P&L=$+0; CRWG:B SQS=4(B) $250 P&L=$-125 [B-GATE:PASS] |
| 2025-11-07 | $-554 | 1 | MSGM:A SQS=6(A) $750 P&L=$-554 |
| 2025-11-11 | $-1,572 | 2 | BODI:A SQS=5(A) $750 P&L=$+0; CRWG:B SQS=5(A) $750 P&L=$-1,572 |
| 2025-11-13 | $+0 | 2 | CMCT:A SQS=5(A) $750 P&L=$+0; BMNG:A SQS=5(A) $750 P&L=$+0 |
| 2025-11-14 | $-1,026 | 2 | ARBB:A SQS=6(A) $750 P&L=$+0; IONZ:B SQS=5(A) $750 P&L=$-1,026 |
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
| 2026-01-09 | $+0 | 3 | ICON:A SQS=7(Shelved) $250 P&L=$+0; CETX:A SQS=7(Shelved) $250 P&L=$+0; FEED:A SQS=6(A) $750 P&L=$+0 |
| 2026-01-13 | $+0 | 1 | ATRA:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2026-01-15 | $+0 | 2 | AGPU:A SQS=5(A) $750 P&L=$+0; BMNG:A SQS=5(A) $750 P&L=$+0 |
| 2026-01-16 | $+5,786 | 3 | GWAV:A SQS=6(A) $750 P&L=$+5,786; RAYA:A SQS=5(A) $750 P&L=$+0; MLEC:A SQS=5(A) $750 P&L=$+0 |
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
  2025-10-14    CYN :B SQS=4(B) risk=$250 P&L=$+263 [B-GATE:PASS]
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
  2025-11-06   CRWG :B SQS=4(B) risk=$250 P&L=$-125 [B-GATE:PASS]
  2025-11-07   MSGM :A SQS=6(A) risk=$750 P&L=$-554
  2025-11-11   BODI :A SQS=5(A) risk=$750 P&L=$+0
  2025-11-11   CRWG :B SQS=5(A) risk=$750 P&L=$-1,572
  2025-11-13   CMCT :A SQS=5(A) risk=$750 P&L=$+0
  2025-11-13   BMNG :A SQS=5(A) risk=$750 P&L=$+0
  2025-11-14   ARBB :A SQS=6(A) risk=$750 P&L=$+0
  2025-11-14   IONZ :B SQS=5(A) risk=$750 P&L=$-1,026
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
  2026-01-09   FEED :A SQS=6(A) risk=$750 P&L=$+0
  2026-01-13   ATRA :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2026-01-15   AGPU :A SQS=5(A) risk=$750 P&L=$+0
  2026-01-15   BMNG :A SQS=5(A) risk=$750 P&L=$+0
  2026-01-16   GWAV :A SQS=6(A) risk=$750 P&L=$+5,786
  2026-01-16   RAYA :A SQS=5(A) risk=$750 P&L=$+0
  2026-01-16   MLEC :A SQS=5(A) risk=$750 P&L=$+0
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
