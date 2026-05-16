# Confirmation Plugins — Unit Test Report

**Date:** 2026-05-17 (Wave 1, Agent D)
**For:** Cowork / Manny
**Scope:** `framework/confirmations/*` modules + `tests/framework/test_confirmations.py`
**Status:** All 83 unit tests pass. Acceptance criteria met (>= 10 cases per pattern).

---

## TL;DR

Built six confirmation plugins implementing `ConfirmationProtocol`:
`SignalCandle`, `BreakoutCandle`, `Acceptance`, `Rejection`, `VolumeConfirm`,
`L2Confirm`. Each plugin is pure (state-free), type-hinted, returns a
`ConfirmationResult` for both pass and reject paths (never raises on
malformed inputs), and ships with a focused unit-test suite. All 83 tests
pass under pytest in `tests/framework/test_confirmations.py`.

These plugins are the building blocks that Wave 2 strategy specs
(ORB / VWAP / PDH-PDL / Round-Number) compose via YAML `confirmation_rule:`
sections. No existing live code was modified.

---

## Test coverage summary

| Plugin           | File                                        | Tests | Status |
|------------------|---------------------------------------------|-------|--------|
| SignalCandle     | `framework/confirmations/signal_candle.py`  | 17    | pass   |
| BreakoutCandle   | `framework/confirmations/breakout_candle.py`| 13    | pass   |
| Acceptance       | `framework/confirmations/acceptance.py`     | 12    | pass   |
| Rejection        | `framework/confirmations/rejection.py`      | 13    | pass   |
| VolumeConfirm    | `framework/confirmations/volume_confirm.py` | 11    | pass   |
| L2Confirm        | `framework/confirmations/l2_confirm.py`     | 15    | pass   |
| Invariants       | (cross-cutting)                             |  2    | pass   |
| **Total**        |                                             | **83**| pass   |

Run: `python -m pytest tests/framework/test_confirmations.py -v` -> `83 passed in 0.06s`.

---

## Pattern criteria (exact)

### SignalCandle — doji / hammer / shooting star

Per directive Section "Signal Candle confirmation":

- **Doji**: `body / range < 0.10`
- **Hammer**: `lower_wick > 2 * body  AND  body_ratio < 0.30  AND  body in upper 30% of range`
- **Shooting star**: `upper_wick > 2 * body  AND  body_ratio < 0.30  AND  body in lower 30% of range`

Where:
- `body = |close - open|`
- `range = high - low`
- `body_ratio = body / range`
- `upper_wick = high - max(open, close)`
- `lower_wick = min(open, close) - low`
- "body in upper 30%" means `min(open, close) >= low + 0.7 * range`
- "body in lower 30%" means `max(open, close) <= low + 0.3 * range`

Volume confirmation (when `require_volume_increase=True`):
- `entry.volume > prior.volume`

Pattern priority: tries `patterns` list in configured order; first match wins.
A bar satisfying both doji and hammer returns "doji" if doji is listed first.

**Sample bars:**

| Bar         | OHLC                      | body_ratio | Verdict           |
|-------------|---------------------------|------------|-------------------|
| doji        | O=10.00, H=10.50, L=9.50, C=10.00 | 0.00 | doji              |
| just-doji   | O=10.00, H=10.50, L=9.50, C=10.095 | 0.095 | doji              |
| no-doji     | O=10.00, H=10.50, L=9.50, C=10.105 | 0.105 | rejected (>0.10) |
| hammer      | O=10.80, H=10.95, L=10.00, C=10.95 | 0.15 | hammer            |
| shooting-*  | O=10.00, H=10.95, L=10.00, C=10.15 | 0.15 | shooting_star     |

### BreakoutCandle — close-beyond-level + volume

