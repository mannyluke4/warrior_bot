# Framework Skeleton — Wave 1 Agent B Report

**Date:** 2026-05-17
**Agent:** Wave 1 Agent B (CC)
**Directive:** `DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md` §3 Agent B
**Status:** Acceptance criteria met. Sample YAML loads end-to-end. All 69 unit tests pass.

---

## TL;DR

Built the Healthy Fluctuation Framework skeleton at `/Users/duffy/warrior_bot_v2/framework/` — a new directory tree that does not touch any existing live code. Wave 1 deliverable scope is the protocols + value objects + YAML registry + built-in stop/target/arrival rules + sample strategy spec. Wave 2 will plug in concrete level-source and confirmation implementations.

Critical rule observed: no edits to `bot_v3_hybrid.py`, `squeeze_detector_v2.py`, `ibkr_feed.py`, `l2_signals.py`, or any other live module.

---

## 1. Module structure

```
warrior_bot_v2/
├── framework/                              # NEW — all Agent B work lives here
│   ├── __init__.py                         # version string ("0.1.0-wave1-skeleton")
│   ├── arrival.py                          # ArrivalDetector (proximity-based)
│   ├── composite.py                        # CompositeTarget builder for YAML
│   ├── registry.py                         # StrategySpec, StrategyRegistry, YAML loader
│   ├── sample_strategy.yaml                # Wave-1 demo / loader fixture
│   ├── stops.py                            # StopRuleProtocol + 4 built-ins
│   ├── targets.py                          # TargetRuleProtocol + 6 built-ins
│   ├── yaml_schema.py                      # SchemaError + validate_strategy_spec()
│   ├── level_sources/
│   │   ├── __init__.py                     # re-exports protocol + value objects
│   │   └── base.py                         # Bar, BarHistory, Level, LevelSet, Protocol
│   └── confirmations/
│       ├── __init__.py
│       └── base.py                         # ConfirmationProtocol, ConfirmationResult
└── tests/framework/                        # 69 tests, all green
    ├── conftest.py                         # sys.path setup
    ├── test_registry.py                    # YAML loader + StrategySpec round-trip
    ├── test_stops.py                       # Every built-in stop rule
    ├── test_targets.py                     # Every built-in target rule + composite
    ├── test_arrival.py                     # Proximity edge cases
    └── test_schema.py                      # Invalid YAML rejection w/ clear errors
```

Agents D and E ran in parallel and wrote `framework/confirmations/*.py`, `framework/sizing.py`, `framework/risk.py`, `framework/attribution.py`, `framework/vix_regime.py`. Agent B owns only the files above; sibling modules are not Agent-B scope.

---

## 2. Plugin protocol signatures

All protocols are `typing.Protocol` with `@runtime_checkable` so duck-typed plugins satisfy them without inheritance.

```python
class LevelSourceProtocol(Protocol):
    def compute_levels(self, symbol: str, history: BarHistory) -> LevelSet: ...
    def update_intraday(self, bar: Bar) -> None: ...

class ConfirmationProtocol(Protocol):
    def check_confirmation(
        self, level: Level, bars: list[Bar], l2_state: dict[str, Any] | None
    ) -> ConfirmationResult: ...

class StopRuleProtocol(Protocol):
    def compute_stop(
        self, entry_price: float, level: Level, history: BarHistory,
        direction: Direction = "long",
    ) -> float: ...

class TargetRuleProtocol(Protocol):
    def compute_target(
        self, entry_price: float, level: Level, level_set: LevelSet,
        history: BarHistory, direction: Direction = "long",
        stop_price: Optional[float] = None,
    ) -> TargetSpec: ...
```

### Value objects (all `@dataclass(frozen=True)`)

- **`Bar`** — `timestamp, open, high, low, close, volume, symbol` + helper props (`range_size`, `body`, `upper_wick`, `lower_wick`).
- **`BarHistory`** — mutable container; supports `append`, iteration, `slice_between`.
- **`Level`** — `price, kind, session_date, metadata`. `LevelKind` is a `Literal[...]` of POC/VAH/VAL/HVN/LVN/PDH/PDL/ORH/ORL/VWAP/ROUND/PM_HIGH/PM_LOW/ANCHORED_VWAP/SWING_HIGH/SWING_LOW/BOX_TOP/BOX_BOTTOM.
- **`LevelSet`** — `symbol, session_date, levels`; helpers `all_levels`, `by_kind(kind)`, `closest_to(price)`.
- **`ConfirmationResult`** — `confirmed, pattern_name, strength (0-1), reason, metadata`.
- **`TargetSpec`** — `primary_price, session_close_exit, trailing dict, metadata`.

### Built-in plugins

