# DIRECTIVE: Wave Breakout Tradability Gate (Chop Filter)

**Date:** May 6, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P0 — fix this BEFORE re-tackling tick-by-tick migration  
**Branch:** `v2-ibkr-migration`  
**Predecessor:** `cowork_reports/2026-05-06_morning_choppy_stock_analysis.md`

---

## Problem (Confirmed by Today's Session)

The Wave Breakout detector has no concept of *"is this stock tradable right now?"* It scores wave shapes and arms entries, but doesn't gate on whether the live tape can actually support a profitable exit. Today's session demonstrated this brutally:

| # | Symbol | Quality of tape | Outcome |
|---:|---|---|---:|
| 1 | CLNN | Choppy, low volume, oscillating around VWAP | win by luck (no-fill rescue) |
| 2 | FATN | Single-print bars, dead tape | −$987 |
| 3 | FATN | Same dead tape, immediate re-entry | −$656 |
| 4 | PMAX | Real momentum, persistent VWAP separation, real volume | +$608 |

Same detector, same scoring, same risk model. **The only thing that separated winners from losers was the tradability of the live tape.** The bot must learn to refuse entries on stocks that don't have tradable tape, regardless of how clean the wave pattern looks.

## The Four Gates

Add a **pre-submission tradability check** in `place_wave_breakout_entry()`. ALL four gates must pass; if any fails, refuse the entry, log `[CHOP_REJECT]`, and blacklist the symbol for 30 minutes.

### Gate 1: R ≥ max(2.5% of entry, 3× spread)

**Why:** A stop ~1% from entry on a stock with even a 0.5% bid-ask spread has no buffer for spread + slippage + normal noise. Today's losers had R-distances of 0.82-1.23%; PMAX had 3.65%.

```python
def gate_r_distance(entry: float, stop: float, current_spread: float | None) -> tuple[bool, str]:
    r_dollars = entry - stop
    r_pct = r_dollars / entry
    
    # Hard floor: R must be at least 2.5% of entry price
    if r_pct < 0.025:
        return False, f"R={r_pct*100:.2f}% < 2.5% floor"
    
    # If we have a real spread, R must be at least 3x it
    if current_spread is not None and current_spread > 0:
        if r_dollars < 3 * current_spread:
            return False, f"R=${r_dollars:.4f} < 3×spread=${3*current_spread:.4f}"
    
    return True, "ok"
```

If real spread isn't available, the 2.5% floor alone is sufficient (it acts as a price-based proxy).

### Gate 2: VWAP Distance ≥ +1.5% for Longs

**Why:** PMAX held +3.3% to +10.5% above VWAP throughout the setup. FATN/CLNN oscillated within ±2-3%. VWAP separation is a clean proxy for directional commitment by buyers.

```python
def gate_vwap_distance(entry: float, vwap: float, side: str) -> tuple[bool, str]:
    if vwap is None or vwap <= 0:
        return False, "vwap unavailable"
    
    dist_pct = (entry - vwap) / vwap * 100
    
    if side == "long":
        if dist_pct < 1.5:
            return False, f"vwap_dist={dist_pct:+.2f}% < +1.5%"
    else:  # short
        if dist_pct > -1.5:
            return False, f"vwap_dist={dist_pct:+.2f}% > -1.5%"
    
    return True, "ok"
```

### Gate 3: 5-Bar Avg Volume ≥ 5,000 Shares

**Why:** PMAX 5-min bars: 8K-52K shares. FATN: 5-1,011 shares. A 50-1000x difference in tradable volume. The detector cannot extract a profitable trade from tape that nobody else is trading.

```python
def gate_volume(recent_bars: list[Bar]) -> tuple[bool, str]:
    if len(recent_bars) < 5:
        return False, f"only {len(recent_bars)} bars available, need 5"
    
    avg_vol = sum(b.volume for b in recent_bars[-5:]) / 5
    
    if avg_vol < 5000:
        return False, f"avg_5bar_vol={avg_vol:.0f} < 5000"
    
    return True, "ok"
```

Note: `recent_bars` should be 5-minute bars, not 1-minute. The detector uses 1-min bars for arming, but the tradability check operates on the 5-min context to filter dead tape.

### Gate 4: At Most 1 of Last 5 Bars Is Degenerate

