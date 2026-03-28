# DIRECTIVE: Post-Squeeze Continuation Strategy (Replaces MP)

**Date:** 2026-03-28  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P1 — Design first, implement after live validation of V2 infrastructure  
**Branch:** `v2-ibkr-migration`

---

## Why This Exists

MP is dead. 15 months of data: -$8,066, 24% win rate, lost money 11/15 months. It's scrapped.

But the problem MP was trying to solve is real. On EEIQ March 26, Ross made $37,800 on 5-6 continuation entries. Our bot made $1,671 on one squeeze entry. The squeeze captured the initial breakout, but 95% of the day's profit came from re-entries on the way up.

This directive defines a new **post-squeeze continuation strategy** designed from scratch around what Ross actually does — not the broken impulse → pullback → confirm cycle that MP used.

---

## What Ross Actually Does (From Video Analysis)

Based on analysis of Ross's EEIQ ($37.8K), UGRO, ARTL continuation, and his "How to Buy the Dip" / "ABCD Pattern" / "Adding to Winners" educational videos:

### Ross's Continuation Entry Rules

1. **Only re-enters stocks that have already proven themselves.** He doesn't re-enter random pullbacks. The stock must have already squeezed hard (big green candles, halts, volume). The initial squeeze IS the proof of concept.

2. **Waits for the pullback to HOLD a key level.** Not just any red candle — the stock must pull back to a recognizable support (VWAP, 9 EMA, prior breakout point, whole dollar) and HOLD IT. He says: "I'm waiting for these first early signs of the wave kind of shifting from pulling back to moving back in."

3. **Volume must dry up on the pullback.** This is Ross's #1 dip-vs-dump filter. Low volume on red bars = healthy consolidation (holders aren't selling). High volume on red bars = dump (get out). He says: "When we have just big sellers on the level two... that makes me worried."

4. **MACD must be positive (or at least not crossed negative on 1-min).** Ross explicitly uses MACD as a go/no-go gate. If 1-min MACD has crossed below zero, he waits. He says: "Just look at the MACD, is it positive or negative? It's negative — what's it going to do? It's going to dump."

5. **Re-entry is on the break of the consolidation high, not on the first green bar.** He buys the break of the pullback's high (point D in ABCD terms), not the first green candle after red bars. This is the critical difference vs old MP — MP armed on the first confirmation candle, Ross waits for the breakout of the consolidation range.

6. **Stop is tight: below the pullback low.** Risk is defined by the consolidation range. If the stock breaks below the low of the pullback, the thesis is dead.

7. **Uses cushion to size up.** After a winning squeeze trade, Ross uses the profit cushion to take bigger continuation positions. "When I got up to $5,500... I sized up."

8. **Three strikes rule.** After 2-3 failed re-entries on the same stock, he stops. "That's my cue to take my hands off the keyboard and walk away."

---

## The New Strategy: "Continuation" (CT)

### State Machine

```
IDLE → SQ_CONFIRMED → WATCHING → CT_PRIMED → CT_ARMED → CT_TRIGGERED
```

1. **IDLE**: No squeeze has completed. Do nothing.
2. **SQ_CONFIRMED**: A squeeze trade just closed with a profit. Continuation hunting is now unlocked for this symbol. Start a cooldown of N bars (default 3) to let the stock settle.
3. **WATCHING**: Cooldown expired. Actively watching for a pullback that holds support.
4. **CT_PRIMED**: A valid pullback has formed (1-3 red/flat bars, volume declining, price holding above key support). Waiting for the first sign of reversal.
5. **CT_ARMED**: Reversal confirmed — a green candle has closed above the pullback's midpoint AND the consolidation high is defined. Trigger price = consolidation high + $0.01. Stop = pullback low - $0.01.
6. **CT_TRIGGERED**: Price breaks above the consolidation high. Enter the trade.

### Key Differences from Old MP

| Feature | Old MP | New CT |
|---------|--------|--------|
| When it activates | Any impulse + pullback on any stock | Only after a profitable squeeze on that specific stock |
| What it watches for | First green bar after 1-3 red bars | Pullback that HOLDS support + declining volume + MACD positive |
| Entry trigger | High of confirmation candle | Break of consolidation range high (ABCD point D) |
| Volume check | None | Pullback volume must be < 50% of impulse volume |
| MACD gate | Optional, often skipped | Required: 1-min MACD must be positive or flat |
| Support check | None | Price must hold above 9 EMA AND above VWAP on pullback |
| Stop placement | Pullback low (often too tight) | Pullback low with wider pad (ATR-based minimum) |
| Position sizing | Same as initial | Can use cushion — probe size (50%) on first re-entry, full size on second if first wins |
| Max re-entries | 3 (but no quality filter) | 2 (strict quality on each) |
| Exit system | Old MP exits (bearish engulf, topping wicky) | Squeeze exit system (2R target, trailing stop, parabolic trail) |

