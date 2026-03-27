# MP Strategy Analysis — Living Document

**Created:** 2026-03-21
**Last updated:** 2026-03-21
**Author:** Cowork (Opus)
**Status:** Active — baseline established, pending Ross recap cross-reference

---

## Corrected Megatest v2 Results (Baseline)

**Source:** MP-only v2 corrected megatest
**Period:** Jan 2, 2025 – Mar 20, 2026 (297 trading days)
**Fixes applied:** corrected sim_start, overlapping trades fix, notional release fix
**All patterns below come from this specific test run.**

### Overall Performance

| Metric | Value |
|--------|-------|
| Starting equity | $30,000 |
| Final equity | $19,879 |
| Net P&L | -$10,121 |
| Total trades | 154 |
| Win rate | 26% (40W / 114L) |
| Profit factor | 0.61 |
| Avg win | $403 |
| Avg loss | $230 |
| Win/loss ratio | 1.75:1 |

Config A (gate=8) and Config B (no gate) produced nearly identical results — **score gating does not help MP**.

At a 26% win rate, the strategy needs roughly a 3:1 avg win/loss ratio to break even. The current 1.75:1 ratio falls well short.

---

### 2025 vs 2026 Split

| Period | P&L | Trades | Win Rate | Profit Factor |
|--------|-----|--------|----------|---------------|
| 2025 | -$16,191 | 128 | 23% | 0.47 |
| 2026 | +$6,070 | 26 | 42% | 3.12 |

**2025:** Consistently negative every month except May (+$498). The strategy bled steadily all year.

**2026:** Much better on the surface, but VERO (+$6,523) accounts for 40% of all 2026 winning P&L. Without VERO, 2026 is roughly -$453 — still marginal. The 2026 improvement tracks universe-wide sentiment (January hot, February cold for all day traders), not a structural MP improvement.

---

### Monthly P&L (Config A)

| Month | P&L |
|-------|-----|
| 2025-01 | -$3,947 |
| 2025-02 | -$471 |
| 2025-03 | -$4,156 |
| 2025-04 | -$1,110 |
| 2025-05 | +$498 |
| 2025-06 | -$2,503 |
| 2025-07 | -$1,043 |
| 2025-08 | -$590 |
| 2025-09 | -$324 |
| 2025-10 | -$632 |
| 2025-11 | -$486 |
| 2025-12 | -$1,427 |
| 2026-01 | +$6,057 |
| 2026-02 | -$456 |
| 2026-03 | +$469 |

---

### Time of Day

| Hour | Net P&L | Notes |
|------|---------|-------|
| 7:xx AM | +$392 (40 trades, avg +$10) | **Only profitable hour** |
| 8:xx AM | Negative | |
| 9:xx AM | Negative | |
| 10:xx AM | Negative | |
| 11:xx AM | Negative | |

**Implication:** MP should have a hard cutoff or reduced sizing after the first hour.

---

### Day of Week

| Day | Net P&L | Notes |
|-----|---------|-------|
| Monday | — | |
| Tuesday | -$4,416 | Worst |
| Wednesday | — | |
| Thursday | -$5,058 | Worst |
| Friday | +$3,388 | **Only profitable day** |

Interesting signal. Needs more investigation with Ross recaps to determine if this is structural or noise.

---

### Streaks

| Metric | Value |
|--------|-------|
| Max consecutive wins | 4 |
| Max consecutive losses | 18 |

The 18-loss streak represents a brutal grinding drawdown. The strategy depends on rare big winners to offset long losing streaks.

---

### Activity

| Metric | Value |
|--------|-------|
| Days with any MP trade | 116 of 297 (39%) |
| Days with zero MP signals | 181 |
| Days with multiple trades | 34 (mixed results) |

---

### Top Winners

| Symbol | P&L |
|--------|-----|
| VERO | +$6,523 |
| AIHS | +$1,004 |
| KTTA | +$806 |
| UUU | +$711 |
| MXC | +$612 |
| KUST | +$474 |
| ARTL | +$447 |
| WAFU | +$438 |
| KPLT | +$422 |
| EDBL | +$417 |

### Top Losers

| Symbol | P&L |
|--------|-----|
| SXTP | -$1,046 |
| SOPA | -$662 |
| PTHS | -$646 |
| STAI | -$639 |
| NTRB | -$629 |
| NCEL | -$605 |
| CYCN | -$592 |
| ATON | -$549 |
| GV | -$548 |
| SNOA | -$548 |

---

## Core Diagnosis

**The fundamental problem:** The avg win/loss ratio (1.75:1) is insufficient for the win rate (26%). The strategy needs either a higher win rate or bigger winners to be viable.

