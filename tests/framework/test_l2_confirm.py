"""Wave-5 Agent N — Tests for the three explicit L2 confirmation modes.

Covers:
  - depth_imbalance  (long, short, threshold, raw vs aggregated)
  - stacked_bids / stacked_asks  (counts, thresholds, fallbacks)
  - momentum_vacuum  (raw history, aggregated drop, direction)
  - protocol compliance + edge cases (NaN, empty book, missing keys)

Designed for ≥95% line coverage of the three Wave-5 mode paths.
The Wave-1 `legacy` mode is exercised by `test_confirmations.py::TestL2Confirm`;
this file focuses on the new modes only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from framework.confirmations.base import ConfirmationProtocol, ConfirmationResult
from framework.confirmations.l2_confirm import L2Confirm
from framework.level_sources.base import Bar, Level


BASE_TS = datetime(2026, 5, 17, 14, 30, tzinfo=timezone.utc)


def mk_level(price: float, kind: str = "PDH") -> Level:
    return Level(price=price, kind=kind, session_date=date(2026, 5, 17))


def raw_book(
    *,
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    timestamp: datetime | None = None,
    history: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    state: dict[str, Any] = {"bids": bids, "asks": asks}
    if timestamp is not None:
        state["timestamp"] = timestamp
    if history is not None:
        state["history"] = history
    state.update(extra)
    return state


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    def test_implements_protocol_in_all_modes(self):
        for mode in (
            "legacy",
            "depth_imbalance",
            "stacked_bids",
            "stacked_asks",
            "momentum_vacuum",
        ):
            l2c = L2Confirm(mode=mode)
            assert isinstance(l2c, ConfirmationProtocol)

    def test_unknown_mode_raises(self):
        l2c = L2Confirm(mode="nonsense")  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            l2c.check_confirmation(mk_level(10.0), [], raw_book(bids=[], asks=[]))

    def test_none_state_strict(self):
        for mode in (
            "depth_imbalance",
            "stacked_bids",
            "stacked_asks",
            "momentum_vacuum",
        ):
            l2c = L2Confirm(mode=mode, pass_through_on_missing=False)
            res = l2c.check_confirmation(mk_level(10.0), [], None)
            assert not res.confirmed
            assert "no L2" in res.reason

    def test_none_state_pass_through(self):
        for mode in (
            "depth_imbalance",
            "stacked_bids",
            "stacked_asks",
            "momentum_vacuum",
        ):
            l2c = L2Confirm(mode=mode, pass_through_on_missing=True)
            res = l2c.check_confirmation(mk_level(10.0), [], None)
            assert res.confirmed
            assert res.strength == 0.0


# ---------------------------------------------------------------------------
# Mode 1: depth_imbalance
# ---------------------------------------------------------------------------


class TestDepthImbalance:
    def test_long_pass_canonical(self):
        # Long: bid/ask = 5000/2000 = 2.5 >= 1.5
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5, top_n=5)
        book = raw_book(
            bids=[(10.00, 2000), (9.99, 1500), (9.98, 1000), (9.97, 300), (9.96, 200)],
            asks=[(10.01, 500), (10.02, 400), (10.03, 400), (10.04, 400), (10.05, 300)],
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert res.confirmed
        assert res.pattern_name == "l2_confirm_depth_imbalance"
        assert res.metadata["ratio"] >= 1.5
        assert 0.0 <= res.strength <= 1.0

    def test_long_fail_below_threshold(self):
        # bid/ask = 2000/2000 = 1.0 < 1.5
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5)
        book = raw_book(
            bids=[(10.00, 1000), (9.99, 500), (9.98, 500)],
            asks=[(10.01, 1000), (10.02, 500), (10.03, 500)],
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert not res.confirmed
        assert "depth_imbalance long fail" in res.reason

    def test_short_pass(self):
        # Short: ask/bid = 6000/1500 = 4.0 >= 1.5
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5)
        book = raw_book(
            bids=[(10.00, 500), (9.99, 500), (9.98, 500)],
            asks=[(10.01, 3000), (10.02, 2000), (10.03, 1000)],
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDL"), [], book)
        assert res.confirmed
        assert res.metadata["direction"] == "short"

    def test_short_fail(self):
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5)
        book = raw_book(
            bids=[(10.00, 1000), (9.99, 1000)],
            asks=[(10.01, 800), (10.02, 800)],
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDL"), [], book)
        assert not res.confirmed

    def test_top_n_constraint(self):
        # Only count top 2 — deep levels with size shouldn't help.
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5, top_n=2)
        book = raw_book(
            bids=[(10.00, 500), (9.99, 500), (9.98, 9000), (9.97, 9000)],
            asks=[(10.01, 1000), (10.02, 1000), (10.03, 100), (10.04, 100)],
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        # top 2 ratio = 1000/2000 = 0.5
        assert not res.confirmed

    def test_empty_book(self):
        l2c = L2Confirm(mode="depth_imbalance")
        book = raw_book(bids=[], asks=[])
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert not res.confirmed
        assert "empty book" in res.reason

    def test_only_bids(self):
        # ask_size == 0 -> ratio = inf -> long passes, strength = 1.0
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5)
        book = raw_book(bids=[(10.0, 1000)], asks=[])
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert res.confirmed
        assert res.strength == 1.0

    def test_only_asks_long_fails(self):
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5)
        book = raw_book(bids=[], asks=[(10.01, 1000)])
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        # bid_size=0 but ask_size>0 -> long ratio = 0/1000 = 0 < 1.5
        assert not res.confirmed

    def test_aggregated_state(self):
        # Aggregated dict with imbalance = 0.7 (bid-share).  ratio = 7/3 = 2.33
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5)
        res = l2c.check_confirmation(
            mk_level(10.0, "PDH"), [], {"imbalance": 0.7}
        )
        assert res.confirmed
        assert res.metadata["ratio"] == pytest.approx(0.7 / 0.3, rel=1e-3)

    def test_aggregated_state_short(self):
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5)
        # bid-share = 0.3 -> ask/bid = 0.7/0.3 = 2.33 -> short passes
        res = l2c.check_confirmation(
            mk_level(10.0, "PDL"), [], {"imbalance": 0.3}
        )
        assert res.confirmed

    def test_aggregated_extremes(self):
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5)
        # imbalance=1.0 -> all bids -> long passes with inf
        r_long = l2c.check_confirmation(mk_level(10.0, "PDH"), [], {"imbalance": 1.0})
        assert r_long.confirmed
        # imbalance=0.0 -> all asks -> short passes with inf
        r_short = l2c.check_confirmation(mk_level(10.0, "PDL"), [], {"imbalance": 0.0})
        assert r_short.confirmed

    def test_aggregated_missing_imbalance(self):
        l2c = L2Confirm(mode="depth_imbalance")
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], {})
        assert not res.confirmed

    def test_aggregated_nan_imbalance(self):
        l2c = L2Confirm(mode="depth_imbalance")
        res = l2c.check_confirmation(
            mk_level(10.0, "PDH"), [], {"imbalance": float("nan")}
        )
        assert not res.confirmed

    def test_strength_increases_with_ratio(self):
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5)
        low = raw_book(
            bids=[(10.00, 1600)],
            asks=[(10.01, 1000)],
        )  # 1.6
        high = raw_book(
            bids=[(10.00, 5000)],
            asks=[(10.01, 1000)],
        )  # 5.0
        r_low = l2c.check_confirmation(mk_level(10.0, "PDH"), [], low)
        r_high = l2c.check_confirmation(mk_level(10.0, "PDH"), [], high)
        assert r_low.confirmed and r_high.confirmed
        assert r_high.strength >= r_low.strength

    def test_strength_clamped_to_unit_interval(self):
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5)
        book = raw_book(
            bids=[(10.00, 1_000_000)],
            asks=[(10.01, 100)],
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert res.confirmed
        assert 0.0 <= res.strength <= 1.0

    def test_nan_sizes_skipped(self):
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5, top_n=3)
        book = raw_book(
            bids=[(10.00, 2500), (9.99, float("nan")), (9.98, 1500)],
            asks=[(10.01, 500), (10.02, 500), (10.03, 500)],
        )
        # bid total skips NaN -> 2500+1500=4000; ask 1500; ratio=2.67 >= 1.5
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert res.confirmed


# ---------------------------------------------------------------------------
# Mode 2: stacked_bids / stacked_asks
# ---------------------------------------------------------------------------


class TestStacked:
    def test_three_consecutive_bids_above_threshold(self):
        l2c = L2Confirm(
            mode="stacked_bids", stack_size_threshold=1000, stack_levels_required=3
        )
        book = raw_book(
            bids=[(10.00, 1500), (9.99, 1200), (9.98, 1100), (9.97, 200)],
            asks=[(10.01, 500)],
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert res.confirmed
        assert res.metadata["count"] == 3
        assert res.metadata["stacked_size"] == pytest.approx(3800)

    def test_only_two_consecutive_fails(self):
        l2c = L2Confirm(
            mode="stacked_bids", stack_size_threshold=1000, stack_levels_required=3
        )
        book = raw_book(
            bids=[(10.00, 1500), (9.99, 1200), (9.98, 800), (9.97, 1100)],
            asks=[],
        )
        # third level 800 < threshold -> count breaks at 2
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert not res.confirmed
        assert res.metadata["count"] == 2

    def test_first_level_below_threshold_count_zero(self):
        l2c = L2Confirm(
            mode="stacked_bids", stack_size_threshold=1000, stack_levels_required=3
        )
        book = raw_book(
            bids=[(10.00, 500), (9.99, 5000), (9.98, 5000), (9.97, 5000)],
            asks=[],
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert not res.confirmed
        assert res.metadata["count"] == 0

    def test_stacked_asks_for_short(self):
        l2c = L2Confirm(
            mode="stacked_asks", stack_size_threshold=1000, stack_levels_required=3
        )
        book = raw_book(
            bids=[(10.00, 100)],
            asks=[(10.01, 2000), (10.02, 1500), (10.03, 1100), (10.04, 200)],
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDL"), [], book)
        assert res.confirmed
        assert res.pattern_name == "l2_confirm_stacked_asks"
        assert res.metadata["count"] == 3

    def test_custom_threshold(self):
        l2c = L2Confirm(
            mode="stacked_bids", stack_size_threshold=5000, stack_levels_required=2
        )
        book = raw_book(
            bids=[(10.00, 6000), (9.99, 5500), (9.98, 4500)],
            asks=[],
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert res.confirmed
        assert res.metadata["count"] == 2

    def test_empty_levels(self):
        l2c = L2Confirm(mode="stacked_bids")
        book = raw_book(bids=[], asks=[])
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert not res.confirmed
        assert res.metadata["count"] == 0

    def test_aggregated_fallback_bids(self):
        # Aggregated state from l2_signals.py — uses bid_stack_levels.
        state = {
            "bid_stack_levels": [(10.00, 1500), (9.99, 2000), (9.98, 1100)],
        }
        l2c = L2Confirm(
            mode="stacked_bids", stack_size_threshold=1000, stack_levels_required=3
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], state)
        assert res.confirmed
        assert "aggregated stacked_bids" in res.reason

    def test_aggregated_fallback_not_enough(self):
        state = {"bid_stack_levels": [(10.00, 1500), (9.99, 500)]}
        l2c = L2Confirm(
            mode="stacked_bids", stack_size_threshold=1000, stack_levels_required=3
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], state)
        assert not res.confirmed

    def test_stacked_asks_no_levels_no_fallback(self):
        l2c = L2Confirm(mode="stacked_asks")
        state = {"bid_stack_levels": [(10.0, 9999)]}  # bid info only, no ask side
        res = l2c.check_confirmation(mk_level(10.0, "PDL"), [], state)
        assert not res.confirmed
        assert "no asks levels" in res.reason

    def test_nan_in_levels_breaks_chain(self):
        l2c = L2Confirm(
            mode="stacked_bids", stack_size_threshold=1000, stack_levels_required=3
        )
        book = raw_book(
            bids=[(10.0, 1500), (9.99, float("nan")), (9.98, 1500), (9.97, 1500)],
            asks=[],
        )
        # NaN breaks consecutive run after 1 level
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert not res.confirmed
        assert res.metadata["count"] == 1

    def test_strength_in_unit_interval(self):
        l2c = L2Confirm(
            mode="stacked_bids", stack_size_threshold=1000, stack_levels_required=3
        )
        book = raw_book(
            bids=[(10.0, 5000)] * 10,
            asks=[],
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert res.confirmed
        assert 0.0 <= res.strength <= 1.0


# ---------------------------------------------------------------------------
# Mode 3: momentum_vacuum
# ---------------------------------------------------------------------------


class TestMomentumVacuum:
    def _snap(self, *, t: datetime, bid_sz: float, ask_sz: float) -> dict[str, Any]:
        return {
            "timestamp": t,
            "bids": [(10.00, bid_sz)],
            "asks": [(10.01, ask_sz)],
        }

    def test_long_vacuum_pass(self):
        # Ask side dropped 70% in last 5s -> long vacuum confirmed.
        now = BASE_TS
        history = [
            self._snap(t=now - timedelta(seconds=6), bid_sz=1000, ask_sz=5000),
            self._snap(t=now - timedelta(seconds=4), bid_sz=1000, ask_sz=3000),
        ]
        cur = {
            "timestamp": now,
            "bids": [(10.00, 1000)],
            "asks": [(10.01, 1500)],
            "history": history,
        }
        l2c = L2Confirm(
            mode="momentum_vacuum", vacuum_drop_pct=0.50, vacuum_window_secs=5.0
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], cur)
        assert res.confirmed
        assert res.metadata["drop_pct"] == pytest.approx(0.70)

    def test_long_vacuum_fail_drop_too_small(self):
        now = BASE_TS
        history = [
            self._snap(t=now - timedelta(seconds=6), bid_sz=1000, ask_sz=2000),
        ]
        cur = {
            "timestamp": now,
            "bids": [(10.00, 1000)],
            "asks": [(10.01, 1500)],  # 25% drop only
            "history": history,
        }
        l2c = L2Confirm(
            mode="momentum_vacuum", vacuum_drop_pct=0.50, vacuum_window_secs=5.0
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], cur)
        assert not res.confirmed

    def test_short_vacuum(self):
        # Bid side dropped 60% -> short vacuum confirmed.
        now = BASE_TS
        history = [
            self._snap(t=now - timedelta(seconds=6), bid_sz=5000, ask_sz=1000),
        ]
        cur = {
            "timestamp": now,
            "bids": [(10.00, 2000)],  # -60%
            "asks": [(10.01, 1000)],
            "history": history,
        }
        l2c = L2Confirm(
            mode="momentum_vacuum", vacuum_drop_pct=0.50, vacuum_window_secs=5.0
        )
        res = l2c.check_confirmation(mk_level(10.0, "PDL"), [], cur)
        assert res.confirmed
        assert res.metadata["opp_side"] == "bids"

    def test_aggregated_drop_pct_pass(self):
        l2c = L2Confirm(mode="momentum_vacuum", vacuum_drop_pct=0.50)
        res = l2c.check_confirmation(
            mk_level(10.0, "PDH"),
            [],
            {"opposite_side_drop_pct": 0.7},
        )
        assert res.confirmed
        assert res.metadata["drop_pct"] == pytest.approx(0.7)

    def test_aggregated_drop_pct_fail(self):
        l2c = L2Confirm(mode="momentum_vacuum", vacuum_drop_pct=0.50)
        res = l2c.check_confirmation(
            mk_level(10.0, "PDH"),
            [],
            {"opposite_side_drop_pct": 0.1},
        )
        assert not res.confirmed

    def test_no_history_no_aggregate(self):
        l2c = L2Confirm(mode="momentum_vacuum")
        res = l2c.check_confirmation(
            mk_level(10.0, "PDH"),
            [],
            raw_book(bids=[(10.0, 100)], asks=[(10.01, 100)]),
        )
        assert not res.confirmed
        assert "no L2 history" in res.reason

    def test_missing_timestamp(self):
        l2c = L2Confirm(mode="momentum_vacuum")
        # Pre-existing history but no current ts and no ts on last snap
        cur = {
            "bids": [(10.0, 100)],
            "asks": [(10.01, 100)],
            "history": [{"bids": [(10.0, 200)], "asks": [(10.01, 200)]}],
        }
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], cur)
        assert not res.confirmed
        assert "missing timestamp" in res.reason

    def test_zero_reference_size(self):
        now = BASE_TS
        history = [self._snap(t=now - timedelta(seconds=6), bid_sz=1000, ask_sz=0)]
        cur = {
            "timestamp": now,
            "bids": [(10.0, 100)],
            "asks": [(10.01, 100)],
            "history": history,
        }
        l2c = L2Confirm(mode="momentum_vacuum")
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], cur)
        assert not res.confirmed

    def test_history_with_iso_timestamps(self):
        # Strings should be parsed via fromisoformat.
        now = BASE_TS.replace(tzinfo=None)  # iso-friendly
        history = [
            {
                "timestamp": (now - timedelta(seconds=6)).isoformat(),
                "bids": [(10.0, 1000)],
                "asks": [(10.01, 4000)],
            },
        ]
        cur = {
            "timestamp": now.isoformat(),
            "bids": [(10.0, 1000)],
            "asks": [(10.01, 1000)],  # 75% drop
            "history": history,
        }
        l2c = L2Confirm(mode="momentum_vacuum", vacuum_drop_pct=0.50)
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], cur)
        assert res.confirmed

    def test_aggregated_drop_with_nan(self):
        l2c = L2Confirm(mode="momentum_vacuum")
        res = l2c.check_confirmation(
            mk_level(10.0, "PDH"),
            [],
            {"opposite_side_drop_pct": float("nan"), "bids": [], "asks": []},
        )
        # NaN aggregated -> falls through; no history either -> missing
        assert not res.confirmed

    def test_strength_in_unit_interval_vacuum(self):
        l2c = L2Confirm(mode="momentum_vacuum")
        res = l2c.check_confirmation(
            mk_level(10.0, "PDH"),
            [],
            {"opposite_side_drop_pct": 0.95},
        )
        assert res.confirmed
        assert 0.0 <= res.strength <= 1.0


# ---------------------------------------------------------------------------
# Direction inference (auto / explicit override)
# ---------------------------------------------------------------------------


class TestDirectionInference:
    def test_auto_uses_long_for_pdh(self):
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5)
        book = raw_book(bids=[(10.00, 2000)], asks=[(10.01, 1000)])
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], book)
        assert res.metadata["direction"] == "long"

    def test_auto_uses_short_for_pdl(self):
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5)
        book = raw_book(bids=[(10.00, 1000)], asks=[(10.01, 2000)])
        res = l2c.check_confirmation(mk_level(10.0, "PDL"), [], book)
        assert res.metadata["direction"] == "short"

    def test_explicit_long_override(self):
        l2c = L2Confirm(mode="depth_imbalance", direction="long", min_imbalance=1.5)
        book = raw_book(bids=[(10.00, 2000)], asks=[(10.01, 1000)])
        # PDL says short, but direction forced long.
        res = l2c.check_confirmation(mk_level(10.0, "PDL"), [], book)
        assert res.metadata["direction"] == "long"
        assert res.confirmed

    def test_no_level_defaults_long(self):
        l2c = L2Confirm(mode="depth_imbalance", min_imbalance=1.5)
        book = raw_book(bids=[(10.00, 2000)], asks=[(10.01, 1000)])
        res = l2c.check_confirmation(None, [], book)
        assert res.metadata["direction"] == "long"
        assert res.confirmed


# ---------------------------------------------------------------------------
# Cross-cutting invariants
# ---------------------------------------------------------------------------


class TestInvariants:
    def test_result_metadata_includes_mode(self):
        for mode in (
            "depth_imbalance",
            "stacked_bids",
            "stacked_asks",
            "momentum_vacuum",
        ):
            l2c = L2Confirm(mode=mode, pass_through_on_missing=True)
            res = l2c.check_confirmation(mk_level(10.0), [], None)
            # pass-through path
            assert res.metadata["mode"] == mode

    def test_legacy_mode_still_works(self):
        """Sanity: Wave-1 mode unchanged."""
        l2c = L2Confirm(mode="legacy", min_imbalance=0.55, max_spread_pct=1.0)
        state = {
            "imbalance": 0.65,
            "imbalance_trend": "rising",
            "bid_stacking": False,
            "bid_stack_levels": [],
            "large_bid": False,
            "large_ask": False,
            "spread_pct": 0.5,
            "ask_thinning": False,
            "signals": [],
        }
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], state)
        assert res.confirmed
        assert res.metadata["mode"] == "legacy"

    def test_default_mode_is_legacy(self):
        l2c = L2Confirm()
        assert l2c.mode == "legacy"

    def test_level_sum_handles_bad_tuple(self):
        # Levels with malformed entries shouldn't crash; total should ignore them.
        from framework.confirmations.l2_confirm import _level_sum
        assert _level_sum(None, 5) == 0.0
        assert _level_sum([(10.0,)], 5) == 0.0  # index error
        assert _level_sum([(10.0, "bad")], 5) == 0.0  # ValueError
        assert _level_sum([(10.0, 100), (9.99, 200)], 5) == 300.0

    def test_consecutive_above_empty(self):
        from framework.confirmations.l2_confirm import _consecutive_above
        assert _consecutive_above(None, 1000) == 0
        assert _consecutive_above([], 1000) == 0
        # Malformed entry breaks chain
        assert _consecutive_above([(10.0, 2000), (9.99,)], 1000) == 1

    def test_is_raw_snapshot_helper(self):
        from framework.confirmations.l2_confirm import _is_raw_snapshot
        assert _is_raw_snapshot({"bids": [], "asks": []}) is True
        assert _is_raw_snapshot({"imbalance": 0.5}) is False

    def test_vacuum_history_iso_with_no_explicit_current_ts(self):
        """When current state has no ts, fall back to last history entry ts."""
        now = BASE_TS
        history = [
            {
                "timestamp": (now - timedelta(seconds=6)).isoformat(),
                "bids": [(10.0, 1000)],
                "asks": [(10.01, 4000)],
            },
            {
                "timestamp": now.isoformat(),
                "bids": [(10.0, 1000)],
                "asks": [(10.01, 1000)],  # 75% drop
            },
        ]
        cur = {
            "bids": [(10.0, 1000)],
            "asks": [(10.01, 1000)],
            "history": history,
        }
        l2c = L2Confirm(mode="momentum_vacuum", vacuum_drop_pct=0.50)
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], cur)
        assert res.confirmed

    def test_vacuum_history_snapshot_with_bad_timestamp(self):
        """Snapshots with non-parseable timestamps are skipped."""
        now = BASE_TS
        history = [
            {"timestamp": "not-a-date", "bids": [(10.0, 1000)], "asks": [(10.01, 5000)]},
            {
                "timestamp": now - timedelta(seconds=6),
                "bids": [(10.0, 1000)],
                "asks": [(10.01, 5000)],
            },
        ]
        cur = {
            "timestamp": now,
            "bids": [(10.0, 1000)],
            "asks": [(10.01, 1000)],
            "history": history,
        }
        l2c = L2Confirm(mode="momentum_vacuum", vacuum_drop_pct=0.50)
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], cur)
        assert res.confirmed

    def test_vacuum_all_history_inside_window(self):
        """If every history snap is inside the window, fall back to oldest."""
        now = BASE_TS
        history = [
            {
                "timestamp": now - timedelta(seconds=2),
                "bids": [(10.0, 1000)],
                "asks": [(10.01, 4000)],
            },
        ]
        cur = {
            "timestamp": now,
            "bids": [(10.0, 1000)],
            "asks": [(10.01, 1000)],  # 75% drop vs ref
            "history": history,
        }
        l2c = L2Confirm(mode="momentum_vacuum", vacuum_drop_pct=0.50,
                        vacuum_window_secs=5.0)
        res = l2c.check_confirmation(mk_level(10.0, "PDH"), [], cur)
        assert res.confirmed
