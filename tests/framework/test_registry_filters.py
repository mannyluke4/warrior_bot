"""Tests for Wave-4 Phase B1 filter knobs on StrategySpec / registry.

Covers the new YAML keys parsed by registry.load_dict / load_yaml:
  - entry_time_window
  - abandon_rule
  - tier_filter
  - opening_bar_alignment
  - skip_mondays
  - symbol_blacklist
  - require_vwap_alignment
  - pre_entry_consolidation_max_pct
  - volume_min_multiple

Plus the framework.filters predicates that consume them.
"""
from __future__ import annotations

from datetime import datetime, date
from pathlib import Path

import pytest

from framework.registry import StrategyRegistry, StrategySpec
from framework import filters as F
from framework.yaml_schema import SchemaError


REPO = Path(__file__).resolve().parents[2]


def _fresh_registry() -> StrategyRegistry:
    StrategyRegistry.reset_default()
    return StrategyRegistry()


def _base_spec_dict() -> dict:
    """Minimal valid spec that load_dict accepts without any Wave-4 knobs."""
    return {
        "name": "TestSpec",
        "level_source": {"type": "pdh_pdl", "params": {"max_gap_days": 2}},
        "arrival_detector": {
            "type": "proximity",
            "params": {"proximity_pct": 0.001},
        },
        "confirmation_rule": {"type": "rejection", "params": {"lookback_bars": 2}},
        "stop_rule": {"type": "just_past_level", "params": {"pad_dollar": 0.10}},
        "target_rule": {"type": "r_multiple", "params": {"r_multiple": 1.5}},
        "risk_per_trade_pct": 1.0,
        "max_concurrent_positions": 3,
        "trade_windows": [["09:30", "15:55"]],
    }


# ---------------------------------------------------------------------------
# Schema parse + StrategySpec attribute round-trip
# ---------------------------------------------------------------------------


def test_pdh_fade_filtered_yaml_round_trips() -> None:
    """The shipped pdh_fade_filtered.yaml must load and expose all knobs."""
    reg = _fresh_registry()
    spec = reg.load_yaml(REPO / "strategies" / "pdh_fade_filtered.yaml")
    assert spec.name == "PDH-PDL-Fade-Filtered"
    assert spec.entry_time_window is not None
    assert spec.entry_time_window["start"] == "09:30:00"
    assert spec.entry_time_window["end"] == "09:44:59"
    assert spec.abandon_rule is not None
    assert spec.abandon_rule["minutes_after_entry"] == 10
    assert spec.abandon_rule["exit_cap_dollars"] == 300
    assert spec.abandon_rule["exit_if_not_profit"] is True


def test_pdh_breakout_f4_yaml_round_trips() -> None:
    reg = _fresh_registry()
    spec = reg.load_yaml(REPO / "strategies" / "pdh_breakout_f4.yaml")
    assert spec.name == "PDH-Breakout-F4"
    assert spec.symbol_blacklist == (
        "PLTR", "CRM", "META", "SOFI", "DIS", "ADBE", "ROKU", "MU"
    )
    assert spec.require_vwap_alignment is True
    assert spec.pre_entry_consolidation_max_pct == 1.0
    assert spec.volume_min_multiple == 2.0


def test_orb_filtered_yaml_parses_via_load_dict() -> None:
    """ORB YAML cannot be load_yaml'd through registry (opposite_range plugin
    needs runtime ORH/ORL); but load_dict on a stop-rule swap version, and the
    schema validator (validate_strategy_spec) on the raw file, must work."""
    import yaml as _yaml

    raw = _yaml.safe_load(
        (REPO / "strategies" / "orb_aligned_300plus_monskip.yaml").read_text()
    )
    # Schema check passes.
    from framework.yaml_schema import validate_strategy_spec

    validate_strategy_spec(raw)
    assert raw["tier_filter"]["min_price"] == 300.0
    assert raw["opening_bar_alignment"]["required"] is True
    assert raw["opening_bar_alignment"]["allow_doji"] is True
    assert raw["skip_mondays"] is True


# ---------------------------------------------------------------------------
# Filter predicate unit tests
# ---------------------------------------------------------------------------


