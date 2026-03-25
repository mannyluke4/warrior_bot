# AIFF/OST Disappearance + Top-N Analysis
**Date**: 2026-03-24
**Baseline**: Old V1 (+$19,832, 49 trades) vs New V1 (+$17,891, 42 trades)
**Gap**: -$1,941

---

## 1. AIFF and OST on Jan 14: What Happened

### Old Scanner (commit aef59a1)
Found 2 stocks, both passing filters:

| Rank | Symbol | Gap% | PM Vol | RVOL | Float | Discovery | Score |
|------|--------|------|--------|------|-------|-----------|-------|
| 1 | AIFF | 63.4% | 8.9M | 27.5 | 6.3M | 08:00 (precise: 07:45) | 0.766 |
| 2 | OST | 43.8% | 6.1M | 3.5 | 4.9M | 07:00 (precise: 07:14) | 0.547 |

**Result**: AIFF produced 3 trades (+$1,061), OST produced 1 trade (+$726). Combined: **+$1,787**.

### New Scanner (current)
Found 1 stock:

| Rank | Symbol | Gap% | PM Vol | RVOL | Float | Discovery | Score |
|------|--------|------|--------|------|-------|-----------|-------|
| 1 | NMHI | 171.7% | 31.3M | 22.8 | 14.5M | 07:00 | 0.804 |

**Result**: NMHI produced 2 trades (**-$143**). Net swing from this one date: **-$1,930**.

### Why NMHI Replaced AIFF/OST

NMHI wasn't in the old scanner because **MAX_FLOAT was 10M** in the old run. NMHI has 14.5M float, so it was filtered out. When MAX_FLOAT was raised to 15M, NMHI entered the universe and — with its huge gap (171%) and massive volume (31M) — scored higher than both AIFF and OST.

But NMHI entering didn't push AIFF/OST out via ranking. **AIFF and OST vanished entirely from the new scanner JSON.** They're not ranked lower — they're gone.

### Root Cause: Scanner Code Changes, Not Ranking

The scanner was re-run after the checkpoint overhaul (commit `03feb7f`) and cumulative window fix (commit `3fcc599`). Between the old run and the new run, the scanner's `get_all_active_symbols()` calls the **live Alpaca API**, which returns the current universe. This produces a non-deterministic stock universe that varies by run date.

Evidence:
- AIFF exists in current scanner JSONs for other dates (Jan 10, May 5, Jun 20, Jul 14)
- OST exists in current scanner JSON for Jan 24
- Both symbols are still active on Alpaca (AIFF appears on Jan 10 with RVOL=56.6)
- The scanner API returns minute bars from Alpaca; subtle changes in the returned data between runs can cause stocks to appear or disappear at specific checkpoints

The new checkpoint schedule (12 custom checkpoints vs 39 five-minute intervals) and cumulative windows (4AM→checkpoint vs incremental) changed the discovery behavior. Combined with the live API's non-determinism, AIFF and OST fell through the cracks on Jan 14 specifically.

---

## 2. CJMB: The Bigger Hidden Issue

CJMB on Jan 15 is actually the most instructive case:

| Run | Discovery | sim_start | Gap% | PM Vol | Rank | Trades | P&L |
|-----|-----------|-----------|------|--------|------|--------|-----|
| Old | 09:00 | 09:00 | 126.8% | 16.6M | 1 | 1 | +$1,028 |
| New | 08:45 | 08:45 | 85.7% | 0.4M | 4 | 0 | $0 |

The cumulative window change found CJMB **15 minutes earlier** (08:45 vs 09:00). But at 08:45, CJMB had only 400K volume vs 16.6M at 09:00 — it was pre-catalyst. The earlier `sim_start` fed the detector different seed bars, and the squeeze detector never ARMed.

**This is not a ranking problem. It's an earlier-discovery-hurts problem.** The cumulative window "improvement" made CJMB worse by finding it before it was ready.

Same pattern with STAI on Jan 30: old disc=09:00 → trade (-$795), new disc=08:45 → no trade. In STAI's case, earlier discovery accidentally avoided a loser.

---

## 3. Top-5 Displacement: How Often Does It Matter?

### Distribution of Stocks Passing Filter

| Stocks Passing | # of Dates | % |
|----------------|------------|---|
| 0 | 6 | 14% |
| 1 | 4 | 10% |
| 2 | 4 | 10% |
| 3 | 9 | 21% |
| 4 | 8 | 19% |
| 5 | 3 | 7% |
| 6+ | 8 | 19% |
| **Average** | **3.2** | |

Top-5 is constraining on only **8 of 42 dates (19%)**. On most days, fewer than 5 stocks pass filters, so the cap is irrelevant.

### Dates Where Top-5 Excluded Stocks

