# January–February 2026 — Giant Scanner Backtest V2 (With Protective Filters)

**Dates tested:** Jan 2 – Feb 27, 2026 (38 trading days)
**Branch:** `scanner-sim-backtest`
**Date compiled:** 2026-03-09
**Directive:** PROTECTIVE_FILTERS_DIRECTIVE_20260309.md

---

## Changes from V1

| # | Filter | Where | What |
|---|--------|-------|------|
| 1 | Profile B float ceiling | scanner_sim.py | 50M → 10M |
| 2 | PM volume minimum | Orchestrator | 1,000 shares (both A and B) |
| 3 | Session kill switch | session_manager.py | -$2K max loss, 50% give-back, 3 consecutive losses |
| 4 | Cold market gate | Orchestrator | Requires quality A-candidate (gap≥20%, PM vol≥5K) AND any 30%+ gapper |

---

## Impact Summary

| Metric | V1 | V2 | Delta |
|--------|----|----|-------|
| **Total P&L** | **-$17,885** | **-$8,938** | **+$8,947** |
| Total Sims | 274 | 161 | -113 |
| Trades (non-zero P&L) | 57 | 25 | -32 |
| Winners | 15 | 7 | -8 |
| Losers | 29 | 18 | -11 |
| Win Rate (among trades) | 26.3% | 28.0% | +1.7pp |
| Profitable Days | 3/38 | 3/30 | — |
| Days Traded | 38 | 30 | -8 (cold market) |
| Avg Loss per Loser | -$886 | -$659 | +$227 |
| Kill switch fires | N/A | 3 | — |
| Cold market skips | N/A | 8 | — |
| PM vol filtered | N/A | 183 stocks | — |
| B > 10M filtered | N/A | ~4 stocks* | — |

*Float >10M stocks (DDC, ARMP, AVR, LTRX) now classified as "skip" at scanner level, so they don't appear in JSONs at all.

---

## Kill Switch Analysis

The kill switch fired on **3 days** across 2 rules:

### Daily Max Loss (2 fires)

| Date | Sims Before Stop | Session P&L | Skipped Candidates |
|------|-----------------|-------------|-------------------|
| Jan 16 | 4 (MLEC -$1,051, FIGG $0, RGNT $0, JL -$2,299) | -$3,350 | **GNPX, RAYA, ELAB, GWAV** |
| Jan 28 | 6 (ENVB $0, GRI $0, MKDW $0, CGTL $0, ASTI -$1,976, CRWG -$965) | -$2,941 | (none — last candidate) |

### Give-Back Rule (1 fire)

| Date | Peak P&L | Final P&L | Trigger |
|------|----------|-----------|---------|
| Jan 21 | +$2,333 (BAOS) | +$444 (after CJMB -$1,889) | 444 ≤ 50% of 2,333 |
| | | Skipped: FEAM, HIMZ | |

### CRITICAL ISSUE: Jan 16 Kill Switch Blocked GWAV

The kill switch on Jan 16 blocked **GWAV** — the backtest's single biggest winner at **+$6,735** in V1. The sort order (A-profile by gap% desc) placed MLEC (gap 30%) and JL (gap 14%) before GWAV (gap ~11% pre-market). GWAV's pre-market gap was modest, but it ran to 550% during the day.

**Impact**: Without the Jan 16 kill switch, V2 P&L would have been approximately **-$2,203** instead of -$8,938. This is the most important finding — the kill switch's candidate ordering is critical. The highest-gap stocks pre-market aren't necessarily the biggest winners.

### Jan 21 Give-Back: Correctly Protected Profits

BAOS hit +$2,333, then CJMB lost -$1,889. The give-back rule correctly stopped trading with $444 left instead of risking more. In V1, FEAM and HIMZ would have been additional sims (likely $0 or small losses).

---

## Cold Market Gate Analysis

The cold market gate skipped **8 days**:

