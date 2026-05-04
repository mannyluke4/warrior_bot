# DIRECTIVE: Wave Breakout — Stage 2 (Lean Into the Bot's Edge)

**Date:** May 4, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code) / Cowork  
**Priority:** P1 — Census variants first, then build  
**Branch:** `v2-ibkr-migration`  
**Predecessor:** `DIRECTIVE_WAVE_SCALP_STAGE1_RESEARCH.md` and `cowork_reports/2026-05-04_wave_scalp_research.md`

---

## Context & Reframe

Stage 1 research showed the wave-detection algorithm correctly identifies real, frequent oscillations — 15,648 waves across 84 days, 547 setups scoring ≥7. The hypothetical strategy produced 40.4% WR and 2.15 PF (ex-FIGG bug).

The original directive failed the WR ≥50% gate. **We're explicitly NOT trying to fix that.**

Manny's hand-trading style is high-WR small-wins. The bot's mechanical detection is finding a fundamentally different edge: **rare big winners on directional waves, with controlled losses on the rest.** This is a swing/breakout return profile, not a scalp profile. Renamed accordingly: **Wave Breakout (WB).**

The thesis for Stage 2: lean INTO what the bot is uniquely good at, rather than tuning it to mimic discretionary scalping it can't replicate anyway.

## What the Bot Is Uniquely Good At

| Capability | Human can't | Bot does it natively |
|---|---|---|
| Watch 174+ symbols simultaneously | Yes | Already wired via watchlist |
| Hold winners through extended consolidation without closing early | Yes (emotional drift) | Mechanical, no fatigue |
| Capture fat-tail moves (>5R, >10R) | Yes (profit-taking instinct) | Will hold by rule |
| Pyramid into confirmed winners with discipline | Yes (averaging into losers reflex) | Rule-based, no FOMO |
| Manage 2-3 concurrent positions on different symbols | Yes (cognitive load) | Trivial for software |
| Stick to mechanical stops at exactly -1R | Yes ("just one more minute") | No argument |

Stage 1 data confirms: **8 trades >10R and 26 trades 5-10R** (1.5% and 4.8% of trades respectively) likely produce ≥70% of total P&L. This is fat-tail dependent. The strategy's job is to:

1. Take many small controlled losses (already doing this — 219 stops at -1R)
2. Let winners run far enough to capture the fat tail (NOT yet doing this — current target = recent wave high caps too soon)
3. Concentrate exposure on the cleanest setups (NOT yet doing this — score-7 and score-10 trades sized identically)

---

## Stage 2 Goals

1. **Fix the FIGG position-sizing bug** (mandatory, non-negotiable)
2. **Test variants that widen R/R asymmetry** — wider targets, longer time stops, no targets at all
3. **Test pyramid sizing** on confirmed +1R trades
4. **Test concurrent positions** across multiple symbols
5. **Test score-weighted sizing** to concentrate capital on best setups
6. **Validate against Manny's manual review** of 5 known-good wave days

Do NOT skip steps. Do NOT combine variants until each is individually evaluated.

---

## Required Variants (Run Census On Each)

For each variant below, re-run the YTD census (`scripts/wave_census.py` extended) and produce a one-page comparison vs the 547-trade ex-FIGG baseline. Save outputs to `wave_research/stage2_variants/<variant>/`.

### Variant 0: Position-Sizer Hardening (Foundation)

**This is mandatory and must be applied to ALL subsequent variants.** Not a strategy decision — an input validation fix.

```python
# In wave_census.simulate_trade():
ENTRY_PRICE = entry  # the actual entry price

# Hardening
MIN_RISK_PER_SHARE = max(0.01, entry * 0.001)  # 10 bps minimum
MAX_NOTIONAL = 50_000  # matches main bot's WB_MAX_NOTIONAL
risk_per_share = max(entry - stop, MIN_RISK_PER_SHARE)
shares_by_risk = int(1_000 / risk_per_share)
shares_by_notional = int(MAX_NOTIONAL / entry)
shares = min(shares_by_risk, shares_by_notional)

if shares == 0:
    skip_trade(reason="position_size_zero")
```

