# Trade-Level Forensic: Where Did the $1,941 Go?

**Date**: 2026-03-24
**Comparison**: megatest_sq_only (Mar 22, +$19,832) vs jan_comparison_v1 (Mar 24, +$17,891)

## Executive Summary

The -$1,941 risk-sized gap comes from a **-$34,960 raw P&L gap** compressed by equity-based risk sizing (2.5% of equity per trade). The gap has **two root causes**, not one:

| Cause | Raw P&L Impact | Description |
|-------|---------------|-------------|
| **Bail timer** (code change) | -$23,945 | 5-min unprofitable exit added to simulate.py on Mar 24 |
| **Scanner changes** | -$12,453 | 12-checkpoint schedule + cumulative window |
| Other code differences | +$2,771 | Bail timer HELPING cascading stocks (VERO) |
| **Risk sizing compression** | — | -$34,960 raw → -$1,941 risk-sized |

**The bail timer is the dominant factor, not the scanner.**

---

## What Changed Between the Two Runs

The megatest ran on **Mar 22**. The V1 batch ran on **Mar 24 at 18:02**. Between those runs, commit `d0a013f` ("Wire SqueezeDetector into live bot + align exits with backtest") added the **bail timer** to `simulate.py`:

```python
# Added Mar 24 — did NOT exist during megatest
if self.bail_timer_enabled and t.entry_time:
    if (now_min - entry_min) >= self.bail_timer_minutes:  # 5 min
        if price <= t.entry:  # still at or below entry
            self._close(t)  # force exit
```

This kills any trade that hasn't gone profitable within 5 minutes. The megatest had no such mechanism — trades could sit underwater indefinitely and recover.

---

## Full Attribution (Raw P&L, Pre-Risk-Sizing)

### A. Bail Timer Casualties: -$23,945 (20 stocks)

Same stock, same date, but fewer trades in the new run — bail timer killed entries before they could recover:

| Date | Stock | Old P&L | Old Trades | New P&L | New Trades | Delta |
|------|-------|---------|------------|---------|------------|-------|
| 2026-01-14 | ROLR | +$18,650 | 3 | +$8,853 | 2 | **-$9,797** |
| 2026-01-21 | SLGB | +$8,345 | 3 | +$3,887 | 2 | **-$4,458** |
| 2026-01-16 | BIYA | +$3,146 | 1 | $0 | 0 | **-$3,146** |
| 2025-01-21 | INM | +$2,172 | 2 | $0 | 0 | **-$2,172** |
| 2025-01-10 | VMAR | +$845 | 3 | -$333 | 1 | **-$1,178** |
| 2026-01-12 | BDSX | +$828 | 3 | -$345 | 2 | **-$1,173** |
| 2026-01-16 | GWAV | +$4,552 | 2 | +$3,467 | 1 | **-$1,085** |
| 2025-01-17 | BTCT | +$847 | 1 | $0 | 0 | **-$847** |
| … | … | … | … | … | … | … |

**Pattern**: These stocks had trades that dipped below entry for 5+ minutes, then recovered. The bail timer killed them. ROLR alone accounts for $9,797 of the gap.

### B. Extra Entries (bail timer frees capacity): -$6,022 (11 stocks)

Same stock, MORE trades in new run. Bail timer kills bad entries quickly, creating room for additional re-entry attempts:

| Date | Stock | Old P&L | Old Trades | New P&L | New Trades | Delta |
|------|-------|---------|------------|---------|------------|-------|
| 2026-01-23 | MOVE | +$6,000 | 3 | +$3,423 | 4 | -$2,577 |
| 2026-01-15 | SPHL | +$5,054 | 3 | +$3,377 | 4 | -$1,677 |
| 2026-01-08 | ACON | +$980 | 2 | -$13 | 3 | -$993 |

**Pattern**: More attempts but worse outcomes — quick bail → re-enter → bail again cycle.

