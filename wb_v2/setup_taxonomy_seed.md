# WB v2 — Setup Taxonomy (Seed)

**Date:** 2026-05-18
**Stage:** 0 (research only — discussion seed, not final taxonomy)
**Author:** Cowork (per `DIRECTIVE_2026-05-18_WB_V2_STAGE_0.md`)
**Status:** Foundation for Stage 1 — Manny edits or replaces

---

## What this document is (and is not)

This is a **first-pass taxonomy** for WB v2 setups, derived directly from Manny's verbatim description. It exists for two reasons:

1. To give Stage 1 a starting vocabulary so trade-intake entries can be tagged consistently.
2. To make the taxonomy editable. Anything in this document is up for revision by Manny. The act of writing it is more important than the specifics — squeeze v1's first taxonomy got rewritten three times before it stabilized.

This is **not** a specification of which setups WB v2 will trade. That decision lives in Stage 1's backtest output. This is just the vocabulary we'll use to talk about candidate setups while we're discovering which ones work.

Same posture as squeeze v1's first taxonomy doc (`STRATEGY_2_SQUEEZE_DESIGN.md`) — a starting point, not a contract.

---

## Source material

Manny, verbatim (2026-05-18, 1:33 AM MDT):

> "I simply just watched the chart, waited for the price to reach a level of support, and added when MACD was green near the bottom, and snipped profits when it was about halfway back up the wave… I also short the stock when it looks like the exact same setup but opposite. Nearing resistance, MACD crossing to red."

Two named setups, perfect mirror.

---

## Top-level taxonomy: two setups, mirrored

### Wave-Reversal Long (WRL)

| Field | Value |
|---|---|
| **Direction** | Long |
| **Trigger price geometry** | Price touches or briefly probes a support level |
| **Confirmation indicator** | MACD turning green (histogram or line/signal crossover) near a local wave low |
| **Wave context** | Near the bottom of a fluctuation, not mid-channel |
| **Universe** | Top-N "most active stocks of the day" by tick rate / volume / RVOL / range |
| **Timeframe** | 1m primary, 5m secondary candidate |
| **Exit philosophy** | "Halfway back up the wave" — reuse squeeze exit stack to operationalize |
| **Manny's quote** | "Waited for the price to reach a level of support, and added when MACD was green near the bottom" |

### Wave-Reversal Short (WRS)

| Field | Value |
|---|---|
| **Direction** | Short |
| **Trigger price geometry** | Price touches or briefly probes a resistance level |
| **Confirmation indicator** | MACD turning red (histogram or line/signal crossover) near a local wave high |
| **Wave context** | Near the top of a fluctuation, not mid-channel |
| **Universe** | Same as WRL — top-N most-active |
| **Timeframe** | 1m primary, 5m secondary candidate |
| **Exit philosophy** | Mirror of WRL — "halfway back down the wave," reuse squeeze exits |
| **Manny's quote** | "Short the stock when it looks like the exact same setup but opposite. Nearing resistance, MACD crossing to red" |