**Why:** Single-print bars (O=H=L=C) mean ONE trade or ZERO trades happened in that 5-min window. The detector replays these as if they're real waves. They're not.

```python
def gate_degenerate_bars(recent_bars: list[Bar]) -> tuple[bool, str]:
    if len(recent_bars) < 5:
        return False, f"only {len(recent_bars)} bars available, need 5"
    
    last5 = recent_bars[-5:]
    degenerate_count = sum(1 for b in last5 if b.high == b.low == b.close == b.open)
    
    if degenerate_count > 1:
        return False, f"{degenerate_count}/5 last bars are degenerate (O=H=L=C)"
    
    return True, "ok"
```

## Composite Gate Function

```python
def check_tradability(
    symbol: str,
    entry: float,
    stop: float,
    vwap: float | None,
    current_spread: float | None,
    recent_5min_bars: list[Bar],
    side: str = "long",
) -> tuple[bool, list[str]]:
    """Returns (passed, list_of_reasons).
    
    All four gates must pass. Returns reasons for ALL failed gates so logs are informative.
    """
    failures = []
    
    ok, reason = gate_r_distance(entry, stop, current_spread)
    if not ok: failures.append(f"R: {reason}")
    
    ok, reason = gate_vwap_distance(entry, vwap, side)
    if not ok: failures.append(f"VWAP: {reason}")
    
    ok, reason = gate_volume(recent_5min_bars)
    if not ok: failures.append(f"VOL: {reason}")
    
    ok, reason = gate_degenerate_bars(recent_5min_bars)
    if not ok: failures.append(f"BARS: {reason}")
    
    return (len(failures) == 0, failures)
```

## Auto-Blacklist on Reject

When `check_tradability` rejects a symbol, blacklist it for 30 minutes. The same chop conditions don't disappear in the next 60 seconds — today's FATN was chop at 11:35 AND at 12:03. A simple cooldown prevents the bot from re-arming on the same dead tape.

```python
# In bot state
state.choppy_until: dict[str, datetime] = {}

# At top of place_wave_breakout_entry, BEFORE the tradability check:
def is_blacklisted(symbol: str) -> bool:
    until = state.choppy_until.get(symbol)
    if until is None:
        return False
    if datetime.now(ET) >= until:
        del state.choppy_until[symbol]
        return False
    return True

def add_to_blacklist(symbol: str, minutes: int = 30):
    state.choppy_until[symbol] = datetime.now(ET) + timedelta(minutes=minutes)

# Then in the entry path:
if is_blacklisted(symbol):
    log.info(f"[CHOP_REJECT] {symbol} still blacklisted until {state.choppy_until[symbol]:%H:%M:%S}")
    return

passed, reasons = check_tradability(...)
if not passed:
    log.info(f"[CHOP_REJECT] {symbol} failed: {' | '.join(reasons)}")
    add_to_blacklist(symbol, minutes=30)
    return

# ... existing entry logic continues here ...
```

## Logging Convention

Every reject must log a structured line for post-session analysis:

```
[CHOP_REJECT] FATN failed: VWAP: vwap_dist=+1.20% < +1.5% | VOL: avg_5bar_vol=824 < 5000 | BARS: 3/5 last bars are degenerate (O=H=L=C)
[CHOP_BLACKLIST] FATN blacklisted until 12:33:00 ET (30min)
[CHOP_BLACKLIST_HIT] FATN still blacklisted (re-arm rejected) until 12:33:00 ET
```

End-of-session summary log:

```
[CHOP_SUMMARY] Day total: 7 entries rejected (4 unique symbols), 3 blacklist hits prevented re-entry
```

## Where the Filter Lives

In `bot_alpaca_subbot.py` (and `bot_v3_hybrid.py` once mirrored), inside `place_wave_breakout_entry()`. **Not** in the detector. Reasons:

- Easy to backtest in isolation (run gate function on existing tick cache trade list)
- Can be toggled with a single env var without retuning detector
- `[CHOP_REJECT]` is its own clean event type for log analysis
- Detector tuning and tradability tuning happen on different schedules

## Env Vars