**Behavioral issues identified:**

1. **MP exits winners too early** — not letting winning trades run far enough relative to R
2. **MP lets losers run too long** — losses accumulate beyond where they should be cut
3. **Heavy outlier dependency** — profitability hinges on VERO-type trades which are expected in hot markets but cannot be relied upon
4. **Ross recap comparison will reveal** whether the gap is in entry timing, scaling, exit management, or setup selection

---

## Comparison with Pre-Run Estimate

The corrected estimate (see `mp_corrected_estimate.md`) predicted final equity between $33,673 (conservative) and $43,729 (optimistic). The actual result of $19,879 came in significantly below even the conservative estimate. Key differences:

- The estimate assumed VERO at +$17,505 (from the old hardcoded-start backtest); actual VERO was +$6,523 — much smaller due to dynamic sizing at lower equity
- The estimate assumed removing suspect trades would help; many losers that were "suspect" were replaced by different losers in the corrected run
- The state-affected trades did not improve as hoped

---

## A+ Setup Criteria (MP Strategy)

**Status:** Seed data from v2 megatest below. **Needs significant expansion from Ross recap analysis.**

This section defines what makes a top-tier, highest-conviction micro pullback setup. When a trade matches these criteria, the conviction sizing model (see `MASTER_TODO.md` — Conviction Sizing) should scale risk up from the 2.5% base toward 5-7%.

### What We Know So Far (from v2 megatest data)

**The ideal MP trade looks like VERO:** A massive gap-up runner with clean impulse that pulls back to support and gives a textbook micro pullback entry. VERO produced +$6,523 — more than the next 9 winners combined (+$5,331). The strategy is structurally dependent on catching these outlier runners.

**Time of day is the strongest filter:**
- 7:xx AM entries are the **only profitable time window** (+$392 across 40 trades, avg +$10/trade)
- Every other hour is net negative
- An A+ MP trade almost certainly happens in the first hour of premarket action

**Top 10 winner characteristics (preliminary — needs deeper cataloging):**
- VERO (+$6,523): Massive gap, clean impulse, high RVOL, strong float characteristics
- AIHS (+$1,004), KTTA (+$806), UUU (+$711), MXC (+$612): Need to pull individual trade details from megatest logs to catalog gap %, float, RVOL, entry time, pattern shape
- Common threads (hypothesis): Big premarket gap (likely >20%), clean first impulse leg, pullback holds above VWAP, re-entry on first sign of continuation

**Negative signals (what makes a setup NOT A+):**
- Entry after 8:00 AM — net negative across the dataset
- Tuesday and Thursday — net negative days (-$4,416 and -$5,058 respectively)
- Thin stocks with low session volume — see min liquidity filter work in MASTER_TODO
- Second or third trade on same symbol after a loss — no-reentry rule already captures this

### TBD — Needs Ross Recap Analysis

The following questions need to be answered by cross-referencing Ross's recap videos with our data:

- **What does Ross look for when he goes heavy?** Track his position sizing relative to normal across 10+ recaps. Identify the signals that correlate with large size.
- **Gap % threshold for A+ conviction?** Is there a gap % above which Ross consistently sizes up?
- **Float / share structure?** Does Ross treat low-float runners differently from mid-float?
- **Catalyst quality?** Does the type of catalyst (FDA, earnings, compliance, PR) affect conviction?
- **Pattern clarity?** Does the "cleanness" of the pullback pattern correlate with Ross's sizing?
- **Prior day runner history?** Does a stock being a multi-day runner change conviction?
- **RVOL threshold for A+?** What relative volume level separates A+ from standard setups?

*This section will be substantially expanded as Ross recap comparisons are completed. Each recap should explicitly tag trades as A+ / B / C quality with reasoning.*

---

## Next Steps (Pending)

1. **Cross-reference with Ross recaps** — Identify specific behavioral gaps (entry timing, scaling, exit management, setup selection)
2. **Compare with SQ-only and MP+SQ v2 results** — Determine interaction effects between strategies
3. **Investigate time-of-day filter** — Test whether restricting to 7:xx AM only improves results
4. **Investigate day-of-week filter** — Test whether avoiding Tuesday/Thursday improves results

---

## Bottom Line

MP needs significant work. These corrected megatest v2 findings establish the baseline for measuring improvement. The strategy is net negative with a structural dependence on rare outlier wins. Any improvement effort should focus on the win/loss ratio (exits) and the time-of-day signal before adding complexity.

---

*Living document — will be updated as new analysis is completed.*
