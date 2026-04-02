# Directive: EPL MP Re-Entry — VWAP Floor Gate

## Priority: P0 (quick tweak + re-run megatest)

---

## Context

The EPL MP re-entry megatest produced +$201K (+$32K over baseline). But of the 10 confirmed EPL trades, 7 were losers, and **6 of those 7 losers exited via `epl_mp_vwap_loss`**. The re-entry triggers while the stock is still pulling back through VWAP, then immediately gets stopped out on VWAP loss.

The fix: don't ARM if the pullback low is already at or below VWAP. If the pullback breaches VWAP, the stock isn't pulling back — it's breaking down. This should filter the 6 VWAP-loss losers (-$5,078) while preserving the ROLR winner (+$22,930) which had a shallow pullback well above VWAP.

---

## What To Change

### File: `epl_mp_reentry.py`

#### 1. Add env var

```python
EPL_MP_VWAP_FLOOR = int(os.environ.get("WB_EPL_MP_VWAP_FLOOR", "1"))  # ON by default
```

#### 2. Add VWAP floor check in on_bar()

In the PULLBACK state, when tracking pullback_low, also check against VWAP. If the pullback bar's low drops below VWAP, reset to WATCHING:

```python
# Inside PULLBACK state, after updating pullback_low:
if EPL_MP_VWAP_FLOOR and bar.get("vwap") and state.pullback_low < bar["vwap"]:
    log(f"[EPL:MP] {symbol} RESET: pullback breached VWAP "
        f"(low={state.pullback_low:.2f} < vwap={bar['vwap']:.2f})")
    state.phase = "WATCHING"
    state.pullback_count = 0
    state.pullback_low = float('inf')
    return None
```

Also check in the confirmation/ARM stage — if the pullback_low that was recorded is below VWAP at the time of ARM, block it:

```python
# Before setting phase = "ARMED":
if EPL_MP_VWAP_FLOOR and bar.get("vwap") and state.pullback_low < bar["vwap"]:
    log(f"[EPL:MP] {symbol} RESET: pullback low below VWAP at ARM "
        f"(pb_low={state.pullback_low:.2f} < vwap={bar['vwap']:.2f})")
    state.phase = "WATCHING"
    state.pullback_count = 0
    state.pullback_low = float('inf')
    return None
```

#### 3. VWAP access

The `bar` dict passed to `on_bar()` should already contain `"vwap"` — the simulator wiring (commit 65ce7cf) builds the bar dict with VWAP. Verify this is present. If not, wire it in from `bar_builder.vwap`.

---

## Add to .env

```bash
WB_EPL_MP_VWAP_FLOOR=1           # Block EPL MP ARM if pullback low < VWAP (default ON)
```

---

## Testing

### Re-run the full 63-day megatest

Same config as commit 7920af2 but with the VWAP floor gate ON (which it is by default):

```bash
# Should produce same or better P&L — the 6 VWAP-loss losers should be filtered
# ROLR's +$22,930 EPL trade should survive (shallow pullback above VWAP)
```

### Report format

Compare against the 7920af2 baseline:

| Metric | Before (7920af2) | After (VWAP floor) | Delta |
|--------|-------------------|---------------------|-------|
| Total P&L | $201,461 | ??? | ??? |
| Trades | 55 | ??? | ??? |
| EPL trades | 10 | ??? | ??? |
| EPL win rate | 30% | ??? | ??? |
| EPL net P&L | +$18,172 | ??? | ??? |
| epl_mp_vwap_loss count | 8 | ??? | ??? |

**Key checks:**
1. ROLR 01-14 EPL trade still fires (+$22,930 or similar)
2. The 6 VWAP-loss losers are blocked (BGL x2, NPT, GXAI, ACCL, ELAB T2)
3. SQ trades completely unchanged
4. No new regressions introduced

---

## What NOT To Do

1. **Do NOT change the VWAP loss exit.** The exit is doing its job (cutting losses quickly). The problem is the ENTRY, not the exit.
2. **Do NOT change cooldown or other parameters.** One variable at a time.
3. **Do NOT change SQ behavior.** This only affects EPL MP re-entry arming.

---

## Commit

```
Add VWAP floor gate to EPL MP re-entry

Block ARM when pullback low < VWAP. 6 of 7 EPL losers entered during
pullbacks that breached VWAP then immediately got stopped out on VWAP
loss. This gate filters those entries while preserving runners (ROLR)
that pull back shallowly above VWAP.

WB_EPL_MP_VWAP_FLOOR=1 by default.
```