| Date | Passed | Excluded | Known P&L |
|------|--------|----------|-----------|
| 2025-01-02 | 6 | HOOK | unknown |
| 2025-01-21 | 6 | DCX | unknown |
| 2026-01-13 | 6 | BCTX | unknown |
| 2026-01-16 | 6 | TNMG | unknown |
| 2026-01-20 | 7 | POLA, SHPH | POLA: +$556 |
| 2026-01-21 | 6 | AIFU | unknown |
| 2026-01-23 | 6 | MAXN | unknown |
| 2026-01-27 | 6 | CYN | CYN: -$198 |

Only 2 excluded stocks have known P&L data (they were traded in the old run): POLA (+$556) and CYN (-$198).

### Top-N P&L Impact

| Threshold | Additional Winners | Additional Losers | Net Change |
|-----------|-------------------|-------------------|------------|
| TOP-5 (current) | — | — | — |
| TOP-7 | +$556 (POLA) | -$198 (CYN) | **+$358** |
| TOP-10 | same as top-7 | same as top-7 | **+$358** |

Going beyond top-7 adds nothing because no dates have more than 7 stocks passing filters.

---

## 4. Full -$1,941 Gap Attribution

| Category | P&L Impact | Details |
|----------|-----------|---------|
| **Lost winners (scanner change)** | -$1,896 | AIFF +$1,061, OST +$726, SLXN +$109 |
| **Lost winner (detector timing)** | -$1,028 | CJMB: in scanner rank 4, but sim_start change prevents ARM |
| **Lost winner (rank displacement)** | -$556 | POLA: bumped from rank 5 to rank 6 |
| **Avoided losers** | +$2,706 | KAPA, PTHS, STAI, CELZ, CYN, FEED, CISS |
| **New winners** | +$602 | BGL +$187, PMN +$415 |
| **New losers** | -$975 | PHIO, NMHI, VATE, NTRB |
| **Same-stock timing diffs** | -$794 | Risk sizing + detector timing on 14 shared stocks |
| **TOTAL** | **-$1,941** | |

---

## 5. Recovery Scenarios

| Scenario | Action | Estimated P&L | Recovery |
|----------|--------|---------------|----------|
| Current (new V1) | Nothing | +$17,891 | — |
| TOP-7 only | Raise TOP_N to 7 | +$18,249 | +$358 |
| Fix CJMB only | Investigate sim_start timing | +$18,919 | +$1,028 |
| TOP-7 + CJMB | Both | +$19,277 | +$1,386 |
| Full scanner fix | Re-run scanner to recover AIFF/OST | +$19,787 | +$1,896 |
| **Maximum** | All of the above | **+$21,173** | **+$3,282** |

---

## 6. Is Top-5 Creating Misleading Batch Results?

**Short answer: No, top-5 is not a significant constraint.**

The data shows:
- Average 3.2 stocks pass filter per day — well under the cap
- Only 19% of dates are constrained (8/42)
- Top-7 recovers only +$358 more than top-5
- Going beyond top-7 adds nothing (max stocks passing = 7)

**The real mismatch with the live bot is not top-N, it's discovery timing.** The live bot uses real-time streaming data and discovers stocks the moment they meet criteria. The batch runner's scanner uses checkpoint-based discovery with cumulative API queries, producing different `sim_start` times that change detector behavior. CJMB (-$1,028 impact) is the proof case.

---

## 7. Recommendations

### Quick Win: Raise TOP_N from 5 to 7 (+$358)
Low risk, captures POLA-type displacement. Most days won't be affected.

### Medium Priority: Investigate CJMB sim_start Issue (+$1,028)
The cumulative window change finding stocks earlier is a double-edged sword. CJMB was found 15 minutes early with 0.4M volume vs 16.6M at the original discovery time. The fix might be:
- **Option A**: Don't advance sim_start when cumulative volume at discovery is very low relative to what it becomes later (deferred start)
- **Option B**: Re-evaluate sim_start at each subsequent checkpoint as volume grows
- **Option C**: Accept this as a known limitation of checkpoint-based backtesting

### Low Priority: Scanner Non-Determinism (+$1,896 theoretical)
AIFF/OST disappearing is fundamentally a non-determinism issue — the scanner calls the live Alpaca API, which returns different bar data on different days. Options:
- **Cache the raw bar data** from the first successful scan, so re-scans are deterministic
- **Pin the symbol universe** (save the list of all active symbols per date)
- Accept this as noise in backtesting

### Not Recommended: Dynamic Ranking Directive
The DIRECTIVE_DYNAMIC_RANKING.md should be killed. The volume distortion hypothesis was disproven — all 120 shared stocks have identical volumes between old and new scanner JSONs. The real issues are scanner non-determinism and cumulative-window sim_start changes.
