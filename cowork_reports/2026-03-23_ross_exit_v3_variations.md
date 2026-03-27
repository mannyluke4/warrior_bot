# Ross Exit V3: Price-Level Partials + CUC Refinement

**Created:** 2026-03-23
**Context:** YTD backtest showed V2 -$10,799 vs baseline. Two root causes identified: (1) CUC fires too aggressively (+$129 avg across 9 trades), (2) no proactive profit-taking at price levels where sellers congregate. This analysis maps out variations to fix both.

---

## The Two Problems (Separated)

### Problem 1: CUC Is the Weakest Link

CUC (Candle Under Candle) fires 9 times in the YTD for +$1,163 total (+$129 avg). Breakdown:

| Trade | Entry | Exit | Exit R | P&L | What Happened |
|-------|-------|------|--------|-----|---------------|
| SLGB | $3.04 | $3.53 | +3.5R | +$1,914 | CUC at $3.53; baseline held to $4.00 (+$3,690) |
| POLA | $2.90 | $3.11 | +1.5R | +$804 | CUC at $3.11; baseline trailed at $2.94 (+$165) — CUC WIN |
| ROLR | $12.24 | $13.38 | +0.3R | +$229 | CUC barely positive on a 3.58R-wide stop |
| SER | $2.22 | $2.26 | +0.3R | +$188 | Tiny win, baseline trailed to $2.30 (+$462) |
| IOTR | $8.62 | $8.31 | -0.6R | -$737 | CUC caught a loser — but baseline's BE caught it at $8.45 (-$443), so CUC was WORSE |
| MOVE | $19.92 | $19.36 | -0.7R | -$806 | CUC on a loser. Baseline BE at $19.49 (-$661) — CUC was WORSE |
| RUBI | $3.15 | $3.11 | -0.2R | -$105 | Small loss |
| CDIO | $3.27 | $3.18 | -0.6R | -$312 | Baseline BE at $3.17 (-$368) — CUC slightly better |
| ANNA | $5.04 | $5.02 | -0.1R | -$12 | Scratch |

**CUC wins vs baseline: 2 trades (POLA +$639, CDIO +$56)**
**CUC loses vs baseline: 5 trades (SLGB -$1,776, IOTR -$294, MOVE -$145, SER -$274, ANNA +$36)**
**CUC neutral: 2 trades**

**Net CUC impact vs baseline: approximately -$1,800.** CUC is a net drag on the strategy.

The core issue: CUC requires only ≥2 consecutive higher-highs before the lower-low fires. On small-cap stocks, 2 green bars happen constantly during consolidation. CUC catches pauses, not reversals.

### Problem 2: No Proactive Profit-Taking

Ross takes partials at whole-dollar resistance. The bot does nothing proactively — it waits for a bearish candle to form. On stocks that consolidate without printing a clean signal, the position just sits there until CUC eventually fires at a worse price.

Price level analysis for key V2 trades:

| Trade | Entry | First Level | Exit | Reached Level? |
|-------|-------|-------------|------|----------------|
| VERO | $3.58 | $4.00 | $5.66 (SS) | YES — blew through $4, $5 |
| SLGB | $3.04 | $3.50 | $3.53 (CUC) | YES — CUC fired right at it |
| BATL | $5.04 | $5.50 | $6.15 (doji) | YES — blew through to $6+ |
| CJMB | $4.68 | $5.00 | $5.13 (SS) | YES |
| ARTL | $7.62 | $8.00 | $8.00 (doji) | YES — doji exactly at $8 |
| MXC | $15.82 | $16.00 | $16.00 (SS) | YES — SS exactly at $16 |
| POLA | $2.90 | $3.00 | $3.11 (CUC) | YES |
| ACON | $8.04 | $8.50 | $7.90 (stop) | NO — reversed before any level |

**Key observation:** The candle signals already tend to fire near price levels. MXC shooting star at exactly $16.00. ARTL doji partial at exactly $8.00. SLGB CUC at $3.53 (near $3.50 half-dollar). The signals are picking up the resistance, but CUC fires too early in the consolidation at those levels rather than waiting for a confirmed reversal.

---

## Variation Design

Two independent axes: **CUC refinement** and **partial system**. Test in combinations.

### CUC Refinements

**C0 — Current (≥2 HH, no min bars, no min R)**
Baseline for comparison. 9 fires, +$1,163, +$129 avg.