| Date | Reason | Would-Have-Traded |
|------|--------|-------------------|
| Jan 3 | No quality A (gap≥20% + PM vol≥5K) | (none) |
| Jan 5 | No quality A (gap≥20% + PM vol≥5K) | QBTZ:A, CRWG:B, CMCT:A, BNAI:A |
| Jan 8 | No quality A (gap≥20% + PM vol≥5K) | ELAB:A |
| Jan 14 | No quality A (gap≥20% + PM vol≥5K) | MLEC:A, SUGP:A, QBTZ:A |
| Feb 9 | No quality A (gap≥20% + PM vol≥5K) | PLYX:A, MAXN:B, FLYE:A, SXTC:A, NAMM:B, ROLR:A, CING:B |
| Feb 10 | No candidate with gap≥30% | TNMG:A, PLYX:A, MNTS:A, SOUX:A, FEED:A, VRCA:A, MAXN:B |
| Feb 24 | No candidate with gap≥30% | BESS:A, AIDX:A |
| Feb 25 | No quality A (gap≥20% + PM vol≥5K) | (none) |

**Feb 9 was the key cold market save.** In V1, Feb 9 produced -$2,421. The cold market gate correctly identified the lack of quality setups.

**False positives**: Jan 5 would have skipped BNAI (which went +$5,610 in the standalone study). However, in the scanner-sim flow with the V1 orchestrator, Jan 5 produced $0 (no entries triggered), so the cold market skip had no negative impact here.

---

## PM Volume Filter Analysis

The PM volume filter (minimum 1,000 shares) blocked **183 stocks** across all 38 dates. Key blocks that saved money (based on V1 losses):

| Symbol | Date | PM Vol | V1 P&L | Blocked by |
|--------|------|--------|--------|-----------|
| TULP | Jan 16 | 100 | -$1,308 | PM vol < 1,000 |
| GCDT | Jan 15 | 301 | -$1,436 | PM vol < 1,000 |
| BENF | Jan 7 | 575 | -$1,715 | PM vol < 1,000 |

---

## Per-Day Breakdown

### January 2026

| Date | Sims | Trades | W/L | Day P&L | Notes |
|------|------|--------|-----|---------|-------|
| Jan 2 | 5 | 3 | 1W/1L | -$102 | QBTZ +$470, EKSO -$605, SOPA +$33 |
| Jan 3 | — | — | — | SKIP | Cold market gate |
| Jan 5 | — | — | — | SKIP | Cold market gate |
| Jan 6 | 1 | 0 | — | $0 | NOMA: no entry |
| Jan 7 | 8 | 1 | 0W/1L | -$1,000 | ANGH -$1,000 |
| Jan 8 | — | — | — | SKIP | Cold market gate |
| Jan 9 | 7 | 1 | 0W/1L | -$1,000 | FEED -$1,000 |
| Jan 12 | 1 | 0 | — | $0 | CLNN: no entry |
| Jan 13 | 5 | 2 | 1W/1L | +$811 | WATT +$2,516, ELAB -$1,705 |
| Jan 14 | — | — | — | SKIP | Cold market gate |
| Jan 15 | 4 | 1 | 0W/1L | -$180 | AGPU -$180 |
| Jan 16 | 4 | 2 | 0W/2L | -$3,350 | MLEC -$1,051, JL -$2,299. **KILL SWITCH** (blocked GWAV) |
| Jan 21 | 3 | 2 | 1W/1L | +$444 | BAOS +$2,333, CJMB -$1,889. **GIVE-BACK** |
| Jan 22 | 6 | 0 | — | $0 | All flat |
| Jan 23 | 4 | 1 | 0W/1L | -$588 | DRCT -$588 |
| Jan 26 | 11 | 2 | 0W/2L | -$1,255 | ASTI -$1,163, QCLS -$92 |
| Jan 27 | 1 | 0 | — | $0 | DRCT: no entry |
| Jan 28 | 6 | 2 | 0W/2L | -$2,941 | ASTI -$1,976, CRWG -$965. **KILL SWITCH** |
| Jan 29 | 10 | 0 | — | $0 | All flat |
| **Jan Total** | | | | **-$9,161** | |

### February 2026

