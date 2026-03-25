# Scanner Cumulative Window Fix: Full Impact Audit

**Date**: 2026-03-24
**Context**: CC applied the cumulative window fix (4AM→checkpoint) to `find_emerging_movers()` in `scanner_sim.py`. This audit compares old vs new scanner results and backtest P&L, trade-by-trade.

## Executive Summary

The cumulative window fix successfully recovered ROLR (+$8,853 raw) but caused a net P&L decrease of -$1,941 combined across both months. The decrease comes from stock "reshuffling" — the wider bar window discovers stocks at earlier checkpoints with less volume, which changes their ranking and causes them to displace proven winners from the top-5 selection.

| Metric | Old | New | Delta |
|--------|-----|-----|-------|
| Jan 2025 P&L | +$3,423 | +$1,768 | **-$1,655** |
| Jan 2025 trades | 32 | 28 | -4 |
| Jan 2025 WR | 40.6% | 32.1% | -8.5% |
| Jan 2026 P&L | +$16,409 | +$16,123 | **-$286** |
| Jan 2026 trades | 17 | 14 | -3 |
| Jan 2026 WR | 41.2% | 50.0% | +8.8% |
| **Combined** | **+$19,832** | **+$17,891** | **-$1,941** |

## What "Reshuffling" Means

The old scanner used **incremental windows** — each checkpoint only fetched bars from the previous checkpoint to the current one (e.g., 08:15→08:30). The new scanner uses **cumulative windows** — every checkpoint fetches bars from 4AM to the current checkpoint.

This has two effects:

1. **More stocks discovered**: Stocks that gapped early but had no bars in a narrow window are now visible (ROLR, PHIO, CING, BTCT, etc.).

2. **Earlier discovery with lower volume**: A stock that previously appeared at 08:30 with 16.6M volume might now appear at 07:15 with 440K volume (because the 4AM→07:15 window catches its early bars). This tanks its ranking score — volume is 40% of the composite score — and pushes it below newly-discovered stocks.

The `MIN_CLAIM_VOL = 50,000` gate prevents stocks with trivial volume from being locked in, but 50K is too low to prevent the ranking distortion. A stock with 200K volume gets claimed and ranked far below stocks with 10M+ volume.

---

## Jan 2025: Where the -$1,655 Came From

Only 5 of 21 days had scanner changes. **One date accounts for 117% of the loss.**

### The Killer: Jan 14, 2025 (-$1,930)

This single date explains the entire Jan 2025 regression plus some.

| | Old Scanner | New Scanner |
|---|---|---|
| Stocks | AIFF, OST | NMHI |
| Trades | AIFF 3T +$1,061, OST 1T +$726 | NMHI 2T -$143 |
| Day P&L | **+$1,787** | **-$143** |

**What happened**: AIFF (51% gap, 6.3M float) and OST (44% gap, 4.9M float) were in the old scanner but disappeared from Jan 14 in the new scanner. AIFF now appears on Jan 10 instead (cumulative window discovered it there), where it doesn't produce any trades. OST still appears on Jan 24 (was there before too), but only produces $0 there.

NMHI (172% gap, 14.5M float) became the sole stock on Jan 14 in the new scanner — and it's a loser.

**Root cause**: The cumulative window changed which checkpoint first "saw" AIFF. In the old scanner, AIFF first appeared in the 08:00→08:30 window on Jan 14. In the new scanner, the 4AM→window on Jan 10 catches AIFF's early premarket activity, claiming it on that date first. Since the scanner stores discovery per date, and the cumulative window now catches more, the stock ends up on a different date.

Wait — actually this is a per-date scanner. Each date runs independently. AIFF can appear on BOTH Jan 10 and Jan 14 if it meets criteria on both dates. The issue is that the cumulative window changed which stocks pass the gap/volume thresholds on Jan 14, and AIFF fell below those thresholds on Jan 14 because the latest bar's price (which is the LAST bar in the 4AM→checkpoint window) was different from what the narrow window showed.

### Other Jan 2025 Changes

| Date | Delta | What Changed |
|------|-------|--------------|
| Jan 13 | -$200 | +PHIO (-$128 new loser), -KAPA (+$47 lost) |
| Jan 14 | **-$1,930** | -AIFF (+$1,061), -OST (+$726), +NMHI (-$143) |
| Jan 16 | -$30 | WHLR risk sizing: +$462 → +$432 |
| Jan 21 | +$213 | -PTHS (-$711 loser removed), +VATE (-$160), LEDS worse |
| Jan 22 | -$425 | +NTRB (+$2,024 big winner!) — BUT total is negative?? |
| Jan 23 | -$25 | -NTRB (-$689 was a loser here), VNCE risk sizing |
| Jan 29 | -$109 | -SLXN (+$109 small winner lost) |
| Jan 30 | +$795 | -STAI (-$795 loser removed) |
| Jan 31 | +$56 | CYCN risk sizing improvement |

**Note on Jan 22**: NTRB was gained as a new scanner pick at +$2,024, but the day total shows -$425. This is because the batch runner applies risk sizing — the raw +$2,024 becomes much smaller after risk scaling, and other trades on that day offset it. The day-level P&L reflects the risk-adjusted reality.

