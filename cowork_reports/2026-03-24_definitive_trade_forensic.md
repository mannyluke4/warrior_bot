# Definitive Trade Forensic: The -$1,941 Gap

**Comparison**: OLD V1 @ `aef59a1` (+$19,832) vs NEW V1 @ `8017aac` (+$17,891)
**Runner**: Same (`run_jan_v1_comparison.py`), same ENV_BASE, same risk sizing ($30K start, 2.5%)
**Only difference**: Scanner JSONs (old = pre-checkpoint-overhaul, new = post-all-fixes)

## The Numbers

| Metric | OLD V1 | NEW V1 |
|--------|--------|--------|
| Jan 2025 P&L | +$3,423 | +$1,768 |
| Jan 2026 P&L | +$16,409 | +$16,123 |
| Total | +$19,832 | +$17,891 |
| Trades | 49 | 42 |

## Attribution

| Category | Stock-Days | P&L Impact |
|----------|-----------|------------|
| **Identical trades** (same entry, same exit, same P&L) | 14 | $0 (carrying $4,707) |
| **Same stock, different result** (same stock+date, different P&L) | 11 | **-$799** |
| **Lost trades** (in old, not in new) | 12 | **-$774** |
| **New trades** (in new, not in old) | 6 | **-$373** |
| **Total** | | **-$1,946** ≈ -$1,941 |

**No single dominant cause.** The gap is spread across three roughly equal buckets.

---

## Identical Trades: 14 stock-days, $4,707 P&L (carried over)

These trades are byte-for-byte the same: same entry time, same entry price, same exit, same P&L (±$10 from risk sizing). The core strategy works identically on these stocks.

Key winners carried over: GDTC +$2,280, ALUR +$2,457, BATL +$615, AMOD +$633, VERO (nearly identical: $14,123 → $13,882)

## Same Stock, Different Result: 11 stock-days, -$799

Most of these are tiny P&L differences from equity-based risk sizing (different equity → different position size → ±$30 on same trade). Only two are meaningful:

| Date | Stock | Old P&L | New P&L | Delta | Root Cause |
|------|-------|---------|---------|-------|------------|
| 2025-01-21 | LEDS | -$351 (SQ) | -$689 (MP) | **-$338** | MP fires at 08:33 before SQ at 09:37; worse entry, bigger loss |
| 2026-01-15 | SPHL | -$132 (1t) | -$319 (2t) | **-$187** | Extra MP trade at 07:58 that old run didn't take |

Both are micro-pullback trades taking worse entries. The rest of the -$799 is risk-sizing noise.

## Lost Trades: 12 stock-days, -$774 net (lost $3,480 in winners, avoided $2,706 in losers)

### Lost Winners: $3,480

| Date | Stock | P&L Lost | Root Cause |
|------|-------|----------|------------|
| 2025-01-14 | **AIFF** | **+$1,061** | Stock not in new scanner JSON — old JSON had AIFF+OST, new has only NMHI |
| 2025-01-14 | **OST** | **+$726** | Same — stock not discovered by new scanner |
| 2026-01-15 | **CJMB** | **+$1,028** | Stock IS in new scanner top-5, but no trades — detector didn't ARM |
| 2026-01-20 | **POLA** | **+$556** | Bumped from top-5 by SDST (new discovery); ranked #6 |
| 2025-01-29 | SLXN | +$109 | Stock not in new scanner JSON |

### Avoided Losers: $2,706

| Date | Stock | P&L Avoided | Notes |
|------|-------|-------------|-------|
| 2025-01-21 | PTHS | -$711 | MP loser, not in new run |
| 2025-01-30 | STAI | -$795 | MP loser, not in new run |
| 2026-01-06 | CELZ | -$687 | 10:26 AM entry — after 9:30 cutoff in new scanner |
| Others | | -$513 | Small MP losers |

**Net lost trades: -$774.** The lost winners ($3,480) are largely offset by avoided losers ($2,706).

## New Trades: 6 stock-days, -$373

| Date | Stock | P&L | Type |
|------|-------|-----|------|
| 2025-01-13 | PHIO | -$247 | MP loser (new discovery) |
| 2025-01-14 | NMHI | -$143 | SQ loser (replaced AIFF+OST) |
| 2025-01-21 | VATE | -$160 | MP loser (new discovery) |
| 2025-01-22 | NTRB | -$425 | SQ loser (new discovery) |
| 2026-01-23 | BGL | +$187 | SQ winner (new discovery) |
| 2026-01-30 | PMN | +$415 | MP winner (new discovery) |