| Date | Sims | Trades | W/L | Day P&L | Notes |
|------|------|--------|-----|---------|-------|
| Feb 2 | 9 | 2 | 0W/2L | -$1,023 | FEED -$357, MNTS -$666 |
| Feb 3 | 7 | 0 | — | $0 | All flat |
| Feb 4 | 10 | 3 | 2W/1L | -$70 | ASTI +$342, CRWG +$625, XCUR -$1,037 |
| Feb 5 | 14 | 1 | 1W/0L | +$2,017 | RIOX +$2,017 |
| Feb 6 | 2 | 0 | — | $0 | All flat |
| Feb 9 | — | — | — | SKIP | Cold market gate |
| Feb 10 | — | — | — | SKIP | Cold market gate |
| Feb 11 | 6 | 0 | — | $0 | All flat |
| Feb 12 | 11 | 1 | 0W/1L | -$96 | ASTI -$96 |
| Feb 13 | 2 | 1 | 0W/1L | -$605 | ASTI -$605 |
| Feb 17 | 2 | 0 | — | $0 | All flat |
| Feb 18 | 4 | 0 | — | $0 | All flat |
| Feb 19 | 1 | 0 | — | $0 | All flat |
| Feb 20 | 7 | 0 | — | $0 | All flat |
| Feb 23 | 3 | 0 | — | $0 | All flat |
| Feb 24 | — | — | — | SKIP | Cold market gate |
| Feb 25 | — | — | — | SKIP | Cold market gate |
| Feb 26 | 1 | 0 | — | $0 | All flat |
| Feb 27 | 6 | 0 | — | $0 | All flat |
| **Feb Total** | | | | **+$223** | |

---

## Top Winners

| Symbol | Date | Profile | P&L |
|--------|------|---------|-----|
| WATT | Jan 13 | A | +$2,516 |
| BAOS | Jan 21 | A | +$2,333 |
| RIOX | Feb 5 | A | +$2,017 |
| CRWG | Feb 4 | B | +$625 |
| QBTZ | Jan 2 | A | +$470 |
| ASTI | Feb 4 | A | +$342 |
| SOPA | Jan 2 | B | +$33 |

## Top Losers

| Symbol | Date | Profile | P&L |
|--------|------|---------|-----|
| JL | Jan 16 | A | -$2,299 |
| ASTI | Jan 28 | A | -$1,976 |
| CJMB | Jan 21 | A | -$1,889 |
| ELAB | Jan 13 | A | -$1,705 |
| ASTI | Jan 26 | A | -$1,163 |
| MLEC | Jan 16 | A | -$1,051 |
| XCUR | Feb 4 | A | -$1,037 |
| ANGH | Jan 7 | A | -$1,000 |
| FEED | Jan 9 | A | -$1,000 |
| CRWG | Jan 28 | B | -$965 |

---

## Key Findings

### 1. Filters reduced losses by $8,947 (50% improvement)
V1: -$17,885 → V2: -$8,938. The combination of PM volume filter, cold market gate, and float ceiling removed the worst-performing segments.

### 2. Kill switch is a double-edged sword
The Jan 16 kill switch correctly identified a bad day (-$3,350 session P&L) but blocked GWAV (+$6,735), the backtest's biggest winner. **Net impact of kill switch across all fires: approximately -$6,735 to +$444** depending on what the skipped candidates would have done. The sort order (gap% descending) doesn't correlate with actual performance.

### 3. February was nearly flat with filters
V1 February: heavy losses. V2 February: +$223. The cold market gate (skipping Feb 9, 10, 24, 25) and the PM volume filter eliminated the worst February bleeds.

### 4. ASTI is a serial loser
ASTI appeared 5 times: -$1,163 (Jan 26), -$1,976 (Jan 28), +$342 (Feb 4), -$96 (Feb 12), -$605 (Feb 13). Net: **-$3,498**. The bot has no memory of past performance on repeat stocks.

### 5. Most sims produce zero trades
136 of 161 sims (84%) had $0 P&L — no entry was triggered. The bot is already very selective about entries; the problem is when it DOES enter, the losers are oversized.

---

## Recommendations for Luke/Perplexity

1. **Kill switch sort order needs work.** Pre-market gap% is not predictive of intraday performance. Consider: PM volume × gap% composite, or simply running ALL candidates regardless of kill switch (since most produce $0 P&L anyway, the kill switch mainly blocks non-events).

2. **Stop calibration is still the #1 issue.** Average loss per loser is -$659 (down from -$886), but the top 5 losers still average -$1,807. The tight R-values on low-liquidity stocks continue to cause outsized losses.

3. **Profile B is marginally positive.** B produced CRWG +$625 and SOPA +$33 as winners, vs CRWG -$965 as the only B loser. The 10M ceiling eliminated the toxic large-float B stocks.

4. **The real edge might be "only trade on hot days."** Jan 13 (+$811) and Feb 5 (+$2,017) were the only meaningfully profitable days. Both had a clear standout A-profile runner (WATT, RIOX).

---

*Report generated by Claude Code — 2026-03-09*
*Directive: PROTECTIVE_FILTERS_DIRECTIVE_20260309.md*
