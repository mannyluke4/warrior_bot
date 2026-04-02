# Directive: EPL Strategy — VWAP Reclaim (Post-2R Graduation)

## Priority: P0
## Prereqs:
- Read `ARCHITECTURE_EXTENDED_PLAY_LIST.md` — EPL design doc
- Read `epl_framework.py` — framework (commit 6d52894)
- Read `epl_mp_reentry.py` — reference implementation of an EPL strategy
- Read `vwap_reclaim_detector.py` — existing standalone VR detector (431 lines, 0 trades)

---

## Context

### Why Standalone VR Failed (0 Trades Across 27 Test Runs)

The standalone VWAP reclaim detector was tested 3 rounds in March 2026. It produced 0 trades because:

1. **Runners** (VERO, ROLR) never dipped below VWAP — squeeze carried them above VWAP all session
2. **Faders** (GRI, APVO, TWG) collapsed below VWAP permanently — never recovered
3. The "dip and recover" pattern sits between these two and essentially didn't exist at scanner-entry time

**Conclusion at the time:** "VR may not be viable for micro-cap momentum. Recommend shelving."

### Why EPL VR Is Different

The VWAP reclaim pattern doesn't appear at scan time — **it appears at graduation time.** After hitting 2R:
- Profit-taking by the bot and other participants causes a selloff
- The stock pulls back, often dipping to or through VWAP
- On the 86% that are runners, the stock recovers above VWAP and continues

This IS the VWAP reclaim pattern. The graduation filter solves the stock selection problem that killed standalone VR. We're only looking at stocks that have already proven momentum (hit 2R), and the post-2R pullback is exactly when the dip-and-recover pattern occurs.

### Evidence From Post-Exit Analysis

Of the 30 runner stocks that hit sq_target_hit, 25 (83%) experienced pullbacks before continuing higher. Many of those pullbacks dipped to or through VWAP. The EPL MP re-entry catches the ones that pull back shallowly (above VWAP). EPL VR catches the ones that pull back deeper (through VWAP then recover).

**MP Re-entry and VR are complementary:**
- MP catches shallow pullbacks (pullback stays above VWAP)
- VR catches deep pullbacks (pullback goes below VWAP, then recovers)
- Together they cover both post-2R patterns

Note: the EPL MP VWAP floor gate (DIRECTIVE_EPL_MP_VWAP_FLOOR) specifically blocks MP entries when pullback breaches VWAP. Those are exactly the setups VR should catch instead.

---

## What To Build

### File: `epl_vwap_reclaim.py` (NEW)

Implements `EPLStrategy` from `epl_framework.py`. Salvages the state machine logic from `vwap_reclaim_detector.py` but adapted for EPL.

#### Properties

```python
@property
def name(self) -> str:
    return "epl_vwap_reclaim"

@property
def priority(self) -> int:
    return 40  # Below MP re-entry (50), below SQ (100)
```

#### Env Vars

```python
EPL_VR_ENABLED = int(os.environ.get("WB_EPL_VR_ENABLED", "0"))
EPL_VR_COOLDOWN_BARS = int(os.environ.get("WB_EPL_VR_COOLDOWN_BARS", "3"))
EPL_VR_VOL_MULT = float(os.environ.get("WB_EPL_VR_VOL_MULT", "1.5"))       # Reclaim bar volume >= 1.5x avg
EPL_VR_RECLAIM_WINDOW = int(os.environ.get("WB_EPL_VR_RECLAIM_WINDOW", "3")) # Bars after reclaim to confirm new high
EPL_VR_MAX_BELOW_BARS = int(os.environ.get("WB_EPL_VR_MAX_BELOW_BARS", "15")) # Max bars below VWAP (wider than standalone — post-2R pullbacks can be longer)
EPL_VR_MIN_R = float(os.environ.get("WB_EPL_VR_MIN_R", "0.06"))
EPL_VR_STOP_PAD = float(os.environ.get("WB_EPL_VR_STOP_PAD", "0.01"))
EPL_VR_SEVERE_LOSS_PCT = float(os.environ.get("WB_EPL_VR_SEVERE_LOSS_PCT", "20.0"))  # If stock drops > 20% below VWAP, give up
```