WRL and WRS are intentionally identical except for direction. If Stage 1 backtests reveal asymmetry (e.g. longs work but shorts don't on certain universe slices), that asymmetry becomes part of the spec. For now, the symmetry is the default.

---

## Sub-type candidates (to cluster from Stage 1+ trade log)

These are *axes* along which WRL and WRS may further split. Manny doesn't pre-commit to any of these; the trade-intake template (Deliverable 4) captures the free-text data, and Stage 1 clusters the taxonomy from what's there.

Same approach as squeeze v1 — we started with one squeeze type, then per-stock trade logs revealed sub-categories (cascading squeezes, PM-runner squeezes, post-squeeze continuation) that became their own detector modules.

### Axis 1: Level type

| Sub-type | Level basis | Why it might matter |
|---|---|---|
| **WRL-PDH / WRS-PDH** | Prior-day high (acting as support after break, or resistance pre-break) | Well-defined, persistent across sessions |
| **WRL-PDL / WRS-PDL** | Prior-day low (mirror) | Same persistence argument |
| **WRL-VWAP / WRS-VWAP** | Intraday VWAP reclaim/reject | Magnet level; high-volume stocks respect it |
| **WRL-AVWAP / WRS-AVWAP** | Anchored VWAP from session open or from a key event | Persistent through the session |
| **WRL-Pivot / WRS-Pivot** | Recent swing high/low (n-bar fractal on 1m) | Manny's "near the bottom" / "near the top" most literally maps here |
| **WRL-Round / WRS-Round** | Whole-dollar / half-dollar magnet levels | Squeeze v1 confirmed these matter for the same universe |
| **WRL-VolNode / WRS-VolNode** | Volume profile POC / VAH / VAL | Already partially built in framework Phase 2 |

Each level type is a separate hypothesis. Stage 1 backtests sweep them; the ones that walk-forward survive.

### Axis 2: Wave depth

| Sub-type | Description | Why it might matter |
|---|---|---|
| **Deep pullback** | Price has retraced ≥ X% of the prior wave's range | Higher R:R but lower base rate |
| **Shallow chop** | Price oscillating in a tight range | Tighter stops, faster fills, lower per-trade P&L |
| **Failed-breakout reversal** | Price broke out, failed, reversed back through the level | Highest-conviction WRS candidate per Manny's pattern recognition |

"Halfway back up the wave" only makes sense if "the wave" is defined. Wave-depth tagging in the trade log is how we'll get there.

### Axis 3: Time of day

| Sub-type | Window (ET) | Why it might matter |
|---|---|---|
| **Pre-market session** | 07:00 – 09:30 | Squeeze v1's golden hour (08:00–08:30) is here. Fluctuation pattern may differ — thinner book, wider spreads. |
| **Open hour** | 09:30 – 10:30 | Highest volume, sharpest fluctuations |
| **Midday** | 10:30 – 14:00 | Lower volume, chop dominates; could be where WRS shines |
| **Power hour** | 14:00 – 15:55 | Reversal magnet; force-flat at 15:55 ET (already wired) |

Squeeze v1's time-of-day signal was strong (08:00–08:30 was 71% WR, +$26,875; post-09:30 was negative EV). WB v2 may have a completely different time-of-day profile because the trigger condition is different.

### Axis 4: MACD variant

| Sub-type | MACD trigger | Why it might matter |
|---|---|---|
| **Histogram zero-cross** | Histogram crosses from negative to positive (long) / positive to negative (short) | Cleanest "MACD green/red" signal |
| **Line/signal cross** | MACD line crosses its signal line | Sometimes leads zero-cross by 1-2 bars |
| **Histogram bottoming** | Histogram bars decreasing in magnitude while still negative, then up-tick | Manny's "near the bottom" most literally maps here |
| **Standard params (12/26/9)** | Default | Most-watched, may be self-fulfilling |
| **Fast params (5/13/5)** | Faster | 1m timeframe may need faster MACD |

Manny didn't specify the variant. Stage 1 enumerates and tests.

---

## How this taxonomy interacts with the trade intake template

The trade-intake CSV (Deliverable 4) intentionally uses **free-text** fields for `level_type`, `macd_state`, and `exit_reason`. Manny types what he sees: *"PDH from yesterday"*, *"VWAP reclaim around 9:42"*, *"histogram just barely flipped green"*.

Stage 1 then **clusters** the free-text entries into the axis-buckets above (or new buckets that emerge from the data). The taxonomy is data-driven, not pre-committed.

This is exactly how the squeeze v1 sub-types emerged. Per-stock trade logs had free-text "what Ross did" notes; clustering those across 100+ stocks produced the cascading-squeeze and post-squeeze-continuation sub-types.

---

## What's intentionally absent

A few things this taxonomy does **not** include, by design:

- **Position sizing tiers.** Not a setup-taxonomy concern. Lives in the spec, not the taxonomy.
- **Exit sub-types.** WB v2 reuses the squeeze exit stack. Exit primitives are documented in Deliverable 6.
- **Hybrid setups.** "WRL + squeeze breakout in same name" or "WRS + post-squeeze continuation reversal" are *possible* but not in scope for Stage 1. If Stage 1 surfaces a winning hybrid candidate, it gets a separate directive.
- **Watchlist-driven entries.** WB v2's universe is dynamic (top-N most-active), not a static watchlist. Setups don't have a "watchlist tier" axis.

---

## How to revise this document

This is a discussion seed. Manny revises freely. Two principles for revisions:

1. **Stay grounded in the verbatim.** Every named sub-type should trace back to a phrase Manny used or a pattern he's observed. New sub-types added by Cowork or CC need a one-sentence justification rooted in observation, not speculation.
2. **Don't pre-commit beyond what the data supports.** A sub-type is a *hypothesis*, not a *commitment*. Stage 1 backtests are what decide which hypotheses get bot code.

Same revision posture as squeeze v1's design docs (`SQUEEZE_V2_PLAN.md`, `STRATEGY_2_SQUEEZE_DESIGN.md`) — write-now, revise-with-data.

---

## Reminder, verbatim from Manny

> "Ride the fluctuation."

Two setups in this taxonomy, both serving that single goal: WRL rides the up-side of the fluctuation back toward the middle, WRS rides the down-side back toward the middle. Everything sub-type-level just sharpens the entry timing.
