# Exit Strategy Cross-Reference: Recap Analysis vs. Video Analysis

**Generated:** 2026-03-22
**Sources:**
- `ross_exit_analysis.md` — Reverse-engineered from 19 daily recaps (Jan 2–31, 2025)
- `ross_exit_video_analysis.md` — Perplexity deep dive on Ross Cameron's "STOP Selling Your Winners Too Soon!" (May 10, 2025) video, including full gap analysis and implementation notes
**Purpose:** Unify both data sources into a single actionable document. Identify what we got right, what we missed, and the correct implementation priority.

---

## 1. What We Got RIGHT from the Recaps

Our recap analysis (ross_exit_analysis.md) identified six major Ross exit behaviors. Here's how each holds up against what the video confirms:

### 1A. Partial Exits at Price Levels — CONFIRMED ✅

**Recap said:** Ross scales out at whole-dollar and half-dollar resistance. First partial 25-50% at first clean resistance, second partial at next level, remainder on trail. He thinks in price levels, not R-multiples. (Section 1.2, observed on 10+ tickers: ARBE, SLRX, INMN, ALUR, SGN, etc.)

**Video confirms:** Ross does not use R-multiple targets. He holds until candle signals fire, taking partials at natural resistance. The video goes further — the specific candle signals that trigger each partial are now defined (see Section 2 below).

**Assessment:** We correctly identified the behavior but lacked the specific candle-signal triggers for each partial tier.

### 1B. Candle-Structure Trailing — CONFIRMED ✅ (with critical timeframe correction)

**Recap said:** Ross uses "mental trailing stop anchored to candle structure." He trails using 1m candle bodies, not wicks. Two consecutive candle bodies closing lower = exit. (Section 1.3)

**Video confirms:** Yes, but with a critical specificity we missed — the primary signal is **Candle Under Candle (CUC)**: the first 1-minute candle making a new low vs. the prior candle's low. This is THE confirmed exit, not just "two consecutive lower closes." Additionally, **the 10s chart is for entry only** — all exit candle reading happens on 1m.

**Assessment:** We got the concept right but missed the precise signal definition and the critical timeframe rule.

### 1C. VWAP as Go/No-Go — CONFIRMED ✅

**Recap said:** Ross uses VWAP as a binary filter. Above VWAP = bullish, below VWAP = bearish. VWAP break = "thesis is broken" exit. (Section 1.4C, observed on RHE Jan 6, OSTX Jan 15, VSS Jan 17)

**Video confirms:** VWAP remains a key reference. The video doesn't contradict our recap finding here.

**Assessment:** Correct as documented. Implementation recommendation (1m close below VWAP → partial, 2 consecutive closes → full exit) stands.

### 1D. Multi-Timeframe Management — PARTIALLY CONFIRMED ⚠️

**Recap said:** Ross uses 10s for fast movers, 1m for standard, 5m for wider moves. He switches between timeframes based on move speed. (Section 1.3, points 3-4)

**Video reveals the CRITICAL DISTINCTION we missed:** 10s is for ENTRY only. 1m is for EXIT management. 5m is for trend confirmation. Our recap correctly observed that Ross uses multiple timeframes but did not identify the directional rule: timeframes go UP after entry, never back down to 10s for exits.

**Assessment:** We observed the behavior correctly but misidentified the purpose of each timeframe. This is the #1 finding — see Section 2.

### 1E. Re-Entry Patterns — CONFIRMED ✅

**Recap said:** Ross re-enters on ~64% of tickers. Dip buys at lower prices are productive; chasing at higher prices loses. Max 2 productive re-entries per ticker. (Section 1.6)

**Video confirms:** The video focuses on exit management rather than re-entry, but nothing contradicts our recap findings.

**Assessment:** Correct. Our recommendation (2 re-entries max, 50% size, higher-low required, no re-entry below VWAP) is sound.

### 1F. Confluence Requirement for Exits — CONFIRMED ✅ (with new specificity)

**Recap said:** Ross uses MULTIPLE confirming signals, not just one. PHIO exit example: "1m double top + topping tail" AND "5m shooting star + candle-under-candle." (Section 1.4A)

**Video adds:** A specific hierarchy of signals with defined actions — not all signals are equal. Some warrant 50% exits, others 100%. CUC is the only "confirmed" full exit. See Section 2 for the hierarchy.

**Assessment:** We got the concept right. The video provides the specific signal-to-action mapping we needed.

---

## 2. What the Video Reveals That We MISSED

These are findings from the video analysis that were either absent from or insufficiently captured in our recap analysis. Ordered by impact.

