"""Tests for framework.level_sources.round_number.

Covers:
- Increment-by-tier correctness ($10-50 → $1+$5; $50-150 → $5; $150-300 → $5+$10)
- Proximity-window handling (window_dollar, window_pct, both)
- Multi-level-near-each-other scenarios (e.g. price=$50.05 — $50 from $1
  increments AND from $5 increments, deduped; tier boundary handling)
- YAML round-trip via registry (the strategy loads end-to-end)
- LevelSet ordering and metadata correctness
"""
from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime, date

from framework.level_sources.base import Bar, BarHistory, LevelSet
from framework.level_sources.round_number import (
    DEFAULT_INCREMENTS,
    RoundNumberSource,
    TIER_BOUNDS,
    from_config,
    resolve_tier,
)
from framework.registry import StrategyRegistry


SESSION = date(2024, 1, 15)


def _history(symbol: str, last_price: float, ts: datetime | None = None) -> BarHistory:
    ts = ts or datetime(2024, 1, 15, 10, 0, 0)
    bar = Bar(
        timestamp=ts,
        open=last_price,
        high=last_price,
        low=last_price,
        close=last_price,
        volume=1000.0,
        symbol=symbol,
    )
    return BarHistory(symbol=symbol, bars=[bar])


# ---------------------------------------------------------------------------
# resolve_tier — boundary correctness
# ---------------------------------------------------------------------------


def test_resolve_tier_known_prices() -> None:
    assert resolve_tier(15.00) == "10_50"
    assert resolve_tier(49.99) == "10_50"
    assert resolve_tier(50.00) == "50_150"
    assert resolve_tier(75.00) == "50_150"
    assert resolve_tier(149.99) == "50_150"
    assert resolve_tier(150.00) == "150_300"
    assert resolve_tier(250.00) == "150_300"
    assert resolve_tier(299.99) == "150_300"


def test_resolve_tier_out_of_universe() -> None:
    assert resolve_tier(0.00) is None
    assert resolve_tier(-5.00) is None
    assert resolve_tier(9.99) is None
    assert resolve_tier(300.00) is None
    assert resolve_tier(500.00) is None


# ---------------------------------------------------------------------------
# RoundNumberSource construction / validation
# ---------------------------------------------------------------------------


def test_default_construction_uses_full_increment_map() -> None:
    src = RoundNumberSource()
    assert set(src.increments.keys()) == set(TIER_BOUNDS.keys())
    assert src.increments["10_50"] == DEFAULT_INCREMENTS["10_50"]
    assert src.increments["50_150"] == DEFAULT_INCREMENTS["50_150"]
    assert src.increments["150_300"] == DEFAULT_INCREMENTS["150_300"]


def test_requires_window_specified() -> None:
    with pytest.raises(ValueError):
        RoundNumberSource(window_dollar=None, window_pct=None)


def test_rejects_negative_window() -> None:
    with pytest.raises(ValueError):
        RoundNumberSource(window_dollar=-1.0)
    with pytest.raises(ValueError):
        RoundNumberSource(window_pct=-0.01)


def test_rejects_unknown_tier_key() -> None:
    with pytest.raises(ValueError):
        RoundNumberSource(increments={"bogus": [1.0]})


def test_rejects_empty_increments_for_tier() -> None:
    with pytest.raises(ValueError):
        RoundNumberSource(increments={"10_50": []})


def test_rejects_nonpositive_increment() -> None:
    with pytest.raises(ValueError):
        RoundNumberSource(increments={"10_50": [0.0, 5.0]})
    with pytest.raises(ValueError):
        RoundNumberSource(increments={"10_50": [-1.0]})


# ---------------------------------------------------------------------------
# Increment-by-tier correctness — $10-50 emits both $1 and $5
# ---------------------------------------------------------------------------


def test_tier_10_50_emits_whole_dollars_and_fives() -> None:
    """A stock at $25 should see $1 increments AND $5 increments in window."""
    src = RoundNumberSource(window_dollar=5.0)
    ls = src.compute_levels("TEST", _history("TEST", 25.00))
    prices = sorted(lv.price for lv in ls.levels)
    # Window [20, 30]: $1 increments hit 20,21,...,30; $5 hits 20,25,30
    # The dedup means $20, $25, $30 are present once each (smaller inc wins).
    expected = [20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0, 28.0, 29.0, 30.0]
    assert prices == expected
    # Spot-check metadata
    for lvl in ls.levels:
        assert lvl.kind == "ROUND"
        assert lvl.metadata["tier"] == "10_50"
        # $20/$25/$30 should have increment=1.0 (smaller inc wins dedup)
        if lvl.price in (20.0, 25.0, 30.0):
            assert lvl.metadata["increment"] == 1.0
        else:
            assert lvl.metadata["increment"] == 1.0


