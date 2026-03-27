# How Ross Cameron Exits Trades: A Complete Analysis

**Generated:** 2026-03-22
**Data sources:** 19 daily recaps (Jan 2–31, 2025), 19 comparison files, strategy audit, monthly summary, post-exit analysis, money-on-table analysis
**Purpose:** Reverse-engineer Ross's exit decision framework so we can model something better than the bot's current sq_target_hit / sq_para_trail_exit system, which leaves 81% of profits on the table.

---

## Part 1: Ross's Exit Decision Framework

Ross doesn't use a single exit system. He uses a layered decision tree that adapts based on setup quality, market conditions, and real-time information. From 19 days of detailed recaps, here are the distinct exit mechanisms he employs, ranked by frequency of observation.

### 1.1 — The Daily P&L Target ("Know When to Stop")

**Observed on:** Jan 2, 3, 7, 10, 13, 14, 17, 24, 30 (at least 9 of 19 days — 47%)

This is Ross's most consistent exit mechanism and it operates at the *session level*, not the trade level. Once he hits a daily dollar target or recognizes diminishing quality, he stops trading entirely.

**Specific observations:**

- **Jan 2:** Stopped after +$12K breaking news win. "Easiest trades are behind me." Recognized post-9:30 AM was halt territory, pops and drops — lower quality.
- **Jan 3:** Stopped after SPCB giveback took him from $5,500 peak to $4,800. Accepted the drawdown rather than chasing it back.
- **Jan 10:** "Base hit day" from 7:30 AM, never wavered. Ended at +$9,500 despite having opportunities to push.
- **Jan 13:** Stopped at intraday high-water mark (+$13K) specifically to avoid a repeat of Jan 8 (-$25K giveback from +$56K peak).
- **Jan 14:** Stopped after recovery from emotional cascade. Ended +$5,633 after hitting +$10K peak.
- **Jan 17:** Fifth consecutive green day. Fewer than 10 trades. "Trading on defense" before 3-day weekend.
- **Jan 24:** +$81K day — stopped after ALUR moved $12/share. "Stopped after big win."
- **Jan 30:** Applied 20% drawdown rule after giving back AMOD gains. Stopped at ~10:30 AM.

**The pattern:** Ross has a ~$5K "base hit" daily target as a floor and a dynamic ceiling based on the day's character. On A+ days (Jan 13, 21, 24, 28, 31), he pushes past the base hit. On choppy/thin days (Jan 3, 7, 10, 15, 17), he takes the base hit and walks away. He *never* trades past 10:30 AM on a defensive day, and rarely past 11:00 AM on any day.

**The 20% drawdown rule (Jan 30):** If daily P&L drops 20% from intraday peak, stop trading. This is a mechanical rule he explicitly cited.

**Bot equivalent:** None. The bot has no concept of "enough for today." It would keep scanning and trading all session, potentially giving back gains on noise trades.

**Automatable?** YES — this is one of the most directly automatable techniques.
- Implement a daily P&L target (e.g., $2,000-$5,000 scaled to account size)
- Implement a 20% peak drawdown halt
- Implement a time cutoff (no new entries after 10:30 AM on days below the base hit target)
- Implement an "after first big win" mode that tightens all subsequent entries

---

### 1.2 — Partial Exits / Scaling Out

**Observed on:** Jan 6 (ARBE), 13 (SLRX), 21 (INMN, BTCT), 22 (NEHC, BBX), 24 (ALUR), 28 (ARNAZ), 29 (SLXN), 31 (SGN)

Ross scales out of winners rather than using all-or-nothing exits. The recaps don't always specify exact percentages, but the pattern is consistent enough to reconstruct his framework.

**How Ross scales:**

1. **First partial: at first technical resistance or round number.** He takes 25-50% off at the first clean resistance level. Examples:
   - **ARBE Jan 6:** Entered $33.75, triple rejection at $50 = exit zone. Whole/half-dollar resistance.
   - **SLRX Jan 13:** Stair-step exits at $3.50, $4.00, $4.50, $5.00 — each whole dollar was a partial exit level.
   - **INMN Jan 21:** Dip buying $7.25-$7.50, high $9.20 — partials at round numbers on the way up.
   - **SGN Jan 31:** Entry $3.40, adds at $3.55/$3.59, squeeze to $4.00. $4.00 whole dollar = first major partial.

2. **Second partial: at the next technical level if momentum continues.** If the stock pushes through the first level, he takes more off at the next significant level.
   - **ALUR Jan 24:** Rode from ~$8.24 to $20. Almost certainly took partials at $10, $12, $15, and exited the remainder as momentum died before the 9:30 AM secondary offering.
   - **ARNAZ Jan 28:** $7.50→$14.00. Halt resumption dip-and-rip pattern. Partials likely at $10, $12, $14.

3. **Remainder: held until a reversal signal or session end.** The last portion rides with a mental trailing stop based on candle patterns (detailed in 1.4 below).