### 2A. CRITICAL: 10-Second vs 1-Minute Timeframe for Exits

**What we had:** Our recap analysis (Section 1.3) noted that Ross uses 10s charts for fast movers and mentioned "10s chart micro-pullback entry" on AIFF, ARBE, OSTX. We documented this as a trailing technique.

**What the video reveals:** Ross explicitly states the 10s chart is for **ENTRY ONLY**. After entering, he switches to the 1-minute chart for all exit management. He never exits based on 10-second candle patterns.

**Why this is critical:** Our bot fires breakeven (BE) exits and topping wicky (TW) exits on 10-second bars. This means every single exit signal the bot generates from candle patterns is being read on the WRONG TIMEFRAME. A "topping wicky" on a 10-second bar is noise — it's a micro-fluctuation inside a single 1-minute candle that might be perfectly healthy.

**This is probably the #1 cause of premature exits.** A 10-second bar that looks like a reversal is often just a wick on the 1-minute candle. The bot sees danger where Ross sees normal price action within a healthy move.

**Impact estimate:** If we switch candle-pattern exits from 10s to 1m, most of the sq_para_trail_exit trades (53% of all exits, 84% runner rate) would hold significantly longer because the "reversal" patterns they triggered on wouldn't exist on the 1m timeframe.

### 2B. CRITICAL: Candle Under Candle (CUC) as THE Primary Exit Signal

**What we had:** Our recap analysis (Section 1.4A) listed "candle-under-candle" as one of six candle patterns Ross uses, observed on PHIO Jan 13. We described it as "current candle's high below prior candle's low."

**What the video reveals:** CUC isn't just one pattern among six — it is THE confirmed exit signal. Ross's exit decision tree is:

1. Warning signals (doji, gravestone, shooting star) → consider partial or full exit
2. CUC on 1-minute chart → confirmed exit, no ambiguity

This specific signal — first 1m candle making a new low vs. prior candle's low — does NOT exist as a defined exit condition in our codebase. We have `bearish_engulfing_exit_full` and `topping_wicky_exit_full`, but neither matches the CUC definition precisely.

**Difference from bearish engulfing:** Bearish engulfing requires the current candle's BODY to fully engulf the prior candle's body. CUC only requires the current candle to make a new LOW below the prior candle's low. CUC is a less restrictive condition (fires more often) but on the 1m timeframe it's the appropriate sensitivity.

### 2C. CRITICAL: Specific Candle Signal Hierarchy

**What we had:** Our recap listed candle patterns (tweezer top, shooting star, double top, topping tail, candle-under-candle, bearish engulfing) as exit triggers and noted that Ross requires confluence. (Section 1.4A)

**What the video reveals:** A specific hierarchy with defined partial exit percentages:

| Signal | Action | Timeframe |
|--------|--------|-----------|
| **Doji** | 50% exit (warning, not confirmed reversal) | 1m |
| **Gravestone Doji** | 100% exit (strong reversal signal) | 1m |
| **Shooting Star** | 100% exit (strong reversal signal) | 1m |
| **CUC (Candle Under Candle)** | 100% confirmed exit (THE exit) | 1m |
| **Bearish Engulfing** | 100% exit | 1m |
| **Tweezer Top** | Tighten trail / prepare to exit | 1m |

**Key insight:** Not all candle patterns are equal. A doji is a WARNING — take half off. A gravestone doji or shooting star is an EXIT — take everything. CUC is CONFIRMATION — if you're still in, get out now. Our bot treats all candle patterns as binary full-exit triggers, which is wrong in both directions: too aggressive on warnings (doji), appropriately aggressive on confirmed signals (but on the wrong timeframe).

### 2D. MACD Negative as Hard Backstop

**What we had:** MACD is not mentioned anywhere in our recap analysis. Not in the exit framework, not in the reversal signals table, not in the automatable recommendations.

**What the video reveals:** Ross explicitly says there is "no scenario where I should still be holding" if MACD goes negative. This is a hard backstop — regardless of candle patterns, price levels, or any other signal, MACD going negative means exit everything.

**Why we missed it:** The recaps don't typically mention indicator values. Ross talks about price action and candle patterns in his commentary, but MACD is a background check he runs constantly without always verbalizing it. The video, being instructional rather than recap, reveals the full decision framework including the indicators he monitors silently.

**Implementation:** Check MACD(12,26,9) on the 1-minute chart. If the MACD line crosses below the signal line into negative territory, exit 100% of position immediately. No partials, no trail — hard exit.

### 2E. 20 EMA Break as Hard Exit

**What we had:** Our recap mentions "200 EMA as daily chart resistance" (Section 1.4D, Jan 13) as a price level reference. The 20 EMA is not mentioned.