def test_passes_entry_time_window_basic() -> None:
    win = {"start": "09:30:00", "end": "09:44:59", "tz": "America/New_York"}
    assert F.passes_entry_time_window(datetime(2024, 4, 1, 9, 35), win) is True
    assert F.passes_entry_time_window(datetime(2024, 4, 1, 9, 44, 59), win) is True
    assert F.passes_entry_time_window(datetime(2024, 4, 1, 9, 45), win) is False
    assert F.passes_entry_time_window(datetime(2024, 4, 1, 10, 0), win) is False
    # None window = pass
    assert F.passes_entry_time_window(datetime(2024, 4, 1, 15, 30), None) is True


def test_passes_tier_filter_min_price() -> None:
    assert F.passes_tier_filter(350.0, {"min_price": 300.0}) is True
    assert F.passes_tier_filter(299.99, {"min_price": 300.0}) is False
    assert F.passes_tier_filter(50.0, None) is True
    assert (
        F.passes_tier_filter(100.0, {"enabled": False, "min_price": 300.0}) is True
    )


def test_passes_tier_filter_min_and_max() -> None:
    spec = {"min_price": 50.0, "max_price": 150.0}
    assert F.passes_tier_filter(50.0, spec) is True
    assert F.passes_tier_filter(149.99, spec) is True
    assert F.passes_tier_filter(150.0, spec) is True
    assert F.passes_tier_filter(150.01, spec) is False
    assert F.passes_tier_filter(49.99, spec) is False


def test_classify_or5_alignment() -> None:
    # Long + green = aligned
    assert F.classify_or5_alignment(100.0, 101.0, "long") == "aligned"
    # Short + red = aligned
    assert F.classify_or5_alignment(100.0, 99.0, "short") == "aligned"
    # Long + red = misaligned
    assert F.classify_or5_alignment(100.0, 99.0, "long") == "misaligned"
    # Doji (body < 0.05%)
    assert F.classify_or5_alignment(100.0, 100.04, "long") == "doji"


def test_passes_opening_bar_alignment_doji_allowed() -> None:
    cfg = {"required": True, "allow_doji": True}
    # doji passes
    assert F.passes_opening_bar_alignment(100.0, 100.02, "long", cfg) is True
    # aligned passes
    assert F.passes_opening_bar_alignment(100.0, 101.0, "long", cfg) is True
    # misaligned fails
    assert F.passes_opening_bar_alignment(100.0, 99.0, "long", cfg) is False


def test_passes_opening_bar_alignment_doji_blocked() -> None:
    cfg = {"required": True, "allow_doji": False}
    assert F.passes_opening_bar_alignment(100.0, 100.02, "long", cfg) is False
    assert F.passes_opening_bar_alignment(100.0, 101.0, "long", cfg) is True


def test_should_skip_monday(monkeypatch) -> None:
    monkeypatch.setenv("WB_FRAMEWORK_SKIP_MONDAYS", "0")
    monday = date(2024, 4, 1)   # Apr 1, 2024 is a Monday
    tuesday = date(2024, 4, 2)
    assert F.should_skip_monday(monday, yaml_flag=False) is False
    assert F.should_skip_monday(monday, yaml_flag=True) is True
    # env override
    monkeypatch.setenv("WB_FRAMEWORK_SKIP_MONDAYS", "1")
    assert F.should_skip_monday(monday, yaml_flag=False) is True
    assert F.should_skip_monday(tuesday, yaml_flag=True) is False


def test_passes_symbol_blacklist() -> None:
    bl = ["PLTR", "CRM", "META"]
    assert F.passes_symbol_blacklist("AAPL", bl) is True
    assert F.passes_symbol_blacklist("PLTR", bl) is False
    assert F.passes_symbol_blacklist("pltr", bl) is False   # case-insensitive
    assert F.passes_symbol_blacklist("AAPL", []) is True
    assert F.passes_symbol_blacklist("AAPL", ()) is True


def test_passes_vwap_alignment() -> None:
    # Long entry above VWAP — pass
    assert F.passes_vwap_alignment(101.0, 100.0, "long", require=True) is True
    # Long entry below VWAP — fail
    assert F.passes_vwap_alignment(99.0, 100.0, "long", require=True) is False
    # Short entry below VWAP — pass
    assert F.passes_vwap_alignment(99.0, 100.0, "short", require=True) is True
    # Short entry above VWAP — fail
    assert F.passes_vwap_alignment(101.0, 100.0, "short", require=True) is False
    # require=False — always pass
    assert F.passes_vwap_alignment(99.0, 100.0, "long", require=False) is True
    # vwap unavailable — pass (conservative)
    assert F.passes_vwap_alignment(99.0, None, "long", require=True) is True


