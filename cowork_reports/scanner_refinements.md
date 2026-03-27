# Scanner Refinements — Living Document
## Created: 2026-03-20
## Last Updated: 2026-03-20
## Purpose: Accumulate evidence from Ross recap comparisons to tune scanner parameters before a final re-run

---

## Goal

After all Ross recaps are cataloged, run one comprehensive scanner re-test with tuned parameters across all available dates. This document tracks every data point leading to that re-run.

Current scanner parameters (Ross's 5 Pillars):
```
Gap:       >= 10%    (no ceiling)
Price:     $2–$20
Float:     100K–10M
RVOL:      >= 2.0x
PM Volume: >= 50,000
```

Scanner timing: first pass at 7:15 AM ET using 4:00–7:15 bars. Rescan checkpoints at 8:00, 8:30, 9:00, 9:30, 10:00, 10:30.

---

## 1. Scanner Hit Rate vs Ross's Picks

Running tally across all recap days analyzed. Updated as new recaps come in.

| Date | Ross Stocks | Scanner Found | Missed | Hit Rate | Notes |
|------|-------------|---------------|--------|----------|-------|
| 2025-02-28 | 3 (BTII, ZOZ, NVVE) | 2 (ZOOZ, NVVE) | 1 (BTII) | 67% | BTII = pre-7:15 compliance play. ZOZ found as ZOOZ (ticker format). |
| 2026-03-19 | 1 (CHNR) | 1 (CHNR) | 0 | 100% | Found 44 min late (8:00 vs 7:16). See CHNR gap analysis. |
| 2026-03-20 | 1 (ARTL) | 1 (ARTL) | 0 | 100% | Found via gap scan. Ross found as continuation play, no fresh catalyst. |
| **Total** | **5** | **4** | **1** | **80%** | **Miss = pre-7:15 reverse split edge case** |

---

## 2. Stocks Ross Caught That Scanner Missed

### BTII — 2025-02-28
- **Symbol**: BTII
- **Ross's alert**: 7:00 AM ET. NASDAQ compliance regained after reverse split. Popped $2.00→$2.30.
- **Ross's trade**: Bought pullback-to-support at ~$2.00, rode curl to $2.40–2.60. +$1,500.
- **Why scanner missed**: Multiple factors:
  1. **Timing (primary)**: Ross found it at 7:00 AM. Scanner's first pass uses 4:00–7:15 bars. The move started at 7:00, so the 7:15 scan may have seen the stock pre-move or mid-move with insufficient gap.
  2. **Gap % uncertainty**: If prev_close was ~$2.00 (post reverse split) and PM price at 7:15 was $2.10–2.20, that's only 5–10% gap — below the 10% threshold. By the 8:00 rescan, the 25% move was already done.
  3. **Reverse split data quality**: Reverse splits create prev_close ambiguity in Databento data. The scanner may have seen a stale pre-split prev_close.
- **Parameter impact**: This is NOT a parameter tuning fix. It's a scan architecture gap — the scanner doesn't run before 7:15, and reverse split compliance plays are a category the gap scanner isn't designed for.
- **Possible fix**: Earlier first scan (6:30–7:00?) or streaming mode for intra-premarket moves. Same fix as the CHNR timing gap.

### GDTC — 2025-01-06
- **Symbol**: GDTC
- **Ross's trade**: +$5,300 on the day. PM price $6.68, 93.6% gap, 94x RVOL — textbook gap-and-go setup.
- **Why scanner missed**: The megatest's `load_and_rank()` function in `run_megatest.py` rejects stocks with null `float_shares` or profile "X". GDTC had missing float data and was filtered out entirely despite having elite gap/RVOL signals.
- **Parameter impact**: This IS a parameter/logic tuning fix. The null-float rejection is too aggressive — it auto-discards stocks that have strong volume and gap signals but happen to lack float data from the primary source.
- **Possible fixes**:
  1. **Default float estimate**: Assign an estimated float based on price/volume behavior when float data is missing.
  2. **Threshold bypass**: Skip the float filter entirely when RVOL and gap exceed high thresholds (e.g., RVOL > 50x AND gap > 50%).
  3. **Secondary data source**: Use a fallback float lookup (e.g., SEC filings, alternate API) before rejecting.
- **Severity**: HIGH — Ross made +$5,300 on a stock the scanner silently discarded. Unknown how many other null-float stocks have been filtered across all test dates.

*Add future misses here as recaps are processed.*

---

## 3. Stocks Scanner Caught That Ross Didn't Trade

### ANNA — 2026-03-20
- **Scanner**: gap +21%, RVOL 2.2x, float 9.4M, Profile B
- **Bot result**: +$528 (squeeze, 3 trades)
- **Why Ross skipped**: Likely float too high (9.4M vs ARTL's 0.7M), focus on ARTL, opportunity cost of splitting attention
- **Implication**: Not a false positive — bot profited. Scanner is correctly surfacing tradeable stocks that Ross intentionally skips for focus/sizing reasons. Multi-stock advantage.

### RDGT — 2026-03-20
- **Scanner**: gap +17%, RVOL 3.8x, float 5.1M, Profile B, discovered 10:03
- **Bot result**: $0 — exhaustion filter blocked MP, squeeze had no valid level
- **Why Ross skipped**: Unknown (may not have traded this day's scan at all — only took ARTL)
- **Implication**: Scanner correctly found it, but no strategy could enter. Late discovery (10:03) also limits opportunity.

*Add future "scanner found, Ross skipped" cases here.*

---

## 4. Discovery Timing Analysis

How early does our scanner find stocks vs when Ross acts on them?

| Date | Stock | Ross Alert | Scanner Discovery | Delta | Impact |
|------|-------|------------|-------------------|-------|--------|
| 2025-02-28 | BTII | 7:00 AM | NOT FOUND | — | Entire move missed. Scanner can't see pre-7:15 movers. |
| 2025-02-28 | ZOZ/ZOOZ | 8:30 AM | **8:27 AM** | **+3 min** | Bot found it FIRST. Ticker format difference (ZOZ vs ZOOZ). |
| 2025-02-28 | NVVE | ~8:30 AM | 8:35 AM | **-5 min** | Bot 5 min late. Both in same scan window. |
| 2026-03-19 | CHNR | 7:16 AM | 8:00 AM | **-44 min** | Missed entire first leg ($3.50→$6.00). Primary cause of 0 trades. |
| 2026-03-20 | ARTL | ~9:00 AM | pre-open | **+60 min** | Scanner found it earlier. Bot's first trade at 09:09. |

**Patterns emerging**:
- For gap-based discovery (8:00+ movers): scanner is competitive with Ross, sometimes faster (ZOZ +3 min, ARTL +60 min).
- For pre-7:15 movers (BTII at 7:00, CHNR at 7:16): scanner is blind or 44+ min late. This is the biggest structural gap.
- The faster rescan task in MASTER_TODO addresses this. Priority: HIGH.

---

## 5. Scanner Parameter Tuning Ideas

### Under consideration (evidence needed before changing)

| Parameter | Current | Proposed | Evidence For | Evidence Against | Status |
|-----------|---------|----------|-------------|-----------------|--------|
| Gap floor | 10% | No change | BTII miss was timing, not threshold. At 7:15, BTII may have been at 5–10% gap — lowering to 5% would add massive noise for one edge case. | All found stocks had 18–67% gaps. 10% floor is not the bottleneck. | **NO CHANGE — timing is the real issue** |
| Float ceiling | 10M | No change | No evidence yet | ZOOZ (8.0M) was profitable for Ross. Current ceiling captures the range. | **NO CHANGE** |
| RVOL floor | 2.0x | No change | All found stocks well above (14.6x–183x) | No misses attributable to RVOL | **NO CHANGE** |
| First scan time | 7:15 AM | **6:30–7:00 AM** | BTII found at 7:00, CHNR at 7:16 — both pre-first-scan. Two misses/late finds from the same root cause. | Earlier scan = more Databento API cost, more noisy candidates that fade before open | **HIGH PRIORITY** — 2 data points now |
| Rescan frequency | 30 min | 5-10 min | CHNR 44-min gap between first scan and first rescan | Cost, complexity | **HIGH PRIORITY** — separate task in MASTER_TODO |
| Reverse split / compliance filter | N/A | Add? | BTII was a compliance play. These have unique characteristics (low gap, news-driven, not volume-first). | Very niche category. Adds complexity for rare edge case. | **MONITOR** — log more cases |
| Continuation scan | N/A | Add? | ARTL 3/20 was a continuation, not a fresh gap. Ross's continuation scanner is a separate concept. | Scanner caught ARTL anyway via gap. ZOZ also caught via gap despite being "no catalyst." | **LOW PRIORITY** — gap scan is catching these |
| Setup quality grade | N/A | A/B/C | Ross rated ARTL B-quality (no catalyst), ZOZ was pure momentum (no setup). Modulate size by quality. | Need more data to define grading criteria. | **RESEARCH** — see Strategy 5 in MASTER_TODO |
| Ticker normalization | N/A | Fix | ZOZ showed as ZOOZ in our scanner. Minor but confusing for cross-referencing. | Cosmetic only, doesn't affect discovery. | **LOW** |
| Null-float rejection | Reject null float_shares / profile "X" | **Bypass or estimate** | GDTC (Jan 6, 2025): 93.6% gap, 94x RVOL, $6.68 PM price — Ross +$5,300. Silently rejected by `load_and_rank()` due to missing float. | Removing float filter entirely could admit low-quality stocks. Need selective bypass. | **HIGH PRIORITY** — confirmed missed winner |

### Decided (enough evidence)

*None yet. Decisions will be made after completing all recap comparisons. Two strong data points for earlier first scan / faster rescan — approaching decision threshold.*

---

## 6. Recap Processing Queue

Track which Ross recaps have been analyzed and which are pending.

| Date | Status | Report | Ross P&L | Bot P&L | Key Finding |
|------|--------|--------|----------|---------|-------------|
| 2025-02-28 | **COMPLETE** | `2025-02-28_ross_recap_comparison.md` | +$23,932 | $0 | 2/3 found. BTII miss = pre-7:15 timing. ZOZ found 3 min early. Strategy gap >> scanner gap. |
| 2026-03-18 | **PARTIAL** | (data in MASTER_TODO, no standalone report) | TBD | TBD | ARTL curl pattern = Ross's best trade |
| 2026-03-19 | **COMPLETE** | `CHNR_2026-03-19_METHODOLOGY_GAP_ANALYSIS.md` | +$2,506 | $0 | Scanner 44 min late, 0 trades, Strategy 4+5 gap |
| 2026-03-20 | **COMPLETE** | `2026-03-20_ross_vs_bot_artl.md` | +$6,100 | +$1,054 | Ross 6x bot on same stock. Strategy 5 validated. |

**Running totals across all analyzed days:**
| Metric | Value |
|--------|-------|
| Ross total P&L | +$32,538+ |
| Bot total P&L | +$1,054 |
| Bot capture rate | ~3.2% of Ross's P&L |
| Scanner hit rate | 4/5 = 80% |
| Scanner misses | 1 (BTII — timing/architecture, not parameters) |

*Add new recap dates here as they're processed. Goal: complete all recaps, then run final tuned scan.*

---

## 7. Final Re-Run Plan

Once all recaps are cataloged and parameter changes decided:

1. Lock parameter changes in `scanner_sim.py` and `live_scanner.py`
2. Re-run `scanner_sim.py` across ALL available dates (currently ~55 YTD + 85 OOS)
3. Compare new scan results against Ross's picks for every analyzed date
4. Run squeeze V2 + MP backtests on any newly discovered stocks
5. Compute revised hit rate, P&L impact, and false positive rate
6. Update MASTER_TODO with final scanner parameters

**This re-run should happen ONCE, after all evidence is in. No premature tuning.**

---

*This is a living document. Update after every Ross recap comparison.*