---

## Detection Logic (Pseudocode)

```python
class ContinuationDetector:
    """Post-squeeze continuation entry detector.
    
    Only activates after a profitable squeeze trade closes.
    Watches for Ross-style pullback → consolidation → breakout continuation.
    """
    
    def __init__(self):
        self.state = "IDLE"
        self.cooldown_bars = 3           # Wait N bars after squeeze close
        self.max_reentries = 2           # Max continuation trades per symbol/session
        self.reentry_count = 0
        self.min_pullback_bars = 1       # At least 1 bar of pullback
        self.max_pullback_bars = 5       # Reset if pullback exceeds 5 bars
        self.max_retrace_pct = 50        # Pullback can't retrace more than 50% of the squeeze move
        self.min_vol_decay = 0.50        # Pullback avg volume must be < 50% of impulse volume
        
        # Tracked from the squeeze trade
        self.squeeze_entry = None        # Entry price of the completed squeeze
        self.squeeze_exit = None         # Exit price of the completed squeeze
        self.squeeze_high = None         # HOD at time of squeeze exit
        self.squeeze_vol = None          # Average volume during squeeze bars
        
        # Pullback tracking
        self.pullback_bars = []          # Bars during the pullback
        self.pullback_low = None         # Lowest low during pullback
        self.pullback_high = None        # Highest high during pullback (consolidation ceiling)
        self.consolidation_bars = 0      # Bars spent in consolidation range
        
        # Armed trade
        self.armed = None                # ArmedTrade object when ready to trigger
    
    def notify_squeeze_closed(self, entry, exit_price, pnl, hod, avg_squeeze_vol):
        """Called when a squeeze trade closes profitably."""
        if pnl <= 0:
            return  # Only activate on winning squeezes
        self.state = "SQ_CONFIRMED"
        self.squeeze_entry = entry
        self.squeeze_exit = exit_price
        self.squeeze_high = hod
        self.squeeze_vol = avg_squeeze_vol
        self.cooldown_remaining = self.cooldown_bars
        self.reentry_count = 0
    
    def on_bar_close_1m(self, bar, vwap, ema9, macd_positive):
        """Process each 1-minute bar close."""
        
        if self.state == "IDLE":
            return None
        
        if self.reentry_count >= self.max_reentries:
            return "CT_MAX_REENTRIES — done for this symbol"
        
        # --- SQ_CONFIRMED: cooldown ---
        if self.state == "SQ_CONFIRMED":
            self.cooldown_remaining -= 1
            if self.cooldown_remaining <= 0:
                self.state = "WATCHING"
                return "CT_WATCHING — cooldown expired, hunting pullbacks"
            return f"CT_COOLDOWN ({self.cooldown_remaining} bars remaining)"
        
        # --- WATCHING: look for pullback formation ---
        if self.state == "WATCHING":
            is_pullback_bar = (
                not bar.green                           # Red or flat bar
                or bar.close <= self.pullback_bars[-1].close  # Lower close than prior
                if self.pullback_bars else not bar.green
            )
            
            if is_pullback_bar:
                self.pullback_bars.append(bar)
                self.pullback_low = min(b.low for b in self.pullback_bars)
                self.pullback_high = max(b.high for b in self.pullback_bars)
                
                # Check: pullback too deep?
                if self.squeeze_high and self.squeeze_entry:
                    squeeze_range = self.squeeze_high - self.squeeze_entry
                    retrace = self.squeeze_high - self.pullback_low
                    if squeeze_range > 0 and (retrace / squeeze_range * 100) > self.max_retrace_pct:
                        self._reset("CT_RESET: pullback too deep ({:.0f}% retrace)".format(retrace/squeeze_range*100))
                        return self._last_msg
                
                # Check: pullback too long?
                if len(self.pullback_bars) > self.max_pullback_bars:
                    self._reset("CT_RESET: pullback too long ({} bars)".format(len(self.pullback_bars)))
                    return self._last_msg
                
                return f"CT_PULLBACK: {len(self.pullback_bars)} bars, low=${self.pullback_low:.2f}"
            
            # Green bar after pullback — check if it qualifies for PRIMED
            if len(self.pullback_bars) >= self.min_pullback_bars and bar.green:
                self.state = "CT_PRIMED"
                # Fall through to CT_PRIMED check below
        
        # --- CT_PRIMED: validate the pullback quality ---
        if self.state == "CT_PRIMED":
            # Gate 1: Volume decay — pullback volume must be lower than squeeze volume
            pb_avg_vol = sum(b.volume for b in self.pullback_bars) / len(self.pullback_bars) if self.pullback_bars else 0
            if self.squeeze_vol and pb_avg_vol > 0:
                vol_ratio = pb_avg_vol / self.squeeze_vol
                if vol_ratio > self.min_vol_decay:
                    self._reset(f"CT_REJECT: pullback volume too high ({vol_ratio:.1f}x squeeze avg)")
                    return self._last_msg
            
            # Gate 2: Price must be above key support
            if vwap and bar.close < vwap:
                self._reset("CT_REJECT: price below VWAP on confirmation")
                return self._last_msg
            
            if ema9 and bar.close < ema9:
                self._reset("CT_REJECT: price below 9 EMA on confirmation")
                return self._last_msg
            
            # Gate 3: MACD must be positive (Ross's #1 dip-vs-dump filter)
            if not macd_positive:
                self._reset("CT_REJECT: MACD negative — likely dump, not dip")
                return self._last_msg
            
            # Gate 4: Pullback must have held above a reasonable level
            # (not below 50% of the squeeze move from entry)
            # Already checked in WATCHING state
            
            # All gates passed — ARM the trade
            entry = self.pullback_high + 0.01  # Break of consolidation ceiling
            stop = self.pullback_low - 0.01    # Below pullback low
            r = entry - stop
            
            if r <= 0 or r < 0.06:
                self._reset(f"CT_REJECT: R too small ({r:.4f})")
                return self._last_msg
            
            self.state = "CT_ARMED"
            self.armed = ArmedTrade(
                trigger_high=entry,
                stop_low=stop,
                entry_price=entry,
                r=r,
                setup_type="continuation",
                # First re-entry uses probe sizing (50%), second uses full
                size_mult=0.5 if self.reentry_count == 0 else 1.0,
            )
            return f"CT_ARMED: entry=${entry:.2f} stop=${stop:.2f} R=${r:.4f}"
        
        # --- CT_ARMED: waiting for price trigger ---
        # (handled in on_trade_price, not bar close)
        if self.state == "CT_ARMED":
            return None
        
        return None
    
    def on_trade_price(self, price):
        """Check if armed trade triggers on this price."""
        if self.state != "CT_ARMED" or not self.armed:
            return None
        
        if price >= self.armed.trigger_high:
            self.state = "IDLE"  # Reset after trigger (will re-enter WATCHING after trade closes)
            return f"CT ENTRY SIGNAL @ ${price:.2f}"
        
        return None
    
    def notify_continuation_closed(self, pnl):
        """Called when a continuation trade closes."""
        self.reentry_count += 1
        if pnl > 0:
            # Winning re-entry — continue hunting with full size
            self.state = "SQ_CONFIRMED"  # Go back to cooldown → watching
            self.cooldown_remaining = 2  # Shorter cooldown after a winning continuation
        else:
            # Losing re-entry — still try one more if under max
            self.state = "SQ_CONFIRMED"
            self.cooldown_remaining = self.cooldown_bars
        self.pullback_bars = []
        self.armed = None
    
    def _reset(self, msg):
        """Reset to WATCHING state (keep watching for next pullback)."""
        self.state = "WATCHING"
        self.pullback_bars = []
        self.pullback_low = None
        self.pullback_high = None
        self.armed = None
        self._last_msg = msg
```