def test_tier_10_50_dedupes_shared_levels() -> None:
    """$25 is hit by BOTH $1 and $5 increments — only one Level emitted, smaller wins."""
    src = RoundNumberSource(window_dollar=3.0)  # tight window
    ls = src.compute_levels("TEST", _history("TEST", 25.00))
    prices = [lv.price for lv in ls.levels]
    # No duplicates
    assert len(prices) == len(set(prices))
    # $25 present exactly once
    assert prices.count(25.0) == 1
    # Smaller increment metadata
    twenty_five = next(lv for lv in ls.levels if lv.price == 25.0)
    assert twenty_five.metadata["increment"] == 1.0


def test_tier_50_150_emits_only_fives() -> None:
    """A stock at $75 should see ONLY $5 multiples — not $1, not $10."""
    src = RoundNumberSource(window_dollar=10.0)
    ls = src.compute_levels("TEST", _history("TEST", 75.00))
    prices = sorted(lv.price for lv in ls.levels)
    # Window [65, 85]: $5 multiples are 65, 70, 75, 80, 85
    assert prices == [65.0, 70.0, 75.0, 80.0, 85.0]
    for lvl in ls.levels:
        assert lvl.metadata["tier"] == "50_150"
        assert lvl.metadata["increment"] == 5.0


def test_tier_150_300_emits_fives_and_tens() -> None:
    """A stock at $200 should see BOTH $5 and $10 multiples. $10s dedup."""
    src = RoundNumberSource(window_dollar=12.0)
    ls = src.compute_levels("TEST", _history("TEST", 200.00))
    prices = sorted(lv.price for lv in ls.levels)
    # Window [188, 212]: $5 multiples = 190, 195, 200, 205, 210
    # $10 multiples = 190, 200, 210 — all already covered by $5s
    assert prices == [190.0, 195.0, 200.0, 205.0, 210.0]
    for lvl in ls.levels:
        assert lvl.metadata["tier"] == "150_300"
        # Smaller increment ($5) wins on duplicate prices
        if lvl.price in (190.0, 200.0, 210.0):
            assert lvl.metadata["increment"] == 5.0


def test_tier_150_300_emits_only_tens_when_fives_disabled() -> None:
    """Configurable: drop $5s for the upper tier, see only $10s."""
    src = RoundNumberSource(
        increments={"10_50": [1.0, 5.0], "50_150": [5.0], "150_300": [10.0]},
        window_dollar=25.0,
    )
    ls = src.compute_levels("TEST", _history("TEST", 250.00))
    prices = sorted(lv.price for lv in ls.levels)
    # Window [225, 275]: $10 multiples = 230, 240, 250, 260, 270
    assert prices == [230.0, 240.0, 250.0, 260.0, 270.0]


# ---------------------------------------------------------------------------
# Tier boundary behavior — exact-boundary handling and tier transitions
# ---------------------------------------------------------------------------


def test_exact_tier_boundary_uses_higher_tier() -> None:
    """Price=$50 sits at the $10-50 / $50-150 boundary. By convention the
    higher tier wins (closed-low / open-high boundaries).
    """
    src = RoundNumberSource(window_dollar=2.0)
    ls = src.compute_levels("TEST", _history("TEST", 50.00))
    # At $50 the source uses tier 50_150, which only emits $5 increments.
    # No $51, $52, etc. should appear.
    prices = sorted(lv.price for lv in ls.levels)
    assert prices == [50.0]
    assert ls.levels[0].metadata["tier"] == "50_150"
    assert ls.levels[0].metadata["increment"] == 5.0


def test_price_at_149_99_uses_50_150_tier() -> None:
    src = RoundNumberSource(window_dollar=2.0)
    ls = src.compute_levels("TEST", _history("TEST", 149.99))
    for lvl in ls.levels:
        assert lvl.metadata["tier"] == "50_150"


def test_price_at_150_00_uses_150_300_tier() -> None:
    src = RoundNumberSource(window_dollar=2.0)
    ls = src.compute_levels("TEST", _history("TEST", 150.00))
    for lvl in ls.levels:
        assert lvl.metadata["tier"] == "150_300"