**C1 — Tighten to ≥3 Consecutive Higher-Highs**
Requires 3+ green bars making progressive new highs before a lower-low triggers CUC. This filters out 2-bar consolidation patterns that aren't true reversals. The move must have real momentum before CUC can declare it "over."

- SLGB: did the bar at $3.53 follow 3+ higher-high bars? If the stock ran $3.04 → $3.50+ in a clean impulse, likely yes. But if it was choppy (up, down, up, down, up, down), this filter catches it.
- Implementation: change `WB_ROSS_CUC_MIN_HH` from 2 to 3 (or add new env var)

**C2 — Minimum Bars Before CUC Can Fire**
CUC cannot fire in the first N bars of the trade. Gives the trade time to develop before declaring it dead. Ross doesn't exit on the first 1-2 candle pullback.

- Env var: `WB_ROSS_CUC_MIN_TRADE_BARS=5` (CUC inactive for first 5 minutes of trade)
- Most CUC losers fire early: IOTR, MOVE, RUBI, CDIO all show CUC catching the first pullback
- Implementation: check trade age in bars before allowing CUC

**C3 — Minimum R-Multiple Before CUC Can Fire**
CUC cannot fire unless trade is at ≥2R profit. Below that threshold, CUC is catching noise, not reversals. Above it, the trade has proven itself and a lower-low is more meaningful.

- Env var: `WB_ROSS_CUC_MIN_R=2.0`
- Note: `WB_ROSS_CUC_MIN_R` already exists (set to 5.0 for suppression on deep runners). Lowering to 2.0 means CUC can fire on any trade above 2R.
- Effect: IOTR (-0.6R), MOVE (-0.7R), RUBI (-0.2R), CDIO (-0.6R), ANNA (-0.1R) all blocked. ROLR (+0.3R), SER (+0.3R) also blocked. Only SLGB (+3.5R) and POLA (+1.5R) still fire.
- Blocked trades total: -$1,650 of losses prevented, -$417 of gains lost. Net: +$1,233 improvement.

**C4 — CUC Only at Price Levels**
CUC only fires when price is within 3% of a whole or half-dollar level. The logic: sellers congregate at round numbers, so a lower-low at $4.00 is meaningful, but a lower-low at $3.37 is noise.

- SLGB: CUC at $3.53, 0.8% from $3.50 half-dollar → FIRES (within 3%)
- POLA: CUC at $3.11, 3.7% from $3.00 whole dollar → BLOCKED
- IOTR: CUC at $8.31, 2.2% from $8.50 → FIRES (within 3% of $8.50 half)
- MOVE: CUC at $19.36, 3.2% from $20.00 → BLOCKED
- More complex to implement but directly aligns CUC with Ross's price-level awareness

---

### Partial Exit Systems

**P0 — No Partials (Current)**
100% position enters, 100% exits on single signal. Baseline for comparison.

**P1 — Whole-Dollar Partials (Mechanical)**
Take 25% off at first whole dollar above entry. Take another 25% at second whole dollar. Remainder (50%) managed by candle signals + structural trail.

Level calculation: for entry $3.58, levels are $4.00, $5.00, $6.00. For entry $8.04, levels are $9.00, $10.00.

Pros: Locks in guaranteed profit at meaningful resistance. Reduces risk on remainder.
Cons: On runners (VERO), front-loads exits and reduces final P&L. 25% at $4.00 on VERO means we captured only $0.42/share on that tranche instead of $2.08.

**P2 — Half-Dollar Partials (Tighter Grid)**
Same as P1 but uses half-dollar levels. For entry $3.58: levels are $4.00, $4.50, $5.00, $5.50. For entry $8.04: $8.50, $9.00, $9.50.

Pros: More frequent partials = more profit locked in on stocks that can't reach the next whole dollar.
Cons: On runners, even more front-loaded. VERO would have 4 partials before the shooting star.

