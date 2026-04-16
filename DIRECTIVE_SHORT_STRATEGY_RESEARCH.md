# DIRECTIVE: Short Strategy Research — Tick-Level Fade Analysis

**Date:** April 15, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code / Cowork)  
**Priority:** P1 — Research and analysis phase. No code yet.

---

## Thesis

Small-cap momentum stocks that squeeze hard eventually come back down. Our data proves it: **44% of our 130 squeeze trades dropped more than 10% from their peak within 30 minutes.** The average fade from peak was 11.2%, with several stocks dropping 30-60%.

Today (April 15), Manny manually shorted BIRD after it ran from $3 to $24 and made $20K on the way down. This is real money on the exact same stocks our bot already watches.

The proposal: after the bot catches the squeeze on the long side, flip to short on the backside of the same stock. The bot already has tick data streaming, knows the HOD, knows when momentum is fading. It just needs the ability to short.

**Before we build anything, we need a tick-level analysis of the fade patterns on our biggest movers.** This directive defines exactly what to analyze and how.

---

## The Data We Have

### Tick Cache (on Mac Mini at `~/warrior_bot_v2/tick_cache/`)
Full tick-level data for multiple dates. These provide second-by-second price action.

### Study Data (108 files in `study_data/`)
Trade-by-trade details including `price_30m_after_exit` and `high_after_exit_30m` for every squeeze trade. Already analyzed — 57 of 130 trades faded 10%+.

### Wave Analysis (10 files in `wave_analysis/`)
Detailed wave profiles (every up and down wave) for our biggest movers. ROLR and VERO already have full wave JSONs.

### Top 10 Targets for Deep Analysis

These are the stocks with the biggest confirmed fades. Analyze ALL of these:

| # | Symbol | Date | Peak | 30m After | Fade % | Fade $ |
|---|--------|------|------|-----------|--------|--------|
| 1 | ROLR | 2026-01-14 | $21.00 | $15.19 | 28% | $5.81 |
| 2 | ACCL | 2026-01-16 | $11.36 | $7.58 | 33% | $3.78 |
| 3 | HIND | 2026-01-27 | $7.57 | $4.82 | 36% | $2.75 |
| 4 | GWAV | 2026-01-16 | $8.40 | $5.30 | 37% | $3.10 |
| 5 | ANPA | 2026-01-09 | $59.83 | $46.43 | 22% | $13.40 |
| 6 | BNAI | 2026-01-28 | $78.50 | $62.51 | 20% | $15.99 |
| 7 | PAVM | 2026-01-21 | $24.07 | $20.03 | 17% | $4.04 |
| 8 | VERO | 2026-01-16 | $6.35 | $5.14 | 19% | $1.21 |
| 9 | SNSE | 2026-02-18 | $36.95 | $31.11 | 16% | $5.84 |
| 10 | MLEC | 2026-02-13 | $12.90 | $10.31 | 20% | $2.59 |

---

## What to Analyze (Per Stock)

For each of the 10 stocks above, produce a detailed fade profile:

### A. The Topping Pattern

At the tick level, what does the transition from "running up" to "fading down" look like? Specifically:

1. **Time of peak (HOD)** — exact timestamp of the highest trade
2. **What happened in the 5 minutes BEFORE the peak?**
   - Was volume increasing or decreasing into the top?
   - Were candles getting smaller (momentum fading)?
   - Were there shooting stars or doji candles at the top?
   - Were there halt resumes at the top?
3. **What was the first signal the top was in?**
   - A bearish engulfing candle?
   - A candle-under-candle break?
   - A VWAP cross below?
   - A volume spike on a red candle?
   - A failed new HOD attempt (lower high)?
4. **How long from peak to the first obvious sell signal?** (in seconds/minutes)
   - If the answer is "less than 1 minute," the bot could catch it
   - If the answer is "the stock chopped for 20 minutes before fading," we need a patience mechanism

### B. The Fade Structure

Once the stock starts coming down:

