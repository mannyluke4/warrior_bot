# Audit: Ross Cameron's Candlestick Strategy vs V2 Bot Implementation

**Date:** 2026-04-01  
**Source:** Ross Cameron — "The Secret Nobody Tells You About Reading Candlestick Charts" (March 28, 2026)  
**Auditor:** Cowork (Perplexity)

---

## Video Summary

Ross's core thesis: **Stop using technical indicators. Read raw candlesticks directly.** Indicators lag because they require candle closes and mathematical transformations. Raw candlestick shapes (body size, wick direction, wick-to-body ratio) give you the same information faster — you can see the signal forming in real time, tick by tick, before the candle even closes.

His 11 candlestick "letters" form a vocabulary. When combined in sequence, they spell out "buy" or "sell" in real time. The key patterns he uses:

**Bullish signals:** Hammer (long lower wick, short body), dragonfly doji, bullish engulfing (candle-over-candle), large green body with no lower wick

**Bearish/exit signals:** Shooting star (long upper wick), gravestone doji, bearish engulfing (candle-under-candle), doji after an uptrend (indecision = momentum fading)

**The critical insight:** He enters on the BREAK of the candle high (not waiting for the close), and exits the SECOND a candle goes red after a shooting star or doji. He's reading price action in real time, not waiting for bar closes.

---

## What We're Doing RIGHT

### 1. Scanner / Stock Selection — SOLID
Ross: Find small-cap, low-priced stocks with breaking news and high volume potential (200-400% moves).

**Our bot:** Scanner filters for gap ≥10%, price $2-$20, float 2-20M, RVOL ≥1.5x, PM volume ≥30K. This matches Ross's criteria almost exactly. ✅

### 2. Candle Pattern Library — EXISTS
We have `candles.py` with correct implementations of:
- `is_doji()` — body ≤12% of range ✅
- `is_hammer()` — lower wick ≥2x body, upper wick ≤0.7x body ✅
- `is_shooting_star()` — upper wick ≥2x body, lower wick ≤0.7x body ✅
- `is_bullish_engulfing()` — green candle body engulfs prior red candle body ✅
- `is_bearish_engulfing()` — red candle body engulfs prior green candle body ✅
- `candle_parts()` — decomposes any candle into body, upper_wick, lower_wick, range ✅

These match Ross's 11 candle types accurately.

### 3. Multi-Pattern Detection — EXISTS
`patterns.py` (356 lines) detects higher-level patterns:
- Bull flag ✅
- Flat top breakout ✅
- Ascending triangle ✅
- ABCD pullback ✅
- Red-to-green ✅
- Volume surge ✅
- Whole dollar proximity ✅

### 4. Volume Explosion Entry — MATCHES ROSS
The squeeze detector requires a volume explosion bar (volume > Nx average) that's green, has significant body (>1.5%), above VWAP, making new HOD. This matches Ross's description of the initial breakout candle. ✅

### 5. Mechanical 2R Target Exit — WORKING
`sq_target_hit` is 13/13 (100%) in the honest YTD. The mechanical exit captures profit reliably. Ross doesn't use a fixed R-target, but the concept of taking profit at a predefined level is sound for a bot that can't read discretionary signals. ✅

---

## What We're MISSING

### 1. CRITICAL: Live Bot Has ZERO Candle-Based Exits

**Ross:** Exits the SECOND a candle goes red after a shooting star. Exits on bearish engulfing. Exits on doji followed by candle-under-candle. He reads reversal patterns in real time and gets out immediately.

**Simulator (`simulate.py`):** Has 18 references to candle-based exit signals — topping wicky, bearish engulfing, doji warnings, chandelier stops. These are wired into `sim_mgr.on_exit_signal()`.

**Live bot (`bot_ibkr.py`):** Has ZERO candle-based exit signals. The `_squeeze_exit()` function is purely mechanical — dollar loss cap, hard stop, R-multiple trailing stop, 2R target. No pattern reading whatsoever.

**Impact:** The live bot cannot detect when a stock is rolling over. It rides the trailing stop all the way down instead of reading the shooting star / doji / bearish engulfing that Ross would use to exit earlier with more profit. The `sq_para_trail_exit` trades that lose money (-$1,359 total in the YTD) are likely situations where a candle-based exit would have gotten out at breakeven or small profit instead.

### 2. CRITICAL: Entries Wait for Bar Close Instead of Real-Time Breakout

**Ross:** "The first trader to spot that a stock is going to break out and buy gets the most profit." He watches raw ticks and enters the MOMENT price breaks the candle high — he doesn't wait for the bar to close.

**Our bot:** The squeeze detector ARMs on bar close (`on_bar_close_1m`), then triggers on the next tick above the trigger price (`on_trade_price`). This means:
- The volume explosion must complete a full 1-minute bar before PRIMED fires
- The level break must complete a full bar before ARM fires
- Only THEN does the tick-level trigger activate