This eliminates FIGG-style degenerate positions at source. Re-run baseline with this fix; that's the new "Variant 0 baseline" everything else compares to.

### Variant 1: Wide Target

Replace target = `max(recent_up_wave_high, entry × 1.015)` with `target = entry × 1.05` (5% target, much wider than typical wave high).

Hypothesis: gives fat-tail winners room to run. Will likely INCREASE time-stops and stop-hits, but the few that hit target will be much larger. PF should improve at the cost of WR.

Output: trade count, WR, PF, P&L, R-distribution, %target_hit / %stop_hit / %time_stop.

### Variant 2: No Target, Trailing Stop Only

Remove the fixed target entirely. Replace with a trailing stop that activates at +1R (breakeven) and trails at 0.5R below the running peak.

Hypothesis: this is what gives the fat tail room to fully run. Trades only exit when they actually reverse, not at an arbitrary price level. Should produce the highest fat-tail capture but also the most trades that round-trip from +0.5R to breakeven.

Logic:
```python
peak = entry
trailing_active = False
for tick in ticks_after_entry:
    peak = max(peak, tick.price)
    if not trailing_active and (peak - entry) >= R:
        trailing_active = True
    if trailing_active:
        trail_stop = peak - (0.5 * R)
        if tick.price <= trail_stop:
            exit(reason="trailing_stop")
            break
    elif tick.price <= entry - R:
        exit(reason="stop_hit")
        break
```

Run with: no time stop, session_end as ultimate cap.

### Variant 3: Extended Time Stop (30 min instead of 10 min)

Same exits as Variant 0 baseline, but time_stop = 30 min.

Hypothesis: from Stage 1 data, time-stopped trades are 50.7% WR with avg +$1,049. Many would resolve as targets if given more time. Extending the cap converts time-stops into target/stop resolutions.

Expected: WR climbs (more conversions to target_hit), trade overlap reduces (longer holds = fewer concurrent slots), avg trade duration grows.

### Variant 4: No Time Stop At All

Same exits as Variant 0 baseline, but no time cap. Trade exits only on target_hit, stop_hit, or session_end.

Compare against Variant 3 to see whether 30 min vs unlimited makes a meaningful difference.

### Variant 5: Pyramid On Confirmed Winners

When a trade hits +1R, add a second entry at the current price with the same dollar risk ($1,000). Both legs share the same trailing stop or target.

Hypothesis: doubles exposure on the trades most likely to be fat-tail winners, since reaching +1R is itself a positive signal. Captures more upside on the 13% of trades that go >2R while not affecting the 53% that stop out at -1R.

Risk caveat: pyramiding doubles capital exposure. Make sure position-sizer cap (`MAX_NOTIONAL = 50K`) applies to the COMBINED position.

### Variant 6: Score-Weighted Sizing

Allocate risk based on signal quality:

| Score | Risk per trade |
|---|---:|
| 7 | $500 (0.5R) |
| 8 | $1,000 (1R, default) |
| 9 | $1,500 (1.5R) |
| 10 | $2,000 (2R) |

Hypothesis: concentrates capital on cleaner setups while still firing on marginal ones. From Stage 1 score-threshold sensitivity, score-9 had the best PF (2.77) — sizing up there should compound that edge.

### Variant 7: Concurrent Positions (≤3 simultaneous)

Currently the simulator allows only one open position per (sym, date) cell. Lift that cap: allow up to 3 concurrent open positions across DIFFERENT symbols.

Hypothesis: with 7.4 setups per day spread across 174 symbols, many simultaneous setups exist that single-position mode forces us to skip. Letting the bot hold 2-3 at once captures more of the daily opportunity set.

Implementation: track open positions by symbol, refuse a new entry if (a) already hold a position in that exact symbol, OR (b) already at the 3-position cap.

### Variant 8: Combined "Best Of" 

After running variants 1-7, combine the best 3-4 mechanics into a single configuration. Example combination (educated guess; replace with whatever the data argues for):