1. **Was it a straight drop or did it bounce?**
   - ROLR's waves show extreme chop: $21→$15.96→$18.40→$15.15→$17.80 (every 2-3 minutes)
   - Other stocks may have a cleaner fade (steady downtrend)
2. **What was the first lower high?** (price and time after HOD)
   - Lower high = trend has shifted from up to down
3. **How deep was the first pullback from HOD before a bounce?**
   - If the stock drops 5% then bounces 3%, the stop needs to survive that bounce
4. **What was the average red candle size vs green candle size during the fade?**
   - Bigger red candles + smaller green bounces = strong downtrend
5. **How long did the fade last?** (minutes from peak to the 30-minute-later price)
6. **Did the stock ever reclaim HOD after starting to fade?**
   - If yes, how often? This is the risk — shorting into a stock that reclaims HOD is a squeeze against YOU

### C. Key Levels During the Fade

1. **VWAP at time of peak** — did the stock fade TO VWAP and hold, or break through it?
2. **Pre-market high** — did this act as support during the fade?
3. **Whole dollar levels** — did the stock bounce at $15, $10, $5 etc?
4. **The gap fill level** (prior day close) — did the stock fade all the way to the gap fill?
5. **50% retrace of the morning move** — did the fade stop at 50% of the squeeze range?

### D. Volume Profile During the Fade

1. **Volume at the peak vs volume during the fade** — is volume increasing or decreasing during the selloff?
2. **Were there volume spikes on red candles?** (panic selling = accelerating fade)
3. **Did volume dry up before a bounce?** (could use volume as a "cover the short" signal)

### E. Timing Analysis

1. **Did the fade happen before or after the RTH open (9:30 ET)?**
   - Pre-market fades have lower volume and wider spreads
   - RTH fades have more liquidity but also more support buyers
2. **How long from the last squeeze exit to the start of the sustained fade?**
   - Our bot exits at 2R target. How many minutes after our exit does the real fade begin?
3. **What time of day did the stock bottom?**
   - Morning faders (peak 8-9 AM, bottom 10-11 AM)?
   - All-day faders (peak 8-9 AM, steadily down until close)?

---

## Output Format

For each stock, produce a report in `cowork_reports/short_analysis/`:

```
cowork_reports/short_analysis/ROLR_2026-01-14_fade.md
cowork_reports/short_analysis/ACCL_2026-01-16_fade.md
... etc for all 10
```

Each report should contain:

```markdown
# FADE ANALYSIS: [SYMBOL] [DATE]

## Peak Details
- HOD: $X.XX at HH:MM:SS ET
- Last squeeze exit: $X.XX at HH:MM ET
- Time from our exit to peak: X minutes
- VWAP at peak: $X.XX

## Topping Signals (what happened at the top)
- [First signal, with timestamp and description]
- [Second signal]
- Earliest reliable short entry: $X.XX at HH:MM ET

## Fade Profile
- First lower high: $X.XX at HH:MM (X min after HOD)
- Deepest bounce during fade: +X% (from $X to $Y)
- Fade duration: X minutes
- Total fade: X% ($X.XX)
- Did it reclaim HOD: Yes/No

## Key Levels
- VWAP: $X.XX (held/broke through)
- PM high: $X.XX (held/broke through)
- 50% retrace: $X.XX (held/broke through)
- Gap fill: $X.XX (reached/didn't reach)

## Volume Profile
- Peak volume (1-min bar): X shares
- Avg volume during fade: X shares
- Volume ratio (fade/peak): X.Xx

## Hypothetical Short Trade
- Entry: $X.XX at HH:MM (first reliable signal)
- Stop: $X.XX (above HOD + buffer)
- Target 1: $X.XX (VWAP)
- Target 2: $X.XX (50% retrace)
- Target 3: $X.XX (gap fill)
- Risk: $X.XX per share
- Reward (to target 1): $X.XX (X:1 R/R)
```

---

## After the Analysis: Three Short Strategies to Test

Once we have the 10 fade profiles, we'll design and backtest these three approaches:

