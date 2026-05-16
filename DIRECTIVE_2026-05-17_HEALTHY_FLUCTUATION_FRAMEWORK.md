# Healthy Fluctuation — The Real Project Goal

**Date:** 2026-05-17
**Author:** Cowork (Perplexity)
**For:** Manny + CC
**Trigger:** Manny: "We do not need to make a hybrid bot/human function... We need to look at the principles from this video, extract all of the mechanical data, and reframe WB to use the tools that the bot does best... My personal strategy, WB, and box all rest on one fundamental unchanging truth: prices fluctuate. Our goal is to find the healthiest fluctuation, and take advantage of that healthy movement."

---

## The principle, named

**Prices fluctuate. Healthy fluctuations have detectable, objective properties. The bot's job is to find them and execute on them with the speed, breadth, and consistency humans can't match.**

This is the project's actual purpose — clearer than anything we've articulated before. WB, box, squeeze, the video's Volume Profile — these are all *methodologies* for identifying healthy fluctuation. We've been treating them as separate strategies. They're not. They're variations of one underlying problem the bot needs to solve:

> Find a price level where a fluctuation will likely react, confirm that the reaction is real, execute with predefined risk and a measurable target.

That's the framework. Everything else is parameter choices within it.

---

## What "healthy fluctuation" means objectively

A healthy fluctuation has these properties — all of which the bot can detect:

1. **Real participation** — multiple market participants trading. Not one-print spikes. Volume confirms activity.
2. **Predictable level structure** — moves respect identifiable levels (POC, VAH, VAL, HVN/LVN, prior swing points, whole-dollar, VWAP, premarket high/low, opening range, multi-day swings).
3. **Direction-able** — there's a reversal-or-continuation pattern at the level that the bot can detect (signal candle, volume confirmation, L2 reaction).
4. **Risk-definable** — there's a clear point where "this fluctuation has failed" (the level breaks decisively).
5. **Edge-to-edge potential** — there's a next level where the next reaction is likely (the target).

If those properties exist, the setup is tradeable. If any of them is missing, it's not. **This is the universal definition.** It applies to every strategy we've discussed.

---

## The unified architecture

**The bot should have one core primitive, not separate strategies:**

```
strategy = (
    level_source,           # which kind of level are we watching?
    arrival_detector,       # how do we know price has arrived?
    confirmation_rule,      # is the reaction real?
    stop_placement,         # where does the thesis die?
    target_rule,            # where do we exit on success?
)
```

Each strategy = one parameter choice within this framework.

| Strategy | level_source | arrival | confirmation | stop | target |
|---|---|---|---|---|---|
| **Squeeze** | whole-dollar, pm_high | price within X% of level | breakout candle + vol_mult | below level | parabolic trail + dollar cap |
| **WB-new** | POC, VAH, VAL, HVN edges | price within X% of level after LVN sweep | signal candle (doji/hammer/star) + higher vol than prior bar | into LVN beyond HVN | opposite profile edge |
| **VA-rule** | prior session VAH/VAL | price re-enters VA from outside | acceptance (≥N bars inside) | just outside VA | opposite VA edge |
| **Box** | range bounds (HOD/LOD of consolidation) | price near level after consolidation | breakout candle + vol | below box | measured move (range height) |
| **Future** | (whatever level type next) | (whatever arrival rule) | (whatever confirmation) | (whatever stop) | (whatever target) |

**This is the right architecture.** Today's bot has each detector reimplementing variations of this. The unified framework lets us add strategies by changing parameters, not by writing new code.

---

## What the bot does beyond any single methodology

The video's strategy is a *human teaching example* of one operationalization. The bot version does what the video can't:

| Capability | Human (video) | Bot |
|---|---|---|
| Symbols monitored | 1-3 at a time | 200+ in parallel |
| Levels pre-marked | Manually before open | All levels computed at boot for all symbols |
| Arrival detection | Watching chart | Continuous monitoring, alert on any approach |
| Confirmation pattern | Eye + judgment | Bar-close + multi-rule check |
| L2 confirmation | Not available to retail human in real-time | Live book imbalance, bid stacking, large-order detection |
| Execution latency | ~1-3 seconds | <100ms |
| Statistical tracking | Mental/journal | Per-level-type hit rate over thousands of decisions |
| Multi-timeframe levels | Practical limit ~2-3 | All timeframes simultaneously (intraday + daily + 5-day + premarket) |
| Risk consistency | Variable | Identical per trade |

**The bot's edge isn't a better methodology than the video.** The bot's edge is *the same methodology applied with capabilities the human can't match.*

---

## What this reframes about everything we've built

### What was right (keep)

- **Squeeze** — already operates within this framework (whole-dollar level, breakout confirmation, predefined risk, parabolic-trail target). Validates the architecture. Squeeze-only at 6/15 stands.
- **L2 work** — the bid-stacking + large-order detection are *direct confirmation signals* for level reactions. Becomes more important under the new framing, not less.
- **chop_gate_v3 architecture** — the modular sub-gate orchestrator is exactly the right shape to host strategy-specific confirmation rules.
- **Persistence layer** — useful for level continuity across sessions (e.g., "this VAH from yesterday is still relevant").
- **Intraday adder** — useful for level continuity within session.
- **Daily report framework** — tracks per-level-type performance going forward.
- **Force-exit / FCHL fix** — universal infrastructure.