**What the video reveals:** Ross uses the 20 EMA (on the 1-minute chart) as a hard exit line. If price breaks below the 20 EMA on the 1m chart, exit.

**Implementation:** Calculate 20 EMA on 1m bars. If price closes below 20 EMA → exit remaining position. This works as a complementary signal to CUC — often CUC and 20 EMA break will fire together, providing the confluence Ross requires.

### 2F. Stall Timer is Anti-Ross

**What we had:** Our recap analysis (Section 1.5) recommended implementing a stall exit: "if no new high in the last N minutes, reduce position or exit." We proposed 5 minutes for base hits, 15 minutes for A-grade, 30 minutes for any setup.

**What the video reveals:** Ross explicitly HOLDS through consolidation and sideways action. His reasoning: after a squeeze leg, consolidation is normal, and the next leg could be massive. Exiting during consolidation means missing the second (often larger) move.

**This directly contradicts our stall timer recommendation.** The stall timer would kill trades during the exact consolidation periods that precede Ross's biggest moves. ALUR consolidated multiple times between $8 and $20. SLRX stair-stepped with pauses at each whole dollar. ARNAZ consolidated between halt levels.

**Resolution:** The stall timer should either be removed entirely or transformed into something much more nuanced — perhaps only firing if consolidation occurs BELOW VWAP or BELOW the 20 EMA, which would indicate the move is truly dying rather than just pausing.

### 2G. Fixed R Targets Are Fundamentally Wrong for Squeezes

**What we had:** Our recap analysis (Section 1.2) noted that "Ross's partials are at PRICE LEVELS, not R-multiples" and proposed replacing sq_target_hit with tiered partials. We identified this correctly.

**What the video adds:** A specific illustration of why R-targets fail on squeezes. Consider: stock at $3.00, risk (R) = $0.20. A 2R target exits at $3.40. If the stock squeezes to $8.00, the bot exits at $3.40 and misses $4.60 of move — capturing 8% of the total move. Ross doesn't use R-multiple targets at all. He holds until candle signals (doji, CUC, etc.) fire on the 1-minute chart.

**Why this matters for our "simplest change" recommendation:** Our Part 6 in the recap analysis recommended a "minimum hold time + minimum profit before trail activates" as the single highest-leverage change. The video analysis suggests this is still too conservative — the minimum profit should not be measured in R-multiples at all. Instead, the trail should activate based on CANDLE SIGNALS, not profit thresholds.

---

## 3. What We're Doing RIGHT (Confirmed by Video)

These existing bot behaviors are validated by the video analysis:

| Bot Feature | Status | Notes |
|-------------|--------|-------|
| **Hard stop at pattern low** | ✅ Correct | Ross uses the pattern low / candle low as his hard stop. Our stop placement is sound. |
| **Bearish engulfing detection** | ✅ Concept correct, ⚠️ wrong timeframe | We detect this pattern, but on 10s bars. Needs to move to 1m. |
| **Topping wicky detection** | ✅ Concept correct, ⚠️ wrong timeframe | Same issue — correct pattern, wrong timeframe. |
| **Parabolic grace period** | ✅ Correct concept | Giving parabolic moves room to run aligns with Ross's approach. The issue is the grace period ends and the tight trail kicks in. |
| **Continuation hold** | ✅ Correct | Recognizing and holding through continuation patterns is Ross-aligned. |
| **VWAP loss on squeeze** | ✅ Correct | VWAP break as an exit condition matches Ross's go/no-go framework. |
| **Bail timer** | ✅ Correct | A maximum hold time for trades that never work is appropriate — Ross cuts dead trades fast. |
| **Max loss cap** | ✅ Correct | Ross has a hard max loss discipline. Our implementation is sound. |

**The pattern:** Our ENTRY-side logic and RISK MANAGEMENT are largely correct. The problem is concentrated in PROFIT-TAKING and TRAIL MANAGEMENT — specifically, we exit winners too aggressively because we're reading signals on the wrong timeframe with the wrong signal hierarchy.

---

## 4. The UNIFIED Priority List

Merging the recap-based recommendations (ross_exit_analysis.md Part 5) with the video-based priorities into a single implementation plan.

### Priority 1: Fix the Foundation (Do These First — Nothing Else Works Without Them)