### Strategy A: "Exhaustion Short" (Aggressive)
Short on the first confirmed reversal signal (shooting star + bearish engulfing + candle-under-candle) after HOD. Stop above HOD + 3%. Target VWAP.
- Pros: Catches the full fade from near the top
- Cons: Higher risk of getting squeezed if stock makes another leg up
- Best for: Stocks that top cleanly with clear exhaustion signals

### Strategy B: "Lower High Short" (Conservative)
Wait for the stock to fail to reclaim HOD (make a lower high on the bounce). Short the break below the lower high's low. Stop above the lower high.
- Pros: Confirmed trend reversal, lower risk of HOD reclaim
- Cons: Misses the first 5-15% of the fade
- Best for: Choppy stocks like ROLR that bounce multiple times before fading

### Strategy C: "VWAP Rejection Short" (Moderate)
Wait for the stock to fall below VWAP, bounce back toward VWAP, and get rejected (VWAP becomes resistance). Short on the rejection candle. Stop above VWAP + 1%.
- Pros: VWAP is the strongest intraday level, rejection = institutional selling
- Cons: Stock may already be down 10-15% by this point
- Best for: Stocks where VWAP acts as a clean dividing line between bullish and bearish

### Strategy Selection
The tick analysis will tell us which strategy fits which stock profile. Halt-heavy stocks (ROLR) probably need Strategy B (too choppy for A). Clean toppers probably work with Strategy A. VWAP-respecting stocks work with Strategy C.

---

## Technical Requirements for Live Shorting

### Alpaca Short Selling
Alpaca supports short selling on paper and live accounts:
```python
# Short entry
order = LimitOrderRequest(
    symbol=symbol,
    qty=qty,
    side=OrderSide.SELL,   # SELL without owning = short sell
    time_in_force=TimeInForce.DAY,
    limit_price=limit_price,
    extended_hours=True
)

# Cover (buy to close)
order = LimitOrderRequest(
    symbol=symbol,
    qty=qty,
    side=OrderSide.BUY,    # BUY when short = cover
    time_in_force=TimeInForce.DAY,
    limit_price=limit_price,
    extended_hours=True
)
```

### IBKR Short Availability
Check if shares are available to borrow:
```python
# ib_insync — check short availability
availability = ib.reqMktData(contract, '236', False, False)
# Generic tick 236 = shortable shares available
# If shortable > 0, shares can be borrowed
```

### Hard-to-Borrow (HTB) Risk
Small-cap momentum stocks are often hard to borrow. The bot MUST check borrow availability before attempting to short. If shares aren't available, skip the trade. This is a hard kill switch — no borrow, no short.

### Uptick Rule (SSR)
If a stock drops 10%+ from prior close, the Short Sale Restriction (SSR) activates. Under SSR, shorts can only be executed on an uptick (bid price above the last sale). The bot needs to handle this:
```python
# Check if SSR is active
ssr_active = (current_price <= prior_close * 0.90)
if ssr_active:
    # Must use limit order at or above current bid + $0.01
    limit_price = current_bid + 0.01
```

---

## What NOT to Do

- Do NOT build any short code yet — research and analysis first
- Do NOT modify the squeeze detector — short is a SEPARATE strategy
- Do NOT short during the squeeze window — the long play has priority
- Do NOT short stocks that are still making new highs (wait for confirmed reversal)
- Do NOT short without checking borrow availability
- Do NOT assume every squeeze stock fades — 19% had minimal fade (<2%)

---

## Timeline

1. **Phase 1 (This directive):** Tick-level fade analysis on 10 stocks → fade profiles
2. **Phase 2:** Design 3 short strategies based on the fade profiles
3. **Phase 3:** Backtest each strategy on the 10 analyzed stocks
4. **Phase 4:** Run full YTD backtest with shorts + squeezes combined
5. **Phase 5:** Paper trade alongside live squeeze bot

---

*The long side catches the rocket. The short side catches the fall. Same stocks, both directions, maximum extraction.*