### What was wrong (fix or retire)

- **WB detector** — built around momentum wave structure. Wrong primitive. Retire and rebuild as a level-reaction instance.
- **WB-specific scoring** — `vol_mult`, `vol_extra`, MACD-as-score-component all assume momentum framing. Replace with level-reaction-specific scoring.
- **Tape-quality gates** — dead-tape gate vetoes setups where price has thinned around a level, but **thin tape near a major HVN can be exactly the right setup** (the LVN sweep before HVN reaction). Need to rethink, not just disable.
- **Persistence-layer assumptions** — was carrying forward "symbols with prior WB activity." Should carry forward "symbols with reaction-worthy levels."
- **Intraday adder filters** — was filtering for "intraday gap and RVOL." Should filter for "approaching a relevant level."

### What's new (build)

- **Universal level-source library** — module that computes POC/VAH/VAL/HVN/LVN from bar data. Reusable across strategies.
- **Level-arrival detector** — abstract module that watches a symbol's current price vs its level set and emits arrival events.
- **Confirmation-pattern detectors** — modules for each pattern (signal candle, breakout candle, acceptance, etc).
- **Strategy registry** — config-driven mapping of strategy_name → (level_source, arrival, confirmation, stop, target).
- **Per-strategy performance tracker** — daily reports break out by strategy AND by level type.

---

## The Volume Profile component specifically

The video's Volume Profile methodology is one instance of this framework. Translating to the bot:

### Level construction

**At session boot for each watchlist symbol:**

```python
def compute_level_set(symbol):
    prior_session_bars = get_rth_bars(symbol, days_ago=1)
    poc = bars_at_volume_peak(prior_session_bars)
    vah, val = value_area_bounds(prior_session_bars, threshold=0.70)
    hvns = find_high_volume_nodes(prior_session_bars, threshold=0.80)
    lvns = find_low_volume_nodes(prior_session_bars, threshold=0.20)

    return LevelSet(
        poc=poc,
        vah=vah,
        val=val,
        hvns=hvns,
        lvns=lvns,
        symbol=symbol,
        session_date=prior_session_date,
    )
```

**Continuously throughout session:**
- Update intraday profile as bars close
- Recompute "developing POC" and "developing value area"
- Add today's session as a parallel level set

### Arrival detection

```python
def check_level_arrival(symbol, current_price, level_set):
    """Returns the first level the price is currently 'at' (within proximity threshold)."""
    proximity = max(0.005, level_set.day_range * 0.01)  # 1% of day range or 0.5%
    for level in level_set.all_levels:
        if abs(current_price - level.price) <= proximity:
            return level
    return None
```

### Signal Candle confirmation (from video)

```python
def detect_signal_candle(bar, prior_bar):
    """Detects doji/hammer/shooting-star with higher volume than prior bar."""
    body = abs(bar.close - bar.open)
    range_size = bar.high - bar.low
    if range_size == 0: return None

    body_ratio = body / range_size
    upper_wick = bar.high - max(bar.open, bar.close)
    lower_wick = min(bar.open, bar.close) - bar.low

    is_doji = body_ratio < 0.1
    is_hammer = lower_wick > 2 * body and body_ratio < 0.3
    is_shooting_star = upper_wick > 2 * body and body_ratio < 0.3

    has_volume_confirm = bar.volume > prior_bar.volume

    if (is_doji or is_hammer or is_shooting_star) and has_volume_confirm:
        return SignalCandle(pattern=..., bar=bar)
    return None
```

### L2 confirmation enhancement

The video uses bar-close volume only. The bot adds L2 confirmation at the same moment:

```python
def confirm_with_l2(symbol, level, signal_candle, direction):
    l2_state = request_l2_snapshot(symbol)
    if direction == "long":
        # Want to see: imbalance turning bull, bid stacking near level, ask thinning above
        return (l2_state.imbalance > 0.55 and
                l2_state.bid_stacking_near(level.price))
    elif direction == "short":
        return (l2_state.imbalance < 0.45 and
                l2_state.ask_stacking_near(level.price))
```

This is what the human trader can't do. Adding L2 as a second confirmation gate at the moment of the signal candle close.

### Stop and target

Per video:
- **Stop**: just past the HVN edge into the LVN (where the thesis is "dead")
- **Target**: opposite edge of the profile (edge-to-edge)

Both straightforward to compute from the level set.

---

## What I'm proposing as the next step

I'm not writing the build directive yet. The right next step is an **architecture design doc** — pseudocode + module structure + reusable-component inventory + new-component scope + decision points where Manny weighs in.

The design doc covers:

1. **Module structure** for the unified framework
2. **Concrete spec** for each piece: level_source, arrival_detector, confirmation_pattern, stop_placement, target_rule
3. **How existing code maps** (squeeze becomes an instance; WB code retires; chop_gate_v3 sub-gates plug in as confirmation rules)
4. **Phased build plan** (Phase A: framework infrastructure. Phase B: first new strategy [Volume Profile-based]. Phase C: migrate squeeze to framework. Phase D: future strategies.)
5. **Validation strategy** — how do we know each new strategy has edge before going live?
6. **Backtest spec** — `simulate.py` needs to support the framework, not just current detectors
7. **Timeline considerations** — what can land before vs after 6/15

After design-doc approval, the build directive follows.

---

## What changes immediately

### 6/15 plan
**Unchanged.** Squeeze-only real money. Squeeze stays in its current implementation; framework migration happens after go-live, not before.

### Current WB
**Retire as planned.** The bot-vs-human reframe stands. WB is closed regardless of what comes next. The new strategy that emerges from the framework work is a *successor*, not a continuation.

### Monday production checklist
**Unchanged.** Gate changes, force-exit validation, dead-tape observe-only, squeeze N-cap all ship.

### L2 work
**Continues** under the L2 build plan. Becomes more central to the new framework — L2 confirmation is exactly the bot-only edge the framework adds beyond the video.

### Engineering attention
**Splits two ways post-Monday:**
- CC: continue squeeze production work + L2 phases per existing plan
- Cowork: write the architecture design doc

---

## Critical pre-design-doc questions for Manny

Before I write the architecture doc, three questions to align scope:

### 1. Strategy inventory — what gets included in the framework?

The framework as defined supports:
- Squeeze (whole-dollar / pm-high level reactions)
- Volume Profile (POC/VAH/VAL/HVN level reactions per video)
- VA Rule (80% rule from video — value area re-entry)
- Box (range-bound consolidation breakout)
- Any "level + confirmation" pattern you want

**Which of these should we plan to build?** Just the Volume Profile one? Or aim for a portfolio of strategies on the framework?

My recommendation: build the framework, validate with Volume Profile + Box, defer others until validated. Aiming for a portfolio early dilutes focus.

### 2. Timeframe scope

Video implies higher timeframes (1H/4H signal candles, daily VP profile). Current bot is 1m-bar everything.

**For the new framework, what timeframes are in scope?**
- 1m bars only (current bot)
- 5m / 15m / 1h bars (adds higher-timeframe confirmation)
- Multi-timeframe (level identified on daily, confirmation on 1m)

My recommendation: multi-timeframe. Levels from daily/yesterday's profile, confirmation on 1m bars. Best of both — the bot sees the level on its proper timeframe but executes with bot-speed precision.

### 3. Universe scope

Current bot universe: small-cap gappers from squeeze scanner.

The video's methodology works on any liquid instrument. **Should the new framework run on the same small-cap universe, or expand?**

My recommendation: keep the small-cap universe for now. We have infrastructure built for it. Expanding the universe is a separate work stream we can do later if the framework proves out.

### 4. Manual trading lane — confirmed dropped

You said no hybrid bot/human function. Confirmed dropping that proposal. Bot is fully autonomous.

---

## What I'm NOT doing

- Not writing the architecture design doc tonight
- Not committing to specific strategy implementations within the framework yet
- Not changing the 6/15 plan
- Not pulling resources from Monday production work
- Not retiring squeeze (squeeze becomes an instance of the new framework eventually, but it's already validated and works)
- Not modifying L2 build plan

---

## Tone

You just gave the project its purpose. "Find healthy fluctuations and take advantage of them" is the right north star. The video, WB, squeeze, box, your discretionary trading — they're all attempts at this. The bot's job is the same attempt, executed with bot capabilities.

This is the cleanest frame we've had. Everything we've built either fits into it or it doesn't. The forensic week told us WB-as-built doesn't fit. The video told us the framework that does fit. Your articulation tonight told us why — *prices fluctuate, we want healthy ones*.

Once you confirm the three pre-design questions above, I write the architecture doc. From there, the build path is clear.

---

## Reports CC owes Cowork — refreshed

| When | Report | Status |
|---|---|---|
| Sun 5/17 evening or before Mon open | Clarification on L2 state (per yesterday's question) | per existing |
| Mon EOD 5/18 | Daily breakdown with Monday production sections | per existing |
| Mon EOD 5/18 | Historical-winner dead-tape backfill | per existing |
| Fri 5/22 | 5-day squeeze evaluation for 6/15 go-live | per existing |
| Cowork (not CC) | Architecture design doc for healthy-fluctuation framework | new, depends on Manny's 3 questions |

---

## Files referenced

- `cowork_reports/2026-05-17_loser_forensic_synthesis.md`
- `cowork_reports/2026-05-17_wb_winner_template.md`
- `trading_notes_volume_profile_strategy.md`
- `DIRECTIVE_2026-05-17_BOT_VS_HUMAN_REFRAME.md` (yesterday's reframe — now superseded by this clearer principle)
- `DIRECTIVE_2026-05-15_L2_FULL_BUILD.md` (Phases 7-8 stay parked under THIS framework too — they fit but they're not the first build target)
- `squeeze_detector_v2.py` (the validated reference for "level-reaction strategy that works")
- `wave_breakout_detector.py` (retiring)