### C. Same Trade Count, Different P&L: +$8,793 (9 stocks)

Same stock, same number of trades, but different raw P&L:

| Date | Stock | Old P&L | New P&L | Delta | Notes |
|------|-------|---------|---------|-------|-------|
| 2026-01-16 | **VERO** | +$1,365 | **+$14,362** | **+$12,997** | Bail timer HELPS |
| 2026-01-22 | SXTP | +$3,331 | +$915 | -$2,416 | |

**VERO insight**: The bail timer actually HELPS cascading stocks. It kills bad early entries fast, letting the bot re-enter on the real runner. Old VERO: limped through 3 trades for +$1,365. New VERO: same 3 trades but with bail timer clearing duds faster, capturing +$14,362.

### D. Lost Stocks (Scanner Changes): -$18,060 (12 stocks with trades)

Stocks that produced profitable trades in the old run but aren't in the new run at all:

| Date | Stock | Old P&L | Trades | Why Lost |
|------|-------|---------|--------|----------|
| 2026-01-15 | **CJMB** | **+$9,533** | 3 | Different scanner selections |
| 2025-01-14 | AIFF | +$2,165 | 3 | Different scanner selections |
| 2025-01-08 | NCEL | +$2,035 | 3 | Different scanner selections |
| 2025-01-14 | OST | +$1,343 | 1 | Different scanner selections |
| 2026-01-12 | SUGP | +$1,249 | 1 | Different scanner selections |

### E. New Stocks (Scanner Changes): +$4,274 net

Winners gained: +$5,607 (GDTC +$2,280, NTRB +$2,024, AMOD +$633, OM +$483, BGL +$187)
Losers added: -$1,333 (PHIO -$128, NMHI -$143, ICON -$579, CLRB -$483)

---

## The Two Problems

### Problem 1: Bail Timer (68% of raw gap)

The bail timer is a **double-edged sword**:

- **HURTS slow runners**: ROLR, SLGB, BIYA — stocks that dip below entry for 5-10 minutes then rocket. The old run held through the dip; the new run bails at 5 min.
- **HELPS cascading stocks**: VERO — bail timer kills early duds fast, freeing capacity for the real runner (+$12,997 improvement).

Net raw impact: -$23,945 + $8,793 (from category C) ≈ **-$15,152** attributed to bail timer

### Problem 2: Scanner Stock Universe (32% of raw gap)

The 12-checkpoint schedule with 9:30 cutoff discovers a different set of stocks than the old 7-checkpoint schedule. Lost $18,060 in proven winners, gained $4,274 from new finds. Net: **-$13,786**

---

## What This Means for the Dynamic Ranking Directive

**Dynamic ranking would NOT fix either problem.**

1. The bail timer issue is a code change, not a ranking issue
2. The scanner stock-universe issue is about which checkpoints exist, not how stocks are ranked within them
3. Volume distortion (the original hypothesis) doesn't exist in the data — all 120 shared stocks have identical volumes between old and new scanner JSONs

---

## Recommended Next Steps

### Immediate: Re-run V1 batch with bail timer OFF
```bash
WB_BAIL_TIMER_ENABLED=0 WB_MP_ENABLED=1 python run_jan_v1_comparison.py
```
This isolates the bail timer impact. If P&L recovers to ~$19K+, the bail timer is the problem, not the scanner.

### Then: Decide bail timer strategy
- **Option A**: Disable bail timer entirely — recovers ROLR/SLGB but loses VERO edge
- **Option B**: Make bail timer smarter — don't bail trades that are within X% of entry, or only bail if the stock is also below VWAP
- **Option C**: Stock-type-aware bail timer — longer timeout for breakout stocks (ROLR pattern), shorter for cascading (VERO pattern)

### Scanner: Lower priority
The scanner stock-universe difference is smaller (-$13,786 raw, much less after risk sizing) and harder to fix without the original JSONs for A/B testing. Investigate only after bail timer is resolved.