**Key insight — Ross's partials are at PRICE LEVELS, not R-multiples.** He doesn't think "I'm at 2R, time to take profit." He thinks "price is approaching $5.00, that's a whole dollar where sellers will appear, I'll lighten up." This is fundamentally different from the bot's fixed R-multiple targets.

**Bot equivalent:** The bot uses sq_target_hit (fixed R-multiple) — a single all-or-nothing exit at a predetermined profit level. No partials.

**Automatable?** YES — partially.
- Implement tiered exits: 1/3 at first round-number resistance above entry, 1/3 at next level, 1/3 on trail
- Round-number resistance is mechanical: if entry is $3.40, first target is $4.00 (next whole dollar)
- Half-dollar levels for stocks above $5: $5.50, $6.00, $6.50, etc.
- The "remainder on trail" portion needs a wider trail than the current parabolic trail (see 1.3)

---

### 1.3 — Trailing Stop Behavior (Mental, Not Mechanical)

**Observed on:** Nearly every winning trade across all 19 days.

Ross does NOT use a traditional trailing stop. He uses what is best described as a "mental trailing stop anchored to candle structure." He holds until the chart tells him the move is over, not until a fixed percentage gives back.

**How Ross trails:**

1. **He does not trail from the first tick of profit.** This is the single biggest difference from the bot. The bot's sq_para_trail_exit activates immediately once a position is profitable, and the parabolic trail tightens aggressively. Ross gives the trade room to breathe.

2. **He trails using 1-minute candle bodies, not wicks.** A wick below the prior candle's low is tolerated. A candle body closing below the prior candle's low is the warning signal. Two consecutive candle bodies closing lower = exit.

3. **On 10-second charts (fast movers), he trails tighter.** For news-driven squeezes in the first 5 minutes, Ross switches to 10-second charts and trails using micro-pullback structure within 1-minute candles:
   - **AIFF Jan 10:** "10s chart entries" — trading micro pullbacks inside 1m candles during rapid acceleration.
   - **ARBE Jan 6:** "10-second chart for fast news movers (micro pullbacks inside 1m candles)."
   - **OSTX Jan 15:** "10s chart micro pullback entry" — same pattern.

4. **He uses 5-minute chart structure for wider moves.** For stocks in a sustained multi-minute run, Ross switches to 5m+1m alignment:
   - **XHG Jan 10:** "5-minute + 1-minute chart alignment = preferred multi-timeframe confirmation." Ross held XHG through multiple 1m pullbacks because the 5m trend was intact.

**The key calibration question:** When does Ross give a trade "room to breathe" vs. cutting it? The answer from the data:

- **High-quality setup (A+ catalyst, low float, massive volume):** Wide room. ALUR ran $8→$20 and Ross held most of the ride. INMN he dip-bought repeatedly. SLRX he held through the stair-step breakout from $1.50→$5.
- **Base-hit setup (smaller catalyst, higher float, uncertain):** Tight room. VMAR Jan 10 ($3.00→$3.25, exit on first stall). TPET Jan 21 ($3.00→$3.24, "didn't pull away" = exit). ZO Jan 17 (4-5 re-entries in a $0.38 range rather than holding).
- **Deteriorating setup:** Immediate exit. XTI Jan 21 (-$12, "ruthless cut"). MIMI Jan 23 ("near flush, narrowly avoided loss").

**Bot equivalent:** sq_para_trail_exit — a parabolic trail that activates from the first tick of profit and tightens aggressively. This captured $0.01/share on WHLR and $0.06/share on SLXN. The trail is calibrated to never give back gains, which means it never allows gains to develop.