class _FakeBar:
    """Lightweight stand-in for framework.level_sources.base.Bar in tests."""

    def __init__(self, ts: datetime, o: float, h: float, l: float, c: float, v: float):
        self.timestamp = ts
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.volume = v


def test_pre_entry_consolidation_pct_tight() -> None:
    bars = [_FakeBar(datetime(2024, 4, 2, 9, 30 + i), 100, 100.3, 99.8, 100.1, 1000)
            for i in range(5)]
    pct = F.compute_5bar_consolidation_pct(bars, 100.0, lookback=5)
    assert pct is not None
    assert pct == pytest.approx(0.5, rel=1e-3)
    # 0.5% range < 1.0% threshold -> passes
    assert F.passes_pre_entry_consolidation(bars, 100.0, max_pct=1.0) is True


def test_pre_entry_consolidation_pct_loose_fails() -> None:
    # Wide range: high=101, low=99 -> 2% of price 100
    bars = [_FakeBar(datetime(2024, 4, 2, 9, 30 + i), 100, 101.0, 99.0, 100.0, 1000)
            for i in range(5)]
    assert F.passes_pre_entry_consolidation(bars, 100.0, max_pct=1.0) is False


def test_pre_entry_consolidation_insufficient_bars_passes() -> None:
    bars = [_FakeBar(datetime(2024, 4, 2, 9, 30 + i), 100, 101, 99, 100, 1000)
            for i in range(3)]
    # only 3 bars < 5 lookback -> pass-through
    assert F.passes_pre_entry_consolidation(bars, 100.0, max_pct=1.0) is True


def test_passes_volume_min_multiple() -> None:
    # 25 prior bars each volume=1000 -> baseline = 1000
    prior = [_FakeBar(datetime(2024, 4, 2, 9, 30 + i), 100, 101, 99, 100, 1000)
             for i in range(25)]
    # entry bar vol 3000 -> mult=3 >= 2 -> pass
    assert F.passes_volume_min_multiple(3000.0, prior, min_mult=2.0) is True
    # entry vol 1500 -> mult=1.5 < 2 -> fail
    assert F.passes_volume_min_multiple(1500.0, prior, min_mult=2.0) is False
    # min_mult None -> pass
    assert F.passes_volume_min_multiple(100.0, prior, min_mult=None) is True
    # insufficient prior bars -> pass
    assert F.passes_volume_min_multiple(100.0, prior[:5], min_mult=2.0) is True


def test_passes_pre_entry_filters_full_stack() -> None:
    """End-to-end: a spec with all filters active, signal passes everything."""
    spec = {
        "entry_time_window": {"start": "09:30:00", "end": "09:44:59"},
        "tier_filter": {"min_price": 300.0},
        "opening_bar_alignment": {"required": True, "allow_doji": True},
        "skip_mondays": True,
        "symbol_blacklist": ["PLTR"],
        "require_vwap_alignment": True,
        "pre_entry_consolidation_max_pct": 1.0,
        "volume_min_multiple": 2.0,
    }
    bars_before = [_FakeBar(datetime(2024, 4, 2, 9, 30 + i), 300, 300.5, 299.5, 300, 1000)
                   for i in range(25)]
    ok, reason = F.passes_pre_entry_filters(
        spec=spec,
        entry_ts=datetime(2024, 4, 2, 9, 35),   # Tuesday, within window
        entry_price=350.0,                       # above $300 tier
        direction="long",
        symbol="AAPL",                           # not blacklisted
        session_date=date(2024, 4, 2),           # Tuesday
        vwap_at_entry=340.0,                     # entry > vwap (long-aligned)
        bars_before_entry=bars_before,
        entry_bar_volume=3000.0,                 # 3x baseline
        or5_open=300.0,
        or5_close=302.0,                         # green (aligned for long)
    )
    assert ok is True
    assert reason == ""


def test_passes_pre_entry_filters_blocked_by_tier() -> None:
    spec = {"tier_filter": {"min_price": 300.0}}
    ok, reason = F.passes_pre_entry_filters(
        spec=spec,
        entry_ts=datetime(2024, 4, 2, 9, 35),
        entry_price=50.0,
        direction="long",
        symbol="AAPL",
        session_date=date(2024, 4, 2),
        vwap_at_entry=None,
        bars_before_entry=[],
        entry_bar_volume=0.0,
    )
    assert ok is False
    assert reason == "tier_filter"