```bash
# Master toggle
WB_WB_TRADABILITY_GATE_ENABLED=1   # default ON

# Gate thresholds (tunable from .env without code changes)
WB_WB_GATE_MIN_R_PCT=0.025         # R must be ≥ 2.5% of entry
WB_WB_GATE_MIN_R_SPREAD_MULT=3.0   # R must be ≥ 3× current spread (if spread known)
WB_WB_GATE_MIN_VWAP_DIST_PCT=1.5   # entry must be ≥ +1.5% above VWAP for longs
WB_WB_GATE_MIN_5BAR_VOL=5000       # avg 5-min volume over last 5 bars
WB_WB_GATE_MAX_DEGENERATE_BARS=1   # max O=H=L=C bars in last 5

# Blacklist
WB_WB_CHOP_BLACKLIST_MINUTES=30    # 30 min cooldown after a reject
```

## Backtest Validation

Before deploying, run the gate against the existing tick cache to prove it doesn't kill historical winners:

1. Replay every entry from the V8b backtest trade log against `check_tradability()`
2. For each entry, compute the gate inputs at entry time using the cached tick data
3. Bucket entries into:
   - **Passed gate, was a winner** — preserved (good)
   - **Passed gate, was a loser** — gate didn't help here (acceptable if rare)
   - **Rejected gate, was a loser** — saved (good)
   - **Rejected gate, was a winner** — false positive (acceptable in moderation)

**Acceptance criteria for deploy:**

| # | Metric | Threshold |
|---:|---|:---:|
| 1 | % of historical losers rejected | ≥ 50% |
| 2 | % of historical winners preserved | ≥ 80% |
| 3 | Net P&L on remaining trades after gate | ≥ 90% of pre-gate net P&L |
| 4 | Top-10 winners (by P&L) preserved | ≥ 9 of 10 |

If criterion 4 fails (gate kills the fat-tail trades the strategy depends on), the gate is too aggressive. Loosen the highest-impact threshold (probably the +1.5% VWAP minimum) and re-test.

Save validation results to: `cowork_reports/2026-05-XX_tradability_gate_backtest.md`

## What NOT to Do

- ❌ Do NOT modify `wave_breakout_detector.py` itself. The gate is bot-side, not detector-side.
- ❌ Do NOT add complex multi-condition logic. Four boolean gates, all must pass. Period.
- ❌ Do NOT run live without backtest validation passing all four acceptance criteria.
- ❌ Do NOT skip the blacklist. Today's FATN re-entry was the costliest mistake of the session.
- ❌ Do NOT use 1-minute bars for the volume/degenerate-bar checks. 5-minute context is needed to capture true tradability.
- ❌ Do NOT touch tick-by-tick code. That's the next priority, not this one.

## Acceptance Gate (Live Deploy)

After backtest validation passes:

1. Deploy to sub-bot only first (bot_alpaca_subbot.py)
2. Run for 1 trading day with `WB_WB_TRADABILITY_GATE_ENABLED=1`
3. Audit logs for `[CHOP_REJECT]` events — verify the specific stocks rejected match the criteria visually
4. Once verified working, mirror to `bot_v3_hybrid.py` (main bot)

## Files Touched

```
bot_alpaca_subbot.py      # Stage 1: add gate function, blacklist, [CHOP_REJECT] logging
bot_v3_hybrid.py          # Stage 2: mirror once sub-bot verified
.env.example              # add new WB_WB_GATE_* vars
cowork_reports/
  2026-05-XX_tradability_gate_backtest.md   # validation results
```

---

## Next Up After This Lands

The tick-by-tick migration (`DIRECTIVE_TICKBYTICK_MIGRATION.md`) is the next P0. The 80% live data gap is structurally limiting how well the bot can read the tape, and the chop filter helps but doesn't fix it.

Today's `WB_TBT_ENABLED` failure (Tier 1 symbols going data-blind for 1-6.5 hours) means the existing migration code has a bug in the `_drain_tick_by_tick_ticker` dispatch path. CC must:
1. First: ship the tradability gate (this directive)
2. Then: diagnose offline why `ticker.tickByTicks` events aren't being delivered for Tier 1 subscribed symbols
3. Then: fix and re-attempt the migration

The chop filter provides immediate value AT today's data quality. The tick-by-tick migration provides the structural fix to data quality itself. Both matter.

---

*Detector picks setups. Tradability gate decides whether the tape can actually deliver. Today's losers all failed at least 3 of the 4 gates. PMAX passed all 4.*
