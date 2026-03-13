# ROLR Case Study — 2026-01-08 (+ 2026-01-21 Follow-Up)

## A. Stock Profile

```
Symbol:     ROLR
Date:       2026-01-08
Catalyst:   Prediction market partnership with Crypto.com (letter of intent)
Prev close: ~$2.25
PM price:   $2.64 (+17.3% gap)
Float:      3.6M (Profile A)
PM volume:  155 shares (EXTREMELY thin — only 1 bar at 4:04 AM)
Day high:   $3.1571 (at 09:37)
Day volume: 660,670
Ross P&L:   ~$86,000 (from video — see note in Section G)
```

## B. Price Action Timeline (Jan 8)

### Premarket (04:00–09:29): Dead Stock

```
TIME    OPEN    HIGH    LOW     CLOSE   VOL     EVENT
04:04   2.64    2.64    2.64    2.64    155     Only PM bar — 155 shares total
08:00   2.58    2.58    2.55    2.55    850     First real activity (4 hrs later)
08:09   2.57    2.57    2.57    2.57    151
08:10   2.58    2.58    2.58    2.58    130
                                                [08:31] Detector: IMPULSE detected
                                                [08:36] Detector: PULLBACK 1/3
08:46   2.65    2.65    2.65    2.65    250     [08:46] RESET (extended: 6 green candles)
08:56   2.60    2.60    2.60    2.60    175
09:18   2.67    2.67    2.67    2.67    200     [09:00-09:31] 16 more RESET (extended)
09:23   2.69    2.69    2.69    2.69    230     Stock drifting up on minimal volume
09:29   2.71    2.71    2.71    2.71    472
```

The stock was essentially dead premarket. 155 shares at 4AM, then thin single-trade bars.
The detector found an "impulse" at 08:31 but it was just a $0.03 tick in a dead market.

### Market Open (09:30–09:37): The Only Move

```
TIME    OPEN    HIGH    LOW     CLOSE   VOL     EVENT
09:30   2.71    2.84    2.69    2.79    19,980  MARKET OPEN — volume explosion
09:31   2.80    3.09    2.77    3.03    33,201  MASSIVE SPIKE +11% in 1 minute
09:32   3.01    3.01    2.90    2.93    21,634  Immediate reversal begins
09:33   2.92    2.98    2.85    2.85    19,014  Selling continues
09:34   2.91    2.98    2.78    2.98    9,836   [09:34] IMPULSE detected
09:35   2.98    3.00    2.90    3.00    18,841  [09:35] PULLBACK 1/3
09:36   3.01    3.03    2.98    3.03    13,169  [09:36] PULLBACK 2/3
09:37   3.03    3.16    2.94    2.95    23,090  *** DAY HIGH $3.1571 ***
                                                [09:37] RESET (bearish engulfing)
```

**Key insight: The entire move was 09:30–09:37 (7 minutes). The stock went from $2.71 to $3.16 then reversed.**

### The Chop Zone (09:38–09:49): Detector Tries, Fails

```
TIME    OPEN    HIGH    LOW     CLOSE   VOL     EVENT
09:38   2.97    2.98    2.74    2.78    5,919   Hard sell-off
09:39   2.78    2.91    2.78    2.91    12,024  Bounce attempt
09:42   2.92    3.13    2.88    3.10    36,346  [09:42] IMPULSE detected
09:43   3.08    3.11    2.86    2.91    11,637  [09:43] RESET (lost VWAP)
09:44   2.91    3.06    2.87    3.06    14,863  [09:44] IMPULSE detected
09:45   3.00    3.05    2.94    3.05    7,230   [09:45] PULLBACK 1/3
09:46   3.03    3.08    2.91    3.07    18,470  [09:46] PULLBACK 2/3
09:47   3.00    3.02    2.95    2.96    5,822   [09:47] RESET (topping wicky)
```

### The Crash (09:50–EOD): Stock Gives It All Back

```
TIME    OPEN    HIGH    LOW     CLOSE   VOL     EVENT
09:50   2.90    2.90    2.87    2.87    576     Fade begins
09:55   2.88    2.90    2.78    2.78    20,530  Selling accelerates
10:00   2.73    2.73    2.65    2.65    11,840  Back to open price
10:03   2.62    2.62    2.45    2.48    13,578  Below previous close
10:15   2.40    2.42    2.37    2.37    1,911
10:17   2.32    2.32    2.27    2.29    6,081   Day low area
...
16:00   2.25    2.26    2.25    2.26    1,334   Closes at prev close
```

**The stock ended the day at $2.26 — essentially unchanged. It was a complete round trip.**

## C. Detector State Machine Log

