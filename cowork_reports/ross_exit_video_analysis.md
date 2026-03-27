# Exit Timing Deep Dive: Ross Cameron vs Our Bot

**Source:** "STOP Selling Your Winners Too Soon!" — Ross Cameron / Warrior Trading (May 10, 2025)
**Problem Statement:** 86% of our exits are on stocks that ran significantly higher. We are leaving massive upside on the table.

---

## Part 1: Ross Cameron's Exit Framework (Step by Step)

### Prerequisites — Exit Signals Only Work on "Obvious" Stocks
Ross's exits assume the 5 Pillars are met: Price $2–$20, up ≥10%, RVOL ≥5x, breaking news, float <20M shares. If the stock isn't widely watched, candlestick signals don't work because not enough participants are responding to the same patterns.

### The Signal Hierarchy (Fastest → Slowest)
1. **Level 2 / Time & Sales** — raw order flow; earliest warning
2. **Candlestick shapes** — the PRIMARY exit trigger
3. **Technical indicators** — lagging backstops (MACD, VWAP, 20 EMA)

### Exit Signal #1: Candlestick Patterns (PRIMARY)

**A) Regular Doji** (after ≥2 large green candles)
- Opens and closes at same price, wicks above/below
- **Action: Sell 50% immediately on doji close**
- If NEXT candle makes a new low below doji's low → Sell remaining 50%
- If next candle continues green → Hold (false alarm)

**B) Gravestone Doji** (most bearish doji)
- Open = Close = Low of candle; tall upper wick only
- Price tried to go up, fully retraced, closed at bottom
- **Action: Sell 100% BEFORE the candle closes** — don't wait for confirmation
- Watch the countdown timer (5,4,3,2,1) and sell as it forms

**C) Shooting Star** (bearish confirmation)
- Has topping tail + closes RED (below the open)
- **Action: Sell 100% before candle closes** (sell as it's forming)

**D) Topping Tail** (general)
- Any large upper wick after a big move up
- **Action: Sell at least 50% as it forms** (especially late in countdown)

**E) Candle Under Candle — THE CONFIRMED EXIT**
- First candle that makes a NEW LOW vs. the prior candle's low
- This is the FINAL, confirmed exit indicator
- **Action: Sell 100% on this signal — no waiting**
- This is what Ross calls "the line in the sand"

### Exit Signal #2: Technical Indicator Breakdown (BACKSTOP)

| Signal | Action |
|---|---|
| MACD goes negative | Sell 100% immediately — "no scenario where I should still be holding" |
| Price breaks below VWAP | Sell 100% |
| Price breaks below 20 EMA | Sell 100% |

**Hold conditions (ALL must remain true):**
- MACD positive ✅
- Price above VWAP ✅
- Price above 20 EMA ✅

### Exit Signal #3: Level 2 / Time & Sales

- Big seller on Level 2 (e.g., 100K shares on the ask) → prepare to exit
- Red on Time & Sales (sell orders dominating) → exit trigger
- These fire BEFORE candle patterns form

### Scaling Out Methodology

**Phase 1 — Warning signal: sell 50%**
- Regular doji after big green run
- Large topping tail forming

**Phase 2 — Confirmed signal: sell remaining 50% or 100%**
- Next candle makes new low (confirms doji was a top)
- Candle under candle
- Gravestone doji or shooting star → skip Phase 1, sell 100% directly

### Stop Loss: Structural
- Stop = low of the entry pullback pattern
- No arbitrary percentage — it's the structural low of the setup
- "Your max loss is the low of the pullback"

### Time Frames
- **10-second chart:** Entry timing only (very fast/parabolic)
- **1-minute chart:** PRIMARY exit management
- **5-minute chart:** Secondary confirmation

### Give-Back Tolerance
- No explicit percentage rule
- Accepts giving back approximately 1–3 candle periods from the top
- On a 100%+ move in 4 minutes, this is ~5–15% of the move — acceptable vs selling 50%+ of move early

### Key Case Study: ZCAR +$33,000
- Stock up 223%, 78M shares volume
- Bought micro pullback on 10-second chart
- Managed on 1-minute chart
- Held through: normal green candles → first doji (sold 50%) → topping tail → candle under candle (sold rest) → confirmed by MACD going negative
- **This is the whole point:** Signal-based holding is what allows $33K instead of $3K