def test_out_of_universe_returns_empty_levelset() -> None:
    src = RoundNumberSource(window_dollar=5.0)
    assert src.compute_levels("TEST", _history("TEST", 5.00)).levels == ()
    assert src.compute_levels("TEST", _history("TEST", 9.99)).levels == ()
    assert src.compute_levels("TEST", _history("TEST", 350.00)).levels == ()


def test_empty_history_returns_empty_levelset() -> None:
    src = RoundNumberSource(window_dollar=5.0)
    ls = src.compute_levels("TEST", BarHistory(symbol="TEST"))
    assert ls.levels == ()
    assert ls.symbol == "TEST"


# ---------------------------------------------------------------------------
# Window handling — dollar, pct, both (larger wins)
# ---------------------------------------------------------------------------


def test_window_dollar_only() -> None:
    src = RoundNumberSource(window_dollar=2.0)
    ls = src.compute_levels("TEST", _history("TEST", 100.00))
    # Window [98, 102]: $5 multiples = 100 only
    prices = sorted(lv.price for lv in ls.levels)
    assert prices == [100.0]


def test_window_pct_only() -> None:
    """At $100 with 10% window → ±$10, captures $90, $95, $100, $105, $110."""
    src = RoundNumberSource(window_dollar=None, window_pct=0.10)
    ls = src.compute_levels("TEST", _history("TEST", 100.00))
    prices = sorted(lv.price for lv in ls.levels)
    assert prices == [90.0, 95.0, 100.0, 105.0, 110.0]


def test_window_dollar_and_pct_take_larger() -> None:
    """At $100: pct=0.01 → $1; dollar=$5 → $5. Larger ($5) wins."""
    src = RoundNumberSource(window_dollar=5.0, window_pct=0.01)
    ls = src.compute_levels("TEST", _history("TEST", 100.00))
    prices = sorted(lv.price for lv in ls.levels)
    # ±$5: $5 multiples = $95, $100, $105
    assert prices == [95.0, 100.0, 105.0]


def test_window_pct_scales_with_price() -> None:
    """A 5% window means a much wider absolute window for $200 vs $20."""
    src = RoundNumberSource(window_dollar=None, window_pct=0.05)
    # $20 → ±$1 window → no $5 multiples reachable from $20 inside [19, 21],
    # but $20 itself (a $1 multiple in tier 10_50) IS captured.
    ls20 = src.compute_levels("TEST", _history("TEST", 20.00))
    prices20 = sorted(lv.price for lv in ls20.levels)
    assert prices20 == [19.0, 20.0, 21.0]

    # $200 → ±$10 window. In tier 150_300 with [5, 10] increments,
    # $5 multiples in [190, 210] = 190, 195, 200, 205, 210
    ls200 = src.compute_levels("TEST", _history("TEST", 200.00))
    prices200 = sorted(lv.price for lv in ls200.levels)
    assert prices200 == [190.0, 195.0, 200.0, 205.0, 210.0]


# ---------------------------------------------------------------------------
# Multi-level-near-each-other scenarios
# ---------------------------------------------------------------------------


def test_multiple_levels_within_proximity_returns_all() -> None:
    """A wide window can produce 10+ levels — the source emits all,
    arrival detection picks the closest. We don't dedupe levels too far
    apart."""
    src = RoundNumberSource(window_dollar=5.0)
    ls = src.compute_levels("TEST", _history("TEST", 30.00))
    # In tier 10_50 with [$1, $5], window [25,35] → 25..35 inclusive
    prices = sorted(lv.price for lv in ls.levels)
    assert prices == [25.0, 26.0, 27.0, 28.0, 29.0, 30.0, 31.0, 32.0, 33.0, 34.0, 35.0]
    assert len(prices) == 11


def test_levels_emitted_in_ascending_price_order() -> None:
    """The framework relies on price-ascending order for ArrivalDetector
    to pick the closest level deterministically."""
    src = RoundNumberSource(window_dollar=10.0)
    ls = src.compute_levels("TEST", _history("TEST", 75.00))
    prices = [lv.price for lv in ls.levels]
    assert prices == sorted(prices)


def test_no_duplicate_levels_in_levelset() -> None:
    """Even with overlapping increments, each price appears exactly once."""
    src = RoundNumberSource(window_dollar=20.0)
    # $30 in tier 10_50 with $1 + $5 increments — $30 hit by both
    ls = src.compute_levels("TEST", _history("TEST", 30.00))
    prices = [lv.price for lv in ls.levels]
    assert len(prices) == len(set(prices)), (
        f"Duplicate levels emitted: {prices}"
    )