**Key threshold changes from standalone VR:**
- `MAX_BELOW_BARS`: 15 (was 10). Post-2R pullbacks take longer to develop.
- No `MAX_R` cap. Standalone VR's $0.50 R-cap was the primary blocker. In EPL, the stop is defined by the reclaim pattern (below VWAP low), and R is naturally bounded by the pullback depth. Let the pattern define the risk.
- No `MAX_R_PCT` cap either. Same reasoning — the graduation filter handles stock quality.

#### Per-Symbol State

```python
@dataclass
class VRState:
    phase: str = "IDLE"             # IDLE, WATCHING, BELOW_VWAP, RECLAIMED, ARMED
    graduation_ctx: Optional[GraduationContext] = None
    cooldown_bars: int = 0
    bars_since_graduation: int = 0
    ever_above_vwap_post_grad: bool = False   # Must see price above VWAP after graduation before tracking dips
    below_vwap_bars: int = 0                  # Bars spent below VWAP
    below_vwap_low: float = float('inf')      # Lowest low while below VWAP
    reclaim_bar: Optional[dict] = None        # The bar that crossed back above VWAP
    reclaim_bars_left: int = 0                # Countdown for new-high confirmation
    trigger_high: float = 0.0                 # High of confirmation candle
    entry_price: float = 0.0
    stop_price: float = 0.0                   # Below VWAP low
    r_value: float = 0.0
    last_bar: Optional[dict] = None
    avg_volume: float = 0.0                   # Running avg for volume comparison
```

#### State Machine

```
IDLE ──[on_graduation]──► WATCHING
                              │
                    [cooldown expires]
                              │
                              ▼
                         WATCHING ◄─────────────────┐
                              │                      │
                    [close > VWAP: ever_above = True] │
                    [close < VWAP AND ever_above]    │
                              │                      │
                              ▼                      │
                        BELOW_VWAP                   │
                              │                      │
                    [close > VWAP with volume]       │
                              │                      │
                              ▼                      │
                        RECLAIMED                    │
                              │                      │
                    [next bar makes new high]        │
                              │                      │
                              ▼                      │
                          ARMED ──[tick break]──► Entry signal
                              │
                    [window expires / reset]──────────┘
```

#### on_graduation(ctx)

```python
def on_graduation(self, ctx: GraduationContext) -> None:
    if not EPL_VR_ENABLED:
        return
    state = self._get_or_create_state(ctx.symbol)
    state.graduation_ctx = ctx
    state.phase = "WATCHING"
    state.cooldown_bars = EPL_VR_COOLDOWN_BARS
    state.bars_since_graduation = 0
    state.ever_above_vwap_post_grad = False
    state.below_vwap_bars = 0
    state.below_vwap_low = float('inf')
    log(f"[EPL:VR] {ctx.symbol} graduated → WATCHING (cooldown={EPL_VR_COOLDOWN_BARS} bars)")
```

#### on_bar(symbol, bar) — The Core Detection