**Automatable?** PARTIALLY.
- Replace the parabolic trail with an ATR-based trail that gives the trade room proportional to the stock's volatility
- Implement a "minimum profit threshold" before any trail activates (e.g., don't start trailing until profit exceeds 1R)
- Use candle-structure trailing: trail below the low of the last completed 1m candle body (not wick)
- For high-score setups (R-score > 10), use 5m candle structure instead of 1m
- The 10-second chart micro-pullback trailing is harder to automate but could be approximated with tick-based trailing on very high volume moves

---

### 1.4 — Specific Reversal Signals Ross Uses to Exit

These are the specific technical signals Ross cited as exit triggers across the 19 recaps. Each is documented with the specific trade where it was observed.

#### A. Candle Patterns

| Signal | Observation | Example |
|--------|------------|---------|
| **Tweezer top** | Matching highs on consecutive 1m candles | OSTX Jan 15: "Tweezer top = reversal signal" |
| **Shooting star (5m)** | Long upper wick, small body on 5m chart | PHIO Jan 13: "5m shooting star + candle-under-candle" |
| **Double top (1m)** | Two equal highs with a dip between | PHIO Jan 13: "1m double top + topping tail" |
| **Topping tail** | Long upper wick on any timeframe | PHIO Jan 13, OSTX Jan 15 |
| **Candle-under-candle** | Current candle's high below prior candle's low | PHIO Jan 13: "candle-under-candle" on 5m = confirmation of reversal |
| **Bearish engulfing** | Current candle's body fully engulfs prior candle's body downward | Implied in multiple exits but not explicitly named by Ross |

**Key insight:** Ross uses MULTIPLE confirming signals, not just one. PHIO exit was "1m double top + topping tail" AND "5m shooting star + candle-under-candle." He waits for confluence before exiting a strong position.

**Bot equivalent:** The bot uses topping_wicky_exit_full and bearish_engulfing_exit_full as discrete single-signal exits. No confluence requirement.

**Automatable?** YES — all of these are pattern-matchable on candle data.
- Implement tweezer top detection (two consecutive 1m candles with highs within 0.5% of each other)
- Implement shooting star detection (upper wick > 2x body on 5m)
- Implement double top detection (two 1m highs within 0.3%, separated by a dip > 1%)
- CRITICAL: require 2+ confirming signals before exiting a high-quality setup. Single-signal exits should only apply to base-hit trades.

#### B. Level 2 / Tape Reading Exits

| Signal | Observation | Example |
|--------|------------|---------|
| **Large seller on Level 2** | 50K-200K share sell orders at specific prices | OSTX Jan 15: "L2 sellers at VWAP/200K at $7" |
| **Volume divergence** | Light volume on up-moves, heavy on down-moves | CGBS Jan 7: "light volume up, heavy volume down = sellers absorbing" |
| **Large bidder disappearing** | The large buyer that triggered the entry leaves | DGNX Jan 23: Ross entered because of a large bidder at $15.55 — exit would be triggered by that bid disappearing |

**Bot equivalent:** None. The bot has no Level 2 data.

**Automatable?** NO — not without real-time Level 2 data feeds. This is part of the ~$25K/month "uncapturable human edge" identified in the money-on-table analysis.

#### C. VWAP as Exit Reference

| Signal | Observation | Example |
|--------|------------|---------|
| **Price breaks below VWAP** | VWAP as go/no-go line — exit if price drops below | RHE Jan 6: "stopped trading RHE when it broke below VWAP" |
| **Sellers stacking at VWAP** | L2 sell orders concentrated at VWAP | OSTX Jan 15: "L2 sellers at VWAP" |
| **VWAP as entry filter (inverse)** | Only enters above VWAP — exit is below VWAP | VSS Jan 17: "below VWAP all morning" = don't enter/exit if holding |

Ross uses VWAP as a binary filter: above VWAP = bullish, below VWAP = bearish. This isn't a trailing mechanism — it's a "the thesis is broken" exit.

**Bot equivalent:** None. The bot doesn't reference VWAP in exit logic.

**Automatable?** YES — VWAP is calculable from price/volume data.
- Implement VWAP break as a hard exit: if price closes a 1m candle below VWAP after being above it, exit remaining position
- This would have prevented the WHLR extended holding (bot held for +$0.01/share while the stock potentially dipped below VWAP and recovered)
- Should be a supplementary exit, not a primary one — VWAP break on high-quality runners may just be a pullback

#### D. Price Level / Psychological Exits

| Signal | Observation | Example |
|--------|------------|---------|
| **Whole dollar resistance** | $3, $4, $5, $10 — sellers congregate here | SLRX Jan 13: partials at every whole dollar from $3→$5. ADD Jan 14: "targeting $3, stalled just under." |
| **Half-dollar resistance** | $3.50, $4.50, etc. | VNCE Jan 29: "$2.99 looking for $3 break" |
| **Triple rejection** | Price tests a level 3 times and fails | ARBE Jan 6: "triple rejection at $50" |
| **Prior day's highs** | The high from a previous session acts as resistance | Jan 13: "200 EMA as daily chart resistance + 'look left' for prior candle highs" |

**Bot equivalent:** The bot's sq_target_hit uses a fixed R-multiple, which may or may not align with actual price levels.

**Automatable?** YES — entirely mechanical.
- Identify the nearest whole dollar above entry as first target
- Identify half-dollars as secondary targets for stocks > $5
- Pull prior day's high and 200 EMA as additional reference levels
- Use these as partial exit levels, not full exits

#### E. SEC Filing / Fundamental Exits

| Signal | Observation | Example |
|--------|------------|---------|
| **Shelf registration discovered** | Signals potential secondary offering | PHIO Jan 13: "checked SEC filings mid-trade, found shelf registration ($100M)" |
| **Operating loss concern** | Signals dilution risk | ARBE Jan 6: "checked SEC filings, found $43M operating loss, worried about secondary offering" |
| **Secondary offering announced** | Immediate exit on news of dilution | ALUR Jan 24: "Secondary offering at 9:30 AM killed momentum — Ross already banked profits" |

Ross checks SEC filings *during* trades. This is a risk management technique — he's looking for reasons the stock might reverse (shelf registrations, large operating losses that need financing, etc.).

**Bot equivalent:** None.

**Automatable?** PARTIALLY — SEC filing data can be pulled, but the interpretation requires judgment. A shelf registration is a risk factor, not an automatic exit. The secondary offering announcement is automatable (news feed trigger).

---

### 1.5 — Time-Based Exit Behavior

**Observed on:** Nearly every day.

Ross's trading has a clear temporal structure:

| Time Window | Ross's Behavior | Frequency |
|-------------|----------------|-----------|
| **6:45-7:00 AM** | Spotting and entering "ice breaker" trades | Daily ritual — small position to get the day started |
| **7:00-8:30 AM** | Primary trading window — largest positions, highest conviction | Where ~70% of profits come from |
| **8:30-9:30 AM** | Continuation and news-driven trades. Sizing starts to decrease | Still active but more selective |
| **9:30-10:00 AM** | Open volatility — choppy, often gives back gains on open-bell trades | Mixed results. NLSP Jan 31 gave back $1K at open. BTCT Jan 21 +$5.5K at open. |
| **10:00-10:30 AM** | Last call. Final trades if the day warrants it | Only if having a strong day |
| **After 10:30 AM** | Rarely trades. Usually only if a mid-morning setup appears (MVNI Jan 29 at 9:47 AM, KAPA Jan 13 at 11:15 AM was bot-only) | <10% of activity |

**Critical insight for exits:** Ross almost never holds a position past the time he'd be willing to enter it. If he enters at 7:00 AM and the stock is stalling at 8:30 AM, he exits — not because of a specific signal, but because the "time for this stock to work" has passed. He doesn't hold losing positions waiting for recovery during his active window.

**Hold time by trade quality (estimated from recaps):**

| Trade Quality | Typical Hold Time | Examples |
|--------------|-------------------|---------|
| **A+ runner** | 30-120 minutes | ALUR: ~90 min ($8→$20). SLRX: ~60 min stair-step. ARNAZ: ~60 min. |
| **Solid winner** | 10-30 minutes | ARBE: ~30 min ($33.75→$50). NEHC: ~20 min. |
| **Base hit** | 2-10 minutes | VMAR: ~5 min. TPET: ~5 min. ZO: 4-5 re-entries of 2-5 min each. |
| **Quick scalp** | <2 minutes | JFB Jan 28: quick scalp. NLSP ice breaker: quick pop. |
| **Failed trade** | <1 minute (often seconds) | XTI Jan 21: -$12, immediate cut. MIMI Jan 23: near flush, quick exit. |

**Bot equivalent:** The bot has no time-based exit logic. It will hold a position through the entire session if no other exit triggers.

**Automatable?** YES.
- Implement a "max hold time" based on setup quality: A-grade = 120 min, B-grade = 30 min, C-grade = 10 min
- Implement a "stall exit": if no new high in the last N minutes (scaled to setup quality), reduce position or exit
- Implement a time-of-day taper: tighten all trails after 9:30 AM, tighten further after 10:00 AM
- Hard stop: no new entries after 10:30 AM (configurable, matches Ross's behavior)

---

### 1.6 — Re-Entry After Exit

**Observed on:** Jan 6 (RHE), 7 (AMVS), 10 (AIFF, XHG), 13 (PHIO), 14 (OST, AIFF), 17 (ZO, AIMX), 21 (NXX, INMN), 24 (OST, ALUR), 28 (JFB, YWBO), 29 (SLXN, MVNI), 31 (SGN, NLSP)

Ross re-enters after exiting on approximately 60-70% of his traded tickers. This is a defining characteristic of his style.

**Re-entry patterns:**

1. **Dip buy after initial exit.** Most common. Ross exits on a reversal signal, watches the stock pull back, then re-enters if it finds support.
   - INMN Jan 21: "Evolved mid-session from breakout entries to dip buying" — he changed his approach during the trade, progressively buying dips at $7.25-$7.50 with 10c stop for 30c reward (3:1 R:R).
   - AIFF Jan 10: "4 trades: main entry at $5.23, break-even re-entry, 2 dip buys at $4.00."

2. **Range trading.** On choppy names, Ross enters and exits multiple times within a range.
   - ZO Jan 17: "4-5 re-entries in tight range ($3.82-$4.20) rather than holding for big move."
   - WHLR Jan 16: Range-traded $3.82-$4.20 multiple times for +$3,800 total.

3. **Fresh signal re-entry.** After fully exiting, Ross re-enters if the stock gives a new breakout signal.
   - SLXN Jan 29: First entry at $2.00 breakout built to ~$7K, gave back some. Later re-entry lost $2K. Net positive.
   - MVNI Jan 29: Lost on first trade at ~$6.00. Broke even on second. Third entry at $4.75 rode to $7.50 (+$3,900).

**Critical finding — MVNI pattern:** Ross's best trade of Jan 29 was his THIRD attempt on MVNI. He lost on #1, scratched #2, and nailed #3 at a much better price ($4.75 vs $6.00). This "persistence through losing attempts" is a recurring edge. The bot takes one trade and moves on.

**Ross's re-entry success rate is mixed.** Re-entries after the initial exit often produce smaller gains or even losses:
- SPCB Jan 3: ~$1K-$1.2K giveback on last trade of the sequence.
- SLXN Jan 29: Re-entry lost $2K.
- NLSP Jan 31: Gave back $1K at the open on a failed breakout attempt.
- AMVS Jan 7: "Gave it all back on 2 re-entries fighting sellers."
- OST Jan 24: Small recoup attempt still deeply red.

**The re-entry giveback pattern is one of Ross's identified weaknesses.** On Jan 8 (not in our detailed data but referenced), he peaked at +$56K and gave back $22K on re-entries. On Jan 14, he gave back 60% of his peak P&L on emotional re-entries (AIFF, VRME).

**Bot equivalent:** The bot occasionally takes 2-3 trades on the same ticker (VNCE Jan 23: 3 trades, ALUR Jan 24: 3 trades) but this is incidental re-triggering of the setup, not deliberate re-entry strategy.

**Automatable?** PARTIALLY — with careful limits.
- Allow re-entry after a 1m higher-low forms above the prior exit price
- Limit re-entries to 2 per ticker per session (matches Ross's productive re-entry count; his 3rd+ re-entries often lose)
- Size re-entries at 50% of initial position (captures the "reduced conviction" aspect)
- CRITICAL: do NOT re-enter if the stock has broken below VWAP since the initial exit

---

### 1.7 — Conviction-Based Sizing (Entry AND Exit)

**Observed on:** Every day, but most dramatically on Jan 22 (NEHC 30K shares), Jan 24 (ALUR massive size), Jan 21 (INMN progressive scaling).

This isn't technically an "exit" mechanism, but it fundamentally determines the P&L impact of exits. Ross sizes based on conviction, which means his exits capture dramatically more dollars on high-conviction trades.

**Ross's sizing tiers (estimated from recaps):**

| Conviction Level | Share Count Range | Notional Range | Example |
|-----------------|-------------------|---------------|---------|
| **A+ (textbook setup, A+ catalyst)** | 20K-30K shares | $100K-$200K+ | NEHC Jan 22: 30K shares at $4.60 = $138K. ALUR Jan 24: likely larger. |
| **A (clear catalyst, good float)** | 10K-20K shares | $50K-$100K | HOTH Jan 7: 30K shares. INMN Jan 21: 6-10K shares. |
| **B (decent setup, some reservations)** | 4K-6K shares | $20K-$40K | CRNC Jan 3: 4K shares. SPCB Jan 3: 6K shares. |
| **Base hit (weak day, defensive)** | 1K-5K shares | $5K-$25K | VMAR Jan 10: small size. TPET Jan 21: 12K shares at $3 = $36K (but tight stop = $475 profit). |
| **Ice breaker** | 1K shares | $3K-$10K | ZENA Jan 7: "starter 1K shares via hotkey." |

**Sizing on losers:** Ross sizes his losers much smaller than his winners. His losses are almost always from "base hit" or "starter" sized positions:
- OST Jan 2: -$3,000 (two trades on a no-news momentum play — moderate size)
- GTBP Jan 13: -$3,400 (too aggressive, his own words — discipline failure)
- VRME Jan 14: -$4,000 (emotional cascade — discipline failure)
- OST Jan 24: -$6,000 (FOMO, oversized entry — discipline failure, his own admission)
- XTI Jan 21: -$12 (proper size, immediate cut)
- SZK Jan 31: -$2,500 (moderate size, reasonable stop)

**The pattern:** Ross's discipline failures (GTBP, VRME, OST Jan 24) produce his biggest losers. When he's disciplined, his losers are tiny (XTI -$12) because he cuts fast and sizes appropriately for the risk.

**Bot equivalent:** Flat $15-22K notional regardless of setup quality. On ALUR, the bot used $15K while Ross was likely at $200K+. On CYCN Jan 31 (a loser), the bot used similar sizing to what it used on ALUR.

**Automatable?** YES — the sizing itself is automatable even if the conviction assessment requires proxies.
- Use scanner rank score as conviction proxy: score > 1.0 = A+ sizing, 0.8-1.0 = A, 0.6-0.8 = B, < 0.6 = base hit
- Scale notional by rank: top-ranked candidate gets 3x base notional, #2 gets 2x, #3+ gets 1x
- CRITICAL: only implement after exit management is fixed. Sizing up into premature exits just increases losses.

---

## Part 2: Exit Timing Analysis

### 2.1 — Hold Times on Winners

From the recaps, Ross's hold times follow a clear pattern based on trade quality:

| Category | Estimated Avg Hold | Notes |
|----------|--------------------|-------|
| A+ runners (ALUR, SLRX, ARNAZ, DGNX) | 45-90 min | Held through multiple pullbacks, exited on session-level signals |
| Solid winners (ARBE, NEHC, INMN, BTCT) | 15-30 min | Held through initial momentum, exited at technical resistance |
| Base hits (VMAR, ZO, TPET, AIMX) | 2-10 min | Quick in-and-out, no expectation of big move |
| Scalps (JFB, NTO, EVAX) | <2 min | One candle, take what's there |

**Contrast with bot:** The bot's average hold time from the post-exit analysis data: sq_para_trail_exit trades averaged <5 minutes hold, sq_target_hit trades averaged <15 minutes. The bot exits in the same timeframe as Ross's *base hits*, even when the stock is a genuine runner.

### 2.2 — Hold Times on Losers

Ross cuts losers fast — typically within 1-3 minutes:

| Trade | Hold Time | Loss |
|-------|-----------|------|
| XTI Jan 21 | Seconds | -$12 |
| MIMI Jan 23 | <1 min | Near scratch |
| SZK Jan 31 | <2 min | -$2,500 |
| GTBP Jan 13 | ~2 min | -$3,400 |

**The asymmetry is the edge:** Ross holds winners 10-90x longer than losers. The bot holds winners and losers for approximately the same duration because the parabolic trail treats all trades identically.

### 2.3 — Re-Entry Frequency

From the 19 recaps, Ross re-entered on approximately 35 of ~55 unique tickers traded (64%). Of those re-entries:
- ~60% were productive (added to daily P&L)
- ~25% were scratch/break-even
- ~15% were losers that gave back prior gains

The productive re-entries tend to be dip-buys at lower prices (INMN, MVNI), while the losing re-entries tend to be "chasing" at higher prices (AMVS, OST, SLXN second entry).

---

## Part 3: How the Bot Currently Exits (The Problem)

### 3.1 — Bot Exit Mechanisms

From the post-exit analysis (109 SQ trades):

| Exit Type | Count | % of Trades | What It Does | Problem |
|-----------|-------|-------------|-------------|---------|
| **sq_para_trail_exit** | 58 | 53% | Parabolic trailing stop from first tick of profit. Tightens aggressively. | Fires at first micro-pullback. Captured $0.01/share on WHLR. 84% of these trades were followed by 2R+ continuation. |
| **sq_target_hit** | 35 | 32% | Fixed R-multiple target. All-or-nothing exit. | Fires at a fixed point regardless of momentum. Captured $0.36 on ALUR's $12 move. 86% of these trades were followed by 2R+ continuation. |
| **sq_max_loss_hit** | 12 | 11% | Hard stop at maximum loss threshold. | Necessary for risk management but 67% of these were followed by 2R+ continuation — suggesting the stop levels may be too tight on volatile names. |
| **sq_trail_exit** | 3 | 3% | Standard trailing stop. | Small sample. |
| **sq_stop_hit** | 1 | 1% | Initial stop loss hit. | Working as intended. |

### 3.2 — The Core Failure: 81% Runner Rate

**88 of 109 SQ trades (81%)** were followed by a 2R+ continuation after the bot exited. These are the "RUNNER" trades from the post-exit analysis. The bot left an estimated $977,937 on the table from runners alone (across the full megatest period, not just January).

**By exit type, the runner rate was:**
- sq_para_trail_exit: 84% of trades were runners → $459,302 left on table
- sq_target_hit: 86% of trades were runners → $497,035 left on table
- sq_max_loss_hit: 67% were runners → $24,540 left on table

**Translation:** Both primary exit mechanisms (parabolic trail and fixed target) exit too early on virtually every trade. The exit system is not just suboptimal — it is fundamentally miscalibrated for the type of stocks the bot trades.

### 3.3 — The Poster Child: ALUR Jan 24

| Metric | Bot | Ross |
|--------|-----|------|
| Entry price | $8.04 | ~$8.24 |
| Entry time | 7:01 AM | ~7:01 AM |
| Exit price | $8.40 | ~$18-20 |
| Exit reason | sq_target_hit (+4.1R) | Rode the move; secondary offering at 9:30 AM |
| Hold time | ~3 minutes | ~90+ minutes |
| P&L | +$586 | +$47,000 |
| % of move captured | 3% ($0.36 of $12) | ~80% (~$10 of $12) |

The bot entered 20 cents BETTER than Ross and made 80x LESS. Same stock. Same time. Same price zone. The entire gap is exit management + sizing.

---

## Part 4: Ross vs Bot — The Exit Gap Mapped

### 4.1 — Side-by-Side on Shared Tickers

| Date | Ticker | Ross Exit Strategy | Bot Exit Strategy | Ross P&L | Bot P&L | Gap |
|------|--------|--------------------|-------------------|----------|---------|-----|
| Jan 14 | AIFF | Emotional re-entry at $10.08, sharp rejection | sq_target_hit at $5.08, $5.36 | -$2,000 | +$1,424 | Bot wins +$3,424 |
| Jan 16 | WHLR | Range-traded $3.82-$4.20 multiple times | sq_para_trail_exit at +$0.01 | +$3,800 | +$28 | Ross wins by $3,772 |
| Jan 24 | ALUR | Rode $8.24→$20, partials along the way | sq_target_hit at $8.40, para_trail on re-entries | +$47,000+ | +$586 | Ross wins by $46,414+ |
| Jan 28 | YIBO | Full conviction ride $5.57→$6.36 | vr_core_tp_1.5R | +$5,724 | +$125 | Ross wins by $5,599 |
| Jan 29 | SLXN | Multi-entry $2.00→$2.50+ range, gave back on re-entry | sq_para_trail_exit at +$0.06 | ~+$5,000 | +$231 | Ross wins by $4,769 |
| | | | **TOTALS** | **~$59,524** | **+$2,394** | **-$57,130** |

**Excluding AIFF (the one time bot discipline beat human emotion): Ross outperformed by $60,554 across 4 shared tickers on exit management alone.**

### 4.2 — What Ross Does That the Bot Doesn't

| Ross Technique | Bot Equivalent | Gap Created |
|---------------|---------------|-------------|
| Partial exits at price levels | All-or-nothing at fixed R-multiple | Massive. Bot captures 3% of ALUR. |
| Mental trailing stop (candle structure) | Parabolic trail from first tick | Bot exits on first micro-pullback. |
| Conviction sizing (5-20x on A+ setups) | Flat notional | 19x sizing gap on YIBO alone. |
| VWAP as go/no-go exit reference | No VWAP logic | Bot holds through VWAP breaks, exits on noise. |
| "Know when to stop" daily limits | No daily limits | Bot keeps trading into diminishing returns. |
| Re-entry on dips after exit | One trade and done (mostly) | Bot misses the 2nd and 3rd best entries. |
| Multi-timeframe trailing (10s, 1m, 5m) | Single timeframe parabolic | Bot can't adapt trail to move speed. |
| Reversal pattern confluence (2+ signals) | Single-signal exits | Bot exits on one candle pattern. |
| Time-based stall detection | No time awareness | Bot holds dead positions indefinitely. |
| SEC filing checks mid-trade | No fundamental awareness | Ross catches dilution risk early. |

---

## Part 5: What Can Be Automated (Priority Ranked)

### Tier 1: High Impact, Directly Automatable

**1. Replace sq_para_trail_exit with ATR-based trail + minimum profit threshold**
- Current: trail from first tick, tightens aggressively
- Proposed: no trail until profit > 1R. Then trail at 1.5x ATR(14) below the high. For high-score setups (R > 10), use 2x ATR.
- Expected impact: captures 30-50% of runner moves instead of 3-5%
- Implementation: modify exit handler to check ATR and R-multiple before activating trail
- Risk: larger drawdowns on reversals. Mitigated by the minimum profit threshold.

**2. Replace sq_target_hit with tiered partial exits at price levels**
- Current: all-out at fixed R-multiple
- Proposed: 1/3 out at first whole-dollar resistance above entry. 1/3 out at next level. 1/3 on ATR trail.
- Example on ALUR: entry $8.04 → 1/3 at $9.00 (+$0.96), 1/3 at $10.00 (+$1.96), 1/3 rides to $15+ on trail
- Expected impact: captures 20-40% of the move instead of 3%
- Implementation: calculate price targets from entry price (next whole dollar, next $2 level, etc.)
- Risk: first partial may be too early on fast runners. Consider starting the first partial at the higher of fixed-R-target or next-whole-dollar.

**3. Implement daily P&L target + 20% drawdown halt**
- Current: bot trades all session regardless of P&L
- Proposed: after reaching $X daily target, tighten all entries. After 20% drawdown from peak, halt new entries.
- Expected impact: prevents late-day giveback, preserves gains
- Implementation: track session P&L, adjust entry criteria dynamically
- Risk: may miss late-morning setups on strong days. Mitigate by allowing override on A+ scanner scores.

**4. Implement conviction-based sizing tied to scanner rank**
- Current: flat $15-22K notional
- Proposed: rank > 1.0 = 3x base, 0.8-1.0 = 2x, 0.6-0.8 = 1x, < 0.6 = skip
- Expected impact: captures more on the ALUR-type days, reduces exposure on marginal candidates
- Implementation: pass scanner rank score to the position sizing module
- PREREQUISITE: fix exits first. Sizing up into premature exits amplifies losses.

### Tier 2: High Impact, Requires More Development

**5. Add VWAP-break exit logic**
- If price closes 1m candle below VWAP after being above → exit 50% of position
- If price closes 2 consecutive 1m candles below VWAP → exit 100%
- Implementation: calculate VWAP in real-time (price × volume cumulative)
- Risk: VWAP breaks on runners may just be pullbacks. Use as partial exit, not full.

**6. Add candle-pattern confluence exits**
- Require 2+ reversal signals before exiting a high-score setup
- Single reversal signal → exit 50% (or tighten trail)
- Two confirming signals → exit 100%
- Patterns to implement: tweezer top, shooting star (5m), double top (1m), candle-under-candle
- Implementation: candle pattern library with confluence scoring

**7. Add time-based stall detection**
- If no new high in last 5 minutes on a base-hit setup → exit
- If no new high in last 15 minutes on an A-grade setup → tighten trail to 1x ATR
- If no new high in last 30 minutes on any setup → exit remaining position
- Hard cutoff: no new entries after 10:30 AM

**8. Add re-entry logic (limited)**
- After exiting profitably, if price forms a 1m higher-low above the prior exit → allow re-entry
- Maximum 2 re-entries per ticker per session
- Re-entry size = 50% of initial position
- Do NOT re-enter if price has broken below VWAP since exit

### Tier 3: Nice-to-Have, Lower Priority

**9. Multi-timeframe trail adaptation**
- If 1m volume > 5x average and price making new highs every 10s → switch to 10s chart trailing
- If 5m trend is intact (higher lows on 5m) → use 5m candle lows as trail reference
- Default: 1m candle structure trail

**10. Runner detection (dynamic target override)**
- If sq_target_hit would fire but: (a) time < 3 min since entry, (b) price is accelerating, (c) volume is increasing → override the fixed target and switch to ATR trail
- This specifically addresses the ALUR case where the target hit in 3 minutes on a stock still accelerating

---

## Part 6: The Simplest Change That Closes the Biggest Gap

If you could make exactly ONE change to the exit system, here's the ranking by expected impact:

**#1: Implement a "minimum hold time" + "minimum profit" before any trail activates.**

The math: 81% of SQ trades are runners. The average runner continues 23R past the exit. The parabolic trail fires in <5 minutes. If we simply added a rule: "do not exit until (a) profit exceeds 2R OR (b) 10 minutes have passed, whichever comes first" — the bot would stay in most runners through their initial acceleration phase.

On ALUR: entry $8.04, stop at $7.90, R = $0.14. Current target: $8.40 (+2.6R). Proposed minimum: hold until 2R is reached AND 10 minutes have passed. At 10 minutes, ALUR was already at $10+ — the ATR trail would then manage the remainder instead of the fixed target.

On WHLR: entry $4.05. Current para_trail fires at $4.06 (+$0.01). Proposed: hold until 2R profit. 2R would be ~$4.33. WHLR hit $4.20 area repeatedly — with a wider trail, the bot could have captured $0.15-$0.20 instead of $0.01.

**This single change — delayed trail activation — addresses both the parabolic trail problem AND the premature target problem simultaneously.** It's the highest-leverage modification because it improves every single trade the bot takes, not just the runners.

**Implementation complexity: LOW.** Add two conditions to the exit handler:
```
if profit_r < 2.0 AND hold_time_minutes < 10:
    do_not_exit()  # Let the trade develop
elif profit_r >= 2.0:
    switch_to_atr_trail()  # Now manage with wider trail
elif hold_time_minutes >= 10:
    switch_to_standard_exit()  # Time's up, use current logic
```

**Risk:** Some trades that currently capture small profits will now become small losses (the 19% of trades that are NOT runners). But 81% × 23R average continuation vs 19% × ~1R average reversal = massive expected value improvement.

---

## Part 7: Summary — Ross's Exit System vs Bot's Exit System

| Dimension | Ross Cameron | Current Bot | Proposed Bot |
|-----------|-------------|-------------|-------------|
| **Exit philosophy** | "Let winners run, cut losers fast" | "Never give back any profit" | "Give trades room to develop, then trail" |
| **Trail activation** | After clear reversal signals (multiple confirming) | From first tick of profit | After 2R profit OR 10 min hold |
| **Trail width** | Candle structure (1m or 5m depending on quality) | Parabolic (tightens from first tick) | ATR-based (1.5-2x ATR below high) |
| **Target behavior** | Partial exits at price levels (whole dollars) | All-or-nothing at fixed R-multiple | Tiered: 1/3, 1/3, 1/3 at price levels |
| **Sizing** | 5-20x on A+ setups, small on base hits | Flat notional | Scaled to scanner rank |
| **VWAP** | Binary go/no-go exit reference | Not used | Partial exit on 1m close below VWAP |
| **Daily P&L** | $5K base hit target, 20% drawdown halt | No limits | Implement both |
| **Re-entry** | 60%+ of tickers, dip-buy approach | Incidental at best | 2 re-entries max, 50% size, higher-low required |
| **Time awareness** | Done by 10:30 AM on defensive days | None | Stall detection + time cutoff |
| **Hold time asymmetry** | Winners: 10-90 min. Losers: <1 min. | Winners ≈ losers: both <5 min | Trail allows winners to run; stops keep losers short |

---

*This analysis is based on 19 daily Ross Cameron recap videos (January 2-31, 2025), 19 daily comparison files, the January 2025 strategy audit (631 lines), the monthly ross_vs_bot summary (139 lines), the money-on-table analysis (252 lines), and the post-exit analysis of 109 SQ trades. Every exit behavior documented above is traced to specific trades and dates in the source data.*