This creates the ~1 minute delay we confirmed in the TradingView verification. Ross would be in the trade 30-60 seconds earlier.

**Impact:** On a stock moving $1/minute (common on our targets), a 1-minute delay costs $0.50-$1.00 in slippage. On a 5,000-share position, that's $2,500-$5,000 per trade in lost edge. The bot is structurally slower than a human trader reading candles in real time.

### 3. IMPORTANT: No Real-Time Candle Shape Reading on Forming Bars

**Ross:** Watches the CURRENT (incomplete) candle forming in real time. If he sees a long upper wick developing on the current candle, he knows sellers are rejecting the high BEFORE the candle closes. He exits immediately.

**Our bot:** Only processes completed 1-minute bars. The `on_bar_close_1m` function fires once per minute. During that minute, the bot is blind to candle shape — it only sees raw price via `on_trade_price`, which checks the trigger level but doesn't analyze the forming candle's shape (growing upper wick, shrinking body, etc.).

**Impact:** The bot cannot detect intra-bar exhaustion signals. A stock could print a $0.50 upper wick in 15 seconds (sellers slamming it), and the bot won't react until the bar closes 45 seconds later.

### 4. IMPORTANT: No Candle-Over-Candle / Candle-Under-Candle in Squeeze Detector

**Ross:** "Candle over candle" (current candle breaks high of prior) is his primary BUY signal. "Candle under candle" (current candle breaks low of prior) is his primary SELL signal.

**Our squeeze detector:** Checks for volume explosion + green bar + body size + VWAP + HOD. It does NOT check whether the current bar breaks the high of the prior bar (candle-over-candle). The level break check (`_find_broken_level`) looks for PM high, whole dollar, and PDH — not prior candle high.

**Impact:** The squeeze detector can ARM on a volume bar that doesn't actually break above the prior candle's high. Ross would wait for that confirmation. This may cause some false PRIMED → ARMED sequences where the stock has volume but no actual breakout structure.

### 5. MODERATE: No Doji/Exhaustion Detection Before Entry

**Ross:** If he sees a doji or shooting star at the top of a move, he does NOT buy the next candle — the momentum is fading. He waits for fresh confirmation.

**Our squeeze detector:** Does not check for exhaustion signals before arming. If a volume explosion bar is followed by a doji (indecision), the detector still proceeds to ARM if a level breaks. Ross would skip this setup.

### 6. MODERATE: No Context Awareness (Trend vs Chop)

**Ross:** Explicitly says patterns are meaningless in sideways/choppy price action. He only trades at "strong trends at potential pivots/reversals/apex points."

**Our detector:** Has a stale stock filter (no new HOD in N bars) but no explicit trend/chop detection. It can fire on volume explosions that occur in choppy price action where the pattern has no directional meaning.

---

## What We Should Do About It

### Priority 1: Add Candle-Based Exits to Live Bot
The simulator already has this code. Port `topping_wicky` and `bearish_engulfing` exit signals from `simulate.py` into `bot_ibkr.py`'s `on_bar_close_1m` or a new `check_exit_patterns()` function. This is the single biggest improvement — it would let the bot read reversal signals instead of blindly riding the trailing stop down.

### Priority 2: Consider Intra-Bar Candle Reading
Add a check in `_process_ticker` that monitors the FORMING candle's shape. If the current bar is developing a large upper wick (current_high - max(current_open, last_price) > threshold), treat it as an early warning. This is harder to implement but gets closer to how Ross reads charts in real time.

### Priority 3: Add Candle-Over-Candle Confirmation to ARM
Before arming, verify that the current bar's high breaks the prior bar's high. This is Ross's primary entry confirmation and would filter out volume bars that don't have breakout structure.

### Priority 4: Add Doji/Exhaustion Gate Before ARM
If the bar preceding the ARM bar is a doji or shooting star, delay or skip the ARM. The momentum may be fading.

---

## The Philosophical Gap

Ross reads candles like a language — each shape is a letter, sequences form words, and context determines meaning. The bot reads candles like a checklist — is it green? is body > 1.5%? is volume > 3x? These are necessary but not sufficient conditions.

The deepest gap isn't any single missing feature. It's that Ross processes ALL the candle information simultaneously and in context (trend, prior patterns, volume profile, wick psychology), while the bot checks individual binary conditions sequentially. Closing this gap fully would require something closer to what we discussed earlier — an ML model trained on the wave analysis data to learn the multivariate pattern that Ross sees intuitively.

But the four priorities above would get us significantly closer without requiring ML. Especially Priority 1 (candle exits in live bot) — that's existing code that just needs to be ported.