```python
def on_bar(self, symbol: str, bar: dict) -> Optional[EntrySignal]:
    if not EPL_VR_ENABLED:
        return None
    state = self._states.get(symbol)
    if not state or state.phase == "IDLE":
        return None

    state.bars_since_graduation += 1
    state.last_bar = bar
    vwap = bar.get("vwap")
    if not vwap:
        return None

    # Update running avg volume
    if state.avg_volume == 0:
        state.avg_volume = bar["v"]
    else:
        state.avg_volume = state.avg_volume * 0.8 + bar["v"] * 0.2

    # --- COOLDOWN ---
    if state.cooldown_bars > 0:
        state.cooldown_bars -= 1
        return None

    # --- WATCHING: Wait for price to be above VWAP, then dip below ---
    if state.phase == "WATCHING":
        if bar["c"] > vwap:
            state.ever_above_vwap_post_grad = True
        elif state.ever_above_vwap_post_grad and bar["c"] < vwap:
            # Dipped below VWAP — transition
            state.phase = "BELOW_VWAP"
            state.below_vwap_bars = 1
            state.below_vwap_low = bar["l"]
            log(f"[EPL:VR] {symbol} BELOW_VWAP (close={bar['c']:.2f} < vwap={vwap:.2f})")
        return None

    # --- BELOW_VWAP: Track how long below, wait for reclaim ---
    if state.phase == "BELOW_VWAP":
        state.below_vwap_low = min(state.below_vwap_low, bar["l"])

        # Severe loss check — stock dropped too far, give up
        if vwap > 0:
            vwap_dist_pct = ((vwap - bar["l"]) / vwap) * 100
            if vwap_dist_pct > EPL_VR_SEVERE_LOSS_PCT:
                log(f"[EPL:VR] {symbol} RESET: severe VWAP loss ({vwap_dist_pct:.1f}% below)")
                self._reset_to_watching(state)
                return None

        if bar["c"] > vwap:
            # RECLAIM! Check volume
            vol_ok = state.avg_volume > 0 and bar["v"] >= (state.avg_volume * EPL_VR_VOL_MULT)
            if vol_ok and bar["green"]:
                state.phase = "RECLAIMED"
                state.reclaim_bar = bar
                state.reclaim_bars_left = EPL_VR_RECLAIM_WINDOW
                log(f"[EPL:VR] {symbol} RECLAIMED (vol={bar['v']:.0f}, "
                    f"avg={state.avg_volume:.0f}, mult={bar['v']/state.avg_volume:.1f}x)")
            else:
                # Reclaim without volume — weak, reset
                log(f"[EPL:VR] {symbol} RESET: reclaim without volume confirmation")
                self._reset_to_watching(state)
        else:
            state.below_vwap_bars += 1
            if state.below_vwap_bars > EPL_VR_MAX_BELOW_BARS:
                log(f"[EPL:VR] {symbol} RESET: too long below VWAP ({state.below_vwap_bars} bars)")
                self._reset_to_watching(state)
        return None

    # --- RECLAIMED: Wait for new-high confirmation bar ---
    if state.phase == "RECLAIMED":
        if bar["c"] < vwap:
            # Lost VWAP again — reset
            log(f"[EPL:VR] {symbol} RESET: lost VWAP after reclaim")
            self._reset_to_watching(state)
            return None

        # Check if this bar makes a new high above reclaim bar
        if bar["h"] > state.reclaim_bar["h"] and bar["green"]:
            # ARM
            entry = bar["h"]
            stop = state.below_vwap_low - EPL_VR_STOP_PAD
            r = entry - stop
            if r < EPL_VR_MIN_R:
                log(f"[EPL:VR] {symbol} RESET: R too small ({r:.4f})")
                self._reset_to_watching(state)
                return None

            state.phase = "ARMED"
            state.trigger_high = entry
            state.entry_price = entry
            state.stop_price = stop
            state.r_value = r
            log(f"[EPL:VR] {symbol} ARMED: trigger={entry:.2f}, stop={stop:.2f}, R={r:.4f}")
            return None  # Wait for tick break

        state.reclaim_bars_left -= 1
        if state.reclaim_bars_left <= 0:
            log(f"[EPL:VR] {symbol} RESET: reclaim window expired (no new high)")
            self._reset_to_watching(state)
        return None

    return None  # ARMED handled in on_tick
```

#### on_tick(symbol, price, size) — Trigger Break

```python
def on_tick(self, symbol: str, price: float, size: int) -> Optional[EntrySignal]:
    if not EPL_VR_ENABLED:
        return None
    state = self._states.get(symbol)
    if not state or state.phase != "ARMED":
        return None

    if price >= state.trigger_high:
        signal = EntrySignal(
            symbol=symbol,
            strategy=self.name,
            entry_price=state.entry_price,
            stop_price=state.stop_price,
            target_price=None,  # Trail-only
            position_size_pct=1.0,  # Full EPL notional
            reason=f"vwap_reclaim trigger={state.trigger_high:.2f} below_low={state.below_vwap_low:.2f}",
            confidence=self._compute_confidence(state),
        )
        log(f"[EPL:VR] {symbol} ENTRY SIGNAL @ {price:.2f} (break {state.trigger_high:.2f})")
        self._reset_to_watching(state)
        return signal

    return None
```

#### manage_exit() — VR's Own Exit Rules