### Full State Machine Sequence

| # | Time | Event | Details |
|---|------|-------|---------|
| 1 | 08:31 | IMPULSE | PM "impulse" — really just a $0.03 tick in thin trading |
| 2 | 08:36 | PULLBACK 1/3 | |
| 3 | 08:46 | RESET (extended) | Stock kept making green candles — 22 resets from 08:46 to 09:31 |
| 4–22 | 08:46–09:31 | RESET (extended: N green candles) | Detector stuck: slow PM drift up doesn't pull back |
| 23 | 09:34 | IMPULSE | Post-open impulse: $2.78 → $2.98 |
| 24 | 09:35 | PULLBACK 1/3 | |
| 25 | 09:36 | PULLBACK 2/3 | |
| 26 | 09:37 | **RESET (bearish engulfing)** | Bar: O=3.03 H=3.16 L=2.94 C=2.95 — massive reversal candle |
| 27 | 09:42 | IMPULSE | $2.88 → $3.13 bounce |
| 28 | 09:43 | **RESET (lost VWAP)** | Close $2.91 vs VWAP $2.93 — price dropped below VWAP |
| 29 | 09:44 | IMPULSE | $2.87 → $3.06 |
| 30 | 09:45 | PULLBACK 1/3 | |
| 31 | 09:46 | PULLBACK 2/3 | |
| 32 | 09:47 | **RESET (topping wicky)** | Bar: O=3.00 H=3.02 L=2.95 C=2.96 — upper wick rejection |

**The detector detected 4 impulses and started 3 pullback sequences. All were invalidated before arming:**
1. PM impulse → stuck in green candle drift (22 resets)
2. 09:34 impulse → bearish engulfing at 09:37 (the day high candle)
3. 09:42 impulse → lost VWAP at 09:43
4. 09:44 impulse → topping wicky at 09:47

**Armed count: 0. The detector never armed. Quality gates never evaluated.**

## D. Gate Check Analysis

### From the Equity Curve Run (Bar Mode)

The earlier equity curve run (bar mode, not tick mode) did produce gate checks for ROLR:

**Setup 1: G1=SKIP (zero_impulse_range), G2=FAIL (0.0% impulse)**
- This was the premarket "impulse" — literally flat bars where the detector thought it saw a move
- Impulse range was zero because the PM bars were single-tick fills ($2.65 → $2.65)
- **Correct gate decision** — this wasn't a real impulse

**Setup 2: G1=FAIL (pb_vol 192% > 70%), G2=FAIL (impulse_vol 1.1x < 1.5x)**
- This was during the post-open chop (09:34-09:37 area)
- Pullback volume was 192% of impulse volume — heavy selling on the dip
- Impulse volume multiplier only 1.1x vs 1.5x minimum
- **Correct gate decision** — the impulse didn't have volume conviction, and the pullback had more selling than the impulse had buying

### Gate Verdict (Jan 8)

**The gates were irrelevant.** In tick mode (which matches live), the detector never armed, so gates never evaluated. In bar mode, gates correctly blocked weak setups. Either way, the stock was a loser — direct mode lost $603.

## E. Three-Way Comparison

### January 8, 2026

| Mode | Trades | Entry | Exit | P&L | Notes |
|------|--------|-------|------|-----|-------|
| Pullback + Gates ON | 0 | — | — | $0 | Detector never armed |
| Pullback + Gates OFF | 0 | — | — | $0 | **Same result** — gates weren't the bottleneck |
| Direct mode | 2 | $3.00, $3.08 | $2.95, $2.93 | **-$603** | Both stopped by topping wicky exits |

### January 21, 2026 (Follow-Up: +49% Gap, $14.56 Day High)

| Mode | Trades | Entry | Exit | P&L | Notes |
|------|--------|-------|------|-----|-------|
| Pullback + Gates ON | 0 | — | — | $0 | Detector never armed |
| Pullback + Gates OFF | 0 | — | — | $0 | Same result |
| Direct mode | 2 | $14.59, $13.10 | $11.74, $13.00 | **-$832** | Entered at PM top, stopped out |

## F. January 21 Deep Dive

```
Symbol:     ROLR
Date:       2026-01-21
PM price:   ~$13.00 (+49% gap from ~$8.70)
PM volume:  34,000+ shares
Day high:   $14.5600 (at 08:13 — premarket!)
Day volume: 3,211,702
```

### Price Action