**1A. Switch all candle-pattern exit signals from 10s to 1m timeframe**
- Source: Video analysis (Section 2A above)
- Recap alignment: Our Section 1.3 mentioned multi-timeframe but didn't identify this specific mismatch
- Impact: Affects 100% of candle-based exits (topping_wicky, bearish_engulfing, and any future candle patterns)
- Implementation: Change the timeframe parameter on all candle-pattern exit evaluators from 10s to 1m bars
- Risk: LOW — this is correcting a fundamental miscalibration, not adding new logic
- **This is THE prerequisite for everything else. No point adding new exit patterns on the wrong timeframe.**

**1B. Implement Candle Under Candle (CUC) as primary confirmed exit on 1m**
- Source: Video analysis (Section 2B above)
- Recap alignment: Our Section 1.4A listed CUC but didn't elevate it as THE primary signal
- Implementation: New exit condition — if current 1m candle's low < prior 1m candle's low, fire CUC exit
- This replaces the parabolic trail as the primary profit-taking mechanism on the 1m timeframe
- Risk: LOW — well-defined, mechanical signal

### Priority 2: Add the Missing Hard Backstops

**2A. Add MACD negative as hard exit**
- Source: Video analysis (Section 2D above)
- Recap alignment: Not mentioned in recap at all — completely new
- Implementation: MACD(12,26,9) on 1m chart. If MACD line crosses below zero → exit 100%
- Risk: LOW — mechanical indicator check, no ambiguity

**2B. Add 20 EMA break as hard exit**
- Source: Video analysis (Section 2E above)
- Recap alignment: Not identified in recap (we only had 200 EMA on daily)
- Implementation: 20 EMA on 1m chart. If price closes 1m candle below 20 EMA → exit remaining position
- Risk: LOW — may fire during brief dips on strong runners. Consider requiring 20 EMA break + one other signal for high-score setups.

**2C. Implement VWAP-break exit logic**
- Source: Both recap (Section 1.4C) and video
- Implementation: 1m close below VWAP → exit 50%. Two consecutive 1m closes below VWAP → exit 100%
- This was already in our Tier 2 recommendations — elevated here because it provides a confirmed framework backstop

### Priority 3: Implement the Signal Hierarchy

**3A. Implement the candle signal hierarchy with appropriate partial percentages**
- Source: Video analysis (Section 2C above)
- Recap alignment: Our Section 1.4A identified the patterns but not the specific partial %s
- Implementation:
  - Doji on 1m → exit 50% of position
  - Gravestone Doji on 1m → exit 100%
  - Shooting Star on 1m → exit 100%
  - CUC on 1m → exit 100% (confirmed)
  - Bearish Engulfing on 1m → exit 100%
- Requires: candle pattern classification on 1m bars (doji vs gravestone vs shooting star)

**3B. Replace fixed R targets with candle-signal-based exits**
- Source: Both recap (Section 1.2) and video (Section 2G above)
- Recap alignment: We recommended tiered partials at price levels. Video says even that's too mechanical — let candle signals drive it.
- Proposed hybrid: Use price levels (whole dollars) as PARTIAL exit triggers (take 1/3), but let candle signals on 1m drive the FULL exit
- This replaces sq_target_hit entirely

### Priority 4: Remove/Fix Counter-Productive Logic

**4A. Remove or radically rework the stall timer**
- Source: Video analysis (Section 2F above)
- Recap alignment: Our Section 1.5 RECOMMENDED a stall timer — the video says this is anti-Ross
- Resolution: Remove the stall timer for squeeze trades. Alternatively, only fire stall exit if the consolidation is occurring BELOW VWAP and BELOW 20 EMA (indicating the move is dead, not pausing)

**4B. Widen or remove the parabolic trail**
- Source: Both recap (Section 1.3) and video
- The parabolic trail from first tick of profit is the single most damaging exit mechanism. Once 1A is implemented (1m candle exits), the parabolic trail becomes redundant — CUC on 1m IS the trail.
- Keep the parabolic trail only as an emergency backstop with a VERY wide setting (e.g., 3x ATR), not as the primary exit mechanism

### Priority 5: Layer On Enhancements (After Foundation Is Solid)

**5A. Implement tiered partial exits at price levels**
- Source: Recap Section 1.2
- 1/3 at first whole-dollar above entry, 1/3 at next level, 1/3 on candle-signal trail

**5B. Implement conviction-based sizing**
- Source: Recap Section 1.7
- PREREQUISITE: Fix exits first (Priorities 1-4). Sizing up into premature exits amplifies losses.

**5C. Implement daily P&L target + 20% drawdown halt**
- Source: Recap Section 1.1
- Sound risk management, independent of exit mechanics

**5D. Implement re-entry logic**
- Source: Recap Section 1.6
- 2 re-entries max, 50% size, higher-low required, no re-entry below VWAP

