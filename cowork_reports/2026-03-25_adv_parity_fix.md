# CC Report: ADV Parity Investigation — Deeper Than Expected
## Date: 2026-03-25
## Machine: Mac Mini

---

## Key Finding: ADV Is NOT the Problem — Both Scanners Get the Same ADV

The trace script tested FEED, CODX, MKDW, and WTO across all three code paths (scanner_sim no-feed, stock_filter sip, scanner_sim+sip). **ALL produce identical ADV values.**

| Stock | Path A (scanner_sim) | Path B (stock_filter) | Path C (A+sip) | Ratio A/B |
|-------|---------------------|----------------------|----------------|-----------|
| FEED | 7,767,076 | 7,767,076 | 7,767,076 | 1.0x |
| CODX | 3,433,787 | 3,433,787 | 3,433,787 | 1.0x |
| MKDW | 323,260 | 323,260 | 323,260 | 1.0x |
| WTO | 104,538 | 104,538 | 104,538 | 1.0x |

The `feed="sip"` parameter and date window differences make NO difference.

## The Real Problem: BOTH Scanners Are Wrong (In Different Directions)

### scanner_sim.py — RVOL Too LOW
- Uses cumulative PM volume (4:00-checkpoint) as numerator
- Divides by FULL-DAY average volume (ADV)
- Result: at 8:45 AM, a stock with 1.4M PM vol / 7.7M ADV = 0.21x RVOL → filtered
- **This is mathematically correct but practically useless** — PM volume is always a fraction of a full day

### stock_filter.py — RVOL Inflated at 4 AM
- Uses `snap.daily_bar.volume` as numerator
- At 4:04 AM, this value may include YESTERDAY's residual volume before Alpaca resets
- FEED: `daily_bar.volume` at scan time was likely ~131M (yesterday's close) or today's early accumulation
- With ADV = 7.7M: RVOL = 131M / 7.7M ≈ 17x (close to reported 19.2x)
- **FEED traded 131 MILLION shares yesterday** — that's what inflated the live bot's RVOL

### Evidence
```
FEED snapshot (end of 2026-03-25):
  daily_bar.volume:      19,136,770 (today)
  prev_daily_bar.volume: 131,169,730 (yesterday — MASSIVE catalyst day)
```

The live bot scanned at 4:04 AM. At that point, `daily_bar.volume` was either:
- Yesterday's 131M (not yet reset) → RVOL ≈ 17x
- Or today's early accumulation (still very high from afterhours/premarket) → similar result

### ADV Outlier Problem
FEED's 20-day average is inflated by yesterday's 131M volume day:
```
Last 5 daily volumes: [328,233, 119,113, 202,707, 131,169,730, 19,116,692]
```
One day at 131M vs normal days at ~200K. The 20-day average is 7.7M but the MEDIAN daily volume is probably ~200K. Both scanners using the mean are distorted by this outlier.

## What This Means

1. **scanner_sim RVOL gate is structurally broken** for rescan stocks — PM volume will always be a small fraction of full-day ADV. Time-scaling or median-based ADV is needed.

2. **stock_filter RVOL is unreliable at 4 AM** — the `daily_bar.volume` field may carry yesterday's volume. Stocks with a big previous day get artificially high RVOL. FEED only passed the live scanner BECAUSE yesterday was a 131M volume day.

3. **Neither scanner is computing RVOL the way Ross Cameron would** — Ross looks at whether today's premarket volume is UNUSUAL relative to this stock's TYPICAL premarket volume, not relative to its full-day average.

## Recommended Fix

**For scanner_sim.py (backtest):**
- Option 1: Time-scale ADV — at checkpoint 08:45, divide ADV by `16` (trading hours) and multiply by `4.75` (hours elapsed since 4 AM). Makes partial-day volume comparable to partial-day expectation.
- Option 2: Use PM-specific ADV — compute 20-day average of 4:00-7:15 volume (not full-day). This requires fetching intraday bars for the lookback period.
- Option 3: Drop RVOL gate on rescan, use absolute volume threshold only (>100K cumulative at discovery). Simplest, least accurate.

**For stock_filter.py (live bot):**
- Verify `daily_bar.volume` is actually TODAY's volume at scan time, not yesterday's residual
- Consider using `sum of today's minute bars` instead of `daily_bar.volume` for a clean intraday accumulation

## Files
- `/tmp/adv_trace.py` output embedded above (not committed)
- `cowork_reports/2026-03-25_adv_parity_fix.md` (this file)