```
08:00   12.23   14.51   11.11   12.99   153,692  MASSIVE PM bar — huge range
08:13   11.91   14.56   11.91   14.54   3,343    *** DAY HIGH *** (PM spike)
08:54   13.00   13.08   12.97   13.00   2,565    Last gasp before crash
09:30   12.32   12.47   12.31   12.32   7,835    Market opens — selloff starts
09:34   11.51   11.51   11.35   11.40   19,035   Already -15% from high
09:42   11.39   11.50   10.86   10.93   35,394   Heavy selling
09:44   10.70   10.70   10.10   10.21   14,991   Crash continues
09:50   9.80    9.92    9.33    9.57    26,541   Below $10
10:05   7.85    8.00    7.45    7.89    47,636   Bottom area — 46% crash from high
```

**The stock peaked in premarket at $14.56, then crashed 46% to $7.45 by 10:05 AM.**

### Detector Behavior (Jan 21)

| # | Time | Event | Details |
|---|------|-------|---------|
| 1 | 08:13 | IMPULSE | PM spike to $14.56 |
| 2 | 08:14 | PULLBACK 1/3 | |
| 3 | 08:15 | RESET (lost VWAP) | Price dropped below VWAP almost immediately |
| 4 | 08:53 | IMPULSE | Bounce to $13.00 |
| 5 | 08:54 | PULLBACK 1/3 | |
| 6 | 08:55 | RESET (bearish engulfing) | The selloff candle |

**Direct mode entered at $14.59 (the PM top) and got stopped at $11.74 for -$753.** The pullback detector saved us from this disaster.

## G. Key Findings

### Finding 1: The Gates Are NOT the Problem

Gates ON and Gates OFF produce **identical results** on both dates. The pullback detector itself never arms because:
- PM impulses are on thin volume → resets on extended green candles
- Post-open impulses are immediately reversed → resets on bearish engulfing, lost VWAP, topping wicky

**The bottleneck is the detector, not the gates.**

### Finding 2: The Detector Was RIGHT to Not Arm

On Jan 8, direct mode entered and lost $603. On Jan 21, direct mode entered and lost $832. The pullback detector's inability to arm on these stocks **protected capital**. These were failed breakouts, not healthy pullback-and-continuation setups.

### Finding 3: The Profitable Window Was Extremely Narrow

On Jan 8, the only profitable entry was 09:30-09:31 (the first 2 minutes of the open). By 09:37 the stock was already reversing. Ross likely:
- Entered at the open ($2.71-$2.80 area)
- Caught the spike to $3.00-$3.15
- Exited within minutes

This is a **momentum/breakout play**, not a pullback play. The micro-pullback strategy is designed for a different setup pattern.

### Finding 4: The $86K Number May Need Context

ROLR on Jan 8 only moved from $2.64 to $3.16 ($0.52/share). Day volume was 660K shares.
- $86K at $0.52/share = ~165,000 shares ($430K+ notional)
- That's larger than ROLR's 660K day volume would typically support
- Ross may have traded ROLR across multiple days, or the $86K figure includes other stocks

### Finding 5: What Would Need to Change

For the bot to capture even part of these moves, it would need a **completely different entry mode**:

1. **Not pullback mode** — these stocks don't pull back cleanly. They spike and either continue or reverse.
2. **Opening range breakout or momentum entry** — enter on the initial push at market open, not waiting for a pullback that never comes.
3. **Very fast exits** — the profitable window on Jan 8 was <5 minutes. The signal exit mode (trailing stop) would need to lock profits much faster on low-float stocks under $5.
4. **Pre-market runner detection** — on Jan 21, the stock peaked in premarket. By market open it was already crashing.

### Finding 6: The Equity Curve Zero-Trade Result Is Expected

The pullback strategy with quality gates is designed for a specific pattern: strong impulse → clean pullback → continuation. ROLR on both dates showed: thin PM spike → immediate reversal. These are **not** the strategy's target setup. The zero-trade result isn't a bug — it's the strategy correctly identifying that these stocks don't match its pattern.

---

## H. Recommendation

**Do NOT loosen the gates or detector thresholds based on this case study.** ROLR was a losing trade on both dates in every mode except the impossibly narrow window at market open. The right question isn't "how do we trade ROLR?" — it's "what stocks DO match the pullback pattern, and are there enough of them?"

If the answer is "not enough stocks match in the Jan 5-16 period," the solution isn't to loosen filters (which would let in losers like ROLR). It's either:
1. **Expand the date range** — test more dates to find the ones where pullback setups DO occur
2. **Add a complementary entry mode** — opening range breakout for momentum plays, alongside pullback for continuation plays
3. **Accept the selectivity** — the strategy trades rarely but protects capital when conditions aren't right

---

*Case study generated by Claude | March 12, 2026*
*Data source: Alpaca SIP (tick mode) | Sim window: 07:00-12:00 ET*