---

## Part 2: What Our Bot Currently Does

### Micro Pullback Exit Logic (Signal Mode)

**Current flow:**
1. Enter trade with hard stop at pattern low
2. When price reaches `WB_BE_TRIGGER_R` (default 3.0R in .env, but often 1.0R in backtest), move stop to breakeven + $0.01
3. After tp_hit, apply percentage trail: `stop = peak * (1 - WB_SIGNAL_TRAIL_PCT)` — default 0.99 = essentially no mechanical trail
4. On every 10-second bar: check for bearish engulfing and topping wicky patterns → full exit
5. Also: R-multiple trailing stop on 10s bar closes (optional, threshold-based: BE at 2R, lock +1R at 4R, trail below peak at 6R)
6. Bail timer: exit if not profitable within 5 minutes
7. Max loss cap: force exit at 2R loss (or 0.75R in megatest)

**Pattern exits on 10s bars:**
- `is_bearish_engulfing()` → full exit (with grace period + profit gate)
- `TOPPING_WICKY` from detector → full exit (with grace period)
- Both can be suppressed by: parabolic grace, continuation hold, 5m guard mode

### Squeeze Exit Logic (Separate Path)

1. Hard stop always active
2. Pre-target trailing: `peak - (WB_SQ_TRAIL_R * R)` — default 1.5R
3. For parabolic entries: tighter trail at `WB_SQ_PARA_TRAIL_R` — default 1.0R
4. Target hit at `WB_SQ_TARGET_R` (2.0R) → exit 75% core, keep 25% runner
5. Runner trail: `peak - (WB_SQ_RUNNER_TRAIL_R * R)` — default 2.5R
6. Stall timer: no new high in 5 bars → exit
7. VWAP loss: close below VWAP → exit
8. Dollar loss cap: $500 max loss

### VWAP Reclaim Exit Logic
- Similar structure to squeeze: hard stop → pre-target trail (1.5R) → target at 1.5R → runner trail 2.0R → stall at 5 bars → VWAP loss exit

---

## Part 3: Gap Analysis — Where We're Leaving Gold

### CRITICAL GAP #1: We Exit on Wrong Timeframe Candles

**Ross exits on 1-MINUTE candles.** Our bot fires bearish engulfing and topping wicky exits on **10-SECOND bars.**

This is the single biggest source of premature exits. A 10-second bearish engulfing is noise on a stock that's making a massive move. Ross explicitly said he uses the 10-second chart for ENTRY only, then immediately switches to the 1-minute chart for EXIT management.

**Impact:** On a stock running from $5 to $9, there will be dozens of 10-second bearish engulfings along the way. Every micro-pullback, every brief consolidation triggers our exit. Ross would hold through all of these because none of them produce a 1-minute candle under candle.

**Fix:** Move pattern exit detection (BE, TW) to 1-minute bars. Use 10-second bars only for entry detection and hard stop monitoring.

### CRITICAL GAP #2: We Don't Have Candle Under Candle (CUC)

Ross's CONFIRMED exit signal — first 1-minute candle that makes a new low vs prior candle — doesn't exist in our codebase at all. This is his "line in the sand" that he describes as the most important signal.

**What we have instead:** Bearish engulfing (requires engulfing body pattern, not just a lower low) and topping wicky (upper wick ratio). These are related but NOT the same as CUC. Bearish engulfing is stricter (needs the body to engulf), and topping wicky fires on wicks without requiring a new low.

**Fix:** Implement candle-under-candle as a 1-minute exit signal: `current_bar.low < prior_bar.low` after the stock has been running (requires ≥2 consecutive bars making higher highs before the CUC fires).

### CRITICAL GAP #3: We Don't Have Partial Exits (Scaling Out)

Ross's approach is graduated:
- Doji/topping tail → sell 50%
- Confirmation (CUC or next candle red) → sell remaining 50%

Our bot is ALL or NOTHING. In signal mode, it's full position in, full position out. The 3-tranche system exists in classic mode, but it's based on fixed R-multiple targets (1R, 2R), not candlestick signals.