- **Long**: `bar.close > level.price * (1 + min_breakout_pct)` (default 0.0002 = 2 bps)
- **Short**: mirror (`< level.price * (1 - min_breakout_pct)`)
- **Volume**: `entry.volume >= min_vol_mult * baseline` where baseline =
  mean of prior 20 bars' volumes (fewer if history short)

Direction inferred from `level.kind` (PDH/ORH/ROUND/PM_HIGH/BOX_TOP/VAH/POC/
ANCHORED_VWAP/VWAP/SWING_HIGH -> long; PDL/ORL/PM_LOW/BOX_BOTTOM/VAL/SWING_LOW
-> short). Override via `direction="long"|"short"|"auto"`.

`require_close_beyond=False` allows wick breakouts (bar.high / bar.low test
instead of bar.close).

### Acceptance — N consecutive bars inside zone

- `min_bars` consecutive bars (default 2) whose `close` is in `[zone_low, zone_high]`
- Zone bounds may be fixed floats OR callables `(level, bars) -> float`
  (useful when bounds derive from level metadata such as `level.metadata["val"]`)
- Inclusive boundary: `close == zone_low` or `close == zone_high` counts as
  inside.

### Rejection — failed-test pattern

For a resistance level (long-side break failed -> short fade):
- Some bar in the last `lookback_bars` (default 2) had `high > level.price`
- AND `entry.close < level.price`

For a support level (mirrored, long entry).

Direction inferred from `level.kind`: resistance kinds = PDH/ORH/VAH/PM_HIGH/
BOX_TOP/SWING_HIGH; support kinds = PDL/ORL/VAL/PM_LOW/BOX_BOTTOM/SWING_LOW;
other kinds default to resistance. Override via `side` arg.

Returns `pattern_name="rejection_down"` (resistance fade) or
`"rejection_up"` (support fade).

### VolumeConfirm — generic volume threshold

- `entry.volume / baseline >= min_relative_volume`
- Baseline modes:
  - `prior_bar`: `bars[-2].volume`
  - `20_bar_avg`: mean of `bars[-21:-1]`
  - `session_avg`: mean of all bars except entry

Falls back to fewer bars if 20 not available (reason string indicates
actual window used).

### L2Confirm — wraps L2 state dict

Consumes the exact dict shape returned by `l2_signals.L2SignalDetector.get_state()`:
`{imbalance, imbalance_trend, bid_stacking, bid_stack_levels, large_bid,
large_ask, spread_pct, ask_thinning, signals}`.

- Spread veto: `spread_pct > max_spread_pct` -> rejected
- Long: `imbalance >= min_imbalance` (default 0.55); optionally requires `bid_stacking`
- Short: `imbalance <= 1 - min_imbalance`; optionally requires `require_ask_stacking`
  (interpreted as "no bid stacking OR an ask-side signal present")
