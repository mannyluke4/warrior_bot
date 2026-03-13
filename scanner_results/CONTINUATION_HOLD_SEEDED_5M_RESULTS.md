# Continuation Hold — Seeded 5-Minute Guard Results
## Generated 2026-03-13

---

## Overview

Tests whether looking backward at already-completed 5m bars (instead of observing forward) can instantly decide at entry whether to activate 5m guard. If the last N completed 5m bars are all green, the stock has already proven itself — activate immediately. If not, stay in 10s hold mode.

### Concept
At trade entry:
1. Get all completed 5m bars from bb_5m for this symbol
2. If fewer than 2 exist → stay in 10s hold (not enough proof)
3. If last 2 are both green (close > open) AND vol_dom >= 2.0x → activate 5m guard immediately
4. If not all green → stay in 10s hold (safe default)

### Configuration
```
WB_CONTINUATION_HOLD_ENABLED=1
WB_CONT_HOLD_5M_TREND_GUARD=1
WB_CONT_HOLD_5M_VOL_EXIT_MULT=2.0
WB_CONT_HOLD_5M_MIN_BARS=2            # ← Changed from 3 to 2
WB_CONT_HOLD_MIN_VOL_DOM=2.0
WB_CONT_HOLD_MIN_SCORE=8.0
WB_CONT_HOLD_MAX_LOSS_R=0.5
WB_CONT_HOLD_CUTOFF_HOUR=10
WB_CONT_HOLD_CUTOFF_MIN=30
```

### Sizing
- Risk: $1,000, dynamic sizing (2.5% of equity)

---

## Results: 5-Way Comparison

| Metric | Baseline | 10s Hold | Old 5m Guard | Graduated 5m | Seeded 5m |
|--------|----------|----------|-------------|-------------|-----------|
| Total P&L | **-$3,197** | **-$1,380** | **+$3,238** | **-$1,379** | **+$3,238** |
| Delta vs baseline | — | +$1,817 | +$6,435 | +$1,818 | **+$6,435** |
| 5m guard activations | — | — | 4 (all) | 0 (none) | **4 (all seeded)** |

**The seeded approach produces identical results to the old 5m guard (+$3,238).** All 4 qualifying stocks had 2+ green 5m bars at entry, so all seeded successfully. The decision is instant at entry — no observation period needed.

---

## Per-Trade Comparison

### Qualifying Trades

| Symbol | Date | Score | Baseline | 10s Hold | Old 5m | Grad 5m | Seeded 5m | Seeded? | Detail |
|--------|------|-------|----------|----------|--------|---------|-----------|---------|--------|
| BNAI T1 | 2026-01-14 | 12.5 | -$88 | +$804 | +$5,732 | +$1,334 | **+$5,732** | YES | 2/2 green bars, held 19min → TW @ $5.62 |
| NCI | 2026-02-20 | 12.0 | +$55 | +$596 | +$580 | +$384 | +$580 | YES | 2/2 green bars, guard OFF at 10:15 |
| HIMZ | 2026-02-05 | 10.5 | -$92 | +$272 | -$45 | -$45 | -$45 | YES | 2/2 green (premarket), guard OFF at 08:55 |
| GNPX T1 | 2025-11-05 | 12.5 | -$445 | -$425 | -$402 | -$425 | -$402 | YES | 2/2 green bars, guard OFF instantly |
| **Subtotal** | | | **-$570** | **+$1,247** | **+$5,865** | **+$1,248** | **+$5,865** | | |

### Non-Qualifying Trades (unchanged across all modes)

| Symbol | Date | P&L |
|--------|------|-----|
| YIBO | 2025-01-27 | -$1,016 |
| IPST | 2025-11-05 | +$442 |
| BOLT | 2026-01-14 | $0 |
| INBS | 2026-02-05 | $0 |
| SPHL | 2026-01-15 | -$244 |
| CRMX | 2026-02-03 | -$459 |
| HYPD | 2025-11-05 | $0 |
| SLMT | 2025-11-05 | $0 |
| TWAV | 2025-12-08 | -$1,350 |
| UONE | 2026-02-12 | $0 |
| CGTL | 2026-02-12 | $0 |
| **Subtotal** | | **-$2,627** |

---

## Detailed Seeded Activation Behavior

### BNAI — Seeded Successfully (+$5,732)

**Trade 1:** Entry 09:41 @ $4.51, score 12.5
- 2 completed green 5m bars at entry (09:30, 09:35) → **SEEDED**
- 09:40 — HOLD: green bar, 4.3x avg volume @ $4.81
- 09:45 — HOLD: green bar, 5.4x avg volume @ $5.17
- 09:50 — HOLD: green bar, 3.2x avg volume @ $5.62
- 09:55 — **GUARD OFF**: vol_dom dropped below 2.0x
- 10:00 — TW exit @ $5.62 → **+$6,543** (+38.5R)

