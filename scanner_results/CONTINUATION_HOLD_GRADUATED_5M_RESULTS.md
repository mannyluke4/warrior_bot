# Continuation Hold — Graduated 5-Minute Guard Results
## Generated 2026-03-13

---

## Overview

Tests whether a graduated activation approach (observe first in 10s hold mode, then upgrade to 5m guard only if vol_dom sustains) captures the best of both worlds: BNAI's runner capture + safe exits on borderline stocks.

### Concept
Instead of immediately committing to 5m mode at entry:
1. **Observation phase** (first 3 five-minute bars): trade runs in normal 10s hold mode (max_holds=2). Bot monitors vol_dom on each 5m bar close.
2. **Activation phase** (after 3 bars, if vol_dom sustained): trade upgrades to full 5m guard mode — all 10s/1m exits suppressed, exit only on high-volume red 5m bar.

### Configuration
```
WB_CONTINUATION_HOLD_ENABLED=1
WB_CONT_HOLD_5M_TREND_GUARD=1
WB_CONT_HOLD_5M_VOL_EXIT_MULT=2.0
WB_CONT_HOLD_5M_MIN_BARS=3
WB_CONT_HOLD_MIN_VOL_DOM=2.0
WB_CONT_HOLD_MIN_SCORE=8.0
WB_CONT_HOLD_MAX_LOSS_R=0.5
WB_CONT_HOLD_CUTOFF_HOUR=10
WB_CONT_HOLD_CUTOFF_MIN=30
WB_CONT_HOLD_MAX_HOLDS=2
```

### Sizing
- Risk: $1,000, dynamic sizing (2.5% of equity)

---

## Results: 5-Way Comparison

| Metric | Baseline | 10s Hold | 1m Exit | Old 5m Guard | Graduated 5m |
|--------|----------|----------|---------|-------------|-------------|
| Total P&L | **-$3,197** | **-$1,380** | **-$1,120** | **+$3,238** | **-$1,379** |
| Delta vs baseline | — | +$1,817 | +$2,077 | +$6,435 | +$1,818 |
| 5m guard activations | — | — | — | 4 (immediate) | **0** |

**The graduated approach never activated 5m guard mode on any trade.** Vol_dom dropped below 2.0x before completing 3 observation bars for every qualifying stock. The result is effectively identical to 10s hold mode.

---

## Per-Trade Comparison

### Qualifying Trades

| Symbol | Date | Score | Baseline | 10s Hold | 1m Exit | Old 5m | Grad 5m | Observation Detail |
|--------|------|-------|----------|----------|---------|--------|---------|-------------------|
| BNAI | 2026-01-14 | 12.5 | -$88 | +$804 | +$1,242 | +$5,732 | +$1,334 | Aborted bar 1/3 (trade 3); trades 1-2 exited during obs |
| NCI | 2026-02-20 | 12.0 | +$55 | +$596 | +$327 | +$580 | +$384 | Aborted bar 2/3 (trade 2); trade 1 exited during obs |
| HIMZ | 2026-02-05 | 10.5 | -$92 | +$272 | +$363 | -$45 | -$45 | Aborted bar 2/3 |
| GNPX | 2025-11-05 | 12.5 | -$445 | -$425 | -$425 | -$402 | -$425 | Aborted bar 1/3 (trade 1 after cutoff: no obs) |
| **Subtotal** | | | **-$570** | **+$1,247** | **+$1,507** | **+$5,865** | **+$1,248** | |

### Non-Qualifying Trades (unchanged across all modes)

| Symbol | Date | P&L | Why Not Held |
|--------|------|-----|-------------|
| YIBO | 2025-01-27 | -$1,016 | After 10:30 cutoff |
| IPST | 2025-11-05 | +$442 | Score < 8 |
| BOLT | 2026-01-14 | $0 | No trades taken |
| INBS | 2026-02-05 | $0 | Score < 8 |
| SPHL | 2026-01-15 | -$244 | Vol dom < 2.0 |
| CRMX | 2026-02-03 | -$459 | Vol dom < 2.0 |
| HYPD | 2025-11-05 | $0 | No trades taken |
| SLMT | 2025-11-05 | $0 | No trades taken |
| TWAV | 2025-12-08 | -$1,350 | Vol dom < 2.0 |
| UONE | 2026-02-12 | $0 | No trades taken |
| CGTL | 2026-02-12 | $0 | No trades taken |
| **Subtotal** | | **-$2,627** | |

---

## Detailed Observation Phase Behavior

### BNAI — Observation Never Completed (+$1,334 vs +$5,732 old 5m)