- `pass_through_on_missing=True`: when `l2_state is None`, returns
  `confirmed=True, strength=0.0` (don't veto strategies in backtests without L2)

The actual L2 detection is unchanged; this is a thin adapter for the
framework protocol.

---

## Edge-case handling (all return ConfirmationResult, never raise)

| Edge case                       | Behavior                                                  |
|---------------------------------|-----------------------------------------------------------|
| Empty bars list                 | `confirmed=False, reason="no bars"`                       |
| `range_size <= 0` (zero-range)  | `confirmed=False, reason="zero range"`                    |
| NaN in OHLC                     | `confirmed=False, reason="nan ohlc"`                      |
| NaN in volume                   | `confirmed=False, reason="nan ..."`                       |
| Missing prior bar (vol check)   | `confirmed=False, reason="no prior bar for volume check"` |
| Invalid level price (<=0 / NaN) | `confirmed=False, reason="invalid level price"`           |
| Zero / no volume baseline       | `confirmed=False, reason="no volume baseline"`            |
| Insufficient bars (Acceptance)  | `confirmed=False, reason="need N bars, have M"`           |
| Zone resolver raises (callable) | `confirmed=False, reason="zone resolver failed: ..."`     |
| `l2_state is None` (strict)     | `confirmed=False, reason="no L2 state"`                   |
| `l2_state is None` (pass-thru)  | `confirmed=True, strength=0.0`                            |
| Invalid pattern name (config)   | `ValueError` at construction (caller bug, not runtime)    |

All other invalid configurations (e.g. `min_bars=0`, `lookback_bars=0`) are
caught at `check_confirmation` time and returned as failed results with a
descriptive reason — they do not raise.

---

## Architecture notes

### Protocol compliance

Each plugin matches the shape Agent B's `ConfirmationProtocol` declares:

```python
def check_confirmation(
    self, level: Optional[Level], bars: list[Bar],
    l2_state: Optional[dict] = None,
) -> ConfirmationResult: ...
```

The `Level` and `Bar` types come from `framework.level_sources.base` (Agent B's
module). The directive mentioned `bars.Bar` namedtuple at `/Users/duffy/warrior_bot_v2/bars.py`,
but Agent B chose to define a framework-local `Bar` dataclass with `range_size`,
`body`, `upper_wick`, `lower_wick` derived-properties — which is what the
protocol type-annotates. We use Agent B's type, leaving `bars.py` untouched
as required.

### Strength scoring

Each plugin maps its match into `strength: [0.0, 1.0]`:
- SignalCandle: 0.5 * body-cleanliness + 0.5 * volume-ratio
- BreakoutCandle: 0.5 * breakout-magnitude + 0.5 * volume-multiplier
- Acceptance: 0.6 * close-clustering + 0.4 * extra-bars-in-zone
- Rejection: 0.5 * poke-depth + 0.5 * reclaim-distance
- VolumeConfirm: asymptotic mapping ratio -> [0, 1]
- L2Confirm: 0.6 * imbalance-margin + 0.4 * stacking-bonus

`ConfirmationResult.__post_init__` (Agent B) clamps `strength` to `[0, 1]`,
so downstream code never sees an out-of-range value even if a plugin's
formula slips.

### Pure / stateless

No plugin holds session state between calls. They take inputs, return a
result. This makes them safe to run in parallel across symbols, easy to
test in isolation, and trivial to backtest.

---

## Files added

| Path                                                | Lines |
|-----------------------------------------------------|-------|
| `framework/confirmations/signal_candle.py`          | 248   |
| `framework/confirmations/breakout_candle.py`        | 197   |
| `framework/confirmations/acceptance.py`             | 170   |
| `framework/confirmations/rejection.py`              | 213   |
| `framework/confirmations/volume_confirm.py`         | 135   |
| `framework/confirmations/l2_confirm.py`             | 220   |
| `framework/confirmations/__init__.py`               | 29    |
| `tests/framework/test_confirmations.py`             | 670   |

No existing files were modified except `framework/confirmations/__init__.py`
(extended to re-export the new plugin classes — Wave 1 left it as
protocol-only). Production code under `bot_v3_hybrid.py`, `squeeze_detector_v2.py`,
`l2_signals.py`, `bars.py`, `ibkr_feed.py` is untouched.

---

## What's next (Wave 2)

These plugins become the `confirmation_rule:` block in strategy YAML specs:

```yaml
confirmation_rule:
  type: breakout_candle
  params:
    min_vol_mult_today_vs_baseline: 2.0
    min_breakout_pct: 0.0002
    require_close_beyond: true
```

Once Agent B's YAML loader lands (or once we close that gap), strategies can
be composed declaratively from `level_source` + `arrival_detector` +
`confirmation_rule` + `stop_rule` + `target_rule`. Wave 2 strategy agents
(F-ORB, G-VWAP, H-PDH/PDL, I-Round-Number) consume these plugins directly.

The 80%-rule Acceptance plugin and L2Confirm wrapper are also Wave-5-ready
(Volume Profile + L2 enhancement). Both ship now to avoid a second pass
on this module later.