| Component | Built-ins |
|---|---|
| stops | `JustPastLevel(pad_dollar)`, `OppositeRange(orh, orl)`, `InLVN(lvn_levels, pad)`, `BarLow(lookback, pad)` |
| targets | `OppositeLevel()`, `RMultiple(r)`, `SessionClose()`, `EdgeToEdge()`, `TrailingATR(atr_mult, activate_at_r)`, `CompositeTarget(primary, fallback, trailing)` |
| arrival | `ArrivalDetector(proximity_pct, proximity_dollar)` |
| level_source | Wave-2 (Agent B stores requested type + params as `LevelSourceStub`) |
| confirmation | Wave-2 (stored as `ConfirmationStub`; Agent D's parallel work registers concrete classes for later wiring) |

### StrategySpec / StrategyRegistry

`StrategySpec` is an immutable dataclass capturing the full strategy config. `StrategyRegistry` holds a `name -> spec` map with `load_yaml(path)`, `load_dict(raw)`, `register(spec)`, `get(name)`, `list_enabled()`, `list_all()`. There is a default singleton accessor (`StrategyRegistry.default()`); tests use fresh instances via `reset_default()` to avoid cross-test contamination.

YAML loading flow:
1. Parse YAML via `yaml.safe_load`.
2. `validate_strategy_spec(raw)` — schema validation with path-aware errors.
3. Instantiate `arrival_detector`, `stop_rule`, `target_rule` from registries.
4. Wrap `level_source` and `confirmation_rule` in stubs (Wave 2 swaps in real classes).
5. Build immutable `StrategySpec` and register.

Loader subtleties: `proximity_dollar` may be flat float or tiered dict (schema accepts both; loader uses min threshold so Wave 2 can resolve per-tier at strategy level). `r_multiple` aliases to `RMultiple.r`. `composite` target type triggers `build_composite_target()` which resolves `primary`/`fallback`/`trailing` from `TARGET_RULES`. `composite` stop type is reserved but `NotImplementedError` in Wave 1.

### Schema validator (`yaml_schema.py`)

Custom lightweight validator (no jsonschema dependency). Raises `SchemaError` with a `.path` attribute (e.g. `$.arrival_detector.params.proximity_pct`) for fast pinpointing. Enforces:
- All required top-level keys present
- `arrival_detector.type == 'proximity'` with at least one of `proximity_pct` / `proximity_dollar`
- Unknown `stop_rule` or `target_rule` types rejected against the live registries (composite passes through to plugin-builder)
- `trade_windows` is a non-empty list of `[HH:MM, HH:MM]` pairs (regex-validated)
- `risk_per_trade_pct > 0`, `max_concurrent_positions: int > 0`
- `name` non-empty

---

## 3. Sample strategy YAML

`framework/sample_strategy.yaml`:

```yaml
name: "Sample-Round-Number-Demo"
enabled: true

level_source:
  type: round_number
  params:
    increments:
      "10_50": [1.00, 5.00]
      "50_150": [5.00]
      "150_300": [5.00, 10.00]

arrival_detector:
  type: proximity
  params:
    proximity_pct: 0.001       # 0.1% of price
    proximity_dollar: 0.10     # OR 10 cents — larger threshold wins

confirmation_rule:
  type: signal_candle
  params:
    patterns: [doji, hammer, shooting_star]
    require_volume_increase: true

stop_rule:
  type: just_past_level
  params:
    pad_dollar: 0.05

target_rule:
  type: composite
  params:
    primary: opposite_level
    fallback: r_multiple
    r_multiple: 2.0
    activate_trailing_at_r: 1.5
    trailing_atr_mult: 1.5

risk_per_trade_pct: 1.0
max_concurrent_positions: 3

trade_windows:
  - ["09:35", "11:30"]
  - ["13:30", "15:55"]

vix_size_multiplier:
  use_vix: false
  rules:
    vix_lt_13: 0.5
    vix_13_16: 0.75
    vix_16_28: 1.0
    vix_28_35: 0.75
    vix_gt_45: 0.0
```

`StrategyRegistry().load_yaml(...)` parses this file end-to-end without runtime errors. The loaded `StrategySpec` has:
- `level_source: LevelSourceStub(type='round_number', params={...})`
- `arrival_detector: ArrivalDetector(proximity_pct=0.001, proximity_dollar=0.10)`
- `confirmation_rule: ConfirmationStub(type='signal_candle', params={...})`
- `stop_rule: JustPastLevel(pad_dollar=0.05)` — concrete
- `target_rule: CompositeTarget(primary=OppositeLevel(), fallback=RMultiple(r=2.0), trailing=TrailingATR(atr_mult=1.5, activate_at_r=1.5))` — concrete
- All risk / trade-window / VIX fields populated from YAML

The spec is not runnable (Wave 2 wires up level computation and confirmation), but it loads, validates, and produces a fully-introspectable object graph — which is exactly the Wave-1 acceptance criterion.

---

## 4. Test coverage summary

```
$ pytest tests/framework/test_{registry,stops,targets,arrival,schema}.py -v

============================== 69 passed in 0.05s ==============================
```

| File | Tests | Coverage highlights |
|---|---:|---|
| `test_registry.py` | 7 | YAML round-trip, plugin-type assertions on every section, disabled-strategy exclusion, default-singleton behavior, hand-built spec registration, missing-strategy KeyError |
| `test_stops.py` | 14 | All 4 built-ins long+short; LVN fallback chain (empty list, no-candidate-side); BarLow lookback truncation + empty-history fallback; zero-pad edge case |
| `test_targets.py` | 14 | All 6 built-ins long+short; CompositeTarget primary-resolves path; fallback-engages path; no-fallback-returns-None path; required-stop missing returns None; trailing policy emission |
| `test_arrival.py` | 10 | Construction validation (negative / both-missing rejected); exact-level, within-pct, within-dollar, just-outside; first-in-set-order resolution; symbol mismatch; pct-vs-dollar "larger wins" rule |
| `test_schema.py` | 24 | Every required key absence; composite-target acceptance; unknown plugin rejection (path in error); arity / regex / range / type checks on trade_windows, risk pct, max positions, name; tiered `proximity_dollar` dict accepted; `SchemaError.path` populated |

Total: **69 / 69 passing**. Suite runs in 50ms.

Three additional failures appear in the same test directory under `test_sizing.py` — those belong to Wave-1 Agent E (sizing/risk/attribution) and are off-by-one rounding in their HalfKellySizer (`749` vs expected `750`). Not Agent-B scope; flagged for Agent E.

---

## 5. Acceptance check

| Criterion (directive §3 Agent B) | Status |
|---|---|
| YAML loader parses `sample_strategy.yaml` end-to-end without runtime errors | PASS |
| `@dataclass StrategySpec` with all specified fields | PASS |
| `class StrategyRegistry` singleton with `load_yaml`/`register`/`get`/`list_enabled` | PASS |
| `LevelSourceProtocol` + `Level` + `LevelSet` value objects | PASS |
| `ConfirmationProtocol` + `ConfirmationResult` | PASS |
| 4 built-in stop rules | PASS |
| 6 built-in target rules including `CompositeTarget` | PASS |
| `ArrivalDetector` with pct + dollar proximity | PASS |
| Composite handling for target YAML specs | PASS |
| YAML schema validation rejecting bad specs with clear errors | PASS |
| All unit tests pass | PASS (69/69) |
| `Protocol` + `@dataclass(frozen=True)` style guide | Followed |
| No business logic | Followed (pure scaffolding; level math + confirmation patterns are Wave 2) |
| No edits to existing live code | Verified |

---

## 6. What Wave 2 picks up

The two stubs (`LevelSourceStub`, `ConfirmationStub`) carry the YAML-declared `type` and `params` forward. Wave 2 wires them to concrete classes by:

1. Adding a `LEVEL_SOURCES` registry to `framework/level_sources/__init__.py` (mirror of `STOP_RULES` / `TARGET_RULES`).
2. Replacing the stub instantiation in `registry._instantiate_level_source(block)` with a real plugin lookup.
3. Same pattern for confirmations — Agent D has already shipped the plugin classes (`SignalCandle`, `BreakoutCandle`, `Acceptance`, `Rejection`, `L2Confirm`, `VolumeConfirm`); they need a `CONFIRMATIONS` registry plus a swap-in in `registry._instantiate_confirmation(block)`.
4. Tier-aware proximity resolution: when `proximity_dollar` is a dict, defer `ArrivalDetector` construction until the symbol's price tier is known (strategy startup, not registry load).

None of this requires touching the YAML schema or breaking the spec format.

---

## 7. Files delivered

Under `/Users/duffy/warrior_bot_v2/framework/`: `__init__.py`, `level_sources/{__init__,base}.py`, `confirmations/{__init__,base}.py` (re-exports only; concrete plugins by Agent D), `arrival.py`, `stops.py`, `targets.py`, `composite.py`, `yaml_schema.py`, `registry.py`, `sample_strategy.yaml`. Under `/Users/duffy/warrior_bot_v2/tests/framework/`: `conftest.py`, `test_registry.py`, `test_stops.py`, `test_targets.py`, `test_arrival.py`, `test_schema.py`.

Wave 1 Agent B complete.
