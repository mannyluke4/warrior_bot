# ARTL Methodology Gap Analysis — Bot vs Ross Cameron
## 2026-03-18

## Summary
Ross made $9,653 on ARTL. The bot (in backtest) made $922. Same stock, same day, 10x difference. This analysis maps Ross's exact trades against the bot's detector signals to identify where the methodology diverges.

---

## Timeline: Ross vs Bot Side-by-Side

| Time (ET) | ARTL Price | Ross Cameron | Bot Detector |
|-----------|-----------|-------------|--------------|
| 07:00 | ~$4.50 | Not yet watching | 1M IMPULSE detected |
| 07:26 | ~$4.60 | Not yet watching | PULLBACK 1/3 |
| 07:27 | ~$4.60 | Not yet watching | **NO_ARM: exhaustion vol_ratio=0.36** (blocked) |
| 07:30-7:40 | $4.50→$7.30 | Sees ARTL on scanner, green arrow, jumping up rankings | (gap between 07:27 and 07:41 — no signals) |
| **07:41** | **$4.59→$6.97** | **NEWS BREAKS. Buys ~$6.84, adds on break of $7.00** | 1M IMPULSE detected |
| **07:42** | $8.20 high | Sells into push toward $8.19. **+$1,500** | **RESET (lost VWAP)** — trade blocked |
| 07:43-07:49 | $8.20→$5.63 | Pullback. Buys dip ~$6.73 with 5,000 shares | No signals (between resets) |
| **07:50** | $6.40→$6.70 | Holding dip buy, riding bounce | 1M IMPULSE detected |
| **07:51** | $6.70+ | Riding toward $7.60 target | **RESET (extended: 6 green candles)** — blocked |
| 08:00-08:10 | $6.33→$8.26 | Sells dip buy near $7.60. **+$5,000** | No signals (gap from 07:51 to 08:16) |
| 08:10 | $8.26 | Done with dip trade | No signals |
| 08:16 | $8.04 | Attempts VWAP reclaim / 1st candle new high | **RESET (extended: 7 green candles)** |
| 08:19 | ~$7.60 | VWAP trade fails, cuts for -$1,000 | **RESET (topping wicky)** |
| 08:22-08:26 | $7.40-$7.65 | Tries curl trades toward $8.00 area | IMPULSE → PULLBACK → **RESET (topping wicky)** ×4 |
| 08:26 | ~$7.44 | Final trades, approaches $10K peak P&L | **RESET (topping wicky)** — last signal until 9:38 |
| 08:27-09:37 | $7.40→$6.30→$7.00 | **DONE TRADING.** Protects green day. | **72 MINUTES OF SILENCE** — no signals |
| 09:38 | ~$7.00 | Finished, reviewing day | 1M IMPULSE detected |
| 09:49 | $7.40 | Finished | 1M IMPULSE detected |
| **09:52** | $7.60 | **Long finished** | **ARMED** entry=$7.60 score=12.0 |
| **09:53** | $7.62 | — | **ENTRY** $7.62, 3,125 shares |
| 10:00 | $7.92 | — | **TW EXIT** $7.92, **+$922** |

---

## The 5 Methodology Gaps

### Gap 1: The Bot Doesn't Trade Breakout Squeezes — Only Pullbacks
**Ross's edge:** He entered at $6.84 anticipating the break of $7.00 — a **whole-dollar breakout** on the initial momentum squeeze. He doesn't wait for a pullback. He sees the news, sees the volume, and jumps in on the first push.

**Bot's limitation:** The MicroPullbackDetector requires IMPULSE → PULLBACK (1-3 bars) → ARM → breakout trigger. By design, it **cannot enter on the first leg of a move**. When ARTL went from $4.59 to $8.20 in the 07:41-07:42 candles, the bot saw an IMPULSE but then immediately RESET because price "lost VWAP" — the move was too violent for the pullback state machine.

**Impact:** Ross captured the $6.84→$8.19 move (+$1.35, +$1,500). The bot saw it as a "lost VWAP reset."

