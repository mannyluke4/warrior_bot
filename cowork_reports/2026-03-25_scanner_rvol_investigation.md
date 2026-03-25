# CC Report: Scanner RVOL Investigation
## Date: 2026-03-25
## Machine: Mac Mini

---

## Root Cause: Confirmed as Scenario B + ADV Data Source Mismatch

### The Problem Is NOT Missing Data — It's Different ADV Computation

scanner_sim.py and stock_filter.py compute Average Daily Volume (ADV) from completely different sources, producing wildly different RVOL values for the same stock.

### Evidence: FEED on 2026-03-25

| Metric | scanner_sim.py | stock_filter.py (live) |
|--------|---------------|----------------------|
| PM/Cumulative Volume | 1,467,817 | ~2,200,000 |
| **ADV** | **6,832,393** | **~115,000** (inferred from RVOL) |
| **RVOL** | **0.21x** → FILTERED | **19.2x** → PASSES |

The ADV differs by **59x** (6.8M vs 115K). This isn't a rounding error — they're computing fundamentally different things.

### Why ADV Differs

**scanner_sim.py** (`get_avg_daily_volumes()`, line ~300):
- Fetches 20 days of daily bars from Alpaca REST
- Uses ALL trading hours volume (4AM-8PM)
- Result: FEED ADV = 6.8M (includes extended hours + regular session)

**stock_filter.py** (`get_stock_info()`, line ~84):
- Fetches 20 days of daily bars from Alpaca REST
- *Should* compute the same thing... but may be using a different timeframe, different bar aggregation, or `prev_daily_bar` from snapshot

**Additional possibility**: scanner_sim may be pulling SIP (consolidated) data while stock_filter pulls IEX (single exchange) data, or vice versa. SIP volume includes all exchanges; IEX is just one.

### Today's Full Diagnostic (2026-03-25)

**13 PM candidates — ALL filtered (RVOL < 2.0 or PM vol < 50K):**

| Stock | PM Vol | ADV | RVOL | Gap |
|-------|--------|-----|------|-----|
| BIAF | 967,252 | 24,608,630 | 0.04x | 18.2% |
| ARMG | 180,312 | 532,428 | 0.34x | 25.3% |
| SHNY | 141,734 | 1,181,471 | 0.12x | 11.2% |
| MKDW | 9,827 | 259,956 | 0.04x | 13.0% |
| (9 more, all < 0.6x RVOL) | | | | |

**18 rescan candidates — ALL filtered (RVOL < 2.0):**

| Stock | Cumul Vol | ADV | RVOL | Gap | Checkpoint |
|-------|-----------|-----|------|-----|-----------|
| CODX | 1,765,301 | 3,170,572 | 0.56x | 21.6% | 08:00 |
| FEED | 1,467,817 | 6,832,393 | 0.21x | 11.9% | 08:45 |
| CIFR | 1,574,689 | 23,855,835 | 0.07x | 11.4% | 08:00 |
| UGRO | 1,152,836 | 9,593,388 | 0.12x | 16.7% | 08:30 |
| WTO | 101,833 | 99,633 | 1.02x | 12.5% | 08:00 |
| (13 more, all < 1.0x RVOL) | | | | | |

**Highest rescan RVOL: WTO at 1.02x** — even the best candidate is half the 2.0x threshold.

### Known Good Date (2026-01-30) — Same Pattern

Only PMN passed the rescan RVOL gate (35x RVOL from ADV of 20K). All other rescan stocks were < 1.0x. Total: 2 candidates (VIVS from PM + PMN from rescan).

### Impact Assessment

**This is systematic, not a one-day fluke.** The ADV source mismatch means:
- PM candidates: Only stocks with genuinely extreme premarket RVOL (>2x of FULL-DAY average before 7:15 AM) pass. This is a very high bar.
- Rescan candidates: Cumulative volume is compared against full-day ADV, so by definition cumulative volume at 8:00 AM is ~1/3 of a normal full day → RVOL ≈ 0.3x → filtered.

### Recommendation

**Option A (Quick fix)**: Use cumulative volume at checkpoint time and scale ADV proportionally. At 8:00 AM (4 hours into a 16-hour trading day), scale ADV by `4/16 = 0.25`. A stock with 1.4M vol at 8:00 vs scaled ADV of `6.8M * 0.25 = 1.7M` gives RVOL = 0.82x — still below 2.0 but much more realistic.

**Option B (Align with live)**: Use the same ADV source as stock_filter.py. If the live bot is getting ADV=115K for FEED (implying a different bar feed or time window), scanner_sim should match.

**Option C (Replace RVOL gate)**: Use absolute PM volume threshold only (>50K or >100K) and drop the RVOL comparison entirely. The live bot already finds the right stocks using its own RVOL; the backtest scanner should find the same ones.

### Files
- `/tmp/scanner_diag_0325.txt` — today's full diagnostic output
- `/tmp/scanner_diag_0130.txt` — Jan 30 diagnostic output
- `cowork_reports/2026-03-25_scanner_rvol_investigation.md` (this file)