---

## Exit System

Continuation trades use the **exact same squeeze exit system** (this was one thing MP V2 got right):

- 2R target → exit 75% (core), keep 25% (runner)
- Parabolic trailing stop for volatile entries
- Max loss dollar cap ($500)
- 5-minute bail timer if not in profit

The squeeze exits are proven (39/39 on sq_target_hit). No reason to reinvent exits.

---

## How It Integrates with the Bot

### Entry Priority: SQ > CT (always)

Squeeze detector has absolute priority. If SQ is PRIMED or ARMED, CT defers. CT only fires when SQ is IDLE — meaning the squeeze has already played out and reset. This prevents the VERO regression where MP V2 cannibalized SQ cascades.

```python
# In check_triggers():
if setup_type == "continuation" and SQ_ENABLED:
    sq = state.sq_detectors.get(symbol)
    if sq and (sq._state != "IDLE" or sq._in_trade):
        print(f"CT DEFERRED: SQ has priority (state={sq._state})")
        return  # Don't disarm — CT stays armed for when SQ goes idle
```

### Lifecycle

1. Squeeze fires on EEIQ at $4.80, exits at $5.60 via sq_target_hit (+$0.80, +2R) → SQ notifies CT detector
2. CT enters SQ_CONFIRMED state, starts 3-bar cooldown
3. After 3 bars: CT → WATCHING. Monitors for pullback to VWAP/EMA support
4. EEIQ pulls back from $5.60 to $5.20 over 2 red bars (holds above VWAP at $5.10, volume declining)
5. Green bar closes at $5.40 → CT → CT_PRIMED. Checks: MACD positive? Volume decay? Above VWAP? Above EMA? Retrace < 50%?
6. All gates pass → CT → CT_ARMED at $5.45 (break of pullback high), stop at $5.19 (below pullback low)
7. Price breaks $5.45 → CT_TRIGGERED, enter with probe sizing (50%)
8. Rides to $5.90 → sq_target_hit (same 2R exit system)
9. CT notifies trade closed → back to SQ_CONFIRMED → shorter cooldown → hunt next pullback
10. Second continuation trade: full sizing this time

