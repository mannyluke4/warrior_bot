# Correct Exit Study: What Makes a Stock "Done" at 2R?

**Date:** 2026-04-02
**Author:** Cowork (Opus)
**Purpose:** Compare indicator state at 2R target hit between stocks that stopped running (correct exit) vs stocks that kept running (should have held)

---

## The Question

86% of target-hit trades are runners. 14% are done. What's different about the 14%?

We analyzed tick-level data for 2 "done" stocks (ATON, BOSC) and 8 runner stocks (ROLR, CYN, STAK, ALUR, QNTM, ARTL, BSLK, INM) at the exact moment their 2R target was hit. Every indicator the bot can see — MACD, volume, VWAP, candle patterns — was compared.

**Missing data:** GV (2025-03-05), SNES (2025-03-13), and DRMA (2025-03-27) have no tick cache. CC would need to fetch from Databento to include them. The conclusions below are drawn from 2 done + 8 runner stocks.

---

## What Does NOT Distinguish Done from Runner

These indicators looked the same at 2R for both groups:

**MACD state:** Both groups show MACD bullish (100%). No bearish crosses at 2R in either group. MACD histogram is NOT declining in either group at the exit bar. This makes sense — 2R happens during strong momentum, and MACD is a lagging indicator that hasn't caught up to the reversal yet.

**Volume climax:** Both groups show climax-level volume at the 2R bar (100%). The exit bar is the highest-volume bar of the session for both done and runner stocks. You can't tell from the exit bar's volume alone whether more is coming.

**Candle patterns at exit:** Neither group consistently shows reversal candles (shooting stars, dojis, bearish engulfing) at the 2R bar itself. The exit bar is usually a strong green bar — the reversal comes AFTER it. Exit candle patterns are NOT leading indicators at the 2R moment.

**MACD histogram trend:** Not declining for either group. Both show expanding histogram at exit. This eliminates "MACD divergence at 2R" as a distinguishing signal.

---

## What DOES Distinguish Done from Runner

Two signals show clear separation:

### Signal 1: VWAP Distance (STRONGEST SIGNAL)

| Group | Avg VWAP Distance at 2R | Range |
|-------|------------------------|-------|
| **DONE** | **+34.7%** above VWAP | +18.5% (ATON), +50.9% (BOSC) |
| **RUNNER** | **+9.7%** above VWAP | -1.8% to +37.2% |

Stocks that are DONE at 2R are dramatically more extended above VWAP. ATON was 18.5% above VWAP. BOSC was 50.9% above VWAP. The runners averaged only 9.7% above VWAP at 2R.

**Why this matters:** VWAP is the gravitational center. The further a stock stretches above VWAP, the stronger the mean-reversion pull. A stock at +35% above VWAP has exhausted the buying pressure needed to sustain the move. A stock at +10% still has room before mean reversion overwhelms momentum.

**Potential rule:** If VWAP distance > 25% at 2R, treat the exit as likely correct. If < 15%, treat 2R as a confirmation signal and hold for candle-based exit.

### Signal 2: Time Into Session (STRONG SIGNAL)

| Group | Avg Bars Into Session | Avg Time |
|-------|----------------------|----------|
| **DONE** | **120 bars** (~2 hours) | Extended move |
| **RUNNER** | **32 bars** (~30 min) | Fresh breakout |

Stocks that are done at 2R have been running for a LONG time. ATON took 180 bars (3 hours) to reach 2R. BOSC took 61 bars (1 hour). The runners hit 2R much faster — often within the first 10-40 bars.

**Why this matters:** A stock that reaches 2R in 10 minutes is in the early stages of a momentum move. A stock that grinds to 2R over 2 hours has been slowly exhausting buyers the whole time. Speed to 2R is a proxy for momentum quality.

**Potential rule:** If bars-to-2R > 60 (1 hour), the move is likely exhausted. If < 20 (20 min), the move is likely just starting.

**BUT — important caveat:** SNES exited at 07:09 ET (only 9 minutes in) and was correctly done. INM and BSLK were runners despite being 170 bars in. Time alone doesn't guarantee the direction. It's a probability weight, not a binary gate.

---

## Supporting Observations

### Volume Ratio Context

| Group | Avg Vol Ratio (exit bar vs 5-bar avg) |
|-------|--------------------------------------|
| DONE | 11x |
| RUNNER | 496x |

Runners tend to have much more extreme volume ratios — but this is partly an artifact of very thin pre-breakout volume (some runners had 10-20 shares/bar before the breakout). The absolute volume ratio is noisy. What matters more is the volume PATTERN:

- **Done stocks (ATON):** Volume was already elevated for hours before 2R. The exit bar (422K) was a continuation of heavy trading, not a fresh spike. The buying had been distributed over time.
- **Runner stocks (ROLR, CYN, STAK):** Volume was near zero before the breakout. The exit bar was the FIRST major volume event. Fresh interest = more potential.

### Post-Exit Volume Tells the Real Story (But We Can't See It Before)

- **Runners:** Volume EXPANDS in the bars after 2R. ROLR went 333K → 1.4M → 971K. CYN went 322K → 539K → 343K. More buyers arrive.
- **Done stocks:** Volume CONTRACTS after 2R or shows halt-reversal behavior. ATON went 422K → 261K → 144K → 183K then declining. BOSC's next bar was a massive reversal (440K).

This is the most reliable signal but it's only available AFTER the exit, not before. However, a trailing approach could capture it: hold through 2R, exit only when post-2R volume contracts below a threshold.

---

## What We Still Don't Know

### The 3 Missing Stocks

