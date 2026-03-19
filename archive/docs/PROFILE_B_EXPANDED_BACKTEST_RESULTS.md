# V6.2 Expanded Backtest Results — Jan-Aug 2025

**Generated:** 2026-03-10
**Branch:** v6-dynamic-sizing
**Dates:** Jan 2 – Aug 21, 2025 (158 trading days)
**Engine:** simulate.py --ticks (tick-by-tick replay)
**V6.2 Rules:** V4 tiers + Profile B $250 risk cap

## 1. Profile B Candidate Funnel (Jan-Aug 2025)

| Stage | Count |
|-------|-------|
| Scanner B candidates (float 5-10M) | 644 |
| Pass price + gap + PM vol filter | 173 |
| Survive SQS + B-gate | 31 |
| B-gate blocked | 79 |
| Actually simulated | 10 |
| Active trades (P&L != $0) | 3 |

## 2. Profile B Per-Trade Detail (Jan-Aug 2025)

| Date | Symbol | SQS | Tier | Risk | P&L | Notes |
|------|--------|-----|------|------|-----|-------|
| 2025-02-18 | AIFF | 4 | B | $250 | $-26 | ACTIVE |
| 2025-03-03 | BTCT | 4 | B | $250 | $+0 | flat |
| 2025-03-18 | AIFF | 4 | B | $250 | $+0 | flat |
| 2025-04-10 | BLIV | 4 | B | $250 | $+0 | flat |
| 2025-06-05 | VBIX | 4 | B | $250 | $+0 | flat |
| 2025-06-16 | INDO | 4 | B | $250 | $+0 | flat |
| 2025-06-23 | INDO | 5 | A | $250 | $+504 | ACTIVE |
| 2025-07-17 | VWAV | 4 | B | $250 | $+0 | flat |
| 2025-08-15 | PPSI | 4 | B | $250 | $+0 | flat |
| 2025-08-15 | NA | 4 | B | $250 | $+916 | ACTIVE |

## 3. Profile B Summary (Jan-Aug 2025)

| Metric | Value |
|--------|-------|
| Total B sims | 10 |
| Active B trades (P&L != $0) | 3 |
| B wins | 2 |
| B losses | 1 |
| B win rate | 66.7% |
| B total P&L | $+1,394 |
| B avg win | $+710 |
| B avg loss | $-26 |

## 4. Combined Profile B (Jan-Aug 2025 + Oct-Feb 2026)

| Metric | Oct-Feb 2026 | Jan-Aug 2025 | Combined |
|--------|-------------|-------------|----------|
| Total B sims | 16 | 10 | 26 |
| Active B trades | 2 | 3 | 5 |
| B total P&L | $+327 | $+1,394 | $+1,721 |

## 5. Profile A Comparison (Jan-Aug 2025)

| Metric | Profile A | Profile B |
|--------|-----------|-----------|
| Total sims | 91 | 10 |
| Active trades | 27 | 3 |
| Winners | 6 | 2 |
| Losers | 21 | 1 |
| Win rate | 22.2% | 66.7% |
| Total P&L | $-6,218 | $+1,394 |
| Avg win | $+377 | $+710 |
| Avg loss | $-404 | $-26 |

## 6. Decision Point

**5 active Profile B trades** — sample size still too small.

Next steps: widen filters:
- Raise float ceiling from 10M to 15M
- Raise gap cap from 25% to 35%
- Raise max-per-day from 2 to 3
- Re-run the full backtest with wider filters

## 7. Overall Headline Metrics (Jan-Aug 2025)

| Metric | Value |
|--------|-------|
| **Total P&L** | **$-4,824** |
| Total Sims | 101 |
| Active Trades | 30 |
| Winners | 8 |
| Losers | 22 |
| Win Rate (active) | 26.7% |
| Profitable Days | 8/65 |
| Cold Market Skips | 52 |
| Kill Switch Fires | 0 |

## 8. Tier Performance

| Tier | Sims | P&L |
|------|------|-----|
| Shelved | 12 | $-174 |
| A | 58 | $-4,227 |
| B | 31 | $-423 |
| B-gate blocked | 79 | N/A |
| SQS skip (0-3) | 164 | N/A |

## 9. Monthly Breakdown