- Variant 0 sizer (mandatory)
- Variant 2 (trailing stop, no fixed target)
- Variant 3 (30-min time stop as failsafe)
- Variant 6 (score-weighted sizing)
- Variant 7 (3 concurrent positions)

Run the full census on this combined config. This is the candidate for Stage 3 (build).

---

## Manual Validation (Manny + Cowork)

In parallel with the variant census runs, validate the wave detector against discretionary trading:

1. Manny picks **5 of his best wave-scalp days from his TradingView paper P&L log** (April 20 – May 1).
2. For each (date, symbol) pair, CC filters `wave_research/ytd_waves_detail.csv` to those rows.
3. Manny reviews the algorithm's tagged waves and answers:
   - Did the algorithm flag the swings I actually traded? (true positives)
   - Did the algorithm tag swings I would NOT have traded? (false positives)
   - Did the algorithm miss swings I did trade? (false negatives)
4. CC writes findings to `cowork_reports/2026-05-XX_wave_manual_validation.md`.

If the detector is missing >30% of Manny's actual trades or flagging >40% of swings he wouldn't take, the detection algorithm needs work BEFORE Stage 3. The wave shape parameters (0.75% min magnitude, 3-15 min duration, 0.5% reversal confirm) may need tuning.

---

## Acceptance Gate for Stage 3 (Build)

Combined "Best Of" variant must show ALL of:

| # | Criterion | Threshold |
|---:|---|:---:|
| 1 | Position sizer correctly caps shares (no FIGG-style degen positions) | All trades ≤ MAX_NOTIONAL |
| 2 | Trade count over 84 days | ≥ 200 |
| 3 | Profit factor | ≥ 2.5 (vs Stage 1's 2.15) |
| 4 | Total P&L (ex any single-trade outliers >10% of total) | ≥ +$300K |
| 5 | Top-5 days share of P&L | ≤ 65% (somewhat concentrated is OK for fat-tail strategy, but not pathological) |
| 6 | Manual validation TP rate | ≥ 70% (algorithm catches most of Manny's real trades) |
| 7 | Manual validation FP rate | ≤ 50% (more than half of flagged setups should be ones Manny would consider) |

WR is **explicitly not gated**. A 35-45% WR with strong PF is the target profile.

---

## What NOT to Do

- ❌ Do NOT modify any existing strategy files (`squeeze_detector.py`, `bot_v3_hybrid.py`, etc.)
- ❌ Do NOT skip Variant 0 sizer hardening — it underpins every other variant
- ❌ Do NOT combine variants until each individual variant has been evaluated
- ❌ Do NOT optimize against a single date or symbol — full 84-day census or it doesn't count
- ❌ Do NOT proceed to Stage 3 (build) without Manny's manual validation passing
- ❌ Do NOT loosen the wave detection parameters (0.75% / 3-15 min / 0.5% reversal) without showing it improves manual validation

---

## Deliverables

1. `wave_research/stage2_variants/<variant_name>/` directory for each of variants 1-8, each containing:
   - Updated `ytd_hypothetical_trades.csv` for that variant
   - `summary.json` with trade count, WR, PF, P&L, R-distribution, exit-reason breakdown
2. `cowork_reports/2026-05-XX_wave_breakout_stage2_results.md` — comparison table of all 8 variants vs baseline, with recommended combined config
3. `cowork_reports/2026-05-XX_wave_manual_validation.md` — manual validation findings
4. Pull request / commit with the chosen combined config flagged for Stage 3

---

## Stage 3 Preview (NOT for now)

Once Stage 2 passes the gate, Stage 3 will be:
- New file `wave_breakout_detector.py` (parallel to `squeeze_detector.py`)
- Strategy module integrated into `bot_v3_hybrid.py` behind a feature flag (`WB_WAVE_BREAKOUT_ENABLED=0` default)
- Lives entirely in paper trading for at least 5 trading days alongside live squeeze
- Real money only after paper validation matches backtest within 20%

That's all Stage 3. Do not pre-build any of it during Stage 2.

---

*The bot's job isn't to be Manny. It's to be the patient, mechanical, fat-tail-capturing version of Manny that can patrol 174 symbols simultaneously and never close a winner too early.*