**P3 — Signal-at-Level (Ross's Actual Approach)**
NO automatic partials. Instead: when a warning signal (doji or topping tail) fires within 3% of a whole or half-dollar level, take a 25% partial. If no warning signal fires at the level, no partial — full position rides.

This is the most selective approach. It combines Ross's two insights: (1) take profit at resistance, (2) only when the candle confirms indecision.

- ARTL: doji at $8.00 (exactly at whole dollar) → 25% partial. YES, this fires.
- MXC: shooting star at $16.00 → this is a full exit signal, not a partial. So no partial needed.
- VERO: did a doji form at $4.00 or $5.00? If not, no partial taken. Full ride to shooting star at $5.66.

Pros: Doesn't penalize runners. Only takes profit when there's both price-level resistance AND candle indecision.
Cons: May miss partials on stocks that fade without a warning signal (those are caught by CUC or backstops instead).

---

## Recommended Test Combinations

### Combo 1: C3 + P0 (Min-R CUC Gate, No Partials)
**The CUC-only fix.** Tests whether simply gating CUC behind a 2R profit minimum fixes the regression. If CUC can't fire below 2R, the 5 losing CUC exits (-$1,972) are all blocked. The 2 winning exits below 2R (ROLR +$229, SER +$188) are also blocked, but those are small.

- Change: `WB_ROSS_CUC_MIN_R=2.0` (from current 5.0)
- Wait — actually CUC_MIN_R=5.0 currently means CUC is suppressed above 5R. We need the OPPOSITE: suppress below 2R. Need a new env var: `WB_ROSS_CUC_FLOOR_R=2.0` (CUC only fires when trade profit ≥ 2R).
- Estimated impact: +$1,233 from blocked losers. Net V2 improvement: $14,910 + $1,233 = ~$16,143. Still behind baseline's $25,709 but closer.
- Tests the hypothesis: "CUC's problem is firing on unprofitable trades"

### Combo 2: C2 + P1 (Min-Bars CUC + Whole-Dollar Partials)
**Time gate + price partials.** CUC can't fire in first 5 bars. Proactive 25% partial at first whole dollar.

- Changes: `WB_ROSS_CUC_MIN_TRADE_BARS=5`, new partial system
- The 5-bar gate gives every trade at least 5 minutes to reach the first price level
- If the stock reaches the level and takes the partial, the remaining 75% is managed by signals
- If CUC fires after bar 5, only 75% of the position is affected (25% already locked in)
- Estimated impact: harder to compute without knowing exact bar counts, needs backtest

### Combo 3: C1+C3 + P3 (Tightened CUC + Signal-at-Level Partials)
**Closest to Ross.** CUC requires ≥3 HH AND ≥2R profit. Partials only when a warning signal coincides with a price level.

- Changes: CUC ≥3 HH + 2R floor, signal-at-level partial logic
- Most selective — only takes action when multiple conditions align
- This is the "high conviction only" approach: hold full position unless there's strong evidence the move is over
- Risk: may not capture enough on stocks that consolidate without clean signals

### Combo 4: C2 + P0 (Min-Bars CUC, No Partials)
**Simplest possible fix.** Just delay CUC by 5 bars. No partial system. Tests whether the timing of CUC is the whole problem.

- Change: `WB_ROSS_CUC_MIN_TRADE_BARS=5`
- If this alone closes most of the gap, the partial system may be unnecessary
- Implementation: ~3 lines of code

---

## Modeling Against Key Trades

### VERO ($3.58 → shooting star at $5.66)

| Variation | Partial at $4? | Partial at $5? | Final Exit | Est P&L per Share | vs V2 ($2.08) |
|-----------|---------------|---------------|------------|-------------------|---------------|
| Combo 1 (C3+P0) | No | No | SS $5.66 | $2.08 | Same |
| Combo 2 (C2+P1) | 25% at $4.00 | 25% at $5.00 | 50% at SS $5.66 | $1.50 | -28% |
| Combo 3 (C1C3+P3) | Only if doji at $4/$5 | Only if doji at $5 | SS $5.66 | $1.50-$2.08 | 0% to -28% |
| Combo 4 (C2+P0) | No | No | SS $5.66 | $2.08 | Same |

**VERO verdict:** Price-level partials HURT on VERO. The no-partial combos (1, 4) match V2. The partial combos (2, 3) reduce P&L.

### SLGB ($3.04 → CUC at $3.53 in V2, sq_target_hit at $4.00 in baseline)

| Variation | CUC fires? | Partial? | Exit | Est P&L per Share |
|-----------|-----------|---------|------|-------------------|
| V2 current | YES at $3.53 | No | $3.53 | $0.49 |
| Combo 1 (C3) | CUC at +3.5R, YES fires | No | $3.53 | $0.49 (no change) |
| Combo 2 (C2) | Depends on bar count | 25% at $3.50 | $3.53 or higher | ~$0.49+ |
| Combo 3 (C1C3) | CUC needs ≥3 HH at +2R, may not fire | Signal-at-level | Unknown | Depends on candles |
| Combo 4 (C2) | If bar count > 5, yes | No | $3.53 or higher | $0.49+ |

**SLGB verdict:** C3 alone doesn't help (CUC fires at 3.5R which is above 2R). C1 (≥3 HH) or C2 (min bars) might help if the consolidation pattern doesn't have 3+ HH bars or happens within 5 bars. **This trade needs the actual bar data to model.**

### ACON ($8.04 → stop at $7.90 in V2, sq_target_hit at $8.32 in baseline)

| Variation | CUC? | Partial? | What happens |
|-----------|------|---------|-------------|
| V2 current | N/A (hit sq_stop) | No | -$375 |
| Combo 1 | N/A | No | Still hits stop: -$375 |
| Combo 2 | N/A | First level $8.50, stock didn't reach it | Still hits stop: -$375 |
| Combo 3 | N/A | Signal-at-level: no signal before stop | Still hits stop: -$375 |
| Combo 4 | N/A | No | Still hits stop: -$375 |

**ACON verdict:** None of our variations help. The stock reversed before any exit mechanism could fire. The baseline caught it with sq_target_hit at $8.32 because 2R was only $0.28 above entry. Without a hard R-target, this trade is a loss in every variation. **This is the cost of not having hard targets** — we accept it because the upside on runners (VERO, BATL, CRE) overwhelms it.

### CRE ($5.04 → sq_target_hit at $6.89 in baseline, $0 in V2)

V2 got 0 trades on CRE because ross exit changed trade sequencing. This is a second-order effect — the exit timing on a prior trade shifted the slot so CRE was never entered. **No exit variation fixes this directly.** It's an artifact of the sequential simulation.

---

## Implementation Priority

Based on the modeling:

1. **Start with Combo 4 (C2 + P0)**: Just add `WB_ROSS_CUC_MIN_TRADE_BARS=5`. This is 3 lines of code and isolates whether CUC timing is the problem. If this closes a meaningful portion of the gap, it proves the hypothesis without adding complexity.

2. **Then test Combo 1 (C3 + P0)**: Add `WB_ROSS_CUC_FLOOR_R=2.0`. This is also ~5 lines and independent of Combo 4. Can test both gates together or separately.

3. **If CUC fixes aren't enough, add P3 (signal-at-level partials)**: This is more complex — requires position tracking for partial fills, price-level detection, and coupling warning signals to levels. Only implement if the CUC fixes alone don't close enough of the gap.

4. **P1/P2 (mechanical price-level partials) are likely not worth it**: They hurt on every runner (VERO, BATL, CRE-type) and the stocks that reverse (ACON, SPRC, SPHL) hit their stop before reaching any level. The math doesn't favor mechanical partials on our stock universe.

---

## Directive for CC

### Phase 1: CUC Fixes (run together as 4-way comparison)

Modify `ross_exit.py` to support two new env vars:
- `WB_ROSS_CUC_MIN_TRADE_BARS=0` (default 0 = current behavior)
- `WB_ROSS_CUC_FLOOR_R=0` (default 0 = current behavior)

Run 4 configs through the YTD runner (or 4 separate runs):
- Config A: Baseline (ross exit OFF) — existing data
- Config B: V2 current (ross exit ON, CUC as-is) — existing data
- Config C: V2 + CUC_MIN_TRADE_BARS=5
- Config D: V2 + CUC_FLOOR_R=2.0
- Config E: V2 + both (CUC_MIN_TRADE_BARS=5 + CUC_FLOOR_R=2.0)

Compare C/D/E against A and B.

### Phase 2: Signal-at-Level Partials (only if Phase 1 insufficient)

Add partial position support to trade accounting. Implement price-level detection (next whole/half dollar above entry). Couple warning signals to levels: doji or topping tail within 3% of a level → 25% partial.

This phase requires more development and is deferred unless Phase 1 results warrant it.

---

## Success Criteria

- Any combo that beats baseline (+$25,709) is ready for live
- Any combo within $3,000 of baseline while having lower max drawdown is a viable alternative
- If no combo beats baseline, we need to rethink the ross exit approach entirely