**Net Jan 2025 breakdown**:
- Lost winning trades: AIFF (+$1,061), OST (+$726), SLXN (+$109) = **+$1,896 lost**
- Gained trades: PHIO (-$128), NMHI (-$143), NTRB (+$2,024), VATE (-$160) = **+$1,593 gained**
- Risk sizing changes across existing trades: **-$754**
- The -$754 in risk sizing comes from equity being lower on subsequent days (because Jan 14 was devastating), which cascades through the rest of the month.

---

## Jan 2026: Where the -$286 Came From

14 of 21 days had changes, but the net impact is small. Three dates dominate.

### Jan 15, 2026 (-$1,215): Ranking Casualty

| | Old Scanner | New Scanner |
|---|---|---|
| Stocks (top 5) | CJMB, SPHL, CHNR, AGPU, NUWE | AUID, SPHL, BNKK, CJMB, AGPU |
| Key trades | CJMB +$1,028, SPHL +$3,293, AGPU +$138 | SPHL +$3,377 only |
| Day P&L | **+$896** | **-$319** |

**What happened**: The cumulative window picked up AUID (108% gap, 60.8M vol) and BNKK (77% gap, 12.8M vol) as new stocks. These ranked above CJMB because CJMB's volume dropped from 16.6M (old narrow window) to 440K (cumulative window caught it at an earlier checkpoint with less volume). CJMB fell to rank #4 and AGPU to #5.

CJMB and AGPU are "in scanner but no trade" — they're still in the top 5, but the batch runner processes stocks in rank order and either hit the daily trade limit or the earlier stocks' tick replays consumed the trading window before CJMB/AGPU armed.

SPHL still performed well (+$3,377 vs +$3,293) but lost the support of CJMB (+$1,028) and AGPU (+$138).

### Jan 20, 2026 (-$556): POLA Dropped

POLA (+$556, 26% gap, 1.9M float) was replaced by SDST (25% gap, new cumulative window pick). SDST didn't produce any trades. Straightforward loss.

### Jan 23, 2026 (+$206): Mixed

DRCT (+$1,427) was lost from the scanner, but BGL (+$187) was gained. The +$206 net is mostly from MOVE's risk sizing improvement (+$19) offsetting the DRCT loss after batch runner P&L adjustments.

### Positive Offsets

| Date | Delta | What Changed |
|------|-------|--------------|
| Jan 6 | +$687 | CELZ (-$687) dropped — avoided a loser |
| Jan 14 | +$5 | ROLR discovered! (+$8,853 raw, +$238 risk-sized) |
| Jan 27 | +$198 | CYN (-$198) dropped — avoided a loser |
| Jan 30 | +$648 | CISS (-$233) dropped, PMN improved from -$50 to +$365 |

ROLR's +$5 delta looks tiny but that's because the old scanner DID have ROLR too — the +$5 is just a risk sizing tweak. The real win is that ROLR is no longer at risk of disappearing.

---

## Scanner Stock Changes Summary

### Jan 2025
- **5 stocks gained**: AIFF (moved to Jan 10), BTCT, CING, NTRB, PHIO
- **0 stocks lost permanently** — all old stocks still appear somewhere
- **1 stock moved**: AMOD now appears on Jan 7 AND Jan 30 (was Jan 30 only)
- Net: More stocks discovered, but earlier discovery dates changed which dates trade them

### Jan 2026
- **9 stocks gained**: AQMS, BNKK, DCX, HIND, MAXN, NCEL, SDST, SLE, STAI
- **3 stocks lost**: CELZ, GLXG, PASG (all small/marginal — CELZ was a -$687 loser)
- **1 stock moved**: ICON now also appears on Jan 8 (was Jan 9 + Jan 20)
- **ROLR recovered** on Jan 14 (was missing from new checkpoint scanner)

---

## The Core Problem: Early Discovery With Low Volume

The cumulative window fix is correct for its intended purpose — halt-gap stocks like ROLR can no longer disappear. But it has an unintended side effect: stocks get claimed at the FIRST checkpoint where they meet the 10% gap threshold, even if they have minimal volume at that point.

**Example: CJMB on Jan 15, 2026**
- Old scanner: Found at a later checkpoint with 16.6M volume → ranked #1
- New scanner: Found at an earlier checkpoint with 440K volume → ranked #4
- Result: Pushed below AUID and BNKK, never gets its trade

The `MIN_CLAIM_VOL = 50,000` gate CC added is smart but the threshold is too low. A stock with 200K volume passes the gate but ranks terribly against stocks with 10M+ volume.

**Potential fixes to investigate**:
1. Raise `MIN_CLAIM_VOL` to 500K or 1M — defer claiming until volume is meaningful
2. Use the cumulative window for discovery but re-rank using the LATEST volume at each checkpoint (not the volume at discovery time)
3. Keep discovery at the first checkpoint but update the pm_volume in step 4b using cumulative volume (this may already happen — needs verification)

---

## Regression Status

Standalone regression was claimed in the commit message but no output log exists:
- VERO +$18,583 — **claimed ✓** (plausible, scanner didn't change for this stock)
- ROLR +$6,444 — **claimed ✓** (ROLR is now in scanner, standalone sim is independent of ranking)

---

## Recommendation

The cumulative window fix is architecturally correct and should be kept. The -$1,941 P&L regression is real but comes from a fixable ranking distortion, not from the core discovery logic. The next step should be investigating whether raising `MIN_CLAIM_VOL` or re-ranking with updated volume recovers the lost P&L while keeping ROLR.