### Gap 2: The Bot Doesn't Dip-Buy
**Ross's edge:** After the initial squeeze pulled back from $8.20 to $5.63, Ross bought the dip at $6.73 with 5,000 shares and rode the bounce to $7.60. This is a **countertrend buy into support** — a fundamentally different setup than a pullback-on-trend.

**Bot's limitation:** The detector only buys **pullbacks within an uptrend** (price above EMA9 and VWAP). A dip from $8.20 to $5.63 is a 30% crash — the bot sees that as a failed move, not a buying opportunity. The detector was between resets during the entire dip-buy window (07:43-07:49).

**Impact:** Ross captured $6.73→$7.60 (+$0.87, +$5,000). The bot was silent.

### Gap 3: Extended Candle / Topping Wicky Resets Kill Momentum Trades
**Ross's edge:** He traded ARTL continuously from 07:41 to 08:26, taking 4+ trades through a volatile, choppy session. He entered and exited on whole-dollar levels, VWAP reclaims, and curl patterns.

**Bot's limitation:** The detector **reset 9 times** during Ross's active trading window:
- 07:42: RESET (lost VWAP)
- 07:51: RESET (extended: 6 green candles)
- 08:16: RESET (extended: 7 green candles)
- 08:19: RESET (topping wicky)
- 08:21: RESET (topping wicky)
- 08:24: RESET (topping wicky)
- 08:26: RESET (topping wicky)

Each reset wipes the detector's state machine. It has to start over with a fresh IMPULSE → PULLBACK cycle. On a stock moving this fast, the detector spends more time resetting than detecting.

**Impact:** 9 resets in 45 minutes meant the bot never got past PULLBACK 1/3 during Ross's entire active window.

### Gap 4: The Bot Has No Concept of "Curl" or VWAP Reclaim Trades
**Ross's strategy:** After the initial squeeze/dip, he specifically trades "the first one-minute candle to make a new high" — a VWAP reclaim setup. When ARTL curls back toward $8.00 from below, he enters anticipating a push through prior HOD.