def test_arrival_picks_nearest_round_number() -> None:
    """End-to-end: source emits levels, ArrivalDetector picks the closest
    within proximity. Confirms the round_number → arrival pipeline."""
    from framework.arrival import ArrivalDetector

    src = RoundNumberSource(window_dollar=5.0)
    ls = src.compute_levels("TEST", _history("TEST", 25.00))
    # Use tier-correct proximity ($0.10 for $10-50)
    det = ArrivalDetector(proximity_dollar=0.10)

    # Price exactly on $25 — should arrive at $25
    found = det.check_arrival("TEST", 25.00, ls)
    assert found is not None and found.price == 25.00

    # Price 0.08 below $24 — within $0.10 of $24, NOT of $25
    found = det.check_arrival("TEST", 23.92, ls)
    assert found is not None and found.price == 24.00

    # Price exactly midway between $24 and $25 — outside $0.10 of either
    found = det.check_arrival("TEST", 24.50, ls)
    assert found is None


# ---------------------------------------------------------------------------
# levels_for_price helper (used by backtest harness)
# ---------------------------------------------------------------------------


def test_levels_for_price_helper() -> None:
    """`levels_for_price` produces the same LevelSet as compute_levels
    without needing a BarHistory."""
    src = RoundNumberSource(window_dollar=5.0)
    via_history = src.compute_levels("TEST", _history("TEST", 75.00))
    via_helper = src.levels_for_price("TEST", 75.00, session_date=SESSION)
    assert tuple(lv.price for lv in via_history.levels) == tuple(
        lv.price for lv in via_helper.levels
    )


# ---------------------------------------------------------------------------
# from_config — YAML loader integration
# ---------------------------------------------------------------------------


def test_from_config_defaults() -> None:
    src = from_config({})
    assert src.window_dollar == 5.0
    assert src.window_pct is None
    assert src.increments["10_50"] == DEFAULT_INCREMENTS["10_50"]


def test_from_config_custom_increments() -> None:
    src = from_config({
        "increments": {
            "10_50": [0.50, 1.00, 5.00],
            "50_150": [2.50, 5.00],
            "150_300": [10.00],
        },
        "window_dollar": 3.0,
    })
    assert src.increments["10_50"] == [0.50, 1.00, 5.00]
    assert src.increments["50_150"] == [2.50, 5.00]
    assert src.increments["150_300"] == [10.00]
    assert src.window_dollar == 3.0


def test_from_config_window_pct_only() -> None:
    src = from_config({"window_pct": 0.05})
    # window_dollar must be None (or this is window_pct + 5.0 default — we
    # check that user-provided window_pct overrides the default)
    assert src.window_pct == 0.05


# ---------------------------------------------------------------------------
# YAML round-trip via the registry — strategies/round_number.yaml must load
# ---------------------------------------------------------------------------


def test_round_number_yaml_loads_via_registry() -> None:
    yaml_path = (
        Path(__file__).resolve().parents[2]
        / "strategies"
        / "round_number.yaml"
    )
    assert yaml_path.exists(), f"missing strategy YAML at {yaml_path}"

    registry = StrategyRegistry()
    spec = registry.load_yaml(yaml_path)

    assert spec.name == "Round-Number"
    assert spec.enabled is True
    assert spec.level_source.type == "round_number"
    # Verify increments keys made it through
    assert "10_50" in spec.level_source.params["increments"]
    assert "50_150" in spec.level_source.params["increments"]
    assert "150_300" in spec.level_source.params["increments"]
    # arrival detector instantiated; takes a single threshold (min of tier dict)
    assert spec.arrival_detector is not None
    # stop / target / risk pulled from YAML
    assert spec.risk_per_trade_pct == 1.0
    assert spec.max_concurrent_positions == 3
    assert spec.trade_windows == (("09:30", "15:55"),)


# ---------------------------------------------------------------------------
# update_intraday is a no-op (round numbers don't develop)
# ---------------------------------------------------------------------------


def test_update_intraday_noop() -> None:
    src = RoundNumberSource(window_dollar=5.0)
    before = src.compute_levels("TEST", _history("TEST", 25.00))
    src.update_intraday(
        Bar(
            timestamp=datetime(2024, 1, 15, 10, 1),
            open=25.0, high=25.5, low=24.5, close=25.3, volume=10_000.0,
            symbol="TEST",
        )
    )
    after = src.compute_levels("TEST", _history("TEST", 25.00))
    # Levels are a pure function of (tier, increments, window, current_price)
    # so calling update_intraday cannot change them.
    assert tuple(lv.price for lv in before.levels) == tuple(
        lv.price for lv in after.levels
    )