| Month | Sims | W/L | P&L | B Sims | B Active |
|-------|------|-----|-----|--------|----------|
| 2025-01 | 7 | 0/2 | $-910 | 0 | 0 |
| 2025-02 | 11 | 3/2 | $+278 | 1 | 1 |
| 2025-03 | 8 | 0/3 | $-839 | 2 | 0 |
| 2025-04 | 7 | 0/2 | $-1,665 | 1 | 0 |
| 2025-05 | 6 | 1/0 | $+855 | 0 | 0 |
| 2025-06 | 28 | 2/8 | $-2,468 | 3 | 1 |
| 2025-07 | 25 | 1/3 | $-159 | 1 | 0 |
| 2025-08 | 9 | 1/2 | $+84 | 2 | 1 |

## 10. Per-Day Breakdown

| Date | Day P&L | Sims | Details |
|------|---------|------|---------|
| 2025-01-02 | $+0 | 2 | COEP:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; BYAH:A SQS=5(A) $750 P&L=$+0 |
| 2025-01-06 | $+0 | 1 | BAOS:A SQS=6(A) $750 P&L=$+0 |
| 2025-01-13 | $+0 | 1 | TRAW:A SQS=5(A) $750 P&L=$+0 |
| 2025-01-23 | $-886 | 1 | ALOY:A SQS=5(A) $750 P&L=$-886 |
| 2025-01-24 | $-24 | 1 | VNCE:A SQS=4(B) $250 P&L=$-24 [B-GATE:PASS] |
| 2025-01-28 | $+0 | 1 | CDT:A SQS=6(A) $750 P&L=$+0 |
| 2025-02-03 | $+0 | 1 | REBN:A SQS=6(A) $750 P&L=$+0 |
| 2025-02-05 | $+0 | 1 | KTTA:A SQS=6(A) $750 P&L=$+0 |
| 2025-02-11 | $+0 | 1 | RAIN:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-02-18 | $-97 | 2 | JTAI:A SQS=4(B) $250 P&L=$-71 [B-GATE:PASS]; AIFF:B SQS=4(B) $250 P&L=$-26 [B-GATE:PASS] |
| 2025-02-20 | $+3 | 1 | JTAI:A SQS=6(A) $750 P&L=$+3 |
| 2025-02-21 | $+0 | 3 | TANH:A SQS=6(A) $750 P&L=$+0; REBN:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; JZXN:A SQS=5(A) $750 P&L=$+0 |
| 2025-02-25 | $+64 | 1 | WAFU:A SQS=7(Shelved) $250 P&L=$+64 |
| 2025-02-26 | $+308 | 1 | RNAZ:A SQS=5(A) $750 P&L=$+308 |
| 2025-03-03 | $+0 | 1 | BTCT:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-03-06 | $-750 | 1 | GV:A SQS=6(A) $750 P&L=$-750 |
| 2025-03-10 | $-64 | 2 | GV:A SQS=5(A) $750 P&L=$+0; RETO:A SQS=5(A) $750 P&L=$-64 |
| 2025-03-11 | $-25 | 1 | SNOA:A SQS=7(Shelved) $250 P&L=$-25 |
| 2025-03-18 | $+0 | 2 | IPDN:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; AIFF:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-03-28 | $+0 | 1 | SMTK:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-04-08 | $-1,500 | 1 | SOBR:A SQS=6(A) $750 P&L=$-1,500 |
| 2025-04-10 | $+0 | 1 | BLIV:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-04-11 | $-165 | 3 | BGLC:A SQS=6(A) $750 P&L=$+0; IOTR:A SQS=5(A) $750 P&L=$+0; SXTP:A SQS=4(B) $250 P&L=$-165 [B-GATE:PASS] |
| 2025-04-23 | $+0 | 1 | SNOA:A SQS=7(Shelved) $250 P&L=$+0 |
| 2025-04-29 | $+0 | 1 | UPC:A SQS=5(A) $750 P&L=$+0 |
| 2025-05-01 | $+0 | 1 | FEED:A SQS=7(Shelved) $250 P&L=$+0 |
| 2025-05-12 | $+0 | 1 | ABTS:A SQS=5(A) $750 P&L=$+0 |
| 2025-05-13 | $+0 | 1 | WBUY:A SQS=5(A) $750 P&L=$+0 |
| 2025-05-16 | $+855 | 1 | AMST:A SQS=6(A) $750 P&L=$+855 |
| 2025-05-30 | $+0 | 2 | ALZN:A SQS=5(A) $750 P&L=$+0; CDT:A SQS=5(A) $750 P&L=$+0 |
| 2025-06-02 | $-444 | 2 | INM:A SQS=7(Shelved) $250 P&L=$-59; BGLC:A SQS=4(B) $250 P&L=$-385 [B-GATE:PASS] |
| 2025-06-03 | $-256 | 2 | CDT:A SQS=6(A) $750 P&L=$+0; BNBX:A SQS=4(B) $250 P&L=$-256 [B-GATE:PASS] |
| 2025-06-04 | $+0 | 2 | HIND:A SQS=5(A) $750 P&L=$+0; CDT:A SQS=5(A) $750 P&L=$+0 |
| 2025-06-05 | $-845 | 2 | AGMH:A SQS=5(A) $750 P&L=$-845; VBIX:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-06-09 | $-203 | 1 | INAB:A SQS=5(A) $750 P&L=$-203 |
| 2025-06-10 | $+0 | 2 | MSW:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; JZXN:A SQS=5(A) $750 P&L=$+0 |
| 2025-06-12 | $+0 | 2 | MFI:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; HYPD:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-06-16 | $+0 | 1 | INDO:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-06-18 | $-52 | 2 | LSE:A SQS=7(Shelved) $250 P&L=$+0; HYPD:A SQS=4(B) $250 P&L=$-52 [B-GATE:PASS] |
| 2025-06-20 | $+0 | 3 | RBNE:A SQS=5(A) $750 P&L=$+0; LSE:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; MTR:A SQS=5(A) $750 P&L=$+0 |
| 2025-06-23 | $+504 | 3 | RBNE:A SQS=6(A) $750 P&L=$+0; APVO:A SQS=5(A) $750 P&L=$+0; INDO:B SQS=5(A) $250 P&L=$+504 |
| 2025-06-25 | $-1,112 | 2 | RBNE:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; MFI:A SQS=5(A) $750 P&L=$-1,112 |
| 2025-06-26 | $-278 | 3 | ULY:A SQS=5(A) $750 P&L=$+0; HYPD:A SQS=4(B) $250 P&L=$-278 [B-GATE:PASS]; GCTK:A SQS=5(A) $750 P&L=$+0 |
| 2025-06-30 | $+218 | 1 | WBUY:A SQS=6(A) $750 P&L=$+218 |
| 2025-07-03 | $+0 | 1 | GITS:A SQS=5(A) $750 P&L=$+0 |
| 2025-07-09 | $+0 | 1 | AUUD:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-07-11 | $-68 | 1 | EDHL:A SQS=5(A) $750 P&L=$-68 |
| 2025-07-14 | $+0 | 2 | WKHS:A SQS=6(A) $750 P&L=$+0; BGLC:A SQS=5(A) $750 P&L=$+0 |
| 2025-07-15 | $+0 | 1 | NUWE:A SQS=5(A) $750 P&L=$+0 |
| 2025-07-16 | $+0 | 3 | MLEC:A SQS=7(Shelved) $250 P&L=$+0; LVLU:A SQS=6(A) $750 P&L=$+0; ONCO:A SQS=5(A) $750 P&L=$+0 |
| 2025-07-17 | $+0 | 1 | VWAV:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-07-21 | $+0 | 2 | GCTK:A SQS=7(Shelved) $250 P&L=$+0; LZMH:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-07-22 | $-154 | 2 | IVF:A SQS=7(Shelved) $250 P&L=$-154; GVH:A SQS=6(A) $750 P&L=$+0 |
| 2025-07-23 | $+0 | 3 | WBUY:A SQS=7(Shelved) $250 P&L=$+0; LVLU:A SQS=5(A) $750 P&L=$+0; IVF:A SQS=5(A) $750 P&L=$+0 |
| 2025-07-24 | $+0 | 2 | HIND:A SQS=5(A) $750 P&L=$+0; HTOO:A SQS=5(A) $750 P&L=$+0 |
| 2025-07-28 | $+813 | 2 | TRUG:A SQS=6(A) $750 P&L=$+0; HTOO:A SQS=5(A) $750 P&L=$+813 |
| 2025-07-29 | $+0 | 2 | AIM:A SQS=5(A) $750 P&L=$+0; AVX:A SQS=5(A) $750 P&L=$+0 |
| 2025-07-31 | $-750 | 2 | ONCO:A SQS=7(Shelved) $250 P&L=$+0; YMAT:A SQS=5(A) $750 P&L=$-750 |
| 2025-08-01 | $+0 | 1 | FGI:A SQS=5(A) $750 P&L=$+0 |
| 2025-08-04 | $+0 | 1 | HYPD:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-08-05 | $-82 | 2 | AUUD:A SQS=4(B) $250 P&L=$-82 [B-GATE:PASS]; LICN:A SQS=4(B) $250 P&L=$+0 [B-GATE:PASS] |
| 2025-08-11 | $+0 | 1 | AUUD:A SQS=5(A) $750 P&L=$+0 |
| 2025-08-14 | $+0 | 1 | SNOA:A SQS=7(Shelved) $250 P&L=$+0 |
| 2025-08-15 | $+916 | 2 | PPSI:B SQS=4(B) $250 P&L=$+0 [B-GATE:PASS]; NA:B SQS=4(B) $250 P&L=$+916 [B-GATE:PASS] |
| 2025-08-20 | $-750 | 1 | AUUD:A SQS=6(A) $750 P&L=$-750 |