**Impact:** When a signal fires, we dump everything. If the stock resumes, we've given up the entire position instead of just half. Ross's 50%/50% approach means he captures most of the move's upside on the second half.

**Fix:** Implement signal-based partial exits: first warning candle (doji, topping tail on 1m) → sell 50%; confirmed reversal (CUC on 1m, MACD negative, below VWAP) → sell remaining 50%.

### CRITICAL GAP #4: Our Trailing Stop Doesn't Match Ross's Approach

Ross doesn't use a mechanical percentage trail. He holds until a CANDLE SIGNAL fires. His "trailing stop" is structural — the low of the most recent micro pullback on the 1-minute chart.

Our bot uses:
- Signal mode: `peak * (1 - 0.05)` = 5% from peak (when not set to 0.99)
- R-multiple trailing: BE at 2R, lock +1R at 4R, trail below peak at 6R
- Squeeze: fixed R-multiple trail (1.5R pre-target, 2.5R post-target)

**The problem:** A fixed percentage trail or R-multiple trail will ALWAYS sell you out during normal pullbacks in a strong move. Ross's approach doesn't use a trailing percentage — he holds until the candle pattern says "this move is over."

**Fix:** In signal mode, the trailing stop should be "low of the last completed 1-minute green candle" (i.e., structural support), not a fixed offset from peak.

### CRITICAL GAP #5: We Have No MACD / VWAP / 20 EMA Backstop

Ross treats these as absolute "you must not still be holding" indicators:
- MACD goes negative → out
- Price below VWAP → out
- Price below 20 EMA → out

Our bot has VWAP loss as an exit for squeeze/VR trades, but NOT for micro pullback trades in signal mode. And we don't check MACD or 20 EMA position as exit conditions at all.

**Impact:** On trades where the candle pattern is ambiguous (no clean doji, just a slow fade), Ross would exit when MACD goes negative. Our bot would hold through that fade until the fixed trail or a BE/TW pattern eventually fires — often much later and at a much worse price.

**Fix:** Add MACD-negative, below-VWAP, and below-20EMA as hard exit signals for all setup types.

### MODERATE GAP #6: Squeeze Exits Are Too Mechanical

Squeeze trades exit core at exactly 2R with a runner at 2.5R trail. Ross doesn't use fixed R targets on squeezes — he reads the candles. A squeeze from $3 to $8 (with a $0.20 R) would hit "2R" at $3.40 and dump 75% of the position. The remaining 25% runner trails at 2.5R from peak. But the move was to $8.

With a $0.20 R, hitting 2R = $0.40 of profit. The stock went up $5.00. We captured $0.40 on 75% of shares and maybe $1-2 on the 25% runner. Ross would have held the full position from $3.40 through to the first 1-minute CUC, probably around $7-8.

**Impact:** This is probably where a huge portion of that 86% left-on-table comes from. On big squeeze moves, our fixed-R targets are catastrophically early.

**Fix:** Squeeze exits should use the same candle-signal-based approach as micro pullbacks. The pre-target phase should trail on candle structure (low of last 1m green candle), not a fixed R offset. The "target" should be replaced by Ross's approach: hold until you get a valid 1-minute exit signal.

### MODERATE GAP #7: Stall Timer is Anti-Ross

The squeeze stall timer exits if no new high in 5 bars. But Ross explicitly holds through consolidation/sideways periods because the next leg up could be massive (ZCAR consolidated multiple times before each leg higher).

Sideways after a spike is NORMAL for low-float stocks. They halt up, consolidate, then squeeze again. Our stall timer kills the trade during the consolidation.

**Fix:** Stall timer should only fire if the stock is also showing negative candle signals (red candles, below key support). Just "no new high" alone is not an exit reason per Ross.

### MINOR GAP #8: No Level 2 / Tape Reading in Backtest

Ross uses Level 2 and Time & Sales as his earliest warning. We obviously can't backtest this with historical data, but the live bot should incorporate bid/ask wall detection as an exit signal input (we have `l2_bearish` and `l2_ask_wall` as signal names, but the logic may not be wired up for exits).

---

## Part 4: What We're Doing RIGHT