**Trade 2:** Entry 10:13 @ $6.77, score 12.5
- Recent 5m bars: only 1/2 green (09:55 bar was red after the peak) → **NOT SEEDED** → 10s hold
- 10:16 — TW exit @ $6.34 → -$811
- Correctly stayed in 10s hold — the stock had already peaked

### NCI — Seeded, Guard Deactivated Early (+$580)

- Entry 10:05, 2/2 green bars → **SEEDED**
- 10:05 — HOLD: green bar, 1.9x avg @ $5.59
- 10:10 — HOLD: green bar, 1.6x avg @ $5.70
- 10:15 — **GUARD OFF**: vol_dom dropped
- 10:26 — BE exit @ $5.82 → +$580
- Same as old 5m guard — guard deactivated naturally, then normal exit fired

### HIMZ — Seeded from Premarket Bars (-$45)

- Entry 08:53, 2/2 green premarket bars → **SEEDED** (unexpected — see analysis below)
- 08:50 — HOLD: green bar @ $4.28
- 08:55 — **GUARD OFF**: vol_dom dropped after just one bar
- 09:02 — BE exit @ $4.01 → -$45
- Same result as old 5m guard

### GNPX — Seeded, Guard Deactivated Instantly (-$402)

- Trade 1 entry 10:20, 2/2 green bars → **SEEDED**, guard OFF instantly, TW exit → +$62
- Trade 2 entry 11:55 (after cutoff) → no seed check, BE exit → -$464

---

## Analysis

### Why Seeded Results Match Old 5m Guard Exactly

All 4 qualifying stocks had 2+ green 5m bars at entry. The seeded check activated 5m guard on every qualifying trade — same as the old immediate activation. The only difference: BNAI trade 3 (10:13) correctly stayed in 10s hold because recent 5m bars weren't all green, while old 5m guard activated there too. But trade 3 lost -$811 regardless, so the net P&L is identical.

### HIMZ: Premarket Bars Defeated the Seeding Filter

The directive expected HIMZ to NOT seed because "0 bars at entry (premarket)". But bb_5m receives premarket seed bars during the bar seeding phase (the `seed_bar_close` calls from 4AM-onward historical bars). By 08:53, HIMZ had 2 completed green 5m bars from premarket activity.

**This is a design gap in the seeding approach.** Premarket bars should arguably not count for the green-bar check, since premarket volume characteristics differ from regular session. However, excluding premarket bars would need a time-of-day filter (only count bars after 09:30 ET), which would prevent BNAI from seeding at 09:41 (it would only have 2 regular-session bars from 09:30 and 09:35 — barely enough).

### The Seeded Approach's Real Value

Even though results match old 5m guard on this dataset, seeded activation is architecturally superior:
1. **Data-driven decision at entry** — looks at proof (green bars) instead of blindly committing
2. **Filters late re-entries** — BNAI trade 3 correctly stayed in 10s hold (1/2 green bars)
3. **Future-proof** — on a stock that entered after a choppy/red 5m period, seeding would correctly NOT activate, while old 5m guard would blindly commit

### What Would Make HIMZ Different

To protect HIMZ while keeping BNAI, options include:
- **Require 3+ green bars** (HIMZ only had 2 premarket bars, would fail) — but BNAI also only had 2 at 09:41
- **Only count regular-session bars** (bars after 09:30 ET) — HIMZ enters at 08:53 with 0 session bars → NOT seeded → +$272
- **Volume threshold on seed bars** — premarket bars have lower volume, wouldn't meet a threshold

---

## Recommendation

**The seeded approach is the correct architecture for 5m guard activation.** It matches old 5m guard performance (+$3,238) while being data-driven and filtering late re-entries.

To protect borderline cases like HIMZ, consider adding a **regular-session filter**: only count 5m bars that close after 09:30 ET for the green-bar seeding check. This would:
- BNAI (09:41 entry): 2 regular-session bars (09:30, 09:35) → seeded → +$5,732
- HIMZ (08:53 entry): 0 regular-session bars → NOT seeded → falls back to 10s hold (+$272)

**Current default: `WB_CONT_HOLD_5M_TREND_GUARD=0` (OFF).** The seeded approach is ready for further refinement with the session filter.

---

*Generated from 15-stock backtest | Tick mode, Alpaca feed, dynamic sizing ($1,000 risk) | Branch: v6-dynamic-sizing*