## 11. Per-Sim Detail

```
  2025-01-02   COEP :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-01-02   BYAH :A SQS=5(A) risk=$750 P&L=$+0
  2025-01-06   BAOS :A SQS=6(A) risk=$750 P&L=$+0
  2025-01-13   TRAW :A SQS=5(A) risk=$750 P&L=$+0
  2025-01-23   ALOY :A SQS=5(A) risk=$750 P&L=$-886
  2025-01-24   VNCE :A SQS=4(B) risk=$250 P&L=$-24 [B-GATE:PASS]
  2025-01-28    CDT :A SQS=6(A) risk=$750 P&L=$+0
  2025-02-03   REBN :A SQS=6(A) risk=$750 P&L=$+0
  2025-02-05   KTTA :A SQS=6(A) risk=$750 P&L=$+0
  2025-02-11   RAIN :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-02-18   JTAI :A SQS=4(B) risk=$250 P&L=$-71 [B-GATE:PASS]
  2025-02-18   AIFF :B SQS=4(B) risk=$250 P&L=$-26 [B-GATE:PASS]
  2025-02-20   JTAI :A SQS=6(A) risk=$750 P&L=$+3
  2025-02-21   TANH :A SQS=6(A) risk=$750 P&L=$+0
  2025-02-21   REBN :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-02-21   JZXN :A SQS=5(A) risk=$750 P&L=$+0
  2025-02-25   WAFU :A SQS=7(Shelved) risk=$250 P&L=$+64
  2025-02-26   RNAZ :A SQS=5(A) risk=$750 P&L=$+308
  2025-03-03   BTCT :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-03-06     GV :A SQS=6(A) risk=$750 P&L=$-750
  2025-03-10     GV :A SQS=5(A) risk=$750 P&L=$+0
  2025-03-10   RETO :A SQS=5(A) risk=$750 P&L=$-64
  2025-03-11   SNOA :A SQS=7(Shelved) risk=$250 P&L=$-25
  2025-03-18   IPDN :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-03-18   AIFF :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-03-28   SMTK :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-04-08   SOBR :A SQS=6(A) risk=$750 P&L=$-1,500
  2025-04-10   BLIV :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-04-11   BGLC :A SQS=6(A) risk=$750 P&L=$+0
  2025-04-11   IOTR :A SQS=5(A) risk=$750 P&L=$+0
  2025-04-11   SXTP :A SQS=4(B) risk=$250 P&L=$-165 [B-GATE:PASS]
  2025-04-23   SNOA :A SQS=7(Shelved) risk=$250 P&L=$+0
  2025-04-29    UPC :A SQS=5(A) risk=$750 P&L=$+0
  2025-05-01   FEED :A SQS=7(Shelved) risk=$250 P&L=$+0
  2025-05-12   ABTS :A SQS=5(A) risk=$750 P&L=$+0
  2025-05-13   WBUY :A SQS=5(A) risk=$750 P&L=$+0
  2025-05-16   AMST :A SQS=6(A) risk=$750 P&L=$+855
  2025-05-30   ALZN :A SQS=5(A) risk=$750 P&L=$+0
  2025-05-30    CDT :A SQS=5(A) risk=$750 P&L=$+0
  2025-06-02    INM :A SQS=7(Shelved) risk=$250 P&L=$-59
  2025-06-02   BGLC :A SQS=4(B) risk=$250 P&L=$-385 [B-GATE:PASS]
  2025-06-03    CDT :A SQS=6(A) risk=$750 P&L=$+0
  2025-06-03   BNBX :A SQS=4(B) risk=$250 P&L=$-256 [B-GATE:PASS]
  2025-06-04   HIND :A SQS=5(A) risk=$750 P&L=$+0
  2025-06-04    CDT :A SQS=5(A) risk=$750 P&L=$+0
  2025-06-05   AGMH :A SQS=5(A) risk=$750 P&L=$-845
  2025-06-05   VBIX :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-06-09   INAB :A SQS=5(A) risk=$750 P&L=$-203
  2025-06-10    MSW :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-06-10   JZXN :A SQS=5(A) risk=$750 P&L=$+0
  2025-06-12    MFI :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-06-12   HYPD :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-06-16   INDO :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-06-18    LSE :A SQS=7(Shelved) risk=$250 P&L=$+0
  2025-06-18   HYPD :A SQS=4(B) risk=$250 P&L=$-52 [B-GATE:PASS]
  2025-06-20   RBNE :A SQS=5(A) risk=$750 P&L=$+0
  2025-06-20    LSE :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-06-20    MTR :A SQS=5(A) risk=$750 P&L=$+0
  2025-06-23   RBNE :A SQS=6(A) risk=$750 P&L=$+0
  2025-06-23   APVO :A SQS=5(A) risk=$750 P&L=$+0
  2025-06-23   INDO :B SQS=5(A) risk=$250 P&L=$+504
  2025-06-25   RBNE :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-06-25    MFI :A SQS=5(A) risk=$750 P&L=$-1,112
  2025-06-26    ULY :A SQS=5(A) risk=$750 P&L=$+0
  2025-06-26   HYPD :A SQS=4(B) risk=$250 P&L=$-278 [B-GATE:PASS]
  2025-06-26   GCTK :A SQS=5(A) risk=$750 P&L=$+0
  2025-06-30   WBUY :A SQS=6(A) risk=$750 P&L=$+218
  2025-07-03   GITS :A SQS=5(A) risk=$750 P&L=$+0
  2025-07-09   AUUD :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-07-11   EDHL :A SQS=5(A) risk=$750 P&L=$-68
  2025-07-14   WKHS :A SQS=6(A) risk=$750 P&L=$+0
  2025-07-14   BGLC :A SQS=5(A) risk=$750 P&L=$+0
  2025-07-15   NUWE :A SQS=5(A) risk=$750 P&L=$+0
  2025-07-16   MLEC :A SQS=7(Shelved) risk=$250 P&L=$+0
  2025-07-16   LVLU :A SQS=6(A) risk=$750 P&L=$+0
  2025-07-16   ONCO :A SQS=5(A) risk=$750 P&L=$+0
  2025-07-17   VWAV :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-07-21   GCTK :A SQS=7(Shelved) risk=$250 P&L=$+0
  2025-07-21   LZMH :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-07-22    IVF :A SQS=7(Shelved) risk=$250 P&L=$-154
  2025-07-22    GVH :A SQS=6(A) risk=$750 P&L=$+0
  2025-07-23   WBUY :A SQS=7(Shelved) risk=$250 P&L=$+0
  2025-07-23   LVLU :A SQS=5(A) risk=$750 P&L=$+0
  2025-07-23    IVF :A SQS=5(A) risk=$750 P&L=$+0
  2025-07-24   HIND :A SQS=5(A) risk=$750 P&L=$+0
  2025-07-24   HTOO :A SQS=5(A) risk=$750 P&L=$+0
  2025-07-28   TRUG :A SQS=6(A) risk=$750 P&L=$+0
  2025-07-28   HTOO :A SQS=5(A) risk=$750 P&L=$+813
  2025-07-29    AIM :A SQS=5(A) risk=$750 P&L=$+0
  2025-07-29    AVX :A SQS=5(A) risk=$750 P&L=$+0
  2025-07-31   ONCO :A SQS=7(Shelved) risk=$250 P&L=$+0
  2025-07-31   YMAT :A SQS=5(A) risk=$750 P&L=$-750
  2025-08-01    FGI :A SQS=5(A) risk=$750 P&L=$+0
  2025-08-04   HYPD :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-08-05   AUUD :A SQS=4(B) risk=$250 P&L=$-82 [B-GATE:PASS]
  2025-08-05   LICN :A SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-08-11   AUUD :A SQS=5(A) risk=$750 P&L=$+0
  2025-08-14   SNOA :A SQS=7(Shelved) risk=$250 P&L=$+0
  2025-08-15   PPSI :B SQS=4(B) risk=$250 P&L=$+0 [B-GATE:PASS]
  2025-08-15     NA :B SQS=4(B) risk=$250 P&L=$+916 [B-GATE:PASS]
  2025-08-20   AUUD :A SQS=6(A) risk=$750 P&L=$-750
```
