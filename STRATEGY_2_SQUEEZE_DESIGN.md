# Strategy 2: Squeeze / Breakout Entry — Design Document

## Created: 2026-03-19
## Status: DESIGN — Awaiting Manny Review Before Implementation

---

## 1. What Is a Squeeze Entry?

A squeeze enters on the **first leg** of a news-driven momentum move — the initial breakout, not the pullback after it. This is fundamentally different from the micro pullback, which waits for impulse → pullback → re-entry.

**ARTL Example (2026-03-18):**
- Premarket: stock at ~$4.59, float 0.7M, gap -7.3%
- 07:00: Volume explosion begins. Price runs $4.59 → $8.19 in ~80 minutes
- The micro pullback detector saw IMPULSE at 07:00 but couldn't ARM until 09:52 ($7.62)
- A squeeze detector would have entered early — on the break through premarket high or a whole-dollar level
- Ross captured the $4.59 → $8.19 move ($1,500+). Our MP detector caught +$922 on the 09:52 continuation

The squeeze captures what the micro pullback misses: the **initial momentum leg**.

---

## 2. How It Differs From Other Strategies

| Aspect | Micro Pullback (S1) | Squeeze (S2) | Dip-Buy (S3) | VWAP Reclaim (S4) |
|--------|---------------------|--------------|--------------|-------------------|
| **When** | 2nd leg (after pullback) | 1st leg (initial breakout) | Countertrend bounce | After recross above VWAP |
| **Enters on** | Trigger break after ARM | Volume + price break of key level | Support hold after selloff | First new high above VWAP |
| **Typical timing** | 07:05 - 10:00 | 07:00 - 07:30 (earliest) | 08:00 - 10:00 | 08:00 - 11:00 |
| **Risk profile** | Tighter stops (pullback low) | Wider stops (below consolidation) | Tighter stops (below support) | Moderate |
| **Speed** | Moderate | Very fast (parabolic moves) | Moderate | Moderate |

---

## 3. Squeeze Entry Criteria

Based on Ross Cameron's methodology (Perplexity research + observed ARTL/VERO/ROLR behavior):

### 3.1 Pre-Conditions (Scanner Already Handles)

These are Ross's 5 Pillars — already enforced by our unified scanner:
- Gap ≥ 10%
- RVOL ≥ 2x
- Float 100K – 10M
- Price $2 – $20
- PM Volume ≥ 50K

### 3.2 Squeeze Detection Criteria (New Logic)

The squeeze detector ARMs when it sees **simultaneous** evidence of:

**A. Volume Explosion (required)**
- Current 1m bar volume ≥ `WB_SQ_VOL_MULT` × average of prior 1m bars (default: 3.0x)
- At least `WB_SQ_MIN_BAR_VOL` shares in the bar (default: 50,000)
- This identifies the moment when institutional/retail volume floods in

**B. Price Above VWAP (required)**
- Current price > VWAP
- Already tracked by `bars.py` — available via `bar_builder.vwap(symbol)`

**C. Breakout Through Key Level (required — the trigger)**
- Price breaks above one of these levels (checked in priority order):
  1. **Premarket high** — already tracked by `bars.py` (`get_premarket_high()`)
  2. **Whole-dollar level** above current consolidation
  3. **Prior day high** (if available from scanner data)
- The break must happen WITH the volume explosion, not before it

**D. Price Momentum (required)**
- Bar is green (close > open)
- Bar range is "significant" — bar body ≥ `WB_SQ_MIN_BODY_PCT` of price (default: 1.5%)
- This filters out low-conviction grinds through levels

### 3.3 What Does NOT Qualify

- Slow grind above VWAP without volume spike → not a squeeze
- Price above PM high but volume falling → exhaustion, not squeeze
- Extended stock already 50%+ above VWAP → too late (same exhaustion logic as MP)
- Second push through same level after first failed → that's a VWAP reclaim (S4)

---

## 4. Squeeze State Machine

```
IDLE
  │
  ├── on_bar_close_1m(): Monitor volume and price vs key levels
  │
  ▼
PRIMED  (volume explosion detected, price above VWAP, near key level)
  │
  ├── Key level not yet broken → stay PRIMED (max WB_SQ_PRIME_BARS bars, default 3)
  ├── Volume dies → RESET to IDLE
  ├── Price drops below VWAP → RESET to IDLE
  │
  ▼
ARMED  (key level broken with volume confirmation)
  │
  ├── ArmedTrade created:
  │     trigger_high = breakout level + small buffer
  │     stop_low = low of the breakout bar (or consolidation low)
  │     setup_type = "squeeze"
  │
  ├── on_trade_price(): Wait for tick to confirm break
  │
  ▼
TRIGGERED → ENTRY via trade_manager.on_signal()
```

**Key differences from MP state machine:**
- No impulse → pullback cycle. Squeeze goes directly from volume detection to ARM
- Shorter time-to-ARM (1-3 bars vs 3-6 bars for MP)
- ARM window is shorter — squeeze setups are fleeting
- The "pullback" phase is replaced by "volume confirmation at level"

