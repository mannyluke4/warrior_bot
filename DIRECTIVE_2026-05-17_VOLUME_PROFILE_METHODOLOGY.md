# Volume Profile Methodology — Watched, Extracted, Critical Questions

**Date:** 2026-05-17 (Sunday evening)
**Author:** Cowork (Perplexity)
**For:** Manny
**Status:** Video extracted. Significant strategic implications. **Questions needed before any directive.**

---

## What I watched and extracted

[Trading Notes — "NEVER Read Price Again – Volume Profile is 10x Better!"](https://youtu.be/XMNUAJvReg0) (84.2K subscriber channel, ~175K views, published ~May 2 2026).

The full breakdown is at `trading_notes_volume_profile_strategy.md`. Key elements:

**Strategy core:** Volume Profile / Auction Market Theory. Pre-mark levels from prior session (POC, VAH, VAL), wait for price to reach those levels, take entries on confirmation patterns.

**Three setups:**
1. **Signal Candle Model** — price sweeps a Low Volume Node and reaches the edge of a High Volume Node, then forms a doji/hammer/shooting-star with higher volume than prior candle. Enter after that candle closes. Stop just beyond HVN edge. Target opposite edge of the profile.
2. **80% Rule** — price opens outside yesterday's value area, re-enters with acceptance (not just a wick), entry direction is back toward the opposite VA edge. Stop just outside VA boundary. Target opposite VA edge.
3. **Profile Shape Bias** — D-shape fades extremes to POC; P/B shapes only valid when day closes on the favoring side of 50%; I-shapes traded with trend.

**Indicators used:** Volume Profile only. No VWAP, no EMAs, no MACD, no RSI.
**Timeframes:** RTH-anchored. Signal candles likely 1H/4H per related Trading Notes content. Position sizing not covered in the video.

---

## This is categorically different from what we built

The current WB strategy:
- Watches for momentum wave breakouts on 1m bars
- Scores entries on `vol_mult`, `vol_extra`, MACD, VWAP relationship, HOD distance
- Universe is small-cap gappers ($2-30, premarket vol filter, gap %, float ≤30M)
- Reactive to price action

The video's strategy:
- Pre-marks key price levels from yesterday's auction
- Waits for price to arrive at those levels
- Confirms with single-candle patterns + volume confirmation
- Universe is any liquid instrument — no premarket scanner, no float filter
- Reactive to **price reaching levels**, not to price movement structure

**These aren't variants of each other.** They're different strategies with different signal sources, different timeframes, different stop/target logic, and different universes.

---

## Why this might actually explain the forensic findings

The "no winner template" finding from Investigation 4 makes more sense under this framing.

The 5 historical "winners" through a Volume Profile lens:
- **FATN 5/5 mid-day reclaim:** could plausibly be a P-shape POC pullback or 80% Rule re-entry — would need to check whether the day's prior-session VA was relevant at the entry
- **ATRA 5/8 EH 68% gap:** not a VP setup; this was momentum
- **SST 5/11 3-hr flat box, breakout 40min post-fill:** could be a VA breakout-and-acceptance pattern
- **MEI 5/13 manual injection:** can't characterize
- **ATRA 5/15 dead-tape:** not a VP setup

**Hypothesis:** the bot has been a momentum bot that occasionally caught VP-shaped trades by accident. The forensic finding "no momentum template explains the wins" is consistent with "the wins were VP setups, but the bot has no VP signal at all to systematically capture them."

I'm not claiming this is true. I'm saying it's the kind of hypothesis that becomes worth testing once we have the right methodology spec.

---

## Critical questions before I write a directive

Manny, before I propose anything concrete, I need to understand what's actually in your paper trading:

### 1. What matches the video and what doesn't?

You said "close enough" and "not my exact paper method." Specifically:

- **Do you use Volume Profile levels (POC/VAH/VAL) at all?** Drawn manually, or via TradingView indicator, or by eye?
- **Do you trade purely off level reactions, or do you also watch momentum/breakouts?** The video is pure VP; your paper might mix both.
- **Which setup is closest to what you do?** Signal Candle (LVN→HVN edge reactions), 80% Rule (VA re-entry), or Profile Shape (D/P/B/I bias)?
- **Timeframes?** The video implies 1H/4H signal candles. Your paper might be on 1m/5m/15m given the small-cap universe.
- **Do you actually trade small-caps with this methodology**, or has your paper been on more liquid names (SPY, futures, large-cap movers)?

### 2. The universe question

The video explicitly says: any liquid instrument, no small-cap requirement. Our bot has been hunting in small-cap gappers because that's the squeeze scanner's universe, which the WB strategy inherited.

- **Are you actually trading small-cap gappers with VP**, or have you been trading something else and we built the bot in the wrong universe?
- If you DO use VP on small-caps: how do you handle that small-caps often don't have meaningful prior-day volume profiles (low avg volume → thin profiles → unreliable HVN/LVN)?

### 3. The data infrastructure question

True Volume Profile needs price-level volume aggregation, ideally from tick data. Our current pipeline has:
- 1m OHLCV bars (good for basic profile construction)
- Tick-by-tick on 5 Tier-1 active symbols (could build live VP)
- L2 depth (just wired up — shows current resting volume at each price)
- No historical tick aggregation for non-watchlist symbols

**Question for you:** when you paper-trade, what tool draws the volume profile? Do you use the TradingView anchored VP from the video, or something else? Where does your prior-day profile come from?

### 4. The execution question

The video says target = opposite edge of profile (edge-to-edge). For a small-cap that's run 30% intraday, "opposite edge of profile" could be a 5-15% move. That's compatible with our current squeeze + WB targets.

But: VP trades often have wide stops (HVN edge could be far from entry) and large targets. Does your paper trading use wide stops + multi-hour holds, or tighter intraday stops?

Our current force-exit at 19:55 ET caps holds at the session. VP edge-to-edge trades sometimes need next-day continuation. **Does your paper carry overnight or stay intraday?**

### 5. The honest question

The forensic finding — WB as currently built has no edge — stands regardless of what the video says. The question is whether your paper trading is reproducing some VP-like edge that the bot has been failing to capture.

- **What's your win rate in paper?** Roughly.
- **Average R-multiple?**
- **Do you have a written checklist of what makes a setup tradeable, or is it intuition right now?**
- **If we built a VP bot exactly per the video, would it match your trading 80%, 50%, 20%?**

---

## What I'm NOT proposing yet

1. **Not** rewriting WB into a VP bot. We don't know if that matches your trading.
2. **Not** changing the 6/15 go-live posture. Current WB doesn't ship regardless. Squeeze-only stands.
3. **Not** retiring WB. Path B (paper-only with engineering freeze) still applies. If a VP-pivot is right, we unfreeze for that work specifically.
4. **Not** changing the Monday gate plan. The forensic-synthesis-response directive's Monday changes still ship.

The forensic decisions stand. This video adds **strategic information about what to do with WB long-term**, but doesn't change the near-term tactical plan.

---

## What a VP-pivot would look like (high level, IF you confirm)

If your paper trading is genuinely VP-based, the long-term WB path becomes:

1. **Replace the WB detector** with a VP-aware detector that pre-marks levels and watches for arrivals + signal candle confirmation
2. **Repurpose L2 data** — the bid-stacking and large-order detection in `l2_signals.py` are direct VP signals (HVN-style accumulation visible in the live book)
3. **Build the VP-state-builder** — at boot, compute prior-day POC/VAH/VAL for each watchlist symbol. Update intraday profile as bars come in.
4. **New universe** — if you trade VP on more liquid names, the small-cap-gapper scanner is the wrong source. Build a "yesterday's interesting profile" scanner instead.
5. **New backtest infrastructure** — `simulate.py` needs VP-state replay, not just bar replay
6. **30+ session paper validation** of the VP bot before any real-money consideration

This is **multiple weeks of engineering** — not a Monday ship. Could happen during the 30-session WB paper-observation window (~7/15 deadline) we agreed on Saturday.

---

## What I want you to think about

The biggest strategic question this video raises:

**Is your edge actually Volume Profile, or is the video just a clean writeup of one set of patterns you happen to use among several?**

If the answer is "yes, VP is the core" — we have a real path forward for WB. Pivot the architecture, validate with 30 paper sessions, real-money 6 weeks later.

If the answer is "VP is one piece, momentum is another piece, intuition is the rest" — that's harder. We'd need to extract the other pieces too, and rebuilding the bot to capture intuition is the hardest engineering problem in trading.

Either answer is useful. Tell me which one matches your reality.

---

## Concrete next step

Reply with answers to questions §1–§5 above. I'll then write either:

- **(A) VP-pivot directive** with concrete build plan and timeline if VP is the core
- **(B) Multi-signal extraction directive** if your trading is more eclectic — we'd need to characterize each piece separately
- **(C) Stay-the-course directive** confirming WB retires or stays paper-only as a momentum bot, regardless of the video

I don't think C is the right answer based on what I just watched, but I want to hear from you before I commit to a recommendation.

---

## Files referenced

- `trading_notes_volume_profile_strategy.md` — full extraction (296 lines)
- `cowork_reports/2026-05-17_loser_forensic_synthesis.md` — the forensic week's conclusions
- `cowork_reports/2026-05-17_wb_winner_template.md` — Investigation 4's "no template" finding
- `archive/scripts/l2_signals.py` — has bid-stacking and large-order detection that map directly to VP HVN signals
- `wave_breakout_detector.py` — current WB momentum-style detector
- `squeeze_detector_v2.py` — current squeeze detector