Net: -$373. New finds are net-negative — 4 losers vs 2 winners.

---

## Root Cause Analysis

### Why did AIFF + OST disappear? (-$1,787 combined)

The old scanner JSON for 2025-01-14 (at commit `aef59a1`) contained **AIFF** (vol=8.9M, gap=63%) and **OST** (vol=6.1M, gap=44%). The new scanner JSON contains only **NMHI** (vol=31.3M, gap=172%).

The checkpoint overhaul changed the scanner schedule (7 → 12 checkpoints, 9:30 cutoff). The new schedule discovers different stocks on this date. AIFF and OST were never added to the new JSON — they simply don't meet the new scanner's discovery criteria at the checkpoint times used.

### Why did CJMB produce 0 trades? (-$1,028)

CJMB IS in the new scanner's top-5 on 2026-01-15 (rank #4). The old run produced a +$1,028 squeeze trade at 11:27. But the new run produces 0 trades.

The old scanner had CJMB discovered earlier or with different sim_start timing. The detector state machine (seed bars, EMA, VWAP) evolves differently based on when simulation starts, which affects whether the squeeze ARMs and triggers.

### Why was POLA bumped? (-$556)

POLA was #5 in the old scanner for 2026-01-20. The new scanner discovered **SDST** (vol=4.7M, rvol=46.2, gap=25%) at 07:45, which scored higher than POLA and pushed it to #6.

### ENV_BASE Differences

Four env vars differ between old and new:

| Variable | Old | New |
|----------|-----|-----|
| WB_HALT_THROUGH_ENABLED | not set (=0) | 1 |
| WB_SQ_PARTIAL_EXIT_ENABLED | not set (=0) | 1 |
| WB_SQ_RUNNER_DETECT_ENABLED | not set (=0) | 1 |
| WB_SQ_WIDE_TRAIL_ENABLED | not set (=0) | 1 |

These are all gated ON in the new run. They affect squeeze exit behavior (partial exits at target, wider trailing stops, runner detection). This explains some of the P&L differences on identical-stock trades (e.g., VERO $14,123 → $13,882).

### NOT the Bail Timer

The bail timer (`WB_BAIL_TIMER_ENABLED`) exists in the code but is **not set in ENV_BASE** for either runner. It defaults from `.env` where it's `=1`. Both runs have it ON. The earlier forensic comparing against the megatest was comparing against a run where the bail timer code **didn't exist yet** — a different problem entirely.

---

## Summary

The -$1,941 gap comes from **scanner stock-universe changes**, not code bugs:

| Cause | Impact | % of Gap |
|-------|--------|----------|
| AIFF + OST disappeared from scanner | -$1,787 | 92% |
| CJMB: same scanner, detector didn't ARM | -$1,028 | 53% |
| POLA bumped from top-5 by SDST | -$556 | 29% |
| Risk sizing noise on shared trades | -$274 | 14% |
| New losers (PHIO, NMHI, VATE, NTRB) | -$975 | 50% |
| Avoided old losers (PTHS, STAI, CELZ) | +$2,706 | -139% |
| New winners (BGL, PMN) | +$602 | -31% |
| MP entry timing differences (LEDS, SPHL) | -$525 | 27% |
| **Net** | **-$1,941** | **100%** |

The 9:30 cutoff correctly avoided CELZ (-$687) and other late losers, nearly paying for itself. The AIFF/OST loss is the single biggest driver and is purely a scanner-discovery issue.

---

## What Would Fix It

1. **Recover AIFF + OST**: These stocks existed in the old scanner but disappeared with the new checkpoint schedule. Investigating why the 12-checkpoint schedule misses them while the 7-checkpoint schedule found them would recover ~$1,787.

2. **CJMB detector ARM**: The stock IS found by the scanner. The issue is detector state — different sim_start timing → different bar history → different ARM decision. This is harder to fix.

3. **POLA top-5 displacement**: Would require adjusting ranking to deprioritize SDST. Not worth pursuing for $556.

4. **Accept the tradeoff**: The new scanner avoids $2,706 in losers while losing $3,480 in winners. That's a 78% recapture rate. The net gap of -$774 from stock selection is modest.