---

## Key Env Vars

```
# Master switch
WB_CT_ENABLED=1               # Enable post-squeeze continuation

# Timing
WB_CT_COOLDOWN_BARS=3         # Bars to wait after squeeze/continuation close
WB_CT_MAX_REENTRIES=2         # Max continuation trades per symbol per session
WB_CT_MIN_PULLBACK_BARS=1     # Min pullback bars before arming
WB_CT_MAX_PULLBACK_BARS=5     # Max pullback bars before reset

# Quality filters
WB_CT_MAX_RETRACE_PCT=50      # Max retracement of squeeze move (%)
WB_CT_MIN_VOL_DECAY=0.50      # Pullback avg vol must be < this × squeeze avg vol
WB_CT_REQUIRE_VWAP=1          # Require price above VWAP on confirmation
WB_CT_REQUIRE_EMA=1           # Require price above 9 EMA on confirmation
WB_CT_REQUIRE_MACD=1          # Require positive MACD on confirmation

# Sizing
WB_CT_PROBE_SIZE=0.5          # First re-entry uses 50% size
WB_CT_FULL_SIZE=1.0           # Second re-entry uses full size

# Exits — uses squeeze exit system (WB_SQ_TARGET_R, WB_SQ_TRAIL_R, etc.)
```

---

## What This Captures vs Ross's EEIQ Session

Ross's EEIQ March 26 timeline:
1. **Breakout scalp ~$6** → halt up → dip-and-rip → $4.5K cushion (= our squeeze trade)
2. **Dip to $7 support** → holds → buy dip → rides to $8.60 (= CT re-entry #1)
3. **Inverted H&S at $7.20** → size up with cushion → add at $7.60, $8.00 → ride to $8.72 → $24K (= CT re-entry #2 with full size)
4. **Later halts toward $10-$12** → shooting stars + MACD negative → stops pressing (= CT would reject: MACD negative)

Our squeeze captures step 1 ($1.6K). This continuation strategy is designed to capture steps 2 and 3. Even capturing 30% of Ross's continuation profits on days like this would add $10K+ per occurrence.

---

## Implementation Order

1. **Create `continuation_detector.py`** — New file, clean implementation. Don't modify micro_pullback.py.
2. **Wire into `simulate.py`** — Add CT detector alongside SQ detector. CT activates only when `notify_squeeze_closed` fires with positive P&L.
3. **Wire into `bot_ibkr.py`** — Same integration pattern as SQ/MP, with SQ priority gate.
4. **Backtest on known runners** — EEIQ (Mar 26), ROLR (Jan 14), VERO (Jan 16), NPT (Feb 3), CRE (Mar 6). These are the stocks where Ross made multiple entries.
5. **YTD A/B test** — SQ-only vs SQ+CT. Must show: (a) CT doesn't degrade SQ trades, (b) CT adds incremental P&L on multi-wave stocks.

---

## Success Criteria

| Test | Pass Condition |
|------|---------------|
| VERO regression | SQ+CT = same P&L as SQ-only (CT defers to SQ cascade) |
| ROLR regression | SQ+CT = same P&L as SQ-only |
| EEIQ validation | SQ+CT > SQ-only (CT catches at least one re-entry) |
| NPT validation | SQ+CT ≥ SQ-only (CT adds or stays neutral) |
| YTD SQ+CT | Total P&L > $264,594 (SQ-only baseline) |
| YTD CT-only trades | Win rate > 50%, positive P&L |
| No regression | SQ trades in SQ+CT mode match SQ-only exactly |

---

## What We're NOT Building

- No standalone entry detection (CT only fires after a confirmed squeeze win)
- No pre-market entries (CT only runs during RTH + evening windows, after squeeze proof)
- No multi-symbol CT (one symbol at a time, same as current bot architecture)
- No complex level detection (uses simple pullback low/high, VWAP, EMA — no Fibonacci, no order flow)
- No position adding (each CT entry is a fresh position, not adding to an existing one)

Keep it simple. The squeeze is the edge. Continuation is just capturing more of the same move.