**Bot's limitation:** The detector has one pattern: IMPULSE → PULLBACK → ARM → breakout. It has no concept of:
- VWAP reclaim (price crossing back above VWAP from below)
- First candle new high (first 1m bar to exceed prior candle's high after a pullback)
- Curl patterns (rounded bottom approach to a level)
- Whole/half-dollar breakout anticipation

These are all distinct Ross Cameron setups that the bot simply doesn't implement.

### Gap 5: The Bot Entered 2+ Hours After the Opportunity Window
**Ross's timeline:** Entered at 07:41, finished by ~08:30. Total active window: ~50 minutes.
**Bot's timeline:** Entered at 09:53. The stock had already made its entire move ($4.59→$8.26→$5.63→$7.60→$6.30→$7.40) and was in a late-morning consolidation.

The bot's entry at $7.62 was in the "leftover" phase — the stock was oscillating around $7-8 with declining volume. Ross's entries were during the **high-conviction, high-volume** phase when news was fresh and the squeeze was happening.

**Why the bot was late:** The detector needed 9 reset cycles before it finally found a clean IMPULSE → PULLBACK after 09:49. By that point, the stock's best moves were 2 hours in the past.

---

## What Ross Does That the Bot Cannot Do (Currently)

| Ross Cameron Setup | Bot Capability | Gap |
|-------------------|---------------|-----|
| News-driven initial squeeze entry | Cannot enter first leg — needs pullback | **MISSING** |
| Whole/half-dollar breakout anticipation | No level awareness for entry | **MISSING** |
| Dip-buy into support after squeeze | Only buys pullbacks in uptrends | **MISSING** |
| VWAP reclaim / cross-back entry | Detects VWAP for filters, not for entry | **MISSING** |
| First 1-min candle to make new high | No concept of "new high" entries | **MISSING** |
| Curl pattern recognition | Not implemented | **MISSING** |
| Multiple trades per stock per session | Limited by cooldown + no-reentry | **PARTIAL** (by design) |
| Cut losers fast (-$1,000 on failed VWAP) | Has exit signals (BE, TW, stop) | **EXISTS** |
| Protect green day, stop when fading | Has daily risk limits | **EXISTS** |

---

## The Fundamental Architecture Problem

The MicroPullbackDetector was designed for **one specific pattern**: the classic 3-bar pullback after an impulse move. This is a valid Ross Cameron setup — he does trade pullbacks. But it's only **one of at least 5-6 setups** he uses on any given stock:

1. **Initial squeeze entry** (news + momentum) — Gap 1
2. **Dip-buy into support** — Gap 2
3. **Pullback entry** (IMPULSE → PULLBACK → breakout) — **THIS IS WHAT THE BOT DOES**
4. **VWAP reclaim** (first candle new high) — Gap 4
5. **Whole/half-dollar breakout** — Gap 4
6. **Curl/extension** toward prior HOD — Gap 4

The bot implements setup #3 and ignores the other 5. On ARTL, setup #3 didn't fire until 09:53 — two hours after setups #1 and #2 made the money.

---

## Detector Reset Analysis — Why 9 Resets?

| Time | Reset Reason | What Happened | Was Reset Correct? |
|------|-------------|---------------|-------------------|
| 07:27 | exhaustion: vol_ratio=0.36 | Volume fading before the news spike | Yes — pre-news |
| 07:42 | lost VWAP | Price crashed through VWAP after $4.59→$8.20 spike | **Debatable** — VWAP was at ~$5 and price was at $6-7, above VWAP. The "lost VWAP" may be a calculation issue with the extreme move |
| 07:51 | extended: 6 green candles | 6+ green candles in a row | **Too aggressive** — on a squeezing stock, 6 green candles IS the move. Resetting here means never trading the initial run |
| 08:16 | extended: 7 green candles | Same issue, later push | Same — too aggressive for squeeze stocks |
| 08:19 | topping wicky | TW pattern detected | Possibly correct — stock was at $7.60 after $8.26 high |
| 08:21 | topping wicky | Another TW | Redundant — already reset |
| 08:24 | topping wicky | TW during pullback attempt | Prevented ARMED from forming |
| 08:26 | topping wicky | Final TW of the premarket session | Killed the last chance for a premarket entry |

**The "extended candles" reset is the biggest problem.** It resets after 5-6 consecutive green candles, which is designed to prevent chasing extended moves. But on a news-driven squeeze, 6 green candles IS the setup — that's exactly what Ross is trading. The reset assumes "too many green candles = overextended" but on a low-float squeeze, it means "the move is underway."

---

## Quantified Opportunity Loss

| Opportunity | Ross P&L | Bot Could Capture? | Why Not? |
|------------|---------|-------------------|---------|
| Initial squeeze ($6.84→$8.19) | +$1,500 | No | No first-leg entry capability |
| Dip buy ($6.73→$7.60) | +$5,000 | No | No dip-buy setup |
| VWAP curls ($7.40→$8.00 area) | +$3,153 | No | No VWAP reclaim setup, resets blocked ARM |
| Late pullback ($7.62→$7.92) | — | **+$922** | This is what the bot got |
| **Total** | **$9,653** | **$922** | **$8,731 gap (90% missed)** |

---

## Recommendations for Cowork

### Short-term (scanner fix — biggest ROI):
The bot can't trade what it can't see. ARTL wasn't even on the watchlist. Fixing the scanner to use Databento/FMP data would have at least put ARTL in front of the detector at 07:41.

### Medium-term (reduce unnecessary resets):
- The "extended candles" reset should be softened or disabled for stocks with extreme RVOL (>10x). On a genuine squeeze, green candles are the feature, not a bug.
- Topping wicky resets during PULLBACK phase should be reviewed — they killed 4 potential ARM formations on ARTL.

### Long-term (new entry types):
To close the 90% gap with Ross, the bot would need:
1. A **squeeze/breakout entry** module (enter on whole-dollar breaks with news + volume confirmation)
2. A **dip-buy** module (enter on bounces from support after a pullback)
3. A **VWAP reclaim** module (enter on first candle new high after crossing above VWAP)

These are fundamentally different from the micro-pullback detector. They would likely be separate strategy modules that coexist with the existing pullback detector.

---

*Analysis created: 2026-03-19 | Mac Mini CC*