**5E. Add candle-pattern confluence requirement for high-score setups**
- Source: Recap Section 1.4A
- For setups with R-score > 10, require 2+ confirming signals before full exit

---

## 5. The Key Realization

Our earlier "Item 3" attempt at improving exits — adding partial exits, widening the trail, and implementing runner detection — failed. This cross-reference reveals WHY.

**We were building on the wrong foundation.**

The bot reads candle patterns on 10-second bars. Every improvement we layer on top of 10-second candle reads is compromised from the start:

- **Partial exits?** The partials trigger based on 10s candle reversals, so they fire on noise. The first partial fires in seconds, and the "trail" portion never gets a chance to run.

- **Wide trail?** A wider trail on 10s bars still fires orders of magnitude faster than Ross's 1m-based exits. A "wide" trail on 10s is still a tight trail on 1m.

- **Runner detection?** We can detect that a stock is running, but if the exit signals are still reading 10s bars, the runner detection gets overridden by the next 10s "reversal" pattern.

**The fix is sequential, not parallel:**

```
Step 1: Move candle reads to 1m          ← fixes the root cause
Step 2: Implement CUC as primary exit    ← gives us Ross's actual signal
Step 3: Add MACD + 20 EMA backstops     ← adds the safety net
Step 4: Add signal hierarchy (partials)  ← refines the exit timing
Step 5: Remove stall timer / fix trail   ← removes counter-productive logic
Step 6: THEN add sizing, re-entries, etc ← layer on enhancements
```

Each step depends on the prior step being correct. You cannot skip to Step 4 or Step 6 and expect results — we tried that, and it didn't work.

**The ALUR example crystallizes this:**
- Entry: $8.04 (bot) vs ~$8.24 (Ross). Bot entered BETTER.
- Exit: $8.40 (bot, sq_target_hit after 3 min) vs ~$18-20 (Ross, rode for 90+ min)
- Ross held because his 1m candles never gave a CUC signal during the run. The stock made higher highs and higher lows on every 1m candle from $8 to $20.
- The bot exited because a fixed R-target hit at $8.40, and even if the R-target hadn't fired, the parabolic trail reading 10s bars would have exited within minutes.
- On 1m bars, there was NO exit signal until the move was mature. On 10s bars, there were dozens of "exit signals" that were just noise inside healthy 1m candles.

**Bottom line:** Fix the timeframe. Everything else follows.

---

## Appendix: Source Cross-Reference Table

| Topic | Recap Section | Video Finding | Agreement |
|-------|--------------|---------------|-----------|
| Partial exits at price levels | 1.2 | Confirmed | ✅ Full |
| Candle-structure trailing | 1.3 | Confirmed + CUC specificity | ⚠️ Partial — missed CUC |
| 10s chart usage | 1.3 (point 3) | ENTRY ONLY, not exits | ❌ Misidentified purpose |
| 1m chart for exits | 1.3 (point 2) | Confirmed as primary exit TF | ✅ Mentioned but not emphasized |
| 5m for trend confirmation | 1.3 (point 4) | Confirmed | ✅ Full |
| VWAP as exit reference | 1.4C | Confirmed | ✅ Full |
| Candle patterns (general) | 1.4A | Confirmed + hierarchy added | ⚠️ Partial — missed hierarchy |
| Confluence requirement | 1.4A | Confirmed | ✅ Full |
| MACD as backstop | Not mentioned | NEW finding | ❌ Missed entirely |
| 20 EMA as exit line | Not mentioned | NEW finding | ❌ Missed entirely |
| Stall timer concept | 1.5 (recommended) | ANTI-ROSS per video | ❌ Wrong recommendation |
| Fixed R targets | 1.2 (identified problem) | Confirmed as wrong | ✅ Full |
| Re-entry patterns | 1.6 | Not contradicted | ✅ Full |
| Daily P&L limits | 1.1 | Not contradicted | ✅ Full |
| Conviction sizing | 1.7 | Not contradicted | ✅ Full |
| Time-based exits | 1.5 | Partially contradicted (stall) | ⚠️ Mixed |

**Score: 9 confirmed, 3 missed entirely, 3 partially correct, 1 wrong recommendation**

Our recap analysis was a strong foundation — it correctly identified most of Ross's exit behaviors from observing outcomes. The video analysis adds the WHY behind the behaviors and reveals the specific mechanics (timeframe rules, signal hierarchy, indicator backstops) that weren't visible from recaps alone.

---

*Cross-reference completed 2026-03-22. Both source documents should be consulted for full context. Implementation should follow the priority order in Section 4, with Priority 1A (timeframe fix) as the absolute first step.*