---

## 5. Stop Placement

Squeeze stops need to be different from MP stops:

**Option A: Below breakout bar low**
- stop = low of the 1m bar that triggered the ARM
- Pro: Tight, defines risk clearly
- Con: Parabolic moves often wick below before continuing

**Option B: Below consolidation zone**
- stop = lowest low of the last N 1m bars before breakout (default: 3)
- Pro: Gives more room for volatile squeeze action
- Con: Wider stop = smaller position size

**Recommendation: Option B with a cap.**
- `stop = min(low of last 3 bars before breakout)`
- But cap max R at `WB_SQ_MAX_R` (default: $0.80 or 5% of price, whichever is smaller)
- If R exceeds cap, skip the trade (too risky for the account size)

---

## 6. Exit Rules

Squeezes are faster and more volatile than pullbacks. The MP exit rules (bearish engulfing, topping wicky) would exit too early on a squeeze because the candles are wild.

### 6.1 Proposed Squeeze Exits

| Exit Type | Condition | Notes |
|-----------|-----------|-------|
| **Hard stop** | Price ≤ stop_low | Same as MP — non-negotiable |
| **Trailing stop** | Price drops `WB_SQ_TRAIL_R` × R below peak (default: 1.5R) | Wider trail than MP to let squeeze run |
| **Time stop** | No new high in `WB_SQ_STALL_BARS` 1m bars (default: 5) | If momentum dies, exit — don't hold and hope |
| **VWAP loss** | Price closes below VWAP on 1m bar | The squeeze thesis is broken |
| **Profit target** | Price hits `WB_SQ_TARGET_R` × R (default: 3.0R) | Take partials or full exit |
| **Max loss** | Same as MP: float-tiered max loss cap | Shared risk management |

### 6.2 What We Do NOT Use From MP Exits

- **Topping wicky exit**: Too sensitive for squeeze candles (almost every squeeze bar has wicks)
- **Bearish engulfing exit**: Too aggressive — squeeze stocks routinely have 1-bar pullbacks mid-run
- **5m guard**: May adapt later, but squeeze moves happen in 1-3 minute bursts, 5m is too slow
- **Continuation hold**: Not applicable — squeeze is the initial move, not a continuation

### 6.3 Exit Routing

The `setup_type` field on `OpenTrade` tells the trade manager which exit rules to apply. When `setup_type == "squeeze"`, the trade manager should use the squeeze exit set instead of the MP exit set.

This is the **first use case** for the strategy profile system described in MASTER_TODO. The trade manager needs a routing layer:

```python
def on_bar_close(self, symbol, o, h, l, c, v):
    trade = self.open_trades.get(symbol)
    if trade and trade.setup_type == "squeeze":
        self._check_squeeze_exits(trade, o, h, l, c, v)
    else:
        self._check_mp_exits(trade, o, h, l, c, v)  # existing logic
```

---

## 7. Position Sizing

Squeeze trades may warrant different sizing than MP trades:

**Option A: Same sizing as MP**
- Use `WB_RISK_DOLLARS` / R to calculate shares
- Pro: Simple, consistent risk
- Con: Wider stops mean fewer shares, which limits upside

**Option B: Reduced sizing for squeeze**
- Apply a `WB_SQ_SIZE_MULT` (default: 0.75) to squeeze position sizes
- Pro: Accounts for higher volatility and wider stops
- Con: Limits gains on the big winners

**Recommendation: Start with Option A.** Let the backtest tell us if squeeze trades need different sizing. The max_loss_cap and notional_cap already protect against outsized losses.

---

## 8. Interaction With Micro Pullback

**Critical question: Can both detectors be armed on the same stock at the same time?**

Yes, but only one should enter. Rules:

1. If squeeze triggers first (as it typically would), take the squeeze trade
2. Once in a squeeze trade, MP detector should NOT arm (no double-dipping)
3. After squeeze exit, MP detector CAN arm for continuation (this is the handoff — squeeze catches leg 1, MP catches leg 2+)
4. `WB_NO_REENTRY_ENABLED` still applies — if squeeze trade was a loss, no MP re-entry

This creates a natural multi-strategy flow on strong stocks:
```
Squeeze entry (07:05) → squeeze exit (07:25) → MP pullback entry (07:35) → cascading...
```

---

## 9. ARTL Walkthrough — What Would Have Happened

Using ARTL 2026-03-18 as a case study:

| Time | Price | What Happened | Squeeze Detector Would Do |
|------|-------|--------------|--------------------------|
| 07:00 | ~$4.59 | Volume explosion begins, IMPULSE detected | **PRIMED**: Vol spike detected, price above VWAP |
| 07:00-07:05 | $4.59→$5.50+ | Rapid run through whole-dollar levels | **ARMED**: Break above PM high / $5.00 with vol confirmation |
| 07:05 | ~$5.50 | Continued momentum | **ENTRY**: Trigger break confirmed on tick |
| 07:05-07:25 | $5.50→$8.19 | Parabolic run | **HOLDING**: Trailing stop following, no stall yet |
| 07:26 | ~$7.50 | First real pullback (MP saw PULLBACK 1/3) | **TRAIL STOP or TIME STOP**: Momentum stalling |
| 07:27 | | MP: NO_ARM exhaustion. Price consolidating. | Squeeze already exited. MP takes over for continuation |

**Estimated squeeze P&L on ARTL**: Entry ~$5.50, exit ~$7.50-$8.00 = ~$2.00/share gain = 2.5-3.0R
**Actual MP P&L**: Entry $7.62, exit $7.92 = $0.30/share = 0.9R

Combined: 3.4-3.9R vs 0.9R from MP alone.

---

## 10. Implementation Plan

### Phase 1: Squeeze Detector Module (squeeze_detector.py)

New file, same interface as `MicroPullbackDetector`:
- `seed_bar_close(o, h, l, c, v)` — warm indicators
- `on_bar_close_1m(bar, vwap)` — primary detection (returns ARM message)
- `on_trade_price(price, is_premarket)` — tick trigger check
- `armed` attribute: `ArmedTrade` with `setup_type="squeeze"`

### Phase 2: Trade Manager Exit Routing

Add squeeze exit logic to `trade_manager.py`:
- Route exits based on `setup_type`
- Implement trailing stop, time stop, VWAP loss for squeeze trades
- Keep all MP exit logic untouched

### Phase 3: Bot/Simulator Integration

Wire squeeze detector into `bot.py` and `simulate.py`:
- `ensure_detector()` returns both MP and squeeze detectors
- Both consume same bar/tick feed
- Conflict resolution: first to trigger wins, block other while in trade

### Phase 4: Backtesting

- Run ARTL 2026-03-18 with squeeze detector enabled
- Run all 9 key dates to measure impact
- Verify MP regression still passes (squeeze is additive, shouldn't affect MP-only trades)

---

## 11. Env Vars (All Gated, All OFF By Default)

```bash
# Master gate
WB_SQUEEZE_ENABLED=0              # 0=off, 1=on

# Detection thresholds
WB_SQ_VOL_MULT=3.0               # Bar volume must be Nx average to qualify
WB_SQ_MIN_BAR_VOL=50000          # Minimum absolute bar volume
WB_SQ_MIN_BODY_PCT=1.5           # Minimum bar body as % of price
WB_SQ_PRIME_BARS=3               # Max bars in PRIMED state before reset

# Risk
WB_SQ_MAX_R=0.80                 # Max R (risk per share) allowed
WB_SQ_SIZE_MULT=1.0              # Position size multiplier (1.0 = same as MP)

# Exits
WB_SQ_TRAIL_R=1.5                # Trailing stop distance in R-multiples
WB_SQ_STALL_BARS=5               # Time stop: exit if no new high in N 1m bars
WB_SQ_TARGET_R=3.0               # Profit target in R-multiples
WB_SQ_VWAP_EXIT=1                # Exit on 1m close below VWAP
```

---

## 12. Open Questions for Manny

1. **Partial profits**: Ross scales out at first target, holds runners. Do we want partial exits on squeeze trades, or all-or-nothing like MP currently does? (The bot is all-or-nothing today.)

2. **Pre-market high as primary level**: The research heavily emphasizes PM high as the key breakout level. On ARTL, PM high would have been around $4.59 (the open). Should we prioritize PM high over whole-dollar levels, or treat them equally?

3. **Maximum number of squeeze attempts per stock per day**: If the first squeeze trade stops out, should we allow a re-entry on the same stock? Ross says "expect multiple small stopouts before catching the big one" — but our no_reentry_after_loss rule would block this. Should squeeze trades have different re-entry rules?

4. **Time window**: Squeezes are typically 07:00-07:30 (first 30 min after market open). Should we restrict squeeze detection to a specific time window, or let it run all session?

5. **Interaction with classifier**: The classifier categorizes stocks by behavior type. Should squeeze detection bypass the classifier entirely (since it's entering before the stock has established a behavior pattern), or should PM behavior inform squeeze confidence?

---

## 13. Risk Assessment

**What could go wrong:**
- Squeeze detector enters on fake breakouts (volume spike but price reverses immediately)
- Wider stops + parabolic volatility = larger individual losses than MP
- Both detectors trying to enter simultaneously causes conflicts

**Mitigation:**
- Volume confirmation requirement (not just price break, need volume WITH it)
- R-cap prevents outsized risk per trade
- Max loss cap and daily loss limit still apply
- Conflict resolution rules prevent double-entry
- All gated by env vars — can disable instantly if it bleeds

---

*This document is the design spec for Strategy 2. Implementation begins after Manny reviews and approves the design, particularly the open questions in Section 12.*