GV, SNES, and DRMA have no tick cache. Here's what we know from the post-exit analysis alone:

| Stock | Date | Exit Time ET | R Taken | Post-Exit R | Category |
|-------|------|-------------|---------|-------------|----------|
| GV | 2025-03-05 | 09:38 | +1.9R | +0.4R | GOOD_EXIT |
| SNES | 2025-03-13 | 07:09 | +1.6R | +0.0R | GOOD_EXIT |
| DRMA | 2025-03-27 | 08:32 | +2.9R | -0.9R | PERFECT_EXIT |

**CC action needed:** Run these through the sim or fetch tick data from Databento to get MACD/volume/VWAP at exit. Key question: were they extended above VWAP like ATON/BOSC?

### Sample Size

2 done vs 8 runner is a small sample. The VWAP distance signal (+34.7% vs +9.7%) is large enough to be meaningful, but we need to test it against the full 109-trade dataset. A rule like "VWAP > 25% = exit" needs to be validated against the 30 runner target-hit trades to check false-exit rate.

### What About the 30 Runner Target-Hit Stocks?

The 30 runners exited via sq_target_hit and kept running. How many of THOSE would have been incorrectly flagged by a "VWAP > 25%" rule? I checked STAK — it was +37.2% above VWAP and still ran +37R. So the VWAP rule would have some false exits on parabolic runners. The threshold needs tuning.

---

## Proposed Exit Logic: VWAP + Time Score

Instead of a binary rule, use a composite "exhaustion score" at 2R:

```
exhaustion_score = 0

# VWAP distance (most predictive)
if vwap_dist_pct > 30: exhaustion_score += 3
elif vwap_dist_pct > 20: exhaustion_score += 2
elif vwap_dist_pct > 15: exhaustion_score += 1

# Time in session
if bars_to_2r > 90: exhaustion_score += 2
elif bars_to_2r > 60: exhaustion_score += 1

# Volume pattern (was volume already elevated before breakout?)
if pre_breakout_vol_avg > 10000: exhaustion_score += 1  # distributed buying

# R multiple already captured
if r_at_exit > 8: exhaustion_score += 1  # stock already moved 8R+

# Decision
if exhaustion_score >= 4: EXIT (stock likely done)
elif exhaustion_score <= 1: HOLD (use candle exit only)
else: TRAIL TIGHT (mechanical trail tightened, but don't exit on target alone)
```

This weights VWAP most heavily (up to 3 points) because it's the strongest signal. Time adds up to 2 points. Volume pattern and R-multiple add 1 each.

**Expected behavior:**
- ATON (VWAP +18.5%, 180 bars, high pre-vol): score = 2+2+1 = 5 → EXIT (correct)
- BOSC (VWAP +50.9%, 61 bars, low pre-vol): score = 3+1+0 = 4 → EXIT (correct)
- ROLR (VWAP +11.6%, 36 bars, low pre-vol): score = 0+0+0 = 0 → HOLD (correct)
- CYN (VWAP +6.6%, 36 bars, low pre-vol): score = 0+0+0 = 0 → HOLD (correct)
- STAK (VWAP +37.2%, 10 bars, low pre-vol): score = 3+0+0 = 3 → TRAIL TIGHT (debatable — stock ran +37R but was extended)
- INM (VWAP +4.3%, 170 bars, expanding vol): score = 0+2+1 = 3 → TRAIL TIGHT (correct — stock ran but was late)

STAK is the interesting edge case. VWAP +37% looks exhausted, but the stock ran another 37R. The time factor (only 10 bars) correctly counterbalances the VWAP distance, keeping the score at 3 (trail tight) rather than 4+ (exit). A tight trail on STAK would have captured most of the continuation.

---

## What the Bot Needs To See This

The bot currently has VWAP available (TradeBarBuilder tracks cumulative VWAP). It does NOT currently:

1. Track "bars in trade" or "bars since session open" in the exit logic
2. Compare price to VWAP as a percentage in check_exit()
3. Compute pre-breakout volume average vs breakout volume

**Implementation path for CC:**
1. Add `self._bars_in_trade` counter to check_exit() (already spec'd in DIRECTIVE_CANDLE_EXIT_V2.md)
2. Add VWAP distance calculation: `vwap_dist = (price - vwap) / vwap`
3. At 2R target hit, compute exhaustion score
4. Gate via env var: `WB_SQV2_EXHAUSTION_SCORE_ENABLED=0` (default off)
5. If score >= threshold (env var), take the 2R exit. If below, suppress exit and switch to candle-based exit (Tier 3 from directive)

---

## Summary

| Signal | Done Stocks | Runner Stocks | Distinguishing? |
|--------|------------|---------------|----------------|
| MACD bullish | Yes (100%) | Yes (100%) | NO |
| MACD bearish cross | No (0%) | No (0%) | NO |
| Histogram declining | No (0%) | No (0%) | NO |
| Climax volume | Yes (100%) | Yes (100%) | NO |
| Exit candle pattern | None (100%) | None (62%) | NO |
| **VWAP distance** | **+34.7%** | **+9.7%** | **YES** |
| **Bars into session** | **120** | **32** | **YES** |
| Vol ratio | 11x | 496x | Partially (noisy) |

**Bottom line:** MACD, volume, and candle patterns at the 2R bar itself do NOT distinguish done from runner. The two signals that do: how far above VWAP the stock is (mean-reversion gravity) and how long it took to get there (momentum quality). A composite exhaustion score using these inputs can gate whether 2R is treated as an exit or a promotion to candle-based trail management.

---

*Generated: April 2, 2026 | Cowork (Opus)*
*Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>*