```python
def manage_exit(self, symbol: str, price: float, bar: Optional[dict]) -> Optional[ExitSignal]:
    """
    EPL VWAP Reclaim exit rules:
    1. Hard stop at below_vwap_low (stop_price)
    2. Trail at 1.5R once profitable
    3. VWAP loss = exit (price drops back below VWAP after entry)
    4. Prior HOD target: take profit at graduation HOD
    5. Time stop: 5 bars without new high
    """
    state = self._states.get(symbol)
    if not state or not getattr(state, '_in_trade', False):
        return None

    # 1. Hard stop
    if price <= state.stop_price:
        return ExitSignal(
            symbol=symbol, strategy=self.name,
            exit_price=price, exit_reason="epl_vr_stop_hit", exit_pct=1.0)

    # 2. Trail at 1.5R
    pnl_r = (price - state.entry_price) / state.r_value if state.r_value > 0 else 0
    if pnl_r >= 1.5:
        trail_stop = getattr(state, '_trade_peak', state.entry_price) - (1.5 * state.r_value)
        if not hasattr(state, '_trail_stop') or trail_stop > getattr(state, '_trail_stop', 0):
            state._trail_stop = trail_stop
        if price <= state._trail_stop:
            return ExitSignal(
                symbol=symbol, strategy=self.name,
                exit_price=price, exit_reason=f"epl_vr_trail_exit(R={pnl_r:.1f})", exit_pct=1.0)

    # 3. VWAP loss (on bar close)
    if bar and bar.get("vwap") and bar["c"] < bar["vwap"]:
        return ExitSignal(
            symbol=symbol, strategy=self.name,
            exit_price=price, exit_reason="epl_vr_vwap_loss", exit_pct=1.0)

    # 4. Prior HOD target — take profit if reaching graduation HOD
    if state.graduation_ctx and price >= state.graduation_ctx.hod_at_graduation:
        return ExitSignal(
            symbol=symbol, strategy=self.name,
            exit_price=price, exit_reason="epl_vr_hod_target", exit_pct=1.0)

    # 5. Time stop (on bar close)
    if bar:
        if not hasattr(state, '_bars_in_trade'):
            state._bars_in_trade = 0
            state._trade_peak = state.entry_price
            state._bars_no_new_high = 0
        state._bars_in_trade += 1
        if bar["h"] > getattr(state, '_trade_peak', 0):
            state._trade_peak = bar["h"]
            state._bars_no_new_high = 0
        else:
            state._bars_no_new_high = getattr(state, '_bars_no_new_high', 0) + 1
        if state._bars_no_new_high >= 5:
            return ExitSignal(
                symbol=symbol, strategy=self.name,
                exit_price=price, exit_reason=f"epl_vr_time_exit({state._bars_no_new_high}bars)", exit_pct=1.0)

    return None
```

**Exit rule 4 (HOD target) is new to VR.** The logic: if the stock reclaims VWAP and runs back to the prior session HOD (which was the HOD when it graduated), that's a natural resistance level. Take profit there. This is a defined target that MP re-entry doesn't have, because VR entries are deeper (from below VWAP) so they have a clear target above.

#### _compute_confidence()

```python
def _compute_confidence(self, state: VRState) -> float:
    score = 0.5
    # Short time below VWAP = higher confidence (quick dip, not a fade)
    if state.below_vwap_bars <= 5:
        score += 0.2
    # Shallow dip below VWAP = higher confidence
    if state.graduation_ctx and state.below_vwap_low > (state.graduation_ctx.vwap_at_graduation * 0.95):
        score += 0.1
    # Early after graduation
    if state.bars_since_graduation <= 15:
        score += 0.1
    return min(score, 1.0)
```

---

## Integration

### Register in simulate.py

Near the EPL framework initialization, alongside MP re-entry registration:

```python
from epl_vwap_reclaim import EPLVwapReclaim, EPL_VR_ENABLED

_epl_vr = EPLVwapReclaim()
if EPL_ENABLED and EPL_VR_ENABLED:
    _epl_registry.register(_epl_vr)
```

The existing execution hooks (bar processing, tick processing, entry/exit execution) from the MP re-entry wiring will automatically handle VR too — the registry collects signals from ALL registered strategies and the arbitrator picks the best one.

### Register in bot_v3_hybrid.py

Same pattern.

### VWAP in bar dict

Confirm the bar dict passed to `on_bar()` includes `"vwap"`. The MP re-entry wiring (commit 65ce7cf) should already pass this. If not, add it.

---

## Add to .env

```bash
# === EPL: VWAP Reclaim ===
WB_EPL_VR_ENABLED=0
WB_EPL_VR_COOLDOWN_BARS=3
WB_EPL_VR_VOL_MULT=1.5
WB_EPL_VR_RECLAIM_WINDOW=3
WB_EPL_VR_MAX_BELOW_BARS=15
WB_EPL_VR_MIN_R=0.06
WB_EPL_VR_STOP_PAD=0.01
WB_EPL_VR_SEVERE_LOSS_PCT=20.0
```