def test_passes_pre_entry_filters_blocked_by_window() -> None:
    spec = {"entry_time_window": {"start": "09:30:00", "end": "09:44:59"}}
    ok, reason = F.passes_pre_entry_filters(
        spec=spec,
        entry_ts=datetime(2024, 4, 2, 10, 0),
        entry_price=50.0,
        direction="long",
        symbol="AAPL",
        session_date=date(2024, 4, 2),
        vwap_at_entry=None,
        bars_before_entry=[],
        entry_bar_volume=0.0,
    )
    assert ok is False
    assert reason == "entry_time_window"


def test_passes_pre_entry_filters_blocked_by_blacklist() -> None:
    spec = {"symbol_blacklist": ["PLTR", "CRM"]}
    ok, reason = F.passes_pre_entry_filters(
        spec=spec,
        entry_ts=datetime(2024, 4, 2, 9, 35),
        entry_price=50.0,
        direction="long",
        symbol="PLTR",
        session_date=date(2024, 4, 2),
        vwap_at_entry=None,
        bars_before_entry=[],
        entry_bar_volume=0.0,
    )
    assert ok is False
    assert reason == "symbol_blacklist"


# ---------------------------------------------------------------------------
# Schema validator coverage — confirm bad knob values fail loudly
# ---------------------------------------------------------------------------


def test_schema_rejects_bad_entry_time_window() -> None:
    bad = _base_spec_dict()
    bad["entry_time_window"] = {"start": "not-a-time", "end": "09:44:59"}
    from framework.yaml_schema import validate_strategy_spec
    with pytest.raises(SchemaError) as exc:
        validate_strategy_spec(bad)
    assert "entry_time_window" in exc.value.path


def test_schema_rejects_bad_abandon_rule() -> None:
    bad = _base_spec_dict()
    bad["abandon_rule"] = {"minutes_after_entry": -1}
    from framework.yaml_schema import validate_strategy_spec
    with pytest.raises(SchemaError) as exc:
        validate_strategy_spec(bad)
    assert "minutes_after_entry" in exc.value.path


def test_schema_rejects_bad_tier_filter() -> None:
    bad = _base_spec_dict()
    bad["tier_filter"] = {"min_price": -10.0}
    from framework.yaml_schema import validate_strategy_spec
    with pytest.raises(SchemaError) as exc:
        validate_strategy_spec(bad)
    assert "min_price" in exc.value.path


def test_schema_rejects_non_list_blacklist() -> None:
    bad = _base_spec_dict()
    bad["symbol_blacklist"] = "PLTR"  # must be list
    from framework.yaml_schema import validate_strategy_spec
    with pytest.raises(SchemaError):
        validate_strategy_spec(bad)


def test_schema_accepts_empty_blacklist() -> None:
    spec = _base_spec_dict()
    spec["symbol_blacklist"] = []
    from framework.yaml_schema import validate_strategy_spec
    validate_strategy_spec(spec)   # no raise


def test_load_dict_round_trip_all_knobs() -> None:
    """Build a dict with every knob and confirm the StrategySpec carries them."""
    reg = _fresh_registry()
    raw = _base_spec_dict()
    raw.update({
        "entry_time_window": {"start": "09:30:00", "end": "09:44:59",
                              "tz": "America/New_York"},
        "abandon_rule": {"enabled": True, "minutes_after_entry": 10,
                         "exit_if_not_profit": True, "exit_cap_dollars": 300},
        "tier_filter": {"min_price": 300.0},
        "opening_bar_alignment": {"required": True, "allow_doji": True},
        "skip_mondays": True,
        "symbol_blacklist": ["PLTR", "CRM"],
        "require_vwap_alignment": True,
        "pre_entry_consolidation_max_pct": 1.0,
        "volume_min_multiple": 2.0,
    })
    spec: StrategySpec = reg.load_dict(raw)
    assert spec.entry_time_window["end"] == "09:44:59"
    assert spec.abandon_rule["exit_cap_dollars"] == 300
    assert spec.tier_filter["min_price"] == 300.0
    assert spec.opening_bar_alignment["required"] is True
    assert spec.skip_mondays is True
    assert spec.symbol_blacklist == ("PLTR", "CRM")
    assert spec.require_vwap_alignment is True
    assert spec.pre_entry_consolidation_max_pct == 1.0
    assert spec.volume_min_multiple == 2.0