1. **Hard stop at pattern low** — matches Ross's "max loss is the low of the pullback"
2. **Bearish engulfing detection** — Ross uses this (called "candle under candle" when it also makes a new low)
3. **Topping wicky detection** — aligns with Ross's "topping tail / shooting star" signals
4. **Parabolic grace period** — correctly suppresses exits during genuine ramps (Ross would do the same — you don't sell during a parabolic)
5. **Continuation hold** — high-conviction setups should be held longer; this aligns with Ross holding ZCAR through multiple doji/consolidation periods
6. **VWAP loss exit on squeeze** — Ross explicitly uses "price breaks below VWAP" as a hard exit
7. **Bail timer** — Ross's "patience has limits" philosophy; if a trade isn't working within a few minutes, he's out
8. **Max loss cap** — protects from gap-throughs; Ross has similar discipline

---

## Part 5: Recommended Changes (Priority Order)

### Priority 1 — IMMEDIATE (Backtest-Ready)

**1A: Move pattern exits from 10s to 1m bars**
- Bearish engulfing and topping wicky should be evaluated on 1-minute bar closes, not 10-second bars
- 10-second bars remain for entry detection and hard stop only
- This single change alone probably fixes 40-50% of the "left gold on table" problem

**1B: Implement Candle Under Candle (CUC) on 1m**
- Definition: `current_1m_bar.low < prior_1m_bar.low` AND prior context is bullish (≥2 consecutive higher-highs before)
- This becomes the CONFIRMED exit signal
- On CUC: exit 100% of remaining position

**1C: Implement 50% partial exit on warning signals**
- Doji detected on 1m → sell 50%
- Topping tail on 1m → sell 50%
- CUC on 1m → sell remaining 50%
- This replaces the current all-or-nothing approach

### Priority 2 — HIGH (Changes Core Exit Philosophy)

**2A: Replace fixed R targets with candle-signal exits for squeezes**
- Remove `WB_SQ_TARGET_R=2.0` as a core exit
- Instead: hold full position until 1m candle signal fires
- Runner concept still valid but triggered by signals, not R multiples

**2B: Add MACD-negative as a hard exit for all setup types**
- If MACD crosses below zero on 1m chart → exit 100%
- This is Ross's "absolute backstop"

**2C: Add 20 EMA break as a hard exit**
- If 1m close < 20 EMA → exit 100%
- Combined with VWAP: if below VWAP OR below 20 EMA → out

### Priority 3 — MODERATE (Refinement)

**3A: Replace fixed trailing % with structural trail**
- Trail stop = low of last completed green 1m candle
- Updates only on new green candle closes
- Much more natural than `peak * 0.95`

**3B: Revise stall timer to require negative signals**
- Current: no new high in 5 bars → exit
- New: no new high in 5 bars AND (last bar is red OR below 20 EMA) → exit
- Just sideways consolidation is not a sell signal

---

## Part 6: Implementation Notes for Backtest

The backtest (`simulate.py`) already has the infrastructure for most of these changes:

1. **1m bar handling exists** — `on_1m_close(bar)` already processes 1-minute bars for both entry detection and some continuation hold logic. Pattern exits can be added here.

2. **Bearish engulfing already works on bars** — `is_bearish_engulfing()` from `candles.py` is called on both 10s and 1m bars in various places. Just need to move the PRIMARY exit trigger to the 1m handler.

3. **MACD is already computed** — the detector tracks MACD for entry quality gates. Exposing the MACD sign as an exit signal is straightforward.

4. **VWAP is already tracked** — available in `bb_1m.get_vwap(symbol)`, passed to squeeze/VR bar handlers. Just needs to be checked for MP signal-mode exits too.

5. **Partial exits need SimTrade accounting changes** — currently SimTrade has `qty_core` and `qty_runner` but no mechanism for "sell 50% on warning, 50% on confirmation." The 3-tranche framework (`qty_t1`, `qty_t2`, `qty_runner`) could be repurposed: T1 = warning exit (50%), T2+Runner = confirmation exit (50%).

6. **CUC is trivial to implement** — it's literally `current_1m.low < previous_1m.low`. The only nuance is requiring a bullish context (prior bars were green/higher-highs) so you don't exit on the first bar of a trade.

---

*Analysis compiled from Ross Cameron "STOP Selling Your Winners Too Soon!" video + full codebase review of trade_manager.py, simulate.py, and run_megatest.py*