---

## How VR and MP Re-Entry Work Together

These strategies are complementary, not competing:

| Scenario | MP Re-Entry | VR |
|----------|-------------|-----|
| Shallow pullback (stays above VWAP) | ARMS and enters | Stays in WATCHING (no dip below VWAP) |
| Deep pullback (dips below VWAP) | Blocked by VWAP floor gate | ARMS when stock reclaims VWAP with volume |
| Fading stock (collapses below VWAP) | Blocked by VWAP floor gate | Reset by severe_loss or max_below_bars |

The MP VWAP floor gate (`WB_EPL_MP_VWAP_FLOOR=1`) explicitly hands off deep-pullback setups to VR. MP catches the shallow pullbacks, VR catches the deep ones.

---

## Testing

### Backtest: Same 63-day megatest as MP re-entry

```bash
# Run with BOTH MP re-entry AND VR enabled
WB_EPL_ENABLED=1 WB_EPL_MP_ENABLED=1 WB_EPL_VR_ENABLED=1 WB_EPL_MP_VWAP_FLOOR=1 \
    python run_ytd_v2_backtest.py
```

### Key checks

1. **Does VR produce any trades?** The whole question is whether the pattern exists in the post-2R window. If VR produces 0 trades even with EPL graduation filter, the pattern truly doesn't exist for these stocks.

2. **Does VR catch what MP misses?** With the MP VWAP floor gate ON, there should be deep-pullback setups that MP skips and VR catches.

3. **SQ unchanged.** VR is additive — SQ behavior must be identical to VR OFF.

4. **MP unchanged.** VR runs alongside MP, not replacing it. MP trades should be the same.

### Report format

| Metric | SQ Only | SQ + MP | SQ + MP + VR | Delta (VR add) |
|--------|---------|---------|--------------|-----------------|
| Total P&L | $169,227 | ??? | ??? | ??? |
| Trades | 29 | ??? | ??? | ??? |
| VR trades | 0 | 0 | ??? | ??? |
| VR win rate | — | — | ??? | — |
| VR net P&L | $0 | $0 | ??? | ??? |

---

## What NOT To Do

1. **Do NOT modify `vwap_reclaim_detector.py`.** Build `epl_vwap_reclaim.py` as a new file. The standalone VR code stays untouched.
2. **Do NOT remove the R-cap from standalone VR.** Only EPL VR has no R-cap. Standalone VR (if ever re-enabled) keeps its original thresholds.
3. **Do NOT use SQ exits.** VR has its own exit rules including the HOD target.
4. **Do NOT change MP re-entry behavior.** VR is additive.

---

## Logging

All log lines prefixed with `[EPL:VR]`:
- `[EPL:VR] STAK graduated → WATCHING (cooldown=3 bars)`
- `[EPL:VR] STAK BELOW_VWAP (close=4.10 < vwap=4.25)`
- `[EPL:VR] STAK RECLAIMED (vol=85000, avg=42000, mult=2.0x)`
- `[EPL:VR] STAK ARMED: trigger=4.35, stop=4.05, R=0.30`
- `[EPL:VR] STAK ENTRY SIGNAL @ 4.36 (break 4.35)`
- `[EPL:VR] STAK EXIT: epl_vr_hod_target, P&L=$800.00`
- `[EPL:VR] STAK RESET: too long below VWAP (16 bars)`
- `[EPL:VR] STAK RESET: severe VWAP loss (22.5% below)`

---

## Deliverables

1. `epl_vwap_reclaim.py` — Full strategy implementation
2. Registration wired in `simulate.py` and `bot_v3_hybrid.py`
3. `.env` additions (8 new vars)
4. `test_epl_vwap_reclaim.py` — Unit tests
5. 63-day megatest: SQ + MP + VR combined
6. Comparison table vs SQ-only and SQ+MP baselines

## Commit

```
Add EPL VWAP Reclaim strategy

Post-2R graduation strategy for deep pullbacks that dip below VWAP.
Complements MP re-entry (shallow pullbacks above VWAP). Salvages state
machine from standalone vwap_reclaim_detector.py with EPL-specific
thresholds (no R-cap, wider below-bars limit).

WB_EPL_VR_ENABLED=0 by default. Includes HOD target exit.
```