**Trade 1:** Entry 09:41 @ $4.51, score 12.5
- Observation started, watching vol_dom for 3 bars
- **09:44 — TW exit fired @ $4.81** → +$1,765 (trade closed DURING observation, before first 5m bar)
- The 10s hold mode allowed this exit; old 5m guard would have suppressed it

**Trade 2:** Entry 09:47 @ $5.12, score 9.5
- Observation restarted on new trade
- 09:45 — vol_dom sustained (bar 1/3)
- **09:50 — TW exit fired @ $5.24** → +$380 (again, closed during observation)

**Trade 3:** Entry 10:13 @ $6.77, score 12.5
- Observation started
- 10:10 — **ABORT**: vol_dom dropped (bar 1/3)
- 10:16 — TW exit → -$811

**Key insight:** BNAI's fast parabolic run generated TW signals every 3-5 minutes. The observation phase (15 min minimum) couldn't survive because exits kept closing and re-opening trades. The old 5m guard's immediate commitment was actually correct for this stock — the speed of the move IS the signal.

### NCI — Observation Aborted, Fell Back to 10s Hold (+$384)

**Trade 1:** Entry 10:05 @ $5.52, score 12.0
- Observation started
- **10:08 — TW exit fired @ $5.60** → +$154 (during observation)

**Trade 2:** Entry 10:11 @ $5.72, score 10.5
- Observation restarted
- 10:10 — vol_dom sustained (bar 1/3)
- 10:15 — **ABORT**: vol_dom dropped (bar 2/3)
- 10:26 — BE exit @ $5.82 → +$230

### HIMZ — Observation Aborted (-$45)

- Entry 08:53, observation started
- 08:50 — vol_dom sustained (bar 1/3)
- 08:55 — **ABORT**: vol_dom dropped (bar 2/3)
- 09:02 — BE exit @ $4.01 → -$45
- Same result as old 5m guard (guard also deactivated early)

### GNPX — Observation Aborted Instantly (-$425)

- Trade 1 entry 10:20 — observation aborted bar 1/3, TW exit @ $5.47 → +$39
- Trade 2 entry 11:55 — after 10:30 cutoff, no observation, BE exit → -$464

---

## Analysis

### Why Graduated Activation Failed

The fundamental assumption was wrong: **stocks that deserve 5m guard mode CAN'T sustain vol_dom through an observation period because the observation period is too long relative to the speed of the move.**

BNAI's parabolic run from $4.51 to $5.62 happened in 19 minutes. The observation period is 15 minutes (3 × 5m bars). By the time observation would complete, the entire move has already happened. Worse, TW signals fire every few minutes during a parabolic run, causing the trade to close and re-open repeatedly during observation.

### The Graduated Approach Collapses to 10s Hold

Since no stock sustained vol_dom through 3 bars:
- **Graduated 5m total: -$1,379**
- **10s hold total: -$1,380**

These are nearly identical because the graduated approach IS 10s hold during observation, and observation never completes.

### The Catch-22

The graduated approach creates a catch-22:
- **Short observation (1-2 bars):** Would activate on NCI/HIMZ too, losing the safety benefit
- **Long observation (3+ bars):** Never activates on BNAI, losing the runner capture benefit
- **Any observation period:** Exits fire during observation, preventing sustained tracking

The old 5m guard's "commit at entry" approach is actually the only way to capture BNAI's move — you need to suppress ALL exits from the moment the trade opens, because the very first TW signal fires within minutes.

---

## Recommendation

**The graduated approach does not improve on any existing mode.**

| Approach | Best For | Total P&L |
|----------|----------|-----------|
| 10s Hold | Safe default, protects borderline cases | -$1,380 |
| 1m Exit | Moderate improvement, slight edge over 10s | -$1,120 |
| Old 5m Guard | Maximum runner capture (BNAI), accepts borderline risk | +$3,238 |
| **Graduated 5m** | **Nothing — collapses to 10s hold** | **-$1,379** |

**Keep `WB_CONT_HOLD_5M_TREND_GUARD=0` (OFF) as the default.** The choice is between:
- **Conservative:** 10s hold (OFF by default, `WB_CONTINUATION_HOLD_ENABLED=1`)
- **Aggressive:** Old 5m guard (immediate activation) — massive upside on runners, slight risk on borderlines

The graduated middle ground doesn't exist for these trade durations.

---

*Generated from 15-stock backtest | Tick mode, Alpaca feed, dynamic sizing ($1,000 risk) | Branch: v6-dynamic-sizing*
