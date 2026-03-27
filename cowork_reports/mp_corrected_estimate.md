# MP-Only Megatest: Corrected Results Estimate

**Date:** 2026-03-21
**Author:** Cowork (Opus)
**Status:** ESTIMATE — awaiting actual corrected megatest run
**Data source:** `megatest_state_mp_only_FAULTY.json` (Config B, 255 trades)

---

## The Bug's Impact on MP-Only Results

The sim_start bug set discovery times to the raw minute stocks first met filter criteria (often 4:00-4:05 AM) instead of the scanner checkpoint time. This affected 46% of all candidates (405/873).

For the MP-only megatest specifically:

- **133 of 255 trades (52%)** entered before the corrected sim_start time. These are "suspect" — they either wouldn't exist or would look different with correct timing.
- **122 trades** entered after the corrected sim_start but 100 of those had wrong EMA/VWAP seeding from the early start. Only **22 trades** are fully unaffected.
- **VERO on 2026-01-16 was completely missed** — the single biggest MP trade in the dataset. With sim_start=04:00, the detector never triggered. With correct sim_start=07:00, it produces **+$17,505** (18.6R).

---

## Faulty Baseline

| Metric | Faulty Value |
|--------|-------------|
| Total Trades | 255 |
| Winners / Losers | 78W / 175L / 2BE |
| Win Rate | 30.6% |
| Total P&L | -$14,483 |
| Final Equity | $15,517 |
| Starting Equity | $30,000 |

---

## Trade Classification

### Suspect Trades (133 — entered before corrected sim_start)

These trades fired because the simulator was already "live" when it shouldn't have been. With corrected timing, most will disappear. Some may reappear with different characteristics.

| Metric | Value |
|--------|-------|
| Count | 133 |
| Winners | 47 |
| Losers | 85 |
| Breakeven | 1 |
| Net P&L | -$651 |

The suspects include both big winners and many losers:

**Top suspect winners (likely to refire with corrected timing):**

| Symbol | Date | Entry Time | Faulty Start | Corrected Start | P&L | R-Mult |
|--------|------|-----------|--------------|-----------------|-----|--------|
| MB | 2025-08-18 | 09:45 | 09:41 | 10:00 | +$2,994 | +7.2R |
| ROLR | 2026-01-14 | 08:26 | 08:18 | 08:30 | +$2,299 | +6.5R |
| ACON | 2025-03-03 | 06:13 | 06:00 | 07:00 | +$876 | +1.4R |
| XAGE | 2025-05-22 | 06:20 | 04:05 | 07:00 | +$699 | +1.4R |
| AIHS | 2025-09-03 | 07:43 | 07:40 | 08:00 | +$651 | +1.4R |
| PTHS | 2025-01-21 | 09:43 | 09:35 | 10:00 | +$619 | +0.9R |
| DWTX | 2025-03-07 | 10:04 | 10:01 | 10:30 | +$514 | +0.8R |
| PBM | 2025-07-31 | 07:47 | 07:38 | 08:00 | +$501 | +1.2R |
| SPRC | 2025-09-17 | 04:13 | 04:00 | 07:00 | +$460 | +1.0R |
| BRIA | 2025-09-04 | 04:10 | 04:00 | 07:00 | +$458 | +1.8R |

Total of top 10 suspect winners: **+$10,071**

Note: MB and ROLR had faulty starts only 4-19 minutes before corrected. High probability they still trigger. ACON, XAGE, SPRC, BRIA had starts hours before corrected — these need re-simulation to know if they survive.

### Clean Trades (122 — entered after corrected sim_start)

| Metric | Value |
|--------|-------|
| Fully unaffected (correct start AND correct state) | 22 |
| State-affected (correct entry time, but wrong EMA seed) | 100 |
| Total P&L | -$13,832 |

The 100 state-affected trades are the major wild card. They entered at the right time, but the detector's EMA/MACD/VWAP state was seeded from 4AM instead of 7AM. This could flip individual trades either way.

- **Unaffected 22 trades P&L:** -$3,075
- **State-affected 100 trades P&L:** -$10,757

---

## Known Missed Trades

### VERO — 2026-01-16 (confirmed)

The single most impactful miss. From the old `ytd_v2_backtest_state_mp_only.json` (which used hardcoded 07:00 start):

| Field | Value |
|-------|-------|
| Entry Time | 07:14 |
| Entry Price | $3.58 |
| Exit Price | $5.81 |
| R-Multiple | +18.6R |
| P&L | +$17,505 |
| Exit Reason | bearish_engulfing_exit_full |

The faulty megatest produced **0 trades on this date**. The corrected run will almost certainly recover this trade, though the exact P&L depends on equity level at that point (sizing is dynamic).

### Potential Other Misses

588 candidates had wrong sim_start and produced 0 trades in the faulty run. The highest-volume ones most likely to produce trades with corrected timing:

| Symbol | Date | Faulty Start | Corrected | Gap % | PM Volume | Float |
|--------|------|-------------|-----------|-------|-----------|-------|
| CETY | 2025-11-25 | 09:41 | 10:00 | 92% | 78.8M | 4.2M |
| XAIR | 2026-01-13 | 10:02 | 10:30 | 172% | 71.2M | 9.4M |
| BATL | 2026-01-26 | 04:00 | 07:00 | 391% | 69.5M | 7.2M |
| BKYI | 2025-10-27 | 06:58 | 07:00 | 169% | 65.0M | 9.6M |
| TNON | 2025-03-25 | 05:09 | 07:00 | 265% | 63.2M | 7.7M |
| BIAF | 2026-03-13 | 09:36 | 10:00 | 122% | 58.8M | 4.3M |
| VSEE | 2025-10-28 | 09:01 | 09:30 | 308% | 58.4M | 7.2M |

These are high-gap, high-volume stocks that the MP detector might trigger on with correct timing. Impossible to predict P&L without running the simulation, but there's meaningful upside potential here.

---

## Corrected P&L Estimate

### Scenario 1: Conservative (-$14,483 → +$3,673)

Assumptions: Remove all 133 suspect trades, add only confirmed VERO, assume no other new trades.

| Component | P&L |
|-----------|-----|
| Clean trades (122) | -$13,832 |
| VERO 2026-01-16 | +$17,505 |
| **Total** | **+$3,673** |
| **Final Equity** | **$33,673** |

### Scenario 2: Moderate (-$14,483 → +$9,715)

Assumptions: Clean trades + VERO + 60% of top 10 suspect winners refire.

| Component | P&L |
|-----------|-----|
| Clean trades (122) | -$13,832 |
| VERO 2026-01-16 | +$17,505 |
| Top suspect winners (60% refire) | +$6,042 |
| **Total** | **+$9,715** |
| **Final Equity** | **$39,715** |

### Scenario 3: Optimistic (-$14,483 → +$13,729)

Assumptions: Clean trades + VERO + 80% of top suspect winners + misc new winners from corrected timing.

| Component | P&L |
|-----------|-----|
| Clean trades (122) | -$13,832 |
| VERO 2026-01-16 | +$17,505 |
| Top suspect winners (80% refire) | +$8,056 |
| Misc new winners from corrected timing | +$2,000 |
| **Total** | **+$13,729** |
| **Final Equity** | **$43,729** |

### Summary Range

| Scenario | P&L | Final Equity | Return |
|----------|-----|-------------|--------|
| Faulty (actual) | -$14,483 | $15,517 | -48.3% |
| Conservative | +$3,673 | $33,673 | +12.2% |
| Moderate | +$9,715 | $39,715 | +32.4% |
| Optimistic | +$13,729 | $43,729 | +45.8% |

---

## The VERO Problem

This estimate reveals a structural concern that persists regardless of the bug fix: **MP's profitability hinges on a single trade.**

VERO 2026-01-16 accounts for +$17,505 of a strategy that otherwise produces -$13,832 to -$14,483 across 250+ trades. Without VERO, MP is deeply negative in every scenario.

This is textbook fat-tail dependency: the strategy needs a handful of monster trades to offset hundreds of small losses. Whether that's a feature or a flaw depends on whether those monsters are consistently findable or just lucky outliers.

From the faulty data, only 3 trades exceeded +$1,000:
- MB +$2,994 (7.2R)
- ROLR +$2,299 (6.5R)
- VERO (missed, would have been +$17,505 at 18.6R)

The next tier is thin: only 8 trades between +$500 and +$1,000. Everything else is small wins fighting a tide of small losses.

---

## Major Uncertainty: State-Affected Trades

The biggest unknown in this estimate is the 100 "state-affected" clean trades. These entered at the right time but with wrong EMA/MACD state (seeded from 4AM instead of 7AM). They contributed **-$10,757** to the faulty results.

With correct seeding:
- Some losers might not trigger (EMA in different position → no impulse detected)
- Some might trigger differently (different stop levels, different scores)
- New trades might appear that didn't exist before

This is a ~$10K uncertainty band that only the actual corrected megatest can resolve.

---

## What This Means for the Corrected Megatest

When the corrected megatest runs, watch for:

1. **VERO 2026-01-16 must appear** — if it doesn't, something else is wrong
2. **Total trade count will likely drop** to 140-180 range (removing premarket ghost trades)
3. **Win rate should improve slightly** — many suspect trades were premarket garbage
4. **Net P&L should be positive** — the conservative estimate already shows +$3,673
5. **The fat-tail dependency problem will remain** — MP is still a "need one big winner" strategy

The corrected run is the only way to get real numbers, but this estimate gives confidence that MP isn't as broken as -$14,483 suggests. The bug was masking what is likely a modestly profitable (but highly VERO-dependent) strategy.

---

*Report by Cowork (Opus) — 2026-03-21*
